# Feedback Template

Canonical per-answer feedback format used by every Fluent practice skill. Referenced by the `math-feedback-formatter` skill.

## Standard Template

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

Skip the ❌ block if the answer is fully correct. Skip the ✅ block only if truly nothing was right.

## Severity markers

| Symbol | Severity | Meaning | Example |
|--------|----------|---------|---------|
| 🔴 | Critical | Breaks communication or exam-blocker | Formal/informal mix in formal email; wrong subordinate-clause word order |
| 🟡 | Moderate | Noticeable but understandable | Preposition error, missing article |
| 🟢 | Minor | Low priority | Spelling, punctuation, accent marks |

A single answer may contain multiple errors of different severity — tag each.

## Category labels

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

## Tone rules

- Encourage before correcting — open with a ✅ or a warm ❌, not a bare "Wrong."
- Explain why, not just what — "{informal form}" → "{polite form}" (formal_informal — a business email needs the polite form)
- Name the pattern so the learner generalizes
- Celebrate progress — "You didn't miss this last time"
- Emojis on (learner default: `use_emojis: true`)

## Examples

*(Placeholders. NEVER copy the language of an example into a session — derive both language names from the learner's profile, every turn.)*

### Mostly correct

> ✅ Nice — the past tense is solid.
>
> **Corrections:**
> - 🟢 "{a word from a third language}" → **"{the {Target} word}"** (vocabulary — small slip, that word is not {Target})
> - ✅ "{their auxiliary + participle}" — perfect
>
> **Correct version:**
> "{the full corrected sentence in {Target}}"
>
> **Score: 9/10** 🎯 One minor swap — don't sweat it.

### Critical error

> ❌ Close, but one pattern is costing you points on the exam.
>
> **Corrections:**
> - 🔴 "{their informal opening}" → **"{the polite opening}"** (formal_informal — a formal text needs the polite form)
> - 🔴 "{their subordinate clause}" → **"{the corrected clause}"** (word_order — the verb moves under subordination)
> - ✅ "{the part they got right}" — correct
>
> **Correct version:**
> "{the full corrected sentence in {Target}}"
>
> **Score: 5/10** 💪 Two patterns to drill — both are on the review queue now.

Each correction is one line: marker, quoted wrong text, `→`, bold quoted
correction, then `(category — why)` in parentheses. The parenthesis is not
decoration: without it the correction never reaches `mistakes-db`.
