# Fluent (fluent_dev2) — Descripció, arquitectura i propostes de millora

**Data:** 2026-09-12 · **Abast revisat:** `/home/albert/projects/fluent_dev2`
(codi del servidor, scripts d'orquestració, hooks Python, prompts, web, docs).
No s'ha inspeccionat cap perfil d'alumne de `~/.fluent/` (en ús).

Aquest document té tres parts: **(A)** què és el projecte i com està organitzat,
**(B)** què s'ha afegit respecte el Fluent original, **(C)** deute tècnic
detectat i propostes de millora prioritzades.

---

# A. El projecte

## A.1 D'on ve i on és ara

Fluent neix com a **plugin de Claude Code** (`fluent@m98`): un tutor d'idiomes
fet de *prompts* i no de codi — 12 skills en Markdown, 5 hooks Python i 6 bases
de dades JSON per alumne. Tot el "programa" era instruccions per a un agent
(Claude Code), i l'agent feia de runtime.

`fluent_dev2` és l'evolució d'aquella idea en una direcció diferent:

1. **Alliberat de l'agent.** Ja no depèn de Claude Code ni d'opencode en temps
   d'execució. Hi ha un **servidor propi** (`server/`, Bun + TypeScript) que
   parla directament amb endpoints OpenAI-compatibles i que implementa ell
   mateix el bucle d'eines (*tool-calling*), la composició del *system prompt*,
   l'historial i la persistència.
2. **LLM local.** Els models són `llama.cpp` a la pròpia màquina (deep
   Qwen3-14B-Q4 al port 12322; face Qwen3-1.7B opcional al 12323). Cap crida
   surt de la LAN.
3. **Filosofia diferent.** De "eina de terminal per a un usuari tècnic" a
   **servei domèstic multi-usuari**: cada alumne té el seu perfil, el seu port,
   la seva contrasenya i la seva web, i entra des del mòbil o la tauleta. El
   propietari del sistema (l'administrador) provisiona perfils amb un script;
   l'alumne no veu mai un terminal.

El que **no** ha canviat és el nucli de la idea: el comportament pedagògic viu
en Markdown (`AGENTS.md`, `LEARNING_SYSTEM.md`, skills, agents, comandes). El
codi només transporta, valida i persisteix. Això manté la propietat més valuosa
del disseny original: **canviar com ensenya no requereix tocar codi**.

## A.2 Mapa del repositori

| Directori / fitxer | Rol |
|---|---|
| `server/src/` | El servidor: `index.ts` (arrencada, resolució de perfil/model, *sweeper*), `http.ts` (HTTP, auth, SSE, API, estàtics), `agent.ts` (orquestrador de torn), `llm.ts` (client OpenAI-compatible + bucle d'eines), `tools.ts` (les 3 eines exposades al model), `commands.ts` (càrrega de comandes Markdown), `db.ts` (pont SQLite) |
| `web/` | Frontend propi: `index.html`, `app.js` (~1.100 línies), `style.css`, `marked.min.js`. Xat + botons de pràctica + panell de progrés |
| `hooks/*.py` | Backend de dades (Python stdlib): `read-db.py`, `update-db.py`, `accumulate-session.py`, `persist-session.py`, `validate-data.py`, `session-start/end.py`, `db_lock.py`, `db_schema.py`, `fluent_paths.py` |
| `skills/fluent-*/` | 12 skills en Markdown (8 d'alumne + 4 d'ajuda: SM-2, formatador de feedback, actualitzador de BD, analitzador de sessió) |
| `references/` | Plantilles compartides (exemples SM-2, plantilla de feedback, payload de BD, format del fitxer de sessió) |
| `prompts/agents/` | Definició dels agents: `learner.md` (web, restringit), `tutor.md`, `tutor-fast.md`, i `rules.md` (regles de comportament compartides, font única). Fins al 2026-09-13, `.opencode/agent/` |
| `prompts/commands/` | Les 10 comandes `/fluent-*` en Markdown, amb *frontmatter* (`agent:`) i directives `` !`cmd` `` que precarreguen l'estat de l'alumne |
| `obsolet/opencode-runtime/` | El que era específic d'opencode: el seu plugin, `opencode.json` i el llançador de models gratuïts |
| `scripts/` | Orquestració: `flowed-start.sh`, `flowed-stop.sh`, `flowed-web.sh`, `new-user.sh`, `flowed-friend.sh`, `migrate-db.py`, `reset-session.py`, `models/` (6 llançadors, inclòs `docker-llama.sh`) |
| `config/fluent.json` | Configuració canònica i **única font**: models (port, ctx, mostreig), backend, webs, camins |
| `.env` / `.env.railab` / `.env.rapve` | Configuració viva per màquina (model, port, GPU, ctx, backend, llista de webs) |
| `tests/` | 7 fitxers de test (unittest) sobre els hooks Python, inclòs un *golden test* de SM-2 |
| `.github/workflows/ci.yml` | CI: byte-compile + `unittest discover` a Python 3.10/3.11/3.12 |
| `docs/` | Manual pràctic (`MANUAL.md`), registre de canvis detallat (`CHANGES.md`), anàlisi comparativa, plans de migració (`dual-model/`, `opencode-migration/`), diagnòstics |
| `obsolet/` | Dades i configs antigues, fora de l'execució |

Nota de nomenclatura: `.opencode/` es va renombrar a `prompts/` el 2026-09-13
(veure P1-10). *Actualitzat el 2026-09-14: `.claude/` també s'ha desmarcat — `hooks/`, `skills/` i `references/` són ara directoris normals a l'arrel, i el camí de plugin s'ha retirat a `obsolet/`. El text que segueix descriu per què s'havia mantingut.* `.claude/` es mantenia perquè allà el nom **sí** que era funcional:
és el que Claude Code descobreix per instal·lar Fluent com a plugin. Cada
directori té un `README.md` que ho explica.

## A.3 Arquitectura d'execució

```
  Navegador (mòbil/PC)                    railab
  ────────────────────       ┌───────────────────────────────────────────┐
   web/index.html  ──HTTP──► │ server/src/http.ts                        │
   web/app.js      ◄──SSE─── │  · basic auth (usuari = nom de l'alumne)  │
                             │  · estàtics + /api/* + /api/event         │
                             └──────────────┬────────────────────────────┘
                                            │
                             ┌──────────────▼────────────────────────────┐
                             │ agent.ts — un "torn"                      │
                             │  1. system prompt = AGENTS.md +           │
                             │     LEARNING_SYSTEM.md + <agent>.md +     │
                             │     rules.md                              │
                             │  2. historial reconstruït des de SQLite   │
                             │  3. routing de model (deep / face)        │
                             │  4. runTurn() amb bucle d'eines           │
                             │  5. cada part → SQLite + event SSE        │
                             └───┬──────────────────────┬────────────────┘
                                 │                      │
                 ┌───────────────▼──────┐   ┌───────────▼───────────────┐
                 │ llm.ts               │   │ tools.ts                  │
                 │ POST /v1/chat/...    │   │  · skill (llegeix SKILL.md)│
                 │ deep :12322 (14B)    │   │  · bash (allowlist curta) │
                 │ face :12323 (1.7B)   │   │  · fluent_deep_evaluate   │
                 │ fallback face→deep   │   │    (rúbrica al deep)      │
                 └──────────────────────┘   └───────────────────────────┘
                                 │
                 ┌───────────────▼──────────────────────────────────────┐
                 │ db.ts — SQLite amb esquema compatible opencode.db    │
                 │ ~/.fluent/<id>/sessions/sessions.db                  │
                 └───────────────┬──────────────────────────────────────┘
                                 │  (frontera codi TS ↔ codi Python)
                 ┌───────────────▼──────────────────────────────────────┐
                 │ hooks Python: accumulate-session.py, persist-        │
                 │ session.py, update-db.py, read-db.py                 │
                 │ → 6 JSON + results/*.md + .backups/ a ~/.fluent/<id>/│
                 └──────────────────────────────────────────────────────┘
```

### La frontera: SQLite com a contracte

> **Nom de la BD (2026-09-13).** La ruta era
> `~/.fluent/<id>/.opencode/opencode/opencode.db`, forma heretada del layout XDG
> d'opencode. Ara és **`~/.fluent/<id>/sessions/sessions.db`**. Les dues es
> llegeixen, en aquest ordre, i la vella **no s'esborra mai**: la versió
> anterior de l'app hi continua escrivint sense assabentar-se de res. Un perfil
> nou neix directament amb la ruta nova, i
> `scripts/migrate-sessions-db.py` copia la vella a la nova (amb l'API de
> *backup* d'SQLite, no `cp`: amb WAL una còpia plana pot sortir incompleta).
> Override puntual: `FLOWED_SESSIONS_DB`.

La decisió arquitectònica més important de `fluent_dev2` és que el servidor
propi **reprodueix l'esquema `session`/`message`/`part` d'opencode.db**
(`server/src/db.ts`). Així, en substituir `opencode serve` per codi propi, els
hooks Python de persistència (que llegeixen la transcripció des d'aquella BD)
segueixen funcionant **sense cap canvi**. És el que permet haver canviat el
runtime sense reescriure el backend de dades.

### Capa per capa

- **`http.ts`** — Bun.serve. Estàtics sense auth (la closca), API amb basic auth
  (usuari = nom de pila en minúscules, o `opencode` per compatibilitat;
  contrasenya per perfil a `.web-password`). Timeout desactivat per als POST de
  missatge i per a l'SSE (el *prefill* del deep pot passar desenes de segons
  sense enviar cap byte). Endpoints: `/api/global/health`, `/api/agent`,
  `/api/fluent/setup-state` (auto-onboarding), `/api/fluent/progress` (crida
  `read-db.py --full` i normalitza les 6 BD per al panell),
  `/api/fluent/summary` (resum de sessió des de `session-draft.json`),
  `/api/session[/id][/message|/command]`, `/api/event` (SSE).
- **`agent.ts`** — un torn = persistir el torn d'usuari → crear el missatge
  d'assistent → `runTurn()` → persistir i emetre cada part → emetre
  `session.idle` → disparar la persistència automàtica. Inclou: composició del
  *system prompt* des de fitxers, reconstrucció de l'historial (inclosos
  `tool_calls` i resultats d'eina), *routing* de model per agent, comprovació de
  salut del face amb *fallback* al deep (i un reintent si el face cau a mig
  torn), i la injecció de la nota "Continuing session" quan una comanda
  continua una pràctica ja iniciada (evita que el model torni a saludar).
- **`llm.ts`** — client `/v1/chat/completions` sense dependències, amb bucle:
  demanar → si torna `tool_calls`, executar-les i tornar-les com a
  `role:"tool"` → repetir fins a text pla (màx. 6 voltes). `stream:false`.
- **`tools.ts`** — tres eines: `skill` (carrega un `SKILL.md`, només `fluent-*`),
  `bash` (5 patrons permesos: `read-db.py`, `update-db.py`,
  `list-profiles.py`, llegir i esborrar `.flowed-active`),
  `fluent_deep_evaluate` (delega l'avaluació d'una resposta lliure al deep amb
  una rúbrica pròpia i context net, amb `enable_thinking:false`). Inclou
  guàrdies contra bucles: rebuig de respostes-placeholder, una sola avaluació
  real per torn, i desactivació de l'eina per sessió després de 3 rebutjos.
- **`commands.ts`** — llegeix `prompts/commands/<cmd>.md`, separa el
  *frontmatter* YAML, i **resol les directives** `` !`cmd` `` executant-les i
  substituint la línia pel seu stdout. És així com cada comanda arriba al model
  amb l'estat de l'alumne ja precarregat (`read-db.py`), sense que el model hagi
  de descobrir res.
- **`db.ts`** — SQLite via `bun:sqlite`, WAL, esquema idempotent, migració
  `last_activity`, IDs tipus `ses_`/`msg_`/`part_`, i les consultes que el
  *sweeper* i la UI necessiten (`getStaleSessions`, `findLatestBySlug`,
  `getMessageView`).

## A.4 Models, orquestració i Docker

### Rols de model

| Rol | Port | Model actual | Ús |
|---|---|---|---|
| `deep` | 12322 | Qwen3-14B-Q4_K_M (ctx 32768) | tutor, xat, sessions, rúbrica d'avaluació |
| `face` | 12323 | Qwen3-1.7B-UD-Q4_K_XL | torns curts estructurats (vocab, review, progress, setup) — **desactivat** ara mateix; el deep el cobreix via *fallback* |

El *routing* és per agent: `tutor` i `learner` → deep; `tutor-fast` → face amb
caiguda automàtica al deep. Les comandes trien agent al seu *frontmatter*
(`fluent-vocab`, `fluent-review`, `fluent-progress`, `fluent-setup` →
`tutor-fast`; la resta → `tutor`).

### Configuració per màquina (`.env`)

Un sol esquema parametritzable serveix per a railab (4090 + 3090, backend
`native`) i per a la màquina rapve (4060 Ti, backend `docker`):
`cp .env.railab .env` o `cp .env.rapve .env`. Variables: model/port/GPU/ctx del
deep, `FLOWED_DEEP_BACKEND` (`native|docker`), `FLOWED_DEEP_MANAGED` (si Fluent
ha de llançar el model o només comprovar-lo), face on/off, i
`FLOWED_WEBS="alex-en:4100 sam-en:4101 demo-en:4102"` (perfil:port). L'entorn i
la CLI manen sempre sobre el fitxer.

### Docker (només el model)

`scripts/models/docker-llama.sh` puja `ghcr.io/ggml-org/llama.cpp:server-cuda`
amb `--gpus all`, els models muntats en només-lectura, `-c 32768 -ngl 99 -fa 1
--parallel 1 -b 4096 -ub 1024 --jinja --reasoning off`, publica el port del
contenidor 8080 al port host del rol, i espera `/health` fins a 120 s. Llegeix
la mateixa font de veritat (`FLOWED_DEEP_*` de l'`.env`).

Peces fines d'aquesta part, que val la pena no perdre:

- **Swap 1:1 de port.** Si el port del deep ja està ocupat per un model
  "d'ús general", `flowed-start.sh` l'atura via `FLOWED_DEFAULT_MANAGER`
  (interfície `start|stop|status`), puja el de Fluent, i `flowed-stop.sh`
  restaura el default. Mai roba ports sense manager declarat.
- **Estat, no heurística.** `/tmp/fluent-deep-docker.state` distingeix "el
  contenidor sa d'aquest port és el nostre" de "és d'un altre" — un `/health`
  correcte no ho pot distingir.
- **Resolució per port publicat.** Docker mostra el port del *contenidor*, no el
  del host; per això el titular d'un port es resol amb `docker ps --format`
  filtrant `:port->`, i els PID d'aquests contenidors s'exclouen de la guàrdia
  de GPU (si no, el propi model semblaria un procés aliè).
- **Guàrdia de GPU.** Abans d'engegar res, llista els processos de còmput a la
  GPU i distingeix nostres / contenidors candidats / aliens; amb aliens
  pregunta (o avorta amb `--yes`, o continua amb `--force`).
- **Neteja d'orfes i pidfiles rancis** a tots els `--stop`, i espera activa
  perquè el port quedi lliure abans del relleu.

### Exposició i multi-usuari

`scripts/flowed-web.sh --app <perfil> --port N` llança una instància del
servidor propi per alumne (`nohup` + pidfile a `/tmp/fluent-web-N.pid`), amb:

- `FLOWED_DATA_DIR=~/.fluent/<id>` → aïllament total de dades,
- el servidor obre `~/.fluent/<id>/sessions/sessions.db` (i llegeix la ruta
  antiga si el perfil encara no s'ha migrat),
- contrasenya estable per perfil (`.web-password`, mode 600) o generada,
- sanejament d'entorn (`env -u OPENCODE_CLIENT -u XDG_STATE_HOME FLOWED_DEV=0`)
  perquè una instància llançada des d'un shell de l'app d'escriptori no acabi en
  mode dev sense el prompt del tutor,
- *preflight* (bun, python3, openssl, port lliure) per fallar en 1 s amb causa
  clara en lloc d'un timeout de 20 s,
- espera de `/api/global/health` i neteja del procés si no arrenca.

`--web` manté el camí alternatiu (UI oficial d'opencode) i `--stop` atura.
`scripts/new-user.sh <id>` provisiona un perfil nou: valida l'id, es nega a
sobreescriure, sembra les 6 BD des de `data-examples/`, marca
`preferences.setup_complete=false` (la web arrencarà `/fluent-setup` sola) i
genera la contrasenya. Provisió determinista per script, sense web d'admin.

## A.5 Dades i persistència

### Què hi ha a `~/.fluent/<id>/`

Les 6 BD JSON (`learner-profile`, `progress-db`, `mistakes-db`, `mastery-db`,
`spaced-repetition`, `session-log`), `results/*.md` (una fitxa per sessió),
`.backups/` (diaris, pre-update i pre-migració), `session-draft.json` (estat de
l'acumulador), `.records/<ses>.jsonl` (registres estructurats), `.metrics/turns.jsonl`,
`.web-password`, i `sessions/sessions.db` (sessions i missatges; als perfils
antics, `.opencode/opencode/opencode.db`).

### Les dues capes

**Capa A — incremental, automàtica, sense pausa visible.** A cada
`session.idle`, `accumulate-session.py` escaneja l'opencode.db del perfil
buscant *feedback ja qualificat* nou (marca d'aigua per `rowid`), n'extreu els
exercicis i els patrons d'error parsejant el format de feedback
(`**Score: X/10**`), els acumula a `session-draft.json` i crida `update-db.py`
amb el payload **complet acumulat**. Com que `update-db.py` és idempotent per
`session_id` (desa una instantània T0 la primera vegada i la restaura abans de
reaplicar), repetir-ho amb un payload que creix no compta doble. També
reescriu la fitxa de resultats, de manera que tancar el navegador no perd res.

**Capa B — final, enriquida.** La dispara el **servidor**, no el tutor: amb
`/fluent-end` (`agent.runDbUpdater`) o quan el *sweeper* detecta 30 min
d'inactivitat. `persist-session.py` re-parseja la transcripció
**sencera** (no només el tros nou) i hi afegeix la durada real de la sessió.
Mateix `session_id` → *upsert*, no duplicació; el marcador
`session.metadata.capa_b_done` evita repetir-la.

Atenció a què **no** fa, malgrat el que deia la documentació anterior: no
afegeix vocabulari nou amb tots els camps, ni qualitats SM-2, ni fites, ni focus
de la propera sessió. Aquests camps només els pot omplir qui sap què ha passat
—el tutor— i en el runtime del servidor ningú els omple (veure la troballa
sobre SM-2 més avall). La Capa B, avui, és "re-parseig complet + durada".

### Altres garanties

- **SM-2 en Python, no al prompt.** `update-db.py:calculate_sm2()` és la font
  única de la matemàtica (interval, factor de facilitat, ratxes, nivell de
  mestria), amb *golden test* a `tests/test_sm2_golden.py`. El model només
  aporta la qualitat 0–5 de cada resposta.
- **Versionat d'esquema.** `db_schema.py` (`_schema_version`, migracions
  registrables, detecció d'esquema futur) + `scripts/migrate-db.py` (informe,
  backup pre-migració a `.backups/`, idempotent). Ara mateix
  `CURRENT_SCHEMA_VERSION = 1` i cap migració registrada: la infraestructura
  existeix abans de necessitar-la.
- **Bloqueig i validació.** `db_lock.py` per a escriptures concurrents,
  `validate-data.py` (hook PostToolUse) valida JSON i fa còpia amb marca de
  temps a cada edició.
- **Resolució de directori de dades** amb precedència clara i pura
  (`fluent_paths.py`): `$FLOWED_DATA_DIR` → `$CLAUDE_PROJECT_DIR/data` →
  `./data` → `~/.claude/fluent-data`, i només si hi ha `learner-profile.json`.

## A.6 La web

Una sola pàgina, sense *framework*: capçalera amb els 7 modes de pràctica com a
botons (writing, speaking, vocabulary, reading, review, "surprise me", progress),
xat, i un compositor pensat per a mòbil. Detalls que hi són per experiència
acumulada: xips d'eina amb etiquetes humanes ("avaluant resposta" amb comptador)
i eines internes amagades, mode debug (`?debug=1` o triple clic),
*deduplicació* de la bombolla optimista contra l'esdeveniment SSE, marcatge del
flux per decidir si el botó buit significa "següent exercici", *placeholders*
contextuals per mode, salt a l'últim missatge, i un **panell de progrés** modal
que pinta les 6 BD normalitzades (ratxa, mestria per habilitat amb estrelles,
tendència de precisió, patrons febles, sessions recents, fites, assoliments).

## A.7 Comportament del tutor: on viu i com es controla

- `AGENTS.md` — protocol de sessió, format de feedback, mapatge nota→qualitat
  SM-2, tipus d'exercici, regles crítiques, gamificació.
- `LEARNING_SYSTEM.md` — metodologia (recall actiu, dificultat desitjable 60–70%,
  interleaving, i+1).
- `prompts/agents/rules.md` — **font única** de les regles dures que han de
  valer a tots els torns, concatenada pel servidor a *tots* els agents. Des del
  2026-09-13 ho és de debò: les còpies literals que arrossegaven `learner.md`,
  `tutor.md`, `tutor-fast.md`, `fluent-learn` i `fluent-vocab` s'han substituït
  per una línia de referència. Les regles són:
  identitat de llengua estricta (el català no és castellà), prohibició de
  repetir res de la sessió o de les últimes 24 h, alternança de direcció al
  vocabulari, prompts de producció no circulars, no tornar a saludar, i el mode
  *friend*.
- `learner.md` — l'agent de la web, amb permisos tancats: `bash` denegat excepte
  5 patrons, escriptura només dins `~/.fluent/**`, només skills `fluent-*`, ni
  web ni *fetch* ni tasques; i instruccions explícites de no investigar el
  sistema (cada rebuig de permís infla el context i pot matar la sessió).
- **Mode friend** (`scripts/flowed-friend.sh <id> on|off|status`): flag
  `preferences.tutor_style` + `interests[]` + `about`. El tutor cita l'última
  sessió i usa els interessos als exemples. `off` deixa el perfil byte-idèntic
  a l'original. Cost ~250 tokens/torn, 0 VRAM. Lliçó documentada: els blocs
  condicionals al **final** de la plantilla s'apliquen; al principi, s'ignoren.

## A.8 Com es distribueix i s'exporta

Tres camins coexisteixen, i això és una virtut del disseny:

1. **Plugin de Claude Code** — `.claude-plugin/{plugin,marketplace}.json` +
   `hooks.json`: `claude plugin install fluent@m98`. Dades a
   `~/.claude/fluent-data/`.
2. **Clone amb opencode** — ARXIVAT el 2026-09-13: el que en quedava és a
   `obsolet/opencode-runtime/`. Restaurar-ho vol dir desfer el renombrat de
   `prompts/`.
3. **Servei standalone** (el camí principal avui) — `flowed-start.sh` puja
   models i una web per alumne; l'alumne només veu una URL i un login.

Per portar el codi a una altra màquina hi ha procediment documentat
(`MANUAL.md` §1.9) i plantilles `.env` per màquina; les dades dels alumnes es
mouen copiant el directori del perfil (`MANUAL.md` §4), i el versionat
d'esquema és el que ha de protegir aquestes còpies a futur.

---

# B. Característiques afegides respecte el Fluent original

| Àmbit | Fluent upstream | fluent_dev2 |
|---|---|---|
| Runtime | Claude Code (o opencode) com a agent | **Servidor propi** Bun/TS: bucle d'eines, prompts, historial, SSE |
| Model | Claude (núvol) | **LLM local** llama.cpp, arquitectura **dual deep/face** amb *fallback* automàtic |
| Avaluació | El mateix model del xat | Eina **`fluent_deep_evaluate`** amb rúbrica i context net + guàrdies anti-bucle |
| Interfície | Terminal | **Web pròpia** mòbil-first, botons de pràctica, panell de progrés, SSE |
| Multi-usuari | Un directori de dades | **Un perfil, un port, una contrasenya, una instància** per alumne (`FLOWED_WEBS`) |
| Provisió | `/fluent-setup` manual | `new-user.sh` + auto-arrencada de `/fluent-setup` (`setup_complete`) |
| Persistència | El tutor havia de cridar-la al final | **Dues capes**: acumulació automàtica a cada `idle` + finalització (comanda o *sweeper* de 30 min), idempotent per `session_id` amb instantània T0 |
| Sessions | — | **Pont SQLite** amb esquema compatible opencode.db (frontera estable TS↔Python) |
| SM-2 | Descrit al prompt | **Implementat en Python** amb *golden test*; el model només dóna la qualitat |
| Esquema de dades | Sense versió | `_schema_version`, migracions registrables, `migrate-db.py` amb backup |
| Orquestració | — | `.env` per màquina, `fluent-start/stop`, 6 llançadors de model, **backend Docker**, swap de port amb manager extern, guàrdia de GPU, neteja d'orfes |
| Qualitat | Tests manuals | 7 fitxers de test + **CI** (3 versions de Python) |
| Personalització | — | **Mode friend** opt-in per alumne, reversible sense tocar codi |
| Regles de comportament | Copiades a cada fitxer | `rules.md` com a **font única** concatenada a tots els agents |
| Documentació | README | `MANUAL.md` pràctic, `docs/CHANGES.md` canvi a canvi amb decisions i verificació, plans de migració, diagnòstics |

**Valoració.** L'estructura és sòlida i, sobretot, *honesta*: les decisions
difícils (swap de ports, idempotència, fallback, sanejament d'entorn) estan
resoltes i documentades amb el perquè. La separació prompt/codi es manté, la
frontera SQLite va permetre canviar de runtime sense reescriure el backend, i
l'aïllament per alumne és real (dades, BD de sessions, contrasenya, procés).

---

# C. Deute tècnic i propostes de millora

Ordenat per **impacte/cost**. P0 = errors reals o hardcodes que ja limiten el
multi-usuari; P1 = arquitectura; P2 = producte.

## C.1 P0 — correccions ✅ APLICADES (2026-09-13)

Totes verificades: `tsc --noEmit` net, `unittest discover` 62/62, i una prova
amb una BD de sessions sintètica amb dues sessions del mateix alumne.

**1. El context d'eina no arribava a les eines. — FET**
`tools.ts` declarava `execute(args, ctx?)` i feia servir `ctx?.sessionID` /
`ctx?.messageID` per als guàrdies anti-bucle, però `llm.ts` cridava
`tool.execute(args)` sense segon argument: tots els comptadors vivien sota la
clau `"unknown"` i per tant eren **globals a tot el servidor** (un rebuig en una
sessió podia desactivar `fluent_deep_evaluate` en una altra, i el límit "una
avaluació per torn" valia per a tot el procés).
*Fet:* `ToolContext` passa a ser definició única a `llm.ts` (amb `dataDir`
opcional), `ToolDefinition.execute` i `runTurn()` l'accepten, `agent.ts` el passa
als dos punts de crida (torn normal i reintent amb deep). `tools.ts` la
reexporta per compatibilitat.

**2. Hardcodes del perfil `nes` al servidor. — FET**
Aquest era el punt greu, i amagava dos errors més:
- `index.ts` (*sweeper*) filtrava les fitxes de resultats per
  `"nes-fluent-learn-"`: per a qualsevol altre alumne no trobava res.
- `index.ts` comparava `draft.session_id === s.id`, però el draft guarda l'id
  **lògic** (`session-003`) i `s.id` és l'id **SQLite** (`ses_ab12…`): mai
  podien ser iguals, així que el marcador `capa_b_done` no servia de res i
  l'única protecció contra repetir la Capa B era l'heurística de les fitxes.
- Aquella heurística mirava **qualsevol** fitxa del directori: un cop una sessió
  quedava enriquida, bloquejava la Capa B de totes les sessions futures.
- `http.ts` (`/api/fluent/summary`) feia `findLatestBySlug("nes")` i retornava
  `streak = sessions ? 1 : 0`, obrint a més un `FluentDB` per petició que no es
  tancava mai.
*Fet:* el *sweeper* filtra per `${loginName}-` i per l'id lògic del draft;
s'escriu `draft.capa_b_sid` amb l'id SQLite (i es compara contra ell, amb
compatibilitat cap enrere); `/api/fluent/summary` llegeix la ratxa de
`learner-profile.json` i ja no obre cap BD. Cap `"nes"` a `server/src/`.

**3. El servidor sabia l'id de sessió i el llençava. — FET**
`agent.runAutoPersistence(_sessionId)` ignorava el paràmetre i
`accumulate-session.py` havia d'endevinar la sessió amb
`LIKE '%"slug"%'` sobre qualsevol text.
*Fet:* `accumulate-session.py` accepta `--session-id` (amb el camí antic com a
*fallback* documentat) i el servidor l'hi passa sempre. Verificat: amb dues
sessions del mateix alumne a la BD, cada id acumula només els seus exercicis, i
un id inexistent surt net amb codi 0 sense tocar res.

**4. Codi mort. — FET**
Eliminats els dos bucles `for … pass` residuals d'`accumulate-session.py`.

**Correcció d'una afirmació del document anterior:** `js-yaml@5.4.1` **no** és
sospitós — ve del repositori oficial `nodeca/js-yaml` i és una versió posterior
al meu tall de coneixement. No cal tocar-la. (Es pot eliminar igualment la
dependència si es vol un servidor sense dependències: el *frontmatter* són 2–3
claus planes.)

**5. El barrido podia repetir la Capa B en bucle. — FET (2026-09-13, tarda)**
Efecte lateral de l'arreglo del punt 2, i val la pena deixar-lo escrit. La
heurística original mirava *qualsevol* fitxa de resultats enriquida: era
incorrecta, però tenia un efecte secundari útil — un cop hi havia una sessió
enriquida, el *sweeper* no tornava a executar res mai. En acotar-la (com tocava)
a la sessió del draft, el fre desapareixia: `getStaleSessions` retorna **totes**
les sessions `learner` inactives, sense límit d'antiguitat, i el marcador
`capa_b_done` viu a `session-draft.json`, que només guarda UNA sessió. Amb 5
sessions velles a la BD, el servidor hauria llançat 5 `persist-session.py` **cada
minut**.
*Fet:* el marcador passa a la pròpia fila de sessió
(`session.metadata.capa_b_done`, via `db.markFinalized()`, escrit tant pel
*sweeper* com per `/fluent-end`), i `getStaleSessions` filtra per aquest camp i
per una finestra de 24 h. Verificat amb una taula sintètica: de quatre sessions
(activa, rància, ja finalitzada, de fa 40 h) només en surt la rància, i
desapareix en marcar-la.

**6. La Capa B esborrava el que la Capa A havia desat. — FET (2026-09-13), VERIFICAT**
El més seriós de tot el que ha sortit, i estava actiu al camí normal: tancar la
sessió (o deixar passar 30 min) destruïa dades.

`update-db.py` només llegeix `session["errors"]`; `persist-session.build_report`
emetia la llista amb la clau `"error_patterns"` i cap `"errors"`. Com que
`update-db.py` és idempotent per `session_id` — restaura la instantània T0 i
reaplica el payload —, reaplicar sense errors **elimina** els patrons que la
Capa A havia escrit per aquella sessió, i amb ells els ítems de repetició
espaiada que se'n derivaven.

Provat amb un perfil sintètic (una resposta qualificada amb una correcció
`(tenses — …)`):

| Moment | `mistakes-db.error_patterns` | `spaced-repetition.items` |
|---|---|---|
| després de Capa A | `example_pattern_1`, **`tenses_go`** | `example_item_id`, **`tenses_go`** |
| després de Capa B (abans) | `example_pattern_1` | `example_item_id` |
| després de Capa B (ara) | `example_pattern_1`, **`tenses_go`** | `example_item_id`, **`tenses_go`** |

*Fet:* `build_report` emet `errors` (amb el mateix mapatge que
`accumulate-session.merge_errors_into_payload`) i manté `error_patterns` per a
la taula del fitxer de resultats. A més, `learner_slug` cau al nom del perfil
quan no es pot llegir de la transcripció — si no, el fitxer de resultats
s'escrivia literalment com a `None-fluent-learn-session-001.md`, un segon fitxer
que a sobre el filtre del *sweeper* no reconeix. Test de regressió:
`tests/test_capa_a_b.py`.

### Trobat de nou durant l'arreglo (pendent de decidir)

**La repetició espaiada no avançava mai. ✅ RESOLT (opció 1) — VERIFICAT**
`update_spaced_repetition` només actualitza interval, factor de facilitat,
repeticions i mestria d'un ítem a partir de `review_results[]`. El bloc
d'`errors[]` únicament **crea** ítems nous (interval 1, EF 2.5, `due_date`
demà); si l'ítem ja existeix, no el toca. I `review_results[]` està buit sempre:
ni `accumulate-session.py` (no pot saber de la prosa quin ítem de la cua
s'estava repassant) ni `persist-session.py` (l'emet buit) l'omplen.

Conseqüència: els ítems entren a la cua i no en surten mai — no graduen, no
s'allarga l'interval, la mestria no puja per haver-los encertat. Es pot
comprovar en un perfil real mirant si tots els ítems tenen `repetitions: 0` i
`interval_days: 1`:

```bash
python3 -c "import json;d=json.load(open('/home/albert/.fluent/<perfil>/spaced-repetition.json'));\
items=d.get('items',{});print(len(items),'items;',sum(1 for i in items.values() if i.get('repetitions',0)==0),'amb repetitions=0')"
```

**Confirmat en producció (2026-09-13):** dos perfils reals donen 15/15 i 12/12
ítems amb `repetitions = 0`. No és un risc teòric: cap ítem ha graduat mai des
que el sistema funciona amb el servidor propi.

Símptoma observable a la pràctica: com que tots els ítems queden vençuts cada
dia, la cua de `/fluent-review` no baixa mai, i el tutor es troba entre dues
ordres contradictòries — repassar la cua i no repetir res de les últimes 24 h.
Probablement acaba inventant exercicis nous en lloc de fer servir la cua.

És el mateix problema de fons que P1-5: la informació existeix al cap del tutor
(«això era l'ítem X i l'ha encertat amb qualitat 4») i es perdia en convertir-la
en prosa. La solució no és un altre parser sobre prosa: és que el tutor ho
**declari**.

*Fet (opció 1, bloc estructurat):* al final d'una sessió de repàs o de
vocabulari el tutor envia, com a última cosa, un bloc tancat:

````markdown
```fluent:review_results
[{"item_id": "<id copiat de la cua>", "quality": 4}]
```
````

- **Parser:** `parse_review_results()` a `persist-session.py` (font única; el
  llegeix tant la Capa A com la Capa B, perquè si la B no el llegís tornaria a
  esborrar el que la A hagués aplicat). Liberal en l'entrada (`id` per
  `item_id`, `score` 0-10 en lloc de `quality` 0-5), estricte en la sortida
  (qualitat retallada a 0-5, un registre per ítem).
- **Validació:** `known_review_results()` descarta els `item_id` que no siguin a
  la cua del perfil i ho diu al log — els models n'inventen.
- **Moment de lectura:** es parseja de la transcripció **sencera** a cada torn,
  no només dels fragments nous. El bloc arriba al missatge de tancament, que
  normalment no porta cap nota nova; amb la porta antiga ("només si hi ha
  feedback graduat nou") no s'hauria aplicat mai.
- **Idempotència:** el draft el guarda sencer i es reemplaça, mai s'acumula;
  com que `update-db.py` restaura T0 i reaplica, SM-2 es calcula una sola vegada
  per molt que s'executi.
- **UI:** `stripMachineBlocks()` a `web/app.js` el treu abans de renderitzar;
  l'alumne no el veu mai.
- **Prompts:** pas nou als skills `fluent-review` i `fluent-vocab`, una línia a
  les comandes corresponents i un punt a `AGENTS.md`.

Provat d'extrem a extrem (`tests/test_capa_a_b.py`): l'ítem passa de
`repetitions 0` a `repetitions 1` amb `last_quality 4`; re-executar la Capa A no
el compta dues vegades; la Capa B no el desfà; i un `item_id` inventat no entra
a la cua.

**El que això NO arregla:** els ítems només avancen si el tutor envia el bloc.
Si un dia no l'envia, aquella sessió no compta — sense error visible. És el
límit de qualsevol contracte basat en que el model escrigui alguna cosa, i és
exactament l'argument de P1-5.


**L'id lògic de sessió es recupera amb un regex.**
`parse_session_id_from_context` busca `"next_session_id": "session-NNN"` dins els
5 primers fragments de la transcripció — és a dir, dins el bloc d'estat que la
comanda precarrega. Si una sessió comencés sense comanda, o si la directiva de
precàrrega fallés, tot s'arxivaria per sempre sota `session-001`. Avui el risc és
baix (la web sempre obre amb `/fluent-setup` o `/fluent-learn`: `app.js`
`initialCommand()`), però la solució neta és que el servidor assigni l'id lògic
en crear la sessió i el desi (a `session.metadata` o al draft) en lloc de
re-deduir-lo. Encaixa amb la millora P1-5.

## C.2 P1 — arquitectura (cost mitjà, impacte alt)

**5. Substituir el parser de notes per una crida d'eina estructurada. ✅ FET (2026-09-13)**
Avui la Capa A depèn d'un `re` que busca `**Score: X/10**` dins la prosa del
tutor: el format del prompt i el parser són **dues fonts de veritat acoblades**,
i qualsevol deriva del model (una nota escrita d'una altra manera, un canvi
d'idioma, una taula) es tradueix en pèrdua silenciosa de dades.
*Fet:* eina `fluent_record_answer(skill, exercise, learner_answer, score,
corrections[], item_id?, sm2_quality?)` a `server/src/tools.ts`. Valida **en
escriure**: nota 0-10, cada correcció amb `wrong`/`right` i una categoria de la
llista canònica (que ara viu en un sol array TS sincronitzat amb
`db_schema.py`), i `item_id` comprovat contra la cua real del perfil. Si alguna
cosa no quadra retorna `REJECTED: …` dient exactament què, i el model ho corregeix
al mateix torn — abans això es descobria setmanes després mirant `mistakes-db`.

Els registres s'escriuen a `<perfil>/.records/<ses_id>.jsonl` (append-only, un
per resposta) i el costat Python els tracta com a **autoritat**: 
`read_records()` + `records_to_payload()` a `persist-session.py`, usats per les
dues capes. Els parsers de prosa queden com a **xarxa de seguretat** per a les
respostes que el tutor narri sense registrar: la fusió descarta duplicats per
text de la resposta (exercicis) i per `pattern_id` (errors), i avisa per stderr
quan el nombre de registres i el de notes en prosa no coincideix — la doble
escriptura amb avís de divergència que estava proposada.

Prompts: `AGENTS.md` (un pas nou al protocol de torn) i
`fluent-feedback-formatter` (la crida, amb la forma exacta). El bloc
`fluent:review_results` es manté com a reserva quan no hi ha registres.

Provat: `tests/test_capa_a_b.py::StructuredRecordsTest` — no es compta dues
vegades el que està registrat i narrat alhora, la categoria declarada arriba
intacta a `mistakes-db`, un registre amb `item_id` fa avançar SM-2 i la Capa B no
el desfà, i una resposta narrada sense registrar no es perd.

**6. *Streaming* de tokens. ✅ FET darrere flag (2026-09-13) — falta provar-lo en viu**
`llm.ts` anava amb `stream:false`: l'alumne no veia res fins que el torn acabava.

*Fet:* `chatStreaming()` a `llm.ts` llegeix l'SSE de llama.cpp i el reconstrueix
en la mateixa forma que una resposta normal, de manera que el bucle d'eines de
`runTurn` no canvia gens. La part fràgil no és el text sinó els `tool_calls`, que
arriben **fragmentats** (el nom en un tros, els arguments repartits en diversos,
adreçats per `index`); si es recomponen malament, l'eina es crida amb JSON trencat
i el torn mor. Per això l'acumulador (`newStreamAccumulator` / `applyStreamChunk`
/ `finishStream`) és pur i té proves pròpies.

A `agent.ts`, el primer *delta* crea una part de text buida i la resta surten com
a events `message.part.delta` — **la forma que `web/app.js` ja sabia llegir**, o
sigui que no ha calgut tocar el frontend. La part es desa un sol cop, quan el
segment es tanca (`flushStream`), també si pel mig hi ha una crida d'eina o un
error: així la transcripció del disc coincideix amb el que l'alumne ha vist,
sense una escriptura a SQLite per token.

**Està desactivat per defecte**: `FLOWED_STREAM=1` (o `server.stream` a
`config/fluent.json`). No l'he pogut executar contra un model real des d'aquí —
en aquesta màquina no hi ha ni bun ni GPU — així que la primera prova amb
`test-en` és obligatòria abans d'activar-lo per a ningú més.

*Matís:* amb `--parallel 1` el *streaming* no fa res més ràpid, només fa que es
vegi abans; el *prefill* segueix mut. El comptador "pensant… N s" que ja hi ha
és el que cobreix aquella espera.

**7. Gestió del context. ✅ (a) i (c) FETS · ⏳ la poda, pendent de dades**
L'historial es reenvia sencer cada torn i el *system prompt* són ~30 KB de
fitxers concatenats; amb ctx 32768 les sessions llargues desborden (la regla
"no reintentis, persisteix i surt" d'`AGENTS.md` és, de fet, un pegat a això).

*Fet — mesurar (era (c)):* `runTurn` rebia `usage` de llama.cpp i el llençava.
Ara acumula `TurnMetrics` per torn (tokens de prompt i de sortida, *roundtrips*,
crides d'eina, temps dins del model) i `agent.ts` deixa una línia al log i una
línia JSON a `<perfil>/.metrics/turns.jsonl`. Amb un model local, context i temps
són els recursos escassos i fins ara no es mesurava cap dels dos.

*Fet — deixar de reinjectar l'estat:* la segona i tercera comanda d'una mateixa
sessió tornaven a executar la directiva `` !`read-db.py` `` i a encastar el bloc
d'estat sencer. `loadCommand` accepta ara `skipDirectives`, i `agent.runCommand`
l'activa quan la sessió ja té torns del tutor, substituint el bloc per una línia
("ja el tens més amunt, no el tornis a carregar"). Són ~3,2 KB per comanda amb un
perfil buit, i bastant més amb una cua real.

*Pendent — la poda per finestra, i per què no l'he feta:* **xoca amb la regla de
no repetir**, que diu literalment al tutor que es rellegeixi la sessió sencera
per no repetir cap paraula ni escenari. Podar l'historial degrada preciionaent la
regla que més ha costat fer complir. La sortida és que el resum no sigui prosa
sinó **la llista exacta d'ítems ja presentats, generada dels registres de P1-5** —
que ara existeixen. És a dir: la poda és segura *perquè* hem fet el 5 abans, i
val la pena fer-la quan `.metrics/turns.jsonl` digui on és el problema de debò.

**8. Supervisió de processos.** Ara mateix tot va amb `nohup` + pidfiles a
`/tmp`: no hi ha reinici automàtic si una instància cau, ni arrencada a l'inici
del sistema. Amb un servei domèstic per a tercers (la família), això és el punt
feble operatiu més gran.
*Proposta:* unitats `systemd --user`: `fluent-model@.service` (deep/face) i
`fluent-web@<perfil>.service` amb `Restart=on-failure`, `WantedBy=default.target`
i `EnvironmentFile=.env`. `fluent-start/stop` passen a ser embolcalls prims sobre
`systemctl --user`. Alternativa equivalent: `docker-compose` per a tot l'stack
(model + N webs), que a més faria l'exportació a una altra màquina trivial.

**9. Unificar la configuració. ✅ FET (2026-09-13)**
Hi havia `opencode.json` (ja no s'usa en runtime),
`config/fluent-models.json`, `.env` (+2 plantilles) i defaults dins el codi, amb
un ordre de precedència de 5 capes a `index.ts:loadModels`.
*Fet:* `config/fluent.json` és la configuració canònica del projecte (models,
ports, GPU, ctx, backend, llista de webs, camins). Tres capes amb precedència
declarada i provada: **config/fluent.json < `.env` < entorn/CLI**.
`scripts/flowed-config.py` la resol i l'emet com a JSON (`--json`) o com a
exports de shell (`--sh --missing-only`), que és com la consumeixen
`flowed-start.sh`, `flowed-stop.sh` i `docker-llama.sh` *després* del seu propi
bucle d'`.env` — així el projecte arrenca sense `.env` i, si n'hi ha, mana ell.
El servidor llegeix la mateixa secció `models` com a capa de sota
(`server/src/index.ts`). *(Aquí es va deixar `config/fluent-models.json` com a
capa d'override heretada; el 2026-09-20 es va retirar: repetia `fluent.json`
valor per valor però hi guanyava, i una temperatura editada a `fluent.json` no
arribava mai al servidor. Ara només `FLOWED_MODELS_FILE`, explícit, hi pot anar
al damunt.)* De passada: el servidor ignorava `max_tokens` dels fitxers
de config (només llegia `maxTokens`); ara accepta les dues formes.

Verificat amb els tres camins: amb `.env` el pla surt idèntic al d'abans; sense
`.env` però amb `config/fluent.json` també; sense cap dels dos, error clar.
Tests: `tests/test_fluent_config.py` (precedència de les tres capes + el fitxer
del repo és vàlid i complet).

**10. Fer coincidir els noms amb la realitat. ✅ FET (2026-09-13, tarda)**
`.opencode/` contenia els agents, les comandes i el plugin d'opencode, i el nom
deia una cosa que ja no era certa: qui els llegeix és el servidor propi.

*Fet, amb el vistiplau explícit de retirar el camí opencode:*

| Abans | Ara |
|---|---|
| `.opencode/agent/` | `prompts/agents/` |
| `.opencode/commands/` | `prompts/commands/` |
| `.opencode/helpers/list-profiles.py` | `scripts/list-profiles.py` |
| `.opencode/plugins/`, `opencode.json`, `fluent-opencode-free.sh` | `obsolet/opencode-runtime/` |

Actualitzat tot el que hi apuntava: `agent.ts`, `commands.ts`, l'allowlist de
`bash` a `tools.ts`, `learner.md`, `fluent-use.md`, els dos skills que remeten a
`rules.md`, i els documents. El mode `--web` de `flowed-web.sh` (la UI
d'opencode) ara falla amb un missatge explicant on ha anat, en lloc d'arrencar
una cosa trencada. Nou `prompts/README.md` amb el contingut i la història del
nom. El camp `model:` del *frontmatter* dels agents (que només llegia opencode i
el servidor ignora) porta ara una nota dient-ho, perquè ningú hi perdi una hora.

**`.claude/` NO es toca**, i el seu README diu per què: `plugin.json` apunta a
`./skills/` i `./hooks/hooks.json`, i `hooks.json` crida
`${CLAUDE_PLUGIN_ROOT}/hooks/*.py`. Allà el nom és funcional.

**Una distinció que el renombrat NO toca:** `.opencode` també apareix com a ruta
de **dades** — `~/.fluent/<id>/.opencode/opencode/opencode.db` és on viuen les
sessions de cada alumne (`XDG_DATA_HOME`). Es queda tal com està: moure-ho seria
tocar les dades vives de tres perfils per estètica.
`tests/test_repo_layout.py` distingeix els dos casos i falla si torna a
aparèixer una ruta de codi cap a `.opencode/`.

*Residu conegut:* `docs/CHANGES.md`, `docs/opencode-migration/` i altres
documents històrics segueixen parlant de `.opencode/`. Són registre del que va
passar; no s'han reescrit a propòsit.

**11. Tests del servidor. ⏳ començat (2026-09-13)**
El TypeScript (que ara és el runtime) no tenia cap test, i sense `bun` en aquesta
màquina no es podien escriure de la manera òbvia. Primera peça:
`server/test/stream-parser.test.ts`, que `node --experimental-strip-types`
executa directament i que `tests/test_server_stream.py` llança dins de la suite
normal (es salta sola si el `node` no ho suporta). Cobreix l'acumulador de
*streaming*: text, `tool_calls` fragmentats, dues crides barrejades per `index`,
soroll, `usage` i flux buit. La resta del servidor segueix sense proves.
*Proposta:* `bun test` amb: `commands.expandDirectives` (directives, stderr,
frontmatter), `llm.runTurn` contra un servidor OpenAI fals (text, tool_calls,
error HTTP, timeout), `tools` (allowlist de bash, validació del nom de skill,
guàrdies del deep), `http` (auth, 401, 404, *path traversal*), i un e2e d'un torn
amb model fals que acabi verificant les files a SQLite. Afegir-ho al CI.

## C.3 P2 — producte i robustesa (cost variable)

**12. Decaïment de mestria. ✅ FET (2026-09-13) · vocabulari estructurat ⏳**

El problema: la mestria només pujava. Un alumne que no escrivia una línia des de
feia dos mesos continuava sent "4 estrelles a writing", i el tutor planificava
amb aquell número.

*On s'aplica i on no.* A `mastery-db.skills[*]`, que només es mou amb la
pràctica. **No** als ítems de repetició espaiada: aquells ja porten el temps a
dins (`due_date`, `interval_days`), i decaure'ls seria comptar dues vegades el
mateix.

*Forma:* res durant `grace_days` (14), després un nivell per cada `step_days`
(21) sense practicar, mai per sota de `floor` (1). Un skill de nivell 5 encara és
5 al cap d'un mes, 4 als 35 dies, 3 als 56, 2 als 77 i 1 als 98 — prou lent
perquè unes vacances no esborrin un any, prou ràpid perquè "dominat" vulgui dir
alguna cosa. Es pot ajustar per alumne amb
`preferences.mastery_decay` al perfil, i `{"step_days": 0}` l'apaga.

*El detall que fa que sigui segur:* el decaïment és **absolut**, no incremental.
Es calcula del nivell **guanyat** (`mastery_level_earned`, camp nou) i dels dies
inactius, mai restant del valor anterior. Com que `update-db.py` restaura l'estat
pre-sessió i reaplica el payload, un decaïment relatiu s'hauria compost a cada
execució. Hi ha un test que ho comprova explícitament.

**12b. Els errors ara poden curar. ✅ FET, i era una troballa nova**
`read-db.py` ordenava els patrons febles per freqüència històrica, amb un segon
criteri inert: el `mastery_level` d'un patró **no puja enlloc del codi** (només
es crea a 0). Conseqüència: un error que l'alumne va corregir a l'abril seguia
sent la prioritat número u del tutor al setembre.

*Fet:* el pes d'un patró es divideix per dos cada `step_days` que passa sense
aparèixer, i cada patró arriba al tutor amb `days_since_seen`. La freqüència real
es continua reportant: només canvia l'ordre. Provat amb un patró de freqüència 9
de fa 120 dies contra un de freqüència 3 d'avui — guanya el d'avui.

*Pendent:* que el `mastery_level` dels patrons pugi quan l'alumne els encerta.
Amb els registres estructurats de P1-5 (categoria + text incorrecte → `pattern_id`)
ja és possible; no ho he fet perquè canvia què considera "feble" el sistema i
val la pena decidir-ho amb dades.

**12c. Vocabulari estructurat. ⏳ pendent**
Lemes + formes + POS + nivell CEFR en lloc de camps lliures. Seria la primera
migració real d'esquema (v1→v2) i validaria `migrate-db.py` amb dades de debò.

**13. Àudio local. 📌 DEMANAT (2026-09-13) — avaluació de cost**

Demanat concretament: *«sentir la frase en l'idioma, ben pronunciada»*. Això és
**sortida de veu (TTS)**, no entrada, i la diferència de cost entre les dues
meitats és enorme. Val la pena separar-les.

### 13a. Escoltar (TTS) — ✅ FET (2026-09-13)

Un botó 🔊 al costat de cada frase en la llengua meta (exercici, correcció,
vocabulari). L'alumne el prem i la sent.

| | |
|---|---|
| **Motor** | `piper` — binari estàtic + model ONNX per veu (~60–110 MB). CPU pura, sense GPU. |
| **Servidor** | Un endpoint `GET /api/fluent/say?text=…` → WAV/Opus, amb memòria cau a disc per hash del text (`<perfil>/.audio/<sha1>.opus`). Les frases es repeteixen molt: la cau fa que la segona vegada sigui instantània. |
| **Web** | Un botó per bloc de text en llengua meta + `<audio>`. El clic ja és el gest d'usuari que demanen els navegadors per reproduir. |
| **Prompt / pedagogia** | **Cap canvi.** El tutor no se n'assabenta, no hi ha eina nova, no hi ha context extra per torn. És capa de presentació pura. |
| **Recursos** | ~150 MB de RAM mentre sintetitza, ~0,2–0,4 s per frase en CPU. **No competeix per la VRAM** amb llama.cpp — que és el recurs escàs a railab i a rapve. |
| **Cost** | **~1 dia.** Unes 250 línies al servidor (endpoint + cau + validació de mida i d'idioma) i ~80 a la web. |
| **Riscos** | Qualitat de veu desigual per llengua (anglès molt bo; el català és més just). Cal decidir quin idioma es llegeix — **només la llengua meta**, mai la nativa, o l'exercici perd la gràcia. El binari i el model s'han d'empaquetar (afegeix ~100 MB a l'exportació). |

**Fet, i tal com estava pressupostat.** Dos botons 🔊 (la capçalera de
l'exercici i el bloc "correct version"), un endpoint `GET /api/fluent/say` amb
cau a `<perfil>/.audio/<sha1>.wav`, i `GET /api/fluent/tts-state` perquè la web
sàpiga si ha de dibuixar-los. Zero canvis de prompt, zero context per torn.

Tres decisions que valen la pena recordar:

- **Ve apagat.** `config/fluent.json` → `tts.enabled: false`. Sense veu
  instal·lada la web no dibuixa cap botó: **millor res que un botó que falla**.
- **Mai endevina la llengua.** Si no hi ha veu per a la llengua meta d'aquell
  perfil, no sona — una veu anglesa llegint català ensenya el contrari del que
  toca. I només es llegeix la llengua meta, mai la nativa.
- **El filtre és la part delicada.** El text ve d'una bombolla de xat: markdown,
  emoji, `8/10` i els aclariments entre parèntesis en català. `speakableText()`
  els treu tots; és el que més comprovacions té (`server/test/tts.test.ts`).

Instal·lació (una vegada, per màquina, i cal internet):

```bash
scripts/flowed-tts.sh install en_GB-alba-medium
python3 scripts/flowed-check.py tts demo-en
```

Seguretat: piper s'executa amb una llista d'arguments i el text va per stdin —
la frase d'un alumne no pot convertir-se en una ordre. CPU pura: si mai apareix
a `nvidia-smi`, algú ha posat una build CUDA i competirà amb el model deep.

### 13b. Parlar (STT) — car, i amb una dependència amagada

Que l'alumne *digui* la frase i el sistema l'escolti és una altra lliga.

- **`whisper.cpp`** va bé, però en CPU és lent per a un torn interactiu i en GPU
  **competeix per la VRAM amb el model deep** — el coll d'ampolla actual.
- **Bloqueig real:** `getUserMedia` (el micròfon) només funciona en *secure
  context*. L'exposició d'avui és basic auth **sense TLS** a la LAN, o sigui que
  l'STT **obliga a fer primer el punt 17 (TLS)**. No és opcional ni ajornable.
- **I sobretot:** transcriure ≠ avaluar pronunciació. Saber *què* ha dit no diu
  si ho ha dit *bé*; puntuar pronunciació és un problema propi (alineament
  fonètic, GOP scoring) i no el resol Whisper.
- **Cost:** ~3–5 dies per a la transcripció, **més** el TLS, **més** una decisió
  pedagògica que encara no està presa sobre com es puntua.

**Al pla, en aquest ordre** (acordat 2026-09-13 — es fa quan estiguem
preparats, no abans):

1. **TLS primer** (punt 17). Sense *secure context* no hi ha micròfon, punt. És
   feina útil igualment: avui l'exposició és basic auth en clar.
2. **Decidir què vol dir "ben pronunciat"** abans d'escriure codi. Transcriure
   i comparar cadenes puntua el vocabulari, no la pronunciació. Les opcions
   serioses són GOP scoring amb un model acústic, o baixar el llistó a
   "s'entén / no s'entén" — que és honest i molt més barat.
3. **Llavors `whisper.cpp`**, i decidir si va a CPU (lent però sense tocar la
   VRAM) o a GPU amb torn compartit amb el model deep.

Fins llavors, `speaking` continua sent conversa escrita, que és el que ja fa.

**14. Informes i exportació.** Un informe setmanal per alumne (Markdown → PDF)
generat per cron des de les 6 BD, i exportació de vocabulari a CSV/Anki. Les
dades ja hi són i són inspeccionables; només cal la vista.

**15. Còpia fora de la màquina.** Els backups són locals. Un `auto-backup.sh`
(git privat o `rclone` xifrat) amb cron diari tanca l'únic risc de pèrdua total.

**16. Observabilitat.** Un log estructurat per torn (perfil, agent, model, ms de
*prefill* i de generació, tokens, eines cridades, resultat) en JSON-lines, i un
`/api/fluent/stats` per veure-ho. Amb LLM local, la latència per torn és *la*
mètrica de producte i ara no es mesura.

**17. Seguretat de l'exposició.** Basic auth sense TLS a la LAN és raonable, però
si algun dia surt de la LAN cal TLS (reverse proxy amb certificat) i límit de
peticions. Complementari: rotació de contrasenyes i que
`/api/fluent/progress` no pugui filtrar rutes al missatge d'error.

**18. Consolidar la documentació del comportament.** `AGENTS.md` descriu la
fórmula SM-2 que en realitat calcula `update-db.py`, i els fitxers d'agent
conserven còpies "legacy" de les regles que ara viuen a `rules.md`. No trenca
res avui, però és deriva garantida. *Fix:* deixar a `AGENTS.md` només el
mapatge nota→qualitat (el que el model ha de fer) i remetre a la implementació;
esborrar les còpies legacy dels agents un cop verificat.

## C.4 Pla suggerit

| Fase | Contingut | Resultat |
|---|---|---|
| 1 (dies) | P0 1–4 | Multi-usuari correcte de debò; guàrdies per sessió; sessió identificada sense endevinar |
| 2 (1 setmana) | P1 5 (amb doble escriptura) + 11 (tests del servidor) | La captura de dades deixa de dependre d'un regex sobre prosa |
| 3 (1 setmana) | P1 6 (streaming) + 7 (context) | Salt gran de percepció de qualitat, sense canviar de model |
| 4 (dies) | P1 8 (systemd o compose) + 9 (config única) | Servei que es recupera sol i s'exporta a una altra màquina sense cirurgia |
| 5 (obert) | P1 10 (noms) + P2 segons prioritat | Neteja conceptual i creixement de producte |

## C.5 Decisions a validar abans de tocar res

1. **Grading estructurat (P1-5):** es vol l'eina nova com a camí principal, amb
   el parser només de xarxa de seguretat, o es prefereix mantenir el parser com
   a principal i l'eina com a complement?
2. **Supervisió (P1-8):** `systemd --user` (mínim, nadiu, ja hi ha `.env`) o
   `docker-compose` per a tot l'stack (més portable cap a la 4060)?
3. **Renombrar l'arbre de prompts (P1-10):** val la pena ara, o es deixa per
   quan hi hagi una migració d'esquema que ja obligui a tocar documentació?
4. **Face:** es manté com a rol (desactivat però previst) o s'arxiva
   definitivament i es simplifica el *routing* a un sol model?

---

# D. Revisió dels skills (2026-09-13)

Revisats els 12 `SKILL.md`. La qualitat pedagògica és alta i les plantilles són
consistents entre elles. El problema no era el contingut sinó que **una part de
les instruccions descrivia un runtime que ja no existeix**: van ser escrites per
a Claude Code (eines `Read`/`Write`, auto-invocació, permisos amples) i
s'executen dins el servidor propi, on l'agent `learner` només té tres eines:
`skill`, `bash` (5 patrons) i `fluent_deep_evaluate`.

Els set punts marcats ✅ s'han aplicat; la resta queda documentada per decidir.

## D.1 Incoherències amb el runtime

**S1. La comanda per carregar l'estat estava denegada pel propi servidor. ✅**
Els 8 skills que carregaven estat deien
`python3 "${CLAUDE_PLUGIN_ROOT:-…}/hooks/read-db.py"`, forma que
l'allowlist de `tools.ts` (`^python3 \hooks/read-db\.py`) **rebutja** —
i que a més era innecessària, perquè la comanda ja precarrega l'estat amb la
directiva `` !`…` ``.
*Fet:* els skills diuen ara que l'estat ja és al context, i donen la forma
literal només com a excepció (amb la variant de Claude Code a part).

**S2. `allowed-tools: Read, Write, Bash` i les ordres d'escriure fitxers. ✅**
6 skills acabaven amb "desa la sessió a `~/.fluent/<id>/results/…`", cosa
impossible sense eina d'escriptura i que ja fa la Capa A en Python.
*Fet:* substituït per un bloc explícit: el tutor no escriu cap fitxer; la seva
única feina de persistència és qualificar amb el format parsejable.

**S3. Contradicció de persistència a tres bandes. ✅**
`AGENTS.md` manava finalitzar amb `persist-session.py` (que **no** és a
l'allowlist), `learner.md` manava persistir amb `fluent-db-updater`, els skills i
les comandes també, i `tutor.md`/`tutor-fast.md` encara deien "actualitza sempre
les 6 BD i desa el fitxer de resultats". Res d'això és possible ni necessari: el
servidor executa `accumulate-session.py` a cada *idle* i `persist-session.py` a
`/fluent-end` i al *sweeper*.
*Fet:* una sola història a `AGENTS.md`, `learner.md`, `tutor.md`,
`tutor-fast.md`, les 7 comandes i els 6 skills de pràctica — **el tutor no
persisteix res**. `fluent-db-updater` passa a ser el contracte del payload per a
mantenidors i per al camí Claude Code, amb un avís al capdamunt.

**S4. `fluent-session-analyzer` no pot funcionar a la web. ⏳**
Demana llegir `~/.fluent/<id>/results/*.md` i no hi ha eina de lectura (el mateix
amb el `fluent-learn` §5, "mira el fitxer de resultats d'avui").
*Opcions:* una eina nova de només lectura servida pel servidor
(`fluent_recent_sessions`, que retorni les N últimes fitxes resumides), o marcar
el skill com a "només camí opencode/TUI".

**S5. Tres convencions de nom per al fitxer de resultats. ⏳ (parcial)**
La implementació sempre escriu `{slug}-fluent-learn-{session-NNN}.md`,
independentment del skill. `AGENTS.md` ja s'ha corregit per dir la veritat; els
skills ja no manen desar res, i `fluent-session-analyzer` encara documenta
`{slug}-{skill}-session-{ID}.md`. Cal decidir: si es vol filtrar per habilitat
(que és el que l'analitzador assumeix), el canvi va al codi.

**S14. `/fluent-setup` no podia completar-se a la web. ✅ FET (2026-09-13, tarda)**
Trobat mentre es revisaven els skills: el setup interroga l'alumne i després ha
d'escriure `learner-profile.json` — amb l'eina `Write` (que no existeix) o amb
`ensure_data_dir.py` i `python3 -c …` (que l'allowlist denega). Però
`/api/fluent/setup-state` **arrenca `/fluent-setup` automàticament** quan
`preferences.setup_complete == false`, que és exactament com queda un perfil nou
creat amb `scripts/new-user.sh`. Conseqüència: un perfil nou es pot entrevistar,
però les respostes no es desen enlloc; els perfils actuals funcionen perquè es
van crear amb el runtime anterior (opencode, que sí tenia eina d'escriptura).
*Fet:* eina `fluent_setup_profile` amb camps tipats (nom, llengües, nivells,
minuts/dia, objectius, motivació, interessos). Valida el que un model
s'equivoca: la mateixa llengua com a nativa i objectiu, nivells que no són CEFR
(normalitza `a2` → `A2`), nom buit, minuts absurds (els retalla a 5-240), i
perfil inexistent — amb missatges `REJECTED: …` que diuen exactament què
arreglar, perquè el model ho pugui corregir al mateix torn. Escriu amb còpia de
seguretat prèvia (`learner-profile.json.backup-…`) i reemplaçament atòmic, neteja
els marcadors de plantilla que quedaven (`{YOUR_NAME}`,
`{travel|work|exam|…}`) i marca `preferences.setup_complete = true`, que és el
que fa que l'app deixi de preguntar.

El skill `fluent-setup` i la seva comanda estan reescrits: res d'eina `Write`,
res de `python3 -c`, i el **reset de progrés deixa de ser una opció del tutor**
(esborrar l'historial d'un alumne és feina del propietari, des d'un terminal i
amb còpia). Les actualitzacions de perfil tornen a passar per la mateixa eina.

Provat amb `server/test/setup-profile.test.ts` (18 comprovacions, executat per
la suite normal amb `node --experimental-strip-types`): el camí feliç, les
quatre menes de rebuig, que un rebuig **no escriu res**, la còpia de seguretat i
que no queden fitxers temporals.

## D.2 Qualitat i cost

**S6. Contaminació de neerlandès. ✅**
`fluent-writing` portava una secció "Dutch A2 patterns" i un exemple llarg;
`fluent-reading` tenia **les capçaleres de les preguntes en neerlandès dins les
plantilles** (`## Vraag 1: Hoofdidee`, `## Vraag 5: Waar of niet waar?`) — text
que el model copia literalment — a més d'un banc de textos en neerlandès;
`fluent-speaking` tenia els *fillers*; `fluent-review`, `fluent-progress`,
`fluent-learn`, `fluent-session-analyzer`, `fluent-db-updater`,
`feedback-template.md` i `sm2-worked-examples.md` tenien exemples o ids
neerlandesos. Mentrestant `rules.md` havia d'insistir cada torn en "no copiïs la
llengua dels exemples".
*Fet:* tot convertit a marcadors `{Target}` / `{Native}`, com ja estava
`fluent-vocab`. Les dues seccions "Language Reference" i el banc de textos s'han
substituït per l'explicació de per què no s'hi guarda cap idioma fix.

**S7. Regles duplicades. ✅**
Identitat de llengua, no-repetició i alternança eren a `rules.md` (concatenat
cada torn) **i** repetides a `learner.md`, `tutor.md`, `tutor-fast.md`,
`fluent-learn` i `fluent-vocab`.
*Fet:* una línia de referència a cada lloc. El prompt de sistema del `learner`
(AGENTS + LEARNING_SYSTEM + agent + rules) queda en ~30 KB.

**S8. Condicional mort a `fluent-learn` §6. ✅ FET**
`difficulty = "medium" if recent_accuracy > 0.70 else "medium"` (dues branques
iguals) → ara puja a `hard` per sobre del 80%, com el nivell següent. I les tres
fonts diuen la mateixa franja: ≤50% baixar, 50–79% mantenir (objectiu 60–70%),
≥80% pujar.

**S9. `fluent-writing` perdia TOTS els patrons d'error. ✅ VERIFICAT**
El skill feia servir correccions en la forma
`- {issue}: "{wrong}" → **"{correct}"** — {why}`, i el parser exigeix
`"wrong" → **"right"** (categoria`, amb parèntesi. Provat sobre el parser real:

| Format | Exercici capturat | Patrons d'error capturats |
|---|---|---|
| Canònic (`fluent-feedback-formatter`) | 1 | 2 |
| Variant de `fluent-writing` (abans) | 1 | **0** |

De les sessions d'escriptura — les més riques en errors — cap error arribava a
`mistakes-db`, que és el que tria els patrons febles de les sessions següents.
*Fet:* la plantilla del skill usa la línia canònica, amb l'avís del perquè, i hi
ha un test de regressió (`tests/test_error_categories.py`) que falla si algú la
torna a canviar.

**S13. La taxonomia de categories no coincidia en tres llocs. ✅ VERIFICAT**
`fluent-feedback-formatter` documentava una llista, el `DEEP_RUBRIC` de
`tools.ts` una altra (`register`, `word-order`) i `parse_error_patterns` una
tercera; el que no era a la llista del parser es convertia silencioionaent en
`grammar` (provat: `(prepositions — …)` s'arxivava com a `grammar_in_Monday`), i
el regex es menjava els guions (`word-order` → `word`).
*Fet:* `ERROR_CATEGORIES` a `hooks/db_schema.py` com a font única (15
categories), amb àlies i normalització de guions i espais; el parser l'importa;
`DEEP_RUBRIC` i els dos documents de prompt llisten exactament les mateixes; i
`tests/test_error_categories.py` falla si les tres superfícies divergeixen.
*Conseqüència assumida:* els `pattern_id` nous poden diferir dels històrics
(`grammar_X` → `prepositions_X`) per al mateix error; no s'han migrat els ids
existents.

**S10. `fluent-sm2-calculator` convidava a fer la feina dues vegades. ✅ (parcial)**
Reenquadrat com a referència per **explicar** els intervals a l'alumne, mai per
calcular-los (ho fa `update-db.py`), i la seva ordre d'exemple passa a la forma
literal. Queda pendent decidir si el skill continua tenint sentit al camí web.

**S11. `fluent-progress` és codi mort al camí web. ⏳**
El botó 📊 obre el panell del client (`app.js`, `openProgress()`), sense cap torn
de model. El skill i la comanda segueixen sent útils al camí opencode/TUI.

**S12. Metadades estancades. ⏳**
`disable-model-invocation`, `allowed-tools` i les explicacions sobre
auto-invocació només tenen sentit a Claude Code.

---

# E. Registre d'aquesta revisió

**2026-09-12** — anàlisi i document inicial.

**2026-09-13** — aplicat:

| Lot | Què | Fitxers |
|---|---|---|
| P0 1–4 | Context d'eina real per sessió · fora els hardcodes `nes` · `--session-id` del servidor al Python · marcador `capa_b_sid` · fuita de `FluentDB` · codi mort | `llm.ts`, `tools.ts`, `agent.ts`, `index.ts`, `http.ts`, `accumulate-session.py` |
| P0 5 | Marcador de finalització durable per sessió (`session.metadata.capa_b_done`) + finestra de 24 h al *sweeper*: evita repetir la Capa B cada minut sobre sessions velles | `db.ts`, `index.ts`, `agent.ts` |
| P0 6 | La Capa B deixa d'esborrar els patrons d'error i els ítems SM-2 de la Capa A (`errors` vs `error_patterns`) · `learner_slug` amb *fallback* al perfil | `persist-session.py`, `tests/test_capa_a_b.py` |
| P1-5 | Eina `fluent_record_answer`: el tutor declara cada resposta qualificada (nota, correccions amb categoria validada, `item_id` + qualitat) · registres a `.records/<ses>.jsonl` com a autoritat, prosa com a xarxa de seguretat, avís de divergència | `tools.ts`, `persist-session.py`, `accumulate-session.py`, `AGENTS.md`, `fluent-feedback-formatter`, tests |
| P1-9 | `config/fluent.json` canònic + `scripts/flowed-config.py` (3 capes amb precedència provada) · scripts i servidor el llegeixen · `max_tokens` deixa de ser ignorat | `config/fluent.json`, `flowed-config.py`, `fluent-start/stop.sh`, `docker-llama.sh`, `index.ts`, tests |
| P1-6 | *Streaming* de tokens darrere `FLOWED_STREAM` (off per defecte): acumulador pur amb recomposició de `tool_calls` fragmentats, deltes cap a l'event que la web ja entenia, part desada un sol cop | `llm.ts`, `agent.ts`, `db.ts`, `index.ts`, `config/fluent.json` |
| P1-7 | Mètriques per torn (tokens, temps, *roundtrips*, eines) al log i a `.metrics/turns.jsonl` · deixar de reinjectar el bloc d'estat a la 2a i 3a comanda d'una sessió | `llm.ts`, `agent.ts`, `commands.ts` |
| P1-11 | Primer test del servidor executable sense bun (`node --experimental-strip-types`), integrat a la suite | `server/test/stream-parser.test.ts`, `tests/test_server_stream.py` |
| P1-10 | READMEs explicant cada directori de prompts | `.claude/README.md`, `prompts/README.md` |
| Ritme | **Indicador de progrés**: el servidor compta les respostes registrades i les envia per SSE (`session.progress`) i per `GET /api/fluent/session-progress`; la web mostra `✏️ 3/8` amb barra i percentatge, i es recupera en recarregar. Llargada de sessió: `preferences.session_length` al perfil (12 per defecte, `0` l'apaga) i **el servidor** demana tancar en arribar-hi — per defecte **oferint** (`session_stop: "soft"`), o tallant si es configura `"hard"`. Escriptura i lectura queden exemptes (un escenari / un text). També: `daily_limits` existeix per fi a la plantilla — el "20 per defecte" dels skills de vocab i review no era enlloc de les dades | `pacing.ts`, `agent.ts`, `read-db.py`, plantilles, 3 skills, `server/test/pacing.test.ts` |
| Eines | `scripts/flowed-check.py`: comprovacions de només lectura d'un perfil (perfil, SM-2, patrons, mestria, registres, mètriques, BD de sessions). Neix d'una revisió del pla de proves: els fragments de Python enganxats al document petaven per la indentació i no distingien "encara no hi ha res" d'un error | `flowed-check.py`, `PROVES.md`, `tests/test_repo_layout.py` |
| P2-12 | Decaïment de mestria (absolut, configurable per alumne, `mastery_level_earned`) · ranquing de patrons d'error amb pes que decau i `days_since_seen` | `db_schema.py`, `update-db.py`, `read-db.py`, `tests/test_mastery_decay.py` |
| S14 | Eina `fluent_setup_profile`: l'entrevista de `/fluent-setup` ja es pot desar (validació, còpia de seguretat, escriptura atòmica, `setup_complete`) · skill i comanda reescrits · el reset de progrés deixa de ser cosa del tutor | `tools.ts`, `fluent-setup` (skill i comanda), `server/test/setup-profile.test.ts` |
| S8 | Condicional mort i franja de dificultat unificada a les tres fonts | `fluent-learn` |
| Dades | Ruta de la BD de sessions: `<perfil>/.opencode/opencode/opencode.db` → **`<perfil>/sessions/sessions.db`**, amb lectura de totes dues i sense esborrar res · `scripts/migrate-sessions-db.py` (còpia verificada amb l'API de backup) · `FLOWED_SESSIONS_DB` per forçar-la | `index.ts`, `db.ts`, `persist-session.py`, `accumulate-session.py`, `flowed-web.sh`, `new-user.sh`, tests |
| Extra | `scripts/models/llama-omnicoder.sh` (llançador face antic) tenia un bloc orfe i **no passava `bash -n`**: hauria fallat el dia que algú el cridés. Bloc duplicat eliminat | `llama-omnicoder.sh` |
| P1-10b | Renombrat `.opencode/{agent,commands}` → `prompts/{agents,commands}` · helper a `scripts/` · plugin, `opencode.json` i llançador free a `obsolet/opencode-runtime/` · `--web` arxivat · test d'estructura | `agent.ts`, `commands.ts`, `tools.ts`, `flowed-web.sh`, prompts, skills, `README.md`, `MANUAL.md`, `tests/test_repo_layout.py` |
| SM-2 | Bloc `fluent:review_results`: el tutor declara quins ítems de la cua ha repassat i amb quina qualitat · parser + validació contra la cua · ocultació a la UI · prompts | `persist-session.py`, `accumulate-session.py`, `web/app.js`, `fluent-review`, `fluent-vocab`, 2 comandes, `AGENTS.md`, `docs/MANUAL.md` |
| S1+S2+S3 | El tutor deixa de tocar infraestructura (carregar estat, escriure fitxers, persistir) | `AGENTS.md`, 3 agents, 7 comandes, 8 skills |
| S9+S13 | Format de correcció parsejable a `fluent-writing` · taxonomia única de categories amb normalització | `db_schema.py`, `persist-session.py`, `tools.ts`, `fluent-writing`, `fluent-feedback-formatter`, `feedback-template.md`, test nou |
| S6+S7 | Fora el neerlandès de plantilles i exemples · regles dures només a `rules.md` | 9 skills, 3 agents, 2 references |
| Ordre | **Porta de repetició espaiada.** L'única regla d'ordre que el servidor pot verificar: si la sessió comença amb 🎲 o 🔁, els ítems vençuts d'avui es fan abans del contingut nou. El servidor coneix la cua (`spaced-repetition.json`) i sap quins `item_id` han tornat per `fluent_record_answer`; la nota al prompt es repeteix mentre la porta és oberta i calla quan es tanca. Topall: com a molt **mitja sessió** (`ceil(session_length/2)`), o el `daily_limits.review_items_per_day`, el que sigui més petit — un endarreriment gran no es menja el dia. Negociable **només a l'inici**: començar directament en 📝/🗣️/📚/📖 és l'alumne triant el dia i no activa la porta; `preferences.review_gate: false` l'apaga per alumne. La web ho mostra com `🔁 2/5 · ✏️ 3/8` | `pacing.ts`, `agent.ts`, `web/`, `fluent-learn`, `server/test/pacing.test.ts` |
| Superfície | **Les comandes són botons, no comandes.** L'alumne no escriu mai `/fluent-…`: nou botó **🏁 Acaba** (tanca la sessió i dispara la Capa B), i `/fluent-setup` surt del camí de l'alumne — la web ja no hi arrenca mai, mostra un avís curt si el perfil no està configurat. L'alta la fa l'administrador amb `scripts/new-user.sh` + **`scripts/flowed-profile.py`** (mateixa validació que l'eina `fluent_setup_profile`, i també escriu `session_length` / `session_stop` / `review_gate`). L'entrevista `/fluent-setup` queda per a l'admin que la prefereixi | `web/index.html`, `web/app.js`, `web/style.css`, `flowed-profile.py`, `flowed-check.py`, comanda `fluent-setup`, `tests/test_fluent_profile.py` |
| Sessions | **Una sessió acabada ja no es reprèn.** Tancar el navegador no fa res al servidor, i `web/app.js` guarda l'id a `localStorage`: tornar-hi hores després reprenia la MATEIXA sessió — inclosa una que el sweeper ja havia finalitzat, de manera que tot el que es fes després arribava a les BD només per Capa A (sense resum, sense fitxer de resultats, sense `review_results`). Vist en viu: `ses_9073d7bb` finalitzada a les 10:15 i amb un torn nou a les 16:09. Ara `GET /api/fluent/session-state` decideix (finalitzada o >30 min inactiva → no es reprèn) i el client n'obre una de nova. La ratxa i el progrés viuen a les BD, no a la sessió | `http.ts`, `web/app.js`, `tests/test_fluent_profile.py` |
| Sessions | **Una sessió d'abans d'un reinici del servidor tampoc es reprèn** (2026-09-25). L'exercici pendent (targeta, pràctica, skill) només viu a la memòria del procés: en reprendre-la es veia la pregunta, però la resposta no es corregia i sortia una pregunta nova. `resumeState()` (session.ts) hi afegeix el cas `restart` (`last_activity` anterior a l'arrencada del procés): en carregar, el client obre una sessió nova; amb la pàgina oberta, `POST message/command` respon `{bounce:"restart"}` sense cridar el model i el client rebota amb avís. La sessió vella la tanca el sweeper (resum inclòs) | `session.ts`, `http.ts`, `web/app.js`, `server/test/session-resume.test.ts` |
| Sessions | **`capa_b_done` deixa de ser permanent.** El marcador evitava que el sweeper repetís la Capa B cada minut, però també impedia per sempre tornar-la a executar. Ara cada torn reobre la sessió si estava marcada (BD + `session-draft.json`); `persist-session.py` recalcula des del snapshot T0, així que repetir-ho és segur per disseny | `db.ts` (`reopenIfFinalized`), `agent.ts`, `tests/test_persist_session.py` |
| Mètriques | **Quines eines, no només quantes.** El log comptava `tool_calls` sense els noms, i per això no es podia respondre "el tutor ha registrat les respostes?". Ara `turns.jsonl` i la línia del log porten la llista, amb `!` davant d'una crida rebutjada (`REJECTED` inclòs, que des de fora semblava un èxit). `flowed-check.py metrics` ho resumeix i avisa si no hi ha cap `fluent_record_answer` | `llm.ts`, `agent.ts`, `flowed-check.py` |
| Veu | **On es pot llegir en veu alta, i com se sap.** La primera versió posava el 🔊 a la targeta d'exercici (`#exercise-card`), que està desactivada des d'abans (`EXERCISE_CARD_ENABLED = false`): **el botó no es va dibuixar mai**. I posar-lo a l'exercici tal qual tampoc serveix — un exercici no és fiablement en la llengua meta ("Translate into English: *Ahir vaig anar al mercat*" és català, i una veu anglesa llegint-ho ensenya el contrari). Endevinar la llengua és una heurística que **falla sorolloionaent**. Solució: dues fonts, totes dues segures — la frase corregida (llengua meta per definició, sense tocar cap prompt) i un marcador explícit `[[say]]…[[/say]]` que el tutor posa. Si el model se n'oblida, es perd un botó; el fracàs és silenciós, que és la direcció correcta. El marcador no arriba mai als ulls de l'alumne | `web/app.js`, `style.css`, `rules.md`, `fluent-feedback-formatter`, `server/test/web-render.test.ts`, `tests/test_tts.py` |
| Veu | **Piper deixa de dependre del `.bashrc`.** El binari porta les seves `libespeak-ng` i `libonnxruntime` al costat, i el carregador hi ha d'apuntar. Arreglat en un perfil de shell, funciona al terminal i **falla en silenci** (503, sense res al log) el dia que el servidor l'arrenqui systemd, un cron o una altra màquina — que és preciionaent el P1-8 que tenim pendent. Ara `ttsEnv()` deriva `LD_LIBRARY_PATH` i `ESPEAK_DATA_PATH` del directori del binari, i l'script fa el mateix; `status` ho comprova. Mesurat a railab: RTF **0,049** (20× més ràpid que temps real) | `tts.ts`, `flowed-tts.sh`, `server/test/tts.test.ts` |
| VRAM | **`kv_type` configurable i context a 49152.** `q8_0` parteix la KV per la meitat (necessita `-fa 1`, que ja hi era), així que 48k de context previstos en **~12.600 MiB** — menys que els 13.938 mesurats a 32k. 48k i no 64k perquè el motiu ja no és la VRAM (la 4060 Ti és una VM dedicada): més context del que cal encareix el prefill, convida l'historial a créixer i un 14B raona pitjor a contextos llargs; la causa real de l'incident ja està atacada amb les sessions noves. **Trampa trobada pel camí:** `FLOWED_DEEP_CTX=32768` als tres `.env`, i l'`.env` mana sobre el config — canviar `config/fluent.json` no hauria servit de res. Comentat als tres. **Cap d'aquests números està mesurat**: bloc 18 de PROVES | `config/fluent.json`, `flowed-config.py`, els dos llançadors, els tres `.env`, `model-qwen14b-q4.md` |
| Context | **Poda de l'historial — ja no és opcional.** En producció: `request (41808 tokens) exceeds the available context size (40960)`. El torn **falla**: l'alumna rep un error en comptes d'un exercici. I abans de fallar, es degrada — mesurat sobre 120 torns reals: de 1,9 s a **19,8 s** per torn (10×), tot dins el model, amb el prompt passant de 25.650 a 31.946 tokens i un màxim de 69.484. Ara cada torn es reté a un pressupost (context − sistema − sortida − 10% de marge), descartant els missatges **més antics**; el prompt de sistema no es toca mai i l'últim missatge de l'alumna tampoc. **Es podia fer perquè ja no cal l'historial complet**: el `covered` del servidor és qui recorda què s'ha preguntat, i `rules.md` ara ho diu explícitament | `pacing.ts`, `agent.ts`, `rules.md`, `server/test/pacing.test.ts` |
| Context | **`ctx: 36864` + `f16`** (2026-09-14). ~14.600 MiB previstos: ~1,7 GB de marge a la 4060 Ti, i un 12% més de context sense tocar la KV. El sostre del model segueix sent 40960, inabastable en f16 sobre 16 GB | `config/fluent.json` |
| Repo | **Desmarcat i llest per a git** (2026-09-14). `.claude/{hooks,skills,references}` → `hooks/`, `skills/`, `references/` a l'arrel, com ja hi era `prompts/`; `CLAUDE.md`, `.claude-plugin/`, `settings.json` i `hooks.json` retirats a `obsolet/claude-code-plugin/` — el camí d'instal·lació com a plugin s'abandona. `CLAUDE_PROJECT_DIR`/`CLAUDE_PLUGIN_ROOT` → `FLOWED_PROJECT_DIR`/`FLOWED_ROOT`, **llegint encara els noms antics** per compatibilitat. Els noms reals de les alumnes surten de tot el codi i els docs (exemples neutres: `alex-en`, `sam-en`, `demo-en`) i el mapa perfil→port passa de `config/fluent.json` a l'`.env`, que no es publica. `README.md` reescrit; l'original de l'etapa plugin a `docs/README-original-plugin.md`. **La història no es toca**: CHANGELOG i docs de migració es queden com estaven | tot el repo, `.gitignore`, `.github/workflows/ci.yml` |
| Repo | **`.gitignore`**: fora `obsolet/` (63 MB), les dues transcripcions de sessions reals (4,5 MB amb noms de menors), els backups de perfils, `.env`, `node_modules`, `__pycache__` i tot el que és dades d'alumne (`results/`, `.records/`, `.metrics/`, `.daily/`, `.memories/`, `sessions/*.db`). El repositori queda en **1,3 MB i 150 fitxers** | `.gitignore` |
| Dades | **Les sessions es daten pel dia que van passar.** `build_report` posava `datetime.now()`, que és correcte per a una sessió tancada el mateix dia i fals per a totes les altres. Vist en viu: el sweeper va reprocessar sessions del 3 i del 9 de setembre i les va estampar totes dues el **14**, així que `session-log.json` deia que dues nenes havien practicat un dia que ningú havia obert l'app. Els números no eren erronis (update-db restaura el snapshot T0 abans de reaplicar), però l'historial explicava una ficció — i l'historial és el que el tutor cita en mode friend. Ara surt de `time_created` de la sessió, amb `last_activity` i `time_updated` com a alternatives i `avui` només si no hi ha res | `persist-session.py`, `tests/test_persist_session.py` |
| Eines | **`flowed-check.py historial`**: contrasta la BD de sessions amb `results/` i `session-log.json`, que són tres traces independents, i llista les entrades per data. Neix de "la Sam segur que ha fet més sessions" — i va servir per veure que no en faltaven, sinó que dues entrades estaven mal datades. *La primera versió comparava els ids del log (`session-005`) amb els de la BD (`ses_…`), que són espais de noms diferents, i marcava totes les entrades com a perdudes: soroll, no diagnòstic. Corregit* | `flowed-check.py` |
| Memòria | **`scripts/flowed-memories.py` — experiment, desconnectat del tutor.** Lot de nit que busca als torns del dia coses que l'alumna hagi dit sobre ella i les deixa a `<perfil>/.memories/pending.jsonl`. **No arriba al prompt**: connectar-ho és una decisió posterior, i la idea és mirar una setmana què en surt abans de construir res. Tres decisions de disseny: (a) **offline** — ningú espera, així que la mida del model deixa de ser un compromís; (b) **intersecció de dos models** — exigir acord costa una segona passada i elimina l'error segur d'un sol model, que és el que importa; (c) **la cita literal es verifica** contra el que va escriure, i si no hi és el candidat es descarta. La part difícil no és extreure, és **abstenir-se**: la majoria de torns són respostes d'exercici, i "I have a dog" com a traducció no és un fet sobre ella — per això se li passa l'exercici com a context. El tutor no escriu mai aquí | `flowed-memories.py`, `tests/test_fluent_memories.py` |
| Dades | **`scripts/close-old-sessions.py`**: marca com a tancades les sessions del build antic que no ho van arribar a estar, escrivint **només** `capa_b_done` a la metadada de la sessió. No executa la Capa B, no toca les 6 BD, no escriu cap fitxer de resultats i no mou cap número. Avui ja s'ignoren (finestra de 24 h del sweeper); això ho fa explícit perquè un canvi futur d'aquesta finestra no les pugui despertar i sumar-les dues vegades. Deixa còpia `.bak` i té `--dry-run`; per defecte no toca res de menys de 2 dies. Decisió conscient: **no s'incorporen** — les dades per torn ja hi són (Capa A) i reprocessar-les arriscaria doble compte | `close-old-sessions.py`, `tests/test_close_old_sessions.py` |
| Prompt | **Regressió meva d'ahir:** `flowed-profile.py` va passar a escriure `daily_goal` i esborrar `session_length`, però `read-db.py` només exposava el nom antic — el tutor havia deixat de veure l'objectiu del dia. Ara passa els dos | `read-db.py` |
| Migració | **`docs/MIGRACIO-LLVM.md`**: portar l'app a **llvm** (la VM de producció a rapve), a `/opt/fluent` amb symlink versionat ara, no al final, per trobar-hi els errors amb temps. Segueix sent copiar el directori i canviar l'`.env` com sempre, **més `bun install`** — el servidor propi amb bun no existia a l'última migració i sense `js-yaml` no arrenca. L'únic pas amb risc real és mesurar 36864/f16 sobre 16 GB, que no s'ha fet mai | `MIGRACIO-LLVM.md` |
| Context | **Decisió (revisada l'endemà a 36864): `ctx: 32768` + `kv_type: "f16"`** — el que hi havia, mesurat. El desbordament el resol la poda, no el context, així que els tokens extra només retardaven el retall i a canvi hi posaven el q8_0 sense mesurar. Següent pas si algun dia cal: **36864 amb f16** (~14.600 MiB, ~1,7 GB de marge a la 4060 Ti). El `kv_type` queda cablejat i provat per si es vol | `config/fluent.json`, `model-qwen14b-q4.md` |
| Context | **El sostre real del model és 40960, no 49152.** Qwen3-14B té `max_position_embeddings: 40960` i llama.cpp reté el `-c` al màxim entrenat si no s'activa YaRN — o sigui que el 49152 que vam configurar al migdia **no es va aplicar mai**, i la taula de VRAM, tot i ser correcta, proposava valors inabastables. Corregit a `ctx: 40960` amb `q8_0` (≈11.900 MiB previstos). YaRN es descarta: degrada la qualitat als contextos curts, que és on viu aquesta app | `config/fluent.json`, `model-qwen14b-q4.md` |
| Sessió | **La no-repetició passa a ser del servidor.** "Never repeat an exercise" era una línia a `rules.md`, i amb quatre patrons febles per treballar el model tornava als mateixos tres enunciats dins la mateixa lliçó. Ara el servidor n'extreu una empremta de cada exercici plantejat (`**Sentence:** X`, `## Exercise N: … (X)`), l'acumula a `plan.covered` i li torna la llista literal amb l'ordre de no reutilitzar-ne cap — i si s'esgoten els patrons, d'inventar-ne un de nou en comptes de reciclar. És el mateix patró que ha funcionat cada vegada avui: el que el model ha de recordar, el recorda el servidor | `pacing.ts`, `agent.ts`, `daily.ts`, `server/test/pacing.test.ts` |
| Sessió | **La Lliçó ha de tancar-se sola.** Amb el compte exhaurit, `pacingNote()` no retornava res i el tutor seguia presentant exercicis indefinidament — vist en viu amb el badge a 0 i el tutor per l'"Exercise 8", tot amb el mateix enunciat. Afegida la nota de tancament (resum curt + tornar als botons, i si l'alumne insisteix, no obrir cap exercici nou) i la instrucció de **variar la forma** de l'exercici. De passada, retirat el sostre de 12 per sessió: contradeia el que s'havia acordat (la Lliçó acaba, el dia no) i a més llegia `session_length`, que ja no s'escriu — només actua si un admin posa `session_stop: "hard"` | `agent.ts`, `tests/test_tts.py` |
| Sessió | **La Lliçó del dia substitueix el "12".** El número era un pressupost disfressat de pla: arribar a 15/12 en una sessió real no volia dir res, perquè no hi havia res a completar. Ara són dues coses. **🎓 Lesson** té final — repassos vençuts d'avui completats amb drills fins a un mínim de 6 — i porta un badge ambre amb el que queda; **✏️ N** no en té, compta tot el qualificat i hi posa una cara que puja (😐 · 🙂 · 😄 · 🤩 als terços de l'objectiu, 15 per defecte). **Res es bloqueja**: el badge diu què es deu i l'alumne tria. El comptatge passa a ser **del DIA, no de la sessió** — coherent amb la ratxa, la cua SM-2 i les BD, i immune a tancar la pestanya. Cada 3 lliçons, la Lliçó reserva un exercici per a l'habilitat més abandonada (writing/reading, mai vocabulari), **integrat a dins**, no com a segona obligació | `pacing.ts`, `daily.ts` (nou), `agent.ts`, `web/`, `flowed-profile.py`, `flowed-check.py`, `server/test/pacing.test.ts` |
| Dades | **Els patrons d'error es perdien tots.** `parse_error_patterns` descartava qualsevol correcció amb nota ≥ 8 com a "demostració". El tutor puntua generós (8, 9, 10), així que un 9/10 amb un `🟡 "last friday" → **"last Friday"**` no deixava rastre. Mesurat sobre una sessió real: tres respostes, tres correccions, **zero** patrons. Ara la senyal és el marcador (🟡/🔴/❌), no la nota. I la taxonomia: el tutor escriu el terme gramatical (`past tense`), no la nostra categoria, i tot el que no coincidia queia a `grammar` — afegits els àlies reals | `persist-session.py`, `db_schema.py` |
| Botons | **El tutor deixa de recomanar comandes.** Amb la cua de repàs buida, `fluent-review` imprimia "Try: `/fluent-learn`, `/fluent-vocab`…" — consell que l'alumne no pot seguir, perquè no té línia d'ordres. Corregit als skills (`fluent-review`, `fluent-progress`, `fluent-setup`), fixat com a regla dura a `rules.md`, i **garantit al renderitzat**: `humanizeCommands()` reescriu qualsevol `/fluent-x` en el nom del seu botó abans de pintar-lo, digui el que digui el model | `rules.md`, 3 skills, `web/app.js`, `server/test/web-render.test.ts` |
| Menús | **Un menú no és un exercici.** El missatge de "cap repàs pendent" (i el menú d'obertura, i el de tancament) es marcava `✏️ Exercici` al flux: convida un nen de vuit anys a respondre una llista d'opcions. `MENU_RE` ampliat + heurística de dos noms de botó. De pas, el camí SSE en viu i el de streaming no passaven per `renderTutorText()`: no treien els blocs màquina ni pintaven l'exercici. Ara hi ha **un sol renderitzador** per al text del tutor | `web/app.js`, `server/test/web-render.test.ts` |
| Veu | **TTS local (13a).** Botó 🔊 a l'exercici i a la frase corregida; `GET /api/fluent/say` amb cau per hash a `<perfil>/.audio/`, `GET /api/fluent/tts-state` perquè la web sàpiga si dibuixar-los. Motor piper, **CPU pura** (no toca la VRAM del model deep). Ve **apagat**: sense veu instal·lada no es dibuixa cap botó. Mai endevina la llengua ni llegeix la nativa. `speakableText()` treu markdown, emoji, notes i els parèntesis en català abans de sintetitzar. Instal·lació d'admin: `scripts/flowed-tts.sh install <veu>`. Zero canvis de prompt i zero context per torn | `tts.ts`, `http.ts`, `index.ts`, `config/fluent.json`, `web/`, `flowed-tts.sh`, `flowed-check.py`, `server/test/tts.test.ts`, `tests/test_tts.py` |
| Skills | **`fluent-session-analyzer` eliminat.** Llegia `results/*.md` amb marcadors per planificar — feina que `read-db.py` ja fa millor i amb dades estructurades (patrons ranquejats per freqüència amb recència, cua SM-2, mestria). Era context per torn a canvi de res. Els `results/*.md` es queden com a registre llegible per una persona. Tanca de retruc S5 (convenció de noms) | `skills/`, `fluent-learn`, `session-file-template.md`, `README.md`, `CLAUDE.md` |

**Verificació:** `tsc --noEmit` net ·
`python3 -m unittest discover -s tests` → **155/155** (dos d'ells executen harnesses de TypeScript amb node, amb 350 comprovacions internes) ·
`py_compile` de tots els hooks, scripts i tests · prova funcional de
`accumulate-session.py --session-id` amb una BD de sessions sintètica de dues
sessions del mateix alumne.

**No verificat encara (cal fer-ho amb el sistema engegat):** el *streaming*
(`FLOWED_STREAM=1`) contra un model real, i una sessió real
d'extrem a extrem amb un perfil de proves (`test-en`) per confirmar que el tutor
ja no intenta cap ordre denegada i que un exercici d'escriptura deixa el patró
d'error a `mistakes-db`. És la prova que tanca el lot.

**Deute obert, per ordre suggerit:** provar-ho tot en viu (veure
[`PROVES.md`](PROVES.md)) · **TLS** (punt 17, i és el que desbloqueja l'STT) ·
**STT / pronunciació** (13b, al pla) · S4 (el tutor no pot llegir sessions passades) · la
mestria dels patrons d'error no puja mai quan l'alumne els encerta · poda de
l'historial quan les mètriques ho justifiquin · P1-8 (supervisió:
systemd/compose) · S10, S11, S12 · la resta de C.2/C.3.

*Tancats en aquest lot:* S5 (convenció de noms de `results/`, amb l'analyzer) i
S14 (el setup ja no és una entrevista inservible: l'alta la fa l'admin per
terminal).

---

# E. Incident 2026-09-16 — la lliçó sense correcció ✅ CORREGIT

Primeres sessions reals de les dues alumnes a **llvm**. Resultat: repetició
constant de la mateixa pregunta tot i respondre bé, el comptador de la Lliçó
sense baixar, i **cap correcció de les respostes**. Es van haver d'aturar.

## E.1 Evidència

Reconstruïda de `sessions.db` (transcripcions literals), `.metrics/turns.jsonl`
(quines eines es van cridar cada torn) i `.daily/` (el pla de la lliçó).

| | perfil A | perfil B |
|---|---|---|
| Torns | 60 | 19 |
| Crides a `fluent_record_answer` | **0** | **4**, només els 2,5 primers minuts |
| Directori `.records/` | **no existia** | 1 fitxer |
| `lesson-2026-09-16.json` | `done: 3` | **`done: 0`** amb 13 exercicis contestats |
| Repetició màxima | **25 torns idèntics** seguits | 5 torns |

L'eina `skill` apareix **una sola vegada per sessió**, sempre al primer command.

## E.2 Causa d'arrel

**El model no carregava mai el skill `fluent-review`.**

Cada sessió s'obre amb un `/fluent-learn` automàtic (`initialCommand()`,
`web/app.js`). Quan l'alumna prem 🎓 Lesson, `/fluent-review` arriba com a
**segon** command de la sessió. La primera línia del command deia *"Load the
`fluent-review` skill via the skill tool and follow it EXACTLY"*, i el model,
ja en ple flux amb un patró que funciona, no s'atura a cridar cap eina. El
skill no era mai el primer command d'una sessió, i per tant no es carregava mai.

Tot el contracte de correcció — marcador 🔴/🟡/🟢, `**Corrections:**`,
`**Correct version:**`, `**Score: N/10**` — viu **només** a
`skills/fluent-review/SKILL.md`. Sense skill:

```
sense skill → sense correcció visible → sense "Score: N/10" al text
  → countGradedInText()==0 → creditTurn() retorna abans d'hora
  → plan.done congelat → la nota de pacing diu el mateix cada torn
  → "Present exercise 4 of 15 now, and nothing else" × 25
```

**Dues instruccions meves hi van contribuir directament.** Les dues es van
afegir per arreglar *"la Lliçó torna a començar de zero quan hi tornes"*, i les
dues diuen "salta't el preàmbul i ves a l'exercici" — i el preàmbul és
exactament on hi havia la càrrega del skill:

1. `agent.ts`, sufix `continuing` del cos del command: *"continue the ongoing
   practice directly: ... present the next exercise"*.
2. `pacingNote()`, missatge `system` al final del prompt, **cada torn**: *"This
   is a CONTINUATION ... Do NOT greet ... Present exercise N of M now, and
   nothing else."*

Per a un 14B, "carrega un skill i segueix-lo" contra "presenta l'exercici N i
res més" no és competició: guanya l'última i la més concreta. La prova és el
perfil B: els 4 primers torns fan **exactament** el que deia la nota (cridar
`fluent_record_answer`) i **res** del que deia el skill (cap línia de feedback).
Obeïa la nota, no el skill.

I com que el text de la nota és funció de `plan.done`, i `plan.done` es va
congelar, el model va rebre una instrucció **idèntica byte a byte** amb un índex
d'exercici fix durant 25 torns. No és el model derivant: és el servidor clavant-lo.

## E.3 Correccions aplicades

| # | Canvi | Fitxers |
|---|---|---|
| 1 | **El servidor carrega el skill.** `loadSkill()` llegeix `skills/<command>/SKILL.md` i el servidor el fixa al **system prompt** de la sessió (`activeSkill`), no a l'historial — l'historial es poda quan s'omple el context i el contracte de correcció és l'últim que pot desaparèixer. Present a **tots** els torns, no només al del botó | `commands.ts`, `agent.ts` |
| 2 | Les 8 comandes deixen de demanar-ho al model: *"already in your system prompt ... Do NOT call the skill tool"* | `prompts/commands/*.md` |
| 3 | **La nota de pacing passa a ser estat, no guió.** Diu on és la lliçó i què ja s'ha preguntat; com es fa un exercici és del skill. Fora `"and nothing else"`, fora `"Present exercise N"`, fora la duplicació del procediment | `agent.ts` |
| 4 | **El comptador accepta evidència estructurada.** Compta si hi ha línia nova a `.records/` **o** `Score: N/10` al text. Abans només el text: 4 correccions estructurades i el comptador a 0 de 12 | `agent.ts` |
| 5 | **Detector d'estancament.** Si la nota no canvia en 4 torns → línia al log. L'estat va durar 25 torns i no va sortir enlloc | `agent.ts` |
| 6 | **Detector de repetició.** Si l'empremta de l'exercici és la mateixa que el torn anterior → línia al log | `agent.ts` |
| 7 | `**Word (Catalan):**` ara sí que es detecta. Amb el patró antic tota una tanda de vocabulari era invisible per a la llista d'"already asked" | `pacing.ts` |
| 8 | **Contracte de correcció escrit un sol cop, al skill:** *"Every answer gets BOTH"* — el feedback visible **i** la crida `fluent_record_answer`. No són alternatives | `skills/fluent-review/SKILL.md` |
| 9 | Regla de varietat moguda al skill (abans només a la nota) | `skills/fluent-review/SKILL.md` |
| 10 | **La nota i el bloc de skill surten de `agent.ts` cap a `pacing.ts`** (`lessonNote()`, `skillBlock()`). `pacing.ts` és Bun-free per disseny: és la part que es trenca, i per tant la que ha de poder-se executar en una prova sense model, sense BD i sense GPU | `pacing.ts`, `agent.ts` |
| 11 | **`"critical"` deixa de ser un exercici.** L'única empremta que es treia d'un ítem de repàs era el parèntesi del títol (`## Exercise 2: Spaced Review (Critical)`), o sigui la dificultat. Al fitxer real del 16/09 hi ha literalment `"critical"` a la llista d'"already asked", fent de tapadora de quinze preguntes diferents. Ara es llegeix `**Exercise:**` / `**Item ID:**`, hi ha una llista de paraules que mai són un exercici, i `**Question:**` només és recurs de darrera hora (perquè sovint és una instrucció genèrica, "Rewrite this sentence correctly", i prohibir-la vetaria tot un tipus d'exercici) | `pacing.ts` |
| 12 | **`flowed-check.py lliço`** — veredicte de vuit línies sobre la lliçó d'avui. Cap dels checks existents deia en una sola pantalla que el tutor no corregia | `scripts/flowed-check.py` |
| 13 | **`skipDirectives` es reenvia de veritat.** Estava declarat a `loadCommand` i no s'passava mai a `expandDirectives`: cada command reexecutava `read-db.py` i reinjectava tot el bloc d'estat, **+2,8k tokens per premuda** (mesurat: 16519 → 19361) | `commands.ts` |

## E.3bis Segona tanda — el que va sortir en engegar-ho (mateixa tarda)

La primera prova en viu amb `test-en`, ja amb el skill carregat, va donar això:

```
Review 1/6 — 🟡
Type: vocabulary
Current mastery: ⭐☆☆☆☆
{Target}: {the word}
What does it mean in {Native}?
```

Tres errors independents en una sola pantalla, i **cap era visible abans**
precisament perquè el skill no arribava mai:

**a) El model copia els exemples del `SKILL.md`.** Això és l'Exemple 1 de
`fluent-review`, literal. La secció ja porta escrit *"(Placeholders. NEVER copy
the language of an example into a session)"* — i una regla que diu *no copiïs
això* és una regla que el prompt no hauria de contenir. El mateix mecanisme
explica el `{✅}` que surt al transcript del matí: és el `{✅ or ❌}` de la
plantilla de `fluent-feedback-formatter`.

**b) La cadena de skills tenia el mateix forat que el skill.**
`fluent-review` § 4 diu *"Use the `fluent-feedback-formatter` skill for
per-answer feedback"* — un segon salt amb l'eina `skill` que el model tampoc no
fa. La plantilla de correcció viu en aquell segon fitxer: el contracte estava a
**dues** càrregues de distància d'un model que no en feia ni una.

**c) Les files de plantilla es comptaven com a dades reals.** `test-en` ve amb
un ítem SM-2 el `item_id` del qual és la cadena `"{unique_identifier}"` i un
patró d'error `example_pattern_1` amb freqüència 0. Comptats com a reals, un
perfil buit es converteix en "6 ítems per repassar" — i el tutor, obligat a
repassar sis coses que no existeixen, copia el primer exemple que veu.

**Correccions:**

| # | Canvi | Fitxers |
|---|---|---|
| 14 | **`renderSkillForModel()`** — el servidor renderitza el skill per al model en comptes d'entregar-lo cru: treu `## Examples`, resol `{Target}`/`{Native}` des del perfil de l'alumne, i afegeix una regla explícita («la teva resposta no pot contenir mai els caràcters `{` o `}`; si n'estàs escrivint un, estàs copiant el document en comptes de fer-lo servir») | `pacing.ts`, `commands.ts` |
| 15 | **`requires:` al frontmatter** dels 5 skills de pràctica, i `loadSkill()` el segueix (un nivell, sense cicles). El `fluent-feedback-formatter` viatja ara amb el skill que el necessita | `skills/*/SKILL.md`, `commands.ts` |
| 16 | **`isTemplateValue()` i `drillMaterial()`** — una fila que encara té la forma de la plantilla (`{...}`, `example_*`, `...`) no és una dada. `dueItemIds()` les filtra i `drillMaterial()` compta només patrons reals (freqüència > 0) | `pacing.ts` |
| 17 | **El cas "no hi ha res a repassar".** Cua buida **i** cap patró real → la nota diu que això és una **primera lliçó, no un repàs**: prohibeix etiquetar els exercicis com a "Review", prohibeix inventar historial de mestria, i demana N peces de material **nou** al nivell de l'alumne | `pacing.ts`, `agent.ts` |

*Cost:* el bloc de pràctica al *system prompt* passa a ~5.200 tokens
(`fluent-review` renderitzat + `fluent-feedback-formatter`), contra 36864 de
context. Ho compensa de sobra el punt 13 (el bloc d'estat que ja no es
reinjecta, −2,8k per premuda).

## E.4 Verificació feta abans de desplegar

`tsc --noEmit` net · `python3 -m unittest discover -s tests` → **220/220**.

**Banc de proves nou: `server/test/lesson-note.test.ts`** — 51 comprovacions que
passen les cadenes **literals** del 16/09 (tretes de `sessions.db` i de
`.daily/lesson-2026-09-16.json`) per les funcions reals, executades amb
`node --experimental-strip-types`. No és un `grep`: és una execució.

**Replay de les 79 respostes reals del tutor** contra el codi nou:

| | perfil A (60 torns) | perfil B (19 torns) |
|---|---|---|
| Qualificades, regla antiga (només text) | 7 | **0** |
| Qualificades, regla nova (text **o** registre) | 7 | **4** |
| Comptador que hauria arribat a | 7 de 15 *(el fitxer real deia 3)* | 4 de 12 *(el real deia 0)* |
| Exercicis amb empremta | **35** *(el real en tenia 6)* | **14** *(el real en tenia 4)* |
| Torns amb exercici idèntic, ara detectats | 9 | 4 |
| Notes de pacing diferents | 42 de 60 | 12 de 19 |

La darrera fila és la que explica el bucle: abans la nota era **una sola**,
repetida seixanta vegades.

**El que això NO prova:** que el model, amb el skill al *system prompt*,
efectivament corregeixi. Això necessita l'LLM real i és la prova de
[`PROVES.md` § 22.2](PROVES.md), amb `test-en`.

## E.5 La lliçó de fons

És la mateixa d'aquest projecte, un pas més enllà:

> El que el model ha de recordar, ho recorda el servidor.
> **El que el model ha de carregar, el carrega el servidor.**

I una de nova, del mateix incident:

> El servidor li diu al model **on és**, no **què ha de fer**. Una instrucció
> imperativa injectada cada torn deixa de ser una guia i passa a ser un bucle
> el dia que el seu contingut es congela.

## E.6 Deute obert que va sortir d'aquí

- **La persona del tutor canvia entre torns.** La web envia sempre
  `agent: "learner"`; `runCommand()` fa servir `resolved.agent`
  (`tutor`/`tutor-fast`) i `runMessage()` torna a `learner`. Així, el torn del
  botó i els torns de resposta corren amb *system prompt* diferent (i, on hi ha
  face, amb model diferent). És el mateix patró que l'skill: estat per command
  que no sobreviu als torns següents. **No tocat**: canviar quin model respon
  té risc propi i mereix decisió a part.
- **Direcció dels exercicis de vocabulari.** Al perfil A els ítems SM-2
  s'estaven preguntant al revés (*"What is the Catalan word for 'morning'?"*):
  examinaven la nena de la seva pròpia llengua. Ve de `fluent-learn` fent
  vocabulari sense la regla de direcció del skill de review. Amb el skill
  carregat hauria de desaparèixer — **cal confirmar-ho en viu**.
- **Tall dur de repetició.** Ara només es detecta i es registra. Un reintent del
  torn quan l'exercici es repeteix és més invasiu (el missatge ja s'ha
  transmès) i queda pendent de decidir.
- Les dades del 16/09 de les dues alumnes són brutes: `spaced-repetition.json` i
  `mistakes-db.json` es van reescriure a partir d'una transcripció sense cap
  qualificació.

---

# F. Auditoria de comportament (2026-09-19)

Motiu, literal: *"abans també va passar test i per les nenes va ser un autèntic
desastre... ha de provar que avança, que tot evoluciona com toca."*

Té raó, i la crítica va al moll de l'os del que hi havia: **la suite era
gairebé tota de codi font, no de comportament.** Els 220 tests haurien passat
el 16 de setembre igualment, amb el tutor fent seixanta torns sense corregir.
Un test que mira si una funció retorna el que toca no veu mai una app trencada.

## F.1 Mètode

Fer córrer **el pipeline real de dades** (`update-db.py`, `read-db.py`, l'SM-2
de debò) sobre setmanes simulades, i fer-li la pregunta que faria un pare: *el
que encerta deixa de sortir? el que falla torna?* Sense model: el que s'audita
és la memòria del sistema, no el que diu el tutor.

## F.2 El que funcionava

**L'SM-2 és correcte.** Intervals 1 → 6 → 16 → 45 dies, els ítems encertats
surten de la cua diària i tornen espaiats. La columna vertebral del sistema
està bé.

## F.3 El que no — i és exactament el símptoma que fa por

**`mistakes-db.error_patterns[].mastery_level` no pujava mai.** Els ítems SM-2
sí que pugen de mestria (`update_spaced_repetition`); els patrons d'error, que
són el que el tutor llegeix a través de `read-db.py`, no els tocava ningú. Ja
constava com a deute obert; ara està mesurat:

> Tres paraules encertades tres vegades cadascuna, intervals creixent
> correctament — i el dia 12 les tres encara a `mastery_level: 0`, encara
> ofertes com els punts més febles de l'alumna.

I això no és cosmètic. Amb la cua SM-2 buida, la Lliçó omple els exercicis que
falten **amb els patrons febles**. O sigui: el tutor torna a fer les mateixes
tres paraules. Cada dia. Per sempre. Vist des de l'altra banda de la pantalla
és un tutor que repeteix sempre les mateixes preguntes — el mateix símptoma del
16, per un camí completament diferent.

## F.4 Correccions

| # | Canvi | Fitxers |
|---|---|---|
| 18 | **`heal_patterns()`** — un encert puja la mestria del patró un pas (màx. 5); una fallada la baixa un pas i reinicia la ratxa. L'ítem SM-2 i el patró ja comparteixen id (punt 19 del lot anterior), així que és un `join` directe | `hooks/update-db.py` |
| 19 | **`HEALED_MASTERY = 4`** — un patró curat surt de `top_weak_patterns` i es compta a part (`healed_patterns`). `drillMaterial()` tampoc el compta, així que la Lliçó no el fa servir de material | `hooks/read-db.py`, `server/src/pacing.ts` |
| 20 | **La llargada de la lliçó és del servidor, no de la cua.** El skill tancava la sessió quan s'acabava la cua SM-2 ("Review Session Complete! Reviewed: 2") i deixava la insígnia a 2 de 6. Ara la nota ho prohibeix explícitament i el skill ho diu com a regla | `pacing.ts`, `skills/fluent-review/SKILL.md` |
| 21 | **L'estat de l'alumne va al system prompt.** *Regressió meva del 16*: en fer que `skipDirectives` funcionés de veritat, el bloc amb nom, nivell, cua i patrons quedava només al primer missatge — i `pruneHistory` esborra els més antics primer. En una sessió llarga desapareixia, mentre el command següent deia "és a l'historial, no el recarreguis". Ara és al system prompt, on la poda no arriba | `commands.ts`, `agent.ts` |

## F.5 Trajectòria després de les correccions

Simulació de 30 dies, tres errors el primer dia i respostes correctes després:

| dia | acció | intervals | mestria | febles | curats |
|---|---|---|---|---|---|
| 1 | 3 errors | 1 · 1 · 1 | 0 · 0 · 0 | 3 | 0 |
| 2 | 3 bé | 1 · 1 · 1 | 1 · 1 · 1 | 3 | 0 |
| 3 | 3 bé | 6 · 6 · 6 | 2 · 2 · 2 | 3 | 0 |
| 9 | 3 bé | 16 · 16 · 16 | 3 · 3 · 3 | 3 | 0 |
| 25 | 3 bé | 45 · 45 · 45 | 4 · 4 · 4 | **0** | **3** |

I la recaiguda: una sola fallada de `welcome` → mestria 4 → 3, torna a
`top_weak_patterns`, i l'ítem torna a la cua **de demà** amb interval 1.

## F.6 La suite, ara

`tests/test_progress_is_real.py` — cinc comprovacions que fan córrer el
pipeline real sobre setmanes simulades, escrites com les preguntes d'un pare i
no com les d'un programador:

- el que encerta deixa de sortir (30 dies → mestria ≥ 4, cap patró feble)
- l'espaiat s'eixampla de veritat (interval > 20 dies)
- el que oblida torna **demà**
- una setmana fallant-ho tot no fa explotar la cua (3 errors = 3 ítems, sempre)
- res no es clava mai a la falta d'ortografia de l'alumna

**227/227 · `tsc --noEmit` net · harness de rèplica: 57/57.**

## F.7 El que aquesta auditoria NO cobreix

El model. Tot l'anterior és la memòria del sistema: què es desa, què es
recupera, què s'ofereix al tutor. **Que el tutor faci bon ús del que rep només
es pot comprovar en viu** ([`PROVES.md` § 22](PROVES.md)), i el criteri de
validació no és cap test: és una sessió sencera que a l'Albert li sembli
raonable.

---

# G. La prova amb el model, i els guards (2026-09-19, tarda)

## G.1 El que faltava

Tota la resta comprova el codi. **Res no feia parlar el tutor.** El 16/09 la
suite era verda mentre el tutor feia seixanta torns sense corregir, perquè el
que es va trencar era el que el model rebia, i cap test unitari ha llegit mai
la resposta d'un model.

`scripts/flowed-e2e.py` obre sessió per l'API igual que el navegador, prem els
botons, contesta, i **llegeix el que respon**. `scripts/flowed-seed.py` li dona
passat al perfil amb el pipeline real, dia a dia, perquè la cua SM-2 tingui
alguna cosa a fer.

## G.2 La regla que va sortir d'aquí

> **O funciona, o hi posem un guard on toqui.**

El marcador es va demanar **tres vegades** al skill (`Score: 0/10 🟢` seguia
sortint a totes les respostes) i es va arreglar en una línia el dia que el
servidor va deixar de demanar-ho i el va corregir ell. A partir d'aquí, tot el
que importa s'imposa:

| Guard | Què fa |
|---|---|
| `alignMarkersToScore()` | 🔴 per 0-4, 🟡 per 5-7, 🟢 per 8-10. La nota ja està escrita a la mateixa frase |
| `alignLessonHeader()` | "Review 7/6" → "Review 4/6". El tutor perd el compte quan l'alumna marxa i torna; el servidor no |
| `turnGuard()` + `enforceTurn()` | Si el torn tanca amb exercicis pendents, repeteix una pregunta d'avui, o corregeix sense preguntar res → **el fa reescriure el torn**, una vegada. Mesurat: 6 intents de repetir, 6 reescriptures, zero repeticions a la pantalla |
| `plan.credited` | Un exercici es compta un sol cop, per molt que es qualifiqui dues vegades |
| `deriveRecord()` | Si el tutor no crida `fluent_record_answer` (no ho fa mai), el servidor treu el registre del seu propi text |

## G.3 Instruments

- **`build stamp`** — el servidor imprimeix el hash de `server/src` a l'arrencada
  i el serveix a `/api/global/health`; l'e2e **es nega a jutjar** un servidor que
  no corre el codi del disc. Dues execucions es van discutir per això: els skills
  es rellegeixen cada torn i el TypeScript no, així que mitja reparació hi és i
  mitja no.
- **`<perfil>/.metrics/guards.jsonl`** — una línia per actuació del guard, al
  costat de les mètriques del torn. El log del servidor viu a `/tmp` i
  desapareix.
- **`flowed-check.py lliço`** — veredicte de vuit línies sobre la lliçó d'avui.

## G.4 Estat de la prova de navegació

`--scenario wander`: Lliçó → 2 exercicis → 📚 Vocabulary → 2 → 🎓 Lesson → 2 →
📚 Vocabulary → 2. **22 de 23**, i la que faltava era una etiqueta de log mal
posada, no un defecte.

```
✅ en tornar a Lesson no saluda ni mostra menú   "## Review 5/6 — moderate"
✅ la lliçó reprèn on era, no de zero
✅ la lliçó no repeteix el que ja havia preguntat
✅ el que fa a Vocabulary queda desat            graded 11 → 14
✅ i no compta com a exercici de la lliçó        lesson 5 → 5
✅ en tornar a Vocabulary no repeteix paraules
✅ cada resposta rep marcador, versió correcta i nota   8/8
✅ les respostes arriben a .records/             15 línies
```

## G.5 El que encara no s'ha provat

- **`--scenario full`**: el tancament de la lliçó i els dos torns de després.
  Cap execució hi ha arribat mai.
- **Dos dies seguits**: que el que contesta avui torni demà com toca. Ara es pot,
  perquè els registres ja s'escriuen.
- **Un perfil real** (`nes-en`), sense `--reset`.
- **`--scenario marathon`** i la prova de dos dies amb `flowed-advance-day.py`.

## G.6 L'`item_id` el posa el servidor (2026-09-19)

`fluent_record_answer` demanava al tutor l'`item_id` «copiat literalment de la
llista d'ítems per repassar». Al tutor no se li ensenya aquesta llista: la nota
de ritme li dóna el **contingut** de l'ítem i res més, a posta, perquè un id
inventat fa avançar la programació equivocada sense dir-ho. Així que cap registre
escrit pel tutor duia `item_id`; els únics que en duien eren els que el servidor
derivava quan el tutor s'oblidava de cridar l'eina.

El resultat és el pitjor possible: arreglar les crides a l'eina **buida** la
programació de repàs.

    sweep 1   12 ítems · 3 per repassar  → 9 registres, 9 amb item_id
    sweep 2   15 ítems · 0 per repassar  → 8 registres, 0 amb item_id

La regla de sempre: **el que el model ha de reportar, el servidor ho dedueix.**
L'ítem que hi havia a la pantalla és un fet del servidor (`gradingItem`), i ara
l'eina l'adjunta ella mateixa quan el tutor no en dóna cap — validat contra la
cua igualment, i esborrat en sortir de la lliçó perquè una assignació caducada
no faci avançar un repàs que ningú ha demanat.

Harness: `server/test/record-item.test.ts` (7 comprovacions).

## G.7 El servidor també tria què es repassa (2026-09-19)

Sis execucions amb el punt de partida igual, i amb tot el que havia fallat tota
la tarda en verd: marcador, versió correcta, nota, comptador, registres,
`item_id`. El que quedava era **repetició**, i quedava sencera:

    "An ___ is a fruit."            × 4
    "She ___ to school every day."  × 3
    "I need to write a letter in ___." × 3

    58 intervencions del guard, 14 de les quals «rewrite rejected: feedback lost»

La nota deia què NO es podia tornar a preguntar («Already asked today — not
again, in any form: …») i deixava l'elecció al tutor. Un 14B triant sota una
llista de prohibicions que creix torna a la mateixa frase; i quan el guard el fa
reescriure, una de cada tres reescriptures es carrega la correcció i s'ha de
llençar.

La regla de sempre, aplicada un cop més: **una prohibició és una cosa a obeir;
una assignació és una cosa a fer.** El servidor ja reparteix l'ítem de la cua
d'un en un; ara, quan no hi ha res vençut, també tria el patró feble que toca
(`nextDrill`, el de mestria més baixa i més freqüent, amb l'error real de
l'alumna adjuntat) i el manté uns quants torns abans de retirar-lo — una errada
mereix un segon exercici, no un tema nou. L'ítem de la cua continua manant: dos
subjectes en un mateix torn és com va descarrilar la lliçó del 16/09.

Harness: `server/test/lesson-note.test.ts` (10 comprovacions noves).

## G.8 Una nota sense resposta al darrere no és una nota (2026-09-19)

El pla del dia va sortir així abans de la primera pregunta:

    {"total": 6, "done": 1, "credited": []}

`done` puja encara que l'exercici no es pugui identificar — és volgut, una
errada d'empremta no li pot costar el progrés a l'alumna. El que no és volgut és
que pugi **sense que ningú hagi contestat**. Un torn obert amb un BOTÓ (🎓
Lesson, 📚 Vocabulary) no porta resposta, i quan el tutor va decorar la seva
resposta d'obertura amb un «Score: 2/10», el servidor va comptar un exercici que
encara no s'havia preguntat.

Al banc de proves va avortar quatre de sis execucions. A una alumna li menja un
exercici a dalt de cada lliçó, en silenci.

Ara, si no hi ha resposta de l'alumna al darrere, no es compta ni se'n deriva
registre — queda registrat com a event de guard (`graded with no answer`). I la
resposta es **consumeix** en comptar-la, perquè un segon torn sense resposta
pròpia no la pugui tornar a comptar.

Al costat, al banc: la comprovació de «la lliçó ja estava començada» llegia el
pla **després** de la salutació i del torn que obre la lliçó, o sigui que també
comptava el que aquells dos torns havien acreditat. Ara llegeix el dia que
l'execució **hereta**, abans del primer torn.


## G.9 Go, Writing i els exercicis tancats (2026-09-23)

**Decisió (Albert):** els exercicis es separen per tipus, no per botó.

- **Tancats** — un buit, una sola resposta correcta. Viuen a 🎲 **Go**
  (gramàtica i vocabulari del camí del currículum) i a 🎓 **Review**. Són els que
  passaran a JSON + comprovació a cegues (`comprova(frase, resposta)`): la
  propera feina, i la resposta a exercicis ambigus com «The car is ___.».
- **Oberts** — l'alumna escriu o diu les seves paraules. 📝 **Writing**,
  🗣️ Speaking, 📖 Reading. Es corregeixen en prosa; no hi ha resposta única a
  comprovar.

**Per què.** Writing s'havia convertit en «demanar frases amb forats i prou»:
Go amb un altre nom, i l'app sense cap lloc on l'alumna produís text propi.

**Què canvia:**

| Peça | Canvi |
|---|---|
| `web/index.html` | 📝 Writing torna a ser visible, amb badge diari. Go: «grammar & vocabulary from your path». |
| `web/app.js` | `writingBtn` amb el mateix `renderSkillBadge` que Speaking; entra a `TRACKED_MODE_CMDS`. |
| `server/src/daily.ts` | Comptador diari `writing`, com `speaking` / `reading`. |
| `server/src/agent.ts` | `inWriting` → `bumpDaily({writing: 1})`; `sessionProgress.writing`; `writingFrameFor()`. |
| `server/src/pacing.ts` | `writingLengthNote`: A1 1-2 frases pròpies amb «Use: …», A2 3-5; **mai un buit**. `writingBlankGuard`: un `___` o «complete the sentence» a Writing es reescriu. |
| `hooks/curriculum.py` | `next --writing` → `writing_frame()`: l'estructura de gramàtica activa (la que Go treballa), només lectura, perquè l'alumna la faci servir en text lliure. |
| `skills/fluent-writing` | A1/A2: una tasca curta cada cop (tema + «Use:»), corregida, i la següent. B1+: un escenari per sessió, com abans. |
| totes les skills | La llista de botons del final inclou 📝 Writing. |

**Obligatori un cop al dia**, igual que Speaking (i que Reading per sobre de
l'A1): el badge avisa, mai bloqueja. Writing no té bloqueig de nivell.

Proves: `server/test/writing.test.ts` (8), `tests/test_curriculum.py` (+2).

## G.10 Un buit de vocabulari ha de dir quina paraula hi va (2026-09-23)

**Cas:** `a1.vocab_colors_adjectives` → «Sentence: The car is ___.» Encara que
l'alumna sàpiga que la lliçó és de colors, qualsevol color hi encaixa, i només
pot endevinar. El guard dels números (`openBlankGuard`) era el primer cas
d'aquest problema; aquest n'és la regla general per a qualsevol llista de
paraules.

**Regla:** a una competència de vocabulari, si la targeta té un buit, la línia
del buit porta la paraula **en la llengua de l'alumna, entre parèntesis**:
«The car is ___ (vermell).». Això fixa la resposta sense regalar l'anglès. No
valen com a pista:

- una categoria: «(colour)», «(adjective)», «(animal)»…
- la paraula anglesa de la llista;
- una tria entre paraules de la llista: «(red/blue)».

Una targeta de traducció o de definició no té buit i ja queda fixada per com
està feta, així que el guard no hi entra. Els números continuen amb el seu
guard propi.

**Com s'aplica:**

- `vocabBlankGuard` (`pacing.ts`) actua al mateix punt que la resta de guards
  i fa reescriure el torn un cop.
- Si la reescriptura continua sense la paraula, es registra a `guards.jsonl`
  com a «vocab gap still open after rewrite». No hi ha pedaç automàtic perquè
  el servidor no sap la paraula en català, i aquest número és el que dirà si
  cal més.
- La nota de `curriculum.py` diu el mateix en una línia i substitueix el
  paràgraf llarg d'abans.

Gramàtica **no** hi entra: amb el context de la competència, la majoria de
buits ja tenen una resposta clara (Albert).

Proves: `server/test/vocab-gap.test.ts` (9).

## G.11 La porta de repàs segrestava Writing (2026-09-24)

**Cas (`nes-en`):** va acabar la lliçó (14 de 14), va prémer 📝 Writing, i el
tutor li va servir «Review 1/6 — critical … Correct the sentence: "There is a pen
on the desk"». La nota que va rebre el tutor en aquell torn de Writing era:

    Spaced-repetition gate: 0 of 6 due review items done in this session.
    Before introducing NEW material, work through the remaining 6 …

Hi havia tres errors:

1. La porta es decidia segons **la primera ordre de la sessió**
   (`sessionOpenedWith`), no segons la pràctica en pantalla. Una sessió que havia
   passat per Review la duia a tots els botons de després.
2. Comptava «0 de 6» just després de 14 de 14: no reconeix els ítems que la
   lliçó acaba de repassar.
3. S'avalua abans que la nota de Writing, així que Writing no rebia les seves
   instruccions.

**Arreglo:** la porta es decideix amb `currentCommand`. Només 🎓 Review la porta,
i dins de Review el pla de la lliçó ja decideix què toca, així que a la pràctica
ja no s'obre enlloc. Review es deu pel seu badge, mai segrestant una altra
pràctica. La porta queda inert: s'esborra a la fase 5 de
`PLA-EXERCICIS-TANCATS.md`.

Prova: `server/test/pacing.test.ts`.

**Proves posades al dia (2026-09-24).** 11 fallades, cap de lògica trencada:

- `test_curriculum`: els llindars 10/20/30 ara es llegeixen de `DEPTH`, no van
  escrits a mà. La còpia «mecànica» del currículum no porta profunditat, perquè
  `cfg_for` ja no deixa que un cfg petit substitueixi el de `normal`.
- Tutor simulat: triava paraules fora de la llista.
- `lesson-note`: quatre comprovacions buscaven textos antics d'`agent.ts`.
- El renderitzador de skills ara també omple `{native_language}` i
  `{target_language}`, que el model copiava literalment.

445/445.

## G.12 Review sobre el banc (2026-09-24)

Fase 4 de `PLA-EXERCICIS-TANCATS.md`, opció C per als patrons antics de la cua.
`tryBankReviewTurn` (`agent.ts`) i `review_pick` / `legacy_competence`
(`curriculum.py`). Mateix interruptor que Go (`exercises.bank`). Si no hi ha
cap ítem, Review torna al camí del model, com abans.

Tres coses al servidor:

- **`creditBankAnswer`:** una resposta del banc suma al dia i, a Review, a la
  lliçó. Abans, cap resposta del banc arribava al comptador.
- **Els ítems del banc van lligats a la seva pràctica:** en canviar de Go a
  Review, o a l'inrevés, l'ítem que hi havia a la pantalla s'oblida.
- **El registre d'un exercici de Review porta l'`item_id` de la cua** i una
  qualitat SM-2 (`floor(nota/2)`), així que la cua avança sola.

Proves: `tests/test_bank_review.py` (col·locació segura, ordre de Review, retirada,
corrector, banc sencer) · `server/test/bank.test.ts`.

## G.13 Fase 5 i ajustos posteriors (2026-09-24)

**Fase 5:** fora els guards que el banc ha deixat sense res a vigilar
(`openBlankGuard`, `patchOpenBlank`, `vocabBlankGuard`), els «drills» del model
(`nextDrill`), la porta de repàs sencera i els paràgrafs de la nota del
currículum. Resultat: −282 línies a `pacing.ts` i −102 a `agent.ts`. El que també
fan servir Writing, Speaking i Reading es manté (`deriveRecord`, `turnGuard`, i
els guards d'imatges i de direcció de llengua).

**Prova de nivell:** surt del banc revisat
(`_bank_checkpoint_items`, `curriculum.py`) i la corregeix `bank.grade`.

**Corrector del banc:** «gairebé» també a «Correct», paraula per paraula.
`_is_inflection` evita que una altra forma del mateix mot (plays/play) compti
com a errada de lletra.

**Banc que s'esgota:** `bank_left` (`bank.py`) alimenta un punt tènue a la vista
del camí de l'alumna (`bank_low`) i la columna «Banc nous» a la vista del
docent.

**Mètriques:** `turns.jsonl` guarda `command`.

463/463.

## G.14 On viuen els perfils: `FLOWED_HOME` (2026-09-24)

La carpeta dels alumnes (`~/.fluent`) estava escrita a mà a 24 fitxers. Ara
es resol en un sol lloc, amb la mateixa regla a Python i a shell:

- **Python:** `hooks/main_paths.py` (abans `fluent_paths.py`), amb
  `profiles_root()` i `profile_dir(id)`.
- **Shell:** `scripts/lib-paths.sh`, que defineix `FLOWED_HOME_DIR`.

Regla:

1. `$FLOWED_HOME`, si està definida;
2. `~/.flowed`, si existeix, o si encara no existeix cap de les dues;
3. `~/.fluent`, mentre la carpeta vella no s'hagi mogut.

Així res es trenca abans del canvi. Per passar a `~/.flowed`, amb l'app aturada:

    scripts/flowed-stop.sh            # o aturar cada web
    mv ~/.fluent ~/.flowed
    scripts/flowed-start.sh

L'app en marxa no depèn del nom: el servidor i els hooks només fan servir
`FLOWED_DATA_DIR`, que construeix `flowed-web.sh`.

**Variables d'entorn (2026-09-25).** Totes les `FLUENT_*` s'han reanomenat a
`FLOWED_*` (mateix sufix: `FLOWED_DATA_DIR`, `FLOWED_DEEP_PORT`,
`FLOWED_WEBS`…), i el marcador `.fluent-active` a `.flowed-active`. Sense
compatibilitat amb els noms vells: cal reanomenar-les a cada `.env` de màquina
i a qualsevol `export` o servei fora del repo.

Proves: `tests/test_main_paths.py`. Comprova que Python i shell donen el mateix
resultat en els quatre casos.

## G.15 Configuració per màquina: `.env` obligatori i veu trobada al disc (2026-09-26)

Primer desplegament de la 0.5.0 a llvm. Dues coses es van perdre pel camí, i
totes dues tenien la mateixa arrel: un valor de màquina vivint en un lloc que
viatja, o que es pot ignorar sense avís.

**1. `.env`.** Els quatre scripts que el llegien (`flowed-start.sh`, `flowed-stop.sh`,
`flowed-web.sh`, `models/docker-llama.sh`) tenien cadascun la seva còpia del
bucle. Un `.env` amb els noms d'abans (`FLUENT_*`) no donava cap error: les
variables no es reconeixien i tot sortia de `config/fluent.json`, que descriu
railab (backend native, port 12322). A llvm, l'start va intentar pujar el model
com a railab.

- Un sol carregador: `flowed_load_env` a `scripts/lib-paths.sh`. Mateixa regla
  (entorn > `.env` > `config/fluent.json`).
- Noms `FLUENT_*` (fitxer o entorn) → es llegeixen com `FLOWED_*`, amb un avís i
  la comanda per convertir-los. També a `flowed-config.py`.
- `flowed-start.sh` i `flowed-stop.sh` exigeixen `.env`; el pla imprimeix quin
  fitxer ha carregat.
- Proves: `tests/test_main_paths.py` (`LoadEnvTest`).

**2. Veu (TTS).** `flowed-tts.sh install` escrivia rutes absolutes del binari i de
la veu a `config/fluent.json`. Es va trencar dues vegades el mateix dia: després
de `mv ~/.fluent ~/.flowed` (rutes a la carpeta vella) i a llvm després del rsync
(el config de railab va substituir el de llvm).

- `config/fluent.json` → `tts` només diu `enabled` i els límits.
- `server/src/tts.ts` `loadTtsConfig(root, dataDir)` troba la instal·lació de la
  màquina: `$FLOWED_TTS_DIR`, o `_tts/` al costat del perfil, o la carpeta de
  perfils (mateixa regla que `main_paths.py`). Veus: `voices/*.onnx` amb el seu
  `.onnx.json`; l'idioma surt del nom (`en_*` → English). Una ruta al config
  només s'usa si existeix en aquesta màquina.
- `flowed-tts.sh install` ja no escriu rutes; `flowed-check.py tts` aplica la
  mateixa regla.
- Proves: `server/test/tts.test.ts` (bloc «this machine's install»),
  `tests/test_tts.py` (el config compartit no porta rutes).


## G.16 Notes de sistema i plantilles estrictes (2026-09-27)

Prova d'un 27B servit per TabbyAPI: cada resposta a un exercici obert donava
`LLM HTTP 400: TemplateError: System message must be at the beginning.` El
servidor posa la nota de cada torn (pacing, reintent) com a missatge `system` al
FINAL de l'historial, on un model petit la llegeix millor. La plantilla de
Qwen3-14B ho accepta; la d'aquest model (i d'altres) no.

- `server/src/llm.ts` `foldLateSystem()`: els `system` inicials es fusionen en
  un; els posteriors van a l'últim torn `user`, marcats «Note for the tutor — not
  written by the learner» (o com a torn `user` propi si l'anterior és del tutor).
- No canvia res per al 14B: només s'aplica quan l'endpoint refusa
  (`LATE_SYSTEM_REFUSED`); llavors es reintenta plegat i es recorda per a aquell
  `baseURL` durant la vida del procés (un sol 400, no un per torn).
- Avís de TabbyAPI «Unable to switch model to deep… inline_model_loading»: és
  inofensiu (respon el model carregat); ve del camp `model: "deep"` que enviem.
- Proves: `server/test/llm-messages.test.ts`.

## G.17 Competències extra per alumne (2026-09-27)

Una cançó, o el tema que fan a classe aquella setmana, per a un sol alumne.
Es practica a Go, surt a Stats i **no compta** per a la barra del nivell ni per
al checkpoint.

- **On viu:** al perfil, no al currículum del nivell.
  - `<perfil>/extra.md` — mateix format que `curriculum/en-A1.md`. `[extra]` = no
    compta (`progress` i `checkpoint_plan` només miren `core`). Secció per
    defecte: «Extra».
  - `<perfil>/bank/<id>.json` — els exercicis, mateix esquema i correcció
    determinista que el banc del nivell.
- **Codi:** `hooks/curriculum.py` `load_curriculum(path, data_dir)` →
  `add_profile_extras` (un id que ja és al nivell s'ignora). `hooks/bank.py`
  `bank_dirs` busca primer al banc del nivell i després al del perfil
  (`load_bank`, `has_bank`, `bank_left`, `pick_item`, `answer_and_record`,
  `_bank_index`). Totes les ordres del CLI i `read-db.py` passen `--data`, així
  que el servidor no canvia.
- **Web:** Stats ja mostrava les competències no-core amb el xip «extra»; la
  secció «Extra» surt sola.
- **Afegir-ne una:** plantilla a `curriculum/extras/<id>/` (`extra.md` + `<id>.json`),
  i `python3 scripts/flowed-extra.py add <perfil> curriculum/extras/<id>`
  (idempotent). `list <perfil>` mostra les que té.
- **Primera:** `x.good_luck_babe` (25 ítems, `validated`, per revisar): vocabulari
  de la cançó i A1 lligat (to be, can, want/need, his/her, plurals, -s). Només
  fragments curts de la lletra; la frase explícita, fora.
- **Proves:** `tests/test_profile_extras.py`.

## G.18 `flowed-web.sh` sol ja segueix el port de l'`.env` (2026-09-27)

Engegada sola (sense `flowed-start.sh`), una web no rebia `FLOWED_DEEP_BASE_URL`
i el servidor parlava amb el port de `config/fluent.json` (12322, railab), fos
quin fos el de l'`.env`. Ara `flowed-web.sh` el deriva de `FLOWED_DEEP_PORT`
com fa l'start. Motiu: el *tutor bench* (MODELBENCH.md) engega una web de prova
a part.

## G.19 El que l'alumne veu: escriptures estranyes, `{❌}` i correcció amagada (2026-09-27)

Trobat pel *tutor bench* (MODELBENCH.md), arreglat al servidor, per a qualsevol model:

- **`{❌}`** (14B): `stripTemplateBraces` a `tidyTutorText` — claus al voltant de
  res amb lletres (`{❌}`, `{8/10}`) es desfan; `{Target}` no es toca.
- **Escriptura no llatina** (14B, Reading: «滑梯» dins d'un text d'A1 i una
  pregunta sobre aquella paraula): `foreignScriptGuard` és el primer de la
  cadena de guardes i demana reescriure el torn; si la reescriptura encara en
  porta, `repairShownText` treu els caràcters i endreça la puntuació. Les
  escriptures de la llengua meta o nativa de l'alumne es respecten.
- **Correcció amagada** (27B: puntua a `fluent_record_answer` i a pantalla només
  «Waiting for your answer! ⏱️»): si hi ha resposta al davant, crida a l'eina i
  cap text del torn porta puntuació, `repairShownText` hi posa davant
  `feedbackFromRecord` (correccions + **Score: N/10**, marcador alineat).
- Proves: `server/test/shown-text.test.ts`.

## G.20 Menys crides per torn a les pràctiques obertes (2026-09-29)

Del *tutor bench* a la 4060 Ti (MODELBENCH.md): el temps no és del model, és de
quantes vegades l'app el fa rellegir un prompt de ~17k tokens.

- **Sense `fluent_record_answer` a Speaking/Writing/Reading.** `toolsFor()` no
  l'ofereix quan `currentCommand` és una pràctica oberta, i `buildSystemPrompt`
  hi afegeix l'últim bloc: el servidor registra la resposta a partir del text
  (`deriveRecord`), no cridis l'eina, mostra `**Score: N/10**` i les correccions
  i continua al mateix missatge. Una crida per torn en lloc de dues; la nota
  guardada és la que es veu (el 27B no coincidia 5 de 17 vegades). Go/Review
  (banc) i Vocab no canvien.
- **Salutació ≠ exercici.** `collectPlainQuestion` prenia «Hello, Test!» sota
  l'encapçalament d'obertura de Speaking com a pregunta feta, i cada sessió nova
  del dia es reescrivia per «already asked hello, test». Sota l'encapçalament
  d'obertura ara només compta una línia que acaba en «?», i les salutacions mai.
- Proves: `server/test/shown-text.test.ts`.
