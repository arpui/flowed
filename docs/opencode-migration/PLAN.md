# Fluent → opencode + LLM local — Pla de migració i seguiment

**Obert:** 2026-08-21
**Estat global:** ✅ **COMPLETAT I VERIFICAT** (2026-08-21)

> Aquest directori (`docs/opencode-migration/`) és l'espai de seguiment de la
> migració. Cada fase s'hi documenta amb estat, decisions, fitxers i
> criteris de verificació. El log d'evolució (§9) és l'historial canvi a canvi.
>
> **Documents:**
> - `PLAN.md` (aquest) — per què, en quines fases, decisions, riscos.
> - [`CHANGES.md`](CHANGES.md) — **registre complet de canvis**: fitxer a
>   fitxer, què conté, detall dels fitxers modificats, mecanisme multi-usuari,
>   verificacions fetes i com revertir.
> - `viabilitat-del-projecte-amb-opencode-i-llm-local.json` — export de la
>   sessió original d'anàlisi de viabilitat (registre de conversa; només lectura).

---

## 1. Context i motivació

- **Problema:** Claude Code és car i limitat en tokens. No es vol fer servir
  Claude com a agent del tutor.
- **Objectiu:** Fer servir Fluent des de **opencode** amb una **LLM local**
  (llama.cpp a `127.0.0.1:12321`, RTX 4090): cost 0 €, sense límit de tokens,
  dades 100% locals.
- **Restriccions d'aquesta feina:**
  - No fer servir git (no commits, no branches).
  - No tocar res dins `.claude/` → Claude Code ha de seguir funcionant
    (compatibilitat doble).

## 2. Valoració de factibilitat (2026-08-21)

**Veredicte: SÍ, és possible.** El projecte ja és ~80% compatible amb
opencode. Evidència:

| Component | Estat amb opencode |
|---|---|
| 12 skills (`skills/*/SKILL.md`) | ✅ Detecció automàtica (verificat en sessió real: les 12 visibles via la tool `skill`) |
| `AGENTS.md` (paper de tutor) | ✅ Opencode el carrega sol com a regles de projecte |
| Scripts Python (`hooks/*.py`) | ✅ 100% stdlib (sense pip); resolució de `./data` per fallback de CWD; `update-db.py` ja fa writes atòmics + backup pre-escriptura + validació estricta (exit 1/2) |
| LLM local | ✅ Provider `llama-local` ja configurat a `~/.config/opencode/opencode.jsonc` → `http://127.0.0.1:12321/v1` |
| `opencode.json` de projecte | ✅ Ja existeix (permisos bash permesos) |

**Diferències de comportament conegudes (no bloquejants):**

| Aspecte | Claude Code | opencode | Mitigació |
|---|---|---|---|
| Comandes `/fluent-*` | Natives (skills = comandes) | No existeixen → cal `.opencode/commands/` | Fase 1 |
| `disable-model-invocation` | Respectat (gating dur) | **Ignorat** (frontmatter desconegut) | Gating tou via descriptions; risc baix |
| `allowed-tools` | Respectat | Ignorat | El model usa les seves tools natives |
| Hooks (PostToolUse/SessionStart/SessionEnd/PreCompact) | Config a `settings.json` | No hi ha equivalent de config | Plugin JS (Fase 2) reutilitzant els mateixos scripts Python |
| `AskUserQuestion` (fluent-setup) | Tool nativa | La model usa la tool `question` d'opencode | Cap acció |

## 3. Decisions preses

