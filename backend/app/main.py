import asyncio
import hashlib
import json
import os
import sqlite3
import base64
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .db import Store, dumps, now, uid
from .documents import build_chapters, ingest, validate_file
from .model import Provider
from .schemas import Action
from .tutoring import get_question, public_question, recompute, run_action
from .preparation import queue_chapter, prepare_space

load_dotenv()
ROOT = Path(__file__).resolve().parents[2]


class SpaceInput(BaseModel):
    name: str = Field(default="", max_length=120)
    document_ids: list[str] = Field(min_length=1, max_length=10)


class SpaceEdit(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None
    chapter_id: str | None = None
    mode: str | None = None
    review_chapters: list[str] | None = None


class SettingsInput(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    key: str | None = Field(default=None, max_length=500)


class MemoryInput(BaseModel):
    scope: str = "space"
    space_id: str | None = None
    text: str = Field(min_length=1, max_length=2000)
    source_id: str | None = None


def create_app(data_dir=None, provider=None):
    store = Store(Path(data_dir or os.getenv("LEARNEST_DATA_DIR", ROOT / "data")))
    model = provider or Provider(store.root, os.getenv("LEARNEST_DEMO") == "1")
    tasks = {}

    @asynccontextmanager
    async def lifespan(app):
        # Re-evaluate existing learning records using the current majority rule.
        with store.connect() as db:
            ids = db.execute("SELECT DISTINCT chapter_id FROM attempts").fetchall()
            for row in ids:
                recompute(db, row["chapter_id"])
        store.write(
            "UPDATE runs SET status='interrupted',error='服务重启中断了生成，请重试' WHERE status='running'"
        )
        store.write(
            "UPDATE documents SET status='failed',error='解析任务被中断，请重试' WHERE status IN ('uploaded','parsing','indexing')"
        )
        store.write("UPDATE jobs SET status='interrupted',error='服务重启，请重试' WHERE status='running'")
        store.write(
            "UPDATE chapters SET preparation='failed',preparation_error='服务重启，请点击本节继续准备' WHERE preparation IN ('queued','running')"
        )
        yield
        for task in list(tasks.values()):
            task.cancel()
        await asyncio.gather(*list(tasks.values()), return_exceptions=True)

    app = FastAPI(title="LearNest", lifespan=lifespan)
    app.state.store, app.state.provider = store, model
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc not in (
            "localhost:5173",
            "127.0.0.1:5173",
            "localhost:4173",
            "127.0.0.1:4173",
            "localhost:8765",
            "127.0.0.1:8765",
        ):
            return JSONResponse({"detail": "不允许的访问来源"}, status_code=403)
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.headers.get("x-learnest") != "1":
            return JSONResponse({"detail": "缺少本地应用请求标识"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def space_exists(space_id):
        row = store.one("SELECT * FROM spaces WHERE id=? AND owner='local'", (space_id,))
        if not row:
            raise HTTPException(404, "学习空间不存在")
        return row

    def document_exists(document_id):
        row = store.one("SELECT * FROM documents WHERE id=? AND owner='local'", (document_id,))
        if not row:
            raise HTTPException(404, "资料不存在")
        return row

    def launch(key, coroutine):
        if key in tasks:
            coroutine.close()
            return
        task = asyncio.create_task(coroutine)
        tasks[key] = task
        task.add_done_callback(lambda _: tasks.pop(key, None))

    app.state.launch = launch

    @app.get("/api/health")
    def health():
        return {"ok": True, "model": model.public()}

    @app.get("/api/settings")
    def settings():
        return {
            **model.public(),
            "memory_paused": bool(
                store.one("SELECT 1 FROM settings WHERE key='memory_paused' AND value='true'")
            ),
        }

    @app.put("/api/settings")
    def update_settings(value: SettingsInput):
        model.save(value.model, value.key)
        return settings()

    @app.post("/api/settings/check")
    async def check_model():
        from .model import ModelError

        async def noop(_):
            pass

        try:
            result, usage = await model.generate("partner", {"request": "请用一句话确认连接正常。"}, noop)
            return {
                "ok": True,
                "demo": model.demo,
                "model": model.public()["model"],
                "checked_at": now(),
                "usage": usage,
            }
        except ModelError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/api/documents")
    def documents():
        return store.all("SELECT * FROM documents WHERE owner='local' ORDER BY created DESC")

    @app.post("/api/documents", status_code=201)
    async def upload(file: UploadFile = File(...)):
        name = Path((file.filename or "").replace("\\", "/")).name[:200]
        kind = Path(name).suffix.lower().lstrip(".")
        if kind not in ("pdf", "pptx"):
            raise HTTPException(400, "仅支持 PDF 和 PPTX")
        content = await file.read(50 * 1024 * 1024 + 1)
        await file.close()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(413, "文件不能超过 50 MiB")
        try:
            validate_file(content, kind)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        digest = hashlib.sha256(content).hexdigest()
        existing = store.one("SELECT * FROM documents WHERE hash=?", (digest,))
        if existing:
            return existing
        document_id = uid()
        (store.root / "files" / f"{document_id}.{kind}").write_bytes(content)
        with store.connect() as db:
            db.execute(
                "INSERT INTO documents(id,name,hash,kind,created) VALUES(?,?,?,?,?)",
                (document_id, name, digest, kind, now()),
            )
            db.execute(
                "INSERT INTO jobs(id,document_id,status,created) VALUES(?,?,?,?)",
                (uid(), document_id, "running", now()),
            )
        launch("parse:" + document_id, asyncio.to_thread(ingest, store, document_id))
        return document_exists(document_id)

    @app.post("/api/documents/{document_id}/retry")
    async def retry_document(document_id: str):
        doc = document_exists(document_id)
        if doc["status"] != "failed":
            raise HTTPException(409, "只有失败任务可以重试")
        store.write("UPDATE documents SET status='uploaded',error=NULL WHERE id=?", (document_id,))
        store.write(
            "INSERT INTO jobs(id,document_id,status,created) VALUES(?,?,?,?)",
            (uid(), document_id, "running", now()),
        )
        launch("parse:" + document_id, asyncio.to_thread(ingest, store, document_id))
        return {"ok": True}

    @app.get("/api/documents/{document_id}/file")
    def document_file(document_id: str):
        doc = document_exists(document_id)
        return FileResponse(
            store.root / "files" / f"{document_id}.{doc['kind']}",
            media_type="application/pdf"
            if doc["kind"] == "pdf"
            else "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=doc["name"],
            content_disposition_type="inline",
        )

    @app.get("/api/documents/{document_id}/pages")
    def document_pages(document_id: str):
        document_exists(document_id)
        return store.all("SELECT * FROM pages WHERE document_id=? ORDER BY number", (document_id,))

    @app.get("/api/spaces")
    def spaces():
        return store.all(
            "SELECT s.*,(SELECT COUNT(*) FROM chapters c WHERE c.space_id=s.id) AS chapter_count FROM spaces s WHERE owner='local' ORDER BY created DESC"
        )

    @app.post("/api/spaces", status_code=201)
    def create_space(value: SpaceInput):
        docs = [document_exists(doc_id) for doc_id in dict.fromkeys(value.document_ids)]
        space_id = uid()
        with store.connect() as db:
            db.execute(
                "INSERT INTO spaces(id,name,created) VALUES(?,?,?)",
                (space_id, value.name.strip() or Path(docs[0]["name"]).stem, now()),
            )
            db.executemany("INSERT INTO space_documents VALUES(?,?)", [(space_id, doc["id"]) for doc in docs])
        for doc in docs:
            if doc["status"] in ("ready", "partial"):
                build_chapters(store, space_id, doc["id"])
        return space_exists(space_id)

    @app.get("/api/spaces/{space_id}")
    def detail(space_id: str, compact: bool = False):
        space = space_exists(space_id)
        chapters = store.all("SELECT * FROM chapters WHERE space_id=? ORDER BY position", (space_id,))
        for chapter in chapters:
            if compact and chapter["id"] != space["current_chapter"]:
                chapter.update(lesson=None, question=None, question_count=0, attempts=[])
                continue
            chapter["lesson"] = json.loads(chapter["lesson"]) if chapter["lesson"] else None
            chapter["question"] = public_question(get_question(store, chapter))
            plan = store.one(
                "SELECT COUNT(*) AS n,MIN(position) AS first FROM questions WHERE chapter_id=? AND version=(SELECT MAX(version) FROM questions WHERE chapter_id=?)",
                (chapter["id"], chapter["id"]),
            )
            chapter["question_count"] = plan["n"]
            chapter["question_index"] -= plan["first"] or 0
            chapter["attempts"] = store.all(
                "SELECT * FROM attempts WHERE chapter_id=? ORDER BY created", (chapter["id"],)
            )
            for attempt in chapter["attempts"]:
                attempt["feedback"] = json.loads(attempt["feedback"])
            from .pedagogy import concept_summary
            questions = [dict(json.loads(q["payload"]), id=q["id"]) for q in store.all(
                "SELECT id,payload FROM questions WHERE chapter_id=?", (chapter["id"],))]
            chapter["concepts"] = concept_summary([q for q in questions if q.get("concept")], list(reversed(chapter["attempts"])))
        docs = store.all(
            "SELECT d.* FROM documents d JOIN space_documents sd ON sd.document_id=d.id WHERE sd.space_id=?",
            (space_id,),
        )
        active = store.one("SELECT id FROM runs WHERE scope=? AND status='running'", (space_id,))
        return {
            **space,
            "chapters": chapters,
            "documents": docs,
            "active_run": active["id"] if active else None,
            "review_queue": json.loads(space["review_queue"]),
            "review_due": [c["id"] for c in chapters if c["state"] == "待复查"][:3],
            "legacy_outline": any(c["outline_version"] < 2 for c in chapters),
        }

    @app.get("/api/spaces/{space_id}/status")
    def space_status(space_id: str):
        space_exists(space_id)
        return {
            "chapters": store.all(
                "SELECT id,preparation,preparation_error,state FROM chapters WHERE space_id=? ORDER BY position",
                (space_id,),
            ),
            "documents": store.all(
                "SELECT d.id,d.status,d.error FROM documents d JOIN space_documents sd ON sd.document_id=d.id WHERE sd.space_id=?",
                (space_id,),
            ),
        }

    @app.get("/api/spaces/{space_id}/resources")
    def resources(space_id: str, document_id: str, topic: str | None = None):
        from .resources import recommend, TOPICS

        space_exists(space_id)
        doc = store.one(
            "SELECT d.* FROM documents d JOIN space_documents sd ON sd.document_id=d.id WHERE sd.space_id=? AND d.id=?",
            (space_id, document_id),
        )
        if not doc:
            raise HTTPException(404, "教材不属于当前空间")
        if topic and topic not in TOPICS:
            raise HTTPException(422, "暂不支持该方向")
        chapters = store.all(
            "SELECT title FROM chapters WHERE space_id=? AND document_id=? ORDER BY position LIMIT 200",
            (space_id, document_id),
        )
        pages = store.all(
            "SELECT substr(text,1,2000) AS text FROM pages WHERE document_id=? ORDER BY number LIMIT 6",
            (document_id,),
        )
        return {
            "document_id": document_id,
            "document_name": doc["name"],
            **recommend(
                doc["name"], " ".join(c["title"] for c in chapters), " ".join(p["text"] for p in pages), topic
            ),
        }

    @app.get("/api/spaces/{space_id}/review")
    def review_detail(space_id: str, chapter_id: str):
        from .review import detail as review_data
        from .model import ModelError

        space_exists(space_id)
        try:
            return review_data(store, space_id, chapter_id)
        except ModelError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.patch("/api/spaces/{space_id}")
    def edit_space(space_id: str, value: SpaceEdit):
        space = space_exists(space_id)
        if store.one("SELECT 1 FROM runs WHERE scope=? AND status='running'", (space_id,)):
            raise HTTPException(409, "请先取消当前生成，再切换学习位置")
        with store.connect() as db:
            if value.name is not None:
                db.execute("UPDATE spaces SET name=? WHERE id=?", (value.name, space_id))
            if value.archived is not None:
                db.execute("UPDATE spaces SET archived=? WHERE id=?", (int(value.archived), space_id))
            if value.chapter_id:
                if not db.execute(
                    "SELECT 1 FROM chapters WHERE id=? AND space_id=? AND is_group=0",
                    (value.chapter_id, space_id),
                ).fetchone():
                    raise HTTPException(404, "章节不属于当前空间")
                db.execute("UPDATE spaces SET current_chapter=? WHERE id=?", (value.chapter_id, space_id))
                if space["mode"] != "review":
                    db.execute(
                        "UPDATE chapters SET state='已学习，待验证' WHERE id=? AND lesson IS NOT NULL AND state='未学习'",
                        (value.chapter_id,),
                    )
            if value.mode == "review" and space["mode"] != "review":
                rows = db.execute(
                    "SELECT id FROM chapters WHERE space_id=? AND is_group=0 ORDER BY CASE state WHEN '需要巩固' THEN 0 WHEN '未学习' THEN 1 WHEN '已学习，待验证' THEN 2 ELSE 3 END,position",
                    (space_id,),
                ).fetchall()
                queue = [
                    r["id"] for r in rows if value.review_chapters is None or r["id"] in value.review_chapters
                ]
                if not queue:
                    raise HTTPException(400, "请先等待章节解析完成")
                db.execute(
                    "UPDATE spaces SET mode='review',return_chapter=current_chapter,current_chapter=?,review_queue=? WHERE id=?",
                    (space["current_chapter"] or queue[0], dumps(queue), space_id),
                )
            if value.mode == "learn" and space["mode"] == "review":
                db.execute(
                    "UPDATE spaces SET mode='learn',current_chapter=return_chapter,return_chapter=NULL WHERE id=?",
                    (space_id,),
                )
        return detail(space_id)

    @app.delete("/api/spaces/{space_id}")
    def delete_space(space_id: str):
        space_exists(space_id)
        if "prepare:" + space_id in tasks:
            tasks["prepare:" + space_id].cancel()
        for row in store.all("SELECT id FROM runs WHERE space_id=? AND status='running'", (space_id,)):
            if row["id"] in tasks:
                tasks[row["id"]].cancel()
        with store.connect() as db:
            db.execute(
                "DELETE FROM summaries WHERE thread=? OR thread IN (SELECT thread FROM messages WHERE space_id=?)",
                (space_id, space_id),
            )
            db.execute("DELETE FROM spaces WHERE id=?", (space_id,))
        return {"ok": True}

    @app.patch("/api/spaces/{space_id}/chapters/{chapter_id}")
    def edit_chapter(space_id: str, chapter_id: str, value: dict):
        space_exists(space_id)
        chapter = store.one("SELECT * FROM chapters WHERE id=? AND space_id=?", (chapter_id, space_id))
        if not chapter:
            raise HTTPException(404, "章节不存在")
        title = str(value.get("title", chapter["title"]))[:120].strip()
        if not title:
            raise HTTPException(400, "章节名称不能为空")
        store.write("UPDATE chapters SET title=? WHERE id=?", (title, chapter_id))
        return {"ok": True}

    @app.get("/api/messages")
    def messages(
        space_id: str | None = None,
        chapter_id: str | None = None,
        question_id: str | None = None,
        session_id: str | None = None,
        node_id: str | None = None,
    ):
        from .review import root_chapter
        from .model import ModelError

        if space_id:
            space_exists(space_id)
        if session_id:
            session = store.one(
                "SELECT * FROM review_sessions WHERE id=? AND space_id=?", (session_id, space_id)
            )
            if not session or question_id not in {
                f"{session_id}:{i}" for i in range(len(json.loads(session["questions"])))
            }:
                raise HTTPException(404, "复习题目不存在")
            thread = f"review-question:{question_id}"
        elif node_id:
            try:
                root = root_chapter(store, space_id, chapter_id)
            except ModelError as exc:
                raise HTTPException(404, str(exc)) from exc
            row = store.one(
                "SELECT * FROM review_maps WHERE space_id=? AND root_id=?", (space_id, root["id"])
            )
            if not row or node_id not in {n["id"] for n in json.loads(row["payload"])["nodes"]}:
                raise HTTPException(404, "知识点不存在")
            thread = f"node:{row['id']}:{node_id}"
        elif question_id:
            if not store.one(
                "SELECT 1 FROM questions q JOIN chapters c ON c.id=q.chapter_id WHERE q.id=? AND c.space_id=?",
                (question_id, space_id),
            ):
                raise HTTPException(404, "题目不存在")
            thread = f"question:{question_id}"
        elif chapter_id:
            if not store.one("SELECT 1 FROM chapters WHERE id=? AND space_id=?", (chapter_id, space_id)):
                raise HTTPException(404, "章节不存在")
            thread = f"lecture:{chapter_id}"
        else:
            if space_id:
                return store.all("SELECT * FROM messages WHERE space_id=? ORDER BY created", (space_id,))
            thread = "partner"
        return store.all("SELECT * FROM messages WHERE thread=? ORDER BY created", (thread,))

    @app.post("/api/spaces/{space_id}/actions", status_code=202)
    async def action(space_id: str, value: Action):
        space = space_exists(space_id)
        if value.action == "partner":
            raise HTTPException(400, "请使用独立陪聊入口")
        chapter_id = value.chapter_id or space["current_chapter"]
        chapter = store.one(
            "SELECT * FROM chapters WHERE id=? AND space_id=? AND is_group=0", (chapter_id, space_id)
        )
        if not chapter:
            raise HTTPException(404, "章节不属于当前学习空间")
        value.chapter_id = chapter_id
        existing = store.one(
            "SELECT id FROM runs WHERE scope=? AND request_key=?", (space_id, value.request_key)
        )
        if existing:
            return existing
        background = tasks.get("prepare:" + space_id)
        if background:
            background.cancel()
            await asyncio.gather(background, return_exceptions=True)
        result = begin_run(space_id, space_id, chapter_id, value)
        if value.prepare_chapter and value.action == "teach":
            queue_chapter(store, chapter)
        launch("prepare:" + space_id, prepare_space(app, space_id))
        return result

    @app.post("/api/spaces/{space_id}/preparation/stop")
    async def stop_preparation(space_id: str):
        space_exists(space_id)
        task = tasks.get("prepare:" + space_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        store.write(
            "UPDATE chapters SET preparation='idle' WHERE space_id=? AND preparation IN ('queued','running')",
            (space_id,),
        )
        return {"ok": True}

    @app.post("/api/spaces/{space_id}/preparation")
    async def prepare_chapter(space_id: str):
        space = space_exists(space_id)
        chapter = store.one(
            "SELECT * FROM chapters WHERE id=? AND space_id=?", (space["current_chapter"], space_id)
        )
        if not chapter:
            raise HTTPException(400, "请先选择章节")
        queue_chapter(store, chapter)
        if not chapter["lesson"]:
            store.write("UPDATE chapters SET preparation='queued' WHERE id=?", (chapter["id"],))
        launch("prepare:" + space_id, prepare_space(app, space_id))
        return {"ok": True}

    @app.post("/api/spaces/{space_id}/rebuild-outline", status_code=201)
    def rebuild_outline(space_id: str):
        old = space_exists(space_id)
        ids = [
            d["document_id"]
            for d in store.all("SELECT document_id FROM space_documents WHERE space_id=?", (space_id,))
        ]
        # New space preserves every previous answer/lesson and avoids attaching them to wrong sections.
        return create_space(SpaceInput(name=old["name"] + " · 新目录", document_ids=ids))

    @app.post("/api/spaces/{space_id}/answer-image")
    async def answer_image(
        space_id: str, file: UploadFile = File(...), target: str | None = None, recognize: bool = True
    ):
        from .model import ModelError
        from PIL import Image
        from io import BytesIO
        import warnings

        space_exists(space_id)
        if target:
            valid = store.one(
                "SELECT 1 FROM questions q JOIN chapters c ON c.id=q.chapter_id WHERE q.id=? AND c.space_id=?",
                (target, space_id),
            )
            if not valid and ":" in target:
                sid, position = target.rsplit(":", 1)
                session = store.one(
                    "SELECT * FROM review_sessions WHERE id=? AND space_id=?", (sid, space_id)
                )
                valid = (
                    session and position.isdigit() and int(position) < len(json.loads(session["questions"]))
                )
            if not valid:
                raise HTTPException(404, "图片必须关联当前空间内的题目")
        content = await file.read(5 * 1024 * 1024 + 1)
        await file.close()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(413, "图片不能超过 5 MiB")
        mime = (
            "image/png"
            if content.startswith(b"\x89PNG\r\n\x1a\n")
            else "image/jpeg"
            if content.startswith(b"\xff\xd8\xff")
            else None
        )
        if not mime:
            raise HTTPException(400, "请选择 PNG 或 JPEG 图片")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as image:
                    if image.width * image.height > 20_000_000 or max(image.size) > 8192:
                        raise ValueError()
                    image.verify()
        except Exception as exc:
            raise HTTPException(400, "图片损坏或尺寸过大，请缩小后重试") from exc

        attachment_id = None
        if target:
            attachment_id = uid()
            store.write(
                "INSERT INTO attachments(id,space_id,target,mime,content,created) VALUES(?,?,?,?,?,?)",
                (attachment_id, space_id, target, mime, content, now()),
            )
        if not recognize:
            if not target:
                raise HTTPException(400, "请选择题目")
            return {"id": attachment_id}

        async def noop(_):
            pass

        try:
            result, _ = await model.generate(
                "transcribe",
                {
                    "request": "抄录这张学生作答图片，不解题。",
                    "_image": "data:" + mime + ";base64," + base64.b64encode(content).decode(),
                },
                noop,
            )
            return {**result, "id": attachment_id}
        except ModelError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/api/spaces/{space_id}/attachments/{attachment_id}")
    def read_attachment(space_id: str, attachment_id: str):
        space_exists(space_id)
        row = store.one("SELECT * FROM attachments WHERE id=? AND space_id=?", (attachment_id, space_id))
        if not row:
            raise HTTPException(404, "图片不存在")
        return Response(row["content"], media_type=row["mime"])

    @app.post("/api/spaces/{space_id}/attachments/{attachment_id}/transcribe")
    async def transcribe_attachment(space_id: str, attachment_id: str):
        from .model import ModelError
        from .attachments import attachment_image

        space_exists(space_id)
        row = store.one("SELECT * FROM attachments WHERE id=? AND space_id=?", (attachment_id, space_id))
        if not row:
            raise HTTPException(404, "图片不存在")
        if row["transcription"]:
            return json.loads(row["transcription"])

        async def noop(_):
            pass

        try:
            result, _ = await model.generate(
                "transcribe",
                {
                    "request": "只转写学生作答，模糊处明确标注。",
                    "_image": attachment_image(store, attachment_id, space_id, row["target"]),
                },
                noop,
            )
            store.write("UPDATE attachments SET transcription=? WHERE id=?", (dumps(result), attachment_id))
            return result
        except ModelError as exc:
            raise HTTPException(502, str(exc)) from exc

    def begin_run(scope, space_id, chapter_id, value):
        existing = store.one(
            "SELECT id FROM runs WHERE scope=? AND request_key=?", (scope, value.request_key)
        )
        if existing:
            return existing
        run_id = uid()
        try:
            store.write(
                "INSERT INTO runs(id,scope,space_id,chapter_id,action,request_key,status,created) VALUES(?,?,?,?,?,?,?,?)",
                (run_id, scope, space_id, chapter_id, value.action, value.request_key, "running", now()),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "正在处理上一条请求，请等待或取消")
        if value.action.startswith("review_"):
            from .review import run_review

            launch(run_id, run_review(app, run_id, value))
        else:
            launch(run_id, run_action(app, run_id, value))
        return {"id": run_id}

    @app.post("/api/partner/actions", status_code=202)
    async def partner_action(value: Action):
        if value.action != "partner":
            raise HTTPException(400, "陪聊不能调用教学操作")
        return begin_run("partner", None, None, value)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        run = store.one("SELECT * FROM runs WHERE id=?", (run_id,))
        if not run:
            raise HTTPException(404, "任务不存在")
        run["result"] = json.loads(run["result"]) if run["result"] else None
        return run

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str):
        get_run(run_id)

        async def stream():
            previous = None
            while True:
                run = get_run(run_id)
                payload = dumps(run)
                if payload != previous:
                    yield f"data: {payload}\n\n"
                    previous = payload
                if run["status"] != "running":
                    break
                await asyncio.sleep(0.25)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/runs/{run_id}/stages")
    def run_stages(run_id: str):
        get_run(run_id)
        return store.all("SELECT stage,created FROM run_stages WHERE run_id=? ORDER BY id", (run_id,))

    @app.post("/api/runs/{run_id}/cancel")
    def cancel(run_id: str):
        get_run(run_id)
        store.write(
            "UPDATE runs SET status='cancelled',completed=? WHERE id=? AND status='running'", (now(), run_id)
        )
        if run_id in tasks:
            tasks[run_id].cancel()
        return get_run(run_id)

    @app.post("/api/attempts/{attempt_id}/dispute")
    def dispute(attempt_id: str):
        attempt = store.one("SELECT * FROM attempts WHERE id=?", (attempt_id,))
        if not attempt:
            raise HTTPException(404, "作答不存在")
        with store.connect() as db:
            db.execute("UPDATE attempts SET disputed=1 WHERE id=?", (attempt_id,))
            recompute(db, attempt["chapter_id"])
        return {"ok": True}

    @app.get("/api/memories")
    def memories(space_id: str | None = None, partner: bool = False):
        if space_id:
            space_exists(space_id)
        scope = "partner" if partner else "space"
        return store.all(
            "SELECT * FROM memories WHERE active=1 AND (scope='global' OR (scope=? AND (space_id=? OR ?='partner'))) ORDER BY updated DESC",
            (scope, space_id, scope),
        )

    @app.post("/api/memories", status_code=201)
    def add_memory(value: MemoryInput):
        if store.one("SELECT 1 FROM settings WHERE key='memory_paused' AND value='true'"):
            raise HTTPException(409, "长期记忆已暂停，请先在设置中恢复后保存")
        if value.scope not in ("space", "global", "partner"):
            raise HTTPException(400, "记忆范围无效")
        if value.scope == "space":
            space_exists(value.space_id)
        else:
            value.space_id = None
        if value.source_id:
            source = store.one("SELECT * FROM messages WHERE id=?", (value.source_id,))
            expected_thread = "partner" if value.scope == "partner" else value.space_id
            if (
                not source
                or source["private"]
                or source["role"] != "user"
                or (value.scope != "global" and source["thread"] != expected_thread)
            ):
                raise HTTPException(400, "来源不允许进入该范围的长期记忆")
        existing = store.one(
            "SELECT * FROM memories WHERE scope=? AND space_id IS ? AND text=? AND active=1",
            (value.scope, value.space_id, value.text),
        )
        if existing:
            return existing
        memory_id = uid()
        store.write(
            "INSERT INTO memories VALUES(?,?,?,?,?,1,?,?)",
            (memory_id, value.scope, value.space_id, value.text, value.source_id, now(), now()),
        )
        return store.one("SELECT * FROM memories WHERE id=?", (memory_id,))

    @app.patch("/api/memories/{memory_id}")
    def edit_memory(memory_id: str, value: MemoryInput):
        old = store.one("SELECT * FROM memories WHERE id=? AND active=1", (memory_id,))
        if not old:
            raise HTTPException(404, "记忆不存在")
        value.scope, value.space_id, value.source_id = old["scope"], old["space_id"], old["source_id"]
        delete_memory(memory_id)
        return add_memory(value)

    @app.delete("/api/memories/{memory_id}")
    def delete_memory(memory_id: str):
        with store.connect() as db:
            old = db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if not old:
                raise HTTPException(404, "记忆不存在")
            db.execute("UPDATE memories SET active=0,updated=? WHERE id=?", (now(), memory_id))
            if old["source_id"]:
                db.execute("UPDATE messages SET private=1 WHERE id=?", (old["source_id"],))
            db.execute("DELETE FROM summaries")
            db.execute(
                "INSERT INTO settings VALUES('memory_generation','1') ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1"
            )
        return {"ok": True}

    @app.put("/api/memory-settings")
    def memory_settings(value: dict):
        paused = bool(value.get("paused"))
        store.write(
            "INSERT INTO settings VALUES('memory_generation','1') ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1"
        )
        store.write(
            "INSERT INTO settings VALUES('memory_paused',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("true" if paused else "false",),
        )
        return {"paused": paused}

    @app.get("/api/diagnostics")
    def diagnostics():
        return {
            "runs": store.all(
                "SELECT id,action,status,error,elapsed,usage,created FROM runs ORDER BY created DESC LIMIT 50"
            ),
            "jobs": store.all("SELECT * FROM jobs ORDER BY created DESC LIMIT 50"),
            "database_bytes": store.path.stat().st_size,
        }

    @app.get("/api/spaces/{space_id}/export")
    def export_space(space_id: str):
        from .review import public_session

        value = detail(space_id)
        value["messages"] = messages(space_id)
        value["memories"] = memories(space_id)
        value["review_maps"] = [
            {**row, "payload": json.loads(row["payload"])}
            for row in store.all("SELECT * FROM review_maps WHERE space_id=?", (space_id,))
        ]
        value["review_sessions"] = [
            {"map_id": row["map_id"], **public_session(row)}
            for row in store.all(
                "SELECT * FROM review_sessions WHERE space_id=? ORDER BY created", (space_id,)
            )
        ]
        value["attachments"] = store.all(
            "SELECT id,target,mime,created FROM attachments WHERE space_id=?", (space_id,)
        )
        return JSONResponse(
            value, headers={"Content-Disposition": 'attachment; filename="learnest-export.json"'}
        )

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app
