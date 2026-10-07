#!/usr/bin/env python3
"""End-to-end math session against the REAL app, with a verdict.

Why this exists, in the words of the person who needed it: *"abans també va
passar test i per les nenes va ser un autèntic desastre... lo obvi ho veig de
seguida, però la resta sense això costa."*

Every other test in this repo checks the code. None of them makes the tutor
speak. On 2026-09-16 the whole suite was green while the tutor ran sixty turns
without correcting a single answer, because the thing that broke was what the
model was told, and no unit test has ever read a model's reply.

This does. It opens a session over the HTTP API exactly as the browser does,
presses the math buttons — 🎲 Go, 🔁 Review, 📚 Facts, 🏁 End — answers the
exercises, and reads what comes back, checking the handful of things that,
when they fail, make a child think the app is broken:

  * every answer gets a marker, a correct version and a score
  * no curly braces (the tutor printing its own template)
  * no exercise asked twice
  * the lesson is not closed before its exercises are done
  * the counter moves, and the answers reach .records/
  * (WP1.9, math path) the bank serves compute/compare/steps cards and grades
    them without the model; a steps answer comes back as an annotated trace;
    the level wording is m1..m6, never CEFR; and 🏁 End really persists —
    results file, session log, and the SM-2 schedule advanced.

It needs the server running:  scripts/flowed-web.sh --app --port N <profile>

  python3 scripts/flowed-e2e.py --port 4200 test-math
  python3 scripts/flowed-e2e.py --port 4200 test-math --answers 8 --transcript /tmp/t.md
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import zlib
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from main_paths import profiles_root  # noqa: E402  (where the profiles live)

REPO = Path(__file__).resolve().parent.parent


def _home_from_env_file() -> None:
    """A bare `python3 scripts/flowed-e2e.py` has no .env: the bash wrappers
    (flowed-bench.sh, flowed-web.sh) load it, a direct run does not — and
    profiles_root() would then fall back to ~/.flowed, which on a machine that
    runs both forks is the LANGUAGE product's home, not this one's. Take
    FLOWED_HOME from the repo's .env when nothing else set it."""
    if os.environ.get("FLOWED_HOME"):
        return
    try:
        for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line.startswith("FLOWED_HOME="):
                os.environ["FLOWED_HOME"] = line.split("=", 1)[1].strip().strip("\"'")
                return
    except OSError:
        pass


_home_from_env_file()
MARKER = re.compile(r"[🟢🟡🔴✅❌]")
SCORE = re.compile(r"\b\d{1,2}\s*/\s*10\b")
# The bank Review closes with the server's fixed "Lesson complete!" (agent.ts);
# the model-driven practices say "Session Complete" (the skills' summaries).
CLOSING = re.compile(r"session complete|lesson complete|sessió completa|lliçó completa", re.I)
MENU_RE = re.compile(r"what would you like to practice|surprise me|spaced review \(today's due", re.I)
GREETING_RE = re.compile(r"^#{0,3}\s*(hello|hi|hola|welcome back)\b", re.I | re.M)
BRACE = re.compile(r"\{[^}\n]{0,60}\}")
# A CEFR token in a math session is the language era leaking through (WP1.9:
# the level wording is m1..m6). Word-bounded so "Form" or "A1.b" inside an id
# does not fire; the pilot ids are `m4.*`.
CEFR_LEAK = re.compile(r"\b(?:A[12]|B[12]|C[12])\b")

# The whole line after the label, quotes stripped afterwards. The first version
# stopped at any apostrophe, so "I don't know" came back as "I don" — the script
# then answered wrongly three times running and reported the tutor for retrying.
# A wrong answer from the test is indistinguishable from a wrong answer from a
# child, and the tutor was right both times.
CORRECT_VERSION = re.compile(r"\*\*Correct version:?\*\*\s*\n+([^\n]{1,120})", re.I)




# ---- the math bank (WP1.9): what the server serves, and what a correct answer is ----
#
# The bank path (🎲 Go / 🔁 Review / 📚 Facts on a competence with a bank) never
# asks the model: the server picks an item, paints the card (server/src/bank.ts)
# and grades with hooks/bank.py. The card names its competence in the comp-tag
# and its problem on a labelled line, so the script can look the item up in the
# bank JSON and answer it exactly — the same lookup the grader does.

_BANK_ITEMS: dict[str, dict] | None = None


def bank_items() -> dict[str, dict]:
    """Every bank item of the repo's curricula, by id (main files + steps/)."""
    global _BANK_ITEMS
    if _BANK_ITEMS is None:
        out: dict[str, dict] = {}
        for f in sorted((REPO / "curriculum" / "bank").glob("*/*.json")) + \
                   sorted((REPO / "curriculum" / "bank").glob("*/steps/*.json")):
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for it in (doc.get("items") if isinstance(doc, dict) else doc) or []:
                if isinstance(it, dict) and it.get("id"):
                    out[it["id"]] = it
        _BANK_ITEMS = out
    return _BANK_ITEMS


CARD_RE = re.compile(
    r"## Exercise \d+: (?P<kind>Calculation|Steps|Vocabulary|Grammar)[^\n]*?"
    r"<span class=\"comp-tag\"[^>]*>(?P<comp>[\w.]+)</span>\s*\n+\n?"
    r"\*\*Problem:\*\*\s*(?P<problem>[^\n]+)", re.I)


def bank_card(reply: str) -> dict | None:
    """The bank item behind the card on screen: (last card heading + problem) →
    the item from the bank JSON. None when the exercise is not a bank card.

    The card's KIND decides the item's type: a steps file may carry the SAME
    problem text as the compute items of its competence (the m4 pilot:
    frac_add_unlike.031 is "1/2 + 2/6", exactly .001's problem). Matching on
    problem alone answered a Steps card with a single number and the grader —
    correctly — marked it wrong. So: Steps heading → a steps item; anything
    else → a non-steps one."""
    m = None
    for m in CARD_RE.finditer(reply or ""):
        pass
    if not m:
        return None
    problem = m.group("problem").strip()
    comp = m.group("comp").strip()
    want_steps = m.group("kind").strip().lower() == "steps"
    same = [it for it in bank_items().values()
            if str(it.get("problem", "")).strip() == problem
            and str(it.get("competence", "")) == comp
            and (it.get("type") == "steps") == want_steps]
    if len(same) == 1:
        return same[0]
    if same:
        return same[0]          # same problem twice in one competence: first wins
    hits = [it for it in bank_items().values()
            if str(it.get("problem", "")).strip() == problem
            and (it.get("type") == "steps") == want_steps]
    return hits[0] if len(hits) == 1 else None


def steps_trace(item: dict) -> str:
    """The whole worked solution, one operation per line — the v1 answer shape
    (DISSENY-MATEMATIQUES §4.2): each expected line evaluates to its step value."""
    return "\n".join(str(s.get("expect", "")) for s in item.get("steps", []))


def math_answer(item: dict, kind: str) -> str:
    """A learner's answer to a bank card. right: the exact answer / the full
    trace. wrong: a plausible slip (a digit transposed, or the first step of a
    trace broken) — the way a child is wrong, not a typed-in "banana"."""
    if item.get("type") == "steps":
        if kind == "right":
            return steps_trace(item)
        lines = steps_trace(item).splitlines()
        if lines:
            lines[0] = lines[0] + " + 1"   # breaks step 1; the rest drag the error
        return "\n".join(lines)
    ans = str(item.get("answer", ""))
    if kind == "right":
        return ans
    digits = re.findall(r"\d", ans)
    if len(digits) >= 2:                      # transpose two digits
        a = list(ans)
        i, j = [k for k, c in enumerate(ans) if c.isdigit()][:2]
        a[i], a[j] = a[j], a[i]
        return "".join(a)
    return "0"


def seed_math_review(prof_dir: Path, ids: list[str]) -> None:
    """Put bank items in the review queue, due today, so 🔁 Review has material
    to serve (review_pick takes due items whose id is a bank id).

    Everything that could undo the seed goes away with it, measured live on
    test-math (WP1.9): update-db.py's T0 snapshots (`.update-state/`) are a
    time machine — a session left unfinished by an earlier run re-applies and
    rolls spaced-repetition.json back to before the seed; the frozen lesson
    plan sizes the lesson to the old queue; and bank-progress.json's
    answered-today ledger silently drops items from the picks. Same discipline
    as restore() and reset_profile() above: wait for the hooks to settle FIRST,
    then archive, then write."""
    wait_quiet(prof_dir)
    archive(prof_dir / ".daily")
    archive(prof_dir / ".update-state")
    archive(prof_dir / ".records")
    park_learner_path(prof_dir)
    for name in ("bank-progress.json", "session-draft.json"):
        f = prof_dir / name
        if f.exists():
            out = prof_dir / "_archive"
            out.mkdir(exist_ok=True)
            f.rename(out / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}")
    sr_path = prof_dir / "spaced-repetition.json"
    today = date.today().isoformat()

    def write_seed() -> None:
        doc = json.loads(sr_path.read_text(encoding="utf-8")) if sr_path.exists() else {"items": {}}
        items = doc.setdefault("items", {})
        # pop first: re-assigning an existing key keeps its OLD position, and the
        # due queue is served in file order among equal due dates.
        for iid in ids:
            items.pop(iid, None)
        for iid in ids:
            items[iid] = {
                "item_id": iid, "item_type": "bank_item", "easiness_factor": 2.5,
                "interval_days": 1, "repetitions": 0, "due_date": today,
                "last_reviewed": None, "review_history": [], "priority": "medium",
            }
        sr_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def settled() -> bool:
        try:
            items = json.loads(sr_path.read_text(encoding="utf-8")).get("items", {})
        except (OSError, ValueError):
            return False
        if not all(items.get(iid, {}).get("due_date") == today and not items.get(iid, {}).get("retired")
                   for iid in ids):
            return False
        # Order too: the due queue is served in FILE order among equal due
        # dates, so a clobber that restores an older file (right dates, wrong
        # order) would still pass a dates-only check and then serve the wrong
        # first card. The seed ids must sit in the file in seed order.
        present = [k for k in items if k in set(ids)]
        return present == list(ids)

    # The write can be clobbered by a hook that fires just after it (the 30-min
    # sweeper finalising a stale session re-applies update-db, which restores a
    # T0 snapshot). Write, let the hooks settle, verify, and rewrite if the seed
    # did not stick — so the lesson is guaranteed to start from the seeded queue.
    for attempt in range(4):
        write_seed()
        wait_quiet(prof_dir)
        if settled():
            return
        print(f"  ⚠ la cua sembrada no s'ha mantingut (intent {attempt + 1}); re-semo")
    raise SystemExit("❌ no s'ha pogut sembrar la cua de repàs de forma estable")




class Client:
    def __init__(self, port: int, password: str, timeout: int, user: str = "opencode"):
        self.base = f"http://127.0.0.1:{port}"
        self.timeout = timeout
        # The server accepts the profile's own login name OR the literal
        # "opencode" (http.ts). "opencode" is the one that is true for every
        # profile, so it is the one to send.
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

    def _call(self, path: str, payload=None, method=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method or ("POST" if data else "GET"),
            headers={"Authorization": self.auth, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            body = r.read().decode()
        return json.loads(body) if body.strip() else {}

    def new_session(self) -> str:
        return self._call("/api/session", {"title": "e2e"})["id"]

    def command(self, sid: str, cmd: str):
        return self._call(f"/api/session/{sid}/command", {"agent": "learner", "command": cmd})

    def say(self, sid: str, text: str):
        return self._call(f"/api/session/{sid}/message",
                          {"agent": "learner", "parts": [{"type": "text", "text": text}]})


def tutor_text(outcome) -> str:
    """The tutor's visible reply from a turn outcome."""
    parts = (outcome or {}).get("parts") or []
    return "\n".join(str(p.get("text", "")) for p in parts
                     if p.get("type") == "text" and str(p.get("text", "")).strip()).strip()


def tools_used(outcome) -> list[str]:
    return [p.get("tool") for p in ((outcome or {}).get("parts") or []) if p.get("type") == "tool"]


def disk_build_stamp() -> str:
    """What server/src looks like right now, by the server's own function."""
    script = (
        "(async()=>{const fs=await import('node:fs');"
        f"const m=await import({json.dumps(str(REPO / 'server' / 'src' / 'pacing.ts'))});"
        f"console.log(m.buildStamp({json.dumps(str(REPO))},"
        "f=>fs.readFileSync(f,'utf8'),d=>fs.readdirSync(d)));})()"
    )
    try:
        p = subprocess.run(["node", "--experimental-strip-types", "-e", script],
                           capture_output=True, text=True, timeout=30)
        return p.stdout.strip()
    except Exception:
        return ""


def fingerprints(text: str) -> list[str]:
    """The server's own fingerprinting, not a second copy of it."""
    script = (
        "let s='';process.stdin.on('data',c=>s+=c).on('end',async()=>{"
        f"const m=await import({json.dumps(str(REPO / 'server' / 'src' / 'pacing.ts'))});"
        "console.log(JSON.stringify(m.exerciseFingerprints(s)));});"
    )
    try:
        p = subprocess.run(["node", "--experimental-strip-types", "-e", script],
                           input=text, capture_output=True, text=True, timeout=30)
        return json.loads(p.stdout.strip() or "[]")
    except Exception:
        return []


class Report:
    def __init__(self):
        self.rows: list[tuple[bool, str, str]] = []
        self.guards = 0
        # (repeats across practices, unanswered exercises shown again, examples):
        # information, never a verdict.
        self.notes: list[tuple[int, int, list[str]]] = []

    def check(self, ok: bool, label: str, detail: str = ""):
        self.rows.append((bool(ok), label, detail))
        return ok

    def render(self) -> int:
        print("\n=== veredicte ===")
        for ok, label, detail in self.rows:
            print(f"  {'✅ PASSA' if ok else '❌ FALLA'}  {label}" + (f"  — {detail}" if detail else ""))
        bad = [r for r in self.rows if not r[0]]
        print()
        if bad:
            print(f"  → {len(bad)} de {len(self.rows)} malament. NO despleguis.")
        else:
            print("  → tot correcte.")
        return 1 if bad else 0


RESETTABLE = re.compile(r"^(test|demo|e2e)", re.I)
PROFILE_DBS = ("learner-profile.json", "mastery-db.json", "mistakes-db.json",
               "progress-db.json", "session-log.json", "spaced-repetition.json")


def snapshot(prof_dir: Path) -> dict[str, str]:
    """The profile as it is right now, so a repeat can start from the same place.

    A lesson consumes the day and the queue: it fills the plan to 6 of 6 and
    pushes every item it reviewed into the future. Running the same scenario
    twice without putting that back is two different experiments — the first
    `--repeat 3` gave one usable run, one on an already-finished lesson, and one
    that correctly refused to start.
    """
    return {n: (prof_dir / n).read_text(encoding="utf-8")
            for n in PROFILE_DBS if (prof_dir / n).exists()}


def archive(d: Path) -> int:
    """Move a directory's live files into `_archive/`, once — see the twin of
    this function in `flowed-seed.py` for the ENAMETOOLONG it replaces. An
    archive is a place, not a suffix chained onto the name every run."""
    if not d.is_dir():
        return 0
    out = d / "_archive"
    moved = 0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for f in d.iterdir():
        # A day archived by flowed-advance-day.py (".<name>.day-<stamp>") is history of a
        # run that is over: leaving it makes the next run's "yesterday" checks read it.
        if f.is_dir() or (f.name.startswith(".") and ".day-" not in f.name):
            continue
        out.mkdir(exist_ok=True)
        f.rename(out / f"{stamp}-{f.name}")
        moved += 1
    return moved


def due_now(prof_dir: Path) -> list[str]:
    """Which items are due today, read the same way the server reads them.

    Printed at the start of every run because an uneven starting point was the
    single source of every misleading number in this rig: a run that begins with
    nothing due takes the "first lesson ever" path, is forbidden from labelling
    anything "Review", and cannot produce a record with an item_id. Comparing it
    with a run that had three due is comparing two different experiments.
    """
    today = date.today().isoformat()
    try:
        sr = json.loads((prof_dir / "spaced-repetition.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    return sorted(k for k, v in (sr.get("items") or {}).items()
                  if isinstance(v, dict) and isinstance(v.get("due_date"), str)
                  and v["due_date"] <= today)


def wait_quiet(prof_dir: Path, timeout: float = 60.0, settle: float = 2.5) -> float:
    """Wait until the server's persistence has finished writing.

    `runAutoPersistence` is fired WITHOUT await: the reply reaches the learner
    (and this script) while `accumulate-session.py` is still to come, and that
    hook calls `update-db.py` with the whole accumulated payload — so the queue
    and the day's plan are written AFTER the answer came back.

    The first version of this only asked "is a hook running?", polled
    immediately, and returned in 0.4s — before the spawn had even happened. The
    restore then landed first and the hook overwrote it: execution 3 opened a
    lesson that was already 1 of 6 and the run aborted. So quiet means BOTH: no
    hook process, and nothing in the profile touched for `settle` seconds.
    """
    watched = [prof_dir, prof_dir / ".daily", prof_dir / ".records",
               prof_dir / ".update-state"]

    def newest() -> float:
        t = 0.0
        for d in watched:
            if not d.is_dir():
                continue
            for f in d.iterdir():
                if f.is_file():
                    try:
                        t = max(t, f.stat().st_mtime)
                    except OSError:
                        pass
        return t

    began = time.time()
    deadline = began + timeout
    while time.time() < deadline:
        busy = subprocess.run(
            ["pgrep", "-f", r"(accumulate-session|update-db|persist-session)\.py"],
            capture_output=True, text=True).returncode == 0
        idle = time.time() - newest()
        if not busy and idle >= settle:
            return time.time() - began
        time.sleep(0.4)
    msg = (f"⚠ la persistència encara escrivia després de {timeout:.0f}s "
           "(accumulate-session.py / update-db.py penjat?); continuo igualment — "
           "el punt de partida d'aquesta execució NO és de fiar")
    print(msg)
    print(msg, file=sys.stderr)
    return timeout


def restore(prof_dir: Path, snap: dict[str, str]) -> None:
    if not RESETTABLE.match(prof_dir.name):
        raise SystemExit(f"❌ restaurar només en perfils de proves, no en {prof_dir.name}")
    for name, body in snap.items():
        (prof_dir / name).write_text(body, encoding="utf-8")
    archive(prof_dir / ".daily")
    archive(prof_dir / ".records")
    park_learner_path(prof_dir)
    # The T0 snapshots are a time machine: re-applying a session restores the
    # databases to the snapshot taken before it. Leaving one from a previous
    # run means the next finalisation rolls the profile back to it.
    archive(prof_dir / ".update-state")
    draft = prof_dir / "session-draft.json"
    if draft.exists():
        draft.unlink()


def park_learner_path(prof_dir: Path) -> None:
    """The learner path (curriculum) is derived from .records/: when the records are
    archived, the path goes with them, or the next run starts from the last one's.
    The same for the courses made of it: certificates, archived courses, notices."""
    out = prof_dir / "_archive"
    stamp = time.strftime('%Y%m%d-%H%M%S')
    for name in ("learner-path.json", "certificates.json", "course-notices.json"):
        f = prof_dir / name
        if f.exists():
            out.mkdir(exist_ok=True)
            f.rename(out / f"{stamp}-{name}")
    courses = prof_dir / "courses"
    if courses.is_dir():
        out.mkdir(exist_ok=True)
        courses.rename(out / f"{stamp}-courses")


def reset_profile(prof_dir: Path) -> None:
    """Blank the learning state so a run starts from the same place every time.

    Refuses anything that is not obviously a scratch profile. The answers this
    script gives are deliberately wrong, and a learner's real history is not
    something to feed them to.
    """
    if not RESETTABLE.match(prof_dir.name):
        raise SystemExit(f"❌ --reset només en perfils de proves (test*/demo*/e2e*), no en {prof_dir.name}")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    blanks = {
        "mistakes-db.json": {"error_patterns": {}},
        "spaced-repetition.json": {"items": {},
                                   "review_queue": {"today": [], "tomorrow": [],
                                                    "this_week": [], "later": []}},
    }
    for name, blank in blanks.items():
        f = prof_dir / name
        if not f.exists():
            continue
        (prof_dir / f"{name}.bak-{stamp}").write_text(f.read_text(), encoding="utf-8")
        doc = json.loads(f.read_text())
        doc.update(blank)
        f.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    for d in (".daily", ".records", ".update-state"):
        src = prof_dir / d
        if not src.is_dir():
            continue
        # Moved OUT to `_archive/`, never renamed in place: renaming kept the old
        # `.bak-<stamp>` suffix on the name and appended a new one each reset, so
        # ten resets in a day grew a 250+ char filename and the next `os.rename`
        # failed with ENAMETOOLONG (measured 2026-09-22, test-en). A backup file
        # already out in `_archive/` is left alone — it is not touched again.
        #
        # `.update-state` MUST be cleared here too: it holds update-db.py's T0
        # snapshot per session_id (hooks/update-db.py, `save_state`/`load_state`).
        # A web session id survives in the browser's localStorage across page
        # reloads, so a leftover T0 file from before the reset makes the NEXT
        # per-turn persist for that same session_id restore learner-profile.json
        # (and the other 5 DBs) to their pre-reset content — silently discarding
        # the reset and any manual edit made after it. Measured 2026-09-22,
        # test-en: `target_level` set to A1 right after a reset reverted to the
        # pre-reset A2 on the session's very next autosave, because
        # `.update-state/session-001@<day>.json` still held the old T0.
        out = prof_dir / "_archive" / f"{stamp}-{d}"
        for f in list(src.glob("*")):
            out.mkdir(parents=True, exist_ok=True)
            f.rename(out / f.name)
    park_learner_path(prof_dir)

    # Blanking the databases is not enough. Sessions from earlier runs are still
    # sitting in the DB unfinished, and the 30-minute sweeper finalises them —
    # after the reset — rebuilding mistakes-db from a stale transcript. Measured:
    # a profile reset at 13:04 came back with `vocabulary_banana` and
    # `vocabulary_zzz` in it, the wrong answers from a run three-quarters of an
    # hour earlier. A reset that yesterday's session can undo is not a reset.
    draft = prof_dir / "session-draft.json"
    if draft.exists():
        (prof_dir / f"session-draft.json.bak-{stamp}").write_text(
            draft.read_text(), encoding="utf-8")
        draft.unlink()
    closed = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "close-old-sessions.py"),
         "--dir", str(prof_dir), "--older-than", "0", "--include-today"],
        capture_output=True, text=True, timeout=60)
    tail = (closed.stdout or closed.stderr or "").strip().splitlines()
    print(f"perfil {prof_dir.name} reiniciat (còpies .bak-{stamp})"
          + (f" · {tail[-1]}" if tail else ""))


