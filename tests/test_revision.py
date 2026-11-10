import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research_agent.ab_review import run_ab_review
from research_agent.revision import _parse_model_json, _validate_rewrite, run_revision
from research_agent.revision_plan import build_revision_plan, validate_plan
from research_agent.revision_io import load_data_tables, read_draft

ROOT = Path(__file__).resolve().parents[1]

DRAFT = """# 测试论文：离线实验结果

## 摘要

本文研究离线分类器的稳定性。实验在 100 个样本上运行 3 个随机种子，方法 A 的平均准确率为 0.9123 [1]。

## 1 引言

分类器评估需要可复核的数字与引用 [1]。本文保留原有实验设置，并补充更清晰的过渡。

## 2 方法

采用固定训练集和测试集，记录每个随机种子的准确率；不改变原始实验条件。

## 3 实验

实验使用 100 个样本和 3 个随机种子，比较方法 A 与方法 B。所有设置与原始实验一致。

## 4 结果

方法 A 的平均准确率为 0.9123，方法 B 的平均准确率为 0.8000 [1]。结果见图 1。

## 5 讨论

方法 A 在当前固定划分上表现更好，但结论仍受单一数据集限制。

## 参考文献

[1] 张三. 离线分类实验方法[J]. 示例期刊, 2025.
"""

METRICS = {
    "metrics": [
        {
            "name": "mean_a",
            "table": "results",
            "column": "accuracy",
            "op": "mean",
            "where": {"method": "A"},
            "digits": 4,
            "replace": "0.9123",
        },
        {"name": "n", "table": "results", "column": "*", "op": "count", "digits": 0},
    ]
}

FIGURES = {
    "figures": [
        {
            "id": "fig1",
            "type": "bar",
            "table": "results",
            "x": "method",
            "y": "accuracy",
            "agg": "mean",
            "title": "Accuracy by method",
            "caption": "图 1 方法准确率比较",
            "insert_after_heading": "结果",
        }
    ]
}


class FakeModel:
    def __init__(self, mode="safe"):
        self.mode = mode
        self.calls = []

    def complete(self, messages, json_mode=True):
        payload = json.loads(messages[1]["content"])
        self.calls.append(payload)
        original = payload["original_text"]
        if self.mode == "noop":
            text = original
        elif self.mode == "bad-number":
            text = original + " 新增结果 0.9999。"
        elif self.mode == "drop-citation":
            text = original.replace("[1]", "")
        else:
            text = original + " 该段保留原有实验条件与数字。"
        return json.dumps(
            {"text": text, "change_summary": ["test revision"]},
            ensure_ascii=False,
        )


def write_fixture(root: Path):
    draft = root / "paper.md"
    draft.write_text(DRAFT, encoding="utf-8")
    data = root / "results.csv"
    data.write_text(
        "method,accuracy\nA,0.91\nA,0.92\nB,0.80\nB,0.81\n",
        encoding="utf-8",
    )
    metrics = root / "metrics.json"
    metrics.write_text(json.dumps(METRICS, ensure_ascii=False), encoding="utf-8")
    figures = root / "figures.json"
    figures.write_text(json.dumps(FIGURES, ensure_ascii=False), encoding="utf-8")
    return draft, data, metrics, figures


