# Portar Fluent a llvm (VM a llvm, 4060 Ti 16 GB) — pas a pas

**Objectiu:** tenir l'app corrent a la màquina de producció per trobar-hi els
errors ara i no al final. No cal que sigui la versió definitiva.

**Com llegir-ho:** cada pas té una comprovació. Si una comprovació falla, atura't
i apunta-ho a *Incidències* (al final) — no continuïs, perquè els passos següents
donen per bo l'anterior.

**Totes les comandes es poden copiar i enganxar tal qual.**

Convenció: `[railab]` s'executa a la màquina d'ara, `[llvm]` a la nova.
La màquina física és **rapve**; la VM on corre tot es diu **llvm**, i és on
s'executa tot el que va marcat `[llvm]`.

Destí final: **`/opt/fluent`** → symlink a `/opt/fluent_dev2-<versió>`.

---

## El que canvia respecte l'últim cop que ho vas fer

Segueix sent **copiar el directori i canviar l'`.env`**. Però des de l'última
migració el runtime ha canviat de soca-rel, i hi ha dues coses que abans no
existien:

| | Abans (opencode) | Ara |
|---|---|---|
| Qui serveix la web | `opencode web` | **servidor propi amb bun** → cal `bun install` (pas 3) |
| Dependències | cap a copiar | `js-yaml` a `server/node_modules/` — **sense això no arrenca** |
| BD de sessions | `.opencode/opencode/opencode.db` | `sessions/sessions.db` — el `rsync` del perfil ja se l'endú |
| Veu | no hi era | piper, opcional i apagat per defecte (pas 7) |

O sigui: **el teu procediment de sempre + `bun install`**. La resta del document
són comprovacions perquè, si alguna cosa no ha arribat, se sàpiga en quin pas i
no tres hores després.

I una dada que no tenim de cap màquina: **36864 amb f16 sobre 16 GB** (pas 5).
És l'únic pas amb risc real.

---

## Estat (2026-09-14)

| Pas | Estat |
|---|---|
| 0. Pre-flight railab | ✅ 169 tests, `ctx 36864` + `f16` |
| 1. Requisits llvm | ✅ py 3.12, openssl 3.0, docker 29.8, `--gpus all` OK, bun |
| 2. Còpia del codi | ✅ a `~/projects`, **pendent** el pas a `/opt/fluent` |
| 3. `bun install` | ✅ 9 paquets |
| 4. `.env` | ✅ `backend docker`, `port 12321`, `ctx 36864`, `f16` |
| 5. Model + mesura VRAM | ⏳ **el següent, i l'únic amb risc** |
| 6–9 | ⏳ |

GPU a llvm en repòs: **18 MiB de 16.380**.

---

## 0. Abans de moure res `[railab]`

```bash
cd ~/projects/fluent_dev2
python3 -m unittest discover -s tests -q
python3 scripts/flowed-config.py --json
```

*Esperat:* els tests en verd, i `ctx: 36864` amb `kv_type: f16`.

Apunta què tens ara, per poder comparar després:

```bash
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
ls ~/.fluent/
```

---

## 1. Què ha de tenir llvm `[llvm]`

```bash
python3 --version          # 3.9+
openssl version
docker --version
docker run --rm --gpus all ubuntu nvidia-smi   # el toolkit de NVIDIA funciona
command -v bun || echo "FALTA bun"
```

Si falta bun:

```bash
curl -fsSL https://bun.sh/install | bash
```

*Esperat:* les quatre primeres responen i `docker run --gpus all` ensenya la
4060 Ti. Si això últim falla, no continuïs: el model no podrà arrencar.

---

## 2. Copiar el codi `[railab]`

`obsolet/` són 63 MB de runtime arxivat i `node_modules` es regenera: fora tots
dos. El `.env` **no** es copia — a llvm se'n fa un de propi al pas 4.

```bash
cd ~/projects
rsync -av --delete \
  --exclude 'obsolet/' \
  --exclude 'node_modules/' \
  --exclude '__pycache__/' \
  --exclude '.env' \
  --exclude '_to_delete/' \
  fluent_dev2/ llvm:~/projects/fluent_dev2/
```

*Esperat:* ~7 MB transferits.

### 2b. Al seu lloc definitiu `[llvm]`

L'app **escriu dins del seu propi directori**, així que ha de ser de l'usuari que
la corre:

