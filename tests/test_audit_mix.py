#!/usr/bin/env python3
"""scripts/flowed-audit-mix.py: a profile must hold data of its own domain only.

Fake profiles in a temp dir, the script run as a subprocess (its real CLI), and
the output and exit code checked. Also: the run writes nothing.
"""
import json
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "flowed-audit-mix.py"


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def make_sessions_db(path: Path, titles) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE session (id text PRIMARY KEY, title text NOT NULL DEFAULT 'FlowMath')")
    con.executemany("INSERT INTO session (id, title) VALUES (?, ?)", [(f"s{i}", t) for i, t in enumerate(titles)])
    con.commit()
    con.close()


def language_profile(home: Path, pid: str = "alex-en") -> Path:
    p = home / pid
    write_json(p / "learner-profile.json", {
        "domain": "language", "learner": {"name": "Alex", "current_level": "A1", "target_level": "A2"}})
    write_json(p / "mistakes-db.json", {"patterns": [{"id": "grammar_past_simple", "category": "grammar", "skill": "grammar"}]})
    write_json(p / "spaced-repetition.json", {"items": [{"id": "a1.present_simple", "competence": "a1.present_simple"}]})
    write_json(p / "mastery-db.json", {"skills": {"vocabulary": {"stars": 2}, "writing": {"stars": 1}}})
    write_json(p / "flash-db.json", {"lists": [{"id": "en-A1.flash.family", "done": 3}]})
    (p / "results").mkdir(parents=True, exist_ok=True)
    (p / "results" / "alex-learn-session-001.md").write_text(
        "# Language Learning Session - session-001\n\n## Summary\nQuestions: 4\n", encoding="utf-8")
    make_sessions_db(p / "sessions" / "sessions.db", ["FlowEd · Language", "FlowEd · Language"])
    return p


def math_profile(home: Path, pid: str = "test-math") -> Path:
    p = home / pid
    write_json(p / "learner-profile.json", {
        "domain": "math", "learner": {"name": "Test", "current_level": "m5", "target_level": "m6"}})
    write_json(p / "mistakes-db.json", {"patterns": [{"id": "calculation_3x4", "category": "calculation", "skill": "computation"}]})
    write_json(p / "spaced-repetition.json", {"items": [{"id": "m5.area_perimeter", "competence": "m5.area_perimeter"}]})
    write_json(p / "mastery-db.json", {"skills": {"computation": {"stars": 3}, "facts": {"stars": 2}}})
    write_json(p / "flash-db.json", {"lists": [{"id": "math-m5.flash.taules", "done": 1}]})
    (p / "results").mkdir(parents=True, exist_ok=True)
    (p / "results" / "test-learn-session-001.md").write_text(
        "# Math Learning Session - session-001\n\n## Summary\nQuestions: 5\n", encoding="utf-8")
    make_sessions_db(p / "sessions" / "sessions.db", ["FlowEd · Math"])
    return p


def run(home: Path, *args: str):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--home", str(home), *args],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


class AuditMixTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "flowed"
        self.home.mkdir()

    def test_clean_profiles_are_ok_and_exit_zero(self):
        language_profile(self.home)
        math_profile(self.home)
        code, out, err = run(self.home)
        self.assertEqual(code, 0, out + err)
        self.assertIn("alex-en  [domain: language, from explicit field]\n  OK", out)
        self.assertIn("test-math  [domain: math, from explicit field]\n  OK", out)
        self.assertIn("checked 2 profile(s): 2 OK, 0 suspicious", out)

    def test_math_category_in_language_mistakes_db_is_flagged(self):
        p = language_profile(self.home)
        write_json(p / "mistakes-db.json", {"patterns": [
            {"id": "grammar_past_simple", "category": "grammar", "skill": "grammar"},
            {"id": "calculation_3x4", "category": "calculation", "skill": "grammar"},
        ]})
        code, out, _ = run(self.home, "alex-en")
        self.assertEqual(code, 1, out)
        self.assertIn("SUSPICIOUS", out)
        self.assertIn("mistakes-db.json  patterns[1].category  \"calculation\"  (math error category)", out)
        self.assertIn("mistakes-db.json  patterns[1].id  \"calculation_3x4\"  (math pattern id (category calculation))", out)
        self.assertNotIn("patterns[0]", out)

    def test_math_skill_competence_and_flash_id_in_language_profile(self):
        p = language_profile(self.home)
        write_json(p / "mastery-db.json", {"skills": {"computation": {"stars": 1}}})
        write_json(p / "spaced-repetition.json", {"items": [{"id": "m7.integers", "competence": "m7.integers"}]})
        write_json(p / "flash-db.json", {"lists": [{"id": "math-m5.flash.taules"}]})
        code, out, _ = run(self.home, "alex-en")
        self.assertEqual(code, 1, out)
        self.assertIn('mastery-db.json  skills.computation (key)  "computation"  (math skill key)', out)
        self.assertIn('spaced-repetition.json  items[0].competence  "m7.integers"  (math competence id)', out)
        self.assertIn('flash-db.json  lists[0].id  "math-m5.flash.taules"  (math Flash list id)', out)

    def test_language_ids_in_math_profile(self):
        p = math_profile(self.home)
        write_json(p / "progress-db.json", {"skills": {"vocabulary": {"done": 4}}})
        write_json(p / "flash-db.json", {"lists": [{"id": "en-A1.flash.family"}]})
        code, out, _ = run(self.home, "test-math")
        self.assertEqual(code, 1, out)
        self.assertIn('progress-db.json  skills.vocabulary (key)  "vocabulary"  (language error category)', out)
        self.assertIn('flash-db.json  lists[0].id  "en-A1.flash.family"  (language Flash list id)', out)

    def test_foreign_brand_in_session_title_is_flagged(self):
        p = math_profile(self.home)
        make_sessions_db(p / "sessions" / "sessions.db", ["FlowEd · Math", "FlowEd · Language"])
        code, out, _ = run(self.home, "test-math")
        self.assertEqual(code, 1, out)
        self.assertIn('sessions/sessions.db  session[s1].title  "FlowEd · Language"  (other domain\'s brand', out)
        self.assertNotIn("session[s0]", out)

    def test_results_files_are_not_checked(self):
        # persist-session.py names every domain's results "-math-learn-" (core naming): not a finding.
        p = language_profile(self.home)
        (p / "results" / "alex-math-learn-session-002.md").write_text(
            "# Math Learning Session - session-002\n", encoding="utf-8")
        code, out, _ = run(self.home, "alex-en")
        self.assertEqual(code, 0, out)
        self.assertNotIn("results/", out)

    def test_domain_field_contradicting_levels_is_flagged(self):
        p = math_profile(self.home)
        write_json(p / "learner-profile.json", {
            "domain": "math", "learner": {"name": "Test", "current_level": "A1", "target_level": "A2"}})
        code, out, _ = run(self.home, "test-math")
        self.assertEqual(code, 1, out)
        self.assertIn("learner-profile.json  domain  \"math\"  (domain field says math but the levels say language)", out)

    def test_unreadable_json_is_flagged(self):
        p = math_profile(self.home)
        (p / "mastery-db.json").write_text("{not json", encoding="utf-8")
        code, out, _ = run(self.home, "test-math")
        self.assertEqual(code, 1, out)
        self.assertIn("mastery-db.json  -", out)
        self.assertIn("unreadable", out)

    def test_ids_argument_limits_the_scan(self):
        language_profile(self.home)
        p = math_profile(self.home)
        write_json(p / "mistakes-db.json", {"patterns": [{"id": "grammar_x", "category": "grammar"}]})
        code, out, _ = run(self.home, "alex-en")
        self.assertEqual(code, 0, out)
        self.assertNotIn("test-math", out)
        code, out, _ = run(self.home, "test-math")
        self.assertEqual(code, 1, out)  # grammar in a math profile is the other domain's category

    def test_unknown_profile_id_is_a_usage_error(self):
        language_profile(self.home)
        code, out, err = run(self.home, "nobody")
        self.assertEqual(code, 2, out + err)
        self.assertIn("nobody", err)

    def test_missing_home_is_a_usage_error(self):
        code, _, err = run(self.root / "absent")
        self.assertEqual(code, 2, err)

    def test_run_writes_nothing(self):
        language_profile(self.home)
        p = math_profile(self.home)
        write_json(p / "mistakes-db.json", {"patterns": [{"id": "grammar_x", "category": "grammar"}]})

        def snapshot():
            return {
                str(f.relative_to(self.root)): (f.read_bytes(), f.stat().st_mtime_ns)
                for f in sorted(self.root.rglob("*")) if f.is_file()
            }

        before = snapshot()
        code, _, _ = run(self.home)
        self.assertEqual(code, 1)
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()
