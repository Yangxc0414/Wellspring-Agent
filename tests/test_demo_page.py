"""Demo replay pages: main full-chain version plus the 24-source frontier variant."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class DemoPagesTest(unittest.TestCase):
    def test_demo_page_is_a_generated_run_replay(self):
        page = (ROOT / "demo" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-dl-page="demo"', page)
        self.assertIn("data-demo-run=", page)
        self.assertIn("demo-legibility.js", page)
        self.assertIn("输入", page)
        self.assertIn("产物", page)
        self.assertNotIn("sim-badge", page)

    def test_frontier_variant_is_generated_and_linked(self):
        page = (ROOT / "demo" / "frontier" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-dl-page="demo"', page)
        self.assertIn("data-demo-run=", page)
        self.assertIn("24", page)
        self.assertIn("候选", page)
        main = (ROOT / "demo" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="frontier/"', main)

    def test_chain_page_shows_end_to_end_provenance(self):
        page = (ROOT / "demo" / "run" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-dl-page="demo"', page)
        self.assertIn("data-demo-chain=", page)
        self.assertIn("来龙去脉", page)
        self.assertIn("S1 文献证据", page)
        self.assertIn("成稿审计", page)
        self.assertIn("REAL RUN", page)
        self.assertIn("../../assets/demo-legibility.css", page)
        replay = (ROOT / "demo" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="run/"', replay)

    def test_chain_copy_matches(self):
        source = (ROOT / "demo" / "run" / "index.html").read_text(encoding="utf-8")
        copied = (ROOT / "site" / "demo" / "run" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(source, copied)

    def test_site_copy_matches_generated_tree(self):
        for relative in ("index.html", "frontier/index.html"):
            source = (ROOT / "demo" / relative).read_text(encoding="utf-8")
            copied = (ROOT / "site" / "demo" / relative).read_text(encoding="utf-8")
            self.assertEqual(source, copied, relative)

    def test_old_agent_workbench_is_replaced_by_a_redirect(self):
        page = (ROOT / "site" / "agent" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-dl-page="agent"', page)
        self.assertIn("../app/", page)
        self.assertIn("已合并到真实工作台", page)
        self.assertFalse((ROOT / "site" / "agent" / "agent.js").exists())
        self.assertFalse((ROOT / "site" / "agent" / "agent.css").exists())

    def test_legacy_demo_artifacts_are_gone(self):
        self.assertFalse((ROOT / "demo" / "dist").exists())
        legacy = list((ROOT / "demo").glob("*.qoder.site"))
        self.assertEqual(legacy, [])


if __name__ == "__main__":
    unittest.main()
