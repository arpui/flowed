#!/usr/bin/env python3
"""The night batch that looks for things the learner said about herself.

Nothing here reaches the tutor — that is a separate, later decision — so what
these checks protect is the extraction itself, and above all the two properties
that decide whether the idea is usable at all:

  * **Abstention.** Most turns are exercise answers. "I have a dog" written as a
    translation is not a fact about her, and a model eager to be useful will
    file it anyway.
  * **The quote is real.** Each candidate carries the sentence she actually
    wrote. An invented quote makes review worthless, so it is verified against
    the source text and dropped if it is not there.

The model itself is not called here: these exercise the plumbing around it.
"""
import importlib.util
import json
import sqlite3
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "fluent_memories", REPO_ROOT / "scripts" / "flowed-memories.py")
mem = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mem)


class AgreementTest(unittest.TestCase):
    """Two models, and only what both say. Free precision when nobody waits."""

    def test_one_model_alone_is_taken_at_its_word(self):
        self.assertEqual(mem.agree([{"fact": "has a dog"}])["fact"], "has a dog")

    def test_both_must_find_something(self):
        self.assertIsNone(mem.agree([{"fact": "has a dog"}, {"fact": None}]))
        self.assertIsNone(mem.agree([{"fact": None}, {"fact": None}]))

    def test_a_failed_call_blocks_the_fact(self):
        # A model that errored is not a model that agreed.
        self.assertIsNone(mem.agree([{"fact": "has a dog"}, None]))

    def test_agreement_survives_different_wording(self):
        got = mem.agree([{"fact": "has a dog called Rex"},
                         {"fact": "has a dog named Rex"}])
        self.assertIsNotNone(got)

    def test_two_different_facts_are_not_agreement(self):
        self.assertIsNone(mem.agree([{"fact": "has a dog called Rex"},
                                     {"fact": "plays the piano on Tuesdays"}]))

    def test_empty_input_does_not_throw(self):
        self.assertIsNone(mem.agree([]))


class TurnExtractionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.profile = Path(self.tmp.name) / "demo-en"
        (self.profile / "sessions").mkdir(parents=True)
        self.db = self.profile / "sessions" / "sessions.db"
        self.now = int(time.time() * 1000)
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE message (id text PRIMARY KEY, session_id text, "
                     "time_created integer, time_updated integer, data text)")
        conn.execute("CREATE TABLE part (id text PRIMARY KEY, message_id text, "
                     "session_id text, time_created integer, time_updated integer, data text)")
        conn.commit()
        conn.close()
        self.n = 0

    def add(self, role: str, text: str, ago_ms: int = 0):
        self.n += 1
        mid, ts = f"m{self.n}", self.now - ago_ms
        conn = sqlite3.connect(self.db)
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     (mid, "ses_1", ts, ts, json.dumps({"role": role})))
        conn.execute("INSERT INTO part VALUES (?,?,?,?,?,?)",
                     (f"p{self.n}", mid, "ses_1", ts, ts,
                      json.dumps({"type": "text", "text": text})))
        conn.commit()
        conn.close()

    def turns(self, since_days: float = 1):
        return mem.learner_turns(self.db, self.now - int(since_days * 86400_000))

    def test_the_exercise_travels_with_the_answer(self):
        # Without it there is no way to tell a confidence from a translation.
        self.add("assistant", "Translate into English: Tinc un gos.")
        self.add("user", "I have a dog at home")
        t = self.turns()
        self.assertEqual(len(t), 1)
        self.assertIn("Translate into English", t[0]["exercise"])
        self.assertEqual(t[0]["answer"], "I have a dog at home")

    def test_commands_are_not_turns(self):
        # A button press arrives as user text carrying the whole expanded prompt.
        self.add("user", "/fluent-learn " + "x" * 300)
        self.assertEqual(self.turns(), [])

    def test_one_word_answers_are_skipped(self):
        self.add("assistant", "What is the English word for poma?")
        self.add("user", "apple")
        self.assertEqual(self.turns(), [])

    def test_a_long_paste_is_skipped(self):
        self.add("user", "y" * 900)
        self.assertEqual(self.turns(), [])

    def test_older_turns_are_outside_the_window(self):
        self.add("user", "I have a dog at home", ago_ms=5 * 86400_000)
        self.assertEqual(self.turns(since_days=1), [])
        self.assertEqual(len(self.turns(since_days=10)), 1)

    def test_a_missing_database_is_not_an_error(self):
        self.assertEqual(mem.learner_turns(self.profile / "nope.db", 0), [])

    def test_the_tutor_is_never_a_turn(self):
        self.add("assistant", "Here is a long and interesting exercise for you.")
        self.assertEqual(self.turns(), [])


class NormaliseTest(unittest.TestCase):
    def test_case_and_punctuation_do_not_matter(self):
        self.assertEqual(mem.normalise("Has a Dog, called Rex!"),
                         mem.normalise("has a dog called rex"))

    def test_empty_is_empty(self):
        self.assertEqual(mem.normalise(None), "")


if __name__ == "__main__":
    unittest.main()
