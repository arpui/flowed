# Pla — exercicis tancats: banc fora de línia

*2026-09-24 · **Estat: fases 1–5 fetes; vegeu «Estat».** Substitueix la
generació en directe (versió del 2026-09-23, aparcada) i integra
`PLA-BANC-EXERCICIS.md` del projecte.*

## Decisió (Albert, 2026-09-24)

Els exercicis tancats de **🎲 Go** i **🎓 Review** (un buit, una resposta) deixen
de generar-se en directe. Es generen i es validen **un cop, fora de línia**, en
un banc JSON. El servidor tria, pinta i corregeix **sense model**.

El model queda per al que és obert: **Writing, Speaking i Reading**, i,
opcionalment, un comentari curt quan una resposta tancada és incorrecta, ja
sabent quina és la bona.

## Per què: les dades

**1. El prompt en directe és massa gran per a un 14B.** `turns.jsonl` de `test-en`
(83 torns):

```
tokens de prompt per torn: mínim 12.933 · mediana 18.503 · p90 22.510 · màxim 23.810   (context 32.768)
```

Abans de la primera resposta de l'alumna, el model ja té 13.000 tokens
d'instruccions. Cada guard n'ha afegit més: més instruccions, pitjor compliment.
És el «desvaria sense motiu» que no trobàvem.

**2. Amb un prompt petit, el mateix model va bé i és ràpid.** Banc de models,
Qwen3-14B-Q4, 2026-09-23:

| Rol | Resultat | Mediana |
|---|---|---|
| alumne (respon els `Check:` del currículum) | **98 %** (41/42) | 0,1 s |
| tutor (escriu exercicis, jutge fix) | **53 %** justos (19/36), varietat 79 % | 0,3 s |

Com a alumne gairebé no falla. Com a generador, la meitat dels exercicis no
serveixen, i els motius són exactament els bugs d'aquests dies:

- **Ambigus:** «There are ___ children» (three / some), «This is ___ mother»
  (our / my), «Hello, my name is ___».
- **Verb entre parèntesis a `can_ability`:** «I ___ (ride) a bike» → «can ride»
  en lloc de «can». És el defecte heretat del `Check:` del currículum.
- **Pista catalana inventada:** «My ___ (german)».
- **Un buit que no és únic, o la resposta que ja surt a la frase:** 7 casos.

Un filtre fora de línia llença aquesta meitat sense que l'alumna la vegi mai.
En directe no hi ha segona oportunitat: per això calien guards.

## Un torn de Go amb el banc

```
curriculum.py next            quina competència toca (ja existeix, no canvia)
      ↓
banc                          quin ítem: no vist fa 7 dies; primer els fallats, després els nous
      ↓
servidor pinta la targeta     el mateix format visual d'ara: el web no canvia
      ↓
l'alumna respon
      ↓
correcció determinista        canon + alternatives + pista d'error ortogràfic
      ↓
retorn prefabricat            marcador · nota · versió correcta · «why» de l'ítem
      ↓
registre exacte               competència, id de l'ítem, resposta; si falla, entra a la cua SM-2
```

Cap model en aquest camí. Si més endavant es vol un comentari personalitzat
quan falla, és una crida de menys de 1.000 tokens amb la resposta bona donada.
És una tasca fàcil, no de judici.

**Review surt gairebé sol:** els ítems fallats entren a `spaced-repetition.json`
amb l'id del banc, i Review els torna a preguntar tal qual.

## L'ítem

```json
{
  "id":          "a1.present_simple.014",
  "competence":  "a1.present_simple",
  "type":        "complete | choose | meaning | translate | correct",
  "instruction": "Complete with the verb in brackets.",
  "sentence":    "My brother ___ (play) football every Saturday.",
  "context":     "",
  "answer":      "plays",
  "also_accept": [],
  "options":     [],
  "why":         "With he / she / it the verb takes -s: he plays.",
  "status":      "generated | validated | reviewed",
  "source":      "qwen3-14b-q4 · 2026-09-24"
}
```

