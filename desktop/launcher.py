"""Source checkout entry point. Web and companion share the same local data."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    data = Path(os.environ.get("LEARNEST_DATA_DIR", ROOT / "data")).resolve()
    data.mkdir(parents=True, exist_ok=True)
    os.environ["LEARNEST_DATA_DIR"] = str(data)
    if "--server" in sys.argv:
        import uvicorn
        from backend.app.main import create_app

        uvicorn.run(create_app(), host="127.0.0.1", port=8765)
    else:
        from desktop.companion import main as companion

        companion()


if __name__ == "__main__":
    main()
