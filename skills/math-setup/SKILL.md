---
name: math-setup
description: One-time interactive onboarding that creates the learner's personalized language-learning profile — name, target language, native language, current/target CEFR level, timeline, daily minutes, and learning goals. Triggered only when the learner types /math-setup. Also handles profile updates and resets for returning users. Must never auto-invoke because re-running can reset progress.
allowed-tools: Read, Write, Bash, AskUserQuestion
disable-model-invocation: true
---

# Language Learning Setup

## Overview

One-time onboarding that seeds all 6 databases in the Fluent data directory. After setup, every other skill reads from those files — this is the bootstrap. Also handles profile updates and progress resets for returning users.

**In the Fluent server (the web app), you do NOT touch files.** The profile
directory and its 6 databases already exist — the system owner created them with
`scripts/new-user.sh`. Your job is the interview, and then ONE call to
`math_setup_profile`, which writes the profile and marks the setup complete.

*(Claude Code / clone mode only: there is no such tool there, so you resolve the
data directory with `main_paths.ensure_data_dir()` and write the files
yourself — see §5b.)*

## When to Use

Trigger this skill only when the learner types `/math-setup`. The skill is gated with `disable-model-invocation: true` — re-running can reset a learner's progress, so it must never auto-fire from an ambiguous prompt.

Skip this skill if a profile already exists and the learner did not ask to change anything; route them to `/math-learn` or `/math-progress` instead.

## Instructions

### 1. Check for existing profile

The learner state is preloaded with the command. If it shows a real name and a
target language, the profile is already set up: jump to **Profile updates**
below. If the fields still look like a template (`{YOUR_NAME}`, empty
languages), this is a first setup — continue.

### 2. Welcome

```markdown
# 🌍 Welcome to Your Personal Language Learning System!

This AI-powered system will help you learn any language through:
- 📊 Systematic progress tracking
- 🧠 Spaced repetition (scientifically proven)
- 🎮 Gamification (streaks, achievements)
- 📈 Adaptive difficulty
- 🎯 Personalized to YOUR goals

**Let's get you set up!** (~5 minutes)
```

### 3. Collect info

Use the `AskUserQuestion` tool to gather questions in batches when possible. Required fields:

1. **Name** — personalizes greetings.
2. **Target language** — the language being learned (e.g. Spanish, French, German, Japanese, Korean, Arabic, Dutch).
3. **Native language** — for translations and explanations.
4. **Other languages spoken** — optional, used to offer cross-language connections.
5. **Current level** — A1 / A2 / B1 / B2 / C1 / C2 / "not sure".
6. **Target level** — where they want to get to.
7. **Timeline** — 3 months / 6 months / 12 months / 2+ years / custom.
8. **Daily study minutes** — 10 / 15 / 30 / 60 / custom.
9. **Learning goal** — travel / work / exam (specify) / living in country / academic / family / interest.
10. **Learning style** — conversational / academic / immersive / balanced (default).
11. **Gamification on/off** — default on.
12. **Interests (max 3, 1-2 words each)** — e.g. football, cooking, travel. Used
    in examples and scenarios. Short on purpose: everything stored here costs
    context on every turn.
13. **About you (1 line, optional)** — free sentence the tutor may reference
    ("I'm a nurse working nights"). Skip if the learner has nothing to add.
14. **Tutor style** — `classic` (default: neutral tutor) or `friend` (warmer:
    cites last session, uses your interests). Changeable later in
    `preferences.tutor_style`.

If the learner picks "not sure" for current level, run a quick 5-question assessment:

1. Basic vocabulary recognition → A1
2. Simple sentence construction → A2
3. Past tense usage → B1
4. Complex subordinate clauses → B2
5. Idiomatic expression → C1

Map score to level: 0-1 correct = A1, 2 = A2, 3 = B1, 4 = B2, 5 = C1.

### 4. Generate the learning plan

Compute expected months to target level:

```
A1 → A2: ~100 hours
A2 → B1: ~150 hours
B1 → B2: ~200 hours
B2 → C1: ~300 hours
C1 → C2: ~400 hours

months = hours_needed / (daily_minutes / 60) / 30
```

Adjust:

- `-10%` time if learner's native language is typologically close to the target (e.g. Dutch ↔ English, Spanish ↔ Italian).
- `-10%` per additional language already known (cap at 30% total).

Present:

