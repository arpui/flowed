# Qwen3-14B-Q4_K_M com a deep — notes de model (2026-09-07)

Candidat a substituir el Q6_K (o a servir targes 16 GB). Resultats mesurats,
no opinions. Baseline: Qwen3-14B-Q6_K, mateix ctx 32768, mateixa bateria.

## VRAM (mesurada amb nvidia-smi)

| Model | Pesos (fitxer) | KV @32768 | Total mesurat |
|---|---|---|---|
| Q6_K | 12.1 GB | ~5.2 GB | **19.4 GB** (@49152) / **16.7–16.8 GB** (@32768) |
| Q4_K_M | 9.0 GB | ~5.2 GB (mateixa arquitectura) | **14.06 GB** (@32768, 4090) / **13.9 GB** (@3090) |

Regla: cada 16k de ctx ≈ 2.6 GB de KV. El Q4@32k (**~14 GB**) cap a 24 GB amb
marge i a **16 GB** (4060 Ti) just però viable. Llançador:
`scripts/models/llama-deep-14b-q4.sh` (mirall de `llama-deep.sh`: `--reasoning off`,
`--parallel 1`; PORT default 12325).

## Pujar el context sense passar de 15 GB (2026-09-13)

Mesura de partida a railab: **13.938 MiB** de 24.576. El sostre el marca l'altra
màquina, la 4060 Ti de 16 GB: **no passar de 15 GB**, o sigui ~1.400 MiB de
marge.

Pressupost, amb la regla mesurada (2,6 GB per 16k ≈ **166 MiB per cada 1k de ctx**):

| ctx | KV | Total previst | 4060 Ti 16 GB |
|---|---|---|---|
| 32768 (avui) | 5.324 MiB | 13.938 MiB | just |
| 36864 | 5.989 MiB | 14.603 MiB | ✅ ~1,7 GB lliures |
| 40960 | 6.655 MiB | 15.269 MiB | ⚠ al límit |
| 49152 | 7.986 MiB | 16.600 MiB | ❌ no hi cap |

O sigui: **sense tocar res més, +4k de context i prou**. És poc.

### El bon calaix: quantitzar la KV

`-ctk q8_0 -ctv q8_0` parteix la KV per la meitat. Requereix `-fa 1`, que ja hi
és. Amb això (**83 MiB per 1k**):

| ctx | KV (q8_0) | Total previst | Marge a la 4060 Ti |
|---|---|---|---|
| 32768 | 2.662 MiB | **11.276 MiB** | 5,1 GB |
| 49152 | 3.993 MiB | **12.607 MiB** | 3,8 GB |
| 65536 | 5.324 MiB | **13.938 MiB** | 2,4 GB — *la VRAM d'avui, amb el doble de context* |

> ### ⚠ Correcció (2026-09-13, vespre): el sostre és 40960, no 49152
>
> En producció: `exceeds the available context size (40960 tokens), n_ctx: 40960`.
> El 49152 **mai es va aplicar**. Qwen3-14B té `max_position_embeddings: 40960`,
> i llama.cpp reté el `-c` al màxim entrenat del model si no s'activa
> escalat de RoPE (YaRN). Les taules de sota calculen la VRAM correctament, però
> el 49152 i el 65536 no són assolibles sense YaRN — i YaRN degrada la qualitat
> a contextos curts, que és on viu aquesta app.
>
> **Valor real posat: `ctx: 40960` + `kv_type: "q8_0"`** → KV ≈ 3.328 MiB,
> total previst ≈ **11.900 MiB**. Segueix sent menys que els 13.938 de partida,
> i és el màxim que el model dona sense trucs.

### Posat (2026-09-14): `ctx: 36864` + `kv_type: "f16"`

~14.600 MiB previstos — ~1,7 GB de marge a la 4060 Ti, i un 12% més de context
sense introduir la variable de qualitat del q8_0. **Pendent de mesurar a rapve**
(`docs/MIGRACIO-LLVM.md`, pas 5): és l'únic número nou de la migració.

### Decisió prèvia (2026-09-13, nit): `ctx: 32768` + `kv_type: "f16"`

