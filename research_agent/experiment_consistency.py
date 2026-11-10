"""Derive a bounded consistency registry from verified experiment evidence.

The registry is a read-only projection for the external scientific-writing
`check_consistency.py` gate. It never creates or changes evidence, claims,
closure or signatures. `sample_size` is the dataset row count; it is not an
evaluation-N estimate.
"""

import hashlib
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import JsonStoreError, read_json


SCHEMA = "experiment-consistency-registry-0.1"
EXTERNAL_SCHEMA = "1.0"
EXPERIMENT_ID_RE = re.compile(r"^EXP-[A-Za-z0-9._-]{1,80}$")
BOUNDARY = (
    "Derived read-only consistency registry from verified experiment evidence; "
    "it does not create claim/EA/gate/closure/signature. sample_size is the "
    "dataset row count, not evaluation N."
)


class ExperimentConsistencyError(ValueError):
    pass


def _load(path: Path) -> Dict[str, Any]:
    try:
        value = read_json(path)
    except JsonStoreError as exc:
        raise ExperimentConsistencyError(str(exc)) from exc
    if not isinstance(value, dict):
        raise ExperimentConsistencyError("expected a JSON object: " + str(path))
    return value


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_consistency_registry(project: Path, experiment_id: str) -> Dict[str, Any]:
    project = Path(project).resolve()
    experiment_id = str(experiment_id).strip()
    if not EXPERIMENT_ID_RE.match(experiment_id):
        raise ExperimentConsistencyError("invalid experiment_id: " + experiment_id)
    package = (project / "experiments" / experiment_id).resolve()
    try:
        package.relative_to(project)
    except ValueError:
        raise ExperimentConsistencyError("experiment package escapes the project")
    if not package.is_dir():
        raise ExperimentConsistencyError("experiment package does not exist: " + str(package))
    spec_path = package / "experiment-spec.json"
    evidence_path = package / "experiment-evidence.json"
    if not spec_path.is_file() or not evidence_path.is_file():
        raise ExperimentConsistencyError(
            "experiment-spec.json and experiment-evidence.json are required"
        )
    spec = _load(spec_path)
    evidence = _load(evidence_path)
    if evidence.get("status") != "verified":
        raise ExperimentConsistencyError("only verified experiment evidence can be projected")
    aggregate = ((evidence.get("metrics") or {}).get("aggregate") or {})
    if not isinstance(aggregate, dict) or not aggregate:
        raise ExperimentConsistencyError("evidence has no aggregate metrics")
    rows = spec.get("data", {}).get("rows")
    if isinstance(rows, bool) or not isinstance(rows, int) or rows <= 0:
        raise ExperimentConsistencyError("experiment spec has no positive data.rows")
    claim = {}
    claim_path = package / "claim.json"
    if claim_path.is_file():
        claim = _load(claim_path)
    claim_status = "signed" if claim.get("status") == "supported" else "unsigned"
    analysis_intent = "confirmatory" if claim_status == "signed" else "exploratory"

    methods = sorted(str(name) for name in aggregate if isinstance(aggregate.get(name), dict))
    if not methods:
        raise ExperimentConsistencyError("evidence has no method aggregates")
    metric_names = sorted(
        {
            str(metric)
            for name in methods
            for metric in (aggregate.get(name) or {})
            if isinstance(aggregate.get(name, {}).get(metric), dict)
        }
    )
    if not metric_names:
        raise ExperimentConsistencyError("evidence has no metric aggregates")
    outcome_by_metric = {
        metric: "O%03d" % (index + 1) for index, metric in enumerate(metric_names)
    }
    method_ids = {
        method: "M%03d" % (index + 1) for index, method in enumerate(methods)
    }

    numeric_facts: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    for method in methods:
        method_id = method_ids[method]
        method_metrics = aggregate.get(method) or {}
        for metric in metric_names:
            metric_value = method_metrics.get(metric)
            if not isinstance(metric_value, dict):
                continue
            outcome_id = outcome_by_metric[metric]
            for statistic in ("mean", "std"):
                value = _number(metric_value.get(statistic))
                if value is None:
                    continue
                numeric_facts.append(
                    {
                        "fact_id": "N%03d" % (len(numeric_facts) + 1),
                        "concept": "%s.%s.%s" % (method, metric, statistic),
                        "section": "results",
                        "value": value,
                        "unit": "unitless",
                        "numerator": None,
                        "denominator": None,
                        "sample_size": None,
                        "analysis_set": "dataset_rows",
                        "evidence_ids": ["E001"],
                    }
                )
            results.append(
                {
                    "result_id": "R%03d" % (len(results) + 1),
                    "method_id": method_id,
                    "outcome_id": outcome_id,
                    "analysis_intent": analysis_intent,
                    "sample_size": rows,
                    "evidence_ids": ["E001"],
                    "reported_sections": ["results"],
                }
            )
    if not numeric_facts or not results:
        raise ExperimentConsistencyError("evidence has no numeric aggregates to project")
    method_entries = [
        {
            "method_id": method_ids[method],
            "name": method,
            "analysis_intent": analysis_intent,
            "protocol_status": "not_applicable",
            "outcome_ids": [
                outcome_by_metric[metric]
                for metric in metric_names
                if isinstance((aggregate.get(method) or {}).get(metric), dict)
            ],
        }
        for method in methods
    ]
    registry = {
        "schema_version": EXTERNAL_SCHEMA,
        "numeric_facts": numeric_facts,
        "methods": method_entries,
        "results": results,
    }
    return {
        "schema_version": SCHEMA,
        "experiment_id": str(experiment_id),
        "claim_status": claim_status,
        "analysis_intent": analysis_intent,
        "source_hashes": {
            "spec_sha256": _sha256(spec_path),
            "evidence_sha256": _sha256(evidence_path),
            "claim_sha256": _sha256(claim_path) if claim_path.is_file() else "",
        },
        "registry": registry,
        "boundary": BOUNDARY,
    }
