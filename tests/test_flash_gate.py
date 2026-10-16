#!/usr/bin/env python3
"""Flash as a condition of the level test (docs/ENCARREC-FLASH-v1.md §4.2, §5).

The level file's `flash_share` says what share of its Flash lists must be closed
(every word in box 2 in data/flash-db.json). Without the key, or with 0, nothing
changes: these tests also pin that the existing rules do not move.
"""
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "hooks"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import curriculum as cu  # noqa: E402

A1 = cu.load_curriculum(REPO_ROOT / "curriculum" / "en-A1.md")
# The real A1 lists: counts come from the files, so adding a list does not break the suite.
REAL_TOTAL = len(cu.flash_lists(REPO_ROOT, "en-A1"))
REAL_NEEDED = math.ceil(REAL_TOTAL * 80 / 100)
A2 = cu.load_curriculum(REPO_ROOT / "curriculum" / "en-A2.md")
CORE = [c["id"] for c in A1["competencies"] if c["core"]]
OLD = dict(cu.CFG, window=6, min_answers=5, min_span_days=4, stalled_answers=20)
# The same level without depths (each competence weighs 1), as tests/test_curriculum.py does:
# six answers a competence then reach "consolidated" under OLD.
import copy  # noqa: E402
A1N = copy.deepcopy(A1)
for _c in A1N["competencies"]:
    _c["depth"], _c["weight"] = None, 1


def level(text_meta: str, stem: str = "en-X1") -> dict:
    """A tiny curriculum: just the front matter, with the stem the loader would give it."""
    cur = cu.parse_curriculum(f"---\n{text_meta}\n---\n")
    cur["meta"]["stem"] = stem
    cur["competencies"] = []
    return cur


def write_lists(root: Path, stem: str, lists: dict[str, list[str]]) -> None:
    d = root / "curriculum" / "flash" / stem
    d.mkdir(parents=True)
    for i, (lid, words) in enumerate(lists.items()):
        body = {"id": lid, "level": "X1", "title": {"en": lid},
                "words": [{"id": w, "target": [w], "native": {"ca": [w]}} for w in words]}
        (d / f"{i:02d}-{lid}.json").write_text(json.dumps(body), encoding="utf-8")


def write_db(data: Path, lists: dict[str, dict[str, int]]) -> None:
    """lists: list id -> {word id: box}."""
    out = {"version": 1, "lists": {
        lid: {"words": {w: {"box": b, "seen": 1, "first_try": 0, "misses": 0, "last": "2026-10-01"}
                        for w, b in ws.items()}, "closed_at": None}
        for lid, ws in lists.items()}, "rounds_by_day": {}}
    (data / cu.FLASH_DB).write_text(json.dumps(out), encoding="utf-8")


class ParseAndValidateTest(unittest.TestCase):
    def test_flash_share_is_an_integer_in_the_front_matter(self):
        self.assertEqual(level("flash_share: 80")["meta"]["flash_share"], 80)
        self.assertEqual(A1["meta"]["flash_share"], 80)

    def test_absent_means_no_requirement_and_no_key(self):
        self.assertNotIn("flash_share", A2["meta"])
        self.assertNotIn("flash_share", level("ready_share: 50"))

    def test_validation_wants_a_percentage(self):
        base = copy_real_a1()
        self.assertEqual(cu.validate_curriculum(base), [])
        for bad in (150, -1):
            cur = copy_real_a1()
            cur["meta"]["flash_share"] = bad
            self.assertTrue(any("flash_share" in e for e in cu.validate_curriculum(cur)), bad)


def copy_real_a1() -> dict:
    import copy
    return copy.deepcopy(A1)


class FlashProgressTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.data = Path(tempfile.mkdtemp())
        self.lists = {"x.flash.a": ["one", "two"], "x.flash.b": ["three"], "x.flash.c": ["four", "five"],
                      "x.flash.d": ["six"], "x.flash.e": ["seven", "eight"]}
        write_lists(self.root, "en-X1", self.lists)

    def progress(self, share=80, cur=None):
        cur = cur or level(f"flash_share: {share}", "en-X1")
        return cu.flash_progress(self.root, cur, self.data)

    def test_no_lists_no_requirement(self):
        empty = Path(tempfile.mkdtemp())
        fp = cu.flash_progress(empty, level("flash_share: 80", "en-X1"), self.data)
        self.assertEqual((fp["total"], fp["closed"], fp["met"]), (0, 0, True))

    def test_no_db_file_nothing_closed(self):
        fp = self.progress()
        self.assertEqual((fp["closed"], fp["total"], fp["share"], fp["needed"], fp["met"]), (0, 5, 80, 4, False))

    def test_partial_list_is_not_closed(self):
        write_db(self.data, {"x.flash.a": {"one": 2, "two": 1}})
        self.assertEqual(self.progress()["closed"], 0)

    def test_a_list_closes_when_every_word_is_known(self):
        write_db(self.data, {"x.flash.a": {"one": 2, "two": 2}, "x.flash.b": {"three": 2}})
        self.assertEqual(self.progress()["closed"], 2)

    def test_the_share_decides_met(self):
        write_db(self.data, {k: {w: 2 for w in ws} for k, ws in list(self.lists.items())[:3]})
        fp = self.progress()
        self.assertEqual((fp["closed"], fp["needed"], fp["met"]), (3, 4, False))
        write_db(self.data, {k: {w: 2 for w in ws} for k, ws in list(self.lists.items())[:4]})
        fp = self.progress()
        self.assertEqual((fp["closed"], fp["needed"], fp["met"]), (4, 4, True))

    def test_a_word_added_to_a_closed_list_reopens_it(self):
        write_db(self.data, {"x.flash.a": {"one": 2, "two": 2}})
        self.assertEqual(self.progress()["closed"], 1)
        (self.root / "curriculum" / "flash" / "en-X1" / "00-x.flash.a.json").write_text(json.dumps({
            "id": "x.flash.a", "level": "X1", "title": {"en": "a"},
            "words": [{"id": w, "target": [w], "native": {"ca": [w]}} for w in ["one", "two", "new"]]}), encoding="utf-8")
        self.assertEqual(self.progress()["closed"], 0)

    def test_share_zero_is_always_met(self):
        fp = self.progress(share=0)
        self.assertEqual((fp["met"], fp["needed"]), (True, 0))

    def test_an_empty_list_is_never_closed(self):
        write_lists(self.root, "en-Y1", {"y.flash.empty": []})
        fp = cu.flash_progress(self.root, level("flash_share: 100", "en-Y1"), self.data)
        self.assertEqual((fp["closed"], fp["total"], fp["met"]), (0, 1, False))

    def test_a_broken_db_counts_as_nothing_closed(self):
        (self.data / cu.FLASH_DB).write_text("{not json", encoding="utf-8")
        self.assertEqual(self.progress()["closed"], 0)

    def test_needed_rounds_up(self):
        fp = cu.flash_progress(self.root, level("flash_share: 50", "en-X1"), self.data)
        self.assertEqual(fp["needed"], 3)  # ceil(5 * 50 / 100)

    def test_the_real_a1_lists(self):
        fp = cu.flash_progress(REPO_ROOT, A1, self.data)
        self.assertEqual((fp["total"], fp["needed"], fp["met"]), (REAL_TOTAL, REAL_NEEDED, False))


class CheckpointReadyTest(unittest.TestCase):
    """checkpoint_ready keeps its old answer when no root/data_dir is given."""

    def setUp(self):
        self.data = Path(tempfile.mkdtemp())

    def _ready_rows(self):
        path = cu.new_path(A1N)
        for cid in CORE:
            for k in range(6):
                cu.record_answer(path, cid, True, (date(2026, 9, 1) + timedelta(days=k)).isoformat())
        return cu.summarize(A1N, path, None, OLD)

    def test_without_root_and_data_dir_there_is_no_flash_requirement(self):
        rows = self._ready_rows()
        self.assertTrue(cu.checkpoint_ready(rows, OLD, A1N))

    def test_with_root_and_data_dir_flash_has_to_be_met(self):
        rows = self._ready_rows()
        self.assertFalse(cu.checkpoint_ready(rows, OLD, A1N, root=REPO_ROOT, data_dir=self.data))
        write_db(self.data, {"x": {}})  # db present, nothing closed: still short
        self.assertFalse(cu.checkpoint_ready(rows, OLD, A1N, root=REPO_ROOT, data_dir=self.data))

    def test_flash_met_and_core_ready_opens_the_test(self):
        rows = self._ready_rows()
        lists = {fl["id"]: {w: 2 for w in fl["words"]} for fl in cu.flash_lists(REPO_ROOT, "en-A1")}
        write_db(self.data, lists)
        self.assertTrue(cu.checkpoint_ready(rows, OLD, A1N, root=REPO_ROOT, data_dir=self.data))

    def test_core_not_ready_stays_not_ready_whatever_flash_says(self):
        path = cu.new_path(A1)
        rows = cu.summarize(A1, path, None, OLD)
        lists = {fl["id"]: {w: 2 for w in fl["words"]} for fl in cu.flash_lists(REPO_ROOT, "en-A1")}
        write_db(self.data, lists)
        self.assertFalse(cu.checkpoint_ready(rows, OLD, A1, root=REPO_ROOT, data_dir=self.data))