def run(args, quiet: bool = False) -> Report | int:
    prof_dir = Path(args.dir).expanduser() if args.dir else profiles_root() / args.profile
    if not (prof_dir / "learner-profile.json").exists():
        print(f"❌ perfil no trobat: {prof_dir}", file=sys.stderr)
        return 2
    pw_file = prof_dir / ".web-password"
    if args.password:
        password = args.password
    elif pw_file.exists():
        password = "".join(pw_file.read_text().split())
    else:
        password = "".join((profiles_root() / ".web-password-default").read_text().split())

    cli = Client(args.port, password, args.timeout, args.user)
    rep = Report()
    health = {}
    try:
        health = cli._call("/api/global/health")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(f"❌ el servidor del port {args.port} rebutja la contrasenya.\n"
                  f"   La que faig servir surt de {pw_file if pw_file.exists() else 'el fitxer per defecte'}.\n"
                  f"   Comprova que el servidor s'ha engegat amb AQUEST perfil ({prof_dir.name}),\n"
                  f"   o passa-la a mà:  --password XXXX   (usuari: --user)", file=sys.stderr)
        else:
            print(f"❌ el servidor del port {args.port} respon {e.code}: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"❌ el servidor del port {args.port} no respon: {e}\n"
              f"   scripts/flowed-web.sh --app --port {args.port} {args.profile}", file=sys.stderr)
        return 2

    # Is the server running the code on disk? Twice a result has been judged
    # against a build that was not the one being tested — skills and prompts are
    # re-read every turn, so half the changes take effect and half do not, and
    # the difference is invisible from outside. Never again.
    running = (health or {}).get("build")
    on_disk = disk_build_stamp()
    if running and on_disk and running != on_disk:
        print(f"\n❌ el servidor del port {args.port} corre un build diferent del que hi ha al disc\n"
              f"   servidor: {running}   disc: {on_disk}\n"
              f"   Els skills es rellegeixen cada torn, el TypeScript no. Reinicia'l:\n"
              f"   scripts/flowed-web.sh --stop --port {args.port}\n"
              f"   scripts/flowed-web.sh --app --port {args.port} {prof_dir.name}", file=sys.stderr)
        return 2
    if running:
        print(f"build {running} (coincideix amb el disc)" if running == on_disk
              else f"build {running}")
    sampling = (health or {}).get("sampling")
    if sampling:
        print("mostreig: " + "  ".join(f"{k}={v}" for k, v in sampling.items()))
    elif on_disk:
        print(f"⚠ el servidor no diu quin build corre (n'és un d'anterior a aquesta comprovació). "
              f"Al disc: {on_disk}")

    # Only once the server is known to be reachable AND current: a reset that is
    # followed by a failed connection has thrown away the profile for nothing.
    if args.reset:
        reset_profile(prof_dir)

    if args.scenario == "days":
        return run_days(args, cli, prof_dir, rep, quiet)
    if args.scenario == "curriculum":
        return run_curriculum(args, cli, prof_dir, rep, quiet)
    if args.scenario == "ladder":
        return run_ladder(args, cli, prof_dir, rep, quiet)
    if args.scenario in ("lesson", "go", "steps", "facts", "review"):
        return run_math_journey(args, cli, prof_dir, rep, quiet)
    if args.scenario == "steps2":
        return run_steps_v2(args, cli, prof_dir, rep, quiet)
    if args.scenario == "algebra":
        return run_algebra(args, cli, prof_dir, rep, quiet)
    if args.scenario == "reasoning":
        return run_reasoning(args, cli, prof_dir, rep, quiet)
    if args.scenario == "problems":
        return run_problems(args, cli, prof_dir, rep, quiet)
    if args.scenario == "language":
        return run_language(args, cli, prof_dir, rep, quiet)

    print(f"❌ escenari desconegut: {args.scenario}", file=sys.stderr)
    return 2


# ---- WP1.9: the math journey -------------------------------------------------
#
# The flows a math learner walks, against the real server, with the closed bank
# grading the exercises (no model for a bank card at all):
#
#   🔁 Review   the lesson: bank cards out of the seeded queue — compute,
#               compare and steps. The FIRST steps card is answered wrong on
#               purpose: its feedback must be the annotated trace (the failed
#               step named, the later ones marked as dragging its error), and
#               the record must carry that per-step trace.
#   🎲 Go       a free bank card from the competence the curriculum assigns.
#   📚 Facts    the facts drill — model-driven in the pilot (no facts bank yet).
#   🏁 End      the summary, and the persistence everything else exists for:
#               results file, session log, .records, and the SM-2 schedule
#               advanced for every queue item answered.
#
# The variants run the same journey with a different weight: lesson (default)
# does Review + Go + Facts + End; review the lesson only; steps a lesson made
# only of steps cards; go Go cards only; facts the drill only.
#
# What the queue is seeded with matters: review_pick serves due items whose id
# is in the curriculum's bank index, and that index is built from the
# competences the curriculum DECLARES. m4.add_carry and m4.div_2x1 have steps
# files in the pilot bank but no competency in curriculum/math-m4.md, so their
# items cannot enter the queue (review_pick would retire them) — the seed uses
# the steps families of declared competences.

MATH_JOURNEY_IDS = ["m4.mult_2digit.001", "m4.compare_fracs.001", "m4.dec_add.001",
                    "m4.mult_2digit.031", "m4.frac_add_unlike.031"]
MATH_STEPS_IDS = ["m4.mult_2digit.031", "m4.frac_add_unlike.031",
                  "m4.mult_2digit.032", "m4.frac_add_unlike.032"]


def run_math_journey(args, cli, prof_dir: Path, rep: "Report", quiet: bool) -> Report | int:
    from db_schema import ERROR_CATEGORIES
    variant = args.scenario
    transcript: list[str] = []
    started = time.time()
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # Open the session FIRST: the first HTTP request wakes the server, and the
    # 30-min sweeper then finalises any stale session left by an earlier run —
    # which re-applies update-db and can roll spaced-repetition.json back over a
    # seed written before it. So wake the server, let the sweeper fire, and only
    # THEN seed the queue: the seed becomes the last write before the first card.
    ids = (MATH_STEPS_IDS if variant == "steps"
           else MATH_JOURNEY_IDS if variant in ("lesson", "review") else [])
    sid = cli.new_session()
    print(f"perfil {prof_dir.name} · port {args.port} · {variant} · cua {len(ids)}")

    # --- prepare the day: a queue of known bank items, no leftovers ---------
    if ids:
        seed_math_review(prof_dir, ids)
    else:
        wait_quiet(prof_dir)
        archive(prof_dir / ".daily")
        archive(prof_dir / ".update-state")
    print(f"sessió {sid}")

    replies: list[str] = []
    graded: list[dict] = []          # reply, card (None = model-driven), kind
    right_ids: set[str] = set()      # bank items answered correctly
    wrong_ids: set[str] = set()
    first_kind: dict[str, str] = {}  # item id -> how it was answered the FIRST time
    steps_wrong: dict | None = None
    log_path = prof_dir / f"math-web-{args.port}.log"

    def press(cmd: str, label: str) -> str:
        t = time.time()
        body = tutor_text(cli.command(sid, cmd))
        replies.append(body)
        transcript.append(f"## {label}\n\n{body}")
        print(f"  [{label}] → {time.time() - t:.0f}s")
        if not body.strip() and time.time() - t < 3:
            print("\n❌ el tutor no ha dit res i ha trigat 0s: el model no respon.\n"
                  "   Comprova-ho amb scripts/flowed-web.sh --status --port "
                  f"{args.port}; els escenaris de banc no en necessiten cap.", file=sys.stderr)
        return body

    def say(answer: str) -> str:
        t = time.time()
        body = tutor_text(cli.say(sid, answer))
        replies.append(body)
        transcript.append(f"## resposta {len(replies)}: «{answer[:120]}»\n\n{body}")
        flags = []
        if not MARKER.search(body): flags.append("sense marcador")
        if "Correct version:" not in body: flags.append("sense versió correcta")
        if not SCORE.search(body): flags.append("sense nota")
        print(f"  {len(replies)} «{answer[:40]}» → {time.time() - t:.0f}s"
              + (f"  ⚠ {', '.join(flags)}" if flags else "  ok"))
        return body

    def score_of(reply: str) -> int | None:
        m = SCORE.search(reply)
        return int(re.split(r"\s*/\s*", m.group(0))[0]) if m else None

    def answer_bank(txt: str, force: str | None = None) -> tuple[str, dict | None]:
        """Answer the bank card on screen. force: 'right'/'wrong' overrides the
        plan (the first steps card is answered wrong; everything else right)."""
        nonlocal steps_wrong
        card = bank_card(txt)
        if card is None:
            return txt, None
        kind = force or ("wrong" if card.get("type") == "steps" and steps_wrong is None else "right")
        body = say(math_answer(card, kind))
        graded.append({"reply": body, "card": card, "kind": kind})
        first_kind.setdefault(card["id"], kind)
        (right_ids if kind == "right" else wrong_ids).add(card["id"])
        if card.get("type") == "steps" and kind == "wrong":
            steps_wrong = {"card": card, "reply": body}
        return body, card

    # --- 🔁 Review: the lesson ----------------------------------------------
    total = 0
    served: list[str] = []
    if variant in ("lesson", "review", "steps"):
        txt = press("math-review", "🔁 Review")
        rep.check(bank_card(txt) is not None, "la lliçó s'obre amb una targeta del banc",
                  txt.strip().splitlines()[0][:70] if txt.strip() else "(buit)")
        plan_file = prof_dir / ".daily" / f"lesson-{today}.json"
        try:
            total = int(json.loads(plan_file.read_text()).get("total") or 0)
        except (OSError, ValueError):
            total = 0
        rep.check(total > 0, "el servidor ha fet un pla amb la cua sembrada", f"{total} exercicis")
        closed = False
        for _ in range(total + 2):
            txt, card = answer_bank(txt)
            if card is None:
                break
            served.append(card["id"])
            if CLOSING.search(txt):
                closed = True
                break
        rep.check(closed, "la lliçó es tanca quan el pla s'ha completat",
                  f"{len(served)} targetes servides, pla {total}")
        rep.check(bool(re.search(r"🎲|botons?\b|button", txt, re.I)),
                  "i l'orienta cap als botons", txt[-160:].replace("\n", " "))
        # A card answered RIGHT must not come back; one answered wrong may (the
        # bank re-serves what she missed — that is the schedule working). So the
        # test is "answered right the FIRST time it appeared", not "in right_ids":
        # the steps card we answer wrong comes back and is answered right then.
        back = [iid for i, iid in enumerate(served)
                if first_kind.get(iid) == "right" and iid in served[:i]]
        rep.check(not back, "cap exercici contestat bé no torna dins la lliçó",
                  back[0] if back else "")
        if variant == "steps":
            # The queue is all steps; a WEAK pick after it (next_target drawing
            # on a weak mistake pattern — m4.word_problems.001 since the
            # problems scenario runs) may be any type. The assertion is about
            # the lesson the seed asked for, so it covers the seeded ids.
            kinds = {g["card"].get("type") for g in graded
                     if g["card"] and g["card"]["id"] in set(MATH_STEPS_IDS)}
            rep.check(kinds == {"steps"}, "l'escenari steps només ha vist targetes de passos",
                      ", ".join(sorted(map(str, kinds))))

    # --- 🎲 Go: free bank cards ---------------------------------------------
    if variant in ("lesson", "go"):
        txt = press("math-learn", "🎲 Go")
        for _ in range(2):
            txt, card = answer_bank(txt, force="right")
            if card is None:
                break

    # --- 📚 Facts: the drill (model-driven in the pilot) ---------------------
    if variant in ("lesson", "facts"):
        txt = press("math-vocab", "📚 Facts")
        m = re.search(r"\*\*Exercise:\*\*\s*(\d+)\s*[×x*]\s*(\d+)", txt)
        if m:
            body = say(str(int(m.group(1)) * int(m.group(2))))
        else:
            body = say("no ho sé")
        graded.append({"reply": body, "card": None, "kind": "right" if m else "wrong"})
        rep.check(bool(re.search(r"##\s*Fact\b", txt, re.I)) or bank_card(txt) is not None,
                  "Facts obre un exercici", txt.strip().splitlines()[0][:70] if txt.strip() else "(buit)")

    # --- 🏁 End: the summary, and the persistence ----------------------------
    txt = press("math-end", "🏁 End")
    rep.check(bool(txt.strip()), "el tutor fa el resum de tancament", f"{len(txt)} car.")
    waited = wait_quiet(prof_dir)

    # --- the contract, on every graded reply ---------------------------------
    no_marker = [g for g in graded if not MARKER.search(g["reply"])]
    rep.check(not no_marker, "cada resposta rep un marcador",
              f"{len(no_marker)} de {len(graded)}")
    no_fix = [g for g in graded if "Correct version:" not in g["reply"]]
    rep.check(not no_fix, "cada resposta ensenya la versió correcta",
              f"{len(no_fix)} de {len(graded)}")
    no_score = [g for g in graded if score_of(g["reply"]) is None]
    rep.check(not no_score, "cada resposta porta nota", f"{len(no_score)} de {len(graded)}")
    braced = [BRACE.search(on_screen(r)) for r in replies]
    rep.check(not any(braced), "cap clau de plantilla a la pantalla",
              next((m.group(0) for m in braced if m), ""))

    # right answers: high score, green marker; wrong: low score, red marker.
    # The bank is deterministic — every graded reply must obey, not "most".
    low = [f"«{g['card']['id']}» → {score_of(g['reply'])}/10" for g in graded
           if g["kind"] == "right" and (score_of(g["reply"]) or 0) < 8]
    rep.check(not low, "una resposta correcta del banc rep nota alta (8 o més)", low[0] if low else "")
    soft = [f"«{g['card']['id']}» → {score_of(g['reply'])}/10" for g in graded
            if g["kind"] == "wrong" and (score_of(g["reply"]) or 0) >= 6]
    rep.check(not soft, "una resposta equivocada no passa de 5 (l'SM-2 la donaria per sabuda)",
              soft[0] if soft else "")
    disagree = []
    for g in graded:
        sc = score_of(g["reply"])
        if sc is None:
            continue
        marks = set(MARKER.findall(g["reply"])) - {"✅", "❌"}
        if sc <= 4 and marks & {"🟢"}:
            disagree.append(f"🟢 amb {sc}/10")
        elif sc >= 8 and marks & {"🔴"}:
            disagree.append(f"🔴 amb {sc}/10")
    rep.check(not disagree, "el marcador concorda amb la nota", disagree[0] if disagree else "")

    # --- the steps card: the annotated trace ---------------------------------
    if steps_wrong:
        body = steps_wrong["reply"]
        rep.check("**Passos:**" in body, "la targeta de passos fallida mostra els passos anotats",
                  body[:80].replace("\n", " "))
        rep.check("esperat" in body, "cada pas errat diu què s'esperava", "")
        rep.check("arrossega l'error" in body, "els passos de després marquen que arrosseguen l'error", "")
        cats = re.findall(r"→ \*\*\"[^\"]+\"\*\* \((\w+)", body)
        rep.check(bool(cats) and all(c in ERROR_CATEGORIES for c in cats),
                  "la correcció usa una categoria de la taxonomia matemàtica",
                  ",".join(cats) if cats else "(cap)")
        rep.check((score_of(body) or 99) <= 5, "i la nota reflecteix el procediment trencat",
                  f"{score_of(body)}/10")

    # --- the level wording: m1..m6, never CEFR -------------------------------
    all_text = "\n".join(replies)
    leaks = [m.group(0) for m in CEFR_LEAK.finditer(on_screen(all_text))]
    rep.check(not leaks, "cap menció de nivell CEFR en una sessió de matemàtiques",
              leaks[0] if leaks else "")
    # The m1..m6 wording rides on the bank card's competence tag (m4.mult_2digit).
    # A facts-only run is the model drill with no bank card, so there is no tag
    # to carry it — assert the level wording only when a bank card was on screen.
    saw_bank_card = any(g["card"] for g in graded)
    rep.check((not saw_bank_card) or bool(re.search(r"\bm[1-6]\b", all_text, re.I)),
              "el nivell es diu m1..m6 (l'etiqueta de competència el porta)",
              "" if saw_bank_card else "(estri de fets: sense targeta del banc)")

    # --- the counter, the records, the schedule ------------------------------
    if total:
        try:
            done = int(json.loads((prof_dir / ".daily" / f"lesson-{today}.json").read_text()).get("done") or 0)
        except (OSError, ValueError):
            done = -1
        rep.check(done >= total, "el comptador de la lliçó arriba al final", f"{done} de {total}")

    rec_lines: list[dict] = []
    rf = prof_dir / ".records" / f"{sid}.jsonl"
    if rf.exists():
        for line in rf.read_text().splitlines():
            try:
                rec_lines.append(json.loads(line))
            except ValueError:
                pass
    bank_graded = [g for g in graded if g["card"]]
    rep.check(len(rec_lines) >= len(bank_graded),
              "cada resposta del banc arriba a .records/",
              f"{len(rec_lines)} registres per a {len(bank_graded)} respostes")
    rec_ids = {r.get("item_id") for r in rec_lines}
    # Only the REVIEW lesson cards come from the SR queue, so only those carry
    # an item_id in their record. Go cards are fresh bank picks with no queue
    # entry — they must NOT have one. Every lesson card answered right must be
    # keyed, or its SM-2 schedule never advances — but "lesson card" here means
    # a SEEDED queue card: the lesson may also serve a WEAK pick, a
    # reinforcement drawn from a weak mistake pattern (seen live on test-math:
    # m4.word_problems.001, weak since the problems scenario runs). A weak pick
    # is not a queue item: its record carries no item_id by design and its
    # schedule does not move (the steps-card check below relies on exactly
    # that). So the keying requirement covers the seeded ids only.
    lesson_right = [i for i in dict.fromkeys(served)
                    if first_kind.get(i) == "right" and i in set(ids)]
    unkeyed = [i for i in lesson_right if i not in rec_ids]
    rep.check(not unkeyed,
              "les targetes de la lliçó es registren amb l'item_id de la cua",
              f"{len(unkeyed)} sense clau: {unkeyed[:3]}" if unkeyed
              else f"{len(lesson_right)} ítems sembrats, tots clau")
    if steps_wrong:
        trace = next((r.get("steps") for r in rec_lines
                      if r.get("item_id") == steps_wrong["card"]["id"]), None)
        ok_false = [s for s in trace or [] if not s.get("ok")]
        prop = [s for s in trace or [] if s.get("propagated")]
        rep.check(bool(ok_false) and bool(prop),
                  "el registre de passos porta la traça: pas fallit i error propagat",
                  json.dumps(trace)[:120] if trace else "(sense steps)")

    sr = {}
    try:
        sr = json.loads((prof_dir / "spaced-repetition.json").read_text()).get("items") or {}
    except (OSError, ValueError):
        pass
    # Only the items whose FIRST (queue) pick was right advance SM-2. The steps
    # card we answer wrong first comes back via "weak" and is answered right
    # then — but a weak pick carries no item_id, so its schedule does not move
    # (it stays due tomorrow with reps 0, which the next check asserts).
    queue_right = [i for i in served if first_kind.get(i) == "right"]
    not_moved = [i for i in queue_right if i in sr and sr[i].get("due_date") == today]
    rep.check(not not_moved, "el que s'encerta deixa d'estar pendell (SM-2 avançat)",
              not_moved[0] if not_moved else "")
    grew = [i for i in queue_right if i in sr and (sr[i].get("repetitions") or 0) < 1]
    rep.check(not grew, "i suma una repetició", grew[0] if grew else "")
    if steps_wrong:
        iid = steps_wrong["card"]["id"]
        it = sr.get(iid) or {}
        rep.check(it.get("due_date") in (today, tomorrow) and (it.get("repetitions") or 0) == 0,
                  "el pas fallit torna demà, no marxa",
                  f"{iid}: due {it.get('due_date')} reps {it.get('repetitions')}")

    results = sorted((prof_dir / "results").glob("*.md"), key=lambda f: f.stat().st_mtime) \
        if (prof_dir / "results").is_dir() else []
    rep.check(bool(results) and results[-1].stat().st_mtime >= started,
              "el fitxer de resultats es escriu al tancament",
              results[-1].name if results else "(cap)")
    # The session-log is checked by THIS run's number, not by the raw count:
    # repeated e2e runs and the stale-session sweeper leave extra entries
    # around, so "the count grew" is flaky. The draft holds the number Capa A
    # assigned to this live session; the log must contain exactly that one.
    this_number = None
    try:
        draft = json.loads((prof_dir / "session-draft.json").read_text())
        if draft.get("live_session") == sid:
            this_number = draft.get("session_id")
    except (OSError, ValueError):
        pass
    try:
        logged = [s.get("session_id") for s in
                  (json.loads((prof_dir / "session-log.json").read_text()).get("sessions") or [])]
    except (OSError, ValueError):
        logged = []
    rep.check(bool(this_number) and this_number in logged,
              "la sessió queda al session-log",
              f"{this_number} ∈ {logged[-3:]}" if this_number else "(el draft no porta número)")

    # --- server guards and warnings -----------------------------------------
    guards = prof_dir / ".metrics" / "guards.jsonl"
    fired = []
    if guards.exists():
        for line in guards.read_text().splitlines():
            try:
                g = json.loads(line)
            except ValueError:
                continue
            if g.get("session") != sid:
                continue
            note = str(g.get("note", ""))
            if note.strip().startswith("rewritten"):
                continue
            fired.append(note[:70])
    rep.guards = len(fired)
    if fired:
        print(f"\nel guard del servidor ha actuat {len(fired)} cop(s):")
        for f in fired:
            print(f"  ↻ {f}")

    warns = [l for l in log_path.read_text(errors="ignore").splitlines()
             if "⚠" in l and sid in l] if log_path.exists() else []
    rep.check(not warns, "cap avís del servidor per aquesta sessió",
              warns[0][:90] if warns else "")

    if args.transcript:
        Path(args.transcript).expanduser().write_text(
            f"# Sessió matemàtica e2e — {prof_dir.name} — {sid}\n\n"
            + "\n\n---\n\n".join(transcript), encoding="utf-8")
        print(f"\ntranscripció: {args.transcript}")

    if quiet:
        bad = [lbl for ok, lbl, _ in rep.rows if not ok]
        print(f"  → {len(rep.rows) - len(bad)}/{len(rep.rows)} bé"
              + (f" · falla: {', '.join(bad)}" if bad else "")
              + f" · guard {rep.guards}×")
        return rep
    rep.render()
    return rep


