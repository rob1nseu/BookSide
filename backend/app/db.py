"""Small SQLite unit-of-work. Migrations and writes are always transactional."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        (root / "files").mkdir(exist_ok=True)
        self.path = root / "learnest.sqlite3"
        existed = self.path.exists()
        backed_up = False
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY)")
            for file in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
                version = int(file.stem.split("_")[0])
                if not db.execute("SELECT 1 FROM migrations WHERE version=?", (version,)).fetchone():
                    if existed and not backed_up:
                        import time
                        backup_dir = root / "backups"
                        backup_dir.mkdir(exist_ok=True)
                        with sqlite3.connect(backup_dir / f"before-migration-{time.time_ns()}.sqlite3") as backup:
                            db.backup(backup)
                        backed_up = True
                    db.executescript(
                        "BEGIN IMMEDIATE;\n"
                        + file.read_text(encoding="utf-8")
                        + f"\nINSERT INTO migrations VALUES({version});\nCOMMIT;"
                    )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def all(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def write(self, sql, args=()):
        with self.connect() as db:
            db.execute(sql, args)
