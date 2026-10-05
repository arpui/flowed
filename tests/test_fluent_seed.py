#!/usr/bin/env python3
"""The seeded past is one this script built — not one layered on the last test.

Measured on 2026-09-19. `flowed-seed.py` cleared today (the plan, the records,
the T0 snapshots) but left `spaced-repetition.json` and `mistakes-db.json`
alone, so every sweep seeded on top of the queue the previous sweep had left
behind. The items it introduces "late" so they are still due were already in
the queue, already answered, already scheduled weeks away:

    sweep 1   12 items · 3 due today  → 9 records, 9 with an item_id
    sweep 2   15 items · 0 due today  → 8 records, 0 with an item_id

Nothing failed. The rig simply measured a different profile each time, and the
lost item_ids looked like a regression in the server. Same family as `--repeat`
consuming the day: when the instrument moves between runs, every comparison
made with it is worthless.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED = REPO_ROOT / "scripts" / "flowed-seed.py"
EXAMPLES = REPO_ROOT / "data-examples"


def summary(out: str) -> dict:
    """items / due, read back from what the script reports."""
    got = {}
    for line in out.splitlines():
        if "ítems SM-2" in line:
            got["items"] = int(line.split(":")[1])
        if "per repassar avui" in line:
            got["due"] = int(line.split(":")[1].split("→")[0])
    return got


class SeedingTwiceGivesTheSameProfile(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="test-seed-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        for tpl in EXAMPLES.glob("*-template.json"):
            shutil.copy(tpl, self.dir / tpl.name.replace("-template", ""))

    def seed(self) -> dict:
        p = subprocess.run(
            [sys.executable, str(SEED), "--dir", str(self.dir), "--days", "8", "--due", "2"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=300)
        self.assertEqual(0, p.returncode, p.stderr[-400:])
        got = summary(p.stdout)
        self.assertIn("due", got, p.stdout)
        return got

    def test_a_second_seed_reproduces_the_first(self):
        first = self.seed()
        self.assertGreater(first["due"], 0, "a seeded profile with nothing due is not a test")
        self.assertEqual(first, self.seed())

    def test_it_survives_a_run_that_moved_the_queue(self):
        first = self.seed()
        sr = self.dir / "spaced-repetition.json"
        doc = json.loads(sr.read_text(encoding="utf-8"))
        # What a real session does to the queue: everything answered, so
        # everything is scheduled far away — plus an item the tutor invented.
        for item in doc["items"].values():
            item["due_date"] = "2099-01-01"
        doc["items"]["vocabulary_junk_from_a_previous_run"] = {"content": "junk",
                                                               "due_date": "2099-01-01"}
        sr.write_text(json.dumps(doc), encoding="utf-8")

        self.assertEqual(first, self.seed())
        after = json.loads(sr.read_text(encoding="utf-8"))["items"]
        self.assertNotIn("vocabulary_junk_from_a_previous_run", after)


class ArchivingDoesNotEatItsOwnTail(unittest.TestCase):
    """The rename scheme that killed the 22:32 bench.

    Archiving renamed each file to `.<name>.bak-seed` in place, and the glob
    that found them matched the archives too. Thirteen sweeps later the seed
    died with ENAMETOOLONG **before seeding anything**, the sweep did not check
    its exit code, and three executions ran on a stale profile with nothing due
    — and were read as the tutor collapsing.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="test-seed-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        for tpl in EXAMPLES.glob("*-template.json"):
            shutil.copy(tpl, self.dir / tpl.name.replace("-template", ""))

    def test_twenty_seeds_leave_short_names_and_a_live_directory(self):
        for _ in range(20):
            p = subprocess.run(
                [sys.executable, str(SEED), "--dir", str(self.dir),
                 "--days", "5", "--due", "2"],
                capture_output=True, text=True, cwd=REPO_ROOT, timeout=300)
            self.assertEqual(0, p.returncode, p.stderr[-400:])

        for d in (".daily", ".records", ".update-state"):
            sub = self.dir / d
            if not sub.is_dir():
                continue
            live = [f for f in sub.iterdir() if f.is_file()]
            self.assertFalse([f for f in live if f.name.startswith(".")],
                             f"{d} encara arxiva canviant el nom al mateix lloc")
            for f in sub.rglob("*"):
                self.assertLess(len(f.name), 120, f"nom massa llarg: {f.name}")


