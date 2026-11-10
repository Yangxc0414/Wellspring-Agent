import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.writing_support import RUN_ID, make_writing_project, write_draft

ROOT = Path(__file__).resolve().parents[1]

PROVIDER_KEY_ENVS = (
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ZHIPU_API_KEY",
    "OPENAI_COMPATIBLE_API_KEY",
    "RESEARCH_AGENT_MODEL_STORE",
    "RESEARCH_AGENT_HOST_MODEL_LEDGER",
)


def hermetic_model_env(base: dict) -> dict:
    """CLI tests must not inherit a developer's live model config.

    A bound profile (including a keyless host_agent profile) changes what the pipeline does,
    and a real provider key would make these tests reach the network. Pointing the store at a
    nonexistent path is what actually isolates it: the repository default store is live state.
    """
    env = dict(base)
    env["PYTHONIOENCODING"] = "utf-8"
    for name in PROVIDER_KEY_ENVS:
        env.pop(name, None)
    scratch = Path(tempfile.mkdtemp(prefix="ra-cli-"))
    env["RESEARCH_AGENT_MODEL_STORE"] = str(scratch / "absent-gateway.json")
    env["RESEARCH_AGENT_HOST_MODEL_LEDGER"] = str(scratch / "absent-turns.json")
    return env


