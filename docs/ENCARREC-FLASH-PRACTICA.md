# Encàrrec P1 — Flash: llistes de "calcular" (operacions noves a cada ronda) i taules de 81

Branca: `flash-vocab`. Decisions tancades (Albert, 2026-10-17).

## 1. Problema

Les llistes de math generades fan servir una llavor fixa (l'id de la llista): sempre surten **les mateixes** 12 operacions. Per a les taules està bé (s'han de memoritzar), però per a "2 xifres × 1 xifra", fraccions, percentatges, equacions… el que s'aprèn és el **mètode**: repetir les mateixes operacions fa memoritzar resultats.

## 2. Dos tipus de llista

| `mode` | Per a | Targetes | Llista tancada quan… |
|---|---|---|---|
| `memory` (per defecte, el d'ara) | taules, vocabulari, verbs, figures de classificar amb poques opcions | fixes (llavor = id de la llista), progrés **per targeta** (Leitner) | totes les targetes sabudes (com ara) |
| `practice` (nou) | operacions de càlcul | **noves a cada ronda** | **2 rondes en dies diferents amb ≥ 80 % d'encerts a la primera** (≥ 8 de 10) |

### 2.1 Quines llistes són `practice`

Afegeix `"mode": "practice"` a **totes** les llistes generades de `curriculum/flash/math-m5/`, `math-m6/` i `math-m7/`, **excepte**:
- les de taules (`*taules-repas*`),
- les de `kind` amb poques targetes possibles (les que tenen entrada a `GEN_ROOM`: `proportion_type`, `notable_points`, `variable_type`, `laplace`, `polygon_angle_sum`), que es queden `memory`.

Language: tot es queda `memory`.

### 2.2 Servidor (`server/src/flash.ts`, `server/src/http.ts`)

- `GET /api/flash/lists`: per a una llista `practice` torna la llista **sense** `words` fixes (o amb `words: []`) i amb `mode: "practice"`, el títol i el nivell.
- Ruta nova `GET /api/flash/practice?list=<id>&n=10&seed=<enter>`: genera `n` targetes noves (màx. 20) amb el generador de la llista i la llavor donada, ids `p1…pN`. El client tria una llavor aleatòria per ronda. Valida que la llista existeixi, que sigui `practice` i del nivell de l'alumne (el mateix filtre que `/lists`).
- Estat (`flash-db.json`, mateix fitxer): per a una llista `practice`, `lists[<id>].practice = { rounds: [{ day: "YYYY-MM-DD", first_try: n, total: n }] }` (màx. 30 rondes guardades, les més recents). `sanitizeFlashState` ho ha d'acceptar i validar. Les llistes `memory` no canvien.

### 2.3 Client (`web/flash.js`)

- Ronda `practice`: 10 targetes de `/api/flash/practice` amb una llavor nova; les fallades tornen al final una vegada, com ara; temps, punts i pistes iguals.
- En acabar la ronda: s'afegeix `{day, first_try, total}` (`total` = targetes de la ronda sense comptar les reencuades). La llista queda tancada (`closed_at`) quan hi ha **2 rondes amb `first_try / total ≥ 0.8` en dies diferents**.
- Menú: per a `practice`, en lloc de `sabudes X/Y` es mostra `rondes bones X/2` (i ✓ quan està tancada). Una llista `practice` tancada continua sent jugable (cada ronda és nova); les rondes noves es guarden però no la tornen a obrir.
- Resum de ronda `practice`: `8 de 10 a la primera` i, si compta, "✓ Ronda bona (1 de 2)".

### 2.4 Python (`hooks/curriculum.py`, `flash_progress`)

- `flash_lists` ha de saber el `mode` de cada llista (del fitxer). Per a `practice`: tancada si `closed_at` existeix **o** si a `practice.rounds` hi ha 2 rondes bones en dies diferents (mateixa regla que el client). Per a `memory`, com ara.
- El total i `needed` de `flash_share` no canvien de regla.

## 3. Taules de 81 (m5)

- Generador `mult`: paràmetres nous `max` (valor màxim dels factors d'1 xifra; per defecte 9, permet 10) i `both_orders` (si és `true`, `7 × 8` i `8 × 7` són targetes diferents; per defecte `false`, com ara).
- `GEN_COUNT_MAX` (i el mirall Python `_flash_count`) puja de 50 a **100**.
- `curriculum/flash/math-m5/01-taules-repas.json` → **id nou** `math-m5.flash.taules` (així el progrés antic de 24 no es barreja), títol "Taules", `generate: { kind: "mult", count: 81, params: { digits: [1, 1], max: 10, both_orders: true } }` ⇒ del 2 al 10 en tots dos ordres = 81 targetes. `mode` = `memory`.
- m6 i m7 no canvien les seves taules de repàs.

## 4. Tests

- TS: `/api/flash/practice` (llavors diferents ⇒ targetes diferents; mateixa llavor ⇒ mateixes; llista `memory` o d'un altre nivell ⇒ error), `mode` a `/lists`, `sanitizeFlashState` amb `practice.rounds`, regla de tancament (1 ronda bona no tanca; 2 el mateix dia no tanquen; 2 en dies diferents sí; 7/10 no compta), `mult` amb `max`/`both_orders` (81 targetes úniques, resultats bons), cap llista `practice` amb `kind` de `GEN_ROOM`.
- Python: `flash_progress` amb llistes `practice` (tancada per rondes), ids/recomptes del mirall amb `count` fins a 100.
- jsdom o Chromium (scratchpad): una ronda `practice` (targetes noves), el menú amb `rondes bones`, i dues rondes la mateixa llista donen operacions diferents.
- Tots: `server/test/*.test.ts`, `cd server && bun x tsc --noEmit`, `python3 -m unittest discover -s tests` — **tots han de passar**.

## 5. Acceptació

- [ ] Llistes de càlcul: operacions noves a cada ronda; es tanquen amb 2 rondes bones en dies diferents.
- [ ] Taules de m5: 81 targetes fixes (2–10, tots dos ordres).
- [ ] Language i les llistes `memory` no canvien.
- [ ] Tests en verd.
