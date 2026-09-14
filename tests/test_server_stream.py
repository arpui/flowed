#!/usr/bin/env python3
"""Server-side checks that can run without bun.

`node --experimental-strip-types` runs the TypeScript directly, so the parts of
the server that are fragile — reassembling streamed tool_calls, and the setup
tool that writes a learner's profile — are covered by the normal test suite
instead of being discovered in a live session. Every `server/test/*.test.ts`
harness is run. Skipped when node is missing or too old.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_DIR = REPO_ROOT / "server" / "test"


class ServerHarnessTest(unittest.TestCase):
    def test_every_typescript_harness_passes(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        harnesses = sorted(HARNESS_DIR.glob("*.test.ts"))
        self.assertTrue(harnesses, f"no harness found in {HARNESS_DIR}")
        for harness in harnesses:
            with self.subTest(harness=harness.name):
                proc = subprocess.run(
                    [node, "--experimental-strip-types", str(harness)],
                    cwd=REPO_ROOT, capture_output=True, text=True,
                )
                combined = proc.stdout + proc.stderr
                if proc.returncode != 0 and "experimental-strip-types" in combined \
                        and "not allowed" in combined.lower():
                    self.skipTest("this node build cannot strip TypeScript types")
                self.assertEqual(proc.returncode, 0, combined)


if __name__ == "__main__":
    unittest.main()
