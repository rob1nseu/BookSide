"""Explicit opt-in real provider smoke check; never prints credentials or response text."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from backend.app.db import now
from backend.app.model import Provider, ModelError
from backend.app.config import setting


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Explicitly allow one real provider request")
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("Skipped: pass --live to opt in to a real API request.")
    load_dotenv()
    provider = Provider(Path(setting("BOOKSIDE_DATA_DIR", "data")), demo=False)

    async def progress(_):
        pass

    try:
        _, usage = await provider.generate("partner", {"request": "请简短确认连接。"}, progress)
    except ModelError as exc:
        raise SystemExit(str(exc)) from None
    print(
        json.dumps(
            {"ok": True, "model": provider.public()["model"], "checked_at": now(), "usage": usage},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
