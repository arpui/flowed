# Encàrrec E4 — Contingut Flash de m5 i poliment

Branca: `flash-vocab`. Parteix d'E1 (generadors i tipus de resposta), E3 (figures i `pair`) i E2 (`curriculum/math-m5.md`). Decisions tancades.

## 1. Llistes de Flash de m5

A `curriculum/flash/math-m5/` ja hi ha `01`…`08` (taules) i `09-2x1-xifres.json`. **No els canviïs** (ids i progrés dels alumnes de prova).

Afegeix **una llista per generador** d'E1/E3, numerades a partir de `10-`, amb aquest format (12 targetes, valors per defecte):

```json
{ "id": "math-m5.flash.arrodonir", "level": "m5", "competence": "m5.…",
  "title": { "ca": "Arrodonir", "es": "Redondear", "en": "Rounding" },
  "generate": { "kind": "round", "count": 12 } }
```

| kind | títol (ca) | competence |
|---|---|---|
| `round` | Arrodonir | — |
| `digit_value` | Valor d'una xifra | — |
| `compare_numbers` | Comparar nombres grans | — |
| `combined` | Operacions combinades | `m5.combined_ops` |
| `divisible` | Divisibilitat | — |
| `frac_of` | Fracció d'una quantitat | `m5.frac_of_quantity` |
| `frac_equiv` | Fraccions equivalents | — |
| `frac_same_den` | Fraccions amb el mateix denominador | `m5.frac_same_den` |
| `frac_dec` | Fraccions i decimals | — |
| `dec_times_int` | Decimal per enter | `m5.dec_ops` |
| `percent_of` | Percentatges | `m5.percent_basic` |
| `unit_convert` | Unitats de mesura | `m5.smd_convert` |
| `complex_to_simple` | Complex i incomplex | `m5.smd_convert` |
| `time_convert` | Hores, minuts i segons | `m5.time_intervals` |
| `area_simple` | Àrees (enunciat) | `m5.area_perimeter` |
| `perimeter_figure` | Perímetres (figura) | `m5.area_perimeter` |
| `area_figure` | Àrees (figura) | `m5.area_perimeter` |
| `angle_type` | Tipus d'angles | — |
| `triangle_by_sides` | Triangles segons els costats | — |
| `circle_element` | Elements de la circumferència | — |
| `grid_point` | Coordenades | — |
| `bars_read` | Diagrames de barres | `m5.mean_mode_range` |
| `mean` | Mitjana | `m5.mean_mode_range` |
| `probability` | Probabilitat | `m5.probability` |
| `equation` | Equacions | `m5.equations_simple` |
| `sequence` | Sèries | — |

("—" = sense camp `competence`.) Títols `es`/`en` traduïts. Ordre dels fitxers: el de la taula.

## 2. Requisit de nivell

A la capçalera de `curriculum/math-m5.md`, afegeix `flash_share: 60`. Comprova amb `flash_progress` que el total de llistes de m5 és el nombre de fitxers vàlids i que `needed = ceil(total × 0,6)`.

## 3. Poliment visual (`web/flash.js`, `web/style.css`)

- **Etiquetes de mida** de `triangle` i `polygon`: col·locar-les **fora** de la figura, desplaçades sobre la normal exterior de cada costat (no al mig del segment), perquè no trepitgin la línia. `rect`: igual (a dalt i a la dreta, fora).
- **Etiqueta sobre la targeta**: "Calcula" per a `number`/`unit`/`fraction`, **"Tria"** per a `choice`, **"Escriu les coordenades"** per a `pair`.
- **Mida de l'enunciat**: si el `prompt` passa de ~40 caràcters, una mida de lletra més petita (classe CSS), perquè no ocupi mitja pantalla al mòbil.

## 4. Tests

- Totes les llistes de `curriculum/flash/math-m5/` vàlides (el test de llistes existent), ids únics, `competence` (quan hi és) existeix a `math-m5.md`.
- Python: `flash_progress` amb `math-m5.md` real ⇒ `share == 60`, `total` = llistes vàlides.
- Captures amb Chromium (Playwright, `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`) d'una targeta de triangle, polígon, rectangle, una de `choice` i una amb enunciat llarg, a 390 px d'ample (mòbil), al scratchpad.
- Tots: `server/test/*.test.ts`, `cd server && bun x tsc --noEmit`, `python3 -m unittest discover -s tests`. Única fallada esperada: les 4 llistes buides d'anglès.

## 5. Acceptació

- [ ] 26 llistes noves a `math-m5/`, ordenades, amb `competence` on toca.
- [ ] `flash_share: 60` a `math-m5.md` i el camí de m5 ho mostra.
- [ ] Etiquetes fora de les figures; "Tria" / "Escriu les coordenades"; enunciats llargs més petits.
- [ ] Res més canvia. Tests en verd (llevat de l'esperada).

## 6. Afegit (2026-10-16, Albert): multiplicacions aleatòries en lloc de taules seguides

A m5 les taules en ordre ja se les saben; és feina de repàs. Per tant:

- **Treu** `curriculum/flash/math-m5/01-taula-2.json` … `08-taula-9.json` i `09-2x1-xifres.json` (només hi ha perfils de prova; el seu progrés es perd, és acceptat).
- **Nou generador** `kind: "mult"` (E1, mateixes regles: determinista, `count`, ids `g1…gN`, mirall Python per `count`): `params.digits: [da, db]` = nombre de xifres de cada factor. Una xifra = 2..9 (sense 0 ni 1); 2 xifres = 10..99; 3 xifres = 100..999. Ordre aleatori (llavor = id de la llista), sense repetir la mateixa multiplicació (ni la commutada `a×b`/`b×a`) dins la llista. Resposta `number`.
- **Tres llistes noves**, que van **primer** a la carpeta:
  - `01-taules-repas.json`: "Taules (repàs)", `digits: [1, 1]`, `count: 24`.
  - `02-mult-2x1.json`: "2 xifres × 1 xifra", `digits: [2, 1]`, `count: 12`.
  - `03-mult-3x1.json`: "3 xifres × 1 xifra", `digits: [3, 1]`, `count: 12`.
  - Totes amb `"competence": "m5.mult_3digit"` només la de 3×1; les altres sense.
- Les 26 llistes de §1 continuen numerant-se a partir de `10-`.
- Tests: el generador `mult` (xifres correctes, sense repetits ni commutats, determinista, resultat recalculat), ids Python == servidor, i el total de `flash_progress` de m5 reflecteix 3 + 26 llistes.
