#!/usr/bin/env python3
"""Mastery decay: what an unpractised skill is worth today.

Two properties matter. First the shape — a holiday must not erase a year, and
"mastered" must stop meaning "was mastered once in April". Second, and easy to
get wrong: the decay is ABSOLUTE (earned level + idle days), never subtracted
from its own previous output. update-db.py restores the pre-session state and
replays the payload, so a relative decay would compound on every single run.
"""
import importlib.util
import json
import subprocess
import sys
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / "hooks"
sys.path.insert(0, str(HOOKS))

import db_schema  # noqa: E402


class DecayShapeTest(unittest.TestCase):
    def test_grace_period_changes_nothing(self):
        for idle in (0, 7, 14):
            self.assertEqual(db_schema.decayed_mastery(5, idle), 5, f"idle={idle}")

    def test_one_level_per_step_after_the_grace(self):
        # defaults: 14 days grace, one level per 21 idle days, floor 1
        self.assertEqual(db_schema.decayed_mastery(5, 35), 4)
        self.assertEqual(db_schema.decayed_mastery(5, 56), 3)
        self.assertEqual(db_schema.decayed_mastery(5, 77), 2)
        self.assertEqual(db_schema.decayed_mastery(5, 98), 1)

    def test_it_never_falls_through_the_floor(self):
        self.assertEqual(db_schema.decayed_mastery(5, 3650), 1)
        self.assertEqual(db_schema.decayed_mastery(3, 3650), 1)

    def test_a_skill_never_practised_stays_at_zero(self):
        self.assertEqual(db_schema.decayed_mastery(0, 3650), 0)

    def test_it_is_absolute_not_incremental(self):
        once = db_schema.decayed_mastery(5, 60)
        twice = db_schema.decayed_mastery(5, 60)
        self.assertEqual(once, twice)
        # feeding the output back in is what compounding would look like
        self.assertNotEqual(db_schema.decayed_mastery(once, 60), once)

    def test_garbage_does_not_raise(self):
        self.assertEqual(db_schema.decayed_mastery(None, 100), 0)
        self.assertEqual(db_schema.decayed_mastery("x", 100), 0)


class DecayConfigTest(unittest.TestCase):
    def test_defaults_when_the_profile_says_nothing(self):
        self.assertEqual(db_schema.decay_config(None), db_schema.MASTERY_DECAY)
        self.assertEqual(db_schema.decay_config({}), db_schema.MASTERY_DECAY)

    def test_a_learner_can_tune_it(self):
        cfg = db_schema.decay_config({"mastery_decay": {"grace_days": 30, "step_days": 30}})
        self.assertEqual(cfg["grace_days"], 30)
        self.assertEqual(cfg["step_days"], 30)
        self.assertEqual(cfg["floor"], db_schema.MASTERY_DECAY["floor"])

    def test_step_days_zero_switches_decay_off(self):
        cfg = db_schema.decay_config({"mastery_decay": {"step_days": 0}})
        self.assertEqual(db_schema.decayed_mastery(5, 3650, cfg), 5)

    def test_nonsense_overrides_are_ignored(self):
        cfg = db_schema.decay_config({"mastery_decay": {"step_days": "soon", "grace_days": -5}})
        self.assertEqual(cfg, db_schema.MASTERY_DECAY)


