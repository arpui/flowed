"""Steps items carry a per-step `goal` (what to do / which property), shown
BEFORE the learner writes the step (2026-10-08, Albert). And a word problem is
never solved by its first step."""
import glob
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks"))
import mathbank  # noqa: E402


def _items():
    for f in sorted(glob.glob(str(ROOT / "curriculum/bank/*/steps/*__steps.json"))):
        for it in json.load(open(f, encoding="utf-8")):
            yield f, it


class StepGoals(unittest.TestCase):
    def test_every_step_has_a_goal_without_a_computation(self):
        n = 0
        for f, it in _items():
            for st in it["steps"]:
                n += 1
                g = st.get("goal", "")
                self.assertTrue(g.strip(), f"{it['id']} step {st['n']}: no goal")
                self.assertFalse(re.search(r"\d+\s*[=×x*+\-]\s*\d+", g), f"{it['id']}: goal gives the step away: {g}")
        self.assertGreater(n, 100)

    def test_validator_rejects_missing_goal(self):
        _, it = next(_items())
        bad = json.loads(json.dumps(it))
        del bad["steps"][0]["goal"]
        self.assertTrue(any("goal" in e for e in mathbank.validate_item(bad)))

    def test_word_problems_are_not_one_step(self):
        for f, it in _items():
            if "problems" not in it["competence"]:
                continue
            self.assertGreaterEqual(len(it["steps"]), 3, it["id"])
            self.assertNotEqual(it["steps"][0]["value"], it["answer"], f"{it['id']}: first step solves it all")

    def test_fill_goals_never_overwrites(self):
        it = {"method": "grouping", "steps": [{"n": 1, "goal": "meu"}, {"n": 2}, {"n": 3}]}
        mathbank.fill_goals(it)
        self.assertEqual(it["steps"][0]["goal"], "meu")
        self.assertTrue(it["steps"][1]["goal"] and it["steps"][2]["goal"])


class MixedNumberExplained(unittest.TestCase):
    """A mixed number is written without "+": the why says what it means."""

    def test_gloss(self):
        g = mathbank.mixed_gloss("1 2/15")
        self.assertIn("17/15 = 1 + 2/15", g)
        self.assertEqual(mathbank.mixed_gloss("5/6"), "")
        self.assertEqual(mathbank.mixed_gloss("12"), "")

    def test_every_mixed_answer_in_the_bank_explains_itself(self):
        n = 0
        for f in glob.glob(str(ROOT / "curriculum/bank/*/*.json")):
            items = json.load(open(f, encoding="utf-8"))
            if not isinstance(items, list):
                continue
            for it in items:
                if isinstance(it, dict) and it.get("type") == "compute" and mathbank.mixed_gloss(it.get("answer", "")):
                    n += 1
                    self.assertIn("nombre mixt", it["why"], it["id"])
        self.assertGreater(n, 5)

    def test_grade_reports_what_was_typed(self):
        import bank
        item = {"id": "m4.frac_add_unlike.x", "competence": "m4.frac_add_unlike", "type": "compute",
                "problem": "4/5 + 4/12", "answer": "1 2/15", "also_accept": [], "options": [], "why": "w"}
        r = bank.grade(item, "68/60")
        self.assertEqual(r["verdict"], "correct")
        self.assertEqual(r["given"], "68/60")


if __name__ == "__main__":
    unittest.main()
