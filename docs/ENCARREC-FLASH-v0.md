# Encàrrec — Flash v0 (vocabulari ràpid, sense model)

Branca: `flash-vocab`. Domini: només `language`. Estat: disseny tancat, per implementar.

## 1. Què és

Un mode de pràctica de vocabulari **ràpid i interactiu, sense LLM**. Pantalla pròpia (no el xat): surt una paraula, l'alumne escriu la traducció, el client corregeix a l'instant.

- No substitueix el vocabulari actual (`fluent-vocab`, banc, SM-2): **no s'hi toca res**.
- Reversible: un sol flag al manifest l'activa o el fa desaparèixer.
- Més endavant el mateix motor servirà per a math (taules, càlcul mental). **Ara no es construeix**, però el motor ha de separar *d'on surten les targetes* de *com es practica*.

## 2. Decisions preses (no reobrir)

| # | Decisió |
|---|---|
| 1 | Paraules de **llistes noves** a `curriculum/flash/`, no del banc. |
| 2 | v0 **no escriu a les bases de dades** de l'alumne. Progrés a `localStorage`, amb la forma exacta del futur `flash-db.json` al servidor. |
| 3 | Cronòmetre **visible i opcional** (interruptor recordat). |
| 4 | Només `language`. Math quan aquest model convenci. |

## 3. Context del codi (ja investigat)

- Servidor Bun: `server/src/http.ts` (`Bun.serve`, rutes `/api/math/*`). Cap a la línia 336-400 serveix `index.html` i injecta `window.__FLOWED_DOMAIN`, `__FLOWED_OPEN`, `__FLOWED_BRAND`, `__FLOWED_HIDDEN` llegint `config/domain.json` i `learner-profile.json` (a `opts.dataDir()`).
- Perfil: `learner.native_language` (text lliure: "Catalan", "català", "Spanish", "castellano"…), `learner.target_language`, `learner.current_level` (A1..C2).
- Web: `web/index.html`, `web/app.js` (~2100 línies), `web/style.css` (tokens a `:root`). Botons del nav amb `data-cmd="math-*"`. A `app.js` (~línia 1999-2075) `LANG_LABELS` i `LANG_ORDER` reetiqueten per a language; el clic envia una comanda a l'agent, **excepte** `math-progress`, que obre un overlay directament (`openProgress`, `#progress-overlay`, CSS `.overlay`). Helper `api(path)` (~línia 905).
- Tests: scripts plans, `node --experimental-strip-types server/test/<x>.test.ts`, estil `check(nom, cond)`.
- **Atenció:** `server/test/domain-shell.test.ts` exigeix que `hidden_commands` de language sigui buit i que `LANG_LABELS` no contingui `math-vocab`/`Vocabulary`. Per això Flash **no** es controla amb `hidden_commands`, sinó amb un flag propi.

## 4. Llistes de paraules

Ja creades: `curriculum/flash/en-A1/01-family.json`, `02-food.json`, `03-home.json`.

Esquema:

```json
{
  "id": "en-A1.flash.family",
  "level": "A1",
  "title": { "ca": "La família", "es": "La familia", "en": "Family" },
  "words": [
    { "id": "mother", "target": ["mother", "mum", "mom"], "native": { "ca": ["mare"], "es": ["madre"] } }
  ]
}
```

- El **primer** element de cada array és el que es mostra; la resta també s'accepten.
- Tasca: afegir `04-animals.json` i `05-verbs.json` (12 paraules cada una, ca + es). Verbs com `"target": ["to eat", "eat"]`.

## 5. Feina

### 5.1 Manifest (interruptor)

A `config/domain.json`, domini `language`:

```json
"flash": { "enabled": true, "dir": "curriculum/flash/en-*" }
```

Math no el porta ⇒ amagat. `enabled: false` ⇒ el botó desapareix del tot. **Aquest és el rollback.**

### 5.2 Servidor

- Nou `server/src/flash.ts` (funcions pures, testables):
  - `nativeCode(text)` → `"ca" | "es"` (accepta Catalan/català/catalan, Spanish/español/castellano; per defecte `"ca"`).
  - `loadFlashLists(root, dirGlob, nativeCode)` → llistes ordenades per nivell i nom de fitxer, amb `native` ja resolt al codi de l'alumne.
- A `http.ts`:
  - Injectar `window.__FLOWED_FLASH` (true/false) al costat dels altres globals.
  - Ruta `GET /api/flash/lists` (autoritzada com la resta de `/api`):
    `{ok, enabled, native, nativeCode, target, level, lists:[{id, level, title, words:[{id, target:[...], native:[...]}]}]}`.

### 5.3 Web

