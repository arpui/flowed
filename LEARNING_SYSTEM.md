# Learning System — the science this tutor runs on

**Purpose:** the evidence-based principles every practice command, guard and
note in this app is built around. This document explains WHY the system behaves
the way it does; it is domain-neutral (it says nothing about which subject is
being taught) and it is not a runbook — the tutor's behaviour lives in
`AGENTS.md`, `prompts/agents/` and the skills, and the scheduling math lives in
code.

**Last Updated:** 2026-10-05

---

## 1. Active recall

Retrieval is the learning event, not exposure. The learner must produce the
answer from memory before seeing it — which is why the tutor always presents
one exercise and waits, never shows an answer before the attempt, and never
lets a hint collapse into the answer itself. Recognition ("is this right?") is
weak practice; recall ("write/solve it") is what moves the item forward.

## 2. Desirable difficulty — keep success at 60–70%

An item that is too easy is re-read, not learned; one that is too hard teaches
nothing and burns motivation. The system targets roughly **60–70% success per
session**: sustained ≥80% means the material is too easy and the tutor steps
up, ≤50% means it is too hard and the tutor steps down. Difficulty comes from
the learner's own history (due items, weak patterns, mastery level), not from
a fixed script.

## 3. Interleaving

Practising one thing in a blocked run feels productive and measures poorly.
Mixing skill types and item types within a session — and mixing old (due)
items with new material — forces the learner to first identify *what kind* of
problem this is, which is most of the real skill. The server assigns
competences and due items turn by turn so a single session interleaves by
construction; the tutor must not quietly settle into one type.

## 4. Immediate, explanatory feedback

Feedback only helps when it arrives while the attempt is still in working
memory, and only when it explains the *why*, not just the what. Every answer
gets a score, per-error corrections with a one-line reason, and the correct
version — and previously-weak patterns that came out right are called out,
because noticing improvement is itself reinforcement. Feedback that is vague
("nice job") or delayed to the end of the session is wasted.

## 5. Spaced repetition

Items enter a queue and resurface at expanding intervals, so each review
happens near the forgetting point. The single implementation of the schedule
is **`hooks/update-db.py`** (SM-2: `calculate_sm2` and its callers) — the
quality scale, interval growth and easiness math live there and nowhere else.
Do not restate or reimplement the formulas anywhere else; if the schedule
needs to change, change that file. Everything upstream (the tutor's quality
judgement, the review block that closes a session) just feeds it quality
values.

## 6. Mastery and decay

Each skill/pattern carries a mastery level (0–5). Sustained success raises it,
sustained failure lowers it — and because memory decays, an item that goes
unpractised is not "done": it stays in the queue and its interval only holds
while it keeps being recalled. The point of the queue and the mastery
downgrade together is that old wins are re-earned, not assumed.

## 7. Gamification, used honestly

Streaks, achievements and visible progress exist to make *showing up*
rewarded, not to flatter. They track real events (sessions, correct answers,
streak lengths, a failing pattern turning strong) and are celebrated when they
happen. Inflating scores or praising wrong answers to keep streaks pretty
destroys the measurement the rest of the system depends on — encouragement is
about tone, never about the numbers.

---

## How the pieces map to the principles

| Principle | Where it is enforced |
|---|---|
| Active recall | one-question flow, wait-for-answer, no answer-first (skills + guards) |
| 60–70% success | difficulty adaptation from due items / weak patterns / mastery |
| Interleaving | per-turn competence assignment, due items mixed with new material |
| Immediate feedback | feedback format, `math_record_answer`, feedback-rebuild guards |
| Spaced repetition | `hooks/update-db.py` (the only SM-2 implementation) |
| Mastery & decay | `mastery-db.json`, review queue, mastery up/down rules |
| Gamification | streaks + achievements in `learner-profile.json` |

If a new feature contradicts one of these seven principles, it needs a reason
strong enough to override the research — not just a convenience.
