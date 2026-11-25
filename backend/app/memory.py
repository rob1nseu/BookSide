"""Background semantic consolidation with deletion-generation checks and source guards."""

from .db import dumps, now, uid
from .schemas import MemoryBatch


def generation(store):
    row = store.one("SELECT value FROM settings WHERE key='memory_generation'")
    return row["value"] if row else "0"


def paused(store):
    return bool(store.one("SELECT 1 FROM settings WHERE key='memory_paused' AND value='true'"))


async def consolidate(store, provider, thread, space_id):
    if paused(store):
        return
    epoch = generation(store)
    scope = "partner" if thread == "partner" else "space"
    rows = store.all(
        "SELECT id,role,text FROM messages WHERE thread=? AND private=0 ORDER BY created DESC LIMIT 30",
        (thread,),
    )
    rows.reverse()
    if not rows:
        return
    existing = store.all(
        "SELECT id,text FROM memories WHERE active=1 AND scope=? AND space_id IS ?", (scope, space_id)
    )
    context = {"task": "memory", "scope": scope, "messages": rows, "existing": existing}

    async def progress(_):
        pass

    try:
        result, usage = await provider.generate("memory", context, progress)
        batch = MemoryBatch.model_validate(result)
        allowed = {r["id"] for r in rows}
        user_ids = {r["id"] for r in rows if r["role"] == "user"}
        existing_ids = {r["id"] for r in existing}
        if not batch.source_ids or not set(batch.source_ids).issubset(allowed):
            return
        if any(
            item.source_id not in user_ids or (item.replaces_id and item.replaces_id not in existing_ids)
            for item in batch.items
        ):
            return
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT value FROM settings WHERE key='memory_generation'").fetchone()
            if (current["value"] if current else "0") != epoch:
                return
            if db.execute("SELECT 1 FROM settings WHERE key='memory_paused' AND value='true'").fetchone():
                return
            if space_id and not db.execute("SELECT 1 FROM spaces WHERE id=?", (space_id,)).fetchone():
                return
            # Recheck sources after the model call, before committing derived information.
            for source_id in batch.source_ids:
                if not db.execute(
                    "SELECT 1 FROM messages WHERE id=? AND thread=? AND private=0", (source_id, thread)
                ).fetchone():
                    return
            for item in batch.items:
                if db.execute(
                    "SELECT 1 FROM memories WHERE scope=? AND space_id IS ? AND text=?",
                    (scope, space_id, item.text),
                ).fetchone():
                    continue  # Includes tombstones; never resurrect deleted text automatically.
                if item.replaces_id:
                    db.execute("UPDATE memories SET active=0,updated=? WHERE id=?", (now(), item.replaces_id))
                db.execute(
                    "INSERT INTO memories VALUES(?,?,?,?,?,1,?,?)",
                    (uid(), scope, space_id, item.text, item.source_id, now(), now()),
                )
            db.execute(
                "INSERT INTO summaries(thread,text,watermark,generation) VALUES(?,?,?,?) ON CONFLICT(thread) DO UPDATE SET text=excluded.text,watermark=excluded.watermark,generation=excluded.generation",
                (thread, batch.summary, rows[-1]["id"], int(epoch)),
            )
            db.execute(
                "INSERT INTO settings(key,value) VALUES('last_memory_usage',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (dumps(usage),),
            )
    except Exception:
        # The complete conversation is retained. Do not invalidate a successful teaching turn.
        return
