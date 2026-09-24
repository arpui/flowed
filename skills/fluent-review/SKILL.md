---
name: fluent-review
description: Run today's spaced-repetition review queue — items scheduled by SM-2 that need reinforcement before the learner forgets them. Triggered only when the learner types /fluent-review. Pulls due items from spaced-repetition.review_queue.today, generates a targeted exercise for each, evaluates the response, updates SM-2 parameters, and reshelves items into the correct future queue.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
requires: [fluent-feedback-formatter]
---

# Spaced-Repetition Review Session

## Overview

Replay items the learner learned before, timed so they hit just before the forgetting curve drops them. This is the single most effective session type — the system depends on it running daily. Items the learner gets right get pushed further into the future; items they miss come back tomorrow.

## When to Use

Trigger this skill only when the learner types `/fluent-review`. The skill is gated with `disable-model-invocation: true` — mutating SM-2 state from a misread prompt would cascade through every future session.

Skip this skill when the queue is empty — point the learner at the 📚 **Vocabulary** or 🎲 **Surprise me!** buttons instead (never at a slash command: they have no command line).

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

The `/fluent-*` command has ALREADY preloaded the learner state into your
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
button at the top (🎓 Review · 📝 Writing · 📖 Reading · 🗣️ Speaking · 📊 Stats).
```

The learner has buttons, not a keyboard shortcut. NEVER tell them to type
`/fluent-…`: in this app there is nothing to type it into, so the advice is
simply wrong.

### 2. Opening

```markdown
# 🔄 Today's Spaced Repetition Review

{greeting in {Target}}, {name}! Time to review items your brain is about to forget. This keeps everything fresh. 🧠

**Items Due Today:** {count}
**Estimated Time:** ~{minutes} min

Why review? Spaced repetition prevents forgetting, moves items into long-term memory, and builds automaticity.

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

- **error_pattern**: load the pattern from `mistakes-db`, create a scenario that forces the correct form. E.g. `formal_informal_confusion` → ask the learner to complete a formal email opening.
  Check `learner_wrote` first: if it is in a DIFFERENT language than
  `content`/`answer`, this is a translation-direction item, not a same-language
  one — `content`/`answer` being in {native_language} does not mean
  {native_language} is what is being tested. Frame it as translation: show the
  {target_language} side (from `learner_wrote`, or a fresh sentence using the
  same words) and ask the learner to produce the {native_language} form, or
  show the {native_language} `content` and ask "How do you say this in
  {target_language}?" — never present the {native_language} sentence alone as
  a same-language fill-in-the-blank (measured live, 2026-09-22, test-en: a
  translation item became "Complete the sentence with the correct verb form:
  'Hi ___ dues pomes sobre la taula.'", with no {target_language} anywhere,
  which reads as a Catalan grammar test). If `learner_wrote` is missing or in
  the same language as `content`, treat it as an ordinary same-language
  error pattern as before.
- **vocabulary**: recognition (target → native), production (native → target), or cloze — rotate modes.
- **grammar_rule**: a fill-in or error-correction exercise that tests the rule.

**Never reuse the same carrier sentence for a recurring skill.** When the same
`item_id`/skill comes due again (same session or a later one), invent a fresh
sentence — do not fall back to the one example that comes to mind for that
rule. (Measured live, 2026-09-22, test-en: "Days, months and seasons" was
due four times across one review session and every single time produced the
identical exercise "My birthday is in ___." — the guard even told the tutor
"you already asked this, use a DIFFERENT exercise" and the very next rewrite
was the same sentence again. A learner can pass a template like this by
always answering the same word, which defeats the point of the review.) Vary
the subject, the verb and the sentence shape, not just the blanked word —
the same standard as Vocabulary's cloze mode.

Present one at a time:

```markdown
## Review {N}/{total} — {priority emoji}

**Type:** {item_type}
**Last reviewed:** {X} days ago
**Current mastery:** {stars}

{exercise}

{"**Type your answer (just the missing word):**" if `exercise` blanks out one word, or
"**Type your answer (the complete sentence):**" if it wants the corrected sentence whole —
see fluent-feedback-formatter's blank-marker rule. Never the bare "Type your
answer:" when `exercise` contains "___".}
```

