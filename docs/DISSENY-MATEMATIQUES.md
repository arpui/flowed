# Disseny — mòdul d'aprenentatge de matemàtiques (fork paral·lel de FlowEd)

**Data:** 2026-10-04 · **Estat:** decisions D1–D10 validades per l'Albert (2026-10-05, totes segons la recomanació). **Fase 0 en execució**: fork creat a `~/projects/flowmath` (snapshot de l'estat de producció committat, `FLOWED_HOME=~/.flowmath`, web de proves a `4200` funcionant, fix del `lib-paths.sh` pel `FLOWED_HOME` de l'`.env`). **No toca res de `flowed` en producció.**

**Objectiu:** aprofitar el màxim de l'arquitectura de FlowEd (tutor d'idiomes amb LLM local) per construir un tutor de matemàtiques amb la mateixa base: competències, banc d'exercicis tancats amb correcció determinista, SM-2, lliçó del dia, camí de progrés i web multi-usuari. La diferència pedagògica central: en lloc de corregir frases, **l'alumne resol per operacions parcials (passos) que porten al resultat, i el sistema li demana i avalua els passos**.

---

## 1. Què hi ha avui i què és aprofitable

L'anàlisi completa és a `docs/ARQUITECTURA.md`; aquí només el que decideix el pla. La pregunta clau era: **el nucli és agnòstic del domini o està cablejat a idiomes?** Resposta: el nucli és agnòstic; el domini viu en ~10 cosses concretes (llistades a §3).

### 1.1 Maquinària reutilitzable tal com està (canvi de nom a part)

| Peça | Fitxers | Per què serveix igual per a matemàtiques |
|---|---|---|
| Servidor: HTTP+SSE, auth, sessions SQLite, sweeper, reconstrucció d'historial, rúting de model deep/face | `server/src/http.ts`, `db.ts`, `llm.ts`, `session.ts`, `index.ts` | No miren el contingut de l'exercici mai |
| Torn del tutor: composició del system prompt, càrrega de skill al system prompt, notes de progrés, guards, poda d'historial | `server/src/agent.ts` (2.528 l.), `pacing.ts` (2.111 l.), `commands.ts` | La lògica és de sessió i ritme, no d'idioma (excepte guards concrets, §3) |
| Lliçó del dia: pla diari, comptadors, badges, ratxa, fites | `server/src/daily.ts`, `pacing.ts`, gamificació a `update-db.py` | Genèrica |
| SM-2 complet (interval, EF, ratxes, cua, decaïment de mestria) | `hooks/update-db.py:212-237` + `db_schema.py` + golden test | Una taula de multiplicar o un procediment de fraccions es repassen exactament igual que una paraula |
| Persistència en dues capes (Capa A a cada idle, Capa B al tancament), idempotència per `session_id`, `.records/*.jsonl` com a autoritat | `hooks/accumulate-session.py`, `persist-session.py`, `update-db.py` | El que canvia és el *contingut* del registre, no el pipeline |
| Currículum com a `.md` de competències + camí de l'alumne derivat de fets + checkpoints + cursos/certificats | `hooks/curriculum.py` (1.891 l.), `learner-path.json`, `docs/ESQUEMA-APRENENTATGE.md` | El format (`Can do`, `Requires`, `Depth`, `Weight`, `Check`) és perfectament aplicable a competències matemàtiques. **L'Albert farà el currículum de matemàtiques** (decidit); el format ja existeix |
| Banc d'exercicis offline: tria determinista (fallats primer, no vistos fa 7 dies), targeta pintada pel servidor, correcció **sense model**, registre automàtic | `hooks/bank.py`, `server/src/bank.ts`, `config/fluent.json → exercises.bank` | El mecanisme és idèntic; només el **corrector** és específic d'idiomes (§4.3) |
| Web: xat SSE, botons de pràctica, panell de progrés, vista del camí, blocs màquina invisibles | `web/app.js` (~2.000 l.), `index.html`, `style.css` | Cal reetiquetar i afegir la interacció de passos (§4.5); el transport i el panell es queden |
| Provisió multi-usuari: `new-user.sh`, perfils `~/.flowed/<id>`, ports per perfil, `.env` per màquina, `flowed-check.py`, e2e i bench | `scripts/` | Tot per variable d'entorn; una segona instància en paral·lel no xoca (§5) |

