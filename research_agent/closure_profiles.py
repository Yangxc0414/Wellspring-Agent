"""Shared vocabulary for the three human-signed closure profiles.

Canonical run closure binds a completed RunCapsule, Event Archive and a
human-signed Claim (``closure.py``). Local experiment closure binds a generated
experiment package, local execution evidence and a human-signed experiment
claim (``experiment_closure.py``). The artifacts differ, but both are
structural, human-signed and never submission-ready.
"""

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import read_json

CANONICAL_RUN = "canonical_run"
LOCAL_EXPERIMENT = "local_experiment"
SEARCH_STUDY = "search_study"
SUBMISSION_READY = False
_STATUS_BOUNDARY = (
    "Read-only closure status; it never signs, publishes, approves or edits artifacts. "
    "Canonical and local experiment profiles are not interchangeable."
)
_CHAIN_BOUNDARY = (
    "Chain entries report presence and SHA-256 identity only; they do not prove correctness, "
    "semantic entailment, peer review or submission readiness."
)
_LINEAGE_BOUNDARY = (
    "Read-only lineage verification; fresh means bytes match the recorded hashes, not that the "
    "experiment is correct, that closure passed or that a claim was signed. Nothing is rebuilt."
)

PROFILES: List[Dict[str, Any]] = [
    {
        "id": CANONICAL_RUN,
        "applies_to": "S5 pipeline runs with RunCapsule + EA + human-signed Claim",
        "entrypoint": "closure check / closure sign / closure publish",
        "report_schema": "closure-report",
        "ready_status": "ready",
        "signature": "closure sign (human only)",
        "artifacts": "run-capsule.json, ea.json, claim.json, closure-report.json",
        "boundary": "structural closure only; not peer review; no auto-submission",
    },
    {
        "id": LOCAL_EXPERIMENT,
        "applies_to": "generated local experiment packages under experiments/<EXP-ID>",
        "entrypoint": "experiment closure / experiment sign",
        "report_schema": "experiment-closure-0.1",
        "ready_status": "ready_for_human_signature",
        "signature": "experiment sign (human only)",
        "artifacts": "experiment-spec.json, execution.json, experiment-evidence.json, claim.json",
        "boundary": "local experiment profile; not RunCapsule/EA; not peer review",
    },
    {
        "id": SEARCH_STUDY,
        "applies_to": "search-study packages under studies/<dataset> produced by `study search`",
        "entrypoint": "study closure / study sign / study lineage",
        "report_schema": "search-study-closure-0.1",
        "ready_status": "ready_for_human_signature",
        "signature": "study sign (human only)",
        "artifacts": "study-spec.json, study.json, study-evidence.json, claim.json, closure-report.json, signature.json",
        "boundary": (
            "structural closure of a study over pipeline configurations; not RunCapsule/EA; "
            "an underpowered study cannot be closed as a finding; not peer review"
        ),
    },
]

PROFILE_IDS = tuple(item["id"] for item in PROFILES)


def describe_profiles() -> Dict[str, Any]:
    return {
        "schema_version": "closure-profiles-0.1",
        "profiles": [dict(item) for item in PROFILES],
        "submission_ready": SUBMISSION_READY,
        "rule": (
            "choose by artifact type, never upgrade one profile into the other; "
            "all three need a human signature and none exports a submission"
        ),
    }


def _load(path: Path) -> Dict[str, Any]:
    try:
        value = read_json(path)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _claim_candidates(root: Path, run: Path) -> List[Path]:
    candidates = [
        run / "claim" / "claim.json",
        run / "claim.json",
        run / "run" / "claim" / "claim.json",
        run / "run" / "claim.json",
    ]
    claims = root / "claims"
    if claims.is_dir():
        candidates.extend(sorted(claims.glob("*.json")))
    return candidates


def claim_candidates(root: Path, run: Path) -> List[Path]:
    """Public alias for the single-point list of where a run's claim may live.

    verdict_ledger binds claim verdict rows to the same file this module reads;
    the candidate list must have exactly one definition.
    """
    return _claim_candidates(root, run)


