"""Workbench source labels share one vocabulary with the ESE runs panel."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class SourceLabelsTest(unittest.TestCase):
    def test_source_pill_uses_panel_vocabulary(self):
        text = (ROOT / "apps" / "web" / "src" / "components" / "SourcePill.tsx").read_text(encoding="utf-8")
        self.assertIn('runtime: "LOCAL RUNTIME"', text)
        self.assertIn('snapshot: "STATIC SNAPSHOT"', text)
        self.assertIn('emptyLabel = "NO DATA"', text)

    def test_topbar_badge_uses_panel_vocabulary(self):
        text = (ROOT / "apps" / "web" / "src" / "components" / "TopBar.tsx").read_text(encoding="utf-8")
        self.assertIn("STATIC SNAPSHOT", text)
        self.assertIn("LOCAL RUNTIME", text)
        self.assertNotIn("演示数据 · 静态", text)

    def test_ese_panel_labels_match(self):
        text = (ROOT / "apps" / "web" / "src" / "components" / "EseRunsPanel.tsx").read_text(encoding="utf-8")
        self.assertIn("LOCAL RUNTIME", text)
        self.assertIn("STATIC SNAPSHOT", text)
        self.assertIn("NO DATA", text)


if __name__ == "__main__":
    unittest.main()
