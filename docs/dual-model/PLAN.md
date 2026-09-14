# Fluent v2 — Arquitectura de doble model i mode dev

**Obert:** 2026-08-21
**Estat:** ✅ Implementat i verificat (2026-08-22) — mode actual: **face (omnicoder-9b) + deep (27B)**

> Espai de seguiment de la versió v2 (`fluent-v2`): arquitectura de doble
> model (fast/deep), eina `fluent_deep_evaluate`, mode dev a desktop i web
> amb render en viu.
>
> **Documents:**
> - `PLAN.md` (aquest) — per què, com funciona, decisions, criteris de verificació.
> - [`CHANGES.md`](CHANGES.md) — registre de canvis fitxer a fitxer i verificacions.
> - Docs de la migració base: [`../opencode-migration/`](../opencode-migration/).

---

## 1. Objectiu

Separar la **conversació** (model ràpid, context complet de la sessió) de
l'**avaluació** de respostes obertes (model "profund", context net i rubric
fix). Això permet:

- Avalorar amb un model fort sense inflar el context del tutor.
- Canviar de model d'avaluació més endavant tocant **una sola configuració**
  (`.opencode/fluent-models.json`), sense tocar agents, comandes ni skills.

## 2. Rols de model

| Rol | Què fa | On es configura |
|---|---|---|
| **fast** | Conversa, protocol de tutor, exercicis ràpids | `model:` a `.opencode/agent/tutor.md` / `learner.md` |
| **deep** | Avaluació de respostes obertes (rubric fix) | `.opencode/fluent-models.json` → `deep` |

**Avui (un sol model):** els dos rols apunten al mateix model
(`Qwen3.8-27B-UD-Q4_K_XL.gguf` a `http://127.0.0.1:12321/v1`). La separació
ja existeix per arquitectura: canviar `deep.baseURL`/`deep.model` activa el
doble model de veritat sense cap més canvi.

