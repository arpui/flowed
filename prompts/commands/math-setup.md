---
description: One-time onboarding — create the learner profile (name, language, level, goals). ADMIN ONLY.
agent: tutor-fast
---
> **Admin path.** The web app no longer sends learners here: a profile is
> provisioned by the system owner with `scripts/new-user.sh <id>` and filled in
> with `scripts/flowed-profile.py <id> --name … --native … --target … --level …`.
> This interview stays available for an admin who prefers to do it in the chat.

Execute /math-setup now:
1. The `math-setup` instructions are already in your system prompt. Follow them EXACTLY. Do NOT call the skill tool for them — the server loads them for you, on every turn, whether this is the first command of the session or the fifth.
2. Ask one question at a time; use the question tool for structured choices where the skill suggests them.
3. Collect: name, target language, native language, current level, target level, timeline, daily minutes, goals.
4. At the end, save everything with ONE `math_setup_profile` call (the skill has the exact fields). Do not write files and do not run scripts: in this runtime you have no way to, and the 6 databases already exist.
5. Never reset or overwrite an existing profile unless the learner explicitly asks for a reset.
6. If the learner is a DIFFERENT person or wants a DIFFERENT target language, they need their own profile directory, and only the system owner can create it (`scripts/new-user.sh <id>`). Say so; never try to create one.
Finish by confirming the profile was created and telling the learner to start with /math-review or /math-learn.
