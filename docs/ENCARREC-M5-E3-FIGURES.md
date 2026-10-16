# Encàrrec E3 — Flash: figures SVG

Branca: `flash-vocab`. Disseny: `docs/DISSENY-M5.md` §2.4. Parteix d'E1 (`docs/ENCARREC-M5-E1-FLASH.md`, commit `d78d5ae`): tipus de resposta (`number`, `fraction`, `unit`, `choice`) i generadors. Decisions tancades.

## 1. Abast

Fitxers: `server/src/flash.ts`, `web/flash.js`, `web/style.css` (secció Flash), `hooks/curriculum.py` (només el mirall de `flash_lists` si cal per a ids), `server/test/flash.test.ts`, `tests/test_flash_math.py`. **No** toquis `curriculum/math-m5.md`, `scripts/mathbank.py`, `curriculum/bank/` (un altre agent hi treballa).

## 2. Camp `figure`

Una paraula de math pot portar `figure` (objecte). El client el dibuixa com a **SVG en línia** dins la targeta, sobre el `prompt`. Res d'imatges externes ni llibreries.

| `type` | Camps | Dibuix |
|---|---|---|
| `angle` | `deg` (1..360) | Dos segments des d'un vèrtex i un arc; **sense** número de graus (si no, l'exercici de classificar no té sentit) llevat que `label: true`. |
| `triangle` | `sides: [a,b,c]` (longituds), `labels: true/false`, `unit` | Triangle construït amb aquests costats (llei del cosinus); etiquetes de mida al mig de cada costat. Validar desigualtat triangular. |
| `polygon` | `sides: [..]` (3..8), `regular: bool`, `labels`, `unit` | Polígon regular (o regular amb les etiquetes donades si no ho és: només etiquetes, forma regular). |
| `rect` | `w`, `h`, `labels`, `unit` | Rectangle a escala. |
| `circle` | `mark`: `"radius" \| "diameter" \| "chord" \| "arc" \| "center"` | Circumferència amb l'element marcat en color d'accent. |
| `bars` | `labels: [..]`, `values: [..]` (enters ≥ 0, ≤ 8 barres), `title?` | Diagrama de barres amb eix vertical i graella. |
| `grid` | `points: [[x,y], ..]` (0..10), `size` (per defecte 10) | Primer quadrant amb graella i eixos numerats; punts marcats. |

- Colors amb els tokens `--flash-*` (llegibles sobre el fons de Flash). Mida màxima ~260 px d'alt, responsive (`viewBox`), `role="img"` i `aria-label` descriptiu en català.
- Validació al servidor: una paraula amb `figure` invàlida es descarta i es reporta (com els ítems invàlids d'E1).

## 3. Tipus de resposta nou: `pair`

Per a `grid`: "Quines coordenades té el punt?" → `(3, 4)`. Accepta `(3,4)`, `3,4`, `3 4`, `(3 ; 4)`. Parell ordenat: `(4,3)` és un error. Pista del 2n error: la primera coordenada (`(3, ?)`).

## 4. Generadors nous (mateixes regles que E1: deterministes, `count`, ids `g1…gN`)

| kind | Targeta | Resposta |
|---|---|---|
| `angle_type` | figura `angle` | choice `["agut", "recte", "obtús", "pla"]` (i `"complet"` si `params.full`) |
| `triangle_by_sides` | figura `triangle` amb etiquetes | choice `["equilàter", "isòsceles", "escalè"]` |
| `perimeter_figure` | `triangle` / `rect` / `polygon` amb etiquetes | unit (`cm`) |
| `area_figure` | `rect` (o triangle rectangle amb base i altura etiquetades) | unit (`cm²`) |
| `circle_element` | figura `circle` | choice `["radi", "diàmetre", "corda", "arc", "centre"]` |
| `bars_read` | figura `bars` | number ("Quants en té X?", "Quina és la moda?" → choice amb les etiquetes, "Mitjana?" amb mitjana entera) |
| `grid_point` | figura `grid` amb un punt | pair |

Llistes `items` explícites també poden portar `figure` (així l'Albert pot escriure'n de pròpies). Per a `choice` amb figura, la validació d'E1 continua (resposta dins de les opcions); per a figures, a més, el servidor comprova la coherència quan es pot (p. ex. `angle_type` escrit a mà: el `deg` ha de correspondre a l'opció).

## 5. Tests

- TS: validació de cada `figure` (bons i dolents), `pair` (formats acceptats, ordre), cada generador nou (determinisme, coherència figura ↔ resposta recalculada de manera independent).
- jsdom (scratchpad): l'SVG apareix amb `aria-label`, cap error de consola, targeta sense figura igual que abans.
- Tots: `server/test/*.test.ts`, `cd server && bun x tsc --noEmit`, `python3 -m unittest discover -s tests`. Única fallada esperada: les 4 llistes buides d'anglès.

## 6. Acceptació

- [ ] Les 7 figures es dibuixen, escalen i són llegibles al fons de Flash.
- [ ] `pair` funciona amb els formats indicats.
- [ ] 7 generadors nous deterministes i coherents.
- [ ] Res del que ja funciona canvia. Tests en verd (llevat de l'esperada).
