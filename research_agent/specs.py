"""Markdown module specs: read, validate, and minimally update.

The frontmatter is intentionally a small YAML subset (scalars and string lists)
so the toolchain stays dependency-free. The body is treated as prose and is only
changed by explicit section patches or changelog appends.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import atomic_replace


class SpecError(ValueError):
    """Raised when a module spec is missing, malformed, or fails validation."""


ALLOWED_STATUS = {"draft", "pilot", "active", "deprecated", "revoked"}
LIST_FIELDS = {"inputs", "outputs", "tools", "gates", "invariants"}
SCALAR_FIELDS = {"id", "name", "stage", "version", "status", "owner"}
REQUIRED_FIELDS = {"id", "name", "stage", "version", "status", "owner", "outputs"}
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass
class ModuleSpec:
    id: str
    name: str
    stage: str
    version: str
    status: str
    owner: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    gates: List[str] = field(default_factory=list)
    invariants: List[str] = field(default_factory=list)
    body: str = ""
    path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "stage": self.stage,
            "version": self.version,
            "status": self.status,
            "owner": self.owner,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "tools": list(self.tools),
            "gates": list(self.gates),
            "invariants": list(self.invariants),
            "path": str(self.path) if self.path else None,
        }


def split_frontmatter(text: str) -> tuple:
    normalized = text.replace("\r\n", "\n")
    lines = normalized.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SpecError("SPEC.md must start with a '---' frontmatter block")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise SpecError("SPEC.md frontmatter is not closed with '---'")
    return lines[1:end], "\n".join(lines[end + 1:]).lstrip("\n")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_frontmatter(lines: List[str]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        if stripped.startswith("- "):
            if current_key is None:
                raise SpecError("list item without a key")
            if not isinstance(data.get(current_key), list):
                data[current_key] = []
            data[current_key].append(_strip_quotes(stripped[2:]))
            continue
        if ":" not in raw:
            raise SpecError("unsupported frontmatter line: " + raw)
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if not value:
            data[key] = []
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [_strip_quotes(part) for part in inner.split(",") if part.strip()] if inner else []
        else:
            data[key] = _strip_quotes(value)
    return data


def _as_string_list(value: Any, key: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise SpecError("field '%s' must be a string or list" % key)


def parse_spec(text: str, path: Optional[Path] = None) -> ModuleSpec:
    fm_lines, body = split_frontmatter(text)
    data = parse_frontmatter(fm_lines)
    missing = sorted(REQUIRED_FIELDS - set(data))
    if missing:
        raise SpecError("missing required fields: " + ", ".join(missing))
    spec = ModuleSpec(
        id=str(data["id"]),
        name=str(data["name"]),
        stage=str(data["stage"]),
        version=str(data["version"]),
        status=str(data["status"]),
        owner=str(data["owner"]),
        inputs=_as_string_list(data.get("inputs"), "inputs"),
        outputs=_as_string_list(data.get("outputs"), "outputs"),
        tools=_as_string_list(data.get("tools"), "tools"),
        gates=_as_string_list(data.get("gates"), "gates"),
        invariants=_as_string_list(data.get("invariants"), "invariants"),
        body=body,
        path=path,
    )
    validate_spec(spec)
    return spec


def validate_spec(spec: ModuleSpec) -> None:
    if not ID_RE.match(spec.id):
        raise SpecError("id must be lower-kebab-case: " + spec.id)
    if not VERSION_RE.match(spec.version):
        raise SpecError("version must be MAJOR.MINOR.PATCH: " + spec.version)
    if spec.status not in ALLOWED_STATUS:
        raise SpecError("unknown status '%s'; allowed: %s" % (spec.status, sorted(ALLOWED_STATUS)))
    if not spec.stage.strip():
        raise SpecError("stage must not be empty")
    if not spec.outputs:
        raise SpecError("outputs must not be empty")
    if spec.path is not None and spec.path.parent.name != spec.id:
        raise SpecError("spec id '%s' does not match directory '%s'" % (spec.id, spec.path.parent.name))


def _find_key_line(lines: List[str], key: str) -> Optional[int]:
    pattern = re.compile(r"^" + re.escape(key) + r"\s*:")
    for i, line in enumerate(lines):
        if pattern.match(line):
            return i
    return None


def _set_scalar(lines: List[str], key: str, value: str) -> List[str]:
    out = list(lines)
    idx = _find_key_line(out, key)
    if idx is None:
        out.append("%s: %s" % (key, value))
    else:
        out[idx] = "%s: %s" % (key, value)
    return out


def _merged(existing: List[str], added: List[str]) -> List[str]:
    """Append-and-dedupe: a minimal update must not silently drop list entries."""
    merged: List[str] = []
    for value in list(existing) + list(added):
        item = str(value)
        if item not in merged:
            merged.append(item)
    return merged


def _set_list(lines: List[str], key: str, values: List[str]) -> List[str]:
    out = list(lines)
    idx = _find_key_line(out, key)
    rendered = ["%s:" % key] + ["  - %s" % item for item in values]
    if idx is None:
        out.extend(rendered)
        return out
    end = idx + 1
    while end < len(out):
        stripped = out[end].strip()
        if stripped == "" or out[end].lstrip().startswith("- "):
            end += 1
        else:
            break
    out[idx:end] = rendered
    return out


def _append_changelog(text: str, version: str, status: str, message: str) -> str:
    lines = text.replace("\r\n", "\n").splitlines()
    entry = "- %s · v%s · status=%s · %s" % (date.today().isoformat(), version, status, message.strip())
    heading_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "## Changelog":
            heading_idx = i
            break
    if heading_idx is None:
        while lines and lines[-1] == "":
            lines.pop()
        lines.extend(["", "## Changelog", "", entry, ""])
        return "\n".join(lines) + "\n"
    insert_at = heading_idx + 1
    while insert_at < len(lines) and not lines[insert_at].strip():
        insert_at += 1
    lines.insert(insert_at, entry)
    return "\n".join(lines) + "\n"


def _patch_section(text: str, section: str, new_text: str) -> str:
    lines = text.replace("\r\n", "\n").splitlines()
    heading = "## " + section
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i
            break
    if start is None:
        while lines and lines[-1] == "":
            lines.pop()
        lines.extend(["", heading, "", new_text.strip(), ""])
        return "\n".join(lines) + "\n"
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    replacement = ["", new_text.strip(), ""]
    if end < len(lines):
        replacement.append("")
    lines[start + 1:end] = replacement
    return "\n".join(lines) + "\n"


class SpecStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[1] / "modules"

    def path_for(self, module_id: str) -> Path:
        return self.root / module_id / "SPEC.md"

    def list_specs(self) -> List[ModuleSpec]:
        specs: List[ModuleSpec] = []
        for path in sorted(self.root.glob("*/SPEC.md")):
            if path.parent.name.startswith("_"):
                continue
            specs.append(parse_spec(path.read_text(encoding="utf-8"), path))
        return specs

    def load(self, module_id: str) -> ModuleSpec:
        path = self.path_for(module_id)
        if not path.is_file():
            raise SpecError("module spec not found: " + str(path))
        return parse_spec(path.read_text(encoding="utf-8"), path)

    def _write_atomic(self, path: Path, content: str) -> None:
        tmp = path.with_suffix(".md.tmp")
        with open(str(tmp), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        atomic_replace(tmp, path)

    def update(
        self,
        module_id: str,
        *,
        version: Optional[str] = None,
        status: Optional[str] = None,
        name: Optional[str] = None,
        stage: Optional[str] = None,
        inputs: Optional[List[str]] = None,
        outputs: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        gates: Optional[List[str]] = None,
        invariants: Optional[List[str]] = None,
        changelog: Optional[str] = None,
        replace_lists: bool = False,
    ) -> ModuleSpec:
        if not changelog or not changelog.strip():
            raise SpecError("changelog is required for a spec update")
        spec = self.load(module_id)
        path = spec.path or self.path_for(module_id)
        fm_lines, body = split_frontmatter(path.read_text(encoding="utf-8"))
        scalars = {
            "version": version,
            "status": status,
            "name": name,
            "stage": stage,
        }
        for key, value in scalars.items():
            if value is not None:
                fm_lines = _set_scalar(fm_lines, key, value)
        lists = {
            "inputs": inputs,
            "outputs": outputs,
            "tools": tools,
            "gates": gates,
            "invariants": invariants,
        }
        existing = {
            "inputs": spec.inputs,
            "outputs": spec.outputs,
            "tools": spec.tools,
            "gates": spec.gates,
            "invariants": spec.invariants,
        }
        for key, value in lists.items():
            if value is None:
                continue
            applied = value if replace_lists else _merged(existing.get(key) or [], value)
            fm_lines = _set_list(fm_lines, key, applied)
        new_text = "---\n" + "\n".join(fm_lines) + "\n---\n\n" + body
        new_text = _append_changelog(
            new_text,
            version or spec.version,
            status or spec.status,
            changelog,
        )
        parsed = parse_spec(new_text, path)
        self._write_atomic(path, new_text)
        return parsed

    def patch_section(self, module_id: str, section: str, text: str) -> ModuleSpec:
        if not section.strip():
            raise SpecError("section must not be empty")
        spec = self.load(module_id)
        path = spec.path or self.path_for(module_id)
        new_text = _patch_section(path.read_text(encoding="utf-8"), section.strip(), text)
        parsed = parse_spec(new_text, path)
        self._write_atomic(path, new_text)
        return parsed
