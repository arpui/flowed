#!/usr/bin/env python3
"""ENCARREC-M7-GO-FOCUS (docs/ENCARREC-M7-GO-FOCUS.md §7).

Pinned here:
  * `go_active`: only the listed competences come out of active_competences,
    review_pool, due_maintenance, the reinforcement list and next_target; a
    sleeping one keeps its progress and its % does not move; no key = as before;
    an unknown id is a validation error; a Requires on a sleeping competence
    does not block;
  * over 20 simulated picks of next_target, only active competences;
  * lists are graded as sets, factorisations as prime powers (order, separators,
    what is missing or extra), word choices by their label;
  * the m7 Go families: their answers are recomputed from their spec, and the
    generated bank has >= 24 valid items per active competence.
"""
import datetime as dt
import importlib
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hooks"))
sys.path.insert(0, str(REPO / "scripts"))

import bank as bankmod          # noqa: E402
import curriculum as cu         # noqa: E402
import mathgrade                # noqa: E402

mb = importlib.import_module("mathbank")

CUR = REPO / "curriculum" / "math-m7.md"
BANK = REPO / "curriculum" / "bank" / "math-m7"
TODAY = "2026-11-03"
GO = {
    "m7.props_grouping", "m7.props_distributive", "m7.integers", "m7.powers_roots",
    "m7.powers_base", "m7.divisors_multiples", "m7.divisibility_rules", "m7.primes",
    "m7.prime_factorization", "m7.factor_gcd_lcm",
}


def _cur(text: str | None = None) -> dict:
    if text is None:
        return cu.load_curriculum(CUR)
    tmp = Path(tempfile.mkdtemp()) / "math-m7.md"
    tmp.write_text(text, encoding="utf-8")
    return cu.load_curriculum(tmp)


def _without_go_key(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith("go_active:")) + "\n"