### 1.2 La decisió estratègica que ja va a favor nostre

El projecte ja va fer (2026-09-24, `docs/PLA-EXERCICIS-TANCATS.md`) el gir que matemàtiques necessita des del primer dia: **els exercicis tancats es generen i validen fora de línia en un banc JSON, i el servidor tria, pinta i corregeix sense LLM** (mediana de prompt a Go: <2.000 tokens, pràcticament instantani). El model només queda per a la pràctica oberta. Per a matemàtiques això és encara millor que per a idiomes: **els ítems es poden generar amb plantilles paramètriques deterministes** (cap jutge LLM cal per validar-los: l'answer la calcula el generador).

---

## 2. Estratègia de fork: com fer-ho sense tocar producció

### 2.1 Mecànica

| Aspecte | Decisió proposada |
|---|---|
| Directori | `git clone /home/albert/projects/flowed ~/projects/flowmath` — el historial es conserva, i els *bugfixes* genèrics que surtin a producció es poden fer `cherry-pick` al fork (i a l'inrevés) |
| Marca | **FlowMath** (provisional). Skills/comandes/eines `fluent-*` → `math-*` |
| Dades | `FLOWED_HOME=~/.flowmath` (ja és una variable, `hooks/main_paths.py:41-55`); perfils `<nom>-math` (p. ex. `naia-math`) |
| Ports web | 4200+ (`FLOWED_WEBS="test-math:4200 …"` al `.env` del fork) |
| Models | **Remot de proves** (acord 2026-10-05): `192.168.31.102:12321`, idèntic al local (Qwen3-14B-Q4_K_M). Ja configurat al fork: `FLOWED_DEEP_BASE_URL` apuntant-hi i `FLOWED_DEEP_MANAGED=0` perquè cap script del fork en pugui un de local. **El model local (12322) només es puja quan calgui** — la feina s'organitza per no necessitar-lo: el camí del banc (Go/Review/Fets) no usa model, i l'únic que el necessita (e2e amb tutor, Fase 3) es pot provar contra el remot |
| Producció | Zero canvis a `~/projects/flowed`. El fork té el seu `.env`, els seus pidfiles (`/tmp/fluent-web-N.pid` → es reanomenaran), les seves proves |

### 2.2 El renombrat `fluent-` → `math-`: radiografia exacta

El prefix és una **convenció**, no una estructura. Està imposat per exactament 3 regexos i es compara literal a ~25 llocs:

- Regex: `server/src/tools.ts:190`, `server/src/commands.ts:38`, `server/src/pacing.ts:767` (`/^fluent-[a-z0-9-]+$/`).
- Comparacions literals de nom de comanda: `agent.ts` (línees 487, 513, 541, 552, 565, 583, 647, 1003, 1034, 1039, 1439-1446, 1643, 1654, 1695, 2170, 2249-2264, 2324, 2339-2344, 2356), `pacing.ts:1331,145,154`.
- Rutes HTTP `/api/fluent/*`: `http.ts:372-508` (9 endpoints) + client `web/app.js`.
- Web: `SLASH_RE` (app.js:293), `BUTTON_NAMES` (280-292), `MACHINE_BLOCK_RE` `` ```fluent: `` (262), `TRACKED_MODE_CMDS` (1054), `MODE_PLACEHOLDERS` (1636-1645).
- Noms d'eina: `fluent_record_answer`, `fluent_deep_evaluate`, `fluent_setup_profile` (`tools.ts:232,321,456`).
- Identitat de sessió/BD: slug `"fluent"` (`session.ts:16`), `proj_fluent` i `providerID: "fluent-deep"` (`db.ts:49,167`), títol `"Fluent"`.
- Permisos: filtre `skill: "fluent-*"` a `prompts/agents/learner.md`.
- Blocs màquina: `` ```fluent:review_results `` (`persist-session.py:380`, `pacing.ts:145,154`, `agent.ts:2324`).
- Fitxers: 11 directoris `skills/fluent-*`, 10 fitxers `prompts/commands/fluent-*.md`, `results/<slug>-fluent-learn-*.md` (patró del sweeper `index.ts:307-317`).

**Recomanació:** fer el renombrat al fork **en un sol commit mecànic al principi** (amb la suite de ~460 tests com a xarxa de seguretat: molts tests contenen literals `fluent-*` i caldrà actualitzar-los al mateix commit). Així tot el treball posterior de contingut matemàtic es fa sobre noms nets, i el diff amb producció queda aïllat en un sol commit fàcil d'identificar. L'alternativa (conservar `fluent-` al fork) fa el diff amb producció més petit però arrossega confusió de per vida.

### 2.3 Integració futura (després, quan el fork demostri el valor)

Quan els dos productes funcionin, hi ha dues sorts d'integració, no una:

1. **Xarxa de seguretat compartida** (immediata i contínua): qualsevol *bugfix* del nucli (pacing, persistència, streaming, guards) es cherry-pick entre els dos repos. Això no requereix res més que mantenir el historial comú.
2. **Extracció del nucli** (tardana, opcional): convertir els punts de §3 en un **adaptador de domini** — un mòdul per domini que exporti: taxonomia d'errors, rúbrica d'avaluació oberta, corrector del banc, escala de nivells, tipus d'exercici, etiquetes. Un sol servidor que arrenca amb `domain: language | math`. Dificultat gran; no cal decidir-ho ara, però el fork s'ha de fer de manera que no ho impossibili (per això el renombrat en un sol commit i el contingut de domini en fitxers separats).

---

## 3. Els punts de coupling del domini (què s'ha de canviar, amb `file:line`)

Aquesta és la llista tancada — tot el servidor i hooks que no hi surt es clona igual.

| # | Acoblament | On | Destinació matemàtica |
|---|---|---|---|
| C1 | Taxonomia de 15 categories d'error gramatical (SSOT + àlies + test de sincronia TS↔PY) | `hooks/db_schema.py:28-86` ↔ `server/src/tools.ts:43-76` ↔ skills + `references/feedback-template.md` ↔ `tests/test_error_categories.py` | Taxonomia d'error matemàtic (§4.4) |
| C2 | Corrector del banc: `canon()` (contraccions, xifres→paraula), OSA ≤1, guàrdia d'infleccions, extracció del buit | `hooks/bank.py:20-94,203-232` | Corrector aritmètic/expressionals (§4.3) |
| C3 | Rúbrica del `fluent_deep_evaluate` (forma de correcció lingüística, severitat, «judge in the target language») | `tools.ts:78-111` | Rúbrica matemàtica (error de càlcul vs de procediment, valorar raonament) |
| C4 | Escala CEFR i camps de llengua: `CEFR` array, `target_language`/`native_language`, `cefr_level`, `pos`/`forms` | `tools.ts:453-473`, `learner-profile.json`, `read-db.py`, `session-start.py`, `pacing.ts:667,815-837`, `app.js:388-389,1426` | Escala de nivells matemàtics (§6, decisió D3) |
| C5 | Guards i notes de llengua: `vocabularyDueNote`, `languageDirectionGuard`, `foreignScript*`, `_NATIVE_RE` (detector de català), regla d'articles | `pacing.ts:906-957,1346-1363,2046-2094`, `update-db.py:534-537` | Fora o adaptats (matemàtiques: guard de notació, §4.6) |
| C6 | Tipus d'exercici del banc: `complete \| choose \| meaning \| translate \| correct` | `bank.ts:20`, `bank.py`, regles V1-V11 del pla | `compute \| choose \| compare \| steps \| word` (§4.1) |
| C7 | Clau d'habilitats: `writing/speaking/vocabulary/reading/listening` (comptadors, mastery-db, panell) | `http.ts:82`, `daily.ts:26-33`, `app.js:1343-1349`, `update-db.py` | `computation/steps/problems/reasoning/facts` (§4.1) |
| C8 | Format de feedback en prosa: regex `"wrong" → **"right"** (categoria)` i `**Score: N/10**`; bloc `fluent:review_results` | `persist-session.py:204,218,380,481`, `bank.ts:71-94`, `app.js:262,1713` | Format amb traça de passos (§4.5); el `Score: N/10` es conserva |
| C9 | TTS (piper, `[[say]]`, veus per idioma) | `tts.ts`, `http.ts:453-476`, `rules.md`, `app.js:116-239` | **Apagat** a matemàtiques (decisió D8) |
| C10 | Contingut: currículum `en-A1/A2.md`, bancs JSON, skills, comandes, `rules.md`, `AGENTS.md`, `LEARNING_SYSTEM.md` (fòssil en neerlandès!), `bench/learner-a1.md`, plantilles `data-examples/` | tota la capa Markdown + `curriculum/` | Contingut matemàtic (§4, currículum el fa l'Albert) |

Més el renombrat estructural de §2.2 (C0).

---

## 4. Disseny pedagògic del domini matemàtic

### 4.1 Tipus d'exercici (paral·lel amb els d'idiomes)

| Pràctica FlowEd | Equivalents matemàtics | Camí |
|---|---|---|
| 🎲 Go (banc tancat) | **Càlcul i procediment tancat**: `compute` (resultat únic), `choose` (tria l'operació/ resultat), `compare` (>, <, =), **`steps` (operacions parcials — la peça nova, §4.2)** | Banc + servidor, sense model |
| 🎓 Review (SM-2 sobre el banc) | Idèntic: els ítems fallats (també els de `steps`) entren a la cua amb l'id del banc | Banc + servidor |
| 📚 Vocab (flashcards) | **Fets i definicions**: taules de multiplicar, dobles/mitats, equivalències (½=0,5), vocabulari («el doble de», «la meitat de», «quants en falten per…») | Banc + servidor |
| 📝 Writing (producció oberta) | **Resolució oberta / raonament**: «explica com ho has resolt», «inventa un problema que es resolgui amb 3/4+1/8», error-correction explicat | Model + rúbrica (C3) |
| 📖 Reading | **Problemes verbals**: text curt + preguntes; es pot fer tancat (banc) o obert (model) | Banc o model |
| 🗣️ Speaking | **Math talk** (opció futura): situació oral resolta per text | Model |
| 🧪 Test de nivell | Checkpoint amb `Check:` del currículum matemàtic (`Compute`/`Steps` tancats) | Servidor, sense model (ja existeix) |

Comptadors d'habilitat (C7) → `computation`, `steps`, `problems`, `reasoning`, `facts`.

### 4.2 La peça nova: exercicis per passos (operacions parcials)

És la diferència central respecte a idiomes que demanaves: la resposta no és una frase a corregir sinó una **traça d'operacions parcials**, i el sistema avalua cada pas.

**Esquema d'ítem `steps`** (extensió de l'ítem de banc existent, `curriculum/bank/…`):

```json
{
  "id": "m4.frac_unlike.014",
  "competence": "m4.fractions_add_unlike",
  "type": "steps",
  "instruction": "Resol-ho pas a pas. Una línia per pas.",
  "problem": "1/4 + 3/8",
  "method": "common_denominator",
  "steps": [
    {"n": 1, "expect": "2/8 + 3/8",  "accept": ["2/8+3/8"], "error_class": "procedure",
     "why": "Escriu 1/4 com a 2/8 (denominador comú 8)."},
    {"n": 2, "expect": "5/8",        "accept": [], "error_class": "calculation",
     "why": "Suma numeradors; el denominador no canvia."}
  ],
  "answer": "5/8",
  "why": "…",
  "status": "generated | validated | reviewed"
}
```

**Interacció — recomano començar amb «tot de cop» (v1) i fer l'incremental (v2) després:**

- **v1 (una sola resposta):** l'alumne escriu la descomposició sencera al quadre (una línia per pas, amb o sense `=`). El servidor parteix per línies, avalua cada línia contra el pas esperat (o els `accept`), i respon amb la traça anotada: ✅/❌ per pas, el `why` del primer pas fallat, i `Score: N/10` ponderat. **No cal cap màquina d'estats nova al servidor** — és un torn normal del camí del banc amb un corrector que llegeix línies. Reutilitza targeta, registre, SM-2 i comptadors tal com estan.
- **v2 (pas a pas):** el servidor manté l'estat «ítem + pas N pendent» (com ja fa amb `gradingItem` per a la cua) i demana un pas per torn, amb reintent quan un pas falla. Més ric pedagògicament, més feina a `agent.ts` (WP2.2).

**Avaluació per pas:** cada línia es normalitza (`"1/4 + 3/8 = 2/8 + 3/8"` → costat esquerre/dret), s'avalua amb fraccions exactes i es compara amb el pas esperat. Un pas pot coincidir en **valor** (acceptar variants vàlides: `2/8+3/8` o directament `5/8` al pas 1 si el mètode ho permet → es declara a `accept`) o exigir la **forma** del mètode. El primer pas fallat determina l'error; els passos posteriors no es castiguen dues vegades (l'error es propaga, no es compta com a error nou).

**Sortida a dades:** el registre `.records` s'estén amb `steps: [{n, ok, got}]` (additiu, no trenca res); el patró d'error es crea amb `pattern_id` de la classe del pas fallat (`error_class` + competència), de manera que «sempre oblida el denominador comú» es converteix en un patró feble que la Lliçó torna a atacar — mateixa mecànica que `heal_patterns` amb els errors gramaticals.

### 4.3 Corrector matemàtic (substitut de `canon`/OSA)

A `hooks/bank.py` (o un `hooks/mathgrade.py` nou, recomanat per no barrejar):

- **Avaluador d'expressions** amb `ast.parse(mode="eval")` restringit a `+ - × ÷ / ( ) ^`, enters, decimals i fraccions `a/b` → `fractions.Fraction`. **Sense dependències** (els hooks són stdlib-pure i la CI ho valida). Equivalència = mateix valor (la commutativitat i les variants algebraiques simples cauen soles); comparació de forma només quan l'ítem ho demana.
- **Veredictes** (paral·lel als actuals correct=10 / typo=7 / wrong=3 / empty=0): `correct` 10; **«gairebé» 7** = transposició de dígits o dígit de més/menys (anàleg exacte de l'OSA lingüístic: «342» per «324», «becuase»→«because»); `wrong` 3 amb `why`; `empty` 0.
- **Unitats:** si l'ítem en porta, es comparen separatament i una unitat errònia és 🟡, no 🔴.
- **Notació tolerant:** `,` decimal, `×`/`*`/`·`, fraccions mixtes `1 1/2`, espais.

### 4.4 Taxonomia d'errors matemàtics (substitut de C1)

Proposta inicial de 12 classes (el SSOT continua sent `db_schema.py` ↔ `tools.ts` ↔ skills, amb el mateix test de sincronia):

`calculation` (lliscada de càlcul) · `sign` (signe) · `place_value` (valor posicional) · `carrying` (transport/arrestando) · `order_of_operations` · `wrong_operation` (tria l'operació equivocada) · `procedure` (sequència de passos incorrecta) · `facts` (no es recorda el fet bàsic) · `simplification` (fracció no simplificada / forma) · `unit` · `misread` (llegeix malament l'enunciat) · `incomplete` (deixa la feina a mitges).

Els àlies (`carry` → `carrying`, `ordre d'operacions` → `order_of_operations`…) segueixen el mateix patró que els àlies gramaticals actuals.

### 4.5 Web: visualització diferent

- **Traça de passos:** el feedback d'un `steps` es pinta com una llista de línies amb ✅/❌ al costat i el `why` del primer fallat (el markdown de sempre ho permet; `paintFeedback` de `app.js` s'adapta, WP2.5).
- **Entrada:** el placeholder passa a «Escriu una operació per línia…»; per a `compute`, teclat numèric (`inputmode="numeric"`) al compositor mòbil.
- **Notació:** per a primària, Unicode prou (`× ÷ ½ ⅓ ² ³ ∠ °`) i fraccions `a/b`. **KaTeX no cal al principi**; si més endavant cal fracció vertical, és un afegit aïllat (decisió D7).
- **Panell de progrés:** mateixes dades (estrelles, tendència, patrons febles, camí) amb etiquetes matemàtiques; afegir «precisió per pas» quan existeixin registres `steps` (WP4).
- **Fora:** botons 🔊 TTS i marcadors `[[say]]`.

### 4.6 Currículum matemàtic (l'Albert l'autoreja)

El format `.md` de `curriculum/` es conserva amb tres adaptacions:

- Front matter: `language: math` (el camp es continua anomenant `language`; `find_curriculum` fa match amb el perfil), `level: m1…m6` (escala per decidir, D3).
- `Forms:` → descripció del procediment; `Words:` → vocabulari del problema verbal; `Tags:` → paraules clau de l'error (`#carrying`, `#fractions`…); `Signals:` es conserva per al guard de competència.
- `Check:` amb tipus nous `Compute:` i `Steps:` (tancats, comparables pel corrector §4.3) — els checkpoints i la prova de nivell ja funcionen amb checks tancats.

**Generació del banc:** a diferència d'idiomes (on calia generar amb LLM i filtrar amb jutge), el banc matemàtic es genera amb **plantilles paramètriques** (`scripts/mathbank.py`: «suma amb transport, 2 xifres», «fraccions amb denominadors no relacionats», N mostres, answer calculada pel mateix avaluador). Validació V-matemàtiques: answer única, pas a pas coherent amb l'avaluador, no repetits. Revisió humana per mostreig, com a idiomes. Això elimina el cost del jutge LLM i el soroll del 50 % d'ítems dolents.

---

## 5. Paquets de feina, dificultat i paral·lelització

Dificultat: 🔴 gran · 🟡 mitjana · 🟢 petita. Tots al fork; cap toca `flowed`.

### Fase 0 — Fork operatiu

| WP | Què | Dificultat | Depèn de |
|---|---|---|---|
| 0.1 | Clone a `~/projects/flowmath`, `.env` propi (home `~/.flowmath`, webs 4200+, model compartit), perfil `test-math`, arrencar i passar el smoke e2e amb el contingut d'idiomes (encara anglès) | 🟢 | — |
| 0.2 | **Commit de renombrat** `fluent`→`math`: 3 regexos, ~25 comparacions `agent.ts`, rutes `http.ts`+client, eines, slug/sessions, skills/commands (renomenar directoris), bloc `math:review_results`, pidfiles, i tots els tests amb literals | 🟡 (mecànic però ampli; la suite de ~460 tests el valida) | 0.1 |
| 0.3 | Neteja del que matemàtiques no usa: TTS apagat, guards de llengua/escriptura fora (`foreignScript*`, `languageDirectionGuard`, `vocabularyDueNote`), `LEARNING_SYSTEM.md` nou (el vell és un fòssil en neerlandès) | 🟢 | 0.2 |

### Fase 1 — Matemàtiques tancades funcionals (el producte mínim)

| WP | Què | Dificultat | Depèn de |
|---|---|---|---|
| 1.1 | Currículum matemàtic `.md` (1 nivell pilot, p. ex. m4) — **feina de l'Albert**, format documentat a §4.6 | 🟢 (contingut) | decisió D3 |
| 1.2 | `hooks/mathgrade.py`: avaluador `ast`+`Fraction`, normalització de notació, veredictes, «gairebé» per transposició | 🟡 | — |
| 1.3 | `bank.py`: nous tipus `compute/choose/compare`, endollar `mathgrade`, progress | 🟡 | 1.2 |
| 1.4 | Taxonomia d'errors matemàtica: `db_schema.py` + `tools.ts` + skills + test de sincronia | 🟢 | — |
| 1.5 | Generador de banc `scripts/mathbank.py` (plantilles paramètriques + validació + estat `reviewed`) | 🟡 | 1.2 |
| 1.6 | Skills i comandes matemàtiques: `math-learn`, `math-review`, `math-facts`, `math-problems` (obert), `math-end`, `math-setup`; reescriure `rules.md` i `AGENTS.md` (identitat tutor de mates, format de feedback amb traça) | 🟡 | 0.2 |
| 1.7 | Perfil i nivells: camps `grade/level` matemàtics a `math_setup_profile`, `new-user.sh`, `read-db.py`, `session-start.py`; escala D3 al web (`CEFR_ORDER` → escala matemàtica, gating de Reading→problemes) | 🟡 | D3 |
| 1.8 | Web: etiquetes/botons/placeholders, teclat numèric, Unicode matemàtic; panell amb etiquetes noves | 🟢 | 1.6 |
| 1.9 | Posar al dia la suite de tests (molts tenen literals d'idioma) + un e2e matemàtic bàsic | 🟡 | tot F1 |

Amb la Fase 1 ja hi ha un tutor de matemàtiques usable: Go/Review/Fets sobre banc (sense model, instantani), Lliçó del dia, SM-2, camí, checkpoints, ratxes.

### Fase 2 — Passos / operacions parcials (la peça demanada)

| WP | Què | Dificultat | Depèn de |
|---|---|---|---|
| 2.1 | Esquema `steps` + generador amb passos (plantilles amb traça) | 🟡 | 1.5 |
| 2.2 | Corrector per línia: partició, avaluació per pas, propagació d'errors, ponderació de nota | 🟡 | 1.2, 2.1 |
| 2.3 | **v1 «tot de cop»:** targeta amb la traça buida, feedback anotat pas a pas, registre amb `steps[]`, patró d'error per `error_class` | 🟡 | 2.2 |
| 2.4 | Web: render de traça ✅/❌ per pas, placeholder multi-línia | 🟢 | 2.3 |
| 2.5 | **v2 incremental:** estat «pas N pendent» per sessió a `agent.ts` (anàleg a `gradingItem`), reintent de pas, nota de progrés per pas | 🔴 | 2.3 |

### Fase 3 — Pràctica oberta matemàtica

| WP | Què | Dificultat |
|---|---|---|
| 3.1 | Rúbrica matemàtica del `math_deep_evaluate` (C3): jutja procediment i raonament, no gramàtica | 🟡 |
| 3.2 | Problemes verbals: banc (tancat) + variant oberta amb model | 🟡 |
| 3.3 | «Explica el teu raonament» (anàleg Writing) amb guards matemàtics (no demanar llistes, exigir justificació) | 🟡 |
| 3.4 | Bench de models per a tasques obertes de mates (patró `flowed-tutorbench.py` + `bench/learner-math.md`) | 🟡 |

### Fase 4 — Visualització i progrés matemàtic

| WP | Què | Dificultat |
|---|---|---|
| 4.1 | Precisió per pas i fluïdesa de càlcul al panell i a `read-db.py` | 🟢 |
| 4.2 | Visuals per competència (recta numèrica, barres de fraccions) — només si el paper ho demana | 🟡 |
| 4.3 | KaTeX/fracció vertical si la notació Unicode es queda curta | 🟡 |

### Fase 5 — Integració (tardana)

| WP | Què | Dificultat |
|---|---|---|
| 5.1 | Cherry-pick continu de bugfixes del nucli entre els dos repos | 🟢 (procediment) |
| 5.2 | Extracció del nucli compartit + adaptador de domini (`domain: language\|math`) | 🔴 |

**Paral·lelització per agents:** dins la Fase 1, els WPs 1.2, 1.4, 1.6 i 1.7 són independents entre si (es poden encarregar a agents en paral·lel després de 0.2); 1.3 i 1.5 esperen 1.2; 1.8-1.9 al final. A la Fase 2, 2.1 i 2.2 es poden preparar abans; 2.3-2.4 són seqüencials; 2.5 és l'únic 🔴 i es pot ajornar sense frenar el producte.

---

## 6. Decisions a prendre abans de començar

| # | Decisió | Opcions | Recomanació |
|---|---|---|---|
| D1 | Directori i marca del fork | `flowmath` / altre | `~/projects/flowmath`, marca FlowMath |
| D2 | Renombrar `fluent-*`→`math-*` al fork | ara (1 commit) / mai | **Ara**, després de 0.1 i abans de qualsevol contingut |
| D3 | Escala de nivells | cicle curricular (1r-6è), `m1…m6`, o reutilitzar A1/A2 | `m1…m6` (ids estables, mateixa mecànica de cursos/certificats); el currículum pilot decideix l'abast |
| D4 | Generació del banc | plantilles paramètriques deterministes / LLM+jutge com a idiomes | **Plantilles**: l'answer la calcula el generador; zero jutge LLM |
| D5 | Interacció de passos | v1 tot-de-cop (parsejar línies) / v2 pas a pas amb estat | **v1 primer**, v2 com a WP2.5 després |
| D6 | Avaluador d'expressions | stdlib `ast`+`Fraction` / sympy | **stdlib** (els hooks són stdlib-pure; fraccions exactes gratuïtes) |
| D7 | Notació al web | Unicode / KaTeX | Unicode; KaTeX només si cal fracció vertical (WP4.3) |
| D8 | TTS a matemàtiques | keep / off | **Off** (no hi ha llengua meta que sentir) |
| D9 | Quines pràctiques obertes a la v1 | problemes verbals + raonament / cap | Problemes verbals sí (és on el model aporta); `math talk` després |
| D10 | Models compartits o propis | mateix endpoint 12322 / port propi | **Resolt (2026-10-05):** proves contra el remot `192.168.31.102:12321` (idèntic); el model local es puja només quan calgui |

## 7. Riscos

| Risc | Mitigació |
|---|---|
| El fork divergeix de producció i es perden *bugfixes* | Historial comú (clone, no rsync) + cherry-pick (WP5.1); el renombrat aïllat en un commit facilita el rebuig de diffs |
| La suite heretada (~460 tests) està plena de literals d'idioma i es torna soroll | Actualitzar-los dins el WP0.2/1.9, no desactivar-los; aquests tests són precisament la xarxa del renombrat |
| Qualitat del 14B en tasques obertes de mates (raonament) — no mesurada | El camí tancat (banc) no depèn del model; per a l'obert, bench propi (WP3.4) abans d'activar res amb alumnes reals |
| Ambigüitat en correcció de passos (variants vàlides no previstes a `accept`) | L'avaluador compara **valor** per defecte i només exigeix forma quan l'ítem ho declara; el «gairebé» cobreix transposicions; banc revisat per mostreig |
| Falsa sensació de progrés si els passos es puntuen malament (error propagat com a diversos errors) | Regla de propagació única a WP2.2 + tests de traça (com el golden test d'SM-2) |
| Duplicació de manteniment (dos repos) | Acceptada i deliberada: producció intocable; la integració (Fase 5) es decideix amb dades, no ara |

## 8. Seqüència suggerida

1. **Decidir D1-D10** (aquest document).
2. **Fase 0** (1 sessió d'agent): fork + renombrat + neteja → el fork arrenca i passa l'e2e.
3. **Fase 1** en paral·lel: l'Albert autoritza el currículum pilot (1.1) mentre agents fan 1.2/1.4/1.6/1.7 i després 1.3/1.5/1.8/1.9. Resultat: tutor de mates tancat funcionant a `test-math:4200`.
4. **Fase 2 v1** (2.1-2.4): operacions parcials tot-de-cop. És el que demanaves; amb v1 ja es pot validar amb l'alumne real.
5. **Fase 3** i **2.5** segons el que digui l'ús real.
6. **Fase 5** quan els dos productes s'hagin estabilitzat.
