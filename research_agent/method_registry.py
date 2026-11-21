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

SCHEMA = "ese-method-registry-0.6"
SEVERITIES = ("blocker", "warn")

# design/166: a closed vocabulary for validity focus. The list is literature-derived
# (Cook & Campbell's four + transferability + utility + cycle + reproducibility), with
# discriminability marked as an ESE-specific engineering-experiment extension.
VALIDITY_KEYS = (
    "internal",
    "external",
    "construct",
    "statistical",
    "transferability",
    "utility",
    "cycle",
    "reproducibility",
    "discriminability",
)
ITERATION_KINDS = ("fixed", "saturation", "cycle", "convergence")

# The closed port-type vocabulary for the element/composition layer (design/156).
PORT_TYPES = (
    "研究问题",
    "候选假设（可判别）",
    "提炼式假设（事后）",
    "探索式数据收集设计",
    "判别式协议",
    "数据收集协议",
    "RunCapsule + EA",
    "ClaimRecord",
    "图 manifest",
    "稿件绑定",
    "closure + 导出",
    "任务反馈",
)

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

    known_stage_ids = []
    for stage in stages:
        stage_id = str(stage.get("id") or "")
        _require(bool(stage_id), "stage id cannot be empty")
        _require(stage_id not in known_stage_ids, "duplicate stage id: " + stage_id)
        known_stage_ids.append(stage_id)

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
        unknown = [stage for stage in fit if stage not in known_stage_ids]
        _require(not unknown, method_id + ": unknown stages " + ", ".join(unknown))
        for key in ("guidelines", "protocol_fields", "artifacts", "cannot_support", "checks",
                    "inputs", "evidence_sources", "evaluation_dimensions"):
            _require(isinstance(method.get(key), list), method_id + ": " + key + " must be a list")
        _require(bool(method.get("inputs")), method_id + ": inputs is required (design/153)")
        _require(bool(method.get("evidence_sources")), method_id + ": evidence_sources is required (design/153)")
        _require(
            bool(method.get("evaluation_dimensions")),
            method_id + ": evaluation_dimensions is required (design/153)",
        )
        for dim in method["evaluation_dimensions"]:
            _require(
                bool(str(dim.get("dimension") or "")) and bool(str(dim.get("basis") or "")),
                method_id + ": evaluation dimension needs dimension/basis",
            )
        _require(isinstance(method.get("stage_tasks"), dict), method_id + ": stage_tasks must be an object")
        _require(bool(method.get("guidelines")), method_id + ": at least one guideline is required")
        _require(bool(method.get("cannot_support")), method_id + ": cannot_support is required")
        _require(bool(method.get("checks")), method_id + ": at least one check is required")
        focus = method.get("validity_focus")
        _require(isinstance(focus, dict), method_id + ": validity_focus required (design/166)")
        _require(focus.get("primary") in VALIDITY_KEYS, method_id + ": unknown primary validity")
        secondary = focus.get("secondary")
        _require(isinstance(secondary, list), method_id + ": validity_focus.secondary must be a list")
        unknown_secondary = [key for key in secondary if key not in VALIDITY_KEYS]
        _require(not unknown_secondary, method_id + ": unknown secondary validity " + ", ".join(unknown_secondary))
        _require(focus["primary"] not in secondary, method_id + ": primary must not repeat in secondary")
        rule = method.get("iteration_rule")
        _require(isinstance(rule, dict), method_id + ": iteration_rule required (design/166)")
        _require(rule.get("kind") in ITERATION_KINDS, method_id + ": unknown iteration kind")
        _require(bool(str(rule.get("detail") or "")), method_id + ": iteration_rule detail required")
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
    # design/155: the tag layer — a shared vocabulary plus per-method tags, so
    # commonality/difference extraction is reproducible data, not intuition.
    vocabulary = registry.get("tag_vocabulary")
    _require(isinstance(vocabulary, list) and vocabulary, "registry needs a tag_vocabulary list")
    vocab_tags = []
    for entry in vocabulary:
        tag = str(entry.get("tag") or "")
        _require(bool(tag), "vocabulary tag cannot be empty")
        _require(bool(str(entry.get("definition") or "")), tag + ": definition required")
        _require(bool(str(entry.get("basis") or "")), tag + ": basis required")
        _require(tag not in vocab_tags, "duplicate vocabulary tag: " + tag)
        vocab_tags.append(tag)
    for method in methods:
        mid = str(method.get("id") or "")
        tags = method.get("tags")
        _require(isinstance(tags, list) and tags, mid + ": tags must be a non-empty list")
        unknown = [tag for tag in tags if tag not in vocab_tags]
        _require(not unknown, mid + ": tags missing from vocabulary: " + ", ".join(unknown))

    # design/166: validity vocabulary must cover the closed key set exactly.
    validity = registry.get("validity_vocabulary")
    _require(isinstance(validity, list) and validity, "registry needs a validity_vocabulary list")
    seen_validity = []
    for entry in validity:
        key = str(entry.get("key") or "")
        _require(key in VALIDITY_KEYS, "unknown validity key: " + key)
        _require(key not in seen_validity, "duplicate validity key: " + key)
        for field in ("name_zh", "definition", "basis"):
            _require(bool(str(entry.get(field) or "")), key + ": " + field + " required")
        seen_validity.append(key)
    missing_validity = [key for key in VALIDITY_KEYS if key not in seen_validity]
    _require(not missing_validity, "validity vocabulary missing: " + ", ".join(missing_validity))

    # design/156: the element/composition layer — the meta-model (elements with
    # typed ports) plus reference wirings, all fail-closed so the "framework is
    # data" claim is backed by an executable loader.
    elements_list = registry.get("elements")
    _require(isinstance(elements_list, list) and elements_list, "registry needs an elements list")
    elements = {}
    for element in elements_list:
        element_id = str(element.get("id") or "")
        _require(bool(element_id), "element id cannot be empty")
        _require(element_id not in elements, "duplicate element id: " + element_id)
        elements[element_id] = element
        _require(bool(str(element.get("label") or "")), element_id + ": label required")
        input_kinds = element.get("input_kinds")
        _require(isinstance(input_kinds, list), element_id + ": input_kinds must be a list")
        for kind in input_kinds:
            _require(kind in PORT_TYPES, element_id + ": unknown input port " + str(kind))
        outputs = element.get("outputs")
        _require(isinstance(outputs, list) and outputs, element_id + ": outputs must be non-empty")
        for rule in outputs:
            consumes = rule.get("consumes")
            produces = rule.get("produces")
            _require(consumes is None or consumes in PORT_TYPES, element_id + ": unknown consumes port")
            _require(produces in PORT_TYPES, element_id + ": unknown produces port")
            _require(
                consumes is None or consumes in input_kinds,
                element_id + ": output rule consumes undeclared input " + str(consumes),
            )
        _require(isinstance(element.get("human"), bool), element_id + ": human must be bool")

    compositions = registry.get("compositions")
    _require(isinstance(compositions, list) and compositions, "registry needs compositions")
    composition_slot_maps = {}
    composition_ids = []
    for composition in compositions:
        composition_id = str(composition.get("id") or "")
        _require(bool(composition_id), "composition id cannot be empty")
        _require(composition_id not in composition_ids, "duplicate composition id: " + composition_id)
        composition_ids.append(composition_id)
        wiring = composition.get("wiring")
        _require(isinstance(wiring, list) and wiring, composition_id + ": wiring must be non-empty")
        slot_map = composition.get("slot_map")
        _require(isinstance(slot_map, dict) and slot_map, composition_id + ": slot_map required")
        for element_id, slots in slot_map.items():
            _require(element_id in elements, composition_id + ": slot_map for unknown element " + element_id)
            _require(isinstance(slots, list) and slots, composition_id + ": slot_map slots must be non-empty")
            for slot in slots:
                _require(slot in known_stage_ids, composition_id + ": slot_map has unknown stage " + str(slot))
        composition_slot_maps[composition_id] = slot_map
        available = ["研究问题"]
        for index, step in enumerate(wiring):
            element_id = str(step.get("element") or "")
            _require(element_id in elements, composition_id + ": wiring references unknown element " + element_id)
            element = elements[element_id]
            consumed = step.get("consumes")
            if consumed:
                _require(
                    consumed in element["input_kinds"],
                    composition_id + ": element " + element_id + " does not declare port " + str(consumed),
                )
                _require(
                    consumed in available,
                    composition_id + ": port " + str(consumed) + " has not been produced upstream",
                )
            _require(
                bool(str(step.get("rationale") or "")),
                composition_id + ": wiring step " + element_id + " needs rationale (design/166)",
            )
            rule = None
            for candidate in element["outputs"]:
                if candidate.get("consumes") == consumed:
                    rule = candidate
                    break
            _require(rule is not None, composition_id + ": no output rule for " + str(consumed))
            if rule["produces"] not in available:
                available.append(rule["produces"])
    not_research = registry.get("not_research")
    _require(isinstance(not_research, list) and not_research, "registry needs a not_research boundary list")
    boundary_ids = []
    for entry in not_research:
        entry_id = str(entry.get("id") or "")
        _require(bool(entry_id), "not_research id required")
        _require(entry_id not in boundary_ids, "duplicate not_research id: " + entry_id)
        boundary_ids.append(entry_id)
        for field in ("label", "missing", "why"):
            _require(bool(str(entry.get(field) or "")), entry_id + ": " + field + " required")

    for method in methods:
        mid = str(method.get("id") or "")
        binding = method.get("composition_id")
        _require(binding in composition_slot_maps, mid + ": composition_id must reference a composition")
        for slot in method["fit_stages"]:
            _require(
                any(slot in slots for element, slots in composition_slot_maps[binding].items()),
                mid + ": fit stage " + str(slot) + " not walked by composition " + str(binding),
            )
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


