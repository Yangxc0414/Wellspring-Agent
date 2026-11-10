"""Read-only research loop capsule derived from run artifacts.

The capsule is an integration surface for Qoder/Claude Code/HTTP clients: it
reports which loop nodes actually produced artifacts, which human gates remain,
and which bounded next action applies. It never creates evidence, claims,
gates, signatures or closures.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import read_json, write_json_atomic

SCHEMA = "research-loop-capsule-0.1"
BOUNDARY = (
    "read-only projection of run artifacts; missing nodes are not passes; "
    "does not create evidence, claims, gates, signatures or closures"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(root: Path, name: str) -> Dict[str, Any]:
    value = read_json(root / name)
    return value if isinstance(value, dict) else {}


def _experiment_command(
    root: Path, experiment_id: str, status: Dict[str, Any]
) -> str:
    project = root.parent.parent
    base = (
        'python -m research_agent experiment %s --project "%s" '
        '--experiment-id %s'
        % ("%s", project, experiment_id)
    )
    action = str(status.get("next_action") or "")
    if action == "experiment approve":
        return base % 'approve --human-reason "..."'
    if action == "experiment run --allow-execute":
        return base % "run --allow-execute"
    if action == "experiment ingest":
        return base % "ingest"
    if action.startswith("experiment claim"):
        return base % 'claim --statement "..." --human-reason "..."'
    if action == "experiment closure":
        return base % "closure"
    if action.startswith("experiment sign"):
        return (
            base % 'sign --report "%s" --human-reason "..."'
            % (root.parent.parent / "experiments" / experiment_id / "experiment-closure" / "closure-report.json")
        )
    return base % "status"


def _project_root_for_run(root: Path) -> Optional[Path]:
    candidate = root.parent.parent
    return candidate if (candidate / "project.json").is_file() else None


def project_root_for_run(root: Path) -> Optional[Path]:
    """Public alias: the project directory a run directory belongs to.

    verdict-ledger consumers re-derive verdicts for one run and need the same
    project root this module already resolves; keep one definition.
    """
    return _project_root_for_run(root)


def _experiment_links(root: Path, run_id: str) -> List[Dict[str, Any]]:
    project = root.parent.parent if root.parent.name == "runs" else None
    experiments = project / "experiments" if project is not None else None
    if experiments is None or not experiments.is_dir() or not run_id:
        return []
    from .experiment_runner import experiment_status

    links: List[Dict[str, Any]] = []
    for package in sorted(experiments.iterdir()):
        if not package.is_dir():
            continue
        spec = _load(package, "experiment-spec.json")
        if str(spec.get("run_id") or "") != run_id:
            continue
        try:
            status = experiment_status(project, package.name)
        except Exception:
            continue
        links.append(
            {
                "experiment_id": package.name,
                "run_id": run_id,
                "idea_id": str(spec.get("idea_id") or ""),
                "status": status,
            }
        )
    return links


def _candidates(idea: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        item for item in (idea.get("candidates") or [])
        if isinstance(item, dict)
    ]


def _slots(paper: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        item for item in (paper.get("slots") or [])
        if isinstance(item, dict)
    ]


def build_loop_capsule(
    output_dir: Path,
    observation_id: str = "",
    active_policy_id: str = "",
) -> Dict[str, Any]:
    root = Path(output_dir)
    task = _load(root, "task.json")
    demo = _load(root, "demo.json")
    literature = _load(root, "literature.json")
    idea = _load(root, "idea.json")
    experiment = _load(root, "experiment.json")
    paper = _load(root, "paper.json")
    figure = _load(root, "figure.manifest.json")
    registry = _load(root, "claim-registry.json")
    closure = _load(root, "closure-report.json") or _load(root, "closure/closure-report.json")
    signature = _load(root, "closure-signature/signature.json")
    signed_claim = _load(root, "claim/claim.json") or _load(root, "run/claim/claim.json")
    study_design = (demo.get("modules") or {}).get("study_design") or {}
    if not study_design:
        # A run can carry its own design/audit files after `design audit`; before this
        # fallback the workbench showed no CCF-A level for such runs.
        design_file = _load(root, "study-design.json")
        audit_file = _load(root, "study-design-audit.json")
        if design_file or audit_file:
            study_design = {"design": design_file, "audit": audit_file}
    study_audit = study_design.get("audit") if isinstance(study_design, dict) else {}
    study_audit = study_audit if isinstance(study_audit, dict) else {}
    manuscript_audit = _load(root, "manuscript-audit.json")
    writing_audit = _load(root, "writing-audit.json")
    writing = manuscript_audit or writing_audit

    gates = {
        str(item.get("gate")): item
        for item in (demo.get("gates") or task.get("gates") or [])
        if isinstance(item, dict)
    }
    candidates = _candidates(idea)
    slots = _slots(paper)
    pending_slots = [
        item for item in slots
        if str(item.get("status") or "") not in ("bound_claim", "bound", "ready")
    ]
    run_module = (demo.get("modules") or {}).get("run") or {}
    capsule = run_module.get("capsule") or {}
    claim_draft = run_module.get("claim_draft_record") or {}
    claim_signed = str(signed_claim.get("status") or "") in ("supported", "approved")
    run_id = str(
        demo.get("run_id")
        or task.get("task_id")
        or (root.name if root.parent.name == "runs" else "")
    )
    experiment_links = _experiment_links(root, run_id)
    primary_experiment = experiment_links[0] if experiment_links else {}
    experiment_stages = (
        (primary_experiment.get("status") or {}).get("stages") or {}
        if primary_experiment else {}
    )
    experiment_claim_signed = experiment_stages.get("claim") == "signed"
    experiment_closure = str(experiment_stages.get("closure") or "")
    experiment_signed = experiment_stages.get("signature") == "signed"
    span_count = len(literature.get("spans") or [])
    coverage = literature.get("coverage") or {}
    blockers: List[str] = []
    next_actions: List[Dict[str, str]] = []
    if not span_count:
        blockers.append("S1_NO_LOCATABLE_SPANS")
        next_actions.append({
            "owner": "human",
            "gate": "S1",
            "command": (
                "add full-text sources or change source scope; abstract-only hits "
                "cannot become spans"
            ),
        })

    idea_status = str(idea.get("status") or "missing")
    if candidates and idea_status in ("candidates_need_human", "needs_human"):
        blockers.append("G1_IDEA_SELECTION_REQUIRED")
        first = str(candidates[0].get("idea_id") or "IDEA-01")
        next_actions.append({
            "owner": "human",
            "gate": "G1",
            "command": (
                "python -m research_agent flow g1 --idea-file %s --idea-id %s "
                "--human-reason \"...\" --output-dir %s"
                % (root / "idea.json", first, root)
            ),
        })

    design_status = str(experiment.get("status") or "missing")
    if design_status in ("needs_human", "blocked"):
        blockers.append("G2_PROTOCOL_FREEZE_REQUIRED")
        next_actions.append({
            "owner": "human",
            "gate": "G2",
            "command": (
                "python -m research_agent protocol freeze-design --design %s "
                "--limitation \"...\" --human-reason \"...\" --output-dir %s"
                % (root / "experiment.json", root)
            ),
        })

    if not capsule and not primary_experiment:
        blockers.append("S5_NOT_RUN")
        next_actions.append({
            "owner": "human",
            "gate": "S5",
            "command": (
                "provide run_dataset/run_dir in a human-approved execution; "
                "claim and closure stay CLI-only"
            ),
        })
    elif capsule and str(capsule.get("status") or "") != "completed":
        blockers.append("S5_NOT_COMPLETED")
    if primary_experiment:
        experiment_id = str(primary_experiment.get("experiment_id") or "")
        experiment_status_value = primary_experiment.get("status") or {}
        experiment_command = _experiment_command(
            root, experiment_id, experiment_status_value
        )
        if not experiment_claim_signed:
            blockers.append("EXPERIMENT_CLAIM_UNSIGNED")
            next_actions.append({
                "owner": "human",
                "gate": "S5b",
                "command": experiment_command,
            })
        elif experiment_closure not in ("ready_for_signature", "signed"):
            blockers.append("EXPERIMENT_CLOSURE_PENDING")
            next_actions.append({
                "owner": "human",
                "gate": "G5",
                "command": experiment_command,
            })
        elif not experiment_signed:
            blockers.append("EXPERIMENT_CLOSURE_UNSIGNED")
            next_actions.append({
                "owner": "human",
                "gate": "G5",
                "command": experiment_command,
            })

    bound_primary = any(
        str(item.get("slot_id")) == "result.primary"
        and str(item.get("status")) == "bound_claim"
        for item in slots
    )
    if claim_draft and not bound_primary:
        blockers.append("CLAIM_UNSIGNED")
        # The draft already knows the scope and the proposed numeric assertion; leaving them as
        # placeholders would make the host copy a weaker command than the draft it just read.
        proposal = claim_draft.get("assertion_proposal")
        proposal = proposal if isinstance(proposal, dict) else {}
        claim_parts = [
            "python -m research_agent run claim",
            "--capsule %s" % (root / "run" / "run-capsule.json"),
            "--ea %s" % (root / "run" / "ea.json"),
            '--statement "..."',
            '--human-reason "..."',
            "--scope %s" % (str(claim_draft.get("scope") or "") or "..."),
        ]
        if proposal.get("assertion_argument"):
            claim_parts.append('--assertion "%s"' % proposal["assertion_argument"])
        claim_parts.append("--output-dir %s" % root)
        next_actions.append({
            "owner": "human",
            "gate": "S5b",
            "command": " ".join(claim_parts),
        })
    if any(item.get("slot_id") == "result.primary" for item in slots) and not claim_draft:
        blockers.append("CLAIM_NOT_CREATED")

    if closure:
        if str(closure.get("status") or "") != "ready":
            blockers.append("CLOSURE_BLOCKED")
        elif not signature:
            # A ready report is not a signed report; saying nothing here let the capsule call
            # an unsigned closure "done".
            blockers.append("CLOSURE_UNSIGNED")
            next_actions.append({
                "owner": "human",
                "gate": "G5",
                "command": (
                    "python -m research_agent closure sign --report %s --demo %s --claim %s "
                    "--human-reason \"...\" --output-dir %s"
                    % (
                        root / "closure" / "closure-report.json",
                        root / "demo.json",
                        root / "run" / "claim" / "claim.json",
                        root / "closure-signature",
                    )
                ),
            })
    else:
        blockers.append("CLOSURE_NOT_RUN")
        next_actions.append({
            "owner": "human",
            "gate": "G5",
            "command": (
                "python -m research_agent closure check --demo %s --claim %s --output-dir %s"
                % (root / "demo.json", root / "run" / "claim" / "claim.json", root / "closure")
            ),
        })
    if signature:
        gates["G5"] = {
            **gates.get("G5", {}),
            "gate": "G5",
            "status": "pass",
            "reason": (
                "closure signed locally (delegated autopilot policy)"
                if str(signature.get("human_reason") or "").startswith("[delegated:")
                else "closure signed locally"
            ),
        }
    if study_audit.get("status") == "incomplete":
        blockers.append("STUDY_DESIGN_INCOMPLETE")
        next_actions.append({
            "owner": "human",
            "gate": "G2",
            "command": (
                "fill study-design.json and rerun "
                "python -m research_agent design audit --design <study-design.json> --strict"
            ),
        })

    writing_status = str(writing.get("status") or "") if writing else ""
    writing_blockers = list(writing.get("blockers") or []) if writing else []
    project_root = _project_root_for_run(root)
    if writing_status == "blocked":
        blockers.append("WRITING_AUDIT_BLOCKED")
        next_actions.append({
            "owner": "human",
            "gate": "S8-S12",
            "command": (
                "fix the draft, bind the current writing pack, then rerun "
                "python -m research_agent writing audit --project %s --run-id %s "
                "--draft <draft.md>" % (project_root, run_id)
                if project_root
                else (
                    "inspect manuscript-audit.json/writing-audit.json in this runtime "
                    "job; runtime job dirs are not project roots, so fix the draft in "
                    "the owning project and rerun writing audit there"
                )
            ),
        })
    elif paper and not writing:
        next_actions.append({
            "owner": "human",
            "gate": "S8-S12",
            "command": (
                "python -m research_agent writing pack --project %s --run-id %s "
                "--experiment-id <EXP-ID>" % (project_root, run_id)
                if project_root
                else (
                    "build the writing pack in the owning project; this runtime job "
                    "dir is not a project root"
                )
            ),
        })
    if not writing and (paper or primary_experiment):
        blockers.append("WRITING_NOT_STARTED")
        next_actions.append({
            "owner": "human",
            "gate": "S8-S12",
            "command": (
                "build a writing pack, draft, then run writing audit; "
                "submission remains blocked until audit is not blocked"
            ),
        })
    if demo.get("fixture_mode") or task.get("fixture_mode"):
        blockers.append("FIXTURE_ONLY")

    nodes = [
        {
            "id": "S1",
            "label": "文献与 span",
            "status": "partial" if span_count else "missing",
            "artifact": "literature.json",
            "metrics": {
                "sources": (coverage.get("sources_found") if isinstance(coverage, dict) else None)
                or len(((demo.get("modules") or {}).get("literature") or {}).get("hits") or []),
                "spans": span_count,
                "gaps": len(coverage.get("gaps") or []) if isinstance(coverage, dict) else 0,
            },
        },
        {
            "id": "S2-S3",
            "label": "假设候选",
            "status": (
                "needs_human" if candidates and idea_status in ("candidates_need_human", "needs_human")
                else "done" if candidates else "missing"
            ),
            "artifact": "idea.json",
            "idea_ids": [str(item.get("idea_id")) for item in candidates],
            "shortlist_selection": ((idea.get("shortlist") or {}).get("selection") or ""),
        },
        {
            "id": "S4",
            "label": "实验设计",
            "status": (
                "blocked" if study_audit.get("status") == "incomplete"
                else design_status if design_status in ("missing", "needs_human", "blocked")
                else "done"
            ),
            "artifact": "experiment.json",
            "idea_id": str(experiment.get("idea_id") or ""),
            "study_design_status": str(study_audit.get("status") or "missing"),
            "ccfa_level": str((study_audit.get("ccfa") or {}).get("level") or ""),
            "study_design_blockers": list(study_audit.get("blockers") or [])[:5],
            "missing_fields": [
                key for key in ("baseline", "primary_metric", "budget")
                if str(experiment.get(key) or "") in ("", "待人工补全")
            ],
        },
        {
            "id": "S5",
            "label": "运行与 EA",
            "status": (
                "done" if experiment_claim_signed
                else "needs_human" if primary_experiment
                else "needs_human" if capsule and claim_draft and "CLAIM_UNSIGNED" in blockers
                else "done" if capsule and str(capsule.get("status") or "") == "completed"
                else "missing"
            ),
            "artifact": (
                "experiments/%s/experiment-spec.json" % primary_experiment.get("experiment_id")
                if primary_experiment else "run/run-capsule.json" if capsule else ""
            ),
            "experiment_id": str(primary_experiment.get("experiment_id") or ""),
            "run_id": str(
                capsule.get("run_id")
                or primary_experiment.get("run_id")
                or run_id
            ),
            "claim_status": (
                str(experiment_stages.get("claim") or "missing")
                if primary_experiment
                else "signed" if claim_signed
                else "draft_needs_human" if claim_draft
                else "missing"
            ),
        },
        {
            "id": "S6",
            "label": "结果图",
            "status": "missing" if not figure else ("partial" if figure.get("schematic") else "done"),
            "artifact": "figure.manifest.json" if figure else "",
            "kind": str(figure.get("kind") or ""),
            "schematic": bool(figure.get("schematic")),
        },
        {
            "id": "S8-S12",
            "label": "写作槽位",
            "status": (
                "blocked" if writing_status == "blocked"
                else "needs_human" if writing or pending_slots
                else "missing" if not paper
                else "done"
            ),
            "artifact": (
                "manuscript-audit.json" if manuscript_audit
                else "writing-audit.json" if writing_audit
                else "paper.json" if paper else ""
            ),
            "paper_status": str(paper.get("status") or ""),
            "writing_status": writing_status,
            "writing_blockers": writing_blockers[:8],
            "submission_ready": bool(writing.get("submission_ready")),
            "slots": len(slots),
            "pending_slots": len(pending_slots),
        },
        {
            "id": "S13",
            "label": "闭包",
            "status": (
                "done" if experiment_signed
                else "ready" if experiment_closure == "ready_for_signature"
                else "blocked" if primary_experiment
                else "missing" if not closure
                else "done" if signature
                else "ready" if str(closure.get("status") or "") == "ready"
                else "blocked"
            ),
            "artifact": (
                "experiments/%s/experiment-closure/closure-report.json"
                % primary_experiment.get("experiment_id")
                if primary_experiment else "closure-report.json" if closure else ""
            ),
            "experiment_id": str(primary_experiment.get("experiment_id") or ""),
            "unresolved": list(closure.get("unresolved") or []),
        },
        {
            "id": "META",
            "label": "自进化",
            "status": "partial" if observation_id or active_policy_id else "not_run",
            "observation_id": observation_id,
            "active_policy_id": active_policy_id,
            "artifact": "",
        },
    ]

    studies_dir = root.parent.parent / "studies"
    scope_run = root.name if root.parent.name == "runs" else run_id
    if studies_dir.is_dir() and not any(
        "study claim" in str(item.get("command")) for item in next_actions
    ):
        for study_dir in sorted(path for path in studies_dir.iterdir() if path.is_dir()):
            report = _load(study_dir, "closure-report.json")
            checks = {
                str(item.get("id")): str(item.get("status"))
                for item in report.get("checks") or []
            }
            if (
                checks.get("has_decidable_comparison") != "pass"
                or checks.get("claim.present") != "fail"
            ):
                continue
            origin = _load(study_dir, "study-origin.json")
            idea_id = str(origin.get("idea_id") or study_dir.name.replace("STUDY-", ""))
            if study_dir.name != "STUDY-%s" % idea_id:
                # Replication environments are evidence, not separate claim anchors.
                continue
            next_actions.append({
                "owner": "human",
                "gate": "S5b",
                "command": (
                    "python -m research_agent study claim --study-dir %s --statement \"...\" "
                    "--human-reason \"...\" --scope %s/%s" % (study_dir, scope_run, idea_id)
                ),
            })

    return {
        "schema_version": SCHEMA,
        "run_id": run_id,
        "generated_at": _now(),
        "route": str((task.get("plan") or {}).get("route") or ""),
        "task_status": str(task.get("status") or ""),
        "flow_mode": str(demo.get("flow_mode") or ""),
        "stopped_at": str(demo.get("stopped_at") or ""),
        "nodes": nodes,
        "experiments": experiment_links,
        "blockers": blockers,
        "next_actions": next_actions,
        "human_gates": [gates[key] for key in gates if key in ("G1", "G2", "G5")],
        "claim_registry": {
            "entries": len(registry.get("entries") or []),
            "coverage": (registry.get("coverage") or {}),
        },
        "writing": {
            "status": writing_status,
            "submission_ready": bool(writing.get("submission_ready")),
            "blockers": writing_blockers[:8],
            "external_gates": {
                name: {
                    "status": str((writing.get(name) or {}).get("status") or ""),
                    "issue_count": len((writing.get(name) or {}).get("issues") or []),
                }
                for name in ("external_lint", "external_consistency")
                if isinstance(writing.get(name), dict)
            },
        } if writing else {},
        "artifact_refs": {
            name: str(root / name)
            for name in (
                "literature.json", "idea.json", "experiment.json", "figure.manifest.json",
                "paper.json", "claim-registry.json", "closure-report.json",
            )
            if (root / name).is_file()
        },
        "boundary": BOUNDARY,
    }


def write_loop_capsule(
    output_dir: Path,
    observation_id: str = "",
    active_policy_id: str = "",
) -> Path:
    root = Path(output_dir)
    capsule = build_loop_capsule(root, observation_id, active_policy_id)
    path = root / "loop-capsule.json"
    write_json_atomic(path, capsule)
    return path


def update_loop_capsule_meta(
    output_dir: Path,
    observation_id: str = "",
    active_policy_id: str = "",
) -> Path:
    root = Path(output_dir)
    path = root / "loop-capsule.json"
    capsule = _load(root, "loop-capsule.json")
    if not capsule:
        return write_loop_capsule(root, observation_id, active_policy_id)
    nodes = [
        item for item in (capsule.get("nodes") or [])
        if isinstance(item, dict)
    ]
    for item in nodes:
        if item.get("id") == "META":
            item["observation_id"] = observation_id
            item["active_policy_id"] = active_policy_id
            item["status"] = "partial" if observation_id or active_policy_id else "not_run"
    capsule["nodes"] = nodes
    capsule["updated_at"] = _now()
    write_json_atomic(path, capsule)
    return path
