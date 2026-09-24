# Fluent — Manual pràctic

**Actualitzat:** 2026-09-06
**Aplica a:** `fluent` (workspace de **dev** inert) i `fluent_learn` (app
d'**aprenentatge activa**), i a qualsevol còpia que en facis.

> Guia pràctica d'ús diari: models, com provar-ho tot i com gestionar les
> dades de l'aprenent. Detalls tècnics a
> [`CHANGES.md`](CHANGES.md) (canvis recents), [`dual-model/PLAN.md`](dual-model/PLAN.md)
> i [`opencode-migration/`](opencode-migration/).

---

## 1. Models i ports

> **Renombrat del 2026-09-13.** Els agents i les comandes ja no són a
> `.opencode/` sinó a **`prompts/agents/`** i **`prompts/commands/`**, i el
> servidor els llegeix directament. `opencode.json`, el plugin d'opencode i el
> llançador de models gratuïts són a `obsolet/opencode-runtime/`. El mode
> `--web` de `fluent-web.sh` (la UI d'opencode) queda arxivat: només `--app`.
> On aquest manual digui "opencode.json" per a la tria de models, ara mana
> `config/fluent.json` (vegeu §1.7).

### 1.1 Arquitectura fast/deep

Fluent v2 separa la **conversació** (model ràpid, context complet de la
sessió) de l'**avaluació** de respostes obertes (model "profund", context net
i rubric fix).

| Rol | Què fa | On es configura | Port |
|---|---|---|---|
| **fast (xat)** | Conversa lliure amb el tutor | Agent `learner` → deep, a `config/fluent.json` | **12322** |
| **face** | Turns curts: `/fluent-vocab`, `/fluent-review`, `/fluent-progress`, `/fluent-setup` | Agent `tutor-fast` → face, a `config/fluent.json` | **12323** (opcional: fallback a deep) |
| **deep** | Sessions llargues: `/fluent-learn`, `/fluent-writing`, `/fluent-speaking`, `/fluent-reading` + avaluació | Agent `tutor` → deep · eina `fluent_deep_evaluate` | **12322** |

El *routing* el fa `server/src/agent.ts` (`modelForAgent`) a partir del nom de
l'agent que declara la comanda al seu *frontmatter*. El camp `model:` que encara
hi ha dins dels fitxers de `prompts/agents/` és un residu d'opencode i **el
servidor l'ignora**.

### 1.2 Taules de ports i models

| Port | Provider | Model actual | Ús | VRAM | Configuració |
|---|---|---|---|---|---|
| **12321** | — (teu, independent) | el que hi posis | Ús general, Fluent NO el toca | — | — |
| **12322** | `fluent-deep` | Qwen3-14B-Q6_K (14B) | Tutor principal + avaluació deep | ~19.4GB mesurats | `config/fluent.json` → `models.deep` |
| **12323** | `llama-face` | Qwen3-1.7B-UD-Q4_K_XL (1.7B) | Comandes ràpides (vocab, review, progress, setup) | ~5GB mesurats | `config/fluent.json` → `models.face` |

**Candidats face (tots al 12323, només un alhora):** qwen1.7-q4 (actiu,
`scripts/models/llama-qwen1.7b-q4.sh`), qwen1.7-bf16
(`scripts/models/llama-qwen1.7b-bf16.sh`), omnicoder legacy
(`scripts/models/llama-omnicoder.sh`, abans `llama-face.sh`).
**Deep alternatiu Q4:** Qwen3-14B-Q4_K_M (~14 GB, apte 16 GB) —
`scripts/models/llama-deep-14b-q4.sh`; notes, temps i gap d'obediència a
[`model-qwen14b-q4.md`](model-qwen14b-q4.md).
**Webs:** alex-en → 4100, sam-en → 4101, demo-en → 4102 (prova). test-en sense port fix.

### 1.3 Com funciona la selecció de model

El nom del model ("deep", "face") és un **identificador intern de Fluent**, no
una validació del model real:

```json
"models": { "deep": { "port": 12322, "model": "…/Qwen3-14B-Q4_K_M.gguf" } }
```

**Fluent envia peticions al port 12322 amb model ID "deep".** El servidor (llama.cpp) les processa amb el que tingui carregat, **ignorant el nom**.

| Component | Com funciona |
|---|---|
| **config/fluent.json** | Defineix quins ports consultar (12322, 12323) i amb quin model els puja |
| **llama.cpp** | Accepta qualsevol nom de model — usa el que tingui carregat |
| **vLLM** | Valida el nom — cal llançar amb `--served-model-name deep` |

### 1.4 Què passa si un port és buit (fallback face→deep)

El face (12323) és una **descàrrega opcional per velocitat**, no un requisit.
Si no respon, el servidor fa **fallback automàtic al deep** (`server/src/agent.ts`,
`resolveModel` + un reintent al `catch`): el torn s'executa igual, només queda
una línia `[Fluent]` al log del servidor (cap avís al xat). L'app no perd res.

| Port buit | Què passa |
|---|---|
| **12323** (face) | `/fluent-vocab`, `/fluent-review`, `/fluent-progress`, `/fluent-setup` s'executen amb el deep (més lent, mateixa qualitat) |
| **12322** (deep) | Tot falla (tutor principal + avaluació) — cal pujar-lo sempre |

### 1.5 Quines comandes usen quin model

| Comanda | Agent | Model | Port |
|---|---|---|---|
| `/fluent-learn` | `tutor.md` | deep (14B) | 12322 |
| `/fluent-writing` | `tutor.md` | deep (14B) | 12322 |
| `/fluent-speaking` | `tutor.md` | deep (14B) | 12322 |
| `/fluent-reading` | `tutor.md` | deep (14B) | 12322 |
| `/fluent-vocab` | `tutor-fast.md` | face (1.7B) o deep si no hi ha face | 12323 → 12322 |
| `/fluent-review` | `tutor-fast.md` | face (1.7B) o deep si no hi ha face | 12323 → 12322 |
| `/fluent-progress` | `tutor-fast.md` | face (1.7B) o deep si no hi ha face | 12323 → 12322 |
| `/fluent-setup` | `tutor-fast.md` | face (1.7B) o deep si no hi ha face | 12323 → 12322 |

### 1.6 Contracte del model deep (ESTABLE)

El provider de projecte `fluent-deep` (a `opencode.json`) apunta sempre a
`127.0.0.1:12322` amb l'alias `deep`. Qualsevol model que servidis allà s'usa
tal qual:

- **llama.cpp**: no cal fer res — accepta qualsevol nom de model a la
  petició (verificat).
- **vLLM**: llança'l amb `--served-model-name deep` (vLLM sí que valida el
  nom).

