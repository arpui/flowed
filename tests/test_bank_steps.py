#!/usr/bin/env python3
"""WP2.2–2.4 — steps items on the serving and grading path (DISSENY-MATEMATIQUES
§4.2/§4.3, the v1 "all-at-once" interaction of §6 D5).

The learner types the WHOLE worked solution, one operation per line. Pinned:

  * the loader sees `steps/<cid>__steps.json` and pick_item serves type:"steps"
    (WP2.2) — while TheWholeBank's one-level glob still does not (pinned in
    test_mathbank.py, not here);
  * an all-correct trace scores 10 and the record carries steps:[{n, ok, got}]
    with one entry per EXPECTED step (WP2.3);
  * the FIRST failed step decides everything: score 3, `error_class` = that
    step's error_class, and every later step is `propagated` — never graded
    on its own, so one slip is one pattern, not three (§7 risk row);
  * a digit transposition on a step's value is "near" (7), like grade_single's;
  * an empty answer is 0; missing lines are "incomplete"; extra lines are
    ignored; blank lines are skipped;
  * every committed pilot item's own expected trace (and its `accept`
    alternates) replays to 10 through bank.grade — 48 items end to end.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))
import bank as bank_mod  # noqa: E402

TODAY = "2026-10-06"
STEM = "m4-steps-test"


def steps_item(**over):
    base = {
        "id": "m4.mult_2digit.901", "competence": "m4.mult_2digit", "type": "steps",
        "instruction": "Resol-ho pas a pas. Una línia per pas.",
        "problem": "93 × 25", "method": "partial_products",
        "steps": [
            {"n": 1, "expect": "93 × 20", "value": "1860",
             "accept": ["93 * 20", "93 × 20 = 1860"], "error_class": "procedure",
             "why": "Separa 25 en 20 + 5 i multiplica 93 × 20."},
            {"n": 2, "expect": "93 × 5", "value": "465",
             "accept": ["93 * 5", "93 × 5 = 465"], "error_class": "calculation",
             "why": "Ara les unitats: 93 × 5."},
            {"n": 3, "expect": "1860 + 465", "value": "2325",
             "accept": ["1860 + 465 = 2325"], "error_class": "carrying",
             "why": "Suma els dos productes parcials."},
        ],
        "answer": "2325", "why": "25 = 20 + 5.", "status": "validated",
        "source": "test",
    }
    return {**base, **over}


class StepsServing(unittest.TestCase):
    """WP2.2: the loader walk reaches the steps/ subdir; pick_item serves it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test-bank-steps-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "repo"
        self.data = self.tmp / "data"
        bank = self.root / "curriculum" / "bank" / STEM / "steps"
        bank.mkdir(parents=True)
        self.file = bank / "m4.mult_2digit__steps.json"
        self.file.write_text(json.dumps([steps_item()], ensure_ascii=False), encoding="utf-8")

    def test_loader_sees_the_steps_file(self):
        items = bank_mod.load_bank(self.root, STEM, "m4.mult_2digit", self.data)
        self.assertEqual([it["id"] for it in items], ["m4.mult_2digit.901"])
        self.assertTrue(bank_mod.has_bank(self.root, STEM, "m4.mult_2digit", self.data))

    def test_generated_status_still_not_served(self):
        self.file.write_text(json.dumps([steps_item(status="generated")], ensure_ascii=False),
                             encoding="utf-8")
        self.assertEqual(bank_mod.load_bank(self.root, STEM, "m4.mult_2digit", self.data), [])
        self.assertIsNone(bank_mod.pick_item(self.root, STEM, "m4.mult_2digit", self.data, TODAY))

    def test_pick_item_serves_a_steps_item(self):
        picked = bank_mod.pick_item(self.root, STEM, "m4.mult_2digit", self.data, TODAY)
        self.assertIsNotNone(picked)
        self.assertEqual(picked["type"], "steps")

    def test_bank_left_counts_under_the_competence(self):
        left = bank_mod.bank_left(self.root, STEM, self.data)
        self.assertEqual(left, {"m4.mult_2digit": {"unseen": 1, "total": 1}})

    def test_main_and_steps_files_merge_for_one_competence(self):
        main = self.root / "curriculum" / "bank" / STEM / "m4.mult_2digit.json"
        compute = {"id": "m4.mult_2digit.001", "competence": "m4.mult_2digit", "type": "compute",
                   "instruction": "Calcula.", "problem": "24 × 3", "answer": "72",
                   "also_accept": [], "options": [], "why": "", "status": "validated"}
        main.write_text(json.dumps([compute], ensure_ascii=False), encoding="utf-8")
        items = bank_mod.load_bank(self.root, STEM, "m4.mult_2digit", self.data)
        self.assertEqual({it["type"] for it in items}, {"compute", "steps"})
        left = bank_mod.bank_left(self.root, STEM, self.data)
        self.assertEqual(left["m4.mult_2digit"], {"unseen": 2, "total": 2})


