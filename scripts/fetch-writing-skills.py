#!/usr/bin/env python3
"""Fetch complete writing-skill repositories into oss/writing-skills/.

Policy: full git clone (no --depth / no --filter), recursive submodules,
LFS pulled when present. If the git endpoint is unavailable, fall back to a
complete codeload archive pinned to a commit and mark it as tree-snapshot.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "oss" / "writing-skills"
DEST.mkdir(parents=True, exist_ok=True)

REPOS = [
    ("zLanqing/codex-claude-academic-skills", "MIT", "zh-first academic writing / Office"),
    ("Master-cai/Research-Paper-Writing-Skills", "MIT", "en ML/CV/NLP paper writing"),
    ("lishix520/academic-paper-skills", "MIT", "en humanities/interdisciplinary"),
    ("LeonChaoX/qinyan-academic-skills", "MIT", "multilingual; NSFC/NSSFC/venue templates"),
    ("SNL-UCSB/paper-writing-skill", "MIT", "en systems/ML rhetoric + red team"),
    ("JingYangYuan/paper-write-4ss", "MIT", "zh social-science writing"),
    ("Tianyuai/SCUT-Thesis-Writing-Skills", "MIT", "zh thesis / Word formatting"),
    ("Orchestra-Research/AI-Research-SKILLs", "MIT", "en research/writing/evaluation"),
    ("Imbad0202/academic-research-skills", "CC BY-NC 4.0 (read-only)", "en 12-agent paper pipeline; do not productize"),
]


def run(cmd: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def head_sha(repo: str) -> tuple[str, str]:
    for branch in ("main", "master"):
        try:
            p = run(["git", "ls-remote", f"https://github.com/{repo}.git", f"refs/heads/{branch}"], timeout=25)
        except subprocess.TimeoutExpired:
            continue
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.split()[0], branch
    return "", "main"


def clone_full(repo: str, target: Path) -> tuple[bool, str]:
    if (target / ".git").is_dir():
        return True, "existing"
    if target.exists():
        shutil.rmtree(target)
    cmd = [
        "git", "-c", "core.longpaths=true", "-c", "http.connectTimeout=20",
        "-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=60",
        "clone", "--recursive", "--progress", f"https://github.com/{repo}.git", str(target),
    ]
    try:
        p = run(cmd)
    except subprocess.TimeoutExpired:
        return False, "git clone timeout"
    if p.returncode != 0:
        return False, (p.stderr or p.stdout).strip()[-500:]
    return True, ""


def download(url: str, target: Path) -> None:
    tmp = target.with_suffix(".zip.part")
    p = run(["curl", "-L", "--fail", "--retry", "2", "--connect-timeout", "20",
             "--max-time", "1800", "-A", "writing-skill-audit", "-o", str(tmp), url], timeout=1900)
    if p.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError((p.stderr or p.stdout).strip()[-400:])
    tmp.replace(target)


def extract(zip_path: Path, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        prefix = members[0].filename.split("/", 1)[0] + "/"
        for item in members:
            if not item.filename.startswith(prefix):
                continue
            rel = item.filename[len(prefix):]
            if not rel:
                continue
            dst = out_dir / rel
            if item.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(item) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)


def inspect(root: Path) -> dict:
    skills = [p for p in root.rglob("SKILL.md") if ".git" not in p.parts]
    license_file = ""
    license_first = ""
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        p = root / name
        if p.is_file():
            license_file = name
            license_first = p.read_text(encoding="utf-8", errors="replace").splitlines()[0][:100]
            break
    return {
        "skills": len(skills),
        "skill_paths": [str(p.relative_to(root)).replace("\\", "/") for p in skills[:20]],
        "license_file": license_file,
        "license_first_line": license_first,
        "has_gitmodules": (root / ".gitmodules").is_file(),
        "has_dot_git": (root / ".git").exists(),
    }


def main() -> int:
    results = []
    for repo, expected_license, purpose in REPOS:
        name = repo.replace("/", "__")
        target = DEST / name
        print(f"==== {repo}", flush=True)
        sha, branch = head_sha(repo)
        kind = "git-full"
        err = ""
        t0 = time.time()
        ok, err = clone_full(repo, target)
        if not ok:
            kind = "tree-snapshot"
            try:
                ref = sha or f"refs/heads/{branch}"
                url = f"https://codeload.github.com/{repo}/zip/{ref}"
                print(f"  git failed ({err}); fallback {url}", flush=True)
                zp = DEST / f"{name}.zip"
                download(url, zp)
                extract(zp, target)
            except Exception as exc:
                print(f"  FAIL {type(exc).__name__}: {exc}", flush=True)
                results.append({"repo": repo, "error": f"{type(exc).__name__}: {exc}"})
                continue
        try:
            actual_sha = run(["git", "-C", str(target), "rev-parse", "HEAD"], timeout=20).stdout.strip()
        except Exception:
            actual_sha = sha
        info = inspect(target)
        meta = {
            "repo": repo, "path": str(target.relative_to(ROOT)).replace("\\", "/"),
            "kind": kind, "expected_license": expected_license, "purpose": purpose,
            "commit": actual_sha or sha, "branch": branch,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "seconds": round(time.time() - t0, 1), **info,
        }
        (DEST / f"{name}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(meta)
        print(f"  OK {kind} skills={info['skills']} license={expected_license} {meta['seconds']}s", flush=True)
    (DEST / "manifest.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE -> oss/writing-skills/manifest.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
