# Fluent — pla de proves per a l'actualització

**Estat:** ⏳ **cap prova executada encara.** · **Creat:** 2026-09-13 ·
**Per a:** railab (ara) i rapve (quan hi facis l'actualització).

Tot el que hi ha aquí s'ha verificat només amb tests automàtics
(`python3 -m unittest discover -s tests` → 120/120, `tsc --noEmit` net) i amb
proves sobre perfils **sintètics**. Res s'ha executat contra un model real ni
contra un perfil viu. Aquest document és la llista del que cal comprovar quan
el sistema estigui engegat.

**Com fer-lo servir:** marca `[x]` el que passi, escriu el que no passi a
"Incidències" al final, i afegeix blocs nous a mesura que hi hagi canvis. Ordre
recomanat: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 10 (migració) → 11 (alta d'alumne) → 12
(decaïment) → 13 (llargada de sessió), i deixar 7 (streaming) per al final.

**Perfil de proves.** Els permesos són **`demo-en`** i **`test-en`** — tots dos
es poden escriure. **Mai `alex-en` ni `sam-en`.** Tria'n un i exporta'l una
vegada; totes les comandes d'aquest document el fan servir:

```bash
cd ~/projects/fluent_dev2
export PERFIL=demo-en          # o test-en, el que facis servir
```

Si `$PERFIL` no existeix encara:

```bash
scripts/new-user.sh "$PERFIL" --port 4199
```

Quan una prova digui "la web de `$PERFIL`", és la instància d'aquell perfil (el
seu port surt a `config/fluent.json` → `webs`, o el que li donis amb `--port`).

**Les comprovacions es fan amb un sol script**, `scripts/fluent-check.py`, que
només llegeix. Substitueix els fragments de Python que abans hi havia aquí (i
que peten en enganxar-los, perquè la indentació del document entra dins del
codi):

```bash
cd ~/projects/fluent_dev2
python3 scripts/fluent-check.py all "$PERFIL"   # tot d'un cop
python3 scripts/fluent-check.py sm2 "$PERFIL"   # o una cosa concreta
```

Comprovacions: `profile` · `sm2` · `patterns` · `mastery` · `records` ·
`metrics` · `sessions` · `all`. Amb `--dir <ruta>` en comptes de l'id del
perfil, si el tens en un altre lloc.

---

## Abans de res: què està dient el tutor de debò

Tres coses de l'app depenen que el **model** faci una cosa concreta a cada torn,
i si no la fa, les tres fallen **en silenci**:

| Es veu com... | Depèn de... |
|---|---|
| L'indicador `✏️ 0/12` no es mou | la crida `fluent_record_answer` |
| El comptador `🔁` de repàs no es mou | la mateixa crida, amb `item_id` |
| No surt cap botó 🔊 | l'etiqueta `Correct version:` o un `[[say]]` |

Des de fora sembla que l'app estigui trencada. Abans de perdre vint minuts
buscant "l'exercici adequat", mira què escriu el tutor:

```bash
python3 scripts/fluent-check.py sortida "$PERFIL"
```

Treu els **tres últims missatges del tutor literals**, i sota de cada un què en
detecta l'app. Fes-ho després de qualsevol sessió en què alguna cosa no es
mogui, i **enganxa'm la sortida sencera**: amb això es veu si el problema és del
model o del codi, sense endevinar.

---

## 0. Preparació i regressió mínima

- [ ] **0.1 La configuració es resol com toca**
```bash
cd ~/projects/fluent_dev2 && python3 scripts/fluent-config.py --json
```
  *Esperat:* surt el port del deep, el model, les webs i `FLUENT_STREAM: "0"`.
  Els valors han de coincidir amb el que hi ha a `.env` (l'`.env` mana sobre
  `config/fluent.json`).

- [ ] **0.2 El pla d'arrencada no ha canviat**
```bash
scripts/fluent-start.sh --dry-run --yes
```
  *Esperat:* la línia `Pla: deep=… :12322 (backend=native, CUDA …)` igual que
  abans del canvi. Si diu una altra cosa, la capa nova de configuració està
  guanyant on no toca.

- [ ] **0.3 Reinici real de les webs** (el codi del servidor ha canviat; els
  prompts es llegeixen a cada torn, però el servidor no)
```bash
scripts/fluent-stop.sh --webs-only
scripts/fluent-start.sh --webs-only --yes
```
  *Esperat:* les tres webs tornen a pujar. Al log de cada instància
  (`/tmp/fluent-web-<port>.log`) hi ha d'haver ara una línia nova:
  `[Fluent] streaming: off`.

- [ ] **0.4 Una sessió normal funciona** — entra a la web de `$PERFIL`, fes
  `/fluent-learn` i respon 3 exercicis.
  *Esperat:* el tutor saluda, presenta un exercici cada cop, i el feedback surt
  amb el format de sempre. Cap missatge d'error a la conversa.

---

## 1. El tutor ja no toca infraestructura (lot S1+S2+S3)

- [ ] **1.1 Cap ordre denegada**
```bash
grep -c "bash denied" /tmp/fluent-web-*.log
```
  *Esperat:* `0` a totes. Abans, els skills manaven una forma de `read-db.py`
  que l'allowlist rebutjava.

- [ ] **1.2 El tutor no intenta persistir** — al final de la sessió 0.4, revisa
  el log.
  *Esperat:* cap intent de `persist-session.py` ni de `update-db.py` des del
  model; sí que hi ha d'haver les línies `[Fluent] 📝 …` (Capa A) després de
  cada torn.

- [ ] **1.3 L'estat no es reinjecta** — dins de la mateixa sessió, prem un
  segon botó de pràctica (p. ex. Vocabulary després de Surprise me).
  *Esperat:* el tutor continua sense tornar a saludar. Al log, la línia `⏱ turn`
  de la segona comanda ha de tenir **menys** `prompt tok` dels que tindria amb
  el bloc d'estat repetit (compara-la amb la primera).

---

## 2. Renombrat `.opencode/` → `prompts/`

- [ ] **2.1 El servidor troba els prompts** — ja ho cobreix 0.4: si
  `prompts/agents/learner.md` no es llegís, el tutor respondria sense personalitat
  ni regles (i no fallaria!). Fixa't que **saluda pel nom i en la llengua
  objectiu**.

- [ ] **2.2 El canvi de perfil segueix funcionant**
```bash
python3 scripts/list-profiles.py
```
  *Esperat:* llista els perfils. (És la ruta nova de l'allowlist.)

- [ ] **2.3 El mode arxivat avisa clarament**
```bash
scripts/fluent-web.sh --web --port 4097
```
  *Esperat:* error explicant que `--web` està arxivat i que cal `--app`. **No**
  ha d'arrencar res.

- [ ] **2.4 No queda res orfe**
```bash
ls obsolet/opencode-runtime/   # dot-opencode, opencode.json, fluent-opencode-free.sh
ls prompts/agents prompts/commands
```

---

## 3. Persistència: el que abans s'esborrava (P0-6)

Aquesta és **la prova més important**: fins ahir, tancar una sessió esborrava
els patrons d'error d'aquella sessió.

- [ ] **3.1 Fotografia abans**
```bash
python3 scripts/fluent-check.py patterns "$PERFIL"
```
  *Apunta el `total`.*

- [ ] **3.2 Fes una sessió amb errors deliberats** (respon malament 2-3 cops) i
  **tanca-la** amb el botó de tancar (o deixa passar 30 min).

- [ ] **3.3 Fotografia després** — la mateixa comanda que 3.1.
  *Esperat:* el nombre de patrons ha **pujat**, i els nous hi segueixen sent
  després del tancament. Si baixa o torna al valor inicial, la Capa B torna a
  esborrar.

- [ ] **3.4 Un sol fitxer de resultats, amb el nom correcte**
```bash
ls ~/.fluent/"$PERFIL"/results/
```
  *Esperat:* `<nom>-fluent-learn-session-XXX.md`, on `<nom>` és el nom de pila
  de l'alumne en minúscules. **No** ha d'aparèixer cap fitxer que comenci per
  `None-`.

- [ ] **3.5 La Capa B no es repeteix en bucle** — deixa el servidor engegat 5
  minuts després de tancar la sessió i mira el log.
  *Esperat:* `✅ Capa B completed` apareix **una sola vegada** per sessió. Si
  apareix cada minut, el marcador durable no s'està escrivint.

---

## 4. Repetició espaiada (el bloc + els registres)

Recorda el punt de partida: **tots els ítems tenien `repetitions: 0`**.

- [ ] **4.1 Estat abans**
```bash
python3 scripts/fluent-check.py sm2 "$PERFIL"
```

- [ ] **4.2 Fes `/fluent-review`** i respon bé 2-3 ítems de la cua.

- [ ] **4.3 Estat després** — la mateixa comanda que 4.1.
  *Esperat:* algun ítem amb `repetitions >= 1`, `interval_days > 1` i la cua
  repartida (`tomorrow` o `this_week` deixen de ser 0).

- [ ] **4.4 El bloc no es veu a la conversa** — durant 4.2, mira el xat.
  *Esperat:* enlloc no apareix `fluent:review_results` ni un bloc de codi amb
  JSON. Si es veu, `stripMachineBlocks` no s'aplica.

- [ ] **4.5 Els registres estructurats existeixen**
```bash
python3 scripts/fluent-check.py records "$PERFIL"
```
  *Esperat:* el nombre de registres i un resum de l'últim (nota, correccions i,
  si venia de la cua, `item_id` i qualitat).

  **Si diu "encara no n'hi ha cap", no és un error**: el directori `.records/`
  el crea el servidor **nou** el primer cop que el tutor qualifica una resposta.
  Un perfil que no ha tingut cap sessió des del reinici (0.3) encara no en té —
  i els perfils antics, com `demo-en`, no en tindran fins que hi facin una
  sessió. Ordre: reiniciar → fer una sessió → mirar això.

- [ ] **4.6 El model no s'entrebanca amb l'eina**
```bash
grep -c "REJECTED" /tmp/fluent-web-*.log
```
  *Esperat:* pocs o cap. Si n'hi ha molts, mira **quin** motiu: si és
  "unknown category", cal afinar el prompt; si és "item_id not in queue", el
  model se'ls inventa i cal insistir-hi al skill.

- [ ] **4.7 Les categories arriben variades**
```bash
python3 scripts/fluent-check.py patterns "$PERFIL"
```
  *Esperat:* més d'una categoria. Si tot és `grammar`, la taxonomia torna a
  col·lapsar.

---

## 5. Contingut dels skills

- [ ] **5.1 Res de neerlandès** — durant qualsevol sessió en anglès, cap
  paraula ni capçalera en neerlandès (`Vraag`, `Hallo`, `omdat`…). Era el
  símptoma de les plantilles amb idioma fix.

- [ ] **5.2 Identitat de llengua** — el tutor ha de dir "català" (no
  "castellà") quan parli de la llengua nativa, i no barrejar-hi paraules
  castellanes.

- [ ] **5.3 Escriptura: les correccions arriben a la BD**
  Fes `/fluent-writing`, escriu un text amb 2-3 errors clars, i després:
```bash
python3 scripts/fluent-check.py patterns "$PERFIL"
```
  *Esperat:* hi apareixen patrons nous. Abans, les sessions d'escriptura en
  perdien el 100%.

- [ ] **5.4 No repetir** — dins d'una sessió llarga, cap paraula ni escenari
  repetit.

---

## 6. Mètriques i context

- [ ] **6.1 El fitxer de mètriques creix**
```bash
python3 scripts/fluent-check.py metrics "$PERFIL"
```
  *Esperat:* una línia per torn, amb tokens i temps plausibles. **Apunta el
  màxim de `prompt_tokens`**: és el número que decidirà si cal podar
  l'historial (el límit és 32768).

- [ ] **6.2 Els tokens creixen amb la sessió, no exploten** — mira si el
  `prompt_tokens` d'una sessió de 20 exercicis s'acosta al límit.

---

## 7. Streaming (experimental, deixar per al final)

**No l'activis a les webs dels nens fins que aquesta secció passi.**

**Com funciona, i com se'n surt** (les preguntes de la revisió):

- **Quan acaba un *stream*?** Al final de **cada torn**, no de la sessió. El
  model escriu, el servidor tanca aquell tros de text i el desa; el torn
  següent obre un de nou. Si pel mig el model crida una eina, el tros es tanca
  abans de la crida i se'n obre un altre després.
- **El resum de sessió** no canvia gens: és un torn més. Amb *streaming* el
  veus escriure's, i quan acaba queda igual que sempre. `/fluent-end` i el botó
  de tancar funcionen igual.
- **Com se surt del mode *streaming*:** és una opció **de la instància**, no de
  la conversa. No hi ha cap manera de desactivar-lo des del xat: s'atura la
  instància i es torna a engegar sense la variable.

```bash
scripts/fluent-web.sh --stop --port 4199            # sortir del mode stream
scripts/fluent-web.sh --app "$PERFIL" --port 4199   # el mateix perfil, sense stream
```

- **Per deixar-lo posat de manera permanent** (quan et convenci), a
  `config/fluent.json` → `"server": { "stream": true }`; així val per a totes
  les instàncies sense haver de recordar la variable.
- **Si el model no accepta `stream:true`**, l'error puja a `agent.ts`, que ja
  sap caure al deep i deixar l'avís al xat: no et quedes sense sessió.

- [ ] **7.1 Instància de proves a part**

  ⚠ **Atura primer la instància normal d'aquest perfil.** Dos servidors sobre el
  mateix perfil obren la mateixa BD de sessions i el mateix `session-draft.json`:
  no es corromp (SQLite va en WAL), però les sessions s'entrellacen i el
  *sweeper* de tots dos pot intentar finalitzar la mateixa sessió. Un perfil,
  una instància.

```bash
scripts/fluent-web.sh --stop --port <el port normal de $PERFIL>
FLUENT_STREAM=1 scripts/fluent-web.sh --app "$PERFIL" --port 4199
```
  *Esperat:* al log, `[Fluent] streaming: on (FLUENT_STREAM)`.

- [ ] **7.2 El text apareix progressivament** en lloc de cop.

- [ ] **7.3 Les eines segueixen funcionant** — fes `/fluent-writing` (que crida
  `fluent_deep_evaluate`) i comprova que l'avaluació arriba i que el xip d'eina
  surt. *Aquest és el risc real del streaming:* els `tool_calls` arriben
  fragmentats i s'han de recompondre.

- [ ] **7.4 La transcripció del disc coincideix amb el que s'ha vist** — tanca
  i torna a obrir la sessió: el text ha de ser sencer, no buit ni duplicat.

- [ ] **7.5 Els registres i la Capa A segueixen funcionant** amb streaming
  actiu (repeteix 4.5 en aquesta instància).

- [ ] **7.6 Atura la instància de proves i torna a deixar la normal**
```bash
scripts/fluent-web.sh --stop --port 4199
scripts/fluent-start.sh --webs-only --yes
```

---

## 8. Multi-usuari (P0-2)

- [ ] **8.1 Cada perfil veu el seu resum** — amb les tres webs engegades:
```bash
for p in 4100 4101 4102; do
  echo "--- $p"; curl -s -u "opencode:$(cat ~/.fluent/alex-en/.web-password)" \
    "http://127.0.0.1:$p/api/fluent/summary" | head -c 200; echo; done
```
  (Fes servir la contrasenya de cada perfil per al seu port.)
  *Esperat:* cada port retorna les dades del seu alumne i una ratxa real, no
  sempre `1` ni sempre les de `nes`.

---

## 9. Coses que sabem que NO funcionen (confirmar que fallen com esperem)

- [x] ~~**9.1 `/fluent-setup` a la web**~~ — **arreglat** el 2026-09-13 amb
  l'eina `fluent_setup_profile`. Es prova al bloc 11.
- [ ] **9.2 `/fluent-progress` per comanda** — a la web el botó 📊 obre el
  panell del client sense passar pel model; la comanda només té sentit fora de
  la web.
- [ ] **9.3 `fluent-session-analyzer`** — no pot llegir els fitxers de sessió
  des de la web (no hi ha eina de lectura). Documentat com a S4.

---

## 10. Migració de la BD de sessions (ruta nova)

> **Estat: la còpia ja s'ha fet a railab** (2026-09-13, manualment). Les
> comprovacions d'aquest bloc encara estan **per fer**, aquí i a rapve.

La transcripció de cada alumne passa de
`~/.fluent/<id>/.opencode/opencode/opencode.db` a
`~/.fluent/<id>/sessions/sessions.db`. **L'app llegeix les dues** (la nova
primer), i la vella **no s'esborra mai**: la versió anterior hi continua
escrivint. Un cop copiada, les dues deixen de ser les mateixes dades — copia amb
la instància aturada.

