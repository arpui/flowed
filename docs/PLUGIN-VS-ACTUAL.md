# El plugin original i el que tenim ara: qui decidia què

Data: 2026-09-21. Només lectura; no s'ha modificat cap fitxer del plugin ni de l'app (només aquest document).

## Abast i verificació

- **Plugin revisat:** `/media/albert/railab2/ext/fluent` (m98/fluent v0.3.0, últim commit `86fb80f`, 2026-06-15). Tot el que diu aquest document sobre el plugin s'ha comprovat llegint aquests fitxers: `.claude/hooks/*`, `.claude/skills/*`, `CLAUDE.md`, `AGENTS.md`, `LEARNING_SYSTEM.md`, `PRACTICE.md`, `docs/DB_SCRIPTS.md`.
- **Què no he fet:** executar el plugin dins Claude Code. «L'agent decideix X» vol dir que les instruccions li ho manen; no he vist què va fer realment el model.
- **Correccions respecte de la primera versió d'aquest document** (escrita amb només una còpia parcial): (1) el decaïment del mestratge per habilitat **no és del plugin, és nostre**; (2) el rànquing de patrons i el «boost» per ítem vençut a `read-db.py` són **nostres**; (3) l'SM-2 del plugin arrodoneix amb `ceil`, el nostre amb `round`; (4) el plugin té un skill que nosaltres hem tret (`fluent-session-analyzer`).

## 1. Arquitectura del plugin (verificada)

```
Claude Code = el tutor
  ├─ CLAUDE.md / AGENTS.md / LEARNING_SYSTEM.md: instruccions llegides al començar
  ├─ /fluent-* (skills): què fa l'agent a cada pràctica
  ├─ hooks (hooks.json): SessionStart, SessionEnd, PostToolUse (Write|Edit), PreCompact
  │     només mostren estadístiques, validen JSON i fan còpies; cap decisió pedagògica
  ├─ read-db.py: carrega les 6 BD + camps calculats (due_reviews_count, next_session_id, streak)
  └─ update-db.py: l'agent hi envia UN informe JSON al final de la sessió (skill fluent-db-updater)
        aplica SM-2, precisió, mestratge per habilitat, ratxa. Atòmic, amb còpia.
/data: 6 JSON: learner-profile · progress-db · mistakes-db · mastery-db · spaced-repetition · session-log
/results: un .md per sessió (feedback complet)
```

`fluent-session-analyzer` (plugin): l'agent llegeix els `.md` de `/results` per planificar la sessió següent (top 3 debilitats = 50 % del temps, etc.).

## 2. Qui decidia cada cosa al plugin

| Decisió | Qui | Com (comprovat) |
|---|---|---|
| Nivell CEFR d'entrada | L'alumne o el tutor | `/fluent-setup`; si diu «not sure», 5 preguntes i el tutor tria |
| Nivell objectiu | L'alumne | `/fluent-setup` |
| **Passar d'A1 a A2** | **Ningú** | `grep` de tot el plugin: `learner.current_level` (CEFR) només s'escriu al setup. Cap regla, cap hook, cap skill de promoció |
| «A2 → A2+ (65% to B1)» | L'agent, copiat | És un exemple de `LEARNING_SYSTEM.md` línia 443. `fluent-progress` usa `{percentage}` sense fórmula |
| Què practicar avui | L'agent | Pla de sessió: cua de repàs + `focus_areas` + equilibri d'habilitats + minuts (`LEARNING_SYSTEM.md`) |
| Dificultat | L'agent | Regla escrita a `LEARNING_SYSTEM.md` (`select_difficulty`) i a `fluent-learn` §6 (cada 3-4 exercicis, zona 60-70 %) |
| Nota d'una resposta | L'agent | `fluent-feedback-formatter` |
| Patrons d'error | L'agent els nomena | Van al payload; `update-db.py` els guarda i els fusiona |
| Quan torna un ítem | **Codi** | `calculate_sm2` a `update-db.py` (interval 1/6/EF, `ceil`) |
| Mestratge per **habilitat** (0-5) | **Codi** | `update_mastery_db`: segons sessions i precisió (≥20 sessions i ≥90 % → 5). **Sense decaïment** |
| Mestratge d'un **ítem** | **Codi** | SM-2: `repetitions ≥ 5` i `consecutive_correct ≥ 3` → ≥ 3 |
| Ratxa | **Codi** | `update-db.py` |
| Quan s'escriuen les BD | L'agent | Al final de la sessió (skill) i, segons `CLAUDE.md`, «després de cada resposta» (instrucció a l'agent) |

## 3. Flux de coneixement i cicle de vida al plugin

1. **Entra:** el tutor inventa cada exercici amb el seu coneixement. No hi ha currículum ni banc d'exercicis.
2. **S'acumula:** per ítem, en 3 llocs: `spaced-repetition.json` (paraules i regles amb SM-2), `mistakes-db.json` (patrons d'error) i `mastery-db.json` (5 habilitats: writing, speaking, vocabulary, reading, listening).
3. **Torna:** la cua de repàs SM-2 i els patrons d'error.
4. **Cicle de vida d'un ítem:** apareix en fallar → SM-2 → puja de mestratge si l'encerta amb repeticions → queda amb prioritat baixa. **Un tema o una competència no tenen cicle de vida.**
5. **Qui declara «has assolit A2»:** ningú. El nivell del perfil és una etiqueta d'entrada.

