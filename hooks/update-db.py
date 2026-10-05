#!/usr/bin/env python3
"""
Fluent DB Update Script
Updates all 6 learning databases from a single JSON session report via stdin.

Usage:
    python3 hooks/update-db.py <<'EOF'
    { "session_id": "session-005", "date": "2026-04-24", ... }
    EOF

See docs/DB_SCRIPTS.md for the full input schema.

Exit codes: 0=success, 1=validation error, 2=blocking/data error
"""
import atexit
import copy
import json
import os
import re
import shutil
import sys
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from main_paths import ensure_data_dir, ensure_backups_dir, force_utf8_io  # noqa: E402
from db_schema import (CURRENT_SCHEMA_VERSION, get_schema_version,  # noqa: E402
                       decay_config, decayed_mastery)
from db_lock import data_lock  # noqa: E402

force_utf8_io()
DATA_DIR = ensure_data_dir()
BACKUP_DIR = ensure_backups_dir()

# --- Utility functions ---

def load_json(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    tmp_path = path.with_suffix('.json.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp_path), str(path))  # atomic + overwrites (os.rename fails on Windows if dest exists)


def parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def date_str(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def tomorrow(today_str: str) -> str:
    return date_str(parse_date(today_str) + timedelta(days=1))


def yesterday(today_str: str) -> str:
    return date_str(parse_date(today_str) - timedelta(days=1))


def date_plus_days(today_str: str, days: int) -> str:
    return date_str(parse_date(today_str) + timedelta(days=days))


def get_week_start(today_str: str) -> str:
    d = parse_date(today_str)
    monday = d - timedelta(days=d.weekday())
    return date_str(monday)


def normalize_milestones(session: dict) -> list:
    """Validate + canonicalize session['milestones'] in place.

    Accepts each entry as either a bare string or an object
    {"milestone": <required non-empty str>, "date": <optional YYYY-MM-DD>}.
    Returns a list of canonical dicts and rewrites session['milestones'] to it.

    Decisions: a milestone's own date is honored (falling back to the session
    date if missing/blank/unparseable); the authoritative top-level session_id
    always wins (any nested session_id is ignored). Malformed entries exit 1
    (validation error) before any DB is touched.

    Each canonical dict carries a private '_achievement_id' key used by
    update_learner_profile; it is harmless because `session` is never persisted
    (only the 6 DBs are written).
    """
    raw = session.get("milestones", [])
    if not raw:
        session["milestones"] = []
        return []
    if not isinstance(raw, list):
        print(f"[Fluent] Error: 'milestones' must be a list, got {type(raw).__name__}", file=sys.stderr)
        sys.exit(1)

    outer_date = session["date"]
    outer_sid = session["session_id"]
    normalized = []

    for i, ms in enumerate(raw):
        if isinstance(ms, str):
            text = ms.strip()
            if not text:
                print(f"[Fluent] Error: milestone at index {i} is an empty string", file=sys.stderr)
                sys.exit(1)
            when = outer_date
        elif isinstance(ms, dict):
            text = ms.get("milestone")
            if not isinstance(text, str) or not text.strip():
                print(f"[Fluent] Error: milestone at index {i} must have a non-empty string 'milestone' field", file=sys.stderr)
                sys.exit(1)
            text = text.strip()
            when = outer_date
            d = ms.get("date")
            if isinstance(d, str) and d.strip():
                try:
                    parse_date(d.strip())
                    when = d.strip()
                except (ValueError, TypeError):
                    when = outer_date  # malformed date falls back to session date
        else:
            print(f"[Fluent] Error: milestone at index {i} must be a string or object, got {type(ms).__name__}", file=sys.stderr)
            sys.exit(1)

        slug = re.sub(r'[^a-z0-9]+', '_', text[:30].lower()).strip('_') or "milestone"
        normalized.append({
            "date": when,
            "milestone": text,
            "session_id": outer_sid,
            "_achievement_id": f"session_{outer_sid}_{i}_{slug}",
        })

    session["milestones"] = normalized
    return normalized


def backup_all(tag: str):
    backup_path = BACKUP_DIR / tag
    backup_path.mkdir(parents=True, exist_ok=True)
    for f in DATA_DIR.glob("*.json"):
        shutil.copy2(f, backup_path / f.name)


# --- Idempotent re-application state -------------------------------------
# update-db.py may be called repeatedly with the SAME session_id as the
# session accumulates (per-answer persistence at session.idle). To avoid
# double-counting, we keep a per-session private snapshot of the 6 databases
# taken *before* the session's first application (state T0). Re-applying the
# same session_id restores T0 and re-applies the (now fuller) accumulated
# payload for that session_id — so the session's contribution is present
# exactly once, reflecting the latest payload.
#
# This lives in a private sidecar dir, NOT in the 6 learning databases, so
# the public schema stays clean. Each snapshot is immutable after the first
# application of its session.

STATE_DIR_NAME = ".update-state"


def state_path(session_id: str, day: str = "") -> Path:
    """The T0 file for a session, scoped to its DAY.

    The id here is a logical counter — "session-001", "session-002" — and it
    restarts whenever a profile is emptied. Keyed on that alone, a session today
    inherited the T0 of a session with the same number from another day, and
    re-applying it rolled the databases back to that older state. Measured on a
    real profile: twelve spaced-repetition items became two, because
    `.update-state/session-002.json` held a snapshot from the night before with
    one item in it.

    A T0 belongs to one run of one session on one day. The date makes the key
    say so, and an old file simply stops being found.
    """
    stem = f"{session_id}@{day}" if day else session_id
    return DATA_DIR / STATE_DIR_NAME / f"{stem}.json"


def save_state(session_id: str, databases: dict, day: str = ""):
    """Record the pre-session (T0) snapshot for a session_id (first apply)."""
    p = state_path(session_id, day)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(databases, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(p))


def load_state(session_id: str, day: str = ""):
    """Return the T0 snapshot for this session ON THIS DAY, or None.

    Deliberately does NOT fall back to the undated file: that fallback is the
    bug. A snapshot from another day is not this session's past.
    """
    p = state_path(session_id, day)
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# --- SM-2 Algorithm ---

def calculate_sm2(item: dict, quality: int) -> dict:
    """Classic SM-2. Uses round() for interval growth, matching the SSOT."""
    ef = item.get("easiness_factor", 2.5)
    interval = item.get("interval_days", 1)
    reps = item.get("repetitions", 0)

    if quality >= 3:
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = int(round(interval * ef))
        reps += 1
    else:
        reps = 0
        interval = 1

    ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ef = max(1.3, ef)

    return {
        "easiness_factor": round(ef, 2),
        "interval_days": interval,
        "repetitions": reps,
    }


# --- Updater functions ---
# Each mutates in place. Confidence in learner-profile is 0-100 int.
# Session-log preserves the existing rich schema (skills_practiced array,
# score_breakdown, topics_covered, breakthroughs, focus_next_session,
# achievements_earned). Spaced-repetition preserves consecutive_*,
# mastery_level, total_reviews, priority, content, answer, category,
# difficulty fields on existing items.

def update_learner_profile(profile: dict, session: dict, is_new_session: bool = True):
    today = session["date"]
    last = profile.get("last_updated", "")

    if last == today:
        pass
    elif last == yesterday(today):
        profile["current_streak_days"] = profile.get("current_streak_days", 0) + 1
    else:
        profile["current_streak_days"] = 1

    profile["last_updated"] = today
    if is_new_session:
        profile["total_sessions"] = profile.get("total_sessions", 0) + 1
        profile["total_study_minutes"] = profile.get("total_study_minutes", 0) + session.get("duration_minutes", 0)

    for skill, scores in session.get("skill_scores", {}).items():
        skills = profile.setdefault("skills", {})
        s = skills.setdefault(skill, {
            "current_level": 0, "confidence": 0,
            "last_practiced": None, "total_practice_time": 0,
        })
        s["last_practiced"] = today
        s["total_practice_time"] = s.get("total_practice_time", 0) + scores.get("time_minutes", 0)
        if scores.get("exercises", 0) > 0:
            # confidence is 0-100 int; EWMA against session accuracy (0-100)
            new_acc_pct = (scores["correct"] / scores["exercises"]) * 100
            old_conf = s.get("confidence", 0)
            s["confidence"] = round(old_conf * 0.7 + new_acc_pct * 0.3)
        s["current_level"] = max(s.get("current_level", 0), 1)

    if session.get("focus_areas"):
        profile["focus_areas"] = session["focus_areas"]

    for m in session.get("milestones", []):
        profile.setdefault("achievements", []).append({
            "id": m["_achievement_id"],
            "name": m["milestone"],
            "earned_date": m["date"],
            "description": m["milestone"],
        })


def update_progress_db(progress: dict, session: dict, is_new_session: bool = True):
    today = session["date"]
    skill_scores = session.get("skill_scores", {})
    total_ex = sum(s.get("exercises", 0) for s in skill_scores.values())
    total_cor = sum(s.get("correct", 0) for s in skill_scores.values())
    accuracy = round(total_cor / total_ex, 3) if total_ex > 0 else 0.0

    stats = progress.setdefault("overall_stats", {
        "total_sessions": 0, "total_exercises": 0, "total_correct": 0,
        "total_incorrect": 0, "accuracy_rate": 0.0,
        "total_study_minutes": 0, "average_session_duration": 0,
    })
    if is_new_session:
        stats["total_sessions"] = stats.get("total_sessions", 0) + 1
        stats["total_exercises"] = stats.get("total_exercises", 0) + total_ex
        stats["total_correct"] = stats.get("total_correct", 0) + total_cor
        stats["total_incorrect"] = stats.get("total_incorrect", 0) + (total_ex - total_cor)
        stats["total_study_minutes"] = stats.get("total_study_minutes", 0) + session.get("duration_minutes", 0)
    stats["accuracy_rate"] = round(stats["total_correct"] / stats["total_exercises"], 3) if stats["total_exercises"] > 0 else 0.0
    stats["average_session_duration"] = round(stats["total_study_minutes"] / stats["total_sessions"]) if stats.get("total_sessions", 0) > 0 else 0

    trend = progress.setdefault("accuracy_trend", [])
    # Dedup same-day entries: replace if present, else append
    existing = next((t for t in trend if t.get("date") == today), None)
    if existing is not None:
        existing["accuracy"] = accuracy
        existing["exercises"] = existing.get("exercises", 0) + total_ex
    else:
        trend.append({"date": today, "accuracy": accuracy, "exercises": total_ex})

    for skill, scores in skill_scores.items():
        sp = progress.setdefault("skill_progress", {}).setdefault(skill, {
            "sessions": 0, "accuracy": 0.0, "last_practiced": None,
            "exercises_completed": 0, "correct_count": 0, "incorrect_count": 0,
        })
        if is_new_session:
            old_sessions = sp.get("sessions", 0)
            sp["sessions"] = old_sessions + 1
            new_acc = scores["correct"] / scores["exercises"] if scores.get("exercises", 0) > 0 else 0.0
            sp["accuracy"] = round(
                (sp.get("accuracy", 0.0) * old_sessions + new_acc) / sp["sessions"], 3
            )
            sp["exercises_completed"] = sp.get("exercises_completed", 0) + scores.get("exercises", 0)
            sp["correct_count"] = sp.get("correct_count", 0) + scores.get("correct", 0)
            sp["incorrect_count"] = sp.get("incorrect_count", 0) + (scores.get("exercises", 0) - scores.get("correct", 0))
        sp["last_practiced"] = today

    week_start = get_week_start(today)
    weekly = progress.setdefault("weekly_summary", [])
    week_entry = next((w for w in weekly if w.get("week_start") == week_start), None)
    if week_entry is None:
        week_entry = {"week_start": week_start, "sessions": 0, "total_minutes": 0, "accuracy": 0.0}
        weekly.append(week_entry)

    if is_new_session:
        old_s = week_entry.get("sessions", 0)
        week_entry["sessions"] = old_s + 1
        week_entry["total_minutes"] = week_entry.get("total_minutes", 0) + session.get("duration_minutes", 0)
        week_entry["accuracy"] = round(
            (week_entry.get("accuracy", 0.0) * old_s + accuracy) / week_entry["sessions"], 3
        )

    progress.setdefault("metadata", {})["last_updated"] = today


def update_mistakes_db(mistakes: dict, session: dict, is_new_session: bool = True):
    today = session["date"]
    patterns = mistakes.setdefault("error_patterns", {})

    for error in session.get("errors", []):
        pid = error["pattern_id"]

        if pid in patterns:
            pat = patterns[pid]
            if is_new_session:
                pat["frequency"] = pat.get("frequency", 0) + 1
                pat.setdefault("examples", []).append({
                    "incorrect": error.get("your_answer", ""),
                    "correct": error.get("correct_answer", ""),
                    "context": error.get("context", ""),
                    "date": today,
                })
                pat["examples"] = pat["examples"][-5:]
            pat["last_seen"] = today
            pat["last_occurred"] = today  # legacy alias kept
            pat["next_review"] = tomorrow(today)
            if is_new_session:
                pat["consecutive_incorrect"] = pat.get("consecutive_incorrect", 0) + 1
                pat["consecutive_correct"] = 0
            if error.get("notes"):
                pat["notes"] = error["notes"]
        else:
            patterns[pid] = {
                "category": error.get("category", "other"),
                "subcategory": error.get("subcategory", ""),
                "description": error.get("description", ""),
                "severity": error.get("severity", "minor"),
                "frequency": 1,
                "mastery_level": 0,
                "difficulty_score": error.get("difficulty_score", 0.5),
                "last_seen": today,
                "last_occurred": today,
                "next_review": tomorrow(today),
                "consecutive_correct": 0,
                "consecutive_incorrect": 1,
                "examples": [{
                    "incorrect": error.get("your_answer", ""),
                    "correct": error.get("correct_answer", ""),
                    "context": error.get("context", ""),
                    "date": today,
                }],
                "notes": error.get("notes", ""),
            }

    mistakes.setdefault("metadata", {})["last_updated"] = today
    mistakes["metadata"]["total_patterns_tracked"] = len(patterns)


def update_mastery_db(mastery: dict, session: dict, progress: dict, is_new_session: bool = True,
                      decay_cfg: dict = None):
    today = session["date"]
    practised = set(session.get("skill_scores", {}))

    for skill, scores in session.get("skill_scores", {}).items():
        s = mastery.setdefault("skills", {}).setdefault(skill, {
            "mastery_level": 0, "confidence_score": 0.0,
            "total_practice_time": 0, "last_practiced": None,
            "practice_count": 0, "avg_accuracy": 0.0,
        })
        s["last_practiced"] = today
        if is_new_session:
            s["total_practice_time"] = s.get("total_practice_time", 0) + scores.get("time_minutes", 0)
            s["practice_count"] = s.get("practice_count", 0) + scores.get("exercises", 0)

        sp = progress.get("skill_progress", {}).get(skill, {})
        acc = sp.get("accuracy", 0)
        sessions = sp.get("sessions", 0)
        s["confidence_score"] = round(acc, 3)
        s["avg_accuracy"] = round(acc, 3)

        if sessions == 0:
            s["mastery_level"] = 0
        elif sessions < 3 or acc < 0.5:
            s["mastery_level"] = max(s.get("mastery_level", 0), 1)
        elif sessions < 5 or acc < 0.65:
            s["mastery_level"] = max(s.get("mastery_level", 0), 2)
        elif sessions < 10 or acc < 0.8:
            s["mastery_level"] = max(s.get("mastery_level", 0), 3)
        elif sessions < 20 or acc < 0.9:
            s["mastery_level"] = max(s.get("mastery_level", 0), 4)
        else:
            s["mastery_level"] = 5

        # What practice earned. Decay reads this, never its own output.
        s["mastery_level_earned"] = s["mastery_level"]

    # Skills NOT practised in this session lose height slowly. Absolute, so
    # re-applying the same session is a no-op (see decayed_mastery).
    for skill, s in mastery.get("skills", {}).items():
        if skill in practised or not isinstance(s, dict):
            continue
        earned = s.get("mastery_level_earned", s.get("mastery_level", 0))
        s["mastery_level_earned"] = earned
        last = s.get("last_practiced")
        if not last:
            continue
        try:
            days_idle = (parse_date(today) - parse_date(last)).days
        except (ValueError, TypeError):
            continue
        s["mastery_level"] = decayed_mastery(earned, days_idle, decay_cfg)
        s["days_since_practice"] = max(0, days_idle)

    mastery.setdefault("metadata", {})["last_updated"] = today


def heal_patterns(mistakes: dict, session: dict, today: str):
    """An error the learner has fixed has to stop being an error.

    `mistakes-db.error_patterns[].mastery_level` is what the tutor reads to
    decide what to drill (read-db ranks by it, and the Lesson fills the space
    the SM-2 queue leaves with it). Nothing in the whole system ever raised it.
    Measured over a simulated fortnight: three words answered correctly three
    times each, intervals growing 1 → 6 → 16 exactly as SM-2 should — and all
    three still sitting at `mastery_level: 0`, still offered as this learner's
    weakest points on day twelve. With an empty queue and a lesson of six, the
    tutor drills those same three words again. And again. Which, from the other
    side of the screen, is a tutor asking the same questions for ever.

    The SM-2 item and the pattern now share an id, so this is a plain join.
    """
    patterns = mistakes.setdefault("error_patterns", {})
    for review in session.get("review_results", []):
        pat = patterns.get(review.get("item_id"))
        if not isinstance(pat, dict):
            continue
        try:
            quality = int(review.get("quality", 0) or 0)
        except (TypeError, ValueError):
            quality = 0
        if quality >= 3:
            pat["consecutive_correct"] = pat.get("consecutive_correct", 0) + 1
            pat["consecutive_incorrect"] = 0
            # One step per clean review, and no streak reset. At these
            # intervals a second correct answer is already days after the
            # first, so each one is real evidence; resetting the streak on
            # every bump stretched "healed" out over months, and months is
            # exactly how long the tutor would go on drilling it.
            pat["mastery_level"] = min(5, (pat.get("mastery_level") or 0) + 1)
        else:
            pat["consecutive_incorrect"] = pat.get("consecutive_incorrect", 0) + 1
            pat["consecutive_correct"] = 0
            pat["mastery_level"] = max(0, (pat.get("mastery_level") or 0) - 1)
        pat["last_reviewed"] = today


MIN_TWIN_CHARS = 8


def _form(text) -> str:
    """The form of a correct answer with case, spacing and punctuation gone."""
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def find_twin(items: dict, error: dict):
    """The id of an existing error item for the SAME correct form, or None.

    Pattern ids are `category_first-20-chars-of-the-correct-form`, so one sentence
    gets a different id when the category drifts or when a capital differs from the
    id the first time it was created. Measured on a five-day run: the same
    "I speak English on Mondays" three times in one lesson, and 9 items due where 6
    were seeded. Short forms ("an", "the") are not merged: they are shared by many
    different exercises."""
    want = _form(error.get("correct_answer"))
    if len(want) < MIN_TWIN_CHARS:
        return None
    for iid, it in items.items():
        if not isinstance(it, dict) or it.get("type") != "error_pattern":
            continue
        if _form(it.get("answer") or it.get("content")) == want:
            return iid
    return None

_NATIVE_RE = re.compile(
    r"[\u00e0\u00e8\u00f2\u00ed\u00f3\u00fa\u00ef\u00fc\u00e7]"
    r"|\b(un|una|uns|unes|el|la|els|les|hi|ha|de|amb|per\u00f2|tinc|pomes?|taula|nens?|jugant|s\u00f3n)\b",
    re.I)


def _log_guard(note: str, head: str) -> None:
    """Same shape as server/src/agent.ts's logGuard: one line per event, next to
    the turn it belongs to, so the bench's existing guard count picks it up."""
    try:
        d = DATA_DIR / ".metrics"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "guards.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(datetime.now().timestamp() * 1000), "session": "update-db",
                                "note": note[:160], "head": head[:1500]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _language_check(error: dict) -> tuple[bool, str | None]:
    """(keep it, guard note or None). Two shapes measured live (2026-09-22, test-en):

    1. Nothing in {Target} anywhere \u2014 content/answer/learner_wrote all {Native}
       (`correct_answer: "Un"`, `your_answer: "Tinc un poma."`): the item teaches
       nothing about {Target}. Dropped, not filed.
    2. `correct_answer` in {Native} while `your_answer` is in {Target}
       (learner correctly wrote "There are children playing on the swings.",
       `correct_answer: "Hi ha nens jugant a les balduï\u00f1es."` \u2014 not even a
       real word): a {Native} "correction" the tutor invented cannot be checked here
       (no dictionary), so it is kept but flagged \u2014 Albert reads guards.jsonl for these.
    """
    content = str(error.get("correct_answer") or error.get("content") or "")
    answer = str(error.get("correct_answer") or "")
    wrote = str(error.get("your_answer") or "")
    native_answer = bool(_NATIVE_RE.search(answer))
    native_wrote = bool(_NATIVE_RE.search(wrote))
    if native_answer and (native_wrote or not wrote):
        return False, f"error_pattern dropped, no {{Target}} anywhere: correct_answer={answer!r} your_answer={wrote!r}"
    if native_answer and not native_wrote:
        return True, f"error_pattern correct_answer in {{Native}} while your_answer is in {{Target}} (unverified translation): correct_answer={answer!r} your_answer={wrote!r}"
    return True, None


def update_spaced_repetition(sr: dict, session: dict, is_new_session: bool = True):
    today = session["date"]
    items = sr.setdefault("items", {})

    wrong_item_ids = []
    for review in session.get("review_results", []):
        item_id = review["item_id"]
        quality = review["quality"]
        if item_id in items:
            item = items[item_id]
            result = calculate_sm2(item, quality)
            item["easiness_factor"] = result["easiness_factor"]
            item["interval_days"] = result["interval_days"]
            item["repetitions"] = result["repetitions"]
            item["due_date"] = date_plus_days(today, result["interval_days"])
            item["last_reviewed"] = today
            item["last_quality"] = quality
            if quality < 3:
                wrong_item_ids.append(item_id)
            if is_new_session:
                item["total_reviews"] = item.get("total_reviews", 0) + 1
            if quality >= 3:
                item["consecutive_correct"] = item.get("consecutive_correct", 0) + 1
                item["consecutive_incorrect"] = 0
            else:
                item["consecutive_incorrect"] = item.get("consecutive_incorrect", 0) + 1
                item["consecutive_correct"] = 0
            pre_wrong_streak = item.get("consecutive_incorrect", 0)
            if item.get("consecutive_correct", 0) >= 5:
                item["mastery_level"] = min(5, item.get("mastery_level", 0) + 1)
                item["consecutive_correct"] = 0
            elif item.get("consecutive_incorrect", 0) >= 3:
                item["mastery_level"] = max(0, item.get("mastery_level", 0) - 1)
                item["consecutive_incorrect"] = 0

            if quality < 3 or pre_wrong_streak >= 2:
                item["priority"] = "high"
            elif item.get("mastery_level", 0) >= 3:
                item["priority"] = "low"
            else:
                item["priority"] = item.get("priority", "medium")
            item.setdefault("review_history", []).append({
                "date": today,
                "quality": quality,
                "score": review.get("score", 0),
            })

    for vocab in session.get("new_vocabulary", []):
        item_id = vocab["item_id"]
        if item_id not in items:
            items[item_id] = {
                "id": item_id,
                "type": vocab.get("item_type", "vocabulary"),
                "content": vocab.get("content", ""),
                "answer": vocab.get("answer", ""),
                "category": vocab.get("category", ""),
                "difficulty": vocab.get("difficulty", ""),
                "created_date": today,
                "due_date": tomorrow(today),
                "interval_days": 1,
                "repetitions": 0,
                "easiness_factor": 2.5,
                "consecutive_correct": 0,
                "consecutive_incorrect": 0,
                "last_reviewed": today,
                "last_quality": vocab.get("initial_quality", 3),
                "mastery_level": 0,
                "total_reviews": 0,
                "priority": vocab.get("priority", "medium"),
            }
            # Optional enrichment fields: only stored when the payload provides
            # them, so sessions that omit them stay byte-identical to before.
            for opt in ("pos", "cefr_level", "forms"):
                if opt in vocab:
                    items[item_id][opt] = vocab[opt]

    for error in session.get("errors", []):
        keep, guard_note = _language_check(error)
        if guard_note:
            _log_guard(guard_note, json.dumps(error, ensure_ascii=False))
        if not keep:
            continue
        item_id = error["pattern_id"]
        if item_id not in items and find_twin(items, error) is not None:
            # The same sentence to learn under another id (the tutor called the
            # slip "grammar" this time and "capitalization" last time, or the id
            # differs by a capital). A second item would make the lesson ask it
            # twice in a row and count it once.
            continue
        if item_id not in items:
            items[item_id] = {
                "id": item_id,
                # `content` is what the item IS ABOUT, and it has to be the
                # correct form. It used to be `your_answer`, so the item a
                # learner had to study was their own mistake: content "ben",
                # and a tutor asking what the English for "ben" is. The slip
                # is kept separately, as context for building the exercise —
                # never as the exercise.
                "type": "error_pattern",
                "content": error.get("correct_answer", "") or error.get("your_answer", ""),
                "answer": error.get("correct_answer", ""),
                "learner_wrote": error.get("your_answer", ""),
                "category": error.get("category", ""),
                "difficulty": "",
                "created_date": today,
                "due_date": tomorrow(today),
                "interval_days": 1,
                "repetitions": 0,
                "easiness_factor": 2.5,
                "consecutive_correct": 0,
                "consecutive_incorrect": 1,
                "last_reviewed": today,
                "last_quality": 2,
                "mastery_level": 0,
                "total_reviews": 0,
                "priority": "high",
            }

    # Rebuild review queue
    sr["review_queue"] = {"today": [], "tomorrow": [], "this_week": [], "later": []}
    tom = tomorrow(today)
    week_end = date_plus_days(today, 7)
    for item_id, item in items.items():
        due = item.get("due_date", today)
        if due <= today:
            sr["review_queue"]["today"].append(item_id)
        elif due == tom:
            sr["review_queue"]["tomorrow"].append(item_id)
        elif due <= week_end:
            sr["review_queue"]["this_week"].append(item_id)
        else:
            sr["review_queue"]["later"].append(item_id)

    if wrong_item_ids:
        wrong_set = set(wrong_item_ids)
        today_ids = set(sr["review_queue"]["today"])
        moved = []
        for queue_name in ("tomorrow", "this_week", "later"):
            kept = []
            for rid in sr["review_queue"][queue_name]:
                if rid in wrong_set:
                    if rid not in today_ids and rid not in moved:
                        moved.append(rid)
                else:
                    kept.append(rid)
            sr["review_queue"][queue_name] = kept
        sr["review_queue"]["today"].extend(moved)

    sr.setdefault("metadata", {})["last_updated"] = today
    sr["metadata"]["total_items_tracked"] = len(items)


def update_session_log(log: dict, session: dict, streak: int):
    """Matches existing schema: skills_practiced (array), score_breakdown,
    topics_covered, breakthroughs, focus_next_session, achievements_earned."""
    today = session["date"]
    skill_scores = session.get("skill_scores", {})
    total_ex = sum(s.get("exercises", 0) for s in skill_scores.values())
    total_cor = sum(s.get("correct", 0) for s in skill_scores.values())

    score_breakdown = {
        skill: round(s["correct"] / s["exercises"], 3) if s.get("exercises", 0) > 0 else 0.0
        for skill, s in skill_scores.items()
    }

    entry = {
        "session_id": session["session_id"],
        "date": today,
        "duration_minutes": session.get("duration_minutes", 0),
        "skills_practiced": session.get("skills_practiced", list(skill_scores.keys())),
        "command_used": session.get("command_used", "/math-learn"),
        "exercises_completed": total_ex,
        "accuracy": round(total_cor / total_ex, 3) if total_ex > 0 else 0.0,
        "score_breakdown": score_breakdown,
        "topics_covered": session.get("topics_covered", []),
        "breakthroughs": session.get("breakthroughs", []),
        "focus_next_session": session.get("focus_next_session", session.get("focus_areas", [])),
        "notes": session.get("session_notes", ""),
        "achievements_earned": session.get("achievements_earned", []),
        "streak_day": streak,
    }
    if session.get("exam_focus"):
        entry["exam_focus"] = session["exam_focus"]
    if session.get("critical_errors_identified"):
        entry["critical_errors_identified"] = session["critical_errors_identified"]

    sessions = log.setdefault("sessions", [])
    # Dedup: replace existing entry with same session_id, else append
    sessions[:] = [s for s in sessions if s.get("session_id") != session["session_id"]]
    sessions.append(entry)

    for m in session.get("milestones", []):
        log.setdefault("milestones", []).append({
            "date": m["date"],
            "milestone": m["milestone"],
            "session_id": m["session_id"],
        })

    log.setdefault("metadata", {})["total_sessions"] = len(log["sessions"])


# --- Main ---

def main():
    try:
        session = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"[Fluent] Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    for field in ("session_id", "date"):
        if field not in session:
            print(f"[Fluent] Error: Missing required field '{field}'", file=sys.stderr)
            sys.exit(1)

    # Validate + canonicalize milestones before touching any DB (exits 1 on
    # malformed input, so disk stays untouched on a validation failure).
    normalize_milestones(session)

    session.setdefault("duration_minutes", 0)

    # Serialize read-modify-write cycles over the 6 DBs. The lock is advisory
    # (see db_lock.py) and held until process exit, so concurrent update-db.py
    # invocations (per-answer hook + idle sweeper + manual persist) can't lose
    # one another's changes.
    stack = ExitStack()
    try:
        stack.enter_context(data_lock(DATA_DIR))
    except TimeoutError as e:
        print(f"[Fluent] Error: database lock timeout: {e}", file=sys.stderr)
        sys.exit(2)
    atexit.register(stack.close)

    files = {
        "profile": DATA_DIR / "learner-profile.json",
        "progress": DATA_DIR / "progress-db.json",
        "mistakes": DATA_DIR / "mistakes-db.json",
        "mastery": DATA_DIR / "mastery-db.json",
        "sr": DATA_DIR / "spaced-repetition.json",
        "log": DATA_DIR / "session-log.json",
    }

    try:
        originals = {k: load_json(p) for k, p in files.items()}
    except Exception as e:
        import traceback
        print(f"[Fluent] Error loading databases: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)

    # Refuse to write over databases from a future schema version (this build
    # of Fluent doesn't understand their shape). read-db.py still warns+reads.
    for k, doc in originals.items():
        version = get_schema_version(doc)
        if version > CURRENT_SCHEMA_VERSION:
            print(f"[Fluent] Error: {k} ({files[k].name}) is schema v{version} > "
                  f"supported v{CURRENT_SCHEMA_VERSION}; upgrade Fluent before writing",
                  file=sys.stderr)
            sys.exit(2)
        if version < CURRENT_SCHEMA_VERSION:
            print(f"[Fluent] Error: {k} ({files[k].name}) is schema v{version} < "
                  f"v{CURRENT_SCHEMA_VERSION}; run python3 scripts/migrate-db.py before writing",
                  file=sys.stderr)
            sys.exit(2)

    sid = session["session_id"]
    # The day the session belongs to, not the day this script happens to run:
    # a sweeper finalising last night's session must find last night's T0.
    day = str(session.get("date") or "")
    reapply = load_state(sid, day)

    if reapply is not None:
        # Same session_id already applied before (accumulating). Restore the
        # true pre-session state (T0) so the fuller payload replaces, not adds.
        originals = {k: reapply[k] for k in files}
    else:
        # First application of this session_id: snapshot T0 so a later re-apply
        # can restore it. Never computed against a re-apply state.
        save_state(sid, originals, day)

    # Work on deep copies so a mid-run exception leaves disk untouched.
    data = {k: copy.deepcopy(v) for k, v in originals.items()}

    try:
        # Detect if this session_id is new (not yet in session-log)
        existing_sids = {s.get("session_id") for s in data["log"].get("sessions", [])}
        is_new = sid not in existing_sids
        update_learner_profile(data["profile"], session, is_new)
        update_progress_db(data["progress"], session, is_new)
        update_mistakes_db(data["mistakes"], session, is_new)
        update_mastery_db(data["mastery"], session, data["progress"], is_new,
                          decay_cfg=decay_config(data["profile"].get("preferences")))
        update_spaced_repetition(data["sr"], session, is_new)
        heal_patterns(data["mistakes"], session, session["date"])
        streak = data["profile"].get("current_streak_days", 0)
        update_session_log(data["log"], session, streak)
    except Exception as e:
        import traceback
        print(f"[Fluent] Error updating databases: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)

    # Backup originals BEFORE writing new state (skip on re-apply: the T0
    # snapshot already gives a cleaner pre-session rollback than a per-call
    # backup would).
    if reapply is None:
        backup_all(f"pre-update-{sid}")

    try:
        for k, p in files.items():
            save_json(p, data[k])
    except Exception as e:
        import traceback
        print(f"[Fluent] Error saving databases: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)

    # Summary
    stats = data["progress"]["overall_stats"]
    sr_tomorrow = len(data["sr"]["review_queue"].get("tomorrow", []))
    skill_scores = session.get("skill_scores", {})
    total_ex = sum(s.get("exercises", 0) for s in skill_scores.values())
    total_cor = sum(s.get("correct", 0) for s in skill_scores.values())

    print(f"[Fluent] ✅ Updated 6 databases for session {session['session_id']}")
    print(f"[Fluent] 🔥 Streak: {streak} days | Sessions: {stats['total_sessions']} | Minutes: {stats['total_study_minutes']}")
    if total_ex > 0:
        print(f"[Fluent] 📊 This session: {total_cor}/{total_ex} correct ({round(total_cor/total_ex*100)}%)")
    else:
        print("[Fluent] 📊 No exercises recorded")
    print(f"[Fluent] 📈 Overall accuracy: {stats['accuracy_rate']*100:.0f}% ({stats['total_exercises']} exercises)")
    print(f"[Fluent] 🧠 SR: {data['sr']['metadata']['total_items_tracked']} items tracked, {sr_tomorrow} due tomorrow")
    print(f"[Fluent] 📝 Errors tracked: {data['mistakes']['metadata']['total_patterns_tracked']} patterns")

    sys.exit(0)


if __name__ == "__main__":
    main()
