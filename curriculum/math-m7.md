---
language: math
level: m7
version: 1
status: pilot
pass_mark: 80
carry_mark: 65
checkpoint_items: 16
ready_share: 50
flash_share: 60
---

# Math m7 — Àlgebra operativa (1r d'ESO)

> Currículum real (WP1.1), autoritzat a partir dels dos drafts de l'Albert:
> `docs/competencies1eso.md` (marc competencial A/B/C) i
> `docs/AlgebraNumericaBasica.md` ("El Joc de les Propietats": BLOC 1 dels
> nombres, BLOC 2 de les lletres). **m7 = 1r d'ESO** — extensió de l'escala
> m1–m6 de la decisió D3 (primària); m8/m9 = 2n/3r d'ESO quan arribin.
>
> **Enquadrament pedagògic (no el perdis):** l'objectiu NO és "trobar quant
> val la lletra" — NO aïllem variables aquí. És l'**operativa, la sintaxi i
> l'agilitat algorísmica**: manipular expressions per fer-les més curtes o
> més fàcils de calcular, un joc de transformació d'estructures (dels nombres
> a les lletres, mateixes regles). La distributiva i el factor comú són la
> "caixa d'eines" mecànica per als cursos següents.
>
> Format: el mateix que `math-m4.md` / `en-A1.md` (`### id — Nom [core]`,
> `Can do`, `Depth`, `Weight`, `Requires`, `Forms`, `Words`, `Tags`,
> `Signals`, `Check:`), amb les adaptacions de `docs/DISSENY-MATEMATIQUES.md`
> §4.6: `Forms:` descriu el procediment, `Words:` el vocabulari de
> l'enunciat, `Tags:` categories d'error matemàtic (`#procedure`, `#sign`…)
> i `Check:` fa servir `Compute:` (valor o expressió, avaluable per
> `hooks/mathgrade.py` — equivalència polinòmica quan porta lletres) i
> `Steps:` (traça esperada "pas 1 ; pas 2 ; …", avaluada línia a línia).
>
> **Clau `Bank:`**: família de plantilles del generador (`scripts/mathbank.py`);
> les famílies `steps` s'han de generar amb `--family` explícit (l'escript
> `gen` les escriu a `curriculum/bank/math-m7/steps/`).

---

## Càlcul intel·ligent (dels nombres)

### m7.props_grouping — Moure i agrupar (commutativa i associativa) [core]
Can do: Reorder and regroup a sum or product so that a round pair (10, 20, 100…) is calculated first, without changing the result.
Depth: normal
Weight: 2
Forms: Busca la parella que suma 10/20/… o que multiplica a un nombre rodó; mou els termes (commutativa) i agrupa-la amb parèntesis (associativa); calcula primer la parella i després acaba l'operació.
Tags: #procedure, #calculation, #facts, commutativa, associativa, agrupar, parella rodona, sumands, factors, parèntesis
Signals: agrupa, mou, commutativa, associativa, parella, rodó, suma, producte, parèntesis, calcula mentalment
Bank: props_grouping_numeric
Check:
- Steps: 13 + 25 + 7 → (13 + 7) + 25 ; 20 + 25 ; 45
- Steps: 4 · 17 · 25 → (4 · 25) · 17 ; 100 · 17 ; 1700
- Steps: 8 + 34 + 12 → (8 + 12) + 34 ; 20 + 34 ; 54

### m7.props_distributive — Distributiva amb nombres (desplegar per simplificar) [core]
Can do: Break a multiplication over a sum or difference into two easy multiplications and add the results.
Depth: normal
Weight: 2
Requires: m7.props_grouping
Forms: Trenca el nombre del parèntesi en dos de més fàcils (10 + 3); el nombre de fora multiplica absolutament tots dos termes (5 · 10 + 5 · 3); calcula les dues multiplicacions i suma (o resta) els productes.
Tags: #procedure, #calculation, #facts, distributiva, desplegar, parèntesi, producte parcial, terme
Signals: distributiva, desplega, parèntesi, multiplica per a dins, trenca, simplificar
Bank: props_distributive_numeric
Check:
- Steps: 5 · (10 + 3) → 5 · 10 + 5 · 3 ; 50 + 15 ; 65
- Steps: 6 · (10 - 2) → 6 · 10 - 6 · 2 ; 60 - 12 ; 48
- Steps: 4 · (20 + 5) → 4 · 20 + 4 · 5 ; 80 + 20 ; 100

