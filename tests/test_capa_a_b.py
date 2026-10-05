#!/usr/bin/env python3
"""Capa A + Capa B on the same session must ADD UP, never cancel out.

update-db.py is idempotent per session_id: it restores the session's pre-state
(T0) and re-applies the payload. So a second layer that omits a field silently
DELETES what the first layer wrote for that session. That is what happened:
persist-session.py emitted "error_patterns", update-db.py only ever reads
"errors", and closing a session (or the 30-min sweeper) wiped the session's
error patterns and their spaced-repetition items.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / "hooks"
TEMPLATES = REPO_ROOT / "data-examples"

FEEDBACK = (
    '❌ Almost!\n\n**Corrections:**\n'
    '- 🔴 "21" → **"31"** (carrying — the carried 1 was dropped)\n\n'
    '**Correct version:**\n"24 + 7 = 31"\n\n'
    '**Score: 5/10** 🟡\n'
)


class CapaABTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="math-capa-"))
        for name in ("learner-profile", "mastery-db", "mistakes-db", "progress-db",
                     "session-log", "spaced-repetition"):
            shutil.copy(TEMPLATES / f"{name}-template.json", self.dir / f"{name}.json")
        profile = json.loads((self.dir / "learner-profile.json").read_text(encoding="utf-8"))
        profile.setdefault("learner", {})["name"] = "Test"
        (self.dir / "learner-profile.json").write_text(
            json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
        self._make_session_db()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _make_session_db(self):
        db_path = self.dir / "sessions" / "sessions.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(db_path)
        db.executescript("""
            CREATE TABLE session (id text PRIMARY KEY, project_id text, slug text,
              directory text, title text, version text, agent text, model text,
              time_created integer, time_updated integer, last_activity integer,
              metadata text);
            CREATE TABLE message (id text PRIMARY KEY, session_id text,
              time_created integer, time_updated integer, data text);
            CREATE TABLE part (id text PRIMARY KEY, message_id text, session_id text,
              time_created integer, time_updated integer, data text);
        """)
        now = int(time.time() * 1000)
        db.execute(
            "INSERT INTO session VALUES ('ses_T','global','math','','Fluent',"
            "'0.0.0-local','learner','deep',?,?,?,NULL)", (now - 600000, now, now))

        def msg(mid, role, text):
            db.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                       (mid, "ses_T", now, now, json.dumps({"role": role})))
            db.execute("INSERT INTO part VALUES (?,?,?,?,?,?)",
                       (mid + "_p", mid, "ses_T", now, now,
                        json.dumps({"type": "text", "text": text})))

        msg("m1", "user", '{"learner": {"name": "Test"}, "computed": {"next_session_id": "session-001"}}')
        msg("m2", "user", "24 + 7 = 21")
        msg("m3", "assistant", FEEDBACK)
        db.commit()
        db.close()

    def _run(self, script, *args):
        env = {**os.environ, "FLOWED_DATA_DIR": str(self.dir)}
        proc = subprocess.run([sys.executable, str(HOOKS / script), *args],
                              capture_output=True, text=True, env=env, cwd=REPO_ROOT)
        self.assertEqual(proc.returncode, 0, f"{script} failed: {proc.stderr}")
        return proc

    def _state(self):
        mistakes = json.loads((self.dir / "mistakes-db.json").read_text(encoding="utf-8"))
        sr = json.loads((self.dir / "spaced-repetition.json").read_text(encoding="utf-8"))
        return set(mistakes.get("error_patterns", {})), set(sr.get("items", {}))

    def test_capa_b_keeps_what_capa_a_recorded(self):
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        patterns_a, items_a = self._state()
        self.assertIn("carrying_31", patterns_a, "Capa A did not record the error pattern")
        self.assertIn("carrying_31", items_a, "Capa A did not queue the pattern for review")

        self._run("persist-session.py", "ses_T", "--dir", str(self.dir))
        patterns_b, items_b = self._state()
        self.assertIn("carrying_31", patterns_b, "Capa B erased the error pattern Capa A had recorded")
        self.assertIn("carrying_31", items_b, "Capa B erased the spaced-repetition item")
        self.assertEqual(patterns_a, patterns_b)
        self.assertEqual(items_a, items_b)

    # --- review block: the only input that advances SM-2 --------------------

    def _append_msg(self, mid, role, text):
        db = sqlite3.connect(self.dir / "sessions" / "sessions.db")
        now = int(time.time() * 1000)
        db.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                   (mid, "ses_T", now, now, json.dumps({"role": role})))
        db.execute("INSERT INTO part VALUES (?,?,?,?,?,?)",
                   (mid + "_p", mid, "ses_T", now, now,
                    json.dumps({"type": "text", "text": text})))
        db.commit()
        db.close()

    def _append_assistant(self, mid, text):
        db = sqlite3.connect(self.dir / "sessions" / "sessions.db")
        now = int(time.time() * 1000)
        db.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                   (mid, "ses_T", now, now, json.dumps({"role": "assistant"})))
        db.execute("INSERT INTO part VALUES (?,?,?,?,?,?)",
                   (mid + "_p", mid, "ses_T", now, now,
                    json.dumps({"type": "text", "text": text})))
        db.commit()
        db.close()

    def _item(self, item_id="example_item_id"):
        sr = json.loads((self.dir / "spaced-repetition.json").read_text(encoding="utf-8"))
        return sr["items"][item_id]

    REVIEW_BLOCK = (
        "## Review session complete!\n\nGreat work today.\n\n"
        "```math:review_results\n"
        '[{"item_id": "example_item_id", "quality": 4},\n'
        ' {"item_id": "not_in_the_queue", "quality": 5}]\n'
        "```\n"
    )

    def test_review_block_advances_sm2_once(self):
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        self.assertEqual(self._item()["repetitions"], 0, "nothing should have advanced yet")

        # The tutor closes the session with the machine-readable block. Note it
        # carries no new grade: the accumulator must not gate on that.
        self._append_assistant("m4", self.REVIEW_BLOCK)
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))

        item = self._item()
        self.assertEqual(item["repetitions"], 1, "SM-2 did not advance from the review block")
        self.assertEqual(item["last_quality"], 4)
        self.assertGreater(item["easiness_factor"], 0)

        # Re-running must not count the same review twice (T0 restore + reapply).
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        self.assertEqual(self._item()["repetitions"], 1, "the review was counted twice")

        # And Capa B must not undo it, the way it used to undo error patterns.
        self._run("persist-session.py", "ses_T", "--dir", str(self.dir))
        self.assertEqual(self._item()["repetitions"], 1, "Capa B undid the SM-2 progress")
        self.assertEqual(self._item()["last_quality"], 4)

    def test_unknown_item_ids_are_discarded(self):
        self._append_assistant("m4", self.REVIEW_BLOCK)
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        sr = json.loads((self.dir / "spaced-repetition.json").read_text(encoding="utf-8"))
        self.assertNotIn("not_in_the_queue", sr["items"],
                         "an invented item_id reached the learner's queue")

    def test_results_file_is_named_after_the_learner(self):
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        self._run("persist-session.py", "ses_T", "--dir", str(self.dir))
        names = sorted(p.name for p in (self.dir / "results").glob("*.md"))
        self.assertEqual(names, ["test-math-learn-session-001.md"],
                         f"unexpected results files: {names}")


class StructuredRecordsTest(CapaABTest):
    """P1-5: the tutor DECLARES each graded answer via math_record_answer.

    The server validates and appends a record; the Python layer prefers records
    over the prose parsers and must not count the same answer twice.
    """

    def _write_record(self, **overrides):
        record = {
            "record_id": "ses_T:m3:1",
            "session_id": "ses_T",
            "ts": int(time.time() * 1000),
            "skill": "writing",
            "exercise": "Compute: 24 + 7",
            "learner_answer": "24 + 7 = 21",
            "score": 5,
            "corrections": [
                {"wrong": "21", "right": "31", "category": "carrying", "severity": "critical"}
            ],
        }
        record.update(overrides)
        d = self.dir / ".records"
        d.mkdir(exist_ok=True)
        with open(d / "ses_T.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _log(self):
        log = json.loads((self.dir / "session-log.json").read_text(encoding="utf-8"))
        return (log.get("sessions") or [{}])[-1]

    def test_recorded_answer_is_not_double_counted_with_the_prose(self):
        self._write_record()
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))

        self.assertEqual(self._log().get("exercises_completed"), 1,
                         "the same answer was counted by both the record and the parser")
        mistakes = json.loads((self.dir / "mistakes-db.json").read_text(encoding="utf-8"))
        self.assertIn("carrying_31", mistakes["error_patterns"])
        self.assertEqual(mistakes["error_patterns"]["carrying_31"]["frequency"], 1)

    def test_record_carries_the_category_the_tutor_declared(self):
        self._write_record(corrections=[
            {"wrong": "-5", "right": "+5", "category": "sign"}
        ])
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        mistakes = json.loads((self.dir / "mistakes-db.json").read_text(encoding="utf-8"))
        self.assertEqual(mistakes["error_patterns"]["sign_+5"]["category"],
                         "sign")

    def test_the_item_is_named_after_the_right_answer_not_the_slip(self):
        """A mistake is evidence. It is not the thing to be learned.

        Keyed on the wrong answer, a learner typing "ben" where "welcome"
        belonged created the item `vocabulary_ben` with content "ben" — and
        three days later the tutor asked "What is the correct English word for
        'ben'?". Seen live on test-en, 2026-09-19.
        """
        self._write_record(corrections=[
            {"wrong": "42", "right": "43", "category": "facts"}
        ])
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        pats = json.loads((self.dir / "mistakes-db.json").read_text(encoding="utf-8"))["error_patterns"]
        self.assertIn("facts_43", pats)
        self.assertNotIn("facts_42", pats)

        sr = json.loads((self.dir / "spaced-repetition.json").read_text(encoding="utf-8"))
        item = sr["items"]["facts_43"]
        self.assertEqual(item["content"], "43", "the item studies the right answer, not the slip")
        self.assertEqual(item["answer"], "43")
        self.assertEqual(item["learner_wrote"], "42", "the slip is kept as context only")

    def test_a_t0_from_another_day_is_not_this_session_s_past(self):
        """The id is a counter, and counters restart.

        `.update-state/session-002.json` held a snapshot from the night before
        with one spaced-repetition item in it. A new session numbered 002 today
        found that file, treated it as its own T0, and re-applying rolled the
        databases back to it: twelve items became two. Measured on a real
        profile, and it is the quietest kind of data loss there is — nothing
        fails, the file is simply older than it should be.
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "udb", REPO_ROOT / "hooks" / "update-db.py")
        udb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(udb)
        udb.DATA_DIR = self.dir
        yesterday = udb.state_path("session-002", "2026-09-18")
        today = udb.state_path("session-002", "2026-09-19")
        self.assertNotEqual(yesterday, today)
        yesterday.parent.mkdir(parents=True, exist_ok=True)
        yesterday.write_text('{"sr": {}}', encoding="utf-8")
        self.assertIsNone(udb.load_state("session-002", "2026-09-19"),
                          "yesterday's snapshot must not be found as today's")
        self.assertIsNotNone(udb.load_state("session-002", "2026-09-18"))
        self.assertIsNone(udb.load_state("session-002"),
                          "and there is no undated fallback: that fallback IS the bug")

    def test_both_parsers_agree_on_the_id(self):
        """The structured path and the prose path must name a pattern the same.

        They did not: one was fixed to key on the correct form, the other kept
        keying on the mistake, and both run over the same session. A real
        profile came back holding `articles_an` and `articles_banana` for the
        same correction — and the second became an SM-2 item, due the next day,
        asking the learner about her own typo.
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ps", REPO_ROOT / "hooks" / "persist-session.py")
        ps = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ps)
        self.assertEqual(ps.pattern_id_for("carrying", "25", "24"), "carrying_24")
        self.assertEqual(ps.pattern_id_for("carrying", "25", ""), "carrying_25",
                         "with no correct form there is nothing else to key on")
        src = (REPO_ROOT / "hooks" / "persist-session.py").read_text()
        self.assertNotIn('pid = f"{cat}_{m.group(1)', src,
                         "the prose parser is keying on the wrong answer again")

    def test_three_slips_of_one_answer_are_one_item(self):
        for wrong in ("3l", "31l", "3-1"):
            self._write_record(corrections=[
                {"wrong": wrong, "right": "31", "category": "calculation"}
            ])
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        pats = json.loads((self.dir / "mistakes-db.json").read_text(encoding="utf-8"))["error_patterns"]
        calc = [k for k in pats if k.startswith("calculation_")]
        self.assertEqual(calc, ["calculation_31"], calc)

    def test_record_with_item_id_advances_sm2_and_survives_capa_b(self):
        self._write_record(item_id="example_item_id", sm2_quality=5)
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        self.assertEqual(self._item()["repetitions"], 1)
        self.assertEqual(self._item()["last_quality"], 5)

        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        self.assertEqual(self._item()["repetitions"], 1, "the record was applied twice")

        self._run("persist-session.py", "ses_T", "--dir", str(self.dir))
        self.assertEqual(self._item()["repetitions"], 1, "Capa B undid the recorded review")
        self.assertEqual(self._log().get("exercises_completed"), 1,
                         "Capa B double-counted the recorded answer")

    def test_narrated_answers_still_count_when_not_recorded(self):
        """A tutor that records some answers and narrates others loses nothing.

        The merge key is the learner's answer, so a second exercise means a
        second answer — which is what a real session looks like.
        """
        self._append_msg("m4", "user", "12 - 5 = 5")
        self._append_msg("m5", "assistant",
                         'Almost.\n\n**Corrections:**\n- 🟡 "5" → **"7"** '
                         '(calculation — 12 − 5 is 7)\n\n**Score: 6/10**\n')
        self._write_record()
        self._run("accumulate-session.py", "--session-id", "ses_T", "--dir", str(self.dir))
        self.assertEqual(self._log().get("exercises_completed"), 2,
                         "the narrated answer was dropped")


if __name__ == "__main__":
    unittest.main()
