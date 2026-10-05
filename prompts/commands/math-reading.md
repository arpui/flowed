---
description: Word problems (short statement; the learner sets up and solves)
agent: tutor
---
Execute /math-reading now:
1. The `math-reading` instructions are already in your system prompt. Follow them EXACTLY. Do NOT call the skill tool for them — the server loads them for you, on every turn, whether this is the first command of the session or the fifth.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. Present ONE word problem at a time (short statement in the learner's language); the learner writes the operation(s) and the answer, then grade the setup (operation choice) and the calculation separately with immediate feedback (use the `math-feedback-formatter` skill).
4. At session end, show the summary and stop: the server persists the session and writes the results file by itself. Never run a persistence script and never write a file.
