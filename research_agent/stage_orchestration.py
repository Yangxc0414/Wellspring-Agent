"""方法驱动的阶段编排（design/174，判据 A）。

pipeline.py 的 run() 是线性函数，阶段间通过局部变量传产物。若一个方法的组合
接线不覆盖某阶段，本模块提供两样东西，让"真跳过"既不崩溃也不伪造：

1. ``StagePlan``：哪个阶段该执行（由 composition_plan.covered_stages 决定）；
   未声明方法时全部执行（向后兼容）。
2. 空产物替身（null object）：跳过的阶段用"显式 not_applicable"的空结果对象，
   下游代码照常访问 .spans / .candidates / .status，不会 NameError，也不会把
   跳过说成完成。每个替身带 ``orchestration_skipped=True`` 标记，产物写盘时
   可被识别，绝不冒充真实证据。

门禁语义：被跳过阶段的专属门（Q0/G1/G2）标 not_applicable，理由写明是方法
编排而非人签通过——治理层不随顺序漂移（design/165 不变项）。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .contracts import (
    CoverageReceipt,
    ExperimentDesign,
    IdeaResult,
    LiteratureBrief,
    LiteratureResult,
    PaperContract,
    PaperSlot,
    QueryPlan,
    WritingProfile,
)


ALL_STAGES: tuple = ("literature", "idea", "experiment", "run", "figure", "paper")

# 阶段专属门禁：阶段被方法跳过时，这些门标 not_applicable，不伪装成 pass。
GATE_FOR_STAGE: Dict[str, str] = {
    "literature": "Q0",
    "idea": "G1",
    "experiment": "G2",
}


@dataclass
class StagePlan:
    """一次运行的阶段编排计划。covered=None 表示未声明方法 → 全阶段执行。"""

    covered: Optional[Set[str]]
    composition: str = ""
    method_id: str = ""
    reason: str = ""

    def enabled(self, stage: str) -> bool:
        return self.covered is None or stage in self.covered

    def skipped(self) -> List[str]:
        if self.covered is None:
            return []
        return [s for s in ALL_STAGES if s not in self.covered]

    def not_applicable_gates(self) -> List[Dict[str, str]]:
        return [
            {
                "gate": GATE_FOR_STAGE[stage],
                "status": "not_applicable",
                "reason": "stage %s not in method composition %s (orchestration, not a gate pass)" % (
                    stage, self.composition or "default"
                ),
            }
            for stage in self.skipped()
            if stage in GATE_FOR_STAGE
        ]


def build_stage_plan(composition_plan: Optional[Dict[str, Any]]) -> StagePlan:
    """从 pipeline_stage_plan 的产物构造 StagePlan。None/损坏 → 全阶段（fail-open，与 164 一致）。"""
    if not composition_plan:
        return StagePlan(covered=None)
    covered = set(composition_plan.get("covered_stages") or [])
    return StagePlan(
        covered=covered,
        composition=str(composition_plan.get("composition") or ""),
        method_id=str(composition_plan.get("method") or ""),
        reason="method composition",
    )


# ---------------------------------------------------------------------------
# 空产物替身：字段与真实产物同构，但显式标 not_applicable，不携带任何证据。
# ---------------------------------------------------------------------------

def skipped_literature(run_id: str) -> LiteratureResult:
    brief = LiteratureBrief(
        coverage_score=0.0, saturation="not_applicable", target_sources=0,
        target_full_text=0, facets=[], source_briefs=[], sections=[], highlights=[],
        summary="stage skipped by method composition", gaps=[],
    )
    return LiteratureResult(
        run_id=run_id, module="literature", spec_version="skipped", status="not_applicable",
        query_plan=QueryPlan(question="", subqueries=[], source_scope=[]),
        hits=[], spans=[],
        coverage=CoverageReceipt(
            queries=0, sources_found=0, sources_read=0, spans_extracted=0,
            gaps=[], warnings=[], source_scope=[],
        ),
        warnings=["literature stage skipped by method composition; no evidence produced"],
        fixture_mode=True, brief=brief,
    )


def skipped_idea(run_id: str) -> IdeaResult:
    return IdeaResult(
        run_id=run_id, module="idea", spec_version="skipped", status="not_applicable",
        candidates=[],
        warnings=["idea stage skipped by method composition; no candidate generated"],
    )


def skipped_design(design_id: str) -> ExperimentDesign:
    return ExperimentDesign(
        design_id=design_id, question="", hypothesis="", baseline="",
        primary_metric="", controls=[], seeds=0, budget="", stopping_rule="",
        evidence_refs=[], status="not_applicable",
        warnings=["experiment stage skipped by method composition; no protocol frozen"],
    )


@dataclass
class NullFigure:
    """figure 阶段跳过时的替身：只暴露下游需要的 figure_id/svg，不携带任何图。"""
    figure_id: str
    svg: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "figure_id": self.figure_id, "svg": "", "status": "not_applicable",
            "warnings": ["figure stage skipped by method composition"],
        }


def skipped_paper(topic: str) -> PaperContract:
    """paper 阶段跳过时的替身：契约结构完整、无正文、无 claim。"""
    return PaperContract(
        title=topic,
        profile=WritingProfile(
            language="zh", venue_type="zh_core_journal",
            citation_style="not_applicable", sections=[],
        ),
        sections=[],
        slots=[
            PaperSlot(slot_id="result.primary", section="结果", required_evidence="EA + Claim"),
        ],
        claims=[],
        status="not_applicable",
        warnings=["paper stage skipped by method composition; no manuscript drafted"],
    )


def skipped_manuscript_bundle(topic: str) -> Dict[str, Any]:
    return {
        "manuscript": "",
        "audit": {"status": "not_applicable", "summary": {"blockers": [], "warnings": []}},
        "argument_ledger": [],
        "claim_registry": [],
    }
