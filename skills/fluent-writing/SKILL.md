---
name: fluent-writing
description: Run an interactive writing practice session (emails, letters, forms, short texts) with systematic error analysis, category-tagged corrections, and detailed feedback. Triggered only when the learner types /fluent-writing. Selects a scenario matched to mastery, lets the learner compose, then analyzes grammar, register, vocabulary, structure, and spelling before updating all databases.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
---

# Writing Practice Session

## Overview

Full-text writing practice with systematic correction. One scenario per session, detailed feedback broken down by severity and category, DB update at end. Mastery-driven scenario selection keeps the task at the right level — challenging, not frustrating.

## When to Use

Trigger this skill only when the learner types `/fluent-writing`. The skill is gated with `disable-model-invocation: true` — a 15-20 min interactive session with DB writes should never start from an ambiguous prompt.

Skip this skill in favor of `/fluent-vocab` if the learner has not yet hit mastery 2 in basic vocabulary — writing needs a minimum word bank.

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

### 2. Pick scenario type

From `mastery-db.skills_mastery`:

- Formal email (if `writing_formal_email` mastery < 4)
- Informal email (if `writing_informal_email` < 4)
- Form filling (if `writing_forms` < 4)
- Newsletter / personal text (if overall writing < 3)
- Mixed scenarios (if all ≥ 4)

Scenarios must match the learner's CEFR level — A2 uses everyday situations, B1+ adds opinion / complaint / inquiry.

### 3. Present the task

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

Use the buttons at the top (🎲 🔁 📚 📝 🗣️ 📖) to continue, or ↺ for a brand-new session. What shall we do next?
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
> - Length: 40-60 words
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

- **One scenario per session.** Don't chain multiple writing tasks — depth over breadth.
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
