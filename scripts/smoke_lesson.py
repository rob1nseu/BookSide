"""Opt-in live chapter generation with synthetic material; prints no secrets or lesson text."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.model import Provider
from backend.app.runtime import bounded_action


@bounded_action
async def check():
    provider = Provider(Path("data"))
    progress = []

    async def update(text):
        progress.append(text)

    lesson, usage = await provider.generate("lesson", {
        "chapter": {"id": "synthetic-chapter", "title": "The derivative of a square"},
        "mode": "learn",
        "evidence": [{"id": "synthetic-page", "text": "The derivative is the instantaneous rate of change. For f(x)=x^2, f'(x)=2x. At x=3 the slope is 6. Check differentiability before using the derivative. The derivative can be defined as a limit of difference quotients."}],
        "request": "请给出精简中文讲解、一个含 LaTeX 分式的示例和两道练习。仅引用给定资料。",
    }, update)
    assert lesson["sources"] == ["synthetic-page"]
    assert all(set(q["sources"]) <= {"synthetic-page"} for q in lesson["questions"])
    assert provider.active_calls == 0
    print(json.dumps({"ok": True, "questions": len(lesson["questions"]), "usage": usage,
                      "format_retries": sum("修复" in p for p in progress)}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    if not parser.parse_args().live:
        raise SystemExit("Skipped: --live explicitly enables provider calls with synthetic material.")
    asyncio.run(check())