### 4. Evaluate + update SM-2

Use the `fluent-feedback-formatter` skill for per-answer feedback.

Then stage the item for the end-of-session update. Do NOT hand-edit `spaced-repetition.json` — use `review_results[]` in the `fluent-db-updater` payload:

```json
{ "item_id": "vocab_{word}", "quality": 4 }
```

The `update-db.py` script runs the SM-2 math (see `fluent-sm2-calculator` skill) and rebuilds the queue. Mapping: `quality = floor(score / 2)`.

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

**Streak:** 🔥 {X} {day/days} 🔥

**Tip:** {one line of advice based on accuracy}

{target-language well done}! 🌟

### 🚀 Keep going?
{one concrete next step, e.g. "The [N] words needing more practice are due tomorrow — or drill them now."}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🎓 Review · 📝 Writing · 📖 Reading · 🗣️ Speaking · 📊 Stats · 🏁 End).
```

Rule: NEVER close with a bare goodbye — this summary is a pause point, not a farewell. The session ends only when the learner says so or starts something else.

### 7. Update all databases

Session fields: `command_used`, `skills_practiced`, `skill_scores`,
`review_results[]` (every item reviewed, with its `quality`), `errors[]` (only
items answered wrong), `focus_next_session[]` (the 2-3 lowest qualities).

**Persistence is automatic — you write nothing.** The Fluent server folds every
graded answer into the learner databases as it happens (Capa A) and finalizes
the session itself (Capa B, on `/fluent-end` or after 30 min idle), including
the results file under `~/.fluent/<id>/results/`. Do NOT call `update-db.py`,
do NOT call `persist-session.py`, do NOT write any file: you have no write tool,
those calls are denied by the allow-list, and each denial eats context. Your only
persistence job is to grade in the canonical feedback format — that is what the
accumulator parses.

*(Claude Code / clone mode only, where nothing persists automatically: load the
`fluent-db-updater` skill and make ONE `update-db.py` call at session end with
the fields listed above.)*

### 8. Report what you reviewed — REQUIRED

The learner's schedule only advances if you report it. As the LAST thing in your
closing message, after the summary, send exactly one block:

````markdown
```fluent:review_results
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

