"""A measured result needs a way out of the notebook: the table -> figure path must be
reachable on its own, not only as a side effect of rewriting a manuscript."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.cli import main

SPEC = {"figures": [{"id": "fig-demo", "type": "line", "x": "evaluations",
                    "y": "score", "series": "cell_id"}]}


class FigureTableCLItest(unittest.TestCase):
    def _write_inputs(self, root: Path):
        data = root / "curve.csv"
        data.write_text(
            "cell_id,evaluations,score\n"
            "a,1,0.10\na,2,0.30\na,3,0.50\n"
            "b,1,0.10\nb,2,0.20\nb,3,0.25\n",
            encoding="utf-8",
        )
        spec = root / "spec.json"
        with open(spec, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(SPEC, handle)
        return data, spec

    def test_table_renders_png_and_svg_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, spec = self._write_inputs(root)
            out = root / "out"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main([
                    "figure", "table", "--data", str(data), "--spec", str(spec),
                    "--output-dir", str(out),
                ])
            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            entries = payload.get("figures") or []
            self.assertEqual(len(entries), 1, payload)
            entry = entries[0]
            self.assertFalse(entry["schematic"], "a data-backed chart is not a schematic")
            for key in ("data_sha256", "spec_sha256", "output_sha256"):
                self.assertTrue(entry.get(key), key)
            for key in ("png", "svg"):
                path = Path(entry[key])
                self.assertTrue(path.is_file(), key)
                self.assertGreater(path.stat().st_size, 100, key)
            self.assertEqual(payload["seed_coverage"], [], "a table without a seeds column has nothing to disclose")
            self.assertIn("not evidence", payload["boundary"])
            sidecars = payload["caption_sidecars"]
            self.assertEqual(len(sidecars), 1, payload)
            text = Path(sidecars[0]).read_text(encoding="utf-8")
            self.assertIn("fig-demo", text)
            for key in ("data_sha256", "spec_sha256", "output_sha256"):
                self.assertIn(key, text)
            self.assertEqual(
                Path(sidecars[0]).parent, Path(entries[0]["svg"]).parent)

    def test_the_seed_disclosure_travels_with_the_image_not_only_in_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "curve.csv"
            data.write_text(
                "cell_id,evaluations,seeds,score\n"
                "a,1,32,0.10\na,2,32,0.30\n"
                "b,1,32,0.10\nb,2,28,0.20\n",
                encoding="utf-8",
            )
            spec = root / "spec.json"
            with open(spec, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({"figures": [{"id": "fig-seeds", "type": "line",
                                        "x": "evaluations", "y": "score",
                                        "series": "cell_id",
                                        "caption": "two arms, uneven seeds"}]}, handle)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                main([
                    "figure", "table", "--data", str(data), "--spec", str(spec),
                    "--output-dir", str(root / "out"),
                ])
            payload = json.loads(buffer.getvalue())
            text = Path(payload["caption_sidecars"][0]).read_text(encoding="utf-8")
            self.assertIn("two arms, uneven seeds", text)
            self.assertIn("seed coverage", text)
            self.assertIn("b: 28 of 32", text)
            self.assertNotIn("a: 28", text)

    def test_an_unknown_spec_field_fails_instead_of_changing_the_chart(self):
        # `"kind": "line"` used to be dropped silently and the loader's default made a bar
        # chart out of a response curve nobody had asked for
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, _ = self._write_inputs(root)
            spec = root / "bad-spec.json"
            with open(spec, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({"figures": [{"id": "fig-typo", "kind": "line",
                                        "x": "evaluations", "y": "score"}]}, handle)
            buffer = io.StringIO()
            with self.assertRaises(SystemExit) as caught:
                with contextlib.redirect_stdout(buffer):
                    main([
                        "figure", "table", "--data", str(data), "--spec", str(spec),
                        "--output-dir", str(root / "out"),
                    ])
            message = str(caught.exception)
            self.assertIn("fig-typo", message)
            self.assertIn("kind", message)
            self.assertIn("known fields", message)

    def test_a_series_with_a_varying_seed_count_is_disclosed_not_quietly_plotted(self):
        # normalisation drops the runs that start at the ceiling, so a seed count that
        # changes inside one series is a selection effect the chart cannot show
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "curve.csv"
            data.write_text(
                "cell_id,evaluations,seeds,score\n"
                "a,1,32,0.10\na,2,32,0.30\n"
                "b,1,32,0.10\nb,2,28,0.20\n",
                encoding="utf-8",
            )
            spec = root / "spec.json"
            with open(spec, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({"figures": [{"id": "fig-seeds", "type": "line",
                                        "x": "evaluations", "y": "score",
                                        "series": "cell_id"}]}, handle)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main([
                    "figure", "table", "--data", str(data), "--spec", str(spec),
                    "--output-dir", str(root / "out"),
                ])
            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            cov = {item["series"]: item for item in payload["seed_coverage"]}
            self.assertEqual((cov["b"]["min_seeds"], cov["b"]["max_seeds"]), (28, 32))
            self.assertEqual(cov["b"]["figure_id"], "fig-seeds")
            self.assertNotIn("a", cov, "a constant seed count is not a selection effect")
            self.assertTrue(
                any("N of M seeds" in w for w in payload["warnings"]), payload["warnings"]
            )

    def test_an_empty_spec_fails_instead_of_rendering_nothing_quietly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, _ = self._write_inputs(root)
            empty = root / "empty.json"
            with open(empty, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({"figures": []}, handle)
            with self.assertRaises(SystemExit):
                main([
                    "figure", "table", "--data", str(data), "--spec", str(empty),
                    "--output-dir", str(root / "out"),
                ])


if __name__ == "__main__":
    unittest.main()
