#!/usr/bin/env python3
"""
Smoke test for hooks/update-db.py.

Runs the script against a fresh fixture DB in a temp dir, feeds it a sample
session report, and asserts schema invariants on the output files.

Usage:
    python3 tests/test_update_db.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "hooks" / "update-db.py"


def make_fixtures(data_dir: Path):
    (data_dir / "learner-profile.json").write_text(json.dumps({
        "learner": {"name": "Test", "target_language": "Dutch",
                    "current_level": "A1", "target_level": "A2"},
        "profile_created": "2026-04-20",
        "last_updated": "2026-04-23",
        "current_streak_days": 2,
        "total_sessions": 1,
        "total_study_minutes": 10,
        "skills": {
            "vocabulary": {"current_level": 1, "confidence": 60,
                           "last_practiced": "2026-04-23",
                           "total_practice_time": 10}
        },
        "focus_areas": [],
        "achievements": [],
        "preferences": {}
    }))
    (data_dir / "progress-db.json").write_text(json.dumps({
        "metadata": {"last_updated": "2026-04-23", "language": "Dutch",
                     "tracking_started": "2026-04-20"},
        "overall_stats": {"total_sessions": 1, "total_exercises": 4,
                          "total_correct": 3, "total_incorrect": 1,
                          "accuracy_rate": 0.75,
                          "total_study_minutes": 10,
                          "average_session_duration": 10},
        "accuracy_trend": [{"date": "2026-04-23", "accuracy": 0.75,
                            "exercises": 4}],
        "skill_progress": {
            "vocabulary": {"sessions": 1, "accuracy": 0.75,
                           "last_practiced": "2026-04-23",
                           "exercises_completed": 4, "correct_count": 3,
                           "incorrect_count": 1}
        },
        "weekly_summary": []
    }))
    (data_dir / "mistakes-db.json").write_text(json.dumps({
        "metadata": {"last_updated": "2026-04-23",
                     "total_patterns_tracked": 0, "language": "Dutch"},
        "error_patterns": {}
    }))
    (data_dir / "mastery-db.json").write_text(json.dumps({
        "metadata": {"last_updated": "2026-04-23", "language": "Dutch"},
        "skills": {
            "vocabulary": {"mastery_level": 1, "confidence_score": 0.75,
                           "total_practice_time": 10,
                           "last_practiced": "2026-04-23",
                           "practice_count": 4, "avg_accuracy": 0.75}
        },
        "patterns": {}
    }))
    (data_dir / "spaced-repetition.json").write_text(json.dumps({
        "metadata": {"algorithm": "SM-2", "last_updated": "2026-04-23",
                     "total_items_tracked": 1, "language": "Dutch"},
        "review_queue": {"today": [], "tomorrow": ["vocab_dag"],
                         "this_week": [], "later": []},
        "items": {
            "vocab_dag": {
                "id": "vocab_dag", "type": "vocabulary", "content": "dag",
                "answer": "day / hi-bye", "category": "greetings",
                "difficulty": "A1", "created_date": "2026-04-23",
                "due_date": "2026-04-24", "interval_days": 1,
                "repetitions": 1, "easiness_factor": 2.5,
                "consecutive_correct": 1, "consecutive_incorrect": 0,
                "last_reviewed": "2026-04-23", "last_quality": 4,
                "mastery_level": 1, "total_reviews": 1, "priority": "medium"
            }
        }
    }))
    (data_dir / "session-log.json").write_text(json.dumps({
        "metadata": {"language": "Dutch", "learner_name": "Test",
                     "total_sessions": 1},
        "sessions": [{
            "session_id": "session-001", "date": "2026-04-23",
            "duration_minutes": 10,
            "skills_practiced": ["vocabulary"],
            "exercises_completed": 4, "accuracy": 0.75,
            "score_breakdown": {"vocabulary": 0.75},
            "topics_covered": [], "breakthroughs": [],
            "focus_next_session": [], "notes": "",
            "achievements_earned": []
        }],
        "milestones": []
    }))


SESSION_PAYLOAD = {
    "session_id": "session-002",
    "date": "2026-04-24",
    "duration_minutes": 15,
    "command_used": "/math-learn",
    "skills_practiced": ["vocabulary"],
    "skill_scores": {
        "vocabulary": {"exercises": 5, "correct": 4, "time_minutes": 15}
    },
    "errors": [{
        "pattern_id": "verb_spreek",
        "category": "calculation",
        "subcategory": "verb_conjugation",
        "your_answer": "Hij spreek",
        "correct_answer": "Hij spreekt",
        "context": "3rd person",
        "severity": "critical",
        "difficulty_score": 0.7
    }],
    "new_facts": [{
        "item_id": "het_huis",
        "item_type": "vocabulary",
        "content": "het huis",
        "answer": "the house",
        "category": "nouns",
        "difficulty": "A1",
        "initial_quality": 4
    }],
    "review_results": [{"item_id": "vocab_dag", "quality": 5}],
    "topics_covered": ["house_vocab"],
    "breakthroughs": ["Got 'het huis' on first try"],
    "focus_next_session": ["de/het drill"],
    "session_notes": "Good session.",
    "milestones": []
}


class UpdateDbSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="math-test-"))
        (self.tmp / "data").mkdir()
        make_fixtures(self.tmp / "data")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, payload: dict):
        # Drop host env that would redirect data-dir resolution away from the
        # tmp fixtures (e.g. FLOWED_DATA_DIR / CLAUDE_PROJECT_DIR from a running
        # opencode session).
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("FLOWED_DATA_DIR", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")
        }
        proc = subprocess.run(
            ["python3", str(SCRIPT)],
            input=json.dumps(payload).encode(),
            cwd=str(self.tmp),
            capture_output=True,
            env=env,
        )
        return proc

    def test_happy_path(self):
        proc = self._run(SESSION_PAYLOAD)
        self.assertEqual(proc.returncode, 0,
                         msg=f"stdout={proc.stdout!r} stderr={proc.stderr!r}")

        with open(self.tmp / "data" / "session-log.json") as f:
            log = json.load(f)
        latest = log["sessions"][-1]
        self.assertEqual(latest["session_id"], "session-002")
        self.assertIn("skills_practiced", latest)
        self.assertIsInstance(latest["skills_practiced"], list)
        self.assertIn("score_breakdown", latest)
        self.assertIn("topics_covered", latest)
        self.assertIn("breakthroughs", latest)
        self.assertIn("focus_next_session", latest)
        self.assertIn("achievements_earned", latest)
        self.assertEqual(latest["streak_day"], 3)  # was 2, yesterday -> +1

        with open(self.tmp / "data" / "learner-profile.json") as f:
            profile = json.load(f)
        self.assertEqual(profile["current_streak_days"], 3)
        conf = profile["skills"]["vocabulary"]["confidence"]
        self.assertIsInstance(conf, int)
        self.assertGreaterEqual(conf, 0)
        self.assertLessEqual(conf, 100)

        with open(self.tmp / "data" / "spaced-repetition.json") as f:
            sr = json.load(f)
        dag = sr["items"]["vocab_dag"]
        # Schema preserved
        for k in ("consecutive_correct", "consecutive_incorrect",
                  "mastery_level", "total_reviews", "priority",
                  "content", "answer", "category", "difficulty"):
            self.assertIn(k, dag, f"lost field {k} on vocab_dag")
        self.assertEqual(dag["total_reviews"], 2)  # was 1, +1 review
        self.assertEqual(dag["last_quality"], 5)

        # New vocabulary item fully populated
        huis = sr["items"]["het_huis"]
        for k in ("id", "type", "content", "answer", "category",
                  "difficulty", "due_date", "interval_days", "repetitions",
                  "easiness_factor", "consecutive_correct",
                  "consecutive_incorrect", "mastery_level",
                  "total_reviews", "priority"):
            self.assertIn(k, huis, f"new item missing {k}")

        with open(self.tmp / "data" / "mistakes-db.json") as f:
            mistakes = json.load(f)
        self.assertIn("verb_spreek", mistakes["error_patterns"])
        pat = mistakes["error_patterns"]["verb_spreek"]
        self.assertEqual(pat["consecutive_incorrect"], 1)
        self.assertEqual(pat["examples"][-1]["incorrect"], "Hij spreek")
        self.assertEqual(pat["examples"][-1]["correct"], "Hij spreekt")

        # Backup directory exists (nested inside data/ to avoid collisions
        # with other plugins when the global fallback ~/.claude/fluent-data is used).
        backup = self.tmp / "data" / ".backups" / "pre-update-session-002"
        self.assertTrue(backup.exists(), "pre-update backup missing")

    def test_optional_vocab_fields_passthrough(self):
        payload = json.loads(json.dumps(SESSION_PAYLOAD))
        payload["session_id"] = "session-021"
        payload["new_facts"] = [dict(
            SESSION_PAYLOAD["new_facts"][0],
            pos="noun", cefr_level="A1", forms={"plural": "de huizen"},
        )]
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 0,
                         msg=f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        with open(self.tmp / "data" / "spaced-repetition.json") as f:
            sr = json.load(f)
        huis = sr["items"]["het_huis"]
        self.assertEqual(huis["pos"], "noun")
        self.assertEqual(huis["cefr_level"], "A1")
        self.assertEqual(huis["forms"], {"plural": "de huizen"})

    def test_optional_vocab_fields_absent_when_not_provided(self):
        payload = json.loads(json.dumps(SESSION_PAYLOAD))
        payload["session_id"] = "session-022"
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 0,
                         msg=f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        with open(self.tmp / "data" / "spaced-repetition.json") as f:
            sr = json.load(f)
        huis = sr["items"]["het_huis"]
        for k in ("pos", "cefr_level", "forms"):
            self.assertNotIn(k, huis, f"{k} added even though payload omitted it")

    def test_the_old_new_vocabulary_spelling_is_still_read(self):
        # WP1.9 renamed the payload block to `new_facts`. Drafts and payloads
        # written before the rename carry `new_vocabulary`; update-db reads the
        # old spelling so an in-flight session is not silently dropped. Same
        # read-old/write-new discipline as the FLUENT_*→FLOWED_* env names.
        payload = json.loads(json.dumps(SESSION_PAYLOAD))
        payload["session_id"] = "session-023"
        payload["new_vocabulary"] = payload.pop("new_facts")
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 0,
                         msg=f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        sr = json.loads((self.tmp / "data" / "spaced-repetition.json").read_text())
        self.assertIn("het_huis", sr["items"])

    def test_future_schema_refuses_write_exit_2(self):
        p = self.tmp / "data" / "learner-profile.json"
        doc = json.loads(p.read_text())
        doc["_schema_version"] = 2
        p.write_text(json.dumps(doc))
        raw_before = {f.name: f.read_bytes() for f in (self.tmp / "data").glob("*.json")}
        proc = self._run(SESSION_PAYLOAD)
        self.assertEqual(proc.returncode, 2)
        self.assertIn(b"> supported v1", proc.stderr)
        raw_after = {f.name: f.read_bytes() for f in (self.tmp / "data").glob("*.json")}
        self.assertEqual(raw_before, raw_after, "wrote despite future schema")

    def test_missing_required_field_exits_1(self):
        proc = self._run({"date": "2026-04-24"})  # no session_id
        self.assertEqual(proc.returncode, 1)

    def test_same_day_does_not_bump_streak(self):
        # Profile last_updated = 2026-04-23; send a session on 2026-04-23.
        payload = dict(SESSION_PAYLOAD)
        payload["session_id"] = "session-003"
        payload["date"] = "2026-04-23"
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        with open(self.tmp / "data" / "learner-profile.json") as f:
            profile = json.load(f)
        self.assertEqual(profile["current_streak_days"], 2)

    # --- Milestones (issue #8) ---

    def _payload_with(self, session_id, milestones, date="2026-04-24"):
        payload = dict(SESSION_PAYLOAD)
        payload["session_id"] = session_id
        payload["date"] = date
        payload["milestones"] = milestones
        return payload

    def _load(self, name):
        with open(self.tmp / "data" / name) as f:
            return json.load(f)

    def test_milestone_string_form(self):
        text = "Reached A2 vocabulary milestone"
        proc = self._run(self._payload_with("session-100", [text]))
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        log = self._load("session-log.json")
        m = log["milestones"][-1]
        self.assertEqual(m["milestone"], text)
        self.assertEqual(m["date"], "2026-04-24")
        self.assertEqual(m["session_id"], "session-100")

        profile = self._load("learner-profile.json")
        ach = profile["achievements"][-1]
        self.assertEqual(ach["name"], text)
        self.assertEqual(ach["description"], text)
        self.assertEqual(ach["earned_date"], "2026-04-24")
        self.assertTrue(ach["id"].startswith("session_session-100_"))

    def test_milestone_object_form(self):
        ms = {"milestone": "Wrote first paragraph", "date": "2026-04-24",
              "session_id": "session-101"}
        proc = self._run(self._payload_with("session-101", [ms]))
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        log = self._load("session-log.json")
        m = log["milestones"][-1]
        self.assertEqual(m["milestone"], "Wrote first paragraph")  # flat string
        self.assertEqual(m["date"], "2026-04-24")
        self.assertEqual(m["session_id"], "session-101")

        profile = self._load("learner-profile.json")
        self.assertEqual(profile["achievements"][-1]["name"], "Wrote first paragraph")

    def test_milestone_object_preserves_own_date(self):
        ms = {"milestone": "Backdated win", "date": "2026-04-20"}
        proc = self._run(self._payload_with("session-102", [ms], date="2026-04-24"))
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        log = self._load("session-log.json")
        self.assertEqual(log["milestones"][-1]["date"], "2026-04-20")
        profile = self._load("learner-profile.json")
        self.assertEqual(profile["achievements"][-1]["earned_date"], "2026-04-20")

    def test_milestone_bad_date_falls_back_to_session_date(self):
        ms = {"milestone": "Typo date", "date": "not-a-date"}
        proc = self._run(self._payload_with("session-103", [ms], date="2026-04-24"))
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        log = self._load("session-log.json")
        self.assertEqual(log["milestones"][-1]["date"], "2026-04-24")

    def test_milestone_malformed_exits_1_no_mutation(self):
        bad_cases = [
            {"date": "2026-04-24"},          # missing milestone
            {"milestone": None},
            {"milestone": ""},
            {"milestone": "   "},
            {"milestone": 5},
            42,                              # neither str nor dict
            "",                              # empty string form
        ]
        for n, bad in enumerate(bad_cases):
            with self.subTest(case=bad):
                proc = self._run(self._payload_with(f"session-2{n:02d}", [bad]))
                self.assertEqual(proc.returncode, 1,
                                 msg=f"case={bad!r} stderr={proc.stderr!r}")
                self.assertTrue(proc.stderr, "expected an error message on stderr")
                # No DB mutation: session-log still has its single original session.
                log = self._load("session-log.json")
                self.assertEqual(len(log["sessions"]), 1)
                self.assertEqual(log["milestones"], [])

    def test_milestone_nested_session_id_overridden(self):
        ms = {"milestone": "X", "session_id": "WRONG-999"}
        proc = self._run(self._payload_with("session-104", [ms]))
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        log = self._load("session-log.json")
        self.assertEqual(log["milestones"][-1]["session_id"], "session-104")

    def test_milestone_distinct_achievement_ids(self):
        # Two strings sharing the first 30 chars would slugify identically;
        # the index prefix must keep their IDs distinct.
        prefix = "Mastered the perfect tense fo"  # 29 chars
        ms = [prefix + "r regular verbs", prefix + "r irregular verbs"]
        proc = self._run(self._payload_with("session-105", ms))
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        profile = self._load("learner-profile.json")
        ids = [a["id"] for a in profile["achievements"][-2:]]
        self.assertEqual(len(set(ids)), 2, msg=f"colliding ids: {ids}")

    def test_milestone_non_latin_distinct_nonempty_ids(self):
        # All-non-Latin text slugifies to empty; fallback + index keep IDs valid.
        ms = ["مرحلة أولى", "مرحلة ثانية"]
        proc = self._run(self._payload_with("session-106", ms))
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        profile = self._load("learner-profile.json")
        ids = [a["id"] for a in profile["achievements"][-2:]]
        self.assertEqual(len(set(ids)), 2, msg=f"colliding ids: {ids}")
        for i in ids:
            self.assertFalse(i.endswith("_"), f"bare trailing underscore: {i}")

    def test_milestones_empty_and_omitted_are_noops(self):
        for n, payload in enumerate([
            self._payload_with("session-107", []),
            {k: v for k, v in self._payload_with("session-108", []).items()
             if k != "milestones"},
        ]):
            with self.subTest(n=n):
                before = len(self._load("learner-profile.json").get("achievements", []))
                proc = self._run(payload)
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                after = len(self._load("learner-profile.json").get("achievements", []))
                self.assertEqual(after, before)


FILES = {
    "learner": "learner-profile.json",
    "progress": "progress-db.json",
    "mistakes": "mistakes-db.json",
    "mastery": "mastery-db.json",
    "sr": "spaced-repetition.json",
    "log": "session-log.json",
}


class UpdateDbIdempotencyTest(unittest.TestCase):
    """Re-applying the same session_id (per-answer incremental persistence)
    must never double-count. Applying the same accumulated payload N times, or
    growing it step by step, must yield the exact same databases as a single
    application of the final payload."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="math-idem-"))
        (self.tmp / "data").mkdir()
        make_fixtures(self.tmp / "data")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, payload: dict):
        env = {k: v for k, v in os.environ.items()
               if k not in ("FLOWED_DATA_DIR", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")}
        return subprocess.run(
            ["python3", str(SCRIPT)], input=json.dumps(payload).encode(),
            cwd=str(self.tmp), capture_output=True, env=env)

    def _dump(self):
        return {k: json.loads((self.tmp / "data" / f).read_text()) for k, f in FILES.items()}

    def _load(self, name):
        with open(self.tmp / "data" / name) as f:
            return json.load(f)

    def _full_payload(self, session_id):
        p = dict(SESSION_PAYLOAD)
        p["session_id"] = session_id
        p["skill_scores"] = {"vocabulary": {"exercises": 3, "correct": 2, "time_minutes": 8}}
        return p

    def test_apply_same_payload_thrice_is_idempotent(self):
        p = self._full_payload("session-150")
        for _ in range(3):
            proc = self._run(p)
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        # Single application of the same payload for comparison.
        proc = self._run(p)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        log = self._load("session-log.json")
        # Only original fixture session + this one, not 4.
        self.assertEqual([s["session_id"] for s in log["sessions"]].count("session-150"), 1)
        mis = self._load("mistakes-db.json")
        self.assertEqual(mis["error_patterns"]["verb_spreek"]["frequency"], 1)
        sr = self._load("spaced-repetition.json")
        dag = sr["items"]["vocab_dag"]
        self.assertEqual(len(dag["review_history"]), 1)
        self.assertEqual(dag["total_reviews"], 2)  # 1 fixture + 1 review
        self.assertEqual(self._load("learner-profile.json")["total_sessions"], 2)

    def test_growing_payload_equals_single_full_apply(self):
        full = self._full_payload("session-151")
        # House 1: apply in a partial step (review + new vocab, no error), then full.
        partial = {k: v for k, v in full.items() if k != "errors"}
        partial["errors"] = []
        proc = self._run(partial)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        proc = self._run(full)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        state_a = self._dump()

        # House 2: fresh fixtures, single full apply.
        shutil.rmtree(self.tmp)
        self.tmp = Path(tempfile.mkdtemp(prefix="math-idem2-"))
        (self.tmp / "data").mkdir()
        make_fixtures(self.tmp / "data")
        proc = self._run(full)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        state_b = self._dump()

        self.assertEqual(set(state_a), set(state_b))
        for k in state_a:
            self.assertEqual(state_a[k], state_b[k],
                             msg=f"growing-then-full and single-full diverged in {k}")


class ErrorTwinsTest(unittest.TestCase):
    """One sentence, one item — whatever the tutor called the slip."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="math-twin-"))
        (self.tmp / "data").mkdir()
        make_fixtures(self.tmp / "data")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, payload):
        env = {k: v for k, v in os.environ.items()
               if k not in ("FLOWED_DATA_DIR", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")}
        p = subprocess.run(["python3", str(SCRIPT)], input=json.dumps(payload).encode(),
                           cwd=str(self.tmp), capture_output=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)

    def _items(self):
        return json.loads((self.tmp / "data" / "spaced-repetition.json").read_text())["items"]

    def _err(self, pid, category, wrong, right):
        return {"session_id": "session-t", "date": "2026-04-24", "duration_minutes": 5,
                "errors": [{"pattern_id": pid, "category": category, "your_answer": wrong,
                            "correct_answer": right, "context": "", "severity": "moderate"}],
                "new_facts": [], "review_results": []}

    def test_the_same_answer_under_another_category_is_not_a_second_item(self):
        self._run(self._err("place_value_247_+_38_=_285", "place_value",
                            "247 + 38 = 185", "247 + 38 = 285"))
        before = set(self._items())
        payload = self._err("calculation_247_+_38_=_285", "calculation",
                            "247 + 38 = 185", "247 + 38 = 285")
        payload["session_id"] = "session-u"
        self._run(payload)
        self.assertEqual(set(self._items()), before)

    def test_a_capital_in_the_id_is_not_a_second_item(self):
        self._run(self._err("carrying_247_+_38_=_285", "carrying", "247 + 38 = 185",
                            "247 + 38 = 285"))
        before = set(self._items())
        payload = self._err("Carrying_247_+_38_=_285", "carrying", "247 + 38 = 185",
                            "247 + 38 = 285.")
        payload["session_id"] = "session-u"
        self._run(payload)
        self.assertEqual(set(self._items()), before)

    def test_different_answers_stay_different(self):
        self._run(self._err("carrying_247_+_38_=_285", "carrying", "247 + 38 = 185",
                            "247 + 38 = 285"))
        payload = self._err("carrying_158_+_45_=_203", "carrying", "158 + 45 = 103",
                            "158 + 45 = 203")
        payload["session_id"] = "session-u"
        self._run(payload)
        self.assertIn("carrying_158_+_45_=_203", self._items())

    def test_short_forms_are_never_merged(self):
        self._run(self._err("sign_+", "sign", "-", "+"))
        payload = self._err("wrong_operation_+", "wrong_operation", "×", "+")
        payload["session_id"] = "session-u"
        self._run(payload)
        self.assertIn("wrong_operation_+", self._items())


if __name__ == "__main__":
    unittest.main()