class DecayThroughUpdateDbTest(unittest.TestCase):
    """The real path: a session applied by update-db.py."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="math-decay-"))
        for name in ("learner-profile", "mastery-db", "mistakes-db", "progress-db",
                     "session-log", "spaced-repetition"):
            shutil.copy(REPO_ROOT / "data-examples" / f"{name}-template.json",
                        self.dir / f"{name}.json")
        self.today = date.today()
        stale = (self.today - timedelta(days=90)).isoformat()
        mastery = json.loads((self.dir / "mastery-db.json").read_text(encoding="utf-8"))
        mastery["skills"] = {
            "writing": {"mastery_level": 5, "last_practiced": stale, "practice_count": 40},
            "vocabulary": {"mastery_level": 4, "last_practiced": self.today.isoformat(),
                           "practice_count": 20},
        }
        (self.dir / "mastery-db.json").write_text(json.dumps(mastery, indent=2), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _apply(self, payload):
        proc = subprocess.run(
            [sys.executable, str(HOOKS / "update-db.py")],
            input=json.dumps(payload), capture_output=True, text=True,
            env={"FLOWED_DATA_DIR": str(self.dir), "PATH": "/usr/bin:/bin", "HOME": str(self.dir)},
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _skills(self):
        return json.loads((self.dir / "mastery-db.json").read_text(encoding="utf-8"))["skills"]

    def test_an_idle_skill_decays_and_a_practised_one_does_not(self):
        payload = {
            "session_id": "session-001",
            "date": self.today.isoformat(),
            "skill_scores": {"vocabulary": {"exercises": 5, "correct": 4}},
            "exercises": [{"type": "vocabulary", "score": 8}],
        }
        self._apply(payload)
        skills = self._skills()
        self.assertEqual(skills["writing"]["mastery_level"], 2,
                         "90 idle days should cost three levels")
        self.assertEqual(skills["writing"]["mastery_level_earned"], 5,
                         "what practice earned must be preserved")
        self.assertGreaterEqual(skills["vocabulary"]["mastery_level"], 1)
        self.assertEqual(skills["vocabulary"]["last_practiced"], self.today.isoformat())

    def test_re_applying_the_same_session_does_not_compound(self):
        payload = {
            "session_id": "session-001",
            "date": self.today.isoformat(),
            "skill_scores": {"vocabulary": {"exercises": 5, "correct": 4}},
            "exercises": [{"type": "vocabulary", "score": 8}],
        }
        self._apply(payload)
        first = self._skills()["writing"]["mastery_level"]
        self._apply(payload)
        self._apply(payload)
        self.assertEqual(self._skills()["writing"]["mastery_level"], first,
                         "decay compounded across runs")


class ErrorPatternsHealTest(unittest.TestCase):
    """read-db.py ranks weak patterns; an old error must not outrank a fresh one.

    The ranking used to be raw historical frequency (with an inert second key:
    pattern mastery_level is never raised anywhere), so a mistake the learner
    fixed months ago kept being the tutor's top priority for ever.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="math-rank-"))
        for name in ("learner-profile", "mastery-db", "mistakes-db", "progress-db",
                     "session-log", "spaced-repetition"):
            shutil.copy(REPO_ROOT / "data-examples" / f"{name}-template.json",
                        self.dir / f"{name}.json")
        today = date.today()
        mistakes = json.loads((self.dir / "mistakes-db.json").read_text(encoding="utf-8"))
        mistakes["error_patterns"] = {
            "tenses_old": {"category": "tenses", "frequency": 9, "mastery_level": 0,
                           "last_seen": (today - timedelta(days=120)).isoformat(), "examples": []},
            "articles_new": {"category": "articles", "frequency": 3, "mastery_level": 0,
                             "last_seen": today.isoformat(), "examples": []},
        }
        (self.dir / "mistakes-db.json").write_text(json.dumps(mistakes, indent=2), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _weak_patterns(self):
        proc = subprocess.run(
            [sys.executable, str(HOOKS / "read-db.py")],
            capture_output=True, text=True,
            env={"FLOWED_DATA_DIR": str(self.dir), "PATH": "/usr/bin:/bin", "HOME": str(self.dir)},
        )
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        return json.loads(proc.stdout)["databases"]["mistakes_db"]["top_weak_patterns"]

    def test_a_recent_mistake_outranks_a_stale_frequent_one(self):
        ids = [p["id"] for p in self._weak_patterns()]
        self.assertEqual(ids[0], "articles_new",
                         f"the stale pattern is still winning: {ids}")

    def test_the_tutor_can_see_how_old_each_pattern_is(self):
        by_id = {p["id"]: p for p in self._weak_patterns()}
        self.assertEqual(by_id["articles_new"]["days_since_seen"], 0)
        self.assertEqual(by_id["tenses_old"]["days_since_seen"], 120)
        self.assertEqual(by_id["tenses_old"]["frequency"], 9,
                         "the raw frequency must still be reported, only the ranking changes")


if __name__ == "__main__":
    unittest.main()
