"""FeedbackPort: the pluggable seam where a verdict changes the next action.

71-§4.2: every loop follows observe -> propose -> gate -> apply -> record, and
the gate defaults to reject — a loop that wants to mutate anything gated stays
a proposal until its scope is explicitly registered.  V1 ships one loop,
``lineage_reverify``: it re-derives the lineage impact straight from the
artifacts (read-only) and records the receipt, which is the 回指 side of
feedback loop B (溯源/失效传播) in the strategy figure.  With no loops enabled
the port writes nothing anywhere, so 关闭全部环 = 与今日行为逐字节一致.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .storage import write_json_atomic

FEEDBACK_SCHEMA = "feedback-ledger-0.1"

_BOUNDARY = (
    "pluggable feedback loops; the gate defaults to reject, so v1 applies only "
    "read-only re-verification and records the receipt; disabled by default — "
    "with no loops enabled nothing is written and no projection changes"
)

# (loop_id) -> {"observe": fn(project, limit) -> [observation],
#               "propose": fn(observation) -> [proposal],
#               "gate": fn(proposal) -> decision,
#               "apply": fn(proposal, observation, project) -> effect}
_LOOPS: Dict[str, Dict[str, Callable[..., Any]]] = {}


def register_loop(loop_id: str, observe: Callable[..., Any], propose: Callable[..., Any],
                  gate: Callable[..., Any], apply: Callable[..., Any]) -> None:
    if loop_id in _LOOPS:
        raise ValueError("feedback loop already registered: " + loop_id)
    _LOOPS[loop_id] = {
        "observe": observe,
        "propose": propose,
        "gate": gate,
        "apply": apply,
    }


def registered_loops() -> List[str]:
    return sorted(_LOOPS)


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _observe_lineage_reverify(project: Path, limit: int = 50) -> List[Dict[str, Any]]:
    from .lineage import LineageAgent, LineageError

    root = Path(project).resolve()
    observations: List[Dict[str, Any]] = []
    runs_dir = root / "runs"
    if not runs_dir.is_dir():
        return observations
    for run in sorted(runs_dir.glob("RUN-*"))[-max(1, min(int(limit), 200)):]:
        if not run.is_dir():
            continue
        manifest = run / "lineage" / "lineage.json"
        if not manifest.is_file():
            continue
        subject = "runs/" + run.name
        try:
            impact = LineageAgent().verify(manifest, run)
        except LineageError as exc:
            observations.append(
                {
                    "loop_id": "lineage_reverify",
                    "subject": subject,
                    "state": "verify_failed",
                    "detail": str(exc),
                    "source_path": _rel(root, manifest),
                    "source_sha256": _sha256(manifest),
                }
            )
            continue
        observations.append(
            {
                "loop_id": "lineage_reverify",
                "subject": subject,
                # impact carries a wall-clock field (verified_at); the observation keeps
                # only stable verdict fields so the ledger stays deterministic
                "state": str(impact.get("status") or "unknown"),
                "changed": bool(impact.get("changed")),
                "stale_nodes": list(impact.get("stale") or []),
                "stale": len(impact.get("stale") or []),
                "requires_reclosure": bool(impact.get("requires_reclosure")),
                "requires_resign": bool(impact.get("requires_resign")),
                "export_allowed": bool(impact.get("export_allowed")),
                "source_path": _rel(root, manifest),
                "source_sha256": _sha256(manifest),
            }
        )
    return observations


def _propose_lineage_reverify(observation: Dict[str, Any]) -> List[Dict[str, Any]]:
    subject = str(observation.get("subject") or "")
    stale = int(observation.get("stale") or 0)
    needs_resign = bool(observation.get("requires_resign"))
    proposal = {
        "loop_id": "lineage_reverify",
        "kind": "record_receipt",
        "read_only": True,
        "subject": subject,
        "human_action": "",
    }
    if stale or needs_resign:
        proposal["human_action"] = (
            "lineage impact is stale on %d node(s)%s; re-run the affected closure/check "
            "and re-sign in the CLI before any further export" % (stale, " and a re-sign is required" if needs_resign else "")
        )
    return [proposal]


def _gate_lineage_reverify(proposal: Dict[str, Any]) -> Dict[str, Any]:
    # default reject: only read-only receipts may pass; anything that would touch a
    # gated artifact (claim/EA/closure/signature/export) is refused at the seam
    if proposal.get("read_only"):
        return {"decision": "auto_allowed", "reason": "read-only re-verification; writes nothing outside the feedback ledger"}
    return {"decision": "rejected", "reason": "mutating proposals need a registered scope (default reject)"}


def _apply_lineage_reverify(proposal: Dict[str, Any], observation: Dict[str, Any], project: Path) -> Dict[str, Any]:
    return {
        "effect": "recorded_receipt",
        "state": str(observation.get("state") or ""),
        "stale": int(observation.get("stale") or 0) if not isinstance(observation.get("stale"), list) else len(observation["stale"]),
        "human_action": str(proposal.get("human_action") or ""),
    }


register_loop(
    "lineage_reverify",
    _observe_lineage_reverify,
    _propose_lineage_reverify,
    _gate_lineage_reverify,
    _apply_lineage_reverify,
)


def _observe_t6b_falsification(project: Path, limit: int = 50) -> List[Dict[str, Any]]:
    """T6b 证伪/反事实（审计项 → 记录化 proposal 的第一步，71-图① 对照）。

    Observation: executed studies bind a falsification condition in
    study-origin.json; the loop reads that condition together with the study's
    claim status.  The auto-back-pointer into hypothesis GENERATION is roadmap;
    v1 records the constraint a future generation must carry.
    """
    from .storage import read_json as _read_json

    root = Path(project).resolve()
    observations: List[Dict[str, Any]] = []
    studies = root / "studies"
    if not studies.is_dir():
        return observations
    for origin_path in sorted(studies.glob("*/study-origin.json"))[-max(1, min(int(limit), 200)):]:
        try:
            origin = _read_json(origin_path)
        except (OSError, ValueError):
            origin = {}
        if not isinstance(origin, dict):
            origin = {}
        study_dir = origin_path.parent
        claim_path = study_dir / "claim.json"
        claim_status = "absent"
        if claim_path.is_file():
            try:
                claim_payload = _read_json(claim_path)
                claim_status = str((claim_payload or {}).get("status") or "absent")
            except (OSError, ValueError):
                claim_status = "unreadable"
        falsification = str(origin.get("falsification") or "")
        observations.append(
            {
                "loop_id": "t6b_falsification",
                "subject": _rel(root, study_dir),
                "state": "falsification_bound" if falsification else "no_falsification_bound",
                "falsification": falsification,
                "idea_id": str(origin.get("idea_id") or ""),
                "claim_status": claim_status,
                "source_path": _rel(root, origin_path),
                "source_sha256": _sha256(origin_path),
            }
        )
    return observations


def _propose_t6b_falsification(observation: Dict[str, Any]) -> List[Dict[str, Any]]:
    falsification = str(observation.get("falsification") or "")
    if observation.get("state") == "falsification_bound":
        constraint = "carry the executed falsification condition into new hypotheses: " + falsification[:240]
        constraint_kind = "carry_falsification"
        payload = {"falsification": falsification[:240]}
    else:
        constraint = (
            "bind a falsification condition before the next study is executed "
            "(study-origin.falsification is empty for %s)" % observation.get("subject")
        )
        constraint_kind = "require_falsification_binding"
        payload = {}
    return [
        {
            "loop_id": "t6b_falsification",
            "kind": "generation_constraint",
            "read_only": True,
            "subject": str(observation.get("subject") or ""),
            "constraint": constraint,
            "constraint_kind": constraint_kind,
            "payload": payload,
            "human_action": "",
        }
    ]


def _apply_t6b_falsification(proposal: Dict[str, Any], observation: Dict[str, Any], project: Path) -> Dict[str, Any]:
    return {
        "effect": "recorded_constraint",
        "state": str(observation.get("state") or ""),
        "constraint": str(proposal.get("constraint") or ""),
    }


register_loop(
    "t6b_falsification",
    _observe_t6b_falsification,
    _propose_t6b_falsification,
    _gate_lineage_reverify,  # same read-only-only gate discipline
    _apply_t6b_falsification,
)


def _observe_belief_revision(project: Path, limit: int = 50) -> List[Dict[str, Any]]:
    """信念修订（图① 反馈环 C 的记录化第一步）。

    Observation: idea.json candidates crossed with idea-review.json reviews
    (recommendation + reasons).  The auto belief-revision mechanism is roadmap;
    v1 records the per-idea constraint a future generation must carry.
    """
    from .storage import read_json as _read_json

    root = Path(project).resolve()
    observations: List[Dict[str, Any]] = []
    for idea_path in sorted(root.glob("runs/*/idea.json"))[-max(1, min(int(limit), 200)):]:
        run_dir = idea_path.parent
        run_id = run_dir.name
        try:
            idea = _read_json(idea_path) or {}
        except (OSError, ValueError):
            idea = {}
        candidates = [c for c in (idea.get("candidates") or []) if isinstance(c, dict)]
        if not candidates:
            continue
        reviews: Dict[str, Dict[str, Any]] = {}
        review_path = run_dir / "idea-review.json"
        if review_path.is_file():
            try:
                review = _read_json(review_path) or {}
                for item in review.get("reviews") or []:
                    if isinstance(item, dict) and item.get("idea_id"):
                        reviews[str(item["idea_id"])] = item
            except (OSError, ValueError):
                reviews = {}
        for cand in candidates:
            idea_id = str(cand.get("idea_id") or "")
            review = reviews.get(idea_id) or {}
            recommendation = str(review.get("recommendation") or cand.get("status") or "unknown")
            reasons = review.get("reasons") or []
            reasons_text = "; ".join(str(r) for r in reasons[:3])[:240]
            # the verdict side of the constraint lives in the review when one
            # exists; bind it as the primary source so a changed review
            # invalidates the constraint, and keep the idea hash as an auxiliary
            # binding because the constraint quotes the candidate title
            primary = review_path if review_path.is_file() else idea_path
            observations.append(
                {
                    "loop_id": "belief_revision",
                    "subject": "runs/%s/%s" % (run_id, idea_id or "candidate"),
                    "state": recommendation,
                    "title": str(cand.get("title") or "")[:160],
                    "lens": str(cand.get("lens") or ""),
                    "reasons": reasons_text,
                    "source_path": _rel(root, primary),
                    "source_sha256": _sha256(primary),
                    "idea_source_path": _rel(root, idea_path),
                    "idea_source_sha256": _sha256(idea_path),
                }
            )
    return observations


def _propose_belief_revision(observation: Dict[str, Any]) -> List[Dict[str, Any]]:
    state = str(observation.get("state") or "unknown")
    title = str(observation.get("title") or "")
    if state in ("revise", "needs_more_work", "rejected"):
        constraint = "next generation: revise or drop '%s' — review verdict %s%s" % (
            title[:120],
            state,
            ("; reasons: " + str(observation.get("reasons"))) if observation.get("reasons") else "",
        )
        constraint_kind = "demote_candidate"
    else:
        constraint = "carry forward '%s' (verdict %s); keep its evidence binding intact" % (title[:120], state)
        constraint_kind = "carry_forward"
    return [
        {
            "loop_id": "belief_revision",
            "kind": "generation_constraint",
            "read_only": True,
            "subject": str(observation.get("subject") or ""),
            "constraint": constraint,
            "constraint_kind": constraint_kind,
            "payload": {"title": title[:120], "verdict": state},
            "human_action": "",
        }
    ]


register_loop(
    "belief_revision",
    _observe_belief_revision,
    _propose_belief_revision,
    _gate_lineage_reverify,
    _apply_t6b_falsification,
)


def _observe_homogeneity(project: Path, limit: int = 50) -> List[Dict[str, Any]]:
    """同质化监测（图① 假设生成自环的记录化第一步）。

    Observation: per idea.json, the lens distribution and single-source share of
    the candidates.  Deterministic counts only; the injection of diversity
    constraints into generation prompts is roadmap.
    """
    from .storage import read_json as _read_json

    root = Path(project).resolve()
    observations: List[Dict[str, Any]] = []
    for idea_path in sorted(root.glob("runs/*/idea.json"))[-max(1, min(int(limit), 200)):]:
        run_id = idea_path.parent.name
        try:
            idea = _read_json(idea_path) or {}
        except (OSError, ValueError):
            idea = {}
        candidates = [c for c in (idea.get("candidates") or []) if isinstance(c, dict)]
        if not candidates:
            continue
        total = len(candidates)
        lens_counts: Dict[str, int] = {}
        single_source = 0
        for cand in candidates:
            lens = str(cand.get("lens") or "unlabeled")
            lens_counts[lens] = lens_counts.get(lens, 0) + 1
            try:
                if int(cand.get("source_count") or 0) <= 1:
                    single_source += 1
            except (TypeError, ValueError):
                pass
        dominant_lens = max(lens_counts, key=lambda k: lens_counts[k])
        dominant_share = round(lens_counts[dominant_lens] / total, 4)
        if total < 3:
            state = "insufficient_data"
        elif dominant_share >= 0.67:
            state = "homogeneous"
        else:
            state = "diverse"
        observations.append(
            {
                "loop_id": "homogeneity",
                "subject": "runs/%s" % run_id,
                "state": state,
                "candidates": total,
                "dominant_lens": dominant_lens,
                "dominant_share": dominant_share,
                "lens_counts": lens_counts,
                "single_source_share": round(single_source / total, 4),
                "source_path": _rel(root, idea_path),
                "source_sha256": _sha256(idea_path),
            }
        )
    return observations


def _propose_homogeneity(observation: Dict[str, Any]) -> List[Dict[str, Any]]:
    state = str(observation.get("state") or "")
    if state != "homogeneous":
        return []  # diverse/insufficient_data carry no constraint
    return [
        {
            "loop_id": "homogeneity",
            "kind": "generation_constraint",
            "read_only": True,
            "subject": str(observation.get("subject") or ""),
            "constraint": (
                "inject diversity: %.0f%% of candidates share lens '%s'; require at least "
                "two distinct lenses in the next generation"
                % (float(observation.get("dominant_share") or 0) * 100, observation.get("dominant_lens"))
            ),
            "constraint_kind": "require_lens_diversity",
            "payload": {
                "dominant_lens": str(observation.get("dominant_lens") or ""),
                "dominant_share": float(observation.get("dominant_share") or 0),
            },
            "human_action": "",
        }
    ]


register_loop(
    "homogeneity",
    _observe_homogeneity,
    _propose_homogeneity,
    _gate_lineage_reverify,
    _apply_t6b_falsification,
)


def run_feedback(project: Path, loops: Optional[List[str]] = None, limit: int = 50) -> Dict[str, Any]:
    """Run the explicitly enabled loops; with none enabled, write nothing anywhere."""
    root = Path(project).resolve()
    if not root.is_dir():
        raise ValueError("project directory does not exist: %s" % root)
    if not loops:
        return {
            "schema_version": FEEDBACK_SCHEMA,
            "status": "disabled",
            "loops_run": [],
            "rows": 0,
            "registered": registered_loops(),
            "boundary": _BOUNDARY,
        }
    unknown = [loop_id for loop_id in loops if loop_id not in _LOOPS]
    if unknown:
        raise ValueError("unknown feedback loop(s): %s; registered: %s" % (", ".join(unknown), ", ".join(registered_loops())))
    rows: List[Dict[str, Any]] = []
    for loop_id in loops:
        entry = _LOOPS[loop_id]
        for observation in entry["observe"](root, limit=limit):
            for proposal in entry["propose"](observation):
                decision = entry["gate"](proposal)
                effect = None
                if decision.get("decision") == "auto_allowed":
                    effect = entry["apply"](proposal, observation, root)
                rows.append(
                    {
                        "loop_id": loop_id,
                        "subject": str(observation.get("subject") or ""),
                        "observation": observation,
                        "proposal": proposal,
                        "gate_decision": decision,
                        "effect": effect,
                    }
                )
    rows.sort(key=lambda row: (row["loop_id"], row["subject"], json.dumps(row["observation"], sort_keys=True)))
    ledger = {
        "schema_version": FEEDBACK_SCHEMA,
        "status": "ran",
        "loops": list(loops),
        "rows": rows,
        "boundary": _BOUNDARY,
    }
    write_json_atomic(str(root / "feedback-ledger.json"), ledger)
    return ledger


def read_ledger(path: Path) -> Dict[str, Any]:
    """Read a previously written feedback ledger."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


