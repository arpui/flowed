# Encàrrec E9 — Flash de m6 (generadors propis i contingut)

Branca: `flash-vocab`. Disseny: `docs/DISSENY-M7-M6.md` §2. Mateixes regles que E1/E5 (generadors deterministes, `count`, ids `g1…gN`, mirall Python per `count`) i que E4/E7 per al contingut. Decisions tancades.

## 1. Generadors nous (motor: `server/src/flash.ts`, mirall Python, tests)

| kind | Exemple | Resposta |
|---|---|---|
| `power_value` | `3⁴`, `√144` | number |
| `int_number_line` | figura `number_line` amb temperatura: `Eren −3 °C i puja 8 °C` | number |
| `frac_ops4` | `2/3 · 3/4`, `5/6 : 2/3`, `1/2 + 2/5` | fraction (`value`) |
| `dec_division` | `7,2 : 0,8`, `9,6 : 4` | number |
| `percent_change` | `Augment del 15 % sobre 80`, `Descompte del 20 % sobre 45` | number |
| `scale` | `Escala 1:50.000. 3 cm al mapa = ? km` | unit |
| `area_units` | `2,5 ha = ? m²`, `3 km² = ? hm²` | unit |
| `volume_units` | `1,5 m³ = ? l`, `250 cm³ = ? ml` | unit |
| `angle_ops` | `35° 40' + 20° 30'`, `90° − 35° 25'` | sexagesimal (`angle`) |
| `area_polygon_formula` | `Hexàgon regular de costat 6 cm i apotema 5,2 cm`, rombe `D = 8, d = 6`, trapezi | unit `cm²` |
| `circle_measures` | `Longitud d'una circumferència de radi 5 cm (π = 3,14)`, àrea | unit |
| `volume_solid` | prisma rectangular, cilindre (π = 3,14) | unit `cm³` |

Captures (Chromium, 390 px) de `int_number_line` i una de `angle_ops`, al scratchpad.

## 2. Contingut

Carpeta `curriculum/flash/math-m6/`: `00-taules-repas.json` (`mult` [1,1], 24) i una llista per generador de la columna Flash de §2 del disseny (els propis d'aquí i els reutilitzats de m5/m7: `int_signs`, `gcd_lcm`, `rule_of_three`, `equation`, `quadrant_point`, `freq_relative`, `median`, `mean`, `probability`), amb `competence` = id de `math-m6.md`. A `math-m6.md`, `flash_share: 60`.

## 3. Tests i acceptació

Mateixos que E5 (generadors) i E7 (contingut). Tots els tests; única fallada esperada: les 4 llistes buides d'anglès.

- [ ] 12 generadors nous de m6. [ ] Llistes de m6 amb `competence`. [ ] `flash_share: 60`. [ ] Res més canvia.

## 4. Afegit: poliment de `parallels` (de les captures d'E7)

Amb angles petits (20°) la secant queda gairebé horitzontal, els arcs són minúsculs i l'etiqueta queda tapada. Al generador `parallel_angles`, limita l'angle conegut a **35°..145°** (múltiples de 5) i a la validació de la figura accepta igualment 20..160 per als ítems escrits a mà. Nova captura de la graella de casos (35° i 145°, posicions al mateix vèrtex i creuades) al scratchpad.
