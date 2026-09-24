#!/usr/bin/env python3
"""Mark old sessions as finished, WITHOUT processing them.

    python3 scripts/close-old-sessions.py --profile alex-en --dry-run
    python3 scripts/close-old-sessions.py --profile alex-en

What it does: writes `capa_b_done` into the session row's metadata, which is the
flag the sweeper reads. Nothing else. It does NOT run Capa B, does NOT touch the
six learning databases, does NOT write a results file, and does NOT change a
single number the learner can see.

Why it exists: sessions from the old build were never closed. Today they are
already ignored — the sweeper only looks 24 hours back — so this changes no
behaviour now. It makes that state EXPLICIT, so a future change to that window,
or a script run by mistake, cannot wake a three-week-old session and fold it
into the databases a second time.

Deliberately not incorporated: those sessions' per-turn data is already in the
databases (Capa A wrote it at the time). Re-processing them now would risk
double-counting, and the summaries are not worth that risk.

Stop the web instances first: the DB is in WAL mode.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import re
from datetime import datetime
from pathlib import Path

CURRENT_REL = Path("sessions") / "sessions.db"
LEGACY_REL = Path(".opencode") / "opencode" / "opencode.db"
DEFAULT_OLDER_THAN_DAYS = 2


def profile_dirs(args) -> list[Path]:
    out: list[Path] = []
    if args.dir:
        out.append(Path(args.dir).expanduser())
    if args.profile:
        out.append(Path.home() / ".fluent" / args.profile)
    if args.all:
        root = Path.home() / ".fluent"
        out += sorted(p for p in root.iterdir()
                      if p.is_dir() and (p / "learner-profile.json").exists())
    return out


def open_sessions(db: Path):
    return [
        (sid, activity, meta or "")
        for sid, activity, meta in sqlite3.connect(f"file:{db}?mode=ro", uri=True).execute(
            "SELECT id, last_activity, COALESCE(metadata,'') FROM session "
            "WHERE json_extract(COALESCE(metadata,'{}'), '$.capa_b_done') IS NULL "
            "ORDER BY last_activity"
        )
    ]


def close(db: Path, cutoff_ms: int, dry_run: bool) -> int:
    """Mark every unfinished session older than the cutoff. Returns how many."""
    try:
        rows = [r for r in open_sessions(db) if (r[1] or 0) < cutoff_ms]
    except sqlite3.Error as exc:
        print(f"  ⚠ {db}: {exc}", file=sys.stderr)
        return 0
    if not rows:
        print("  (cap sessió antiga oberta)")
        return 0

    for sid, activity, _ in rows:
        when = datetime.fromtimestamp((activity or 0) / 1000).strftime("%Y-%m-%d %H:%M")
        print(f"  {'(simulat) ' if dry_run else ''}tancant  {when}  {sid[:24]}")
    if dry_run:
        return len(rows)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db.with_name(f"{db.name}.bak-{stamp}")
    shutil.copy2(db, backup)
    print(f"  còpia de seguretat: {backup.name}")

    conn = sqlite3.connect(db)
    try:
        now_ms = int(datetime.now().timestamp() * 1000)
        conn.executemany(
            "UPDATE session SET metadata = json_set(COALESCE(metadata,'{}'), '$.capa_b_done', ?) "
            "WHERE id = ?",
            [(now_ms, sid) for sid, _, _ in rows],
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Marca sessions velles com a tancades, sense processar-les",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--profile", help="id del perfil sota ~/.fluent/")
    ap.add_argument("--dir", help="directori de perfil explícit")
    ap.add_argument("--all", action="store_true", help="tots els perfils")
    ap.add_argument("--older-than", type=int, default=DEFAULT_OLDER_THAN_DAYS,
                    metavar="DIES", help=f"dies d'antiguitat mínima (per defecte {DEFAULT_OLDER_THAN_DAYS})")
    ap.add_argument("--legacy", action="store_true",
                    help="fes-ho també a la BD antiga (.opencode/), que el build vell encara usa")
    ap.add_argument("--include-today", action="store_true",
                    help="permet --older-than 0. NOMÉS per a perfils de proves "
                         "(test*/demo*/e2e*): tanca també les sessions d'avui, perquè "
                         "l'escombrall no reompli les bases de dades acabades de buidar")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    targets = profile_dirs(args)
    if not targets:
        ap.error("dona --profile, --dir o --all")
    if args.older_than < 1 and not args.include_today:
        ap.error("--older-than ha de ser 1 dia com a mínim: no toquem sessions d'avui")

    if args.include_today:
        # The rig guard: a scratch profile only. On a learner's profile this
        # would close the session they are sitting in.
        guard_names = [args.profile] if args.profile else ([Path(args.dir).name] if args.dir else [])
        for name in guard_names:
            if not re.match(r"^(test|demo|e2e)", name or "", re.I):
                ap.error(f"--include-today només en perfils de proves, no en {name}")
        if args.all:
            ap.error("--include-today no es combina amb --all")
    cutoff_ms = int((datetime.now().timestamp() - args.older_than * 86400) * 1000)
    print(f"tancant sessions anteriors a {datetime.fromtimestamp(cutoff_ms / 1000):%Y-%m-%d %H:%M}"
          f"{'  (SIMULACIÓ)' if args.dry_run else ''}\n")

    total = 0
    for d in targets:
        print(f"=== {d.name} ===")
        if not d.exists():
            print(f"  ❌ no existeix: {d}", file=sys.stderr)
            continue
        dbs = [d / CURRENT_REL] + ([d / LEGACY_REL] if args.legacy else [])
        for db in dbs:
            if not db.exists():
                continue
            print(f"  {db.parent.name}/{db.name}")
            total += close(db, cutoff_ms, args.dry_run)
        print()

    verb = "es tancarien" if args.dry_run else "tancades"
    print(f"{total} sessió/ns {verb}. Les 6 bases de dades NO s'han tocat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