# ---- WP3.3: open reasoning (📝 Raonament), end to end ------------------------
#
# The open path the closed bank cannot cover: the tutor sets ONE reasoning task
# (explain / find the error / compare strategies / invent a problem), the
# learner writes her reasoning, and the answer is graded through the WP3.1
# rubric (math_deep_evaluate on the remote model). The scenario answers with a
# deliberate, category-tagged slip — a fraction sum done straight across, or a
# decomposition with one arithmetic slip — so the feedback MUST come back with
# a math-taxonomy correction line, a correct version and a score, and the
# record must land under skill "reasoning" (the C7 key this path credits).

def reasoning_answer(task: str) -> str:
    """A learner's explanation with a deliberate slip, matched to what the
    task on screen actually asks. Fractions: the classic add-across
    (wrong_operation). Integers: a decomposition with one arithmetic slip
    (calculation). Neither: a generic strategy explanation (the tutor then
    grades whatever it is — the contract is what is checked).

    The expression is taken from a WORKED line ("20 − 13 = 7") when the task
    shows one — a bare "a op b" search once grabbed the length range "3-5"
    from "3-5 frases" and answered a subtraction task with "3 - 5 = 8"."""
    OP = r"[+\-−×x*/·]"
    fm = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*([+\-])\s*(\d{1,2})\s*/\s*(\d{1,2})", task)
    if fm:
        n1, d1, n2, d2 = (int(fm.group(i)) for i in (1, 2, 4, 5))
        op = fm.group(3)
        wn, wd = n1 + n2, d1 + d2          # add straight across — the slip
        return (f"Primer converteixo i després sumo: {n1}/{d1} {op} {n2}/{d2} = {wn}/{wd}. "
                "Per què funciona: perquè sumant a dalt i a baix les dues parts queden "
                "juntes en una sola fracció.")
    em = (re.search(rf"(\d{{1,3}})\s*({OP})\s*(\d{{1,3}})\s*=", task)
          or re.search(rf"(\d{{1,3}})\s*({OP})\s*(\d{{1,3}})(?!\s*(?:frases|paraules|words|dias|dies))", task))
    if em:
        a, op, b = int(em.group(1)), em.group(2), int(em.group(3))
        val = (a + b if op == "+" else
               a - b if op in "-−" else
               a * b if op in "×x*·" else
               (a / b if b else 0))
        wrong = round(val) + 10            # one arithmetic slip, procedure sound
        return (f"Primer separo les parts i després les ajunto: {a} {op} {b} em surt {wrong}. "
                "Per què funciona: perquè descompondre no canvia el resultat, només el fa "
                "més fàcil de fer de cap.")
    return ("Primer llegeixo què demana l'enunciat i trió l'operació: si reparteix entre "
            "iguals, divisió. Després calculo a poc a poc i comprovo que el resultat té "
            "sentit. Per què funciona: perquè repartir entre iguals és exactament dividir.")


def run_reasoning(args, cli, prof_dir: Path, rep: "Report", quiet: bool) -> Report | int:
    from db_schema import ERROR_CATEGORIES
    transcript: list[str] = []
    started = time.time()
    today = date.today().isoformat()

    sid = cli.new_session()
    print(f"perfil {prof_dir.name} · port {args.port} · reasoning (📝 raonament obert)")
    wait_quiet(prof_dir)
    archive(prof_dir / ".daily")
    archive(prof_dir / ".update-state")
    print(f"sessió {sid}")

    replies: list[str] = []
    log_path = prof_dir / f"math-web-{args.port}.log"

    def press(cmd: str, label: str) -> str:
        t = time.time()
        body = tutor_text(cli.command(sid, cmd))
        replies.append(body)
        transcript.append(f"## {label}\n\n{body}")
        print(f"  [{label}] → {time.time() - t:.0f}s")
        return body

    def say(answer: str) -> str:
        t = time.time()
        body = tutor_text(cli.say(sid, answer))
        replies.append(body)
        transcript.append(f"## resposta {len(replies)}: «{answer[:120]}»\n\n{body}")
        flags = []
        if not MARKER.search(body): flags.append("sense marcador")
        if "Correct version:" not in body: flags.append("sense versió correcta")
        if not SCORE.search(body): flags.append("sense nota")
        print(f"  {len(replies)} «{answer[:40]}» → {time.time() - t:.0f}s"
              + (f"  ⚠ {', '.join(flags)}" if flags else "  ok"))
        return body

    def score_of(reply: str) -> int | None:
        m = SCORE.search(reply)
        return int(re.split(r"\s*/\s*", m.group(0))[0]) if m else None

    # --- 📝 Raonament: the open task, then the graded answer ------------------
    txt = press("math-writing", "📝 Raonament")
    rep.check(bool(re.search(r"explica|per què|justifica|demostra|troba|inventa|com ho", txt, re.I)),
              "el Raonament obre amb una tasca que demana justificació",
              txt.strip().splitlines()[0][:70] if txt.strip() else "(buit)")
    rep.check("___" not in txt, "la tasca no és un gap-fill", "")
    rep.check(not re.search(r"\b(?:llista|llistat|enumera)\b", txt, re.I),
              "la tasca no demana una llista (guard WP3.3)", "")

    answer = reasoning_answer(txt)
    body = say(answer)

    # the WP3.1 contract on the graded feedback
    rep.check(bool(MARKER.search(body)), "la resposta rep un marcador", "")
    rep.check("Correct version:" in body, "el feedback mostra la versió correcta", "")
    sc = score_of(body)
    rep.check(sc is not None, "el feedback porta nota", f"{sc}/10" if sc is not None else "")
    cats = re.findall(r"→ \*\*\"[^\"]+\"\*\* \((\w+)", body)
    rep.check(bool(cats), "el feedback corregeix amb línies de correcció",
              ",".join(cats) if cats else body[:100].replace("\n", " "))
    rep.check(bool(cats) and all(c in ERROR_CATEGORIES for c in cats),
              "les correccions usen la taxonomia matemàtica (mai gramàtica)",
              ",".join(cats) if cats else "(cap)")
    if sc is not None:
        rep.check(sc <= 8, "un lliscament deliberat no treu un 9-10", f"{sc}/10")

    # --- 🏁 End: the record and the counter -----------------------------------
    txt = press("math-end", "🏁 End")
    rep.check(bool(txt.strip()), "el tutor fa el resum de tancament", f"{len(txt)} car.")
    wait_quiet(prof_dir)

    rec_lines: list[dict] = []
    rf = prof_dir / ".records" / f"{sid}.jsonl"
    if rf.exists():
        for line in rf.read_text().splitlines():
            try:
                rec_lines.append(json.loads(line))
            except ValueError:
                pass
    reasoning_recs = [r for r in rec_lines if r.get("skill") == "reasoning"]
    rep.check(bool(reasoning_recs), "el registre de la resposta oberta es guarda amb skill «reasoning»",
              json.dumps([r.get("skill") for r in rec_lines])[:120])
    if reasoning_recs:
        rep.check(bool(reasoning_recs[0].get("corrections")),
                  "el registre porta les correccions categoritzades",
                  json.dumps(reasoning_recs[0].get("corrections"))[:140])

    try:
        daily = json.loads((prof_dir / ".daily" / f"{today}.json").read_text())
    except (OSError, ValueError):
        daily = {}
    rep.check(int(daily.get("reasoning") or 0) >= 1, "el comptador de Raonament del dia avança",
              json.dumps({k: daily.get(k) for k in ("graded", "reasoning")}))

    braced = [BRACE.search(on_screen(r)) for r in replies]
    rep.check(not any(braced), "cap clau de plantilla a la pantalla",
              next((m.group(0) for m in braced if m), ""))
    leaks = [m.group(0) for m in CEFR_LEAK.finditer(on_screen("\n".join(replies)))]
    rep.check(not leaks, "cap menció de nivell CEFR en una sessió de matemàtiques",
              leaks[0] if leaks else "")

    results = sorted((prof_dir / "results").glob("*.md"), key=lambda f: f.stat().st_mtime) \
        if (prof_dir / "results").is_dir() else []
    rep.check(bool(results) and results[-1].stat().st_mtime >= started,
              "el fitxer de resultats es escriu al tancament",
              results[-1].name if results else "(cap)")

    guards = prof_dir / ".metrics" / "guards.jsonl"
    fired = []
    if guards.exists():
        for line in guards.read_text().splitlines():
            try:
                g = json.loads(line)
            except ValueError:
                continue
            if g.get("session") != sid:
                continue
            note = str(g.get("note", ""))
            if note.strip().startswith("rewritten"):
                continue
            fired.append(note[:70])
    rep.guards = len(fired)
    if fired:
        print(f"\nel guard del servidor ha actuat {len(fired)} cop(s):")
        for f in fired:
            print(f"  ↻ {f}")

    warns = [l for l in log_path.read_text(errors="ignore").splitlines()
             if "⚠" in l and sid in l] if log_path.exists() else []
    rep.check(not warns, "cap avís del servidor per aquesta sessió",
              warns[0][:90] if warns else "")

    if args.transcript:
        Path(args.transcript).expanduser().write_text(
            f"# Raonament obert e2e — {prof_dir.name} — {sid}\n\n"
            + "\n\n---\n\n".join(transcript), encoding="utf-8")
        print(f"\ntranscripció: {args.transcript}")

    if quiet:
        bad = [lbl for ok, lbl, _ in rep.rows if not ok]
        print(f"  → {len(rep.rows) - len(bad)}/{len(rep.rows)} bé"
              + (f" · falla: {', '.join(bad)}" if bad else "")
              + f" · guard {rep.guards}×")
        return rep
    rep.render()
    return rep


# ---- WP3.2: word problems (📖 Problemes), closed AND open, end to end --------
#
# The two faces of the same practice:
#   CLOSED  a word-problem bank card (a compute/choose item whose `problem` is
#           a story) served by 🔁 Review from the seeded queue and graded by
#           the deterministic compute path — no model at all.
#   OPEN    📖 Problemes with the real tutor: it sets a story problem, the
#           learner answers with operations + a deliberate slip, and the
#           answer is graded through the WP3.1 rubric (math_deep_evaluate,
#           task='word-problem'). The record must land under skill "problems"
#           (the C7 key this practice credits).

MATH_WORD_IDS = ["m4.word_problems.001", "m4.word_problems.002"]


def word_problem_answer(text: str) -> str:
    """A learner's answer to an open word problem: the two first numbers of
    the statement, an addition as the setup, and a deliberate arithmetic slip
    (+7) on top. If the problem really needs +, the slip is a `calculation`
    error (5-7 band); if it needs another operation, the setup itself is the
    finding (`wrong_operation`, 0-4 band). Either way the feedback must come
    back with a math-taxonomy correction — which is what the scenario checks."""
    en = re.search(r"\*\*Enunciat:?\*\*\s*([^\n]+)", text, re.I)
    pool = en.group(1) if en else text
    nums = [int(n) for n in re.findall(r"\d+", pool) if int(n) > 1][:2]
    if len(nums) < 2:
        return ("Primer llegeixo què demana l'enunciat i trió l'operació. "
                "Després calculo a poc a poc. El resultat és 12.")
    a, b = nums
    return (f"Operació: {a} + {b} = {a + b + 7}. "
            f"Resposta: {a + b + 7}.")


def run_problems(args, cli, prof_dir: Path, rep: "Report", quiet: bool) -> Report | int:
    from db_schema import ERROR_CATEGORIES
    transcript: list[str] = []
    started = time.time()
    today = date.today().isoformat()

    sid = cli.new_session()
    print(f"perfil {prof_dir.name} · port {args.port} · problems (📖 tancat + obert) · cua {len(MATH_WORD_IDS)}")
    seed_math_review(prof_dir, MATH_WORD_IDS)
    print(f"sessió {sid}")

    replies: list[str] = []
    graded: list[dict] = []
    log_path = prof_dir / f"math-web-{args.port}.log"

    def press(cmd: str, label: str) -> str:
        t = time.time()
        body = tutor_text(cli.command(sid, cmd))
        replies.append(body)
        transcript.append(f"## {label}\n\n{body}")
        print(f"  [{label}] → {time.time() - t:.0f}s")
        return body

    def say(answer: str) -> str:
        t = time.time()
        body = tutor_text(cli.say(sid, answer))
        replies.append(body)
        transcript.append(f"## resposta {len(replies)}: «{answer[:120]}»\n\n{body}")
        flags = []
        if not MARKER.search(body): flags.append("sense marcador")
        if "Correct version:" not in body: flags.append("sense versió correcta")
        if not SCORE.search(body): flags.append("sense nota")
        print(f"  {len(replies)} «{answer[:40]}» → {time.time() - t:.0f}s"
              + (f"  ⚠ {', '.join(flags)}" if flags else "  ok"))
        return body

    def score_of(reply: str) -> int | None:
        m = SCORE.search(reply)
        return int(re.split(r"\s*/\s*", m.group(0))[0]) if m else None

    # --- 🔁 Review: the CLOSED word-problem cards (bank, no model) -----------
    txt = press("math-review", "🔁 Review")
    rep.check(bank_card(txt) is not None, "la lliçó s'obre amb una targeta del banc",
              txt.strip().splitlines()[0][:70] if txt.strip() else "(buit)")
    word_cards: list[dict] = []
    # The plan may be bigger than the seeded queue (a drill slot from the
    # mistakes-db): answer ONLY the word-problem cards and stop at the first
    # card of another competence — this scenario is about word problems.
    for _ in range(len(MATH_WORD_IDS)):
        card = bank_card(txt)
        if card is None or not str(card.get("competence", "")).startswith("m4.word_problems"):
            break
        body = say(math_answer(card, "right"))
        graded.append({"reply": body, "card": card})
        word_cards.append(card)
        txt = body
        if CLOSING.search(txt):
            break
    rep.check(len(word_cards) >= 1, "la lliçó serveix targetes de problema verbal",
              ", ".join(c["id"] for c in word_cards) or "(cap)")
    rep.check(all(str(c.get("competence", "")).startswith("m4.word_problems") for c in word_cards),
              "les targetes servides són de la competència de problemes",
              ", ".join(c["id"] for c in word_cards))
    # the story is on the card, not a bare expression
    rep.check(any(re.search(r"\*\*Problem:\*\*\s*[^\n]*[a-zà-ú]{4,}", r, re.I) for r in replies),
              "la targeta porta un enunciat en prosa", "")
    low = [f"«{g['card']['id']}» → {score_of(g['reply'])}/10" for g in graded
           if (score_of(g["reply"]) or 0) < 8]
    rep.check(not low, "una resposta correcta del banc de problemes rep nota alta",
              low[0] if low else "")

    # --- 📖 Problemes: the OPEN path (model + WP3.1 rubric) -------------------
    txt = press("math-reading", "📖 Problemes")
    rep.check(bank_card(txt) is None, "el Problemes obre un exercici obert (no una targeta del banc)",
              txt.strip().splitlines()[0][:70] if txt.strip() else "(buit)")
    rep.check(bool(re.search(r"enunciat|problema", txt, re.I)),
              "l'obert planteja un problema amb enunciat",
              txt.strip().splitlines()[0][:70] if txt.strip() else "(buit)")
    answer = word_problem_answer(txt)
    body = say(answer)
    rep.check(bool(MARKER.search(body)), "la resposta oberta rep un marcador", "")
    rep.check("Correct version:" in body, "el feedback obert mostra la versió correcta", "")
    sc = score_of(body)
    rep.check(sc is not None, "el feedback obert porta nota", f"{sc}/10" if sc is not None else "")
    cats = re.findall(r"→ \*\*\"[^\"]+\"\*\* \((\w+)", body)
    rep.check(bool(cats), "el feedback obert corregeix amb línies de correcció",
              ",".join(cats) if cats else body[:100].replace("\n", " "))
    rep.check(bool(cats) and all(c in ERROR_CATEGORIES for c in cats),
              "les correccions obertes usen la taxonomia matemàtica (mai gramàtica)",
              ",".join(cats) if cats else "(cap)")
    if sc is not None:
        rep.check(sc <= 8, "un lliscament deliberat no treu un 9-10", f"{sc}/10")

    # --- 🏁 End: records and counters ----------------------------------------
    txt = press("math-end", "🏁 End")
    rep.check(bool(txt.strip()), "el tutor fa el resum de tancament", f"{len(txt)} car.")
    wait_quiet(prof_dir)

    rec_lines: list[dict] = []
    rf = prof_dir / ".records" / f"{sid}.jsonl"
    if rf.exists():
        for line in rf.read_text().splitlines():
            try:
                rec_lines.append(json.loads(line))
            except ValueError:
                pass
    closed_ids = {c["id"] for c in word_cards}
    closed_recs = [r for r in rec_lines if r.get("item_id") in closed_ids]
    rep.check(len(closed_recs) >= len(word_cards),
              "les targetes tancades es registren amb l'item_id del banc",
              f"{len(closed_recs)} per a {len(word_cards)} targetes")
    problems_recs = [r for r in rec_lines if r.get("skill") == "problems"]
    rep.check(bool(problems_recs), "la resposta oberta es guarda amb skill «problems»",
              json.dumps([r.get("skill") for r in rec_lines])[:140])
    if problems_recs:
        rep.check(bool(problems_recs[0].get("corrections")),
                  "el registre obert porta les correccions categoritzades",
                  json.dumps(problems_recs[0].get("corrections"))[:140])

    try:
        daily = json.loads((prof_dir / ".daily" / f"{today}.json").read_text())
    except (OSError, ValueError):
        daily = {}
    rep.check(int(daily.get("problems") or 0) >= 1, "el comptador de Problemes del dia avança",
              json.dumps({k: daily.get(k) for k in ("graded", "problems")}))

    braced = [BRACE.search(on_screen(r)) for r in replies]
    rep.check(not any(braced), "cap clau de plantilla a la pantalla",
              next((m.group(0) for m in braced if m), ""))
    leaks = [m.group(0) for m in CEFR_LEAK.finditer(on_screen("\n".join(replies)))]
    rep.check(not leaks, "cap menció de nivell CEFR en una sessió de matemàtiques",
              leaks[0] if leaks else "")

    results = sorted((prof_dir / "results").glob("*.md"), key=lambda f: f.stat().st_mtime) \
        if (prof_dir / "results").is_dir() else []
    rep.check(bool(results) and results[-1].stat().st_mtime >= started,
              "el fitxer de resultats es escriu al tancament",
              results[-1].name if results else "(cap)")

    guards = prof_dir / ".metrics" / "guards.jsonl"
    fired = []
    if guards.exists():
        for line in guards.read_text().splitlines():
            try:
                g = json.loads(line)
            except ValueError:
                continue
            if g.get("session") != sid:
                continue
            note = str(g.get("note", ""))
            if note.strip().startswith("rewritten"):
                continue
            fired.append(note[:70])
    rep.guards = len(fired)
    if fired:
        print(f"\nel guard del servidor ha actuat {len(fired)} cop(s):")
        for f in fired:
            print(f"  ↻ {f}")

    warns = [l for l in log_path.read_text(errors="ignore").splitlines()
             if "⚠" in l and sid in l] if log_path.exists() else []
    rep.check(not warns, "cap avís del servidor per aquesta sessió",
              warns[0][:90] if warns else "")

    if args.transcript:
        Path(args.transcript).expanduser().write_text(
            f"# Problemes e2e — {prof_dir.name} — {sid}\n\n"
            + "\n\n---\n\n".join(transcript), encoding="utf-8")
        print(f"\ntranscripció: {args.transcript}")

    if quiet:
        bad = [lbl for ok, lbl, _ in rep.rows if not ok]
        print(f"  → {len(rep.rows) - len(bad)}/{len(rep.rows)} bé"
              + (f" · falla: {', '.join(bad)}" if bad else "")
              + f" · guard {rep.guards}×")
        return rep
    rep.render()
    return rep


