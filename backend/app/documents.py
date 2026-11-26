"""Immutable PDF/PPTX ingestion. Parser failures never masquerade as indexed content."""

import re
import json
import zipfile
from pathlib import Path

import pymupdf
from pptx import Presentation

from .db import uid, dumps
from .outline import make_outline, section_pages, heading


def validate_file(content: bytes, kind: str):
    if kind == "pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("文件内容不是有效 PDF")
    if kind == "pptx" and not content.startswith(b"PK"):
        raise ValueError("文件内容不是有效 PPTX")


def parse_file(path: Path, kind: str):
    result = []
    if kind == "pdf":
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ValueError("暂不支持加密 PDF，请先解密")
            if len(doc) > 1000:
                raise ValueError("文件超过 1000 页上限")
            bookmarks = doc.get_toc()
            toc = {entry[2]: entry[1] for entry in bookmarks if entry[0] == 1}
            for index, page in enumerate(doc):
                text = page.get_text(sort=True).strip()
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                warning = "扫描页或空白页：未提取到可靠文本" if len(text) < 15 else ""
                if page.get_images() and not warning:
                    warning = "含图片：图像和图片中的公式未解析，请核对原页"
                result.append(
                    dict(
                        number=index + 1,
                        title=toc.get(index + 1, lines[0][:100] if lines else f"第 {index + 1} 页"),
                        text=text,
                        notes="",
                        warning=warning,
                        chapter=index + 1 in toc,
                    )
                )
                result[-1]["headings"] = [
                    {"title": title, "size": max(s["size"] for s in line["spans"])}
                    for block in page.get_text("dict")["blocks"]
                    if "lines" in block
                    for line in block["lines"]
                    if (title := "".join(s["text"] for s in line["spans"]).strip()) and heading(title)
                ]
    else:
        with zipfile.ZipFile(path) as archive:
            if sum(info.file_size for info in archive.infolist()) > 250 * 1024 * 1024:
                raise ValueError("PPTX 解压后体积过大")
            if "ppt/presentation.xml" not in archive.namelist():
                raise ValueError("不是有效 PPTX 演示文稿")
        doc = Presentation(path)
        if len(doc.slides) > 1000:
            raise ValueError("文件超过 1000 张幻灯片上限")
        for index, slide in enumerate(doc.slides):
            blocks = []
            image_count = 0
            for shape in sorted(slide.shapes, key=lambda s: (s.top, s.left)):
                if shape.has_text_frame:
                    blocks.append(shape.text)
                if shape.has_table:
                    blocks.extend(" | ".join(cell.text for cell in row.cells) for row in shape.table.rows)
                if shape.shape_type == 13:
                    image_count += 1
            text = "\n".join(blocks).strip()
            notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
            title = slide.shapes.title.text if slide.shapes.title else f"幻灯片 {index + 1}"
            warning = "含图片或图表：请在原始幻灯片中核对" if image_count else ""
            if not text:
                warning = "未提取到正文；该页不能作为可靠教学依据"
            result.append(
                dict(
                    number=index + 1,
                    title=title[:100],
                    text=text,
                    notes=notes,
                    warning=warning,
                    chapter=True,
                    slide=True,
                )
            )
    if not result:
        raise ValueError("文件没有页面")
    result[0]["outline"] = make_outline(result, bookmarks if kind == "pdf" else ())
    return result


