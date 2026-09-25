"""The `curriculum` scenario against a fake tutor.

A real run is a long time of model. The loop around it — advance the clock keeping
the records, answer what is on screen, rebuild the path, judge — is plain code, and
a mistake in it costs the whole run. So it runs here against a tutor that behaves
like the specified one: it asks hooks/curriculum.py `next` (same code as the server)
which competence the exercise is about, builds an exercise that carries one of its
signals, grades right/wrong exactly, and writes the same notes and records the real
server writes. The student's grammar answers come from a stub instead of a model.

If this passes, a red check in a real run is the tutor's or the server's, not the
scenario's.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from argparse import Namespace
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))
import curriculum as cu  # noqa: E402


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


e2e = _load("fluent_e2e_curriculum", "scripts/flowed-e2e.py")


class FakeTutor:
    def __init__(self, prof: Path, wrong_note: str | None = None):
        self.prof = prof
        self.n = 0
        self.state: dict[str, dict] = {}
        self.wrong_note = wrong_note   # if set: never follows the competence
        self.cur = None
        self.vocab_sids: set[str] = set()

    def curriculum(self):
        if self.cur is None:
            self.cur = cu.load_curriculum(cu.find_curriculum(REPO, self.prof))
        return self.cur

    def note(self, sid: str, comp: dict | None) -> None:
        m = self.prof / ".metrics"
        m.mkdir(exist_ok=True)
        row = {"session": sid, "competence": ({"id": comp["id"], "name": comp["name"], "kind": comp["kind"]} if comp else None)}
        with open(m / "notes.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def ask(self, sid: str, vocab: bool = False) -> str:
        st = self.state.setdefault(sid, {"last": None, "count": 0, "vocab": vocab})
        comp = cu.next_target(self.curriculum(), self.prof, date.today().isoformat(), st["last"],
                              only_vocab=st.get("vocab", False))
        self.note(sid, comp or None)
        st["count"] += 1
        if not comp:
            st["expected"] = None
            return "## Exercise\n\nSay hello.\n\n**Type your answer:**"
        st["last"] = comp["id"]
        st["comp"] = comp["id"]
        if comp["vocab"]:
            # A tutor that FOLLOWS the note: always a word of the assigned list.
            # It used to fall back to a random word of the e2e's small bank when
            # none of the 5 words next_target offers was in it («escola», «matí»
            # for house_and_furniture) — an off-list card, which the check then
            # rightly flagged: 0-3 of 21. Catalan→English when the bank knows
            # the Catalan word, English→Catalan with the list word otherwise.
            words = comp["words"] or []
            full = next((c["words"] for c in self.curriculum()["competencies"] if c["id"] == comp["id"]), words)
            wanted = [w.lower() for w in (words or full)] + [w.lower() for w in full]
            pair = next(((en, ca) for w in wanted for en, ca in e2e.vocab_bank() if en.lower() == w), None)
            if pair:
                st["expected"] = pair[0]
                return f"## Word {st['count']}\n\n**Català:** {pair[1]}\n\n**What is it in English?**\n\n**Type your answer:**"
            word = (words or full)[0]
            st["expected"] = word
            return f"## Word {st['count']}\n\n**English:** {word}\n\n**What is it in Catalan?**\n\n**Type your answer:**"
        st["expected"] = "RIGHT"
        sig = "" if self.wrong_note else (comp["signals"][0] if comp["signals"] else "")
        topic = "I have two children" if self.wrong_note else f"She ___ (go) {sig}"
        return f"## Exercise {st['count']}\n\nComplete: {topic}.\n\n**Type your answer:**"

    def grade(self, sid: str, text: str) -> str:
        st = self.state[sid]
        exp = st.get("expected")
        if exp is None:
            return ""
        right = text.strip().lower() == exp.lower()
        score = 10 if right else 2
        rec = {"record_id": f"{sid}:m:{st['count']}", "session_id": sid, "ts": int(time.time() * 1000),
               "skill": "vocabulary" if exp != "RIGHT" else "grammar", "exercise": "x", "learner_answer": text,
               "score": score, "corrections": [], "competency": st["comp"]}
        rd = self.prof / ".records"
        rd.mkdir(exist_ok=True)
        with open(rd / f"{sid}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return f"{'✅' if right else '❌'} Feedback.\n\n**Correct version:**\n\"{exp}\"\n\n**Score: {score}/10**\n\n"

    def command(self, sid: str, cmd: str) -> str:
        if cmd == "fluent-vocab":
            self.vocab_sids.add(sid)
            self.state[sid] = {"last": None, "count": 0, "vocab": True}
            return self.ask(sid, vocab=True)
        self.state[sid] = {"last": None, "count": 0, "menu": True}
        self.note(sid, None)
        return "# Hello, Albert!\n\n**What would you like to practice today?**\n\n6. 🎲 Surprise me!\n\n**Type a number:**"

    def message(self, sid: str, text: str) -> str:
        st = self.state.setdefault(sid, {"last": None, "count": 0})
        if st.pop("menu", False):
            return self.ask(sid)
        return self.grade(sid, text) + self.ask(sid)


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

        def do_GET(self):
            self._send({})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/session":
                tutor.n += 1
                return self._send({"id": f"s{tutor.n}"})
            parts = self.path.split("/")
            text = tutor.command(parts[3], body["command"]) if self.path.endswith("/command") \
                else tutor.message(parts[3], body["parts"][0]["text"])
            self._send({"parts": [{"type": "text", "text": text}]})
    return H


class CurriculumAgainstFakeTutorTest(unittest.TestCase):
    def run_scenario(self, tutor_kwargs=None, days=4):
        tmp = Path(tempfile.mkdtemp()) / "test-fake"
        tmp.mkdir()
        for tpl in (REPO / "data-examples").glob("*-template.json"):
            shutil.copy(tpl, tmp / tpl.name.replace("-template", ""))
        (tmp / ".web-password").write_text("x")
        tutor = self.tutor = FakeTutor(tmp, **(tutor_kwargs or {}))
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tutor))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        e2e.wait_quiet = lambda *a, **k: 0.0
        # the student's grammar answers: right or wrong on demand, without a model
        e2e.student_llm = lambda url, exercise, ok, timeout=90: "RIGHT" if ok else "WRONG"
        args = Namespace(profile="test-fake", dir=str(tmp), port=srv.server_address[1], answers=6, timeout=20,
                         transcript=None, user="opencode", password="x", scenario="curriculum",
                         always_wrong=False, repeat=1, reset=False, days=days, student="fast", seed=3,
                         vocab=3, student_url="http://127.0.0.1:1/v1")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rep = e2e.run(args, quiet=True)
        return rep, tmp, buf.getvalue()

    def test_a_tutor_that_follows_the_note_passes_every_check(self):
        rep, tmp, out = self.run_scenario()
        self.assertNotIsInstance(rep, int, out[-800:])
        failed = [r for r in rep.rows if not r[0]]
        self.assertEqual(failed, [], f"{failed}\n{out[-1500:]}")
        # ...the records of every day are still there, one day apart, and the path moved
        cur = cu.load_curriculum(cu.find_curriculum(REPO, tmp))
        path = cu.load_path(tmp, cur)
        days = {a[0] for c in path["competencies"].values() for a in c["answers"]}
        # Vocabulary sessions only got vocabulary competences
        notes = [json.loads(l) for l in (tmp / ".metrics" / "notes.jsonl").read_text().splitlines()]
        vocab_rows = [r for r in notes if r["session"] in self.tutor.vocab_sids and r.get("competence")]
        self.assertTrue(vocab_rows)
        self.assertTrue(all(r["competence"]["id"].startswith("a2.vocab_") for r in vocab_rows),
                        [r["competence"]["id"] for r in vocab_rows])
        self.assertEqual(len(days), 4, days)
        self.assertGreater(cu.progress(cu.summarize(cur, path, date.today().isoformat()))["pct"], 0)
        self.assertIn("→", out)          # the order of competences is printed

    def test_a_tutor_that_ignores_the_competence_is_caught(self):
        rep, _, out = self.run_scenario({"wrong_note": "x"}, days=3)
        self.assertNotIsInstance(rep, int, out[-800:])
        failed = {r[1] for r in rep.rows if not r[0]}
        self.assertIn("el tutor fa l'exercici de la competència assignada (gramàtica i funcions)", failed, out[-1200:])


if __name__ == "__main__":
    unittest.main()
