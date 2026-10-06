# Database Helper Scripts

Two Python scripts under `hooks/` manage the six learner databases:

| Script | Purpose |
|--------|---------|
| `read-db.py` | Load all 6 databases (+ computed fields) in one call |
| `update-db.py` | Apply a session report to all 6 databases atomically |
| `scripts/migrate-db.py` | Migrate or check the 6 databases to the current schema |

Both scripts resolve the data directory internally (see `fluent_paths.data_dir()`)
and produce identical output regardless of CWD. Always invoke them with the
`${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}` prefix so the script path
itself resolves whether Fluent is installed as a plugin (CWD is the data
directory) or cloned (CWD is the repo root).

## Reading

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/hooks/read-db.py"
```

Outputs a single JSON object:

```json
{
  "databases": {
    "learner_profile": { ... },
    "progress_db": { ... },
    "mistakes_db": { ... },
    "mastery_db": { ... },
    "spaced_repetition": { ... },
    "session_log": { ... }
  },
  "computed": {
    "today": "2026-04-24",
    "due_reviews_count": 3,
    "due_review_items": ["vocab_dag", ...],
    "next_session_id": "session-005",
    "streak_active": true,
    "days_since_last_session": 1
  }
}
```

Exit codes: `0` OK, `1` one or more files missing (partial result with
`_warnings`), `2` critical error.

## Writing

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/hooks/update-db.py" <<'EOF'
{
  "session_id": "session-005",
  "date": "2026-04-24",
  "duration_minutes": 20,
  "command_used": "/fluent-learn",
  "skills_practiced": ["vocabulary", "writing"],
  "skill_scores": {
    "vocabulary": { "exercises": 5, "correct": 4, "time_minutes": 10 },
    "writing":    { "exercises": 3, "correct": 3, "time_minutes": 10 }
  },
  "errors": [
    {
      "pattern_id": "verb_conjugation_3rd_person",
      "category": "grammar",
      "subcategory": "verb_conjugation",
      "your_answer": "Hij spreek",
      "correct_answer": "Hij spreekt",
      "context": "3rd person singular",
      "difficulty_score": 0.7,
      "severity": "critical",
      "notes": "optional free text"
    }
  ],
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
  ],
  "review_results": [
    { "item_id": "vocab_dag", "quality": 4 }
  ],
  "topics_covered": ["articles", "house_vocabulary"],
  "breakthroughs": ["First correct use of 'het' vs 'de'"],
  "focus_next_session": ["Drill de/het article gender"],
  "session_notes": "Strong session. Article gender still tricky.",
  "achievements_earned": [],
  "milestones": [
    { "milestone": "Reached 100 words learned", "date": "2026-04-24" },
    "Completed first full conversation"
  ]
}
EOF
```

### Required fields
- `session_id` (string, conventionally `session-NNN`)
- `date` (YYYY-MM-DD)

Everything else is optional; omitted fields do not update.

### Side effects
- Backs up `data/*.json` to `.backups/pre-update-<session_id>/` *before*
  writing.
- Writes each JSON file via a `.tmp` + `fsync` + `rename` pattern so a crash
  mid-write cannot leave a half-written file.
- Rebuilds `spaced-repetition.review_queue` from scratch each run — any manual
  edits there will be overwritten. Items reviewed in the session with
  `quality < 3` are forced into `review_queue.today` after the rebuild, even if
  their SM-2 `due_date` lands tomorrow.

### Exit codes
- `0` success
- `1` validation error (bad/missing JSON, missing required field)
- `2` I/O, lock timeout, or logic error (full traceback on stderr; no files
  were modified)

## Locking

The six databases are plain JSON files. Each file write is atomic, but a
session update is a read-modify-write cycle across all six files. To avoid two
concurrent writers losing one another's changes, writer scripts take an
advisory `flock()` on `<data-dir>/.db.lock`:

| Script | Lock behavior |
|---|---|
| `update-db.py` | Exclusive lock before reading/writing the six DBs |
| `scripts/migrate-db.py` | Exclusive lock only in write/migration mode; `--check` does not lock |
| `read-db.py` | No lock (read-only; kept outside this change) |
| `session-draft.json` writers | Not covered by this DB lock |

`FLOWED_DB_LOCK_TIMEOUT` sets the acquire timeout in seconds (default `10`).
On timeout the writer exits with `2` and leaves the databases untouched.
`.db.lock` is not copied into `.backups/` and is released by the OS if the
holding process dies.

## Data model notes

- `learner-profile.json` stores `confidence` per skill as an integer 0–100.
- `progress-db.json` stores `accuracy` values as floats 0.0–1.0.
- `session-log.json` sessions use `skills_practiced` (array), `score_breakdown`
  (per-skill float accuracy), `topics_covered`, `breakthroughs`,
  `focus_next_session`, `achievements_earned`. Session IDs are
  `session-NNN`.
- `spaced-repetition.json` items preserve `consecutive_correct/incorrect`,
  `mastery_level`, `total_reviews`, `priority`, `content`, `answer`,
  `category`, `difficulty` — supply these in `new_facts` payloads so new
  items are fully populated. (`new_facts` is the WP1.9 name; the old
  `new_vocabulary` spelling is still read in payloads written before it.)
- `milestones[]` accepts **either** a bare string **or** an object
  `{ "milestone": <required non-empty string>, "date": <optional YYYY-MM-DD,
  defaults to the session date> }`. A nested `session_id` is ignored — the
  script always stamps each milestone with the authoritative top-level
  `session_id`. An entry that is neither a string nor an object, or an object
  whose `milestone` is missing/empty/non-string, is a validation error (exit
  `1`, no files written). A present-but-unparseable `date` silently falls back
  to the session date.
