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

**Les comprovacions es fan amb un sol script**, `scripts/flowed-check.py`, que
només llegeix. Substitueix els fragments de Python que abans hi havia aquí (i
que peten en enganxar-los, perquè la indentació del document entra dins del
codi):

```bash
cd ~/projects/fluent_dev2
python3 scripts/flowed-check.py all "$PERFIL"   # tot d'un cop
python3 scripts/flowed-check.py sm2 "$PERFIL"   # o una cosa concreta
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
python3 scripts/flowed-check.py sortida "$PERFIL"
```

Treu els **tres últims missatges del tutor literals**, i sota de cada un què en
detecta l'app. Fes-ho després de qualsevol sessió en què alguna cosa no es
mogui, i **enganxa'm la sortida sencera**: amb això es veu si el problema és del
model o del codi, sense endevinar.

---

## 0. Preparació i regressió mínima

- [ ] **0.1 La configuració es resol com toca**
```bash
cd ~/projects/fluent_dev2 && python3 scripts/flowed-config.py --json
```
  *Esperat:* surt el port del deep, el model, les webs i `FLOWED_STREAM: "0"`.
  Els valors han de coincidir amb el que hi ha a `.env` (l'`.env` mana sobre
  `config/fluent.json`).

- [ ] **0.2 El pla d'arrencada no ha canviat**
```bash
scripts/flowed-start.sh --dry-run --yes
```
  *Esperat:* la línia `Pla: deep=… :12322 (backend=native, CUDA …)` igual que
  abans del canvi. Si diu una altra cosa, la capa nova de configuració està
  guanyant on no toca.

- [ ] **0.3 Reinici real de les webs** (el codi del servidor ha canviat; els
  prompts es llegeixen a cada torn, però el servidor no)
```bash
scripts/flowed-stop.sh --webs-only
scripts/flowed-start.sh --webs-only --yes
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
scripts/flowed-web.sh --web --port 4097
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
python3 scripts/flowed-check.py patterns "$PERFIL"
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
python3 scripts/flowed-check.py sm2 "$PERFIL"
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
python3 scripts/flowed-check.py records "$PERFIL"
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
python3 scripts/flowed-check.py patterns "$PERFIL"
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
python3 scripts/flowed-check.py patterns "$PERFIL"
```
  *Esperat:* hi apareixen patrons nous. Abans, les sessions d'escriptura en
  perdien el 100%.

- [ ] **5.4 No repetir** — dins d'una sessió llarga, cap paraula ni escenari
  repetit.

---

## 6. Mètriques i context

- [ ] **6.1 El fitxer de mètriques creix**
```bash
python3 scripts/flowed-check.py metrics "$PERFIL"
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
scripts/flowed-web.sh --stop --port 4199            # sortir del mode stream
scripts/flowed-web.sh --app "$PERFIL" --port 4199   # el mateix perfil, sense stream
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
scripts/flowed-web.sh --stop --port <el port normal de $PERFIL>
FLOWED_STREAM=1 scripts/flowed-web.sh --app "$PERFIL" --port 4199
```
  *Esperat:* al log, `[Fluent] streaming: on (FLOWED_STREAM)`.

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
scripts/flowed-web.sh --stop --port 4199
scripts/flowed-start.sh --webs-only --yes
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
scripts/flowed-web.sh --stop --port 4199    # si en tens una engegada
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
scripts/flowed-stop.sh --webs-only
python3 scripts/migrate-sessions-db.py --all
scripts/flowed-start.sh --webs-only --yes
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
python3 scripts/flowed-check.py profile prova-en
```
  *Esperat:* `setup_complete : False` i la línia `plantilla sense omplir` amb
  els `{...}` encara posats.

- [ ] **11.2 Omple'l des del terminal**
```bash
python3 scripts/flowed-profile.py prova-en \
  --name Prova --native Catalan --target English \
  --level A2 --goal B1 --minutes 20 --session-length 8
```
  *Esperat:* imprimeix el resum amb `setup_complete  True` i surt amb codi 0.

- [ ] **11.3 Ha quedat desat de debò**
```bash
python3 scripts/flowed-check.py profile prova-en
ls ~/.fluent/prova-en/ | grep backup
```
  *Esperat:* dades reals, `setup_complete : True`, `plantilla sense omplir:
  cap ✅` i un `learner-profile.json.backup-…`.

- [ ] **11.4 Es pot retocar després sense tornar-hi tot**
```bash
python3 scripts/flowed-profile.py prova-en --session-length 6 --stop soft
python3 scripts/flowed-profile.py prova-en --show
```
  *Esperat:* només canvien els dos valors; la resta es manté.

- [ ] **11.5 Refusa el que no té sentit**
```bash
python3 scripts/flowed-profile.py prova-en --level Z9 ; echo "codi=$?"
```
  *Esperat:* error amb la llista A1…C2 i `codi=1`. El perfil **no** s'ha tocat.

- [ ] **11.6 La web arrenca directament a practicar** — obre
  `scripts/flowed-web.sh --app prova-en --port 4198`.
  *Esperat:* comença amb `/fluent-learn`. **No** hi ha cap botó de setup i **no**
  surt cap entrevista.

- [ ] **11.7 Un perfil sense configurar no atrapa l'alumne** — crea'n un altre
  amb `new-user.sh` i obre'l sense passar per `flowed-profile.py`.
  *Esperat:* un avís curt dient que el perfil encara no està configurat i que ho
  fa l'administrador. Cap formulari.

- [ ] **11.8 Neteja** — atura la instància quan acabis.

---

## 12. Decaïment (P2)

Costa de provar en una tarda: depèn de dies. El que sí es pot comprovar avui:

- [ ] **12.1 Un skill inactiu baixa** — mira un perfil real amb alguna habilitat
  sense practicar fa setmanes, després d'una sessió nova:
```bash
python3 scripts/flowed-check.py mastery "$PERFIL"
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
python3 scripts/flowed-check.py profile "$PERFIL"
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
python3 scripts/flowed-check.py sortida "$PERFIL"
python3 scripts/flowed-check.py metrics "$PERFIL"
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
python3 scripts/flowed-check.py sm2 "$PERFIL"
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
python3 scripts/flowed-profile.py "$PERFIL" --review-gate off
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
python3 scripts/flowed-check.py all "$PERFIL"
```
  *Esperat:* els patrons i els ítems SM-2 de la sessió hi són (és el bug P0-6:
  la Capa B esborrava la Capa A).

---

## 14. Només a rapve (4060 Ti, backend Docker)

- [ ] **14.1 `cp .env.rapve .env`** i `python3 scripts/flowed-config.py --json`
  → el backend ha de sortir `docker` i el port el que toqui.
- [ ] **14.2 `scripts/flowed-start.sh --dry-run --yes`** → el pla ha de dir
  `backend=docker`.
- [ ] **14.3 Arrencada real** → el contenidor puja, `/health` respon, i
  `/tmp/fluent-deep-docker.state` existeix.
- [ ] **14.4 `scripts/flowed-stop.sh`** → el contenidor s'atura i, si hi ha
  `FLOWED_DEFAULT_MANAGER`, el model per defecte torna al port.

---

## 15. Veu: escoltar la frase (TTS)

Només sortida de veu. L'entrada (micròfon) no hi és i no hi serà fins que hi
hagi TLS — vegeu `ARQUITECTURA.md` §C.3-13b.

**Abans de res: no hi ha res instal·lat.** Amb la configuració tal com ve, no ha
de sortir cap botó 🔊 enlloc. Això és el primer que cal comprovar.

- [ ] **15.1 Apagat, no es nota** — obre la web sense instal·lar res.
```bash
python3 scripts/flowed-check.py tts "$PERFIL"
```
  *Esperat:* `enabled : False`, `veus : cap`, i `aquest perfil … sense veu`. A la
  web, **cap** botó 🔊 enlloc i cap error a la consola del navegador.

- [ ] **15.2 Instal·la piper i una veu** (cal internet en aquesta màquina)
```bash
cd ~/projects/fluent_dev2
scripts/flowed-tts.sh install en_GB-alba-medium
scripts/flowed-tts.sh status
```
  *Esperat:* binari ✅, la veu llistada, i `enabled: True` amb
  `English: …/en_GB-alba-medium.onnx`. Baixa ~80 MB. Comprova-ho també amb
  `python3 scripts/flowed-check.py tts "$PERFIL"` → ha de dir `sonarà 🔊`.

- [ ] **15.3 Prova-ho sense la web**
```bash
scripts/flowed-tts.sh say "Good morning, how are you today?"
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
env -i HOME="$HOME" PATH=/usr/bin:/bin bash -lc 'cd ~/projects/fluent_dev2 && scripts/flowed-tts.sh status'
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
python3 scripts/flowed-check.py tts "$PERFIL"
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
python3 scripts/flowed-check.py metrics "$PERFIL"
```
  *Esperat:* el **màxim** de prompt tokens baixa amb les sessions noves i es
  queda ben per sota del límit. Era 51.605 contra un ctx de 32.768 — el model
  truncava per l'esquerra, on hi ha les regles.

- [ ] **17.5 I ara sí, els registres** — respon **un** exercici de debò.
```bash
python3 scripts/flowed-check.py metrics "$PERFIL"
python3 scripts/flowed-check.py records "$PERFIL"
```
  *Esperat:* `fluent_record_answer  1 ok` i un `.records/<ses>.jsonl`. Si
  segueix sense sortir, **ara sí** que el model ignora la instrucció i cal
  reforçar-la — apunta-ho.

---

## 18. Context i VRAM (ja configurat, **falta mesurar-ho**)

`config/fluent.json` ja porta `ctx: 49152` i `kv_type: "q8_0"`. L'aritmètica i
el perquè de 48k i no 64k són a `docs/model-qwen14b-q4.md`. **Res d'això està
mesurat encara.**

- [ ] **18.1 El valor efectiu és el que creus** — `FLOWED_DEEP_CTX` estava
  fixat a 32768 als `.env` i l'`.env` mana sobre el config; s'ha comentat.
```bash
python3 scripts/flowed-config.py --sh | grep -i "DEEP_CTX\|KV_TYPE"
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
python3 scripts/flowed-check.py metrics "$PERFIL"
```
  *Esperat:* el bloc `abans/ara` separa el torn sencer del temps **dins** el
  model. Si creix `dins el model`, és el model (context 49152, KV q8_0, prompt
  més gros). Si creix la diferència entre els dos, és codi nostre.
  La KV quantitzada té un cost de càlcul per token (típic 5–15%): és el preu del
  contexte extra, i si no compensa, `kv_type: "f16"` amb `ctx 36864`.

- [ ] **18.6b Velocitat (antic)** — compara el temps per torn amb el que tens apuntat.
```bash
python3 scripts/flowed-check.py metrics "$PERFIL"
```
  *Esperat:* mediana semblant. Si el prefill s'ha encarit molt, apunta-ho.

---

## 20. Context: que no peti i que no s'arrossegui

Mesurat el 13/09 sobre 120 torns reals: de **1,9 s a 19,8 s** per torn, tot dins
el model, amb el prompt passant de 25.650 a 31.946 tokens — i un màxim de
**69.484** contra un context de 40.960, que és el `HTTP 400` que va sortir.

- [ ] **20.1 El límit efectiu és 40960**
```bash
python3 scripts/flowed-config.py --sh | grep -i "DEEP_CTX\|KV_TYPE"
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
python3 scripts/flowed-check.py metrics "$PERFIL"
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
python3 scripts/flowed-check.py sm2 "$PERFIL"
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
python3 scripts/flowed-profile.py "$PERFIL" --daily-goal 15
python3 scripts/flowed-check.py profile "$PERFIL"
```

---

## 21. On són totes les sessions (diagnòstic)

La BD de sessions **no és l'única traça**. Cada sessió tancada deixa un fitxer a
`results/` i una entrada a `session-log.json`. Les tres han de quadrar; si la BD
en té menys, hi ha transcripcions en un altre fitxer.

```bash
for p in alex-en sam-en demo-en; do
  echo "=== $p ==="
  python3 scripts/flowed-check.py historial "$p"
