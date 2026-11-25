import base64
from .model import ModelError


def attachment_image(store, attachment_id, space_id, target):
    row = store.one(
        "SELECT * FROM attachments WHERE id=? AND space_id=? AND target=?", (attachment_id, space_id, target)
    )
    if not row:
        raise ModelError("图片不属于当前题目，请重新上传")
    return "data:" + row["mime"] + ";base64," + base64.b64encode(row["content"]).decode()
