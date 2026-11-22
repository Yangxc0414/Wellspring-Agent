"""元模型驱动的编排：从端口契约推导顺序，并生成阶段执行契约（design/177）。

设计要点（与 174 正交）：
- 174 回答"跑哪些阶段"（方法 fit_stages → covered）；
- 本模块回答"按什么顺序跑、每阶段要满足什么"（元模型端口 → 拓扑序 + 契约）。

契约不是新的事实源，而是元模型 + 方法数据的投影：
  requires/produces ← elements[].input_kinds/outputs
  human            ← elements[].human
  gate             ← 阶段到治理门的固定映射（不由方法决定）
  iteration        ← method.iteration_rule
  tasks            ← method.stage_tasks（该阶段才有）
  checks           ← method.checks（按阶段归属过滤）

只读、不产生 Claim、不读门禁、不改注册表。
"""

from typing import Any, Dict, List, Optional, Set

# 治理门与阶段的固定映射：门是治理层，不由方法或接线决定（design/163 不变层）。
# 依据 ARCHITECTURE.md 的 human gates（Q0/G1/G2/S5b/G5）：
#   Q0 覆盖问题与证据范围；G1 假设选择；G2 协议冻结；S5b 人签判定；G5 导出闭包。
# 执行（S5）与图表（S6）本身不是门；写作（S8-S12）完成后才进入 G5 闭包。
STAGE_GATE: Dict[str, str] = {
    "S0": "Q0",
    "S1": "Q0",
    "S1b": "Q0",
    "S2-S3": "G1",
    "S4": "G2",
    "S5": "",
    "S5b": "S5b",
    "S6": "",
    "S8-S12": "G5",
    "S13-S16": "G5",
}

# 元模型要素 -> pipeline 阶段（与 method_registry.pipeline_stage_plan 的映射保持一致）。
SLOT_TO_STAGE: Dict[str, str] = {
    "S0": "composition",
    "S1": "literature",
    "S1b": "literature",
    "S2-S3": "idea",
    "S4": "experiment",
    "S5": "run",
    "S5b": "run",
    "S6": "figure",
    "S8-S12": "paper",
    "S13-S16": "closure",
}


class OrchestrationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OrchestrationError(message)


def _element_index(registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(e.get("id") or ""): e for e in (registry.get("elements") or [])}


def _production_rule(element: Dict[str, Any], consumed: Optional[str]) -> str:
    """给定该 element 的一条输入端口，返回它对应的输出端口。"""
    for rule in element.get("outputs") or []:
        if rule.get("consumes") == consumed:
            produced = rule.get("produces")
            if produced:
                return str(produced)
    raise OrchestrationError(
        "element %s has no output rule for consumes=%s" % (element.get("id"), consumed)
    )


