"""Repository hygiene check: generated copies, big caches, stale workflow paths.

The repository has three kinds of drift that are invisible in code review and expensive
later: (1) generated site copies silently diverging from their sources, (2) multi-hundred-MB
local caches (browser profiles, model caches) that make clones slow and confuse tooling,
(3) CI path filters that point at files nothing produces any more.

This checker is read-only and has no third-party dependencies. Exit code 1 means at least
one blocker; warnings never fail the run.

Usage:
    python scripts/repo_hygiene.py
    python scripts/repo_hygiene.py --json
"""

import argparse
import fnmatch
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Generated from <source> by scripts/build-site.mjs; the copy must match the source.
SITE_COPIES = (
    ("demo/index.html", "site/demo/index.html"),
    ("README.md", "site/docs/README.md"),
    ("design/16-科研Skill生态调研与动态流程编排.md", "site/docs/16-科研Skill生态调研.md"),
    ("design/17-基于Skill契约的上层微服务架构.md", "site/docs/17-上层微服务架构.md"),
    ("design/18-GitHub Pages部署与多智能体Skill设计.md", "site/docs/18-GitHub Pages部署与多智能体Skill设计.md"),
    ("design/71-四图对照与解耦设计-判定总线与反馈环一等化.md", "site/docs/71-四图对照与解耦设计.md"),
)

# Local caches that must never appear inside the repository tree.
CACHE_GLOBS = (
    "research_agent/vendor/astradraw/.local/runs/*/edge-profile*",
    "research_agent/vendor/astradraw/.local/runs/*/edge-profile*/*",
)

LARGE_DIR_BYTES = 200 * 1024 * 1024

SKIP_DIRS = {
    ".git",
    ".verify",
    ".workbuddy",
    ".claude",
    ".qoder",
    ".zcode",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "runtime_data",
    "Wellspring-Agent",
    "math-rsi-main",
    "FlashRSI-main",
    "IdeaScientist-main",
    "TTME-main",
    "SciForge-OSS-master",
    "harness2-main",
    "cortex-agent",
    "agent-reliability-survey",
    "claude-code-main",
    "template_refs",
    "oss",
    "figures",
    "trees",
    "research",
    "research-project",
    "papers",
    "single-loop",
    "manuscript",
    "apps",
}


