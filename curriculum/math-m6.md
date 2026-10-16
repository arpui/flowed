---
language: math
level: m6
version: 1
status: esborrany
pass_mark: 80
carry_mark: 65
checkpoint_items: 12
ready_share: 50
flash_share: 60
---

# Math m6 — currículum (esborrany)

> Competències de 6è de primària segons el disseny `docs/DISSENY-M7-M6.md` §2 (Go: el
> banc d'exercicis). Els exercicis que es poden respondre de cap en pocs segons (fets,
> taules, equivalències) van pel canal Flash (`curriculum/flash/`, encàrrec E9); aquí
> hi ha les competències amb procediment, càlcul llarg i problemes de context.
>
> Format: el mateix que `math-m5.md` (`### id — Nom [core]`, `Can do`, `Depth`,
> `Weight`, `Requires`, `Forms`, `Tags`, `Signals`, `Bank`, `Check:`). `Check:` fa
> servir `Compute:` (valor o resultat amb unitat, avaluable per `hooks/mathgrade.py`).
>
> **Clau `Bank:`**: la família de `scripts/mathbank.py` que genera el banc de la
> competència. Les competències sense `Bank:` (p. ex. `m6.coordinates`) només tenen
> Flash.
>
> `flash_share: 60` (capçalera): cal tancar el 60 % de les llistes Flash de m6 per obrir el test de nivell.

---

## Sentit numèric i càlcul

### m6.powers_roots — Potències i arrels exactes [core]
Can do: Compute a power with a whole exponent, a product of powers, and the exact square or cube root of a perfect power.
Depth: normal
Weight: 2
Forms: Una potència és un producte de factors iguals: b^e vol dir b · b · … (e vegades). Un negatiu elevat a un exponent parell dóna positiu, i a un senar, negatiu. Per a un producte de potències, calcula cada potència i després multiplica. Arrel exacta: descompon el nombre en factors primers; l'arrel quadrada agafa cada factor que es repeteix dues vegades una sola vegada, i la cúbica, cada factor que es repeteix tres vegades.
Tags: #calculation, #procedure, #facts, #sign, potència, base, exponent, arrel exacta, factors primers, quadrat, cub
Signals: potència, exponent, base, elevat a, al quadrat, al cub, arrel, quadrada, cúbica, exacta
Bank: powers_value
Check:
- Compute: Quant és 2^5? → 32
- Compute: Quant és (-3)^3? → -27
- Compute: Quina és l'arrel quadrada exacta de 144? → 12

### m6.integers — Enters: temperatures, ascensors i deutes [core]
Can do: Add and subtract integers in a context (temperatures, a lift below ground, a debt), reading the sign of each number.
Depth: normal
Weight: 2
Forms: Pujar una temperatura, ingressar o pujar de planta és sumar; baixar la temperatura o gastar és restar. Un nombre negatiu és per sota de zero: el soterrani, un deute, un saldo negatiu. Escriu l'operació amb el signe de cada nombre i calcula d'esquerra a dreta; sobre la recta numèrica, sumar és anar a la dreta i restar és anar a l'esquerra.
Tags: #sign, #calculation, #misread, #procedure, enters, negatiu, recta numèrica, temperatura, deute, soterrani, sumar, restar
Signals: temperatura, graus, sota zero, soterrani, planta, ascensor, deute, saldo, puja, baixa, negatiu
Bank: integers_context
Check:
- Compute: A les 6 del matí hi ha -4 graus. Al migdia la temperatura puja 9 graus. Quina temperatura hi ha al migdia? → 5
- Compute: Un ascensor és a la planta -2 i puja 7 plantes. En quina planta és? → 5
- Compute: Un compte té un saldo de -15 €. S'ingressen 20 €. Quin és el saldo ara? → 5

