"""Cada execució d'un --repeat deixa la seva transcripció.

Abans escrivien totes al mateix fitxer i només quedava l'última: el text real
del tutor a les execucions que fallaven es perdia abans de poder-lo llegir.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("fluent_e2e", REPO / "scripts" / "flowed-e2e.py")
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)


class NumberedPathTest(unittest.TestCase):
    def test_number_goes_before_the_extension(self):
        self.assertEqual(e2e.numbered_path("/r/base/transcript-wander.md", 3),
                         "/r/base/transcript-wander.3.md")

    def test_every_run_gets_a_different_file(self):
        paths = {e2e.numbered_path("/r/t.md", n) for n in range(1, 7)}
        self.assertEqual(len(paths), 6)

    def test_no_extension_still_works(self):
        self.assertEqual(e2e.numbered_path("/r/t", 2), "/r/t.2")


class UngradedRunTest(unittest.TestCase):
    def test_a_run_with_no_score_at_all_is_ungraded(self):
        rows = [(True, "el tutor obre la sessió", ""), (False, "posa nota", "0/8")]
        self.assertTrue(e2e.is_ungraded(rows))

    def test_a_run_that_missed_one_score_is_not(self):
        self.assertFalse(e2e.is_ungraded([(False, "posa nota", "7/8")]))

    def test_a_clean_run_is_not(self):
        self.assertFalse(e2e.is_ungraded([(True, "posa nota", "8/8")]))


class RepeatsThatMatterTest(unittest.TestCase):
    """Un exercici que es torna a mostrar sense haver-lo contestat no és cap
    repetició; un de contestat, només compta com a fallada dins la mateixa
    pràctica (el servidor permet que una paraula surti a dues pràctiques)."""

    def test_unanswered_exercise_shown_again_is_fine(self):
        # 0 menú, 1 lliçó A (contestada al 2?) — no: al 2 ella respon A; al 3 surt B
        # Aquí: A a la lliçó (1), ella va a Vocabulary (2) i li tornen A sense haver-la contestat.
        asked = [[], ["a"], ["a"]]
        practice = ["-", "lesson", "vocab"]
        r = e2e.classify_repeats(asked, practice, set())
        self.assertEqual(r["same"], [])
        self.assertEqual(r["cross"], [])
        self.assertEqual(r["unanswered"], [(2, "a")])

    def test_answered_then_asked_again_in_the_same_practice_is_a_loop(self):
        asked = [[], ["a"], ["a"]]
        practice = ["-", "lesson", "lesson"]
        r = e2e.classify_repeats(asked, practice, {2})
        self.assertEqual(r["same"], [(2, "a")])

    def test_answered_in_the_lesson_and_asked_in_vocabulary_is_reported_not_failed(self):
        asked = [[], ["a"], ["b"], ["a"]]
        practice = ["-", "lesson", "lesson", "vocab"]
        r = e2e.classify_repeats(asked, practice, {2})
        self.assertEqual(r["same"], [])
        self.assertEqual(r["cross"], [(3, "a")])

    def test_fresh_means_not_answered_yet(self):
        asked = [[], ["a"], ["a"], ["b"]]
        practice = ["-", "lesson", "lesson", "lesson"]
        r = e2e.classify_repeats(asked, practice, {2, 3})
        self.assertEqual(r["fresh"][2], [])      # la mateixa pregunta un altre cop
        self.assertEqual(r["fresh"][3], ["b"])   # una de nova

    def test_a_button_press_is_not_an_answer(self):
        asked = [[], ["a"], ["a"]]
        practice = ["-", "lesson", "vocab"]
        r = e2e.classify_repeats(asked, practice, set())   # cap resposta
        self.assertEqual(r["fresh"][2], ["a"])


class TemplateBracesTest(unittest.TestCase):
    def test_the_review_results_block_is_not_on_screen(self):
        text = 'Bé!\n\n```fluent:review_results\n[{"item_id": "x", "quality": 1}]\n```\n'
        self.assertFalse(e2e.BRACE.search(e2e.on_screen(text)))

    def test_a_real_leaked_placeholder_still_is(self):
        self.assertTrue(e2e.BRACE.search(e2e.on_screen("## Review 1/6 — {Target}: {the word}")))


class StudentScenarioTest(unittest.TestCase):
    """L'alumne que sap algunes respostes: només val si sap de quin ítem parla."""

    def setUp(self):
        import json, tempfile
        self.dir = Path(tempfile.mkdtemp(prefix="e2e-student-"))
        self.addCleanup(__import__("shutil").rmtree, self.dir, True)
        self.notes = self.dir / "notes.jsonl"
        self.sr = self.dir / "sr.json"
        self.sr.write_text(json.dumps({"items": {
            "vocabulary_morning": {"content": "matí", "answer": "morning"},
            "agreement_she_goes": {"content": "She goes to school", "answer": "She goes to school",
                                   "learner_wrote": "She go to school"}}}))
        self.json = json

    def write_notes(self, *rows):
        self.notes.write_text("\n".join(self.json.dumps(r) for r in rows) + "\n")

    def test_the_item_on_screen_is_the_last_one_assigned_to_this_session(self):
        self.write_notes(
            {"session": "s1", "assigned": {"id": "vocabulary_morning", "content": "matí"}},
            {"session": "other", "assigned": {"id": "agreement_she_goes", "content": "x"}},
        )
        got = e2e.onscreen_item(self.notes, self.sr, "s1")
        self.assertEqual(got["id"], "vocabulary_morning")
        self.assertEqual(got["answer"], "morning")

    def test_no_notes_means_no_item(self):
        self.assertIsNone(e2e.onscreen_item(self.notes, self.sr, "s1"))

    def test_nothing_assigned_means_no_item(self):
        self.write_notes({"session": "s1", "assigned": None})
        self.assertIsNone(e2e.onscreen_item(self.notes, self.sr, "s1"))

    def test_right_is_the_answer_and_wrong_is_the_learners_own_slip(self):
        item = {"id": "a", "content": "She goes to school", "answer": "She goes to school",
                "learner_wrote": "She go to school"}
        self.assertEqual(e2e.student_answer("right", item), "She goes to school")
        self.assertEqual(e2e.student_answer("wrong", item), "She go to school")

    def test_a_vocabulary_item_has_no_slip_so_the_decoy_is_used(self):
        item = {"id": "v", "content": "matí", "answer": "morning", "learner_wrote": ""}
        self.assertEqual(e2e.student_answer("wrong", item), e2e.DECOY)

    def test_the_decoy_is_never_the_items_own_answer(self):
        # days 083631: on the card for «taula» the decoy «table» is the answer.
        item = {"id": "vocabulary_table", "content": "taula", "answer": "table", "learner_wrote": ""}
        self.assertNotEqual(e2e.student_answer("wrong", item).lower(), "table")
        self.assertEqual(e2e.student_answer("right", item), "table")

    def test_without_an_item_it_says_it_does_not_know(self):
        self.assertEqual(e2e.student_answer("right", None), "no ho sé")

    def test_the_exercise_is_what_follows_the_last_heading(self):
        reply = "❌ Close! goes.\n\n## Review 2/6\n\n**Exercise:**\n\"I ___ apples\""
        self.assertTrue(e2e.exercise_tail(reply).startswith("## Review 2/6"))
        self.assertNotIn("Close", e2e.exercise_tail(reply))

    def test_an_exercise_built_from_the_item_follows_it(self):
        item = {"content": "She goes to school", "answer": "She goes to school"}
        reply = "## Review 1/6\n\n**Exercise:**\nComplete: \"She ___ to school every day.\""
        self.assertTrue(e2e.follows_item(item, reply))

    def test_a_vocabulary_exercise_can_use_either_language(self):
        item = {"content": "matí", "answer": "morning"}
        self.assertTrue(e2e.follows_item(item, '## Review\n\n**Exercise:**\nEnglish for "matí"?'))
        self.assertTrue(e2e.follows_item(item, '## Review\n\n**Exercise:**\nGood ___ (morning)'))

    def test_an_exercise_about_something_else_does_not(self):
        item = {"content": "She goes to school", "answer": "She goes to school"}
        self.assertFalse(e2e.follows_item(item, '## Review\n\n**Exercise:**\nThe cat sleeps.'))

    def test_feedback_words_do_not_count_as_the_exercise(self):
        item = {"content": "She goes to school", "answer": "She goes to school"}
        reply = "❌ She goes to school is right.\n\n## Review 2/6\n\n**Exercise:**\nThe cat sleeps."
        self.assertFalse(e2e.follows_item(item, reply))


