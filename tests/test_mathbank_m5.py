#!/usr/bin/env python3
"""E2 (docs/ENCARREC-M5-E2-BANC.md §5) — the m5 Go bank.

Pinned here:
  * the 14 compute families and the 2 steps families (partial_products_3,
    long_division_2): determinism, validation of every draw, self-grading, and the
    value of each expression;
  * units: a unit lives in the answer ("3500 m", "40 cm²", "95 min"); a bare number
    is value-correct but "near" (7), never a full mark;
  * word_problems_multistep choose items: the answer is one of the options and every
    other option is wrong by value;
  * steps traces grade through hooks/bank.py, and a wrong trace does not;
  * the generated bank on disk: validates, ids sequential, no problem repeated within
    a competence (compute and steps files together);
  * curriculum/math-m5.md: parses, validates, every `Bank:` family exists, every
    `Check:` answer passes its own grader.
"""
import contextlib
import importlib.util
import io
import json
import random
import re
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))

import bank as bankmod    # noqa: E402
import curriculum as cu   # noqa: E402
import db_schema          # noqa: E402
import mathgrade          # noqa: E402


def _load_mathbank():
    spec = importlib.util.spec_from_file_location("mathbank", REPO / "scripts" / "mathbank.py")
    mb = importlib.util.module_from_spec(spec)
    sys.modules["mathbank"] = mb
    spec.loader.exec_module(mb)
    return mb


mb = _load_mathbank()

CUR = REPO / "curriculum" / "math-m5.md"
BANK = REPO / "curriculum" / "bank" / "math-m5"
FIXED_DATE = "2026-10-16"

NEW_COMPUTE = ["mult_3digit", "div_2digit", "combined_ops", "frac_same_den", "frac_of_quantity",
               "dec_ops", "percent_basic", "smd_convert", "time_intervals", "area_perimeter",
               "mean_mode_range", "probability_simple", "equations_simple", "word_problems_multistep"]
NEW_STEPS = ["partial_products_3", "long_division_2"]
COMPETENCES = ["m5.mult_3digit", "m5.div_2digit", "m5.combined_ops", "m5.distributive",
               "m5.frac_same_den", "m5.frac_of_quantity", "m5.dec_ops", "m5.percent_basic",
               "m5.smd_convert", "m5.time_intervals", "m5.area_perimeter", "m5.mean_mode_range",
               "m5.probability", "m5.equations_simple", "m5.word_problems"]


