# Changelog

All notable changes to Fluent will be documented in this file.

## [0.5.2] — 2026-08-26

### Fixed

- `fluent_deep_evaluate` can no longer fall into a tool-call loop. The
  27B kept calling the tool with placeholder content (observed:
  "PLACEHOLDER", "test", "x", "n/a", "ignore", "stop", "final") — each call
  cost a full deep-model inference (~18 s, up to 7 per turn ≈ 2 min).
  Two guards in `plugins/fluent.js` (both cheap, no deep round-trip):
  reject empty/placeholder answers, and cap at one real evaluation per
  turn.
- The web no longer renders the learner's message bubble twice. The SSE
  `message.updated` event arrives without parts, so the text-match dedup
  against the optimistic bubble failed and a second identical bubble was
  created (`web/app.js`).
- `scripts/flowed-web.sh` sanitizes the learner instance's environment
  (`-u OPENCODE_CLIENT -u XDG_STATE_HOME`, `FLUENT_DEV=0`): when the
  launcher was an opencode desktop shell, the web serve inherited
  `OPENCODE_CLIENT=desktop`, the plugin flipped into dev mode and the
  tutor prompt (AGENTS.md) was stripped from web sessions.

### Changed

- The `fluent_deep_evaluate` chip in the web now reads "avaluant resposta"
  (with a call counter) instead of the raw tool name.
- `/fluent-learn`, `/fluent-speaking` and `/fluent-writing` state
  explicitly: call the tool at most ONCE, only with the learner's real
  answer — never with placeholder or invented content.

## [0.5.1] — 2026-08-26

### Fixed

- Deep-model resolution no longer breaks when the global opencode config
  changes. New project-local provider `fluent-deep` (port 12321, model alias
  `deep`) in `opencode.json`; `tutor.md` and `learner.md` now use
  `model: fluent-deep/deep`. Previously the agents referenced
  `llama-local//<path>` from the global config, so renaming the provider
  (e.g. to `vllm-local`) made every 27B turn fail with
  `ProviderModelNotFoundError`.

### Changed

- `scripts/flowed-web.sh` now prints the status of both models at startup
  (`deep` on 12321, `face` on 12322 — OK / NOT RUNNING). Informational only:
  it never starts or stops them. Ports overridable via
  `FLUENT_DEEP_PORT` / `FLUENT_FACE_PORT`.
- Deep-model contract: whatever is served on `127.0.0.1:12321` is used as-is.
  llama.cpp needs no changes (it accepts any model name); vLLM must be
  launched with `--served-model-name deep`.

## [0.5.0] — 2026-08-22

### Added

- Fast "face" model for short structured turns: `omnicoder-9b` on the RTX 3090
  (port 12322, `scripts/llama-face.sh`) drives a new `tutor-fast` agent for
  `/fluent-vocab`, `/fluent-review`, `/fluent-progress` and `/fluent-setup`.
  First content in ~3-8 s instead of 20-40 s. Long sessions
  (learn/writing/speaking/reading) and free chat stay on the 27B model.
- Live `pensant… N s` counter in the web UI while waiting for the first token,
  plus a one-time hint. The SSE death fix from 0.4.x stays (proxy
  `server.timeout(req, 0)`).
- `read-db.py` compact mode (default, ~11KB instead of ~33KB) with due-review
  items including content/answer, top weak patterns and mastery; `--full`
  returns the complete databases for setup/debug.

### Changed

- Merged `AGENTS.md` + `LEARNING_SYSTEM.md` into one compact tutor guide
  (~6KB); removed `instructions: ["LEARNING_SYSTEM.md"]` from `opencode.json`.
  Per-turn context dropped from ~65k to ~14-20k tokens, cutting the 27B
  first-token time from ~36 s to ~9-15 s.
- `llama-face.sh`: default GPU is now 1 (CUDA index != nvidia-smi index on
  this machine; verified with a compiled CUDA probe).

### Fixed

- None outstanding — web SSE streaming, incremental render and command
  routing (command frontmatter `agent` wins over the request `agent`
  parameter) all verified end-to-end with headless Chrome CDP.

## [0.4.0] — 2026-08-21


### Added

- opencode support — run Fluent with any local LLM, no Claude Code required
  (the `.claude/` plugin is unchanged; both front-ends work side by side):
  - `.opencode/commands/fluent-*.md` — the 8 slash commands for the opencode
    TUI. Each preloads the learner databases via `read-db.py` so the model
    always has learner context in the prompt.
  - `.opencode/agent/tutor.md` — dedicated tutor agent; pin your local model
    in its frontmatter.
  - `.opencode/plugins/fluent.js` — opencode plugin replacing the Claude Code
    hooks: JSON validation + timestamped backups on data edits, session-start
    welcome, daily session-end snapshot, pre-compact safety backup. Reuses
    the existing `hooks/*.py` scripts via the Bun shell API.
  - `opencode.json` — project config: `LEARNING_SYSTEM.md` always loaded as
    instructions.
- README: "opencode + local LLM" section.
- `docs/opencode-migration/PLAN.md` — migration plan & phase tracking.

## [0.3.0] — 2026-06-15

### Added

- Milestones support in the `update-db.py` session payload. The new
  `milestones[]` field accepts either a bare string or an object
  `{ "milestone": <required non-empty string>, "date": <optional YYYY-MM-DD,
  defaults to the session date> }`. Each milestone is recorded in both
  `session-log.milestones[]` and `learner-profile.achievements[]`. Validation
  rejects malformed entries (exit `1`, no files written); an unparseable
  `date` falls back to the session date.

## [0.2.1] — 2026-06-11

### Fixed

- Hooks no longer fail on Windows with `No such file or directory` (#5).
  Plugin hook commands in `hooks.json` used the bash default-value syntax
  `${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}`, which Claude Code's own
  variable substitution does not understand on Windows — it replaced the
  variable names but left the `:-` separators literal, producing a single
  garbage path. Hook commands now use plain `${CLAUDE_PLUGIN_ROOT}` (always
  set for plugin hooks) and invoke scripts via an explicit `python3`/`bash`
  interpreter so they don't depend on shebang handling under Git Bash.

## [0.2.0] — 2026-05-14

### Breaking changes

All 12 skills renamed with a `fluent-` prefix to prevent collisions with other
plugins and Claude Code built-ins. Update any muscle memory or external
references.

| Old | New |
|-----|-----|
| `/setup` | `/fluent-setup` |
| `/learn` | `/fluent-learn` |
| `/review` | `/fluent-review` |
| `/vocab` | `/fluent-vocab` |
| `/writing` | `/fluent-writing` |
| `/speaking` | `/fluent-speaking` |
| `/reading` | `/fluent-reading` |
| `/progress` | `/fluent-progress` |
| `sm2-calculator` | `fluent-sm2-calculator` |
| `db-updater` | `fluent-db-updater` |
| `feedback-formatter` | `fluent-feedback-formatter` |
| `session-analyzer` | `fluent-session-analyzer` |

New session result files use `/results/fluent-{skill}-session-{NNN}.md`.
Existing files using the older `{skill}-session-{NNN}.md` naming are still
read by `fluent-session-analyzer` — no migration required.

### Fixed

- Plugin install no longer fails on first DB read. Skills now invoke helper
  scripts via `${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/hooks/...`
  so the path resolves regardless of CWD.
- Added missing `hooks/ensure_data_dir.py` referenced by
  `fluent-setup`.

### Migration

```bash
claude plugin update fluent@m98
```

Then use the new slash commands. Your data (`~/.claude/fluent-data/` or
`./data/`) is unchanged.

## [0.1.0] — 2026-03-15

Initial release.
