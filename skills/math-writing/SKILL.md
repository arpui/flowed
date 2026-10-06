---
name: math-writing
description: Run an interactive math REASONING session — the learner explains how they solved something, justifies a claim, or invents a problem that fits an expression, with systematic error analysis on procedure and justification. Triggered only when the learner types /math-writing. Selects a task matched to mastery, lets the learner write their reasoning, then analyzes procedure, operation choice and justification before updating all databases.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
requires: [math-feedback-formatter]
---

# Math Reasoning Session

## Overview

Open-ended math practice with systematic correction. One task per turn,
detailed feedback broken down by severity and category, DB update at end.
The learner does not compute a single right number here (that is 🎲 Go) — they
**explain, justify, or invent**: "explica com ho has resolt", "per què
3 + 2 × 4 no és 20?", "inventa un problema que es resolgui amb 3/4 + 1/8",
"troba l'error i explica per què". Mastery-driven task selection keeps the
task at the right level — challenging, not frustrating.

## When to Use

Trigger this skill only when the learner types `/math-writing`. The skill is gated with `disable-model-invocation: true` — a 15-20 min interactive session with DB writes should never start from an ambiguous prompt.

Reasoning is the one practice where the learner writes her OWN mathematical
words. Closed exercises — a result to compute, a gap to fill, a sentence to
complete — belong to 🎲 Go, which drills the same procedures. Never set one
here, at any level: the task is tiny at m1, but it is still hers to explain.

## The three math guards (WP3.3)

Every task this practice sets must pass three rules — the server rejects the
turn and asks for a rewrite when it does not:

1. **Never a bare list.** "Fes una llista de…" asks for items, not reasons.
   The deliverable is an explanation in her own words, with the reason
   attached. (A task may name the words or steps to use — that is a scaffold,
   not a list to produce.)
2. **Always require justification.** The task must ask HOW or WHY: "explica
   com ho has resolt i per què funciona", "per què 3 + 2 × 4 no és 20?",
   "demostra-ho", "troba l'error i explica'l", "inventa un problema que es
   resolgui amb …". A task that only asks for a result is Go under another
   name.
3. **The answer alone does not score.** Say it in the task itself: the number
   without the reasoning scores low on procedure and justification. The deep
   rubric (WP3.1) grades four dimensions — answer, procedure, justification,
   communication — and a bare result is weak on three of them.

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

Need: `learner-profile` (level, native language, focus areas), `mistakes-db` (weak procedure patterns: procedure, wrong_operation, misread), `mastery-db` (reasoning sub-skills).

### 2. Pick the task

**Younger / lower levels (m1-m3 equivalent) — one small explanation at a
time.** A problem she has just solved in Go, or a tiny claim about her own
numbers: "explica com vas fer 24 + 7 de cap", "per què 5 × 3 és el mateix que
3 × 5?", "quina operació necessites per saber quants en falten per 20?". If
the server's note gives a *Writing frame*, the pattern to explain comes from
it — it is the procedure Go is teaching her right now. Grade the answer, then
set the next short task in the same message.

**Upper levels — one task per session**, from `mastery-db.skills_mastery`:

- Explain-your-solution (if `reasoning_explain` mastery < 4): "explica com ho has resolt i per què funciona"
- Find-and-fix-the-error (if `reasoning_error_correction` < 4): a worked solution with one deliberate error — "hi ha un error. Troba'l i explica'l."
- Invent-a-problem (if `reasoning_invent` < 4): "inventa un problema que es resolgui amb 3/4 + 1/8"
- Justify-a-claim (if overall reasoning < 3): "té sentit que 1/3 + 1/4 = 2/7? Demostra-ho"
- Mixed tasks (if all ≥ 4)

Tasks must match the learner's level — lower levels use everyday quantities, upper levels add proportion, fractions, and multi-step planning.

### 3. Present the task

At **lower levels**:

