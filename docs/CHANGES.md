# Fluent — Registre de canvis

Log canvi a canvi. Cada entrada: fitxer, què canvia, per què, i com es
verifica. Els canvis majors tenen una secció dedicada a `docs/MANUAL.md`.

---

## 2026-09-08 — Scripts unificats: `.env` + `fluent-start/stop` + `scripts/models/`

### Context / objectiu

Hi havia 4 orquestradors solapats (`fluent-up.sh`, `scripts/4060/`, `alexup.sh`,
`docker/`) amb lògica duplicada i rutes mortes. Unificar en un sol esquema
parametritzable que serveixi aquí (railab) i a la 4060.

### Decisions de disseny

- **`.env` viu + `.env.railab` / `.env.rapve`** (`cp` per canviar de màquina):
  deep (model/port/GPU/ctx/managed/backend), face (on/off), webs
  (`"alex-en:4100 sam-en:4101 demo-en:4102"`). CLI/entorn mana sobre el fitxer
  (carregador sense trepitjar).
- **`scripts/models/`**: 6 llançadors (`docker-llama.sh` inclòs; `ROOT`
  arreglat a doble `dirname`, rutes `scripts/models/`). Cridades sols, sense
  l'start.
- **`flowed-start.sh` / `flowed-stop.sh`**: lògica de `fluent-up.sh`
  generalitzada (`--dry-run`, `--gpu`, `--models/--webs-only`, detecció amb
  neteja de rancis, guàrdia GPU, espera de ports). `BACKEND=native|docker`:
  amb `docker`, l'start crida `docker-llama.sh` (llegeix `FLUENT_DEEP_*`);
  l'stop Docker va per `docker stop` (matar per port mataria el docker-proxy).
- **Orfes per port**: tots els `--stop` (models i webs) maten pidfile +
  qualsevol procés escoltant el port (TERM→espera→KILL). Trobat en validar:
  un `llama-server` orfe de 4 h retenia el 12322.
- Retirats: `fluent-up.sh`, `scripts/4060/`, `alexup.sh`, `docker/`.
  MANUAL §1.7–1.8 reescrits.

Verificat: `bash -n` tot, `--dry-run` normal i rapve-simulada, cicle
stop→start real (deep Q4 + 3 webs, logins per nom OK).

## 2026-09-08 — Mode friend v0.3 (opt-in per alumne) + `flowed-friend.sh`

### Context / objectiu

El tutor coneixia l'alumne pedagògicament (errors, nivell, ratxa) però no
biogràficament. Afegir calidesa (cita última sessió, usa interessos) sense
trencar res i sense matar la 4060, amb rollback garantit.

### Decisions de disseny

- Flag `preferences.tutor_style` (`friend`/absent=clàssic) + `interests[]`
  (max 3) + `about` (1 línia): camps opcionals, cap migració. Toggle amb
  `scripts/flowed-friend.sh <id> [on|off|status]` (`off` = clau eliminada,
  perfil byte-idèntic verificat en 3 perfils).
- Únic toc de codi: allowlist del compacte `read-db.py` (+3 camps).
  Prompts: bloc FRIEND condicional a `tutor.md`, salutació `learn` §3 (P.S.
  final), 1 línia a `vocab`/`speaking`/`reading`. Setup pregunta amb topall.
- Cost: ~250 tokens/torn (+0.5–2% temps), 0 VRAM (KV pre-reservat).
- Lliçó: condicionals al PRINCIPI de plantilla s'ignoren (4 intents, Q4+Q6);
  al FINAL funcionen al primer intent. Versió 0.3.0.

Verificat: regressió clàssica byte-idèntica, P.S. friend real (Q4), `tsc` net.

## 2026-09-07 — Ports 12322/12323, fallback face→deep, auth per nom, neteja UI

### Context / objectiu

