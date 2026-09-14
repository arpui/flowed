---
description: Today's spaced-repetition review queue (SM-2)
agent: tutor-fast
---
Execute /fluent-review now:
1. Load the `fluent-review` skill via the skill tool and follow it EXACTLY.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. Review the due items ONE AT A TIME with immediate feedback, scoring each answer 0-10. Use the `fluent-sm2-calculator` skill for the SM-2 math and the `fluent-feedback-formatter` skill for the feedback format.
4. If no items are due, say so and suggest /fluent-learn instead.
5. At session end, show the summary and stop: the server persists the session and writes the results file by itself. Never run a persistence script and never write a file. At the very end, after the summary, send the `fluent:review_results` block described in the skill (one entry per queue item practised, `item_id` copied verbatim, `quality = floor(score / 2)`). It is the only thing that advances the spaced-repetition schedule: without it every item stays due for ever.
