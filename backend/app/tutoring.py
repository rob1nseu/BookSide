import asyncio
import json
import math
import re
import time

from .db import dumps, now, uid
from .documents import retrieve
from .model import ModelError
from .schemas import Feedback, Lesson, Reply


def public_question(row):
    if not row:
        return None
    value = json.loads(row["payload"])
    return {
        **{key: value[key] for key in ("kind", "prompt", "options", "unit") if key in value},
        "id": row["id"],
        "position": row["position"],
    }


def get_question(store, chapter):
    return store.one(
        "SELECT * FROM questions WHERE chapter_id=? AND position=?",
        (chapter["id"], chapter["question_index"]),
    )


def validate_sources(result, evidence):
    allowed = {page["id"] for page in evidence}
    sources = result.get("sources", []) + [
        source for question in result.get("questions", []) for source in question["sources"]
    ]
    if any(source not in allowed for source in sources):
        raise ModelError("模型引用了不属于本次资料的内容，结果未提交")


def recompute(db, chapter_id):
    questions = db.execute(
        "SELECT id FROM questions WHERE chapter_id=? AND version=(SELECT MAX(version) FROM questions WHERE chapter_id=?)",
        (chapter_id, chapter_id),
    ).fetchall()
    passed = 0
    weak = False
    for q in questions:
        rows = db.execute(
            "SELECT * FROM attempts WHERE question_id=? AND disputed=0 ORDER BY created DESC", (q["id"],)
        ).fetchall()
        if any(json.loads(r["feedback"])["verdict"] == "correct" and not r["assisted"] for r in rows):
            passed += 1
        elif any(json.loads(r["feedback"])["verdict"] in ("incorrect", "partial") for r in rows):
            weak = True
    state = (
        "通过当前检查" if questions and passed == len(questions) else "需要巩固" if weak else "已学习，待验证"
    )
    db.execute(
        "UPDATE chapters SET state=?,passed_at=? WHERE id=?",
        (state, now() if state == "通过当前检查" else None, chapter_id),
    )


def memory_context(store, space_id, partner=False):
    if store.one("SELECT 1 FROM settings WHERE key='memory_paused' AND value='true'"):
        return []
    scope = "partner" if partner else "space"
    return store.all(
        "SELECT id,text FROM memories WHERE active=1 AND (scope='global' OR (scope=? AND (space_id=? OR ?='partner'))) ORDER BY updated DESC LIMIT 12",
        (scope, space_id, scope),
    )


def history_context(store, thread):
    rows = store.all(
        "SELECT id,role,text FROM messages WHERE thread=? ORDER BY created DESC LIMIT 12", (thread,)
    )
    # Hard character cap is explicit, not misreported as exact token accounting.
    budget, result = 16000, []
    for row in rows:
        if len(row["text"]) > budget:
            break
        result.append(row)
        budget -= len(row["text"])
    summary = store.one("SELECT text FROM summaries WHERE thread=?", (thread,))
    return {"recent": list(reversed(result)), "summary": summary["text"] if summary else ""}


