"""Reproducible small-fixture measurements; no model calls or user data access."""

import json
import platform
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psutil
from backend.app.db import Store, now, uid
from backend.app.documents import ingest, retrieve
from scripts.make_samples import generate


def main():
    process = psutil.Process()
    output = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "fixture": "original 2-page PDF + 1-slide PPTX",
        "rss_before_mib": round(process.memory_info().rss / 2**20, 2),
        "models": "not called; model latency and teaching quality unmeasured",
        "production_processes": "1 Python API process; optional desktop adds 1 host; development Vite is separate",
    }
    with tempfile.TemporaryDirectory(prefix="bookside-measure-") as temp:
        root = Path(temp)
        generate(root / "samples")
        start = time.perf_counter()
        store = Store(root / "store")
        output["database_migration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        sid = uid()
        store.write("INSERT INTO spaces(id,name,created) VALUES(?,?,?)", (sid, "benchmark", now()))
        for name, kind in [("calculus.pdf", "pdf"), ("lecture.pptx", "pptx")]:
            did = uid()
            data = (root / "samples" / name).read_bytes()
            (store.root / "files" / f"{did}.{kind}").write_bytes(data)
            store.write(
                "INSERT INTO documents(id,name,hash,kind,created) VALUES(?,?,?,?,?)",
                (did, name, uid(), kind, now()),
            )
            store.write("INSERT INTO space_documents VALUES(?,?)", (sid, did))
            start = time.perf_counter()
            ingest(store, did)
            output[kind + "_parse_index_ms"] = round((time.perf_counter() - start) * 1000, 2)
        start = time.perf_counter()
        for _ in range(20):
            retrieve(store, sid, "函数 定义 条件")
        output["retrieval_mean_ms"] = round((time.perf_counter() - start) * 1000 / 20, 2)
        output["rss_after_mib"] = round(process.memory_info().rss / 2**20, 2)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