- [ ] **10.1 Assaig en sec, tots els perfils**
```bash
cd ~/projects/fluent_dev2 && python3 scripts/migrate-sessions-db.py --all --dry-run
```
  *Esperat:* per a cada perfil, la ruta antiga i els comptadors
  (sessions/missatges/parts). Res no s'escriu.

- [ ] **10.2 Migrar un perfil de prova primer**
```bash
scripts/fluent-web.sh --stop --port 4199    # si en tens una engegada
python3 scripts/migrate-sessions-db.py --profile "$PERFIL"
ls ~/.fluent/"$PERFIL"/sessions/
```
  *Esperat:* `✅ copiada`, només `sessions.db` al directori nou (cap `.tmp`), i
  l'antiga encara existeix.

- [ ] **10.3 El servidor fa servir la nova** — arrenca la instància i mira el log.
  *Esperat:* `[Fluent] sessions : /home/albert/.fluent/<perfil>/sessions/sessions.db`
  **sense** el sufix `(legacy path)`.

- [ ] **10.4 Un perfil no migrat segueix funcionant** — mira el log d'un perfil
  que encara no hagis copiat.
  *Esperat:* `(legacy path)` i, a sota, la comanda exacta per migrar-lo. La
  sessió ha de funcionar igual.

- [ ] **10.5 La sessió continua on era** — obre la web del perfil migrat.
  *Esperat:* l'historial hi és. Si surt buit, la còpia no s'ha fet bé: atura,
  torna a copiar amb `--force` i revisa els comptadors.

