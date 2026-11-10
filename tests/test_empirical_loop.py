import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.empirical_loop import check_empirical_loop, run_empirical_paper
from research_agent.framework_api import ResearchAgentAPI
from research_agent.experiment_codegen import generate_experiment_code
from research_agent.writing_audit import audit_manuscript
from research_agent.writing_pack import build_writing_pack
from research_agent.experiment_runner import (
    approve_experiment,
    execute_experiment,
    ingest_experiment,
    sign_experiment_claim,
)
from tests.writing_support import RUN_ID, make_writing_project, write_draft

EXPERIMENT_ID = "EXP-EMPIRICAL"


class _FakeModel:
    model_id = "fake:empirical"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, json_mode=True):
        self.calls.append({"json_mode": json_mode, "messages": messages})
        if not self.responses:
            raise AssertionError("fake model has no responses left")
        return self.responses.pop(0)


class _JudgeModel:
    model_id = "fake:judge"

    def __init__(self, status="supported"):
        self.status = status

    def complete(self, messages, json_mode=True):
        payload = json.loads(messages[-1]["content"])
        return json.dumps(
            {
                "verdicts": [
                    {
                        "id": item["id"],
                        "status": self.status,
                        "rationale": "fake judge",
                        "evidence_refs": [item["evidence"][0]["ref"]],
                    }
                    for item in payload["items"]
                ]
            },
            ensure_ascii=False,
        )


def _innovation() -> dict:
    return {
        "status": "reviewed",
        "gaps": [
            {
                "gap_id": "GAP-01",
                "description": "学习曲线评估缺少统一协议",
                "why_unresolved": "现有工作各自定义指标",
                "observable": "跨种子方差",
                "evidence_refs": ["REF-01", "REF-02"],
            }
        ],
        "final_ideas": [
            {
                "idea_id": "IDEA-01",
                "title": "统一学习曲线评估",
                "mechanism": "证据账本约束评估协议",
                "falsification": "若跨数据集方差无下降则否证",
                "evidence_refs": ["REF-01", "REF-02"],
            }
        ],
    }


def _prepare(root: Path, *, signed: bool) -> Path:
    project = make_writing_project(root)
    experiment_file = project / "runs" / RUN_ID / "experiment.json"
    design = json.loads(experiment_file.read_text(encoding="utf-8"))
    design["idea_id"] = "IDEA-01"
    experiment_file.write_text(json.dumps(design, ensure_ascii=False), encoding="utf-8")
    data = project / "data.csv"
    rows = ["x1,x2,y"]
    for index in range(40):
        rows.append("%d,%d,%d" % (index, index % 5, index * 2 + (index % 4)))
    data.write_text("\n".join(rows) + "\n", encoding="utf-8")
    generate_experiment_code(
        project,
        RUN_ID,
        data_path="data.csv",
        target="y",
        features=["x1", "x2"],
        task="regression",
        methods=["dummy", "ridge"],
        seeds=2,
        experiment_id=EXPERIMENT_ID,
    )
    approve_experiment(project, EXPERIMENT_ID, "empirical loop test")
    execution = execute_experiment(project, EXPERIMENT_ID, allow_execute=True)
    if execution["status"] != "completed":
        raise AssertionError(execution)
    ingest_experiment(project, EXPERIMENT_ID)
    if signed:
        sign_experiment_claim(
            project,
            EXPERIMENT_ID,
            "Ridge is compared with the dummy baseline under the local protocol.",
            "checked synthetic protocol",
            ["metric=r2,value=0.0,comparator=>=,tolerance=0.01"],
        )
    (project / "runs" / RUN_ID / "innovation-review.json").write_text(
        json.dumps(_innovation(), ensure_ascii=False), encoding="utf-8"
    )
    return project


class EmpiricalLoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_blocks_unsigned_claim(self):
        project = _prepare(self.root, signed=False)
        result = check_empirical_loop(project, RUN_ID, EXPERIMENT_ID)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("human-signed" in item for item in result["blockers"]))
        self.assertFalse((project / "runs" / RUN_ID / "empirical-paper-loop.json").exists())

    def test_external_lint_error_blocks_empirical_loop(self):
        project = _prepare(self.root, signed=True)
        skill = self.root / "external" / "skills" / "scientific-writing" / "scripts" / "lint_manuscript.py"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "import json; print(json.dumps({'tool':'lint_manuscript','status':'fail',"
            "'summary':{'errors':1,'warnings':0},'issues':[{'severity':'error',"
            "'code':'PLACEHOLDER_FOUND'}]}))",
            encoding="utf-8",
        )
        result = run_empirical_paper(
            project,
            RUN_ID,
            EXPERIMENT_ID,
            project / "drafts" / "external-lint.md",
            review_rounds=0,
            offline_draft=True,
            external_lint=True,
            external_skill_root=str(skill.parents[3]),
        )
        self.assertEqual(result["status"], "needs_more_work", result)
        self.assertEqual(result["final_audit"]["external_lint"]["status"], "blocked")
        self.assertTrue(
            any("external_lint" in item for item in result["final_audit"]["blockers"]),
            result["final_audit"]["blockers"],
        )

    def test_external_consistency_error_blocks_empirical_loop(self):
        project = _prepare(self.root, signed=True)
        skill = (
            self.root
            / "external"
            / "skills"
            / "scientific-writing"
            / "scripts"
            / "check_consistency.py"
        )
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "import json; print(json.dumps({'tool':'check_consistency','status':'fail',"
            "'summary':{'errors':1,'warnings':0},'issues':[{'severity':'error',"
            "'code':'RESULT_WITHOUT_EVIDENCE'}]}))",
            encoding="utf-8",
        )
        registry = project / "consistency.json"
        registry.write_text("{}", encoding="utf-8")
        result = run_empirical_paper(
            project,
            RUN_ID,
            EXPERIMENT_ID,
            project / "drafts" / "external-consistency.md",
            review_rounds=0,
            offline_draft=True,
            external_consistency=True,
            external_consistency_registry="consistency.json",
            external_skill_root=str(skill.parents[3]),
        )
        self.assertEqual(result["status"], "needs_more_work", result)
        self.assertEqual(
            result["final_audit"]["external_consistency"]["status"], "blocked"
        )
        self.assertTrue(
            any("external_consistency" in item for item in result["final_audit"]["blockers"]),
            result["final_audit"]["blockers"],
        )

    def test_external_consistency_auto_derives_registry_and_blocks(self):
        project = _prepare(self.root, signed=True)
        skill = (
            self.root
            / "external"
            / "skills"
            / "scientific-writing"
            / "scripts"
            / "check_consistency.py"
        )
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "import json; print(json.dumps({'tool':'check_consistency','status':'fail',"
            "'summary':{'errors':1,'warnings':0},'issues':[{'severity':'error',"
            "'code':'RESULT_WITHOUT_EVIDENCE'}]}))",
            encoding="utf-8",
        )
        result = run_empirical_paper(
            project,
            RUN_ID,
            EXPERIMENT_ID,
            project / "drafts" / "external-consistency-auto.md",
            review_rounds=0,
            offline_draft=True,
            external_consistency=True,
            external_consistency_auto=True,
            external_skill_root=str(skill.parents[3]),
        )
        self.assertEqual(result["status"], "needs_more_work", result)
        self.assertEqual(
            result["final_audit"]["external_consistency"]["status"], "blocked"
        )
        self.assertEqual(
            result["final_audit"]["external_consistency_source"]["claim_status"],
            "signed",
        )
        self.assertTrue(
            any("external_consistency" in item for item in result["final_audit"]["blockers"]),
            result["final_audit"]["blockers"],
        )

    def test_writing_pack_binds_experiment_evidence_hash(self):
        project = _prepare(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID, experiment_id=EXPERIMENT_ID)
        evidence_path = project / "experiments" / EXPERIMENT_ID / "experiment-evidence.json"
        digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        self.assertEqual(pack["run"]["ea"]["sha256"], digest)
        self.assertTrue(pack["run"]["ea"]["hash_bound"])
        self.assertEqual(pack["run"]["ea"]["bound_claim_id"], "CLAIM-" + EXPERIMENT_ID)
        self.assertEqual(pack["claim"]["status"], "signed")
        self.assertTrue(pack["writing_contract"]["allowed_result_numbers"])

        evidence_path.write_text(
            evidence_path.read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        )
        stale = build_writing_pack(project, RUN_ID, experiment_id=EXPERIMENT_ID)
        self.assertEqual(stale["claim"]["status"], "invalidated")
        self.assertFalse(stale["run"]["ea"]["hash_bound"])
        self.assertEqual(stale["writing_contract"]["allowed_result_numbers"], [])
        self.assertTrue(
            any("invalidated" in item for item in stale["warnings"]),
            stale["warnings"],
        )

    def test_method_schematic_is_bound_but_not_a_result(self):
        project = _prepare(self.root, signed=True)
        draft = write_draft(
            self.root / "seed-method.md",
            result_text="图 1 展示了不同方法的均值与标准差；结果表明所提框架在多数设置下优于基线。",
        )
        body = draft.read_text(encoding="utf-8").replace(
            "我们采用统一协议比较不同策略 [REF-01]。",
            "我们采用统一协议比较不同策略，方法流程见图 2 [REF-01]。",
        )
        draft.write_text(body, encoding="utf-8")
        result = run_empirical_paper(
            project,
            RUN_ID,
            EXPERIMENT_ID,
            project / "drafts" / "empirical-method.md",
            model=_FakeModel([body]),
            review_rounds=0,
            method_template="calm-method",
        )
        self.assertEqual(result["status"], "ready_for_human_review", result)
        method = result["method_figure"]
        self.assertTrue(method["schematic"])
        self.assertEqual(method["kind"], "astradraw_scene")
        self.assertEqual(method["figure_number"], 2)
        pack = json.loads(
            (project / "runs" / RUN_ID / "writing-pack.json").read_text(encoding="utf-8")
        )
        self.assertTrue(pack["experiment_package"]["method_figure"]["schematic"])
        checks = {item["id"]: item for item in result["final_audit"]["checks"]}
        self.assertEqual(checks["method_figure.schematic"]["status"], "pass")
        self.assertNotIn("method_figure.not_result", checks)

        bad = body.replace("，方法流程见图 2 [REF-01]", " [REF-01]").replace(
            "图 1 展示了", "图 2 展示了"
        )
        bad_path = self.root / "bad-method.md"
        bad_path.write_text(bad, encoding="utf-8")
        bad_audit = audit_manuscript(bad_path, pack=pack)
        self.assertEqual(bad_audit["status"], "blocked")
        self.assertTrue(
            any("method_figure.not_result" in item for item in bad_audit["blockers"])
        )

    def test_semantic_support_ledger_gates_the_draft(self):
        project = _prepare(self.root, signed=True)
        draft_text = write_draft(
            self.root / "seed-semantic.md",
            result_text="图 1 展示了不同方法的均值与标准差；结果表明所提框架在多数设置下优于基线。",
        ).read_text(encoding="utf-8")
        result = run_empirical_paper(
            project,
            RUN_ID,
            EXPERIMENT_ID,
            project / "drafts" / "empirical-semantic.md",
            model=_FakeModel([draft_text]),
            review_model=_JudgeModel("supported"),
            review_rounds=0,
            semantic_support=True,
            strict_support=True,
        )
        self.assertEqual(result["status"], "ready_for_human_review", result)
        ledger = result["support_ledger"]
        self.assertEqual(ledger["status"], "ready")
        self.assertGreater(ledger["counts"]["supported"], 0)
        self.assertTrue((project / "runs" / RUN_ID / "support-ledger.json").is_file())

        blocked = run_empirical_paper(
            project,
            RUN_ID,
            EXPERIMENT_ID,
            project / "drafts" / "empirical-semantic-bad.md",
            model=_FakeModel([draft_text]),
            review_model=_JudgeModel("contradicted"),
            review_rounds=0,
            semantic_support=True,
            strict_support=True,
        )
        self.assertEqual(blocked["status"], "needs_more_work", blocked)
        self.assertEqual(blocked["support_ledger"]["status"], "blocked")

    def test_mcp_empirical_status_tool_returns_same_run_preflight(self):
        _prepare(self.root, signed=True)
        api = ResearchAgentAPI(self.root)
        response = api.call_tool(
            "research_empirical_status",
            {
                "project_dir": "project",
                "run_id": RUN_ID,
                "experiment_id": EXPERIMENT_ID,
            },
        )
        result = response["result"]
        self.assertEqual(result["status"], "ready_for_writing", result)
        self.assertTrue(result["experiment"]["idea_grounded"])
        self.assertIn("never executes experiments", result["boundary"])

    def test_low_review_score_is_not_reported_ready(self):
        project = _prepare(self.root, signed=True)
        draft_text = write_draft(
            self.root / "seed-low.md", result_text="图 1 展示了不同方法的均值与标准差；结果表明所提框架在多数设置下优于基线。"
        ).read_text(encoding="utf-8")
        low_review = json.dumps(
            {
                "scores": {
                    "evidence": 5.0,
                    "contribution": 5.0,
                    "method": 5.0,
                    "clarity": 5.0,
                    "venue_fit": 5.0,
                },
                "overall": 5.0,
                "strengths": ["结构完整"],
                "weaknesses": ["证据和贡献不足"],
                "must_fix": ["加强结果与来源对照"],
                "section_actions": [],
                "decision": "revise",
            },
            ensure_ascii=False,
        )
        result = run_empirical_paper(
            project,
            RUN_ID,
            EXPERIMENT_ID,
            project / "drafts" / "empirical-low.md",
            model=_FakeModel([draft_text]),
            review_model=_FakeModel([low_review]),
            review_rounds=1,
            threshold=8.0,
        )
        self.assertEqual(result["status"], "needs_more_work", result)
        self.assertEqual(result["review"]["status"], "needs_more_work")
        self.assertIn("加强结果与来源对照", result["review"]["must_fix"])
        self.assertEqual(result["final_audit"]["status"], "ready_for_human_review")
        self.assertEqual(result["closure"]["status"], "ready_for_human_signature")
        self.assertTrue(any("below threshold" in item for item in result["human_actions"]))

    def test_same_run_loop_reaches_human_review_without_signing(self):
        project = _prepare(self.root, signed=True)
        draft_text = write_draft(
            self.root / "seed.md", result_text="图 1 展示了不同方法的均值与标准差；结果表明所提框架在多数设置下优于基线。"
        ).read_text(encoding="utf-8")
        review_payload = json.dumps(
            {
                "scores": {
                    "evidence": 8.4,
                    "contribution": 8.2,
                    "method": 8.0,
                    "clarity": 8.5,
                    "venue_fit": 8.1,
                },
                "overall": 8.3,
                "strengths": ["证据链完整"],
                "weaknesses": ["可补更多对照"],
                "must_fix": [],
                "section_actions": [],
                "decision": "accept",
            },
            ensure_ascii=False,
        )
        output = project / "drafts" / "empirical.md"
        writer = _FakeModel([draft_text])
        result = run_empirical_paper(
            project,
            RUN_ID,
            EXPERIMENT_ID,
            output,
            model=writer,
            review_model=_FakeModel([review_payload]),
            review_rounds=1,
        )
        self.assertEqual(result["status"], "ready_for_human_review", result)
        self.assertTrue(output.is_file())
        self.assertEqual(result["final_audit"]["status"], "ready_for_human_review")
        self.assertEqual(result["closure"]["status"], "ready_for_human_signature")
        self.assertFalse(result["submission_ready"])
        pack = json.loads(
            (project / "runs" / RUN_ID / "writing-pack.json").read_text(encoding="utf-8")
        )
        self.assertEqual(pack["claim"]["status"], "signed")
        self.assertEqual(pack["experiment_package"]["experiment_id"], EXPERIMENT_ID)
        self.assertIsNotNone(pack["experiment_package"]["figure"])
        self.assertFalse(pack["experiment_package"]["figure"]["schematic"])
        self.assertEqual(result["figure"]["status"], "clean")
        self.assertTrue(Path(result["figure"]["png"]).is_file())
        self.assertIn("图 1", pack["experiment_package"]["figure"]["caption"])
        self.assertEqual(pack["experiment_design"]["hypothesis"], "统一评估协议能减少决策错误。")
        self.assertEqual(pack["experiment_design"]["idea_id"], "IDEA-01")
        self.assertTrue(result["preflight"]["experiment"]["idea_grounded"])
        baseline_mean = "%.4f" % pack["experiment_package"]["metrics_summary"]["dummy"]["mean"]
        self.assertIn(baseline_mean, pack["writing_contract"]["allowed_result_numbers"])
        prompt = writer.calls[0]["messages"][1]["content"]
        self.assertIn("中文实证研究论文", prompt)
        self.assertIn("allowed_result_numbers", prompt)
        self.assertIn("已人签实验证据", prompt)
        self.assertNotIn("不放实验数值", prompt)
        self.assertTrue((project / "runs" / RUN_ID / "empirical-paper-loop.json").is_file())
        self.assertTrue((project / "runs" / RUN_ID / "writing-audit.json").is_file())
        self.assertFalse(
            (
                project
                / "experiments"
                / EXPERIMENT_ID
                / "experiment-closure"
                / "signature.json"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