### m7.props_factor — Factor comú amb nombres (agrupar per calcular ràpid) [core]
Can do: Spot the multiplier repeated in both products and pull it out of the sum to shorten the calculation.
Depth: normal
Weight: 2
Requires: m7.props_distributive
Forms: Mira què es repeteix a tots els termes (el 7 de 7 · 8 + 7 · 2); treu el factor comú a fora del parèntesi (7 · (8 + 2)); suma primer els de dins i multiplica una sola vegada.
Tags: #procedure, #calculation, #facts, factor comú, agrupar, repetir, desplegar invers
Signals: factor comú, es repeteix, treu fora, agrupa, estalvia passos
Bank: props_factor_numeric
Check:
- Steps: 7 · 8 + 7 · 2 → 7 · (8 + 2) ; 7 · 10 ; 70
- Steps: 3 · 15 - 3 · 5 → 3 · (15 - 5) ; 3 · 10 ; 30
- Steps: 8 · 6 + 8 · 4 → 8 · (6 + 4) ; 8 · 10 ; 80

## A. Sintaxi i agrupació (l'entrada de les lletres)

### m7.syntax_letters — Commutativa i associativa amb lletres [core]
Can do: Group like terms of an expression (same letter together, numbers on their own) into a shorter equivalent expression.
Depth: normal
Weight: 3
Requires: m7.props_grouping
Forms: Les lletres iguals es poden sumar entre elles; els nombres sols van per la seva banda. Reordena (3x + 5 + 2x → (3x + 2x) + 5) i suma els coeficients de cada lletra; el resultat és una expressió equivalent, no un nombre.
Tags: #procedure, #sign, #calculation, termes semblants, coeficient, lletra, agrupar, expressió equivalent, part numèrica
Signals: simplifica, agrupa, termes, lletres iguals, coeficient, expressió, equivalent
Bank: syntax_grouping_letters
Check:
- Compute: 3x + 5 + 2x → 5x + 5
- Compute: 4y + 7z + 2y + z → 6y + 8z
- Compute: 4x + 10 + 3x → 7x + 10

### m7.value_numeric — El valor numèric (mecànica de substitució) [core]
Can do: Substitute numbers for letters in an expression and evaluate it with the correct order of operations.
Depth: normal
Weight: 2
Requires: m7.syntax_letters
Forms: La lletra és una casella on s'insereix un valor: substitueix cada lletra pel seu número (2a − 3b amb a = 5, b = 2 → 2 · 5 − 3 · 2); respecta la jerarquia d'operacions (multiplicacions abans que sumes i restes); el resultat és un nombre.
Tags: #order_of_operations, #calculation, #procedure, substitució, valor numèric, casella, jerarquia d'operacions, avaluar
Signals: substitueix, valor, si val, calcula el valor, expressió, resultat
Bank: value_numeric
Check:
- Compute: 2a - 3b, amb a = 5 i b = 2 → 4
- Compute: 3x + 2, amb x = 4 → 14
- Compute: 5y - 3, amb y = 6 → 27

## B. La distributiva amb lletres

### m7.distributive_letters — Distributiva amb lletres (desplegant paquets) [core]
Can do: Expand k(x ± c) into kx ± kc, including a negative outside factor where the signs inside change.
Depth: deep
Weight: 3
Requires: m7.props_distributive, m7.syntax_letters
Forms: El nombre de fora multiplica absolutament tot el que hi ha dins del parèntesi (3 · (x + 4) → 3x + 12). Gestió del signe: si el de fora és negatiu (−2 · (x + 4)), els signes de dins canvien en desplegar (−2x − 8). El resultat és una expressió, no es resol res.
Tags: #procedure, #sign, #wrong_operation, #calculation, distributiva, desplegar, parèntesi, signe, coeficient
Signals: desplega, distributiva, parèntesi, multiplica tot, signe, menys
Bank: distributive_letters
Check:
- Compute: 3 · (x + 4) → 3x + 12
- Compute: 2 · (3y - 5) → 6y - 10
- Compute: -2 · (x + 4) → -2x - 8

## C. El factor comú

