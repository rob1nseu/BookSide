"""Source-bound chapter maps and independent review sessions; no learning cursor mutation."""

import asyncio
import json
import time

from .db import dumps, now, uid
from .documents import retrieve
from .model import ModelError
from .schemas import KnowledgeMap, ReviewPlan, Feedback, Reply
from .tutoring import validate_sources, history_context
from .attachments import attachment_image
from .runtime import bounded_action


def root_chapter(store, space_id, chapter_id):
    chapter = store.one("SELECT * FROM chapters WHERE id=? AND space_id=?", (chapter_id, space_id))
    if not chapter:
        raise ModelError("章节不存在")
    return (
        store.one("SELECT * FROM chapters WHERE id=?", (chapter["parent_id"],))
        if chapter["parent_id"]
        else chapter
    )


def material(store, space_id, root):
    sections = store.all(
        "SELECT * FROM chapters WHERE space_id=? AND (parent_id=? OR id=?) AND is_group=0 ORDER BY position",
        (space_id, root["id"], root["id"]),
    )
    if len(sections) > 24:
        raise ModelError("本章小节超过单次导图预算，请先选择较小的章节范围")
    evidence, outline = [], []
    for section in sections:
        pages = retrieve(store, space_id, section["title"], section, limit=2)
        # Same-page sections can share a source id: retain the independently clipped text.
        evidence.extend(dict(p, chapter_id=section["id"], text=p["text"][:1800], notes=p["notes"][:500]) for p in pages)
        outline.append({"id": section["id"], "title": section["title"], "sources": [p["id"] for p in pages]})
    return outline, evidence


def validate_map(payload, sections, evidence):
    payload = KnowledgeMap.model_validate(payload).model_dump()
    nodes = {n["id"]: n for n in payload["nodes"]}
    allowed = {s["id"]: set(s["sources"]) for s in sections}
    if len(nodes) != len(payload["nodes"]) or "__root" in nodes:
        raise ModelError("导图节点重复，未保存")
    for node in nodes.values():
        if node["chapter_id"] not in allowed or not set(node["sources"]) <= allowed[node["chapter_id"]]:
            raise ModelError("导图知识点与原文不匹配，未保存")
        seen, current = {node["id"]}, node
        while current["parent_id"]:
            parent = current["parent_id"]
            if parent not in nodes or parent in seen or len(seen) >= 3:
                raise ModelError("导图层级无效，未保存")
            seen.add(parent)
            current = nodes[parent]
    covered = {n["chapter_id"] for n in nodes.values()}
    if any(s["sources"] and s["id"] not in covered for s in sections):
        raise ModelError("导图遗漏了有正文的小节，请重试")
    return payload


def public_session(row):
    if not row:
        return None
    questions, attempts = json.loads(row["questions"]), json.loads(row["attempts"])
    position = row["position"]
    q = questions[position] if position < len(questions) and row["status"] == "active" else None
    return {
        "id": row["id"],
        "status": row["status"],
        "position": position,
        "count": len(questions),
        "question": {
            **{k: q.get(k) for k in ("prompt", "kind", "options", "unit", "node_id")},
            "id": f"{row['id']}:{position}",
        }
        if q
        else None,
        "attempts": attempts,
        "assisted": position in json.loads(row["assisted"]),
    }


def attempt_states(attempts, verified="已验证"):
    states = {}
    for a in attempts:
        verdict = a.get("feedback", {}).get("verdict")
        if verdict in ("incorrect", "partial") or (verdict == "correct" and a.get("assisted")):
            states[a["node_id"]] = "需巩固"
        elif verdict == "correct":
            states[a["node_id"]] = verified
        elif verdict == "uncertain":
            states[a["node_id"]] = "未验证"
    return states


def detail(store, space_id, chapter_id):
    root = root_chapter(store, space_id, chapter_id)
    row = store.one("SELECT * FROM review_maps WHERE space_id=? AND root_id=?", (space_id, root["id"]))
    if not row:
        return {"root_id": root["id"], "title": root["title"], "map": None, "session": None, "states": {}}
    sessions = store.all(
        "SELECT * FROM review_sessions WHERE space_id=? AND map_id=? ORDER BY created DESC",
        (space_id, row["id"]),
    )
    states = {}
    for session in reversed(sessions):
        states.update(attempt_states(json.loads(session["attempts"])))
    return {
        "root_id": root["id"],
        "title": root["title"],
        "map": json.loads(row["payload"]),
        "states": states,
        "round_states": attempt_states(json.loads(sessions[0]["attempts"]), "本轮已验证") if sessions else {},
        "session": public_session(sessions[0]) if sessions else None,
    }


