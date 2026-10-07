#!/usr/bin/env python3
"""
Tests for hooks/read-db.py: due ordering with overdue boost,
non-destructive reads, missing/corrupt files, and schema-version warnings.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "hooks" / "read-db.py"

MANAGED_ENV = ("FLOWED_DATA_DIR", "FLOWED_PROJECT_DIR", "FLOWED_ROOT",
               "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "HOME")


def day(offset_days: int) -> str:
    return (datetime.now() + timedelta(days=offset_days)).strftime("%Y-%m-%d")


def make_fixtures(data_dir: Path, with_profile=True):
    if with_profile:
        (data_dir / "learner-profile.json").write_text(json.dumps({
            "learner": {"name": "Test", "target_language": "Dutch",
                        "current_level": "A1"},
            "current_streak_days": 0,
            "last_updated": day(-1),
            "skills": {}, "focus_areas": [], "achievements": [],
        }))
    (data_dir / "progress-db.json").write_text(json.dumps({
        "metadata": {}, "overall_stats": {}, "accuracy_trend": [],
        "skill_progress": {}, "weekly_summary": [],
    }))
    (data_dir / "mistakes-db.json").write_text(json.dumps({
        "metadata": {"total_patterns_tracked": 0}, "error_patterns": {},
    }))
    (data_dir / "mastery-db.json").write_text(json.dumps({
        "metadata": {}, "skills": {}, "patterns": {},
    }))
    (data_dir / "session-log.json").write_text(json.dumps({
        "metadata": {}, "sessions": [], "milestones": [],
    }))
    (data_dir / "spaced-repetition.json").write_text(json.dumps({
        "metadata": {"algorithm": "SM-2"},
        "review_queue": {"today": [], "tomorrow": [], "this_week": [], "later": []},
        "items": {
            "low_very_old": {"id": "low_very_old", "type": "vocabulary",
                             "content": "a", "answer": "A", "priority": "low",
                             "due_date": day(-40), "interval_days": 1,
                             "repetitions": 1, "easiness_factor": 2.5},
            "med_mid": {"id": "med_mid", "type": "vocabulary",
                        "content": "c", "answer": "C", "priority": "medium",
                        "due_date": day(-20), "interval_days": 1,
                        "repetitions": 1, "easiness_factor": 2.5},
            "high_recent": {"id": "high_recent", "type": "vocabulary",
                            "content": "b", "answer": "B", "priority": "high",
                            "due_date": day(-1), "interval_days": 1,
                            "repetitions": 1, "easiness_factor": 2.5},
            "not_due": {"id": "not_due", "type": "vocabulary",
                        "content": "z", "answer": "Z", "priority": "critical",
                        "due_date": day(5), "interval_days": 1,
                        "repetitions": 1, "easiness_factor": 2.5},
        },
    }))


class ReadDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="math-read-"))
        self.data = self.tmp / "data"
        self.data.mkdir()
        make_fixtures(self.data)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = {k: v for k, v in os.environ.items() if k not in MANAGED_ENV}
        env["HOME"] = str(self.tmp / "home")  # keep fallback out of the real home
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            cwd=str(self.tmp), capture_output=True, env=env,
        )

    def _result(self, *args):
        proc = self._run(*args)
        return proc, json.loads(proc.stdout)

    def test_due_items_ordered_by_overdue_boosted_priority(self):
        proc, r = self._result()
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        due = r["databases"]["spaced_repetition"]["due_items"]
        ids = [e["id"] for e in due]
        # All three due items land in the same effective rank (low@40d and
        # medium@20d get boosted to high), so most-overdue goes first.
        self.assertEqual(ids, ["low_very_old", "med_mid", "high_recent"])
        self.assertNotIn("not_due", ids)
        by_id = {e["id"]: e for e in due}
        self.assertEqual(by_id["low_very_old"]["days_overdue"], 40)
        self.assertEqual(by_id["low_very_old"]["effective_priority"], "high")
        self.assertEqual(by_id["med_mid"]["days_overdue"], 20)
        self.assertEqual(by_id["med_mid"]["effective_priority"], "high")
        self.assertEqual(by_id["high_recent"]["effective_priority"], "high")
        self.assertEqual(by_id["high_recent"]["days_overdue"], 1)
        self.assertEqual(r["computed"]["due_review_items"], ids)

    def test_read_is_non_destructive(self):
        before = sorted(self.data.iterdir())
        raw = {p.name: p.read_bytes() for p in before}
        proc, _ = self._result("--full")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        after = {p.name: p.read_bytes() for p in sorted(self.data.iterdir())}
        self.assertEqual(raw, after, "read-db.py modified files on disk")

    def test_compact_and_full_agree_on_due_ids(self):
        _, compact = self._result()
        _, full = self._result("--full")
        self.assertEqual(
            [e["id"] for e in compact["databases"]["spaced_repetition"]["due_items"]],
            full["computed"]["due_review_items"],
        )

    def test_missing_files_warn_and_exit_1(self):
        (self.data / "session-log.json").unlink()
        proc, r = self._result()
        self.assertEqual(proc.returncode, 1)
        warnings = r["_warnings"]
        self.assertTrue(any("session-log.json" in w for w in warnings), warnings)

    def test_corrupt_file_warns_once_on_stderr_and_exit_1(self):
        (self.data / "mistakes-db.json").write_text("{ this is not json")
        proc, r = self._result()
        self.assertEqual(proc.returncode, 1)
        self.assertIn(b"[Fluent]", proc.stderr)
        warnings = r["_warnings"]
        self.assertTrue(any("Unreadable" in w for w in warnings), warnings)
        # The corrupt file must not also be listed as a plain missing file.
        self.assertFalse(any(w.startswith("Missing file") and "mistakes-db" in w
                             for w in warnings), warnings)

    def test_future_schema_warns_and_exit_1(self):
        p = self.data / "learner-profile.json"
        doc = json.loads(p.read_text())
        doc["_schema_version"] = 2
        p.write_text(json.dumps(doc))
        proc, r = self._result()
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(any("newer than supported" in w for w in r["_warnings"]),
                        r["_warnings"])

    def test_missing_schema_field_is_not_a_warning(self):
        proc, r = self._result()
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertNotIn("_warnings", r)

    def test_next_session_id_convention(self):
        (self.data / "session-log.json").write_text(json.dumps({
            "sessions": [{"session_id": "session-007"}], "milestones": [],
        }))
        _, r = self._result()
        self.assertEqual(r["computed"]["next_session_id"], "session-008")

    def test_steps_precision_absent_without_records(self):
        _, r = self._result()
        self.assertIsNone(r["computed"]["steps_precision"])

    def test_steps_precision_from_records(self):
        # WP4.1: the .records steps traces (agent.ts appendBankRecord shape)
        # feed per-step precision + calculation fluency.
        recs = [
            # v1 whole-trace: step 2 failed, step 3 is the cascade (not an attempt)
            {"record_id": "s1:bank:1", "session_id": "session-001", "skill": "steps",
             "score": 3, "steps": [{"n": 1, "ok": True, "got": "a"},
                                   {"n": 2, "ok": False, "got": "b"},
                                   {"n": 3, "ok": False, "got": "c", "propagated": True}]},
            # v2 clean: every step right on the first try
            {"record_id": "s1:bank:2", "session_id": "session-001", "skill": "steps",
             "score": 10, "steps": [{"n": 1, "ok": True, "got": "a"},
                                    {"n": 2, "ok": True, "got": "b"}]},
            # duplicate record_id must not double-count
            {"record_id": "s1:bank:2", "session_id": "session-001", "skill": "steps",
             "score": 10, "steps": [{"n": 1, "ok": True}]},
            # a compute record is not a steps trace
            {"record_id": "s1:bank:3", "session_id": "session-001", "skill": "computation",
             "score": 10},
        ]
        (self.data / ".records").mkdir()
        (self.data / ".records" / "session-001.jsonl").write_text(
            "\n".join(json.dumps(r) for r in recs) + "\n")
        _, r = self._result()
        sp = r["computed"]["steps_precision"]
        self.assertEqual(sp["items"], 2)
        by_n = {e["n"]: e for e in sp["per_step"]}
        self.assertEqual(by_n[1], {"n": 1, "seen": 2, "ok_rate": 100.0})
        self.assertEqual(by_n[2], {"n": 2, "seen": 2, "ok_rate": 50.0})
        self.assertNotIn(3, by_n)  # propagated step is not an attempt
        self.assertEqual(sp["first_try_rate"], 50.0)
        self.assertEqual(sp["retry_rate"], 0.0)
        self.assertEqual(sp["revealed_rate"], 50.0)


if __name__ == "__main__":
    unittest.main()
