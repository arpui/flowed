#!/usr/bin/env python3
"""Local text-to-speech: the wiring, not the synthesis.

The audio itself is covered by `server/test/tts.test.ts` (what gets spoken,
the cache, refusing to guess a voice). What these checks protect is the
property that makes the feature safe to ship half-installed: **off by default,
and invisible when off**. A 🔊 button that fails is worse than no button, and a
server that will not start because a voice is missing is far worse than silence.
"""
import json
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TtsConfigTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((REPO_ROOT / "config" / "fluent.json").read_text())

    def test_the_block_exists(self):
        self.assertIn("tts", self.config, "config/fluent.json has no tts block")

    def test_enabled_never_means_enabled_without_a_voice(self):
        # config/fluent.json is a working file: scripts/fluent-tts.sh flips
        # `enabled` when it installs a voice, so asserting it is False would
        # fail on any machine that actually has audio. The invariant that
        # matters is the one that prevents buttons which 503 on every click:
        # enabled implies at least one voice, and every voice file exists.
        tts = self.config["tts"]
        if not tts.get("enabled"):
            return
        voices = tts.get("voices") or {}
        self.assertTrue(voices, "tts.enabled is true but no voice is configured")
        # Whether the .onnx is actually on THIS disk is machine state, not a
        # repository invariant — `scripts/fluent-check.py tts <perfil>` reports
        # that, and the server refuses with 503 rather than guessing a voice.

    def test_it_carries_the_limits(self):
        tts = self.config["tts"]
        self.assertGreater(tts["cache_max_mb"], 0)
        self.assertGreater(tts["timeout_ms"], 0)


