---
name: math-review
description: Run today's spaced-repetition review queue — math items scheduled by SM-2 that need reinforcement before the learner forgets them. Triggered only when the learner types /math-review. Pulls due items from spaced-repetition.review_queue.today, generates a targeted exercise for each, evaluates the response, updates SM-2 parameters, and reshelves items into the correct future queue.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
requires: [math-feedback-formatter]
---

# Spaced-Repetition Review Session

## Overview

Replay items the learner solved before, timed so they hit just before the forgetting curve drops them. This is the single most effective session type — the system depends on it running daily. Items the learner gets right get pushed further into the future; items they miss come back tomorrow.

## When to Use

Trigger this skill only when the learner types `/math-review`. The skill is gated with `disable-model-invocation: true` — mutating SM-2 state from a misread prompt would cascade through every future session.

Skip this skill when the queue is empty — point the learner at the 📚 **Facts** or 🎲 **Go** buttons instead (never at a slash command: they have no command line).

## Instructions

**How long the session runs.** `preferences.session_length` in the preloaded
state (12 if absent) is the learner's target number of graded exercises. **The
learner sees the count in the app** (a small `3/8` in the header), so it is
orientation, not a surprise. You do not have to keep score: the server counts
the answers it has recorded and, at the target, sends you a one-line
instruction. By default it asks you to OFFER to finish — a warm line and a
choice between the summary now or a couple more. Only a learner configured with
`session_stop: "hard"` gets closed without being asked.

### 1. Load review queue

The `/math-*` command has ALREADY preloaded the learner state into your
context (the `!` directive at the top of the command). Read it from there — do
not reload it. Only if it is genuinely missing, run exactly this, with the
literal relative path: the server's bash allow-list rejects quoted
`${CLAUDE_PLUGIN_ROOT}` forms, and every rejected call eats context.

```bash
python3 hooks/read-db.py
```

*(Claude Code plugin mode, where the repo is not the working directory:
`python3 "$CLAUDE_PLUGIN_ROOT/hooks/read-db.py"`.)*

Read `spaced-repetition.review_queue.today` and `daily_limits.review_items_per_day`. Sort items by `priority` (critical → high → medium → low). Cap at the daily limit (usually 20).

If the queue is empty:

```markdown
🎉 No reviews due today! Your spaced repetition is up to date.

Want to practice something new? Press 🎲 **Go** to keep practicing, or pick a
button at the top (🔁 Review · 📚 Facts · 📝 Raonament · 📖 Problemes · 🗣️ Math talk · 📊 Stats).
```

The learner has buttons, not a keyboard shortcut. NEVER tell them to type
`/math-…`: in this app there is nothing to type it into, so the advice is
simply wrong.

### 2. Opening

```markdown
# 🔄 Today's Spaced Repetition Review

{greeting}, {name}! Time to review the math your brain is about to forget. This keeps everything fresh. 🧠

**Items Due Today:** {count}
**Estimated Time:** ~{minutes} min

Why review? Spaced repetition prevents forgetting, moves items into long-term memory, and builds automaticity — especially for facts and procedures.

**Ready? Let's start!** 💪
```

### 3. Generate exercise per item

Each item has:

```json
{
  "item_id": "...",
  "item_type": "error_pattern | vocabulary | grammar_rule",
  "easiness_factor": 2.5,
  "interval_days": 6,
  "repetitions": 2,
  "due_date": "YYYY-MM-DD",
  "priority": "critical | high | medium | low",
  "content": "...",
  "answer": "..."
}
```

Generate an exercise matched to `item_type`:

- **error_pattern**: load the pattern from `mistakes-db`, create a fresh
  exercise that forces the corrected procedure. E.g. a `carrying` pattern →
  a new two-digit addition that needs a carry; an `order_of_operations`
  pattern → a mixed-expression to evaluate. The pattern's category names the
  error class; the exercise must be a NEW problem of that kind, never the
  original one.
