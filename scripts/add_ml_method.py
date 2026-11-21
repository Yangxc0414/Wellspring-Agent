"""One-shot migration: add the tenth method `ml-iterative-experiment`
(ML/AI 迭代实验科学) discovered via the pengsida-research skill survey
(design/158). Schema stays ese-method-registry-0.4; adds 8 new vocabulary
tags + the full method declaration. Every field is grounded in the
pengsida/learning_research practitioner methodology and Agarwal et al. 2021.
"""

import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "modules" / "method-registry" / "registry.json"

NEW_VOCABULARY = [
    {"tag": "消融实验", "definition": "逐模块移除以验证各自贡献", "basis": "ML 消融实践；pengsida learning_research（writing_template）"},
    {"tag": "最小可行实验", "definition": "二元可测标准的极简验证实验（MV 三步）", "basis": "pengsida learning_research（minimal experiment）"},
    {"tag": "一次一因素", "definition": "单次实验只改一个因素", "basis": "Freeman：only change one thing at a time"},
    {"tag": "失败案例分析", "definition": "failure case 的规律与技术原因分析", "basis": "pengsida learning_research（debug 五步定位法）"},
    {"tag": "实验日志", "definition": "目的/setting/结果/分析/next step 五要素记录", "basis": "pengsida learning_research（experiment_log）"},
    {"tag": "SOTA 对比", "definition": "与已发表最优方法的可复现对比", "basis": "writing_template：comparison experiments"},
    {"tag": "种子披露", "definition": "随机种子与统计区间披露", "basis": "Agarwal et al. 2021（statistical precipice）"},
    {"tag": "toy 实验", "definition": "保留 technical challenge 的简化 setting", "basis": "pengsida learning_research（toy experiment 原则）"},
]

NEW_METHOD = {
    "id": "ml-iterative-experiment",
    "name_zh": "机器学习迭代实验",
    "name_en": "ML Iterative Experimentation",
    "fit_stages": ["S1", "S2-S3", "S4", "S5", "S5b", "S6", "S8-S12"],
    "guidelines": [
        {
            "key": "pengsida2026",
            "citation": "Peng Sida. learning_research: A Research Methodology Handbook (52 docs). GitHub, 2026.",
            "mandates": "goal-driven roadmap、最小可行实验（MV 二元标准）、一次一因素、失败案例分析、实验日志五要素"
        },
        {
            "key": "games003",
            "citation": "Peng Sida. GAMES003: 科研基本能力课程（week1/3/5）. 2023.",
            "mandates": "写作倒排（intro/method 提前交导师改）、review 清单（五被拒因素）、实验记录与 next step"
        },
        {
            "key": "agarwal2021",
            "citation": "Agarwal et al. (2021). Deep Reinforcement Learning at the Edge of the Statistical Precipice. NeurIPS.",
            "mandates": "多种子与统计区间披露；单点比较不充分"
        }
    ],
    "protocol_fields": [
        "goal_roadmap",
        "minimal_viable_criterion",
        "toy_setting",
        "exploration_points",
        "one_factor_at_a_time",
        "primary_metric",
        "seeds",
        "ablation_plan",
        "baseline_comparison",
        "experiment_log"
    ],
    "artifacts": [
        "实验记录（目的/setting/结果/分析/next step）",
        "最小可行实验标准",
        "失败案例分析",
        "消融表",
        "对比表",
        "多种子结果"
    ],
    "cannot_support": [
        "理论证明（需形式化方法）",
        "单次实验外推为普适结论",
        "未披露种子的可复现声明",
        "因果机制（除非满足受控+随机）"
    ],
    "checks": [
        {"id": "experiment.log", "severity": "blocker", "requires": ["experiment_log", "analysis"]},
        {"id": "mv.criterion", "severity": "blocker", "requires": ["minimal_viable_criterion"]},
        {"id": "one.factor", "severity": "warn", "requires": ["experiment_log"]},
        {"id": "ablation.study", "severity": "warn", "requires": ["ablation_plan"]},
        {"id": "baseline.comparison", "severity": "warn", "requires": ["baseline_comparison"]},
        {"id": "seed.disclosure", "severity": "warn", "requires": ["seeds"]}
    ],
    "stage_tasks": {
        "S1": "先 search 再 re-search：literature tree + 蒸馏开源基线代码的 tricks",
        "S2-S3": "从新 failure case 入手收敛 idea；用 problem-driven 四问立项",
        "S4": "设计最小可行实验（MV 二元标准）与消融/对比计划；一次只探索一件事",
        "S5": "快速迭代：实验记录五要素；控制变量定位不 work 的技术原因",
        "S5b": "claim 只能基于预注册主指标与多种子区间；失败结果如实保留",
        "S6": "可视化 failure case 与消融表；图绑定实验产物",
        "S8-S12": "按 Intro 五部分倒推/正推与 Method 三元素（motivation→design→advantage）写作"
    },
    "reporting_sections": [
        "Goal 与 roadmap",
        "最小可行实验标准",
        "实验记录（含失败分析）",
        "消融与对比",
        "多种子与区间",
        "效度威胁（toy→real 差距）",
        "可宣称边界"
    ],
    "inputs": [
        "Goal roadmap 与 literature tree",
        "toy setting / 简化数据",
        "开源基线代码（蒸馏 tricks）",
        "计算预算"
    ],
    "evidence_sources": [
        "实验记录（目的/setting/结果/分析/next step）",
        "多种子测量与消融对比",
        "failure case 可视化"
    ],
    "evaluation_dimensions": [
        {"dimension": "可复现性：多种子与统计区间披露", "basis": "Agarwal et al. 2021（statistical precipice）"},
        {"dimension": "判别力：消融能否区分各模块贡献", "basis": "pengsida learning_research（ablation 实践）"},
        {"dimension": "外部效度：toy setting 到真实 setting 的迁移差距", "basis": "pengsida learning_research（toy experiment 原则）"},
        {"dimension": "迭代有效性：失败案例是否被系统分析", "basis": "pengsida learning_research（debug 五步定位法）"}
    ],
    "tags": [
        "消融实验", "最小可行实验", "一次一因素", "失败案例分析",
        "实验日志", "SOTA 对比", "种子披露", "toy 实验"
    ]
}


def main() -> None:
    with open(REGISTRY, "r", encoding="utf-8") as handle:
        registry = json.load(handle)

    assert registry["schema"] == "ese-method-registry-0.4", registry["schema"]
    ids = [m["id"] for m in registry["methods"]]
    assert "ml-iterative-experiment" not in ids, "already migrated"

    vocab_tags = {item["tag"] for item in registry["tag_vocabulary"]}
    unknown = [t for t in NEW_METHOD["tags"] if t not in vocab_tags]
    registry["tag_vocabulary"].extend([item for item in NEW_VOCABULARY if item["tag"] not in vocab_tags])
    unknown = [t for t in NEW_METHOD["tags"] if t not in {i["tag"] for i in registry["tag_vocabulary"]}]
    assert not unknown, unknown

    registry["methods"].append(NEW_METHOD)
    with open(REGISTRY, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(registry, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"methods {len(registry['methods'])}; vocabulary {len(registry['tag_vocabulary'])}; added ml-iterative-experiment")


if __name__ == "__main__":
    main()