- [ ] **10.6 Migrar la resta** (amb les instàncies aturades)
```bash
scripts/fluent-stop.sh --webs-only
python3 scripts/migrate-sessions-db.py --all
scripts/fluent-start.sh --webs-only --yes
```
  *Esperat:* cap `(legacy path)` als logs.

- [ ] **10.7 La ruta antiga segueix intacta** — `ls ~/.fluent/<id>/.opencode/opencode/`
  encara ha de mostrar `opencode.db`. No l'esborris fins que estiguis segur.

---

## 11. Alta d'un alumne nou (ara la fa l'administrador)

Abans la web enviava l'alumne a `/fluent-setup` i li feia omplir un formulari a
mitja lliçó. Qui és algú i com se li pacen les sessions és decisió del
propietari, així que ara la donada d'alta és una comanda de terminal i l'alumne
no hi entra mai.

- [ ] **11.1 Crea el perfil**
```bash
cd ~/projects/fluent_dev2
scripts/new-user.sh prova-en --port 4198
python3 scripts/fluent-check.py profile prova-en
```
  *Esperat:* `setup_complete : False` i la línia `plantilla sense omplir` amb
  els `{...}` encara posats.

- [ ] **11.2 Omple'l des del terminal**
```bash
python3 scripts/fluent-profile.py prova-en \
  --name Prova --native Catalan --target English \
  --level A2 --goal B1 --minutes 20 --session-length 8
```
  *Esperat:* imprimeix el resum amb `setup_complete  True` i surt amb codi 0.

