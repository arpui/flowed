# Encàrrec E2 — Go: currículum m5 i banc d'exercicis

Disseny: `docs/DISSENY-M5.md` §2.3 (llegir-lo). Decisions tancades.

## 1. Abast

Fitxers: `curriculum/math-m5.md` (nou), `scripts/mathbank.py`, `curriculum/bank/math-m5/` (generat), tests de `tests/` relacionats amb el banc/currículum de math. **No** toquis `server/src/flash.ts`, `web/`, ni `hooks/curriculum.py` (un altre agent hi treballa en paral·lel).

## 2. `curriculum/math-m5.md`

Mateix format que `curriculum/math-m4.md` (capçalera, seccions, `### id — Nom [core]`, `Can do`, `Depth`, `Weight`, `Requires`, `Forms`, `Tags`, `Signals`, `Check:` amb `Compute:` avaluables per `mathgrade`, i `Bank: <família>`). Capçalera: `language: math`, `level: m5`, `status: esborrany`, `pass_mark: 80`, `carry_mark: 65`, `checkpoint_items: 12`, `ready_share: 50`. **Sense `flash_share`** (ho afegirà E4).

Competències (taula de §2.3 del disseny), agrupades en seccions: Càlcul, Fraccions i decimals, Mesura, Geometria, Estadística i probabilitat, Àlgebra i problemes. Les marcades [core] al disseny són `[core]`. Textos en català. `Tags:` amb les categories d'error de `AGENTS.md` (`#calculation`, `#place_value`, `#carrying`, `#order_of_operations`, `#unit`, `#simplification`…).

`python3 hooks/curriculum.py` ha de validar el fitxer sense errors (mira com ho fan els tests existents per a m4/m7: `validate_curriculum`).

## 3. Famílies noves a `scripts/mathbank.py`

Mateix patró que les famílies existents (`mult_2digit`, `frac_add_unlike`, `word_problems`…): funció `(rng) -> dict` registrada a `FAMILIES` (o `STEPS_FAMILIES`), resposta calculada amb `mathgrade.parse_expr`, `why` en català, `validate_item` ha de passar.

| Família | Tipus | Contingut |
|---|---|---|
| `mult_3digit` | compute | 3 xifres × 2 xifres i 3 × 3. |
| `div_2digit` | compute | Dividend de 3-4 xifres entre divisor de 2 xifres; resposta "quocient" (enunciat clar: "quocient sencer" o divisió exacta — tria'n una i sigues coherent amb `mathgrade`). |
| `combined_ops` | compute | Jerarquia i parèntesis, 3-4 operands, resultat enter ≥ 0. |
| `frac_same_den` | compute | Suma/resta de fraccions amb el mateix denominador; `also_accept` amb la forma simplificada. |
| `frac_of_quantity` | compute | "3/4 de 120". |
| `dec_ops` | compute | Suma/resta fins a mil·lèsimes; decimal × enter. |
| `percent_basic` | compute | 10/25/50/75 % d'una quantitat. |
| `smd_convert` | compute | Conversions de longitud, massa i capacitat; resposta amb unitat (mira com `mathgrade` tracta les unitats). |
| `time_intervals` | compute | Enunciat d'hora d'inici i fi → durada en minuts (o h i min, coherent amb el corrector). |
| `area_perimeter` | compute | Rectangle, quadrat, triangle (àrea), perímetre de polígons; unitat cm/cm². |
| `mean_mode_range` | compute | Mitjana entera, moda, rang d'una llista curta. |
| `probability_simple` | compute | Fracció casos favorables / possibles; `also_accept` simplificada. |
| `equations_simple` | compute | `a·x + b = c`, solució entera. |
| `word_problems_multistep` | compute + choose | Problemes de 2-3 passos (mateixa estructura que `word_problems`, amb `expression`). |

Steps: amplia `partial_products` per acceptar 3 xifres i `long_division` per a divisor de 2 xifres **sense canviar els ítems ja generats de m4** (paràmetre o família nova `partial_products_3`, `long_division_2`).

## 4. Generar el banc

Amb el CLI de `mathbank.py` (llegeix-ne l'ús), llavor fixa, ~12 ítems per competència a `curriculum/bank/math-m5/` (i `steps/` per a les de passos). Han de passar la validació del generador.

## 5. Tests

- Tests de les famílies noves (en l'estil de `tests/test_mathbank.py`): determinisme, `validate_item`, resposta correcta segons `mathgrade`.
- `math-m5.md` vàlid; cada `Bank:` existeix a `FAMILIES`.
- Ítems de m4/m7 ja generats **idèntics** (regenerar amb la mateixa llavor no canvia res).
- `python3 -m unittest discover -s tests` sencer. L'única fallada esperada és la del harness `flash.test.ts` per les 4 llistes buides d'anglès.

## 6. Acceptació

- [ ] `curriculum/math-m5.md` vàlid amb totes les competències del disseny.
- [ ] 14 famílies noves + steps per a 3 xifres i divisor de 2 xifres.
- [ ] Banc de m5 generat i validat.
- [ ] m4/m7 sense canvis. Tests en verd (llevat de l'esperada).
