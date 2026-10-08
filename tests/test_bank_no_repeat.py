"""A bank item answered correctly is not served again while unseen ones remain,
across calls exactly as the server makes them (CLI pick / answer, one process
each), for a level competence and for a learner's extra. (2026-10-08: nes
seemed to get the same questions again.)"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class NoRepeat(unittest.TestCase):
    def test_pick_answer_loop_never_repeats(self):
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "FLOWED_HOME": home}
            run = lambda *a: subprocess.run(a, cwd=ROOT, env=env, capture_output=True, text=True, check=True)
            run("bash", "scripts/new-user.sh", "test-lang", "--domain", "language")
            run(sys.executable, "scripts/flowed-profile.py", "test-lang", "--domain", "language", "--name", "T",
                "--native", "Catalan", "--target", "English", "--level", "A1", "--goal", "A2",
                "--minutes", "20", "--motivation", "practice")
            run(sys.executable, "scripts/flowed-extra.py", "add", "test-lang", "curriculum/extras/x.good_luck_babe")
            d = Path(home) / "test-lang"

            def cli(*a):
                r = subprocess.run([sys.executable, "hooks/curriculum.py", "bank", *a, "--auto", "--data", str(d)],
                                   cwd=ROOT, capture_output=True, text=True)
                return json.loads(r.stdout or "{}")

            for cid in ("x.good_luck_babe", "a1.vocab_food_snacks"):
                seen = []
                for _ in range(8):
                    p = cli("pick", "--competence", cid)
                    self.assertTrue(p.get("available"), (cid, p))
                    it = p["item"]
                    self.assertNotIn(it["id"], seen, f"{cid}: {it['id']} served again")
                    seen.append(it["id"])
                    a = cli("answer", "--competence", cid, "--item-id", it["id"], "--answer", it["answer"])
                    self.assertEqual(a.get("score"), 10, a)
            prog = json.loads((d / "bank-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(len(prog["x.good_luck_babe"]), 8)


if __name__ == "__main__":
    unittest.main()
