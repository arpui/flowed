#!/usr/bin/env python3
"""Flash for language drill and dictation lists (docs/ENCARREC-LANG-L1-FLASH.md §2, §3, §5): the Python
side counts the same items as the server (server/src/flash.ts, langItems), the new A1 and A2 lists are
there, and the A1 requirement counts the 16 lists (13 of them needed)."""
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "hooks"))

import curriculum as cu  # noqa: E402


def node_json(expr: str):
    """Evaluates `expr` (with `m` = server/src/flash.ts as a module) in node and returns its JSON."""
    script = (
        f"const m = await import({json.dumps(str(REPO_ROOT / 'server' / 'src' / 'flash.ts'))});"
        f"console.log(JSON.stringify({expr}));"
    )
    proc = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)


def server_lang_lists(root: Path, stem: str) -> list[dict]:
    """The language lists of one level as server/src/flash.ts serves them (id and word ids), read by node."""
    return node_json(
        f"m.loadFlashLists({json.dumps(str(root))}, 'curriculum/flash/{stem}', 'ca')"
        ".map((l) => ({ id: l.id, kind: l.kind ?? null, words: l.words.map((w) => w.id) }))"
    )


def write_lang(root: Path, stem: str, files: dict[str, dict]) -> None:
    d = root / "curriculum" / "flash" / stem
    d.mkdir(parents=True)
    for name, body in files.items():
        (d / name).write_text(json.dumps(body), encoding="utf-8")


DRILL_ITEMS = [
    {"id": "go", "prompt": "go → past", "answer": ["went"]},
    {"id": "go", "prompt": "go → past again", "answer": ["went"]},          # repeated id: the first stays
    {"id": "", "prompt": "x", "answer": ["x"]},                             # no id
    {"id": "noans", "prompt": "x", "answer": []},                           # no answer
    {"id": "noprompt", "answer": ["x"]},                                    # no prompt
    {"id": "fewopts", "prompt": "… apple", "answer": ["an"], "options": ["an"]},          # one option
    {"id": "notin", "prompt": "… apple", "answer": ["the"], "options": ["a", "an"]},      # answer not an option
    {"id": "choice", "prompt": "… apple", "answer": ["an"], "options": ["a", "an"]},
    {"id": "list-of-null", "prompt": "x", "answer": ["x"], "options": None},              # options present but empty
]
DICT_ITEMS = [
    {"id": "hello", "say": "Hello", "answer": ["Hello"]},
    {"id": "nosay", "answer": ["x"]},
    {"id": "opts", "say": "Bye", "answer": ["Bye"], "options": ["Bye", "Hi"]},          # a dictation has no options
    {"id": "hello", "say": "Hello again", "answer": ["Hello again"]},                  # repeated id
]


class LangMirror(unittest.TestCase):
    """The ids the Python side counts are the ids the server serves, for the shipped lists and for bad ones."""

    def test_shipped_a1_and_a2_lists_match_the_server(self):
        for stem in ("en-A1", "en-A2"):
            with self.subTest(stem=stem):
                py = cu.flash_lists(REPO_ROOT, stem)
                srv = server_lang_lists(REPO_ROOT, stem)
                self.assertEqual([(l["id"], l["words"]) for l in py], [(l["id"], l["words"]) for l in srv])

    def test_a_bad_drill_and_dictation_drop_what_the_server_drops(self):
        tmp = Path(tempfile.mkdtemp(prefix="flash-lang-"))
        write_lang(tmp, "en-Z1", {
            "01-drill.json": {"id": "z.drill", "level": "Z1", "kind": "drill", "title": {"en": "d"}, "items": DRILL_ITEMS},
            "02-dict.json": {"id": "z.dict", "level": "Z1", "kind": "dictation", "title": {"en": "t"}, "items": DICT_ITEMS},
            "03-nothing.json": {"id": "z.none", "level": "Z1", "kind": "dictation", "title": {"en": "n"},
                                "items": [{"id": "a", "answer": ["a"]}]},
        })
        py = {l["id"]: l["words"] for l in cu.flash_lists(tmp, "en-Z1")}
        srv = {l["id"]: l["words"] for l in server_lang_lists(tmp, "en-Z1")}
        self.assertEqual(py, srv)
        self.assertEqual(py["z.drill"], ["go", "choice"])
        self.assertEqual(py["z.dict"], ["hello"])
        self.assertEqual(py["z.none"], [])


class LevelCounts(unittest.TestCase):
    def test_a1_asks_for_80_percent_of_16_lists_so_13_are_needed(self):
        a1 = cu.load_curriculum(REPO_ROOT / "curriculum" / "en-A1.md")
        self.assertEqual(a1["meta"]["flash_share"], 80)
        lists = cu.flash_lists(REPO_ROOT, "en-A1")
        self.assertEqual(len(lists), 16)
        fp = cu.flash_progress(REPO_ROOT, a1, Path(tempfile.mkdtemp()), "en-A1")
        self.assertEqual((fp["total"], fp["needed"], fp["closed"], fp["met"]), (16, math.ceil(16 * 80 / 100), 0, False))
        self.assertEqual(fp["needed"], 13)

    def test_a2_has_seven_lists_and_no_requirement(self):
        a2 = cu.load_curriculum(REPO_ROOT / "curriculum" / "en-A2.md")
        self.assertNotIn("flash_share", a2["meta"])
        self.assertEqual(len(cu.flash_lists(REPO_ROOT, "en-A2")), 7)
        fp = cu.flash_progress(REPO_ROOT, a2, Path(tempfile.mkdtemp()), "en-A2")
        self.assertTrue(fp["met"])

    def test_the_new_lists_have_their_items(self):
        a1_lists = {l["id"]: l["words"] for l in cu.flash_lists(REPO_ROOT, "en-A1")}
        self.assertEqual(len(a1_lists["en-A1.flash.third-person"]), 16)
        self.assertEqual(len(a1_lists["en-A1.flash.dictation-a1"]), 16)


if __name__ == "__main__":
    unittest.main()
