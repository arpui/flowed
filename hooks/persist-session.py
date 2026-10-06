#!/usr/bin/env python3
"""
Fluent Session Persistence Script
Extracts a session from the profile's sessions DB, builds a report, and calls update-db.py.

Usage:
    python3 hooks/persist-session.py <session-id> [--dir <data-dir>]
    python3 hooks/persist-session.py --latest [--slug <learner-slug>] [--dir <data-dir>]

Examples:
    python3 hooks/persist-session.py ses_fbc429f6bffeX9Mnl3BEFl0OW2
    python3 hooks/persist-session.py --latest --slug sam
    python3 hooks/persist-session.py --latest --dir ~/.flowed/sam-en

Exit codes: 0=success, 1=error
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# --- Config ---
# Legacy central DB (opencode's own, outside any profile). Kept last in the
# resolution order so an old single-user install still works.
DEFAULT_OPENCODE_DB = Path.home() / ".local/share/opencode/opencode.db"

# Where a profile's session transcript lives now, and where it used to live.
SESSIONS_DB_REL = ("sessions", "sessions.db")
LEGACY_SESSIONS_DB_REL = (".opencode", "opencode", "opencode.db")
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from db_schema import normalize_error_category  # noqa: E402
from main_paths import profiles_root  # noqa: E402  (where the profiles live)

UPDATE_DB = SCRIPT_DIR / "update-db.py"
# Results files are per-user now: each learner's session history lives in
# ~/.flowed/<id>/results/, alongside the 6 DBs. Derived at save time from the
# resolved data_dir (profile), not from the repo root — see save_results_file().
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results"

# --- Per-profile sessions DB resolution ---
# Each learner's transcript lives inside their own profile directory. The path
# used to be ~/.flowed/<id>/.opencode/opencode/opencode.db — a shape inherited
# from opencode's XDG layout, kept long after opencode stopped being the
# runtime. It is now ~/.flowed/<id>/sessions/sessions.db.
#
# Resolution order (first hit wins):
#   1. explicit --db
#   2. $FLOWED_SESSIONS_DB
#   3. <profile>/sessions/sessions.db            (current)
#   4. <profile>/.opencode/opencode/opencode.db  (legacy — still read, never
#      deleted, so the previous version of the app keeps working on it)
#   5. the central legacy DB
# A profile with neither gets the CURRENT path, so new profiles are born clean.
def resolve_sessions_db(data_dir, explicit_db=None):
    if explicit_db:
        return Path(explicit_db).expanduser()
    env = os.environ.get("FLOWED_SESSIONS_DB")
    if env:
        return Path(env).expanduser()
    if data_dir:
        p = Path(data_dir).expanduser()
        current = p.joinpath(*SESSIONS_DB_REL)
        if current.exists():
            return current
        legacy = p.joinpath(*LEGACY_SESSIONS_DB_REL)
        if legacy.exists():
            return legacy
        return current
    return DEFAULT_OPENCODE_DB


# Old name, kept so nothing that imported it breaks.
resolve_opencode_db = resolve_sessions_db

SESSIONS_DB = DEFAULT_OPENCODE_DB
OPENCODE_DB = SESSIONS_DB  # legacy alias, kept in sync by set_sessions_db()


def set_sessions_db(path):
    """Point the module-level DB path at a specific sessions DB."""
    global SESSIONS_DB, OPENCODE_DB
    SESSIONS_DB = path
    OPENCODE_DB = path


set_opencode_db = set_sessions_db


def find_session(session_id=None, slug=None, latest=False):
    """Find a session in the sessions DB."""
    conn = sqlite3.connect(str(SESSIONS_DB))
    conn.row_factory = sqlite3.Row
    
    if session_id:
        row = conn.execute(
            "SELECT * FROM session WHERE id = ?", (session_id,)
        ).fetchone()
    elif latest:
        if slug:
            # Find sessions with learner name in the initial prompt
            rows = conn.execute("""
                SELECT s.* FROM session s
                JOIN part p ON p.session_id = s.id
                WHERE json_extract(p.data, '$.type') = 'text'
                AND json_extract(p.data, '$.text') LIKE ?
                AND s.agent = 'learner'
                ORDER BY s.time_created DESC LIMIT 1
            """, (f'%"{slug}"%',)).fetchall()
            row = rows[0] if rows else None
        else:
            row = conn.execute(
                "SELECT * FROM session WHERE agent = 'learner' ORDER BY time_created DESC LIMIT 1"
            ).fetchone()
    else:
        conn.close()
        return None
    
    conn.close()
    return dict(row) if row else None


def extract_transcript(session_id):
    """Extract (role, text) pairs from a session, in order.

    Roles come from the owning message (part.message_id -> message.data.role).
    Used by parsers that need to tell learner answers apart from tutor
    instructions/feedback.
    """
    conn = sqlite3.connect(str(SESSIONS_DB))
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute("""
        SELECT json_extract(m.data, '$.role') as role,
               json_extract(p.data, '$.text') as text
        FROM part p
        JOIN message m ON m.id = p.message_id
        WHERE p.session_id = ?
        AND json_extract(p.data, '$.type') = 'text'
        AND json_extract(p.data, '$.text') IS NOT NULL
        AND length(json_extract(p.data, '$.text')) > 0
        ORDER BY p.rowid
    """, (session_id,)).fetchall()
    
    conn.close()
    return [(dict(r)['role'] or 'assistant', dict(r)['text']) for r in rows]


def extract_transcript_plain(transcript):
    """Back-compat: plain list of texts from the (role, text) list."""
    return [t for _, t in transcript]


def extract_learner_texts(transcript):
    """All verbatim learner (user) text segments, for use as answers."""
    return [t for r, t in transcript if r == 'user' and t.strip()]


def extract_tool_calls(session_id):
    """Extract tool calls from a session."""
    conn = sqlite3.connect(str(SESSIONS_DB))
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute("""
        SELECT json_extract(data, '$.tool') as tool,
               json_extract(data, '$.state.output') as output,
               json_extract(data, '$.state.status') as status
        FROM part
        WHERE session_id = ?
        AND json_extract(data, '$.type') = 'tool'
        ORDER BY rowid
    """, (session_id,)).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]


def parse_learner_name(transcript):
    """Extract learner name from the initial prompt."""
    for role, text in transcript[:5]:
        m = re.search(r'"name"\s*:\s*"(\w+)"', text)
        if m:
            return m.group(1).lower()
    return None


def parse_session_id_from_context(transcript):
    """Extract session_id from the computed section.

    Dead in practice: the read-db state block that carries next_session_id is
    pinned to the SYSTEM prompt and never stored as a part, so no transcript
    contains it and this always falls back to "session-001". The live number
    now comes from the draft — see draft_number_for(); this stays only as the
    fallback for sessions whose draft has already rotated away (the sweeper).
    """
    for role, text in transcript[:5]:
        m = re.search(r'"next_session_id"\s*:\s*"(session-\d+)"', text)
        if m:
            # next_session_id is the NEXT session, so current is one less
            num = int(m.group(1).split('-')[1])
            return f"session-{num:03d}"
    return "session-001"


def draft_number_for(data_dir, live_session_id):
    """The session NUMBER Capa A (accumulate-session) assigned to this live
    session, read from session-draft.json. Capa B must land on the same
    session_id or the two layers write two different sessions and update-db's
    idempotency (restore T0, re-apply) can't line them up. None when the draft
    belongs to another session — e.g. the sweeper finalising an old one."""
    try:
        draft = json.loads((Path(data_dir).expanduser() / "session-draft.json")
                           .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if draft.get("live_session") == live_session_id and str(draft.get("session_id", "")).startswith("session-"):
        return draft["session_id"]
    return None


def _feedback_of(text):
    """Return (score, feedback_text) if text is a graded feedback, else None."""
    score_match = re.search(r'\*\*Score:\s*(\d+)/10\*\*', text)
    if not score_match:
        return None
    return int(score_match.group(1)), text


def parse_exercises(transcript):
    """Parse exercises from a (role, text) transcript.

    A graded feedback (assistant text containing '**Score: X/10**') closes an
    exercise. The learner's answer is the most recent user text segment that
    appeared after the preceding exercise prompt but before this feedback.
    """
    exercises = []
    score_re = re.compile(r'\*\*Score:\s*(\d+)/10\*\*')
    pending_answer = None

    for role, text in transcript:
        if role == 'user' and text.strip():
            pending_answer = text.strip()
            continue

        if role != 'assistant':
            continue

        m = score_re.search(text)
        if not m:
            continue
        score = int(m.group(1))

        # Question: try to locate a labelled exercise/question heading.
        heading = re.search(r'(##\s*(?:Exercise|Question|Review)\s*\d*[^\n]*)', text[:200] or '')
        question = heading.group(1).strip() if heading else ""
        if not question:
            # Use the first bold phrase of the feedback/instruction as a fallback.
            qm = re.search(r'\*\*(.+?)\*\*\s*', text)
            question = qm.group(1).strip() if qm else ""
        # Prefer the prompt text (before the corrections) as the question.
        prompt_cut = re.split(r'\*\*((?:Corrections|Correct version))', text)
        if len(prompt_cut) >= 2:
            question = prompt_cut[0].strip().replace('##', '').strip()[:200] or question

        # Determine exercise type from the whole feedback text — the five math
        # skill keys (C7, WP1.9). The language-era defaults (writing/speaking/
        # vocabulary/reading) named skills this product no longer has; a prose
        # fallback that invents them writes phantom skill_scores entries.
        seg = text.lower()
        exercise_type = "computation"
        if any(w in seg for w in ['steps', 'passos', 'operació per línia']):
            exercise_type = "steps"
        elif any(w in seg for w in ['flashcard', 'fact', 'fets', 'taula de multiplicar', 'equival', 'doble', 'meitat']):
            exercise_type = "facts"
        elif any(w in seg for w in ['problema', 'word problem', 'problemes']):
            exercise_type = "problems"
        elif any(w in seg for w in ['explica', 'justifica', 'raonament', 'per què']):
            exercise_type = "reasoning"

        exercises.append({
            "type": exercise_type,
            "question": question[:200],
            "learner_answer": (pending_answer or "")[:500],
            "correct_answer": "",
            "score": score,
            "feedback": text[:500],
            "error_patterns": []
        })
        pending_answer = None

    return exercises


RECORDS_DIRNAME = ".records"


def read_records(data_dir, session_id):
    """Structured grading records written by the server's math_record_answer.

    One JSON object per line in <data_dir>/.records/<session_id>.jsonl, already
    validated at write time (score range, known category, item_id present in the
    queue). These are the AUTHORITY; the prose parsers below stay as a fallback
    for answers the tutor narrated but did not record.
    """
    if not data_dir or not session_id:
        return []
    path = Path(data_dir).expanduser() / RECORDS_DIRNAME / f"{session_id}.jsonl"
    records, seen = [], set()
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
                if not isinstance(rec, dict):
                    continue
                rid = rec.get("record_id")
                if rid:
                    if rid in seen:
                        continue
                    seen.add(rid)
                records.append(rec)
    except OSError:
        return []
    return records


def answer_key(text):
    """Loose key used to tell a recorded answer from a narrated one."""
    return re.sub(r"\W+", "", str(text or "").lower())[:40]


def pattern_id_for(category, wrong, right=None):
    """The id of the thing being LEARNED, not of the slip that revealed it.

    Keyed on the wrong answer, this produced `vocabulary_ben` from a learner
    who typed "ben" where "welcome" belonged — and three sessions later the
    tutor dutifully asked "What is the correct English word for 'ben'?". "ben"
    is not a word. It was a typo, promoted to study material.

    Keyed on the correct form it is both meaningful and self-deduplicating:
    three different misspellings of the same word collapse into one item
    instead of spawning three. Falls back to the wrong form when there is no
    correct one, so the prose parser (which often has only the mistake) keeps
    the id shape it always had.
    """
    key = str(right or wrong)
    return f"{category}_{key.replace(' ', '_')[:20]}"


def records_to_payload(records):
    """(exercises, errors, review_results) from structured records."""
    exercises, errors, reviews, seen = [], [], {}, set()
    for rec in records:
        try:
            score = int(rec.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0
        exercises.append({
            "type": (rec.get("skill") or "computation"),  # math skill keys (C7); was "writing"
            "question": str(rec.get("exercise", ""))[:200],
            "learner_answer": str(rec.get("learner_answer", ""))[:500],
            "correct_answer": "",
            "score": score,
            "feedback": "",
            "error_patterns": [],
        })
        for corr in rec.get("corrections", []) or []:
            if not isinstance(corr, dict):
                continue
            category = normalize_error_category(corr.get("category"))
            wrong = str(corr.get("wrong", "")).strip()
            right = str(corr.get("right", "")).strip()
            if not wrong or not right:
                continue
            pid = pattern_id_for(category, wrong, right)
            if pid in seen:
                continue
            seen.add(pid)
            errors.append({
                "pattern_id": pid,
                "category": category,
                "your_answer": wrong,
                "correct_answer": right,
                "context": str(rec.get("exercise", ""))[:200],
                "severity": corr.get("severity", "moderate"),
            })
        item_id = str(rec.get("item_id") or "").strip()
        if item_id:
            quality = rec.get("sm2_quality")
            if quality is None:
                quality = score // 2
            try:
                reviews[item_id] = max(0, min(5, int(quality)))
            except (TypeError, ValueError):
                pass
    return exercises, errors, [{"item_id": k, "quality": v} for k, v in reviews.items()]


REVIEW_BLOCK_RE = re.compile(r"```math:review_results\s*(.*?)```", re.S)


def parse_review_results(transcript):
    """Read the tutor's machine-readable review block(s) from the transcript.

    Shape (the tutor sends it once, at the end of a review/vocab session):

        ```math:review_results
        [{"item_id": "vocab_window", "quality": 4}, ...]
        ```

    This is the ONLY input that advances SM-2 for an item already in the queue
    (interval, easiness factor, repetitions, mastery) — update-db.py reads
    session["review_results"]. Without it, items are created from errors and
    never graduate, which is exactly what happened until 2026-09-13.

    Liberal in what it accepts (`id` for `item_id`, `score` 0-10 instead of
    `quality` 0-5), strict in what it emits: one entry per item, quality
    clamped to 0-5, last mention wins. Malformed blocks are skipped, never
    fatal — a tutor that writes nonsense must not break persistence.
    """
    out = {}
    for role, text in transcript:
        if role != "assistant" or not text:
            continue
        for match in REVIEW_BLOCK_RE.finditer(text):
            try:
                data = json.loads(match.group(1).strip())
            except ValueError:
                continue
            if isinstance(data, dict):
                data = data.get("review_results") or data.get("items") or []
            if not isinstance(data, list):
                continue
            for row in data:
                if not isinstance(row, dict):
                    continue
                item_id = str(row.get("item_id") or row.get("id") or "").strip()
                if not item_id:
                    continue
                quality = row.get("quality")
                if quality is None and row.get("score") is not None:
                    try:
                        quality = int(float(row["score"])) // 2
                    except (TypeError, ValueError):
                        quality = None
                try:
                    quality = int(quality)
                except (TypeError, ValueError):
                    continue
                out[item_id] = max(0, min(5, quality))
    return [{"item_id": k, "quality": v} for k, v in out.items()]


def known_review_results(review_results, data_dir):
    """Drop ids that are not in the learner's queue (models do invent them).

    update-db.py ignores unknown ids anyway; filtering here is what makes the
    log say how many were dropped instead of failing silently.
    """
    if not review_results:
        return []
    try:
        with open(Path(data_dir).expanduser() / "spaced-repetition.json", encoding="utf-8") as f:
            items = set(json.load(f).get("items", {}))
    except (OSError, ValueError, TypeError):
        return review_results
    kept = [r for r in review_results if r["item_id"] in items]
    dropped = len(review_results) - len(kept)
    if dropped:
        print(f"[Fluent] ⚠ {dropped} review result(s) discarded: item_id not in the queue",
              file=sys.stderr)
    return kept


def parse_error_patterns(transcript):
    """Extract error patterns from feedback.

    A correction is a learner MISTAKE when the tutor marks it as one, and a
    DEMONSTRATION when it does not ("you could also say…"). Telling them apart
    used to be done by score — anything at 8/10 or above was discarded as a
    demonstration — and on real sessions that threw away almost everything: the
    tutor scores generously, so a 9/10 carrying an explicit

        - 🟡 "last friday" → **"last Friday"** (capitalization — …)

    lost its pattern, and with it the whole point of mistakes-db. Measured on a
    live speaking session: three graded answers, three real corrections, **zero**
    patterns stored.

    The marker is the signal, not the score. The `→ **"right"** (category)`
    shape only ever appears in a correction; a ✅ line is a confirmation and a
    "natural alternative" carries no arrow at all, so both are already excluded
    by the pattern itself. What remains is to skip a match that sits on a ✅
    line, and to keep the original intent for a flawless answer.
    """
    patterns = []
    # Matches corrections "wrong" → **"right"** (category ...) which appear in
    # graded feedback, regardless of the leading marker (❌ / 🟡 / 🔴 / "-").
    # The category may carry hyphens ("word-order"); db_schema normalizes it.
    correction_pattern = re.compile(r'"([^"]+)"\s*→\s*\*\*"([^"]+)"\*\*\s*\(([\w-]+)')
    seen = set()

    for role, text in transcript:
        if role != 'assistant':
            continue
        fb = _feedback_of(text)
        if not fb:
            continue
        score, _ = fb
        for m in correction_pattern.finditer(text):
            # The line this correction sits on decides what it is.
            start = text.rfind("\n", 0, m.start()) + 1
            end = text.find("\n", m.end())
            line = text[start:end if end != -1 else len(text)]
            marked = any(mark in line for mark in ("🔴", "🟡", "🟢", "❌"))
            if "✅" in line and not marked:
                continue  # a confirmation of what they got right
            if score >= 10 and not marked:
                continue  # flawless answer: this is a demonstration
            cat = normalize_error_category(m.group(3))
            # The same rule as the structured path, which was fixed and this one
            # was not: the id names the thing being LEARNED, never the slip. Both
            # parsers run over the same session, so keying them differently
            # produced two patterns per correction — `articles_an` from the right
            # answer and `articles_banana` from the wrong one, side by side in a
            # real profile. And the second one then became an SM-2 item, due
            # tomorrow, asking the learner about her own typo.
            pid = pattern_id_for(cat, m.group(1), m.group(2))
            if pid in seen:
                continue
            seen.add(pid)
            patterns.append({
                "id": pid,
                "category": cat,
                "frequency": 1,
                "example_incorrect": m.group(1),
                "example_correct": m.group(2)
            })

    return patterns


def session_date(session_info) -> str:
    """The day the session HAPPENED, not the day it was written up.

    This used to be `datetime.now()`, which is right for a session closed the
    same day and wrong for every other case. Seen live: the sweeper picked up
    sessions from 3 and 9 September and stamped them both 14 September, so
    `session-log.json` said two girls had practised on a day nobody had opened
    the app. The numbers were fine — update-db restores its T0 snapshot before
    re-applying — but the history read as fiction.

    The session row carries when it happened. Use it, and fall back to today
    only when there is genuinely nothing to go on.
    """
    for key in ("time_created", "last_activity", "time_updated"):
        try:
            ms = int((session_info or {})[key])
        except (KeyError, TypeError, ValueError):
            continue
        if ms > 0:
            return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")


def build_report(session_id, transcript, tool_calls, session_info, override_session_id=None,
                 data_dir_for_records=None):
    """Build the report JSON for update-db.py."""
    learner_slug = parse_learner_name(transcript)
    computed_session_id = parse_session_id_from_context(transcript)
    # Capa A already gave this live session its number in the draft; use the
    # same one so both layers fold into ONE update-db session (idempotent).
    if not override_session_id and data_dir_for_records:
        computed_session_id = draft_number_for(data_dir_for_records, session_id) or computed_session_id
    if override_session_id:
        computed_session_id = override_session_id

    # Structured records (math_record_answer) are the authority; the prose
    # parsers below fill in only the answers the tutor narrated but did not
    # record. Capa B re-applies the WHOLE session, so it must read both — if it
    # dropped either, closing a session would undo what Capa A just applied.
    records = read_records(data_dir_for_records, session_id)
    rec_exercises, rec_errors, rec_reviews = records_to_payload(records)

    prose_exercises = parse_exercises(transcript)
    prose_patterns = parse_error_patterns(transcript)
    block_reviews = parse_review_results(transcript)

    recorded_answers = {answer_key(e["learner_answer"]) for e in rec_exercises}
    extra_exercises = [e for e in prose_exercises
                       if answer_key(e.get("learner_answer")) not in recorded_answers]
    exercises = rec_exercises + extra_exercises

    recorded_pids = {e["pattern_id"] for e in rec_errors}
    error_patterns = [p for p in prose_patterns
                      if pattern_id_for(p["category"], p["example_incorrect"],
                                        p.get("example_correct")) not in recorded_pids]

    recorded_items = {r["item_id"] for r in rec_reviews}
    review_results = rec_reviews + [r for r in block_reviews
                                    if r["item_id"] not in recorded_items]

    if records:
        print(f"[Fluent] 🧾 {len(records)} structured record(s); prose adds "
              f"{len(extra_exercises)} exercise(s), {len(error_patterns)} pattern(s)")
        if len(prose_exercises) != len(rec_exercises):
            print(f"[Fluent] ⚠ divergence: {len(rec_exercises)} recorded vs "
                  f"{len(prose_exercises)} graded in prose — the tutor did not record "
                  f"every answer", file=sys.stderr)
    
    # Calculate stats
    total_exercises = len(exercises)
    correct_count = sum(1 for e in exercises if e["score"] >= 8)
    accuracy = correct_count / total_exercises if total_exercises > 0 else 0
    avg_score = sum(e["score"] for e in exercises) / total_exercises if total_exercises > 0 else 0
    
    # Calculate duration from session timestamps
    duration_minutes = 0
    if session_info:
        created = session_info.get('time_created', 0)
        updated = session_info.get('time_updated', 0)
        if created and updated:
            duration_minutes = max(1, round((updated - created) / 60000))
    
    # Build skill_scores
    skill_scores = {}
    for e in exercises:
        skill = e["type"]
        if skill not in skill_scores:
            skill_scores[skill] = {"exercises": 0, "correct": 0}
        skill_scores[skill]["exercises"] += 1
        if e["score"] >= 8:
            skill_scores[skill]["correct"] += 1
    
    # update-db.py reads session["errors"], never "error_patterns". Emitting
    # only the latter meant Capa B applied ZERO errors — and because update-db
    # is idempotent per session_id (restore T0, re-apply), running Capa B after
    # Capa A ERASED the error patterns and the spaced-repetition items that
    # Capa A had already recorded for that session. Same mapping as
    # accumulate-session.merge_errors_into_payload.
    errors = rec_errors + [
        {
            "pattern_id": p["id"],
            "category": p["category"],
            "your_answer": p.get("example_incorrect", ""),
            "correct_answer": p.get("example_correct", ""),
            "context": "",
            "severity": "moderate",
        }
        for p in error_patterns
    ]

    # Build the report
    report = {
        "session_id": computed_session_id,
        "learner_slug": learner_slug,
        "skill": "math-learn",
        "date": session_date(session_info),
        "duration_minutes": duration_minutes,
        "total_exercises": total_exercises,
        "correct_count": correct_count,
        "accuracy": accuracy,
        "avg_score": avg_score,
        "skill_scores": skill_scores,
        "skills_practiced": list(skill_scores.keys()),
        "exercises": exercises,
        "errors": errors,              # consumed by update-db.py
        "error_patterns": error_patterns,  # kept for the results markdown table
        "new_facts": [],  # WP1.9: renamed from new_vocabulary (update-db still reads the old key)
        "review_results": review_results,
        "focus_next_session": [],
        "session_notes": "Persisted automatically from opencode transcript.",
        "milestones": [],
        "achievements_earned": []
    }
    
    return report, learner_slug, computed_session_id


def save_results_file(learner_slug, session_id, exercises, accuracy, report, data_dir=None):
    """Save the results markdown file under the learner's profile directory.

    Results are per-user: ~/.flowed/<id>/results/{slug}-math-learn-{ID}.md.
    Falls back to the repo-root results/ when no data_dir/profile is known.
    """
    data_dir_p = Path(data_dir).expanduser() if data_dir else None
    results_dir = (
        (data_dir_p / "results")
        if data_dir_p and data_dir_p / "learner-profile.json"
        else DEFAULT_RESULTS_DIR
    )
    if not results_dir.exists():
        results_dir.mkdir(parents=True)
    
    filename = f"{learner_slug}-math-learn-{session_id}.md"
    filepath = results_dir / filename
    
    lines = [
        f"# Math Learning Session - {session_id}",
        f"**Date:** {report['date']} · **Duration:** {report['duration_minutes']} min · **Skill:** math-learn",
        "",
        f"## Summary",
        f"Questions: {len(exercises)} · Correct: {report['correct_count']} · Accuracy: {accuracy*100:.0f}%",
        "",
        "## Questions & Answers"
    ]
    
    for i, e in enumerate(exercises, 1):
        lines.append(f"### Q{i}: {e['type']}")
        lines.append(f"**Answer:** \"{e['learner_answer']}\" · **Correct:** \"{e['correct_answer']}\" · **Score:** {e['score']}/10")
        if e.get('feedback'):
            lines.append(f"**Feedback:** {e['feedback']}")
        lines.append("")
    
    if report.get('error_patterns'):
        lines.append("## Error Analysis")
        lines.append("| Pattern | Category | Frequency | Mastery |")
        lines.append("|---|---|---|---|")
        for p in report['error_patterns']:
            lines.append(f"| {p['id']} | {p['category']} | {p['frequency']} | 0 |")
        lines.append("")
    
    lines.append("## Progress")
    lines.append(f"**Focus next:** {', '.join(report.get('focus_next_session', [])) or 'N/A'}")
    lines.append(f"**Note:** Persisted automatically from opencode transcript.")
    lines.append("")
    
    filepath.write_text("\n".join(lines), encoding="utf-8")
    print(f"[Fluent] 📄 Results file: {filepath}")
    return filepath


def run_update_db(report, data_dir):
    """Call update-db.py with the report."""
    cmd = [sys.executable, str(UPDATE_DB)]
    env = os.environ.copy()
    if data_dir:
        env["FLOWED_DATA_DIR"] = data_dir
    
    proc = subprocess.run(
        cmd,
        input=json.dumps(report),
        capture_output=True,
        text=True,
        env=env
    )
    
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    
    return proc.returncode == 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Persist a Fluent session from the sessions DB")
    parser.add_argument("session_id", nargs="?", help="Session ID to persist")
    parser.add_argument("--latest", action="store_true", help="Persist the latest session")
    parser.add_argument("--slug", help="Learner slug (for --latest)")
    parser.add_argument("--dir", help="FLOWED_DATA_DIR path")
    parser.add_argument("--db", help="Explicit sessions DB path to read the session from")
    parser.add_argument("--session-id", dest="override_session_id",
                        help="Override the session id (e.g. session-004)")
    parser.add_argument("--dry-run", action="store_true", help="Print report without persisting")
    args = parser.parse_args()
    
    if not args.session_id and not args.latest:
        parser.error("Provide a session ID or use --latest")
    
    # Resolve which sessions DB to read: explicit --db, else derive from --dir
    # when it points at a per-profile data dir (~/.flowed/<id>/), else default.
    set_sessions_db(resolve_sessions_db(args.dir, args.db))
    if not SESSIONS_DB.exists():
        # sqlite3.connect would silently CREATE an empty DB here and the real
        # failure ("no such table: session") would surface much later, confusing.
        print(f"[Fluent] ❌ sessions DB not found: {SESSIONS_DB} "
              f"(pass --db <path> or --dir <profile-data-dir>)", file=sys.stderr)
        sys.exit(1)
    print(f"[Fluent] 🗄️  Reading sessions from: {SESSIONS_DB}")

    # Find the session
    session = find_session(args.session_id, args.slug, args.latest)
    if not session:
        print("[Fluent] ❌ Session not found", file=sys.stderr)
        sys.exit(1)
    
    session_id = session['id']
    print(f"[Fluent] 🔍 Found session: {session_id}")
    
    # Extract transcript
    transcript = extract_transcript(session_id)
    if not transcript:
        print("[Fluent] ❌ No transcript found", file=sys.stderr)
        sys.exit(1)
    
    print(f"[Fluent] 📝 Transcript: {len(transcript)} text segments")
    
    # Extract tool calls
    tool_calls = extract_tool_calls(session_id)
    
    # Build report
    report, learner_slug, computed_sid = build_report(
        session_id, transcript, tool_calls, session, args.override_session_id,
        data_dir_for_records=args.dir)
    report["review_results"] = known_review_results(report["review_results"], args.dir)

    # Fallback: the name is parsed out of the preloaded state in the first turns.
    # If that block is missing (a session started without a command, a truncated
    # transcript), fall back to the profile instead of writing a results file
    # literally called "None-math-learn-...".
    if not learner_slug and args.dir:
        try:
            with open(Path(args.dir).expanduser() / "learner-profile.json", encoding="utf-8") as f:
                learner_slug = (json.load(f).get("learner", {}).get("name") or "").strip().lower() or None
        except (OSError, ValueError):
            pass
    
    print(f"[Fluent] 👤 Learner: {learner_slug}")
    print(f"[Fluent] 📊 Session: {computed_sid}, {report['total_exercises']} exercises, {report['accuracy']*100:.0f}% accuracy")
    
    # Nothing to persist: a session with no graded exercise (the learner opened
    # it and left). This is DONE, not a failure — exit 0 so the caller marks it
    # finalised. It used to exit 1, which told the 30-min sweeper "failed, try
    # again", so it re-ran Capa B for that session EVERY minute forever; each
    # retry re-entered update-db's T0 machinery and could roll a freshly-seeded
    # spaced-repetition queue back over (seen live in the WP1.9 e2e).
    if report['total_exercises'] == 0:
        print("[Fluent] ⚠️  No graded exercises found in this session — nothing to persist.")
        sys.exit(0)
    
    if args.dry_run:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0)
    
    # Persist
    data_dir = args.dir
    if not data_dir and learner_slug:
        data_dir = str(profiles_root() / f"{learner_slug}-en")
    
    success = run_update_db(report, data_dir)
    if not success:
        print("[Fluent] ❌ update-db.py failed", file=sys.stderr)
        sys.exit(1)
    
    # Save results file (per-user profile results dir)
    save_results_file(learner_slug, computed_sid, report['exercises'], report['accuracy'], report, data_dir)
    
    print(f"[Fluent] ✅ Session {computed_sid} persisted for {learner_slug}")


if __name__ == "__main__":
    main()
