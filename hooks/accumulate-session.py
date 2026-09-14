#!/usr/bin/env python3
"""
Fluent Session Accumulator (incremental, idempotent).

Runs at every `session.idle`: scans the active learner session's sessions DB
for NEWLY-graded feedback since the last run (a high-water mark) and folds it
into an accumulating `session-draft.json` payload for the current session_id.
If new answers arrived, it then calls update-db.py with the FULL accumulated
payload. update-db.py is idempotent per session_id (see docs/CHANGES.md), so
re-running with a growing payload never double-counts.

This is the "Capa A" (core per-answer) persistence: it captures from each
grade what the tutor already decided — score, corrections/category/severity,
correct version — without any new model turn or visible pause. The rich
metadata the transcript can't express (new_vocabulary full fields,
review_results quality, milestones, focus) is finalized by the tutor's
end-of-session fluent-db-updater call (same session_id → upsert, no repeat).

Usage:
    python3 accumulate-session.py --dir ~/.fluent/<id> [--dry-run]
    python3 accumulate-session.py --dir ~/.fluent/alex-en

Exit codes: 0=ok (0/no output means nothing new), 1=error
"""
import argparse
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Load persist-session.py as a module (its filename has a hyphen, so load via
# importlib) to reuse the transcript/parsing helpers without duplicating them.
# Its main() is guarded by __main__, so exec is safe and runs no CLI logic.
_SPEC = importlib.util.spec_from_file_location(
    "persist_session_mod", SCRIPT_DIR / "persist-session.py"
)
ps = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ps)

UPDATE_DB = SCRIPT_DIR / "update-db.py"
DRAFT_NAME = "session-draft.json"

SCORE_RE = re.compile(r"\*\*Score:\s*(\d+)/10\*\*")


def draft_path(data_dir: str) -> Path:
    return Path(data_dir).expanduser() / DRAFT_NAME


def load_draft(data_dir: str) -> dict:
    p = draft_path(data_dir)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_draft(data_dir: str, draft: dict):
    p = draft_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(p))


