"""ESE method registry: stage x method task cards, required fields, advisory checks.

The repository already has a stage dimension (S0-S16 modules). It did not have a
*method* dimension: a controlled experiment, a case study and a repository-mining study
were all validated by the same generic design checklist. This module makes the advisor's
two-dimensional matrix (research stage x research method) executable data:

- the registry (modules/method-registry/registry.json) is the source of truth;
- a task card merges stage + method into: required protocol fields, artifacts, checks,
  reporting sections and the canonical guidelines that mandate them;
- check() reports missing fields for a design/protocol payload, but is **advisory only**:
  it never blocks a gate, never writes, never creates a Claim.

Reference work behind the entries (short form): Kitchenham & Charters 2007; Wohlin 2014;
PRISMA 2020; Wohlin et al. 2012; Kitchenham et al. 2002; Jedlitschka et al. 2008;
Ralph et al. 2020; Runeson & Host 2009; Yin 2018; Kalliamvakou et al. 2014;
Bird et al. 2009; Hassan 2009; Sim et al. 2003; Sainz et al. 2023; Kitchenham & Pfleeger
2008; Hevner et al. 2004; Wieringa 2014; Johannesson & Perjons 2014; Avison et al. 1999;
Shadish, Cook & Campbell 2002.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SCHEMA = "ese-method-registry-0.1"
SEVERITIES = ("blocker", "warn")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "modules" / "method-registry" / "registry.json"


class MethodRegistryError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MethodRegistryError(message)


def validate(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Fail closed on malformed registry data: it is shipped data, not ad-hoc input."""
    _require(isinstance(registry, dict), "registry must be an object")
    _require(str(registry.get("schema") or "") == SCHEMA, "schema must be " + SCHEMA)
    stages = registry.get("stages")
    methods = registry.get("methods")
    _require(isinstance(stages, list) and stages, "registry needs a non-empty stages list")
    _require(isinstance(methods, list) and methods, "registry needs a non-empty methods list")

    stage_ids = []
    for stage in stages:
        stage_id = str(stage.get("id") or "")
        _require(bool(stage_id), "stage id cannot be empty")
        _require(stage_id not in stage_ids, "duplicate stage id: " + stage_id)
        stage_ids.append(stage_id)

    method_ids = []
    for method in methods:
        method_id = str(method.get("id") or "")
        _require(bool(method_id), "method id cannot be empty")
        _require(method_id not in method_ids, "duplicate method id: " + method_id)
        method_ids.append(method_id)
        _require(bool(str(method.get("name_zh") or "")), method_id + ": name_zh required")
        _require(bool(str(method.get("name_en") or "")), method_id + ": name_en required")
        fit = method.get("fit_stages")
        _require(isinstance(fit, list) and fit, method_id + ": fit_stages must be non-empty")
        unknown = [stage for stage in fit if stage not in stage_ids]
        _require(not unknown, method_id + ": unknown stages " + ", ".join(unknown))
        for key in ("guidelines", "protocol_fields", "artifacts", "cannot_support", "checks"):
            _require(isinstance(method.get(key), list), method_id + ": " + key + " must be a list")
        _require(isinstance(method.get("stage_tasks"), dict), method_id + ": stage_tasks must be an object")
        _require(bool(method.get("guidelines")), method_id + ": at least one guideline is required")
        _require(bool(method.get("cannot_support")), method_id + ": cannot_support is required")
        _require(bool(method.get("checks")), method_id + ": at least one check is required")
        keys = []
        for guideline in method["guidelines"]:
            key = str(guideline.get("key") or "")
            _require(bool(key) and bool(guideline.get("citation")) and bool(guideline.get("mandates")),
                     method_id + ": guideline needs key/citation/mandates")
            _require(key not in keys, method_id + ": duplicate guideline key " + key)
            keys.append(key)
        for check in method["checks"]:
            check_id = str(check.get("id") or "")
            _require(bool(check_id), method_id + ": check id required")
            _require(str(check.get("severity")) in SEVERITIES, check_id + ": severity must be blocker/warn")
            requires = check.get("requires")
            _require(isinstance(requires, list) and requires, check_id + ": requires must be non-empty")
        for stage_id, task in method["stage_tasks"].items():
            _require(stage_id in fit, method_id + ": stage_tasks for stage outside fit_stages: " + stage_id)
            _require(bool(str(task or "")), method_id + ": empty stage task for " + stage_id)
    return registry


