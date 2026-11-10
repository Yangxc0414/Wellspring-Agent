#!/usr/bin/env python3
"""Fetch complete GitHub working-tree archives (no .git) by commit SHA.

Used when the git pack endpoint is too slow for very large repositories.
The archive is tied to an exact commit via codeload.github.com/<repo>/zip/<sha>.
This is a tree snapshot, NOT a full clone: it has no history and may omit
submodule contents / LFS blobs. Recorded as such in oss/full/CLONES.md.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "oss" / "full" / "_zip"
DEST.mkdir(parents=True, exist_ok=True)

REPOS = [
    "assafelovic/gpt-researcher",
    "InternScience/InternAgent",
    "SamuelSchmidgall/AgentLaboratory",
    "snap-stanford/Biomni",
    "aiming-lab/AutoResearchClaw",
    "wanshuiyin/Auto-claude-code-research-in-sleep",
    "EvoMap/AutoResearch",
    "Gen-Verse/RSI-Anything",
    "OpenRSI-Foundation/OpenRSI-Index",
    "DAIR-AutoResearch/AutoSci",
    # 762 MB upstream history; archive download is slow. Fetch it last so the
    # other ten are not blocked, and mark it pending if it does not finish.
    "HKUDS/AI-Researcher",
]


def head_sha(repo: str) -> tuple[str, str]:
    for branch in ("main", "master"):
        try:
            proc = subprocess.run(
                ["git", "ls-remote", f"https://github.com/{repo}.git", f"refs/heads/{branch}"],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            continue
        line = proc.stdout.strip().splitlines()
        if proc.returncode == 0 and line:
            return line[0].split()[0], branch
    return "", "main"


def download(url: str, target: Path) -> None:
    tmp = target.with_suffix(".zip.part")
    proc = subprocess.run(
        [
            "curl", "-L", "--fail", "--retry", "2", "--connect-timeout", "20",
            "--max-time", "1800", "-A", "research-agent-repo-audit", "-o", str(tmp), url,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"curl rc={proc.returncode}: {proc.stderr.strip()[-400:]}")
    tmp.replace(target)


def extract(zip_path: Path, out_dir: Path) -> int:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        prefix = members[0].filename.split("/", 1)[0] + "/"
        for item in members:
            name = item.filename
            if not name.startswith(prefix):
                continue
            rel = name[len(prefix):]
            if not rel:
                continue
            target = out_dir / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(item) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count


def inspect(out_dir: Path) -> dict:
    license_file = ""
    first_line = ""
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md"):
        p = out_dir / name
        if p.is_file():
            license_file = name
            first_line = p.read_text(encoding="utf-8", errors="replace").splitlines()[0][:120]
            break
    gitmodules = (out_dir / ".gitmodules").is_file()
    lfs = False
    attrs = out_dir / ".gitattributes"
    if attrs.is_file():
        lfs = "filter=lfs" in attrs.read_text(encoding="utf-8", errors="replace")
    return {
        "license_file": license_file,
        "license_first_line": first_line,
        "has_gitmodules": gitmodules,
        "has_lfs_attributes": lfs,
        "has_dot_git": (out_dir / ".git").exists(),
    }


def main() -> int:
    results = []
    for repo in REPOS:
        name = repo.replace("/", "__")
        zip_path = DEST / f"{name}.zip"
        out_dir = DEST / name
        print(f"==== {repo}", flush=True)
        try:
            sha, branch = head_sha(repo)
            ref = sha or f"refs/heads/{branch}"
            url = f"https://codeload.github.com/{repo}/zip/{ref}"
            print(f"  {branch} {sha[:12] or 'HEAD'} -> {url}", flush=True)
            t0 = time.time()
            if not zip_path.exists():
                download(url, zip_path)
            size = zip_path.stat().st_size
            files = extract(zip_path, out_dir)
            meta = {
                "repo": repo,
                "commit": sha,
                "branch": branch,
                "archive_url": url,
                "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "zip_bytes": size,
                "files": files,
                "snapshot_type": "tree-snapshot (no .git)",
                **inspect(out_dir),
            }
            (DEST / f"{name}.meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            results.append(meta)
            print(f"  OK {files} files, {size/1048576:.1f} MB zip, {time.time()-t0:.1f}s", flush=True)
        except Exception as exc:
            print(f"  FAIL {type(exc).__name__}: {exc}", flush=True)
            results.append({"repo": repo, "error": f"{type(exc).__name__}: {exc}"})
    (DEST / "archives.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("DONE -> oss/full/_zip/archives.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