done
```

Si diu **`⚠ FALTEN TRANSCRIPCIONS`**, busca on són:

```bash
ls -la ~/.local/share/opencode/ 2>/dev/null
find ~ -name 'opencode.db' -o -name 'sessions.db' 2>/dev/null | grep -v node_modules
```

L'`opencode` antic desava a un lloc **central compartit** fins que
`flowed-web.sh` va començar a fixar `XDG_DATA_HOME` per perfil. Les sessions
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
| 4 | 15.2 instal·lació | Piper no arrencava sense tocar el `.bashrc` (llibreries pròpies al costat del binari). Funciona al terminal, però el servidor no llegeix cap perfil de shell si l'arrenca systemd/cron o una altra màquina. | ✅ Portat al codi: `ttsEnv()` a `tts.ts` i `piper_env` a `flowed-tts.sh`. El `.bashrc` ja no cal (pots deixar-lo, no fa mal). Provar a 15.3b. |
| 3 | Sessió del matí | 48 torns acumulats, màxim **51.605 prompt tokens** contra un ctx de 32.768 → el model truncava per l'esquerra (on hi ha el prompt de sistema). | ✅ Arrel atacada amb 17.x (sessions noves). Pujar el ctx és 18.x. Podar l'historial, pendent de decidir. |
| 2 | Sessió del matí | `ses_9073d7bb` marcada `tancada ✅` a les 10:15 i amb un torn nou a les 16:09: es reprenia una sessió ja finalitzada i el que es feia després no es tornava a persistir mai. | ✅ Corregit: `session-state` + `reopenIfFinalized`. Provar a 17.1–17.3. |
| 1 | Entrada a demo-en | Amb la cua de repàs buida, el tutor deia «Try: `/fluent-learn`, `/fluent-vocab`…» — comandes que l'alumne no pot escriure. I el missatge sortia marcat `✏️ Exercici`. | ✅ Corregit: skills + regla dura a `rules.md` + `humanizeCommands()` al renderitzat; `MENU_RE` ampliat. Tornar a provar (16.1 i 16.2). |

## 22. El skill arriba al model (incident 2026-09-16)

El 16/09 el tutor va fer una lliçó sencera **sense haver carregat mai**
`skills/fluent-review/SKILL.md`: 60 torns, cap correcció, el comptador clavat i
el mateix exercici 25 vegades. La causa i el detall són a
[`ARQUITECTURA.md` § E](ARQUITECTURA.md). Aquestes proves confirmen que ja no
pot tornar a passar.

### 22.1 Estàtic — abans d'engegar res

```bash
cd /opt/fluent && python3 -m unittest discover -s tests -q 2>&1 | tail -3
```

Ha de dir **`Ran 227 tests`** i **`OK`**. Un número més baix vol dir que el
`rsync` no ha arribat: no continuïs.

Cap comanda pot demanar-li al model que carregui el skill:

```bash
cd /opt/fluent && grep -l "via the skill tool" prompts/commands/*.md; echo "coincidencies: $?"
```

Ha de no imprimir cap fitxer (`coincidencies: 1`).

El servidor sí que el carrega, i el fixa al *system prompt*:

```bash
cd /opt/fluent && grep -c "loadSkill" server/src/commands.ts && grep -c "activeSkill" server/src/agent.ts
```

Han de sortir dos números, tots dos **≥ 2**.

### 22.2 En viu — la prova que importa (una sola comanda)

Amb el servidor engegat i **`test-en`**, mai amb un perfil real. Obre l'app
(que llança `/fluent-learn` sola), prem 🎓 Lesson, contesta **4 exercicis** i:

```bash
python3 scripts/flowed-check.py lliço test-en
```

Vuit línies, totes han de dir `✅ PASSA`:

```
  ✅ PASSA  el tutor marca les respostes
  ✅ PASSA  ensenya la versió correcta
  ✅ PASSA  posa nota
  ✅ PASSA  hi ha respostes registrades (.records/)
  ✅ PASSA  el comptador de la lliçó avança
  ✅ PASSA  queda constància del que s'ha preguntat
  ✅ PASSA  cap etiqueta de brossa a la llista
  ✅ PASSA  cap resposta del tutor repetida
```

Les tres primeres són el skill. Si fallen, el skill no ha arribat al model i
**no despleguis a llvm**.

I mirant la primera pantalla a ull nu, tres coses que **no** hi poden ser:

- Cap clau: `{Target}`, `{the word}`, `{✅}`. Vol dir que el model està copiant
  la plantilla en comptes de fer-la servir.
- La paraula **Review** ni cap `⭐` de mestria en un perfil nou: si no hi ha res
  a repassar, ha de ser una primera lliçó de material nou, no un repàs fingit.
- Cap `Last reviewed: 0 days ago` d'un ítem que l'alumne no ha vist mai. Contra els perfils del 16/09 aquesta mateixa comanda
dona 4 i 3 falles respectivament — és a dir, detecta la incidència.

### 22.3 El detall, si alguna cosa falla

Amb el servidor engegat i un perfil de proves. **Reprodueix exactament la
seqüència que va fallar**: obre l'app (que llança `/fluent-learn` sola) i
llavors prem 🎓 Lesson. És el segon command de la sessió, que és on es trencava.

Respon **3 exercicis**, i després:

```bash
PERFIL=test-en; python3 scripts/flowed-check.py sortida "$PERFIL" | tail -60
```

Tres coses han de sortir a cada resposta del tutor:

1. Un marcador 🟢 / 🟡 / 🔴 (o ✅ / ❌).
2. `**Correct version:**`
3. `**Score: N/10**`

Si en falta cap, el skill no hi és. Atura't aquí.

### 22.4 El comptador es mou

```bash
PERFIL=test-en; cat ~/.fluent/$PERFIL/.daily/lesson-$(date +%F).json
```

`done` ha de ser **3**. Si és `0`, el comptador no llegeix l'evidència: mira si
hi ha registres estructurats, que ara també compten:

```bash
PERFIL=test-en; wc -l ~/.fluent/$PERFIL/.records/*.jsonl
```

### 22.5 Els registres hi són

```bash
PERFIL=test-en; python3 scripts/flowed-check.py records "$PERFIL"
```

Un directori `.records/` inexistent és el símptoma exacte del perfil A el 16/09:
zero qualificacions estructurades en tota la sessió.

### 22.6 Els detectors nous

Al log del servidor no hi ha d'haver cap d'aquestes dues línies:

```bash
grep -hE "has not changed in 4 turns|same exercise twice in a row" /tmp/fluent-web-*.log 2>/dev/null || echo "cap avis - correcte"
```

Si en surt alguna, **guarda el log**: és la traça que el 16/09 no teníem.

### 22.7 El bloc d'estat no es reinjecta cada premuda

Prem 🎓 Lesson, contesta, i prem 📝 Writing. Els tokens de prompt del segon
command **no** han de pujar ~2,8k respecte del torn anterior:

```bash
PERFIL=test-en; tail -12 ~/.fluent/$PERFIL/.metrics/turns.jsonl | python3 -c "import sys,json; [print(json.loads(l).get('prompt_tokens'), json.loads(l).get('tools')) for l in sys.stdin]"
```

### 22.8 Direcció dels exercicis de vocabulari

Mirant la sortida de 22.2: en un perfil que aprèn anglès des del català, les
preguntes han de demanar **la paraula anglesa**. Si el tutor pregunta *"What is
the Catalan word for 'morning'?"*, està examinant l'alumna de la seva pròpia
llengua — era un dels símptomes del 16/09 i ha de desaparèixer amb el skill
carregat.

---

## 23. Que avanci de debò (auditoria 2026-09-19)

Els tests de codi font no veuen una app trencada: els 220 d'abans haurien
passat el 16 igualment. Aquests fan córrer el pipeline real sobre setmanes
simulades. Es corren sols dins la suite, però si vols veure'ls:

```bash
cd /home/albert/projects/fluent_dev2 && python3 -m unittest tests.test_progress_is_real -v
```

Cinc comprovacions, escrites com les preguntes que faries tu:

- el que encerta deixa de sortir (30 dies → mestria ≥ 4, cap patró feble)
- l'espaiat s'eixampla (interval > 20 dies)
- el que oblida torna **demà**
- una setmana fallant-ho tot no fa explotar la cua
- res no es clava mai a una falta d'ortografia seva

### 23.1 El mateix, amb un perfil real, sense tocar-lo

Lectura només: diu què li està oferint el sistema al tutor ara mateix.

```bash
PERFIL=naia-en; FLOWED_DATA_DIR=~/.fluent/$PERFIL python3 hooks/read-db.py | python3 -c "
import json,sys; m=json.load(sys.stdin)['databases']['mistakes_db']
print('patrons totals :', m.get('total_patterns'))
print('curats         :', m.get('healed_patterns'))
print('encara febles  :', [p['id'] for p in m.get('top_weak_patterns',[])])"
```

Si **cap** patró surt com a curat després de setmanes d'ús, la mestria no puja
i el tutor tornarà a repetir el mateix. Era el cas fins al 19/09.

### 23.2 La lliçó no es tanca abans d'hora

Arran del 19/09: el skill tancava en acabar-se la cua SM-2 i deixava la
insígnia a 2 de 6. Fes una lliçó amb pocs ítems deguts i mira que arribi als 6.

```bash
PERFIL=test-en; cat ~/.fluent/$PERFIL/.daily/lesson-$(date +%F).json
```

`done` ha de coincidir amb `total` quan el tutor digui "Session Complete".

---

## 24. La lliçó sencera, contra el model de debò (`flowed-e2e.py`)

El que faltava. Tota la resta comprova el codi; això fa **parlar el tutor** i
llegeix el que diu. El 16/09 la suite era verda mentre el tutor feia seixanta
torns sense corregir, perquè el que es va trencar era el que el model rebia, i
cap test unitari ha llegit mai una resposta d'un model.

Obre sessió per l'API igual que el navegador, prem 🎓 Lesson, contesta els
exercicis **a posta malament** — una resposta correcta només demostra que el
tutor sap felicitar, que no és la part que es trenca — i comprova el que fa que
una nena pensi que l'app està trencada.

### 24.1 Córrer-lo

Amb el servidor engegat:

```bash
scripts/flowed-web.sh --app --port 4103 test-en
```

En una altra terminal:

```bash
cd /home/albert/projects/fluent_dev2
python3 scripts/flowed-e2e.py test-en --port 4103 --reset --transcript /tmp/llico.md
```

Triga el que trigui el model: compta ~15-40 s per exercici amb el 14B. Va
imprimint cada resposta a mesura que arriba, amb el temps i els avisos.

### 24.2 Què comprova

```
✅ el tutor obre la sessió
✅ el servidor ha fet el pla de la lliçó
✅ cada resposta rep un marcador
✅ ensenya la versió correcta
✅ posa nota
✅ cap clau de plantilla a la pantalla
✅ cap exercici repetit seguit
✅ cap exercici repetit en tota la lliçó
✅ no tanca la lliçó abans d'hora
✅ el comptador segueix les respostes
✅ les respostes arriben a .records/
✅ cap avís del servidor per aquesta sessió
```

Les tres primeres de contingut (marcador, versió correcta, nota) són el skill.
Si fallen, el skill no arriba al model. La de les claus és el tutor imprimint
la seva pròpia plantilla. Les dues de repetició són el símptoma del 16/09.

### 24.3 La transcripció

`--transcript` desa **tot el que ha dit el tutor**, resposta per resposta. És
la part que cap comprovació automàtica pot jutjar: si els exercicis tenen
sentit, si el to és bo, si una nena de vuit anys ho entendria. Llegeix-la.

```bash
less /tmp/llico.md
```

### 24.4 Opcions

| | |
|---|---|
| `--answers N` | quants exercicis contestar (per defecte 6) |
| `--reset` | buida l'estat d'aprenentatge abans de començar, amb còpia `.bak`. **Només** en perfils `test*`/`demo*`/`e2e*` — en un perfil real es nega |
| `--timeout N` | segons per torn (per defecte 240) |
| `--dir RUTA` | perfil per ruta, en comptes de `~/.fluent/<id>` |
| `--user` / `--password` | credencials a mà. Per defecte usuari `opencode` (el servidor l'accepta sempre) i la contrasenya de `<perfil>/.web-password`. Un 401 vol dir, gairebé sempre, que el servidor s'ha engegat amb un altre perfil |

Codi de sortida 0 si tot passa, 1 si alguna comprovació falla, 2 si no hi ha
servidor o perfil. Es pot encadenar.

---

## 25. Els quatre usos que falten

### 25.1 La lliçó s'acaba, i es queda acabada

Cap execució hi havia arribat mai: totes paraven a 6 respostes.

```bash
python3 scripts/flowed-seed.py test-en --days 21 --due 3
python3 scripts/flowed-e2e.py test-en --port 4103 --scenario full --transcript /tmp/full.md
```

Contesta fins que la lliçó es tanqui i **després insisteix dos torns més**. Tres
comprovacions noves:

```
✅ la lliçó arriba al seu final
✅ i s'hi queda: cap exercici nou després de tancar
✅ i l'orienta cap als botons
```

Si surt un setè exercici d'amagat després del tancament, la insígnia menteix.

### 25.2 Demà

El que tot el sistema sosté: **el que encerta no torna demà, el que falla sí.**
Esperar un dia per prova no és un pla, així que el rellotge es mou:

```bash
python3 scripts/flowed-seed.py test-en --days 21 --due 3
python3 scripts/flowed-e2e.py test-en --port 4103 --scenario lesson

python3 scripts/flowed-advance-day.py test-en
python3 scripts/flowed-e2e.py test-en --port 4103 --scenario lesson
```

`flowed-advance-day.py` resta un dia a **totes** les dates del perfil, que és el
mateix que el calendari avançant-ne un: un ítem per demà passa a ser per avui, i
el dia que acaba s'arxiva. La segona execució afegeix:

```
✅ no li torna a preguntar el que ja sabia
✅ i sí que li torna el que va fallar
```

Es nega en qualsevol perfil que no sigui de proves.

### 25.3 Un perfil real

No cal codi: el mateix amb `nes-en`, i **sense `--reset`** ni `--seed`, que té
dades de veritat i les vols conservar.

```bash
python3 scripts/flowed-e2e.py nes-en --port 4103 --scenario wander --transcript /tmp/nes.md
```

### 25.4 El forat que queda obert

Els registres derivats **no porten `item_id`**, així que encertar un ítem de la
cua no el treu de la cua. El bloc `fluent:review_results` del tutor sí que ho
fa, però depèn del model — i ja sabem com acaba això. La reparació és que el
servidor casi l'exercici amb l'ítem que tenia pendent. **No fet.**

---

## 26. Taxes, no fotos (`--repeat`) i el marató

### 26.1 Per què una execució no prova res

El model es mostreja: **els mateixos paràmetres donen una resposta diferent
cada vegada**. Una execució verda no vol dir que el problema hagi marxat, i una
de vermella no vol dir que hi sigui sempre. El que s'ha de mirar és una taxa.

```bash
python3 scripts/flowed-e2e.py test-en --port 4103 --scenario wander --repeat 3
```

Al final:

```
=== resum de 3 execucions ===
  ✅ cada resposta rep un marcador
  ⚠️  cap exercici repetit en tota la lliçó  — falla 1/3
  ❌ les respostes arriben a .records/  — falla 3/3

  el guard del servidor ha actuat 14 cop(s) en total  (4.7 per execució)
  1 de 23 comprovacions han fallat alguna vegada
```

El **`4.7 per execució`** és el número que vol dir alguna cosa quan després
canviïs els paràmetres de mostreig. Si baixa a 0.3 sense que cap comprovació de
format es torni groga, el canvi és bo.

### 26.2 El marató

16 respostes i tres desviacions, una a Writing (respostes llargues):

```bash
python3 scripts/flowed-e2e.py test-en --port 4103 --scenario marathon --transcript /tmp/marato.md
```

Serveix per a l'única cosa que cap prova ha tocat mai: que el context creixi
prou perquè **la poda d'historial** entri en joc. És on vivia el desbordament de
41808 tokens.

---

## 27. El servidor dispensa la cua (punt 4)

**El problema, mesurat:** després d'una lliçó sencera, `0 de 15 registres
porten item_id`. L'eina `fluent_record_answer` no es crida mai, i un registre
derivat del text **no pot inventar-se l'id** — un id equivocat avança l'horari
d'un altre ítem, en silenci.

**La solució:** el servidor agafa el de dalt de la cua ell mateix i l'hi diu al
tutor:

> The next exercise reviews this item: "English" (answer: "English"). Build the
> exercise yourself — the wording, the level and the form are yours — but keep
> it about that item.

Sap quin ítem era **perquè l'ha triat ell**. El repartiment no canvia:

| El servidor | El tutor |
|---|---|
| quin ítem toca, i en quin ordre | quin exercici en fa, a quin nivell, amb quina forma |

Només dins de la Lliçó i només per als ítems vençuts; la resta d'exercicis i
totes les altres pràctiques, el tutor els tria lliurement.

**Tres guardes:**

- La resposta es crèdita a **l'assignació anterior**, no a la que s'acaba de
  fer: l'exercici a la pantalla el va decidir el torn passat.
- L'id es comprova contra la cua abans d'escriure'l, igual que fa l'eina.
- Un ítem no es reparteix dues vegades a la mateixa sessió.

### 27.1 Com es comprova

```bash
PERFIL=test-en; cat ~/.fluent/$PERFIL/.records/*.jsonl | python3 -c "
import sys,json
n=w=0
for l in sys.stdin:
    d=json.loads(l); n+=1; w+=1 if d.get('item_id') else 0
print(f'{w} de {n} registres porten item_id')"
```

Abans: `0 de 15`. Amb una lliçó que tingui ítems vençuts, ara n'hi ha d'haver
tants com ítems de la cua s'hagin practicat.

I que l'horari es mogui de debò:

```bash
PERFIL=test-en; python3 -c "
import json,os,datetime
sr=json.load(open(os.path.expanduser('~/.fluent/$PERFIL/spaced-repetition.json')))
avui=datetime.date.today().isoformat()
for k,v in sr['items'].items():
    if v.get('last_reviewed')==avui: print(' ',k,'interval',v.get('interval_days'),'proper',v.get('due_date'))"
```

Un ítem encertat ha de sortir amb l'interval **més gran** que tenia i una data
futura. Si segueix a `interval 1` i venç demà, no s'ha registrat.

---

## 28. La bateria de paràmetres (`flowed-bench.sh`)

### 28.1 La comanda

```bash
scripts/flowed-bench.sh              # base + 3 hipòtesis, wander ×3
scripts/flowed-bench.sh --quick      # només la base, per veure si tot rutlla
scripts/flowed-bench.sh --full       # wander + full + marathon
scripts/flowed-bench.sh --repeat 5 --port 4104
```

La bateria és **la mateixa cada vegada**. Editar-la és decidir què vol dir "va
bé"; canviar-la entre dues execucions és perdre la comparació.

Les quatre configuracions, i per què són aquestes:

| | Paràmetres | Què respon |
|---|---|---|
| `base` | els actuals (`temperature 0.2`) | la referència; sense ella la resta no vol dir res |
| `temp06` | `temperature=0.6` | la temperatura sola, ¿és el que fa repetir? |
| `penal` | `presence_penalty=0.4, frequency_penalty=0.3, repeat_last_n=512` | les penalitzacions soles, a temperatura baixa |
| `totes` | les dues coses | ¿se sumen o es trepitgen? |

Separades a posta: si es canvien alhora i millora, no se sap què ho ha fet.

### 28.2 Cridar el sweep a mà

```bash
python3 scripts/flowed-sweep.py test-en --port 4103 --repeat 3 \
  --setting "base:" \
  --setting "calent:temperature=0.8,top_k=40" \
  --setting "estricte:temperature=0.3,repeat_penalty=1.15,repeat_last_n=1024"
```

Format: `"nom:clau=valor,clau=valor"`. Admet `temperature`, `top_p`, `top_k`,
`presence_penalty`, `frequency_penalty`, `repeat_penalty`, `repeat_last_n` —
qualsevol altra cosa es rebutja amb la llista de les vàlides. Una configuració
sense paràmetres (`"base:"`) deixa la del fitxer.

### 28.3 Com es llegeix la sortida

```
=== resum ===
  setting     escenari    guard/exec  falles         cua   regs  item_id
  base        wander             5.7       5      12→13      8        5
  temp06      wander             1.3       2      12→14      9        7

=== què canvia, comprovació per comprovació ===
                                                      base      temp06
  cada resposta rep un marcador                        1/3           ·
  cap exercici repetit en tota la lliçó                3/3         1/3
  les respostes arriben a .records/                    3/3           ·

  · = no falla mai en aquella configuració
```

La taula de sota és la que decideix. La de dalt diu **quant**; aquesta diu
**què** — si una configuració arregla la repetició però trenca el format, es
veu a la mateixa columna.

**`cua 12→13`** és la comprovació de pèrdua de dades: qualsevol execució que
deixi la cua més petita del que l'ha trobada es marca amb ⚠, digui el que digui
la resta. És el que no vam veure el 19/09, quan una instantània T0 amb el número
de sessió reciclat va rebobinar un perfil de dotze ítems a dos.

**`item_id`** són els registres que porten identificador de cua: si és zero,
l'SM-2 no rep senyal i el que encerta tornarà demà igualment.

### 28.4 On queda tot

`results/sweep-<data>/<configuració>/` amb `knobs.json`, els logs d'aturada,
arrencada i sembra, el log de cada execució, la transcripció sencera del tutor,
i `04-profile-<escenari>.json` amb l'estat del perfil abans i després. A dalt,
`summary.csv` amb tot en columnes.

La configuració original es restaura **sempre**, també si la bateria peta a
mitges.

---

## 29. Quan l'instrument es mou entre execucions (2026-09-19)

Dues «regressions» de la bateria del 19 no eren del servidor sinó del banc de
proves. Val la pena tenir-les escrites perquè són la mateixa família d'error que
`--repeat` consumint el dia: **si l'instrument canvia entre execucions, cap
comparació feta amb ell val res.**

**La sembra no era idempotent.** `flowed-seed.py` buidava el dia (el pla, els
registres, els T0) però deixava `spaced-repetition.json` i `mistakes-db.json` tal
com estaven. Cada bateria sembrava **a sobre** de la cua que havia deixat
l'anterior: els ítems que introdueix tard perquè quedin per repassar avui ja hi
eren, ja contestats i ja programats per d'aquí setmanes.

    sweep 1   12 ítems · 3 per repassar avui
    sweep 2   15 ítems · 0 per repassar avui   ← i `--due 3` sense queixar-se

Amb res per repassar, la lliçó es munta dels patrons febles, cap registre pot
portar `item_id`, i la regla del guard «avui no hi ha res per repassar» queda
armada tota l'execució. Ara la sembra reinicia la cua i els patrons (còpia a
`*.bak-seed`) abans de construir el passat. Prova: `tests/test_fluent_seed.py`.

**El guard es comptava dues vegades.** `guards.jsonl` escriu la línia que
dispara i després `rewritten`, que és el **resultat** de la mateixa
intervenció. `flowed-e2e.py` les comptava totes dues: els «11 guards» d'una
execució eren cinc intervencions i les seves reescriptures. Totes les xifres de
guard anteriors a avui estan inflades ~×2.

**El marcador ✅/❌.** Dins d'una vinyeta de correcció («❌ becouse → ✅ because»)
són correctes i es queden; a la línia de veredicte diuen el mateix que la nota, i
«❌ Not quite» sobre un «Score: 10/10» és la contradicció que un nen llegeix
primer. `alignMarkersToScore` ara els repinta **només** a la línia de veredicte i
només als dos extrems (≥8, ≤4); la comprovació de `flowed-e2e.py` mira el mateix.

**La persistència arriba tard.** `runAutoPersistence` es dispara **sense
`await`**: la resposta arriba a l'alumne (i a l'script) mentre
`accumulate-session.py` encara corre, i aquest hook crida `update-db.py` amb tot
el payload acumulat, `review_results` inclosos. O sigui que **la cua avança
DESPRÉS que la resposta hagi tornat**.

Entre repeticions això és letal: `restore()` tornava a posar els 3 ítems per
repassar i l'escriptura endarrerida de l'execució anterior els tornava a
empènyer cap endavant. Execució 1 amb 3 per repassar, execucions 2 i 3 amb cap;
al tutor se li deia «avui no hi ha res per repassar» i cap registre podia portar
`item_id`. Llegit des de fora és exactament una regressió del servidor.

    execució 1   8 registres · 2 amb item_id
    execució 2   8 registres · 1 amb item_id
    execució 3   6 registres · 0 amb item_id   ← i el sweep només mirava aquesta

Ara `flowed-e2e.py` espera (`wait_quiet()`) que no quedi cap
`accumulate-session.py` / `update-db.py` / `persist-session.py` corrent abans de
restaurar, i un cop més en acabar.

**El sweep només comptava l'última repetició.** `restore()` arxiva els registres
de cada volta amb un nom amb punt al davant, i `profile_state` feia
`glob("*.jsonl")`. Ara compta tot el que s'ha escrit des que va començar
l'escenari i diu en quantes execucions.

### I la sembra que va morir sense que ningú ho mirés (22:32)

La tanda següent va sortir amb els tres punts de partida **iguals i a zero**, i
el motiu no era la cursa: `flowed-seed.py` havia petat abans de sembrar res.

    OSError: [Errno 36] File name too long:
      .daily/................lesson-2026-09-16.json.bak-20260919-122651.bak-…

Arxivar volia dir reanomenar el fitxer a `.<nom>.bak-seed` **al mateix lloc**, i
el glob que els trobava també agafava els arxius. Cada tanda afegia un punt i un
sufix; a la tretzena el nom va passar dels 255 bytes. El sweep no mirava el codi
de sortida de la sembra, així que va córrer tres execucions sobre un perfil
ranci amb 14 ítems i res per repassar, i les va donar per bones.

Tres canvis, un per cada baula:

- **Un arxiu és un lloc, no un sufix.** `flowed-seed.py` i `restore()` mouen els
  fitxers vius a `_archive/<segell>-<nom>` i no toquen mai el que ja hi és.
  Prova: `tests/test_fluent_seed.py` sembra vint vegades seguides i comprova que
  cap nom passa dels 120 caràcters.
- **El sweep atura l'escenari** si la sembra retorna error o deixa 0 per
  repassar, en lloc de mesurar un perfil que no s'ha preparat.
- **`due_today` es calcula com el servidor** (`due_date <= avui`), no des de
  `review_queue.today`, perquè la porta anterior ha de coincidir amb el que el
  tutor rebrà de debò.

### La predicció, escrita abans de la tanda

Les execucions 2 i 3 del 19 són **exactament** les que van començar amb 0 ítems
per repassar, i exactament les que van col·lapsar (2 de 8 i 0 de 8 respostes amb
marcador). L'execució 1, amb 3 per repassar, va anar bé. Per tant «el tutor no
corregeix en 1 de cada 3 execucions» **no està demostrat**: està confós amb
l'estat «res per repassar», que activa el camí de primera lliçó, prohibeix
etiquetar res com a *Review* — i la capçalera es va quedar clavada a
«Review 1/6» igualment.

Amb tots els punts de partida iguals (3 vençuts), la propera tanda decideix:

- **el col·lapse desapareix** → la causa era el camí «res per repassar»: un bug
  de prompt o de servidor, no variància del model;
- **es manté en ~1 de cada 3** → és una fallada real independent de l'estat, i
  el símptoma del 16/09 continua viu.

Per poder-ho adjudicar, `flowed-e2e.py` imprimeix els vençuts en començar cada
execució i marca **PUNT DE PARTIDA DIFERENT** si no coincideixen amb els de la
primera; el sweep ho puja a la columna `desigual` i a `summary.csv`. L'espera de
la persistència té límit (45 s) i, si el supera, ho diu pels dos canals i avisa
que aquell punt de partida no és de fiar. I es jutja per **taxa de fallada per
comprovació**, no pel total d'una volta: amb el mateix codi hem vist de 14/23 a
22/23.

---

## 30. El mostreig que arriba de veritat (2026-09-20)

### 30.1 Què va passar

`temp06` **mai va córrer a 0,6**. El sweep escrivia la temperatura a
`config/fluent.json`, però el servidor llegeix també `config/fluent-models.json`
(capa heretada, **versionada**) i aquesta guanya sobre la primera. Aquesta porta
`temperature: 0.2`. Reproduït amb el codi real de `loadModels`:

| Config | Temperatura efectiva |
|---|---|
| `fluent.json` = 0,6, sense models file | **0,2** (el cas d'abans) |
| `FLOWED_MODELS_FILE` amb 0,6 | 0,6 |

Els altres paràmetres (`top_p`, penalitzacions, `repeat_last_n`) sí que passaven,
perquè `fluent-models.json` no els fixa. Cap comprovació ho deia. **Qualsevol
número de la taula `base` vs `temp06` d'abans compara dues execucions a 0,2.**

I el mateix valia per a qualsevol edició de `temperature` a `config/fluent.json`,
a qualsevol màquina. `fluent-models.json` repetia `fluent.json` valor per valor
(port, temperatura, max_tokens, timeout: comprovat) i no aportava res, només hi
guanyava. **S'ha retirat** (és a `obsolet/config/`) i el servidor ja no l'agafa:
`config/fluent.json` és l'única font. Verificat amb el `loadModels` real: els
valors que resol el servidor són byte per byte els mateixos d'abans, i ara un
`temperature` editat a `fluent.json` arriba.

### 30.2 Què s'ha canviat

- **El mostreig d'un setting viatja per `FLOWED_MODELS_FILE`** (un fitxer per
  setting, a `results/sweep-*/<setting>/models.json`). És la capa que guanya sobre
  totes, i no cal reescriure ni restaurar cap fitxer del repositori. Les claus
  van en camelCase perquè és el que llegeix el servidor.
- **El sweep comprova el mostreig efectiu abans de córrer**: demana a
  `/api/global/health` què enviarà el servidor al model i el compara amb el
  demanat. Si difereix (o si una capa hi posa un paràmetre que ningú ha demanat,
  cosa que faria que la base ja no ho sigui), **no corre aquell setting** i diu
  quin. La sortida imprimeix `mostreig efectiu: …`.
- **Una sola font per als paràmetres dels models:** `config/fluent.json`. Només
  hi poden anar al damunt l'`.env` (port, GPU, backend) i `FLOWED_MODELS_FILE`,
  explícit.
- **La comprovació «el model no corre» mirava tot el log** i la línia del `face`
  (apagat per disseny) la disparava. Ara només compta la línia `model: deep`.
- **El bench ja no reescriu un perfil que existeix**: només en crea i configura un
  de nou.
- **En acabar, el sweep atura l'app de proves** (portava el mostreig de l'últim
  setting a l'entorn).
- **`flowed-bench.sh` deixa a punt el perfil i el model.** El perfil `test-en`
  es crea i es configura si no hi és. El model deep, si no respon, l'aixeca amb
  `flowed-start.sh --models-only --yes` i l'atura en acabar; si ja corria, no el
  toca. `--keep-model` no l'atura, `--no-start` avorta en comptes d'aixecar-lo.
  Compte: `flowed-start.sh --yes` fa el canvi 1:1 amb el model per defecte si
  ocupa el port (`FLOWED_DEFAULT_MANAGER`), i l'stop el restaura.

### 30.3 Com es comprova

```bash
python3 -m unittest tests.test_fluent_sweep -v
scripts/flowed-bench.sh --quick --repeat 1
```

*Esperat a la segona:* `mostreig efectiu: temperature=0.2, top_p=0.95` per a la
base. Per veure la comprovació treballant, amb un setting que el servidor **sí**
ha de complir:

```bash
python3 scripts/flowed-sweep.py test-en --port 4103 --repeat 1 --setting "calent:temperature=0.6"
```

*Esperat:* `mostreig efectiu: temperature=0.6, top_p=0.95`. Si diu `❌ el
mostreig efectiu NO és el demanat`, hi ha una altra capa que fixa el paràmetre.

### 30.4 Una transcripció per execució

Amb `--repeat N`, l'e2e ja no sobreescriu la transcripció: escriu
`transcript-<escenari>.1.md … .N.md` (al sweep, dins `results/sweep-*/<setting>/`).
Cada fitxer acaba amb la secció `## guard del servidor (text complet, en ordre)`:
una línia JSON per acció del guard, incloent-hi les de resultat "rewritten"
(text original, text reescrit, motiu de rebuig). Serveix per llegir què escriu
realment el tutor quan un check diu "corregeix però no pregunta".