- [ ] **11.3 Ha quedat desat de debò**
```bash
python3 scripts/fluent-check.py profile prova-en
ls ~/.fluent/prova-en/ | grep backup
```
  *Esperat:* dades reals, `setup_complete : True`, `plantilla sense omplir:
  cap ✅` i un `learner-profile.json.backup-…`.

- [ ] **11.4 Es pot retocar després sense tornar-hi tot**
```bash
python3 scripts/fluent-profile.py prova-en --session-length 6 --stop soft
python3 scripts/fluent-profile.py prova-en --show
```
  *Esperat:* només canvien els dos valors; la resta es manté.

- [ ] **11.5 Refusa el que no té sentit**
```bash
python3 scripts/fluent-profile.py prova-en --level Z9 ; echo "codi=$?"
```
  *Esperat:* error amb la llista A1…C2 i `codi=1`. El perfil **no** s'ha tocat.

- [ ] **11.6 La web arrenca directament a practicar** — obre
  `scripts/fluent-web.sh --app prova-en --port 4198`.
  *Esperat:* comença amb `/fluent-learn`. **No** hi ha cap botó de setup i **no**
  surt cap entrevista.

- [ ] **11.7 Un perfil sense configurar no atrapa l'alumne** — crea'n un altre
  amb `new-user.sh` i obre'l sense passar per `fluent-profile.py`.
  *Esperat:* un avís curt dient que el perfil encara no està configurat i que ho
  fa l'administrador. Cap formulari.

- [ ] **11.8 Neteja** — atura la instància quan acabis.

---

## 12. Decaïment (P2)

Costa de provar en una tarda: depèn de dies. El que sí es pot comprovar avui:

- [ ] **12.1 Un skill inactiu baixa** — mira un perfil real amb alguna habilitat
  sense practicar fa setmanes, després d'una sessió nova:
```bash
python3 scripts/fluent-check.py mastery "$PERFIL"
```
  *Esperat:* les habilitats practicades avui tenen `mastery_level ==
  mastery_level_earned`; les que fa més de 35 dies que no es toquen, un nivell
  menys per cada 21 dies. **Cap ha de baixar de 1.**

- [ ] **12.2 No es compon** — passa dues sessions seguides sense tocar aquella
  habilitat: el nivell ha de ser el mateix les dues vegades (el decaïment es
  calcula dels dies, no del valor anterior).

- [ ] **12.3 Els patrons d'error ordenen per actualitat** — a l'estat que
  precarrega la comanda, els `top_weak_patterns` han de portar `days_since_seen`
  i un d'antic no ha de sortir per davant d'un de recent amb menys freqüència.

- [ ] **12.4 Si el trobes massa agressiu**, ajusta'l per alumne a
  `learner-profile.json` → `preferences.mastery_decay`, o apaga'l amb
  `{"step_days": 0}`.

---

## 13. On ets dins la sessió (indicador + tancament)

Dues coses: l'alumne **veu on és**, i el tutor sap quan proposar tancar. El
número no el porta el model — el servidor compta les respostes registrades.

- [ ] **13.1 Mira el número del perfil**
```bash
python3 scripts/fluent-check.py profile "$PERFIL"
```
  *Esperat:* la línia `exercicis/sessió`. Si diu `(per defecte 12)`, és que el
  perfil no el porta escrit i s'usa el 12.

- [ ] **13.2 Posa'n un de curt per provar-ho ràpid** — edita
  `~/.fluent/$PERFIL/learner-profile.json` → `"preferences": { "session_length": 4 }`
  i reinicia la instància d'aquell perfil.

- [ ] **13.3 L'indicador es mou** — prem 🎲 i respon un parell d'exercicis.
  *Esperat:* a la capçalera surt `✏️ 1/4`, `✏️ 2/4`… amb la barra omplint-se.
  Passant-hi el ratolí, el percentatge.

  **Si es queda a `0/4`** — que és el que passava — no cal investigar res més:
```bash
python3 scripts/fluent-check.py sortida "$PERFIL"
python3 scripts/fluent-check.py metrics "$PERFIL"
```
  El comptador surt dels registres de `fluent_record_answer`. Si el tutor no
  crida l'eina, l'indicador **no es pot moure**: no és un bug de la barra, és que
  no hi ha res a comptar. Les dues comandes ho diuen en una línia; enganxa-les.

- [ ] **13.4 En recarregar, no es perd** — recarrega la pàgina a mitja sessió.
  *Esperat:* l'indicador torna amb el mateix número.

- [ ] **13.5 Al límit, ofereix** — arriba als 4.
  *Esperat:* el tutor **pregunta** si vols el resum o un parell més (mode `soft`,
  el de defecte), no et talla. Al log: `🏁 session … : 4 graded`. Si tries
  continuar, no ho ha de tornar a preguntar.

- [ ] **13.6 No en parla** — el tutor no ha d'esmentar cap instrucció ni cap
  límit del sistema: només ho proposa amb naturalitat.

- [ ] **13.7 Mode dur, si el vols** — posa `"session_stop": "hard"` a
  `preferences` i reinicia: en arribar al número ha de tancar directament.

- [ ] **13.8 Escriptura i lectura no es tallen** — fes `/fluent-writing` amb el
  límit encara a 4.
  *Esperat:* no es talla a mitges (és un sol escenari per disseny; el mateix amb
  un text de lectura), i l'indicador surt sense objectiu (`✏️ 2`).

- [ ] **13.9 Deixa el número que vulguis** per a cada alumne (`session_length`),
  o `0` per apagar el tancament. L'indicador seguirà comptant.

### 13b. El repàs va abans del contingut nou (porta SM-2)

L'única regla d'ordre que el servidor pot comprovar de debò: si la sessió
comença amb 🎲 o 🔁, els ítems vençuts d'avui es fan primer. Com a molt la porta
ocupa **mitja sessió** (amb `session_length` 8 → 4 ítems), perquè un endarreriment
gran no es mengi el dia sencer.

- [ ] **13b.1 Mira quants en deuen avui**
```bash
python3 scripts/fluent-check.py sm2 "$PERFIL"
```
  *Esperat:* el recompte de `today`. Si és 0, la porta no s'activa — apunta-ho i
  salta a 13b.6.

- [ ] **13b.2 Comença amb 🎲** i fixa't en la capçalera.
  *Esperat:* `🔁 0/N · ✏️ 0/M`. El tooltip diu "el repàs va abans del contingut
  nou".

- [ ] **13b.3 El comptador de repàs es mou** — respon els exercicis de repàs.
  *Esperat:* `🔁 1/N`, `🔁 2/N`… **Si no es mou**, el tutor no està passant
  l'`item_id` a `fluent_record_answer` (mira `records` al bloc 4.5) — és el
  mateix símptoma que feia que l'SM-2 no avancés.