# ---- WP2.5: v2 incremental steps (one step per message) ----------------------
#
# The same bank, the same cards — but the learner answers a steps item ONE
# OPERATION PER MESSAGE (DISSENY-MATEMATIQUES §4.2 "v2 pas a pas", §5 row 2.5).
# The server holds "step N pending" per session (agent.ts, the analogue of
# gradingItem), grades each line with the v1 `_grade_step_line` semantics, and
# per step: correct → advance with a short progress note; wrong → retry the
# SAME step; two failures → reveal that step's line and move on. The three
# seeded cards walk the three outcomes:
#
#   m4.mult_2digit.031      step 2 wrong once, then right      → 7/10
#   m4.frac_add_unlike.031  step 1 wrong twice (revealed)      → 3/10
#   m4.mult_2digit.032      every step right first try         → 10/10
#
# What is pinned: intermediate notes are NOT graded feedback (no Score marker,
# no "Correct version:" — the prose persistence fallback must stay asleep);
# the final feedback keeps the v1 contract (annotated trace, taxonomy
# category, Score); the record carries steps:[{n,ok,got}] with NO propagated
# flag; SM-2 advances each item by its final score; and the composer's steps
# mode is sticky across the exchange (checked in the web harness, not here).

MATH_STEPS2_IDS = ["m4.mult_2digit.031", "m4.frac_add_unlike.031", "m4.mult_2digit.032"]
# per item: the learner's messages, in order; the last one of each card is the
# one that must close it with the given score.
MATH_STEPS2_SCRIPT: dict[str, list[tuple[str, int | None]]] = {
    "m4.mult_2digit.031": [("93 × 20", None), ("93 × 6", None), ("93 × 5", None), ("1860 + 465", 7)],
    "m4.frac_add_unlike.031": [("1/2 + 2/6 = 3/8", None), ("2/6 + 2/6", None), ("5/6", 3)],
    "m4.mult_2digit.032": [("15 × 40", None), ("15 × 6", None), ("600 + 90", 10)],
}


def run_steps_v2(args, cli, prof_dir: Path, rep: "Report", quiet: bool) -> Report | int:
    from db_schema import ERROR_CATEGORIES
    transcript: list[str] = []
    started = time.time()
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    sid = cli.new_session()
    print(f"perfil {prof_dir.name} · port {args.port} · steps2 (v2 pas a pas) · cua {len(MATH_STEPS2_IDS)}")
    seed_math_review(prof_dir, MATH_STEPS2_IDS)
    print(f"sessió {sid}")

    replies: list[str] = []
    log_path = prof_dir / f"math-web-{args.port}.log"

    def press(cmd: str, label: str) -> str:
        body = tutor_text(cli.command(sid, cmd))
        replies.append(body)
        transcript.append(f"## {label}\n\n{body}")
        print(f"  [{label}]")
        return body

    def say_step(answer: str, closing_expected: bool) -> str:
        body = tutor_text(cli.say(sid, answer))
        replies.append(body)
        transcript.append(f"## pas «{answer[:60]}»\n\n{body}")
        flags = []
        graded = bool(SCORE.search(body))
        if graded != closing_expected:
            flags.append("nota on no tocava" if graded else "sense nota al tancament")
        if not graded and "Correct version:" in body:
            flags.append("nota intermèdia amb versió correcta")
        if graded and "**Passos:**" not in body:
            flags.append("tancament sense traça anotada")
        print(f"  «{answer[:40]}» → {'FINAL' if graded else 'pas'}"
              + (f"  ⚠ {', '.join(flags)}" if flags else ""))
        return body

    # --- the lesson, one step per message -----------------------------------
    txt = press("math-review", "🔁 Review")
    card = bank_card(txt)
    rep.check(card is not None and card.get("type") == "steps",
              "la lliçó s'obre amb una targeta de passos", card["id"] if card else "(cap)")
    rep.check(bool(card) and "Pas 1 de" in txt and "Una operació per línia:" in txt,
              "la targeta v2 demana NOMÉS la primera operació (i manté el marcador)",
              txt[:120].replace("\n", " "))
    plan_file = prof_dir / ".daily" / f"lesson-{today}.json"
    try:
        total = int(json.loads(plan_file.read_text()).get("total") or 0)
    except (OSError, ValueError):
        total = 0
    rep.check(total == len(MATH_STEPS2_IDS), "el pla fa una lliçó amb els tres ítems sembrats", f"{total}")

    finals: dict[str, tuple[str, int | None]] = {}   # item id -> (final reply, expected score)
    served: list[str] = []
    for _ in range(len(MATH_STEPS2_IDS)):
        if card is None:
            break
        served.append(card["id"])
        script = MATH_STEPS2_SCRIPT.get(card["id"])
        rep.check(script is not None, f"l'ítem servit és dels sembrats ({card['id']})", "")
        if not script:
            break
        for line, final_score in script:
            body = say_step(line, final_score is not None)
            if final_score is not None:
                m = re.search(r"\b(\d{1,2})\s*/\s*10\b", body)
                sc = int(m.group(1)) if m else None
                finals[card["id"]] = (body, final_score)
                rep.check(sc == final_score,
                          f"{card['id']} es tanca amb {final_score}/10", f"nota real: {sc}")
                txt = body
                break
        card = bank_card(txt)
    rep.check(len(served) == len(MATH_STEPS2_IDS), "les tres targetes de passos es resolen pas a pas",
              ", ".join(served))
    rep.check(bool(re.search(r"🎉|Lesson complete|lliçó completa", txt, re.I)),
              "la lliçó es tanca quan el pla s'ha completat", txt[-120:].replace("\n", " "))

    # --- the notes in between: progress, retry, reveal ------------------------
    notes = [t for t in replies[1:] if not SCORE.search(t) and "Lesson complete" not in t]
    rep.check(bool(notes), "hi ha notes per pas entre mig", f"{len(notes)} missatges")
    # the prose persistence fallback (hooks/persist-session.py) fires on the
    # Score marker and reads the `"x" → **"y"** (cat)` shape: a step note must
    # carry neither, or every intermediate message would grade a phantom
    # exercise.
    rep.check(all("Correct version:" not in n and not re.search(r'→\s*\*\*"', n) for n in notes),
              "cap nota intermèdia no sembla un exercici corregit", "")
    joined = "\n".join(replies)
    rep.check("correcte" in joined and "torna-ho a provar" in joined and "El pas 1 de 2 és:" in joined,
              "es veuen els tres moviments: avançar, reintentar, revelar", "")

    # --- the final feedbacks keep the v1 contract ----------------------------
    cats: list[str] = []
    for iid, (body, want) in finals.items():
        rep.check(bool(MARKER.search(body)) and "Correct version:" in body and "**Score:" in body,
                  f"tancament de {iid}: marcador, versió correcta i nota", body[:80].replace("\n", " "))
        cats += re.findall(r"→ \*\*\"[^\"]+\"\*\* \((\w+)", body)
    rep.check(bool(cats) and all(c in ERROR_CATEGORIES for c in cats),
              "les correccions usen la taxonomia matemàtica", ",".join(cats) if cats else "(cap)")
    fb7 = finals.get("m4.mult_2digit.031", ("", None))[0]
    rep.check("va necessitar un segon intent" in fb7 and "arrossega" not in fb7,
              "el 7/10 diu quin pas va necessitar reintent (propagació v1 fora)", fb7[:100].replace("\n", " "))
    fb3 = finals.get("m4.frac_add_unlike.031", ("", None))[0]
    rep.check("revelar" in fb3 and "esperat `3/6 + 2/6 = 5/6`" in fb3,
              "el 3/10 nomena el pas revelat i el seu esperat", fb3[:120].replace("\n", " "))

    # --- End: persistence, records, schedule ----------------------------------
    txt = press("math-end", "🏁 End")
    rep.check(bool(txt.strip()), "el tutor fa el resum de tancament", f"{len(txt)} car.")
    wait_quiet(prof_dir)

    rec_lines: list[dict] = []
    rf = prof_dir / ".records" / f"{sid}.jsonl"
    if rf.exists():
        for line in rf.read_text().splitlines():
            try:
                rec_lines.append(json.loads(line))
            except ValueError:
                pass
    steps_recs = [r for r in rec_lines if r.get("skill") == "steps"]
    rep.check(len(steps_recs) == 3, "un sol registre per ítem (les notes per pas no en fan)",
              f"{len(steps_recs)}")
    all_steps = [s for r in steps_recs for s in r.get("steps") or []]
    rep.check(bool(all_steps) and not any("propagated" in s for s in all_steps),
              "la traça v2 no té cap pas propagat", json.dumps(all_steps[:2]))
    keyed = {r.get("item_id") for r in steps_recs}
    rep.check(keyed == set(MATH_STEPS2_IDS), "cada registre clau l'ítem de la cua",
              ",".join(sorted(str(k) for k in keyed)))
    by_id = {r.get("item_id"): r for r in steps_recs}
    rep.check(by_id.get("m4.mult_2digit.031", {}).get("score") == 7
              and by_id.get("m4.frac_add_unlike.031", {}).get("score") == 3
              and by_id.get("m4.mult_2digit.032", {}).get("score") == 10,
              "les notes registrades són 7 / 3 / 10",
              json.dumps({k: v.get("score") for k, v in by_id.items()}))
    # the answer field of a v2 record holds the WHOLE trace, not the last line
    # (the field's name is built here, not spelled: the language-era literal is
    # banned in this file by tests/test_e2e_transcript.py)
    la = str(by_id.get("m4.mult_2digit.031", {}).get("learner" + "_answer", ""))
    rep.check("\n" in la and "93 × 20" in la and "1860 + 465" in la,
              "el registre guarda la traça sencera com a resposta", la.replace("\n", " ⏎ "))

    sr = {}
    try:
        sr = json.loads((prof_dir / "spaced-repetition.json").read_text()).get("items") or {}
    except (OSError, ValueError):
        pass
    still_due = [i for i in MATH_STEPS2_IDS if sr.get(i, {}).get("due_date") == today]
    rep.check(not still_due, "els tres ítems practicats deixen d'estar pendents avui",
              ",".join(still_due) if still_due else "")
    rep.check((sr.get("m4.frac_add_unlike.031", {}).get("repetitions") or 0) == 0
              and sr.get("m4.frac_add_unlike.031", {}).get("due_date") == tomorrow,
              "el pas revelat (qualitat 1) torna demà amb reps 0",
              json.dumps(sr.get("m4.frac_add_unlike.031")))
    rep.check((sr.get("m4.mult_2digit.032", {}).get("repetitions") or 0) >= 1,
              "el 10/10 suma una repetició SM-2", json.dumps(sr.get("m4.mult_2digit.032")))

    results = sorted((prof_dir / "results").glob("*.md"), key=lambda f: f.stat().st_mtime) \
        if (prof_dir / "results").is_dir() else []
    rep.check(bool(results) and results[-1].stat().st_mtime >= started,
              "el fitxer de resultats es escriu al tancament",
              results[-1].name if results else "(cap)")

    warns = [l for l in log_path.read_text(errors="ignore").splitlines()
             if "⚠" in l and sid in l] if log_path.exists() else []
    rep.check(not warns, "cap avís del servidor per aquesta sessió", warns[0][:90] if warns else "")

    if args.transcript:
        Path(args.transcript).expanduser().write_text(
            f"# Sessió v2 pas a pas e2e — {prof_dir.name} — {sid}\n\n"
            + "\n\n---\n\n".join(transcript), encoding="utf-8")
        print(f"\ntranscripció: {args.transcript}")

    if quiet:
        bad = [lbl for ok, lbl, _ in rep.rows if not ok]
        print(f"  → {len(rep.rows) - len(bad)}/{len(rep.rows)} bé"
              + (f" · falla: {', '.join(bad)}" if bad else ""))
        return rep
    rep.render()
    return rep


# ---- WP1.1-live: the m7 algebra scenario (test-m7:4201) ----------------------
#
# The live verification WP1.1 deliberately skipped: a 1r ESO profile against the
# real server, with the algebraic grader deciding. In ONE lesson:
#
#   * the m7 curriculum resolves for the profile — the path bar and every card
#     carry m7.* competences. (The ladder places a learner at the LOWEST
#     uncertified level of the subject, so the profile needs its m4 certified —
#     the same provisioning as tests/test_curriculum.py's m7 test.)
#   * an algebraic answer written differently but equivalently ("4x + 5x + 10"
#     for "9x + 10", not the answer nor its also_accept) grades 10: polynomial
#     equivalence, not string match;
#   * a sign slip ("-2x + 12" for "-2x - 12") grades wrong and is filed under
#     the "sign" category — in the Corrections line AND in the .records record;
#   * retyping the problem ("3(x+4)" for "3 · (x + 4)") is caught as
#     "procedure" even though it is trivially equivalent: the task was to
#     TRANSFORM the expression;
#   * a steps card from m7.props_grouping runs the v2 incremental path: one
#     operation per message, notes in between, ONE record with the trace;
#   * the level test machinery with Compute:/Steps: checks runs end to end
#     through the CLI path the WP1.1 tests use (checkpoint_start/answer), live
#     against this profile: 12 bank questions, all right, verdict "pass".

MATH_ALG_IDS = [
    "m7.syntax_letters.011",        # 5x + 10 + 4x → 9x + 10 (answered unsimplified)
    "m7.distributive_letters.005",  # -2 · (x + 6) → -2x - 12 (answered with a sign slip)
    "m7.distributive_letters.009",  # 3 · (x + 4) → 3x + 12 (answered as a verbatim retype)
    "m7.value_numeric.002",         # prose substitution, numeric answer (the numeric path on m7)
    "m7.props_grouping.002",        # steps card: the v2 path, one step per message
]
MATH_ALG_SCRIPT: dict[str, str] = {
    "m7.syntax_letters.011": "4x + 5x + 10",    # equivalent, NOT the answer nor its also_accept
    "m7.distributive_letters.005": "-2x + 12",  # the sign slip
    "m7.distributive_letters.009": "3(x+4)",    # the literal copy of the problem
    "m7.value_numeric.002": "4",
}
MATH_ALG_STEPS: dict[str, list[str]] = {
    "m7.props_grouping.002": ["(5 + 15) + 37", "20 + 37", "57"],
}