### m7.factor_letters — Factor comú amb lletres (el pas estrella) [core]
Can do: Extract the common factor of an expression at four levels: a repeated letter, letter plus number, a hidden number (multiplication table), and x² as x · x.
Depth: deep
Weight: 3
Requires: m7.distributive_letters, m7.props_factor
Forms: Busca què es repeteix a TOTS els termes i treu-ho fora del parèntesi. Nivell 1, només lletra: ax + bx → x(a + b). Nivell 2, lletra i número: 4x + xy → x(4 + y). Nivell 3, número amagat (taula de multiplicar): 8x + 12 → 4(2x + 3). Nivell 4, potències: x² vol dir x · x, així que x² + 5x → x(x + 5). És el pas invers de la distributiva: es transforma l'expressió, no es resol.
Tags: #procedure, #facts, #simplification, #sign, factor comú, extreure, taula de multiplicar, potència, x quadrada, pas invers
Signals: factor comú, treu fora, es repeteix, transforma, factoritza, x al quadrat
Bank: factor_letters
Check:
- Compute: 7x + 7y → 7(x + y)
- Compute: 10x + 15 → 5(2x + 3)
- Compute: x^2 + 9x → x(x + 9)

## D. Problemes (prova)

### m7.problems_generic — Problemes genèrics amb enunciat, per passos [extra]
Can do: Read a short story problem that may mix operations, write the operations one per line and reach the result.
Depth: light
Forms: Llegeix l'enunciat sencer; tria l'operació de cada part («baixen» = restar, «pugen» = sumar, «cadascun» = multiplicar); escriu una operació per línia i acaba amb el resultat.
Tags: #wrong_operation, #calculation, #procedure, problema, enunciat, operació, resultat
Signals: problema, enunciat, quant, quants, en total, queden, cadascun
Check:
- Steps: 4 × (7 + 3) → 4 × 10 ; 40
- Steps: 38 - 12 + 9 → 35 - 15 ; 20
- Steps: 5 × 6 + 5 × 4 → 30 + 20 ; 50

---

> **E6 (2026-10-16, DISSENY-M7-M6 §1.1):** competències noves de l'àmbit Go. Cada una
> té la seva família de `scripts/mathbank.py` (`Bank:`), llevat de `m7.triangle_points`,
> que només té Flash (sense `Bank:`, com diu el disseny). El banc és a
> `curriculum/bank/math-m7/` (fitxers nous). `checkpoint_items` passa a 16 perquè el
> nombre de competències `[core]` ho exigeix (7 de les antigues + 9 de noves).

## Nombres enters i divisibilitat

### m7.integers — Enters: signes, valor absolut i operacions combinades [core]
Can do: Compute expressions with negative integers, powers, parentheses and nested parentheses, applying the sign rules.
Depth: normal
Weight: 2
Requires: m7.props_grouping
Forms: Primer els parèntesis (els de dins abans que els de fora); després les potències; després les multiplicacions; després les sumes i restes. Regla dels signes: + per + i − per − donen +; + per − i − per + donen −. Restar un negatiu és sumar el seu oposat.
Tags: #sign, #order_of_operations, #calculation, #procedure, enters, signe, negatiu, oposat, valor absolut, potència, parèntesi
Signals: negatiu, signe, oposat, valor absolut, parèntesi, potència, combinada, enter
Bank: integers_combined
Check:
- Compute: (-3) · (4 - 9) + 2^2 → 19
- Compute: -6 - 2 · (-5 + 1) → 2
- Steps: (-4)^2 - 3 · (-5) → 16 + 15 ; 31

### m7.factor_gcd_lcm — Factors primers, MCD i mcm en problemes [core]
Can do: Factorise numbers into primes and find the greatest common divisor or the least common multiple to solve a context problem.
Depth: normal
Weight: 2
Requires: m7.props_grouping
Forms: Descompon cada nombre en factors primers, dividint pel primer primer que hi cap. MCD: els factors comuns amb el menor exponent (el tros més gran que cap exactament en totes dues). mcm: tots els factors amb el major exponent (el primer moment en què coincideixen). Talls en trossos iguals és MCD; coincidir cada tant és mcm.
Tags: #procedure, #facts, #calculation, factors primers, MCD, mcm, divisor, múltiple, descomposició
Signals: MCD, mcm, factors primers, divisor, múltiple, coincideixen, talls, iguals, tros, cada
Bank: gcd_lcm_problems
Check:
- Compute: Quin és el MCD de 36 i 48? → 12
- Compute: Quin és el mcm de 6 i 8? → 24
- Compute: Dos autobusos passen cada 12 i cada 18 minuts. Al cap de quants minuts coincideixen? → 36