def topological_order(composition: Dict[str, Any], registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """按端口依赖推导 wiring 的执行顺序（Kahn），返回有序 step 列表。

    wiring 本身已由 validate() 保证"声明顺序满足依赖"；本函数做的是**显式推导**：
    依赖边 = 产出某端口的 step -> 消费该端口的 step。若出现环，fail-closed。
    """
    steps = list(composition.get("wiring") or [])
    _require(bool(steps), "composition %s has empty wiring" % composition.get("id"))
    elements = _element_index(registry)

    produced_by: Dict[str, int] = {}  # port -> step index
    edges: List[Set[int]] = [set() for _ in steps]
    indegree = [0] * len(steps)

    for index, step in enumerate(steps):
        element_id = str(step.get("element") or "")
        element = elements.get(element_id)
        _require(element is not None, "unknown element %s" % element_id)
        consumed = step.get("consumes")
        if consumed:
            upstream = produced_by.get(str(consumed))
            _require(
                upstream is not None,
                "composition %s: port %s consumed by %s has no upstream producer"
                % (composition.get("id"), consumed, element_id),
            )
            if upstream not in edges[index]:
                edges[upstream].add(index)
                indegree[index] += 1
        produced = _production_rule(element, consumed)
        # 同一端口可能被多个 element 产出（如 RunCapsule+EA）；后写覆盖不影响依赖，
        # 因为消费方只需要"至少一个上游"，而 validate 已保证声明顺序合法。
        produced_by.setdefault(produced, index)

    ready = [i for i, degree in enumerate(indegree) if degree == 0]
    ordered: List[Dict[str, Any]] = []
    visited = 0
    while ready:
        current = ready.pop(0)
        ordered.append(dict(steps[current], _index=current))
        visited += 1
        for downstream in sorted(edges[current]):
            indegree[downstream] -= 1
            if indegree[downstream] == 0:
                ready.append(downstream)
        ready.sort()

    _require(
        visited == len(steps),
        "composition %s has a port-dependency cycle; orchestration refuses to guess an order"
        % composition.get("id"),
    )
    return ordered


def _checks_for_stage(method: Dict[str, Any], stage: str) -> List[str]:
    """按 check id 前缀把检查归到**唯一**阶段；不做模糊归属。

    规则：每个 check 只归一个阶段（先匹配先得），避免同一个 check 在多个阶段重复出现。
    未匹配的 check 不强行塞进任何阶段——契约里看不到就是看不到，不伪造完整性。
    """
    prefix_to_stage = {
        "slr.protocol": "S1",
        "slr.reproducible_search": "S1",
        "slr.screening_agreement": "S1",
        "slr.quality": "S1b",
        "mining.sampling_frame": "S1",
        "mining.time_split": "S1",
        "mining.dedup": "S1",
        "mining.license": "S1",
        "mining.label_source": "S5",
        "mining.analysis": "S5b",
        "case.questions": "S1",
        "case.selection": "S1",
        "case.triangulation": "S5",
        "case.ethics": "S1",
        "case.member_checking": "S5",
        "experiment.hypothesis": "S2-S3",
        "experiment.design": "S4",
        "experiment.power": "S4",
        "experiment.analysis_plan": "S4",
        "experiment.randomization": "S4",
    }
    result: List[str] = []
    for check in method.get("checks") or []:
        check_id = str(check.get("id") or "")
        if prefix_to_stage.get(check_id) == stage:
            result.append(check_id)
    return result


def stage_contracts(method_id: str, registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """生成该方法的有序阶段执行契约（元模型 + 方法数据的投影）。"""
    methods = {str(m.get("id") or ""): m for m in (registry.get("methods") or [])}
    compositions = {str(c.get("id") or ""): c for c in (registry.get("compositions") or [])}
    method = methods.get(method_id)
    _require(method is not None, "unknown method %s" % method_id)
    composition = compositions.get(str(method.get("composition_id") or ""))
    _require(composition is not None, "method %s has unknown composition" % method_id)
    elements = _element_index(registry)
    fit = set(str(x) for x in (method.get("fit_stages") or []))
    slot_map = composition.get("slot_map") or {}

    contracts: List[Dict[str, Any]] = []
    seen_stages: Set[str] = set()
    for step in topological_order(composition, registry):
        element_id = str(step.get("element") or "")
        element = elements[element_id]
        slots = [str(s) for s in (slot_map.get(element_id) or [])]
        if not slots:
            continue
        for slot in slots:
            if slot in seen_stages:
                continue
            seen_stages.add(slot)
            covered = slot in fit
            contract = {
                "stage": slot,
                "element": element_id,
                "requires": list(element.get("input_kinds") or []),
                "produces": [
                    str(rule.get("produces")) for rule in (element.get("outputs") or []) if rule.get("produces")
                ],
                "human": bool(element.get("human")),
                "gate": STAGE_GATE.get(slot, ""),
                "iteration": dict(method.get("iteration_rule") or {}),
                "tasks": str((method.get("stage_tasks") or {}).get(slot) or ""),
                "checks": _checks_for_stage(method, slot),
                "locked_outputs": [
                    str(rule.get("produces")) for rule in (element.get("outputs") or []) if rule.get("produces")
                ] if element.get("human") else [],
                "covered": covered,
                "not_applicable_reason": "" if covered else
                "stage not in method %s fit_stages; orchestration skips it (design/174)" % method_id,
            }
            contracts.append(contract)
    return contracts


def orchestration_plan(method_id: str, registry: Dict[str, Any]) -> Dict[str, Any]:
    """完整编排计划：有序阶段 + 契约 + 端口依赖边，供 stage_plan 与前端消费。"""
    plan = stage_contracts(method_id, registry)
    methods = {str(m.get("id") or ""): m for m in (registry.get("methods") or [])}
    compositions = {str(c.get("id") or ""): c for c in (registry.get("compositions") or [])}
    method = methods[method_id]
    composition = compositions[str(method.get("composition_id") or "")]
    order = topological_order(composition, registry)

    edges: List[Dict[str, str]] = []
    elements = _element_index(registry)
    produced: Dict[str, str] = {}
    for step in order:
        element_id = str(step.get("element") or "")
        consumed = step.get("consumes")
        if consumed and str(consumed) in produced:
            edges.append({"from": produced[str(consumed)], "to": element_id, "port": str(consumed)})
        produced.setdefault(_production_rule(elements[element_id], consumed), element_id)

    return {
        "schema": "ese-orchestration-plan-0.1",
        "method": method_id,
        "composition": str(method.get("composition_id") or ""),
        # full_order 是完整接线序（含本方法不覆盖的要素），解释"为什么跳过"；
        # order 是本次实际会走的要素序（只含 covered），用于前端呈现与后续执行器消费。
        "full_order": [str(step.get("element")) for step in order],
        "order": [
            str(step.get("element"))
            for step in order
            if any(c["element"] == str(step.get("element")) and c["covered"] for c in plan)
        ],
        "contracts": plan,
        "edges": edges,
        "boundary": (
            "read-only projection of elements + method data; it does not reorder the pipeline's "
            "code blocks (design/174 §5), does not read gates and produces no Claim"
        ),
    }