class StepsGrading(unittest.TestCase):
    """WP2.3: per-line grading, propagation, scores."""

    def setUp(self):
        self.item = steps_item()

    def grade(self, answer):
        return bank_mod.grade(self.item, answer)

    def test_all_correct_trace_scores_10_with_steps(self):
        r = self.grade("93 × 20 = 1860\n93 × 5 = 465\n1860 + 465 = 2325")
        self.assertEqual((r["score"], r["verdict"]), (10, "correct"))
        self.assertEqual([(s["n"], s["ok"]) for s in r["steps"]], [(1, True), (2, True), (3, True)])
        self.assertEqual(r["steps"][0]["got"], "93 × 20 = 1860")
        self.assertNotIn("propagated", r["steps"][0])
        # "Correct version:" is the full correct trace, one step per line.
        self.assertEqual(r["correct_version"], "93 × 20 = 1860\n93 × 5 = 465\n1860 + 465 = 2325")

    def test_bare_expression_lines_and_accept_alternates(self):
        r = self.grade("93 * 20\n93 × 5 = 465\n1860 + 465")
        self.assertEqual(r["score"], 10, r)

    def test_first_step_wrong_propagates_and_names_the_error_class(self):
        # step 1 does the wrong decomposition; steps 2-3 are internally
        # consistent with it — they must NOT be counted as new errors.
        r = self.grade("93 × 25 = 2325\n93 × 0 = 0\n2325 + 0 = 2325")
        self.assertEqual((r["score"], r["verdict"]), (3, "wrong"))
        self.assertEqual(r["error_class"], "procedure")  # step 1's error_class
        self.assertEqual(r["failed_step"], 1)
        self.assertEqual(r["steps"][0], {"n": 1, "ok": False, "got": "93 × 25 = 2325"})
        for s in r["steps"][1:]:
            self.assertTrue(s.get("propagated"), s)
            self.assertFalse(s["ok"])
            self.assertIsNotNone(s["got"])  # their lines are shown, not re-graded

    def test_wrong_in_a_later_step_only(self):
        # 400 for 465 is two digit edits away — a real calculation error, not
        # the one-edit "near" slip (that case is tested just below).
        r = self.grade("93 × 20 = 1860\n93 × 5 = 400\n1860 + 400 = 2260")
        self.assertEqual((r["score"], r["verdict"]), (3, "wrong"))
        self.assertEqual(r["error_class"], "calculation")  # step 2's error_class
        self.assertEqual(r["failed_step"], 2)
        self.assertTrue(r["steps"][0]["ok"])
        self.assertTrue(r["steps"][2].get("propagated"))

    def test_transposition_on_a_step_is_near(self):
        # right operation, digits of the result transposed: 1680 for 1860.
        r = self.grade("93 × 20 = 1680\n1680 + 465 = 2145")
        self.assertEqual((r["score"], r["verdict"]), (7, "near"))
        self.assertEqual(r["error_class"], "calculation")
        self.assertEqual(r["failed_step"], 1)
        self.assertTrue(r["steps"][1].get("propagated"))

    def test_empty_answer_scores_zero(self):
        for answer in ("", "   ", "no ho sé"):
            r = self.grade(answer)
            self.assertEqual((r["score"], r["verdict"]), (0, "empty"), answer)
            self.assertEqual([(s["n"], s["ok"], s["got"]) for s in r["steps"]],
                             [(1, False, None), (2, False, None), (3, False, None)], answer)

    def test_missing_lines_are_incomplete_and_stop_the_trace(self):
        r = self.grade("93 × 20 = 1860")
        self.assertEqual((r["score"], r["verdict"]), (3, "wrong"))
        self.assertEqual(r["error_class"], "incomplete")
        self.assertEqual(r["failed_step"], 2)
        self.assertTrue(r["steps"][0]["ok"])
        self.assertEqual(r["steps"][1]["got"], None)
        self.assertTrue(r["steps"][2].get("propagated"))

    def test_blank_lines_skipped_extra_lines_ignored(self):
        r = self.grade("\n93 × 20 = 1860\n\n93 × 5 = 465\n1860 + 465 = 2325\ncomprovació 2325\n")
        self.assertEqual(r["score"], 10, r)

    def test_unparseable_line_is_wrong_not_a_crash(self):
        r = self.grade("poma de sant joan\n93 × 5 = 465\n1860 + 465 = 2325")
        self.assertEqual((r["score"], r["verdict"]), (3, "wrong"))
        self.assertEqual(r["failed_step"], 1)
        self.assertEqual(r["error_class"], "procedure")

    def test_two_equals_on_a_line_is_wrong_not_a_crash(self):
        r = self.grade("93 × 20 = 1860 = 2\n93 × 5 = 465\n1860 + 465 = 2325")
        self.assertEqual(r["score"], 3, r)

    def test_answer_and_record_writes_progress_and_steps(self):
        tmp = Path(tempfile.mkdtemp(prefix="test-bank-steps-rec-"))
        try:
            root = tmp / "repo"
            data = tmp / "data"
            bank = root / "curriculum" / "bank" / STEM / "steps"
            bank.mkdir(parents=True)
            (bank / "m4.mult_2digit__steps.json").write_text(
                json.dumps([self.item], ensure_ascii=False), encoding="utf-8")
            r = bank_mod.answer_and_record(root, STEM, self.item["id"], "m4.mult_2digit",
                                           "93 × 20 = 1860\n93 × 5 = 465\n1860 + 465 = 2325",
                                           data, TODAY)
            self.assertEqual(r["score"], 10)
            self.assertEqual(len(r["steps"]), 3)
            prog = json.loads((data / "bank-progress.json").read_text(encoding="utf-8"))
            self.assertTrue(prog["m4.mult_2digit"][self.item["id"]]["correct"])
        finally:
            shutil.rmtree(tmp, True)


