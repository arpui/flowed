#!/usr/bin/env python3
"""WP1.3 — the math bank types (compute / choose / compare), graded by
hooks/mathgrade.py through hooks/bank.py's dispatch (DISSENY-MATEMATIQUES §4.1/§4.3).

End-to-end through bank.answer_and_record (the function the server's
`curriculum.py bank answer` CLI calls) with a temp bank: verdicts and scores,
the unit case, compare symbols + Catalan words, bank-progress treating a 7/10
"near" as NOT correct (KNOWN_SCORE=8), and the feedback text the server renders
being parseable by persist-session.parse_error_patterns with a canonical
category. The language path (complete/choose/meaning/translate/correct) must
keep using canon/OSA unchanged — the fork still ships language banks.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))
import bank as bank_mod  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "hooks" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


persist = _load("persist-session")
TODAY = "2026-10-05"
STEM = "m4-test"


def item(**over):
    base = {"id": "m4.add_frac.001", "competence": "m4.add_frac", "type": "compute",
            "instruction": "Calcula.", "problem": "1/4 + 3/8", "answer": "5/8",
            "also_accept": [], "options": [], "why": "Denominador comú 8.", "status": "validated"}
    return {**base, **over}


class MathBankGrading(unittest.TestCase):
    """answer_and_record end-to-end: grade + bank-progress, temp bank on disk."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="test-bank-math-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = self.d / "repo"
        self.data = self.d / "data"
        bank = self.root / "curriculum" / "bank" / STEM
        bank.mkdir(parents=True)
        self.items = [
            item(),
            item(id="m4.add_frac.002", problem="24 × 9 + 48", answer="264",
                 why="Multipliqueu primer; després sumeu."),
            item(id="m4.add_frac.003", problem="Perímetre d'un quadrat de 3 cm", answer="12 cm",
                 why="4 × 3 cm."),
            item(id="m4.doble.004", competence="m4.doble", type="choose",
                 problem="Quina operació resol «el doble de 5»?", options=["5+2", "5×2", "5−2"],
                 answer="5×2", why="El doble és multiplicar per 2."),
            item(id="m4.opcions.005", competence="m4.doble", type="choose",
                 problem="Quants en hi ha? 324", options=["324", "342", "325"], answer="324",
                 why="Compta otra vegada."),
            item(id="m4.compara.006", competence="m4.compara", type="compare",
                 problem="3/4 ○ 2/3", options=[">", "<", "="], answer=">",
                 why="3/4 = 0,75 i 2/3 ≈ 0,66.", error_class="sign"),
        ]
        (bank / "m4.add_frac.json").write_text(json.dumps(self.items[:3]), encoding="utf-8")
        (bank / "m4.doble.json").write_text(json.dumps(self.items[3:5]), encoding="utf-8")
        (bank / "m4.compara.json").write_text(json.dumps(self.items[5:]), encoding="utf-8")

    def answer(self, item_id, competence, text):
        return bank_mod.answer_and_record(self.root, STEM, item_id, competence, text, self.data, TODAY)

    def progress(self, item_id):
        prog = json.loads((self.data / "bank-progress.json").read_text(encoding="utf-8"))
        for by_item in prog.values():
            if item_id in by_item:
                return by_item[item_id]
        return None

    # ---- compute -------------------------------------------------------------
    def test_compute_exact_and_equivalent_notation(self):
        for text in ("5/8", "0,625", "1/4 + 3/8 = 5/8"):  # full equation: grade the result
            r = self.answer("m4.add_frac.001", "m4.add_frac", text)
            self.assertEqual((10, "correct"), (r["score"], r["verdict"]), text)
            self.assertEqual("1/4 + 3/8 = 5/8", r["correct_version"])

    def test_compute_near_is_a_transcription_slip(self):
        r = self.answer("m4.add_frac.002", "m4.add_frac", "246")  # 264 with digits swapped
        self.assertEqual((7, "near"), (r["score"], r["verdict"]))
        self.assertIn("264", r["note"])

    def test_compute_wrong_and_empty(self):
        r = self.answer("m4.add_frac.001", "m4.add_frac", "1/2")
        self.assertEqual((3, "wrong"), (r["score"], r["verdict"]))
        self.assertEqual("Denominador comú 8.", r["note"])  # the item's why
        for text in ("", "no ho sé"):
            r = self.answer("m4.add_frac.001", "m4.add_frac", text)
            self.assertEqual((0, "empty"), (r["score"], r["verdict"]), text)

    def test_compute_unit_expected(self):
        self.assertEqual(10, self.answer("m4.add_frac.003", "m4.add_frac", "12 cm")["score"])
        for text, why in (("12", "que falta"), ("12 m", "errònia")):
            r = self.answer("m4.add_frac.003", "m4.add_frac", text)
            self.assertEqual((7, "near"), (r["score"], r["verdict"]), text)
            self.assertIn(why, r["note"])
        self.assertEqual("Perímetre d'un quadrat de 3 cm = 12 cm",
                         self.answer("m4.add_frac.003", "m4.add_frac", "12 cm")["correct_version"])

    # ---- choose --------------------------------------------------------------
    def test_choose_operation_and_result(self):
        self.assertEqual(10, self.answer("m4.doble.004", "m4.doble", "5×2")["score"])
        self.assertEqual(3, self.answer("m4.doble.004", "m4.doble", "5+2")["score"])
        # a DIFFERENT option one digit off is wrong, never "near": picking 342
        # when 324 was asked is a wrong choice, not a slip of the finger.
        r = self.answer("m4.opcions.005", "m4.doble", "342")
        self.assertEqual((3, "wrong"), (r["score"], r["verdict"]))

    # ---- compare -------------------------------------------------------------
    def test_compare_symbols_and_catalan_words(self):
        for text in (">", "major que", "més gran que", " > "):
            r = self.answer("m4.compara.006", "m4.compara", text)
            self.assertEqual((10, "correct"), (r["score"], r["verdict"]), text)
        for text in ("<", "menor que", "menys que", "igual", "igual que"):
            r = self.answer("m4.compara.006", "m4.compara", text)
            self.assertEqual((3, "wrong"), (r["score"], r["verdict"]), text)
        self.assertEqual("3/4 > 2/3", self.answer("m4.compara.006", "m4.compara", ">")["correct_version"])
        self.assertEqual(0, self.answer("m4.compara.006", "m4.compara", "")["score"])

    # ---- progress: near is NOT known (KNOWN_SCORE = 8) ------------------------
    def test_progress_near_keeps_the_item_coming_back(self):
        self.answer("m4.add_frac.002", "m4.add_frac", "246")  # near, 7/10
        self.assertFalse(self.progress("m4.add_frac.002")["correct"])
        self.answer("m4.add_frac.002", "m4.add_frac", "264")  # then exact
        self.assertTrue(self.progress("m4.add_frac.002")["correct"])
        self.assertEqual(TODAY, self.progress("m4.add_frac.002")["date"])

    # ---- the language path is untouched ---------------------------------------
    def test_language_choose_still_grades_via_canon(self):
        lang = {"id": "a1.articles_plurals.009", "competence": "a1.articles_plurals", "type": "choose",
                "instruction": "Choose a or an.", "sentence": "I need ___ umbrella.", "context": "",
                "answer": "an", "also_accept": [], "options": ["a", "an"], "why": "vowel sound",
                "status": "reviewed"}
        self.assertEqual(10, bank_mod.grade(lang, "an")["score"])
        self.assertEqual(3, bank_mod.grade(lang, "a")["score"])  # same-lesson other word
        self.assertEqual("I need an umbrella.", bank_mod.grade(lang, "an")["correct_version"])


