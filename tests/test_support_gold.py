import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from research_agent.cli import main
from research_agent.project import init_project
from research_agent.storage import write_json_atomic
from research_agent.support_gold import (
    SupportGoldError,
    build_gold_templates,
    evaluate_support_gold,
    load_annotations,
    panel_from_ledger,
)


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _annotations(root: Path, digest: str):
    a = _write(
        root / "a.json",
        {
            "annotator": "A",
            "draft_sha256": digest,
            "items": [
                {"id": "SUP-01", "status": "supported"},
                {"id": "SUP-02", "status": "partial"},
                {"id": "SUP-03", "status": "contradicted"},
                {"id": "SUP-04", "status": "supported"},
            ],
        },
    )
    b = _write(
        root / "b.json",
        {
            "annotator": "B",
            "draft_sha256": digest,
            "items": [
                {"id": "SUP-01", "status": "supported"},
                {"id": "SUP-02", "status": "supported"},
                {"id": "SUP-03", "status": "contradicted"},
                {"id": "SUP-04", "status": "supported"},
            ],
        },
    )
    return [load_annotations(a), load_annotations(b)]


class SupportGoldTest(unittest.TestCase):
    def test_gold_kappa_and_panel_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            annotations = _annotations(Path(tmp), "a" * 64)
            panel = {
                "draft_sha256": "a" * 64,
                "status": "ready",
                "panel_fingerprint": "f" * 64,
                "items": [
                    {"id": "SUP-01", "final_status": "supported"},
                    {"id": "SUP-02", "final_status": "supported"},
                    {"id": "SUP-03", "final_status": "supported"},
                    {"id": "SUP-04", "final_status": "supported"},
                ],
            }
            report = evaluate_support_gold(annotations, panel=panel)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["counts"]["contradicted"], 1)
            self.assertEqual(report["counts"]["partial"], 1)
            self.assertEqual(report["unanimous_items"], 3)
            self.assertIsNotNone(report["agreement"]["mean_kappa"])
            self.assertEqual(report["panel"]["accuracy"], 0.5)
            self.assertEqual(
                {item["id"] for item in report["panel"]["disagreements"]},
                {"SUP-02", "SUP-03"},
            )
            self.assertFalse(report.get("submission_ready", False))

    def test_gold_panel_from_qoder_ledger_and_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            annotations = _annotations(Path(tmp), "a" * 64)
            ledger = {
                "draft": "draft.md",
                "draft_sha256": "a" * 64,
                "status": "ready",
                "judge_model": "qoder:test",
                "cache_key": "c" * 64,
                "items": [
                    {
                        "id": "SUP-01",
                        "section": "引言",
                        "sentence": "示例句 A[REF-01]。",
                        "refs": ["REF-01"],
                        "evidence": [{"ref": "SPAN-01", "text": "证据 A"}],
                        "status": "supported",
                    },
                    {
                        "id": "SUP-02",
                        "section": "结果",
                        "sentence": "示例句 B[REF-01]。",
                        "refs": ["REF-01"],
                        "evidence": [{"ref": "SPAN-02", "text": "证据 B"}],
                        "status": "partial",
                    },
                    {
                        "id": "SUP-03",
                        "section": "讨论",
                        "sentence": "示例句 C[REF-01]。",
                        "refs": ["REF-01"],
                        "evidence": [],
                        "status": "supported",
                    },
                    {
                        "id": "SUP-04",
                        "section": "结论",
                        "sentence": "示例句 D[REF-01]。",
                        "refs": ["REF-01"],
                        "evidence": [],
                        "status": "supported",
                    },
                ],
            }
            panel = panel_from_ledger(
                ledger, source="runs/RUN/support-ledger.json"
            )
            self.assertEqual(panel["judge_model"], "qoder:test")
            self.assertEqual(panel["items"][0]["final_status"], "supported")
            templates = build_gold_templates(
                panel, ["A", "B"], source="runs/RUN/support-ledger.json"
            )
            self.assertEqual(templates["item_count"], 4)
            self.assertTrue(
                all(item["status"] == "" for item in templates["templates"][0]["items"])
            )
            self.assertNotIn(
                "final_status", json.dumps(templates, ensure_ascii=False)
            )

            report = evaluate_support_gold(annotations, panel=panel)
            self.assertEqual(report["panel"]["accuracy"], 0.75)
            self.assertEqual(report["panel"]["judge_model"], "qoder:test")
            self.assertEqual(
                report["panel"]["source"], "runs/RUN/support-ledger.json"
            )

    def test_cli_gold_template_from_qoder_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            init_project(project, "gold ledger template")
            run = project / "runs" / "RUN-LEDGER"
            run.mkdir(parents=True)
            write_json_atomic(
                run / "support-ledger.json",
                {
                    "draft": "drafts/draft.md",
                    "draft_sha256": "a" * 64,
                    "status": "ready",
                    "judge_model": "qoder:test",
                    "items": [
                        {
                            "id": "SUP-01",
                            "section": "引言",
                            "sentence": "示例句 A[REF-01]。",
                            "refs": ["REF-01"],
                            "evidence": [{"ref": "SPAN-01", "text": "证据 A"}],
                            "status": "supported",
                        },
                        {
                            "id": "SUP-02",
                            "section": "结果",
                            "sentence": "示例句 B[REF-01]。",
                            "refs": ["REF-01"],
                            "evidence": [],
                            "status": "partial",
                        },
                    ],
                },
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    [
                        "writing", "support-gold-template",
                        "--project", str(project),
                        "--run-id", "RUN-LEDGER",
                        "--ledger", "runs/RUN-LEDGER/support-ledger.json",
                    ]
                )
            self.assertEqual(code, 0, buffer.getvalue())
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["item_count"], 2)
            self.assertEqual(set(payload["files"]), {"A", "B"})

    def test_gold_rejects_bad_annotations_and_mismatched_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            annotations = _annotations(root, "a" * 64)
            bad = _write(
                root / "bad.json",
                {
                    "annotator": "B",
                    "items": [{"id": "SUP-01", "status": "unknown"}],
                },
            )
            with self.assertRaises(SupportGoldError):
                load_annotations(bad)
            other = _write(
                root / "other.json",
                {
                    "annotator": "C",
                    "items": [{"id": "SUP-99", "status": "supported"}],
                },
            )
            with self.assertRaises(SupportGoldError):
                evaluate_support_gold(annotations + [load_annotations(other)])
            with self.assertRaises(SupportGoldError):
                evaluate_support_gold(
                    annotations,
                    panel={"draft_sha256": "b" * 64, "items": []},
                )

    def test_gold_template_omits_panel_verdicts_and_writes_blank_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            init_project(project, "gold template")
            run = project / "runs" / "RUN-TEMPLATE"
            run.mkdir(parents=True)
            write_json_atomic(
                run / "support-panel.json",
                {
                    "draft_sha256": "a" * 64,
                    "items": [
                        {
                            "id": "SUP-01",
                            "section": "结果",
                            "sentence": "示例句 A。",
                            "refs": ["REF-01"],
                            "evidence": [{"ref": "SPAN-01", "text": "证据片段"}],
                            "majority": "partial",
                            "final_status": "supported",
                            "verdicts": {"judge-a": "supported"},
                        },
                        {
                            "id": "SUP-02",
                            "section": "讨论",
                            "sentence": "示例句 B。",
                            "refs": ["REF-01"],
                            "evidence": [],
                            "final_status": "supported",
                        },
                    ],
                },
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    [
                        "writing", "support-gold-template",
                        "--project", str(project),
                        "--run-id", "RUN-TEMPLATE",
                    ]
                )
            self.assertEqual(code, 0, buffer.getvalue())
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["item_count"], 2)
            self.assertEqual(set(payload["files"]), {"A", "B"})
            template = json.loads(Path(payload["files"]["A"]).read_text(encoding="utf-8"))
            self.assertEqual(template["annotator"], "A")
            self.assertTrue(all(item["status"] == "" for item in template["items"]))
            serialized = json.dumps(template, ensure_ascii=False)
            self.assertNotIn("final_status", serialized)
            self.assertNotIn("verdicts", serialized)
            self.assertIn("证据片段", serialized)
            self.assertTrue((run / "support-gold-template.md").is_file())

    def test_cli_support_gold_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            init_project(project, "gold test")
            draft = project / "inputs" / "draft.md"
            draft.write_text("# 引言\n\n示例句[REF-01]。\n", encoding="utf-8")
            digest = hashlib.sha256(draft.read_bytes()).hexdigest()
            _annotations(project / "inputs", digest)
            run = project / "runs" / "RUN-GOLD"
            run.mkdir(parents=True)
            write_json_atomic(
                run / "support-panel.json",
                {
                    "draft": str(draft),
                    "draft_sha256": digest,
                    "status": "ready",
                    "items": [
                        {"id": "SUP-01", "final_status": "supported"},
                        {"id": "SUP-02", "final_status": "supported"},
                        {"id": "SUP-03", "final_status": "supported"},
                        {"id": "SUP-04", "final_status": "supported"},
                    ],
                },
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    [
                        "writing", "support-gold",
                        "--project", str(project),
                        "--run-id", "RUN-GOLD",
                        "--draft", "inputs/draft.md",
                        "--annotator-file", "inputs/a.json",
                        "--annotator-file", "inputs/b.json",
                        "--panel", "runs/RUN-GOLD/support-panel.json",
                    ]
                )
            self.assertEqual(code, 0, buffer.getvalue())
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["status"], "complete")
            self.assertTrue((run / "support-gold.json").is_file())
            self.assertTrue((run / "support-gold.md").is_file())


if __name__ == "__main__":
    unittest.main()