class RevisionTest(unittest.TestCase):
    def test_markdown_metrics_figures_and_model_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft, data, metrics, figures = write_fixture(root)
            model = FakeModel()
            result = run_revision(
                draft_path=draft,
                output_dir=root / "out",
                data_paths=[data],
                metrics_path=metrics,
                figures_path=figures,
                venue="software_journal",
                profile_id="test-profile",
                model=model,
                formats=("md", "tex", "docx"),
            )
            self.assertEqual(result["status"], "review_ready")
            self.assertEqual(result["writer_mode"], "model")
            self.assertFalse(result["audit"]["submission_ready"])
            self.assertTrue(result["audit"]["review_ready"])
            self.assertTrue(result["audit"]["format_ready"])
            self.assertGreater(result["audit"]["rewrite"]["changed_blocks"], 0)
            self.assertIn("[1]", Path(result["files"]["revised_markdown"]).read_text(encoding="utf-8"))
            self.assertIn("0.9150", Path(result["files"]["revised_markdown"]).read_text(encoding="utf-8"))
            self.assertNotIn("0.9123", Path(result["files"]["revised_markdown"]).read_text(encoding="utf-8"))
            self.assertTrue(Path(result["export"]["files"]["markdown"]).is_file())
            self.assertTrue(Path(result["export"]["files"]["latex"]).is_file())
            self.assertTrue(Path(result["export"]["files"]["docx"]).is_file())
            diff = json.loads(Path(result["files"]["diff"]).read_text(encoding="utf-8"))
            self.assertTrue(diff["records"])
            self.assertTrue(any(item["status"] == "accepted" for item in diff["records"]))
            ledger = json.loads(Path(result["files"]["sentence_ledger"]).read_text(encoding="utf-8"))
            self.assertGreater(ledger["summary"]["sentences"], 0)
            self.assertGreater(ledger["summary"]["metric_linked"], 0)
            manifest = json.loads(Path(result["files"]["figures"]).read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["figures"]), 1)
            self.assertTrue(Path(manifest["figures"][0]["png"]).is_file())
            self.assertTrue(manifest["figures"][0]["output_sha256"])
            self.assertTrue(any(call["section"] == "4 结果" for call in model.calls))

    def test_model_must_not_add_numbers_or_drop_citations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft, data, metrics, figures = write_fixture(root)
            result = run_revision(
                draft_path=draft,
                output_dir=root / "bad-number",
                data_paths=[data],
                metrics_path=metrics,
                figures_path=figures,
                profile_id="test-profile",
                model=FakeModel("bad-number"),
                formats=("md",),
            )
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(any("new numbers added" in item for item in result["audit"]["blockers"]))
            result = run_revision(
                draft_path=draft,
                output_dir=root / "drop-citation",
                data_paths=[data],
                metrics_path=metrics,
                figures_path=figures,
                profile_id="test-profile",
                model=FakeModel("drop-citation"),
                formats=("md",),
            )
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(any("citation set changed" in item for item in result["audit"]["blockers"]))

    def test_copy_mode_never_claims_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft, data, metrics, figures = write_fixture(root)
            result = run_revision(
                draft_path=draft,
                output_dir=root / "copy",
                data_paths=[data],
                metrics_path=metrics,
                figures_path=figures,
                formats=("md", "docx"),
            )
            self.assertEqual(result["status"], "copy_only")
            self.assertFalse(result["audit"]["review_ready"])
            self.assertTrue(any("no model profile" in item for item in result["audit"]["warnings"]))
            self.assertIn("0.9150", Path(result["files"]["revised_markdown"]).read_text(encoding="utf-8"))

    def test_model_noop_is_not_reported_as_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft, data, metrics, figures = write_fixture(root)
            result = run_revision(
                draft_path=draft,
                output_dir=root / "noop",
                data_paths=[data],
                metrics_path=metrics,
                figures_path=figures,
                profile_id="test-profile",
                model=FakeModel("noop"),
                formats=("md",),
            )
            self.assertEqual(result["status"], "copy_only")
            self.assertEqual(result["audit"]["rewrite"]["changed_blocks"], 0)
            self.assertFalse(result["audit"]["review_ready"])

    def test_nested_json_text_is_unwrapped(self):
        nested = json.dumps(
            {"text": "改写后的段落", "change_summary": ["test"]},
            ensure_ascii=False,
        )
        parsed = _parse_model_json(json.dumps({"text": nested}, ensure_ascii=False))
        self.assertEqual(parsed["text"], "改写后的段落")

    def test_table_figure_translation_keeps_reference_identity(self):
        original = "The comparison is summarized in Table 1 and discussed in the main text with the same evidence and conditions."
        revised = "对比结果见表 1，并在正文中结合同样的证据与实验条件进行讨论。"
        blockers, _ = _validate_rewrite(original, revised, protected=False)
        self.assertFalse(any("figure/table references" in item for item in blockers))

    def test_whole_section_output_is_rejected_as_scope_change(self):
        original = "This study evaluates a classifier on a fixed split with three seeds and reports the same evidence conditions."
        revised = "This study evaluates a classifier.\n\nIt uses a fixed split and three seeds.\n\nThe evidence conditions are unchanged."
        blockers, _ = _validate_rewrite(original, revised, protected=False)
        self.assertTrue(any("paragraph scope" in item for item in blockers))

    def test_goal_is_sent_to_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft, data, metrics, figures = write_fixture(root)
            model = FakeModel()
            run_revision(
                draft_path=draft,
                output_dir=root / "goal",
                data_paths=[data],
                metrics_path=metrics,
                figures_path=figures,
                profile_id="test-profile",
                model=model,
                sections=["引言"],
                goal="提升论证连贯性并合并冗余表达，不新增事实。",
                review_comments=["明确研究缺口", "减少长句"],
                formats=("md",),
            )
            self.assertTrue(model.calls)
            self.assertTrue(any(call.get("rewrite_goal") for call in model.calls))
            self.assertTrue(any(call.get("review_comments") for call in model.calls))

    def test_section_plan_and_ab_review(self):
        class PlanModel:
            model_id = "fake:plan"
            def complete(self, messages, json_mode=True):
                return json.dumps({
                    "sections": [{
                        "heading": "1 引言",
                        "role": "定位问题",
                        "issues": ["过渡不清"],
                        "paragraph_actions": [{"block_index": 0, "action": "明确研究缺口", "preserve": ["[1]"]}],
                        "target_length_ratio": "0.9-1.2",
                    }]
                }, ensure_ascii=False)

        class ABModel:
            model_id = "fake:ab"
            def complete(self, messages, json_mode=True):
                return json.dumps({
                    "scores": {
                        "A": {"clarity": 6, "argument": 6, "evidence_consistency": 6, "academic_style": 6},
                        "B": {"clarity": 9, "argument": 9, "evidence_consistency": 9, "academic_style": 9},
                    },
                    "winner": "B", "reason": "B is clearer", "issues": {"A": [], "B": []},
                }, ensure_ascii=False)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft, data, metrics, figures = write_fixture(root)
            plan = build_revision_plan(draft, PlanModel(), sections=["引言"])
            validated = validate_plan(plan, read_draft(draft))
            self.assertEqual(validated["sections"][0]["heading"], "1 引言")
            original = draft.read_text(encoding="utf-8")
            revised = root / "revised.md"
            revised.write_text(original.replace("本文保留原有实验设置，并补充更清晰的过渡。", "本文保留原有实验设置，并进一步说明研究缺口与过渡逻辑。"), encoding="utf-8")
            ab = run_ab_review(draft, revised, ABModel(), sections=["引言"])
            self.assertEqual(ab["results"][0]["winner"], ab["results"][0]["mapping"]["B"])
            self.assertEqual(ab["wins"]["original"] + ab["wins"]["revised"] + ab["wins"]["tie"], 1)

    def test_docx_ingest_preserves_headings_tables_and_images(self):
        from docx import Document
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "chart.png"
            Image.new("RGB", (80, 50), (30, 90, 160)).save(str(image_path))
            doc = Document()
            doc.add_heading("DOCX 测试论文", level=1)
            doc.add_heading("1 方法", level=2)
            doc.add_paragraph("这是原有实验方法叙事，包含 100 个样本和 3 个随机种子。")
            table = doc.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "method"
            table.cell(0, 1).text = "accuracy"
            table.cell(1, 0).text = "A"
            table.cell(1, 1).text = "0.91"
            doc.add_heading("2 结果", level=2)
            doc.add_paragraph("结果见下图。")
            doc.add_picture(str(image_path))
            source = root / "paper.docx"
            doc.save(str(source))
            parsed = read_draft(source, assets_dir=root / "assets")
            headings = [section.heading for section in parsed.sections]
            self.assertIn("1 方法", headings)
            self.assertIn("2 结果", headings)
            self.assertTrue(any(block.kind == "table" for section in parsed.sections for block in section.blocks))
            self.assertTrue(any(block.kind == "figure" for section in parsed.sections for block in section.blocks))

    def test_cli_inspect_and_copy_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft, data, metrics, figures = write_fixture(root)
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            inspect = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "revision", "inspect",
                    "--draft", str(draft), "--output-dir", str(root / "inspect"),
                    "--data", str(data), "--metrics", str(metrics), "--figures", str(figures),
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=env,
            )
            self.assertEqual(inspect.returncode, 0, inspect.stderr)
            self.assertEqual(json.loads(inspect.stdout)["status"], "inspected")
            run = subprocess.run(
                [
                    sys.executable, "-m", "research_agent", "revision", "run",
                    "--draft", str(draft), "--output-dir", str(root / "cli-run"),
                    "--data", str(data), "--metrics", str(metrics), "--figures", str(figures),
                    "--format", "md", "--format", "docx",
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=env,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            payload = json.loads(run.stdout)
            self.assertEqual(payload["status"], "copy_only")
            self.assertTrue(Path(payload["export"]["files"]["docx"]).is_file())

    def test_data_loader_supports_json_and_xlsx(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "rows.json"
            json_path.write_text(json.dumps([{"x": 1, "y": 2}, {"x": 2, "y": 4}]), encoding="utf-8")
            tables = load_data_tables([json_path])
            self.assertEqual(tables[0].rows[1]["y"], "4")
            try:
                from openpyxl import Workbook
            except ImportError:
                return
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["method", "score"])
            sheet.append(["A", 0.9])
            xlsx = root / "book.xlsx"
            workbook.save(str(xlsx))
            tables = load_data_tables([xlsx])
            self.assertTrue(tables)
            self.assertEqual(tables[0].rows[0]["method"], "A")


if __name__ == "__main__":
    unittest.main()
