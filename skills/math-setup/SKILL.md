---
name: math-setup
description: One-time interactive onboarding that creates the learner's personalized math-learning profile — name, the language of the problem statements, current/target level, timeline, daily minutes, and learning goals. Triggered only when the learner types /math-setup. Also handles profile updates and resets for returning users. Must never auto-invoke because re-running can reset progress.
allowed-tools: Read, Write, Bash, AskUserQuestion
disable-model-invocation: true
---

# Math Learning Setup

## Overview

One-time onboarding that seeds all 6 databases in the FlowMath data directory. After setup, every other skill reads from those files — this is the bootstrap. Also handles profile updates and progress resets for returning users.

**In the FlowMath server (the web app), you do NOT touch files.** The profile
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
level, the profile is already set up: jump to **Profile updates** below. If the
fields still look like a template (`{YOUR_NAME}`, empty languages), this is a
first setup — continue.

### 2. Welcome

```markdown
# 🌍 Benvingut al teu sistema personal de matemàtiques!

Aquest sistema t'ajudarà a progressar en matemàtiques amb:
- 📊 Seguiment sistemàtic del progrés
- 🧠 Repàs espaiat (SM-2, científicament provat)
- 🎮 Gamificació (ratxes, assoliments)
- 📈 Dificultat adaptativa
- 🎯 Personalitzat als TEUS objectius

**Comencem!** (~5 minuts)
```

### 3. Collect info

Use the `AskUserQuestion` tool to gather questions in batches when possible. Required fields:

1. **Name** — personalizes greetings.
2. **Language of the problem statements** — the language the learner reads and
   answers word problems in (e.g. Catalan, Spanish). This is stored as
   `native_language`.
3. **School grade / current math level** — which grade they are in, or what
   they can already do (times tables? fractions? multi-step problems?).
4. **Target level** — where they want to get to (pass the course? automatic
   mental math? prepare an exam?).
5. **Timeline** — this term / this year / 2+ years / custom.
6. **Daily study minutes** — 10 / 15 / 30 / 60 / custom.
7. **Learning goal** — school / exam / mental math automaticity / everyday
   math (shopping, cooking) / competition / interest.
8. **Learning style** — practice-first / theory-first / balanced (default).
9. **Gamification on/off** — default on.
10. **Interests (max 3, 1-2 words each)** — e.g. football, cooking, space. Used
    in word problems and examples. Short on purpose: everything stored here
    costs context on every turn.
11. **About you (1 line, optional)** — free sentence the tutor may reference
    ("vaig a 5è i em perdo amb les fraccions"). Skip if the learner has nothing to add.
12. **Tutor style** — `classic` (default: neutral tutor) or `friend` (warmer:
    cites last session, uses your interests). Changeable later in
    `preferences.tutor_style`.

If the learner does not know their level, run a quick 5-question placement
with closed math items, one at a time:

1. A double or halve (×2, ÷2) → early
2. A times-table fact → basic
3. A two-digit addition with carrying → intermediate
4. A fraction equivalence (1/2 = ?/4) → upper
5. A two-step word problem with fractions → advanced

Map score to level: 0-1 correct = early, 2 = basic, 3 = intermediate, 4 = upper, 5 = advanced.

### 4. Generate the learning plan

Present:

```markdown
## 🎉 Setup Complete!

**El teu perfil:**
- 👤 Nom: {name}
- 🔢 Assignatura: Matemàtiques
- 🗣️ Enunciat en: {native_language}
- 📊 Nivell: {current} → {target}
- 📅 Terminis: {timeline}
- ⏱️ Temps diari: {minutes} min
- 💡 Objectiu: {goal}

## 📋 Pla personalitzat

**Diari:**
- 🔁 **Review** — repàs espaiat ({X} min)
- 📚 **Facts** — càlcul automàtic ({Y} min)

**Alternant:**
- 🎲 **Go** — càlcul i procediment (dilluns/dimecres/divendres)
- 📖 **Problemes** (dimarts/dijous)
- 📝 **Raonament** o 🗣️ **Math talk** (cap de setmana)

**Setmanal:**
- 📊 **Stats** — mira el progrés (5 min)

### Fites
- Mes 1: {reasonable short-term}
- Mes 3: {quarter-way}
- Mes 6: {half-way}
- Data objectiu: {target}!

### Next Steps
1. Comença ara — prem 🎲 **Go**
2. Hàbit diari — 🔁 **Review** cada dia
3. Setmanal — 📊 **Stats** per veure les xifres
4. Stay consistent — even 10 min daily beats 2 hours weekly

**El teu camí cap a les matemàtiques fluides comença ara!** 🚀
```