CONSTRAINT_SCHEMA = "generation-constraints-0.2"

_T6B_CARRY_PREFIX = "carry the executed falsification condition into new hypotheses: "
_BELIEF_DROP_PREFIX = "next generation: revise or drop '"

# only kinds that actually change generation cross this edge; carry_forward and
# require_falsification_binding remain ledger receipts (audit/human), not noise
# in the generation provenance
GENERATION_EFFECT_KINDS = frozenset(
    ("require_lens_diversity", "demote_candidate", "carry_falsification")
)

_CONSTRAINT_BOUNDARY = (
    "consumer-side read of the feedback ledger: generation_constraint rows are "
    "consumed by typed constraint_kind/payload (text is human-readable only); "
    "rows whose observation source no longer hashes to the recorded sha256 are "
    "denied (default reject) and listed in stale; read-only, writes nothing"
)


def _generation_constraint_kind(
    proposal: Dict[str, Any], loop_id: str, text: str
) -> Tuple[str, bool]:
    kind = str(proposal.get("constraint_kind") or "").strip()
    if kind:
        return kind, False
    # legacy ledgers (pre-0.6.0) carry text only; infer the kind once, at the
    # consumer edge, so the generation side never parses English prose
    if loop_id == "t6b_falsification":
        if text.startswith(_T6B_CARRY_PREFIX):
            return "carry_falsification", True
        return "require_falsification_binding", True
    if loop_id == "belief_revision":
        if text.startswith(_BELIEF_DROP_PREFIX):
            return "demote_candidate", True
        return "carry_forward", True
    if loop_id == "homogeneity":
        return "require_lens_diversity", True
    return "", True


