# Running the core — el que hi ha en el repo, còm a cò (2026-10-07)

This document is the operational map of the unified core (WP5.2). Read it with
`docs/CORE-AND-DOMAINS.md` (the architecture) and `docs/DISSENY-MATEMATIQUES.md`
(the plan).

## 1. Què ès el repo now

The repo (branch `wp52-core`) is ONE product: the core engine `flowed` + two
domains, `language` and `math`. Nothing is forked anymore; a domain is data +
adapter (see CORE-AND-DOMAINS.md).

```
server/            core engine (Bun/TypeScript): agent, pacing, bank, steps,
                   http, tools, commands + domain-language.ts (language adapter)
hooks/             core Python: SM-2, update-db, accumulate/persist-session,
                   read-db, curriculum engine, mathgrade (math grader)
                   + domain.py (the domain resolver)
web/               the learner UI (one shell; the button bar swaps by domain)
scripts/           orchestration: new-user.sh, flowed-web.sh, flowed-e2e.py,
                   mathbank.py, lib-paths.sh (loads .env BEFORE resolving home)
config/domain.json THE MANIFEST — the single authority for what a domain is
curriculum/        domain data: en-*.md (language) + math-m*.md (math)
curriculum/bank/   domain data: en-A1/A2 (language) + math-m4/m7 (math)
skills/            domain tutor layer: fluent-* (language) + math-* (math)
prompts/commands/  domain tutor layer: fluent-*.md + math-*.md
prompts/agents/    rules.md (shared) + rules-math.md + rules-language.md
```

Homes (where the learners' data lives — NOT in the repo):
- `~/.flowed` — this fork/core's home (the `.env` sets `FLOWED_HOME`; the
  `.env` is gitignored, so a fresh worktree without it falls back to
  `~/.flowed` — that is exactly the bug the lib-paths fix addresses; when
  running from a worktree, export `FLOWED_HOME` explicitly).
- `~/.flowed` — the language product's production home (untouched).
- `~/.fluent` — legacy, only while it has not been moved.

## 2. Ports per user (one instance per learner)

Each profile gets its own web instance, its own 6 DBs and its own password:

```bash
scripts/new-user.sh <id> --port <N>            # provision (profile + dbs + password)
scripts/flowed-web.sh --app <id> --port <N>    # start; prints login + password
scripts/flowed-web.sh --stop --port <N>        # stop one instance
```

The password lives in `~/.flowed/<id>/.web-password` (stable across
restarts). Ports in use now: 4200 test-math, 4201 test-m7, 4203 albert-math,
4205 test-lang (the language test). Production `flowed` keeps its own ports in
its own repo/home — the two never collide.

## 3. Com funciona tot (the flow of one turn)

1. The learner presses a button. The web sends the DOMAIN command name
   (`fluent-review` for a language profile — `app.js` swaps the prefix and the
   labels from `window.__FLOWED_DOMAIN`, which the server injects into the
   shell from the manifest rule).
2. `agent.ts` canonicalizes it for the LOGIC (`cmdKey`: `fluent-review` ≡
   `math-review` — the engine is domain-neutral) but loads the RAW name
   (`prompts/commands/fluent-review.md`).
3. The turn runs on the bank path (no model: Go/Review/Facts over declared
   banks) or the model path (open practices). Grading: math → `mathgrade`
   (polynomial equivalence); language → the bank's word/grammar paths.
4. The answer lands in `.records/<session>.jsonl` (one record, with the steps
   trace when it is a steps item) — the AUTHORITY.
5. Capa A (`accumulate-session.py`) folds it into the 6 DBs at every idle;
   Capa B (`persist-session.py`) finalizes on `/X-end` and after 30 min. Both
   key on the SQLite live session id (the WP5.1 rotation fix).
6. `read-db.py` summarizes (now also `computed.domain` and
   `computed.steps_precision`); the panel renders it.

## 4. Testar-lo here before production (the exact recipe)

Suites first (cheap, no model):