Terreny conegut. El raonament, en una línia: **el desbordament el resol la poda
de l'historial, no el context**, així que els tokens extra només serveixen per
retallar una mica més tard — i a canvi hi posaven una variable de qualitat (q8_0)
sense mesurar.

| | ctx | VRAM | Qualitat |
|---|---|---|---|
| **f16 @ 32768** ← posat | 32k | 13.938 MiB *(mesurat)* | la de sempre |
| f16 @ 36864 | 36k | ~14.600 MiB | la de sempre · ~1,7 GB de marge a la 4060 Ti |
| f16 @ 40960 | 41k *(sostre del model)* | ~16.000 MiB | ❌ no cap a la 4060 Ti |
| q8_0 @ 40960 | 41k | ~12.600 MiB | sense mesurar |

**Si algun dia cal més i no vols tocar la KV: `ctx: 36864`** — hi caben ~1,7 GB
de marge a la 4060 Ti i no canvia res més. És el següent pas natural.

Per sobre de 40960 no s'hi arriba de cap manera sense YaRN, i YaRN es descarta:
degrada els contextos curts, que és on viu aquesta app.

---

**Històric (aplicat i revertit el mateix dia): `ctx: 40960` + `kv_type: "q8_0"`.** Un 50% més de
context i **menys** VRAM que abans (12,6 GB previstos contra 13,9 mesurats).

**Per què 48k i no 64k**, ara que se sap que la 4060 Ti és una VM dedicada i no
mou cap escriptori — el motiu ja no és la VRAM:

- **Més context del que et cal no és gratis.** L'atenció recorre tota la KV, o
  sigui que el *prefill* de cada torn s'encareix amb el context ocupat, no amb
  el reservat; però reservar 64k convida l'historial a créixer fins a omplir-lo,
  i llavors sí que es paga.
- **Un 14B a 64k no raona igual que a 16k.** La degradació de qualitat en
  contextos llargs és real i no es veu a `nvidia-smi`: es veu en respostes
  pitjors, que és justament el que costa més de diagnosticar.
- **La causa real era una altra.** Els 51.605 tokens venien de sessions que no
  s'acabaven mai; això ja està arreglat. El context és marge, no cura. Una
  sessió sana no hauria de passar de ~15k.

Si algun dia 48k queda curt de debò, pujar a 64k és canviar un número i tornar a
mesurar — i llavors hi haurà un motiu mesurat per fer-ho.

**Això no està mesurat, és aritmètica** que encaixa amb les mesures anteriors.
Cal comprovar-ho:

```bash
python3 scripts/flowed-config.py --json | grep -i kv
scripts/models/llama-deep-14b-q4.sh --stop
scripts/models/llama-deep-14b-q4.sh
nvidia-smi --query-gpu=memory.used --format=csv
```

I sobretot: q8_0 a la KV **és una pèrdua de qualitat**, petita però real. Abans
de deixar-ho fix, passa-hi la bateria de sota i compara amb el f16. Si es nota,
torna a `f16` amb ctx 36864 i ja està.

### Com es configura

A `config/fluent.json`, dins `models.deep`:

```json
"ctx": 49152,
"kv_type": "q8_0"
```

`f16` és el valor per defecte del codi; el repositori ara porta `q8_0` escrit.

**Atenció al precedent:** `FLOWED_DEEP_CTX` estava fixat a `32768` als tres
fitxers `.env`, i l'`.env` **mana sobre el config**. Amb el valor allà, canviar
`config/fluent.json` no hauria servit de res. S'ha comentat als tres
(`.env`, `.env.railab`, `.env.rapve`) perquè les dues màquines faran servir el
mateix context; ja no és un valor per màquina. Comprova sempre què surt de debò:

```bash
python3 scripts/flowed-config.py --sh | grep -i "DEEP_CTX\|KV_TYPE"
``` Els dos llançadors (natiu i Docker) hi afegeixen
`-ctk/-ctv` només quan `kv_type` no és `f16`, i ho diuen a la línia d'arrencada.