- [ ] **13b.4 Demana-li saltar-se'l** — a mitja porta, digues "avui vull escriure".
  *Esperat:* respon amablement que primer acaba el repàs d'avui i t'ofereix el
  següent ítem. **No** ha d'esmentar cap instrucció ni cap "regla del sistema".

- [ ] **13b.5 En acabar-lo, s'obre** — completa els N ítems.
  *Esperat:* `🔁 N/N` es queda apagat i el tutor passa a contingut nou sense que
  li ho demanis.

- [ ] **13b.6 Triar el dia sí que es pot** — sessió nova començant directament
  amb 📝 Writing (o 📚 Vocabulary).
  *Esperat:* **cap** indicador `🔁` — començar en una habilitat concreta és
  l'alumne dient què vol avui, i això s'accepta. Si després prems 🎲 dins la
  mateixa sessió, la porta segueix sense aparèixer.

- [ ] **13b.7 Es pot apagar per alumne**
```bash
python3 scripts/fluent-profile.py "$PERFIL" --review-gate off
```
  i reinicia la instància. *Esperat:* cap `🔁`, ni amb 🎲.
  Torna-ho a posar amb `--review-gate on` quan acabis.

### 13c. El botó d'acabar

- [ ] **13c.1 El botó hi és** — 🏁 **Acaba** a la barra de dalt.

- [ ] **13c.2 Tanca de debò** — prem-lo a mitja sessió.
  *Esperat:* resum (exercicis, encerts, patrons) i comiat. Al log, la Capa B
  (`persist-session.py`) s'executa tot seguit.

- [ ] **13c.3 No perd res** — després del resum:
```bash
python3 scripts/fluent-check.py all "$PERFIL"
```
  *Esperat:* els patrons i els ítems SM-2 de la sessió hi són (és el bug P0-6:
  la Capa B esborrava la Capa A).

---

## 14. Només a rapve (4060 Ti, backend Docker)

- [ ] **14.1 `cp .env.rapve .env`** i `python3 scripts/fluent-config.py --json`
  → el backend ha de sortir `docker` i el port el que toqui.
- [ ] **14.2 `scripts/fluent-start.sh --dry-run --yes`** → el pla ha de dir
  `backend=docker`.
- [ ] **14.3 Arrencada real** → el contenidor puja, `/health` respon, i
  `/tmp/fluent-deep-docker.state` existeix.
- [ ] **14.4 `scripts/fluent-stop.sh`** → el contenidor s'atura i, si hi ha
  `FLUENT_DEFAULT_MANAGER`, el model per defecte torna al port.

---

## 15. Veu: escoltar la frase (TTS)

Només sortida de veu. L'entrada (micròfon) no hi és i no hi serà fins que hi
hagi TLS — vegeu `ARQUITECTURA.md` §C.3-13b.

**Abans de res: no hi ha res instal·lat.** Amb la configuració tal com ve, no ha
de sortir cap botó 🔊 enlloc. Això és el primer que cal comprovar.

- [ ] **15.1 Apagat, no es nota** — obre la web sense instal·lar res.
```bash
python3 scripts/fluent-check.py tts "$PERFIL"
```
  *Esperat:* `enabled : False`, `veus : cap`, i `aquest perfil … sense veu`. A la
  web, **cap** botó 🔊 enlloc i cap error a la consola del navegador.

- [ ] **15.2 Instal·la piper i una veu** (cal internet en aquesta màquina)
```bash
cd ~/projects/fluent_dev2
scripts/fluent-tts.sh install en_GB-alba-medium
scripts/fluent-tts.sh status
```
  *Esperat:* binari ✅, la veu llistada, i `enabled: True` amb
  `English: …/en_GB-alba-medium.onnx`. Baixa ~80 MB. Comprova-ho també amb
  `python3 scripts/fluent-check.py tts "$PERFIL"` → ha de dir `sonarà 🔊`.

- [ ] **15.3 Prova-ho sense la web**
```bash
scripts/fluent-tts.sh say "Good morning, how are you today?"
```
  *Esperat:* escriu un `.wav`. Escolta'l (`aplay <ruta>`). Si aquí no sona, no
  cal continuar: el problema és de piper, no de Fluent.

