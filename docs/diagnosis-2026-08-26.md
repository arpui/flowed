# Diagnòstic del penjam de `/fluent-learn` — 2026-08-26

Anàlisi de les dues falles consecutives a la web (fluent-v2, app `alex-en`) i dels canvis aplicats.

---

## 1. Què ha passat

### Falla A — 20:25 (sessió `ses_fc0addc1bffeSWr6VJPM1pkCx2`, després esborrada pel reset)
- `/fluent-learn` → l'alumne tria **"6"** del menú d'opcions.
- El model confon la selecció de menú amb una resposta i crida `fluent_deep_evaluate` amb `answer="6"`.
- El guard A1 la rebutja (no és una resposta real); el model insisteix i repeteix → **43 crides** a la mateixa sessió (~18 s per inferència deep → minuts de penjam).
- **ESTAT: ARREGLAT** amb el guard A3 (desactivació per sessió a `plugins/fluent.js`). Verificat en viu a la Falla B.

### Falla B — 20:02–22:17 (sessió `ses_fc05543b8ffeCMwYpxl614q6Q2`)
- `/fluent-learn` → salutació OK (~38 s) → "6".
- L'eina es desactiva amb A3 (el guard funciona).
- El model es perd: cree que no té l'eina `skill` i comença a investigar la BD:
  - `python3 hooks/update-db.py --help 2>&1 || python3 hooks/update-db.py 2>&1 | head -40` → **DENY**
  - 3 intents de `write` → **DENY**
  - `python3 hooks/read-db.py --full` → OK
- Missatge final `msg_03fb0487a001B9Lpgaq5kt4cmn`: 5 passos buits (step-start + reasoning buit, ~1,5–2,5 min cadascun) → error **`Context size has been exceeded.`** a les 22:17:58.

---

## 2. Per què abans funcionava bé (línia de temps)

| Versió | Data | Què hi havia |
|---|---|---|
| 0.4.0 | 8/21 | Model únic 27B (`Q8_0`, `llama-local`). setup/e2e OK. |
| 0.5.0 | 8/22 | Dual-model: face `omnicoder-9b` (port 12322) per a vocab/review/progress/setup; 27B per a learn/writing/speaking/reading. Prompt compacte → **context 14–20k per torn, TTFT 9–15 s**. |
| 0.5.1 | 8/26 | Provider `fluent-deep` (port 12321, alias `deep`). |
| 0.5.2 | 8/26 | Eina `fluent_deep_evaluate` + guard A1; dedup SSE; sanejament d'entorn (devMode). |

La versió "bona" (0.5.0) funcionava perquè: **no existia l'eina d'avaluació** (cap superfície de crides de brossa), el context era petit i no hi havia denies al bucle.

Evidència de sessions (`~/.local/share/opencode/opencode.db`):
- 8/21: `Qwen3.8-27B-Q8_0.gguf` — setup/e2e (OK).
- 8/22: `Qwen3.8-27B-UD-Q4_K_XL` + `omnicoder-9b` — la sessió d'alumne "Alex A1 English vocabulary practice session" va córrer al **face 9B** (ràpid i simple).
- 8/26: `fluent-deep/deep` — les dues falles d'aquest document.

---

## 3. Causes arrel (amb evidència)

### 3.1 L'agent `learner` té un bloqueig de permisos amb paths de v1 obsolets ← origen real dels denies
La web usa `agent: "learner"` (`web/app.js:9`). El frontmatter de `fluent-v2/.opencode/agent/learner.md` conté:

```yaml
permission:
  bash:
    "*": deny
    "python3 hooks/read-db.py*": allow
    "python3 /media/albert/railab2/projects/fluent/hooks/read-db.py*": allow   # ← path de V1
    "python3 hooks/update-db.py*": allow
    "python3 /media/albert/railab2/projects/fluent/hooks/update-db.py*": allow # ← path de V1
    ... (tots els paths absoluts apunten a v1)
    "rm -f .fluent-active": allow
  edit:
    "*": deny
    "data/*.json": allow
    "/media/albert/railab2/projects/fluent/data/*.json": allow   # ← path de V1
    "results/*.md": allow
    ...
```

Conseqüències observades a la Falla B:
- La composada `... || ... | head -40` → **DENY**: el subcomanda `head -40` no està al whitelist.
- Cada deny retorna un error de ~4,3k caràcters amb la llista de 63 regles → **cada deny incrusta ~1,5–2k tokens** al context.
- Les 3 writes → DENY (`edit "*": deny`; només `data/`, `results/`, `.fluent-active` permés).
- El bloqueig és **per disseny** (web de finalista), però els paths absoluts són obsolets (apunten a v1) i el model ignora l'avís de la línia 52 ("compound bash commands ... are blocked").

### 3.2 Cap `limit` a `opencode.json` → límit de context de 32k per defecte
`fluent-v2/opencode.json` (i v1) no defineix `limit` al model deep → opencode aplica **32k per defecte**. Amb thinking + crides d'eina + denies, el context el supera → `Context size has been exceeded.`

### 3.3 `timeout: 60000` massa curt
A 25k+ de context, el TTFT del 27B supera els 60 s → cada pas es talla buit → opencode reintenta → accelera el desbordament.

