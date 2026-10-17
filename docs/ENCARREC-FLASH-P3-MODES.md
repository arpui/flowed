# Encàrrec P3 — Flash: selector de mode a dalt i contrarellotge també amb opcions

Branca: `flash-vocab`. Parteix de P2 (`docs/ENCARREC-FLASH-CONTRARELLOTGE.md`, commit `3ec7f26`). Decisions tancades (Albert, 2026-10-17).

## 1. Error a corregir

Després d'una contrarellotge, al resum, **"Un altre cop" no torna a fer una contrarellotge** (l'Albert ho ha vist a railab). El codi sembla correcte llegint-lo (`sprint-again` → `startSprint`), així que **reprodueix-ho en un navegador real** (Chromium del sistema, servidor de prova com a P2) fent exactament: menú → llista → ⏱ → esperar el final del temps (temps simulat) → clic a "Un altre cop" (i també Enter amb el focus on quedi després del final). Troba la causa, corregeix-la i deixa'n un test.

## 2. Selector de mode a dalt del menú

- A dalt del menú de Flash (sota el títol, abans de la direcció/temps): un selector segmentat **Normal** | **⏱ Contrarellotge**, recordat a les preferències. Amb Contrarellotge, al costat, **1 / 2 / 3 min** (el selector actual de durada es mou aquí).
- Amb **Contrarellotge** triat:
  - les llistes no elegibles surten en gris, no seleccionables, amb un text petit "no disponible en contrarellotge";
  - el doble clic i el botó de baix (que diu "⏱ Comença") comencen una contrarellotge;
  - el selector "Temps per paraula" s'amaga (no s'aplica).
- Amb **Normal**: tot com ara; el botó ⏱ del costat de "Comença" desapareix (el mode ja es tria a dalt).
- Al resum, el botó de repetir **sempre repeteix el mode que s'acaba de fer** ("Un altre cop" a contrarellotge, "Una altra ronda" a normal).

## 3. Contrarellotge també amb opcions

- Llistes elegibles: les d'abans (totes les targetes `number`/`unit`) **i** les de `choice` (totes les targetes amb botons). Una llista que barreja `choice` i `number` (p. ex. `bars_read`) també és elegible: cada targeta es respon pel seu tipus.
- Targeta `choice` en contrarellotge: botons (i tecles 1–n); **un toc** respon i passa a la següent, sense marcar si és correcte. No hi ha desactivació d'opcions.
- Resum: les errades de `choice` es mostren igual (`Quin tipus d'angle és? — has triat obtús → agut`), amb la figura en petit si en tenia.
- Les de `fraction`, `pair`, `factorization`, `algebraic`, `sexagesimal` i language continuen **no** elegibles.
- `sprintable()` al servidor s'actualitza en conseqüència (i els seus tests).

## 4. Tests

- Test del punt 1 (el que reprodueix l'error, en verd després de la correcció).
- Selector: preferència recordada, llistes en gris, doble clic en cada mode, botó de repetir segons el mode.
- Elegibilitat amb `choice` i mixtes; resum amb errades de `choice`.
- Captures (390 px) al scratchpad: menú en mode Contrarellotge (amb llistes en gris), una targeta `choice` en contrarellotge.
- Tots els tests (`server/test/*.test.ts`, `bun x tsc --noEmit`, `python3 -m unittest discover -s tests`) en verd.

## 5. Acceptació

- [ ] "Un altre cop" repeteix la contrarellotge.
- [ ] Selector Normal / Contrarellotge a dalt, amb llistes no elegibles en gris.
- [ ] Contrarellotge també amb llistes d'opcions.
- [ ] Res més canvia. Tests en verd.
