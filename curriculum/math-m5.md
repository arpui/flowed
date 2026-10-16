---
language: math
level: m5
version: 1
status: esborrany
pass_mark: 80
carry_mark: 65
checkpoint_items: 12
ready_share: 50
---

# Math m5 — currículum (esborrany)

> Competències de 5è de primària segons el disseny `docs/DISSENY-M5.md` §2.3 (Go: el
> banc d'exercicis). Els exercicis que es poden respondre de cap en pocs segons (fets,
> taules, conversions simples) van pel canal Flash (`curriculum/flash/`, encàrrec E4);
> aquí hi ha les competències amb procediment, càlcul llarg i problemes de 2-3 passos.
>
> Format: el mateix que `math-m4.md` (`### id — Nom [core]`, `Can do`, `Depth`,
> `Weight`, `Requires`, `Forms`, `Tags`, `Signals`, `Bank:`, `Check:`). `Check:` fa
> servir `Compute:` (valor o resultat amb unitat, avaluable per `hooks/mathgrade.py`) i
> `Steps:` (traça completa, un pas per ` ; `).
>
> **Clau `Bank:`**: la família de `scripts/mathbank.py` que genera el banc de la
> competència (les de passos, `Steps:`, es generen amb `--family` explícit). Les
> competències sense ítems de càlcul (p. ex. `m5.distributive`) declaren la família de
> passos.
>
> Sense `flash_share`: el contingut Flash de m5 el deixa E4.

---

## Càlcul

### m5.mult_3digit — Multiplicacions de 3 xifres [core]
Can do: Multiply a 3-digit number by a 2-digit or 3-digit number, with and without carrying.
Depth: normal
Weight: 3
Forms: Multiplica el primer factor per cada xifra del segon, començant per les unitats i desplaçant cada producte parcial a la seva posició (per les desenes, per les centenes); suma els productes parcials alineats, transportant quan una xifra passa de 9.
Tags: #calculation, #carrying, #place_value, multiplicació, producte parcial, transport, centenes, desenes, unitats
Signals: multiplica, multiplicació, vegades, producte, factor, centenes, desenes, unitats, transport
Bank: mult_3digit
Check:
- Compute: 342 × 27 → 9234
- Compute: 408 × 53 → 21624
- Steps: 342 × 27 → 342 × 20 ; 342 × 7 ; 6840 + 2394

### m5.div_2digit — Divisió exacta per un divisor de 2 xifres [core]
Can do: Divide a 3- or 4-digit number exactly by a 2-digit number, subtracting multiples of the divisor step by step.
Depth: normal
Weight: 3
Requires: m5.mult_3digit
Forms: Busca el múltiple del divisor per les desenes del quocient que no passi del dividend; resta'l; el que queda es reparteix per les unitats del quocient (quocient de l'última xifra); ajunta les desenes i les unitats del quocient.
Tags: #facts, #procedure, #calculation, divisió, quocient, múltiple, taula de multiplicar, resta, desenes, unitats
Signals: divideix, divisió, quocient, repartir, exacta, múltiple, resta, cabre
Bank: div_2digit
Check:
- Compute: 1344 ÷ 24 → 56
- Compute: 2592 ÷ 36 → 72
- Steps: 1344 ÷ 24 → 24 × 50 ; 1344 - 1200 ; 144 ÷ 24 ; 50 + 6

### m5.combined_ops — Operacions combinades (jerarquia i parèntesis) [core]
Can do: Evaluate an expression with several operations, multiplication and division before addition and subtraction, and parentheses first.
Depth: normal
Weight: 2
Forms: Resol primer els parèntesis; després les multiplicacions i divisions d'esquerra a dreta; després les sumes i restes d'esquerra a dreta; escriu el resultat intermedi a cada pas.
Tags: #order_of_operations, #calculation, #procedure, jerarquia, parèntesis, multiplicació, suma, resta, ordre
Signals: combinada, parèntesis, primer, després, jerarquia, operacions, expressió
Bank: combined_ops
Check:
- Compute: 4 + 3 × 5 → 19
- Compute: (7 + 5) × 4 - 9 → 39
- Compute: 6 × (9 - 4) + 12 → 42

