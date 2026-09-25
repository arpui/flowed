# Esquema d'aprenentatge: currículum com a base, estat mesurat pel servidor

Estat: **proposta aprovada en el marc** (2026-09-21, versió 3). Decidit: format `.md`, checks en anglès, checkpoint obligatori amb precondició, llindars 80/65. Res d'això està implementat.
Prerequisit de lectura: `docs/PLUGIN-VS-ACTUAL.md` (qui decidia què al plugin i ara).

## 1. El problema, amb el que s'ha comprovat

Al plugin (i avui a la nostra app) el «què s'aprèn» té només tres fonts:

1. **La cua SM-2 i els patrons d'error:** el que l'alumne ja ha fallat (regla explícita a `fluent-vocab` §2, `fluent-learn` §5).
2. **`focus_areas` del perfil:** una llista de paraules soltes escrita al setup («New high-frequency words matching `learner-profile.focus_areas`»).
3. **La lliure elecció del model:** la resta. Què és un «A2», quines estructures venen abans, quin vocabulari toca. No hi ha cap llista al plugin ni a l'app.

Conseqüències (deduïdes de les instruccions; el plugin no l'he executat):

- **No repetir:** al plugin només depenia de la memòria de la conversa i de si el tutor llegia `session-log.topics_covered` o els `.md` de `/results`. A la nostra app ho fa el servidor amb el que s'ha preguntat i contestat ben avui, però no entre setmanes.
- **Avançar:** no hi ha res que hagi de passar. Un alumne que només encerta pot fer setmanes de «warm-up» fàcil; un que falla, drills del mateix.
- **Convergir:** no hi ha punt d'arribada. El nivell objectiu és una etiqueta; no hi ha llista de coses per assolir, ni pas intermedi, ni estimació.

El diagnòstic de l'Albert és correcte: **sense un conjunt finit de continguts, els passos intermedis són arbitraris.**

## 2. Què aporta `fluent-session-analyzer` que no tenim

Llegeix els `.md` de `/results`, compta patrons per freqüència (1 = ignorar, 2-3 = emergent, 4+ = crític), extreu **punts forts** (✅ i notes ≥ 7), mira la **trajectòria** (precisió i errors per sessió) i fa un pla 50 % debilitats / 30 % patrons moderats / 20 % integració.

- **Ja ho tenim, millor:** freqüència i recència de patrons (`mistakes-db`, rànquing de `read-db.py`), i el servidor ja assigna el patró a treballar.
- **No ho tenim:** els **punts forts** com a senyal (què ja domina, per no repetir-ho ni gastar-hi temps) i la **trajectòria** entre sessions. Tots dos hi són a l'SM-2 (intervals llargs = domini), però ningú els resumeix. En el disseny nou surten de l'estat de cada competència (secció 4).
- **No cal recuperar-lo:** és un skill de lectura de fitxers que depèn del model; el que fa es pot fer amb codi sobre dades estructurades.

## 3. Proposta: un fitxer de currículum + un estat que compta el servidor

### 3.1 Currículum (`curriculum/<idioma>-<nivell>.md`)

Un fitxer `.md` per idioma i nivell, llegible per docents i pel servidor. Primer fitxer: `curriculum/en-A2.md` (v1, esborrany). El format està explicat a la capçalera del propi fitxer; en resum:

- Front matter: `language`, `level`, `version`, `status`, `pass_mark`, `carry_mark`, `checkpoint_items`, `ready_share` (% de les `core` consolidades perquè s'obri la prova; 0 = n'hi ha prou amb «en pràctica»; recomanat 50; és per nivell i es canvia al fitxer). **Sense `assumes`** (no hi ha A1 encara).
- Una competència per `###`: `id — Nom [core|extra]`, amb `Can do`, `Requires` (tou), `Forms`, `Words` (vocabulari), `Replaces` i 3 `Check`.
- `Check: Tipus: enunciat → resposta`: tipus = fins al primer `:`, resposta = després de l'última `→`; `/` = alternatives, `, ` = buits successius. Tot en anglès (independent de l'idioma natiu). Tipus tancats (`Complete`, `Correct`, `Meaning`) es comparen; oberts (`Ask`, `Say`) els valora el model.
- Els `Check` són **exemples**: el model genera ítems nous a partir de `Forms`/`Words`/`Can do`.
- **Ordre:** l'ordre del fitxer és l'ordre d'ensenyament dins de cada secció (Gramàtica, Funcions, Vocabulari); el servidor porta com a màxim 3 competències actives, una per secció.
- **Ids:** immutables; fusions amb `Replaces`; retirades a la secció «Retirades»; cada canvi puja `version`.

