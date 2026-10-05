#!/usr/bin/env python3
"""🧮 WP1.2 — hooks/mathgrade.py: the deterministic arithmetic grader.

Table-driven: parse values, canonical forms, grade_single verdicts
(correct/near/wrong/empty, also_accept, units), grade_step (forms, sides,
strict_form), and the CLI. DISSENY-MATEMATIQUES §4.3.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))
import mathgrade as mg  # noqa: E402


class TestParseValues(unittest.TestCase):
    """parse_expr: exact rational values."""

    VALUES = [
        ("3/4", Fraction(3, 4)),
        ("0,75", Fraction(3, 4)),          # decimal comma
        (".75", Fraction(3, 4)),
        ("0.75", Fraction(3, 4)),
        ("3,5", Fraction(7, 2)),
        ("1 1/2 + 1/4", Fraction(7, 4)),   # mixed number
        ("-1 1/2", Fraction(-3, 2)),       # minus applies to the whole mixed number
        ("2 × 3", 6),
        ("6 ÷ 2", 3),
        ("2 · 3", 6),
        ("-(-3)", 3),
        ("2^3", 8),
        ("2 ** 3", 8),
        ("(1+2)*3", 9),
        ("10 - 2 - 3", 5),
        ("1/3 + 1/6", Fraction(1, 2)),
        ("1000000", 1000000),
        ("99999999999999999999999 + 1", 10**23),   # huge ints fine
        ("2^100", 2**100),
        ("12/4", 3),                        # NOT a mixed number: no space
        ("7/4", Fraction(7, 4)),
        ("+5", 5),
        ("  3 +4 ", 7),                     # whitespace
        ("−3 + 5", 2),                      # unicode minus
    ]

    def test_values(self):
        for text, want in self.VALUES:
            with self.subTest(text=text):
                self.assertEqual(mg.parse_expr(text).value, Fraction(want))

    BAD = [
        "1/0",            # division by zero
        "3 + ",           # incomplete
        "abc",            # name
        "len(1)",         # call
        "[1, 2]",         # subscript/list
        "1 == 1",         # comparison
        "x + 1",          # name
        "1.000.000",      # thousand separators: NOT accepted in v1
        "1,000,000",      # ... with commas either
        "2^100000",       # exponent guard
        "2^(1/2)",        # non-integer exponent
        "",               # empty
        "   ",
        "1 if 2 else 3",
        "True",
        "(1,2)",          # tuple-ish: comma between digits -> "1.2)"? no: parses as 1.2 — see below
    ]

    def test_parse_errors(self):
        for text in self.BAD:
            if text == "(1,2)":
                continue  # documented: becomes "(1.2)" = 1.2, tolerated
            with self.subTest(text=text):
                with self.assertRaises(mg.ParseError):
                    mg.parse_expr(text)

    def test_tuple_comma_tolerated(self):
        # Documented limitation: "(1,2)" normalizes to "(1.2)" and reads 1.2.
        self.assertEqual(mg.parse_expr("(1,2)").value, Fraction(6, 5))

    def test_single_group_dot_is_decimal(self):
        # Documented limitation: "1.000" is the decimal 1.0, not 1000.
        self.assertEqual(mg.parse_expr("1.000").value, 1)


class TestParseForms(unittest.TestCase):
    """Canonical FORM strings: sorted commutative operands, decimals as
    fractions, written divisions kept unreduced."""

    FORMS = [
        ("1/4 + 3/8", "1/4 + 3/8"),
        ("3/8 + 1/4", "1/4 + 3/8"),          # commutative -> same form
        ("2/8 + 3/8", "2/8 + 3/8"),          # written division NOT reduced
        ("0,75", "3/4"),                     # decimal constant -> exact fraction
        (".75", "3/4"),
        ("5 - 3", "5 - 3"),
        ("-(1+2)", "-(1 + 2)"),
        ("2*(3+1)", "(1 + 3) * 2"),          # operands sorted lexicographically
        ("3 * 1/2", "1 * 3 / 2"),           # left-assoc: (3*1)/2, structure kept
        ("2^3", "2^3"),
        ("1 1/2", "1 + 1/2"),
        ("6 ÷ 2", "6/2"),                   # written fraction atom, unreduced
        ("(2/3)^2", "(2/3)^2"),
        ("-3", "-3"),
        ("1/2 * 3", "1/2 * 3"),
    ]

    def test_forms(self):
        for text, want in self.FORMS:
            with self.subTest(text=text):
                self.assertEqual(mg.parse_expr(text).form, want)

    def test_value_and_form_independent(self):
        p = mg.parse_expr("2/8 + 3/8")
        self.assertEqual(p.value, Fraction(5, 8))
        self.assertEqual(p.form, "2/8 + 3/8")


class TestGradeSingle(unittest.TestCase):
    def test_correct(self):
        cases = [
            ("3/4", "0,75"),
            ("3/4", ".75"),
            ("7/4", "1 1/2 + 1/4"),
            ("8", "2^3"),
            ("3", "6 ÷ 2"),
            (Fraction(3, 4), "3/4"),   # expected as a Fraction
            (12, "12"),               # expected as an int
        ]
        for exp, got in cases:
            with self.subTest(expected=exp, given=got):
                v = mg.grade_single(exp, got)
                self.assertEqual(v["verdict"], "correct")
                self.assertEqual(v["score"], 10)

    def test_correct_via_also_accept(self):
        v = mg.grade_single("5/8", "1/4 + 3/8", also_accept=["1/4 + 3/8"])
        self.assertEqual(v["verdict"], "correct")
        # value already equals expected, accept not even needed:
        v = mg.grade_single("5/8", "1/4 + 3/8")
        self.assertEqual(v["verdict"], "correct")
        v = mg.grade_single("0.5", "1/2", also_accept=["50/100"])
        self.assertEqual(v["verdict"], "correct")

    def test_near_digit_slips(self):
        for exp, got in [("324", "342"),      # transposition
                         ("324", "3240"),     # extra digit
                         ("324", "32"),       # missing digit
                         ("12", "21"),        # length 2 IS >= 2 -> near
                         ("0,75", "0,57"),    # decimal slip
                         ("324", "325")]:     # substitution
            with self.subTest(expected=exp, given=got):
                v = mg.grade_single(exp, got)
                self.assertEqual(v["verdict"], "near")
                self.assertEqual(v["score"], 7)

    def test_not_near(self):
        for exp, got in [("324", "432"),      # two edits
                         ("3/4", "4/3"),      # fractions are not plain numbers
                         ("5", "50"),         # digit string length < 2
                         ("324", "-324"),     # sign flip: same digits -> wrong
                         ("324", "2340")]:    # two edits
            with self.subTest(expected=exp, given=got):
                v = mg.grade_single(exp, got)
                self.assertEqual(v["verdict"], "wrong")
                self.assertEqual(v["score"], 3)

    def test_also_accept_is_correct_not_near(self):
        # Given equals a different also_accept exactly -> correct, never near.
        v = mg.grade_single("324", "425", also_accept=["425"])
        self.assertEqual(v["verdict"], "correct")
        # Near is computed against the expected answer only:
        v = mg.grade_single("324", "234", also_accept=["999"])
        self.assertEqual(v["verdict"], "near")

    def test_empty(self):
        for got in ["", "   ", "?", "no ho sé", "NO SÉ", "ns", "no sé", "no ho sé."]:
            with self.subTest(given=got):
                v = mg.grade_single("3/4", got)
                self.assertEqual(v["verdict"], "empty")
                self.assertEqual(v["score"], 0)

    def test_wrong_parse_error_is_wrong(self):
        for got in ["abc", "3 + ", "1/0"]:
            with self.subTest(given=got):
                v = mg.grade_single("3/4", got)
                self.assertEqual(v["verdict"], "wrong")
                self.assertEqual(v["score"], 3)

    def test_wrong_value(self):
        v = mg.grade_single("3/4", "4/5")
        self.assertEqual(v["verdict"], "wrong")

    def test_units(self):
        cases = [
            # (expected, given, verdict, score)
            ("12 cm", "12 cm", "correct", 10),
            ("12 cm", "12cm", "correct", 10),
            ("12 m", "12 metres", "correct", 10),      # alias table
            ("12 m", "12 METRES", "correct", 10),      # case-insensitive
            ("12 cm", "12", "near", 7),                # unit missing
            ("12 cm", "12 m", "near", 7),              # unit wrong
            ("12 cm", "13 cm", "near", 7),             # digit slip (12->13) + right unit
            ("12 cm", "13", "near", 7),                # digit slip, unit missing
            ("12 cm", "130 cm", "wrong", 3),           # two edits: not near
            ("12", "12 cm", "correct", 10),            # extra unit tolerated
        ]
        for exp, got, verdict, score in cases:
            with self.subTest(expected=exp, given=got):
                v = mg.grade_single(exp, got)
                self.assertEqual(v["verdict"], verdict)
                self.assertEqual(v["score"], score)

    def test_unit_param(self):
        v = mg.grade_single(12, "12", unit="cm")
        self.assertEqual(v["verdict"], "near")   # value right, unit missing
        self.assertFalse(v["unit_ok"])
        v = mg.grade_single(12, "12 cm", unit="cm")
        self.assertEqual(v["verdict"], "correct")

    def test_near_with_unit(self):
        v = mg.grade_single("324 cm", "342 cm")
        self.assertEqual(v["verdict"], "near")

    def test_verdict_shape(self):
        v = mg.grade_single("3/4", "0,75")
        for key in ("score", "verdict", "note", "expected", "got"):
            self.assertIn(key, v)
        self.assertEqual(v["expected"], "3/4")
        self.assertEqual(v["got"], "3/4")


class TestGradeStep(unittest.TestCase):
    def test_form_expected_matches_right_side(self):
        v = mg.grade_step("2/8 + 3/8", "1/4+3/8 = 2/8+3/8")
        self.assertEqual(v["verdict"], "correct")
        self.assertIn("right", v["matched_sides"])
        self.assertNotIn("left", v["matched_sides"])  # left is a different form

    def test_value_only_expected_matches_value(self):
        v = mg.grade_step("5/8", "1/4+3/8 = 5/8")
        self.assertEqual(v["verdict"], "correct")
        self.assertIn("right", v["matched_sides"])

    def test_value_expected_matches_both_sides(self):
        v = mg.grade_step("5/8", "1/4 + 3/8 = 5/8")
        self.assertEqual(v["verdict"], "correct")
        self.assertEqual(sorted(v["matched_sides"]), ["left", "right"])

    def test_bare_line(self):
        v = mg.grade_step("5/8", "1/4 + 3/8")
        self.assertEqual(v["verdict"], "correct")
        self.assertEqual(v["matched_sides"], ["line"])

    def test_form_expected_rejects_value_only_line(self):
        v = mg.grade_step("2/8 + 3/8", "5/8")
        self.assertEqual(v["verdict"], "wrong")
        self.assertEqual(v["score"], 3)

    def test_strict_form_rejects_value_only_line(self):
        v = mg.grade_step("5/8", "1/4 + 3/8", strict_form=True)
        self.assertEqual(v["verdict"], "wrong")

    def test_strict_form_accepts_matching_form(self):
        v = mg.grade_step("5/8", "1/4 + 3/8", strict_form=True)
        self.assertEqual(v["verdict"], "wrong")
        v = mg.grade_step("1/4 + 3/8", "3/8 + 1/4", strict_form=True)
        self.assertEqual(v["verdict"], "correct")

    def test_mixed_number_expected_is_a_value(self):
        v = mg.grade_step("1 1/2", "3/2")
        self.assertEqual(v["verdict"], "correct")

    def test_two_equals_is_parse_error(self):
        with self.assertRaises(mg.ParseError):
            mg.grade_step("5/8", "a = b = c")

    def test_unparseable_side_is_parse_error(self):
        with self.assertRaises(mg.ParseError):
            mg.grade_step("5/8", "1/4 + = 5/8")

    def test_empty_line(self):
        v = mg.grade_step("5/8", "")
        self.assertEqual(v["verdict"], "empty")
        self.assertEqual(v["score"], 0)

    def test_sides_detail(self):
        v = mg.grade_step("5/8", "1/4+3/8 = 5/8")
        self.assertEqual(v["sides"]["left"]["value"], "5/8")
        self.assertEqual(v["sides"]["right"]["form"], "5/8")


class TestCLI(unittest.TestCase):
    SCRIPT = REPO / "hooks" / "mathgrade.py"

    def run_cli(self, *args):
        r = subprocess.run([sys.executable, str(self.SCRIPT), *args],
                           capture_output=True, text=True)
        return r

    def test_eval(self):
        r = self.run_cli("eval", "1 1/2 + 1/4")
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        self.assertEqual(out["value"], "7/4")

    def test_grade(self):
        r = self.run_cli("grade", "3/4", "0,75")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["score"], 10)

    def test_grade_near(self):
        r = self.run_cli("grade", "324", "342")
        self.assertEqual(json.loads(r.stdout)["verdict"], "near")

    def test_step(self):
        r = self.run_cli("step", "2/8 + 3/8", "1/4+3/8 = 2/8+3/8")
        out = json.loads(r.stdout)
        self.assertEqual(out["verdict"], "correct")
        self.assertIn("right", out["matched_sides"])

    def test_eval_error(self):
        r = self.run_cli("eval", "1/0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("division by zero", json.loads(r.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
