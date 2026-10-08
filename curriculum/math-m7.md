---
language: math
level: m7
version: 1
status: pilot
pass_mark: 80
carry_mark: 65
checkpoint_items: 12
ready_share: 50
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
