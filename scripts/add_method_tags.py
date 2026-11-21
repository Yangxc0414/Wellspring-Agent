"""One-shot migration: tag-ify the method registry (design/155).

Adds a shared tag vocabulary (top-level `tag_vocabulary`) and per-method
`tags` (design/154 -> the advisor's assigned todo: 标签化梳理 each method's
steps, then extract commonality/difference REPRODUCIBLY instead of by
intuition). Every tag grounding points at a field or check the method
ALREADY registers — no invented structure.
"""

import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "modules" / "method-registry" / "registry.json"

# Shared vocabulary: tag -> {definition, basis}. The basis cites the
# methodology literature or the registry's own check ids.
VOCABULARY = [
    {"tag": "预注册协议", "definition": "分析计划先于数据收集/筛选冻结", "basis": "Wohlin 2014（实验预注册）；Kitchenham 2007（SLR 协议）"},
    {"tag": "随机化", "definition": "单元到条件的分配由随机机制决定", "basis": "实验两要素之一（受控+随机）；Wohlin 2014"},
    {"tag": "对照组", "definition": "存在明确的对照条件", "basis": "受控/准实验协议字段（comparison_group）"},
    {"tag": "区组", "definition": "按已知干扰因素分组分配", "basis": "受控实验协议字段（blocking）"},
    {"tag": "功效分析", "definition": "样本量与统计功效的事前计算", "basis": "受控实验检查 experiment.power"},
    {"tag": "停止规则", "definition": "数据收集/实验终止的事前条件", "basis": "受控实验协议字段（stopping_rule）"},
    {"tag": "抽样框", "definition": "明确的总体与抽样单位清单", "basis": "survey/mining 协议字段（sampling_frame）"},
    {"tag": "时间切分", "definition": "按时间划分观察窗口", "basis": "mining 协议字段（time_split）"},
    {"tag": "去重策略", "definition": "记录去重规则的事前声明", "basis": "mining 协议字段（dedup_policy）"},
    {"tag": "标签启发式声明", "definition": "标签来源与局限的显式声明", "basis": "mining 协议字段（label_source）；capsule warning"},
    {"tag": "许可核对", "definition": "数据许可合规检查", "basis": "mining 协议字段（license_check）"},
    {"tag": "快照哈希", "definition": "数据/脚本快照以哈希固定", "basis": "mining stage_tasks S5；run contract evidence.hash"},
    {"tag": "污染控制", "definition": "评测数据污染检查", "basis": "benchmark 检查 benchmark.contamination"},
    {"tag": "饱和分析", "definition": "基准 headroom（剩余提升空间）分析", "basis": "benchmark 协议字段（saturation_note）"},
    {"tag": "多重比较策略", "definition": "多次比较的校正策略", "basis": "benchmark 协议字段（multiple_comparison_policy）"},
    {"tag": "质量评估", "definition": "纳入研究的质量评估", "basis": "SLR 协议字段（quality_assessment）"},
    {"tag": "筛选标准", "definition": "纳入/排除标准的事前声明", "basis": "SLR 协议字段（inclusion/exclusion_criteria）"},
    {"tag": "综合矩阵", "definition": "证据抽取与综合的结构化载体", "basis": "SLR 产物（综合矩阵/synthesis_method）"},
    {"tag": "三角验证", "definition": "多源证据交叉印证", "basis": "案例研究协议字段（triangulation）"},
    {"tag": "链式证据", "definition": "从原始数据到结论的可追溯链", "basis": "案例研究协议字段（chain_of_evidence）"},
    {"tag": "编码本", "definition": "定性编码规则", "basis": "案例研究产物（编码本）"},
    {"tag": "成员核查", "definition": "由被研究者核查结论", "basis": "案例研究检查 case.member_checking"},
    {"tag": "案例选择协议", "definition": "案例选择理由与标准的事前声明", "basis": "案例研究协议字段（case_selection）"},
    {"tag": "伦理审查", "definition": "伦理 / 知情同意核查", "basis": "case/ethics、survey/consent、action/ethics 检查"},
    {"tag": "识别策略", "definition": "观察数据中的因果识别方法", "basis": "准实验协议字段（identification_strategy）"},
    {"tag": "混杂清单", "definition": "混杂变量显式登记", "basis": "准实验协议字段（confounders）"},
    {"tag": "敏感性分析", "definition": "结论对假设的敏感度检验", "basis": "准实验检查 quasi.sensitivity"},
    {"tag": "贡献声明", "definition": "制品贡献类型的显式声明", "basis": "DSR 协议字段（contribution_type）"},
    {"tag": "边界条件", "definition": "制品有效边界的声明", "basis": "DSR 协议字段（boundary_conditions）"},
    {"tag": "介入循环", "definition": "诊断→行动→评估→反思的循环结构", "basis": "行动研究协议字段（cycles）；Susman & Evered 1978"},
    {"tag": "研究者角色声明", "definition": "研究者在介入中的角色披露", "basis": "行动研究协议字段（researcher_role）"},
    {"tag": "预试记录", "definition": "测量工具的试测记录", "basis": "survey 协议字段（pilot）"},
]

# method_id -> curated tags. Every tag is grounded in a field/check the method
# ALREADY registers (protocol_fields / stage_tasks / checks listed verbatim in
# the registry); curation is the advisor's 标签化梳理 step made reproducible.
METHOD_TAGS = {
    "systematic-literature-review": [
        "预注册协议", "筛选标准", "质量评估", "综合矩阵"
    ],
    "repository-mining": [
        "预注册协议", "抽样框", "时间切分", "去重策略",
        "标签启发式声明", "许可核对", "快照哈希"
    ],
    "controlled-experiment": [
        "预注册协议", "随机化", "对照组", "区组", "功效分析", "停止规则"
    ],
    "quasi-experiment": [
        "对照组", "识别策略", "混杂清单", "敏感性分析"
    ],
    "benchmark-evaluation": [
        "污染控制", "饱和分析", "多重比较策略"
    ],
    "case-study": [
        "案例选择协议", "三角验证", "链式证据", "编码本", "成员核查", "伦理审查"
    ],
    "survey": [
        "抽样框", "预试记录", "伦理审查"
    ],
    "design-science": [
        "贡献声明", "边界条件"
    ],
    "action-research": [
        "介入循环", "研究者角色声明", "伦理审查"
    ],
}


def main() -> None:
    with open(REGISTRY, "r", encoding="utf-8") as handle:
        registry = json.load(handle)

    assert registry["schema"] == "ese-method-registry-0.2", registry["schema"]
    vocab_tags = {item["tag"] for item in VOCABULARY}

    registry["schema"] = "ese-method-registry-0.3"
    registry["tag_vocabulary"] = VOCABULARY

    unknown_in_vocab = set()
    for method in registry["methods"]:
        tags = METHOD_TAGS.get(method["id"])
        if tags is None:
            raise SystemExit("missing tags for " + method["id"])
        unknown = [tag for tag in tags if tag not in vocab_tags]
        if unknown:
            unknown_in_vocab.update(unknown)
        method["tags"] = tags
    if unknown_in_vocab:
        raise SystemExit("tags missing from vocabulary: " + ", ".join(sorted(unknown_in_vocab)))

    with open(REGISTRY, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(registry, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tagged = sum(1 for method in registry["methods"] if method.get("tags"))
    print(f"vocabulary {len(VOCABULARY)} tags; tagged {tagged} methods; schema -> ese-method-registry-0.3")


if __name__ == "__main__":
    main()