Alliberar el 12321 (ús independent de l'usuari), fer el face opcional de
debò, login humà per a l'alumnat i treure soroll de la UI.

### Decisions de disseny

- Deep 12321→**12322**, face→**12323** (tots els candidats face el
  comparteixen; `llama-face.sh` → `llama-omnicoder.sh` legacy).
  `opencode.json`, `server/src/index.ts` (+override `face` a
  `fluent-models.json`), `tutor-fast.md`, `flowed-web.sh`.
- **Fallback** (`agent.ts` `resolveModel` + reintent al `catch`): sense face,
  `tutor-fast` corre amb deep (només log). E2: bateria fast 5–15 s amb deep
  sol a la 3090 → face arxivable en la pràctica.
- **Auth**: usuari = nom en minúscules (`nes`…), legacy `opencode` acceptat
  (`http.ts` + `resolveLoginName` + missatges `flowed-web.sh`). Passwords
  intactes.
- **UI**: xip icona sola + `skill`/`bash` amagats + mode debug (`?debug=1`,
  triple-clic), ➤ buit = `next` només si el tutor no espera resposta
  (etiquetes de flux), CTA de tancament obert als 6 skills + progress,
  títol/versió.
- **Robustesa stop/start**: preflight (1 s vs 20 s), neteja de pidfiles
  rancis, kill+neteja en fallar, detecció amb `kill -0`.
- **Config fora de `.opencode`**: `config/fluent-models.json` (+`.example`),
  ordre defaults ← legacy ← `config/` ← `$FLUENT_MODELS_FILE`.

Verificat: e2e scratch (fallback, routing face/deep), `tsc` + `bash -n`,
saluts amb ambdós logins, `fluent_dev` intacte després de cada ronda.

---

## 2026-09-05 — Locks advisorials per als escriptors de les 6 DB

### Context / objectiu

Cada fitxer JSON ja s'escrivia de manera atòmica (`tmp` + `fsync` +
`os.replace`), però una sessió fa un **read-modify-write repartit en 6
fitxers**. Dos `update-db.py` concurrents (idle hook, sweeper del servidor o
persistència manual) podien carregar l'estat antiga i perdre una aplicació.

Aquest canvi afegeix un lock advisory per serialitzar els escriptors de les 6
DB sense canviar el punt 1 de coherència/lectura.

### Decisions de disseny

- **Lock advisory amb `fcntl.flock`** sobre `<data-dir>/.db.lock`. És
  cooperatiu entre els scripts de Fluent i no bloqueja processos aliens.
- **Alliberament automàtic**: si el procés que manté el lock mor, el SO
  allibera el lock; no queda un fitxer de lock obsolet bloquejant el sistema.
- **Timeout configurable** amb `FLUENT_DB_LOCK_TIMEOUT` (default `10` segons).
  En timeout, l'escriptor surt amb `2` i no muta els JSON.
- **Escriptors protegits**: `update-db.py` i `scripts/migrate-db.py` en mode
  escriptor. `--check` de `migrate-db.py` no adquireix lock i no crea
  `.db.lock`.
- **`read-db.py` no modificat**: segueix fent lectures sense lock, tal com es
  va decidir no tocar el punt 1.

### Canvis per fitxer

| Fitxer | Què canvia | Per què |
|---|---|---|
| `hooks/db_lock.py` (NOU) | Context manager `data_lock()` amb `fcntl.flock`, fallback no-op si no hi ha `fcntl`, timeout via env. | Reutilitzable per als scripts escriptors. |
| `hooks/update-db.py` | Adquireix el lock exclusiu just abans de carregar les DB i el manté fins a la sortida del procés. Timeout → `2`. | Evita perdre aplicacions entre dues execucions concurrents. |
| `scripts/migrate-db.py` | Adquireix el lock exclusiu només en mode migració, abans de carregar/escriure DB. Timeout → `2`. | Evita migrar mentre un `update-db.py` està escrivint. |
| `tests/test_db_lock.py` (NOU) | Proves de bloqueig, timeout, execucions concurrents i que `.db.lock` no va als backups. | Verifica el comportament del lock. |
| `tests/test_migrate_db.py` | Proves que `--check` no crea lock i que migrate respecta el timeout. | Verifica el nou comportament del migrator. |

