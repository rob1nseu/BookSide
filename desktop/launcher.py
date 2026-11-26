"""Frozen Windows entry point: local web service plus optional desktop companion."""

import os
import sys
from pathlib import Path


def main():
    if "--self-test" in sys.argv:
        import json
        import tempfile
        from backend.app.main import create_app
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QPixmap

        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        qt = QApplication([])
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(directory)
            checks = {
                "database": bool(app.state.store.one("SELECT name FROM sqlite_master WHERE name='chapters'")),
                "frontend": (root / "frontend/dist/index.html").exists(),
                "sprite": not QPixmap(str(root / "desktop/assets/companion.png")).isNull(),
            }
        report = Path(sys.argv[sys.argv.index("--self-test") + 1])
        report.write_text(json.dumps(checks), encoding="utf-8")
        qt.quit()
        raise SystemExit(0 if all(checks.values()) else 1)
    data = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "LearNest"
    data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("LEARNEST_DATA_DIR", str(data))
    if "--server" in sys.argv:
        import uvicorn
        from backend.app.main import create_app

        uvicorn.run(create_app(), host="127.0.0.1", port=8765, log_config=None)
    else:
        from desktop.companion import main as companion

        companion()


if __name__ == "__main__":
    main()
