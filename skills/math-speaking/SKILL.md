---
name: math-speaking
description: Run a light MATH TALK session — a short oral-style exchange, typed, about how the learner thinks: what strategy they used, why it works, which answer is faster and why. Triggered only when the learner types /math-speaking. Asks one question at a time in the learner's language, values a clear explanation over perfect formalism, and updates all databases at the end.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
requires: [math-feedback-formatter]
---

# Math Talk (Typed)

## Overview

A light conversational practice: the learner *talks about* math instead of
only doing it. "Com ho has fet, de cap, 29 + 17?", "per què 5 × 3 és el
mateix que 3 × 5?", "quina de les dues et surt més ràpid i per què?". Unlike
`/math-writing`, keep it SHORT — one or two sentences per turn, a warm
back-and-forth. Goal: make the learner's thinking out loud, so the tutor can
hear the strategy and the learner can hear it explained back.

## When to Use

Trigger this skill only when the learner types `/math-speaking`. The skill is gated with `disable-model-invocation: true` — 15-20 min interactive session with DB writes should never start from an ambiguous prompt.

Skip this skill for a learner who has not yet automated the basic facts
(`facts` mastery < 2) — they need the facts first (`/math-vocab` a few times)
before talking about strategies has anything to talk about.

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

Need: `learner-profile` (level, native language, interests), `mastery-db.skills_mastery` (reasoning), `mistakes-db` (weak procedure patterns).

### 2. Opening

```markdown
# 🗣️ Math Talk

{greeting}, {name}!

Ara parlem de matemàtiques: et faré preguntes curtes sobre **com penses**,
i m'ho expliques amb les teves paraules. No cal resoldre res gran — cal dir
com ho faries i per què.

**Focus:** estratègies, per què funcionen, triar la més ràpida
**Level:** {level}
*(`{level}` = `learner-profile.learner.current_level`, read verbatim — never estimated or guessed. Measured live, 2026-09-22, language fork: a profile with `current_level: "A0"` got a session opened at "Level: A2", a level nobody set anywhere.)*
**Duration:** 10-15 min

**Tips:**
- Respon curt: una o dues frases
- Explica el "com", no només el "quant"
- Si no estàs segur, digues-ho — també és informació útil

**Comencem!** 💬
```

### 3. Pick topic based on mastery

Early topics:
1. Com fas el doble d'un nombre de cap?
2. Per què sumar 9 és com sumar 10 i treure 1?
3. Quina taula et surt més ràpida? I la més lenta?
4. Com saps si 7 × 8 fa 54 o 56?
5. Repartir 20 caramels entre 4: quina operació i per què?

Mid/upper topics: estratègies de càlcul mental, per què (a+b)×c = a×c + b×c,
com estimar abans de calcular, comparar fraccions sense denominador comú,
per què multiplicar per 1/2 és dividir per 2.

Anchor topics to what the learner just did in Go/Review when the history
shows it — talking about a problem they actually solved beats an abstract one.

### 4. One question at a time

```markdown
## Question {N}: {Topic}

{the question, in the learner's language}

**Respon amb les teves paraules:**
```

Build the conversation naturally — after 3-4 Qs on one topic, transition:
`Molt bé! Parlem d'una altra cosa...`. Follow up ONCE on a vague answer
("i per què funciona?"), then move on. Never interrogate.

### 5. Evaluate

Check in this order:

1. **Strategy** (most important, 0-5 points): is there a real method, and does it actually work?
2. **Justification** (0-3 points): did they say WHY, not just WHAT?
3. **Accuracy** (0-2 points): is the math they state correct?

Feedback template (variant of `math-feedback-formatter`):

```markdown
{✅ or 🟡} {one-line encouragement}

**Què has dit:**
"{their_answer}"

**Estratègia:** {Real i vàlida / Bona idea, poc clara / No funciona} ✅

**Notes:** (secondary — don't over-focus)
- {only corrections that matter for the math, in the canonical shape}

**Una manera de dir-ho:**
També ho podries explicar així: "{clearer phrasing of the same math}"

**Score: {X}/10**
- Estratègia: {Y}/5
- Justificació: {Z}/3
- Precisió: {W}/2

{encouragement}

---
```