def _read(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def _gen(tmp: Path, competence: str, n: int, seed: int, family=None, steps=False) -> Path:
    argv = ["gen", "--curriculum", str(CUR), "--competence", competence, "--n", str(n),
            "--seed", str(seed), "--out", str(tmp), "--date", FIXED_DATE]
    if family:
        argv += ["--family", family]
    if steps:
        argv += ["--type", "steps"]
    with contextlib.redirect_stdout(io.StringIO()):
        rc = mb.main(argv)
    assert rc == 0, f"gen failed for {competence} {family}"
    return tmp / (f"{competence}__steps.json" if steps else f"{competence}.json")


class NewFamiliesTest(unittest.TestCase):
    def test_all_new_families_registered(self):
        for fam in NEW_COMPUTE:
            self.assertIn(fam, mb.FAMILIES)
        for fam in NEW_STEPS:
            self.assertIn(fam, mb.STEPS_FAMILIES)

    def test_each_family_is_deterministic(self):
        for fam in NEW_COMPUTE + NEW_STEPS:
            a = mb.build_item(fam, random.Random(7), "m5.x", 1, "t")
            b = mb.build_item(fam, random.Random(7), "m5.x", 1, "t")
            self.assertEqual(a, b, fam)

    def test_every_draw_passes_validation(self):
        # build_item refuses (GenError) any draw that fails validate_item, so 60 draws
        # per family with no error is the check; then validate again to be explicit.
        for fam in NEW_COMPUTE + NEW_STEPS:
            for seed in range(60):
                item = mb.build_item(fam, random.Random(seed), "m5.x", seed + 1, "t")
                self.assertEqual(mb.validate_item(item), [], f"{fam} seed {seed}")

    def test_compute_answers_grade_10_against_themselves(self):
        for fam in NEW_COMPUTE:
            for seed in range(40):
                it = mb.build_item(fam, random.Random(seed), "m5.x", 1, "t")
                if it["type"] == "steps":
                    continue
                self.assertEqual(bankmod.grade(it, it["answer"])["score"], 10, f"{fam} {it['problem']}")
                for alt in it["also_accept"]:
                    self.assertEqual(bankmod.grade(it, alt)["score"], 10, f"{fam} alt {alt}")

    def test_expression_or_problem_equals_the_answer(self):
        for fam in NEW_COMPUTE:
            for seed in range(40):
                it = mb.build_item(fam, random.Random(seed), "m5.x", 1, "t")
                src = it.get("expression") or it["problem"]
                self.assertEqual(mathgrade.parse_expr(src).value,
                                 mb._answer_value(it["answer"]), f"{fam}: {src} vs {it['answer']}")


class UnitsTest(unittest.TestCase):
    def test_unit_answers_are_values_not_algebra(self):
        self.assertTrue(mb._is_unit_answer("40 cm²"))
        self.assertTrue(mb._is_unit_answer("95 min"))
        self.assertTrue(mb._is_unit_answer("2,45 m"))
        self.assertFalse(mb._is_unit_answer("5x + 5"))
        self.assertFalse(mb._is_unit_answer("3x"))  # a variable is not a unit
        self.assertFalse(mb._is_unit_answer("56"))

    def test_bare_number_is_near_not_correct_when_a_unit_is_expected(self):
        it = mb.build_item("smd_convert", random.Random(3), "m5.smd_convert", 1, "t")
        value_only = str(mb._answer_value(it["answer"]))
        verdict = mathgrade.grade_single(it["answer"], value_only)
        self.assertEqual(verdict["verdict"], "near")
        self.assertEqual(verdict["score"], 7)
        self.assertEqual(bankmod.grade(it, value_only)["score"], 7)

    def test_unit_answers_carry_their_unit(self):
        for fam in ("smd_convert", "area_perimeter", "time_intervals"):
            for seed in range(40):
                it = mb.build_item(fam, random.Random(seed), "m5.x", 1, "t")
                self.assertTrue(mb._is_unit_answer(it["answer"]), f"{fam}: {it['answer']}")

    def test_validation_refuses_a_unit_answer_with_the_wrong_value(self):
        item = {"id": "m5.smd_convert.001", "competence": "m5.smd_convert", "type": "compute",
                "instruction": "Converteix.", "problem": "Quants metres són 3,5 km?",
                "expression": "3,5 × 1000", "answer": "3400 m", "also_accept": [], "options": [],
                "why": "1 km = 1000 m.", "status": "validated", "source": "test"}
        self.assertTrue(mb.validate_item(item))
        item["answer"] = "3500 m"
        self.assertEqual(mb.validate_item(item), [])


class ChooseTest(unittest.TestCase):
    def test_choose_options_are_wrong_by_value_except_the_answer(self):
        seen_choose = 0
        for seed in range(200):
            it = mb.build_item("word_problems_multistep", random.Random(seed), "m5.word_problems", 1, "t")
            if it["type"] != "choose":
                continue
            seen_choose += 1
            self.assertIn(it["answer"], it["options"])
            self.assertEqual(len(it["options"]), 4)
            for opt in it["options"]:
                if opt == it["answer"]:
                    self.assertEqual(bankmod.grade(it, opt)["score"], 10)
                else:
                    self.assertNotEqual(mathgrade.parse_expr(opt).value, mb._answer_value(it["answer"]), opt)
                    self.assertEqual(bankmod.grade(it, opt)["score"], 3, opt)
        self.assertGreater(seen_choose, 10)

    def test_word_problem_numbers_are_in_the_story(self):
        for seed in range(80):
            it = mb.build_item("word_problems_multistep", random.Random(seed), "m5.word_problems", 1, "t")
            text = f"{it['problem']} {it['why']}"
            for num in re.findall(r"\d+", it["expression"]):
                if int(num) >= 2:
                    self.assertRegex(text, rf"(?<!\d){num}(?!\d)", it["expression"])


class StepsFamiliesTest(unittest.TestCase):
    def test_traces_are_consistent_and_grade_10(self):
        for fam in NEW_STEPS:
            for seed in range(40):
                it = mb.build_item(fam, random.Random(seed), "m5.x", 1, "t")
                self.assertEqual(it["type"], "steps")
                self.assertEqual(Fraction(mathgrade.parse_expr(it["steps"][-1]["value"]).value),
                                 mb._answer_value(it["answer"]), f"{fam} {it['problem']}")
                for st in it["steps"]:
                    self.assertIn(st["error_class"], db_schema.ERROR_CATEGORIES)
                    self.assertTrue(st["goal"].strip())
                trace = "\n".join(st["expect"] for st in it["steps"])
                self.assertEqual(bankmod.grade(it, trace)["score"], 10, f"{fam}: {trace}")

    def test_a_wrong_trace_does_not_grade_10(self):
        it = mb.build_item("long_division_2", random.Random(5), "m5.div_2digit", 1, "t")
        lines = [st["expect"] for st in it["steps"]]
        lines[-1] = lines[-1].split(" + ")[0] + " + 1"  # the last sum is one off
        self.assertNotEqual(bankmod.grade(it, "\n".join(lines))["score"], 10)

    def test_long_division_2_divides_exactly(self):
        for seed in range(40):
            it = mb.build_item("long_division_2", random.Random(seed), "m5.div_2digit", 1, "t")
            a, d = (int(x) for x in re.findall(r"\d+", it["problem"]))
            self.assertEqual(a, d * int(it["answer"]))


class DiskBankTest(unittest.TestCase):
    def test_every_competence_has_items(self):
        for cid in COMPETENCES:
            self.assertTrue(bankmod.has_bank(REPO, "math-m5", cid, None), cid)

    def test_every_file_validates(self):
        files = sorted(BANK.glob("*.json")) + sorted((BANK / "steps").glob("*.json"))
        self.assertEqual(len(files), 17)
        for f in files:
            self.assertEqual(mb.validate_file(f), [], f.name)

    def test_ids_sequential_and_no_problem_repeated_per_competence(self):
        for cid in COMPETENCES:
            items = []
            for f in (BANK / f"{cid}.json", BANK / "steps" / f"{cid}__steps.json"):
                if f.exists():
                    items += _read(f)
            nums = sorted(int(it["id"].rsplit(".", 1)[1]) for it in items)
            self.assertEqual(nums, list(range(1, len(items) + 1)), cid)
            keys = [mb.norm_problem(it["problem"]) for it in items]
            self.assertEqual(len(keys), len(set(keys)), f"{cid}: a problem repeats across its files")

    def test_disk_items_grade_10_through_the_bank(self):
        for cid in COMPETENCES:
            for it in bankmod.load_bank(REPO, "math-m5", cid, None):
                if it["type"] == "steps":
                    trace = "\n".join(st["expect"] for st in it["steps"])
                    self.assertEqual(bankmod.grade(it, trace)["score"], 10, it["id"])
                else:
                    self.assertEqual(bankmod.grade(it, it["answer"])["score"], 10, it["id"])


class RuleAcrossFilesTest(unittest.TestCase):
    """generate() never repeats a problem of its competence, whichever file is written
    first: a steps item cannot repeat a compute item, and the other way round."""

    def test_steps_after_compute_avoids_compute_problems(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _gen(tmp, "m5.div_2digit", 12, 42, family="div_2digit")
            steps = _read(_gen(tmp, "m5.div_2digit", 12, 42, family="long_division_2", steps=True))
            compute = {mb.norm_problem(it["problem"]) for it in _read(tmp / "m5.div_2digit.json")}
            self.assertFalse([it["id"] for it in steps if mb.norm_problem(it["problem"]) in compute])

    def test_compute_after_steps_avoids_steps_problems(self):
        # the steps file lives in the steps/ subdirectory, as in the real bank
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "steps").mkdir()
            _gen(tmp / "steps", "m5.div_2digit", 12, 42, family="long_division_2", steps=True)
            compute = _read(_gen(tmp, "m5.div_2digit", 12, 42, family="div_2digit"))
            steps = {mb.norm_problem(it["problem"])
                     for it in _read(tmp / "steps" / "m5.div_2digit__steps.json")}
            self.assertFalse([it["id"] for it in compute if mb.norm_problem(it["problem"]) in steps])
            self.assertEqual(compute[0]["id"], "m5.div_2digit.013")  # numbering continues past the steps


class M5CurriculumTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cur = cu.load_curriculum(CUR)

    def test_parses_and_validates(self):
        self.assertEqual(cu.validate_curriculum(self.cur), [])
        m = self.cur["meta"]
        self.assertEqual(m["language"], "math")
        self.assertEqual(m["level"], "m5")
        self.assertEqual(m["status"], "esborrany")
        self.assertNotIn("flash_share", m)

    def test_the_design_competences_are_all_there(self):
        ids = [c["id"] for c in self.cur["competencies"]]
        self.assertEqual(sorted(ids), sorted(COMPETENCES))

    def test_core_fits_the_checkpoint(self):
        core = [c["id"] for c in self.cur["competencies"] if c["core"]]
        self.assertEqual(len(core), 9)
        self.assertLessEqual(len(core), self.cur["meta"]["checkpoint_items"])

    def test_every_bank_family_exists(self):
        for c in self.cur["competencies"]:
            fam = mb.bank_family_for(CUR, c["id"])
            self.assertIn(fam, set(mb.FAMILIES) | set(mb.STEPS_FAMILIES), c["id"])

    def test_every_check_passes_its_own_grader(self):
        for c in self.cur["competencies"]:
            self.assertEqual(len(c["checks"]), 3, c["id"])
            for ch in c["checks"]:
                text = ("\n".join(s.strip() for s in ch["answer"].split(" ; "))
                        if ch["type"] == "Steps" else ch["answer"])
                self.assertTrue(cu.grade_check(ch, text), f"{c['id']}: {ch['prompt']}")


if __name__ == "__main__":
    unittest.main()