### m5.distributive — Distributiva amb nombres (desplegar per calcular) [extra]
Can do: Break a multiplication over a sum or difference into two easy multiplications and add or subtract the results.
Depth: normal
Weight: 2
Forms: Trenca el nombre del parèntesi en dos de més fàcils; el nombre de fora multiplica absolutament tots dos termes; calcula les dues multiplicacions i suma (o resta) els productes.
Tags: #procedure, #calculation, #facts, distributiva, desplegar, parèntesi, producte parcial, terme
Signals: distributiva, desplega, parèntesi, multiplica per a dins, trenca, calcular
Bank: props_distributive_numeric
Check:
- Steps: 3 × (20 + 4) → 3 × 20 + 3 × 4 ; 60 + 12 ; 72
- Steps: 5 × (30 - 2) → 5 × 30 - 5 × 2 ; 150 - 10 ; 140
- Steps: 7 × (10 + 6) → 7 × 10 + 7 × 6 ; 70 + 42 ; 112

## Fraccions i decimals

### m5.frac_same_den — Suma i resta de fraccions amb el mateix denominador [core]
Can do: Add or subtract fractions with the same denominator, and simplify the result when it can be reduced.
Depth: normal
Weight: 2
Forms: Els denominadors ja són iguals: el denominador no canvia; suma o resta els numeradors; si el resultat es pot simplificar, divideix numerador i denominador pel mateix nombre; si és més gran que 1, escriu-lo com a nombre mixt.
Tags: #calculation, #simplification, #procedure, fraccions, mateix denominador, numerador, simplificar, nombre mixt
Signals: fracció, numerador, denominador, suma, resta, simplifica, mateix, parts
Bank: frac_same_den
Check:
- Compute: 3/8 + 2/8 → 5/8
- Compute: 1/9 + 7/9 → 8/9
- Compute: 7/8 - 3/8 → 4/8

### m5.frac_of_quantity — Fracció d'una quantitat [core]
Can do: Find a fraction of a quantity, dividing it into equal parts and taking the number of parts the numerator says.
Depth: normal
Weight: 2
Forms: Divideix la quantitat en tantes parts iguals com diu el denominador; agafa tantes parts com diu el numerador (multiplica el resultat de la divisió pel numerador).
Tags: #procedure, #calculation, #wrong_operation, fracció, parts iguals, numerador, denominador, de
Signals: fracció, de, parts, repartir, numerador, denominador, quina part, quant és
Bank: frac_of_quantity
Check:
- Compute: Quant és 3/4 de 120? → 90
- Compute: Quant és 2/5 de 45? → 18
- Compute: Quant és 5/6 de 36? → 30

### m5.dec_ops — Sumes, restes i multiplicacions amb decimals [core]
Can do: Add and subtract decimals up to thousandths, and multiply a decimal by a whole number, keeping the comma aligned.
Depth: normal
Weight: 2
Forms: Alinea les comes (mateixa columna, completa amb zeros); suma o resta com amb enters, de dreta a esquerra amb transport o préstec; per multiplicar un decimal per un enter, multiplica sense mirar la coma i després separa tantes xifres decimals com en té el decimal.
Tags: #place_value, #calculation, #carrying, decimals, coma decimal, mil·lèsimes, transport, alinear
Signals: decimals, coma, suma, resta, multiplica, mil·lèsimes, alinear, euros, mesura
Bank: dec_ops
Check:
- Compute: 1,235 + 0,487 → 1,722
- Compute: 4,5 - 1,275 → 3,225
- Compute: 2,35 × 4 → 9,4