Mida actual: 19 competències (16 `core`, 3 `extra`).

**Origen:** esborrany de l'Albert + Claude, sense revisar contra el MCER ni l'English Grammar/Vocabulary Profile. Cal revisió docent abans de fiar-s'hi.

### 3.2 Estat per alumne (`learner-path.json`, escriu només el servidor)

Cada competència: `unseen → introduced → practicing → consolidated → mastered`, amb regles que compta el codi:

| Estat | Entra quan |
|---|---|
| `introduced` | Ha sortit un exercici de la competència |
| `practicing` | ≥ 3 respostes registrades amb el camp `competency` |
| `consolidated` | ≥ 80 % dels seus ítems (ítems amb aquest `competency`) superats en ≥ 2 dies diferents, l'últim amb interval SM-2 ≥ 6 dies |
| `mastered` | Ítems amb interval SM-2 ≥ 21 dies |
| reobertura | Un ítem consolidat falla dues vegades seguides → torna a `practicing` (màxim 2 cops; després `stalled`) |

Cada ítem SM-2 porta el camp `competency`; el servidor l'assigna en crear-lo, igual que assigna avui l'`item_id`. **Els temes de `topics.txt` esdevenen competències** (o s'hi mapegen) i ja tenen cicle de vida.

### 3.3 Qui decideix cada pas

| Pas | Qui | Regla |
|---|---|---|
| Què repassar avui | Servidor | La cua SM-2 (sense canvis; Lliçó = tota la cua) |
| **Què és nou** | **Servidor** | La següent competència del currículum en ordre de fitxer (avís si no es compleixen els `Requires`); màxim 3 actives, una per secció; `new_items_per_day` del perfil |
| Prioritat del docent | Servidor | Les del docent passen davant i respecten `requires` (avisa si no es compleix) |
| Punt de partida | Servidor + tutor | Diagnòstic: els `Check` de cada competència, de les més baixes a les més altes, fins que falla; s'omet el que ja domina |
| Exercici concret | Tutor | Dins de la competència assignada: forma, context, frase |
| Nota | Tutor | Sense canvis |
| **Pujar de nivell** | **Servidor** (el docent pot forçar-ho) | Checkpoint obligatori: es pot fer quan totes les `core` són com a mínim `practicing`, o quan el docent el llança; `checkpoint_items` de les `core`, almenys 1 per competència, no vistos els últims 7 dies. ≥ `pass_mark` % → puja. Entre `carry_mark` i `pass_mark` → puja, i les competències fluixes queden obertes al nivell nou. < `carry_mark` → reforç i repetició (màx. 2), després decideix el docent. Els llindars són al fitxer del nivell (decidit 2026-09-21: 80 / 65 per defecte, ajustables) |
| Progrés i estimació | Servidor | `% = core consolidades / core totals fins al nivell objectiu`; `ETA = pendents / ritme dels últims 14 dies` |

**Únic escriptor del nivell:** el servidor. El tutor no en parla ni el declara.

### 3.4 Per què convergeix

- Conjunt **finit** de competències amb un estat terminal → hi ha una definició de «arribat».
- **Monòton:** cada competència només va endavant, tret de reobertures limitades → no hi ha bucles infinits; una competència que no avança es marca `stalled` i es mostra al docent.
- El progrés és **mesurable** (no és un percentatge escrit pel tutor) i comparable entre alumnes.
- **No repeteix** el que és `consolidated`: el servidor no l'assigna com a nou; només torna per SM-2.
- **No s'avorreix:** els punts forts (competències `mastered`) surten dels exercicis i queden al manteniment.

### 3.5 Què no canvia

La Lliçó continua sent tota la cua SM-2. El currículum només mana on avui manen els temes: pràctica lliure, Mix, Writing, Speaking, Reading, Vocabulary i els exercicis de Lliçó sense ítem assignat. L'exercici el continua dissenyant el model; el que canvia és que **el què** ja no l'inventa.

## 4. Riscos i decisions

1. **Autoria del currículum:** és el treball més gran, i el que dona valor. Cal revisió humana; un currículum generat sense revisar fixa els errors del model.
2. **Llindars** (80 %, ≥ 2 dies, interval ≥ 6): són una primera proposta. Amb pocs exercicis per competència els percentatges són sorollosos; s'han de calibrar amb ús real, no amb el bench.
3. **Rigidesa:** un alumne amb un interès (viatge, examen) vol saltar. Solució: `requires` tou (avís, no bloqueig) i temes del docent amb prioritat.
4. **Checkpoint:** afegeix fricció. Es pot fer com una Lliçó especial i saltar-lo si les `core` porten prou dies consolidades.
5. **Idiomes:** un fitxer per idioma destí. El primer és l'anglès (l'alumne de proves).

