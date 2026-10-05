#!/usr/bin/env python3
"""Read-only checks on a learner profile — one short command per question.

The test plan used to paste multi-line `python3 -c "..."` snippets, which break
the moment they are copied with the surrounding indentation. This script exists
so a check is always one line:

    python3 scripts/flowed-check.py all demo-en
    python3 scripts/flowed-check.py sm2 test-en
    python3 scripts/flowed-check.py records test-en --dir /some/other/profile

Checks: profile · sm2 · patterns · mastery · records · metrics · sessions.
It never writes anything.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sqlite3
import statistics
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from main_paths import profiles_root  # noqa: E402  (where the profiles live)

CHECKS = ("profile", "sm2", "patterns", "mastery", "records", "metrics", "sessions", "tts", "sortida", "historial", "lliço", "obertes")


def load(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        print(f"  ⚠ {path.name}: {exc}")
        return None


def days_since(value) -> int | None:
    if not value:
        return None
    try:
        then = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (date.today() - then).days


def head(title: str):
    print(f"\n=== {title} ===")


def check_profile(d: Path):
    head("perfil")
    profile = load(d / "learner-profile.json")
    if not profile:
        print("  ❌ no hi ha learner-profile.json")
        return
    learner = profile.get("learner", {})
    print(f"  nom            : {learner.get('name')}")
    print(f"  llengües       : {learner.get('native_language')} → {learner.get('target_language')}")
    print(f"  nivell         : {learner.get('current_level')} → {learner.get('target_level')}")
    print(f"  minuts/dia     : {learner.get('daily_goal_minutes')}")
    print(f"  setup_complete : {profile.get('preferences', {}).get('setup_complete')}")
    print(f"  ratxa          : {profile.get('current_streak_days')} dies")
    prefs = profile.get("preferences", {})
    print(f"  objectiu diari : {prefs.get('daily_goal', prefs.get('session_length', '(per defecte 15)'))}"
          f"   · en arribar-hi: {prefs.get('session_stop', '(per defecte soft)')}"
          f"   · decaïment: {prefs.get('mastery_decay', '(per defecte)')}")
    gate = prefs.get("review_gate", "(per defecte on)")
    print(f"  repàs abans de nou: {gate}")
    leftovers = [f"{k}={v}" for k, v in learner.items()
                 if isinstance(v, str) and v.startswith("{") and v.endswith("}")]
    print(f"  plantilla sense omplir: {leftovers or 'cap ✅'}")


def check_sm2(d: Path):
    head("repetició espaiada (SM-2)")
    sr = load(d / "spaced-repetition.json")
    if not sr:
        print("  ❌ no hi ha spaced-repetition.json")
        return
    items = sr.get("items", {})
    if not items:
        print("  (cap ítem a la cua encara)")
        return
    fresh = sum(1 for i in items.values() if (i.get("repetitions") or 0) == 0)
    intervals = collections.Counter(i.get("interval_days") for i in items.values())
    queue = {k: len(v) for k, v in (sr.get("review_queue") or {}).items()}
    print(f"  ítems          : {len(items)}  ·  amb repetitions=0: {fresh}")
    print(f"  intervals      : {dict(intervals)}")
    print(f"  cua            : {queue}")
    if fresh == len(items):
        print("  ⚠ cap ítem ha graduat mai — si ja s'ha fet un /math-review amb el codi nou,")
        print("    vol dir que el bloc math:review_results o l'eina no han arribat.")
    else:
        print("  ✅ hi ha ítems que han avançat")


def check_patterns(d: Path):
    head("patrons d'error")
    mistakes = load(d / "mistakes-db.json")
    if not mistakes:
        print("  ❌ no hi ha mistakes-db.json")
        return
    patterns = mistakes.get("error_patterns", {})
    if not patterns:
        print("  (cap patró encara)")
        return
    cats = collections.Counter(p.get("category") for p in patterns.values())
    print(f"  total          : {len(patterns)}")
    print(f"  per categoria  : {dict(cats)}")
    # Collapse detector: everything landing on the default category
    # (DEFAULT_ERROR_CATEGORY in hooks/db_schema.py — "calculation").
    if len(cats) == 1 and "calculation" in cats:
        print("  ⚠ tot és 'calculation': la taxonomia torna a col·lapsar")
    ranked = sorted(patterns.items(), key=lambda kv: -(kv[1].get("frequency") or 0))[:5]
    for pid, p in ranked:
        idle = days_since(p.get("last_seen") or p.get("last_occurred"))
        print(f"    {pid[:34]:34} freq {p.get('frequency')}  fa {idle if idle is not None else '?'} dies")


def check_mastery(d: Path):
    head("mestria i decaïment")
    mastery = load(d / "mastery-db.json")
    if not mastery:
        print("  ❌ no hi ha mastery-db.json")
        return
    skills = mastery.get("skills", {})
    if not skills:
        print("  (cap habilitat practicada encara)")
        return
    for name, s in sorted(skills.items()):
        if not isinstance(s, dict):
            continue
        level = s.get("mastery_level")
        earned = s.get("mastery_level_earned", "—")
        idle = days_since(s.get("last_practiced"))
        flag = ""
        if isinstance(earned, int) and isinstance(level, int) and level < earned:
            flag = f"  ↓ decaigut des de {earned}"
        print(f"  {name:12} nivell {level} (guanyat {earned}) · últim {s.get('last_practiced')}"
              f" · fa {idle if idle is not None else '?'} dies{flag}")


def check_records(d: Path):
    head("registres estructurats (math_record_answer)")
    folder = d / ".records"
    if not folder.exists():
        print("  (encara no n'hi ha cap)")
        print("  Normal si aquest perfil no ha tingut cap sessió amb el servidor NOU.")
        print("  Es crea sol al primer torn qualificat després de reiniciar la instància.")
        return
    files = sorted(folder.glob("*.jsonl"))
    if not files:
        print("  (el directori existeix però és buit)")
        return
    total = 0
    last = None
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                total += 1
                last = line
    print(f"  fitxers        : {len(files)}  ·  registres: {total}")
    if last:
        try:
            rec = json.loads(last)
        except ValueError:
            print("  ⚠ l'últim registre no és JSON vàlid")
            return
        print(f"  últim          : {rec.get('skill')} · nota {rec.get('score')}/10 · "
              f"{len(rec.get('corrections') or [])} correccions"
              + (f" · ítem {rec['item_id']} qualitat {rec.get('sm2_quality')}" if rec.get("item_id") else ""))


def check_metrics(d: Path):
    head("mètriques per torn")
    path = d / ".metrics" / "turns.jsonl"
    if not path.exists():
        print("  (encara no n'hi ha)")
        print("  Es crea al primer torn amb el servidor nou.")
        return
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    if not rows:
        print("  (fitxer buit)")
        return
    prompts = [r.get("prompt_tokens", 0) for r in rows if r.get("prompt_tokens")]
    # El límit real, no un número escrit a mà: surt de config/fluent.json.
    try:
        repo = Path(__file__).resolve().parent.parent
        ctx = int(json.loads((repo / "config" / "fluent.json").read_text())["models"]["deep"]["ctx"])
    except Exception:
        ctx = 32768
    walls = [r.get("wall_ms", 0) / 1000 for r in rows if r.get("wall_ms")]
    print(f"  torns          : {len(rows)}")
    if prompts:
        print(f"  prompt tokens  : mediana {statistics.median(prompts):.0f} · màxim {max(prompts)}"
              f"   (límit de context: {ctx})")
        if max(prompts) > ctx:
            print(f"  ❌ ALGUN TORN HA PETAT: {max(prompts)} tokens contra un context de {ctx}")
            print("     (la poda automàtica hauria d'evitar-ho; si segueix sortint, apunta-ho)")
        elif max(prompts) > ctx * 0.75:
            print("  ⚠ a prop del límit")
    if walls:
        print(f"  temps per torn : mediana {statistics.median(walls):.1f} s · màxim {max(walls):.1f} s")

    # Qui triga: el model o nosaltres. wall_ms és el torn sencer; model_ms és el
    # temps DINS de llama.cpp. Si creix model_ms, és el model (context, KV
    # quantitzada, mida del prompt). Si creix la diferència, és codi nostre.
    def _split(rows_):
        w = [r.get("wall_ms", 0) / 1000 for r in rows_ if r.get("wall_ms")]
        m = [r.get("model_ms", 0) / 1000 for r in rows_ if r.get("model_ms")]
        t = [r.get("prompt_tokens", 0) for r in rows_ if r.get("prompt_tokens")]
        return (statistics.median(w) if w else 0,
                statistics.median(m) if m else 0,
                statistics.median(t) if t else 0)

    if len(rows) >= 6:
        half = min(10, len(rows) // 2)
        old_w, old_m, old_t = _split(rows[-2 * half:-half])
        new_w, new_m, new_t = _split(rows[-half:])
        print(f"  abans/ara ({half} torns cada tram):")
        print(f"    torn sencer  : {old_w:5.1f} s → {new_w:5.1f} s")
        print(f"    dins el model: {old_m:5.1f} s → {new_m:5.1f} s")
        print(f"    prompt tokens: {old_t:5.0f}   → {new_t:5.0f}")
        d_model = new_m - old_m
        d_ours = (new_w - new_m) - (old_w - old_m)
        if new_w > old_w * 1.25:
            if d_model > d_ours:
                print("  → el temps extra és DINS el model (context, KV quantitzada, prompt més gros)")
            else:
                print("  → el temps extra és FORA del model: codi nostre o persistència")
        else:
            print("  → sense diferència rellevant")
    total = sum(r.get("tool_calls", 0) for r in rows)
    print(f"  crides d'eina  : {total} en total")

    # QUINES eines, no només quantes. "El tutor ha registrat les respostes?" no
    # es pot respondre amb un recompte, i és justament la pregunta que importa.
    names = collections.Counter()
    refused = collections.Counter()
    for r in rows:
        for name in r.get("tools") or []:
            if name.startswith("!"):
                refused[name[1:]] += 1
                names[name[1:]] += 0
            else:
                names[name] += 1
    if not names and total:
        print("  (aquest log és d'abans que es guardessin els noms — fes un torn nou)")
    for name, ok in sorted(names.items(), key=lambda kv: -kv[1]):
        bad = refused.get(name, 0)
        print(f"    {name:24s} {ok:4d} ok" + (f"  ⚠ {bad} rebutjada/es" if bad else ""))
    if names and not names.get("math_record_answer"):
        print("  ⚠ cap crida a math_record_answer: el tutor no ha qualificat res")
        print("    (normal si la sessió es va quedar al menú o al saludo)")
    last = rows[-1]
    when = datetime.fromtimestamp(last.get("ts", 0) / 1000).strftime("%Y-%m-%d %H:%M") if last.get("ts") else "?"
    print(f"  últim torn     : {when}  ({last.get('agent')}, sessió {str(last.get('session_id'))[:24]})")


def check_sessions(d: Path):
    head("BD de sessions")
    current = d / "sessions" / "sessions.db"
    legacy = d / ".opencode" / "opencode" / "opencode.db"
    for label, path in (("nova   ", current), ("antiga ", legacy)):
        if not path.exists():
            print(f"  {label}: —")
            continue
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            counts = []
            for table in ("session", "message", "part"):
                try:
                    counts.append(f"{table}={conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]}")
                except sqlite3.Error:
                    counts.append(f"{table}=?")
            conn.close()
            print(f"  {label}: {path}  ({', '.join(counts)})")
        except sqlite3.Error as exc:
            print(f"  {label}: {path}  ⚠ {exc}")
    if current.exists():
        print("  → el servidor farà servir la NOVA")
    elif legacy.exists():
        print("  → el servidor farà servir l'ANTIGA (migra-la amb scripts/migrate-sessions-db.py)")

    # Les últimes sessions de CADA base, amb qui les ha tancades. Sense això,
    # "no s'ha guardat res" no es distingeix de "s'ha guardat a l'altra base".
    for label, path in (("NOVA", current), ("ANTIGA", legacy)):
        if not path.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            rows = conn.execute(
                "SELECT id, last_activity, COALESCE(metadata,'') FROM session "
                "ORDER BY last_activity DESC LIMIT 5"
            ).fetchall()
            conn.close()
        except sqlite3.Error as exc:
            print(f"  últimes ({label}): ⚠ {exc}")
            continue
        if not rows:
            continue
        print(f"  últimes sessions ({label}):")
        for sid, activity, meta in rows:
            try:
                when = datetime.fromtimestamp(activity / 1000).strftime("%Y-%m-%d %H:%M")
            except (TypeError, ValueError, OSError):
                when = "?"
            done = "capa_b_done" in (meta or "")
            print(f"    {when}  {sid[:24]:24s} {'tancada ✅' if done else 'sense tancar ⏳'}")


def check_historial(d: Path):
    """Quantes sessions hi ha hagut DE DEBÒ, segons tres fonts independents.

    La BD de sessions no és l'única traça. Cada sessió tancada deixa un fitxer a
    `results/` i una entrada a `session-log.json`, i les tres han de quadrar. Si
    la BD en té menys, hi ha transcripcions en un altre fitxer — típicament
    perquè l'opencode antic escrivia a un lloc central compartit abans que
    `flowed-web.sh` fixés `XDG_DATA_HOME` per perfil.
    """
    head("historial: quantes sessions hi ha hagut")

    db_ids, db_count = set(), 0
    for label, rel in (("nova", Path("sessions") / "sessions.db"),
                       ("antiga", Path(".opencode") / "opencode" / "opencode.db")):
        path = d / rel
        if not path.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            ids = {r[0] for r in conn.execute("SELECT id FROM session")}
            conn.close()
        except sqlite3.Error as exc:
            print(f"  BD {label}: ⚠ {exc}")
            continue
        db_ids |= ids
        db_count = max(db_count, len(ids))
        print(f"  BD {label:7s}: {len(ids)} sessions")

    results = sorted((d / "results").glob("*.md")) if (d / "results").exists() else []
    print(f"  results/     : {len(results)} fitxers")

    log_sessions = []
    try:
        log_sessions = json.loads((d / "session-log.json").read_text()).get("sessions", [])
    except Exception:
        pass
    print(f"  session-log  : {len(log_sessions)} entrades")
    if log_sessions:
        dates = [s.get("date") for s in log_sessions if s.get("date")]
        if dates:
            print(f"                 de {min(dates)} a {max(dates)}")

    expected = max(len(results), len(log_sessions))
    if expected > db_count:
        print(f"  ⚠ FALTEN TRANSCRIPCIONS: hi ha rastre de {expected} sessions i la BD"
              f" només en té {db_count}")
        print("     Les dades d'aprenentatge hi són igualment (viuen a les 6 BD JSON);")
        print("     el que falta és el text de la conversa. Busca'l amb:")
        print("       ls -la ~/.local/share/opencode/ 2>/dev/null")
        print("       find ~ -name 'opencode.db' -o -name 'sessions.db' 2>/dev/null | grep -v node_modules")
    elif expected == 0 and db_count == 0:
        print("  (cap sessió encara)")
    else:
        print(f"  ✅ quadra: la BD té almenys tantes sessions com rastre n'hi ha")

    # Quan es va usar de debò: la traça més fiable de l'activitat real.
    if log_sessions:
        by_month = collections.Counter(str(s.get("date", ""))[:7] for s in log_sessions if s.get("date"))
        print("  sessions per mes:", dict(sorted(by_month.items())))

    # Entrada per entrada: quina falta, i si alguna data és sospitosa.
    if log_sessions:
        print("  entrades del session-log:")
        today = date.today().isoformat()
        # El session-log fa servir ids propis ("session-005") i la BD fa servir
        # "ses_...": NO són el mateix espai de noms i no es poden comparar. La
        # primera versió d'aquesta comprovació ho intentava i marcava TOTES les
        # entrades com a "sense transcripció", que és soroll, no diagnòstic.
        for entry in log_sessions:
            sid = str(entry.get("session_id", "?"))
            when = str(entry.get("date", "?"))
            ex = entry.get("exercises_completed")
            cmd = entry.get("command_used", "")
            flag = "  ⚠ data = AVUI" if when == today else ""
            print(f"    {when}  {sid:14s} {str(ex):>3} exercicis  {cmd}{flag}")
        if any(str(e.get("date")) == today for e in log_sessions):
            print()
            print("  ⚠ Hi ha una entrada amb data d'AVUI. Si avui no s'ha practicat,")
            print("    la Capa B ha reprocessat una sessió antiga i li ha posat la data")
            print("    d'avui (update-db.py escriu `date` del report, i el report la posa")
            print("    d'avui quan no en troba cap). Mira quan es va tocar el fitxer:")
            print(f"      ls -la {d}/session-log.json {d}/results/ | tail -12")


def check_sortida(d: Path, limit: int = 3):
    """Què ha dit el tutor, literalment, i què en detecta l'app.

    Tres coses de l'app depenen que el tutor faci una cosa concreta:
    l'indicador ✏️ N/M (crida `math_record_answer`), el botó 🔊 de la
    correcció (l'etiqueta `Correct version:`) i les frases marcades
    (`[[say]]`). Si el model no ho fa, les tres fallen en silenci i des de
    fora sembla que l'app estigui trencada. Això ho ensenya en una pantalla.
    """
    head(f"últims {limit} missatges del tutor (literals)")
    db = d / "sessions" / "sessions.db"
    if not db.exists():
        print("  (no hi ha BD de sessions)")
        return
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT m.id, m.session_id, m.time_created, m.data FROM message m "
            "ORDER BY m.time_created DESC LIMIT 60"
        ).fetchall()
        texts = []
        for mid, sid, ts, data in rows:
            try:
                if json.loads(data or "{}").get("role") != "assistant":
                    continue
            except ValueError:
                continue
            parts = conn.execute(
                "SELECT data FROM part WHERE message_id = ? ORDER BY time_created", (mid,)
            ).fetchall()
            body = []
            for (pd,) in parts:
                try:
                    part = json.loads(pd or "{}")
                except ValueError:
                    continue
                if part.get("type") == "text" and part.get("text"):
                    body.append(part["text"])
            if body:
                texts.append((sid, ts, "\n".join(body)))
            if len(texts) >= limit:
                break
        conn.close()
    except sqlite3.Error as exc:
        print(f"  ⚠ {exc}")
        return

    if not texts:
        print("  (cap missatge del tutor encara)")
        return

    records_dir = d / ".records"
    for sid, ts, text in reversed(texts):
        when = datetime.fromtimestamp((ts or 0) / 1000).strftime("%H:%M:%S")
        print(f"\n  ── {when}  sessió {str(sid)[:24]} " + "─" * 20)
        for line in text.splitlines():
            print(f"  │ {line}")
        flags = []
        flags.append("nota /10 ✅" if re.search(r"score\s*:?\s*\d+\s*/\s*10", text, re.I)
                     else "nota /10 ❌")
        # Mirall EXACTE del que fa web/app.js (SPEAKABLE_LABEL_RE + quotedIn).
        # La primera versió buscava "correct version" a pèl i deia ✅ sobre
        # "Now type the correct version yourself:" — que és una instrucció a
        # l'alumne, no la frase model. L'instrument mentia.
        say_lines = [ln for ln in text.splitlines()
                     if re.search(r"correct version|natural alternative|you could also say", ln, re.I)]
        quoted = []
        for ln in say_lines:
            q = re.findall(r'"([^"]{2,300})"', ln)
            quoted.extend(q)
        # La frase pot anar a la línia següent de l'etiqueta.
        if say_lines and not quoted:
            lines = text.splitlines()
            for i, ln in enumerate(lines):
                if ln in say_lines and i + 1 < len(lines):
                    quoted.extend(re.findall(r'"([^"]{2,300})"', lines[i + 1]))
        if quoted:
            flags.append(f"botó 🔊 sobre {len(quoted)} frase/s ✅")
        elif say_lines:
            flags.append("etiqueta trobada però cap frase entre cometes ❌ → sense 🔊")
        else:
            flags.append("cap frase model ❌ → sense 🔊")
        flags.append("[[say]] ✅" if "[[say]]" in text else "[[say]] ❌")
        rec = records_dir / f"{sid}.jsonl"
        n = len(rec.read_text().splitlines()) if rec.exists() else 0
        flags.append(f"registres de la sessió: {n}" + (" ❌ → l'indicador ✏️ no es mourà" if n == 0 else " ✅"))
        print("  └─ " + " · ".join(flags))
    print()


def check_tts(d: Path):
    """Veu: què hi ha instal·lat i si aquest perfil en pot fer servir cap."""
    head("veu (TTS)")
    repo = Path(__file__).resolve().parent.parent
    try:
        tts = json.loads((repo / "config" / "fluent.json").read_text()).get("tts", {})
    except Exception as e:
        print(f"  no puc llegir config/fluent.json: {e}")
        return
    # Same rule as server/src/tts.ts (loadTtsConfig): the machine's own install
    # in _tts/ next to the profiles; the config only says whether to use it.
    langs = {"en": "English", "de": "German", "fr": "French", "es": "Spanish",
             "ca": "Catalan", "it": "Italian", "pt": "Portuguese", "nl": "Dutch"}
    cands = [Path(os.environ["FLOWED_TTS_DIR"])] if os.environ.get("FLOWED_TTS_DIR") else []
    cands += [d.parent / "_tts", profiles_root() / "_tts"]
    tts_dir = next((c for c in cands if c.exists()), None)
    binary = tts_dir / "piper" / "piper" if tts_dir else None
    voices = {}
    for f in sorted((tts_dir / "voices").glob("*.onnx")) if tts_dir else []:
        lang = langs.get(f.name[:2]) if re.match(r"^[a-z]{2}_[A-Z]{2}-", f.name) else None
        if lang and Path(str(f) + ".json").is_file():
            voices.setdefault(lang, str(f))
    enabled = tts.get("enabled") is True and bool(voices)
    print(f"  config enabled : {tts.get('enabled') is True}")
    print(f"  carpeta        : {tts_dir or '— cap _tts/ (scripts/flowed-tts.sh install <veu>)'}")
    print(f"  binari         : {binary if binary and binary.is_file() else '❌ no trobat'}")
    if not voices:
        print("  veus           : cap  (scripts/flowed-tts.sh install <veu>)")
    for lang, model in voices.items():
        print(f"  {lang:15s}: {model} ✅")

    target = None
    try:
        target = json.loads((d / "learner-profile.json").read_text()).get("learner", {}).get("target_language")
    except Exception:
        pass
    match = next((m for lang, m in voices.items() if lang.lower() == str(target or "").lower()), None)
    usable = enabled and bool(match) and Path(str(match)).is_file()
    print(f"  aquest perfil  : aprèn {target or '?'} → "
          + ("sonarà 🔊" if usable else "sense veu (no sortirà cap botó)"))

    cache = d / ".audio"
    files = list(cache.glob("*.wav")) if cache.exists() else []
    size_mb = sum(f.stat().st_size for f in files) / 1024 / 1024
    print(f"  cau            : {len(files)} fitxers, {size_mb:.1f} MB"
          f" (límit {tts.get('cache_max_mb', 200)} MB)")


def check_lesson(d: Path):
    """Veredicte d'una sola pantalla sobre la lliçó d'avui.

    Escrita arran del 16/09/2026, quan una lliçó sencera va córrer sense el
    skill `math-review` carregat: cap correcció a la pantalla, el comptador
    clavat a 0 de 12 amb tretze exercicis contestats, i el mateix exercici
    vint-i-cinc vegades. Cap dels checks que ja hi havia ho deia en una línia.
    Aquest sí: mira les quatre coses que van fallar aquell dia i diu PASSA o
    FALLA per a cadascuna.
    """
    head("la lliçó d'avui — veredicte")
    today = date.today().isoformat()
    verdicts = []

    def verdict(ok, label, detail=""):
        verdicts.append(ok)
        print(f"  {'✅ PASSA' if ok else '❌ FALLA'}  {label}" + (f"  — {detail}" if detail else ""))

    # 1. El tutor corregeix. Els tres senyals que l'app necessita del text.
    texts = _recent_tutor_texts(d, limit=12)
    if not texts:
        print("  (cap missatge del tutor encara — fes uns quants exercicis primer)")
        return
    marked = sum(1 for t in texts if re.search(r"[🟢🟡🔴✅❌]", t))
    corrected = sum(1 for t in texts if "Correct version:" in t)
    scored = sum(1 for t in texts if re.search(r"\b\d{1,2}\s*/\s*10\b", t))
    # El llistó: un terç dels últims missatges. En una lliçó sana gairebé cada
    # torn del tutor qualifica una resposta; els que no ho fan són el menú i el
    # resum. Un 0/8 o un 2/8 és el símptoma del 16/09, no soroll estadístic.
    floor = max(1, len(texts) // 3)
    verdict(marked >= floor, "el tutor marca les respostes", f"{marked}/{len(texts)} missatges")
    verdict(corrected >= floor, "ensenya la versió correcta", f"{corrected}/{len(texts)} missatges")
    verdict(scored >= floor, "posa nota", f"{scored}/{len(texts)} missatges")

    # 2. Hi ha registres estructurats (el que alimenta SM-2).
    rec_dir = d / ".records"
    lines = 0
    if rec_dir.is_dir():
        for f in rec_dir.glob("*.jsonl"):
            lines += sum(1 for line in f.read_text().splitlines() if line.strip())
    verdict(lines > 0, "hi ha respostes registrades (.records/)", f"{lines} línies")

    # 3. El comptador de la lliçó es mou.
    plan = load(d / ".daily" / f"lesson-{today}.json")
    if not plan:
        print("  ⚠  encara no hi ha pla de lliçó per avui (prem 🎓 Lesson)")
    else:
        done, total = plan.get("done", 0), plan.get("total", 0)
        verdict(done > 0, "el comptador de la lliçó avança", f"{done} de {total}")
        cov = plan.get("covered", [])
        verdict(len(cov) >= done, "queda constància del que s'ha preguntat",
                f"{len(cov)} exercicis anotats")
        junk = [c for c in cov if c in ("critical", "easy", "medium", "hard")]
        verdict(not junk, "cap etiqueta de brossa a la llista", ", ".join(junk) or "neta")

    # 4. Cap pregunta repetida. El 16/09 el mateix bloc va sortir vint-i-cinc
    # vegades seguides; dues ja són sospitoses, tres són el bucle.
    counts = collections.Counter(t.strip() for t in texts)
    worst, times = counts.most_common(1)[0]
    verdict(times < 3, "cap resposta del tutor repetida",
            f"la més repetida surt {times} cop(s) dels últims {len(texts)}")
    if times >= 3:
        print(f"       ↳ «{worst.splitlines()[0][:70]}»")

    print()
    if all(verdicts):
        print("  → tot correcte. El skill ha arribat al model.")
    else:
        print("  → alguna cosa no hi és. Mira `sortida` per veure el text literal:")
        print(f"     python3 scripts/flowed-check.py sortida --dir {d}")


def _recent_tutor_texts(d: Path, limit: int = 8) -> list[str]:
    """Els últims missatges del tutor, el més recent primer."""
    db = d / "sessions" / "sessions.db"
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT id, data FROM message ORDER BY time_created DESC LIMIT 80"
        ).fetchall()
        out = []
        for mid, data in rows:
            try:
                if json.loads(data or "{}").get("role") != "assistant":
                    continue
            except ValueError:
                continue
            body = []
            for (pd,) in conn.execute(
                "SELECT data FROM part WHERE message_id = ? ORDER BY time_created", (mid,)
            ):
                try:
                    part = json.loads(pd or "{}")
                except ValueError:
                    continue
                if part.get("type") == "text" and str(part.get("text", "")).strip():
                    body.append(str(part["text"]))
            if body:
                out.append("\n".join(body))
            if len(out) >= limit:
                break
        conn.close()
        return out
    except sqlite3.Error:
        return []


OPEN_PRACTICES = ("math-speaking", "math-writing", "math-reading")


def check_open(d: Path):
    """Les pràctiques obertes d'un dia (per defecte avui; FLOWED_CHECK_DAY=AAAA-MM-DD).

    Escrita el 2026-09-27, amb un 27B nou a producció: saber, sense tocar res,
    si les respostes de Speaking/Writing/Reading d'aquell dia es van guardar i
    puntuar. Per torn: si el tutor va cridar math_record_answer (puntuat pel
    model) o si el servidor el va haver de derivar (el model no ho va fer), i
    els errors LLM del log de la web.
    """
    day = os.environ.get("FLOWED_CHECK_DAY") or date.today().isoformat()
    head(f"pràctiques obertes — {day}")

    def day_of(ms) -> str:
        try:
            return datetime.fromtimestamp(ms / 1000).date().isoformat()
        except (TypeError, ValueError, OSError):
            return ""

    turns = []
    mp = d / ".metrics" / "turns.jsonl"
    for line in (mp.read_text(encoding="utf-8").splitlines() if mp.exists() else []):
        try:
            t = json.loads(line)
        except ValueError:
            continue
        if day_of(t.get("ts")) == day:
            turns.append(t)
    recs = []
    for f in sorted((d / ".records").glob("*.jsonl")) if (d / ".records").exists() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if day_of(r.get("ts")) == day:
                recs.append(r)
    # a record belongs to the first turn of its session that ends at or after it
    by_sess: dict[str, list] = collections.defaultdict(list)
    for t in turns:
        by_sess[t.get("session_id")].append(t)
    for ts in by_sess.values():
        ts.sort(key=lambda t: t.get("ts") or 0)
    per = {c: {"turns": 0, "no_tool": 0, "model": 0, "derived": 0, "scores": []} for c in OPEN_PRACTICES}
    for t in turns:
        c = t.get("command")
        if c in per:
            per[c]["turns"] += 1
            per[c]["no_tool"] += 1 if not t.get("tool_calls") else 0
    for r in recs:
        t = next((t for t in by_sess.get(r.get("session_id"), []) if (t.get("ts") or 0) >= (r.get("ts") or 0)), None)
        c = t.get("command") if t else None
        if c in per:
            per[c]["derived" if r.get("derived") else "model"] += 1
            if isinstance(r.get("score"), (int, float)):
                per[c]["scores"].append(r["score"])
    if not any(v["turns"] for v in per.values()):
        print("  cap torn de Speaking/Writing/Reading aquest dia")
    for c, v in per.items():
        if not v["turns"]:
            continue
        avg = f"{statistics.mean(v['scores']):.1f}" if v["scores"] else "—"
        print(f"  {c.split('-')[-1]:9s}: {v['turns']:3d} torns · puntuades pel model {v['model']}"
              f" · derivades pel servidor {v['derived']} · sense cap eina {v['no_tool']} · nota mitjana {avg}")
    errs = []
    for f in sorted(d.glob("math-web-*.log")) + sorted(d.glob("flowed-web-*.log")):
        errs += [l.strip() for l in f.read_text(encoding="utf-8", errors="replace").splitlines()
                 if "LLM HTTP" in l or "TemplateError" in l]
    print(f"  errors LLM al log de la web (tot el log): {len(errs)}")
    for l in errs[-3:]:
        print(f"    {l[:160]}")
    print("  Llegenda: «derivades» = el model no va cridar l'eina i el servidor va guardar")
    print("  la resposta igualment; «sense cap eina» inclou els torns de presentar exercici.")


RUNNERS = {
    "profile": check_profile,
    "sm2": check_sm2,
    "patterns": check_patterns,
    "mastery": check_mastery,
    "records": check_records,
    "metrics": check_metrics,
    "sessions": check_sessions,
    "tts": check_tts,
    "sortida": check_sortida,
    "historial": check_historial,
    "lliço": check_lesson,
    "obertes": check_open,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only checks on a Flowed learner profile")
    parser.add_argument("check", choices=(*CHECKS, "all"), help="what to look at")
    parser.add_argument("profile", nargs="?", help="profile id under ~/.flowed/ (e.g. demo-en)")
    parser.add_argument("--dir", help="explicit profile directory (instead of a profile id)")
    args = parser.parse_args()

    if args.dir:
        profile_dir = Path(args.dir).expanduser()
    elif args.profile:
        profile_dir = profiles_root() / args.profile
    else:
        parser.error("give a profile id or --dir")

    if not profile_dir.exists():
        print(f"❌ no existeix: {profile_dir}", file=sys.stderr)
        return 1
    print(f"perfil: {profile_dir}")

    for name in (CHECKS if args.check == "all" else (args.check,)):
        RUNNERS[name](profile_dir)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