class PathViewTest(unittest.TestCase):
    def test_flash_block_only_for_levels_that_have_a_share(self):
        data = Path(tempfile.mkdtemp())
        path = cu.new_path(A1)
        v = cu.path_view(A1, path, "2026-10-16", data_dir=data, stem="en-A1", root=REPO_ROOT)
        self.assertEqual(v["flash"], {"closed": 0, "total": REAL_TOTAL, "share": 80, "needed": REAL_NEEDED, "met": False})
        v2 = cu.path_view(A2, cu.new_path(A2), "2026-10-16", data_dir=data, stem="en-A2", root=REPO_ROOT)
        self.assertIsNone(v2["flash"])

    def test_no_data_dir_no_flash_block(self):
        v = cu.path_view(A1, cu.new_path(A1), "2026-10-16")
        self.assertIsNone(v["flash"])
        self.assertEqual(v["checkpoint"], "pending")


class ReportTest(unittest.TestCase):
    def test_report_says_flash_when_only_flash_is_missing(self):
        # Core ready, Flash short: the report names Flash instead of the core shortfall.
        path = cu.new_path(A1N)
        for cid in CORE:
            for k in range(6):
                cu.record_answer(path, cid, True, (date(2026, 9, 1) + timedelta(days=k)).isoformat())
        data = Path(tempfile.mkdtemp())
        text = cu.render_report(A1N, path, "2026-10-16", cfg=OLD, root=REPO_ROOT, data_dir=data)
        self.assertIn(f"Checkpoint: encara no (Flash: 0/{REAL_NEEDED} llistes tancades)", text)
        self.assertNotIn("falten", text)
        # Without the data dir the requirement is not looked at: the old wording stays.
        plain = cu.render_report(A1N, path, "2026-10-16", cfg=OLD)
        self.assertIn("Checkpoint: llest", plain)


def load_sim():
    spec = importlib.util.spec_from_file_location("math_sim_flash", REPO_ROOT / "scripts" / "flowed-sim-path.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["math_sim_flash"] = mod
    spec.loader.exec_module(mod)
    return mod


class LevelTestMessageTest(unittest.TestCase):
    """checkpoint_start: the learner who has the topics but not the Flash lists is told so."""

    @classmethod
    def setUpClass(cls):
        cls.sim = load_sim()

    def _steady_history(self):
        from datetime import datetime, time as T
        d = Path(tempfile.mkdtemp())
        (d / "learner-profile.json").write_text(json.dumps(
            {"learner": {"target_language": "English", "target_level": "A2", "current_level": "A0"}}))
        cur = cu.load_curriculum(cu.find_curriculum(REPO_ROOT, d))
        by = {c["id"]: c for c in cur["competencies"]}
        anchor, given = date(2026, 1, 1), []
        self.sim.run(cur, "steady", 7, 120, anchor, verbose=False, stop_when_ready=True,
                     on_answer=lambda cid, ok, dd: given.append(((dd - anchor).days, cid, ok)))
        n = max(g[0] for g in given)
        last = date.today() - timedelta(days=2)
        (d / ".records").mkdir()
        (d / ".records" / "x.jsonl").write_text("\n".join(json.dumps({
            "record_id": f"l{k}", "score": 9 if ok else 3, "competency": cid,
            "ts": int(datetime.combine(last - timedelta(days=n - i), T(12)).timestamp() * 1000) + k,
            "skill": "vocabulary" if by[cid]["words"] else "grammar"}) for k, (i, cid, ok) in enumerate(given)) + "\n")
        return d, cur

    def test_the_test_waits_for_flash_and_says_why(self):
        d, cur = self._steady_history()
        out = cu.checkpoint_start(d, cur, date.today().isoformat(), stem="en-A1", root=REPO_ROOT)
        self.assertFalse(out["ok"])
        self.assertIn(f"closed enough Flash lists (you have 0, need {REAL_NEEDED} of {REAL_TOTAL})", out["text"])

    def test_the_test_opens_once_the_lists_are_closed(self):
        d, cur = self._steady_history()
        lists = {fl["id"]: {w: 2 for w in fl["words"]} for fl in cu.flash_lists(REPO_ROOT, "en-A1")}
        write_db(d, lists)
        out = cu.checkpoint_start(d, cur, date.today().isoformat(), stem="en-A1", root=REPO_ROOT)
        self.assertTrue(out["ok"], out.get("text"))


if __name__ == "__main__":
    unittest.main()
