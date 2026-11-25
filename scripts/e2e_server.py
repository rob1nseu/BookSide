"""Isolated disposable server for browser tests, never touches user data."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from backend.app.main import create_app
from backend.app.model import Provider

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="learnest-e2e-") as temporary:
        root = Path(temporary)
        app = create_app(root, Provider(root, demo=True))
        uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