def _text_digest(path):
    """Digest a text file with line endings normalised.

    The copies are byte copies at build time, but a git checkout may materialise one side
    with CRLF and the other with LF, which used to read as real drift on Linux CI. Comparing
    normalised text keeps the check about content, not about checkout conversion.
    """
    try:
        with open(str(path), "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return hashlib.sha256(data).hexdigest()
    return hashlib.sha256(text.replace(chr(13) + chr(10), chr(10)).encode("utf-8")).hexdigest()


def _sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _walk(root, skip):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            yield os.path.join(dirpath, name)


def _release_owned(root, relative):
    """A release bundle may own a file that is a copy source in the source repository.

    README.md is release-owned in Wellspring-Agent while site/docs/README.md is a copy of the
    source README; the bundle's own hygiene check must not report that intentional difference
    as drift. The manifest marks release-owned files explicitly, so read it instead of hard-coding.
    """
    manifest = os.path.join(root, "MANIFEST.txt")
    if not os.path.isfile(manifest):
        return False
    with open(manifest, "r", encoding="utf-8", errors="ignore") as handle:
        text = handle.read()
    marker = "# release-owned files and media"
    if marker not in text:
        return False
    for line in text.split(marker, 1)[1].splitlines():
        row = line.strip()
        if row and row.split(chr(9))[0].strip() == relative:
            return True
    return False


def check_site_copies(root):
    blockers = []
    for source, target in SITE_COPIES:
        source_path = os.path.join(root, source)
        target_path = os.path.join(root, target)
        if not os.path.isfile(source_path):
            if _release_owned(root, source):
                continue
            blockers.append({"kind": "site_source_missing", "path": source})
            continue
        if not os.path.isfile(target_path):
            blockers.append({"kind": "site_copy_missing", "path": target, "source": source})
            continue
        if source == "README.md" and _release_owned(root, source):
            continue
        left = _text_digest(source_path)
        right = _text_digest(target_path)
        if left is None or right is None or left != right:
            blockers.append({"kind": "site_copy_drift", "path": target, "source": source})
    return blockers


def check_caches(root):
    import glob

    found = []
    for pattern in CACHE_GLOBS:
        for path in glob.glob(os.path.join(root, pattern)):
            found.append(os.path.relpath(path, root).replace(os.sep, "/"))
    blockers = [
        {"kind": "local_cache_in_tree", "path": path}
        for path in sorted(set(found))
    ]
    return blockers


def _dir_size(path):
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


# Reference clones and local run data are expected to be large; they never ship.
LOCAL_ONLY_TOP = {
    "math-rsi-main",
    "FlashRSI-main",
    "IdeaScientist-main",
    "TTME-main",
    "SciForge-OSS-master",
    "harness2-main",
    "cortex-agent",
    "agent-reliability-survey",
    "claude-code-main",
    "template_refs",
    "oss",
    "runtime_data",
    "Wellspring-Agent",
    "manuscript",
    "research",
    "research-project",
    "papers",
    "docs",
    "apps",
}


def check_large_dirs(root, bytes_threshold=LARGE_DIR_BYTES):
    warnings = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return warnings
    for name in names:
        path = os.path.join(root, name)
        if not os.path.isdir(path) or name in (".git",) or name in LOCAL_ONLY_TOP:
            continue
        size = _dir_size(path)
        if size >= bytes_threshold:
            warnings.append(
                {"kind": "large_dir", "path": name, "mb": round(size / (1024.0 * 1024.0), 1)}
            )
    return warnings


def check_workflow_paths(root):
    """Path filters in .github/workflows that name a literal file nobody produces."""
    blockers = []
    workflows = os.path.join(root, ".github", "workflows")
    if not os.path.isdir(workflows):
        return blockers
    for name in sorted(os.listdir(workflows)):
        if not name.endswith((".yml", ".yaml")):
            continue
        path = os.path.join(workflows, name)
        in_paths = False
        paths_indent = 0
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                indent = len(line) - len(line.lstrip())
                if stripped.startswith("paths:"):
                    in_paths = True
                    paths_indent = indent
                    continue
                if in_paths and stripped.startswith("-"):
                    if indent <= paths_indent:
                        in_paths = False
                    else:
                        entry = stripped[1:].strip().strip("\"'")
                        if entry and "*" not in entry and "?" not in entry and not entry.startswith("!"):
                            if not os.path.exists(os.path.join(root, entry)):
                                blockers.append(
                                    {
                                        "kind": "workflow_path_missing",
                                        "workflow": ".github/workflows/" + name,
                                        "line": number,
                                        "path": entry,
                                    }
                                )
                        continue
                if in_paths and indent <= paths_indent:
                    in_paths = False
    return blockers


def check_duplicate_sources(root):
    """Duplicate hand-written md/py outside generated trees (report only)."""
    skip = set(SKIP_DIRS) | {"site", "demo", "docs", "deploy", "plugin", "integrations", "vendor"}
    groups = {}
    for path in _walk(root, skip):
        if not path.endswith((".md", ".py")):
            continue
        try:
            if os.path.getsize(path) > 1_500_000:
                continue
            digest = _sha256(path)
        except OSError:
            continue
        groups.setdefault(digest, []).append(os.path.relpath(path, root).replace(os.sep, "/"))
    duplicates = [sorted(items) for items in groups.values() if len(items) > 1]
    return [
        {"kind": "duplicate_source", "files": items}
        for items in sorted(duplicates, key=lambda items: items[0])
    ]


def check_hygiene(root=ROOT):
    blockers = []
    blockers.extend(check_site_copies(root))
    blockers.extend(check_caches(root))
    blockers.extend(check_workflow_paths(root))
    warnings = check_large_dirs(root)
    warnings.extend(check_duplicate_sources(root))
    return {
        "schema": "repo-hygiene-0.1",
        "root": root,
        "status": "blocked" if blockers else "ok",
        "blockers": blockers,
        "warnings": warnings,
        "boundary": "read-only hygiene check; it does not rewrite, delete or regenerate anything",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="repository hygiene check (read-only)")
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failure")
    args = parser.parse_args(argv)

    report = check_hygiene(os.path.abspath(args.root))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("repo hygiene: {0}".format(report["status"]))
        for item in report["blockers"]:
            print("  BLOCK {0}: {1}".format(item.get("kind"), item.get("path") or item.get("workflow")))
        for item in report["warnings"]:
            if item.get("kind") == "large_dir":
                print("  warn  large_dir: {0} ({1} MB)".format(item["path"], item["mb"]))
            else:
                print("  warn  {0}: {1}".format(item.get("kind"), item.get("files")))
    if report["blockers"]:
        return 1
    if args.strict and report["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