@bounded_action
async def run_review(app, run_id, action):
    store, provider = app.state.store, app.state.provider
    run = store.one("SELECT * FROM runs WHERE id=?", (run_id,))
    started, last = time.monotonic(), ""

    async def progress(text):
        nonlocal last
        if text == last:
            return
        current = await asyncio.to_thread(store.one, "SELECT status FROM runs WHERE id=?", (run_id,))
        if not current or current["status"] != "running":
            raise asyncio.CancelledError()
        await asyncio.to_thread(
            store.write, "UPDATE runs SET partial=? WHERE id=? AND status='running'", (text, run_id)
        )
        last = text
        await asyncio.to_thread(store.write, "INSERT INTO run_stages(run_id,stage,created) VALUES(?,?,?)", (run_id, text, now()))

    try:
        await progress("正在整理本章复习内容…")
        root = root_chapter(store, run["space_id"], action.chapter_id)
        sections, evidence = await asyncio.to_thread(material, store, run["space_id"], root)
        if not evidence:
            raise ModelError("本章没有可用于复习的可靠原文")
        map_row = store.one(
            "SELECT * FROM review_maps WHERE space_id=? AND root_id=?", (run["space_id"], root["id"])
        )
        result, usage, payload, plan, session, attempt, reply = {}, {}, None, None, None, None, None
        context = {
            "action": action.action,
            "title": root["title"],
            "sections": sections,
            "evidence": evidence,
            "request": action.text,
        }
        if action.action == "review_map":
            if not map_row:
                generated, usage = await provider.generate("review_map", context, progress)
                try:
                    payload = validate_map(generated, sections, evidence)
                except ModelError as error:
                    await progress("正在核对导图的小节与引用对应关系…")
                    repair_context = dict(context, previous_map=generated,
                        validation_error=str(error),
                        request="修正导图：chapter_id 必须逐字复制 sections.id；sources 只能选该小节自己的 sources，不能使用其他小节或编造编号。保留有原文支持的知识点，覆盖有正文的小节。")
                    generated, repair_usage = await provider.generate("review_map", repair_context, progress)
                    usage = {"initial": usage, "repair": repair_usage}
                    payload = validate_map(generated, sections, evidence)
        else:
            if not map_row:
                raise ModelError("请先生成章节导图")
            nodes = json.loads(map_row["payload"])["nodes"]
            node = next((n for n in nodes if n["id"] == action.node_id), None)
            if action.node_id and not node:
                raise ModelError("知识点不属于当前导图")
            if action.action == "review_start":
                active = store.one(
                    "SELECT * FROM review_sessions WHERE map_id=? AND status='active'", (map_row["id"],)
                )
                if active:
                    raise ModelError("本轮练习尚未结束，请先完成或结束本轮")
                states = detail(store, run["space_id"], action.chapter_id)["states"]
                selected = (
                    [node]
                    if node
                    else sorted(
                        nodes,
                        key=lambda n: {"需巩固": 0, "未验证": 1, "已验证": 2}[states.get(n["id"], "未验证")],
                    )[:5]
                )
                prior = store.all(
                    "SELECT attempts,questions FROM review_sessions WHERE map_id=? ORDER BY created DESC LIMIT 3",
                    (map_row["id"],),
                )
                context.update(
                    selected_nodes=selected,
                    previous_attempts=[json.loads(p["attempts"])[-5:] for p in prior],
                    previous_questions=[
                        {"prompt": q["prompt"][:1000], "node_id": q["node_id"]}
                        for p in prior
                        for q in json.loads(p["questions"])[-5:]
                    ],
                )
                generated, usage = await provider.generate("review_plan", context, progress)
                plan = ReviewPlan.model_validate(generated).model_dump()["questions"]
                for q in plan:
                    if q["node_id"] not in {n["id"] for n in selected}:
                        raise ModelError("复习题关联了错误知识点，未保存")
                    selected_node = next(n for n in selected if n["id"] == q["node_id"])
                    allowed = next(s["sources"] for s in sections if s["id"] == selected_node["chapter_id"])
                    if not set(q["sources"]) <= set(allowed):
                        raise ModelError("复习题引用不属于对应小节，未保存")
                validate_sources({"questions": plan}, evidence)
            elif action.action == "review_node":
                if not node:
                    raise ModelError("请选择知识点")
                context.update(
                    node=node, history=history_context(store, f"node:{map_row['id']}:{node['id']}")
                )
                reply, usage = await provider.generate("reply", context, progress)
                reply = Reply.model_validate(reply).model_dump()
                validate_sources(reply, evidence)
                result = reply
            else:
                session = store.one(
                    "SELECT * FROM review_sessions WHERE id=? AND space_id=? AND map_id=? AND status='active'",
                    (action.session_id, run["space_id"], map_row["id"]),
                )
                if not session:
                    raise ModelError("复习会话已结束或不属于当前章节")
                questions = json.loads(session["questions"])
                position = session["position"]
                q = questions[position] if position < len(questions) else None
                target = f"{session['id']}:{position}"
                hint_row = store.one("SELECT level FROM hint_levels WHERE scope=?", (target,))
                hint_level = min(3, (hint_row["level"] if hint_row else 0) + 1)
                context["hint_level"] = hint_level
                if action.action != "review_end" and (not q or action.question_id != target):
                    raise ModelError("复习题目已切换，请刷新后继续")
                if action.action in ("review_answer", "review_help", "review_hint"):
                    if action.action == "review_answer":
                        if (
                            not action.text.strip()
                            and not action.selected_option
                            and not action.attachment_id
                        ):
                            raise ModelError("请填写答案或上传图片")
                        if q["kind"] == "choice" and action.selected_option not in q["options"]:
                            raise ModelError("请选择一个选项")
                        context.update(
                            question=q,
                            answer=action.selected_option or action.text,
                            selected_option=action.selected_option,
                            reasoning=action.text,
                        )
                        if action.attachment_id:
                            context["_image"] = attachment_image(
                                store, action.attachment_id, run["space_id"], target
                            )
                        feedback, usage = await provider.generate("grade", context, progress)
                        feedback = Feedback.model_validate(feedback).model_dump()
                        validate_sources(feedback, evidence)
                        if q["kind"] == "choice":
                            if action.selected_option != q["answer"]:
                                feedback["verdict"] = "incorrect"
                            elif feedback["verdict"] == "incorrect":
                                feedback["verdict"] = "partial"
                        attempt = {
                            "id": uid(),
                            "position": position,
                            "node_id": q["node_id"],
                            "answer": action.text,
                            "selected_option": action.selected_option,
                            "attachment_id": action.attachment_id,
                            "feedback": feedback,
                            "assisted": position in json.loads(session["assisted"]),
                        }
                        result = {"feedback": feedback}
                    else:
                        context.update(
                            current_question={k: q.get(k) for k in ("prompt", "options", "kind")},
                            history=history_context(store, f"review-question:{target}"),
                        )
                        if action.action == "review_hint":
                            hints = q.get("hints") or [q["hint"]]
                            reply = {"text": hints[min(hint_level, len(hints)) - 1], "sources": q["sources"]}
                        else:
                            reply, usage = await provider.generate("reply", context, progress)
                            reply = Reply.model_validate(reply).model_dump()
                            validate_sources(reply, evidence)
                        result = reply
        await progress("正在保存复习结果…")
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if not active or active[0] != "running":
                return
            if payload:
                db.execute(
                    "INSERT INTO review_maps VALUES(?,?,?,?,?)",
                    (uid(), run["space_id"], root["id"], dumps(payload), now()),
                )
            if plan:
                db.execute(
                    "INSERT INTO review_sessions(id,space_id,map_id,questions,created) VALUES(?,?,?,?,?)",
                    (uid(), run["space_id"], map_row["id"], dumps(plan), now()),
                )
            if session:
                attempts = json.loads(session["attempts"])
                if attempt:
                    attempts.append(attempt)
                    db.execute(
                        "UPDATE review_sessions SET attempts=? WHERE id=?", (dumps(attempts), session["id"])
                    )
                if action.action in ("review_next", "review_end"):
                    if action.action == "review_next" and not any(
                        a["position"] == position for a in attempts
                    ):
                        attempts.append(
                            {"id": uid(), "position": position, "node_id": q["node_id"], "skipped": True}
                        )
                    end = action.action == "review_end" or position + 1 >= len(questions)
                    db.execute(
                        "UPDATE review_sessions SET position=?,status=?,attempts=? WHERE id=?",
                        (position + 1, "done" if end else "active", dumps(attempts), session["id"]),
                    )
                if action.action in ("review_help", "review_hint"):
                    db.execute("INSERT INTO hint_levels(scope,level) VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET level=excluded.level", (target, hint_level))
                    assisted = sorted(set(json.loads(session["assisted"]) + [position]))
                    db.execute(
                        "UPDATE review_sessions SET assisted=? WHERE id=?", (dumps(assisted), session["id"])
                    )
            if reply:
                thread = (
                    f"node:{map_row['id']}:{node['id']}"
                    if action.action == "review_node"
                    else f"review-question:{target}"
                )
                for role, text in (("user", action.text), ("assistant", reply["text"])):
                    if text:
                        db.execute(
                            "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
                            (uid(), run["space_id"], thread, role, text, int(action.private), now()),
                        )
            db.execute(
                "UPDATE runs SET status='done',result=?,partial='',completed=?,elapsed=?,usage=? WHERE id=?",
                (dumps(result), now(), time.monotonic() - started, dumps(usage), run_id),
            )
    except asyncio.CancelledError:
        store.write(
            "UPDATE runs SET status='cancelled',completed=? WHERE id=? AND status='running'", (now(), run_id)
        )
    except Exception as exc:
        error = (
            str(exc) if isinstance(exc, ModelError) else "复习内容校验失败，请重试；已保存的导图和作答保留"
        )
        store.write(
            "UPDATE runs SET status='failed',error=?,completed=? WHERE id=? AND status='running'",
            (error, now(), run_id),
        )
