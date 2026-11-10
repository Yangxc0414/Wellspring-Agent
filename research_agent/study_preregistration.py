"""Machine-bound pre-registration sidecar for search studies.

The declaration is human-authored data, not a signature: it records the question,
hypothesis, analysis plan and decision rule before the run, and binds them to the study by
hash. `study closure` refuses a sidecar whose study hash or resolved design drifted.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .storage import read_json, write_json_atomic

PREREG_SCHEMA = "study-preregistration-0.1"
SIDECAR = "study-preregistration.json"
REQUIRED_TEXT = ("question", "hypothesis", "analysis", "decision_rule")
BASELINE_KINDS = ("tuned_cv", "external_file", "none")


class PreregistrationError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


UNFILLED_MARK = "TODO("
SCAFFOLD_BOUNDARY = (
    "the scaffold is a form, not a pre-registration: the four prose fields stay placeholders "
    "until a human writes them, and a plan that still contains a placeholder is refused at load "
    "time, because a pre-filled template would make the pre-registration a ceremony rather than "
    "a commitment made before the results existed"
)


def scaffold(design, seeds, budget, dataset, min_delta=0.005, baseline=None):
    """A pre-registration form with the mechanical parts filled in and the promises left to a human.

    The JSON shape was the barrier: measured across 104 packages only 30 carried a
    pre-registration, and the ones that did were written by hand in a scratch script. This fills
    the parts that are facts about the request (dataset, seeds, budget, resolved design) and
    refuses to guess the parts that are research judgement.
    """
    from .search_lab import normalize_design

    resolved = normalize_design(dict(design or {}), float(min_delta))
    return {
        "schema_version": PREREG_SCHEMA,
        "question": UNFILLED_MARK + "state the one question this study answers)",
        "hypothesis": UNFILLED_MARK + "state the mechanism you expect to move the metric, and which way)",
        "analysis": UNFILLED_MARK + "state the estimator and its interval, and what is not claimed)",
        "decision_rule": UNFILLED_MARK + "state what result would make you stop calling this a direction)",
        "design": resolved,
        "seeds": [int(seed) for seed in (seeds or [])],
        "budget": int(budget),
        "min_delta": float(min_delta),
        "dataset": str(dataset),
        "baseline": baseline or {
            "kind": "tuned_cv",
            "file": "tuned-baseline.json",
            "why": UNFILLED_MARK + "say why this opponent is the strong comparison)",
        },
        "boundary": SCAFFOLD_BOUNDARY,
    }


def unfilled_fields(prereg):
    """Which prose fields still hold a placeholder."""
    fields = [key for key in REQUIRED_TEXT if UNFILLED_MARK in str(prereg.get(key) or "")]
    baseline = prereg.get("baseline")
    if isinstance(baseline, dict) and UNFILLED_MARK in str(baseline.get("why") or ""):
        fields.append("baseline.why")
    return fields


def load_preregistration(path: Path) -> Dict[str, Any]:
    try:
        data = read_json(Path(path))
    except Exception as exc:
        raise PreregistrationError("pre-registration is not readable JSON: %s" % exc)
    if not isinstance(data, dict):
        raise PreregistrationError("pre-registration must be a JSON object")
    if str(data.get("schema_version") or "") != PREREG_SCHEMA:
        raise PreregistrationError("schema_version must be %s" % PREREG_SCHEMA)
    for field in REQUIRED_TEXT:
        if not str(data.get(field) or "").strip():
            raise PreregistrationError("pre-registration lacks %s" % field)
    design = data.get("design")
    if not isinstance(design, dict):
        raise PreregistrationError("pre-registration design must be an object")
    seeds = data.get("seeds")
    if not isinstance(seeds, list) or not [item for item in seeds if isinstance(item, int)]:
        raise PreregistrationError("pre-registration needs a non-empty seeds list")
    budget = data.get("budget")
    if not isinstance(budget, int) or budget <= 0:
        raise PreregistrationError("pre-registration budget must be a positive integer")
    if not str(data.get("dataset") or "").strip():
        raise PreregistrationError("pre-registration needs dataset")
    baseline = data.get("baseline")
    if baseline is not None:
        if not isinstance(baseline, dict):
            raise PreregistrationError("pre-registration baseline must be an object")
        kind = str(baseline.get("kind") or "")
        if kind not in BASELINE_KINDS:
            raise PreregistrationError(
                "pre-registration baseline.kind must be one of %s; the opponent is chosen here, "
                "before results exist, not when a claim is signed" % "/".join(BASELINE_KINDS)
            )
        if kind != "none":
            if not str(baseline.get("file") or "").strip():
                raise PreregistrationError(
                    "baseline.kind=%s requires baseline.file: a declared opponent cannot be empty"
                    % kind
                )
            if not str(baseline.get("why") or "").strip():
                raise PreregistrationError(
                    "baseline.kind=%s requires baseline.why: state why this is the strong "
                    "comparison, not just that one was made" % kind
                )
        else:
            # an explicit none is a decision worth recording; a silent omission is not
            if not str(baseline.get("why") or "").strip():
                raise PreregistrationError(
                    "baseline.kind=none requires baseline.why: say why no external opponent is "
                    "claimed, so the claim is read as an internal comparison"
                )
    leftover = unfilled_fields(data)
    if leftover:
        raise PreregistrationError(
            "pre-registration still holds placeholder text in %s: it was scaffolded and never "
            "written. The point of pre-registering is a commitment made before the results exist, "
            "so an unfilled form is refused rather than accepted as a formality"
            % ", ".join(leftover)
        )
    return data


def assert_matches_run(prereg: Dict[str, Any], *, design: Dict[str, Any], seeds: List[int],
                       budget: int, dataset: str) -> None:
    declared_design = prereg.get("design") or {}
    if _canonical(declared_design) != _canonical(design or {}):
        raise PreregistrationError(
            "declared design does not match the command's --factors; "
            "the pre-registration must be written before the run"
        )
    if [int(item) for item in prereg.get("seeds") or []] != [int(item) for item in seeds]:
        raise PreregistrationError("declared seeds do not match --seeds")
    if int(prereg.get("budget") or 0) != int(budget):
        raise PreregistrationError("declared budget does not match --budget")
    if str(prereg.get("dataset") or "") != str(dataset):
        raise PreregistrationError("declared dataset does not match --dataset")


def bind_sidecar(study_dir: Path, prereg: Dict[str, Any], study: Dict[str, Any]) -> Path:
    payload = dict(prereg)
    payload.update({
        "declared_design_sha256": hashlib.sha256(
            _canonical(prereg.get("design") or {}).encode("utf-8")
        ).hexdigest(),
        "resolved_design": study.get("design") or {},
        "study_sha256": study.get("study_sha256") or "",
        "bound_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "boundary": (
            "the declared fields are human-authored and not signed; the study/design hashes "
            "only prove the declared plan was bound to this package, not that the study is "
            "correct or peer-reviewed"
        ),
    })
    path = Path(study_dir) / SIDECAR
    write_json_atomic(path, payload)
    return path


def check_preregistration(study_dir: Path, study: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(study_dir) / SIDECAR
    if not path.is_file():
        return {
            "present": False,
            "bound": False,
            "reason": "no study-preregistration.json; legacy or unregistered study",
        }
    try:
        data = read_json(path)
    except Exception as exc:
        return {"present": True, "bound": False, "reason": "sidecar unreadable: %s" % exc}
    if not isinstance(data, dict):
        return {"present": True, "bound": False, "reason": "sidecar is not an object"}
    if str(data.get("study_sha256") or "") != str(study.get("study_sha256") or ""):
        return {"present": True, "bound": False, "reason": "sidecar study hash does not match"}
    if _canonical(data.get("resolved_design") or {}) != _canonical(study.get("design") or {}):
        return {"present": True, "bound": False, "reason": "sidecar design does not match study"}
    if str(data.get("declared_design_sha256") or "") != hashlib.sha256(
        _canonical(data.get("design") or {}).encode("utf-8")
    ).hexdigest():
        return {"present": True, "bound": False, "reason": "sidecar design hash is invalid"}
    return {"present": True, "bound": True, "reason": "declared plan is hash-bound to this study"}