if __name__ == "__main__":
    unittest.main()


class JourneyScenarioTest(unittest.TestCase):
    """La lliçó i, després, pràctica lliure: cal saber de quina paraula parla l'exercici."""

    def test_the_bank_word_is_found_in_the_exercise_on_screen(self):
        reply = ('## Exercise 1: Vocabulary (Easy)\n\n**Word (Catalan):** "matí"\n\n'
                 '**Question:** What is the English word for "matí"?\n\n**Type your answer:**')
        item = e2e.bank_item(reply)
        self.assertEqual((item["content"], item["answer"]), ("matí", "morning"))
        self.assertIsNone(item["id"])

    def test_feedback_above_the_exercise_does_not_confuse_it(self):
        reply = ('Correct! "matí" is morning.\n\n**Score: 10/10** ✅\n\n'
                 '## Exercise 2\n\n**Question:** What is the English word for "finestra"?')
        self.assertEqual(e2e.bank_item(reply)["answer"], "window")

    def test_a_word_outside_the_bank_is_left_out(self):
        self.assertIsNone(e2e.bank_item('## Exercise\n**Question:** What is "xocolata" in English?'))

    def test_right_is_the_answer_and_wrong_is_another_real_word(self):
        item = {"id": None, "content": "matí", "answer": "morning", "learner_wrote": ""}
        self.assertEqual(e2e.free_vocab_answer("right", item), "morning")
        wrong = e2e.free_vocab_answer("wrong", item)
        self.assertNotEqual(wrong, "morning")
        self.assertIn(wrong, [en for en, _ in e2e.vocab_bank()])
        self.assertEqual(e2e.free_vocab_answer("right", None), "no ho sé")

    def test_the_scenario_exists_in_the_cli_and_the_bench(self):
        src = (REPO / "scripts" / "flowed-e2e.py").read_text()
        bench = "\n".join(l for l in (REPO / "scripts" / "flowed-bench.sh").read_text().splitlines()
                          if not l.lstrip().startswith("#"))
        self.assertIn('"journey"', src)
        self.assertIn("--journey", bench)

    def test_the_closing_replies_are_not_counted_as_insisting(self):
        src = (REPO / "scripts" / "flowed-e2e.py").read_text()
        self.assertIn("closed_early_at <= i < resume_at", src)

    def test_the_bank_knows_the_words_the_tutor_picks_on_its_own(self):
        for ca in ("beure", "dia", "plat", "cotxe", "telefon"):
            item = e2e.bank_item(f'## Word 1/10\n**Català:** {ca}\n**Què vol dir en català?**')
            self.assertIsNotNone(item, ca)

    def test_writing_and_unanswered_words_are_not_read_as_insisting_or_repeating(self):
        src = (REPO / "scripts" / "flowed-e2e.py").read_text()
        self.assertIn("if i in writing_replies:", src)
        self.assertIn("for i in answer_idx if phase[\"vocab_a\"][0] <= i < phase[\"vocab_a\"][1]", src)


