# Disseny — mòdul d'aprenentatge de matemàtiques (fork paral·lel de FlowEd)

**Data:** 2026-10-06 · **Estat:** decisions D1–D10 validades per l'Albert (2026-10-05, totes segons la recomanació). **Fase 0, Fase 1 sencera (WP1.1 inclòs: escala m7 + avaluador algebraic + currículum math-m7 + pilots d'm4 + checkpoints Compute:/Steps: — `dd4c3b1`·`4b35f92`·`eb30834`·`ad4abbb`·`b88c3f2` —, verificat en viu amb el perfil `test-m7:4201` i l'escenari e2e `algebra`), Fase 2 sencera (WP2.1–2.5) i Fase 3 sencera (WP3.1 rúbrica + WP3.3 raonament obert, `f56075a`; WP3.2 problemes verbals tancats+oberts, `0568b11`; WP3.4 bench de tasques obertes, `53af5a8`) feta.** L'e2e math passa en viu (lesson/steps/steps2/go/review/facts/reasoning/problems + el nou `algebra` d'm7, RC=0) contra el remot. **Candidats a cherry-pick a `flowed` (producció), a més del de `lib-paths.sh`:** els 3 fallos de producte que l'e2e va destapar i l'WP1.9 va arreglar al fork — (1) rotació de sessió: el número es parsejava del transcript on mai hi és → tot queia a `session-001` i l'update-db restaurava un sol T0 barrejant sessions; (2) `tryBankReviewTurn` perdia el primer ítem de la cua perquè `pacingNote` el preassignava a `usedItems` (reforçat a `e54ce63`: el camí del banc manté la seva pròpia llista `bankUsedItems`, separada de la del model); (3) bucle infinit del sweeper amb sessions sense res a persistir (exit 1 → reintent cada minut); (4) `CORRECTION_RE` de `pacing.ts` (WP3.1 `f56075a`): sostre 120→400 caràcters i apòstrofs permesos — a flowed les correccions llargues en català cauen silenciosament del registre derivat TS (el fallback Python, sense sostre, les troba: divergència silenciosa entre les dues vies). Nota: el fix del `÷` del `wordProblemTaskGuard` (`53af5a8`) NO és cherry-pick — aquell guard només existeix al fork. A avaluar també a flowed: `CORRECTION_RE` exigeix `^[-*]`, correccions sense bullet es perden (flagged pel bench WP3.4, no tocat al fork). Commits al fork: WP0.1 `917a81b` · WP0.2 renombrat `b1cf5cb` · WP0.1b `276f39f` · WP0.3 `392a78f` · WP1.2 mathgrade `1bf06db` · WP1.4 taxonomia `daec108` · WP1.5 generador+banc pilot `df329b5` · WP1.3 banc math `7cfe42d` · WP1.6 skills/comandes `2e44f79` · WP2.1 ítems de passos `2e55ae6` · WP1.7+1.8 perfil m1–m6/web `2ae6a8e` · WP2.2–2.4 servei+correcció per línia+traça `39a2bfc` · WP2.5 passos incrementals (v2) `e54ce63` · WP3.1+3.3 rúbrica oberta + raonament `f56075a` · WP3.2 problemes verbals (banc + obert) `0568b11` · WP3.4 bench obert `53af5a8` · WP3.5 alumne fix del bench `10c5f09`+`4dfc41c` · WP1.1 currículum m7 + avaluador algebraic + checkpoints `dd4c3b1`·`4b35f92`·`eb30834`·`ad4abbb`·`b88c3f2` · WP1.1-live e2e `algebra` + fix de l'avís d'encallament en torns de banc. Suite: 719 tests Python OK + 14 harnessos server OK. Pendent: **Fase 4** (visualització) i **Fase 5** (integració/cherry-picks). **No toca res de `flowed` en producció.**

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
| 1.1 | Currículum matemàtic `.md` — **fet** (`dd4c3b1`·`4b35f92`·`eb30834`·`ad4abbb`·`b88c3f2`): pilot m4 amb les competències declarades (`m4.add_carry`, `m4.div_2x1`, `m4.word_problems`, cadascuna amb la seva línia `Bank:`) + **m7 real (1r ESO)**: `curriculum/math-m7.md` (7 competències, checks `Compute:`/`Steps:`), escala D3 ampliada a m7 (m8/m9 reservats), avaluador algebraic `mathgrade.parse_poly/poly_form/grade_algebraic`, 7 famílies de banc (84 ítems) i checkpoints `Compute:`/`Steps:` a `curriculum.py`. Verificació en viu: perfil `test-m7:4201` + escenari e2e `algebra` (aquest commit) | 🟢 (contingut) | decisió D3 |
| 1.2 | `hooks/mathgrade.py`: avaluador `ast`+`Fraction`, normalització de notació, veredictes, «gairebé» per transposició | 🟡 | — |
| 1.3 | `bank.py`: nous tipus `compute/choose/compare`, endollar `mathgrade`, progress | 🟡 | 1.2 |
| 1.4 | Taxonomia d'errors matemàtica: `db_schema.py` + `tools.ts` + skills + test de sincronia | 🟢 | — |
| 1.5 | Generador de banc `scripts/mathbank.py` (plantilles paramètriques + validació + estat `reviewed`) | 🟡 | 1.2 |
| 1.6 | Skills i comandes matemàtiques: `math-learn`, `math-review`, `math-facts`, `math-problems` (obert), `math-end`, `math-setup`; reescriure `rules.md` i `AGENTS.md` (identitat tutor de mates, format de feedback amb traça) | 🟡 | 0.2 |
| 1.7 | Perfil i nivells: camps `grade/level` matemàtics a `math_setup_profile`, `new-user.sh`, `read-db.py`, `session-start.py`; escala D3 al web (`CEFR_ORDER` → escala matemàtica, gating de Reading→problemes) | 🟡 | D3 |
| 1.8 | Web: etiquetes/botons/placeholders, teclat numèric, Unicode matemàtic; panell amb etiquetes noves | 🟢 | 1.6 |
| 1.9 | Posar al dia la suite de tests (molts tenen literals d'idioma) + un e2e matemàtic bàsic | 🟡 | tot F1 |

Amb la Fase 1 ja hi ha un tutor de matemàtiques usable: Go/Review/Fets sobre banc (sense model, instantani), Lliçó del dia, SM-2, camí, checkpoints, ratxes.

**Tancament de Fase 1 — WP1.1-live (2026-10-06).** Els quatre punts de `docs/WP1.1-NOTES.md` («Què queda per tancar la Fase 1»):

1. `tools.ts` (enum `m7` a `math_setup_profile`) i `bank.ts` (categoria del veredicte algebraic al feedback) — **aplicats** a `b88c3f2`.
2. **e2e en viu d'm7 — fet.** Perfil `test-m7` (`~/.flowmath/test-m7`, port 4201, `FLOWED_WEBS="test-math:4200 test-m7:4201"`; provisió: `new-user.sh` + `flowed-profile.py --level m7 --goal m7` + certificat M4 sembrat, perquè l'escala col·loca l'alumne al nivell NO certificat més baix). Escenari nou `algebra` a `scripts/flowed-e2e.py` (RC=0, 29 comprovacions): currículum m7 resolt (barra del camí + targetes `m7.*`), forma equivalent «4x + 5x + 10» val 10/10 (equivalència polinòmica, no cadena), lliscament de signe «-2x + 12» → 3/10 amb categoria `sign` al feedback **i** a `.records`, còpia literal «3(x+4)» atrapada com a `procedure`, targeta de passos d'm7 pel camí v2 (un pas per missatge, traça al registre, cap pas propagat), SM-2 avança els encertats i torna els dos lliscaments demà, i la prova de nivell `Compute:`/`Steps:` (via CLI de `curriculum.py`, la que fan servir els tests WP1.1) fa 12 preguntes (6 compute + 6 steps) i acaba 12/12 «pass».
   *Bugs de producte destapats i arreglats:* (a) l'avís «the pacing note has not changed in 4 turns — the lesson is not advancing» saltava en lliçons servides **només pel banc** (el pla ja complet re-servia una targeta feble i la nota no canviava, però la lliçó avançava tot sol: el model ni es crida). El seguiment d'encallament passa a viure al camí del model, després dels `return` del banc (`agent.ts`); fixat a `server/test/lesson-note.test.ts`. No és candidat a cherry-pick: el guard és `math-review`-sol. (b) La correcció d'una còpia literal de l'enunciat mostrava la forma canònica a banda i banda de la fletxa («3x + 12» → «… → 3x + 12») — la forma canònica d'una còpia ÉS la de la resposta; el guard de `mathgrade.grade_algebraic` ara reporta el text cru de l'alumne, fixat a `tests/test_mathgrade.py`.
   *Ajust del rigor de l'e2e (no de producte):* les assercions de keying i «només steps» de lesson/review/steps comptaven també la targeta **feble** (reforç d'un patró fluix — `m4.word_problems.001` des que corre l'escenari problems), que no és ítem de cua i no porta `item_id` per disseny; restringides als ids sembrats.
3. El draft `docs/AlgebraNumericaBasica.md` creua cap a més competències m7? — **OBERT (decisió de producte de l'Albert; no s'hi ha actuat).**
4. Revisar els `why` dels ítems steps quan el pilot s'obri a alumnes de veritat — **OBERT (decisió de producte; no s'hi ha actuat).**

**Llista de deutes per a WP1.9** (recollida dels informes WP1.3–1.8, 2026-10-06):
- `scripts/flowed-e2e.py`: regex `LEVEL_Q` d'era-idioma i ruta de log `/tmp/math-web` en lloc de `$DATA_DIR`; cal reescriure'l per al camí math (etiquetes web exactes a `2ae6a8e`: 🎲 Go / 🔁 Review / 📚 Facts / 📝 Raonament / 📖 Problemes / 🗣️ Math talk / 📊 Stats / 🏁 End).
- Camp `new_vocabulary` al payload d'eines (nom d'era-idioma; renombrar amb llegir-el-vell).
- `pacing.ts` `writingLengthNote()`: indexat A1..C2 amb tasques email/postcard; retorna null per a m-nivells — math-ificar-lo o esborrar-lo.
- `pacing.ts` `NOT_AN_EXERCISE`: llista de paraules d'habilitat lingüística (deny-list, funciona, però les kind-words math depenen del filtre "(Easy)").
- `curriculum.py` `competency_of()`: especial per `skill=="vocabulary"` i prefix `vocabulary_` (mort per a math, inofensiu).
- `update-db.py:629` `item_type` per defecte `"vocabulary"`; `persist-session.py:248-252,340` i `accumulate-session.py:225,386` per defecte `"writing"/"speaking"/"vocabulary"` quan parsegen prosa de feedback.
- `read-db.py` (comentaris ~120–124) explica la rationale `{Native}/{Target}` de drills d'idioma; plantilla spaced-repetition amb placeholder `{error_pattern|vocabulary|grammar_rule}`.
- `~/.fluent` rutes legacy a `learner.md` (agents).
- Comptadors daily indexats per comanda (revisar coherència amb reasoning/problems/facts).
- `agent.ts` `learnerLevel()/lessonState()` posen el nivell en majúscules ("M4"): `curriculum._lvl` i `app.js` normalitzen, però **tot comparador nou ha de fer lowercase**.
- `test_tts.py`: assertions de l'era TTS (WP0.3 va netejar guards — verificar què queda).
- `math_deep_evaluate` task enum → es resol al WP3.1, no ara.

