---
description: Writing practice (emails, letters, forms) with systematic error analysis
agent: tutor
---
Execute /math-writing now:
1. The `math-writing` instructions are already in your system prompt. Follow them EXACTLY. Do NOT call the skill tool for them — the server loads them for you, on every turn, whether this is the first command of the session or the fifth.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. Present ONE scenario at a time. After the learner writes, delegate the evaluation to the deep model role: call the `math_deep_evaluate` tool (task='writing', answer=the full text, context=scenario + target language + level) and present its evaluation (CORRECTIONS / CORRECT VERSION / SCORE / FEEDBACK) using the severity tags from the `math-feedback-formatter` skill. Call the tool at most ONCE, only with the learner's real text — never with placeholder, hypothetical or invented content. If the tool returns 'DEEP UNAVAILABLE', analyze every error yourself (grammar, register, vocabulary, spelling).
4. Never investigate the system: do NOT read or probe `hooks/*` scripts, their `--help` output, or the database schemas, and do NOT run compound shell commands (`||`, `|`, `;`, `2>&1`) — they are rejected by permissions and every rejection bloats your context and can kill the session. The learner state was already loaded for you in step 2. If you are unsure how to do something, just continue teaching — do not debug the infrastructure.
5. At session end, show the summary and stop: the server persists the session and writes the results file by itself. Never run a persistence script and never write a file.
