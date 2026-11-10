"""Shared fixtures for writing-pack and manuscript-audit tests."""

from pathlib import Path
from typing import Any

from research_agent.project import init_project
from research_agent.storage import write_json_atomic

RUN_ID = "RUN-TEST-0001"
SOURCE_ID = "S1"
SOURCE_ID_2 = "S2"
SOURCE_ID_3 = "S3"
TITLE = "Learning Curves for Decision Making: A Survey"
TITLE_2 = "Validation Recommendations for Supervised Learning"
TITLE_3 = "Failure-Aware Agent Training with Verified Trajectories"


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, payload)


def make_writing_project(root: Path, *, with_run: bool = True, signed: bool = False) -> Path:
    project = Path(root) / "project"
    init_project(project, "writing-test")
    run = project / "runs" / RUN_ID
    run.mkdir(parents=True, exist_ok=True)
    _write(
        run / "run-context.json",
        {"schema_version": "research-run-context-0.1", "run_id": RUN_ID},
    )
    _write(
        run / "task.json",
        {
            "route": "experiment_validation" if with_run else "literature_review",
            "status": "completed",
            "stopped_at": None,
            "goal": "学习曲线在决策中的可复现评估",
        },
    )
    _write(
        run / "literature-ledger.json",
        {
            "schema_version": "literature-ledger-0.2",
            "sources": [
                {
                    "source_id": SOURCE_ID,
                    "title": TITLE,
                    "year": 2024,
                    "venue": "arXiv",
                    "doi": "",
                    "url": "https://arxiv.org/abs/2401.00001",
                    "license": "arXiv",
                    "full_text": True,
                    "fixture": False,
                    "source_type": "preprint",
                    "peer_reviewed": "unknown",
                    "span_count": 12,
                },
                {
                    "source_id": SOURCE_ID_2,
                    "title": TITLE_2,
                    "year": 2023,
                    "venue": "arXiv",
                    "doi": "",
                    "url": "",
                    "license": "arXiv",
                    "full_text": True,
                    "fixture": False,
                    "source_type": "preprint",
                    "peer_reviewed": "unknown",
                    "span_count": 3,
                },
                {
                    "source_id": SOURCE_ID_3,
                    "title": TITLE_3,
                    "year": 2024,
                    "venue": "arXiv",
                    "doi": "",
                    "url": "https://arxiv.org/abs/2410.00003",
                    "license": "arXiv",
                    "full_text": True,
                    "fixture": False,
                    "source_type": "preprint",
                    "peer_reviewed": "unknown",
                    "span_count": 4,
                },
            ],
            "coverage": {"gaps": ["few independent replications"], "covered_facets": ["core"]},
        },
    )
    _write(
        project / "inputs" / "arxiv-sources.json",
        {
            "downloaded": [
                {
                    "title": TITLE,
                    "arxiv_id": "2401.00001",
                    "url": "https://arxiv.org/abs/2401.00001",
                    "abstract": "Learning curves describe model performance as a function of training data. "
                    "This survey organizes methods for decision making and highlights open evaluation gaps.",
                    "authors": ["A. Researcher", "B. Researcher"],
                    "year": 2024,
                },
                {
                    "title": TITLE_3,
                    "arxiv_id": "2410.00003",
                    "url": "https://arxiv.org/abs/2410.00003",
                    "abstract": "We study failure-aware training for language agents with verified trajectories. "
                    "A quality gate filters failed interactions before they update the policy.",
                    "authors": ["C. Researcher"],
                    "year": 2024,
                },
            ]
        },
    )
    good_span = (
        "We propose a unified framework for decision making with learning curves and show that it "
        "reduces extrapolation error across the evaluated settings."
    )
    good_span_2 = (
        "This paper surveys learning-curve methods for data collection decisions and organizes them "
        "into a common evaluation framework."
    )
    _write(
        run / "literature.json",
        {
            "spans": [
                {
                    "span_id": SOURCE_ID + "-S01-01",
                    "source_id": SOURCE_ID,
                    "section": "Page 1",
                    "page": 1,
                    "text": good_span,
                },
                {
                    "span_id": SOURCE_ID + "-S01-02",
                    "source_id": SOURCE_ID,
                    "section": "Page 1",
                    "page": 1,
                    "text": good_span_2,
                },
                {
                    "span_id": SOURCE_ID + "-S01-03",
                    "source_id": SOURCE_ID,
                    "section": "Page 2",
                    "page": 2,
                    "text": "Instruction: calculate 3 + 5 and return the result in the box below.",
                },
                {
                    "span_id": SOURCE_ID + "-S01-04",
                    "source_id": SOURCE_ID,
                    "section": "Page 3",
                    "page": 3,
                    "text": "Natalia sold clips to 48 of her friends in April, and then she sold half as many clips in May.",
                },
                {
                    "span_id": SOURCE_ID + "-S01-05",
                    "source_id": SOURCE_ID,
                    "section": "Page 4",
                    "page": 4,
                    "text": "Figure 2: Overview of the proposed pipeline. The encoder takes an input image and returns a label.",
                },
                {
                    "span_id": SOURCE_ID_2 + "-S01-01",
                    "source_id": SOURCE_ID_2,
                    "section": "Page 1",
                    "page": 1,
                    "text": "Here we present community recommendations that establish standards for validation in biology.",
                },
                {
                    "span_id": SOURCE_ID_3 + "-S01-01",
                    "source_id": SOURCE_ID_3,
                    "section": "Page 1",
                    "page": 1,
                    "text": "We show that a quality gate over failed trajectories improves agent training stability across the evaluated tasks.",
                },
            ],
            "brief": {"source_briefs": [{"source_id": SOURCE_ID, "full_text": True}]},
        },
    )
    _write(
        run / "idea.json",
        {
            "candidates": [
                {
                    "idea_id": "IDEA-01",
                    "title": "统一学习曲线评估",
                    "hypothesis": "统一的评估协议能减少决策错误。",
                    "falsification": "若跨数据集无差异则否证。",
                    "evidence_refs": [SOURCE_ID + "-S01-01"],
                }
            ]
        },
    )
    _write(run / "idea-review.json", {"status": "advance"})
    _write(
        run / "experiment.json",
        {
            "status": "designed",
            "hypothesis": "统一评估协议能减少决策错误。",
            "baseline": "fixed-budget",
            "primary_metric": "R2",
            "controls": ["same splits"],
            "seeds": 3,
            "budget": "small",
        },
    )
    _write(run / "design-audit.json", {"status": "complete", "blockers": []})
    if with_run:
        _write(
            run / "run" / "run-capsule.json",
            {
                "run_id": "RUN-LOCAL-1",
                "dataset_id": "synthetic",
                "model": "ridge",
                "metric_name": "R2",
                "seeds": [0, 1, 2],
                "mean": 0.1438,
                "std": 0.0123,
                "status": "completed",
                "metrics_by_seed": [{"seed": 0, "value": 0.14}],
            },
        )
        _write(
            run / "run" / "ea.json",
            {"artifact_id": "EA-1", "scope": "S5/test", "sha256": "a" * 64, "immutable": True},
        )
        _write(run / "run" / "metrics.json", [{"seed": 0, "R2": 0.1438}])
        _write(run / "run" / "claim-draft.json", {"status": "draft", "statement": "R2=0.1438"})
        if signed:
            _write(
                run / "claim" / "claim.json",
                {
                    "status": "supported",
                    "statement": "R2 improves over the baseline.",
                    "assertions": [
                        {"observed": 0.1438},
                        {"observed": 0.187},
                    ],
                },
            )
    return project


def write_draft(
    path: Path,
    *,
    result_text: str,
    citation: str = "[REF-01]",
) -> Path:
    body = """# 测试手稿

## 摘要

本文研究学习曲线在数据采集决策中的作用 %s。

## 引言

数据规模决策需要可复现的评估 %s。

## 相关工作

已有综述总结了学习曲线方法 %s。

## 方法

我们采用统一协议比较不同策略 %s。

## 实验

实验使用固定数据划分和多个随机种子 %s。

## 结果

%s

## 讨论

结果仍需在更多数据集上复核 %s。

## 结论

本文给出可审计的评估框架 %s。

## 参考文献

1. %s A. Researcher. Learning Curves for Decision Making: A Survey. arXiv, 2024.
""" % (
        citation,
        citation,
        citation,
        citation,
        citation,
        result_text,
        citation,
        citation,
        citation,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path
