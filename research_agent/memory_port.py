"""MemoryWritePort: admission strategies in front of every memory write.

71-§4.3 / M2: 「同一批候选在不同准入策略下进不进记忆」需要成为可测对象。四策略：
store_all（现状基线）/ store_none（对照臂）/ replay_then_store（来源可重放才存）/
independent_verify_then_store（带独立验证回执才存）。端口只返回准入决定——写入仍走
guideline_memory.merge/save 单一路径，默认 store_all 与迁移前行为逐字节一致。
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .storage import write_json_atomic

MEMORY_ADMISSION_SCHEMA = "memory-admission-0.1"

STRATEGIES = (
    "store_all",
    "store_none",
    "replay_then_store",
    "independent_verify_then_store",
)

_BOUNDARY = (
    "admission decisions only: the port never writes memory bodies (merge/save keep "
    "single-ownership), produces no evidence qualification (stored entries are "
    "prompt-side advice, never claims), and the default strategy reproduces today's "
    "behavior byte for byte"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_sources(item: Dict[str, Any]) -> List[str]:
    return [str(source) for source in (item.get("sources") or [])]


def _replayable(item: Dict[str, Any], project: Path) -> Tuple[bool, str]:
    sources = _candidate_sources(item)
    if not sources:
        return False, "no sources to replay"
    for source in sources:
        path = (project / source) if not Path(source).is_absolute() else Path(source)
        if not path.is_file():
            return False, "source missing: " + source
        try:
            with open(str(path), "rb") as handle:
                if not handle.read(1):
                    return False, "source empty: " + source
        except OSError as exc:
            return False, "source unreadable: %s (%s)" % (source, exc)
    return True, "all %d source(s) present and readable" % len(sources)


def _independently_verified(item: Dict[str, Any], project: Path) -> Tuple[bool, str]:
    verification = item.get("verification")
    if not isinstance(verification, dict):
        return False, "no verification receipt attached"
    source = str(verification.get("source") or "")
    claimed = str(verification.get("sha256") or "")
    if not source or not claimed:
        return False, "verification receipt missing source or sha256"
    own_sources = set(_candidate_sources(item))
    if source in own_sources:
        return False, "verification source is one of the candidate's own sources (not independent)"
    path = (project / source) if not Path(source).is_absolute() else Path(source)
    if not path.is_file():
        return False, "verification source missing: " + source
    if _sha256(path) != claimed:
        return False, "verification sha256 does not match the file on disk"
    return True, "verification receipt binds a file outside the candidate's own sources"


def _decide(item: Dict[str, Any], strategy: str, project: Path) -> Tuple[str, str]:
    if strategy == "store_all":
        return "admitted", "store_all: baseline strategy"
    if strategy == "store_none":
        return "rejected", "store_none: control arm"
    if strategy == "replay_then_store":
        ok, reason = _replayable(item, project)
        return ("admitted", reason) if ok else ("rejected", reason)
    if strategy == "independent_verify_then_store":
        ok, reason = _independently_verified(item, project)
        return ("admitted", reason) if ok else ("rejected", reason)
    raise ValueError("unknown memory admission strategy: %s; registered: %s" % (strategy, ", ".join(STRATEGIES)))


def admit(proposed: List[Dict[str, Any]], *, strategy: str, project: Path) -> Dict[str, Any]:
    """Decide, per candidate, whether the strategy admits it into memory."""
    root = Path(project).resolve()
    if not root.is_dir():
        raise ValueError("project directory does not exist: %s" % root)
    if strategy not in STRATEGIES:
        raise ValueError("unknown memory admission strategy: %s; registered: %s" % (strategy, ", ".join(STRATEGIES)))
    rows: List[Dict[str, Any]] = []
    admitted: List[Dict[str, Any]] = []
    for item in proposed or []:
        if not isinstance(item, dict):
            rows.append({"text": str(item)[:120], "decision": "rejected", "reason": "candidate is not an object"})
            continue
        decision, reason = _decide(item, strategy, root)
        rows.append({"text": str(item.get("text") or "")[:120], "decision": decision, "reason": reason})
        if decision == "admitted":
            admitted.append(item)
    counts = {"admitted": len(admitted), "rejected": len(rows) - len(admitted), "proposed": len(rows)}
    return {
        "schema_version": MEMORY_ADMISSION_SCHEMA,
        "strategy": strategy,
        "rows": rows,
        "admitted": admitted,
        "counts": counts,
        "boundary": _BOUNDARY,
    }


def write_report(path: Path, report: Dict[str, Any]) -> Dict[str, Any]:
    """Atomically persist an admission report; deterministic content."""
    target = Path(path)
    if target.parent and not target.parent.is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(str(target), report)
    return {"path": str(target), "counts": report.get("counts") or {}}


def load_report(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
