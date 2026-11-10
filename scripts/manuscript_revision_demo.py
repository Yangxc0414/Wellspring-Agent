"""Demo: revise an existing manuscript and export a journal working package.

Without --profile this runs in copy mode: data metrics and figures are updated,
but prose is preserved. With --profile it rewrites paragraphs through the model
gateway while rejecting new numbers/citations.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.revision import run_revision


DRAFT = """# 离线分类实验：可投稿修订示例

## 摘要

本文在固定划分上比较方法 A 与方法 B，方法 A 的平均准确率为 0.9123 [1]。原有实验条件保持不变。

## 1 引言

可复核的实验叙事需要把数字、图表与数据表绑定 [1]。

## 2 方法

使用固定训练集、测试集和 3 个随机种子；不改变原始数据与模型设置。

## 3 实验

实验包含 100 个样本，方法 A 与方法 B 在同一划分上评估。

## 4 结果

方法 A 的平均准确率为 0.9123，方法 B 的平均准确率为 0.8000 [1]。结果见图 1。

## 5 讨论

方法 A 在固定划分上更好，但只代表当前数据集与协议。

## 参考文献

[1] 张三. 离线分类实验方法[J]. 示例期刊, 2025.
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def prepare(root: Path):
    draft = root / "paper.md"
    data = root / "results.csv"
    metrics = root / "metrics.json"
    figures = root / "figures.json"
    _write(draft, DRAFT)
    _write(
        data,
        "method,accuracy\nA,0.91\nA,0.92\nA,0.91\nB,0.80\nB,0.81\nB,0.80\n",
    )
    _write(
        metrics,
        json.dumps(
            {
                "metrics": [
                    {
                        "name": "mean_a", "table": "results", "column": "accuracy",
                        "op": "mean", "where": {"method": "A"}, "digits": 4,
                        "replace": "0.9123",
                    },
                    {
                        "name": "mean_b", "table": "results", "column": "accuracy",
                        "op": "mean", "where": {"method": "B"}, "digits": 4,
                        "replace": "0.8000",
                    },
                    {"name": "n", "table": "results", "column": "*", "op": "count", "digits": 0},
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    _write(
        figures,
        json.dumps(
            {
                "figures": [
                    {
                        "id": "fig1", "type": "bar", "table": "results",
                        "x": "method", "y": "accuracy", "agg": "mean",
                        "title": "Accuracy by method", "caption": "图 1 方法准确率比较",
                        "insert_after_heading": "结果",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return draft, data, metrics, figures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=str(ROOT / "runtime_data" / "revision-demo-input"))
    parser.add_argument("--output-dir", default=str(ROOT / "runtime_data" / "revision-demo-output"))
    parser.add_argument("--profile", default="", help="model profile; empty runs copy mode")
    parser.add_argument("--venue", default="software_journal")
    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    draft, data, metrics, figures = prepare(input_dir)
    result = run_revision(
        draft_path=draft,
        output_dir=Path(args.output_dir),
        data_paths=[data],
        metrics_path=metrics,
        figures_path=figures,
        venue=args.venue,
        profile_id=args.profile,
        formats=("md", "tex", "docx", "pdf"),
    )
    print(json.dumps({
        "status": result["status"],
        "writer_mode": result["writer_mode"],
        "output_dir": result["output_dir"],
        "export": result["export"]["files"],
        "blockers": result["audit"]["blockers"],
        "warnings": result["audit"]["warnings"],
    }, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