**Decidit (2026-09-21):** (c) checkpoint obligatori, amb precondició `core ≥ practicing` o llançament del docent; llindars 80/65 al fitxer del nivell; format `.md`; checks en anglès; sense fitxer A1 de moment.
**Pendent:** (a) qui revisa el currículum d'anglès i amb quina font; (b) llindars de consolidació per competència (80 %, ≥ 2 dies, interval ≥ 6), a calibrar amb ús real; A1 i B1.

## 5. Ordre de treball, sense trencar res

| Fase | Què | Canvi visible |
|---|---|---|
| 0 | Fitxer de currículum + lector + `competency` als registres (només etiqueta) | Cap; el servidor comença a acumular evidència |
| 1 | Estat per competència calculat a `update-db.py`; pantalla de progrés amb dades reals; s'amaga el «% cap al següent nivell» inventat | El progrés deixa de ser text del tutor |
| 2 | El servidor assigna la competència nova a la pràctica lliure (nota, com `assigned` de la Lliçó) | El contingut nou surt del currículum |
| 3 | Diagnòstic inicial i checkpoint; pujada de nivell pel servidor | Es pot dir «has arribat a A2» |
| Bench | Escenari `curriculum` (com `days`): alumne simulat que segueix N competències durant dies; comprova que no en salta cap, que no repeteix les consolidades i que el nivell només puja amb el checkpoint | |

Estimació orientativa: fases 0-1 petites (dies), fase 2 mitjana (mateix patró que `assigned`), fase 3 mitjana; l'autoria del currículum és a part.

## 6. Com es guarda i com es veu (implementat en mode prova, 2026-09-21)

Estat: **lector, estat derivat, informes i alumne simulat implementats; res connectat encara a l'app.** Fitxers: `hooks/curriculum.py`, `scripts/flowed-sim-path.py`, `tests/test_curriculum.py` (25 tests).

### 6.1 Què es guarda: fets, no estats

`data/learner-path.json` (un per perfil; l'escriurà només el servidor). Només conté el que va passar:

- `competencies.<id>.answers`: cada resposta com `["2026-09-21", 1]` (dia, 1 = correcta). Màxim 200 per competència.
- `checkpoints`: data, ítems, correctes, %, resultat (`pass` / `carry` / `stay` / `teacher`), competències fallades.
- `promotions`: nivell assolit, data, tipus, competències arrossegades.
- `reinforce` / `carried`: competències que toquen reforçar o que arrossega el nivell nou.

L'**estat** de cada competència (`unseen → introduced → practicing → consolidated → mastered`), el %, l'ETA i l'evolució es **calculen** a partir dels fets. Avantatges: es poden canviar els llindars sense perdre historial, i es pot reproduir qualsevol dia passat (és com surt l'evolució setmanal).

Regles actuals (`CFG` a `curriculum.py`, competència sencera; quan els ítems SM-2 portin `competency`, `consolidated`/`mastered` llegiran els seus intervals):