async def run_action(app, run_id, action):
    store, provider = app.state.store, app.state.provider
    run = store.one("SELECT * FROM runs WHERE id=?", (run_id,))
    started = time.monotonic()
    usage = {}
    last_progress = ("", 0.0)

    async def progress(text):
        nonlocal last_progress
        if text == last_progress[0] and time.monotonic() - last_progress[1] < 0.75:
            return
        current = await asyncio.to_thread(store.one, "SELECT status,partial FROM runs WHERE id=?", (run_id,))
        if not current or current["status"] != "running":
            raise asyncio.CancelledError()
        if current["partial"] != text:
            await asyncio.to_thread(
                store.write, "UPDATE runs SET partial=? WHERE id=? AND status='running'", (text, run_id)
            )
        last_progress = (text, time.monotonic())

    try:
        await progress("正在准备当前任务…")
        partner = action.action == "partner"
        chapter = (
            None
            if partner
            else store.one(
                "SELECT * FROM chapters WHERE id=? AND space_id=?", (action.chapter_id, run["space_id"])
            )
        )
        thread = (
            "partner"
            if partner
            else (
                f"question:{action.question_id}"
                if action.action == "ask_question"
                else f"lecture:{chapter['id']}"
                if action.action == "ask"
                else run["space_id"]
            )
        )
        evidence = (
            [] if partner else retrieve(store, run["space_id"], action.text or chapter["title"], chapter)
        )
        context = {
            "request": action.text,
            "action": action.action,
            "evidence": evidence,
            "history": history_context(store, thread),
            "memory": memory_context(store, run["space_id"], partner),
        }
        if chapter:
            context["chapter"] = {k: chapter[k] for k in ("title", "state", "question_index")}
            context["course_outline"] = store.all(
                "SELECT title,parent_id,id,start_page,end_page FROM chapters WHERE space_id=? ORDER BY position LIMIT 200",
                (run["space_id"],),
            )
            prerequisites = store.all(
                "SELECT * FROM chapters WHERE space_id=? AND document_id=? AND is_group=0 AND position<? ORDER BY position DESC LIMIT 2",
                (run["space_id"], chapter["document_id"], chapter["position"]),
            )
            context["prerequisites"] = []
            for prerequisite in reversed(prerequisites):
                found = retrieve(store, run["space_id"], prerequisite["title"], prerequisite, limit=1)
                context["prerequisites"].append({"title": prerequisite["title"], "evidence": found})
                existing = {p["id"] for p in evidence}
                evidence.extend(p for p in found if p["id"] not in existing)
            context["mode"] = store.one("SELECT mode FROM spaces WHERE id=?", (run["space_id"],))["mode"]

            def search(query):
                found = retrieve(store, run["space_id"], query, limit=4)
                existing = {page["id"] for page in evidence}
                evidence.extend(page for page in found if page["id"] not in existing)
                return found

            context["_search"] = search
        question = get_question(store, chapter) if chapter else None
        question_value = json.loads(question["payload"]) if question else None
        if action.action != "ask":
            context["current_question"] = public_question(question)
        if action.action == "ask_question" and (not question or question["id"] != action.question_id):
            raise ModelError("题目已切换，请重新打开这道题的提问入口")
        if (
            action.question_id
            and action.action in ("answer", "hint", "solution", "next", "skip", "retry_grade")
            and (not question or question["id"] != action.question_id)
        ):
            raise ModelError("题目已切换，答案未提交到其他题目")
        feedback = None
        selected_option = action.selected_option
        reasoning = action.text if selected_option else ""
        lesson = None
        disputed_attempt = None
        result = {}
        if action.action in ("teach", "train"):
            if not evidence:
                raise ModelError("本章节缺少可靠文本，请查看原页或选择其他章节")
            if action.action == "teach" and chapter["lesson"]:
                raise ModelError("本章已有讲解，请使用换个解释或继续作答")
            if action.action == "train":
                context["request"] = (
                    "针对已有作答缺口生成一轮补讲和最多 3 道新题；仍覆盖本章核心目标，不重复原题。本轮是新的核心检查计划。"
                )
                context["attempts"] = store.all(
                    "SELECT answer,feedback FROM attempts WHERE chapter_id=? AND disputed=0 ORDER BY created DESC LIMIT 3",
                    (chapter["id"],),
                )
            result, usage = await provider.generate("lesson", context, progress)
            lesson = Lesson.model_validate(result).model_dump()
            if action.action == "train":
                lesson["questions"] = lesson["questions"][:3]
            validate_sources(lesson, evidence)
            result = {k: v for k, v in lesson.items() if k != "questions"}
        elif action.action in ("answer", "retry_grade"):
            if not question:
                raise ModelError("当前没有待答题目")
            answer = action.text
            if action.action == "retry_grade":
                disputed_attempt = store.one(
                    "SELECT * FROM attempts WHERE question_id=? AND disputed=1 AND reviewed=0 AND review_of IS NULL ORDER BY created DESC LIMIT 1",
                    (question["id"],),
                )
                if not disputed_attempt:
                    raise ModelError("这次作答已复核或没有待复核作答；可换题验证或跳过")
                answer = disputed_attempt["answer"]
                selected_option = disputed_attempt["selected_option"]
                reasoning = disputed_attempt["reasoning"]
            attachment_id = disputed_attempt["attachment_id"] if disputed_attempt else action.attachment_id
            if attachment_id:
                from .attachments import attachment_image

                context["_image"] = attachment_image(store, attachment_id, run["space_id"], question["id"])
            if not answer.strip() and not selected_option and not attachment_id:
                raise ModelError("请先填写回答")
            if question_value["kind"] == "choice":
                selected_option = selected_option or answer
                if selected_option not in question_value["options"]:
                    raise ModelError("请选择题目中的一个选项，理由请单独填写")
                correct = selected_option == question_value["answer"]
                feedback = {
                    "verdict": "correct" if correct else "incorrect",
                    "explanation": question_value["rubric"],
                    "missing": [],
                    "next_step": "继续学习" if correct else "试着结合提示重新理解",
                    "sources": question_value["sources"],
                }
                if reasoning.strip() or attachment_id:
                    context.update(
                        question=question_value,
                        answer=selected_option,
                        selected_option=selected_option,
                        reasoning=reasoning,
                        review=action.action == "retry_grade",
                    )
                    result, usage = await provider.generate("grade", context, progress)
                    feedback = Feedback.model_validate(result).model_dump()
                    validate_sources(feedback, evidence)
                    # Option correctness is deterministic. A right guess with faulty reasoning
                    # is not recorded as independent mastery.
                    feedback["verdict"] = (
                        ("partial" if feedback["verdict"] == "incorrect" else feedback["verdict"])
                        if correct
                        else "incorrect"
                    )
                answer = selected_option + ("\n理由：" + reasoning if reasoning else "")
            elif question_value["kind"] == "number" and not attachment_id:
                match = re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*", answer)
                if match and match[2] != question_value["unit"] and re.search(r"[=+\\$*/^()]|\n", match[2]):
                    match = None
                if not match:
                    context.update(
                        question=question_value, answer=answer, review=action.action == "retry_grade"
                    )
                    result, usage = await provider.generate("grade", context, progress)
                    feedback = Feedback.model_validate(result).model_dump()
                    validate_sources(feedback, evidence)
                    if re.search(r"(?i)(i (?:do not|don't) know|不知道|不会|不清楚)", answer):
                        feedback.update(
                            verdict="uncertain",
                            explanation="还没有可核对的计算答案。",
                            next_step="可以查看提示，或跳过继续学习",
                        )
                else:
                    correct = (
                        math.isclose(
                            float(match[1]),
                            float(question_value["answer"]),
                            rel_tol=0,
                            abs_tol=question_value["tolerance"],
                        )
                        and match[2] == question_value["unit"]
                    )
                    feedback = {
                        "verdict": "correct" if correct else "incorrect",
                        "explanation": question_value["rubric"],
                        "missing": [],
                        "next_step": "继续学习" if correct else "检查运算与单位",
                        "sources": question_value["sources"],
                    }
            else:
                context.update(question=question_value, answer=answer, review=action.action == "retry_grade")
                result, usage = await provider.generate("grade", context, progress)
                feedback = Feedback.model_validate(result).model_dump()
                validate_sources(feedback, evidence)
            result = {"feedback": feedback}
        elif action.action in ("hint", "solution"):
            if not question:
                raise ModelError("当前没有题目")
            result = {
                "text": question_value["hint"]
                if action.action == "hint"
                else question_value["answer"] + "\n\n" + question_value["rubric"],
                "sources": question_value["sources"],
            }
        elif action.action in ("next", "skip"):
            result = {"text": "已保存当前位置。你可以继续下一题，或选择其他章节。", "sources": []}
        else:
            result, usage = await provider.generate("partner" if partner else "reply", context, progress)
            result = Reply.model_validate(result).model_dump()
            validate_sources(result, evidence)
        await progress("正在保存已验证的结果…")
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if not current or current["status"] != "running":
                return
            if lesson:
                if (
                    run["scope"].startswith("prepare:")
                    and db.execute("SELECT lesson FROM chapters WHERE id=?", (chapter["id"],)).fetchone()[0]
                ):
                    db.execute("UPDATE runs SET status='done',completed=? WHERE id=?", (now(), run_id))
                    return
                payload = {k: v for k, v in lesson.items() if k != "questions"}
                offset = db.execute(
                    "SELECT COUNT(*) FROM questions WHERE chapter_id=?", (chapter["id"],)
                ).fetchone()[0]
                version = db.execute(
                    "SELECT COALESCE(MAX(version),0)+1 FROM questions WHERE chapter_id=?", (chapter["id"],)
                ).fetchone()[0]
                for index, q in enumerate(lesson["questions"]):
                    db.execute(
                        "INSERT INTO questions(id,chapter_id,position,payload,version) VALUES(?,?,?,?,?)",
                        (uid(), chapter["id"], offset + index, dumps(q), version),
                    )
                db.execute(
                    "UPDATE chapters SET lesson=?,question_index=?,hint_used=0,revealed=0,state='已学习，待验证' WHERE id=?",
                    (dumps(payload), offset, chapter["id"]),
                )
                db.execute(
                    "UPDATE chapters SET preparation='ready',preparation_error=NULL WHERE id=?",
                    (chapter["id"],),
                )
                if run["scope"].startswith("prepare:"):
                    db.execute("UPDATE chapters SET state='未学习' WHERE id=?", (chapter["id"],))
            if feedback:
                if disputed_attempt:
                    # Preserve original verdict and store a separate reviewed attempt.
                    assisted = disputed_attempt["assisted"]
                    answer = disputed_attempt["answer"]
                    db.execute("UPDATE attempts SET reviewed=1 WHERE id=?", (disputed_attempt["id"],))
                else:
                    assisted = int(bool(chapter["hint_used"] or chapter["revealed"]))
                attempt_id = uid()
                db.execute(
                    "INSERT INTO attempts(id,chapter_id,question_id,answer,feedback,assisted,disputed,created) VALUES(?,?,?,?,?,?,?,?)",
                    (attempt_id, chapter["id"], question["id"], answer, dumps(feedback), assisted, 0, now()),
                )
                db.execute(
                    "UPDATE attempts SET selected_option=?,reasoning=? WHERE id=?",
                    (selected_option, reasoning, attempt_id),
                )
                db.execute("UPDATE attempts SET attachment_id=? WHERE id=?", (attachment_id, attempt_id))
                if disputed_attempt:
                    db.execute(
                        "UPDATE attempts SET review_of=? WHERE id=?", (disputed_attempt["id"], attempt_id)
                    )
                result["attempt_id"] = attempt_id
                recompute(db, chapter["id"])
            if action.action in ("hint", "solution", "ask_question"):
                db.execute(
                    "UPDATE chapters SET hint_used=1,revealed=? WHERE id=?",
                    (int(action.action == "solution" or chapter["revealed"]), chapter["id"]),
                )
            if action.action in ("next", "skip"):
                db.execute(
                    "UPDATE chapters SET question_index=question_index+1,hint_used=0,revealed=0 WHERE id=?",
                    (chapter["id"],),
                )
            text = (
                result.get("text")
                or (feedback and feedback["explanation"])
                or (lesson and lesson["explanation"])
                or ""
            )
            user_text = answer if feedback else action.text
            background = run["scope"].startswith("prepare:")
            if user_text and not background:
                db.execute(
                    "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
                    (uid(), run["space_id"], thread, "user", user_text, int(action.private), now()),
                )
            if not background:
                message_id = uid()
                db.execute(
                    "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
                    (message_id, run["space_id"], thread, "assistant", text, int(action.private), now()),
                )
                result["message_id"] = message_id
            db.execute(
                "UPDATE runs SET status='done',result=?,partial='',completed=?,elapsed=?,usage=? WHERE id=?",
                (dumps(result), now(), time.monotonic() - started, dumps(usage), run_id),
            )
        if background:
            return
        compact_history(store, thread)
        count = store.one(
            "SELECT COUNT(*) AS n FROM messages WHERE thread=? AND role='user' AND private=0", (thread,)
        )["n"]
        if count and count % 6 == 0:
            from .memory import consolidate

            app.state.launch("memory:" + thread, consolidate(store, provider, thread, run["space_id"]))
    except asyncio.CancelledError:
        store.write(
            "UPDATE runs SET status='cancelled',completed=? WHERE id=? AND status='running'", (now(), run_id)
        )
    except Exception as exc:
        error = (
            str(exc) if isinstance(exc, ModelError) else "生成结果校验或保存失败，请重试；原学习位置已保留"
        )
        store.write(
            "UPDATE runs SET status='failed',error=?,completed=?,elapsed=? WHERE id=? AND status='running'",
            (error, now(), time.monotonic() - started, run_id),
        )


def compact_history(store, thread):
    """Lossless archive + bounded extractive summary. No extra model call per message."""
    try:
        if store.one("SELECT 1 FROM summaries WHERE thread=?", (thread,)):
            return  # Keep the last validated summary; semantic consolidation advances its watermark.
        rows = store.all(
            "SELECT id,role,text FROM messages WHERE thread=? AND private=0 ORDER BY created", (thread,)
        )
        if len(rows) <= 18:
            return
        # This is explicitly an extractive timeline, not a claimed LLM semantic summary.
        older = rows[:-12][-16:]
        summary = "\n".join(f"[{r['id']}] {r['role']}: {r['text'][:180]}" for r in older)
        store.write(
            "INSERT INTO summaries(thread,text,watermark) VALUES(?,?,?) ON CONFLICT(thread) DO UPDATE SET text=excluded.text,watermark=excluded.watermark",
            (thread, summary, older[-1]["id"]),
        )
    except Exception:
        pass  # Maintenance must not turn an already committed answer into failure.
