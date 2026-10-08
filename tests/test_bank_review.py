#!/usr/bin/env python3
"""🎓 Review on the bank (PLA-EXERCICIS-TANCATS.md, fase 4) — and the bank's grader.

Review stops asking the model to invent an exercise per queue item. Each
exercise is a bank item: a failed bank item first, then an old error pattern of
the queue placed SAFELY in a competence (Albert, 2026-09-24: option C), then a
weak competence. Old patterns that cannot be placed safely are retired.
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

CUR = cu.load_curriculum(REPO / "curriculum" / "en-A1.md")
TODAY = "2026-09-24"


def pattern(cat, wrong, right):
    return {"category": cat, "frequency": 1, "mastery_level": 0,
            "examples": [{"incorrect": wrong, "correct": right}]}


class SafePlacement(unittest.TestCase):
    """Option C: only the placements that are not a guess."""

    def place(self, item_id, pat=None, content=""):
        return cu.legacy_competence(CUR, item_id, {"content": content}, pat)

    def test_a_category_with_one_competence_is_safe(self):
        cid, how, safe = self.place("tenses_go", pattern("tenses", "I goes", "I go"))
        self.assertEqual(("a1.present_simple", True), (cid, safe), how)

    def test_an_exclusive_tag_word_is_safe(self):
        cid, _, safe = self.place("agreement_has_got", pattern("agreement", "She have got", "She has got"))
        self.assertEqual(("a1.have_got", True), (cid, safe))

    def test_a_tag_word_two_competences_share_is_a_guess(self):
        # "don't" is an imperatives tag AND a present simple one (measured on nes-en)
        cid, how, safe = self.place("word_order_don't_like", pattern("word_order", "I not like", "I don't like"))
        self.assertFalse(safe, (cid, how))

    def test_a_category_the_curriculum_does_not_have_is_retired(self):
        _, how, safe = self.place("spelling_is_raining", pattern("spelling", "is rainning", "is raining"))
        self.assertFalse(safe)
        self.assertEqual("category-not-in-curriculum", how)

    def test_a_word_outside_every_list_is_retired(self):
        _, _, safe = self.place("vocabulary_umbrella", pattern("vocabulary", "umbrela", "umbrella"), "umbrella")
        self.assertFalse(safe)


class ReviewPick(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="test-review-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        (self.d / ".records").mkdir()
        bank_id = bank_mod.load_bank(REPO, "en-A1", "a1.can_ability")[0]["id"]
        self.bank_id = bank_id
        sr = {"items": {
            bank_id: {"content": "can", "due_date": "2026-09-20"},
            "tenses_go": {"content": "I go", "due_date": "2026-09-21"},
            "spelling_is_raining": {"content": "is raining", "due_date": "2026-09-19"},
            "tenses_later": {"content": "x", "due_date": "2026-12-01"},
        }}
        (self.d / "spaced-repetition.json").write_text(json.dumps(sr), encoding="utf-8")
        (self.d / "mistakes-db.json").write_text(json.dumps({"error_patterns": {
            "tenses_go": pattern("tenses", "I goes", "I go"),
            "spelling_is_raining": pattern("spelling", "is rainning", "is raining"),
        }}), encoding="utf-8")

    def pick(self, used=(), dry=False):
        return cu.review_pick(REPO, CUR, "en-A1", self.d, TODAY, list(used), None, dry)

    def sr(self):
        return json.loads((self.d / "spaced-repetition.json").read_text(encoding="utf-8"))["items"]

    def test_the_order_retire_then_bank_item_then_old_pattern_then_weak(self):
        first = self.pick()
        # the oldest due item cannot be placed: it is retired on the way
        self.assertEqual(["spelling_is_raining"], [r["id"] for r in first["retired"]])
        self.assertEqual(("bank", self.bank_id), (first["source"], first["queue_id"]))
        self.assertEqual(self.bank_id, first["item"]["id"])
        second = self.pick([self.bank_id])
        self.assertEqual(("legacy", "tenses_go", "a1.present_simple"),
                         (second["source"], second["queue_id"], second["competence"]))
        self.assertEqual("a1.present_simple", second["item"]["competence"])
        third = self.pick([self.bank_id, "tenses_go"])
        self.assertEqual("weak", third["source"])        # nothing due left: a competence, still a bank item
        self.assertIsNone(third["queue_id"])
        self.assertTrue(third["available"])

    def test_retiring_keeps_the_history_and_a_due_date_that_never_comes(self):
        self.pick()
        it = self.sr()["spelling_is_raining"]
        self.assertEqual(cu.RETIRED_DUE, it["due_date"])
        self.assertEqual("category-not-in-curriculum", it["retired"]["reason"])
        self.assertEqual("2026-09-19", it["retired"]["was_due"])
        self.assertEqual("is raining", it["content"])
        self.assertEqual("2026-12-01", self.sr()["tenses_later"]["due_date"])   # not due: untouched

    def test_a_dry_run_writes_nothing(self):
        before = (self.d / "spaced-repetition.json").read_text(encoding="utf-8")
        out = self.pick(dry=True)
        self.assertTrue(out["retired"])
        self.assertEqual(before, (self.d / "spaced-repetition.json").read_text(encoding="utf-8"))


class Grader(unittest.TestCase):
    """bank.grade had no tests of its own."""

    item = {"id": "x.1", "competence": "a1.vocab_colors_adjectives", "type": "complete",
            "sentence": "Ten plus ten is ___.", "answer": "twenty", "also_accept": [], "options": [], "why": "10 + 10"}

    def test_right_almost_and_wrong(self):
        self.assertEqual(10, bank_mod.grade(self.item, "twenty")["score"])
        self.assertEqual(10, bank_mod.grade(self.item, "Ten plus ten is twenty.")["score"])   # whole sentence
        self.assertEqual(7, bank_mod.grade(self.item, "twnety")["score"])                     # swapped letters: OSA 1
        self.assertEqual(3, bank_mod.grade(self.item, "thirty")["score"])
        self.assertEqual(0, bank_mod.grade(self.item, "")["score"])

    def test_another_word_of_the_lesson_is_not_a_typo(self):
        item = {**self.item, "sentence": "I have ___ cats.", "answer": "three", "options": ["three", "there"]}
        self.assertEqual(3, bank_mod.grade(item, "there")["score"])


class NearMisses(unittest.TestCase):
    """«gairebé» is a slip of the finger — never the grammar the exercise is about."""

    fix = {"id": "c.1", "type": "correct", "sentence": "She can to speak English.",
           "answer": "She can speak English.", "also_accept": [], "options": [], "why": "can + verb"}
    gap = {"id": "g.1", "competence": "a1.present_simple", "type": "complete",
           "sentence": "He ___ (play) football every day.", "answer": "plays", "also_accept": [], "options": [],
           "why": "he + -s"}

    def test_one_slip_in_a_corrected_sentence_is_almost(self):
        self.assertEqual(7, bank_mod.grade(self.fix, "She can speak Englsih.")["score"])

    def test_but_the_wrong_form_is_wrong_not_almost(self):
        self.assertEqual(3, bank_mod.grade(self.fix, "She can speaks English.")["score"])
        self.assertEqual(3, bank_mod.grade(self.gap, "play")["score"])          # the present simple mistake itself
        self.assertEqual(7, bank_mod.grade(self.gap, "plyas")["score"])         # a slip

    def test_inflection(self):
        for a, b in (("play", "plays"), ("watch", "watches"), ("like", "liked"), ("make", "making"),
                     ("study", "studies"), ("have", "has")):
            self.assertTrue(bank_mod._is_inflection(a, b), (a, b))
        self.assertFalse(bank_mod._is_inflection("twnety", "twenty"))


class LevelTestFromTheBank(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="test-checkpoint-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        (self.d / ".records").mkdir()

    def test_it_draws_reviewed_bank_items_not_the_three_checks(self):
        out = cu.checkpoint_start(self.d, CUR, TODAY, force=True, stem="en-A1", root=REPO)
        self.assertTrue(out["ok"], out)
        run = json.loads(cu.run_file(self.d).read_text(encoding="utf-8"))
        self.assertTrue(all(it.get("bank") for it in run["items"]))
        self.assertEqual(len(run["items"]), len({(i["cid"], i["prompt"]) for i in run["items"]}))
        checks = {k["prompt"] for c in CUR["competencies"] for k in c["checks"]}
        self.assertFalse([i for i in run["items"] if i["prompt"] in checks])

    def test_a_right_answer_passes_and_a_wrong_one_does_not(self):
        cu.checkpoint_start(self.d, CUR, TODAY, force=True, stem="en-A1", root=REPO)
        run = json.loads(cu.run_file(self.d).read_text(encoding="utf-8"))
        first = run["items"][0]["bank"]
        r = cu.checkpoint_answer(self.d, CUR, TODAY, first["answer"], root=REPO)
        self.assertTrue(r["correct"], r)
        r = cu.checkpoint_answer(self.d, CUR, TODAY, "zzz", root=REPO)
        self.assertFalse(r["correct"])

    def test_without_a_bank_it_is_the_checks_as_before(self):
        out = cu.checkpoint_start(self.d, CUR, TODAY, force=True)
        self.assertTrue(out["ok"])
        run = json.loads(cu.run_file(self.d).read_text(encoding="utf-8"))
        self.assertFalse(any(it.get("bank") for it in run["items"]))


class BankLeft(unittest.TestCase):
    def test_unseen_goes_down_as_she_practises(self):
        d = Path(tempfile.mkdtemp(prefix="test-left-"))
        self.addCleanup(shutil.rmtree, d, True)
        before = bank_mod.bank_left(REPO, "en-A1", d)["a1.can_ability"]
        self.assertEqual(before["unseen"], before["total"])
        item = bank_mod.pick_item(REPO, "en-A1", "a1.can_ability", d, TODAY)
        bank_mod.answer_and_record(REPO, "en-A1", item["id"], "a1.can_ability", item["answer"], d, TODAY)
        self.assertEqual(before["unseen"] - 1, bank_mod.bank_left(REPO, "en-A1", d)["a1.can_ability"]["unseen"])


class TheWholeBank(unittest.TestCase):
    """Every valid answer of every item scores 10 — exact, as the whole sentence, in capitals.

    Found 2026-09-24: extract_gap() stripped the raw length of the text after
    the gap whenever its canon() matched, and canon(".") is "" — so for
    "Ten plus ten is ___." the exact answer "twenty" became "twent", 7/10.
    """

    def test_no_right_answer_is_marked_down(self):
        bad = []
        for f in sorted((REPO / "curriculum" / "bank").glob("*/*.json")):
            for it in json.loads(f.read_text(encoding="utf-8")):
                valid = [it["answer"], *it.get("also_accept", [])]
                # _full_sentence fills the "___" of a LANGUAGE sentence; math
                # items (compute/choose/compare) carry a `problem` instead and
                # their answer IS the full correct version (WP1.3).
                if it["type"] in ("complete", "choose") and "sentence" in it:
                    valid += [bank_mod._full_sentence(it), it["answer"].upper()]
                bad += [(it["id"], a) for a in valid if bank_mod.grade(it, a)["score"] != 10]
        self.assertEqual([], bad[:10], f"{len(bad)} valid answers not graded 10")


if __name__ == "__main__":
    unittest.main()
