# Disseny — exercicis de m7 i m6

Data: 2026-10-16. Mateix enfocament i estil que `docs/DISSENY-M5.md` (llegir-lo primer): **⚡ Flash** per al que es respon de cap en pocs segons, **🎲 Go (banc)** per al que demana procediment o un enunciat llarg. Ordre: **m7 primer, després m6.**

## 1. m7 (1r d'ESO)

`curriculum/math-m7.md` ja té 9 competències (propietats amb nombres, sintaxi amb lletres, valor numèric, distributiva i factor comú amb lletres, problemes per passos) amb banc. **Es mantenen tal qual** (ids, ítems, banc). S'hi sumen les competències noves.

### 1.1 Competències noves i canal

| Competència | Go (banc) | Flash |
|---|---|---|
| `m7.integers` [core] — enters, valor absolut, oposat, regla dels signes, combinades amb potències i claudàtors | `integers_combined` | `int_signs`, `abs_opp`, `int_combined` |
| `m7.factor_gcd_lcm` [core] — factors primers, MCD i mcm, problemes | `gcd_lcm_problems` | `prime_factors`, `gcd_lcm` |
| `m7.fractions` [core] — irreductible, combinades amb parèntesis i potències | `frac_combined` | `frac_simplify`, `frac_combined` |
| `m7.decimals_generatrix` — tipus de decimal, fracció generatriu (exactes) | `generatrix` | `decimal_type`, `generatrix` |
| `m7.powers_roots` [core] — propietats de potències, arrel sencera i residu | `powers_props` | `power_props`, `int_sqrt` |
| `m7.algebraic_language` [core] — traduir enunciats, valor numèric | `translate_expr` | `translate_expr` (choice), `value_expr` |
| `m7.monomials` [core] — coeficient, part literal, grau, suma/resta/producte | `monomials_ops` | `monomial_parts`, `monomial_ops` |
| `m7.linear_equations` [core] — transposició, parèntesis, problemes | `linear_equations` (+ steps `linear_eq_steps`) | `linear_eq` |
| `m7.proportionality` [core] — directa/inversa, regla de tres, percentatges encadenats | `proportion_problems` | `proportion_type`, `rule_of_three`, `chained_percent` |
| `m7.functions` — 4 quadrants, taules de valors, `y = mx + n` | `linear_function` | `quadrant_point`, `linear_func`, `line_read` |
| `m7.pythagoras` [core] | `pythagoras` | `pythagoras` (figura) |
| `m7.angles_lines` — paral·leles i secant, suma d'angles interiors | `polygon_angles` | `parallel_angles` (figura), `polygon_angle_sum` |
| `m7.triangle_points` — circumcentre, incentre, baricentre, ortocentre | — | `notable_points` (choice) |
| `m7.composite_areas` — descomposició, sectors, corones (π = 3,14) | `composite_areas` | `composite_area` |
| `m7.units_derived` — superfície i volum, km/h ↔ m/s, densitat | `units_derived` | `unit_area_volume`, `speed_convert` |
| `m7.sexagesimal` — suma, resta, × i : de temps i angles | `sexagesimal_ops` | `sexagesimal_ops` |
| `m7.statistics` — tipus de variable, freqüències, mitjana ponderada, mediana, moda, rang | `stats_tables` | `variable_type`, `freq_relative`, `median`, `weighted_mean` |
| `m7.probability` — espai mostral, Laplace | `laplace` | `laplace` |

### 1.2 Què cal afegir a Flash (motor)

**Tipus de resposta nous:**