| Decisió | Opció triada | Motiu |
|---|---|---|
| Model LLM | **Qwen3.8-27B-Q8_0** (ja corrent al port 12321) | Model dens més potent disponible a `/home/albert/aidev/models/`; el 35B-A3B (MoE) té només 3B actius → pitjor seguiment d'instruccions; el TQ3_4S perd qualitat de quantització |
| Abast | **Completa (Fases 1+2+3)** | Substitució completa de Claude |
| Interfície | TUI d'opencode amb `/fluent-*` | Mateixa UX i muscle memory que a Claude Code |
| Dades | `./data` (relatiu a l'arrel del repo) | Fallback de CWD de `fluent_paths.py` + `FLUENT_DATA_DIR` injeccionat pel plugin |

## 4. Arquitectura objectiu

```
opencode TUI (model: Qwen3.8-27B @ 127.0.0.1:12321)
├── AGENTS.md ................ auto-carregat (paper de tutor)          [ja funciona]
├── LEARNING_SYSTEM.md ....... afegit a `instructions` (always-on)     [Fase 1]
├── skills/* (12) .... detectats automàticament                 [ja funciona]
├── .opencode/commands/*.md .. comandes /fluent-*                       [Fase 1, NOU]
├── .opencode/agent/tutor.md . agent tutor amb model local fixat        [Fase 3, NOU]
├── .opencode/plugins/fluent.js  substitut dels hooks de Claude         [Fase 2, NOU]
└── hooks/*.py ........ scripts stdlib, SENSE canvis             [ja funciona]
```

## 5. Fases

### Fase 1 — Nucli (comandes + metodologia) — ✅ fet (2026-08-21)

Objectiu: poder fer `opencode` a l'arrel del repo i executar `/fluent-*` amb
el context de l'aprenent garantit al prompt.

- [x] Crear 8 fitxers `.opencode/commands/fluent-*.md`
      (`setup`, `learn`, `review`, `vocab`, `writing`, `speaking`,
      `reading`, `progress`).
- [x] Modificar `opencode.json` (projecte): afegir
      `"instructions": ["LEARNING_SYSTEM.md"]` (permisos existents intactes).

**Disseny del template de comanda** (exemple `/fluent-learn`):

```markdown
---
description: Main adaptive learning session (mixed skills)
agent: tutor
---
Execute /fluent-learn now:
1. Load the `fluent-learn` skill via the skill tool and follow it EXACTLY.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. If any database is missing, route the learner to /fluent-setup and stop.
4. One question at a time, wait for the answer, immediate feedback,
   update the 6 DBs at session end via the `fluent-db-updater` skill.
```

Notes de disseny:
- La injecció `` !`python3 hooks/read-db.py` `` **garanteix** que el
  model local tingui el context de l'aprenent al prompt (elimina el principal
  mode de fallada: oblidar-se de llegir les BDs).
- `/fluent-setup` **sense** injecció (crea les BDs; no existeixen encara).
  Els altres 7, amb injecció.
- `PRACTICE.md` NO s'afegeix a `instructions` (lègim específic de preparació
  d'examen de neerlandès, no és general).

**Criteris de verificació de la fase:**
1. `python3 tests/test_update_db.py` → passa.
2. Test headless: fixtures a `FLUENT_DATA_DIR=/tmp/fluent-e2e/data` (a partir
   de `data-examples/`) + `opencode run` amb el prompt de `/fluent-progress`
   → mostra les estadístiques correctes. (No contaminar `data/` real.)

### Fase 2 — Plugin de hooks (seguretat de dades) — ✅ fet (2026-08-21)

Objectiu: reproduir els hooks de Claude sense reinventar lògica (els scripts
Python existents ja fan tot; el plugin només els orquestra).

Fitxer nou: `.opencode/plugins/fluent.js` (JS sense dependències externes).

> **⚠️ Gotxes trobades durant la implementació (important si es toca):**
> 1. `import { execFileSync } from "node:child_process"` **petrifica el
>    carregament de plugins d'opencode** (hang silencios al boot, abans de
>    crear la sessió). Cal usar l'API de shell de Bun (`ctx.$`) que opencode
>    injecta al context del plugin.
> 2. **No usar `$.escape()` dins els templates de Bun shell**: opencode/Bun
>    ja escapa les expressions interpolades automàticament; escapar aquí
>    duplica les cometes i trenca la comanda (`python3 "/ruta"` →
>    `python3 cwd/"/ruta"`).

| Hook de Claude | Event opencode | Acció del plugin |
|---|---|---|
| PostToolUse `Write\|Edit` (validació + backup) | `tool.execute.after` (tools `edit`/`write`) | Si el fitxer és `data/*.json` → cridar `validate-data.py` amb stdin `{"tool_input":{"file_path":...}}` (mateix payload que Claude). Si exit 2 (JSON malformat) → avisar l'usuari |
| SessionStart (benvinguda + stats + avisos de revisions) | `session.created` | `session-start.py` → mostrar el seu stdout (toast TUI o log) |
| SessionEnd (snapshot diari `.backups/YYYYMMDD/`) | `session.idle` | `session-end.py` amb guardà "màx. 1 cop/dia" (guardà en memòria del plugin) |
| PreCompact (backup de seguretat) | `experimental.session.compacting` | Mateixa operació que `precompact-backup.sh`: `mkdir -p data/.backups/precompact && cp data/*.json data/.backups/precompact/` |
| (resolució de data dir) | `shell.env` | Injeccionar `FLUENT_DATA_DIR=<arrel>/data` i `CLAUDE_PROJECT_DIR=<arrel>` en tota execució de shell → els scripts i els patrons `${CLAUDE_PROJECT_DIR:-.}` dels skills funcionen des de qualsevol CWD |

