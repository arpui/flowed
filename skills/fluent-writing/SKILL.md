---
name: fluent-writing
description: Run an interactive writing practice session (emails, letters, forms, short texts) with systematic error analysis, category-tagged corrections, and detailed feedback. Triggered only when the learner types /fluent-writing. Selects a scenario matched to mastery, lets the learner compose, then analyzes grammar, register, vocabulary, structure, and spelling before updating all databases.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
requires: [fluent-feedback-formatter]
---

# Writing Practice Session

## Overview

Full-text writing practice with systematic correction. One scenario per session, detailed feedback broken down by severity and category, DB update at end. Mastery-driven scenario selection keeps the task at the right level — challenging, not frustrating.

## When to Use

Trigger this skill only when the learner types `/fluent-writing`. The skill is gated with `disable-model-invocation: true` — a 15-20 min interactive session with DB writes should never start from an ambiguous prompt.

Writing is the one practice where the learner writes her OWN words. Closed
exercises — a gap to fill, a sentence to complete — belong to 🎲 Go, which
drills the same structures. Never set one here, at any level: at A1 the task is
tiny, but it is still hers to write.

## Instructions

### 1. Load context

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

Need: `learner-profile` (level, target language, focus areas), `mistakes-db` (weak writing patterns), `mastery-db` (writing sub-skills).

### 2. Pick the task

**A1 and A2 — guided writing, one short task at a time.** A topic from her own
life (her pet, her family, her school, her breakfast, her favourite game) and
the one or two words she should use. If the server's note gives a *Writing
frame*, the words to use come from it — it is the structure Go is teaching her
right now. Grade the answer, then set the next short task in the same message.

**B1 and above — one scenario per session**, from `mastery-db.skills_mastery`:

- Formal email (if `writing_formal_email` mastery < 4)
- Informal email (if `writing_informal_email` < 4)
- Form filling (if `writing_forms` < 4)
- Newsletter / personal text (if overall writing < 3)
- Mixed scenarios (if all ≥ 4)

Scenarios must match the learner's CEFR level — A2 uses everyday situations, B1+ adds opinion / complaint / inquiry.

### 3. Present the task

At **A1 / A2**:

```markdown
## ✍️ Writing Exercise

**Topic:** {one small topic from her life, in native language}

**Task:** Write {1-2 | 3-5} sentences in {target_language}.

**Use:** {one or two words or short structures, in target language}

**Write your sentences below:**
```

No `___`, no sentence to complete, no sentence to copy, no model answer shown
before she writes.

At **B1 and above**:

```markdown
## ✍️ Writing Exercise

**Scenario:** {clear description in native language}

**Task:** Write a {type} in {target_language}.

**Requirements:**
- Length: {X-Y} words
- Include: {must-include elements}
- Register: {formal / informal}
- Level: {CEFR}

{Optional: example structure for harder tasks}

**Write your {text_type} below:**
```

### 4. Wait for the full text

Don't correct mid-composition. Let the learner finish.

### 5. Systematic error analysis

Check every sentence for these categories:

1. **Grammar** — word order, conjugation, clause structure, articles
2. **Formal/informal** — register consistency
3. **Vocabulary** — wrong word, English mixing, register-wrong synonyms
4. **Missing elements** — greeting, closing, required fields
5. **Spelling** — minor at A2, weightier at B2+
6. **Structure** — organization, flow, paragraphing

Tag each finding with a severity: 🔴 critical, 🟡 moderate, 🟢 minor.

### 6. Detailed feedback

Diverges slightly from the standard `fluent-feedback-formatter` template because writing answers are multi-sentence. Use this variant:

```markdown
## Feedback

### ✅ What You Did Well
- {strength 1}
- {strength 2}

### ❌ Areas to Improve

Every correction line MUST use the canonical shape — marker, the wrong text in
quotes, the arrow, the correct text in bold quotes, then the category and the
reason IN PARENTHESES. The accumulator parses exactly this; a line written as
`"wrong" → **"right"** — why` (no parentheses) is silently dropped and the
mistake never reaches `mistakes-db`:

```markdown
- 🔴 "{wrong}" → **"{correct}"** ({category} — {why})
- 🟡 "{wrong}" → **"{correct}"** ({category} — {why})
- 🟢 "{wrong}" → **"{correct}"** ({category} — {why})
```

Group them by severity if the text is long, but never drop the parenthesis.
Categories: see the `fluent-feedback-formatter` skill (single source of truth).

### 📝 Corrected Version

```
{fully corrected text}
```

**Score: {X}/10**

**Breakdown:**
- Grammar: {Y}/10
- Vocabulary: {Z}/10
- Structure: {W}/10
- Communication: {V}/10

---
```

### 7. Optional rewrite

