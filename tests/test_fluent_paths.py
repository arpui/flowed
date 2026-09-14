#!/usr/bin/env python3
"""
Tests for hooks/fluent_paths.py path resolution.

Exercises the precedence rules documented in the module docstring without
creating real dirs: FLUENT_DATA_DIR -> CLAUDE_PROJECT_DIR/data -> ./data ->
~/.claude/fluent-data, plus plugin_root and backups_dir nesting.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / "hooks"
sys.path.insert(0, str(HOOKS))

import fluent_paths  # noqa: E402

MANAGED_ENV = ("FLUENT_DATA_DIR", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")


def clear_caches():
    fluent_paths.data_dir.cache_clear()
    fluent_paths.plugin_root.cache_clear()
    fluent_paths.backups_dir.cache_clear()


class FluentPathsTest(unittest.TestCase):
    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in MANAGED_ENV}
        self._saved_home = os.environ.get("HOME")
        for k in MANAGED_ENV:
            os.environ.pop(k, None)
        self.tmp = Path(tempfile.mkdtemp(prefix="fluent-paths-"))
        self._old_cwd = Path.cwd()
        clear_caches()

    def tearDown(self):
        os.chdir(self._old_cwd)
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if self._saved_home is not None:
            os.environ["HOME"] = self._saved_home
        clear_caches()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_data(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        (path / "learner-profile.json").write_text("{}")
        return path

    def test_env_var_wins_when_profile_present(self):
        d = self._make_data(self.tmp / "explicit")
        os.environ["FLUENT_DATA_DIR"] = str(d)
        clear_caches()
        self.assertEqual(fluent_paths.data_dir(), d.resolve())

    def test_env_var_pointing_at_empty_dir_falls_through(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        cwd_data = self._make_data(self.tmp / "repo" / "data")
        os.chdir(self.tmp / "repo")
        os.environ["FLUENT_DATA_DIR"] = str(empty)
        clear_caches()
        self.assertEqual(fluent_paths.data_dir(), cwd_data.resolve())

    def test_project_dir_data_used_when_it_holds_profile(self):
        project = self._make_data(self.tmp / "proj" / "data").parent
        os.chdir(self.tmp)  # cwd/data has no profile
        os.environ["CLAUDE_PROJECT_DIR"] = str(project)
        clear_caches()
        self.assertEqual(fluent_paths.data_dir(), project.resolve() / "data")

    def test_cwd_data_used_in_repo_mode(self):
        d = self._make_data(self.tmp / "data")
        os.chdir(self.tmp)
        clear_caches()
        self.assertEqual(fluent_paths.data_dir(), d.resolve())

    def test_home_fallback_when_nothing_matches(self):
        (self.tmp / "home").mkdir()
        os.chdir(self.tmp)
        os.environ["HOME"] = str(self.tmp / "home")
        clear_caches()
        self.assertEqual(
            fluent_paths.data_dir(),
            (self.tmp / "home" / ".claude" / "fluent-data").resolve(),
        )

    def test_backups_dir_nested_under_data_dir(self):
        d = self._make_data(self.tmp / "data")
        os.chdir(self.tmp)
        clear_caches()
        self.assertEqual(fluent_paths.backups_dir(), d.resolve() / ".backups")

    def test_ensure_creates_dirs(self):
        target = self._make_data(self.tmp / "data")
        os.chdir(self.tmp)
        clear_caches()
        resolved = fluent_paths.ensure_data_dir()
        self.assertTrue(resolved.is_dir())
        b = fluent_paths.ensure_backups_dir()
        self.assertTrue(b.is_dir())
        self.assertEqual(b, resolved / ".backups")

    def test_plugin_root_env_precedence(self):
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(self.tmp / "plugin")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.tmp / "project")
        clear_caches()
        self.assertEqual(fluent_paths.plugin_root(), (self.tmp / "plugin").resolve())

    def test_plugin_root_project_dir_second(self):
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.tmp / "project")
        clear_caches()
        self.assertEqual(fluent_paths.plugin_root(), (self.tmp / "project").resolve())

    def test_plugin_root_dev_fallback_is_repo_root(self):
        clear_caches()
        self.assertEqual(fluent_paths.plugin_root(), REPO_ROOT.resolve())

    def test_force_utf8_io_is_safe_to_call(self):
        fluent_paths.force_utf8_io()  # must not raise on any platform


if __name__ == "__main__":
    unittest.main()


class EnvVarNamesTest(unittest.TestCase):
    """The env vars carry the project's name, not the tool it grew inside.

    `CLAUDE_PROJECT_DIR` / `CLAUDE_PLUGIN_ROOT` were the contract between the
    server and the Python hooks. Both ends live in this repo, so renaming them
    is safe — but the old spellings are still READ, so an older checkout, or
    that tool itself, keeps working. Nothing writes them any more.
    """

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fluent_paths", REPO_ROOT / "hooks" / "fluent_paths.py")
        self.fp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.fp)

    def test_the_new_name_is_preferred(self):
        self.assertEqual(self.fp.ROOT_ENV_VARS[0], "FLUENT_ROOT")

    def test_the_old_names_are_still_read(self):
        self.assertIn("CLAUDE_PLUGIN_ROOT", self.fp.ROOT_ENV_VARS)
        self.assertIn("CLAUDE_PROJECT_DIR", self.fp.ROOT_ENV_VARS)

    def test_first_match_wins(self):
        import os
        env = {"CLAUDE_PROJECT_DIR": "/old", "FLUENT_ROOT": "/new"}
        old = {k: os.environ.get(k) for k in env}
        try:
            os.environ.update(env)
            self.assertEqual(self.fp._first_env(self.fp.ROOT_ENV_VARS), "/new")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_nothing_set_is_none(self):
        self.assertIsNone(self.fp._first_env(("NOPE_NOT_SET_AT_ALL",)))

    def test_the_server_writes_only_the_new_names(self):
        for name in ("agent.ts", "tools.ts", "commands.ts"):
            src = (REPO_ROOT / "server" / "src" / name).read_text()
            self.assertNotIn("CLAUDE_PROJECT_DIR", src,
                             f"server/src/{name} still sets the old variable")