### m5.percent_basic — Percentatges bàsics (10, 25, 50 i 75 %) [extra]
Can do: Find 10, 25, 50 or 75 per cent of a quantity.
Depth: normal
Weight: 1
Forms: Recorda que el tant per cent és una fracció de 100; calcula la fracció d'una quantitat (el 25 % és un quart, el 50 % la meitat, el 75 % tres quarts, el 10 % la desena part).
Tags: #calculation, #facts, #procedure, percentatge, per cent, cent, meitat, quart, desena
Signals: per cent, %, percentatge, de cada cent, rebaixa, descompte
Bank: percent_basic
Check:
- Compute: Quant és el 25 % de 80? → 20
- Compute: Quant és el 75 % de 60? → 45
- Compute: Quant és el 10 % de 340? → 34

## Mesura

### m5.smd_convert — Conversions de longitud, massa i capacitat [core]
Can do: Convert between units of length (km, m, cm, mm), mass (kg, g) and capacity (l, ml) and write the answer with its unit.
Depth: normal
Weight: 2
Forms: Recorda la relació entre les unitats (1 km = 1000 m, 1 m = 100 cm, 1 cm = 10 mm, 1 kg = 1000 g, 1 l = 1000 ml); si passes a una unitat més petita multiplica; si passes a una més gran divideix; escriu la unitat de la resposta.
Tags: #unit, #procedure, #calculation, conversió, unitat, quilòmetre, metre, centímetre, quilogram, litre, multiplicar, dividir
Signals: quants metres, quants centímetres, quants grams, quants litres, converteix, equivalent, unitats
Bank: smd_convert
Check:
- Compute: Quants metres són 3,5 km? → 3500 m
- Compute: Quants centímetres són 2,5 m? → 250 cm
- Compute: Quants metres són 245 cm? → 2,45 m

### m5.time_intervals — Durada entre dues hores [extra]
Can do: Work out how many minutes pass between a start time and an end time on the same day.
Depth: normal
Weight: 2
Forms: Calcula quants minuts hi ha fins a cada hora (cada hora són 60 minuts); resta el primer del segon; o compta els minuts fins a l'hora en punt i després els que falten.
Tags: #unit, #calculation, #procedure, hora, minut, durada, trajecte, hora en punt
Signals: surt, arriba, durada, dura, minuts, hora, quarts, comença, acaba
Bank: time_intervals
Check:
- Compute: Un autobús surt a les 9:45 i arriba a les 11:20. Quants minuts dura el trajecte? → 95 min
- Compute: Una classe comença a les 16:10 i acaba a les 17:05. Quants minuts dura? → 55 min
- Compute: Un tren surt a les 8:30 i arriba a les 10:15. Quants minuts dura el viatge? → 105 min

## Geometria

### m5.area_perimeter — Àrea i perímetre de figures planes [core]
Can do: Work out the area of rectangles, squares and triangles, and the perimeter of polygons, with the right unit.
Depth: normal
Weight: 2
Forms: Àrea del rectangle: base × alçada; del triangle: base × alçada ÷ 2; perímetre: suma de tots els costats (al rectangle, 2 × (base + alçada)). Escriu l'àrea en cm² i el perímetre en cm.
Tags: #unit, #wrong_operation, #calculation, àrea, perímetre, rectangle, quadrat, triangle, costat, base, alçada
Signals: àrea, perímetre, rectangle, quadrat, triangle, costat, base, alçada, quants centímetres
Bank: area_perimeter
Check:
- Compute: Un rectangle té 8 cm de base i 5 cm d'alçada. Quina és la seva àrea? → 40 cm²
- Compute: Quin és el perímetre d'un rectangle de 8 cm de base i 5 cm d'alçada? → 26 cm
- Compute: Un quadrat té 7 cm de costat. Quin és el seu perímetre? → 28 cm

## Estadística i probabilitat

