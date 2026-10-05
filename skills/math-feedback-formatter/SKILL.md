---
name: math-feedback-formatter
description: Canonical feedback template for every learner answer in the FlowMath system — celebrate correct parts, correct mistakes with math category and brief explanation, show the full correct version, score out of 10, and classify severity (🔴 critical / 🟡 moderate / 🟢 minor). Use in every practice session (math-learn, math-review, math-vocab, math-writing, math-speaking, math-reading) immediately after the learner submits an answer.
---

# Feedback Formatter

## Overview

Every practice session ends each turn with immediate feedback. Consistency matters — the learner builds mental models from the structure, and error patterns we mine from session files depend on predictable markers (❌, ✅, severity emoji). This skill defines the single feedback shape used across all FlowMath practice skills.

## When to Use

Load this skill whenever the tutor:

- Grades a learner answer in any practice skill (`math-learn`, `math-vocab`, `math-writing`, `math-speaking`, `math-reading`, `math-review`).
- Needs to classify an error by severity before writing to `mistakes-db.json`.
- Needs to tag an error by category (calculation, sign, carrying, etc.).

Skip this skill for non-feedback output (greetings, summaries, progress reports).

## Instructions

### 1. Standard template

Six parts, in this order. Nothing in this section is text to copy: it is a
description of what to write. A reply that contains a curly brace is a reply
that copied the description instead of following it.

1. One line: ✅ if the answer was right, ❌ if it was not, then a short,
   encouraging sentence in your own words.
2. `**Corrections:**` and, under it, one bullet per mistake:
   `- ❌ "what they wrote" → **"the right form"** (category — why, in a few words)`
   and one bullet for anything they got right: `- ✅ "the good part" — why it works`.
   For math, the quoted parts are numbers, operations or whole lines of work —
   e.g. ❌ "24 + 7 = 32" → **"24 + 7 = 31"**.
3. `**Correct version:**` on its own line, then the correct answer or the
   correct line of work, in quotes, on the next line. **Only the answer** — no
   explanation, no "and remember to carry". The learner and the app both read
   that line as the solution.
4. `**Score: N/10**` with a real number, then an emoji and a short comment.
5. The emoji and the marker must agree with the number: ❌/🔴 for 0-4, 🟡 for
   5-7, ✅/🟢 for 8-10. "Score: 0/10 🟢" tells a child she did well and badly in
   the same sentence, and she believes the emoji.
   **A wrong result is 0-4, never 🟡.** The wrong number, the wrong operation,
   or nothing of the right answer in it ("32" for 24 + 7, "4/12" for
   1/4 + 3/8) is 0-4. 5-7 is only for an answer that is right apart from one
   slip (a transposed digit, a missing unit, an unsimplified fraction). The
   schedule counts 6 and up as remembered: a 6 for a wrong result sends it
   away for days, and it is not asked again until it is forgotten.
6. Then the next exercise, in the same reply.

Here is one, filled in, for a learner doing two-digit addition. Yours will say
something else entirely — the shape is what to copy, never the words:

> ❌ Almost — the setup is perfect, only the carried ten went missing.
>
> **Corrections:**
> - ❌ "24 + 7 = 32" → **"24 + 7 = 31"** (carrying — the tens digit did not
>   carry)
> - ✅ "24 + 7" — exactly the right operation
>
> **Correct version:**
> "24 + 7 = 31"
>
> **Score: 7/10** 🟡 One digit away. Try the next one.

Skip the ❌ block if the answer is fully correct. Skip the ✅ block only if truly nothing was right (rare — usually at least the operation or the setup was right).

### 2. Tag severity on every error

| Symbol | Severity | Meaning | Example |
|--------|----------|---------|---------|
| 🔴 | Critical | Wrong result or wrong method — the answer cannot stand | `wrong_operation` (added instead of multiplied), `procedure` (steps in the wrong order) |
| 🟡 | Moderate | Right idea, noticeable slip | `sign` (+ instead of −), `unit` (answer right, unit missing or wrong) |
| 🟢 | Minor | Low priority | `simplification` (6/8 instead of 3/4), untidy final form |

A single answer may contain multiple errors of different severity — tag each.

### 3. Use these category labels

These feed `mistakes-db.json`:

- `calculation` — arithmetic slip: right method, wrong number
- `sign` — a +/− (or >/<) changed or dropped
- `place_value` — digits misaligned: units / tens / hundreds
- `carrying` — carry or borrow forgotten or done wrong
- `order_of_operations` — steps done in the wrong precedence order
- `wrong_operation` — right numbers, wrong operation (+ instead of ×)
- `procedure` — wrong sequence of steps for the task
- `facts` — basic fact not recalled: times tables, doubles, halves
- `simplification` — fraction not reduced / answer not in the required form
- `unit` — missing or wrong unit
- `misread` — the problem statement was read wrong
- `incomplete` — work left half-done

