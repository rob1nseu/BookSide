"""Reproducible arithmetic grading probes. --live uses only synthetic material.

These machine-derived labels supplement, never replace, a human teaching-quality set.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.model import Provider, ModelError


def cases():
    for n in range(1, 11):
        for category, answer, expected in (
            ("correct", str(n * n), "correct"),
            ("incorrect", str(n * n + 1), "incorrect"),
            ("equivalent", f"{n * n * 2}/2", "correct"),
            ("unknown", "我不知道", "uncertain"),
        ):
            yield {
                "id": f"square-{n}-{category}",
                "split": "holdout" if n > 7 else "development",
                "category": category,
                "n": n,
                "answer": answer,
                "expected": expected,
            }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--output", default="docs/eval-arithmetic.json")
    args = parser.parse_args()
    if not args.live:
        print(json.dumps(list(cases()), ensure_ascii=True, indent=2))
        return
    provider = Provider(Path("data"))
    results = []

    async def progress(_):
        pass

    for case in list(cases())[: args.limit]:
        n = case["n"]
        start = time.monotonic()
        try:
            result, usage = await provider.generate(
                "grade",
                {
                    "action": "answer",
                    "answer": case["answer"],
                    "question": {
                        "kind": "short",
                        "prompt": f"计算 {n} 的平方。",
                        "answer": str(n * n),
                        "rubric": "等价表达式也正确；未作答为 uncertain。",
                        "sources": ["p1"],
                    },
                    "evidence": [{"id": "p1", "text": "一个数的平方是该数与自身相乘。"}],
                },
                progress,
            )
            results.append(
                {
                    **case,
                    "actual": result["verdict"],
                    "pass": result["verdict"] == case["expected"],
                    "seconds": round(time.monotonic() - start, 2),
                    "usage": usage,
                }
            )
        except ModelError:
            results.append({**case, "pass": False, "error": "provider_or_validation_error"})
        print(case["id"], results[-1]["pass"], flush=True)
    Path(args.output).write_text(
        json.dumps(
            {
                "scope": "synthetic arithmetic only; not human teaching evaluation",
                "passed": sum(r["pass"] for r in results),
                "total": len(results),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