| Estat | Entra quan |
|---|---|
| `introduced` | 1-2 respostes |
| `practicing` | ≥ 3 respostes |
| `consolidated` | ≥ 5 respostes; ≥ 80 % de les últimes 6; aquestes 6 repartides en ≥ 4 dies |
| `mastered` | consolidada + 21 dies entre la primera i l'última resposta + les últimes 4 correctes |
| reobertura | dues errades seguides ho treuen de consolidada (per la finestra de 6) |
| `estancada` (alerta) | ≥ 20 respostes i no consolidada |

**La barra:** `mitjana dels punts de les competències core` (sense veure 0, introduïda 0,15, en pràctica 0,5, consolidada o dominada 1). 100 % = totes les core consolidades = «llest per al checkpoint». Les `extra` no hi compten.

### 6.2 Com es veu

- **Alumne** (`python3 hooks/curriculum.py report --curriculum curriculum/en-A2.md --data data`): barra, quantes assolides, què treballa ara, si el checkpoint és a prop, i la llista per secció amb `■■■□`.
- **Admin** (`--admin`, afegeix): evolució setmanal (`▁▃▄▅`), ETA a totes les core consolidades al ritme dels últims 14 dies, alertes (estancades, oblidades), taula per competència (respostes, % total, % últimes, dies sense veure) i historial de checkpoints.
- **Web (fet, 2026-09-21)**: `GET /api/fluent/path` executa `python3 hooks/curriculum.py json --auto` (funció `path_view`; `{available:false}` si el nivell del perfil no té currículum, i llavors el web no mostra res). Dos llocs:
  - **Barra petita a la capçalera** (`#path-mini`, amb el %): s'actualitza en carregar i després de cada torn (màx. 1 cada 5 s); clicar-la obre el panell 📊.
  - **Secció «El teu camí cap al A2» a dalt del 📊 Progrés**: barra gran i %, «assolides x de 16 · en curs · per començar», «ara treballes», «per repassar», estat de la prova de nivell, i totes les competències per secció amb l'estat en paraules i una barra n/necessàries (mai 100% fins que és consolidada).
  - **`<details>` «Detall (docent)»** (plegat): estimació de dies, alertes (estancades / oblidades), evolució setmanal, taula per competència (respostes, encert total i recent, últim dia, profunditat·pes) i proves de nivell. Res d'això surt fora del bloc plegat. No hi ha rols nous: el mateix web, per a tothom.

Exemple (alumne simulat `steady`, llavor 1):

```
English A2 · dia 16 · 2026-10-06
A2  ████████████████░░░░   81%   assolides 10/16 · en curs 6 · per començar 0
Nivell A2 assolit el 2026-10-06
Ara: present_perfect_experience

GRAMÀTICA
  ■■■□ present_simple_vs_continuous               consolidada    8 resp 100%
  ■■□□ pronouns_possessives                       en pràctica    9 resp  50%
  ■■■□ prepositions_time_place                    consolidada    9 resp  83%
  ■■■□ infinitive_gerund                          consolidada    6 resp  83%
  ■■■□ countable_uncountable                      consolidada    8 resp  83%
  ■■■□ past_simple                                consolidada    6 resp  83%
  ■■□□ past_continuous                            en pràctica    6 resp  50%
  ■■□□ comparatives_superlatives                  en pràctica    5 resp  40%
  ■■□□ modals_ability_obligation                  en pràctica    4 resp  75%
  ■■□□ future_going_to_will                       en pràctica    4 resp  75%
  □□□□ present_perfect_experience         (extra) sense veure    0 resp   - 

FUNCIONS
  ■■□□ directions                                 en pràctica   10 resp  67%
  ■■■□ suggestions                                consolidada    8 resp  83%
  ■■■□ shopping_restaurant                        consolidada    8 resp 100%
```

### 6.3 Alumne simulat A1 → A2

`python3 scripts/flowed-sim-path.py --profile steady|fast|weak --seed N [--admin]`. 8 exercicis al dia: 2 per cada competència nova (una per secció), repàs de les començades (mai dos dies seguits), i 2 de manteniment de les consolidades. Cada competència té una probabilitat d'encert que creix amb la pràctica (i baixa si fa dies que no es veu). **Prova la mecànica del camí, no el tutor.**

