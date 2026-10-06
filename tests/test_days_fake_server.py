"""The multi-day scenario against a fake tutor.

A real run of `--scenario days` is half an hour of model time. The loop around
it — advance the clock, read the queue, answer what is on screen, wait for
persistence, judge the day — is plain code, and a mistake in it costs the whole
half hour. So it is run here against a server that behaves like a perfect
tutor: it hands out the due items, grades exact answers 10 and anything else 2,
and writes the same notes, plan and records the real server writes; the real
hook (update-db.py) then does the SM-2.

If this passes, a red check in a real run is the tutor's or the server's, not
the scenario's.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from argparse import Namespace
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


e2e = _load("math_e2e_days", "scripts/flowed-e2e.py")
seed = _load("math_seed_days", "scripts/flowed-seed.py")

WORDS = [("casa", "house"), ("gat", "cat"), ("gos", "dog"), ("pa", "bread"),
         ("aigua", "water"), ("llibre", "book")]


class FakeTutor:
    def __init__(self, prof: Path):
        self.prof = prof
        self.n = 0
        self.plans: dict[str, dict] = {}
        self.results: dict[str, list] = {}

    def sr(self) -> dict:
        return json.loads((self.prof / "spaced-repetition.json").read_text())["items"]

    def today(self) -> str:
        return date.today().isoformat()

    def plan_path(self) -> Path:
        d = self.prof / ".daily"
        d.mkdir(exist_ok=True)
        return d / f"lesson-{self.today()}.json"

    def note(self, sid: str, item_id: str | None) -> None:
        m = self.prof / ".metrics"
        m.mkdir(exist_ok=True)
        it = self.sr().get(item_id or "", {})
        rec = {"session": sid}
        if item_id:
            rec["assigned"] = {"id": item_id, "content": it.get("content", "")}
        with open(m / "notes.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def exercise(self, item_id: str) -> str:
        it = self.sr()[item_id]
        return f"## Exercise\n**Translate:** {it['content']} ({it['answer']})"

    def next_item(self, sid: str) -> str | None:
        done = {r["item_id"] for r in self.results.get(sid, [])}
        due = [k for k, v in self.sr().items() if v["due_date"] <= self.today() and k not in done]
        return sorted(due)[0] if due else None

    def command(self, sid: str, cmd: str) -> str:
        if cmd != "math-review":
            return "Hi!"
        due = [k for k, v in self.sr().items() if v["due_date"] <= self.today()]
        total = len(due) or 3
        self.plans[sid] = {"total": total, "done": 0}
        self.plan_path().write_text(json.dumps(self.plans[sid]))
        item = self.next_item(sid)
        self.note(sid, item)
        return self.exercise(item) if item else "## Exercise\n**Translate:** drill"

    def message(self, sid: str, text: str) -> str:
        plan = self.plans[sid]
        notes = [json.loads(l) for l in (self.prof / ".metrics" / "notes.jsonl").read_text().splitlines()]
        mine = [n for n in notes if n["session"] == sid]
        item_id = (mine[-1].get("assigned") or {}).get("id")
        score = 2
        if item_id:
            score = 10 if text.strip().lower() == self.sr()[item_id]["answer"].lower() else 2
            self.results.setdefault(sid, []).append({"item_id": item_id, "score": score})
            rec = self.prof / ".records"
            rec.mkdir(exist_ok=True)
            with open(rec / f"{sid}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"item_id": item_id, "score": score}) + "\n")
        plan["done"] += 1
        self.plan_path().write_text(json.dumps(plan))
        if plan["done"] >= plan["total"]:
            # The real server names sessions "session-001"… from a counter and the
            # wall clock does not move between simulated days, so every day is
            # "session-001@<today>": the T0 snapshot of day 1 is found on day 2.
            payload = {"session_id": "session-001", "date": self.today(), "duration_minutes": 5,
                       "exercises": [], "errors": [], "new_facts": [],
                       "review_results": [{"item_id": r["item_id"], "quality": r["score"] // 2}
                                          for r in self.results.get(sid, [])]}
            seed.update(self.prof, payload)
            return f"Score: {score}/10\nReview session complete"
        nxt = self.next_item(sid)
        self.note(sid, nxt)
        return f"Score: {score}/10 ✅\n" + (self.exercise(nxt) if nxt else "## Exercise\n**Translate:** drill")


def make_handler(tutor: FakeTutor):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _text(self, text):
            self._send({"parts": [{"type": "text", "text": text}]})

        def do_GET(self):
            self._send({})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/session":
                tutor.n += 1
                return self._send({"id": f"s{tutor.n}"})
            parts = self.path.split("/")
            if self.path.endswith("/command"):
                return self._text(tutor.command(parts[3], body["command"]))
            if self.path.endswith("/message"):
                return self._text(tutor.message(parts[3], body["parts"][0]["text"]))
            self._send({})
    return H


class DaysAgainstFakeTutorTest(unittest.TestCase):
    def test_five_days_of_a_perfect_tutor_pass_every_check(self):
        tmp = Path(tempfile.mkdtemp()) / "test-fake"
        tmp.mkdir()
        for tpl in (REPO / "data-examples").glob("*-template.json"):
            shutil.copy(tpl, tmp / tpl.name.replace("-template", ""))
        (tmp / ".web-password").write_text("x")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        seed.update(tmp, {"session_id": "seed", "date": yesterday, "duration_minutes": 1,
                          "exercises": [], "errors": [], "review_results": [],
                          "new_facts": [
                              {"item_id": f"vocabulary_{en}", "item_type": "vocabulary",
                               "content": ca, "answer": en, "category": "vocabulary",
                               "priority": "medium"} for ca, en in WORDS]})
        tutor = FakeTutor(tmp)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tutor))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        e2e.wait_quiet = lambda *a, **k: 0.0
        args = Namespace(profile="test-fake", dir=str(tmp), port=srv.server_address[1], answers=6,
                         timeout=20, transcript=None, user="opencode", password="x",
                         scenario="days", always_wrong=False, repeat=1, reset=False, days=5)
        with contextlib.redirect_stdout(io.StringIO()):
            rep = e2e.run(args, quiet=True)
        self.assertNotIsInstance(rep, int)
        failed = [r for r in rep.rows if not r[0]]
        self.assertEqual(failed, [], failed)
        # ...and the intervals really grew: 1 → 6 across the days.
        intervals = {int(v["interval_days"]) for v in tutor.sr().values()}
        self.assertIn(6, intervals, intervals)
        days_seen = {r[1].split(":")[0] for r in rep.rows if r[1].startswith("dia ")}
        self.assertEqual(days_seen, {f"dia {d}" for d in range(1, 6)})


if __name__ == "__main__":
    unittest.main()