def stage_plan(method_id: str, registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resolve a method's composition wiring into its ordered stage plan
    (design/162): per slot, the methodology-constrained task card. Fit slots
    not walked by the composition are appended in canonical order with an
    uncovered marker — the honest extension seam."""
    data = registry or load_registry()
    method = get_method(method_id, data)
    composition = next(
        (item for item in data.get("compositions", []) if item["id"] == method.get("composition_id")),
        None,
    )
    if composition is None:
        raise MethodRegistryError("method has no composition binding: " + method_id)
    slot_map = composition.get("slot_map", {})
    fit = list(method["fit_stages"])
    tasks = method.get("stage_tasks", {})
    stages = []
    seen = set()
    for step in composition["wiring"]:
        for slot in slot_map.get(step["element"], []):
            if slot in fit and slot not in seen:
                seen.add(slot)
                stages.append({"slot": slot, "task": tasks.get(slot, "")})
    uncovered = [slot for slot in fit if slot not in seen]
    for slot in uncovered:
        stages.append({"slot": slot, "task": tasks.get(slot, ""), "uncovered": True})
    return {
        "method": method_id,
        "composition": composition["id"],
        "label": composition["label"],
        "stages": stages,
        "uncovered": uncovered,
    }


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


def get_composition(composition_id: str, registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = registry or load_registry()
    for composition in data.get("compositions", []):
        if composition["id"] == composition_id:
            return composition
    known = ", ".join(item["id"] for item in data.get("compositions", []))
    raise MethodRegistryError("unknown composition: {0}; known: {1}".format(composition_id, known))


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


def pipeline_stage_plan(method_id: str, registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resolve a method's composition into pipeline stage names (design/164).

    Maps governance slots to the pipeline's stage names. Advisory only: the
    runner records the covered set and emits stage_skip events; it does not
    actually skip code blocks yet (that migration is SPEC-first roadmap).
    """
    plan = stage_plan(method_id, registry)
    slot_to_stage = {
        "S1": "literature",
        "S1b": "literature",
        "S2-S3": "idea",
        "S4": "experiment",
        "S5": "run",
        "S5b": "run",
        "S6": "figure",
        "S8-S12": "paper",
    }
    covered = set()
    for step in plan["stages"]:
        stage = slot_to_stage.get(step["slot"])
        if stage:
            covered.add(stage)
    return {
        "method": method_id,
        "composition": plan["composition"],
        "label": plan["label"],
        "covered_stages": sorted(covered),
        "plan": plan["stages"],
    }


def method_diff(a: str, b: str, registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Explain the essential difference between two methods (design/166).

    Compares the three places a method difference should live: validity focus,
    evidence sources, and the order its composition walks the governance slots.
    Returns structure, not a ranking: no method is "better" and nothing here
    creates a Claim.
    """
    data = registry or load_registry()
    left = get_method(a, data)
    right = get_method(b, data)
    lv = left["validity_focus"]
    rv = right["validity_focus"]
    left_evidence = set(left["evidence_sources"])
    right_evidence = set(right["evidence_sources"])
    left_plan = stage_plan(a, data)
    right_plan = stage_plan(b, data)
    left_slots = [step["slot"] for step in left_plan["stages"]]
    right_slots = [step["slot"] for step in right_plan["stages"]]
    divergence = None
    for index in range(min(len(left_slots), len(right_slots))):
        if left_slots[index] != right_slots[index]:
            divergence = {"index": index, "a": left_slots[index], "b": right_slots[index]}
            break
    return {
        "schema": "ese-method-diff-0.1",
        "a": {"id": a, "name": left["name_zh"], "composition": left_plan["composition"]},
        "b": {"id": b, "name": right["name_zh"], "composition": right_plan["composition"]},
        "validity": {
            "a": lv["primary"],
            "b": rv["primary"],
            "same": lv["primary"] == rv["primary"],
            "a_secondary": list(lv["secondary"]),
            "b_secondary": list(rv["secondary"]),
        },
        "evidence": {
            "only_a": sorted(left_evidence - right_evidence),
            "only_b": sorted(right_evidence - left_evidence),
            "shared": sorted(left_evidence & right_evidence),
        },
        "order": {
            "a": left_slots,
            "b": right_slots,
            "same": left_slots == right_slots,
            "first_divergence": divergence,
        },
        "iteration": {
            "a": dict(left["iteration_rule"]),
            "b": dict(right["iteration_rule"]),
            "same": left["iteration_rule"]["kind"] == right["iteration_rule"]["kind"],
        },
        "boundary": "structural difference only; no method is ranked and no Claim is created",
    }
