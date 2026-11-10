import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("doctor", ROOT / "scripts/doctor.py")
doctor = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(doctor)


def _root(parent: Path) -> Path:
    root = parent / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "research_mcp_server.py").write_text("", encoding="utf-8")
    (root / "apps" / "web").mkdir(parents=True)
    (root / "apps" / "web" / "package.json").write_text("{}", encoding="utf-8")
    return root


class DoctorTest(unittest.TestCase):
    def test_reports_presence_without_leaking_key_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _root(Path(tmp))
            with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-secret-value-1234567890"}):
                report = doctor.check_environment(root)
            keys = next(item for item in report["checks"] if item["id"] == "model_supply")
        self.assertTrue(keys["detail"]["provider_keys"]["DEEPSEEK_API_KEY"])
        self.assertEqual(keys["next"], "")
        modules = next(item for item in report["checks"] if item["id"] == "optional_modules")
        self.assertEqual(modules["next"], "")
        serialized = json.dumps(report)
        self.assertNotIn("sk-secret-value", serialized)
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["warnings"])

    def test_host_agent_binding_satisfies_model_supply_without_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _root(Path(tmp))
            store_path = Path(tmp) / "gateway.json"
            from research_agent.models import GatewayStore, ModelProfile, ProviderConfig

            store = GatewayStore(store_path)
            store.upsert_provider(
                ProviderConfig(provider_id="host-agent", kind="host_agent", label="Host")
            )
            store.upsert_profile(
                ModelProfile(profile_id="host-agent", provider_id="host-agent", model="host")
            )
            store.set_binding("idea", "host-agent")
            clean = {
                name: ""
                for name in doctor.KEY_ENV_NAMES
            }
            with mock.patch.dict(
                os.environ,
                dict(clean, RESEARCH_AGENT_MODEL_STORE=str(store_path)),
                clear=False,
            ):
                report = doctor.check_environment(root)
            supply = next(item for item in report["checks"] if item["id"] == "model_supply")
        self.assertEqual(supply["status"], "ok")
        self.assertEqual(supply["detail"]["host_agent_bound_modules"], ["idea"])
        self.assertTrue(supply["detail"]["provider_keys"]["DEEPSEEK_API_KEY"] is False)

    def test_missing_launcher_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            report = doctor.check_environment(root)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(
            any(item["id"] == "mcp_launcher" for item in report["blockers"])
        )

    def test_external_skill_root_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _root(Path(tmp))
            skill = Path(tmp) / "external"
            scripts = skill / "skills" / "scientific-writing" / "scripts"
            scripts.mkdir(parents=True)
            for name in doctor.EXTERNAL_SCRIPTS:
                (scripts / name).write_text("", encoding="utf-8")
            report = doctor.check_environment(root, skill_root=skill)
        entry = next(item for item in report["checks"] if item["id"] == "external_skills")
        self.assertEqual(entry["status"], "ok")
        self.assertTrue(all(entry["detail"]["scripts"].values()))

    def test_cli_json_is_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _root(Path(tmp))
            buffer = io.StringIO()
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-cli-secret-1234567890"}):
                with redirect_stdout(buffer):
                    code = doctor.main(["--root", str(root), "--json"])
        self.assertEqual(code, 0)
        self.assertNotIn("sk-cli-secret", buffer.getvalue())
        self.assertEqual(json.loads(buffer.getvalue())["schema_version"], "research-agent-doctor-0.1")


if __name__ == "__main__":
    unittest.main()
