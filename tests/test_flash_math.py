#!/usr/bin/env python3
"""Flash for math (docs/ENCARREC-FLASH-MATH.md §2, §5; docs/ENCARREC-M5-E1-FLASH.md §3–§4): the
Python side counts the same words as the server (server/src/flash.ts), and a math level with no
level file has no Flash requirement."""
import json
import math
import re
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
                if kind == "mult":
                    gen["params"] = {"digits": [2, 1]}  # at [1,1] there are only 36 products: the server gives fewer than 50
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
                # m7 (docs/ENCARREC-M7-E5-FLASH.md §2, §3): factorization, algebraic, sexagesimal, the new figures
                {"id": "e5-fz1", "prompt": "Descompon 12", "answer": ["2^2·3"], "answer_kind": "factorization"},
                {"id": "e5-fz2", "prompt": "Descompon 12", "answer": ["2^2·4"], "answer_kind": "factorization"},
                {"id": "e5-al1", "prompt": "x", "answer": ["3x²"], "answer_kind": "algebraic"},
                {"id": "e5-al2", "prompt": "x", "answer": ["3x^7"], "answer_kind": "algebraic"},
                {"id": "e5-sx1", "prompt": "x", "answer": ["7 h 45 min"], "answer_kind": "sexagesimal"},
                {"id": "e5-sx2", "prompt": "x", "answer": ["7 h 75 min"], "answer_kind": "sexagesimal"},
                {"id": "e5-sx3", "prompt": "x", "answer": ["18° 55'"], "answer_kind": "sexagesimal", "mode": "angle"},
                {"id": "e5-sx4", "prompt": "x", "answer": ["18° 55'"], "answer_kind": "sexagesimal", "mode": "time"},
                {"id": "e5-pa1", "prompt": "Quant mesura l'angle marcat amb «?»", "answer": ["70"], "figure": {"type": "parallels", "angle": 70, "known": 1, "ask": 4}},
                {"id": "e5-pa2", "prompt": "Quant mesura l'angle marcat amb «?»", "answer": ["110"], "figure": {"type": "parallels", "angle": 70, "known": 1, "ask": 4}},
                {"id": "e5-pa3", "prompt": "Quant mesura l'angle marcat amb «?»", "answer": ["70"], "figure": {"type": "parallels", "angle": 70, "known": 1, "ask": 4}, "answer_kind": "number"},
                {"id": "e5-rt1", "prompt": "Calcula el costat que falta (?)", "answer": ["5"], "answer_kind": "unit", "unit": "cm", "figure": {"type": "right_triangle", "a": 3, "b": 4, "c": 5, "ask": "c", "unit": "cm"}},
                {"id": "e5-rt2", "prompt": "x", "answer": ["6"], "figure": {"type": "right_triangle", "a": 3, "b": 4, "c": 6, "ask": "c"}},
                {"id": "e5-nl1", "prompt": "Quin nombre és?", "answer": ["−3"], "figure": {"type": "number_line", "min": -5, "max": 5, "point": -3}},
                {"id": "e5-nl2", "prompt": "Quin nombre és?", "answer": ["3"], "figure": {"type": "number_line", "min": -5, "max": 5, "point": -3}},
                {"id": "e5-gr1", "prompt": "Quin és el pendent de la recta?", "answer": ["2"], "figure": {"type": "grid", "points": [], "min": -6, "max": 6, "line": {"m": 2, "n": -3}}},
                {"id": "e5-gr2", "prompt": "Quin és el pendent de la recta?", "answer": ["3"], "figure": {"type": "grid", "points": [], "min": -6, "max": 6, "line": {"m": 2, "n": -3}}},
                {"id": "e5-gr3", "prompt": "x", "answer": ["(−3, 4)"], "answer_kind": "pair", "figure": {"type": "grid", "points": [[-3, 4]], "min": -6, "max": 6}},
                {"id": "e5-gr4", "prompt": "x", "answer": ["(−3, 4)"], "answer_kind": "pair", "figure": {"type": "grid", "points": [[-3, 8]], "min": -6, "max": 6}},
            ]}
            files["92-nope.json"] = {"id": "math-t9.flash.nope", "level": "t9", "title": {"en": "nope"}, "generate": {"kind": "nope", "count": 4}}
            write_math(tmp, "math-t9", files)
            self.assertEqual(python_math_lists(tmp), server_math_lists(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_m5_has_the_tables_the_explicit_list_and_the_generated_ones(self):
        lists = {l["id"]: l["words"] for l in cu.flash_lists(REPO_ROOT, "math-m5")}
        self.assertEqual(len(lists), 29)  # §6: 3 multiplication lists (01..03, kind mult) + 26 generated (10..35, E4)
        self.assertEqual(len(lists["math-m5.flash.arrodonir"]), 12)
        self.assertEqual(lists["math-m5.flash.taules-repas"], [f"g{i}" for i in range(1, 25)])
        self.assertEqual(len(lists["math-m5.flash.mult-2x1"]), 12)
        self.assertEqual(len(lists["math-m5.flash.mult-3x1"]), 12)


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
        self.assertEqual(fp["total"], 29)
        self.assertEqual(fp["share"], 0)
        self.assertTrue(fp["met"])


class M5FlashGate(unittest.TestCase):
    """E4 §2: math-m5.md asks for flash_share 60; the level needs ceil(total × 0,6) closed lists."""

    @classmethod
    def setUpClass(cls):
        cls.cur = cu.load_curriculum(REPO_ROOT / "curriculum" / "math-m5.md")
        cls.lists = cu.flash_lists(REPO_ROOT, "math-m5")

    def close(self, n):
        """A data dir where the first n lists are closed (every word in box 2) and the rest are untouched."""
        d = Path(tempfile.mkdtemp(prefix="flash-gate-"))
        lists = {
            l["id"]: {"words": {w: {"box": cu.FLASH_KNOWN_BOX, "seen": 2, "first_try": 2, "misses": 0, "last": "2026-10-16"} for w in l["words"]}, "closed_at": None}
            for l in self.lists[:n]
        }
        (d / cu.FLASH_DB).write_text(json.dumps({"version": 1, "lists": lists}), encoding="utf-8")
        return d

    def test_the_level_asks_for_sixty_percent_of_the_valid_lists(self):
        self.assertEqual(self.cur["meta"]["flash_share"], 60)
        with tempfile.TemporaryDirectory() as data:
            fp = cu.flash_progress(REPO_ROOT, self.cur, data, "math-m5")
        self.assertEqual(fp["share"], 60)
        self.assertEqual(fp["total"], len(self.lists))
        self.assertEqual(fp["total"], 29)
        self.assertEqual(fp["needed"], math.ceil(29 * 0.6))  # 18
        self.assertEqual(fp["closed"], 0)
        self.assertFalse(fp["met"])

    def test_met_exactly_at_the_needed_count(self):
        for n, met in ((17, False), (18, True)):
            d = self.close(n)
            try:
                fp = cu.flash_progress(REPO_ROOT, self.cur, d, "math-m5")
            finally:
                shutil.rmtree(d, ignore_errors=True)
            self.assertEqual(fp["closed"], n)
            self.assertEqual(fp["met"], met, n)


class M7FlashLists(unittest.TestCase):
    """E7 §1–§3: one list per m7 generator (docs/ENCARREC-M7-E5-FLASH.md §4), the repàs first, and flash_share 60."""

    @classmethod
    def setUpClass(cls):
        cls.cur = cu.load_curriculum(REPO_ROOT / "curriculum" / "math-m7.md")
        cls.lists = cu.flash_lists(REPO_ROOT, "math-m7")
        cls.files = sorted((REPO_ROOT / "curriculum" / "flash" / "math-m7").glob("*.json"))
        cls.md = (REPO_ROOT / "curriculum" / "math-m7.md").read_text(encoding="utf-8")

    def test_one_valid_list_per_file_and_the_ids_are_unique(self):
        self.assertEqual(len(self.files), 36)
        self.assertEqual(len(self.lists), 36)
        ids = [l["id"] for l in self.lists]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(ids[0], "math-m7.flash.taules-repas")
        self.assertEqual(len(self.lists[0]["words"]), 24)
        # 12 cards each, except the four kinds whose vocabulary is finite (GEN_ROOM in server/src/flash.ts)
        room = {"math-m7.flash.proporcionalitat-directa-o-inversa": 8, "math-m7.flash.punts-notables-del-triangle": 8,
                "math-m7.flash.tipus-de-variable": 10, "math-m7.flash.probabilitat-de-laplace": 9}
        for l in self.lists[1:]:
            self.assertEqual(len(l["words"]), room.get(l["id"], 12), l["id"])

    def test_every_competence_exists_in_math_m7_and_the_repas_has_none(self):
        competences = set(re.findall(r"^### (m7\.[a-z_]+)", self.md, flags=re.M))
        for f in self.files:
            raw = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(raw["level"], "m7", f.name)
            self.assertEqual(set(raw["title"]), {"ca", "es", "en"}, f.name)
            if f.name.startswith("00-"):
                self.assertNotIn("competence", raw)
                continue
            self.assertIn(raw["competence"], competences, f.name)

    def test_the_level_asks_for_sixty_percent_and_the_gate_counts_36(self):
        self.assertEqual(self.cur["meta"]["flash_share"], 60)
        with tempfile.TemporaryDirectory() as data:
            fp = cu.flash_progress(REPO_ROOT, self.cur, data, "math-m7")
        self.assertEqual((fp["share"], fp["total"], fp["needed"]), (60, 36, math.ceil(36 * 0.6)))
        self.assertEqual(fp["needed"], 22)
        self.assertFalse(fp["met"])



class M6FlashLists(unittest.TestCase):
    """E9 §2–§3: the m6 lists (docs/ENCARREC-M6-E9-FLASH.md §2): the repàs first, one list per generator, flash_share 60."""

    @classmethod
    def setUpClass(cls):
        cls.cur = cu.load_curriculum(REPO_ROOT / "curriculum" / "math-m6.md")
        cls.lists = cu.flash_lists(REPO_ROOT, "math-m6")
        cls.files = sorted((REPO_ROOT / "curriculum" / "flash" / "math-m6").glob("*.json"))
        cls.md = (REPO_ROOT / "curriculum" / "math-m6.md").read_text(encoding="utf-8")

    def test_one_valid_list_per_file_and_the_ids_are_unique(self):
        self.assertEqual(len(self.files), 22)
        self.assertEqual(len(self.lists), 22)
        ids = [l["id"] for l in self.lists]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(ids[0], "math-m6.flash.taules-repas")
        self.assertEqual(len(self.lists[0]["words"]), 24)
        for l in self.lists[1:]:
            self.assertEqual(len(l["words"]), 12, l["id"])

    def test_every_competence_exists_in_math_m6_and_the_repas_has_none(self):
        competences = set(re.findall(r"^### (m6\.[a-z_]+)", self.md, flags=re.M))
        for f in self.files:
            raw = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(raw["level"], "m6", f.name)
            self.assertEqual(set(raw["title"]), {"ca", "es", "en"}, f.name)
            if f.name.startswith("00-"):
                self.assertNotIn("competence", raw)
                continue
            self.assertIn(raw["competence"], competences, f.name)

    def test_the_level_asks_for_sixty_percent_and_the_gate_counts_22(self):
        self.assertEqual(self.cur["meta"]["flash_share"], 60)
        with tempfile.TemporaryDirectory() as data:
            fp = cu.flash_progress(REPO_ROOT, self.cur, data, "math-m6")
        self.assertEqual((fp["share"], fp["total"], fp["needed"]), (60, 22, math.ceil(22 * 0.6)))
        self.assertEqual(fp["needed"], 14)
        self.assertFalse(fp["met"])


if __name__ == "__main__":
    unittest.main()
