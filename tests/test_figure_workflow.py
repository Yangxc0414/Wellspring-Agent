import json
import tempfile
import unittest
from pathlib import Path

from research_agent.figure_workflow import (
    FigureWorkflowError,
    list_templates,
    render_template,
)


class FigureWorkflowTest(unittest.TestCase):
    def test_template_catalog_contains_vendored_astradraw_scenes(self):
        catalog = list_templates()
        ids = {item["id"] for item in catalog["templates"]}
        self.assertIn("calm-method", ids)
        self.assertIn("framework-example", ids)
        self.assertIn("survey-framework", ids)
        self.assertTrue(all(item["schematic"] for item in catalog["templates"]))
        self.assertIn("visual/layout priors", catalog["boundary"])

    def test_render_template_writes_svg_png_audit_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "figure"
            result = render_template(
                template_id="framework-example",
                output_dir=output,
                title="Rendered Framework",
                description="AstraDraw scene rendered by the research agent",
                formats=("svg", "png"),
            )
            self.assertEqual(result["status"], "rendered")
            self.assertTrue(Path(result["files"]["svg"]).is_file())
            self.assertTrue(Path(result["files"]["png"]).is_file())
            self.assertTrue(Path(result["files"]["audit"]).is_file())
            audit = json.loads(Path(result["files"]["audit"]).read_text(encoding="utf-8"))
            self.assertTrue(audit["ok"])
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
            self.assertTrue(manifest["schematic"])
            self.assertEqual(manifest["template_id"], "framework-example")
            self.assertIn("visual/layout priors", manifest["boundary"])
            with self.assertRaises(FigureWorkflowError):
                render_template("framework-example", output, formats=("svg",))


if __name__ == "__main__":
    unittest.main()
