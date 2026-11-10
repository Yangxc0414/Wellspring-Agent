"""Same-run empirical paper loop.

One research run can carry literature, synthesis, innovation review, a local
experiment package, verified evidence and a human-signed experiment claim. This
module checks that all pieces belong to the same run, then builds one writing
pack, drafts/reviews the article and re-runs experiment closure with the
manuscript. It never signs, approves, executes or submits anything.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .experiment_closure import check_experiment_closure
from .experiment_figures import ExperimentFigureError, build_result_figure, verify_result_figure
from .experiment_runner import ExperimentExecutionError, experiment_status
from .manuscript_review import run_manuscript_review
from .manuscript_writer import generate_manuscript
from .project import project_file, project_output_path, run_dir
from .storage import read_json, write_json_atomic
from .writing_audit import audit_manuscript
from .writing_pack import build_writing_pack, render_writing_pack

LOOP_SCHEMA = "empirical-paper-loop-0.1"
LOOP_BOUNDARY = (
    "Same-run empirical paper loop: it reads verified experiment evidence and a "
    "human-signed claim, drafts/reviews a manuscript, and re-checks closure. It "
    "never executes experiments, signs claims, approves gates or submits."
)


class EmpiricalLoopError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(path: Path) -> Dict[str, Any]:
    try:
        value = read_json(path)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _render_method_figure(
    project: Path,
    run_id: str,
    method_scene: str = "",
    method_template: str = "",
) -> tuple:
    if not method_scene and not method_template:
        return {}, ""
    from .figure_workflow import FigureWorkflowError, render_scene, render_template

    try:
        base = project / "runs" / run_id / "figures"
        index = 1
        while True:
            output = base / ("method-schematic" if index == 1 else "method-schematic-%d" % index)
            if not output.exists() or not any(output.iterdir()):
                break
            index += 1
        title = "Method overview (schematic)"
        description = "AstraDraw method/architecture schematic; not an experimental result."
        if method_template:
            result = render_template(
                method_template,
                output,
                title=title,
                description=description,
                output_name="method-schematic",
                formats=("svg",),
            )
        else:
            scene = project_file(project, method_scene, "method scene")
            result = render_scene(
                scene,
                output,
                title=title,
                description=description,
                output_name="method-schematic",
                formats=("svg",),
            )
        manifest = _load(Path(result["manifest"]))
        files = manifest.get("files") or {}
        caption = "图 2 %s（AstraDraw 方法示意图，schematic=true，非实验结果）。" % (
            manifest.get("title") or "方法概览"
        )
        info = {
            "manifest": result["manifest"],
            "svg": files.get("svg") or "",
            "png": files.get("png") or "",
            "caption": caption,
            "figure_number": 2,
            "kind": "astradraw_scene",
            "renderer": "astradraw",
            "schematic": True,
            "template_id": method_template or None,
        }
        write_json_atomic(base / "method-figure.json", info)
        return info, ""
    except (FigureWorkflowError, OSError, ValueError) as exc:
        return {}, str(exc)


def _empirical_command(
    blocker: str,
    project: str,
    run_id: str,
    experiment_id: str,
    question: str,
    metric: str,
) -> str:
    """A concrete next command for one blocker, or "" when the step is a human judgement.

    The preflight used to answer every blocker with "resolve blockers in order", which is
    weaker advice than the artifacts support: the run already knows its question, project,
    run id, experiment id and declared metric.
    """
    if blocker.startswith("literature ledger has no sources"):
        return 'python -m research_agent literature run --question "%s" --max-sources 4' % (
            question or "<topic>"
        )
    if blocker.startswith("multi-source synthesis matrix is missing"):
        return "python -m research_agent literature synthesize --project %s --run-id %s" % (
            project, run_id
        )
    if blocker.startswith("innovation review is missing"):
        return "python -m research_agent innovation review --project %s --run-id %s --rounds 1" % (
            project, run_id
        )
    if blocker.startswith("experiment package does not exist"):
        return (
            "python -m research_agent experiment scaffold --project %s --run-id %s "
            "--data <csv> --target <y> --features <x1,x2> --task classification --metric %s "
            "--experiment-id %s" % (project, run_id, metric, experiment_id)
        )
    if blocker.startswith("experiment evidence is not verified"):
        return "python -m research_agent experiment ingest --project %s --experiment-id %s" % (
            project, experiment_id
        )
    if blocker.startswith("experiment claim is not human-signed"):
        return (
            "python -m research_agent experiment claim --project %s --experiment-id %s "
            '--statement "..." --human-reason "..." '
            '--assertion "metric=%s,value=<v>,comparator=>=,tolerance=0.01"'
            % (project, experiment_id, metric)
        )
    return ""


def check_empirical_loop(project: Path, run_id: str, experiment_id: str) -> Dict[str, Any]:
    project = Path(project).resolve()
    target = run_dir(project, run_id)
    if not target.is_dir():
        raise EmpiricalLoopError("run does not exist: " + run_id)
    ledger = _load(target / "literature-ledger.json")
    sources = [item for item in (ledger.get("sources") or []) if isinstance(item, dict)]
    synthesis = _load(target / "synthesis-matrix.json")
    innovation = _load(target / "innovation-review.json")
    spec = _load(project / "experiments" / experiment_id / "experiment-spec.json")
    try:
        status = experiment_status(project, experiment_id)
    except ExperimentExecutionError as exc:
        # A missing package is a preflight finding, not a crash: the caller asked whether
        # the run is ready to write, and "the experiment does not exist yet" is the answer.
        status = {"stages": {}, "next_action": "", "error": str(exc)}
    blockers = []
    warnings = []
    if not sources:
        blockers.append("literature ledger has no sources")
    elif len(sources) < 3:
        warnings.append("fewer than 3 literature sources; the article is a scoped brief")
    if sources and len(sources) >= 5 and not synthesis:
        blockers.append("multi-source synthesis matrix is missing; run literature synthesize")
    if not innovation:
        blockers.append("innovation review is missing; run innovation review before writing")
    idea_id = ""
    if not spec:
        blockers.append("experiment package does not exist: " + experiment_id)
    elif str(spec.get("run_id") or "") != run_id:
        blockers.append(
            "experiment %s belongs to run %s, not %s"
            % (experiment_id, spec.get("run_id") or "unknown", run_id)
        )
    else:
        design = spec.get("design") or {}
        if not str(spec.get("hypothesis") or "").strip():
            blockers.append("experiment hypothesis is missing")
        for field in ("methods", "metric", "seeds"):
            if not design.get(field):
                blockers.append("experiment design is missing " + field)
        idea_id = str(spec.get("idea_id") or "")
        selected_ids = {
            str(item.get("idea_id") or "")
            for item in (
                innovation.get("final_ideas")
                or innovation.get("selected_ideas")
                or innovation.get("ideas")
                or []
            )
            if isinstance(item, dict)
        }
        if not idea_id:
            warnings.append("experiment has no idea_id; it cannot be tied to a selected innovation")
        elif selected_ids and idea_id not in selected_ids:
            blockers.append(
                "experiment idea_id %s is not in the innovation review" % idea_id
            )
    stages = status.get("stages") or {}
    if stages.get("evidence") != "verified":
        blockers.append("experiment evidence is not verified; run experiment ingest")
    if stages.get("claim") != "signed":
        blockers.append("experiment claim is not human-signed; human must run experiment claim")
    next_actions = []
    blocker_actions: List[Dict[str, str]] = []
    ordering = ""
    if blockers:
        context = _load(target / "run-context.json")
        request = context.get("request") if isinstance(context, dict) else None
        q0 = _load(target / "q0.json")
        question = ""
        if isinstance(request, dict):
            question = str(request.get("goal") or request.get("question") or "")
        if not question and isinstance(q0, dict):
            question = str(q0.get("question") or "")
        if not question:
            question = str((_load(target / "task.json") or {}).get("question") or "")
        design = (spec or {}).get("design") or {} if isinstance(spec, dict) else {}
        metric = str(design.get("metric") or "<metric>")
        for blocker in blockers:
            command = _empirical_command(
                blocker, str(project), run_id, experiment_id, question, metric
            )
            blocker_actions.append({"blocker": blocker, "command": command})
            next_actions.append(command or ("human decision required: " + blocker))
        ordering = "resolve blockers in the listed order; human gates stay in CLI"
    else:
        next_actions = [
            "build writing pack with experiment_id",
            "generate manuscript draft",
            "run manuscript review",
            "re-run experiment closure with the manuscript; human signs closure",
        ]
    return {
        "schema_version": LOOP_SCHEMA,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "status": "ready_for_writing" if not blockers else "blocked",
        "sources": len(sources),
        "has_synthesis": bool(synthesis),
        "has_innovation_review": bool(innovation),
        "experiment": {
            "run_id_matches": bool(spec) and str(spec.get("run_id") or "") == run_id,
            "idea_id": idea_id,
            "idea_grounded": bool(idea_id) and (not innovation or idea_id in {
                str(item.get("idea_id") or "")
                for item in (
                    innovation.get("final_ideas")
                    or innovation.get("selected_ideas")
                    or innovation.get("ideas")
                    or []
                )
                if isinstance(item, dict)
            }),
            "stages": stages,
            "next_action": status.get("next_action"),
        },
        "blockers": blockers,
        "blocker_actions": blocker_actions,
        "ordering": ordering,
        "warnings": warnings,
        "next_actions": next_actions,
        "boundary": LOOP_BOUNDARY,
    }


def run_empirical_paper(
    project: Path,
    run_id: str,
    experiment_id: str,
    output_path: Path,
    *,
    model: Any = None,
    review_model: Any = None,
    review_rounds: int = 0,
    threshold: float = 8.0,
    language: str = "zh",
    venue: str = "zh_core_journal",
    max_sources: int = 16,
    max_spans_per_source: int = 3,
    repair_attempts: int = 2,
    method_scene: str = "",
    method_template: str = "",
    semantic_support: bool = False,
    strict_support: bool = False,
    support_votes: int = 1,
    support_judge: Any = None,
    judge_model_id: str = "",
    ab_check: bool = False,
    ab_sections: Optional[List[str]] = None,
    offline_draft: bool = False,
    external_lint: bool = False,
    external_skill_root: str = "",
    external_consistency: bool = False,
    external_consistency_registry: str = "",
    external_consistency_auto: bool = False,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    preflight = check_empirical_loop(project, run_id, experiment_id)
    if preflight["status"] != "ready_for_writing":
        return {
            "schema_version": LOOP_SCHEMA,
            "status": "blocked",
            "preflight": preflight,
            "blockers": preflight["blockers"],
            "boundary": LOOP_BOUNDARY,
        }
    target = run_dir(project, run_id)
    figure = None
    figure_error = ""
    try:
        figure = build_result_figure(project, experiment_id)
    except (ExperimentFigureError, ImportError, OSError, ValueError) as exc:
        figure_error = str(exc)
    method_figure, method_error = _render_method_figure(
        project, run_id, method_scene=method_scene, method_template=method_template
    )
    pack = build_writing_pack(
        project,
        run_id,
        language=language,
        venue=venue,
        max_sources=max_sources,
        max_spans_per_source=max_spans_per_source,
        experiment_id=experiment_id,
    )
    write_json_atomic(target / "writing-pack.json", pack)
    with open(str(target / "writing-pack.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_writing_pack(pack))
    output = project_output_path(project, str(output_path), "draft")
    draft = generate_manuscript(
        project,
        run_id,
        output,
        model=model,
        repair_attempts=max(0, min(int(repair_attempts), 3)),
        offline_draft=offline_draft,
    )
    final_path = output
    review = None
    if review_rounds > 0:
        if review_model is None:
            raise EmpiricalLoopError("a review model is required when review_rounds > 0")
        review = run_manuscript_review(
            project,
            run_id,
            output,
            rounds=review_rounds,
            threshold=threshold,
            model=review_model,
            output_dir=target / "manuscript-review",
            ab_reviewer=review_model if ab_check else None,
            ab_sections=ab_sections,
        )
        final_path = Path(review.get("final_draft") or output)
    support = None
    if semantic_support:
        if review_model is None:
            raise EmpiricalLoopError("semantic support requires a review/judge model")
        from .adapters.support_judge import support_judge_from_model
        from .support_audit import audit_pack_support

        judge = support_judge or support_judge_from_model(
            review_model, strict=strict_support
        )
        support = audit_pack_support(
            final_path,
            pack,
            judge=judge,
            strict=strict_support,
            judge_model_id=judge_model_id
            or getattr(review_model, "model_id", type(review_model).__name__),
            judge_votes=support_votes,
            cache_dir=target / "support-cache",
        )
    final_audit = audit_manuscript(
        final_path, pack=pack, project=project, run_id=run_id, experiment_id=experiment_id
    )
    external_lint_result: Dict[str, Any] = {}
    if external_lint:
        from .external_writing_gate import (
            ExternalWritingGateError,
            run_writing_lint,
        )

        try:
            external_lint_result = run_writing_lint(
                final_path,
                Path(external_skill_root) if external_skill_root else None,
            )
            final_audit["external_lint"] = external_lint_result
            if external_lint_result.get("status") == "blocked":
                final_audit["status"] = "blocked"
                final_audit.setdefault("blockers", []).append(
                    "external_lint: "
                    + ", ".join(
                        str(item.get("code") or "external_issue")
                        for item in (external_lint_result.get("issues") or [])[:6]
                    )
                )
        except ExternalWritingGateError as exc:
            external_lint_result = {
                "schema_version": "external-writing-gate-0.1",
                "status": "unavailable",
                "error": str(exc),
            }
            final_audit["external_lint"] = external_lint_result
            final_audit["status"] = "blocked"
            final_audit.setdefault("blockers", []).append(
                "external_lint: unavailable: " + str(exc)
            )
    if external_consistency:
        from .external_consistency_gate import (
            ExternalConsistencyGateError,
            run_consistency_check,
        )

        registry_value = str(external_consistency_registry or "").strip()
        if external_consistency_auto and not registry_value:
            from .experiment_consistency import (
                ExperimentConsistencyError,
                build_consistency_registry,
            )

            try:
                derived = build_consistency_registry(project, experiment_id)
                auto_path = target / "consistency-registry.json"
                write_json_atomic(auto_path, derived["registry"])
                registry_value = str(auto_path)
                final_audit["external_consistency_source"] = derived
            except (ExperimentConsistencyError, OSError, ValueError) as exc:
                final_audit["external_consistency"] = {
                    "schema_version": "external-consistency-gate-0.1",
                    "status": "unavailable",
                    "error": "auto registry failed: " + str(exc),
                }
                final_audit["status"] = "blocked"
                final_audit.setdefault("blockers", []).append(
                    "external_consistency: auto registry failed: " + str(exc)
                )
                registry_value = ""
        if not registry_value:
            final_audit["external_consistency"] = {
                "schema_version": "external-consistency-gate-0.1",
                "status": "unavailable",
                "error": "external consistency registry is required",
            }
            final_audit["status"] = "blocked"
            final_audit.setdefault("blockers", []).append(
                "external_consistency: registry is required"
            )
        else:
            try:
                registry = project_file(project, registry_value, "consistency registry")
                external_consistency_result = run_consistency_check(
                    registry,
                    Path(external_skill_root) if external_skill_root else None,
                )
                final_audit["external_consistency"] = external_consistency_result
                if external_consistency_result.get("status") == "blocked":
                    final_audit["status"] = "blocked"
                    final_audit.setdefault("blockers", []).append(
                        "external_consistency: "
                        + ", ".join(
                            str(item.get("code") or "external_issue")
                            for item in (external_consistency_result.get("issues") or [])[:6]
                        )
                    )
            except (ExternalConsistencyGateError, OSError, ValueError) as exc:
                final_audit["external_consistency"] = {
                    "schema_version": "external-consistency-gate-0.1",
                    "status": "unavailable",
                    "error": str(exc),
                }
                final_audit["status"] = "blocked"
                final_audit.setdefault("blockers", []).append(
                    "external_consistency: unavailable: " + str(exc)
                )
    if support is not None:
        final_audit["support"] = support
        write_json_atomic(target / "support-ledger.json", support)
        if support.get("status") == "blocked":
            final_audit.setdefault("warnings", []).append(
                "semantic support ledger found contradicted or unresolved citations"
            )
    write_json_atomic(target / "writing-audit.json", final_audit)
    closure = check_experiment_closure(
        project,
        experiment_id,
        manuscript=final_path,
        output_dir=project / "experiments" / experiment_id / "experiment-closure",
    )
    review_passed = True
    if review is not None:
        review_passed = review.get("status") == "reviewed"
    support_counts = (support or {}).get("counts") or {}
    support_passed = (
        not semantic_support
        or not strict_support
        or (
            (support or {}).get("status") != "blocked"
            and int(support_counts.get("insufficient") or 0) == 0
            and int((support or {}).get("unresolved_refs") or 0) == 0
        )
    )
    if final_audit.get("external_lint", {}).get("status") in ("blocked", "unavailable") or final_audit.get(
        "external_consistency", {}
    ).get("status") in ("blocked", "unavailable"):
        status = "needs_more_work"
    elif final_audit.get("status") == "ready_for_human_review" and closure.get("status") == "ready_for_human_signature":
        status = (
            "ready_for_human_review"
            if review_passed and support_passed
            else "needs_more_work"
        )
    elif draft.get("status") == "blocked":
        status = "draft_blocked"
    else:
        status = "closure_blocked"
    latest_review = {}
    if review:
        for item in reversed(review.get("iterations") or []):
            if item.get("stage") == "review":
                latest_review = item.get("review") or {}
                break
    report = {
        "schema_version": LOOP_SCHEMA,
        "status": status,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "created_at": _now(),
        "preflight": preflight,
        "figure": (
            {
                "manifest": figure.get("manifest"),
                "figure_id": figure.get("figure_id"),
                "png": figure.get("png"),
                "svg": figure.get("svg"),
                "caption": figure.get("caption"),
                "status": verify_result_figure(Path(figure["manifest"]), project=project).get("status"),
                "schematic": False,
            }
            if figure
            else {"status": "unavailable", "error": figure_error}
        ),
        "method_figure": method_figure or {"status": "not_requested", "error": method_error},
        "warnings": (
            ([figure_error] if figure_error else [])
            + ([method_error] if method_error else [])
            + list(preflight.get("warnings") or [])
        ),
        "writing_pack": {
            "json": str(target / "writing-pack.json"),
            "markdown": str(target / "writing-pack.md"),
        },
        "draft": {
            "path": str(output),
            "status": draft.get("status"),
            "audit": draft.get("audit", {}).get("status"),
            "repair_attempts": draft.get("repair_attempts"),
        },
        "review": (
            {
                "status": review.get("status"),
                "best_score": review.get("best_score"),
                "threshold": review.get("threshold"),
                "final_draft": str(final_path),
                "weaknesses": list(latest_review.get("weaknesses") or [])[:6],
                "must_fix": list(latest_review.get("must_fix") or [])[:8],
                "submission_ready": False,
            }
            if review
            else None
        ),
        "final_audit": final_audit,
        "external_lint": external_lint_result or None,
        "support_ledger": (
            {
                "status": support.get("status"),
                "method": support.get("method"),
                "counts": support.get("counts"),
                "unresolved_refs": support.get("unresolved_refs"),
                "path": str(target / "support-ledger.json"),
            }
            if support
            else None
        ),
        "writing_audit": str(target / "writing-audit.json"),
        "closure": {
            "status": closure.get("status"),
            "report": str(
                project / "experiments" / experiment_id / "experiment-closure" / "closure-report.json"
            ),
            "blockers": closure.get("blockers") or [],
        },
        "human_actions": (
            [
                "run another review round or revise the manuscript; the model review is below threshold",
                "do not sign the experiment closure while the manuscript needs more work",
            ]
            if not review_passed
            else [
                "review the final draft and experiment closure report",
                "sign the experiment closure only if the manuscript is acceptable (human only)",
            ]
        )
        + ["no automatic submission"],
        "submission_ready": False,
        "boundary": LOOP_BOUNDARY,
    }
    write_json_atomic(target / "empirical-paper-loop.json", report)
    lines = [
        "# Empirical Paper Loop",
        "",
        "- run: `%s`" % run_id,
        "- experiment: `%s`" % experiment_id,
        "- status: **%s**" % status,
        "- draft: `%s`" % final_path,
        "- draft audit: `%s`" % final_audit.get("status"),
        "- experiment closure: `%s`" % closure.get("status"),
        "- submission_ready: false",
        "",
        "## Human actions",
        "",
    ]
    for item in report["human_actions"]:
        lines.append("- " + item)
    lines += ["", LOOP_BOUNDARY, ""]
    (target / "empirical-paper-loop.md").write_text("\n".join(lines), encoding="utf-8")
    return report
