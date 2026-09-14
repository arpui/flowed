---
name: fluent-feedback-formatter
description: Canonical feedback template for every learner answer in the Fluent system — celebrate correct parts, correct mistakes with category and brief explanation, show the full correct version, score out of 10, and classify severity (🔴 critical / 🟡 moderate / 🟢 minor). Use in every practice session (fluent-writing, fluent-vocab, fluent-speaking, fluent-reading, fluent-review) immediately after the learner submits an answer.
---

# Feedback Formatter

## Overview

Every practice session ends each turn with immediate feedback. Consistency matters — the learner builds mental models from the structure, and error patterns we mine from session files depend on predictable markers (❌, ✅, severity emoji). This skill defines the single feedback shape used across all Fluent practice skills.

## When to Use

Load this skill whenever the tutor:

- Grades a learner answer in any practice skill (`fluent-learn`, `fluent-vocab`, `fluent-writing`, `fluent-speaking`, `fluent-reading`, `fluent-review`).
- Needs to classify an error by severity before writing to `mistakes-db.json`.
- Needs to tag an error by category (grammar, vocabulary, prepositions, etc.).

Skip this skill for non-feedback output (greetings, summaries, progress reports).

## Instructions

### 1. Standard template

```markdown
{✅ or ❌} {one-line encouragement or gentle correction}

**Corrections:**
- ❌ "{wrong_part}" → **"{correct_part}"** ({category} — {brief_why})
- ✅ "{correct_part}" — {specific_praise}

**Correct version:**
"{full_correct_sentence}"

**Score: {X}/10** {emoji} {short_comment}

---
```

Skip the ❌ block if the answer is fully correct. Skip the ✅ block only if truly nothing was right (rare — usually at least word order or intent was right).

### 2. Tag severity on every error

| Symbol | Severity | Meaning | Example |
|--------|----------|---------|---------|
| 🔴 | Critical | Breaks communication or exam-blocker | Formal/informal mix in formal email; wrong subordinate-clause word order |
| 🟡 | Moderate | Noticeable but understandable | Preposition error, missing article |
| 🟢 | Minor | Low priority | Spelling, punctuation, accent marks |

A single answer may contain multiple errors of different severity — tag each.

### 3. Use these category labels

These feed `mistakes-db.json`:

- `grammar` — conjugation, clause structure, general morphology
- `word_order` — position of verb, object, adverb, negation
- `tenses` — wrong tense or aspect
- `agreement` — subject-verb, gender, number
- `articles` — definite / indefinite / zero article
- `prepositions` — wrong or missing preposition
- `pronouns` — wrong or missing pronoun
- `vocabulary` — wrong word, native-language mixing, register-wrong synonym
- `spelling` — misspelling, accents, diacritics
- `punctuation` — commas, apostrophes, final punctuation
- `capitalization` — upper/lower case
- `formal_informal` — wrong politeness form for the situation
- `register` — tone mismatch (too casual / too stiff) beyond politeness forms
- `missing` — omitted greeting, closing, required element
- `comprehension` — reading/listening answer that misreads the source

Use these names exactly, in lowercase with underscores. They are the single
source of truth (`ERROR_CATEGORIES` in `hooks/db_schema.py`): a label
that is not on the list is silently filed as `grammar`, which destroys the
learner's error profile.

### 4. Tone rules

- **Encourage before correcting.** Open with a ✅ or a warm ❌ (`"Close! Let's tune one word."`), not a bare `Wrong.`.
- **Explain why, not just what.** `"Ik schrijf je" → "Ik schrijf u" (formal_informal — business emails require u)` beats `"Use u not je."`.
- **Name the pattern.** Helps the learner generalize: `"This is the subordinate-clause rule: the verb moves."` — name it in {Native} for A1-A2 learners.
- **Celebrate progress.** `"You didn't miss this last time — well done."` when `mistakes-db` shows improvement.
- **Emojis on.** The learner's profile has `use_emojis: true` by default. Keep them.

### 5. Record the answer (one tool call, every time)

The corrected sentence already gets a 🔊 button on its own (the app finds it
by the `Correct version:` label — keep that label exactly as it is). For
anything else in the target language that is worth hearing, wrap it in
`[[say]]…[[/say]]`; see `rules.md`.

After the feedback text, call `fluent_record_answer` with the same values:

```
fluent_record_answer({
  skill: "vocabulary" | "writing" | "speaking" | "reading" | "grammar",
  exercise: "<the exercise you presented, one line>",
  learner_answer: "<their answer, verbatim>",
  score: <0-10, the one you just showed>,
  corrections: [{wrong, right, category, severity}],   // [] if the answer was right
  item_id: "<only when the exercise came from the review queue>",
  sm2_quality: <0-5, omit and it is derived as floor(score / 2)>
})
```

- The categories are the ones listed above; anything else is rejected on the
  spot with the allowed list, so fix it and call again once.
- `item_id` must be copied verbatim from the preloaded due-items list — an id
  that is not in the queue is rejected.
- The call is silent: never tell the learner about it, never paste its result.
- This is what stores the answer. Your text is for the human; this is the data.

### 6. Hand score to SM-2

After scoring, feed the score into the SM-2 update via the `fluent-sm2-calculator` skill: `quality = floor(score / 2)`.

## Examples

See `references/feedback-template.md` for fully-rendered examples (mostly-correct answer with a minor slip; critical error with severity tagging). The reference file is the authoritative version — keep it and this skill in sync if updating.

Quick pattern:

- Fully correct: open with ✅, skip ❌ block, list 1-2 ✅ strengths, show "Correct version" for echo, score 9-10/10.
- Mistakes: open with warm ❌, list each correction with severity emoji + category + brief why, show full correct version, score with breakdown if the answer is long.

## Critical Rules

- **Always use the template exactly.** Deviations break session-file parsing downstream.
- **Severity tag is mandatory** on every ❌ line. Drives spaced-repetition priority.
- **One score per answer.** Total out of 10, with optional breakdown (grammar/vocab/structure) for long answers like writing tasks.
- **Never skip the "Correct version".** Even if perfect, echoing the target form reinforces motor memory.

## Why This Matters

Structured, consistent feedback:
1. Lets the learner scan for what to fix at a glance.
2. Makes session files parseable so `PRACTICE.md` analysis + `/results` mining work.
3. Populates `mistakes-db.json` categories cleanly — which feeds spaced repetition, which drives the whole system.