**Model "face" (ACTIU des del 2026-08-22):** `omnicoder-9b-q4_k_m.gguf` a port
`12322` (RTX 3090), llançador a `scripts/llama-face.sh` (default GPU 1 —
l'índex de CUDA no coincideix amb el de `nvidia-smi` en aquesta màquina).
El provider `llama-face` està declarat a `opencode.json` i l'agent
`tutor-fast.md` l'usa per a `/fluent-vocab`, `/fluent-review`,
`/fluent-progress` i `/fluent-setup` (rutejat pel `agent:` del frontmatter de
les comandes; el paràmetre `agent` de la petició web no el sobreescriu —
verificat). Resultats E2E: primer contingut en ~3 s (vocab, face) vs. ~9-15 s
(xat, 27B amb context reduït); abans de l'optimització: 20-40 s.

## 3. Eina `fluent_deep_evaluate`

Registra el plugin `.opencode/plugins/fluent.js` una eina custom:

```
fluent_deep_evaluate(task, answer, context)
```

- Fa un `POST` directe al chat/completions del model deep (sense passar pel
  loop de l'agent): rubric fix `DEEP_RUBRIC` + prompt amb task/context/answer.
- Rubric de sortida (seccions fixes):
  `## CORRECTIONS` / `## CORRECT VERSION` / `## SCORE` (0-10) / `## FEEDBACK`.
- Temps límit configurable (`deep.timeout_ms`, 120 s per defecte) amb
  `AbortController`; en fallar retorna
  `DEEP UNAVAILABLE: <detall>` + instrucció de fallback → el tutor avaluació
  ell mateix en el mateix format. La sessió mai no es trenca per un model caigut.

### Routing determinista (on s'usa l'eina)

| Tipus de resposta | Qui avalua |
|---|---|
| Escritura (texts, correus, cartes) | `fluent_deep_evaluate` |
| Conversa (respostes lliures de speaking) | `fluent_deep_evaluate` |
| Lectura (respostes obertes a un text) | `fluent_deep_evaluate` |
| Puntuació final / resum de sessió | `fluent_deep_evaluate` |
| Vocabulari, review SM-2, true/false, complecions | Model fast (el tutor), feedback directe |

Les comandes `fluent-writing`, `fluent-speaking` i `fluent-learn` ho indiquen
a la seva descripció; `learner.md` té el permís `fluent_deep_evaluate: allow`.

## 4. Mode dev a desktop

El plugin detecta el client desktop (`OPENCODE_CLIENT=desktop`, fallback
`XDG_STATE_HOME` que acabi en `ai.opencode.desktop`, override `FLUENT_DEV=1/0`)
i, només en aquest cas:

- Elimina dels system prompts els blocs `Instructions from:` d'`AGENTS.md` i
  `LEARNING_SYSTEM.md` (paper de tutor) i hi afegeix un preàmbul curt de
  desenvolupament (`DEV_PREAMBLE`).
- Salta el benvinguda de tutor a `session.created`.
- A `experimental.session.compacting` injecta el context de dev (no el de tutor).

TUI / web / app d'aprenent **no es toquen**: el tutor segueix sent el paper
per defecte. Nota: el plugin es carrega en arrencar el server d'opencode →
cal reiniciar la instància perquè els canvis del plugin surtin.

## 5. Web: render incremental + SSE en viu

`web/app.js` (mode `--app`) deixa de redibuixar tot l'historial després de
cada torn:

- `POST /session/:id/message` i `/command` bloquegen i tornen
  `{ info: AssistantMessage, parts: Part[] }` → s'afegeixen al DOM amb
  deduplicació per `info.id` (fallback a `refresh()` si la forma canvia).
- `EventSource /api/event` renderitza en viu: `message.updated` (crea el
  missatge), `message.part.updated` (actualitza parts; les que arriben abans
  del seu missatge es matriulen a `pendingParts`), `message.part.delta`
  (streaming de tokens al text), `message.removed`, `session.idle`,
  `session.error`.
- Missatge d'usuari optimista: es pinta a l'instant i es confirma amb el
  `message.updated` de rol user (o es descarta si el POST falla).
- Xarxa de seguretat: polling de l'historial cada 5 s només mentre hi ha un
  torn actiu (+15 s de drenatge), per si el SSE es cau.
- Parts no visibles (`reasoning`, `step-start/finish`) no es pinten.

## 6. Criteris de verificació

1. `python3 tests/test_update_db.py` → 12/12 OK.
2. Headless (`opencode run`, sense env del desktop): llista d'eines inclou
   `fluent_deep_evaluate`; cridar l'eina fa un `POST` real al 12321 i torna
   el format CORRECTIONS/CORRECT VERSION/SCORE/FEEDBACK.
3. Web (`scripts/fluent-web.sh --app`): pàgina estàtica + `/api/global/health`
   + `/api/event` en viu a través del proxy; un POST de missatge genera
   `message.updated`/`message.part.updated`/`message.part.delta` i la resposta
   té la forma `{info, parts}`.
4. En fallar el model deep, l'eina retorna `DEEP UNAVAILABLE: …` (mai error).

## 7. Riscos / notes

- El loader de plugins d'opencode 1.18.21 **invoca cada export function del
  mòdul com a plugin**: els helpers han de quedar privats i el factory de
  hooks ha de ser `export default` (un export només, sense més exports de
  funcions). Un error de sintaxi en el plugin fa que el mòdul falli en
  importar-se **silencióionaent** (cap eina ni hook, sense error a la UI).
- El desktop carrega el plugin en arrencar: després de canviar-lo, reiniciar
  l'app per veure-ho.
- No fer servir `node:child_process` dins del plugin (deadlock en carregar);
  el shell Bun (`$`) no existeix al runtime Node del desktop → tot ús de
  `runPython` va amb guardà `shell` (avís al log).
