import json
import unittest
from pathlib import Path

from research_agent.adapters.real_corpus_retriever import RealCorpusRetriever
from research_agent.adapters.svg_audit import audit_svg
from research_agent.adapters.simple_parser import SimpleParser
from research_agent.contracts import (
    FigureEdge,
    FigureNode,
    LiteratureBrief,
    SourceBrief,
    Span,
)
from research_agent.modules.experiment import ExperimentDesignAgent, ExperimentRequest
from research_agent.modules.figure import FigureAgent, FigureRequest
from research_agent.modules.grant import GrantAgent, GrantRequest
from research_agent.modules.idea import IdeaAgent, IdeaRequest
from research_agent.modules.paper import PaperAgent, PaperRequest
from research_agent.modules.run import RunAgent
from research_agent.pipeline import (
    PipelineError,
    PipelineRequest,
    PipelineRunner,
    render_report_markdown,
    write_pipeline_artifacts,
)
from research_agent.specs import SpecStore


class ModuleContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SpecStore()
        cls.specs = {name: cls.store.load(name) for name in ("literature", "idea", "experiment", "figure", "paper", "grant")}

    def test_registry_exposes_all_modules(self):
        ids = {spec.id for spec in self.store.list_specs()}
        self.assertTrue({"literature", "idea", "experiment", "figure", "paper", "grant"} <= ids)

    def test_idea_frames_are_candidates_with_falsification(self):
        spans = [
            Span("S-1", "FX-001", "Results", "fixture 结果句，用于候选框架测试。", 0, 20),
            Span("S-2", "FX-002", "Method", "fixture 方法句，用于候选框架测试。", 0, 20),
        ]
        result = IdeaAgent(self.specs["idea"]).run(IdeaRequest("fixture topic", spans, 2))
        self.assertEqual(result.status, "candidates_need_human")
        self.assertEqual(len(result.candidates), 2)
        self.assertTrue(all(card.falsification for card in result.candidates))
        self.assertTrue(all(card.status == "candidate" for card in result.candidates))

    def test_experiment_design_requires_fields(self):
        agent = ExperimentDesignAgent(self.specs["experiment"])
        incomplete = agent.run(ExperimentRequest("q"))
        self.assertEqual(incomplete.status, "needs_human")
        self.assertTrue(any("missing" in warning for warning in incomplete.warnings))
        complete = agent.run(
            ExperimentRequest(
                "q", hypothesis="h", baseline="b", primary_metric="m",
                controls=["negative"], seeds=3, budget="cap",
            )
        )
        self.assertEqual(complete.status, "ready_for_g2")
        self.assertIn("不得事后修改", complete.stopping_rule)

    def test_paper_routes_language_and_keeps_result_slots_pending(self):
        agent = PaperAgent(self.specs["paper"])
        paper = agent.run(PaperRequest("topic", language="zh", venue_type="zh_core_journal", evidence_refs=["S-1"]))
        self.assertEqual(paper.profile.citation_style, "GB/T 7714-2015")
        self.assertEqual(paper.claims, [])
        self.assertTrue(all(slot.status == "pending_evidence" for slot in paper.slots))
        bound = agent.run(PaperRequest(
            "topic", language="zh", venue_type="zh_core_journal",
            evidence_refs=["S-1"], claim_refs=["CLM-TEST"],
        ))
        primary = next(slot for slot in bound.slots if slot.slot_id == "result.primary")
        self.assertEqual(primary.status, "bound_claim")
        self.assertEqual(bound.claims, ["CLM-TEST"])
        self.assertTrue(any("does not re-verify" in warning for warning in bound.warnings))
        with self.assertRaises(Exception):
            agent.run(PaperRequest("topic", language="zh", venue_type="en_conference"))

    def test_paper_draft_keeps_result_numbers_out_without_claim(self):
        brief = LiteratureBrief(
            coverage_score=0.5,
            saturation="partial",
            target_sources=6,
            target_full_text=3,
            facets=[],
            source_briefs=[
                SourceBrief(
                    "S-1", "Fixture source", 2025, "Venue", True, 1,
                    ["Results"], "fixture excerpt",
                )
            ],
            sections=[],
            highlights=[],
            summary="1 source / 1 span",
            gaps=["thin_source_count"],
        )
        span = Span("S-1-S01-01", "S-1", "Results", "Fixture 结果句，用于写作边界测试。", 0, 20)
        paper = PaperAgent(self.specs["paper"]).run(
            PaperRequest(
                "fixture topic", language="zh", venue_type="zh_core_journal",
                evidence_refs=[span.span_id], spans=[span], literature_brief=brief,
                fixture_mode=True,
            )
        )
        self.assertTrue(paper.draft)
        self.assertEqual(paper.writer_mode, "deterministic")
        result_section = next(item for item in paper.draft if item.section == "结果")
        self.assertNotIn("420", result_section.text)
        self.assertNotIn("780", result_section.text)
        self.assertEqual(result_section.status, "pending_evidence")
        self.assertTrue(any("fixture" in warning for warning in paper.warnings))

    def test_paper_renders_the_study_design_not_the_run_design(self):
        span = Span("S-1-S01-01", "S-1", "Results", "Fixture 结果句，用于写作边界测试。", 0, 20)
        study = {
            "schema_version": "study-design-0.1",
            "question": "记录完整性是否决定湿热稳定性差异可判定？",
            "hypothesis": "只有完整记录时差异才可能被判定。",
            "claims": [
                {"claim": "完整记录提高可判定率。", "type": "beats_prior", "evidence": "配对比较两种记录协议。"}
            ],
            "datasets": [{"name": "lab", "role": "test", "data_status": "planned",
                          "splits": "batch split", "leakage_checks": "device id", "license": "internal"}],
            "baselines": [{"name": "control", "implementation": "official", "tuning": "none", "compute": "same chamber"}],
            "ablations": [{"name": "remove passivation", "mechanism": "interface only", "single_change": True}],
            "statistics": {"seeds": 3},
        }
        paper = PaperAgent(self.specs["paper"]).run(
            PaperRequest(
                "fixture topic", language="zh", venue_type="zh_core_journal",
                evidence_refs=[span.span_id], spans=[span],
                study_design=study, study_design_audit={"status": "incomplete", "ccfa": {"level": "disclosure_incomplete"}},
                run_summary={"dataset": "sklearn:iris:150x4", "status": "completed"},
            )
        )
        setup = next(item for item in paper.draft if item.section == "实验设计")
        self.assertIn("记录完整性是否决定", setup.text)
        self.assertIn("完整记录提高可判定率", setup.text)
        self.assertNotIn("StandardScaler", setup.text)
        self.assertIn("study design supplied", " ".join(paper.warnings))

    def test_paper_labels_a_local_run_as_protocol_validation(self):
        span = Span("S-1-S01-01", "S-1", "Results", "Fixture 结果句，用于写作边界测试。", 0, 20)
        paper = PaperAgent(self.specs["paper"]).run(
            PaperRequest(
                "fixture topic", language="zh", venue_type="zh_core_journal",
                evidence_refs=[span.span_id], spans=[span],
                claim_statements=["On the local iris protocol, mean accuracy is 0.956."],
                run_summary={"dataset": "sklearn:iris:150x4", "status": "completed"},
            )
        )
        setup = next(item for item in paper.draft if item.section == "实验设计")
        results = next(item for item in paper.draft if item.section == "结果")
        # The local run is a protocol validation, not the study's scientific design; a reader
        # must not see its dataset metric presented as the paper's result.
        self.assertIn("本地协议验证设计", setup.text)
        self.assertIn("本地协议验证 run", results.text)

    def test_paper_renders_verified_claim_assertions(self):
        paper = PaperAgent(self.specs["paper"]).run(
            PaperRequest(
                "validated topic",
                language="en",
                venue_type="en_conference",
                evidence_refs=["S-1"],
                claim_refs=["CLM-1"],
                claim_statements=["The protocol reaches 0.94 mean accuracy."],
                claim_assertions=[
                    {
                        "metric": "accuracy",
                        "comparator": ">=",
                        "value": 0.94,
                        "observed": 0.943,
                        "tolerance": 0.01,
                        "status": "pass",
                    }
                ],
            )
        )
        result = next(item for item in paper.draft if item.section == "Results")
        self.assertIn("0.94", result.text)
        self.assertIn("observed=0.943", result.text)
        self.assertEqual(result.status, "bound_claim")

    def test_paper_writer_is_rejected_when_it_invents_citations_or_numbers(self):
        brief = LiteratureBrief(
            coverage_score=0.5, saturation="partial", target_sources=6, target_full_text=3,
            facets=[], sections=[], highlights=[], summary="1 source / 1 span",
            source_briefs=[
                SourceBrief("S-1", "Fixture source", 2025, "Venue", True, 1, ["Results"], "excerpt")
            ],
            gaps=[],
        )
        span = Span("S-1-S01-01", "S-1", "Results", "fixture evidence sentence for writer.", 0, 20)
        base = dict(
            topic="fixture topic", language="zh", venue_type="zh_core_journal",
            evidence_refs=[span.span_id], spans=[span], literature_brief=brief,
            fixture_mode=True,
        )

        def good_writer(payload):
            ref = payload["allowed_evidence"][0]["ref"]
            return {
                "abstract": "这是由模型生成的摘要草稿，只依赖给定证据，不写结果数字。" * 3,
                "introduction": ("这是由模型生成的引言草稿，引用给定证据 [%s]。" % ref) * 3,
                "related_work": ("相关工作草稿，只引用给定来源 [%s]。" % ref) * 3,
                "results": "模型不应写入的结果段。",
            }

        paper = PaperAgent(self.specs["paper"], section_writer=good_writer).run(PaperRequest(**base))
        self.assertEqual(paper.writer_mode, "model")
        result_section = next(item for item in paper.draft if item.section == "结果")
        self.assertNotIn("模型不应写入", result_section.text)

        def bad_writer(payload):
            return {
                "introduction": ("编造引用 [FAKE-SPAN-99] 与数字 9999。" * 4),
                "related_work": ("编造数字 8888 的段落。" * 4),
            }

        fallback = PaperAgent(self.specs["paper"], section_writer=bad_writer).run(PaperRequest(**base))
        self.assertEqual(fallback.writer_mode, "model_rejected")
        self.assertTrue(any("rejected" in warning for warning in fallback.warnings))
        introduction = next(item for item in fallback.draft if item.section == "引言")
        self.assertNotIn("9999", introduction.text)

    def test_grant_has_no_scientific_content_or_numbers(self):
        grant = GrantAgent(self.specs["grant"]).run(GrantRequest("topic", "nsfc", ["S-1"]))
        self.assertEqual(grant.status, "draft_needs_human")
        self.assertIn("立项依据", grant.modules)
        self.assertTrue(any("AI" in item or "科学观点" in item for item in grant.compliance))

    def test_input_validation_rejects_zero_budgets_and_bad_style(self):
        from research_agent.modules.literature import LiteratureAgent, LiteratureError, LiteratureRequest
        from research_agent.modules.idea import IdeaError, IdeaAgent, IdeaRequest
        from research_agent.modules.figure import FigureError
        from research_agent.adapters import FixtureRetriever, SimpleParser
        from research_agent.contracts import FigureNode
        from research_agent.modules.figure import FigureRequest
        lit = LiteratureAgent(self.specs["literature"], FixtureRetriever(), SimpleParser())
        with self.assertRaises(LiteratureError):
            lit.run(LiteratureRequest("q", max_sources=0))
        with self.assertRaises(IdeaError):
            IdeaAgent(self.specs["idea"]).run(IdeaRequest("q", [], max_candidates=0))
        with self.assertRaises(FigureError):
            FigureAgent(self.specs["figure"]).run(
                FigureRequest("x", "d", [FigureNode("a", "a", "paper", 0)], [], style="unknown")
            )

    def test_missing_schematic_renderer_degrades_to_scene_only(self):
        # the schematic is advisory output: a release copy without the vendored renderer
        # must still produce a scene, and must say out loud that there is no picture
        from unittest import mock

        from research_agent.adapters import astradraw_renderer
        from research_agent.modules.figure import FigureRequest

        with mock.patch.object(astradraw_renderer, "_RENDERER", None), mock.patch.object(
            astradraw_renderer, "_RENDERER_PATH", Path("Z:/absent/build_components.py")
        ):
            artifact = FigureAgent(self.specs["figure"]).run(
                FigureRequest(
                    "降级示意图", "只应有 scene",
                    [FigureNode("lit", "文献", "literature", 0)], [], run_id="FIG-DEGRADE",
                )
            )
        self.assertEqual(artifact.svg, "")
        self.assertIs(artifact.manifest["renderer_available"], False)
        self.assertEqual(artifact.manifest["svg_sha256"], "")
        self.assertTrue(artifact.scene, "the scene contract must survive")
        self.assertIn("astradraw_renderer_missing", artifact.audit["errors"])

    def test_figure_renders_auditable_svg(self):
        nodes = [
            FigureNode("lit", "文献", "literature", 0),
            FigureNode("fig", "图表", "figure", 1),
            FigureNode("paper", "论文", "paper", 2),
        ]
        edges = [FigureEdge("lit", "fig"), FigureEdge("fig", "paper")]
        artifact = FigureAgent(self.specs["figure"]).run(
            FigureRequest("测试图", "结构示意", nodes, edges, run_id="FIG-TEST")
        )
        self.assertEqual(artifact.figure_id, "FIG-TEST")
        self.assertTrue(artifact.audit["ok"])
        self.assertIn('role="img"', artifact.svg)
        self.assertIn('id="fig-title"', artifact.svg)
        self.assertIn('id="fig-desc"', artifact.svg)
        self.assertNotIn("<script", artifact.svg)
        self.assertEqual(artifact.manifest["schematic"], True)
        self.assertEqual(len(artifact.manifest["svg_sha256"]), 64)

    def test_svg_audit_rejects_script_and_external_reference(self):
        bad = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10"><script>x</script><image href="https://evil.test/a.png"/></svg>'
        report = audit_svg(bad)
        self.assertFalse(report["ok"])
        self.assertTrue(any("script" in error for error in report["errors"]))
        self.assertTrue(any("external" in error for error in report["errors"]))

    def test_svg_audit_rejects_doctype_and_bad_aria_targets(self):
        bad = '<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10"><title id="fig-title">t</title><desc id="fig-desc">d</desc></svg>'
        self.assertFalse(audit_svg(bad)["ok"])
        bad_aria = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10" role="img" aria-labelledby="missing"><title id="fig-title">t</title><desc id="fig-desc">d</desc></svg>'
        report = audit_svg(bad_aria)
        self.assertFalse(report["ok"])
        self.assertTrue(any("aria-labelledby" in error for error in report["errors"]))

    def test_real_text_pipeline_uses_ccby_spans_without_claims(self):
        root = Path(__file__).resolve().parents[1]
        runner = PipelineRunner(
            self.store,
            retriever=RealCorpusRetriever(root / "modules" / "literature" / "fixtures" / "real_corpus.json"),
            parser=SimpleParser(max_spans_per_source=2000),
            source_scope=["real"],
        )
        result = runner.run(
            PipelineRequest(
                topic="How do self-improving coding agents use archives and judge signals?",
                language="en",
                venue_type="en_conference",
                run_id="PIPE-REAL-TEST",
            )
        )
        literature = result.modules["literature"]
        self.assertFalse(result.fixture_mode)
        self.assertFalse(literature["fixture_mode"])
        self.assertGreater(len(literature["spans"]), 100)
        self.assertTrue(all(span["fixture"] is False for span in literature["spans"]))
        self.assertTrue(all(hit["fixture"] is False for hit in literature["hits"]))
        self.assertEqual(result.modules["paper"]["claims"], [])
        self.assertTrue(any("real-text pipeline" in warning for warning in result.warnings))
        # L0: the runner must actually hand the S1/S1b receipts to S2.
        self.assertTrue(
            any("synthesis_breadth=gap_pack:provided" in warning for warning in result.warnings)
        )
        self.assertTrue(
            any(
                card["gap_ref"] != "none"
                for card in result.modules["idea"]["candidates"]
            )
        )

    def test_pipeline_accepts_a_module_override_without_editing_the_pipeline(self):
        class InjectedIdeaAgent(IdeaAgent):
            def run(self, request):
                result = super().run(request)
                if result.candidates:
                    result.candidates[0].title = "INJECTED idea implementation"
                return result

        runner = PipelineRunner(
            self.store,
            module_overrides={"idea": InjectedIdeaAgent(self.specs["idea"])},
        )
        result = runner.run(
            PipelineRequest(
                topic="钙钛矿 界面 钝化 稳定性",
                language="zh",
                venue_type="zh_core_journal",
                run_id="PIPE-PLUGIN-TEST",
            )
        )
        self.assertEqual(
            result.modules["idea"]["candidates"][0]["title"],
            "INJECTED idea implementation",
        )

    def test_study_arm_executes_the_design_and_reports_its_three_states(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pipeline"
            result = PipelineRunner(self.store, run_output_dir=out / "run").run(
                PipelineRequest(
                    topic="Does retaining accepted configurations improve search efficiency?",
                    language="en",
                    venue_type="en_conference",
                    run_id="PIPE-STUDY-TEST",
                    study_dataset="iris",
                    study_seeds=4,
                    study_budget=12,
                )
            )
            study = result.study or {}
            self.assertEqual(study.get("status"), "executed")
            self.assertEqual(study.get("dataset"), "iris")
            self.assertEqual(len(study.get("seeds") or []), 4)
            directory = Path(study["study_dir"])
            self.assertTrue((directory / "study-evidence.json").is_file())
            origin = json.loads((directory / "study-origin.json").read_text(encoding="utf-8"))
            self.assertEqual(origin["source"], "pipeline_design")
            self.assertEqual(origin["resolved_controls"]["dataset"], "iris")
            # the executed study must carry the refuting condition of the idea it tests; with no
            # idea selected there is no condition to carry, and the origin says so explicitly
            if origin["idea_id"] == "PIPELINE":
                self.assertEqual(origin["falsification"], "")
            else:
                self.assertTrue(origin["falsification"], origin)
            # Every comparison is labelled, including the ones that decide nothing.
            self.assertEqual(len(study["comparison"]), 3)
            self.assertTrue(
                any("would need about" in item for item in result.warnings),
                [item for item in result.warnings if "undecidable" in item],
            )
            # the executed design must not be mistaken for the still-incomplete S4 draft
            self.assertTrue(
                any("not the S4 draft" in item for item in result.warnings),
                result.warnings,
            )
            report = render_report_markdown(result)
            self.assertIn("搜索研究臂", report)
            self.assertIn("dataset=iris", report)
            self.assertEqual(len(study["comparison"]), 3)

    def test_study_arm_refuses_a_dataset_it_cannot_run(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pipeline"
            with self.assertRaises(PipelineError) as caught:
                PipelineRunner(self.store, run_output_dir=out / "run").run(
                    PipelineRequest(
                        topic="search efficiency",
                        language="en",
                        venue_type="en_conference",
                        run_id="PIPE-STUDY-BAD",
                        study_dataset="chemlab",
                        study_seeds=4,
                        study_budget=12,
                    )
                )
        message = str(caught.exception)
        self.assertIn("study arm refused", message)
        self.assertIn("chemlab", message)

    def test_pipeline_writes_readable_paper_and_report(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = PipelineRunner(self.store).run(
                PipelineRequest(
                    topic="钙钛矿 界面 钝化 稳定性",
                    language="zh",
                    venue_type="zh_core_journal",
                    run_id="PIPE-REPORT-TEST",
                )
            )
            paths = write_pipeline_artifacts(result, Path(tmp))
            self.assertTrue(Path(paths["paper_markdown"]).is_file())
            self.assertTrue(Path(paths["literature_ledger"]).is_file())
            self.assertTrue(Path(paths["design_audit"]).is_file())
            self.assertTrue(Path(paths["manuscript_markdown"]).is_file())
            self.assertTrue(Path(paths["manuscript_audit"]).is_file())
            self.assertTrue(Path(paths["claim_registry"]).is_file())
            self.assertTrue(Path(paths["argument_ledger"]).is_file())
            self.assertTrue(Path(paths["report_markdown"]).is_file())
            self.assertTrue(Path(paths["evidence_packages"]).is_file())
            self.assertTrue(Path(paths["loop_capsule"]).is_file())
            loop_capsule = json.loads(Path(paths["loop_capsule"]).read_text(encoding="utf-8"))
            loop_nodes = {item["id"]: item for item in loop_capsule["nodes"]}
            self.assertEqual(loop_nodes["S2-S3"]["status"], "needs_human")
            self.assertEqual(loop_nodes["S4"]["status"], "needs_human")
            self.assertIn("G1_IDEA_SELECTION_REQUIRED", loop_capsule["blockers"])
            self.assertIn("G2_PROTOCOL_FREEZE_REQUIRED", loop_capsule["blockers"])
            self.assertTrue(result.evidence_packages)
            self.assertIsNotNone(result.manuscript)
            demo = json.loads(Path(paths["demo"]).read_text(encoding="utf-8"))
            self.assertEqual(
                [item["id"] for item in demo["evidence_packages"]],
                [item["id"] for item in result.evidence_packages],
            )
            self.assertEqual(demo["manuscript_uri"], "manuscript.md")
            self.assertEqual(demo["literature_ledger_uri"], "literature-ledger.json")
            self.assertEqual(demo["design_audit_uri"], "design-audit.json")
            self.assertEqual(demo["claim_registry_uri"], "claim-registry.json")
            report = Path(paths["report_markdown"]).read_text(encoding="utf-8")
            paper = Path(paths["paper_markdown"]).read_text(encoding="utf-8")
            manuscript = Path(paths["manuscript_markdown"]).read_text(encoding="utf-8")
            audit = json.loads(Path(paths["manuscript_audit"]).read_text(encoding="utf-8"))
            self.assertIn("科研任务运行报告", report)
            self.assertIn("结论边界", report)
            self.assertIn("中文投稿工作稿", report)
            self.assertIn("槽位状态", paper)
            self.assertIn("## 参考文献", manuscript)
            self.assertFalse(audit["submission_ready"])
            self.assertTrue(any("fixture" in item for item in audit["blockers"]))
            self.assertTrue(result.modules["paper"]["draft"])
            self.assertEqual(result.modules["paper"]["writer_mode"], "deterministic")

    def test_pipeline_with_s5_run_creates_claim_draft(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = PipelineRunner(self.store, run_output_dir=Path(tmp) / "run").run(
                PipelineRequest(
                    topic="Iris protocol validation",
                    language="en",
                    venue_type="en_conference",
                    run_dataset="iris",
                    run_seeds=3,
                    run_id="PIPE-S5-TEST",
                )
            )
            self.assertEqual(result.modules["run"]["capsule"]["status"], "completed")
            self.assertEqual(result.modules["run"]["capsule"]["seeds"], [17, 18, 19])
            self.assertTrue(Path(result.modules["run"]["claim_draft"]).is_file())
            self.assertIsNotNone(result.idea_review)
            self.assertIsNotNone(result.design_audit)
            self.assertIsNotNone(result.run_contract)
            self.assertEqual(result.run_contract_check["status"], "attention")
            self.assertEqual(result.run_contract_check["blockers"], [])
            fig = result.modules["run"]["result_figure"]
            self.assertFalse(fig["manifest"]["schematic"])
            self.assertTrue(Path(fig["paths"]["svg"]).is_file())
            result_figure_slot = next(slot for slot in result.modules["paper"]["slots"] if slot["slot_id"] == "result.figure")
            self.assertEqual(result_figure_slot["status"], "bound_figure")
            design = result.modules["experiment"]
            self.assertEqual(design["baseline"], "majority class")
            self.assertEqual(design["primary_metric"], "accuracy")
            self.assertEqual(design["controls"], ["majority baseline"])
            self.assertEqual(design["status"], "ready_for_g2")
            primary = next(slot for slot in result.modules["paper"]["slots"] if slot["slot_id"] == "result.primary")
            self.assertEqual(primary["status"], "pending_evidence")
            g2 = next(gate for gate in result.gates if gate["gate"] == "G2")
            self.assertEqual(g2["status"], "needs_human")
            self.assertIn("human-frozen ProtocolCard", g2["reason"])
            self.assertEqual(result.modules["paper"]["claims"], [])
            packages = {item["id"]: item for item in result.evidence_packages}
            self.assertEqual(packages["run"]["status"], "ready")
            self.assertEqual(packages["ea"]["status"], "ready")
            self.assertEqual(packages["claim"]["status"], "needs_signature")
            self.assertEqual(packages["paper"]["status"], "needs_human")
            self.assertTrue(any("claim draft" in warning for warning in result.warnings))
            self.assertTrue(any("separate evidence arm" in warning for warning in result.warnings))
            self.assertFalse(any("no experiment" in warning for warning in result.warnings))
            self.assertIn("run", result.spec_versions)
            chem = PipelineRunner(self.store, run_output_dir=Path(tmp) / "chem-run").run(
                PipelineRequest(
                    topic="ChemLab reaction conversion baseline",
                    language="en",
                    venue_type="en_conference",
                    run_dataset="chemlab",
                    run_seeds=2,
                    run_id="PIPE-CHEM-TEST",
                )
            )
            design = chem.modules["experiment"]
            self.assertEqual(design["baseline"], "mean predictor (DummyRegressor)")
            self.assertEqual(design["primary_metric"], "delta_r2")
            self.assertEqual(design["controls"], ["mean baseline"])
            self.assertEqual(design["status"], "ready_for_g2")
            draft = json.loads(Path(chem.modules["run"]["claim_draft"]).read_text(encoding="utf-8"))
            self.assertIn("mean baseline", draft["statement"])
            self.assertEqual(draft["status"], "draft_needs_human")
            claim = RunAgent(self.store.load("run")).claim(
                Path(chem.modules["run"]["paths"]["capsule"]),
                Path(chem.modules["run"]["paths"]["ea"]),
                draft["statement"], "test signature",
                "S5/demo/chemlab", Path(tmp) / "chem-claim",
            )
            protocol = ExperimentDesignAgent(self.store.load("experiment")).freeze(
                chem.modules["experiment"],
                Path(chem.modules["run"]["paths"]["capsule"]),
                "single public dataset; baseline only",
                "test G2 signature",
                Path(tmp) / "protocol",
            )
            reused = PipelineRunner(self.store, run_output_dir=Path(tmp) / "reuse-run").run(
                PipelineRequest(
                    topic="ChemLab reaction conversion baseline",
                    language="en", venue_type="en_conference",
                    claim_refs=[claim["claim"]["claim_id"]],
                    run_dir=str(Path(chem.modules["run"]["paths"]["capsule"]).parent),
                    run_dataset="chemlab",
                    protocol_file=protocol["path"],
                    run_seeds=2,
                    run_id="PIPE-CHEM-BOUND",
                )
            )
            self.assertEqual(
                reused.modules["run"]["evidence"]["artifact_id"],
                chem.modules["run"]["evidence"]["artifact_id"],
            )
            primary = next(slot for slot in reused.modules["paper"]["slots"] if slot["slot_id"] == "result.primary")
            self.assertEqual(primary["status"], "bound_claim")
            method = next(slot for slot in reused.modules["paper"]["slots"] if slot["slot_id"] == "method.protocol")
            limitation = next(slot for slot in reused.modules["paper"]["slots"] if slot["slot_id"] == "limitation")
            self.assertEqual(method["status"], "bound_protocol")
            self.assertEqual(limitation["status"], "bound_scope")
            self.assertEqual(reused.modules["protocol"]["status"], "frozen")

    def test_pipeline_composes_modules_without_claims(self):
        result = PipelineRunner(self.store).run(
            PipelineRequest(
                topic="钙钛矿 界面 钝化 稳定性",
                language="zh",
                venue_type="zh_core_journal",
                grant_scheme="nsfc",
                primary_metric="湿热稳定性",
                budget="待定",
                controls=["未钝化对照"],
                run_id="PIPE-TEST",
            )
        )
        self.assertEqual(result.run_id, "PIPE-TEST")
        self.assertTrue(result.fixture_mode)
        self.assertEqual(
            set(result.modules),
            {"literature", "idea", "experiment", "figure", "paper", "grant", "q0", "synthesis"},
        )
        self.assertTrue(result.modules["synthesis"]["themes"])
        self.assertTrue(
            all(theme["source_count"] >= 2 for theme in result.modules["synthesis"]["themes"])
        )
        self.assertEqual(result.modules["figure"]["audit"]["ok"], True)
        self.assertEqual(result.modules["paper"]["claims"], [])
        self.assertTrue(any(gate["gate"] == "G5" and gate["status"] == "blocked" for gate in result.gates))
        self.assertEqual(result.status, "needs_human")



class G1ResumeTest(unittest.TestCase):
    """A human G1 decision must survive into a later run, and the artifact must stop asking."""

    @classmethod
    def setUpClass(cls):
        cls.store = SpecStore()

    def _idea_file(self, root: Path) -> Path:
        payload = {
            "run_id": "PIPE-G1-FIXTURE-idea",
            "module": "idea",
            "spec_version": "0.1.0",
            "status": "candidates_need_human",
            "candidates": [
                {
                    "idea_id": "IDEA-01",
                    "title": "Archive value depends on how parents are drawn",
                    "hypothesis": "Retention helps only when the next parent is sampled broadly.",
                    "falsification": "If greedy and broad cells agree on every dataset, the claim fails.",
                    "evidence_refs": ["FX-001-S01-01"],
                    "status": "candidate",
                    "lens": "mechanism",
                }
            ],
            "warnings": [],
            "brief": None,
        }
        path = root / "idea-fixture.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _run(self, out: Path, **kwargs):
        result = PipelineRunner(self.store).run(
            PipelineRequest(
                topic="Does retaining accepted configurations improve search efficiency?",
                language="en",
                venue_type="en_conference",
                run_id="PIPE-G1-" + out.name.upper(),
                **kwargs
            )
        )
        write_pipeline_artifacts(result, out)
        return result

    def test_selected_idea_is_recorded_and_g1_is_not_asked_twice(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decision = root / "g1-decision.json"
            decision.write_text(
                json.dumps(
                    {
                        "status": "approved",
                        "selected_idea_id": "IDEA-01",
                        "human_reason": "test: reviewed the candidates",
                    }
                ),
                encoding="utf-8",
            )
            self._run(
                root / "run",
                idea_file=str(self._idea_file(root)),
                g1_decision_file=str(decision),
            )
            record = json.loads((root / "run" / "idea.json").read_text(encoding="utf-8"))
            self.assertEqual(record["status"], "selected", record["status"])
            selected = [c["idea_id"] for c in record["candidates"] if c["status"] == "selected"]
            self.assertEqual(selected, ["IDEA-01"])
            capsule = json.loads(
                (root / "run" / "loop-capsule.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("G1_IDEA_SELECTION_REQUIRED", capsule["blockers"])


class AssertionProposalTest(unittest.TestCase):
    """The draft may propose a number; only a human can turn it into an assertion."""

    def _capsule(self, values, metric="accuracy"):
        return {
            "metric_name": metric,
            "seeds": list(range(1, len(values) + 1)),
            "metrics_by_seed": [
                {"seed": index + 1, metric: value} for index, value in enumerate(values)
            ],
        }

    def test_proposal_uses_the_worst_seed_and_stays_a_draft(self):
        from research_agent.pipeline import _assertion_proposal

        proposal = _assertion_proposal(self._capsule([0.9111, 0.9556, 1.0]), "iris")
        self.assertEqual(proposal["status"], "proposed_for_human")
        self.assertEqual(proposal["value"], 0.9111)
        self.assertEqual(proposal["metric"], "accuracy")
        self.assertEqual(proposal["basis"]["max"], 1.0)
        self.assertIn("value=0.9111", proposal["assertion_argument"])
        self.assertIn("not a claim", proposal["boundary"])

    def test_missing_values_say_unavailable_instead_of_guessing(self):
        from research_agent.pipeline import _assertion_proposal

        proposal = _assertion_proposal(
            {"metric_name": "accuracy", "metrics_by_seed": []}, "iris"
        )
        self.assertEqual(proposal["status"], "unavailable")
        self.assertNotIn("value", proposal)


class ResumeInputsTest(unittest.TestCase):
    """Resuming must carry every input forward, or the continued run reports a worse audit."""

    def test_a_verified_bibliography_card_is_picked_up_from_the_run_dir(self):
        import tempfile

        from research_agent.cli import _resume_pipeline_inputs

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            card = {
                "status": "verified_datacite_snapshot",
                "entry_count": 2,
                "entries": [{"title": "A"}, {"title": "B"}],
            }
            (run_dir / "bibliography.json").write_text(json.dumps(card), encoding="utf-8")
            found = _resume_pipeline_inputs(run_dir)
            self.assertEqual(found.get("bibliography_file"), str(run_dir / "bibliography.json"))

    def test_a_missing_card_is_not_invented(self):
        import tempfile

        from research_agent.cli import _resume_pipeline_inputs

        with tempfile.TemporaryDirectory() as tmp:
            self.assertNotIn("bibliography_file", _resume_pipeline_inputs(Path(tmp)))

class RunEventIntegrationTest(unittest.TestCase):
    def test_a_real_run_writes_a_verifiable_chain_and_refuses_the_boundary(self):
        import tempfile

        from research_agent.run_events import (
            REJECTED_KIND,
            read_events,
            replay_boundaries,
            verify_events,
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = PipelineRunner(SpecStore()).run(
                PipelineRequest(
                    topic="钙钛矿 界面 钝化 稳定性",
                    language="zh",
                    run_id="PIPE-EVENT-TEST",
                )
            )
            self.assertTrue(result.events)
            self.assertTrue(verify_events(result.events)["ok"])
            paths = write_pipeline_artifacts(result, Path(tmp))
            self.assertTrue(paths.get("events"), "events.ndjson was not written")
            rows = read_events(Path(paths["events"]))
            self.assertEqual(len(rows), len(result.events))
            self.assertTrue(verify_events(rows)["ok"])
            # A default fixture run always has human gates pending: no boundary
            # may be committed, and the refusal must be visible in the log.
            replay = replay_boundaries(rows)
            self.assertEqual(replay["boundaries"], [])
            self.assertTrue(any(row.get("kind") == REJECTED_KIND for row in rows))
            gates = {gate["gate"]: gate["status"] for gate in result.gates}
            self.assertEqual(gates.get("G3"), "blocked")
            self.assertEqual(gates.get("G5"), "blocked")
            demo = json.loads(Path(paths["demo"]).read_text(encoding="utf-8"))
            self.assertEqual(demo["gates"], result.gates)

    def test_writing_artifacts_twice_does_not_splice_two_chains(self):
        import tempfile

        from research_agent.run_events import read_events, verify_events

        with tempfile.TemporaryDirectory() as tmp:
            result = PipelineRunner(SpecStore()).run(
                PipelineRequest(topic="fixture topic", language="zh", run_id="PIPE-EVENT-TWICE")
            )
            first = write_pipeline_artifacts(result, Path(tmp))
            second = write_pipeline_artifacts(result, Path(tmp))
            self.assertEqual(first["events"], second["events"])
            rows = read_events(Path(first["events"]))
            self.assertTrue(verify_events(rows)["ok"])
            self.assertEqual(len(rows), len(result.events))


if __name__ == "__main__":
    unittest.main()