`--calibrate N` fa que els mateixos alumnes, amb `N` llavors, s'enfrontin a diferents regles per obrir el checkpoint (`ready_share` = fracció de les core que han d'estar consolidades). `true p` = el que l'alumne sap de veritat quan el promocionen (probabilitat mitjana d'encert de les core):

```
30 seeds per profile. ready_share = share of core consolidated before the checkpoint opens.

profile  ready |  dia  pass carry  stay teach  none | true p core ok
fast      0.00 |   14    30     0     0     0     0 |   0.94  11.6/16
fast      0.50 |   14    30     0     0     0     0 |   0.94  11.6/16
fast      0.75 |   15    30     0     0     0     0 |   0.94  12.1/16
fast      1.00 |   19     7     0     0     0    23 |   0.96  16.0/16
steady    0.00 |   16    23     7     0     0     0 |   0.85   9.3/16
steady    0.50 |   16    25     5     0     0     0 |   0.85   9.5/16
steady    0.75 |   19    20     9     1     0     0 |   0.87  12.5/16
steady    1.00 |   23     4     0     0     0    26 |   0.89  16.0/16
weak      0.00 |   17     0    29     0     1     0 |   0.66   2.4/16
weak      0.50 |   25     3    21     6     0     0 |   0.71   8.2/16
weak      0.75 |   33     1    13     3     0    13 |   0.76  12.3/16
weak      1.00 |    0     0     0     0     0    30 |   0.00   0.0/16
```

Lectura: amb la regla actual (`ready_share 0`, «en pràctica» n'hi ha prou) el checkpoint s'obre el dia 14-17 amb 3-4 respostes per competència; l'alumne fluix hi arriba amb `true p` 0,66 i passa per `carry` amb 2-3 de 16 consolidades. Amb 0,5 espera uns 8 dies més i entra amb 0,71. Amb 1,0 el simulador gairebé no hi arriba (el seu manteniment és de 2 exercicis al dia; no és un resultat sobre l'app). **Recomanació:** començar amb `ready_share = 0,5`; és una decisió per a l'Albert (queda a `ready_share: 0` al front matter de `curriculum/en-A2.md` fins que la confirmi; es canvia allà, sense tocar codi).

### 6.4 Fase 0 (feta, 2026-09-21): etiquetar les respostes

