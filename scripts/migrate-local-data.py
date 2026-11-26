"""Explicit copy into an empty destination; source is never removed or modified."""
import argparse
import shutil
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--destination", type=Path, required=True)
args = parser.parse_args()
source, destination = args.source.resolve(), args.destination.resolve()
database = source / "bookside.sqlite3"
if not database.is_file():
    database = source / "learnest.sqlite3"
if not database.is_file():
    raise SystemExit("Source database missing")
if destination.exists():
    raise SystemExit("Destination must not exist; no existing user data will be overwritten")
if source in destination.parents:
    raise SystemExit("Destination must be outside source")
destination.mkdir(parents=True)
with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as src:
    with sqlite3.connect(destination / "bookside.sqlite3") as dst:
        src.backup(dst)
for name in ("files", "model.local.json"):
    item = source / name
    if item.is_dir():
        shutil.copytree(item, destination / name)
    elif item.is_file():
        shutil.copy2(item, destination / name)
print("Copied database, uploads and local settings. Original data retained. Stop the source app before switching.")