```markdown
## 🎉 Setup Complete!

**Your Learning Profile:**
- 👤 Name: {name}
- 🌍 Learning: {target_language}
- 📚 Native: {native_language}
- 📊 Level: {current} → {target}
- 📅 Timeline: {timeline}
- ⏱️ Daily time: {minutes} min
- 💡 Goal: {goal}

## 📋 Personalized Plan

**Estimated time:** {months} months
**Total study hours:** ~{hours} hours

### Weekly Schedule
**Daily:**
- 🔁 **Review** — spaced repetition ({X} min)
- 📚 **Vocabulary** — new words ({Y} min)

**Alternating:**
- 📝 **Writing** (Mon/Wed/Fri)
- 🗣️ **Speaking** (Tue/Thu/Sat)
- 📖 **Reading** (Sun)

**Weekly:**
- 📊 **Progress** — check stats (5 min)

### Milestones
- Month 1: {reasonable short-term}
- Month 3: {quarter-way}
- Month 6: {half-way}
- Target date: {target_level}!

### Next Steps
1. Start now — press 🎲 **Surprise me!**
2. Daily habit — 🔁 **Review** every day
3. Weekly — 📊 **Progress** to see stats
4. Stay consistent — even 10 min daily beats 2 hours weekly

**Your journey to {target_language} fluency starts now!** 🚀
```

### 5. Save the profile — ONE tool call

```
math_setup_profile({
  name: "<their first name>",
  target_language: "<in English: English, German, …>",
  native_language: "<in English: Catalan, Spanish, …>",   // never guess
  current_level: "A1|A2|B1|B2|C1|C2",
  target_level:  "A1|A2|B1|B2|C1|C2",
  daily_minutes: <number>,
  goals: ["…"],                 // why they are learning, their words
  motivation: "travel|work|exam|living_abroad|personal|family",
  interests: ["…"],             // up to 3, optional — warmer examples
  about: "<one line>"           // optional
})
```

- Call it **once**, at the end of the interview, with what they actually said.
- If the learner does not know their CEFR level, ask ONE placement question and
  decide yourself — the call needs a level.
- It returns `REJECTED: …` when something is off (same language twice, a level
  that is not CEFR, no profile directory). Fix exactly that and call again once.
- On success the setup is marked complete and the app stops asking. Then show
  the plan (§4) and invite them to start practising.
- The 6 databases already exist; you never create or overwrite them.

### 5b. Claude Code / clone mode only

There is no `math_setup_profile` tool outside the Fluent server. There, start
from the templates in `data-examples/`, resolve the directory with
`main_paths.ensure_data_dir()` and write the 6 files with the Write tool
(`learner-profile.json` filled in and `preferences.setup_complete = true`; the
other five as the empty templates). Never call `update-db.py` for this — that
script is for session updates, not bootstrapping.

### 6. Optional first lesson

```markdown
## 🎓 Want to start your first lesson now?

A quick 5-10 min intro session to learn your first 10 words and get familiar with the system.

Type "yes" to start, "later" to begin on your own.
```

If yes, hand off to the `math-learn` skill.

## Profile Updates (existing profile)

```markdown
# 👋 Welcome back, {name}!

You already have a learning profile.

What would you like to do?

1. **Update profile** — change goals, timeline, or preferences
2. **View current plan** — see your learning schedule
3. **Reset progress** — start fresh (⚠️ erases all progress!)
4. **Cancel** — keep everything as is

**Type 1, 2, 3, or 4:**
```

- **1** — ask which field, then call `math_setup_profile` again with the WHOLE
  set of fields (the ones that do not change included): the call replaces the
  profile fields it receives and keeps everything else — progress, streak,
  achievements — untouched. It writes a `learner-profile.json.backup-…` first.
- **2** — render the plan section from current data. Read-only.
- **3** — **Reset is not something you can do.** Erasing a learner's history is
  the system owner's job, from a terminal, with a backup. Tell them that and
  offer option 1 instead.
- **4** — exit cleanly.

## Examples

### Example 1 — first-time setup flow

Learner runs `/math-setup`. After collecting the answers, compute months,
show the plan, call `math_setup_profile` once, offer the first lesson.

### Example 2 — returning-user profile reset

Learner: "reset my progress, I want to start over"

> You're about to delete:
> - 42 sessions
> - 6-day streak
> - 287 vocabulary items
> - 12 mastered patterns
>
> This is irreversible. Type `RESET` (all caps) to confirm, or anything else to cancel.

## Critical Rules

- **Never auto-invoke.** Re-running this can reset a learner's progress. Must be an explicit `/math-setup`.
- **Confirm twice before reset.** "This will erase X days of progress, Y sessions, and Z mastered words. Proceed? (yes/no)".
- **Always seed all 6 files** — every other skill assumes they exist.
- **Back up before reset.** Hooks may not fire here; back up manually to `.backups/pre-reset-<timestamp>/`.
- **Don't invent data.** Start every file empty — progress, mistakes, mastery all start at zero. The system builds up from real sessions.
