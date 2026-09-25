# Fluent v2 — Registre de canvis (dual-model / dev-mode / web)

Log canvi a canvi. Cada entrada: fitxer, què canvia, per què, i com es
verifica.

---

## 2026-08-26 (II) — Bucle de l'eina deep + bug de la web (bomba doble, dev mode per herència)

Motiu: a la web (sessió real de Alex, 17:05–17:11), després d'un
`/fluent-learn` el 27B va cridar `fluent_deep_evaluate` **7 vegades amb
contingut placeholder** (`PLACEHOLDER`, `test`, `x`, `n/a`, `ignore`,
`stop`, `final`) — ~18 s per crida (cada crida és una inferència completa
del mateix 27B) → 2 min d'espera, i la interfície mostrava el nom de l'eina
7 vegades. A més, cada resposta de l'aprenent apareixia **doblada** a la
interfície, i l'instància web arrencada des de la shell de l'app desktop
anava en **dev mode** (paper de tutor amagat).

### `.opencode/plugins/fluent.js` — guards anti-bucle (A1)
- `isRealAnswer()`: rebutja respostes buides (<3 caràcters) o omplidores
  (`PLACEHOLDER|todo|n/a|test|ignore|stop|final|…` — la llista ve dels 7
  casos reals observats al log). Sense cap crida al deep (~0 s per crida
  falsa; abans cada una costava ~18 s).
- Guard de quota: **màxim 1 avaluació real per missatge d'assistant**
  (per `messageID`); les crides amb placeholder no consumeixen la quota
  (sinó una crida falsa bloquejaria la real del mateix torn).
- Descripció de l'eina: "at most ONCE, only with the real
  already-submitted answer — never with placeholder content".

### `.opencode/commands/fluent-{learn,speaking,writing}.md` — regla explícita (A2)
"Màxim 1 crida, només amb la resposta real de l'aprenent — mai amb
contingut placeholder, hipotètic o inventat".

### `web/app.js` — bomba d'usuari doblada (D)
`send()` dibuixa una bomba optimista i guarda `pendingUser`. L'esdeveniment
SSE `message.updated` arriba **sense parts** (el text ve després, en
`message.part.updated`), de manera que la comparació de textos per no
duplicar comparava `""` amb el text real → creava una segona bomba.
Arregl: a `ensureMsg`, si no hi ha parts s'adopta la bomba optimista sense
comparar (les envios es serialitzen: mai n'hi ha més d'una pendent); amb
parts (safety-poll/historial) la comparació es manté com a guarda contra
missatges antics.

### `web/app.js` — chip amigable (C)
El chip de `fluent_deep_evaluate` passa de mostrar el nom cru a
"avaluant resposta" (+ comptador si hi ha més d'una crida al mateix
missatge).

### `scripts/flowed-web.sh` (v1 i v2) — sanejament d'entorn
El serve heretava l'entorn de la shell que l'arrencava. Des de l'app
desktop (`OPENCODE_CLIENT=desktop`, `XDG_STATE_HOME=…ai.opencode.desktop`)
el plugin activava **dev mode** → a la web es treia el paper de tutor
(AGENTS.md) del system prompt. Ara: `env -u OPENCODE_CLIENT -u
XDG_STATE_HOME FLUENT_DEV=0` en arrencar el serve (modes `--web` i
`--app`).

**Verificació (2026-08-26):**
- Harness (node): els 7 placeholders observats + buit → `DEEP UNAVAILABLE`
  sense cridar el deep; resposta real → avaluació real del 27B; 2a crida
  real al mateix torn → bloquejada per la quota.
- Web re-arrancada (mateixa password via `FLUENT_WEB_PASSWORD`): log
  `fluent-hooks initialized (client=cli devMode=false shell=yes)`; entorn
  del serve sense `OPENCODE_CLIENT`/`XDG_STATE_HOME`.