def run_algebra(args, cli, prof_dir: Path, rep: "Report", quiet: bool) -> Report | int:
    from db_schema import ERROR_CATEGORIES
    transcript: list[str] = []
    started = time.time()
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    sid = cli.new_session()
    print(f"perfil {prof_dir.name} · port {args.port} · algebra (m7, WP1.1-live) · cua {len(MATH_ALG_IDS)}")
    seed_math_review(prof_dir, MATH_ALG_IDS)
    # seed_math_review archives certificates.json with the rest of the path
    # state; without the m4 certificate the ladder would open math-m4 for this
    # profile, not math-m7. Put it back AFTER the seed, before the first card.
    (prof_dir / "certificates.json").write_text(json.dumps(
        [{"language": "math", "level": "M4", "date": "2026-10-01",
          "type": "checkpoint", "result": "pass"}], indent=2) + "\n", encoding="utf-8")
    print(f"sessió {sid}")

    # --- the curriculum this profile resolves to (CLI, the server's own finder)
    cu = _load_module("math_curriculum", "hooks/curriculum.py")
    cf = cu.find_curriculum(REPO, prof_dir)
    rep.check(bool(cf) and cf.name == "math-m7.md",
              "el currículum que resol per aquest perfil és math-m7.md",
              cf.name if cf else "(cap)")

    replies: list[str] = []
    graded: list[dict] = []          # reply, card, kind ("scripted"/"right"/"step")
    served: list[str] = []
    first_kind: dict[str, str] = {}
    log_path = prof_dir / f"math-web-{args.port}.log"

    def press(cmd: str, label: str) -> str:
        t = time.time()
        body = tutor_text(cli.command(sid, cmd))
        replies.append(body)
        transcript.append(f"## {label}\n\n{body}")
        print(f"  [{label}] → {time.time() - t:.0f}s")
        return body

    def say(answer: str) -> str:
        t = time.time()
        body = tutor_text(cli.say(sid, answer))
        replies.append(body)
        transcript.append(f"## resposta {len(replies)}: «{answer[:120]}»\n\n{body}")
        flags = []
        if not MARKER.search(body): flags.append("sense marcador")
        if "Correct version:" not in body: flags.append("sense versió correcta")
        if not SCORE.search(body): flags.append("sense nota")
        print(f"  {len(replies)} «{answer[:40]}» → {time.time() - t:.0f}s"
              + (f"  ⚠ {', '.join(flags)}" if flags else "  ok"))
        return body

    def say_step(answer: str, final: bool) -> str:
        body = tutor_text(cli.say(sid, answer))
        replies.append(body)
        transcript.append(f"## pas «{answer[:60]}»\n\n{body}")
        graded_note = bool(SCORE.search(body))
        print(f"  «{answer[:40]}» → {'FINAL' if graded_note else 'pas'}"
              + ("  ⚠ nota on no tocava" if graded_note != final else "")
              + ("" if graded_note or "Correct version:" not in body else "  ⚠ versió correcta a mig camí"))
        return body

    def score_of(reply: str) -> int | None:
        m = SCORE.search(reply)
        return int(re.split(r"\s*/\s*", m.group(0))[0]) if m else None

    # --- the path bar (📊): m7 competences, never the m4 pilot's --------------
    view = (cli._call("/api/math/path") or {}).get("data") or {}
    comp_ids = [it["id"] for sec in (view.get("sections") or []) for it in (sec.get("items") or [])]
    rep.check(view.get("available") and view.get("level") == "m7" and comp_ids
              and all(str(i).startswith("m7.") for i in comp_ids),
              "la barra del camí pinta competències m7",
              f"nivell {view.get('level')} · {len(comp_ids)} competències")

    # --- 🔁 Review: the m7 lesson ---------------------------------------------
    txt = press("math-review", "🔁 Review")
    card = bank_card(txt)
    rep.check(card is not None, "la lliçó s'obre amb una targeta del banc",
              txt.strip().splitlines()[0][:70] if txt.strip() else "(buit)")
    plan_file = prof_dir / ".daily" / f"lesson-{today}.json"
    try:
        total = int(json.loads(plan_file.read_text()).get("total") or 0)
    except (OSError, ValueError):
        total = 0
    rep.check(total >= len(MATH_ALG_IDS), "el pla fa la lliçó amb la cua sembrada d'm7", f"{total} exercicis")

    steps_final: dict[str, tuple[str, int | None]] = {}   # steps item -> (final reply, score)
    steps_notes: list[str] = []
    closed = False
    for _ in range(total + 4):
        card = bank_card(txt)
        if card is None:
            break
        served.append(card["id"])
        iid = card["id"]
        if card.get("type") == "steps" and MATH_ALG_STEPS.get(iid) and iid not in steps_final:
            # the v2 path: one operation per message; only the last one grades.
            rep.check("Pas 1 de" in txt and "Una operació per línia:" in txt,
                      "la targeta de passos d'm7 demana NOMÉS la primera operació (v2)",
                      txt[:120].replace("\n", " "))
            lines = MATH_ALG_STEPS[iid]
            for k, line in enumerate(lines):
                body = say_step(line, k == len(lines) - 1)
                if k < len(lines) - 1:
                    steps_notes.append(body)
                else:
                    steps_final[iid] = (body, score_of(body))
                    graded.append({"reply": body, "card": card, "kind": "right"})
                    first_kind.setdefault(iid, "right")
            txt = steps_final[iid][0]
        elif iid in MATH_ALG_SCRIPT and first_kind.get(iid) is None:
            body = say(MATH_ALG_SCRIPT[iid])
            graded.append({"reply": body, "card": card, "kind": "scripted"})
            first_kind[iid] = "scripted"
            txt = body
        else:
            # a re-served card (the bank brings back what was missed) or an
            # unexpected one: answer it exactly right.
            body = say(math_answer(card, "right"))
            graded.append({"reply": body, "card": card, "kind": "right"})
            first_kind.setdefault(iid, "right")
            txt = body
        if CLOSING.search(txt):
            closed = True
            break
    rep.check(closed, "la lliçó es tanca quan el pla s'ha completat",
              f"{len(served)} targetes servides, pla {total}")
    tags = {str((bank_card(t) or {}).get("competence", "")) for t in replies if bank_card(t)}
    rep.check(all(t.startswith("m7.") for t in tags) and bool(tags),
              "totes les targetes servides són de competències m7", ",".join(sorted(tags))[:90])

    # --- the algebraic verdicts, on screen -------------------------------------
    def reply_for(iid: str) -> str:
        for g in graded:
            if g["card"] and g["card"]["id"] == iid and g["kind"] == "scripted":
                return g["reply"]
        return ""

    eq_body = reply_for("m7.syntax_letters.011")
    rep.check((score_of(eq_body) or 0) == 10 and "✅" in eq_body,
              "«4x + 5x + 10» contra «9x + 10»: forma equivalent, 10/10",
              f"{score_of(eq_body)}/10")
    sign_body = reply_for("m7.distributive_letters.005")
    sign_cats = re.findall(r"→ \*\*\"[^\"]+\"\*\* \((\w+)", sign_body)
    rep.check(sign_body and (score_of(sign_body) or 99) <= 5 and "sign" in sign_cats,
              "«-2x + 12» contra «-2x - 12»: error de signe, categoria «sign» al feedback",
              f"{score_of(sign_body)}/10 · cats {sign_cats}")
    lit_body = reply_for("m7.distributive_letters.009")
    lit_cats = re.findall(r"→ \*\*\"[^\"]+\"\*\* \((\w+)", lit_body)
    rep.check(lit_body and (score_of(lit_body) or 99) <= 5 and "procedure" in lit_cats,
              "«3(x+4)» com a resposta de «3 · (x + 4)»: còpia literal, categoria «procedure»",
              f"{score_of(lit_body)}/10 · cats {lit_cats}")
    rep.check(all(c in ERROR_CATEGORIES for c in sign_cats + lit_cats),
              "les categories són de la taxonomia matemàtica",
              ",".join(sign_cats + lit_cats) if (sign_cats + lit_cats) else "(cap)")

    # --- the v2 steps card ------------------------------------------------------
    if steps_final:
        iid, (body, sc) = next(iter(steps_final.items()))
        rep.check(sc == 10 and "**Passos:**" in body,
                  f"la targeta de passos d'm7 es tanca amb 10/10 i la traça anotada", f"{sc}/10")
        rep.check(bool(steps_notes) and all(not SCORE.search(n) and "Correct version:" not in n
                                            for n in steps_notes),
                  "les notes per pas no qualifiquen (només l'últim missatge tanca l'exercici)",
                  f"{len(steps_notes)} notes")

    # --- 🏁 End: the summary and the persistence -------------------------------
    txt = press("math-end", "🏁 End")
    rep.check(bool(txt.strip()), "el tutor fa el resum de tancament", f"{len(txt)} car.")
    wait_quiet(prof_dir)

    # --- the records: the category must reach .records too ----------------------
    rec_lines: list[dict] = []
    rf = prof_dir / ".records" / f"{sid}.jsonl"
    if rf.exists():
        for line in rf.read_text().splitlines():
            try:
                rec_lines.append(json.loads(line))
            except ValueError:
                pass
    bank_graded = [g for g in graded if g["card"]]
    rep.check(len(rec_lines) >= len(bank_graded),
              "cada resposta del banc arriba a .records/",
              f"{len(rec_lines)} registres per a {len(bank_graded)} respostes")

    def rec_for(iid: str, wrong: bool) -> dict:
        for r in rec_lines:
            if r.get("item_id") == iid and ((r.get("score") or 0) < 8) == wrong:
                return r
        return {}

    sign_rec = rec_for("m7.distributive_letters.005", wrong=True)
    rep.check((sign_rec.get("corrections") or [{}])[0].get("category") == "sign",
              "el registre de l'error de signe porta la categoria «sign»",
              json.dumps(sign_rec.get("corrections"))[:120] if sign_rec else "(sense registre)")
    lit_rec = rec_for("m7.distributive_letters.009", wrong=True)
    rep.check((lit_rec.get("corrections") or [{}])[0].get("category") == "procedure",
              "el registre de la còpia literal porta la categoria «procedure»",
              json.dumps(lit_rec.get("corrections"))[:120] if lit_rec else "(sense registre)")
    eq_rec = rec_for("m7.syntax_letters.011", wrong=False)
    rep.check((eq_rec.get("score") or 0) == 10 and not eq_rec.get("corrections"),
              "la forma equivalent es registra com a 10, sense correccions",
              json.dumps({k: eq_rec.get(k) for k in ("score", "corrections")})[:120] if eq_rec
              else "(sense registre)")
    if steps_final:
        iid = next(iter(steps_final))
        st_rec = rec_for(iid, wrong=False)
        trace = st_rec.get("steps") or []
        rep.check(st_rec.get("skill") == "steps" and len(trace) == len(MATH_ALG_STEPS[iid])
                  and all(s.get("ok") for s in trace) and not any("propagated" in s for s in trace),
                  "el registre de passos d'm7 porta la traça v2 sencera (cap pas propagat)",
                  json.dumps(trace)[:140] if trace else "(sense steps)")

    # --- SM-2: right advances, the two slips come back tomorrow -----------------
    sr = {}
    try:
        sr = json.loads((prof_dir / "spaced-repetition.json").read_text()).get("items") or {}
    except (OSError, ValueError):
        pass
    moved = [i for i in ("m7.syntax_letters.011", "m7.value_numeric.002", "m7.props_grouping.002")
             if sr.get(i, {}).get("due_date") == today or (sr.get(i, {}).get("repetitions") or 0) < 1]
    rep.check(not moved, "els ítems encertats deixen d'estar pendents (SM-2 avançat)", ",".join(moved))
    back = [i for i in ("m7.distributive_letters.005", "m7.distributive_letters.009")
            if sr.get(i, {}).get("due_date") != tomorrow or (sr.get(i, {}).get("repetitions") or 0) != 0]
    rep.check(not back, "els dos lliscaments algebraics tornen demà amb reps 0",
              ",".join(f"{i}:{sr.get(i, {}).get('due_date')}" for i in back))

    results = sorted((prof_dir / "results").glob("*.md"), key=lambda f: f.stat().st_mtime) \
        if (prof_dir / "results").is_dir() else []
    rep.check(bool(results) and results[-1].stat().st_mtime >= started,
              "el fitxer de resultats es escriu al tancament",
              results[-1].name if results else "(cap)")

    # --- the level test machinery, live on this profile (the WP1.1 CLI path) ----
    try:
        M7 = cu.load_curriculum(REPO / "curriculum" / "math-m7.md")
        start = cu.checkpoint_start(prof_dir, M7, today, force=True, stem="math-m7", root=REPO)
        rep.check(bool(start.get("ok")), "la prova de nivell arrenca (checks Compute:/Steps:)",
                  str(start.get("text", ""))[:80].replace("\n", " "))
        total_cp = int(start.get("total") or 0)
        rep.check(total_cp == 12, "el pla de la prova fa 12 preguntes (checkpoint_items)", str(total_cp))
        r, asked_cp, n_compute, n_steps = None, 0, 0, 0
        for _ in range(total_cp + 2):
            run = cu._read_json(cu.run_file(prof_dir), None)
            if not run:
                break
            item = run["items"][run["i"]]
            b = item.get("bank") or {}
            if b.get("type") == "steps":
                ans = "\n".join(s["expect"] for s in b.get("steps", []))
                n_steps += 1
            elif b:
                ans = str(b.get("answer", ""))
                n_compute += 1
            else:
                ans = str(item.get("answer", "")).split(" / ")[0].strip()
            asked_cp += 1
            r = cu.checkpoint_answer(prof_dir, M7, today, ans, root=REPO)
            if r.get("done"):
                break
        res = (r or {}).get("result") or {}
        rep.check(bool((r or {}).get("done")) and asked_cp == total_cp,
                  "la prova es completa pregunta a pregunta", f"{asked_cp} de {total_cp}")
        rep.check(n_steps > 0 and n_compute > 0,
                  "la prova barreja preguntes compute i de passos del banc d'm7",
                  f"compute {n_compute} · steps {n_steps}")
        rep.check(res.get("correct") == res.get("items") and res.get("result") == "pass",
                  "12/12 i veredicte «pass»: els checks Compute:/Steps: es resolen en viu",
                  json.dumps({k: res.get(k) for k in ("correct", "items", "result")}))
    except Exception as e:
        rep.check(False, "la prova de nivell en viu (CLI)", f"{type(e).__name__}: {e}")

    # --- no CEFR leak, no server warnings ---------------------------------------
    all_text = "\n".join(replies)
    leaks = [m.group(0) for m in CEFR_LEAK.finditer(on_screen(all_text))]
    rep.check(not leaks, "cap menció de nivell CEFR en una sessió d'm7", leaks[0] if leaks else "")
    warns = [l for l in log_path.read_text(errors="ignore").splitlines()
             if "⚠" in l and sid in l] if log_path.exists() else []
    rep.check(not warns, "cap avís del servidor per aquesta sessió", warns[0][:90] if warns else "")

    if args.transcript:
        Path(args.transcript).expanduser().write_text(
            f"# Sessió àlgebra m7 e2e — {prof_dir.name} — {sid}\n\n"
            + "\n\n---\n\n".join(transcript), encoding="utf-8")
        print(f"\ntranscripció: {args.transcript}")

    if quiet:
        bad = [lbl for ok, lbl, _ in rep.rows if not ok]
        print(f"  → {len(rep.rows) - len(bad)}/{len(rep.rows)} bé"
              + (f" · falla: {', '.join(bad)}" if bad else ""))
        return rep
    rep.render()
    return rep


# ---- the days scenario's learner: one who knows some of the answers ---------
#
# Answering junk only proves the tutor can grade a wrong answer, never whether
# a right one earns a high score, a green marker and the right item_id. The
# server knows what it asked (notes.jsonl carries the assigned item) and the
# seed knows that item's answer, so this learner can answer right on purpose,
# and wrong the way a real learner is wrong. (WP1.9: the model-driven scenarios
# that used these — wander/marathon/journey/noisy/topics — are gone with the
# language path; 🎓 days still drives them.)
DECOY = "table"
DECOYS = (DECOY, "dog")


# ---- WP5.2: the language-domain scenario (bank path, no model) --------------


def run_language(args, cli, prof_dir: Path, rep: "Report", quiet: bool) -> Report | int:
    """WP5.2: the language domain on the unified core, bank path (no model).
    Asserts the domain seams: the fluent command loads (the regexos accept the
    fluent prefix), the curriculum resolves to the language course, the record
    carries a language skill, and the canonical lesson logic (math-review keys)
    runs for a fluent-review press."""
    sid = cli.new_session()
    txt = tutor_text(cli.command(sid, "fluent-learn"))
    rep.check(bool(txt.strip()), "fluent-learn loads and answers (the regexos accept the fluent prefix)",
              txt.strip().splitlines()[0][:70] if txt.strip() else "(empty)")
    ans = tutor_text(cli.say(sid, "three cats"))
    recs: list[dict] = []
    rp = prof_dir / ".records"
    if rp.is_dir():
        f = rp / f"{sid}.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    recs.append(json.loads(line))
                except ValueError:
                    pass
    skills = {str(r.get("skill", "")) for r in recs}
    graded = bool(SCORE.search(ans))
    if graded:
        rep.check(bool(recs) and skills <= {"vocabulary", "grammar", "spelling", "computation"},
                  "the record carries a language skill, never a math-only one",
                  f"{len(recs)} records · skills {sorted(skills)}")
    else:
        rep.check(True, "records not provable this run (model unreachable — seam checked when it answers)",
                  f"0 graded · {len(recs)} records")
    cu = _load_module("lang_curriculum", "hooks/curriculum.py")
    cf = cu.find_curriculum(REPO, prof_dir)
    rep.check(bool(cf) and cf.name.startswith("en-"),
              "the curriculum that resolves is the language course",
              cf.name if cf else "(none)")
    rev = tutor_text(cli.command(sid, "fluent-review"))
    plan = prof_dir / ".daily" / f"lesson-{date.today().isoformat()}.json"
    total = 0
    try:
        total = int(json.loads(plan.read_text()).get("total") or 0)
    except (OSError, ValueError):
        pass
    rep.check(total > 0, "fluent-review opens the lesson (the canonical keys work for fluent-*)",
              f"lesson total {total}")
    return rep.render()


def decoy_for(item: dict | None) -> str:
    """A wrong answer that is not the item's own answer. Measured 2026-09-21: on
    the card for «taula» the decoy «table» IS the answer, the tutor marked it 10/10
    and the bench blamed it (days 083631)."""
    own = {str((item or {}).get("answer", "")).strip().lower(),
           str((item or {}).get("content", "")).strip().lower()}
    return next((d for d in DECOYS if d not in own), DECOYS[-1])



