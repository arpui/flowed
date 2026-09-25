# Registre complet de canvis — opencode + LLM local + multi-usuari + web

**Data:** 2026-08-21 · **Estat:** verificat (veure §5)
**Llegir amb:** `PLAN.md` (per què i en quines fases) i `WEB.md` (detall de l'accés per navegador). Aquest document diu **exactament què** canvia cada fitxer, per poder revisar o revertir qualsevol canvi sense fer diff.

---

## 1. Resum de fitxers

### Nous (12 — nucli opencode)

| Fitxer | Línies | Paper |
|---|---|---|
| `.opencode/commands/fluent-setup.md` | 12 | Comanda `/fluent-setup` (onboarding; **sense** injecció de BDs) + regla 6 multi-usuari |
| `.opencode/commands/fluent-learn.md` | 11 | Comanda `/fluent-learn` (sessió adaptativa mixta) |
| `.opencode/commands/fluent-review.md` | 11 | Comanda `/fluent-review` (repartició espaiada, items vencuts) |
| `.opencode/commands/fluent-vocab.md` | 10 | Comanda `/fluent-vocab` (drills de lèxic) |
| `.opencode/commands/fluent-writing.md` | 10 | Comanda `/fluent-writing` (escritura amb anàlisi d'errors) |
| `.opencode/commands/fluent-speaking.md` | 10 | Comanda `/fluent-speaking` (conversació escrita) |
| `.opencode/commands/fluent-reading.md` | 10 | Comanda `/fluent-reading` (comprensió lectora) |
| `.opencode/commands/fluent-progress.md` | 9 | Comanda `/fluent-progress` (dashboard d'estadístiques) |
| `.opencode/commands/fluent-use.md` | 20 | Comanda `/fluent-use` — canvia el perfil d'aprenent actiu (multi-usuari) |
| `.opencode/agent/tutor.md` | 16 | Agent tutor: model local fixat (`Qwen3.8-27B-Q8_0`), `temperature: 0.7`, persona curta |
| `.opencode/plugins/fluent.js` | 173 | Plugin: substitut dels hooks de Claude (validació, backups, benvinguda, pre-compact) + resolució multi-usuari |
| `.opencode/helpers/list-profiles.py` | 57 | Helper stdlib: llista perfils (`data/` + `~/.fluent/*/`) per al `/fluent-use` |

### Nous (7 — accés per navegador, Fase 0+1 web)

| Fitxer | Paper |
|---|---|
| `scripts/flowed-web.sh` | Llançador: modes `--web` (UI de sèrie, port 4097) i `--app` (frontend tancat, port 4100 + serve intern 4199), perfil (`~/.fluent/<id>`), port, password (generat o `FLUENT_WEB_PASSWORD`), mDNS (`fluent[-id].local`), `--stop`. **Ignora a propòsit** un `OPENCODE_SERVER_PASSWORD` heretat (per no compartir el password del serveidor opencode principal) |
| `scripts/flowed-web-proxy.mjs` | Proxy Bun sense dependències: un sol port públic → estàtics de `web/` + proxyfoca `/api/*` a `opencode serve` (passa l'`Authorization`; els 401 surten al navegador) |
| `web/index.html` | Frontend tancat: capçalera + estat, xat, 8 botons de modes, input |
| `web/app.js` | Client de l'API de l'opencode via `/api/*`: sessió persistent (`localStorage`), xat + comandes amb `agent:"learner"` fixat, render markdown (marked), chips de tools, abort si s'amaga la pestanya. **Nota:** el `POST /session/:id/command` exigeix la clau `arguments` (encara que sigui `""`) |
| `web/style.css` | Estil mòbil-first (safe-area, botons grans, bubbles) |
| `web/marked.min.js` | Renderer de markdown v12.0.2 (vendored — funciona sense internet) |
| `.opencode/agent/learner.md` | Agent tancat per a la UI web: mateix model/persona que `tutor` + permisos restrictius (whitelist de `bash`/`edit`, `skill` només `fluent-*`, `webfetch`/`task`/`question`/`external_directory` deny) |

### Modificats (4)

| Fitxer | Canvi |
|---|---|
| `opencode.json` | **+1 línia**: `"instructions": ["LEARNING_SYSTEM.md"]` (permisos existents intactes) |
| `README.md` | **+79 línies**: secció "🖥️ Alternative: opencode + local LLM" (requeriments, provider, comandes, taula de components, secció multi-usuari, notes) |
| `CHANGELOG.md` | **+20 línies**: entrada `[0.4.0] — 2026-08-21` (Added: suport opencode) |
| `.gitignore` | **+3 línies**: `.fluent-active` (marcador de perfil actiu) |

### No tocat (intencional)

- `.claude/**` (skills, hooks, settings) → Claude Code continua funcionant.
- `CLAUDE.md`, `LEARNING_SYSTEM.md`, `AGENTS.md`, `PRACTICE.md` → llegits pels dos front-ends.
- `data-examples/`, `tests/`, `docs/DB_SCRIPTS.md`.

### Auto-generats per l'opencode (no escrits a mà)

- `.opencode/package.json`, `.opencode/package-lock.json`, `.opencode/node_modules/`
  → els crea l'opencode per resoldre el runtime dels plugins (Bun). Gitignorats
  pel `.gitignore` propi del directori `.opencode/.gitignore`.

---

## 2. Detall per fitxer nou

### 2.1 Comandes `.opencode/commands/fluent-*.md`

Estructura comuna (frontmatter + cos):

```markdown
---
description: <descripció curta (anglès per a les 8 originals; català per a fluent-use)>
agent: tutor
---
Execute /fluent-<nom> now:
1. Load the `fluent-<nom>` skill via the skill tool and follow it EXACTLY.
2. Current learner state (preloaded by read-db.py):
!`python3 hooks/read-db.py`
3. If any database is missing, route the learner to /fluent-setup and stop.
4. <regla específica de la comanda: 1 pregunta alhora, feedback immediat,
   actualitzar les 6 BDs a la fi via la skill `fluent-db-updater`, etc.>
```

Decisions de disseny:
- **Injecció `` !`python3 hooks/read-db.py` ``** a totes excepte
  `/fluent-setup` (que crea les BDs; encara no existeixen). És el mecanisme
  clau perquè el model local tingui sempre el context de l'aprenent al prompt
  (elimina el mode de fallada principal: oblidar-se de llegir les BDs).
- `agent: tutor` → totes les sessions corren amb el model local fixat.
- Les skills s'hi carreguen via la tool `skill` (opencode detecta
  automàticament `skills/*/SKILL.md`).
- `PRACTICE.md` no s'afegeix a res (lègim específic de neerlandès, no general).

**`fluent-setup.md` — regla 6 (multi-usuari)**: si ja existeix un perfil a la
data dir activa i l'aprenent és una persona diferent (o vol una altra llengua):
preguntar un id curt (p. ex. `albert-en`), crear `~/.fluent/<id>/`, escriure el
camí absolut a `.fluent-active` (arrel del projecte) i crear les 6 BDs allà.
Tots els hooks ho recullen automàticament via `FLUENT_DATA_DIR`.

**`fluent-use.md`** (comanda nova, multi-usuari):
- Preinjecta la llista de perfils (`python3 .opencode/helpers/list-profiles.py`)
  i el perfil actiu (`cat .fluent-active`).
- Instruccions: activar un perfil existent = escriure el seu camí absolut com a
  contingut únic de `.fluent-active`; activar `data` = esborrar el fitxer;
  perfil inexistent = oferir de crear-lo (director `~/.fluent/<id>/` + marcador
  + flux complet de `/fluent-setup`).
- El canvi és **persistent** entre sessions (fins que es canviï de nou).

### 2.2 `.opencode/agent/tutor.md`

```markdown
---
description: Fluent language tutor — use for all /fluent-* sessions
mode: primary
model: llama-local//home/albert/aidev/models/Qwen3.8-27B-Q8_0.gguf
temperature: 0.7
---
<persona: tutor motivador, una pregunta alhora, segueix AGENTS.md,
LEARNING_SYSTEM.md i les skills fluent-*>
```

- Canviar de model = canviar només la línia `model:`.
- El provider `llama-local` ja estava configurat a
  `~/.config/opencode/opencode.jsonc` → `http://127.0.0.1:12321/v1`
  (llama.cpp, RTX 4090).

### 2.3 `.opencode/plugins/fluent.js` (173 línies)

Substitueix els hooks de Claude **sense duplicar lògica**: orquestra els
scripts Python existents de `hooks/` via l'API de shell de Bun (`$`)
que l'opencode injecta al context del plugin.

| Event opencode | Equivalent de Claude | Acció |
|---|---|---|
| `shell.env` | (resolució de data dir) | Injecciona `FLUENT_DATA_DIR` + `CLAUDE_PROJECT_DIR` a totes les execucions de shell → els scripts i els patrons `${CLAUDE_PROJECT_DIR:-.}` dels skills funcionen des de qualsevol CWD |
| `tool.execute.after` (`edit`/`write`) | PostToolUse | Si el fitxer és un `.json` dins la data dir activa → `validate-data.py` amb payload `{"tool_input":{"file_path":...}}` (mateix que Claude). exit 2 (JSON malformat) → toast d'error amb la via de recuperació |
| `event: session.created` | SessionStart | `session-start.py` → stdout com a toast (benvinguda, nivell, racha, revisions vencudes) |
| `event: session.idle` | SessionEnd | `session-end.py` (snapshot diari a `<data>/.backups/YYYYMMDD/`) amb guardà "màx. 1 cop/dia" (variable en memòria) |
| `experimental.session.compacting` | PreCompact | `mkdir -p <data>/.backups/precompact && cp -f <data>/*.json` + injecció de context resumit al compacte (recordatori del protocol del tutor) |

**Resolució multi-usuari** (funció `resolveDataDir`, exportada per a tests):

```
prioritat:  FLUENT_DATA_DIR (env-var)  >  .fluent-active (marcador)  >  <repo>/data
```

- Expansió de `~` a env-var i a marcador.
- `dataDir()` es resol **lazy** en cada hook: si `/fluent-use` reescriu el
  marcador a mig de sessió, el shell següent ja veu el nou directori.
- La validació (`inDataDir`), el backup pre-compact i els `hookEnv` dels
  scripts Python tot usa el mateix directori resolts.

**⚠️ Gotxes crítiques (si es toca aquest fitxer):**
1. **No importar `node:child_process`**: petrifica el carregament de plugins
   de l'opencode (hang silenciós al boot). Ús exclusiu de l'API `$` de Bun.
2. **No usar `$.escape()`** a les expressions interpolades: l'opencode/Bun ja
   escapa automàticament; escapar duplica les cometes i trenca la comanda.
3. Els scripts Python reben `FLUENT_DATA_DIR` explícitament via `hookEnv`
   (no confien en l'entorn heretat).

### 2.4 `.opencode/helpers/list-profiles.py`

Helper stdlib (sense dependències) per al `/fluent-use`:
- Escaneja `<repo>/data/learner-profile.json` (id `data`) i
  `~/.fluent/*/learner-profile.json` (id = nom del directori).
- Sortida, una línia per perfil: `<id>  <nom>  (<llengua>, nivell <CEFR>, racha <N>d)`
- Sense perfils → `(cap perfil — fes /fluent-setup per crear-ne un)`.
- Exit 0 sempre (tolerant a JSON corrupte → simplement no llista el perfil).

### 2.5 Accés per navegador (fitxers web)

Documentació completa a [`WEB.md`](WEB.md). Resum del disseny:

- **Dos modes, un llançador** (`scripts/flowed-web.sh`):
  - `--web` (Fase 0): `opencode web` oficial — UI completa (agents, models,
    fitxers) + les comandes `/fluent-*` (el frontmatter de cada comanda fixa
    l'agent `tutor`).
  - `--app` (Fase 1): `opencode serve` (només `127.0.0.1:<port+99>`) darrere
    del proxy Bun (`scripts/flowed-web-proxy.mjs`, un sol port públic):
    estàtics de `web/` + `/api/*` → API de l'opencode amb passada de l'
    `Authorization`.
- **Instància = aprenent**: cada llançament porta el seu port, el seu
  `FLUENT_DATA_DIR` (perfil `~/.fluent/<id>/` o el `data/` del repo) i el seu
  password (`OPENCODE_SERVER_PASSWORD` intern; el script **ignora a propòsit**
  un `OPENCODE_SERVER_PASSWORD` heretat de l'entorn i només honora
  `FLUENT_WEB_PASSWORD` o en genera un nou). mDNS: `fluent.local` /
  `fluent-<id>.local` (sense col·lisió amb l'`opencode.local` del 4096).
- **Frontend tancat** (`web/`): xat + 8 botons de modes; cada petició va amb
  `agent: "learner"` fixat al cos; sessió persistent a `localStorage`;
  `POST /session/:id/command` amb `arguments: ""` (clau obligatòria);
  markdown amb `marked.min.js` vendored (sense CDN).
- **Agent `learner`** (`.opencode/agent/learner.md`): persona tutor + permisos
  tancats — `bash` i `edit` només amb whitelist (scripts Fluent, `data/*.json`,
  `.fluent-active`, `results/*.md`), `skill` només `fluent-*`, i
  `webfetch`/`websearch`/`task`/`question`/`external_directory` en deny.
  Les regles de l'agent guanyen sobre les globals de l'`opencode.json`.
- El plugin de hooks funciona igual en les dues modes (corre al procés del
  serveidor; sense TUI, el toast de benvinguda cau al log).

**Gotxes trobades (web):**
1. `POST /session/:id/command` **requereix** la clau `arguments` (400
   "Missing key at [arguments]" si no és), encara que sigui `""`.
2. El password heretat de l'entorn (l'alias `opencodeserver` del `.bashrc` en
   defineix un per al 4096) feia que el script reutilitzés el password del
   serveidor principal → canviat a `FLUENT_WEB_PASSWORD` explícit.
3. Resposta bloquejant (sense streaming): amb el model local, ~30–120 s per
   resposta; el frontend ho assenyala amb "el tutor està pensant…".

---

## 3. Detall dels fitxers modificats

### 3.1 `opencode.json`

```diff
 {
   "$schema": "https://opencode.ai/config.json",
+  "instructions": ["LEARNING_SYSTEM.md"],
   "permission": { ... }   // permisos existents: intactes
 }
```

### 3.2 `README.md` — secció nova (després de la instal·lació de Claude Code)

"## 🖥️ Alternative: opencode + local LLM (no Claude)" amb:
- Requeriments (opencode, model local al port 12321, python3).
- Pas 1: apuntar el provider `llama-local` a la config global
  (`~/.config/opencode/opencode.jsonc`) — exemple JSON.
- Pas 2: obrir l'opencode a l'arrel del repo + primeres comandes.
- Taula de components (comandes, agents tutor/learner, plugin, helper, config).
- **Secció Multi-user / multiple languages**: les 3 maneres de triar el perfil
  (env-var → `/fluent-use` → defecte), convenció `~/.fluent/<id>/`,
  "un perfil = un usuari + una llengua objectiu".
- **Secció 3. Browser access (phone / tablet / other PC)**: els dos modes del
  `scripts/flowed-web.sh`, mDNS/URL, password per instància, enllaç a
  `docs/opencode-migration/WEB.md`.
- Notes: `.claude/` intacte; dades a `./data/` (o env-var / marcador);
  com canviar de model; enllaç a `docs/opencode-migration/PLAN.md`.
- (Correcció 2026-08-21: es va reparar una indentació errònia de 2 espais en
  aquesta secció que la convertia en text de continuació/bloc de codi.)

### 3.3 `CHANGELOG.md`

Entrada `[0.4.0] — 2026-08-21` → `### Added`: suport opencode (comandes, agent,
plugin, `opencode.json`), secció README, `docs/opencode-migration/PLAN.md`.

### 3.4 `.gitignore`

```diff
+# Active learner profile marker (multi-user; written by /fluent-use)
+.fluent-active
+
 # System files
 .DS_Store
```

---

## 4. Mecanisme multi-usuari — resum operatiu

```
Un repo, N aprenents (i N llengües per aprenent). Sense còpies del projecte.

Perfils:   <repo>/data/          → perfil per defecte (id "data")
           ~/.fluent/<id>/       → perfils multi-usuari (6 BDs + .backups/)

Resolució (plugin, lazy, en cada hook):
  1. FLUENT_DATA_DIR exportat al shell    (guanya sempre; per terminal)
  2. .fluent-active (arrel, gitignorat)   (persistent; escrit per /fluent-use)
  3. <repo>/data/                          (defecte)

Fluxos:
  - Usuari nou:    /fluent-setup → (si ja hi ha perfil actiu) regla 6
                   → crea ~/.fluent/<id>/ + marcador → onboarding allà.
  - Canviar:       /fluent-use <id>   (llista: /fluent-use sol)
  - Paralelisme:   dos terminals amb env-var diferents = dos perfils alhora
                   (el marcador és compartit; l'env-var l'eclipsa).
```

---

## 5. Verificacions fetes (2026-08-21)

| Prova | Resultat |
|---|---|
| `python3 tests/test_update_db.py` (scripts DB existents) | ✅ 12/12 |
| Harness del plugin amb bun — fases 1–3 (5 hooks) | ✅ 5/5 |
| E2E headless `opencode run` `/fluent-progress` (agent tutor + skill + plugin + Qwen3.8-27B, fixtures a `FLUENT_DATA_DIR=/tmp/fluent-e2e/data`) | ✅ PASS — dashboard correcte |
| Harness multi-usuari 1 (env-var) | ✅ 13/13 |
| E2E multi-usuari: `read-db.py` amb env-var apunta al directori correcte | ✅ PASS |
| Harness multi-usuari 2 (env > marcador > defecte, `~`, canvi a mig de sessió) | ✅ 15/15 |
| E2E `/fluent-use`: fixture `~/.fluent/fluent-e2e/` llistat per `list-profiles.py`, activat amb el marcador, `read-db.py` carrega el perfil correcte | ✅ PASS (fixture netejat) |
| Web Fase 0 (`opencode web` 4097): health amb password nou 200, amb el password del 4096 → 401, UI servida, agents `tutor`+`learner` registrats | ✅ PASS |
| Web Fase 1 (proxy 4100): health/estàtics/401 sense auth/creació de sessió via `/api/*` | ✅ PASS |
| Web Fase 1: `/fluent-progress` amb agent `learner` (fixture `~/.fluent/fluent-webtest/`) | ✅ dashboard correcte (73 s, model local) |
| Web Fase 1 — bloqueig: "executa `rm -rf`", "llegeix `~/.ssh/id_rsa`", "webfetch", "canvia a build", injecció de prompt (`cat /etc/passwd`) | ✅ tots rebutjats; dades intactes (md5) |
| Web Fase 1 — `update-db.py` real via l'agent learner (heredoc) | ✅ exit 0 + backup `.backups/pre-update-session-001/` |
| Web Fase 1 — snapshot diari del plugin en serve headless | ✅ `.backups/20260821/` (6 BDs) |
| `git diff` final: només els 4 fitxers modificats declarats (abans de la feina web) | ✅ confereix amb aquest registre |

Fixtures de prova sempre fora de `data/` real; `data/` queda buida (només
`.gitkeep`); `.fluent-active`, `~/.fluent/fluent-e2e` i
`~/.fluent/fluent-webtest` netejats després de les proves. L'instància Fase 0
(port 4097) queda activa per a proves de l'usuari; l'instància de test (4100)
s'ha aturat.

**Pendent (usuari):** e2e interactiu a la TUI — `/fluent-setup` real + sessió
`/fluent-vocab` completa (criteri 2–3 dels criteris d'acceptació globals de `PLAN.md` §5).

---

## 6. Com revertir

| Què | Com |
|---|---|
| Tot el suport opencode | Esborrar `.opencode/` (excepte si hi ha plugins propis), `opencode.json`, i revertir `README.md`, `CHANGELOG.md`, `.gitignore` (els trossos marcats a §3) |
| Només multi-usuari | Esborrar `.opencode/commands/fluent-use.md`, `.opencode/helpers/`, revertir la regla 6 de `fluent-setup.md`, `.fluent-active` del `.gitignore`, i a `fluent.js` restaurar `dataDir` a `path.join(root, "data")` (4 punts: `hookEnv`, `inDataDir`, `shell.env`, pre-compact) |
| Només l'accés web | `scripts/flowed-web.sh --stop` (aturar instàncies) + esborrar `web/`, `scripts/flowed-web.sh`, `scripts/flowed-web-proxy.mjs`, `.opencode/agent/learner.md` i la secció "Browser access" del README + `WEB.md` |
| Un canvi puntual | El `git diff` de cada fitxer coincideix exactament amb §2–§3; no hi ha canvis amagats enlloc altressí |
