# Encàrrec L1 — Flash d'anglès A1/A2: formes, decisions ràpides i dictat

Branca: `flash-vocab`. Decisions tancades (Albert, 2026-10-17). Context: avui Flash d'anglès només té llistes de traducció (`curriculum/flash/en-A1/*.json`, format `words: [{id, target, native:{ca,es}}]`). El motor de Flash ja té, per a math, generadors, `items` explícits i el tipus de resposta `choice` amb botons (`server/src/flash.ts`, `web/flash.js`). La veu existeix: `GET /api/math/say?text=…&lang=…` torna un WAV (piper), i `GET /api/math/tts-state` diu si està activa.

## 1. Abast

Fitxers: `server/src/flash.ts`, `web/flash.js`, `web/style.css` (secció Flash), `hooks/curriculum.py` (només el mirall de Flash: ids i recompte de paraules), `server/test/flash.test.ts`, `tests/test_flash_math.py` (o un `tests/test_flash_lang.py` nou), i llistes noves a `curriculum/flash/en-A1/` i `curriculum/flash/en-A2/`. **No** toquis `hooks/bank.py`, `server/src/bank.ts`, `curriculum/bank/`, `curriculum/en-*.md` (un altre agent hi treballa en paral·lel), ni les 12 llistes de traducció existents d'A1.

## 2. Tipus de llista nous per a language

Una llista de language pot portar `"kind"`:

- absent ⇒ traducció, **com ara** (res no canvia).
- `"drill"`: `items: [{id, prompt, answer: [..], options?: [..]}]`. Sense direcció (com math). El `prompt` és en anglès (p. ex. `go → past`). Si porta `options`, és `choice` (botons, mateix flux que math); si no, resposta escrita.
  - Correcció de text: minúscules, espais col·lapsats, sense puntuació final, apòstrofs tipogràfics = rectes (`don’t` = `don't`). **Sense** treure articles ni accents (aquí la forma exacta és el que es practica).
  - Pista del 2n error: primera lletra + guions, com ara.
- `"dictation"`: `items: [{id, say, answer: [..]}]`. La targeta mostra un botó gran 🔊 i reprodueix `say` amb la veu en obrir-se (i en prémer el botó; com a màxim 3 reproduccions per targeta). L'alumne escriu el que sent; correcció com `drill` però **ignorant la puntuació** i les majúscules. Si la veu no està activa (`tts-state`), la llista surt al menú desactivada amb la nota "Cal la veu activada".
- El selector de direcció del menú no surt si totes les llistes del nivell són `drill`/`dictation`; si n'hi ha de traducció, surt i només afecta les de traducció.
- Servidor: valida els ítems (ids únics, `answer` no buit, `options` contenen `answer[0]`), els descartats es reporten com a math. Python: el mirall compta els ítems per id.

## 3. Contingut (llistes noves)

Ids `en-A1.flash.<slug>` / `en-A2.flash.<slug>`, títols `ca`/`es`/`en`, `competence` = id de `curriculum/en-A1.md` / `en-A2.md` quan n'hi hagi un d'equivalent (llegeix-los). 12–20 ítems per llista, vocabulari d'A1/A2.

**A1** (numera a partir de `20-` perquè quedin després de les de traducció):
- `20-third-person.json` (drill): `play → he …` → `he plays`; `watch → she …` → `she watches`; `study → it …` → `it studies`; `have → he …` → `he has`.
- `21-plurals.json` (drill): `child → plural` → `children`; `box`, `baby`, `man`, `tooth`, `bus`…
- `22-a-an.json` (drill, choice `["a", "an"]`): `… apple`, `… umbrella`, `… hour`, `… university`, `… book`.
- `23-dictation-a1.json` (dictation): paraules i frases molt curtes d'A1 (`Thursday`, `my sister`, `I am twelve`).

**A2** (carpeta nova `en-A2/`, numera a partir de `01-`):
- `01-past-irregular.json` (drill): `go → past` → `went`, `buy` → `bought`, `see`, `eat`, `take`, `write`… (20).
- `02-ing.json` (drill): `run → -ing` → `running`, `make` → `making`, `swim`, `lie` → `lying`…
- `03-comparatives.json` (drill): `big → comparative` → `bigger`, `good` → `better`, `beautiful` → `more beautiful`, `happy` → `happier`…
- `04-in-on-at.json` (drill, choice `["in", "on", "at"]`): `… Monday`, `… July`, `… 7 o'clock`, `… the weekend`, `… 2010`, `… night`.
- `05-much-many.json` (drill, choice `["much", "many"]`) i `06-some-any.json` (drill, choice `["some", "any"]`) amb frases curtes (`There isn't … milk`).
- `07-dictation-a2.json` (dictation): frases curtes d'A2 (`She went to the market`, `I'm going to travel`).

## 4. Requisit de nivell

`curriculum/en-A1.md` té `flash_share: 80`. **No el canviïs**; afegir 4 llistes a A1 puja el nombre de llistes que cal tancar (de 10 a 13 de 16). Reporta-ho. A A2 no hi ha `flash_share`.

## 5. Tests

- TS: correcció de `drill` (apòstrofs, majúscules, puntuació), `choice` de language, `dictation` (puntuació ignorada), validació d'ítems, totes les llistes de `curriculum/flash/en-*` vàlides, el filtre per nivell (un alumne d'A2 veu només `en-A2`).
- Python: mirall d'ids per a les llistes noves; `flash_progress` d'A1 amb el total nou.
- Captures amb Chromium (390 px) al scratchpad: una targeta `drill` escrita, una de `choice` (a/an), una de `dictation` (botó 🔊).
- Tots: `server/test/*.test.ts`, `cd server && bun x tsc --noEmit`, `python3 -m unittest discover -s tests` — **tots han de passar** (ja no hi ha fallades esperades).

## 6. Acceptació

- [ ] `drill` (escrit i choice) i `dictation` funcionen; la traducció no canvia.
- [ ] 4 llistes noves a A1 i 7 a A2.
- [ ] Tests en verd.
