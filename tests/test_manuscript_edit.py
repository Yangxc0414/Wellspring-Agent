import tempfile
import unittest
from pathlib import Path

from research_agent.manuscript_edit import ManuscriptEditError, replace_section
from research_agent.mcp_server import ResearchMCPService
from research_agent.project import run_dir
from research_agent.storage import write_json_atomic
from research_agent.writing_pack import build_writing_pack, ensure_pack_marker
from tests.writing_support import RUN_ID, make_writing_project, write_draft


class ManuscriptEditTest(unittest.TestCase):
    def test_replaces_one_section_and_preserves_the_rest(self):
        text = "# 标题\n\n## 引言\n\n原始引言 [REF-01]。\n\n## 讨论\n\n原始讨论 [REF-01]。\n"
        result = replace_section(text, "讨论", "改写讨论 [REF-01]。")
        self.assertIn("改写讨论 [REF-01]。", result["text"])
        self.assertIn("原始引言 [REF-01]。", result["text"])
        self.assertNotIn("原始讨论", result["text"])
        self.assertEqual(len(result["old_section_sha256"]), 64)
        self.assertEqual(result["section"], "讨论")

    def test_edits_subsection_without_changing_parent(self):
        text = (
            "## 方法\n\n前置说明。\n\n### 与现有工作的关系\n\n旧关系 [REF-01]。\n\n"
            "### 概念运行时\n\n其他内容 [REF-02]。\n"
        )
        result = replace_section(text, "与现有工作的关系", "新关系 [REF-01]。")
        self.assertIn("新关系 [REF-01]。", result["text"])
        self.assertNotIn("旧关系", result["text"])
        self.assertIn("## 方法", result["text"])
        self.assertIn("概念运行时", result["text"])
        self.assertIn("其他内容 [REF-02]。", result["text"])

    def test_rejects_new_refs_numbers_and_stale_hash(self):
        text = "## 讨论\n\n原始讨论 [REF-01] 为 0.9。\n"
        with self.assertRaises(ManuscriptEditError):
            replace_section(text, "讨论", "新增引用 [REF-02]。")
        with self.assertRaises(ManuscriptEditError):
            replace_section(text, "讨论", "新增数字 0.8。")
        with self.assertRaises(ManuscriptEditError):
            replace_section(text, "讨论", "改写 [REF-01]。", expected_section_sha256="b" * 64)
        with self.assertRaises(ManuscriptEditError):
            replace_section(text, "不存在的章节", "改写。")

    def test_mcp_section_edit_writes_new_bound_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            pack = build_writing_pack(project, RUN_ID)
            target = run_dir(project, RUN_ID)
            write_json_atomic(target / "writing-pack.json", pack)
            source = project / "draft.md"
            source.write_text(
                ensure_pack_marker(
                    write_draft(root / "source.md", result_text="无数字。").read_text(
                        encoding="utf-8"
                    ),
                    pack,
                ),
                encoding="utf-8",
            )
            service = ResearchMCPService(root)
            response = service.manuscript_section_edit(
                {
                    "project_dir": "project",
                    "run_id": RUN_ID,
                    "draft": "draft.md",
                    "section": "讨论",
                    "replacement": "讨论改写后的文本 [REF-01]。",
                    "output": "draft-edited.md",
                }
            )
            self.assertFalse(response["isError"])
            new_draft = project / "draft-edited.md"
            self.assertTrue(new_draft.is_file())
            text = new_draft.read_text(encoding="utf-8")
            self.assertIn("讨论改写后的文本 [REF-01]。", text)
            self.assertIn("writing-pack:", text)
            self.assertIn("## 引言", text)


if __name__ == "__main__":
    unittest.main()
