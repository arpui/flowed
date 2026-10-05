---
name: math-reading
description: Run an interactive reading comprehension session with a short target-language text followed by main-idea, detail, vocabulary-in-context, inference, and true/false questions. Triggered only when the learner types /math-reading. Presents the text, waits for the learner to read, then asks questions one at a time with immediate feedback, and optionally adds new vocabulary to the spaced-repetition queue.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
---

# Reading Comprehension Session

## Overview

Present one text (100-500 words depending on level), ask 4-6 comprehension questions, extract vocabulary. Builds passive-to-active bridge: learners decode target-language writing, then answer questions that force recall.

## When to Use

Trigger this skill only when the learner types `/math-reading`. The skill is gated with `disable-model-invocation: true` — 15-20 min interactive session with DB writes should never start from an ambiguous prompt.

Skip this skill below A1 mastery 3 — shorter flashcard drills (`/math-vocab`) are more appropriate for very early learners.

## Instructions

### 1. Load context

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

Need: `learner-profile` (level, target language, interests), `mastery-db.skills_mastery.reading`.

**The text is in `target_language`, never in `native_language` — read both fields
from the preloaded state before writing a single word.** A Catalan-native
learner of English reads an ENGLISH text with ENGLISH questions; nothing in this
session is in Catalan except, if at all, a gloss the learner explicitly asks
for. (Seen live, 2026-09-22: `target_language: "English"`, `native_language:
"Catalan"`, and the tutor opened with "# 👀 Catalan Reading Practice" and wrote
the whole passage in Catalan — the reverse of every field it had just read. If
you notice you are about to write a sentence in the learner's native language
for the main text or a question, stop and check `target_language` again.)

### 2. Opening

```markdown
# 👀 {target_language} Reading Practice

{greeting in {Target}}, {name}!

Today we're practicing **reading comprehension**. I'll show you a short {target_language} text, then ask you questions about it.

**Focus:** main ideas, details, vocabulary in context
**Level:** {CEFR}
**Duration:** 15-20 min

**Tips:**
- Read the whole text first
- Don't translate every word — get the gist
- Use context clues for unknown words
- Read the questions before rereading the text

**Ready? Let's read!** 📖
```

### 3. Pick text type + length

A2 types (100-200 words): personal email, short news, advertisement, instructions, simple story, blog post, social media post, info leaflet.

B1 (200-350 words): opinion pieces, longer narratives, structured guides.

B2+ (350-500): editorials, technical explanations, interviews.

Match the topic to `learner-profile.focus_areas` when possible.

### 4. Present the text

```markdown
## 📄 Reading Text {N}

**Topic:** {topic}
**Type:** {text_type}
**Length:** ~{word_count} words

---

{target-language text — clean formatting, no inline translation}

---

Take your time. When you're done, type **"ready"**.
```

### 5. Question sequence (one at a time)

Rotate across these types. The headings below are placeholders: write them in
the learner's target language, never in the language of this file.

**Main idea:**
```markdown
## {"Question 1: Main idea" — the heading written in {Target}}

{question in target language}

a) {option 1}
b) {option 2}
c) {option 3}

**Type a, b, or c:**
```

**Details:**
```markdown
## {"Question 2: Detail" — in {Target}}

{specific question about the text}

**Type your answer:**
```

**Vocabulary in context:**
```markdown
## {"Question 3: Vocabulary in context" — in {Target}}

In the text it says "{word/phrase}". What does this mean?

a) {meaning 1}
b) {meaning 2}
c) {meaning 3}
```

**Inference:**
```markdown
## {"Question 4: Inference" — in {Target}}

{question requiring inference — not directly stated}

**Answer in {target language}:**
```

**True / false:**
```markdown
## {"Question 5: True or false" — in {Target}}

{statement}

**Type your answer:**
```

### 6. Feedback per question

```markdown
{✅ or ❌}

**Answer:** {correct_answer}

**Explanation:** {why — reference the text}

{If incorrect: **The text says:** "{relevant_quote}"}

**Score: {X}/10**

---
```

### 7. Vocabulary review

After the questions:

