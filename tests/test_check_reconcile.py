"""flowed-check reconcile: records vs the derived DBs (read-only)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "scripts" / "flowed-check.py"


def _w(d, name, obj):
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


def _run(d):
    return subprocess.run([sys.executable, str(CHECK), "reconcile", "--dir", str(d)],
                          capture_output=True, text=True)


class Reconcile(unittest.TestCase):
    def _profile(self, d):
        _w(d, "learner-profile.json", {"domain": "language", "level": "A1"})
        (d / ".records").mkdir()
        recs = [
            {"record_id": "r1", "ts": 1, "skill": "grammar", "score": 10, "item_id": "a1.x.001", "sm2_quality": 5},
            {"record_id": "r2", "ts": 2, "skill": "vocabulary", "score": 4, "corrections": [{"x": 1}]},
        ]
        (d / ".records" / "2026-10-08.jsonl").write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")

    def test_records_missing_from_dbs_fail(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._profile(d)
            _w(d, "progress-db.json", {"overall_stats": {"total_exercises": 0}})
            r = _run(d)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("progress-db.json", r.stdout)

    def test_consistent_dbs_pass(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._profile(d)
            _w(d, "progress-db.json", {"overall_stats": {"total_exercises": 2}})
            _w(d, "mastery-db.json", {"skills": {"grammar": {"last_practiced": "2026-10-08"},
                                                  "vocabulary": {"last_practiced": "2026-10-08"}}})
            _w(d, "session-log.json", {"sessions": [{"session_id": "001", "exercises_completed": 2}]})
            _w(d, "mistakes-db.json", {"error_patterns": {"p1": {"category": "tenses"}}})
            _w(d, "spaced-repetition.json", {"items": {"a1.x.001": {"repetitions": 1}}})
            r = _run(d)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("✅", r.stdout)

    def test_foreign_category_flagged(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._profile(d)
            _w(d, "progress-db.json", {"overall_stats": {"total_exercises": 2}})
            _w(d, "mastery-db.json", {"skills": {"grammar": {"last_practiced": "x"}, "vocabulary": {"last_practiced": "x"}}})
            _w(d, "session-log.json", {"sessions": [{"session_id": "001", "exercises_completed": 2}]})
            _w(d, "mistakes-db.json", {"error_patterns": {"p1": {"category": "calculation"}}})
            _w(d, "spaced-repetition.json", {"items": {"a1.x.001": {}}})
            r = _run(d)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("taxonomia", r.stdout)


class Reconcile2(unittest.TestCase):
    def _base(self, d, ts_ms, item="grammar_There_is_a_book_on_t"):
        _w(d, "learner-profile.json", {"domain": "language", "level": "A1"})
        (d / ".records").mkdir()
        recs = [{"record_id": "r1", "ts": ts_ms, "skill": "grammar", "score": 10, "item_id": item, "sm2_quality": 5}]
        (d / ".records" / "ses_L.jsonl").write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
        _w(d, "progress-db.json", {"overall_stats": {"total_exercises": 1}})
        _w(d, "mastery-db.json", {"skills": {"grammar": {"last_practiced": "x"}}})
        _w(d, "session-log.json", {"sessions": [{"session_id": "session-001", "date": "2026-10-08", "exercises_completed": 1}]})
        _w(d, "mistakes-db.json", {"error_patterns": {}})
        _w(d, "spaced-repetition.json", {"items": {}})
        _w(d, "session-draft.json", {"live_session": "ses_L", "session_id": "session-001"})

    def test_old_unknown_sm2_item_is_a_warning_not_a_failure(self):
        import time
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._base(d, int((time.time() - 30 * 86400) * 1000))
            r = _run(d)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("sense entrada a SM-2", r.stdout)

    def test_fresh_unknown_sm2_item_fails(self):
        import time
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._base(d, int(time.time() * 1000))
            r = _run(d)
            self.assertEqual(r.returncode, 1, r.stdout)

    def test_last_session_with_fewer_exercises_than_records_fails(self):
        import time
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._base(d, int(time.time() * 1000), item="")
            _w(d, "session-log.json", {"sessions": [{"session_id": "session-001", "exercises_completed": 0}]})
            r = _run(d)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("resposta perduda", r.stdout)

    def test_prose_only_answers_are_reported_not_failed(self):
        import time
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._base(d, int(time.time() * 1000), item="")
            _w(d, "session-log.json", {"sessions": [{"session_id": "session-001", "exercises_completed": 3}]})
            r = _run(d)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("només en prosa", r.stdout)


if __name__ == "__main__":
    unittest.main()
