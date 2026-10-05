#!/usr/bin/env python3
"""Tests for advisory database locks (db_lock.py + update-db.py)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

REPO_ROOT = Path(__file__).resolve().parent.parent
UPDATE_DB = REPO_ROOT / "hooks" / "update-db.py"
sys.path.insert(0, str(REPO_ROOT / "tests"))
from test_update_db import SESSION_PAYLOAD, make_fixtures  # noqa: E402


def base_env(data_dir: Path, lock_timeout: str | None = None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("FLOWED_DATA_DIR", "FLOWED_PROJECT_DIR", "FLOWED_ROOT",
                                "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")}
    env["FLOWED_DATA_DIR"] = str(data_dir)
    if lock_timeout is not None:
        env["FLOWED_DB_LOCK_TIMEOUT"] = lock_timeout
    return env


class UpdateDbLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="math-lock-"))
        self.data = self.tmp / "data"
        self.data.mkdir()
        make_fixtures(self.data)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, payload: dict, lock_timeout: str | None = None):
        return subprocess.run(
            ["python3", str(UPDATE_DB)],
            input=json.dumps(payload).encode(),
            cwd=str(self.tmp),
            capture_output=True,
            env=base_env(self.data, lock_timeout),
        )

    def test_lock_blocks_second_writer_until_timeout(self):
        if fcntl is None:
            self.skipTest("flock is unavailable on this platform")
        lock_path = self.data / ".db.lock"
        with open(lock_path, "a+", encoding="utf-8") as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX)
            proc = self._run(dict(SESSION_PAYLOAD, session_id="session-blocked"), "0.1")
            self.assertEqual(proc.returncode, 2, msg=f"stderr={proc.stderr!r}")
            self.assertIn(b"database lock timeout", proc.stderr)

        log = json.loads((self.data / "session-log.json").read_text())
        self.assertEqual([s["session_id"] for s in log["sessions"]], ["session-001"])

    def test_lock_released_after_writer_exits(self):
        if fcntl is None:
            self.skipTest("flock is unavailable on this platform")
        lock_path = self.data / ".db.lock"
        with open(lock_path, "a+", encoding="utf-8") as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        proc = self._run(dict(SESSION_PAYLOAD, session_id="session-after-lock"))
        self.assertEqual(proc.returncode, 0, msg=f"stderr={proc.stderr!r}")

    def test_concurrent_updates_are_serialized_and_both_apply(self):
        proc_a = subprocess.Popen(
            ["python3", str(UPDATE_DB)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.tmp),
            env=base_env(self.data),
        )
        proc_b = subprocess.Popen(
            ["python3", str(UPDATE_DB)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.tmp),
            env=base_env(self.data),
        )
        a_in = json.dumps(dict(SESSION_PAYLOAD, session_id="session-a")).encode()
        b_in = json.dumps(dict(SESSION_PAYLOAD, session_id="session-b")).encode()
        a_out, a_err = proc_a.communicate(a_in)
        b_out, b_err = proc_b.communicate(b_in)
        self.assertEqual(proc_a.returncode, 0, msg=f"stderr={a_err!r}")
        self.assertEqual(proc_b.returncode, 0, msg=f"stderr={b_err!r}")

        log = json.loads((self.data / "session-log.json").read_text())
        ids = {s["session_id"] for s in log["sessions"]}
        self.assertIn("session-a", ids)
        self.assertIn("session-b", ids)
        progress = json.loads((self.data / "progress-db.json").read_text())
        self.assertEqual(progress["overall_stats"]["total_exercises"], 14)
        self.assertEqual(progress["overall_stats"]["total_sessions"], 3)

    def test_lock_file_is_not_backed_up(self):
        proc = self._run(dict(SESSION_PAYLOAD, session_id="session-locks"))
        self.assertEqual(proc.returncode, 0, msg=f"stderr={proc.stderr!r}")
        self.assertTrue((self.data / ".db.lock").exists())
        backup = self.data / ".backups" / "pre-update-session-locks"
        self.assertTrue(backup.exists())
        self.assertFalse((backup / ".db.lock").exists())
        self.assertEqual([p.name for p in backup.glob("*") if not p.name.endswith(".json")], [])


if __name__ == "__main__":
    unittest.main()