class KnownOnlyRepeatsTest(unittest.TestCase):
    """El servidor només refusa el que s'ha contestat bé: la resta pot tornar."""

    def test_a_wrong_answer_may_come_back_without_being_a_repeat(self):
        asked = [["casa"], ["llibre"], ["casa"]]
        practice = ["v", "v", "v"]
        # answer at 1 (to "casa") was wrong, so "casa" at 2 is allowed
        rc = e2e.classify_repeats(asked, practice, {1, 2}, known={2})
        self.assertEqual(rc["same"], [])

    def test_a_right_answer_may_not(self):
        asked = [["casa"], ["llibre"], ["casa"]]
        rc = e2e.classify_repeats(asked, ["v", "v", "v"], {1, 2}, known={1, 2})
        self.assertEqual(rc["same"], [(2, "casa")])

    def test_without_known_every_answer_counts_as_before(self):
        asked = [["casa"], ["llibre"], ["casa"]]
        rc = e2e.classify_repeats(asked, ["v", "v", "v"], {1, 2})
        self.assertEqual(rc["same"], [(2, "casa")])

    def test_a_wrong_answer_is_still_not_a_fresh_question(self):
        # so "the same question three times in a row" is still seen
        asked = [["casa"], ["casa"], ["casa"]]
        rc = e2e.classify_repeats(asked, ["v", "v", "v"], {1, 2}, known=set())
        self.assertEqual(rc["fresh"][1:], [[], []])

    def test_a_context_word_does_not_hijack_the_card(self):
        card = ('## Word 3/10\n**Català:** capitalització\n**Context:** Els dies de la setmana '
                'han de tenir majúscula.\n**Què vol dir en català?**')
        self.assertIsNone(e2e.bank_item(card))

    def test_the_headword_line_wins_over_the_context(self):
        card = ('## Word 3/10\n**Català:** aigua\n**Context:** La setmana passada vaig beure aigua.\n')
        self.assertEqual(e2e.bank_item(card)["answer"], "water")


