#!/usr/bin/env bash
# Full clones for research-framework comparison.
# - full history (no --depth / no --filter)
# - recursive submodules
# - Git LFS objects pulled
# - keeps .git; does not modify upstream content
# Run from repo root: bash scripts/clone-research-repos.sh
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/oss/full"
LOG="$DEST/clone.log"
mkdir -p "$DEST"
: > "$LOG"

repos=(
  "HICAI-ZJU/SciToolAgent"
  "ResearAI/DeepScientist"
  "zhu-minjun/Researcher"
  "SakanaAI/AI-Scientist-v3"
  "HKUDS/AI-Researcher"
  "assafelovic/gpt-researcher"
  "InternScience/InternAgent"
  "SamuelSchmidgall/AgentLaboratory"
  "snap-stanford/Biomni"
  "aiming-lab/AutoResearchClaw"
  "wanshuiyin/Auto-claude-code-research-in-sleep"
  "EvoMap/AutoResearch"
  "Gen-Verse/RSI-Anything"
  "OpenRSI-Foundation/OpenRSI-Index"
  "DAIR-AutoResearch/AutoSci"
)

echo "clone_start $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
for repo in "${repos[@]}"; do
  name="${repo//\//__}"
  target="$DEST/$name"
  echo "==== $repo -> $target" | tee -a "$LOG"
  if [ -d "$target/.git" ]; then
    echo "SKIP existing .git: $repo" | tee -a "$LOG"
  else
    GIT_LFS_SKIP_SMUDGE=0 git -c core.longpaths=true \
      -c http.connectTimeout=20 -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=60 \
      clone --recursive --progress \
      "https://github.com/$repo.git" "$target" >> "$LOG" 2>&1
    rc=$?
    echo "clone_rc=$rc $repo" | tee -a "$LOG"
    if [ $rc -ne 0 ]; then
      echo "CLONE_FAILED $repo (partial dir may remain; inspect before retry)" | tee -a "$LOG"
      continue
    fi
  fi
  if [ -d "$target/.git" ]; then
    (cd "$target" && git -c core.longpaths=true submodule update --init --recursive) >> "$LOG" 2>&1
    (cd "$target" && git lfs pull) >> "$LOG" 2>&1
    commit=$(cd "$target" && git rev-parse HEAD 2>/dev/null || echo "?")
    branch=$(cd "$target" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
    size=$(du -sh "$target" 2>/dev/null | awk '{print $1}')
    lfs_count=$(cd "$target" && git lfs ls-files 2>/dev/null | wc -l | tr -d ' ')
    sub_count=$(cd "$target" && git submodule status 2>/dev/null | wc -l | tr -d ' ')
    echo "DONE $repo commit=$commit branch=$branch size=$size lfs=$lfs_count submodules=$sub_count" | tee -a "$LOG"
  fi
done
echo "clone_end $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
echo "All done. Log: $LOG"