```bash
python3 -m unittest discover -s tests        # 767 OK (math + domain loader + taxonomia)
(cd server && bun --test test/*.test.ts)     # 17 harnessos OK (també amb `node --experimental-strip-types server/test/<x>.test.ts`)
(cd server && bun x tsc --noEmit)            # 0 errors (http.ts i web-render arreglats 2026-10-08)
```

Live, per domain (needs the remote model for the open practices; the bank
path runs without it):

```bash
# math (already the reference): profile test-m7, scenario algebra
FLOWED_HOME=$HOME/.flowed python3 scripts/flowed-e2e.py test-m7 --port 4201 --scenario algebra

# language (WP5.2): provision once, then the language scenario
FLOWED_HOME=$HOME/.flowed bash scripts/new-user.sh test-lang --port 4205
# (patch the profile: domain=language, target English, level A2 — or run /math-setup)
FLOWED_HOME=$HOME/.flowed bash scripts/flowed-web.sh --app test-lang --port 4205
FLOWED_HOME=$HOME/.flowed python3 scripts/flowed-e2e.py test-lang --port 4205 --scenario language --password <pw>
FLOWED_HOME=$HOME/.flowed bash scripts/flowed-web.sh --stop --port 4205
```

Verified today: the `language` scenario passes 4/4 (fluent commands load, a
`grammar` record lands, the curriculum resolves to the language course,
`fluent-review` opens the lesson through the canonical keys).

### Tot d'una: `scripts/flowed-verify.sh` (2026-10-08)

Suites + e2e en directe (language a `test-lang`:4205, algebra a `test-m7`:4201)
contra el model remot, amb `FLOWED_HOME=~/.flowed` i `FLOWED_DEEP_MANAGED=0`.
Es nega a córrer contra `~/.flowed`/`~/.fluent` o un perfil que no sigui de prova.
Informe a `results/verify-<data>/summary.md` + un `.log` per pas i les
transcripcions dels e2e. `TUTORBENCH=1` hi afegeix el tutor bench.

Per a un agent (Claude Code a railab): skill `flowed-verify` — executa el
script, classifica cada fallada (codi / model / entorn) amb evidència i deixa
`results/verify-<data>/ANALISI.md` amb el veredicte.

### Taxonomia per domini (2026-10-08, WP6)

Les habilitats i les categories d'error són **del domini**, no del nucli:

| | math | language |
|---|---|---|
| habilitats | computation · steps · problems · reasoning · facts | writing · speaking · vocabulary · reading · grammar · listening |
| categories d'error | les 12 de mates | les 15 de language (+ 5 antigues) |
| si no la reconeix | `calculation` | `grammar` |

Abans el nucli només coneixia les de mates: `grammar` es desava com a `computation`
(Càlcul a les Stats), `vocabulary` com a `facts`, i «I went» com a `calculation_I_went`.
Ara cada punt pregunta el domini del perfil (`hooks/db_schema.py`, `server/src/taxonomy.ts`;
dos mirall, `tests/test_taxonomy.py` els manté iguals). El panell només llista les
habilitats del domini i amaga «Precisió per pas» a language. L'eina de registre i el
ritme de la Lliçó també són del domini.

- **Auditar un perfil:** `python3 scripts/flowed-check.py taxonomy <perfil>` (o `--dir`):
  surt 1 si hi troba habilitats o categories d'un altre domini.
- **Coherència registres ↔ BDs:** `python3 scripts/flowed-check.py reconcile <perfil>` (o `--dir`): cada
  registre ha de veure's a progress, mastery, mistakes, session-log i SM-2; exit 1 si no.
- **Perfil nou de language:** `scripts/new-user.sh <id> --domain language` i
  `scripts/flowed-profile.py <id> --domain language --name … --native Catalan --target English --level A1 --goal A2`
  (plantilles a `data-examples/language/`). Abans tots els perfils sortien de les plantilles de mates.
