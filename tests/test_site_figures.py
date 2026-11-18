"""Demo figure captions declare provenance and a resolvable artifact path."""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PAGE = ROOT / "site" / "index.html"
ARTIFACT_RE = re.compile(r'data-artifact="([^"]+)"')


class FigureProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.text = PAGE.read_text(encoding="utf-8")

    def test_five_figures_declare_provenance(self):
        self.assertEqual(self.text.count("data-figure-provenance="), 5)

    def test_schematic_and_generated_are_both_present(self):
        self.assertIn('data-figure-provenance="schematic"', self.text)
        self.assertIn('data-figure-provenance="generated"', self.text)

    def test_every_figure_maps_to_an_existing_artifact(self):
        artifacts = ARTIFACT_RE.findall(self.text)
        self.assertEqual(len(artifacts), 5)
        missing = [path for path in artifacts if not (ROOT / path).is_file()]
        self.assertEqual(missing, [], "missing artifact paths: %s" % missing)

    def test_schematic_figures_link_to_runtime_evidence(self):
        self.assertGreaterEqual(self.text.count('href="#ese-run"'), 4)

    def test_generation_script_is_cited(self):
        self.assertIn("make_figure_loop.py", self.text)


if __name__ == "__main__":
    unittest.main()