## 4. Què tenim ara

Diferències mesurades amb `diff` (línies que canvien): `update-db.py` 379, `read-db.py` 267, `fluent_paths.py` 43; els skills 10-182 cadascun; `AGENTS.md` 526; `LEARNING_SYSTEM.md` i `PRACTICE.md` 2. Els fitxers de dades són els mateixos 6 JSON.

**Del plugin, sense canvis:** `session-start.py`, `session-end.py`, `validate-data.py`, `precompact-backup.sh`, i la doctrina de `LEARNING_SYSTEM.md`.

**Afegit a la capa de dades i hooks (nostre):**
- `db_lock.py`, `db_schema.py` (versions de BD i categories d'error úniques), `accumulate-session.py` i `persist-session.py` (registre incremental per resposta, idempotent per `session_id`).
- `update-db.py`: decaïment del mestratge per habilitat quan no es practica, ajust del mestratge per ítem (`consecutive_correct ≥ 5`), `round` en lloc de `ceil`, fusió de patrons d'error bessons, còpies T0 per sessió.
- `read-db.py`: rànquing dels ítems vençuts amb pes per endarreriment, exclusió dels patrons ja corregits.

**Afegit com a capa de servidor (`server/src/`, Bun) davant d'un LLM local:** el que abans decidia l'agent, ara ho decideix el servidor:

| Decisió | Plugin | Ara |
|---|---|---|
| Què surt a la Lliçó i en quin ordre | L'agent | El servidor: pla amb mida = pendent, un ítem assignat per torn |
| Que una resposta compti | L'agent | El servidor acredita una vegada per exercici |
| Que la lliçó s'acabi | L'agent | El servidor (`lessonNote`) |
| Repeticions i «ja contestat» | L'agent | El servidor (guards, empremtes) |
| Que el feedback sigui de l'ítem contestat | L'agent | El servidor comprova (nou, 2026-09-21) |
| Registre de cada resposta amb `item_id` | Al final, l'agent | Eina `fluent_record_answer` amb l'`item_id` que assigna el servidor |
| Comptador «Review N/M» | L'agent | El servidor el força |
| Temes del docent | No existeix | `topics.txt`, sense estat |
| Nivell CEFR, objectiu, progrés | **Ningú** | **Ningú** |
| Contingut, dificultat, nota | L'agent | L'agent |

**Tret respecte del plugin:** `fluent-session-analyzer` (no hi ha un pas que llegeixi els `.md` d'anàlisi). Rànquing de debilitats ara es fa a `read-db.py`.

## 5. Conclusions per a l'app

1. **El nivell CEFR no ha tingut mai mecanisme**, ni al plugin ni ara. El «65 % to B1» és un exemple de la documentació que el tutor copia.
2. **L'únic senyal d'aprenentatge que el codi mesura és l'SM-2 per ítem** i els patrons d'error. Les estrelles per habilitat mesuren volum i precisió, no què s'ha après.
3. **El currículum (què és un A2, en quin ordre) només viu al model.** No hi ha cap llista al plugin ni a l'app.
4. Per poder dir «has arribat a A2» cal un llistat de competències i regles de promoció que compti el servidor: `docs/ESQUEMA-APRENENTATGE.md` (proposta, sense implementar).
5. Mentrestant, l'app no hauria de mostrar «% cap al següent nivell»: no té base. Es pot substituir per magnituds mesurades (ítems dominats, ratxa, cua).

## 6. On mirar (plugin)

- Instruccions al tutor: `CLAUDE.md`, `AGENTS.md`, `LEARNING_SYSTEM.md`.
- Regles de mestratge i SM-2: `.claude/hooks/update-db.py` (`calculate_sm2`, `update_mastery_db`, `update_spaced_repetition`).
- Progrés: `.claude/skills/fluent-progress/SKILL.md`.
- Setup i nivell: `.claude/skills/fluent-setup/SKILL.md`.
- Anàlisi de sessions: `.claude/skills/fluent-session-analyzer/SKILL.md`.
