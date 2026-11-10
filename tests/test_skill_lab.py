import tempfile
import unittest
from pathlib import Path

from research_agent.actions import run_skill
from research_agent.evolution_policy import EvolutionPolicyStore
from research_agent.rsi import StepLedger
from research_agent.skill_lab import SkillLab, SkillLabError
from research_agent.skill_registry import SkillRegistryStore, manifest_from_payload


class SkillLabTest(unittest.TestCase):
    def _lab(self, root: Path) -> SkillLab:
        policy = EvolutionPolicyStore(root / "policy.json")
        policy.update(enabled=True)
        return SkillLab(
            registry_path=root / "skills.json",
            usage_path=root / "usage.json",
            eval_root=root / "evals",
            ledger_path=root / "ledger.json",
            policy_path=root / "policy.json",
            versions_path=root / "versions.json",
        )

    def test_usage_is_recorded_and_summarized(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = self._lab(Path(tmp))
            usage = lab.record_usage(
                "literature-brief",
                "warn",
                task_id="TASK-1",
                checks=[{"id": "coverage", "status": "warn"}],
                note="thin full text",
            )
            self.assertEqual(usage["skill_id"], "literature-brief")
            summary = lab.usage.summary()
            self.assertEqual(summary["count"], 1)
            self.assertEqual(summary["skills"]["literature-brief"]["warn"], 1)
            self.assertIn("not a capability claim", summary["boundary"])

    def test_builtin_skill_has_public_and_hidden_eval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lab = self._lab(root)
            report = lab.evaluate("literature-brief", "all")
            self.assertEqual(report.status, "pass")
            self.assertGreaterEqual(report.passed, 2)
            self.assertEqual(report.failed, 0)
            self.assertTrue(list((root / "evals").glob("*.json")))
            self.assertIn("deterministic", report.boundary)

    def test_imported_skill_is_not_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lab = self._lab(root)
            registry = SkillRegistryStore(root / "skills.json")
            manifest = manifest_from_payload({
                "name": "imported-check",
                "description": "a read-only imported skill",
                "instructions": "check something",
                "tools": ["session.inspect"],
            })
            registry.register(manifest)
            report = lab.evaluate(manifest.id, "all")
            self.assertEqual(report.status, "not_executable")
            self.assertEqual(report.cases, [])

    def test_protocol_skill_checks_primary_metric_and_freeze_metadata(self):
        frozen = run_skill("protocol-review", {
            "protocol": {
                "status": "frozen",
                "hypothesis": "h",
                "baseline": "majority",
                "primary_metric": "accuracy",
                "controls": ["majority"],
                "seeds": 3,
                "design_sha256": "a" * 64,
                "human_reason": "reviewed",
                "limitation": "one local dataset",
            }
        })
        self.assertEqual(frozen["status"], "pass")
        self.assertTrue(frozen["frozen"])
        self.assertEqual(frozen["missing"], [])

        incomplete = run_skill("protocol-review", {
            "protocol": {
                "status": "frozen",
                "hypothesis": "h",
                "baseline": "majority",
                "primary_metric": "accuracy",
                "controls": ["majority"],
                "seeds": 3,
                "design_sha256": "a" * 64,
            }
        })
        self.assertEqual(incomplete["status"], "needs_input")
        self.assertIn("human_reason", incomplete["missing"])
        self.assertIn("limitation", incomplete["missing"])

    def test_version_activation_requires_eval_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lab = self._lab(root)
            self.assertEqual(lab._skill("protocol-review")["version"], "1.1.0")
            report = lab.evaluate("protocol-review", "all", version="1.0.0")
            self.assertEqual(report.status, "pass")
            self.assertEqual(report.skill_version, "1.0.0")
            report_path = next((root / "evals").glob("protocol-review-1.0.0-all-*.json"))
            activated = lab.activate(
                "protocol-review", "1.0.0", report_path, "validated old behavior"
            )
            self.assertEqual(activated["activation"]["active"]["protocol-review"], "1.0.0")
            self.assertEqual(lab._skill("protocol-review")["version"], "1.0.0")
            usage = lab.record_usage("protocol-review", "pass")
            self.assertEqual(usage["version"], "1.0.0")
            rolled = lab.rollback("protocol-review", "restore current behavior")
            self.assertEqual(rolled["rollback"]["active"]["protocol-review"], "1.1.0")
            self.assertEqual(lab._skill("protocol-review")["version"], "1.1.0")

    def test_version_activation_rejects_unvalidated_or_unknown_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lab = self._lab(root)
            report = lab.evaluate("protocol-review", "public", version="1.0.0")
            report_path = next((root / "evals").glob("protocol-review-1.0.0-public-*.json"))
            with self.assertRaises(SkillLabError):
                lab.activate("protocol-review", "1.0.0", report_path, "no hidden cases")
            with self.assertRaises(SkillLabError):
                lab.activate("protocol-review", "9.9.9", report_path, "unknown")
            custom, _ = lab.registry.register(manifest_from_payload({
                "name": "custom-version",
                "description": "custom skill",
                "instructions": "do something safe",
                "tools": [],
            }))
            with self.assertRaises(SkillLabError):
                lab.activate(custom["id"], "1.0.0", report_path, "not executable")
            self.assertEqual(report.skill_version, "1.0.0")

    def test_skill_proposal_is_pending_and_requires_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lab = self._lab(root)
            with self.assertRaises(SkillLabError):
                lab.propose(
                    "literature-brief",
                    "add a review subquery",
                    "thin coverage",
                    "one more full text",
                )
            lab.record_usage("literature-brief", "warn", task_id="TASK-2")
            proposal = lab.propose(
                "literature-brief",
                "add a review subquery before broad retrieval",
                "thin coverage",
                "one more full text",
                dry_run_ref="DRY-SKILL-1",
            )
            self.assertEqual(proposal["candidate"]["decision"], "pending_human")
            ledger = StepLedger.load(root / "ledger.json")
            self.assertEqual(len(ledger.episodes), 1)
            self.assertEqual(ledger.episodes[0].candidate.kind, "skill")
            self.assertEqual(ledger.episodes[0].decision, "pending_human")
            self.assertIn("pending_human only", proposal["boundary"])


if __name__ == "__main__":
    unittest.main()