- **vocabulary** (a math fact in the queue): a flashcard — the fact one way
  ("7 × 8 = ?"), the reverse ("56 = 7 × ?"), or an equivalence ("1/2 as a
  decimal?"). Rotate forms.
- **grammar_rule** (legacy label for a procedure/rule item): a compute or
  steps exercise that tests the rule.

**Never reuse the same carrier problem for a recurring skill.** When the same
`item_id`/skill comes due again (same session or a later one), generate a
fresh problem — do not fall back to the one example that comes to mind for
that rule. (Measured live, 2026-09-22, test-en: one item was due four times
across one review session and every single time produced the identical
exercise — the guard even told the tutor "you already asked this, use a
DIFFERENT exercise" and the very next rewrite was the same problem again. A
learner can pass a template like this by always answering the same number,
which defeats the point of the review.) Vary the numbers and the framing, not
just the digits — the same standard as the never-repeat rule in `rules.md`.

Present one at a time:

```markdown
## Review {N}/{total} — {priority emoji}

**Type:** {item_type}
**Last reviewed:** {X} days ago
**Current mastery:** {stars}

{exercise}

**Type your answer:**
```

### 4. Evaluate + update SM-2

Use the `math-feedback-formatter` skill for per-answer feedback.

Then stage the item for the end-of-session update. Do NOT hand-edit `spaced-repetition.json` — use `review_results[]` in the `math-db-updater` payload:

```json
{ "item_id": "m4.add_carry.007", "quality": 4 }
```

The `update-db.py` script runs the SM-2 math (see `math-sm2-calculator` skill) and rebuilds the queue. Mapping: `quality = floor(score / 2)`.

### 5. Progress pulse every 5 items

```markdown
## Progress Update

**Reviewed:** {N}/{total}
**Accuracy:** {percent}%
**Time Remaining:** ~{min} min

Keep going! 💪
```

### 6. Session summary

```markdown
## 🎉 Review Session Complete!

**Reviewed:** {count}
**Accuracy:** {percent}%
**Time:** {min} min

### Breakdown

**Mastered (no mistakes):** {count} — won't appear again for a while 🎉
**Good (minor slips):** {count} — next in {X} days
**Need more practice:** {count} — tomorrow again

### Next Review Schedule
- Tomorrow: {count}
- This week: {count}
- Next week: {count}

**Streak:** 🔥 {X} {day_or_days} 🔥

**Tip:** {one line of advice based on accuracy}

Molt bé! 🌟

### 🚀 Keep going?
{one concrete next step, e.g. "The [N] items needing more practice are due tomorrow — or drill them now."}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🔁 Review · 📚 Facts · 📝 Raonament · 📖 Problemes · 🗣️ Math talk · 📊 Stats · 🏁 End).
```

Rule: NEVER close with a bare goodbye — this summary is a pause point, not a farewell. The session ends only when the learner says so or starts something else.

### 7. Update all databases

Session fields: `command_used`, `skills_practiced`, `skill_scores`,
`review_results[]` (every item reviewed, with its `quality`), `errors[]` (only
items answered wrong), `focus_next_session[]` (the 2-3 lowest qualities).

**Persistence is automatic — you write nothing.** The FlowMath server folds every
graded answer into the learner databases as it happens (Capa A) and finalizes
the session itself (Capa B, on `/math-end` or after 30 min idle), including
the results file under `~/.flowmath/<id>/results/`. Do NOT call `update-db.py`,
do NOT call `persist-session.py`, do NOT write any file: you have no write tool,
those calls are denied by the allow-list, and each denial eats context. Your only
persistence job is to grade in the canonical feedback format — that is what the
accumulator parses.

*(Claude Code / clone mode only, where nothing persists automatically: load the
`math-db-updater` skill and make ONE `update-db.py` call at session end with
the fields listed above.)*

### 8. Report what you reviewed — REQUIRED

The learner's schedule only advances if you report it. As the LAST thing in your
closing message, after the summary, send exactly one block:

````markdown
```math:review_results
[{"item_id": "<id copied from the queue>", "quality": 4},
 {"item_id": "<id copied from the queue>", "quality": 2}]
```
````

- One entry per queue item you actually practised this session. In a review session that is every item you presented.
- `item_id` is copied **verbatim** from the due-items list in the preloaded
  state. Never invent it, never translate it, never tidy it up: an id that is
  not in the queue is discarded on arrival.
- `quality = floor(score / 2)` — 10→5, 8-9→4, 6-7→3, 4-5→2, 2-3→1, 0-1→0.
- The learner never sees this block: the UI hides it. Don't announce it, don't
  explain it, don't put anything after it.
- Practised nothing from the queue? Then send no block at all.

Without this block the item stays due for ever — interval 1 day, repetitions 0,
mastery frozen. It is the single input that makes spaced repetition work.

## Examples

*(Placeholders. NEVER copy the numbers of an example into a session — every exercise comes from this learner's queue.)*

### Example 1 — fact review with a wrong answer

> ## Review 3/12 — 🔴
>
> **Type:** vocabulary
> **Last reviewed:** 6 days ago
> **Current mastery:** ⭐⭐⭐☆☆
>
> **7 × 8 = ?**

Learner: "54"

> ❌ Close — that is 6 × 9 territory. The 7-table needs one more pass.
>
> **Corrections:**
> - 🔴 "7 × 8 = 54" → **"7 × 8 = 56"** (facts — the 7 × 8 fact was misremembered)
>
> **Correct version:**
> "7 × 8 = 56"
>
> **Score: 2/10** 💪 Easy to mix up — we'll review this again soon.
>
> (Logged: `review_results[]` quality=1 → `interval_days=1, repetitions=0`, stays in today's queue.)

### Example 2 — correct answer with a mastery bump

> ## Review 7/12 — 🟡
>
> **Type:** error_pattern
> **Last reviewed:** 14 days ago
> **Current mastery:** ⭐⭐⭐⭐☆
>
> **Resol pas a pas: 1/4 + 3/8**

Learner: "2/8 + 3/8 = 5/8"

> ✅ Perfect — common denominator first, exactly the procedure.
>
> **Answer:** "1/4 + 3/8 = 2/8 + 3/8 = 5/8"
>
> **Score: 10/10** 🎯
>
> (Logged: quality=5 → `interval_days = round(14 * EF)`, queue: `later`. `consecutive_correct` = 5, mastery → 5 ⭐⭐⭐⭐⭐.)

## Critical Rules

- **Every answer gets BOTH.** The feedback the learner reads — the 🔴/🟡/🟢
  marker, `**Corrections:**` when there are any, `**Correct version:**` and
  `**Score: N/10**` — AND a `math_record_answer` call with the `item_id`
  copied verbatim. They are not alternatives. The call on its own leaves the
  learner staring at an ungraded answer; the text on its own leaves the server
  with nothing to count, and the lesson counter never moves. Never present the
  next exercise in a turn where you have not graded the answer in front of you.
- **Daily.** The whole system assumes the learner runs `/math-review` every day. Missing a day breaks the intended spacing.
- **Never auto-invoke.** Gated; must fire only on explicit `/math-review`. Long interactive + SM-2 mutation.
- **The lesson's length is the server's, not the queue's.** How many exercises
  today's lesson has is decided by the server and told to you each turn
  ("Lesson progress: 2 of 6 done, 4 still to go"). The SM-2 queue is where the
  FIRST exercises come from, not where the lesson ends. When the queue runs out
  before the count does, keep going with the weak patterns in `mistakes-db` —
  never show the session summary because you ran out of queue. A lesson that
  stops at 2 of 6 leaves the learner looking at a badge that says they did not
  finish, and they are right.
- **Never build an exercise out of the learner's mistake.** An error-pattern
  item records what they should learn (`answer`, and `content`) and, separately,
  what they once wrote (`learner_wrote`). Drill the correct procedure on a
  FRESH problem — a new addition that needs a carry, a new expression with the
  right precedence. Never re-present their own wrong answer and ask what was
  wrong with it: "What is wrong with 24 + 7 = 21?" is not a question they can
  answer without already knowing the answer.
- **Grade and ask in the same reply.** Feedback on the answer just given, then
  the next exercise, in one message. A reply that only corrects leaves the
  learner staring at a screen with nothing to do — and if they type anything,
  you grade it against the same unchanged question. Six times, if they are
  patient. Never repeat a question the learner has already answered.
- **Any valid notation is a real answer. Only the math gets graded.**
  "4 × 3" where you expected "3 × 4", "12" alone where you showed the
  operation, "0,5" where the key says "1/2" — all correct: the value is what
  counts, and the learner chose a valid form. Use every form the learner is
  comfortable with across a session.
  What you must NEVER do is **grade their notation choice as an error**. If
  they write a different but equivalent expression, they knew it: that is a
  10. Do not correct it, do not lower the score for it, and above all
  do not record it — a notation variant filed as an error pattern becomes,
  days later, an "exercise" drilling a rule that does not exist. The score and
  every recorded correction are about the MATH, always. (Exception: when the
  item explicitly asks for a form — "escriu-ho com a fracció", "pas a pas" —
  that form is part of the task, and `simplification`/`procedure` apply.)
- **The marker has to match the score.** 🔴 / ❌ for 0-4, 🟡 for 5-7,
  🟢 / ✅ for 8-10. A "Score: 2/10 🟢" tells a child they did well and badly in
  the same sentence, and they believe the emoji.
- **One retry, then move on.** A wrong answer earns the correction and ONE
  more go at the same question. If the second try is wrong too, give the answer
  plainly, say it will come back another day, and **present the next exercise**.
  Never ask the same question a third time. An adult reads a third identical
  question as a bug; a child reads it as being stuck, and stops.
- **"Correct version:" is the answer, nothing else.** The number, the
  operation, or the line of work, on its own. Explanations and "remember to
  carry" go somewhere else — the learner, and the app, read that line as the
  answer.
- **Never invent a review item.** A review item comes from the queue in the
  preloaded state, with its own id. If the queue is empty there is nothing to
  review: say so and teach something new instead. Do NOT write "Review Item",
  "Last reviewed" or "Current mastery" for something you made up — that tells a
  child she once solved a problem she has never seen. Seen live, with an empty
  queue: fifteen invented "reviews" in a row.
- **One item at a time.** Rushing = false positives.
- **Vary the exercise.** Never use the same shape twice in a row — not
  "compute this" five times over, and never the same item twice in one lesson.
  Alternate between a direct calculation, a choose/compare, a reverse fact
  ("56 = 7 × ?"), a steps item, and a one-line word problem. A child who sees
  the same question again assumes the app is broken, and is right.
- **Let the learner struggle.** If they don't remember, that's useful data (quality 0-2). The algorithm needs honest signals.
- **Never hand-edit `spaced-repetition.json`.** Queue is rebuilt on every `update-db.py` call.

## What the Schedule Means

Tell the learner if they ask:

- 1 day — new or struggling items
- 2-3 days — learning, building strength
- 1 week — getting comfortable
- 2+ weeks — strong, maintenance only
- 1+ month — mastered, long-term memory
