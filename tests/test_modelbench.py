#!/usr/bin/env python3
"""scripts/flowed-modelbench.py against fake models.

The real bench needs a model on railab. What is checked here is everything
around it: the learner skill is filled in, the answer is compared loosely
enough (contractions, digits), a tutor that writes "The car is ___." is caught
before the judge ever sees it, and the scorecard and the comparison come out.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "flowed-modelbench.py"

CURRICULUM = """---
language: English
level: A1
---

## Gramàtica

### a1.verb_to_be — The verb "to be" [core]
Can do: Introduce people.
Forms: I am, you are, he is
Check:
- Complete: She ___ (be) a doctor. → is
- Complete: We ___ (not/be) from London. → aren't / are not

## Vocabulari

### a1.vocab_colors_adjectives — Colours [core]
Can do: Describe things.
Words: red, blue, green
Check:
- Meaning: the colour of the sky on a sunny day → blue
"""


def fake(mode: str):
    prompts = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            p = body["messages"][0]["content"]
            prompts.append(p)
            if "You are a child learning English" in p:          # the learner skill
                if "(be) a doctor" in p:
                    out = {"answer": "is"}
                elif "(not/be)" in p:
                    out = {"answer": "are not"}                 # aren't / are not: the same answer
                elif "sky" in p:
                    out = {"answer": "blue"}
                elif "(vermell)" in p:
                    out = {"answer": "red"}
                else:
                    out = {"answer": "is"}
            else:                                                # the tutor
                if "Colours" in p:
                    out = ({"sentence": "The car is ___.", "answer": "red"} if mode == "bad"
                           else {"sentence": "The car is ___ (vermell).", "answer": "red"})
                else:
                    out = {"sentence": "He ___ my brother.", "answer": "is"}
            data = json.dumps({"choices": [{"message": {"content": json.dumps(out)}}],
                               "usage": {"completion_tokens": 7}}).encode()
            self.send_response(200)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/v1/chat/completions", prompts


class Bench(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.cur = Path(tempfile.mkdtemp()) / "en-A1.md"
        self.cur.write_text(CURRICULUM, encoding="utf-8")

    def run_bench(self, url, *args, judge=None):
        cmd = [sys.executable, str(SCRIPT), "--url", url, "--curriculum", str(self.cur), *args]
        if judge:
            cmd += ["--judge-url", judge]
        env = {**os.environ, "FLOWED_BENCH_OUT": str(self.out)}
        return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)

    def test_the_learner_role_scores_the_curriculum_checks(self):
        srv, url, prompts = fake("good")
        try:
            p = self.run_bench(url, "--name", "m", "learner")
        finally:
            srv.shutdown(); srv.server_close()
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        self.assertIn("m · learner: 100% de 3", p.stdout)
        # the skill was filled in: the lesson list, the current lesson, the card
        self.assertIn("Colours", prompts[0])
        self.assertIn("She ___ (be) a doctor.", prompts[0])
        self.assertNotIn("<<", prompts[0])

    def test_a_tutor_that_writes_the_car_is_gap_is_caught_before_the_judge(self):
        srv, url, prompts = fake("bad")
        try:
            p = self.run_bench(url, "--name", "bad", "generate", "--per", "1", judge=url)
        finally:
            srv.shutdown(); srv.server_close()
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        self.assertIn("vocabulari sense la paraula en català", p.stdout)
        self.assertIn("bad · generate: 50% de 2", p.stdout)

    def test_a_tutor_that_pins_the_word_is_fair_and_it_all_compares(self):
        srv, url, _ = fake("good")
        try:
            self.assertEqual(0, self.run_bench(url, "--name", "good", "generate", "--per", "1", judge=url).returncode)
            self.assertEqual(0, self.run_bench(url, "--name", "good", "learner").returncode)
            p = self.run_bench(url, "compare")
        finally:
            srv.shutdown(); srv.server_close()
        self.assertIn("good", p.stdout)
        line = next(l for l in p.stdout.splitlines() if l.startswith("good"))
        self.assertIn("100%", line)


if __name__ == "__main__":
    unittest.main()
