---
description: Show learning stats, mastery levels, streak and achievements (read-only)
agent: tutor-fast
---
Execute /math-progress now:
1. The `math-progress` instructions are already in your system prompt. Follow them EXACTLY. Do NOT call the skill tool for them — the server loads them for you, on every turn, whether this is the first command of the session or the fifth.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. Show the full statistics dashboard to the learner. This command is READ-ONLY: do not modify any database.
