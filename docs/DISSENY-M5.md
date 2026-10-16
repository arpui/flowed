# Disseny — exercicis de m5

Data: 2026-10-16. Font: currículum m5 (5 blocs) que ha passat l'Albert. Objectiu: decidir **quin tipus d'exercici** cobreix cada punt, **per quin canal** (Flash o Go) i **què cal construir**.

## 1. Els dos canals

| Canal | Per a què | Com es corregeix | Ja existeix |
|---|---|---|---|
| **⚡ Flash** | Fets i càlculs curts que s'han d'automatitzar (resposta en < 20 s). | Al navegador, al moment, sense model. | Sí: números, operacions generades (`+ − × :`). |
| **🎲 Go (banc)** | Exercicis amb procediment: càlcul llarg pas a pas, problemes de 2-3 passos, operacions combinades. | `hooks/mathgrade.py` (fraccions, decimals, unitats, algebra) i el corrector de passos. El tutor només presenta i explica. | Sí: `compute`, `choose`, `compare`, `steps`; generador `scripts/mathbank.py`. |

Regla: **si es pot respondre de cap en pocs segons → Flash. Si cal escriure passos o llegir un enunciat llarg → Go.** Moltes competències tenen les dues coses (p. ex. fracció d'una quantitat: Flash per al càlcul directe, Go per al problema amb enunciat).

## 2. Què falta construir

### 2.1 Flash: tipus de resposta (encàrrec E1)

Avui Flash només compara números. m5 necessita:

| Tipus | Exemple | Regla |
|---|---|---|
| `number` (ja hi és) | `7 × 8` → `56` | Valor numèric; coma o punt. |
| `fraction` | `3/8 + 2/8` → `5/8` | Accepta equivalents (`10/16`) **llevat** que la llista digui `"form": "simplest"` (llavors cal la irreductible). Accepta nombres mixtos `1 1/2`. |
| `unit` | `3,5 km = ? m` → `3500` | L'alumne escriu només el número; la unitat surt al costat de la caixa. |
| `choice` | Angle de 135° → agut / recte / **obtús** / pla | Botons (i tecles 1-4). Un error desactiva l'opció triada; es revela quan en queda una o al 3r error. Serveix per a `<, >, =`, Sí/No, classificar triangles, segur/possible/impossible… |

### 2.2 Flash: generadors nous (encàrrec E1)

Tots generen `count` ítems **deterministes** (llavor = id de la llista), amb resultat calculat pel codi. Ids `g1…gN`, de manera que el Python només necessita `count` per comptar paraules.

| Generador | Exemple de targeta | Bloc |
|---|---|---|
| `round` | Arrodoneix 4.735.218 a la centena → 4.735.200 | Nombres |
| `digit_value` | Quin valor té el 7 a 4.735.218? → 700.000 | Nombres |
| `compare_numbers` | 1.204.500 ? 1.240.050 → `<` (choice) | Nombres |
| `frac_of` | 3/4 de 120 → 90 | Fraccions |
| `frac_equiv` | 2/3 = ?/12 → 8 | Fraccions |
| `frac_same_den` | 3/8 + 2/8 → 5/8 (fraction) | Fraccions |
| `frac_dec` | 25/100 = ? → 0,25 · i al revés 0,7 → 7/10 | Decimals |
| `dec_times_int` | 2,35 × 4 → 9,4 | Decimals |
| `percent_of` | 25 % de 80 → 20 | Percentatges |
| `divisible` | És 135 divisible per 3? → Sí (choice) | Divisibilitat |
| `combined` | 4 + 3 × 5 → 19 · (4 + 3) × 5 → 35 | Operacions |
| `unit_convert` | 3,5 km = ? m → 3500 (unit) | Mesura |
| `complex_to_simple` | 2 m 45 cm = ? cm → 245 | Mesura |
| `time_convert` | 3 h 15 min = ? min → 195 | Mesura |
| `area_simple` | Rectangle 8 cm × 5 cm, àrea? → 40 (unit cm²) · triangle b=10, h=6 → 30 | Geometria |
| `mean` | Mitjana de 4, 8, 6, 2 → 5 (sempre entera) | Estadística |
| `probability` | Dau: probabilitat de treure parell? → 3/6 (fraction, equivalents valen) | Probabilitat |
| `equation` | 3·x + 5 = 20 → x = 5 | Àlgebra |
| `sequence` | 3, 7, 11, 15, ? → 19 | Patrons |

Llistes escrites a mà (`items`) també poden fer servir `choice`/`fraction`/`unit`: p. ex. "Un prisma pentagonal, quantes arestes?" → 15; "Segment que passa pel centre i toca dos punts de la circumferència" → diàmetre (choice).

### 2.3 Go: banc de m5 (encàrrec E2)

Fitxer de nivell nou `curriculum/math-m5.md` (mateix format que `math-m4.md`) amb una competència per punt del currículum i la seva línia `Bank:`. Famílies noves a `scripts/mathbank.py` (resultat calculat amb `mathgrade`, com les actuals):

| Competència | Tipus Go | Família |
|---|---|---|
| `m5.mult_3digit` [core] | compute + steps | `mult_3digit` (+ `partial_products` per a 3 xifres) |
| `m5.div_2digit` [core] | compute + steps | `div_2digit` (+ `long_division` amb divisor de 2 xifres) |
| `m5.combined_ops` [core] | compute | `combined_ops` (jerarquia i parèntesis) |
| `m5.distributive` | steps | `props_distributive_numeric` (ja existeix) |
| `m5.frac_same_den` [core] | compute | `frac_same_den` |
| `m5.frac_of_quantity` [core] | compute (amb enunciat curt) | `frac_of_quantity` |
| `m5.dec_ops` [core] | compute | `dec_ops` (suma/resta 3 decimals, decimal × enter) |
| `m5.percent_basic` | compute | `percent_basic` |
| `m5.smd_convert` [core] | compute (amb unitat) | `smd_convert` |
| `m5.time_intervals` | compute (enunciat: "surt a les 9:45 i arriba a les 11:20") | `time_intervals` |
| `m5.area_perimeter` [core] | compute (amb unitat) | `area_perimeter` |
| `m5.mean_mode_range` | compute | `mean_mode_range` |
| `m5.probability` | compute (fracció) | `probability_simple` |
| `m5.equations_simple` | compute | `equations_simple` |
| `m5.word_problems` [core] | compute + choose (2-3 passos) | `word_problems_multistep` |

### 2.4 Figures (encàrrec E3, després d'E1)

Bona part de geometria i estadística demana **veure** alguna cosa. Flash pot dibuixar una figura SVG a partir d'una especificació a la targeta, sense imatges:

| `figure.type` | Exemple | Per a |
|---|---|---|
| `angle` | arc de 135° → classificar o estimar | Angles |
| `triangle` / `polygon` | costats amb mides → perímetre, classificar | Polígons, perímetre |
| `circle` | marca radi/diàmetre/corda/arc → triar el nom | Circumferència |
| `bars` | diagrama de barres → llegir un valor, moda, mitjana | Gràfics |
| `grid` | punt al primer quadrant → escriure `(3, 4)` (tipus `pair`) | Coordenades |

### 2.5 Fora d'abast (ara)

- **Traçar** angles amb transportador, **crear** gràfics, simetries i translacions dibuixant: necessiten interacció de dibuix. Es poden aproximar amb `choice` sobre figures (E3), però no com a construcció.
- Lectura/escriptura de nombres en lletres: possible amb `items` escrits a mà, sense generador.

## 3. Ordre de feina

1. **E1** Flash: tipus de resposta + generadors. **E2** (en paral·lel) Go: `math-m5.md` + famílies del banc.
2. **E3** Flash: figures SVG.
3. **E4** Contingut Flash de m5 (llistes per a cada competència) + `flash_share` a `math-m5.md`.
