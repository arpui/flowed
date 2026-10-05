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
"""
import importlib.util
import io
import json
import contextlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))

import curriculum as cu   # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
