"""Check Git blobs without ever printing matched credentials. Works before commit/push."""

import re
import subprocess
import sys
from pathlib import PurePosixPath

PATTERN = re.compile(rb"(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")


def git(*args):
    return subprocess.check_output(["git", *args])


def check(staged=False, history=False):
    failures = []
    paths = (
        git("ls-files", "-z", *([] if staged else ["--cached", "--others", "--exclude-standard"]))
        .decode("utf-8")
        .split("\0")
    )
    for path in filter(None, paths):
        name = PurePosixPath(path).name
        forbidden = (
            path.startswith("data/")
            or name in ("model.local.json", "model.local.tmp")
            or name.startswith(".env")
        )
        try:
            content = git("show", ":" + path) if staged else open(path, "rb").read()
        except (OSError, subprocess.CalledProcessError):
            continue
        if forbidden or PATTERN.search(content):
            failures.append(path)
    if history:
        for oid in set(git("rev-list", "--objects", "--all").decode("utf-8").splitlines()):
            oid = oid.split(" ", 1)[0]
            if git("cat-file", "-t", oid).strip() == b"blob" and PATTERN.search(git("cat-file", "blob", oid)):
                failures.append("history blob " + oid[:12])
    if failures:
        print("Secret check BLOCKED. Review these paths/objects (values redacted):")
        for path in failures:
            print(path)
        return 1
    print("Secret check passed: no matching credentials or private config paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(check("--staged" in sys.argv, "--history" in sys.argv))
