import json
import tempfile
import unittest
from pathlib import Path

from research_agent.adapters.support_judge import support_judge_from_model
from research_agent.models import ModelRequiredError
from research_agent.postprocess import run_claim_postprocess
from research_agent.writing_audit import audit_manuscript
from research_agent.writing_pack import build_writing_pack
from tests.writing_support import RUN_ID, make_writing_project, write_draft
from research_agent.support_audit import SupportAuditError, audit_pack_support, audit_support


class SupportAuditTest(unittest.TestCase):
    def _paper(self):
        return {
            "title": "fixture paper",
            "draft": [{
                "section": "Results",
                "text": "Passivation improves stability under damp heat. The control is unchanged.",
                "evidence_refs": ["S-1"],
            }],
        }

    def _spans(self):
        return [{
            "span_id": "S-1",
            "source_id": "FX-1",
            "section": "Results",
            "text": "Passivation improves stability under damp heat in the paired control.",
        }]

    def test_heuristic_is_labelled_and_never_claims_supported(self):
        report = audit_support(self._paper(), self._spans())
        self.assertEqual(report["method"], "lexical_overlap_heuristic")
        self.assertEqual(report["status"], "partial")
        self.assertGreaterEqual(len(report["items"]), 1)
        self.assertEqual(report["counts"]["supported"], 0)
        self.assertTrue(all(
            item["status"] in ("partial", "insufficient")
            for item in report["items"]
        ))
        self.assertIn("heuristic", report["warnings"][0])

    def test_explicit_citation_limits_evidence_to_the_cited_span(self):
        paper = {
            "title": "citation test",
            "draft": [{
                "section": "Related Work",
                "text": "The passivation group reached 780 h under damp heat [S-1].",
                "evidence_refs": ["S-1", "S-2"],
            }],
        }
        spans = [
            {"span_id": "S-1", "source_id": "FX-1", "text": "Passivation reached 780 h under damp heat."},
            {"span_id": "S-2", "source_id": "FX-2", "text": "A different control reached 420 h."},
        ]
        report = audit_support(paper, spans)
        self.assertEqual(report["items"][0]["citation_mode"], "explicit_span")
        self.assertEqual(report["items"][0]["evidence_refs"], ["S-1"])
        self.assertEqual(report["citation_modes"], {"explicit_span": 1})

    def test_model_judge_verdicts_are_validated(self):
        def judge(payload):
            first = payload["items"][0]
            return [{
                "id": first["id"],
                "status": "contradicted",
                "rationale": "evidence says the opposite",
                "evidence_refs": ["S-1"],
            }, {
                "id": "UNKNOWN",
                "status": "supported",
                "rationale": "must be rejected",
                "evidence_refs": ["S-404"],
            }]

        report = audit_support(self._paper(), self._spans(), judge=judge)
        self.assertEqual(report["method"], "model_judge")
        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["counts"]["contradicted"], 1)
        self.assertEqual(len(report["items"]), 1)
        self.assertEqual(report["items"][0]["evidence_refs"], ["S-1"])

    def test_deterministic_precheck_blocks_numbers_missing_from_cited_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = root / "draft.md"
            draft.write_text(
                "# 结果\n\n## 结果\n\n钝化组 T80 为 0.93 [REF-01]。\n",
                encoding="utf-8",
            )
            report = audit_pack_support(draft, pack)
            self.assertEqual(report["precheck_failed"], 1, report)
            item = report["items"][0]
            self.assertEqual(item["status"], "insufficient")
            self.assertEqual(item["method"], "deterministic_evidence_precheck")
            self.assertIn("0.93", item["precheck_missing"])
            self.assertTrue(
                any("not found in cited span" in str(entry.get("rationale") or "")
                    for entry in report["items"])
            )

    def test_strict_requires_a_judge(self):
        with self.assertRaises(ModelRequiredError):
            audit_support(self._paper(), self._spans(), strict=True)

    def test_adapter_parses_verdicts_and_strict_failure(self):
        class FakeModel:
            def complete(self, messages, json_mode=True):
                return json.dumps({"verdicts": [{"id": "SUP-01", "status": "supported"}]})

        parsed = support_judge_from_model(FakeModel())({"items": []})
        self.assertEqual(parsed, [{"id": "SUP-01", "status": "supported"}])

        class BadModel:
            def complete(self, messages, json_mode=True):
                return "not json"

        self.assertIsNone(support_judge_from_model(BadModel())({"items": []}))
        with self.assertRaises(ModelRequiredError):
            support_judge_from_model(BadModel(), strict=True)({"items": []})

    def test_strict_postprocess_blocks_contradicted_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            demo_path = root / "demo.json"
            claim_path = root / "claim.json"
            demo_path.write_text(json.dumps({
                "modules": {
                    "paper": self._paper(),
                    "literature": {"spans": self._spans()},
                },
            }), encoding="utf-8")
            claim_path.write_text(json.dumps({
                "claim_id": "CLM-1",
                "statement": "Passivation improves stability.",
                "status": "supported",
                "evidence_refs": ["EA-1"],
            }), encoding="utf-8")

            def judge(payload):
                return [{
                    "id": item["id"],
                    "status": "contradicted",
                    "rationale": "evidence contradicts the sentence",
                    "evidence_refs": [item["evidence"][0]["ref"]],
                } for item in payload["items"]]

            with self.assertRaises(SupportAuditError):
                run_claim_postprocess(
                    demo_path,
                    claim_path,
                    root / "out",
                    support_judge=judge,
                    strict_support=True,
                )
            self.assertTrue((root / "out" / "support-audit.json").is_file())

    def test_support_judge_majority_vote_reduces_single_call_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。")
            calls = {"count": 0}

            def judge(payload):
                statuses = ["supported", "insufficient", "supported"]
                status = statuses[calls["count"] % len(statuses)]
                calls["count"] += 1
                return [
                    {
                        "id": item["id"],
                        "status": status,
                        "rationale": "vote %s" % status,
                        "evidence_refs": [item["evidence"][0]["ref"]],
                    }
                    for item in payload["items"]
                ]

            report = audit_pack_support(
                draft, pack, judge=judge, judge_votes=3, strict=True
            )
            self.assertEqual(report["method"], "model_judge_majority")
            self.assertEqual(report["judge_votes"], 3)
            self.assertEqual(report["status"], "ready")
            self.assertGreaterEqual(report["counts"]["supported"], 6)
            self.assertEqual(report["counts"]["insufficient"], 0)
            self.assertIn("votes", report["items"][0])

    def test_section_summary_prioritizes_weak_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="结果表明所提框架优于基线 [REF-01]。")

            def judge(payload):
                return [
                    {
                        "id": item["id"],
                        "status": "partial" if item["section"] == "结果" else "supported",
                        "rationale": "checked",
                        "evidence_refs": [item["evidence"][0]["ref"]],
                    }
                    for item in payload["items"]
                ]

            report = audit_pack_support(draft, pack, judge=judge)
            weak = report["section_summary"]["weak_sections"]
            self.assertTrue(weak)
            self.assertEqual(weak[0]["section"], "结果")
            self.assertGreater(weak[0]["weak"], 0)

    def test_support_judge_batches_long_manuscripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。")
            batch_sizes = []

            def judge(payload):
                batch_sizes.append(len(payload["items"]))
                return [
                    {
                        "id": item["id"],
                        "status": "supported",
                        "rationale": "checked",
                        "evidence_refs": [item["evidence"][0]["ref"]],
                    }
                    for item in payload["items"]
                ]

            report = audit_pack_support(
                draft,
                pack,
                judge=judge,
                judge_batch_size=2,
                max_items=10,
                strict=True,
            )
            self.assertGreaterEqual(len(batch_sizes), 2)
            self.assertTrue(all(size <= 2 for size in batch_sizes))
            self.assertEqual(report["judge_batch_size"], 2)
            self.assertEqual(report["status"], "ready")

    def test_support_ledger_reports_truncation_and_strict_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。")

            def judge(payload):
                return [
                    {
                        "id": item["id"],
                        "status": "supported",
                        "rationale": "checked",
                        "evidence_refs": [item["evidence"][0]["ref"]],
                    }
                    for item in payload["items"]
                ]

            partial = audit_pack_support(
                draft, pack, judge=judge, max_items=2, strict=False
            )
            self.assertTrue(partial["truncated"])
            self.assertEqual(partial["audited_cited_sentences"], 2)
            self.assertGreater(partial["total_cited_sentences"], 2)
            self.assertEqual(partial["status"], "partial")
            self.assertTrue(any("truncated" in item for item in partial["warnings"]))

            strict = audit_pack_support(
                draft, pack, judge=judge, max_items=2, strict=True
            )
            self.assertTrue(strict["truncated"])
            self.assertEqual(strict["status"], "blocked")

    def test_support_ledger_cache_reuses_verdicts_for_same_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。")
            cache = root / "support-ledger.json"
            calls = {"count": 0}

            def judge(payload):
                calls["count"] += 1
                status = "supported" if calls["count"] == 1 else "insufficient"
                return [
                    {
                        "id": item["id"],
                        "status": status,
                        "rationale": "call %d" % calls["count"],
                        "evidence_refs": [item["evidence"][0]["ref"]],
                    }
                    for item in payload["items"]
                ]

            first = audit_pack_support(
                draft, pack, judge=judge, cache_path=cache, judge_votes=1
            )
            self.assertFalse(first["cached"])
            self.assertEqual(first["status"], "ready")
            self.assertEqual(calls["count"], 1)

            second = audit_pack_support(
                draft, pack, judge=judge, cache_path=cache, judge_votes=1
            )
            self.assertTrue(second["cached"])
            self.assertEqual(second["status"], "ready")
            self.assertEqual(calls["count"], 1)

            refreshed = audit_pack_support(
                draft,
                pack,
                judge=judge,
                cache_path=cache,
                judge_votes=1,
                refresh=True,
            )
            self.assertFalse(refreshed["cached"])
            self.assertNotEqual(refreshed["status"], "ready")
            self.assertEqual(calls["count"], 2)

    def test_support_cache_dir_keys_by_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。")
            cache_dir = root / "support-cache"
            calls = {"count": 0}

            def judge(payload):
                calls["count"] += 1
                return [
                    {
                        "id": item["id"],
                        "status": "supported",
                        "rationale": "cache test",
                        "evidence_refs": [item["evidence"][0]["ref"]],
                    }
                    for item in payload["items"]
                ]

            first = audit_pack_support(
                draft, pack, judge=judge, cache_dir=cache_dir
            )
            second = audit_pack_support(
                draft, pack, judge=judge, cache_dir=cache_dir
            )
            self.assertFalse(first["cached"])
            self.assertTrue(second["cached"])
            self.assertEqual(calls["count"], 1)
            self.assertTrue(any(cache_dir.glob("*.json")))

    def test_pack_support_resolves_refs_to_selected_spans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。")

            def judge(payload):
                return [
                    {
                        "id": item["id"],
                        "status": "supported",
                        "rationale": "span supports the sentence",
                        "evidence_refs": [item["evidence"][0]["ref"]],
                    }
                    for item in payload["items"]
                ]

            report = audit_pack_support(
                draft, pack, judge=judge, strict=True, judge_model_id="fake"
            )
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["method"], "model_judge")
            self.assertEqual(report["unresolved_refs"], 0)
            self.assertEqual(report["items"][0]["refs"], ["REF-01"])
            self.assertTrue(report["items"][0]["evidence_refs"])
            self.assertEqual(report["items"][0]["evidence_refs"][0], "S1-S01-01")

    def test_proposal_sentences_do_not_require_evidence_entailment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = root / "proposal.md"
            draft.write_text(
                "# 计划\n\n## 讨论\n\n我们计划在后续实验中验证该机制 [REF-01]。\n",
                encoding="utf-8",
            )

            def judge(payload):
                return [
                    {
                        "id": item["id"],
                        "status": "insufficient",
                        "rationale": "should not be called for proposals",
                        "evidence_refs": [],
                    }
                    for item in payload["items"]
                ]

            report = audit_pack_support(draft, pack, judge=judge, strict=True)
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["counts"]["not_required"], 1)
            self.assertEqual(report["counts"]["insufficient"], 0)
            self.assertEqual(report["unresolved_refs"], 0)

    def test_method_section_protocols_are_not_factual_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = root / "method.md"
            draft.write_text(
                "# 方法\n\n## 方法\n\n本文的审计协议包含三个步骤：核查来源、标注支持强度、记录缺口 [REF-01]。\n",
                encoding="utf-8",
            )

            def judge(payload):
                return [
                    {
                        "id": item["id"],
                        "status": "insufficient",
                        "rationale": "protocol sentence",
                        "evidence_refs": [],
                    }
                    for item in payload["items"]
                ]

            report = audit_pack_support(draft, pack, judge=judge, strict=True)
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["counts"]["not_required"], 1)

    def test_reference_list_is_not_support_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = root / "refs.md"
            draft.write_text(
                "# 文\n\n## 参考文献\n\n1. [REF-01] Learning curves. arXiv.\n",
                encoding="utf-8",
            )
            report = audit_pack_support(draft, pack)
            self.assertEqual(report["status"], "not_applicable")
            self.assertEqual(report["items"], [])

    def test_pack_support_blocks_unresolved_citation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。", citation="[REF-99]")
            report = audit_pack_support(draft, pack)
            self.assertEqual(report["status"], "blocked")
            self.assertGreater(report["unresolved_refs"], 0)
            self.assertTrue(
                any(item["status"] == "insufficient" for item in report["items"])
            )

    def test_strict_pack_support_requires_a_judge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。")
            with self.assertRaises(ModelRequiredError):
                audit_pack_support(draft, pack, strict=True)

    def test_writing_audit_blocks_contradicted_support_when_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。")

            def contradicted(payload):
                return [
                    {
                        "id": item["id"],
                        "status": "contradicted",
                        "rationale": "evidence contradicts the sentence",
                        "evidence_refs": [item["evidence"][0]["ref"]],
                    }
                    for item in payload["items"]
                ]

            audit = audit_manuscript(
                draft,
                pack=pack,
                support_judge=contradicted,
                strict_support=True,
                judge_model_id="fake",
            )
            self.assertEqual(audit["status"], "blocked")
            self.assertIn("support", audit)
            self.assertTrue(
                any("semantic_support" in item for item in audit["blockers"])
            )

    def test_strict_support_allows_partial_but_blocks_insufficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。")

            def partial(payload):
                return [
                    {
                        "id": item["id"],
                        "status": "partial",
                        "rationale": "only part of the sentence is supported",
                        "evidence_refs": [item["evidence"][0]["ref"]],
                    }
                    for item in payload["items"]
                ]

            audit = audit_manuscript(
                draft, pack=pack, support_judge=partial, strict_support=True
            )
            self.assertEqual(audit["status"], "ready_for_human_review", audit["blockers"])
            self.assertEqual(audit["support"]["status"], "partial")

    def test_no_draft_evidence_is_not_applicable(self):
        paper = {"title": "empty", "draft": [{"section": "Abstract", "text": "short", "evidence_refs": []}]}
        report = audit_support(paper, self._spans())
        self.assertEqual(report["status"], "not_applicable")
        self.assertEqual(report["items"], [])


if __name__ == "__main__":
    unittest.main()