- E2E: POST `/session/:id/message` (learner) → resposta de tutor ("Hola
  Alex! … 21 reviews due"), ~45 s amb context complet.
- `node --check` OK a `fluent.js` i `app.js`; `bash -n` OK al script.

## 2026-08-26 — Resolució de model independent: provider `fluent-deep` (alias `deep` al port 12321)

Motiu: després del canvi del 2026-08-25 al config global
`~/.config/opencode/opencode.jsonc` (provider `llama-local` → `vllm-local`),
tots els turns amb el 27B a la web fallaven amb HTTP 500
`ProviderModelNotFoundError: llama-local/...`. Els agents tenien el provider +
path del model **hardcodejats del config global**, de manera que qualsevol
experiment del propietari allà trencava fluent.

**Contracte:** el model deep sempre està a `127.0.0.1:12321` i fluent l'anomena
`deep`. Amb llama.cpp no cal fer res (accepta qualsevol nom de model a la
petició — verificat empíricament amb completions de prova); amb **vLLM** cal
llançar-lo amb `--served-model-name deep` (vLLM sí que valida el nom).

### `opencode.json` (v1 i v2)
Provider de projecte **nou** `fluent-deep` (baseURL
`http://127.0.0.1:12321/v1`, clau de model `deep`, amb el mateix
`tool_parsing`/`parameters` que abans). El config de projecte és independent
del global: canviar el config global (proveïdors, models, experiments) ja no
afecta a fluent.

### `.opencode/agent/tutor.md` i `learner.md` (v1 i v2)
`model: llama-local//...` → `model: fluent-deep/deep`. El `tutor-fast.md` no es
toca (`llama-face/...` — mateix patró, model fix).

### `scripts/flowed-web.sh` (v1 i v2)
A l'arrencar, mostra l'estat dels models (només informatiu, **no** arrenca ni
atura res): `deep (12321)` i `face (12322)` — OK / NOT RUNNING. Ports
sobrescriptibles amb `FLUENT_DEEP_PORT` / `FLUENT_FACE_PORT`.

**Verificació (web real 4100, 2026-08-26):**
- POST `/session/:id/message` (agent learner) → `providerID: fluent-deep`,
  `modelID: deep`, resposta correcta (~22 s amb context).
- POST `/session/:id/command` `fluent-vocab` → rutejat a `tutor-fast` →
  `llama-face`/omnicoder-9b, ~9 s, llegeix la BD de la Alex (21 ítems
  pendents).
- `scripts/flowed-web.sh --app alex-en` imprimeix `deep — OK` i `face — OK`.
- Canviar de model al 12321 (qualsevol GGUF amb llama.cpp) **no requereix cap
  canvi** a fluent.

---

## 2026-08-22 — Latència: context reduït + model "face" per a turns curts + comptador "pensant…"

Motiu: amb el model gran (27B), el primer caràcter trignava 15–40 s (prefill
de ~65k tokens: 2 docs de paper de tutor ~31KB + `read-db.py` amb les 6 BDs
completes ~33KB + història creixent). La UI semblava morta.

**Front 1 — context (~65k → ~14-20k tokens):**

### `AGENTS.md` (v1 i v2, reescrit)
Fusiona l'`AGENTS.md` antic (13.7KB) + `LEARNING_SYSTEM.md` (18KB) en un sol
paper de ~6KB amb el mateix contingut operatiu (protocol, feedback, SM-2,
result files, regles). `LEARNING_SYSTEM.md` queda a disc com a referència.

### `opencode.json` (v1 i v2)
Eliminat `"instructions": ["LEARNING_SYSTEM.md"]` (ja està al AGENTS.md, que
opencode carrega sols). V1: afegit el provider `llama-face` (idèntic al de v2).

### `hooks/read-db.py` (v1 i v2)
Mode **compacte per defecte** (~11KB vs 33KB amb la alex-en): essencials del
perfil, reviews pendents **amb content/answer** (permeter repassar sense
re-lluir fitxers), top-5 patrons febles amb últim exemple, mastery, stats i
`computed.next_session_id` (mateixa forma que abans). `--full` retorna les 6
BDs completes (setup/debug).

**Front 2 — model face per a turns curts:**

### `scripts/llama-face.sh` (v1 nou / v2 actualitzat)
Llançador del servidor face. **Fix:** el GPU per defecte és ara `1` — a
aquesta màquina l'índex CUDA no coincideix amb el de `nvidia-smi`
(CUDA 0 = RTX 4090 ocupada amb el 27B; CUDA 1 = RTX 3090 lliure). Verificat
amb un test de CUDA compilat (`cudaGetDeviceCount`/`cudaMalloc` per GPU).

### `.opencode/agent/tutor-fast.md` (nou, v1 i v2)
Agent amb la mateixa persona tutor però `model:
llama-face//home/albert/aidev/models/omnicoder-9b-q4_k_m.gguf` (RTX 3090,
ctx 32k al 12322).

### `.opencode/commands/fluent-{vocab,review,progress,setup}.md` (v1 i v2)
`agent: tutor` → `agent: tutor-fast`. Les altres comandes (learn/writing/
speaking/reading/use) queden al `tutor` (27B). Verificat que el `agent:` del
frontmatter de la comanda guanya sobre el paràmetre `agent` de la petició
POST /command (el web envia `agent: learner`): el missatge resultant porta
`providerID: llama-face`.

**Front 3 — UI:**

### `web/app.js` (v1 i v2)
El placeholder del missatge d'assistència és ara un comptador en viu
`pensant… N s` (tick 1 s) fins que arriba el primer part; es neteja també en
cas d'error; s'afegeix una pista d'ús únic (localStorage) al primer turn.

**Verificació:**
- `opencode run --command fluent-vocab` (face, entorn alex-en): skill +
  read-db compacte + salutació + 1a paraula en **~7.5 s** de punta a punta.
- E2E Chrome headless (CDP) contra la web: `/fluent-vocab` primer contingut en
  **3 s**; xat (27B) en **9 s** (abans 36 s); comptador visible i substituït
  pel contingut; 0 errors de consola, 0 falles de xarxa.
- `python3 tests/test_update_db.py` → 12/12 OK (sense `FLUENT_DATA_DIR` a
  l'entorn; amb la variable assenyalant un directori buit els tests fallen per
  disseny — l'env de la sessió de desenvolupament ho contaminava).
- Face: TTFT ~0.1 s, ~110 tok/s de generació; servidor actiu al 12322 (GPU 1).

**Com revertir:** restaurar `AGENTS.md`/`LEARNING_SYSTEM.md` antics +
`"instructions"`, `read-db.py` antic (sense `--full`), esborrar
`tutor-fast.md`, restaurar `agent: tutor` a les 4 comandes, aturar el face
(`scripts/llama-face.sh --stop`). El fix del GPU a `llama-face.sh` es manté.

---

## 2026-08-22 — Web: l'SSE mor cada ~20 s (ERR_INCOMPLETE_CHUNKED_ENCODING) → "…" etern

Síntoma: la UI nova (render incremental) mostrava `…` per sempre; al DevTools,
`eventsource`/`event` en **failed** amb `ERR_INCOMPLETE_CHUNKED_ENCODING`, mentre
`message?limit=60` (polling) respondia 200.

Causa arrel (dues, en cascada):
1. **`Bun.serve` tanca les connexions inactives a 10 s** (per defecte; també en
   mig d'un streaming). El proxy servia `/api/event` (SSE) amb `fetch` +
   `new Response(upstream.body)`: els heartbeats d'opencode arriben cada ~10 s
   (límit exacte → la connexió moria al cap de 1 heartbeat, ~20 s). Els POST
   bloquejants de missatge (30 s+ de prefill sense escriure cap byte) també
   s'hi escapatxaven. Verificat: `Bun.fetch` (client) NO té timeout (stream de
   110 s amb buits de 30 s); el culpable és exclusivament el `idleTimeout` del
   servidor.
2. **`ensureMsg()` feia early-return** si el missatge ja estava renderitzat: el
   polling de seguretat (cada 5 s) creava el placeholder `…` i després ja no
   aplicava mai les parts que arribaven. Només l'SSE actualitzava un missatge
   ja renderitzat → amb l'SSE mort, `…` etern.

### `scripts/flowed-web-proxy.mjs` (v2 modificat, copiat a v1 — idèntics)

- `const server = serve(...)` + `server.timeout(req, 0)` per a cada request
  `/api/*`: desactiva el `idleTimeout` per a les peticions proxyades (SSE i
  POSTs llargs).

### `web/app.js` (v2 modificat, copiat a v1 — idèntics)

- `ensureMsg()`: si el missatge ja està renderitzat, **re-aplica les parts**
  (`applyPart` és idempotent), de manera que el polling de seguretat pugui
  actualitzar el placeholder `…`. També mostra `info.error` si apareix després.

Verificació:
- SSE directe a `opencode serve`: 150 s, 15 heartbeats (OK).
- SSE **via proxy**: abans moria a 20 s (curl exit 18); amb el fix, **150 s,
  15 events** (igual que directe).
- E2E amb Chrome headless (CDP, `node /tmp/cdp-e2e.mjs`): missatge de xat →
  `…` a 2 s, chip `✓ bash` a 10 s (streaming en viu), **text complet a 24 s**;
  sense errors de consola ni falles de xarxa.

Nota: cal reiniciar la instància web perquè agafi el proxy nou
(`scripts/flowed-web.sh --stop --port 4100` i tornar a llançar-la).

---

## 2026-08-22 — Web UX: comandes com a chip + streaming robust (sync v1↔v2)

Problemes observats a la web (sessió `ses_fda6c6822ffe`, v1 amb `--app alex-en`):
1. Prem un botó (p. ex. "Aprèn") → l'app mostra el **prompt complet de la
   comanda** ("Execute /fluent-learn now: … + JSON de l'estat") com a missatge
   d'usuari: "text gegant", l'aprenent es desorienta.
2. Escriu "6" (mix adaptatiu, turn multi-tempsa amb `read`/`glob`) → l'app
   antiga (POST bloquejant + un sol re-render) només mostrava el primer chip
   `read`; el text final (generat, visible a la DB) mai apareguia. A més,
   canviar de pestanya/pantalla **abortava** el turn en marxa.

### `web/app.js` (v2 modificat, copiat a v1 — els dos idèntics)

1. **`userBubbleHTML()`**: els missatges d'usuari que comencen per
   `Execute /fluent-…` (expansió de comanda) es renderitzen com un chip
   compacte (`🎲 /fluent-learn`, `📊 /fluent-progress`, …) en lloc del text
   complet. S'aplica a la via SSE i a la re-renderització de l'historial.
2. **Eliminat l'abort en `visibilitychange`**: bloquejar la pantalla o
   canviar de pestanya ja no mata el turn; el servidor el completa i, en
   tornar, SSE + polling de seguretat mostren el resultat.
3. `lastActivity = Date.now()` en `init()`: finestra de polling de seguretat
   de 15 s després de carregar la pàgina (per si el turn ja estava en marxa).

Verificat e2e (v1, `--app alex-en`, port 4100): `/fluent-learn` → 881
`message.part.delta` en viu + resposta `{info, parts}` amb el text; turn "6"
multi-tempsa (88 s, 9 crides d'eina) → **4681** `part.delta` en viu i el text
final complet. `node --check` OK als dos app.js.

### `.opencode/agent/learner.md` (v1 i v2)

- Afegit permís `cat /…/fluent/.fluent-active*` (camin absolut; el relatiu
  amb `|| echo` es bloquejava per la descomposició de la comanda composta).
- Pista al prompt: llegir `.fluent-active` amb l'eina `read` (les comandes
  `bash` compostes estan bloquejades).

### `docs/MANUAL.md` (v2)

- Secció 2.1: comportament de la interfície (streaming, chips, equivalència
  botons↔menú) i aclariment del botó `👤 Perfil` / `fluent-use`.

---

## 2026-08-22 — Fix definitiu del plugin + web en viu + docs

### `.opencode/plugins/fluent.js` (modificat)

1. **Fix d'un error de sintaxi que feia fallar el mòdul sencer (silenciós):**
   `async execute(args, context) => {` (barreja invàlida de mètode i fletxa)
   → `execute: async (args, context) => {`. Fins aleshores cap server nou
   carregava el plugin (cap eina ni hook); només les instàncies amb el
   còdig antic a la memòria (desktop) el tenien actiu.
2. **`export default FluentHooks`** al final del fitxer. El loader 1.18.21
   registra fiablement el factory com a *default export*; amb exports només
   de nom la eina no apareixia (verificat amb un projecte de prova:
   `test_ping` amb default export sí; sense, no).
3. **`resolveDataDir` privat** (eliminat l'`export`): el loader invoca cada
   export function com a plugin; cridat amb `(input, options)` llançava
   `The "path" argument must be of type string` i descartava el plugin
   (error visible al log: `failed to load plugin`).
4. **`loadDeepConfig(root)`**: abans referenciava `root` fora d'escop
   (`ReferenceError` capturat → sempre feia fallback als defaults, ignorant
   `fluent-models.json`). Ara rep `root` com a paràmetre.

### `web/app.js` (reescrit)

De redibuix sencer post-torn a **render incremental + streaming en viu**:

- Maps `renderedMsgs` (mid → div + parts) i `pendingParts` (parts que
  arriben abans del seu `message.updated`).
- `ensureMsg(info, parts)` deduplica per `info.id`; `applyPart` afegeix/
  actualitza parts (text amb re-render `md()`, tool com a chip); placeholder
  `…` fins la primera part visible.
- `appendAssistant(res)` consumeix la resposta bloquejant `{info, parts}`
  (verificada real) amb fallback a `refresh()`.
- `EventSource /api/event`: `message.updated`, `message.part.updated`,
  `message.part.delta` (tokens en viu), `message.removed`, `session.idle`,
  `session.error`; reconexió amb backoff; filtra per `sessionID`.
- Missatge d'usuari optimista (`pendingUser`) confirmat pel SSE o descartat
  si el POST falla.
- Polling de seguretat cada 5 s només amb torn actiu (+15 s de drenatge).

### `tests/test_update_db.py` (modificat)

- `_run` ara passa un `env` netejat de `FLUENT_DATA_DIR`,
  `CLAUDE_PROJECT_DIR` i `CLAUDE_PLUGIN_ROOT`. Sense això, en un shell que
  hereta aquests env (p. ex. una sessió opencode desktop), els 11/12 tests
  apuntaven al data dir del host en lloc dels fixtures del tmpdir.

### `docs/dual-model/` (nou)

- `PLAN.md` — arquitectura fast/deep, eina, routing, mode dev, web en viu,
  criteris de verificació, riscos (inclòs el gotxa del loader de plugins).
- `CHANGES.md` — aquest registre.

### `README.md` (modificat)

- Taula de peces: el plugin també registra `fluent_deep_evaluate`.
- Nota de model: referència a `docs/dual-model/PLAN.md` per a l'arquitectura
  de doble model i al canvi del model deep.

### Verificacions fetes (2026-08-22)

- `python3 tests/test_update_db.py` → **12/12 OK**.
- `node --check web/app.js` → sintaxi OK.
- Headless (`opencode run` amb env neteja): la llista d'eines inclou
  `fluent_deep_evaluate`; cridar l'eina amb una traducció al francès va
  fer un `POST` real al model deep (12321) i va tornar
  `SCORE / CORRECT VERSION / FEEDBACK` correctes (e.g. 10/10 per
  «Je suis allé au marché hier»).
- Harness Bun directe sobre el plugin: `default export` és function; hooks
  `tool`, `shell.env`, `tool.execute.after`, `event`,
  `experimental.chat.system.transform`, `experimental.session.compacting`;
  `execute` de l'eina respon amb la rubric completa.
- Web `scripts/flowed-web.sh --app` (port 4100): pàgina estàtica OK,
  `/api/global/health` OK, sessió creada, POST de missatge → resposta
  `{info, parts}` (parts: step-start/reasoning/text/step-finish) i el
  `/api/event` va emetre `message.part.delta` (639), `message.part.updated`
  (7), `message.updated` (6, user+assistant) i `session.idle` (1).
  Instància aturada després de la prova.

### Com revertir

- Plugin: `git` no s'usa en v2; el còpia anterior (amb els exports antics)
  es conserva a `tmpjson/` només per a `opencode.json`/`AGENTS.md`. Per
  revertir el plugin, restaurar la versió anterior de
  `.opencode/plugins/fluent.js` (tenia l'eina però amb els tres defectes de
  càrrega documentats a dalt).
- Web: la versió anterior d'`app.js` (redibuix sencer) és la mateixa del
  v1: `/media/albert/railab2/projects/fluent/web/app.js`.
