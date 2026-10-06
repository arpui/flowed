---
language: math
level: m4
version: 1
status: esborrany-pilot
pass_mark: 80
carry_mark: 65
checkpoint_items: 12
ready_share: 50
---

# Math m4 — currículum (PILOT)

> ⚠️ **Contingut de prova, no definitiu.** Aquest fitxer és un *placeholder* funcional
> per al pilot de la Fase 1 (WP1.5): serveix perquè el generador de banc
> (`scripts/mathbank.py`), `hooks/bank.py` i el servidor tinguin on apuntar mentre
> l'Albert autoreja el currículum real de m4 (WP1.1). Les competències, els ids i els
> `Bank:` d'aquí poden canviar sense avís quan arribi el currículum autèntic.
>
> Format: el mateix que `en-A1.md` / `en-A2.md` (`### id — Nom [core]`, `Can do`,
> `Depth`, `Weight`, `Requires`, `Forms`, `Tags`, `Signals`, `Check:`), amb les
> adaptacions matemàtiques de `docs/DISSENY-MATEMATIQUES.md` §4.6: `Forms:` descriu el
> procediment, `Tags:` són categories d'error matemàtic (`#carrying`, `#simplification`…)
> i `Check:` fa servir `Compute:` (tancat, avaluable per `hooks/mathgrade.py`).
>
> **Clau `Bank:`** (convenció proposta per a WP1.5): cada competència declara la família
> de plantilles del generador amb una línia `Bank: <família>` (p. ex. `Bank: mult_2digit`).
> `scripts/mathbank.py` la llegeix directament del `.md`; `hooks/curriculum.py` l'ignora
> (clau desconeguda). Una competència sense `Bank:` no té banc generable.
>
> **WP1.1 (2026-10-06):** les tres competències pilot que el banc ja tenia generades i
> validades però que el currículum no declarava — `m4.add_carry`, `m4.div_2x1` (steps,
> renumerats `.001–.012` a WP2.1) i `m4.word_problems` (compute/choose, els primers
> ítems `choose` del banc) — queden declarades aquí amb les seves línies `Bank:`.
> Fins ara Go/lliçó no les servien perquè no eren al `.md` (forat registrat); els ítems
> `.031–.042` de `mult_2digit` i `frac_add_unlike` pertanyen a les competències
> existents (compute + steps del mateix id).

---

## Càlcul

### m4.mult_2digit — Multiplicacions de 2 xifres [core]
Can do: Multiply two 2-digit numbers exactly, with and without carrying.
Depth: normal
Weight: 3
Forms: Descompon el segon factor en desenes i unitats; multiplica cada producte parcial (unitats × unitats, unitats × desenes, desenes × unitats, desenes × desenes); suma els productes parcials alineats per valor posicional, transportant quan una xifra passa de 9.
Tags: #carrying, #place_value, #facts, multiplicació, producte parcial, transport, desenes, unitats
Signals: multiplica, multiplicació, vegades, producte, factor, xifres, desenes, unitats, transport
Bank: mult_2digit
Check:
- Compute: 24 × 3 → 72
- Compute: 27 × 14 → 378
- Compute: 35 × 26 → 910

### m4.dec_add — Suma de decimals (una xifra) [core]
Can do: Add decimals with one decimal place, keeping the comma aligned.
Depth: normal
Weight: 2
Forms: Alinea les comes decimals; suma com amb enters, de dreta a esquerra amb transport; l'comma de la resposta va a la mateixa posició que als sumands.
Tags: #place_value, #carrying, #calculation, decimals, coma decimal, suma, transport
Signals: suma, sumar, decimals, coma, anar, portar, cèntims, euros, mesura
Bank: dec_add
Check:
- Compute: 3,5 + 2,4 → 5,9
- Compute: 23,8 + 7,6 → 31,4
- Compute: 48,9 + 25,5 → 74,4

### m4.add_carry — Suma amb transport (descomposició) [core]
Can do: Add two 2-digit numbers with carrying by splitting each into tens and units, adding the columns, and combining.
Depth: normal
Weight: 2
Forms: Separa cada sumand en desenes i unitats (27 = 20 + 7); suma les desenes entre elles; suma les unitats — si passen de 9 hi ha transport; ajunta els dos resultats parcials.
Tags: #carrying, #place_value, #calculation, suma, transport, desenes, unitats, arrestando, suma parcial
Signals: suma, sumar, transport, anar, portar, desenes, unitats, total
Bank: partial_sums
Check:
- Steps: 27 + 16 → 20 + 10 ; 7 + 6 ; 30 + 13
- Steps: 35 + 28 → 30 + 20 ; 5 + 8 ; 50 + 13
- Steps: 46 + 27 → 40 + 20 ; 6 + 7 ; 60 + 13

