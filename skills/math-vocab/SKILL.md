---
name: math-vocab
description: Run an interactive math-facts drill — times tables, doubles and halves, equivalences (1/2 = 0,5), and key problem vocabulary ("el doble de", "quants en falten per"). Flashcard-style prompts, spaced repetition, per-answer feedback. Triggered only when the learner types /math-vocab. Reads spaced-repetition / mistakes / mastery DBs to pick facts, presents one fact at a time, scores each answer, and closes with the review-results block.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
requires: [math-feedback-formatter]
---

# Math Facts Drill Session

## Overview

Flashcard-style practice of the automatic recall layer of math: times
tables, doubles and halves, fraction/decimal/percent equivalences, and the
vocabulary that word problems turn on ("el doble de", "la meitat de", "quants
en falten per…"). One fact at a time, immediate feedback, DB update at the
end. Interleaves three modes (direct recall, reverse, equivalence/apply) to
force active recall rather than passive re-reading.

There is no translation direction here: the PROMPT is in the learner's own
language (Catalan) and the ANSWER is the math fact. Never ask for a word in
another language — the fact is the point.

## When to Use

Trigger this skill only when the learner types `/math-vocab`. The skill is gated with `disable-model-invocation: true` — a false-positive auto-trigger would launch a 15-min interactive session and mutate 6 JSON databases. Not worth the risk.

Skip this skill ONLY if the learner explicitly asks for a different activity.
Otherwise ALWAYS run a drill — even with an empty review queue:

- If items are due or mistakes exist, use the priority order in §2.
- If nothing is due (e.g. fresh profile, empty `focus_areas`), start with 10
  high-frequency facts for the learner's level and START drilling immediately.
- NEVER emit the session summary with 0 facts reviewed. If you have presented
  no facts, you have not run a session — start one instead of closing.
- **The 10-fact floor and the `session_length` target (12 if absent) are not
  suggestions — stopping earlier is not a shorter session, it is an incomplete
  one.** (Seen live, 2026-09-22, language fork: a fresh profile got the summary
  after 2 cards — a fifth of the floor.) If you are about to write the session
  summary and fewer than 10 facts have been presented on a fresh/empty-queue
  profile, or fewer than the target on any profile, do not close: pick more
  facts (fall back to more starter facts, or repeat modes on ones already
  shown) and keep going instead.

## Instructions

### 1. Load facts data

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

If the helper is unavailable, resolve `<data_dir>` via `main_paths.data_dir()` then read:

- `<data_dir>/spaced-repetition.json`
- `<data_dir>/mistakes-db.json`
- `<data_dir>/mastery-db.json`
- `<data_dir>/learner-profile.json` (for name, level, native language)

If any are missing, direct the learner to `/math-setup` and stop.

**How long the session runs.** `preferences.session_length` in the preloaded
state (12 if absent) is the learner's target number of graded exercises. **The
learner sees the count in the app** (a small `3/8` in the header), so it is
orientation, not a surprise. You do not have to keep score: the server counts
the answers it has recorded and, at the target, sends you a one-line
instruction. By default it asks you to OFFER to finish — a warm line and a
choice between the summary now or a couple more. Only a learner configured with
`session_stop: "hard"` gets closed without being asked.

### 2. Select facts

Priority order:

1. Items in `spaced-repetition.review_queue.today` with `item_type == "vocabulary"` (in FlowMath these are math facts: a table entry, an equivalence, a double).
2. Patterns from `mistakes-db.json` where `category == "facts"` and `mastery_level <= 2`.
3. New high-frequency facts matching the learner's level and the curriculum path in the preloaded state (times tables up to the level, doubles/halves, 1/2 = 0,5, 1/4 = 0,25, "quants en falten per…").

Limit: `spaced-repetition.daily_limits.review_items_per_day` (default 20).

4. If all three sources are empty (fresh profile: no due items, no mistakes,
   no focus areas), use 10 high-frequency facts for the level (e.g. ×2, ×5,
   ×10 tables and doubles to 10) and START drilling immediately. Never ask
   the learner to choose, never close the session — an empty selection is not
   an outcome.

**A fact card must have exactly one right answer.** Before writing a card,
compute the answer yourself. "6 × 7 = ?" has one answer; "think about the
7-table" has none. If you are genuinely unsure of a fact, drop it and pick a
different one — never invent or guess one to fill a slot.

### 3. Present one fact at a time

Your FIRST message in a facts session MUST be `## Fact 1/…` — never the
session summary, never a question about what to practice, never an
explanation. Start drilling immediately; talk is not practice.
Strictly alternate modes in fixed order: direct recall → reverse →
equivalence/apply → repeat. NEVER present the same mode twice in a row. If the
session history shows the last mode used, continue the rotation from there. Do
not label the mode — the format itself shows it.

- **Direct recall**: "7 × 8 = ?"
- **Reverse**: "56 = 7 × ?" / "Quants en falten per 20 si en tens 13?"
- **Equivalence/apply**: "1/2 com a decimal?", "el doble de 26", "3/4 = ? %"

**Never reuse the same carrier framing.** In the apply mode, invent a fresh
one-line context for every fact — do not fall back to one convenient template
with only the number swapped. (Seen live, 2026-09-22, language fork: twelve
cards in a row got the identical sentence with only the number changed —
technically different, but it reads as the same question twelve times.) Vary
the framing, not just the digits.

Card format (the `**Exercise:**` line is what the server's tracker reads to
fingerprint the item):

```markdown
## Fact {N}/{total}

**Exercise:** {the fact — "7 × 8 = ?", "56 = 7 × ?", "1/2 = ? (decimal)"}

**Type your answer:**
```

### 4. Feedback after each answer

Use the `math-feedback-formatter` skill's template. Score out of 10, tag severity.
A wrong fact is a `facts` category error (🔴 if the learner clearly does not
have it, 🟡 if one digit off a near-miss).

Track the answer for the end-of-session DB update:

- Add to `review_results[]` with `quality = floor(score / 2)` (see `math-sm2-calculator` skill).
- If the learner met a new fact, stage it for `new_facts[]` (WP1.9 renamed it from the language-era `new_vocabulary[]`; the persistence scripts still read the old spelling).
- If the learner made an error, stage it for `errors[]`.

Do **not** call `update-db.py` after every fact — batch at session end.

### 5. Session summary (ONLY after presenting ≥1 fact — never as a first message)

```markdown
## 📚 Facts Session Complete!

**Facts Reviewed:** {N}
**Accuracy:** {X}%
**New Facts Met:** {Y}
**Facts Mastered (→ level 5):** {Z}

**Strong:** {list facts with mastery 4-5}
**Need more practice:** {list facts with mastery 0-2}

**Next review:**
- Tomorrow: {count} facts
- This week: {count} facts

Molt bé! 🌟

### 🚀 Keep going?
{one concrete next step, e.g. "Let's drill [facts with mastery 0-2] once more."}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🔁 Review · 📚 Facts · 📝 Raonament · 📖 Problemes · 🗣️ Math talk · 📊 Stats · 🏁 End).
```

Rule: NEVER close with a bare goodbye — this summary is a pause point, not a farewell. The session ends only when the learner says so or starts something else.

### 6. Update all databases

Session fields: `session_id`, `date`, `duration_minutes`, `command_used`,
`skills_practiced: ["facts"]`, `skill_scores.facts`, `errors[]`,
`new_facts[]`, `review_results[]`, `focus_next_session[]`.

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

### 7. Report what you reviewed — REQUIRED

The learner's schedule only advances if you report it. As the LAST thing in your
closing message, after the summary, send exactly one block:

````markdown
```math:review_results
[{"item_id": "<id copied from the queue>", "quality": 4},
 {"item_id": "<id copied from the queue>", "quality": 2}]
```
````

- One entry per queue item you actually practised this session. In a facts drill that is only the facts that came from the queue — not the starter facts you introduced yourself.
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

### Example 1 — direct recall, correct

> ## Fact 1/15
>
> **Exercise:** 6 × 7 = ?
>
> **Type your answer:**

Learner: "42"

> ✅ Exacte — la taula del 6 va sola.
>
> **Correct version:**
> "6 × 7 = 42"
>
> **Score: 10/10** 🎯
>
> ---

### Example 2 — reverse mode, near miss

> ## Fact 7/15
>
> **Exercise:** 56 = 7 × ?

Learner: "9"

> ❌ A prop — 7 × 9 és 63. Compta cap enrere des de 56.
>
> **Corrections:**
> - 🟡 "7 × 9 = 56" → **"7 × 8 = 56"** (facts — the 7 × 8 fact was misremembered)
>
> **Correct version:**
> "56 = 7 × 8"
>
> **Score: 4/10** 💪 This one comes back tomorrow.

### Example 3 — session end summary

> ## 📚 Facts Session Complete!
>
> **Facts Reviewed:** 15
> **Accuracy:** 80% (12/15)
> **New Facts Met:** 3
> **Facts Mastered:** 1
>
> **Need more practice:** 7 × 8, 6 × 7, 3/4 = ? %
>
> **Next review:** Tomorrow 4 facts, this week 8 facts.
>
> Molt bé! 🌟

## Critical Rules

- **A facts card needs one right answer, and not every review item is one.**
  The review queue holds several kinds of item, and only a fact
  (`item_type: vocabulary` in the queue schema) goes on a card. An
  `error_pattern` is a procedure the learner broke — drill it as a procedure:
  a computation to do, a steps item, a choose/compare. Its id is not a fact.
  Seen live in the language fork: a rule id turned into a flashcard reading
  "what does *capitalization* mean?" — neither a question, neither teaches
  anything. Same trap here: an `order_of_operations` pattern is not "a fact
  to memorize"; it is a rule to apply on a fresh expression.
- **One fact at a time.** Wait for the learner's answer before showing the next.
- **Immediate feedback** after each — use `math-feedback-formatter`.
- **Alternate modes strictly** (direct → reverse → equivalence/apply →
  repeat); never twice the same in a row. (The general never-repeat rule comes
  from `prompts/agents/rules.md` — already in your prompt.)
- **Never a 0-fact session.** If every fact source is empty, drill 10 starter
  facts (§2 step 4). The summary with 0 facts reviewed is forbidden.
- FRIEND MODE (only if `preferences.tutor_style == "friend"`): prefer apply-mode
  framings involving `learner.interests`.
- **Never** update the DBs mid-session — batch at end.
- **Never auto-invoke.** This skill is gated; must fire only on explicit `/math-vocab`.

## Tips for the Learner (append if they seem tired or unsure)

- Review daily for best retention — spaced repetition depends on it.
- Focus time on weak facts (mastery 0-2), not already-strong ones.
- Automatic facts free up your working memory for the hard problems — that is what the drill is for.
- Say facts out loud even though you're typing.
