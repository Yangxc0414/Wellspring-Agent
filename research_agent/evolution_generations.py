"""Two-track version management for evolution itself.

The platform evolves along two tracks that must be versioned separately and linked:

* **agent** — a harness tree adopted from Harness² (c1..c8). Versioned by the tree hash
  plus the episode ids and evidence statuses that justify it.
* **platform** — this repository's own code. Versioned by ``paths.build_fingerprint()``
  (a content hash of ``research_agent/**/*.py``) plus the commit that carries it.

Why both: a harness admitted on platform A is not automatically valid on platform B.
Recording the platform fingerprint next to the harness generation is what makes
"this improvement was measured on that code" checkable, and what lets a platform change
name the agent generations that now need re-validation.

The store is append-only with a hash-chained event log, mirroring the RSI ledger. It never
applies a patch, never signs, and never revokes a lease by itself: reverting and
re-validating are human actions that the ledger only records.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import REPO_ROOT, RUNTIME_DATA_ROOT, build_fingerprint, build_info
from .storage import read_json, write_json_atomic

SCHEMA = "evolution-generations-0.1"
STORY_SCHEMA = "evolution-story-0.1"
DEFAULT_PATH = RUNTIME_DATA_ROOT / "evolution" / "generations.json"

KINDS = ("agent", "platform")
OPEN_STATUSES = ("proposed", "adopted")
CLOSED_STATUSES = ("adopted", "reverted", "superseded")


class GenerationError(ValueError):
    """The generation ledger cannot accept this record."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return prefix + "-" + uuid.uuid4().hex[:10]


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(ch in "0123456789abcdef" for ch in value.lower())


def sha256_file(path: Any) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


