---
name: fluent-db-updater
description: Atomically update all 6 Fluent learner databases (learner-profile, progress, mistakes, mastery, spaced-repetition, session-log) at session end by calling hooks/update-db.py with a single JSON payload. Use at the end of every practice session — fluent-writing, fluent-vocab, fluent-speaking, fluent-reading, fluent-review, fluent-learn — to persist the session's errors, review results, new vocabulary, and session metadata.
---

# DB Updater

> **Who this is for.** In the Fluent server runtime (the web app) the tutor
> NEVER calls this: `accumulate-session.py` persists every graded answer and
> the server itself runs the Capa B finalization. This skill is the **payload
> contract** — documentation for maintainers, and the instruction set for the
> Claude Code / clone runtime, where nothing persists automatically.

## Overview

Practice sessions now persist in **two layers**:

1. **Automatic per-answer (Capa A)** — the plugin's `session.idle` hook runs
   `accumulate-session.py`, which folds each newly-graded feedback into a
   `session-draft.json` and calls `update-db.py` with the FULL accumulated
   payload. It runs async/invisibly (no model turn, no learner pause) and is
   **idempotent per `session_id`**, so it never double-counts even if run
   many times for the same session.
2. **Finalization (Capa B)** — in the server runtime this is
   `persist-session.py`, run by the server on `/fluent-end` and after 30 min of
   inactivity. It re-parses the WHOLE transcript and adds the session duration;
   it does not invent metadata. The same `session_id` **replaces** the
   auto-applied entry, so it finalizes over the incremental state — no
   duplication.

   **Known gap (2026-09-13):** `new_vocabulary`, `review_results`, `milestones`
   and `focus_next_session` are structured fields that no automatic layer can
   extract from prose, so in the server runtime they are currently always
   empty. `review_results` is the one that matters: it is the ONLY input that
   advances SM-2 (interval, easiness factor, repetitions, mastery) for an item
   already in the queue. Until a structured grading call exists, queue items are
   created from errors and never graduate. In Claude Code / clone mode, where
   the tutor fills this payload itself, those fields do work.

Update-db.py is the single source of truth: it runs pre-write backups,
validates the payload, applies all changes atomically via `.tmp + fsync +
rename`, and rebuilds the spaced-repetition queue. Passing the same
`session_id` repeatedly is safe (idempotent) — see docs/CHANGES.md.

## When to Use

Server runtime: never. Claude Code / clone runtime — load this skill whenever
the tutor:

- **Finalizes a session**: at real session end, to add metadata the
  per-answer accumulation can't capture (new vocabulary full fields,
  review_result qualities, milestones, duration, focus_next_session).
- Needs to add new vocabulary to the spaced-repetition queue.
- Records new errors, review results, or mastery changes beyond the
  auto-persisted core.

The per-answer core (score, errors, progress) is already persisted
automatically by `accumulate-session.py` at `session.idle`; this skill is the
end-of-session **finalization** that assents the full, richer payload.

Skip this skill for read-only operations (use the `fluent-progress` skill or
`read-db.py` directly) and during session setup (use `fluent-setup` skill
instead — `update-db.py` is for session deltas, not bootstrap).

## Instructions

### 1. Call the script