| Tipus | Exemple | Regla |
|---|---|---|
| `factorization` | 360 → `2^3·3^2·5` | Accepta `2^3·3^2·5`, `2³·3²·5`, `2·2·2·3·3·5`, `*` o `x` com a producte; compara el multiconjunt de primers; un factor no primer és error. |
| `algebraic` | `3x² + 5x² − x²` → `7x²` | Equivalència de polinomis (sumes de monomis, coeficients enters o fraccions, diverses lletres, potències `^2`/`²`, producte implícit `3xy`). Mateixes regles que `mathgrade.parse_poly`. |
| `sexagesimal` | `2 h 35 min × 3` → `7 h 45 min` | Temps (`h`, `min`, `s`, també `2:05:10`) o angles (`°`, `'`, `''`); compara el total en segons; exigeix forma normalitzada (min, s < 60). |
| `number` | `(−6)·(+4)` → `−24` | Ja hi és; comprovar signe menys normal i `−` unicode. |

**Figures noves:** `grid` amb 4 quadrants (`min`, `max` negatius) i opcionalment una recta (`line: {m, n}`); `parallels` (dues paral·leles i una secant, un angle marcat amb el valor i un altre amb `?`); `right_triangle` (catets i hipotenusa, dos amb mida i un amb `?`); `number_line` (recta numèrica amb un punt, per a m6).

### 1.3 Requisit de nivell

`flash_share: 60` a `math-m7.md` (com m5).

## 2. m6 (6è de primària)

Fitxer nou `curriculum/math-m6.md` (no existeix). Molts generadors de Flash de m5 i m7 es reutilitzen; els propis de m6 s'afegeixen a l'encàrrec de contingut de m6.

| Competència | Go | Flash |
|---|---|---|
| `m6.powers_roots` [core] | `powers_value` | `power_value` |
| `m6.integers` [core] — temperatures, recta numèrica | `integers_context` | `int_number_line` (figura), `int_signs` (sumes/restes) |
| `m6.gcd_lcm` [core] | `gcd_lcm_problems` | `gcd_lcm` |
| `m6.fraction_ops` [core] — +, −, ×, : | `frac_ops4` | `frac_ops4` |
| `m6.decimal_division` [core] | `dec_division` | `dec_division` |
| `m6.percent_change` [core] — regla de tres, augments i descomptes | `percent_change` | `percent_change`, `rule_of_three` |
| `m6.scales` — mapes i plànols | `scales` | `scale` |
| `m6.equations_intro` | `equations_simple` (m5) | `equation` (m5) |
| `m6.area_units` — km² a mm², ha/a/ca | `area_units` | `area_units` |
| `m6.volume_capacity` — m³, dm³, l | `volume_units` | `volume_units` |
| `m6.angles_sexagesimal` | `sexagesimal_ops` (m7, nivell fàcil) | `angle_ops` |
| `m6.areas_polygons` [core] — regulars (apotema), rombe, trapezi | `areas_polygons` | `area_polygon_formula` |
| `m6.circle` [core] — longitud i àrea (π = 3,14) | `circle_measures` | `circle_measures` |
| `m6.volumes` — prismes i cilindres | `volumes_solids` | `volume_solid` |
| `m6.coordinates` — 4 quadrants | — | `quadrant_point` (m7) |
| `m6.statistics` — freqüència absoluta i relativa, mitjana, mediana, moda, rang | `mean_mode_range` (m5) + `stats_tables` (m7, fàcil) | `freq_relative`, `median`, `mean` |
| `m6.probability` | `probability_simple` (m5) | `probability` (m5) |

`flash_share: 60` a `math-m6.md`.

## 3. Encàrrecs i ordre

| # | Què | Paral·lel amb |
|---|---|---|
| **E5** | Flash: tipus `factorization`, `algebraic`, `sexagesimal`; figures `grid` 4 quadrants + recta, `parallels`, `right_triangle`, `number_line`; generadors de m7 (§1.1, columna Flash). | E6 |
| **E6** | Go m7: competències noves a `math-m7.md` + famílies del banc + banc generat. | E5 |
| **E7** | Contingut Flash de m7 (una llista per generador) + `flash_share: 60`. | E8 |
| **E8** | Go m6: `math-m6.md` + famílies + banc. | E7 |
| **E9** | Flash m6: generadors propis de m6 + llistes + `flash_share: 60`. | — |
