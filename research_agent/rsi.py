from __future__ import annotations

"""Governed RSI control plane.

This is deliberately not an autonomous self-modifying agent. It is the
admission/accounting layer that a future RSI loop must pass through:

    observation -> candidate -> dry-run -> public eval -> hidden eval
    -> EV checks -> human admission -> lease -> monitor/revoke

The module never fabricates metrics and never allows a candidate to change
claims, evidence, gates, rubrics, export or authorship.
"""

import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import atomic_replace
from .paths import build_fingerprint


class RSIPolicyError(ValueError):
    pass


IMMUTABLE_SURFACES = ("claim", "evidence", "gate", "rubric", "export", "signature", "authorship", "closure", "heldout")
ALLOWED_KINDS = ("skill", "process", "prompt", "knowledge")
ALLOWED_DECISIONS = ("pending_human", "approved", "rejected", "no_decision")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return prefix + "-" + uuid.uuid4().hex[:10]


def _evidence_fingerprint(evidence: EvalEvidence) -> str:
    return hashlib.sha256(
        json.dumps(asdict(evidence), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _evidence_digest(evidences: List[Optional[EvalEvidence]]) -> str:
    payload = [
        asdict(evidence) if evidence is not None else None for evidence in evidences
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass
class Candidate:
    kind: str
    target: str
    patch: str
    rationale: str
    predicted_effect: str
    parent_id: str = ""
    scope: str = ""
    candidate_id: str = ""
    predicted_metrics: Dict[str, float] = field(default_factory=dict)
    proposer: str = "human-cli"
    proposer_model: str = ""
    prompt_sha256: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id:
            self.candidate_id = _id("CAND")
        numeric: Dict[str, float] = {}
        for key, value in dict(self.predicted_metrics).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RSIPolicyError("predicted_metrics must be numeric: " + str(key))
            number = float(value)
            if not math.isfinite(number):
                raise RSIPolicyError("predicted_metrics must be finite: " + str(key))
            numeric[str(key)] = number
        self.predicted_metrics = numeric


@dataclass
class EvalEvidence:
    split: str
    status: str
    artifact_ref: str
    metrics: Dict[str, float] = field(default_factory=dict)
    n: int = 0
    note: str = ""
    simulation: bool = False
    claim_eligible: bool = True
    evaluator: str = ""
    artifact_sha256: str = ""
    task_pack_sha256: str = ""
    evaluated_at: str = ""
    code_fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.split not in ("public", "hidden", "near_ood", "regression"):
            raise RSIPolicyError("eval split must be public, hidden, near_ood or regression")
        if self.status not in ("pending", "passed", "failed", "invalid"):
            raise RSIPolicyError("unknown eval status: " + self.status)
        if self.status in ("passed", "failed") and not self.artifact_ref:
            raise RSIPolicyError("a completed eval needs an artifact_ref")
        # Evidence binds the code version that produced it, so a verdict can never be
        # silently reused against a different platform build (D9 verdict binding).
        if not self.code_fingerprint:
            self.code_fingerprint = build_fingerprint()
        for label, value in (
            ("artifact_sha256", self.artifact_sha256),
            ("task_pack_sha256", self.task_pack_sha256),
        ):
            if value and (len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower())):
                raise RSIPolicyError("%s must be a 64-character sha256" % label)


@dataclass
class StepRecord:
    episode_id: str
    candidate: Candidate
    created_at: str
    decision: str = "pending_human"
    reason: str = ""
    public_eval: Optional[EvalEvidence] = None
    hidden_eval: Optional[EvalEvidence] = None
    near_ood_eval: Optional[EvalEvidence] = None
    regression_eval: Optional[EvalEvidence] = None
    dry_run_ref: str = ""
    lease_id: str = ""
    simulation: bool = False
    actuals: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    approved_by: str = ""
    admission_mode: str = "fixture"
    evidence_digest: str = ""
    platform_fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.decision not in ALLOWED_DECISIONS:
            raise RSIPolicyError("unknown decision: " + self.decision)


@dataclass
class Lease:
    candidate_id: str
    scope: str
    ttl_days: int
    created_at: str
    status: str = "active"
    lease_id: str = ""
    revoked_reason: str = ""

    def __post_init__(self) -> None:
        if not self.lease_id:
            self.lease_id = _id("LEASE")
        if self.ttl_days < 1:
            raise RSIPolicyError("ttl_days must be >= 1")
        if self.status not in ("active", "revoked", "expired"):
            raise RSIPolicyError("unknown lease status: " + self.status)

    def expires_on(self) -> str:
        created = date.fromisoformat(self.created_at[:10])
        return (created + timedelta(days=self.ttl_days)).isoformat()

    def effective_status(self, today: Optional[date] = None) -> str:
        if self.status != "active":
            return self.status
        return "expired" if (today or date.today()).isoformat() > self.expires_on() else "active"


class GovernancePolicy:
    @staticmethod
    def check(candidate: Candidate) -> None:
        if candidate.kind not in ALLOWED_KINDS:
            raise RSIPolicyError("kind must be one of %s" % (ALLOWED_KINDS,))
        target = candidate.target.lower()
        for surface in IMMUTABLE_SURFACES:
            if surface in target:
                raise RSIPolicyError("candidate cannot change immutable surface: " + surface)
        if not candidate.patch.strip():
            raise RSIPolicyError("patch must not be empty")
        if not candidate.rationale.strip():
            raise RSIPolicyError("rationale is required")
        if not candidate.predicted_effect.strip():
            raise RSIPolicyError("predicted_effect is required")
        if candidate.parent_id == candidate.candidate_id:
            raise RSIPolicyError("candidate cannot be its own parent")


class StepLedger:
    schema_version = "rsi-0.1"

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self.events_path = (
            self.path.with_name(self.path.name + ".events.jsonl") if self.path else None
        )
        self.episodes: List[StepRecord] = []
        self.leases: List[Lease] = []
        self.confirmations: List[Dict[str, Any]] = []
        self.warnings: List[str] = []

    def _append_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self.events_path is None:
            return
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        previous = ""
        if self.events_path.is_file():
            lines = [
                line for line in self.events_path.read_text(encoding="utf-8").splitlines()
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
            "type": event_type,
            "payload": payload,
            "prev_hash": previous,
        }
        entry["entry_hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        with open(str(self.events_path), "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def _event_count(self) -> int:
        if self.events_path is None or not self.events_path.is_file():
            return 0
        return sum(
            1 for line in self.events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    def verify_events(self) -> Dict[str, Any]:
        if self.events_path is None or not self.events_path.is_file():
            return {"ok": True, "count": 0, "last_hash": "", "errors": []}
        errors: List[str] = []
        previous = ""
        expected_seq = 1
        count = 0
        last_hash = ""
        for line_number, line in enumerate(
            self.events_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                errors.append("line %d is not JSON" % line_number)
                continue
            if entry.get("seq") != expected_seq:
                errors.append("line %d seq is not %d" % (line_number, expected_seq))
            if entry.get("prev_hash") != previous:
                errors.append("line %d prev_hash mismatch" % line_number)
            payload = {key: value for key, value in entry.items() if key != "entry_hash"}
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            if entry.get("entry_hash") != digest:
                errors.append("line %d entry_hash mismatch" % line_number)
            previous = str(entry.get("entry_hash", ""))
            last_hash = previous
            expected_seq += 1
            count += 1
        return {
            "ok": not errors,
            "count": count,
            "last_hash": last_hash,
            "errors": errors,
        }

    def append(self, record: StepRecord) -> StepRecord:
        self.episodes.append(record)
        return record

    def add_lease(self, lease: Lease) -> Lease:
        self.leases.append(lease)
        return lease

    def find(self, episode_id: str) -> StepRecord:
        for record in self.episodes:
            if record.episode_id == episode_id:
                return record
        raise RSIPolicyError("episode not found: " + episode_id)

    def find_lease(self, lease_id: str) -> Lease:
        for lease in self.leases:
            if lease.lease_id == lease_id:
                return lease
        raise RSIPolicyError("lease not found: " + lease_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episodes": [asdict(record) for record in self.episodes],
            "leases": [asdict(lease) for lease in self.leases],
            "confirmations": [dict(item) for item in self.confirmations],
            "warnings": list(self.warnings),
        }

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(str(tmp), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        atomic_replace(tmp, self.path)

    @classmethod
    def load(cls, path: Path) -> "StepLedger":
        ledger = cls(path)
        if not Path(path).is_file():
            return ledger
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("schema_version") != cls.schema_version:
            raise RSIPolicyError("unsupported ledger schema: " + str(data.get("schema_version")))
        for raw in data.get("episodes", []):
            candidate = Candidate(**raw["candidate"])
            public = EvalEvidence(**raw["public_eval"]) if raw.get("public_eval") else None
            hidden = EvalEvidence(**raw["hidden_eval"]) if raw.get("hidden_eval") else None
            record = StepRecord(
                episode_id=raw["episode_id"],
                candidate=candidate,
                created_at=raw["created_at"],
                decision=raw.get("decision", "pending_human"),
                reason=raw.get("reason", ""),
                public_eval=public,
                hidden_eval=hidden,
                near_ood_eval=EvalEvidence(**raw["near_ood_eval"]) if raw.get("near_ood_eval") else None,
                regression_eval=EvalEvidence(**raw["regression_eval"]) if raw.get("regression_eval") else None,
                dry_run_ref=raw.get("dry_run_ref", ""),
                lease_id=raw.get("lease_id", ""),
                simulation=bool(raw.get("simulation", False)),
                actuals=dict(raw.get("actuals", {})),
                notes=list(raw.get("notes", [])),
                approved_by=str(raw.get("approved_by", "")),
                admission_mode=str(raw.get("admission_mode", "fixture")),
                evidence_digest=str(raw.get("evidence_digest", "")),
                platform_fingerprint=str(raw.get("platform_fingerprint", "")),
            )
            ledger.episodes.append(record)
        for raw in data.get("leases", []):
            ledger.leases.append(Lease(**raw))
        ledger.confirmations = [dict(item) for item in data.get("confirmations", [])]
        ledger.warnings = list(data.get("warnings", []))
        return ledger


class RSIController:
    """Control-plane operations; no model calls and no research execution."""

    def __init__(self, ledger: StepLedger):
        self.ledger = ledger

    def propose(
        self,
        candidate: Candidate,
        observation: str = "",
        dry_run_ref: str = "",
        simulation: bool = False,
    ) -> StepRecord:
        chain = self.ledger.verify_events()
        if not chain["ok"]:
            raise RSIPolicyError(
                "RSI event chain is broken; inspect before adding new episodes: "
                + "; ".join(chain["errors"][:3])
            )
        GovernancePolicy.check(candidate)
        record = StepRecord(
            episode_id=_id("EP"),
            candidate=candidate,
            created_at=_now(),
            dry_run_ref=dry_run_ref,
            simulation=simulation,
            notes=[observation] if observation else [],
            platform_fingerprint=build_fingerprint(),
        )
        self.ledger.append(record)
        self.ledger.save()
        self.ledger._append_event(
            "propose",
            {
                "episode_id": record.episode_id,
                "candidate_id": candidate.candidate_id,
                "kind": candidate.kind,
                "target": candidate.target,
                "scope": candidate.scope,
                "proposer": candidate.proposer,
                "simulation": simulation,
                "candidate_version": candidate.version,
                "platform_fingerprint": record.platform_fingerprint,
            },
        )
        return record

    def evaluate(
        self,
        episode_id: str,
        public_eval: EvalEvidence,
        hidden_eval: Optional[EvalEvidence] = None,
        near_ood_eval: Optional[EvalEvidence] = None,
        regression_eval: Optional[EvalEvidence] = None,
    ) -> StepRecord:
        """Attach evaluation receipts while keeping the episode pending for a human.

        Public-only receipts are allowed for a prefilter; admission still requires
        both public and hidden passed evidence in ``admit``.
        """
        record = self.ledger.find(episode_id)
        if record.decision != "pending_human":
            raise RSIPolicyError("only a pending episode can receive evaluation evidence")
        record.public_eval = public_eval
        record.hidden_eval = hidden_eval
        record.near_ood_eval = near_ood_eval
        record.regression_eval = regression_eval
        record.notes.append("evaluation receipts attached; awaiting human admission")
        self.ledger.save()
        self.ledger._append_event(
            "evaluate",
            {
                "episode_id": episode_id,
                "candidate_id": record.candidate.candidate_id,
                "splits": [
                    split for split, evidence in (
                        ("public", public_eval),
                        ("hidden", hidden_eval),
                        ("near_ood", near_ood_eval),
                        ("regression", regression_eval),
                    ) if evidence is not None
                ],
            },
        )
        return record

    def record_actuals(self, episode_id: str, actuals: Dict[str, Any], note: str = "") -> StepRecord:
        if not actuals:
            raise RSIPolicyError("actuals must not be empty")
        record = self.ledger.find(episode_id)
        record.actuals = dict(actuals)
        if note:
            record.notes.append(note)
        self.ledger.save()
        self.ledger._append_event(
            "actuals",
            {
                "episode_id": episode_id,
                "candidate_id": record.candidate.candidate_id,
                "actuals": dict(actuals),
            },
        )
        return record

    def record_confirmation(
        self, episode_id: str, confirmation: Dict[str, Any], note: str = ""
    ) -> Dict[str, Any]:
        """Record a sealed post-lease check.

        A confirmation is never admission input: passing cannot promote anything, and the
        record explicitly forbids ``used_for_admission``. A *failed* check is actionable in
        the one direction that is always safe to automate — it revokes the lease the
        runtime is consuming, so a post-lease regression stops changing runs immediately
        instead of waiting for a human to notice.
        """
        record = self.ledger.find(episode_id)
        if confirmation.get("sealed") is not True:
            raise RSIPolicyError("confirmation must be sealed")
        if confirmation.get("used_for_admission") is not False:
            raise RSIPolicyError("confirmation must not feed admission")
        status = str(confirmation.get("status") or "")
        if status not in ("confirmed", "regressed", "unsupported"):
            raise RSIPolicyError("unrecognized confirmation status: " + status)
        passed = confirmation.get("passed")
        if not isinstance(passed, bool):
            raise RSIPolicyError("confirmation passed must be boolean")
        if status == "confirmed" and not passed:
            raise RSIPolicyError("confirmed status requires passed=true")
        if status == "regressed" and passed:
            raise RSIPolicyError("regressed status requires passed=false")
        if status == "unsupported" and passed:
            raise RSIPolicyError("unsupported confirmation cannot be passed")
        scope = str(confirmation.get("scope", "")).strip()
        leases = [
            lease for lease in self.ledger.leases
            if lease.candidate_id == record.candidate.candidate_id
        ]
        if leases and scope and all(lease.scope != scope for lease in leases):
            raise RSIPolicyError("confirmation scope does not match any lease scope")
        delta = confirmation.get("delta") or {}
        if not isinstance(delta, dict):
            raise RSIPolicyError("confirmation delta must be an object")
        numeric_delta: Dict[str, float] = {}
        for key, value in delta.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RSIPolicyError("confirmation delta must be numeric: " + str(key))
            number = float(value)
            if not math.isfinite(number):
                raise RSIPolicyError("confirmation delta must be finite: " + str(key))
            numeric_delta[str(key)] = number
        digest = hashlib.sha256(
            json.dumps(confirmation, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        for existing in self.ledger.confirmations:
            if existing.get("episode_id") == episode_id and existing.get("artifact_sha256") == digest:
                return existing
        entry = {
            "episode_id": episode_id,
            "candidate_id": record.candidate.candidate_id,
            "status": status,
            "passed": passed,
            "scope": scope,
            "split": str(confirmation.get("split", "")),
            "delta": numeric_delta,
            "artifact_sha256": digest,
            "recorded_at": _now(),
            "note": note,
        }
        self.ledger.confirmations.append(entry)
        self.ledger.save()
        self.ledger._append_event(
            "confirmation",
            {
                "episode_id": episode_id,
                "candidate_id": record.candidate.candidate_id,
                "status": status,
                "artifact_sha256": digest,
            },
        )
        entry["demotion"] = self._demote_on_regression(record, entry) if status == "regressed" else {
            "performed": False,
            "reason": "only a regressed confirmation demotes automatically",
        }
        return entry

    def _demote_on_regression(self, record: StepRecord, confirmation: Dict[str, Any]) -> Dict[str, Any]:
        """Revoke the lease a failed post-lease check invalidated. Demotion only."""
        scope = str(confirmation.get("scope") or "")
        candidates = [
            lease for lease in self.ledger.leases
            if lease.candidate_id == record.candidate.candidate_id and lease.status == "active"
        ]
        if scope:
            candidates = [lease for lease in candidates if lease.scope == scope] or candidates
        if not candidates:
            return {
                "performed": False,
                "reason": "no active lease for this candidate; nothing to demote",
            }
        reason = "auto-revoked after regressed confirmation %s" % confirmation.get("artifact_sha256", "")[:12]
        revoked = [lease.lease_id for lease in candidates]
        for lease in candidates:
            self.revoke(lease.lease_id, reason)
        return {
            "performed": True,
            "lease_ids": revoked,
            "reason": reason,
            "note": (
                "the runtime re-reads the lease on every consumption, so the active policy "
                "stops applying at the next run; promotion still requires a human signature"
            ),
        }

    def admit(
        self,
        episode_id: str,
        public_eval: EvalEvidence,
        hidden_eval: EvalEvidence,
        human_reason: str,
        scope: str,
        ttl_days: int = 90,
        near_ood_eval: Optional[EvalEvidence] = None,
        regression_eval: Optional[EvalEvidence] = None,
        strict: bool = False,
        approved_by: str = "human-cli",
    ) -> StepRecord:
        record = self.ledger.find(episode_id)
        if record.decision != "pending_human":
            raise RSIPolicyError("only a pending episode can be admitted")
        chain = self.ledger.verify_events()
        if not chain["ok"]:
            raise RSIPolicyError(
                "RSI event chain is broken; admission refused: "
                + "; ".join(chain["errors"][:3])
            )
        if public_eval.status != "passed" or hidden_eval.status != "passed":
            raise RSIPolicyError("public and hidden evaluation must both pass")
        if not record.dry_run_ref.strip():
            raise RSIPolicyError("dry-run receipt is required before admission")
        if not human_reason.strip():
            raise RSIPolicyError("human admission reason is required")
        if not approved_by.strip():
            raise RSIPolicyError("approver identity is required")
        if not scope.strip():
            raise RSIPolicyError("lease scope is required")
        evidences = [public_eval, hidden_eval, near_ood_eval, regression_eval]
        if strict:
            if any(evidence is None for evidence in evidences):
                raise RSIPolicyError(
                    "strict admission requires public, hidden, near_ood and regression evidence"
                )
            if any(bool(evidence.simulation) for evidence in evidences if evidence is not None):
                raise RSIPolicyError("strict admission rejects simulated evidence")
            for evidence in evidences:
                if evidence is None:
                    continue
                if not evidence.evaluator.strip():
                    raise RSIPolicyError("strict admission requires an evaluator id")
                if not evidence.artifact_sha256:
                    raise RSIPolicyError("strict admission requires artifact_sha256")
                if not evidence.task_pack_sha256:
                    raise RSIPolicyError("strict admission requires task_pack_sha256")
        for label, existing, attempted in (
            ("public", record.public_eval, public_eval),
            ("hidden", record.hidden_eval, hidden_eval),
            ("near_ood", record.near_ood_eval, near_ood_eval),
            ("regression", record.regression_eval, regression_eval),
        ):
            if (
                existing is not None
                and attempted is not None
                and _evidence_fingerprint(existing) != _evidence_fingerprint(attempted)
            ):
                raise RSIPolicyError(
                    "admission evidence cannot be replaced after evaluation: " + label
                )
        mode = "strict" if strict else (
            "fixture"
            if record.simulation or any(bool(e and e.simulation) for e in evidences)
            else "standard"
        )
        digest = _evidence_digest(evidences)
        lease = Lease(
            candidate_id=record.candidate.candidate_id,
            scope=scope,
            ttl_days=ttl_days,
            created_at=_now(),
        )
        record.public_eval = public_eval
        record.hidden_eval = hidden_eval
        record.near_ood_eval = near_ood_eval
        record.regression_eval = regression_eval
        record.decision = "approved"
        record.reason = human_reason.strip()
        record.lease_id = lease.lease_id
        record.approved_by = approved_by.strip()
        record.admission_mode = mode
        record.evidence_digest = digest
        record.notes.append(
            "human admission recorded; %s lease issued" % mode
        )
        if record.approved_by == record.candidate.proposer:
            record.notes.append(
                "approver and proposer have the same local label; independence is not verified"
            )
        self.ledger.add_lease(lease)
        self.ledger.warnings = [w for w in self.ledger.warnings if "no admission" not in w]
        self.ledger.save()
        self.ledger._append_event(
            "admit",
            {
                "episode_id": episode_id,
                "candidate_id": record.candidate.candidate_id,
                "lease_id": lease.lease_id,
                "scope": scope,
                "mode": mode,
                "approved_by": record.approved_by,
                "evidence_digest": digest,
            },
        )
        return record

    def reject(self, episode_id: str, reason: str) -> StepRecord:
        record = self.ledger.find(episode_id)
        if record.decision != "pending_human":
            raise RSIPolicyError("only a pending episode can be rejected")
        if not reason.strip():
            raise RSIPolicyError("rejection reason is required")
        record.decision = "rejected"
        record.reason = reason.strip()
        self.ledger.save()
        self.ledger._append_event(
            "reject",
            {
                "episode_id": episode_id,
                "candidate_id": record.candidate.candidate_id,
                "reason": record.reason,
            },
        )
        return record

    def revoke(self, lease_id: str, reason: str) -> Lease:
        if not reason.strip():
            raise RSIPolicyError("revocation reason is required")
        chain = self.ledger.verify_events()
        if not chain["ok"]:
            raise RSIPolicyError(
                "RSI event chain is broken; revocation refused: "
                + "; ".join(chain["errors"][:3])
            )
        lease = self.ledger.find_lease(lease_id)
        if lease.status != "active":
            raise RSIPolicyError("only an active lease can be revoked")
        lease.status = "revoked"
        lease.revoked_reason = reason.strip()
        for record in self.ledger.episodes:
            if record.lease_id == lease_id:
                record.notes.append("lease revoked; dependent artifacts require review")
        self.ledger.save()
        self.ledger._append_event(
            "lease_revoke",
            {
                "lease_id": lease_id,
                "candidate_id": lease.candidate_id,
                "reason": lease.revoked_reason,
            },
        )
        return lease

    def archive(self) -> CandidateArchive:
        return CandidateArchive(self.ledger)

    def report(self) -> Dict[str, Any]:
        return MetaTracker().report(self.ledger)


class MetaTracker:
    """Track the RSI process itself: not a proof of capability gain."""

    def report(self, ledger: StepLedger) -> Dict[str, Any]:
        episodes = ledger.episodes
        pending = [e for e in episodes if e.decision == "pending_human"]
        approved = [e for e in episodes if e.decision == "approved"]
        rejected = [e for e in episodes if e.decision == "rejected"]
        active = [l for l in ledger.leases if l.effective_status() == "active"]
        expired = [l for l in ledger.leases if l.effective_status() == "expired"]
        revoked = [l for l in ledger.leases if l.status == "revoked"]
        active_lease_ids = {lease.lease_id for lease in active}
        warnings: List[str] = list(ledger.warnings)
        if pending:
            warnings.append("pending human admission; no lease is active")
        if not any(e.hidden_eval for e in episodes):
            warnings.append("no hidden evaluation recorded; no capability claim is allowed")
        if approved and any(e.hidden_eval is None for e in approved):
            warnings.append("approved episode without hidden evidence; inspect before relying on it")
        if approved and any(e.lease_id not in active_lease_ids for e in approved):
            warnings.append(
                "approved episode without an active lease; capability claim withheld"
            )
        if approved and any(e.near_ood_eval is None for e in approved):
            warnings.append("approved episode without near-OOD evidence; transfer is unproven")
        if approved and any(e.regression_eval is None for e in approved):
            warnings.append("approved episode without regression evidence; forgetting is unmeasured")
        if any(self._simulated(e) for e in approved):
            warnings.append("approved simulated episode; no capability claim is allowed")
        if any(not self._simulated(e) and not self._claimable(e, active_lease_ids) for e in approved):
            warnings.append("approved harness-only episode; no capability claim is allowed")
        if expired:
            warnings.append("expired lease present; it is not applied and cannot be a parent")
        if rejected:
            warnings.append("negative results retained; do not retry without new evidence")
        confirmations = ledger.confirmations
        confirmed_ids = {
            item.get("episode_id") for item in confirmations
            if item.get("status") == "confirmed"
        }
        active_episode_ids = {
            record.episode_id for record in episodes
            if any(lease.candidate_id == record.candidate.candidate_id for lease in active)
        }
        if active_episode_ids - confirmed_ids:
            warnings.append("active lease without recorded confirmation; post-lease check is not tracked")
        if any(item.get("status") == "regressed" for item in confirmations):
            warnings.append("recorded confirmation regressed; human review required")
        tracking = self._tracking(episodes)
        if tracking["status"] == "uncalibrated":
            warnings.append("actuals recorded without numeric predictions; calibration unavailable")
        elif tracking["status"] == "partial":
            warnings.append("numeric prediction coverage is partial; calibration covers a subset")
        return {
            "episodes": len(episodes),
            "pending": len(pending),
            "approved": len(approved),
            "rejected": len(rejected),
            "active_leases": len(active),
            "expired_leases": len(expired),
            "revoked_leases": len(revoked),
            "confirmations": {
                "confirmed": sum(1 for item in confirmations if item.get("status") == "confirmed"),
                "regressed": sum(1 for item in confirmations if item.get("status") == "regressed"),
                "unsupported": sum(1 for item in confirmations if item.get("status") == "unsupported"),
                "records": [dict(item) for item in confirmations],
            },
            "lineage": {e.episode_id: e.candidate.parent_id for e in episodes},
            "archive": CandidateArchive(ledger).summary(),
            "suggested_parents": CandidateArchive(ledger).select_parents(2),
            "warnings": warnings,
            "capability_claims": [
                {
                    "episode_id": e.episode_id,
                    "candidate_id": e.candidate.candidate_id,
                    "public_metrics": e.public_eval.metrics if e.public_eval else {},
                    "hidden_metrics": e.hidden_eval.metrics if e.hidden_eval else {},
                    "near_ood_metrics": e.near_ood_eval.metrics if e.near_ood_eval else {},
                    "regression_metrics": e.regression_eval.metrics if e.regression_eval else {},
                    "n": e.hidden_eval.n if e.hidden_eval else 0,
                    "scope": next((l.scope for l in ledger.leases if l.lease_id == e.lease_id), ""),
                }
                for e in approved if self._claimable(e, active_lease_ids)
            ],
            "next_questions": self._next_questions(pending, rejected, approved),
            "prediction_audit": [
                {
                    "episode_id": e.episode_id,
                    "candidate_id": e.candidate.candidate_id,
                    "decision": e.decision,
                    "predicted": e.candidate.predicted_effect,
                    "actual": e.actuals,
                }
                for e in episodes if e.actuals
            ],
            "tracking": tracking,
            "event_log": ledger.verify_events(),
            "simulation": all(self._simulated(e) for e in episodes) if episodes else False,
        }

    @staticmethod
    def _tracking(episodes: List[StepRecord]) -> Dict[str, Any]:
        with_actuals = [e for e in episodes if e.actuals]
        comparisons: List[Dict[str, Any]] = []
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for record in with_actuals:
            predicted = record.candidate.predicted_metrics
            actual = {
                key: float(value)
                for key, value in record.actuals.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
            shared = sorted(set(predicted) & set(actual))
            if not shared:
                continue
            per_metric: Dict[str, Dict[str, Any]] = {}
            for key in shared:
                error = actual[key] - predicted[key]
                row = {
                    "predicted": predicted[key],
                    "actual": actual[key],
                    "error": round(error, 6),
                    "direction_ok": MetaTracker._same_direction(predicted[key], actual[key]),
                }
                per_metric[key] = row
                buckets.setdefault(key, []).append(row)
            comparisons.append({
                "episode_id": record.episode_id,
                "candidate_id": record.candidate.candidate_id,
                "decision": record.decision,
                "metrics": per_metric,
            })
        metrics: Dict[str, Dict[str, float]] = {}
        for key, rows in sorted(buckets.items()):
            errors = [row["error"] for row in rows]
            metrics[key] = {
                "n": float(len(rows)),
                "mae": round(sum(abs(error) for error in errors) / len(errors), 6),
                "bias": round(sum(errors) / len(errors), 6),
                "direction_agreement": round(
                    sum(1 for row in rows if row["direction_ok"]) / len(rows), 6
                ),
            }
        if not with_actuals:
            status = "no_actuals"
        elif not comparisons:
            status = "uncalibrated"
        elif len(comparisons) < len(with_actuals):
            status = "partial"
        else:
            status = "tracked"
        return {
            "status": status,
            "episodes_with_actuals": len(with_actuals),
            "compared_episodes": len(comparisons),
            "coverage": round(len(comparisons) / len(with_actuals), 6) if with_actuals else 0.0,
            "metrics": metrics,
            "episodes": comparisons,
        }

    @staticmethod
    def _same_direction(predicted: float, actual: float) -> bool:
        if predicted == 0 or actual == 0:
            return predicted == actual
        return (predicted > 0) == (actual > 0)

    @staticmethod
    def _simulated(record: StepRecord) -> bool:
        if record.simulation:
            return True
        evals = (record.public_eval, record.hidden_eval, record.near_ood_eval, record.regression_eval)
        return any(evidence is not None and evidence.simulation for evidence in evals)

    @staticmethod
    def _claimable(record: StepRecord, active_lease_ids: Optional[set] = None) -> bool:
        if MetaTracker._simulated(record):
            return False
        if active_lease_ids is not None and record.lease_id not in active_lease_ids:
            return False
        evals = (record.public_eval, record.hidden_eval, record.near_ood_eval, record.regression_eval)
        present = [evidence for evidence in evals if evidence is not None]
        return bool(present) and all(evidence.claim_eligible for evidence in present)

    @staticmethod
    def _next_questions(pending: List[StepRecord], rejected: List[StepRecord], approved: List[StepRecord]) -> List[str]:
        questions: List[str] = []
        if pending:
            questions.append("待人工准入：补齐 public/hidden 证据、理由与 scope。")
        if rejected:
            questions.append("拒绝项是否形成可复用的负结果，而不是重复尝试？")
        if approved:
            questions.append("下一轮是否能在近域迁移与成本约束下复现该增益？")
        if not questions:
            questions.append("还没有 episode；先记录一个可证伪的改进候选。")
        return questions


def _stage_for_target(target: str) -> str:
    text = (target or "").lower()
    if "literature" in text or "retriev" in text or "query" in text:
        return "S1"
    if "idea" in text or "hypoth" in text:
        return "S2–S3"
    if "experiment" in text or "seed" in text or "protocol" in text:
        return "S5"
    if "paper" in text or "writing" in text:
        return "S8–S12"
    return "META"


def _eval_story(evidence: Optional[EvalEvidence], split: str) -> Dict[str, Any]:
    if evidence is None:
        return {"split": split, "status": "missing", "metrics": {}, "n": 0}
    return {
        "split": split,
        "status": evidence.status,
        "metrics": dict(evidence.metrics),
        "n": evidence.n,
        "simulation": evidence.simulation,
        "claim_eligible": evidence.claim_eligible,
        "note": evidence.note,
    }


def _num(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 6)
    return None


def ledger_story(ledger: StepLedger) -> Dict[str, Any]:
    """Normalize a ledger into a read-only, human-readable audit story.

    This is not a capability evaluation. Rejected candidates and missing gates
    stay visible; a confirmed harness change is not promoted to a claim.
    """
    report = MetaTracker().report(ledger)
    confirmations = {str(item.get("candidate_id")): dict(item) for item in ledger.confirmations}
    leases = {lease.candidate_id: lease for lease in ledger.leases}
    episodes: List[Dict[str, Any]] = []
    for record in ledger.episodes:
        lease = leases.get(record.candidate.candidate_id)
        confirmation = confirmations.get(record.candidate.candidate_id)
        public = _eval_story(record.public_eval, "public")
        hidden = _eval_story(record.hidden_eval, "hidden")
        near = _eval_story(record.near_ood_eval, "near_ood")
        regression = _eval_story(record.regression_eval, "regression")
        gates = [
            {
                "id": "dry-run",
                "label": "Dry-run",
                "state": "passed" if record.dry_run_ref else "missing",
                "detail": record.dry_run_ref or "未记录 dry-run 引用",
            },
            {"id": "public", "label": "Public", "state": public["status"], "metrics": public["metrics"], "detail": public.get("note", "")},
            {"id": "hidden", "label": "Hidden", "state": hidden["status"], "metrics": hidden["metrics"], "detail": hidden.get("note", "")},
            {"id": "near_ood", "label": "Near-OOD", "state": near["status"], "metrics": near["metrics"], "detail": near.get("note", "")},
            {"id": "regression", "label": "Regression", "state": regression["status"], "metrics": regression["metrics"], "detail": regression.get("note", "")},
            {"id": "human", "label": "Human admission", "state": record.decision, "detail": record.reason},
            {
                "id": "lease",
                "label": "Lease",
                "state": lease.effective_status() if lease else "missing",
                "detail": "%s · %s · TTL %s days" % (lease.lease_id, lease.scope, lease.ttl_days) if lease else "未授予",
            },
            {
                "id": "consume",
                "label": "Consume / trace",
                "state": "recorded" if record.actuals else "not_recorded",
                "detail": "actuals: " + json.dumps(record.actuals, ensure_ascii=False) if record.actuals else "尚无消费记录",
            },
            {
                "id": "confirmation",
                "label": "Sealed confirmation",
                "state": str(confirmation.get("status")) if confirmation else "pending",
                "detail": str(confirmation.get("note", "")) if confirmation else "尚未记录租约后复核",
            },
        ]
        episodes.append({
            "episode_id": record.episode_id,
            "candidate_id": record.candidate.candidate_id,
            "kind": record.candidate.kind,
            "target": record.candidate.target,
            "patch": record.candidate.patch,
            "rationale": record.candidate.rationale,
            "predicted_effect": record.candidate.predicted_effect,
            "predicted_metrics": dict(record.candidate.predicted_metrics),
            "scope": record.candidate.scope,
            "parent_id": record.candidate.parent_id,
            "created_at": record.created_at,
            "decision": record.decision,
            "reason": record.reason,
            "simulation": record.simulation,
            "claim_eligible": bool(
                not record.simulation
                and all(
                    evidence.claim_eligible
                    for evidence in (record.public_eval, record.hidden_eval, record.near_ood_eval, record.regression_eval)
                    if evidence is not None
                )
                and any(
                    evidence is not None
                    for evidence in (record.public_eval, record.hidden_eval, record.near_ood_eval, record.regression_eval)
                )
            ),
            "notes": list(record.notes),
            "actuals": dict(record.actuals),
            "public_eval": public,
            "hidden_eval": hidden,
            "near_ood_eval": near,
            "regression_eval": regression,
            "lease": {**asdict(lease), "effective_status": lease.effective_status()} if lease else None,
            "confirmation": confirmation,
            "gates": gates,
            "stage": _stage_for_target(record.candidate.target),
        })

    confirmed = [item for item in episodes if item.get("decision") == "approved" and item.get("confirmation")]
    approved = [item for item in episodes if item.get("decision") == "approved"]
    pending = [item for item in episodes if item.get("decision") == "pending_human"]
    selected = (confirmed or approved or pending or episodes)[0] if episodes else None

    timeline: List[Dict[str, Any]] = []
    if selected:
        gate_states = {gate["id"]: gate for gate in selected["gates"]}
        timeline = [
            {"id": "observe", "label": "观察", "state": "done", "detail": selected["notes"][0] if selected["notes"] else selected["reason"]},
            {"id": "candidate", "label": "候选", "state": "done", "detail": "%s · %s" % (selected["candidate_id"], selected["patch"])},
            {"id": "dry-run", "label": "Dry-run", "state": gate_states["dry-run"]["state"], "detail": gate_states["dry-run"]["detail"]},
            {"id": "public", "label": "Public", "state": gate_states["public"]["state"], "detail": gate_states["public"]["detail"]},
            {"id": "hidden", "label": "Hidden", "state": gate_states["hidden"]["state"], "detail": gate_states["hidden"]["detail"]},
            {"id": "near_ood", "label": "Near-OOD", "state": gate_states["near_ood"]["state"], "detail": gate_states["near_ood"]["detail"]},
            {"id": "regression", "label": "Regression", "state": gate_states["regression"]["state"], "detail": gate_states["regression"]["detail"]},
            {"id": "human", "label": "人工准入", "state": gate_states["human"]["state"], "detail": gate_states["human"]["detail"]},
            {"id": "lease", "label": "租约", "state": gate_states["lease"]["state"], "detail": gate_states["lease"]["detail"]},
            {"id": "consume", "label": "消费 / trace", "state": gate_states["consume"]["state"], "detail": gate_states["consume"]["detail"]},
            {"id": "confirmation", "label": "Sealed 复核", "state": gate_states["confirmation"]["state"], "detail": gate_states["confirmation"]["detail"]},
        ]

    if selected and selected.get("confirmation"):
        delta = selected["confirmation"].get("delta", {})
        headline = "%s 通过 public/hidden/near-OOD/regression，租约 %s 已消费；sealed holdout %s（mean Δ=%s, cost Δ=%s）。仍无 capability claim。" % (
            selected["candidate_id"],
            selected["lease"]["lease_id"] if selected.get("lease") else "—",
            selected["confirmation"].get("status"),
            _num(delta.get("mean_score")) if isinstance(delta, dict) else None,
            _num(delta.get("cost")) if isinstance(delta, dict) else None,
        )
    elif selected:
        headline = "%s：%s；负结果与缺失门禁保留，等待人工或复核。" % (
            selected["candidate_id"], selected["reason"] or selected["decision"],
        )
    else:
        headline = "尚无 RSI episode；先记录一个可证伪的 harness 候选。"

    stages: Dict[str, Dict[str, Any]] = {}
    for item in episodes:
        stage = item["stage"]
        current = stages.get(stage)
        if current is None:
            stages[stage] = {
                "stage": stage,
                "targets": [item["target"]],
                "candidates": [item["candidate_id"]],
                "status": item["decision"],
                "evidence": item["confirmation"]["status"] if item.get("confirmation") else (item.get("hidden_eval", {}).get("status") or item["decision"]),
                "detail": item["patch"],
            }
        else:
            current["targets"].append(item["target"])
            current["candidates"].append(item["candidate_id"])
            current["detail"] = item["patch"]
            if item.get("confirmation"):
                current["status"] = "confirmed"
                current["evidence"] = "sealed confirmation"

    # the ratio is the instrument's own reading, not a score: a round in which the gate never said
    # no has learned nothing, whichever way the proposals went. measured on the only ledger that
    # exists, episodes=1 / rejected=0, which lands in gate_uninformative rather than in "good".
    decided = report["approved"] + report["rejected"]
    rejection_rate = (report["rejected"] / float(decided)) if decided else None
    gate_stops: Dict[str, int] = {}
    # "no stop" is not only passed: an active lease and a human approval are the gate working, and
    # counting them as stops invented failures (measured on an admitted episode: lease:active and
    # human:approved both landed in gate_stops until this list named them)
    clear_states = ("done", "passed", "consumed", "active", "approved", "confirmed")
    for item in episodes:
        for gate in item.get("gates") or []:
            state = str(gate.get("state") or "")
            if state in clear_states:
                continue
            key = "%s:%s" % (gate.get("id") or "?", state or "?")
            gate_stops[key] = gate_stops.get(key, 0) + 1
    if report["episodes"] == 0:
        gate_verdict = "no_episodes"
    elif decided == 0:
        gate_verdict = "awaiting_decisions"
    elif rejection_rate == 0:
        gate_verdict = "gate_uninformative"
    else:
        gate_verdict = "informative"

    # Provenance is recorded per episode but the summary dropped it, so a reader of the headline
    # counts could not tell an exercised loop from an improved one. The house rule already demands
    # that simulated material announce itself; this is that rule applied to the audit projection.
    simulated = sum(1 for item in episodes if item.get("simulation"))
    story_warnings = list(report["warnings"])
    if simulated:
        story_warnings.append(
            "%d of %d episode(s) carry simulation=true: this story reconstructs an exercised loop, "
            "not an improved one, and none of its counts are evidence of a real capability gain"
            % (simulated, len(episodes))
        )

    from .paths import build_info

    return {
        "schema_version": "rsi-story-0.4",
        "generated_at": _now(),
        "source_fingerprint": str(build_info().get("fingerprint") or ""),
        "read_only": True,
        "base": "one ledger: %d episode(s); every count below describes that ledger only, not the "
        "project and not the harness" % report["episodes"],
        "provenance": {
            "simulation_episodes": simulated,
            "episodes": report["episodes"],
            "source": "rsi step ledger",
        },
        "summary": {
            "headline": headline,
            "episodes": report["episodes"],
            "pending": report["pending"],
            "approved": report["approved"],
            "rejected": report["rejected"],
            "active_leases": report["active_leases"],
            "confirmed": report["confirmations"]["confirmed"],
            "regressed": report["confirmations"]["regressed"],
            "capability_claims": len(report["capability_claims"]),
            "calibration": report["tracking"]["status"],
            "decided": decided,
            "rejection_rate": rejection_rate,
            "gate_verdict": gate_verdict,
            "simulation_episodes": simulated,
            "gate_stops": dict(sorted(gate_stops.items(), key=lambda kv: (-kv[1], kv[0]))),
            "rejection_verdict_boundary": (
                "rejection_rate is a statement about the gate and the task set, not about proposal "
                "quality: gate_uninformative means nothing was rejected in this round, which is the "
                "same saturation failure the retrieval probes showed, and it is never reported as "
                "success; awaiting_decisions means the round has not been judged by a human yet"
            ),
        },
        "selected_episode_id": selected["episode_id"] if selected else None,
        "timeline": timeline,
        "episodes": episodes,
        "stage_process": sorted(stages.values(), key=lambda item: item["stage"]),
        "tracking": report["tracking"],
        "warnings": story_warnings,
        "next_questions": report["next_questions"],
        "confirmations": report["confirmations"]["records"],
        "boundary": "Audit reconstruction only: a confirmed harness change is not a capability claim; human admission and claim signatures remain separate.",
    }


def trace_research(
    ledger_path: Path,
    scope: str,
    capsule_path: Path,
    confirmation_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only check that an active lease actually reached a research run.

    This is not a capability test: it verifies linkage and fail-closed scope,
    and it never turns harness evidence into a claim.
    """
    ledger = StepLedger.load(Path(ledger_path))
    active = [
        lease for lease in ledger.leases
        if lease.effective_status() == "active" and lease.scope == scope
    ]
    if not active:
        return {"ok": False, "status": "no_active_lease", "scope": scope, "checks": {}}
    candidates = {lease.candidate_id for lease in active}
    if len(candidates) > 1:
        return {"ok": False, "status": "conflicting_active_leases", "scope": scope, "checks": {}}
    lease = active[0]
    record = next(
        (item for item in ledger.episodes if item.candidate.candidate_id == lease.candidate_id),
        None,
    )
    if record is None:
        return {"ok": False, "status": "lease_without_episode", "scope": scope, "checks": {}}
    capsule = json.loads(Path(capsule_path).read_text(encoding="utf-8"))
    checks: Dict[str, bool] = {
        "capsule_completed": capsule.get("status") == "completed",
        "no_capability_claim": not MetaTracker().report(ledger)["capability_claims"],
    }
    warnings: List[str] = []
    dataset = scope.rsplit("/", 1)[-1]
    if record.candidate.target == "experiment.run.seeds":
        try:
            seeds = json.loads(record.candidate.patch).get("seeds")
        except (TypeError, ValueError):
            seeds = None
        applied = list(capsule.get("seeds") or [])
        checks["seed_budget_applied"] = (
            isinstance(seeds, int) and not isinstance(seeds, bool)
            and applied == list(range(17, 17 + seeds))
        )
        capsule_dataset = str(capsule.get("dataset_id", ""))
        checks["scope_matches_dataset"] = (
            capsule_dataset == dataset or capsule_dataset.startswith(dataset + ":")
        )
        if not checks["seed_budget_applied"]:
            warnings.append("capsule seeds do not match the admitted seed budget")
        if not checks["scope_matches_dataset"]:
            warnings.append("capsule dataset does not match lease scope")
    confirmation: Optional[Dict[str, Any]] = None
    if confirmation_path is not None and Path(confirmation_path).is_file():
        confirmation = json.loads(Path(confirmation_path).read_text(encoding="utf-8"))
        checks["confirmation_sealed"] = confirmation.get("sealed") is True
        checks["confirmation_not_admission"] = confirmation.get("used_for_admission") is False
        checks["confirmation_scope"] = confirmation.get("scope") == scope
        ledger_records = [
            item for item in ledger.confirmations
            if item.get("episode_id") == record.episode_id
        ]
        recorded_hash = (confirmation.get("ledger_confirmation") or {}).get("artifact_sha256")
        if ledger_records:
            checks["confirmation_in_ledger"] = bool(recorded_hash) and any(
                item.get("artifact_sha256") == recorded_hash for item in ledger_records
            )
            if not checks["confirmation_in_ledger"]:
                warnings.append("confirmation file is not linked to a ledger record")
        else:
            warnings.append("confirmation not recorded in ledger; trace uses file only")
        if confirmation.get("status") not in ("confirmed", "regressed", "unsupported"):
            warnings.append("confirmation status is not a recognized sealed outcome")
        if confirmation.get("status") == "regressed":
            warnings.append("sealed confirmation regressed; human review required")
    else:
        warnings.append("no confirmation artifact linked; post-lease check is not traceable")
    ok = all(checks.values())
    return {
        "ok": ok,
        "status": "traceable" if ok else "incomplete",
        "scope": scope,
        "lease": {
            "lease_id": lease.lease_id,
            "candidate_id": lease.candidate_id,
            "episode_id": record.episode_id,
            "target": record.candidate.target,
            "patch": record.candidate.patch,
        },
        "run": {
            "run_id": capsule.get("run_id"),
            "dataset_id": capsule.get("dataset_id"),
            "seeds": capsule.get("seeds"),
            "metric_name": capsule.get("metric_name"),
            "mean": capsule.get("mean"),
        },
        "confirmation": (
            {
                "status": confirmation.get("status"),
                "passed": confirmation.get("passed"),
                "used_for_admission": confirmation.get("used_for_admission"),
            }
            if confirmation is not None
            else None
        ),
        "ledger_confirmations": [
            dict(item) for item in ledger.confirmations
            if item.get("episode_id") == record.episode_id
        ],
        "checks": checks,
        "warnings": warnings,
    }


class CandidateArchive:
    """DGM/RRSI-style archive: keep lineage, rejected candidates and diverse parents."""

    def __init__(self, ledger: StepLedger):
        self.ledger = ledger

    def by_target(self) -> Dict[str, List[StepRecord]]:
        result: Dict[str, List[StepRecord]] = {}
        for record in self.ledger.episodes:
            result.setdefault(record.candidate.target, []).append(record)
        return result

    def summary(self) -> Dict[str, Any]:
        result: Dict[str, Dict[str, int]] = {}
        for target, records in self.by_target().items():
            result[target] = {
                "total": len(records),
                "approved": sum(1 for r in records if r.decision == "approved"),
                "rejected": sum(1 for r in records if r.decision == "rejected"),
                "pending": sum(1 for r in records if r.decision == "pending_human"),
            }
        return result

    def select_parents(self, k: int = 2) -> List[str]:
        """Prefer approved episodes with hidden evidence; keep target diversity."""
        active_candidates = {
            lease.candidate_id for lease in self.ledger.leases
            if lease.effective_status() == "active"
        }
        approved = [
            r for r in self.ledger.episodes
            if r.decision == "approved" and r.hidden_eval and r.candidate.candidate_id in active_candidates
        ]
        if not approved:
            return []

        def score(record: StepRecord) -> float:
            metrics = record.hidden_eval.metrics if record.hidden_eval else {}
            # Lower-is-better diagnostics must not make a cheaper candidate look
            # worse when selecting an incumbent parent.
            excluded = ("cost", "failed", "gap")
            values = [
                float(value) for key, value in metrics.items()
                if not any(token in str(key).lower() for token in excluded)
                and isinstance(value, (int, float)) and not isinstance(value, bool)
            ]
            return sum(values) / len(values) if values else 0.0

        approved.sort(key=lambda r: (score(r), r.created_at), reverse=True)
        selected: List[str] = []
        used_targets = set()
        for record in approved:
            if len(selected) >= k:
                break
            if record.candidate.target not in used_targets:
                selected.append(record.episode_id)
                used_targets.add(record.candidate.target)
        for record in approved:
            if len(selected) >= k:
                break
            if record.episode_id not in selected:
                selected.append(record.episode_id)
        return selected
