---
name: math-reading
description: Run an interactive WORD PROBLEMS session — a short problem statement in the learner's own language, which the learner reads, sets up and solves; the tutor grades the setup (operation choice) and the calculation. Triggered only when the learner types /math-reading. Presents one problem at a time with immediate feedback, and optionally adds the problem's key vocabulary to the spaced-repetition queue.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
---

# Word Problems Session

## Overview

Present one short word problem, wait for the learner to set it up and solve
it, then grade the two halves separately: the **setup** (which operation the
situation calls for) and the **calculation** (the arithmetic after that).
This is where reading and math meet: most wrong answers are not bad arithmetic
but a misread statement or a wrong operation — and the feedback must say which.

## When to Use

Trigger this skill only when the learner types `/math-reading`. The skill is gated with `disable-model-invocation: true` — 15-20 min interactive session with DB writes should never start from an ambiguous prompt.

Skip this skill for a learner who has not yet automated the basic facts
(`facts` mastery < 2) — shorter drills (`/math-vocab`) are more appropriate
until the arithmetic is not the bottleneck.

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

Need: `learner-profile` (level, native language, interests), `mastery-db.skills_mastery` (problems), `mistakes-db` (weak `wrong_operation` / `misread` patterns).

**The statement is in the learner's own language** (`native_language` from the
profile — the language they read school problems in). The math itself is
universal; there is no "target language" to read. What you grade is the
math, never the Catalan of their answer.

### 2. Opening

```markdown
# 📖 Problemes

{greeting}, {name}!

Avui resolem **problemes**: llegiràs un enunciat curt, escriuràs les operacions
que calen i el resultat, i jo et diré si la idea i el càlcul són bé.

**Focus:** triar bé l'operació, després calcular bé
**Level:** {level}
**Duration:** 15-20 min

**Tips:**
- Llegeix l'enunciat sencer abans de començar
- Subratlla mentalment la pregunta: què et demanen?
- Escriu una operació per línia
- Comprova el resultat al final: té sentit?

**Comencem!** 💪
```

### 3. Pick problem type + length

Match the numbers to the learner's level (the curriculum path in the preloaded
state names what has been taught) and the topic to `learner-profile.interests`
in friend mode.

- **One-step** (early): a single operation hiding behind a keyword — "en total", "quants en queden", "el doble de", "repartir entre iguals".
- **Two-step** (mid): combine + then ×, or a "quants en falten per…" with a comparison.
- **Multi-step / fractions / proportions** (upper): common denominators, unit rates, change-over-time.

Rotate the operation the problem *needs* (×, ÷, +, −, mixed) so the learner
cannot fall into "the last number always gets multiplied".

### 4. Present the problem

```markdown
## Problema {N}

**Enunciat:** {the problem statement, 1-4 sentences, in the learner's language}

**Escriu les operacions (una per línia) i el resultat:**
```

The `**Enunciat:**` line carries the problem; keep it on one line so the
exercise tracker can fingerprint it. Never reuse a problem presented in the
last 24h — check the session history and the ALREADY ASKED list first.

The card MUST ask for the operations, not only the result: the server's
Problemes guard sends back a task that just says "escriu el resultat", and
the rubric scores a bare number 0-4 anyway. The statement must be a story —
"**Enunciat:** 24 ÷ 6" is a Go card, not a problem.

### 5. Grade the two halves — delegate to the deep evaluator (WP3.2)

When the answer arrives, call `math_deep_evaluate` with:

- `task='word-problem'` — ALWAYS this task for this practice (the rubric
  judges the deliverable of a word problem: setup + operations + answer)
- `answer=` the learner's full text, verbatim (operations lines included)
- `context=` the problem statement, the operation(s) it calls for and the
  exact result (so the evaluator checks the setup against the right one),
  plus the learner's level and language

Call it at most ONCE per answer, only with her real submitted text — never
placeholder or invented content. If it returns `DEEP UNAVAILABLE`, grade the
four rubric dimensions yourself (answer, procedure, justification,
communication) in the same format.

The rubric already separates the two halves inside "procedure" — read its
CORRECTIONS with this in mind:

1. **Setup** — does the operation match the situation? Wrong operation or a
   misread statement is the headline finding (`wrong_operation`, `misread`).
2. **Calculation** — is the arithmetic after the setup right? (`calculation`,
   `carrying`, `facts`…)
3. **Answer form** — unit present, sentence answered, fraction reduced
   (`unit`, `simplification`, `incomplete`).

Present its evaluation in the canonical feedback shape (the
`math-feedback-formatter` contract — the accumulator parses it), and record
the answer with `math_record_answer` using **skill `problems`**:

```markdown
{✅ or ❌} {one line}

**Corrections:**
- ❌ "{their setup}" → **"{the right setup}"** (wrong_operation — "repartir entre iguals" demana ÷, no −)
- ✅ "{the part that was right}" — {praise}

**Correct version:**
"{the full correct line of work and the answer}"

**Score: {X}/10** {emoji} {comment}

---
```