def onscreen_item(notes_path: Path, sr_path: Path, sid: str) -> dict | None:
    """The review item behind the exercise on screen right now.

    The note written while the previous message was processed names the item
    the server handed out for the NEXT exercise, which is the one now waiting
    for an answer."""
    try:
        lines = [json.loads(l) for l in notes_path.read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        return None
    mine = [n for n in lines if n.get("session") == sid]
    assigned = (mine[-1].get("assigned") if mine else None) or None
    if not assigned:
        return None
    try:
        it = json.loads(sr_path.read_text())["items"][assigned["id"]]
    except (OSError, ValueError, KeyError):
        return {"id": assigned["id"], "content": assigned.get("content", ""),
                "answer": "", "learner_wrote": ""}
    return {"id": assigned["id"], "content": str(it.get("content", "")),
            "answer": str(it.get("answer", "")), "learner_wrote": str(it.get("learner_wrote", ""))}


def student_answer(kind: str, item: dict | None) -> str:
    """right: the item's answer. wrong: the slip a learner would make."""
    if not item or not item.get("answer"):
        return "no ho sé"
    if kind == "right":
        return item["answer"]
    return item.get("learner_wrote") or decoy_for(item)


def _words(text: str) -> set[str]:
    folded = "".join(ch for ch in unicodedata.normalize("NFD", (text or "").lower())
                     if unicodedata.category(ch) != "Mn")
    return set(re.findall(r"[a-z0-9']+", folded))


def exercise_tail(reply: str) -> str:
    """The exercise a reply ends on: from its last heading, not the feedback."""
    heads = list(re.finditer(r"(?m)^#{1,6} ", reply or ""))
    return (reply or "")[heads[-1].start():] if heads else (reply or "")[-500:]


def follows_item(item: dict | None, reply: str) -> bool:
    """Is the exercise about the item the server assigned?

    Half of the item's words showing up in the exercise is enough: the tutor
    builds the exercise ("She ___ to school") from the item ("She goes to
    school"), it does not copy it."""
    if not item:
        return False
    want = _words(item.get("content", "")) | _words(item.get("answer", ""))
    if not want:
        return False
    return len(want & _words(exercise_tail(reply))) / len(want) >= 0.5


# The tutor picks its own words in free Vocabulary (beure, dia, plat, cotxe,
# telefon…), and every one outside the bank was an unjudged "no ho sé".
EXTRA_WORDS = [
    ("to drink", "beure"), ("day", "dia"), ("plate", "plat"), ("car", "cotxe"),
    ("phone", "telèfon"), ("cat", "gat"), ("sun", "sol"), ("moon", "lluna"),
    ("night", "nit"), ("table", "taula"), ("chair", "cadira"), ("door", "porta"),
    ("city", "ciutat"), ("sea", "mar"), ("tree", "arbre"), ("apple", "poma"),
    ("milk", "llet"), ("coffee", "cafè"), ("time", "hora"), ("year", "any"),
    ("week", "setmana"), ("money", "diners"), ("work", "feina"), ("family", "família"),
    ("child", "nen"), ("woman", "dona"), ("man", "home"), ("red", "vermell"),
    ("big", "gran"), ("small", "petit"),
]
_BANK: list | None = None


def vocab_bank() -> list[tuple[str, str]]:
    """(english, catalan) pairs — the seed's own vocabulary, one source."""
    global _BANK
    if _BANK is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("math_seed", Path(__file__).with_name("flowed-seed.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _BANK = [(en, ca) for en, ca in mod.VOCAB] + EXTRA_WORDS
    return _BANK


def _fold_text(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", (text or "").lower())
                   if unicodedata.category(ch) != "Mn")


def bank_item(reply: str, strict: bool = False) -> dict | None:
    """The bank word the exercise on screen is about, if it is one of ours.

    The tutor picks its own vocabulary, so a word outside the bank is possible;
    then there is nothing to judge the answer against, and the turn is left out
    of the right/wrong checks (it is still checked for a grade)."""
    tail = _fold_text(exercise_tail(reply))
    # The card names its word on a labelled line ("**Català:** aigua", "**Word
    # (Catalan):** "matí""). Look there first: the CONTEXT sentence under it can
    # hold another bank word (a card for "capitalització" whose context says "els
    # dies de la setmana" was answered "week", and the tutor rightly gave 6/10).
    head = re.search(r"\*\*(?:Catal[àa]|Catalan|Word|Paraula)[^*:\n]*:\*\*\s*[\"“«]?([^\n\"”»*]+)", exercise_tail(reply), re.I)
    if head:
        word = _fold_text(head.group(1)).strip(" .?!:")
        for en, ca in vocab_bank():
            if _fold_text(ca) == word:
                return {"id": None, "content": ca, "answer": en, "learner_wrote": ""}
        return None
    if strict:
        # Only a card that names its word on a labelled line. Looking for any Catalan word
        # in the text found "home" (= man) in "describing your home" and answered "man".
        return None
    best = None
    for en, ca in vocab_bank():
        m = re.search(rf"(?<![a-z]){re.escape(_fold_text(ca))}(?![a-z])", tail)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), en, ca)
    if not best:
        return None
    return {"id": None, "content": best[2], "answer": best[1], "learner_wrote": ""}


def free_vocab_answer(kind: str, item: dict | None) -> str:
    if not item:
        return "no ho sé"
    if kind == "right":
        return item["answer"]
    bank = vocab_bank()
    others = [en for en, _ in bank if en != item["answer"]]
    return others[(len(item["answer"]) + 3) % len(others)]   # a real word, the wrong one


REVIEW_BLOCK = re.compile(r"```math:review_results.*?```", re.S)


def on_screen(text: str) -> str:
    """The reply as the learner sees it: the web app hides the review-results
    block (web/app.js), it is data for the server. Looking for template braces
    in the raw text flagged its JSON as a leaked placeholder."""
    return REVIEW_BLOCK.sub("", text or "")


def classify_repeats(asked, practice_of, answer_idx, known=None):
    """What was asked again, and did it matter?

    An exercise shown again while it was still UNANSWERED is not a repeat: she
    walked away from it, or pressed a button that brought it back, and being
    shown it again is the right thing. A repeat is an exercise she had already
    ANSWERED, and even then it depends where:

      same   — in the same practice. That is the tutor looping.
      cross  — in another practice (Lesson <-> Vocabulary). The server allows a
               bare term to come up in two practices, so this is reported but
               never fails the run.

    `fresh[i]` are the fingerprints of turn i she has not answered yet, which is
    what "did the question change" has to mean.

    `known` (indices of the answers that were RIGHT) narrows what counts as a
    repeat: the server only refuses what she got right — a wrong answer is meant
    to come back (SM-2), and so is one she walked away from. Without it, every
    answer counts.
    """
    answered: dict[str, str] = {}
    answered_known: dict[str, str] = {}
    known_idx = answer_idx if known is None else known
    fresh_each, same, cross, unanswered = [], [], [], []
    seen: set[str] = set()
    for i, fp in enumerate(asked):
        if i in answer_idx and i > 0:
            for f in asked[i - 1]:
                answered.setdefault(f, practice_of[i - 1])
                if i in known_idx:
                    answered_known.setdefault(f, practice_of[i - 1])
        fresh = []
        for f in fp:
            if f in answered_known:
                (same if answered_known[f] == practice_of[i] else cross).append((i, f))
            if f in answered:
                pass
            else:
                fresh.append(f)
                if f in seen:
                    unanswered.append((i, f))
            seen.add(f)
        fresh_each.append(fresh)
    return {"fresh": fresh_each, "same": same, "cross": cross, "unanswered": unanswered}


def is_ungraded(rows) -> bool:
    """A run in which the tutor graded nothing at all.

    Not a separate failure but the same one six times over: with no marker, no
    correct version and no score, half the checks fail together. Counted apart
    so one such run is not read as six problems."""
    for ok, label, detail in rows:
        if label == "posa nota" and not ok:
            return str(detail or "").startswith("0/")
    return False


def numbered_path(path: str, n: int) -> str:
    """transcript-wander.md → transcript-wander.3.md

    With --repeat every execution wrote to the SAME file, so only the last one
    survived: the tutor's actual text in the runs that failed was gone before
    anyone could read it. A number of a rate ("4 of 6 asked nothing") is not a
    cause; the text is."""
    q = Path(path).expanduser()
    return str(q.with_name(f"{q.stem}.{n}{q.suffix}"))


# ---- the "days" scenario: several days in a row, and the queue moving ----------
#
# Everything the other scenarios measure is ONE day. What the system is built on
# is what happens between days: what she answered right does not come back, what
# she missed comes back tomorrow, and the intervals grow 1 → 6 → 16. Waiting a
# day per test is not a plan, so the clock is moved (flowed-advance-day.py) and
# the same learner sits the next lesson.
#
# The learner: each item has its own number of sightings before she knows it
# (0, 1 or 2, fixed by the id), wrong until then and right afterwards. So on any
# day some items are being learned, some are known, and the queue has to tell
# them apart.
def learns_after(item_id: str) -> int:
    return zlib.crc32(item_id.encode()) % 3


def sm2_after(state: dict, quality: int) -> tuple[int, int]:
    """(repetitions, interval_days) after a review — hooks/update-db.py's SM-2."""
    reps = int(state.get("repetitions", 0) or 0)
    interval = int(state.get("interval_days", 1) or 1)
    ef = float(state.get("easiness_factor", 2.5) or 2.5)
    if quality >= 3:
        if reps == 0:
            return 1, 1
        if reps == 1:
            return 2, 6
        return reps + 1, int(round(interval * ef))
    return 0, 1


def record_qualities(records: list[dict]) -> dict[str, int]:
    """item_id -> the quality the hook will store: the LAST record of the item."""
    out: dict[str, int] = {}
    for r in records:
        iid = r.get("item_id")
        if not iid:
            continue
        q = r.get("sm2_quality")
        if q is None:
            try:
                q = int(float(r.get("score", 0) or 0)) // 2
            except (TypeError, ValueError):
                q = 0
        out[iid] = max(0, min(5, int(q)))
    return out


def judge_day(day: int, today: str, tomorrow: str, due0: list[str], sr0: dict, sr1: dict,
              total: int, limit: int, assigned: list[str], answered: list[str],
              quality: dict[str, int], lesson_min: int = 3,
              decoys: set[str] | None = None) -> list[tuple[bool, str, str]]:
    """What has to be true of ONE day of the days scenario. Pure: no I/O."""
    rows: list[tuple[bool, str, str]] = []
    want = min(len(due0), max(limit, 1)) if due0 else lesson_min
    rows.append((total == want, f"dia {day}: la lliçó té la mida del pendent",
                 f"{total} exercicis, {len(due0)} pendents (esperat {want})"))
    extra = sorted(set(assigned) - set(due0))
    rows.append((not extra, f"dia {day}: no torna cap ítem que no tocava", ", ".join(extra[:3])))
    if len(due0) <= total:
        missing = sorted(set(due0) - set(answered))
        rows.append((not missing, f"dia {day}: tot el pendent surt a la lliçó", ", ".join(missing[:3])))
    else:
        got = len(set(answered) & set(due0))
        rows.append((got >= total, f"dia {day}: tot el pendent surt a la lliçó",
                     f"{got} de {total} possibles"))
    have = [i for i in answered if i in quality]
    rows.append((len(have) >= len(answered) - 1, f"dia {day}: cada resposta queda registrada amb item_id",
                 f"{len(have)} de {len(answered)}"))
    bad_sm2, bad_wrong, bad_right = [], [], []
    for iid in dict.fromkeys(answered):
        if iid not in quality or iid not in sr0 or iid not in sr1:
            continue
        q = quality[iid]
        reps, interval = sm2_after(sr0[iid], q)
        due = (date.fromisoformat(today) + timedelta(days=interval)).isoformat()
        a = sr1[iid]
        if (a.get("repetitions"), a.get("interval_days"), a.get("due_date")) != (reps, interval, due):
            bad_sm2.append(f"{iid}: q{q} {sr0[iid].get('repetitions')}/{sr0[iid].get('interval_days')}d → "
                           f"{a.get('repetitions')}/{a.get('interval_days')}d {a.get('due_date')} "
                           f"(esperat {reps}/{interval}d {due})")
        if q < 3 and a.get("due_date") != tomorrow:
            bad_wrong.append(f"{iid}: fallat però vence {a.get('due_date')}")
        if q >= 3 and int(sr0[iid].get("repetitions", 0) or 0) >= 1 and str(a.get("due_date")) <= tomorrow:
            bad_right.append(f"{iid}: ja sabut i encertat però vence {a.get('due_date')}")
    if decoys:
        passed = [f"{i}: paraula equivocada amb qualitat {quality[i]}" for i in decoys
                  if i in quality and quality[i] >= 3]
        rows.append((not passed, f"dia {day}: una paraula equivocada no compta com a sabuda",
                     passed[0] if passed else ""))
    rows.append((not bad_sm2, f"dia {day}: l'SM-2 avança com toca", bad_sm2[0] if bad_sm2 else ""))
    rows.append((not bad_wrong, f"dia {day}: el que s'ha fallat torna demà", bad_wrong[0] if bad_wrong else ""))
    rows.append((not bad_right, f"dia {day}: el que ja se sabia i s'ha encertat s'allunya",
                 bad_right[0] if bad_right else ""))
    moved = [i for i in due0 if i not in answered and i in sr0 and i in sr1
             and (sr1[i].get("due_date"), sr1[i].get("repetitions")) !=
             (sr0[i].get("due_date"), sr0[i].get("repetitions"))]
    rows.append((not moved, f"dia {day}: el que no s'ha contestat no es toca", moved[0] if moved else ""))
    return rows


def judge_carry(day: int, prev_wrong: list[str], prev_known: list[str], answered: list[str],
                total: int, due0: list[str]) -> list[tuple[bool, str, str]]:
    """Between two days: what she missed is back, what she knew is not."""
    rows = []
    if len(due0) <= total:
        back = sorted(set(prev_wrong) - set(answered))
        rows.append((not back, f"dia {day}: el que va fallar ahir torna avui", ", ".join(back[:3])))
    early = sorted(set(prev_known) & set(answered))
    rows.append((not early, f"dia {day}: el que va encertar ahir (i ja sabia) no torna avui",
                 ", ".join(early[:3])))
    return rows


def sr_items(prof_dir: Path) -> dict:
    try:
        return json.loads((prof_dir / "spaced-repetition.json").read_text(encoding="utf-8")).get("items") or {}
    except (OSError, ValueError):
        return {}


def run_days(args, cli, prof_dir: Path, rep: "Report", quiet: bool):
    ndays = max(2, args.days)
    limit = 20
    try:
        raw = json.loads((prof_dir / "spaced-repetition.json").read_text()).get("daily_limits", {})
        limit = int(raw.get("review_items_per_day") or limit)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    notes_path = prof_dir / ".metrics" / "notes.jsonl"
    seen: dict[str, int] = {}
    sids: set[str] = set()
    transcript: list[str] = []
    table: list[str] = []
    prev_wrong: list[str] = []
    prev_known: list[str] = []
    print(f"perfil {prof_dir.name} · port {args.port} · {ndays} dies seguits")

    for day in range(1, ndays + 1):
        if day > 1:
            wait_quiet(prof_dir)
            p = subprocess.run([sys.executable, str(REPO / "scripts" / "flowed-advance-day.py"),
                                prof_dir.name, "--dir", str(prof_dir), "--days", "1"],
                               capture_output=True, text=True)
            if p.returncode != 0:
                rep.check(False, f"dia {day}: el rellotge avança",
                          (p.stderr or p.stdout).strip()[-120:])
                break
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        sr0 = json.loads(json.dumps(sr_items(prof_dir)))
        due0 = due_now(prof_dir)
        plan_path = prof_dir / ".daily" / f"lesson-{today}.json"
        print(f"\n--- dia {day} ({today}) · {len(due0)} per repassar ---")

        sid = cli.new_session()
        sids.add(sid)
        t0 = time.time()
        greeting = tutor_text(cli.command(sid, "math-learn"))
        first = tutor_text(cli.command(sid, "math-review"))
        transcript.append(f"# dia {day} · {today} · sessió {sid}\n\n## /math-learn\n\n{greeting}\n\n## 🎓 Lesson\n\n{first}")
        if day == 1 and not greeting.strip() and time.time() - t0 < 3:
            print("\n❌ el tutor no ha dit res i ha trigat 0s: el model no respon.", file=sys.stderr)
            return 2
        try:
            total = int(json.loads(plan_path.read_text()).get("total") or 0)
        except (OSError, ValueError):
            total = 0
        rep.check(total > 0, f"dia {day}: el servidor ha fet el pla de la lliçó", f"{total} exercicis")
        if not total:
            break

        replies = [first]
        answered: list[str] = []
        kinds: dict[str, str] = {}
        decoys: set[str] = set()
        on_item = 0
        for n in range(total):
            item = onscreen_item(notes_path, prof_dir / "spaced-repetition.json", sid)
            iid = item.get("id") if item else None
            if iid and item.get("answer"):
                k = "right" if seen.get(iid, 0) >= learns_after(iid) else "wrong"
                seen[iid] = seen.get(iid, 0) + 1
                answer = student_answer(k, item)
                answered.append(iid)
                kinds[iid] = k
                if k == "wrong" and answer in DECOYS:
                    decoys.add(iid)
                on_item += 1 if follows_item(item, replies[-1]) else 0
            else:
                answer = "no ho sé"
            t = time.time()
            body = tutor_text(cli.say(sid, answer))
            replies.append(body)
            transcript.append(f"## dia {day} · resposta {n + 1}: «{answer}»"
                              f"{' (' + kinds[iid] + ' · ' + iid + ')' if iid in kinds else ''}\n\n{body}")
            print(f"  {n + 1}/{total} «{answer}» → {time.time() - t:.0f}s"
                  + (f"  [{kinds[iid]}]" if iid in kinds else ""))
            if CLOSING.search(body):
                break

        wait_quiet(prof_dir)
        sr1 = sr_items(prof_dir)
        records: list[dict] = []
        rf = prof_dir / ".records" / f"{sid}.jsonl"
        if rf.exists():
            for line in rf.read_text().splitlines():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    pass
        quality = record_qualities(records)
        assigned: list[str] = []
        if notes_path.exists():
            for line in notes_path.read_text().splitlines():
                try:
                    nt = json.loads(line)
                except ValueError:
                    continue
                a = nt.get("assigned") if nt.get("session") == sid else None
                if a and a.get("id") and a["id"] not in assigned:
                    assigned.append(a["id"])

        for ok, label, detail in judge_day(day, today, tomorrow, due0, sr0, sr1, total, limit,
                                           assigned, answered, quality, decoys=decoys):
            rep.check(ok, label, detail)
        if day > 1:
            for ok, label, detail in judge_carry(day, prev_wrong, prev_known, answered, total, due0):
                rep.check(ok, label, detail)
        if answered:  # a day with nothing due is drills: there is no item to follow
            rep.check(on_item >= max(1, (len(answered) * 2 + 2) // 3),
                      f"dia {day}: l'exercici és sobre l'ítem que el servidor ha assignat",
                      f"{on_item} de {len(answered)}")
        try:
            done = int(json.loads(plan_path.read_text()).get("done") or 0)
        except (OSError, ValueError):
            done = 0
        rep.check(done >= min(len(answered), total) - 1, f"dia {day}: el pla compta les respostes",
                  f"{done} de {len(answered)}")

        # What the server thought, per day, beside what the learner saw: the plan
        # (done / credited / covered), the note it gave the tutor each turn, and every
        # guard event. Without them a red "el pla compta les respostes" is a number
        # nobody can trace back.
        try:
            plan_now = json.loads(plan_path.read_text())
        except (OSError, ValueError):
            plan_now = {}
        diag = [f"## dia {day} · pla del servidor\n\n" + json.dumps(plan_now, ensure_ascii=False, indent=1)]
        for label, fpath in (("notes del servidor al tutor", notes_path),
                             ("guard del servidor", prof_dir / ".metrics" / "guards.jsonl")):
            rows_ = []
            if fpath.exists():
                for line in fpath.read_text().splitlines():
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if obj.get("session") == sid:
                        rows_.append("- " + json.dumps({k: v for k, v in obj.items() if k != "session"},
                                                       ensure_ascii=False))
            diag.append(f"## dia {day} · {label}\n\n" + ("\n".join(rows_) or "(res)"))
        transcript.append("\n\n".join(diag))
        print(f"  pla: {plan_now.get('done')} de {plan_now.get('total')} · credited "
              f"{len(plan_now.get('credited') or [])} · covered {len(plan_now.get('covered') or [])}")

        prev_wrong = [i for i in answered if quality.get(i, 0) < 3]
        prev_known = [i for i in answered if quality.get(i, 0) >= 3
                      and int(sr0.get(i, {}).get("repetitions", 0) or 0) >= 1]
        right = sum(1 for i in answered if quality.get(i, 0) >= 3)
        table.append(f"  dia {day}: pendents {len(due0):>2} · lliçó {total:>2} · encertats {right} · "
                     f"fallats {len(answered) - right} · demà torna {sum(1 for v in sr1.values() if str(v.get('due_date')) <= tomorrow)}"
                     f" · intervals {sorted({int(v.get('interval_days', 0) or 0) for v in sr1.values()})}")

    print("\n=== els dies ===")
    print("\n".join(table))
    if args.transcript:
        Path(args.transcript).expanduser().write_text(
            f"# Dies seguits — {prof_dir.name}\n\n" + "\n\n---\n\n".join(transcript), encoding="utf-8")
        print(f"\ntranscripció: {args.transcript}")
    guards = prof_dir / ".metrics" / "guards.jsonl"
    fired = 0
    if guards.exists():
        for line in guards.read_text().splitlines():
            try:
                g = json.loads(line)
            except ValueError:
                continue
            # "rewritten" is the outcome of the previous line, not a second trigger.
            if g.get("session") in sids and not str(g.get("note", "")).strip().startswith("rewritten"):
                fired += 1
    rep.guards = fired
    if quiet:
        bad = [lbl for ok, lbl, _ in rep.rows if not ok]
        print(f"  → {len(rep.rows) - len(bad)}/{len(rep.rows)} bé"
              + (f" · falla: {', '.join(bad)}" if bad else "") + f" · guard {rep.guards}×")
        return rep
    rep.render()
    return rep


# ---- the "curriculum" scenario: a student going through A1 -> A2 in free practice ----
#
# The Lesson has its item handed out by the server; free practice (Mix, Vocabulary)
# now has its COMPETENCE handed out too (docs/ESQUEMA-APRENENTATGE.md, phase 2).
# This walks a simulated student through several days of it and looks at three
# things: does the tutor ask what the server assigned, does every answer become a
# record the path can use, and does the path move the way the answers say.
#
# Nothing here judges the model's teaching. The student's ability per competence is
# a fixed curve (scripts/flowed-sim-path.py); what the model is asked for is the
# base: the right kind of question, in order, graded, recorded.
#
# Answers: vocabulary from the bench word bank (right or wrong known for certain);
# grammar and functions written by a model told to be right or to make a typical A1
# mistake. If no model answers at --student-url the grammar answers are "no ho sé"
# and only the exercise checks mean anything.
CURRICULUM_LEAK = re.compile(r"curriculum\s*[—-]|next exercise practises|\bcompetenc(?:e|ia|ència)\b", re.I)


def _load_module(name: str, rel: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def student_llm(url: str, exercise: str, ok: bool, timeout: int = 90) -> str | None:
    """One answer from a model playing an A1 learner: right, or with one typical mistake."""
    how = ("Answer it CORRECTLY." if ok else
           "Answer it with ONE typical mistake of an A1 learner (wrong verb form or tense, a missing "
           "article or preposition, wrong word order, or a wrong word). Do not mention the mistake.")
    body = {
        "model": "student", "temperature": 0.6, "max_tokens": 80,
        "messages": [
            {"role": "system", "content": "You play an English learner at level A1 whose native language is "
             "Catalan. Reply with ONLY the text of your answer: no explanation, no quotes, no labels."},
            {"role": "user", "content": f"Exercise:\n{exercise.strip()[:900]}\n\n{how}"},
        ],
    }
    try:
        req = urllib.request.Request(url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode())
        text = out["choices"][0]["message"]["content"] or ""
    except Exception:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    line = next((l for l in text.splitlines() if l.strip()), "")
    line = re.sub(r"^(answer|resposta)\s*:\s*", "", line.strip().strip("*").strip(), flags=re.I)
    return line.strip("\"“”'` ")[:200] or None


def onscreen_competence(notes_path: Path, sid: str) -> dict | None:
    """The competence the server assigned for the exercise now on screen (last note of the session)."""
    try:
        rows = [json.loads(l) for l in notes_path.read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        return None
    mine = [r for r in rows if r.get("session") == sid]
    return (mine[-1].get("competence") if mine else None) or None


def has_signal(signals: list[str], text: str) -> bool:
    hay = " " + " ".join(re.findall(r"[a-z0-9']+", _fold_text(text))) + " "
    for sg in signals:
        w = " ".join(re.findall(r"[a-z0-9']+", _fold_text(sg)))
        if w and f" {w} " in hay:
            return True
    return False


def vocab_card_on_list(words: list[str], text: str) -> bool:
    """Is this vocabulary card about a word of the assigned list?

    Looking for the ENGLISH word only was right for an English→Catalan card and
    wrong for the other direction: a «Català: vermell — what is it in English?»
    card hides the English word on purpose, because it is the answer. Every such
    card counted as off-list (the fake tutor's check, 0 of 21, since at least
    2026-09-19). So a Catalan word whose English is on the list counts too.
    """
    if has_signal(words, text):
        return True
    wanted = {w.strip().lower() for w in words}
    return has_signal([ca for en, ca in vocab_bank() if en.strip().lower() in wanted], text)


VOCAB_DIRECTION_RE = re.compile(
    r"what is the (english|catalan)\s*(?:word|translation)\s*for\s*[\"'“]([^\"'”]+)[\"'”]",
    re.I,
)


def vocab_direction_bug(text: str, extra_english: set[str] | None = None) -> str | None:
    """'What is the English word for X' where X is already English (or the
    Catalan mirror) -- the card asking to translate itself. Found live on
    2026-09-23: a card showed an English number and then asked for its
    English word. `extra_english` widens the English side beyond the fixed
    demo vocab_bank() -- the curriculum's own Vocabulari word lists (numbers,
    days...), which is where the bug was actually seen."""
    m = VOCAB_DIRECTION_RE.search(exercise_tail(text))
    if not m:
        return None
    lang, word = m.group(1).lower(), _fold_text(m.group(2)).strip(" .?!:")
    if lang == "english" and word in (extra_english or set()):
        return f'demana la paraula anglesa de "{m.group(2)}", que ja \u00e9s angl\u00e8s'
    for en, ca in vocab_bank():
        en_f, ca_f = _fold_text(en), _fold_text(ca)
        if lang == "english" and word == en_f:
            return f'demana la paraula anglesa de "{m.group(2)}", que ja \u00e9s angl\u00e8s'
        if lang == "catalan" and word == ca_f:
            return f'demana la paraula catalana de "{m.group(2)}", que ja \u00e9s catal\u00e0'
    return None


MARKER_LINE_RE = re.compile(r"\*{0,2}Type your answer\s*\(([^)]*)\)\s*:?\*{0,2}", re.I)


def marker_mode(text: str) -> str | None:
    """The declared answer shape of the exercise on screen ('just the missing
    word' / 'the complete sentence'), from its own closing marker line."""
    m = MARKER_LINE_RE.search(text)
    return m.group(1).lower() if m else None


def marker_structure_bug(mode: str | None, feedback: str) -> str | None:
    """The marker promised one shape (a word / a sentence) but the
    'Correct version:' the tutor then grades against is the other shape --
    found live: a one-word gap and a no-gap vocab prompt both defaulted to
    '(the complete sentence)'."""
    if not mode:
        return None
    cv = CORRECT_VERSION.search(feedback)
    if not cv:
        return None
    words = len(cv.group(1).split())
    if "missing word" in mode and words > 2:
        return f'marcador de "nom\u00e9s la paraula" per\u00f2 "Correct version:" t\u00e9 {words} paraules'
    if "complete sentence" in mode and words <= 1:
        return f'marcador de "frase completa" per\u00f2 "Correct version:" t\u00e9 {words} paraula'
    return None


def run_curriculum(args, cli, prof_dir: Path, rep: "Report", quiet: bool, setup: bool = True, finish: bool = True):
    if not RESETTABLE.match(prof_dir.name):
        print(f"❌ l'escenari curriculum només corre en perfils de proves, no en {prof_dir.name}", file=sys.stderr)
        return 2
    ndays = max(2, args.days)
    sys.path.insert(0, str(REPO / "hooks"))
    cu = _load_module("math_curriculum", "hooks/curriculum.py")
    sim = _load_module("math_sim_path", "scripts/flowed-sim-path.py")

    # The course this scenario tests: A2 (the learner comes with A1 certified by the teacher — a
    # "placement" — so the ladder does not send her back to A1) or A1 (from zero). The scratch
    # profile is set up for it; the file is restored by --repeat, and a test profile has nothing to lose.
    course = (getattr(args, "course", None) or "A2").upper()
    if setup:
        if not args.reset:
            reset_profile(prof_dir)
        lp = prof_dir / "learner-profile.json"
        doc = json.loads(lp.read_text(encoding="utf-8"))
        learner = doc.setdefault("learner", {})
        learner.update({"target_language": "English", "target_level": getattr(args, "target_level", None) or course,
                        "current_level": "A0" if course == "A1" else "A1"})
        lp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        park_learner_path(prof_dir)
        if course == "A2":
            cu._write_json(cu.certificates_file(prof_dir), [
                {"language": "English", "level": "A1", "date": date.today().isoformat(), "type": "placement",
                 "result": "manual", "pct": None, "weak": [], "archive": None}])
    cf = cu.find_curriculum(REPO, prof_dir)
    print(f"perfil {prof_dir.name}: English, curs {course}")
    if cf is None:
        print("❌ no hi ha cap curriculum/*.md per a aquest perfil (llengua i nivell)", file=sys.stderr)
        return 2
    cur = cu.load_curriculum(cf)
    by_id = {c["id"]: c for c in cur["competencies"]}
    all_english = {w.strip().lower() for c in cur["competencies"] for w in (c.get("words") or [])}
    problems = cu.validate_curriculum(cur)
    rep.check(not problems, "el curriculum és vàlid", "; ".join(problems[:3]))

    # A clean start: nothing due (the Lesson's review gate would take the first exercises of
    # every Mix), no old records (the path is derived from them), no old path (done above).
    if setup:
        archive(prof_dir / ".records")
    # (notes are matched by session id: older runs cannot be mistaken for this one)

    notes_path = prof_dir / ".metrics" / "notes.jsonl"
    guards_path = prof_dir / ".metrics" / "guards.jsonl"
    student = sim.Student(args.student, args.seed, cur)
    start = date.today()
    sids: set[str] = set()
    transcript: list[str] = []
    table: list[str] = []
    llm_ok = {"n": 0, "fail": 0}
    turns_total = {"asked": 0, "assigned": 0, "follow_seen": 0, "follow_ok": 0, "leak": 0,
                   "graded": 0, "verdict_seen": 0, "verdict_ok": 0, "gram_seen": 0, "gram_ok": 0,
                   "vocab_tag_seen": 0, "vocab_tag_ok": 0}
    repeat_findings: list[str] = []
    marker_score_mismatches: list[str] = []
    vocab_direction_findings: list[str] = []
    marker_structure_findings: list[str] = []
    kinds_seen: dict[str, int] = {}
    order_seen: list[str] = []
    print(f"perfil {prof_dir.name} · port {args.port} · {ndays} dies · alumne {args.student} (llavor {args.seed}) · "
          f"{args.answers} Mix + {args.vocab} Vocabulary per dia · curriculum {cf.name}")
    print(f"model de l'alumne (gramàtica): {args.student_url}")

    def answer_turns(sid: str, first: str, count: int, day: int, label: str) -> None:
        reply = first
        sim_today = start + timedelta(days=day - 1)
        asked_fps: list[list[str]] = [fingerprints(first)]
        known_idx: set[int] = set()
        for n in range(count):
            comp = onscreen_competence(notes_path, sid)
            cid = comp.get("id") if comp else None
            asked_now = bool(exercise_tail(reply).strip()) and not GREETING_RE.search(reply[:80]) \
                and not MENU_RE.search(reply)
            if asked_now:
                turns_total["asked"] += 1
                turns_total["assigned"] += 1 if cid else 0
                if cid:
                    kinds_seen[comp.get("kind") or "?"] = kinds_seen.get(comp.get("kind") or "?", 0) + 1
                    if not order_seen or order_seen[-1] != cid:
                        order_seen.append(cid)
            vbug = vocab_direction_bug(reply, all_english)
            if vbug:
                vocab_direction_findings.append(f"dia {day} {label} torn {n + 1}: {vbug}")
            mode = marker_mode(exercise_tail(reply))
            c = by_id.get(cid) if cid else None
            ok = student.answer(cid, sim_today) if c else (n % 2 == 0)
            how = ""
            answer = "no ho sé"
            item = bank_item(reply, strict=True) if (c is None or c["words"]) else None
            if item:
                answer = free_vocab_answer("right" if ok else "wrong", item)
                how = "banc"
            else:
                got = student_llm(args.student_url, exercise_tail(reply), ok)
                llm_ok["n"] += 1
                if got:
                    answer, how = got, "model"
                else:
                    llm_ok["fail"] += 1
                    how = "sense model"
            t = time.time()
            body = tutor_text(cli.say(sid, answer))
            transcript.append(f"## dia {day} · {label} · resposta {n + 1}: «{answer}» "
                              f"[{cid or 'sense competència'} · {'bé' if ok else 'malament'} · {how}]\n\n{body}")
            shown = on_screen(body)
            asked_fps.append(fingerprints(body))
            sc = SCORE.search(shown)
            score = int(sc.group(0).split("/")[0]) if sc else None
            if score is not None and score >= 8:
                known_idx.add(n + 1)
            mbug = marker_structure_bug(mode, shown)
            if mbug:
                marker_structure_findings.append(f"dia {day} {label} torn {n + 1}: {mbug}")
            if score is not None:
                marks = set(MARKER.findall(shown)) - {"✅", "❌"}
                lines_ = [l for l in shown.split("\n") if l.strip()]
                verdict_ = [l for i, l in enumerate(lines_) if i == 0 or SCORE.search(l)]
                marks |= {m for l in verdict_ for m in MARKER.findall(l)}
                if score <= 4 and marks & {"🟢", "✅"}:
                    marker_score_mismatches.append(f"dia {day} {label} torn {n + 1}: 🟢/✅ amb {score}/10")
                elif score >= 8 and marks & {"🔴", "❌"}:
                    marker_score_mismatches.append(f"dia {day} {label} torn {n + 1}: 🔴/❌ amb {score}/10")
            if score is not None and how != "sense model" and (how == "banc" or ok is not None):
                # the tutor's verdict against what the student meant to do
                turns_total["verdict_seen"] += 1 if how == "banc" else 0
                turns_total["verdict_ok"] += 1 if how == "banc" and ((score >= 8) == ok) else 0
                if how == "model":
                    turns_total["gram_seen"] += 1
                    turns_total["gram_ok"] += 1 if ((score >= 8) == ok) else 0
            turns_total["graded"] += 1 if score is not None else 0
            if CURRICULUM_LEAK.search(shown):
                turns_total["leak"] += 1
            # Is the exercise it now shows about the competence it was assigned? (next note)
            nxt = onscreen_competence(notes_path, sid)
            if nxt and trailing_asks(body):
                cn = by_id.get(nxt.get("id"))
                sig = (cn.get("signals") or [t2 for t2 in cn["tags"] if not t2.startswith("#")]) if cn else []
                tail_ = exercise_tail(body)
                if cn and not cn["words"] and sig:
                    turns_total["follow_seen"] += 1
                    turns_total["follow_ok"] += 1 if (has_signal(sig, tail_) or has_signal([cn["name"]], tail_)) else 0
                elif cn and cn["words"]:
                    turns_total["vocab_tag_seen"] += 1
                    turns_total["vocab_tag_ok"] += 1 if vocab_card_on_list(cn["words"], tail_) else 0
            print(f"  {label} {n + 1}/{count} [{cid or '—'}] «{answer}» ({'bé' if ok else 'malament'}, {how})"
                  f" → {time.time() - t:.0f}s" + (f" · nota {score}/10" if score is not None else ""))
            reply = body
            if CLOSING.search(body):
                break
        answer_idx = set(range(1, len(asked_fps)))
        rc = classify_repeats(asked_fps, [label] * len(asked_fps), answer_idx, known_idx)
        for i, f in rc["same"]:
            repeat_findings.append(f"dia {day} {label} torn {i}: «{f}» ja contestat en aquesta mateixa pràctica")

    def trailing_asks(text: str) -> bool:
        return bool(re.search(r"(?m)^#{1,6} ", text or "")) and "?" in exercise_tail(text) or \
            bool(re.search(r"(?i)type your answer|escriu|answer:", exercise_tail(text)))

    for day in range(1, ndays + 1):
        if day > 1:
            wait_quiet(prof_dir)
            p = subprocess.run([sys.executable, str(REPO / "scripts" / "flowed-advance-day.py"),
                                prof_dir.name, "--dir", str(prof_dir), "--days", "1", "--keep-records"],
                               capture_output=True, text=True)
            if p.returncode != 0:
                rep.check(False, f"dia {day}: el rellotge avança", (p.stderr or p.stdout).strip()[-120:])
                break
        today = date.today().isoformat()
        print(f"\n--- dia {day} ({today}) ---")
        # Mix
        sid = cli.new_session()
        sids.add(sid)
        t0 = time.time()
        greeting = tutor_text(cli.command(sid, "math-learn"))
        if day == 1 and not greeting.strip() and time.time() - t0 < 3:
            print("\n❌ el tutor no ha dit res i ha trigat 0s: el model no respon.", file=sys.stderr)
            return 2
        first = tutor_text(cli.say(sid, "6"))          # 🎲 Surprise me!
        transcript.append(f"# dia {day} · {today} · Mix · sessió {sid}\n\n## /math-learn\n\n{greeting}\n\n## «6»\n\n{first}")
        answer_turns(sid, first, args.answers, day, "Mix")
        # Vocabulary
        if args.vocab > 0:
            vsid = cli.new_session()
            sids.add(vsid)
            vfirst = tutor_text(cli.command(vsid, "math-vocab"))
            transcript.append(f"## dia {day} · Vocabulary · sessió {vsid}\n\n{vfirst}")
            answer_turns(vsid, vfirst, args.vocab, day, "Vocab")

        wait_quiet(prof_dir)
        # What the server said and did, per day, next to what the learner saw: the note each
        # turn carried (with the competence assigned) and every guard event. Without them a red
        # "el servidor assigna…" is a number nobody can trace back.
        day_sids = {sid} | ({vsid} if args.vocab > 0 else set())
        for label, fpath, keep in (("notes del servidor al tutor", notes_path, ("command", "answer", "competence", "note")),
                                   ("guard del servidor", guards_path, ("note", "text"))):
            rows_ = []
            if fpath.exists():
                for line in fpath.read_text().splitlines():
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if obj.get("session") in day_sids:
                        rows_.append("- " + json.dumps({k: (str(v)[:260] if k in ("note", "text") else v)
                                                        for k, v in obj.items() if k in keep},
                                                       ensure_ascii=False))
            transcript.append(f"## dia {day} · {label}\n\n" + ("\n".join(rows_) or "(res)"))
        path = cu.rebuild_path(prof_dir, cur, save=True)
        rows = cu.summarize(cur, path, today)
        prog = cu.progress(rows)
        tg = path["tagging"]
        states: dict[str, int] = {}
        for r in rows:
            states[r["state"]] = states.get(r["state"], 0) + 1
        day_recs = [r for r in cu.read_records(prof_dir)
                    if datetime_day(r) == today]
        table.append(f"  dia {day}: respostes {len(day_recs):>2} · %{prog['pct']:>5.1f} · "
                     f"{', '.join(f'{k} {v}' for k, v in sorted(states.items()) if k != 'unseen') or '—'}"
                     f" · assignades {tg['tagged']}/{tg['records']}")
        rep.check(len(day_recs) >= max(1, (args.answers + args.vocab) // 2),
                  f"dia {day}: les respostes queden com a registres", f"{len(day_recs)} de {args.answers + args.vocab}")
        if day in (1, 3) or day == ndays:
            print("\n" + cu.render_report(cur, path, today))

    print("\n=== els dies ===")
    print("\n".join(table))
    print("\ncompetències en l'ordre en què el servidor les ha anat assignant:\n  " + " → ".join(order_seen))

    # ---- verdict --------------------------------------------------------------------
    path = cu.rebuild_path(prof_dir, cur, save=True)
    tg = path["tagging"]
    t = turns_total
    pct = lambda a, b: f"{a} de {b}"
    rep.check(t["asked"] > 0 and t["assigned"] >= 0.9 * t["asked"],
              "el servidor assigna una competència a cada exercici", pct(t["assigned"], t["asked"]))
    rep.check(t["follow_seen"] == 0 or t["follow_ok"] >= 0.7 * t["follow_seen"],
              "el tutor fa l'exercici de la competència assignada (gramàtica i funcions)",
              pct(t["follow_ok"], t["follow_seen"]))
    rep.check(t["leak"] == 0, "el tutor no diu res de la nota del currículum", f"{t['leak']} torns")
    rep.check(t["graded"] >= 0.9 * max(1, t["asked"] - 1), "el tutor qualifica cada resposta", pct(t["graded"], t["asked"]))
    rep.check(tg["records"] > 0 and tg["tagged"] >= 0.7 * tg["records"],
              "les respostes queden assignades a una competència", f"{tg['tagged']} de {tg['records']}"
              + ("" if tg["tagged"] >= 0.7 * max(1, tg["records"]) else f" · sense assignar: {tg['how']}"))
    rep.check(t["verdict_seen"] == 0 or t["verdict_ok"] >= 0.85 * t["verdict_seen"],
              "el tutor puntua com toca el vocabulari (bé ≥ 8, malament < 8)", pct(t["verdict_ok"], t["verdict_seen"]))
    rep.check(len(order_seen) >= 3, "el camí avança per més d'una competència", f"{len(order_seen)} tornades de competència")
    rep.check(t["vocab_tag_seen"] == 0 or t["vocab_tag_ok"] >= 0.7 * t["vocab_tag_seen"],
              "el tutor fa l'exercici de vocabulari amb les paraules de la competència assignada",
              pct(t["vocab_tag_ok"], t["vocab_tag_seen"]))
    rep.check(not repeat_findings, "cap exercici ja contestat es repeteix dins la mateixa pràctica (curriculum)",
              repeat_findings[0] if repeat_findings else "")
    rep.check(not marker_score_mismatches, "el marcador (🟢/🔴/✅/❌) concorda amb la nota (curriculum)",
              marker_score_mismatches[0] if marker_score_mismatches else "")
    rep.check(not vocab_direction_findings, "el vocabulari no demana traduir una paraula al seu propi idioma",
              vocab_direction_findings[0] if vocab_direction_findings else "")
    rep.check(not marker_structure_findings, "el marcador (paraula/frase) concorda amb la resposta esperada",
              marker_structure_findings[0] if marker_structure_findings else "")
    for label_, findings_ in (("exercicis repetits", repeat_findings), ("marcador/nota", marker_score_mismatches),
                              ("direcció vocabulari", vocab_direction_findings),
                              ("marcador/estructura", marker_structure_findings)):
        if len(findings_) > 1:
            print(f"\n  {label_} — {len(findings_)} casos:")
            for f in findings_[:8]:
                print(f"    · {f}")
    day1 = (date.today() - timedelta(days=ndays - 1)).isoformat()
    first_pct = cu.progress(cu.summarize(cur, path, day1))["pct"]
    last_pct = cu.progress(cu.summarize(cur, path, date.today().isoformat()))["pct"]
    rep.check(last_pct > first_pct, "la barra es mou (final del dia 1 → avui)", f"{first_pct:.1f}% → {last_pct:.1f}%")
    # informative
    print(f"\n  tipus d'assignació: {kinds_seen}")
    if t["gram_seen"]:
        print(f"  informatiu: el tutor coincideix amb la intenció de l'alumne en gramàtica {t['gram_ok']} de {t['gram_seen']} "
              f"(el model d'alumne també s'equivoca; no és cap verdict)")
    if llm_ok["fail"]:
        print(f"  ⚠ el model de l'alumne no ha respost {llm_ok['fail']} de {llm_ok['n']} cops ({args.student_url}): "
              f"aquestes respostes són «no ho sé»")
    print("\n" + cu.render_report(cur, path, date.today().isoformat(), admin=True))
    if args.transcript:
        Path(args.transcript).expanduser().write_text(
            f"# Curriculum — {prof_dir.name}\n\n" + "\n\n---\n\n".join(transcript), encoding="utf-8")
        print(f"\ntranscripció: {args.transcript}")
    fired = 0
    if guards_path.exists():
        for line in guards_path.read_text().splitlines():
            try:
                g = json.loads(line)
            except ValueError:
                continue
            if g.get("session") in sids and not str(g.get("note", "")).strip().startswith("rewritten"):
                fired += 1
    rep.guards = fired
    kinds: dict[str, int] = {}
    if guards_path.exists():
        for line in guards_path.read_text().splitlines():
            try:
                g = json.loads(line)
            except ValueError:
                continue
            if g.get("session") in sids and not str(g.get("note", "")).strip().startswith("rewritten"):
                k = re.sub(r'"[^"]*"', '"…"', str(g.get("note", "")))[:70]
                kinds[k] = kinds.get(k, 0) + 1
    if kinds:
        print("\n  guards per tipus:")
        for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]):
            print(f"    {n:>3}× {k}")
    if not finish:
        return rep
    if quiet:
        bad = [lbl for ok, lbl, _ in rep.rows if not ok]
        print(f"  → {len(rep.rows) - len(bad)}/{len(rep.rows)} bé"
              + (f" · falla: {', '.join(bad)}" if bad else "") + f" · guard {rep.guards}×")
        return rep
    rep.render()
    return rep


# ---- the "ladder" scenario: A0 → A1 → level test → cut → A2, with the real tutor -------------
#
# The whole course machinery on the running app, in five steps:
#   A  the A1 course from zero: real days with the real tutor (what the curriculum scenario measures);
#   B  the rest of the A1 history is made up (a simulated learner's answers, written as records
#      in the past — it cannot be lived in an afternoon) until the level test opens;
#   C  the level test, run by the server without the tutor: the answers come from the curriculum's
#      own checks (`--test-mode pass`) or are all wrong (`fail`: the course must NOT close);
#   D  the cut: certificate, profile level, archived course, notice, empty A2 path;
#   E  real days of the A2 course with the real tutor: only the new records count.
LEVEL_Q = re.compile(r"\*\*(?:Complete the sentence:|Correct the sentence:|Which word means:)\*\* (.*?)\n\n\*\*Type your answer", re.S)


def run_ladder(args, cli, prof_dir: Path, rep: "Report", quiet: bool):
    import argparse as _ap
    from datetime import datetime, time as _time
    if not RESETTABLE.match(prof_dir.name):
        print(f"❌ l'escenari ladder només corre en perfils de proves, no en {prof_dir.name}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(REPO / "hooks"))
    cu = _load_module("math_curriculum", "hooks/curriculum.py")
    sim = _load_module("math_sim_path", "scripts/flowed-sim-path.py")
    mode = getattr(args, "test_mode", "pass")
    today = date.today().isoformat()

    print("\n=== A · curs A1 des de zero, amb el tutor real ===")
    a1 = _ap.Namespace(**vars(args))
    a1.course, a1.target_level = "A1", "A2"          # the goal is A2: the ladder starts at A1
    r = run_curriculum(a1, cli, prof_dir, rep, quiet=True, setup=True, finish=False)
    if r == 2:
        return 2
    guards = rep.guards
    cf = cu.find_curriculum(REPO, prof_dir)
    cur = cu.load_curriculum(cf) if cf else None
    if not rep.check(cur is not None and cur["meta"].get("level") == "A1", "el curs actiu és A1",
                     cf.name if cf else "cap curriculum"):
        return rep
    by_id = {c["id"]: c for c in cur["competencies"]}

    print("\n=== B · la resta de l'historial d'A1 (alumne simulat, en el passat) ===")
    # Es fa créixer dia a dia contra l'estat REAL fusionat (fase A + el que porti fet la
    # B), no una simulació aïllada: si no, "a punt" segons el simulador sol pot no coincidir
    # amb "a punt" un cop fusionat amb la fase A (mesurat 2026-09-22: 176 respostes/73%,
    # "pending"; calia una mica més perquè totes les core arribessin a "practicing").
    n_real = max(2, args.days)
    last_day = date.today() - timedelta(days=n_real)
    max_days, k = 400, 0
    out_lines: list[str] = []
    student = sim.Student(args.student, args.seed, cur)
    ready, virt, days_used = False, last_day - timedelta(days=max_days), 0
    while virt < last_day and k < max_days:
        rows_now = cu.summarize(cur, cu.rebuild_path(prof_dir, cur, save=False), virt.isoformat())
        if cu.checkpoint_ready(rows_now, cu.CFG, cur):
            ready = True
            break
        live_path = cu.load_path(prof_dir, cur)
        actives = cu.active_competences(rows_now, live_path)
        pool = list(cu.review_pool(rows_now))
        maint = cu.due_maintenance(cur, live_path, virt.isoformat())[:sim.MAINTENANCE]
        plan: list[str] = []
        for cid in actives:
            plan += [cid] * cu.quota(by_id[cid]["depth"], "new")
        for cid in pool:
            room = sim.PER_DAY - len(plan) - len(maint)
            if room <= 0:
                break
            plan += [cid] * min(room, cu.quota(by_id[cid]["depth"], "review"))
        plan += maint
        filler = (actives + pool) or [r["id"] for r in rows_now if r["core"]][:1]
        i = 0
        while len(plan) < sim.PER_DAY:
            plan.append(filler[i % len(filler)])
            i += 1
        plan = plan[:sim.PER_DAY]
        ts0 = int(datetime.combine(virt, _time(12, 0)).timestamp() * 1000)
        for cid in plan:
            ok = student.answer(cid, virt)
            out_lines.append(json.dumps({
                "record_id": f"ladder-{k}", "ts": ts0 + k, "score": 9 if ok else 3, "competency": cid,
                "skill": "vocabulary" if by_id[cid]["words"] else "grammar", "session": "ladder-synthetic"}))
            k += 1
        rdir = prof_dir / ".records"
        rdir.mkdir(exist_ok=True)
        (rdir / "ladder-synthetic.jsonl").write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        virt += timedelta(days=1)
        days_used += 1
    rep.check(ready, "l'alumne simulat arriba a punt per a la prova (estat real fusionat)",
              f"{k} respostes" if ready else f"no en {max_days} dies ({args.student})")
    path = cu.rebuild_path(prof_dir, cur, save=True)
    rows = cu.summarize(cur, path, today)
    ready = cu.checkpoint_ready(rows, cu.CFG, cur)
    view = (cli._call("/api/math/path") or {}).get("data") or {}
    print(f"  {len(out_lines)} respostes sintètiques en {days_used} dies · barra {cu.progress(rows)['pct']:.0f}% · "
          f"prova: {view.get('checkpoint')}")
    if not rep.check(ready and view.get("checkpoint") == "ready", "l'app ofereix la prova de nivell",
                     f"servidor: {view.get('checkpoint')} · local: {ready}"):
        return rep
    if getattr(args, "stop_before_test", False):
        print(f"\n=== aturat abans de C: fes la prova tu mateix a la web (perfil {prof_dir.name}) ===")
        return _ladder_finish(rep, quiet)

    print(f"\n=== C · la prova de nivell, feta pel servidor (mode {mode}) ===")
    bank = {k["prompt"]: k for c in cur["competencies"] for k in c["checks"]}
    sid = cli.new_session()
    out = tutor_text(cli.command(sid, "math-checkpoint"))
    print("  " + out.splitlines()[0][:80] if out.strip() else "  (buit)")
    rep.check("Level test" in out and "question 1/" in out, "la prova comença amb la primera pregunta", out[:70])
    asked = 0
    final = ""
    while "## Level test — question" in out and asked < 80:
        m = LEVEL_Q.search(out)
        chk = bank.get(m.group(1).strip()) if m else None
        if mode == "fail" or chk is None:
            ans = "no idea"
        else:
            ans = chk["answer"].split("/")[0].strip()
        asked += 1
        out = tutor_text(cli.say(sid, ans))
        final = out
    print(f"  {asked} preguntes · final: " + (final.strip().splitlines()[-1][:100] if final.strip() else "(buit)"))
    rep.check(asked >= 5 and "Level test finished" in final, "la prova s'acaba amb el resultat",
              f"{asked} preguntes")
    rep.check(not re.search(r"(?i)\bcurriculum\b|learner-path|competency", final), "el missatge de la prova no filtra res intern")
    certs = cu.load_certificates(prof_dir)
    prof = json.loads((prof_dir / "learner-profile.json").read_text(encoding="utf-8")).get("learner", {})

    if mode == "fail":
        print("\n=== D · sense tall: el curs continua ===")
        path = cu.rebuild_path(prof_dir, cur, save=True)
        rep.check("Not yet" in final, "el missatge diu que encara no", final[-90:])
        rep.check(not any(c.get("level") == "A1" for c in certs), "no hi ha cap certificat d'A1", str(certs))
        rep.check(prof.get("current_level") != "A1", "el nivell del perfil no canvia", str(prof.get("current_level")))
        rep.check(len(path.get("checkpoints") or []) == 1 and path["checkpoints"][0].get("result") == "stay",
                  "el camí guarda l'intent (stay)", json.dumps(path.get("checkpoints"))[:120])
        cf2 = cu.find_curriculum(REPO, prof_dir)
        rep.check(cf2 is not None and cf2.name == cf.name, "el curs actiu continua sent A1", cf2.name if cf2 else "?")
        rep.check(not (prof_dir / "checkpoint-run.json").exists(), "no queda cap prova a mig fer")
        v2 = (cli._call("/api/math/path") or {}).get("data") or {}
        rep.check(not v2.get("notice"), "no hi ha cap avís de curs acabat", str(v2.get("notice"))[:80])
        rep.guards = guards
        return _ladder_finish(rep, quiet)

    print("\n=== D · el tall: certificat, arxiu, avís i curs nou ===")
    rep.check("certified" in final, "el missatge diu que el nivell queda certificat", final[-90:])
    rep.check(any(c.get("level") == "A1" and c.get("type") == "checkpoint" for c in certs),
              "certificat d'A1 per la prova", str(certs)[:120])
    rep.check(prof.get("current_level") == "A1", "el nivell del perfil és A1", str(prof.get("current_level")))
    archived = list((prof_dir / "courses").glob("*.json")) if (prof_dir / "courses").is_dir() else []
    rep.check(any("A1" in f.name for f in archived), "el curs A1 queda arxivat", ", ".join(f.name for f in archived) or "cap")
    rep.check(not (prof_dir / "checkpoint-run.json").exists(), "no queda cap prova a mig fer")
    v2 = (cli._call("/api/math/path") or {}).get("data") or {}
    rep.check(v2.get("level") == "A2" and (v2.get("pct") or 0) == 0.0,
              "el camí actiu és A2 i comença a 0%", f"{v2.get('level')} {v2.get('pct')}%")
    notice = v2.get("notice") or {}
    rep.check(bool(notice), "hi ha l'avís de curs acabat", json.dumps(notice, ensure_ascii=False)[:100])
    cli._call("/api/math/path/seen", {}, "POST")
    v3 = (cli._call("/api/math/path") or {}).get("data") or {}
    rep.check(not v3.get("notice"), "l'avís no torna un cop vist")
    rep.check(v3.get("checkpoint") != "ready", "A2 no ofereix la prova de nivell el primer dia", str(v3.get("checkpoint")))
    again = tutor_text(cli.command(cli.new_session(), "math-checkpoint"))
    rep.check("opens when" in again or "level test" in again.lower(), "el botó de la prova a A2 diu que encara no", again[:80])

    print("\n=== E · curs A2 amb el tutor real ===")
    a2 = _ap.Namespace(**vars(args))
    a2.course, a2.days, a2.transcript = "A2", 2, None
    r2 = run_curriculum(a2, cli, prof_dir, rep, quiet=True, setup=False, finish=False)
    if r2 == 2:
        return 2
    rep.guards += guards
    return _ladder_finish(rep, quiet)


def _ladder_finish(rep: "Report", quiet: bool):
    if quiet:
        bad = [lbl for ok, lbl, _ in rep.rows if not ok]
        print(f"  → {len(rep.rows) - len(bad)}/{len(rep.rows)} bé"
              + (f" · falla: {', '.join(bad)}" if bad else "") + f" · guard {rep.guards}×")
        return rep
    rep.render()
    return rep


def datetime_day(rec: dict) -> str:
    from datetime import datetime
    return datetime.fromtimestamp((rec.get("ts") or 0) / 1000).date().isoformat()




def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("profile", nargs="?", default="test-math",
                    help="profile id under the data home (~/.flowmath/)")
    ap.add_argument("--dir", help="explicit profile directory")
    ap.add_argument("--port", type=int, default=4200)
    ap.add_argument("--course", choices=("A1", "A2"), default="A2",
                    help="curriculum: quin curs prova (A2 amb l'A1 certificat per col·locació; A1 des de zero)")
    ap.add_argument("--test-mode", choices=("pass", "fail"), default="pass", dest="test_mode",
                    help="ladder: la prova de nivell es contesta bé (curs tancat, passa a A2) o tot malament "
                         "(el curs ha de continuar)")
    ap.add_argument("--stop-before-test", action="store_true", dest="stop_before_test",
                    help="ladder: para just abans de la prova de nivell (perfil llest, ~70-80%%) perquè la "
                         "facis tu mateix a la web, en lloc que la faci el propi escenari")
    ap.add_argument("--answers", type=int, default=6, help="how many exercises to answer")
    ap.add_argument("--timeout", type=int, default=240, help="seconds per turn")
    ap.add_argument("--transcript", help="write everything the tutor said to this file")
    ap.add_argument("--user", default="opencode", help="basic-auth user (default: opencode)")
    ap.add_argument("--password", help="basic-auth password (default: the profile's .web-password)")
    ap.add_argument("--scenario", choices=("lesson", "go", "steps", "steps2", "facts", "review", "algebra", "reasoning", "problems", "days", "curriculum", "ladder", "language"), default="lesson",
                    help="lesson (WP1.9, per defecte): 🔁 Review amb la cua sembrada (compute/compare/"
                         "steps, la primera de passos fallida a propòsit) + 🎲 Go + 📚 Facts + 🏁 End i la "
                         "persistència · review: només la lliçó · steps: una lliçó només de targetes de "
                         "passos · go: només targetes del banc a pràctica lliure · facts: només el drill "
                         "de fets · algebra (WP1.1-live, perfil m7): lliçó d'àlgebra — forma equivalent "
                         "que val 10, lliscament de signe amb categoria «sign», còpia literal de "
                         "l'enunciat atrapada com a «procedure», targeta de passos en camí v2 i prova "
                         "de nivell Compute:/Steps: per la via CLI · reasoning (WP3.3): 📝 Raonament obert — el tutor planteja una tasca "
                         "d'explicar, l'alumne respon amb un lliscament deliberat i el feedback ha de "
                         "venir amb correccions de la taxonomia matemàtica (rúbrica WP3.1) · "
                         "problems (WP3.2): 📖 Problemes — targeta tancada del banc (enunciat en prosa, "
                         "correcció compute) + problema obert amb el model (task='word-problem', "
                         "registre amb skill «problems») · "
                         "days: N dies seguits (el rellotge avança); l'SM-2 ha de fer tornar el "
                         "que es falla i allunyar el que s'encerta · "
                         "curriculum: N dies d'un alumne simulat A1→A2 en pràctica lliure (Mix + Vocabulary): "
                         "el servidor assigna la competència, el tutor fa l'exercici, l'alumne respon "
                         "(vocabulari amb el banc de paraules, gramàtica amb el model) i es mira el camí")
    ap.add_argument("--days", type=int, default=5,
                    help="escenari days: quants dies seguits (per defecte 5)")
    ap.add_argument("--student", choices=("fast", "steady", "weak"), default="steady",
                    help="escenari curriculum: com aprèn l'alumne simulat (flowed-sim-path.py)")
    ap.add_argument("--seed", type=int, default=1, help="escenari curriculum: llavor de l'alumne simulat")
    ap.add_argument("--vocab", type=int, default=3,
                    help="escenari curriculum: respostes de Vocabulary cada dia (Mix fa --answers)")
    ap.add_argument("--student-url", dest="student_url",
                    default=os.environ.get("FLOWED_STUDENT_URL", "http://127.0.0.1:12322/v1"),
                    help="escenari curriculum: model OpenAI-compatible que respon la gramàtica com a "
                         "alumne (per defecte el llama del 12322; pot ser el mateix que el tutor)")
    ap.add_argument("--repeat", type=int, default=1,
                    help="repetir l'escenari N vegades i donar una TAXA, no una foto. "
                         "Imprescindible per comparar paràmetres de mostreig")
    ap.add_argument("--summary", action="store_true",
                    help="printa el resum agregat encara que sigui una sola execució "
                         "(el sweep el llegeix; sense ell dóna «0 de 0 comprovacions»)")
    ap.add_argument("--reset", action="store_true",
                    help="blank the learning state first (test*/demo*/e2e* profiles only)")
    args = ap.parse_args()
    if args.repeat <= 1 and not args.summary:
        out = run(args)
        return out if isinstance(out, int) else (1 if any(not r[0] for r in out.rows) else 0)

    # One run proves nothing about repetition: the model is sampled, and the
    # same settings give a different answer each time. What a parameter change
    # has to be judged on is a rate — how OFTEN the guard had to step in, how
    # OFTEN a check failed — not a single screenshot.
    prof_dir = Path(args.dir).expanduser() if args.dir else profiles_root() / args.profile
    if not RESETTABLE.match(prof_dir.name):
        print("❌ --repeat només en perfils de proves: cada execució ha de tornar el perfil\n"
              "   al punt de partida, i això no es fa en un perfil real.", file=sys.stderr)
        return 2
    if args.reset:
        print("❌ --reset i --repeat no es combinen: el reset tornaria a córrer a cada volta\n"
              "   i esborraria el punt de partida que s'ha de restaurar. Prepara el perfil una\n"
              "   vegada (--reset o flowed-seed.py) i després llança el --repeat.", file=sys.stderr)
        return 2
    snap = snapshot(prof_dir)

    runs: list[Report] = []
    expected_due: list[str] | None = None
    base_transcript = args.transcript
    for n in range(args.repeat):
        print(f"\n{'=' * 22} execució {n + 1} de {args.repeat} {'=' * 22}")
        if base_transcript:
            args.transcript = numbered_path(base_transcript, n + 1)
        if n:
            waited = wait_quiet(prof_dir)
            restore(prof_dir, snap)
            # A late hook can still land between the two. If the day came back
            # from the dead, wait properly and put it back once more rather than
            # throwing away the four runs that were still to come.
            plan_file = prof_dir / ".daily" / f"lesson-{date.today().isoformat()}.json"
            if plan_file.exists() and (json.loads(plan_file.read_text()).get("done") or 0) > 0:
                print("⚠ el pla d'avui ha reaparegut després de restaurar; espero i ho repeteixo")
                waited += wait_quiet(prof_dir, settle=5.0)
                restore(prof_dir, snap)
            print(f"perfil tornat al punt de partida (persistència tancada en {waited:.1f}s)")
        due = due_now(prof_dir)
        if expected_due is None:
            expected_due = due
            print(f"per repassar en començar: {len(due)} → {due}")
        elif due == expected_due:
            print(f"per repassar en començar: {len(due)} (igual que l'execució 1)")
        else:
            print(f"⚠ PUNT DE PARTIDA DIFERENT: {len(due)} per repassar, no "
                  f"{len(expected_due)} → {due}\n"
                  "   aquesta execució no és comparable amb les altres: sense res per "
                  "repassar el tutor pren el camí de «primera lliçó» i cap registre pot "
                  "portar item_id.")
        out = run(args, quiet=True)
        if isinstance(out, int):
            # An aborted run must not throw away the ones that worked.
            print(f"\n⚠ execució {n + 1} interrompuda; resumeixo les {len(runs)} anteriors",
                  file=sys.stderr)
            break
        runs.append(out)
    if not runs:
        return 2
    # And once more at the end, so whoever reads the profile after this script
    # (the sweep's "després") reads a settled one.
    wait_quiet(prof_dir)

    print(f"\n=== resum de {len(runs)} execucions ===")
    labels = [lbl for _, lbl, _ in runs[0].rows]
    for lbl in labels:
        bad_rows = [(d or "") for r in runs for ok, l, d in r.rows if l == lbl and not ok]
        fails = len(bad_rows)
        mark = "✅" if fails == 0 else ("⚠️ " if fails < len(runs) else "❌")
        print(f"  {mark} {lbl}" + (f"  — falla {fails}/{len(runs)}" if fails else ""))
        # The detail, not just the count: a summary that says only "3/3" sends
        # someone back to the raw logs to find out what the numbers were, and
        # that is where an afternoon goes.
        for d in dict.fromkeys(x for x in bad_rows if x):
            print(f"        {d}")
    ungraded = sum(1 for r in runs if is_ungraded(r.rows))
    print(f"\n  execucions sense cap qualificació: {ungraded} de {len(runs)}")
    cross_total = sum(n[0] for r in runs for n in r.notes)
    again_total = sum(n[1] for r in runs for n in r.notes)
    print(f"\n  informatiu (no és cap verdict): {cross_total} exercici(s) ja contestat(s) "
          f"tornat(s) a treure en una altra pràctica; {again_total} sense contestar tornat(s) "
          f"a mostrar (correcte)")
    total_guards = sum(r.guards for r in runs)
    print(f"\n  el guard del servidor ha actuat {total_guards} cop(s) en total"
          f"  ({total_guards / len(runs):.1f} per execució)")
    bad = [lbl for lbl in labels
           if any(not ok for r in runs for ok, l, _ in r.rows if l == lbl)]
    print(f"  {len(bad)} de {len(labels)} comprovacions han fallat alguna vegada")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
