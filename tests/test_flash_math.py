#!/usr/bin/env python3
"""Flash for math (docs/ENCARREC-FLASH-MATH.md §2, §5): the Python side counts the same
words as the server (server/src/flash.ts), and a math level with no level file has no
Flash requirement."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "hooks"))

import curriculum as cu  # noqa: E402

MATH_STEMS = sorted(p.name for p in (REPO_ROOT / "curriculum" / "flash").glob("math-*") if p.is_dir())


def server_math_lists() -> list[dict]:
    """The lists as server/src/flash.ts serves them (id and word ids), read by node."""
    script = (
        f"const m = await import({json.dumps(str(REPO_ROOT / 'server' / 'src' / 'flash.ts'))});"
        "const lists = m.loadFlashLists(" + json.dumps(str(REPO_ROOT)) + ", 'curriculum/flash/math-*', 'ca');"
        "console.log(JSON.stringify(lists.map((l) => ({ id: l.id, words: l.words.map((w) => w.id) }))));"
    )
    proc = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)


def python_math_lists(root: Path) -> list[dict]:
    out = []
    for stem in sorted(p.name for p in (root / "curriculum" / "flash").glob("math-*") if p.is_dir()):
        out.extend(cu.flash_lists(root, stem))
    return out


def write_math(root: Path, stem: str, files: dict[str, dict]) -> None:
    d = root / "curriculum" / "flash" / stem
    d.mkdir(parents=True)
    for name, body in files.items():
        (d / name).write_text(json.dumps(body), encoding="utf-8")


class MathListIds(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node is needed to read the server's lists")
    def test_python_ids_match_the_server_for_every_math_list(self):
        self.assertTrue(MATH_STEMS, "no math-* folder under curriculum/flash")
        self.assertEqual(python_math_lists(REPO_ROOT), server_math_lists())

    def test_m5_has_eight_tables_and_the_explicit_list(self):
        lists = {l["id"]: l["words"] for l in cu.flash_lists(REPO_ROOT, "math-m5")}
        self.assertEqual(len(lists), 9)
        self.assertEqual(lists["math-m5.flash.taula-7"], [f"7x{b}" for b in range(1, 11)])
        self.assertEqual(lists["math-m5.flash.2x1-xifres"][0], "23x4")
        self.assertEqual(len(lists["math-m5.flash.2x1-xifres"]), 12)


class MathRules(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="flash-math-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generate_drops_inexact_division_and_negative_results(self):
        write_math(self.tmp, "math-x1", {
            "01-div.json": {"id": "d", "level": "x1", "generate": {"op": ":", "a": [21], "b": [2, 3, 7]}},
            "02-minus.json": {"id": "m", "level": "x1", "generate": {"op": "-", "a": [3], "b": [5, 1]}},
        })
        lists = {l["id"]: l["words"] for l in cu.flash_lists(self.tmp, "math-x1")}
        self.assertEqual(lists, {"d": ["21d3", "21d7"], "m": ["3m1"]})

    def test_a_wrong_explicit_result_is_dropped_and_the_rest_stays(self):
        items = [
            {"id": "bad", "prompt": "23 × 4", "answer": ["91"]},
            {"id": "good", "prompt": "23 × 4", "answer": ["92"]},
            {"id": "open", "prompt": "Quants n'hi ha?", "answer": ["3"]},
        ]
        write_math(self.tmp, "math-x1", {"01-items.json": {"id": "i", "level": "x1", "items": items}})
        self.assertEqual(cu.flash_lists(self.tmp, "math-x1")[0]["words"], ["good", "open"])

    def test_a_file_with_generate_and_items_is_skipped(self):
        write_math(self.tmp, "math-x1", {"01-both.json": {"id": "b", "generate": {"op": "+", "a": [1], "b": [1]}, "items": []}})
        self.assertEqual(cu.flash_lists(self.tmp, "math-x1"), [])

    def test_a_new_generated_file_counts_with_no_code_change(self):
        write_math(self.tmp, "math-x1", {"01-new.json": {"id": "n", "generate": {"op": "×", "a": [3], "b": {"from": 1, "to": 3}}}})
        self.assertEqual(cu.flash_lists(self.tmp, "math-x1")[0]["words"], ["3x1", "3x2", "3x3"])

    def test_numbers_as_text_and_decimal_points(self):
        self.assertEqual(cu.math_numeric("72,0"), 72.0)
        self.assertEqual(cu.math_numeric(" 7 2 "), 72.0)
        self.assertIsNone(cu.math_numeric(""))
        self.assertIsNone(cu.math_numeric("setanta"))

    def test_operator_synonyms_and_simple_op(self):
        self.assertEqual(cu.math_op("x"), "×")
        self.assertEqual(cu.math_op("/"), ":")
        self.assertIsNone(cu.math_op("%"))
        self.assertEqual(cu.math_simple_op("23 × 4"), (23, "×", 4))
        self.assertIsNone(cu.math_simple_op("Quants són dos?"))


class MathGate(unittest.TestCase):
    """A math level has no level file: no Flash requirement (flash_progress is met)."""

    def test_no_level_file_means_met(self):
        cur = cu.parse_curriculum("---\n---\n")
        cur["meta"]["stem"] = "math-m5"
        with tempfile.TemporaryDirectory() as data:
            fp = cu.flash_progress(REPO_ROOT, cur, data, "math-m5")
        self.assertEqual(fp["total"], 9)
        self.assertEqual(fp["share"], 0)
        self.assertTrue(fp["met"])


if __name__ == "__main__":
    unittest.main()
