---
id: ccfa-audit
name: CCF-A 实验设计披露审计
stage: S4
version: 0.4.0
status: draft
owner: research-agent
inputs:
  - StudyDesign
  - IdeaResult
  - RunEvidence
outputs:
  - CCFADesignAudit
  - StudyDesignDraft
tools:
  - design.draft
  - design.audit
  - design.template
gates:
  - G2
invariants:
  - 只做确定性披露检查，不做同行评审、不给录用判断、不证明证据支持结论
  - study-design.json 与本地 run 设计（experiment.json）是两件事；run 设计不得被当成研究设计
  - claims 必须逐条映射到证据；beats_prior 需要调过参的基线，mechanism 需要单变量消融
  - 数据必须声明切分/泄漏检查/许可；统计必须声明 seeds、效应量、区间、多重比较、缺失数据与功效
  - disclosure_complete ≠ venue_ready：没有 collected 数据、功效分析与先前工作，不得声称可投 CCF-A
  - 不创建 Claim/EA/gate/signature/closure
---

# CCF-A 实验设计披露审计

## Purpose

把 Awesome-Journal-Skills 中 NeurIPS / ICML / ICLR 的 experiment skill 转成可执行、可复跑的确定性清单，回答两个问题：**研究设计是否披露了审稿人必须看到的东西**，以及**离 CCF-A 还差什么**。它不评价新颖性，也不替代审稿。

## Contract

- 输入：`study-design.json`（schema `study-design-0.1`），与 `experiment.json` 分离。
- 字段：question、hypothesis、claims（type ∈ beats_prior/mechanism/scales/robustness/real_world/negative + evidence）、datasets（role/splits/leakage_checks/license/coverage/data_status）、baselines（implementation/tuning/compute/compute_matched）、ablations（mechanism/single_change）、robustness（axis/plan）、compute（hardware/training_time/inference_cost/fairness）、statistics（seeds/effect_size/confidence_interval/multiplicity/missing_data/power_analysis）、prior_work、negative_results、limitations、metric_validity（可选：metric/score_ceiling/ceiling_share_by_dataset/sensitivity/decided_in/undecided_in/artifact/boundary）。
- 输出：`ccfa-design-audit-0.1`（checks、blockers、warnings、score）、`status=ready_for_g2|attention|incomplete`，以及 `ccfa.level`：
  - `disclosure_incomplete`：有 blocker；
  - `disclosure_complete`：清单通过，但没有 `data_status=collected` 或功效分析；
  - `evidence_ready`：有 collected 数据与功效分析，但先前工作/基线实现不足，或 `metric_validity.undecided_in` 非空（指标敏感性未在所有声明环境判定）；
  - `venue_ready`：以上都有。**仍不是录用判断**。
- 失败：schema 不是 study-design（例如传入 run 设计）直接 incomplete；缺字段是 blocker，弱字段是 warning。
- 命令：`python -m research_agent design audit --design <path> [--strict]`、`design template --output <path>`。
- 集成：`pipeline run --study-design-file <path>` 把研究设计写进论文的“实验设计”段；本地 iris run 只作为“协议验证”臂，不再冒充研究设计。


## Current Implementation

- `research_agent/ccfa_audit.py`：`audit_study_design` / `audit_file` / `study_design_template`；
- `research_agent/design_draft.py`：`request_study_design` 走 host-model turn（module=design），pending 返回 turn_id，回答后重跑回放并写 `study-design.json` + `study-design-audit.json`；
- `research_agent/cli_design.py`：`design draft|audit|template`，由 `cli.py` 单向 import；
- claims-to-evidence 阶梯、单变量消融、基线调参/算力/切分泄漏、功效分析、先前工作与 readiness 分级；
- `pipeline.py` 读取 `study_design_file`，把 `study_design` + audit 放进 demo，并把内容渲染到论文 setup 段（`paper.py::_study_design_text`）；
- 不联网；不读外部 skill 目录；检查规则是本仓库代码，外部 skill 只作为方法来源与文档引用。

## Boundaries