```bash
scripts/flowed-bench.sh --quick --repeat 6
ls results/sweep-*/base/transcript-wander.*.md
```

### 30.5 El fingerprint no veia l'exercici (2026-09-20)

Amb les transcripcions per execució (`results/sweep-20260920-134521`) es va veure
que el tutor **sí** demanava l'exercici en el format:

```
**Exercise:**
Complete the sentence with the correct form of the word:
"She ___ to school every day."
```

`exerciseFingerprints` només llegia la línia següent a l'etiqueta (la instrucció,
que es descarta a propòsit) i retornava `[]`. Mesurat sobre les 6 transcripcions:
0 de 8 respostes amb fingerprint a 5 execucions (només la 4, que usa un altre
format, en tenia). Conseqüències, totes de la mateixa causa:

- El guard "corregeix però no pregunta" es defineix com `asked.length === 0`:
  **saltava en fals** i forçava reescriptures, que a més canviaven la correcció
  (p. ex. «woke» → «apple»; «an» → «a»).
- La repetició (la mateixa frase 3-4 cops seguits a 4 execucions) era invisible
  per al guard i per al servidor.
- Al banc: `exercicis diferents`, `el comptador…`, `en proposa de noves` i
  `no insisteix` fallaven per mesura, no per conducta del tutor.

