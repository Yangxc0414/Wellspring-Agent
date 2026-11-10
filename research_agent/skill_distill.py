"""Distill a used external skill into a governed, disabled local candidate.

Distillation copies SKILL.md and scripts into a local skill folder, records
provenance/license/per-file hashes, and registers a disabled local candidate.
It never executes, enables or activates the candidate, and it never proves
quality. A human must review and enable it.
"""

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .skill_registry import SkillRegistryStore, manifest_from_payload
from .storage import write_json_atomic

DISTILL_SCHEMA = "skill-distill-0.1"
DISTILL_BOUNDARY = (
    "distillation localizes an external skill for review; it does not prove quality, "
    "does not enable the candidate, does not execute scripts, and never enters "
    "Claim/EA/gate"
)
MAX_RESOURCE_FILES = 500
MAX_RESOURCE_BYTES = 25 * 1024 * 1024
SCRIPT_SUFFIXES = (".py", ".sh", ".cmd", ".bat", ".ps1", ".js", ".ts")
RESOURCE_DIRS = ("scripts", "references", "assets")
SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv", ".idea", ".vscode"}


class SkillDistillError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", str(value or "").lower()).strip("-")
    return cleaned[:50] or "skill"


def _write_text(path: Path, text: str) -> None:
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _find_skill(registry_path: Path, skill_id: str) -> Dict[str, Any]:
    wanted = str(skill_id or "").strip()
    for skill in SkillRegistryStore(registry_path).list():
        if wanted in (str(skill.get("id")), str(skill.get("name"))):
            return skill
    raise SkillDistillError("skill not found in registry: " + wanted)


def _source_root(skill: Dict[str, Any]) -> Optional[Path]:
    origin = Path(str(skill.get("origin") or ""))
    if origin.is_file():
        return origin.resolve().parent
    if origin.is_dir():
        return origin.resolve()
    return None


def _skip_path(relative: Path) -> bool:
    return any(
        part.startswith(".") or part in SKIP_DIRS
        for part in relative.parts
    )


def _resource_sources(source: Path) -> List[Path]:
    files: List[Path] = []
    seen = set()

    def add(path: Path) -> None:
        if path.is_symlink() or path.name.lower() == "distill.json":
            return
        try:
            resolved = path.resolve()
            relative = resolved.relative_to(source.resolve())
        except (OSError, ValueError):
            return
        if not resolved.is_file() or resolved in seen or _skip_path(relative):
            return
        seen.add(resolved)
        files.append(resolved)

    for dirname in RESOURCE_DIRS:
        directory = source / dirname
        if directory.is_dir():
            for path in sorted(directory.rglob("*")):
                add(path)
    try:
        for path in sorted(source.iterdir()):
            if path.is_file() and path.name.lower() != "skill.md":
                add(path)
    except OSError:
        pass
    return files


def _copy_resources(source: Path, target: Path) -> List[Dict[str, Any]]:
    files = _resource_sources(source)
    if len(files) > MAX_RESOURCE_FILES:
        raise SkillDistillError(
            "resource package has too many files (%d > %d)"
            % (len(files), MAX_RESOURCE_FILES)
        )
    total = 0
    for path in files:
        try:
            total += path.stat().st_size
        except OSError as exc:
            raise SkillDistillError("cannot read resource file: %s" % exc)
        if total > MAX_RESOURCE_BYTES:
            raise SkillDistillError(
                "resource package exceeds %d bytes; refusing to copy" % MAX_RESOURCE_BYTES
            )
    copied: List[Dict[str, Any]] = []
    for path in files:
        relative = path.relative_to(source.resolve())
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(path), str(destination))
        copied.append(
            {
                "path": relative.as_posix(),
                "kind": relative.parts[0] if len(relative.parts) > 1 else "resource",
                "sha256": _sha256_file(destination),
                "size": destination.stat().st_size,
            }
        )
    return copied


def _is_script(relative: str) -> bool:
    path = Path(relative)
    if path.suffix.lower() not in SCRIPT_SUFFIXES:
        return False
    return path.parts[0] == "scripts" or len(path.parts) == 1


def _register_candidate(
    registry_path: Path,
    local_name: str,
    description: str,
    instructions: str,
    tools: List[str],
    license_value: str,
    skill_path: Path,
    has_scripts: bool,
) -> Dict[str, Any]:
    payload = {
        "name": local_name,
        "description": description,
        "instructions": instructions,
        "tools": tools or ["session.inspect"],
        "version": "0.1.0-local",
        "license": license_value,
        "origin": str(skill_path),
        "source": "custom",
        "enabled": False,
        "has_scripts": has_scripts,
    }
    manifest = manifest_from_payload(payload)
    record, created = SkillRegistryStore(registry_path).register(manifest)
    if not created and record.get("enabled"):
        raise SkillDistillError(
            "local candidate already exists and is enabled; review it directly: "
            + str(record.get("id"))
        )
    return {"record": record, "created": created}


