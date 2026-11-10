import json
import tempfile
import unittest
from pathlib import Path

from research_agent.external_skills import ExternalSkillError, invoke_external_skill
from research_agent.skill_registry import SkillRegistryStore, manifest_from_payload


class FakeModel:
    def __init__(self, payload=None, raw=None):
        self.payload = payload or {
            "advisory": "Use a paired comparison and report the preregistered metric.",
            "assumptions": ["the protocol is frozen"],
            "limitations": ["lexical advice only"],
            "suggested_checks": ["check claim evidence refs"],
        }
        self.raw = raw
        self.messages = []

    def complete(self, messages, json_mode=True):
        self.messages = messages
        return self.raw if self.raw is not None else json.dumps(self.payload)


def registry_with_skill(root: Path, enabled=True, has_scripts=False, license_value=""):
    store = SkillRegistryStore(root / "skills.json")
    manifest = manifest_from_payload(
        {
            "name": "writing-checklist",
            "description": "Use when checking a research manuscript.",
            "instructions": "Check that every result sentence has an evidence ref.",
            "version": "0.1.0",
            "license": license_value,
            "tools": ["evidence.inspect"],
            "source": "imported",
            "enabled": enabled,
            "has_scripts": has_scripts,
        }
    )
    store.register_many([manifest])
    return root / "skills.json", manifest