```markdown
## 📚 New Vocabulary from the Text

| {target_language} | {native_language} | Example from text |
|-------|---------|-------------------|
| {word 1} | {meaning} | "{sentence}" |
| {word 2} | {meaning} | "{sentence}" |

**Save these for future review?** (They'll enter spaced repetition.)

Type "yes" to add, "no" to skip.
```

If yes, stage each word for `new_vocabulary[]` in the end-of-session DB update.

**Never skip straight to the summary without showing this table first.**
(Measured live, 2026-09-22, test-en, A0 profile: a 150-word text, 80% accuracy
— meaning real unfamiliar words were in play — went straight from the last
question's feedback to "New Words Added: 0", no table, no yes/no asked. At
A0 a text of that length is not free of new words; the step was skipped, not
genuinely empty.) The table can legitimately have zero rows for an advanced
learner who already knows the text's whole vocabulary — but for anyone below
B1, assume there ARE unfamiliar words and look for them before concluding
there are none.

### 8. Session summary

```markdown
## 📊 Reading Session Complete!

**Text:** {title/topic}
**Length:** {words} words
**Questions:** {N}
**Accuracy:** {percent}%

### Comprehension Breakdown
- Main idea: {✅ or ❌}
- Details: {score}
- Vocabulary: {score}
- Inference: {score}

### New Words Added: {count}
{list}

### For Next Time
- {suggestion based on which question type was weakest}

**{target-language well done}!** 📖✨

### 🚀 Keep going?
{one concrete next step, e.g. "More [weakest question type] practice would help."}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🎓 Review · 📝 Writing · 📖 Reading · 🗣️ Speaking · 📊 Stats · 🏁 End).
```

Rule: NEVER close with a bare goodbye — this summary is a pause point, not a farewell. The session ends only when the learner says so or starts something else.

### 9. Update all databases

Session fields: `command_used`, `skills_practiced: ["reading"]`,
`skill_scores.reading`, `errors[]` (per question-type weakness: `comprehension`,
`vocabulary`), `new_vocabulary[]` (words the learner chose to save),
`focus_next_session[]`.

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

## Examples

*(Placeholders. NEVER copy the language of an example into a session — derive both language names from the learner's profile, every turn.)*

### Example 1 — reading text

> ## 📄 Reading Text 1
>
> **Topic:** Making weekend plans
> **Type:** Personal email
> **Length:** ~75 words
>
> ---
>
> {a ~75-word personal email in {Target}, level A2: a greeting, a proposal with a
> date and a time, a place to meet, one practical remark, a closing}
>
> ---
>
> Take your time. When you're done, type **"ready"**.

### Example 2 — main-idea question on the above

> ## {"Question 1: Main idea", written in {Target}}
>
> {the question, in {Target}}
>
> a) {a plausible wrong option}
> b) {the correct option}
> c) {a detail from the text, but not the main idea}

Learner: "b"

> ✅ Correct!
>
> **Answer:** b) {the correct option}
>
> **Explanation:** The email's core is the meet-up plan — date, time, place and
> activity. The practical remark is a secondary detail.
>
> **Score: 10/10**

## Critical Rules

- **Wait for "ready"** before asking the first question. Rushing the reading step defeats the purpose.
- **One question at a time.** Multiple at once invites skimming.
- **Ask questions in the target language** (at least from A2 up). Reading-comprehension checks should happen in the same language as the text.
- **Quote the text** in explanations so the learner can trace the answer back to the source.
- **Vocabulary opt-in.** Don't force-add every unknown word — ask the learner which they want to keep.
- FRIEND MODE (only if `preferences.tutor_style == "friend"`): prefer texts touching `learner.interests` when choosing passages.
- **Never auto-invoke.** Gated; must fire only on explicit `/math-reading`.

## Text Bank

Keep no fixed sample texts here: a stored text in one language is exactly what
makes the tutor drift away from the learner's target language, and a reused text
is a repeated exercise (forbidden).

Generate each text fresh, in the profile's target language, for the CEFR level
and (in friend mode) the learner's interests. Useful text types at A2-B1:
personal email, advertisement or course flyer, short news item, notice or set of
instructions, informal message thread. Never reuse a text presented in the last
24h — check the session history first.
