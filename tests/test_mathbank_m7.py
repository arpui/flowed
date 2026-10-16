#!/usr/bin/env python3
"""E6 (docs/ENCARREC-M7-E6-BANC.md §4) — the m7 Go bank for the new competences.

Pinned here:
  * the 17 new compute families: registered, deterministic, every draw passes
    validation, every answer grades 10 against itself (and its also_accept);
  * the validator's two algebra/equation rules: an algebraic `expression` is a
    polynomial; a linear equation in one letter needs an answer that solves it;
  * units: cm², dm², cm³ are answers that carry their unit;
  * the generated bank on disk: one file per new competence, validates, ids
    sequential, no problem repeated; every item grades 10 through the bank;
  * curriculum/math-m7.md: parses, validates, 18 new competences with the design's
    core marks, every `Bank:` family exists, every `Check:` passes its own grader.
"""
import contextlib
import importlib.util
import io
import json
import random
import sys
import unittest
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))

import bank as bankmod    # noqa: E402
import curriculum as cu   # noqa: E402
import mathgrade          # noqa: E402


def _load_mathbank():
    spec = importlib.util.spec_from_file_location("mathbank", REPO / "scripts" / "mathbank.py")
    mb = importlib.util.module_from_spec(spec)
    sys.modules["mathbank"] = mb
    spec.loader.exec_module(mb)
    return mb


mb = _load_mathbank()

CUR = REPO / "curriculum" / "math-m7.md"
BANK = REPO / "curriculum" / "bank" / "math-m7"
FIXED_DATE = "2026-10-16"

NEW_FAMILIES = ["integers_combined", "gcd_lcm_problems", "frac_combined", "generatrix",
                "powers_props", "translate_expr", "monomials_ops", "linear_equations",
                "proportion_problems", "linear_function", "pythagoras", "polygon_angles",
                "composite_areas", "units_derived", "sexagesimal_ops", "stats_tables", "laplace"]
# competence -> family, for the 17 with a Bank line (triangle_points has none)
NEW_COMPETENCES = {
    "m7.integers": "integers_combined", "m7.factor_gcd_lcm": "gcd_lcm_problems",
    "m7.fractions": "frac_combined", "m7.decimals_generatrix": "generatrix",
    "m7.powers_roots": "powers_props", "m7.algebraic_language": "translate_expr",
    "m7.monomials": "monomials_ops", "m7.linear_equations": "linear_equations",
    "m7.proportionality": "proportion_problems", "m7.functions": "linear_function",
    "m7.pythagoras": "pythagoras", "m7.angles_lines": "polygon_angles",
    "m7.composite_areas": "composite_areas", "m7.units_derived": "units_derived",
    "m7.sexagesimal": "sexagesimal_ops", "m7.statistics": "stats_tables",
    "m7.probability": "laplace",
}
# the design's [core] marks for the new competences (DISSENY-M7-M6 §1.1)
NEW_CORE = {"m7.integers", "m7.factor_gcd_lcm", "m7.fractions", "m7.powers_roots",
            "m7.algebraic_language", "m7.monomials", "m7.linear_equations",
            "m7.proportionality", "m7.pythagoras"}
OLD_COMPETENCES = ["m7.props_grouping", "m7.props_distributive", "m7.props_factor",
                   "m7.syntax_letters", "m7.value_numeric", "m7.distributive_letters",
                   "m7.factor_letters", "m7.problems_generic"]


