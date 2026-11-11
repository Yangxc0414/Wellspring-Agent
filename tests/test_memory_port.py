"""MemoryWritePort: admission strategies must discriminate and default to today.

The port is the M2 被测对象: the same candidate pool must yield pairwise-distinct
admission sets across the four strategies, ordered by strictness — and the
default (store_all) must reproduce pre-port behavior byte for byte.
"""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.memory_port import STRATEGIES, admit, write_report


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(payload, encoding="utf-8")


def _project(tmp: Path) -> Path:
    root = Path(tmp) / "project"
    root.mkdir(parents=True)
    _write(root / "project.json", {"schema_version": "project-0.1", "name": "memory-port-test"})
    return root


def _pool(project: Path):
    import hashlib

    good = project / "inputs" / "protocol.txt"
    _write(good, "preregistered protocol: temperature, humidity, sample size, stopping rule\n")
    receipt = project / "inputs" / "verification.json"
    _write(receipt, {"verified_by": "independent session"})
    return [
        {"text": "good source entry", "sources": ["inputs/protocol.txt"]},
        {"text": "missing source entry", "sources": ["inputs/missing.txt"]},
        {
            "text": "independently verified entry",
            "sources": ["inputs/protocol.txt"],
            "verification": {"source": "inputs/verification.json", "sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()},
        },
        {"text": "bare entry", "sources": []},
    ]


class MemoryPortTest(unittest.TestCase):
    def test_store_all_admits_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            pool = _pool(project)
            report = admit(pool, strategy="store_all", project=project)
            self.assertEqual(report["counts"]["admitted"], len(pool))

    def test_store_none_admits_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            report = admit(_pool(project), strategy="store_none", project=project)
            self.assertEqual(report["counts"]["admitted"], 0)
            self.assertEqual(report["counts"]["rejected"], len(_pool(project)))

    def test_replay_requires_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            report = admit(_pool(project), strategy="replay_then_store", project=project)
            admitted_texts = [item["text"] for item in report["admitted"]]
            self.assertIn("good source entry", admitted_texts)
            self.assertNotIn("missing source entry", admitted_texts)
            self.assertNotIn("bare entry", admitted_texts)

    def test_independent_verification_requires_outside_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            pool = _pool(project)
            pool.append(
                {
                    "text": "self-verified entry",
                    "sources": ["inputs/protocol.txt"],
                    "verification": {"source": "inputs/protocol.txt", "sha256": "irrelevant"},
                }
            )
            report = admit(pool, strategy="independent_verify_then_store", project=project)
            admitted_texts = [item["text"] for item in report["admitted"]]
            self.assertIn("independently verified entry", admitted_texts)
            self.assertNotIn("self-verified entry", admitted_texts)
            self.assertNotIn("missing source entry", admitted_texts)

    def test_tampered_receipt_sha_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _pool(project)
            pool = [
                {
                    "text": "tampered receipt entry",
                    "sources": ["inputs/protocol.txt"],
                    "verification": {"source": "inputs/verification.json", "sha256": "0" * 64},
                }
            ]
            report = admit(pool, strategy="independent_verify_then_store", project=project)
            self.assertEqual(report["counts"]["admitted"], 0)
            self.assertIn("sha256", report["rows"][0]["reason"])

    def test_unknown_strategy_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            with self.assertRaises(ValueError):
                admit([], strategy="store_everything", project=project)

    def test_strategies_registry_matches_spec(self):
        self.assertEqual(
            STRATEGIES,
            ("store_all", "store_none", "replay_then_store", "independent_verify_then_store"),
        )

    def test_report_write_is_atomic_and_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            report = admit(_pool(project), strategy="replay_then_store", project=project)
            out = project / "memory-admission.json"
            write_report(out, report)
            again = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(again["counts"], report["counts"])


if __name__ == "__main__":
    unittest.main()
