#!/usr/bin/env python3
"""
Tests for persist-session.py path resolution + the new opencode.db guard,
and accumulate-session.py's best-effort behavior when the db is absent.
Uses importlib because the filenames contain dashes.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / "hooks"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ResolveSessionsDbTest(unittest.TestCase):
    """Where a profile's transcript is read from, and in what order.

    The path moved from <profile>/.opencode/opencode/opencode.db (opencode's
    XDG shape) to <profile>/sessions/sessions.db. Both are read: a profile that
    has not been migrated keeps working, and the previous build of the app —
    which only knows the old path — keeps working on the file it wrote.
    """

    @classmethod
    def setUpClass(cls):
        cls.ps = _load("ps_under_test", "persist-session.py")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fluent-ps-"))
        self._saved_env = os.environ.pop("FLOWED_SESSIONS_DB", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("FLOWED_SESSIONS_DB", None)
        if self._saved_env is not None:
            os.environ["FLOWED_SESSIONS_DB"] = self._saved_env

    def _make(self, *rel):
        path = self.tmp.joinpath(*rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path

    def test_explicit_db_wins(self):
        p = self.tmp / "custom.db"
        self.assertEqual(self.ps.resolve_sessions_db(self.tmp, p), p)

    def test_env_override_beats_the_profile(self):
        self._make("sessions", "sessions.db")
        os.environ["FLOWED_SESSIONS_DB"] = str(self.tmp / "elsewhere.db")
        self.assertEqual(self.ps.resolve_sessions_db(self.tmp), self.tmp / "elsewhere.db")

    def test_current_path_when_present(self):
        current = self._make("sessions", "sessions.db")
        self.assertEqual(self.ps.resolve_sessions_db(self.tmp), current)

    def test_legacy_path_is_still_read(self):
        legacy = self._make(".opencode", "opencode", "opencode.db")
        self.assertEqual(self.ps.resolve_sessions_db(self.tmp), legacy)

    def test_current_wins_over_legacy_once_migrated(self):
        self._make(".opencode", "opencode", "opencode.db")
        current = self._make("sessions", "sessions.db")
        self.assertEqual(self.ps.resolve_sessions_db(self.tmp), current)

    def test_a_fresh_profile_is_born_on_the_new_path(self):
        self.assertEqual(self.ps.resolve_sessions_db(self.tmp),
                         self.tmp / "sessions" / "sessions.db")

    def test_no_profile_dir_falls_back_to_the_central_legacy_db(self):
        self.assertEqual(self.ps.resolve_sessions_db(None), self.ps.DEFAULT_OPENCODE_DB)

    def test_old_function_name_still_works(self):
        self.assertIs(self.ps.resolve_opencode_db, self.ps.resolve_sessions_db)

    def test_set_sessions_db_updates_both_globals(self):
        old = self.ps.SESSIONS_DB
        try:
            self.ps.set_sessions_db(self.tmp / "other.db")
            self.assertEqual(self.ps.SESSIONS_DB, self.tmp / "other.db")
            self.assertEqual(self.ps.OPENCODE_DB, self.tmp / "other.db")
        finally:
            self.ps.set_sessions_db(old)


class DbMissingGuardTest(unittest.TestCase):
    """End-to-end: a missing opencode.db must produce a clear [Fluent] error,
    never the confusing 'no such table: session' from a silently-created
    empty database."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fluent-ps-guard-"))
        self.missing = self.tmp / "nope.db"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _base_env(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("FLOWED_DATA_DIR", "CLAUDE_PROJECT_DIR",
                            "CLAUDE_PLUGIN_ROOT")}
        env["HOME"] = str(self.tmp)  # keep default db fallback out of the real home
        return env

    def test_persist_session_exits_1_when_db_missing(self):
        env = self._base_env()
        proc = subprocess.run(
            ["python3", str(HOOKS / "persist-session.py"),
             "--latest", "--db", str(self.missing)],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("sessions DB not found", proc.stderr)
        self.assertFalse(self.missing.exists(),
                         "guard ran too late — sqlite created an empty db file")

    def test_accumulate_session_skips_cleanly_when_db_missing(self):
        data = self.tmp / "data"
        data.mkdir()
        (data / "learner-profile.json").write_text(json.dumps(
            {"learner": {"name": "Tester"}}))
        env = self._base_env()
        env["FLOWED_DATA_DIR"] = str(data)
        # HOME is tmp, so the default ~/.local/share/opencode/opencode.db
        # does not exist either.
        proc = subprocess.run(
            ["python3", str(HOOKS / "accumulate-session.py"),
             "--dir", str(data), "--slug", "tester"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(proc.returncode, 0,
                         "best-effort hook must never block the session")
        self.assertIn("sessions DB not found", proc.stderr)


class ReopenFinalizedSessionTest(unittest.TestCase):
    """A session the learner comes back to is not finished.

    `markFinalized` was permanent: once the sweeper ran Capa B, the DB filter
    (`capa_b_done IS NULL`) excluded that session for ever. But web/app.js keeps
    the session id in localStorage, so reopening the browser hours later resumes
    the SAME session — and everything done afterwards reached the databases
    through Capa A only: no summary, no results file, no review_results block.
    Observed live: session ses_9073d7bb was finalized at 10:15 and took another
    turn at 16:09.

    This exercises the real SQL, on a throwaway database.
    """

    def setUp(self):
        import sqlite3
        from tempfile import TemporaryDirectory
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "sessions.db"
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TABLE session (id text PRIMARY KEY, agent text, metadata text, last_activity integer)"
        )
        conn.execute(
            "INSERT INTO session VALUES ('ses_done', 'learner', json_set('{}', '$.capa_b_done', 1760000000000), 100)"
        )
        conn.execute("INSERT INTO session VALUES ('ses_open', 'learner', '{}', 100)")
        conn.commit()
        conn.close()

    def _conn(self):
        import sqlite3
        return sqlite3.connect(self.db)

    def _stale(self, conn):
        return [r[0] for r in conn.execute(
            "SELECT id FROM session WHERE agent = 'learner' "
            "AND json_extract(COALESCE(metadata,'{}'), '$.capa_b_done') IS NULL"
        )]

    def _reopen(self, conn, sid):
        row = conn.execute(
            "SELECT json_extract(COALESCE(metadata,'{}'), '$.capa_b_done') FROM session WHERE id = ?",
            (sid,)).fetchone()
        if not row or row[0] is None:
            return False
        conn.execute(
            "UPDATE session SET metadata = json_remove(COALESCE(metadata,'{}'), '$.capa_b_done') WHERE id = ?",
            (sid,))
        conn.commit()
        return True

    def test_a_finalized_session_is_skipped_until_it_is_reopened(self):
        conn = self._conn()
        self.assertEqual(self._stale(conn), ["ses_open"],
                         "the finalized session should start out excluded")
        self.assertTrue(self._reopen(conn, "ses_done"), "reopen should report a change")
        self.assertCountEqual(self._stale(conn), ["ses_open", "ses_done"],
                              "after a new turn the session must be finalizable again")
        conn.close()

    def test_reopening_an_open_session_changes_nothing(self):
        conn = self._conn()
        self.assertFalse(self._reopen(conn, "ses_open"))
        self.assertCountEqual(self._stale(conn), ["ses_open"])
        conn.close()

    def test_reopening_keeps_the_rest_of_the_metadata(self):
        conn = self._conn()
        conn.execute(
            "UPDATE session SET metadata = json_set(metadata, '$.keep', 'me') WHERE id = 'ses_done'")
        conn.commit()
        self._reopen(conn, "ses_done")
        meta = conn.execute("SELECT metadata FROM session WHERE id = 'ses_done'").fetchone()[0]
        self.assertIn("keep", meta, "reopening must not wipe unrelated metadata")
        self.assertNotIn("capa_b_done", meta)
        conn.close()


if __name__ == "__main__":
    unittest.main()


class MigrateSessionsDbTest(unittest.TestCase):
    """scripts/migrate-sessions-db.py: copy, verify, never delete."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fluent-mig-"))
        (self.tmp / "learner-profile.json").write_text('{"learner": {"name": "Test"}}',
                                                       encoding="utf-8")
        self.legacy = self.tmp / ".opencode" / "opencode" / "opencode.db"
        self.legacy.parent.mkdir(parents=True)
        import sqlite3
        db = sqlite3.connect(self.legacy)
        db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE session (id text PRIMARY KEY, agent text);
            CREATE TABLE message (id text PRIMARY KEY, session_id text, data text);
            CREATE TABLE part (id text PRIMARY KEY, message_id text, session_id text, data text);
        """)
        db.executemany("INSERT INTO session VALUES (?,?)", [(f"ses_{i}", "learner") for i in range(3)])
        db.executemany("INSERT INTO message VALUES (?,?,?)", [(f"m{i}", "ses_0", "{}") for i in range(5)])
        db.commit()
        db.close()
        self.current = self.tmp / "sessions" / "sessions.db"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "migrate-sessions-db.py"),
             "--dir", str(self.tmp), *args],
            capture_output=True, text=True)

    def _counts(self, path):
        import sqlite3
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return [conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                    for t in ("session", "message", "part")]
        finally:
            conn.close()

    def test_dry_run_changes_nothing(self):
        proc = self._run("--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(self.current.exists())

    def test_copy_matches_and_original_stays(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.current.exists(), "the new DB was not created")
        self.assertTrue(self.legacy.exists(), "the legacy DB must never be deleted")
        self.assertEqual(self._counts(self.current), self._counts(self.legacy))
        self.assertEqual(self._counts(self.current), [3, 5, 0])
        leftovers = [p.name for p in self.current.parent.iterdir() if ".tmp" in p.name]
        self.assertEqual(leftovers, [], f"temporary sidecars left behind: {leftovers}")

    def test_second_run_refuses_to_overwrite(self):
        self._run()
        proc = self._run()
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no la trepitjo", proc.stdout)


class SessionDateTest(unittest.TestCase):
    """A session is dated by the day it happened, not the day it was written up.

    `datetime.now()` is right for a session closed the same day and wrong for
    every other case. Seen live: the sweeper picked up sessions from 3 and 9
    September and stamped them both 14 September, so `session-log.json` claimed
    two learners had practised on a day nobody opened the app. The numbers were
    never wrong — update-db restores its T0 snapshot before re-applying — but
    the history read as fiction, and history is what the tutor cites back.
    """

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "persist_session", REPO_ROOT / "hooks" / "persist-session.py")
        self.ps = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ps)
        # 2026-09-09 17:52 local
        self.sept9 = int(datetime(2026, 9, 9, 17, 52).timestamp() * 1000)

    def test_the_session_row_decides(self):
        self.assertEqual(self.ps.session_date({"time_created": self.sept9}), "2026-09-09")

    def test_reprocessing_weeks_later_keeps_the_original_day(self):
        # The whole point: today is irrelevant.
        self.assertNotEqual(self.ps.session_date({"time_created": self.sept9}),
                            datetime.now().strftime("%Y-%m-%d"))

    def test_last_activity_is_the_next_best_thing(self):
        self.assertEqual(self.ps.session_date({"last_activity": self.sept9}), "2026-09-09")

    def test_a_useless_timestamp_falls_through_to_the_next(self):
        got = self.ps.session_date({"time_created": "rubbish", "last_activity": self.sept9})
        self.assertEqual(got, "2026-09-09")

    def test_zero_is_not_a_date(self):
        self.assertEqual(self.ps.session_date({"time_created": 0, "last_activity": self.sept9}),
                         "2026-09-09")

    def test_nothing_to_go_on_falls_back_to_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(self.ps.session_date({}), today)
        self.assertEqual(self.ps.session_date(None), today)