class DaysScenarioTest(unittest.TestCase):
    """The judge of the multi-day scenario: SM-2 as update-db.py does it."""

    def test_sm2_intervals_grow_one_six_then_by_ease(self):
        st = {"repetitions": 0, "interval_days": 1, "easiness_factor": 2.5}
        self.assertEqual(e2e.sm2_after(st, 5), (1, 1))
        self.assertEqual(e2e.sm2_after({**st, "repetitions": 1}, 4), (2, 6))
        self.assertEqual(e2e.sm2_after({**st, "repetitions": 2, "interval_days": 6}, 4), (3, 15))

    def test_a_miss_resets(self):
        self.assertEqual(e2e.sm2_after({"repetitions": 3, "interval_days": 16}, 1), (0, 1))

    def test_sm2_matches_the_hook(self):
        import importlib.util as u
        spec = u.spec_from_file_location("upd", REPO / "hooks" / "update-db.py")
        upd = u.module_from_spec(spec)
        spec.loader.exec_module(upd)
        for reps, interval, ef in ((0, 1, 2.5), (1, 1, 2.5), (2, 6, 2.36), (4, 16, 1.3)):
            for q in range(6):
                st = {"repetitions": reps, "interval_days": interval, "easiness_factor": ef}
                r = upd.calculate_sm2(st, q)
                self.assertEqual(e2e.sm2_after(st, q), (r["repetitions"], r["interval_days"]))

    def test_quality_is_score_over_two_and_the_last_record_wins(self):
        recs = [{"item_id": "a", "score": 3}, {"item_id": "a", "score": 9},
                {"item_id": "b", "score": 10, "sm2_quality": 4}, {"score": 7}]
        self.assertEqual(e2e.record_qualities(recs), {"a": 4, "b": 4})

    def test_each_item_learns_after_its_own_number_of_sightings(self):
        ns = {e2e.learns_after(f"item_{i}") for i in range(30)}
        self.assertEqual(ns, {0, 1, 2})

    def _day(self, **over):
        sr0 = {"a": {"repetitions": 0, "interval_days": 1, "easiness_factor": 2.5, "due_date": "2026-09-20"},
               "b": {"repetitions": 1, "interval_days": 1, "easiness_factor": 2.5, "due_date": "2026-09-20"},
               "c": {"repetitions": 2, "interval_days": 6, "easiness_factor": 2.5, "due_date": "2026-09-25"}}
        sr1 = {"a": {"repetitions": 0, "interval_days": 1, "easiness_factor": 2.3, "due_date": "2026-09-21"},
               "b": {"repetitions": 2, "interval_days": 6, "easiness_factor": 2.6, "due_date": "2026-09-26"},
               "c": sr0["c"]}
        kw = dict(day=2, today="2026-09-20", tomorrow="2026-09-21", due0=["a", "b"], sr0=sr0, sr1=sr1,
                  total=2, limit=20, assigned=["a", "b"], answered=["a", "b"], quality={"a": 1, "b": 5})
        kw.update(over)
        return e2e.judge_day(**kw)

    def test_a_correct_day_passes_everything(self):
        rows = self._day()
        self.assertEqual([r for r in rows if not r[0]], [])

    def test_an_item_that_was_not_due_coming_back_is_caught(self):
        bad = [r for r in self._day(assigned=["a", "b", "c"]) if not r[0]]
        self.assertEqual([r[1] for r in bad], ["dia 2: no torna cap ítem que no tocava"])

    def test_a_lesson_of_the_wrong_size_is_caught(self):
        bad = [r for r in self._day(total=3) if not r[0]]
        self.assertTrue(any("mida" in r[1] for r in bad))

    def test_an_empty_queue_gives_the_minimum(self):
        rows = e2e.judge_day(1, "2026-09-20", "2026-09-21", [], {}, {}, 3, 20, [], [], {})
        self.assertTrue(all(r[0] for r in rows), rows)

    def test_a_pending_item_that_never_showed_is_caught(self):
        bad = [r for r in self._day(answered=["a"], total=2) if not r[0]]
        self.assertTrue(any("tot el pendent" in r[1] for r in bad))

    def test_a_missed_item_that_does_not_come_back_tomorrow_is_caught(self):
        sr1_bad = {"a": {"repetitions": 0, "interval_days": 6, "due_date": "2026-09-26"}}
        day = self._day()
        rows = e2e.judge_day(2, "2026-09-20", "2026-09-21", ["a"], {"a": {"repetitions": 0, "interval_days": 1}},
                             sr1_bad, 1, 20, ["a"], ["a"], {"a": 1})
        self.assertTrue(any(not r[0] and "torna demà" in r[1] for r in rows))
        self.assertTrue(all(r[0] for r in day))

    def test_a_known_item_answered_right_that_stays_close_is_caught(self):
        sr0 = {"b": {"repetitions": 2, "interval_days": 6, "easiness_factor": 2.5}}
        sr1 = {"b": {"repetitions": 3, "interval_days": 1, "due_date": "2026-09-21"}}
        rows = e2e.judge_day(3, "2026-09-20", "2026-09-21", ["b"], sr0, sr1, 1, 20, ["b"], ["b"], {"b": 5})
        self.assertTrue(any(not r[0] and "s'allunya" in r[1] for r in rows))

    def test_an_unanswered_due_item_must_not_be_touched(self):
        sr0 = {"a": {"repetitions": 0, "due_date": "2026-09-20"}}
        sr1 = {"a": {"repetitions": 0, "due_date": "2026-09-21"}}
        rows = e2e.judge_day(2, "2026-09-20", "2026-09-21", ["a"], sr0, sr1, 1, 20, ["a"], [], {})
        self.assertTrue(any(not r[0] and "no es toca" in r[1] for r in rows))

    def test_carry_between_days(self):
        ok = e2e.judge_carry(2, ["a"], ["b"], ["a", "c"], 5, ["a", "c"])
        self.assertTrue(all(r[0] for r in ok))
        bad = e2e.judge_carry(2, ["a"], ["b"], ["b"], 5, ["a", "b"])
        self.assertEqual(sorted(r[1] for r in bad if not r[0]),
                         ["dia 2: el que va encertar ahir (i ja sabia) no torna avui",
                          "dia 2: el que va fallar ahir torna avui"])

    def test_a_wrong_word_counted_as_remembered_is_caught(self):
        sr0 = {"a": {"repetitions": 0, "interval_days": 1, "easiness_factor": 2.5}}
        sr1 = {"a": {"repetitions": 1, "interval_days": 1, "due_date": "2026-09-21"}}
        rows = e2e.judge_day(1, "2026-09-20", "2026-09-21", ["a"], sr0, sr1, 1, 20, ["a"], ["a"],
                             {"a": 3}, decoys={"a"})
        self.assertTrue(any(not r[0] and "equivocada" in r[1] for r in rows))
        ok = e2e.judge_day(1, "2026-09-20", "2026-09-21", ["a"], sr0, sr1, 1, 20, ["a"], ["a"],
                           {"a": 3}, decoys=set())
        self.assertFalse(any("equivocada" in r[1] for r in ok))

    def test_the_scenario_is_wired_in(self):
        src = (REPO / "scripts" / "flowed-e2e.py").read_text(encoding="utf-8")
        self.assertIn('if args.scenario == "days":', src)
        self.assertIn('"days", "noisy"', src)
        self.assertIn("--days", (REPO / "scripts" / "flowed-bench.sh").read_text(encoding="utf-8"))


