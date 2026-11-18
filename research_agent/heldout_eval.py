"""Held-out task evaluation: deterministic rubric over pipeline artifacts.

The repository could describe its research stages but not *measure* how well a run did on
a task that was never used to author the recipe. This module makes the first half of that
measurable without inventing judgement:

- tasks and rubric are frozen data (research_agent/eval/heldout_tasks.json);
- each axis (idea / experiment / paper) is scored by coarse deterministic checks;
- a run that lacks an artifact is reported as not_run, never as pass;
- the report says what it is not: conformance, not scientific quality.

It reads artifacts only; it creates no Claim / EA / Verdict / Signature.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "heldout-tasks-0.1"
REPORT_SCHEMA = "heldout-eval-0.1"
EXPECTED_SECTIONS = (
    "Abstract",
    "Introduction",
    "Related Work",
    "Method",
    "Experimental Setup",
    "Results",
    "Discussion",
    "Conclusion",
)
# Draft text cites evidence spans as [ARXIV-...-S01-04] (numeric [1] refs are produced later
# by the manuscript renderer), so count any bracketed token, not only digits.
CITATION_RE = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9._:-]{3,80})\]")


class HeldoutEvalError(ValueError):
    pass


def load_tasks(path: Any) -> Dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise HeldoutEvalError("held-out task file not found: " + str(target))
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HeldoutEvalError("cannot read held-out tasks: " + str(exc))
    if not isinstance(data, dict) or str(data.get("schema") or "") != SCHEMA:
        raise HeldoutEvalError("held-out task schema must be " + SCHEMA)
    tasks = data.get("tasks")
    rubric = data.get("rubric")
    if not isinstance(tasks, list) or not tasks:
        raise HeldoutEvalError("held-out task file needs a non-empty tasks list")
    if not isinstance(rubric, dict) or not rubric:
        raise HeldoutEvalError("held-out task file needs a rubric object")
    for axis, checks in rubric.items():
        if not isinstance(checks, list) or not checks:
            raise HeldoutEvalError("rubric axis needs checks: " + axis)
        for check in checks:
            if not str(check.get("id") or "").strip():
                raise HeldoutEvalError("rubric check needs an id")
    return data


def task_by_id(data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    for task in data["tasks"]:
        if str(task.get("task_id") or "") == task_id:
            return task
    known = ", ".join(str(task.get("task_id")) for task in data["tasks"])
    raise HeldoutEvalError("unknown task {0}; known: {1}".format(task_id, known))


def _load(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HeldoutEvalError("cannot read {0}: {1}".format(path.name, exc))
    return value if isinstance(value, dict) else None


def _nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return value is not None


def _metric_shape(value: str) -> bool:
    text = (value or "").strip()
    if not text or len(text) > 48 or " " in text or text.endswith("."):
        return False
    return not any(mark in text for mark in (",", ";", ":", "：", "。", "，"))


BUDGET_UNIT_RE = re.compile(
    r"(\d[\d,]*\s*(?:x|×|seeds?|tasks?|tokens?|runs?|evals?|evaluations?|hours?|minutes?|seconds?|gb|mb))"
    r"|(?:(?:seeds?|tasks?|runs?|tokens?)\s*[:=]\s*\d)",
    re.IGNORECASE,
)


def _budget_ok(value: str) -> bool:
    """A budget needs a number *with a unit*, not just any digit.

    First version accepted any digit, which let "Pilot scale: 1 base model family" pass.
    The tightened rule is what the frozen rubric now means by "measurable budget".
    """
    text = (value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(mark in lowered for mark in ("not specified", "unspecified", "tbd", "待定")):
        return False
    if not any(char.isdigit() for char in text):
        return False
    return bool(BUDGET_UNIT_RE.search(text))


def _check_idea(run: Path) -> Tuple[str, List[Dict[str, Any]]]:
    idea = _load(run / "idea.json")
    literature = _load(run / "literature.json") or {}
    if idea is None:
        return "not_run", []
    candidates = [item for item in (idea.get("candidates") or []) if isinstance(item, dict)]
    span_ids = {
        str(span.get("span_id"))
        for span in (literature.get("spans") or [])
        if isinstance(span, dict) and span.get("span_id")
    }
    grounded = []
    for candidate in candidates:
        refs = [str(ref) for ref in (candidate.get("evidence_refs") or [])]
        grounded.append(bool(refs) and any(ref in span_ids for ref in refs))
    checks = [
        {"id": "idea.candidates", "passed": len(candidates) >= 3,
         "detail": "{0} candidates".format(len(candidates))},
        {"id": "idea.grounded", "passed": bool(candidates) and all(grounded),
         "detail": "{0}/{1} grounded".format(sum(1 for item in grounded if item), len(candidates))},
        {"id": "idea.falsifiable", "passed": bool(candidates) and all(
            _nonempty(item.get("falsification")) for item in candidates)},
        {"id": "idea.lenses", "passed": len({str(item.get("lens")) for item in candidates}) >= 2},
    ]
    return "run", checks


def _check_experiment(run: Path) -> Tuple[str, List[Dict[str, Any]]]:
    design = _load(run / "experiment.json")
    if design is None:
        return "not_run", []
    controls = design.get("controls") or []
    seeds = design.get("seeds")
    checks = [
        {"id": "experiment.fields", "passed": all(
            _nonempty(design.get(key)) for key in ("hypothesis", "baseline", "primary_metric", "controls"))},
        {"id": "experiment.metric_shape", "passed": _metric_shape(str(design.get("primary_metric") or "")),
         "detail": str(design.get("primary_metric") or "")[:60]},
        {"id": "experiment.budget", "passed": _budget_ok(str(design.get("budget") or "")),
         "detail": str(design.get("budget") or "")[:60]},
        {"id": "experiment.controls", "passed": isinstance(controls, list) and len(controls) >= 2},
        {"id": "experiment.seeds", "passed": isinstance(seeds, int) and seeds >= 3},
        {"id": "experiment.stopping_rule", "passed": _nonempty(design.get("stopping_rule"))},
    ]
    return "run", checks


def _check_paper(run: Path) -> Tuple[str, List[Dict[str, Any]]]:
    paper = _load(run / "paper.json")
    if paper is None:
        return "not_run", []
    draft = [item for item in (paper.get("draft") or []) if isinstance(item, dict)]
    by_section = {str(item.get("section")): item for item in draft}
    missing = [name for name in EXPECTED_SECTIONS if name not in by_section]
    empty = [name for name in EXPECTED_SECTIONS
             if name in by_section and not str(by_section[name].get("text") or "").strip()]
    results = by_section.get("Results") or {}
    results_status = str(results.get("status") or "")
    citations = set()
    for item in draft:
        citations.update(CITATION_RE.findall(str(item.get("text") or "")))
    checks = [
        {"id": "paper.sections", "passed": not missing,
         "detail": "missing: " + ", ".join(missing) if missing else "all present"},
        {"id": "paper.draft", "passed": not empty,
         "detail": "empty: " + ", ".join(empty) if empty else "all non-empty"},
        {"id": "paper.results_pending", "passed": "pending" in results_status,
         "detail": "results status: " + (results_status or "missing")},
        {"id": "paper.citations", "passed": len(citations) >= 4,
         "detail": "{0} distinct citations".format(len(citations))},
    ]
    return "run", checks


def evaluate_run(run_dir: Any, task_file: Any, task_id: str = "") -> Dict[str, Any]:
    data = load_tasks(task_file)
    task = task_by_id(data, task_id) if task_id else data["tasks"][0]
    run = Path(run_dir)
    if not run.is_dir():
        raise HeldoutEvalError("run dir not found: " + str(run))
    rubric = data["rubric"]
    axes: List[Dict[str, Any]] = []
    total_passed = total_checks = 0
    for axis in ("idea", "experiment", "paper"):
        if axis not in rubric:
            continue
        status, checks = {"idea": _check_idea, "experiment": _check_experiment, "paper": _check_paper}[axis](run)
        if status == "not_run":
            axes.append({"axis": axis, "status": "not_run", "checks": [], "passed": 0, "total": 0})
            continue
        passed = sum(1 for check in checks if check.get("passed"))
        axes.append({"axis": axis, "status": "run", "checks": checks,
                     "passed": passed, "total": len(checks)})
        total_passed += passed
        total_checks += len(checks)
    return {
        "schema": REPORT_SCHEMA,
        "task_id": task.get("task_id"),
        "topic": task.get("topic"),
        "run_dir": str(run),
        "axes": axes,
        "summary": {
            "passed": total_passed,
            "total": total_checks,
            "score": round(float(total_passed) / total_checks, 3) if total_checks else 0.0,
        },
        "boundary": (
            "deterministic conformance rubric; it measures whether a run satisfies the frozen checks, "
            "not whether the science is good. n=1 run is not a direction claim."
        ),
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Held-out evaluation: " + str(report.get("task_id")),
        "",
        "- topic: " + str(report.get("topic")),
        "- run: " + str(report.get("run_dir")),
        "- score: {0}/{1}".format(report["summary"]["passed"], report["summary"]["total"]),
        "",
    ]
    for axis in report["axes"]:
        lines.append("## " + axis["axis"] + " (" + axis["status"] + ")")
        if axis["status"] == "not_run":
            lines.append("")
            lines.append("- artifact missing; not counted as pass")
            lines.append("")
            continue
        for check in axis["checks"]:
            mark = "PASS" if check.get("passed") else "FAIL"
            detail = check.get("detail")
            lines.append("- [{0}] {1}{2}".format(mark, check["id"], (" — " + str(detail)) if detail else ""))
        lines.append("")
    lines.append("> " + str(report.get("boundary")))
    return "\n".join(lines) + "\n"
