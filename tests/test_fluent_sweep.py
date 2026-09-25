"""El sweep ha de mesurar el que diu que mesura.

El 2026-09-19 es va descobrir que `temp06` mai havia corregut a 0,6: el sweep
escrivia la temperatura a config/fluent.json, però config/fluent-models.json (una
capa per sobre) la fixava a 0,2. Cap comprovació ho deia i les taules
comparaven soroll amb soroll. Aquests tests fixen les dues meitats de l'arreglo:
el mostreig viatja per FLOWED_MODELS_FILE amb les claus que el servidor llegeix,
i el sweep es nega a córrer un setting que el servidor no està fent servir.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import re
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("fluent_sweep", REPO / "scripts" / "flowed-sweep.py")
sweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sweep)


class ModelsFileTest(unittest.TestCase):
    def write(self, knobs):
        with tempfile.TemporaryDirectory() as d:
            path = sweep.write_models_file(knobs, Path(d) / "models.json")
            return json.loads(path.read_text(encoding="utf-8"))

    def test_base_is_temperature_02_and_nothing_else(self):
        self.assertEqual(self.write({}), {"deep": {"temperature": 0.2}})

    def test_the_setting_wins_over_the_base_temperature(self):
        self.assertEqual(self.write({"temperature": 0.6})["deep"]["temperature"], 0.6)

    def test_keys_are_the_camel_case_the_server_reads_and_ints_stay_ints(self):
        deep = self.write({"temperature": 0.6, "top_k": 40.0, "repeat_last_n": 512.0,
                           "presence_penalty": 0.4, "frequency_penalty": 0.3,
                           "repeat_penalty": 1.15, "top_p": 0.9})["deep"]
        self.assertEqual(deep, {"temperature": 0.6, "topK": 40, "repeatLastN": 512,
                                "presencePenalty": 0.4, "frequencyPenalty": 0.3,
                                "repeatPenalty": 1.15, "topP": 0.9})
        self.assertIsInstance(deep["topK"], int)
        self.assertIsInstance(deep["repeatLastN"], int)

    def test_every_key_written_is_one_the_server_reads(self):
        """Un nom mal escrit aquí no dóna error enlloc: el servidor l'ignora."""
        src = (REPO / "server" / "src" / "index.ts").read_text(encoding="utf-8")
        for snake, camel in sweep.MODELS_FILE_KEYS.items():
            self.assertIsNotNone(re.search(rf"\b{camel}\b", src),
                                 f"{snake} → {camel}: index.ts no el llegeix")

    def test_every_knob_has_a_file_key(self):
        self.assertEqual(set(sweep.KNOBS), set(sweep.MODELS_FILE_KEYS))


class SamplingCheckTest(unittest.TestCase):
    def test_the_bug_itself_asked_06_server_says_02(self):
        problems = sweep.sampling_problems({"temperature": 0.6},
                                           {"temperature": 0.2, "top_p": 0.95})
        self.assertEqual(len(problems), 1)
        self.assertIn("temperature", problems[0])

    def test_matching_sampling_has_no_problems(self):
        self.assertEqual(sweep.sampling_problems(
            {"temperature": 0.6, "repeat_last_n": 512},
            {"temperature": 0.6, "top_p": 0.95, "repeat_last_n": 512}), [])

    def test_base_means_base(self):
        self.assertEqual(sweep.sampling_problems({}, {"temperature": 0.2, "top_p": 0.95}), [])

    def test_a_knob_nobody_asked_for_is_a_problem(self):
        """Si una capa de configuració hi posa un presence_penalty, "base" ja
        no és base i la comparació és falsa."""
        problems = sweep.sampling_problems({}, {"temperature": 0.2, "top_p": 0.95,
                                                "presence_penalty": 0.4})
        self.assertEqual(len(problems), 1)
        self.assertIn("presence_penalty", problems[0])

    def test_a_knob_that_never_arrived_is_a_problem(self):
        problems = sweep.sampling_problems({"repeat_last_n": 512}, {"temperature": 0.2})
        self.assertTrue(any("repeat_last_n" in p for p in problems))

    def test_top_p_default_is_not_a_problem_but_a_wrong_asked_one_is(self):
        self.assertEqual(sweep.sampling_problems({}, {"temperature": 0.2, "top_p": 0.95}), [])
        self.assertTrue(sweep.sampling_problems({"top_p": 0.8}, {"temperature": 0.2, "top_p": 0.95}))


class _Health(BaseHTTPRequestHandler):
    PASSWORD = "s3cret"
    PAYLOAD = {"ok": True, "sampling": {"temperature": 0.6, "top_p": 0.95}}

    def do_GET(self):  # noqa: N802
        good = "Basic " + base64.b64encode(f"opencode:{self.PASSWORD}".encode()).decode()
        if self.path != "/api/global/health" or self.headers.get("Authorization") != good:
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps(self.PAYLOAD).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silent
        pass


class EffectiveSamplingTest(unittest.TestCase):
    def setUp(self):
        self.srv = HTTPServer(("127.0.0.1", 0), _Health)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.tmp = tempfile.TemporaryDirectory()
        self.prof = Path(self.tmp.name)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def test_reads_what_the_running_app_reports(self):
        (self.prof / ".web-password").write_text("s3cret\n")
        got = sweep.effective_sampling(self.port, self.prof, wait=2)
        self.assertEqual(got, {"temperature": 0.6, "top_p": 0.95})

    def test_a_wrong_password_is_none_not_an_empty_dict(self):
        """{} voldria dir "el servidor no porta cap paràmetre"; això és "no m'ho ha dit"."""
        (self.prof / ".web-password").write_text("nope\n")
        self.assertIsNone(sweep.effective_sampling(self.port, self.prof, wait=1.2))

    def test_nothing_listening_is_none(self):
        (self.prof / ".web-password").write_text("s3cret\n")
        self.assertIsNone(sweep.effective_sampling(1, self.prof, wait=1.2))