- Les respostes ja es guarden a `<perfil>/.records/<sessió>.jsonl` (tutor o derivades). **No s'hi escriu res**: l'etiqueta de competència es **deriva** (`competency_of` a `hooks/curriculum.py`) i `rebuild_path` recalcula `learner-path.json` de zero, sempre igual (idempotent). Si millora el mapa, es reetiqueta tot l'historial. Un camp `competency` al registre, si existeix, mana (fase 2).
- **Regles:** vocabulari → per `Words`. Gramàtica i funcions → per `Tags:` de la competència: primer la `#categoria` de l'ítem o de la correcció, després les paraules que hi surten; si cap paraula surt, només s'assigna quan hi ha una sola candidata. El que el nivell no ensenya (p. ex. articles a l'A2) queda **sense etiqueta**, i la paraula fora de les llistes també.
- **Quan corre:** el servidor executa `curriculum.py rebuild --auto` després de cada `accumulate-session`. `--auto` tria el fitxer de `curriculum/` amb `language` i `level` iguals a `target_language` / `target_level` del perfil (o `$FLOWED_CURRICULUM`); si no n'hi ha, no fa res. No canvia cap comportament de l'app.
- **Cobertura:** `python3 hooks/curriculum.py coverage --curriculum curriculum/en-A2.md --data ~/.fluent/<perfil>` diu quantes respostes s'han pogut assignar i per què no la resta. Amb els 20 ítems del perfil de proves: 10 assignats (50 %); els no assignats són d'A1 (articles, majúscules, ortografia), una paraula fora de la llista i `grammar_two_children`, que és ambigu.
- Perfil i informes: `report --rebuild` refà el camí abans de mostrar-lo.

### 6.5 Repàs de les competències assolides (cicle d'oblit), proposta

Avui una competència consolidada només torna si els seus ítems SM-2 venen per la Lliçó. Cal que hi torni per si mateixa, a intervals que s'allarguin, i que un error la faci baixar:

- Després de consolidar-se, el següent repàs toca als **3 dies**; cada repàs correcte l'allarga (**7 → 14 → 30 dies**); un error el torna al principi i la competència a «en pràctica» si són dos de seguits.
- La data del proper repàs també es **deriva** de l'historial de respostes; no cal guardar res més.
- El servidor inclou les competències «per repassar» dins la quota de manteniment del dia (com ara fa el simulador, però amb aquests intervals en lloc d'un mínim fix de 3 dies).
- «Consolidada» ja exigeix respostes repartides en ≥ 4 dies, de manera que no s'assoleix en una sola sessió.

**Implementat** (`review_due`, `due_maintenance` a `curriculum.py`, i el simulador el fa servir). Intervals `review_days = [3, 7, 14, 30]` per confirmar.

### 6.6 Fase 2 (implementada, 2026-09-21): el servidor assigna la competència a la pràctica lliure

Mateix patró que l'ítem de la Lliçó: el que el tutor no pot saber, ho diu el servidor.

- **On:** només 🎲 Mix (`fluent-learn`) i 📚 Vocabulary (`fluent-vocab`). No a la Lliçó (té la seva cua SM-2) ni a Writing/Speaking/Reading. Vocabulary només rep competències amb paraules (`--vocab`). Si hi ha una paraula pendent de repàs (`vocabularyDueNote`), aquesta mana i la competència espera. La nota de competència **substitueix** la de `topics.txt`; sense currículum res canvia.
- **Qui tria:** `hooks/curriculum.py next --auto --data <perfil> [--last <id>] [--vocab]` → JSON `{id, name, kind (new|review|maintenance), can_do, signals, words, vocab, note}`. Ordre: noves d'avui (2 exercicis cadascuna, com a màxim 3 actives), començades sense consolidar (1), consolidades que toquen pel cicle d'oblit (1); mai la que s'acaba de preguntar.
- **Nota al tutor:** «the next exercise practises "<nom>": <can do>. Structures: … Use one of these words as the ANSWER…». El tutor construeix l'exercici; el servidor no el dicta.
- **Guard:** l'exercici en què acaba la resposta ha de contenir algun `signal` de la competència (paraules del `Tags:` que no són `#categoria`: «now», «at the moment», «goes»…; paraula sencera, sense accents ni majúscules). Si no, es reescriu **només l'exercici** (`The next exercise must practice "<nom>"…`, una vegada, el feedback es manté). Vocabulari no es jutja (es pregunta en la llengua de l'alumne).
- **Registre:** el registre de la resposta porta `competency: <id>` només si l'exercici es va veure que seguia la competència i no és de vocabulari (aquest l'assigna Python per `Words`). Sense això, l'etiquetatge segueix derivat (6.4). `notes.jsonl` guarda `competence: {id, name, kind}` per torn.
- **Límit conegut:** els ítems SM-2 nous des de la pràctica lliure (segona meitat de la idea original) no estan fets: una resposta de gramàtica només alimenta el camí, no la cua SM-2.

**Evidència per competència (2026-09-21).** Cada competència declara `Depth: light|normal|deep` i `Weight: 1-3` al `.md`. `Depth` fixa quantes respostes calen per consolidar (8 / 12 / 20), l'espai en dies de la finestra (3 / 5 / 7) i els exercicis diaris (nova 3/3/4, repàs 2/2/3); `Weight` pesa a la barra. Detall i valors inicials a `docs/PROVES.md` § 30.41; les taules de `curriculum.py` (`DEPTH`) són l'únic lloc on es canvien.

### 6.7 Test amb el tutor real: `--scenario curriculum`

`scripts/flowed-bench.sh --curriculum --quick --repeat 1` (o `python3 scripts/flowed-e2e.py test-en --port 4103 --scenario curriculum --days 5 --answers 6 --vocab 3 --transcript /tmp/cur.md`).

Què fa: buida el perfil de proves (cua SM-2 i registres, perquè cap repàs pendent tapi la competència), el posa a `target_language=English`, `target_level=A2`, `current_level=A1` i simula N dies d'un alumne (`--student fast|steady|weak`, `--seed`, les mateixes corbes que `flowed-sim-path.py`). Cada dia: una sessió Mix (`fluent-learn`, «6») amb `--answers` respostes i una de Vocabulary amb `--vocab`. El rellotge avança amb `flowed-advance-day.py --keep-records` (no arxiva els registres: en desplaça el `ts`, perquè el camí es deriva de tots).

Respostes: vocabulari amb el banc de paraules del bench (bé o malament, ben conegut); gramàtica i funcions les escriu un model (`--student-url`, per defecte el llama del 12322; pot ser el mateix que el tutor) al qual es demana «respon bé» o «fes un error típic d'A1». Sense model, la gramàtica és «no ho sé» i només valen les comprovacions de l'exercici.

Comprovacions: el servidor assigna competència a ≥ 90 % dels exercicis · l'exercici segueix la competència (≥ 70 %, per signals) · el tutor no diu res de la nota · qualifica cada resposta · ≥ 70 % de respostes assignades a una competència (i, si no, per què) · puntua el vocabulari com toca · el camí passa per més d'una competència · la barra es mou · cada dia les respostes queden com a registres. Al final imprimeix l'ordre de competències, la taula per dies, l'informe de l'alumne (dies 1, 3 i final) i l'informe d'admin. Informatiu: coincidència tutor/intenció en gramàtica.

Sense servidor: `tests/test_curriculum_fake_server.py` corre l'escenari sencer contra un tutor fals que fa servir el mateix `next_target` (2 tests: un tutor correcte passa tot; un que ignora la competència és enxampat).

No mira: el checkpoint (ho fa el simulador) ni la qualitat del que ensenya el tutor.

### 6.8 Cursos, tall i certificats (2026-09-21)

Cada nivell és un **curs** amb un **tall dur**: quan s'assoleix, es certifica, s'avisa i comença un curs nou (A1 → A2). No es torna enrere i el nivell certificat no es perd mai; només es repassen errades (SM-2).

- **Nivell de partida.** «A0» no existeix com a fitxer: vol dir sense coneixement previ. El nivell declarat a l'inici (A0/A1) és **indeterminat**: no garanteix res i cal certificar-lo. `find_curriculum` tria el **nivell més baix sense certificar** de l'escala fins al `target_level` del perfil; el `current_level` declarat no es fia. Quan tot està certificat, l'últim.
- **Què es guarda al perfil** (`hooks/curriculum.py`): `learner-path.json` = només el curs actiu (`curriculum`, `start_ts` en ms); `certificates.json` (permanent: nivell, data, tipus `checkpoint`/`manual`/`placement`, resultat, pct, competències febles, arxiu); `courses/<llengua>-<nivell>-<dia>.json` (arxiu del curs: camí, resultat, estats finals); `course-notices.json` (avís de «curs acabat», amb `seen`); `checkpoint-run.json` (prova en curs).
- **`close_course`** és l'únic que escriu el certificat i el `current_level` del perfil; és idempotent (tancar dos cops no duplica). Arxiva el camí, posa un camí nou buit amb `start_ts` = ara i crea l'avís.
- **Què es manté:** registres, sessions, ratxa, perfil, cua SM-2 i errades. **Què reinicia:** camí, barra, estats, checkpoints i reforç; els registres anteriors a `start_ts` **no compten** al curs nou (`rebuild_path`).
- **No s'arrosseguen competències febles** al curs nou: queden al certificat (`weak`) i el repàs d'errades SM-2 continua. Unes «competències personalitzades» són una opció futura, no feta.
- **Certificació manual:** `curriculum.py close --auto --data <dir> --day <YYYY-MM-DD>` (el docent). Avís: `curriculum.py notice [--seen]`.
- **Si un camí és d'un altre curs** (perfil canviat a mà), `rebuild_path` l'arxiva abans de sobreescriure'l.

### 6.9 Prova de nivell a l'app

La fa el **servidor sense el LLM** (`checkpoint start|answer|status` a `curriculum.py`; `checkpointTurn` a `server/src/agent.ts` escriu els missatges del tutor). Així la nota no depèn del model.

- **Quan s'ofereix:** `checkpoint_ready` (totes les core treballades i `ready_share` % consolidades; el `ready_share` és una constant del front matter de cada nivell). El web mostra el botó 🧪 només quan s'ofereix (`checkpoint: "ready"` a `/api/fluent/path`). Si no toca, la prova respon per què (cal esperar `checkpoint_gap_days` = 3 dies o falta treballar).
- **Preguntes:** els `Check` tancats (Complete / Correct / Meaning): ≥ 1 per competència core i extres a les més febles, sense repetir; en un reintent, prefereix les no vistes; ordre barrejat determinista. Les respostes de la prova **no són registres** (no toquen el camí, només el resultat).
- **Correcció** per comparació normalitzada (majúscules, puntuació, apòstrofs; la frase sencera o només les paraules que falten; blancs múltiples en ordre; Meaning ≤ 5 paraules que continguin la resposta). `A / B` = respostes alternatives.
- **Resultat** (`apply_checkpoint`): `pass`/`carry` → `close_course` (certificat + curs següent); `stay` → competències febles a `reinforce` + espera de 3 dies; `teacher` després de massa intents.
- **Interrompre:** la prova es reprèn el mateix dia; una d'un altre dia es descarta.
- **Limitació:** només 3 `Check` per competència → banc petit; els missatges de la prova són en anglès.

### 6.10 Escenari `ladder` (A0 → A1 → prova → tall → A2)

`scripts/flowed-bench.sh --ladder --quick --repeat 1 --span 3` (o `python3 scripts/flowed-e2e.py test-en --port 4103 --scenario ladder --days 3 [--test-mode pass|fail]`). Només perfils de proves.

1. **A**: curs A1 des de zero amb el tutor real (les comprovacions de `--scenario curriculum`, `--days` dies).
2. **B**: la resta de l'historial d'A1 es **fabrica** (alumne simulat `--student`, `--seed`) i s'escriu com a registres al passat (`.records/ladder-synthetic.jsonl`, camp `competency` explícit) fins que la prova s'obre. No es pot viure en una tarda. Comprova que el servidor ofereix la prova.
3. **C**: prova de nivell **feta pel servidor**; les respostes surten dels `Check` del propi currículum (`pass`) o són totes errònies (`fail`).
4. **D** (`pass`): certificat d'A1 (`checkpoint`), `current_level` = A1, curs arxivat a `courses/`, avís de curs acabat (un sol cop), camí actiu A2 a 0 %, A2 no ofereix la prova. **Sense tall** (`fail`): missatge «Not yet», cap certificat, nivell del perfil igual, intent `stay`, cap avís, el curs continua sent A1.
5. **E** (`pass`): 2 dies d'A2 amb el tutor real; només compten els registres nous.

`flowed-sim-path.py --ladder` fa el mateix sense app (només la mecànica; `fast`/`steady`/`weak` passen A1 → tall → A2). `sim.run(..., stop_when_ready=True, on_answer=…)` s'usa a la fase B.

### 6.11 Què falta

1. ~~Fase 1: barra al web~~ (feta, §6.2). ~~Curs, tall i certificats~~ (§6.8). ~~Prova de nivell a l'app~~ (§6.9, només provada amb tests i fonts; falta veure-la a la pantalla real).
2. Executar `--ladder` i `--curriculum` amb el model i decidir amb dades: intervals del cicle d'oblit (3/7/14/30, sense confirmar), si els `signals` són prou bons (el guard només enxampa derives grosses; opció: només evidència positiva).
3. Ítems SM-2 nous des de la pràctica lliure.
4. Bancs de `Check` més grans (3 per competència és poc per a la prova); missatges de la prova en la llengua nativa.
5. Currículum B1; «competències personalitzades» a partir de les febles del certificat.
