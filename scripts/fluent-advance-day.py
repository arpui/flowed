#!/usr/bin/env python3
"""Move a test profile's clock forward, so tomorrow can be tested today.

The thing nobody has ever checked is the one the whole system is built on: that
what she answered correctly today comes back later, and what she missed comes
back tomorrow. Waiting a day per test is not a plan.

Every stored date in the profile is shifted back by N days, which is the same
thing as the calendar moving forward: an item due tomorrow becomes due now, a
pattern last seen today becomes last seen yesterday. Today's lesson plan and
records are set aside, because a new day starts empty.

    python3 scripts/fluent-advance-day.py test-en            # +1 dia
    python3 scripts/fluent-advance-day.py test-en --days 7

Refuses anything that is not a scratch profile: rewriting a learner's dates is
not a thing to do by accident.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SCRATCH = re.compile(r"^(test|demo|e2e)", re.I)
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FILES = ("spaced-repetition.json", "mistakes-db.json", "mastery-db.json",
         "progress-db.json", "session-log.json", "learner-profile.json")


def shift(value, days: int):
    """Every YYYY-MM-DD in the document, N days earlier."""
    if isinstance(value, str):
        if ISO.match(value):
            try:
                return (datetime.strptime(value, "%Y-%m-%d").date()
                        - timedelta(days=days)).isoformat()
            except ValueError:
                return value
        return value
    if isinstance(value, list):
        return [shift(v, days) for v in value]
    if isinstance(value, dict):
        return {k: shift(v, days) for k, v in value.items()}
    return value


def shift_records(prof: Path, days: int) -> int:
    """Every recorded answer, N days earlier: the learner path takes its day from `ts`."""
    n = 0
    rd = prof / ".records"
    for f in sorted(rd.glob("*.jsonl")) if rd.is_dir() else []:
        out = []
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                out.append(line)
                continue
            if isinstance(rec, dict) and isinstance(rec.get("ts"), (int, float)):
                rec["ts"] = int(rec["ts"] - days * 86_400_000)
                n += 1
            out.append(json.dumps(rec, ensure_ascii=False))
        f.write_text("\n".join(out) + "\n", encoding="utf-8")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("profile", nargs="?", default="test-en")
    ap.add_argument("--dir", help="directori de perfil explícit")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--keep-records", action="store_true", dest="keep_records",
                    help="no arxivis .records/: desplaça el `ts` de cada resposta N dies enrere "
                         "(learner-path.json també). Per a l'escenari `curriculum`, on el camí es "
                         "deriva de TOTES les respostes; sense això el dia 2 no veu el dia 1.")
    args = ap.parse_args()

    prof = Path(args.dir).expanduser() if args.dir else Path.home() / ".fluent" / args.profile
    if not (prof / "learner-profile.json").exists():
        print(f"❌ perfil no trobat: {prof}", file=sys.stderr)
        return 2
    if not SCRATCH.match(prof.name):
        print(f"❌ només en perfils de proves (test*/demo*/e2e*), no en {prof.name}", file=sys.stderr)
        return 2
    if args.days < 1:
        print("❌ --days ha de ser 1 o més", file=sys.stderr)
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for name in FILES:
        f = prof / name
        if not f.exists():
            continue
        (prof / f"{name}.bak-{stamp}").write_text(f.read_text(), encoding="utf-8")
        f.write_text(json.dumps(shift(json.loads(f.read_text()), args.days),
                                indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # A new day starts empty: today's plan and counters belong to the day that
    # just ended, and the sweeper must not finalise it into the new one.
    for d, pattern in ((".daily", "*.json"), (".records", "*.jsonl")):
        if d == ".records" and args.keep_records:
            continue
        for f in (prof / d).glob(pattern) if (prof / d).is_dir() else []:
            f.rename(prof / d / f".{f.name}.day-{stamp}")
    if args.keep_records:
        shifted = shift_records(prof, args.days)
        lp = prof / "learner-path.json"
        if lp.exists():
            doc = shift(json.loads(lp.read_text(encoding="utf-8")), args.days)
            if isinstance(doc.get("start_ts"), (int, float)):       # the cut of the course moves with the records
                doc["start_ts"] = int(doc["start_ts"] - args.days * 86_400_000)
            lp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        for name in ("certificates.json", "course-notices.json"):
            f = prof / name
            if f.exists():
                f.write_text(json.dumps(shift(json.loads(f.read_text(encoding="utf-8")), args.days),
                                        indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  (respostes conservades: {shifted} desplaçades {args.days} dia/es enrere)")
    draft = prof / "session-draft.json"
    if draft.exists():
        draft.rename(prof / f"session-draft.json.bak-{stamp}")

    # update-db.py keeps a T0 snapshot per `session-NNN@<date>`. A real tomorrow has
    # another date, so yesterday's snapshots are simply never found. Here the wall
    # clock does NOT move: without this, day 2's "session-001" finds day 1's T0,
    # restores the databases to before day 1 and re-applies — and the SM-2 never
    # progresses, whatever the tutor does. (Measured 2026-09-20: five simulated
    # days, one new snapshot; every "right" answer stuck at 1 day.)
    t0 = prof / ".update-state"
    moved_t0 = 0
    if t0.is_dir():
        out = t0 / "_archive"
        for f in list(t0.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                out.mkdir(exist_ok=True)
                f.rename(out / f"{stamp}-{f.name}")
                moved_t0 += 1

    today = date.today().isoformat()
    sr = json.loads((prof / "spaced-repetition.json").read_text())
    due = [k for k, v in (sr.get("items") or {}).items()
           if isinstance(v.get("due_date"), str) and v["due_date"] <= today]
    print(f"perfil {prof.name}: el rellotge avança {args.days} dia/es")
    print(f"  per repassar ara: {len(due)}  → {due}")
    print(f"  (còpies .bak-{stamp}; el dia d'avui s'ha arxivat"
          + (f"; {moved_t0} instantànies T0 apartades" if moved_t0 else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
