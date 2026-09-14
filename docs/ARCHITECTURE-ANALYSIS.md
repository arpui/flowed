# Anàlisi Arquitectònica: Fluent vs Open Course CLI

**Data:** 2026-09-03  
**Propòsit:** Avaluar millores estratègiques per a Fluent basant-nos en l'arquitectura d'Open Course CLI

---

## 1. Arquitectura Actual de Fluent

### Entry Point

`scripts/fluent-web.sh --app <profile-id>` → `server/src/index.ts` (servidor Bun/TypeScript standalone)

### Stack tecnològic

| Capa | Tecnologia | Fitxers |
|------|-----------|---------|
| **Servidor** | Bun/TypeScript | `server/src/index.ts`, `llm.ts`, `agent.ts`, `http.ts`, `db.ts`, `tools.ts`, `commands.ts` |
| **Web UI** | HTML/JS/CSS | `web/index.html`, `web/app.js`, `web/style.css` |
| **Backend de dades** | Python (stdlib) | `hooks/*.py` (read-db, update-db, accumulate, persist, validate, etc.) |
| **Habilitats** | Markdown | `skills/fluent-*/SKILL.md` (12 skills) |
| **Agents/Comandaments** | Markdown | `.opencode/agent/*.md`, `.opencode/commands/fluent-*.md` |
| **Models** | LLMs locals | deep (Qwen3.8-27B @ 12321) + face (OmniCoder-9B @ 12322) |

### Flux de dades

```
Usuari → Browser → server/src/index.ts → LLM local → Resposta
                                    ↓
                            Python hooks → 6 JSON a ~/.fluent/<id>/
```

### Emmagatzematge

- **6 fitxers JSON** per alumne a `~/.fluent/<id>/`
- **SQLite** per a sessions/missatges (opencode.db)
- **Fitxers markdown** de resultats a `~/.fluent/<id>/results/`
- **Backups** a `~/.fluent/<id>/.backups/`

### Flux de persistència (2 capes)

1. **Capa A (automàtica):** `session.idle` hook → `accumulate-session.py` → `update-db.py`
2. **Capa B (final):** Tutor crida `update-db.py` amb metadata final → `persist-session.py`

---

## 2. Arquitectura d'Open Course CLI

### Entry Point

`opencourse` (binari Rust) → `crates/cli/src/main.rs`

### Stack tecnològic

| Capa | Tecnologia | Crates |
|------|-----------|--------|
| **CLI/TUI** | Rust + ratatui | `crates/cli/` |
| **Domini** | Rust pur | `crates/core/` (tipus, scoring, orquestració) |
| **Lògica de negoci** | Rust | `crates/service/` (sessions, currículum) |
| **Emmagatzematge** | LanceDB (Arrow columnar) | `crates/db/` |
| **Client LLM** | rig-core | `crates/llm/` |
| **Configuració** | JSON + Rust | `crates/config/` |
| **Sync cloud** | Rust | `crates/sync/` (outbox pattern) |

### Flux de dades

```
Usuari → Terminal (ratatui) → service/ → llm/ → LLM cloud/local
                                    ↓
                              db/ → LanceDB per parella lingüística
```

### Emmagatzematge

- **LanceDB** per parella lingüística (`~/.open-course-cli/pairs/{native}-{target}/db/`)
- **config.json** amb proveïdors, perfils, preferències
- **Outbox** per sync cloud (mutacions ordenades monotònicament)

### Flux de persistència

- Tot passa per `Database` struct → LanceDB
- Migracions de schema versionades (v1→v5)
- Outbox per sync (cada mutació es registra)

---

## 3. Taula Comparativa Detallada

| Aspecte | **Fluent** | **Open Course** | **Impacte** |
|---------|-----------|-----------------|-------------|
| **Llenguatge** | TypeScript + Python | Rust | Python és més accessible per a contribuïdors |
| **Runtime** | Bun (JS) + Python | Binari Rust compilat | Rust és més ràpid, però més complex |
| **Servidor web** | Sí (propia HTTP) | No (TUI terminal) | Fluent és més accessible (browser) |
| **Emmagatzematge** | 6 JSON + SQLite | LanceDB (columnar) | JSON és més inspectable/editable manualment |
| **Migracions schema** | Cap (JSON flexible) | Versionades (v1→v5) | Open Course evita breaking changes |
| **Tests** | 1 fitxer Python, manual | CI complet (fmt+clippy+test) | Open Course té més confiança en canvis |
| **Error handling** | Exit codes + print | `AppError` enum tipat + retry | Open Course és més robust |
| **ID de sessió** | Timestamp (col·lisions possibles) | UUIDv7 (time-ordered, únics) | Open Course evita col·lisions |
| **Scoring** | SM-2 (spaced repetition) | EMA adaptativa + decay exponencial | Open Course té decay (~5%/dia) |
| **Vocabulari** | Camps lliures al JSON | Lema + formes + POS (UD) | Open Course és més estructurat |
| **Sync cloud** | No (backups locals) | Sí (outbox pattern, tombstones) | Open Course permet multi-device |
| **Múltiples usuaris** | Sí (~/.fluent/<id>/) | No (per parella lingüística) | Fluent és multi-user, Open Course no |
| **Dependències** | Bun + Python (stdlib) | Rust + molts crates | Fluent és més lleuger |
| **Documentació** | README + AGENTS.md | README + flow.md + docs/ | Similar |
| **CI/CD** | Cap | GitHub Actions (fmt+clippy+test+release) | Open Course té deploy automatitzat |
| **Configuració** | opencode.json + fluent-models.json | config.json unificat | Open Course és més net |

