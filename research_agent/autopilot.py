"""Policy-bounded autopilot: a human delegates the gates once, with limits.

The policy file is the authority. This module never invents one, never widens or overwrites
one, and writes the policy hash into every reason it signs. It is CLI-only: MCP and HTTP expose no
autopilot tool, because a host that can start a run could otherwise choose its own policy.

What it automates: G1 selection, G2 protocol freeze, bibliography verification, S5b claim,
G5 closure signature, local bundle publication and lineage. What it refuses: an expired or
out-of-scope policy, a claim whose assertion is not the worst-seed floor, a run that already
has a claim, more runs than the policy allows, and any check the chain itself blocks.
"""

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .bibliography import BibliographyAgent
from .closure import ClosureAgent
from .flow import sha256_json
from .lineage import LineageAgent, write_impact, write_manifest
from .modules.experiment import ExperimentDesignAgent
from .modules.run import RunError, RunAgent
from .paths import DEFAULT_SIGNER_STORE_PATH
from .pipeline import PipelineRequest, PipelineRunner, write_pipeline_artifacts
from .project import ProjectError, open_project
from .signers import SignerError, SignerStore
from .specs import SpecStore
from .storage import write_json_atomic

POLICY_SCHEMA = "autopilot-policy-0.1"
REPORT_SCHEMA = "autopilot-report-0.1"
LEDGER_SCHEMA = "autopilot-ledger-0.1"
POLICY_BOUNDARY = (
    "a human-authored policy, not a human signature: every artifact it creates records the "
    "policy hash and the authorizer, submission stays false, and anything outside the policy "
    "stops the run instead of widening it"
)


