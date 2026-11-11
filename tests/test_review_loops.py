import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent.innovation_review import InnovationReviewError, run_innovation_review
from research_agent.manuscript_review import (
    ManuscriptReviewError,
    review_progress,
    run_manuscript_review,
)
from research_agent.manuscript_writer import generate_manuscript
from tests.writing_support import RUN_ID, make_writing_project, write_draft


class _FakeModel:
    model_id = "fake:test"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, json_mode=True):
        self.calls.append({"json_mode": json_mode, "messages": messages})
        if not self.responses:
            raise AssertionError("fake model has no responses left")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _idea_payload(tag="v1"):
    return json.dumps(
        {
            "gaps": [
                {
                    "description": "失败轨迹的筛选标准缺少统一证据账本。",
                    "why_unresolved": "现有工作各自定义清洗规则，无法横向比较。",
                    "observable": "跨任务方差和筛选规则覆盖率。",
                    "evidence_refs": ["REF-01", "REF-03"],
                },
                {
                    "description": "多智能体角色数量与收益之间缺少消融证据。",
                    "why_unresolved": "角色分工多以案例展示，未控制调用成本。",
                    "observable": "成功率随角色数的变化。",
                    "evidence_refs": ["REF-01", "REF-02"],
                },
                {
                    "description": "指令混合的配比决策缺少可追溯依据。",
                    "why_unresolved": "配比常由经验决定，未绑定来源证据。",
                    "observable": "配比变化下的下游任务表现。",
                    "evidence_refs": ["REF-02", "REF-03"],
                },
            ],
            "ideas": [
                {
                    "title": "统一失败轨迹的可审计复用 %s" % tag,
                    "problem": "失败轨迹的筛选标准不稳定，导致训练信号漂移。",
                    "mechanism": "用证据账本记录失败类型、筛选规则和更新结果。",
                    "novelty_claim": "把失败轨迹复用从启发式清洗变成可审计协议。",
                    "falsification": "若统一协议不能降低跨任务性能方差，则假设被否证。",
                    "experiment_plan": {
                        "profile": "search_factorial",
                        "dataset": "iris",
                        "baseline": "memory_off_gate_off",
                        "metric": "improvement_per_evaluation",
                        "stopping_rule": "固定验证评估预算，多种子配对后停止",
                    },
                    "evidence_refs": ["REF-01", "REF-02"],
                    "risks": ["任务规模有限"],
                },
                {
                    "title": "角色分工的最小充分集 %s" % tag,
                    "problem": "多智能体角色越多，协调成本越高。",
                    "mechanism": "用消融实验寻找推理/执行/验证的最小充分角色集。",
                    "novelty_claim": "把角色数量当作可检验的设计变量。",
                    "falsification": "若减少角色后指标不下降，则角色扩展假设被否证。",
                    "experiment_plan": {
                        "profile": "protocol_run",
                        "dataset": "breast_cancer",
                        "baseline": "默认配置",
                        "metric": "accuracy",
                        "stopping_rule": "固定种子预算后停止",
                    },
                    "evidence_refs": ["REF-01", "REF-02"],
                    "risks": ["成本测量困难"],
                },
                {
                    "title": "指令混合的证据化配比 %s" % tag,
                    "problem": "指令配比依赖经验，缺少可追溯的决策依据。",
                    "mechanism": "把配比决策绑定到来源证据和小规模消融。",
                    "novelty_claim": "用证据账本约束数据配比搜索。",
                    "falsification": "若证据约束不能优于随机配比，则假设被否证。",
                    "experiment_plan": {
                        "profile": "local_tabular_experiment",
                        "dataset": "user-provided CSV inside the project",
                        "baseline": "dummy",
                        "metric": "r2",
                        "stopping_rule": "固定搜索预算",
                    },
                    "evidence_refs": ["REF-01", "REF-02"],
                    "risks": ["数据泄漏不可完全排除"],
                },
            ]
        },
        ensure_ascii=False,
    )


def _review_payload(score):
    return json.dumps(
        {
            "scores": [
                {"idea_id": "IDEA-01", "score": score, "strengths": ["清楚"], "weaknesses": ["需更多证据"], "must_fix": ["补足证据链"]},
                {"idea_id": "IDEA-02", "score": score, "strengths": ["可测"], "weaknesses": ["成本"], "must_fix": ["明确停止规则"]},
                {"idea_id": "IDEA-03", "score": score, "strengths": ["具体"], "weaknesses": ["风险"], "must_fix": ["补充风险"]},
            ],
            "overall": "ok",
        },
        ensure_ascii=False,
    )