El config global d'opencode (`~/.config/opencode/opencode.jsonc`) **ja no
afecta a fluent**: pots fer-hi els teus experiments de models sense trencar
la web.

### 1.7 Arrencar/aturar tot (start/stop + .env)

**On viu la configuració (des de 2026-09-13).** Tres capes, de baix a dalt:

| Capa | Fitxer | Què hi va |
|---|---|---|
| 1 | `config/fluent.json` | La configuració del projecte: models, ports, GPU, ctx, backend, llista de webs. Va al git. |
| 2 | `.env` a l'arrel | Només el que aquesta màquina fa diferent (`cp .env.railab .env` / `cp .env.rapve .env`). No va al git. |
| 3 | entorn i CLI | `FLUENT_DEEP_PORT=... scripts/fluent-start.sh`, `--gpu 4090`, etc. |

Per veure la configuració efectiva, sense endevinar quina capa ha guanyat:

```bash
python3 scripts/fluent-config.py --json      # resultat final
python3 scripts/fluent-config.py --sh        # el mateix, com a exports
```

Els scripts carreguen l'`.env` com sempre i després omplen el que falti des de
`config/fluent.json`, de manera que **el projecte arrenca sense `.env`** i, si
n'hi ha, mana ell. La secció `models` de `config/fluent.json` és **l'única font**
dels paràmetres dels models (port, ctx, temperatura, penalitzacions…): no hi ha
cap altre fitxer que se li superposi. Només poden passar-li al davant l'`.env`
(port, GPU, backend) i, per a un experiment, `FLUENT_MODELS_FILE` (és el que fa
servir `scripts/fluent-sweep.py`). `config/fluent-models.json` es va retirar el
2026-09-20 (és a `obsolet/config/`): repetia `fluent.json` però hi guanyava.

**Streaming (experimental).** `server.stream` a `config/fluent.json`, o
`FLUENT_STREAM=1` a l'entorn, fa que el tutor escrigui token a token en lloc
d'aparèixer de cop. Està **desactivat per defecte** i encara no s'ha provat
contra un model real: activa'l primer en una instància de proves
(`FLUENT_STREAM=1 scripts/fluent-web.sh --app test-en --port 4199`) i mira el
log. Si el model no accepta `stream:true`, l'error puja a `agent.ts`, que ja sap
caure al deep i mostrar l'avís.

**Mètriques per torn.** Cada torn deixa una línia al log
(`⏱ turn … prompt N tok · out N tok · R roundtrips`) i una línia JSON a
`~/.fluent/<perfil>/.metrics/turns.jsonl`. Per mirar on va el context:

```bash
python3 scripts/fluent-check.py metrics demo-en
```

Treu els torns, la mediana i el màxim de prompt, el temps per torn, **quines**
eines s'han cridat, i un `abans/ara` que separa el temps de dins el model del
temps del nostre codi.

Tot es governa des de `.env` a l'arrel (`cp .env.railab/.env.rapve` segons la
màquina; tot sobreescrivible per entorn o CLI):

```bash
scripts/fluent-start.sh                # detecta → pregunta → puja models + webs
scripts/fluent-start.sh --yes          # sense preguntes
scripts/fluent-start.sh --dry-run      # només mostra el pla (segur)
scripts/fluent-start.sh --gpu 4090     # deep a la 4090 (CUDA 0)
scripts/fluent-start.sh --force        # continua malgrat processos aliens (risc VRAM)
scripts/fluent-stop.sh                 # atura webs + models gestionats
```

