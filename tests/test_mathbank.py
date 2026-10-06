#!/usr/bin/env python3
"""WP1.5 — the parametric math bank generator (scripts/mathbank.py).

The whole point of the template approach (DISSENY-MATEMATIQUES D4) is that the
answer is computed by the same evaluator that will grade it, deterministically,
with no LLM in the loop. These tests pin exactly that:

  * determinism: same seed -> byte-identical JSON;
  * every generated answer grades 10 via mathgrade.grade_single against its own
    item, and the problem string evaluates to the answer's value;
  * no duplicate problems, schema fields present, ids sequential;
  * compare items: answer is one of the options and matches the true relation;
  * the `validate` subcommand passes on the committed pilot
    (curriculum/bank/math-m4/*.json, seed 42).

WP2.1 adds the `steps` families (§4.2, full expected traces). Pinned here:

  * determinism per family;
  * every step's expect/value parse via mathgrade and agree; every `accept`
    entry is an alternative line for the step's value;
  * the LAST step's value equals the answer, and the answer equals the
    problem's value;
  * error_class is one of the 12 canonical §4.4 classes (db_schema);
  * status == "validated" since WP2.3 (the per-line grader is wired) — and
    the proof that hooks/bank.py serves them from the steps/ subdir:
    load_bank/pick_item on a bank containing ONLY __steps files return the
    12 items, bank_left counts them under the real competence (no phantom
    "__steps" one), and demoting the status back to "generated" hides them
    again (the status filter is the single remaining guard);
  * the committed steps pilot (seed 42, 12 per family) validates on disk.
"""
import importlib.util
import io
import json
import contextlib
import shutil
import sys
import tempfile
import unittest
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

CUR = REPO / "curriculum" / "math-m4.md"
PILOT = REPO / "curriculum" / "bank" / "math-m4"
COMPETENCES = ["m4.mult_2digit", "m4.frac_add_unlike", "m4.dec_add", "m4.compare_fracs"]
FIXED_DATE = "2026-10-05"


def _gen(tmp: Path, competence: str, n: int, seed: int) -> Path:
    rc = mb.main(["gen", "--curriculum", str(CUR), "--competence", competence,
                  "--n", str(n), "--seed", str(seed), "--out", str(tmp),
                  "--date", FIXED_DATE])
    assert rc == 0, f"gen failed for {competence}"
    return tmp / f"{competence}.json"


