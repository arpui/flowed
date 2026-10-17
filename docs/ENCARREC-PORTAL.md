# Encàrrec G1 — Portal: una sola adreça per a tots els alumnes

Decisions tancades (Albert, 2026-10-17).

## 1. Problema

Cada perfil d'alumne és un servidor web propi en un port propi (`FLOWED_WEBS="nes-en:4102 iona-math:4207 …"` al `.env`; l'arrenca `scripts/flowed-web.sh --app <id> --port <N>`, amb basic auth: usuari = nom de l'alumne en minúscules, contrasenya a `~/.flowed/<id>/.web-password`). Cal donar a cada alumne el seu port. Es vol **una sola adreça**.

## 2. Què es fa

Un programa nou, `scripts/flowed-portal.mjs` (Bun, mateix estil que `scripts/flowed-web-proxy.mjs`, llegeix-lo), que escolta en **un port** (`FLOWED_PORTAL_PORT`, per defecte `4000`) i:

1. **Pàgina d'entrada** (`GET /` sense sessió): formulari usuari + contrasenya, en català, amb l'estil de la web (colors de `web/style.css`), usable al mòbil.
2. **Login** (`POST /login`): busca els perfils de `FLOWED_WEBS` (llegit amb la mateixa lògica de `.env` que `scripts/lib-paths.sh` / `flowed-start.sh`; perfils a `FLOWED_HOME_DIR`, per defecte `~/.flowed`) amb aquell **nom d'usuari** (el nom de l'alumne en minúscules, com `flowed-web.sh`: mira com el calcula) i **contrasenya** (`.web-password` del perfil). Comparació en temps constant.
   - Cap coincidència ⇒ "Usuari o contrasenya incorrectes" (sense dir quin dels dos). Limitació simple d'intents (p. ex. 5 errors per IP en 5 minuts ⇒ espera).
   - Una coincidència ⇒ entra directament.
   - Diverses (p. ex. `nes-en` i `nes-math`, mateix nom i mateixa contrasenya o no) ⇒ pàgina **"Què vols fer?"** amb un botó per perfil: "🌍 Anglès" / "🧮 Matemàtiques" (segons el domini del perfil, `learner-profile.json`), amb el nivell si n'hi ha.
3. **Sessió**: cookie `HttpOnly`, `SameSite=Lax`, signada (HMAC amb un secret aleatori desat a `~/.flowed/.portal-secret`, mode 600, creat la primera vegada), que diu quin perfil. Durada 30 dies. `GET /logout` l'esborra.
4. **Proxy**: amb sessió, **tota** petició (pàgina, `/api/*`, estàtics, i l'SSE `/api/event` en streaming sense buffer) es reenvia a `http://127.0.0.1:<port del perfil>` afegint la capçalera `Authorization: Basic …` del perfil, de manera que el navegador **no veu mai** el diàleg de basic auth. Respostes i capçaleres es tornen tal qual (sense `WWW-Authenticate`). Si el servidor del perfil no respon ⇒ pàgina "Ara no està disponible" amb enllaç per sortir.
5. **Canviar de perfil**: un enllaç petit "Canvia" (fixe a la cantonada, injectat per pàgina d'entrada no; n'hi ha prou amb `GET /switch` que torna a "Què vols fer?" si n'hi ha més d'un, i `/logout`). No toquis `web/` per això.

## 3. Arrencada

- `scripts/flowed-start.sh`: si `FLOWED_PORTAL_PORT` està definit (al `.env` o l'entorn), en arrencar les webs arrenca també el portal (en segon pla, log a `~/.flowed/portal.log`, pid a `~/.flowed/portal.pid`) i en mostra l'adreça (local i de xarxa, com `flowed-web.sh`). `scripts/flowed-stop.sh` l'atura (també amb `--webs-only`).
- Afegeix `FLOWED_PORTAL_PORT=4000` comentat a `.env.railab` i `.env.rapve` (plantilles), amb una línia d'explicació.
- Documenta-ho breument a `docs/RUNNING.md` (com activar-lo, com entrar, com afegir un alumne: només `FLOWED_WEBS`).

## 4. Abast

Fitxers: `scripts/flowed-portal.mjs` (nou), `scripts/flowed-start.sh`, `scripts/flowed-stop.sh`, `.env.railab`, `.env.rapve`, `docs/RUNNING.md`, tests nous (`server/test/portal.test.ts` o `tests/test_portal.py`). **No** toquis `web/`, `server/src/`, `hooks/`, `curriculum/` (un altre agent hi treballa). Els servidors de perfil no canvien: continuen funcionant pel seu port com ara.

## 5. Tests

- Amb dos servidors falsos (Bun, en ports temporals, amb basic auth) i un `.env`/`FLOWED_HOME_DIR` temporals: login correcte/incorrecte, un perfil ⇒ entra, dos perfils ⇒ "Què vols fer?", la cookie porta al perfil correcte, el proxy afegeix l'`Authorization` i el perfil respon, SSE passa en streaming (rep dos esdeveniments separats en el temps), cookie manipulada ⇒ torna al login, límit d'intents, perfil caigut ⇒ pàgina d'error.
- Tots els tests del repo en verd.

## 6. Acceptació

- [ ] Una adreça, login per nom + contrasenya, tria de math/anglès si en té tots dos.
- [ ] Mai surt el diàleg de basic auth; l'app funciona igual (inclòs l'SSE).
- [ ] S'arrenca i s'atura amb `flowed-start.sh` / `flowed-stop.sh` si `FLOWED_PORTAL_PORT` és definit.
- [ ] Tests en verd.