### Com es verifica

1. `python3 -m unittest discover -s tests -q` → **62/62 OK**.
2. `python3 -m py_compile hooks/db_lock.py hooks/update-db.py
   scripts/migrate-db.py tests/test_db_lock.py tests/test_migrate_db.py` → OK.
3. Un lock aguantat externament fa que `update-db.py` i `migrate-db.py`
   surtin amb `2` amb `FLUENT_DB_LOCK_TIMEOUT=0.1`.
4. Dues execucions concurrents de `update-db.py` amb dos `session_id`
   diferents queden les dues aplicades.

---

## 2026-08-30 — `results/` per-usuari + `fluent` com a workspace de dev inert

### Context / objectiu

Separar clarament el **codi** del **dades** i el **desenvolupament** de la
**producció**:

- `fluent` passa a ser el directori de **desenvolupament inert**: no actua de
  tutor, no escriu dades, no genera resultats de sessió.
- `fluent_learn` és l'**app d'aprenentatge activa** (còpia exacta i
  independent de `fluent`).
- Les **dades i els `results/`** viuen per-usuari a `~/.fluent/<id>/`,
  completament **fora del projecte** (ja ho feien els 6 JSON; ara també els
  fitxers de resultat de sessió).

### Decisións de disseny

- **Sincronització manual**: producció = "còpia de tot el projecte +
  esborrar el marcador `.fluent-dev`". Al copiar, l'app activa llegeix les
  dades de `~/.fluent/<id>/`, que estan fora del repo.
- Els perfils (6 JSON) ja eren externs (`~/.fluent/<id>/`); amb aquest canvi
  els **results de sessió** passen a viure al mateix lloc.
- `fluent/results/` (abans del projecte) es buida a `obsolet/results/`
  (moviment, no còpia), igual que es va fer amb `data/`.

### Canvis per fitxer