def run_update_db(payload: dict, data_dir: str) -> bool:
    cmd = [sys.executable, str(UPDATE_DB)]
    env = os.environ.copy()
    if data_dir:
        env["FLUENT_DATA_DIR"] = data_dir
    proc = subprocess.run(
        cmd, input=json.dumps(payload), capture_output=True, text=True, env=env
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode == 0


def extract_graded_with_rowids(session_id):
    """(rowid, role, text) for graded feedback parts only, in order.

    Mirrors persist-session.extract_transcript but keeps the rowid so the
    accumulator can resume from a high-water mark, and keeps only segments
    that are graded feedback (contain '**Score: X/10**').
    """
    conn = sqlite3.connect(ps.SESSIONS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT p.rowid as rid,
               json_extract(m.data, '$.role') as role,
               json_extract(p.data, '$.text') as text
        FROM part p
        JOIN message m ON m.id = p.message_id
        WHERE p.session_id = ?
        AND json_extract(p.data, '$.type') = 'text'
        AND json_extract(p.data, '$.text') IS NOT NULL
        AND length(json_extract(p.data, '$.text')) > 0
        ORDER BY p.rowid
        """,
        (session_id,),
    ).fetchall()
    conn.close()

    out = []
    for r in rows:
        role = r["role"] or "assistant"
        text = r["text"]
        if SCORE_RE.search(text):
            out.append((r["rid"], role, text))
    return out


def extract_learner_answer_for_feedback(session_id, feedback_rowid):
    """Find the learner's answer that precedes a graded feedback.

    Returns the most recent user text part before the feedback's rowid.
    """
    conn = sqlite3.connect(ps.SESSIONS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT p.rowid as rid,
               json_extract(m.data, '$.role') as role,
               json_extract(p.data, '$.text') as text
        FROM part p
        JOIN message m ON m.id = p.message_id
        WHERE p.session_id = ?
        AND json_extract(p.data, '$.type') = 'text'
        AND json_extract(p.data, '$.text') IS NOT NULL
        AND length(json_extract(p.data, '$.text')) > 0
        AND p.rowid < ?
        AND json_extract(m.data, '$.role') = 'user'
        ORDER BY p.rowid DESC
        LIMIT 1
        """,
        (session_id, feedback_rowid),
    ).fetchall()
    conn.close()
    if rows:
        return rows[0]["text"]
    return ""


def merge_errors_into_payload(payload: dict, new_patterns: list):
    errors = payload.setdefault("errors", [])
    existing = {e.get("pattern_id") for e in errors}
    for p in new_patterns:
        pid = p["id"]
        if pid in existing:
            continue
        errors.append({
            "pattern_id": pid,
            "category": p["category"],
            "your_answer": p.get("example_incorrect", ""),
            "correct_answer": p.get("example_correct", ""),
            "context": "",
            "severity": "moderate",
        })
        existing.add(pid)


def write_results_file(data_dir: str, slug: str, session_id: str, payload: dict):
    """Write/refresh the per-user results markdown (Capa A side-effect).

    Relies on Accumulated-only data (= what the tutor already graded), so it
    needs no model turn and runs at idle together with update-db.py. Keeps the
    summary file complete even if the browser is simply closed (no manual
    end-of-session persist-session.py call). Idempotent: same session_id
    filename gets rewritten in place, never duplicated.
    """
    try:
        ps.save_results_file(
            learner_slug=slug,
            session_id=payload.get("session_id") or session_id,
            exercises=payload.get("exercises", []),
            accuracy=(sum(1 for e in payload.get("exercises", [])
                          if e.get("score", 0) >= 8) / len(payload.get("exercises"))
                      if payload.get("exercises") else 0),
            report=_results_report(payload),
            data_dir=data_dir,
        )
    except Exception as e:  # never let the summary block persistence
        print(f"[Fluent] ⚠ accumulate-session: could not write results file: {e}",
              file=sys.stderr)


def _results_report(payload: dict) -> dict:
    exercises = payload.get("exercises", [])
    correct = sum(1 for e in exercises if e.get("score", 0) >= 8)
    error_patterns = [
        {"id": e.get("pattern_id", ""), "category": e.get("category", ""),
         "frequency": 1}
        for e in payload.get("errors", [])
        if e.get("pattern_id")
    ]
    return {
        "date": payload.get("date", ""),
        "duration_minutes": payload.get("duration_minutes", 0),
        "correct_count": correct,
        "skill_scores": payload.get("skill_scores", {}),
        "skills_practiced": payload.get("skills_practiced", []),
        "exercises": exercises,
        "error_patterns": error_patterns,
        "focus_next_session": payload.get("focus_next_session", []),
        "session_notes": "Persisted automatically from opencode transcript.",
    }


def rebuild_skill_scores(payload: dict):
    scores = {}
    for e in payload.get("exercises", []):
        skill = e.get("type", "writing")
        s = scores.setdefault(skill, {"exercises": 0, "correct": 0})
        s["exercises"] += 1
        if e.get("score", 0) >= 8:
            s["correct"] += 1
    payload["skill_scores"] = scores
    payload["skills_practiced"] = list(scores.keys())


def main():
    parser = argparse.ArgumentParser(description="Accumulate a Fluent session incrementally")
    parser.add_argument("--dir", help="FLUENT_DATA_DIR / profile dir (~/.fluent/<id>); "
                                      "defaults to $FLUENT_DATA_DIR")
    parser.add_argument("--slug", help="Learner slug (overrides profile name detection)")
    parser.add_argument("--session-id", dest="session_id",
                        help="sessions DB session id (ses_...) to accumulate. "
                             "The caller (the server) knows it exactly; without "
                             "it we fall back to guessing the latest learner "
                             "session by slug, which can pick the wrong one.")
    parser.add_argument("--dry-run", action="store_true", help="Print payload, skip update-db.py and draft write")
    args = parser.parse_args()

    data_dir = args.dir or os.environ.get("FLUENT_DATA_DIR")
    if not data_dir:
        print("[Fluent] ⚠ accumulate-session: no --dir and no FLUENT_DATA_DIR — skipping", file=sys.stderr)
        sys.exit(0)
    data_dir = os.path.expanduser(data_dir)
    profile = Path(data_dir) / "learner-profile.json"
    if not profile.exists():
        print("[Fluent] ⚠ accumulate-session: no learner-profile.json — skipping", file=sys.stderr)
        sys.exit(0)

    ps.set_sessions_db(ps.resolve_sessions_db(data_dir))
    if not ps.SESSIONS_DB.exists():
        print(f"[Fluent] ⚠ accumulate-session: sessions DB not found "
              f"({ps.SESSIONS_DB}) — skipping", file=sys.stderr)
        sys.exit(0)  # best-effort hook: never block the session

    slug = args.slug
    if not slug:
        try:
            with open(profile, encoding="utf-8") as f:
                lp = json.load(f)
            slug = (lp.get("learner", {}).get("name") or "").strip().lower()
        except Exception:
            slug = None
    if not slug:
        print("[Fluent] ⚠ accumulate-session: cannot determine learner slug", file=sys.stderr)
        sys.exit(0)

    if args.session_id:
        session = ps.find_session(args.session_id)
        if not session:
            print(f"[Fluent] ⚠ accumulate-session: session {args.session_id} "
                  f"not found in {ps.SESSIONS_DB} — skipping", file=sys.stderr)
            sys.exit(0)
    else:
        session = ps.find_session(None, slug, True)
        if not session:
            print("[Fluent] ⚠ accumulate-session: no recent learner session — skipping",
                  file=sys.stderr)
            sys.exit(0)
    session_id = session["id"]

    graded = extract_graded_with_rowids(session_id)
    transcript_all = ps.extract_transcript(session_id)
    draft = load_draft(data_dir)

    # --- SESSION ROTATION CHECK ---
    # If the session_id computed from the transcript differs from the draft's,
    # this is a new session: reset the draft and re-accumulate from scratch.
    computed_sid = ps.parse_session_id_from_context(transcript_all) if transcript_all else ""
    draft_sid = draft.get("session_id")
    if draft_sid and computed_sid and draft_sid != computed_sid:
        print(f"[Fluent] 🔄 New session detected ({draft_sid} → {computed_sid}), resetting draft")
        draft = {}  # reset for new session

    # Review block: it arrives ONCE, in the closing message, which usually
    # carries no new grade. So it is parsed from the full transcript on every
    # run and compared against the draft — gating it behind "new graded
    # feedback" would mean it never got applied at all.
    reviews_block = ps.known_review_results(ps.parse_review_results(transcript_all), data_dir)

    # Structured records (fluent_record_answer): the authority. Read whole on
    # every run — they are append-only and the payload is rebuilt from scratch,
    # so this stays idempotent.
    records = ps.read_records(data_dir, session_id)
    rec_exercises, rec_errors, rec_reviews = ps.records_to_payload(records)
    records_changed = len(records) != draft.get("records_count", 0)

    recorded_items = {r["item_id"] for r in rec_reviews}
    reviews = rec_reviews + [r for r in reviews_block if r["item_id"] not in recorded_items]
    reviews_changed = reviews != draft.get("review_results", [])

    hwm = draft.get("high_water_mark", 0)
    new = [(rid, role, text) for (rid, role, text) in graded if rid > hwm]
    if not graded and not reviews_changed and not records_changed:
        print("[Fluent] · accumulate-session: no graded feedback yet")
        sys.exit(0)
    if not new and not reviews_changed and not records_changed:
        print("[Fluent] · accumulate-session: no new graded feedback since last run")
        sys.exit(0)

    max_rid = max((rid for rid, _, _ in new), default=hwm)

    new_transcript = [(role, text) for _, role, text in new]

    # Parse exercises from new graded feedback, enriching with learner answers
    new_exercises_raw = ps.parse_exercises(new_transcript)
    new_patterns = ps.parse_error_patterns(new_transcript)

    # Enrich exercises with learner_answer by looking back in the full transcript
    new_exercises = []
    for ex in new_exercises_raw:
        # Find which graded feedback this exercise came from (by score match)
        # Since we only have the new feedback segments, find the matching rowid
        matching_rid = None
        for rid, role, text in new:
            if f"**Score: {ex['score']}/10**" in text:
                matching_rid = rid
                break
        if matching_rid:
            learner_ans = extract_learner_answer_for_feedback(session_id, matching_rid)
            ex["learner_answer"] = learner_ans
        new_exercises.append(ex)

    if not new_exercises and not new_patterns and not reviews_changed and not records_changed:
        # DO NOT advance high_water_mark — parser may have failed, keep for next run
        print("[Fluent] · accumulate-session: new segments but no grades parsed (keeping hwm)")
        sys.exit(0)

    sid = draft.get("session_id")
    if not sid:
        sid = computed_sid
        draft["session_id"] = sid

    # Replaced wholesale, never appended: update-db.py restores T0 and
    # re-applies, so SM-2 is computed from the pre-session state exactly once
    # however many times this runs.
    draft["review_results"] = reviews

    draft["date"] = draft.get("date") or datetime.now().strftime("%Y-%m-%d")
    draft["high_water_mark"] = max_rid
    draft["records_count"] = len(records)
    draft.setdefault("exercises", []).extend(new_exercises)
    merge_errors_into_payload(draft, new_patterns)

    # Merge: everything the tutor DECLARED, plus whatever it only narrated.
    # Overlap is dropped by answer text (exercises) and by pattern id (errors),
    # so an answer that was both recorded and parsed counts exactly once.
    recorded_answers = {ps.answer_key(e["learner_answer"]) for e in rec_exercises}
    prose_exercises = [e for e in draft.get("exercises", [])
                       if ps.answer_key(e.get("learner_answer")) not in recorded_answers]
    recorded_pids = {e["pattern_id"] for e in rec_errors}
    prose_errors = [e for e in draft.get("errors", [])
                    if e.get("pattern_id") not in recorded_pids]

    merged_exercises = rec_exercises + prose_exercises
    merged_errors = rec_errors + prose_errors
    skill_scores = {}
    for ex in merged_exercises:
        sc = skill_scores.setdefault(ex.get("type", "writing"), {"exercises": 0, "correct": 0})
        sc["exercises"] += 1
        if ex.get("score", 0) >= 8:
            sc["correct"] += 1
    draft["skill_scores"] = skill_scores
    draft["skills_practiced"] = list(skill_scores.keys())
    draft["review_results"] = reviews

    if records and len(rec_exercises) != len(draft.get("exercises", [])):
        print(f"[Fluent] ⚠ divergence: {len(rec_exercises)} recorded vs "
              f"{len(draft.get('exercises', []))} graded in prose", file=sys.stderr)

    payload = {
        "session_id": sid,
        "date": draft["date"],
        "duration_minutes": draft.get("duration_minutes", 0),
        "skills_practiced": draft.get("skills_practiced", []),
        "skill_scores": draft.get("skill_scores", {}),
        "exercises": merged_exercises,
        "errors": merged_errors,
        "new_vocabulary": draft.get("new_vocabulary", []),
        "review_results": draft.get("review_results", []),
        "focus_next_session": draft.get("focus_next_session", []),
        "milestones": [],
    }

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False))
        sys.exit(0)

    # Persist the high-water mark + accumulated draft and apply.
    save_draft(data_dir, draft)
    ok = run_update_db(payload, data_dir)
    if ok:
        write_results_file(data_dir, slug, session_id, payload)
    print(f"[Fluent] 📝 {len(records)} record(s) + {len(prose_exercises)} narrated "
          f"exercise(s), {len(merged_errors)} pattern(s), {len(reviews)} review "
          f"result(s) for {sid}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()