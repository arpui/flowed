#!/usr/bin/env python3
"""WP3.1 — the math rubric seam (C3) and the math skill keys (C7).

The deep evaluator's rubric used to judge language ("fully communicative",
"judge in the target language") and its task enum was writing/speaking/
reading/scoring. WP3.1 replaces both with the math equivalents, and the
record's `skill` field — persisted into .records/ and re-read by update-db on
every persistence — must carry the five math keys, with the language-era
names mapped (read-old/write-new, the FLUENT_*→FLOWED_* pattern).

These tests pin:
  * the rubric text in tools.ts: math dimensions, the closed path's 10/7/3
    bands, no language-era judging phrases;
  * the open-task enum and its legacy map;
  * SKILL_KEYS / LEGACY_SKILL_KEYS / SKILL_SURFACE_ALIASES identical between
    hooks/db_schema.py and server/src/tools.ts (the TS mirror of the SSOT);
  * the prose parser's heading regex (pacing.ts) knows the math practices;
  * records_to_payload maps a stored language-era skill to its math key.
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


TOOLS_TS = (REPO_ROOT / "server" / "src" / "tools.ts").read_text(encoding="utf-8")
PACING_TS = (REPO_ROOT / "server" / "src" / "pacing.ts").read_text(encoding="utf-8")


_STR_LIT = re.compile(
    r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|`((?:[^`\\]|\\.)*)`'
)


def _rubric_text():
    """The DEEP_RUBRIC array's string literals (double, single or backtick),
    joined in order — the text the deep model actually reads."""
    m = re.search(r"export const DEEP_RUBRIC = \[(.*?)\]\.join", TOOLS_TS, re.S)
    assert m, "tools.ts has no exported DEEP_RUBRIC array"
    parts = [next(g for g in mt.groups() if g is not None) for mt in _STR_LIT.finditer(m.group(1))]
    return "\n".join(parts)


def _ts_map(decl_regex):
    """Extract a TS object literal as a dict; keys may be quoted or bare."""
    m = re.search(decl_regex, TOOLS_TS, re.S)
    assert m, f"tools.ts has no map matching {decl_regex!r}"
    return {k: v for k, v in re.findall(r'"?([A-Za-zà-ú\'-]+)"?:\s*"([a-z_-]+)"', m.group(1))}


class RubricTest(unittest.TestCase):
    def test_rubric_judges_the_four_math_dimensions(self):
        r = _rubric_text()
        for dim in ("answer:", "procedure:", "justification:", "communication:"):
            self.assertIn(dim, r)

    def test_rubric_maps_onto_the_closed_10_7_3_scale(self):
        # finalize_steps (hooks/bank.py) hands out 10 / 7 / 3; the open rubric
        # must speak the same bands or the two paths' scores are incomparable.
        r = _rubric_text()
        self.assertIn("10/7/3", r)
        self.assertIn("needed a retry", r)
        self.assertIn("needed revealing", r)

    def test_rubric_forbids_grading_the_learners_language(self):
        self.assertIn("never the language the answer is written in", _rubric_text())

    def test_rubric_has_no_language_era_phrases(self):
        r = _rubric_text()
        for gone in ("fully communicative", "communication breaks",
                     "judge in the target language", "partial communication"):
            self.assertNotIn(gone, r, gone)

    def test_rubric_categories_line_is_the_math_taxonomy(self):
        r = _rubric_text()
        self.assertIn("Allowed categories: ${ERROR_CATEGORIES.join(\", \")}", r)
        # the joined list itself must not name a language category
        listed = re.search(r"export const ERROR_CATEGORIES = \[(.*?)\] as const;", TOOLS_TS, re.S).group(1)
        for lang in ("grammar", "vocabulary", "spelling", "word_order"):
            self.assertNotIn(f'"{lang}"', listed)

    def test_bare_answer_without_reasoning_scores_low(self):
        self.assertRegex(_rubric_text(), r"0-4 = .*bare\s*answer with no reasoning")


class TaskEnumTest(unittest.TestCase):
    def test_the_four_open_task_kinds(self):
        m = re.search(r"export const DEEP_TASKS = \[(.*?)\] as const;", TOOLS_TS, re.S)
        self.assertIsNotNone(m, "tools.ts has no DEEP_TASKS array")
        listed = re.findall(r'"([a-z-]+)"', m.group(1))
        self.assertEqual(listed, ["explain", "error-analysis", "compare-strategies", "word-problem"])

    def test_legacy_task_names_are_mapped(self):
        mapped = _ts_map(r"const LEGACY_DEEP_TASKS: Record<string, string> = \{(.*?)\};")
        for old in ("writing", "speaking", "reading", "scoring"):
            self.assertIn(old, mapped, old)
        self.assertEqual(mapped["reading"], "word-problem")
        for canon in mapped.values():
            self.assertIn(canon, ["explain", "error-analysis", "compare-strategies", "word-problem"])


class SkillKeysTest(unittest.TestCase):
    def test_python_and_ts_agree_on_the_five_keys(self):
        m = re.search(r"export const SKILL_KEYS = \[(.*?)\] as const;", TOOLS_TS, re.S)
        self.assertIsNotNone(m, "tools.ts has no SKILL_KEYS array")
        listed = re.findall(r'"([a-z_]+)"', m.group(1))
        self.assertEqual(listed, list(db_schema.SKILL_KEYS))

    def test_python_and_ts_agree_on_the_legacy_skill_map(self):
        ts_map = _ts_map(r"const LEGACY_SKILL_KEYS: Record<string, string> = \{(.*?)\};")
        self.assertEqual(ts_map, db_schema.LEGACY_SKILL_KEYS)

    def test_python_and_ts_agree_on_the_surface_aliases(self):
        ts_map = _ts_map(r"const SKILL_SURFACE_ALIASES: Record<string, string> = \{(.*?)\};")
        self.assertEqual(ts_map, db_schema.SKILL_SURFACE_ALIASES)

    def test_normalize_skill_key(self):
        for key in db_schema.SKILL_KEYS:
            self.assertEqual(db_schema.normalize_skill_key(key), key)
        self.assertEqual(db_schema.normalize_skill_key("writing"), "reasoning")
        self.assertEqual(db_schema.normalize_skill_key("vocabulary"), "facts")
        self.assertEqual(db_schema.normalize_skill_key("reading"), "problems")
        self.assertEqual(db_schema.normalize_skill_key("grammar"), "computation")
        self.assertEqual(db_schema.normalize_skill_key("Raonament"), "reasoning")
        self.assertEqual(db_schema.normalize_skill_key("problemes"), "problems")
        self.assertEqual(db_schema.normalize_skill_key("unknown-thing"), db_schema.DEFAULT_SKILL_KEY)
        self.assertEqual(db_schema.normalize_skill_key(None), db_schema.DEFAULT_SKILL_KEY)

    def test_record_tool_documents_the_math_keys(self):
        self.assertIn("${SKILL_KEYS.join(\" | \")}", TOOLS_TS)
        self.assertNotIn("vocabulary | writing | speaking | reading | grammar", TOOLS_TS)


class ParserSurfaceTest(unittest.TestCase):
    def test_heading_regex_knows_the_math_practices(self):
        m = re.search(r"const SKILL_IN_HEADING_RE =\s*\n?\s*/(.*?)/im;", PACING_TS, re.S)
        self.assertIsNotNone(m, "pacing.ts has no SKILL_IN_HEADING_RE")
        body = m.group(1)
        for word in ("computation", "steps", "problems", "reasoning", "facts",
                     "raonament", "problema", "passos", "fets"):
            self.assertIn(word, body, word)

    def test_records_to_payload_maps_a_legacy_skill(self):
        ps = _load("ps_skills", "persist-session.py")
        recs = [
            {"record_id": "s:1", "skill": "writing", "score": 6, "corrections": []},
            {"record_id": "s:2", "skill": "vocabulary", "score": 9, "corrections": []},
            {"record_id": "s:3", "score": 8, "corrections": []},  # no skill at all
        ]
        exercises, _, _ = ps.records_to_payload(recs)
        self.assertEqual([e["type"] for e in exercises], ["reasoning", "facts", "computation"])


class E2EWiringTest(unittest.TestCase):
    def test_the_reasoning_scenario_is_wired(self):
        src = (REPO_ROOT / "scripts" / "flowed-e2e.py").read_text(encoding="utf-8")
        self.assertIn('if args.scenario == "reasoning":', src)
        self.assertIn("run_reasoning(args, cli, prof_dir, rep, quiet)", src)
        self.assertIn('"reasoning"', src)
        bench = (REPO_ROOT / "scripts" / "flowed-bench.sh").read_text(encoding="utf-8")
        self.assertIn("--reasoning", bench)


if __name__ == "__main__":
    unittest.main()
