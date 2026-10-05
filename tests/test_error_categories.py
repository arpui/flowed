#!/usr/bin/env python3
"""Error-category taxonomy: one list, three surfaces, and it must stay one.

The tutor's prompts, the deep evaluator's rubric and the transcript parser each
used to carry their own list. Anything the parser did not recognize became
"grammar" silently, so mistakes-db collapsed into a single category. These tests
fail the moment the three drift apart again.
"""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / "hooks"
sys.path.insert(0, str(HOOKS))

import db_schema  # noqa: E402


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NormalizeTest(unittest.TestCase):
    def test_canonical_names_pass_through(self):
        for cat in db_schema.ERROR_CATEGORIES:
            self.assertEqual(db_schema.normalize_error_category(cat), cat)

    def test_hyphens_spaces_and_case(self):
        self.assertEqual(db_schema.normalize_error_category("word-order"), "word_order")
        self.assertEqual(db_schema.normalize_error_category("Word Order"), "word_order")
        self.assertEqual(db_schema.normalize_error_category(" FORMAL_INFORMAL "), "formal_informal")

    def test_aliases(self):
        self.assertEqual(db_schema.normalize_error_category("preposition"), "prepositions")
        self.assertEqual(db_schema.normalize_error_category("pronoun"), "pronouns")
        self.assertEqual(db_schema.normalize_error_category("inference"), "comprehension")

    def test_unknown_falls_back(self):
        self.assertEqual(db_schema.normalize_error_category("correct verb form"), "grammar")
        self.assertEqual(db_schema.normalize_error_category(""), "grammar")


class SurfacesInSyncTest(unittest.TestCase):
    def test_server_category_list_matches_python(self):
        """tools.ts drives both the deep rubric and math_record_answer's
        validation from one array; it must equal the Python source of truth."""
        src = (REPO_ROOT / "server" / "src" / "tools.ts").read_text(encoding="utf-8")
        m = re.search(r"export const ERROR_CATEGORIES = \[(.*?)\] as const;", src, re.S)
        self.assertIsNotNone(m, "tools.ts has no ERROR_CATEGORIES array")
        listed = re.findall(r'"([a-z_]+)"', m.group(1))
        self.assertEqual(listed, list(db_schema.ERROR_CATEGORIES))

    def test_rubric_and_tool_schema_are_derived_from_that_array(self):
        src = (REPO_ROOT / "server" / "src" / "tools.ts").read_text(encoding="utf-8")
        self.assertIn("Allowed categories: ${ERROR_CATEGORIES.join(\", \")}", src,
                      "the deep rubric no longer derives its category list")
        self.assertIn("One of: ${ERROR_CATEGORIES.join(\", \")}", src,
                      "math_record_answer no longer documents the canonical list")

    def test_prompt_surfaces_document_every_category(self):
        for rel in (
            "skills/math-feedback-formatter/SKILL.md",
            "references/feedback-template.md",
        ):
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for cat in db_schema.ERROR_CATEGORIES:
                self.assertIn(f"- `{cat}` —", text, f"{rel} does not document `{cat}`")


class WritingFeedbackIsParseableTest(unittest.TestCase):
    """Regression: the math-writing variant used to lose every error."""

    @classmethod
    def setUpClass(cls):
        cls.ps = _load("ps_categories", "persist-session.py")

    def _patterns(self, body):
        return self.ps.parse_error_patterns([("assistant", body + "\n\n**Score: 6/10**\n")])

    def test_canonical_line_is_captured_with_its_category(self):
        pats = self._patterns('- 🟡 "in Monday" → **"on Monday"** (prepositions — days take "on")')
        self.assertEqual(len(pats), 1)
        self.assertEqual(pats[0]["category"], "prepositions")

    def test_hyphenated_category_is_normalized(self):
        pats = self._patterns('- 🔴 "I yesterday went" → **"I went yesterday"** (word-order — adverb last)')
        self.assertEqual(len(pats), 1)
        self.assertEqual(pats[0]["category"], "word_order")

    def test_writing_skill_template_uses_the_parseable_shape(self):
        skill = (REPO_ROOT / "skills/math-writing/SKILL.md").read_text(encoding="utf-8")
        self.assertIn('- 🔴 "{wrong}" → **"{correct}"** ({category} — {why})', skill)
        self.assertNotIn('- {issue}: "{wrong}" → **"{correct}"** — {why}', skill)


if __name__ == "__main__":
    unittest.main()