## Fraccions, decimals i potències

### m7.fractions — Fraccions irreductibles i combinades [core]
Can do: Simplify a fraction to its irreducible form and compute combined operations with fractions, parentheses and powers.
Depth: normal
Weight: 2
Requires: m7.factor_gcd_lcm
Forms: Simplifica dividint numerador i denominador pel mateix nombre (el MCD és el que ho deixa irreductible). En una expressió combinada: primer el parèntesi, després la potència, després la multiplicació o la divisió (dividir per una fracció és multiplicar per la inversa), i la suma o la resta amb denominador comú.
Tags: #simplification, #procedure, #calculation, fracció, irreductible, simplificar, denominador comú, parèntesi, potència, inversa
Signals: fracció, simplifica, irreductible, parèntesi, potència, dividir, multiplicar, inversa, combinada
Bank: frac_combined
Check:
- Compute: (3/4 - 1/2) × 2/5 → 1/10
- Compute: (2/3)^2 + 1/6 → 11/18
- Compute: (1/2 + 1/3) ÷ 5/6 → 1

### m7.decimals_generatrix — Decimals exactes i fracció generatriu [extra]
Can do: Write a finite decimal as an irreducible fraction (its generating fraction).
Depth: light
Weight: 2
Forms: Un decimal exacte té tants decimals com zeros té el denominador: 0,36 = 36/100. Simplifica la fracció pel MCD del numerador i el denominador. Els decimals periòdics no entren aquí.
Tags: #simplification, #place_value, #procedure, decimal, exacte, generatriu, fracció, irreductible, decimals
Signals: decimal, coma, fracció, generatriu, exacte, simplifica, irreductible
Bank: generatrix
Check:
- Compute: 0,36 → 9/25
- Compute: 2,5 → 5/2
- Compute: 0,125 → 1/8

### m7.powers_roots — Propietats de les potències [core]
Can do: Apply the exponent rules for products, quotients and powers of powers, and write the result as one power.
Depth: normal
Weight: 2
Requires: m7.props_grouping
Forms: Mateixa base: en multiplicar se sumen els exponents; en dividir es resten; potència de potència: es multipliquen. El resultat és una sola potència de la mateixa base (o el seu valor).
Tags: #procedure, #facts, #calculation, potència, exponent, base, propietat, producte, quocient
Signals: potència, exponent, base, mateixa base, elevat a, al quadrat, al cub
Bank: powers_props
Check:
- Compute: 2^3 × 2^4 → 2^7
- Compute: 3^8 ÷ 3^5 → 27
- Compute: (5^2)^3 → 5^6

## Àlgebra

### m7.algebraic_language — Llenguatge algebraic: traduir enunciats [core]
Can do: Translate a sentence about an unknown number into an algebraic expression with a letter, and evaluate it when a value is given.
Depth: normal
Weight: 2
Requires: m7.syntax_letters
Forms: Dona nom a la lletra (x és el nombre). Tradueix cada paraula clau: «el doble» és 2 · x; «el triple», 3 · x; «més» és +; «menys» i «la diferència» són restar; «el quadrat» és x^2; «augmentat en» és +; «multiplicat per» és · i, si cal, parèntesi.
Tags: #misread, #wrong_operation, #procedure, llenguatge algebraic, traducció, enunciat, expressió, lletra, doble, triple
Signals: doble, triple, quadrat, més, menys, diferència, augmentat, multiplicat, expressió, nombre
Bank: translate_expr
Check:
- Compute: el triple d'un nombre x, menys 4 → 3x - 4
- Compute: un nombre x augmentat en 2 i després multiplicat per 5 → 5x + 10
- Compute: el quadrat d'un nombre x més el seu doble → x^2 + 2x