### m4.div_2x1 — Divisió de 2 xifres entre 1 (amb residu) [core]
Can do: Divide a 2-digit number by a 1-digit number with a remainder: the biggest multiple that fits, the subtraction that leaves the remainder, and the result as a mixed number.
Depth: normal
Weight: 2
Requires: m4.mult_2digit
Forms: Busca el múltiple del divisor més gran que no sobrepassi el dividend (5 × 8 = 40 per a 43 ÷ 5); resta'l per veure el residu (43 − 40 = 3); escriu el resultat com a quocient + residu/divisor (8 3/5).
Tags: #facts, #procedure, #calculation, divisió, quocient, residu, múltiple, taula de multiplicar, fracció mixta
Signals: divideix, divisió, quocient, residu, sobra, múltiple, repartir
Bank: long_division
Check:
- Steps: 43 ÷ 5 → 5 × 8 ; 43 - 40 ; 8 3/5
- Steps: 25 ÷ 3 → 3 × 8 ; 25 - 24 ; 8 1/3
- Steps: 47 ÷ 6 → 6 × 7 ; 47 - 42 ; 7 5/6

## Fraccions

### m4.frac_add_unlike — Suma de fraccions amb denominadors diferents [core]
Can do: Add two fractions with different denominators by rewriting them over a common denominator.
Depth: deep
Weight: 3
Requires: m4.mult_2digit
Forms: Busca el denominador comú (el mcm dels dos denominadors); reescriu cada fracció com una equivalent amb aquest denominador (multiplica numerador i denominador per la mateixa xifra); suma els numeradors i deixa el denominador; simplifica si la fracció es pot reduir.
Tags: #procedure, #simplification, #calculation, fraccions, denominador comú, numerador, mcm, equivalent, simplificar
Signals: fracció, fraccions, denominador, numerador, meitat, terç, quart, fifth, equivalent, simplificar, resta, suma
Bank: frac_add_unlike
Check:
- Compute: 1/4 + 3/8 → 5/8
- Compute: 1/2 + 1/3 → 5/6
- Compute: 2/3 + 1/6 → 5/6

### m4.compare_fracs — Comparació de fraccions [core]
Can do: Say which of two fractions is bigger, or if they are equal, using >, < or =.
Depth: normal
Weight: 2
Requires: m4.frac_add_unlike
Forms: Posa les dues fraccions sobre un denominador comú (o compara els productes en creu); la fracció amb el numerador més gran és la més gran; escriu >, < o = entre les dues.
Tags: #procedure, #sign, #calculation, fraccions, comparació, més gran, més petita, igual, producte en creu
Signals: compara, més gran, més petita, igual, fracció, sembla, >, <, =, denominador
Bank: compare_fracs
Check:
- Compute: 3/4 ? 2/3 → >
- Compute: 2/5 ? 3/5 → <
- Compute: 2/3 ? 4/6 → =

## Problemes

### m4.word_problems — Problemes verbals (triar i resoldre l'operació) [core]
Can do: Read a short story problem, decide which operation solves it, and carry it out to the result (or name the operation).
Depth: normal
Weight: 2
Requires: m4.mult_2digit
Forms: Llegeix l'enunciat i busca la pista de l'operació («repartir igualment entre» = divisió, «quants en falten» = resta, «el doble» = multiplicar per 2, «en total» = suma o producte); escriu l'operació amb els números del problema i calcula el resultat.
Tags: #misread, #wrong_operation, #procedure, #calculation, problema verbal, repartir, doble, quants en falten, en total, operació
Signals: problema, reparteix, compra, li tornen, quants, falten, doble, total, part
Bank: word_problems
Check:
- Compute: En Marc reparteix 16 pomes igualment entre 4 amics. Quants en toquen a cada amic? → 4
- Compute: Un àlbum té 30 espais i la Laia ja n'ha omplert 12. Quants espais li falten? → 18
- Compute: Una pizza tallada en 8 parts iguals; en Pere se'n menja 3. Quina part de la pizza queda? → 5/8