---

## 4. Millores Concretes (Prioritzades)

### Prioritat ALTA (Impacte alt, esforç baix-mitjà)

#### 4.1. Migracions de schema per als JSON

**Problema:** Actualment els 6 JSON no tenen versió de schema. Si canviem l'estructura, els perfils existents es trencen.

**Solució:**
```python
# Afegir a cada JSON:
{ "_schema_version": 2, ... }

# Script de migració:
scripts/migrate-db.py --from 1 --to 2
```

**Fitxers a crear:**
- `scripts/migrate-db.py` — migrador genèric
- `data-examples/migrations/` — scripts de migració per versió

---

#### 4.2. Tests automatitzats per als Python scripts

**Problema:** Només hi ha `tests/test_update-db.py`. No hi ha tests per a `read-db.py`, `accumulate-session.py`, `persist-session.py`, ni per la lògica de les skills.

**Solució:**
```
tests/
├── test_update_db.py          (ja existeix)
├── test_read_db.py            (nou)
├── test_accumulate_session.py (nou)
├── test_persist_session.py    (nou)
├── test_fluent_paths.py       (nou)
├── test_sm2.py                (nou)
└── test_migrate_db.py         (nou)
```

**Execució:** `python3 -m pytest tests/` o `python3 -m unittest discover tests/`

---

#### 4.3. Error handling robust

**Problema:** Els scripts fan `sys.exit(1)` o `print()` sense logging estructurat. Si falla un hook, l'usuari no entén què ha passat.

**Solució:**
```python
# Afegir logging consistent:
import logging
logger = logging.getLogger("fluent")

# Error handling amb context:
try:
    ...
except Exception as e:
    logger.error(f"Error updating DB: {e}", exc_info=True)
    sys.exit(1)
```

**Fitxers a modificar:**
- Tots els `hooks/*.py` — afegir logging + error messages clars

---

### Prioritat MITJANA (Impacte alt, esforç mitjà)

#### 4.4. ID de sessió millorat

**Problema:** Els timestamps com a ID poden tenir col·lisions si dues sessions es creen al mateix segon.

**Solució:**
```python
# Opció 1: UUID4 (simple)
import uuid
session_id = f"session-{uuid.uuid4().hex[:12]}"

# Opció 2: UUID7 (time-ordered, com Open Course)
# Requereix pip install uuid7 o implementació pròpia
```

**Fitxers a modificar:**
- `hooks/update-db.py` — generar ID únic
- `server/src/index.ts` — usar ID únic en lloc de timestamp

---

#### 4.5. Scoring amb decay exponencial

**Problema:** La mastery no decau amb el temps. Si un alumne no practica un patró durant setmanes, el sistema encara el considera "dominat".

**Solució (inspirada en Open Course):**
```python
# Decay exponencial:
# mastery_decay = 0.05 per dia (5% de pèrdua diària)
# Si last_practiced = fa 10 dies:
# mastery_decay = 0.05 * 10 = 0.5 (50% de reducció)

def apply_decay(mastery, last_practiced, days_elapsed):
    decay_rate = 0.05
    return mastery * max(0, 1 - (decay_rate * days_elapsed))
```

**Fitxers a modificar:**
- `hooks/update-db.py` — aplicar decay al calcular mastery
- `AGENTS.md` — documentar el decay

---

#### 4.6. Vocabulari estructurat

**Problema:** El vocabulari s'emmagatzema com a camps lliures al JSON. No hi ha separació clara entre lema, formes, POS, o nivell CEFR.