### m6.gcd_lcm — MCD i mcm en problemes [core]
Can do: Find the greatest common divisor or the least common multiple of two numbers to solve a problem about equal pieces, or about two things that coincide.
Depth: normal
Weight: 2
Forms: MCD: el tros més llarg que cap exactament en totes dues longituds; són els factors comuns amb el menor exponent. mcm: el primer moment en què coincideixen dos cicles; són tots els factors amb el major exponent. Descompon cada nombre en factors primers i aplica la regla.
Tags: #procedure, #facts, #wrong_operation, MCD, mcm, factors primers, divisor, múltiple, coincidir, tros
Signals: MCD, mcm, divisor, múltiple, coincideixen, talls, iguals, cada, tros, el més gran
Bank: gcd_lcm_problems
Check:
- Compute: Quin és el MCD de 24 i 36? → 12
- Compute: Quin és el mcm de 4 i 6? → 12
- Compute: Dos autobusos passen cada 10 i cada 15 minuts. Al cap de quants minuts coincideixen? → 30

### m6.fraction_ops — Fraccions: sumar, restar, multiplicar i dividir [core]
Can do: Add, subtract, multiply and divide fractions with different denominators, and write the result in its simplest form.
Depth: normal
Weight: 2
Requires: m6.gcd_lcm
Forms: Sumar i restar: primer un denominador comú (el mcm dels denominadors); després sumes o restes els numeradors. Multiplicar: multipliques els numeradors entre ells i els denominadors entre ells. Dividir: multipliques per la inversa de la segona fracció. Simplifica dividint numerador i denominador pel mateix nombre.
Tags: #calculation, #simplification, #procedure, #wrong_operation, fracció, denominador comú, numerador, inversa, simplificar, multiplicar, dividir
Signals: fracció, numerador, denominador, suma, resta, multiplica, divideix, inversa, simplifica
Bank: frac_ops4
Check:
- Compute: Quant és 1/2 + 1/3? → 5/6
- Compute: Quant és 3/4 × 2/5? → 3/10
- Compute: Quant és 3/8 ÷ 1/2? → 3/4

### m6.decimal_division — Divisió de decimals [core]
Can do: Divide a decimal by a whole number or by a decimal number, with an exact quotient, and put the decimal comma in the right place.
Depth: normal
Weight: 2
Forms: Dividir un decimal per un enter: divideix com amb enters i posa la coma al quocient just quan baixes la primera xifra decimal del dividend. Dividir per un decimal: multiplica el dividend i el divisor per 10 (o per 100) fins que el divisor sigui un enter; després divideix com abans.
Tags: #place_value, #calculation, #procedure, decimal, coma decimal, divisió, quocient, divisor, dividend, zeros
Signals: decimal, coma, divideix, quocient, divisor, dividend, exacta, repartir
Bank: dec_division
Check:
- Compute: Quant és 4,8 ÷ 6? → 0,8
- Compute: Quant és 3,6 ÷ 0,4? → 9
- Compute: Quant és 7,5 ÷ 2,5? → 3

## Proporcionalitat i àlgebra

### m6.percent_change — Augments, descomptes i regla de tres [core]
Can do: Work out the price after an increase or a discount, and solve a direct rule of three.
Depth: normal
Weight: 2
Requires: m6.decimal_division
Forms: Un augment del p % es calcula amb el factor 1 + p/100 (pujar un 15 % és multiplicar per 1,15); un descompte, amb el factor 1 − p/100 (baixar un 20 % és multiplicar per 0,8). Regla de tres directa: si la quantitat és més gran, el preu també ho és; el preu d'un de la mateixa mida es calcula amb (preu × quantitat) ÷ quantitat inicial.
Tags: #calculation, #procedure, #wrong_operation, percentatge, augment, descompte, factor, regla de tres, directa, preu
Signals: per cent, %, puja, baixa, descompte, rebaixa, regla de tres, preu, directa, cada
Bank: percent_change
Check:
- Compute: Un article val 40 €. Puja un 15 %. Quin és el preu nou? → 46
- Compute: Un article val 60 €. Té un descompte del 20 %. Quin és el preu final? → 48
- Compute: 4 kg de pomes costen 6 €. Quant costen 10 kg de les mateixes pomes? → 15