class AutopilotError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_time(value: Any, label: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise AutopilotError(label + " is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise AutopilotError(label + " must be ISO-8601")
    if parsed.tzinfo is None:
        raise AutopilotError(label + " must include a timezone offset")
    return parsed


def policy_fingerprint(policy: Dict[str, Any]) -> str:
    payload = {key: value for key, value in policy.items() if key != "policy_sha256"}
    return sha256_json(payload)


def build_policy(
    *,
    scope: str,
    authorized_by: str,
    signer_id: str,
    datasets: Optional[List[str]] = None,
    min_seeds: int = 3,
    max_runs: int = 1,
    expires_hours: int = 24,
    endpoint: str = "bundle",
    limitation: str = "",
    bibliography_source: str = "",
    allow_revise_idea: bool = False,
    note: str = "",
) -> Dict[str, Any]:
    """Build the authorization artifact a human writes once; it is not a signature."""
    if not str(scope or "").strip():
        raise AutopilotError("scope is required")
    if not str(authorized_by or "").strip():
        raise AutopilotError("authorized_by is required; an unattributed policy is not a delegation")
    if not str(signer_id or "").strip():
        raise AutopilotError("signer_id is required; the delegated closure signature needs an identity")
    if endpoint not in ("bundle", "lineage"):
        raise AutopilotError("endpoint must be bundle or lineage")
    if int(min_seeds) < 1:
        raise AutopilotError("min_seeds must be >= 1")
    if int(max_runs) < 1:
        raise AutopilotError("max_runs must be >= 1")
    if int(expires_hours) < 1:
        raise AutopilotError("expires_hours must be >= 1")
    now = datetime.now(timezone.utc)
    policy = {
        "schema_version": POLICY_SCHEMA,
        "policy_id": "AUTO-" + sha256_json(
            {"scope": scope, "authorized_by": authorized_by, "at": now.isoformat()}
        )[:10],
        "authorized_by": str(authorized_by).strip(),
        "authorized_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(hours=int(expires_hours))).isoformat(timespec="seconds"),
        "scope": str(scope).strip(),
        "datasets": [str(item) for item in (datasets or [])] or [str(scope).split("/")[-1]],
        "min_seeds": int(min_seeds),
        "max_runs": int(max_runs),
        "endpoint": endpoint,
        "signer_id": str(signer_id).strip(),
        "statement": "draft_verbatim",
        "require_worst_seed_assertion": True,
        "auto_g1": {
            "enabled": True,
            "require_review_advance": not bool(allow_revise_idea),
            "allow_revise": bool(allow_revise_idea),
            "require_kill_criteria": True,
        },
        "auto_g2": {"enabled": True, "limitation": str(limitation).strip()},
        "bibliography_source": str(bibliography_source).strip(),
        "note": str(note).strip(),
        "boundary": POLICY_BOUNDARY,
    }
    policy["policy_sha256"] = policy_fingerprint(policy)
    return policy


def load_policy(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise AutopilotError("policy not found: " + str(path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AutopilotError("policy is not readable JSON: %s" % exc)
    if not isinstance(value, dict):
        raise AutopilotError("policy must be a JSON object")
    if value.get("schema_version") != POLICY_SCHEMA:
        raise AutopilotError("unsupported policy schema: %s" % value.get("schema_version"))
    for key in (
        "policy_id",
        "authorized_by",
        "authorized_at",
        "expires_at",
        "scope",
        "signer_id",
        "endpoint",
        "datasets",
        "min_seeds",
        "max_runs",
    ):
        if key not in value:
            raise AutopilotError("policy is missing field: " + key)
    recorded = str(value.get("policy_sha256") or "")
    actual = policy_fingerprint(value)
    if recorded != actual:
        raise AutopilotError("policy hash does not match its contents; edit is not authorized")
    return value


def parse_assertion(text: str) -> Dict[str, Any]:
    parts: Dict[str, str] = {}
    for chunk in str(text or "").split(","):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parts[key.strip()] = value.strip()
    try:
        value = float(parts.get("value", ""))
        tolerance = float(parts.get("tolerance", "0"))
    except ValueError:
        raise AutopilotError("assertion value/tolerance must be numbers: " + str(text))
    return {
        "metric": parts.get("metric", ""),
        "comparator": parts.get("comparator", ""),
        "value": round(value, 4),
        "tolerance": tolerance,
    }


def worst_seed_floor(capsule: Dict[str, Any]) -> Tuple[str, Optional[float]]:
    """The floor the draft is supposed to propose: worst seed, no distributional assumption."""
    dataset = str(capsule.get("dataset_id") or "")
    metric = "delta_r2" if "chemlab" in dataset else str(capsule.get("metric_name") or "accuracy")
    values = [
        float(item[metric])
        for item in (capsule.get("metrics_by_seed") or [])
        if isinstance(item, dict) and metric in item
    ]
    return metric, (round(min(values), 4) if values else None)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_ledger(project: Path) -> Dict[str, Any]:
    ledger = _read_json(project / "autopilot" / "ledger.json")
    if ledger.get("schema_version") != LEDGER_SCHEMA:
        return {"schema_version": LEDGER_SCHEMA, "runs": [], "boundary": POLICY_BOUNDARY}
    ledger.setdefault("runs", [])
    return ledger


def _policy_runs_used(ledger: Dict[str, Any], policy_id: str) -> int:
    return sum(
        1
        for item in ledger.get("runs") or []
        if isinstance(item, dict)
        and str(item.get("policy_id") or "") == policy_id
        and str(item.get("claim_id") or "")
    )


def _append_ledger(project: Path, entry: Dict[str, Any]) -> str:
    path = Path(project) / "autopilot" / "ledger.json"
    ledger = _read_ledger(project)
    ledger["runs"].append(entry)
    ledger["updated_at"] = _now()
    write_json_atomic(path, ledger)
    return str(path)


def inspect_run(
    project: Path,
    run_id: str,
    policy: Dict[str, Any],
    ledger: Dict[str, Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """All policy checks before anything is signed, as a list of reasons to stop."""
    root = Path(project).resolve()
    run_dir = root / "runs" / run_id
    run_sub = run_dir / "run"
    reasons: List[str] = []
    if now is None:
        now = datetime.now(timezone.utc)
    expires_at = _parse_time(policy.get("expires_at"), "policy expires_at")
    if now > expires_at:
        reasons.append("policy expired at %s" % policy.get("expires_at"))
    if _policy_runs_used(ledger, str(policy.get("policy_id"))) >= int(policy.get("max_runs") or 1):
        reasons.append(
            "policy already signed %s run(s), its max_runs=%s"
            % (_policy_runs_used(ledger, str(policy.get("policy_id"))), policy.get("max_runs"))
        )
    if not run_dir.is_dir():
        reasons.append("run directory not found: %s" % run_dir)
    capsule = _read_json(run_sub / "run-capsule.json")
    ea = _read_json(run_sub / "ea.json")
    draft = _read_json(run_sub / "claim-draft.json")
    if not capsule:
        reasons.append("run-capsule.json is missing or unreadable")
    if not ea:
        reasons.append("ea.json is missing or unreadable")
    if not draft:
        reasons.append("claim-draft.json is missing; autopilot does not write its own statement")
    if (run_dir / "claim" / "claim.json").is_file():
        reasons.append("this run already has a claim; autopilot never re-signs")
    if capsule and str(capsule.get("status") or "") != "completed":
        reasons.append("capsule status is %s, not completed" % capsule.get("status"))
    draft_scope = str(draft.get("scope") or "")
    if draft_scope and draft_scope != str(policy.get("scope") or ""):
        reasons.append(
            "draft scope %r is outside policy scope %r"
            % (draft_scope, policy.get("scope"))
        )
    dataset = str(capsule.get("dataset_id") or "")
    allowed = [str(item).lower() for item in (policy.get("datasets") or [])]
    if dataset and allowed and not any(item in dataset.lower() for item in allowed):
        reasons.append("dataset %r is not in policy datasets %s" % (dataset, allowed))
    seeds = capsule.get("seeds") or []
    if len(seeds) < int(policy.get("min_seeds") or 1):
        reasons.append(
            "run has %d seed(s); policy requires at least %s"
            % (len(seeds), policy.get("min_seeds"))
        )
    demo = _read_json(run_dir / "demo.json")
    study_design = (demo.get("modules") or {}).get("study_design") or {}
    study_audit = study_design.get("audit") if isinstance(study_design, dict) else {}
    if str((study_audit or {}).get("status") or "") == "incomplete":
        reasons.append("study design audit is incomplete; G2 is blocked")
    if draft and str(draft.get("status") or "") != "draft_needs_human":
        reasons.append("draft status is %r, expected draft_needs_human" % draft.get("status"))
    statement = str(draft.get("statement") or "").strip()
    if not statement:
        reasons.append("draft has no statement")
    proposal = draft.get("assertion_proposal")
    proposal = proposal if isinstance(proposal, dict) else {}
    assertion_text = str(proposal.get("assertion_argument") or "")
    metric, floor = worst_seed_floor(capsule)
    if policy.get("require_worst_seed_assertion", True):
        if not assertion_text:
            reasons.append("draft has no assertion proposal; policy requires the worst-seed floor")
        else:
            try:
                parsed = parse_assertion(assertion_text)
            except AutopilotError as exc:
                parsed = {}
                reasons.append(str(exc))
            if parsed:
                if floor is None:
                    reasons.append("capsule has no per-seed %s values to check the floor" % metric)
                elif parsed["value"] != floor:
                    reasons.append(
                        "assertion value %s is not the worst seed %.4f" % (parsed["value"], floor)
                    )
                if parsed["metric"] != metric:
                    reasons.append(
                        "assertion metric %r is not the capsule metric %r"
                        % (parsed["metric"], metric)
                    )
                if parsed["comparator"] != ">=" or parsed["tolerance"] != 0.0:
                    reasons.append("assertion must be comparator >= with tolerance 0.0")
    return {
        "ok": not reasons,
        "reasons": reasons,
        "run_dir": str(run_dir),
        "capsule": capsule,
        "ea": ea,
        "draft": draft,
        "statement": statement,
        "assertion": assertion_text,
        "metric": metric,
        "floor": floor,
        "runs_used": _policy_runs_used(ledger, str(policy.get("policy_id"))),
    }


def _delegation_reason(policy: Dict[str, Any], step: str) -> str:
    return (
        "[delegated:autopilot] %s under policy %s sha256:%s authorized_by:%s; "
        "not a human signature"
        % (step, policy.get("policy_id"), policy.get("policy_sha256"), policy.get("authorized_by"))
    )


def _g1_decision(run_dir: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    idea = _read_json(run_dir / "idea.json")
    review = _read_json(run_dir / "idea-review.json")
    ranked = list((idea.get("shortlist") or {}).get("ranked") or [])
    candidates = {str(item.get("idea_id")): item for item in (idea.get("candidates") or [])}
    if not ranked:
        raise AutopilotError("idea.json has no ranked shortlist; G1 cannot be delegated")
    choice = ranked[0]
    idea_id = str(choice.get("idea_id") or "")
    candidate = candidates.get(idea_id)
    if not candidate:
        raise AutopilotError("top-ranked idea %r is not in the candidate list" % idea_id)
    settings = policy.get("auto_g1") or {}
    if settings.get("require_kill_criteria", True) and not str(
        candidate.get("falsification") or ""
    ).strip():
        raise AutopilotError("top-ranked idea has no falsification condition")
    recommendation = next(
        (
            str(item.get("recommendation") or "")
            for item in (review.get("reviews") or [])
            if str(item.get("idea_id") or "") == idea_id
        ),
        "",
    )
    if recommendation == "reject":
        raise AutopilotError("idea pre-review rejected the top-ranked idea")
    if recommendation == "revise" and not settings.get("allow_revise", False):
        raise AutopilotError(
            "idea pre-review asks for revision; policy does not allow selecting a revise candidate"
        )
    if settings.get("require_review_advance", True) and recommendation != "advance":
        raise AutopilotError(
            "idea pre-review recommendation is %r, policy requires advance"
            % (recommendation or "missing")
        )
    decision = {
        "status": "approved",
        "selected_idea_id": idea_id,
        "selected_idea_sha256": sha256_json(
            {
                "idea_id": idea_id,
                "title": str(candidate.get("title") or ""),
                "hypothesis": str(candidate.get("hypothesis") or ""),
                "falsification": str(candidate.get("falsification") or ""),
                "evidence_refs": list(candidate.get("evidence_refs") or []),
            }
        ),
        "human_reason": _delegation_reason(policy, "G1 select top-ranked idea " + idea_id),
        "decision_id": "G1-" + idea_id,
        "delegated": True,
    }
    path = run_dir / "g1-decision.json"
    write_json_atomic(path, decision)
    return {"path": str(path), "decision": decision, "recommendation": recommendation}


def _g2_protocol(run_dir: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    settings = policy.get("auto_g2") or {}
    limitation = str(settings.get("limitation") or "").strip()
    if not settings.get("enabled", True):
        raise AutopilotError("auto_g2 is disabled in the policy")
    if not limitation:
        raise AutopilotError("auto_g2.limitation is empty; a protocol without a limitation is not frozen")
    design = _read_json(run_dir / "experiment.json")
    if not design:
        raise AutopilotError("experiment.json is missing or unreadable")
    audit = _read_json(run_dir / "design-audit.json")
    blockers = [item for item in (audit.get("blockers") or []) if str(item).strip()]
    if blockers:
        raise AutopilotError("design audit has blockers: " + ", ".join(map(str, blockers)))
    capsule_path = run_dir / "run" / "run-capsule.json"
    result = ExperimentDesignAgent(SpecStore().load("experiment")).freeze(
        design,
        capsule_path,
        limitation,
        _delegation_reason(policy, "G2 freeze protocol"),
        run_dir / "protocol",
    )
    return {"path": result["path"], "protocol": result["protocol"]}


def _bibliography(run_dir: Path, policy: Dict[str, Any], project: Path, repo_root: Path) -> Dict[str, Any]:
    source = str(policy.get("bibliography_source") or "").strip()
    if not source:
        raise AutopilotError("policy has no bibliography_source; closure cannot pass without one")
    candidate = Path(source)
    if not candidate.is_absolute():
        for base in (project, repo_root):
            if (base / source).is_file():
                candidate = base / source
                break
    if not candidate.is_file():
        raise AutopilotError("bibliography source not found: " + source)
    output_dir = run_dir / "bibliography"
    result = BibliographyAgent().verify(candidate, output_dir)
    card = result.get("bibliography") or {}
    if card.get("status") != "verified_datacite_snapshot":
        raise AutopilotError("bibliography did not verify: %s" % card.get("status"))
    path = Path(str(result.get("path") or output_dir / "bibliography-card.json"))
    if not path.is_file():
        raise AutopilotError("bibliography card was not written")
    return {"path": str(path), "card": card, "source": str(candidate)}


def _replay_writer(run_dir: Path):
    """Reuse model-written sections instead of regenerating the manuscript deterministically.

    Binding a signed claim re-runs the pipeline's paper stage. Without a writer that stage would
    replace the host model's prose with the deterministic template — the claim would be bound and
    the writing lost. Only `model_draft` sections are replayed; deterministic ones stay live.
    """
    paper = _read_json(run_dir / "paper.json")
    by_label = {
        str(item.get("section") or ""): str(item.get("text") or "")
        for item in (paper.get("draft") or [])
        if isinstance(item, dict)
        and str(item.get("status") or "") == "model_draft"
        and str(item.get("text") or "").strip()
    }
    if not by_label:
        return None

    def writer(payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
        out: Dict[str, str] = {}
        for section in payload.get("sections") or []:
            if not isinstance(section, dict):
                continue
            text = by_label.get(str(section.get("label") or ""))
            if text:
                out[str(section.get("key") or "")] = text
        return out or None

    return writer


def _bind_pipeline(
    run_dir: Path,
    policy: Dict[str, Any],
    claim_path: Path,
    protocol_path: Path,
    bibliography_path: Path,
) -> Dict[str, Any]:
    demo = _read_json(run_dir / "demo.json")
    topic = str(demo.get("topic") or "").strip()
    if not topic:
        raise AutopilotError("demo.json has no topic; cannot replay the pipeline deterministically")
    # The bind must speak the same language/venue as the original paper, otherwise the section
    # labels change (摘要 → Abstract) and replaying model prose silently misses every section.
    profile = _read_json(run_dir / "paper.json").get("profile") or {}
    language = str(profile.get("language") or "en")
    venue = str(profile.get("venue_type") or "en_conference")
    if language not in ("zh", "en"):
        raise AutopilotError("paper profile has an unsupported language: " + language)
    study_design_path = run_dir / "study-design.json"
    if not study_design_path.is_file():
        recorded = (
            (_read_json(run_dir / "demo.json").get("modules") or {}).get("study_design") or {}
        )
        study_design = recorded.get("design") if isinstance(recorded, dict) else None
        if isinstance(study_design, dict):
            write_json_atomic(study_design_path, study_design)
    request = PipelineRequest(
        topic=topic,
        language=language,
        venue_type=venue,
        run_dir=str(run_dir / "run"),
        claim_file=str(claim_path),
        protocol_file=str(protocol_path),
        bibliography_file=str(bibliography_path),
        g1_decision_file=str(run_dir / "g1-decision.json"),
        # Reuse the exact idea/design the protocol was frozen against: regenerating them with
        # different retrieval parameters changes design_sha256 and strict mode blocks at G2.
        idea_file=str(run_dir / "idea.json"),
        design_file=str(run_dir / "experiment.json"),
        study_design_file=str(study_design_path) if study_design_path.is_file() else "",
        flow_mode="strict",
    )
    runner = PipelineRunner(
        run_output_dir=run_dir / "run",
        section_writer=_replay_writer(run_dir),
    )
    result = runner.run(request)
    # The CLI writes the demo and runs claim postprocess; the autopilot must not skip the
    # postprocess, because the closure report it produces is what the G5 signature covers.
    write_pipeline_artifacts(result, run_dir, claim_file=str(claim_path))
    return {
        "status": result.status,
        "demo": str(run_dir / "demo.json"),
        "warnings": list(result.warnings),
    }


def run_autopilot(
    project: Path,
    run_id: str,
    policy_path: Path,
    signers_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute the delegated tail of one run; stop at the first policy or chain failure."""
    project = Path(project).resolve()
    try:
        opened = open_project(project)
    except ProjectError as exc:
        raise AutopilotError(str(exc))
    project = Path(opened["path"]).resolve()
    policy = load_policy(Path(policy_path))
    repo_root = Path(repo_root).resolve() if repo_root else project
    signers_store = SignerStore(Path(signers_path or DEFAULT_SIGNER_STORE_PATH))
    try:
        signer = signers_store.get(str(policy.get("signer_id")))
    except SignerError as exc:
        raise AutopilotError("policy signer is not usable: %s" % exc)

    ledger = _read_ledger(project)
    report_dir = project / "autopilot" / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "created_at": _now(),
        "project_dir": str(project),
        "run_id": run_id,
        "policy": {
            "policy_id": policy.get("policy_id"),
            "policy_sha256": policy.get("policy_sha256"),
            "authorized_by": policy.get("authorized_by"),
            "expires_at": policy.get("expires_at"),
            "endpoint": policy.get("endpoint"),
        },
        "status": "stopped",
        "stopped_at": "",
        "reasons": [],
        "steps": [],
        "artifacts": {},
        "delegation": {
            "delegated": True,
            "signer_id": signer.get("signer_id"),
            "signer_name": signer.get("name"),
            "not_a_human_signature": True,
        },
        "boundary": POLICY_BOUNDARY,
    }

    def finish(status: str, stopped_at: str = "", reasons: Optional[List[str]] = None) -> Dict[str, Any]:
        report["status"] = status
        report["stopped_at"] = stopped_at
        if reasons is not None:
            report["reasons"] = list(reasons)
        path = report_dir / "autopilot-report.json"
        report["path"] = str(path)
        write_json_atomic(path, report)
        _append_ledger(
            project,
            {
                "policy_id": policy.get("policy_id"),
                "policy_sha256": policy.get("policy_sha256"),
                "run_id": run_id,
                "status": status,
                "stopped_at": stopped_at,
                "claim_id": (report["artifacts"].get("claim") or {}).get("claim_id", ""),
                "signature_id": (report["artifacts"].get("closure") or {}).get("signature_id", ""),
                "bundle": (report["artifacts"].get("bundle") or {}).get("path", ""),
                "created_at": report["created_at"],
            },
        )
        return report

    try:
        checked = inspect_run(project, run_id, policy, ledger)
    except AutopilotError as exc:
        report["reasons"] = [str(exc)]
        return finish("stopped", "policy")
    if not checked["ok"]:
        report["reasons"] = checked["reasons"]
        return finish("stopped", "policy")
    run_dir = Path(checked["run_dir"])
    report["scope"] = policy.get("scope")
    report["dataset"] = checked["capsule"].get("dataset_id")
    report["seeds"] = list(checked["capsule"].get("seeds") or [])
    report["steps"].append({"step": "policy", "status": "pass", "detail": "bounds checked"})

    try:
        g1 = _g1_decision(run_dir, policy)
    except (AutopilotError, OSError, ValueError) as exc:
        report["reasons"] = [str(exc)]
        return finish("stopped", "G1")
    report["steps"].append(
        {
            "step": "G1",
            "status": "delegated",
            "detail": "selected %s; pre-review=%s"
            % (g1["decision"]["selected_idea_id"], g1["recommendation"] or "missing"),
            "path": g1["path"],
        }
    )

    try:
        g2 = _g2_protocol(run_dir, policy)
    except (AutopilotError, OSError, ValueError) as exc:
        report["reasons"] = [str(exc)]
        return finish("stopped", "G2")
    report["steps"].append(
        {"step": "G2", "status": "delegated", "detail": "protocol frozen", "path": g2["path"]}
    )

    try:
        bib = _bibliography(run_dir, policy, project, repo_root)
    except (AutopilotError, OSError, ValueError) as exc:
        report["reasons"] = [str(exc)]
        return finish("stopped", "bibliography")
    report["steps"].append(
        {
            "step": "bibliography",
            "status": "pass",
            "detail": "%d entries verified" % int(bib["card"].get("entry_count") or 0),
            "path": bib["path"],
        }
    )

    claim_dir = run_dir / "claim"
    try:
        claim_result = RunAgent(SpecStore().load("run")).claim(
            run_dir / "run" / "run-capsule.json",
            run_dir / "run" / "ea.json",
            checked["statement"],
            _delegation_reason(policy, "S5b claim"),
            str(policy.get("scope") or ""),
            claim_dir,
            assertions=[parse_assertion(checked["assertion"])],
        )
    except (AutopilotError, RunError, OSError, ValueError) as exc:
        report["reasons"] = [str(exc)]
        return finish("stopped", "S5b")
    claim = claim_result["claim"]
    report["artifacts"]["claim"] = {
        "claim_id": claim.get("claim_id"),
        "path": claim_result["path"],
        "sha256": sha256_json(claim),
        "assertion": checked["assertion"],
    }
    report["steps"].append(
        {
            "step": "S5b",
            "status": "delegated",
            "detail": "claim %s signed under policy" % claim.get("claim_id"),
            "path": claim_result["path"],
        }
    )
    delegation_path = report_dir / "claim-delegation.json"
    write_json_atomic(
        delegation_path,
        {
            "schema_version": "autopilot-claim-delegation-0.1",
            "policy_id": policy.get("policy_id"),
            "policy_sha256": policy.get("policy_sha256"),
            "authorized_by": policy.get("authorized_by"),
            "claim_id": claim.get("claim_id"),
            "claim_path": claim_result["path"],
            "claim_sha256": report["artifacts"]["claim"]["sha256"],
            "boundary": POLICY_BOUNDARY,
        },
    )

    try:
        bound = _bind_pipeline(
            run_dir, policy, Path(claim_result["path"]), Path(g2["path"]), Path(bib["path"])
        )
    except (AutopilotError, OSError, ValueError, KeyError) as exc:
        report["reasons"] = [str(exc)]
        return finish("stopped", "S5b-bind")
    report["steps"].append(
        {"step": "S5b-bind", "status": "pass", "detail": "pipeline status=%s" % bound["status"]}
    )

    closure_report = run_dir / "closure" / "closure-report.json"
    closure = _read_json(closure_report)
    if str(closure.get("status") or "") != "ready":
        report["reasons"] = [
            "closure is %s: %s"
            % (closure.get("status") or "missing", ", ".join(closure.get("unresolved") or []))
        ]
        return finish("stopped", "G5-check")
    report["steps"].append({"step": "G5-check", "status": "pass", "detail": "closure ready"})

    try:
        signed = ClosureAgent().sign(
            closure_report,
            run_dir / "demo.json",
            Path(claim_result["path"]),
            _delegation_reason(policy, "G5 closure signature"),
            run_dir / "closure-signature",
            signer_store=signers_store,
            signer_id=str(policy.get("signer_id")),
        )
    except (OSError, ValueError) as exc:
        report["reasons"] = [str(exc)]
        return finish("stopped", "G5-sign")
    report["artifacts"]["closure"] = {
        "signature_id": signed["signature"].get("signature_id"),
        "signature_path": signed["path"],
        "manifest": signed["manifest"],
        "report_id": signed["signature"].get("report_id"),
        "submission": False,
    }
    report["steps"].append(
        {
            "step": "G5-sign",
            "status": "delegated",
            "detail": "closure signature %s" % signed["signature"].get("signature_id"),
            "path": signed["path"],
        }
    )

    if str(policy.get("endpoint") or "bundle") == "lineage":
        return finish("completed")

    bundles_parent = project / "bundles"
    bundle_dir = bundles_parent / run_id
    if bundle_dir.exists():
        report["reasons"] = ["bundle target already exists; autopilot never overwrites: " + str(bundle_dir)]
        return finish("stopped", "publish")
    try:
        published = ClosureAgent().publish(
            Path(signed["manifest"]),
            bundles_parent,
            Path(signed["path"]),
            run_id,
            signers_store,
        )
    except (OSError, ValueError) as exc:
        report["reasons"] = [str(exc)]
        return finish("stopped", "publish")
    bundle_dir = Path(str(published.get("bundle") or bundle_dir))
    report["artifacts"]["bundle"] = {
        "path": str(bundle_dir),
        "manifest": str(published.get("manifest") or bundle_dir / "bundle-manifest.json"),
        "signed": bool(published.get("signed")),
        "artifact_count": int(published.get("artifact_count") or 0),
    }
    report["steps"].append(
        {
            "step": "publish",
            "status": "pass",
            "detail": "submission=false bundle sealed",
            "path": report["artifacts"]["bundle"]["path"],
        }
    )

    try:
        bundle_check = ClosureAgent().verify_bundle(bundle_dir, signers_store)
        if bundle_check.get("status") != "clean":
            report["reasons"] = [
                "sealed bundle failed verification: " + "; ".join(bundle_check.get("errors") or [])
            ]
            return finish("stopped", "verify-bundle")
        report["artifacts"]["bundle"]["verified"] = True
        report["artifacts"]["bundle"]["signature_verified"] = bool(
            bundle_check.get("signature_verified")
        )
        # Lineage reads a run layout, not the sealed bundle layout; the bundle itself has
        # already been re-hashed above, so these are two views of the same bytes.
        manifest = LineageAgent().build(run_dir, signer_store=signers_store)
        manifest_path = write_manifest(manifest, report_dir / "lineage")
        impact = LineageAgent().verify(manifest_path, run_dir)
        impact_path = write_impact(impact, report_dir / "lineage-verify")
    except (OSError, ValueError) as exc:
        report["reasons"] = [str(exc)]
        return finish("stopped", "lineage")
    report["artifacts"]["lineage"] = {
        "status": manifest.get("status"),
        "path": str(manifest_path),
        "verify": impact.get("status"),
        "verify_path": str(impact_path),
    }
    report["steps"].append(
        {
            "step": "lineage",
            "status": "pass" if impact.get("status") == "clean" else "fail",
            "detail": "status=%s verify=%s" % (manifest.get("status"), impact.get("status")),
            "path": str(manifest_path),
        }
    )
    if impact.get("status") != "clean":
        report["reasons"] = ["lineage verify is %s" % impact.get("status")]
        return finish("stopped", "lineage")
    # The pipeline wrote the capsule before the signature existed; rewrite it so G5/S13/claim
    # status reflect the signed state instead of asking for a signature that already happened.
    try:
        from .loop_capsule import write_loop_capsule

        report["artifacts"]["loop_capsule"] = str(write_loop_capsule(run_dir))
    except (OSError, ValueError) as exc:
        report["reasons"] = ["loop capsule refresh failed: %s" % exc]
        return finish("stopped", "loop-capsule")
    return finish("completed")


def _scope_dataset(policy: Dict[str, Any]) -> str:
    scope = str(policy.get("scope") or "")
    prefix = "S5/demo/"
    if not scope.startswith(prefix):
        raise AutopilotError("autopilot research needs a scope of the form S5/demo/<dataset>")
    dataset = scope[len(prefix):].strip()
    if dataset not in ("iris", "breast_cancer", "chemlab"):
        raise AutopilotError("unsupported dataset in scope: " + dataset)
    allowed = [str(item).lower() for item in (policy.get("datasets") or [])]
    if allowed and not any(item in dataset.lower() for item in allowed):
        raise AutopilotError("dataset %r is not in policy datasets %s" % (dataset, allowed))
    return dataset


def run_autopilot_research(
    project: Path,
    topic: str,
    policy_path: Path,
    language: str = "en",
    venue: str = "en_conference",
    max_sources: int = 4,
    run_id: str = "",
    corpus_dir: Optional[Path] = None,
    study_design_file: Optional[Path] = None,
    signers_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """One command from a topic to a sealed bundle, inside one policy.

    The pipeline half stays deterministic: no planner/writer/idea/experiment model is called,
    because a CLI process cannot answer host-model turns. That makes the idea pre-review a
    revise; the policy must say it accepts revise candidates, otherwise this refuses before
    spending a run.
    """
    project = Path(project).resolve()
    try:
        opened = open_project(project)
    except ProjectError as exc:
        raise AutopilotError(str(exc))
    project = Path(opened["path"]).resolve()
    policy = load_policy(Path(policy_path))
    if not str(topic or "").strip():
        raise AutopilotError("topic is required")
    expires_at = _parse_time(policy.get("expires_at"), "policy expires_at")
    if datetime.now(timezone.utc) > expires_at:
        raise AutopilotError("policy expired at %s" % policy.get("expires_at"))
    ledger = _read_ledger(project)
    used = _policy_runs_used(ledger, str(policy.get("policy_id")))
    if used >= int(policy.get("max_runs") or 1):
        raise AutopilotError(
            "policy already signed %d run(s), its max_runs=%s" % (used, policy.get("max_runs"))
        )
    if (policy.get("auto_g1") or {}).get("require_review_advance", True):
        raise AutopilotError(
            "deterministic models produce revise candidates; the policy must allow_revise_idea "
            "or the host must answer idea turns before running autopilot research"
        )
    dataset = _scope_dataset(policy)
    seeds = max(3, int(policy.get("min_seeds") or 3))
    run_id = run_id or "RUN-AUTO-%s-%s" % (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        sha256_json({"topic": topic, "at": _now()})[:6],
    )
    run_dir = project / "runs" / run_id
    if run_dir.exists():
        raise AutopilotError("run directory already exists: " + str(run_dir))
    run_dir.mkdir(parents=True)
    study_design_arg = ""
    if study_design_file:
        source = Path(study_design_file)
        if not source.is_file():
            raise AutopilotError("study design file not found: " + str(source))
        shutil.copyfile(str(source), str(run_dir / "study-design.json"))
        study_design_arg = str(run_dir / "study-design.json")
    retriever = None
    parser = None
    source_scope = None
    if corpus_dir:
        from .adapters import LocalDocumentRetriever, SimpleParser

        retriever = LocalDocumentRetriever(Path(corpus_dir))
        parser = SimpleParser(max_spans_per_source=4000)
        source_scope = ["local"]
    runner = PipelineRunner(
        retriever=retriever,
        parser=parser,
        source_scope=source_scope,
        run_output_dir=run_dir / "run",
    )
    result = runner.run(
        PipelineRequest(
            topic=topic,
            language=language,
            venue_type=venue,
            max_sources=max(1, int(max_sources)),
            run_dataset=dataset,
            run_seeds=seeds,
            study_design_file=study_design_arg,
        )
    )
    write_pipeline_artifacts(result, run_dir)
    report = run_autopilot(
        project,
        run_id,
        Path(policy_path),
        Path(signers_path) if signers_path else None,
        repo_root,
    )
    return {
        "schema_version": "autopilot-research-0.1",
        "status": report.get("status"),
        "run_id": run_id,
        "pipeline": {"status": result.status, "fixture_mode": result.fixture_mode},
        "autopilot": report,
        "boundary": POLICY_BOUNDARY,
    }


def _relative_or_empty(root: Path, value: Any) -> str:
    try:
        return Path(str(value)).resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return ""


def autopilot_snapshot(project: Path, history: int = 5) -> Dict[str, Any]:
    """Path-free projection for HTTP and the workbench; the CLI keeps full paths."""
    root = Path(project).resolve()
    status = autopilot_status(root)
    latest = status.get("latest") or {}
    artifacts = latest.get("artifacts") or {}
    steps = [
        {"step": item.get("step"), "status": item.get("status"), "detail": item.get("detail")}
        for item in (latest.get("steps") or [])
        if isinstance(item, dict)
    ]
    claim = artifacts.get("claim") or {}
    closure = artifacts.get("closure") or {}
    bundle = artifacts.get("bundle") or {}
    lineage = artifacts.get("lineage") or {}
    runs = []
    for item in list(status.get("runs") or [])[-max(1, int(history)):]:
        if not isinstance(item, dict):
            continue
        runs.append(
            {
                "policy_id": item.get("policy_id"),
                "run_id": item.get("run_id"),
                "status": item.get("status"),
                "claim_id": item.get("claim_id"),
                "signature_id": item.get("signature_id"),
                "bundle": _relative_or_empty(root, item.get("bundle")),
                "created_at": item.get("created_at"),
            }
        )
    return {
        "schema_version": "autopilot-snapshot-0.1",
        "policy": {
            key: (latest.get("policy") or {}).get(key)
            for key in ("policy_id", "policy_sha256", "authorized_by", "expires_at", "endpoint")
        },
        "run_id": str(latest.get("run_id") or ""),
        "status": str(latest.get("status") or "missing"),
        "stopped_at": str(latest.get("stopped_at") or ""),
        "reasons": list(latest.get("reasons") or []),
        "created_at": str(latest.get("created_at") or ""),
        "steps": steps,
        "claim": {
            "claim_id": claim.get("claim_id"),
            "sha256": claim.get("sha256"),
            "assertion": claim.get("assertion"),
        },
        "signature": {
            "signature_id": closure.get("signature_id"),
            "report_id": closure.get("report_id"),
            "submission": bool(closure.get("submission")),
        },
        "bundle": {
            "path": _relative_or_empty(root, bundle.get("path")),
            "verified": bool(bundle.get("verified")),
            "signed": bool(bundle.get("signed")),
            "artifact_count": int(bundle.get("artifact_count") or 0),
        },
        "lineage": {
            "status": lineage.get("status"),
            "verify": lineage.get("verify"),
        },
        "delegation": dict(latest.get("delegation") or {}),
        "history": runs,
        "boundary": POLICY_BOUNDARY,
    }


def autopilot_status(project: Path) -> Dict[str, Any]:
    root = Path(project).resolve()
    ledger = _read_ledger(root)
    latest: Optional[Dict[str, Any]] = None
    latest_path = ""
    for path in sorted((root / "autopilot").glob("*/autopilot-report.json")):
        value = _read_json(path)
        if value:
            latest = value
            latest_path = str(path)
    return {
        "schema_version": "autopilot-status-0.1",
        "project_dir": str(root),
        "runs": list(ledger.get("runs") or []),
        "latest": latest,
        "latest_path": latest_path,
        "boundary": POLICY_BOUNDARY,
    }
