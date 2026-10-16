# Encàrrec — Flash v0.1 (ronda clara, temps per paraula, continuïtat)

Branca: `flash-vocab`. Parteix de la v0 (`docs/ENCARREC-FLASH-v0.md`, commit `36aa218`). Tot el que no es diu aquí es manté igual.

Prova d'Albert (2026-10-16): visualment bé, però tres problemes.

## 1. El comptador de dalt no s'entén

**Problema.** Durant la ronda, dalt hi diu `0/12 sabudes` i no es mou encara que encertis. És correcte (una paraula és *sabuda* quan l'encertes a la primera en **dues rondes diferents**), però sembla un error. A més no se sap quant falta per acabar la ronda.

**Canvi.**
- Durant la ronda, dalt hi va el **progrés de la ronda**: `Paraula 3 de 10` + una fila de punts, un per targeta de la ronda.
  - Pendent: buit. Actual: contorn marcat.
  - Encert a la 1a: verd (`--flash-ok`). Encert a la 2a: groc/ambre (token nou). Fallada o temps esgotat: vermell (`--flash-err`).
  - Les targetes que tornen al final de la ronda (revelades) **afegeixen** un punt al final quan es reencuen, perquè el total sigui honest.
- `X/Y sabudes` **surt de la pantalla de joc**. Es queda al menú (ja hi és, amb la barra) i al resum.
- Al **resum**, afegir: `Sabudes: 0 → 2 de 12` (abans → després de la ronda) i `A mig camí: N` (paraules amb caixa 1). Sota, una línia petita: "Una paraula queda sabuda quan l'encertes a la primera en dues rondes."

## 2. Temps per paraula (substitueix el cronòmetre general)

**Problema.** El cronòmetre general no diu res útil.

**Canvi.**
- L'interruptor "Cronòmetre" del menú passa a ser **"Temps per paraula"**, amb tres opcions: `10 s`, `20 s` (per defecte), `30 s`. Desactivat = sense límit (com ara). Es recorda a `flowed.flash.prefs` (`timer: false | 10 | 20 | 30`; migrar el valor antic `true` → `20`).
- Quan surt una targeta comença el compte enrere: **barra que s'escurça** sota la paraula (verda → ambre als últims 5 s → vermella als últims 3 s) i els segons en número petit.
- Els errors **no** reinicien el temps (els 3 intents comparteixen el mateix temps).
- Temps esgotat ⇒ compta com a **fallada** (mateix camí que el 3r error: `how = "revealed"`, la caixa baixa, la targeta torna al final una vegada). Es mostra "⏱ Temps!" i la resposta correcta, i **passa sola** a la següent en 2 s (no espera Enter: en mode temps, el ritme no s'atura).
- El compte enrere s'atura mentre es mostra el feedback d'encert/fallada.
- Resum: substituir "Temps" per **"Temps mitjà per paraula"** (només targetes respostes, no les esgotades).
- Les funcions pures que calgui (p. ex. color de la barra segons temps restant, migració de prefs) a `FlashCore`, amb test.

## 3. Continuïtat amb FlowEd

**Problema.** Flash ocupa tota la pantalla i sembla una altra app.

**Canvi.**
- La capçalera de FlowEd (`<header>`: marca, estat, botons) **queda visible**. La pantalla Flash comença **sota** la capçalera i ocupa la resta (mateix ample màxim que `body`, 760 px, centrada).
  - `app.js` ja manté l'alçada real de la capçalera amb un `ResizeObserver` per al `padding-top` de `main`: exposar-la també com a variable CSS (`--header-h` a `:root`) i usar-la a `.flash-screen { top: var(--header-h) }`. Treure `inset: 0` i el z-index que la posa per sobre de la capçalera.
- El botó **⚡ Flash queda marcat com a actiu** a la barra mentre la pantalla és oberta (classe `active`; estil: el mateix tractament que un botó premut, amb el color de Flash).
- Si es prem **un altre botó** de la barra amb Flash obert: es tanca Flash (guardant l'estat) i s'executa aquell botó com sempre. Tornar a prémer ⚡ amb Flash obert el tanca.
- El ✕ propi de Flash es pot treure (ja no cal: la barra fa de sortida); el `‹ Menú` es manté.
- Els colors de Flash (`--flash-*`) es mantenen dins la seva àrea. La capçalera no canvia de color.

## 4. Tests

- Ampliar `server/test/flash.test.ts`: migració de prefs, color/estat de la barra de temps, que el temps esgotat produeix el mateix resultat que una revelació, i que el comptador de ronda compta les reencuades.
- Passar **tots** els `server/test/*.test.ts` amb `node --experimental-strip-types`.
- Prova amb jsdom (com a la v0) del flux: punts de ronda, temps esgotat ⇒ passa sola, capçalera visible i ⚡ actiu, un altre botó tanca Flash.

## 5. Criteris d'acceptació

- [ ] Durant la ronda es veu `Paraula N de M` i els punts de colors; `sabudes` ja no hi surt.
- [ ] El resum mostra sabudes abans → després i "a mig camí".
- [ ] Temps per paraula 10/20/30/off; en esgotar-se, fallada + resposta + passa sola en 2 s.
- [ ] La capçalera FlowEd és visible a sobre de Flash; ⚡ actiu; un altre botó tanca Flash i fa la seva acció.
- [ ] Res de `data/` ni de `fluent-vocab` tocat. Tests en verd.

## 6. Afegit: traça al xat (continuïtat)

Decisió (2026-10-16): Flash es queda a la zona del xat amb la capçalera visible (§3). A més, en **tancar Flash després d'haver acabat almenys una ronda**, s'afegeix al xat (`#messages`) una línia de resum, p. ex. `⚡ Flash · Família — 8/10 a la primera · sabudes 2/12` (una per sessió de Flash; si se n'han fet diverses rondes, el total).

- És **només visual i local**: un element DOM amb classe pròpia (`flash-trace`), estil discret (mateix to que els xips de comanda). **No** s'envia a l'agent, no passa per `send()`, no es desa enlloc; si es recarrega la pàgina, desapareix.
- No ha de confondre el codi que llegeix l'últim missatge del tutor / la targeta d'exercici (comprovar que `#current-q` i el seguiment de l'exercici l'ignoren).
- Criteri: [ ] en sortir de Flash amb almenys una ronda feta apareix la línia al xat i no es genera cap petició al servidor.
