#!/usr/bin/env python3
"""Taxonomy per domain (WP6, 2026-10-08).

Skills, error categories and their fallbacks belong to the DOMAIN of the
profile. Until now the core carried only the math ones, so a language learner's
grammar became "computation" (Càlcul in her Stats), her vocabulary "facts", and
a slip like "I went" was stored as `calculation_I_went`. Here: the Python side
(db_schema, persist-session, domain_for_dir) and the guard that keeps it in
sync with its TS mirror (server/src/taxonomy.ts).
"""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / "hooks"
sys.path.insert(0, str(HOOKS))

import db_schema as D  # noqa: E402
from domain import domain_for_dir  # noqa: E402

TS = (REPO_ROOT / "server" / "src" / "taxonomy.ts").read_text(encoding="utf-8")


def _ts_array(name):
    m = re.search(r"export const %s = \[(.*?)\] as const;" % name, TS, re.S)
    assert m, name
    return tuple(re.findall(r'"([^"]+)"', m.group(1)))


def _ts_map(name):
    m = re.search(r"export const %s: Record<string, string> = \{(.*?)\n\};" % name, TS, re.S)
    assert m, name
    pairs = re.findall(r'(?:"([^"]+)"|([A-Za-z_]+))\s*:\s*"([^"]+)"', m.group(1))
    return {(a or b): c for a, b, c in pairs}


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LanguageTaxonomyTest(unittest.TestCase):
    def test_language_skill_stays_language(self):
        self.assertEqual(D.normalize_skill_key("grammar", "language"), "grammar")
        self.assertEqual(D.normalize_skill_key("vocabulary", "language"), "vocabulary")
        self.assertEqual(D.normalize_skill_key("writing", "language"), "writing")

    def test_math_default_is_unchanged(self):
        # every old call site (no domain) keeps meaning math
        self.assertEqual(D.normalize_skill_key("grammar"), "computation")
        self.assertEqual(D.normalize_skill_key("raonament"), "reasoning")
        self.assertEqual(D.normalize_error_category("zzz"), "calculation")
        self.assertEqual(D.normalize_error_category("carrying"), "carrying")

    def test_a_math_key_never_invents_a_math_skill_in_language(self):
        for raw in D.SKILL_KEYS:
            self.assertIn(D.normalize_skill_key(raw, "language"), D.LANGUAGE_SKILL_KEYS)

    def test_language_categories_and_fallback(self):
        self.assertEqual(D.normalize_error_category("tenses", "language"), "tenses")
        self.assertEqual(D.normalize_error_category("verb tense", "language"), "tenses")
        self.assertEqual(D.normalize_error_category("zzz", "language"), "grammar")
        # a math label is not a language category: it falls to the domain default
        self.assertEqual(D.normalize_error_category("calculation", "language"), "grammar")
        self.assertEqual(D.normalize_error_category("gerund", "language"), "gerund")

    def test_domain_lists(self):
        self.assertEqual(D.skill_keys("language"), D.LANGUAGE_SKILL_KEYS)
        self.assertEqual(D.skill_keys("math"), D.SKILL_KEYS)
        self.assertEqual(D.error_categories("language"), D.LANGUAGE_ERROR_CATEGORIES)
        self.assertEqual(D.default_skill_key("language"), "writing")
        self.assertEqual(D.default_error_category("language"), "grammar")
        self.assertEqual(D.default_error_category("math"), "calculation")


class TsMirrorTest(unittest.TestCase):
    """server/src/taxonomy.ts must say what db_schema.py says."""

    def test_skill_keys(self):
        self.assertEqual(_ts_array("LANGUAGE_SKILL_KEYS"), D.LANGUAGE_SKILL_KEYS)

    def test_error_categories(self):
        self.assertEqual(_ts_array("LANGUAGE_ERROR_CATEGORIES"), D.LANGUAGE_ERROR_CATEGORIES)
        self.assertEqual(_ts_array("LANGUAGE_OLD_CATEGORIES"), D.LANGUAGE_OLD_CATEGORIES)

    def test_aliases(self):
        self.assertEqual(_ts_map("LANGUAGE_CATEGORY_ALIASES"), D.LANGUAGE_ERROR_CATEGORY_ALIASES)
        self.assertEqual(_ts_map("LANGUAGE_SKILL_ALIASES"), D.LANGUAGE_SKILL_ALIASES)
        self.assertEqual(_ts_map("MATH_TO_LANGUAGE_SKILL"), D.MATH_TO_LANGUAGE_SKILL)

    def test_defaults(self):
        self.assertIn(f'DEFAULT_LANGUAGE_SKILL_KEY = "{D.DEFAULT_LANGUAGE_SKILL_KEY}"', TS)
        self.assertIn(f'DEFAULT_LANGUAGE_ERROR_CATEGORY = "{D.DEFAULT_LANGUAGE_ERROR_CATEGORY}"', TS)


class DomainOfDirTest(unittest.TestCase):
    def _dir(self, body):
        d = tempfile.mkdtemp()
        (Path(d) / "learner-profile.json").write_text(json.dumps(body), encoding="utf-8")
        return d

    def test_by_level(self):
        self.assertEqual(domain_for_dir(self._dir({"learner": {"current_level": "A1"}})), "language")
        self.assertEqual(domain_for_dir(self._dir({"learner": {"current_level": "m7"}})), "math")

    def test_explicit_and_missing(self):
        self.assertEqual(domain_for_dir(self._dir({"domain": "language"})), "language")
        self.assertEqual(domain_for_dir(tempfile.mkdtemp()), "math")  # no profile: the default


class PersistenceTest(unittest.TestCase):
    """What the records of a session become in the databases."""

    @classmethod
    def setUpClass(cls):
        cls.ps = _load("ps_taxonomy", "persist-session.py")

    RECORDS = [
        {"skill": "grammar", "exercise": "I go to school yesterday", "learner_answer": "I go", "score": 5,
         "corrections": [{"wrong": "I go", "right": "I went", "category": "tenses"}]},
        {"skill": "vocabulary", "exercise": "brush", "learner_answer": "brosh", "score": 3,
         "corrections": [{"wrong": "brosh", "right": "brush", "category": "spelling"}]},
    ]

    def test_language_records_keep_their_skills_and_categories(self):
        ex, errs, _ = self.ps.records_to_payload(self.RECORDS, "language")
        self.assertEqual([e["type"] for e in ex], ["grammar", "vocabulary"])
        self.assertEqual([e["category"] for e in errs], ["tenses", "spelling"])

    def test_the_same_records_in_math_keep_the_old_mapping(self):
        ex, _, _ = self.ps.records_to_payload(self.RECORDS)
        self.assertEqual([e["type"] for e in ex], ["computation", "facts"])

    def test_an_unknown_language_label_is_grammar_not_calculation(self):
        rec = [{"skill": "writing", "exercise": "x", "learner_answer": "y", "score": 4,
                "corrections": [{"wrong": "a", "right": "b", "category": "whatever"}]}]
        _, errs, _ = self.ps.records_to_payload(rec, "language")
        self.assertEqual(errs[0]["category"], "grammar")
        self.assertTrue(errs[0]["pattern_id"].startswith("grammar_"))


if __name__ == "__main__":
    unittest.main()
