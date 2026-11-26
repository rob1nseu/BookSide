"""Exercise the frozen binary with isolated demo data; never reads local model settings."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

exe = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix="learnest-frozen-") as directory:
    report = Path(directory) / "native.json"
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.run([str(exe), "--self-test", str(report)], check=True, timeout=45, creationflags=flags)
    checks = json.loads(report.read_text())
    # Refuse to mistake a pre-existing development service for the frozen application.
    try:
        urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=1)
    except OSError:
        pass
    else:
        raise SystemExit("Port 8765 occupied; close the existing app before frozen smoke test")
    env = dict(os.environ, LEARNEST_DATA_DIR=directory, LEARNEST_DEMO="1")
    process = subprocess.Popen([str(exe), "--server"], env=env, creationflags=flags)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=1) as response:
                    checks["http_health"] = bool(json.loads(response.read())["ok"])
                break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError("Frozen backend exited")
                time.sleep(.1)
        with urllib.request.urlopen("http://127.0.0.1:8765/", timeout=5) as response:
            checks["html"] = b"LearNest" in response.read()
        with urllib.request.urlopen("http://127.0.0.1:8765/seu-emblem.png", timeout=5) as response:
            checks["emblem"] = response.status == 200
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    print(json.dumps(checks))
    if not all(checks.values()):
        raise SystemExit(1)
