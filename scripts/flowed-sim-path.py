#!/usr/bin/env python3
"""Simulated student on a curriculum: A1 -> A2 without the model.

Tests the MECHANICS of the learner path (what is new each day, when a
competence counts as consolidated, when the checkpoint opens, pass / carry /
stay / teacher, the % and the ETA) with invented answers. It does not test the
tutor: for that, the e2e bench. Never touches real learner data (writes to
--out, a temp dir by default).

    python3 scripts/flowed-sim-path.py --profile steady --seed 1
    python3 scripts/flowed-sim-path.py --profile weak --days 60 --admin
"""
from __future__ import annotations

import argparse
import math
import random
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))
import curriculum as cu  # noqa: E402

# p0: chance of a right answer before any practice; pmax: ceiling; k: speed.
PROFILES = {
    "fast": {"p0": 0.60, "pmax": 0.97, "k": 0.45, "hard": 1.0},
    "steady": {"p0": 0.45, "pmax": 0.95, "k": 0.28, "hard": 0.7},
    "weak": {"p0": 0.30, "pmax": 0.85, "k": 0.18, "hard": 0.45},
}
PER_DAY = 8
MAINTENANCE = 2


class Student:
    def __init__(self, profile: str, seed: int, cur: dict):
        self.prof = PROFILES[profile]
        self.rng = random.Random(seed)
        self.exposures: dict[str, int] = {}
        self.last: dict[str, date] = {}
        # a fixed handful of competences are hard for this student
        ids = [c["id"] for c in cur["competencies"]]
        self.hard = set(random.Random(f"{seed}:hard").sample(ids, k=3))

    def p(self, cid: str, today: date) -> float:
        pr = self.prof
        n = self.exposures.get(cid, 0)
        h = pr["hard"] if cid in self.hard else 1.0
        p = pr["p0"] + (pr["pmax"] - pr["p0"]) * h * (1 - math.exp(-pr["k"] * h * n))
        gap = (today - self.last[cid]).days if cid in self.last else 0
        if gap > 14:
            p *= 0.8
        elif gap > 7:
            p *= 0.9
        return max(0.02, min(0.99, p))

    def answer(self, cid: str, today: date, practice: bool = True) -> bool:
        ok = self.rng.random() < self.p(cid, today)
        if practice:
            self.exposures[cid] = self.exposures.get(cid, 0) + 1
            self.last[cid] = today
        return ok


def pick_maintenance(rows: list[dict], today: date, k: int) -> list[str]:
    done = [r for r in rows if r["state"] in ("consolidated", "mastered") and r["last_day"]]
    done.sort(key=lambda r: r["last_day"])
    return [r["id"] for r in done if (today - date.fromisoformat(r["last_day"])).days >= 3][:k]