## Temps (mateixos torns, perfil scratch)

| Torn | Q4@4090 | Q4@3090 | Q6@4090 | Q6@3090 (E2) |
|---|---|---|---|---|
| `fluent-progress` (~2.2k ch) | 10 s | 15 s | 13 s | 15 s |
| `fluent-vocab` 1r torn | 2 s | 3 s | 4–5 s | 9 s |
| `fluent-review` | — | — | 3 s | 5 s |

Caiguda 4090→3090 en torns curts: **~1.5×** (el 10× documentat és de prompts
llargs). Estimació 4060 Ti derivada: ample de banda 288 vs 936 GB/s (~3.2× en
decode) aplicat al Q4@3090 → vocab ~10 s, progress ~30–45 s.

## Qualitat: equivalents en torns amb dades

Mateixos continguts, mateixa disciplina d'eines (skill sola — l'estat ve
precarregat a la comanda, no cal `read-db.py` via eina), mateixos temps
d'ordre. **No hi ha degradació mesurable del Q4 en el camí normal.**

## Gap conegut: obediència en casos límit (Q4 < Q6)

Escenari: cua de repàs + mistakes + focus **buits** (perfil verge). Tots dos
models tendeixen al tancament degenerat (`Words Reviewed: 0`), però:

- **Q6**: emet el resum-0 però **remunta i perfora** (Word 1/10 net).
- **Q4**: emet el resum-0 i **pregunta què practicar en comptes de perforar**,
  tot i haver rebut la prohibició en 3 llocs del skill (verificat al
  `skill_content` servit — la va veure i la va desobeir).

Lliçó de prompting (verificada): al Q4 li funcionen les regles
**estructurals positives** ("el PRIMER missatge HA DE SER `## Word 1`"),
no les prohibicions ("mai facis X"). Amb la regla estructural el Q4 perfora
net al primer intent (`water`, català, sense resum, sense "Spanish").
Aplicat a `skills/fluent-vocab/SKILL.md` §3 + Critical Rules.

## Confusió català/castellà (prior del model, no del prompt)

- Cap prompt ni el perfil (`native_language: Catalan`) conté "Spanish".
- Origen: el 31/08 el tutor va escriure `"apple" → "manzana"` (prior
  català≈castellà, molt comú) i l'eco va quedar a l'historial de sessió.
- Fix: regla d'identitat estricta (nom del perfil VERBATIM; català ≠
  castellà; no copiar exemples ni historial) a `fluent-vocab` Critical Rules
  + `tutor-fast.md`, i exemples Dutch del skill neutralitzats a
  `{Native}`/`{Target}`. Amb sessió nova (↺) l'eco vell desapareix.
- Rotació de modes: "rotate" tou → alternança estricta
  recognition → production → cloze (el "sempre cap al català" era
  no-rotació + atzar, en tots dos models).

## Estat de producció (2026-09-07)

