#!/usr/bin/env python3
"""Copy a learner's session transcript to the new path. Never deletes anything.

    ~/.fluent/<id>/.opencode/opencode/opencode.db   (legacy, stays put)
        ->  ~/.fluent/<id>/sessions/sessions.db     (what the app uses now)

Why a script and not `cp`: the DB runs in WAL mode. Copying the file while
anything holds it open can leave the copy missing everything still in the -wal
sidecar, and the corruption only shows up later as "missing sessions". SQLite's
own backup API takes a consistent snapshot instead, live writer or not.

The legacy file is left exactly as it is, so the previous build of the app keeps
working on it. The two stop being the same data the moment either side writes
again — copy when the instance is stopped, or accept that the old file freezes.

Usage:
    python3 scripts/migrate-sessions-db.py --all [--dry-run]
    python3 scripts/migrate-sessions-db.py --profile test-en
    python3 scripts/migrate-sessions-db.py --dir /home/albert/.fluent/test-en
    python3 scripts/migrate-sessions-db.py --all --force   # overwrite an existing copy

Exit codes: 0 ok (or nothing to do), 1 error.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

LEGACY_REL = Path(".opencode") / "opencode" / "opencode.db"
CURRENT_REL = Path("sessions") / "sessions.db"
TABLES = ("session", "message", "part")


def counts(db_path: Path) -> dict:
    """Row counts per table, so the copy can be checked against the original."""
    out = {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for table in TABLES:
            try:
                out[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                out[table] = None
    finally:
        conn.close()
    return out


def migrate(profile_dir: Path, dry_run=False, force=False) -> bool:
    legacy = profile_dir / LEGACY_REL
    current = profile_dir / CURRENT_REL
    name = profile_dir.name

    if not legacy.exists():
        if current.exists():
            print(f"[{name}] ja és al lloc nou ({current.name}) — res a fer")
        else:
            print(f"[{name}] cap BD de sessions — res a fer")
        return True

    if current.exists() and not force:
        print(f"[{name}] ⚠ ja existeix {current} — no la trepitjo (--force per sobreescriure)")
        return True

    before = counts(legacy)
    print(f"[{name}] {legacy}")
    print(f"[{name}]   sessions={before.get('session')} missatges={before.get('message')} "
          f"parts={before.get('part')}")
    if dry_run:
        print(f"[{name}]   → (dry-run) copiaria a {current}")
        return True

    current.parent.mkdir(parents=True, exist_ok=True)
    tmp = current.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()

    src = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)          # consistent snapshot, WAL included
        dst.commit()
    finally:
        dst.close()
        src.close()

    after = counts(tmp)
    if after != before:
        print(f"[{name}] ❌ la còpia no quadra: {before} -> {after}. Deixo {tmp} per mirar-la.",
              file=sys.stderr)
        return False

    tmp.replace(current)
    # The read-back opens the temp file again, which recreates its -wal/-shm
    # sidecars; they belong to a name that no longer exists, so they would just
    # sit there looking like a broken database.
    for sidecar in (tmp.with_name(tmp.name + "-wal"), tmp.with_name(tmp.name + "-shm")):
        if sidecar.exists():
            sidecar.unlink()
    print(f"[{name}] ✅ copiada a {current} (l'original es queda on era)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Move a profile's sessions DB to the new path")
    parser.add_argument("--profile", help="profile id under ~/.fluent/")
    parser.add_argument("--dir", help="explicit profile directory")
    parser.add_argument("--all", action="store_true", help="every profile under ~/.fluent/")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="overwrite an existing copy")
    args = parser.parse_args()

    targets: list[Path] = []
    if args.dir:
        targets.append(Path(args.dir).expanduser())
    if args.profile:
        targets.append(Path.home() / ".fluent" / args.profile)
    if args.all:
        root = Path.home() / ".fluent"
        targets += sorted(p for p in root.iterdir()
                          if p.is_dir() and (p / "learner-profile.json").exists())
    if not targets:
        parser.error("give --profile, --dir or --all")

    ok = True
    for profile_dir in targets:
        if not profile_dir.exists():
            print(f"[{profile_dir.name}] ❌ no existeix: {profile_dir}", file=sys.stderr)
            ok = False
            continue
        ok = migrate(profile_dir, dry_run=args.dry_run, force=args.force) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