### m6.scales — Escales: mapes i plànols [extra]
Can do: Use a scale 1:n to turn a distance on a map into a real one, and back, in metres and centimetres.
Depth: normal
Weight: 2
Forms: L'escala 1:n vol dir que 1 unitat del mapa són n unitats de la realitat. Del mapa a la realitat: multiplica per n i passa a la unitat demanada (1 m = 100 cm). De la realitat al mapa: passa la mesura real a centímetres i divideix per n.
Tags: #unit, #calculation, #procedure, escala, plànol, mapa, distància, realitat, conversió, multiplicar, dividir
Signals: escala, plànol, mapa, distància real, centímetres, metres, quilòmetres, a escala
Bank: scales
Check:
- Compute: En un plànol a escala 1:200, una taula mesura 4 cm. Quants metres mesura de veritat? → 8 m
- Compute: En un mapa a escala 1:1000, quants centímetres separen dos punts que estan a 35 m de distància real? → 3,5 cm
- Compute: Dues ciutats estan a 3 km. En un mapa a escala 1:100000, quants centímetres les separen? → 3 cm

### m6.equations_intro — Introducció a les equacions [extra]
Can do: Solve a first-degree equation of the form a·x + b = c with a whole-number solution.
Depth: normal
Weight: 2
Forms: Treu el mateix nombre als dos costats per deixar el terme amb x sol (a·x = c − b); divideix els dos costats pel coeficient de x; comprova el resultat substituint-lo a l'equació.
Tags: #procedure, #sign, #calculation, equació, incògnita, coeficient, resta, divisió, comprovar
Signals: equació, incògnita, x, quant val, resol, treu, divideix
Bank: equations_simple
Check:
- Compute: Quant val x en l'equació 3x + 4 = 19? → 5
- Compute: Quant val x en l'equació 2x + 9 = 25? → 8
- Compute: Quant val x en l'equació 5x + 6 = 31? → 5

## Mesura

### m6.area_units — Unitats de superfície [extra]
Can do: Convert areas between km², m², dm², cm² and mm², and between hectares or ares and m².
Depth: normal
Weight: 2
Requires: m6.decimal_division
Forms: Cada unitat de superfície és 100 vegades més petita que la de l'esquerra (1 m² = 100 dm², 1 dm² = 100 cm²); 1 km² = 1 000 000 m². Per passar a una unitat més petita multiplica; per passar a una més gran divideix. Equivalències: 1 ha = 10 000 m² i 1 a = 100 m².
Tags: #unit, #calculation, #procedure, superfície, km², m², dm², cm², mm², hectàrea, àrea, conversió, multiplicar, dividir
Signals: superfície, quadrat, km², m², cm², hectàrea, ha, àrea, metres quadrats
Bank: area_units
Check:
- Compute: Quants m² són 3 km²? → 3000000 m²
- Compute: Quants cm² són 2 dm²? → 200 cm²
- Compute: Quants m² són 2 ha? → 20000 m²

### m6.volume_capacity — Volum i capacitat [extra]
Can do: Convert volumes and capacities between m³, dm³, cm³, litres and millilitres.
Depth: normal
Weight: 2
Requires: m6.decimal_division
Forms: 1 m³ = 1000 dm³ = 1000 l; 1 dm³ = 1 l = 1000 cm³; 1 l = 1000 ml. Cada unitat és 1000 vegades més petita que la de l'esquerra: per passar a una més petita multiplica per 1000, i per passar a una més gran divideix.
Tags: #unit, #calculation, #procedure, volum, capacitat, litre, mil·lilitre, m³, dm³, cm³, conversió
Signals: volum, capacitat, litres, mil·lilitres, cm³, dm³, m³, quants litres, quants ml, cabre
Bank: volume_units
Check:
- Compute: Quants litres són 2,5 m³? → 2500 l
- Compute: Quants cm³ són 3 dm³? → 3000 cm³
- Compute: Quants litres són 750 ml? → 0,75 l