`12322` → Q4-14B @3090 (ctx 32768). Si cal tornar al Q6: stop 12322 +
`LLAMA_DEEP_GPU=1 scripts/models/llama-deep.sh` (2 comandes, les webs ni s'assabenten).

## Docker — RTX 4060 Ti 16GB (2026-09-08)

Llançador: `scripts/models/docker-llama.sh` (model-només; la web Fluent queda fora del
Docker de moment). Recepta: Q4 + ctx 32768 (~14 GB) al port host 12322.
Canvis respecte la versió original: ctx 16384→32768 (16k petaria per context
en torns reals de 12–25k), afegits `--reasoning off --parallel 1 -b 4096
-ub 1024 -fa 1 --jinja`, `--shm-size=8g`, mount `:ro`, health-check,
`--stop`, variables cablejades (`MODEL_DIR/MODEL_FILE/HOST_PORT/CTX`).
Validació pendent a la 4060: `/health` + 1 torn cronometrat (`fluent-progress`;
referència 3090: 15 s) per obtenir el factor real.

## Mesura real — Docker 4060 Ti @192.168.31.102:12321 (2026-09-08)

Contenidor amb el script ANTIC (`-c 16384`, sense `--reasoning/--parallel/-fa/--jinja`):

| Torn | 4060 Docker | Q4@3090 | Factor |
|---|---|---|---|
| `fluent-progress` (~2.4k ch) | **68 s** ✓ coherent | 15 s | ~4.5× |
| `fluent-vocab` (Word 1/10, català) | **55 s** ✓ drill net | 3 s | ~18× |

Lectura honesta: el factor supera l'estimació teòrica (~2-3×) — part pot ser la
manca de flags (`-fa 1` accelera el prefill; `--jinja` la plantilla). El ctx
16k va aguantar aquests dos torns, però continua sent arriscat per a torns
llargs (12–25k mesurats). **Recomanació:** reconstruir el contenidor amb
`scripts/models/docker-llama.sh` (ctx 32768 + flags) i repetir la mesura; s'espera
millora sobretot en prefill.

### Com provar un model remot (recepta 2026-09-08)

Des d'aquí (model a `IP:PORT`, p. ex. `192.168.31.102:12321`):

```bash
# 0. Sanity: ha de dir {"status":"ok"} i el model a /v1/models (mirar n_ctx!)
curl -sf http://IP:PORT/health
curl -sf http://IP:PORT/v1/models | head -c 400

# 1. Override via env (sense tocar config/: $FLOWED_MODELS_FILE mana sobre tot)
python3 - <<'EOF'
import json
json.dump({
  'deep': {'baseURL': 'http://IP:PORT/v1'},
  'face': {'provider': 'llama-face', 'model': 'face',
    'baseURL': 'http://IP:PORT/v1',
    'temperature': 0.7, 'max_tokens': 4096, 'timeout_ms': 120000},
}, open('/tmp/remote-models.json', 'w'), indent=2)
EOF

# 2. Perfil + web scratch (mai perfils reals)
rm -rf /tmp/remote-test /tmp/remote-xdg
cp -r ~/.fluent/test-en /tmp/remote-test
rm -f /tmp/remote-test/.opencode/opencode/opencode.db*
mkdir -p /tmp/remote-xdg
XDG_DATA_HOME=/tmp/remote-xdg FLOWED_DATA_DIR=/tmp/remote-test PORT=4192 \
  FLOWED_WEB_PASSWORD=remotetest FLOWED_MODELS_FILE=/tmp/remote-models.json \
  nohup bun server/src/index.ts > /tmp/remote-web.log 2>&1 &
 sleep 8

# 3. Torn cronometrat (referències Q4@3090: progress 15 s, vocab 3 s)
SID=$(curl -sf -u opencode:remotetest -X POST http://127.0.0.1:4192/api/session \
  -H 'content-type: application/json' -d '{"title":"remote"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
time curl -s -u opencode:remotetest -X POST http://127.0.0.1:4192/api/session/$SID/command \
  -H 'content-type: application/json' -d '{"agent":"learner","command":"fluent-progress"}' \
  -o /tmp/remote-out.json -w "HTTP=%{http_code}\n"

# 4. Neteja (la config de producció no s'ha tocat: l'override era només env)
ss -tlnp 2>/dev/null | grep ":4192" | grep -oP "pid=\K[0-9]+" | head -1 > /tmp/fluent-web-4192.pid
scripts/flowed-web.sh --stop --port 4192
rm -rf /tmp/remote-test /tmp/remote-xdg /tmp/remote-out.json /tmp/remote-models.json
```

Des de la mateixa màquina 4060 (sense el repo Fluent): prova ràpida directa
sense pila Fluent — fum + latència, sense tool-loop:

```bash
# mateixa màquina: localhost; des d'aquí: la IP
time curl -s http://127.0.0.1:12321/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"Qwen3-14B-Q4_K_M","messages":[
    {"role":"system","content":"You are a concise assistant."},
    {"role":"user","content":"Explain in one sentence what spaced repetition is."}],
    "max_tokens":200,"temperature":0.7}' \
  | head -c 500; echo
```

Per a un torn Fluent complet cal el repo (mateixa recepta d'abans amb
`127.0.0.1:PORT` com a URL remota).