Run from the repo root:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/hooks/update-db.py" <<'EOF'
{ ...payload... }
EOF
```

Exit codes: `0` success, `1` validation error, `2` I/O error.

### 2. Fill the payload

**Required fields**

- `session_id` — string, convention `session-NNN`. Use `computed.next_session_id` from `read-db.py`.
- `date` — YYYY-MM-DD.

**Optional fields** — omit to skip. Full canonical example (copy-paste this and fill in):

```
${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/references/db-updater-payload.example.json
```

Key blocks the example covers: `skill_scores`, `errors[]`, `new_vocabulary[]`, `review_results[]`, `topics_covered`, `breakthroughs`, `focus_next_session`, `session_notes`, `achievements_earned`, `milestones`.

### 3. Field notes

- `errors[]` — one entry per distinct mistake this session. Collapse duplicates (same `pattern_id`) before sending; `frequency` is bumped by the script.
- An error pattern needs {Target} on at least one side of it. A card that asks in {Native} and is answered in {Native} — nothing in {Target} anywhere in the exchange — is not testing {Target} at all, so there is nothing to file: skip it. This is NOT about which language the learner answers in: translation/recognition cards ({Target} word → answer in {Native}, or the reverse) are fine and completely normal, especially at A1 — file those as usual, `correct_answer` in whichever language the card actually asked for. The one thing to rule out is both sides being {Native}: a card built around {Target} vocabulary where the learner answered with a whole {Native} sentence, and the tutor then graded that sentence's OWN {Native} grammar (a gender-agreement slip, a typo) as the "mistake" — that has nothing to do with {Target} and becomes a review item drilling the learner's own language back at them. (Seen live, 2026-09-21: card about "apple", learner answered "Tinc un poma.", tutor filed `correct_answer: "Un"` — a fix to the sentence's Catalan article, no English involved at all. Had it filed "apple"/"poma" as target/native, that would have been fine.)
- `new_vocabulary[]` — items the learner met for the first time. Fill every field; incomplete entries yield incomplete spaced-repetition records.
- `review_results[]` — items already in the queue that were reviewed. The script runs SM-2 on each. See the `fluent-sm2-calculator` skill. Mapping: `quality = floor(score / 2)`.
- `skill_scores[].correct` counts correct exercises, not a percentage. Accuracy is derived.
- `confidence` in `learner-profile.skills` is 0–100 integer; `accuracy` in `progress-db` is 0.0–1.0 float. The script handles the conversion.
- `milestones[]` — each entry is a bare string OR an object `{ "milestone": <required non-empty string>, "date": <optional YYYY-MM-DD, defaults to the session date> }`. Don't set a nested `session_id`; the script stamps the authoritative top-level one. A malformed entry (neither string nor object, or an object missing/empty `milestone`) exits `1` with no files written. Each milestone becomes both a `session-log.milestones[]` record and a `learner-profile.achievements[]` entry.

### 4. Read before writing

Call `read-db.py` once at session start to get current state + `next_session_id`
(in the server runtime the command already preloaded it). Don't read each JSON
file separately:

```bash
python3 hooks/read-db.py
```

Returns all 6 databases plus computed fields (`due_reviews_count`, `next_session_id`, `streak_active`, `days_since_last_session`).

## Examples

### Example 1 — /fluent-review session with 5 items

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/hooks/update-db.py" <<'EOF'
{
  "session_id": "session-012",
  "date": "2026-04-24",
  "duration_minutes": 12,
  "command_used": "/fluent-review",
  "skills_practiced": ["vocabulary", "grammar"],
  "skill_scores": {
    "vocabulary": { "exercises": 3, "correct": 3, "time_minutes": 7 },
    "grammar":    { "exercises": 2, "correct": 1, "time_minutes": 5 }
  },
  "review_results": [
    { "item_id": "vocab_word_a", "quality": 5 },
    { "item_id": "vocab_word_b", "quality": 4 },
    { "item_id": "vocab_word_c", "quality": 5 },
    { "item_id": "word_order_subordinate", "quality": 2 },
    { "item_id": "tenses_past", "quality": 4 }
  ],
  "errors": [
    {
      "pattern_id": "word_order_subordinate",
      "category": "word_order",
      "your_answer": "{the learner's clause, wrong order}",
      "correct_answer": "{the same clause, right order}",
      "context": "subordinate clause word order",
      "severity": "critical"
    }
  ],
  "focus_next_session": ["Drill subordinate-clause word order"]
}
EOF
```

### Example 2 — /fluent-vocab session with a new word

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/hooks/update-db.py" <<'EOF'
{
  "session_id": "session-013",
  "date": "2026-04-25",
  "command_used": "/fluent-vocab",
  "skills_practiced": ["vocabulary"],
  "new_vocabulary": [
    {
      "item_id": "vocab_kitchen",
      "item_type": "vocabulary",
      "content": "{the word in the target language}",
      "answer": "{its translation in the native language}",
      "category": "household_rooms",
      "difficulty": "A1",
      "initial_quality": 4,
      "priority": "medium"
    }
  ]
}
EOF
```

## Critical Rules

- **Call at session end to finalize** the accumulated state with rich
  metadata (new vocabulary full fields, review_results qualities, milestones,
  duration). The per-answer core is already applied automatically; this call
  adds what `accumulate-session.py` can't extract from the transcript.
- **Repeated calls with the same `session_id` are idempotent** — the script
  restores the session's pre-state (internal `.update-state/` snapshot) and
  re-applies the full payload, so the session's contribution is present
  exactly once. Safe to run at every `session.idle` **and** at session end.
- **Never hand-edit `spaced-repetition.review_queue`.** It's regenerated from scratch on every run.
- **Same `session_id` replaces.** Sending the same ID again replaces rather
  than appends (both for the accumulated DB state and for `session-log`).
- **Backups are automatic.** Written to `.backups/pre-update-<session_id>/`
  on first application of a session. Check there to roll back.
- **Exit code 1 means validation failed, no files touched.** Fix the payload and retry.
- **Exit code 2 means I/O failure, no files touched.** Check disk space, permissions, then retry.

## Why This Matters

Six interdependent JSON files must agree: a new `session-log` entry, a bumped
`total_sessions`, updated SM-2 params, new mistake patterns, recalculated
accuracy, refreshed streak. Because `accumulate-session.py` re-applies the
growing payload at every `session.idle`, idempotency is what keeps these files
consistent no matter how often (or how late) the session is persisted — even
if the learner closes the window mid-session, the data up to the last graded
answer is already safe.
