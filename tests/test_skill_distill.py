import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research_agent.external_skills import invoke_external_skill
from research_agent.skill_distill import SkillDistillError, distill_skill
from research_agent.skill_registry import SkillRegistryStore, manifest_from_payload

ROOT = Path(__file__).resolve().parents[1]


def write_skill(root: Path, name="external-review", license_value="MIT", scripts=True):
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    license_line = ("license: %s\n" % license_value) if license_value else ""
    (skill_dir / "SKILL.md").write_text(
        "---\nname: %s\ndescription: Use when reviewing evidence.\n%s---\n"
        "# Review\n\nCheck every result sentence against an evidence span.\n"
        % (name, license_line),
        encoding="utf-8",
    )
    if scripts:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.py").write_text(
            "import json, sys\n"
            "payload = json.load(sys.stdin)\n"
            "print(json.dumps({'echo': payload['input']}))\n",
            encoding="utf-8",
        )
        (scripts_dir / "helper.txt").write_text("support", encoding="utf-8")
    references = skill_dir / "references"
    references.mkdir()
    (references / "checklist.md").write_text("Check the evidence span.", encoding="utf-8")
    assets = skill_dir / "assets"
    assets.mkdir()
    (assets / "template.txt").write_text("Template", encoding="utf-8")
    (skill_dir / ".secret").write_text("must not be copied", encoding="utf-8")
    return skill_dir


def import_and_enable(root: Path, skill_dir: Path):
    registry = root / "skills.json"
    store = SkillRegistryStore(registry)
    imported = store.import_directory(skill_dir)
    skill_id = imported["snapshot"]["skills"][0]["id"]
    store.set_enabled(skill_id, True)
    return registry, store, skill_id


