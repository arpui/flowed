#!/usr/bin/env python3
"""
Golden tests for SM-2 behavior documented in references/.

Runs update-db.py against a temporary data directory and checks the exact
spaced-repetition outcome for the worked examples.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "hooks" / "update-db.py"
TODAY = "2026-09-01"


def due(offset: int) -> str:
    base = datetime.strptime(TODAY, "%Y-%m-%d")
    return (base + timedelta(days=offset)).strftime("%Y-%m-%d")


def sr_item(
    item_id: str,
    content: str,
    answer: str,
    interval_days: int,
    repetitions: int,
    easiness_factor: float,
    consecutive_correct: int,
    consecutive_incorrect: int,
    mastery_level: int,
):
    return {
        "id": item_id,
        "type": "vocabulary",
        "content": content,
        "answer": answer,
        "category": "golden",
        "difficulty": "A1",
        "created_date": "2026-08-31",
        "due_date": TODAY,
        "interval_days": interval_days,
        "repetitions": repetitions,
        "easiness_factor": easiness_factor,
        "consecutive_correct": consecutive_correct,
        "consecutive_incorrect": consecutive_incorrect,
        "last_reviewed": "2026-08-31",
        "last_quality": 3,
        "mastery_level": mastery_level,
        "total_reviews": repetitions,
        "priority": "medium",
    }


def make_fixtures(data_dir: Path):
    items = {
        "sm2_ex1": sr_item("sm2_ex1", "het huis", "the house", 6, 2, 2.5, 1, 0, 1),
        "sm2_ex2": sr_item("sm2_ex2", "het gebouw", "the building", 6, 2, 2.3, 1, 0, 2),
        "sm2_ex3": sr_item("sm2_ex3", "omdat", "because", 14, 4, 2.8, 4, 0, 3),
        "sm2_ex4": sr_item("sm2_ex4", "formal_informal_confusion", "u/jij", 4, 1, 1.6, 0, 2, 2),
    }

    (data_dir / "learner-profile.json").write_text(json.dumps({
        "learner": {"name": "Golden", "target_language": "Dutch"},
        "last_updated": "2026-08-31",
        "current_streak_days": 2,
        "total_sessions": 1,
        "total_study_minutes": 10,
        "skills": {},
        "focus_areas": [],
        "achievements": [],
        "preferences": {},
    }))
    (data_dir / "progress-db.json").write_text(json.dumps({
        "metadata": {},
        "overall_stats": {
            "total_sessions": 1,
            "total_exercises": 0,
            "total_correct": 0,
            "total_incorrect": 0,
            "accuracy_rate": 0.0,
            "total_study_minutes": 10,
            "average_session_duration": 10,
        },
        "accuracy_trend": [],
        "skill_progress": {},
        "weekly_summary": [],
    }))
    (data_dir / "mistakes-db.json").write_text(json.dumps({
        "metadata": {},
        "error_patterns": {},
    }))
    (data_dir / "mastery-db.json").write_text(json.dumps({
        "metadata": {},
        "skills": {},
        "patterns": {},
    }))
    (data_dir / "spaced-repetition.json").write_text(json.dumps({
        "metadata": {"algorithm": "SM-2", "language": "Dutch"},
        "review_queue": {"today": [], "tomorrow": [], "this_week": [], "later": []},
        "items": items,
    }))
    (data_dir / "session-log.json").write_text(json.dumps({
        "metadata": {},
        "sessions": [],
        "milestones": [],
    }))


PAYLOAD = {
    "session_id": "session-sm2-golden",
    "date": TODAY,
    "review_results": [
        {"item_id": "sm2_ex1", "quality": 4},
        {"item_id": "sm2_ex2", "quality": 1},
        {"item_id": "sm2_ex3", "quality": 5},
        {"item_id": "sm2_ex4", "quality": 1},
    ],
}


class SM2GoldenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="math-sm2-golden-"))
        (self.tmp / "data").mkdir()
        make_fixtures(self.tmp / "data")

        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("FLOWED_DATA_DIR", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")
        }
        proc = subprocess.run(
            ["python3", str(SCRIPT)],
            input=json.dumps(PAYLOAD).encode(),
            cwd=str(self.tmp),
            capture_output=True,
            env=env,
        )
        if proc.returncode != 0:
            shutil.rmtree(self.tmp, ignore_errors=True)
            self.fail(
                f"update-db.py exited {proc.returncode}\n"
                f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
            )

        with open(self.tmp / "data" / "spaced-repetition.json") as f:
            self.sr = json.load(f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_correct_answer_regular_case(self):
        item = self.sr["items"]["sm2_ex1"]
        self.assertEqual(item["repetitions"], 3)
        self.assertEqual(item["interval_days"], 15)
        self.assertEqual(item["easiness_factor"], 2.5)
        self.assertEqual(item["consecutive_correct"], 2)
        self.assertEqual(item["consecutive_incorrect"], 0)
        self.assertEqual(item["mastery_level"], 1)
        self.assertEqual(item["due_date"], due(15))
        self.assertIn("sm2_ex1", self.sr["review_queue"]["later"])

    def test_wrong_answer_resets_and_drops_ef(self):
        item = self.sr["items"]["sm2_ex2"]
        self.assertEqual(item["repetitions"], 0)
        self.assertEqual(item["interval_days"], 1)
        self.assertAlmostEqual(item["easiness_factor"], 1.76)
        self.assertEqual(item["consecutive_correct"], 0)
        self.assertEqual(item["consecutive_incorrect"], 1)
        self.assertEqual(item["mastery_level"], 2)
        self.assertEqual(item["due_date"], due(1))
        self.assertIn("sm2_ex2", self.sr["review_queue"]["today"])
        self.assertNotIn("sm2_ex2", self.sr["review_queue"]["tomorrow"])

    def test_fifth_correct_bumps_mastery(self):
        item = self.sr["items"]["sm2_ex3"]
        self.assertEqual(item["repetitions"], 5)
        self.assertEqual(item["interval_days"], 39)
        self.assertAlmostEqual(item["easiness_factor"], 2.9)
        self.assertEqual(item["consecutive_correct"], 0)
        self.assertEqual(item["consecutive_incorrect"], 0)
        self.assertEqual(item["mastery_level"], 4)
        self.assertEqual(item["due_date"], due(39))
        self.assertIn("sm2_ex3", self.sr["review_queue"]["later"])

    def test_third_wrong_drops_mastery_and_forces_today(self):
        item = self.sr["items"]["sm2_ex4"]
        self.assertEqual(item["repetitions"], 0)
        self.assertEqual(item["interval_days"], 1)
        self.assertAlmostEqual(item["easiness_factor"], 1.3)
        self.assertEqual(item["consecutive_correct"], 0)
        self.assertEqual(item["consecutive_incorrect"], 0)
        self.assertEqual(item["mastery_level"], 1)
        self.assertEqual(item["due_date"], due(1))
        self.assertIn("sm2_ex4", self.sr["review_queue"]["today"])
        self.assertNotIn("sm2_ex4", self.sr["review_queue"]["tomorrow"])


if __name__ == "__main__":
    unittest.main()