- [ ] **15.3b El servidor no depèn del teu `.bashrc`** — piper porta les seves
  pròpies `libespeak-ng` i `libonnxruntime` al costat del binari, i cal
  apuntar-hi el carregador. Si ho vas arreglar al `.bashrc`, funciona al
  terminal però **no** el dia que el servidor l'arrenqui systemd o un cron. Ara
  ho fa el codi (`ttsEnv()` a `tts.ts` i `piper_env` a l'script). Comprova-ho
  **sense** el teu perfil de shell:
```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin bash -lc 'cd ~/projects/fluent_dev2 && scripts/fluent-tts.sh status'
```
  *Esperat:* la línia `(corre sense dependre del teu .bashrc ✅)`. Si surt
  l'avís, enganxa'm la sortida de `ldd` que et proposa.

- [ ] **15.4 Reinicia la instància** del perfil i recarrega la web.

- [ ] **15.5 El botó de l'exercici** — fes `/fluent-learn`.
  *Esperat:* 🔊 a la dreta de la capçalera "✏️ Exercici". Prem-lo: sona la
  pregunta en anglès.

- [ ] **15.6 El botó de la correcció** — falla un exercici a posta.
  *Esperat:* 🔊 al final del bloc "Correct version". Prem-lo: sona **només la
  frase correcta**, sense l'etiqueta ni l'explicació en català. Aquest botó no
  depèn de cap instrucció al model: la frase corregida és en la llengua meta per
  definició.

- [ ] **15.6b Les frases marcades pel tutor** — el tutor pot marcar qualsevol
  frase en llengua meta amb `[[say]]…[[/say]]` i surt subratllada amb un 🔊.
  *Esperat:* si en marca alguna, es veu i sona. Si no en marca cap, **no passa
  res** — aquesta és la gràcia: oblidar-se'n costa un botó, no una lectura amb
  l'accent equivocat. El que **mai** ha de passar és veure `[[say]]` escrit a la
  pantalla; si ho veus, apunta-ho.

- [ ] **15.6c No llegeix mai la llengua nativa** — no cal buscar cap exercici
  concret: no pots demanar-li al tutor que en tregui un de determinat. Simplement
  **mentre facis les altres proves**, si en algun moment veus un 🔊 al costat de
  text en català, prem-lo i apunta-ho. És el pitjor error possible d'aquesta
  funció.
  *Per disseny no hauria de passar:* els 🔊 només surten sobre la frase de
  `Correct version` i sobre el que el tutor marqui amb `[[say]]`. Si en veus un
  en un altre lloc, ja és una incidència encara que soni bé.

- [ ] **15.7 No llegeix el que no ha de llegir** — escolta una correcció que
  porti un aclariment entre parèntesis en català i una nota `8/10`.
  *Esperat:* no diu ni el parèntesi, ni la nota, ni cap emoji. **Si ho diu**,
  apunta la frase sencera: és el filtre (`speakableText`) el que falla.

- [ ] **15.8 La segona vegada és instantània** — prem el mateix botó dos cops.
```bash
python3 scripts/fluent-check.py tts "$PERFIL"
```
  *Esperat:* el segon cop sona de seguida, i la línia `cau` compta un `.wav` per
  frase. La capçalera `x-fluent-cached: 1` a la pestanya Xarxa del navegador ho
  confirma.

- [ ] **15.9 No es menja la GPU** — mentre sona, mira `nvidia-smi`.
  *Esperat:* piper **no** hi surt. Si hi surt, algú ha compilat una build CUDA i
  competirà amb el model deep.

- [ ] **15.10 No es menja el disc** — el límit és `cache_max_mb` (200 per
  defecte). Baixa'l a `1` a `config/fluent.json`, reinicia, fes sonar unes
  quantes frases i comprova que el directori no creix indefinidament.

- [ ] **15.11 Una llengua sense veu no inventa** — si algun perfil aprèn una
  llengua per a la qual no has instal·lat veu, aquell perfil no ha de mostrar
  cap 🔊 (i mai ha de sonar amb accent anglès).

---

## 16. Comandes i menús (arran de la incidència 1)

- [ ] **16.1 Cap comanda a la vista** — entra amb la cua de repàs buida (o prem
  🔁 quan no en deguis cap).
  *Esperat:* el missatge convida a prémer botons (🎲 / 📚 / 📊) i **enlloc** surt
  cap `/fluent-…`. Si el model se'n inventa una, s'ha de veure el nom del botó
  en negreta, no la comanda.

- [ ] **16.2 El menú no és un exercici** — el mateix missatge.
  *Esperat:* **cap** etiqueta `✏️ Exercici`, ni cap fons verd d'exercici. El
  mateix amb el menú d'obertura i el de tancament de sessió.

- [ ] **16.3 Els exercicis de debò segueixen marcats** — demana una pràctica.
  *Esperat:* una pregunta real **sí** que porta `✏️ Exercici`. Si s'ha perdut
  la marca, apunta la frase: l'he filat massa fi.

---

## 17. Sessions que s'acaben (arran de les incidències 2 i 3)

- [ ] **17.1 Tornar-hi no reprèn** — fes uns torns, tanca el navegador, espera
  **més de 30 min** i torna a obrir.
  *Esperat:* sessió **nova**, buida. La ratxa i el progrés hi són igualment (són
  a les BD). Al log del servidor no ha de sortir cap `↩ session … reopened`.

- [ ] **17.2 Tornar-hi de seguida sí que reprèn** — tanca i torna a obrir en
  menys de 5 min.
  *Esperat:* la mateixa conversa. No volem trencar una pausa per anar al lavabo.

- [ ] **17.3 Una sessió tancada no es reprèn mai** — prem 🏁 **Acaba** i després
  recarrega.
  *Esperat:* sessió nova.

- [ ] **17.4 El context deixa de créixer**
```bash
python3 scripts/fluent-check.py metrics "$PERFIL"
```
  *Esperat:* el **màxim** de prompt tokens baixa amb les sessions noves i es
  queda ben per sota del límit. Era 51.605 contra un ctx de 32.768 — el model
  truncava per l'esquerra, on hi ha les regles.

- [ ] **17.5 I ara sí, els registres** — respon **un** exercici de debò.
```bash
python3 scripts/fluent-check.py metrics "$PERFIL"
python3 scripts/fluent-check.py records "$PERFIL"
```
  *Esperat:* `fluent_record_answer  1 ok` i un `.records/<ses>.jsonl`. Si
  segueix sense sortir, **ara sí** que el model ignora la instrucció i cal
  reforçar-la — apunta-ho.

---

## 18. Context i VRAM (ja configurat, **falta mesurar-ho**)

`config/fluent.json` ja porta `ctx: 49152` i `kv_type: "q8_0"`. L'aritmètica i
el perquè de 48k i no 64k són a `docs/model-qwen14b-q4.md`. **Res d'això està
mesurat encara.**

- [ ] **18.1 El valor efectiu és el que creus** — `FLUENT_DEEP_CTX` estava
  fixat a 32768 als `.env` i l'`.env` mana sobre el config; s'ha comentat.
```bash
python3 scripts/fluent-config.py --sh | grep -i "DEEP_CTX\|KV_TYPE"
```
  *Esperat:* `49152` i `q8_0`. Si surt 32768, hi ha un `.env` que encara el fixa.

> **Decidit el 13/09 al vespre: `ctx: 32768` + `kv_type: "f16"`** — el de sempre,
> mesurat. El desbordament el resol la poda (bloc 20), no el context. Aquest bloc
> queda com a referència per si algun dia cal pujar: el següent pas natural és
> **36864 amb f16** (~14.600 MiB, ~1,7 GB de marge a la 4060 Ti). El q8_0 només
> fa falta per arribar als 40960 del sostre del model, i només a la 4060 Ti.

- [ ] **18.2 Mesura de partida** — amb el model **aturat**, per saber què hi ha
  ocupat que no sigui nostre.
```bash
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

- [ ] **18.3 Arrenca i mesura**
```bash
scripts/models/llama-deep-14b-q4.sh --stop
scripts/models/llama-deep-14b-q4.sh
nvidia-smi --query-gpu=memory.used --format=csv
```
  *Esperat previst:* **~12.600 MiB** (contra els 13.938 d'abans), i la línia
  d'arrencada ha de dir `ctx 49152, kv q8_0`. **Apunta el número real** — tota
  la taula del document és aritmètica, no mesura.

- [ ] **18.4 El model diu el context que toca**
```bash
curl -s http://127.0.0.1:12322/v1/models | python3 -m json.tool | grep -i ctx
```

- [ ] **18.5 La qualitat no cau** — passa la bateria de
  `docs/model-qwen14b-q4.md` i compara amb el f16. Mira sobretot correccions
  fines i identitat de llengua. **Si es nota, torna a `"kv_type": "f16"` amb
  `"ctx": 36864`** (~14.600 MiB) i prou: el context no era el problema.

- [ ] **18.6 Velocitat — qui triga, el model o nosaltres**
```bash
python3 scripts/fluent-check.py metrics "$PERFIL"
```
  *Esperat:* el bloc `abans/ara` separa el torn sencer del temps **dins** el
  model. Si creix `dins el model`, és el model (context 49152, KV q8_0, prompt
  més gros). Si creix la diferència entre els dos, és codi nostre.
  La KV quantitzada té un cost de càlcul per token (típic 5–15%): és el preu del
  contexte extra, i si no compensa, `kv_type: "f16"` amb `ctx 36864`.

- [ ] **18.6b Velocitat (antic)** — compara el temps per torn amb el que tens apuntat.
```bash
python3 scripts/fluent-check.py metrics "$PERFIL"
```
  *Esperat:* mediana semblant. Si el prefill s'ha encarit molt, apunta-ho.

---

## 20. Context: que no peti i que no s'arrossegui

Mesurat el 13/09 sobre 120 torns reals: de **1,9 s a 19,8 s** per torn, tot dins
el model, amb el prompt passant de 25.650 a 31.946 tokens — i un màxim de
**69.484** contra un context de 40.960, que és el `HTTP 400` que va sortir.

- [ ] **20.1 El límit efectiu és 40960**
```bash
python3 scripts/fluent-config.py --sh | grep -i "DEEP_CTX\|KV_TYPE"
curl -s http://127.0.0.1:12322/v1/models | python3 -m json.tool | grep -i ctx
```
  *Esperat:* `40960` als dos llocs. El 49152 del migdia **no s'aplicava**: és per
  sobre del màxim entrenat de Qwen3-14B i llama.cpp el retallava en silenci.

- [ ] **20.2 La poda actua** — fes una sessió llarga (15+ exercicis) i mira el
  log del servidor.
  *Esperat:* línies `✂ session … : dropped N old message(s) to fit the context`.
  Si no en surt cap i el prompt passa dels 30k, la poda no s'està aplicant.

- [ ] **20.3 Cap torn peta**
```bash
python3 scripts/fluent-check.py metrics "$PERFIL"
```
  *Esperat:* el màxim de prompt tokens **per sota** de 40960. Si surt
  `❌ ALGUN TORN HA PETAT`, apunta-ho.

- [ ] **20.4 I no s'arrossega** — el bloc `abans/ara` de la mateixa comanda.
  *Esperat:* el temps per torn s'estabilitza en comptes de créixer sense aturador.
  No serà pla del tot (el prompt oscil·la), però el 10× ha de desaparèixer.

- [ ] **20.5 Podar no li fa perdre el fil** — després d'una sessió llarga,
  comprova que el tutor segueix sense repetir exercicis.
```bash
cat ~/.fluent/$PERFIL/.daily/lesson-$(date +%F).json
```
  *Esperat:* `covered` segueix creixent i no hi ha repeticions. **Aquesta és la
  prova clau de la poda**: l'historial es retalla, però qui recorda què s'ha
  preguntat és el servidor, no la conversa.

---

## 19. La Lliçó del dia (disseny nou)

Dues coses separades, i aquesta és tota la idea: **la Lliçó té final, l'esforç
del dia no.** Res es bloqueja mai.

- [ ] **19.1 El botó** — 🎓 **Lesson**, el primer de la barra, amb la vora
  destacada i un badge ambre amb el número que queda.
  *Esperat:* el badge pulsa suaument mentre hi hagi feina.

- [ ] **19.2 De què està feta** — la Lliçó són els repassos vençuts, completats
  amb drills de patrons febles fins a **6 com a mínim**.
```bash
python3 scripts/fluent-check.py sm2 "$PERFIL"
```
  *Esperat:* amb 5 ítems vençuts, el badge diu **6**. Amb 0 vençuts, també 6
  (tot drills) — la Lliçó no és mai un gest simbòlic.

- [ ] **19.3 Es buida** — prem 🎓 i fes els exercicis.
  *Esperat:* el badge baixa 6 → 5 → 4… Quan arriba a 0, es torna un ✓ verd uns
  segons i desapareix.

- [ ] **19.4 Res queda bloquejat** — amb el badge encara a 4, prem 📚 Vocab.
  *Esperat:* funciona normal. El badge es queda com estava (els exercicis de
  fora de la Lliçó no la compten, però sí que compten al dia).

- [ ] **19.5 La cara puja** — mira el comptador de la dreta mentre respons.
  *Esperat:* `✏️ 0 😐` → `✏️ 5 🙂` → `✏️ 10 😄` → `✏️ 15 🤩`. Passar de 15 no és
  error: es queda a 🤩.

- [ ] **19.6 Compta el DIA, no la sessió** — tanca el navegador amb 8 fets i
  torna una hora després.
  *Esperat:* segueix dient `✏️ 8`. Abans tornava a 0, que era el que feia que el
  número no volgués dir res.

- [ ] **19.7 Cada 3 lliçons, una d'escriptura o lectura** — la Lliçó reserva un
  exercici per a l'habilitat més abandonada, **dins la mateixa Lliçó** (no és un
  botó a part).
  *Esperat:* a la 3a lliçó, el tutor hi posa un exercici de writing o reading
  sense anunciar-ho com un càstig. El tooltip del botó ho diu: `inclou writing`.
  Només salta si l'habilitat fa 3+ dies que no es toca.

- [ ] **19.6b Sortir i tornar NO recomença** — a mig fer la Lliçó (badge a 2),
  prem 🗣️ Speaking, fes un exercici, i torna a prémer 🎓.
  *Esperat:* **continua** on eres. No torna a saludar, no torna a l'exercici 1,
  i no repeteix res del que ja has fet. El badge segueix a 2.
  *Això era el bug:* recomençava pel primer exercici i, en acabar-lo, donava la
  Lliçó per feta — amb la sisena pregunta sense haver-se vist mai.

- [ ] **19.6c El total no es mou sota els peus** — apunta el badge en començar i
  compara'l a mitja Lliçó.
```bash
cat ~/.fluent/$PERFIL/.daily/lesson-$(date +%F).json
```
  *Esperat:* `total` és el mateix de principi a fi. Es fixa una vegada al dia.
  (Abans es recalculava, i com que respondre un repàs fa que deixi de vèncer, el
  total encongia sol.)

- [ ] **19.7b La Lliçó TANCA** — fes-la sencera fins que el badge arribi a 0.
  *Esperat:* el tutor diu que la lliçó està feta, fa un resum de dues línies i
  et convida a triar botó o plegar. **No presenta cap exercici més.** Si hi
  respons igualment, contesta breu i t'assenyala els botons.
  *Això era el bug:* el badge deia 6 i el tutor anava per l'Exercise 8. En
  acabar-se el compte no rebia cap instrucció i seguia per sempre.

- [ ] **19.7c No repeteix la mateixa forma** — durant la Lliçó, mira els
  enunciats.
  *Esperat:* alterna (reescriure, omplir un buit, traduir, triar entre dues
  formes…). Sortien tots com a "Rewrite this sentence correctly", que avorreix.

- [ ] **19.7c-bis No repeteix el mateix exercici** — fes la Lliçó sencera i
  fixa't si algun enunciat torna a sortir.
```bash
cat ~/.fluent/$PERFIL/.daily/lesson-$(date +%F).json
```
  *Esperat:* el camp `covered` porta la llista del que ja s'ha preguntat avui
  ("a book of english", "where are the park", "i lunch"…), i cap enunciat es
  repeteix. Si el pou de patrons febles s'esgota, el tutor se n'ha d'inventar un
  de nou al nivell de l'alumna, **no** reciclar-ne un.
  *Això era el bug:* "no repeteixis" era una línia a `rules.md`, i amb quatre
  patrons per treballar el model tornava als mateixos tres en bucle.

- [ ] **19.7d El joc lliure no té sostre amagat** — després de la Lliçó, fes 10
  exercicis de 📚 Vocab seguits.
  *Esperat:* no et talla mai. El comptador puja i prou. (Només talla si el
  perfil té `session_stop: "hard"`, que no és el cas per defecte.)

- [ ] **19.8 L'objectiu és configurable**
```bash
python3 scripts/fluent-profile.py "$PERFIL" --daily-goal 15
python3 scripts/fluent-check.py profile "$PERFIL"
```

---

## 21. On són totes les sessions (diagnòstic)

La BD de sessions **no és l'única traça**. Cada sessió tancada deixa un fitxer a
`results/` i una entrada a `session-log.json`. Les tres han de quadrar; si la BD
en té menys, hi ha transcripcions en un altre fitxer.

```bash
for p in alex-en sam-en demo-en; do
  echo "=== $p ==="
  python3 scripts/fluent-check.py historial "$p"
done
```

Si diu **`⚠ FALTEN TRANSCRIPCIONS`**, busca on són:

```bash
ls -la ~/.local/share/opencode/ 2>/dev/null
find ~ -name 'opencode.db' -o -name 'sessions.db' 2>/dev/null | grep -v node_modules
```

L'`opencode` antic desava a un lloc **central compartit** fins que
`fluent-web.sh` va començar a fixar `XDG_DATA_HOME` per perfil. Les sessions
anteriors a aquell canvi són en aquell fitxer únic, barrejades entre alumnes.

> **El que NO s'ha perdut:** les dades d'aprenentatge. Nivell, ratxa, patrons
> d'error, cua SM-2 i mestria viuen a les 6 BD JSON del perfil, i les escrivia la
> Capa A a cada torn. El que faltaria és **el text de la conversa**.

> **I `close-old-sessions.py` no hi té res a veure:** només escriu un flag a la
> metadada. No esborra ni una fila, i deixa còpia `.bak`.

---

## Incidències

| # | Prova | Què ha passat | Notes |
|---|---|---|---|
| 10 | — | `HTTP 400: request (41808 tokens) exceeds the available context size (40960)`. El torn falla i l'alumna rep un error. Abans de petar, 10× més lent (1,9 s → 19,8 s sobre 120 torns). | ✅ Poda de l'historial per pressupost de tokens. Provar al bloc 20. |
| 9 | 18.x | El `ctx: 49152` no s'aplicava mai: Qwen3-14B té el màxim entrenat a 40960 i llama.cpp el retalla. La meva taula de VRAM proposava valors inabastables. | ✅ Corregit a `ctx: 40960`. YaRN descartat (degrada els contextos curts). |
| 8 | 19.3 Lliçó | Repetia els mateixos enunciats en bucle dins la mateixa lliçó. | ✅ El servidor apunta cada exercici plantejat a `plan.covered` i li torna la llista: "ja preguntat avui, no ho tornis a fer servir". Provar a 19.7c-bis. |
| 7 | 19.3 Lliçó | Amb el badge a 0, el tutor seguia preguntant (Exercise 7, 8…) i sempre amb la mateixa forma ("Rewrite this sentence correctly"). En acabar-se el compte no rebia **cap** instrucció. | ✅ Nota de tancament + instrucció de variar la forma. També retirat el sostre ocult de 12 per sessió, que contradeia el disseny acordat. Provar a 19.7b–19.7d. |
| 6 | 19.1 badge | El número del badge sortia tallat per dalt: estava posicionat sobre el botó i el `overflow-x` de la barra el retallava. | ✅ Ara va dins el botó, en línia. Res el pot retallar. |
| 5 | 19.3 Lliçó | Sortir a Speaking a mitja Lliçó i tornar recomençava per l'exercici 1, i en acabar-lo donava els 6 per fets sense haver vist el sisè. El pla es recalculava a cada consulta. | ✅ El pla es fixa un cop al dia (`.daily/lesson-<data>.json`) i el tutor rep ordre de **continuar**, no de recomençar. Provar a 19.6b i 19.6c. |
| 4 | 15.2 instal·lació | Piper no arrencava sense tocar el `.bashrc` (llibreries pròpies al costat del binari). Funciona al terminal, però el servidor no llegeix cap perfil de shell si l'arrenca systemd/cron o una altra màquina. | ✅ Portat al codi: `ttsEnv()` a `tts.ts` i `piper_env` a `fluent-tts.sh`. El `.bashrc` ja no cal (pots deixar-lo, no fa mal). Provar a 15.3b. |
| 3 | Sessió del matí | 48 torns acumulats, màxim **51.605 prompt tokens** contra un ctx de 32.768 → el model truncava per l'esquerra (on hi ha el prompt de sistema). | ✅ Arrel atacada amb 17.x (sessions noves). Pujar el ctx és 18.x. Podar l'historial, pendent de decidir. |
| 2 | Sessió del matí | `ses_9073d7bb` marcada `tancada ✅` a les 10:15 i amb un torn nou a les 16:09: es reprenia una sessió ja finalitzada i el que es feia després no es tornava a persistir mai. | ✅ Corregit: `session-state` + `reopenIfFinalized`. Provar a 17.1–17.3. |
| 1 | Entrada a demo-en | Amb la cua de repàs buida, el tutor deia «Try: `/fluent-learn`, `/fluent-vocab`…» — comandes que l'alumne no pot escriure. I el missatge sortia marcat `✏️ Exercici`. | ✅ Corregit: skills + regla dura a `rules.md` + `humanizeCommands()` al renderitzat; `MENU_RE` ampliat. Tornar a provar (16.1 i 16.2). |

## Pendent d'afegir en properes tandes

- Poda de l'historial (quan 6.1 digui que cal).
- Mestria dels patrons d'error quan l'alumne els encerta (avui no puja mai).
- Nom del fitxer de resultats per habilitat (S5), si es decideix canviar-lo.
- Lectura de sessions anteriors pel tutor (S4), si es fa l'eina.
- Supervisió amb systemd (P1-8), si es fa.