**Criteris de verificació de la fase:**
1. Editar un `data/*.json` (edició vàlida) → apareix backup
   `.backup-YYYYMMDD-HHMMSS` + missatge de validació OK.
2. Escriure JSON malformat → el plugin avisa (exit 2 de `validate-data.py`).
3. `session.idle` → snapshot diari a `data/.backups/YYYYMMDD/` (una sola vegada/dia).
4. Compactació de sessió → backup a `data/.backups/precompact/`.

### Fase 3 — Polida (agent, docs, e2e) — ✅ fet (2026-08-21)

- [x] `.opencode/agent/tutor.md`:
  ```markdown
  ---
  description: Fluent language tutor — use for all /fluent-* sessions
  mode: primary
  model: llama-local//home/albert/aidev/models/Qwen3.8-27B-Q8_0.gguf
  temperature: 0.7
  ---
  <persona curta: tutor motivador, una pregunta alhora, segueix
  AGENTS.md + LEARNING_SYSTEM.md + les skills fluent-*>
  ```
  Les comandes hi apunten via `agent: tutor`.
- [x] `README.md`: secció "opencode + local LLM (no Claude)" (requeriments,
  config del provider, com executar, taula de components, com canviar de
  model).
- [x] `CHANGELOG.md`: entrada `[0.4.0]` amb suport opencode.
- [x] **E2E headless** (`opencode run --command fluent-progress`): PASS —
  agent tutor + skill + plugin + model local → dashboard correcte amb
  fixtures (2026-08-21).
