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
