#!/usr/bin/env python3
"""Pure helpers of scripts/flowed-mathbench.py (WP3.4).

The bench itself runs live against the server — it cannot go in unittest.
What is checked here is the measurement machinery around it: the arithmetic
the seeded learner needs to fit its answer to the real task, the band judge
against the WP3.1 rubric (10 / 8-9 / 5-7 / 0-4), the task-shape mirror of the
WP3.3/WP3.2 guards, and the error classes of bench/learner-math.md.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("mathbench", REPO / "scripts" / "flowed-mathbench.py")
mb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mb)


class TestArithmetic(unittest.TestCase):
    def test_two_term_worked_line(self):
        w = mb.parse_worked("Calcula 12 + 7 = 19")
        self.assertIsNotNone(w)
        self.assertFalse(w["tri"])
        self.assertEqual(w["true"], 19)
        self.assertEqual(w["shown"], 19)

    def test_precedence_claim(self):
        # the classic Raonament task: the shown result obeys left-to-right
        w = mb.parse_worked("per què 3 + 2 × 4 no és 20?")
        self.assertIsNotNone(w)
        self.assertTrue(w["tri"])
        self.assertEqual(w["true"], 11)
        self.assertEqual(w["shown"], 20)
        self.assertEqual(w["ltr"], 20)
        self.assertEqual(w["step1"], "2 × 4 = 8")
        self.assertEqual(w["step2"], "3 + 8 = 11")

    def test_precedence_first_pair(self):
        w = mb.parse_worked("Mira 3 × 4 + 2 = 14. És correcte?")
        self.assertIsNotNone(w)
        self.assertEqual(w["true"], 14)
        self.assertEqual(w["step1"], "3 × 4 = 12")

    def test_three_term_without_claim_is_not_worked(self):
        self.assertIsNone(mb.parse_worked("inventa un problema amb 3 + 2 × 4"))

    def test_bare_expr_skips_three_term_prefix(self):
        self.assertIsNone(mb.parse_bare_expr("per què 3 + 2 × 4 no és 20?"))
        self.assertEqual(mb.parse_bare_expr("explica com fas 24 + 7 de cap"), (24.0, "+", 7.0))

    def test_bare_expr_skips_ranges(self):
        self.assertIsNone(mb.parse_bare_expr("escriu 3-5 frases"))

    def test_bare_expr_skips_fractions_in_prose(self):
        # "3/4 d'un pastís" is a fraction in the statement, not the operation
        self.assertIsNone(mb.parse_bare_expr("si tens 3/4 d'un pastís i en comparteixes 1/8"))


class TestBandJudge(unittest.TestCase):
    def test_bare_answer_must_land_0_4(self):
        self.assertEqual(mb.judge_band("bare", 3), "ok")
        self.assertEqual(mb.judge_band("bare", 0), "ok")
        self.assertEqual(mb.judge_band("bare", 5), "fail")
        self.assertEqual(mb.judge_band("bare", 10), "fail")

    def test_calc_slip_expects_5_7_strict_0_4_is_soft(self):
        self.assertEqual(mb.judge_band("calc-slip", 6), "ok")
        self.assertEqual(mb.judge_band("calc-slip", 2), "soft")  # result wrong → defensible
        self.assertEqual(mb.judge_band("calc-slip", 9), "fail")  # missed the slip

    def test_wrong_operation_expects_0_4(self):
        self.assertEqual(mb.judge_band("wrong-op", 3), "ok")
        self.assertEqual(mb.judge_band("wrong-op", 6), "fail")

    def test_correct_expects_8_10(self):
        self.assertEqual(mb.judge_band("correct", 10), "ok")
        self.assertEqual(mb.judge_band("correct", 8), "ok")
        self.assertEqual(mb.judge_band("correct", 6), "soft")
        self.assertEqual(mb.judge_band("correct", 2), "fail")

    def test_no_score_no_verdict(self):
        self.assertIsNone(mb.judge_band("bare", None))


class TestAnswerGenerator(unittest.TestCase):
    def test_bare_answer_has_no_reasoning(self):
        ans, seed = mb.make_answer("Explica com resols 24 + 7 de cap.", "bare", "math-writing")
        self.assertEqual(seed, "bare")
        self.assertIn("31", ans)
        self.assertNotIn("per què", ans.lower())

    def test_slip_answer_shows_work_with_one_slip(self):
        ans, seed = mb.make_answer("Explica com resols 24 + 7 de cap.", "slip", "math-writing")
        self.assertEqual(seed, "calc-slip")
        self.assertIn("24 + 7", ans)
        self.assertIn("38", ans)  # 31 + 7 — the seeded slip
        self.assertIn("per què", ans.lower())

    def test_correct_answer_on_precedence_claim(self):
        ans, seed = mb.make_answer("per què 3 + 2 × 4 no és 20?", "correct", "math-writing")
        self.assertEqual(seed, "correct")
        self.assertIn("2 × 4 = 8", ans)
        self.assertIn("11", ans)

    def test_multi_step_shown_solution_is_replayed(self):
        task = ('**Task:** has escrit: "3 × 6 = 18, 18 − 4 = 14". '
                "Explica com ho has resolt i per què funciona.")
        bare, s1 = mb.make_answer(task, "bare", "math-writing")
        self.assertEqual((s1, "El resultat és 14." in bare), ("bare", True))
        slip, s2 = mb.make_answer(task, "slip", "math-writing")
        self.assertEqual(s2, "calc-slip")
        self.assertIn("3 × 6 = 18", slip)
        self.assertIn("18 − 4 = 21", slip)  # the seeded slip on the last step
        good, s3 = mb.make_answer(task, "correct", "math-writing")
        self.assertEqual(s3, "correct")
        self.assertIn("3 × 6 = 18", good)
        self.assertIn("18 − 4 = 14", good)
        self.assertIn("per què", good.lower())

    def test_task_half_ignores_feedback_replies(self):
        grade = ('❌ "8 + 48 = 56" → **"48 ÷ 6 = 8"** (wrong_operation — repartir)\n'
                 "**Correct version:**\n\"Operació: 48 ÷ 6 = 8.\"\n\n**Score: 4/10**")
        self.assertIsNone(mb.task_half(grade, "math-reading"))
        nxt = grade + "\n\n## Problema 2\n\n**Enunciat:** La Marta té 12 pomes.\n"
        self.assertIn("Problema 2", mb.task_half(nxt, "math-reading"))

    def test_error_analysis_classes(self):
        task = "Troba l'error: 12 + 7 = 29. Explica'l."
        bare, s1 = mb.make_answer(task, "bare", "math-writing")
        self.assertEqual((s1, bare), ("bare", "Està malament."))
        good, s3 = mb.make_answer(task, "correct", "math-writing")
        self.assertEqual(s3, "correct")
        self.assertIn("19", good)

    def test_word_problem_bare_is_a_bare_number(self):
        task = ("**Enunciat:** En Marc reparteix 42 caramels igualment entre 7 amics. "
                "Quants en toquen a cada amic?")
        ans, seed = mb.make_answer(task, "bare", "math-reading")
        self.assertEqual(seed, "bare")
        self.assertIn("6", ans)
        self.assertNotIn("Operació", ans)

    def test_word_problem_slip_with_confident_op_seeds_wrong_operation(self):
        task = ("**Enunciat:** En Marc reparteix 42 caramels igualment entre 7 amics. "
                "Quants en toquen a cada amic?")
        ans, seed = mb.make_answer(task, "slip", "math-reading")
        self.assertEqual(seed, "wrong-op")
        self.assertIn("42 + 7", ans)

    def test_word_problem_equal_groups_is_multiplication(self):
        # "repartir" alone is not division: groups of equal size → ×
        task = ("**Enunciat:** En un joc de taula, cada jugador rep 5 fitxes. "
                "Si hi ha 8 jugadors, quants de fitxes es repartiran en total?")
        ans, seed = mb.make_answer(task, "correct", "math-reading")
        self.assertEqual(seed, "correct")
        self.assertIn("5 × 8 = 40", ans)

    def test_word_problem_rate_is_multiplication(self):
        task = ("**Enunciat:** Un cotxe consumeix 8 litres de combustible per cada 100 km. "
                "Si el cotxe fa un viatge de 300 km, quants litres de combustible "
                "necessitarà?")
        ans, seed = mb.make_answer(task, "correct", "math-reading")
        self.assertEqual(seed, "correct")
        self.assertIn("300 ÷ 100 = 3", ans)
        self.assertIn("8 × 3 = 24", ans)

    def test_word_problem_double_is_multiplication(self):
        task = "**Enunciat:** Marta té 10 anys. El seu germà té el doble d'edat que ella."
        ans, seed = mb.make_answer(task, "correct", "math-reading")
        self.assertEqual(seed, "correct")
        self.assertIn("10 × 2 = 20", ans)

    def test_fraction_task_with_implied_operation_seeds_generic(self):
        task = ("Si tens 3/4 d'un pastís i en comparteixes 1/8 amb un amic, quina fracció "
                "del pastís quedarà? Explica com ho has resolt i per què funciona.")
        _ans, seed = mb.make_answer(task, "correct", "math-writing")
        self.assertEqual(seed, "generic")
        self.assertIsNone(mb.judge_band("generic", 4))

    def test_word_problem_correct_shows_operation_and_why(self):
        task = ("**Enunciat:** En Marc reparteix 42 caramels igualment entre 7 amics. "
                "Quants en toquen a cada amic?")
        ans, seed = mb.make_answer(task, "correct", "math-reading")
        self.assertEqual(seed, "correct")
        self.assertIn("42 ÷ 7 = 6", ans)
        self.assertIn("repartir", ans)


class TestTaskShape(unittest.TestCase):
    def test_reasoning_task_with_justification_passes(self):
        ok, _ = mb.task_shape("## 📝 Raonament\n**Task:** explica com ho has resolt i per què funciona.",
                              "math-writing")
        self.assertTrue(ok)

    def test_reasoning_bare_list_fails(self):
        ok, why = mb.task_shape("## Raonament\n**Task:** fes una llista de nombres parells.", "math-writing")
        self.assertFalse(ok)
        self.assertEqual(why, "bare list")

    def test_reasoning_result_only_fails(self):
        ok, why = mb.task_shape("## Raonament\n**Task:** calcula 12 + 7.", "math-writing")
        self.assertFalse(ok)
        self.assertEqual(why, "no justification cue")

    def test_problem_pure_arithmetic_enunciat_fails(self):
        ok, why = mb.task_shape("**Enunciat:** 24 ÷ 6\nEscriu les operacions.", "math-reading")
        self.assertFalse(ok)
        self.assertEqual(why, "Enunciat is pure arithmetic")

    def test_problem_without_work_demand_fails(self):
        ok, why = mb.task_shape("**Enunciat:** La Marta té 12 pomes i en compra 7 més. Quantes en té?",
                                "math-reading")
        self.assertFalse(ok)
        self.assertEqual(why, "work not demanded")

    def test_problem_story_with_work_passes(self):
        ok, _ = mb.task_shape(
            "**Enunciat:** La Marta té 12 pomes i en compra 7 més. Quantes en té?\n"
            "Escriu les operacions, una per línia, i el resultat.", "math-reading")
        self.assertTrue(ok)


class TestCategoriesAndKinds(unittest.TestCase):
    def test_categories_read_off_arrow_lines(self):
        text = ('- 🔴 "42 + 7 = 56" → **"42 ÷ 7 = 6"** (wrong_operation — repartir és dividir)\n'
                '- 🟢 "56" → **"6"** (calculation — suma mal feta)')
        self.assertEqual(mb.categories_of(text), ["wrong_operation", "calculation"])

    def test_language_category_is_detected_as_not_math(self):
        cats = mb.categories_of('- 🟡 "vaig anar" → **"vaig anar"** (grammar — temps verbal)')
        self.assertEqual(cats, ["grammar"])
        self.assertNotIn(mb.normalize_error_category("grammar"), mb.ERROR_CATEGORIES)

    def test_surface_spelling_normalizes_to_a_math_class(self):
        cats = mb.categories_of('- 🟡 "24 + 7 = 21" → **"31"** (transport — faltava la unitat)')
        self.assertEqual(cats, ["transport"])
        self.assertTrue(mb.category_is_math("transport"))

    def test_invented_category_fails_the_taxonomy_gate(self):
        # "justification" is a rubric DIMENSION, not one of the 12 categories;
        # the server would silently fold it into "calculation"
        self.assertFalse(mb.category_is_math("justification"))
        self.assertTrue(mb.category_is_math("wrong_operation"))
        self.assertFalse(mb.category_is_math("grammar"))

    def test_kind_classification(self):
        self.assertEqual(mb.classify_kind("Troba l'error i explica'l"), "error-analysis")
        self.assertEqual(mb.classify_kind("Quina estratègia és més fàcil?"), "compare-strategies")
        self.assertEqual(mb.classify_kind("Explica com ho has resolt"), "explain")


if __name__ == "__main__":
    unittest.main()
