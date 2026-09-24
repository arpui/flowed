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

Six parts, in this order. Nothing in this section is text to copy: it is a
description of what to write. A reply that contains a curly brace is a reply
that copied the description instead of following it.

1. One line: ✅ if the answer was right, ❌ if it was not, then a short,
   encouraging sentence in your own words.
2. `**Corrections:**` and, under it, one bullet per mistake:
   `- ❌ "what they wrote" → **"the right form"** (category — why, in a few words)`
   and one bullet for anything they got right: `- ✅ "the good part" — why it works`.
3. `**Correct version:**` on its own line, then the corrected sentence or the
   right word, in quotes, on the next line. **Only the answer** — no
   explanation, no etymology, no "this is a popular Catalan dish". The learner
   and the app both read that line as the solution.
4. `**Score: N/10**` with a real number, then an emoji and a short comment.
5. The emoji and the marker must agree with the number: ❌/🔴 for 0-4, 🟡 for
   5-7, ✅/🟢 for 8-10. "Score: 0/10 🟢" tells a child she did well and badly in
   the same sentence, and she believes the emoji.
   **A wrong answer is 0-4, never 🟡.** A different word, the wrong meaning, or
   nothing of the right answer in it ("friend" for *llibre*, "table" for
   *matí*) is 0-4. 5-7 is only for an answer that is right apart from one slip
   (a letter, an accent, an article). The schedule counts 6 and up as
   remembered: a 6 for a wrong word sends it away for days, and she is not
   asked it again until she has forgotten it.
6. Then the next exercise, in the same reply.

Here is one, filled in, for a learner writing English. Yours will say something
else entirely — the shape is what to copy, never the words:

> ❌ Almost — the verb is the only thing standing between you and a perfect
> sentence.
>
> **Corrections:**
> - ❌ "She go to school" → **"She goes to school"** (agreement — with he/she/it
>   the verb takes -s)
> - ✅ "to school" — exactly right, no article needed
>
> **Correct version:**
> "She goes to school."
>
> **Score: 7/10** 🟡 One letter away. Try the next one.

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
  corrections: one entry per mistake, each with wrong, right, category, severity  // empty if the answer was right
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
- **Don't invent a "correct" spelling in the learner's native language.** The
  model's grip on {native_language} orthography is not reliable enough to
  correct it the way it corrects {target_language} — a wrong native-language
  "correction" teaches the learner a mistake in their OWN language, which is
  worse than saying nothing. (Seen live, 2026-09-22, native language Catalan:
  learner wrote "diset" for "seventeen"; the tutor marked it wrong — correctly,
  the real word is "disset" — but then "corrected" it to "dissete", which is
  not a Catalan word at all.) Grade a native-language answer on whether the
  MEANING is unambiguous, not spelling precision; if you are not certain of the
  exact correct spelling, say the word looks off without asserting a specific
  "corrected" form, and never dock severity for a spelling variant you are not
  sure about.
- **A blank ("___") asks for what fills it, nothing already given — in every
  skill, not only vocab cloze.** "Where ___ the restroom?" with a blank before
  "is" is filled by "is", not "is the restroom" — the word "is" already sits in
  the prompt (measured live, 2026-09-22: prompt "___ is the restroom?", learner
  answered "Where", correct, and the tutor marked it 6/10 for "missing the
  verb" — the verb "is" was already in the prompt; the blank was for "Where").
  Read the prompt as a sentence WITH the blank filled by the learner's answer,
  and grade that resulting sentence — never require them to retype words that
  were not blanked. This is not vocab-specific: the same mistake happened in a
  `fluent-writing` exercise (measured live, 2026-09-22: prompt "I am ___ years
  old.", learner answered "ten" — correctly filling the blank — and the tutor
  scored it 7/10 for not also writing "I am", which was already given).
  **Whoever writes the exercise prompt must fold which one is wanted directly
  into the closing line the learner types under — never a separate line above
  it** (2026-09-23: a standalone marker line was too easy to drop; the closing
  line itself is written every single time, so the mode now rides inside it).
  The closing line is `**Type your answer (just the missing word):**` for a
  blank-fill, or `**Type your answer (the complete sentence):**` when the
  whole sentence is wanted. Use it however the exercise looks: a "___" is fine
  either way (it also shows where the word goes in a full-sentence answer) —
  this line, not the presence or absence of "___", is what tells the
  learner and the grader apart. A bare "Type your answer:" under a "___" is
  what causes this: it never says which convention applies, so grading guesses
  and sometimes guesses against its own prompt. This exact line is also
  what the web app reads to show the exercise differently by kind (2026-09-22:
  in mixed practice the learner could not tell, before answering, whether a
  "___" exercise wanted one word or the whole sentence) — do not paraphrase
  it, use the two phrases above verbatim so that still works.
  **The choice is about the ANSWER, not the exercise's label.** Measured live,
  2026-09-23: a Grammar exercise with a one-word gap ("I see ___ elephants")
  and a Vocabulary prompt with no gap at all ("Write this number in words:
  7.") both got `(the complete sentence)` anyway, defaulted to it, wrong both
  times — grading then correctly accepted the single word, contradicting its
  own closing line. It does not matter whether the exercise is called
  Writing, Grammar, or Vocabulary, or whether it has a "___" at all: if a
  correct answer is one word, a number, or a short phrase — including an
  open "write/say X" prompt with nothing blanked — use `(just the missing
  word)`. Use `(the complete sentence)` only when a correct answer has to be
  a full sentence (subject and verb of its own) for the exercise to be
  answered at all.

## Why This Matters

Structured, consistent feedback:
1. Lets the learner scan for what to fix at a glance.
2. Makes session files parseable so `PRACTICE.md` analysis + `/results` mining work.
3. Populates `mistakes-db.json` categories cleanly — which feeds spaced repetition, which drives the whole system.
