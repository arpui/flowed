---
description: Vocabulary drills (flashcard-style, spaced repetition)
agent: tutor-fast
---
Execute /fluent-vocab now:
1. The `fluent-vocab` instructions are already in your system prompt. Follow them EXACTLY. Do NOT call the skill tool for them — the server loads them for you, on every turn, whether this is the first command of the session or the fifth.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. Present ONE word at a time, wait for the answer, then give immediate feedback (use the `fluent-feedback-formatter` skill).
4. At session end, show the summary and stop: the server persists the session and writes the results file by itself. Never run a persistence script and never write a file. At the very end, after the summary, send the `fluent:review_results` block described in the skill (one entry per queue item practised, `item_id` copied verbatim, `quality = floor(score / 2)`). It is the only thing that advances the spaced-repetition schedule: without it every item stays due for ever.