def run(cur: dict, profile: str, seed: int, days: int, start: date, verbose: bool = True,
        cfg: dict | None = None, stop_when_ready: bool = False, on_answer=None) -> tuple[dict, dict]:
    """`stop_when_ready`: stop the day the level test would open (result "ready"), without taking it.
    `on_answer(cid, ok, day)` sees every answer given (the e2e ladder writes them as records)."""
    cfg = cfg or cu.CFG
    path = cu.new_path(cur)
    info: dict = {"day": None, "result": None, "true_p": None, "core_done": None}
    st = Student(profile, seed, cur)
    show = {1, 3, 7, 14, 21, 28, 35, 42, 56}
    for d in range(days):
        today = start + timedelta(days=d)
        day = today.isoformat()
        yesterday = (today - timedelta(days=1)).isoformat()
        rows = cu.summarize(cur, path, yesterday, cfg)
        actives = cu.active_competences(rows, path)
        # started but not consolidated: back again, but not two days running
        pool = [cid for cid in cu.review_pool(rows)
                if not any(r["id"] == cid and r["last_day"] == yesterday for r in rows)]
        maint = cu.due_maintenance(cur, path, day, cfg)[:MAINTENANCE]   # forgetting cycle: 3 -> 7 -> 14 -> 30 days
        plan: list[str] = []
        by_id = {c["id"]: c for c in cur["competencies"]}
        for cid in actives:            # new: the quota of its depth (deep = more)
            plan += [cid] * cu.quota(by_id[cid]["depth"], "new")
        for cid in pool:               # started: the quota of its depth, while there is room
            room = PER_DAY - len(plan) - len(maint)
            if room <= 0:
                break
            plan += [cid] * min(room, cu.quota(by_id[cid]["depth"], "review"))
        plan += maint
        i = 0
        filler = (actives + pool) or [r["id"] for r in rows if r["core"]][:1]
        while len(plan) < PER_DAY:      # nothing left to schedule: keep practising what is open
            plan.append(filler[i % len(filler)])
            i += 1
        plan = plan[:PER_DAY]
        for cid in plan:
            ok_ = st.answer(cid, today)
            if on_answer:
                on_answer(cid, ok_, today)
            cu.record_answer(path, cid, ok_, day)
        rows = cu.summarize(cur, path, day, cfg)
        event = ""
        last = cu.last_checkpoint_day(path)
        gap_ok = last is None or (today - date.fromisoformat(last)).days >= cu.CFG["checkpoint_gap_days"]
        if stop_when_ready and not path["promotions"] and cu.checkpoint_ready(rows, cfg, cur if cfg is cu.CFG else None):
            info = {"day": d + 1, "result": "ready", "pct": None, "true_p": None, "core_done": cu.progress(rows)["core_done"]}
            break
        if not path["promotions"] and cu.checkpoint_ready(rows, cfg, cur if cfg is cu.CFG else None) and gap_ok:
            items = cu.checkpoint_plan(cur, rows)
            results = [(cid, st.answer(cid, today, practice=False)) for cid in items]
            res = cu.apply_checkpoint(cur, path, day, results, cfg)
            core_ids = [r["id"] for r in rows if r["core"]]
            info = {"day": d + 1, "result": res["result"], "pct": res["pct"],
                    "true_p": sum(st.p(c, today) for c in core_ids) / len(core_ids),
                    "core_done": cu.progress(rows)["core_done"]}
            event = f"CHECKPOINT {res['correct']}/{res['items']} = {res['pct']:.0f}% → {res['result']}"
            if verbose:
                print(f"\n=== dia {d + 1}: {event}")
                if res["weak"]:
                    print("    fallades: " + ", ".join(w.split('.', 1)[-1] for w in res["weak"]))
            if res["result"] in ("pass", "carry", "teacher"):
                break
        if verbose and (d + 1) in show:
            print("\n" + cu.render_report(cur, path, day))
    return path, info


def run_ladder(profile: str, seed: int, days: int, start: date, verbose: bool = True) -> dict:
    """A0 -> A1 -> A2 through the real course machinery: the A1 course, the checkpoint, the cut
    (archive, certificate, profile level, new empty path) and the A2 course. Files in a temp dir."""
    import json
    data = Path(tempfile.mkdtemp(prefix="flowed-ladder-"))
    (data / "learner-profile.json").write_text(json.dumps(
        {"learner": {"target_language": "English", "target_level": "A2", "current_level": "A0"}}), encoding="utf-8")
    out: dict = {"data": str(data), "courses": []}
    day0 = start
    for level in ("A1", "A2"):
        cf = cu.find_curriculum(ROOT, data)
        cur = cu.load_curriculum(cf)
        assert cur["meta"]["level"] == level, f"expected the {level} course, got {cur['meta']['level']}"
        path, info = run(cur, profile, seed, days, day0, verbose=False)
        rows = cu.summarize(cur, path, None)
        step = {"level": level, "checkpoint_day": info["day"], "result": info["result"], "pct": info.get("pct")}
        out["courses"].append(step)
        if verbose:
            print(f"\n=== curs {level}: prova el dia {info['day']} → {info['result']} ({info.get('pct')}%), "
                  f"core consolidades {info['core_done']}/{sum(1 for r in rows if r['core'])}")
        if info["result"] not in ("pass", "carry"):
            break
        end = day0 + timedelta(days=info["day"] - 1)
        cu.save_path(data, path)
        res = cu.close_course(data, cur, end.isoformat(), root=ROOT,
                              now_ms=int(datetime.combine(end + timedelta(days=1), datetime.min.time()).timestamp() * 1000))
        step["closed"] = res
        if verbose:
            print(f"    tall: {res.get('archive')} · nivell següent: {res.get('next_level') or '— (objectiu assolit)'}")
        if not res.get("next_level"):
            break
        day0 = end + timedelta(days=1)
    out["certificates"] = cu.load_certificates(data)
    out["current"] = cu.find_curriculum(ROOT, data).name
    return out


