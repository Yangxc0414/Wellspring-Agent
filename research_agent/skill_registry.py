"""Local registry for Agent Skills-style SKILL.md packages.

This is a catalog and validation layer, not an executor. Imported skills are
untrusted instructions until a human reviews them; scripts are never executed
and `allowed-tools` is a declaration, not a permission grant. The registry can
be used by the CLI/runtime to make local skills inspectable without turning the
browser or the agent into an arbitrary code runner.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .paths import DEFAULT_SKILL_REGISTRY_PATH
from .storage import JsonStoreError, now_iso, read_json, write_json_atomic

__all__ = [
    "DEFAULT_SKILL_REGISTRY_PATH",
    "MAX_INSTRUCTIONS",
    "SKILL_REGISTRY_SCHEMA",
    "SkillError",
    "SkillManifest",
    "SkillRegistryStore",
    "SkillScanResult",
    "manifest_from_payload",
    "parse_skill_markdown",
    "scan_skill_directory",
]

SKILL_REGISTRY_SCHEMA = "skill-registry-0.1"
MAX_SKILLS = 100
MAX_FILE_BYTES = 128 * 1024
MAX_INSTRUCTIONS = 8000
MAX_DESCRIPTION = 1024
MAX_NAME = 80


class SkillError(ValueError):
    pass


@dataclass
class SkillManifest:
    id: str
    name: str
    description: str
    instructions: str
    tools: List[str]
    version: str = "0.1.0"
    license: str = ""
    origin: str = ""
    content_hash: str = ""
    source: str = "imported"
    enabled: bool = False
    execution: str = "not_available"
    untrusted: bool = True
    risk_flags: List[str] = field(default_factory=list)
    has_scripts: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillScanResult:
    skills: List[SkillManifest]
    skipped: List[Dict[str, str]]
    errors: List[str]
    root: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "count": len(self.skills),
            "skills": [skill.to_dict() for skill in self.skills],
            "skipped": list(self.skipped),
            "errors": list(self.errors),
        }


def _now() -> str:
    return now_iso()


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower())
    return re.sub(r"-+", "-", cleaned).strip("-") or "skill"


def _skill_id(name: str, content_hash: str = "") -> str:
    base = "skill-" + _slug(name)
    return base if not content_hash else "%s-%s" % (base, content_hash[:6])


def _clean_scalar(value: str) -> str:
    return re.sub(r"\s+#.*$", "", value.strip()).strip("\"'").strip()


def _parse_frontmatter(raw: str) -> Optional[Tuple[Dict[str, str], str]]:
    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", raw)
    if not match:
        return None
    meta: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#")) or ":" not in line:
            continue
        key, value = line.split(":", 1)
        cleaned = _clean_scalar(value)
        if key.strip() and cleaned:
            meta[key.strip()] = cleaned
    return meta, raw[match.end():].strip()


def _tools_from(meta: Dict[str, str]) -> List[str]:
    raw = meta.get("allowed-tools") or meta.get("allowed_tools") or meta.get("tools") or ""
    tools = [
        item.strip().strip("\"'")
        for item in re.split(r"[,;\s]+", raw.replace("[", "").replace("]", ""))
        if item.strip()
    ]
    return list(dict.fromkeys(tools))[:20] or ["session.inspect"]


def _risk_flags(tools: Sequence[str], has_scripts: bool) -> List[str]:
    lowered = " ".join(str(tool).lower() for tool in tools)
    flags: List[str] = []
    if "*" in lowered or "all" in lowered.split():
        flags.append("unbounded_tools")
    if any(token in lowered for token in ("bash", "shell", "terminal", "exec")):
        flags.append("shell_capable")
    if any(token in lowered for token in ("write", "edit", "delete", "remove")):
        flags.append("write_capable")
    if any(token in lowered for token in ("network", "http", "fetch", "web", "browser")):
        flags.append("network_capable")
    if has_scripts:
        flags.append("has_scripts")
    return flags


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_skill_markdown(
    raw: str,
    origin: str = "",
    fallback_name: str = "",
    has_scripts: bool = False,
) -> SkillManifest:
    if len(raw.encode("utf-8")) > MAX_FILE_BYTES:
        raise SkillError("SKILL.md exceeds %d bytes" % MAX_FILE_BYTES)
    parsed = _parse_frontmatter(raw)
    if parsed is None:
        raise SkillError("missing YAML frontmatter")
    meta, body = parsed
    name = _clean_scalar(meta.get("name", fallback_name.replace(".md", "")))
    description = _clean_scalar(meta.get("description", ""))
    if not name:
        raise SkillError("missing name")
    if not description:
        raise SkillError("missing description (trigger condition)")
    tools = _tools_from(meta)
    instructions = body[:MAX_INSTRUCTIONS]
    if len(body) > MAX_INSTRUCTIONS:
        instructions += "\n\n[import truncated at %d characters]" % MAX_INSTRUCTIONS
    content_hash = _hash_text(raw)
    return SkillManifest(
        id=_skill_id(name, content_hash),
        name=name[:MAX_NAME],
        description=description[:MAX_DESCRIPTION],
        instructions=instructions,
        tools=tools,
        version=_clean_scalar(meta.get("version", "0.1.0")) or "0.1.0",
        license=_clean_scalar(meta.get("license", "")),
        origin=origin,
        content_hash=content_hash,
        source="imported",
        enabled=False,
        risk_flags=_risk_flags(tools, has_scripts),
        has_scripts=has_scripts,
        created_at=_now(),
        updated_at=_now(),
    )


def manifest_from_payload(payload: Dict[str, Any]) -> SkillManifest:
    if not isinstance(payload, dict):
        raise SkillError("skill payload must be an object")
    name = " ".join(str(payload.get("name", "")).split())
    description = " ".join(str(payload.get("description", "")).split())
    instructions = str(payload.get("instructions", "")).strip()
    if not name or len(name) > MAX_NAME:
        raise SkillError("name must be 1-%d characters" % MAX_NAME)
    if not description or len(description) > MAX_DESCRIPTION:
        raise SkillError("description must be 1-%d characters" % MAX_DESCRIPTION)
    if not instructions:
        raise SkillError("instructions must not be empty")
    tools = [str(item).strip() for item in payload.get("tools", []) if str(item).strip()]
    tools = list(dict.fromkeys(tools))[:20] or ["session.inspect"]
    source = str(payload.get("source", "imported"))
    if source not in ("imported", "custom"):
        raise SkillError("source must be imported or custom")
    version = str(payload.get("version", "0.1.0") or "0.1.0")
    has_scripts = bool(payload.get("has_scripts", False))
    canonical = json.dumps(
        {
            "name": name,
            "description": description,
            "instructions": instructions,
            "tools": tools,
            "version": version,
            "has_scripts": has_scripts,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    content_hash = _hash_text(canonical)
    return SkillManifest(
        id=_skill_id(name, content_hash),
        name=name,
        description=description,
        instructions=instructions[:MAX_INSTRUCTIONS],
        tools=tools,
        version=version,
        license=str(payload.get("license", "")),
        origin=str(payload.get("origin", "frontend")),
        content_hash=content_hash,
        source=source,
        enabled=bool(payload.get("enabled", False)),
        risk_flags=_risk_flags(tools, has_scripts),
        has_scripts=has_scripts,
        created_at=_now(),
        updated_at=_now(),
    )


class SkillRegistryStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @property
    def boundary(self) -> str:
        return (
            "catalog only: imported skills are untrusted instructions; scripts are never executed, "
            "allowed-tools is a declaration, and nothing here enters Claim/EA/gate"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            payload = read_json(self.path)
        except JsonStoreError as exc:
            raise SkillError(str(exc))
        if payload is None:
            return []
        if not isinstance(payload, dict) or not isinstance(payload.get("skills"), list):
            raise SkillError("skill registry must contain a skills list")
        return [item for item in payload["skills"] if isinstance(item, dict)]

    def _save(self, skills: List[Dict[str, Any]]) -> None:
        write_json_atomic(
            self.path,
            {
                "schema_version": SKILL_REGISTRY_SCHEMA,
                "updated_at": _now(),
                "count": len(skills),
                "skills": skills,
                "boundary": self.boundary,
            },
        )

    def _unique_id(self, manifest: SkillManifest, skills: List[Dict[str, Any]]) -> str:
        existing = {str(item.get("id")) for item in skills}
        if manifest.id not in existing:
            return manifest.id
        if any(item.get("content_hash") == manifest.content_hash for item in skills):
            return manifest.id
        return "%s-%s" % (manifest.id, _now_stamp().lower())

    def register(self, manifest: SkillManifest) -> Tuple[Dict[str, Any], bool]:
        skills = self._load()
        for item in skills:
            if str(item.get("name", "")).lower() == manifest.name.lower():
                return item, False
            if manifest.content_hash and item.get("content_hash") == manifest.content_hash:
                return item, False
        if len(skills) >= MAX_SKILLS:
            raise SkillError("skill registry is full (%d)" % MAX_SKILLS)
        manifest.id = self._unique_id(manifest, skills)
        record = manifest.to_dict()
        skills.insert(0, record)
        self._save(skills)
        return record, True

    def register_many(self, manifests: Iterable[SkillManifest]) -> Dict[str, Any]:
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, str]] = []
        for manifest in manifests:
            try:
                record, created = self.register(manifest)
                if created:
                    accepted.append(record)
                else:
                    rejected.append({"name": manifest.name, "reason": "duplicate skill name or content"})
            except SkillError as exc:
                rejected.append({"name": manifest.name, "reason": str(exc)})
        return {"accepted": accepted, "rejected": rejected, "snapshot": self.snapshot()}

    def list(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        skills = sorted(self._load(), key=lambda item: str(item.get("created_at", "")), reverse=True)
        if enabled_only:
            return [item for item in skills if item.get("enabled")]
        return skills

    def set_enabled(self, skill_id: str, enabled: bool) -> Dict[str, Any]:
        skills = self._load()
        target = next((item for item in skills if item.get("id") == skill_id), None)
        if target is None:
            raise SkillError("skill not found: " + skill_id)
        target["enabled"] = bool(enabled)
        target["updated_at"] = _now()
        self._save(skills)
        return target

    def delete(self, skill_id: str) -> bool:
        skills = self._load()
        remaining = [item for item in skills if item.get("id") != skill_id]
        if len(remaining) == len(skills):
            return False
        self._save(remaining)
        return True

    def snapshot(self) -> Dict[str, Any]:
        skills = self.list()
        return {
            "schema_version": SKILL_REGISTRY_SCHEMA,
            "generated_at": _now(),
            "count": len(skills),
            "skills": skills,
            "boundary": self.boundary,
        }

    def export(self, output: Path) -> Dict[str, Any]:
        snapshot = self.snapshot()
        write_json_atomic(Path(output), snapshot)
        return {"output": str(output), "count": snapshot["count"]}

    def import_directory(self, root: Path) -> Dict[str, Any]:
        result = scan_skill_directory(Path(root))
        registered = self.register_many(result.skills)
        return {
            "scan": result.to_dict(),
            "accepted": registered["accepted"],
            "rejected": result.skipped + registered["rejected"],
            "snapshot": registered["snapshot"],
        }


SCRIPT_SUFFIXES = (".py", ".sh", ".cmd", ".bat", ".js", ".ts", ".ps1")


def _has_scripts(directory: Path) -> bool:
    scripts = directory / "scripts"
    try:
        if scripts.is_dir() and any(
            path.is_file() and path.suffix.lower() in SCRIPT_SUFFIXES
            for path in scripts.rglob("*")
        ):
            return True
        return any(
            path.is_file() and path.suffix.lower() in SCRIPT_SUFFIXES
            for path in directory.iterdir()
        )
    except OSError:
        return False


def scan_skill_directory(root: Path) -> SkillScanResult:
    root = Path(root)
    if not root.is_dir():
        raise SkillError("skill path is not a directory: " + str(root))
    skills: List[SkillManifest] = []
    skipped: List[Dict[str, str]] = []
    errors: List[str] = []
    seen: set = set()
    candidates: List[Path] = []
    for path in sorted(root.rglob("SKILL.md")):
        if path.is_file():
            candidates.append(path)
    try:
        for path in sorted(root.iterdir()):
            if path.is_file() and path.suffix.lower() == ".md" and path.name.lower() != "skill.md":
                candidates.append(path)
    except OSError as exc:
        errors.append(str(exc))
    candidates = candidates[:200]
    for path in candidates:
        if len(skills) >= MAX_SKILLS:
            skipped.append({"name": str(path), "reason": "skill limit reached"})
            continue
        try:
            relative = path.relative_to(root).as_posix()
            if relative in seen:
                continue
            seen.add(relative)
            raw = path.read_text(encoding="utf-8", errors="replace")
            manifest = parse_skill_markdown(raw, origin=str(path), fallback_name=path.parent.name, has_scripts=_has_scripts(path.parent))
            skills.append(manifest)
        except (OSError, UnicodeError, SkillError) as exc:
            skipped.append({"name": str(path), "reason": str(exc)})
    return SkillScanResult(skills=skills, skipped=skipped, errors=errors, root=str(root))