### m7.monomials — Monomis: coeficient, part literal i operacions [core]
Can do: Identify the coefficient and the literal part of a monomial, multiply monomials, and add or subtract like terms.
Depth: normal
Weight: 2
Requires: m7.syntax_letters
Forms: El coeficient és el nombre que acompanya les lletres; la part literal són les lletres amb els seus exponents. Producte: es multipliquen els coeficients i se sumen els exponents de cada lletra. Suma i resta: només es poden sumar monomis amb la mateixa part literal; se sumen els coeficients i la part literal es queda igual.
Tags: #procedure, #sign, #calculation, monomi, coeficient, part literal, termes semblants, exponent, producte
Signals: monomi, coeficient, part literal, termes semblants, multiplica, suma, potència, exponent
Bank: monomials_ops
Check:
- Compute: 3x^2y · (-2xy^3) → -6x^3y^4
- Compute: 5a^2b + 3a^2b - a^2b → 7a^2b
- Compute: (2x^3)^2 → 4x^6

### m7.linear_equations — Equacions de primer grau: parèntesis i transposició [core]
Can do: Solve a linear equation with a whole solution, removing brackets first and then moving the terms with the unknown to one side.
Depth: deep
Weight: 3
Requires: m7.distributive_letters, m7.integers
Forms: Primer treu els parèntesis (distributiva). Després redueix les x d'un costat i els nombres de l'altre: quan un terme canvia de costat, canvia de signe (transposició). Finalment divideix pel coeficient de la x. Comprova substituint el resultat a l'equació.
Tags: #procedure, #sign, #calculation, #simplification, equació, transposició, parèntesi, incògnita, solució, signe
Signals: equació, resol, transposa, incògnita, igualtat, parèntesi, solució, x val
Bank: linear_equations
Check:
- Compute: 2 · (x + 3) + x = 15 → 3
- Compute: 4x + 7 = 2x + 15 → 4
- Compute: 3 · (x - 2) = -9 → -1

## Proporcionalitat i funcions

### m7.proportionality — Proporcionalitat: directa, inversa i percentatges encadenats [core]
Can do: Solve direct and inverse proportion problems with a rule of three, and chain percentage increases and decreases.
Depth: normal
Weight: 2
Requires: m7.fractions
Forms: Directa: el quocient entre les quantitats es manté (preu unitari = total ÷ quantitat; després es multiplica). Inversa: el producte es manté (obrers × dies = treball constant; els dies es divideixen). Percentatges encadenats: cada variació és un factor (pujar un 20 % és × 1,2; baixar un 10 % és × 0,9) i els factors es multipliquen.
Tags: #procedure, #wrong_operation, #calculation, proporció directa, inversa, regla de tres, percentatge, factor, encadenat
Signals: proporció, directa, inversa, regla de tres, per cada, percentatge, puja, baixa, descompte
Bank: proportion_problems
Check:
- Compute: 3 quaderns iguals costen 7,50 €. Quant costen 8 quaderns com aquests? → 20 €
- Compute: 4 obrers fan una feina en 6 dies. Quants dies trigaran 8 obrers? → 3
- Compute: Un article val 50 €. Puja un 20 % i després baixa un 10 %. Quin és el preu final? → 54 €

### m7.functions — Funcions lineals: taules, quadrants i y = mx + n [extra]
Can do: Use a straight line y = mx + n: find y for a given x, the slope from two points, or the intercept from a point and the slope.
Depth: normal
Weight: 2
Forms: Un punt és (x, y): la x primer. La pendent m és l'increment de y entre l'increment de x. L'ordenada a l'origen n és el valor de y quan x = 0; amb un punt i la pendent, n = y - m · x. Per calcular y, substitueix la x i respecta els signes.
Tags: #sign, #calculation, #procedure, funció, recta, pendent, ordenada a l'origen, quadrant, coordenades, substitució
Signals: recta, pendent, y = mx + n, punt, coordenades, quadrant, ordenada, taula, valor
Bank: linear_function
Check:
- Compute: La recta és y = 2x - 3. Quin valor té y quan x = 4? → 5
- Compute: Una recta passa pels punts (1, 5) i (3, 9). Quina és la seva pendent? → 2
- Compute: Una recta té pendent 2 i passa pel punt (1, 5). Quina és l'ordenada a l'origen? → 3

## Geometria

