"""The writing pack must hand the reviewer a real re-run command, or say why it cannot."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.writing_pack import _reproduction_map


def _write_capsule(root: Path, capsule: dict) -> Path:
    run_dir = root / "runs" / "RUN-1"
    (run_dir / "run").mkdir(parents=True)
    (run_dir / "run" / "run-capsule.json").write_text(
        json.dumps(capsule), encoding="utf-8"
    )
    return run_dir


class ReproductionMapTest(unittest.TestCase):
    def test_qualified_dataset_still_yields_the_runnable_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _write_capsule(
                Path(tmp),
                {
                    "dataset_id": "sklearn:iris:150x4",
                    "seeds": [1, 2, 3],
                    "protocol_id": "PROTO-1",
                    "test_size": 0.2,
                    "artifacts": {"capsule": "runs/RUN-1/run/run-capsule.json"},
                    "dataset_sha256": "d" * 64,
                },
            )
            repro = _reproduction_map(run_dir)
            self.assertEqual(repro["inputs"]["runnable_dataset"], "iris")
            self.assertIn("--dataset iris", repro["command"])
            self.assertIn("--seeds 3", repro["command"])
            self.assertIn("--protocol-id PROTO-1", repro["command"])
            self.assertIn("--test-size 0.2", repro["command"])
            self.assertEqual(repro["claim_status"], "missing")
            self.assertTrue(repro["artifacts"][0]["path"].startswith("runs/"))
            self.assertTrue(
                any("lineage verify" in c for c in repro["caveats"]),
                "name/path artifacts must not read as a hash guarantee",
            )
            self.assertIn("nothing here re-ran", repro["boundary"])

    def test_status_is_never_collapsed_below_the_packs_own_claim_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _write_capsule(
                Path(tmp), {"dataset_id": "sklearn:iris:150x4", "seeds": [1]}
            )
            self.assertEqual(
                _reproduction_map(run_dir, "draft_needs_human")["claim_status"],
                "draft_needs_human",
            )
            self.assertEqual(
                _reproduction_map(run_dir, "signed")["claim_status"], "signed"
            )

    def test_dataset_outside_the_run_surface_gets_no_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _write_capsule(
                Path(tmp), {"dataset_id": "sklearn:wine:178x13", "seeds": [1, 2]}
            )
            repro = _reproduction_map(run_dir)
            self.assertEqual(repro["command"], "")
            self.assertTrue(any("not on the run execute surface" in c for c in repro["caveats"]))

    def test_missing_seeds_are_not_turned_into_a_default_seed_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _write_capsule(Path(tmp), {"dataset_id": "sklearn:iris:150x4"})
            repro = _reproduction_map(run_dir)
            self.assertEqual(repro["command"], "")
            self.assertTrue(any("no seeds" in c for c in repro["caveats"]))


if __name__ == "__main__":
    unittest.main()