def load_registry(path: Optional[Any] = None) -> Dict[str, Any]:
    target = Path(path) if path else DEFAULT_REGISTRY
    if not target.is_file():
        raise MethodRegistryError("method registry not found: " + str(target))
    try:
        with open(str(target), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise MethodRegistryError("cannot read method registry: " + str(exc))
    return validate(data)


def stage_ids(registry: Optional[Dict[str, Any]] = None) -> List[str]:
    return [str(stage["id"]) for stage in (registry or load_registry())["stages"]]


def list_methods(registry: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    data = registry or load_registry()
    out = []
    for method in data["methods"]:
        out.append({
            "id": method["id"],
            "name_zh": method["name_zh"],
            "name_en": method["name_en"],
            "fit_stages": list(method["fit_stages"]),
            "guidelines": [item["key"] for item in method["guidelines"]],
            "cannot_support": list(method["cannot_support"]),
        })
    return out


def get_method(method_id: str, registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = registry or load_registry()
    for method in data["methods"]:
        if method["id"] == method_id:
            return method
    known = ", ".join(item["id"] for item in data["methods"])
    raise MethodRegistryError("unknown method: {0}; known: {1}".format(method_id, known))


def matrix(registry: Optional[Dict[str, Any]] = None, stage: Optional[str] = None) -> Dict[str, Any]:
    """Stage x method projection. A cell is the task the method imposes at that stage."""
    data = registry or load_registry()
    known = stage_ids(data)
    if stage is not None and stage not in known:
        raise MethodRegistryError("unknown stage: {0}; known: {1}".format(stage, ", ".join(known)))
    rows = []
    for stage_id in known:
        if stage is not None and stage_id != stage:
            continue
        cells = []
        for method in data["methods"]:
            if stage_id not in method["fit_stages"]:
                continue
            cells.append({
                "method": method["id"],
                "task": method["stage_tasks"].get(stage_id, ""),
                "checks": [check["id"] for check in method["checks"]],
            })
        rows.append({"stage": stage_id, "cells": cells})
    return {"schema": "ese-method-matrix-0.1", "stage": stage or "*", "rows": rows}


def task_card(stage: str, method_id: str, registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = registry or load_registry()
    method = get_method(method_id, data)
    if stage not in data_stage_ids(data):
        raise MethodRegistryError("unknown stage: {0}".format(stage))
    applicable = stage in method["fit_stages"]
    return {
        "schema": "ese-task-card-0.1",
        "stage": stage,
        "method": method["id"],
        "applicable": applicable,
        "task": method["stage_tasks"].get(stage, ""),
        "protocol_fields": list(method["protocol_fields"]),
        "artifacts": list(method["artifacts"]),
        "checks": [dict(check) for check in method["checks"]],
        "guidelines": [dict(item) for item in method["guidelines"]],
        "reporting_sections": list(method.get("reporting_sections") or []),
        "cannot_support": list(method["cannot_support"]),
        "boundary": "advisory only: the card defines what the method requires, it does not sign or block anything",
    }


def data_stage_ids(registry: Dict[str, Any]) -> List[str]:
    return [str(stage["id"]) for stage in registry["stages"]]


def _lookup(payload: Any, field: str) -> Any:
    """Dotted lookup; returns None when absent."""
    current = payload
    for part in field.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        upper = text.upper()
        if upper in ("TODO", "TBD", "N/A", "NA", "NONE"):
            return False
        # same convention as study_preregistration: TODO(...) is an unfilled promise
        if upper.startswith("TODO(") or upper.startswith("TBD("):
            return False
        return True
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    if isinstance(value, bool):
        return value
    return True


def check(method_id: str, payload: Dict[str, Any], registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Advisory check of a design/protocol payload against one method's required fields.

    Returns findings, not a gate decision. A caller may show it to a human; nothing in the
    claim / EA / closure path reads it.
    """
    data = registry or load_registry()
    method = get_method(method_id, data)
    if not isinstance(payload, dict):
        raise MethodRegistryError("payload must be an object")
    findings = []
    for rule in method["checks"]:
        missing = [field for field in rule["requires"] if not _present(_lookup(payload, field))]
        findings.append({
            "check": rule["id"],
            "severity": rule["severity"],
            "status": "missing" if missing else "pass",
            "missing": missing,
        })
    blockers = [item for item in findings if item["severity"] == "blocker" and item["status"] == "missing"]
    return {
        "schema": "ese-method-check-0.1",
        "method": method["id"],
        "status": "advisory_missing" if blockers else "advisory_ok",
        "findings": findings,
        "boundary": "advisory only; missing fields are not a gate failure and do not create or modify any Claim",
    }