@dataclass
class Generation:
    kind: str
    label: str
    status: str = "proposed"
    generation_id: str = ""
    created_at: str = ""
    parent_id: str = ""
    platform_fingerprint: str = ""
    agent_tree_sha: str = ""
    candidate_ids: List[str] = field(default_factory=list)
    episode_ids: List[str] = field(default_factory=list)
    artifact_ref: str = ""
    artifact_sha256: str = ""
    commit: str = ""
    note: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    closed_at: str = ""

    def __post_init__(self) -> None:
        if not self.generation_id:
            self.generation_id = _id("GEN")
        if not self.created_at:
            self.created_at = _now()
        self.kind = str(self.kind).strip()
        self.label = str(self.label).strip()
        self.status = str(self.status).strip()
        if self.kind not in KINDS:
            raise GenerationError("kind must be one of %s" % (KINDS,))
        if not self.label:
            raise GenerationError("label is required")
        if self.status not in OPEN_STATUSES + CLOSED_STATUSES:
            raise GenerationError("unknown status: " + self.status)
        if self.platform_fingerprint and not _is_hex(self.platform_fingerprint, 16):
            raise GenerationError("platform_fingerprint must be 16 hex characters")
        if self.agent_tree_sha and not _is_hex(self.agent_tree_sha, 64):
            raise GenerationError("agent_tree_sha must be a 64-character sha256")
        if self.artifact_sha256 and not _is_hex(self.artifact_sha256, 64):
            raise GenerationError("artifact_sha256 must be a 64-character sha256")
        if self.parent_id == self.generation_id:
            raise GenerationError("a generation cannot be its own parent")
        self.candidate_ids = [str(item) for item in self.candidate_ids or []]
        self.episode_ids = [str(item) for item in self.episode_ids or []]
        self.evidence = dict(self.evidence or {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "created_at": self.created_at,
            "parent_id": self.parent_id,
            "platform_fingerprint": self.platform_fingerprint,
            "agent_tree_sha": self.agent_tree_sha,
            "candidate_ids": list(self.candidate_ids),
            "episode_ids": list(self.episode_ids),
            "artifact_ref": self.artifact_ref,
            "artifact_sha256": self.artifact_sha256,
            "commit": self.commit,
            "note": self.note,
            "evidence": dict(self.evidence),
            "closed_at": self.closed_at,
        }


class GenerationStore:
    schema_version = SCHEMA

    def __init__(self, path: Optional[Any] = None):
        self.path = Path(path) if path else DEFAULT_PATH
        self.events_path = self.path.with_name(self.path.name + ".events.jsonl")
        self.generations: List[Generation] = []

    # ---------------------------------------------------------------- persistence
    @classmethod
    def load(cls, path: Optional[Any] = None) -> "GenerationStore":
        store = cls(path)
        data = read_json(store.path)
        if data is None:
            return store
        if not isinstance(data, dict) or data.get("schema_version") != cls.schema_version:
            raise GenerationError("unsupported generation ledger schema")
        for raw in data.get("generations", []):
            store.generations.append(Generation(**raw))
        return store

    def save(self) -> None:
        write_json_atomic(
            self.path,
            {
                "schema_version": self.schema_version,
                "generations": [item.to_dict() for item in self.generations],
                "updated_at": _now(),
            },
        )

    def _append_event(self, action: str, generation: Generation) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        previous = ""
        if self.events_path.is_file():
            lines = [
                line
                for line in self.events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if lines:
                try:
                    previous = str(json.loads(lines[-1]).get("entry_hash", ""))
                except ValueError:
                    previous = ""
        entry = {
            "seq": self._event_count() + 1,
            "at": _now(),
            "action": action,
            "generation_id": generation.generation_id,
            "kind": generation.kind,
            "status": generation.status,
            "prev_hash": previous,
        }
        entry["entry_hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        with open(str(self.events_path), "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def _event_count(self) -> int:
        if not self.events_path.is_file():
            return 0
        return sum(
            1 for line in self.events_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )

    def verify_events(self) -> Dict[str, Any]:
        if not self.events_path.is_file():
            return {"ok": True, "count": 0, "errors": []}
        errors: List[str] = []
        previous = ""
        expected = 1
        for number, line in enumerate(
            self.events_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                errors.append("line %d is not JSON" % number)
                continue
            if entry.get("seq") != expected:
                errors.append("line %d seq is not %d" % (number, expected))
            if entry.get("prev_hash") != previous:
                errors.append("line %d prev_hash mismatch" % number)
            payload = {key: value for key, value in entry.items() if key != "entry_hash"}
            if entry.get("entry_hash") != hashlib.sha256(
                json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest():
                errors.append("line %d entry_hash mismatch" % number)
            previous = str(entry.get("entry_hash", ""))
            expected += 1
        return {"ok": not errors, "count": expected - 1, "errors": errors}

    # ---------------------------------------------------------------- queries
    def list(self, kind: str = "") -> List[Generation]:
        return [item for item in self.generations if not kind or item.kind == kind]

    def get(self, generation_id: str) -> Generation:
        for item in self.generations:
            if item.generation_id == generation_id:
                return item
        raise GenerationError("unknown generation: " + str(generation_id))

    def latest(self, kind: str, status: str = "") -> Optional[Generation]:
        for item in reversed(self.list(kind)):
            if not status or item.status == status:
                return item
        return None

    # ---------------------------------------------------------------- mutations
    def open(
        self,
        kind: str,
        label: str,
        status: str = "proposed",
        parent_id: str = "",
        platform_fingerprint: str = "",
        agent_tree_sha: str = "",
        candidate_ids: Optional[List[str]] = None,
        episode_ids: Optional[List[str]] = None,
        artifact_ref: str = "",
        artifact_sha256: str = "",
        commit: str = "",
        note: str = "",
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Generation:
        if status not in OPEN_STATUSES:
            raise GenerationError("open() accepts proposed or adopted, not " + status)
        if kind == "agent" and status == "adopted" and not agent_tree_sha:
            raise GenerationError("an adopted agent generation needs the harness tree sha")
        parent = parent_id
        if not parent:
            previous = self.latest(kind)
            parent = previous.generation_id if previous else ""
        generation = Generation(
            kind=kind,
            label=label,
            status=status,
            parent_id=parent,
            platform_fingerprint=platform_fingerprint or build_fingerprint(),
            agent_tree_sha=agent_tree_sha,
            candidate_ids=candidate_ids or [],
            episode_ids=episode_ids or [],
            artifact_ref=artifact_ref,
            artifact_sha256=artifact_sha256,
            commit=commit,
            note=note,
            evidence=evidence or {},
        )
        self.generations.append(generation)
        self._append_event("open", generation)
        self.save()
        return generation

    def close(
        self, generation_id: str, status: str, note: str = "", commit: str = ""
    ) -> Generation:
        if status not in CLOSED_STATUSES:
            raise GenerationError("close() accepts %s" % (CLOSED_STATUSES,))
        generation = self.get(generation_id)
        if generation.status in CLOSED_STATUSES and generation.status == status:
            raise GenerationError("generation %s is already %s" % (generation_id, status))
        generation.status = status
        generation.closed_at = _now()
        if note:
            generation.note = (generation.note + " | " + note).strip(" |")
        if commit:
            generation.commit = commit
        if status == "superseded":
            newer = self.latest(generation.kind, "adopted")
            if newer is None or newer.generation_id == generation_id:
                raise GenerationError("nothing supersedes %s yet" % generation_id)
        self._append_event("close", generation)
        self.save()
        return generation

    # ---------------------------------------------------------------- projections
    def compare(self, left_id: str, right_id: str) -> Dict[str, Any]:
        left = self.get(left_id)
        right = self.get(right_id)
        if left.kind != right.kind:
            raise GenerationError("compare needs two generations of the same kind")
        if left.kind == "agent":
            same_tree = left.agent_tree_sha == right.agent_tree_sha
            return {
                "kind": "agent",
                "from": left_id,
                "to": right_id,
                "same_tree": same_tree,
                "tree_changed": not same_tree,
                "candidates_delta": len(right.candidate_ids) - len(left.candidate_ids),
                "episodes_delta": len(right.episode_ids) - len(left.episode_ids),
                "platform_same": left.platform_fingerprint == right.platform_fingerprint,
                "status": {"from": left.status, "to": right.status},
            }
        return {
            "kind": "platform",
            "from": left_id,
            "to": right_id,
            "same_fingerprint": left.platform_fingerprint == right.platform_fingerprint,
            "fingerprint": {"from": left.platform_fingerprint, "to": right.platform_fingerprint},
            "commit": {"from": left.commit, "to": right.commit},
            "status": {"from": left.status, "to": right.status},
        }

    def verify(self, current_fingerprint: str = "") -> Dict[str, Any]:
        """Check the chain, the parent links, and the platform/agent coupling."""
        current = current_fingerprint or build_fingerprint()
        errors: List[str] = []
        warnings: List[str] = []
        known = {item.generation_id for item in self.generations}
        for item in self.generations:
            if item.parent_id and item.parent_id not in known:
                errors.append("%s references missing parent %s" % (item.generation_id, item.parent_id))
            if item.kind == "platform" and item.status in ("adopted", "reverted"):
                if not item.commit and not item.note:
                    warnings.append(
                        "%s is %s without a commit or note; the version cannot be reconstructed"
                        % (item.generation_id, item.status)
                    )
        adopted_agents = [item for item in self.list("agent") if item.status == "adopted"]
        for item in adopted_agents:
            if item.platform_fingerprint and item.platform_fingerprint != current:
                warnings.append(
                    "%s was admitted on platform %s, current is %s: re-validate before reusing it"
                    % (item.generation_id, item.platform_fingerprint, current)
                )
        latest_platform = self.latest("platform", "adopted")
        if latest_platform and latest_platform.platform_fingerprint != current:
            warnings.append(
                "platform code changed since %s (%s -> %s); record a new platform generation"
                % (latest_platform.generation_id, latest_platform.platform_fingerprint, current)
            )
        chain = self.verify_events()
        if not chain["ok"]:
            errors.extend(chain["errors"][:5])
        return {
            "ok": not errors,
            "current_fingerprint": current,
            "errors": errors,
            "warnings": warnings,
            "generations": len(self.generations),
            "events": chain["count"],
            "stale_agents": [
                item.generation_id
                for item in adopted_agents
                if item.platform_fingerprint and item.platform_fingerprint != current
            ],
        }

    def story(self, current_fingerprint: str = "") -> Dict[str, Any]:
        current = current_fingerprint or build_fingerprint()
        report = self.verify(current)
        info = build_info()
        tracks = {}
        for kind in KINDS:
            tracks[kind] = [item.to_dict() for item in self.list(kind)]
        latest = {kind: (self.latest(kind).to_dict() if self.latest(kind) else None) for kind in KINDS}
        return {
            "schema": STORY_SCHEMA,
            "generated_at": _now(),
            "current": {
                "fingerprint": current,
                "source_files": info.get("source_files", 0),
                "platform_generation": (latest["platform"] or {}).get("generation_id", ""),
                "agent_generation": (latest["agent"] or {}).get("generation_id", ""),
            },
            "tracks": tracks,
            "latest": latest,
            "verify": report,
            "warnings": report["warnings"],
            "boundary": (
                "a generation records which code and which harness produced which evidence; "
                "it never applies a patch, never signs and never revokes a lease by itself. "
                "The platform fingerprint covers research_agent/**/*.py only, so a SPEC-only "
                "change does not move it."
            ),
        }


def agent_generation_from_run(
    store: GenerationStore,
    payload: Dict[str, Any],
    label: str,
    artifact_path: Any = "",
    episode_ids: Optional[List[str]] = None,
    status: str = "adopted",
    note: str = "",
) -> Generation:
    """Record one Harness² run as an agent generation, linked to the platform it ran on."""
    adopted = payload.get("adopted") or []
    tree_sha = ""
    if adopted:
        tree_sha = str(adopted[0].get("adopted_sha256", "") or "")
    if not tree_sha:
        raise GenerationError("the run has no adopted harness tree; nothing to version")
    budget = payload.get("budget") or {}
    classification = payload.get("classification") or {}
    held = {key: value for key, value in (payload.get("held_out") or {}).items() if key != "artifact_ref"}
    evidence = {
        "budget_identity": budget.get("R") == budget.get("expected_R")
        and budget.get("P") == budget.get("expected_P"),
        "tasks": [
            {"task_id": item.get("task_id", ""), "status": item.get("status", "")}
            for item in payload.get("tasks") or []
        ],
        "held_out": held,
        "simulation": bool(classification.get("simulation")),
        "claim_eligible": bool(classification.get("claim_eligible")),
    }
    metrics = {}
    if (payload.get("run") or {}).get("adapter"):
        metrics["adapter"] = payload["run"]["adapter"]
    # Store a repository-relative reference: the ledger is exported to a public page, and an
    # absolute local path there leaks the machine layout without adding any information.
    reference = str(artifact_path or "")
    if reference:
        try:
            reference = str(Path(reference).resolve().relative_to(REPO_ROOT))
        except (ValueError, OSError):
            reference = Path(reference).name
    generation = store.open(
        kind="agent",
        label=label,
        status=status,
        platform_fingerprint=str(payload.get("platform_fingerprint", "") or build_fingerprint()),
        agent_tree_sha=tree_sha,
        episode_ids=episode_ids or [],
        artifact_ref=reference,
        artifact_sha256=sha256_file(artifact_path) if artifact_path else "",
        note=note,
        evidence=dict(evidence, **{"metrics": metrics}),
    )
    # The same harness tree measured again on a newer platform is a re-validation, not a new
    # improvement: the older record is superseded so the lineage does not show two "current"
    # versions of one tree.
    if status == "adopted":
        for older in store.list("agent"):
            if (
                older.generation_id != generation.generation_id
                and older.status == "adopted"
                and older.agent_tree_sha == tree_sha
            ):
                store.close(
                    older.generation_id,
                    "superseded",
                    note="re-validated on platform %s" % generation.platform_fingerprint,
                )
    return generation


def platform_snapshot(
    store: GenerationStore,
    label: str,
    commit: str = "",
    note: str = "",
    fingerprint: str = "",
) -> Generation:
    """Record the current (or a named) platform state as a generation."""
    value = fingerprint or build_fingerprint()
    latest = store.latest("platform")
    if latest and latest.platform_fingerprint == value and latest.status == "adopted":
        raise GenerationError(
            "platform %s is already recorded as %s" % (value, latest.generation_id)
        )
    generation = store.open(
        kind="platform",
        label=label,
        status="adopted",
        platform_fingerprint=value,
        commit=commit,
        note=note,
    )
    # Supersede only after the new generation exists: close(superseded) refuses to run when
    # nothing newer is adopted yet, which is what keeps the chain honest.
    if latest and latest.status == "adopted":
        store.close(latest.generation_id, "superseded", note="superseded by " + label)
    return generation


def propose_platform_patch(
    store: GenerationStore,
    label: str,
    patch_path: Any,
    note: str = "",
    applies: Optional[bool] = None,
) -> Generation:
    """Record a proposed platform patch. ``applies`` is the result of ``git apply --check``."""
    path = Path(patch_path)
    if not path.is_file():
        raise GenerationError("patch not found: %s" % path)
    evidence = {"applies_cleanly": applies}
    if applies is False:
        evidence["blocked"] = "git apply --check rejected this patch"
    return store.open(
        kind="platform",
        label=label,
        status="proposed",
        artifact_ref=str(path),
        artifact_sha256=sha256_file(path),
        note=note,
        evidence=evidence,
    )


def summarize_lineage(store: GenerationStore, current_fingerprint: str = "") -> Dict[str, Any]:
    """Compact view for a page: latest per track plus the warnings that matter.

    ``artifact_ref`` is dropped here: the page never links it, and a local path in published
    JSON is a leak with no reader.
    """
    story = store.story(current_fingerprint)

    def clean(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [{key: value for key, value in item.items() if key != "artifact_ref"} for item in items]

    return {
        "schema": STORY_SCHEMA,
        "current": story["current"],
        "platform": clean(story["tracks"]["platform"][-5:]),
        "agent": clean(story["tracks"]["agent"][-5:]),
        "warnings": story["warnings"],
        "ok": story["verify"]["ok"],
        "boundary": story["boundary"],
    }
