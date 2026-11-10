"""Static lint for Agent Skills packages.

This never executes a skill or its scripts. It enforces a minimal, portable
manifest contract and flags dangerous script patterns for human review.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

SKILL_LINT_SCHEMA = "skill-lint-0.1"
ALLOWED_FRONTMATTER = {
    "name", "description", "version", "license", "allowed-tools", "tools",
    "when_to_use", "argument-hint", "arguments",
}
MAX_FILE_BYTES = 128 * 1024
MAX_DESCRIPTION = 1024
MAX_BODY_LINES = 500
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
DANGEROUS_RE = re.compile(
    r"(?<![A-Za-z0-9_])(eval|exec)\s*\(|os\.system\s*\(|os\.popen\s*\(|"
    r"subprocess\.(run|Popen|call)\s*\(|shutil\.rmtree\s*\("
)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
BOUNDARY = (
    "static text/path inspection only; scripts are never executed and a pass "
    "does not establish safety or scientific correctness"
)


def _parse_frontmatter(raw: str) -> Optional[Dict[str, str]]:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        closing = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return None
    meta: Dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip() or line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def _body_lines(raw: str) -> int:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return len(lines)
    try:
        closing = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return len(lines)
    return max(0, len(lines) - closing - 1)


def lint_skill_file(path: Path) -> Dict[str, Any]:
    path = Path(path)
    errors: List[str] = []
    warnings: List[str] = []
    if not path.is_file():
        return {
            "path": str(path), "name": "", "status": "invalid",
            "errors": ["SKILL.md does not exist"], "warnings": [], "body_lines": 0,
        }
    raw_bytes = path.read_bytes()
    if len(raw_bytes) > MAX_FILE_BYTES:
        errors.append("SKILL.md exceeds %d bytes" % MAX_FILE_BYTES)
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return {
            "path": str(path), "name": "", "status": "invalid",
            "errors": ["SKILL.md is not valid UTF-8"], "warnings": [], "body_lines": 0,
        }
    meta = _parse_frontmatter(raw)
    if meta is None:
        errors.append("missing YAML frontmatter")
        return {
            "path": str(path), "name": "", "status": "invalid",
            "errors": errors, "warnings": warnings, "body_lines": _body_lines(raw),
        }
    name = meta.get("name", "").strip()
    description = meta.get("description", "").strip()
    if not name:
        errors.append("missing name")
    elif not NAME_RE.match(name):
        errors.append("name must be lowercase letters/digits/hyphens (max 64)")
    if not description:
        errors.append("missing description (trigger condition)")
    elif "\n" in description:
        errors.append("description must be a single line")
    elif len(description) > MAX_DESCRIPTION:
        errors.append("description exceeds %d characters" % MAX_DESCRIPTION)
    unknown = sorted(set(meta) - ALLOWED_FRONTMATTER)
    if unknown:
        warnings.append("unknown frontmatter keys: " + ", ".join(unknown))
    body_lines = _body_lines(raw)
    if body_lines > MAX_BODY_LINES:
        errors.append("SKILL.md body exceeds %d lines" % MAX_BODY_LINES)
    if "TODO:" in raw:
        warnings.append("unresolved TODO marker")
    root = path.parent
    scripts = root / "scripts"
    if scripts.is_dir():
        for script in scripts.rglob("*"):
            if not script.is_file():
                continue
            try:
                resolved = script.resolve()
                resolved.relative_to(root.resolve())
            except (OSError, ValueError):
                errors.append("script escapes skill directory: " + str(script))
                continue
            try:
                text = resolved.read_text(encoding="utf-8", errors="replace")
            except OSError:
                warnings.append("cannot read script: " + str(script))
                continue
            if DANGEROUS_RE.search(text):
                errors.append("dangerous script pattern: " + str(script))
    for target in LINK_RE.findall(raw):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target_path = (root / target.split("#", 1)[0]).resolve()
        try:
            target_path.relative_to(root.resolve())
        except ValueError:
            errors.append("markdown link escapes skill directory: " + target)
            continue
        if not target_path.exists():
            warnings.append("markdown link target missing: " + target)
    return {
        "path": str(path),
        "name": name,
        "status": "invalid" if errors else ("attention" if warnings else "valid"),
        "errors": errors,
        "warnings": warnings,
        "description_length": len(description),
        "body_lines": body_lines,
        "has_scripts": scripts.is_dir(),
    }


def lint_skill_directory(root: Path) -> Dict[str, Any]:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("skill directory does not exist: " + str(root))
    skills = []
    names: Dict[str, str] = {}
    for skill_file in sorted(root.rglob("SKILL.md")):
        result = lint_skill_file(skill_file)
        name = result.get("name", "")
        if name and name in names:
            result["errors"].append(
                "duplicate skill name '%s' also used at %s" % (name, names[name])
            )
            result["status"] = "invalid"
        elif name:
            names[name] = str(skill_file)
        skills.append(result)
    errors = [item for skill in skills for item in skill.get("errors", [])]
    warnings = [item for skill in skills for item in skill.get("warnings", [])]
    return {
        "schema_version": SKILL_LINT_SCHEMA,
        "root": str(root),
        "status": "invalid" if errors else ("attention" if warnings else "valid"),
        "skill_count": len(skills),
        "skills": skills,
        "errors": errors,
        "warnings": warnings,
        "boundary": BOUNDARY,
    }
