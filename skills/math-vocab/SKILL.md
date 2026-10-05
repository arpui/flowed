---
name: math-vocab
description: Run an interactive vocabulary drill session with flashcard-style prompts, spaced repetition, and per-answer feedback. Triggered only when the learner types /math-vocab. Reads spaced-repetition / mistakes / mastery DBs to pick words, presents one word at a time, scores each answer, and calls math-db-updater at the end.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
requires: [math-feedback-formatter]
---

# Vocabulary Drill Session

## Overview

Flashcard-style vocabulary practice using spaced repetition. One word at a time, immediate feedback, DB update at the end. Interleaves three modes (recognition, production, cloze) to force active recall rather than passive re-reading.

## When to Use

Trigger this skill only when the learner types `/math-vocab`. The skill is gated with `disable-model-invocation: true` — a false-positive auto-trigger would launch a 15-min interactive session and mutate 6 JSON databases. Not worth the risk.

Skip this skill ONLY if the learner explicitly asks for a different activity.
Otherwise ALWAYS run a drill — even with an empty review queue:

- If items are due or mistakes exist, use the priority order in §2.
- If nothing is due (e.g. fresh profile, empty `focus_areas`), start with 10
  high-frequency starter words for the learner's level and native language.
- NEVER emit the session summary with 0 words reviewed. If you have presented
  no words, you have not run a session — start one instead of closing.
- **The 10-word floor and the `session_length` target (12 if absent) are not
  suggestions — stopping earlier is not a shorter session, it is an incomplete
  one.** (Seen live, 2026-09-22: a fresh profile, no `session_length` set, got
  the summary after 2 words — a fifth of the 10-word floor, a sixth of the
  default target.) If you are about to write the session summary and fewer than
  10 words have been presented on a fresh/empty-queue profile, or fewer than the
  target on any profile, do not close: pick more words (fall back to more
  starter words, or repeat modes on ones already shown) and keep going instead.

## Instructions

### 1. Load vocabulary data

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
- `<data_dir>/learner-profile.json` (for target_language, name, level)

If any are missing, direct the learner to `/math-setup` and stop.

**How long the session runs.** `preferences.session_length` in the preloaded
state (12 if absent) is the learner's target number of graded exercises. **The
learner sees the count in the app** (a small `3/8` in the header), so it is
orientation, not a surprise. You do not have to keep score: the server counts
the answers it has recorded and, at the target, sends you a one-line
instruction. By default it asks you to OFFER to finish — a warm line and a
choice between the summary now or a couple more. Only a learner configured with
`session_stop: "hard"` gets closed without being asked.

### 2. Select words

Priority order:

1. Items in `spaced-repetition.review_queue.today` with `item_type == "vocabulary"`.
2. Words from `mistakes-db.json` where `category == "vocabulary"` and `mastery_level <= 2`.
3. New high-frequency words matching `learner-profile.focus_areas`.

Limit: `spaced-repetition.daily_limits.review_items_per_day` (default 20).

4. If all three sources are empty (fresh profile: no due items, no mistakes,
   no focus areas), use 10 high-frequency A1 words (concrete nouns/verbs:
   water, house, eat, …) and START drilling immediately. Never ask the learner
   to choose, never close the session — an empty selection is not an outcome.

**A word labeled `{native_language}:` must actually BE in
{native_language} — check it is not still an English word before writing the
card.** (Measured live, 2026-09-22, test-en: meant to translate "full" to
Catalan ("ple"), the card instead showed `**Catalan:** fill` — not a
translation at all, just the English word "full" corrupted into the
similar-looking English word "fill", left untranslated and unrelated to the
numbers-themed context and answer key around it. A card like this teaches
nothing and cannot be graded sensibly — the learner has no way to know what is
even being asked.) Before writing the `{native_language}:` line: (1) confirm
the value is actually a {native_language} word, not an English one that
slipped through untranslated or got garbled into a similar-looking English
word; (2) confirm it is the correct translation, not a look-alike. If
genuinely unsure, drop the word and pick a different one from the queue or the
starter list — never invent or guess one to fill a slot.

### 3. Present one word at a time

Your FIRST message in a vocab session MUST be `## Word 1/…` — never the
session summary, never a question about what to practice, never an
explanation. Start drilling immediately; talk is not practice.
Strictly alternate modes in fixed order: recognition → production → cloze →
repeat. NEVER present the same mode twice in a row. If the session history
shows the last mode used, continue the rotation from there. Do not label the
mode — the format itself shows it. Both directions must appear every 3 words;
a session that only drills target→native (or only native→target) is a failure.

**Never reuse the same carrier sentence.** In Cloze (and the optional example
sentence in Recognition/Production), invent a fresh sentence for every word —
do not fall back to one convenient template with only the target word swapped.
(Seen live, 2026-09-22: a numbers review queued twelve number-words together
and every single one got "There are ___ apples on the table." with only the
number changed — technically a different word each time, but it reads as the
same question asked twelve times.) Vary the subject, the verb, and the
sentence shape, not just the blanked word.

**Recognition** (target_language → native):

```markdown
## Word {N}/{total}

**{target_language}:** {word}

**Context:** {example_sentence}

**What does it mean in {native_language}?**

**Type your answer:**
```

**Production** (native → target_language):