class SkillDistillTest(unittest.TestCase):
    def test_distill_copies_scripts_and_registers_disabled_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry, store, skill_id = import_and_enable(root, write_skill(root))
            result = distill_skill(
                skill_id=skill_id,
                library_dir=root / "library",
                registry_path=registry,
                human_reason="Needed for claim-evidence review",
                source_url="https://example.invalid/skill",
            )
            self.assertTrue(result["created"])
            candidate = result["candidate"]
            target = Path(result["path"])
            self.assertEqual(candidate["status"], "candidate")
            self.assertFalse(candidate["enabled"])
            self.assertTrue(candidate["has_scripts"])
            self.assertEqual(candidate["license"], "MIT")
            self.assertEqual(candidate["human_reason"], "Needed for claim-evidence review")
            self.assertTrue((target / "distill.json").is_file())
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertTrue((target / "scripts" / "run.py").is_file())
            self.assertTrue((target / "scripts" / "helper.txt").is_file())
            self.assertTrue((target / "references" / "checklist.md").is_file())
            self.assertTrue((target / "assets" / "template.txt").is_file())
            self.assertFalse((target / ".secret").exists())
            paths = {item["path"] for item in candidate["files"]}
            self.assertEqual(
                paths,
                {
                    "SKILL.md",
                    "scripts/run.py",
                    "scripts/helper.txt",
                    "references/checklist.md",
                    "assets/template.txt",
                },
            )
            run_file = target / "scripts" / "run.py"
            expected = hashlib.sha256(run_file.read_bytes()).hexdigest()
            recorded = next(item for item in candidate["files"] if item["path"] == "scripts/run.py")
            self.assertEqual(recorded["sha256"], expected)
            local = next(item for item in store.list() if item.get("id") == candidate["registered_skill_id"])
            self.assertFalse(local["enabled"])
            self.assertTrue(local["name"].startswith("local-"))
            self.assertEqual(local["source"], "custom")
            self.assertEqual(local["license"], "MIT")
            self.assertIn("Provenance", local["instructions"])
            self.assertIn("Claim/EA/gate", result["boundary"])
            reimported = SkillRegistryStore(root / "reimport.json").import_directory(target)
            self.assertEqual(len(reimported["accepted"]), 1)
            self.assertTrue(reimported["accepted"][0]["has_scripts"])
            self.assertEqual(reimported["accepted"][0]["license"], "MIT")

            # A human-reviewed candidate is usable without re-importing the source.
            store.set_enabled(candidate["registered_skill_id"], True)
            reuse = root / "reuse"
            reuse.mkdir()
            reused = invoke_external_skill(
                skill_id=candidate["registered_skill_id"],
                input_text="local reuse",
                trusted_scripts=True,
                workdir=str(reuse),
                registry_path=str(registry),
                usage_path=str(root / "reuse-usage.json"),
            )
            self.assertEqual(reused["output"]["echo"], "local reuse")
            self.assertEqual(reused["execution_mode"], "trusted_script")

    def test_distill_is_idempotent_and_rejects_bad_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry, store, skill_id = import_and_enable(root, write_skill(root))
            first = distill_skill(
                skill_id=skill_id,
                library_dir=root / "library",
                registry_path=registry,
                human_reason="review",
            )
            count = len(store.list())
            second = distill_skill(
                skill_id=skill_id,
                library_dir=root / "library",
                registry_path=registry,
                human_reason="review again",
            )
            self.assertFalse(second["created"])
            self.assertEqual(second["path"], first["path"])
            self.assertEqual(len(store.list()), count)
            with self.assertRaises(SkillDistillError):
                distill_skill(
                    skill_id=skill_id,
                    library_dir=root / "other-library",
                    registry_path=registry,
                    human_reason="",
                )
            with self.assertRaises(SkillDistillError):
                distill_skill(
                    skill_id=skill_id,
                    library_dir=root / "other-library",
                    registry_path=registry,
                    license="Apache-2.0",
                    human_reason="review",
                )

    def test_distill_requires_enabled_source_and_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry, store, skill_id = import_and_enable(
                root, write_skill(root, license_value="")
            )
            with self.assertRaises(SkillDistillError):
                distill_skill(
                    skill_id=skill_id,
                    library_dir=root / "library",
                    registry_path=registry,
                    human_reason="review",
                )
            store.set_enabled(skill_id, False)
            with self.assertRaises(SkillDistillError):
                distill_skill(
                    skill_id=skill_id,
                    library_dir=root / "library",
                    registry_path=registry,
                    license="MIT",
                    human_reason="review",
                )

            payload_registry = root / "payload-skills.json"
            payload_store = SkillRegistryStore(payload_registry)
            manifest = manifest_from_payload(
                {
                    "name": "remote-script-skill",
                    "description": "Remote script skill.",
                    "instructions": "Run the remote script.",
                    "license": "MIT",
                    "enabled": True,
                    "has_scripts": True,
                }
            )
            record, _ = payload_store.register(manifest)
            payload_store.set_enabled(record["id"], True)
            with self.assertRaises(SkillDistillError):
                distill_skill(
                    skill_id=record["id"],
                    library_dir=root / "payload-library",
                    registry_path=payload_registry,
                    human_reason="review",
                )

    def test_cli_distill_and_invoke_auto_distill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = write_skill(root, scripts=False)
            registry, store, skill_id = import_and_enable(root, skill_dir)
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "skill", "distill",
                    "--skill-id", skill_id,
                    "--library-dir", str(root / "cli-library"),
                    "--registry-path", str(registry),
                    "--human-reason", "CLI review",
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["created"])
            self.assertEqual(payload["candidate"]["license"], "MIT")

            # The CLI invoke path is covered without a model by asserting the
            # auto-distill flags are parsed and the missing profile is reported.
            missing = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "skill", "invoke",
                    "--skill-id", skill_id, "--input", "review",
                    "--distill-on-success", "--distill-reason", "CLI review",
                    "--library-dir", str(root / "auto-library"),
                    "--registry-path", str(registry),
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=env,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("profile_id", missing.stderr)


if __name__ == "__main__":
    unittest.main()