### m6.angles_sexagesimal — Hores, minuts i graus: operacions [extra]
Can do: Add and subtract durations and angles given in hours (or degrees) and minutes, and give the result in minutes.
Depth: normal
Weight: 1
Forms: Passa cada quantitat a minuts (1 hora o 1 grau = 60 minuts): 2 h 5 min són 2 · 60 + 5 = 125 min. Després suma o resta els minuts totals. Si cal, torna-ho a hores i minuts: 60 minuts fan una hora, o un grau.
Tags: #unit, #calculation, #procedure, hores, minuts, graus, angle, sexagesimal, suma, conversió
Signals: hores, minuts, graus, angle, durada, suma, sumen, dura, quants minuts
Bank: sexagesimal_ops_easy
Check:
- Compute: Una classe dura 1 h 25 min i una altra 2 h 10 min. Quants minuts duren les dues? → 215 min
- Compute: Un angle mesura 30 graus i 40 minuts, i un altre 12 graus i 35 minuts. Quants minuts sumen els dos angles? → 2595 min
- Compute: Quants minuts són 3 hores i 15 minuts? → 195 min

## Geometria

### m6.areas_polygons — Àrees de polígons regulars, rombes i trapezis [core]
Can do: Work out the area of a regular polygon from its apothem, of a rhombus from its diagonals and of a trapezium from its bases and height, with the right unit.
Depth: normal
Weight: 2
Requires: m6.decimal_division
Forms: Polígon regular: àrea = perímetre × apotema ÷ 2 (el perímetre és la suma dels costats, tots iguals). Rombe: diagonal major × diagonal menor ÷ 2. Trapezi: (base gran + base petita) × altura ÷ 2. Escriu l'àrea en cm².
Tags: #unit, #wrong_operation, #calculation, #procedure, polígon regular, apotema, rombe, trapezi, diagonal, base, altura, àrea
Signals: polígon, apotema, rombe, diagonal, trapezi, base, altura, àrea, regular, costats
Bank: areas_polygons
Check:
- Compute: Un hexàgon regular té costats de 4 cm i l'apotema de 3,5 cm. Quina és la seva àrea? → 42 cm²
- Compute: Un rombe té les diagonals de 10 cm i 6 cm. Quina és la seva àrea? → 30 cm²
- Compute: Un trapezi té les bases de 8 cm i 4 cm i l'altura de 5 cm. Quina és la seva àrea? → 30 cm²

