# Feedback Template

Canonical per-answer feedback format used by every FlowMath practice skill. Referenced by the `math-feedback-formatter` skill.

## Standard Template

```markdown
{✅ or ❌} {one-line encouragement or gentle correction}

**Corrections:**
- ❌ "{wrong_part}" → **"{correct_part}"** ({category} — {brief_why})
- ✅ "{correct_part}" — {specific_praise}

**Correct version:**
"{full_correct_answer}"

**Score: {X}/10** {emoji} {short_comment}

---
```

Skip the ❌ block if the answer is fully correct. Skip the ✅ block only if truly nothing was right.

## Severity markers

| Symbol | Severity | Meaning | Example |
|--------|----------|---------|---------|
| 🔴 | Critical | Wrong result or wrong method — the answer cannot stand | `wrong_operation` (added when the problem needed ÷), `procedure` (wrong sequence of steps) |
| 🟡 | Moderate | Right idea, noticeable slip | `sign` (− where + belongs), `unit` (right number, wrong or missing unit) |
| 🟢 | Minor | Low priority | `simplification` (6/8 instead of 3/4), untidy final form |

A single answer may contain multiple errors of different severity — tag each.

## Category labels

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
learner's error profile.

## Tone rules

- Encourage before correcting — open with a ✅ or a warm ❌, not a bare "Wrong."
- Explain why, not just what — "3 + 2 × 4 = 20" → "3 + 2 × 4 = 11" (order_of_operations — the multiplication happens before the addition)
- Name the pattern so the learner generalizes
- Celebrate progress — "You didn't miss this last time"
- Emojis on (learner default: `use_emojis: true`)

## Examples

*(Placeholders. NEVER copy the numbers of an example into a session — every exercise comes from this learner's bank item, weak pattern or level.)*

### Mostly correct

> ✅ Nice — the method is solid, only the final form is loose.
>
> **Corrections:**
> - 🟢 "24 + 7 = 31/1" → **"24 + 7 = 31"** (simplification — the answer is a whole number, write it as one)
> - ✅ "24 + 7" — perfect setup
>
> **Correct version:**
> "24 + 7 = 31"
>
> **Score: 9/10** 🎯 One tidy-up away — don't sweat it.

### Critical error

> ❌ Close, but one pattern is costing you — it has shown up twice this week.
>
> **Corrections:**
> - 🔴 "1/4 + 3/8 = 4/12" → **"1/4 + 3/8 = 2/8 + 3/8 = 5/8"** (wrong_operation — denominators are never added; find the common denominator first)
> - 🔴 "3 + 2 × 4 = 20" → **"3 + 2 × 4 = 11"** (order_of_operations — multiply before adding)
> - ✅ "3 + 2 × 4" — you copied the expression correctly
>
> **Correct version:**
> "3 + 2 × 4 = 11"
>
> **Score: 3/10** 💪 Two patterns to drill — both are on the review queue now.

Each correction is one line: marker, quoted wrong text, `→`, bold quoted
correction, then `(category — why)` in parentheses. The parenthesis is not
decoration: without it the correction never reaches `mistakes-db`.