### m5.mean_mode_range — Mitjana, moda i rang [extra]
Can do: Find the mean (a whole number here), the mode and the range of a short list of data.
Depth: normal
Weight: 2
Forms: Mitjana: suma totes les dades i divideix pel nombre de dades. Moda: el valor que més es repeteix. Rang: el valor més gran menys el més petit.
Tags: #procedure, #misread, #calculation, mitjana, moda, rang, dades, suma, dividir, més gran, més petit
Signals: mitjana, moda, rang, dades, més gran, més petit, es repeteix, sumes
Bank: mean_mode_range
Check:
- Compute: Quina és la mitjana de les dades 4, 8, 6 i 2? → 5
- Compute: Quin és el rang de les dades 3, 9, 14, 6 i 1? → 13
- Compute: Quina és la moda de les dades 2, 5, 5, 7, 5 i 9? → 5

### m5.probability — Probabilitat simple (casos favorables entre possibles) [extra]
Can do: Write the probability of an event as a fraction: favourable outcomes over all possible outcomes.
Depth: normal
Weight: 2
Forms: Compta els casos favorables (els que compleixen el que es demana) i els casos possibles (tots); escriu la fracció favorables / possibles; simplifica si es pot.
Tags: #misread, #simplification, #procedure, probabilitat, casos favorables, casos possibles, fracció, a l'atzar
Signals: probabilitat, a l'atzar, sense mirar, favorable, possible, bossa, treure, fracció
Bank: probability_simple
Check:
- Compute: Una bossa té 3 boles vermelles i 5 de blaves. Quina és la probabilitat de treure una vermella? → 3/8
- Compute: Una bossa té 1 bola vermella i 3 de blaves. Quina és la probabilitat de treure una vermella? → 1/4
- Compute: Una bossa té 5 boles vermelles i 3 de blaves. Quina és la probabilitat de treure una vermella? → 5/8

## Àlgebra i problemes

### m5.equations_simple — Equacions de primer grau (a·x + b = c) [extra]
Can do: Solve a first-degree equation of the form a·x + b = c with a whole-number solution.
Depth: normal
Weight: 2
Forms: Treu el mateix nombre als dos costats per deixar el terme amb x sol (a·x = c − b); divideix els dos costats pel coeficient de x; comprova el resultat substituint-lo.
Tags: #procedure, #sign, #calculation, equació, incògnita, coeficient, resta, divisió, comprovar
Signals: equació, incògnita, x, val, resol, quant val, treu, divideix
Bank: equations_simple
Check:
- Compute: Quant val x en l'equació 3x + 5 = 20? → 5
- Compute: Quant val x en l'equació 2x + 7 = 31? → 12
- Compute: Quant val x en l'equació 4x + 9 = 41? → 8

### m5.word_problems — Problemes de 2-3 passos (triar i resoldre) [core]
Can do: Read a short story problem of two or three operations, decide the operation sequence, and carry it out to the result (or choose the operation).
Depth: normal
Weight: 3
Forms: Llegeix l'enunciat i busca les pistes de cada operació («cada un» = multiplicar, «en paga» = restar, «igualment entre» = dividir, «en perden» = restar, «en total» = sumar); escriu l'expressió amb els números del problema en l'ordre en què es fan les operacions; calcula el resultat.
Tags: #misread, #wrong_operation, #procedure, #calculation, problema, passos, operació, expressió, repartir, en total
Signals: problema, compra, paga, torna, reparteix, cada un, en total, perden, queden, quants, quantes
Bank: word_problems_multistep
Check:
- Compute: La Marta compra 3 quaderns a 2 € cada un i 2 llibres a 5 € cada un. Paga amb un bitllet de 50 €. Quants euros li tornen? → 34
- Compute: Hi ha 4 caixes amb 6 cromos a cada caixa. Se'n treuen 7 per regalar. Quants cromos en queden? → 17
- Compute: En Pere té 12 gominoles i el seu germà en té 9. Entre els dos en perden 5. Quantes gominoles els queden? → 16
