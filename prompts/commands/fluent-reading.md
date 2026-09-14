---
description: Reading comprehension (short text + questions)
agent: tutor
---
Execute /fluent-reading now:
1. Load the `fluent-reading` skill via the skill tool and follow it EXACTLY.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. Present the text, wait for the learner to read it, then ask questions ONE AT A TIME with immediate feedback (use the `fluent-feedback-formatter` skill).
4. At session end, show the summary and stop: the server persists the session and writes the results file by itself. Never run a persistence script and never write a file.
