"""Generate the distributable folder from the repository root.

The release folder is a build product, not a second source of truth: hand edits to it are
invisible drift, and drift is what this project spends its days hunting.  So the copy is
scripted, and the manifest it writes is what the integrity test verifies.

Usage:
    python scripts/build_release.py            # sync Wellspring-Agent from the repo root
    python scripts/build_release.py --check    # report drift, write nothing
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST_NAME = "Wellspring-Agent"

SYNC_FILES = (
    "pyproject.toml",
    "requirements-runtime.txt",
    "requirements-dev.txt",
    ".gitignore",
    ".dockerignore",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "apps/web/tsconfig.json",
    "apps/web/vite.config.ts",
    "apps/web/index.html",
    "apps/web/playwright.config.ts",
    "apps/web/README.md",
    "apps/web/.gitignore",
)
# The web app cannot be built from src/ alone, and CI is what proves the bundle is a repo
# rather than a folder of source files; both used to sit in the copy untracked and unverified.
SYNC_DIRS = (
    "research_agent",
    "harness2-main",
    "modules",
    "tests",
    "scripts",
    "integrations",
    "site",
    "apps/web/src",
    "apps/web/public",
    "apps/web/tests",
    "trees",
    "papers",
    "single-loop",
    "deploy",
    "plugin",
    ".github",
)
# Written for readers of the bundle, not copied from the working tree. The builder refuses
# to delete them and the integrity test requires every one of them to exist.
RELEASE_OWNED = (
    "README.md",
    "SECURITY.md",
    "LICENSING.md",
    "CONTRIBUTING.md",
    "DISTRIBUTION.md",
    ".mcp.json.example",
)
# Root documents copied only when they exist here; release-only documents (README,
# DISTRIBUTION, LICENSING, ...) are owned by the release folder and left untouched.
SYNC_DOCS = (
    "apps/web/index.html",
    "PRODUCTION-READINESS.md",
    "ARCHITECTURE.md",
    "AGENTS.md",
    "QUICKSTART.md",
    "THIRD_PARTY_NOTICES.md",
)
# The owner's design archive ships as text source so the upload folder is self-contained.
# Binary media (figures/, docs/ audit screenshots, PDF/DOCX) stays out: the bundle is kept
# source-sized by the integrity test's 40 MB cap, and media is not source.
SYNC_DOCS = SYNC_DOCS + tuple(sorted(p.name for p in ROOT.glob("[0-9][0-9]-*.md")))
SYNC_DOCS = SYNC_DOCS + tuple(sorted(p.name for p in ROOT.glob("组会汇报-*.md")))
SYNC_DOCS = SYNC_DOCS + ("1110讨论.html",)
SKIP_NAMES = {"__pycache__", "node_modules", "dist", "test-results", ".pytest_cache", ".ruff_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
# Run data lives inside the package directory.  It is local experiment output, not source,
# and shipping it would publish the owner's research history.
DENY = (
    # Pages deployment belongs to the showcase repository; the bundle repo is the
    # product itself and should not run a second site deploy on push.
    ".github/workflows/pages.yml",
    ".github/workflows/refresh-digest.yml",
    "research_agent/web/data",
    "runtime_data",
    "research_agent/web/data/",
)
# The vendored third-party tool ships 200 MB of its own local state, demo output and media.
# Only the renderer, its components, its references and its examples are needed to run.
VENDOR_KEEP = ("scripts", "components", "references", "examples")
VENDOR_ROOT = "research_agent/vendor/astradraw"
# Harness² is vendored verbatim as the self-evolution engine, so the bundle can run
# `rsi harness2` without a second checkout. Its 6.8 MB of README media is the only trim:
# code, docs, tests and third-party notices all ship.
HARNESS2_ROOT = "harness2-main"
HARNESS2_SKIP = ("assets",)
DOT_ALLOW = {".gitignore", ".gitattributes", ".dockerignore", ".github"}


def _denied(rel: str) -> bool:
    if any(rel == d or rel.startswith(d) for d in DENY):
        return True
    parts = rel.split("/")
    # dot-paths are third-party local state (.local, .cache) unless they are the few
    # version-control files a repository is supposed to ship
    for part in parts:
        if part.startswith(".") and part not in DOT_ALLOW:
            return True
    prefix = HARNESS2_ROOT + "/"
    if rel.startswith(prefix):
        first = rel[len(prefix) :].split("/")[0]
        if first in HARNESS2_SKIP:
            return True
    prefix = VENDOR_ROOT + "/"
    if rel.startswith(prefix):
        first = rel[len(prefix):].split("/")[0]
        if "/" in rel[len(prefix):] and first not in VENDOR_KEEP:
            return True
        if "/" not in rel[len(prefix):] and not rel.endswith((".md", ".txt", ".py")):
            return True
    return False


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required_template_scenes():
    """Scenes the shipped catalog advertises, by id, derived from the code itself.

    Trimming the vendored folder once removed four template scenes that
    figure_workflow.TEMPLATES still names: the bundle then documented figures it could not
    render. Deriving the list from the module keeps the promise and the artifact together.
    """
    try:
        if str(ROOT) not in sys.path:
            # running this file as a script puts scripts/ on sys.path, not the repo root,
            # so an unguarded import here fails silently and ships a trimmed catalog
            sys.path.insert(0, str(ROOT))
        from research_agent import figure_workflow
    except Exception as exc:  # pragma: no cover - surfaced by the release integrity test
        print("warning: cannot read the figure template catalog:", exc, file=sys.stderr)
        return []
    base = Path(str(figure_workflow.VENDOR_ROOT)).resolve()
    try:
        rel_root = base.relative_to(ROOT).as_posix()
    except ValueError:
        return []
    found = []
    for relative in (figure_workflow.TEMPLATES or {}).values():
        path = base / str(relative)
        if path.is_file():
            found.append((rel_root + "/" + str(relative), path))
    return found


def iter_source():
    required = {rel for rel, _ in _required_template_scenes()}
    seen = set()
    for rel in list(SYNC_DIRS) + list(SYNC_FILES) + list(SYNC_DOCS):
        target = ROOT / rel
        if target.is_file():
            if rel not in seen:
                seen.add(rel)
                yield rel, target
        elif target.is_dir():
            for path in sorted(target.rglob("*")):
                if not path.is_file():
                    continue
                if any(part in SKIP_NAMES for part in path.parts) or path.suffix in SKIP_SUFFIXES:
                    continue
                rel = path.relative_to(ROOT).as_posix()
                if _denied(rel) and rel not in required:
                    continue
                if rel not in seen:
                    seen.add(rel)
                    yield rel, path
    for rel, path in _required_template_scenes():
        if rel not in seen:
            seen.add(rel)
            yield rel, path


def build(check_only: bool, prune: bool = False) -> dict:
    """Sync the release bundle, or report drift when check_only. Prints nothing."""
    dest = ROOT / DEST_NAME
    drift = []
    missing = []
    rows = []
    shipped = set()
    for rel, src_path in iter_source():
        out = dest / rel
        digest = sha256_of(src_path)
        rows.append((rel, digest, src_path.stat().st_size))
        shipped.add(rel)
        known = sha256_of(out) if out.is_file() else None
        if known is None:
            missing.append(rel)
        elif known != digest:
            drift.append(rel)
        if not check_only and known != digest:
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(src_path), str(out))

    pruned = []
    if prune and not check_only:
        # a build product must not keep files the build would not produce: hand-copied run
        # data and third-party local state otherwise ship forever
        for rel in list(SYNC_DIRS):
            base = dest / rel
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*"), reverse=True):
                if path.is_file():
                    rel_path = path.relative_to(dest).as_posix()
                    # the build's own file list decides what belongs; re-checking _denied
                    # here deleted the scenes the catalog had just required
                    if rel_path not in shipped:
                        pruned.append(rel_path)
                        path.unlink()
                elif path.is_dir() and not any(path.iterdir()):
                    path.rmdir()

    # files written for readers of the bundle: they are not copies of the working tree, but
    # they must still be accounted for, or "every file in the release is explained" is a lie
    owned_rows = []
    owned_missing = []
    for rel in RELEASE_OWNED:
        out = dest / rel
        if out.is_file():
            owned_rows.append((rel, sha256_of(out), out.stat().st_size))
        else:
            owned_missing.append(rel)

    if not check_only:
        dest.mkdir(parents=True, exist_ok=True)
        sep = chr(9)
        nl = chr(10)
        body = "".join(r + sep + d + sep + str(size) + nl for r, d, size in sorted(rows))
        owned = "".join(r + sep + d + sep + str(size) + nl for r, d, size in sorted(owned_rows))
        with open(str(dest / "MANIFEST.txt"), "w", encoding="utf-8", newline=nl) as handle:
            handle.write("# release manifest: relpath" + sep + "sha256" + sep + "bytes" + nl)
            handle.write("# generated by scripts/build_release.py; do not hand-edit" + nl)
            handle.write(body)
            handle.write("# release-owned files (written for readers, not copied)" + nl)
            handle.write(owned)

    return {
        "mode": "check" if check_only else "sync",
        "files": len(rows),
        "missing_in_release": len(missing),
        "content_drift": len(drift),
        "pruned": len(pruned),
        "release_owned_missing": list(owned_missing),
        "examples_missing": missing[:6],
        "examples_drift": drift[:6],
        "examples_pruned": pruned[:6],
        "boundary": (
            "the release folder is a build product of the repository root; edit the root and "
            "re-run this script, never the copy"
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", dest="check_only", action="store_true",
                        help="report drift without writing")
    parser.add_argument("--prune", action="store_true",
                        help="delete release files the build would not produce")
    args = parser.parse_args(argv)
    report = build(args.check_only, args.prune)
    # printing belongs to the CLI: a test importing build() must stay silent
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if (report["missing_in_release"] or report["content_drift"]) and args.check_only else 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
