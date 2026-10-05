"""Learner-only competences: <profile>/extra.md + <profile>/bank/<id>.json.

2026-09-27, Albert: a song (or a class topic) practised in Go, shown in Stats,
never counted in the level bar. See docs/ARQUITECTURA.md G.17.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))
import bank  # noqa: E402
import curriculum as cu  # noqa: E402

A1 = REPO / "curriculum" / "en-A1.md"
SRC = REPO / "curriculum" / "extras" / "x.good_luck_babe"
CID = "x.good_luck_babe"


class ProfileExtrasTest(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "learner-profile.json").write_text(json.dumps(
            {"learner": {"name": "Test", "target_language": "English", "level": "A1"}}))
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "flowed-extra.py"), "add", str(self.d), str(SRC)],
                           capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_the_extra_joins_the_curriculum_only_for_this_learner(self):
        base = cu.load_curriculum(A1)
        mine = cu.load_curriculum(A1, self.d)
        self.assertNotIn(CID, [c["id"] for c in base["competencies"]])
        extra = next(c for c in mine["competencies"] if c["id"] == CID)
        self.assertFalse(extra["core"])
        self.assertEqual("Extra", extra["section"])

    def test_it_never_counts_in_the_level_bar_or_the_checkpoint(self):
        cur = cu.load_curriculum(A1, self.d)
        path = cu.rebuild_path(self.d, cur, save=False)
        for i in range(12):
            cu.record_answer(path, CID, True, f"2026-09-{10 + i:02d}")
        rows = cu.summarize(cur, path, "2026-09-27")
        base_rows = [r for r in rows if r["id"] != CID]
        self.assertEqual(cu.progress(base_rows)["pct"], cu.progress(rows)["pct"])
        self.assertNotIn(CID, cu.checkpoint_plan(cur, rows))

    def test_stats_show_it_in_its_own_section(self):
        cur = cu.load_curriculum(A1, self.d)
        view = cu.path_view(cur, cu.rebuild_path(self.d, cur, save=False), "2026-09-27",
                            data_dir=self.d, stem="en-A1", root=REPO)
        extra = [s for s in view["sections"] if s["name"] == "Extra"]
        self.assertEqual([CID], [i["id"] for i in extra[0]["items"]])

    def test_its_exercises_come_from_the_profile_bank(self):
        item = bank.pick_item(REPO, "en-A1", CID, self.d, "2026-09-27")
        self.assertTrue(item and item["competence"] == CID)
        self.assertIn(CID, bank.bank_left(REPO, "en-A1", self.d))
        self.assertEqual([], bank.load_bank(REPO, "en-A1", CID))  # not without the profile

    def test_go_can_pick_it(self):
        t = cu.next_target(cu.load_curriculum(A1, self.d), self.d, "2026-09-27")
        plan_ids = {t.get("id")}
        self.assertTrue(plan_ids)  # something is offered
        cur = cu.load_curriculum(A1, self.d)
        rows = cu.summarize(cur, cu.rebuild_path(self.d, cur, save=False), "2026-09-27")
        self.assertIn(CID, cu.active_competences(rows, {}, dict(cu.CFG, max_active=9)))

    def test_add_is_idempotent(self):
        subprocess.run([sys.executable, str(REPO / "scripts" / "flowed-extra.py"), "add", str(self.d), str(SRC)],
                       capture_output=True, text=True, check=True)
        text = (self.d / "extra.md").read_text()
        self.assertEqual(1, text.count(f"### {CID} "))

    def test_every_bank_answer_is_graded_right(self):
        for it in json.loads((SRC / f"{CID}.json").read_text()):
            for a in [it["answer"], *it["also_accept"]]:
                self.assertEqual("correct", bank.grade(it, a)["verdict"], (it["id"], a))


if __name__ == "__main__":
    unittest.main()