| Fitxer | Quan s'escriu |
|---|---|
| `.env` | el crees tu |
| `config/fluent.json` | `flowed-tts.sh install` hi escriu la veu |
| `.flowed-active` | només per `/fluent-use` (camí d'admin) |
| `__pycache__/` | a cada execució de qualsevol script Python |

Els PID i els logs van a `/tmp`, i les dades a `~/.fluent`: aquests són
independents d'on visqui el codi.

```bash
sudo mkdir -p /opt/fluent_dev2-0.4
sudo rsync -a --delete ~/projects/fluent_dev2/ /opt/fluent_dev2-0.4/
sudo chown -R albert:albert /opt/fluent_dev2-0.4
sudo ln -sfn /opt/fluent_dev2-0.4 /opt/fluent
```

**Treballa sempre des de `/opt/fluent`.** Quan hi hagi una 0.5, la puges al
costat i mous el symlink: l'actualització és instantània i tornar enrere també.
Un servei systemd, si algun dia n'hi ha, apunta al symlink i no a la versió.

Quan `/opt/fluent` funcioni, esborra la còpia de `~/projects` — dos repos a la
mateixa màquina acaben amb tu editant el que no toca.

```bash
ls -l /opt/fluent && ls /opt/fluent/scripts/ | head
```

---

## 3. Dependències del servidor `[llvm]`

```bash
cd /opt/fluent/server
bun install
```

*Esperat:* crea `server/node_modules/`. El servidor importa `js-yaml`; sense
això no arrenca.

```bash
cd /opt/fluent
python3 -m unittest discover -s tests -q
```

*Esperat:* els mateixos **169** que a railab (un `skipped` és normal). **Aquesta és la primera
comprovació de debò que el codi ha arribat sencer.**

---

## 4. Configuració de la màquina `[llvm]`

```bash
cd /opt/fluent
cp .env.rapve .env
python3 scripts/flowed-config.py --json
```

*Esperat:*
- `backend: docker` (a railab és `native`)
- `port: 12321` (a railab és 12322)
- `ctx: 36864`, `kv_type: f16` — venen de `config/fluent.json`, iguals a les dues màquines

Si el `ctx` surt 32768, hi ha un `FLOWED_DEEP_CTX` descomentat a l'`.env`:
comenta'l. L'`.env` mana sobre el config.

---

## 5. El model, i la mesura que importa `[llvm]`

Aquest és el pas amb risc real: **36864 amb f16 són ~14.600 MiB previstos sobre
una targeta de 16.384.** El marge és d'uns 1,7 GB i mai s'ha mesurat aquí.

### 5a. Dues coses que han d'existir i NO venien amb el rsync

```bash
ls -l /home/albert/aidev/scripts/docker-llama-default.sh
ls -lh /home/albert/aidev/models/Qwen3-14B-Q4_K_M.gguf
```

*Esperat:* el primer executable, el segon ~9 GB. El model no viatja amb el repo.

### 5b. El swap amb el model que ja hi ha

A llvm el port **12321** el comparteixen el teu model *default* i el nostre. El
canvi el fa l'start sol, i el desfà l'stop:

| | Què passa al port 12321 |
|---|---|
| `flowed-start.sh` | si l'ocupa un altre → `FLOWED_DEFAULT_MANAGER stop`, espera que s'alliberi, puja el nostre |
| `flowed-stop.sh` | **sempre** `FLOWED_DEFAULT_MANAGER start` — et torna el default |
| port ocupat i sense manager | avorta amb `no robo ports` |

O sigui: **sí, arrencar Fluent baixa el model que estigui funcionant**, i
`flowed-stop.sh` te'l torna. L'estat viu a `/tmp/fluent-deep-docker.state`; si
hi és i el port respon, l'start respecta el que hi ha i no toca res.

Fes primer el pla i llegeix-lo abans de continuar:

```bash
cd /opt/fluent && scripts/flowed-start.sh --dry-run --yes
```

```bash
nvidia-smi --query-gpu=memory.used --format=csv        # abans, amb tot aturat
scripts/models/docker-llama.sh
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

*Esperat:* el contenidor puja i la línia d'arrencada diu `ctx 36864, kv f16`.

**Decideix segons el número:**

| Mesura | Què fer |
|---|---|
| < 15.000 MiB | Endavant |
| 15.000–15.800 | Va just. Baixa a `"ctx": 32768` a `config/fluent.json` |
| No arrenca / OOM | `"ctx": 32768` primer; si encara falla, `"kv_type": "q8_0"` |

**Apunta el número real.** És l'única dada nova d'aquesta migració.

```bash
curl -s http://127.0.0.1:12321/health
curl -s http://127.0.0.1:12321/v1/models | python3 -m json.tool | grep -i ctx
```

*Esperat:* `{"status":"ok"}` i el `n_ctx` que has configurat. Si el `n_ctx` surt
més petit del que demanes, llama.cpp l'ha retallat (el sostre de Qwen3-14B és
40960).

---

## 6. Les dades dels alumnes `[railab]`

> ⚠️ `alex-en` i `sam-en` estan **en ús**. Copia-les només quan decideixis que
> llvm passa a ser la màquina bona, i **amb les webs aturades a railab** —
> copiar una BD de sessions mentre s'escriu la pot deixar a mitges.

Per a la prova, comença només amb `demo-en`:

```bash
scripts/flowed-web.sh --stop --port 4102     # atura la web d'aquest perfil
rsync -av ~/.fluent/demo-en/ llvm:~/.fluent/demo-en/
```

*Esperat:* hi van les 6 BD JSON, `sessions/sessions.db`, `results/`,
`.records/`, `.metrics/`, `.daily/` i el `.web-password` (la contrasenya viatja
amb el perfil, o sigui que el login no canvia).

```bash
ssh llvm 'cd /opt/fluent && python3 scripts/flowed-check.py all demo-en'
```

*Esperat:* el mateix que a railab — mateix nivell, mateixa ratxa, mateixos
patrons. **Si algun número balla, atura't.**

---

## 6b. Tancar les sessions velles (sense tocar-ne les dades)

Els perfils que vénen del build antic porten sessions que no es van tancar mai
(alex-en 9, sam-en 6). **Avui ja s'ignoren** — el sweeper només mira 24 h
enrere — però val la pena deixar-ho explícit perquè cap canvi futur d'aquesta
finestra les pugui despertar i sumar-les a les bases una segona vegada.

**Primer, còpia del perfil sencer.** L'script només copia `sessions.db`; això
cobreix tot, i triga un segon:

```bash
cd ~
tar czf ~/fluent-backup-$(date +%F-%H%M).tgz .fluent/alex-en .fluent/sam-en
ls -lh ~/fluent-backup-*.tgz
```

Per restaurar: `cd ~ && tar xzf ~/fluent-backup-<data>.tgz`.

> **On queda cada còpia:** si executes això a llvm, tant el `.tgz` com els
> `sessions.db.bak-*` es queden **a llvm**. I railab segueix sent una tercera
> xarxa: si els perfils hi van arribar per `rsync`, els originals hi són
> intactes.

```bash
python3 scripts/close-old-sessions.py --profile alex-en --dry-run
python3 scripts/close-old-sessions.py --profile sam-en --dry-run
```

*Esperat:* la llista de sessions que es marcarien, i `Les 6 bases de dades NO
s'han tocat.`

```bash
python3 scripts/close-old-sessions.py --profile alex-en
python3 scripts/close-old-sessions.py --profile sam-en
```

*Esperat:* deixa una còpia `sessions.db.bak-<data>` i marca les sessions.

```bash
python3 scripts/flowed-check.py sessions alex-en
python3 scripts/flowed-check.py all alex-en
```

*Esperat:* les velles com a `tancada ✅`, i **exactament els mateixos números**
a `all` que abans: nivell, ratxa, patrons, cua. Si algun s'ha mogut, l'script ha
fet alguna cosa que no havia de fer — restaura el `.bak` i apunta-ho.

> **No s'incorporen.** Les dades per torn d'aquelles sessions ja són a les bases
> (la Capa A les escrivia al moment). Reprocessar-les ara arriscaria doble
> compte, i els resums de fa tres setmanes no ho valen.

> Afegeix `--legacy` si vols marcar-les també a la BD antiga (`.opencode/`). Per
> defecte no s'hi toca, perquè el build anterior encara la fa servir.

---

## 7. Veu — TTS `[llvm]`

Opcional, però és el que fa que l'alumna pugui **sentir la frase ben
pronunciada**. Ve apagat: si te'l saltes, no es dibuixa cap botó i no falla res.

**Cal internet en aquesta màquina** (baixa ~80 MB de GitHub i Hugging Face).

### 7.1 Instal·lar

```bash
cd /opt/fluent
scripts/flowed-tts.sh install en_GB-alba-medium
```

Això fa tres coses de cop: baixa el binari de piper a `~/.fluent/_tts/piper/`,
baixa la veu a `~/.fluent/_tts/voices/`, i escriu la ruta de totes dues a
`config/fluent.json` deixant `tts.enabled: true`.

Els tres perfils aprenen **anglès**, així que amb `en_GB-alba-medium` n'hi ha
prou per als tres. Per a una altra llengua:
`scripts/flowed-tts.sh voice de_DE-thorsten-low`.

### 7.2 Comprovar que corre sense dependre del teu shell

A railab va caldre tocar el `.bashrc` perquè piper trobés les seves pròpies
`libespeak-ng` i `libonnxruntime`. **Aquí no cal**: ho fa el codi
(`ttsEnv()` a `tts.ts` i `piper_env` a l'script), i és important que sigui així
perquè el servidor no llegeix cap perfil de shell si un dia l'arrenca systemd.

```bash
scripts/flowed-tts.sh status
```

*Esperat:* `(corre sense dependre del teu .bashrc ✅)`.

Si surt l'avís, prova-ho **sense** el teu perfil de shell, que és com ho farà el
servidor:

```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin bash -lc 'cd /opt/fluent && scripts/flowed-tts.sh status'
```

### 7.3 Provar-ho fora de la web

```bash
scripts/flowed-tts.sh say "Good morning, how are you today?"
aplay /tmp/tmp*.wav        # o copia el .wav i escolta'l on puguis
```

*Esperat:* un `.wav` i un `Real-time factor` molt per sota d'1 (a railab: 0,049,
o sigui 20× més ràpid que temps real). **Si aquí no sona, no continuïs**: el
problema és de piper, no de Fluent.

### 7.4 Lligar-ho al perfil

```bash
python3 scripts/flowed-check.py tts demo-en
```

*Esperat:* `enabled: True`, la veu amb ✅, i `aquest perfil: aprèn English →
sonarà 🔊`. Si diu `sense veu`, la llengua meta del perfil no coincideix amb cap
veu instal·lada — i llavors **no sonarà res**, que és el comportament volgut: mai
llegeix amb una veu que no és la de la llengua.

**Reinicia les instàncies web** perquè agafin la configuració nova.

### 7.5 ⚠️ Després de cada `rsync` des de railab

`flowed-tts.sh` escriu dins `config/fluent.json`, i aquest fitxer **viatja amb
el `rsync`**. O sigui que una sincronització des de railab et deixarà el `tts`
apagat un altre cop. No cal reinstal·lar res — els fitxers segueixen al seu
lloc — només tornar-ho a lligar:

```bash
scripts/flowed-tts.sh install en_GB-alba-medium    # detecta que ja hi és i només reescriu el config
python3 scripts/flowed-check.py tts demo-en
```

---

## 8. Arrencar `[llvm]`

```bash
cd /opt/fluent
scripts/flowed-start.sh --dry-run --yes
```

*Esperat:* el pla diu `backend=docker` i les webs que toquen. **Llegeix-lo abans
de continuar.**

```bash
scripts/flowed-start.sh --yes
```

*Esperat:* el model ja hi era (pas 5) i puja una web per perfil.

---

## 9. Prova de fum

Obre la web de `demo-en` des d'un altre dispositiu i comprova, per ordre:

- [ ] **9.1** Entra amb la contrasenya de sempre.
- [ ] **9.2** Arrenca sol amb la salutació. Si surt l'avís de "perfil no
  configurat", el `learner-profile.json` no ha arribat bé (torna al pas 6).
- [ ] **9.3** La barra de botons es veu sencera, amb el badge de 🎓 Lesson.
- [ ] **9.4** Fes **tres** exercicis. El comptador `✏️ N` ha de pujar i la cara
  amb ell.
- [ ] **9.5** Prem 🏁 End: resum i comiat.
- [ ] **9.6** Els números no s'han perdut:
```bash
python3 scripts/flowed-check.py all demo-en
python3 scripts/flowed-check.py metrics demo-en
```
  *Esperat:* els temps per torn de llvm — **la comparació amb railab és el que
  volem saber d'aquesta màquina.**

---

## 10. Tornar enrere

Res del que fas a llvm toca railab. Per desfer:

```bash
# [rapve]
scripts/flowed-stop.sh
docker rm -f qwen-fluent-server
```

A railab tot segueix igual: el codi, els perfils i les webs no s'han mogut.
L'única cosa irreversible seria copiar perfils **de llvm cap a railab** — no ho
facis fins que llvm estigui provada.

---

## Actualitzar llvm després d'un canvi `[railab]`

**Això no és un pas de la migració: és el que faràs cada vegada.** El
desenvolupament passa a railab, i llvm es queda enrere sense avisar.

```bash
rsync -av --delete \
  --exclude 'obsolet/' \
  --exclude 'node_modules/' \
  --exclude '__pycache__/' \
  --exclude '.env' \
  --exclude '_to_delete/' \
  --exclude '.flowed-active' \
  ~/projects/fluent_dev2/ llvm:/opt/fluent_dev2-0.4/
```

Els *excludes* no són decoratius:

| Exclòs | Per què |
|---|---|
| `.env` | és de la màquina: llvm té `backend docker` i port 12321 |
| `node_modules/` | el va fer `bun install` allà; copiar-lo des de railab és demanar problemes |
| `.flowed-active` | marcador de perfil actiu, propi de cada màquina |
| `__pycache__/` | es regenera; copiar-lo hi porta `.pyc` d'una altra versió de Python |
| `obsolet/` | 63 MB de runtime arxivat |

**`config/fluent.json` SÍ que viatja, i ja no porta res de la màquina** (des de
2026-09-26). La veu (piper) no hi té rutes: el servidor la troba a `_tts/` al
costat dels perfils (`~/.flowed/_tts/`). Un rsync ja no la desfà. Per comprovar-la:

```bash
# [llvm]
python3 scripts/flowed-check.py tts <perfil>
```

**Sempre, després de qualsevol rsync:**

```bash
# [llvm]
cd /opt/fluent && python3 -m unittest discover -s tests -q
```

Si el nombre de tests no ha pujat quan esperaves que pugés, el `rsync` no ha
arribat. És la comprovació més barata que hi ha.

### Quan sigui una versió i no un pedaç

```bash
# [llvm]
sudo cp -a /opt/fluent_dev2-0.4 /opt/fluent_dev2-0.5
# rsync cap a la 0.5, provar-la, i llavors:
sudo ln -sfn /opt/fluent_dev2-0.5 /opt/fluent
```

El canvi és instantani i tornar enrere és moure el symlink un altre cop.

## Pas a FlowEd 0.5.0 (`~/projects/flowed` → `/opt/flowed`) `[railab]` `[llvm]`

Canvis que afecten el desplegament: scripts `fluent-*` → `flowed-*`, variables
`FLUENT_*` → `FLOWED_*` (sense compatibilitat), marcador `.fluent-active` →
`.flowed-active`, perfils a `~/.flowed` (amb `~/.fluent` com a reserva mentre no
es mogui). Tot amb l'app aturada.

```bash
# [llvm] 1. aturar (amb l'script que hi hagi: flowed-stop.sh o fluent-stop.sh)
cd /opt/flowed && scripts/flowed-stop.sh
# 2. còpia per tornar enrere (serveix tant si /opt/flowed és carpeta com symlink)
#    (inclou l'.env vell: /opt/flowed-0.4/.env; una còpia DINS /opt/flowed
#    l'esborraria el rsync --delete)
sudo cp -a "$(readlink -f /opt/flowed)" /opt/flowed-0.4
```

```bash
# [railab] 3. codi
rsync -av --delete \
  --exclude 'obsolet/' --exclude 'node_modules/' --exclude '__pycache__/' \
  --exclude '.env' --exclude '_to_delete/' --exclude '.flowed-active' \
  ~/projects/flowed/ llvm:/opt/flowed/
```

```bash
# [llvm] 4. entorn i perfils
cd /opt/flowed
# .env de llvm = plantilla rapve (docker, --gpus all, una sola GPU, face off)
# + els perfils reals, recuperats de l'.env vell (no viatja amb el rsync).
WEBS=$(grep -E '^(FLUENT|FLOWED)_WEBS=' /opt/flowed-0.4/.env | cut -d= -f2-)
cp .env.rapve .env
[ -n "$WEBS" ] && sed -i "s|^FLOWED_WEBS=.*|FLOWED_WEBS=$WEBS|" .env
grep -E '^FLOWED_(WEBS|DEEP_PORT|DEEP_BACKEND)=' .env
[ -e ~/.flowed ] || mv ~/.fluent ~/.flowed
python3 hooks/main_paths.py home            # ha de dir /home/<usuari>/.flowed
# 5. res de fora del repo amb noms vells (scripts reanomenats!)
crontab -l 2>/dev/null | grep -i fluent; grep -rln 'fluent' ~/.config/systemd/user 2>/dev/null
# 6. proves i engegar
(cd server && bun install)
python3 -m unittest discover -s tests -q 2>&1 | tail -1
scripts/flowed-start.sh --dry-run --yes    # revisar abans d'engegar
scripts/flowed-start.sh
```

Després: comprovar la veu (`python3 scripts/flowed-check.py tts <perfil>`; si
`_tts/` ja hi era, no cal fer res) i obrir la web: la capçalera ha de dir `v0.5.0`.

**Si falta `.env`,** `flowed-start.sh` i `flowed-stop.sh` s'aturen amb un error
(abans agafaven en silenci els valors de `config/fluent.json`, que són els de
railab). **Si l'`.env` encara té noms `FLUENT_*`,** es llegeixen igual, amb un
avís que diu com convertir-los.

**Tornar enrere:** aturar, `sudo rsync -a --delete /opt/flowed-0.4/ /opt/flowed/`,
(l'.env vell ja hi torna amb el rsync), `mv ~/.flowed ~/.fluent` (la 0.4 només coneix
`~/.fluent`), engegar amb l'script vell.

## Després de la 0.5.0: canvis del 2026-09-26/27 `[railab]` `[llvm]`

Tot va dins del mateix rsync (secció «Pas a FlowEd 0.5.0», pas 3). Res a fer a
mà a llvm llevat del que diu aquí:

- **`.env`:** obligatori; si encara té `FLUENT_*`, funciona amb avís
  (ARQUITECTURA G.15).
- **Veu:** es troba sola a `~/.flowed/_tts/`; `scripts/flowed-tts.sh status` per
  comprovar-ho. No cal `install`.
- **Models amb plantilla estricta** (27B a TabbyAPI): sense configuració
  (G.16).
- **Competència extra** (G.17): al perfil que la vulgui, després del rsync:

```bash
# [llvm]
cd /opt/flowed
python3 scripts/flowed-extra.py add <perfil> curriculum/extras/x.good_luck_babe
python3 scripts/flowed-extra.py list <perfil>
```

Després, `scripts/flowed-stop.sh && scripts/flowed-start.sh`.

---

## Incidències

| # | Pas | Què ha passat | Notes |
|---|-----|---------------|-------|
|   |     |               |       |

## Pendent

- [ ] Mesura de VRAM real a 36864/f16 (pas 5) — l'única dada nova.
- [ ] Decidir quan es mouen `alex-en` i `sam-en`.
- [ ] Si llvm passa a ser la bona: on queda railab (desenvolupament?).

---

## Addendum WP5.2 (2026-10-07) — què t'ha de set extra on el que corré is the unified core

The procedure above still holds (rsync the dir → `bun install` → swap `.env` →
rsync the profiles → the pas checks). Three things the core adds that this
document predates:

1. **`FLOWED_HOME` on llvm.** `.env.rapve` does not set it, so the core would
   default to `~/.flowed`. Set it explicitly in the machine's `.env` — e.g.
   `FLOWED_HOME=/home/albert/.flowmath` (or a production home). The lib-paths
   fix (WP5.1) means a `FLOWED_HOME` in `.env` is now honored at source time;
   without it, `new-user.sh` provisions into the wrong home (the very bug the
   fix names).
2. **`FLOWED_WEBS` for the core's profiles.** `.env.rapve` lists the language
   product's webs (`alex-en:4100 sam-en:4101 demo-en:4102`). The core serves
   whatever profiles exist on the machine — math at 4200+ and the language
   learners you move over; list them with their ports.
3. **The manifest travels for free.** `config/domain.json` is in the repo, so
   the rsync carries it; each learner's domain is its level scale (A1..C2 →
   language, m1..m7 → math) — no per-learner config, nothing else to set.

Moving a real language learner from `flowed-language` to the core: the 6 DBs +
`.records` + `sessions/sessions.db` are the same format, so copying the profile
dir under the core's `FLOWED_HOME` is the whole migration. Before doing it with
real learners, land the polish list in `docs/RUNNING.md` §7 (declare `Bank:`
competences in `en-*.md` so Go/Review are model-free like math's; e2e-prove the
button labels; exercise TTS).
