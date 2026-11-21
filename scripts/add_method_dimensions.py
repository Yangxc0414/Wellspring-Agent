"""One-shot migration: add inputs / evidence_sources / evaluation_dimensions
to every method in modules/method-registry/registry.json (schema 0.1 -> 0.2).

Every entry is grounded in established empirical-methodology literature
(Kitchenham 2007, Wohlin 2014, Runeson & Höst 2009, Cook & Campbell 1979,
Hevner 2004, Susman & Evered 1978, Easterbrook et al. 2008) and in the
registry's own cannot_support/threat_focus/checks fields.
"""

import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "modules" / "method-registry" / "registry.json"

# method_id -> three dimensions. 评估维度 entries carry a literature basis each.
DIMENSIONS = {
    "systematic-literature-review": {
        "inputs": [
            "研究问题（RQ）",
            "检索协议：检索式 / 数据库 / 检索日期",
            "纳入与排除标准",
            "质量评估清单",
        ],
        "evidence_sources": [
            "已发表研究全文（期刊 / 会议）",
            "预印本与灰色文献（显式声明）",
            "各原始研究自身报告的数据（二手证据）",
        ],
        "evaluation_dimensions": [
            {"dimension": "可复现性：检索与筛选可被他人重放", "basis": "Kitchenham 2007 §协议与检索策略"},
            {"dimension": "筛选一致性：多人按标准筛选并报告数量流", "basis": "PRISMA 2020（识别/筛选/纳入）"},
            {"dimension": "外部效度受原始研究集合限制", "basis": "Wohlin 2014（滚雪球与数据库合并）"},
        ],
    },
    "repository-mining": {
        "inputs": [
            "抽样框与项目选择规则",
            "时间窗与时间切分定义",
            "标签来源（path/message 启发式）",
            "抽取脚本与许可证核对",
        ],
        "evidence_sources": [
            "代码仓库历史（commit / issue / PR 记录）",
            "仓库元数据与镜像快照（sha 固定）",
        ],
        "evaluation_dimensions": [
            {"dimension": "构造效度：标签启发式是否测到目标构念", "basis": "threat_focus=construct；capsule warning"},
            {"dimension": "可复现性：重复运行必须得到同一快照", "basis": "run contract：evidence.hash / artifacts.required"},
            {"dimension": "外部效度：语言 / 生态 / 时间窗范围", "basis": "threat_focus=external；claim scope 规则"},
            {"dimension": "内部因果效度不可支持（观察性）", "basis": "cannot_support：因果机制"},
        ],
    },
    "controlled-experiment": {
        "inputs": [
            "可操控因子与水平的假设",
            "随机化与区组计划",
            "样本量与功效分析",
            "分析计划与停止规则",
        ],
        "evidence_sources": [
            "受控环境下对实验单元的一手测量",
            "分配与偏离记录（随机化留痕）",
        ],
        "evaluation_dimensions": [
            {"dimension": "内部效度：因果来自控制 + 随机", "basis": "Cook & Campbell 1979；Wohlin 2014 效度框架"},
            {"dimension": "统计结论效度：功效与检验", "basis": "experiment.power / experiment.analysis_plan 检查"},
            {"dimension": "构念效度：任务是否代表目标构念", "basis": "threat_focus=construct"},
            {"dimension": "外部效度：单元与情境的推广范围", "basis": "threat_focus=external"},
        ],
    },
    "quasi-experiment": {
        "inputs": [
            "处理定义与对照条件",
            "分配规则（非随机）",
            "混杂变量清单",
            "识别策略",
        ],
        "evidence_sources": [
            "自然发生分组条件下的一手测量",
            "处理前后 / 组间可比数据",
        ],
        "evaluation_dimensions": [
            {"dimension": "内部效度：选择偏倚是首要威胁", "basis": "Cook & Campbell 1979"},
            {"dimension": "识别策略的有效性", "basis": "threat_focus=internal；quasi.identification 检查"},
            {"dimension": "敏感性分析", "basis": "quasi.sensitivity 检查"},
        ],
    },
    "benchmark-evaluation": {
        "inputs": [
            "基准数据集及版本（哈希）",
            "被评系统与配置",
            "预算匹配策略",
            "基线与复现记录",
        ],
        "evidence_sources": [
            "标准化任务上的自动评分（固定任务集）",
            "污染检查记录",
        ],
        "evaluation_dimensions": [
            {"dimension": "构造效度：基准是否测到宣称的能力", "basis": "threat_focus=construct"},
            {"dimension": "污染控制", "basis": "benchmark.contamination 检查"},
            {"dimension": "饱和 / headroom", "basis": "benchmark.saturation 检查"},
            {"dimension": "跨基准的无条件排名不可支持", "basis": "cannot_support"},
        ],
    },
    "case-study": {
        "inputs": [
            "研究问题与案例选择协议",
            "多源数据源清单（访谈 / 文档 / 制品）",
            "分析策略与编码本",
        ],
        "evidence_sources": [
            "访谈与观察记录",
            "项目文档与制品",
            "三角验证的多源对照",
        ],
        "evaluation_dimensions": [
            {"dimension": "构造效度：三角验证与链式证据", "basis": "Runeson & Höst 2009 §效度讨论"},
            {"dimension": "可转移性（非统计泛化）", "basis": "threat_focus=external；cannot_support"},
            {"dimension": "成员核查（member checking）", "basis": "case.member_checking 检查"},
        ],
    },
    "survey": {
        "inputs": [
            "总体与抽样框",
            "问卷 / 访谈提纲（预试记录）",
            "知情同意与响应率计划",
        ],
        "evidence_sources": [
            "人群自报应答（问卷 / 访谈）",
        ],
        "evaluation_dimensions": [
            {"dimension": "构念效度：题目测到目标构念", "basis": "threat_focus=construct；survey.instrument 检查"},
            {"dimension": "无应答与响应偏倚（代表性）", "basis": "cannot_support：未响应者代表性"},
            {"dimension": "行为因果不可支持（自报局限）", "basis": "cannot_support：行为因果"},
        ],
    },
    "design-science": {
        "inputs": [
            "设计问题与需求",
            "知识基准（已有制品 / 理论）",
            "利益相关者",
        ],
        "evidence_sources": [
            "制品演示与评估记录（可混合实验 / 案例 / 模拟）",
            "设计过程与理由",
        ],
        "evaluation_dimensions": [
            {"dimension": "效用评估限于评估策略所及", "basis": "cannot_support：未评估的效用声明"},
            {"dimension": "贡献类型清晰度", "basis": "dsr.contribution 检查"},
            {"dimension": "边界条件声明", "basis": "protocol_fields：boundary_conditions"},
        ],
    },
    "action-research": {
        "inputs": [
            "介入计划与利益相关者",
            "研究者角色声明",
            "伦理审查",
        ],
        "evidence_sources": [
            "介入循环中的行动与反思记录",
            "利益相关者反馈",
        ],
        "evaluation_dimensions": [
            {"dimension": "循环完整性：诊断→行动→评估→反思", "basis": "action.cycles 检查；Susman & Evered 1978"},
            {"dimension": "研究者角色透明度", "basis": "action.role 检查"},
            {"dimension": "无介入的因果归因不可支持", "basis": "cannot_support"},
        ],
    },
}


def main() -> None:
    with open(REGISTRY, "r", encoding="utf-8") as handle:
        registry = json.load(handle)

    assert registry["schema"] == "ese-method-registry-0.1", registry["schema"]
    updated = 0
    for method in registry["methods"]:
        dims = DIMENSIONS.get(method["id"])
        if dims is None:
            raise SystemExit("missing dimensions for " + method["id"])
        method["inputs"] = dims["inputs"]
        method["evidence_sources"] = dims["evidence_sources"]
        method["evaluation_dimensions"] = [
            {"dimension": item["dimension"], "basis": item["basis"]}
            for item in dims["evaluation_dimensions"]
        ]
        updated += 1

    registry["schema"] = "ese-method-registry-0.2"
    with open(REGISTRY, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(registry, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"updated {updated} methods; schema -> ese-method-registry-0.2")


if __name__ == "__main__":
    main()
