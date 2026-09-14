#!/usr/bin/env python3
"""Onboarding belongs to the admin, not to the learner.

/fluent-setup used to be a form the learner filled in mid-lesson — the web app
auto-started it whenever `preferences.setup_complete` was false. Who someone is
and how their sessions are paced is the system owner's call, so the write now
also exists as a deterministic CLI (`scripts/fluent-profile.py`) and the app
shows a notice instead of the interview.

These checks cover the CLI's validation (a wrong CEFR level must not reach the
profile) and the two UI facts that make the change real.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "fluent-profile.py"
TEMPLATE = REPO_ROOT / "data-examples" / "learner-profile-template.json"


class FluentProfileCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.profile_dir = self.home / ".fluent" / "demo-en"
        self.profile_dir.mkdir(parents=True)
        self.profile = self.profile_dir / "learner-profile.json"
        self.profile.write_text(TEMPLATE.read_text())
        self.addCleanup(self.tmp.cleanup)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "demo-en", *args],
            capture_output=True, text=True, cwd=REPO_ROOT,
            env={"HOME": str(self.home), "PATH": "/usr/bin:/bin"},
        )

    def read(self):
        return json.loads(self.profile.read_text())

    def test_a_full_setup_completes_the_profile(self):
        r = self.run_cli("--name", "Nes", "--native", "Catalan", "--target", "English",
                         "--level", "A2", "--goal", "B1", "--minutes", "20")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = self.read()
        self.assertEqual(data["learner"]["name"], "Nes")
        self.assertEqual(data["learner"]["current_level"], "A2")
        self.assertEqual(data["learner"]["daily_goal_minutes"], 20)
        self.assertTrue(data["preferences"]["setup_complete"],
                        "a complete profile must stop the app asking")

    def test_template_placeholders_never_survive(self):
        self.run_cli("--name", "Nes", "--native", "Catalan", "--target", "English",
                     "--level", "A2", "--goal", "B1")
        blob = json.dumps(self.read())
        self.assertNotIn('"{', blob, "a {PLACEHOLDER} reached a real profile")

    def test_pacing_preferences_are_admin_settable(self):
        self.run_cli("--name", "Nes", "--native", "Catalan", "--target", "English",
                     "--level", "A2", "--goal", "B1")
        r = self.run_cli("--daily-goal", "8", "--stop", "hard", "--review-gate", "off")
        self.assertEqual(r.returncode, 0, r.stderr)
        prefs = self.read()["preferences"]
        self.assertEqual(prefs["daily_goal"], 8)
        # One name, not two: session_length was the old spelling and the
        # concept moved from "a session" to "a day".
        self.assertNotIn("session_length", prefs)
        self.assertEqual(prefs["session_stop"], "hard")
        self.assertIs(prefs["review_gate"], False)

    def test_the_old_flag_still_works(self):
        self.run_cli("--name", "Nes", "--native", "Catalan", "--target", "English",
                     "--level", "A2", "--goal", "B1")
        self.run_cli("--session-length", "9")
        self.assertEqual(self.read()["preferences"]["daily_goal"], 9)

    def test_a_bad_level_is_refused_and_writes_nothing(self):
        before = self.profile.read_text()
        r = self.run_cli("--level", "Z9")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("A1", r.stderr + r.stdout)
        self.assertEqual(self.profile.read_text(), before)

    def test_the_same_language_twice_is_refused(self):
        r = self.run_cli("--native", "English", "--target", "English")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(json.loads(TEMPLATE.read_text()), self.read())

    def test_a_missing_profile_points_at_new_user(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "nope-en", "--show"],
            capture_output=True, text=True, cwd=REPO_ROOT,
            env={"HOME": str(self.home), "PATH": "/usr/bin:/bin"},
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("new-user.sh", r.stderr + r.stdout)

    def test_every_write_leaves_a_backup(self):
        self.run_cli("--name", "Nes", "--native", "Catalan", "--target", "English",
                     "--level", "A2", "--goal", "B1")
        self.assertTrue(list(self.profile_dir.glob("learner-profile.json.backup-*")))


class LearnerFacingSurfaceTest(unittest.TestCase):
    """What the learner can reach from the app."""

    def setUp(self):
        self.app_js = (REPO_ROOT / "web" / "app.js").read_text()
        self.index = (REPO_ROOT / "web" / "index.html").read_text()

    def test_the_app_never_auto_starts_the_setup_interview(self):
        # The name may still appear (the renderer maps it to "l'administrador");
        # what must not exist is a code path that RUNS it.
        import re
        for match in re.findall(r'runCommand\(([^)]*)\)', self.app_js):
            self.assertNotIn("setup", match, f"web/app.js runs the setup command: {match}")
        self.assertNotIn('return "fluent-setup"', self.app_js,
                         "initialCommand() still routes the learner into onboarding")

    def test_an_unconfigured_profile_gets_a_notice(self):
        self.assertIn("showSetupNotice", self.app_js)
        self.assertIn("administrador", self.app_js)

    def test_finishing_a_session_is_a_button(self):
        self.assertIn('data-cmd="fluent-end"', self.index,
                      "the learner must be able to close the session themselves")

    def test_setup_is_not_a_button(self):
        self.assertNotIn('data-cmd="fluent-setup"', self.index)

    def test_the_lesson_badge_and_the_day_counter_exist(self):
        # Two separate things, which is the whole point: the Lesson HAS an end
        # (badge counts down), the day's effort does not (count plus a face).
        self.assertIn("renderLessonBadge", self.app_js)
        self.assertIn("pace-face", self.app_js)

    def test_the_lesson_button_never_disables_anything(self):
        # Agreed design: nothing is blocked. The badge says what is owed.
        self.assertNotIn("lessonBtn.disabled", self.app_js)

    def test_the_count_is_the_days_not_the_session(self):
        # Closing the tab at lunchtime must not reset the afternoon to zero.
        self.assertNotIn("renderPace(null); // new session", self.app_js)

    def test_no_prompt_tells_the_learner_to_type_a_command(self):
        # The learner has buttons and no command line. A skill printing
        # "/fluent-vocab" is advice they cannot act on. Only the model-facing
        # notes about *triggering* may name a command; anything inside a
        # ```markdown block is shown to the learner verbatim.
        import re
        root = REPO_ROOT / "skills"
        offenders = []
        for skill in sorted(root.glob("*/SKILL.md")):
            for block in re.findall(r"```markdown\n(.*?)```", skill.read_text(), re.S):
                if re.search(r"/fluent-[a-z]+", block):
                    offenders.append(skill.parent.name)
        self.assertEqual(offenders, [],
                         f"these skills print a slash command to the learner: {offenders}")

    def test_a_finished_session_is_not_resumed(self):
        # Closing the browser does nothing server-side. Resuming blindly landed
        # the learner back in a finalized session that kept growing past the
        # model's context window.
        self.assertIn("session-state", self.app_js)
        self.assertIn("resumable", self.app_js)

    def test_the_renderer_rewrites_commands_anyway(self):
        # Belt and braces: the model improvises, the renderer does not.
        self.assertIn("humanizeCommands", self.app_js)
        self.assertIn("BUTTON_NAMES", self.app_js)


class SessionAnalyzerRemovedTest(unittest.TestCase):
    """fluent-session-analyzer duplicated read-db.py from prose files, worse.

    Planning reads the JSON databases; the results/*.md files stay as the
    human-readable record. A stale reference would send the tutor looking for a
    skill that is not there and burn a turn on the miss.
    """

    def test_the_skill_is_gone(self):
        self.assertFalse((REPO_ROOT / "skills" / "fluent-session-analyzer").exists())

    def test_nothing_live_still_points_at_it(self):
        live = [
            *(REPO_ROOT / "skills").glob("*/SKILL.md"),
            *(REPO_ROOT / "references").glob("*.md"),
            *(REPO_ROOT / "prompts").rglob("*.md"),
            REPO_ROOT / "README.md",
            REPO_ROOT / "CLAUDE.md",
            REPO_ROOT / "AGENTS.md",
        ]
        for path in live:
            if not path.exists():
                continue
            self.assertNotIn("session-analyzer", path.read_text(),
                             f"{path.relative_to(REPO_ROOT)} still references the removed skill")


if __name__ == "__main__":
    unittest.main()