def ingest(store, document_id):
    doc = store.one("SELECT * FROM documents WHERE id=?", (document_id,))
    try:
        store.write("UPDATE documents SET status='parsing',error=NULL WHERE id=?", (document_id,))
        pages = parse_file(store.root / "files" / f"{doc['id']}.{doc['kind']}", doc["kind"])
        store.write("UPDATE documents SET status='indexing' WHERE id=?", (document_id,))
        with store.connect() as db:
            db.execute("DELETE FROM pages WHERE document_id=?", (document_id,))
            for page in pages:
                db.execute(
                    "INSERT INTO pages VALUES(?,?,?,?,?,?,?)",
                    (
                        uid(),
                        document_id,
                        page["number"],
                        page["title"],
                        page["text"],
                        page["notes"],
                        page["warning"],
                    ),
                )
            status = "partial" if any(p["warning"] for p in pages) else "ready"
            if not any(len(p["text"]) >= 15 for p in pages):
                raise ValueError("没有可用于教学的文本；请上传文本型 PDF 或 PPTX")
            db.execute(
                "UPDATE documents SET status=?,outline=? WHERE id=?",
                (status, dumps(pages[0]["outline"]), document_id),
            )
            db.execute(
                "UPDATE jobs SET status='done' WHERE document_id=? AND status='running'", (document_id,)
            )
        for item in store.all("SELECT space_id FROM space_documents WHERE document_id=?", (document_id,)):
            build_chapters(store, item["space_id"], document_id, pages)
    except Exception as exc:
        error = str(exc) if isinstance(exc, ValueError) else "解析失败，请检查文件是否损坏后重试"
        store.write("UPDATE documents SET status='failed',error=? WHERE id=?", (error, document_id))
        store.write(
            "UPDATE jobs SET status='failed',error=? WHERE document_id=? AND status='running'",
            (error, document_id),
        )


def build_chapters(store, space_id, document_id, parsed=None):
    pages = parsed or store.all("SELECT * FROM pages WHERE document_id=? ORDER BY number", (document_id,))
    if not pages:
        return
    doc = store.one("SELECT * FROM documents WHERE id=?", (document_id,))
    if not doc.get("outline"):
        parsed_pages = parsed or parse_file(
            store.root / "files" / f"{document_id}.{doc['kind']}", doc["kind"]
        )
        outline = parsed_pages[0]["outline"]
        store.write("UPDATE documents SET outline=? WHERE id=?", (dumps(outline), document_id))
    else:
        outline = json.loads(doc["outline"])
    with store.connect() as db:
        if db.execute(
            "SELECT 1 FROM chapters WHERE space_id=? AND document_id=?", (space_id, document_id)
        ).fetchone():
            return
        offset = db.execute("SELECT COUNT(*) FROM chapters WHERE space_id=?", (space_id,)).fetchone()[0]
        ids = [uid() for _ in outline]
        for index, item in enumerate(outline):
            chapter_id = ids[index]
            db.execute(
                "INSERT INTO chapters(id,space_id,document_id,title,start_page,end_page,position,parent_id,level,is_group,start_offset,end_offset,outline_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,2)",
                (
                    chapter_id,
                    space_id,
                    document_id,
                    item["title"],
                    item["page"],
                    item["end_page"],
                    offset + index,
                    ids[item["parent"]] if item["parent"] is not None else None,
                    item["level"],
                    item["is_group"],
                    item["offset"],
                    item["end_offset"],
                ),
            )
            if not item["is_group"]:
                db.execute(
                    "UPDATE spaces SET current_chapter=COALESCE(current_chapter,?) WHERE id=?",
                    (chapter_id, space_id),
                )


def retrieve(store, space_id, query, chapter=None, limit=6):
    pages = store.all(
        "SELECT p.*,d.name,d.kind FROM pages p JOIN space_documents s ON s.document_id=p.document_id JOIN documents d ON d.id=p.document_id WHERE s.space_id=?",
        (space_id,),
    )
    if chapter:
        pages = section_pages(pages, chapter)
    terms = re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", query.lower())
    terms += [
        term[i : i + 2]
        for term in terms.copy()
        if re.search("[\u4e00-\u9fff]", term)
        for i in range(len(term) - 1)
    ]

    def score(p):
        text = (p["title"] + p["text"] + p["notes"]).lower()
        local = (
            chapter
            and p["document_id"] == chapter["document_id"]
            and chapter["start_page"] <= p["number"] <= chapter["end_page"]
        )
        return sum(min(text.count(term), 5) for term in set(terms)) + (20 if local else 0)

    ranked = sorted((p for p in pages if len(p["text"]) >= 15), key=score, reverse=True)[:limit]
    result = []
    for p in ranked:
        # Rank overlapping passages, retaining page identity for existing citation links.
        text = p["text"]
        passages = [text[i:i + 1500] for i in range(0, len(text), 1200)]
        ordered = sorted(range(len(passages)), key=lambda i: -sum(
            min(passages[i].lower().count(t), 5) for t in set(terms)))[:3]
        excerpt = "\n?\n".join(passages[i] for i in sorted(ordered))
        result.append(dict(p, text=excerpt, notes=p["notes"][:1500]))
    return result