def _read(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


class CurriculumTest(unittest.TestCase):
    def test_pilot_curriculum_parses_and_validates(self):
        cur = cu.load_curriculum(CUR)
        self.assertEqual(cu.validate_curriculum(cur), [])
        self.assertEqual(cur["meta"]["language"], "math")
        self.assertEqual(cur["meta"]["level"], "m4")
        self.assertEqual(cur["meta"]["status"], "esborrany-pilot")
        ids = [c["id"] for c in cur["competencies"]]
        for cid in COMPETENCES:
            self.assertIn(cid, ids)

    def test_every_competence_declares_a_bank_family(self):
        for cid in COMPETENCES:
            fam = mb.bank_family_for(CUR, cid)
            self.assertIn(fam, mb.FAMILIES)


class DeterminismTest(unittest.TestCase):
    def test_same_seed_identical_json(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            for cid in COMPETENCES:
                a = _gen(Path(d1), cid, 12, 42).read_text(encoding="utf-8")
                b = _gen(Path(d2), cid, 12, 42).read_text(encoding="utf-8")
                self.assertEqual(a, b, f"{cid}: same seed produced different JSON")

    def test_different_seed_different_items(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            for cid in COMPETENCES:
                a = {mb.norm_problem(i["problem"]) for i in _read(_gen(Path(d1), cid, 12, 1))}
                b = {mb.norm_problem(i["problem"]) for i in _read(_gen(Path(d2), cid, 12, 7))}
                self.assertLess(len(a & b), len(a), f"{cid}: seed did not change the draw")


class GeneratedItemsTest(unittest.TestCase):
    """Fresh generation (seed 42, 30 per competence) checked end to end."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.items = {}
        for cid in COMPETENCES:
            cls.items[cid] = _read(_gen(Path(cls.tmp.name), cid, 30, 42))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_schema_fields_present(self):
        for cid, items in self.items.items():
            self.assertEqual(len(items), 30, cid)
            for it in items:
                for f in mb.REQUIRED_FIELDS:
                    self.assertIn(f, it, f"{it.get('id')}: missing {f}")
                self.assertEqual(it["status"], "validated")
                self.assertEqual(it["competence"], cid)
                self.assertIn(it["type"], mb.ITEM_TYPES)
                self.assertTrue(it["why"].strip())
                self.assertTrue(it["instruction"].strip())

    def test_ids_sequential(self):
        for cid, items in self.items.items():
            nums = [int(it["id"].rsplit(".", 1)[1]) for it in items]
            self.assertEqual(nums, list(range(1, len(items) + 1)), cid)

    def test_answers_grade_10_against_their_own_item(self):
        for cid, items in self.items.items():
            for it in items:
                if it["type"] == "compare":
                    continue  # relations are graded literally by WP1.3, not parsed
                v = mathgrade.grade_single(it["answer"], it["answer"], it["also_accept"])
                self.assertEqual(v["score"], 10, f"{it['id']}: {v}")
                self.assertEqual(v["verdict"], "correct", it["id"])

    def test_problem_evaluates_to_the_answer(self):
        for cid, items in self.items.items():
            for it in items:
                if it["type"] == "compare":
                    continue
                p = mathgrade.parse_expr(it["problem"])
                a = mathgrade.parse_expr(it["answer"])
                self.assertEqual(p.value, a.value, f"{it['id']}: {it['problem']} != {it['answer']}")

    def test_no_duplicate_problems(self):
        for cid, items in self.items.items():
            keys = [mb.norm_problem(it["problem"]) for it in items]
            self.assertEqual(len(keys), len(set(keys)), cid)

    def test_compare_items_answer_in_options_and_true(self):
        for cid, items in self.items.items():
            for it in items:
                if it["type"] != "compare":
                    continue
                self.assertEqual(it["options"], [">", "<", "="], it["id"])
                self.assertIn(it["answer"], it["options"], it["id"])
                left, right = it["problem"].split("?")
                lv, rv = mathgrade.parse_expr(left).value, mathgrade.parse_expr(right).value
                truth = "=" if lv == rv else (">" if lv > rv else "<")
                self.assertEqual(it["answer"], truth, it["id"])

    def test_appending_never_reuses_ids_or_problems(self):
        with tempfile.TemporaryDirectory() as d:
            first = _read(_gen(Path(d), "m4.compare_fracs", 20, 42))
            second = _read(_gen(Path(d), "m4.compare_fracs", 20, 99))
            self.assertEqual(len(second), 40)
            ids = [it["id"] for it in second]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(int(ids[-1].rsplit(".", 1)[1]), 40)
            probs = [mb.norm_problem(it["problem"]) for it in second]
            self.assertEqual(len(probs), len(set(probs)))


class ValidationRefusesBadItemsTest(unittest.TestCase):
    def _item(self, **over):
        it = {"id": "m4.x.001", "competence": "m4.x", "type": "compute",
              "instruction": "Calcula.", "problem": "27 × 14", "answer": "378",
              "also_accept": [], "options": [], "why": "x", "status": "validated",
              "source": "test"}
        it.update(over)
        return it

    def test_wrong_answer_value_rejected(self):
        self.assertTrue(mb.validate_item(self._item(answer="387")))

    def test_unparseable_problem_rejected(self):
        self.assertTrue(mb.validate_item(self._item(problem="27 × x")))

    def test_compare_contradiction_rejected(self):
        self.assertTrue(mb.validate_item(
            self._item(type="compare", problem="3/4 ? 2/3", answer="<",
                       options=[">", "<", "="])))

    def test_compare_answer_not_in_options_rejected(self):
        self.assertTrue(mb.validate_item(
            self._item(type="compare", problem="3/4 ? 2/3", answer=">",
                       options=["<", "="])))

    def test_choose_distractor_also_correct_rejected(self):
        self.assertTrue(mb.validate_item(
            self._item(type="choose", answer="378", options=["378", "378.0", "387"])))

    def test_missing_field_rejected(self):
        it = self._item()
        del it["why"]
        self.assertTrue(mb.validate_item(it))

    def test_unknown_family_fails_loudly(self):
        import random
        with self.assertRaises(mb.GenError):
            mb.build_item("no_such_family", random.Random(1), "m4.x", 1, "test")

    def test_duplicate_problem_in_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m4.mult_2digit.json"
            item = self._item(id="m4.mult_2digit.001")
            p.write_text(json.dumps([item, dict(item, id="m4.mult_2digit.002")]),
                         encoding="utf-8")
            self.assertTrue(mb.validate_file(p))


class PilotOnDiskTest(unittest.TestCase):
    """The committed pilot (seed 42) must stand on its own."""

    def test_pilot_files_exist_with_items(self):
        for cid in COMPETENCES:
            items = _read(PILOT / f"{cid}.json")
            self.assertGreaterEqual(len(items), 25, cid)

    def test_pilot_items_all_valid(self):
        for cid in COMPETENCES:
            self.assertEqual(mb.validate_file(PILOT / f"{cid}.json"), [], cid)

    def test_pilot_answers_grade_10(self):
        for cid in COMPETENCES:
            for it in _read(PILOT / f"{cid}.json"):
                if it["type"] == "compare":
                    continue
                self.assertEqual(
                    mathgrade.grade_single(it["answer"], it["answer"], it["also_accept"])["score"],
                    10, it["id"])

    def test_validate_subcommand_passes_on_pilot(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mb.main(["validate", "--curriculum", str(CUR)])
        self.assertEqual(rc, 0, buf.getvalue())
        for cid in COMPETENCES:
            self.assertIn(f"{cid}.json", buf.getvalue())


# ------------------------------------------------------------- steps (WP2.1) ---

STEPS_PILOT = {
    "m4.mult_2digit": "partial_products",
    "m4.add_carry": "partial_sums",
    "m4.frac_add_unlike": "common_denominator",
    "m4.div_2x1": "long_division",
}
# The committed steps pilot lives in a steps/ SUBDIRECTORY of the bank dir.
# Since WP2.2 load_bank reaches it by name (`steps/<cid>__steps.json`) and
# bank_left/_bank_index walk it with the `__steps` stem normalized back to the
# competence — but tests/test_bank_review.py TheWholeBank still globs
# bank/*/*.json (one level) and never sees the subdir, which is the whole
# point of the location: TheWholeBank grades everything it finds with the
# language-shaped path.
STEPS_PILOT_DIR = PILOT / "steps"


def _gen_steps(tmp: Path, competence: str, family: str, n: int, seed: int) -> Path:
    rc = mb.main(["gen", "--curriculum", str(CUR), "--competence", competence,
                  "--family", family, "--n", str(n), "--seed", str(seed),
                  "--out", str(tmp), "--date", FIXED_DATE])
    assert rc == 0, f"gen failed for {competence}/{family}"
    return tmp / f"{competence}__steps.json"


class StepsDeterminismTest(unittest.TestCase):
    def test_same_seed_identical_json(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            for cid, fam in STEPS_PILOT.items():
                a = _gen_steps(Path(d1), cid, fam, 12, 42).read_text(encoding="utf-8")
                b = _gen_steps(Path(d2), cid, fam, 12, 42).read_text(encoding="utf-8")
                self.assertEqual(a, b, f"{fam}: same seed produced different JSON")

    def test_different_seed_different_items(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            for cid, fam in STEPS_PILOT.items():
                a = {mb.norm_problem(i["problem"]) for i in _read(_gen_steps(Path(d1), cid, fam, 12, 1))}
                b = {mb.norm_problem(i["problem"]) for i in _read(_gen_steps(Path(d2), cid, fam, 12, 7))}
                self.assertLess(len(a & b), len(a), f"{fam}: seed did not change the draw")


class StepsItemsTest(unittest.TestCase):
    """Fresh generation (seed 42, 12 per family) checked end to end."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.items = {}
        for cid, fam in STEPS_PILOT.items():
            cls.items[fam] = _read(_gen_steps(Path(cls.tmp.name), cid, fam, 12, 42))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_schema_and_status(self):
        for fam, items in self.items.items():
            self.assertEqual(len(items), 12, fam)
            for it in items:
                for f in mb.STEPS_REQUIRED_FIELDS:
                    self.assertIn(f, it, f"{it.get('id')}: missing {f}")
                self.assertEqual(it["type"], "steps", it["id"])
                # WP2.3 wired the per-line grader: steps items are generated
                # validated like compute items, and bank.py serves them.
                self.assertEqual(it["status"], "validated", it["id"])
                self.assertEqual(it["method"], fam, it["id"])
                self.assertTrue(it["why"].strip())
                self.assertEqual(it["instruction"], "Resol-ho pas a pas. Una línia per pas.")

    def test_every_step_parses_and_agrees(self):
        for fam, items in self.items.items():
            for it in items:
                for i, st in enumerate(it["steps"]):
                    self.assertEqual(st["n"], i + 1, f"{it['id']} step {i + 1}")
                    ev = mathgrade.parse_expr(st["expect"])
                    vv = mathgrade.parse_expr(st["value"])
                    self.assertEqual(ev.value, vv.value,
                                     f"{it['id']} step {st['n']}: {st['expect']!r} != {st['value']!r}")
                    for acc in st["accept"]:
                        self.assertTrue(mb._accept_ok(acc, vv.value),
                                        f"{it['id']} step {st['n']}: accept {acc!r} "
                                        f"does not mean {st['value']!r}")

    def test_last_step_equals_answer_and_problem(self):
        for fam, items in self.items.items():
            for it in items:
                aval = mathgrade.parse_expr(it["answer"]).value
                last = mathgrade.parse_expr(it["steps"][-1]["value"]).value
                self.assertEqual(last, aval, f"{it['id']}: last step != answer")
                pval = mathgrade.parse_expr(it["problem"]).value
                self.assertEqual(pval, aval, f"{it['id']}: problem != answer")

    def test_error_class_canonical(self):
        for fam, items in self.items.items():
            for it in items:
                for st in it["steps"]:
                    self.assertIn(st["error_class"], db_schema.ERROR_CATEGORIES,
                                  f"{it['id']} step {st['n']}: {st['error_class']!r}")
                    self.assertTrue(st["why"].strip(), f"{it['id']} step {st['n']}: empty why")

    def test_expected_trace_grades_via_grade_step(self):
        """The whole point of §4.2: the item's own trace, replayed line by
        line, is graded correct by the existing mathgrade.grade_step."""
        for fam, items in self.items.items():
            for it in items:
                for st in it["steps"]:
                    for line in (st["expect"], f"{st['expect']} = {st['value']}"):
                        v = mathgrade.grade_step(st["expect"], line)
                        self.assertEqual(v["score"], 10,
                                         f"{it['id']} step {st['n']}: {line!r} -> {v}")

    def test_no_duplicate_problems_within_family(self):
        for fam, items in self.items.items():
            keys = [mb.norm_problem(it["problem"]) for it in items]
            self.assertEqual(len(keys), len(set(keys)), fam)

    def test_ids_sequential(self):
        # A fresh file in an empty dir starts at .001; ids then continue
        # across the competence's files (see StepsIdUniquenessTest).
        for fam, items in self.items.items():
            nums = [int(it["id"].rsplit(".", 1)[1]) for it in items]
            self.assertEqual(nums, list(range(nums[0], nums[0] + len(nums))), fam)


class StepsServedByBankTest(unittest.TestCase):
    """WP2.2/2.3 flipped the gate: the __steps files ARE now part of the
    serving path (load_bank reads `steps/<cid>__steps.json` too, pick_item
    serves type:"steps"), and the STATUS filter is the only guard left —
    a demoted "generated" item is invisible again."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        bankdir = root / "curriculum" / "bank" / "math-m4" / "steps"
        bankdir.mkdir(parents=True)
        for cid in STEPS_PILOT:
            shutil.copy(STEPS_PILOT_DIR / f"{cid}__steps.json", bankdir / f"{cid}__steps.json")
        self.root = root
        self.data = root / "data"
        self.data.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_bank_and_pick_item_serve_steps(self):
        for cid in STEPS_PILOT:
            items = bankmod.load_bank(self.root, "math-m4", cid, self.data)
            self.assertEqual(len(items), 12, cid)
            self.assertTrue(all(it["type"] == "steps" for it in items), cid)
            self.assertTrue(bankmod.has_bank(self.root, "math-m4", cid, self.data), cid)
            picked = bankmod.pick_item(self.root, "math-m4", cid, self.data, FIXED_DATE)
            self.assertIsNotNone(picked, cid)
            self.assertEqual(picked["type"], "steps", cid)

    def test_bank_left_counts_under_the_real_competence(self):
        left = bankmod.bank_left(self.root, "math-m4", self.data)
        self.assertEqual(sorted(left), sorted(STEPS_PILOT), "no phantom __steps competence")
        for cid, entry in left.items():
            self.assertEqual(entry, {"unseen": 12, "total": 12}, cid)

    def test_generated_status_is_still_not_served(self):
        # The status gate survives the flip: demote one file and it vanishes.
        for cid in STEPS_PILOT:
            path = self.root / "curriculum" / "bank" / "math-m4" / "steps" / f"{cid}__steps.json"
            items = _read(path)
            for it in items:
                it["status"] = "generated"
            path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(bankmod.load_bank(self.root, "math-m4", cid, self.data), [], cid)
            self.assertFalse(bankmod.has_bank(self.root, "math-m4", cid, self.data), cid)
            self.assertIsNone(bankmod.pick_item(self.root, "math-m4", cid, self.data, FIXED_DATE), cid)
        self.assertEqual(bankmod.bank_left(self.root, "math-m4", self.data), {})

    def test_real_pilot_serves_compute_and_steps(self):
        with tempfile.TemporaryDirectory() as d:
            items = bankmod.load_bank(REPO, "math-m4", "m4.mult_2digit", d)
            self.assertGreaterEqual(len(items), 25 + 12)
            self.assertTrue(any(it["type"] == "steps" for it in items))
            self.assertTrue(any(it["type"] == "compute" for it in items))


class StepsPilotOnDiskTest(unittest.TestCase):
    def test_pilot_steps_files_exist_and_validate(self):
        for cid, fam in STEPS_PILOT.items():
            path = STEPS_PILOT_DIR / f"{cid}__steps.json"
            self.assertTrue(path.exists(), str(path))
            items = _read(path)
            self.assertEqual(len(items), 12, cid)
            self.assertEqual(mb.validate_file(path), [], cid)
            self.assertEqual({it["method"] for it in items}, {fam}, cid)
            # WP2.3: the pilot is validated — that is the gate that lets the
            # steps grader serve it.
            self.assertEqual({it["status"] for it in items}, {"validated"}, cid)

    def test_steps_files_invisible_to_every_bank_glob(self):
        """Pin the LOCATION invariant (WP2.2 kept it): the one-level bank glob
        that tests/test_bank_review.py TheWholeBank uses must not see the steps
        files — they live in the `steps/` subdir, which load_bank reaches by
        name. (The old non-recursive-glob invisibility of bank_left/
        _bank_index is gone on purpose: WP2.2 made those walks see the subdir
        and normalize the `__steps` stem back to the competence.)"""
        one_level = sorted((REPO / "curriculum" / "bank").glob("*/*.json"))
        self.assertFalse([f for f in one_level if "__steps" in f.name],
                         "steps files must not sit at bank/<stem>/ level")
        self.assertFalse([f for f in PILOT.glob("*.json") if "__steps" in f.name])
        # ...and the real serving path now returns compute AND steps items.
        with tempfile.TemporaryDirectory() as d:
            for cid in STEPS_PILOT:
                items = bankmod.load_bank(REPO, "math-m4", cid, d)
                self.assertTrue(any(it["type"] == "steps" for it in items), cid)


class StepsValidationRefusesBadItemsTest(unittest.TestCase):
    def _steps_item(self, **over):
        it = {"id": "m4.x.001", "competence": "m4.x", "type": "steps",
              "instruction": "Resol-ho pas a pas. Una línia per pas.",
              "problem": "12 × 25", "method": "partial_products",
              "steps": [
                  {"n": 1, "expect": "12 × 20", "value": "240",
                   "accept": ["12*20", "12 × 20 = 240"], "error_class": "procedure", "why": "a"},
                  {"n": 2, "expect": "12 × 5", "value": "60",
                   "accept": [], "error_class": "calculation", "why": "b"},
                  {"n": 3, "expect": "240 + 60", "value": "300",
                   "accept": [], "error_class": "carrying", "why": "c"},
              ],
              "answer": "300", "why": "w", "status": "generated", "source": "test"}
        it.update(over)
        return it

    def test_good_item_accepted(self):
        # _steps_item() defaults to "generated" — the validator now refuses
        # that (see test_status_generated_rejected), so accept a validated one.
        self.assertEqual(mb.validate_item(self._steps_item(status="validated")), [])

    def test_status_generated_rejected(self):
        # WP2.3 wired the steps grader: "generated" is no longer a status a
        # steps item may carry — validated/reviewed, same rule as compute.
        self.assertTrue(mb.validate_item(self._steps_item(status="generated")))

    def test_last_step_not_answer_rejected(self):
        bad = self._steps_item()
        bad["steps"][-1]["value"] = "301"
        self.assertTrue(mb.validate_item(bad))

    def test_step_expect_not_value_rejected(self):
        bad = self._steps_item()
        bad["steps"][1]["value"] = "61"
        self.assertTrue(mb.validate_item(bad))

    def test_bad_error_class_rejected(self):
        bad = self._steps_item()
        bad["steps"][0]["error_class"] = "aritmètica"
        self.assertTrue(mb.validate_item(bad))

    def test_unparseable_expect_rejected(self):
        bad = self._steps_item()
        bad["steps"][0]["expect"] = "12 × vint"
        self.assertTrue(mb.validate_item(bad))

    def test_accept_wrong_value_rejected(self):
        bad = self._steps_item()
        bad["steps"][0]["accept"] = ["12 × 21"]
        self.assertTrue(mb.validate_item(bad))

    def test_non_sequential_step_n_rejected(self):
        bad = self._steps_item()
        bad["steps"][1]["n"] = 5
        self.assertTrue(mb.validate_item(bad))

    def test_build_item_steps_status_validated(self):
        import random
        it = mb.build_item("partial_products", random.Random(3), "m4.mult_2digit", 1, "test")
        # WP2.3: the grader exists, so the generator emits served items.
        self.assertEqual(it["status"], "validated")
        self.assertEqual(it["type"], "steps")
        self.assertEqual(mb.validate_item(it), [])


if __name__ == "__main__":
    unittest.main()
