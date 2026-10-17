# Encàrrec L2 — Go d'anglès A1/A2: ordenar paraules i transformar frases

Decisions tancades (Albert, 2026-10-17). Context: el banc d'anglès (`curriculum/bank/en-A1/`, `en-A2/`, un fitxer per competència) és sobretot `complete` (omplir un buit: 644 de 773 a A2). Tipus existents: `complete`, `choose`, `meaning`, `translate`, `correct`. La correcció és a `hooks/bank.py` (`grade`, comparació canònica + distància OSA; `correct`/`translate` comparen la frase sencera), i el text de la targeta i del feedback es genera a `server/src/bank.ts`.

## 1. Abast

Fitxers: `hooks/bank.py`, `server/src/bank.ts`, `curriculum/bank/en-A1/*.json` i `en-A2/*.json` (afegir ítems, no tocar els existents), tests del banc (`tests/test_bank_*.py`, `server/test/bank.test.ts`). **No** toquis `server/src/flash.ts`, `web/flash.js`, `curriculum/flash/`, ni `hooks/curriculum.py` llevat que sigui imprescindible per servir els tipus nous (un altre agent hi treballa en paral·lel).

## 2. Tipus nous

### `order` — ordenar paraules
- Ítem: `{type: "order", instruction: "Put the words in order.", words: ["you", "where", "live", "do"], answer: "Where do you live?", also_accept: [..], why}`. `sentence` es pot deixar buit si el codi ho permet; si cal, posa-hi les paraules separades per ` / `.
- Targeta: `**Words:** you / where / live / do ?` i "Write the sentence:".
- Correcció: frase sencera, com `correct` (majúscula inicial i puntuació final **no** compten; l'ordre sí). Validació: les paraules de `answer` (sense puntuació, en minúscules) són exactament el multiconjunt de `words`.

### `transform` — transformar una frase
- Ítem: `{type: "transform", instruction: "Make it negative." | "Make it a question." | "Put it in the past." | …, sentence: "She plays tennis.", answer: "She doesn't play tennis.", also_accept: ["She does not play tennis."], why}`.
- Targeta: la instrucció + `**Sentence:** …` + "Write the new sentence:".
- Correcció: com `correct` (frase sencera; contraccions i formes llargues via `also_accept`, i a més `don't`=`do not`, `doesn't`=`does not`, `isn't`=`is not`, `aren't`=`are not`, `didn't`=`did not`, `can't`=`cannot`/`can not`, `won't`=`will not` acceptades sempre per a aquests dos tipus).

Els dos tipus han de funcionar a tot arreu on es fa servir el banc (Go, repàs, i que el test de nivell els serveixi o els salti de manera coherent amb com tracta avui `correct`/`translate` — revisa `_bank_checkpoint_items`).

## 3. Contingut

Ítems nous (`status: "validated"`, `source: "claude · 2026-10-17"`), ids continuant la numeració de cada fitxer de competència:

- **A1** (gramàtica): `a1.verb_to_be`, `a1.present_simple`, `a1.question_words`, `a1.have_got`, `a1.can_ability`, `a1.there_is_are` (comprova els ids reals a `curriculum/en-A1.md`): 6 `order` + 6 `transform` per competència (negativa, pregunta).
- **A2** (gramàtica): `a2.present_simple_vs_continuous`, `a2.past_simple`, `a2.past_continuous`, `a2.comparatives_superlatives`, `a2.modals_ability_obligation`, `a2.future_going_to_will`, `a2.present_perfect_experience`: 6 `order` + 6 `transform` (negativa, pregunta, passat, futur, segons la competència).
- Vocabulari i frases naturals, adequats a A1/A2; cap ítem duplicat (mateixa resposta) dins d'una competència.

## 4. Tests

- Correcció de `order` (ordre equivocat = error; majúscula/punt final indiferents) i `transform` (contraccions), validació de tots els ítems nous (multiconjunt de paraules, resposta no buida, `why` present), render de la targeta i del feedback a `bank.ts`.
- Tots: `server/test/*.test.ts` (`node --experimental-strip-types`), `cd server && bun x tsc --noEmit`, `python3 -m unittest discover -s tests` — **tots han de passar** (ja no hi ha fallades esperades).

## 5. Acceptació

- [ ] Tipus `order` i `transform` servits i corregits a Go.
- [ ] ~72 ítems nous a A1 i ~84 a A2.
- [ ] Res existent canviat. Tests en verd.