def distill_skill(
    skill_id: str,
    library_dir: Path,
    registry_path: Path,
    license: str = "",
    human_reason: str = "",
    source_url: str = "",
) -> Dict[str, Any]:
    registry_path = Path(registry_path)
    skill = _find_skill(registry_path, skill_id)
    if not skill.get("enabled"):
        raise SkillDistillError("only an enabled, reviewed skill can be distilled")
    reason = str(human_reason or "").strip()
    if not reason:
        raise SkillDistillError("human_reason is required for distillation")
    declared_license = str(skill.get("license") or "").strip()
    explicit_license = str(license or "").strip()
    if explicit_license and declared_license and explicit_license != declared_license:
        raise SkillDistillError(
            "license override conflicts with the source skill license (%s)"
            % declared_license
        )
    license_value = explicit_license or declared_license
    if not license_value:
        raise SkillDistillError(
            "license is required for distillation; pass --license or add it to the source skill"
        )
    source_root = _source_root(skill)
    if source_root is None and skill.get("has_scripts"):
        raise SkillDistillError(
            "script-bearing skill has no local origin folder; import the folder before distillation"
        )
    instructions = str(skill.get("instructions") or "").strip()
    source_hash = str(skill.get("content_hash") or hashlib.sha256(
        instructions.encode("utf-8")
    ).hexdigest())
    slug = _slug(str(skill.get("name") or "skill"))
    target = Path(library_dir).expanduser().resolve() / (
        "%s-%s" % (slug, source_hash[:8])
    )
    manifest_path = target / "distill.json"
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "created": False,
            "candidate": existing,
            "path": str(target),
            "boundary": DISTILL_BOUNDARY,
        }
    target.mkdir(parents=True, exist_ok=True)
    local_name = ("local-%s-%s" % (slug, source_hash[:8]))[:64]
    description = ("[Local candidate] " + str(
        skill.get("description") or "Distilled external skill"
    ).replace("\n", " "))[:1024]
    body = (
        "# %s\n\n"
        "> Local candidate distilled from `%s`; disabled until human review.\n\n"
        "## Provenance\n\n"
        "- source skill: `%s` (`%s`) v%s\n"
        "- source hash: `%s`\n"
        "- license: %s\n"
        "- source url: %s\n"
        "- distilled at: %s\n"
        "- human reason: %s\n\n"
        "## Operating contract\n\n"
        "- Advisory by default; no claims, evidence, gates, signatures or export.\n"
        "- Scripts, if present, execute only with explicit trusted-script opt-in and are not sandboxed.\n"
        "- Allowed tools are declarative and are not granted automatically.\n"
        "- This candidate is disabled until a human reviews and enables it.\n\n"
        "## Instructions\n\n%s\n"
        % (
            local_name,
            skill.get("name"),
            skill.get("id"),
            skill.get("name"),
            skill.get("version"),
            source_hash,
            license_value,
            source_url or "-",
            _now(),
            reason,
            instructions,
        )
    )
    tool_values = [
        re.sub(r"[\r\n;]+", " ", str(tool)).strip()
        for tool in (skill.get("tools") or [])
        if str(tool).strip()
    ]
    tools_line = (
        "allowed-tools: %s\n" % ", ".join(tool_values) if tool_values else ""
    )
    skill_text = (
        "---\nname: %s\ndescription: %s\nversion: 0.1.0-local\n%slicense: %s\n---\n\n%s"
        % (
            local_name,
            description,
            tools_line,
            license_value.replace("\n", " "),
            body,
        )
    )
    skill_path = target / "SKILL.md"
    _write_text(skill_path, skill_text)
    files: List[Dict[str, Any]] = [
        {
            "path": "SKILL.md",
            "sha256": _sha256_file(skill_path),
            "size": skill_path.stat().st_size,
        }
    ]
    if source_root is not None:
        files.extend(_copy_resources(source_root, target))
    has_scripts = any(_is_script(str(item["path"])) for item in files)
    if skill.get("has_scripts") and not has_scripts:
        raise SkillDistillError(
            "source skill declares scripts but no runnable script files were found to copy"
        )
    registration = _register_candidate(
        registry_path=registry_path,
        local_name=local_name,
        description=description,
        instructions=body,
        tools=list(skill.get("tools") or []),
        license_value=license_value,
        skill_path=skill_path,
        has_scripts=has_scripts,
    )
    candidate = {
        "schema_version": DISTILL_SCHEMA,
        "candidate_id": "DIST-%s-%s" % (slug, source_hash[:8]),
        "local_name": local_name,
        "source_skill_id": skill.get("id"),
        "source_name": skill.get("name"),
        "source_version": skill.get("version"),
        "source_hash": source_hash,
        "license": license_value,
        "declared_license": declared_license,
        "source_url": source_url,
        "human_reason": reason,
        "status": "candidate",
        "enabled": False,
        "has_scripts": has_scripts,
        "files": files,
        "registered_skill_id": registration["record"].get("id"),
        "registration_created": registration["created"],
        "created_at": _now(),
        "boundary": DISTILL_BOUNDARY,
    }
    write_json_atomic(manifest_path, candidate)
    return {
        "created": True,
        "candidate": candidate,
        "path": str(target),
        "registry_created": registration["created"],
        "registered_skill": registration["record"],
        "boundary": DISTILL_BOUNDARY,
    }
