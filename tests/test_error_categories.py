#!/usr/bin/env python3
"""Error-category taxonomy: one list, three surfaces, and it must stay one.

The tutor's prompts, the deep evaluator's rubric and the transcript parser each
used to carry their own list. Anything the parser did not recognize became
the default category silently, so mistakes-db collapsed into a single category.
These tests fail the moment the three drift apart again.

WP1.4 replaced the 15 FlowEd grammar categories with the 12 math classes of
docs/DISSENY-MATEMATIQUES.md §4.4; the machinery (SSOT + aliases + sync test)
is the same one the language fork shipped with.
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
        self.assertEqual(db_schema.normalize_error_category("order-of-operations"), "order_of_operations")
        self.assertEqual(db_schema.normalize_error_category("Order Of Operations"), "order_of_operations")
        self.assertEqual(db_schema.normalize_error_category(" WRONG_OPERATION "), "wrong_operation")

    def test_aliases(self):
        # The tutor names the slip in everyday words, in any of the three
        # languages a Catalan classroom mixes.
        self.assertEqual(db_schema.normalize_error_category("signe"), "sign")
        self.assertEqual(db_schema.normalize_error_category("transport"), "carrying")
        self.assertEqual(db_schema.normalize_error_category("ordre d'operacions"), "order_of_operations")
        self.assertEqual(db_schema.normalize_error_category("taula"), "facts")
        self.assertEqual(db_schema.normalize_error_category("simplificació"), "simplification")
        self.assertEqual(db_schema.normalize_error_category("valor posicional"), "place_value")
        self.assertEqual(db_schema.normalize_error_category("càlcul"), "calculation")
        self.assertEqual(db_schema.normalize_error_category("incomplet"), "incomplete")

    def test_every_alias_lands_on_a_canonical_category(self):
        for alias, canon in db_schema.ERROR_CATEGORY_ALIASES.items():
            self.assertIn(canon, db_schema.ERROR_CATEGORIES, f"alias {alias!r}")
            self.assertEqual(db_schema.normalize_error_category(alias), canon)

    def test_legacy_language_categories_are_accepted_but_deprecated(self):
        # Stored language-era ids (and the #tags of the language curriculum
        # files still shipped in the fork) keep their shape instead of
        # collapsing into the default. The tutor-facing surfaces do not offer
        # them; see LEGACY_ERROR_CATEGORIES in db_schema.py. One language name
        # is deliberately redirected to its math counterpart by an alias:
        # "comprehension" → "misread".
        aliased = set(db_schema.ERROR_CATEGORY_ALIASES)
        for cat in db_schema.LEGACY_ERROR_CATEGORIES:
            if cat in aliased:
                continue
            self.assertEqual(db_schema.normalize_error_category(cat), cat)
        self.assertEqual(db_schema.normalize_error_category("comprehension"), "misread")
        self.assertNotIn("grammar", db_schema.ERROR_CATEGORIES)

    def test_unknown_falls_back(self):
        self.assertEqual(db_schema.normalize_error_category("correct verb form"), "calculation")
        self.assertEqual(db_schema.normalize_error_category(""), "calculation")
        self.assertEqual(db_schema.DEFAULT_ERROR_CATEGORY, "calculation")


class SurfacesInSyncTest(unittest.TestCase):
    def test_server_category_list_matches_python(self):
        """tools.ts drives both the deep rubric and math_record_answer's
        validation from one array; it must equal the Python source of truth."""
        src = (REPO_ROOT / "server" / "src" / "tools.ts").read_text(encoding="utf-8")
        m = re.search(r"export const ERROR_CATEGORIES = \[(.*?)\] as const;", src, re.S)
        self.assertIsNotNone(m, "tools.ts has no ERROR_CATEGORIES array")
        listed = re.findall(r'"([a-z_]+)"', m.group(1))
        self.assertEqual(listed, list(db_schema.ERROR_CATEGORIES))

    def test_server_alias_map_matches_python(self):
        """normalizeCategory's aliases must be the same map as
        ERROR_CATEGORY_ALIASES, or the tool rejects what the parser accepts."""
        src = (REPO_ROOT / "server" / "src" / "tools.ts").read_text(encoding="utf-8")
        m = re.search(r"const aliases: Record<string, string> = \{(.*?)\};", src, re.S)
        self.assertIsNotNone(m, "tools.ts has no aliases map")
        listed = dict(re.findall(r'"([^"]+)":\s*"([a-z_]+)"', m.group(1)))
        self.assertEqual(listed, db_schema.ERROR_CATEGORY_ALIASES)

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
        pats = self._patterns('- 🟡 "24 + 7 = 21" → **"24 + 7 = 31"** (carrying — the carried 1 was dropped)')
        self.assertEqual(len(pats), 1)
        self.assertEqual(pats[0]["category"], "carrying")

    def test_hyphenated_category_is_normalized(self):
        pats = self._patterns('- 🔴 "3 + 2 × 4 = 20" → **"3 + 2 × 4 = 11"** (order-of-operations — multiply before adding)')
        self.assertEqual(len(pats), 1)
        self.assertEqual(pats[0]["category"], "order_of_operations")

    def test_writing_skill_template_uses_the_parseable_shape(self):
        skill = (REPO_ROOT / "skills/math-writing/SKILL.md").read_text(encoding="utf-8")
        self.assertIn('- 🔴 "{wrong}" → **"{correct}"** ({category} — {why})', skill)
        self.assertNotIn('- {issue}: "{wrong}" → **"{correct}"** — {why}', skill)


if __name__ == "__main__":
    unittest.main()
