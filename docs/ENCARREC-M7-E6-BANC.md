# Encàrrec E6 — Go: competències noves de m7 i banc

Disseny: `docs/DISSENY-M7-M6.md` §1.1 (llegir-lo). Mateix enfocament que E2 (`docs/ENCARREC-M5-E2-BANC.md`, llegir-lo). Decisions tancades.

## 1. Abast

Fitxers: `curriculum/math-m7.md`, `scripts/mathbank.py`, `curriculum/bank/math-m7/` (només fitxers nous), tests de `tests/` del banc/currículum de math. **No** toquis `server/`, `web/`, `hooks/curriculum.py` ni `curriculum/flash/` (un altre agent hi treballa en paral·lel).

## 2. `curriculum/math-m7.md`

- **Les 9 competències actuals es queden igual** (text, ids, `Bank:`), i els seus ítems de banc han de quedar **idèntics byte a byte**.
- Afegeix les 18 competències noves de la taula §1.1 del disseny, agrupades en seccions noves (Nombres enters i divisibilitat, Fraccions, decimals i potències, Àlgebra, Proporcionalitat i funcions, Geometria, Mesura, Estadística i probabilitat). Mateix format que la resta (`Can do`, `Depth`, `Weight`, `Requires`, `Forms`, `Tags`, `Signals`, `Check:` amb `Compute:` avaluables per `mathgrade`, `Bank:`). `[core]` segons el disseny; la resta `[extra]`.
- `m7.triangle_points` no té família de banc (només Flash): sense línia `Bank:` (mira com es tracta avui una competència sense `Bank:`).
- **No** afegeixis `flash_share` (ho fa E7).
- Ha de validar (`validate_curriculum`).

## 3. Famílies noves a `scripts/mathbank.py`

Una per competència (noms de la columna Go del disseny), mateix patró que E2: resposta calculada amb `mathgrade`, `why` en català, `validate_item` passa. Notes:

- `integers_combined`: negatius, potències, parèntesis i claudàtors; resultat enter.
- `gcd_lcm_problems`: problemes contextualitzats (rajoles, autobusos que coincideixen…); resposta numèrica.
- `frac_combined`: parèntesis i potències; `also_accept` amb la forma simplificada.
- `generatrix`: decimal exacte → fracció irreductible.
- `powers_props`: resposta com a potència (`2^7`) **o** valor; mira si `mathgrade` les fa equivalents i sigues coherent.
- `translate_expr`, `monomials_ops`: respostes algebraiques (`grade_algebraic`, com les famílies de lletres actuals).
- `linear_equations`: amb parèntesis i transposició; solució entera. Steps `linear_eq_steps` (un pas per línia: treure parèntesis, transposar, reduir, aïllar).
- `proportion_problems`: directa, inversa, percentatges encadenats.
- `linear_function`: valor de `y` per a una `x` donada, o `m`/`n` a partir de dos punts.
- `pythagoras`, `polygon_angles`, `composite_areas` (π = 3,14, unitat), `units_derived` (unitat), `sexagesimal_ops` (resposta en la unitat més petita, p. ex. minuts o segons, perquè el corrector ho pugui comparar; enunciat explícit), `stats_tables` (mitjana ponderada, mediana, moda, rang), `laplace` (fracció, `also_accept` simplificada).

Banc generat amb llavor fixa, ~12 ítems per competència nova (i `steps/` per a `linear_eq_steps`).

## 4. Tests

- Tests de les famílies noves (estil `tests/test_mathbank_m5.py`).
- `math-m7.md` vàlid; cada `Bank:` existeix.
- Ítems de m4, m5 i m7 ja existents **idèntics**.
- `python3 -m unittest discover -s tests` sencer. Única fallada esperada: el harness de `flash.test.ts` per les 4 llistes buides d'anglès.

## 5. Acceptació

- [ ] 18 competències noves a `math-m7.md`, les 9 antigues intactes.
- [ ] Famílies noves + `linear_eq_steps`; banc generat i validat.
- [ ] Res existent canviat. Tests en verd (llevat de l'esperada).