class ExternalSkillTest(unittest.TestCase):
    def test_enabled_instruction_skill_returns_advisory_and_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry, manifest = registry_with_skill(root)
            model = FakeModel()
            result = invoke_external_skill(
                skill_id=manifest.id,
                input_text="Review this manuscript.",
                profile_id="test-profile",
                registry_path=str(registry),
                usage_path=str(root / "usage.json"),
                model=model,
            )
            self.assertEqual(result["schema_version"], "external-skill-invocation-0.2")
            self.assertIn("paired comparison", result["advisory"])
            self.assertEqual(result["usage"]["status"], "pass")
            self.assertFalse(result["evidence_eligible"])
            self.assertTrue(result["untrusted"])
            self.assertIn("Never execute", model.messages[0]["content"])
            self.assertIn("evidence ref", model.messages[1]["content"])
            self.assertTrue((root / "usage.json").is_file())
            with self.assertRaises(ExternalSkillError):
                invoke_external_skill(
                    manifest.id, "x", "p", registry_path=str(registry),
                    usage_path=str(root / "usage.json"), model=FakeModel(),
                    script_args=["--unexpected"],
                )

    def test_disabled_or_script_skill_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry, manifest = registry_with_skill(root, enabled=False)
            with self.assertRaises(ExternalSkillError):
                invoke_external_skill(
                    manifest.id, "x", "p", registry_path=str(registry),
                    usage_path=str(root / "u.json"), model=FakeModel(),
                )
            registry, manifest = registry_with_skill(root, enabled=True, has_scripts=True)
            with self.assertRaises(ExternalSkillError):
                invoke_external_skill(
                    manifest.id, "x", "p", registry_path=str(registry),
                    usage_path=str(root / "u.json"), model=FakeModel(),
                )

    def test_trusted_script_runs_with_local_process_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "script-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: script-skill\ndescription: Use when running a script.\n---\n# Script\n",
                encoding="utf-8",
            )
            scripts = skill_dir / "scripts"
            scripts.mkdir()
            (scripts / "run.py").write_text(
                "import json, sys\n"
                "from pathlib import Path\n"
                "payload = json.load(sys.stdin)\n"
                "Path('proof.txt').write_text('ran', encoding='utf-8')\n"
                "print(json.dumps({'echo': payload['input'], 'args': sys.argv[1:]}))\n",
                encoding="utf-8",
            )
            registry = root / "skills.json"
            store = SkillRegistryStore(registry)
            imported = store.import_directory(skill_dir)
            skill_id = imported["snapshot"]["skills"][0]["id"]
            store.set_enabled(skill_id, True)
            result = invoke_external_skill(
                skill_id=skill_id,
                input_text="hello",
                trusted_scripts=True,
                workdir=str(root),
                usage_path=str(root / "usage.json"),
                registry_path=str(registry),
                script_args=["--check", "evidence"],
            )
            self.assertEqual(result["execution_mode"], "trusted_script")
            self.assertEqual(result["output"]["echo"], "hello")
            self.assertEqual(result["output"]["args"], ["--check", "evidence"])
            self.assertEqual(result["returncode"], 0)
            self.assertTrue((root / "proof.txt").is_file())
            self.assertEqual(result["usage"]["status"], "pass")
            self.assertFalse(result["evidence_eligible"])
            distilled = invoke_external_skill(
                skill_id=skill_id,
                input_text="hello again",
                trusted_scripts=True,
                workdir=str(root),
                usage_path=str(root / "usage.json"),
                registry_path=str(registry),
                distill_on_success=True,
                distill_license="MIT",
                distill_reason="reuse the script locally",
                library_dir=str(root / "library"),
            )
            self.assertEqual(distilled["distillation"]["status"], "candidate")
            candidate = distilled["distillation"]["result"]["candidate"]
            self.assertTrue(candidate["has_scripts"])
            self.assertIn(
                "scripts/run.py", {item["path"] for item in candidate["files"]}
            )
            self.assertFalse(candidate["enabled"])
            with self.assertRaises(ExternalSkillError):
                invoke_external_skill(
                    skill_id=skill_id,
                    input_text="hello",
                    workdir=str(root),
                    usage_path=str(root / "usage.json"),
                    registry_path=str(registry),
                )

    def test_successful_invocation_can_distill_a_disabled_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry, manifest = registry_with_skill(root, license_value="MIT")
            result = invoke_external_skill(
                skill_id=manifest.id,
                input_text="Review this manuscript.",
                profile_id="test-profile",
                registry_path=str(registry),
                usage_path=str(root / "usage.json"),
                model=FakeModel(),
                distill_on_success=True,
                distill_reason="reuse the checklist locally",
                distill_source_url="https://example.invalid/checklist",
                library_dir=str(root / "library"),
            )
            self.assertIn("paired comparison", result["advisory"])
            self.assertEqual(result["usage"]["status"], "pass")
            distilled = result["distillation"]
            self.assertEqual(distilled["status"], "candidate")
            candidate = distilled["result"]["candidate"]
            self.assertFalse(candidate["enabled"])
            self.assertEqual(candidate["license"], "MIT")
            self.assertTrue((Path(distilled["result"]["path"]) / "distill.json").is_file())
            records = SkillRegistryStore(registry).list()
            local = next(item for item in records if item.get("id") == candidate["registered_skill_id"])
            self.assertFalse(local["enabled"])

            no_reason = invoke_external_skill(
                skill_id=manifest.id,
                input_text="Review again.",
                profile_id="test-profile",
                registry_path=str(registry),
                usage_path=str(root / "usage.json"),
                model=FakeModel(),
                distill_on_success=True,
                library_dir=str(root / "unused-library"),
            )
            self.assertIn("paired comparison", no_reason["advisory"])
            self.assertEqual(no_reason["distillation"]["status"], "error")
            self.assertIn("human_reason", no_reason["distillation"]["error"])

    def test_invalid_model_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry, manifest = registry_with_skill(root)
            with self.assertRaises(ExternalSkillError):
                invoke_external_skill(
                    manifest.id, "x", "p", registry_path=str(registry),
                    usage_path=str(root / "u.json"), model=FakeModel(raw="not json"),
                )
            with self.assertRaises(ExternalSkillError):
                invoke_external_skill(
                    manifest.id, "x", "p", registry_path=str(registry),
                    usage_path=str(root / "u.json"), model=FakeModel(raw='{"advisory": ""}'),
                )
            usage = json.loads((root / "u.json").read_text(encoding="utf-8"))
            self.assertEqual(usage["count"], 2)
            self.assertTrue(all(item["status"] == "fail" for item in usage["entries"]))


if __name__ == "__main__":
    unittest.main()
