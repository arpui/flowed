# Session Result File Template

Every practice skill saves its session to `~/.fluent/<id>/results/{learner-slug}-math-{skill}-session-{NNN}.md` (learner-slug = the learner's first name, lowercased, e.g. `alex`). These files are the human-readable record of a session; the machine-readable
side is `.records/<session>.jsonl` plus the six JSON databases. Keep the format
consistent so a person (or a later tool) can still read them.

## File naming

```
~/.fluent/<id>/results/{learner-slug}-math-{skill}-session-{NNN}.md
```

Examples:
- `alex-math-writing-session-012.md`
- `sam-math-vocab-session-005.md`
- `nes-math-speaking-session-003.md`
- `alex-math-review-session-042.md`
- `sam-math-learn-session-018.md`
- `nes-math-reading-session-007.md`

> Each learner's session files live in their own profile dir (`~/.fluent/<id>/results/`), so there is no risk of two learners overwriting each other. The `{learner-slug}` prefix in the filename is kept for consistency with `session-log.json`.

> Files created before v0.2.0 may use the older `{skill}-session-{NNN}.md` naming (no `math-` prefix). Do not rename existing files.

`NNN` is the global session counter (not per-skill) — matches `session_id` in `session-log.json`.

## Required structure

```markdown
# {Skill} Practice Session {NNN}

**Date:** YYYY-MM-DD
**Duration:** {X} minutes
**Skill:** {writing/speaking/vocab/reading/review/learn}
**Command:** {/math-writing, /math-speaking, etc.}

---

## Session Summary
- Questions: {Y}
- Correct: {Z}
- Accuracy: {percent}%

---

## Questions & Answers

### Question 1: {Type}

**Prompt:** {what the learner was asked}
**Your answer:** "{what they wrote}"
**Correct answer:** "{correct version}"

**Analysis:**
- ❌ {error with severity emoji} — {correction} ({category})
- ✅ {what was correct}

**Score:** {X}/10

---

### Question 2: {Type}

[repeat]

---

## Error Pattern Summary

| Pattern | Category | Severity | Count This Session |
|---------|----------|----------|--------------------|
| {pattern} | {category} | 🔴/🟡/🟢 | {N} |

## Strengths

| Skill | Evidence |
|-------|----------|
| {skill} | {what the learner did well} |

## Progress Tracking

**Improvements:**
- {what improved compared to last session}

**Focus Areas:**
- {what needs work}

**Next Session:**
- {recommended focus}
```

## Key parsing markers

Keep these markers — they are what makes an old session file readable at a glance:

- `❌` — error line (parsed for category + severity)
- `✅` — strength line
- `**Score:** {X}/10` — per-question score
- `**Accuracy:** {percent}%` — session accuracy
- `| 🔴` / `| 🟡` / `| 🟢` — severity in tables
- `**Focus Areas:**` — cue for next-session planning

Do not rename these headings or reorder sections. Changes break the analyzer.

## Interaction with databases

Session files are **markdown narrative**. JSON databases (`mistakes-db.json`, `mastery-db.json`) hold aggregated counts and SM-2 state. Both must be updated — the markdown records the story, the JSON records the numbers.

Call `hooks/update-db.py` once at session end with a full payload (see `db-updater-payload.example.json`). The script handles the JSON side; the practice skill handles the markdown side. The `math-db-updater` skill documents the payload schema.