def _signed_claim_exists(project: Path, run: Path) -> bool:
    for path in _claim_candidates(project, run):
        if path.is_file() and str(_load(path).get("status") or "") in ("supported", "approved"):
            return True
    return False


def _study_verdict(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Decidable / undecidable / unavailable per comparison, from the same rule the claim uses."""
    from .study_claims import comparison_verdicts

    try:
        rows = comparison_verdicts(evidence or {})
    except (KeyError, TypeError, ValueError):
        # A malformed evidence package must still appear in the inventory, just without a verdict.
        return {"available": False, "comparisons": [], "counts": {}}
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    detail = evidence.get("comparison") if isinstance(evidence.get("comparison"), dict) else {}

    def _planning(name: str):
        """How many seeds the same design would need at this effect size, when the study says so."""
        item = detail.get(name)
        return item.get("seeds_for_80pct") if isinstance(item, dict) else None

    return {
        "available": True,
        "comparisons": [
            {
                "comparison": row["comparison"],
                "state": row["state"],
                "mean_diff": row["mean_diff"],
                "ci95": row["ci95"],
                "reason": row["reason"],
                # An undecidable row is a result, but the reader still needs the next step.
                "seeds_for_80pct": _planning(str(row["comparison"])),
            }
            for row in rows
        ],
        "counts": counts,
        "decidable": counts.get("positive", 0) + counts.get("negative", 0),
        "undecidable": counts.get("undecidable", 0),
    }


def _claim_draft_prompt(root: Path, run_dir: Path) -> Optional[Dict[str, Any]]:
    """What the human would sign and the exact command; showing it signs nothing.

    Paths are project-relative because this inventory also travels over HTTP. The statement and
    human reason stay as placeholders: the draft is the system's wording, and the human has to
    retype or edit it for the signature to mean anything.
    """
    draft = _load(run_dir / "claim-draft.json")
    if not draft:
        return None
    proposal = draft.get("assertion_proposal")
    proposal = proposal if isinstance(proposal, dict) else {}
    scope = str(draft.get("scope") or "")
    assertion = str(proposal.get("assertion_argument") or "")
    command = [
        "python -m research_agent run claim",
        "--capsule %s" % _relative(root, run_dir / "run-capsule.json"),
        "--ea %s" % _relative(root, run_dir / "ea.json"),
        '--statement "<confirmed statement>"',
        '--human-reason "<why you accept this evidence>"',
    ]
    if scope:
        command.append("--scope %s" % scope)
    if assertion:
        command.append('--assertion "%s"' % assertion)
    command.append("--output-dir %s" % _relative(root, run_dir / "claim"))
    return {
        "status": str(draft.get("status") or ""),
        "statement": str(draft.get("statement") or ""),
        "scope": scope,
        "assertion": assertion,
        "reading": str(proposal.get("reading") or ""),
        "command": " ".join(command),
        "cwd": "project root",
        "boundary": "a draft shown to a human; rendering or copying it signs nothing",
    }


def _replication_summary(root: Path, studies: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """How many datasets actually decide each comparison — the anecdote check.

    Kept read-only and path-free: the page may show which datasets agree, never where they live.
    """
    if len(studies) < 2:
        return None
    from .study_replication import build_replication_report

    report = build_replication_report(root / "studies", siblings=True)
    return {
        "packages": report["packages"],
        # The whole-scope coverage table lives with the scan that knows every root, so the page
        # reads the same denominators the CLI reports instead of a second, narrower projection.
        "chain_layers": report.get("chain_layers"),
        "status_counts": report["status_counts"],
        "warnings": report["warnings"],
        # The over-claim detector is the part a human reader acts on, so it travels with the
        # inventory instead of staying inside the report file.
        "overturned": report["overturned"],
        "power_ladders": len(report["power_ladders"]),
        # The headline cost-of-deciding-early number, not the per-ladder detail.
        "power_audit": (report.get("power_audit") or {}),
        "groups": [
            {
                "design_key": group["design_key"],
                "datasets": group["datasets"],
                "seed_counts": group["seed_counts"],
                "comparisons": {
                    name: {
                        key: result[key]
                        for key in ("status", "direction", "decided_in", "generalizes")
                    }
                    for name, result in group["comparisons"].items()
                },
            }
            for group in report["replicated"]
        ],
        "unreplicated": [
            {
                "design_key": item["design_key"],
                "datasets": item["datasets"],
                "reason": item["reason"],
            }
            for item in report["unreplicated"]
        ],
        "boundary": report["boundary"],
    }


def detect_project_profiles(project: Path, limit: int = 50) -> Dict[str, Any]:
    """Read-only inventory of closure artifacts already present in a project."""
    from .study_claims import origin_state

    root = Path(project).resolve()
    cap = max(1, min(int(limit), 200))
    canonical: List[Dict[str, Any]] = []
    runs = root / "runs"
    if runs.is_dir():
        for run in sorted(runs.glob("RUN-*"))[-cap:]:
            if not run.is_dir():
                continue
            capsule = run / "run" / "run-capsule.json"
            if not capsule.is_file():
                continue
            run_dir = run / "run"
            closure = _load(run_dir / "closure-report.json") or _load(run / "closure" / "closure-report.json")
            signed = _signed_claim_exists(root, run)
            signature = _load(run / "closure-signature" / "signature.json")
            has_signature = bool(signature)
            delegated = str(signature.get("human_reason") or "").startswith("[delegated:")
            panel = _load(run / "support-panel.json")
            panel_status = str(panel.get("status") or "missing")
            demo = _load(run / "demo.json")
            study = ((demo.get("modules") or {}).get("study_design") or {})
            study_audit = study.get("audit") if isinstance(study, dict) else {}
            study_audit = study_audit if isinstance(study_audit, dict) else {}
            closure_status = str(closure.get("status") or "missing")
            if has_signature and closure_status == "ready":
                closure_status = "signed"
            if str(study_audit.get("status") or "") == "incomplete":
                next_action = "fix study design; G2 is blocked"
            elif has_signature:
                next_action = (
                    "closed locally; verify the sealed bundle"
                    if (root / "bundles" / run.name).is_dir()
                    else "signature present; publish a local bundle"
                )
            elif not signed:
                next_action = "claim sign (human only)"
            elif panel_status in ("blocked", "needs_human"):
                next_action = "support adjudication (human only)"
            elif closure.get("status") == "ready":
                next_action = "closure sign (human only)"
            else:
                next_action = "closure check"
            canonical.append(
                {
                    "profile": CANONICAL_RUN,
                    "run_id": run.name,
                    "status": str(_load(capsule).get("status") or "unknown"),
                    "has_ea": (run_dir / "ea.json").is_file(),
                    "has_claim_draft": (run_dir / "claim-draft.json").is_file(),
                    "has_signed_claim": signed,
                    "has_signature": has_signature,
                    # Delegated and human signatures are both local HMAC; the marker says who
                    # authorized the act, not what cryptography was used.
                    "delegated": delegated,
                    "study_design": (
                        {
                            "status": str(study_audit.get("status") or "missing"),
                            "ccfa_level": str((study_audit.get("ccfa") or {}).get("level") or ""),
                            "blockers": list(study_audit.get("blockers") or [])[:5],
                        }
                        if study_audit else None
                    ),
                    "closure_status": closure_status,
                    "support_panel_status": panel_status,
                    # Once signed, "what you would sign" is noise; before that it is the next step.
                    "claim_draft": None if signed else _claim_draft_prompt(root, run_dir),
                    "next": next_action,
                }
            )
    experiments: List[Dict[str, Any]] = []
    packages = root / "experiments"
    if packages.is_dir():
        for package in sorted(packages.glob("EXP-*"))[-cap:]:
            if not package.is_dir() or not (package / "experiment-spec.json").is_file():
                continue
            closure = _load(package / "experiment-closure" / "closure-report.json")
            spec = _load(package / "experiment-spec.json")
            run_id = str(spec.get("run_id") or "")
            panel_path = root / "runs" / run_id / "support-panel.json" if run_id else package / "support-panel.json"
            panel = _load(panel_path)
            panel_status = str(panel.get("status") or "missing")
            if panel_status in ("blocked", "needs_human"):
                next_action = "support adjudication (human only)"
            elif closure.get("status") == "ready_for_human_signature":
                next_action = "experiment sign (human only)"
            else:
                next_action = "experiment closure"
            experiments.append(
                {
                    "profile": LOCAL_EXPERIMENT,
                    "experiment_id": package.name,
                    "closure_status": str(closure.get("status") or "missing"),
                    "support_panel_status": panel_status,
                    "signed": (package / "experiment-closure" / "signature.json").is_file(),
                    "next": next_action,
                }
            )
    from .search_lab import code_fingerprint
    from .study_integrity import integrity_layers, package_integrity

    studies: List[Dict[str, Any]] = []
    study_root = root / "studies"
    stamp = code_fingerprint()
    if study_root.is_dir():
        for package in sorted(p for p in study_root.iterdir() if p.is_dir())[-cap:]:
            if not (package / "study-spec.json").is_file():
                continue
            closure = _load(package / "closure-report.json")
            evidence = _load(package / "study-evidence.json")
            spec = _load(package / "study-spec.json")
            origin = _load(package / "study-origin.json")
            # Before a closure report exists the spec is the only truthful source of the dataset;
            # falling back to the directory name would label a wine study as "STUDY-IDEA-02".
            dataset_label = str(
                (closure or {}).get("dataset")
                or (spec or {}).get("dataset")
                or evidence.get("dataset")
                or package.name
            )
            origin_binding = origin_state(package)
            signed = (package / "signature.json").is_file()
            # The report on disk predates the signature; reporting its raw status here would
            # show a signed study as still awaiting one.
            closure_status = str(closure.get("status") or "missing")
            if signed and closure_status == "ready_for_human_signature":
                closure_status = "signed"
            if signed:
                next_action = "closed; report is signed"
            elif evidence.get("underpowered"):
                next_action = "not closable as a finding: add seeds or narrow the claim"
            elif closure_status == "ready_for_human_signature":
                next_action = "study sign (human only)"
            else:
                next_action = "study closure"
            studies.append(
                {
                    "profile": SEARCH_STUDY,
                    # A project-relative path: the inventory is read over HTTP too, and an absolute
                    # local path there would leak the user's directory layout with no benefit.
                    "study_dir": package.relative_to(root).as_posix(),
                    "dataset": dataset_label,
                    "closure_status": closure_status,
                    "underpowered": bool(evidence.get("underpowered")),
                    "has_signed_claim": (package / "claim.json").is_file(),
                    "signed": signed,
                    "verdict": _study_verdict(evidence),
                    "integrity": package_integrity(package, current_fingerprint=stamp),
                    "origin": origin_binding["state"],
                    "idea_id": origin_binding.get("idea_id", ""),
                    "idea_title": str((origin or {}).get("idea_title") or ""),
                    "falsification": origin_binding.get("falsification", ""),
                    "next": next_action,
                }
            )
    return {
        "schema_version": "closure-profiles-0.7",
        "project_dir": str(root),
        "canonical_run": canonical,
        "local_experiment": experiments,
        "search_study": studies,
        "replication": _replication_summary(root, studies),
        "study_integrity_layers": integrity_layers(studies),
        "present_profiles": [
            item
            for item, values in (
                (CANONICAL_RUN, canonical),
                (LOCAL_EXPERIMENT, experiments),
                (SEARCH_STUDY, studies),
            )
            if values
        ],
        "submission_ready": SUBMISSION_READY,
        "guidance": (
            "RunCapsule/EA runs use canonical_run closure; generated CSV experiment packages use "
            "local_experiment closure; search-study packages use search_study closure. Do not "
            "present one profile's report as another's, and an underpowered study cannot be "
            "closed as a finding at all."
        ),
    }

def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _chain_entry(
    root: Path,
    path: Path,
    role: str,
    *,
    required: bool = True,
    status: str = "",
    meta: Dict[str, Any] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "role": role,
        "path": _relative(root, path),
        "required": required,
        "present": path.is_file(),
    }
    if entry["present"]:
        entry["sha256"] = _sha256_file(path)
        if status:
            entry["status"] = status
        if meta:
            entry["meta"] = meta
    return entry


def _chain_fingerprint(chain: List[Dict[str, Any]]) -> str:
    import json

    payload = [
        [item["role"], item["path"], item.get("sha256", ""), item["present"]] for item in chain
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _run_claim_path(root: Path, run: Path) -> Path:
    for candidate in _claim_candidates(root, run):
        if candidate.is_file():
            return candidate
    return run / "claim" / "claim.json"


def _canonical_chain(root: Path, run: Path) -> List[Dict[str, Any]]:
    capsule = run / "run" / "run-capsule.json"
    report = run / "run" / "closure-report.json"
    if not report.is_file():
        report = run / "closure" / "closure-report.json"
    signature = run / "closure" / "signature.json"
    if not signature.is_file():
        signature = run / "run" / "closure-signature.json"
    claim_path = _run_claim_path(root, run)
    claim = _load(claim_path)
    pack_path = run / "writing-pack.json"
    pack = _load(pack_path)
    audit_path = run / "writing-audit.json"
    audit = _load(audit_path)
    panel_path = run / "support-panel.json"
    panel = _load(panel_path)
    claim_meta = {"status": str(claim.get("status") or "missing")}
    if claim_path.parent == root / "claims":
        claim_meta["scope"] = "project/claims; verify it belongs to this run"
    chain = [
        _chain_entry(root, capsule, "run_capsule", status=str(_load(capsule).get("status") or "missing")),
        _chain_entry(root, run / "run" / "ea.json", "event_archive", status="present"),
        _chain_entry(root, claim_path, "claim", status=claim_meta["status"], meta=claim_meta),
        _chain_entry(root, report, "closure_report", status=str(_load(report).get("status") or "missing")),
        _chain_entry(root, signature, "closure_signature"),
        _chain_entry(
            root,
            pack_path,
            "writing_pack",
            required=False,
            meta={
                "pack_id": str(pack.get("pack_id") or ""),
                "pack_sha256": str(pack.get("pack_sha256") or ""),
            },
        ),
        _chain_entry(
            root,
            audit_path,
            "writing_audit",
            required=False,
            status=str(audit.get("status") or "missing"),
            meta={"pack_id": str(audit.get("pack_id") or "")},
        ),
        _chain_entry(
            root,
            panel_path,
            "support_panel",
            required=False,
            status=str(panel.get("status") or "missing"),
            meta={
                "panel_fingerprint": str(panel.get("panel_fingerprint") or ""),
                "pending_human": len(panel.get("pending_human") or []),
            },
        ),
        _chain_entry(
            root,
            run / "result-figure.manifest.json",
            "result_figure_manifest",
            required=False,
        ),
    ]
    return chain


def _experiment_chain(root: Path, package: Path) -> List[Dict[str, Any]]:
    spec = _load(package / "experiment-spec.json")
    approval = _load(package / "execution-approval.json")
    execution = _load(package / "execution.json")
    evidence = _load(package / "experiment-evidence.json")
    claim = _load(package / "claim.json")
    report = _load(package / "experiment-closure" / "closure-report.json")
    run_id = str(spec.get("run_id") or "")
    panel_path = root / "runs" / run_id / "support-panel.json" if run_id else package / "support-panel.json"
    panel = _load(panel_path)
    table_csv = package / "outputs" / "results-table.csv"
    table = table_csv if table_csv.is_file() else package / "outputs" / "results-table.md"
    return [
        _chain_entry(
            root,
            package / "experiment-spec.json",
            "experiment_spec",
            status=str(spec.get("status") or "present"),
        ),
        _chain_entry(
            root,
            package / "execution-approval.json",
            "execution_approval",
            meta={
                "data_sha256": str(approval.get("data_sha256") or ""),
                "spec_sha256": str(approval.get("spec_sha256") or ""),
                "code_sha256": str(approval.get("code_sha256") or ""),
            },
        ),
        _chain_entry(
            root,
            package / "execution.json",
            "execution",
            status=str(execution.get("status") or "missing"),
            meta={"dry_run": bool(execution.get("dry_run"))},
        ),
        _chain_entry(
            root,
            package / "experiment-evidence.json",
            "experiment_evidence",
            status=str(evidence.get("status") or "missing"),
        ),
        _chain_entry(
            root,
            package / "claim.json",
            "claim",
            status=str(claim.get("status") or "missing"),
        ),
        _chain_entry(root, table, "results_table"),
        _chain_entry(
            root,
            panel_path,
            "support_panel",
            required=False,
            status=str(panel.get("status") or "missing"),
            meta={
                "panel_fingerprint": str(panel.get("panel_fingerprint") or ""),
                "pending_human": len(panel.get("pending_human") or []),
            },
        ),
        _chain_entry(
            root,
            package / "experiment-closure" / "closure-report.json",
            "closure_report",
            status=str(report.get("status") or "missing"),
        ),
        _chain_entry(root, package / "experiment-closure" / "signature.json", "closure_signature"),
    ]


def lineage_status(project: Path, *, experiment_id: str) -> Dict[str, Any]:
    """Read-only re-hash of an experiment lineage manifest; never rebuilds it."""
    root = Path(project).resolve()
    package = root / "experiments" / str(experiment_id).strip()
    path = package / "experiment-lineage" / "lineage.json"
    lineage = _load(path)
    nodes = list(lineage.get("nodes") or [])
    if not path.is_file() or not nodes:
        return {
            "schema_version": "lineage-status-0.1",
            "project_dir": str(root),
            "profile": LOCAL_EXPERIMENT,
            "experiment_id": experiment_id,
            "status": "missing",
            "lineage": _relative(root, path),
            "checks": [],
            "stale": [],
            "node_count": 0,
            "next_action": "experiment lineage (CLI, after closure)",
            "submission_ready": SUBMISSION_READY,
            "boundary": _LINEAGE_BOUNDARY,
        }
    checks: List[Dict[str, Any]] = []
    stale: List[str] = []
    for item in nodes:
        node_path = Path(str(item.get("path") or ""))
        if not node_path.is_absolute():
            node_path = root / node_path
        reason = ""
        try:
            node_path.resolve().relative_to(root)
            inside = True
        except ValueError:
            inside = False
        if not inside:
            ok = False
            reason = "outside project"
        else:
            ok = node_path.is_file() and _sha256_file(node_path) == str(
                item.get("sha256") or ""
            )
            if not ok:
                reason = "missing" if not node_path.is_file() else "sha256 mismatch"
        entry: Dict[str, Any] = {
            "node_id": item.get("node_id"),
            "status": "fresh" if ok else "stale",
        }
        if reason:
            entry["reason"] = reason
        checks.append(entry)
        if not ok:
            stale.append(str(item.get("node_id")))
    return {
        "schema_version": "lineage-status-0.1",
        "project_dir": str(root),
        "profile": LOCAL_EXPERIMENT,
        "experiment_id": experiment_id,
        "status": "fresh" if not stale else "stale",
        "lineage": _relative(root, path),
        "checks": checks,
        "stale": stale,
        "node_count": len(nodes),
        "next_action": (
            "none (lineage matches recorded hashes)"
            if not stale
            else "experiment closure (CLI; rebuild lineage after resolving stale inputs)"
        ),
        "submission_ready": SUBMISSION_READY,
        "boundary": _LINEAGE_BOUNDARY,
    }


def closure_status(
    project: Path,
    *,
    run_id: str = "",
    experiment_id: str = "",
) -> Dict[str, Any]:
    """Read-only closure status for one run/experiment or the whole project."""
    root = Path(project).resolve()
    if not run_id and not experiment_id:
        return {
            "schema_version": "closure-status-0.2",
            "project_dir": str(root),
            "inventory": detect_project_profiles(root),
            "submission_ready": SUBMISSION_READY,
            "boundary": _STATUS_BOUNDARY,
        }
    if experiment_id:
        package = root / "experiments" / str(experiment_id).strip()
        report = _load(package / "experiment-closure" / "closure-report.json")
        signature = _load(package / "experiment-closure" / "signature.json")
        claim = _load(package / "claim.json")
        spec = _load(package / "experiment-spec.json")
        run_id = str(spec.get("run_id") or "")
        panel_path = root / "runs" / run_id / "support-panel.json" if run_id else package / "support-panel.json"
        panel = _load(panel_path)
        panel_status = str(panel.get("status") or "missing")
        status = str(report.get("status") or "missing")
        if signature:
            action = "complete (human-signed local closure)"
        elif panel_status in ("blocked", "needs_human"):
            action = "support adjudication (human only)"
        elif status == "ready_for_human_signature":
            action = "experiment sign (human only)"
        else:
            action = "experiment closure"
        chain = _experiment_chain(root, package)
        return {
            "schema_version": "closure-status-0.2",
            "project_dir": str(root),
            "profile": LOCAL_EXPERIMENT,
            "experiment_id": experiment_id,
            "status": status,
            "signed": bool(signature),
            "claim_status": str(claim.get("status") or "missing"),
            "checks": list(report.get("checks") or []),
            "blockers": list(report.get("blockers") or []),
            "support_panel_status": panel_status,
            "support_panel_pending_human": len(panel.get("pending_human") or []),
            "next_action": action,
            "submission_ready": SUBMISSION_READY,
            "chain": chain,
            "chain_complete": all(
                item["present"] for item in chain if item["required"]
            ),
            "chain_fingerprint": _chain_fingerprint(chain),
            "chain_boundary": _CHAIN_BOUNDARY,
            "boundary": _STATUS_BOUNDARY,
        }
    run = root / "runs" / str(run_id).strip()
    report = _load(run / "run" / "closure-report.json") or _load(
        run / "closure" / "closure-report.json"
    )
    signature = _load(run / "closure" / "signature.json") or _load(
        run / "run" / "closure-signature.json"
    )
    status = str(report.get("status") or "missing")
    claim_path = _run_claim_path(root, run)
    claim = _load(claim_path)
    claim_status = str(claim.get("status") or "missing")
    claim_signed = claim_status in ("supported", "approved")
    panel = _load(run / "support-panel.json")
    panel_status = str(panel.get("status") or "missing")
    if signature:
        action = "complete (human-signed canonical closure)"
    elif not claim_signed:
        action = "claim sign (human only)"
    elif panel_status in ("blocked", "needs_human"):
        action = "support adjudication (human only)"
    elif status == "ready":
        action = "closure sign (human only)"
    else:
        action = "closure check"
    chain = _canonical_chain(root, run)
    return {
        "schema_version": "closure-status-0.2",
        "project_dir": str(root),
        "profile": CANONICAL_RUN,
        "run_id": run_id,
        "status": status,
        "signed": bool(signature),
        "claim_status": claim_status,
        "claim_signed": claim_signed,
        "claim_path": _relative(root, claim_path),
        "support_panel_status": panel_status,
        "support_panel_pending_human": len(panel.get("pending_human") or []),
        "checks": list(report.get("checks") or []),
        "blockers": list(report.get("blockers") or []),
        "unresolved": list(report.get("unresolved") or []),
        "next_action": action,
        "submission_ready": SUBMISSION_READY,
        "chain": chain,
        "chain_complete": all(
            item["present"] for item in chain if item["required"]
        ),
        "chain_fingerprint": _chain_fingerprint(chain),
        "chain_boundary": _CHAIN_BOUNDARY,
        "boundary": _STATUS_BOUNDARY,
    }