- **Un sol buit per ítem a l'A1.** Els buits múltiples compliquen la correcció
  i no aporten res a aquest nivell.
- **`choose`**, amb 2–4 opcions, per a les competències on el buit admet per
  naturalesa diverses respostes del mateix tipus: this/that, these/those,
  a/an/the, what/where/how, morning/evening. Una pista a la frase en deixa bona
  només una.
- **`why`** és la regla en una frase, escrita i revisada fora de línia. És el que
  l'alumna llegeix quan falla, i per això en directe no cal model.
- **Vocabulari:** el buit porta la paraula en català entre parèntesis («The car
  is ___ (vermell).»), o bé és `meaning` / `translate`, sense buit.

Fitxers: `curriculum/bank/en-A1/<competence_id>.json`, un per competència,
versionats amb git. Els ids no es reutilitzen mai: el progrés hi va lligat.

## Validació (fora de línia, un cop)

**Regles fixes.** V1–V8 del pla anterior, més tres que surten de la línia base:

| | Regla |
|---|---|
| V1 | `type` permès per la competència (vocabulari: meaning/complete/translate; gramàtica: complete/choose/correct) |
| V2 | exactament un `___` (complete/choose) |
| V3 | `answer` no surt a `sentence` ni a `context` |
| V4 | vocabulari: `answer` és de `Words:` |
| V5 | vocabulari amb buit: hi ha una pista entre parèntesis, i no és una categoria ni la paraula anglesa |
| V6 | frase no repetida dins la competència (després de `canon`) |
| V7 | sense referències a imatges; la direcció de llengua és correcta |
| V8 | `correct`: la frase inicial i la resposta difereixen en poques paraules |
| V9 | `choose`: `answer` ∈ `options`, amb 2–4 opcions |
| **V10** | gramàtica amb paraules a `Tags:`: la resposta en conté una. El buit ha de ser l'estructura de la lliçó, no el verb que l'acompanya. Mata el cas «can ride», i ha de valer també per als `Check:` del currículum. |
| **V11** | `why` present, i no conté la resposta d'una altra opció |

**Jutge.** `bench/learner-a1.md` sobre el model de referència respon l'ítem
sense saber la resposta. **Just** = arriba a `answer` o a una de les
`also_accept`. És el rol `generate` del banc de models, sense canvis de criteri.

**Revisió.** Claude revisa cada fitxer de competència sencer (és feina fora de
línia i barata). L'Albert en mira una mostra del 10 %, amb èmfasi en les pistes
en català. Només els ítems en estat `reviewed` arriben a l'alumna.

**Rendiment esperat:** amb el 14B, ~50 % d'ítems justos, i hi ha duplicats. Per
tenir 40 ítems bons per competència cal generar-ne uns 100. Amb un model més
fort, menys. El generador és qualsevol model per `--url`.

## Correcció determinista

1. **Extreure el que va al buit:** si escriu la frase sencera, se'n treu la part
   del buit (la lògica de `only_the_gap`).