- [ ] **E2E interactiu** (TUI, per l'usuari):
  1. `opencode` a l'arrel del repo.
  2. `/fluent-setup` → crea els 6 JSON a `data/`.
  3. `/fluent-vocab` → sessió completa de Q&A; a la fi, `update-db.py`
     amb exit 0 i backup a `data/.backups/pre-update-<session_id>/`.

**Criteris d'acceptació globals (totes les fases):**
1. `python3 tests/test_update_db.py` → passa.
2. `/fluent-setup` crea els 6 fitxers JSON a `data/`.
3. Una sessió `/fluent-vocab` completa deixa les BDs actualitzades + backup.
4. JSON corrupte després d'una edició → avís del plugin.
5. Tot el flux funciona sense cost de tokens extern.
6. `.claude/` intacte → Claude Code continua funcionant.

## 6. Fitxers planificats

| Fitxer | Acció | Fase |
|---|---|---|
| `.opencode/commands/fluent-setup.md` | Nou | 1 |
| `.opencode/commands/fluent-learn.md` | Nou | 1 |
| `.opencode/commands/fluent-review.md` | Nou | 1 |
| `.opencode/commands/fluent-vocab.md` | Nou | 1 |
| `.opencode/commands/fluent-writing.md` | Nou | 1 |
| `.opencode/commands/fluent-speaking.md` | Nou | 1 |
| `.opencode/commands/fluent-reading.md` | Nou | 1 |
| `.opencode/commands/fluent-progress.md` | Nou | 1 |
| `opencode.json` | Modificat (+`instructions`) | 1 |
| `.opencode/plugins/fluent.js` | Nou | 2 |
| `.opencode/agent/tutor.md` | Nou | 3 |
| `README.md` | Modificat (secció opencode) | 3 |
| `CHANGELOG.md` | Modificat (entrada nova) | 3 |
| `.claude/**` | **No tocar** | — |

## 7. Riscos i mitigacions

| Risc | Severitat | Mitigació |
|---|---|---|
| El Qwen 27B trenca el protocol "una pregunta alhora" | Mitjana | BDs pre-injectades al prompt; rules explícites al template de cada comanda |
| JSON lleugerament dolent per a `update-db.py` | Mitjana | Validació estricta del script (exit 1 → error net → el model reintenta); l'exemple de payload a `references/db-updater-payload.example.json` ja el refereixen les skills |
| Qualitat de correcció gramatical per a B2+/C inferior a Claude | Baixa–Mitjana | Dependrà de la llengua/nivell de l'aprenent; si cal, canviar de model local (només cal tocar `model` a `.opencode/agent/tutor.md`) |
| `disable-model-invocation` ignorat → el model podria auto-iniciar sessions | Baixa | Gating tou via descriptions ("Triggered only when the learner types /fluent-X") |
| `session.idle` dispara `session-end.py` massa sovint | Baixa | Guardà "una vegada/dia" en memòria del plugin |

## 8. Referències

- Docs opencode: skills (`skills` auto-detecció), commands
  (`.opencode/commands/*.md`, injecció `` !`cmd` ``), plugins (events
  `tool.execute.after`, `session.idle`, `session.compacting`, `shell.env`,
  `tui.toast.show`), rules (`AGENTS.md` > `CLAUDE.md`).
- `docs/DB_SCRIPTS.md` — esquema complet del payload de `update-db.py`.
- `references/` — templates (payload DB, feedback, fitxer de sessió,
  SM-2 amb exemples).
- `tests/test_update_db.py` — test de fum dels scripts (sense dependències).

## 9. Log d'evolució

| Data | Canvi |
|---|---|
| 2026-08-21 | Anàlisi completa del projecte (skills, scripts, hooks, config). Factibilitat confirmada amb evidència (skills ja detectades per opencode, scripts stdlib amb fallback CWD, provider local ja configurat). Decisions: Qwen3.8-27B-Q8 + abast complet. Pla de 3 fases definit. |
| 2026-08-21 | **Execució completa de les Fases 1–3.** 10 fitxers nous + 3 modificacions. Verificació: tests unitaris 12/12, harness de plugin amb bun (5/5 hooks), e2e headless `/fluent-progress` PASS (agent tutor + skill + plugin + Qwen3.8-27B). Bugs trobats i resols: deadlock de `node:child_process` al carregament de plugins (canvi a API `ctx.$` de Bun) i doble-escaping de `$.escape()` a templates. Fixtures de prova netejades de `data/`. Pendents: e2e interactiu a la TUI (usuari). |
| 2026-08-21 | **Suport multi-usuari al plugin.** Abans, el plugin forçava `FLUENT_DATA_DIR=<repo>/data` a tots els shells i anul·lava el mecanisme multi-learner del sistema. Ara `resolveDataDir()` respecta un `FLUENT_DATA_DIR` preexistents (amb expansió de `~`) i només injeixa el fallback si no és; validacions, backups i scripts Python operen sobre el mateix directori resolts. Harness ampliat: 13/13 PASS + e2e del script amb env-var. Ús: `export FLUENT_DATA_DIR=~/.fluent/<nom>` abans d'obrir l'opencode → un repo, un directori de dades per aprenent/idioma, sense còpies del projecte. |
| 2026-08-21 | **Comanda `/fluent-use` (canvi d'usuari/idioma en sessió, persistent).** Prioritat de resolució: env-var `FLUENT_DATA_DIR` > marcador `.fluent-active` (a la arrel, gitignorat) > `data/` del repo. Nous: `.opencode/commands/fluent-use.md` (llista perfils i activa un; si no existeix, ofereix de crear-lo amb el flux de setup), `.opencode/helpers/list-profiles.py` (stdlib: escaneja `data/` + `~/.fluent/*/`), `fluent-setup.md` amb regla 6 (perfil nou → `~/.fluent/<id>/` + marcador, sense re-setup). El plugin ressol `dataDir()` de forma lazy en cada hook (el canvi es veu al shell següent). README actualitzat (secció multi-usuari). |
| 2026-08-21 | **Registre complet de canvis.** Creat `CHANGES.md` (fitxer a fitxer: 12 nous + 4 modificats amb detall, mecanisme multi-usuari operatiu, totes les verificacions amb resultats, guia de revert). Enllaçat des de l'encapçalament d'aquest pla. Total final: 12 fitxers nous + 4 modificats (+102 línies), `.claude/` intacte. |
| 2026-08-21 | **Accés per navegador (Fases 0+1 web).** Nova doc `WEB.md`. Nous: `scripts/flowed-web.sh` (llançador `--web`/`--app`/`--stop`, perfil, port, password generat o `FLUENT_WEB_PASSWORD`, mDNS `fluent[-id].local`; ignora `OPENCODE_SERVER_PASSWORD` heretat), `scripts/flowed-web-proxy.mjs` (proxy Bun un port: estàtics + `/api/*`), `web/` (frontend tancat: xat + 8 botons, agent `learner` fixat, marked vendored), `.opencode/agent/learner.md` (permisos tancats: whitelist bash/edit, skills `fluent-*` només, webfetch/task/question deny). El teu servidor 4096 (projecte home, password propi) queda intacte; Fluent web a 4097 (UI sèrie) i 4100 (app tancada). Verificat: e2e `/fluent-progress` amb learner (73 s), 5 atacs adversarials rebutjats (rm -rf, ~/.ssh, webfetch, canvi d'agent, prompt injection) amb dades intactes, `update-db.py` real via heredoc OK + backups, snapshot diari del plugin en serve headless OK. README: secció "Browser access" + correcció d'indentació. |