| Fitxer | Què canvia | Per què |
|---|---|---|
| `hooks/persist-session.py` | `RESULTS_DIR` → `DEFAULT_RESULTS_DIR` (fallback a l'arrel del repo). `save_results_file()` ara rep `data_dir` i escriu a `~/.fluent/<id>/results/` quan el directori té `learner-profile.json`; `main()` li passa la `data_dir` resolta. | Els resultats de sessió van al perfil de l'aprenent, no al projecte. |
| `.opencode/agent/learner.md` | Permisos d'`edit` → `~/.fluent/**/*.json`, `~/.fluent/**/results/*.md`, `~/.fluent/**/.fluent-active`. `read: "*": allow`. `external_directory` → `"~/.fluent/**": allow, "*": deny`. Eliminats tots els paths de `fluent-v2`. | L'agent de la web escrivia els results; ara els escriu dins del perfil extern. |
| `.opencode/plugins/fluent.js` | `isDevMode(root)` detecta el marcador `.fluent-dev` a l'arrel (les 4 crides passen `root`). `session.idle` salta en dev. `session.compacting` en dev no fa precompact backup i només injecta context de dev. | Cada checkout pot triar dev (inert) o prod (tutor) amb un sol marcador. |
| `hooks/fluent_paths.py` | `data_dir()` ignora `FLUENT_DATA_DIR` si el directori no té `learner-profile.json`. | Evita fer servir directoris buits com a perfil actiu. |
| Docs i skills | `results/` → `~/.fluent/<id>/results/` a tots els commands, agents, skills i referències. Es manté el `{learner-slug}` al nom del fitxer (compatibilitat amb `session-log.json` i `fluent-session-analyzer`). | Coherència de paths per-usuari arreu. |
| `AGENTS.md` | Seccions de resultats de sessió actualitzades al path per-usuari. | Document de referència del tutor. |

### Nous fitxers

- `fluent/.fluent-dev` — **marcador buit** d'`isDevMode()`. La seva presència
  a l'arrel converteix el checkout en un workspace de dev (inert).

### Migracions de dades

- Moguts els `results/*.md` existents al **perfil** de cada aprenent:
  - `~/.fluent/alex-en/results/` (sessions 001–004)
  - `~/.fluent/sam-en/results/` (sessions 001–004)
- Els originals de `fluent/results/` i `fluent/data/` → `fluent/obsolet/`
  (contingut històric, no actiu).

### Com es verifica

1. `python3 tests/test_update_db.py` → **12/12 OK** (no trenca els hooks).
2. `save_results_file(..., data_dir=perfil)` escriu a `~/.fluent/<id>/results/`
   i `save_results_file(..., data_dir=None)` a `fluent/results/` (fallback).
3. `read-db.py` a `fluent` (amb `.fluent-dev` i sense perfil) → perfil buit.
4. `node --check .opencode/plugins/fluent.js` → OK.
5. Cap referència residual a `fluent-v2` als fitxers actius.
6. Després de qualsevol canvi de plugin/config, **reinicieu opencode**.

---

## 2026-08-30 — Persistència automàtica i idempotent (per `session_id`)

### Context / objectiu

Fins ara la persistència de la sessió **depenia del tutor**: havia de carregar
la skill `fluent-db-updater` i cridar `update-db.py` manualment al final. Si
fallava (context ple, tanca finestra, model mort) les dades es perdien, i a
més l'espera de la crida manual (inferència sencera del model) feia que
l'usuari esperès.

Objectiu: persistir **cada resposta graduada de manera automàtica i invisible**
(disparada pel `session.idle` del plugin, sense pausa ni chip per a
l'aprenent), **idempotent per `session_id`** (cada aplicació del mateix
`sessio` reemplaça, mai no afegeix en duplicat).

### Decisions de disseny

- **Dos nivells de persistència**:
  1. **Automàtic per-resposta (capa A)**: el `session.idle` crida
     `accumulate-session.py`, que afegeix el feedback ja graduat
     (`Score: X/10`) al `session-draft.json` i aplica **el payload complet
     acumulat** amb `update-db.py`. Idempotent → segur a cada idle.
  2. **Finalització del tutor (capa B)**: al final real, `persist-session.py`
     re-persisteix/assenta el mateix `session_id` i afegeix la metadada rica
     (new vocab complet, `review_results` per SM-2, milestones, durada).
- **`update-db.py` es torna idempotent per `session_id`**: guarda un snapshot
  de l'estat **T0 (pre-sessió)** en un sidecar `.update-state/<sid>.json`. Si
  el `session_id` ja s'havia aplicat, restaura T0 i re-aplica el payload
  acumulat; el backup `pre-update-<sid>` només es fa a la primera aplicació.
- **High-water-mark (`--dry-run` no muta)**: l'helper recorda el `rowid` màxim
  processat; les crides següents només acumulen el que és nou. En `--dry-run`
  no avança l'estat (no escriu el draft).
- **`--dir` opcional**: l'helper fa fallback a `$FLUENT_DATA_DIR`, que el
  plugin ja resol via `shell.env` → el ganxo el crida sense arguments.

### Canvis per fitxer

| Fitxer | Què canvia | Per què |
|---|---|---|
| `hooks/update-db.py` | Idempotent per `session_id`: `STATE_DIR_NAME = ".update-state"`, `state_path()`/`save_state()`/`load_state()`. A `main()`, si el `session_id` ja es va aplicar (sidecar existeix) restaura T0 i re-aplica; si no, `save_state` i aplica. `backup_all("pre-update-<sid>")` només a la primera aplicació. | Re-aplicar el mateix payload moltes vegades (idle + final) no duplica comptadors, sessions, mistakes ni SM-2. |
| `hooks/accumulate-session.py` (NOU) | Helper incrementable. Carrega `persist-session.py` com a mòdul (`importlib`, el nom té guions) per reutilitzar `resolve_opencode_db`, `find_session`, `parse_*`. `extract_graded_with_rowids()` (SQLite, `json_extract` + `SCORE_RE` = `\*\*Score:\s*(\d+)/10\*\*`). Manté `session-draft.json` amb `high_water_mark`. Crida `update-db.py` amb el payload acumulat. `--dry-run` no escriu. | Persistir cada resposta de manera invisible i incremental al `session.idle`. |
| `.opencode/plugins/fluent.js` | A `session.idle`, en mode no-dev, crida `accumulate-session.py` (sense stdin, via `FLUENT_DATA_DIR`) **abans** del guard del backup diari, a **cada** idle. | Cada res resolució ja graduada es persisteix sense pausa visible; el backup diari es manté com a copia de seguretat. |
| `skills/fluent-db-updater/SKILL.md` | Reescrit: model de 2 capes (auto per-resposta + finalització). "Call once per session" → "finalitzeu amb rich metadata"; repeticions del mateix `session_id` són idempotents i segures. | El tutor ja no és el camí de persistència principal; només afegeix metadada al final. |
| `AGENTS.md` | "Persist after every answer" (línia 32) i "ONE command at session end" (36–38/110) resolts: la persistència és automàtica a `session.idle`; el tutor finalitza amb UNA comanda al final. | Eliminar la contradicció i reflectir la nova realitat (auto acumulació + assentament final). |

### Nous fitxers

- `hooks/accumulate-session.py` — helper d'acumulació incremental.
- (Sidecars en runtime, per-usuari): `~/.fluent/<id>/session-draft.json` i
  `~/.fluent/<id>/.update-state/<sid>.json`.

### Com es verifica

1. `python3 -m unittest discover -s tests` → **14/14 OK** (2 tests nous a
   `tests/test_update_db.py`, classe `UpdateDbIdempotencyTest`:
   `test_apply_same_payload_thrice_is_idempotent` i
   `test_growing_payload_equals_single_full_apply`).
2. `node --check .opencode/plugins/fluent.js` → OK.
3. `python3 hooks/accumulate-session.py --help` → `--dir` opcional.
4. **Prova sintètica punt a punt**: `opencode.db` amb 3 exercicis graduats;
   aplicar incrementalment (ex1+ex2, després ex3) produeix **BBDD idèntiques**
   a aplicar-ho d'una sola vegada (cap pèrdua, cap doble-compte).
5. **Aplicar el mateix payload 3 cops** → `verb_spreek` freq=1, una sola fila
   de sessió al `session-log`.
6. **Re-run sense feedback nou** → "no new graded feedback since last run"
   (el `high_water_mark` bloca re-processar).
7. Després de qualsevol canvi de plugin/config, **reinicieu opencode**.

> ⚠️ La prova **en viu** (arrencar `fluent_learn` sense el marcador
> `.fluent-dev` i fer una sessió curta per confirmar que el `session.idle`
> persisteix) queda **pendent de fer per l'usuari**.

---

## 2026-08-31 — Diagnòstic nes + `results/*.md` automàtic + bootstrap d'usuaris (setup validat)

### Context / objectiu

Tres frents:

1. **Per què `/fluent-learn` fallava a `nes` però no a `alex`** (mateix codi,
   mateix `learner.md` fixat). Causa real — **no era codi ni `learner.md`**:
   la web guarda la sessió activa a `localStorage` (`fluent.session`,
   `web/app.js`), i **per instància/perfil** (`~/.fluent/<id>/` té el seu propi
   `opencode.db`). `nes` reutilitzava una **sessió vella/penjada**
   (`ses_fb863baa…`), que feia `init count=1` + `UnknownError`; `alex` havia
   creat una sessió **nova** (`count=13`) i funcionava. **Fix: netejar
   `localStorage.fluent.session`** (o "Nova sessió") → es crea una sessió nova
   i funcional.
2. **"Acabar sessió = tancar el navegador" ja ho deixa tot fet** gràcies a la
   capa A, **menys** el fitxer `results/*.md`: ara la capa A també el genera.
3. **No existia cap via neta per provisionar un usuari nou** (ni script ni web
   d'"admin"): `flowed-web.sh` rebutja perfils sense `learner-profile.json`, i
   `data_dir()` ignora un `FLUENT_DATA_DIR` buit. Creat `scripts/new-user.sh`.

### Canvis

| Fitxer | Què canvia | Per què |
|---|---|---|
| `hooks/accumulate-session.py` | Després de `run_update_db` (exitos) crida `write_results_file(...)` → reutilitza `ps.save_results_file` per generar/refrescar `results/{slug}-fluent-learn-{sid}.md` al mateix perfil. Nou `_results_report` mapeja `errors[].pattern_id` → `id` (contracte de `save_results_file`). | La capa A deixa el resum de sessió fet automàticament: tancar el navegador ho persisteix tot, inclòs el fitxer de resultat. Reutilitza la funció existent → sense ús del model, determinista, ràpid. |
| `scripts/new-user.sh` (nou) | `scripts/new-user.sh <id> [--port N]`: valida l'`id`, rebutja perfils existents, crea `~/.fluent/<id>/` i seeda els 6 JSON de `data-examples/`, genera `.web-password` (600), imprimeix la comanda de llançament. | Tanca el gap d'**ou-i-gallina**: sense `learner-profile.json` no pots ni llançar la web ni resoldre `data_dir()`. El script provisiona el perfil perquè tot el sistema l'accepti; el primer `/fluent-setup` omple la identitat real. |

### Com es verifica

1. `python3 -m unittest discover -s tests` → **14/14 OK** (sense regressions).
2. `python3 -m py_compile hooks/accumulate-session.py` → OK.
3. `bash -n scripts/new-user.sh` → OK; `scripts/new-user.sh "bad id"` → exit 2.
4. `new-user.sh test-en --port 4102` → crea `~/.fluent/test-en/` amb els 6
   JSON + `.web-password`; `FLUENT_DATA_DIR=~/.fluent/test-en` → `data_dir()`
   retorna `~/.fluent/test-en` (el seed fa que el guard ho accepti).
5. Llançat `scripts/flowed-web.sh --app test-en --port 4102`; API
   `POST /session` + `POST /session/{id}/command {command:"fluent-learn"}`
   → **`init count=13`** i salutació del tutor ("Hello, Test! 👋") → el setup
   del perfil és **funcional de cap a cap** (el mateix `leaner.md` que fallava
   a `nes` ara funciona en un perfil net).
6. `write_results_file` (aïllat) genera correctament el `.md` a
   `~/.fluent/test-en/results/`.
7. La prova en viu de la capa A a `nes` (28 exercicis, 16 patrons, `session-001`
   sense duplicats, `high_water_mark` bloquejant re-runs) queda documentada a
   la secció 2.5 del `MANUAL.md`.

> Nota: `results/*.md` de la prova de `nes` encara es pot generar amb la capa B
> (`persist-session.py`) o bé sortirà automàticament en la propera sessió acti-
> va (ara la capa A el genera).

---

## 2026-08-31 — Setup automàtic per a usuaris nous (començar directe per `/fluent-setup`)

### Context / objectiu

Un usuari **nou** (acabat de crear amb `new-user.sh`) arrencava la web i
queia al menú de `/fluent-learn` amb un `learner-profile.json` placeholder, en
lloc de configurar-se primer. L'objectiu: si el perfil **no està configurat**,
en obrir la web ha d'anar **directe a `/fluent-setup`** sense que ningú
escrigui res. Els usuaris **ja configurats** no han de canviar de comportament.

S'ha resolt **per l'estat explícit del perfil** (`setup_complete`) + una
comprovació a la **web** (no al tutor ni al `learner.md`), per no tocar el flux
de pràctica.

### Canvis (a `fluent` i propagats a `fluent_learn`)

| Fitxer | Què canvia | Per què |
|---|---|---|
| `scripts/new-user.sh` | En seedar el perfil, afegeix `preferences.setup_complete: false` al `learner-profile.json`. | Marca el perfil com a "pendent de setup" perquè la web ho sàpiga. |
| `skills/fluent-setup/SKILL.md` | A l'**alta inicial**, escriure `preferences.setup_complete: true` al `learner-profile.json`. | En completar la configuració, el perfil passa a "configurat" (la web llavors arrenca `/fluent-learn`). |
| `scripts/flowed-web-proxy.mjs` | Endpoint reservat `GET /api/fluent/setup-state` (no es proxyïa cap a opencode): llegeix `<FLUENT_DATA_DIR>/learner-profile.json` i retorna `{ setup_complete: bool }`. **Fallback segur:** si el camp **no existeix** (perfils migrats com `alex`/`nes`/`sam`) → `true`; només `false` quan hi ha un `false` **explícit**. | Proveeix l'estat a la web sense cremar cap torn de model, protegint els usuaris existents. |
| `web/app.js` | Nova `initialCommand()`: consulta `setup-state` i tria `fluent-setup` (si `false`) o `fluent-learn` (si `true`); fallback a `fluent-learn` si l'endpoint falla. Aplicat a `init()` i `newSession()` (on abans s'auto-arrencava sempre `fluent-learn`). | Decidir el primer pas segons l'estat de configuració del perfil. |

### Com es verifica

1. `bash -n scripts/new-user.sh` → OK; `node --check web/app.js` → OK;
   `bun build scripts/flowed-web-proxy.mjs` → OK.
2. `new-user.sh` posa `setup_complete: false` (comprovat amb `curl` de
   `setup-state` = `false`).
3. **Prova integrada real:** perfil nou → obrir la web → es llança
   `/fluent-setup` automàticament i el tutor fa "Step 1: What's your name?".
4. **Perfils existents (sense flag o amb `true`):** `setup-state` = `true` →
   `/fluent-learn` com sempre (no es trenca res).
5. `python3 -m unittest discover -s tests` → **14/14 OK**.
6. Els 4 fitxers són **idèntics** entre `fluent` i `fluent_learn` (propagació
   verificada amb `diff -q`).

### Nota sobre l'update de setup

L'edició posterior del perfil **no** és una via visible per a l'usuari: es fa
amb **sessió nova + comanda `/fluent-setup`** (cas excepcional, no cal exposar-lo).

---

## 2026-09-04 — Versionat d'esquema + migracions + decay no-destructiu + tests i CI (`fluent_dev2`)

### Context / objectiu

Apliquem el pla recomanat de `docs/ARCHITECTURE-ANALYSIS.md` (bones pràctiques
d'Open Course) a la còpia `fluent_dev2`, amb criteri conservador i
**no-trencador**: dades existents sense `_schema_version` es llegeixen com a
v1, cap escrit nou trenca sessions antigues. Fora d'abast: UUIDv7 per a
`session_id` i sincronització Git automàtica.

### Canvis per fitxer

| Fitxer | Què canvia | Per què |
|---|---|---|
| `hooks/db_schema.py` (nou) | `CURRENT_SCHEMA_VERSION=1`, `DB_FILENAMES`, `get_schema_version` (absent = baseline 1), `is_current/is_future`, `MIGRATIONS`, `migrate_docs`, `stamp_docs`. | Helpers compartits per hooks i scripts. |
| `scripts/migrate-db.py` (nou) | CLI `--dir` / `--check`; backup a `<data>/.backups/pre-migration-<ts>/`; escriptura atòmica; exit `0` res/migrat, `1` drift, `2` error. `--check` marca drift també si falta el stamp. | Migrar esquemes amb segurança i idempotència. |
| `data-examples/*` | Les 6 plantilles porten `_schema_version: 1`. | Perfils nous neixen estampats. |
| `hooks/read-db.py` | Decay **no-destructiu** (`ranked_due_items`: boost de prioritat pels dies vençuts, `OVERDUE_BOOST_DAYS=14`, camps `days_overdue`/`effective_priority` només a la sortida); warnings `[Fluent]` de schema futur/antic i fitxers corruptes; exit `1` si en falta algun o hi ha warnings de schema. | Prioritzar repassos endarrerits sense mutar dades; fer visible l'esquema incompatible. |
| `hooks/update-db.py` | Refusa escriure sobre schema futur o antic (exit `2`, fitxers intactes); `traceback` als errors; `new_vocabulary` accepta camps opcionals `pos`/`cefr_level`/`forms` **només si el payload els porta**. | No corrompre dades d'una versió futura; vocabulari estructurat sense canviar items antics. |
| `hooks/persist-session.py` | Guard: si `opencode.db` no existeix, error `[Fluent] ❌ opencode.db not found` i exit `1` (abans `sqlite3.connect` creava un DB buit → error confús "no such table"). | Diagnòstic clar de paths dolents. |
| `hooks/accumulate-session.py` | Guard equivalent però surt amb `0`: hook best-effort, mai ha de bloquejar la sessió. | El decaïment del persist no pot trencar el tutor. |
| `tests/` | Nous: `test_fluent_paths.py`, `test_read_db.py`, `test_migrate_db.py`, `test_persist_session.py`; estesos: `test_update_db.py` (camps vocab opcionals + guard schema futur) i cleanup `_dump`. | 52 tests en lloc de 14; cobrixen el pla sencer. |
| `.github/workflows/ci.yml` (nou) | Matriu Python 3.10–3.12: `py_compile` de hooks/scripts + `unittest discover`. | El repo no tenia CI; ara els tests corren sols. |

### Com es verifica

1. `python3 -m py_compile hooks/*.py scripts/*.py` → OK.
2. `python3 -W error::ResourceWarning -m unittest discover -s tests` → **52/52 OK**.
3. Smoke de decay: fitxer IDÈNTIC després de `read-db.py`; ítems vençuts
   reordenats per prioritat efectiva sense mutar `priority`/SM-2.
4. Smoke `migrate-db.py`: legacy → `--check` exit 1 → migració → stamp →
   segona exec "Nothing to do" (idempotent, sense backup nou).
5. Smoke guard DB: `persist-session.py --db <inexistent>` → exit `1` amb
   `[Fluent] ❌ opencode.db not found`; el fitxer no es crea.

---

## 2026-09-05 — SM-2 daurat: `round()`, mastery per ratxes i cua avui pels encerts fallats

### Context / objectiu

`update-db.py` aplicava SM-2 amb una regla d'interval (`ceil()`) i una
heurística de mastery divergent de la font canònica del projecte
(`skills/fluent-sm2-calculator/SKILL.md` +
`references/sm2-worked-examples.md`). L'objectiu era alinear el
comportament amb els exemples daurats documentats i afegir tests que evitin
regressions futures.

### Canvis per fitxer

| Fitxer | Què canvia | Per què |
|---|---|---|
| `hooks/update-db.py` | `calculate_sm2()` fa servir `int(round(interval * ef))` per a la tercera repetició i següents. `update_spaced_repetition()` aplica mastery només amb ratxes documentades: `consecutive_correct >= 5` → `mastery_level +1` (clamp 0–5 i reset de la ratxa) i `consecutive_incorrect >= 3` → `mastery_level -1` (clamp 0–5 i reset de la ratxa). Els ítems revisats amb `quality < 3` es mouen a `review_queue.today` després de reconstruir la cua, encara que el seu `due_date` quedi demà. | Coherència amb la font SM-2 canònica i amb la política de repassar de seguida els ítems fallats. |
| `tests/test_sm2_golden.py` (nou) | Fixtures temporals per als 4 exemples daurats amb data base `2026-09-01`; executa `update-db.py` reals i valida `repetitions`, `interval_days`, `easiness_factor`, ratxes, mastery, `due_date` i colocació a `review_queue`. | Bloqueja regressions silencioses en SM-2 i documenta el comportament esperat. |
| `docs/DB_SCRIPTS.md` | Afegeix la nota que els ítems amb `quality < 3` es forcen a la cua `today` després del rebuild. | Documenta el canvi observable a consumers de `spaced-repetition.json`. |

### Com es verifica

1. `python3 -m py_compile hooks/update-db.py tests/test_sm2_golden.py` → OK.
2. `python3 -m unittest discover -s tests -q` → **56/56 OK**.
