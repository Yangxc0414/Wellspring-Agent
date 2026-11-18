import json
import tempfile
import unittest
from pathlib import Path

from research_agent.closure import (
    ESE_CLOSURE_PROFILE,
    ClosureError,
    EseClosureAgent,
)
from research_agent.modules.run import RunAgent, RunError
from research_agent.specs import SpecStore
from research_agent.storage import sha256_file


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


class EseClosureChainTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ese-chain-")
        self.root = Path(self._tmp.name)

        self.metrics_path = self.root / "run" / "metrics.json"
        _write(
            self.metrics_path,
            [
                {
                    "seed": 42,
                    "test_cochange_rate": 0.4,
                    "adjusted_difference": 0.07,
                    "pooled": True,
                }
            ],
        )

        self.capsule_path = self.root / "run" / "run-capsule.json"
        _write(
            self.capsule_path,
            {
                "run_id": "RUN-T",
                "protocol_id": "RUN-T",
                "dataset_id": "msr-corpus:click",
                "seeds": [42],
                "metric_name": "test_cochange_rate",
                "metrics_by_seed": [{"seed": 42, "test_cochange_rate": 0.4}],
                "mean": 0.4,
                "status": "completed",
                "environment": {"python": "3.8.7"},
            },
        )

        self.ea_path = self.root / "run" / "ea.json"
        _write(
            self.ea_path,
            {
                "artifact_id": "EA-T",
                "kind": "metric",
                "run_id": "RUN-T",
                "path": str(self.metrics_path),
                "sha256": sha256_file(self.metrics_path),
                "source": "ese-exec",
                "captured_at": "2026-11-18T00:00:00+00:00",
                "immutable": True,
                "scope": "S5/RUN-T",
            },
        )

        self.agent = RunAgent(SpecStore().load("run"))
        self.claim_dir = self.root / "claim"
        self.report_dir = self.root / "closure"
        self.sign_dir = self.root / "signature"

    def tearDown(self):
        self._tmp.cleanup()

    def _claim(self, **kwargs):
        return self.agent.claim(
            self.capsule_path,
            self.ea_path,
            "在测试语料上，缺陷修复提交触碰测试的比例为 0.40。",
            "核对了 pooled 行与 capsule 重算结果。",
            "S5/RUN-T",
            self.claim_dir,
            assertions=[
                {
                    "metric": "test_cochange_rate",
                    "value": 0.4,
                    "comparator": "approx",
                    "tolerance": 0.001,
                }
            ],
            **kwargs
        )

    def test_default_source_rejects_ese_exec(self):
        with self.assertRaises(RunError):
            self._claim()

    def test_explicit_source_allows_claim(self):
        result = self._claim(evidence_sources=["ese-exec"])
        self.assertEqual("supported", result["claim"]["status"])
        self.assertEqual("ese-exec", result["claim"]["verification"]["evidence_source"])

    def test_ese_closure_is_ready_and_signs(self):
        self._claim(evidence_sources=["ese-exec"])
        claim_path = self.claim_dir / "claim.json"
        checked = EseClosureAgent().check(
            self.capsule_path, self.ea_path, claim_path, self.report_dir
        )
        self.assertEqual("ready", checked["report"]["status"])
        self.assertEqual(ESE_CLOSURE_PROFILE, checked["report"]["closure_profile"])

        signed = EseClosureAgent().sign(
            Path(checked["path"]),
            self.capsule_path,
            self.ea_path,
            claim_path,
            "确认断言仅覆盖该测试语料。",
            self.sign_dir,
        )
        self.assertEqual(
            checked["report"]["report_id"], signed["signature"]["report_id"]
        )
        self.assertFalse(signed["signature"]["submission"])
        self.assertTrue(Path(signed["manifest"]).is_file())
        self.assertTrue(Path(signed["path"]).is_file())

    def test_tampered_metrics_blocks(self):
        self._claim(evidence_sources=["ese-exec"])
        _write(
            self.metrics_path,
            [{"seed": 42, "test_cochange_rate": 0.9, "pooled": True}],
        )
        checked = EseClosureAgent().check(
            self.capsule_path,
            self.ea_path,
            self.claim_dir / "claim.json",
            self.report_dir,
        )
        self.assertEqual("blocked", checked["report"]["status"])
        self.assertIn(
            "ea_sha256_matches_metrics", checked["report"]["unresolved"]
        )

    def test_tampered_assertion_blocks(self):
        self._claim(evidence_sources=["ese-exec"])
        claim_path = self.claim_dir / "claim.json"
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        claim["assertions"][0]["value"] = 0.9
        _write(claim_path, claim)

        checked = EseClosureAgent().check(
            self.capsule_path, self.ea_path, claim_path, self.report_dir
        )
        self.assertEqual("blocked", checked["report"]["status"])
        self.assertIn(
            "claim_assertions_recomputed", checked["report"]["unresolved"]
        )

    def test_sign_rejects_stale_report(self):
        self._claim(evidence_sources=["ese-exec"])
        claim_path = self.claim_dir / "claim.json"
        checked = EseClosureAgent().check(
            self.capsule_path, self.ea_path, claim_path, self.report_dir
        )
        _write(
            self.metrics_path,
            [{"seed": 42, "test_cochange_rate": 0.9, "pooled": True}],
        )
        with self.assertRaises(ClosureError):
            EseClosureAgent().sign(
                Path(checked["path"]),
                self.capsule_path,
                self.ea_path,
                claim_path,
                "试图在输入变化后签署。",
                self.sign_dir,
            )

    def test_ese_sign_rejects_canonical_report(self):
        report_path = self.root / "canonical-report.json"
        _write(
            report_path,
            {
                "report_id": "CLR-X",
                "status": "ready",
                "closure_profile": "canonical_run",
                "checks": [],
            },
        )
        with self.assertRaises(ClosureError):
            EseClosureAgent().sign(
                report_path,
                self.capsule_path,
                self.ea_path,
                self.root / "missing-claim.json",
                "profile 不匹配。",
                self.sign_dir,
            )


if __name__ == "__main__":
    unittest.main()