2. **`canon`**, el de `flowed-modelbench.py`: minúscules, contraccions
   (aren't = are not), xifres (20 = twenty), apòstrofs, «o'clock».
3. **Veredicte:**
   - igual a `answer` o a una `also_accept` → ✅ 10/10;
   - a una lletra de distància (definició a sota) → 🟡 7/10: «gairebé: s'escriu
     *because*»;
   - la resposta d'una altra opció (`choose`) o una forma incorrecta → 🔴
     3/10, amb `why`;
   - buida o «no ho sé» → 🔴 0/10, amb `why`.
4. **«Una lletra de distància», exactament:**
   - **Distància Damerau restringida (OSA) ≤ 1:** Levenshtein (substituir,
     afegir o treure una lletra) més l'intercanvi de dues lletres seguides,
     l'error més típic d'una nena («becuase», «freind»). Levenshtein pur els
     compta com a 2.
   - **Sobre quines cadenes:** minúscules i sense espais als extrems, calculada
     dos cops: amb les formes tal com són i amb les passades per `canon`. Val la
     menor. Així «dont» contra «don't» dona 1 → 🟡.
   - **Longitud:** la resposta esperada, sencera, ha de tenir **5 caràcters o
     més**. Per sota, qualsevol diferència és 🔴.
   - **Excepció:** si el que ha escrit és una altra paraula de la lliçó
     (`Words:`, `Tags:` de la competència o `options` de l'ítem), no és una
     errada de lletra sinó un error: «there» per «three», «those» per «these» →
     🔴, encara que la distància sigui 1.
5. **`correct`**: es compara la frase sencera, amb `canon`.
6. **Sense penalitzar** accents ni lletres pròpies del català, com ara.

El retorn té el format de sempre (marcador, correccions, versió correcta,
«Score: N/10»): el web, els registres i el comptador no canvien.

## Estat (2026-09-24, revisió)

- **Fets:** fases 1–2. Banc A1 a `curriculum/bank/en-A1/`: 18 competències,
  570 ítems, **tots `reviewed`** (acceptats per l'Albert el 2026-09-24). Go i
  Vocabulary el fan servir (`exercises.bank: true`).
- **Mida del banc: el doble de l'evidència que demana `Depth:`**
  (`min_answers` a `hooks/curriculum.py`):

  | Depth | Respostes per consolidar | Ítems al banc |
  |---|---|---|
  | light | 10 | 20 |
  | normal | 20 | 40 |
  | deep | 30 | 60 |

  Amb el filtre «no vist fa 7 dies» i les quotes diàries (3 noves / 2 de repàs),
  l'alumna consolida una competència sense repetir cap ítem. Els repetits
  arriben al manteniment (3, 7, 14, 30 dies després) i als ítems fallats,
  que es repeteixen a posta. El doble també cobreix el cas d'una competència
  encallada (`stalled_answers`: 16 / 24 / 40). L'A1 ja compleix la regla: el
  mínim són 20 ítems per a `light`, i `vocab_colors_adjectives` en té 30.
  Si `min_answers` puja, el banc ha de pujar també.
- **Fase 3** (mesura amb l'e2e, banc encès i apagat): pendent, si no s'ha fet.
- **Fase 4: feta (2026-09-24), falta mesurar-la.** Review ja no crida el model.
  Cada exercici surt de `curriculum.py bank review-pick`, en aquest ordre:
  1. **Un ítem de la cua que és del banc** (fallat abans) → aquell ítem.
  2. **Un patró d'error antic**, només si es pot col·locar **amb seguretat**
     (opció C) → un ítem del banc de la seva competència. El registre porta
     l'`item_id` del patró, i l'SM-2 l'avança fins que surt de la cua. És segur
     quan:
     - la paraula és a la llista `Words:` d'una competència, o
     - la categoria correspon a una sola competència, o
     - dins la categoria hi ha una sola competència guanyadora **i** alguna de
       les paraules que hi coincideixen és exclusiva d'ella en tot el
       currículum. «don't» no ho és (és d'`imperatives` i de `present_simple`).
  3. **Si no hi ha res vençut** → la competència que tria `next_target`.

  Els patrons que no es poden col·locar **es retiren**: conserven la història,
  guarden `retired` {data, motiu, suposició, venciment d'abans} i reben un
  venciment que no arriba mai (`9999-12-31`). A `nes-en`, 11 es col·loquen i 15
  es retiren. Per veure-ho abans que passi:
  `python3 hooks/curriculum.py bank review-pick --auto --data ~/.fluent/<perfil> --dry-run`.

  La lliçó acabada també és una plantilla fixa, sense model.
- **Errors trobats de passada (arreglats):**
  - Les respostes del banc no sumaven al comptador del dia (✏️): el camí del
    banc sortia abans de `creditTurn`.
  - El corrector del banc treia l'última lletra de la resposta quan el buit
    acabava la frase: «Ten plus ten is ___.» + «twenty» → «twent» → 7/10. També
    es menjava la pista entre parèntesis: «It ___ (rain).» + «is going to rain»
    → 3/10.
  - La «Correct version» mostrava la pista: «There are five children (child)
    in the park.».
  - Les targetes del banc deien «Exercise N: **Writing**».

  Prova nova sobre **tot** el banc (A1 i A2): tota resposta vàlida treu 10,
  tant exacta com escrita en frase sencera o en majúscules.
- **Fase 3:** mesurada per l'Albert (2026-09-24).
- **Fase 5: feta (2026-09-24).** S'ha tret:
  - `openBlankGuard`, `patchOpenBlank`, `vocabBlankGuard` i els seus ajudants;
  - `nextDrill` i la nota de «drill»;
  - la porta de repàs sencera (`resolveReviewGate`, `reviewGateNote`,
    `GATE_COMMANDS`, `sessionOpenedWith`);
  - els paràgrafs de la nota de `curriculum.py`, que ara només arriba al model
    en el cas de reserva.

  `pacing.ts` passa de 2.306 a 2.024 línies, i `agent.ts` de 2.544 a 2.442. Es
  **mantenen**, perquè també serveixen Writing, Speaking i Reading:
  `deriveRecord`, `turnGuard` (repeticions, «graded with no answer») i els
  guards d'imatges i de direcció de llengua. La prova `vocab-gap.test.ts` és a
  `_to_delete/fase5-20260924/`.
- **Després del pla (2026-09-24):**
  - **La prova de nivell surt del banc revisat**, no dels 3 `Check:` per
    competència. Mai repeteix un ítem d'una prova anterior, prefereix el que no
    ha practicat els últims 7 dies i fa servir el corrector del banc: una
    errada de lletra (7/10) no aprova. Sense banc, continua amb els `Check:`.
  - **«Gairebé» també a «Correct»**, paraula per paraula (una sola paraula
    diferent, OSA ≤ 1, 5 lletres o més). En tots dos casos, **una forma
    flexionada no és una errada de lletra** (play/plays, speak/speaks,
    have/has…): és l'error de gramàtica que l'exercici ensenya, i surt 🔴. Abans
    «He play» per «He plays» treia 7/10.
  - **Banc que s'esgota:** a la vista del camí, un punt tènue (·) al costat del
    tema, amb el títol «Queden pocs exercicis nous d'aquest tema», quan en
    queden 3 o menys de nous (`BANK_LOW`). A la vista del docent, la columna
    «Banc nous» (no vistos / total). L'alumna no veu mai el número.
  - **`turns.jsonl` guarda `command`**, per poder mesurar el prompt de cada
    pràctica.
  - Arreglat el `Check:` de `a1.can_ability`: «I ___ swim, but I can't fly.»,
    sense la pista entre parèntesis que convidava a conjugar.
- **Proves:** 463/463 en verd. S'han posat al dia per als llindars 10/20/30,
  que ara les proves llegeixen de `DEPTH` i no porten escrits. També s'ha
  arreglat el tutor simulat, que triava paraules fora de la llista, i quatre
  comprovacions de codi que buscaven textos antics.

## Fases

| Fase | Què | Surt |
|---|---|---|
| **1 · Pilot** | `bench → bank`: generar, validar (V1–V11, jutge), revisar. Banc per a **dues competències**: `a1.present_simple` (gramàtica, la que ha donat més bugs) i `a1.vocab_colors_adjectives` (vocabulari, el cas «The car is ___»). Repartiment, targeta, correcció determinista. Rere l'interruptor `exercises.bank` a `config/fluent.json`. Una competència sense banc continua pel camí actual. | Prova de concepte en l'app real |
| **2 · A1 sencer** | Les 18 competències × ~40 ítems revisats. Arreglar de passada els `Check:` del currículum que no passen V10. | Banc A1 |
| **3 · Mesura** | `flowed-bench.sh --repeat 6` amb l'interruptor apagat i encès. | Decisió d'encendre'l per defecte |
| **4 · Review** | Els ítems fallats entren a la cua amb l'id del banc; Review els repeteix tal qual. S'elimina la generació en directe de Review. | Review sobre el banc |
| **5 · Neteja** | Fora els guards i les notes que ja no tenen res a vigilar (llista a sota). Els prompts de Go i Review es redueixen. | Menys codi, prompt petit |

Cada fase es mesura sola, com fins ara.

## Criteris d'acceptació (fase 3)

- Correcció **tota en verd** (marcador, versió correcta, nota, registres, `item_id`).
- Repetició **0 de 6**. Ambigüitat **0**, perquè no hi ha cap ítem sense revisar.
- Tokens de prompt en un torn de Go: **< 2.000** (ara: mediana 18.503).
- Latència mediana d'un torn de Go **≤ la d'ara**. Se n'espera molt menys: sense model, és gairebé instantani.
- Cap de les 23 comprovacions de l'e2e empitjora.

## Què desapareix a la fase 5

> **Fet el 2026-09-24**, amb una correcció respecte a aquesta llista: `deriveRecord`, les empremtes de repetició (`turnGuard`) i «graded with no answer» **es mantenen**, perquè també les fan servir Writing, Speaking i Reading. Vegeu «Estat».

`openBlankGuard` · `patchOpenBlank` · `vocabBlankGuard` · les empremtes per
regex de repeticions dels tancats · `nextDrill` i la nota de «drill» · la deriva
de competència (`signals`) · el «graded with no answer» dels tancats ·
`deriveRecord` per a Go/Review · els paràgrafs de la nota de `curriculum.py`
(números, «vary the type», «pin the blank», «Shape of one») · la contradicció
«just the missing word» (Bug 3). Es mantenen els guards de Writing, Speaking i
Reading.

## Relació amb els bugs del 2026-09-24

Hi ha tres bugs oberts, tots de generació i correcció en directe:

1. `there_is_are` / `present_simple`.
2. `can_ability`: el buit és al lloc equivocat (el verb entre parèntesis).
3. «Does» / «Do» / «Are there»: el marcador contradiu la instrucció «just the
   missing word».

Les mitigacions de prompt fetes aquell dia (`foldedContent` i la nota del buit)
**es mantenen** fins que la competència afectada tingui banc (fases 1–2). No es
fan guards nous per al bug 3: la fase 5 el resol de soca-rel.

## Riscos

| Risc | Mitigació |
|---|---|
| Qualitat del banc: una pista catalana dolenta («german») arriba a les nenes | Estat `reviewed` obligatori; mostra de l'Albert centrada en les pistes |
| Monotonia | 40 per competència més repàs espaiat no s'esgoten en mesos; el banc s'amplia fora de línia; un comptador d'ítems no vistos per competència avisa quan en queden pocs |
| Respon la frase sencera, o amb una lletra canviada | Extracció del buit i política de «gairebé» (a dalt) |
| Es perd l'adaptació als interessos (`topics.txt`) a Go | Es manté a Writing; més endavant, bancs amb temes |
| El currículum canvia | Ids estables; `Replaces:` migra el progrés com ja fa |
| Transició a mitges | L'interruptor per competència: amb banc → banc; sense banc → camí actual |

## Què es manté del pla anterior i què s'abandona

- **Es manté:** l'esquema JSON (ara és el format del banc), les regles V1–V8,
  el tipus `choose`, l'alumne simulat com a jutge.
- **S'abandona:**
  - la generació i la validació en directe a cada torn (la crida `json_schema`,
    la comprovació a cegues en línia, els reintents);
  - la comprovació d'«ambigüitat» amb un model que llista respostes (F0/F1): els
    seus veredictes no deien res útil. L'script és a `_to_delete/`.

## Fitxers

**Nous:** `curriculum/bank/en-A1/*.json` · l'ordre `bank` a
`scripts/flowed-modelbench.py` (generar → validar → escriure) ·
`server/src/bank.ts` (triar, pintar, corregir).
**Canvien:** `server/src/agent.ts` (Go/Review: banc si n'hi ha) ·
`hooks/curriculum.py` (només arreglar `Check:`, la tria de competència no
canvia) · `config/fluent.json` (`exercises.bank`) · `scripts/flowed-e2e.py`
(comparació banc / directe).