**Dades per a l'e2e math (WP1.9), de la mà de WP2.2–2.4 (`39a2bfc`):** targeta steps = `## Exercise N: Steps (…) <name> <comp-tag>` + `**Problem:** <problema>` + `**Una operació per línia:**` + `**Type your answer:**`; placeholder del composer `Escriu una operació per línia…`; resposta = traça completa, una operació per línia; feedback amb llista `**Passos:**` (`- ✅ 1 · \`…\`` / `- ❌ N · esperat … · has escrit … — why` / `arrossega l'error del pas N`) i el contracte estàndard (Corrections category = `error_class` del primer pas fallit, `**Correct version:**` = traça completa multilínia, `**Score: N/10**`). Registre: `skill:"steps"`, `steps:[{n,ok,got,propagated?}]`. Ids pilot steps: `m4.mult_2digit.031–.042`, `m4.frac_add_unlike.031–.042`, `m4.add_carry.001–.012`, `m4.div_2x1.001–.012` (renumerats per col·lisió amb compute — progress/cua/registre van per id).

### Fase 2 — Passos / operacions parcials (la peça demanada)

| WP | Què | Dificultat | Depèn de |
|---|---|---|---|
| 2.1 | Esquema `steps` + generador amb passos (plantilles amb traça) | 🟡 | 1.5 |
| 2.2 | Corrector per línia: partició, avaluació per pas, propagació d'errors, ponderació de nota | 🟡 | 1.2, 2.1 |
| 2.3 | **v1 «tot de cop»:** targeta amb la traça buida, feedback anotat pas a pas, registre amb `steps[]`, patró d'error per `error_class` | 🟡 | 2.2 |
| 2.4 | Web: render de traça ✅/❌ per pas, placeholder multi-línia | 🟢 | 2.3 |
| 2.5 | **v2 incremental:** estat «pas N pendent» per sessió a `agent.ts` (anàleg a `gradingItem`), reintent de pas, nota de progrés per pas | 🔴 | 2.3 |

Anotacions per a WP2.5/Fase 3 (de l'informe WP1.9, 2026-10-06): el bloc `math:review_results` del model al tancament pot avançar ítems de la cua **mai practicats** (vist: `dec_add.001` i `frac_add_unlike.031` amb reps=1 sense haver-se servit) — WP2.5 no ho empitjora (el camí v2 només registra quan la traça es completa; un intercanvi abandonat no escriu res), però **no ho arregla**: la guarda (id de la cua ↔ ítems realment servits) queda per a Fase 3; la interacció `pacingNote`↔`tryBankReviewTurn` (fix `usedItems` a `e0057b4`) és rellevant per a qualsevol feina del camí de lliçó — WP2.5 la va trencar en dos sentits amb l'intercanvi multi-torn i la va refer amb una llista pròpia del banc (`bankUsedItems` a `agent.ts`); el banc pilot no té ítems `choose` (forat WP1.1); `curriculum.py` checkpoint no té tipus de prova `Compute:`/`Steps:` (test de nivell math → Fase 3); els fets són model-driven (no hi ha ítems de fets al banc).

**Per a Fase 3 (pràctica oberta, rúbrica `math_deep_evaluate`, checks `Compute:`/`Steps:`):** el corrector per pas solt és `hooks/bank.py grade_step` (reutilitza `_grade_step_line`: forma I valor, `accept[]`, lliscada «near»); la política de reintent/revelació (2 intents per pas) i l'estat «pas N pendent» són a `server/src/steps.ts` + `agent.ts` (`assignedBankItem.stepsV2`); l'escala de nota v2 (10 tot primer-encert / 7 calgué reintent / 3 calgué revelar) és a `finalize_steps` i ha de coincidir amb la rúbrica oberta; les notes per pas NO porten marcador `**Score:**` ni fletxa de correcció — és el que evita que el parser de prosa de `persist-session.py` s'inventi exercicis; qualsevol pràctica oberta multi-torn amb estat del servidor ha de seguir la mateixa regla. Un ítem `steps` servit v2 que l'alumne contesta amb ≥2 línies cau a la correcció v1 tot-de-cop (via d'escapament «tota la traça de cop»).

### Fase 3 — Pràctica oberta matemàtica

| WP | Què | Dificultat |
|---|---|---|
| 3.1 | Rúbrica matemàtica del `math_deep_evaluate` (C3): jutja procediment i raonament, no gramàtica — fet `f56075a` (enum `explain/error-analysis/compare-strategies/word-problem`, bandes 10/7/3, skill keys C7 amb llegir-vell) | ✅ |
| 3.2 | Problemes verbals: banc (tancat) + variant oberta amb model (enviar `task='word-problem'`) — fet `0568b11` (família `word_problems` al generador; pilot `m4.word_problems` .001–.012, els primers 2 ítems `choose` del banc; obert: `math-reading` → `math_deep_evaluate` task='word-problem' + registre skill `problems`; guard `wordProblemTaskGuard`; escenari e2e `problems`) | ✅ |
| 3.3 | «Explica el teu raonament» (anàleg Writing) amb guards matemàtics (no demanar llistes, exigir justificació) — fet `f56075a` (`reasoningTaskGuard`, escenari e2e `reasoning`) | ✅ |
| 3.4 | Bench de models per a tasques obertes de mates — fet `53af5a8` (`scripts/flowed-mathbench.py` + `bench/learner-math.md`: alumne fix amb classes d'error sembrades `bare/calc-slip/wrong-op/thin/correct`; 13 portes de suficiència + bandes de la rúbrica per classe; cobertura de les 4 tasques via l'argument `task` del `math_deep_evaluate`; guards de tasca des de `.metrics/guards.jsonl`; `rescore` sense tornar a córrer el model) | ✅ |
| 3.5 | Arreglar l'alumne fix del bench (instrument de mesura, zero producte) i tornar a mesurar — fet `10c5f09` (respostes canned derivades de l'operació real de la tasca; pistes `infer_op` de resta «queden/falten», repartiment «entre N / quants vehicles calen», preu unitari; percentatges ×fracció; ordre gran-first per a −/÷; classe `generic` sense verdict de banda quan cap resposta canned quepa; +17 tests) | ✅ |

Anotacions per a WP3.4 (de l'informe WP3.2, 2026-10-06): el camí obert de problemes ja està connectat — `math-reading` (📖 Problemes) envia **sempre** `task='word-problem'` al `math_deep_evaluate` (rúbrica WP3.1: answer/procedure/justification/communication, bandes 10/7/3) i registra amb skill `problems`; el bench ha de cobrir les quatre tasques obertes (`explain`, `error-analysis`, `compare-strategies`, `word-problem`) i mirar-se el skill amb què queda el registre (`reasoning` per les tres primeres, `problems` per aquesta). El guard `wordProblemTaskGuard` (pacing.ts, aplicat a `agent.ts` en la cadena de guards) rebutja targetes amb `**Enunciat:**` de pura expressió aritmètica i tasques que només demanen el resultat — el bench hauria de puntuar també si el model *demana la feina* (operacions per línia), no només si corregeix bé. Un answer numèric pelat (sense operacions) ha de caure a la banda 0-4 de la rúbrica: comprovar-ho explícitament al bench. Nota de banc: els ítems de problema verbal porten la sintà a `expression` (el `problem` és prosa) — el corrector és el camí compute de sempre, res de nou per al bench.

Resultat del primer bench (2026-10-06, Qwen3-14B-Q4 remot, `test-math`, 2 passades — taula completa a `docs/MODELBENCH.md`): **NO SUFICIENT** per a l'obert, però no per on es temia. El model planteja bé les tasques (`task_ok` 4/4, **0 reescritures de guard** — demana la feina ell sol), corregeix amb la taxonomia de 12 (`taxonomy` 12/12), registra amb el skill correcte (`skill_ok` 12/12) i manté els torns intermedis nets (`grade_clean` 22/22). Falla on la rúbrica és exigent: **`band_ok` 6/12** — una resposta pelada sense operacions rep 7-10/10 quan la rúbrica la posa a 0-4 (mediana `bare` = 7), i **`continues` 9/12** — a 📝 sovint s'atura en «escriu rewrite o next» en lloc de la tasca següent. Dues derives més: 2/12 correccions sense el guió inicial → el `CORRECTION_RE` del servidor perd la correcció al registre derivat (`corrections: []`, no arriba al mistakes-db); i el 14B mai crida `math_record_answer` a les obertes ni delega a `math_deep_evaluate` des de 📝 (el skill no mana la crida — decideix Fase 3 si cal fer-la obligatòria). Per a alumnes reals: l'obert queda **apagat** fins que el model (o el prompt) respecti les bandes. *(Superat per WP3.5 — vegeu el paràgraf següent.)*

Resultat de WP3.5 (2026-10-06, mateix 14B remot `12321`, `test-math`, dues execucions × 2 passades — taula completa a `docs/MODELBENCH.md`): el residu del calibratge era de l'instrument, no del model. Amb l'alumne fix arreglat, **SUFICIENT**: `band_ok` **12/12** a les dues execucions (bare mediana 3-3.5, correct 8.5-9, wrong-op 3), `contract`/`taxonomy`/`continues`/`grade_clean`/`skill_ok` tots verd, 0 reescritures de guard. L'únic error real del model en 48 files: una etiqueta de categoria inventada («operation» → el servidor la normalitza en silenci a `calculation`). Permanent i invariable en 8 execucions: el 14B mai crida `math_record_answer` a les obertes i 📝 mai delega a `math_deep_evaluate` — **el registre derivat del servidor és la xarxa que sosté l'obert; no treure'l mai**. **Postura final de Fase 3: obrir la pràctica oberta per a alumnes reals** (ship open), amb els guards i el registre derivat com a xarxa; el banc (`run --repeat 2`, dues execucions verdes) és el termòmetre obligatori davant de qualsevol canvi de prompt o model.

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
| Qualitat del 14B en tasques obertes de mates — **mesurada (WP3.4, `53af5a8`): NO SUFICIENT** (`band_ok` 6/12: respostes pelades que reben 7-10 en lloc de 0-4; `continues` 9/12) | El camí tancat (banc) no depèn del model i segueix verd; l'obert queda apagat per a alumnes reals fins que el model o el prompt respectin les bandes de la rúbrica — el bench (`flowed-mathbench.py`) torna a mesurar-ho en un minut de reescritura de prompt |
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
