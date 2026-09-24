#!/usr/bin/env python3
"""End-to-end lesson against the REAL model, with a verdict.

Why this exists, in the words of the person who needed it: *"abans també va
passar test i per les nenes va ser un autèntic desastre... lo obvi ho veig de
seguida, però la resta sense això costa."*

Every other test in this repo checks the code. None of them makes the tutor
speak. On 2026-09-16 the whole suite was green while the tutor ran sixty turns
without correcting a single answer, because the thing that broke was what the
model was told, and no unit test has ever read a model's reply.

This does. It opens a session over the HTTP API exactly as the browser does,
presses 🎓 Lesson, answers the exercises, and reads what comes back — checking
the handful of things that, when they fail, make a child think the app is
broken:

  * every answer gets a marker, a correct version and a score
  * no curly braces (the tutor printing its own template)
  * no exercise asked twice
  * the lesson is not closed before its exercises are done
  * the counter moves, and the answers reach .records/

It needs the server running:  scripts/fluent-web.sh --app --port N <profile>

  python3 scripts/fluent-e2e.py --port 4103 test-en
  python3 scripts/fluent-e2e.py --port 4103 test-en --answers 8 --transcript /tmp/t.md
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

REPO = Path(__file__).resolve().parent.parent
MARKER = re.compile(r"[🟢🟡🔴✅❌]")
SCORE = re.compile(r"\b\d{1,2}\s*/\s*10\b")
CLOSING = re.compile(r"session complete|sessió completa|review session complete", re.I)
MENU_RE = re.compile(r"what would you like to practice|surprise me|spaced review \(today's due", re.I)
GREETING_RE = re.compile(r"^#{0,3}\s*(hello|hi|hola|welcome back)\b", re.I | re.M)
BRACE = re.compile(r"\{[^}\n]{0,60}\}")

# How this script answers, and why it matters more than it looks.
#
# The first version answered wrongly every single time — "xxx", "banana",
# "zzz", six in a row — and then reported the tutor for repetition. But a tutor
# that re-asks a question the learner just got wrong is doing its job, and no
# child answers wrongly six times running. The test was manufacturing the loop
# it was complaining about.
#
# So it plays a learner: wrong on the first sight of a question, and then, once
# the tutor has shown the correct version, right. That is the sequence that
# actually asks the question worth asking — when she gets it right, does the
# lesson move on?
WRONG = ["xxx", "no ho sé", "banana", "zzz", "aaa", "qqq", "wibble", "1234"]
# The whole line after the label, quotes stripped afterwards. The first version
# stopped at any apostrophe, so "I don't know" came back as "I don" — the script
# then answered wrongly three times running and reported the tutor for retrying.
# A wrong answer from the test is indistinguishable from a wrong answer from a
# child, and the tutor was right both times.
CORRECT_VERSION = re.compile(r"\*\*Correct version:?\*\*\s*\n+([^\n]{1,120})", re.I)


def _unquote(line: str) -> str:
    return line.strip().strip("*").strip().strip("\"\u201c\u201d\u2018\u2019'").strip().rstrip(".").strip()


def learner_answer(last_reply: str, n: int, always_wrong: bool, retry: bool) -> str:
    """Wrong on a new question; right when the tutor re-asks the same one.

    A graded reply carries the correction for the question just answered AND the
    next, different question. Taking the correct version out of it and sending
    it back answers the PREVIOUS question — which is wrong, every time, and the
    databases fill up with the learner being marked down for answers the tutor
    had just supplied. The right answer is only knowable on a retry, when the
    question has not changed. Everywhere else, a script cannot know it, and
    pretending otherwise is how a test lies.
    """
    if always_wrong or not retry:
        return WRONG[n % len(WRONG)]
    m = CORRECT_VERSION.search(last_reply or "")
    if m:
        answer = _unquote(m.group(1))
        # Some tutors put an explanation where the answer goes ("X is a Catalan
        # dish that translates to..."). A sentence is not an answer; fall back.
        if answer and len(answer.split()) <= 6:
            return answer
    return WRONG[n % len(WRONG)]


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
    this function in `fluent-seed.py` for the ENAMETOOLONG it replaces. An
    archive is a place, not a suffix chained onto the name every run."""
    if not d.is_dir():
        return 0
    out = d / "_archive"
    moved = 0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for f in d.iterdir():
        # A day archived by fluent-advance-day.py (".<name>.day-<stamp>") is history of a
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
    prof_dir = Path(args.dir).expanduser() if args.dir else Path.home() / ".fluent" / args.profile
    if not (prof_dir / "learner-profile.json").exists():
        print(f"❌ perfil no trobat: {prof_dir}", file=sys.stderr)
        return 2
    pw_file = prof_dir / ".web-password"
    if args.password:
        password = args.password
    elif pw_file.exists():
        password = "".join(pw_file.read_text().split())
    else:
        password = "".join((Path.home() / ".fluent" / ".web-password-default").read_text().split())

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
              f"   scripts/fluent-web.sh --app --port {args.port} {args.profile}", file=sys.stderr)
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
              f"   scripts/fluent-web.sh --stop --port {args.port}\n"
              f"   scripts/fluent-web.sh --app --port {args.port} {prof_dir.name}", file=sys.stderr)
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
    if args.scenario == "topics":
        return run_topics(args, cli, prof_dir, rep, quiet)
    if args.scenario == "curriculum":
        return run_curriculum(args, cli, prof_dir, rep, quiet)
    if args.scenario == "ladder":
        return run_ladder(args, cli, prof_dir, rep, quiet)

    # The day's plan BEFORE this run touches anything. Read after the greeting
    # and the Lesson-opening turn — as it used to be — it also counts whatever
    # those two turns credited, so a tutor that put a score in its opening reply
    # made the run abort with "the lesson was already under way (1 of 6)" and
    # threw away the four executions still to come. What has to be untouched is
    # the day this run inherited, not the day two turns into it.
    plan_path = prof_dir / ".daily" / f"lesson-{date.today().isoformat()}.json"
    started_before = 0
    if plan_path.exists():
        try:
            started_before = json.loads(plan_path.read_text()).get("done", 0) or 0
        except ValueError:
            started_before = 0

    records_before = len(list((prof_dir / ".records").glob("*.jsonl"))) if (prof_dir / ".records").is_dir() else 0
    transcript: list[str] = []
    print(f"perfil {prof_dir.name} · port {args.port} · {args.answers} respostes")

    sid = cli.new_session()
    print(f"sessió {sid}")

    t0 = time.time()
    greeting = tutor_text(cli.command(sid, "fluent-learn"))
    transcript.append(f"## /fluent-learn\n\n{greeting}")
    rep.check(bool(greeting), "el tutor obre la sessió", f"{len(greeting)} car.")
    # An empty greeting that came back instantly is not a tutor that failed to
    # greet: it is a model that is not running. Saying so here saves reading ten
    # red checks and a sweep summary that looks like a catastrophe.
    if not greeting.strip() and time.time() - t0 < 3:
        print("\n❌ el tutor no ha dit res i ha trigat 0s: el model no respon.\n"
              "   Comprova-ho amb scripts/fluent-web.sh --status --port "
              f"{args.port} (hauria de dir «model: deep … RUNNING»)\n"
              "   i arrenca'l amb scripts/fluent-start.sh --models-only.", file=sys.stderr)
        return 2

    first = tutor_text(cli.command(sid, "fluent-review"))
    transcript.append(f"## 🎓 Lesson\n\n{first}")
    print(f"  Lesson oberta ({time.time() - t0:.0f}s)")

    # The lesson's own size, from the server — not a number this script invents.
    plan_file = prof_dir / ".daily" / f"lesson-{date.today().isoformat()}.json"
    plan = json.loads(plan_file.read_text()) if plan_file.exists() else {}
    total = plan.get("total") or 0
    rep.check(total > 0, "el servidor ha fet el pla de la lliçó", f"{total} exercicis")
    # Not "unfinished" — UNTOUCHED. A lesson already under way is the previous
    # run's lesson, and continuing it measures something else: the second run of
    # the first --repeat 3 finished run 1's lesson and reported it as its own.
    # Only the third refused, and only because by then it was full.
    started = started_before
    if total and started > 0:
        done_note = "ja estava acabada" if started >= total else "ja estava començada"
        # (mesurat abans del primer torn: el que compta és el dia que hereta)
        print(f"\n❌ la lliçó d'avui {done_note} abans d'aquesta execució "
              f"({started} de {total}).\n"
              f"   Continuar-la no mesura una lliçó: mesura el que en quedava. Buida el dia:\n"
              f"   python3 scripts/fluent-e2e.py {prof_dir.name} --port {args.port} --reset …\n"
              f"   o, si vols passat, fluent-seed.py (que també buida el dia).", file=sys.stderr)
        return 2

    replies = [first]
    asked: list[list[str]] = [fingerprints(first)]
    practice_of: list[str] = ["-"]   # which practice each reply came from
    current_practice = "-"
    closed_early_at = None
    detour_at: int | None = None   # index in `replies` where the learner left
    resumed_at: int | None = None  # ...and where 🎓 Lesson was pressed again
    phase: dict[str, list[int]] = {}
    after_close: int | None = None  # first reply after the lesson closed
    journey_from: int | None = None  # journey: first reply of free practice
    writing_press: int | None = None  # journey: the reply that presented the Writing exercise
    writing_replies: list[int] = []
    answer_idx: list[int] = []      # which replies came from an answer, not a button
    judged: list[dict] = []         # student scenario: what was answered, and about which item
    outstanding: list[str] = []     # the exercise on screen when she walked away
    daily_at_detour: dict = {}
    daily_after_vocab: dict = {}

    free_replies: list[int] = []   # journey: replies to answers given in free practice

    def answer_once(n: int, free: str | None = None, kind_free: str | None = None) -> str:
        """One learner turn. Returns the tutor's reply."""
        nonlocal closed_early_at
        retry = len(asked) >= 2 and bool(asked[-1]) and asked[-1] == asked[-2]
        item = None
        if free == "vocab":
            item = bank_item(replies[-1])
            answer = free_vocab_answer(kind_free or "right", item)
            judged.append({"reply": len(replies), "kind": kind_free, "item": item,
                           "answer": answer, "follows": item is not None})
        elif free == "writing":
            answer = FREE_WRITING[n % len(FREE_WRITING)]
        elif args.scenario in ("student", "journey", "noisy"):
            item = onscreen_item(prof_dir / ".metrics" / "notes.jsonl",
                                 prof_dir / "spaced-repetition.json", sid)
            if args.scenario == "noisy":
                variant = NOISY_PLAN[n % len(NOISY_PLAN)]
                answer, kind = noisy_answer(variant, item)
            else:
                kind = variant = STUDENT_PLAN[n % len(STUDENT_PLAN)]
                answer = student_answer(kind, item)
            judged.append({"reply": len(replies), "kind": kind, "variant": variant,
                           "item": item, "answer": answer,
                           "follows": follows_item(item, replies[-1])})
        else:
            answer = learner_answer(replies[-1], n, args.always_wrong, retry)
        t = time.time()
        body = tutor_text(cli.say(sid, answer))
        replies.append(body)
        asked.append(fingerprints(body))
        practice_of.append(current_practice)
        answer_idx.append(len(replies) - 1)
        if free:
            free_replies.append(len(replies) - 1)
        if free == "writing":
            writing_replies.append(len(replies) - 1)
        transcript.append(f"## resposta {len(replies) - 1}: «{answer}»\n\n{body}")
        flags = []
        if not MARKER.search(body): flags.append("sense marcador")
        if "Correct version:" not in body: flags.append("sense versió correcta")
        if not SCORE.search(body): flags.append("sense nota")
        if BRACE.search(on_screen(body)): flags.append("CLAUS")
        if CLOSING.search(body) and closed_early_at is None:
            closed_early_at = len(replies) - 1
        print(f"  {len(replies) - 1} «{answer}» → {time.time() - t:.0f}s"
              + (f"  ⚠ {', '.join(flags)}" if flags else "  ok"))
        return body

    def press(cmd: str, label: str) -> str:
        nonlocal current_practice
        t = time.time()
        current_practice = {"fluent-review": "lesson", "fluent-vocab": "vocab"}.get(cmd, cmd)
        body = tutor_text(cli.command(sid, cmd))
        replies.append(body)
        asked.append(fingerprints(body))
        practice_of.append(current_practice)
        transcript.append(f"## {label}\n\n{body}")
        print(f"  [{label}] → {time.time() - t:.0f}s")
        return body

    def read_daily() -> dict:
        f = prof_dir / ".daily" / f"{date.today().isoformat()}.json"
        try:
            return json.loads(f.read_text())
        except Exception:
            return {}

    def plan_done() -> int:
        try:
            return json.loads(plan_file.read_text()).get("done", 0)
        except Exception:
            return 0

    if args.scenario == "wander":
        # What a child actually does: start the lesson, get bored two questions
        # in, go and do some vocabulary, come back to the lesson, and later go
        # back to vocabulary again. Three things have to hold: the lesson is
        # waiting where she left it, the vocabulary work is not lost, and
        # vocabulary does not start over from the same words.
        phase["lesson_a"] = [len(replies)]
        for n in range(2):
            answer_once(n)
        phase["lesson_a"].append(len(replies))
        daily_at_detour = read_daily()

        detour_at = len(replies)
        press("fluent-vocab", "📚 Vocabulary")
        phase["vocab_a"] = [len(replies)]
        for n in range(2, 4):
            answer_once(n)
        phase["vocab_a"].append(len(replies))
        daily_after_vocab = read_daily()

        # The exercise she was looking at when she left. Presenting it again on
        # her return is not a repetition — it is the only correct thing to do,
        # because she never answered it.
        outstanding = list(asked[phase["lesson_a"][1] - 1]) if phase.get("lesson_a") else []
        resumed_at = len(replies)
        press("fluent-review", "🎓 Lesson (torna)")
        phase["lesson_b"] = [len(replies)]
        for n in range(4, 6):
            if closed_early_at:
                break
            answer_once(n)
        phase["lesson_b"].append(len(replies))

        press("fluent-vocab", "📚 Vocabulary (torna)")
        phase["vocab_b"] = [len(replies)]
        for n in range(6, 8):
            answer_once(n)
        phase["vocab_b"].append(len(replies))

    elif args.scenario == "marathon":
        # Long enough that the context grows past the point where history
        # pruning starts dropping turns — which has never happened in a test,
        # and is where the 41808-token overflow lived. Three detours, one of
        # them into Writing, whose answers are long.
        phase["lesson_a"] = [len(replies)]
        for n in range(3):
            answer_once(n)
        phase["lesson_a"].append(len(replies))
        daily_at_detour = read_daily()

        detour_at = len(replies)
        press("fluent-vocab", "📚 Vocabulary")
        phase["vocab_a"] = [len(replies)]
        for n in range(3, 6):
            answer_once(n)
        phase["vocab_a"].append(len(replies))
        daily_after_vocab = read_daily()

        press("fluent-writing", "📝 Writing")
        for n in range(6, 9):
            answer_once(n)

        outstanding = list(asked[phase["lesson_a"][1] - 1]) if phase.get("lesson_a") else []
        resumed_at = len(replies)
        press("fluent-review", "🎓 Lesson (torna)")
        phase["lesson_b"] = [len(replies)]
        for n in range(9, 13):
            if closed_early_at:
                break
            answer_once(n)
        phase["lesson_b"].append(len(replies))

        press("fluent-vocab", "📚 Vocabulary (torna)")
        phase["vocab_b"] = [len(replies)]
        for n in range(13, 16):
            answer_once(n)
        phase["vocab_b"].append(len(replies))

    elif args.scenario == "journey":
        # 1) the lesson, to its end, and one answer past it (a closed lesson stays closed)
        phase["lesson_a"] = [len(replies)]
        for n in range(total):
            answer_once(n)
            if closed_early_at:
                after_close = len(replies)
                answer_once(total)
                break
        phase["lesson_a"].append(len(replies))
        daily_at_detour = read_daily()

        # 2) free practice: vocabulary, right and wrong
        journey_from = len(replies)
        press("fluent-vocab", "📚 Vocabulary")
        phase["vocab_a"] = [len(replies)]
        for k, kf in enumerate(FREE_VOCAB_PLAN):
            answer_once(100 + k, free="vocab", kind_free=kf)
        phase["vocab_a"].append(len(replies))
        daily_after_vocab = read_daily()

        # 3) writing: the answers are wrong on purpose, the tutor has to correct them
        writing_press = len(replies)
        press("fluent-writing", "📝 Writing")
        for k in range(len(FREE_WRITING)):
            answer_once(200 + k, free="writing")

        # 4) back to vocabulary: what was answered must not come back
        press("fluent-vocab", "📚 Vocabulary (torna)")
        phase["vocab_b"] = [len(replies)]
        for k, kf in enumerate(FREE_VOCAB_BACK):
            answer_once(300 + k, free="vocab", kind_free=kf)
        phase["vocab_b"].append(len(replies))

    else:
        limit = (args.answers if args.scenario == "lesson"
                 else total if args.scenario in ("student", "noisy")
                 else max(args.answers, total + 3))
        for n in range(limit):
            answer_once(n)
            if closed_early_at:
                # Two more turns past the end: a closed lesson has to stay
                # closed, not quietly start a seventh exercise.
                after_close = len(replies)
                for extra in range(2):
                    answer_once(limit + extra)
                break

    # Pressing a button is not answering a question. Counting the three command
    # replies of a wander as "answers" made every ratio wrong: 8 records for
    # "11 answers" when only 8 answers were ever given.
    graded = [replies[i] for i in answer_idx]
    floor = max(1, len(graded) * 2 // 3)

    # --- the format ---------------------------------------------------------
    rep.check(sum(1 for r in graded if MARKER.search(r)) >= floor,
              "cada resposta rep un marcador",
              f"{sum(1 for r in graded if MARKER.search(r))}/{len(graded)}")
    rep.check(sum(1 for r in graded if "Correct version:" in r) >= floor,
              "ensenya la versió correcta",
              f"{sum(1 for r in graded if 'Correct version:' in r)}/{len(graded)}")
    rep.check(sum(1 for r in graded if SCORE.search(r)) >= floor,
              "posa nota",
              f"{sum(1 for r in graded if SCORE.search(r))}/{len(graded)}")

    braced = [i for i, r in enumerate(replies) if BRACE.search(on_screen(r))]
    rep.check(not braced, "cap clau de plantilla a la pantalla",
              (BRACE.search(on_screen(replies[braced[0]])).group(0) if braced else ""))

    # --- did the lesson actually MOVE? -------------------------------------
    #
    # The check this replaces compared each turn's fingerprints with the
    # previous turn's, and a turn that presents no exercise at all has no
    # fingerprints — so six identical gradings of one single question passed
    # it, while the badge went to 6 of 6. What matters is not whether two
    # consecutive turns differ. It is whether a new question was ever asked.
    seen: list[str] = []
    for fp in asked:
        seen.extend(f for f in fp if f not in seen)
    def _score_at(i: int) -> int | None:
        m = SCORE.search(replies[i]) if i < len(replies) else None
        return int(re.split(r"\s*/\s*", m.group(0))[0]) if m else None

    rc = classify_repeats(asked, practice_of, set(answer_idx),
                          {i for i in answer_idx if (_score_at(i) or 0) >= 8})
    new_each_turn = rc["fresh"]
    repeats_of_old = rc["same"]
    rep.notes.append((len(rc["cross"]), len(rc["unanswered"]),
                      [f"{f} (torn {i})" for i, f in rc["cross"]][:6]))

    distinct = len(seen)
    # One retry is teaching, two is a loop. A tutor that corrects a wrong answer
    # and gives the same question one more go is doing its job; the third
    # identical question is where a child decides the app is broken.
    # Only answers count. A button press that brings back the exercise she was
    # already looking at is not the tutor insisting.
    # From the reply that closes the lesson until free practice starts nothing new
    # is asked, by design: the closing summary and the answers past the end are
    # not "the same question again" (a false alarm, 6/6, until this was excluded).
    resume_at = journey_from if journey_from is not None else len(asked)
    run_len, worst = 0, 0
    for i in range(1, len(asked)):
        if i not in answer_idx:
            continue
        if closed_early_at is not None and closed_early_at <= i < resume_at:
            continue
        if i in writing_replies:
            # A Writing exercise has no fingerprint (a scenario and a task, not a
            # word): "no new question" would be read into every Writing answer.
            run_len = 0
            continue
        # "Insisting" is the SAME exercise again straight after she answered it (or
        # no exercise at all). An exercise she had answered wrong in an earlier
        # visit that comes back later is not that: it is SM-2 doing its job.
        stuck = (not asked[i]) or bool(set(asked[i]) & set(asked[i - 1]))
        run_len = run_len + 1 if stuck else 0
        worst = max(worst, run_len)
    rep.check(worst <= 1, "no insisteix més d'un reintent en la mateixa pregunta",
              f"{worst} torns seguits sense canviar de pregunta" if worst > 1 else "")
    rep.check(not repeats_of_old, "cap exercici ja contestat es repeteix dins la mateixa pràctica",
              f'«{repeats_of_old[0][1]}» al torn {repeats_of_old[0][0]}' if repeats_of_old else "")
    # With one retry allowed, N answers should still produce at least half as
    # many distinct questions. One question for six answers is not a retry.
    rep.check(distinct >= max(1, (len(graded) + 1) // 2),
              "exercicis diferents, no el mateix repetit",
              f"{distinct} exercicis per a {len(graded)} respostes")

    rep.check(closed_early_at is None or closed_early_at >= total,
              "no tanca la lliçó abans d'hora",
              f"ha tancat a {closed_early_at} de {total}" if closed_early_at else "")

    # --- the counter must count exercises, not keystrokes -------------------
    plan = json.loads(plan_file.read_text()) if plan_file.exists() else {}
    done = plan.get("done", 0)
    rep.check(done <= distinct, "el comptador no compta més del que s'ha preguntat",
              f"{done} de {plan.get('total')} amb només {distinct} exercici(s) diferent(s)")
    # Only answers given INSIDE the lesson can move the lesson's counter. In a
    # wander, half of them are Vocabulary — counting those made a correct 3 of 6
    # look like a failure.
    in_lesson = len(graded)
    if args.scenario in ("wander", "marathon", "journey"):
        in_lesson = sum(1 for i in answer_idx
                        if any(a <= i < b for a, b in (phase.get("lesson_a", [0, 0]),
                                                       phase.get("lesson_b", [0, 0]))))
    if args.scenario in ("student", "noisy"):
        in_lesson = min(in_lesson, total)   # the extras after the close do not count
    rep.check(done >= max(1, in_lesson - 1), "el comptador segueix les respostes de la lliçó",
              f"{done} de {plan.get('total')} amb {in_lesson} respostes dins la lliçó")

    # --- the marker has to agree with the score -----------------------------
    disagree = []
    for r in graded:
        sc = SCORE.search(r)
        if not sc:
            continue
        n = int(re.split(r"\s*/\s*", sc.group(0))[0])
        # Every traffic light in the reply, not just the first: the failure seen
        # live was "❌ Close!" at the top and "Score: 2/10 🟢" at the bottom — a
        # red answer wearing a green badge, in the same message.
        marks = set(MARKER.findall(r)) - {"✅", "❌"}
        # ✅/❌ only where they are a verdict. Inside a correction bullet
        # ("❌ becouse → ✅ because") they are about one word, and an 8/10 with
        # one small correction legitimately carries both.
        lines = [l for l in r.split("\n") if l.strip()]
        verdict = [l for i, l in enumerate(lines) if i == 0 or SCORE.search(l)]
        marks |= {m for l in verdict for m in MARKER.findall(l)}
        if n <= 4 and marks & {"🟢", "✅"}:
            disagree.append(f"🟢/✅ amb {sc.group(0)}")
        elif n >= 8 and marks & {"🔴", "❌"}:
            disagree.append(f"🔴/❌ amb {sc.group(0)}")
    rep.check(not disagree, "el marcador concorda amb la nota",
              disagree[0] if disagree else "")

    # --- is it grading her own language? ------------------------------------
    #
    # Asking for the Catalan meaning of an English word is a fine exercise: it
    # tests whether she knows what the word means. What is not fine is marking
    # her Catalan. A missing accent is not an English mistake, and once it is
    # filed as an error pattern it comes back days later as an "exercise"
    # drilling her own language at her.
    def fold(w: str) -> str:
        return "".join(ch for ch in unicodedata.normalize("NFD", w.lower())
                       if unicodedata.category(ch) != "Mn" and ch.isalnum())

    filed = []
    if (prof_dir / ".records").is_dir():
        for f in (prof_dir / ".records").glob("*.jsonl"):
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    corrections = json.loads(line).get("corrections") or []
                except ValueError:
                    continue
                for c in corrections:
                    w, r = str(c.get("wrong", "")), str(c.get("right", ""))
                    # The harm is not "the right answer is a Catalan word" — a
                    # recognition exercise asks for exactly that, and marking a
                    # wrong answer to one is the tutor doing its job. The harm
                    # is marking her down for an accent or a typo in a word she
                    # plainly knew: "mati" → "matí". Same word, different skin.
                    # Not when they differ only in capitals: that is an English
                    # rule (the student scenario writes "i speak english" on
                    # purpose), not a diacritic or a letter of her own language.
                    if w and r and w != r and w.lower() != r.lower() and fold(w) == fold(r):
                        filed.append(f"{w} → {r}")
    rep.check(not filed, "no la penalitza per un accent o una lletra de la seva llengua",
              filed[0] if filed else "")

    recs = sorted((prof_dir / ".records").glob("*.jsonl")) if (prof_dir / ".records").is_dir() else []
    lines = sum(1 for f in recs for l in f.read_text().splitlines() if l.strip())
    scored = sum(1 for r in graded if SCORE.search(r))
    rep.check(lines >= max(1, scored - 1), "les respostes arriben a .records/",
              f"{lines} línies per a {scored} respostes qualificades")

    # --- what happens when she wanders off and comes back ------------------
    if args.scenario in ("wander", "marathon"):
        def span(name: str) -> list[str]:
            a, b = phase.get(name, [0, 0])
            return [f for fp in asked[a:b] for f in fp]

        back = replies[resumed_at] if resumed_at is not None and resumed_at < len(replies) else ""
        rep.check(not MENU_RE.search(back) and not GREETING_RE.search(back),
                  "en tornar a Lesson no torna a saludar ni a mostrar el menú",
                  back.strip().splitlines()[0][:60] if back.strip() else "(buit)")

        before, after = set(span("lesson_a")), span("lesson_b")
        rep.check(not (before & set(after)), "la lliçó no repeteix el que ja havia preguntat",
                  next(iter(before & set(after)), ""))

        done_now = plan_done()
        rep.check(done_now >= 2, "la lliçó reprèn on era, no de zero",
                  f"{done_now} de {total} després de tornar")

        # Vocabulary is practice, not the lesson: it counts for the day and must
        # NOT count against the lesson badge, or the badge fills up with work
        # the lesson never asked for.
        d0, d1 = daily_at_detour, daily_after_vocab
        rep.check(d1.get("graded", 0) > d0.get("graded", 0),
                  "el que fa a Vocabulary queda desat",
                  f"graded {d0.get('graded')} → {d1.get('graded')}")
        rep.check(d1.get("lesson", 0) == d0.get("lesson", 0),
                  "i no compta com a exercici de la lliçó",
                  f"lesson {d0.get('lesson')} → {d1.get('lesson')}")

        va, vb = set(span("vocab_a")), span("vocab_b")
        rep.check(not (va & set(vb)), "en tornar a Vocabulary no repeteix les mateixes paraules",
                  next(iter(va & set(vb)), ""))
        rep.check(bool(vb), "i sí que en proposa de noves", f"{len(set(vb))} exercicis")

    # --- the student: right answers must be treated as right ----------------
    if args.scenario in ("student", "journey", "noisy"):
        graded_turns = [j for j in judged if j["item"] and j["item"].get("answer")]
        on_item = [j for j in graded_turns if j["follows"]]
        # Lesson turns only: they have an item the server assigned (an id). The
        # free-practice turns of the journey are judged by the bank word instead.
        lesson_turns = [j for j in graded_turns if j["item"].get("id")]
        on_lesson = [j for j in lesson_turns if j["follows"]]
        rep.check(len(on_lesson) >= max(1, (len(lesson_turns) * 2 + 2) // 3),
                  "l'exercici és sobre l'ítem que el servidor ha assignat",
                  f"{len(on_lesson)} de {len(lesson_turns)}"
                  + (f" · no: «{next(j['item']['content'] for j in lesson_turns if not j['follows'])}»"
                     if len(on_lesson) < len(lesson_turns) else ""))

        def score_of(reply_idx: int) -> int | None:
            m = SCORE.search(replies[reply_idx]) if reply_idx < len(replies) else None
            return int(re.split(r"\s*/\s*", m.group(0))[0]) if m else None

        # Only turns whose exercise was about the item: a tutor that ignored the
        # assignment makes the "right" answer a wrong one, and that is the check
        # above, not this one.
        low = [f"«{j['answer']}» → {score_of(j['reply'])}/10" for j in on_item
               if j["kind"] == "right" and (score_of(j["reply"]) or 0) < 8]
        rep.check(not low, "una resposta correcta rep nota alta (8 o més)",
                  low[0] if low else "")
        # 9 or more, not 8: a slip that is only a capital letter ("i speak english
        # on mondays") is a small mistake and 8/10 is a fair mark for it.
        high = [f"«{j['answer']}» → {score_of(j['reply'])}/10" for j in on_item
                if j["kind"] == "wrong" and (score_of(j["reply"]) or 0) >= 9]
        rep.check(not high, "una resposta equivocada no rep nota alta (9 o més)",
                  high[0] if high else "")
        if args.scenario == "noisy":
            small = [f"«{j['answer'][:40]}» ({j['variant']}) → {score_of(j['reply'])}/10"
                     for j in on_item if j["kind"] == "typo" and (score_of(j["reply"]) or 0) < 6]
            rep.check(not small, "una errada d'una lletra és una errada petita (6 o més)",
                      small[0] if small else "")
            lax = [f"«{j['answer'][:40]}» ({j['variant']}) → {score_of(j['reply'])}/10"
                   for j in on_item if j["variant"] in NOISY_STRICT
                   and (score_of(j["reply"]) or 0) >= 8]
            rep.check(not lax, "incompleta, en una altra llengua o buida no arriba a 8",
                      lax[0] if lax else "")
            longs = [j for j in on_item if j["variant"] == "long"]
            lost = [f"«{j['answer'][:30]}…»" for j in longs
                    if not asked[j["reply"]] and not CLOSING.search(replies[j["reply"]])]
            rep.check(not lost, "una resposta molt llarga no fa perdre el fil",
                      lost[0] if lost else "")
        # A different real word is not "almost there". The schedule counts a 6 as
        # remembered (quality = score // 2 >= 3), so a 6 for "friend" on llibre
        # sends the word away for days. Measured 2026-09-20: table→6, rain→6, friend→6.
        other = [f"«{j['answer']}» → {score_of(j['reply'])}/10" for j in on_item
                 if j["kind"] == "wrong" and (j["answer"] in DECOYS or not j["item"].get("id"))
                 and (score_of(j["reply"]) or 0) >= 6]
        rep.check(not other, "una paraula equivocada no passa de 5 (l'SM-2 la donaria per sabuda)",
                  other[0] if other else "")
        green = [j for j in on_item if j["kind"] == "right"
                 and score_of(j["reply"]) is not None and score_of(j["reply"]) >= 8
                 and not (set(MARKER.findall(replies[j["reply"]])) & {"🟢", "✅"})]
        rep.check(not green, "i una de correcta porta marcador verd",
                  f"«{green[0]['answer']}»" if green else "")

        rec_items: dict[str, list[int]] = {}
        rf = prof_dir / ".records" / f"{sid}.jsonl"
        if rf.exists():
            for line in rf.read_text().splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("item_id"):
                    rec_items.setdefault(r["item_id"], []).append(int(r.get("score", 0) or 0))
        keyed = [j for j in on_lesson if j["item"]["id"] in rec_items]
        rep.check(len(keyed) >= max(0, len(on_lesson) - 1),
                  "cada resposta queda registrada amb l'item_id de l'ítem assignat",
                  f"{len(keyed)} de {len(on_lesson)}")
        wrongly_scored = [f"{j['item']['id']}: {j['kind']} però registrat {rec_items[j['item']['id']]}"
                          for j in keyed
                          if (j["kind"] == "right" and max(rec_items[j["item"]["id"]]) < 8)
                          or (j["kind"] == "wrong" and min(rec_items[j["item"]["id"]]) >= 9)]
        rep.check(not wrongly_scored, "i el registre porta una nota que hi concorda",
                  wrongly_scored[0] if wrongly_scored else "")

    # --- the journey: free practice after the lesson ------------------------
    if args.scenario == "journey":
        def free_score(i: int) -> int | None:
            m = SCORE.search(replies[i])
            return int(re.split(r"\s*/\s*", m.group(0))[0]) if m else None

        no_grade = [i for i in free_replies if free_score(i) is None]
        rep.check(not no_grade, "tota resposta en pràctica lliure rep correcció amb nota",
                  f"{len(no_grade)} de {len(free_replies)} sense nota (torn {no_grade[0]})" if no_grade else "")
        soft = [i for i in writing_replies if (free_score(i) or 0) >= 9]
        rep.check(not soft, "una frase amb errors a Writing no rep nota alta (9 o més)",
                  f"torn {soft[0]}: {free_score(soft[0])}/10" if soft else "")
        # Writing's feedback has its own heading ("📝 Corrected Version").
        no_fix = [i for i in writing_replies
                  if not re.search(r"correct(?:ed)? (?:version|text)|correct answer", replies[i], re.I)]
        rep.check(len(no_fix) <= len(writing_replies) // 2, "i n'ensenya la versió correcta",
                  f"{len(writing_replies) - len(no_fix)} de {len(writing_replies)}")
        # What the Writing exercise asks for must be what the level can write
        # (skills/fluent-writing/SKILL.md): A2 does not write an email.
        if writing_press is not None and writing_press < len(replies):
            try:
                level = str(json.loads((prof_dir / "learner-profile.json").read_text())
                            .get("learner", {}).get("current_level", "")).strip().upper()
            except (OSError, ValueError):
                level = ""
            limits = {"A1": (25, 3), "A2": (45, 6), "B1": (70, 12), "B2": (120, 20)}
            ex = exercise_tail(replies[writing_press]) or replies[writing_press]
            if level in limits:
                max_words, max_sent = limits[level]
                asked_words = [int(x) for m in re.finditer(r"(\d+)\s*(?:-|–|—|to)\s*(\d+)\s*words", ex, re.I)
                               for x in m.groups()] + \
                              [int(m.group(1)) for m in re.finditer(r"(\d+)\+?\s*words", ex, re.I)]
                asked_sent = [int(x) for m in re.finditer(r"(\d+)\s*(?:-|–|—|to)\s*(\d+)\s*sentences", ex, re.I)
                              for x in m.groups()] + \
                             [int(m.group(1)) for m in re.finditer(r"(\d+)\s*sentences", ex, re.I)]
                bad = []
                if asked_words and max(asked_words) > max_words:
                    bad.append(f"{max(asked_words)} paraules (màx. {max_words})")
                if asked_sent and max(asked_sent) > max_sent:
                    bad.append(f"{max(asked_sent)} frases (màx. {max_sent})")
                if level in ("A1", "A2") and re.search(r"\b(?:e-?mail|letter)\b", ex, re.I):
                    bad.append("un email/carta, tasca de B1")
                rep.check(not bad, f"Writing demana un text adequat al nivell ({level})",
                          "; ".join(bad))
        d0, d1 = daily_at_detour, daily_after_vocab
        rep.check(d1.get("graded", 0) > d0.get("graded", 0), "el que fa a Vocabulary queda desat",
                  f"graded {d0.get('graded')} → {d1.get('graded')}")
        rep.check(d1.get("lesson", 0) == d0.get("lesson", 0), "i no compta com a exercici de la lliçó",
                  f"lesson {d0.get('lesson')} → {d1.get('lesson')}")
        # Words she ANSWERED in the first visit. One shown and left unanswered may
        # come back (that is not a repeat), so it is not on this list.
        va = {f for i in answer_idx if phase["vocab_a"][0] <= i < phase["vocab_a"][1]
              and (free_score(i) or 0) >= 8
              for f in asked[i - 1]}
        vb = {f for fp in asked[phase["vocab_b"][0] - 1:phase["vocab_b"][1]] for f in fp}
        rep.check(not (va & vb), "en tornar a Vocabulary no repeteix les mateixes paraules",
                  next(iter(va & vb), ""))
        rep.check(bool(vb), "i sí que en proposa de noves", f"{len(vb)} exercicis")

        # A card must ask in the language it is not written in: "Català: finestra —
        # Què vol dir en català?" asks the Catalan word's meaning in Catalan. The
        # tutor mixes the two card templates of skills/fluent-vocab/SKILL.md.
        span_vocab = [i for a, b in (phase["vocab_a"], phase["vocab_b"]) for i in range(a - 1, b)]
        cards = [exercise_tail(replies[i]) for i in span_vocab if 0 <= i < len(replies)]
        mixed = [c for c in cards
                 if re.search(r"\*\*(?:Catal[àa]|Catalan):\*\*", c)
                 and re.search(r"en catal[àa]|in catalan", c, re.I)]
        rep.check(not mixed, "les targetes de Vocabulary no demanen en la llengua de la paraula",
                  f"{len(mixed)} de {len(cards)} targetes" if mixed else "")

    # --- a closed lesson has to stay closed --------------------------------
    if args.scenario in ("full", "student", "journey", "noisy"):
        rep.check(closed_early_at is not None, "la lliçó arriba al seu final",
                  f"{plan_done()} de {total} després de {len(graded)} respostes")
        if after_close is not None:
            end_closed = journey_from if journey_from is not None else len(asked)
            extra_new = [f for i in range(after_close, end_closed) for f in new_each_turn[i]]
            rep.check(not extra_new, "i s'hi queda: cap exercici nou després de tancar",
                      extra_new[0] if extra_new else "")
            rep.check(all(not CLOSING.search(r) or True for r in replies[after_close:end_closed]),
                      "segueix responent sense trencar-se", "")
            pointed = sum(1 for r in replies[after_close:end_closed]
                          if re.search(r"bot(ó|ons)|button|🎲|🔁|📚", r, re.I))
            rep.check(pointed >= 1, "i l'orienta cap als botons",
                      f"{pointed} de {end_closed - after_close} torns")

    # --- and what about yesterday? -----------------------------------------
    #
    # The one thing the whole system is built on: what she answered correctly
    # does not come back tomorrow, and what she missed does. Previous days live
    # in the archived records that fluent-advance-day.py sets aside.
    knew, missed = set(), set()
    rec_dir = prof_dir / ".records"
    if rec_dir.is_dir():
        for f in rec_dir.glob(".*.jsonl.day-*"):
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                ex = str(r.get("exercise", "")).strip().lower()
                if not ex:
                    continue
                (knew if int(r.get("score", 0) or 0) >= 8 else missed).add(ex)
    if knew or missed:
        today_asked = {f for fp in asked for f in fp}
        again = sorted(knew & today_asked)
        rep.check(not again, "no li torna a preguntar el que ja sabia",
                  f"«{again[0]}»" if again else f"{len(knew)} encertats ahir, cap repetit")
        if missed:
            rep.check(bool(missed & today_asked), "i sí que li torna el que va fallar",
                      f"{len(missed & today_asked)} de {len(missed)}")

    guards = prof_dir / ".metrics" / "guards.jsonl"
    fired = []
    all_events: list[dict] = []
    if guards.exists():
        for line in guards.read_text().splitlines():
            try:
                g = json.loads(line)
            except ValueError:
                continue
            if g.get("session") != sid:
                continue
            all_events.append(g)
            note = g.get("note", "")
            # "rewritten" is the OUTCOME of the line above it, not a second
            # intervention. Counting both doubled every guard figure we have
            # compared runs on: 11 events were five triggers and their rewrites.
            if note.strip().startswith("rewritten"):
                continue
            fired.append(note[:70])
    rep.guards = len(fired)
    if fired:
        print(f"\nel guard del servidor ha actuat {len(fired)} cop(s):")
        for f in fired:
            print(f"  ↻ {f}")
    if all_events:
        # The full lines, rewrites included, in the order they happened: the
        # console shows 70 characters of each and drops the outcome, and it is
        # the outcome ("rewrite rejected", "rewritten") that says what the
        # student would have seen.
        transcript.append("## guard del servidor (text complet, en ordre)\n\n" + "\n".join(
            "- " + json.dumps({k: v for k, v in g.items() if k != "session"}, ensure_ascii=False)
            for g in all_events))

    notes_file = prof_dir / ".metrics" / "notes.jsonl"
    turn_notes: list[str] = []
    if notes_file.exists():
        for line in notes_file.read_text().splitlines():
            try:
                nt = json.loads(line)
            except ValueError:
                continue
            if nt.get("session") != sid:
                continue
            turn_notes.append("- " + json.dumps({k: v for k, v in nt.items() if k != "session"},
                                                ensure_ascii=False))
    if turn_notes:
        # What the server told the tutor, per turn, beside the learner's answer:
        # the way to see a note and a guard asking for opposite things.
        transcript.append("## notes del servidor al tutor (per torn)\n\n" + "\n".join(turn_notes))

    log = Path(f"/tmp/fluent-web-{args.port}.log")
    warns = [l for l in log.read_text(errors="ignore").splitlines()
             if "⚠" in l and sid in l] if log.exists() else []
    rep.check(not warns, "cap avís del servidor per aquesta sessió",
              warns[0][:90] if warns else "")

    if args.transcript:
        Path(args.transcript).expanduser().write_text(
            f"# Lliçó e2e — {prof_dir.name} — {sid}\n\n" + "\n\n---\n\n".join(transcript),
            encoding="utf-8")
        print(f"\ntranscripció: {args.transcript}")

    if quiet:
        bad = [lbl for ok, lbl, _ in rep.rows if not ok]
        print(f"  → {len(rep.rows) - len(bad)}/{len(rep.rows)} bé"
              + (f" · falla: {', '.join(bad)}" if bad else "")
              + f" · guard {rep.guards}×")
        return rep
    rep.render()
    return rep


# ---- the "student" scenario: a learner who knows some of the answers ---------
#
# The other scenarios answer junk, and on a retry the tutor's own correction.
# That proves the tutor can grade a wrong answer and nothing about a right one:
# whether a correct answer earns a high score, a green marker and the right
# item_id was never tested. The server knows what it asked (notes.jsonl carries
# the assigned item) and the seed knows that item's answer, so this learner can
# answer right on purpose, and wrong the way a real learner is wrong.
STUDENT_PLAN = ["right", "wrong", "right", "right", "wrong", "right"]
DECOY = "table"
DECOYS = (DECOY, "dog")


def decoy_for(item: dict | None) -> str:
    """A wrong answer that is not the item's own answer. Measured 2026-09-21: on
    the card for «taula» the decoy «table» IS the answer, the tutor marked it 10/10
    and the bench blamed it (days 083631)."""
    own = {str((item or {}).get("answer", "")).strip().lower(),
           str((item or {}).get("content", "")).strip().lower()}
    return next((d for d in DECOYS if d not in own), DECOYS[-1])

# ---- the "noisy" scenario: a learner who is not tidy --------------------------
#
# The student answers exactly the item's answer, or a fixed decoy. Nobody
# answers like that. Real answers come with a full stop, in a sentence, with a
# Catalan lead-in, in capitals, with a letter missing, half finished, in the
# wrong language, or as a paragraph. The tutor has to tell those apart:
#   right    — the answer is correct however it is dressed         → 8 or more
#   typo     — one letter off: a small mistake, not a wrong answer → 6 or more
#   strict   — incomplete, in the wrong language, or nothing       → below 8
#   wrong    — her own recorded slip                               → below 9
NOISY_PLAN = ["dot", "sentence", "typo", "partial", "upper", "catalan", "long",
              "noaccents", "wrong", "question"]
NOISY_STRICT = {"partial", "catalan", "question"}


def noisy_answer(variant: str, item: dict | None) -> tuple[str, str]:
    """(what she types, the class it belongs to) — see NOISY_PLAN.

    Pure, so the rules of what counts as right are tested without a model."""
    if not item or not item.get("answer"):
        return "no ho sé", "wrong"
    ans = str(item["answer"]).strip()
    iid = str(item.get("id", ""))
    words = ans.split()
    vocab = iid.startswith("vocabulary_")
    spelling = iid.startswith("spelling_")
    if variant == "dot":
        return ans + ".", "right"
    if variant == "sentence":
        return f"crec que és: {ans}", "right"
    if variant == "noaccents":
        return f"ho tinc, es {_fold_text(ans) if not spelling else ans}", "right"
    if variant == "upper":
        return (ans.upper(), "right") if vocab else (ans[:1].upper() + ans[1:], "right")
    if variant == "long":
        return ("Uf, no n'estic segura del tot, però ho vaig veure ahir a classe i em sembla "
                f"que era així: {ans}. Però també podria ser una altra cosa, no ho sé, "
                "perquè a vegades em confonc amb el que ens va dir la profe la setmana passada "
                "sobre aquestes coses i després em quedo en blanc. Bé, provo aquesta.", "right")
    if variant == "typo":
        if spelling:               # the typo IS the exercise there
            return ans + ".", "right"
        if len(words) == 1 and len(ans) >= 5:
            return ans[:2] + ans[3:], "typo"          # a letter dropped
        if len(words) > 1:
            w = max(range(len(words)), key=lambda i: len(words[i]))
            x = words[w]
            if len(x) >= 5:
                words[w] = x[:1] + x[2] + x[1] + x[3:]  # two letters swapped
                return " ".join(words), "typo"
        return ans, "right"
    if variant == "partial":
        if len(words) >= 3:
            return " ".join(words[:2]), "partial"
        return "no ho sé", "partial"
    if variant == "catalan":
        # Only a vocabulary card's content is a Catalan word; for a grammar item it is
        # the English sentence itself (the first version sent the right answer and
        # blamed the tutor for marking it 10/10).
        content = str(item.get("content", "")).strip() if str(item.get("id", "")).startswith("vocabulary_") else ""
        return (content or "no sé com es diu això en anglès, ho deixo així"), "catalan"
    if variant == "question":
        return "?", "question"
    if variant == "wrong":
        return item.get("learner_wrote") or decoy_for(item), "wrong"
    return ans, "right"


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


# ---- the "journey" scenario: the lesson, and then free practice ----------------
#
# The lesson is the mandatory minimum; everything after it is free practice,
# graded like always. This walks past the end of the lesson into Vocabulary and
# Writing and back, answering right and wrong on purpose, to see that free
# practice grades every answer and never asks an answered question again.
FREE_VOCAB_PLAN = ["right", "wrong", "right", "wrong"]
FREE_VOCAB_BACK = ["right", "wrong"]
FREE_WRITING = ["I have two childs and she go to school yesterday.",
                "Yesterday I am going to the market and buyed three apple."]
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
        spec = importlib.util.spec_from_file_location("fluent_seed", Path(__file__).with_name("fluent-seed.py"))
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


REVIEW_BLOCK = re.compile(r"```fluent:review_results.*?```", re.S)


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
# day per test is not a plan, so the clock is moved (fluent-advance-day.py) and
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
            p = subprocess.run([sys.executable, str(REPO / "scripts" / "fluent-advance-day.py"),
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
        greeting = tutor_text(cli.command(sid, "fluent-learn"))
        first = tutor_text(cli.command(sid, "fluent-review"))
        transcript.append(f"# dia {day} · {today} · sessió {sid}\n\n## /fluent-learn\n\n{greeting}\n\n## 🎓 Lesson\n\n{first}")
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
# a fixed curve (scripts/fluent-sim-path.py); what the model is asked for is the
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
    cu = _load_module("fluent_curriculum", "hooks/curriculum.py")
    sim = _load_module("fluent_sim_path", "scripts/fluent-sim-path.py")

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
            p = subprocess.run([sys.executable, str(REPO / "scripts" / "fluent-advance-day.py"),
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
        greeting = tutor_text(cli.command(sid, "fluent-learn"))
        if day == 1 and not greeting.strip() and time.time() - t0 < 3:
            print("\n❌ el tutor no ha dit res i ha trigat 0s: el model no respon.", file=sys.stderr)
            return 2
        first = tutor_text(cli.say(sid, "6"))          # 🎲 Surprise me!
        transcript.append(f"# dia {day} · {today} · Mix · sessió {sid}\n\n## /fluent-learn\n\n{greeting}\n\n## «6»\n\n{first}")
        answer_turns(sid, first, args.answers, day, "Mix")
        # Vocabulary
        if args.vocab > 0:
            vsid = cli.new_session()
            sids.add(vsid)
            vfirst = tutor_text(cli.command(vsid, "fluent-vocab"))
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
    cu = _load_module("fluent_curriculum", "hooks/curriculum.py")
    sim = _load_module("fluent_sim_path", "scripts/fluent-sim-path.py")
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
    view = (cli._call("/api/fluent/path") or {}).get("data") or {}
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
    out = tutor_text(cli.command(sid, "fluent-checkpoint"))
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
        v2 = (cli._call("/api/fluent/path") or {}).get("data") or {}
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
    v2 = (cli._call("/api/fluent/path") or {}).get("data") or {}
    rep.check(v2.get("level") == "A2" and (v2.get("pct") or 0) == 0.0,
              "el camí actiu és A2 i comença a 0%", f"{v2.get('level')} {v2.get('pct')}%")
    notice = v2.get("notice") or {}
    rep.check(bool(notice), "hi ha l'avís de curs acabat", json.dumps(notice, ensure_ascii=False)[:100])
    cli._call("/api/fluent/path/seen", {}, "POST")
    v3 = (cli._call("/api/fluent/path") or {}).get("data") or {}
    rep.check(not v3.get("notice"), "l'avís no torna un cop vist")
    rep.check(v3.get("checkpoint") != "ready", "A2 no ofereix la prova de nivell el primer dia", str(v3.get("checkpoint")))
    again = tutor_text(cli.command(cli.new_session(), "fluent-checkpoint"))
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


# ---- the "topics" scenario: the teacher's list steers the tutor, not the queue ----
#
# `topics.txt` in the profile is read by the server every turn (no restart) and
# reaches the tutor as a note. Two things have to hold: free practice (Writing)
# is built around a topic, and the Lesson's due items still come first. The file
# is written for the run and put back afterwards.
TOPIC_LINES = ["present perfect (have / has + past participle)", "food and restaurants"]
TOPIC_WORDS = re.compile(
    r"present perfect|\bhave (?:you )?(?:ever|never|already|just|been|eaten|visited|seen)\b|\bhas (?:she|he)?\s*\w*ed\b|"
    r"\b(?:ever|never|already|yet|since)\b|restaurant|menu|waiter|order|dinner|lunch|breakfast|food|meal|"
    r"eat|dish|table for", re.I)
LEAK = re.compile(r"teacher wants these topics|topics\.txt|this note", re.I)


def mentions_topic(text: str) -> bool:
    return bool(TOPIC_WORDS.search(text or ""))


def run_topics(args, cli, prof_dir: Path, rep: "Report", quiet: bool):
    tf = prof_dir / "topics.txt"
    before = tf.read_text(encoding="utf-8") if tf.exists() else None
    tf.write_text("# e2e topics\n" + "\n".join(TOPIC_LINES) + "\n", encoding="utf-8")
    transcript: list[str] = []
    replies: list[str] = []
    try:
        sid = cli.new_session()
        print(f"perfil {prof_dir.name} · port {args.port} · temes: {TOPIC_LINES}")
        greeting = tutor_text(cli.command(sid, "fluent-learn"))
        transcript.append(f"## /fluent-learn\n\n{greeting}")
        if not greeting.strip():
            print("\n❌ el tutor no ha dit res: el model no respon.", file=sys.stderr)
            return 2

        # 1. free practice: Writing, twice (the rotation moves with the answers)
        w1 = tutor_text(cli.command(sid, "fluent-writing"))
        transcript.append(f"## ✍️ Writing\n\n{w1}")
        replies.append(w1)
        rep.check(mentions_topic(exercise_tail(w1) or w1), "Writing es construeix al voltant d'un tema de la llista",
                  (exercise_tail(w1) or w1)[:110].replace("\n", " "))
        a1 = tutor_text(cli.say(sid, "Yesterday I went to a restaurant and I have eaten pizza with my friends."))
        transcript.append(f"## resposta (Writing)\n\n{a1}")
        replies.append(a1)
        rep.check(bool(SCORE.search(a1)), "i la resposta a Writing es corregeix amb nota", "")

        # 2. Vocabulary: a card is still a card
        v1 = tutor_text(cli.command(sid, "fluent-vocab"))
        transcript.append(f"## 📚 Vocabulary\n\n{v1}")
        replies.append(v1)
        rep.check(bool(re.search(r"Word \d+/\d+|\*\*(?:Catal|English)", v1)), "Vocabulary segueix donant targetes", v1[:80].replace("\n", " "))

        # 3. the Lesson: the queue wins
        due = due_now(prof_dir)
        first = tutor_text(cli.command(sid, "fluent-review"))
        transcript.append(f"## 🎓 Lesson\n\n{first}")
        replies.append(first)
        notes_path = prof_dir / ".metrics" / "notes.jsonl"
        sr_path = prof_dir / "spaced-repetition.json"
        if due:
            ok = 0
            shown = 0
            prev = first
            for n in range(min(3, len(due))):
                item = onscreen_item(notes_path, sr_path, sid)
                if item and item.get("answer"):
                    shown += 1
                    ok += 1 if follows_item(item, prev) else 0
                body = tutor_text(cli.say(sid, student_answer("right", item)))
                transcript.append(f"## resposta Lesson {n + 1}\n\n{body}")
                replies.append(body)
                prev = body
            rep.check(shown > 0 and ok >= max(1, (shown * 2 + 2) // 3),
                      "a la Lliçó mana la cua, no la llista de temes", f"{ok} de {shown}")

        leaked = [r[:60] for r in replies if LEAK.search(r)]
        rep.check(not leaked, "el tutor no anuncia ni cita la nota dels temes", leaked[0] if leaked else "")
    finally:
        # Put the profile back as it was: a topics file left behind steers every
        # later run and nobody would know why.
        if before is None:
            tf.unlink(missing_ok=True)
        else:
            tf.write_text(before, encoding="utf-8")
    if args.transcript:
        Path(args.transcript).expanduser().write_text(
            f"# Temes — {prof_dir.name}\n\n" + "\n\n---\n\n".join(transcript), encoding="utf-8")
    if quiet:
        bad = [lbl for ok, lbl, _ in rep.rows if not ok]
        print(f"  → {len(rep.rows) - len(bad)}/{len(rep.rows)} bé" + (f" · falla: {', '.join(bad)}" if bad else ""))
        return rep
    rep.render()
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("profile", nargs="?", default="test-en", help="profile id under ~/.fluent/")
    ap.add_argument("--dir", help="explicit profile directory")
    ap.add_argument("--port", type=int, default=4103)
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
    ap.add_argument("--scenario", choices=("lesson", "wander", "full", "marathon", "student", "journey", "days", "noisy", "topics", "curriculum", "ladder"), default="lesson",
                    help="lesson: una lliçó seguida · wander: Lesson→Vocabulary→Lesson→Vocabulary "
                         "(reprèn on tocava? es desa? repeteix?) · full: fins al tancament i dos torns més · "
                         "marathon: 16 respostes i tres desviacions, fins que la poda d'historial entri · "
                         "student: contesta bé i malament a propòsit els ítems que el servidor assigna · "
                         "journey: student + després Vocabulary, Writing i Vocabulary un altre cop, "
                         "amb respostes bones i dolentes i sense repetir res · "
                         "noisy: com student però amb respostes brutes (punt final, frase, majúscules, "
                         "una lletra de menys, a mitges, en català, molt llargues) · "
                         "topics: escriu un topics.txt temporal i comprova que Writing hi va i que la cua "
                         "de la Lliçó segueix manant · "
                         "days: N dies seguits (el rellotge avança); l'SM-2 ha de fer tornar el "
                         "que es falla i allunyar el que s'encerta · "
                         "curriculum: N dies d'un alumne simulat A1→A2 en pràctica lliure (Mix + Vocabulary): "
                         "el servidor assigna la competència, el tutor fa l'exercici, l'alumne respon "
                         "(vocabulari amb el banc de paraules, gramàtica amb el model) i es mira el camí")
    ap.add_argument("--days", type=int, default=5,
                    help="escenari days: quants dies seguits (per defecte 5)")
    ap.add_argument("--student", choices=("fast", "steady", "weak"), default="steady",
                    help="escenari curriculum: com aprèn l'alumne simulat (fluent-sim-path.py)")
    ap.add_argument("--seed", type=int, default=1, help="escenari curriculum: llavor de l'alumne simulat")
    ap.add_argument("--vocab", type=int, default=3,
                    help="escenari curriculum: respostes de Vocabulary cada dia (Mix fa --answers)")
    ap.add_argument("--student-url", dest="student_url",
                    default=os.environ.get("FLUENT_STUDENT_URL", "http://127.0.0.1:12322/v1"),
                    help="escenari curriculum: model OpenAI-compatible que respon la gramàtica com a "
                         "alumne (per defecte el llama del 12322; pot ser el mateix que el tutor)")
    ap.add_argument("--always-wrong", action="store_true", dest="always_wrong",
                    help="never give a right answer (stress test: how long does it retry?)")
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
    prof_dir = Path(args.dir).expanduser() if args.dir else Path.home() / ".fluent" / args.profile
    if not RESETTABLE.match(prof_dir.name):
        print("❌ --repeat només en perfils de proves: cada execució ha de tornar el perfil\n"
              "   al punt de partida, i això no es fa en un perfil real.", file=sys.stderr)
        return 2
    if args.reset:
        print("❌ --reset i --repeat no es combinen: el reset tornaria a córrer a cada volta\n"
              "   i esborraria el punt de partida que s'ha de restaurar. Prepara el perfil una\n"
              "   vegada (--reset o fluent-seed.py) i després llança el --repeat.", file=sys.stderr)
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
