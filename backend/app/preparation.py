"""Serial, resumable chapter preparation; foreground requests always take priority."""

import asyncio

from .db import now, uid
from .schemas import Action
from .tutoring import run_action


def queue_chapter(store, chapter):
    parent = chapter["parent_id"]
    if not parent:
        return  # A standalone chapter has no sibling preparation cost.
    store.write(
        "UPDATE chapters SET preparation='queued',preparation_error=NULL WHERE space_id=? AND parent_id=? AND is_group=0 AND lesson IS NULL AND id!=? AND preparation!='running'",
        (chapter["space_id"], parent, chapter["id"]),
    )


async def prepare_space(app, space_id):
    store = app.state.store
    current = None
    try:
        while store.one("SELECT 1 FROM spaces WHERE id=?", (space_id,)):
            if store.one("SELECT 1 FROM runs WHERE scope=? AND status='running'", (space_id,)):
                await asyncio.sleep(0.25)
                continue
            current = store.one(
                "SELECT * FROM chapters WHERE space_id=? AND preparation='queued' AND lesson IS NULL ORDER BY CASE WHEN id=(SELECT current_chapter FROM spaces WHERE id=?) THEN 0 ELSE 1 END,position LIMIT 1",
                (space_id, space_id),
            )
            if not current:
                return
            run_id = uid()
            store.write("UPDATE chapters SET preparation='running' WHERE id=?", (current["id"],))
            store.write(
                "INSERT INTO runs(id,scope,space_id,chapter_id,action,request_key,status,created) VALUES(?,?,?,?,?,?,?,?)",
                (run_id, "prepare:" + space_id, space_id, current["id"], "teach", uid(), "running", now()),
            )
            await run_action(app, run_id, Action(action="teach", chapter_id=current["id"], request_key=uid()))
            if asyncio.current_task().cancelling():
                return
            run = store.one("SELECT * FROM runs WHERE id=?", (run_id,))
            if run and run["status"] != "done":
                store.write(
                    "UPDATE chapters SET preparation='failed',preparation_error=? WHERE id=? AND lesson IS NULL",
                    (run["error"] or "准备已暂停，可点击本节重试", current["id"]),
                )
            current = None
    finally:
        if current:
            store.write(
                "UPDATE chapters SET preparation='queued' WHERE id=? AND lesson IS NULL", (current["id"],)
            )
