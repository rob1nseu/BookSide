"""Generate repeatable original PDF/PPTX fixtures; no third-party textbooks."""

import argparse
from pathlib import Path
import pymupdf
from pptx import Presentation


def generate(root):
    root.mkdir(parents=True, exist_ok=True)
    pdf = pymupdf.open()
    chapters = [
        (
            "第一章 函数与极限",
            "函数描述输入与输出之间的对应关系。每一个输入只能对应一个输出。\n理解一个概念时，需要同时关注定义、适用条件和例子。\n极限描述自变量不断接近某个值时，函数值趋近的目标。\n例如，当 x 趋近于 2 时，x 的平方趋近于 4。",
        ),
        (
            "第二章 导数与变化率",
            "导数刻画函数在某个位置附近的变化速度。\n平均变化率是函数值的变化量与自变量变化量的比值。\n当区间不断缩小时，平均变化率的极限就是导数。\n函数 f(x)=x 的平方的导数为 2x。",
        ),
    ]
    for title, text in chapters:
        page = pdf.new_page()
        page.insert_text((55, 70), title, fontname="china-s", fontsize=21)
        page.insert_textbox((55, 110, 540, 680), text, fontname="china-s", fontsize=15, lineheight=1.8)
    pdf.set_toc([[1, title, i + 1] for i, (title, _) in enumerate(chapters)])
    pdf.save(root / "calculus.pdf")
    ppt = Presentation()
    slide = ppt.slides.add_slide(ppt.slide_layouts[1])
    slide.shapes.title.text = "第一章 函数与极限"
    slide.placeholders[1].text = "函数将每个输入映射到唯一输出。\n关注定义与适用条件，而不只是背诵术语。"
    slide.notes_slide.notes_text_frame.text = "讲解时先给出函数的生活例子，再强调唯一性。"
    ppt.save(root / "lecture.pptx")
    blank = pymupdf.open()
    blank.new_page()
    blank.save(root / "blank.pdf")
    (root / "broken.pdf").write_bytes(b"%PDF-corrupted")
    hierarchy = pymupdf.open()
    titles = ["1.1 Sets", "1.2 Functions", "1.3 Inverse", "1.4 Elementary"]
    for i, title in enumerate(titles):
        page = hierarchy.new_page()
        if i == 0:
            page.insert_text((55, 45), "Chapter 1 Functions", fontsize=20)
        page.insert_text((55, 100), title, fontsize=18)
        page.insert_text(
            (55, 150),
            "A function maps each input to exactly one output.\nA one-to-one function has an inverse.",
            fontsize=13,
        )
    hierarchy.set_toc([[1, "Chapter 1 Functions", 1]] + [[2, title, i + 1] for i, title in enumerate(titles)])
    hierarchy.save(root / "hierarchy.pdf")
    answer = pymupdf.open()
    page = answer.new_page(width=400, height=200)
    page.insert_text((40, 70), "2x + 3 = 7", fontsize=24)
    page.insert_text((40, 120), "x = 2", fontsize=24)
    page.get_pixmap().save(root / "answer.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/samples")
    args = parser.parse_args()
    generate(Path(args.output))
    print("Generated original sample files in", args.output)