def _manuscript_review(score):
    return json.dumps(
        {
            "scores": {
                "evidence": score,
                "contribution": score,
                "method": score,
                "clarity": score,
                "venue_fit": score,
            },
            "overall": score,
            "strengths": ["结构完整"],
            "weaknesses": ["论证需要更具体"],
            "must_fix": ["补充与其他路径的对照"],
            "section_actions": [{"heading": "讨论", "action": "增加限制与对照"}],
            "decision": "revise",
        },
        ensure_ascii=False,
    )


class InnovationReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_round_review_reaches_threshold(self):
        project = make_writing_project(self.root)
        model = _FakeModel(
            [
                _idea_payload("v1"),
                _review_payload(6),
                _review_payload(6),
                _review_payload(6),
                _idea_payload("v2"),
                _review_payload(8.5),
                _review_payload(8.5),
                _review_payload(8.5),
            ]
        )
        result = run_innovation_review(
            project, RUN_ID, rounds=2, threshold=8.0, model=model
        )
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["rounds_completed"], 2)
        self.assertEqual(len(result["selected_ideas"]), 3)
        self.assertGreater(
            result["iterations"][1]["overall"], result["iterations"][0]["overall"]
        )
        self.assertTrue((project / "runs" / RUN_ID / "innovation-review.json").is_file())
        self.assertTrue((project / "runs" / RUN_ID / "innovation-report.md").is_file())
        self.assertTrue((project / "runs" / RUN_ID / "innovation-iterations.jsonl").is_file())
        for idea in result["final_ideas"]:
            self.assertTrue(set(idea["evidence_refs"]).issubset({"REF-01", "REF-02"}))

    def test_unknown_evidence_is_repaired_or_rejected(self):
        project = make_writing_project(self.root)
        bad = json.loads(_idea_payload())
        bad["ideas"][0]["evidence_refs"] = ["REF-99", "REF-01"]
        model = _FakeModel([json.dumps(bad, ensure_ascii=False), json.dumps(bad, ensure_ascii=False)])
        with self.assertRaises(InnovationReviewError):
            run_innovation_review(project, RUN_ID, rounds=1, model=model)
        self.assertEqual(len(model.calls), 2)

    def test_support_patch_rewrites_only_flagged_sentences(self):
        project = make_writing_project(self.root, with_run=False)
        draft = write_draft(
            self.root / "draft-patch.md",
            result_text="需要改写的断言目前仍缺少足够证据支持 [REF-01]。结果表明所提框架在多数设置下优于基线。",
        )
        original = draft.read_text(encoding="utf-8")
        patch = json.dumps(
            {
                "replacements": [
                    {
                        "find": "需要改写的断言目前仍缺少足够证据支持 [REF-01]。",
                        "rewrite": "在证据范围内，该结论成立 [REF-01]。",
                    }
                ]
            },
            ensure_ascii=False,
        )

        def judge(payload):
            return [
                {
                    "id": item["id"],
                    "status": (
                        "partial"
                        if "需要改写" in item["sentence"]
                        else "supported"
                    ),
                    "rationale": "fake support judge",
                    "evidence_refs": (
                        [item["evidence"][0]["ref"]] if item["evidence"] else []
                    ),
                }
                for item in payload["items"]
            ]

        model = _FakeModel(
            [
                _manuscript_review(6.2),
                patch,
                _manuscript_review(8.3),
            ]
        )
        result = run_manuscript_review(
            project,
            RUN_ID,
            draft,
            rounds=2,
            threshold=8.0,
            model=model,
            support_judge=judge,
            strict_support=True,
            support_votes=1,
            revision_mode="support",
        )
        self.assertEqual(result["status"], "reviewed", result)
        revision = next(
            item for item in result["iterations"] if item.get("stage") == "revision"
        )
        self.assertEqual(revision["revision_mode"], "support")
        self.assertEqual(revision["revised_sections"], ["结果"])
        final = Path(result["final_draft"]).read_text(encoding="utf-8")
        self.assertIn("在证据范围内，该结论成立 [REF-01]。", final)
        self.assertNotIn("需要改写的断言", final)
        self.assertIn("## 参考文献", final)
        self.assertNotIn("results.numbers_without_claim", result["final_audit"]["blockers"])

    def test_section_revision_preserves_unmodified_sections(self):
        project = make_writing_project(self.root, with_run=False)
        draft = write_draft(
            self.root / "draft-section.md",
            result_text="结果表明所提框架在多数设置下优于基线。",
        )
        original = draft.read_text(encoding="utf-8")
        revised_section = (
            "结果仍需在更多数据集上复核，并与跨来源证据逐条对照 [REF-01]。"
        )
        review_low = json.loads(_manuscript_review(6.0))
        review_low["section_actions"] = [
            {"heading": "讨论", "action": "增加证据对照"}
        ]
        review_high = json.loads(_manuscript_review(8.2))
        model = _FakeModel(
            [
                json.dumps(review_low, ensure_ascii=False),
                revised_section,
                json.dumps(review_high, ensure_ascii=False),
            ]
        )
        result = run_manuscript_review(
            project,
            RUN_ID,
            draft,
            rounds=2,
            threshold=8.0,
            model=model,
            revision_mode="section",
        )
        self.assertEqual(result["status"], "reviewed", result)
        revision = next(
            item for item in result["iterations"] if item.get("stage") == "revision"
        )
        self.assertEqual(revision["revision_mode"], "section")
        self.assertEqual(revision["revised_sections"], ["讨论"])
        final = Path(result["final_draft"]).read_text(encoding="utf-8")
        for heading in ("## 摘要", "## 引言", "## 相关工作", "## 方法", "## 实验", "## 结果", "## 讨论", "## 结论", "## 参考文献"):
            self.assertIn(heading, final)
        self.assertIn(revised_section, final)
        self.assertNotIn(original.split("## 讨论")[1].split("## 结论")[0].strip(), final)

    def test_ab_check_gates_revision_acceptance(self):
        project = make_writing_project(self.root, with_run=False)
        draft = write_draft(
            self.root / "draft-ab.md",
            result_text="结果表明所提框架在多数设置下优于基线。",
        )
        original = draft.read_text(encoding="utf-8").replace(
            "结果仍需在更多数据集上复核 [REF-01]。",
            "结果仍需在更多数据集上复核，并报告配对差异、置信区间与跨来源证据对照，避免将局部结论外推 [REF-01]。",
        )
        draft.write_text(original, encoding="utf-8")
        revised = original.replace(
            "避免将局部结论外推 [REF-01]。",
            "避免将局部结论外推，并在讨论中补充失败案例与替代解释 [REF-01]。",
        )
        model = _FakeModel(
            [
                _manuscript_review(6.0),
                revised,
                _manuscript_review(8.2),
            ]
        )
        ab_tie = json.dumps(
            {
                "scores": {
                    "A": {"clarity": 8.0, "argument": 8.0, "evidence_consistency": 8.0, "academic_style": 8.0},
                    "B": {"clarity": 8.0, "argument": 8.0, "evidence_consistency": 8.0, "academic_style": 8.0},
                },
                "winner": "tie",
                "reason": "comparable",
                "issues": {"A": [], "B": []},
            },
            ensure_ascii=False,
        )
        result = run_manuscript_review(
            project,
            RUN_ID,
            draft,
            rounds=2,
            threshold=8.0,
            model=model,
            ab_reviewer=_FakeModel([ab_tie]),
            ab_sections=["讨论"],
        )
        self.assertEqual(result["status"], "reviewed", result)
        revision = next(
            item for item in result["iterations"] if item.get("stage") == "revision"
        )
        self.assertEqual(revision["ab_review"]["overall_winner"], "tie")
        self.assertTrue(revision["accepted"], revision["reason"])

    def test_semantic_support_is_fed_into_revision_and_acceptance(self):
        project = make_writing_project(self.root, with_run=False)
        draft = write_draft(
            self.root / "draft-support.md",
            result_text="无证据的断言。结果表明所提框架在多数设置下优于基线。",
        )
        original = draft.read_text(encoding="utf-8")
        revised = original.replace("无证据的断言。", "")

        def judge(payload):
            return [
                {
                    "id": item["id"],
                    "status": (
                        "insufficient"
                        if "无证据" in item["sentence"]
                        else "supported"
                    ),
                    "rationale": "fake support judge",
                    "evidence_refs": (
                        [item["evidence"][0]["ref"]] if item["evidence"] else []
                    ),
                }
                for item in payload["items"]
            ]

        model = _FakeModel(
            [
                _manuscript_review(6.0),
                revised,
                _manuscript_review(8.2),
            ]
        )
        result = run_manuscript_review(
            project,
            RUN_ID,
            draft,
            rounds=2,
            threshold=8.0,
            model=model,
            support_judge=judge,
            strict_support=True,
            judge_model_id="fake",
        )
        self.assertEqual(result["status"], "reviewed", result)
        self.assertEqual(result["support"]["counts"]["insufficient"], 0)
        self.assertTrue(
            (Path(result["final_draft"]).parent / "support-ledger.json").is_file()
        )
        revision = next(
            item for item in result["iterations"] if item.get("stage") == "revision"
        )
        self.assertTrue(revision["accepted"], revision["reason"])

    def test_revision_cannot_change_reported_result_numbers(self):
        from research_agent.manuscript_review import _accept_candidate

        accepted, reason = _accept_candidate(
            "a" * 200,
            "a" * 200,
            {
                "status": "ready_for_human_review",
                "blockers": [],
                "result_number_count": 1,
                "result_numbers": ["0.1438"],
            },
            {
                "status": "ready_for_human_review",
                "blockers": [],
                "result_number_count": 1,
                "result_numbers": ["0.187"],
            },
        )
        self.assertFalse(accepted)
        self.assertIn("changes or drops", reason)

    def test_requires_model(self):
        project = make_writing_project(self.root)
        with mock.patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "",
                "RESEARCH_AGENT_MODEL_STORE": str(Path(self.root) / "no-gateway.json"),
            },
            clear=False,
        ):
            with self.assertRaises(InnovationReviewError) as raised:
                run_innovation_review(project, RUN_ID, rounds=1, model=None)
        message = str(raised.exception)
        self.assertIn("no usable model", message)
        self.assertIn("host_agent", message)


class ManuscriptReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_review_revision_review_improves_and_preserves_audit(self):
        project = make_writing_project(self.root, with_run=False)
        draft = write_draft(
            self.root / "draft.md",
            result_text="结果表明所提框架在多数设置下优于基线。",
        )
        original = draft.read_text(encoding="utf-8")
        revised = original.replace(
            "已有综述总结了学习曲线方法 [REF-01]。",
            "已有综述总结了学习曲线方法，并把决策情境、曲线问题与资源类型作为分类轴 [REF-01]。\n\n"
            "与只做方法罗列的综述相比，本文更强调证据可追溯性与跨任务复核。",
        )
        model = _FakeModel(
            [
                _manuscript_review(6.5),
                revised,
                _manuscript_review(8.2),
            ]
        )
        result = run_manuscript_review(
            project, RUN_ID, draft, rounds=2, threshold=8.0, model=model
        )
        self.assertEqual(result["status"], "reviewed")
        self.assertTrue(result["improved"])
        self.assertGreaterEqual(result["best_score"], 8.0)
        self.assertFalse(result["submission_ready"])
        self.assertEqual(result["final_audit"]["status"], "ready_for_human_review")
        final_text = Path(result["final_draft"]).read_text(encoding="utf-8")
        self.assertIn("[REF-01]", final_text)
        self.assertNotIn("0.1438", final_text)
        self.assertTrue((Path(result["final_draft"]).parent / "manuscript-review.json").is_file())

    def test_revision_with_new_result_number_is_rejected(self):
        project = make_writing_project(self.root)
        draft = write_draft(
            self.root / "draft.md",
            result_text="结果表明所提框架在多数设置下优于基线。",
        )
        original = draft.read_text(encoding="utf-8")
        bad_revision = original.replace(
            "结果表明所提框架在多数设置下优于基线。",
            "结果表明所提框架在多数设置下优于基线，R² 为 0.9999。",
        )
        model = _FakeModel(
            [
                _manuscript_review(6.0),
                bad_revision,
            ]
        )
        result = run_manuscript_review(
            project, RUN_ID, draft, rounds=2, threshold=8.0, model=model
        )
        self.assertEqual(result["accepted_revisions"], 0)
        final_text = Path(result["final_draft"]).read_text(encoding="utf-8")
        final_text = re.sub(r"<!--\s*writing-pack:.*?-->\s*", "", final_text, count=1)
        self.assertEqual(final_text, original)
        self.assertTrue(
            any(
                item.get("stage") == "revision" and not item.get("accepted")
                for item in result["iterations"]
            )
        )

    def test_revision_cannot_drop_all_result_numbers(self):
        from research_agent.manuscript_review import _accept_candidate

        accepted, reason = _accept_candidate(
            "a" * 200,
            "a" * 200,
            {"status": "ready_for_human_review", "blockers": [], "result_number_count": 2},
            {"status": "ready_for_human_review", "blockers": [], "result_number_count": 0},
        )
        self.assertFalse(accepted)
        self.assertIn("drops all", reason)

    def test_review_progress_flags_same_concerns_rescored(self):
        prev = {"must_fix": ["补充对照", "明确停止规则"]}
        same = {"must_fix": ["明确停止规则", "补充对照"]}
        changed = {"must_fix": ["补充对照"]}
        self.assertFalse(review_progress(prev, same)["progress"])
        self.assertEqual(review_progress(prev, same)["reason"], "no_progress_same_concerns")
        self.assertTrue(review_progress(prev, changed)["progress"])
        self.assertTrue(review_progress(None, same)["progress"])
        self.assertTrue(review_progress(prev, {"must_fix": []})["progress"])

    def test_same_concerns_rescored_stops_the_loop(self):
        project = make_writing_project(self.root, with_run=False)
        draft = write_draft(
            self.root / "draft.md",
            result_text="结果表明所提框架在多数设置下优于基线。",
        )
        original = draft.read_text(encoding="utf-8")
        revised = original.replace(
            "已有综述总结了学习曲线方法 [REF-01]。",
            "已有综述总结了学习曲线方法，并补充分类轴 [REF-01]。",
        )
        model = _FakeModel(
            [_manuscript_review(6.0), revised, _manuscript_review(6.5)]
        )
        result = run_manuscript_review(
            project, RUN_ID, draft, rounds=3, threshold=8.0, model=model
        )
        self.assertEqual(result["stop_reason"], "no_progress_same_concerns")
        self.assertEqual(result["rounds_completed"], 2)
        self.assertEqual(result["accepted_revisions"], 1)
        self.assertEqual(result["status"], "needs_more_work")

    def test_no_op_revision_is_rejected(self):
        project = make_writing_project(self.root, with_run=False)
        draft = write_draft(
            self.root / "draft.md",
            result_text="结果表明所提框架在多数设置下优于基线。",
        )
        original = draft.read_text(encoding="utf-8")
        model = _FakeModel([_manuscript_review(6.0), original])
        result = run_manuscript_review(
            project, RUN_ID, draft, rounds=2, threshold=8.0, model=model
        )
        self.assertEqual(result["accepted_revisions"], 0)
        self.assertEqual(result["stop_reason"], "revision_rejected")
        self.assertTrue(
            any(
                item.get("stage") == "revision" and item.get("reason") == "no_op_revision"
                for item in result["iterations"]
            )
        )

    def test_requires_model(self):
        project = make_writing_project(self.root)
        draft = write_draft(self.root / "draft.md", result_text="无数字。")
        with self.assertRaises(ManuscriptReviewError):
            run_manuscript_review(project, RUN_ID, draft, model=None)


class ManuscriptWriterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_writer_prompt_maps_each_ref_to_selected_spans(self):
        project = make_writing_project(self.root, with_run=False)
        innovation = {"gaps": [], "final_ideas": []}
        good = write_draft(self.root / "good.md", result_text="无数字。").read_text(
            encoding="utf-8"
        )
        fake = _FakeModel([good])
        generate_manuscript(
            project,
            RUN_ID,
            self.root / "drafts" / "mapped.md",
            model=fake,
            innovation=innovation,
        )
        prompt = fake.calls[0]["messages"][1]["content"]
        self.assertIn("引用-证据对照", prompt)
        self.assertIn("[REF-01]", prompt)
        self.assertIn("S1-S01-01", prompt)
        self.assertIn("只能支持", prompt)
        self.assertIn("每句最多保留一个", prompt)
        self.assertIn("Claim plan", prompt)
        self.assertIn("只对应一个 claim", prompt)

    def test_writer_repairs_unknown_citation_once(self):
        project = make_writing_project(self.root, with_run=False)
        innovation = {
            "gaps": [
                {"gap_id": "GAP-01", "description": "失败轨迹筛选不稳定", "why_unresolved": "缺少统一协议", "observable": "跨任务方差", "evidence_refs": ["REF-01"]}
            ],
            "final_ideas": [
                {"idea_id": "IDEA-01", "title": "可审计失败轨迹", "mechanism": "证据账本", "falsification": "若方差不降则否证", "evidence_refs": ["REF-01", "REF-02"]}
            ],
        }
        bad = write_draft(self.root / "bad.md", result_text="无数字。", citation="[REF-99]").read_text(encoding="utf-8")
        good = write_draft(self.root / "good.md", result_text="无数字。", citation="[REF-01]").read_text(encoding="utf-8")
        fake = _FakeModel([bad, good])
        output = self.root / "drafts" / "review.md"
        result = generate_manuscript(
            project,
            RUN_ID,
            output,
            model=fake,
            innovation=innovation,
            repair_attempts=1,
        )
        self.assertEqual(result["status"], "generated")
        self.assertEqual(result["repair_attempts"], 1)
        self.assertEqual(result["audit"]["status"], "ready_for_human_review")
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[0]["json_mode"], False)
        self.assertIn("[REF-01]", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
