#!/usr/bin/env python3
"""
Tests for scripts/migrate-db.py: check/migrate exit codes, backup, idempotency,
and refusal to touch future-schema or corrupt databases.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "migrate-db.py"

NAMES = ["learner-profile.json", "spaced-repetition.json", "mistakes-db.json",
         "progress-db.json", "mastery-db.json", "session-log.json"]


class MigrateDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="math-mig-"))
        self.data = self.tmp / "data"
        self.data.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_db(self, name, doc):
        (self.data / name).write_text(json.dumps(doc), encoding="utf-8")

    def write_legacy_set(self):
        for name in NAMES:
            self.write_db(name, {"seed": name})  # no _schema_version

    def _run(self, *args):
        env = {k: v for k, v in os.environ.items() if k != "FLOWED_DATA_DIR"}
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            capture_output=True, text=True, env=env,
        )

    def _backup_dirs(self):
        b = self.data / ".backups"
        return sorted(p for p in b.iterdir()) if b.is_dir() else []

    def test_check_flags_legacy_then_migrate_stamps(self):
        self.write_legacy_set()
        check = self._run("--dir", str(self.data), "--check")
        self.assertEqual(check.returncode, 1, msg=check.stderr)
        run = self._run("--dir", str(self.data))
        self.assertEqual(run.returncode, 0, msg=run.stderr)
        for name in NAMES:
            doc = json.loads((self.data / name).read_text())
            self.assertEqual(doc.get("_schema_version"), 1, name)
        backups = self._backup_dirs()
        self.assertEqual(len(backups), 1)
        # Backup holds the pre-migration (un-stamped) copies.
        bdoc = json.loads((backups[0] / "learner-profile.json").read_text())
        self.assertNotIn("_schema_version", bdoc)

    def test_idempotent_second_run_writes_nothing(self):
        self.write_legacy_set()
        self._run("--dir", str(self.data))
        raw_before = {p.name: p.read_bytes() for p in self.data.glob("*.json")}
        run = self._run("--dir", str(self.data))
        self.assertEqual(run.returncode, 0, msg=run.stderr)
        self.assertIn("Nothing to do", run.stdout)
        raw_after = {p.name: p.read_bytes() for p in self.data.glob("*.json")}
        self.assertEqual(raw_before, raw_after)
        self.assertEqual(len(self._backup_dirs()), 1, "second run created a backup")

    def test_check_clean_after_migrate(self):
        self.write_legacy_set()
        self._run("--dir", str(self.data))
        check = self._run("--dir", str(self.data), "--check")
        self.assertEqual(check.returncode, 0, msg=check.stderr)
        self.assertIn("up to date", check.stdout)

    def test_future_schema_aborts_disk_untouched(self):
        self.write_legacy_set()
        self.write_db("progress-db.json", {"seed": "x", "_schema_version": 99})
        raw_before = {p.name: p.read_bytes() for p in self.data.glob("*.json")}
        run = self._run("--dir", str(self.data))
        self.assertEqual(run.returncode, 2)
        self.assertIn("newer", run.stderr)
        raw_after = {p.name: p.read_bytes() for p in self.data.glob("*.json")}
        self.assertEqual(raw_before, raw_after)
        self.assertEqual(self._backup_dirs(), [])

    def test_corrupt_file_exit_2(self):
        self.write_legacy_set()
        (self.data / "mastery-db.json").write_text("{ broken")
        run = self._run("--dir", str(self.data))
        self.assertEqual(run.returncode, 2)
        self.assertIn("Cannot read", run.stderr)

    def test_partial_set_migrates_present_only(self):
        self.write_db("learner-profile.json", {"learner": {}})
        self.write_db("session-log.json", {"sessions": []})
        run = self._run("--dir", str(self.data))
        self.assertEqual(run.returncode, 0, msg=run.stderr)
        self.assertIn("Missing (skipped)", run.stderr)
        for name in ("learner-profile.json", "session-log.json"):
            self.assertEqual(
                json.loads((self.data / name).read_text())["_schema_version"], 1)

    def test_empty_dir_exit_2(self):
        run = self._run("--dir", str(self.data))
        self.assertEqual(run.returncode, 2)

    def test_nonexistent_dir_exit_2(self):
        run = self._run("--dir", str(self.tmp / "nope"))
        self.assertEqual(run.returncode, 2)

    def test_env_var_data_dir(self):
        self.write_legacy_set()
        env = {k: v for k, v in os.environ.items() if k != "FLOWED_DATA_DIR"}
        env["FLOWED_DATA_DIR"] = str(self.data)
        proc = subprocess.run(["python3", str(SCRIPT)],
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("Migrated", proc.stdout)

    def test_no_tmp_files_left_after_migrate(self):
        self.write_legacy_set()
        self._run("--dir", str(self.data))
        self.assertEqual(list(self.data.glob("*.tmp")), [])

    def test_check_does_not_create_lock_file(self):
        self.write_legacy_set()
        run = self._run("--dir", str(self.data), "--check")
        self.assertEqual(run.returncode, 1, msg=run.stderr)
        self.assertFalse((self.data / ".db.lock").exists())

    def test_migrate_waits_for_database_lock(self):
        if fcntl is None:
            self.skipTest("flock is unavailable on this platform")
        self.write_legacy_set()
        lock_path = self.data / ".db.lock"
        with open(lock_path, "a+", encoding="utf-8") as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX)
            env = {k: v for k, v in os.environ.items() if k != "FLOWED_DATA_DIR"}
            env["FLOWED_DB_LOCK_TIMEOUT"] = "0.1"
            run = subprocess.run(
                ["python3", str(SCRIPT), "--dir", str(self.data)],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(run.returncode, 2, msg=run.stderr)
            self.assertIn("Database lock timeout", run.stderr)

        for name in NAMES:
            doc = json.loads((self.data / name).read_text())
            self.assertNotIn("_schema_version", doc)
        self.assertEqual(self._backup_dirs(), [])


if __name__ == "__main__":
    unittest.main()
