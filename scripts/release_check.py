#!/usr/bin/env python3
"""Check the public-release surface without network or third-party packages.

This is a guardrail, not a legal review. It verifies that the delivery docs exist,
local-only trees are excluded, and common credential/local-path leaks are absent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


REQUIRED_DOCS = (
    "README.md",
    "LICENSING.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "THIRD_PARTY_NOTICES.md",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "QUICKSTART.md",
    ".mcp.json.example",
    "requirements-dev.txt",
    ".github/workflows/ci.yml",
)

REQUIRED_GITIGNORE = (
    "runtime_data/",
    "oss/full/*",
    "oss/*-main/",
    "oss/*-master/",
    "oss/*-curated/",
    "oss/writing-skills/*",
    "research_agent/vendor/astradraw/",
    "research/anthropic/*",
    "claude-code-main/",
    "template_refs/",
    "/agent-reliability-survey/",
    "/manuscript/",
    "/research/frontier/",
    "/.mcp.json",
    ".env",
)

LOCAL_ONLY_DIRS = (
    "runtime_data",
    "oss/full",
    "oss/writing-skills",
    "research_agent/vendor/astradraw",
    "research/anthropic/repos",
    "claude-code-main",
    "cortex-agent",
    "template_refs",
    "agent-reliability-survey",
    "manuscript",
    "research/frontier",
)

SKIP_DIRS = {
    ".git",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "runtime_data",
    "dist",
    "dist-github",
    "dist-github-remote",
    "test-results",
    "playwright-report",
    # agent-tool local state (machine paths, caches); not shippable source
    ".workbuddy",
    ".claude",
    ".qoder",
    ".zcode",
}
SKIP_PREFIXES = (
    "oss",
    "research/anthropic",
    "research_agent/vendor/astradraw",
    "claude-code-main",
    "cortex-agent",
    "template_refs",
)
TEXT_SUFFIXES = {
    ".py",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".example",
}
CODE_SUFFIXES = {".py", ".json", ".toml", ".yaml", ".yml", ".ts", ".tsx", ".js", ".mjs"}

SECRET_PATTERNS = (
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "private key block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "assigned secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|access[_-]?token)\b\s*[:=]\s*"
            r"['\"][A-Za-z0-9_\-]{20,}['\"]"
        ),
    ),
)

WINDOWS_HOME = re.compile(r"(?i)\b[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\\/\s\"']+")
POSIX_HOME = re.compile(r"(?<![\w.])/(?:Users|home)/[A-Za-z0-9._-]+/")


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _walk_files(root: Path, suffixes: set[str]):
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_dir = _rel(current, root) if current != root else ""
        kept = []
        for name in dirnames:
            rel = (rel_dir + "/" + name).lstrip("/")
            if name in SKIP_DIRS or any(rel == p or rel.startswith(p + "/") for p in SKIP_PREFIXES):
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            path = current / name
            if path.suffix.lower() not in suffixes and not name.endswith(".env.example"):
                continue
            try:
                if path.stat().st_size > 1_500_000:
                    continue
            except OSError:
                continue
            yield path


def _scan_secrets(root: Path):
    findings = []
    for path in _walk_files(root, TEXT_SUFFIXES):
        rel = _rel(path, root)
        if rel.startswith("tests/") or rel.startswith("apps/web/tests/"):
            continue
        # a nested release bundle is scanned with the bundle as its own root, so its
        # tests/ allowlist lines up; skipping it here keeps fixture keys from being
        # reported twice under a path the allowlist cannot match
        if rel.startswith(NESTED_PRODUCT_DIRS):
            continue
        if rel in ("SECURITY.md", "THIRD_PARTY_NOTICES.md"):
            continue
        text = _read(path)
        for label, pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append({"kind": "credential", "label": label, "path": rel})
                break
    return findings


NESTED_PRODUCT_DIRS = ("Wellspring-Agent/",)


def _scan_local_paths(root: Path):
    findings = []
    for path in _walk_files(root, CODE_SUFFIXES):
        rel = _rel(path, root)
        if rel.startswith("tests/") or rel.startswith("apps/web/tests/"):
            continue
        if rel.startswith(NESTED_PRODUCT_DIRS):
            continue
        text = _read(path)
        match = WINDOWS_HOME.search(text) or POSIX_HOME.search(text)
        if match:
            severity = "warning" if rel == ".mcp.json" else "blocker"
            findings.append(
                {
                    "kind": "local_path",
                    "path": rel,
                    "match": match.group(0),
                    "severity": severity,
                }
            )
    # Published JSON is served verbatim, and JSON escapes backslashes, so a path can hide
    # from the extension list above (``D:\\Users\\alice`` never matches a single-backslash
    # pattern). Scan the shipped data files explicitly instead of widening CODE_SUFFIXES,
    # which would also sweep thousands of test fixtures.
    site = root / "site"
    if site.is_dir():
        for path in sorted(site.rglob("*.json")):
            rel = _rel(path, root)
            text = _read(path).replace("\\\\", "\\")
            match = WINDOWS_HOME.search(text) or POSIX_HOME.search(text)
            if match:
                findings.append(
                    {
                        "kind": "local_path",
                        "path": rel,
                        "match": match.group(0),
                        "severity": "blocker",
                    }
                )
    return findings


def check_release(root: Path, for_public_release: bool = False) -> dict:
    root = Path(root).resolve()
    blockers = []
    warnings = []
    info = []

    missing = [name for name in REQUIRED_DOCS if not (root / name).is_file()]
    for name in missing:
        blockers.append({"kind": "missing_doc", "path": name})

    gitignore = _read(root / ".gitignore")
    ignore_lines = {line.strip() for line in gitignore.splitlines() if line.strip()}
    for pattern in REQUIRED_GITIGNORE:
        if pattern not in ignore_lines:
            blockers.append({"kind": "missing_gitignore", "pattern": pattern})

    if (root / "LICENSE").is_file():
        info.append({"kind": "license", "status": "root LICENSE present"})
    else:
        message = {
            "kind": "license",
            "status": "root LICENSE pending; project is not yet open source",
        }
        if for_public_release:
            blockers.append(message)
        else:
            warnings.append(message)

    for name in LOCAL_ONLY_DIRS:
        path = root / name
        if path.exists():
            info.append({"kind": "local_only_tree", "path": name, "excluded_by": ".gitignore"})

    secret_findings = _scan_secrets(root)
    blockers.extend(secret_findings)

    path_findings = _scan_local_paths(root)
    for finding in path_findings:
        if finding["severity"] == "blocker":
            blockers.append(finding)
        else:
            warnings.append(finding)

    pyproject = _read(root / "pyproject.toml")
    if "license" not in pyproject.lower():
        warning = {"kind": "package_metadata", "path": "pyproject.toml", "field": "license"}
        if for_public_release:
            blockers.append(warning)
        else:
            warnings.append(warning)

    web_package = root / "apps/web/package.json"
    if web_package.is_file():
        try:
            payload = json.loads(_read(web_package))
        except json.JSONDecodeError:
            payload = {}
        if not payload.get("license"):
            warning = {
                "kind": "package_metadata",
                "path": "apps/web/package.json",
                "field": "license",
            }
            if for_public_release:
                blockers.append(warning)
            else:
                warnings.append(warning)

    return {
        "root": str(root),
        "for_public_release": for_public_release,
        "status": "blocked" if blockers else "ok",
        "blockers": blockers,
        "warnings": warnings,
        "info": info,
        "checked_docs": len(REQUIRED_DOCS),
        "checked_ignore_patterns": len(REQUIRED_GITIGNORE),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on warnings")
    parser.add_argument(
        "--for-public-release",
        action="store_true",
        help="treat a pending license and missing package license fields as blockers",
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    report = check_release(Path(args.root), for_public_release=args.for_public_release)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "release surface: %s (%d blockers, %d warnings)"
            % (report["status"], len(report["blockers"]), len(report["warnings"]))
        )
        for item in report["blockers"]:
            print("BLOCKER %s" % json.dumps(item, ensure_ascii=False))
        for item in report["warnings"]:
            print("WARN    %s" % json.dumps(item, ensure_ascii=False))
        for item in report["info"]:
            print("INFO    %s" % json.dumps(item, ensure_ascii=False))

    if report["blockers"]:
        return 1
    if args.strict and report["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