*(Placeholders. NEVER copy the language of an example into a session — derive both language names from the learner's profile, every turn.)*

### Example 1 — vocabulary review with a wrong answer

> ## Review 3/12 — 🔴
>
> **Type:** vocabulary
> **Last reviewed:** 6 days ago
> **Current mastery:** ⭐⭐⭐☆☆
>
> **{Target}:** {the word}
>
> **What does it mean in {Native}?**

Learner: *(a near-miss — a word from the same semantic field)*

> ❌ Close — those two are related, but not the same.
>
> **Corrections:**
> - 🟡 "{their answer}" → **"{the right translation}"** (vocabulary — {the word} is X; {their answer} is Y)
>
> **Correct version:**
> "{the word}" = {the right translation}.
>
> **Score: 3/10** 💪 Easy to mix up — we'll review this again soon.
>
> (Logged: `review_results[]` quality=1 → `interval_days=1, repetitions=0`, stays in today's queue.)

### Example 2 — correct answer with a mastery bump

> ## Review 7/12 — 🟡
>
> **Type:** grammar_rule
> **Last reviewed:** 14 days ago
> **Current mastery:** ⭐⭐⭐⭐☆
>
> **Complete:** "{a sentence in {Target} with a gap where the rule applies}"

Learner: *(the correct form)*

> ✅ Perfect — that rule is locked in.
>
> **Answer:** "{the complete sentence}"
>
> **Score: 10/10** 🎯
>
> (Logged: quality=5 → `interval_days = round(14 * EF)`, queue: `later`. `consecutive_correct` = 5, mastery → 5 ⭐⭐⭐⭐⭐.)

## Critical Rules

- **Every answer gets BOTH.** The feedback the learner reads — the 🔴/🟡/🟢
  marker, `**Corrections:**` when there are any, `**Correct version:**` and
  `**Score: N/10**` — AND a `fluent_record_answer` call with the `item_id`
  copied verbatim. They are not alternatives. The call on its own leaves the
  learner staring at an ungraded answer; the text on its own leaves the server
  with nothing to count, and the lesson counter never moves. Never present the
  next exercise in a turn where you have not graded the answer in front of you.
- **Daily.** The whole system assumes the learner runs `/fluent-review` every day. Missing a day breaks the intended spacing.
- **Never auto-invoke.** Gated; must fire only on explicit `/fluent-review`. Long interactive + SM-2 mutation.
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
  what they once wrote (`learner_wrote`). Drill the correct form — a gap to
  fill, a sentence to rewrite, a translation. Never ask them what the correct
  word for their own typo is: "What is the correct English word for 'ben'?" is
  not a question, because "ben" is not a word.
- **Grade and ask in the same reply.** Feedback on the answer just given, then
  the next exercise, in one message. A reply that only corrects leaves the
  learner staring at a screen with nothing to do — and if they type anything,
  you grade it against the same unchanged question. Six times, if they are
  patient. Never repeat a question the learner has already answered.
- **Both directions are real exercises. Only one language gets graded.**
  Asking for the native word ("**Word:** Hello — what is it in {Native}?") is a
  recognition exercise and a perfectly good one: it tests whether they know what
  the English word means. Asking them to produce the English is a production
  exercise. Use both.
  What you must NEVER do is **grade their own language**. If they write the
  right meaning with a missing accent or a typo in {Native}, they knew the word:
  that is a 10. Do not correct it, do not lower the score for it, and above all
  do not record it — a {Native} spelling mistake filed as an error pattern
  becomes, days later, an "exercise" drilling their own language back at them.
  The score and every recorded correction are about the {Target}, always.
- **The marker has to match the score.** 🔴 / ❌ for 0-4, 🟡 for 5-7,
  🟢 / ✅ for 8-10. A "Score: 2/10 🟢" tells a child they did well and badly in
  the same sentence, and they believe the emoji.
- **One retry, then move on.** A wrong answer earns the correction and ONE
  more go at the same question. If the second try is wrong too, give the answer
  plainly, say it will come back another day, and **present the next exercise**.
  Never ask the same question a third time. An adult reads a third identical
  question as a bug; a child reads it as being stuck, and stops.
- **"Correct version:" is the answer, nothing else.** The word or the sentence,
  on its own. Explanations, etymology and "it is a popular Catalan dish" go
  somewhere else — the learner, and the app, read that line as the answer.
- **Never invent a review item.** A review item comes from the queue in the
  preloaded state, with its own id. If the queue is empty there is nothing to
  review: say so and teach something new instead. Do NOT write "Review Item",
  "Last reviewed" or "Current mastery" for something you made up — that tells a
  child she once knew a word she has never seen, and half the time the word is
  not even real. Seen live, with an empty queue: fifteen invented "reviews" in a
  row, including a Spanish word and one that does not exist in any language.
- **One item at a time.** Rushing = false positives.
- **Vary the exercise.** Never use the same shape twice in a row — not
  "Rewrite this sentence correctly" five times over, and never the same item
  twice in one lesson. Alternate between rewriting, filling a gap, translating,
  answering a question about a short text, and choosing between two forms. A
  child who sees the same question again assumes the app is broken, and is
  right.
- **Let the learner struggle.** If they don't remember, that's useful data (quality 0-2). The algorithm needs honest signals.
- **Never hand-edit `spaced-repetition.json`.** Queue is rebuilt on every `update-db.py` call.

## What the Schedule Means

Tell the learner if they ask:

- 1 day — new or struggling items
- 2-3 days — learning, building strength
- 1 week — getting comfortable
- 2+ weeks — strong, maintenance only
- 1+ month — mastered, long-term memory
