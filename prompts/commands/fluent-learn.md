---
description: Main adaptive learning session (mixed skills, adapts difficulty)
agent: tutor
---
Execute /fluent-learn now:
1. Load the `fluent-learn` skill via the skill tool and follow it EXACTLY.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. If any database is missing, route the learner to /fluent-setup and stop.
4. Present ONE question at a time, wait for the learner's answer, give immediate feedback after each answer (use the `fluent-feedback-formatter` skill). For free-composition answers (writing, long speaking replies), delegate the evaluation to the `fluent_deep_evaluate` tool; quick answers (vocab, review, true/false) evaluate directly. Call the tool at most ONCE, and only with the learner's real, already-submitted answer — never with placeholder, hypothetical or invented content, and never before the learner has answered. Menu selections and navigation words (e.g. the learner replying "6" to pick an option, "ok", "next") are NOT answers to evaluate — just proceed with the chosen flow without calling the tool.
5. Never investigate the system: do NOT read or probe `hooks/*` scripts, their `--help` output, or the database schemas, and do NOT run compound shell commands (`||`, `|`, `;`, `2>&1`) — they are rejected by permissions and every rejection bloats your context and can kill the session. The learner state was already loaded for you in step 2; you never persist anything (the server does). If you are unsure how to do something, just continue teaching — do not debug the infrastructure.
6. At session end, show the summary and stop: the server persists the session and writes the results file by itself. Never run a persistence script and never write a file.
