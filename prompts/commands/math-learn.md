---
description: Main adaptive math session (closed items, mixed practices, adapts difficulty)
agent: tutor
---
Execute /math-learn now:
1. The `math-learn` instructions are already in your system prompt. Follow them EXACTLY. Do NOT call the skill tool for them — the server loads them for you, on every turn, whether this is the first command of the session or the fifth.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. If any database is missing, route the learner to /math-setup and stop.
4. Present ONE closed exercise at a time (one right result or one right line of work), wait for the learner's answer, give immediate feedback after each answer (use the `math-feedback-formatter` skill). Closed items (computation, facts, choose/compare, steps) you grade yourself against the exact value — never delegate those. Only for free-composition answers (a reasoning explanation, a long math-talk reply) delegate the evaluation to the `math_deep_evaluate` tool. Call the tool at most ONCE, and only with the learner's real, already-submitted answer — never with placeholder, hypothetical or invented content, and never before the learner has answered. Menu selections and navigation words (e.g. the learner replying "6" to pick an option, "ok", "next") are NOT answers to evaluate — just proceed with the chosen flow without calling the tool.
5. Never investigate the system: do NOT read or probe `hooks/*` scripts, their `--help` output, or the database schemas, and do NOT run compound shell commands (`||`, `|`, `;`, `2>&1`) — they are rejected by permissions and every rejection bloats your context and can kill the session. The learner state was already loaded for you in step 2; you never persist anything (the server does). If you are unsure how to do something, just continue teaching — do not debug the infrastructure.
6. At session end, show the summary and stop: the server persists the session and writes the results file by itself. Never run a persistence script and never write a file.
