#!/usr/bin/env python3
"""Does the learner actually get anywhere?

Every other test here checks that a function returns what it should. None of
them would have caught what the children hit: the tutor asking the same
questions for ever. A passing suite and a broken app are not a contradiction
when the suite never runs a week of the app.

So this one runs the real pipeline — update-db.py, read-db.py, the real SM-2 —
over simulated weeks, and asks the question a parent asks: does what she gets
right stop coming back, and does what she gets wrong return?
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORDS = ["welcome", "goodbye", "breakfast"]


class LearnerProgressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for src in (REPO_ROOT / "data-examples").glob("*-template.json"):
            (self.dir / src.name.replace("-template", "")).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8")
        for name, blank in (
            ("mistakes-db.json", {"error_patterns": {}}),
            ("spaced-repetition.json", {"review_queue": {"today": [], "tomorrow": [],
                                                         "this_week": [], "later": []},
                                        "items": {}}),
        ):
            doc = json.loads((self.dir / name).read_text(encoding="utf-8"))
            doc.update(blank)
            (self.dir / name).write_text(json.dumps(doc, indent=2), encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def _env(self):
        return {**os.environ, "FLUENT_DATA_DIR": str(self.dir), "FLUENT_ROOT": str(REPO_ROOT)}

    def _update(self, payload):
        p = subprocess.run([sys.executable, str(REPO_ROOT / "hooks" / "update-db.py")],
                           input=json.dumps(payload), capture_output=True, text=True,
                           env=self._env(), cwd=REPO_ROOT)
        self.assertEqual(p.returncode, 0, p.stderr)

    def _db(self, name):
        return json.loads((self.dir / name).read_text(encoding="utf-8"))

    def _due(self, day):
        return [k for k, v in self._db("spaced-repetition.json").get("items", {}).items()
                if isinstance(v.get("due_date"), str) and v["due_date"] <= day]

    def _weak(self):
        p = subprocess.run([sys.executable, str(REPO_ROOT / "hooks" / "read-db.py")],
                           capture_output=True, text=True, env=self._env(), cwd=REPO_ROOT)
        m = json.loads(p.stdout)["databases"].get("mistakes_db", {})
        return [w["id"] for w in m.get("top_weak_patterns", [])]

    def _mastery(self, word):
        return self._db("mistakes-db.json")["error_patterns"][f"vocabulary_{word}"].get("mastery_level")

    def _run_days(self, n_days, start=date(2026, 10, 1), wrong_on=()):
        """Day 0 makes the three mistakes; every later day answers what is due."""
        for n in range(n_days):
            day = (start + timedelta(days=n)).isoformat()
            due = self._due(day)
            payload = {"session_id": f"s{n}", "date": day, "duration_minutes": 10,
                       "exercises": [], "errors": [], "review_results": []}
            if n == 0:
                for w in WORDS:
                    payload["errors"].append({
                        "pattern_id": f"vocabulary_{w}", "category": "vocabulary",
                        "your_answer": "xxx", "correct_answer": w,
                        "context": "", "severity": "moderate"})
            else:
                quality = 1 if n in wrong_on else 5
                for item in due:
                    payload["review_results"].append({"item_id": item, "quality": quality})
            self._update(payload)

    # --- the two questions that matter ------------------------------------

    def test_what_she_gets_right_stops_coming_back(self):
        self._run_days(30)
        for w in WORDS:
            with self.subTest(word=w):
                self.assertGreaterEqual(self._mastery(w), 4,
                                        "answered right for a month and still not learned")
        self.assertEqual([], self._weak(),
                         "the tutor is still being told to drill what she knows")

    def test_the_spacing_actually_widens(self):
        self._run_days(30)
        items = self._db("spaced-repetition.json")["items"]
        for w in WORDS:
            with self.subTest(word=w):
                self.assertGreater(items[f"vocabulary_{w}"]["interval_days"], 20,
                                   "a month of correct answers and it still comes back weekly")

    def test_what_she_forgets_comes_straight_back(self):
        self._run_days(30)
        self.assertEqual([], self._weak())
        self._update({"session_id": "relapse", "date": "2026-12-09", "duration_minutes": 5,
                      "exercises": [], "errors": [],
                      "review_results": [{"item_id": "vocabulary_welcome", "quality": 1}]})
        self.assertEqual(3, self._mastery("welcome"), "one miss should cost exactly one step")
        self.assertIn("vocabulary_welcome", self._weak(), "a relapse must come back")
        item = self._db("spaced-repetition.json")["items"]["vocabulary_welcome"]
        self.assertEqual(1, item["interval_days"])
        self.assertEqual("2026-12-10", item["due_date"], "and it must come back tomorrow")

    def test_a_week_of_wrong_answers_does_not_explode_the_queue(self):
        """Three mistakes must stay three items, however often they are missed."""
        self._run_days(14, wrong_on=tuple(range(1, 14)))
        items = self._db("spaced-repetition.json")["items"]
        self.assertEqual(3, len(items), sorted(items))
        pats = self._db("mistakes-db.json")["error_patterns"]
        self.assertEqual(3, len(pats), sorted(pats))

    def test_nothing_is_ever_keyed_on_the_learners_typo(self):
        self._run_days(3)
        for db, key in (("mistakes-db.json", "error_patterns"), ("spaced-repetition.json", "items")):
            with self.subTest(db=db):
                self.assertEqual(sorted(self._db(db)[key]),
                                 sorted(f"vocabulary_{w}" for w in WORDS))


if __name__ == "__main__":
    unittest.main()