Use these names exactly, in lowercase with underscores. They are the single
source of truth (`ERROR_CATEGORIES` in `hooks/db_schema.py`): a label
that is not on the list is silently filed as `calculation`, which destroys the
learner's error profile. The `math_record_answer` tool rejects an unknown
category on the spot — but the prose fallback parser does not, so the words in
your feedback matter just as much.

### 4. Tone rules

- **Encourage before correcting.** Open with a ✅ or a warm ❌ (`"Close! The method was right."`), not a bare `Wrong.`.
- **Explain why, not just what.** `"3 + 2 × 4 = 20" → "3 + 2 × 4 = 11" (order_of_operations — multiply before adding)` beats `"Do the × first."`.
- **Name the pattern.** Helps the learner generalize: `"This is the carrying rule: the extra ten joins the tens column."` — name it in the learner's own language for younger learners.
- **Celebrate progress.** `"You didn't miss this last time — well done."` when `mistakes-db` shows improvement.
- **Emojis on.** The learner's profile has `use_emojis: true` by default. Keep them.

### 5. Record the answer (one tool call, every time)

After the feedback text, call `math_record_answer` with the same values:

```
math_record_answer({
  skill: "computation" | "steps" | "problems" | "reasoning" | "facts",
  exercise: "<the exercise you presented, one line>",
  learner_answer: "<their answer, verbatim>",
  score: <0-10, the one you just showed>,
  corrections: one entry per mistake, each with wrong, right, category, severity  // empty if the answer was right
  item_id: "<only when the exercise came from the review queue>",
  sm2_quality: <0-5, omit and it is derived as floor(score / 2)>
})
```

- Pick the `skill` label that matches the practice: `computation`/`steps` for
  closed calculation items, `facts` for the drill, `reasoning` for explaining
  or inventing, `problems` for word problems. NOTE (WP1.7): the app's
  per-button counters and the progress panel still key on the language-era
  names (writing/reading/speaking) taken from the button pressed, not from
  this field — the label here is for the record itself.
- The categories are the ones listed above; anything else is rejected on the
  spot with the allowed list, so fix it and call again once.
- `item_id` must be copied verbatim from the preloaded due-items list — an id
  that is not in the queue is rejected.
- The call is silent: never tell the learner about it, never paste its result.
- This is what stores the answer. Your text is for the human; this is the data.

### 6. Hand score to SM-2

After scoring, feed the score into the SM-2 update via the `math-sm2-calculator` skill: `quality = floor(score / 2)`.

### 7. Blank-marker lines (bank items only)

The server's bank cards end with one of two exact lines, and the web app reads
them to show the exercise differently:

- `**Type your answer (just the missing word):**` — the answer is the single
  thing that fills the blank, nothing already given. "25 + ___ = 31" is
  answered "6", not "25 + 6 = 31" — never require retyping what was not
  blanked.
- `**Type your answer (the complete sentence):**` — a full-sentence answer is
  wanted.

Use these phrases verbatim when you write a blank-style exercise yourself;
never paraphrase them. Most math exercises have no blank at all — a number,
an operation or a short line of work is the answer — and those simply close
with `**Type your answer:**`.

## Examples

See `references/feedback-template.md` for fully-rendered examples (mostly-correct answer with a minor slip; critical error with severity tagging). The reference file is the authoritative version — keep it and this skill in sync if updating.

Quick pattern:

- Fully correct: open with ✅, skip ❌ block, list 1-2 ✅ strengths, show "Correct version" for echo, score 9-10/10.
- Mistakes: open with warm ❌, list each correction with severity emoji + category + brief why, show full correct version, score with breakdown if the answer is a multi-step trace.

## Critical Rules

- **Always use the template exactly.** Deviations break session-file parsing downstream.
- **Severity tag is mandatory** on every ❌ line. Drives spaced-repetition priority.
- **One score per answer.** Total out of 10, with optional breakdown (setup / calculation / form) for long multi-step answers.
- **Never skip the "Correct version".** Even if perfect, echoing the right form reinforces the pattern.
- **Grade the math, not the Catalan.** The problem statement and the learner's
  explanation are in their own language. A spelling or grammar slip in the
  learner's Catalan explanation is not a math error: do not correct it in the
  ❌ block, do not dock the score for it, and above all never file it in
  `mistakes-db` — a native-language slip filed as an error pattern becomes,
  days later, an exercise drilling their own language back at them. Grade
  whether the MATH and the reasoning are right; if the wording is genuinely
  ambiguous enough to change the math, that is a `misread`, not a language
  correction.
- **A wrong result is 0-4, never 🟡.** See §1 point 5: the schedule counts 6
  and up as remembered, and a soft score for a wrong answer hides it for days.

## Why This Matters

Structured, consistent feedback:
1. Lets the learner scan for what to fix at a glance.
2. Makes session files parseable so the results mining works.
3. Populates `mistakes-db.json` categories cleanly — which feeds spaced repetition, which drives the whole system.