def calibrate(cur: dict, n: int, days: int) -> None:
    """Same students, different rule for opening the checkpoint. `true p` is what the
    student really knows (mean chance of a right answer over the core) when promoted."""
    print(f"{n} seeds per profile. ready_share = share of core consolidated before the checkpoint opens.\n")
    print(f"{'profile':<8} {'ready':>5} | {'dia':>4} {'pass':>5} {'carry':>5} {'stay':>5} {'teach':>5} {'none':>5} | {'true p':>6} {'core ok':>7}")
    for prof in PROFILES:
        for share in (0.0, 0.5, 0.75, 1.0):
            cfg = dict(cu.CFG, ready_share=share)
            infos = [run(cur, prof, s, days, date(2026, 9, 21), verbose=False, cfg=cfg)[1] for s in range(1, n + 1)]
            got = [i for i in infos if i["day"]]
            cnt = {k: sum(1 for i in got if i["result"] == k) for k in ("pass", "carry", "stay", "teacher")}
            med = sorted(i["day"] for i in got)[len(got) // 2] if got else 0
            tp = sum(i["true_p"] for i in got) / len(got) if got else 0
            cd = sum(i["core_done"] for i in got) / len(got) if got else 0
            print(f"{prof:<8} {share:>5.2f} | {med:>4} {cnt['pass']:>5} {cnt['carry']:>5} {cnt['stay']:>5} {cnt['teacher']:>5} {n - len(got):>5} | {tp:>6.2f} {cd:>5.1f}/16")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--curriculum", default=str(ROOT / "curriculum" / "en-A2.md"))
    ap.add_argument("--profile", choices=sorted(PROFILES), default="steady")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--start", default="2026-09-21")
    ap.add_argument("--out", default="")
    ap.add_argument("--admin", action="store_true", help="admin report at the end")
    ap.add_argument("--calibrate", type=int, default=0, metavar="N", help="N seeds per profile x checkpoint rule")
    ap.add_argument("--quiet", action="store_true", help="only the final report")
    ap.add_argument("--ladder", action="store_true", help="A0 -> A1 -> A2 with the real course cut between the two")
    a = ap.parse_args()
    if a.ladder:
        r = run_ladder(a.profile, a.seed, a.days, date.fromisoformat(a.start), verbose=not a.quiet)
        print("\ncertificats: " + ", ".join(f"{c['level']} ({c['date']}, {c['type']})" for c in r["certificates"]))
        print(f"curs actual: {r['current']} · fitxers: {r['data']}")
        return 0
    cur = cu.load_curriculum(a.curriculum)
    if a.calibrate:
        calibrate(cur, a.calibrate, a.days)
        return 0
    path, _ = run(cur, a.profile, a.seed, a.days, date.fromisoformat(a.start), verbose=not a.quiet)
    last_day = max(x[0] for c in path["competencies"].values() for x in c["answers"])
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="flowed-sim-path-"))
    out.mkdir(parents=True, exist_ok=True)
    cu.save_path(out, path)
    print("\n" + "=" * 60 + "\nFINAL\n")
    print(cu.render_report(cur, path, last_day, admin=a.admin))
    print(f"\nlearner-path.json: {cu.path_file(out)}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main())
