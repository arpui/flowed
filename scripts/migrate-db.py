#!/usr/bin/env python3
"""
Flowed DB Migration Tool
Brings the 6 learning databases up to the current schema version, in place.

Usage:
    python3 scripts/migrate-db.py --dir ~/.flowed/alex-en          # migrate
    python3 scripts/migrate-db.py --dir ~/.flowed/alex-en --check   # report only

Behaviour:
  - Documents without `_schema_version` are treated as version 1 (baseline).
  - A pre-migration backup of every present DB is written to
    <data-dir>/.backups/pre-migration-<timestamp>/ before anything is written.
  - Writes are atomic (tmp + os.replace), same as update-db.py.
  - Documents stamped with a version newer than this tool understands abort
    the run without touching disk.

Exit codes: 0=up to date / migrated OK, 1=check found drift, 2=error.
"""
import argparse
import json
import os
import sys
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from db_lock import data_lock  # noqa: E402
from db_schema import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
    DB_FILENAMES,
    get_schema_version,
    migrate_docs,
    stamp_docs,
)


def resolve_data_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("FLOWED_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    cwd_data = (Path.cwd() / "data").resolve()
    if cwd_data.is_dir():
        return cwd_data
    print("[Flowed] ❌ Could not resolve a data dir — pass --dir <path>", file=sys.stderr)
    sys.exit(2)


def load_present_docs(data_dir: Path) -> dict:
    """Load every existing DB; abort on unreadable/corrupt files."""
    docs = {}
    for name in DB_FILENAMES:
        path = data_dir / name
        if not path.exists():
            print(f"[Flowed] ⚠️  Missing (skipped): {path}", file=sys.stderr)
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                docs[name] = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[Flowed] ❌ Cannot read {path}: {e}", file=sys.stderr)
            sys.exit(2)
    return docs


def save_doc(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(path))


def report_versions(docs: dict) -> bool:
    """Print one line per document; return True when all are at target AND stamped
    (i.e. a plain run would be a no-op)."""
    up_to_date = True
    for name in DB_FILENAMES:
        if name not in docs:
            continue
        d = docs[name]
        v = get_schema_version(d)
        stamped = d.get("_schema_version") is not None
        ok = v == CURRENT_SCHEMA_VERSION and stamped
        marker = "✅" if ok else "⚠️ "
        extra = "" if stamped else "  [not stamped yet]"
        print(f"[Flowed] {marker} {name}: schema v{v} (target v{CURRENT_SCHEMA_VERSION}){extra}")
        up_to_date = up_to_date and ok
    return up_to_date


def main():
    parser = argparse.ArgumentParser(description="Migrate Flowed databases to the current schema version")
    parser.add_argument("--dir", help="Data directory to migrate (default: $FLOWED_DATA_DIR or ./data)")
    parser.add_argument("--check", action="store_true",
                        help="Report versions and exit (1 if a plain run would write anything)")
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.dir)
    if not data_dir.is_dir():
        print(f"[Flowed] ❌ Data dir does not exist: {data_dir}", file=sys.stderr)
        sys.exit(2)

    print(f"[Flowed] 🗄️  Data dir: {data_dir} (target schema v{CURRENT_SCHEMA_VERSION})")

    stack = ExitStack()
    if not args.check:
        try:
            stack.enter_context(data_lock(data_dir))
        except TimeoutError as e:
            print(f"[Flowed] ❌ Database lock timeout: {e}", file=sys.stderr)
            sys.exit(2)

    try:
        docs = load_present_docs(data_dir)
        if not docs:
            print("[Flowed] ❌ No databases found — wrong data dir?", file=sys.stderr)
            sys.exit(2)

        if args.check:
            up_to_date = report_versions(docs)
            if up_to_date:
                print("[Flowed] ✅ All databases are up to date")
                sys.exit(0)
            print("[Flowed] ⚠️  Some databases need migration — run without --check", file=sys.stderr)
            sys.exit(1)

        pre_stamp = {name: doc.get("_schema_version") for name, doc in docs.items()}
        try:
            start, end = migrate_docs(docs)
        except ValueError as e:
            print(f"[Flowed] ❌ {e}", file=sys.stderr)
            sys.exit(2)
        except LookupError as e:
            print(f"[Flowed] ❌ {e}", file=sys.stderr)
            sys.exit(2)

        if pre_stamp == {name: end for name in docs}:
            report_versions(docs)
            print("[Flowed] ✅ Nothing to do")
            sys.exit(0)

        stamp_docs(docs)

        backup_dir = data_dir / ".backups" / f"pre-migration-{datetime.now():%Y%m%d-%H%M%S}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for name in docs:
            src = data_dir / name
            try:
                (backup_dir / name).write_bytes(src.read_bytes())
            except OSError as e:
                print(f"[Flowed] ❌ Backup failed for {src}: {e} — aborting, disk untouched", file=sys.stderr)
                sys.exit(2)
        print(f"[Flowed] 🗂️  Backup written to {backup_dir}")

        try:
            for name, doc in docs.items():
                save_doc(data_dir / name, doc)
        except OSError as e:
            print(f"[Flowed] ❌ Write failed: {e}", file=sys.stderr)
            sys.exit(2)

        report_versions(docs)
        print(f"[Flowed] ✅ Migrated {len(docs)} databases (v{start} → v{end})")
        sys.exit(0)
    finally:
        stack.close()


if __name__ == "__main__":
    main()