class ParseSettingTest(unittest.TestCase):
    def test_parses_name_and_knobs(self):
        self.assertEqual(sweep.parse_setting("temp06:temperature=0.6"),
                         ("temp06", {"temperature": 0.6}))
        self.assertEqual(sweep.parse_setting("base:"), ("base", {}))

    def test_rejects_unknown_knobs(self):
        with self.assertRaises(SystemExit):
            sweep.parse_setting("x:temprature=0.6")


REAL_START_LOG = """
Fluent web UP (mode=app, profile=test-en, port=4103)
  local:    http://localhost:4103
  log:      /tmp/fluent-web-4103.log
  model:    deep  (tutor, chat, sessions) — OK (port 12322)
  model:    face  (vocab, review, progress, setup) — NOT RUNNING (port 12323)
"""


class DeepModelDownTest(unittest.TestCase):
    def test_face_off_by_design_is_not_a_dead_model(self):
        """La sortida real del 2026-09-20: deep OK, face apagat. El bench es va
        aturar dient «el model NO corre» amb el deep funcionant."""
        self.assertFalse(sweep.deep_model_down(REAL_START_LOG))

    def test_deep_down_is_detected(self):
        self.assertTrue(sweep.deep_model_down(
            REAL_START_LOG.replace("deep  (tutor, chat, sessions) — OK",
                                   "deep  (tutor, chat, sessions) — NOT RUNNING")))

    def test_empty_log_is_not_evidence_of_anything(self):
        self.assertFalse(sweep.deep_model_down(""))


class SingleSourceTest(unittest.TestCase):
    """Un paràmetre, un lloc. config/fluent-models.json repetia fluent.json i hi
    guanyava: un `temperature` editat a fluent.json no arribava al servidor."""

    def test_the_shadowing_file_is_gone(self):
        self.assertFalse((REPO / "config" / "fluent-models.json").exists(),
                         "una segona font de paràmetres: fluent.json ja no mana")

    def test_the_server_does_not_load_it_by_itself(self):
        src = (REPO / "server" / "src" / "index.ts").read_text(encoding="utf-8")
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith(("//", "*", "/*")))
        self.assertNotIn("fluent-models.json", code)


class UngradedRunsTest(unittest.TestCase):
    def test_the_count_is_read_from_the_summary(self):
        text = (
            "=== resum de 6 execucions ===\n"
            "  ✅ posa nota\n"
            "\n  execucions sense cap qualificació: 1 de 6\n"
            "\n  el guard del servidor ha actuat 33 cop(s) en total  (5.5 per execució)\n"
        )
        got = sweep.read_result(text)
        self.assertEqual(got["ungraded"], 1)
        self.assertEqual(got["guards"], 33)

    def test_an_older_log_without_the_line_counts_zero(self):
        self.assertEqual(sweep.read_result("=== resum de 2 execucions ===\n")["ungraded"], 0)


class TestbedScriptsTest(unittest.TestCase):
    """El banc i el banc manual comparteixen com deixen a punt perfil i model."""

    ROOT = Path(__file__).resolve().parent.parent

    def read(self, name):
        return (self.ROOT / "scripts" / name).read_text(encoding="utf-8")

    def code(self, name):
        """Sense els comentaris: el que l'script fa, no el que diu."""
        return "\n".join(l for l in self.read(name).splitlines()
                         if not l.lstrip().startswith("#"))

    def test_both_use_the_same_preparation(self):
        for name in ("flowed-bench.sh", "flowed-testbase.sh"):
            with self.subTest(script=name):
                body = self.read(name)
                self.assertIn("source scripts/lib-testbed.sh", body)
                self.assertIn("tb_ensure_profile", body)
                self.assertIn("tb_ensure_model", body)

    def test_the_preparation_is_not_copied_into_the_scripts(self):
        for name in ("flowed-bench.sh", "flowed-testbase.sh"):
            with self.subTest(script=name):
                body = self.code(name)
                self.assertNotIn("new-user.sh", body)
                self.assertNotIn("flowed-start.sh --models-only", body)

    def test_the_manual_bench_refuses_a_real_profile(self):
        self.assertIn("només corre en perfils de proves", self.read("flowed-testbase.sh"))

    def test_the_manual_bench_stops_an_old_app_before_it_seeds(self):
        body = self.code("flowed-testbase.sh")
        self.assertLess(body.index("l'aturo abans"), body.index("python3 scripts/flowed-seed.py"))

    def test_the_app_is_pointed_at_the_model_that_was_checked(self):
        self.assertIn("FLOWED_DEEP_BASE_URL", self.read("flowed-testbase.sh"))

    def test_the_manual_bench_says_it_wipes_the_day(self):
        self.assertIn("BUIDA", self.read("flowed-testbase.sh"))

    def test_all_the_shell_scripts_parse(self):
        import subprocess
        for name in ("lib-testbed.sh", "flowed-bench.sh", "flowed-testbase.sh"):
            with self.subTest(script=name):
                r = subprocess.run(["bash", "-n", str(self.ROOT / "scripts" / name)],
                                   capture_output=True, text=True)
                self.assertEqual(0, r.returncode, r.stderr)


if __name__ == "__main__":
    unittest.main()
