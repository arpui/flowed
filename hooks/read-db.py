#!/usr/bin/env python3
"""
FlowMath DB Reader Script
Loads the 6 learning databases and outputs a JSON object to stdout.

Usage:
    python3 hooks/read-db.py            # compact summary (default)
    python3 hooks/read-db.py --full     # complete databases (setup/debug)

Compact mode keeps the context small: learner essentials, due review items
(with content/answer, so reviews can run without re-reading files), the top
weak error patterns, mastery levels and overall stats.

Exit codes: 0=success, 1=partial (some files missing), 2=critical error
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from main_paths import data_dir, force_utf8_io  # noqa: E402
from db_schema import CURRENT_SCHEMA_VERSION, get_schema_version, decay_config  # noqa: E402
from domain import domain_for_profile  # noqa: E402 (WP5.2 domain adapter)

force_utf8_io()
DATA_DIR = data_dir()

FILES = {
    "learner_profile": DATA_DIR / "learner-profile.json",
    "progress_db": DATA_DIR / "progress-db.json",
    "mistakes_db": DATA_DIR / "mistakes-db.json",
    "mastery_db": DATA_DIR / "mastery-db.json",
    "spaced_repetition": DATA_DIR / "spaced-repetition.json",
    "session_log": DATA_DIR / "session-log.json",
}

HEALED_MASTERY = 4  # mastery at or above this = fixed, stop drilling it
TOP_WEAK_PATTERNS = 5
REVIEW_ITEMS_PROMPT_CAP = 20  # matches server/src/pacing.ts REVIEW_DAILY_LIMIT_DEFAULT

PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
RANK_PRIORITY = {v: k for k, v in PRIORITY_RANK.items()}
OVERDUE_BOOST_DAYS = 14


def load_json(path: Path, errors: list):
    """Load one DB file. Missing -> None; unreadable/corrupt -> None + note."""
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Fluent] ⚠️ Could not read {path}: {e}", file=sys.stderr)
        errors.append(f"Unreadable file: {path} ({e.__class__.__name__})")
        return None


def days_between(date_str, today: str):
    """Whole days from `date_str` to `today` (both YYYY-MM-DD), or None."""
    if not date_str:
        return None
    try:
        then = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        reference = datetime.strptime(str(today)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    return (reference - then).days


def next_session_id(sessions: list) -> str:
    """Produce 'session-NNN' matching existing id convention.
    Falls back to 'session-001' on empty log or unparseable last id."""
    if not sessions:
        return "session-001"
    # Find the highest session number across ALL entries (handles duplicates)
    max_num = 0
    for s in sessions:
        last_id = s.get("session_id", "")
        m = re.search(r'(\d+)', last_id)
        if m:
            max_num = max(max_num, int(m.group(1)))
    if max_num > 0:
        return f"session-{max_num + 1:03d}"
    return f"session-{len(sessions) + 1:03d}"


def days_overdue(due_date: str, today: str) -> int:
    try:
        return (datetime.strptime(today, "%Y-%m-%d")
                - datetime.strptime(due_date, "%Y-%m-%d")).days
    except (ValueError, TypeError):
        return 0


def effective_rank(item: dict, overdue: int) -> int:
    """Display-time priority: stored priority boosted by how overdue it is.

    Non-destructive: boosts the sort/presentation rank only — the stored
    ``priority`` and all SM-2 fields in the database are never modified here.
    """
    rank = PRIORITY_RANK.get(item.get("priority", "medium"), 2)
    return max(0, rank - overdue // OVERDUE_BOOST_DAYS)


def ranked_due_items(items: dict, today: str) -> list:
    """Due items sorted by effective priority (boosted by overdue days), then
    most-overdue first. Carries days_overdue/effective_priority for display."""
    due = []
    for iid, item in items.items():
        if item.get("due_date", "") > today:
            continue
        overdue = max(0, days_overdue(item.get("due_date"), today))
        rank = effective_rank(item, overdue)
        entry = {
            k: item.get(k) for k in (
                # `learner_wrote` matters for `error_pattern` items: it is the
                # only signal of WHAT the learner actually did wrong — the
                # expression she wrote (a dropped carry, a sign flipped, 51 for
                # 15) against the correct one. Dropped here, the review skill
                # saw a bare problem with no trace of the slip and built a
                # generic drill of the same expression instead of attacking the
                # mistake (seen live in the language fork, 2026-09-22, where the
                # same field distinguished a translation-direction card from a
                # same-language one).
                "id", "type", "content", "answer", "learner_wrote", "category",
                "difficulty", "priority",
            ) if item.get(k) is not None
        }
        entry.setdefault("id", iid)
        entry["days_overdue"] = overdue
        entry["effective_priority"] = RANK_PRIORITY[rank]
        due.append((rank, -overdue, entry))
    due.sort(key=lambda t: (t[0], t[1]))
    return [entry for _, _, entry in due]


def curriculum_progress(today: str) -> dict | None:
    """The active course's % from the curriculum path — the same number the web
    bar shows — or None where there is no curriculum for this profile/level.

    Without this, {progress}% in the greeting template had no real source: the
    tutor filled it in itself (measured live, 2026-09-22: a freshly reset,
    zero-record test-en profile greeted with "Level: A0 → A1 (65% progress)",
    a number invented out of nothing)."""
    try:
        root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(root / "hooks"))
        import curriculum as cu  # noqa: PLC0415
        cf = cu.find_curriculum(root, DATA_DIR)
        if cf is None:
            return None
        cur = cu.load_curriculum(cf, DATA_DIR)
        path = cu.rebuild_path(DATA_DIR, cur, save=False)
        rows = cu.summarize(cur, path, today)
        pr = cu.progress(rows)
        return {"level": cur["meta"].get("level"), "pct": round(pr["pct"], 1)}
    except Exception:
        return None


def steps_precision() -> dict | None:
    """WP4.1 — per-step precision and calculation fluency from the .records
    steps traces.

    The server files a `steps: [{n, ok, got, propagated?}]` trace on every
    steps record (agent.ts appendBankRecord, hooks/bank.py _grade_steps);
    until now nothing read it. Per step position `n` we keep the ok-rate over
    REAL attempts only — a `propagated` step is the error cascade after the
    first failure, not the learner's own try, so it stays out of both
    numerator and denominator. Fluency uses the v2 score scale (10 = every
    step right on the first try, 7 = one needed a second intent, 3 = a step
    had to be revealed); v1 whole-trace grading conflates a digit slip into
    the 7 band, which is acceptable for the pilot and documented here.
    Returns None when the learner has no steps records yet — the panel hides
    the section instead of showing zeros."""
    per_step: dict = {}
    items = first_try = retried = revealed = 0
    seen_ids = set()
    for path in sorted((DATA_DIR / ".records").glob("*.jsonl")):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(rec, dict) or rec.get("skill") != "steps":
                        continue
                    rid = rec.get("record_id")
                    if rid:
                        if rid in seen_ids:
                            continue
                        seen_ids.add(rid)
                    steps = rec.get("steps")
                    if not isinstance(steps, list):
                        continue
                    items += 1
                    try:
                        score = int(rec.get("score"))
                    except (TypeError, ValueError):
                        score = 0
                    if score >= 10:
                        first_try += 1
                    elif score >= 7:
                        retried += 1
                    else:
                        revealed += 1
                    for s in steps:
                        if not isinstance(s, dict) or s.get("propagated"):
                            continue
                        n = s.get("n")
                        if not isinstance(n, int) or isinstance(n, bool):
                            continue
                        cell = per_step.setdefault(n, [0, 0])
                        cell[0] += 1
                        cell[1] += 1 if s.get("ok") else 0
        except OSError:
            continue
    if not items:
        return None
    return {
        "items": items,
        "per_step": [
            {"n": n, "seen": seen, "ok_rate": round(100 * ok / seen, 1)}
            for n, (seen, ok) in sorted(per_step.items())
        ],
        "first_try_rate": round(100 * first_try / items, 1),
        "retry_rate": round(100 * retried / items, 1),
        "revealed_rate": round(100 * revealed / items, 1),
    }


def compact_databases(databases: dict, today: str) -> dict:
    """Build a small view of the 6 databases (see module docstring)."""
    out = {}
    out["curriculum"] = curriculum_progress(today)

    profile = databases.get("learner_profile", {})
    learner = profile.get("learner", {})
    skills = {
        k: {kk: v.get(kk) for kk in ("current_level", "confidence") if v.get(kk) is not None}
        for k, v in profile.get("skills", {}).items()
        if isinstance(v, dict)
    }
    out["learner_profile"] = {
        "learner": {k: learner.get(k) for k in (
            "name", "target_language", "native_language",
            "current_level", "target_level", "interests", "about",
        ) if learner.get(k) is not None},
        "preferences": {k: profile.get("preferences", {}).get(k) for k in (
            "tutor_style", "daily_goal", "session_length",
        ) if profile.get("preferences", {}).get(k) is not None},
        "current_streak_days": profile.get("current_streak_days"),
        "total_sessions": profile.get("total_sessions"),
        "focus_areas": profile.get("focus_areas", []),
        "skills": skills,
    }

    progress = databases.get("progress_db", {})
    out["progress_db"] = {
        "overall_stats": progress.get("overall_stats", {}),
        "skill_progress": {
            k: {kk: v.get(kk) for kk in (
                "exercises_completed", "correct_count", "incorrect_count",
            ) if v.get(kk) is not None}
            for k, v in progress.get("skill_progress", {}).items()
            if isinstance(v, dict)
        },
    }

    mastery = databases.get("mastery_db", {})
    out["mastery_db"] = {
        "skills": {
            k: {"mastery_level": v.get("mastery_level"), "avg_accuracy": v.get("avg_accuracy")}
            for k, v in mastery.get("skills", {}).items()
            if isinstance(v, dict)
        },
        "patterns": {
            k: {"mastery_level": v.get("mastery_level")}
            for k, v in mastery.get("patterns", {}).items()
            if isinstance(v, dict)
        },
    }

    mistakes = databases.get("mistakes_db", {})
    patterns = mistakes.get("error_patterns", {})
    # Errors have to be able to heal. Ranking by raw frequency meant a pattern
    # the learner fixed in April kept topping the list in September, simply
    # because it had been frequent once — and the second sort key was inert
    # (pattern mastery_level is never raised anywhere). So the weight halves
    # every `step_days` a pattern goes unseen: recent mistakes win, old ones
    # sink without being forgotten.
    decay_cfg = decay_config(profile.get("preferences") if isinstance(profile, dict) else None)
    half_life = max(1, int(decay_cfg.get("step_days", 21) or 21))

    def pattern_weight(p: dict) -> float:
        frequency = p.get("frequency", 0) or 0
        idle = days_between(p.get("last_seen") or p.get("last_occurred"), today)
        if idle is None:
            return float(frequency)
        return float(frequency) * (0.5 ** (max(0, idle) / half_life))

    # A pattern the learner has fixed is not a weak pattern. Until mastery was
    # wired up this filter had nothing to filter on (every pattern sat at 0 for
    # ever), so a word answered right three times kept being offered as one of
    # this learner's weakest points — and with an empty review queue that is
    # what the Lesson drills. Relapse lowers the level again and it comes back.
    healed = {pid for pid, p in patterns.items() if (p.get("mastery_level") or 0) >= HEALED_MASTERY}
    ranked = sorted(
        ((pid, p) for pid, p in patterns.items() if pid not in healed),
        key=lambda kv: (-pattern_weight(kv[1]), kv[1].get("mastery_level", 0)),
    )[:TOP_WEAK_PATTERNS]
    out["mistakes_db"] = {
        "total_patterns": len(patterns),
        "healed_patterns": len(healed),
        "top_weak_patterns": [],
    }
    for pid, p in ranked:
        examples = p.get("examples", [])
        last = examples[-1] if examples else {}
        out["mistakes_db"]["top_weak_patterns"].append({
            "id": pid,
            "category": p.get("category"),
            "frequency": p.get("frequency"),
            "mastery_level": p.get("mastery_level"),
            "last_seen": p.get("last_seen"),
            "days_since_seen": days_between(p.get("last_seen") or p.get("last_occurred"), today),
            "last_example": {
                k: last.get(k) for k in ("your_answer", "incorrect", "correct_answer", "correct")
                if last.get(k) is not None
            } or None,
        })

    sr = databases.get("spaced_repetition", {})
    items = sr.get("items", {})
    due = ranked_due_items(items, today)
    # Only ever a handful of these are used: the review skill sorts by
    # priority and caps at daily_limits.review_items_per_day (the server's
    # lessonPlan caps at the same number, or lower once the queue is smaller
    # than the limit). Dumping every due item regardless — measured live
    # 2026-09-24, nes-en: 41 due items embedded (content+answer each) while
    # the day's plan only ever worked through 14 of them — grows the system
    # prompt with the backlog, not with the session, and eats straight into
    # pruneHistory's budget: three context-full bounces in under an hour as
    # the queue grew through the day. `due_today_count` still reports the
    # true total for the "Items Due Today" banner; only the embedded bodies
    # are capped, already sorted best-first so nothing that would be picked
    # is dropped.
    daily_limits = sr.get("daily_limits", {})
    try:
        review_cap = int(daily_limits.get("review_items_per_day"))
        if review_cap <= 0:
            review_cap = REVIEW_ITEMS_PROMPT_CAP
    except (TypeError, ValueError):
        review_cap = REVIEW_ITEMS_PROMPT_CAP
    tomorrow = [
        item.get("id")
        for item in items.values()
        if item.get("due_date") == (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    ]
    out["spaced_repetition"] = {
        "total_items": len(items),
        "due_items": due[:review_cap],
        "due_today_count": len(due),
        "due_tomorrow_ids": tomorrow,
        "daily_limits": daily_limits,
    }

    log = databases.get("session_log", {})
    sessions = log.get("sessions", [])
    last_session = sessions[-1] if sessions else {}
    out["session_log"] = {
        "total_sessions": len(sessions),
        "last_session": {
            k: last_session.get(k) for k in (
                "session_id", "date", "skills_practiced", "exercises_completed",
                "accuracy", "focus_next_session",
            ) if last_session.get(k) is not None
        },
        "milestones": log.get("milestones", []),
    }

    return out


def main():
    full = "--full" in sys.argv[1:]

    databases = {}
    missing = []
    unreadable = []
    schema_warnings = []
    for key, path in FILES.items():
        data = load_json(path, unreadable)
        if data is None:
            if not any(str(path) in note for note in unreadable):
                missing.append(str(path))
            databases[key] = {}
        else:
            databases[key] = data
            version = get_schema_version(data)
            if version > CURRENT_SCHEMA_VERSION:
                schema_warnings.append(
                    f"{path.name}: schema v{version} is newer than supported "
                    f"v{CURRENT_SCHEMA_VERSION} — upgrade FlowMath or migrate before writing"
                )
            elif version < CURRENT_SCHEMA_VERSION:
                schema_warnings.append(
                    f"{path.name}: schema v{version} < v{CURRENT_SCHEMA_VERSION} — "
                    f"run python3 scripts/migrate-db.py"
                )

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    sr = databases.get("spaced_repetition", {})
    items = sr.get("items", {})
    due_items = [e["id"] for e in ranked_due_items(items, today) if e.get("id") is not None]

    log = databases.get("session_log", {})
    sessions = log.get("sessions", [])

    profile = databases.get("learner_profile", {})
    last_updated = profile.get("last_updated", "")
    streak_active = last_updated in (today, yesterday)
    try:
        days_since = (now - datetime.strptime(last_updated, "%Y-%m-%d")).days if last_updated else None
    except ValueError:
        days_since = None

    result = {
        "mode": "full" if full else "compact",
        "databases": databases if full else compact_databases(databases, today),
        "computed": {
            "today": today,
            "due_reviews_count": len(due_items),
            "due_review_items": due_items,
            "next_session_id": next_session_id(sessions),
            "streak_active": streak_active,
            "days_since_last_session": days_since,
            "steps_precision": steps_precision(),
            "domain": domain_for_profile(profile),
        },
    }
    if not full:
        result["_note"] = (
            "compact summary — for the complete databases run: "
            "python3 hooks/read-db.py --full"
        )

    warnings = schema_warnings + [f"Missing file: {m}" for m in missing] + unreadable
    if warnings:
        result["_warnings"] = warnings

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()

    sys.exit(1 if (missing or unreadable or schema_warnings) else 0)


if __name__ == "__main__":
    main()