**Solució (inspirada en Open Course):**
```json
{
  "vocabulary": {
    "lemmas": [
      {
        "id": "lem-001",
        "lemma": "festiu",
        "pos": "ADJ",
        "translation": "holiday",
        "cefr_level": "A2",
        "mastery": 3,
        "practice_count": 5
      }
    ],
    "forms": [
      {
        "id": "form-001",
        "lemma_id": "lem-001",
        "form": "festius",
        "feats": "Gender=Masc|Number=Plur"
      }
    ]
  }
}
```

**Fitxers a modificar:**
- `data-examples/learner-profile.json` — afegir camp `vocabulary` estructurat
- `hooks/update-db.py` — processar vocabulari estructurat
- Skills de vocabulari — usar nova estructura

---

### Prioritat BAIXA (Impacte mitjà, esforç alt)

#### 4.7. CI/CD amb GitHub Actions

**Problema:** No hi ha CI automatitzat. Els tests s'executen manualment.

**Solució:**
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: python3 -m pytest tests/ -v
      - run: python3 tests/test_update_db.py
```

**Fitxers a crear:**
- `.github/workflows/ci.yml`

---

#### 4.8. Sync senzill (Git auto-commit)

**Problema:** Els backups són locals. Si es perd el disc, es perden les dades.

**Solució simple (no cal outbox complex com Open Course):**
```bash
# Cron job o hook que fa git auto-commit dels JSON:
cd ~/.fluent/<id>/
git add *.json
git commit -m "Auto-backup $(date +%Y-%m-%d)"
git push  # a un repo privat
```

**Fitxers a crear:**
- `scripts/auto-backup.sh`

---

## 5. Pla d'Implementació

### Fase 1: Fonaments (1-2 setmanes)

| Millores | Esforç | Fitxers |
|----------|--------|---------|
| 4.1 Migracions de schema | Baix | `scripts/migrate-db.py` |
| 4.2 Tests automatitzats | Mitjà | `tests/test_*.py` |
| 4.3 Error handling robust | Baix | Tots `hooks/*.py` |

### Fase 2: Millores de dades (1 setmana)

| Millores | Esforç | Fitxers |
|----------|--------|---------|
| 4.4 ID de sessió millorat | Baix | `update-db.py`, `server/src/index.ts` |
| 4.5 Scoring amb decay | Mitjà | `update-db.py`, `AGENTS.md` |
| 4.6 Vocabulari estructurat | Alt | JSON schemas, skills, hooks |

### Fase 3: Infraestructura (opcional)

| Millores | Esforç | Fitxers |
|----------|--------|---------|
| 4.7 CI/CD | Baix | `.github/workflows/ci.yml` |
| 4.8 Sync Git | Mitjà | `scripts/auto-backup.sh` |

---

## 6. Recomanació Estratègica

### Per què millorar Fluent, no Open Course?

| Factor | Millorar Fluent | Modificar Open Course |
|--------|-----------------|----------------------|
| **Filosofia** | Manté AI-agent-as-app (el valor diferencial) | Hauria de destruir l'arquitectura CLI/TUI |
| **Accessibilitat** | Web UI → accessible des de qualsevol dispositiu | TUI → només terminal |
| **Multi-user** | Sí (~/.fluent/<id>/) | No (per parella lingüística) |
| **Dependències** | Bun + Python (stdlib) → fàcil de desplegar | Rust + molts crates → compilació complexa |
| **Extensibilitat** | Skills en Markdown → fàcil d'afegir nous exercicis | Rust structs → requereix recompilació |
| **Risc** | Baix (canvis incrementals) | Alt (reescriure tot) |
| **Comunitat** | Python + TypeScript → més desenvolupadors | Rust → nínxol |

### La clau

La **filosofia de Fluent** és ser un plugin d'IA que funciona dins d'assistents (Claude Code, OpenCode) **i** com a servidor standalone. Open Course és un CLI autònom amb TUI — un paradigma diferent.

**Fluent ja té el millor dels dos mons:**
- Web UI (més accessible que TUI)
- Multi-user (Open Course no)
- Skills en Markdown (fàcil d'extendre)
- Backend Python (accessible)

**El que li falta (i que Open Course té):**
- Tests automatitzats
- Migracions de schema
- Error handling robust
- Scoring amb decay
- Vocabulari estructurat

### Conclusió

**Millorar Fluent amb les millors pràctiques d'Open Course** és l'estratègica correcta. No cal canviar de paradigma — cal afinar el que ja funciona.

---

## Referències

- **Fluent repo:** `/media/albert/railab2/projects/fluent_dev/`
- **Open Course repo:** `/home/albert/ext/open-course-cli/`
- **AGENTS.md:** Instruccions del tutor AI
- **LEARNING_SYSTEM.md:** Metodologia pedagògica
- **Open Course README:** `/home/albert/ext/open-course-cli/README.md`