```markdown
## 📝 Repte de Raonament

**Tema:** {one small topic from the problems she just solved}

**Task:** Explica en {1-2 | 3-5} frases com ho faries / per què funciona.

**Fes servir:** {one or two words or structures: "el doble de", "primers els parèntesis"}

**Escriu el teu raonament a sota:**
```

No `___`, nothing to complete, nothing to copy, no model answer shown before
she writes.

At **upper levels**:

```markdown
## 📝 Repte de Raonament

**Scenario:** {clear description in the learner's language}

**Task:** {Explica com ho has resolt | Troba l'error i explica'l | Inventa un problema que es resolgui amb …}

**Requirements:**
- Length: see the table below
- Include: the operation(s), the reason they are the right ones, the result
- Level: {level}

**Escriu el teu raonament a sota:**
```

### 4. Wait for the full answer

Don't correct mid-composition. Let the learner finish.

### 5. Systematic error analysis

Grade the four dimensions of the WP3.1 rubric — the same ones
`math_deep_evaluate` judges (task='explain' | 'error-analysis' |
'compare-strategies'; the server's rubric maps the score onto the closed
path's 10/7/3 bands):

1. **Answer** — is the final result correct, when the task has one
2. **Procedure** — are the steps sound and complete: the sequence, the
   operation choice (`wrong_operation` when the justification picks + where
   the situation needs ×), the order, the carrying
3. **Justification** — does she say WHY, not just WHAT? A right result with no
   reason ("per què?" unanswered) is weak here; a bare answer with no
   reasoning at all lands in the 0-4 band
4. **Communication** — is the math written clearly: notation, units, one
   operation per line (`misread` when the explanation answers a different
   problem than the one asked)

Tag each finding with a severity: 🔴 critical, 🟡 moderate, 🟢 minor.
Categories are the math ones from `math-feedback-formatter` — `procedure`,
`wrong_operation` and `misread` are the heart of this practice.

### 6. Detailed feedback

Diverges slightly from the standard `math-feedback-formatter` template because reasoning answers are multi-sentence. Use this variant:

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

For reasoning, the quoted parts are often whole steps or claims:
`- 🔴 "1/4 + 3/8 = 4/12" → **"1/4 + 3/8 = 2/8 + 3/8 = 5/8"** (wrong_operation — denominators are never added)`.
Group them by severity if the text is long, but never drop the parenthesis.
Categories: see the `math-feedback-formatter` skill (single source of truth).

The corrected reasoning uses the CANONICAL marker — `**Correct version:**`
on its own line, the full corrected reasoning in quotes on the next line.
The persistence fallback parses exactly that; a heading like
"### Corrected Version" is invisible to it and the corrected answer is lost:

**Correct version:**
"{the full corrected reasoning}"

**Score: {X}/10**

**Breakdown:** (the four rubric dimensions, WP3.1)
- Procedure: {Y}/10
- Justification: {Z}/10
- Answer: {W}/10
- Communication: {V}/10

---
```

### 7. Optional rewrite

If score < 7, offer:

```markdown
**Vols tornar-ho a provar?** Reescriure el raonament amb les correccions fixa el procediment.

Escriu "rewrite" per tornar-hi, o "next" per continuar.
```

### 8. Session summary

```markdown
## 📊 Raonament Session Summary

**Task Type:** {type}
**Score:** {X}/10
**Key Takeaways:**
- {learning 1}
- {learning 2}
- {learning 3}

**Next Time:**
- Focus on: {weak pattern}
- Review: {relevant queue items}

Molt bé! ✍️

### 🚀 Keep going?
{one concrete next step, e.g. "Rewrite the explanation fixing [weak pattern], or try a new one."}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🔁 Review · 📚 Facts · 📝 Raonament · 📖 Problemes · 🗣️ Math talk · 📊 Stats · 🏁 End).
```

Rule: NEVER close with a bare goodbye — this summary is a pause point, not a farewell. The session ends only when the learner says so or starts something else.

### 9. Update all databases

Session fields: `command_used`, `skills_practiced: ["reasoning"]`,
`skill_scores.reasoning`, `errors[]` (one per distinct pattern, deduped),
`focus_next_session[]`.

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

## Examples

*(Placeholders. NEVER copy the numbers of an example into a session — every task comes from this learner's level and weak patterns.)*

### Example 1 — explain-your-solution

> ## 📝 Repte de Raonament
>
> **Scenario:** Ahir vas fer 29 + 17 de cap i et va sortir 46.
>
> **Task:** Explica en 2-3 frases com ho vas fer i per què funciona.
>
> **Requirements:**
> - Length: see the table below — 1-2 sentences is a lower-level task, not an upper-level one
> - Include: the steps you took, and why they keep the answer right
>
> **Escriu el teu raonament a sota:**

Learner: *(adds 29 + 17 as 30 + 20 − 3, with one arithmetic slip in the middle)*

> ## Feedback
>
> ### ✅ What You Did Well
> - You rounded 29 to 30 and corrected at the end — that is a real strategy.
> - The final answer is right.
>
> ### ❌ Areas to Improve
>
> - 🟡 "30 + 20 = 50" → **"30 + 17 = 47"** (calculation — you added 20 instead of the 17 you were compensating for)
> - 🟢 "47 − 3 = 46" → **"47 − 1 = 46"** (procedure — you rounded 29 up by 1, so take 1 back, not 3)
>
> **Correct version:**
> "29 + 17 = 30 + 17 − 1 = 47 − 1 = 46"
>
> **Score: 7/10**
> - Procedure: 8/10 — the compensation idea is right.
> - Justification: 6/10 — you did not say why you subtract 1.
> - Answer: 7/10 — right at the end, one slip mid-way.
> - Communication: 7/10 — clear enough to follow.

Note the correction lines: marker, quoted wrong text, arrow, bold quoted
correction, then `(category — why)` in parentheses. That is what gets parsed.

## Critical Rules

- **Length follows the level, and the level is in the profile.** A learner who
  is being asked what double of 6 is cannot write a paragraph justifying a
  fraction claim, and asking is not ambition, it is a wall.

  | Level | Ask for |
  |---|---|
  | m1-m2 (early) | 1-2 sentences of her own, with the words to use named in the task |
  | m3-m4 | 3-5 sentences: explain a solution, find one error |
  | m5 | a full justification: steps + why each step is allowed |
  | m6+ | invent a problem for an expression, or defend a claim |

  Seen live in the language fork: an A1 profile asked for a 50-70 word text in
  the same session as "what is the word for poma".

- **Never a gap.** No `___`, nothing to complete, nothing to copy — at any level.
  The server rejects a Writing turn that contains one.
- **Never a bare list, always a justification.** "Fes una llista de…" is not
  reasoning, and a task that only asks for a result is Go under another name.
  Every task asks HOW or WHY and says the answer alone will not score — the
  server rejects a Raonament task that does neither (WP3.3 guards).
- **Lower levels: one short task at a time**, graded, then the next. **Upper
  levels: one task per session** — depth over breadth.
- **Wait for the full answer** before correcting.
- **Severity tagging is mandatory.** Fed into `mistakes-db` and drives spaced repetition priority.
- **Never write files.** The results file under `~/.flowmath/<id>/results/` is written by the server, from your graded feedback.
- **Never auto-invoke.** This skill is gated; must fire only on explicit `/math-writing`.

## Notation Reference

This skill deliberately carries **no per-level cheat-sheet of problems**. A
fixed example leaks into real sessions: the tutor starts producing that
problem instead of this learner's. Derive the level from
`learner-profile.json` every turn.

What to check in a reasoning answer, ALWAYS:

- the operation choice matches the situation the learner describes
- each step follows from the previous one (one operation per line when showing work)
- the justification says WHY, not just WHAT
- the final form matches what was asked (fraction reduced, unit present)
- notation follows `rules.md`: × ÷ −, fractions a/b, decimal comma — never LaTeX

If a learner needs a recurring reference, keep it in their own
profile (`learner-profile.json → notes`), not in this shared skill.
