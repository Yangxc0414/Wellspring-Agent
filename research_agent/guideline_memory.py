"""Guideline memory: deterministic bookkeeping for run-wide lessons (no weight updates).

Ported mechanics from TTME's Guideline Memory (``ttt/memory/guidelines.py``), with one deliberate
change: TTME accepts a free-text line whose only truth test is a sandbox score, while this project
will not state anything it cannot point at. A guideline must cite artifact paths that exist in the
project, so a lesson fossilising into the next prompt is at least traceable to the failure that
taught it.

Everything here is deterministic. Producing the candidate lines is a model call and belongs to the
host-model turn path, not to this module.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import read_json, write_json_atomic

GUIDELINE_SCHEMA = "guideline-memory-0.1"
GUIDELINE_DELIMITER = " -> "
MAX_ENTRIES = 24
MAX_PROPOSED_PER_STEP = 3
STALE_STEPS = 20
CHAR_BUDGET = 900
DEDUP_OVERLAP = 0.5

GUIDELINE_BOUNDARY = (
    "guidelines are prompt-side advice, not capability: they cannot create or change a Claim, an "
    "assertion, a gate decision or an exported number; each one names the artifacts that taught it, "
    "and an unconfirmed guideline expires rather than staying in the prompt forever"
)

_TOKENS = re.compile(r"[a-z0-9_\u4e00-\u9fff]+")


def parse_entry(text: str) -> Optional[Dict[str, str]]:
    """Parse the one-line ``trigger -> mechanism -> action`` form, or reject it.

    Splitting on the delimiter rather than matching a character class keeps hyphens and dots legal —
    a lesson that names ``from-idea`` or ``study-evidence.json`` is exactly the kind we want.
    A malformed line is dropped instead of stored loosely: the block goes into a prompt, and a
    half-parsed lesson reads like a verified rule to the next model call.
    """
    parts = [part.strip() for part in (text or "").strip().split(GUIDELINE_DELIMITER)]
    if len(parts) != 3 or not all(parts):
        return None
    if any(len(part) > 120 or "\n" in part for part in parts):
        return None
    return {"trigger": parts[0], "mechanism": parts[1], "action": parts[2]}


def _tokens(text: str) -> set:
    return {token for token in _TOKENS.findall(text.lower()) if len(token) > 1}


def overlap(first: str, second: str) -> float:
    left, right = _tokens(first), _tokens(second)
    if not left or not right:
        return 0.0
    return len(left & right) / float(len(left | right))


def _source_ok(source: str, project: Path) -> bool:
    """A citation must resolve inside the project; this is the whole traceability claim."""
    cleaned = (source or "").strip()
    if not cleaned:
        return False
    head = cleaned.split("#", 1)[0]
    if not head:
        return False
    candidate = (project / head).resolve()
    try:
        return candidate.is_relative_to(project.resolve()) and candidate.exists()
    except AttributeError:  # Python 3.8 has no Path.is_relative_to
        return str(candidate).startswith(str(project.resolve())) and candidate.exists()


def load(project: Path) -> List[Dict[str, Any]]:
    path = Path(project) / "memory" / "guidelines.json"
    stored = read_json(path)
    if isinstance(stored, dict):
        entries = stored.get("entries")
        return [item for item in (entries or []) if isinstance(item, dict)]
    return []


def save(project: Path, entries: List[Dict[str, Any]], step: int) -> Path:
    path = Path(project) / "memory" / "guidelines.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        path,
        {
            "schema_version": GUIDELINE_SCHEMA,
            "step": int(step),
            "entries": entries,
            "boundary": GUIDELINE_BOUNDARY,
        },
    )
    return path


def merge(
    entries: List[Dict[str, Any]],
    proposed: List[Dict[str, Any]],
    *,
    step: int,
    project: Path,
) -> Dict[str, Any]:
    """Apply TTME's reaffirm-or-expire rules: repeat evidence strengthens, silence expires.

    ``proposed`` items carry ``text`` and ``sources``. A proposed line that overlaps an existing one
    increments ``seen`` instead of adding a near-duplicate; that is what keeps a short prompt from
    filling up with three phrasings of the same lesson.
    """
    project = Path(project).resolve()
    live = [dict(item) for item in entries]
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for item in (proposed or [])[:MAX_PROPOSED_PER_STEP]:
        if len(proposed) > MAX_PROPOSED_PER_STEP:
            rejected.append({"text": str(item.get("text") or "")[:120], "reason": "over-cap-per-step"})
        text = str(item.get("text") or "")
        parts = parse_entry(text)
        if parts is None:
            rejected.append({"text": text[:120], "reason": "not trigger -> mechanism -> action"})
            continue
        sources = [str(source) for source in (item.get("sources") or [])]
        if not sources or not all(_source_ok(source, project) for source in sources):
            rejected.append({"text": parts["action"][:120], "reason": "sources missing or outside the project"})
            continue
        sentence = " ".join(parts.values())
        twin = next(
            (existing for existing in live if overlap(" ".join(str(v) for k, v in existing.items() if k in ("trigger", "mechanism", "action")), sentence) >= DEDUP_OVERLAP),
            None,
        )
        if twin is not None:
            twin["seen"] = int(twin.get("seen") or 1) + 1
            twin["last_seen_step"] = int(step)
            twin["sources"] = sorted({*(twin.get("sources") or []), *sources})[:8]
            accepted.append({"text": text, "reaffirmed": True})
            continue
        live.append(
            {
                "trigger": parts["trigger"],
                "mechanism": parts["mechanism"],
                "action": parts["action"],
                "seen": 1,
                "first_step": int(step),
                "last_seen_step": int(step),
                "sources": sorted(set(sources))[:8],
            }
        )
        accepted.append({"text": text, "reaffirmed": False})
    live.sort(key=lambda item: (int(item.get("seen") or 0), int(item.get("last_seen_step") or 0)), reverse=True)
    expired = [item for item in live if int(step) - int(item.get("last_seen_step") or step) > STALE_STEPS]
    live = [item for item in live if item not in expired][:MAX_ENTRIES]
    return {
        "entries": live,
        "accepted": accepted,
        "rejected": rejected,
        "expired": [item["action"] for item in expired],
    }


def block_for(project: Path) -> str:
    """The stored lessons as a prompt block; empty string when there is nothing confirmed yet."""
    return render_block(load(Path(project)), step=0)


def render_block(entries: List[Dict[str, Any]], *, step: int) -> str:
    """The prompt block, within a character budget, most-corroborated first."""
    if not entries:
        return ""
    lines = ["## 本 run 已确认的做法（自动记忆，非结论；每条都注明教它的产物）"]
    used = len(lines[0])
    for item in entries:
        line = "- %s -> %s -> %s（%d 次印证，来自 %s）" % (
            item.get("trigger"),
            item.get("mechanism"),
            item.get("action"),
            int(item.get("seen") or 1),
            ", ".join((item.get("sources") or [])[:2]) or "未记产物",
        )
        if used + len(line) > CHAR_BUDGET:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)
