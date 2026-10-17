#!/usr/bin/env python3
"""ENCARREC-LANG-L2-BANC: the two new English bank types, `order` and `transform`.

  * `order` — the learner puts the given `words` in order; graded as a whole
    sentence (capitals and final punctuation do not count, the order does).
  * `transform` — the learner rewrites a `sentence` (negative, question, a tense);
    graded as `correct`, contractions and long forms are the same words.

Pinned here: the grader's rules on both types, the content of the 13 competence
files (6 order + 6 transform each, validated, no duplicate answer), and that the
level test does not serve a transform item (its question has no instruction slot).
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
import curriculum as cu  # noqa: E402

TODAY = "2026-10-17"
BANK = REPO / "curriculum" / "bank"
NEW_TYPES = ("order", "transform")
NEW_COMPETENCES = {
    "en-A1": ["a1.verb_to_be", "a1.present_simple", "a1.question_words", "a1.have_got",
              "a1.can_ability", "a1.there_is_are"],
    "en-A2": ["a2.present_simple_vs_continuous", "a2.past_simple", "a2.past_continuous",
              "a2.comparatives_superlatives", "a2.modals_ability_obligation",
              "a2.future_going_to_will", "a2.present_perfect_experience"],
}


def _file(stem: str, cid: str) -> list[dict]:
    return json.loads((BANK / stem / f"{cid}.json").read_text(encoding="utf-8"))


def _new_items(stem: str, cid: str) -> list[dict]:
    return [it for it in _file(stem, cid) if it["type"] in NEW_TYPES]


def _order(answer: str, words: list[str]) -> dict:
    return {"id": "t.order.001", "competence": "t.c", "type": "order", "instruction": "Put the words in order.",
            "words": words, "context": "", "answer": answer, "also_accept": [], "options": [],
            "why": "x", "status": "validated"}


def _transform(sentence: str, answer: str, also: list[str] | None = None) -> dict:
    return {"id": "t.transform.001", "competence": "t.c", "type": "transform",
            "instruction": "Make it negative.", "sentence": sentence, "context": "",
            "answer": answer, "also_accept": also or [], "options": [], "why": "x", "status": "validated"}


class OrderGrading(unittest.TestCase):
    def setUp(self):
        self.item = _order("Where do you live?", ["you", "where", "live", "do"])

    def test_the_right_order_scores_ten(self):
        self.assertEqual(bank_mod.grade(self.item, "Where do you live?")["score"], 10)

    def test_capitals_and_final_punctuation_do_not_count(self):
        for ans in ("where do you live", "WHERE DO YOU LIVE", "Where do you live", "where do you live."):
            self.assertEqual(bank_mod.grade(self.item, ans)["score"], 10, ans)

    def test_the_wrong_order_is_wrong(self):
        r = bank_mod.grade(self.item, "Where you do live?")
        self.assertEqual(r["verdict"], "wrong")
        self.assertEqual(r["score"], 3)
        self.assertEqual(r["correct_version"], "Where do you live?")

    def test_a_missing_or_extra_word_is_wrong(self):
        self.assertEqual(bank_mod.grade(self.item, "Where do you")["verdict"], "wrong")
        self.assertEqual(bank_mod.grade(self.item, "Where do you live now?")["verdict"], "wrong")

    def test_one_letter_slip_in_a_long_word_is_almost(self):
        item = _order("It will be sunny tomorrow.", ["tomorrow", "sunny", "be", "will", "it"])
        r = bank_mod.grade(item, "It will be sunny tomorow.")
        self.assertEqual(r["verdict"], "typo")
        self.assertEqual(r["score"], 7)

    def test_an_empty_answer_is_not_right_and_does_not_crash(self):
        # As for `correct` (the same branch): nothing written is wrong, with the answer shown.
        r = bank_mod.grade(self.item, "")
        self.assertLess(r["score"], 8)
        self.assertEqual(r["correct_version"], "Where do you live?")

    def test_the_whole_sentence_is_the_correct_version(self):
        self.assertEqual(bank_mod._full_sentence(self.item), "Where do you live?")


class TransformGrading(unittest.TestCase):
    def test_a_contraction_and_its_long_form_are_the_same(self):
        item = _transform("She plays tennis.", "She doesn't play tennis.", ["She does not play tennis."])
        for ans in ("She doesn't play tennis.", "She does not play tennis.", "she doesn't play tennis"):
            self.assertEqual(bank_mod.grade(item, ans)["score"], 10, ans)

    def test_each_contraction_is_accepted_for_its_long_form(self):
        pairs = [("I don't like it.", "I do not like it."), ("He doesn't work.", "He does not work."),
                 ("It isn't cold.", "It is not cold."), ("We aren't here.", "We are not here."),
                 ("They didn't go.", "They did not go."), ("I can't swim.", "I cannot swim."),
                 ("I can't swim.", "I can not swim."), ("I won't go.", "I will not go."),
                 ("He couldn't run.", "He could not run."), ("You mustn't smoke.", "You must not smoke.")]
        for short, long_ in pairs:
            self.assertEqual(bank_mod.grade(_transform("x", short), long_)["score"], 10, (short, long_))
            self.assertEqual(bank_mod.grade(_transform("x", long_), short)["score"], 10, (short, long_))

    def test_a_wrong_form_is_wrong_not_almost(self):
        item = _transform("She plays tennis.", "She doesn't play tennis.", ["She does not play tennis."])
        self.assertEqual(bank_mod.grade(item, "She don't play tennis.")["verdict"], "wrong")
        self.assertEqual(bank_mod.grade(item, "She doesn't plays tennis.")["verdict"], "wrong")

    def test_the_correct_version_is_the_whole_sentence(self):
        item = _transform("She plays tennis.", "She doesn't play tennis.")
        self.assertEqual(bank_mod.grade(item, "")["correct_version"], "She doesn't play tennis.")


class ItemValidation(unittest.TestCase):
    def test_an_order_whose_words_are_not_the_answers_is_refused(self):
        bad = _order("Where do you live?", ["you", "where", "live", "go"])
        self.assertTrue(bank_mod.item_problems(bad))

    def test_an_order_with_the_right_words_is_fine(self):
        self.assertEqual(bank_mod.item_problems(_order("I am a student.", ["a", "student", "am", "I"])), [])

    def test_a_transform_needs_a_sentence_and_an_instruction(self):
        item = _transform("", "x")
        self.assertTrue(bank_mod.item_problems(item))

    def test_other_types_are_not_checked_here(self):
        self.assertEqual(bank_mod.item_problems({"type": "complete"}), [])


class NewContent(unittest.TestCase):
    def test_every_competence_has_six_order_and_six_transform(self):
        for stem, cids in NEW_COMPETENCES.items():
            for cid in cids:
                items = _new_items(stem, cid)
                kinds = [it["type"] for it in items]
                self.assertEqual(kinds.count("order"), 6, cid)
                self.assertEqual(kinds.count("transform"), 6, cid)

    def test_no_other_competence_has_the_new_types(self):
        for f in sorted(BANK.glob("*/*.json")):
            stem, cid = f.parent.name, f.stem
            if cid in NEW_COMPETENCES.get(stem, []):
                continue
            self.assertFalse([it for it in _file(stem, cid) if it["type"] in NEW_TYPES], f.name)

    def test_every_new_item_is_valid_and_served(self):
        for stem, cids in NEW_COMPETENCES.items():
            for cid in cids:
                for it in _new_items(stem, cid):
                    self.assertEqual(bank_mod.item_problems(it), [], it["id"])
                    self.assertEqual(it["status"], "validated", it["id"])
                    self.assertTrue(it["why"].strip(), it["id"])
                    self.assertEqual(it["source"], "claude · 2026-10-17", it["id"])
                    if it["type"] == "order":
                        self.assertNotIn("sentence", it, it["id"])

    def test_new_ids_continue_the_file_and_are_unique(self):
        for stem, cids in NEW_COMPETENCES.items():
            for cid in cids:
                items = _file(stem, cid)
                ids = [it["id"] for it in items]
                self.assertEqual(len(ids), len(set(ids)), cid)
                nums = [int(i.rsplit(".", 1)[1]) for i in ids if i.startswith(cid + ".")]
                self.assertEqual(sorted(nums), list(range(1, len(nums) + 1)), cid)

    def test_no_new_answer_repeats_another_item_of_its_competence(self):
        # Only the new items are checked: the older files already share single
        # words ("is" is the answer of several complete items).
        for stem, cids in NEW_COMPETENCES.items():
            for cid in cids:
                items = _file(stem, cid)
                for new in (it for it in items if it["type"] in NEW_TYPES):
                    key = bank_mod.canon(new["answer"])
                    clash = [it["id"] for it in items
                             if it is not new and bank_mod.canon(it["answer"]) == key]
                    self.assertEqual(clash, [], f"{new['id']} repeats an answer")

    def test_every_valid_answer_of_a_new_item_scores_ten(self):
        for stem, cids in NEW_COMPETENCES.items():
            for cid in cids:
                for it in _new_items(stem, cid):
                    for a in [it["answer"], *it.get("also_accept", [])]:
                        self.assertEqual(bank_mod.grade(it, a)["score"], 10, (it["id"], a))


class LevelTestAndGo(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="test-order-transform-"))
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_the_level_test_does_not_serve_order_or_transform(self):
        for stem, cids in NEW_COMPETENCES.items():
            for cid in cids:
                items = cu._bank_checkpoint_items(REPO, stem, cid, self.d, TODAY, set())
                self.assertFalse([c for c in items if c["bank"]["type"] in NEW_TYPES], cid)

    def test_go_counts_the_new_items_as_unseen(self):
        left = bank_mod.bank_left(REPO, "en-A1", self.d)
        self.assertEqual(left["a1.verb_to_be"]["total"], 52)
        left2 = bank_mod.bank_left(REPO, "en-A2", self.d)
        self.assertEqual(left2["a2.past_simple"]["total"], 74)

    def test_go_serves_a_new_item_and_grades_it(self):
        # Answering right walks the unseen items in file order; the new ones
        # come after the 40 older items of the competence.
        served = set()
        for _ in range(60):
            item = bank_mod.pick_item(REPO, "en-A1", "a1.verb_to_be", self.d, TODAY)
            if item["type"] in NEW_TYPES:
                served.add(item["type"])
                r = bank_mod.answer_and_record(REPO, "en-A1", item["id"], "a1.verb_to_be", item["answer"],
                                               self.d, TODAY)
                self.assertEqual(r["score"], 10, item["id"])
            if served == set(NEW_TYPES):
                break
            bank_mod.answer_and_record(REPO, "en-A1", item["id"], "a1.verb_to_be", item["answer"], self.d, TODAY)
        self.assertEqual(served, set(NEW_TYPES))


if __name__ == "__main__":
    unittest.main()
