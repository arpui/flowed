#!/usr/bin/env python3
"""The curriculum reader and the learner path: rules, not the model.

The point is that the path is DERIVED from stored facts (answers, checkpoints),
so every rule here can be checked with a handful of invented answers.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "hooks"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import curriculum as cu  # noqa: E402

CUR = cu.load_curriculum(REPO_ROOT / "curriculum" / "en-A2.md")
CORE = [c["id"] for c in CUR["competencies"] if c["core"]]

# The mechanical rules are tested with small numbers (5 answers, window 6) on a copy of
# the curriculum where no competence declares a depth and every one weighs 1; what each
# depth asks for has its own tests (DepthTest). No depth, not "normal": since
# 2026-09-24 cfg_for() lays DEPTH["normal"] over any cfg for a "normal" competence
# (the fix that made normal really need 20 answers), so a copy marked "normal" could
# no longer be tested with OLD's small numbers at all.
import copy  # noqa: E402
OLD = dict(cu.CFG, window=6, min_answers=5, min_span_days=4, stalled_answers=20)
CUR_N = copy.deepcopy(CUR)
for _c in CUR_N["competencies"]:
    _c["depth"], _c["weight"] = None, 1


def days(start: int, n: int, ok=1):
    return [[f"2026-09-{start + i:02d}", ok] for i in range(n)]


class ParseTest(unittest.TestCase):
    def test_the_real_file_is_valid(self):
        self.assertEqual(cu.validate_curriculum(CUR), [])
        self.assertEqual(len(CUR["competencies"]), 19)
        self.assertEqual(len(CORE), 16)
        self.assertEqual(CUR["meta"]["pass_mark"], 80)

    def test_check_splits_on_first_colon_and_last_arrow(self):
        c = cu._parse_check("- Ask: Ask politely: how to get there → Excuse me, how do I get there? / Could you tell me?")
        self.assertEqual(c["type"], "Ask")
        self.assertEqual(c["prompt"], "Ask politely: how to get there")
        self.assertEqual(c["alternatives"], ["Excuse me, how do I get there?", "Could you tell me?"])

    def test_sections_and_retired(self):
        sections = {c["section"] for c in CUR["competencies"]}
        self.assertEqual(sections, {"Gramàtica", "Funcions", "Vocabulari"})
        self.assertTrue(any("a2.restaurant" in r for r in CUR["retired"]))
        shop = next(c for c in CUR["competencies"] if c["id"] == "a2.shopping_restaurant")
        self.assertEqual(shop["replaces"], ["a2.restaurant"])

    def test_no_check_depends_on_the_native_language(self):
        for c in CUR["competencies"]:
            for k in c["checks"]:
                self.assertNotIn("CA->EN", k["type"])
                self.assertNotEqual(k["type"], "Translate")

    def test_validator_catches_problems(self):
        bad = cu.parse_curriculum(
            "---\nlanguage: X\nlevel: A2\nversion: 1\npass_mark: 80\ncarry_mark: 90\ncheckpoint_items: 1\n---\n"
            "## G\n### a.x — X [core]\nRequires: a.nope\nCheck:\n- Complete: a ___ → b\n")
        joined = " ".join(cu.validate_curriculum(bad))
        self.assertIn("Requires desconegut", joined)
        self.assertIn("n'hi ha de ser 3", joined)
        self.assertIn("carry_mark", joined)


class StateTest(unittest.TestCase):
    def test_ladder(self):
        self.assertEqual(cu.competence_state([]), "unseen")
        self.assertEqual(cu.competence_state(days(1, 2)), "introduced")
        self.assertEqual(cu.competence_state(days(1, 3)), "practicing")

    def test_one_sitting_is_not_consolidation(self):
        one_day = [["2026-09-01", 1]] * 8
        self.assertEqual(cu.competence_state(one_day, OLD), "practicing")
        self.assertEqual(cu.competence_state(days(1, 6), OLD), "consolidated")

    def test_two_misses_in_a_row_reopen(self):
        a = days(1, 8) + [["2026-09-10", 0], ["2026-09-11", 0]]
        self.assertEqual(cu.competence_state(a, OLD), "practicing")

    def test_mastered_needs_span_and_streak(self):
        a = [["2026-09-01", 1]] * 3 + [["2026-09-15", 1], ["2026-09-22", 0], ["2026-09-23", 1]]
        self.assertEqual(cu.competence_state(a, OLD), "consolidated")          # a miss inside the last four
        a = a + [[f"2026-09-{d}", 1] for d in (24, 25, 26, 27)]
        self.assertEqual(cu.competence_state(a, OLD), "mastered")
        short = [["2026-09-10", 1]] * 3 + [[f"2026-09-{d}", 1] for d in (12, 13, 14, 15)]
        self.assertEqual(cu.competence_state(short, OLD), "consolidated")      # streak but not 21 days

    def test_progress_is_the_share_of_core_and_replays_any_day(self):
        path = cu.new_path(CUR)
        for cid in CORE[:8]:
            for a in days(1, 6):
                cu.record_answer(path, cid, bool(a[1]), a[0])
        self.assertAlmostEqual(cu.progress(cu.summarize(CUR_N, path, None, OLD))["pct"], 50.0)
        early = cu.progress(cu.summarize(CUR_N, path, "2026-09-02", OLD))["pct"]
        self.assertLess(early, 20.0)

    def test_extras_do_not_count(self):
        path = cu.new_path(CUR)
        for a in days(1, 6):
            cu.record_answer(path, "a2.vocab_clothes", True, a[0])
        self.assertEqual(cu.progress(cu.summarize(CUR_N, path, None, OLD))["pct"], 0.0)


class SlotsTest(unittest.TestCase):
    def test_start_is_one_per_section_in_file_order(self):
        rows = cu.summarize(CUR, cu.new_path(CUR))
        self.assertEqual(cu.active_competences(rows, cu.new_path(CUR)),
                         ["a2.present_simple_vs_continuous", "a2.directions", "a2.vocab_food_and_drink"])

    def test_started_competence_leaves_the_slot_and_joins_the_review_pool(self):
        path = cu.new_path(CUR)
        for a in days(1, 3):
            cu.record_answer(path, "a2.present_simple_vs_continuous", True, a[0])
        rows = cu.summarize(CUR, path)
        self.assertEqual(cu.active_competences(rows, path)[0], "a2.pronouns_possessives")
        self.assertIn("a2.present_simple_vs_continuous", cu.review_pool(rows))

    def test_extra_only_when_no_core_is_left_in_the_section(self):
        path = cu.new_path(CUR)
        for cid in [c["id"] for c in CUR["competencies"] if c["section"] == "Vocabulari" and c["core"]]:
            for a in days(1, 3):
                cu.record_answer(path, cid, True, a[0])
        vocab = [i for i in cu.active_competences(cu.summarize(CUR, path), path) if "vocab" in i]
        self.assertEqual(vocab, ["a2.vocab_travel_transport"])


class CheckpointTest(unittest.TestCase):
    def _ready_path(self, share_done=0):
        path = cu.new_path(CUR)
        for i, cid in enumerate(CORE):
            n = 6 if i < share_done else 3
            for a in days(1, n):
                cu.record_answer(path, cid, True, a[0])
        return path

    def test_ready_needs_every_core_started(self):
        path = self._ready_path()
        self.assertTrue(cu.checkpoint_ready(cu.summarize(CUR_N, path, None, OLD)))
        del path["competencies"][CORE[0]]
        self.assertFalse(cu.checkpoint_ready(cu.summarize(CUR_N, path, None, OLD)))

    def test_ready_share_can_be_set_in_the_level_file(self):
        self.assertTrue(0 <= CUR["meta"]["ready_share"] <= 100)  # the file's own value: Albert edits it
        CUR_N["meta"]["ready_share"] = 0
        cur = copy.deepcopy(CUR_N)
        cur["meta"]["ready_share"] = 50
        # validated on the real file: CUR_N has no depths on purpose, which the validator rightly refuses
        real = copy.deepcopy(CUR)
        real["meta"]["ready_share"] = 50
        self.assertEqual(cu.validate_curriculum(real), [])
        rows = cu.summarize(cur, self._ready_path(share_done=4), None, OLD)
        self.assertFalse(cu.checkpoint_ready(rows, OLD, cur))       # the file asks for 50%: 4 of 16 is not enough
        self.assertTrue(cu.checkpoint_ready(rows, OLD, CUR_N))      # the file says nothing: CFG's 0
        cur["meta"]["ready_share"] = 150
        self.assertTrue(any("ready_share" in e for e in cu.validate_curriculum(cur)))

    def test_ready_share_asks_for_consolidation(self):
        rows = cu.summarize(CUR_N, self._ready_path(share_done=4), None, OLD)
        self.assertFalse(cu.checkpoint_ready(rows, dict(cu.CFG, ready_share=0.5)))
        rows = cu.summarize(CUR_N, self._ready_path(share_done=8), None, OLD)
        self.assertTrue(cu.checkpoint_ready(rows, dict(cu.CFG, ready_share=0.5)))

    def test_plan_has_one_item_per_core_and_the_rest_on_the_weakest(self):
        path = self._ready_path()
        for a in days(10, 3, ok=0):
            cu.record_answer(path, CORE[5], False, a[0])
        plan = cu.checkpoint_plan(CUR, cu.summarize(CUR_N, path, None, OLD))
        self.assertEqual(len(plan), CUR["meta"]["checkpoint_items"])
        for cid in CORE:
            self.assertGreaterEqual(plan.count(cid), 1)
        self.assertGreater(plan.count(CORE[5]), 1)

    def _results(self, wrong):
        plan = list(CORE) + CORE[:8]
        return [(cid, i >= wrong) for i, cid in enumerate(plan)]

    def test_pass_carry_stay(self):
        stays = 0
        self.assertEqual(cu.checkpoint_result(CUR, self._results(4), stays)["result"], "pass")     # 20/24 = 83 %
        self.assertEqual(cu.checkpoint_result(CUR, self._results(6), stays)["result"], "carry")    # 18/24 = 75 %
        self.assertEqual(cu.checkpoint_result(CUR, self._results(10), stays)["result"], "stay")    # 14/24 = 58 %

    def test_teacher_decides_after_two_repetitions(self):
        path = cu.new_path(CUR)
        outcomes = [cu.apply_checkpoint(CUR, path, f"2026-09-{d:02d}", self._results(10))["result"] for d in (5, 10, 15)]
        self.assertEqual(outcomes, ["stay", "stay", "teacher"])           # attempt + 2 repetitions
        self.assertEqual(path["promotions"], [])

    def test_pass_and_carry_promote_and_carry_keeps_the_weak_open(self):
        path = cu.new_path(CUR)
        res = cu.apply_checkpoint(CUR, path, "2026-09-20", self._results(6))
        self.assertEqual(res["result"], "carry")
        self.assertEqual(path["promotions"][0]["achieved"], "A2")
        self.assertEqual(path["carried"], res["weak"])
        self.assertTrue(res["weak"])

    def test_a_failed_checkpoint_sends_the_weak_ones_to_reinforcement(self):
        path = cu.new_path(CUR)
        res = cu.apply_checkpoint(CUR, path, "2026-09-20", self._results(10))
        self.assertEqual(path["reinforce"], res["weak"])
        rows = cu.summarize(CUR_N, path, None, OLD)
        self.assertEqual(cu.active_competences(rows, path), res["weak"][:3])


class StorageAndSimTest(unittest.TestCase):
    def test_save_load_roundtrip_is_compact(self):
        with tempfile.TemporaryDirectory() as d:
            path = cu.new_path(CUR)
            cu.record_answer(path, CORE[0], True, "2026-09-21")
            cu.save_path(d, path)
            text = cu.path_file(d).read_text(encoding="utf-8")
            self.assertIn('["2026-09-21",1]', text)
            self.assertEqual(json.loads(text), path)
            self.assertEqual(cu.load_path(d, CUR), path)

    def test_answers_are_capped(self):
        path = cu.new_path(CUR)
        for i in range(300):
            cu.record_answer(path, CORE[0], True, "2026-09-21")
        self.assertEqual(len(path["competencies"][CORE[0]]["answers"]), cu.CFG["keep_answers"])

    def test_reports_render(self):
        path = cu.new_path(CUR)
        for cid in CORE[:3]:
            for a in days(1, 6):
                cu.record_answer(path, cid, True, a[0])
        text = cu.render_report(CUR_N, path, "2026-09-10", admin=True, cfg=OLD)
        for needle in ("A2  ", "assolides 3/16", "GRAMÀTICA", "ADMIN", "Evolució setmanal", "ETA"):
            self.assertIn(needle, text)

    def test_simulated_student_is_deterministic_and_reaches_a_verdict(self):
        import importlib.util
        from datetime import date
        spec = importlib.util.spec_from_file_location("sim", REPO_ROOT / "scripts" / "flowed-sim-path.py")
        sim = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sim)
        p1, i1 = sim.run(CUR, "steady", 1, 60, date(2026, 9, 21), verbose=False)
        p2, i2 = sim.run(CUR, "steady", 1, 60, date(2026, 9, 21), verbose=False)
        self.assertEqual(p1, p2)
        self.assertIn(i1["result"], ("pass", "carry"))
        # every answer belongs to a competence of the file
        self.assertTrue(set(p1["competencies"]) <= {c["id"] for c in CUR["competencies"]})


def rec(item=None, skill="grammar", exercise="", answer="", score=10, corrections=None, ts=1789910071546, rid=None, **extra):
    r = {"record_id": rid or f"s:{item or exercise}:{ts}", "session_id": "s", "ts": ts, "skill": skill,
         "exercise": exercise, "learner_answer": answer, "score": score, "corrections": corrections or []}
    if item:
        r["item_id"] = item
    r.update(extra)
    return r


class TaggingTest(unittest.TestCase):
    def tag(self, **kw):
        return cu.competency_of(CUR, rec(**kw))

    def test_vocabulary_goes_by_the_word_list(self):
        self.assertEqual(self.tag(item="vocabulary_bread", skill="vocabulary"), ("a2.vocab_food_and_drink", "words"))
        self.assertEqual(self.tag(item="vocabulary_window", skill="vocabulary")[0], "a2.vocab_house_and_furniture")
        # a word answered right with no queue item: the answer is the word
        self.assertEqual(self.tag(skill="vocabulary", answer="Fridge", exercise='How do you say "nevera"?')[0],
                         "a2.vocab_house_and_furniture")
        # a word that is not in any list is not forced into one
        self.assertEqual(self.tag(item="vocabulary_house", skill="vocabulary"), (None, "word-not-in-list"))

    def test_a_card_is_found_by_the_word_it_asked_even_when_the_answer_is_in_the_other_language(self):
        # measured 2026-09-21 (211700): 'cheese' -> 'formatge' never counted, so the same three words came back every day
        self.assertEqual(self.tag(skill="vocabulary", exercise="cheese", answer="formatge"), ("a2.vocab_food_and_drink", "words"))
        self.assertEqual(self.tag(skill="vocabulary", exercise="butter", answer="margarina", score=6)[0], "a2.vocab_food_and_drink")
        # a wrong answer to a Catalan-prompted card has no English word to go by: not forced into a list
        self.assertEqual(self.tag(skill="vocabulary", exercise="llit", answer="teeth"), (None, "word-not-in-list"))

    def test_a_sentence_exercise_labelled_vocabulary_is_tagged_as_grammar(self):
        self.assertEqual(self.tag(skill="vocabulary", exercise="Suggest a place to go", answer="Let's go to the cinema")[0],
                         "a2.suggestions")

    def test_words_used_come_from_the_asked_word(self):
        import datetime as dt
        ts = int(dt.datetime(2026, 9, 21, 10, 0).timestamp() * 1000)
        d = Path(tempfile.mkdtemp())
        (d / ".records").mkdir()
        recs = [rec(skill="vocabulary", exercise=w, answer="x", score=10, ts=ts + i, rid=f"v{i}")
                for i, w in enumerate(["bread", "cheese", "butter"])]
        (d / ".records" / "s.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        t = cu.next_target(CUR, d, "2026-09-22", only_vocab=True)
        for w in ("bread", "cheese", "butter"):
            self.assertNotIn(w, t["words"])

    def test_grammar_goes_by_category_then_words(self):
        self.assertEqual(self.tag(item="agreement_she_goes_to_school")[0], "a2.present_simple_vs_continuous")
        self.assertEqual(self.tag(item="tenses_i_woke_up_at_seven_yesterday",
                                  exercise='Correct: "I wake up at seven yesterday."')[0], "a2.past_simple")
        self.assertEqual(self.tag(item="tenses_she_has_lived_here_for_two_y")[0], "a2.present_perfect_experience")
        self.assertEqual(self.tag(item="prepositions_i_am_interested_in_music")[0], "a2.prepositions_time_place")

    def test_what_the_level_does_not_teach_stays_untagged(self):
        self.assertEqual(self.tag(item="articles_i_have_a_dog"), (None, "category-not-in-curriculum"))
        self.assertEqual(self.tag(item="capitalization_my_birthday_is_in_july")[0], None)
        self.assertEqual(self.tag(item="spelling_because")[0], None)

    def test_a_generic_category_with_no_word_signal_is_not_guessed(self):
        self.assertEqual(self.tag(item="grammar_two_children"), (None, "ambiguous"))

    def test_the_record_can_carry_its_own_competency(self):
        self.assertEqual(self.tag(item="articles_i_have_a_dog", competency="a2.directions"), ("a2.directions", "record"))
        self.assertEqual(self.tag(item="x", competency="a2.nope")[0], None)

    def test_correction_category_is_used_when_there_is_no_item(self):
        r = rec(exercise="Write about yesterday", answer="I go to the cinema yesterday",
                corrections=[{"wrong": "I go", "right": "I went", "category": "tenses"}], score=5)
        self.assertEqual(cu.competency_of(CUR, r)[0], "a2.past_simple")


class RebuildTest(unittest.TestCase):
    def _data(self, records):
        d = Path(tempfile.mkdtemp())
        (d / ".records").mkdir()
        (d / ".records" / "s.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        return d

    def test_rebuild_is_idempotent_and_counts_only_what_it_can_tag(self):
        day = 86400000
        base = 1789910071546
        d = self._data([
            rec(item="vocabulary_bread", skill="vocabulary", score=10, ts=base, rid="a"),
            rec(item="vocabulary_bread", skill="vocabulary", score=2, ts=base + day, rid="b"),
            rec(item="articles_i_have_a_dog", score=10, ts=base, rid="c"),
            rec(item="vocabulary_bread", skill="vocabulary", score=10, ts=base, rid="a"),   # duplicate record
        ])
        p1 = cu.rebuild_path(d, CUR)
        p2 = cu.rebuild_path(d, CUR)
        self.assertEqual(p1, p2)
        ans = p1["competencies"]["a2.vocab_food_and_drink"]["answers"]
        self.assertEqual([a[1] for a in ans], [1, 0])
        self.assertEqual(p1["tagging"]["records"], 3)
        self.assertEqual(p1["tagging"]["tagged"], 2)
        self.assertEqual(p1["tagging"]["how"]["category-not-in-curriculum"], 1)

    def test_rebuild_keeps_checkpoints_and_promotions(self):
        d = self._data([rec(item="vocabulary_bread", skill="vocabulary")])
        path = cu.new_path(CUR)
        path["checkpoints"].append({"date": "2026-09-20", "result": "stay", "weak": [], "items": 24, "correct": 10, "pct": 41.7, "level": "A2"})
        cu.save_path(d, path)
        again = cu.rebuild_path(d, CUR)
        self.assertEqual(len(again["checkpoints"]), 1)
        self.assertEqual(len(again["competencies"]["a2.vocab_food_and_drink"]["answers"]), 1)

    def test_curriculum_is_found_from_the_profile(self):
        d = Path(tempfile.mkdtemp())
        prof = {"learner": {"target_language": "English", "target_level": "A2"}}
        (d / "learner-profile.json").write_text(json.dumps(prof), encoding="utf-8")
        # the declared level is not trusted: A1 has to be certified before A2 starts
        self.assertEqual(cu.find_curriculum(REPO_ROOT, d).name, "en-A1.md")
        cu._write_json(cu.certificates_file(d), [{"language": "English", "level": "A1", "date": "2026-09-21"}])
        self.assertEqual(cu.find_curriculum(REPO_ROOT, d).name, "en-A2.md")
        # everything up to the target certified: the goal is reached, the last course stays
        cu._write_json(cu.certificates_file(d), [{"language": "English", "level": "A1"}, {"language": "English", "level": "A2"}])
        self.assertEqual(cu.find_curriculum(REPO_ROOT, d).name, "en-A2.md")
        # a target with no curriculum above it: the ones below still serve
        prof["learner"]["target_level"] = "B1"
        (d / "learner-profile.json").write_text(json.dumps(prof), encoding="utf-8")
        cu._write_json(cu.certificates_file(d), [])
        self.assertEqual(cu.find_curriculum(REPO_ROOT, d).name, "en-A1.md")
        prof["learner"]["target_language"] = "Klingon"
        (d / "learner-profile.json").write_text(json.dumps(prof), encoding="utf-8")
        self.assertIsNone(cu.find_curriculum(REPO_ROOT, d))

    def test_auto_rebuild_without_a_curriculum_does_nothing(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(cu.main(["rebuild", "--auto", "--quiet", "--data", str(d)]), 0)
        self.assertFalse(cu.path_file(d).exists())


class ForgettingCycleTest(unittest.TestCase):
    def _cons(self):
        return days(1, 6)          # consolidated on day 6 (spaced over 5 days)

    def test_not_due_before_three_days_then_due(self):
        a = self._cons()
        self.assertFalse(cu.review_due(a, "2026-09-08", OLD))     # 2 days after the last answer
        self.assertTrue(cu.review_due(a, "2026-09-09", OLD))      # 3 days

    def test_each_good_review_lengthens_the_gap(self):
        a = self._cons() + [["2026-09-09", 1]]
        self.assertFalse(cu.review_due(a, "2026-09-15", OLD))     # 6 days after: not yet 7
        self.assertTrue(cu.review_due(a, "2026-09-16", OLD))
        a += [["2026-09-16", 1]]
        self.assertFalse(cu.review_due(a, "2026-09-29", OLD))     # 13 days: not yet 14
        self.assertTrue(cu.review_due(a, "2026-09-30", OLD))

    def test_a_miss_brings_it_back_the_next_day(self):
        a = self._cons() + [["2026-09-09", 0]]
        self.assertTrue(cu.review_due(a, "2026-09-10", OLD))

    def test_only_consolidated_competences_are_maintenance(self):
        path = cu.new_path(CUR)
        for a in days(1, 3):
            cu.record_answer(path, CORE[0], True, a[0])       # practicing
        for a in days(1, 6):
            cu.record_answer(path, CORE[1], True, a[0])       # consolidated
        self.assertEqual(cu.due_maintenance(CUR_N, path, "2026-09-20", OLD), [CORE[1]])


class DepthTest(unittest.TestCase):
    """Six good answers do not prove a tense; they do prove five words."""

    def _state(self, depth, n, span=None):
        a = [[f"2026-09-{1 + (i * (span or n) // n):02d}", 1] for i in range(n)]
        return cu.competence_state(a, cu.CFG, depth)

    def test_each_depth_asks_for_its_own_evidence(self):
        # From DEPTH, not written out: the thresholds are a decision that moves
        # (8/12/20 -> 10/20/30 on 2026-09-23), the rule under test is that each
        # depth needs exactly its own number and not one fewer.
        for depth in ("light", "normal", "deep"):
            n = cu.DEPTH[depth]["min_answers"]
            with self.subTest(depth=depth, n=n):
                # over 20 days: enough spacing for every depth, not yet the 21 of "mastered"
                self.assertEqual(self._state(depth, n, span=20), "consolidated")
                self.assertEqual(self._state(depth, n - 1, span=20), "practicing")
        self.assertLess(cu.DEPTH["light"]["min_answers"], cu.DEPTH["normal"]["min_answers"])
        self.assertLess(cu.DEPTH["normal"]["min_answers"], cu.DEPTH["deep"]["min_answers"])

    def test_deep_also_needs_more_days(self):
        n = cu.DEPTH["deep"]["min_answers"]
        # enough answers, crammed into too few days: not enough spacing
        a = [[f"2026-09-{1 + i // 4:02d}", 1] for i in range(n)]
        self.assertEqual(cu.competence_state(a, cu.CFG, "deep"), "practicing")
        # the same answers spread out: the last window spans the days deep asks for
        a = [[f"2026-09-{1 + i * 20 // n:02d}", 1] for i in range(n)]
        self.assertEqual(cu.competence_state(a, cu.CFG, "deep"), "consolidated")

    def test_accuracy_still_counts(self):
        a = [[f"2026-09-{1 + i:02d}", 1 if i % 3 else 0] for i in range(20)]      # ~67 %
        self.assertEqual(cu.competence_state(a, cu.CFG, "deep"), "practicing")

    def test_the_file_declares_depth_and_weight(self):
        by = {c["id"]: c for c in CUR["competencies"]}
        self.assertEqual((by["a2.present_simple_vs_continuous"]["depth"], by["a2.present_simple_vs_continuous"]["weight"]), ("deep", 3))
        self.assertEqual(by["a2.vocab_food_and_drink"]["depth"], "light")
        self.assertTrue(all(c["depth"] in cu.DEPTH and 1 <= c["weight"] <= 3 for c in CUR["competencies"]))

    def test_every_grammar_and_function_competence_declares_signals_wider_than_its_tags(self):
        for c in CUR["competencies"]:
            if c["words"]:
                continue
            self.assertTrue(c["signals"], c["id"])
            plain = [t for t in c["tags"] if not t.startswith("#")]
            self.assertTrue(set(plain) <= set(c["signals"]) or len(c["signals"]) >= len(plain), c["id"])
        t = cu.next_target(CUR, tempfile.mkdtemp() and Path(tempfile.mkdtemp()), "2026-09-21", last_id=None)
        self.assertIn("now", t["signals"])

    def test_a_row_says_how_many_answers_it_needs(self):
        rows = {r["id"]: r for r in cu.summarize(CUR, cu.new_path(CUR))}
        self.assertEqual((rows["a2.present_simple_vs_continuous"]["need"], rows["a2.vocab_clothes"]["need"]),
                         (cu.DEPTH["deep"]["min_answers"], cu.DEPTH["light"]["min_answers"]))

    def test_weight_moves_the_bar(self):
        cur = copy.deepcopy(CUR_N)
        by = {c["id"]: c for c in cur["competencies"]}
        by[CORE[0]]["weight"] = 3
        path = cu.new_path(cur)
        for a in days(1, 6):
            cu.record_answer(path, CORE[0], True, a[0])
        heavy = cu.progress(cu.summarize(cur, path, None, OLD))["pct"]
        path2 = cu.new_path(CUR_N)
        for a in days(1, 6):
            cu.record_answer(path2, CORE[0], True, a[0])
        light = cu.progress(cu.summarize(CUR_N, path2, None, OLD))["pct"]
        self.assertGreater(heavy, light)

    def test_deep_gets_more_exercises_a_day(self):
        self.assertGreater(cu.quota("deep", "new"), cu.quota("normal", "new"))
        self.assertGreater(cu.quota("deep", "review"), cu.quota("light", "review"))

    def test_bad_depth_or_weight_is_reported(self):
        bad = copy.deepcopy(CUR)
        bad["competencies"][0]["depth"] = "huge"
        bad["competencies"][1]["weight"] = 7
        joined = " ".join(cu.validate_curriculum(bad))
        self.assertIn("Depth desconegut", joined)
        self.assertIn("Weight ha de ser", joined)


class NextTargetTest(unittest.TestCase):
    def _data(self, records=()):
        d = Path(tempfile.mkdtemp())
        (d / ".records").mkdir()
        (d / ".records" / "s.jsonl").write_text("\n".join(json.dumps(r) for r in records) + ("\n" if records else ""), encoding="utf-8")
        return d

    def test_first_target_is_the_first_new_competence_and_the_note_names_it(self):
        t = cu.next_target(CUR, self._data(), "2026-09-21")
        self.assertEqual(t["id"], "a2.present_simple_vs_continuous")
        self.assertEqual(t["kind"], "new")
        self.assertIn("Present simple vs present continuous", t["note"])
        self.assertIn("Say nothing about this note", t["note"])
        self.assertTrue(t["signals"])

    def test_a_grammar_note_asks_for_a_sentence_exercise_with_a_shape_and_a_vocabulary_one_for_listed_words(self):
        t = cu.next_target(CUR, self._data(), "2026-09-21")
        self.assertIn("SENTENCE exercise", t["note"])
        self.assertIn("Shape of one", t["note"])
        self.assertIn("never say the name", t["note"])
        v = cu.next_target(CUR, self._data(), "2026-09-21", only_vocab=True)
        self.assertIn("Not a word outside this list", v["note"])
        self.assertNotIn("SENTENCE exercise", v["note"])

    def test_writing_gets_a_grammar_structure_to_use_never_a_word_list(self):
        # 📝 Writing reinforces what Go is teaching, from the other side: a topic
        # that needs the structure, written freely (Albert, 2026-09-23).
        w = cu.writing_frame(CUR, self._data(), "2026-09-21")
        comp = next(c for c in CUR["competencies"] if c["id"] == w["id"])
        self.assertFalse(comp["words"], "a vocabulary list is not a structure to write with")
        self.assertIn("Writing frame", w["note"])
        self.assertIn("no gap", w["note"])
        self.assertIn("Never say the name of the grammar point", w["note"])

    def test_the_writing_frame_writes_nothing(self):
        d = self._data()
        before = sorted(p.name for p in d.rglob("*"))
        cu.writing_frame(CUR, d, "2026-09-21")
        self.assertEqual(before, sorted(p.name for p in d.rglob("*")))

    def test_never_the_one_just_asked(self):
        t = cu.next_target(CUR, self._data(), "2026-09-21", last_id="a2.present_simple_vs_continuous")
        self.assertNotEqual(t["id"], "a2.present_simple_vs_continuous")

    def test_vocabulary_practice_is_only_handed_competences_with_words(self):
        t = cu.next_target(CUR, self._data(), "2026-09-21", only_vocab=True)
        self.assertTrue(t["vocab"], t)
        self.assertTrue(t["id"].startswith("a2.vocab_"))
        t2 = cu.next_target(CUR, self._data(), "2026-09-21", last_id=t["id"], only_vocab=True)
        self.assertTrue(t2["vocab"])

    def test_a_vocabulary_target_offers_words_it_has_not_used(self):
        import datetime as dt
        ts = int(dt.datetime(2026, 9, 21, 10, 0).timestamp() * 1000)
        recs = [rec(item="vocabulary_bread", skill="vocabulary", ts=ts, rid="v1")]
        # everything else already consolidated (explicit competency on the record), so food is what is new
        for c in [c for c in CUR["competencies"] if c["id"] != "a2.vocab_food_and_drink"]:
            n = cu.DEPTH[c["depth"]]["min_answers"]
            for i in range(n):        # its own evidence, spread over 20 days
                t0 = int(dt.datetime(2026, 9, 1 + i * 20 // n, 10, 0).timestamp() * 1000)
                recs.append(rec(competency=c["id"], ts=t0, rid=f"{c['id']}{i}", item="x_y"))
        t = cu.next_target(CUR, self._data(recs), "2026-09-21", last_id="a2.directions")
        self.assertEqual(t["id"], "a2.vocab_food_and_drink")
        self.assertTrue(t["vocab"])
        self.assertNotIn("bread", t["words"])

    def test_cli_returns_json_and_empty_without_a_curriculum(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cu.main(["next", "--curriculum", str(REPO_ROOT / "curriculum" / "en-A2.md"), "--data", str(self._data()), "--today", "2026-09-21"])
        self.assertEqual(json.loads(buf.getvalue())["id"], "a2.present_simple_vs_continuous")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cu.main(["next", "--auto", "--data", str(self._data())])
        self.assertEqual(json.loads(buf.getvalue()), {})


class PathViewTest(unittest.TestCase):
    """What the web draws: a plain learner part, the discouraging details apart under `admin`."""

    def _data(self, recs=()):
        import tempfile
        d = Path(tempfile.mkdtemp())
        (d / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        return d

    def _view(self, recs=()):
        d = self._data(recs)
        return cu.path_view(CUR, cu.rebuild_path(d, CUR, save=False), "2026-09-21")

    def test_fresh_learner_starts_at_zero(self):
        v = self._view()
        self.assertTrue(v["available"])
        self.assertEqual(v["pct"], 0)
        self.assertEqual(v["core_done"], 0)
        self.assertEqual(v["checkpoint"], "pending")
        self.assertIsNone(v["promotion"])
        self.assertTrue(v["sections"])
        it = v["sections"][0]["items"][0]
        self.assertEqual(set(it), {"id", "name", "core", "state", "label", "n", "need", "depth", "pct", "resting", "bank_low"})
        self.assertEqual(json.loads(json.dumps(v)), v)  # serialisable

    def test_details_for_the_teacher_are_apart(self):
        v = self._view()
        self.assertEqual(set(v["admin"]), {"history", "eta_days", "alerts", "rows", "checkpoints", "bank_low_at"})
        learner_part = {k: x for k, x in v.items() if k != "admin"}
        self.assertNotIn("acc_all", json.dumps(learner_part))
        self.assertNotIn("alerts", json.dumps(learner_part))
        # how many bank exercises are left is the teacher's number; she only gets a hint
        self.assertNotIn("bank_unseen", json.dumps(learner_part))

    def test_cli_json_is_unavailable_without_a_curriculum(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cu.main(["json", "--auto", "--data", str(self._data())])
        self.assertEqual(json.loads(buf.getvalue()), {"available": False})


class CourseTest(unittest.TestCase):
    """A hard cut between levels: certified for good, archived, a new course from zero."""

    def setUp(self):
        import datetime as dt
        self.d = Path(tempfile.mkdtemp())
        (self.d / ".records").mkdir()
        prof = {"learner": {"target_language": "English", "target_level": "A2", "current_level": "A0"}}
        (self.d / "learner-profile.json").write_text(json.dumps(prof), encoding="utf-8")
        self.a1 = cu.load_curriculum(REPO_ROOT / "curriculum" / "en-A1.md")
        self.a2 = cu.load_curriculum(REPO_ROOT / "curriculum" / "en-A2.md")
        self.ts = lambda day, i=0: int(dt.datetime.fromisoformat(day + "T10:00:00").timestamp() * 1000) + i
        recs = [rec(item="vocabulary_mother", skill="vocabulary", ts=self.ts("2026-09-10", i), rid=f"a{i}") for i in range(4)]
        (self.d / ".records" / "s.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))

    def _close(self, kind="checkpoint", **kw):
        cu.rebuild_path(self.d, self.a1)
        res = None
        if kind == "checkpoint":
            res = cu.apply_checkpoint(self.a1, cu.load_path(self.d, self.a1), "2026-09-20", [(c["id"], True) for c in self.a1["competencies"] if c["core"]])
            path = cu.load_path(self.d, self.a1)
            path["checkpoints"].append(res)
            cu.save_path(self.d, path)
        return cu.close_course(self.d, self.a1, "2026-09-20", res, now_ms=self.ts("2026-09-21"), root=REPO_ROOT, kind=kind, **kw)

    def test_the_first_course_is_the_lowest_uncertified_level(self):
        self.assertEqual(cu.find_curriculum(REPO_ROOT, self.d).name, "en-A1.md")

    def test_certifying_archives_certifies_and_starts_the_next_course(self):
        r = self._close()
        self.assertEqual(r["next_level"], "A2")
        cert = cu.load_certificates(self.d)
        self.assertEqual([(c["level"], c["type"], c["result"]) for c in cert], [("A1", "checkpoint", "pass")])
        arch = json.loads((self.d / cert[0]["archive"]).read_text())
        self.assertIn("a1.vocab_family", arch["path"]["competencies"])   # the old course, whole
        self.assertTrue(arch["final"])
        path = cu.load_path(self.d, self.a2)                             # the new course: empty, with its cut
        self.assertEqual(path["curriculum"], "English-A2")
        self.assertEqual(path["competencies"], {})
        self.assertEqual(path["start_ts"], self.ts("2026-09-21"))
        self.assertEqual(json.loads((self.d / "learner-profile.json").read_text())["learner"]["current_level"], "A1")
        self.assertEqual(cu.find_curriculum(REPO_ROOT, self.d).name, "en-A2.md")

    def test_records_before_the_cut_do_not_count_in_the_new_course(self):
        self._close()
        # an A1-era answer, and one made after the cut, both about food
        more = [rec(item="vocabulary_bread", skill="vocabulary", ts=self.ts("2026-09-15"), rid="old"),
                rec(item="vocabulary_cheese", skill="vocabulary", ts=self.ts("2026-09-22"), rid="new")]
        with open(self.d / ".records" / "s.jsonl", "a") as f:
            f.write("".join(json.dumps(r) + "\n" for r in more))
        path = cu.rebuild_path(self.d, self.a2)
        self.assertEqual(path["tagging"]["records"], 1)
        self.assertEqual(len(path["competencies"]["a2.vocab_food_and_drink"]["answers"]), 1)
        self.assertEqual(path["start_ts"], self.ts("2026-09-21"))        # the cut survives a rebuild

    def test_a_certificate_is_never_lost_or_repeated(self):
        self._close()
        again = self._close()
        self.assertTrue(again["already"])
        self.assertEqual(len(cu.load_certificates(self.d)), 1)
        self.assertEqual(len(list((self.d / "courses").glob("*.json"))), 1)

    def test_the_last_level_of_the_target_does_not_start_another_course(self):
        prof = {"learner": {"target_language": "English", "target_level": "A1", "current_level": "A0"}}
        (self.d / "learner-profile.json").write_text(json.dumps(prof), encoding="utf-8")
        r = self._close()
        self.assertIsNone(r["next_level"])
        self.assertEqual(cu.load_path(self.d, self.a1)["curriculum"], "English-A1")   # the finished course stays on view

    def test_a_teacher_can_certify_by_hand_and_the_weak_ones_stay_on_the_certificate(self):
        r = self._close(kind="manual")
        c = cu.load_certificates(self.d)[0]
        self.assertEqual((c["type"], c["result"]), ("manual", "manual"))
        self.assertIn("a1.verb_to_be", c["weak"])                        # nothing consolidated: all core are weak
        self.assertEqual(r["next_level"], "A2")

    def test_the_learner_is_told_once(self):
        self._close()
        n = cu.pending_notices(self.d)
        self.assertEqual([(x["type"], x["level"], x["next_level"]) for x in n], [("course_completed", "A1", "A2")])
        self.assertEqual(cu.mark_notices_seen(self.d), 1)
        self.assertEqual(cu.pending_notices(self.d), [])

    def test_the_view_carries_the_certificates_and_the_notice(self):
        self._close()
        path = cu.rebuild_path(self.d, self.a2, save=False)
        v = cu.path_view(self.a2, path, "2026-09-22", data_dir=self.d)
        self.assertEqual([c["level"] for c in v["certified"]], ["A1"])
        self.assertEqual(v["notice"]["level"], "A1")
        self.assertEqual(v["pct"], 0)                      # the bar starts again

    def test_cli_close_and_notice(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cu.main(["close", "--auto", "--data", str(self.d), "--day", "2026-09-20"])
        self.assertEqual(json.loads(buf.getvalue())["next_level"], "A2")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cu.main(["notice", "--data", str(self.d)])
        self.assertEqual(len(json.loads(buf.getvalue())), 1)
        with contextlib.redirect_stdout(io.StringIO()):
            cu.main(["notice", "--data", str(self.d), "--seen"])
        self.assertEqual(cu.pending_notices(self.d), [])

    def test_a_simulated_student_goes_from_zero_to_a2_through_the_cut(self):
        import importlib.util
        from datetime import date
        spec = importlib.util.spec_from_file_location("sim_ladder", REPO_ROOT / "scripts" / "flowed-sim-path.py")
        sim = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sim)
        r = sim.run_ladder("steady", 1, 90, date(2026, 9, 21), verbose=False)
        self.assertEqual([c["level"] for c in r["certificates"]], ["A1", "A2"])
        self.assertEqual([c["level"] for c in r["courses"]], ["A1", "A2"])
        a1_end = r["certificates"][0]["date"]
        self.assertLess(a1_end, r["certificates"][1]["date"])          # A2 certified after A1, never before
        data = Path(r["data"])
        self.assertEqual(len(list((data / "courses").glob("*.json"))), 2)

    def test_a_path_of_another_course_is_archived_before_it_is_overwritten(self):
        cu.rebuild_path(self.d, self.a1)
        self.assertTrue(cu.load_path(self.d, self.a1)["competencies"])
        cu.rebuild_path(self.d, self.a2)      # e.g. the profile target moved: the A1 file must not vanish
        self.assertTrue(list((self.d / "courses").glob("English-A1-orphan*.json")))
        self.assertEqual(cu.load_path(self.d, self.a2)["curriculum"], "English-A2")


class LevelTestTest(unittest.TestCase):
    """The level test: the server picks, asks and grades; the outcome cuts the course."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        prof = {"learner": {"target_language": "English", "target_level": "A2", "current_level": "A0"}}
        (self.d / "learner-profile.json").write_text(json.dumps(prof), encoding="utf-8")
        self.a1 = cu.load_curriculum(REPO_ROOT / "curriculum" / "en-A1.md")
        self.day = "2026-09-25"

    def _run(self, right=True, wrong_ids=()):
        """Answer every question: right (the expected answer) or wrong; returns the last reply."""
        run = json.loads((self.d / "checkpoint-run.json").read_text())
        out = None
        for it in run["items"]:
            good = it["cid"] not in wrong_ids and right
            out = cu.checkpoint_answer(self.d, self.a1, self.day, it["answer"].split(" / ")[0] if good else "zzz", root=REPO_ROOT)
        return out

    def test_every_expected_answer_of_every_closed_check_is_accepted(self):
        for f in ("en-A1.md", "en-A2.md"):
            cur = cu.load_curriculum(REPO_ROOT / "curriculum" / f)
            for c in cur["competencies"]:
                for k in c["checks"]:
                    if k["type"] not in cu.CLOSED_TYPES:
                        continue
                    for alt in [a.strip() for a in k["answer"].split("/")]:
                        self.assertTrue(cu.grade_check(k, alt), f"{c['id']}: {k['prompt']} -> {alt}")
                        if k["type"] == "Complete":
                            self.assertTrue(cu.grade_check(k, cu._blank_filled(k["prompt"], alt)), f"{c['id']} full sentence")
                    self.assertFalse(cu.grade_check(k, "zzz"), c["id"])
                    self.assertFalse(cu.grade_check(k, ""), c["id"])

    def test_grading_is_forgiving_about_form_and_strict_about_content(self):
        k = {"type": "Complete", "prompt": "We ___ (not/be) from London.", "answer": "aren't / are not"}
        for good in ("Aren't", "are not", "ARE NOT.", "We aren’t from London", "we are not from london!"):
            self.assertTrue(cu.grade_check(k, good), good)
        for bad in ("is not", "are", "we are from London", "not"):
            self.assertFalse(cu.grade_check(k, bad), bad)
        two = {"type": "Complete", "prompt": "I have ___ apple and two ___. (apple / banana)", "answer": "an, bananas"}
        self.assertTrue(cu.grade_check(two, "an, bananas") and cu.grade_check(two, "an bananas") and cu.grade_check(two, "bananas an") is False)
        self.assertFalse(cu.grade_check(two, "a, bananas"))
        m = {"type": "Meaning", "prompt": "the number that comes after nine", "answer": "ten"}
        self.assertTrue(cu.grade_check(m, "Ten") and cu.grade_check(m, "it is ten"))
        self.assertFalse(cu.grade_check(m, "eleven"))

    def test_it_does_not_open_before_the_learner_is_ready_and_a_teacher_can_force_it(self):
        r = cu.checkpoint_start(self.d, self.a1, self.day)
        self.assertFalse(r["ok"])
        self.assertFalse((self.d / "checkpoint-run.json").exists())
        r = cu.checkpoint_start(self.d, self.a1, self.day, force=True)
        self.assertTrue(r["ok"])
        self.assertIn("question 1/", r["text"])

    def test_the_plan_has_at_least_one_question_per_core_competence_and_never_repeats_one(self):
        cu.checkpoint_start(self.d, self.a1, self.day, force=True)
        run = json.loads((self.d / "checkpoint-run.json").read_text())
        core = {c["id"] for c in self.a1["competencies"] if c["core"]}
        self.assertLessEqual(core, {i["cid"] for i in run["items"]})
        keys = [(i["cid"], i["prompt"]) for i in run["items"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(i["type"] in cu.CLOSED_TYPES for i in run["items"]))

    def test_the_same_day_it_resumes_where_it_was(self):
        cu.checkpoint_start(self.d, self.a1, self.day, force=True)
        cu.checkpoint_answer(self.d, self.a1, self.day, "zzz")
        r = cu.checkpoint_start(self.d, self.a1, self.day, force=True)
        self.assertTrue(r["resumed"])
        self.assertIn("question 2/", r["text"])

    def test_passing_certifies_and_starts_the_next_course(self):
        cu.checkpoint_start(self.d, self.a1, self.day, force=True)
        r = self._run(right=True)
        self.assertTrue(r["done"])
        self.assertEqual(r["result"]["result"], "pass")
        self.assertEqual(r["closed"]["next_level"], "A2")
        self.assertIn("certified", r["text"])
        self.assertFalse((self.d / "checkpoint-run.json").exists())
        self.assertEqual([c["level"] for c in cu.load_certificates(self.d)], ["A1"])
        self.assertEqual(cu.find_curriculum(REPO_ROOT, self.d).name, "en-A2.md")
        archived = json.loads(next((self.d / "courses").glob("*.json")).read_text())
        self.assertTrue(archived["path"]["checkpoints"][0]["detail"])      # what was asked and answered is kept

    def test_failing_keeps_the_course_reinforces_and_makes_her_wait(self):
        cu.checkpoint_start(self.d, self.a1, self.day, force=True)
        r = self._run(right=False)
        self.assertEqual(r["result"]["result"], "stay")
        self.assertIsNone(r["closed"])
        self.assertEqual(cu.load_certificates(self.d), [])
        self.assertEqual(cu.find_curriculum(REPO_ROOT, self.d).name, "en-A1.md")
        path = cu.load_path(self.d, self.a1)
        self.assertTrue(path["reinforce"])                                   # the weak ones come first
        self.assertEqual(path["promotions"], [])
        self.assertIn("2026-09-28", r["text"])                               # checkpoint_gap_days = 3
        again = cu.checkpoint_start(self.d, self.a1, "2026-09-26", force=False)
        self.assertFalse(again["ok"])
        self.assertIn("2026-09-28", again["text"])

    def test_a_retry_prefers_questions_it_did_not_ask_before(self):
        cu.checkpoint_start(self.d, self.a1, self.day, force=True)
        first = json.loads((self.d / "checkpoint-run.json").read_text())["items"]
        self._run(right=False)
        cu.checkpoint_start(self.d, self.a1, "2026-09-30", force=True)
        second = json.loads((self.d / "checkpoint-run.json").read_text())["items"]
        by_cid = lambda items: {i["cid"]: i["prompt"] for i in items}
        a, b = by_cid(first), by_cid(second)
        same = [c for c in a if a[c] == b.get(c)]
        self.assertLess(len(same), len(a) // 2)

    def test_a_test_left_from_another_day_is_discarded_not_answered(self):
        cu.checkpoint_start(self.d, self.a1, self.day, force=True)
        r = cu.checkpoint_answer(self.d, self.a1, "2026-09-26", "whatever")
        self.assertFalse(r["ok"])
        self.assertFalse((self.d / "checkpoint-run.json").exists())

    def test_the_view_says_when_the_test_is_running(self):
        cu.checkpoint_start(self.d, self.a1, self.day, force=True)
        path = cu.rebuild_path(self.d, self.a1, save=False)
        v = cu.path_view(self.a1, path, self.day, data_dir=self.d)
        self.assertEqual(v["checkpoint_run"]["active"], True)
        self.assertEqual(v["checkpoint_run"]["i"], 1)


class LadderScenarioTest(unittest.TestCase):
    """The pieces of the e2e `ladder` scenario that do not need the app: how the level test's
    questions are read back, the made-up A1 history, and the test taken from it."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("fluent_e2e_ladder", REPO_ROOT / "scripts" / "flowed-e2e.py")
        cls.e2e = importlib.util.module_from_spec(spec)
        sys.modules["fluent_e2e_ladder"] = cls.e2e
        spec.loader.exec_module(cls.e2e)
        spec = importlib.util.spec_from_file_location("fluent_sim_ladder", REPO_ROOT / "scripts" / "flowed-sim-path.py")
        cls.sim = importlib.util.module_from_spec(spec)
        sys.modules["fluent_sim_ladder"] = cls.sim
        spec.loader.exec_module(cls.sim)

    def test_every_question_can_be_read_back_to_its_check(self):
        for f in ("en-A1.md", "en-A2.md"):
            cur = cu.load_curriculum(REPO_ROOT / "curriculum" / f)
            bank = {}
            for c in cur["competencies"]:
                for k in c["checks"]:
                    if k["type"] in cu.CLOSED_TYPES:
                        bank.setdefault(k["prompt"], k)
                        m = self.e2e.LEVEL_Q.search(cu._question(k, 1, 10))
                        self.assertIsNotNone(m, k["prompt"])
                        self.assertEqual(m.group(1).strip(), k["prompt"].strip())
            self.assertTrue(bank)

    def _history(self, profile):
        from datetime import date, datetime, time as T, timedelta
        d = Path(tempfile.mkdtemp())
        (d / "learner-profile.json").write_text(json.dumps(
            {"learner": {"target_language": "English", "target_level": "A2", "current_level": "A0"}}))
        cur = cu.load_curriculum(cu.find_curriculum(REPO_ROOT, d))
        by = {c["id"]: c for c in cur["competencies"]}
        anchor, given = date(2026, 1, 1), []
        _, info = self.sim.run(cur, profile, 7, 120, anchor, verbose=False, stop_when_ready=True,
                               on_answer=lambda cid, ok, dd: given.append(((dd - anchor).days, cid, ok)))
        n = max(g[0] for g in given)
        last = date.today() - timedelta(days=2)
        (d / ".records").mkdir()
        (d / ".records" / "x.jsonl").write_text("\n".join(json.dumps({
            "record_id": f"l{k}", "score": 9 if ok else 3, "competency": cid,
            "ts": int(datetime.combine(last - timedelta(days=n - i), T(12)).timestamp() * 1000) + k,
            "skill": "vocabulary" if by[cid]["words"] else "grammar"}) for k, (i, cid, ok) in enumerate(given)) + "\n")
        return d, cur, info

    def test_the_simulated_learner_stops_when_the_test_opens_and_the_history_makes_it_ready(self):
        from datetime import date
        for profile in ("fast", "steady", "weak"):
            d, cur, info = self._history(profile)
            self.assertEqual(info["result"], "ready", profile)
            path = cu.rebuild_path(d, cur, save=False)
            rows = cu.summarize(cur, path, date.today().isoformat())
            self.assertTrue(cu.checkpoint_ready(rows, cu.CFG, cur), profile)

    def test_the_test_taken_from_the_history_certifies_and_moves_to_a2(self):
        import re
        from datetime import date
        d, cur, _ = self._history("steady")
        today = date.today().isoformat()
        out = cu.checkpoint_start(d, cur, today)["text"]
        bank = {k["prompt"]: k for c in cur["competencies"] for k in c["checks"]}
        while "## Level test \u2014 question" in out:
            m = self.e2e.LEVEL_Q.search(out)
            out = cu.checkpoint_answer(d, cur, today, bank[m.group(1).strip()]["answer"].split("/")[0].strip(),
                                       root=REPO_ROOT)["text"]
        self.assertIn("certified", out)
        self.assertEqual([c["level"] for c in cu.load_certificates(d)], ["A1"])
        self.assertEqual(cu.find_curriculum(REPO_ROOT, d).name, "en-A2.md")

    def test_a_test_answered_all_wrong_does_not_close_the_course(self):
        from datetime import date
        d, cur, _ = self._history("steady")
        today = date.today().isoformat()
        out = cu.checkpoint_start(d, cur, today)["text"]
        while "## Level test \u2014 question" in out:
            out = cu.checkpoint_answer(d, cur, today, "no idea", root=REPO_ROOT)["text"]
        self.assertIn("Not yet", out)
        self.assertEqual(cu.load_certificates(d), [])
        self.assertEqual(cu.find_curriculum(REPO_ROOT, d).name, "en-A1.md")
        self.assertEqual(cu.load_path(d, cur)["checkpoints"][0]["result"], "stay")


if __name__ == "__main__":
    unittest.main()