- Compte: `test-lang` va rebre registres de mates (tutor bench d'abans) i té dades barrejades;
  és perfil de prova, es pot refer amb les dues comandes de dalt.

### Provar a mà a railab: `scripts/flowed-dev.sh` (2026-10-08)

Engega les webs de prova (`test-lang`:4205, `test-m7`:4201) contra el model
remot, sense exportar res al terminal: `scripts/flowed-dev.sh up | status | down`.
Només perfils `test*/demo*/e2e*` de `~/.flowed`. Altres perfils o ports:
`DEV_WEBS="test-lang:4205 test-nes:4206" scripts/flowed-dev.sh up`.

### Canvis del 2026-10-08 (després de la verificació)

- **Mates sense pràctiques obertes.** `config/domain.json` → `open_practices`:
  language `["speaking","writing","reading"]`, math `[]`. A mates, un model
  general inventa enunciats que no quadren i no pot comprovar un càlcul. La web
  amaga els botons (el servidor injecta `window.__FLOWED_OPEN`), el servidor
  respon sense model si arriba una comanda tancada (`closedPracticeTurn`) i
  l'objectiu diari no les demana. Reactivar-les (model entrenat per a mates) =
  afegir-les a la llista del manifest; el codi hi és.
- **«No fa la pregunta següent»** (6 de 26 respostes al tutor bench): a les
  pràctiques obertes, si la resposta puntua i després de la nota no hi ha res a
  fer (cap encapçalament, cap «?», cap «escriu/torna-ho a provar»), `turnGuard`
  demana reescriure només l'exercici i es conserva el feedback
  (`hasNextAfterScore`, `openPracticeAnswered`).
- **Prova de problemes per passos (m7):** competència `m7.problems_generic`
  `[extra]` (secció «D. Problemes (prova)»), 2 problemes amb enunciat a
  `curriculum/bank/math-m7/steps/m7.problems_generic__steps.json`, corregits per
  passos sense model. El validador de `mathbank.py` accepta `expression` als
  ítems de passos amb enunciat.
- Proves: `server/test/open-practices.test.ts`; tutor bench i verify salten les
  pràctiques que el domini no fa.

## 5. Git: què hi ha unpushed, i dnde el push cal go

- `origin` is `git@github.com:arpui/flowed.git` — the LANGUAGE product's repo.
  The fork's whole history (45+ commits, now the unified core) has never been
  pushed; `origin/main` is still `74d73a0` v0.5.0.
- Branches: `main` (fork WP0–WP3), `wp41-head` (WP4.1), `wp52-core` (WP4.1+WP5.2);
  in the `flowed` repo: `wp51-integration` (the 5.1 cherry-picks).
- Decision to make BEFORE pushing: the unified core is no longer "the math
  fork" — pushing `wp52-core` to `arpui/flowed` would publish the whole
  unified history into the language repo. Recommended: give the core its own
  private repo (e.g. `arpui/flowed-core`) and keep `arpui/flowed` for the
  language product until it retires. Then:
  `git push -u origin wp52-core` (this repo, new remote) — never force-push,
  never push over `main` of the other repo.
- Until then everything lives locally; `git merge wp52-core` into `main` is
  the local integration step.

## 6. Com s'ha dividit i gestionat tot

- The CORE never mentions a domain: the manifest (`config/domain.json`) is the
  only place that knows `language`/`math`; `hooks/domain.py` + `agent.ts
  domainForSession()` + `http.ts` are its three readers (same rule, one
  definition).
- A profile declares its domain (`domain` field) or the level scale decides
  (A1..C2 → language, m1..m7 → math). Existing math profiles are untouched —
  the default is math.
- A future domain = one manifest entry + its dirs (the checklist in
  CORE-AND-DOMAINS.md). Nothing in the core changes.

## 7. Known polish (honest list)

- The web button LABELS swap by domain is code-complete but not e2e-proven
  (the e2e presses commands through the API, not the DOM).
- The TTS gate by domain is code-complete; not exercised (no voice turn in the
  language scenario).
- `curriculum/en-A2.md` declares no `Bank:` competences — the language bank
  path falls to the model today; declaring banks for the language competences
  (like math's) would make Go/Review model-free too.
- The ladder places a new learner at the LOWEST uncertified level of the
  subject (test-lang opened en-A1, not en-A2) — same known-by-design behavior
  as math's m7 story.
- Cleanup owed: a stray empty `~/.flowed/test-lang` profile was created during
  provisioning from a worktree without `.env` — delete it
  (`rm -rf ~/.flowed/test-lang`).
