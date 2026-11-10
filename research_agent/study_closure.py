"""Search-study closure: the third human-signed profile.

A study that cannot be closed is a study whose conclusion can silently rot: the dataset,
seeds, budget or the search code changes and the earlier claim keeps being cited as if it
still followed from the evidence. This module binds spec -> study -> evidence -> claim ->
signature with hashes, and re-verifies them read-only, so a change upstream marks the chain
stale instead of passing unnoticed.

It stays consistent with the other two profiles: structural only, human signature required,
``submission_ready`` always false, and never exposed as an MCP/HTTP action.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .closure_profiles import SEARCH_STUDY, SUBMISSION_READY
from .search_lab import algorithm_canary, code_fingerprint, evidence_sha256_of, spec_sha256_of
from .study_claims import BASELINE_FILENAME, comparison_verdicts, origin_state
from .storage import now_iso, read_json, write_json_atomic

STUDY_CLOSURE_SCHEMA = "search-study-closure-0.1"
STUDY_LINEAGE_SCHEMA = "search-study-lineage-0.1"
STUDY_SIGNATURE_SCHEMA = "search-study-signature-0.1"

STUDY_CLOSURE_BOUNDARY = (
    "search-study closure is structural and human-signed: it proves the recorded artifacts "
    "are present and hash-bound, not that the study is correct, adequately powered, "
    "peer-reviewed or submittable. It is a third profile, not an upgrade of canonical_run "
    "or local_experiment."
)

CHAIN_FILES = (
    "study-spec.json",
    "study.json",
    "study-evidence.json",
    # The provenance sidecar is part of the chain: "which idea do these numbers answer" must go
    # stale together with the study it names, instead of drifting silently beside it.
    "study-origin.json",
    # The bound external opponent travels with the claim that cites it: re-encoding this file is
    # how a tampered baseline reaches closure as a stale chain instead of passing unseen.
    "tuned-baseline.json",
    # What was declared before the run is evidence too: without this entry a human could rewrite
    # the question, hypothesis or decision rule in study-preregistration.json and every hash in
    # the chain would still verify, because declared_design_sha256 only covers the design.
    "study-preregistration.json",
    "claim-draft.json",
    "claim.json",
    "closure-report.json",
    "signature.json",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    try:
        return read_json(path)
    except Exception:
        return None


def portable_study_dir(root: Path) -> str:
    """A study path a reader can act on, without shipping the machine that produced it.

    Every closure report ever written carried an absolute ``study_dir`` (measured: 190 of 190), so a
    bundle handed to a double-blind venue would disclose the author's home directory - exactly the
    item the artifact rubrics call out. Nothing is rewritten here for old packages: this affects new
    reports only, and no closure signature exists that binds those bytes today.
    """
    path = Path(root).resolve()
    try:
        relative = path.relative_to(Path(__file__).resolve().parents[1])
    except ValueError:
        return path.name
    return relative.as_posix()


def check_study_closure(
    study_dir: Path,
    *,
    output_dir: Optional[Path] = None,
    verify_repro: bool = False,
) -> Dict[str, Any]:
    """Verify one study package end to end; report ready or blocked, never sign.

    ``verify_repro`` re-executes this package's own controls under the code on disk. It is opt-in
    because that is the expensive part, and the blocker stays in force either way.
    """
    root = Path(study_dir).resolve()
    spec = _load(root / "study-spec.json") or {}
    study = _load(root / "study.json") or {}
    evidence = _load(root / "study-evidence.json") or {}
    claim = _load(root / "claim.json") or _load(root / "claim-draft.json") or {}
    claim_is_signed = (root / "claim.json").is_file()

    checks: List[Dict[str, str]] = []
    blockers: List[str] = []
    warnings: List[str] = []

    def add(
        check_id: str, ok: bool, detail: str, severity: str = "blocker", pass_detail: str = ""
    ) -> None:
        text = pass_detail if ok and pass_detail else detail
        checks.append({"id": check_id, "status": "pass" if ok else "fail", "detail": text})
        if ok:
            return
        (blockers if severity == "blocker" else warnings).append("%s: %s" % (check_id, text))

    add("spec.present", bool(spec), "study-spec.json")
    add("study.present", bool(study), "study.json")
    add("evidence.present", bool(evidence), "study-evidence.json")

    if spec:
        add(
            "study.bound_to_spec",
            str(study.get("study_sha256") or "") == str(spec.get("study_sha256") or ""),
            "study hash recorded in spec",
        )
        expected_code = str(spec.get("code_fingerprint") or "")
        code_matches = bool(expected_code) and code_fingerprint() == expected_code
        add(
            "code.unchanged",
            code_matches,
            "search code changed since the study ran; re-run before citing it"
            if expected_code
            else "study-spec.json has no code_fingerprint; predates code binding",
            severity="blocker" if expected_code else "warning",
            pass_detail="code fingerprint matches the study spec",
        )
        # Positive signal only, never a substitute for the blocker above: a fixed control set is
        # re-executed so a human can see whether the edit could have moved any number at all.
        # The canary covers one design on one dataset, so stability here does not prove the
        # package's own numbers reproduce — `--verify-repro` re-runs those instead.
        expected_canary = str(spec.get("algorithm_canary") or "")
        if expected_canary:
            stable = expected_canary == algorithm_canary()
            add(
                "code.canary_stable",
                stable,
                "the fixed canary controls still reproduce, so the code edit is unlikely to have "
                "moved these numbers — verify with `study closure --verify-repro`"
                if stable
                else "the fixed canary controls no longer reproduce: this code edit can move "
                "results, so re-run the study before citing it",
                severity="warning",
            )
        if verify_repro and not code_matches:
            from .search_lab import run_study

            recomputed = run_study(
                dataset=str(spec.get("dataset") or "iris"),
                seeds=[int(seed) for seed in (spec.get("seeds") or [])],
                budget=int(spec.get("budget") or 60),
                min_delta=float(spec.get("min_delta") or 0.005),
                design=spec.get("design") or None,
            )

            def outcomes(payload: Dict[str, Any]) -> Dict[str, Any]:
                # `study_sha256` covers the design and factor list, so a registry change would fail
                # a hash comparison without any number moving. Reproduction is about the numbers.
                return {
                    "cells": sorted(
                        "%s|%s|%s"
                        % (
                            cell.get("cell_id"),
                            cell.get("mean_improvement_per_evaluation"),
                            cell.get("mean_best_score"),
                        )
                        for cell in payload.get("cells") or []
                    ),
                    "comparison": {
                        str(key): [
                            value.get("mean_diff") if isinstance(value, dict) else None,
                            value.get("ci95_low") if isinstance(value, dict) else None,
                            value.get("ci95_high") if isinstance(value, dict) else None,
                        ]
                        for key, value in sorted(
                            (payload.get("comparison") or {}).items(), key=lambda item: str(item[0])
                        )
                    },
                }

            same = outcomes(recomputed) == outcomes(study)
            add(
                "code.reproduced",
                same,
                "re-running this package's own controls under the current code produced the same "
                "cell means and comparison intervals"
                if same
                else "re-running this package's own controls produced different numbers: the "
                "recorded results no longer follow from the code on disk",
                severity="warning" if same else "blocker",
            )
    if study:
        add(
            "study.self_hash",
            bool(study.get("study_sha256")),
            "study.json carries no self hash",
            pass_detail="study.json carries its own sha256",
        )
    if evidence:
        add(
            "evidence.bound_to_study",
            str(evidence.get("study_sha256") or "") == str(study.get("study_sha256") or ""),
            "evidence references the study hash",
        )
        add(
            "evidence.bound_to_spec",
            str(evidence.get("study_spec_sha256") or "") == spec_sha256_of(spec),
            "evidence references the canonical spec hash",
        )
        add(
            "evidence.self_hash",
            str(evidence.get("evidence_sha256") or "") == evidence_sha256_of(evidence),
            "evidence self hash does not match its own content",
            pass_detail="evidence self hash matches its own content",
        )
        add(
            "power.sufficient",
            not evidence.get("underpowered"),
            "study is underpowered: intervals are withheld, nothing is decidable",
            pass_detail="study has enough seeds for its comparisons",
        )
        # The same rule the claim uses, including the interaction: a study whose only decidable
        # finding is the interaction must not be signable yet uncloseable.
        from .study_claims import comparison_verdicts

        decidable = [
            row["comparison"]
            for row in comparison_verdicts(evidence)
            if row["state"] in ("positive", "negative")
        ]
        add(
            "has_decidable_comparison",
            bool(decidable),
            "no comparison or interaction excludes zero"
            if not decidable
            else "decidable: " + ", ".join(decidable),
        )

    environment = (spec or {}).get("environment") or {}
    add(
        "environment.recorded",
        bool(environment.get("python"))
        and float(environment.get("study_wall_seconds") or 0) > 0,
        "study-spec.json carries no environment block, so wall-clock and library versions "
        "cannot be reported: this package predates compute disclosure and is not blamed for it",
        severity="warning",
        pass_detail=(
            "environment disclosed: python %s, sklearn %s, %s logical CPUs, %s s wall-clock "
            "(not contention-corrected, and no judgement depends on it)"
            % (
                environment.get("python"),
                environment.get("sklearn"),
                environment.get("cpu_logical"),
                environment.get("study_wall_seconds"),
            )
        ),
    )

    from .metric_saturation import saturation_report

    saturation = saturation_report(study)
    if saturation.get("available"):
        add(
            "metric.headroom",
            not saturation.get("saturated"),
            str(saturation.get("detail") or ""),
            severity="warning",
            pass_detail="no run reaches a bounded metric ceiling",
        )

    add("claim.present", bool(claim), "claim-draft.json or claim.json")
    if study:
        from .study_preregistration import check_preregistration

        prereg = check_preregistration(root, study)
        add(
            "preregistration.present",
            bool(prereg.get("present")),
            str(prereg.get("reason") or ""),
            severity="warning",
            pass_detail="declared plan is present",
        )
        if prereg.get("present"):
            add(
                "preregistration.bound",
                bool(prereg.get("bound")),
                str(prereg.get("reason") or ""),
                pass_detail="declared plan is hash-bound to this study",
            )
    if claim:
        add(
            "claim.signed",
            claim_is_signed and str(claim.get("status")) in ("supported", "approved"),
            "claim is a draft; sign it through the human claim path",
            pass_detail="claim is signed",
        )
        add(
            "claim.bound_to_study",
            str(claim.get("verification", {}).get("study_sha256") or "")
            == str(study.get("study_sha256") or ""),
            "claim does not reference this study's hash",
            pass_detail="claim references this study's hash",
        )
        recorded_baseline = str(
            claim.get("verification", {}).get("baseline_sha256") or ""
        )
        if recorded_baseline:
            stored = root / BASELINE_FILENAME
            add(
                "baseline.bound",
                stored.is_file() and _sha(stored) == recorded_baseline,
                "the claim records baseline_sha256 but the package holds no %s with those bytes: "
                "the cited opponent is missing, was edited after the claim was drafted, or was "
                "re-serialised instead of copied" % BASELINE_FILENAME,
                pass_detail="the bound tuned baseline is in the package and hashes to the sha "
                "the claim records",
            )
        else:
            add(
                "baseline.bound",
                False,
                "no tuned baseline is bound: these numbers face only the reference cell inside "
                "the study, which is the weaker opponent an external reviewer asks about first",
                severity="warning",
            )
        # Who the opponent is must be decided before the results exist, so the declaration and
        # the binding are compared rather than each being believed on its own.
        prereg = _load(root / "study-preregistration.json") or {}
        declared = prereg.get("baseline") if isinstance(prereg.get("baseline"), dict) else None
        bound_file = BASELINE_FILENAME if recorded_baseline else ""
        if declared is None:
            add(
                "baseline.declared",
                False,
                "the pre-registration carries no baseline slot, so the opponent was picked when "
                "the claim was drafted rather than before the run",
                severity="warning",
            )
        elif str(declared.get("kind") or "") == "none" and recorded_baseline:
            add(
                "baseline.declared",
                False,
                "pre-registration declared baseline.kind=none but the claim binds %s: an "
                "opponent cannot appear for the first time after the results" % BASELINE_FILENAME,
            )
        elif str(declared.get("kind") or "") != "none" and str(
            declared.get("file") or ""
        ) != bound_file:
            add(
                "baseline.declared",
                False,
                "pre-registration declared opponent %r but the claim binds %r: bind the declared "
                "file or re-register the plan before signing"
                % (str(declared.get("file") or ""), bound_file),
            )
        else:
            add(
                "baseline.declared",
                True,
                "declared and bound opponents differ",
                pass_detail=(
                    "declared opponent %s (kind=%s) is what the claim binds"
                    % (bound_file or "none", declared.get("kind"))
                ),
            )
        assertions = claim.get("assertions") or []
        add(
            "claim.has_assertions",
            bool(assertions),
            "claim carries no numerical assertion",
            pass_detail="claim carries a numerical assertion",
        )
        add(
            "claim.assertions_verifiable",
            bool(assertions)
            and all(
                item.get("observed") is not None and item.get("status") == "verified"
                for item in assertions
            ),
            "every assertion needs an observed value from a decidable comparison",
            pass_detail="every assertion has a verified observed value",
        )
        # What the check really means: if the evidence contains comparisons that decide nothing,
        # the claim must name them. A study whose every comparison decided something needs no list.
        refused = [
            row["comparison"]
            for row in comparison_verdicts(evidence)
            if row["state"] in ("undecidable", "unavailable")
        ]
        add(
            "claim.records_undecidable",
            bool(claim.get("verification", {}).get("not_signable")) or not refused,
            "claim should list which comparisons were refused as underpowered: "
            + ", ".join(refused),
            severity="warning",
            pass_detail="claim records every refused comparison"
            if refused
            else "no refused comparisons to record",
        )
        add(
            "claim.carries_analogue_flag",
            any("analogue" in str(item) for item in claim.get("warnings") or []),
            "claim must keep the analogue boundary so it cannot be read as an agent study",
            pass_detail="claim keeps the analogue boundary",
        )

    # The idea these numbers were produced to test has to still be the one on file, whether or not
    # a claim exists yet: a re-run package is untrustworthy from the moment its sidecar diverges.
    provenance = origin_state(root)
    add(
        "origin.matches_study",
        provenance["state"] != "stale",
        "study-origin.json describes a different study than the package now holds, so any claim "
        "over these numbers would cite a design that no longer produced them",
        pass_detail="no stale study-origin.json",
    )
    add(
        "origin.present",
        provenance["state"] == "bound",
        "study-origin.json is stale: this package is no longer traceable to the idea that asked "
        "for it, so re-run `study from-idea` rather than citing the old binding"
        if provenance["state"] == "stale"
        else "no study-origin.json: this study is not traceable to an idea that asked for it",
        severity="warning",
        pass_detail="study-origin.json is bound to this study",
    )

    decidable_summary = {
        name: (item.get("mean_diff"), item.get("ci95_low"), item.get("ci95_high"))
        for name, item in (evidence.get("comparison") or {}).items()
    }
    status = "ready_for_human_signature" if not blockers else "blocked"
    report = {
        "schema_version": STUDY_CLOSURE_SCHEMA,
        "closure_profile": SEARCH_STUDY,
        "report_id": "REP-" + uuid.uuid4().hex[:10],
        "study_dir": portable_study_dir(root),
        "dataset": spec.get("dataset"),
        "seeds": spec.get("seeds"),
        "budget": spec.get("budget"),
        "status": status,
        "checks": checks,
        "unresolved": blockers,
        "warnings": warnings,
        "comparisons": decidable_summary,
        "artifact_refs": [name for name in CHAIN_FILES if (root / name).is_file()],
        "created_at": now_iso(),
        "submission_ready": SUBMISSION_READY,
        "boundary": STUDY_CLOSURE_BOUNDARY,
    }
    destination = Path(output_dir) if output_dir else root
    destination.mkdir(parents=True, exist_ok=True)
    write_json_atomic(destination / "closure-report.json", report)
    return report


def sign_study_closure(
    study_dir: Path,
    *,
    human_reason: str,
    signer: str = "",
) -> Dict[str, Any]:
    """Attach a human signature to a study closure report that is ready for it.

    Refuses when the report is blocked, when the reason is empty, or when the report no
    longer matches the closure on disk: the signature binds a specific report hash.
    """
    if not human_reason.strip():
        raise ValueError("human_reason is required to sign a study closure")
    root = Path(study_dir).resolve()
    report = _load(root / "closure-report.json")
    if not isinstance(report, dict):
        raise ValueError("run the study closure check before signing")
    if report.get("status") != "ready_for_human_signature":
        raise ValueError("closure is %s; only a ready report can be signed" % report.get("status"))
    rechecked = check_study_closure(root)
    if rechecked.get("status") != "ready_for_human_signature":
        raise ValueError("closure no longer verifies; re-run the check")
    signature = {
        "schema_version": STUDY_SIGNATURE_SCHEMA,
        "signature_id": "SIG-" + uuid.uuid4().hex[:10],
        "report_id": report.get("report_id"),
        "closure_profile": SEARCH_STUDY,
        "report_sha256": _sha(root / "closure-report.json"),
        "study_sha256": str((_load(root / "study.json") or {}).get("study_sha256", "")),
        "signer": signer.strip() or "human-signer",
        "human_reason": human_reason.strip(),
        "signed_at": now_iso(),
        "submission_ready": SUBMISSION_READY,
        "boundary": (
            "a human statement that this study's closure is accepted as recorded; it is not "
            "peer review, not a submission decision, and does not make an underpowered "
            "comparison decidable"
        ),
    }
    write_json_atomic(root / "signature.json", signature)
    return signature


def build_study_lineage(study_dir: Path) -> Dict[str, Any]:
    root = Path(study_dir).resolve()
    nodes: List[Dict[str, Any]] = []
    for name in CHAIN_FILES:
        path = root / name
        if not path.is_file():
            continue
        nodes.append(
            {
                "node_id": name.replace(".json", ""),
                "path": str(path),
                "sha256": _sha(path),
            }
        )
    lineage = {
        "schema_version": STUDY_LINEAGE_SCHEMA,
        "study_dir": portable_study_dir(root),
        "closure_profile": SEARCH_STUDY,
        "nodes": nodes,
        "created_at": now_iso(),
        "boundary": STUDY_CLOSURE_BOUNDARY,
    }
    write_json_atomic(root / "lineage.json", lineage)
    return lineage


def verify_study_lineage(study_dir: Path) -> Dict[str, Any]:
    root = Path(study_dir).resolve()
    lineage = _load(root / "lineage.json")
    if not isinstance(lineage, dict):
        raise ValueError("study lineage is missing; run the lineage build first")
    checks: List[Dict[str, str]] = []
    stale: List[str] = []
    for item in lineage.get("nodes") or []:
        path = Path(str(item.get("path") or ""))
        ok = path.is_file() and _sha(path) == str(item.get("sha256") or "")
        checks.append({"node_id": item.get("node_id"), "status": "fresh" if ok else "stale"})
        if not ok:
            stale.append(str(item.get("node_id")))
    return {
        "schema_version": "search-study-lineage-check-0.1",
        "status": "fresh" if not stale else "stale",
        "checks": checks,
        "stale": stale,
        "lineage": str(root / "lineage.json"),
        "closure_profile": SEARCH_STUDY,
        "boundary": (
            "fresh means the recorded bytes still match; it does not mean the study is "
            "correct, well powered or publishable, and nothing is rebuilt here"
        ),
    }
