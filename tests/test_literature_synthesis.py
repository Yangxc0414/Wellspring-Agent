import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent.literature_synthesis import SynthesisError, synthesize_literature
from tests.writing_support import RUN_ID, SOURCE_ID, SOURCE_ID_2, SOURCE_ID_3, make_writing_project


class _FakeModel:
    model_id = "fake:synthesis"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, json_mode=True):
        self.calls.append({"json_mode": json_mode, "messages": messages})
        if not self.responses:
            raise AssertionError("no fake responses left")
        return self.responses.pop(0)


def _payload(extra_invalid=False):
    themes = [
        {
            "name": "证据门控与失败经验",
            "summary": "两篇来源都讨论失败经验，但对筛选规则的必要性判断不同。",
            "source_ids": [SOURCE_ID, SOURCE_ID_2],
            "stances": [
                {"source_id": SOURCE_ID, "stance": "supports"},
                {"source_id": SOURCE_ID_2, "stance": "qualifies"},
            ],
            "agreement": "失败经验需要质量筛选。",
            "tension": "筛选标准是否可跨任务迁移仍不一致。",
            "confidence": "medium",
        },
        {
            "name": "验证协议与可复现性",
            "summary": "来源对验证协议的必要性有一致判断，但覆盖范围不同。",
            "source_ids": [SOURCE_ID, SOURCE_ID_3],
            "stances": [
                {"source_id": SOURCE_ID, "stance": "supports"},
                {"source_id": SOURCE_ID_3, "stance": "supports"},
            ],
            "agreement": "需要显式验证协议。",
            "tension": "协议粒度尚未统一。",
            "confidence": "medium",
        },
        {
            "name": "角色分工与审计",
            "summary": "角色分工能降低单点负担，但验证责任仍可能被稀释。",
            "source_ids": [SOURCE_ID_2, SOURCE_ID_3],
            "stances": [
                {"source_id": SOURCE_ID_2, "stance": "qualifies"},
                {"source_id": SOURCE_ID_3, "stance": "supports"},
            ],
            "agreement": "分工需要独立验证。",
            "tension": "独立验证由谁承担仍不明确。",
            "confidence": "low",
        },
    ]
    if extra_invalid:
        themes.append(
            {
                "name": "无效单源主题",
                "summary": "只引用一篇来源。",
                "source_ids": [SOURCE_ID],
                "stances": [{"source_id": SOURCE_ID, "stance": "supports"}],
                "agreement": "",
                "tension": "",
                "confidence": "low",
            }
        )
    return json.dumps({"themes": themes, "unused_sources": []}, ensure_ascii=False)


class LiteratureSynthesisTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_theme_covers_multiple_sources_and_attaches_spans(self):
        project = make_writing_project(self.root)
        result = synthesize_literature(
            project, RUN_ID, max_themes=3, model=_FakeModel([_payload()])
        )
        self.assertEqual(result["theme_count"], 3)
        self.assertEqual(result["source_count"], 3)
        for theme in result["themes"]:
            self.assertGreaterEqual(theme["source_count"], 2)
            self.assertGreaterEqual(len({item["source_id"] for item in theme["stances"]}), 2)
            for stance in theme["stances"]:
                self.assertTrue(stance["ref_id"].startswith("REF-"))
                self.assertGreaterEqual(len(stance["evidence"]), 1)
        self.assertTrue((project / "runs" / RUN_ID / "synthesis-matrix.json").is_file())
        self.assertTrue((project / "runs" / RUN_ID / "synthesis-matrix.md").is_file())

    def test_single_source_theme_is_dropped_and_unused_sources_reported(self):
        project = make_writing_project(self.root)
        payload = json.loads(_payload(extra_invalid=True))
        payload["unused_sources"] = [{"source_id": SOURCE_ID_3, "reason": "not needed"}]
        result = synthesize_literature(
            project, RUN_ID, max_themes=4, model=_FakeModel([json.dumps(payload, ensure_ascii=False)])
        )
        self.assertEqual(result["theme_count"], 3)
        self.assertTrue(any("single-source" in warning or "dropped" in warning for warning in result["warnings"]))

    def test_too_few_valid_themes_is_rejected(self):
        project = make_writing_project(self.root)
        one = json.loads(_payload())
        one["themes"] = one["themes"][:1]
        with self.assertRaises(SynthesisError):
            synthesize_literature(
                project, RUN_ID, max_themes=3, model=_FakeModel([json.dumps(one, ensure_ascii=False)])
            )

    def test_requires_model(self):
        project = make_writing_project(self.root)
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            with self.assertRaises(SynthesisError):
                synthesize_literature(project, RUN_ID, model=None)


if __name__ == "__main__":
    unittest.main()
