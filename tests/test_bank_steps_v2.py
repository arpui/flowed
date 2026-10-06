#!/usr/bin/env python3
"""WP2.5 — v2 incremental steps: one step per message (DISSENY-MATEMATIQUES
§4.2 "v2 pas a pas", §5 row 2.5).

The session state (which step is pending, attempts) lives in the server; the
stateless half is here. Pinned:

  * `grade_step` reuses `_grade_step_line` verbatim — form AND value, `accept`
    alternates, near-slip — and adds the step's error_class/why/expect_line
    for the server's retry note; it writes NO progress;
  * `finalize_steps` scores on v1's exact scale: all first-try → 10, a step
    that needed a retry → 7, a revealed step → 3; the trace is
    `[{n, ok, got}]` with NO `propagated` anywhere (every step was attempted);
  * `failed_step`/`error_class` name the first outright failure (a revealed
    step) when there is one, else the first retried step; a retried step whose
    first slip was a digit slip files under "calculation" (the v1 near rule);
  * `answer_and_record_steps` writes bank-progress once, correct = score >= 8
    (KNOWN_SCORE), like `answer_and_record`;
  * the CLI actions `grade-step` / `finalize-steps` reach them;
  * v1 all-at-once is untouched: the same item graded whole still propagates.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))
import bank as bank_mod  # noqa: E402

TODAY = "2026-10-06"
STEM = "m4-steps2-test"


def steps_item(**over):
    base = {
        "id": "m4.mult_2digit.911", "competence": "m4.mult_2digit", "type": "steps",
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


class GradeStep(unittest.TestCase):
    """One line against one step — the v1 `_grade_step_line` semantics."""

    def setUp(self):
        self.item = steps_item()

    def test_correct_form(self):
        r = bank_mod.grade_step(self.item, 1, "93 × 20")
        self.assertEqual(r["verdict"], "correct")
        self.assertEqual(r["got"], "93 × 20")
        self.assertEqual(r["error_class"], "procedure")
        self.assertEqual(r["expect_line"], "93 × 20 = 1860")
        self.assertIn("Separa 25", r["why"])

    def test_accept_alternate_and_assertion(self):
        self.assertEqual(bank_mod.grade_step(self.item, 1, "93 * 20")["verdict"], "correct")
        self.assertEqual(bank_mod.grade_step(self.item, 1, "93 × 20 = 1860")["verdict"], "correct")

    def test_near_is_a_digit_slip(self):
        r = bank_mod.grade_step(self.item, 2, "93 × 5 = 456")   # 465 transposed
        self.assertEqual(r["verdict"], "near")
        self.assertEqual(r["error_class"], "calculation")       # v1 near rule

    def test_wrong_line(self):
        r = bank_mod.grade_step(self.item, 1, "93 × 25")
        self.assertEqual(r["verdict"], "wrong")
        self.assertEqual(r["error_class"], "procedure")         # the step's own class

    def test_unparseable_line(self):
        r = bank_mod.grade_step(self.item, 1, "no ho sé")
        self.assertEqual(r["verdict"], "wrong")
        self.assertEqual(r["note"], "no s'ha entès l'operació")

    def test_unknown_step(self):
        self.assertIn("error", bank_mod.grade_step(self.item, 9, "93 × 20"))

    def test_writes_no_progress(self):
        # grade_step is pure: the item is recorded only at finalize.
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            bank_mod.grade_step(self.item, 1, "93 × 20")
            self.assertFalse((data / "bank-progress.json").exists())


def results(*per_step):
    """per_step: (n, ok, attempts, revealed?, first_wrong?, near?)"""
    out = []
    for t in per_step:
        r = {"n": t[0], "ok": t[1], "got": t[2], "attempts": t[3]}
        if len(t) > 4 and t[4]:
            r["revealed"] = True
        if len(t) > 5 and t[5] is not None:
            r["first_wrong"] = t[5]
        if len(t) > 6 and t[6]:
            r["near"] = True
        out.append(r)
    return out


class FinalizeSteps(unittest.TestCase):
    """The v2 record payload: v1's scale, no propagation."""

    def setUp(self):
        self.item = steps_item()

    def test_all_first_try_scores_10(self):
        g = bank_mod.finalize_steps(self.item, results(
            (1, True, "93 × 20", 1), (2, True, "93 × 5", 1), (3, True, "1860 + 465", 1)))
        self.assertEqual((g["score"], g["verdict"]), (10, "correct"))
        self.assertEqual(g["mode"], "v2")
        self.assertNotIn("failed_step", g)
        self.assertNotIn("error_class", g)

    def test_retry_scores_7(self):
        g = bank_mod.finalize_steps(self.item, results(
            (1, True, "93 × 20", 1),
            (2, True, "93 × 5", 2, None, "93 × 6", False),
            (3, True, "1860 + 465", 1)))
        self.assertEqual((g["score"], g["verdict"]), (7, "near"))
        self.assertEqual(g["failed_step"], 2)
        self.assertEqual(g["error_class"], "calculation")   # step 2's own class
        self.assertEqual(g["got"], "93 × 6")                # the slip, not the fix

    def test_retry_after_near_slip_files_calculation(self):
        g = bank_mod.finalize_steps(self.item, results(
            (1, True, "93 × 20", 1),
            (2, True, "93 × 5", 2, None, "93 × 5 = 456", True),
            (3, True, "1860 + 465", 1)))
        self.assertEqual((g["score"], g["verdict"]), (7, "near"))
        self.assertEqual(g["error_class"], "calculation")

    def test_reveal_scores_3_and_names_the_revealed_step(self):
        g = bank_mod.finalize_steps(self.item, results(
            (1, True, "93 × 20", 2, None, "93 × 21", False),
            (2, False, "93 × 7", 2, True, "93 × 6", False),
            (3, True, "1860 + 465", 1)))
        self.assertEqual((g["score"], g["verdict"]), (3, "wrong"))
        # the first OUTRIGHT failure (revealed) wins over an earlier retry
        self.assertEqual(g["failed_step"], 2)
        self.assertEqual(g["error_class"], "calculation")

    def test_revealed_step_keeps_its_own_error_class(self):
        g = bank_mod.finalize_steps(self.item, results(
            (1, False, "93 × 25", 2, True, "93 × 26", False),
            (2, True, "93 × 5", 1), (3, True, "1860 + 465", 1)))
        self.assertEqual(g["score"], 3)
        self.assertEqual(g["error_class"], "procedure")

    def test_trace_shape_matches_v1_minus_propagation(self):
        g = bank_mod.finalize_steps(self.item, results(
            (1, True, "93 × 20", 1), (2, False, "93 × 7", 2, True, "93 × 6", False),
            (3, True, "1860 + 465", 1)))
        self.assertEqual([s["n"] for s in g["steps"]], [1, 2, 3])
        self.assertEqual([s["ok"] for s in g["steps"]], [True, False, True])
        self.assertEqual(g["steps"][1]["got"], "93 × 7")   # last attempt, not the reveal
        for s in g["steps"]:
            self.assertNotIn("propagated", s)              # v2: every step attempted
            self.assertEqual(set(s), {"n", "ok", "got"})

    def test_correct_version_is_the_full_trace(self):
        g = bank_mod.finalize_steps(self.item, results(
            (1, True, "93 × 20", 1), (2, True, "93 × 5", 1), (3, True, "1860 + 465", 1)))
        self.assertEqual(g["correct_version"],
                         "93 × 20 = 1860\n93 × 5 = 465\n1860 + 465 = 2325")