### m6.circle — Circumferència i àrea del cercle (π = 3,14) [core]
Can do: Work out the circumference and the area of a circle from its radius or diameter, with π = 3,14.
Depth: normal
Weight: 2
Requires: m6.decimal_division
Forms: Circumferència = 2 × π × radi, o π × diàmetre. Àrea = π × radi × radi (el radi al quadrat). Usa π = 3,14 i escriu el resultat amb la unitat (cm per a la longitud, cm² per a l'àrea).
Tags: #calculation, #procedure, #unit, cercle, circumferència, radi, diàmetre, àrea, π, quadrat
Signals: cercle, circumferència, radi, diàmetre, àrea, π, rodona, longitud
Bank: circle_measures
Check:
- Compute: Un cercle té un radi de 5 cm. Quina és la longitud de la circumferència (π = 3,14)? → 31,4 cm
- Compute: Un cercle té un radi de 10 cm. Quina és la seva àrea (π = 3,14)? → 314 cm²
- Compute: Un cercle té un diàmetre de 8 cm. Quina és la longitud de la circumferència (π = 3,14)? → 25,12 cm

### m6.volumes — Volum de prismes i cilindres (π = 3,14) [extra]
Can do: Work out the volume of a cuboid, of a cylinder and of a prism with a triangular base, with the right unit.
Depth: normal
Weight: 2
Requires: m6.areas_polygons
Forms: El volum d'un prisma és l'àrea de la base per l'altura (o la llargada). Prisma rectangular: a × b × c. Cilindre: π × radi × radi × altura. Prisma de base triangular: (base × altura ÷ 2) × llargada. Escriu el volum en cm³.
Tags: #unit, #calculation, #procedure, volum, prisma, cilindre, base, altura, π, cm³
Signals: volum, prisma, cilindre, base, altura, aresta, llargada, cabre, cm³
Bank: volumes_solids
Check:
- Compute: Un prisma rectangular té les arestes de 4 cm, 5 cm i 6 cm. Quin és el seu volum? → 120 cm³
- Compute: Un cilindre té un radi de la base de 2 cm i una altura de 10 cm (π = 3,14). Quin és el seu volum? → 125,6 cm³
- Compute: Un prisma té una base triangular de 6 cm de base i 4 cm d'altura, i una llargada de 5 cm. Quin és el seu volum? → 60 cm³

### m6.coordinates — Coordenades als quatre quadrants [extra]
Can do: Read the coordinates of a point on the grid, and work out the reflection of a point across an axis.
Depth: light
Weight: 1
Forms: Un punt es llegeix (x, y): primer la x (horitzontal) i després la y (vertical). Quadrant I: x i y positius; II: x negatiu i y positiu; III: els dos negatius; IV: x positiu i y negatiu. El simètric respecte de l'eix y canvia el signe de la x; respecte de l'eix x, canvia el signe de la y.
Tags: #misread, #sign, #facts, coordenades, quadrant, eix, punt, horitzontal, vertical, negatiu, simètric
Signals: coordenades, quadrant, eix, punt, horitzontal, vertical, negatiu, positiu, simètric
Check:
- Compute: Quina és la coordenada x del simètric del punt (3, -2) respecte de l'eix y? → -3
- Compute: Quina és la coordenada y del simètric del punt (-4, 5) respecte de l'eix x? → -5
- Compute: Quina és la suma de les coordenades del punt (-2, 6)? → 4

## Estadística i probabilitat

### m6.statistics — Freqüències, mitjana, mediana, moda i rang [extra]
Can do: Read a frequency table or a short list of data and find the weighted mean, the median, the mode and the range.
Depth: normal
Weight: 2
Forms: Mitjana ponderada: multiplica cada valor per la seva freqüència, suma-ho tot i divideix pel total de dades. Mediana: ordena les dades; és el valor del mig (o la mitjana dels dos del mig si el nombre de dades és parell). Moda: el valor que més es repeteix. Rang: el més gran menys el més petit.
Tags: #calculation, #procedure, #misread, estadística, mitjana, mediana, moda, rang, freqüència, ordenar
Signals: mitjana, mediana, moda, rang, freqüència, dades, ordena, taula
Bank: stats_tables
Check:
- Compute: Les notes són 4, 9, 6, 7 i 5. Quina és la mediana? → 6
- Compute: Les temperatures són 12, 17, 9 i 15 graus. Quin és el rang? → 8
- Compute: 3 alumnes han tret un 6 i 1 alumne un 10. Quina és la nota mitjana? → 7

### m6.probability — Probabilitat simple [extra]
Can do: Write the probability of an event as a fraction: favourable cases over all possible cases, and simplify it.
Depth: normal
Weight: 2
Forms: Compta els casos favorables (els que compleixen el que es demana) i els casos possibles (tots); escriu la fracció favorables / possibles i simplifica-la si es pot.
Tags: #misread, #simplification, #procedure, probabilitat, casos favorables, casos possibles, fracció, a l'atzar
Signals: probabilitat, a l'atzar, favorable, possible, bossa, treure, fracció
Bank: probability_simple
Check:
- Compute: Una bossa té 2 boles vermelles i 6 de blaves. Quina és la probabilitat de treure una vermella? → 1/4
- Compute: Una bossa té 4 boles vermelles i 4 de blaves. Quina és la probabilitat de treure una vermella? → 1/2
- Compute: Una bossa té 3 boles vermelles i 9 de blaves. Quina és la probabilitat de treure una vermella? → 1/4