```markdown
## Word {N}/{total}

**{native_language}:** {word}

**Use it in a sentence (optional).**

**How do you say this in {target_language}?**

**Type your answer:**
```

**Cloze** (fill in the blank):

```markdown
## Word {N}/{total}

**Complete the sentence:**

{target_language sentence with _____ where the word goes}

**Type your answer (just the missing word):**
```

### 4. Feedback after each answer

Use the `math-feedback-formatter` skill's template. Score out of 10, tag severity.

Track the answer for the end-of-session DB update:

- Add to `review_results[]` with `quality = floor(score / 2)` (see `math-sm2-calculator` skill).
- If the learner met a new word, stage it for `new_vocabulary[]`.
- If the learner made an error, stage it for `errors[]`.

Do **not** call `update-db.py` after every word — batch at session end.

### 5. Session summary (ONLY after presenting ≥1 word — never as a first message)

```markdown
## 📚 Vocabulary Session Complete!

**Words Reviewed:** {N}
**Accuracy:** {X}%
**New Words Learned:** {Y}
**Words Mastered (→ level 5):** {Z}

**Strong:** {list words with mastery 4-5}
**Need more practice:** {list words with mastery 0-2}

**Next review:**
- Tomorrow: {count} words
- This week: {count} words

{target-language "well done"}! 🌟

### 🚀 Keep going?
{one concrete next step, e.g. "Let's drill [words with mastery 0-2] once more."}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🎓 Review · 📝 Writing · 📖 Reading · 🗣️ Speaking · 📊 Stats · 🏁 End).
```

Rule: NEVER close with a bare goodbye — this summary is a pause point, not a farewell. The session ends only when the learner says so or starts something else.

### 6. Update all databases

Session fields: `session_id`, `date`, `duration_minutes`, `command_used`,
`skills_practiced: ["vocabulary"]`, `skill_scores.vocabulary`, `errors[]`,
`new_vocabulary[]`, `review_results[]`, `focus_next_session[]`.

**Persistence is automatic — you write nothing.** The Fluent server folds every
graded answer into the learner databases as it happens (Capa A) and finalizes
the session itself (Capa B, on `/math-end` or after 30 min idle), including
the results file under `~/.fluent/<id>/results/`. Do NOT call `update-db.py`,
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

- One entry per queue item you actually practised this session. In a vocabulary drill that is only the words that came from the queue — not the starter words you introduced yourself.
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

### Example 1 — recognition drill ({Native} → {Target}; placeholders — never copy an example's language)

> ## Word 1/15
>
> **{Native}:** {a native word — e.g. the translation of "the kitchen"}
>
> **Context:** "{a sentence in the native language}"
>
> **What does it mean in {Target}?**
>
> Type your answer:

Learner: "{the correct target-language translation}"

> ✅ Exactly.
>
> **Answer:** {translation}
> **Meaning:** {brief definition}
> **Example:** "{native sentence}" ({target translation})
>
> **Score: 10/10** 🎯
>
> ---

### Example 2 — production with error

> ## Word 7/15
>
> **{Target}:** {a target word — e.g. "to write"}
>
> **How do you say this in {Native}?**

Learner: "{their attempt}"

> ✅ Correct — infinitive form.
>
> Now: can you also give the first-person present? (I write → …)

### Example 3 — session end summary

> ## 📚 Vocabulary Session Complete!
>
> **Words Reviewed:** 15
> **Accuracy:** 80% (12/15)
> **New Words Learned:** 3
> **Words Mastered:** 1
>
> **Need more practice:** {word1}, {word2}, {word3}
>
> **Next review:** Tomorrow 4 words, this week 8 words.
>
> {well done in the target language}! 🌟

## Critical Rules

- **A flashcard needs a word, and not every review item is one.** The review
  queue holds three kinds of item, and only `item_type: vocabulary` is a word to
  show on a card. An `error_pattern` is a rule the learner broke — drill it as a
  rule: a gap to fill, a sentence to correct, a choice between two forms. Its
  id is not a word. Seen live: `articles_an_apple` turned into a flashcard
  reading "**English:** an — what does it mean in català?", and
  `capitalization_English` into "what does *capitalization* mean in català?".
  Neither is a question, and neither teaches anything.


- **One word at a time.** Wait for the learner's answer before showing the next.
- **Immediate feedback** after each — use `math-feedback-formatter`.
- **Alternate modes strictly** (recognition → production → cloze → repeat);
  never twice the same in a row, never one direction only. (The general form of
  this rule, and the language-identity and never-repeat rules, come from
  `prompts/agents/rules.md` — already in your prompt.)
- **Never a 0-word session.** If every word source is empty, drill 10 A1
  starter words (§2 step 4). The summary with 0 words reviewed is forbidden.
- FRIEND MODE (only if `preferences.tutor_style == "friend"`): prefer example
  sentences involving `learner.interests`.
- **Use target language** for greetings + transitions when the learner is B1+; for A1-A2 mix target + native.
- **Never** update the DBs mid-session — batch at end.
- **Never auto-invoke.** This skill is gated; must fire only on explicit `/math-vocab`.

## Tips for the Learner (append if they seem tired or unsure)

- Review daily for best retention — spaced repetition depends on it.
- Focus time on weak words (mastery 0-2), not already-strong ones.
- Use words in sentences to build contextual memory.
- Say words out loud even though you're typing.
