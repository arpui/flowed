---
description: Word problems (short statement; the learner sets up and solves)
agent: tutor
---
Execute /math-reading now:
1. The `math-reading` instructions are already in your system prompt. Follow them EXACTLY. Do NOT call the skill tool for them — the server loads them for you, on every turn, whether this is the first command of the session or the fifth.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. Present ONE word problem at a time (a short STORY in the learner's language — never a bare expression); the card must ask for the operation(s), one per line, and the result (a bare answer alone will not score). When she answers, delegate the evaluation to the deep model role: call `math_deep_evaluate` with task='word-problem', answer=her full text verbatim, context=the statement + the operation(s) it calls for + the exact result + level and language — at most ONCE per answer, never with invented content. Present its evaluation (CORRECTIONS / CORRECT VERSION / SCORE / FEEDBACK) in the canonical feedback format (use the `math-feedback-formatter` skill), reading the corrections as setup (`wrong_operation`/`misread`) vs calculation (`calculation`/`carrying`…), and record the answer with `math_record_answer` using skill `problems`. If the tool returns 'DEEP UNAVAILABLE', grade the four rubric dimensions yourself in the same format.
4. At session end, show the summary and stop: the server persists the session and writes the results file by itself. Never run a persistence script and never write a file.
