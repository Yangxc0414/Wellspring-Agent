"""The documented RSI demo chain must actually run from a clean directory.

#81's readback acceptance was blocked by a ledger that no documented step produced; the fix is an
executable walkthrough (scripts/demo_walkthrough.py). This test runs it in a temp dir and asserts
the chain completes and the story carries a verdict, so the demo cannot silently rot again.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class DemoWalkthroughTest(unittest.TestCase):
    def test_the_offline_chain_runs_and_reports_a_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(REPO / "scripts" / "demo_walkthrough.py"), "--work-dir", tmp],
                cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding="utf-8", errors="replace", timeout=300,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout[-800:])
            story = json.loads((Path(tmp) / "story.json").read_text(encoding="utf-8"))
            self.assertIn("gate_verdict", story["summary"])
            self.assertIn(story["summary"]["gate_verdict"],
                          ("informative", "gate_uninformative", "awaiting_decisions", "no_episodes"))
            self.assertTrue((Path(tmp) / "real-ledger.json").is_file())


if __name__ == "__main__":
    unittest.main()