Correction lines, when there are any, still use the canonical shape
(marker, quoted wrong, arrow, bold right, `(category — why)`) so they reach
`mistakes-db` — usually `procedure`, `facts` or `misread`.

### 6. Session summary

```markdown
## 🎉 Math Talk Session Complete!

**Duration:** {X} min
**Questions Answered:** {N}
**Topics Covered:** {list}

### Strategy Scores
**Overall:** {percent}%
- Clear strategies: {count}
- Explained the "why": {count}
- Confidence: Growing! 💪

### Strategies Used Well
- {strategies}

### For Next Time
- Prova de fer servir: {new strategy}
- Repassa: {weak area}

Molt bé! 🌟

### 🚀 Keep going?
{one concrete next step, e.g. "One more round on [topic], explaining each step."}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🔁 Review · 📚 Facts · 📝 Raonament · 📖 Problemes · 🗣️ Math talk · 📊 Stats · 🏁 End).
```

Rule: NEVER close with a bare goodbye — this summary is a pause point, not a farewell. The session ends only when the learner says so or starts something else.

### 7. Update all databases

Session fields: `command_used`, `skills_practiced: ["reasoning"]`,
`skill_scores.reasoning`, `errors[]` (only strategy-breaking ones — don't
flood mistakes-db with minor talk slips), `focus_next_session[]`.

**Persistence is automatic — you write nothing.** The FlowMath server folds every
graded answer into the learner databases as it happens (Capa A) and finalizes
the session itself (Capa B, on `/math-end` or after 30 min idle), including
the results file under `~/.flowed/<id>/results/`. Do NOT call `update-db.py`,
do NOT call `persist-session.py`, do NOT write any file: you have no write tool,
those calls are denied by the allow-list, and each denial eats context. Your only
persistence job is to grade in the canonical feedback format — that is what the
accumulator parses.

*(Claude Code / clone mode only, where nothing persists automatically: load the
`math-db-updater` skill and make ONE `update-db.py` call at session end with
the fields listed above.)*

## Examples

*(Placeholders. NEVER copy the numbers of an example into a session — anchor every question to this learner's level and recent work.)*

### Example 1 — strategy question

> ## Question 1: Càlcul mental
>
> Com fas 29 + 17 de cap? Explica-ho en una o dues frases.

Learner: "faig 30 + 17 i després trec 1"

> ✅ Exacte — compensar i tornar. Aquesta és una estratègia de veritat.
>
> **Què has dit:** "faig 30 + 17 i després trec 1"
>
> **Estratègia:** Real i vàlida ✅
>
> **Score: 10/10** — i ara digues-ho amb una operació: 29 + 17 = 30 + 17 − 1 = 46.

### Example 2 — a strategy that doesn't work

> ## Question 3: Taules
>
> Saps 6 × 7? Com ho esbrinaries si no te'n recordessis?

Learner: "sumo 6 + 7"

> 🟡 Bona intuïció — les taules són sumes repetides — però 6 + 7 és una suma, no sis setens.
>
> **Corrections:**
> - 🟡 "6 + 7" → **"6 + 6 + 6 + 6 + 6 + 6 (sis vegades set)"** (procedure — multiplicar és sumar el mateix nombre diverses vegades)
>
> **Score: 5/10** 💪 La idea de sumar és la correcta; la manera d'usar-la, demà al repàs.

## Critical Rules

- **Strategy first.** A real method explained loosely scores better than a memorized slogan with no understanding.
- **One question at a time.** Wait for reply before next.
- **Talk in the learner's language.** Math talk is about thinking; the thinking happens in their language. The math notation follows `rules.md`.
- **Praise real strategies.** If the learner invents a valid shortcut, call it out by name — that is the signal that their thinking counts.
- **Don't over-correct.** A talk session with 20 red marks kills the willingness to explain. Correct only what breaks the math.
- FRIEND MODE (only if `preferences.tutor_style == "friend"`): anchor questions to problems from `session_log.last_session` and `learner.interests`.
- **Never auto-invoke.** Gated; must fire only on explicit `/math-speaking`.
