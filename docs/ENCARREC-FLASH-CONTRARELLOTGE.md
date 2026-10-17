# Encàrrec P2 — Flash: mode contrarellotge

Branca: `flash-vocab`. Parteix de P1 (`docs/ENCARREC-FLASH-PRACTICA.md`: llistes `memory` / `practice`, taules de 81). Decisions tancades (Albert, 2026-10-17).

## 1. Què és

Un mode de ronda nou dins de Flash: fer **tantes operacions com es pugui en un temps fix**. Les operacions surten una darrere l'altra, l'alumne escriu el resultat i passa a la següent **sense correcció**; tot es corregeix **al final**.

## 2. On surt

- Només a llistes de math on totes les targetes són de resposta `number` o `unit` (taules, `mult`, `combined`, `frac_of`, `percent_of`, `dec_times_int`, etc.). No a `choice`, `fraction`, `pair`, `factorization`, `algebraic`, `sexagesimal`, ni a language.
- Menú: amb una llista d'aquestes seleccionada, al costat de "Comença" un botó **⏱ Contrarellotge** i un selector de durada **1 / 2 / 3 min** (per defecte 2, recordat a les preferències).
- El doble clic sobre la llista continua començant una ronda normal.

## 3. Durant el temps

- Compte enrere gran a dalt (`1:42`) i comptador d'operacions fetes. Sense temps per targeta, sense punts de colors, sense pistes, sense feedback.
- Enter amb resposta ⇒ es guarda i surt la següent a l'instant. Enter buit ⇒ es salta (compta com a no feta, no com a errada).
- Teclat numèric al mòbil, com ara.
- Font de targetes:
  - `memory` (taules): totes les targetes de la llista **barrejades**; si s'acaben, es tornen a barrejar (sense repetir la mateixa dues vegades seguides).
  - `practice`: lots de `/api/flash/practice` (n = 20, llavor nova cada lot), demanats abans que s'acabi el lot actual.
- En arribar a 0: la targeta a mig escriure **no** compta; es passa al resum.

## 4. Resum

- `34 de 38 bé` (fetes = respostes donades; saltades a part si n'hi ha).
- Llista de les errades: `7 × 8 — has posat 54 → 56` (màx. 20, la resta "i N més").
- **Rècord** de la llista per a aquella durada: "🏆 Nou rècord!" si se supera (rècord = nombre d'encerts).
- Botons: "Un altre cop", "Menú".

## 5. Progrés

- **No** canvia caixes ni tanca llistes (`memory` ni `practice`): no hi ha hagut correcció ni pistes.
- **Sí** compta com a ronda per a l'avís diari (`rounds_by_day`).
- `flash-db.json`: `lists[<id>].sprint = { best: { "60": n, "120": n, "180": n }, runs: [{ day, seconds, done, correct }] }` (màx. 30 runs). `sanitizeFlashState` i el mirall Python l'han d'acceptar (Python no el fa servir per a `flash_progress`).

## 6. Tests

- Funcions pures a `FlashCore`: barreja sense repetició seguida, correcció del lot al final, rècord, saneig de `sprint`.
- Elegibilitat: quines llistes mostren el botó (number/unit sí; choice/fraction/language no).
- jsdom o Chromium (scratchpad): una contrarellotge de 1 min amb el temps simulat; captures del joc i del resum a 390 px.
- Tots els tests (`server/test/*.test.ts`, `bun x tsc --noEmit`, `python3 -m unittest discover -s tests`) en verd.

## 7. Acceptació

- [ ] Botó i selector de durada només a les llistes elegibles.
- [ ] Sense correcció durant el temps; resum amb errades i rècord.
- [ ] No altera el progrés de targetes ni el tancament de llistes; compta per a l'avís diari.
- [ ] Tests en verd.