- `index.html`: botó `data-cmd="math-flash"` amb `⚡` i `Flash` (title: "Flash — vocabulari ràpid"), i `<script src="/flash.js">`.
- `app.js`, canvis mínims:
  - `LANG_ORDER`: Flash just després de Review.
  - Ocultar el botó si `!window.__FLOWED_FLASH`.
  - Al clic de `math-flash`: obrir l'overlay (com `math-progress`), sense torn de l'agent.
- Nou `web/flash.js` + CSS a `style.css`. Pantalla completa, **fons de color propi** (tokens nous a `:root`), paraula gran al centre, una sola caixa d'entrada.

#### Pantalles

1. **Menú:** llistes amb barra de progrés (sabudes/total) i ✓ si està tancada; selector de direcció (natiu→idioma, idioma→natiu, barrejat); interruptor de cronòmetre; botó Comença (per defecte, la primera llista no tancada). Les llistes tancades ofereixen "Repassa".
2. **Targeta:** Enter comprova.
   - Error 1 → la targeta tremola, torna a provar.
   - Error 2 → pista: primera lletra + guions (`m _ _ _ _ _`).
   - Error 3 → mostra la resposta; la targeta torna **una vegada** al final de la ronda.
   - Encert → flaix verd breu, següent. Si hi ha altres respostes vàlides, mostrar-les.
3. **Resum:** encerts a la primera, errors, millor ratxa, temps (si el cronòmetre és actiu). Botons: "Una altra ronda", "Menú", tancar.

Textos de la UI en català.

### 5.4 Correcció de respostes

- Minúscules, `trim`, espais col·lapsats, sense puntuació final.
- Sense accents per comparar. Si s'ha acceptat gràcies a això, mostrar l'ortografia correcta.
- Treure articles inicials — en: `the a an to` · ca: `el la l' els les un una` · es: `el la los las un una`.

### 5.5 Progressió ("aprendre i no repetir")

Caixa Leitner per paraula, 0..2:

| Resultat | Caixa |
|---|---|
| Encert a la 1a | +1 (màx. 2) |
| Encert a la 2a | igual |
| 3r error / resposta mostrada | `max(0, caixa-1)` |

- Paraula **sabuda** = caixa 2 (encert a la primera en dues rondes diferents).
- Composició de ronda (màx. 10): primer les vistes no sabudes (caixa més baixa primer), després les no vistes en ordre de llista. Les sabudes no surten.
- Totes sabudes ⇒ llista **tancada** (`closed_at`), el menú passa a la següent.
- **Repassa** una llista tancada: paraules barrejades, **no modifica l'estat**.
- La direcció no té caixa pròpia (una caixa per paraula).

Estat a `localStorage` (tot accés dins `try/catch`; la pàgina ha de funcionar sense), clau per domini + idioma + natiu. Forma = futur `flash-db.json`:

```json
{ "version": 1,
  "lists": { "<listId>": {
    "words": { "<wordId>": { "box": 0, "seen": 0, "first_try": 0, "misses": 0, "last": "2026-10-16" } },
    "closed_at": null } } }
```

La lògica (correcció, selecció de ronda, actualització de caixes, tancament) va com a **funcions pures** exposades a `globalThis.FlashCore`, perquè un test de node pugui carregar `web/flash.js` amb `vm`.

## 6. Tests

Nou `server/test/flash.test.ts`:

- Totes les llistes de `curriculum/flash`: ids únics (de llista i de paraula dins la llista), `ca` i `es` presents i no buits, `target` no buit.
- `nativeCode` amb les variants.
- Normalització: majúscules, accents, articles, puntuació.
- Leitner: pujar, mantenir, baixar; selecció de ronda; tancament de llista; "Repassa" no muta l'estat.
- Flag al manifest i injecció `__FLOWED_FLASH` a `http.ts`.

Després, passar **tots** els `server/test/*.test.ts` existents.

## 7. Criteris d'acceptació

- [ ] Amb `enabled: true`, un perfil language veu ⚡ Flash després de Review; un perfil math no.
- [ ] Amb `enabled: false`, cap rastre del botó.
- [ ] `/api/flash/lists` retorna les 5 llistes amb el natiu de l'alumne.
- [ ] El flux 1r/2n/3r error funciona; la paraula revelada torna al final.
- [ ] Una paraula encertada a la primera en dues rondes ja no surt; llista completa ⇒ ✓ i es passa a la següent.
- [ ] Cap canvi als fitxers de `data/` ni al comportament de `fluent-vocab`.
- [ ] Tests nous i existents en verd.

## 8. Fora d'abast (v1+)

- Persistència al servidor (`flash-db.json`) i connexió amb SM-2.
- Motor per a math (generadors: taules, 1×2 xifres, 2×2 xifres).
- Àudio (TTS) de la paraula.
