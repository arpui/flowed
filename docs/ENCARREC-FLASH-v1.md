# Encàrrec — Flash v1 (persistència al servidor i requisit de nivell)

Branca: `flash-vocab`. Parteix de la v0.1 (`docs/ENCARREC-FLASH-v0.1.md`, commit `e3dea33`). Tot el que no es diu aquí es manté igual.

## 1. Què i per què

Flash ha de comptar per **passar de nivell**. El progrés és avui al navegador (`localStorage`), que el servidor no pot llegir. Aquesta versió:

1. Mou el progrés a `data/flash-db.json` (al directori de dades de l'alumne).
2. Afegeix un requisit al test de nivell: un percentatge de llistes Flash del nivell **tancades**.
3. Mostra Flash al camí de l'alumne.
4. Posa un recordatori diari (1 ronda) al botó ⚡.

## 2. Decisions preses (no reobrir)

| # | Decisió |
|---|---|
| 1 | Flash és un **apartat propi**. No escriu respostes a les competències existents (`learner-path.json`) ni a cap de les 6 BD. |
| 2 | Requisit de nivell = **80 %** de les llistes Flash del nivell tancades, i ha de ser **fàcil de canviar**: clau `flash_share` a la capçalera del fitxer del nivell (`curriculum/en-A1.md`). Sense la clau (o `0`) ⇒ cap requisit. |
| 3 | Recordatori diari = **1 ronda** acabada. Avís, **no** bloqueig. |
| 4 | Lligam informatiu llista → competència (`"competence"` al JSON de la llista). No té cap efecte ara. |

## 3. Context del codi (ja investigat)

- `hooks/curriculum.py`:
  - `parse_curriculum()` (~l. 156) llegeix la capçalera YAML-simple; els enters són a la tupla `("version", "pass_mark", "carry_mark", "checkpoint_items", "ready_share")` (~l. 167). `validate_curriculum()` (~l. 296) comprova `ready_share` 0-100.
  - `checkpoint_ready(rows, cfg, cur)` (~l. 531) decideix si s'obre el test. Es crida a ~l. 802 (missatge "The level test opens when…"), ~l. 1531 (vista JSON del camí: `"checkpoint": "ready"|"pending"`) i ~l. 1587 (resum de text "Checkpoint: …").
  - La vista JSON del camí (`/api/math/path` → `curriculum.py json --auto --data <dir>`) es construeix cap a ~l. 1520.
  - Tests Python a `tests/test_curriculum.py` (p. ex. ~l. 148-162 per a `checkpoint_ready` i `ready_share`).
- Llistes: `curriculum/flash/en-A1/*.json` (camp `level: "A1"`). El fitxer del nivell és `curriculum/en-A1.md` ⇒ la carpeta de llistes del nivell és `curriculum/flash/<stem del fitxer del nivell>/`.
- Servidor: `server/src/flash.ts` (càrrega de llistes, `flashListsResponse`), ruta `GET /api/flash/lists` a `server/src/http.ts`. `opts.dataDir()` és el directori de dades.
- Web: `web/flash.js` (`FlashCore` pur + UI; estat amb forma `{version:1, lists:{<listId>:{words:{<wordId>:{box,seen,first_try,misses,last}}, closed_at}}}` a `localStorage` amb clau `flowed.flash.v1|<domain>|<target>|<code>`).
- Avís diari: `web/app.js` ~l. 503-530, `renderSkillBadge(btn, …)` ja fa "1 pendent avui" per a Facts/Problemes/Raonament. Reutilitzar-lo per a ⚡.

## 4. Feina

### 4.1 `data/flash-db.json`

Forma = l'estat actual + registre de rondes:

```json
{ "version": 1,
  "lists": { "<listId>": { "words": { "<wordId>": { "box": 0, "seen": 0, "first_try": 0, "misses": 0, "last": "2026-10-16" } }, "closed_at": null } },
  "rounds_by_day": { "2026-10-16": 2 } }
```

- Servidor (`flash.ts` + `http.ts`):
  - `GET /api/flash/state` → el fitxer (o un estat buit si no existeix).
  - `PUT /api/flash/state` → valida la forma (versió, tipus, `box` 0..2, ids de llista existents; descarta el que no encaixi) i l'escriu **de forma atòmica** (fitxer temporal + `rename`).
- Client (`flash.js`):
  - En obrir Flash: llegeix l'estat del servidor. **Migració única:** si el servidor és buit i `localStorage` té progrés, puja'l amb PUT.
  - Desa amb PUT en acabar cada targeta i en acabar la ronda (incrementa `rounds_by_day[avui]` en acabar una ronda que **no** sigui de repàs).
  - Si el PUT falla: guarda a `localStorage` com ara i torna-ho a provar en el desat següent. Flash no ha de petar mai per culpa del servidor.

### 4.2 Requisit de nivell (`hooks/curriculum.py`)

- Capçalera: afegir `flash_share` a la tupla d'enters i a la validació (0-100). Afegir `flash_share: 80` a `curriculum/en-A1.md` (només aquí; A2 encara no té llistes).
- Nova funció pura `flash_progress(root, cur, data_dir) -> {"closed": n, "total": m, "share": p, "needed": k, "met": bool}`:
  - Llistes del nivell: `curriculum/flash/<stem>/*.json`.
  - Una llista és **tancada** si **totes** les paraules del fitxer tenen `box >= 2` a `flash-db.json` (no et fiïs només de `closed_at`: si s'afegeixen paraules a una llista, deixa d'estar tancada).
  - `needed = ceil(total * share / 100)`. `met = closed >= needed`. Si `share == 0` o `total == 0` ⇒ `met = true`.
- `checkpoint_ready(...)`: a més del que ja comprova, exigeix `flash_progress(...).met`. Cal que li arribin `root` i `data_dir` (paràmetres opcionals amb valor per defecte que no canviï el comportament quan no es passen: si falten ⇒ sense requisit Flash). Actualitzar els tres llocs on es crida.
- Missatges quan el que falta és Flash:
  - ~l. 802: "…and closed enough Flash lists (N of M; you have K)."
  - ~l. 1587: "Checkpoint: encara no (Flash: K/N llistes tancades)".
- Vista JSON del camí: afegir `"flash": {closed, total, share, needed, met}` (o `null` si el nivell no en té).

### 4.3 Camí (web)

- A la vista del camí (overlay de progrés del camí a `app.js`), una fila **⚡ Flash: K/M llistes tancades** amb una barra, i "cal N per al test" si `share > 0`.

### 4.4 Avís diari al botó ⚡

- Pendent si avui `rounds_by_day[avui]` és 0 o no hi és. Reutilitzar `renderSkillBadge` (objectiu fix = 1). Es refresca en carregar la pàgina i en tancar Flash.

### 4.5 Llistes

- Afegir `"competence"` a cada llista: `01-family` → `a1.vocab_family`, `02-food` → `a1.vocab_food_snacks`; la resta sense camp (no hi ha competència equivalent). Només informatiu.

## 5. Tests

- Python (`tests/test_curriculum.py` o un fitxer nou `tests/test_flash_gate.py`, mateix estil): parse/validació de `flash_share`; `flash_progress` (cap fitxer, llista parcial, llista tancada, paraula afegida ⇒ deixa d'estar tancada, `share` 0); `checkpoint_ready` amb i sense requisit Flash; els tests existents no canvien de resultat.
- TS (`server/test/flash.test.ts`): validació del PUT (descarta camps dolents, `box` fora de rang), escriptura atòmica en un directori temporal, GET d'estat buit.
- jsdom (al scratchpad): migració `localStorage` → servidor, desat per targeta, PUT que falla ⇒ continua amb `localStorage`, avís ⚡ pendent/fet.
- Passar **tots** els `server/test/*.test.ts` (`node --experimental-strip-types`), `cd server && bun x tsc --noEmit` i `python3 -m pytest tests -q` (o `python3 -m unittest`, el que facin servir els existents).

## 6. Criteris d'acceptació

- [ ] El progrés de Flash viu a `data/flash-db.json`; el que hi havia al navegador s'hi copia la primera vegada.
- [ ] Amb `flash_share: 80` a `en-A1.md`, el test de nivell no s'obre fins a tenir 4 de 5 llistes tancades (a més dels requisits actuals). Treient la línia, tot torna a ser com abans.
- [ ] El camí mostra ⚡ Flash K/M i què cal.
- [ ] El botó ⚡ mostra l'avís diari fins que s'acaba una ronda (no de repàs) aquell dia.
- [ ] Cap canvi a les 6 BD ni a `learner-path.json`. Tots els tests en verd.