### m7.pythagoras — Teorema de Pitàgores [core]
Can do: Use c² = a² + b² to find the square of the hypotenuse, or of a missing leg, of a right triangle.
Depth: normal
Weight: 2
Requires: m7.powers_roots
Forms: En un triangle rectangle, la hipotenusa (c) és el costat més llarg, el que és oposat a l'angle recte. c² = a² + b²; per trobar un catet, b² = c² − a². Calcula primer els quadrats i després suma o resta.
Tags: #calculation, #procedure, #wrong_operation, Pitàgores, hipotenusa, catet, angle recte, quadrat, triangle rectangle
Signals: triangle rectangle, hipotenusa, catet, Pitàgores, quadrat, angle recte, mesura
Bank: pythagoras
Check:
- Compute: Catets de 9 cm i 12 cm: quin és el quadrat de la hipotenusa (en cm²)? → 225 cm²
- Compute: Hipotenusa de 13 cm i catet de 5 cm: quin és el quadrat de l'altre catet (en cm²)? → 144 cm²
- Compute: Hipotenusa de 10 cm i catet de 6 cm: quin és el quadrat de l'altre catet (en cm²)? → 64 cm²

### m7.angles_lines — Angles interiors dels polígons [extra]
Can do: Calculate the sum of the interior angles of a polygon, and one angle of a regular polygon.
Depth: normal
Weight: 2
Forms: Un polígon de n costats es divideix en n − 2 triangles des d'un vèrtex; la suma dels angles interiors és (n − 2) · 180°. En un polígon regular tots els angles són iguals: divideix la suma entre n.
Tags: #calculation, #procedure, #facts, angles, polígon, interior, suma, regular, triangle
Signals: polígon, costats, angles interiors, suma d'angles, regular, graus, triangles
Bank: polygon_angles
Check:
- Compute: Suma dels angles interiors d'un polígon de 8 costats (en graus)? → 1080
- Compute: Cada angle interior d'un hexàgon regular (en graus)? → 120
- Compute: Suma dels angles interiors d'un triangle (en graus)? → 180

### m7.composite_areas — Àrees de figures compostes (π = 3,14) [extra]
Can do: Find the area of a figure made of rectangles, squares or circles, by adding or subtracting its parts.
Depth: normal
Weight: 2
Forms: Descompon la figura en parts conegudes (rectangles, quadrats, cercles) o imagina-la com una figura gran menys una de petita (com una corona). Àrea del cercle: π · r², amb π = 3,14. Escriu les unitats al resultat (cm²).
Tags: #calculation, #unit, #procedure, àrea, figura composta, cercle, corona, π, descomposició
Signals: àrea, figura, retallat, cercle, radi, corona, π, descompon, quadrat, rectangle
Bank: composite_areas
Check:
- Compute: Rectangle de 8 cm × 5 cm amb un quadrat de 2 cm retallat: àrea (en cm²)? → 36 cm²
- Compute: Cercle de radi 10 cm (π = 3,14): àrea (en cm²)? → 314 cm²
- Compute: Corona amb radi exterior 5 cm i radi interior 2 cm (π = 3,14): àrea (en cm²)? → 65,94 cm²

### m7.triangle_points — Punts notables del triangle [extra]
Can do: Recognise the four notable points of a triangle and find the centroid (baricentre) from its vertices.
Depth: light
Weight: 1
Forms: Baricentre: intersecció de les medianes; les seves coordenades són la mitjana de les coordenades dels tres vèrtexs. Circumcentre: equidistant dels vèrtexs (mediatrius). Incentre: equidistant dels costats (bisectrius). Ortocentre: intersecció de les alçades.
Tags: #facts, #calculation, punts notables, baricentre, circumcentre, incentre, ortocentre, mediatriu, bisectriu, alçada
Signals: baricentre, circumcentre, incentre, ortocentre, mediatriu, bisectriu, alçada, mediana, vèrtex
Check:
- Compute: Baricentre dels vèrtexs (0, 0), (6, 0) i (3, 9): coordenada x? → 3
- Compute: Baricentre dels vèrtexs (0, 0), (6, 0) i (3, 9): coordenada y? → 3
- Compute: Quants punts notables té un triangle (circumcentre, incentre, baricentre, ortocentre)? → 4

## Estadística i probabilitat