The rubric's bands are the closed path's 10/7/3 scale, so the numbers read
the same everywhere: a right setup with a wrong calculation lands 5-7 (the
hard part was the idea). A wrong setup scores 0-4 even if the arithmetic that
followed was flawless — the schedule must bring the *choice* back tomorrow.
A bare numeric answer with no operations at all is 0-4 too (procedure and
justification empty) — when that happens, say so in the feedback: next time
write the operations, one per line, because the answer alone does not score.

### 6. Problem vocabulary review

After each problem (or every few), name the keyword that decided the
operation:

```markdown
## 📚 Claus del problema

| Paraula | Què vol dir | Operació |
|---------|-------------|----------|
| {keyword 1} | {meaning} | {operation} |
| {keyword 2} | {meaning} | {operation} |

**Vols que aquestes claus entrin a la cua de repàs?** Escriu "yes" o "no".
```

If yes, stage each keyword for `new_facts[]` in the end-of-session DB
update (WP1.9 renamed it from the language-era `new_vocabulary[]`; the
persistence scripts still read the old spelling).

**Never skip straight to the summary without showing this table at least
once** when the session used a keyword the learner had not seen before. The
table can legitimately have zero rows when every keyword was already known —
but look for them before concluding there are none.

### 7. Session summary

```markdown
## 📊 Problemes Session Complete!

**Problems:** {N}
**Accuracy:** {percent}%

### Breakdown
- Setup (operació correcta): {count}/{N}
- Calculation: {count}/{N}
- Answer form: {count}/{N}

### New Keywords Added: {count}
{list}

### For Next Time
- {suggestion based on which half was weakest}

Molt bé! 📖✨

### 🚀 Keep going?
{one concrete next step, e.g. "More [setup/answer] practice would help — or drill the facts behind it."}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🔁 Review · 📚 Facts · 📝 Raonament · 📖 Problemes · 🗣️ Math talk · 📊 Stats · 🏁 End).
```

Rule: NEVER close with a bare goodbye — this summary is a pause point, not a farewell. The session ends only when the learner says so or starts something else.

### 8. Update all databases

Session fields: `command_used`, `skills_practiced: ["problems"]`,
`skill_scores.problems`, `errors[]` (per half: `wrong_operation`/`misread` for
setup, `calculation`/`carrying`/… for the arithmetic), `new_facts[]`
(keywords the learner chose to save), `focus_next_session[]`.

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

*(Placeholders. NEVER copy the numbers of an example into a session — every problem comes from this learner's level.)*

### Example 1 — wrong setup, right arithmetic

> ## Problema 2
>
> **Enunciat:** La Marta té 24 galetes i les vol repartir igualment entre 6 amics. Quantes galetes toquen a cada amic?
>
> **Escriu les operacions (una per línia) i el resultat:**

Learner: "24 − 6 = 18"

> ❌ La idea no és aquesta — "repartir igualment" és dividir, no treure.
>
> **Corrections:**
> - 🔴 "24 − 6 = 18" → **"24 ÷ 6 = 4"** (wrong_operation — repartir entre iguals demana ÷)
> - ✅ "24 − 6 = 18" — la resta, ben calculada; el càlcul no era el problema
>
> **Correct version:**
> "24 ÷ 6 = 4 galetes per amic"
>
> **Score: 3/10** 💪 L'operació torna demà al repàs.

### Example 2 — right setup, one slip

> ## Problema 4
>
> **Enunciat:** En Pere compra 3 llibretes a 2,50 € cada una i paga amb un bitllet de 10 €. Quants euros li tornen?

Learner: "3 × 2,50 = 7,50; 10 − 7,5 = 3,5"

> ✅ Perfecte — dues operacions, en l'ordre correcte.
>
> **Correct version:**
> "3 × 2,50 = 7,50 €; 10 − 7,50 = 2,50 €"
>
> **Score: 9/10** 🎯 Un llapis al final: 10 − 7,50 són 2,50, no 3,5.

## Critical Rules

- **One problem at a time.** Wait for the answer before the next.
- **Grade setup before calculation, and say which one failed.** The learner needs to know whether to reread the statement or drill the arithmetic.
- **The statement is in the learner's language; the grade is of the math.** A Catalan slip in their answer line is never a correction (see `math-feedback-formatter`).
- **Quote the keyword** ("repartir", "en total", "quants en falten") in explanations so the learner traces the operation choice back to the text.
- **Vocabulary opt-in.** Don't force-add every keyword — ask the learner which they want to keep.
- FRIEND MODE (only if `preferences.tutor_style == "friend"`): prefer problems touching `learner.interests`.
- **Never auto-invoke.** Gated; must fire only on explicit `/math-reading`.

## Problem Bank

Keep no fixed sample problems here: a stored problem is exactly what makes the
tutor drift from this learner's level, and a reused problem is a repeated
exercise (forbidden).

Generate each problem fresh, at the learner's level and (in friend mode) their
interests, with numbers the grader can compute exactly. Useful framings:
shopping and change, sharing equally, "quants en falten per…", double/half
comparisons, two-step plans. Never reuse a problem presented in the last 24h —
check the session history first.