def _legacy_constraint_payload(kind: str, text: str) -> Dict[str, Any]:
    if kind == "carry_falsification" and text.startswith(_T6B_CARRY_PREFIX):
        return {"falsification": text[len(_T6B_CARRY_PREFIX):]}
    if kind == "demote_candidate" and text.startswith(_BELIEF_DROP_PREFIX):
        rest = text[len(_BELIEF_DROP_PREFIX):]
        end = rest.find("'")
        return {"title": rest[:end] if end >= 0 else rest}
    return {}


def generation_constraints(project: Path) -> Dict[str, Any]:
    """Fresh generation constraints for the next hypothesis generation.

    The loops record constraints bound to the artifact they observed; this is
    the read side of that seam (71-图① 回指).  A constraint whose source
    artifact changed since the ledger row was written is stale: it is denied
    and surfaced in ``stale`` instead of silently shaping a new hypothesis —
    the same 上游变更→失效→回指复验 discipline the lineage loop applies to
    closures, applied to generation.
    """
    root = Path(project).resolve()
    result: Dict[str, Any] = {
        "schema_version": CONSTRAINT_SCHEMA,
        "constraints": [],
        "stale": [],
        "ledger_sha256": "",
        "boundary": _CONSTRAINT_BOUNDARY,
    }
    ledger_path = root / "feedback-ledger.json"
    if not ledger_path.is_file():
        return result
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    if not isinstance(ledger, dict):
        return result
    result["ledger_sha256"] = _sha256(ledger_path)
    seen = set()
    for row in ledger.get("rows") or []:
        if not isinstance(row, dict):
            continue
        proposal = row.get("proposal") or {}
        observation = row.get("observation") or {}
        if not isinstance(proposal, dict) or not isinstance(observation, dict):
            continue
        if proposal.get("kind") != "generation_constraint":
            continue
        if (row.get("gate_decision") or {}).get("decision") != "auto_allowed":
            continue
        constraint = str(proposal.get("constraint") or "")
        source_path = str(observation.get("source_path") or "")
        recorded = str(observation.get("source_sha256") or "")
        if not constraint or not source_path or not recorded:
            continue
        key = (str(row.get("loop_id") or ""), str(observation.get("subject") or ""), constraint)
        if key in seen:
            continue
        seen.add(key)
        constraint_kind, legacy = _generation_constraint_kind(proposal, key[0], constraint)
        if constraint_kind not in GENERATION_EFFECT_KINDS:
            continue
        payload = proposal.get("payload") if isinstance(proposal.get("payload"), dict) else {}
        if legacy:
            payload = _legacy_constraint_payload(constraint_kind, constraint) or payload
        entry = {
            "loop_id": key[0],
            "subject": key[1],
            "constraint": constraint,
            "constraint_kind": constraint_kind,
            "payload": payload,
            "source_path": source_path,
            "source_sha256": recorded,
        }
        if legacy:
            entry["legacy_inferred"] = True
        source = root / source_path
        actual = _sha256(source) if source.is_file() else ""
        if actual != recorded:
            entry["reason"] = (
                "source artifact changed or missing since the ledger row was recorded"
            )
            result["stale"].append(entry)
            continue
        aux_path = str(observation.get("idea_source_path") or "")
        aux_recorded = str(observation.get("idea_source_sha256") or "")
        if aux_path and aux_recorded:
            aux = root / aux_path
            if not aux.is_file() or _sha256(aux) != aux_recorded:
                entry["reason"] = (
                    "bound idea artifact changed or missing since the ledger row was recorded"
                )
                result["stale"].append(entry)
                continue
        result["constraints"].append(entry)
    result["constraints"].sort(key=lambda item: (item["loop_id"], item["subject"], item["constraint"]))
    result["stale"].sort(key=lambda item: (item["loop_id"], item["subject"], item["constraint"]))
    return result


