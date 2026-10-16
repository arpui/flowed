#!/usr/bin/env python3
"""E8 (docs/ENCARREC-M6-E8-BANC.md §4) — the m6 Go bank.

Pinned here:
  * the 12 new families (11 from the design + the easy sexagesimal sibling):
    registered, deterministic, every draw passes validation, every answer grades 10
    against itself (and its also_accept);
  * the two rules the families rely on: an exact root is a product of prime powers
    that evaluates to the root; a division of fractions is grouped, so the grader
    reads it as the learner does (a/b ÷ (c/d));
  * units: the m6 units (mm², ha) are answers that carry their unit, and the area `a`
    is never an answer unit (a letter-unit would read as algebra);
  * the generated bank on disk: one file per competence with a `Bank:` line, validates,
    ids sequential, no problem repeated; every item grades 10 through the bank;
  * curriculum/math-m6.md: parses, validates, 17 competences, the design's core marks,
    checkpoint_items >= core, every `Bank:` family exists, every `Check:` passes its own
    grader; m6.coordinates has no bank (Flash only, as the design says).
"""
import contextlib
import importlib.util
import io
import json
import random
import sys
import tempfile
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

CUR = REPO / "curriculum" / "math-m6.md"
BANK = REPO / "curriculum" / "bank" / "math-m6"
FIXED_DATE = "2026-10-16"

NEW_FAMILIES = ["powers_value", "integers_context", "frac_ops4", "dec_division", "percent_change",
                "scales", "area_units", "volume_units", "areas_polygons", "circle_measures",
                "volumes_solids", "sexagesimal_ops_easy"]
# competence -> family, for the 16 with a Bank line (m6.coordinates has none)
COMPETENCE_FAMILY = {
    "m6.powers_roots": "powers_value", "m6.integers": "integers_context",
    "m6.gcd_lcm": "gcd_lcm_problems", "m6.fraction_ops": "frac_ops4",
    "m6.decimal_division": "dec_division", "m6.percent_change": "percent_change",
    "m6.scales": "scales", "m6.equations_intro": "equations_simple",
    "m6.area_units": "area_units", "m6.volume_capacity": "volume_units",
    "m6.angles_sexagesimal": "sexagesimal_ops_easy", "m6.areas_polygons": "areas_polygons",
    "m6.circle": "circle_measures", "m6.volumes": "volumes_solids",
    "m6.statistics": "stats_tables", "m6.probability": "probability_simple",
}
# the design's [core] marks (DISSENY-M7-M6 §2)
CORE = {"m6.powers_roots", "m6.integers", "m6.gcd_lcm", "m6.fraction_ops",
        "m6.decimal_division", "m6.percent_change", "m6.areas_polygons", "m6.circle"}
ALL_COMPETENCES = list(COMPETENCE_FAMILY) + ["m6.coordinates"]


