#!/usr/bin/env python3
"""
Tests for hooks/main_paths.py path resolution.

Exercises the precedence rules documented in the module docstring without
creating real dirs: FLOWED_DATA_DIR -> CLAUDE_PROJECT_DIR/data -> ./data ->
~/.claude/fluent-data, plus plugin_root and backups_dir nesting.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / "hooks"
sys.path.insert(0, str(HOOKS))

import main_paths  # noqa: E402

MANAGED_ENV = ("FLOWED_DATA_DIR", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")


def clear_caches():
    main_paths.data_dir.cache_clear()
    main_paths.plugin_root.cache_clear()
    main_paths.backups_dir.cache_clear()


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
        os.environ["FLOWED_DATA_DIR"] = str(d)
        clear_caches()
        self.assertEqual(main_paths.data_dir(), d.resolve())

    def test_env_var_pointing_at_empty_dir_falls_through(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        cwd_data = self._make_data(self.tmp / "repo" / "data")
        os.chdir(self.tmp / "repo")
        os.environ["FLOWED_DATA_DIR"] = str(empty)
        clear_caches()
        self.assertEqual(main_paths.data_dir(), cwd_data.resolve())

    def test_project_dir_data_used_when_it_holds_profile(self):
        project = self._make_data(self.tmp / "proj" / "data").parent
        os.chdir(self.tmp)  # cwd/data has no profile
        os.environ["CLAUDE_PROJECT_DIR"] = str(project)
        clear_caches()
        self.assertEqual(main_paths.data_dir(), project.resolve() / "data")

    def test_cwd_data_used_in_repo_mode(self):
        d = self._make_data(self.tmp / "data")
        os.chdir(self.tmp)
        clear_caches()
        self.assertEqual(main_paths.data_dir(), d.resolve())

    def test_home_fallback_when_nothing_matches(self):
        (self.tmp / "home").mkdir()
        os.chdir(self.tmp)
        os.environ["HOME"] = str(self.tmp / "home")
        clear_caches()
        self.assertEqual(
            main_paths.data_dir(),
            (self.tmp / "home" / ".claude" / "fluent-data").resolve(),
        )

    def test_backups_dir_nested_under_data_dir(self):
        d = self._make_data(self.tmp / "data")
        os.chdir(self.tmp)
        clear_caches()
        self.assertEqual(main_paths.backups_dir(), d.resolve() / ".backups")

    def test_ensure_creates_dirs(self):
        target = self._make_data(self.tmp / "data")
        os.chdir(self.tmp)
        clear_caches()
        resolved = main_paths.ensure_data_dir()
        self.assertTrue(resolved.is_dir())
        b = main_paths.ensure_backups_dir()
        self.assertTrue(b.is_dir())
        self.assertEqual(b, resolved / ".backups")

    def test_plugin_root_env_precedence(self):
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(self.tmp / "plugin")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.tmp / "project")
        clear_caches()
        self.assertEqual(main_paths.plugin_root(), (self.tmp / "plugin").resolve())

    def test_plugin_root_project_dir_second(self):
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.tmp / "project")
        clear_caches()
        self.assertEqual(main_paths.plugin_root(), (self.tmp / "project").resolve())

    def test_plugin_root_dev_fallback_is_repo_root(self):
        clear_caches()
        self.assertEqual(main_paths.plugin_root(), REPO_ROOT.resolve())

    def test_force_utf8_io_is_safe_to_call(self):
        main_paths.force_utf8_io()  # must not raise on any platform


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
            "main_paths", REPO_ROOT / "hooks" / "main_paths.py")
        self.fp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.fp)

    def test_the_new_name_is_preferred(self):
        self.assertEqual(self.fp.ROOT_ENV_VARS[0], "FLOWED_ROOT")

    def test_the_old_names_are_still_read(self):
        self.assertIn("CLAUDE_PLUGIN_ROOT", self.fp.ROOT_ENV_VARS)
        self.assertIn("CLAUDE_PROJECT_DIR", self.fp.ROOT_ENV_VARS)

    def test_first_match_wins(self):
        import os
        env = {"CLAUDE_PROJECT_DIR": "/old", "FLOWED_ROOT": "/new"}
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


class ProfilesRootTest(unittest.TestCase):
    """Where the learners live: one rule, in main_paths.py and lib-paths.sh alike."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home)}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("FLOWED_HOME", None)

    def shell(self) -> str:
        lib = REPO_ROOT / "scripts" / "lib-paths.sh"
        return subprocess.run(["bash", "-c", f'source "{lib}"; echo "$FLOWED_HOME_DIR"'],
                              capture_output=True, text=True, env=dict(os.environ)).stdout.strip()

    def both(self) -> tuple[str, str]:
        return str(main_paths.profiles_root()), self.shell()

    def test_a_new_machine_gets_flowed(self):
        self.assertEqual((str(self.home / ".flowed"),) * 2, self.both())

    def test_the_old_folder_is_used_until_it_is_moved(self):
        (self.home / ".fluent").mkdir()
        self.assertEqual((str(self.home / ".fluent"),) * 2, self.both())

    def test_once_moved_the_new_one_wins(self):
        (self.home / ".fluent").mkdir()
        (self.home / ".flowed").mkdir()
        self.assertEqual((str(self.home / ".flowed"),) * 2, self.both())

    def test_the_variable_wins_over_both(self):
        os.environ["FLOWED_HOME"] = str(self.home / "altres")
        self.assertEqual((str(self.home / "altres"),) * 2, self.both())
        self.assertEqual(self.home / "altres" / "nes-en", main_paths.profile_dir("nes-en"))


class LoadEnvTest(unittest.TestCase):
    """scripts/lib-paths.sh flowed_load_env — the one .env loader of every script.

    2026-09-26, llvm: an .env still written with the pre-0.5.0 names was ignored
    in silence, every value fell back to config/fluent.json (railab's native
    backend, port 12322), and the start tried to bring the model up the railab way.
    """

    def run_loader(self, env_text, extra_env=None):
        with tempfile.TemporaryDirectory() as d:
            if env_text is not None:
                Path(d, ".env").write_text(env_text)
            env = {k: v for k, v in os.environ.items() if not k.startswith(("FLOWED_", "FLUENT_"))}
            env.update(extra_env or {})
            script = (f'set -euo pipefail; source "{REPO_ROOT}/scripts/lib-paths.sh"; '
                      f'flowed_load_env "{d}"; '
                      'echo "$FLOWED_DEEP_PORT|${FLOWED_DEEP_BACKEND:-}|${FLOWED_ENV_FILE:+yes}"')
            r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)
            self.assertEqual(0, r.returncode, r.stderr)
            return r.stdout.strip(), r.stderr

    def test_new_names(self):
        out, err = self.run_loader("FLOWED_DEEP_PORT=12321\nFLOWED_DEEP_BACKEND=docker\n")
        self.assertEqual("12321|docker|yes", out)
        self.assertEqual("", err)

    def test_old_names_still_work_and_say_so(self):
        out, err = self.run_loader("FLUENT_DEEP_PORT=12321\nFLUENT_DEEP_BACKEND=docker\n")
        self.assertEqual("12321|docker|yes", out)
        self.assertIn("FLUENT_DEEP_PORT", err)

    def test_the_environment_wins_over_the_file(self):
        out, _ = self.run_loader("FLOWED_DEEP_PORT=12321\n", {"FLOWED_DEEP_PORT": "9"})
        self.assertTrue(out.startswith("9|"), out)

    def test_no_file_is_reported(self):
        out, _ = self.run_loader(None, {"FLOWED_DEEP_PORT": "1"})
        self.assertEqual("1||", out)