class NoisyAnswersTest(unittest.TestCase):
    """The untidy learner: what she types, and which class it belongs to."""
    VOC = {"id": "vocabulary_house", "answer": "house", "content": "casa"}
    SENT = {"id": "agreement_she_goes_to_school", "answer": "She goes to school",
            "content": "She go to school", "learner_wrote": "She go to school"}
    SPELL = {"id": "spelling_because", "answer": "because", "content": "becouse"}

    def test_every_variant_of_the_plan_is_known(self):
        for v in e2e.NOISY_PLAN:
            text, cls = e2e.noisy_answer(v, self.SENT)
            self.assertTrue(text.strip(), v)
            self.assertIn(cls, {"right", "typo", "wrong", "partial", "catalan", "question"})

    def test_the_plan_has_all_classes(self):
        classes = {e2e.noisy_answer(v, self.VOC)[1] for v in e2e.NOISY_PLAN}
        self.assertEqual(classes, {"right", "typo", "wrong", "partial", "catalan", "question"})

    def test_dressed_up_right_answers_still_contain_the_answer(self):
        for v in ("dot", "sentence", "long", "upper", "noaccents"):
            text, cls = e2e.noisy_answer(v, self.SENT)
            self.assertEqual(cls, "right", v)
            self.assertIn("she goes to school", e2e._fold_text(text), v)

    def test_a_vocabulary_word_in_capitals(self):
        self.assertEqual(e2e.noisy_answer("upper", self.VOC), ("HOUSE", "right"))

    def test_a_typo_is_one_letter_off_not_the_answer(self):
        text, cls = e2e.noisy_answer("typo", self.VOC)
        self.assertEqual(cls, "typo")
        self.assertNotEqual(text, "house")
        self.assertEqual(len(text), len("house") - 1)

    def test_a_typo_in_a_sentence_swaps_two_letters(self):
        text, cls = e2e.noisy_answer("typo", self.SENT)
        self.assertEqual(cls, "typo")
        self.assertNotEqual(text, "She goes to school")
        self.assertEqual(sorted(text), sorted("She goes to school"))

    def test_a_spelling_item_never_gets_a_typo_that_would_be_the_exercise(self):
        text, cls = e2e.noisy_answer("typo", self.SPELL)
        self.assertEqual(cls, "right")
        self.assertIn("because", text)

    def test_partial_is_half_a_sentence_or_nothing(self):
        self.assertEqual(e2e.noisy_answer("partial", self.SENT), ("She goes", "partial"))
        self.assertEqual(e2e.noisy_answer("partial", self.VOC), ("no ho sé", "partial"))

    def test_catalan_answer_is_the_catalan_word(self):
        self.assertEqual(e2e.noisy_answer("catalan", self.VOC), ("casa", "catalan"))

    def test_a_catalan_answer_to_a_grammar_item_is_not_the_english_sentence(self):
        text, cls = e2e.noisy_answer("catalan", self.SENT)
        self.assertEqual(cls, "catalan")
        self.assertNotIn("goes to school", text.lower())
        self.assertNotIn("go to school", text.lower())

    def test_the_long_one_is_long(self):
        self.assertGreater(len(e2e.noisy_answer("long", self.VOC)[0]), 250)

    def test_without_an_item_it_is_a_plain_dont_know(self):
        self.assertEqual(e2e.noisy_answer("dot", None), ("no ho sé", "wrong"))

    def test_the_scenario_is_wired_in(self):
        src = (REPO / "scripts" / "flowed-e2e.py").read_text(encoding="utf-8")
        self.assertIn('"noisy")', src)
        self.assertIn("una errada d'una lletra és una errada petita", src)
        self.assertIn("--noisy", (REPO / "scripts" / "flowed-bench.sh").read_text(encoding="utf-8"))


class TopicsScenarioTest(unittest.TestCase):
    def test_a_topical_exercise_is_recognised(self):
        self.assertTrue(e2e.mentions_topic("Write 4 sentences about what you have already eaten."))
        self.assertTrue(e2e.mentions_topic("You are at a restaurant. Order a meal."))
        self.assertFalse(e2e.mentions_topic("Describe your bedroom in 4 sentences."))

    def test_the_leak_of_the_note_is_recognised(self):
        self.assertTrue(e2e.LEAK.search("The learner's teacher wants these topics practised: x"))
        self.assertFalse(e2e.LEAK.search("Great job! Here is your next exercise."))

    def test_wired_in(self):
        self.assertIn("--topics", (REPO / "scripts" / "flowed-bench.sh").read_text(encoding="utf-8"))
        self.assertIn('run_topics(args, cli, prof_dir, rep, quiet)',
                      (REPO / "scripts" / "flowed-e2e.py").read_text(encoding="utf-8"))