class TtsScriptTest(unittest.TestCase):
    script = REPO_ROOT / "scripts" / "fluent-tts.sh"

    def test_it_exists_and_is_executable(self):
        self.assertTrue(self.script.exists())
        self.assertTrue(self.script.stat().st_mode & 0o111, "not executable")

    def test_it_parses(self):
        r = subprocess.run(["bash", "-n", str(self.script)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_status_runs_on_a_machine_with_nothing_installed(self):
        r = subprocess.run(["bash", str(self.script), "status"],
                           capture_output=True, text=True, cwd=REPO_ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("binary", r.stdout)

    def test_an_unknown_command_fails_loudly(self):
        r = subprocess.run(["bash", str(self.script), "frobnicate"],
                           capture_output=True, text=True, cwd=REPO_ROOT)
        self.assertNotEqual(r.returncode, 0)


class TtsServerSurfaceTest(unittest.TestCase):
    def setUp(self):
        self.http = (REPO_ROOT / "server" / "src" / "http.ts").read_text()
        self.tts = (REPO_ROOT / "server" / "src" / "tts.ts").read_text()

    def test_the_two_endpoints_exist(self):
        self.assertIn('/api/fluent/tts-state', self.http)
        self.assertIn('/api/fluent/say', self.http)

    def test_only_the_target_language_is_read_aloud(self):
        self.assertIn("readTargetLanguage", self.http)
        self.assertIn("target_language", self.http)

    def test_the_learners_sentence_never_becomes_a_command(self):
        # piper is spawned with an argument array and the text goes on stdin.
        self.assertIn('spawn(config.binary, ["--model"', self.tts)
        self.assertNotIn("exec(", self.tts)
        self.assertNotIn("shell: true", self.tts)

    def test_it_does_not_compete_for_the_gpu(self):
        # A GPU flag here would put TTS in contention with the deep model,
        # which is the scarce resource on both machines.
        self.assertNotIn("--cuda", self.tts)


class LessonPlanTest(unittest.TestCase):
    """The Lesson is a plan, not a running total.

    Reported live: five exercises done, switch to Speaking, come back — the
    tutor restarted at exercise 1, and finishing that repeat marked the lesson
    6/6 with the sixth question never asked.
    """

    def setUp(self):
        self.agent = (REPO_ROOT / "server" / "src" / "agent.ts").read_text()
        self.daily = (REPO_ROOT / "server" / "src" / "daily.ts").read_text()
        self.review_skill = (REPO_ROOT / "skills" / "fluent-review" / "SKILL.md").read_text()
        # The note itself is Bun-free and lives in pacing.ts, so it can be run
        # for real by server/test/lesson-note.test.ts instead of grepped.
        self.pacing = (REPO_ROOT / "server" / "src" / "pacing.ts").read_text()

    def test_the_plan_is_persisted(self):
        self.assertIn("readPlan", self.daily)
        self.assertIn("writePlan", self.daily)
        self.assertIn("lesson-", self.daily)

    def test_the_total_is_frozen_once_a_day(self):
        # lessonPlan() returns the stored plan when there is one; only a day
        # with no plan computes a fresh total.
        body = self.agent.split("lessonPlan(): LessonPlan {")[1][:400]
        self.assertIn("if (existing) return existing", body)

    def test_coming_back_continues_instead_of_restarting(self):
        # The wording moved: the note used to ORDER the tutor to continue
        # ("This is a CONTINUATION ... Present exercise N of M now, and nothing
        # else"), which out-ranked the command's own instructions and, once the
        # counter froze, repeated itself unchanged for twenty-five turns. It now
        # states the progress and lets the skill run the exercise.
        self.assertIn("Lesson progress: ${lesson.done} of ${lesson.total} done", self.pacing)
        self.assertIn("continue it rather than starting it again", self.pacing)
        self.assertIn("lessonNote(", self.agent)
        self.assertIn("this.lessonPlan().covered", self.agent)

    def test_the_note_never_dictates_which_exercise_to_present(self):
        # The exact sentence that pinned the tutor in place. It must not come
        # back in any form: the server says where the lesson is, never what to
        # ask next.
        emitted = "\n".join(
            l
            for l in (self.agent + "\n" + self.pacing).splitlines()
            if not l.lstrip().startswith("//") and not l.lstrip().startswith("*")
        )
        self.assertNotIn("and nothing else", emitted)
        self.assertNotIn("Present exercise", emitted)
        self.assertNotIn("CONTINUATION, not a new lesson", emitted)

    def test_a_stalled_lesson_is_reported(self):
        # An unchanging note means the lesson is not advancing. On 2026-09-16
        # that state lasted twenty-five turns and surfaced nowhere.
        self.assertIn("noteStall", self.agent)
        self.assertIn("has not changed in 4 turns", self.agent)

    def test_a_repeated_exercise_is_reported(self):
        self.assertIn("lastAsked", self.agent)
        self.assertIn("same exercise twice in a row", self.agent)

    def test_progress_is_credited_against_the_plan(self):
        self.assertIn("plan.done < plan.total", self.agent)

    def test_a_finished_lesson_tells_the_tutor_to_stop(self):
        # Observed live: the lesson total was 6 and the tutor was on
        # "Exercise 8", still going. Once the count ran out it received no
        # instruction at all, so it simply carried on for ever.
        self.assertIn("lesson is COMPLETE", self.agent)
        self.assertIn("Do NOT present another exercise", self.agent)

    def test_the_lesson_does_not_repeat_one_shape_for_ever(self):
        # Every exercise came out as "Rewrite this sentence correctly". Varying
        # the shape is the skill's job now — one voice, one place — and the
        # server contributes what the skill cannot know: what was already asked
        # today and what was asked last turn.
        self.assertIn("vary the exercise", self.review_skill.lower())
        self.assertIn("Already answered correctly today", self.pacing)
        self.assertIn("Your previous exercise was", self.pacing)

    def test_the_counter_accepts_structured_evidence(self):
        # Measured: four fluent_record_answer calls, no "Score: N/10" in the
        # text, counter stuck at 0 of 12 while thirteen exercises were answered.
        self.assertIn("recordsBefore", self.agent)
        body = self.agent.split("const gradedNow =")[1][:260]
        self.assertIn("countGradedInText", body)
        self.assertIn("recordCount(sessionId) > recordsBefore", body)

    def test_free_play_has_no_hidden_ceiling(self):
        # Agreed design: the Lesson ends, the day does not. A session stop at 12
        # would contradict what the learner is shown.
        self.assertIn('mode === "hard"', self.agent)


class TtsWebSurfaceTest(unittest.TestCase):
    def setUp(self):
        self.app = (REPO_ROOT / "web" / "app.js").read_text()
        self.index = (REPO_ROOT / "web" / "index.html").read_text()
        self.css = (REPO_ROOT / "web" / "style.css").read_text()

    def test_the_ui_asks_before_drawing_anything(self):
        self.assertIn("tts-state", self.app)
        self.assertIn("ttsReady", self.app)

    def test_no_voice_means_no_button(self):
        # paintSpeakers and the exercise-card button are both behind ttsReady.
        self.assertIn("if (!ttsReady", self.app)
        self.assertIn("if (ttsReady)", self.app)

    def test_the_exercise_card_has_one(self):
        self.assertIn('id="ex-speak"', self.index)
        self.assertIn("hidden", self.index.split('id="ex-speak"')[1][:200])

    def test_the_button_is_styled(self):
        self.assertIn(".speak", self.css)

    def test_only_known_target_language_text_gets_a_speaker(self):
        # Putting a speaker on the whole exercise looks obvious and is wrong:
        # "Translate into English: Ahir vaig anar al mercat" is Catalan, and an
        # English voice reading it teaches the opposite of what the exercise is
        # for. Two sources only: the tutor's [[say]] marker, and the corrected
        # sentence (target language by definition).
        self.assertIn("SAY_RE", self.app)
        self.assertIn("fb-correct", self.app)
        self.assertIn("data-say", self.app)

    def test_the_marker_is_never_shown_to_the_learner(self):
        # markSayable runs inside renderTutorText, which is the single renderer
        # for tutor text — so the strip happens whether or not a voice exists.
        body = self.app.split("function renderTutorText")[1][:300]
        self.assertIn("markSayable", body)

    def test_the_tutor_is_told_about_the_marker(self):
        rules = (REPO_ROOT / "prompts" / "agents" / "rules.md").read_text()
        self.assertIn("[[say]]", rules)
        self.assertIn("TARGET language", rules)

    def test_the_dead_exercise_card_is_not_the_only_place(self):
        # The first version wired the speaker to #exercise-card, which has been
        # switched off since before the audio existed: the button was never
        # drawn once. paintSpeakers must not depend on it.
        painter = self.app.split("function paintSpeakers")[1][:600]
        self.assertNotIn("exercise-card", painter)
        self.assertNotIn("ex-speak", painter)


if __name__ == "__main__":
    unittest.main()