def _read(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


class NewFamiliesTest(unittest.TestCase):
    def test_all_new_families_registered(self):
        for fam in NEW_FAMILIES:
            self.assertIn(fam, mb.FAMILIES)
            self.assertIn(fam, mb.M6_FAMILIES)

    def test_each_family_is_deterministic(self):
        for fam in NEW_FAMILIES:
            a = mb.build_item(fam, random.Random(7), "m6.x", 1, "t")
            b = mb.build_item(fam, random.Random(7), "m6.x", 1, "t")
            self.assertEqual(a, b, fam)

    def test_every_draw_passes_validation(self):
        # build_item refuses (GenError) any draw that fails validate_item: 300 draws per
        # family with no error is the check; then validate again to be explicit.
        for fam in NEW_FAMILIES:
            for seed in range(300):
                item = mb.build_item(fam, random.Random(seed), "m6.x", seed + 1, "t")
                self.assertEqual(item["type"], "compute", fam)
                self.assertEqual(mb.validate_item(item), [], f"{fam} seed {seed}")

    def test_answers_grade_10_against_themselves(self):
        for fam in NEW_FAMILIES:
            for seed in range(80):
                it = mb.build_item(fam, random.Random(seed), "m6.x", 1, "t")
                self.assertEqual(bankmod.grade(it, it["answer"])["score"], 10,
                                 f"{fam}: {it['problem']} -> {it['answer']}")
                for alt in it["also_accept"]:
                    self.assertEqual(bankmod.grade(it, alt)["score"], 10, f"{fam} alt {alt}")

    def test_expression_or_problem_equals_the_answer(self):
        for fam in NEW_FAMILIES:
            for seed in range(80):
                it = mb.build_item(fam, random.Random(seed), "m6.x", 1, "t")
                src = it.get("expression") or it["problem"]
                self.assertEqual(mathgrade.parse_expr(src).value,
                                 mb._answer_value(it["answer"]), f"{fam}: {src} vs {it['answer']}")


class RulesTest(unittest.TestCase):
    def test_exact_roots_have_a_power_or_a_plain_expression(self):
        # mathgrade reads no root sign: a root's expression is a prime power (2^3) or a prime
        seen = 0
        for seed in range(400):
            it = mb.build_item("powers_value", random.Random(seed), "m6.x", 1, "t")
            if "arrel" not in it["problem"]:
                continue
            seen += 1
            self.assertIn("expression", it)
            self.assertRegex(it["expression"], r"^\d+(\^\d+)?$")
            self.assertEqual(mathgrade.parse_expr(it["expression"]).value,
                             Fraction(it["answer"]), it["problem"])
        self.assertGreater(seen, 20)

    def test_division_of_fractions_is_grouped(self):
        seen = 0
        for seed in range(400):
            it = mb.build_item("frac_ops4", random.Random(seed), "m6.x", 1, "t")
            if "÷" not in it["problem"]:
                continue
            seen += 1
            left, right = it["problem"].split(" ÷ ")
            a, b = (int(x) for x in left.split("/"))
            c, d = (int(x) for x in right.strip("()").split("/"))
            self.assertEqual(mathgrade.parse_expr(it["problem"]).value, Fraction(a, b) / Fraction(c, d),
                             it["problem"])
        self.assertGreater(seen, 10)

    def test_units_mm2_and_ha_are_answers_with_a_unit(self):
        for ans in ("200 mm²", "2,5 ha", "20000 m²", "0,75 l", "3,5 m³"):
            self.assertTrue(mb._is_unit_answer(ans), ans)

    def test_the_letter_a_is_not_an_answer_unit(self):
        # "3a" is algebra (a letter), not a unit: the are is only ever given, never asked
        self.assertFalse(mb._is_unit_answer("3a"))
        self.assertFalse(mb._is_unit_answer("2 a"))

    def test_area_and_volume_families_never_answer_in_a(self):
        for fam in ("area_units",):
            for seed in range(200):
                it = mb.build_item(fam, random.Random(seed), "m6.x", 1, "t")
                self.assertNotRegex(it["answer"], r"\ba$", it["answer"])

    def test_exact_decimal_division_has_at_most_two_decimals(self):
        for seed in range(200):
            it = mb.build_item("dec_division", random.Random(seed), "m6.x", 1, "t")
            q = it["answer"]
            self.assertLessEqual(len(q.split(",")[1]) if "," in q else 0, 2, q)

    def test_scales_example(self):
        # 1 cm on a 1:500 plan is 500 cm, so 6 cm is 30 m
        it = {"problem": "En un plànol a escala 1:500, una paret mesura 6 cm. Quants metres mesura la paret de veritat?",
              "expression": "6 × 500 ÷ 100", "answer": "30 m", "also_accept": [], "options": [],
              "why": "1 m = 100 cm.", "value": None, "type": "compute", "instruction": "x",
              "status": "validated", "source": "t", "competence": "m6.x", "id": "m6.x.001"}
        self.assertEqual(mb.validate_item(it), [])
        self.assertEqual(bankmod.grade(it, "30 m")["score"], 10)


class DiskBankTest(unittest.TestCase):
    def test_one_file_per_competence_with_a_bank(self):
        for cid in COMPETENCE_FAMILY:
            self.assertTrue((BANK / f"{cid}.json").is_file(), cid)
        self.assertFalse((BANK / "m6.coordinates.json").exists())

    def test_every_file_validates(self):
        for cid in COMPETENCE_FAMILY:
            self.assertEqual(mb.validate_file(BANK / f"{cid}.json"), [], cid)

    def test_ids_sequential_and_no_problem_repeated(self):
        for cid in COMPETENCE_FAMILY:
            items = _read(BANK / f"{cid}.json")
            self.assertEqual(len(items), 12, cid)
            nums = [int(it["id"].rsplit(".", 1)[1]) for it in items]
            self.assertEqual(nums, list(range(1, 13)), cid)
            keys = [mb.norm_problem(it["problem"]) for it in items]
            self.assertEqual(len(keys), len(set(keys)), f"{cid}: a problem repeats")

    def test_disk_items_grade_10_through_the_bank(self):
        for cid in COMPETENCE_FAMILY:
            for it in bankmod.load_bank(REPO, "math-m6", cid, None):
                self.assertEqual(bankmod.grade(it, it["answer"])["score"], 10, it["id"])

    def test_generation_is_reproducible(self):
        with tempfile.TemporaryDirectory() as d:
            for cid in COMPETENCE_FAMILY:
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = mb.main(["gen", "--curriculum", str(CUR), "--competence", cid, "--n", "12",
                                  "--seed", "42", "--out", d, "--date", FIXED_DATE])
                self.assertEqual(rc, 0, cid)
                fresh = Path(d) / f"{cid}.json"
                self.assertEqual(fresh.read_text(encoding="utf-8"),
                                 (BANK / f"{cid}.json").read_text(encoding="utf-8"), cid)


class M6CurriculumTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cur = cu.load_curriculum(CUR)
        cls.comp = {c["id"]: c for c in cls.cur["competencies"]}

    def test_parses_and_validates(self):
        self.assertEqual(cu.validate_curriculum(self.cur), [])
        self.assertEqual(self.cur["meta"]["level"], "m6")
        self.assertEqual(self.cur["meta"]["language"], "math")
        self.assertEqual(self.cur["meta"]["checkpoint_items"], 12)
        self.assertEqual(self.cur["meta"]["flash_share"], 60)  # E9

    def test_the_seventeen_competences_are_there(self):
        self.assertEqual(len(self.cur["competencies"]), 17)
        for cid in ALL_COMPETENCES:
            self.assertIn(cid, self.comp, cid)

    def test_core_marks_and_checkpoint(self):
        for cid in ALL_COMPETENCES:
            self.assertEqual(self.comp[cid]["core"], cid in CORE, cid)
        core = sum(1 for c in self.cur["competencies"] if c["core"])
        self.assertEqual(core, len(CORE))
        self.assertLessEqual(core, self.cur["meta"]["checkpoint_items"])

    def test_every_bank_family_exists(self):
        for cid, fam in COMPETENCE_FAMILY.items():
            self.assertEqual(mb.bank_family_for(CUR, cid), fam, cid)
            self.assertIn(fam, mb.FAMILIES)

    def test_coordinates_has_no_bank(self):
        self.assertTrue(mb.competence_exists(CUR, "m6.coordinates"))
        with self.assertRaises(mb.GenError):
            mb.bank_family_for(CUR, "m6.coordinates")

    def test_every_check_passes_its_own_grader(self):
        for cid in ALL_COMPETENCES:
            checks = self.comp[cid]["checks"]
            self.assertEqual(len(checks), 3, cid)
            for ch in checks:
                self.assertTrue(cu.grade_check(ch, ch["answer"]), f"{cid}: {ch['prompt']}")


if __name__ == "__main__":
    unittest.main()