class RecordSteps(unittest.TestCase):
    """finalize + the one progress write."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test-steps-v2-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "repo"
        self.data = self.tmp / "data"
        bank = self.root / "curriculum" / "bank" / STEM / "steps"
        bank.mkdir(parents=True)
        (bank / "m4.mult_2digit__steps.json").write_text(
            json.dumps([steps_item()], ensure_ascii=False), encoding="utf-8")

    def test_progress_written_once_at_finalize(self):
        out = bank_mod.answer_and_record_steps(
            self.root, STEM, "m4.mult_2digit.911", "m4.mult_2digit",
            results((1, True, "93 × 20", 1), (2, True, "93 × 5", 2, None, "93 × 6", False),
                    (3, True, "1860 + 465", 1)),
            self.data, TODAY)
        self.assertEqual(out["score"], 7)
        self.assertEqual(out["item"]["id"], "m4.mult_2digit.911")
        prog = json.loads((self.data / "bank-progress.json").read_text())
        rec = prog["m4.mult_2digit"]["m4.mult_2digit.911"]
        self.assertEqual(rec["date"], TODAY)
        # KNOWN_SCORE is 8 (server/src/pacing.ts): a 7 "needed a retry" is not
        # known, so the item keeps coming back — same boundary as v1's near.
        self.assertFalse(rec["correct"])

    def test_revealed_item_not_correct_in_progress(self):
        bank_mod.answer_and_record_steps(
            self.root, STEM, "m4.mult_2digit.911", "m4.mult_2digit",
            results((1, False, "x", 2, True, "y", False), (2, True, "93 × 5", 1),
                    (3, True, "1860 + 465", 1)),
            self.data, TODAY)
        prog = json.loads((self.data / "bank-progress.json").read_text())
        self.assertFalse(prog["m4.mult_2digit"]["m4.mult_2digit.911"]["correct"])


class BankCli(unittest.TestCase):
    """curriculum.py bank grade-step | finalize-steps (the server's door).

    The CLI resolves the bank from the REPO root (no override), so this drives
    the real pilot item m4.mult_2digit.031 with a throwaway --data dir."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test-steps-v2-cli-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = self.tmp / "data"

    def _cli(self, *args):
        r = subprocess.run(
            [sys.executable, str(REPO / "hooks" / "curriculum.py"), "bank", *args,
             "--curriculum", str(REPO / "curriculum" / "math-m4.md"),
             "--data", str(self.data), "--today", TODAY],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_grade_step_action(self):
        out = self._cli("grade-step", "--competence", "m4.mult_2digit",
                        "--item-id", "m4.mult_2digit.031", "--step", "2", "--line", "93 × 5")
        self.assertEqual(out["verdict"], "correct")

    def test_finalize_steps_action(self):
        res = results((1, True, "93 × 20", 1), (2, True, "93 × 5", 1), (3, True, "1860 + 465", 1))
        out = self._cli("finalize-steps", "--competence", "m4.mult_2digit",
                        "--item-id", "m4.mult_2digit.031", "--results", json.dumps(res))
        self.assertEqual(out["score"], 10)
        self.assertEqual(out["mode"], "v2")
        self.assertTrue((self.data / "bank-progress.json").exists())

    def test_v1_answer_action_untouched(self):
        # the same item, whole trace, still grades through `answer` with
        # propagation — v1 did not move (WP2.5 is additive).
        whole = "93 × 20\n93 × 6\n1860 + 465"
        out = self._cli("answer", "--competence", "m4.mult_2digit",
                        "--item-id", "m4.mult_2digit.031", "--answer", whole)
        self.assertEqual(out["score"], 3)
        self.assertTrue(out["steps"][1]["ok"] is False)
        self.assertTrue(out["steps"][2].get("propagated"))


if __name__ == "__main__":
    unittest.main()