Llançadors per separat (independents de l'start, a `scripts/models/`):
`llama-deep.sh` (Q6/Q4 segons `LLAMA_DEEP_MODEL`), `llama-deep-14b-q4.sh`,
`llama-qwen1.7b-q4.sh` (face), `llama-qwen1.7b-bf16.sh`, `llama-omnicoder.sh`
(legacy), `docker-llama.sh` (Docker 4060; llegeix `FLUENT_DEEP_*` de l'env).

Backend del deep (`FLUENT_DEEP_BACKEND`): `native` (llama-*.sh) o `docker`
(`docker-llama.sh`, `--gpus all`). A rapve: `BACKEND=docker` + `MANAGED=1` →
l'start el puja on digui l'env; amb `MANAGED=0` només el comprova.

Swap transparent amb el model default (mateix port, p. ex. 12321 a rapve):
`FLUENT_DEFAULT_MANAGER` (script aliè amb interfície `start|stop|status`,
res a veure amb el nostre) — l'start l'atura abans de pujar el nostre,
l'stop el restaura sempre. Decisió per fitxer d'estat
(`/tmp/fluent-deep-docker.state`, agnòstic a noms: un port sa no distingeix
dos contenidors). Sense manager + port estrany → avort explícit.
La detecció mostra sempre el titular (`contenidor 'X'` / `procés pid` /
`port lliure`); el Docker es resol per published-port (el cmdline duu el port
del contenidor, mai el del host).

L'env mana també al servidor: `FLUENT_DEEP_BASE_URL` / `FLUENT_FACE_BASE_URL`
(URL completes, màxima prioritat). Si buides, l'start les deriva del port amb
`127.0.0.1`. Posar-les explícites només per a model remot (IP).

# Comprovació d'estat (informatiu)
scripts/fluent-web.sh --app alex-en
# → mostra: "model: deep — OK (port 12322)"
#           "model: face — NOT RUNNING (port 12323)"

**Atenció:** a aquesta màquina l'índex de CUDA **no** coincideix amb el de
`nvidia-smi` (CUDA 0 = RTX 4090 = nvidia-smi 1; CUDA 1 = RTX 3090 = nvidia-smi 0).
Si el face no arrenca, mira `/tmp/fluent-qwen1.7b-q4-12323.log`.

### 1.8 Màquina 4060 (prova local, RTX 4060 Ti 16GB)

- **Model extern**: `scripts/models/docker-llama.sh` (Q4, ctx 32768, ~14 GB)
  al port host que digui l'env (estàndard 12322). El `docker/` antic ja no
  existeix.
- **Orquestració**: els mateixos `fluent-start.sh`/`fluent-stop.sh` amb
  `cp .env.rapve .env` (`BACKEND=docker`, `MANAGED=1`: l'start el comprova i
  el puja si cal; `MANAGED=0`: només el comprova, el poses tu).
- **Prereqs**: Docker + `--gpus all`, `bun`, `python3`, `openssl`, `curl`.
- **Repo**: còpia sencera (cal `server/node_modules/`; `config/` per defecte
  ja apunta al 12322 — revisar igualment).
- **Perfils**: a `~/.fluent/<id>/` d'allà (p. ex. còpia de `demo-en`);
  `scripts/new-user.sh <id>` per a perfils verges. Perfils inexistents:
  l'start els salta amb avís.
- **Xarxa**: les webs escolten a totes les interfícies (`*:port`); des de fora
  cal la IP LAN + firewall obert + login per nom (`nes`, no `opencode`).

### 1.9 Sincronitzar codi cap a una altra màquina (procediment segur)

La causa més cara vista fins ara: **còpia rància** (el servidor vell servint
amb config vella mentre el log nou enganya). Regles:

- **SÍ copiar**: el repo sencer (`server/`, `web/`, `scripts/`, `hooks/`, `skills/`,
  `.opencode/`, `docker/`, docs). Comprovar vintage després:
  `ls scripts/fluent-start.sh config/fluent.json` + `grep VERSION server/src/index.ts`.
- **NO copiar a cegues**: `~/.fluent/<id>/` (sessions, ratxes, passwords i
  flags divergeixen per màquina). Si cal migrar un perfil: backup del destí
  primer, després còpia; mai fusió manual de JSONs.
- **`config/` i `.env`**: revisar sempre (ports/GPU/model difereixen);
  `cp .env.rapve .env` a la 4060, mai a l'inrevés.
- **Aturar-ho tot al destí abans** (`fluent-stop.sh`) per no deixar orfes
  servint codi vell amb pidfiles nous.
- `server/node_modules/` es pot copiar (JS pur, mateixa arch) o reinstal·lar.

---

## 2. Configuració i aïllament

### 2.1 Workspace de dev vs app de producció

Hi ha un **únic `opencode.json`** per a tots els alumnes, i el codi és
**100% projecte** (cap dada dins). La diferència entre desenvolupament i
producció la marca un **marcador** a l'arrel del directori:

| Workspace | Marcador | Rol |
|---|---|---|
| `fluent` | `.fluent-dev` **present** | **Dev inert**: no fa de tutor, no escriu dades, no genera resultats |
| `fluent_learn` (o qualsevol còpia sense marcador) | `.fluent-dev` **absent** | **App activa**: tutor que llegeix i escriu a `~/.fluent/<id>/` |

**Per crear una app de producció** des del workspace de dev:

```bash
cp -a /camí/fluent /camí/fluent-prod
rm /camí/fluent-prod/.fluent-dev        # treure el marcador → activa el tutor
```

Com que totes les dades (6 JSON + `results/`) viuen fora, a `~/.fluent/<id>/`,
la còpia ja és funcional sense tocar res més. El plugin (`fluent.js`)
detecta el marcador amb `isDevMode()` a l'arrencar.

### 2.2 Aïllament de dades per alumne

Cada alumne té el seu directori de dades **fora del projecte**:

```
~/.fluent/alex-en/               ← dades de Alex
~/.fluent/sam-en/               ← dades d'Sam
~/.fluent/demo-en/                ← dades de Nes
```

Contingut de cada directori:
```
~/.fluent/<id>/
├── learner-profile.json         ← perfil (nom, idioma, CEFR, streak)
├── spaced-repetition.json       ← cua de repetició espaçada (SM-2)
├── mistakes-db.json             ← patrons d'error
├── progress-db.json             ← estadístiques
├── mastery-db.json              ← nivells de domini (0-5 estrelles)
├── session-log.json             ← històric de sessions
├── results/                     ← fitxers de resultat de cada sessió (*.md)
├── session-draft.json           ← acumulador incremental (persistència automàtica)
├── .update-state/               ← snapshots T0 per a la idempotència per session_id
├── sessions/sessions.db         ← sessions i missatges (transcripció)
├── .opencode/opencode/          ← MATEIXA BD, ruta antiga: es manté perquè la
│                                  versió anterior de l'app hi escriu. No
│                                  s'esborra; es migra amb
│                                  scripts/migrate-sessions-db.py
├── .records/                    ← registres estructurats per sessió (P1-5)
├── .metrics/turns.jsonl         ← tokens i temps per torn
├── .backups/                    ← còpies de seguretat
└── .web-password                ← password d'aquesta instància
```

Els **fitxers de resultat de sessió** (`alex-fluent-learn-session-001.md`)
viatgen ara amb les dades, a `~/.fluent/<id>/results/`, no dins del projecte.
`persist-session.py` hi escriu automàticament quan el directori de dades té
`learner-profile.json`.

### 2.3 Variables d'entorn per instància

El script `fluent-web.sh` configura **per cada instància**:

| Variable | Valor | Propòsit |
|---|---|---|
| `FLUENT_DATA_DIR` | `~/.fluent/<id>/` | On buscar les BDs del tutor |
| `XDG_DATA_HOME` | `~/.fluent/<id>/.opencode` | Només per a la versió anterior i per al camí opencode arxivat. El servidor actual obre `~/.fluent/<id>/sessions/sessions.db` |
| `FLUENT_SESSIONS_DB` | (opcional) | Força una BD de sessions concreta, saltant-se la resolució |
| `OPENCODE_SERVER_PASSWORD` | Generat o desat a `.web-password` | Autenticació HTTP |

### 2.4 Arquitectura completa

```
┌─────────────────────────────────────────────────────────────────┐
│      fluent / fluent_learn — opencode.json                       │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │ fluent-deep     │  │ llama-face      │                       │
│  │ port 12322      │  │ port 12323      │                       │
│  │ model: deep     │  │ model: face     │                       │
│  └────────┬────────┘  └────────┬────────┘                       │
└───────────┼────────────────────┼────────────────────────────────┘
            │                    │
            ▼                    ▼
┌───────────────────┐  ┌───────────────────┐
│ llama-server      │  │ llama-server      │
│ Qwen3-14B-Q6_K    │  │ Qwen3-1.7B-Q4     │
│ (tutor, fallback) │  │ (face opcional)   │
└───────────────────┘  └───────────────────┘
            │                    │
            └────────┬───────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌───────────────────┐  ┌───────────────────┐
│ Alex              │  │ Sam              │
│ ~/.fluent/alex-en │  │ ~/.fluent/sam-en │
│ (BDs pròpies)     │  │ (BDs pròpies)     │
│ (results pròpies) │  │ (results pròpies) │
└───────────────────┘  └───────────────────┘
```

### 2.5 Persistència automàtica (per a mi i per al codi)

La sessió es desa **incrementalment i per si sola**, sense que calgui que jo
recordi res ni que l'aprenent esperi. Ho fa el servidor amb **dos nivells**:

**Nivell A — cada resposta (automàtic, invisible).**
Al final de cada torn el **servidor** (`agent.runAutoPersistence`, amb l'id de
sessió exacte) executa `accumulate-session.py`:

1. Llegeix l'`opencode.db` i troba el feedback que ja he graduat (el format
   `**Score: X/10**` és el contracte de lectura).
2. Afegeix **només el que és nou** al `session-draft.json` del perfil, usant
   un *high-water-mark* (el `rowid` màxim ja processat) → no repeteix res.
3. Aplica **el payload complet acumulat** amb `update-db.py`.

Com que `update-db.py` és **idempotent per `session_id`** (guarda un snapshot
pre-sessió a `.update-state/<sid>.json` i, si el `session_id` ja s'havia
aplicat, restaura i re-aplica), donar el mateix payload moltes vegades no
duplica comptadors, sessions, errors ni SM-2. Cada `session.idle` és segur:
aplicar-lo de nou és un no-op.

**A més, la capa A genera el fitxer de resultat de sessió.**
Després d'aplicar (exitós), `accumulate-session.py` crida `write_results_file`,
que reutilitza `save_results_file` per crear/refrescar
`~/.fluent/<id>/results/{slug}-fluent-learn-{sid}.md`. És determinista (només
uneix dades ja graduades, **sense ús del model**) i idempotent (mateix nom de
fitxer → es reescriu, mai duplica). Per tant **"acabar sessió = tancar el
navegador" ho deixa tot fet, inclòs el resum Markdown** — no depèn d'una
comanda manual del tutor.

**Nivell B — finalització (la fa el servidor, no jo).**
Quan l'aprenent tanca amb `/fluent-end`, i també automàticament quan una sessió
porta 30 min inactiva (*sweeper* del servidor, cada minut), s'executa
`persist-session.py <ses_id> --dir <data-dir>`. Re-parseja la transcripció
**sencera** i hi afegeix la durada real. Mateix `session_id` → reemplaça, no
duplica. Queda marcat a `session.metadata.capa_b_done` perquè no es repeteixi.

El tutor **no** persisteix res: no crida cap script ni escriu cap fitxer (no en
té permís i no cal). Si vull re-executar la Capa B d'una sessió antiga a mà:
```bash
python3 hooks/persist-session.py ses_XXXX --dir ~/.fluent/<perfil>
```

**El bloc de repàs (`fluent:review_results`) — l'única entrada que fa avançar
SM-2.** Ni la capa A ni la B poden endevinar de la prosa quin ítem de la cua
s'estava repassant. Per això, al final d'una sessió de repàs o de vocabulari, el
tutor envia com a última cosa:

````markdown
```fluent:review_results
[{"item_id": "<id copiat de la cua>", "quality": 4}]
```
````

La web l'amaga (`stripMachineBlocks` a `web/app.js`), el parser el llegeix de la
transcripció sencera a cada torn (`parse_review_results`), descarta els
`item_id` que no siguin a la cua del perfil, i `update-db.py` hi aplica SM-2.
Sense aquest bloc, un ítem es queda amb `interval_days: 1` i `repetitions: 0`
per sempre: entra a la cua i no en surt mai.

Les entrades de `new_vocabulary` poden portar els camps opcionals `pos`,
`cefr_level` i `forms` (p. ex. `{"word": "…", "translation": "…", "pos": "noun",
"cefr_level": "A2", "forms": {"plural": "…"}}`): es desen si el payload els
inclou, i els payloads antics sense aquests camps funcionen igual que sempre.

**On es guarda la metadada d'acumulació (per perfil):**
```
~/.fluent/<id>/
├── session-draft.json        ← acumulador incremental (high-water-mark + payload)
└── .update-state/<sid>.json  ← snapshot T0 (pre-sessió) per a la idempotència
```

> A mode de recordatori tècnic: només em cal graduar amb el **format de
> feedback parsejable** (vegeu AGENTS.md) → la capa A ho recull sola. No he de
> carregar skills de persistència ni escriure les BDs a mà.

---

## 3. Com provar-ho tot

1. **Tests (2 s):**
   ```bash
   cd fluent && python3 -m unittest discover -s tests
   python3 -m py_compile hooks/*.py scripts/*.py   # el que fa la CI
   ```
   → 52/52 OK. La CI (`.github/workflows/ci.yml`) correix ambdues coses en
   una matriu Python 3.10–3.12 a cada push.
2. **Desktop:** reinicia l'app (el plugin es carrega en arrencar el server).
   - A `fluent` (**marcador `.fluent-dev`**): **mode dev** (paper de tutor
     amagat, eina `fluent_deep_evaluate` disponible per a desenvolupar).
   - A `fluent_learn` / qualsevol còpia sense `.fluent-dev`: mode tutor.
3. **TUI + eina deep:**
   ```bash
   cd fluent && opencode
   ```
    → `/fluent-writing` (o `/fluent-speaking`) → respon un exercici → el
    tutor crida `fluent_deep_evaluate` (a la web, chip "avaluant resposta")
    i retorna `CORRECTIONS / CORRECT VERSION / SCORE / FEEDBACK`.
4. **Web amb streaming en viu:** vegeu [3.1](#31-la-web-i-el-profile-id).
5. **Fallback amb el deep caigut (opcional):** atura el server del model al
   12322 i repeteix el 3 → l'eina retorna `DEEP UNAVAILABLE: …` i el tutor
   avaluà sol; la sessió continua.
   **Fallback amb el face caigut:** no cal aturar res — si el 12323 és buit,
   `/fluent-vocab` (etc.) corre amb el deep automàticament (només log).
6. **Headless (fum):** `opencode run "…"` amb un entorn net → la llista
   d'eines inclou `fluent_deep_evaluate`.
7. **Persistència automàtica (en viu, verificada 2026-08-31):** a `nes` es van
   fer 28 exercicis amb respostes graduades; al `session.idle` la capa A ho va
   acumular tot (sense duplicar la fila `session-001`), i ara també genera el
   `results/*.md` automàticament. Es verifica el mateix als pasos per a qualsevol
   perfil nou (vegeu `new-user.sh` i §3.1).

### 3.1 La web i el `profile-id`

```bash
scripts/fluent-web.sh --app [--port N] [profile-id]
```

- **Sense `profile-id`** → l'instància usa la carpeta `data/` del propi
  projecte. A `fluent` està buida → l'app s'obre **"sense usuari"**
  (cap perfil carregat).
- **Amb `profile-id`** → usa `~/.fluent/<profile-id>/`, que **ha
  d'existir** amb el seu `learner-profile.json` (sinó el script avisa
  `error: profile '...' not found` i no arrenca). El domini mDNS canvia a
  `fluent-<profile-id>.local`.
  ```bash
  scripts/fluent-web.sh --app alex-en
  # → http://fluent-alex-en.local:4100  (o http://<ip>:4100)
  # login: opencode + el password que imprimeix el script
  ```
- **Crear un perfil nou (bootstrap):** `scripts/new-user.sh <id> [--port N]`
  valida l'`id`, crea `~/.fluent/<id>/` i seeda els 6 JSON de
  `data-examples/`, genera el `.web-password`, i imprimeix la comanda de
  llançament. Marca el perfil com a **"pendent de setup"**
  (`preferences.setup_complete: false`).
  ```bash
  scripts/new-user.sh test-en --port 4102
  scripts/fluent-web.sh --app test-en --port 4102
  ```
- **Setup automàtic al primer login:** en obrir la web sobre un perfil **no
  configurat**, el client llegeix `/api/fluent/setup-state` i auto-arrenca
  **`/fluent-setup`** (l'entrevista) en lloc del menú de `/fluent-learn` — no
  cal que l'admin escrigui res. Un cop configurat (`setup_complete: true`),
  la web torna a arrencar `/fluent-learn` com sempre.
  - Els **perfils ja existents** (sense el camp, p. ex. `alex`, `nes`, `sam`)
    es tracten com a **configurats** (fallback segur) i no es veuen afectats.
  - **Editar** el setup més endavant no és una via visible per a l'usuari: es
    fa amb **sessió nova + comanda `/fluent-setup`** (cas excepcional).
- **Un perfil per instància:** cada `--app <id>` té el seu port, password i
  data dir, perquè els perfils mai es barregen.
- **Aturar:** `scripts/fluent-web.sh --stop [--port N]`.
- **Robustesa d'arrencada:** preflight (bun/python3/perfil — error en 1 s, no
  20 s de timeout), neteja de pidfiles rancis, i kill+neteja si el health-check
  falla. Els `fluent-up*` netegen rancis abans de decidir (mai "ACTIVA"
  fantasmes).
- **Comportament de la interfície (app.js SSE):**
  - El text s'escriu **en viu** (streaming SSE); canviar de pestanya o
    bloquejar la pantalla **no** interromp la sessió (abans sí).
  - Les comandes dels botons apareixen com un chip amb la **icona sola**
    (p. ex. `🎲`, sense `/fluent-…`); els xips `skill`/`bash` reeixits
    s'amaguen (errors i "avaluant resposta" sempre visibles).
    **Mode debug** (`?debug=1` o triple-clic a 🌍 Fluent): mostra el text de
    la comanda i tots els xips d'eines.
  - **Enviar buit = "next" (només quan toca):** prémer ➤ (o Enter) sense
    escriure res envia `next` — però només si el tutor NO espera resposta
    (últim missatge sense `✏️ Exercici` obert). Si l'exercici espera, el ➤
    s'atenua i cal escriure (o escriure `next` per saltar). Es mostra com a
    xip `⏭`.
  - **Comandes a mitja sessió continuen (no reinicien):** el servidor marca el
    torn (`Continuing session…`, excepte `fluent-end`) quan l'historial ja té
    text del tutor — així un 🎲 no re-saluda ni re-mostra el menú. Les regles
    de prompt soles perden contra la plantilla de salutació (verificat).
  - **Regles compartides:** `agent/rules.md` es concatena a TODOS els agents
    (learner/tutor/tutor-fast); font única (rollback = esborrar 3 línies a
    `agent.ts` `buildSystemPrompt`).
  - Els botons equivalen al menú numerat del tutor: `🎲 Aprèn` = Surprise
    me (mix adaptatiu), `🔁 Repassa` = Spaced Review, `📚 Lèxic` =
    Vocabulary, `📝 Escritura` = Writing, `🗣️ Conversa` = Speaking,
    `📖 Lèctura` = Reading; a més `📊 Progrés` i `👤 Perfil`.
- **`👤 Perfil` a la web:** executa `fluent-use` (agent tutor) i llista els
  perfils de `~/.fluent/`; el perfil actiu d'una instància, però, es tria
  **en arrencar** amb `profile-id`.
- **Crear un perfil nou** (un cop, per exemple a partir d'una còpia amb
  dades):
  ```bash
  cp -a /camí/origen/data ~/.fluent/<nou-id>
  ```
  (els 6 JSON + `.backups/`; vegeu la secció 4.)

### 3.2 Panell visual de progrés (botó 📊 Progress)

- El botó **📊 Progress** del nav **obre directament el panell visual**
  (modal), sense llançar cap torn de l'agent. Escriure `/fluent-progress`
  continua disponible per demanar el resum textual al tutor.
- **No necessita models:** el panell és 100% local — el navegador crida
  `GET /api/fluent/progress`, el servidor executa `read-db.py --full` sobre
  el perfil actiu i retorna un **resum normalitzat** (no el DB sencer).
- **Seccions:** capçalera (nom · idioma · nivell), 6 targetes KPI (ratxa,
  sessions, exercicis, encert, minuts, reviews d'avui + chips dels ítems),
  mastery per skill (estrelles ★ + barra + encert), patrons febles (top 5),
  mini-gràfic de tendència d'encert (CSS), resum setmanal, sessions recents
  i fites/assoliments.
- **Botó ↻** dins el panell per actualitzar sense tancar. Es tanca amb la
  ✕, clicant el fons o amb `Escape`. Si l'API falla, el panell mostra
  l'error (no penja la conversa).
- **Prova ràpida (perfil de test, sense models):**
  ```bash
  cp -r ~/.fluent/demo-en /tmp/progress-nes
  PORT=4199 FLUENT_DATA_DIR=/tmp/progress-nes FLUENT_WEB_PASSWORD=test \
    bun server/src/index.ts &
  curl -s -u opencode:test http://127.0.0.1:4199/api/fluent/progress \
    | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print(d['learner'], d['overview'])"
  ```

### 3.3 Caixa de resposta i marques al flux

- **Caixa amb aire:** l'entrada arrenca amb 2 línies (`min-height: 64px`) i
  creix sola fins al 38% de la pantalla. El `placeholder` canvia segons el
  mode ("Escriu la traducció…" a vocab, "Escriu el teu text en l'idioma
  meta…" a writing, etc.).
- **Ressalt "et toca":** quan el tutor acaba un torn, el composer s'il·lumina
  (vora verda) i recupera el focus; el ressalt marxa en començar a escriure
  o enviar.
- **Botó ⤢ (escriptura gran):** expandeix la caixa al ~70% de la pantalla
  per textos llargs. `Ctrl/Cmd+Enter` envia (útil en expandit);
  `Shift+Enter` continua fent salt de línia. Es desactiva durant el torn,
  com la resta.
- **Darrera resposta amb vora verda:** l'últim missatge del tutor porta
  línia verda a l'esquerra (`msg-latest`); només un cada vegada.
- **Enunciat amb fons destacat:** pregunta pura → tot el bloc en verd clar;
  empaquetat → des del primer paràgraf amb marcador (`Exercise N:`,
  `## Exercise`, `Question N:`, `Question:`) fins al final, amb el primer bloc remarcat (`ex-start`: vora
  verda + to més fort) perquè es vegi on comença la pregunta; el feedback
  conserva la seva pintura. Si el
  marcador cau a mig paràgraf, es pinta el bloc sencer (limitació assumida).
- **Heurística (només client, sense tocar l'agent):** és exercici obert si
  **no** porta `Score: X/10` (el feedback sempre en porta), **no** és el
  menú ("Type a number or skill name…"), **no** és resum de fi de sessió
  ("Session Complete", "Today's Stats", "Breakthroughs") i fa menys de
  ~1500 caràcters. Falsos positius possibles (p. ex. salutacions curtes) —
  a calibrar amb l'ús; la via robusta futura seria marcar exercicis als
  prompts.
- **Etiquetatge al flux:** cada missatge del tutor es classifica en viu
  (també durant l'streaming): pregunta oberta → vora verda + xip "✏️
  Exercici"; feedback → xip amb la nota ("★ 8/10"). Els teus missatges no
  s'etiqueten mai. Així el flux mostra l'estructura pregunta→correcció.
- **Targeta d'exercici aparcada:** `EXERCISE_CARD_ENABLED = false` — no es
  mostra (l'extracció es reutilitza per pintar); `FREEZE_FOR_CARD = false`
  — l'auto-scroll torna al comportament normal. Es pot reactivar tot.
- **Fons pintats al feedback:** el paràgraf `Correct version:` porta fons
  verd suau; els ítems ❌/✅ de correccions, vermell/verd suaus. Només amb
  marcadors canònics; si el format no hi és, no es pinta res.
- **Fons pintats al feedback:** el paràgraf `Correct version:` porta fons
  verd suau; els ítems ❌/✅ de correccions, vermell/verd suaus. Només amb
  marcadors canònics; si el format no hi és, no es pinta res.
- **Bombolles pròpies en blau-gris:** les teves respostes porten fons
  `--user-bubble` (#e7edf5), separat del verd de correctes
  (`--assistant-correct`), perquè al flux no es confonguin.
- **Píndola "↓ Últim missatge":** per a la resta (conversa, feedback), apareix
  **només quan l'últim missatge del tutor ha sortit de la pantalla**.
  Clic → scroll suau al missatge. Res es duplica ni es plega.
- **Navegació a la capçalera:** els botons de mode (Writing…Progress) viuen
  **sota el títol 🌍 Fluent**, en format compacte (icona; etiqueta sencera
  en pantalles amples; scroll horitzontal en mòbil). En **mode concentració**
  s'amaguen durant el torn i tornen en acabar, sense desplaçar el composer.

---

## 4. Dades de l'aprenent: còpia i migració

**Què és l'estat?** Els **6 JSON** (`learner-profile`, `progress-db`,
`mistakes-db`, `mastery-db`, `spaced-repetition`, `session-log`) més la
carpeta **`results/`** (fitxers de resultat de sessió, `*.md`) i el
directori `.backups/`. Res més — **tot viu fora del projecte**, a
`~/.fluent/<id>/`. Des del 2026-09-04 l'esquema està **versionat**: cada JSON
porta `_schema_version` (actualment `1`; els fitxers antics sense el camp es
llegeixen com a v1). Les dades copiades entre còpies de codi funcionen sense
cap canvi mentre la versió coincideixi; si una versió futura puja l'esquema,
es migra explícitament (vegeu §4.1).

**Perfils existents (2026-08-28):**

| Perfil | On | Estat |
|---|---|---|
| **Alex** (English, A1) | `~/.fluent/alex-en/` | Actiu, sessions múltiples |
| **Sam** (English, A1) | `~/.fluent/sam-en/` | Actiu, sessions múltiples |
| **Nes** (English, A1) | `~/.fluent/demo-en/` | Cread, poques sessions |

**Opcions (de més recomanada a menys):**

**A. Perfil únic a `~/.fluent/<id>/`** (convenció multi-usuari, recomanat;
conté els 6 JSON + `results/` + `.backups/`). Funciona directament amb
`--app <id>` a la web i `/fluent-use <id>` al TUI:
```bash
mkdir -p ~/.fluent
cp -a /camí/origen/~/.fluent/albert-en ~/.fluent 2>/dev/null
# o un shortcut amb FLUENT_DATA_DIR:
export FLUENT_DATA_DIR=~/.fluent/albert-en
```

**B. Copiar tot el directori d'estat d'un altre projecte** (per absorbir
l'estat d'una còpia que encara el portava dins):
```bash
cp -a /camí/origen/data/* ~/.fluent/<nou-id>/
mkdir -p ~/.fluent/<nou-id>/results
cp -a /camí/origen/results/* ~/.fluent/<nou-id>/results/
```

**C. Apuntar-hi sense copiar** (la dada viu en un lloc únic i totes les
còpies de codi la comparteixen):
```bash
echo "/camí/absolut/data" > /nou-directori/.fluent-active
```
o `export FLUENT_DATA_DIR=/camí/absolut/data` abans de llançar opencode, o
`/fluent-use <id>` dins una sessió TUI.

> Consell: com que tot l'estat (6 JSON + `results/` + backups) viu a
> `~/.fluent/<id>/`, les còpies de codi no porten dades dins i migrar de
> versió és només canviar de directori — l'aprenentatge no es perd mai. Per
> activar una còpia, treu el marcador `.fluent-dev` (secció 2.1).

### 4.0 Decaïment de la mestria (des del 2026-09-13)

El nivell de cada habilitat a `mastery-db.json` ara baixa sol si no es practica:
res durant 14 dies, després un nivell cada 21 dies d'inactivitat, mai per sota
d'1. El que la pràctica va guanyar es guarda a `mastery_level_earned` i no es
toca mai — `mastery_level` és el valor d'avui, recalculat a cada sessió.

Per alumne, al seu `learner-profile.json`:

```json
"preferences": { "mastery_decay": { "grace_days": 14, "step_days": 21, "floor": 1 } }
```

`"step_days": 0` l'apaga per a aquell alumne. Els ítems de repetició espaiada
**no** decauen: ja porten el temps al seu `due_date`.

Els patrons d'error segueixen la mateixa lògica però només per a l'**ordre** en
què arriben al tutor: el pes es divideix per dos cada 21 dies sense aparèixer, de
manera que un error ja corregit deixa de ser la prioritat. La freqüència real no
es toca.

### 4.0b Quantes preguntes dura una sessió, i on ets

Dues coses separades: **l'alumne veu on és** i **el tutor sap quan tancar**.

**On ets.** A la capçalera de la web hi ha un indicador petit (`✏️ 3/8` amb una
barra; passant-hi per sobre, el percentatge). El número **no** el porta el
model: el servidor compta les respostes que té registrades
(`fluent_record_answer`) i l'envia a cada torn per SSE (`session.progress`); en
recarregar la pàgina es recupera de
`GET /api/fluent/session-progress?session=<id>`. Quan el mode no es compta per
exercicis (escriptura, lectura) surt només el compte, sense objectiu.

**Quan es tanca.** `preferences.session_length` al perfil (12 si no hi és, `0`
ho apaga). En arribar-hi, el servidor injecta una instrucció al torn següent:

| `preferences.session_stop` | Què fa el tutor |
|---|---|
| `"soft"` (per defecte) | Ofereix acabar: una línia amable i triar entre el resum ara o un parell més |
| `"hard"` | Tanca amb el resum sense preguntar |

Al log hi queda `🏁 session … : N graded — asking the tutor to close`.

Queden exempts **writing** (un escenari per sessió) i **reading** (un text),
que tenen forma pròpia. Els botons de dalt segueixen disponibles sempre: el
resum és una pausa, no un tancament.

El límit diari de repàs i de paraules noves viu a `spaced-repetition.json` →
`daily_limits` (`review_items_per_day: 20`, `new_items_per_day: 10`). Fins ara
els skills deien "20 per defecte" i aquella clau **no existia a les dades**: el
número sortia només del prompt.

### 4.1 Versionat d'esquema i `scripts/migrate-db.py`

Els 6 JSON porten un camp `_schema_version` (actualment `1`). Un perfil antic
sense el camp **es llegeix i s'usa amb normalitat** (es tracta com a v1);
l'únic que cal és "estampar-lo":

```bash
# Informatiu: versió de cada fitxer; exit 1 si una execució normal escriuria
python3 scripts/migrate-db.py --check --dir ~/.fluent/alex-en

# Migrar: fa backup a <dir>/.backups/pre-migration-<timestamp>/ i estampa.
# Idempotent: si ja tot és a la versió actual, surt amb "Nothing to do".
python3 scripts/migrate-db.py --dir ~/.fluent/alex-en
```

Sense `--dir` usa `$FLUENT_DATA_DIR` (i si no està definida, `./data`).

Guardes que protegeixen les dades (coberts pels tests de la CI):

- `update-db.py` **refusa escriure** sobre un perfil amb esquema futur o
  desconegut (exit 2, fitxers intactes). El missatge
  `is schema v2 > supported v1; upgrade Fluent before writing` vol dir que
  les dades són d'una Fluent més nova: actualitza el codi, no les dades.
- `read-db.py` imprimeix avisos `[Fluent]` i surt amb exit 1 si troba
  esquemes incompatibles o fitxers corruptes.
- **Lock advisory d'escriptura:** `update-db.py` i `migrate-db.py` (mode
  escriptor) agafen `flock()` sobre `<data-dir>/.db.lock` abans de fer el
  read-modify-write sobre els 6 JSON. `FLUENT_DB_LOCK_TIMEOUT` controla els
  segons d'espera (default `10`); si s'esgota, surten amb `2` sense escriure.
  El lock es libera sol si el procés mor. `read-db.py` segueix sense lock.
- **Decaïment no destructiu:** a la llista de repassos, cada 14 dies de
  retard (`OVERDUE_BOOST_DAYS`) apuja un nivell la *prioritat efectiva*
  (camps de sortida `days_overdue`/`effective_priority`). És només ordenació
  de la lectura: mai muta `priority`, `due_date` ni paràmetres SM-2 al disc.

---

## 5. Opcions per canviar de model

### 5.1 Fer servir el mateix model als dos ports

Si vols un sol model (ex: 14B) per a tot: **no cal fer res** — si el 12323 és
buit, les comandes ràpides fan fallback automàtic al deep (vegeu §1.4).

### 5.2 Provar un model temporalment

Per provar un model sense tocar la configuració de producció:

```bash
# 1. Llençar el model a un port lliure (p. ex. 12325)
llama-server -m /path/to/model.gguf --port 12325 --host 127.0.0.1

# 2. Canviar temporalment opencode.json
#    (fluent-deep.baseURL → http://127.0.0.1:12325/v1)

# 3. Provar

# 4. Tornar a la configuració original i reiniciar opencode
```

### 5.3 Troubleshooting de models

| Síntoma | Causa | Solució |
|---|---|---|
| `Connection refused` al port 12322 | No hi ha model deep | `scripts/fluent-start.sh` (o `scripts/models/llama-deep.sh` directe) |
| `Connection refused` al port 12323 | No hi ha model face | `FLUENT_FACE_ENABLED=1 scripts/fluent-start.sh` (opcional: el deep el cobreix) |
| `DEEP UNAVAILABLE` | Model deep cau o timeout | El tutor avaluà sol; el servei continua |
| `/fluent-learn` → `HTTP 500 UnknownError`, log `init count=1` | **Sessió vella/penjada** desada al `localStorage` del navegador (`fluent.session`) per a una instància concreta; la web la reutilitza en lloc de crear-ne una de nova | Netejar `localStorage.removeItem("fluent.session")` (o botó **"Nova sessió"**), recargar i tornar a provar. No és un error de codi ni de `learner.md`: un perfil amb sessió nova fa `init count=13` i funciona |
| Resposta molt lenta (>60s) | Model gran o context ple | Reduir context o usar model més petit |
| `Context size has been exceeded` | Context sobrepassat | Reduir `max_tokens` o augmentar `-c` al servidor |
| La web carrega però els torns fallen (altres navegadors van bé) | Brutícia del navegador (caché, auth desada, extensions) o stream SSE mort | Finestra d'incògnit per descartar; si allà va: DevTools → Application → Clear site data de l'origen + desactiva extensions (VPN/adblock). Tancar pestanyes no neteja ni caché ni SSE morts |

---

## 6. Notes

- El plugin (`.opencode/plugins/fluent.js`) es carrega **en arrencar el
  server**: després de canviar-lo, cal reiniciar l'app desktop / una
  instància nova perquè surti.
- El password de la web s'imprimeix **una sola vegada** (mai es desa); per
  fixar-ne un permanent: `FLUENT_WEB_PASSWORD=... scripts/fluent-web.sh --app`.
- **Login per nom:** l'usuari del basic-auth és el nom de l'alumne en
  minúscules (`nes`, `alex`, `sam`, `test`) amb el password del seu
  `.web-password` (que es manté). L'antic `opencode` continua funcionant.
- El model s'ha de servir abans de provar (deep al 12322; face al 12323
  opcional amb fallback): `scripts/fluent-start.sh` ho puja tot.
- **Per a mi (tutor):** la persistència per-resposta és **automàtica** al
  `session.idle` (vegeu §2.5); només finalitzo amb UNA comanda al final per
  afegir la metadada rica. `session-draft.json` i `.update-state/` són
  **runtime regenerable** (no cal editar-los ni esborrar-los a mà; si els
  elimino es recumulen i es recupera la idempotència).
- Si un perfil es corromp: els backups a `~/.fluent/<id>/.backups/` (pre-actualització
  i diaris) permeten restaurar.
- **Guard d'`opencode.db` (2026-09-04):** si el db resolt no existeix,
  `persist-session.py` imprimeix `[Fluent] ❌ opencode.db not found` i surt amb
  exit 1 (abans creava un sqlite buit amb un "no such table" confús);
  `accumulate-session.py` (el ganxo `session.idle`) dona el mateix avís però
  surt amb 0: és best-effort i no ha de bloquejar la sessió. Solució: revisar
  `FLUENT_DATA_DIR`/`XDG_DATA_HOME` (§2.3).
- **Tots els alumnes comparteixen el mateix `opencode.json`**: els canvis
  de configuració de models afecten a tothom.
- **Cada alumne té les seves pròpies BDs**: `FLUENT_DATA_DIR` aïlla les
  dades per instància.
- **Els perfils nous es creen amb `scripts/new-user.sh`** (bootstrap net dels
  6 JSON; posa `preferences.setup_complete: false`, i la web auto-arrenca
  `/fluent-setup` al primer login — vegeu §3.1). No cal (ni és segur) editar
  `~/.fluent/<id>/` a mà.

## 7. Mode friend v0.3 (opt-in per alumne, default clàssic)

El tutor pot mostrar que coneix l'alumne (cita l'última sessió, usa els seus
interessos) quan el perfil porta `preferences.tutor_style: "friend"`. Sense el
flag, comportament clàssic idèntic (verificat). Cost: ~250 tokens/torn (+0.5–2%
de temps), 0 VRAM (KV pre-reservat pel `-c`).

- **Dades:** `learner.interests[]` (max 3 curts), `learner.about` (1 línia),
  `preferences.tutor_style` — camps opcionals a `learner-profile.json` (setup
  els pregunta amb topall; cap migració). Exposats al compacte de `read-db.py`
  (únic toc de codi; `.get` tolerants).
- **Prompts:** bloc FRIEND condicional a `tutor.md` + salutació `learn` §3 +
  1 línia a `vocab`/`speaking`/`reading`. Res més.
- **Rollback:** esborrar el flag = clàssic instantani (`scripts/fluent-friend.sh
  <id> [on|off|status]` — `off` deixa el perfil byte-idèntic, verificat).
  Revert total = aquests fitxers (seccions FRIEND) + 2 línies d'allowlist a
  `read-db.py:126-135`.
- **Lliçó de disseny (verificada Q4+Q6):** les instruccions condicionals al
  PRINCIPI de plantilla s'ignoren sistemàticament (4 intents, 2 models,
  skill verificat com a fresc servit); al FINAL funcionen al primer intent.
  Estructura > prohibició.

## 8. Temes específics per alumne (`topics.txt`)

Un fitxer de text al perfil, `~/.fluent/<perfil>/topics.txt` (o `topics.md`), amb un tema
per línia. Model d'exemple: `data-examples/topics.example.txt`.

- **Què és un tema:** text lliure. Serveix una estructura gramatical (`present perfect`,
  `there is / there are`, `first conditional`), un tema de vocabulari i situació (`food and
  restaurants`, `at the doctor's`), una funció (`asking for directions`, `making
  suggestions`), una unitat de l'escola (`unit 4: describing people`) o una construcció
  concreta (`irregular past participles`, `prepositions of time`). Es pot afegir una pista
  després de dos punts o entre parèntesis: el tutor la llegeix tal qual.
- **On s'aplica:** només on el tutor escull ell el tema: 🎲 Mix, Writing, Speaking, Reading,
  Vocabulary, i els exercicis de la Lliçó que no tenen ítem de la cua ni patró assignat
  pel servidor. **Un ítem pendent o un patró assignat mana sempre.**
- **Com:** cada torn el servidor llegeix el fitxer i passa al tutor 2 temes (rota amb el
  dia i les respostes, perquè tots tinguin torn). El canvi val des del missatge següent, sense
  reiniciar; esborrar el fitxer ho atura. Sense fitxer, res canvia (nota nul·la).
- **Límits:** 30 temes, 160 caràcters per línia; línies buides, `#` i vinyetes s'ignoren.
- **Nivell:** el tutor l'aplica al nivell del perfil; si el tema és més difícil, en fa servir
  la forma més simple. Si el tema no encaixa a la pràctica (una estructura a Vocabulary),
  l'ignora.
- **Proves:** `scripts/fluent-bench.sh --topics --quick` escriu un `topics.txt` temporal,
  comprova que Writing hi va i que la Lliçó segueix manant la cua, i el restaura.