If score < 7, offer:

```markdown
**Want to try again?** Rewriting with the corrections locks in the patterns.

Type "rewrite" to try again, or "next" to continue.
```

### 8. Session summary

```markdown
## 📊 Writing Session Summary

**Text Type:** {type}
**Score:** {X}/10
**Key Takeaways:**
- {learning 1}
- {learning 2}
- {learning 3}

**Next Time:**
- Focus on: {weak pattern}
- Review: {relevant flashcards}

{target-language "well done"}! ✍️

### 🚀 Keep going?
{one concrete next step, e.g. "Rewrite the text fixing [weak pattern], or try a new one."}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🎓 Review · 📝 Writing · 📖 Reading · 🗣️ Speaking · 📊 Stats · 🏁 End).
```

Rule: NEVER close with a bare goodbye — this summary is a pause point, not a farewell. The session ends only when the learner says so or starts something else.

### 9. Update all databases

Session fields: `command_used`, `skills_practiced: ["writing"]`,
`skill_scores.writing`, `errors[]` (one per distinct pattern, deduped),
`focus_next_session[]`.

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

## Examples

*(Placeholders. NEVER copy the language of an example into a session — derive both language names from the learner's profile, every turn.)*

### Example 1 — formal email task

> ## ✍️ Writing Exercise
>
> **Scenario:** ({Native}) You need to cancel an appointment you have on Thursday.
>
> **Task:** Write a formal email to the clinic in {Target}.
>
> **Requirements:**
> - Length: see the table below — 40-60 words is a B1 task, not an A1 one
> - Include: greeting, reason, request for a new appointment, closing
> - Register: formal
> - Level: A2
>
> **Write your email below:**

Learner: *(a 40-word text in {Target} with an informal greeting, a subordinate
clause in the wrong order, and no closing line)*

> ## Feedback
>
> ### ✅ What You Did Well
> - Clear reason for the cancellation.
> - Correct request structure.
>
> ### ❌ Areas to Improve
>
> - 🔴 "{informal greeting used}" → **"{formal greeting in {Target}}"** (formal_informal — a formal email needs the polite form; mixed registers cost exam points)
> - 🔴 "{their subordinate clause}" → **"{corrected clause}"** (word_order — in {Target} this clause puts the verb {where})
> - 🟡 "{missing closing}" → **"{formal closing in {Target}}"** (missing — a formal email needs a closing line)
>
> ### 📝 Corrected Version
>
> ```
> {the full corrected text, in {Target}}
> ```
>
> **Score: 6/10**
> - Grammar: 6/10 — the subordinate clause tripped you up.
> - Vocabulary: 8/10 — solid word choice.
> - Structure: 5/10 — missing proper opening + closing.
> - Communication: 7/10 — the message was clear despite the issues.

Note the correction lines: marker, quoted wrong text, arrow, bold quoted
correction, then `(category — why)` in parentheses. That is what gets parsed.

## Critical Rules

- **Length follows the level, and the level is in the profile.** A learner who
  is being asked what "apple" is in English cannot write a 50-word email, and
  asking is not ambition, it is a wall.

  | Level | Ask for |
  |---|---|
  | A1 | 1-2 sentences of her own, with the words to use named in the task |
  | A2 | 3-5 sentences of her own: a short note, a message or a postcard |
  | B1 | 50-70 words: an email with a greeting and a closing |
  | B2+ | 80-120 words, with an argument to make |

  Seen live: an A1 profile asked for a 50-70 word email in the same session as
  "what is the English word for poma".



- **Never a gap.** No `___`, nothing to complete, nothing to copy — at any level.
  The server rejects a Writing turn that contains one.
- **A1 / A2: one short task at a time**, graded, then the next. **B1+: one
  scenario per session** — depth over breadth.
- **Wait for the full answer** before correcting.
- **Severity tagging is mandatory.** Fed into `mistakes-db` and drives spaced repetition priority.
- **Never write files.** The results file under `~/.fluent/<id>/results/` is written by the server, from your graded feedback.
- **Never auto-invoke.** This skill is gated; must fire only on explicit `/fluent-writing`.

## Language Reference

This skill deliberately carries **no per-language cheat-sheet**. A fixed example
language leaks into real sessions: the tutor starts producing that language
instead of the learner's. Derive the target language from
`learner-profile.json` every turn.

What to check in a formal text, in ANY language:

- the politeness form the language uses, and whether it is consistent throughout
- opening and closing conventions for the text type
- clause-order rules that change under subordination or negation
- date, time and address formats
- register-appropriate vocabulary (no casual contractions in a formal letter)

If a learner needs a recurring per-language reference, keep it in their own
profile (`learner-profile.json → notes`), not in this shared skill.
