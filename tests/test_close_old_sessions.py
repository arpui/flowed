#!/usr/bin/env python3
"""Closing old sessions must be a no-op for everything the learner can see.

Sessions from the old build were never finalized. They are already ignored (the
sweeper looks back 24 h), so marking them changes no behaviour today — it makes
that state explicit, so a future change to that window cannot wake a three-week
-old session and fold it into the databases a second time.

The property that matters: **it writes one metadata flag and nothing else.**
No Capa B, no results file, no number moved.
"""
import json
import sqlite3
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "close-old-sessions.py"
DAY_MS = 86_400_000


class CloseOldSessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.profile = self.home / ".fluent" / "demo-en"
        (self.profile / "sessions").mkdir(parents=True)
        (self.profile / "learner-profile.json").write_text('{"learner": {"name": "D"}}')

        # The six databases, so we can prove they are not touched.
        self.dbs = {}
        for name in ("mistakes-db", "mastery-db", "progress-db",
                     "spaced-repetition", "session-log"):
            f = self.profile / f"{name}.json"
            f.write_text(json.dumps({"marker": name}))
            self.dbs[name] = f.read_bytes()

        self.db = self.profile / "sessions" / "sessions.db"
        now = int(time.time() * 1000)
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE session (id text PRIMARY KEY, agent text, "
                     "metadata text, last_activity integer)")
        for sid, meta, age_days in (
            ("ses_old", None, 20),
            ("ses_recent", None, 5),
            ("ses_today", None, 0),
            ("ses_done", json.dumps({"capa_b_done": 1}), 30),
        ):
            conn.execute("INSERT INTO session VALUES (?,?,?,?)",
                         (sid, "learner", meta, now - int(age_days * DAY_MS)))
        conn.commit()
        conn.close()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--profile", "demo-en", *args],
            capture_output=True, text=True, cwd=REPO_ROOT,
            env={"HOME": str(self.home), "PATH": "/usr/bin:/bin"},
        )

    def state(self):
        return {
            sid: bool(meta and "capa_b_done" in meta)
            for sid, meta in sqlite3.connect(self.db).execute("SELECT id, metadata FROM session")
        }

    def test_old_sessions_are_closed(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.state()["ses_old"])
        self.assertTrue(self.state()["ses_recent"])

    def test_todays_session_is_left_alone(self):
        self.run_cli()
        self.assertFalse(self.state()["ses_today"],
                         "a session the learner may still be in must not be closed")

    def test_the_six_databases_are_not_touched(self):
        self.run_cli()
        for name, before in self.dbs.items():
            self.assertEqual((self.profile / f"{name}.json").read_bytes(), before,
                             f"{name}.json changed — this script must move no numbers")

    def test_no_results_file_is_written(self):
        self.run_cli()
        self.assertFalse((self.profile / "results").exists())

    def test_dry_run_changes_nothing(self):
        before = self.state()
        r = self.run_cli("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state(), before)
        self.assertIn("SIMULACIÓ", r.stdout)

    def test_a_backup_is_left_behind(self):
        self.run_cli()
        self.assertTrue(list((self.profile / "sessions").glob("sessions.db.bak-*")))

    def test_running_twice_is_harmless(self):
        self.run_cli()
        after_first = self.state()
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state(), after_first)
        self.assertIn("cap sessió antiga oberta", r.stdout)

    def test_the_window_is_respected(self):
        self.run_cli("--older-than", "10")
        s = self.state()
        self.assertTrue(s["ses_old"], "20 days old, should close")
        self.assertFalse(s["ses_recent"], "5 days old, outside a 10-day window")

    def test_it_refuses_to_touch_todays_sessions(self):
        r = self.run_cli("--older-than", "0")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("1 dia", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main()
