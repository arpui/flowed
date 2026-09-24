#!/usr/bin/env python3
"""The skill reaches the model, on every turn, without the model's help.

The failure this guards against, in full, because it cost two children a whole
lesson and looked from the outside like the app was broken:

Every session opens with an automatic `/fluent-learn`. When the learner then
pressed 🎓 Lesson, `/fluent-review` arrived as the SECOND command of the
session. Its first line said "Load the `fluent-review` skill via the skill tool
and follow it EXACTLY" — and the model, already mid-practice with a working
pattern in front of it, did not. Measured on 2026-09-16: the `skill` tool was
called exactly once per session, always on the first command, never again.

Everything else followed from that one miss, because the entire grading
contract — the 🔴/🟡/🟢 marker, `**Corrections:**`, `**Correct version:**`,
`**Score: N/10**` — lives only in `skills/fluent-review/SKILL.md`:

  no skill  ->  no correction shown        (60 turns, zero corrections)
            ->  no "Score: N/10" in text   (creditTurn returned early)
            ->  plan.done frozen at 0      (13 exercises answered, 0 of 12 shown)
            ->  the pacing note unchanging (identical instruction, 25 turns)
            ->  the same exercise, for ever

So the server loads it and pins it to the SYSTEM prompt. Not the history: the
history is pruned when the context fills, and the grading contract must be the
one thing that cannot be dropped.
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS = sorted((REPO_ROOT / "prompts" / "commands").glob("fluent-*.md"))


class CommandsDoNotAskTheModelToLoadSkills(unittest.TestCase):
    def test_no_command_delegates_the_load_to_the_model(self):
        offenders = [c.name for c in COMMANDS if "via the skill tool" in c.read_text()]
        self.assertEqual([], offenders)

    def test_each_command_with_a_skill_points_at_the_system_prompt(self):
        for cmd in COMMANDS:
            name = cmd.stem
            if not (REPO_ROOT / "skills" / name / "SKILL.md").exists():
                continue
            with self.subTest(command=name):
                self.assertIn("already in your system prompt", cmd.read_text())


class TheServerLoadsIt(unittest.TestCase):
    def setUp(self):
        self.commands = (REPO_ROOT / "server" / "src" / "commands.ts").read_text()
        self.agent = (REPO_ROOT / "server" / "src" / "agent.ts").read_text()

    def test_the_loader_resolves_the_skill_beside_the_command(self):
        self.assertIn("export function loadSkill", self.commands)
        self.assertIn('path.join(root, "skills", name, "SKILL.md")', self.commands)
        self.assertIn("loadSkill(opts.root, command, opts.dataDir)", self.commands)

    def test_it_follows_the_declared_skill_chain(self):
        # "Use the `fluent-feedback-formatter` skill for per-answer feedback" is
        # one more hop the model will not take, and the feedback template — the
        # grading contract — is in that second file. `requires:` makes the
        # dependency explicit and the server follows it.
        self.assertIn("requiredSkills(main)", self.commands)
        for name in ("fluent-review", "fluent-learn", "fluent-vocab",
                     "fluent-writing", "fluent-speaking"):
            with self.subTest(skill=name):
                body = (REPO_ROOT / "skills" / name / "SKILL.md").read_text()
                self.assertIn("requires: [fluent-feedback-formatter]", body)

    def test_the_skill_is_rendered_for_the_model_not_shipped_raw(self):
        # The file a person maintains is not the prompt a 14B should read.
        self.assertIn("renderSkillForModel", self.commands)
        pacing = (REPO_ROOT / "server" / "src" / "pacing.ts").read_text()
        self.assertIn("export function renderSkillForModel", pacing)

    def test_it_is_pinned_to_the_system_prompt_not_the_history(self):
        body = self.agent.split("private buildSystemPrompt")[1].split("// ---- history")[0]
        self.assertIn("this.activeSkill.get(sessionId)", body)
        self.assertIn("skillBlock(", body)
        pacing = (REPO_ROOT / "server" / "src" / "pacing.ts").read_text()
        self.assertIn("<skill_content", pacing)

    def test_every_turn_gets_it_not_only_the_command_turn(self):
        # runMessage is the ordinary answer turn. If it built the system prompt
        # without the session, the skill would be present on the press of the
        # button and gone for every answer after it.
        self.assertEqual(2, self.agent.count("this.buildSystemPrompt(agent, sessionId)"))
        self.assertNotIn("this.buildSystemPrompt(agent)", self.agent)

    def test_the_state_block_is_not_re_injected_every_command(self):
        # `skipDirectives` was declared on loadCommand and never forwarded to
        # expandDirectives, so read-db.py re-ran and re-printed the whole
        # learner state on the second and third command: +2.8k tokens a press.
        self.assertIn("skip: opts.skipDirectives", self.commands)


class TheGradingContractHasOneHome(unittest.TestCase):
    def setUp(self):
        self.skill = (REPO_ROOT / "skills" / "fluent-review" / "SKILL.md").read_text()

    def test_the_review_skill_states_it(self):
        for token in ("**Correct version:**", "Score: ", "fluent_record_answer"):
            with self.subTest(token=token):
                self.assertIn(token, self.skill)

    def test_text_and_tool_call_are_not_alternatives(self):
        # Iona's tutor called the tool four times and wrote no feedback at all:
        # the corrections existed, in JSON, and she never saw one.
        self.assertIn("Every answer gets BOTH", self.skill)


class TheIncidentIsReplayed(unittest.TestCase):
    """The regression harness runs the real functions on the real strings.

    `server/test/lesson-note.test.ts` feeds the verbatim tutor turns of
    2026-09-16 through `lessonNote`, `skillBlock`, `exerciseFingerprints`,
    `countGradedInText` and `loadCommand`. It is executed by
    `test_server_stream.py` with `node --experimental-strip-types`, so it is a
    real run, not a grep. This check only guarantees it cannot be dropped.
    """

    def test_the_replay_harness_exists_and_is_wired_in(self):
        harness = REPO_ROOT / "server" / "test" / "lesson-note.test.ts"
        self.assertTrue(harness.exists())
        body = harness.read_text()
        for token in ("lessonNote", "skillBlock", "loadSkill", "loadCommand",
                      "exerciseFingerprints", "countGradedInText"):
            with self.subTest(token=token):
                self.assertIn(token, body)

    def test_it_uses_the_real_failing_strings(self):
        body = (REPO_ROOT / "server" / "test" / "lesson-note.test.ts").read_text()
        # Verbatim from sessions.db and .daily/lesson-2026-09-16.json.
        self.assertIn("**Word (Catalan):** l'anglès", body)
        self.assertIn("my sister runs today", body)
        self.assertIn("Spaced Review (Critical)", body)


if __name__ == "__main__":
    unittest.main()
