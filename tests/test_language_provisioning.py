#!/usr/bin/env python3
"""A language profile is provisioned from the language domain's own templates
(WP6, 2026-10-08): new-user.sh --domain language + flowed-profile.py --domain
language. Before, every new profile was seeded from the MATH templates, so a
language learner started with Càlcul/Passos/Fets in her databases."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))
from domain import domain_for_dir  # noqa: E402
import db_schema  # noqa: E402


def run(*args, home):
    env = dict(os.environ, FLOWED_HOME=str(home))
    return subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)


class LanguageProvisioningTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def _make(self, pid, domain):
        r = run("bash", "scripts/new-user.sh", pid, "--domain", domain, "--port", "4999", home=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return self.home / pid

    def test_language_profile_starts_with_language_skills_only(self):
        d = self._make("test-ana", "language")
        for fname, key in (("mastery-db.json", "skills"), ("progress-db.json", "skill_progress"),
                           ("learner-profile.json", "skills")):
            skills = set(json.loads((d / fname).read_text())[key])
            self.assertTrue(skills <= set(db_schema.LANGUAGE_SKILL_KEYS), (fname, skills))
            self.assertFalse(skills & set(db_schema.SKILL_KEYS), (fname, skills))

    def test_flowed_profile_sets_domain_levels_and_target(self):
        d = self._make("test-ana", "language")
        r = run(sys.executable, "scripts/flowed-profile.py", "test-ana", "--domain", "language", "--name", "Ana",
                "--native", "Catalan", "--target", "English", "--level", "a1", "--goal", "A2", home=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        prof = json.loads((d / "learner-profile.json").read_text())
        self.assertEqual(prof["domain"], "language")
        self.assertEqual((prof["learner"]["current_level"], prof["learner"]["target_level"]), ("A1", "A2"))
        self.assertEqual(prof["learner"]["target_language"], "English")
        self.assertEqual(domain_for_dir(d), "language")

    def test_a_language_profile_refuses_a_math_level(self):
        self._make("test-ana", "language")
        r = run(sys.executable, "scripts/flowed-profile.py", "test-ana", "--level", "m4", home=self.home)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("A1", r.stdout + r.stderr)

    def test_a_language_profile_needs_its_target_language(self):
        self._make("test-ana", "language")
        r = run(sys.executable, "scripts/flowed-profile.py", "test-ana", "--domain", "language", "--native", "Catalan",
                home=self.home)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--target", r.stdout + r.stderr)

    def test_math_stays_as_it_was(self):
        d = self._make("test-nes", "math")
        r = run(sys.executable, "scripts/flowed-profile.py", "test-nes", "--name", "Nes", "--native", "Catalan",
                "--level", "m7", "--goal", "m7", home=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        prof = json.loads((d / "learner-profile.json").read_text())
        self.assertEqual(prof["learner"]["current_level"], "m7")
        self.assertEqual(prof["learner"]["target_language"], "Math")
        self.assertEqual(domain_for_dir(d), "math")

    def test_taxonomy_check_passes_on_a_fresh_profile_and_fails_on_a_mixed_one(self):
        d = self._make("test-ana", "language")
        run(sys.executable, "scripts/flowed-profile.py", "test-ana", "--domain", "language", "--name", "Ana",
            "--native", "Catalan", "--target", "English", "--level", "A1", "--goal", "A2", home=self.home)
        ok = run(sys.executable, "scripts/flowed-check.py", "taxonomy", "--dir", str(d), home=self.home)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        m = json.loads((d / "mastery-db.json").read_text())
        m["skills"]["computation"] = {"mastery_level": 1}
        (d / "mastery-db.json").write_text(json.dumps(m))
        bad = run(sys.executable, "scripts/flowed-check.py", "taxonomy", "--dir", str(d), home=self.home)
        self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
        self.assertIn("computation", bad.stdout)


if __name__ == "__main__":
    unittest.main()
