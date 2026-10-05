---
name: math-progress
description: Show the learner's math learning progress, statistics, mastery levels, streak, and achievements. Use when the learner asks "how am I doing", "show my progress", "stats", "dashboard", "what's my streak", "how many facts have I automated", or invokes /math-progress. Read-only — safe to auto-invoke.
allowed-tools: Read, Bash
---

# Progress Dashboard

## Overview

Show the learner a comprehensive, personalized progress report with visual statistics, skill mastery levels, trends, and next goals. This is read-only: do not modify any database files.

## When to Use

Trigger this skill when:

- Learner types `/math-progress`.
- Learner asks about their progress, statistics, streak, mastery, achievements, or how they're improving.
- Learner asks "how am I doing", "show me my stats", "am I getting better".
- After a session ends, if the learner wants a broader view than the session summary.

Skip this skill when the learner is mid-practice — the ongoing session skill already shows per-turn feedback, and opening the full dashboard interrupts the flow.

## Instructions

### 1. Load all 6 databases

Prefer the helper script over manual Read calls:

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

This returns a single JSON with all 6 databases + computed fields (`due_reviews_count`, `next_session_id`, `streak_active`, `days_since_last_session`).

If the helper is unavailable, fall back to reading each file directly. Resolve the data directory via `main_paths.data_dir()` first — do NOT hardcode `data/` (plugin installs store data elsewhere):

- `<data_dir>/learner-profile.json`
- `<data_dir>/progress-db.json`
- `<data_dir>/mastery-db.json`
- `<data_dir>/mistakes-db.json`
- `<data_dir>/spaced-repetition.json`
- `<data_dir>/session-log.json`

If any are missing, point the learner at `/math-setup` and stop.

### 2. Generate the report

Use this exact structure. Fill in values from the databases; compute percentages and progress bars yourself.

The math skills are `computation`, `steps`, `problems`, `reasoning`, `facts`.
NOTE (WP1.7): databases created before the math fork may still carry
language-era skill keys (`writing`, `speaking`, `vocabulary`, `reading`) in
`mastery-db` and `progress-db`. Render whatever keys exist under the math
label that best matches (writing→reasoning, vocabulary→facts, reading→problems,
speaking→math talk); never invent numbers for a key that is absent.

```markdown
# 📊 {learner_name}'s Math Learning Dashboard

**Last Updated:** {today}

---

## 🎯 Overview

**Current Level:** {current_level}
**Target Level:** {target_level}
**Progress to {next_level}:** {progress_bar} {percentage}%

**Days Studying:** {total_days}
**Current Streak:** 🔥 {streak_days} {day_or_days} {streak_message}
**Total Sessions:** {total_sessions}
**Total Study Time:** {total_minutes} minutes ({hours} hours)

---

## 💪 Skills Mastery

### Computation 🧮
**Level:** {n}/5 {stars}
**Accuracy:** {percent}%
**Progress:** {progress_bar}
**Last Practiced:** {date_or_never}

### Steps 🪜
**Level:** {n}/5 {stars}
**Accuracy:** {percent}%
**Progress:** {progress_bar}
**Last Practiced:** {date_or_never}

### Problems 📖
**Level:** {n}/5 {stars}
**Accuracy:** {percent}%
**Progress:** {progress_bar}
**Last Practiced:** {date_or_never}

### Reasoning ✍️
**Level:** {n}/5 {stars}
**Accuracy:** {percent}%
**Progress:** {progress_bar}
**Last Practiced:** {date_or_never}

### Facts ⚡
**Level:** {n}/5 {stars}
**Facts Automated:** {count}
**Facts Mastered:** {count}
**Progress:** {progress_bar}
**Last Practiced:** {date_or_never}

---

## 📈 Progress Trends

### Accuracy Over Time
{generate ASCII chart from progress-db weekly_summary}

### This Week's Summary
- **Sessions:** {count}
- **Minutes:** {total}
- **Exercises:** {count}
- **Accuracy:** {percent}%
- **Skills Practiced:** {list}

---

## 🎯 Focus Areas

### 🔴 Critical (Needs Urgent Attention)
{patterns from mistakes-db with mastery 0-1 and high frequency}

### 🟡 Working On (Making Progress)
{patterns from mistakes-db with mastery 2-3}

### 🟢 Strong (Almost Mastered)
{patterns from mistakes-db with mastery 4-5}

---

## 🔄 Spaced Repetition Status

**Items Due Today:** {count}
**Items Due This Week:** {count}
**Items Mastered:** {count}

---

## 🏆 Achievements Unlocked

{list from learner-profile → achievements, show locked ones with 🔒}

---

## 📅 Session History

| Date | Duration | Skill | Accuracy |
|------|----------|-------|----------|
{most recent 5-10 sessions from session-log}

---

## 🎯 Next Goals

**Short-term (This Week):**
{derive from weak patterns + due reviews}

**Medium-term (This Month):**
{derive from skill mastery gaps}

**Long-term:**
{derive from target level gap}

---

## 💡 Recommendations

1. {top weak area from mistakes-db}
2. {skill not practiced recently}
3. {due review count if > 0}

Press 🎲 **Go** to keep practicing, or pick a button at the top (🔁 Review · 📚 Facts · 📝 Raonament · 📖 Problemes · 🗣️ Math talk · 📊 Stats · 🏁 End) to act on this now.

---

"{personalized motivational message}"
```

### 3. Optional interpretation footer

Append this only if the learner seems new or asks what the numbers mean:

```markdown
## 📖 How to Read Your Stats

**Mastery Levels:**
- ⭐☆☆☆☆ (1/5): Just started
- ⭐⭐☆☆☆ (2/5): Learning
- ⭐⭐⭐☆☆ (3/5): Good
- ⭐⭐⭐⭐☆ (4/5): Strong
- ⭐⭐⭐⭐⭐ (5/5): Mastered — automatic

**Accuracy bands:** 0-40% intensive, 40-60% learning, 60-75% good, 75-85% strong, 85%+ excellent.
```

## Examples

### Example 1 — minimal (new learner, week 1)

> # 📊 {Name}'s Math Learning Dashboard
>
> **Current Level:** m4 → m5 (4% to m5)
> **Current Streak:** 🔥 3 days
> **Total Sessions:** 3 · 45 min
>
> ### Facts ⚡
> **Level:** 1/5 ⭐☆☆☆☆ · 12 facts automated · 0 mastered
>
> Computation / Steps / Problems / Reasoning: Not yet practiced.
>
> **Items Due Today:** 6 — press 🔁 **Review** first.
>
> "Three days in a row — momentum matters. Keep going!"

### Example 2 — trigger on natural-language question

Learner: "how am I doing?" / "how is my times-table going?" → auto-invoke this skill, render the full dashboard.

## Critical Rules

- **Read-only.** Never call `update-db.py` or edit any JSON in `data/`.
- **Use the current streak value** from `learner-profile.json`. Never guess or increment.
- **Use `day` vs `days`** correctly (1 = day, else days).
- **Skip sections with no data.** If reasoning hasn't been practiced, show "Not yet practiced" — don't fabricate numbers.
- **Cite the learner by name** from `learner-profile.json`.
- **Greet in the learner's own language** where natural — never in the language of an example.

## Why This Skill Auto-Invokes

Unlike session commands, this is a pure read. A false-positive (Claude opens the dashboard when the learner asked something else) costs only a few tokens — no DB corruption, no interrupted practice. Worth the lower trigger bar.
