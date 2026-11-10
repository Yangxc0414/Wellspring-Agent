"""Runtime observations that can seed governed evolution proposals.

Observations are not evidence and never enter Claim/EA/Closure. They only
summarize what a task run actually encountered so a human/model can propose a
bounded process change.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import DEFAULT_EVOLUTION_OBSERVATIONS_PATH
from .storage import JsonStoreError, read_json, write_json_atomic

SCHEMA = "evolution-observation-0.1"
MAX_OBSERVATIONS = 500


class ObservationError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EvolutionObservationStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or DEFAULT_EVOLUTION_OBSERVATIONS_PATH)

    @property
    def boundary(self) -> str:
        return "runtime observations only; not evidence, not a capability claim, never enters Claim/EA/Closure"

    def _load(self) -> Dict[str, Any]:
        try:
            data = read_json(self.path)
        except JsonStoreError as exc:
            raise ObservationError(str(exc))
        if data is None:
            return {
                "schema_version": SCHEMA,
                "updated_at": "",
                "observations": [],
            }
        if data.get("schema_version") != SCHEMA:
            raise ObservationError("unsupported evolution observation schema")
        observations = data.get("observations")
        if not isinstance(observations, list):
            raise ObservationError("evolution observations must be a list")
        return {
            "schema_version": SCHEMA,
            "updated_at": str(data.get("updated_at") or ""),
            "observations": [item for item in observations if isinstance(item, dict)],
        }

    def _save(self, data: Dict[str, Any]) -> None:
        data["schema_version"] = SCHEMA
        data["updated_at"] = _now()
        write_json_atomic(self.path, data)

    def record(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(observation, dict):
            raise ObservationError("observation must be an object")
        topic = str(observation.get("topic") or "").strip()
        if not topic:
            raise ObservationError("observation.topic is required")
        data = self._load()
        fingerprint = str(observation.get("fingerprint") or "")
        if not fingerprint:
            fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "topic": topic,
                        "status": observation.get("status"),
                        "stopped_at": observation.get("stopped_at"),
                        "max_sources": observation.get("max_sources"),
                        "packages": observation.get("packages"),
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
        existing = next(
            (item for item in data["observations"] if item.get("fingerprint") == fingerprint),
            None,
        )
        if existing is not None:
            return existing
        item = {
            "observation_id": "OBS-" + uuid.uuid4().hex[:10],
            "fingerprint": fingerprint,
            "created_at": _now(),
            **{
                key: value
                for key, value in observation.items()
                if key not in ("observation_id", "created_at", "fingerprint")
            },
        }
        data["observations"].insert(0, item)
        del data["observations"][MAX_OBSERVATIONS:]
        self._save(data)
        return item

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), MAX_OBSERVATIONS))
        return list(self._load()["observations"][:limit])

    def summary(self) -> Dict[str, Any]:
        data = self._load()
        observations = data["observations"]
        by_status: Dict[str, int] = {}
        by_q0: Dict[str, int] = {}
        fixture = 0
        for item in observations:
            status = str(item.get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
            q0 = str(item.get("q0_status") or "unknown")
            by_q0[q0] = by_q0.get(q0, 0) + 1
            if item.get("fixture_mode"):
                fixture += 1
        return {
            "schema_version": SCHEMA,
            "count": len(observations),
            "fixture_count": fixture,
            "by_status": by_status,
            "by_q0": by_q0,
            "updated_at": data.get("updated_at", ""),
            "recent": observations[:10],
            "boundary": self.boundary,
        }

    def suggest_budget(self) -> Dict[str, Any]:
        """Suggest a lower retrieval budget only when coverage is already healthy."""
        observations = [
            item for item in self._load()["observations"]
            if not item.get("fixture_mode") and item.get("q0_status") == "pass"
        ]
        budgets = [
            int(item["max_sources"])
            for item in observations
            if isinstance(item.get("max_sources"), int) and item["max_sources"] >= 4
        ]
        if len(budgets) < 2:
            return {
                "status": "insufficient_observations",
                "reason": "need at least two non-fixture Q0-pass observations with max_sources >= 4",
                "observations": len(observations),
                "boundary": self.boundary,
            }
        budgets.sort()
        current = budgets[len(budgets) // 2]
        proposed = max(2, current - 2)
        return {
            "status": "suggested",
            "candidate": {
                "candidate_id": "OBS-CAND-" + uuid.uuid4().hex[:8],
                "kind": "process",
                "target": "literature.retrieval.budget",
                "patch": {"retriever": "bm25", "max_sources": proposed},
                "rationale": "runtime observations already passed Q0 with max_sources=%d; test a cheaper budget" % current,
                "predicted_effect": "same coverage with fewer retrieval sources: %d -> %d" % (current, proposed),
                "observation_count": len(budgets),
                "predicted_metrics": {"max_sources": proposed},
            },
            "boundary": self.boundary,
            "next": "evaluate with `python -m research_agent rsi real-trial --candidate-file <file>`; admission remains human-only",
        }