def _random_path(cur: dict, rng: random.Random) -> dict:
    """A path where every competence has a random history (some right, some wrong, several days)."""
    path = cu.new_path(cur)
    base = dt.date.fromisoformat("2026-10-01")
    for c in cur["competencies"]:
        n = rng.choice([0, 1, 3, 6, 12, 25])
        answers = []
        for i in range(n):
            day = (base + dt.timedelta(days=rng.randint(0, 40) + i // 3)).isoformat()
            answers.append([day, 1 if rng.random() < 0.8 else 0])
        answers.sort(key=lambda a: a[0])
        if answers:
            path["competencies"][c["id"]] = {"answers": answers}
    return path


class GoActiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cur = cu.load_curriculum(CUR)
        cls.text = CUR.read_text(encoding="utf-8")

    def test_the_level_declares_the_ten_active_competences(self):
        self.assertEqual(set(self.cur["meta"]["go_active"]), GO)
        self.assertEqual(len(self.cur["meta"]["go_active"]), 10)
        self.assertEqual(cu.validate_curriculum(self.cur), [])

    def test_an_unknown_id_is_a_validation_error(self):
        text = self.text.replace("m7.factor_gcd_lcm\n---", "m7.factor_gcd_lcm, m7.no_existeix\n---", 1)
        cur = _cur(text)
        self.assertIn("go_active: id desconegut m7.no_existeix", cu.validate_curriculum(cur))

    def test_without_the_key_nothing_sleeps(self):
        cur = _cur(_without_go_key(self.text))
        self.assertNotIn("go_active", cur["meta"])
        self.assertEqual(cu.asleep_ids(cur), set())
        rng = random.Random(3)
        offered = set()
        for _ in range(50):
            path = _random_path(cur, rng)
            rows = cu.summarize(cur, path, TODAY)
            self.assertFalse(any(r["asleep"] for r in rows))
            offered |= set(cu.active_competences(rows, path))
        # the competences that are asleep under the key come out again without it
        self.assertTrue(offered - GO)

    def test_sleeping_competences_never_come_out(self):
        rng = random.Random(11)
        for _ in range(200):
            path = _random_path(self.cur, rng)
            rows = cu.summarize(self.cur, path, TODAY)
            path["reinforce"] = rng.sample([c["id"] for c in self.cur["competencies"]], 4)
            self.assertLessEqual(set(cu.active_competences(rows, path)), GO)
            path["reinforce"] = []
            self.assertLessEqual(set(cu.active_competences(rows, path)), GO)
            self.assertLessEqual(set(cu.review_pool(rows)), GO)
            self.assertLessEqual(set(cu.due_maintenance(self.cur, path, TODAY)), GO)

    def test_a_sleeping_competence_keeps_its_progress_and_the_percentage(self):
        rng = random.Random(5)
        path = _random_path(self.cur, rng)
        with_key = cu.summarize(self.cur, path, TODAY)
        without = cu.summarize(_cur(_without_go_key(self.text)), path, TODAY)
        self.assertEqual(cu.progress(with_key), cu.progress(without))
        self.assertEqual([r["state"] for r in with_key], [r["state"] for r in without])
        asleep = [r for r in with_key if r["asleep"]]
        self.assertTrue(asleep)
        self.assertTrue(all(r["id"] not in GO for r in asleep))

    def test_the_path_view_labels_a_sleeping_competence(self):
        path = cu.new_path(self.cur)
        view = cu.path_view(self.cur, path, TODAY)
        items = [i for s in view["sections"] for i in s["items"]]
        labels = {i["id"]: i["label"] for i in items}
        self.assertEqual(labels["m7.syntax_letters"], "💤 adormida")
        self.assertNotIn("💤 adormida", [labels[c] for c in GO])

    def test_a_requirement_that_sleeps_does_not_block(self):
        text = (
            "---\nlanguage: math\nlevel: m9\nversion: 1\npass_mark: 80\ncarry_mark: 65\n"
            "checkpoint_items: 2\ngo_active: m9.a\n---\n\n"
            "## Test\n\n### m9.a — A [core]\nCan do: A.\nDepth: normal\nWeight: 1\nRequires: m9.b\n"
            "Tags: #procedure\nCheck:\n- Compute: 1 + 1 → 2\n- Compute: 2 + 2 → 4\n- Compute: 3 + 3 → 6\n\n"
            "### m9.b — B [core]\nCan do: B.\nDepth: normal\nWeight: 1\nTags: #procedure\n"
            "Check:\n- Compute: 1 + 2 → 3\n- Compute: 2 + 3 → 5\n- Compute: 3 + 4 → 7\n"
        )
        cur = _cur(text)
        self.assertEqual(cu.validate_curriculum(cur), [])
        rows = cu.summarize(cur, cu.new_path(cur), TODAY)
        self.assertEqual(cu.active_competences(rows, cu.new_path(cur)), ["m9.a"])

    def test_next_target_offers_only_active_competences_over_twenty_picks(self):
        rng = random.Random(2026)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".records").mkdir()
            picks, last = [], None
            ts0 = int(dt.datetime(2026, 11, 3, 9, 0).timestamp() * 1000)
            for i in range(20):
                t = cu.next_target(self.cur, d, TODAY, last_id=last)
                self.assertIn(t["id"], GO, f"pick {i + 1}: {t.get('id')}")
                picks.append(t["id"])
                last = t["id"]
                rec = {"record_id": f"sim:{i}", "session_id": "sim", "ts": ts0 + i, "skill": "math",
                       "exercise": t["id"], "learner_answer": "", "score": rng.choice([10, 10, 7, 4]),
                       "corrections": [], "competency": t["id"]}
                with (Path(d) / ".records" / "sim.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
            self.assertEqual(len(picks), 20)
            self.assertGreater(len(set(picks)), 1)

    def test_every_active_competence_comes_up_early(self):
        # 2026-11-03 (Albert, llvm): one new competence per SECTION hid divisibility and
        # factorisation behind `integers`. With go_active each active one is its own slot.
        rng = random.Random(7)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".records").mkdir()
            seen, last = [], None
            ts0 = int(dt.datetime(2026, 11, 3, 9, 0).timestamp() * 1000)
            for i in range(12):  # all ten within the first twelve exercises (was the 36th before)
                t = cu.next_target(self.cur, d, TODAY, last_id=last)
                seen.append(t["id"])
                last = t["id"]
                rec = {"record_id": f"sim:{i}", "session_id": "sim", "ts": ts0 + i, "skill": "math",
                       "exercise": t["id"], "learner_answer": "", "score": rng.choice([10, 7, 4]),
                       "corrections": [], "competency": t["id"]}
                with (Path(d) / ".records" / "sim.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
            self.assertEqual(set(seen), set(GO), sorted(set(GO) - set(seen)))

    def test_the_path_view_lists_the_go_competences_by_name(self):
        # 2026-11-03 (Albert): in Stats it was not clear which competences the Go would bring.
        view = cu.path_view(self.cur, cu.new_path(self.cur), TODAY)
        self.assertEqual({x["id"] for x in view["go_active"]}, set(GO))
        self.assertTrue(all(x["name"] for x in view["go_active"]))
        items = [it for s in view["sections"] for it in s["items"]]
        self.assertTrue(all(it["asleep"] == (it["id"] not in GO) for it in items))

    def test_the_go_path_ids_are_the_level_ids(self):
        # the Go note and the bank look competences up by id: every active id has bank items
        for cid in GO:
            self.assertTrue((BANK / f"{cid}.json").is_file() or (BANK / "steps" / f"{cid}__steps.json").is_file(), cid)


class ListAndFactorisationGradeTest(unittest.TestCase):
    def test_a_list_is_a_set(self):
        for given in ("1, 2, 23, 46", "46 23 2 1", "1; 2; 23; 46", "{1, 2, 23, 46}", "1 i 2 i 23 i 46", "1, 1, 2, 23, 46"):
            r = mathgrade.grade_list("1, 2, 23, 46", given)
            self.assertEqual((r["score"], r["verdict"]), (10, "correct"), given)

    def test_missing_and_extra_numbers_are_named(self):
        r = mathgrade.grade_list("1, 2, 23, 46", "1, 2, 46")
        self.assertEqual((r["verdict"], r["score"], r["note"]), ("near", 7, "et falta el 23"))
        r = mathgrade.grade_list("1, 2, 23, 46", "1, 2, 5, 23, 46")
        self.assertEqual(r["verdict"], "near")
        self.assertIn("sobra el 5", r["note"])
        self.assertLess(r["score"], 8)

    def test_wrong_and_empty_lists(self):
        self.assertEqual(mathgrade.grade_list("1, 2, 23, 46", "")["verdict"], "empty")
        self.assertEqual(mathgrade.grade_list("1, 2, 23, 46", "hola")["verdict"], "wrong")
        self.assertEqual(mathgrade.grade_list("1, 2, 23, 46", "5, 7")["verdict"], "wrong")

    def test_a_factorisation_is_prime_powers_in_any_order(self):
        for given in ("2^3 · 3^2 · 5", "5·3²·2³", "2*2*2*3*3*5", "2^3 x 3^2 x 5", "3^2·2^3·5"):
            self.assertEqual(mathgrade.grade_factorization("2^3 · 3^2 · 5", given)["verdict"], "correct", given)

    def test_the_right_value_not_factorised_is_near_not_correct(self):
        for given in ("360", "4 · 90", "2^2 · 3^2 · 5 · 2"):
            r = mathgrade.grade_factorization("2^3 · 3^2 · 5", given)
            self.assertIn(r["verdict"], ("near", "correct") if given == "2^2 · 3^2 · 5 · 2" else ("near",), given)
        self.assertEqual(mathgrade.grade_factorization("2^3 · 3^2 · 5", "360")["verdict"], "near")

    def test_a_wrong_factorisation_says_what_it_gives(self):
        r = mathgrade.grade_factorization("2^3 · 3^2 · 5", "2^3 · 3^2")
        self.assertEqual(r["verdict"], "wrong")
        self.assertIn("72", r["note"])
        self.assertEqual(mathgrade.grade_factorization("2^3 · 3^2 · 5", "2^2 · 3^2 · 5")["verdict"], "near")

    def test_bank_grades_a_set_item_as_a_set(self):
        it = {"id": "m7.x.001", "competence": "m7.x", "type": "set", "instruction": "Escriu-los.",
              "problem": "Escriu tots els divisors de 46", "answer": "1, 2, 23, 46", "also_accept": [],
              "options": [], "why": "D(46) = {1, 2, 23, 46}.", "status": "validated", "source": "t",
              "spec": "divisors:46"}
        self.assertEqual(bankmod.grade(it, "46, 23, 2, 1")["score"], 10)
        r = bankmod.grade(it, "1 2 46")
        self.assertEqual(r["verdict"], "near")
        self.assertIn("et falta el 23", r["note"])
        self.assertIn("1, 2, 23, 46", r["correct_version"])

    def test_bank_grades_a_factorisation_item_with_its_correct_version(self):
        it = {"id": "m7.x.001", "competence": "m7.x", "type": "factorization", "instruction": "Descompon.",
              "problem": "Descompon 360 en factors primers", "answer": "2^3 · 3^2 · 5", "also_accept": [],
              "options": [], "why": "360 ÷ 2 = 180; …", "status": "validated", "source": "t", "spec": "fac:360"}
        self.assertEqual(bankmod.grade(it, "5 · 2³ · 3²")["score"], 10)
        self.assertEqual(bankmod.grade(it, "360")["verdict"], "near")
        self.assertIn("2^3 · 3^2 · 5", bankmod.grade(it, "2^3 · 3^2")["correct_version"])

    def test_a_word_choice_is_graded_by_its_word(self):
        it = {"id": "m7.x.002", "competence": "m7.x", "type": "choose", "instruction": "Primer o compost?",
              "problem": "És 91 primer o compost?", "answer": "compost", "also_accept": [],
              "options": ["primer", "compost"], "why": "91 = 7 · 13.", "status": "validated", "source": "t",
              "spec": "prime:91"}
        self.assertEqual(bankmod.grade(it, "compost")["score"], 10)
        self.assertEqual(bankmod.grade(it, "Compost")["score"], 10)
        self.assertEqual(bankmod.grade(it, "primer")["verdict"], "wrong")


class M7GoItemsTest(unittest.TestCase):
    def test_a_wrong_answer_is_refused_by_the_validator(self):
        good = mb.build_item("divisors_multiples", random.Random(1), "m7.divisors_multiples", 1, "t")
        while good["type"] != "set":
            good = mb.build_item("divisors_multiples", random.Random(random.randrange(10**6)), "m7.divisors_multiples", 1, "t")
        self.assertEqual(mb.validate_item(good), [])
        self.assertTrue(mb.validate_item(dict(good, answer=good["answer"] + ", 999")))
        fac = mb.build_item("prime_factorization", random.Random(4), "m7.prime_factorization", 1, "t")
        while fac["type"] != "factorization":
            fac = mb.build_item("prime_factorization", random.Random(random.randrange(10**6)), "m7.prime_factorization", 1, "t")
        self.assertEqual(mb.validate_item(fac), [])
        self.assertTrue(mb.validate_item(dict(fac, answer="2 · " + fac["answer"])))

    def test_a_word_choice_with_a_wrong_label_is_refused(self):
        it = {"id": "m7.primes.001", "competence": "m7.primes", "type": "choose", "instruction": "x",
              "problem": "És 91 primer o compost?", "answer": "primer", "also_accept": [],
              "options": ["primer", "compost"], "why": "91 = 7 · 13", "status": "validated",
              "source": "t", "spec": "prime:91"}
        self.assertTrue(mb.validate_item(it))
        self.assertEqual(mb.validate_item(dict(it, answer="compost")), [])

    def test_each_active_competence_has_at_least_24_valid_items(self):
        for cid in sorted(GO):
            items = bankmod.load_bank(REPO, "math-m7", cid, None)
            self.assertGreaterEqual(len(items), 24, cid)
            for it in items:
                if it["type"] == "steps":  # a steps item is graded by its whole trace
                    answer = "\n".join(bankmod._steps_correct_version(it).splitlines())
                else:
                    answer = it["answer"]
                self.assertEqual(bankmod.grade(it, answer)["score"], 10, f"{cid} {it['id']}")

    def test_the_long_integers_are_at_least_half(self):
        items = bankmod.load_bank(REPO, "math-m7", "m7.integers", None)
        long_ones = [it for it in items if sum(it["problem"].count(op) for op in "+-·÷^") >= 5]
        self.assertGreaterEqual(len(long_ones), 12)
        self.assertGreaterEqual(len(items), 24)


if __name__ == "__main__":
    unittest.main()