### 3.4 L'eina `fluent_deep_evaluate` (nova a 0.5.2)
Superfície de crides de brossa (bucle de "6"/"n/a"/PLACEHOLDER). Arreglada amb A1+A3, però el model encara malgasta un pas cridant-la amb brossa.

### 3.5 Secundari: el model deep ha canviat
- 8/21 (el 27B "bo"): `Qwen3.8-27B-Q8_0.gguf`
- ara (12321): `Qwen3.8-27B-UD-Q6_K_XL.gguf` (unsloth hub, quantització inferior)
→ seguiment d'instruccions més feble (el model va ignorar l'avís explícit). És el model de l'usuari; decisió secundària.

### 3.6 Detal·l (no és causa)
Les sessions de la web pertanyen al projecte `global` (worktree `/`), perquè `fluent-v2` no és un repos git. La config (projecte + global + agent) s'aplica correcte igual (verificat a la llista de 63 regles del deny), per tant no canvia el comportament.

---

## 4. Canvis aplicats

### 4.1 `opencode.json` (v1 + v2)
Model **deep**:
```diff
      "models": {
        "deep": {
          "name": "Deep model (actiu al 12321)",
          "tool_parsing": { ... },
+         "limit": { "context": 131072, "output": 8192 },
          "parameters": {
            "temperature": 0.7,
-           "max_tokens": 4096,
+           "max_tokens": 8192,
            "top_p": 0.95,
-           "timeout": 60000
+           "timeout": 300000
          }
        }
```
Model **face**:
```diff
+       "limit": { "context": 32768, "output": 4096 },
        "parameters": { ... "timeout": 120000 }   // era 60000
```
(Esquema opencode: `limit` requereix `context` i `output`; viu a nivell de model.)

### 4.2 `.opencode/agent/learner.md`
- **v2**: substituir els paths absoluts de v1 (`/media/albert/railab2/projects/fluent/...`) pels de v2 (`/media/albert/railab2/projects/fluent-v2/...`). El bloqueig es manté (per disseny).
- **v1**: els paths absoluts ja són correctes (v1); només s'hi aplica el que faci sentit.

### 4.3 `web/app.js` (v1 + v2)
- En obrir, si la sessió **no té cap missatge** (nova), l'app envia automàticament **`/fluent-learn`** com a primer comandament → salutació + flux immediat.
- Si la sessió ja té història (recàrrega a mitja sessió), **no** resenvia.

### 4.4 `.opencode/commands/fluent-learn.md` (v1 + v2)
Nova regla:
- Mai investigar els scripts de BD (`read-db.py`, `update-db.py`), el seu esquema, ni els hooks.
- No usar comandes composades (`||`, `|`, `;`, `--help`): el bloqueig de permisos les rebutja i cada deny infla el context.
- Persistir l'estat **només** amb la skill `fluent-db-updater` al final de la sessió.
- (Ja hi ha la regla de seleccions de menú de l'A3: "6"/"ok"/"next" no són respostes.)

### 4.5 Reinici + reset
- `scripts/flowed-web.sh --stop --port 4100`
- `FLUENT_WEB_PASSWORD=8cYfFtlZhAu8NwTg nohup scripts/flowed-web.sh --app alex-en > /tmp/fluent-web-restart.log 2>&1 &`
- `python3 scripts/reset-session.py`
- Verificar: `devMode=false` al log, deep (12321) i face (12322) UP, web UP.

### 4.6 Sync v1 ↔ v2
- `opencode.json`, `web/app.js`, `fluent-learn.md` → sincronitzats a v1.
- `learner.md` → **no** sync ceguerament (els paths absoluts són per-repo; veure 4.2).

---

## 5. Validació

- `jq . opencode.json` (v1 + v2) — JSON vàlid.
- `node --check web/app.js` — sintaxi OK.
- Després del reinici: `opencode.log` (`fluent-hooks initialized (devMode=false)`), `ss -tlnp` (4100/4199), deep 12321 i face 12322 UP.
- Re-prova de l'usuari: obrir la web → auto `/fluent-learn` → saludar-se i respondre unes quantes preguntes → sense penjam ni denies.

## 6. Estat (completat 2026-08-26 ~22:25)

- [x] Guard A3 trans-turn (Falla A) — implementat i verificat en viu.
- [x] 4.1 `opencode.json` (v1+v2) — verificat al serve actiu: deep `limit {131072, 8192}`, face `limit {32768, 4096}`.
- [x] 4.2 `learner.md` (v2) — paths absoluts ara apunten a `fluent-v2`.
- [x] 4.3 `app.js` (v1+v2) — salutació automàtica `/fluent-learn` en sessió nova buida (`init()` i `newSession()`); `node --check` OK.
- [x] 4.4 Regla anti-investigació a `fluent-learn.md`, `fluent-speaking.md`, `fluent-writing.md` (v1+v2).
- [x] 4.5 Reinici + reset — web UP (alex-en, devMode=false, deep 12321 i face 12322 OK); sessió neta: `ses_fbfd3c082ffeYE6MXRSpbr0nGW`.
- [x] 4.6 Sync v1 — `opencode.json`, `app.js`, les 3 comandes i aquest document. (`learner.md` no sincronitzat a propòsit: els paths són per-repo.)
