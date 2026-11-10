"""Active, validated evolution policy applied by the local runtime.

Activation is deliberately separate from RSI admission: an approved lease is
necessary but not sufficient. The active store re-checks the target, patch,
lease TTL and four evaluation gates, then exposes one bounded policy that the
runtime can consume.

Every consumption also re-reads the source lease. Revoking a lease therefore
propagates to the runtime in the same step, instead of leaving an activated
parameter in force until its TTL. Verification fails closed: a missing or
unreadable ledger cannot keep mutating runs. Promotion stays human-only;
demotion is automatic because it only ever restores the incumbent.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import DEFAULT_EVOLUTION_ACTIVE_PATH, DEFAULT_EVOLUTION_POLICY_PATH
from .rsi import StepLedger
from .storage import JsonStoreError, read_json, write_json_atomic

SCHEMA = "evolution-active-0.1"
SUPPORTED_TARGETS = ("literature.retrieval.budget",)


class ActivePolicyError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_patch(raw: str) -> Dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise ActivePolicyError("candidate patch must be valid JSON")
    if not isinstance(value, dict):
        raise ActivePolicyError("candidate patch must be a JSON object")
    return value


def _validate_budget_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    retriever = str(patch.get("retriever") or "bm25").strip().lower()
    budget = patch.get("max_sources")
    if retriever not in ("bm25", "minilm"):
        raise ActivePolicyError("literature budget retriever must be bm25 or minilm")
    if isinstance(budget, bool) or not isinstance(budget, int) or not 2 <= budget <= 12:
        raise ActivePolicyError("literature budget max_sources must be an integer in 2..12")
    return {"retriever": retriever, "max_sources": budget}


class ActivePolicyStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or DEFAULT_EVOLUTION_ACTIVE_PATH)

    @property
    def boundary(self) -> str:
        return (
            "one bounded process parameter selected by a human-approved RSI lease; "
            "never a Claim, gate decision, rubric, closure or signature"
        )

    def _load(self) -> Dict[str, Any]:
        try:
            data = read_json(self.path)
        except JsonStoreError as exc:
            raise ActivePolicyError(str(exc))
        if data is None:
            return {"schema_version": SCHEMA, "active": None, "history": []}
        if data.get("schema_version") != SCHEMA:
            raise ActivePolicyError("unsupported active evolution policy schema")
        history = data.get("history")
        return {
            "schema_version": SCHEMA,
            "active": data.get("active") if isinstance(data.get("active"), dict) else None,
            "history": [item for item in history if isinstance(item, dict)] if isinstance(history, list) else [],
        }

    def _save(self, data: Dict[str, Any]) -> None:
        data["schema_version"] = SCHEMA
        write_json_atomic(self.path, data)

    @staticmethod
    def _expired(active: Dict[str, Any]) -> bool:
        expires = str(active.get("expires_at") or "")
        return bool(expires and expires < _now()[:10])

    @staticmethod
    def _lease_state(active: Dict[str, Any]) -> str:
        """Re-read the source lease so a revocation reaches the runtime immediately."""
        ledger_path = str(active.get("ledger_path") or "")
        if not ledger_path:
            return "unverifiable"
        try:
            ledger = StepLedger.load(Path(ledger_path))
        except Exception:
            return "unverifiable"
        lease = next(
            (item for item in ledger.leases if item.lease_id == active.get("lease_id")), None
        )
        if lease is None:
            return "missing"
        return lease.effective_status()

    def _settle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Drop an active policy whose lease no longer holds; never add one."""
        active = data.get("active")
        if not active or self._expired(active):
            return data
        state = self._lease_state(active)
        if state in ("active",):
            return data
        reason = "lease %s at re-check (%s)" % (state, active.get("lease_id"))
        data["history"].insert(
            0, dict(active, event="auto_deactivated", reason=reason, at=_now())
        )
        data["history"] = data["history"][:50]
        data["active"] = None
        data["last_auto_deactivation"] = {"reason": reason, "at": _now()}
        self._save(data)
        return data

    def snapshot(self) -> Dict[str, Any]:
        data = self._settle(self._load())
        active = data.get("active")
        effective = active if active and not self._expired(active) else None
        exposed = dict(effective) if effective else None
        if exposed is not None:
            lease_state = self._lease_state(effective)
            exposed.pop("ledger_path", None)
            exposed["lease_state"] = lease_state
        return {
            "schema_version": SCHEMA,
            "active": exposed,
            "expired": bool(active and self._expired(active)),
            "auto_deactivations": len(
                [item for item in data["history"] if item.get("event") == "auto_deactivated"]
            ),
            "history_count": len(data["history"]),
            "boundary": self.boundary,
        }

    def resolve(self, target: str) -> Optional[Dict[str, Any]]:
        active = self.snapshot()["active"]
        if not active or active.get("target") != target:
            return None
        return active

    def activate(
        self,
        ledger_path: Path,
        lease_scope: str,
        human_reason: str,
        allow_simulation: bool = False,
        evolution_policy_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        from .evolution_policy import EvolutionPolicyStore

        if not human_reason.strip():
            raise ActivePolicyError("human_reason is required to activate a policy")
        ledger = StepLedger.load(Path(ledger_path))
        active_leases = [
            lease for lease in ledger.leases
            if lease.effective_status() == "active" and lease.scope == lease_scope
        ]
        if not active_leases:
            raise ActivePolicyError("no active lease for scope: " + lease_scope)
        if len(active_leases) > 1:
            raise ActivePolicyError("conflicting active leases for scope: " + lease_scope)
        lease = active_leases[0]
        episode = next(
            (item for item in ledger.episodes if item.lease_id == lease.lease_id),
            None,
        )
        if episode is None:
            raise ActivePolicyError("active lease has no approved episode")
        if episode.decision != "approved":
            raise ActivePolicyError("episode is not approved")
        if episode.candidate.target not in SUPPORTED_TARGETS:
            raise ActivePolicyError("target is not supported by the runtime: " + episode.candidate.target)
        # The scope registry must govern the target the runtime actually consumes: an
        # unregistered or disabled namespace cannot become an active policy, lease or not.
        EvolutionPolicyStore(
            evolution_policy_path or DEFAULT_EVOLUTION_POLICY_PATH
        ).require_candidate(episode.candidate.kind, episode.candidate.target)
        if episode.simulation and not allow_simulation:
            raise ActivePolicyError("simulated evidence cannot activate a runtime policy")
        for label, evidence in (
            ("public", episode.public_eval),
            ("hidden", episode.hidden_eval),
            ("near_ood", episode.near_ood_eval),
            ("regression", episode.regression_eval),
        ):
            if evidence is None or evidence.status != "passed":
                raise ActivePolicyError("%s evaluation is missing or not passed" % label)
        patch = _parse_patch(episode.candidate.patch)
        if episode.candidate.target == "literature.retrieval.budget":
            patch = _validate_budget_patch(patch)

        data = self._load()
        current = data.get("active")
        if current and not self._expired(current):
            if current.get("lease_id") == lease.lease_id:
                return self.snapshot()
            raise ActivePolicyError(
                "another active policy exists (%s); deactivate it before activation"
                % current.get("policy_id")
            )
        payload = {
            "policy_id": "ACT-" + uuid.uuid4().hex[:10],
            "episode_id": episode.episode_id,
            "candidate_id": episode.candidate.candidate_id,
            "lease_id": lease.lease_id,
            "ledger_path": str(Path(ledger_path).resolve()),
            "scope": lease.scope,
            "target": episode.candidate.target,
            "patch": patch,
            "human_reason": human_reason.strip(),
            "activated_at": _now(),
            "expires_at": lease.expires_on(),
            "source_eval": {
                "public": episode.public_eval.metrics,
                "hidden": episode.hidden_eval.metrics,
                "near_ood": episode.near_ood_eval.metrics,
                "regression": episode.regression_eval.metrics,
                "simulation": episode.simulation,
            },
            "boundary": self.boundary,
        }
        data["active"] = payload
        data["history"].insert(0, dict(payload, event="activated"))
        data["history"] = data["history"][:50]
        self._save(data)
        return self.snapshot()

    def deactivate(self, reason: str) -> Dict[str, Any]:
        if not reason.strip():
            raise ActivePolicyError("deactivation reason is required")
        data = self._load()
        active = data.get("active")
        if active:
            data["history"].insert(0, dict(active, event="deactivated", reason=reason.strip()))
            data["history"] = data["history"][:50]
        data["active"] = None
        self._save(data)
        return self.snapshot()


def active_policy_snapshot(path: Optional[Path] = None) -> Dict[str, Any]:
    return ActivePolicyStore(path).snapshot()
