# Core and domains — the WP5.2 architecture (2026-10-07)

**The decision:** one repo, one engine. `flowed` is the CORE (the learning
machine: SM-2, pacing, records, guards, the server loop, the web, the 6 DBs);
a domain is DATA + a thin adapter on top of it. Today there are two domains —
`language` and `math` — and the plan is that a future one (music? chess?
languages-of-the-office?) plugs in the same way, profiting from the core
without forking it again.

## What is core (never touches a domain)

server loop (agent.ts, llm.ts, http.ts, db bridge), hooks (update-db,
accumulate/persist-session, read-db, curriculum engine, SM-2, decay), the web
shell, the records format (`.records/*.jsonl`), the taxonomy FRAME (12 slots),
the checkpoint machinery, the guards that are practice-generic (turnGuard,
pictureGuard, bounce, pruneHistory).

## What is a domain (the manifest: `config/domain.json`)

| Piece | Where it lives | language | math |
|---|---|---|---|
| level scale | manifest `level_scale` | A1..C2 (CEFR) | m1..m7 |
| command/skill prefix | manifest `command_prefix` | `fluent-` | `math-` |
| curricula | `curriculum/en-*.md` | `curriculum/math-m*.md` |
| bank | `curriculum/bank/en-*` | `curriculum/bank/math-m*` |
| grader | language: bank.py word/grammar paths | math: `hooks/mathgrade.py` |
| taxonomy additions | manifest `taxonomy_extra` | vocabulary/spelling/grammar | sign/incomplete/procedure/wrong_operation/calculation |
| tutor layer | `skills/fluent-*`, `prompts/commands/fluent-*`, `prompts/agents/rules-language.md` | `skills/math-*`, `prompts/commands/math-*`, `rules-math.md` |
| domain code | `server/src/domain-language.ts` (the guards WP0.3 had stripped: foreign script, Speaking direction, due-words note, writing length) | `hooks/mathgrade.py`, steps v2, math guards in pacing.ts |
| TTS | manifest `tts` | on | off |
| web labels | manifest `web_labels` | language buttons | math buttons |

## How the core resolves the domain

1. `config/domain.json` is the manifest (single source; `default: math`).
2. `hooks/domain.py` is the Python authority: explicit `domain` field in
   `learner-profile.json` wins; else the level scale decides (A1..C2 →
   language, m1..m7 → math). `read-db.py` emits it as `computed.domain`.
3. `server/src/agent.ts` `domainForSession()` is the TS twin (same rule); it
   gates the language guards, the language pacing notes, and the
   `rules-<domain>.md` load (domain rules load LAST, on top of the shared
   `rules.md`).
4. The web gets it via `/api/math/progress` → `d.domain` (labels, subject).

## How a future domain plugs in (the checklist)

1. Add an entry to `config/domain.json` (scale, prefixes, globs, taxonomy
   additions, labels, tts).
2. Add its dirs: `curriculum/<dom>-*.md`, `curriculum/bank/<dom>-*`,
   `skills/<dom>-*`, `prompts/commands/<dom>-*`, `prompts/agents/rules-<dom>.md`.
3. If it needs grading beyond the generic word/number compare, add a grader
   module (like `mathgrade`) and name it in the manifest.
4. If it needs domain-specific guards/notes, add `server/src/domain-<dom>.ts`
   and gate it in `agent.ts` exactly as `domain-language.ts` is gated.
5. Tests: `tests/test_<dom>*.py` + a `server/test/<dom>*.test.ts` harness.
   Nothing in the core changes.

## Migration record (what WP5.2 did, 2026-10-07)

- Branch `wp52-core` (on top of WP4.1 `fa3b059`).
- Restored the language machinery WP0.3 had stripped, as `domain-language.ts`
  (verbatim from flowed's pacing.ts), gated by `domainForSession() ===
  "language"` at the three seams: the guard chain, `repairShownText`
  (foreign-script strip), `pacingNote` (writing length + due-words).
- Restored the language tutor layer: `skills/fluent-*` (11) and
  `prompts/commands/fluent-*` (10), copied from flowed.
- Split `rules.md` into shared + `rules-math.md` + `rules-language.md`.
- Added the manifest (`config/domain.json`), the Python adapter (`hooks/domain.py`)
  and its tests (`tests/test_domain.py`, 7).
- Wired `computed.domain` (read-db → http.ts → web labels).

## Verified / pending

- Verified: math suite stays green (the gates are inert for math profiles);
  `tests/test_domain.py` green; server harnesses + tsc green.
- PENDING (documented, not executed): the web BUTTONS per domain (the button
  bar is static in the web shell — it must read `web_labels` from the manifest);
  the TTS gate by domain (`config/domain.json tts` is the flag; `tts.ts` still
  reads `config/fluent.json`); the command-prefix regexos in tools.ts/commands.ts
  still match only `math-` — they must be parameterized by the manifest's
  `command_prefix` before a language profile can run commands here.
- The language domain has never been e2e-tested in the unified core — the
  `flowed` repo remains the reference until a `language` e2e scenario runs
  here. Rollback of any piece: `git revert` the WP5.2 commits.