ACTION_SCHEMA = "verdict-action-0.1"

_ACTION_BOUNDARY = (
    "deterministic decision table: verdict rows -> one proposed action per subject; "
    "same-subject conflicts and invariant violations escalate to a human instead of "
    "guessing a winner; pure and wall-clock free, so the same rows always produce "
    "the same actions"
)


def _action_for(kind: str, status: str) -> str:
    if kind == "closure":
        if status == "signed":
            return "verify_bundle"
        if status == "ready":
            return "closure_sign_human"
        return "inspect_run"
    if kind == "claim":
        if status == "signed":
            return "closure_check"
        if status == "draft":
            return "claim_sign_human"
        return "complete_run_first"
    if kind == "experiment":
        if status == "signed":
            return "verify_bundle"
        if status == "ready_for_human_signature":
            return "experiment_sign_human"
        return "run_experiment_closure"
    if kind == "study":
        if status == "signed":
            return "closed_study"
        if status == "ready_for_human_signature":
            return "study_sign_human"
        return "run_study_closure"
    if kind == "snapshot_drift":
        # the drift row means the capsule snapshot is stale; the summary consumer
        # already re-derives through the bus, so the action is: trust the override,
        # never the snapshot
        return "verdict_bus_authoritative"
    return "inspect_artifacts"


