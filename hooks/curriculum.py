#!/usr/bin/env python3
"""Curriculum + learner path: what has to be learned, and how far along the learner is.

Two things live here and nothing else:

1. A reader for `curriculum/<language>-<level>.md` (format explained at the top of
   that file).
2. The learner's path through it. Only FACTS are stored (`learner-path.json`: every
   answer as [day, 0|1], every checkpoint, every promotion). The state of each
   competence (unseen -> introduced -> practicing -> consolidated -> mastered),
   the % and the ETA are DERIVED from those facts, on demand. So the thresholds can
   be recalibrated later without losing history, and any past day can be replayed.

No behaviour of the app depends on this yet (docs/ESQUEMA-APRENENTATGE.md, phase 0-1).
The state rules are the competence-level version of the ones in that document;
when the server tags each SM-2 item with its `competency`, `consolidated` and
`mastered` will read the item intervals instead of the answer history.

CLI:
    python3 hooks/curriculum.py report --curriculum curriculum/en-A2.md [--data DIR] [--admin]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_schema import ERROR_CATEGORIES, LEGACY_ERROR_CATEGORIES  # noqa: E402

# The language curriculum files (curriculum/en-*.md) still ship in the fork and
# use the FlowEd grammar names as `#tags`; the math taxonomy (WP1.4) replaced
# them in ERROR_CATEGORIES. Until the math curriculum lands (WP1.1), tags and
# item-id heads may be either generation — new content should use the math
# names, legacy names keep validating.
ALL_CATEGORY_NAMES = frozenset(ERROR_CATEGORIES) | frozenset(LEGACY_ERROR_CATEGORIES)
import bank as bank_mod  # noqa: E402

STATES = ("unseen", "introduced", "practicing", "consolidated", "mastered")
# Contribution of a competence to the level bar. 100 % = every `core` competence
# consolidated: that is what "ready for the checkpoint" means, mastered adds nothing
# to the bar (it is reported apart).
POINTS = {"unseen": 0.0, "introduced": 0.15, "practicing": 0.5, "consolidated": 1.0, "mastered": 1.0}
LABEL = {
    "unseen": "sense veure", "introduced": "introduïda", "practicing": "en pràctica",
    "consolidated": "consolidada", "mastered": "dominada",
}

CFG = {
    "practicing_min": 3,       # answers to leave `introduced`
    "window": 10,              # last answers that decide consolidation   (these four are the `normal` depth)
    "min_answers": 12,
    "accuracy": 0.8,           # share correct in the window
    "min_span_days": 5,        # days the review window must span before consolidating
    "mastered_span_days": 21,  # first answer -> last answer
    "mastered_streak": 4,      # last answers all correct
    "stalled_answers": 24,     # this many answers and still not consolidated (twice min_answers)
    "forgotten_days": 14,      # consolidated but not seen for this long
    "keep_answers": 200,       # per competence, oldest dropped
    "checkpoint_gap_days": 3,  # between two checkpoints
    "max_repeats": 2,          # repetitions of a failed checkpoint before the teacher decides
    "max_active": 3,           # new competences in play at once (one per section)
    "review_days": [3, 7, 14, 30],  # after consolidation: days to the next review of a competence, growing with each good one
    "ready_share": 0.0,        # share of core that must be consolidated before the checkpoint opens (0 = "practicing" is enough)
}



# How much evidence a competence needs before it counts as consolidated, and how much
# practice per day it gets while it is being learned. A tense that takes weeks to get
# right (deep) is not a list of five words (light): six correct answers prove the second,
# not the first. Declared by each competence (`Depth:`), `normal` when it says nothing.
# `new` / `review`: exercises per day while it is new (< 3 answers) / practising.
DEPTH = {
    # min_answers raised 2026-09-23 (Albert): 8/12/20 -> 10/20/30 -- stalled_answers
    # left as it was (16/24/40), so light and deep keep less than the "twice
    # min_answers" margin the comment above used to describe; flagged, not
    # changed on its own, since only min_answers was asked for.
    "light": {"min_answers": 10, "window": 8, "min_span_days": 3, "stalled_answers": 16, "new": 3, "review": 2},
    "normal": {"min_answers": 20, "window": 10, "min_span_days": 5, "stalled_answers": 24, "new": 3, "review": 2},
    "deep": {"min_answers": 30, "window": 12, "min_span_days": 7, "stalled_answers": 40, "new": 4, "review": 3},
}


# Dev-only escape hatch (Albert, 2026-09-23): testing a full day's worth of
# curriculum behaviour in one sitting needs competences to be able to
# consolidate same-day, which `min_span_days` (3-7 depending on depth) exists
# specifically to prevent in real use -- that gap is real spaced repetition,
# not padding. The old way to bypass it was editing CFG["min_span_days"]
# directly, which silently did nothing (cfg_for() always re-applies the
# per-depth value from DEPTH on top of it) and, worse, had no guard against
# that edit surviving into a deploy. This env var is the only way to override
# it now: unset (the default, and always the case in production -- it is
# never set in any shipped .env) it does nothing at all; set it in a
# railab-only .env (never .env in the repo root, never anything synced to
# llvm) to force every competence's min_span_days to that value regardless of
# depth, for exactly as long as that shell has it exported.
_MIN_SPAN_DAYS_OVERRIDE = os.environ.get("FLOWED_TEST_MIN_SPAN_DAYS")


def cfg_for(cfg: dict, depth: str | None) -> dict:
    """The thresholds of a competence: the global ones, with its depth on top.

    "normal" used to be a special case that skipped straight to the bare
    `cfg` instead of merging `DEPTH["normal"]` like "light" and "deep" do.
    That was fine while CFG's own min_answers (12) mirrored DEPTH["normal"]'s
    (the comment next to CFG still says so) -- until DEPTH's three were
    raised 2026-09-23 (10/20/30) and CFG's flat default was not, silently
    leaving every `normal`-depth competence (most of A1 and A2) consolidating
    at 12 answers instead of 20. Fixed 2026-09-24 (Albert): "normal" now goes
    through DEPTH like the other two depths, so all three actually get what
    DEPTH says they get.
    """
    if not depth or depth not in DEPTH:
        out = cfg
    else:
        d = DEPTH[depth]
        out = {**cfg, **{k: v for k, v in d.items() if k not in ("new", "review")}}
    if _MIN_SPAN_DAYS_OVERRIDE is not None:
        out = {**out, "min_span_days": int(_MIN_SPAN_DAYS_OVERRIDE)}
    return out


def quota(depth: str | None, kind: str) -> int:
    """Exercises per day of a competence: kind is `new` or `review`."""
    return DEPTH.get(depth or "normal", DEPTH["normal"])[kind]


_HEAD = re.compile(r"^###\s+(\S+)\s+—\s+(.*?)\s*\[(core|extra)\]\s*$")
_KEY = re.compile(r"^(Can do|Requires|Forms|Words|Replaces|Tags|Signals|Depth|Weight|Check):\s*(.*)$")


# ---- curriculum file ---------------------------------------------------------

def _parse_check(line: str) -> dict | None:
    body = line[2:].strip()
    kind, _, rest = body.partition(":")
    prompt, arrow, ans = rest.rpartition("→")
    if not arrow:
        return None
    return {
        "type": kind.strip(),
        "prompt": prompt.strip(),
        "answer": ans.strip(),
        "alternatives": [a.strip() for a in ans.split(" / ") if a.strip()],
    }


def parse_curriculum(text: str) -> dict:
    lines = text.splitlines()
    meta: dict = {}
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            k, _, v = lines[i].partition(":")
            meta[k.strip()] = v.strip()
            i += 1
        i += 1
    for k in ("version", "pass_mark", "carry_mark", "checkpoint_items", "ready_share"):
        if k in meta:
            meta[k] = int(meta[k])
    comps: list[dict] = []
    retired: list[str] = []
    section = ""
    cur: dict | None = None
    in_check = False
    in_retired = False
    for raw in lines[i:]:
        s = raw.rstrip()
        m = _HEAD.match(s)
        if m:
            cur = {
                "id": m.group(1), "name": m.group(2), "core": m.group(3) == "core",
                "section": section, "can_do": "", "requires": [], "forms": "",
                "words": [], "replaces": [], "tags": [], "signals": [], "checks": [],
                "depth": "normal", "weight": 1,
            }
            comps.append(cur)
            in_check = False
            continue
        if s.startswith("## "):
            section = s[3:].strip()
            in_retired = section.lower() == "retirades"
            cur = None
            in_check = False
            continue
        if in_retired:
            if s.startswith("- "):
                retired.append(s[2:].strip())
            continue
        if cur is None:
            continue
        if in_check and s.startswith("- "):
            c = _parse_check(s)
            if c:
                cur["checks"].append(c)
            continue
        k = _KEY.match(s)
        if not k:
            continue
        key, val = k.group(1), k.group(2).strip()
        in_check = key == "Check"
        if key == "Can do":
            cur["can_do"] = val
        elif key == "Requires":
            cur["requires"] = [x.strip() for x in val.split(",") if x.strip()]
        elif key == "Forms":
            cur["forms"] = val
        elif key == "Words":
            cur["words"] = [x.strip() for x in val.split(",") if x.strip()]
        elif key == "Replaces":
            cur["replaces"] = [x.strip() for x in val.split(",") if x.strip()]
        elif key == "Tags":
            cur["tags"] = [x.strip().lower() for x in val.split(",") if x.strip()]
        elif key == "Signals":
            cur["signals"] = [x.strip().lower() for x in val.split(",") if x.strip()]
        elif key == "Depth":
            cur["depth"] = val.strip().lower()
        elif key == "Weight":
            try:
                cur["weight"] = int(val)
            except ValueError:
                cur["weight"] = 0
    return {"meta": meta, "competencies": comps, "retired": retired}


EXTRA_FILE = "extra.md"


def load_curriculum(path: str | os.PathLike, data_dir: str | os.PathLike | None = None) -> dict:
    """The level's curriculum; with `data_dir`, plus that learner's own extras."""
    cur = parse_curriculum(Path(path).read_text(encoding="utf-8"))
    if data_dir:
        add_profile_extras(cur, data_dir)
    return cur


def add_profile_extras(cur: dict, data_dir: str | os.PathLike) -> dict:
    """Competences only one learner has: `<profile>/extra.md`, same format as
    the curriculum (2026-09-27, Albert: a song, or what they do in class this
    week). `[extra]` ones are practised like any other but never count towards
    the level bar or the checkpoint (`progress` and `checkpoint_plan` only look
    at `core`). Their exercises live in `<profile>/bank/<id>.json` (hooks/bank.py).
    An id that is already in the curriculum is ignored: an extra never replaces
    a competence of the level."""
    f = Path(data_dir) / EXTRA_FILE
    if not f.is_file():
        return cur
    try:
        ext = parse_curriculum(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cur
    known = {c["id"] for c in cur["competencies"]}
    for c in ext["competencies"]:
        if c["id"] in known:
            continue
        c["section"] = c["section"] or "Extra"
        c["profile"] = True
        cur["competencies"].append(c)
        known.add(c["id"])
    return cur


def validate_curriculum(cur: dict) -> list[str]:
    """Problems a teacher editing the file would want to hear about."""
    out: list[str] = []
    ids = [c["id"] for c in cur["competencies"]]
    for cid in {i for i in ids if ids.count(i) > 1}:
        out.append(f"id repetit: {cid}")
    for c in cur["competencies"]:
        if len(c["checks"]) != 3:
            out.append(f"{c['id']}: {len(c['checks'])} Check (n'hi ha de ser 3)")
        for r in c["requires"]:
            if r not in ids:
                out.append(f"{c['id']}: Requires desconegut {r}")
        if c["depth"] not in DEPTH:
            out.append(f"{c['id']}: Depth desconegut {c['depth']} ({', '.join(DEPTH)})")
        if not 1 <= c["weight"] <= 3:
            out.append(f"{c['id']}: Weight ha de ser 1, 2 o 3")
        if c["section"].lower().startswith("vocab") and not c["words"]:
            out.append(f"{c['id']}: vocabulari sense Words")
        for tag in c["tags"]:
            if tag.startswith("#") and tag[1:] not in ALL_CATEGORY_NAMES:
                out.append(f"{c['id']}: Tags desconegut {tag} (categories: {', '.join(ERROR_CATEGORIES)})")
        if not c["section"].lower().startswith("vocab") and not c["tags"]:
            out.append(f"{c['id']}: sense Tags (les respostes no es podran assignar a aquesta competència)")
    m = cur["meta"]
    if not 0 <= m.get("ready_share", 0) <= 100:
        out.append("ready_share ha de ser un percentatge (0-100)")
    if not (0 < m.get("carry_mark", 0) < m.get("pass_mark", 0) <= 100):
        out.append("carry_mark ha de ser menor que pass_mark (≤ 100)")
    core = sum(1 for c in cur["competencies"] if c["core"])
    if m.get("checkpoint_items", 0) < core:
        out.append(f"checkpoint_items ({m.get('checkpoint_items')}) < competències core ({core})")
    return out


# ---- learner path (facts only) ----------------------------------------------

def new_path(cur: dict, start_ts: int = 0) -> dict:
    """An empty path for a course. `start_ts` (ms) is the cut: records made before it belong to an
    earlier course and do not count here."""
    m = cur["meta"]
    return {
        "version": 1,
        "curriculum": f"{m.get('language', '')}-{m.get('level', '')}",
        "curriculum_version": m.get("version"),
        "start_ts": int(start_ts),
        "competencies": {},
        "checkpoints": [],
        "promotions": [],
        "reinforce": [],
        "carried": [],
    }


def path_file(data_dir: str | os.PathLike) -> Path:
    return Path(data_dir) / "learner-path.json"


def load_path(data_dir: str | os.PathLike, cur: dict) -> dict:
    p = path_file(data_dir)
    if p.exists():
        path = json.loads(p.read_text(encoding="utf-8"))
        if path.get("curriculum") in (None, new_path(cur)["curriculum"]):
            return path
    return new_path(cur)


def save_path(data_dir: str | os.PathLike, path: dict) -> None:
    p = path_file(data_dir)
    tmp = p.with_suffix(".json.tmp")
    text = json.dumps(path, ensure_ascii=False, indent=1)
    # one answer per line, not four: [ "2026-09-21", 1 ]
    text = re.sub(r'\[\s+("\d{4}-\d\d-\d\d"),\s+([01])\s+\]', r"[\1,\2]", text)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def record_answer(path: dict, cid: str, ok: bool, day: str, cfg: dict = CFG) -> None:
    entry = path["competencies"].setdefault(cid, {"answers": []})
    entry["answers"].append([day, 1 if ok else 0])
    if len(entry["answers"]) > cfg["keep_answers"]:
        entry["answers"] = entry["answers"][-cfg["keep_answers"]:]


# ---- derived state ----------------------------------------------------------

def rest_cap(depth: str | None, cfg: dict = CFG) -> int:
    """How many all-correct answers today earn a competence a day off (Albert,
    2026-09-23): 30% of its own min_answers, min 2 -- proportional to how much
    evidence it needs in the first place. Shared by next_target() (which
    competence to pick next) and summarize() (so the report/web can show it),
    so the two never disagree about what "resting" means."""
    need = cfg_for(cfg, depth)["min_answers"]
    return max(2, -(-need * 3 // 10))  # ceil(0.3 * need)


def rested_today(answers: list, depth: str | None, today: str, cfg: dict = CFG) -> bool:
    """True once `answers` has >= rest_cap() entries for `today`, all correct.
    A single wrong answer today makes this False again (see next_target)."""
    today_ans = [ok for d, ok in answers if d == today]
    return len(today_ans) >= rest_cap(depth, cfg) and all(today_ans)


def display_score(answers: list, depth: str | None, cfg: dict = CFG) -> float:
    """Continuous 0..1 progress for DISPLAY ONLY (Albert, 2026-09-24): the real
    state machine (competence_state, just above) still gates everything that
    matters -- when an exercise is offered, checkpoint readiness, "resting
    today". This is purely what the bar/percentage shows, so a day of real
    effort is visibly rewarded without being able to fake actual consolidation.

    effort  = (1 - e^-(n/need)) * recent_accuracy -- grows with every correct
              answer and saturates on its own as evidence piles up (need =
              min_answers), so it can reach ~1.0 in a single sitting.
    ceiling = 0.5 + 0.5 * min(1, days_spanned / min_span_days) -- grows ONLY
              with the calendar, mirroring the `spaced` check in
              competence_state() exactly (same window, same min_span_days).
    display = min(effort, ceiling): visible movement for genuine work, but
    capped below full until practice is actually spread over days.
    """
    ecfg = cfg_for(cfg, depth)
    n = len(answers)
    if n == 0:
        return 0.0
    window = answers[-ecfg["window"]:]
    acc = sum(a[1] for a in window) / len(window)
    effort = (1 - math.exp(-n / ecfg["min_answers"])) * acc
    days = (date.fromisoformat(window[-1][0]) - date.fromisoformat(window[0][0])).days
    ceiling = 0.5 + 0.5 * min(1.0, days / ecfg["min_span_days"])
    return min(effort, ceiling)


def competence_state(answers: list, cfg: dict = CFG, depth: str | None = None) -> str:
    cfg = cfg_for(cfg, depth)
    n = len(answers)
    if n == 0:
        return "unseen"
    if n < cfg["practicing_min"]:
        return "introduced"
    window = answers[-cfg["window"]:]
    acc = sum(a[1] for a in window) / len(window)
    spaced = (date.fromisoformat(window[-1][0]) - date.fromisoformat(window[0][0])).days >= cfg["min_span_days"]
    if n >= cfg["min_answers"] and acc >= cfg["accuracy"] and spaced:
        span = (date.fromisoformat(answers[-1][0]) - date.fromisoformat(answers[0][0])).days
        streak = answers[-cfg["mastered_streak"]:]
        if span >= cfg["mastered_span_days"] and len(streak) == cfg["mastered_streak"] and all(a[1] for a in streak):
            return "mastered"
        return "consolidated"
    return "practicing"


def summarize(cur: dict, path: dict, as_of: str | None = None, cfg: dict = CFG) -> list[dict]:
    """One row per competence, as of a day (default: everything recorded)."""
    rows = []
    for c in cur["competencies"]:
        ans = path["competencies"].get(c["id"], {}).get("answers", [])
        if as_of:
            ans = [a for a in ans if a[0] <= as_of]
        depth = c.get("depth", "normal")
        ecfg = cfg_for(cfg, depth)
        state = competence_state(ans, cfg, depth)
        recent = ans[-ecfg["window"]:]
        rows.append({
            "id": c["id"], "name": c["name"], "core": c["core"], "section": c["section"],
            "state": state, "n": len(ans), "depth": depth, "weight": c.get("weight", 1),
            "need": ecfg["min_answers"],
            "acc_all": (sum(a[1] for a in ans) / len(ans)) if ans else None,
            "acc_recent": (sum(a[1] for a in recent) / len(recent)) if recent else None,
            "first_day": ans[0][0] if ans else None,
            "last_day": ans[-1][0] if ans else None,
            "stalled": len(ans) >= ecfg["stalled_answers"] and state not in ("consolidated", "mastered"),
            # Today's exercise picker skips this competence for the rest of
            # `as_of` once it hits this (see rested_today docstring) -- surfaced
            # here so the report/web can show it instead of it just silently
            # not coming up (Albert, 2026-09-24: "no canvia... és el límit
            # diari o què és?").
            "resting_today": bool(as_of) and state not in ("consolidated", "mastered") and rested_today(ans, depth, as_of, cfg),
            # Display-only continuous score (see display_score docstring):
            # unseen/consolidated/mastered are already the extremes 0/1, so
            # only introduced/practicing need the saturating formula.
            "display_pct": 0.0 if state == "unseen" else 100.0 if state in ("consolidated", "mastered")
                           else round(100.0 * display_score(ans, depth, cfg), 1),
        })
    return rows


def _done(r: dict) -> bool:
    return r["state"] in ("consolidated", "mastered")


def progress(rows: list[dict]) -> dict:
    core = [r for r in rows if r["core"]]
    total_w = sum(r.get("weight", 1) for r in core)
    # Weighted by the same continuous display_pct as each row (falls back to
    # the discrete POINTS if a row predates that field) -- so the headline %
    # moves with real same-day effort instead of sitting frozen at whatever
    # the discrete state happens to be (Albert, 2026-09-24).
    pts = sum((r["display_pct"] / 100.0 if "display_pct" in r else POINTS[r["state"]]) * r.get("weight", 1) for r in core)
    return {
        "pct": 100.0 * pts / total_w if total_w else 0.0,
        "core_total": len(core),
        "core_done": sum(1 for r in core if _done(r)),
        "core_mastered": sum(1 for r in core if r["state"] == "mastered"),
        "in_progress": sum(1 for r in core if r["state"] in ("introduced", "practicing")),
        "unseen": sum(1 for r in core if r["state"] == "unseen"),
    }


def active_competences(rows: list[dict], path: dict, cfg: dict = CFG) -> list[str]:
    """What is NEW today: one competence per section, in file order — then shuffled.

    Only competences not yet started (unseen / introduced) are new: once a
    competence is `practicing` it leaves the slot and comes back through
    `review_pool` on later days — consolidation needs the days in between, so
    the slot cannot wait for it. `core` first; an `extra` only when the section
    has no `core` left. After a failed checkpoint the weak ones come first.

    The list used to come back in file order (Gramàtica, Funcions, Vocabulari)
    every time, and `next_target`'s picker always tries the list front-to-back,
    excluding only the ONE competence just asked — never a fair rotation.
    Measured live, 2026-09-23 (nes-en): 14 grammar/function competences
    introduced over 3 days against 1 vocabulary one — Gramàtica and Funcions
    ping-ponged turn after turn (each excludes the other as `last_id`, so each
    one keeps winning the very next turn) and Vocabulari only got a turn on
    the rare occasion both others were exhausted at once. Rotated here instead
    of always front-to-back, so each active section gets a fair turn at going
    first. Rotation, not `random.shuffle`: keyed off the total answers already
    on record (deterministic given the same history), so replaying the same
    path (`test_simulated_student_is_deterministic_and_reaches_a_verdict`)
    still gives the same result every time — true randomness would have
    broken that. Reading and Speaking never call this (agent.ts only builds
    this note for math-learn / math-vocab) — untouched.
    """
    if path.get("reinforce"):
        return list(path["reinforce"])[: cfg["max_active"]]
    sections: dict[str, list[dict]] = {}
    for r in rows:
        sections.setdefault(r["section"], []).append(r)
    picks: list[str] = []
    for rs in sections.values():
        for want_core in (True, False):
            cand = [r for r in rs if r["core"] == want_core and r["state"] in ("unseen", "introduced")]
            if cand:
                picks.append(cand[0]["id"])
                break
    if picks:
        total_answers = sum(r["n"] for r in rows)
        k = total_answers % len(picks)
        picks = picks[k:] + picks[:k]
    return picks[: cfg["max_active"]]


def review_pool(rows: list[dict]) -> list[str]:
    """Started but not consolidated: they need to come back on other days. Weakest first."""
    pool = [r for r in rows if r["state"] == "practicing" and not r["stalled"]]
    pool.sort(key=lambda r: (r["acc_recent"] if r["acc_recent"] is not None else 0.0, r["last_day"] or ""))
    return [r["id"] for r in pool]


# ---- checkpoint --------------------------------------------------------------

def checkpoint_ready(rows: list[dict], cfg: dict = CFG, cur: dict | None = None) -> bool:
    """Every core competence at least `practicing`, and `ready_share` of them consolidated.

    `ready_share` is the level file's (`ready_share:` in the front matter, a percentage), else CFG's."""
    core = [r for r in rows if r["core"]]
    if not core or not all(STATES.index(r["state"]) >= 2 for r in core):
        return False
    share = cur["meta"]["ready_share"] / 100 if cur and "ready_share" in cur["meta"] else cfg["ready_share"]
    return sum(1 for r in core if _done(r)) / len(core) >= share


def checkpoint_plan(cur: dict, rows: list[dict]) -> list[str]:
    """Competence of each checkpoint item: one per core, the rest on the weakest."""
    n = cur["meta"].get("checkpoint_items", 0)
    core = [r for r in rows if r["core"]]
    plan = [r["id"] for r in core]
    weakest = sorted(core, key=lambda r: (r["acc_recent"] if r["acc_recent"] is not None else 0.0,
                                          STATES.index(r["state"])))
    k = 0
    while len(plan) < n and weakest:
        plan.append(weakest[k % len(weakest)]["id"])
        k += 1
    return plan


def checkpoint_result(cur: dict, results: list[tuple[str, bool]], previous_stays: int, cfg: dict = CFG) -> dict:
    """results: (competence, correct) per item. -> pct, outcome, weak competences."""
    total = len(results)
    correct = sum(1 for _, ok in results if ok)
    pct = 100.0 * correct / total if total else 0.0
    m = cur["meta"]
    weak = sorted({cid for cid, ok in results if not ok}, key=[c["id"] for c in cur["competencies"]].index)
    if pct >= m["pass_mark"]:
        outcome = "pass"
    elif pct >= m["carry_mark"]:
        outcome = "carry"
    elif previous_stays >= cfg["max_repeats"]:
        outcome = "teacher"
    else:
        outcome = "stay"
    return {"items": total, "correct": correct, "pct": round(pct, 1), "result": outcome, "weak": weak}


def apply_checkpoint(cur: dict, path: dict, day: str, results: list[tuple[str, bool]], cfg: dict = CFG) -> dict:
    stays = sum(1 for c in path["checkpoints"] if c["result"] == "stay")
    res = checkpoint_result(cur, results, stays, cfg)
    res["date"] = day
    res["level"] = cur["meta"].get("level")
    path["checkpoints"].append(res)
    if res["result"] in ("pass", "carry"):
        path["reinforce"] = []
        path["carried"] = res["weak"] if res["result"] == "carry" else []
        path["promotions"].append({
            "date": day, "achieved": cur["meta"].get("level"), "type": "checkpoint",
            "carried": path["carried"],
        })
    elif res["result"] == "stay":
        path["reinforce"] = res["weak"]
    return res


def last_checkpoint_day(path: dict) -> str | None:
    return path["checkpoints"][-1]["date"] if path["checkpoints"] else None


# ---- the level test: run by the server, graded by the server ----------------------
#
# The test certifies a level, so it does not depend on a model's mood: the server picks the
# items (the closed `Check`s: Complete / Correct / Meaning, one per core competence at least,
# the rest on the weakest), asks them one at a time and grades them by comparing with the
# expected answer. Only the outcome touches the path (apply_checkpoint) — and, on pass / carry,
# the cut (close_course). The test's answers are not practice: they are kept in the run and in
# the checkpoint entry, not in the records.

CLOSED_TYPES = ("Complete", "Correct", "Meaning")


def run_file(data_dir) -> Path:
    return Path(data_dir) / "checkpoint-run.json"


def _norm(text: str) -> str:
    t = str(text).lower().replace("’", "'").replace("‘", "'")
    t = re.sub(r"[^a-z0-9'\- ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _blank_filled(prompt: str, alt: str) -> str:
    """The sentence of a `Complete` with its blank(s) filled by the (comma-separated) answer; hints in
    brackets are dropped."""
    text = re.sub(r"\([^)]*\)", " ", prompt)
    parts = [x.strip() for x in alt.split(", ")]
    for part in parts:
        if "___" not in text:
            break
        text = text.replace("___", part, 1)
    return text


def grade_check(check: dict, text: str) -> bool:
    """Is `text` an accepted answer to this closed check? Case, punctuation and contractions'
    apostrophes do not matter; the answer may be the missing words or the whole sentence."""
    got = _norm(text)
    if not got:
        return False
    for alt in [a.strip() for a in check["answer"].split("/") if a.strip()]:
        if got == _norm(alt):
            return True
        if check["type"] == "Complete" and got == _norm(_blank_filled(check["prompt"], alt)):
            return True
        if check["type"] == "Complete" and ", " in alt:
            # several blanks: the words in order, anywhere in the reply
            pos, ok = 0, True
            for part in (_norm(x) for x in alt.split(", ")):
                i = f" {got} ".find(f" {part} ", pos)
                if i < 0:
                    ok = False
                    break
                pos = i + len(part) + 1
            if ok:
                return True
        if check["type"] == "Meaning" and len(got.split()) <= 5 and f" {_norm(alt)} " in f" {got} ":
            return True
    return False


def _question(check: dict, i: int, total: int) -> str:
    b = check.get("bank")
    if b:
        head = {"complete": "Complete the sentence:", "choose": "Choose and complete:", "correct": "Correct the sentence:",
                "meaning": "Which word means:", "translate": "Translate:"}.get(b["type"], "Complete the sentence:")
        body = b["sentence"]
        if b["type"] in ("meaning", "translate"):
            body = f"{b.get('instruction', '')} {b['sentence']}".strip()
        if b["type"] == "choose" and b.get("options"):
            body += "  (" + " / ".join(b["options"]) + ")"
        return f"## Level test — question {i}/{total}\n\n**{head}** {body}\n\n**Type your answer:**"
    head = {"Complete": "Complete the sentence:", "Correct": "Correct the sentence:", "Meaning": "Which word means:"}[check["type"]]
    return f"## Level test — question {i}/{total}\n\n**{head}** {check['prompt']}\n\n**Type your answer:**"


def _expected(check: dict) -> str:
    return " / ".join(a.strip() for a in check["answer"].split("/") if a.strip())


def checkpoint_wait_until(path: dict, cfg: dict = CFG) -> str | None:
    """The first day a new attempt is allowed (None: now)."""
    last = last_checkpoint_day(path)
    return (date.fromisoformat(last) + timedelta(days=cfg["checkpoint_gap_days"])).isoformat() if last else None


def checkpoint_status(data_dir) -> dict:
    run = _read_json(run_file(data_dir), None)
    if not isinstance(run, dict):
        return {"active": False}
    return {"active": True, "i": run["i"] + 1, "total": len(run["items"]), "level": run.get("level")}


BANK_TO_CHECK = {"complete": "Complete", "choose": "Complete", "correct": "Correct",
                 "meaning": "Meaning", "translate": "Translate"}


def _bank_checkpoint_items(root, stem: str, cid: str, data_dir, today: str, used: set) -> list[dict]:
    """The level test's candidates for one competence, from the bank.

    It used to draw only on the curriculum's three `Check:` examples per
    competence — 54 items for all of A1, the flawed ones included ("I ___ (swim),
    but I can't fly. → can"). The exercise that decides whether she moves up had
    the thinnest material in the app (Albert, 2026-09-24). Now: the reviewed
    bank, never an item of an earlier level test, and preferring what she has
    not practised in the last 7 days — a test, not a replay of this week.
    """
    items = bank_mod.load_bank(Path(root), stem, cid, data_dir)
    if not items:
        return []
    prog = bank_mod._load_progress(data_dir).get(cid, {})
    def recent(it) -> int:
        rec = prog.get(it["id"])
        if not rec:
            return 0
        try:
            return 1 if (date.fromisoformat(today) - date.fromisoformat(rec["date"])).days < 7 else 0
        except (ValueError, KeyError):
            return 0
    fresh = [it for it in items if (cid, it["sentence"]) not in used]
    fresh.sort(key=lambda it: (recent(it), items.index(it)))
    return [{"cid": cid, "type": BANK_TO_CHECK.get(it["type"], "Complete"), "prompt": it["sentence"],
             "answer": " / ".join([it["answer"], *it.get("also_accept", [])]), "bank": it} for it in fresh]


def checkpoint_start(data_dir, cur: dict, today: str, force: bool = False, cfg: dict = CFG,
                     stem: str | None = None, root=None) -> dict:
    """Begin (or resume, the same day) the level test. {ok, text, ...}."""
    run = _read_json(run_file(data_dir), None)
    if isinstance(run, dict) and run.get("course") == f"{cur['meta'].get('language')}-{cur['meta'].get('level')}" \
            and run.get("day") == today:
        c = run["items"][run["i"]]
        return {"ok": True, "resumed": True, "text": "Let's carry on with the level test.\n\n" + _question(c, run["i"] + 1, len(run["items"])),
                "i": run["i"] + 1, "total": len(run["items"])}
    path = rebuild_path(data_dir, cur)
    rows = summarize(cur, path, today, cfg)
    if path.get("promotions"):
        return {"ok": False, "text": f"You have already certified {cur['meta'].get('level')}."}
    wait = checkpoint_wait_until(path, cfg)
    if not force and wait and today < wait:
        return {"ok": False, "text": f"You can try the level test again on {wait}. Until then, we practise the weak points."}
    if not force and not checkpoint_ready(rows, cfg, cur):
        return {"ok": False, "text": "The level test opens when you have worked on every main topic and consolidated enough of them."}
    used = {(c["cid"], c["prompt"]) for cp in path["checkpoints"] for c in cp.get("detail", [])}
    banks: dict[str, list[dict]] = {}
    for c in cur["competencies"]:
        from_bank = (_bank_checkpoint_items(root or Path(__file__).resolve().parent.parent, stem, c["id"],
                                            data_dir, today, used) if stem else [])
        if from_bank:
            banks[c["id"]] = from_bank
            continue
        checks = [k for k in c["checks"] if k["type"] in CLOSED_TYPES]
        banks[c["id"]] = sorted(checks, key=lambda k: ((c["id"], k["prompt"]) in used, c["checks"].index(k)))
    items, taken = [], set()
    for cid in checkpoint_plan(cur, rows):
        for k in banks.get(cid, []):
            if (cid, k["prompt"]) not in taken:
                taken.add((cid, k["prompt"]))
                items.append({**k, "cid": cid})
                break
    if not items:
        return {"ok": False, "text": "This level has no closed exercises for a test yet."}
    random.Random(f"{today}:{len(path['checkpoints'])}").shuffle(items)
    run = {"course": path["curriculum"], "level": cur["meta"].get("level"), "day": today, "i": 0, "items": items, "results": []}
    _write_json(run_file(data_dir), run)
    intro = (f"# Level test {cur['meta'].get('level')}\n\n{len(items)} short questions. "
             f"You need {cur['meta'].get('pass_mark')}% to pass. There is no help during the test.\n\n")
    return {"ok": True, "text": intro + _question(items[0], 1, len(items)), "i": 1, "total": len(items)}


def checkpoint_answer(data_dir, cur: dict, today: str, text: str, root=None, cfg: dict = CFG) -> dict:
    """Grade the answer to the current question, then ask the next one or finish (apply the result,
    and on pass / carry close the course)."""
    run = _read_json(run_file(data_dir), None)
    if not isinstance(run, dict) or run.get("day") != today:
        run_file(data_dir).unlink(missing_ok=True)
        return {"ok": False, "text": "There is no level test in progress."}
    item = run["items"][run["i"]]
    # A bank item is graded by the bank's own grader, the one Go and Review use:
    # a typo (7/10) is not a pass in a level test.
    ok = (bank_mod.grade(item["bank"], text)["score"] >= 8) if item.get("bank") else grade_check(item, text)
    run["results"].append({"cid": item["cid"], "prompt": item["prompt"], "answer": str(text)[:200], "correct": ok})
    run["i"] += 1
    verdict = "✅ Correct!" if ok else f"❌ Not quite. The answer was: **{_expected(item)}**"
    total = len(run["items"])
    if run["i"] < total:
        _write_json(run_file(data_dir), run)
        return {"ok": True, "done": False, "correct": ok, "i": run["i"] + 1, "total": total,
                "text": f"{verdict}\n\n{_question(run['items'][run['i']], run['i'] + 1, total)}"}
    path = rebuild_path(data_dir, cur)
    res = apply_checkpoint(cur, path, today, [(r["cid"], r["correct"]) for r in run["results"]], cfg)
    res["detail"] = [{"cid": r["cid"], "prompt": r["prompt"], "correct": r["correct"]} for r in run["results"]]
    save_path(data_dir, path)
    run_file(data_dir).unlink(missing_ok=True)
    closed = None
    if res["result"] in ("pass", "carry"):
        closed = close_course(data_dir, cur, today, res, root=root, kind="checkpoint")
    names = {c["id"]: c["name"] for c in cur["competencies"]}
    weak = ", ".join(names[w] for w in res["weak"])
    head = f"{verdict}\n\n## Level test finished\n\n**{res['correct']}/{res['items']} — {res['pct']:.0f}%**\n\n"
    if res["result"] == "pass":
        body = f"🎉 You passed. Level {cur['meta'].get('level')} is certified."
    elif res["result"] == "carry":
        body = (f"🎉 You passed. Level {cur['meta'].get('level')} is certified." +
                (f" To review: {weak}." if weak else ""))
    elif res["result"] == "stay":
        wait = checkpoint_wait_until(path, cfg)
        body = (f"Not yet: you need {cur['meta'].get('carry_mark')}% to move on. We will practise: {weak}. "
                f"You can try again on {wait}.")
    else:
        body = "Your teacher will decide the next step."
    return {"ok": True, "done": True, "correct": ok, "result": res, "closed": closed, "text": head + body}


# ---- tagging: which competence does a recorded answer belong to ---------------
#
# Nothing is written on the record: the tag is DERIVED, so a better mapping
# re-tags the whole history. The only exception is a `competency` field on the
# record itself (phase 2: the server assigns the competence, and that is
# authoritative).

KNOWN_SCORE = 8  # same threshold as the server: an answer >= 8 counts as right


def _words_in(text: str, tag: str) -> bool:
    return re.search(r"(?<![\w'])" + re.escape(tag) + r"(?![\w'])", text) is not None


def _record_category(rec: dict) -> str | None:
    """The kind of mistake/item: from the queue item id (`agreement_she_goes…`), else the first correction."""
    item = str(rec.get("item_id") or "")
    head = item.split("_", 1)[0]
    if head in ALL_CATEGORY_NAMES:
        return head
    for c in rec.get("corrections") or []:
        cat = str((c or {}).get("category") or "").strip().lower()
        if cat in ALL_CATEGORY_NAMES:
            return cat
    return None


def _vocab_candidates(rec: dict) -> list[str]:
    """The strings a vocabulary record can name its word by, best first: the queue item, the word the
    card asked (`exercise`, when it is a word and not a sentence), the corrected form, and the answer
    when it was right. A card goes either direction, so the target-language word can be any of them."""
    out: list[str] = []
    item = str(rec.get("item_id") or "")
    if item.startswith("vocabulary_"):
        out.append(item[len("vocabulary_"):].replace("_", " ").strip().lower())
    ex = str(rec.get("exercise") or "").strip().lower()
    if 0 < len(ex.split()) <= 3:
        out.append(ex)
    for c in rec.get("corrections") or []:
        right = str((c or {}).get("right") or "").strip().lower()
        if right:
            out.append(right)
    if float(rec.get("score") or 0) >= KNOWN_SCORE:
        out.append(str(rec.get("learner_answer") or "").strip().lower())
    return [w for w in out if w]


def _vocab_hit(cur: dict, rec: dict) -> tuple[str | None, str]:
    """(competence id, the word from its list) for a vocabulary record, or (None, "")."""
    for w in _vocab_candidates(rec):
        for c in cur["competencies"]:
            if w in [x.lower() for x in c["words"]]:
                return c["id"], w
    return None, ""


def competency_of(cur: dict, rec: dict) -> tuple[str | None, str]:
    """(competence id or None, how). `how` is the rule that decided, or why nothing did."""
    comps = cur["competencies"]
    ids = {c["id"] for c in comps}
    explicit = str(rec.get("competency") or "")
    if explicit in ids:
        return explicit, "record"
    is_vocab = str(rec.get("skill") or "").lower() == "vocabulary" or str(rec.get("item_id") or "").startswith("vocabulary_")
    if is_vocab:
        cid, _ = _vocab_hit(cur, rec)
        if cid:
            return cid, "words"
        if not _vocab_candidates(rec):
            return None, "vocab-without-word"
        # A record the tutor labelled "vocabulary" but that is really a sentence exercise (measured 2026-09-21,
        # curriculum 211700: "Suggest a place to go…" / "mine" filed as vocabulary): tag it as grammar.
        if str(rec.get("item_id") or "").startswith("vocabulary_"):
            return None, "word-not-in-list"
        cid, why = _tag_grammar(cur, rec)
        return (cid, why) if cid else (None, "word-not-in-list")
    return _tag_grammar(cur, rec)


# Tags this common are never discriminating: "a"/"is" sit inside almost every
# English sentence, so as a literal Tags: entry they win the count for whatever
# competence lists them regardless of what the exercise is actually about.
# Measured 2026-09-22: three "There is/are" exercises in a row were tagged
# a1.articles_plurals (or nothing) instead of a1.there_is_are, because
# "a"/"the" (articles_plurals) or "is"/"are" (verb_to_be) matched every one of
# them and outscored the real, more specific tag. Multi-word tags ("there is",
# "isn't", contractions) stay meaningful and are not touched.
_GENERIC_TAGS = {"a", "an", "the", "is", "are", "am"}


def _tag_grammar(cur: dict, rec: dict) -> tuple[str | None, str]:
    comps = cur["competencies"]
    grammar = [c for c in comps if c["tags"]]
    cat = _record_category(rec)
    pool = " ".join([
        str(rec.get("exercise") or ""), str(rec.get("learner_answer") or ""),
        *[f"{(c or {}).get('wrong', '')} {(c or {}).get('right', '')}" for c in rec.get("corrections") or []],
        str(rec.get("item_id") or "").replace("_", " "),
    ]).lower()
    if cat:
        cands = [c for c in grammar if f"#{cat}" in c["tags"]]
        if not cands:
            return None, "category-not-in-curriculum"
    else:
        cands = grammar
    scored = [(sum(1 for tg in c["tags"] if not tg.startswith("#") and tg not in _GENERIC_TAGS and _words_in(pool, tg)), i, c) for i, c in enumerate(cands)]
    best = max((s for s, _, _ in scored), default=0)
    if best > 0:
        top = [c for s, _, c in scored if s == best]
        return top[0]["id"], "tags"
    if cat and len(cands) == 1:
        return cands[0]["id"], "category"
    return None, "ambiguous" if cat else "no-signal"


def read_records(data_dir: str | os.PathLike) -> list[dict]:
    """Every recorded answer of the learner, oldest first, without duplicates."""
    out: list[dict] = []
    seen: set[str] = set()
    for f in sorted((Path(data_dir) / ".records").glob("*.jsonl")):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get("score") is None:
                continue
            rid = rec.get("record_id")
            if rid:
                if rid in seen:
                    continue
                seen.add(rid)
            out.append(rec)
    out.sort(key=lambda r: r.get("ts") or 0)
    return out


def rebuild_path(data_dir: str | os.PathLike, cur: dict, cfg: dict = CFG, save: bool = True) -> dict:
    """Recompute the answers of the path from the records. Idempotent: run it as often as you like.

    Keeps what is not derived from records (checkpoints, promotions, reinforcement).
    """
    if save:
        _archive_foreign_path(data_dir, cur)
    old = load_path(data_dir, cur)
    path = new_path(cur, old.get("start_ts", 0))
    for k in ("checkpoints", "promotions", "reinforce", "carried"):
        path[k] = old.get(k, path[k])
    how: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    # a course only counts the records made since it started
    recs = [r for r in read_records(data_dir) if (r.get("ts") or 0) >= path["start_ts"]]
    for rec in recs:
        cid, why = competency_of(cur, rec)
        how[why] = how.get(why, 0) + 1
        if cid is None:
            s = samples.setdefault(why, [])
            if len(s) < 5:
                s.append(str(rec.get("item_id") or rec.get("exercise") or "")[:60])
            continue
        day = datetime.fromtimestamp((rec.get("ts") or 0) / 1000).date().isoformat()
        record_answer(path, cid, float(rec["score"]) >= KNOWN_SCORE, day, cfg)
    tagged = sum(n for k, n in how.items() if k in ("record", "words", "tags", "category"))
    path["tagging"] = {"records": len(recs), "tagged": tagged, "how": how, "untagged_samples": samples}
    if save:
        save_path(data_dir, path)
    return path


# ---- courses: one curriculum at a time, a hard cut between levels ----------------
#
# A course is the work towards ONE level. The learner does not declare a level: it is
# certified by the checkpoint (or by the teacher). Certifying closes the course for good:
# its path is archived, a certificate is written (never removed), the profile's level moves
# up, and the next level starts as a NEW course with an empty path. What is not derived from
# answers stays (the SM-2 queue and the mistakes that review errors, the sessions, the
# records themselves); what is derived (bar, states, checkpoints) starts again from the cut.
# Weak competences are NOT carried into the new course: they stay on the certificate for the
# teacher, and the SM-2 review keeps working on the mistakes.

LEVELS = ("A0", "A1", "A2", "B1", "B2", "C1", "C2")


def _lvl(level: str) -> int:
    try:
        return LEVELS.index(str(level).strip().upper())
    except ValueError:
        return 99


def _write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def certificates_file(data_dir) -> Path:
    return Path(data_dir) / "certificates.json"


def load_certificates(data_dir) -> list[dict]:
    d = _read_json(certificates_file(data_dir), [])
    return d if isinstance(d, list) else []


def certified_levels(data_dir, language: str) -> set[str]:
    return {str(c.get("level", "")).upper() for c in load_certificates(data_dir)
            if str(c.get("language", "")).lower() == str(language).lower()}


def ladder(root, language: str) -> list[Path]:
    """The curriculum files of a language, lowest level first."""
    out = []
    for f in (Path(root) / "curriculum").glob("*.md"):
        try:
            meta = parse_curriculum(f.read_text(encoding="utf-8"))["meta"]
        except OSError:
            continue
        if str(meta.get("language", "")).lower() == str(language).lower():
            out.append((_lvl(meta.get("level", "")), f))
    return [f for _, f in sorted(out, key=lambda t: (t[0], t[1].name))]


def _learner(data_dir) -> dict:
    return _read_json(Path(data_dir) / "learner-profile.json", {}).get("learner", {}) or {}


def find_curriculum(root: str | os.PathLike, data_dir: str | os.PathLike | None = None) -> Path | None:
    """The curriculum of this learner's CURRENT course: $FLOWED_CURRICULUM, else — among the
    curricula of the profile's target_language up to its target_level — the lowest level that has
    not been certified yet (the declared current level is not trusted: it is certified by a
    checkpoint). When every level up to the target is certified, the last one (goal reached).
    None when there is no curriculum."""
    env = os.environ.get("FLOWED_CURRICULUM")
    if env:
        p = Path(env).expanduser()
        p = p if p.is_absolute() else Path(root) / p
        return p if p.exists() else None
    if not data_dir:
        return None
    learner = _learner(data_dir)
    lang = str(learner.get("target_language") or "").strip()
    target = _lvl(learner.get("target_level") or "")
    if not lang or target == 99:
        return None
    files = []
    for f in ladder(root, lang):
        try:
            lv = parse_curriculum(f.read_text(encoding="utf-8"))["meta"].get("level", "")
        except OSError:
            continue
        if _lvl(lv) <= target:
            files.append((str(lv).upper(), f))
    if not files:
        return None
    done = certified_levels(data_dir, lang)
    for lv, f in files:
        if lv not in done:
            return f
    return files[-1][1]


def _archive_foreign_path(data_dir, cur: dict) -> None:
    """A learner-path.json that belongs to another course (the profile changed, a file was copied
    over) is archived before it can be overwritten: nothing the learner did is ever lost."""
    p = path_file(data_dir)
    old = _read_json(p, None)
    if not isinstance(old, dict) or old.get("curriculum") in (None, new_path(cur)["curriculum"]):
        return
    if not old.get("competencies"):
        return
    n = 0
    while True:
        dest = Path(data_dir) / "courses" / f"{old.get('curriculum', 'unknown')}-orphan{'' if not n else '-' + str(n)}.json"
        if not dest.exists():
            break
        n += 1
    _write_json(dest, {"closed": None, "result": {"result": "orphan"}, "path": old})
    p.unlink()


def _set_profile_level(data_dir, level: str) -> None:
    f = Path(data_dir) / "learner-profile.json"
    prof = _read_json(f, None)
    if not isinstance(prof, dict) or not isinstance(prof.get("learner"), dict):
        return
    prof["learner"]["current_level"] = level
    _write_json(f, prof)


def notices_file(data_dir) -> Path:
    return Path(data_dir) / "course-notices.json"


def pending_notices(data_dir) -> list[dict]:
    d = _read_json(notices_file(data_dir), [])
    return [n for n in d if isinstance(n, dict) and not n.get("seen")] if isinstance(d, list) else []


def mark_notices_seen(data_dir) -> int:
    d = _read_json(notices_file(data_dir), [])
    n = 0
    if isinstance(d, list):
        for x in d:
            if isinstance(x, dict) and not x.get("seen"):
                x["seen"] = True
                n += 1
        _write_json(notices_file(data_dir), d)
    return n


def close_course(data_dir, cur: dict, day: str, result: dict | None = None, now_ms: int | None = None,
                 root=None, kind: str = "checkpoint") -> dict:
    """Certify the level of `cur`, archive its path and start the next course (if the profile's target
    is higher). The only writer of the certificate and of the profile's current level.

    Idempotent: a level that is already certified is left alone."""
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    m = cur["meta"]
    lang, level = m.get("language", ""), m.get("level", "")
    if str(level).upper() in certified_levels(data_dir, lang):
        return {"already": True, "level": level}
    path = load_path(data_dir, cur)
    res = dict(result or (path["checkpoints"][-1] if path.get("checkpoints") else {}))
    rows = summarize(cur, path, day)
    if kind == "manual" or not res:
        res = {"result": "manual", "pct": None,
               "weak": [r["id"] for r in rows if r["core"] and r["state"] not in ("consolidated", "mastered")]}
    final = [{"id": r["id"], "state": r["state"], "answers": r["n"],
              "acc": None if r["acc_all"] is None else round(100 * r["acc_all"])} for r in rows]
    n = 0
    while True:
        dest = Path(data_dir) / "courses" / f"{lang}-{level}-{day}{'' if not n else '-' + str(n)}.json"
        if not dest.exists():
            break
        n += 1
    _write_json(dest, {"course": path.get("curriculum"), "closed": day, "result": res, "final": final, "path": path})
    cert = {"language": lang, "level": level, "date": day, "type": kind, "result": res.get("result"),
            "pct": res.get("pct"), "weak": res.get("weak", []), "archive": f"courses/{dest.name}"}
    _write_json(certificates_file(data_dir), load_certificates(data_dir) + [cert])
    _set_profile_level(data_dir, level)
    nxt = find_curriculum(root, data_dir)
    nxt_cur = load_curriculum(nxt) if nxt else None
    next_level = nxt_cur["meta"].get("level") if nxt_cur and str(nxt_cur["meta"].get("level", "")).upper() != str(level).upper() else None
    if next_level:
        _write_json(path_file(data_dir), new_path(nxt_cur, now_ms if now_ms is not None else int(datetime.now().timestamp() * 1000)))
    notices = _read_json(notices_file(data_dir), [])
    notices = notices if isinstance(notices, list) else []
    notices.append({"type": "course_completed", "language": lang, "level": level, "date": day,
                    "pct": res.get("pct"), "result": res.get("result"), "next_level": next_level,
                    "weak": [c.split(".", 1)[-1] for c in res.get("weak", [])], "seen": False})
    _write_json(notices_file(data_dir), notices)
    return {"already": False, "level": level, "next_level": next_level, "archive": cert["archive"]}


# ---- forgetting cycle: when a consolidated competence has to come back --------
#
# Derived from the answers, like everything else. Proposal 2026-09-21 (docs/
# ESQUEMA-APRENENTATGE.md 6.5): the intervals are a first guess, to be calibrated.

def _consolidated_at(answers: list, cfg: dict, depth: str | None = None) -> int | None:
    for i in range(len(answers)):
        if competence_state(answers[: i + 1], cfg, depth) in ("consolidated", "mastered"):
            return i
    return None


def review_due(answers: list, today: str, cfg: dict = CFG, depth: str | None = None) -> bool:
    """A consolidated competence is due when enough days have passed since its last answer:
    `review_days[k]` after k spaced good reviews, and the next day after a miss.

    A good answer only counts as a review when it comes at least `review_days[k]`
    days after the previous one: the answer of the day after consolidation is
    practice, not a review that earns a longer gap."""
    if competence_state(answers, cfg, depth) not in ("consolidated", "mastered"):
        return False
    start = _consolidated_at(answers, cfg, depth)
    if start is None:
        return False
    steps = cfg["review_days"]
    k, anchor = 0, date.fromisoformat(answers[start][0])
    for d, ok in answers[start + 1:]:
        day = date.fromisoformat(d)
        if ok and (day - anchor).days >= steps[min(k, len(steps) - 1)]:
            k += 1
            anchor = day
    gap = 1 if answers[-1][1] == 0 else steps[min(k, len(steps) - 1)]
    return (date.fromisoformat(today) - date.fromisoformat(answers[-1][0])).days >= gap


def due_maintenance(cur: dict, path: dict, today: str, cfg: dict = CFG) -> list[str]:
    """Consolidated competences that are due, the longest-waiting first."""
    out = []
    for c in cur["competencies"]:
        ans = [a for a in path["competencies"].get(c["id"], {}).get("answers", []) if a[0] <= today]
        if ans and review_due(ans, today, cfg, c.get("depth")):
            out.append((ans[-1][0], c["id"]))
    return [cid for _, cid in sorted(out)]


# ---- the next exercise: what the server tells the tutor to practise -----------

def _today_counts(recs: list[dict], cur: dict, today: str) -> dict[str, int]:
    n: dict[str, int] = {}
    for rec in recs:
        day = datetime.fromtimestamp((rec.get("ts") or 0) / 1000).date().isoformat()
        if day != today:
            continue
        cid, _ = competency_of(cur, rec)
        if cid:
            n[cid] = n.get(cid, 0) + 1
    return n


def writing_frame(cur: dict, data_dir: str | os.PathLike, today: str | None = None,
                  cfg: dict = CFG) -> dict:
    """The structure a Writing task should get her to USE, as a short note.

    Writing is the one practice where she produces text of her own. Go already
    drills each structure with closed exercises (a gap, a sentence to correct);
    Writing reinforces the same structure from the other side: a topic that
    needs it, written freely. So this borrows the active grammar/function
    competence from the same plan Go uses — read-only, nothing is assigned or
    counted here — and says how to frame the task, never what to fill in.
    """
    t = next_target(cur, data_dir, today, cfg=cfg, only_grammar=True)
    if not t.get("id"):
        return {}
    comp = next((c for c in cur["competencies"] if c["id"] == t["id"]), None) or {}
    note = (f'Writing frame — build the task so that what she writes naturally uses this structure: '
            f'{comp.get("can_do") or t.get("can_do", "")}')
    note = note.rstrip(". ")
    if comp.get("forms"):
        note += f' (forms: {str(comp["forms"]).rstrip(". ")}).'
    else:
        note += "."
    note += (' Give her a topic from her own life that needs it, and name the one or two words she should '
             'use (for example "Use: I have, It is"). She writes her own sentences: no gap, no sentence to '
             'complete, no sentence to copy. Never say the name of the grammar point to her.')
    return {"id": t["id"], "name": t.get("name", t["id"]), "note": note}


def next_target(cur: dict, data_dir: str | os.PathLike, today: str | None = None,
                last_id: str | None = None, cfg: dict = CFG, only_vocab: bool = False,
                only_grammar: bool = False) -> dict:
    """The competence the NEXT free-practice exercise is about, and the note that says so.

    No daily quota (removed 2026-09-23, Albert: "la idea és que no hi hagués cap
    límit i punt" -- `quota()` used to gate how many exercises of a competence
    counted per day, which was meant as a spacing PACE across several short
    sessions. It has no meaning for someone doing an hour in one sitting: once
    every competence was over its count for the day, the old fallback always
    picked the single weakest-accuracy one, minus only the literal last ask --
    two competences ping-ponged forever. There is no cap here now, of any kind:
    whatever is new today (still capped in NUMBER by `active_competences`'s own
    `max_active`, not by exercises-per-day) or started-but-not-consolidated or
    due for maintenance is all one pool, and every turn goes to whichever
    competence in it has been asked LEAST so far today -- ties broken by the
    pool's own order (new competences first, then review weakest-accuracy-
    first, then maintenance). That naturally round-robins through the whole
    pool, however long the session runs, and never repeats one before every
    other candidate has had an equal turn. `quota()` itself is untouched --
    other callers (flowed-e2e.py, flowed-sim-path.py, its own tests) still use
    it for their own simulated pacing.

    `only_vocab`: the Vocabulary practice asks one word at a time, so it is only handed
    the competences that have words (`{}` when there is none to offer).
    """
    today = today or date.today().isoformat()
    recs = read_records(data_dir)
    path = rebuild_path(data_dir, cur, cfg, save=False)
    rows = summarize(cur, path, today, cfg)
    by_id = {c["id"]: c for c in cur["competencies"]}
    counts = _today_counts(recs, cur, today)
    plan = [(c, "new") for c in active_competences(rows, path, cfg)]
    plan += [(c, "review") for c in review_pool(rows)]
    plan += [(c, "maintenance") for c in due_maintenance(cur, path, today, cfg)]
    if only_vocab:
        plan = [(c, k) for c, k in plan if by_id[c]["words"]]
    if only_grammar:
        plan = [(c, k) for c, k in plan if not by_id[c]["words"]]

    # A competence rests for the REST OF TODAY once it has come up enough
    # times today, all of them right, with no error today at all (Albert,
    # 2026-09-23: "un cop una competència ja ha sortit aquestes vegades sense
    # error no cal que surti més durant el mateix dia"). "Enough" is
    # proportional to how much evidence that competence needs in the first
    # place, not a flat number for everyone: 30% of its own `min_answers` --
    # 3 for light (10), 6 for normal (20), 9 for deep (30) -- so a competence
    # that takes more to prove also takes more to earn a day off. A single
    # wrong answer today cancels the day's rest entirely (not just pauses
    # it): she is still working on it, so it stays in rotation for the rest
    # of today regardless of how many she got right before or after that
    # miss. Tomorrow starts clean, same as every daily count in this file.
    def _rested_today(cid: str) -> bool:
        answers = path["competencies"].get(cid, {}).get("answers", [])
        return rested_today(answers, by_id[cid].get("depth"), today, cfg)

    rest = (
        [c for c, _ in plan if c != last_id and not _rested_today(c)]
        or [c for c, _ in plan if c != last_id]
        or [c for c, _ in plan]
        or [r["id"] for r in rows if r["core"]]
    )
    if only_vocab:
        rest = [c for c in rest if by_id[c]["words"]] or [r["id"] for r in rows if by_id[r["id"]]["words"] and r["core"]]
    if only_grammar:
        rest = [c for c in rest if not by_id[c]["words"]] or [r["id"] for r in rows if not by_id[r["id"]]["words"] and r["core"]]
    if not rest:
        return {}
    best = min(rest, key=lambda c: counts.get(c, 0))
    best_kind = next((k for c, k in plan if c == best), "review")
    cid, kind = best, best_kind
    comp = by_id[cid]
    counts_all = {cid: path["competencies"].get(cid, {}).get("answers", [])}
    used = {w for r in recs for c2, w in [_vocab_hit(cur, r)] if c2 == cid}
    words = [w for w in comp["words"] if w.lower() not in used][:5] or comp["words"][:5]
    signals = comp["signals"] or [tg for tg in comp["tags"] if not tg.startswith("#")]
    # Fase 5 (2026-09-24): with the bank on, Go and Vocabulary are served by the
    # server and this note only reaches the model when a competence has no bank
    # item — the fallback. The paragraphs each incident used to add (numbers,
    # "vary the type", the long pin-the-blank rule) went with the guards they
    # were paired with; what stays is what the fallback still needs to aim.
    parts = [f'Curriculum — the next exercise practises "{comp["name"]}": {comp["can_do"]}']
    if comp["forms"]:
        parts.append(f"Structures: {comp['forms']}.")
    if comp["words"]:
        parts.append(f'Make the card about ONE of these words: {", ".join(words or comp["words"][:5])}. '
                     f'Not a word outside this list. If the card has a gap, put the word in her own language in '
                     f'brackets after it — "The car is ___ (vermell)." — so only one word fits.')
    else:
        parts.append("It is a SENTENCE exercise: a gap to fill or a sentence to correct, where the gap is this "
                     "structure itself. Never a vocabulary card or a translation, and never say the name of the "
                     "competence to her.")
        shapes = [c for c in comp["checks"] if c["type"] in ("Complete", "Correct", "Ask", "Say")]
        if shapes:
            ex = shapes[len(counts_all.get(cid, [])) % len(shapes)]
            parts.append(f'Shape of one (write a DIFFERENT sentence, never copy this one): {ex["type"]}: {ex["prompt"]}.')
    parts.append("Make it different from the ones already asked. Say nothing about this note.")
    return {"id": cid, "name": comp["name"], "kind": kind, "can_do": comp["can_do"],
            "signals": signals, "words": words, "vocab": bool(comp["words"]), "note": " ".join(parts)}


# ---- history and estimate ----------------------------------------------------

def history(cur: dict, path: dict, step: int = 7, upto: str | None = None) -> list[tuple[str, float]]:
    days = sorted({a[0] for c in path["competencies"].values() for a in c["answers"]})
    if not days:
        return []
    start = date.fromisoformat(days[0])
    end = date.fromisoformat(upto or days[-1])
    pts: list[tuple[str, float]] = []
    d = start
    while d <= end:
        pts.append((d.isoformat(), progress(summarize(cur, path, d.isoformat()))["pct"]))
        d += timedelta(days=step)
    if pts[-1][0] != end.isoformat():
        pts.append((end.isoformat(), progress(summarize(cur, path, end.isoformat()))["pct"]))
    return pts


def eta_days(cur: dict, path: dict, as_of: str, window: int = 14) -> int | None:
    """Days until every core is consolidated, at the pace of the last `window` days."""
    now = progress(summarize(cur, path, as_of))["pct"]
    if now >= 100.0:
        return 0
    before_day = (date.fromisoformat(as_of) - timedelta(days=window)).isoformat()
    before = progress(summarize(cur, path, before_day))["pct"]
    rate = (now - before) / window
    if rate <= 0:
        return None
    return int(round((100.0 - now) / rate))


# ---- text views ---------------------------------------------------------------

def bar(pct: float, width: int = 20) -> str:
    filled = int(round(max(0.0, min(100.0, pct)) / 100.0 * width))
    return "█" * filled + "░" * (width - filled)


def cells(state: str) -> str:
    n = STATES.index(state)
    return "■" * n + "□" * (4 - n)


def spark(values: list[float]) -> str:
    chars = " ▁▂▃▄▅▆▇█"
    return "".join(chars[min(8, int(round(v / 100.0 * 8)))] for v in values)


def _day_number(path: dict, as_of: str) -> int:
    days = [a[0] for c in path["competencies"].values() for a in c["answers"]]
    return (date.fromisoformat(as_of) - date.fromisoformat(min(days))).days + 1 if days else 0


def path_view(cur: dict, path: dict, as_of: str, cfg: dict = CFG, data_dir=None, stem: str | None = None,
              root=None) -> dict:
    """Everything the web needs to draw the learner's path, in one JSON-able dict.

    The learner part is deliberately plain (bar, %, state in words, what is being worked on);
    what could discourage (stalled, forgotten, per-competence accuracy) is under `admin`."""
    rows = summarize(cur, path, as_of, cfg)
    pr = progress(rows)
    m = cur["meta"]
    by_id = {c["id"]: c for c in cur["competencies"]}
    left = (bank_mod.bank_left(Path(root or Path(__file__).resolve().parent.parent), stem, data_dir)
            if data_dir and stem else {})
    promo = path["promotions"][-1] if path.get("promotions") else None
    pending = [r for r in rows if r["core"] and STATES.index(r["state"]) < 2]
    sections: list[dict] = []
    for r in rows:
        if not sections or sections[-1]["name"] != r["section"]:
            sections.append({"name": r["section"], "items": []})
        sections[-1]["items"].append({
            "id": r["id"], "name": r["name"], "core": r["core"], "state": r["state"], "label": LABEL[r["state"]],
            "n": r["n"], "need": r["need"], "depth": r["depth"], "resting": bool(r.get("resting_today")),
            "pct": r.get("display_pct"),
            # Only the fact that it is running low, never the count: this is the
            # learner's view (subtle, Albert 2026-09-24). The numbers are in admin.
            "bank_low": bool(left.get(r["id"])) and left[r["id"]]["unseen"] <= bank_mod.BANK_LOW,
        })
    now = [] if promo and path.get("carried") else active_competences(rows, path, cfg)
    due = due_maintenance(cur, path, as_of, cfg)
    view = {
        "available": True,
        "language": m.get("language", ""), "level": m.get("level", ""),
        "day": _day_number(path, as_of), "as_of": as_of,
        "pct": round(pr["pct"], 1), "core_done": pr["core_done"], "core_total": pr["core_total"],
        "in_progress": pr["in_progress"], "unseen": pr["unseen"], "mastered": pr["core_mastered"],
        "promotion": ({"achieved": promo["achieved"], "date": promo["date"], "carried": len(promo["carried"])} if promo else None),
        "checkpoint": ("promoted" if promo else "ready" if checkpoint_ready(rows, cfg, cur) else "pending"),
        "checkpoint_pending": len(pending),
        "now": [{"id": c, "name": by_id[c]["name"]} for c in now],
        "review": [{"id": c, "name": by_id[c]["name"]} for c in due],
        "sections": sections,
    }
    if data_dir:
        view["checkpoint_run"] = checkpoint_status(data_dir)
        view["checkpoint_wait_until"] = checkpoint_wait_until(path, cfg)
        lang = m.get("language", "")
        view["certified"] = [{"level": c.get("level"), "date": c.get("date"), "pct": c.get("pct"), "type": c.get("type")}
                             for c in load_certificates(data_dir) if str(c.get("language", "")).lower() == str(lang).lower()]
        pend = pending_notices(data_dir)
        view["notice"] = pend[0] if pend else None
    flags = []
    for r in rows:
        if r["stalled"]:
            flags.append(f"Estancada: {r['name']} ({r['n']} respostes, {100 * (r['acc_recent'] or 0):.0f}% últimes)")
        if _done(r) and r["last_day"] and (date.fromisoformat(as_of) - date.fromisoformat(r["last_day"])).days > cfg["forgotten_days"]:
            flags.append(f"Oblidada? {r['name']}: sense veure des del {r['last_day']}")
    h = history(cur, path, 7, as_of)
    eta = eta_days(cur, path, as_of)
    view["admin"] = {
        "history": [{"day": d, "pct": round(v, 1)} for d, v in h],
        "eta_days": eta,
        "alerts": flags,
        "rows": [{"name": r["name"], "state": LABEL[r["state"]], "n": r["n"], "need": r["need"],
                  "acc_all": None if r["acc_all"] is None else round(100 * r["acc_all"]),
                  "acc_recent": None if r["acc_recent"] is None else round(100 * r["acc_recent"]),
                  "last_day": r["last_day"], "weight": r["weight"], "depth": r["depth"],
                  "bank_unseen": (left.get(r["id"]) or {}).get("unseen"),
                  "bank_total": (left.get(r["id"]) or {}).get("total")} for r in rows],
        "bank_low_at": bank_mod.BANK_LOW,
        "checkpoints": [{"date": c.get("date"), "pct": c.get("pct"), "result": c.get("result")}
                        for c in path.get("checkpoints", [])],
    }
    return view


def render_report(cur: dict, path: dict, as_of: str, admin: bool = False, cfg: dict = CFG) -> str:
    rows = summarize(cur, path, as_of, cfg)
    pr = progress(rows)
    m = cur["meta"]
    out: list[str] = []
    title = f"{m.get('language', '')} {m.get('level', '')}"
    out.append(f"{title} · dia {_day_number(path, as_of)} · {as_of}")
    out.append(
        f"{m.get('level', '')}  {bar(pr['pct'])} {pr['pct']:4.0f}%   "
        f"assolides {pr['core_done']}/{pr['core_total']} · en curs {pr['in_progress']} · per començar {pr['unseen']}"
    )
    if path.get("promotions"):
        p = path["promotions"][-1]
        extra = f" (arrossega {len(p['carried'])} competències)" if p["carried"] else ""
        out.append(f"Nivell {p['achieved']} assolit el {p['date']}{extra}")
    else:
        pending = [r for r in rows if r["core"] and STATES.index(r["state"]) < 2]
        if checkpoint_ready(rows, cfg, cur):
            last = last_checkpoint_day(path)
            out.append("Checkpoint: llest" + (f" (últim: {last})" if last else ""))
        else:
            out.append(f"Checkpoint: encara no (falten {len(pending)} competències per arribar a «en pràctica»)")
    if path.get("promotions") and path.get("carried"):
        out.append("Reforç: " + " · ".join(c.split(".", 1)[-1] for c in path["carried"]))
    else:
        now = active_competences(rows, path, cfg)
        if now:
            out.append("Ara: " + " · ".join(c.split(".", 1)[-1] for c in now))
    by_id = {r["id"]: r for r in rows}
    section = None
    for r in rows:
        if r["section"] != section:
            section = r["section"]
            out.append("")
            out.append(section.upper())
        tag = "" if r["core"] else " (extra)"
        acc = f"{100 * r['acc_recent']:3.0f}%" if r["acc_recent"] is not None else "  - "
        rest = "  ⏸ avui" if r.get("resting_today") else ""
        out.append(f"  {cells(r['state'])} {r['id'].split('.', 1)[-1][:34]:<34}{tag:<8} {LABEL[r['state']]:<12} {r['n']:>3}/{r['need']:<2} resp {acc}{rest}")
    if not admin:
        return "\n".join(out)

    out.append("")
    out.append("── ADMIN ──────────────────────────────────────────────")
    h = history(cur, path, 7, as_of)
    if h:
        out.append("Evolució setmanal: " + spark([v for _, v in h]) + "  " +
                   " → ".join(f"{v:.0f}%" for _, v in h))
    eta = eta_days(cur, path, as_of)
    out.append("ETA a totes les core consolidades: " + (f"~{eta} dies" if eta is not None else "no calculable (sense ritme)"))
    out.append(f"Dominades (core): {pr['core_mastered']}")
    flags = []
    for r in rows:
        if r["stalled"]:
            flags.append(f"ESTANCADA {r['id']}: {r['n']} respostes, {100 * (r['acc_recent'] or 0):.0f}% últimes")
        if _done(r) and r["last_day"] and (date.fromisoformat(as_of) - date.fromisoformat(r["last_day"])).days > cfg["forgotten_days"]:
            flags.append(f"OBLIDADA? {r['id']}: sense veure des del {r['last_day']}")
    out.append("Alertes: " + ("cap" if not flags else ""))
    out.extend(f"  · {f}" for f in flags)
    out.append("")
    out.append(f"{'competència':<34} {'estat':<12} {'resp':>4} {'%tot':>5} {'%últ':>5} {'fa':>4}")
    for r in rows:
        ago = (date.fromisoformat(as_of) - date.fromisoformat(r["last_day"])).days if r["last_day"] else None
        out.append(
            f"{r['id'].split('.', 1)[-1][:34]:<34} {LABEL[r['state']]:<12} {r['n']:>4} "
            f"{'' if r['acc_all'] is None else format(100 * r['acc_all'], '.0f') + '%':>5} "
            f"{'' if r['acc_recent'] is None else format(100 * r['acc_recent'], '.0f') + '%':>5} "
            f"{'' if ago is None else str(ago) + 'd':>4}"
        )
    if path.get("checkpoints"):
        out.append("")
        out.append("Checkpoints:")
        for c in path["checkpoints"]:
            weak = ", ".join(w.split(".", 1)[-1] for w in c["weak"]) or "-"
            out.append(f"  {c['date']}  {c['correct']}/{c['items']} = {c['pct']:.0f}%  → {c['result']}   fallades: {weak}")
    return "\n".join(out)


# ---- CLI ---------------------------------------------------------------------

# ---- 🎓 Review on the bank (PLA-EXERCICIS-TANCATS.md, fase 4) --------------------
#
# Review stops asking the model to invent an exercise for each due queue item.
# Every exercise is a bank item; what changes is WHICH one:
#   1. a queue item that IS a bank item (failed before)   -> that item
#   2. an old error pattern of the queue ("tenses_go")    -> an item of its competence,
#      only when the mapping is safe (Albert, 2026-09-24: option C); the rest retire
#   3. queue empty but the lesson is not done             -> the competence next_target picks
# Retiring is not deleting: the item keeps its history, gets `retired` with the
# reason, and a due date that never comes.

RETIRED_DUE = "9999-12-31"


def _pattern_record(item_id: str, sr_item: dict, pattern: dict | None) -> dict:
    """A queue item seen as a record, so competency_of() can place it."""
    pattern = pattern or {}
    ex = (pattern.get("examples") or [{}])[-1] or {}
    cat = str(pattern.get("category") or "").strip().lower()
    return {
        "item_id": item_id,
        "skill": "vocabulary" if item_id.startswith("vocabulary_") or cat == "vocabulary" else "grammar",
        "exercise": str(sr_item.get("content") or ""),
        "learner_answer": str(ex.get("incorrect") or ""),
        "corrections": [{"wrong": str(ex.get("incorrect") or ""), "right": str(ex.get("correct") or sr_item.get("content") or ""),
                         "category": cat}],
    }


def legacy_competence(cur: dict, item_id: str, sr_item: dict, pattern: dict | None = None) -> tuple[str | None, str, bool]:
    """(competence, how, safe) for an old error pattern in the review queue.

    Safe — the only ones Review turns into a bank exercise — is:
      * vocabulary: the word itself is in a competence's `Words:` list;
      * grammar: its category belongs to exactly one competence, or the tag
        words point to exactly ONE competence among those of its category.
    A tie, no category, or a tag match outside the category is a guess, and a
    guess sends her to practise a neighbouring competence instead of her own
    mistake ("Go_right_and_then_tu" -> subject_pronouns, measured on nes-en).
    """
    rec = _pattern_record(item_id, sr_item, pattern)
    cid, how = competency_of(cur, rec)
    if not cid:
        return None, how, False
    if how in ("words", "category", "record"):
        return cid, how, True
    if how != "tags":
        return cid, how, False
    cat = _record_category(rec)
    if not cat:
        return cid, "tags-without-category", False
    grammar = [c for c in cur["competencies"] if c["tags"] and f"#{cat}" in c["tags"]]
    pool = " ".join([rec["exercise"], rec["learner_answer"], item_id.replace("_", " "),
                     *[f"{c['wrong']} {c['right']}" for c in rec["corrections"]]]).lower()
    scores = [sum(1 for tg in c["tags"] if not tg.startswith("#") and tg not in _GENERIC_TAGS and _words_in(pool, tg))
              for c in grammar]
    best = max(scores, default=0)
    if not (best > 0 and scores.count(best) == 1):
        return cid, "tags-tie", False
    # And at least one matching word must belong to this competence ALONE, in
    # the whole curriculum: "don't" is an imperatives tag, but also present
    # simple's, so "word_order_don't_like" landing on imperatives is a guess.
    winner = grammar[scores.index(best)]
    others = {tg for c in cur["competencies"] if c["id"] != winner["id"] for tg in c["tags"]}
    own = [tg for tg in winner["tags"] if not tg.startswith("#") and tg not in _GENERIC_TAGS
           and _words_in(pool, tg) and tg not in others]
    return (winner["id"], "tags", True) if own else (winner["id"], "tags-shared", False)


def _bank_index(root: Path, stem: str, data_dir: str | os.PathLike | None = None) -> dict[str, dict]:
    """Every bank item of this curriculum (and of the learner's own extras), by id."""
    out: dict[str, dict] = {}
    for d in bank_mod.bank_dirs(root, stem, data_dir):
        for f in sorted(d.glob("*.json")):
            for it in bank_mod.load_bank(root, stem, f.stem, data_dir):
                out[it["id"]] = it
    return out


def review_pick(root: Path, cur: dict, stem: str, data_dir: str | os.PathLike, today: str,
                used: list[str] | tuple = (), last_id: str | None = None, dry_run: bool = False) -> dict:
    """The next Review exercise, from the bank. See the block comment above."""
    data_dir = Path(data_dir)
    sr_path = data_dir / "spaced-repetition.json"
    try:
        sr = json.loads(sr_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sr = {"items": {}}
    try:
        patterns = json.loads((data_dir / "mistakes-db.json").read_text(encoding="utf-8")).get("error_patterns", {})
    except (OSError, ValueError):
        patterns = {}
    index = _bank_index(root, stem, data_dir)
    items = sr.get("items") or {}
    due = sorted(((k, v) for k, v in items.items()
                  if isinstance(v, dict) and isinstance(v.get("due_date"), str) and v["due_date"] <= today
                  and not v.get("retired") and "{" not in k and k not in set(used)),
                 key=lambda kv: kv[1]["due_date"])
    retired: list[dict] = []
    choice = None
    for qid, it in due:
        if qid in index:
            item = index[qid]
            choice = {"source": "bank", "queue_id": qid, "competence": item["competence"], "item": item}
            break
        cid, how, safe = legacy_competence(cur, qid, it, patterns.get(qid))
        if safe and cid and bank_mod.has_bank(root, stem, cid, data_dir):
            item = bank_mod.pick_item(root, stem, cid, data_dir, today)
            if item:
                choice = {"source": "legacy", "queue_id": qid, "competence": cid, "how": how, "item": item}
                break
        reason = how if not safe else "no-bank"
        retired.append({"id": qid, "reason": reason, "guess": cid})
        if not dry_run:
            it["retired"] = {"date": today, "reason": reason, "guess": cid, "was_due": it.get("due_date")}
            it["due_date"] = RETIRED_DUE
    if retired and not dry_run:
        try:
            from db_lock import data_lock  # noqa: E402
            with data_lock(data_dir):
                fresh = json.loads(sr_path.read_text(encoding="utf-8"))
                for r in retired:
                    if r["id"] in fresh.get("items", {}):
                        fresh["items"][r["id"]].update({k: items[r["id"]][k] for k in ("retired", "due_date")})
                sr_path.write_text(json.dumps(fresh, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as e:  # never cost the learner the turn
            print(f"[Fluent] review_pick: could not retire {len(retired)} item(s): {e}", file=sys.stderr)
    if choice is None:
        t = next_target(cur, data_dir, today, last_id)
        cid = t.get("id")
        if cid and bank_mod.has_bank(root, stem, cid, data_dir):
            item = bank_mod.pick_item(root, stem, cid, data_dir, today)
            if item:
                choice = {"source": "weak", "queue_id": None, "competence": cid, "item": item}
    comp = next((c for c in cur["competencies"] if choice and c["id"] == choice["competence"]), None)
    out = {"available": choice is not None, "retired": retired}
    if choice:
        out.update(choice)
        out["competence_name"] = comp["name"] if comp else choice["competence"]
        out["depth"] = (comp or {}).get("depth") or "normal"
        out["vocab"] = bool((comp or {}).get("words"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("report", help="text report of the learner path")
    rp.add_argument("--curriculum", required=True)
    rp.add_argument("--data", default=os.environ.get("FLOWED_DATA_DIR", "data"))
    rp.add_argument("--admin", action="store_true")
    rp.add_argument("--today", default=date.today().isoformat())
    rp.add_argument("--rebuild", action="store_true", help="rebuild learner-path.json from the records first")
    bp = sub.add_parser("rebuild", help="rebuild learner-path.json from the recorded answers")
    bp.add_argument("--data", default=os.environ.get("FLOWED_DATA_DIR", "data"))
    bp.add_argument("--curriculum", default="")
    bp.add_argument("--auto", action="store_true", help="pick the curriculum from the profile (or $FLOWED_CURRICULUM); do nothing if none")
    bp.add_argument("--quiet", action="store_true")
    np_ = sub.add_parser("next", help="JSON: the competence the next free-practice exercise should be about")
    np_.add_argument("--data", default=os.environ.get("FLOWED_DATA_DIR", "data"))
    np_.add_argument("--curriculum", default="")
    np_.add_argument("--auto", action="store_true")
    np_.add_argument("--last", default="", help="id of the competence asked last")
    np_.add_argument("--today", default=date.today().isoformat())
    np_.add_argument("--vocab", action="store_true", help="only competences with words (Vocabulary practice)")
    np_.add_argument("--writing", action="store_true",
                     help="the structure a Writing task should use (read-only frame, not an exercise)")
    jp = sub.add_parser("json", help="the learner's path as JSON, for the web (nothing available -> {\"available\": false})")
    jp.add_argument("--data", default=os.environ.get("FLOWED_DATA_DIR", "data"))
    jp.add_argument("--curriculum", default="")
    jp.add_argument("--auto", action="store_true")
    jp.add_argument("--today", default=date.today().isoformat())
    clp = sub.add_parser("close", help="certify and close the CURRENT course by hand (teacher / tests): archive, certificate, next course")
    clp.add_argument("--data", default=os.environ.get("FLOWED_DATA_DIR", "data"))
    clp.add_argument("--curriculum", default="")
    clp.add_argument("--auto", action="store_true")
    clp.add_argument("--day", default=date.today().isoformat())
    ck = sub.add_parser("checkpoint", help="the level test: start | answer | status (JSON out)")
    ck.add_argument("action", choices=("start", "answer", "status"))
    ck.add_argument("--data", default=os.environ.get("FLOWED_DATA_DIR", "data"))
    ck.add_argument("--auto", action="store_true")
    ck.add_argument("--curriculum", default="")
    ck.add_argument("--today", default=date.today().isoformat())
    ck.add_argument("--text", default="")
    ck.add_argument("--force", action="store_true", help="teacher: open the test even if the learner is not ready")
    nq = sub.add_parser("notice", help="JSON: the course notices the learner has not seen yet; --seen marks them seen")
    nq.add_argument("--data", default=os.environ.get("FLOWED_DATA_DIR", "data"))
    nq.add_argument("--seen", action="store_true")
    cp = sub.add_parser("coverage", help="how many recorded answers could be assigned to a competence, and why not")
    cp.add_argument("--data", default=os.environ.get("FLOWED_DATA_DIR", "data"))
    cp.add_argument("--curriculum", required=True)
    vp = sub.add_parser("validate", help="check a curriculum file")
    vp.add_argument("--curriculum", required=True)
    bkp = sub.add_parser("bank", help="offline exercise bank: pick | answer (JSON out)")
    bkp.add_argument("action", choices=("pick", "answer", "review-pick"))
    bkp.add_argument("--competence", default="")
    bkp.add_argument("--used", default="", help="review-pick: queue ids already used this session, comma-separated")
    bkp.add_argument("--last", default="", help="review-pick: competence asked last")
    bkp.add_argument("--dry-run", action="store_true", help="review-pick: retire nothing, just say what would happen")
    bkp.add_argument("--data", default=os.environ.get("FLOWED_DATA_DIR", "data"))
    bkp.add_argument("--curriculum", default="")
    bkp.add_argument("--auto", action="store_true")
    bkp.add_argument("--today", default=date.today().isoformat())
    bkp.add_argument("--item-id", default="", help="required for action=answer")
    bkp.add_argument("--answer", default="", help="the learner's raw text; required for action=answer")
    a = ap.parse_args(argv)
    if a.cmd == "rebuild":
        root = Path(__file__).resolve().parent.parent
        f = Path(a.curriculum) if a.curriculum else (find_curriculum(root, a.data) if a.auto else None)
        if not f:
            if not a.auto:
                print("cal --curriculum o --auto", file=sys.stderr)
                return 2
            return 0
        path = rebuild_path(a.data, load_curriculum(f, a.data))
        if not a.quiet:
            tg = path["tagging"]
            print(f"{f.name}: {tg['records']} respostes registrades, {tg['tagged']} assignades a una competència")
        return 0
    if a.cmd == "json":
        root = Path(__file__).resolve().parent.parent
        f = Path(a.curriculum) if a.curriculum else (find_curriculum(root, a.data) if a.auto else None)
        if not f:
            print(json.dumps({"available": False}))
            return 0
        cur_ = load_curriculum(f, a.data)
        print(json.dumps(path_view(cur_, rebuild_path(a.data, cur_, save=False), a.today, data_dir=a.data,
                                   stem=f.stem, root=root), ensure_ascii=False))
        return 0
    if a.cmd == "checkpoint":
        root = Path(__file__).resolve().parent.parent
        if a.action == "status":
            print(json.dumps(checkpoint_status(a.data)))
            return 0
        f = Path(a.curriculum) if a.curriculum else (find_curriculum(root, a.data) if a.auto else None)
        if not f:
            print(json.dumps({"ok": False, "text": "No curriculum for this learner."}))
            return 0
        cur_ = load_curriculum(f, a.data)
        if a.action == "start":
            out = checkpoint_start(a.data, cur_, a.today, force=a.force, stem=f.stem, root=root)
        else:
            out = checkpoint_answer(a.data, cur_, a.today, a.text, root=root)
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if a.cmd == "bank":
        root = Path(__file__).resolve().parent.parent
        f = Path(a.curriculum) if a.curriculum else (find_curriculum(root, a.data) if a.auto else None)
        cur_ = load_curriculum(f, a.data) if f else None
        stem = f.stem if f else ""
        comp = next((c for c in (cur_["competencies"] if cur_ else []) if c["id"] == a.competence), None)
        if a.action == "review-pick":
            if not cur_:
                print(json.dumps({"available": False, "error": "no curriculum"}))
                return 0
            used = [u for u in a.used.split(",") if u]
            print(json.dumps(review_pick(root, cur_, stem, a.data, a.today, used, a.last or None, a.dry_run),
                             ensure_ascii=False))
            return 0
        if not a.competence:
            print(json.dumps({"error": "--competence required"}))
            return 2
        if a.action == "pick":
            item = bank_mod.pick_item(root, stem, a.competence, a.data, a.today) if stem else None
            out = {"available": item is not None, "item": item}
            if item and comp:
                out["competence_name"] = comp["name"]
                out["depth"] = comp.get("depth", "normal")
            print(json.dumps(out, ensure_ascii=False))
            return 0
        if not a.item_id:
            print(json.dumps({"error": "--item-id required for action=answer"}))
            return 2
        out = bank_mod.answer_and_record(root, stem, a.item_id, a.competence, a.answer, a.data, a.today, comp)
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if a.cmd == "notice":
        if a.seen:
            print(json.dumps({"marked": mark_notices_seen(a.data)}))
        else:
            print(json.dumps(pending_notices(a.data), ensure_ascii=False))
        return 0
    if a.cmd == "close":
        root = Path(__file__).resolve().parent.parent
        f = Path(a.curriculum) if a.curriculum else (find_curriculum(root, a.data) if a.auto else None)
        if not f:
            print(json.dumps({"error": "no curriculum"}))
            return 2
        cur_ = load_curriculum(f, a.data)
        rebuild_path(a.data, cur_)
        print(json.dumps(close_course(a.data, cur_, a.day, root=root, kind="manual"), ensure_ascii=False))
        return 0
    if a.cmd == "next":
        root = Path(__file__).resolve().parent.parent
        f = Path(a.curriculum) if a.curriculum else (find_curriculum(root, a.data) if a.auto else None)
        if a.writing:
            print(json.dumps(writing_frame(load_curriculum(f, a.data), a.data, a.today) if f else {}, ensure_ascii=False))
        else:
            print(json.dumps(next_target(load_curriculum(f, a.data), a.data, a.today, a.last or None, only_vocab=a.vocab) if f else {}, ensure_ascii=False))
        return 0
    cur = load_curriculum(a.curriculum)
    if a.cmd == "coverage":
        path = rebuild_path(a.data, cur, save=False)
        tg = path["tagging"]
        pct = 100.0 * tg["tagged"] / tg["records"] if tg["records"] else 0.0
        print(f"{tg['records']} respostes · {tg['tagged']} assignades ({pct:.0f}%)")
        for why, n in sorted(tg["how"].items(), key=lambda kv: -kv[1]):
            ex = ", ".join(tg["untagged_samples"].get(why, []))
            print(f"  {why:<28} {n:>5}" + (f"   p. ex.: {ex}" if ex else ""))
        return 0
    if a.cmd == "validate":
        problems = validate_curriculum(cur)
        n_core = sum(1 for c in cur["competencies"] if c["core"])
        print(f"{len(cur['competencies'])} competències ({n_core} core)")
        for p in problems:
            print("  ✗", p)
        return 1 if problems else 0
    path = rebuild_path(a.data, cur) if getattr(a, "rebuild", False) else load_path(a.data, cur)
    print(render_report(cur, path, a.today, admin=a.admin))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main())
