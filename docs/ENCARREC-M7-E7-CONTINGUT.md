# Encàrrec E7 — Contingut Flash de m7

Branca: `flash-vocab`. Parteix d'E5 (generadors de m7) i E6 (competències noves a `math-m7.md`). Mateix estil que E4 (`docs/ENCARREC-M5-E4-CONTINGUT.md`). Decisions tancades.

## 1. Llistes

Carpeta nova `curriculum/flash/math-m7/`. **Una llista per generador d'E5** (§4 de `docs/ENCARREC-M7-E5-FLASH.md`), en l'ordre d'aquella taula, numerades `01-`, `02-`…, 12 targetes, ids `math-m7.flash.<slug ascii del títol>`, títols `ca`/`es`/`en`, i `competence` amb l'id de `math-m7.md` que correspon segons la taula §1.1 de `docs/DISSENY-M7-M6.md` (`m7.integers`, `m7.factor_gcd_lcm`, …). A més, al principi:

- `00-taules-repas.json`: "Taules (repàs)", `kind: "mult"`, `digits: [1, 1]`, `count: 24`, sense `competence` (el repàs de càlcul continua a m7).

## 2. Requisit de nivell

`flash_share: 60` a la capçalera de `curriculum/math-m7.md`. Comprova `flash_progress` (total = llistes vàlides, `needed = ceil(total × 0,6)`).

## 3. Tests

- Llistes vàlides, ids únics, cada `competence` existeix a `math-m7.md`.
- Python: `flash_progress` de m7 amb `share == 60` i el total correcte.
- Captures (Chromium, 390 px) d'una targeta de cada tipus de resposta nou (`factorization`, `algebraic`, `sexagesimal`) i de les figures `parallels`, `right_triangle`, `grid` amb recta, al scratchpad.
- Tots els tests (`server/test/*.test.ts`, `bun x tsc --noEmit`, `python3 -m unittest discover -s tests`). Única fallada esperada: les 4 llistes buides d'anglès.

## 4. Acceptació

- [ ] Una llista per generador de m7 + repàs de taules, amb `competence`.
- [ ] `flash_share: 60` a `math-m7.md`.
- [ ] Res més canvia. Tests en verd (llevat de l'esperada).
