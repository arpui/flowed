---
name: math-db-updater
description: Atomically update all 6 FlowMath learner databases (learner-profile, progress, mistakes, mastery, spaced-repetition, session-log) at session end by calling hooks/update-db.py with a single JSON payload. Use at the end of every practice session — math-writing, math-vocab, math-speaking, math-reading, math-review, math-learn — to persist the session's errors, review results, new facts, and session metadata.
---

# DB Updater

> **Who this is for.** In the FlowMath server runtime (the web app) the tutor
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
   `persist-session.py`, run by the server on `/math-end` and after 30 min of
   inactivity. It re-parses the WHOLE transcript and adds the session duration;
   it does not invent metadata. The same `session_id` **replaces** the
   auto-applied entry, so it finalizes over the incremental state — no
   duplication.

   **Known gap (2026-09-13):** `new_facts` (WP1.9; read as `new_vocabulary` in
   older payloads), `review_results`, `milestones`
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
  per-answer accumulation can't capture (new facts full fields,
  review_result qualities, milestones, duration, focus_next_session).
- Needs to add new facts to the spaced-repetition queue.
- Records new errors, review results, or mastery changes beyond the
  auto-persisted core.

The per-answer core (score, errors, progress) is already persisted
automatically by `accumulate-session.py` at `session.idle`; this skill is the
end-of-session **finalization** that assents the full, richer payload.

Skip this skill for read-only operations (use the `math-progress` skill or
`read-db.py` directly) and during session setup (use `math-setup` skill
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

Key blocks the example covers: `skill_scores`, `errors[]`, `new_facts[]`, `review_results[]`, `topics_covered`, `breakthroughs`, `focus_next_session`, `session_notes`, `achievements_earned`, `milestones`.

### 3. Field notes

- `errors[]` — one entry per distinct mistake this session. Collapse duplicates (same `pattern_id`) before sending; `frequency` is bumped by the script.
- An error pattern must be about the MATH. A slip in the learner's own-language
  wording of an explanation (a Catalan spelling or grammar mistake) is not a
  math error: do not file it. What gets filed is the math failure — the wrong
  operation, the dropped carry, the misread statement — with `your_answer` and
  `correct_answer` quoting the numbers or the line of work. (Seen live in the
  language fork: a native-language article slip got filed as the "mistake" of
  a target-language card, and days later came back as an exercise drilling the
  learner's own language. Same trap here: a `misread` of a Catalan statement is
  filed as `misread` about the MATH asked, never as a language correction.)
- `new_facts[]` — facts the learner met for the first time (a table entry,
  an equivalence, a problem keyword). WP1.9 renamed it from the language-era
  `new_vocabulary[]`; the scripts still read the old spelling in old payloads.
  Fill every field; incomplete entries yield incomplete spaced-repetition records.
- `review_results[]` — items already in the queue that were reviewed. The script runs SM-2 on each. See the `math-sm2-calculator` skill. Mapping: `quality = floor(score / 2)`.
- `skill_scores[]` — use the math skill keys: `computation`, `steps`, `problems`,
  `reasoning`, `facts`. NOTE (WP1.7): the server's per-button daily counters
  still key on the language-era names (`writing`/`reading`/`speaking`) taken
  from the button pressed, and the progress panel seeds those names; math keys
  flow through `update-db.py` and the panel picks them up from the data, but
  until WP1.7 the two vocabularies coexist. `skill_scores[].correct` counts
  correct exercises, not a percentage. Accuracy is derived.
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

### Example 1 — /math-review session with 5 items

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/hooks/update-db.py" <<'EOF'
{
  "session_id": "session-012",
  "date": "2026-04-24",
  "duration_minutes": 12,
  "command_used": "/math-review",
  "skills_practiced": ["computation", "facts"],
  "skill_scores": {
    "computation": { "exercises": 3, "correct": 3, "time_minutes": 7 },
    "facts":       { "exercises": 2, "correct": 1, "time_minutes": 5 }
  },
  "review_results": [
    { "item_id": "m4.add_carry.007", "quality": 5 },
    { "item_id": "m4.add_carry.011", "quality": 4 },
    { "item_id": "fact.x7_x8", "quality": 5 },
    { "item_id": "m4.order_ops.003", "quality": 2 },
    { "item_id": "m4.frac_equiv.002", "quality": 4 }
  ],
  "errors": [
    {
      "pattern_id": "order_of_operations_mixed",
      "category": "order_of_operations",
      "your_answer": "3 + 2 × 4 = 20",
      "correct_answer": "3 + 2 × 4 = 11",
      "context": "addition before multiplication",
      "severity": "critical"
    }
  ],
  "focus_next_session": ["Drill precedence: multiply before add"]
}
EOF
```

### Example 2 — /math-vocab session with a new fact

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/hooks/update-db.py" <<'EOF'
{
  "session_id": "session-013",
  "date": "2026-04-25",
  "command_used": "/math-vocab",
  "skills_practiced": ["facts"],
  "new_facts": [
    {
      "item_id": "fact.x7_x8",
      "item_type": "facts",
      "content": "7 × 8 = ?",
      "answer": "56",
      "category": "times_tables",
      "difficulty": "m4",
      "initial_quality": 4,
      "priority": "medium"
    }
  ]
}
EOF
```

## Critical Rules

- **Call at session end to finalize** the accumulated state with rich
  metadata (new facts full fields, review_results qualities, milestones,
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
