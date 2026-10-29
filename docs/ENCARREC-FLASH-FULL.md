# Encàrrec F1 — Flash: prova de full (60 multiplicacions en 2 minuts)

Branca: `flash-vocab`. Decisions tancades (Albert, 2026-10-29). Parteix de P3/P4 (`docs/ENCARREC-FLASH-P3-MODES.md`, `docs/ENCARREC-P4-FLASH-INICI.md`).

## 1. Què és

Reproduir la prova de classe de m5: un **full** amb 60 multiplicacions d'una xifra, totes diferents, en 4 columnes de 15. L'alumne les omple **en l'ordre que vulgui**. Quan s'acaba el temps (2 min), es corregeix i el resultat és **el nombre de respostes correctes** ("47 / 60").

Ha de ser **genèric**: el tipus d'operació, el nombre d'operacions, les columnes i el temps els diu la llista, no el codi. Avui només hi haurà una llista (multiplicació d'una xifra, 60, 4 columnes, 120 s); demà en podrà haver d'altres (sumes, divisions, 40 operacions en 3 minuts...) sense tocar codi.

## 2. La llista

Una llista Flash de math nova, `curriculum/flash/math-m5/04-full-taules.json`:

```json
{
  "id": "math-m5.flash.full_taules",
  "level": "m5",
  "title": { "ca": "Full de taules (60 en 2 min)", "es": "Hoja de tablas (60 en 2 min)", "en": "Times tables sheet (60 in 2 min)" },
  "generate": { "kind": "mult", "count": 64, "params": { "digits": [1, 1], "max": 9, "both_orders": true } },
  "sheet": { "n": 60, "cols": 4, "seconds": 120 }
}
```

- `sheet` (opcional) converteix la llista en **prova de full**: `n` operacions (totes diferents), `cols` columnes, `seconds` de temps. Valida-ho al carregar (`n` ≥ 1 i ≤ les cartes que pot donar el generador; `cols` 1–6; `seconds` 10–1800); si no és vàlid, la llista se salta amb un avís al log, com les altres llistes mal formades.
- Les operacions surten del **generador existent** (`generate`, el mateix que fan servir les llistes de pràctica, `practiceWords` / `drawWords` a `server/src/flash.ts`), amb una llavor nova cada vegada: cada full és diferent. Totes diferents: sense repetir el mateix enunciat (amb `both_orders`, `7 × 8` i `8 × 7` compten com a diferents, com al paper).
- Només llistes on totes les cartes es responen amb un número (`answer_kind` number). Una llista `sheet` amb altres tipus no és vàlida.
- Una llista `sheet` **no** compta per tancar Flash ni per al `flash_share` del test de nivell (`hooks/curriculum.py`): és una prova, no una llista per memoritzar. Comprova que `flash_progress` la ignora.

## 3. Servidor (`server/src/flash.ts`, `server/src/http.ts`)

- `GET /api/flash/lists`: la llista surt amb `sheet: {n, cols, seconds}` i sense paraules (com les de pràctica).
- `GET /api/flash/sheet?list=<id>&seed=<enter>`: les `n` cartes del full (mateix format que `/api/flash/practice`), mateix filtre de nivell que `/api/flash/practice`. Mateixa llavor ⇒ mateix full.
- La correcció es fa al navegador amb el mateix `check()` de `web/flash.js` que la resta de Flash (no dupliquis el corrector).
- Resultat desat a `flash-db.json` dins de l'entrada de la llista: `sheet: { history: [{ date, correct, answered, n, seconds }], best }` (els darrers 50 intents com a màxim). `sanitizeFlashState` l'accepta i el valida (números enters, `correct ≤ answered ≤ n`).

## 4. Web (`web/flash.js`, `web/style.css`)

- **Menú**: la llista surt amb una icona 📝 i, a sota, "60 operacions · 2 min" i, si n'hi ha, "Millor: 52 · Darrer: 47". En mode Contrarellotge, la llista surt com a no disponible (té el seu propi temps).
- **Començar**: pantalla breu "60 multiplicacions, 2 minuts. Omple les que puguis, en l'ordre que vulguis." i botó "Comença". El temps arrenca en prémer-lo.
- **El full**: graella de `cols` columnes × `n/cols` files (l'última columna pot ser més curta). Cada cel·la: `7 × 8 =` i una casella petita (`inputmode="numeric"`). A dalt, el temps que queda, i un botó "He acabat" per lliurar abans d'hora.
  - Teclat: Enter o ↓ passa a la casella de sota (al final d'una columna, a la primera de la següent); ↑ a la de sobre; Tab segueix l'ordre natural. Es pot clicar qualsevol casella.
  - Mòbil (390 px): si les 4 columnes no hi caben llegibles, 2 columnes (l'ordre de les operacions és el mateix). No ha d'haver-hi scroll horitzontal.
  - No es mostra cap correcció mentre dura la prova.
- **Final** (temps esgotat o "He acabat"): les caselles es bloquegen; es corregeix; surt **"47 / 60 correctes"** gran, i a sota "Respostes: 50 · Errors: 3 · En blanc: 10". Al full, cada casella en verd (correcta), en vermell amb la bona al costat (errònia), o en gris amb la bona (en blanc). Botons: "Un altre full" (llavor nova) i "Tornar".
- El progrés de la prova s'envia al servidor com la resta de l'estat de Flash (`/api/flash/state`), amb les claus per perfil (`flowedKey`, P4).
- Si la pestanya es tanca a mig full, l'intent no compta.

## 5. Abast

Fitxers: `server/src/flash.ts`, `server/src/http.ts`, `web/flash.js`, `web/style.css`, `curriculum/flash/math-m5/04-full-taules.json` (nou), `hooks/curriculum.py` només si cal perquè `flash_progress` ignori les llistes `sheet`, i els tests. No toquis `web/app.js` si no cal.

## 6. Tests

- Servidor: validació de `sheet`, `/api/flash/sheet` (n cartes, totes diferents, mateixa llavor ⇒ mateix full, nivell), `/lists` amb `sheet`, `sanitizeFlashState` amb l'historial.
- `flash_progress` ignora les llistes `sheet` (test a `tests/`).
- Web: recorregut al navegador (Chromium, servidor real amb un perfil m5 temporal, temps simulat): menú, començar, omplir unes quantes caselles en desordre (bé, malament, en blanc), "He acabat", resultat correcte i colors; i un altre amb el temps esgotat. Captures a 390 px i a 1024 px al scratchpad.
- Tots els tests (`bun test` a `server/`, `bun x tsc --noEmit`, `python3 -m unittest discover -s tests`) en verd.

## 7. Acceptació

- [ ] Llista "Full de taules": 60 multiplicacions diferents en 4 columnes, 2 minuts, s'omplen en qualsevol ordre.
- [ ] En acabar, el nombre de correctes, i les errades i en blanc marcades.
- [ ] Millor i darrer resultat al menú; desats al servidor.
- [ ] Una altra llista amb un altre `generate` i un altre `sheet` funcionaria sense tocar codi (prova-ho en un test amb una llista de sumes de 40 en 3 columnes i 90 s).
- [ ] Tests en verd.