class TheMaterialHasSense(unittest.TestCase):
    """Con pocs ítems i sense enunciat, cada repetició era ambigua: del tutor o
    del banc? Un vocabulari amb només la paraula anglesa feia preguntar «What is
    the English word for 'because'?»."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("math_seed", SEED)
        cls.seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.seed)

    def test_there_is_a_lot_of_material(self):
        self.assertGreaterEqual(len(self.seed.material()), 30)

    def test_every_item_has_a_unique_id(self):
        ids = [m["id"] for m in self.seed.material()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_a_vocabulary_item_asks_in_catalan_and_answers_in_english(self):
        for m in self.seed.material():
            if m["kind"] == "vocab":
                self.assertNotEqual(m["content"], m["answer"], m["id"])

    def test_a_grammar_item_is_a_sentence_or_word_with_its_mistake(self):
        for m in self.seed.material():
            if m["kind"] == "error":
                self.assertNotEqual(m["right"], m["wrong"], m["id"])

    def test_the_due_order_names_real_items_and_mixes_kinds(self):
        keys = {m["key"] for m in self.seed.material()}
        self.assertTrue(set(self.seed.DUE_ORDER) <= keys)
        first6 = self.seed.DUE_ORDER[:6]
        self.assertGreaterEqual(len({k.split(":")[0] for k in first6}), 4)


class SixDueMeansSixDue(unittest.TestCase):
    def test_a_full_lesson_of_items_is_due_today_and_no_more(self):
        d = Path(tempfile.mkdtemp(prefix="test-seed-"))
        self.addCleanup(shutil.rmtree, d, True)
        for tpl in EXAMPLES.glob("*-template.json"):
            shutil.copy(tpl, d / tpl.name.replace("-template", ""))
        p = subprocess.run([sys.executable, str(SEED), "--dir", str(d), "--days", "21"],
                           capture_output=True, text=True, cwd=REPO_ROOT, timeout=300)
        self.assertEqual(0, p.returncode, p.stderr[-400:])
        got = summary(p.stdout)
        self.assertEqual(6, got["due"], p.stdout)
        self.assertGreaterEqual(got["items"], 30)

class LessonSizesAreExact(unittest.TestCase):
    """A lesson of 2 and a lesson of 15 are both real days: --due N is exactly N."""

    def _due(self, n: int) -> int:
        d = Path(tempfile.mkdtemp(prefix="test-seed-"))
        self.addCleanup(shutil.rmtree, d, True)
        for tpl in EXAMPLES.glob("*-template.json"):
            shutil.copy(tpl, d / tpl.name.replace("-template", ""))
        p = subprocess.run([sys.executable, str(SEED), "--dir", str(d), "--days", "21",
                            "--due", str(n)],
                           capture_output=True, text=True, cwd=REPO_ROOT, timeout=300)
        self.assertEqual(0, p.returncode, p.stderr[-400:])
        return summary(p.stdout)["due"]

    def test_two_due(self):
        self.assertEqual(2, self._due(2))

    def test_fifteen_due(self):
        self.assertEqual(15, self._due(15))

    def test_the_order_past_the_hand_picked_eight_alternates_kinds(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("math_seed_o", SEED)
        seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed)
        order = seed.due_order(seed.material())
        self.assertEqual(order[:len(seed.DUE_ORDER)], seed.DUE_ORDER)
        self.assertEqual(len(order), len(set(order)))
        extra = order[len(seed.DUE_ORDER):len(seed.DUE_ORDER) + 8]
        self.assertGreaterEqual(len({k.split(":")[0] == "vocabulary" for k in extra}), 2)


class DayArchivesAreHistory(unittest.TestCase):
    """The multi-day scenario leaves `.<name>.day-<stamp>` files behind. The next
    run's "yesterday" checks read them: «finestra» was reported as asked again
    when it was the seed's own item, answered right in a run that was over."""

    def test_the_seed_puts_day_archives_away(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("math_seed_a", SEED)
        seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed)
        d = Path(tempfile.mkdtemp(prefix="test-seed-"))
        self.addCleanup(shutil.rmtree, d, True)
        (d / ".abc.jsonl.day-20260920-101010").write_text("{}")
        (d / ".hidden-other").write_text("x")
        (d / "live.jsonl").write_text("{}")
        seed.archive(d)
        left = sorted(p.name for p in d.iterdir() if p.is_file())
        self.assertEqual(left, [".hidden-other"])

    def test_advance_day_sets_the_t0_snapshots_aside(self):
        d = Path(tempfile.mkdtemp(prefix="test-adv-"))
        self.addCleanup(shutil.rmtree, d, True)
        for tpl in EXAMPLES.glob("*-template.json"):
            shutil.copy(tpl, d / tpl.name.replace("-template", ""))
        (d / ".update-state").mkdir()
        (d / ".update-state" / "session-001@2026-09-20.json").write_text("{}")
        p = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "flowed-advance-day.py"),
                            "--dir", str(d), "--days", "1"],
                           capture_output=True, text=True, cwd=REPO_ROOT, timeout=60)
        self.assertEqual(0, p.returncode, p.stderr[-300:])
        live = [f.name for f in (d / ".update-state").iterdir() if f.is_file()]
        self.assertEqual(live, [])
        self.assertEqual(len(list((d / ".update-state" / "_archive").iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
