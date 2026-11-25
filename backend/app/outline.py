"""Deterministic, source-anchored outlines. Offsets address extracted page text."""

import re


def normalized(text):
    return re.sub(r"\s+", "", text).casefold()


def toc_line(line):
    return bool(re.search(r"(?:[.·…]\s*){3,}\d+\s*$", line))


def heading(line):
    line = line.strip()
    if len(line) > 100 or toc_line(line):
        return None
    if re.match(r"^(第[一二三四五六七八九十百零\d]+[章节]|Chapter\s+\d+)", line, re.I):
        return 1
    match = re.match(r"^(\d+(?:\.\d+)+)(?:\s+|(?=[\u4e00-\u9fff]))\S", line)
    if match:
        return len(match[1].split("."))
    return None


def make_outline(pages, bookmarks=()):
    candidates = []
    for level, title, number in bookmarks:
        if not 1 <= number <= len(pages) or level > 2:
            continue
        if normalized(title) in ("目录", "contents", "tableofcontents"):
            continue
        page = pages[number - 1]
        offset = 0
        for line in page["text"].splitlines(keepends=True):
            if normalized(line) == normalized(title):
                break
            offset += len(line)
        if offset >= len(page["text"]):
            offset = 0
        candidates.append(dict(title=title.strip(), level=level, page=number, offset=offset))
    # Read all body lines, not page headers. Repeated running titles are deduplicated.
    if not candidates or not any(c["level"] == 2 for c in candidates):
        has_bookmarks = bool(candidates)
        styled = [h for p in pages for h in p.get("headings", [])]
        sizes = {}
        for item in styled:
            key = normalized(item["title"])
            sizes[key] = max(sizes.get(key, 0), item["size"])
        for page in pages:
            offset = 0
            lines = page["text"].splitlines(keepends=True)
            toc_page = sum(toc_line(s) for s in lines) >= 2
            for line in lines:
                level = heading(line)
                if level and level <= 2 and not toc_page and not (has_bookmarks and level == 1):
                    matching = [
                        h for h in page.get("headings", []) if normalized(h["title"]) == normalized(line)
                    ]
                    if (
                        not matching
                        or max(h["size"] for h in matching) >= sizes.get(normalized(line), 0) - 0.5
                    ):
                        candidates.append(
                            dict(title=line.strip(), level=level, page=page["number"], offset=offset)
                        )
                offset += len(line)
    if not candidates:
        candidates = [
            dict(title=p["title"], level=1, page=p["number"], offset=0)
            for p in (pages if pages[0].get("slide") else pages[::8])
        ]
    seen, anchors = set(), []
    for item in candidates:
        key = normalized(item["title"])
        if key not in seen:
            seen.add(key)
            anchors.append(item)
    anchors.sort(key=lambda a: (a["page"], a["offset"], a["level"]))
    stack = []
    for i, item in enumerate(anchors):
        while stack and anchors[stack[-1]]["level"] >= item["level"]:
            stack.pop()
        item["parent"] = stack[-1] if stack else None
        stack.append(i)
        next_item = next((a for a in anchors[i + 1 :] if a["level"] <= item["level"]), None)
        item["end_page"] = next_item["page"] if next_item else pages[-1]["number"]
        item["end_offset"] = next_item["offset"] if next_item else len(pages[-1]["text"])
        if next_item and next_item["offset"] == 0 and next_item["page"] > item["page"]:
            item["end_page"] -= 1
            item["end_offset"] = len(pages[item["end_page"] - 1]["text"])
        item["is_group"] = int(i + 1 < len(anchors) and anchors[i + 1]["level"] > item["level"])
    return anchors


def section_pages(pages, chapter):
    result = []
    for page in pages:
        if (
            page["document_id"] != chapter["document_id"]
            or not chapter["start_page"] <= page["number"] <= chapter["end_page"]
        ):
            continue
        text = page["text"]
        start = chapter.get("start_offset", 0) if page["number"] == chapter["start_page"] else 0
        end = chapter.get("end_offset") if page["number"] == chapter["end_page"] else None
        result.append(dict(page, text=text[start:end]))
    return result