### 5. Save the profile — ONE tool call

```
math_setup_profile({
  name: "<their first name>",
  target_language: "Math",          // the subject — the server field is still named this (WP1.7)
  native_language: "<the language of the statements, in English: Catalan, Spanish, …>",  // never guess
  current_level: "A1|A2|B1|B2|C1|C2",
  target_level:  "A1|A2|B1|B2|C1|C2",
  daily_minutes: <number>,
  goals: ["…"],                 // why they are learning, their words
  motivation: "school|exam|personal|family|work",
  interests: ["…"],             // up to 3, optional — warmer word problems
  about: "<one line>"           // optional
})
```

- Call it **once**, at the end of the interview, with what they actually said.
- **WP1.7 note:** the tool still validates CEFR levels and a language pair —
  the math level scale (m1…m6) is not in the server yet. Until it is, map the
  learner's math level onto CEFR honestly (early→A1, basic→A2, intermediate→B1,
  upper→B2, advanced→C1) and keep the real grade in `about`/`goals`. The
  curriculum front matter matches on `language: math`, so `target_language:
  "Math"` is what makes the course files resolve.
- If the learner does not know their level, run the placement (§3) and decide
  yourself — the call needs a level.
- It returns `REJECTED: …` when something is off (same language twice, a level
  that is not CEFR, no profile directory). Fix exactly that and call again once.
- On success the setup is marked complete and the app stops asking. Then show
  the plan (§4) and invite them to start practising.
- The 6 databases already exist; you never create or overwrite them.

### 5b. Claude Code / clone mode only

There is no `math_setup_profile` tool outside the FlowMath server. There, start
from the templates in `data-examples/`, resolve the directory with
`main_paths.ensure_data_dir()` and write the 6 files with the Write tool
(`learner-profile.json` filled in and `preferences.setup_complete = true`; the
other five as the empty templates). Never call `update-db.py` for this — that
script is for session updates, not bootstrapping.

### 6. Optional first lesson

```markdown
## 🎓 Vols fer la primera lliçó ara?

Una sessió curta de 5-10 min per veure què saps fer i agafar el ritme del sistema.

Escriu "yes" per començar, "later" per anar-hi pel teu compte.
```

If yes, hand off to the `math-learn` skill.

## Profile Updates (existing profile)

```markdown
# 👋 De nou per aquí, {name}!

Ja tens un perfil d'aprenentatge.

Què vols fer?

1. **Actualitzar el perfil** — canvia objectius, terminis o preferències
2. **Veure el pla actual** — mira el teu calendari d'estudi
3. **Reiniciar el progrés** — començar de zero (⚠️ esborra tot el progrés!)
4. **Cancel·lar** — deixa-ho tot com està

**Escriu 1, 2, 3 o 4:**
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

Learner runs `/math-setup`. After collecting the answers, run the placement if
needed, show the plan, call `math_setup_profile` once, offer the first lesson.

### Example 2 — returning-user profile reset

Learner: "reset my progress, I want to start over"

> Estàs a punt d'esborrar:
> - 42 sessions
> - una ratxa de 6 dies
> - 287 ítems de repàs
> - 12 patrons dominats
>
> Això és irreversible. Escriu `RESET` (majúscules) per confirmar, qualsevol altra cosa per cancel·lar.

## Critical Rules

- **Never auto-invoke.** Re-running this can reset a learner's progress. Must be an explicit `/math-setup`.
- **Confirm twice before reset.** "This will erase X days of progress, Y sessions, and Z mastered patterns. Proceed? (yes/no)".
- **Always seed all 6 files** — every other skill assumes they exist.
- **Back up before reset.** Hooks may not fire here; back up manually to `.backups/pre-reset-<timestamp>/`.
- **Don't invent data.** Start every file empty — progress, mistakes, mastery all start at zero. The system builds up from real sessions.
