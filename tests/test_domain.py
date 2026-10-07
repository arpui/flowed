#!/usr/bin/env python3
"""
Tests for hooks/domain.py (WP5.2): the domain manifest is the single authority
for which domain a profile is — explicit field, then level-scale inference,
then the manifest default.
"""
import json
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "hooks"))

import domain as dm  # noqa: E402


class DomainTest(unittest.TestCase):
    def test_manifest_is_readable(self):
        m = dm.manifest()
        self.assertIn("language", m["domains"])
        self.assertIn("math", m["domains"])
        self.assertEqual("math", m["default"])

    def test_level_scale_infers_the_domain(self):
        self.assertEqual("language", dm.domain_for_level("A2"))
        self.assertEqual("math", dm.domain_for_level("m7"))
        self.assertIsNone(dm.domain_for_level(""))
        self.assertIsNone(dm.domain_for_level("zz"))

    def test_explicit_field_wins_over_the_level(self):
        p = {"domain": "language", "learner": {"current_level": "m4"}}
        self.assertEqual("language", dm.domain_for_profile(p))

    def test_math_profile_without_a_domain_field_stays_math(self):
        p = {"learner": {"current_level": "m4", "target_level": "m7"}}
        self.assertEqual("math", dm.domain_for_profile(p))

    def test_language_profile_infers_language(self):
        p = {"learner": {"current_level": "A1", "target_language": "Dutch"}}
        self.assertEqual("language", dm.domain_for_profile(p))

    def test_profile_without_clues_gets_the_default(self):
        self.assertEqual("math", dm.domain_for_profile({}))

    def test_spec_carries_the_adapter(self):
        s = dm.spec("math")
        self.assertEqual("math", s["command_prefix"])
        self.assertIn("m7", s["level_scale"])
        self.assertFalse(s["tts"])
        l = dm.spec("language")
        self.assertEqual("fluent", l["command_prefix"])
        self.assertTrue(l["tts"])


if __name__ == "__main__":
    unittest.main()