def _read(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def _gen(tmp: Path, competence: str, n: int, seed: int) -> Path:
    argv = ["gen", "--curriculum", str(CUR), "--competence", competence, "--n", str(n),
            "--seed", str(seed), "--out", str(tmp), "--date", FIXED_DATE]
    with contextlib.redirect_stdout(io.StringIO()):
        rc = mb.main(argv)
    assert rc == 0, f"gen failed for {competence}"
    return tmp / f"{competence}.json"


class NewFamiliesTest(unittest.TestCase):
    def test_all_new_families_registered(self):
        for fam in NEW_FAMILIES:
            self.assertIn(fam, mb.FAMILIES)
            self.assertIn(fam, mb.M7_FAMILIES)

    def test_each_family_is_deterministic(self):
        for fam in NEW_FAMILIES:
            a = mb.build_item(fam, random.Random(7), "m7.x", 1, "t")
            b = mb.build_item(fam, random.Random(7), "m7.x", 1, "t")
            self.assertEqual(a, b, fam)

    def test_every_draw_passes_validation(self):
        # build_item refuses (GenError) any draw that fails validate_item: 150 draws per
        # family with no error is the check; then validate again to be explicit.
        for fam in NEW_FAMILIES:
            for seed in range(150):
                item = mb.build_item(fam, random.Random(seed), "m7.x", seed + 1, "t")
                self.assertEqual(item["type"], "compute", fam)
                self.assertEqual(mb.validate_item(item), [], f"{fam} seed {seed}")

    def test_answers_grade_10_against_themselves(self):
        for fam in NEW_FAMILIES:
            for seed in range(60):
                it = mb.build_item(fam, random.Random(seed), "m7.x", 1, "t")
                self.assertEqual(bankmod.grade(it, it["answer"])["score"], 10,
                                 f"{fam}: {it['problem']} -> {it['answer']}")
                for alt in it["also_accept"]:
                    self.assertEqual(bankmod.grade(it, alt)["score"], 10, f"{fam} alt {alt}")

    def test_numeric_expression_or_problem_equals_the_answer(self):
        for fam in NEW_FAMILIES:
            for seed in range(60):
                it = mb.build_item(fam, random.Random(seed), "m7.x", 1, "t")
                if _is_algebra(it) or "=" in it["problem"]:  # equations: see the next test
                    continue
                src = it.get("expression") or it["problem"]
                self.assertEqual(mathgrade.parse_expr(src).value,
                                 mb._answer_value(it["answer"]), f"{fam}: {src} vs {it['answer']}")

    def test_algebra_expression_is_equivalent_to_the_answer(self):
        for fam in ("translate_expr", "monomials_ops"):
            for seed in range(60):
                it = mb.build_item(fam, random.Random(seed), "m7.x", 1, "t")
                self.assertTrue(_is_algebra(it), f"{fam}: {it['answer']}")
                src = it.get("expression") or it["problem"]
                self.assertEqual(mathgrade.parse_poly(src), mathgrade.parse_poly(it["answer"]),
                                 f"{fam}: {src} vs {it['answer']}")

    def test_equation_answers_solve_their_equation(self):
        for seed in range(80):
            it = mb.build_item("linear_equations", random.Random(seed), "m7.x", 1, "t")
            self.assertEqual(mb._solves_equation(it), [], it["problem"])
            x0 = int(it["answer"])
            wrong = dict(it, answer=str(x0 + 1))
            self.assertTrue(mb.validate_item(wrong), it["problem"])


def _is_algebra(item) -> bool:
    return bool(mb._ALG_LETTERS.search(str(item["answer"]))) and not mb._is_unit_answer(item["answer"])


class ValidatorRulesTest(unittest.TestCase):
    def _item(self, **kw):
        base = {"id": "m7.x.001", "competence": "m7.x", "type": "compute",
                "instruction": "Resol.", "problem": "3 · (x + 2) = 15", "answer": "3",
                "also_accept": [], "options": [], "why": "Treu el parèntesi.",
                "status": "validated", "source": "test"}
        base.update(kw)
        return base

    def test_equation_with_the_right_answer_is_valid(self):
        self.assertEqual(mb.validate_item(self._item()), [])

    def test_equation_with_a_wrong_answer_is_refused(self):
        errs = mb.validate_item(self._item(answer="4"))
        self.assertTrue(any("does not solve" in e for e in errs), errs)

    def test_a_story_with_a_formula_is_not_an_equation(self):
        # 'y = 2x + 3' in a story has an expression: the numeric two-path rule applies
        it = self._item(problem="La recta és y = 2x + 3. Quin valor té y quan x = 4?",
                        expression="2 × 4 + 3", answer="11", why="2 × 4 + 3 = 11.")
        self.assertEqual(mb.validate_item(it), [])

    def test_algebra_expression_must_match_the_answer(self):
        it = self._item(problem="el doble d'un nombre x, més 5", expression="2 · x + 5",
                        answer="2x + 5", also_accept=[], why="2 · x + 5.")
        self.assertEqual(mb.validate_item(it), [])
        self.assertTrue(mb.validate_item(dict(it, answer="2x + 4")))

    def test_units_cm3_dm2_are_answers_with_a_unit(self):
        for ans in ("200 cm³", "100 dm²", "3,5 m³"):
            self.assertTrue(mb._is_unit_answer(ans), ans)
        self.assertFalse(mb._is_unit_answer("2x³"))


class DiskBankTest(unittest.TestCase):
    def test_one_file_per_new_competence(self):
        for cid in NEW_COMPETENCES:
            self.assertTrue((BANK / f"{cid}.json").is_file(), cid)
        # the old m7 files are still there, untouched by E6 (their own tests pin the items)
        for cid in ["m7.syntax_letters", "m7.value_numeric", "m7.distributive_letters",
                    "m7.factor_letters"]:
            self.assertTrue((BANK / f"{cid}.json").is_file(), cid)

    def test_every_file_validates(self):
        for cid in NEW_COMPETENCES:
            self.assertEqual(mb.validate_file(BANK / f"{cid}.json"), [], cid)

    def test_ids_sequential_and_no_problem_repeated(self):
        for cid in NEW_COMPETENCES:
            items = _read(BANK / f"{cid}.json")
            self.assertEqual(len(items), 12, cid)
            nums = [int(it["id"].rsplit(".", 1)[1]) for it in items]
            self.assertEqual(nums, list(range(1, 13)), cid)
            keys = [mb.norm_problem(it["problem"]) for it in items]
            self.assertEqual(len(keys), len(set(keys)), f"{cid}: a problem repeats")

    def test_disk_items_grade_10_through_the_bank(self):
        for cid in NEW_COMPETENCES:
            for it in bankmod.load_bank(REPO, "math-m7", cid, None):
                self.assertEqual(bankmod.grade(it, it["answer"])["score"], 10, it["id"])

    def test_generation_is_reproducible(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            for cid in NEW_COMPETENCES:
                fresh = _gen(Path(d), cid, 12, 42)
                self.assertEqual(fresh.read_text(encoding="utf-8"),
                                 (BANK / f"{cid}.json").read_text(encoding="utf-8"), cid)


class M7CurriculumNewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cur = cu.load_curriculum(CUR)
        cls.comp = {c["id"]: c for c in cls.cur["competencies"]}

    def test_parses_and_validates(self):
        self.assertEqual(cu.validate_curriculum(self.cur), [])
        self.assertEqual(self.cur["meta"]["level"], "m7")
        self.assertEqual(self.cur["meta"]["language"], "math")

    def test_the_new_competences_are_there_and_the_old_ones_too(self):
        for cid in list(NEW_COMPETENCES) + ["m7.triangle_points"] + OLD_COMPETENCES:
            self.assertIn(cid, self.comp, cid)

    def test_core_marks_and_checkpoint(self):
        for cid in NEW_CORE:
            self.assertTrue(self.comp[cid]["core"], cid)
        for cid in set(NEW_COMPETENCES) - NEW_CORE:
            self.assertFalse(self.comp[cid]["core"], cid)
        core = sum(1 for c in self.cur["competencies"] if c["core"])
        self.assertLessEqual(core, self.cur["meta"]["checkpoint_items"])

    def test_every_bank_family_exists(self):
        for cid, fam in NEW_COMPETENCES.items():
            self.assertEqual(mb.bank_family_for(CUR, cid), fam, cid)
            self.assertIn(fam, mb.FAMILIES)

    def test_triangle_points_has_no_bank(self):
        self.assertTrue(mb.competence_exists(CUR, "m7.triangle_points"))
        with self.assertRaises(mb.GenError):
            mb.bank_family_for(CUR, "m7.triangle_points")

    def test_every_check_passes_its_own_grader(self):
        for cid in list(NEW_COMPETENCES) + ["m7.triangle_points"]:
            checks = self.comp[cid]["checks"]
            self.assertEqual(len(checks), 3, cid)
            for ch in checks:
                text = ("\n".join(s.strip() for s in ch["answer"].split(" ; "))
                        if ch["type"] == "Steps" else ch["answer"])
                self.assertTrue(cu.grade_check(ch, text), f"{cid}: {ch['prompt']}")

    def test_steps_check_rejects_a_slip(self):
        ch = self.comp["m7.integers"]["checks"][2]   # (-4)^2 - 3 · (-5) → 16 + 15 ; 31
        self.assertTrue(cu.grade_check(ch, "16 + 15\n31"))
        self.assertFalse(cu.grade_check(ch, "16 - 15\n31"))


if __name__ == "__main__":
    unittest.main()
