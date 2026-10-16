#!/usr/bin/env python3
"""Flash for math (docs/ENCARREC-FLASH-MATH.md §2, §5; docs/ENCARREC-M5-E1-FLASH.md §3–§4): the
Python side counts the same words as the server (server/src/flash.ts), and a math level with no
level file has no Flash requirement."""
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


def node_json(expr: str):
    """Evaluates `expr` (with `m` = server/src/flash.ts as a module) in node and returns its JSON."""
    script = (
        f"const m = await import({json.dumps(str(REPO_ROOT / 'server' / 'src' / 'flash.ts'))});"
        f"console.log(JSON.stringify({expr}));"
    )
    proc = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)


def server_math_lists(root: Path = REPO_ROOT) -> list[dict]:
    """The lists as server/src/flash.ts serves them (id and word ids), read by node."""
    return node_json(
        f"m.loadFlashLists({json.dumps(str(root))}, 'curriculum/flash/math-*', 'ca')"
        ".map((l) => ({ id: l.id, words: l.words.map((w) => w.id) }))"
    )


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

    @unittest.skipUnless(shutil.which("node"), "node is needed to read the server's lists")
    def test_python_ids_match_the_server_for_generated_and_typed_lists(self):
        """Every generator kind (count default, 1, 50 and an out-of-range count), an op list, and explicit
        items of each answer kind, with the drops, in a throwaway curriculum."""
        tmp = Path(tempfile.mkdtemp(prefix="flash-e1-"))
        try:
            kinds = node_json("m.GEN_KINDS")
            self.assertEqual(sorted(kinds), sorted(cu.MATH_GEN_KINDS))
            files = {}
            for i, kind in enumerate(kinds):
                gen = {"kind": kind}
                if i % 4 == 1:
                    gen["count"] = 1
                elif i % 4 == 2:
                    gen["count"] = 50
                elif i % 4 == 3:
                    gen["count"] = 99
                files[f"{i + 1:02d}-{kind}.json"] = {"id": f"math-t9.flash.{kind}", "level": "t9", "title": {"en": kind}, "generate": gen}
            files["90-op.json"] = {"id": "math-t9.flash.op", "level": "t9", "title": {"en": "op"}, "generate": {"op": "x", "a": [7], "b": {"from": 1, "to": 10}}}
            files["91-items.json"] = {"id": "math-t9.flash.items", "level": "t9", "title": {"en": "items"}, "items": [
                {"id": "c1", "prompt": "3 ? 5", "answer": ["<"], "answer_kind": "choice", "options": ["<", ">", "="]},
                {"id": "c2", "prompt": "3 ? 5", "answer": ["x"], "answer_kind": "choice", "options": ["<", ">"]},
                {"id": "f1", "prompt": "3/8 + 2/8", "answer": ["5/8"], "answer_kind": "fraction"},
                {"id": "f2", "prompt": "1/2", "answer": ["2/4"], "answer_kind": "fraction", "form": "simplest"},
                {"id": "f3", "prompt": "1/2", "answer": ["1 1/2"], "answer_kind": "fraction", "form": "simplest"},
                {"id": "u1", "prompt": "2 km = ? m", "answer": ["2000"], "answer_kind": "unit", "unit": "m"},
                {"id": "u2", "prompt": "2 km = ? m", "answer": ["2000"], "answer_kind": "unit"},
                {"id": "k1", "prompt": "x", "answer": ["1"], "answer_kind": "dibuix"},
                {"id": "s1", "prompt": "23 × 4", "answer": ["91"]},
                {"id": "s2", "prompt": "23 × 4", "answer": ["92"]},
                {"id": "n1", "prompt": "Quants?", "answer": ["3"], "answer_kind": None},
                # figures and pairs (docs/ENCARREC-M5-E3-FIGURES.md): kept, dropped by the figure, or by the answer
                {"id": "a1", "prompt": "Quin tipus d'angle és?", "answer": ["agut"], "answer_kind": "choice", "options": ["agut", "recte", "obtús", "pla"], "figure": {"type": "angle", "deg": 45}},
                {"id": "a2", "prompt": "Quin tipus d'angle és?", "answer": ["recte"], "answer_kind": "choice", "options": ["agut", "recte", "obtús", "pla"], "figure": {"type": "angle", "deg": 45}},
                {"id": "a3", "prompt": "Quin tipus d'angle és?", "answer": ["obtús"], "answer_kind": "choice", "options": ["agut", "obtús"], "figure": {"type": "angle", "deg": 200}},
                {"id": "p1", "prompt": "Quines coordenades té el punt?", "answer": ["(2, 3)"], "answer_kind": "pair", "figure": {"type": "grid", "points": [[2, 3]]}},
                {"id": "p2", "prompt": "Quines coordenades té el punt?", "answer": ["(3,2)"], "answer_kind": "pair", "figure": {"type": "grid", "points": [[2, 3]]}},
                {"id": "p3", "prompt": "Quines coordenades?", "answer": ["dos"], "answer_kind": "pair"},
                {"id": "p4", "prompt": "Quines coordenades?", "answer": ["(3 ; 4)"], "answer_kind": "pair"},
                {"id": "f1", "prompt": "Quant fa el perímetre?", "answer": ["10"], "answer_kind": "unit", "unit": "cm", "figure": {"type": "rect", "w": 4, "h": 2, "labels": True}},
                {"id": "f2", "prompt": "Quant fa el perímetre?", "answer": ["12"], "answer_kind": "unit", "unit": "cm", "figure": {"type": "rect", "w": 4, "h": 2, "labels": True}},
                {"id": "f3", "prompt": "Quina és l'àrea?", "answer": ["8"], "answer_kind": "unit", "unit": "cm²", "figure": {"type": "bars", "labels": ["a"], "values": [1]}},
                {"id": "f4", "prompt": "x", "answer": ["1"], "figure": {"type": "pie"}},
                {"id": "f5", "prompt": "x", "answer": ["1"], "figure": None},
                {"id": "f6", "prompt": "Quina és l'àrea?", "answer": ["6"], "answer_kind": "unit", "unit": "cm²", "figure": {"type": "triangle", "sides": [3, 4, 5], "labels": True}},
                {"id": "f7", "prompt": "x", "answer": ["1"], "figure": {"type": "triangle", "sides": [1, 2, 3]}},
                {"id": "f8", "prompt": "x", "answer": ["3"], "figure": {"type": "circle", "mark": "radius", "rot": 400}},
            ]}
            files["92-nope.json"] = {"id": "math-t9.flash.nope", "level": "t9", "title": {"en": "nope"}, "generate": {"kind": "nope", "count": 4}}
            write_math(tmp, "math-t9", files)
            self.assertEqual(python_math_lists(tmp), server_math_lists(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

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


class GeneratedLists(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="flash-gen-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_generated_list_counts_g1_to_gn(self):
        write_math(self.tmp, "math-x1", {
            "01-round.json": {"id": "r", "generate": {"kind": "round"}},
            "02-frac.json": {"id": "f", "generate": {"kind": "frac_of", "count": 7}},
            "03-big.json": {"id": "b", "generate": {"kind": "mean", "count": 500}},
        })
        lists = {l["id"]: l["words"] for l in cu.flash_lists(self.tmp, "math-x1")}
        self.assertEqual(lists["r"], [f"g{i}" for i in range(1, 13)])
        self.assertEqual(lists["f"], [f"g{i}" for i in range(1, 8)])
        self.assertEqual(lists["b"], [f"g{i}" for i in range(1, 51)])

    def test_an_unknown_kind_counts_nothing(self):
        write_math(self.tmp, "math-x1", {"01-nope.json": {"id": "n", "generate": {"kind": "nope", "count": 4}}})
        self.assertEqual(cu.flash_lists(self.tmp, "math-x1")[0]["words"], [])

    def test_typed_items_drop_what_the_server_drops(self):
        items = [
            {"id": "a", "prompt": "Quina?", "answer": ["b"], "answer_kind": "choice", "options": ["a", "b"]},
            {"id": "b", "prompt": "Quina?", "answer": ["z"], "answer_kind": "choice", "options": ["a", "b"]},
            {"id": "c", "prompt": "1/2", "answer": ["2/4"], "answer_kind": "fraction", "form": "simplest"},
            {"id": "d", "prompt": "1/2", "answer": ["2/4"], "answer_kind": "fraction"},
            {"id": "e", "prompt": "2 km = ? m", "answer": ["2000"], "answer_kind": "unit"},
            {"id": "f", "prompt": "2 km = ? m", "answer": ["2000"], "answer_kind": "unit", "unit": "m"},
            {"id": "g", "prompt": "Quants?", "answer": ["3"], "answer_kind": "dibuix"},
        ]
        write_math(self.tmp, "math-x1", {"01-items.json": {"id": "i", "items": items}})
        self.assertEqual(cu.flash_lists(self.tmp, "math-x1")[0]["words"], ["a", "d", "f"])

    def test_the_generated_count_is_clamped_and_defaults_to_twelve(self):
        self.assertEqual(cu._flash_count(None), 12)
        self.assertEqual(cu._flash_count(0), 1)
        self.assertEqual(cu._flash_count(51), 50)
        self.assertEqual(cu._flash_count(12.5), 12)
        self.assertEqual(cu._flash_count(True), 12)


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