Canvi: `collectBlock` a `server/src/pacing.ts`. Amb l'etiqueta sola a la línia,
el fingerprint és la primera línia entre cometes de sota (fins a 4 línies, sense
passar d'un `**…`). Una línia sense cometes **no** s'endevina. Tests a
`server/test/pacing.test.ts` (6 checks nous, amb el text real).
Repetit sobre les 6 transcripcions: 8 de 8 respostes fingerprintades.

*Efecte esperat a la propera tanda:* menys guards "asks nothing" (només els
reals), i apareixen els "already asked" que abans no es veien. Les xifres de la
tanda anterior (4.5 guards/exec, 5 checks 5/6) **no són comparables** amb les
següents: el guard era cec.

### 30.6 La reescriptura descartada per «feedback lost» (2026-09-20)

Tanda `sweep-20260920-140201` (fingerprint ja corregit, 6 execucions): 50 accions
de guard (8.3/exec), 2 checks fallen (`cap exercici repetit` 4/6, `no insisteix`
3/6). 11 de les 50 eren «rewrite rejected: feedback lost», i **les 11 eren un
cartó sol** (`## Review 5/6 — high …`, `## Word 1/10 …`): davant «mateix
feedback i un exercici diferent», el model torna només l'exercici nou. El servidor
el descartava per no tenir «Correct version:», i amb ell l'exercici nou: la
repetició es quedava a la pantalla (a l'execució 2, «An ___ is a vegetable» 3
cops seguits, també després d'una resposta correcta 10/10).

Canvi: `spliceFeedback` (`server/src/pacing.ts`). Si la reescriptura és només
l'exercici, es posa darrere del feedback de la primera resposta (fins a la línia
`**Score…`, inclosa). No s'aplica si la primera resposta no té «Correct version:»
ni línia de nota, o si la reescriptura porta feedback propi o no demana res
(llavors continua el rebuig). Nota del guard: «rewritten (feedback kept,
exercise replaced)». 7 checks nous a `server/test/pacing.test.ts`.

També: `guards.jsonl` guarda ara 1500 caràcters del text (abans 120), perquè la
secció de guard de les transcripcions sigui llegible de debò.

*Encara obert, no tocat:* quan se li demana «un exercici diferent», el tutor sol
donar una variació de la mateixa frase amb la mateixa resposta («An ___ is a
fruit», «…a red fruit», «…that grows on trees»). El fingerprint és de text i no
ho distingeix; només una regla sobre l'ítem (la resposta) ho podria fer.

### 30.7 Tanda `sweep-20260920-145348`: què va passar i què s'ha afegit

6 execucions, 33 guards (5.5/exec), 8 checks fallen alguna vegada. **Sis dels
vuit venen d'una sola execució (la 4)**, en què el tutor no qualifica res (0/8
nota, 0/8 versió correcta). Per execució, checks bé sobre 23: 22, 23, 22, **15**,
23, 23 (tanda anterior: 23, 21, 22, 21, 23, 21). Sense la 4: `no insisteix` 3/6
→ 0/5, «rewrite rejected» 11 → 0, guards 8.3 → 5.5/exec.

La 4 no ve de l'empalmament: els dos primers torns no tenen cap guard, i la
primera targeta ja era degenerada (sense buit, amb la resposta en negreta).
Més probable: mode sense feedback que s'autoalimenta amb l'historial, a
temperatura 0.2. Amb 12 execucions amb el fingerprint corregit és 1 cas; no
demostrat.

Encara real: a les execucions 1 i 3, `repeated in a row` surt **després** de
`rewritten`, és a dir, la reescriptura torna el mateix exercici.

Afegit (només instrument):

- `server/src/agent.ts` `logNote` → `.metrics/notes.jsonl`: per torn, la nota que
  el servidor dóna al tutor, l'ítem assignat, `last_asked` i la resposta de
  l'alumne. Fitxer apart de `guards.jsonl` perquè no és una intervenció i
  inflaria els recomptes. Cada transcripció acaba amb la secció
  `## notes del servidor al tutor (per torn)`. Serveix per veure si la nota
  («revisa aquest ítem») i el guard («exercici diferent») demanen coses
  contràdictòries.
- L'e2e i el sweep compten «execucions sense cap qualificació» (una execució
  amb 0 notes) a part dels checks: una execució així ja no es llegeix com sis
  problemes. Columna `sense nota` al resum i `ungraded_runs` a `summary.csv`.

Tanda següent: `scripts/flowed-bench.sh --quick --repeat 12`.

### 30.8 El banc demanava una cosa impossible: 6 exercicis amb 3 ítems (2026-09-20)

El perfil sembrat deixava **3 ítems per repassar** (`capitalization_English`,
`spelling_because`, `articles_an_apple`), però una lliçó són 6 exercicis
(`LESSON_MINIMUM`). Els 3 restants surten dels patrons febles, que són les mateixes
tres frases; el banc demanava al tutor sis exercicis diferents amb tres conceptes
i comptava cada variant («An ___ is a fruit», «…a red fruit») com a repetició, i
el guard reescrivia. Una part de les repeticions i dels guards de les tandes
anteriors venia d'aquí, no del tutor.

Canvi (només banc): `flowed-sweep.py --due` per defecte 3 → 6. Comprovat
amb un perfil temporal: `per repassar avui: 6` amb sis ítems diferents
(`vocabulary_morning`, `agreement_She_goes_to_school`, `tenses_I_woke_up_at_seven`,
`capitalization_English`, `spelling_because`, `articles_an_apple`). Cada torn de la
lliçó té així un ítem assignat propi, i una repetició ja és del tutor.

**Les tandes anteriors no són comparables amb les que vinguin.**

*Obert, decisió de producte (no tocat):* quan un alumne real té poc material
(pocs ítems i pocs patrons), el servidor fixa igualment 6 exercicis. Potser el
total de la lliçó s'hauria d'ajustar al material disponible en comptes de
demanar-ne de nous al tutor.

### 30.9 Què compta com a repetició, i un fons que la faci inequívoca (2026-09-20)

Tanda `sweep-20260920-151622` (6 ítems per repassar): 0 execucions sense nota,
0 «rewrite rejected», 4.0 guards/exec, 24 de 48 registres amb `item_id` (abans
10 de 38). Però «cap exercici repetit» fallava 6/6. Classificades les 20
repeticions de les transcripcions: **17 entre pràctiques** (l'ítem de la Lliçó
torna a sortir a Vocabulary o al revés), 3 dins Vocabulary, 0 dins la Lliçó.
El servidor permet que una paraula solta surti a dues pràctiques (`turnGuard`), i
el check ho comptava sempre com a fallada: fallava per construcció.

**Decisió (Albert):** un exercici que es torna a mostrar sense haver-lo contestat
és correcte, també a una altra pràctica. No cal canvi al servidor.

Canvis de banc:

- `flowed-e2e.py` `classify_repeats`: *repetició* = exercici **ja contestat** que
  torna a sortir. Dins la mateixa pràctica → fallada (el check ara es diu «cap
  exercici ja contestat es repeteix dins la mateixa pràctica»). Entre pràctiques
  → només informatiu, línia `informatiu (no és cap verdict)` del resum. Sense
  contestar → correcte. «No insisteix» també compta només exercicis ja contestats.
  Amb les transcripcions de la tanda: 3 repeticions reals de 6 execucions.
