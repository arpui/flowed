#!/usr/bin/env python3
"""The prompt tree must be where the server looks for it.

After the 2026-09-13 rename (.opencode/ -> prompts/), a half-finished move
would only surface as a silent behaviour change: a missing agent file makes
readAgentBody() return "", and the tutor would run with no persona and no hard
rules instead of failing. These checks are cheap insurance.
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class PromptTreeTest(unittest.TestCase):
    def test_agents_exist_where_the_server_reads_them(self):
        for name in ("learner.md", "tutor.md", "tutor-fast.md", "rules.md"):
            path = REPO_ROOT / "prompts" / "agents" / name
            self.assertTrue(path.exists(), f"missing prompt: {path}")
            self.assertGreater(path.stat().st_size, 200, f"suspiciously small: {path}")

    def test_every_command_the_ui_can_start_exists(self):
        # The web buttons and the auto-start path in web/app.js.
        for cmd in ("fluent-learn", "fluent-review", "fluent-vocab", "fluent-writing",
                    "fluent-speaking", "fluent-reading", "fluent-progress",
                    "fluent-setup", "fluent-end", "fluent-use"):
            path = REPO_ROOT / "prompts" / "commands" / f"{cmd}.md"
            self.assertTrue(path.exists(), f"missing command: {path}")

    def test_server_paths_point_at_the_prompt_tree(self):
        agent = (REPO_ROOT / "server" / "src" / "agent.ts").read_text(encoding="utf-8")
        commands = (REPO_ROOT / "server" / "src" / "commands.ts").read_text(encoding="utf-8")
        self.assertIn('"prompts", "agents"', agent)
        self.assertIn('"prompts", "commands"', commands)


class NoStaleReferencesTest(unittest.TestCase):
    """`.opencode` may only survive as the per-profile DATA path."""

    DATA_PATH = re.compile(r"\.opencode[\"'/\\, ]*(opencode|\"opencode\")")

    def test_no_repo_path_still_points_at_dot_opencode(self):
        offenders = []
        for pattern in ("server/src/*.ts", "skills/*/SKILL.md",
                        "prompts/agents/*.md", "prompts/commands/*.md",
                        "hooks/*.py"):
            for path in REPO_ROOT.glob(pattern):
                for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if ".opencode" not in line:
                        continue
                    # the profile's own SQLite lives at <profile>/.opencode/opencode/
                    if self.DATA_PATH.search(line) or "XDG_DATA_HOME" in line:
                        continue
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()[:90]}")
        self.assertEqual(offenders, [], "stale .opencode references:\n" + "\n".join(offenders))

    def test_list_profiles_helper_moved_with_its_allow_list(self):
        self.assertTrue((REPO_ROOT / "scripts" / "list-profiles.py").exists())
        tools = (REPO_ROOT / "server" / "src" / "tools.ts").read_text(encoding="utf-8")
        self.assertIn("scripts\\/list-profiles\\.py", tools)


if __name__ == "__main__":
    unittest.main()


class FluentCheckScriptTest(unittest.TestCase):
    """scripts/flowed-check.py is what PROVES.md tells the user to run.

    It must survive a profile that is missing everything (a fresh one) without
    tracebacks — a diagnostic tool that crashes on the case you are diagnosing
    is worse than none.
    """

    def setUp(self):
        import shutil
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="fluent-check-"))
        self._rm = shutil.rmtree
        for name in ("learner-profile", "mastery-db", "mistakes-db", "progress-db",
                     "session-log", "spaced-repetition"):
            shutil.copy(REPO_ROOT / "data-examples" / f"{name}-template.json",
                        self.tmp / f"{name}.json")

    def tearDown(self):
        self._rm(self.tmp, ignore_errors=True)

    def _run(self, check):
        import subprocess
        import sys as _sys
        return subprocess.run(
            [_sys.executable, str(REPO_ROOT / "scripts" / "flowed-check.py"),
             check, "--dir", str(self.tmp)],
            capture_output=True, text=True)

    def test_every_check_runs_on_a_bare_profile(self):
        for check in ("profile", "sm2", "patterns", "mastery", "records",
                      "metrics", "sessions", "all"):
            with self.subTest(check=check):
                proc = self._run(check)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_missing_records_is_explained_not_an_error(self):
        proc = self._run("records")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("encara no n'hi ha cap", proc.stdout)

    def test_a_profile_that_does_not_exist_fails_cleanly(self):
        import subprocess
        import sys as _sys
        proc = subprocess.run(
            [_sys.executable, str(REPO_ROOT / "scripts" / "flowed-check.py"),
             "all", "--dir", str(self.tmp / "nope")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no existeix", proc.stderr)
