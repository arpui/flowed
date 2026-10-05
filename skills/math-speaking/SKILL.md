---
name: math-speaking
description: Run an interactive typed conversation session simulating spoken practice — free-flowing dialogue, role-plays, and opinion questions prioritizing communication over perfect grammar. Triggered only when the learner types /math-speaking. Asks questions one at a time in the target language, evaluates clarity and naturalness first and grammar second, and updates all databases at the end.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
requires: [math-feedback-formatter]
---

# Speaking Practice (Typed)

## Overview

Conversational practice through typed dialogue. Unlike `/math-writing`, prioritize **communication and naturalness** — grammar errors that don't block meaning are downplayed. Goal: build the learner's confidence to produce target-language output without over-analyzing.

## When to Use

Trigger this skill only when the learner types `/math-speaking`. The skill is gated with `disable-model-invocation: true` — 15-20 min interactive session with DB writes should never start from an ambiguous prompt.

Skip this skill below A1 mastery 2 — the learner needs a basic word bank and verb conjugations first (run `/math-vocab` a few times).

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

Need: `learner-profile` (level, target language), `mastery-db.skills_mastery.speaking`.

### 2. Opening

```markdown
# 🗣️ {target_language} Speaking Practice

{greeting in {Target}}, {name}!

Today we're practicing **speaking** through typed conversation. I'll ask you questions or give scenarios, you respond naturally in {target_language} — just like a real conversation.

**Focus:** natural expression, fluency, pronunciation (typed)
**Level:** {CEFR}  
*(`{CEFR}` = `learner-profile.learner.current_level`, read verbatim — never estimated or guessed. Measured live, 2026-09-22, test-en: a profile with `current_level: "A0"` got a Speaking session opened at "Level: A2", a level nobody set anywhere. Same rule for `{target_language}`/`{native_language}` just above: read them from the profile, never swap or guess which is which —
measured the same day: target_language "English"/native_language "Catalan" produced "Catalan Speaking Practice", asking the learner to answer IN THEIR OWN native language, backwards.)*
**Duration:** 15-20 min

**Tips:**
- Think in {target_language}, not {native_language}
- Don't chase perfect grammar — focus on getting your message across
- Use complete sentences
- Be natural and conversational

**Ready? Let's chat!** 💬
```

### 3. Pick topic based on mastery

A2 topics:
1. Personal introductions
2. Daily routine
3. Hobbies and interests
4. Shopping
5. Making appointments
6. Asking for directions
7. Ordering food
8. Talking about weather
9. Weekend plans
10. Work / study

B1+: opinions, comparisons, hypotheticals, complaints, narratives.

### 4. One question at a time

```markdown
## Question {N}: {Topic}

{Question in target language}

**Type your answer in {target_language}:**
```

Build the conversation naturally — after 3-4 Qs on one topic, transition: `Interessant! Let's talk about something else...`.

Production prompts ("How would you say … in {target_language}") ALWAYS carry
the source sentence in the NATIVE language — never in the target language
itself (asking to say a target sentence "in target" is circular: zero learning
value, never emit it).

### 5. Evaluate

Check in this order:

1. **Communication** (most important, 0-5 points): was the message clear? Did it answer the question?
2. **Grammar** (0-3 points): verb conjugation, word order, articles. Note but don't belabor.
3. **Vocabulary** (0-2 points): appropriate word choice, no English mixing.

Feedback template (variant of `math-feedback-formatter`):

```markdown
{✅ or 🟡} {one-line encouragement}

**What you said:**
"{their_answer}"

**Communication:** {Clear / Mostly clear / Unclear} ✅

**Grammar notes:** (secondary — don't over-focus)
- {major error → correction, only if communication-blocking}

**Natural alternative:**
You could also say: "{more_natural_phrasing}"

**Score: {X}/10**
- Communication: {Y}/5
- Grammar: {Z}/3
- Vocabulary: {W}/2

{encouragement}

---
```

### 6. Role-play (advanced)

For B1+ or when the learner is warmed up:

```markdown
## 🎭 Role-Play

**Scenario:** {description in native language}
**Your role:** {what the learner plays}
**I'll be:** {what Claude plays}

Ready? I'll start...

---

{first line in target language}

**Your turn:**
```

### 7. Session summary

```markdown
## 🎉 Speaking Session Complete!

**Duration:** {X} min
**Questions Answered:** {N}
**Topics Covered:** {list}

### Communication Scores
**Overall:** {percent}%
- Clear messages: {count}
- Natural expression: {rating}/5
- Confidence: Growing! 💪

### Vocabulary Used Well
- {words}

### For Next Time
- Try using: {new phrase}
- Practice: {weak area}

**{target-language well done}!** 🌟

### 🚀 Keep going?
{one concrete next step, e.g. "One more round on [topic] using [new phrase]."}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🎓 Review · 📝 Writing · 📖 Reading · 🗣️ Speaking · 📊 Stats · 🏁 End).
```

Rule: NEVER close with a bare goodbye — this summary is a pause point, not a farewell. The session ends only when the learner says so or starts something else.

### 8. Update all databases

Session fields: `command_used`, `skills_practiced: ["speaking"]`,
`skill_scores.speaking`, `errors[]` (only communication-blocking ones — don't
flood mistakes-db with minor speaking slips), `focus_next_session[]`.

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

### Example 1 — personal intro

> ## Question 1: Introductions
>
> {"Tell me about yourself. Where are you from?" — asked in {Target}}
> ({the same question in {Native}, for A1-A2 learners})

Learner: *(two sentences in {Target}: name, origin, where they live now — with
one preposition slip)*

> ✅ Clear and natural!
>
> **What you said:** "{their reply}"
>
> **Communication:** Clear ✅
>
> **Grammar notes:**
> - 🟢 "{their preposition}" → **"{the right one}"** (prepositions — origin takes {the right one}). Small slip; the message was still crystal clear.
>
> **Score: 9/10** — keep going, that flowed well.

## Critical Rules

- **Communication first.** A clear message with a missed article scores better than a grammatically perfect but confusing answer.
- **One question at a time.** Wait for reply before next.
- **Stay in the target language** for questions and transitions. Drop to native only for explanations.
- **Praise natural expression.** If the learner uses a hesitation marker or discourse particle of {Target} correctly, call it out — those are fluency markers.
- **Don't over-correct.** A speaking session with 20 red marks kills confidence.
- FRIEND MODE (only if `preferences.tutor_style == "friend"`): pick role-play scenarios involving `learner.interests`.
- **Never auto-invoke.** Gated; must fire only on explicit `/math-speaking`.

## Language Reference

No per-language filler list is kept here on purpose: a fixed example language
leaks into sessions. Every language has its own hesitation markers and
discourse particles ("well…", "actually…", "so…", "right"), and using them is a
genuine fluency signal.

Derive them from the profile's target language, and when the learner uses one
correctly, name it and praise it — that is the cue that they are thinking in the
language rather than translating.
