# Encàrrec P4 — Error de llistes buides a Flash i botó 🏠 Inici amb el portal

Branca: `flash-vocab`. Decisions tancades (Albert, 2026-10-18).

## 1. Error: en triar una llista no surt res a sota

Després de P3 (`docs/ENCARREC-FLASH-P3-MODES.md`, commit `885d923`), l'Albert veu a railab que, almenys amb la llista **"Tipus d'angles"** (m5, `angle_type`, `choice`, `practice`), **no surt res a sota** en triar-la, tant en mode Normal com en Contrarellotge.

- Reprodueix-ho en un navegador real (Chromium del sistema) amb l'app real (`web/index.html` + `app.js` + `flash.js`) sobre el `server/src/flash.ts` real, amb un perfil m5 en un directori temporal. Hi ha arnesos de P2/P3 a `/tmp/claude-0/-home-user-flowed/db921e4d-817b-5de9-b68f-31ca77e8f10a/scratchpad/p3/` (`drive-p3.mjs`) i `sprint-ui/`.
- Prova: seleccionar la llista (un clic), doble clic, botó de baix, en tots dos modes; també després de canviar de mode; i amb altres llistes `choice` (`triangle_by_sides`, `circle_element`) i alguna numèrica, per veure l'abast.
- Mira la consola (errors JS) i les peticions (`/api/flash/practice`).
- Troba la causa, corregeix-la i deixa'n un test (de codi font o funcions pures, com fan els de P2/P3) que hauria fallat abans.

## 2. Botó 🏠 Inici quan s'entra pel portal

Context: el portal (`scripts/flowed-portal.mjs`, `docs/ENCARREC-PORTAL.md`) fa d'intermediari amb el servidor de cada perfil; `/switch` torna a la tria de perfil (si n'hi ha més d'un) i `/logout` tanca la sessió del portal.

- El portal, en servir la pàgina principal (`/` o `index.html`) d'un perfil, injecta abans de `</head>` `<script>window.__FLOWED_PORTAL={multi:<true|false>}</script>` (`multi` = l'alumne té més d'un perfil a la sessió). Res més de la pàgina canvia.
- `web/index.html` / `web/app.js`: si `window.__FLOWED_PORTAL` existeix, a la capçalera surt un botó **🏠** (títol: "Inici" si `multi`, "Surt" si no). Sense portal, no surt (els ports directes no canvien).
- En prémer-lo: confirmació breu ("Vols acabar la sessió i tornar a l'inici?"). Si sí, **es tanca la sessió exactament com 🏁 End** (mateix camí: la comanda d'acabar, que desa i fa el resum), s'espera que acabi (amb un límit, p. ex. 20 s; si no acaba, es continua igualment, perquè el servidor tanca sol la sessió als 30 min d'inactivitat), i es navega a `/switch` si `multi`, o a `/logout` si no.
- Si no hi ha cap sessió activa (no s'ha fet res), no cal acabar-la: es navega directament.

## 3. Abast

Fitxers: `web/flash.js`, `web/app.js`, `web/index.html`, `web/style.css`, `scripts/flowed-portal.mjs`, `server/test/flash.test.ts`, `tests/test_portal.py`, i els tests de web que calgui. No toquis `hooks/`, `curriculum/`, el banc.

## 4. Tests

- §1: el test nou + el recorregut al navegador (captura de la llista "Tipus d'angles" seleccionada en tots dos modes, 390 px, al scratchpad).
- §2: el portal injecta `__FLOWED_PORTAL` només a la pàgina principal i amb el `multi` correcte (tests a `tests/test_portal.py`); el botó surt amb portal i no sense; en prémer-lo es crida el mateix camí que 🏁 End i després es navega a `/switch` o `/logout` (prova al navegador amb el portal i un servidor de perfil de prova).
- Tots els tests del repo en verd.

## 5. Acceptació

- [ ] En triar "Tipus d'angles" (i les altres) surten les opcions i es pot jugar, en tots dos modes.
- [ ] 🏠 només amb portal; acaba la sessió com 🏁 i torna a la tria o surt.
- [ ] Tests en verd.