class CliTest(unittest.TestCase):
    def setUp(self):
        self.env = hermetic_model_env(os.environ)

    def test_spec_list_and_literature_run(self):
        listed = subprocess.run(
            [sys.executable, "-m", "research_agent", "spec", "list"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
        )
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("literature", listed.stdout)

        run = subprocess.run(
            [
                sys.executable, "-m", "research_agent", "literature", "run",
                "--question", "钙钛矿 钝化", "--max-sources", "3",
            ],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["module"], "literature")
        self.assertTrue(payload["fixture_mode"])

    def test_rsi_propose_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = str(Path(tmp) / "rsi-ledger.json")
            policy_path = str(Path(tmp) / "policy.json")
            propose = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "rsi", "propose",
                    "--policy-path", policy_path,
                    "--ledger", ledger, "--kind", "skill",
                    "--target", "literature.query_planner",
                    "--patch", "add review subquery",
                    "--rationale", "thin coverage",
                    "--predicted", "one more full text",
                    "--dry-run-ref", "DRY-CLI",
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(propose.returncode, 0, propose.stderr)
            status = subprocess.run(
                [sys.executable, "-m", "research_agent", "rsi", "status", "--ledger", ledger],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            payload = json.loads(status.stdout)
            self.assertEqual(payload["pending"], 1)
            self.assertEqual(payload["capability_claims"], [])

    def test_agent_registry_and_policy_pause_block_new_proposals(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents_path = str(Path(tmp) / "custom_agents.json")
            policy_path = str(Path(tmp) / "policy.json")
            ledger = str(Path(tmp) / "rsi-ledger.json")
            added = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "agent", "add",
                    "--custom-agents-path", agents_path,
                    "--name", "覆盖审稿人", "--role", "reviewer",
                    "--purpose", "检查全文覆盖与引用", "--check", "coverage",
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(added.returncode, 0, added.stderr)
            listed = subprocess.run(
                [sys.executable, "-m", "research_agent", "agent", "list", "--custom-agents-path", agents_path],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(json.loads(listed.stdout)["count"], 1)

            paused = subprocess.run(
                [sys.executable, "-m", "research_agent", "rsi", "policy", "set", "--policy-path", policy_path, "--disabled"],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(paused.returncode, 0, paused.stderr)
            blocked = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "rsi", "propose",
                    "--policy-path", policy_path, "--ledger", ledger,
                    "--kind", "skill", "--target", "literature.query_planner",
                    "--patch", "add review subquery", "--rationale", "thin coverage",
                    "--predicted", "one more full text", "--dry-run-ref", "DRY-CLI",
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("self-evolution policy is off", blocked.stderr)

            immutable = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "rsi", "policy", "set",
                    "--policy-path", policy_path, "--scope", "claim.statement=on",
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertNotEqual(immutable.returncode, 0)
            self.assertIn("immutable", immutable.stderr)

    def test_rsi_propose_model_requires_exactly_one_model_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "rsi", "propose-model",
                    "--policy-path", str(Path(tmp) / "policy.json"),
                    "--observation", "public baseline",
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("exactly one", run.stderr)

    def test_skill_scan_registers_local_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skills" / "citation-check"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: citation-check\ndescription: Check refs.\n---\nUse read-only checks.",
                encoding="utf-8",
            )
            registry = str(Path(tmp) / "skills.json")
            scanned = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "skill", "scan",
                    "--path", str(Path(tmp) / "skills"), "--registry-path", registry,
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(scanned.returncode, 0, scanned.stderr)
            payload = json.loads(scanned.stdout)
            self.assertEqual(payload["snapshot"]["count"], 1)
            self.assertEqual(payload["accepted"][0]["name"], "citation-check")
            listed = subprocess.run(
                [sys.executable, "-m", "research_agent", "skill", "list", "--registry-path", registry],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(json.loads(listed.stdout)["count"], 1)

    def test_signer_create_and_list_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            signers = str(Path(tmp) / "signers.json")
            created = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "signer", "create",
                    "--name", "PI", "--signers-path", signers,
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            payload = json.loads(created.stdout)
            self.assertTrue(payload["signer"]["signer_id"].startswith("SIGNER-"))
            self.assertNotIn("secret_hex", created.stdout)
            listed = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "signer", "list",
                    "--signers-path", signers,
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(json.loads(listed.stdout)["count"], 1)

    def test_skill_version_activation_and_rollback_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            eval_root = Path(tmp) / "evals"
            versions = Path(tmp) / "versions.json"
            evaluated = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "skill", "eval",
                    "--skill-id", "protocol-review", "--version", "1.0.0",
                    "--eval-root", str(eval_root), "--versions-path", str(versions),
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
            report = json.loads(evaluated.stdout)
            self.assertEqual(report["skill_version"], "1.0.0")
            report_path = next(eval_root.glob("protocol-review-1.0.0-all-*.json"))
            activated = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "skill", "version", "activate",
                    "--skill-id", "protocol-review", "--version", "1.0.0",
                    "--eval-report", str(report_path), "--human-reason", "validated old behavior",
                    "--versions-path", str(versions),
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(activated.returncode, 0, activated.stderr)
            self.assertEqual(
                json.loads(activated.stdout)["activation"]["active"]["protocol-review"],
                "1.0.0",
            )
            rolled = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "skill", "version", "rollback",
                    "--skill-id", "protocol-review", "--human-reason", "restore",
                    "--versions-path", str(versions),
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(rolled.returncode, 0, rolled.stderr)
            self.assertEqual(
                json.loads(rolled.stdout)["rollback"]["active"]["protocol-review"],
                "1.1.0",
            )

    def test_pipeline_writes_svg_and_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "pipeline", "run",
                    "--topic", "钙钛矿 钝化", "--venue", "zh_core_journal",
                    "--grant", "nsfc", "--primary-metric", "稳定性",
                    "--control", "未钝化对照", "--output-dir", tmp,
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            for name in ("demo.json", "figure.svg", "figure.scene.json", "figure.manifest.json", "paper.json", "grant.json", "specs.json"):
                self.assertTrue((Path(tmp) / name).is_file(), name)
            svg = (Path(tmp) / "figure.svg").read_text(encoding="utf-8")
            self.assertIn('id="fig-title"', svg)


    def test_writing_pack_and_audit_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_writing_project(Path(tmp), signed=True)
            pack = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "writing", "pack",
                    "--project", str(project), "--run-id", RUN_ID, "--max-sources", "2",
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(pack.returncode, 0, pack.stderr)
            payload = json.loads(pack.stdout)
            self.assertEqual(payload["claim"]["status"], "signed")
            self.assertTrue((project / "runs" / RUN_ID / "writing-pack.json").is_file())

            draft = write_draft(Path(tmp) / "draft.md", result_text="R² 均值为 0.1438。")
            audit = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "writing", "audit",
                    "--project", str(project), "--run-id", RUN_ID, "--draft", str(draft),
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(audit.returncode, 0, audit.stderr)
            self.assertEqual(json.loads(audit.stdout)["status"], "ready_for_human_review")
            self.assertTrue((project / "runs" / RUN_ID / "writing-audit.json").is_file())

    def test_writing_audit_cli_returns_one_on_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_writing_project(Path(tmp))
            draft = write_draft(Path(tmp) / "draft.md", result_text="R² 均值为 0.1438。")
            audit = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "writing", "audit",
                    "--project", str(project), "--run-id", RUN_ID, "--draft", str(draft),
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=self.env,
            )
            self.assertEqual(audit.returncode, 1, audit.stderr)
            self.assertEqual(json.loads(audit.stdout)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