class MathFeedbackIsParseable(unittest.TestCase):
    """The exact feedback text server/src/bank.ts `mathFeedback` renders (the
    same strings are asserted in server/test/bank.test.ts, where it is the real
    function) must feed persist-session.parse_error_patterns a CANONICAL math
    category — that is what turns a bank miss into a mistakes-db pattern."""

    NEAR_FB = (
        "🟡 Almost — gairebé: s'escriu «264».\n\n"
        "**Corrections:**\n"
        "- ❌ \"246\" → **\"24 × 9 + 48 = 264\"** (calculation — gairebé: s'escriu «264»)\n\n"
        "**Correct version:**\n\"24 × 9 + 48 = 264\"\n\n"
        "**Score: 7/10** Very close — read the note and try the next one!"
    )
    WRONG_FB = (
        "🔴 Not quite — the correct answer is \"3/4 > 2/3\".\n\n"
        "**Corrections:**\n"
        "- ❌ \"<\" → **\"3/4 > 2/3\"** (sign — 3/4 = 0,75 i 2/3 ≈ 0,66.)\n\n"
        "**Correct version:**\n\"3/4 > 2/3\"\n\n"
        "**Score: 3/10** Keep practising — you'll get it."
    )
    OK_FB = (
        "✅ Perfect! \"1/4 + 3/8 = 5/8\" is right.\n\n"
        "**Corrections:**\n- ✅ \"1/4 + 3/8 = 5/8\" — exactly right.\n\n"
        "**Correct version:**\n\"1/4 + 3/8 = 5/8\"\n\n"
        "**Score: 10/10** 🎉 Perfect! You got it right on the first try. Keep up the good work!"
    )

    def patterns(self, fb):
        return persist.parse_error_patterns([("assistant", fb)])

    def test_near_lands_a_canonical_calculation_pattern(self):
        pats = self.patterns(self.NEAR_FB)
        self.assertEqual(1, len(pats), pats)
        self.assertEqual("calculation", pats[0]["category"])
        self.assertEqual("246", pats[0]["example_incorrect"])

    def test_wrong_uses_the_items_error_class(self):
        pats = self.patterns(self.WRONG_FB)
        self.assertEqual(1, len(pats), pats)
        self.assertEqual("sign", pats[0]["category"])
        self.assertEqual("<", pats[0]["example_incorrect"])

    def test_correct_answer_produces_no_pattern(self):
        self.assertEqual([], self.patterns(self.OK_FB))


if __name__ == "__main__":
    unittest.main()
