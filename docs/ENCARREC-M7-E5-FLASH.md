# Encàrrec E5 — Flash: motor per a m7 (tipus, figures, generadors)

Branca: `flash-vocab`. Disseny: `docs/DISSENY-M7-M6.md` §1 (llegir-lo) i, per al motor existent, `docs/ENCARREC-M5-E1-FLASH.md` i `docs/ENCARREC-M5-E3-FIGURES.md`. Mateixes regles que E1/E3: generadors deterministes (llavor = id de la llista), `count` (per defecte 12, màx. 50), ids `g1…gN`, mirall Python per `count`, resultats en aritmètica exacta, textos en català, decimals amb coma. Decisions tancades.

## 1. Abast

Fitxers: `server/src/flash.ts`, `web/flash.js`, `web/style.css` (secció Flash), `hooks/curriculum.py` (només el mirall de Flash: `MATH_GEN_KINDS` i el que calgui per a ids), `server/test/flash.test.ts`, `tests/test_flash_math.py`. **No** toquis `curriculum/math-m7.md`, `curriculum/math-m6.md`, `scripts/mathbank.py`, `curriculum/bank/` (un altre agent hi treballa en paral·lel), ni les llistes existents de `curriculum/flash/`.

## 2. Tipus de resposta nous

- `factorization`: accepta `2^3·3^2·5`, `2³·3²·5`, `2·2·2·3·3·5`, separadors `·`, `*`, `x`, `×`, espais. Compara el multiconjunt de primers. Un factor no primer ⇒ incorrecte. Pista del 2n error: el nombre de factors primers diferents ("3 primers diferents").
- `algebraic`: polinomis (sumes de monomis) amb coeficients enters o fraccions, una o més lletres (`x`, `y`, `a`, `b`…), potències `^n` o superíndexs, producte implícit (`3xy`, `2x²y`), `·`/`*`. Compara per equivalència (forma canònica: diccionari monomi → coeficient). Pista: el grau de la resposta.
- `sexagesimal`: `params.mode` `"time"` (h, min, s; també `h:mm` i `h:mm:ss`) o `"angle"` (`°`, `'`, `''`; accepta també `º` i cometes tipogràfiques). Compara el total en segons i exigeix minuts i segons < 60 (si l'alumne escriu `1 h 75 min`, és error amb nota "normalitza"). Pista: les hores (o graus).
- `number`: confirmar que `−24`, `-24` i `− 24` funcionen (amb test).

## 3. Figures noves (SVG en línia, mateix estil que E3)

| `type` | Camps |
|---|---|
| `grid` (ampliació) | `min`, `max` (per defecte 0 i 10; m7 fa servir −6..6), eixos al 0; `line: {m, n}` opcional (dibuixa `y = mx + n` dins la graella). |
| `parallels` | `angle` (graus de l'angle conegut, 20..160), `known` i `ask`: posicions `1..8` (els 8 angles que forma la secant amb les dues paral·leles). Dibuixa el conegut amb el valor i el demanat amb `?`. |
| `right_triangle` | `a`, `b`, `c` (catets i hipotenusa), `ask`: `"a" \| "b" \| "c"`; marca d'angle recte; mides a fora (com E4); `?` al costat demanat. |
| `number_line` | `min`, `max`, `point` (enter), `label?` (p. ex. "°C"). |

Validació al servidor (figura invàlida o incoherent ⇒ ítem descartat i reportat).

## 4. Generadors de m7

Per a cada un: resposta i figura coherents, sense targetes repetides dins la llista.

| kind | Exemple | Resposta |
|---|---|---|
| `int_signs` | `(−6) · (+4)`, `(−36) : (−9)`, `−7 + 12` | number |
| `abs_opp` | `|−7| = ?`, `Oposat de −12` | number |
| `int_combined` | `−3 + 4 · (−2)²`, `[5 − (−3)] · (−2)` | number |
| `prime_factors` | `Descompon 360` (nombres 24..2000 amb almenys 3 factors) | factorization |
| `gcd_lcm` | `MCD(36, 48)`, `mcm(12, 18)` | number |
| `frac_simplify` | `Simplifica 84/126` | fraction (`simplest`) |
| `frac_combined` | `(1/2 + 1/3) · 3/5`, `(2/3)² − 1/9` | fraction (`value`) |
| `decimal_type` | `0,3333…`, `0,1666…`, `0,375` | choice `["exacte", "periòdic pur", "periòdic mixt"]` |
| `generatrix` | `0,375 = ?` (decimals exactes) | fraction (`simplest`) |
| `power_props` | `2³ · 2⁴ = 2^?`, `(5²)³ = 5^?`, `6⁵ : 6² = 6^?`, `3⁴ · 5⁴ = ?^4` | number |
| `int_sqrt` | `Arrel quadrada sencera de 50, i residu` | pair (`(7, 1)`) |
| `translate_expr` | `El doble d'un nombre més 3` | choice amb 4 expressions (1 correcta + 3 distractors plausibles) |
| `value_expr` | `3x − 2 per a x = −4` | number |
| `monomial_parts` | `Grau de −5x³y²`, `Coeficient de −5x³y²` | number |
| `monomial_ops` | `3x² + 5x² − x²`, `(2x) · (3x²)`, `4ab − 7ab` | algebraic |
| `linear_eq` | `3(x − 2) = 2x + 5` (solució entera, pot ser negativa) | number |
| `proportion_type` | situacions (obrers i dies, kg i preu…) | choice `["directa", "inversa"]` |
| `rule_of_three` | directa i inversa amb resultat enter | number |
| `chained_percent` | `200 €, puja un 10 % i baixa un 20 %` | number (resultat exacte, pot tenir decimals) |
| `quadrant_point` | figura `grid` −6..6 amb un punt | pair (coordenades negatives) |
| `linear_func` | `y = 2x − 3. Quant val y per a x = 4?` | number |
| `line_read` | figura `grid` amb recta: `Pendent?` / `Ordenada a l'origen?` (m i n enters) | number |
| `pythagoras` | figura `right_triangle` (ternes pitagòriques i múltiples) | unit `cm` |
| `parallel_angles` | figura `parallels`: `Quant mesura l'angle ?` | number (graus) |
| `polygon_angle_sum` | `Suma dels angles interiors d'un hexàgon` | number |
| `notable_points` | `Punt on es tallen les mediatrius` | choice `["circumcentre", "incentre", "baricentre", "ortocentre"]` |
| `composite_area` | `Corona circular de radis 5 cm i 3 cm (π = 3,14)`, `Sector de 90° de radi 4 cm` | unit `cm²` (decimal exacte amb π = 3,14) |
| `unit_area_volume` | `3,5 m² = ? dm²`, `2 dm³ = ? cm³`, `1,2 m³ = ? l` | unit |
| `speed_convert` | `72 km/h = ? m/s` (resultats enters) · densitat simple `massa = ? g` | unit |
| `sexagesimal_ops` | `2 h 35 min × 3`, `5 h 20 min − 2 h 45 min`, `75° 40' : 4` (exacte) | sexagesimal |
| `variable_type` | `Nombre de germans`, `Color preferit`, `Alçada` | choice `["qualitativa", "quantitativa discreta", "quantitativa contínua"]` |
| `freq_relative` | `20 alumnes, 5 tenen gos. Freqüència relativa?` | fraction (`value`, accepta decimal) |
| `median` | llista de 5-8 valors | number |
| `weighted_mean` | `Notes 6 (pes 2) i 8 (pes 3)` | number |
| `laplace` | `Dos daus: probabilitat que sumin 7`, `dues monedes: dues cares` | fraction (`value`) |

## 5. Tests

- TS: cada tipus nou (formats acceptats i rebutjats), cada figura (bona i dolenta), cada generador (determinisme, sense repetits, resposta recalculada de manera independent i coherent amb la figura).
- Python: ids iguals al servidor per a tots els `kind` nous.
- Captures amb Chromium (390 px) de: `parallels`, `right_triangle`, `grid` amb recta, `number_line`, una de `factorization`, al scratchpad.
- Tots: `server/test/*.test.ts`, `cd server && bun x tsc --noEmit`, `python3 -m unittest discover -s tests`. Única fallada esperada: les 4 llistes buides d'anglès.

## 6. Acceptació

- [ ] 3 tipus de resposta nous + `number` amb negatius verificat.
- [ ] 4 figures (3 noves + `grid` ampliada).
- [ ] 35 generadors de m7 deterministes i coherents.
- [ ] Res del que ja funciona canvia (m5, language). Tests en verd (llevat de l'esperada).