- `cap clau de plantilla` ja no mira el bloc `fluent:review_results` (el web
  l'amaga; era el fals positiu `{"item_id": …}`).
- `flowed-seed.py`: 32 ítems (14 de vocabulari + 18 de gramàtica; abans 10) i
  `--due` 6 per defecte amb una barreja fixa (2 de vocabulari, 4 de gramàtica).
  Vocabulari amb `content` en català i `answer` en anglès («matí» → morning);
  gramàtica amb frases senceres. Abans un ítem era només «because» i el tutor
  preguntava «What is the English word for 'because'?». Els no vençuts s'escampen
  fins a `days − 9`: SM-2 necessita tres revisions (intervals 1, 1, 6, 16) perquè
  un ítem quedi lluny, i un introduït més tard tornava a vèncer avui (`--due 6`
  en donava 8). Comprovat: 6 vençuts, 26 lluny, 18 patrons. Amb `--days`
  inferior a ~12 no es pot garantir.

**Les tandes anteriors no són comparables amb les següents** (tercer cop: banc
diferent cada vegada; ara ha de quedar estable).

### 30.10 L'alumne que sap algunes respostes (`--scenario student`)

Fins ara tots els escenaris contestaven brossa (i, en un reintent, la correcció
del tutor): es provava que el tutor sap corregir una resposta dolenta i mai que
tracta bé una de bona. L'escenari `student` contesta **bé i malament a propòsit**
(patró `right, wrong, right, right, wrong, right`, una lliçó de 6):

- L'ítem que hi ha a la pantalla és l'assignat pel servidor a la nota del torn
  anterior (`.metrics/notes.jsonl`); la seva resposta és a `spaced-repetition.json`.
- *Bé* = `answer` de l'ítem. *Malament* = el que l'alumne va escriure (`learner_wrote`)
  a la gramàtica («She go to school»), i un ganxo (`table`) al vocabulari.
- Després de la sisena resposta, dos torns més per veure que la lliçó es queda tancada.

Checks nous (només en aquest escenari; jutgen només els torns en què l'exercici
va sobre l'ítem assignat, mig de les paraules de l'ítem a l'exercici):

1. `l'exercici és sobre l'ítem que el servidor ha assignat` (2/3 dels torns com a mínim)
2. `una resposta correcta rep nota alta (8 o més)`
3. `una resposta equivocada no rep nota alta`
4. `i una de correcta porta marcador verd`
5. `cada resposta queda registrada amb l'item_id de l'ítem assignat`
6. `i el registre porta una nota que hi concorda`

Més els de tancament de `full` (arriba al final, s'hi queda, orienta cap als botons).

```bash
scripts/flowed-bench.sh --student --quick --repeat 6
```

Funcions pures i testades a `tests/test_e2e_transcript.py`; l'escenari sencer
només es pot córrer amb el model i l'app (no s'ha executat encara).

### 30.11 Primera tanda `student`: l'última resposta de la lliçó no rebia feedback

`sweep-20260920-155912`, 6 execucions, 0 guards. Cinc checks fallaven; **dos eren
de l'instrument i un era un error real del servidor**.

*Instrument (corregit):*
- «una resposta correcta rep nota alta» i «equivocada no rep nota alta» fallaven
  6/6 perquè llegien la nota de la resposta següent (índex desplaçat en un). En
  llegir la resposta correcta, «morning» surt 10/10, i «table» 6/10.
- «no la penalitza per un accent» marcava «i speak english on mondays → I speak
  English on Mondays»: és una regla anglesa (majúscules), no una lletra de la seva
  llengua. Ja no compta quan només canvien les majúscules.
- Una resposta equivocada que només és una majúscula pot valer 8/10; el llindar
  d'«equivocada» és ara 9.

*Servidor (corregit), la causa de «la lliçó arriba al seu final» 6/6:* el pla es
crèdita **després** de la resposta, així que en arribar la 6a resposta de 6 diu
5 fetes. La nota deia al tutor «1 exercici per fer: no tanquis» i el tutor
obeïa: **no donava cap feedback a l'última resposta**, presentava un setè exercici
i la lliçó no es tancava. Ho va empitjorar el propi encapçalament «Review k/6»,
que anava un per sota (dos exercicis seguits amb «1/6»). Cap escenari anterior
contestava exactament `total` respostes, per això no s'havia vist.

Canvi: `withAnswerInFront` (`server/src/pacing.ts`) i `lessonWithAnswerInFront`
(`agent.ts`): mentre hi ha una resposta al davant, compta com a feta per a la
nota, els guards i l'encapçalament. No compta per a un botó, ni sense resposta,
ni per a un reintent d'un exercici ja acreditat. A la 6a resposta la nota passa a
ser la de lliçó completa («avalua la resposta i tanca»). 10 checks nous a
`server/test/pacing.test.ts`. **Cal reiniciar l'app.**

*Fons (corregit):* l'ítem `articles_an_apple` tenia només «an apple» com a
contingut i el tutor preguntava «What is the English word for 'an apple'?».
Ara és una frase: «I eat an apple every day».

### 30.12 `flowed-testbase.sh`: el banc manual

`scripts/flowed-testbase.sh` deixa el perfil de proves amb el mateix fons que la
bateria i l'app oberta perquè hi provis a mà. Comparteix la preparació de perfil
i model amb la bateria (`scripts/lib-testbed.sh`, un sol lloc). Sembra (buida
avui, la cua i els patrons: el mateix reset que fa la bateria), aixeca el model si
cal, obre l'app en el port 4105 i imprimeix URL, usuari i contrasenya.
`--keep` no sembra; `--stop` atura l'app; `--stop --models` també el model.

### 30.13 Tanda `student` després de la correcció: la lliçó es tanca bé

`sweep-20260920-161518`, 6 execucions: 3 checks fallen (3/6 cada un) i tots tres
són el mateix: el **missatge de tancament** es fingerprintava com un exercici
(«**What to work on:** Keep practicing to maintain your progress») i, en tornar a
sortir a la resposta següent, comptava com a «repetit» i com a «exercici nou
després de tancar». Tots els altres checks passen, incloent-hi els que eren
nous: `la lliçó arriba al seu final`, notes altes per a les correctes, baixes per a
les equivocades, marcador verd, `item_id` correcte i nota del registre coherent.
L'última resposta ja rep feedback i la lliçó es tanca al torn 6 (comprovat a les
transcripcions).

Canvi: `exerciseFingerprints` no fingerprinta res d'un missatge que tanca la
lliçó («lesson/session (is) complete») si no té un bloc `**Exercise:**`, i
`NOT_A_LABEL` ha crescut amb les etiquetes del resum (una llista no basta: cada
execució en surt amb una redacció nova, per això la regla estructural). Repassat
sobre les 6 transcripcions: cap fingerprint després del tancament. 4 checks nous a
`server/test/pacing.test.ts`. **Cal reiniciar l'app.**

*Trobat, no tocat:* el resum del tutor menteix. Amb dues respostes falladas
(«table», i una frase sense majúscules) diu «Accuracy 100%», «Mastered (no
mistakes): 6» i «all 6 exercises were perfect». El bloc `fluent:review_results`
sí porta les qualitats bones (2, 5, 5, 5, 2-4, 5): el servidor sap la veritat i el
tutor n'inventa el text. Candidat per a la tanda següent: donar al tutor a la nota
de tancament la xifra real (encerts, nota mitjana, ítems a reforçar), o comprovar-la.

### 30.14 Primera prova per la web (`flowed-testbase.sh`)

Dues coses vistes a mà, escrivint «6» (🎲 Surprise me) al menú:

1. **L'alumne veia l'identificador intern** (`Item ID: agreement_she_goes_to_school`).
   El tutor l'escriu perquè veu la cua com a JSON. Corregit **al render**
   (`web/app.js`, `INTERNAL_ID_LINE_RE` dins `stripMachineBlocks`): la línia no
   arriba a la pantalla ni amb streaming; el text desat la conserva. 5 tests nous a
   `server/test/web-render.test.ts`.
2. **Sense feedback a la primera resposta.** A «mornint» (per «morning») el tutor no
   va corregir res i va presentar un altre «Exercise 1». La segona («She goes to
   school») i la tercera («windows», 8/10) sí es van corregir. Aquest mode és
   `fluent-learn`, no la Lliçó: els guards de «corregeix però no pregunta» i de
   tancament només actuen a la Lliçó. Diagnòstic a § 30.15.

### 30.15 Contracte Lliçó / mode lliure (canvi de disseny)

**Diagnòstic** (`guards.jsonl` + `notes.jsonl` d'una sessió 🎲): `assigned:null` i una
nota fixa «Spaced-repetition gate: 0 of 6 due items done… item_id copied verbatim».
La «gate» (`GATE_COMMANDS`) s'aplicava també a `fluent-learn` i demanava registrar
ítems pendents amb `item_id`; al mode lliure el servidor no assigna cap ítem, així que
la nota no avançava mai i el tutor escrivia l'ID a pantalla. L'avaluació (nota,
feedback, `graded`, registre derivat) funciona a tots els modes: no era això.

**Contracte, fixat:**
- **Lliçó** (`fluent-review`) = l'únic mínim obligatori: repàs de **tot el pendent**
  d'avui (cua SM-2), amb comptador, guards i `item_id`. Mida variable: 2 ítems o 15
  (límit diari `review_items_per_day`, 20 per defecte). **Sense farcit** a 6. Només
  una cua buida dona una lliçó curta de `LESSON_MINIMUM` = 3 exercicis sobre patrons
  febles.
- **Mode lliure** (🎲, 📝🗣️📚📖): com abans; exercicis corregits i amb nota, sense
  gate ni `item_id`. `GATE_COMMANDS` = només `fluent-review`.

**Canvis:** `pacing.ts` (`LESSON_MINIMUM` 6→3, `lessonTarget` sense farcit,
`GATE_COMMANDS`), tests actualitzats a `pacing.test.ts` (gate 🎲 = no; 5/2/15 pendents).
**Pendent:** el guard «ja preguntat / falta feedback» al mode lliure (el «mornint»
sense feedback no té àrbitre fora de la Lliçó).

### 30.16 Mode lliure: la resposta no es corregia («morn» per «matí»)

**Dades** (`notes.jsonl` + `guards.jsonl`, codi ja sense gate): a `fluent-learn` la nota
del servidor era només la llista «ja preguntats, no els tornis a demanar», i hi
constava **«matí»**, l'exercici que l'alumne estava contestant. Resposta del tutor a
«morn»: la mateixa fitxa de «matí», **sense cap feedback**. El guard de repetició la va
canviar per «finestra», també sense feedback. A la llista hi havia a més «high priority»
(l'etiqueta «Review (High Priority)» presa per un exercici) i ítems d'altres proves d'avui.

**Canvis:**
- `practiceNote(covered, lastAsked, answerInFront)`: amb resposta al davant l'exercici en
  joc **surt de la llista de prohibits** i la nota diu «el missatge és la resposta a "X":
  corregeix-la primer (veredicte, versió correcta, nota) i després l'exercici següent».
- `turnGuard` (tots els modes, no només la Lliçó): resposta al davant + resposta que
  pregunta però no corregeix ⇒ es reescriu una vegada («corregeix primer…»; si repeteix
  l'exercici, «no repeteixis "X"»). Camp nou `answering` a `TurnGuardState`.
- `NOT_AN_EXERCISE`: `high/medium/low/critical priority`.
- Tests: 4 a `practiceNote`, 7 al guard, 1 de fingerprint.

**Per provar net:** `flowed-web.sh` directe sobre `test-en` arrossega el «ja preguntat
avui» de les benches; `scripts/flowed-testbase.sh` neteja el fons abans d'arrencar.
**No verificat amb model encara.**

### 30.17 Resultat `student` (sweep-20260920-171904) i escenari `journey`

**Resultat:** 25/26 comprovacions; l'única que falla, 6/6, és «no insisteix més d'un
reintent en la mateixa pregunta» (3 torns seguits). **Era un fals positiu del bench:**
la Lliçó tanca a la resposta 6 (resum de tancament) i les respostes 7 i 8 («no ho sé»)
ja no tenen cap pregunta; el check les comptava com a «la mateixa pregunta». Corregit:
des de la resposta que tanca fins que comença la pràctica lliure no es compta.
Sense fallades reals del tutor: marcador, versió correcta, nota, `item_id` (36 de 36),
0 sense nota, guard 0.3 per execució, 2 en total.

**Escenari nou `journey`** (`scripts/flowed-bench.sh --journey --quick`), més complicat i
sense repeticions:
1. Lliçó fins al final amb el pla `student` (encerta/falla) + 1 resposta passat el final.
2. 📚 Vocabulary: 4 respostes (bé, malament, bé, malament). La resposta es treu d'un banc
   (el `VOCAB` de `flowed-seed.py`) segons la paraula catalana de l'exercici en pantalla;
   si el tutor en posa una de fora del banc, la resposta és «no ho sé» i no es jutja.
   La resposta dolenta és una altra paraula anglesa real.
3. 📝 Writing: 2 frases amb errors a propòsit.
4. 📚 Vocabulary (torna): 2 respostes (bé, malament).

**Comprovacions noves:** tota resposta en pràctica lliure té nota; una frase amb errors a
Writing no rep 9+ i n'ensenya la versió correcta; Vocabulary queda desat al dia i no
compta com a lliçó; en tornar a Vocabulary no repeteix paraules; a més, les del
`student` (nota alta per la correcta, baixa per l'equivocada, marcador verd, `item_id`).
**No executat encara.**

### 30.18 Primer `journey` (sweep-20260920-181339): 5 de 33 comprovacions fallen

Bo: la pràctica lliure corregeix tota resposta (`tota resposta … rep correcció amb nota`
6/6), Writing no dona notes altes a frases amb errors, la Lliçó tanca i s'hi queda,
Vocabulary queda desat i no compta com a lliçó. La nota nova («és la resposta a X:
corregeix-la primer») fa que les respostes de Vocabulary rebin feedback.

**Error meu (servidor):** `lastAsked` sobrevivia al canvi de pràctica. Després de
📝 Writing l'última paraula de Vocabulary («llibre») seguia com a «exercici que
contesta», la nota nova deia «és la resposta a "llibre"» i el tutor va corregir les
frases de Writing com si fossin «no ho sé» per «llibre» (2 registres falsos per
execució; 90 registres per 36 amb `item_id`). Corregit: un botó esborra `lastAsked`
(`agent.ts`, `runCommand`); la resposta al botó el torna a posar si presenta un
exercici reconegut.

**Errors del bench:** (a) les respostes de Writing no tenen empremta i el check
«insisteix» les llegia com a «mateixa pregunta» (5/6); (b) una paraula mostrada i no
contestada que torna a Vocabulary no és repetició (decisió), però el check la
comptava; (c) el tutor tria paraules pròpies (menjar, dia, plat, cotxe, telefon…):
el banc ha passat de 14 a 44 paraules.

**Errors reals del tutor (model):** «i speak english on mondays» → 10/10 (1/6, també
al registre); en tornar a Vocabulary reprèn en «Word 1/10» i torna a preguntar una
paraula ja contestada («cotxe»), 2/6.

**Decisió pendent:** el guard «ja preguntat» del servidor també salta amb paraules
mostrades però no contestades (25 intervencions en 6 execucions, la majoria així), quan
hem decidit que aquestes poden tornar. Proposta: `covered` només amb el contestat.

### 30.19 «Ja preguntat» = contestat correctament

**Decisió:** la llista que impedeix repetir un exercici només porta el que l'alumne ha
contestat **correctament** (nota ≥ 8, `KNOWN_SCORE`). Un exercici mostrat i no contestat
pot tornar; un de contestat malament també (SM-2 el vol de tornada, i el tutor pot donar
un reintent).

**Canvis** (`agent.ts`, `pacing.ts`):
- `plan.covered` i `askedByPractice` creixen a `creditTurn`, amb l'exercici que hi havia
  a pantalla **abans** d'aquest torn, només si la resposta hi era (`answerInFront`) i la
  nota d'aquest torn és ≥ 8. Ja no creixen en mostrar l'exercici.
- `scoreOfReply()`: llegeix la nota del feedback i **salta els encapçalaments**
  («## Word 8/10» és progrés, no una nota).
- `enforceTurn`: el guard compta com a conegut l'exercici que aquest mateix torn puntua
  ≥ 8 (`justKnown`), perquè `creditTurn` encara no ha corregut.
- Les notes diuen «Already answered correctly today…».

**Pendent (no mesurat):** el bench `journey` de 30.18 es va llançar abans d'aquest canvi.

### 30.20 Longitud de Writing segons el nivell — està escrit, no està vigilat

`skills/fluent-writing/SKILL.md` ja té la taula (A1: 1-3 frases / 15-25 paraules;
A2: 4-6 / 30-45; B1: 50-70, «email amb salutació i comiat»). És només instrucció: ni el
servidor ni el bench la comproven. El `journey` va mostrar un exercici «email amb
salutació, dissabte i diumenge i comiat» (3 requisits) per a un perfil A2, que és un
exercici de B1. **Proposta:** un check al `journey` (nivell del perfil → màxim de
paraules/frases demanades, i «email/carta» prohibit per sota de B1) i, si falla, una
regla al servidor. Res tocat encara.

### 30.21 `journey` amb «contestat correctament» (sweep-20260920-194253)

11 de 33 fallen alguna vegada; les que fallen sempre o quasi:
- **«cap avís del servidor» 6/6** — `the pacing note has not changed in 4 turns`. L'avís és
  de la Lliçó (que no avança). A pràctica lliure la nota és la llista del que ja sap i no
  canvia mentre no s'encerti res nou: era esperat. Ara l'avís només salta a `fluent-review`.
- **«n'ensenya la versió correcta» 4/6** — Writing la posa sota «📝 Corrected Version», no
  «Correct version:». El check llegia la literal. El feedback de Writing era bo (6/10 a
  frases amb errors, correcció i versió corregida).
- **repeticions «cap», «capitalització»** — el bench comptava com a repetició qualsevol
  resposta, i el servidor ara només refusa la contestada bé. `classify_repeats(…, known=)`:
  «repetit» = contestat bé (nota ≥ 8); una de fallada no és repetició, però **sí que
  continua sense ser una pregunta nova** (`fresh`), de manera que «la mateixa pregunta 3
  cops seguits» es continua veient.

**Nou:** `writingLengthNote(level)` (`pacing.ts`) — a `fluent-writing` el servidor diu al
tutor què demana el nivell (A2: 4-6 frases / 30-45 paraules, una nota o postal, **no un
email**). I un check al `journey`: «Writing demana un text adequat al nivell» (paraules,
frases, «email/carta» per sota de B1). Abans només era una taula al SKILL.md.

**Errors del tutor sense arreglar:** «i speak english on mondays» → 10/10 (2 de 12
execucions); «week» → 6/10 en una resposta correcta; una execució amb Writing sense nota
(Writing no té empremta: el servidor no sap que hi ha una resposta pendent). A
Vocabulary, a l'execució 1, targetes sense sentit («an», «on», «goes»: «Què vol dir en
català?») que semblen sortir de les frases de la Lliçó; no repetit a la resta que he
mirat. Sospita, no diagnosi: la llista de la nota porta fragments lletjos («i up at seven
yesterday»).

### 30.22 Errors del tutor al `journey` (194253): què són de veritat

1. **«i speak english on mondays» → 10/10** (1 de 6; les altres 5, 8/10). L'exercici
   era «Complete the sentence correctly: "I speak English on ___."». El forat amaga
   el que l'ítem vol treballar (la majúscula), i la resposta del bench, la frase sencera
   en minúscula, conté «mondays»: el tutor l'accepta. A l'ítem `capitalization` només li
   arriba la frase correcta, no l'error de l'alumne. **Proposta:** afegir `learner_wrote`
   a `AssignedItem` i dir al tutor «mostra l'error de l'alumne i demana que el corregeixi».
2. **«week» → 6/10** — **error del bench**: la targeta era «capitalització» i el context
   deia «els dies de la setmana»; el bench va triar «setmana» del context. El tutor tenia
   raó. Corregit: `bank_item` mira la línia de la paraula (`**Català:** X`).
3. **Writing sense nota** (1 de 6): l'alumne va contestar amb una frase a un exercici
   d'email i el tutor la va prendre com a tema d'un exercici nou. El servidor no ho va
   poder vigilar: un exercici de Writing no té empremta (`**Scenario:**` és a
   `NOT_A_LABEL`, `**Task:**` és una instrucció). **Proposta:** empremta per a
   `**Scenario:**`, i el guard «resposta sense nota» funciona també a Writing.
4. **Targetes sense sentit** («an», «on», «goes», «capitalització» a Vocabulary). No és
   nou: `skills/fluent-vocab/SKILL.md` ja diu, a les Critical Rules, que un ítem
   `error_pattern` no és una paraula i cita `articles_an_apple` com a cas real. Però la
   cua arriba al tutor com una llista plana de pendents i AGENTS.md diu «review due
   items first». **Proposta:** a `fluent-vocab` el servidor passa només els pendents de
   tipus vocabulari (paraula i resposta) i diu que la resta són regles, no targetes.
   Mateix patró que la longitud de Writing: una instrucció escrita que ningú vigilava.
5. **`</think>` a pantalla** (1 cop, en un exercici de Writing). Corregit: `tidyTutorText`
   treu `<think>…</think>` i les etiquetes soltes.

### 30.23 Tres canvis al servidor per als errors de 30.22

1. **Ítem de regla amb l'error de l'alumne** (`pacing.ts`): `AssignedItem.wrong` (de
   `learner_wrote`, només si difereix del contingut). La nota de la Lliçó afegeix: «el
   seu error va ser "X": fes un exercici en què repetir-lo es marqui malament (p. ex.
   corregir una frase que el contingui); no l'amaguis darrere d'un forat». No s'aplica a
   ítems de vocabulari.
2. **Writing amb empremta**: `**Scenario:**` és ara una marca d'exercici. El servidor sap
   que hi ha una resposta pendent i el guard «has d'avaluar la resposta» (30.16)
   també hi actua.
3. **Vocabulary només amb paraules**: `vocabularyDueNote()` — a `fluent-vocab` la nota
   porta els pendents de tipus `vocabulary` amb la seva resposta (menys els ja
   contestats bé) i diu que la resta d'ítems de la cua són regles, no targetes.

**Cal mesurar:** `--journey --repeat 6` (targetes sense sentit a Vocabulary, Writing sense
nota, capitalització 10/10).

### 30.24 `journey` després dels tres canvis (sweep-20260920-201752)

**Arreglat i confirmat:** «cap avís del servidor» (0 fallades), capitalització (6/10 a les
6 execucions, cap 10/10), Writing demana un text adequat a A2 (passa) i amb el
`Scenario` fingerprintat, cap Writing sense nota d'escriptura, sense `</think>`.

**Fallades que eren del bench** (5/6 cadascuna):
- «no insisteix»: comptava com a «mateixa pregunta» una paraula contestada abans (en un
  altre moment) que torna. «Insistir» és ara el **mateix exercici just després de
  contestar-lo**, o cap exercici.
- «en tornar a Vocabulary no repeteix»: comptava paraules contestades **malament** (que
  poden tornar). Ara només les contestades bé.

**Decisió aplicada (guard):** com que «cobert» = contestat bé, un terme sol també es
refusa a totes les pràctiques (abans només dins la que l'havia mostrat). A la Lliçó «matí»
(contestat 10/10) sortia un altre cop a Vocabulary.

**Targetes sense sentit** («an», «de», «on», amb context «Vull un ___ de poma»): amb la
nota nova van baixar (2 de 5 execucions, abans 1 sola amb 4 targetes) però no van
desaparèixer. Motiu: després de la Lliçó **no queda cap pendent** (tot reprogramat), així
que la llista de paraules és buida i queda només la instrucció general. Ara la nota diu
sempre què és una targeta: nom, verb o adjectiu, mai article, preposició o tros de
frase gramatical.

**Nou, sense arreglar:** les targetes barregen les dues plantilles del SKILL.md:
«**Català:** finestra — Què vol dir en català?» (pregunta el significat en català d'una
paraula catalana). Check nou al `journey`: «les targetes de Vocabulary no demanen en la
llengua de la paraula».

**Execució 3, plana:** va començar amb la cua buida des del punt de vista del servidor
(«Review items due: 0») tot i que la sembra en deia 6; el tutor va improvisar 3
exercicis de gramàtica sense ítem i la Lliçó va acabar a 5 de 6. 1 de 6, no repetit;
sospita: carrera entre el reset del perfil i la persistència de l'execució anterior.

### 30.25 `journey` 204104: 35/35 a 4 de 6 execucions

Falles que queden: «no insisteix» (1/6) i «targetes que demanen en la llengua de la
paraula» (1/6, 5 de 8 targetes d'aquella execució).
- **«no insisteix» era real:** dues respostes seguides a Vocabulary corregides sense
  cap targeta següent («Let's try another one.» i res). La Lliçó té la regla «corregeix
  però no pregunta», la pràctica lliure no. Ara `turnGuard` la porta a `fluent-vocab`
  (`oneAtATime`); Writing queda fora a propòsit (un escenari per sessió, el feedback
  acaba assenyalant els botons).
- **Targetes barrejades:** la nota de Vocabulary diu ara les dues direccions amb els
  idiomes del perfil («una paraula en català demana "How do you say it in English?"»).

### 30.26 Tres escenaris nous: `days`, `noisy` i mides de lliçó / nivells

Fins ara tot es mesurava en UN dia i amb respostes netes. Tres forats:

**`days` — diversos dies seguits** (`flowed-bench.sh --days`, o
`flowed-e2e.py --scenario days --days 5`). Cada dia: sessió nova, Lliçó completa,
espera a la persistència, i `flowed-advance-day.py` mou el rellotge un dia. L'alumne
té un nombre de vistes abans de saber cada ítem (0, 1 o 2, fixat pel `item_id`): erroni
fins llavors i correcte després. Per dia es comprova, contra `spaced-repetition.json`:
la mida de la Lliçó = pendents (topall `review_items_per_day`; cua buida → 3); cap ítem
assignat que no tocava; tot el pendent surt; cada resposta queda amb `item_id`;
**l'SM-2 avança exactament com `update-db.py`** (repeticions, interval, `due_date`; la
qualitat és `score // 2` de l'últim registre de l'ítem); el que es falla torna demà;
el que ja se sabia i s'encerta s'allunya (≥ 6 dies); el que no s'ha contestat no es
toca. Entre dies: el que va fallar ahir torna avui, el que va encertar (sabent-lo) no.
Al final imprimeix una taula (pendents, lliçó, encertats, fallats, intervals).
Els jutges (`judge_day`, `judge_carry`, `sm2_after`) són funcions pures amb tests, i
`tests/test_days_fake_server.py` corre l'escenari sencer contra un tutor fals perfecte
(mateixes notes, pla i registres; el `update-db.py` és el de veritat): 5 dies, 62/62.
Si una execució real falla un check, és del tutor o del servidor, no de l'escenari.
Durada: ~5 lliçons per execució; el sweep li dóna 4 h de marge (les altres, 30 min).

**`noisy` — respostes brutes** (`--noisy`). Com `student` però l'alumna escriu com
una persona: punt final, dins una frase amb entrada en català, sense accents, tot en
majúscules, una lletra de menys, a mitges, en català, en un paràgraf de 300 caràcters,
«?» o la seva errada de sempre. Classes esperades: correcta ≥ 8; errada d'una lletra
≥ 6; incompleta / en una altra llengua / buida < 8; errada pròpia < 9; i una resposta
llarga no fa perdre el fil. (En ítems d'ortografia la «typo» no s'aplica: seria
l'exercici; en majúscules només a vocabulari.)

**Mides i nivells.** `flowed-seed.py --due N` accepta fins a 26 (després dels 8
escollits a mà alterna gramàtica i vocabulari). `flowed-bench.sh --student --due 2` i
`--due 15` proven la Lliçó petita i la gran; `--level A1|B1` crea i fa servir
`test-en-a1` / `test-en-b1` (l'objectiu és el nivell següent) i comprova, amb
`--journey`, la llargada del Writing per nivell.

Ordre suggerit de proves: `--days`, `--noisy`, `--student --due 2`, `--student --due 15`,
`--journey --level A1`, `--journey --level B1`, i només llavors base vs temp06.


### 30.27 `journey` 205656: 2 falles, i un problema més gran que no veia el bench

Falles: «cap exercici contestat es repeteix» (1/6, execució 3) i «resposta correcta
rep nota alta» (1/6, execució 6). Mirades als transcripts:
- **«to eat» → 4/10 (exec. 6): error del banc, no del tutor.** La targeta portava
  «El menjar és important per a la salut»: aquí *menjar* és nom (= *food*). Substituït
  per *beure / to drink* (no és nom).
- **«llibre» torna després de 10/10 (exec. 3):** la nota ja el llistava com a contestat,
  però el guard va reescriure aquell torn per «corregeix i no preguntes» (`oneAtATime`)
  i la reescriptura va tornar a triar *llibre*. Ara la nota de la reescriptura afegeix
  «Not any of these — she already got them right today: …».
- **El que el bench no mirava:** un mot equivocat rep **6/10 🟡** (*table* per *matí*,
  *rain* per *casa*, *friend* per *llibre*), a totes les execucions. L'SM-2 fa
  `qualitat = puntuació // 2` i ≥ 3 és «recordat»: un 6 envia la paraula a 1 → 6 dies i no
  torna. La rúbrica del skill deia «5-7 🟡» sense excloure les respostes equivocades.
  Canvis: `skills/fluent-feedback-formatter` («una resposta equivocada és 0-4, mai 🟡»);
  check nou al `student`/`journey` («una paraula equivocada no passa de 5») i al `days`
  («una paraula equivocada no compta com a sabuda»).
- Els skills es rellegeixen a cada torn: un `days` en curs quan es va canviar el skill
  barreja les dues rúbriques a partir d'aquell punt.


### 30.28 Temes per alumne (`topics.txt`)

Idea d'Albert: donar al tutor estructures concretes (les que estudien les nenes a
l'escola) sense trencar res. Fitxer de text per perfil; es llegeix a cada torn i arriba
com una nota (`topicsNote` a `pacing.ts`, `topicsNoteFor` a `agent.ts`). Manual § 8.
- **Seguretat:** sense fitxer, la nota és nul·la i cap torn canvia. La cua mana: a la
  Lliçó només s'afegeix quan no hi ha ítem assignat ni patró (`!assigned && !drill`).
  La nota diu «ignora'l abans que forçar-lo» i «no ho anunciïs».
- **Tests:** `parseTopics` (comentaris, vinyetes, duplicats, límit), `pickTopics`
  (rotació, tots tenen torn), la nota, i que el servidor només la posa on toca.
  Escenari `topics` (`--topics`): Writing hi va, Vocabulary segueix donant targetes,
  la Lliçó segueix el que assigna el servidor i el tutor no cita la nota.


### 30.29 Primera tanda de `days`, `noisy`, `--due 2/15` i A1 (213444 … 215123)

**Errors del banc (arreglats, no diuen res del tutor):**
- **`days`: l'SM-2 «no avançava» (15 de 63 malament).** Els cinc dies feien servir el
  mateix `session-001@<data>`: el rellotge de paret no es mou, i `update-db.py` va
  trobar el T0 del dia 1, va restaurar les bases a abans del dia 1 i va tornar a
  aplicar. Una instantània nova en 5 dies. Un demà de veritat té una altra data i no hi
  arriba mai. `flowed-advance-day.py` aparta ara `.update-state/*.json`; el test
  contra el tutor fals reprodueix la falla sense l'arranjament (5 dies, intervals 1 → 6).
- **«no li torna a preguntar el que ja sabia — finestra / she go to school»** (tres
  benchs): eren arxius `.day-*` del `days` anterior, que el check «ahir» llegia com a
  història. El `seed` (i el `restore`) els aparten.
- **`noisy` «en català → 10/10»:** per a un ítem de gramàtica el `content` és la frase
  anglesa; el bench enviava la resposta correcta. Ara envia català de veritat.
- El sweep no llegia res d'una execució (`guard -1×`, «0 de 0»): `--summary`.

**Del tutor (oberts):**
1. **La correcció és d'un altre exercici** (`noisy` i A1): «crec que és: window» per a
   *finestra* rep la correcció de «She go to school»; a A1 «morning» rep la de
   *window*, i l'etiqueta fa Review 3/6, 2/6, 4/6, 2/6… El comptador queda a 1 de 6.
2. **Exercici mal format:** de l'ítem d'ortografia *because* fa «Correct the sentence:
   "I can't go to the park because."» i qualifica «because» amb 4/10 (`--due 15`).
3. **Ítems duplicats:** un error surt amb dues categories (`grammar_…` i
   `capitalization_…`) i fa dos ítems de la mateixa frase; a la cua del dia 1, 9 en lloc
   de 6.


### 30.30 «La correcció és d'un altre exercici»: no era el tutor, era la reescriptura

Albert: «no sé si cal el guard, ho hem trobat només una vegada?» Rastrejats tots els
transcripts (`results/*/transcript-*.md`, 985 respostes qualificades): 25 marcades per una
heurística (correcció que cita un error que ni la resposta ni l'exercici contenen, o un
10/10 la versió correcta del qual no té res a veure amb la resposta). Descomptats els
falsos positius antics (`xxx`, `no ho sé`), **8 reals, tots a les quatre últimes tandes**
(`noisy` 2/6, A1 3/14, `--due 15` 2/15) i cap a les 12 execucions netes de 204104/205656.
Als guards de cada una: **totes vénen d'una línia «rewritten»**. L'original era bo
(«"Morning" és correcte per a *matí*»); la reescriptura, demanada perquè faltava
l'exercici següent, tornava a qualificar, ara la resposta que l'alumna encara no havia
donat («"Window" és correcte per a *finestra*», un «table» correcte i corregit com
«bread»). El check `lostVersion`/`lostMarker` no la veia: té versió correcta i marcador.
Probable agreujant: la nota de la reescriptura de 30.27 («Not any of these…»).

Arranjament (`enforceTurn`, `pacing.ts`): per als guards que només parlen de
l'**exercici** (`isExerciseGuard`: «corregeix però no pregunta» i «ja has preguntat…»)
es conserva la valoració original i es pren de la reescriptura només l'exercici
(`exerciseOnlyOf`, tallat a l'últim encapçalament) amb `spliceFeedback`; la nota diu
«write ONLY the next exercise — no feedback, no correction, no score». Els guards que
parlen de la valoració (no ha corregit, buit de cua…) continuen reescrivint tot el torn.
Tests amb el text de 214531.


### 30.31 `days` 221120: l'SM-2 avança; el que falla és el pla i la cua

Amb l'arranjament de 30.29 (T0 apartats entre dies) **tots els checks de l'SM-2 passen
els cinc dies**: el fallat torna demà, l'encertat que ja se sabia s'allunya, els
intervals surten 1 → 6 → 16 (i 45 a ítems vells), una paraula equivocada no compta com a
sabuda, i la mida de la lliçó és igual als pendents (6, 9, 8, 8, 5). Falten 6 checks:
«cada resposta amb item_id» (7 de 9), «el pla compta les respostes» (1 de 9, 3 de 8, 1 de 5)
i «l'exercici és sobre l'ítem assignat» (5 de 8, 3 de 5); 40 guards per execució (una
execució `journey` en fa 3-4).

**Causa (dues, sumades):**
1. **La reescriptura de 30.30** (aquesta execució va començar abans de l'arranjament):
   correccions inventades de respostes no donades, que a més **creen ítems** que
   l'alumna mai ha fallat («She don't like apples», «He don't like oranges» surten al
   dia 3 i 4).
2. **Ítems duplicats (T3 de 30.29).** L'id d'un ítem d'error és
   `categoria_primers-20-caràcters-de-la-forma-correcta`, amb majúscules. La mateixa
   frase amb categoria diferent (`grammar_` / `capitalization_`) o una majúscula
   diferent és un ítem nou: «I speak English on Mondays» tres vegades a la mateixa
   lliçó (respostes 5, 8 i 9 del dia 2), els «Review 2/9» repetits, el crèdit que diu
   «already counted» (l'empremta és la mateixa) i el pla clavat a `done: 1`.
   `update-db.py` ja no crea un ítem d'error si n'hi ha un altre amb la mateixa forma
   correcta (`find_twin`; sense majúscules ni puntuació; formes de menys de 8
   caràcters no es fusionen). Tests a `test_update_db.py`.

El `days` desa ara, per dia, el pla del servidor (`done`, `credited`, `covered`), les
notes al tutor i els guards a la transcripció.


---

### 30.32 `journey --level A1` 222217: l'exercici sense etiqueta no s'identifica

**Resultat:** 4 de 36 checks fallen a vegades; 12,3 guards per execució (run 1: 2; run 2: 16; run 3: 19).

**Causa:** el tutor del perfil A1 escriu les targetes com `## Review 1/6` + frase entre cometes, **sense** `**Exercise:**`. `exerciseFingerprints` no hi troba res, i això té tres efectes:

- El servidor creu que la resposta no pregunta res → guard «asks nothing» (7-9 per run) i el splice reemplaça exercicis que estaven bé.
- L'obertura (intro amb «~12 min») s'identifica com a exercici `~12 min`; la primera resposta s'acredita a aquest → «already counted: ~12 min» (×5).
- El comptador «Review N/M» i les comprovacions «no insisteix» / «exercicis diferents» hi queden desalineats.

**Canvi (`server/src/pacing.ts`):**

- `NOT_A_LABEL` amplia: items due today, estimated time, duration, total, goal, focus, level, progress.
- Nou `collectReviewCard`: llegeix les targetes `## Review|Exercise|Question N/M` i pren la primera línia amb un subjecte entre cometes. Només s'usa dins `exerciseFingerprints`, després de `collectBlock`.
- Test amb els textos A1 literals (`server/test/lesson-note.test.ts`). Nota: `normalizeLabel` treu els `_` (`She ___ to school` → `she to school`).

**Pendent de mesurar:** reiniciar l'app i repetir `--journey --level A1 --quick --repeat 3`. Esperat: guards molt per sota de 12 i cap «already counted: ~12 min».

### 30.33 Resultats 223056 (`days`) i 223716 (journey A1 amb el fix de 30.32)

**Journey A1 (`--quick --repeat 3`), després de 30.32:** 0 de 36 checks fallen (abans 4), guards 6,7 per execució (abans 12,3). El fix de les targetes sense etiqueta funciona.

**`days` 223056:** 2 checks fallen (dia 3 «l'exercici és sobre l'ítem assignat», dia 5 «el pla compta les respostes»). Aquesta execució va començar **abans** del canvi de 30.32 (`pacing.ts` modificat a les 22:31, l'execució va començar a les 22:30). El dia 5 és el mateix defecte: obertura fingerprintada com `~6 min`, 5× «already counted: ~6 min», pla `1 de 6`. Cal repetir-la.

**Dia 3 (defecte nou):** el botó Lliçó no porta resposta, però el tutor va qualificar una resposta inventada («table» → matí, 2/10) i va preguntar *finestra* en lloc de l'assignat *matí*; tota la jornada es va desplaçar un exercici. El servidor només ho registrava («graded with no answer», no es comptava), però el text arribava a l'alumne. Canvi: nou guard a `turnGuard` (`buttonTurn`, torn obert per un botó + feedback amb `Correct version:`) que demana reescriure només l'obertura.

**Dues preguntes seguides (defecte nou):** el tutor A1 escriu `**Score: 2/10** 🔴 Let's try again. What is the English word for "X"?`. En reemplaçar l'exercici, `spliceFeedback` conservava tota la línia i l'alumne veia la pregunta antiga i després la targeta nova. Ara es talla la frase interrogativa final de la línia de la puntuació.

**Pendent:** la pregunta en línia (sense capçalera) tampoc s'identifica com a exercici, per això salten 4-5 guards «asks nothing» per execució; ara són innocus (el splice la substitueix) però costen una crida cada un. Repetir `--days` i `--journey --level A1 --quick --repeat 3`.

### 30.34 Journey A1 224927: 3 de 36 fallen (una execució cadascuna)

**Guards:** 6,7 per execució (igual que 223716). Cap dels 3 fallos és nou: venen de dos comportaments.

**1. «llibre» torna a Vocabulary (repetició d'un exercici ja contestat).** El guard «asks nothing» reescriu l'exercici; la llista «no aquests, ja els ha encertat» es tallava als **últims 12** (`slice(-12)`), i «llibre» ja havia caigut fora de la llista. Fix: `slice(-40)`. La reescriptura no es torna a validar (un sol reintent); si torna a passar, cal mirar si val la pena una segona validació.

**2. Lliçó 5 de 6 després de 14 respostes (execució 2).** Contradicció entre skills i servidor: `fluent-review/SKILL.md` («One retry, then move on») deixa un segon intent de la mateixa pregunta; la nota de la lliçó diu «exercici DIFERENT». El tutor va escriure «Score 4/10 🔴 Let's try again» i va tornar a preguntar *finestra*; la resposta següent del bench (guionitzada per a la targeta 3) es va gastar en el reintent i la lliçó va quedar a 5 de 6. Decisió: a la Lliçó no hi ha segon intent (l'ítem fallat torna per SM-2); el skill es manté per a la pràctica lliure. Nota nova a `lessonNote`: «No second try in the Lesson either…».

**Pendent de mesurar:** repetir `--journey --level A1 --quick --repeat 3`. Si el tutor de Vocabulary també ha de deixar de fer «Let's try again» (la pregunta en línia fa saltar el guard «asks nothing»), es pot decidir a part.

### 30.35 Resultats 072836 (journey A1) i 073725 (days base/temp06) — l'exercici no segueix l'ítem assignat

**Journey A1 (072836):** 1 fallo de 36 (guards 2,3 per execució, abans 6,7). El fallo: a Vocabulary, el tutor va preguntar «llum» tres cops seguits (el bench responia «no ho sé»); el skill permet un sol reintent i el servidor només ho **registra** («repeated in a row»), no ho impedeix.

**Days base (073725):** fallen `l'exercici és sobre l'ítem assignat` dia 2/3/5. Dues formes del mateix defecte, cap és de comptatge:
- El tutor pregunta un altre ítem de la cua que ell veu (assignat *escola*, pregunta *matí*). La resposta del bench («school») queda com a incorrecta.
- El tutor qualifica com si l'alumne hagués respost l'ítem següent: a la resposta «window» (per a *finestra*) contesta «She go to school → She goes to school, 7/10» i pregunta un tercer ítem. La nota li diu «Her own mistake was "She go to school"» i ho fa servir com si fos la resposta. Tot el dia es desplaça un exercici.

**Resultat final del sweep 073725 (days ×3 per configuració, 12 execucions):** execucions sense cap fallo: base 1/3, temp06 0/3, penal 2/3, totes 0/3. Amb aquesta mostra no es pot dir que una configuració sigui millor que una altra; el soroll el domina el defecte de sota. Guards per execució: base 2,3 · temp06 8,7 · penal 14,7 · totes 7,7.

**Mesura del desplaçament (replay sobre les 354 respostes de lliçó dels transcripts):** ~55 respostes (≈15 %) porten feedback que no és de l'ítem contestat (vocabulari qualificat amb «She go to school → She goes to school», etc.). Explica la major part dels fallos restants: `l'exercici és sobre l'ítem`, `el pla compta`, `tot el pendent surt`, `item_id`, i el `vocabulary_kitchen` amb qualitat 3 (una paraula equivocada qualificada 6/10 amb el feedback de «a apple»).

**Aplicat (2026-09-21):**
1. `followsAssigned` + regla a `turnGuard`: l'exercici ha de portar ≥ 50 % de les paraules de l'ítem assignat («The next exercise must review "X"»); guard d'exercici (es conserva el feedback, se substitueix l'exercici).
2. `feedbackFollowsGrading` + regla a `turnGuard`: el feedback (tot abans de l'última capçalera) ha de portar almenys una paraula de contingut de l'ítem que hi havia a pantalla o de la seva resposta («Your feedback is about something else…»); reescriptura de tot el torn.
3. Nota de la lliçó: «The learner's message is their answer to THAT exercise: grade it, and only it» i «It has not been asked yet, so nothing has been answered for it».
4. Tests a `lesson-note.test.ts`; 351 tests Python OK.

**Pendent de mesurar:** repetir `--days --repeat 3` (esperat: menys fallos d'ítem/pla, més guards al principi). Fals positius possibles del guard 2: feedback d'un ítem de vocabulari que només parla de la traducció sense la paraula original ni la resposta (cap cas als 354 transcripts un cop es compta la resposta). Guard del tercer «mateix exercici seguit» (avui només es registra).

### 30.36 Journey A1 094202 i days 083631 (amb els fixos de 30.35)

**Journey A1 (`--quick --repeat 3`):** 0 de 36 fallen, 2,3 guards per execució (30.32: 4 fallen i 12,3 guards). Estable.

**Days ×3 per configuració:** cap `l'exercici és sobre l'ítem assignat` en les 12 execucions (abans 8 fallos en 12). Execucions perfectes: base 1/3, temp06 2/3, penal 2/3, totes 1/3. Guards per execució: base 4,3 · temp06 6,7 · penal 8,0 · totes 15,7.

**Configuracions.** `penal` i `totes` (presence/frequency penalty, repeat_last_n) degraden el format: penal run 3 i totes runs 2-3 tenen 19-22 guards i fallos de pla/item_id. Exemple (penal 3, dia 2): el tutor escriu «✅ Great job! "finestra" is window» **sense** `Correct version:` ni `Score:` (les penalitzacions castiguen repetir les línies de plantilla), el servidor no ho pot comptar i la lliçó queda encallada a 2 de 6. Base i temp06 no en tenen. Amb 3 execucions no es pot dir base vs temp06 (1 fallo de 3 execucions contra 3), però **les penalitzacions no compensen**.

**Restants i causes:**
1. `vocabulary_table … qualitat 5` (base): defecte del **bench**. L'ítem *taula* té com a resposta «table», que és també el decoy. Ara el decoy no coincideix mai amb la resposta o el contingut de l'ítem (`decoy_for`) i només compta com a decoy una resposta amb `kind == "wrong"`.
2. Temp06 run 1 (dia 3 → 4): el tutor va escriure la matèria en cursiva («What is the English word for *finestra*?»). L'empremta no la trobava: el guard «asks nothing» va saltar sobre un torn correcte, `last_asked` va quedar buit i el pla va comptar 0. Ara `collectReviewCard` accepta subjecte en cursiva (`*…*`) i no confon un camp de la targeta (`*Last reviewed: …*`) amb un subjecte.
3. Mateix run, resposta final: el tutor va anar directe a «Review Session Complete! Accuracy 100%» **sense** corregir l'últim «window». Nou guard: un tancament de lliçó que no qualifica l'última resposta es reescriu; `gradingItem` s'esborra si no hi ha res a pantalla, perquè un missatge posterior a la lliçó no dispari el guard.
4. Base run 3, dia 1: `vocabulary_morning` amb qualitat 2 al bloc de resultats, però `due_date` no s'ha mogut (SM-2 no aplicat només a aquest ítem). No reproduït en cap altra execució; **obert**. Cal el log de l'app per veure si l'actualització d'aquest ítem es va perdre.

**Pendent de mesurar:** `--days --repeat 3` (esperat: tancaments amb nota i sense guards falsos amb cursiva) i `--journey --level B1`. Comparació base/temp06: fer-la amb `--repeat 5` per configuració, només sense penalitzacions.

## Pendent d'afegir en properes tandes

- Poda de l'historial (quan 6.1 digui que cal).
- Mestria dels patrons d'error quan l'alumne els encerta (avui no puja mai).
- Nom del fitxer de resultats per habilitat (S5), si es decideix canviar-lo.
- Lectura de sessions anteriors pel tutor (S4), si es fa l'eina.
- Supervisió amb systemd (P1-8), si es fa.
- **Temes per alumne (`topics.txt`, § 30.28):** implementat i amb tests, però sense mesurar
  amb el model. Analitzar-lo després: `--topics`, i si els temes de la llista s'acaben
  notant a Writing / Mix sense trencar la cua.
- Punts oberts del tutor de 30.29: exercici d'ortografia mal format (*because*) i ítems
  duplicats per categoria. (El de «correcció d'un altre exercici» es tanca a 30.30.)

## 30.37 Days 111324 i journey 125602: dues causes d'empremta (2026-09-21)

**Resultat.** Journey base: 0/36 falles, 1.3 guards/exec. Days (4 settings × 3 execucions): 4 falles en 4 configuracions, totes de tipus «el pla compta les respostes» o «va fallar ahir i no torna».

**Causes trobades** (llegint les transcripcions, no per hipòtesi):

1. **Targeta sense encapçalament numerat.** Base, execució 1, dia 2: la targeta és `# 🔄 Today's Spaced Repetition Review` + `**Type:**…` + pregunta, sense `## Review N/M` ni `**Exercise:**`. No s'empremtava (`last_asked: []` tot el dia), el servidor creia que el tutor «no preguntava res», va disparar el guard cada torn, no va acreditar res (`credited 0`) i el reescriure va deixar el feedback d'un altre ítem; la resta del dia va anar desplaçada.
2. **Subjecte de dues lletres.** Temp06 execució 3 i totes execució 1, dia 4: `What is the English word for "pa"?` no s'empremtava (mínim 3 caràcters). `last_asked` va quedar a «aigua»; la resposta «bread» s'hi va atribuir → `already counted: aigua` → «bread» sense acreditar. Explica els dos «el pla compta…» i «no torna» restants.
3. **No és bug nostre:** a `totes` el tutor va escriure `✅ Close! … ❌ "bread" → "bread"` amb 10/10 i va ometre la nota en una altra resposta (les penalitzacions degraden el format, ja anotat a 30.36).

**Canvis** (`server/src/pacing.ts`):

- `collectReviewCard`: dues passades (`Review N/M` i títol `Spaced Repetition Review`); no una sola alternança, perquè una obertura de lliçó té el títol i la targeta numerada.
- Subjecte entre cometes de 2 lletres acceptat (`collect`, `collectBlock`, targeta).
- Tests: targeta amb només títol, `"pa"`, `"pa"` després de feedback, obertura amb títol + targeta numerada.

**Verificat:** proves TS passen (fitxer complet). **No verificat amb el model:** cal reiniciar l'app i repetir `--days --repeat 3`.

## 30.38 Fase 0 del camí d'aprenentatge (2026-09-21)

Canvis: `hooks/curriculum.py` (lector, estat derivat, informes, etiquetatge `competency_of`, `rebuild`, `coverage`), `scripts/flowed-sim-path.py` (alumne simulat, `--calibrate`), `curriculum/en-A2.md` (v1, amb `Tags:`), `tests/test_curriculum.py` (35 tests) i **una** línia de servidor: `runAutoPersistence` crida `curriculum.py rebuild --auto --quiet` després d'`accumulate-session` (try/catch propi). Cap comportament de l'app canvia; sense fitxer de currículum per al perfil no fa res.

Verificat: tests Python 387 OK, TS OK (test de codi font del cablejat). **No verificat amb el model ni amb l'app real.** Requereix reiniciar l'app (canvi a `agent.ts`) i el bench rebutjarà un build antic.

Resultat de journey 125602 (base): 0 falles, 1.3 guards/exec, però és el build anterior als canvis de 30.37 i 30.38; no els confirma.


## 30.39 Days 185739: el guard «no ho ha corregit» corregia l'exercici següent (2026-09-21)

**Resultat** (build `ciip5g`, coincideix amb el disc; ja amb els canvis de 30.37): base 1 falla (guard/exec 2.0), temp06 0 (2.0), penal 0 (0.3), totes 4 (3.7, 3 en una sola execució). Les dues causes de 30.37 (targeta amb només títol, subjecte de 2 lletres) no hi surten.

**Causa de les que queden** (base execució 1 dia 2; totes execució 3 dia 2, plan 2 de 6): el tutor respon a una resposta correcta amb «✅ Perfect! X is correct.» + la targeta següent, **sense «Correct version» ni «Score»**. El guard «has respost i no ho corregeixes» demana reescriure el torn sencer, i el model escriu el feedback de la **targeta següent** (la que acaba de posar) o repeteix el mateix. Resultat: resposta no acreditada i tot el dia desplaçat un exercici. Amb `totes` (penalitzacions) el format degrada més, com ja es veia a 30.36.

**Canvi:** guard simètric al d'«exercici només» (30.20):
- `isFeedbackGuard(note)`: la nota «does not grade it» que no és la de tancar la lliçó.
- L'exercici de la primera resposta es manté (`trailingExercise`); el reintent només demana el feedback (veredicte, `Correct version:`, `**Score: N/10**`, sense exercici nou).
- `mergeFeedbackOnly`: feedback nou + exercici original; si el reintent no té `Correct version` i nota, o parla d'un altre ítem que el contestat (`feedbackFollowsGrading`), es manté la primera resposta.

**Verificat:** 8 tests TS nous passen, l'agent es compila; res amb el model. Requereix reiniciar l'app. Fer `--days --repeat 3`; mirar sobretot `totes`, on el format és pitjor.
**Límit conegut:** si el tutor no escriu nota ni al reintent, la resposta queda sense acreditar (la primera resposta es manté).

## 30.40 Fase 2 i escenari `curriculum` (2026-09-21)

**Canvis de servidor** (`pacing.ts`, `agent.ts`, `tools.ts`): a Mix i Vocabulary el servidor demana a `curriculum.py next` la competència de l'exercici següent i la posa a la nota (substitueix `topics.txt`; Vocabulary només competències amb paraules; una paraula pendent de repàs mana). `followsCompetence` + regla a `turnGuard` (`must practice "<nom>"`, reescriu només l'exercici); `notes.jsonl` guarda `competence`; el registre porta `competency` només si l'exercici seguia la competència i no és de vocabulari. Detalls a ESQUEMA-APRENENTATGE § 6.6.

**Escenari `curriculum`** (`flowed-e2e.py`, `flowed-bench.sh --curriculum`): N dies d'un alumne simulat A1→A2 en pràctica lliure, amb comprovacions i informe del camí (§ 6.7). `flowed-advance-day.py --keep-records` (desplaça `ts` en lloc d'arxivar). `reset`/`restore` també aparten `learner-path.json`. Cal tenir en compte que el bench deixa el perfil de proves amb `target_level=A2`.

**Verificat:** tests Python 398 OK (+ tutor fals de l'escenari, 2 tests), tests TS OK, `bun build` de l'agent OK. **No verificat amb el model ni amb l'app real.** Requereix reiniciar l'app. Proposta de primera prova: `scripts/flowed-bench.sh --curriculum --quick --repeat 1` (~30 min, 5 dies × 9 respostes).

**Riscos a mirar en el primer resultat:** (1) que els `signals` donin falsos positius al guard (mirar `guards.jsonl` amb `must practice`); (2) que el tutor de Mix ignori la nota (comprovació «segueix la competència»); (3) que la Vocabulary rebi poques competències de vocabulari; (4) que el model de l'alumne es confongui amb els exercicis en català.

## 30.41 Curriculum 201107 (primer resultat real) i evidència per competència (2026-09-21)

**Resultat** (base, 1 execució, 5 dies, alumne `steady`): 3 falles — servidor assigna competència a 30 de 45 exercicis; el tutor fa l'exercici de la competència 11 de 27; respostes assignades 16 de 45 (`word-not-in-list` 28). Guard 26×. Barra 2 % → 13 %. Registres i qualificació bé.

**Causes trobades:**
1. **Bug meu, Vocabulary:** `vocabularyDueNote()` sempre retorna text (la regla «cada targeta és un nom, verb o adjectiu»), i «cedeix davant d'una paraula pendent» es va escriure com `v ? null : …`. Resultat: 0 de 15 torns de Vocabulary amb competència; el tutor va posar les seves paraules (house, kitchen, left…) i van quedar 28 registres sense competència. Ara només cedeix si hi ha «Words due for review today».
2. **El tutor llegeix la nota malament a Mix:** exercicis «Vocabulary (Easy): What is the Catalan word for "object pronouns"?» o preguntes obertes que qualsevol resposta satisfà («What do you do every day?» → 10/10); mateix exercici repetit (Exercise 1 = Exercise 3; «Can I borrow **your** book?» dos cops). La nota ara diu què és l'exercici (frase: buit, correcció o pregunta que només es pot respondre amb l'estructura; mai targeta de vocabulari, mai el nom del tema), dóna la **forma d'un `Check`** de la competència com a exemple (rotant) i, per a vocabulari, «una paraula d'aquesta llista, cap altra».
3. Quan el tutor no demana cap exercici després del feedback, el bench encara respon l'anterior amb l'etiqueta de la competència nova. Les comprovacions ho reflecteixen com a «el tutor no fa l'exercici»; no és un problema del bench.

**Nou al bench:** la transcripció porta, per dia, les notes del servidor (amb `competence`) i els guards; el final imprimeix els guards per tipus. Sense això, els 26 guards no es podien explicar. El sweep ja no avisa de «cua perduda» a `curriculum` (la buida a propòsit).

**Evidència per competència (`Depth:` / `Weight:` a `curriculum/en-A2.md`, v2):** sis respostes no demostren un temps verbal. `light` = 8 respostes, ≥ 3 dies (últimes 8); `normal` (per defecte) = 12, ≥ 5 dies (últimes 10); `deep` = 20, ≥ 7 dies (últimes 12); sempre ≥ 80 %. `Depth` també fixa els exercicis/dia mentre s'aprèn (nova 3/3/4, repàs 2/2/3) i `Weight` (1-3) pesa a la barra. Proposta inicial: deep = present simple vs continuous, past simple, prepositions, infinitive/gerund; light = vocabulari i `suggestions`; la resta normal. L'informe mostra `n/necessàries`. Efecte al simulador: amb `ready_share 0` el checkpoint s'obre al dia ~10 amb 0/16 consolidades; amb 0,5 al dia ~30, `true p` 0,86-0,95 (fast/steady). **Recomano `ready_share = 0,5` ara**; queda a 0 fins que ho confirmis.

**Verificat:** Python 407 OK, TS OK, `bun build` OK. **No verificat amb el model.** Cal reiniciar l'app i repetir `--curriculum` (amb 5 dies les competències deep no arribaran a consolidar-se: el que es mira és assignació, seguiment i registre; per veure el camí llarg, `--days 12`).

## 30.42 Curriculum 203946 (amb els canvis de 30.41): els `signals` eren massa estrets (2026-09-21)

**Resultat** (base, 1 execució, 5 dies): assignació **bé** (abans 30/45), etiquetatge **bé** (abans 16/45), 12/14. Falles: «el tutor fa l'exercici» 12 de 22 i «puntua el vocabulari» 5 de 6. Guard 19× (7 «must practice» a pronouns, 4 «ja ho has preguntat» formatge/cap, 3 «no pregunta res», 2 més «must practice», 1 revisió inventada).

**Lectura:** el tutor ja fa exercicis de frase amb buit, bons («That is not your phone. It is ___ phone.»). Els 7 guards de pronouns eren **falsos positius meus**: els `signals` eren els `Tags` (`me, him, mine…`), que són paraules de la **resposta**, i el buit les amaga. Igual a shopping («Could I ___ the menu»). La falla 12/22 és la mateixa.
La falla de vocabulari (5/6) era del bench: `bank_item` va trobar «home» (= man) dins «describing your home» i va respondre «man» a un exercici de llista de mobles. Ara el bench només usa el banc si la targeta té la paraula en una línia etiquetada.

**Canvi:** clau nova `Signals:` al `.md` (paraules que surten a l'**exercici**, generoses), separada de `Tags:` (que assignen respostes ja fetes). Sense `Signals:`, fa servir els `Tags` sense `#`. Reavaluat sobre la transcripció 203946: 22 de 22 (abans 12).
**Límit conegut:** amb llistes així de generoses, algunes competències (prepositions, modals, past continuous, present perfect) passen gairebé qualsevol frase; el guard només enxampa la deriva grollera (targeta de vocabulari, un altre tema sense cap d'aquestes paraules). Les llistes s'ajusten al fitxer. Els 22/22 s'han comprovat sobre les mateixes dades on s'ha afinat, no és una mesura independent.

**Pendent de mirar amb el model:** el guard hauria de baixar de 19 a uns pocs; repetits de vocabulari («formatge», «cap») i «no pregunta res» segueixen sent del tutor.

## 30.43 Curriculum 205425: 14/14, guard 12× (2026-09-21)

Tot passa (assignació, seguiment, etiquetatge, vocabulari, camí). Guards de 205425, llegits de `.metrics/guards.jsonl` del perfil: 4 «corregeix i no pregunta res» (cartes de Vocabulary on el tutor repeteix «pa»), 2 «ja has preguntat» (sala, give to them), **2 `must practice` de prepositions = falsos positius meus** («The party is ___ Saturday ___ 8 o'clock», amb títol «Prepositions of Time and Place»), 2 «graded with no answer» (obertura de Vocabulary), 1 revisió inventada al menú, 1 «no ho has corregit».
**Canvi:** un exercici amb el **nom de la competència** al títol la segueix (`followsCompetence`, també al bench), i `Signals:` de prepositions amplia (dies, mesos, parts del dia, `preposition(s)`, `when`, `where`, llocs). **Pendent:** el tutor de Vocabulary repeteix «pa» a cada sessió (la nota llista sempre les mateixes paraules sense usar); mirar-ho quan es faci `--days 12`.

## 30.44 Camí de l'alumne al web (2026-09-21)

`hooks/curriculum.py json` (`path_view`) → `GET /api/fluent/path` → barra a la capçalera + secció a dalt del 📊 Progrés + bloc plegable «Detall (docent)» (vegeu ESQUEMA §6.2). Proves: `PathViewTest` (3, Python; suite 411 OK), `web-render.test.ts` (13 comprovacions noves: res sense currículum, escapament, docent plegat i sense alertes fora, barres, promoció), `bun build src/http.ts` OK. **No verificat a la pantalla real** (reinicia l'app i obre 📊; cal un perfil amb `target_level` que tingui currículum: el bench el deixa a A2 al perfil de proves).

## 30.45 Curriculum 211700: etiquetatge 61/108 (2026-09-21)

20/21. Falla: «les respostes queden assignades» (61 de 108, mínim 70%). Guard 24× (11 «ja has preguntat», 7 `must practice`, 2 «graded with no answer», 3 repetits de vocabulari).
**Causa (mesurada als registres):** 41 targetes de vocabulari sense assignar. `_vocab_word` només mirava `item_id`, les correccions o la **resposta**; el registre desa la paraula demanada a `exercise` («cheese») i l'alumne respon en català («formatge»), així que no coincidia amb cap llista. Efecte doble: (1) no s'assignava, (2) les paraules **mai es comptaven com a usades**, per això la nota tornava a oferir bread/cheese/butter/rice cada dia (el «pa» repetit pendent des de 30.43). A més, el tutor etiqueta com `vocabulary` exercicis de frase de Mix («Suggest a place to go…» / «mine») i es tractaven com a targetes.
**Canvi (`hooks/curriculum.py`):** `_vocab_candidates`/`_vocab_hit` (paraula de l'ítem, `exercise` si té ≤3 paraules, correccions, resposta si era bona); si una targeta no troba paraula, prova l'etiquetatge de gramàtica (els `item_id` `vocabulary_*` no); la nota usa `_vocab_hit` per saber les paraules usades. Sobre els mateixos 108 registres: **83 assignats (77%)**. Restants: targetes en català amb resposta errònia (llit→teeth), no es poden assignar sense diccionari, i el tutor s'ha desviat de la llista (cuina/llit/dormir a «Health»): correcte no assignar-les. 3 tests nous, 60 al mòdul.

## 30.46 Curriculum 224510: 21/21, guard 36× (2026-09-21)

Tot passa (etiquetatge 87/108 = 81%, `ready_share: 50` al fitxer). Guard 36× (abans 24): 10 «ja has preguntat», 18 `must practice`, 4 «graded with no answer», resta 1 cadascun. Llegits de `.metrics/guards.jsonl` (`head` = la resposta del tutor): dels 9 `must practice` que es veuen, **3 són reals** (targetes de vocabulari «braç», «llum» quan tocava countable) i **6 falsos positius meus** perquè el buit amaga el senyal: «You ___ wear a seatbelt… It's the law» (modals), «How ___ water / sugar…» (countable), «I ___ go to the party tonight, but I'm not sure» (modals), «I ___ (help) you… this evening» (future, «plans» ≠ «plan»).
**Canvi:** `Signals:` ampliats a `curriculum/en-A2.md` per countable (`how`, noms de mesura), modals (`wear`, `law`, `rules`, `not sure`, `maybe`, `might`…) i future (`plans`, `this evening`, `later`, `weekend`, `next`…). Mateix límit que 30.43: és afinar sobre dades ja vistes; els senyals amb buit no es poden jutjar bé. Si torna a passar, el pas següent és fer que el guard només actuï amb evidència positiva de deriva (targeta de vocabulari, o senyals d'una altra competència) i no per absència de senyal.
Test `ready_share` ja no fixa el valor del fitxer (l'Albert l'edita).

## 30.47 Currículum A1 (2026-09-21)

`curriculum/en-A1.md` v1, a partir de l'esborrany de l'Albert. Correccions: front matter trencat (`## language:` sense `---` → el fitxer no es trobava per nivell); afegits `version`, `status`, `ready_share`, `Depth`, `Weight`, `Tags` (categories vàlides), `Signals`; `Can do`, enunciats i `Check` passats a anglès (cap dependència de la llengua nativa: `Translate (CA->EN)` → `Meaning`); tipus `Ask politely` → `Ask`; `Words` sense «etc.» ni `autumn/fall` (números fins a 100 i 12 mesos complets); seccions `## Gramàtica/Funcions/Vocabulari` (les numerades sortien tal qual al web); `assumes` eliminat (el nivell zero és el punt de partida, explicat a la capçalera); `checkpoint_items` 15 → 20 (14 core). `validate` OK, sim `flowed-sim-path.py --curriculum` OK, 415 proves OK.

## 30.48 Cursos, prova de nivell a l'app i escenari ladder (2026-09-21)

Bench 230509 validat abans de començar: 21/21, guard 27×, etiquetatge 91 %.
**Fet** (disseny a ESQUEMA §6.8–6.10): (1) tall de curs (`close_course`, certificats, arxiu, avís, `find_curriculum` per escala, registres anteriors al `start_ts` no compten) + simulador encadenat `flowed-sim-path.py --ladder` (A1 → tall → A2 per fast/steady/weak); (2) prova de nivell dins l'app, feta pel servidor sense LLM (Python + `agent.ts` + web: botó 🧪, avís de curs acabat); (3) `--scenario ladder` a `flowed-e2e.py` (A tutor real A1 · B historial sintètic fins que s'obre la prova · C prova pel servidor `--test-mode pass|fail` · D tall o «no tall» · E dos dies d'A2), `flowed-bench.sh --ladder` / `--ladder-fail`.
**Proves:** suite Python 440 OK (CourseTest, LevelTestTest —totes les respostes esperades dels Check d'A1 i A2 s'accepten—, LadderScenarioTest: lectura de les preguntes, historial sintètic → llest, prova → certificat i A2, tot malament → cap tall); `web-render.test.ts` i `lesson-note.test.ts` OK; parts TS sense canvis des de l'última verificació. Fora de l'app, el mateix flux (historial sintètic → prova → certificat → A2) passa per fast/steady/weak (24 preguntes).
**No verificat en viu:** el camí real de la prova (servidor + web) i l'escenari `ladder` contra el tutor, cal executar-los; tampoc la pantalla (🧪, avís).
Decisions de l'Albert: no s'arrosseguen competències febles; «competències personalitzades» és futur.