def verdict_action_table(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministically propose the next action per subject from verdict rows.

    借鉴点（71-§4.2 设计输入 3）：grade-iterate 的 verdict_reader 是纯函数决策表，
    预算/状态改变建议动作；这里同型——同一 subject 的判定互相矛盾、或出现不变量
    违例（closure signed 而 claim 未签）时，升级为 escalate_conflict 交人工裁决，
    不猜哪边对。
    """
    by_subject: Dict[str, Dict[str, str]] = {}
    for row in rows:
        subject = str(row.get("subject") or "")
        kind = str(row.get("kind") or "")
        status = str(row.get("status") or "")
        if not subject or not kind:
            continue
        slot = by_subject.setdefault(subject, {})
        if kind in slot and slot[kind] != status:
            # same subject, same kind, two verdicts: the table does not guess
            slot[kind] = "__conflict__"
        else:
            slot[kind] = status
    actions = []
    for subject in sorted(by_subject):
        slot = by_subject[subject]
        conflict = any(status == "__conflict__" for status in slot.values())
        if not conflict and slot.get("closure") == "signed" and slot.get("claim") not in (None, "signed"):
            # invariant violation: a signed closure over an unsigned claim cannot be
            # acted on; escalate instead of picking a winner
            conflict = True
        if conflict:
            action, basis = "escalate_conflict", "conflicting verdicts for one subject"
        else:
            # the earliest unfinished stage wins: claim -> closure -> bundle
            claim_status = slot.get("claim")
            closure_status = slot.get("closure")
            if closure_status is not None:
                action, basis = _action_for("closure", closure_status), {"kind": "closure", "status": closure_status}
            elif claim_status is not None:
                action, basis = _action_for("claim", claim_status), {"kind": "claim", "status": claim_status}
            else:
                drift_status = slot.get("snapshot_drift")
                exp_status = slot.get("experiment")
                study_status = slot.get("study")
                if drift_status is not None:
                    action, basis = _action_for("snapshot_drift", drift_status), {"kind": "snapshot_drift", "status": drift_status}
                elif exp_status is not None:
                    action, basis = _action_for("experiment", exp_status), {"kind": "experiment", "status": exp_status}
                elif study_status is not None:
                    action, basis = _action_for("study", study_status), {"kind": "study", "status": study_status}
                else:
                    action, basis = "inspect_artifacts", {}
        actions.append({"subject": subject, "action": action, "basis": basis})
    counts: Dict[str, int] = {}
    for item in actions:
        counts[item["action"]] = counts.get(item["action"], 0) + 1
    return {
        "schema_version": ACTION_SCHEMA,
        "actions": actions,
        "counts": counts,
        "boundary": _ACTION_BOUNDARY,
    }