class StepsIdUniqueness(unittest.TestCase):
    """bank.py merges `<cid>.json` and `steps/<cid>__steps.json` into ONE item
    set addressed by id (progress, queue, records) — so an id may appear in
    only one of the two files. The generator numbers across both; the pilot
    was renumbered to prove it (mult_2digit / frac_add_unlike steps start at
    .031, after the 30 compute items)."""

    PILOT = REPO / "curriculum" / "bank" / "math-m4"

    def test_merged_item_set_has_unique_ids(self):
        for cid in ("m4.mult_2digit", "m4.frac_add_unlike", "m4.add_carry", "m4.div_2x1"):
            items = bank_mod.load_bank(self.PILOT.parent.parent, "math-m4", cid, None)
            ids = [it["id"] for it in items]
            self.assertEqual(len(ids), len(set(ids)), cid)

    def test_generator_continues_numbering_across_files(self):
        import subprocess
        tmp = Path(tempfile.mkdtemp(prefix="test-steps-gen-"))
        try:
            bank = tmp / "steps"
            bank.mkdir(parents=True)
            (tmp / "m4.mult_2digit.json").write_text(json.dumps(
                [{"id": "m4.mult_2digit.007", "competence": "m4.mult_2digit", "type": "compute",
                  "instruction": "Calcula.", "problem": "24 × 3", "answer": "72", "also_accept": [],
                  "options": [], "why": "", "status": "validated", "source": "test"}],
                ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(REPO / "scripts" / "mathbank.py"), "gen",
                            "--curriculum", str(REPO / "curriculum" / "math-m4.md"),
                            "--competence", "m4.mult_2digit", "--family", "partial_products",
                            "--n", "2", "--seed", "5", "--out", str(bank), "--date", "2026-10-06"],
                           check=True, capture_output=True)
            new = json.loads((bank / "m4.mult_2digit__steps.json").read_text(encoding="utf-8"))
            self.assertEqual([it["id"] for it in new], ["m4.mult_2digit.008", "m4.mult_2digit.009"])
        finally:
            shutil.rmtree(tmp, True)


class CommittedPilotReplays(unittest.TestCase):
    """Every committed pilot item (48, all four families): its own expected
    trace — each step as bare `expect` and as `expect = value` — and its
    `accept` alternates all grade correct through bank.grade."""

    PILOT = REPO / "curriculum" / "bank" / "math-m4" / "steps"

    def test_every_pilot_trace_grades_10(self):
        checked = 0
        for f in sorted(self.PILOT.glob("*.json")):
            for it in json.loads(f.read_text(encoding="utf-8")):
                self.assertEqual(it["status"], "validated", it["id"])
                bare = "\n".join(s["expect"] for s in it["steps"])
                full = "\n".join(f"{s['expect']} = {s['value']}" for s in it["steps"])
                self.assertEqual(bank_mod.grade(it, bare)["score"], 10, it["id"])
                self.assertEqual(bank_mod.grade(it, full)["score"], 10, it["id"])
                # replay with ONE step written its `accept` way, the rest bare
                for i, s in enumerate(it["steps"]):
                    for a in s.get("accept", []):
                        t = [x["expect"] for x in it["steps"]]
                        t[i] = a
                        self.assertEqual(bank_mod.grade(it, "\n".join(t))["score"], 10,
                                         f"{it['id']} step {s['n']} accept {a!r}")
                checked += 1
        self.assertEqual(checked, 48)


if __name__ == "__main__":
    unittest.main()