### m7.statistics — Estadística: freqüències, mitjana, mediana, moda i rang [extra]
Can do: Read a frequency table or a short list of data and find the weighted mean, the median, the mode and the range.
Depth: normal
Weight: 2
Forms: Mitjana ponderada: multiplica cada valor per la seva freqüència, suma-ho tot i divideix pel total de dades. Mediana: ordena les dades; és el valor del mig (o la mitjana dels dos del mig si el nombre de dades és parell). Moda: el valor que més es repeteix. Rang: el més gran menys el més petit.
Tags: #calculation, #procedure, #misread, estadística, mitjana, mediana, moda, rang, freqüència, ordenar
Signals: mitjana, mediana, moda, rang, freqüència, dades, ordena, taula, mitjana ponderada
Bank: stats_tables
Check:
- Compute: 4 alumnes han tret un 6 i 6 alumnes un 8. Quina és la nota mitjana? → 7,2
- Compute: Les notes són 4, 9, 6, 7 i 5. Quina és la mediana? → 6
- Compute: Les temperatures són 12, 17, 9 i 15 graus. Quin és el rang? → 8

### m7.probability — Probabilitat: regla de Laplace [extra]
Can do: Compute the probability of an event whose outcomes are equally likely, as a fraction, and simplify it.
Depth: normal
Weight: 2
Forms: Probabilitat = casos favorables ÷ casos possibles (només si tots els casos són igualment probables). Escriu-la com a fracció; si es pot, simplifica-la (la forma simplificada també val).
Tags: #calculation, #simplification, #procedure, probabilitat, Laplace, casos favorables, casos possibles, fracció, espai mostral
Signals: probabilitat, possible, favorable, dau, bossa, boles, fracció, espai mostral, de cada
Bank: laplace
Check:
- Compute: Es llança un dau de 6 cares. Quina probabilitat hi ha de treure un nombre parell? → 1/2
- Compute: Una bossa té 4 boles vermelles i 6 de blaves. Quina probabilitat hi ha de treure una de vermella? → 2/5
- Compute: Es llança un dau de 6 cares. Quina probabilitat hi ha de treure un múltiple de 3? → 1/3

## Mesura

### m7.units_derived — Unitats derivades: superfície, volum, velocitat i densitat [extra]
Can do: Convert areas and volumes between units, convert km/h to m/s, and compute a density as mass over volume.
Depth: normal
Weight: 2
Forms: Un canvi d'unitat de superfície va de 100 en 100 (1 m² = 100 dm²) i de volum de 1000 en 1000 (1 m³ = 1000 dm³). Per passar de km/h a m/s es divideix entre 3,6 (1 km = 1000 m i 1 h = 3600 s). La densitat és la massa dividida pel volum (g/cm³).
Tags: #unit, #calculation, #procedure, unitats, superfície, volum, km/h, m/s, densitat, conversió
Signals: unitat, superfície, volum, dm², cm³, km/h, m/s, densitat, convertir, massa
Bank: units_derived
Check:
- Compute: Quants dm² són 1 m²? → 100 dm²
- Compute: Un prisma té base de 4 cm × 5 cm i alçada de 10 cm. Quin és el volum (en cm³)? → 200 cm³
- Compute: Un tren va a 72 km/h. Quants metres recorre per segon? → 20

### m7.sexagesimal — Hores, minuts i angles: operacions [extra]
Can do: Add, subtract and multiply durations given in hours and minutes, and express the result in minutes.
Depth: light
Weight: 1
Forms: Passa cada temps a minuts (1 h = 60 min) abans d'operar: 2 h 35 min són 2 · 60 + 35 = 155 min. Opera amb els minuts totals i, si cal, torna-ho a passar a hores i minuts (més de 60 min és una hora més). Quan calgui, el resultat s'escriu en minuts.
Tags: #unit, #calculation, #procedure, hores, minuts, sexagesimal, durada, suma, resta, conversió
Signals: hores, minuts, durada, temps, dura, suma, resta, multiplica, quants minuts, h i min
Bank: sexagesimal_ops
Check:
- Compute: Una pel·lícula dura 2 h 35 min. Quants minuts duren 3 pel·lícules seguides? → 465 min
- Compute: Quant temps passa entre 1 h 50 min i 3 h 15 min? Dona-ho en minuts. → 85 min
- Compute: Quants minuts sumen 2 h 35 min i 1 h 50 min? → 265 min
