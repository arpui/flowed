"""Does a graded answer end up saved and graded, in BOTH domains? (2026-10-08)

Real pipeline minus the model: structured records (what the server's record
tool writes) -> persist-session.build_report -> update-db.py -> the six DBs, then
`flowed-check.py reconcile` and `taxonomy` must both be clean. A fresh profile
per domain, never ~/.flowed.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODAY = date.today().isoformat()

CASES = {
    "language": {
        "records": [
            {"skill": "grammar", "score": 10, "item_id": "a1.can_ability.001", "sm2_quality": 5, "corrections": []},
            {"skill": "grammar", "score": 4, "corrections": [{"category": "tenses", "wrong": "I goed", "right": "I went"}]},
            {"skill": "vocabulary", "score": 8, "corrections": []},
            {"skill": "writing", "score": 6, "corrections": [{"category": "agreement", "wrong": "he have", "right": "he has"}]},
        ],
        "skills": {"grammar", "vocabulary", "writing"},
        "cats": {"tenses", "agreement"},
    },
    "math": {
        "records": [
            {"skill": "computation", "score": 10, "item_id": "m7.props_grouping.001", "sm2_quality": 5, "corrections": []},
            {"skill": "steps", "score": 4, "corrections": [{"category": "calculation", "wrong": "7+3=11", "right": "7+3=10"}]},
            {"skill": "reasoning", "score": 8, "corrections": []},
            {"skill": "problems", "score": 6, "corrections": [{"category": "wrong_operation", "wrong": "4+10", "right": "4*10"}]},
        ],
        "skills": {"computation", "steps", "reasoning", "problems"},
        "cats": {"calculation", "wrong_operation"},
    },
}


def _load_persist(data_dir):
    os.environ["FLOWED_DATA_DIR"] = str(data_dir)
    spec = importlib.util.spec_from_file_location("persist_session", ROOT / "hooks" / "persist-session.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "hooks"))
    spec.loader.exec_module(mod)
    return mod


class PersistenceBothDomains(unittest.TestCase):
    def _run_domain(self, domain):
        case = CASES[domain]
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "FLOWED_HOME": home}
            pid = f"test-persist-{domain}"
            subprocess.run(["bash", str(ROOT / "scripts" / "new-user.sh"), pid, "--domain", domain],
                           check=True, capture_output=True, text=True, env=env, cwd=ROOT)
            d = Path(home) / pid
            sr = json.loads((d / "spaced-repetition.json").read_text(encoding="utf-8"))
            for rec in case["records"]:
                if rec.get("item_id"):
                    sr.setdefault("items", {})[rec["item_id"]] = {
                        "item_id": rec["item_id"], "item_type": "bank_item", "easiness_factor": 2.5,
                        "interval_days": 1, "repetitions": 0, "due_date": TODAY,
                        "last_reviewed": None, "review_history": []}
            (d / "spaced-repetition.json").write_text(json.dumps(sr), encoding="utf-8")
            (d / ".records").mkdir()
            recs = [{**r, "record_id": f"s1:m:{i}", "ts": 1000 + i, "exercise": f"ex {i}", "learner_answer": f"ans {i}"}
                    for i, r in enumerate(case["records"])]
            (d / ".records" / "ses_x.jsonl").write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")

            ps = _load_persist(d)
            report, _, _ = ps.build_report("ses_x", [], [], {}, override_session_id="session-001",
                                           data_dir_for_records=str(d))
            self.assertEqual(report["total_exercises"], 4)
            self.assertTrue(ps.run_update_db(report, str(d)))

            ld = lambda n: json.loads((d / n).read_text(encoding="utf-8"))
            prog = ld("progress-db.json")
            self.assertEqual(prog["overall_stats"]["total_exercises"], 4, domain)
            self.assertEqual(prog["overall_stats"]["total_correct"], 2, domain)  # score >= 8
            mastery = ld("mastery-db.json")["skills"]
            for k in case["skills"]:
                self.assertTrue(mastery[k]["last_practiced"], f"{domain}: {k} not practiced")
            pats = {k: v for k, v in ld("mistakes-db.json")["error_patterns"].items() if not k.startswith("example_")}
            self.assertEqual({p["category"] for p in pats.values()}, case["cats"], domain)
            self.assertEqual(len(ld("session-log.json")["sessions"][-1:]), 1)
            item = next(i for i in ld("spaced-repetition.json")["items"].values() if i.get("item_id") == case["records"][0]["item_id"])
            self.assertGreaterEqual(item["repetitions"], 1, f"{domain}: SM-2 item not reviewed")

            for chk in ("reconcile", "taxonomy"):
                r = subprocess.run([sys.executable, str(ROOT / "scripts" / "flowed-check.py"), chk, "--dir", str(d)],
                                   capture_output=True, text=True, cwd=ROOT)
                self.assertEqual(r.returncode, 0, f"{domain} {chk}:\n{r.stdout}{r.stderr}")

    # --- Capa A: persistence DURING the session, no End, no Capa B ----------
    def _capa_a(self, domain):
        import sqlite3
        import time
        case = CASES[domain]
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "FLOWED_HOME": home}
            pid = f"test-capa-a-{domain}"
            subprocess.run(["bash", str(ROOT / "scripts" / "new-user.sh"), pid, "--domain", domain],
                           check=True, capture_output=True, text=True, env=env, cwd=ROOT)
            d = Path(home) / pid
            prof = json.loads((d / "learner-profile.json").read_text(encoding="utf-8"))
            prof.setdefault("learner", {})["name"] = "Test"
            (d / "learner-profile.json").write_text(json.dumps(prof), encoding="utf-8")
            sr = json.loads((d / "spaced-repetition.json").read_text(encoding="utf-8"))
            first = case["records"][0]["item_id"]
            sr.setdefault("items", {})[first] = {
                "item_id": first, "item_type": "bank_item", "easiness_factor": 2.5, "interval_days": 1,
                "repetitions": 0, "due_date": TODAY, "last_reviewed": None, "review_history": []}
            (d / "spaced-repetition.json").write_text(json.dumps(sr), encoding="utf-8")
            (d / "sessions").mkdir(exist_ok=True)
            db = sqlite3.connect(d / "sessions" / "sessions.db")
            db.executescript("""
                CREATE TABLE session (id text PRIMARY KEY, project_id text, slug text, directory text,
                  title text, version text, agent text, model text, time_created integer,
                  time_updated integer, last_activity integer, metadata text);
                CREATE TABLE message (id text PRIMARY KEY, session_id text, time_created integer,
                  time_updated integer, data text);
                CREATE TABLE part (id text PRIMARY KEY, message_id text, session_id text,
                  time_created integer, time_updated integer, data text);""")
            now = int(time.time() * 1000)
            db.execute("INSERT INTO session VALUES ('ses_A','global','test','','FlowEd','0','learner','deep',?,?,?,NULL)",
                       (now - 600000, now, now))
            db.execute("INSERT INTO message VALUES ('m1','ses_A',?,?,?)", (now, now, json.dumps({"role": "user"})))
            db.execute("INSERT INTO part VALUES ('m1_p','m1','ses_A',?,?,?)",
                       (now, now, json.dumps({"type": "text", "text": '{"learner": {"name": "Test"}}'})))
            db.commit()
            db.close()
            (d / ".records").mkdir(exist_ok=True)
            recs = [{**r, "record_id": f"s:m:{i}", "ts": 1000 + i, "exercise": f"ex {i}", "learner_answer": f"ans {i}"}
                    for i, r in enumerate(case["records"])]
            rec_file = d / ".records" / "ses_A.jsonl"
            run_env = {**os.environ, "FLOWED_DATA_DIR": str(d)}

            def accumulate():
                r = subprocess.run([sys.executable, str(ROOT / "hooks" / "accumulate-session.py"),
                                    "--session-id", "ses_A", "--dir", str(d)],
                                   capture_output=True, text=True, env=run_env, cwd=ROOT)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            ld = lambda n: json.loads((d / n).read_text(encoding="utf-8"))
            # after 2 answers (session still open, nothing else has run)
            rec_file.write_text("\n".join(json.dumps(r) for r in recs[:2]), encoding="utf-8")
            accumulate()
            self.assertEqual(ld("progress-db.json")["overall_stats"]["total_exercises"], 2, domain)
            # same records again: idempotent, no double count
            accumulate()
            self.assertEqual(ld("progress-db.json")["overall_stats"]["total_exercises"], 2, domain)
            # two more answers
            rec_file.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
            accumulate()
            self.assertEqual(ld("progress-db.json")["overall_stats"]["total_exercises"], 4, domain)
            self.assertEqual(ld("progress-db.json")["overall_stats"]["total_correct"], 2, domain)
            for k in case["skills"]:
                self.assertTrue(ld("mastery-db.json")["skills"][k]["last_practiced"], f"{domain} {k}")
            cats = {p["category"] for k, p in ld("mistakes-db.json")["error_patterns"].items() if not k.startswith("example_")}
            self.assertEqual(cats, case["cats"], domain)
            self.assertGreaterEqual(ld("spaced-repetition.json")["items"][first]["repetitions"], 1, domain)
            self.assertEqual(len(ld("session-log.json")["sessions"]), 1, f"{domain}: session-log must hold exactly the live session (no template placeholder)")
            self.assertEqual(ld("session-log.json")["metadata"]["total_sessions"], 1, domain)
            for chk in ("reconcile", "taxonomy"):
                r = subprocess.run([sys.executable, str(ROOT / "scripts" / "flowed-check.py"), chk, "--dir", str(d)],
                                   capture_output=True, text=True, cwd=ROOT)
                self.assertEqual(r.returncode, 0, f"{domain} {chk}:\n{r.stdout}{r.stderr}")
            # closing the session (Capa B) must not change a single total
            r = subprocess.run([sys.executable, str(ROOT / "hooks" / "persist-session.py"), "ses_A", "--dir", str(d)],
                               capture_output=True, text=True, env=run_env, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(ld("progress-db.json")["overall_stats"]["total_exercises"], 4, domain)

    def test_capa_a_language_without_end(self):
        self._capa_a("language")

    def test_capa_a_math_without_end(self):
        self._capa_a("math")

    def test_language(self):
        self._run_domain("language")

    def test_math(self):
        self._run_domain("math")


if __name__ == "__main__":
    unittest.main()
