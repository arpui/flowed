#!/usr/bin/env python3
"""P1-9: one configuration, three layers, a known precedence.

config/fluent.json describes the project, .env says how this machine differs,
the environment wins over both. The bash scripts rely on that order, so it is
worth a test rather than a comment.
"""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "fluent_config_mod", REPO_ROOT / "scripts" / "flowed-config.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ConfigLayersTest(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.tmp = Path(tempfile.mkdtemp(prefix="fluent-cfg-"))
        self.mod.CONFIG = self.tmp / "fluent.json"
        self.mod.ENV_FILE = self.tmp / ".env"
        self.mod.CONFIG.write_text(json.dumps({
            "paths": {"model_dir": "/models"},
            "models": {
                "deep": {"backend": "native", "managed": True, "model": "/models/deep.gguf",
                         "port": 12322, "gpu": 1, "ctx": 32768},
                "face": {"enabled": False, "model": "/models/face.gguf", "port": 12323},
            },
            "webs": {"a-en": 4100, "b-en": 4101},
        }), encoding="utf-8")
        self._saved = {k: v for k, v in os.environ.items() if k.startswith("FLOWED_")}
        for k in self._saved:
            del os.environ[k]

    def tearDown(self):
        for k in [k for k in os.environ if k.startswith("FLOWED_")]:
            del os.environ[k]
        os.environ.update(self._saved)

    def test_json_alone_produces_the_script_variables(self):
        values = self.mod.resolve()
        self.assertEqual(values["FLOWED_DEEP_PORT"], "12322")
        self.assertEqual(values["FLOWED_DEEP_MODEL"], "/models/deep.gguf")
        self.assertEqual(values["FLOWED_DEEP_MANAGED"], "1")
        self.assertEqual(values["FLOWED_FACE_ENABLED"], "0")
        self.assertEqual(values["FLOWED_WEBS"], "a-en:4100 b-en:4101")

    def test_env_file_overrides_the_json(self):
        self.mod.ENV_FILE.write_text("FLOWED_DEEP_PORT=13000\n# comment\nFLOWED_DEEP_GPU=0\n",
                                     encoding="utf-8")
        values = self.mod.resolve()
        self.assertEqual(values["FLOWED_DEEP_PORT"], "13000")
        self.assertEqual(values["FLOWED_DEEP_GPU"], "0")
        self.assertEqual(values["FLOWED_DEEP_MODEL"], "/models/deep.gguf")

    def test_environment_overrides_everything(self):
        self.mod.ENV_FILE.write_text("FLOWED_DEEP_PORT=13000\n", encoding="utf-8")
        os.environ["FLOWED_DEEP_PORT"] = "14000"
        self.assertEqual(self.mod.resolve()["FLOWED_DEEP_PORT"], "14000")

    def test_missing_config_is_not_fatal(self):
        """No config at all: built-in defaults, but no model path — which is the
        signal the launcher checks before refusing to start."""
        self.mod.CONFIG = self.tmp / "does-not-exist.json"
        self.mod.ENV_FILE = self.tmp / "does-not-exist.env"
        values = self.mod.resolve()
        self.assertNotIn("FLOWED_DEEP_MODEL", values)
        self.assertEqual(values["FLOWED_DEEP_PORT"], "12322")


class RepoConfigTest(unittest.TestCase):
    def test_the_committed_config_is_valid_and_complete(self):
        mod = _load()
        values = mod.resolve(include_env_file=False, include_environ=False)
        # FLOWED_WEBS deliberately not here: the profile→port map is per
        # machine and carries real learners' names, so it lives in .env, which
        # is not committed.
        for key in ("FLOWED_DEEP_MODEL", "FLOWED_DEEP_PORT", "FLOWED_DEEP_CTX",
                    "FLOWED_FACE_PORT"):
            self.assertIn(key, values, f"config/fluent.json does not define {key}")


if __name__ == "__main__":
    unittest.main()