- 清单可以被“写得完整”而通过；`venue_ready` 只表示披露齐全，不表示新颖性/正确性/录用。
- 没有 collected 数据时只能到 `disclosure_complete`；fixture/planned 数据永远不能 carry venue claim。
- 不替代 G2 人审；是否冻结协议仍由人决定。
- 不生成研究设计本身：Qoder/领域模型先写，audit 只做检查。

## Minimal Change Workflow

1. 先改本文件或 `ccfa_audit.py` 的 `Contract`；
2. 升 `version` + `## Changelog`；
3. 改代码 + `tests/test_ccfa_audit.py`；
4. `python -m unittest tests.test_ccfa_audit`；命令面变化时跑 `workspace export`。

## Changelog

- 2026-10-31 · v0.4.0 · status=draft · CCF-A 设计审计把只在天花板截断指标上成立的交互判成 venue_ready：design audit 对 study-design-idea03-all.json（含 limitations 里的 ceiling 敏感性）仍给 status=ready_for_g2 / ccfa.level=venue_ready。现在新增可选 metric_validity（decided_in/undecided_in 等）；undecided_in 非空时 readiness 最高 evidence_ready，并给 metric.validity warning（不产生 blocker），设计文本必须把主张限定为该度量。实测 all-window 设计从 venue_ready 降为 attention/evidence_ready，warning 为 metric.validity。新增 1 项测试，ccfa-audit 11 项通过。契约新增可选字段，升 minor。
- 2026-10-31 · v0.3.1 · status=draft · 全局 replication=consistent 会把设计抬到 venue_ready，即使某个 claim 只在更少环境判定：IDEA-03 主效应 4/4、交互 3/4，4 环境复审仍给 venue_ready，和 claim 证据不一致。现在 readiness 取最弱 claim 的复现范围：replication 里任何 *_decided_in 列表短于 datasets 时，级别最高 evidence_ready，并给 replication.partial_claim warning。实测 IDEA-03 4 环境设计变为 status=attention / evidence_ready，warning=interaction_decided_in 3/4；主效应 4/4 仍记录为 consistent。新增 1 项测试。升 patch。
- 2026-10-31 · v0.3.0 · status=draft · CCF-A 审计会把单数据集效应判成 venue_ready：一个 design 在 breast_cancer 判定、digits/iris/wine 三个环境跨零，power_analysis.sd 写成“not estimated”，审计仍给 venue_ready、零 blocker。原因是 _readiness 只检查字段非空、且不读复现状态。现在（1）power_analysis.sd 必须含数字，not estimated/未估计不算功效声明；（2）设计可带 replication={status,datasets,decided_in}，one_dataset_decided/undecided/mixed 最高到 evidence_ready；（3）声明多个环境却没有 replication 状态也最高到 evidence_ready，并在 checks 里给 replication.scope warning。契约新增可选 replication 字段与更严的 readiness，升 minor。
- 2026-10-31 · v0.2.0 · status=draft · 研究设计走了宿主模型，不再由人/agent 手写 JSON：新增 design draft --project --run-id，读取 idea/experiment/demo 证据，向绑定的 host-agent 发一个 module=design、purpose=S4 study design 的 ModelTurn；pending 时返回 turn id，宿主用 research_model_respond 作答后重跑即回放并写入 study-design.json + study-design-audit.json。Qoder 实测：turn MT-dd24fcb6b9cc → ready_for_g2/disclosure_complete（0 blocker），随后 autopilot 完成、论文 setup 段仍是研究设计、5 段 model_draft 保留、严格审计只剩 fixture。tests.test_design_draft 1 项 OK。新增命令与工具，升 minor。
- 2026-10-30 · v0.1.0 · status=draft · 首版：把 NeurIPS/ICML/ICLR experiment skills 的披露要求做成 study-design audit；区分 run 设计与研究设计；新增 `design audit|template`；pipeline 可用 `--study-design-file` 把研究设计写进论文；Qoder 研究的 fixture/planned 版本被评为 `disclosure_complete`（不是 venue_ready），`tests.test_ccfa_audit` 7 项通过。
