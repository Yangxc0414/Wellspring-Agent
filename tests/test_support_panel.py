import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from research_agent.cli import main
from research_agent.project import ProjectError, run_dir
from research_agent.storage import write_json_atomic
from research_agent.support_panel import SupportPanelError, audit_support_panel
from research_agent.writing_pack import build_writing_pack, ensure_pack_marker
from tests.writing_support import RUN_ID, make_writing_project, write_draft

PACK_ID = "WP-abcdef123456"
PACK_SHA = "a" * 64
MARKER = "<!-- writing-pack: %s sha256=%s -->" % (PACK_ID, PACK_SHA)

DRAFT = """%s

# 引言

研究表明，该方法在湿热条件下保持稳定[REF-01]。 该结果支持大面积制备的可行性[REF-01]。

# 讨论

文献报告了类似的界面钝化效果[REF-01]。
""" % MARKER


def _pack():
    return {
        "pack_id": PACK_ID,
        "pack_sha256": PACK_SHA,
        "literature": {
            "references": [{"ref_id": "REF-01", "source_id": "SRC-01"}],
            "selected_spans": {
                "SRC-01": [
                    {"span_id": "SPAN-01", "text": "湿热条件下界面钝化可保持稳定"},
                    {"span_id": "SPAN-02", "text": "大面积制备需要均匀钝化"},
                ]
            },
        },
        "evidence_map": {"REF-01": ["SPAN-01", "SPAN-02"]},
    }


def _judge(statuses):
    def judge(payload):
        return [
            {
                "id": item["id"],
                "status": statuses.get(item["id"], "supported"),
                "rationale": "test judgement",
            }
            for item in payload["items"]
        ]

    return judge


class SupportPanelTest(unittest.TestCase):
    def test_family_required_panel_needs_two_declared_families(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft = root / "draft.md"
            draft.write_text(DRAFT, encoding="utf-8")
            judges = [
                ("profile:a", _judge({})),
                ("profile:b", _judge({})),
            ]
            with self.assertRaises(SupportPanelError):
                audit_support_panel(
                    draft,
                    _pack(),
                    judges,
                    cache_dir=root / "cache",
                    judge_families={"profile:a": "openai"},
                    require_families=True,
                )
            with self.assertRaises(SupportPanelError):
                audit_support_panel(
                    draft,
                    _pack(),
                    judges,
                    cache_dir=root / "cache",
                    judge_families={
                        "profile:a": "openai",
                        "profile:b": "openai",
                    },
                    require_families=True,
                )
            result = audit_support_panel(
                draft,
                _pack(),
                judges,
                cache_dir=root / "cache",
                judge_families={
                    "profile:a": "openai",
                    "profile:b": "anthropic",
                },
                require_families=True,
            )
            self.assertEqual(result["family_requirement"], "required")
            self.assertEqual(result["independence"], "declared_two_family")
            self.assertEqual(
                {item["family"] for item in result["judges"]},
                {"openai", "anthropic"},
            )
            self.assertEqual(
                result["agreement"]["pairs"][0]["b_family"],
                "anthropic",
            )

    def test_provider_required_panel_needs_two_distinct_provider_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft = root / "draft.md"
            draft.write_text(DRAFT, encoding="utf-8")
            judges = [
                ("profile:a", _judge({})),
                ("profile:b", _judge({})),
            ]
            with self.assertRaises(SupportPanelError):
                audit_support_panel(
                    draft,
                    _pack(),
                    judges,
                    cache_dir=root / "cache-a",
                    judge_providers={"profile:a": "openai"},
                    require_providers=True,
                )
            with self.assertRaises(SupportPanelError):
                audit_support_panel(
                    draft,
                    _pack(),
                    judges,
                    cache_dir=root / "cache-b",
                    judge_providers={"profile:a": "openai", "profile:b": "openai"},
                    require_providers=True,
                )
            result = audit_support_panel(
                draft,
                _pack(),
                judges,
                cache_dir=root / "cache-c",
                judge_providers={"profile:a": "openai", "profile:b": "anthropic"},
                judge_models={"profile:a": "gpt-x", "profile:b": "claude-x"},
                require_providers=True,
            )
            self.assertEqual(result["provider_requirement"], "required")
            self.assertEqual(result["independence"], "distinct_providers")
            self.assertEqual(
                result["judge_providers"],
                {"profile:a": "openai", "profile:b": "anthropic"},
            )
            self.assertEqual(result["agreement"]["pairs"][0]["b_provider"], "anthropic")
            self.assertIn("do not prove", result["independence_note"])

    def test_disagreement_requires_human_and_adjudication_resolves_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft = root / "draft.md"
            draft.write_text(DRAFT, encoding="utf-8")
            adjudication = root / "adjudication.json"
            adjudication.write_text(
                json.dumps(
                    {
                        "schema_version": "support-adjudication-0.1",
                        "decisions": [
                            {
                                "id": "SUP-02",
                                "status": "supported",
                                "human_reason": "checked the source sentence manually",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = audit_support_panel(
                draft,
                _pack(),
                [
                    ("profile:a", _judge({"SUP-01": "supported", "SUP-02": "partial"})),
                    ("profile:b", _judge({"SUP-01": "supported", "SUP-02": "supported"})),
                ],
                cache_dir=root / "cache",
            )
            self.assertEqual(result["status"], "needs_human")
            self.assertEqual(result["pending_human"], ["SUP-02"])
            self.assertEqual(result["disagreements"], ["SUP-02"])
            self.assertEqual(result["adjudication"]["applied"], 0)
            self.assertEqual(len(result["adjudication_template"]["decisions"]), 1)
            self.assertEqual(result["agreement"]["pairs"][0]["items"], 3)
            self.assertIsNotNone(result["agreement"]["pairs"][0]["kappa"])
            self.assertEqual(result["pack_binding"], "bound")
            self.assertFalse((root / "claim.json").exists())

            resolved = audit_support_panel(
                draft,
                _pack(),
                [
                    ("profile:a", _judge({"SUP-01": "supported", "SUP-02": "partial"})),
                    ("profile:b", _judge({"SUP-01": "supported", "SUP-02": "supported"})),
                ],
                cache_dir=root / "cache",
                adjudication_path=adjudication,
            )
            self.assertEqual(resolved["status"], "ready")
            self.assertEqual(resolved["pending_human"], [])
            self.assertEqual(resolved["adjudication"]["applied"], 1)
            item = next(value for value in resolved["items"] if value["id"] == "SUP-02")
            self.assertEqual(item["final_status"], "supported")
            self.assertEqual(item["final_source"], "human_adjudication")

    def test_strict_panel_blocks_unadjudicated_disagreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = Path(tmp) / "draft.md"
            draft.write_text(DRAFT, encoding="utf-8")
            result = audit_support_panel(
                draft,
                _pack(),
                [
                    ("profile:a", _judge({"SUP-02": "partial"})),
                    ("profile:b", _judge({"SUP-02": "supported"})),
                ],
                strict=True,
                cache_dir=Path(tmp) / "cache",
            )
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["pending_human"], ["SUP-02"])

    def test_cli_support_panel_writes_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            pack = build_writing_pack(project, RUN_ID)
            target = run_dir(project, RUN_ID)
            write_json_atomic(target / "writing-pack.json", pack)
            draft = write_draft(root / "draft.md", result_text="无数字。")
            draft.write_text(
                ensure_pack_marker(draft.read_text(encoding="utf-8"), pack),
                encoding="utf-8",
            )
            with mock.patch(
                "research_agent.cli._resolve_support_judge",
                side_effect=lambda spec: (_judge({}), ""),
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = main(
                        [
                            "writing", "support-panel",
                            "--project", str(project),
                            "--run-id", RUN_ID,
                            "--draft", str(draft),
                            "--judge-profile", "a",
                            "--judge-profile", "b",
                            "--strict-support",
                        ]
                    )
            payload = json.loads(buffer.getvalue())
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["status"], "ready")
            self.assertTrue((target / "support-panel.json").is_file())
            self.assertTrue((target / "support-adjudication-template.json").is_file())

    def test_mcp_qoder_items_and_verdicts_round_trip_into_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            pack = build_writing_pack(project, RUN_ID)
            target = run_dir(project, RUN_ID)
            write_json_atomic(target / "writing-pack.json", pack)
            draft = project / "draft.md"
            draft.write_text(
                ensure_pack_marker(
                    write_draft(root / "source.md", result_text="无数字。").read_text(
                        encoding="utf-8"
                    ),
                    pack,
                ),
                encoding="utf-8",
            )
            from research_agent.mcp_server import ResearchMCPService

            service = ResearchMCPService(root)
            items = service.support_items(
                {
                    "project_dir": "project",
                    "run_id": RUN_ID,
                    "draft": "draft.md",
                }
            )["structuredContent"]
            self.assertTrue(items["judgeable_ids"])
            by_id = {item["id"]: item for item in items["items"]}
            verdicts = []
            for item_id in items["judgeable_ids"]:
                refs = [
                    entry["ref"]
                    for entry in by_id[item_id].get("evidence") or []
                    if entry.get("ref")
                ][:1]
                verdicts.append(
                    {
                        "id": item_id,
                        "status": "supported",
                        "rationale": "checked by Qoder",
                        "evidence_refs": refs,
                    }
                )
            recorded = service.support_verdicts(
                {
                    "project_dir": "project",
                    "run_id": RUN_ID,
                    "draft": "draft.md",
                    "judge_id": "qoder-session",
                    "verdicts": verdicts,
                }
            )["structuredContent"]
            self.assertEqual(recorded["status"], "ready")
            self.assertEqual(recorded["judge_model"], "qoder:qoder-session")
            self.assertTrue((target / "support-ledger.json").is_file())

            audit = service.manuscript_audit(
                {"project_dir": "project", "run_id": RUN_ID, "draft": "draft.md"}
            )["structuredContent"]
            self.assertEqual(audit["support"]["judge_model"], "qoder:qoder-session")
            self.assertEqual(audit["support"]["status"], "ready")

    def test_mcp_support_verdicts_reuse_after_single_sentence_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            pack = build_writing_pack(project, RUN_ID)
            target = run_dir(project, RUN_ID)
            write_json_atomic(target / "writing-pack.json", pack)
            source = write_draft(root / "source.md", result_text="无数字。").read_text(
                encoding="utf-8"
            )
            draft = project / "draft.md"
            draft.write_text(ensure_pack_marker(source, pack), encoding="utf-8")
            from research_agent.mcp_server import ResearchMCPService

            service = ResearchMCPService(root)
            items = service.support_items(
                {
                    "project_dir": "project",
                    "run_id": RUN_ID,
                    "draft": "draft.md",
                }
            )["structuredContent"]
            judgeable = items["judgeable_ids"]
            self.assertGreaterEqual(len(judgeable), 3)
            by_id = {item["id"]: item for item in items["items"]}
            first_verdicts = []
            for item_id in judgeable:
                refs = [
                    entry["ref"]
                    for entry in by_id[item_id].get("evidence") or []
                    if entry.get("ref")
                ][:1]
                first_verdicts.append(
                    {
                        "id": item_id,
                        "status": "supported",
                        "rationale": "checked by Qoder",
                        "evidence_refs": refs,
                    }
                )
            service.support_verdicts(
                {
                    "project_dir": "project",
                    "run_id": RUN_ID,
                    "draft": "draft.md",
                    "judge_id": "qoder-session",
                    "verdicts": first_verdicts,
                }
            )
            first_sha = json.loads(
                (target / "support-ledger.json").read_text(encoding="utf-8")
            )["draft_sha256"]

            changed = source.replace(
                "数据规模决策需要可复现的评估", "数据规模决策依赖可复现的评估", 1
            )
            self.assertNotEqual(source, changed)
            draft2 = project / "draft2.md"
            draft2.write_text(ensure_pack_marker(changed, pack), encoding="utf-8")
            items2 = service.support_items(
                {
                    "project_dir": "project",
                    "run_id": RUN_ID,
                    "draft": "draft2.md",
                }
            )["structuredContent"]
            changed_ids = [
                item["id"]
                for item in items2["items"]
                if "数据规模决策依赖" in item["sentence"]
            ]
            self.assertEqual(len(changed_ids), 1)
            changed_id = changed_ids[0]
            self.assertIn(changed_id, items2["judgeable_ids"])

            recorded = service.support_verdicts(
                {
                    "project_dir": "project",
                    "run_id": RUN_ID,
                    "draft": "draft2.md",
                    "judge_id": "qoder-session",
                    "reuse": True,
                    "verdicts": [
                        {
                            "id": changed_id,
                            "status": "partial",
                            "rationale": "changed sentence needs a new judgement",
                            "evidence_refs": [],
                        }
                    ],
                }
            )["structuredContent"]
            self.assertEqual(recorded["provided_count"], 1)
            self.assertEqual(recorded["reused_count"], len(items2["judgeable_ids"]) - 1)
            self.assertEqual(recorded["reuse_source"], "support-ledger.json")
            self.assertEqual(
                recorded["archived_ledger"],
                "support-ledger-history/support-ledger-%s.json" % first_sha[:16],
            )
            archived = json.loads(
                (target / recorded["archived_ledger"]).read_text(encoding="utf-8")
            )
            self.assertEqual(archived["draft_sha256"], first_sha)
            recorded_by_id = {item["id"]: item for item in recorded["items"]}
            unchanged = next(
                item_id
                for item_id in items2["judgeable_ids"]
                if item_id != changed_id
            )
            self.assertTrue(recorded_by_id[unchanged].get("reused"))
            self.assertEqual(recorded_by_id[changed_id]["status"], "partial")

            with self.assertRaises(ProjectError):
                service.support_verdicts(
                    {
                        "project_dir": "project",
                        "run_id": RUN_ID,
                        "draft": "draft2.md",
                        "judge_id": "different-judge",
                        "reuse": True,
                        "verdicts": [
                            {
                                "id": changed_id,
                                "status": "partial",
                                "rationale": "different judge cannot reuse",
                                "evidence_refs": [],
                            }
                        ],
                    }
                )

    def test_next_actions_surfaces_support_review_and_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            target = run_dir(project, RUN_ID)
            draft = project / "draft.md"
            draft.write_text("# draft\n", encoding="utf-8")
            write_json_atomic(
                target / "support-ledger.json",
                {
                    "status": "partial",
                    "draft": str(draft),
                    "counts": {
                        "supported": 2,
                        "partial": 1,
                        "insufficient": 0,
                        "contradicted": 0,
                        "not_required": 0,
                    },
                    "section_summary": {
                        "weak_sections": [
                            {"section": "引言", "weak": 1, "total": 3}
                        ]
                    },
                },
            )
            from research_agent.mcp_server import ResearchMCPService

            service = ResearchMCPService(root)
            actions = service.next_actions(
                {"project_dir": "project", "run_id": RUN_ID}
            )["structuredContent"]["next_actions"]
            self.assertEqual(actions[0]["kind"], "support_review")
            self.assertEqual(actions[0]["weak_sections"][0]["section"], "引言")
            self.assertIn("reuse=true", actions[0]["message"])
            self.assertEqual(actions[0]["draft"], "draft.md")

            (target / "task.json").unlink()
            without_task = service.next_actions(
                {"project_dir": "project", "run_id": RUN_ID}
            )["structuredContent"]["next_actions"]
            self.assertEqual(without_task[0]["kind"], "support_review")
            self.assertNotEqual(without_task[0]["kind"], "inspect")

    def test_next_actions_moves_from_support_ready_to_human_gold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            target = run_dir(project, RUN_ID)
            draft = project / "draft.md"
            draft.write_text("# draft\n", encoding="utf-8")
            digest = "a" * 64
            write_json_atomic(
                target / "support-ledger.json",
                {
                    "status": "ready",
                    "draft": str(draft),
                    "draft_sha256": digest,
                    "judge_model": "qoder:test",
                    "items": [{"id": "SUP-01", "status": "supported"}],
                    "section_summary": {"weak_sections": []},
                },
            )
            from research_agent.mcp_server import ResearchMCPService

            service = ResearchMCPService(root)
            actions = service.next_actions(
                {"project_dir": "project", "run_id": RUN_ID}
            )["structuredContent"]["next_actions"]
            self.assertEqual(actions[0]["kind"], "human_gold")
            self.assertIn("support-gold-template", actions[0]["cli"])
            self.assertNotIn("support-gold --project", actions[0]["cli"])

            write_json_atomic(
                target / "support-gold-template.json",
                {"draft_sha256": digest, "item_count": 1},
            )
            actions = service.next_actions(
                {"project_dir": "project", "run_id": RUN_ID}
            )["structuredContent"]["next_actions"]
            self.assertEqual(actions[0]["kind"], "human_gold")
            self.assertIn("support-gold --project", actions[0]["cli"])

            write_json_atomic(
                target / "support-gold.json",
                {
                    "draft_sha256": digest,
                    "status": "complete",
                    "panel": {"accuracy": 1.0, "disagreements": []},
                },
            )
            actions = service.next_actions(
                {"project_dir": "project", "run_id": RUN_ID}
            )["structuredContent"]["next_actions"]
            kinds = [action["kind"] for action in actions]
            self.assertIn("human_gold_ready", kinds)
            self.assertNotIn("human_gold", kinds)

    def test_status_surfaces_qoder_native_manuscript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            target = run_dir(project, RUN_ID)
            (target / "task.json").unlink()
            draft = project / "draft.md"
            draft.write_text("# draft\n", encoding="utf-8")
            digest = "a" * 64
            write_json_atomic(
                target / "support-ledger.json",
                {
                    "status": "ready",
                    "draft": str(draft),
                    "draft_sha256": digest,
                    "judge_model": "qoder:test",
                    "counts": {
                        "supported": 1,
                        "partial": 0,
                        "contradicted": 0,
                        "insufficient": 0,
                        "not_required": 0,
                    },
                    "section_summary": {"weak_sections": []},
                },
            )
            write_json_atomic(
                target / "writing-audit.json",
                {
                    "status": "ready_for_human_review",
                    "submission_ready": False,
                    "draft": str(draft),
                },
            )
            write_json_atomic(
                target / "support-gold-template.json",
                {"draft_sha256": digest},
            )
            other = project / "runs" / "RUN-OTHER"
            other.mkdir(parents=True, exist_ok=True)
            write_json_atomic(other / "task.json", {"status": "completed"})
            write_json_atomic(
                project / "runs" / "index.json",
                {"runs": [{"run_id": "RUN-OTHER", "status": "completed"}]},
            )
            from research_agent.mcp_server import ResearchMCPService

            service = ResearchMCPService(root)
            result = service.status(
                {"project_dir": "project", "limit": 10}
            )["structuredContent"]
            row = next(
                item for item in result["runs"] if item["run_id"] == RUN_ID
            )
            other_row = next(
                item for item in result["runs"] if item["run_id"] == "RUN-OTHER"
            )
            self.assertEqual(other_row["status"], "completed")
            self.assertTrue(row.get("qoder_native"))
            self.assertEqual(row["status"], "manuscript:ready")
            self.assertEqual(row["support"]["status"], "ready")
            self.assertEqual(row["support"]["counts"]["supported"], 1)
            self.assertEqual(row["support"]["draft"], "draft.md")
            self.assertEqual(
                row["manuscript"]["status"], "ready_for_human_review"
            )
            self.assertFalse(row["manuscript"]["submission_ready"])
            self.assertTrue(row["support_gold"]["templates"])
            self.assertFalse(row["support_gold"]["evaluated"])

    def test_next_actions_includes_experiment_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            data = project / "inputs" / "data.csv"
            data.parent.mkdir(parents=True, exist_ok=True)
            rows = ["x1,x2,y"]
            for index in range(1, 13):
                rows.append("%d,%d,%d" % (index, index * 2, index * 3 + 1))
            data.write_text("\n".join(rows) + "\n", encoding="utf-8")
            from research_agent.experiment_codegen import generate_experiment_code

            generated = generate_experiment_code(
                project,
                RUN_ID,
                data_path="inputs/data.csv",
                target="y",
                features=["x1", "x2"],
                methods=["dummy", "ridge"],
                seeds=3,
            )
            self.assertEqual(generated["status"], "generated")
            from research_agent.mcp_server import ResearchMCPService

            service = ResearchMCPService(root)
            actions = service.next_actions(
                {"project_dir": "project", "run_id": RUN_ID}
            )["structuredContent"]["next_actions"]
            action = next(
                item for item in actions if item["kind"] == "experiment_approval"
            )
            self.assertEqual(action["experiment_id"], generated["experiment_id"])
            self.assertIn("experiment approve", action["cli"])

    def test_status_surfaces_idea_shortlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            target = run_dir(project, RUN_ID)
            write_json_atomic(
                target / "idea.json",
                {
                    "run_id": "IDEA-TEST",
                    "status": "candidates_need_human",
                    "candidates": [
                        {
                            "idea_id": "IDEA-01",
                            "title": "候选一",
                            "prior_art_scope": "live_search",
                            "novelty_status": "unverified",
                            "evidence_count": 2,
                            "source_count": 1,
                            "kill_criteria": "drop if covered",
                        },
                        {
                            "idea_id": "IDEA-02",
                            "title": "候选二",
                            "prior_art_scope": "none",
                            "novelty_status": "unverified",
                            "evidence_count": 1,
                            "source_count": 1,
                        },
                    ],
                    "shortlist": {
                        "ranked": [
                            {"rank": 1, "idea_id": "IDEA-01", "prior_art_scope": "live_search"},
                            {"rank": 2, "idea_id": "IDEA-02", "prior_art_scope": "none"},
                        ],
                        "selection": "human_g1",
                        "boundary": "advisory only; human G1",
                    },
                },
            )
            from research_agent.mcp_server import ResearchMCPService

            service = ResearchMCPService(root)
            result = service.status(
                {"project_dir": "project", "limit": 10}
            )["structuredContent"]
            row = next(
                item for item in result["runs"] if item["run_id"] == RUN_ID
            )
            self.assertEqual(row["idea"]["candidate_count"], 2)
            self.assertEqual(row["idea"]["shortlist_selection"], "human_g1")
            self.assertEqual(
                row["idea"]["candidates"][0]["prior_art_scope"],
                "live_search",
            )
            self.assertEqual(
                row["idea"]["shortlist_ranked"][0]["idea_id"], "IDEA-01"
            )

    def test_status_surfaces_experiment_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            data = project / "inputs" / "data.csv"
            data.parent.mkdir(parents=True, exist_ok=True)
            rows = ["x1,x2,y"]
            for index in range(1, 13):
                rows.append("%d,%d,%d" % (index, index * 2, index * 3 + 1))
            data.write_text("\n".join(rows) + "\n", encoding="utf-8")
            from research_agent.experiment_codegen import generate_experiment_code

            generated = generate_experiment_code(
                project,
                RUN_ID,
                data_path="inputs/data.csv",
                target="y",
                features=["x1", "x2"],
                methods=["dummy", "ridge"],
                seeds=3,
            )
            from research_agent.mcp_server import ResearchMCPService

            service = ResearchMCPService(root)
            result = service.status(
                {"project_dir": "project", "limit": 10}
            )["structuredContent"]
            row = next(
                item for item in result["runs"] if item["run_id"] == RUN_ID
            )
            experiments = row.get("experiments") or []
            self.assertEqual(
                experiments[0]["experiment_id"], generated["experiment_id"]
            )
            self.assertEqual(experiments[0]["stages"]["approval"], "missing")
            self.assertIn("approve", experiments[0]["next_action"].lower())
            inventory = result.get("experiment_inventory") or {}
            self.assertEqual(inventory["count"], 1)
            self.assertEqual(
                inventory["experiments"][0]["experiment_id"],
                generated["experiment_id"],
            )
            self.assertIn("read-only", inventory["boundary"].lower())

    def test_cli_writing_bind_from_existing_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            pack = build_writing_pack(project, RUN_ID)
            write_json_atomic(run_dir(project, RUN_ID) / "writing-pack.json", pack)
            source = project / "inputs" / "external.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(
                "# 手稿\n\n## 引言\n\n已有结论[REF-01]。\n", encoding="utf-8"
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    [
                        "writing", "bind",
                        "--project", str(project),
                        "--run-id", RUN_ID,
                        "--draft", "inputs/external.md",
                        "--output", "drafts/bound-cli.md",
                    ]
                )
            self.assertEqual(code, 0, buffer.getvalue())
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["resolved_refs"], ["REF-01"])
            self.assertEqual(payload["unresolved_refs"], [])
            bound = (project / "drafts" / "bound-cli.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("writing-pack:", bound)
            self.assertIn("已有结论[REF-01]。", bound)

    def test_mcp_manuscript_bind_attaches_pack_marker_without_changing_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            pack = build_writing_pack(project, RUN_ID)
            target = run_dir(project, RUN_ID)
            write_json_atomic(target / "writing-pack.json", pack)
            source = project / "external-draft.md"
            body = (
                "# 已有手稿\n\n## 引言\n\n已有结论[REF-01]。\n\n"
                "## 讨论\n\n未映射引用[REF-99]。\n"
            )
            source.write_text(body, encoding="utf-8")
            from research_agent.mcp_server import ResearchMCPService

            service = ResearchMCPService(root)
            result = service.manuscript_bind(
                {
                    "project_dir": "project",
                    "run_id": RUN_ID,
                    "draft": "external-draft.md",
                    "output": "drafts/bound-draft.md",
                }
            )["structuredContent"]
            self.assertIn("writing-pack:", result["marker"])
            self.assertEqual(result["resolved_refs"], ["REF-01"])
            self.assertEqual(result["unresolved_refs"], ["REF-99"])
            bound = (project / "drafts/bound-draft.md").read_text(encoding="utf-8")
            self.assertIn("writing-pack:", bound)
            self.assertIn(body.strip(), bound)

            items = service.support_items(
                {
                    "project_dir": "project",
                    "run_id": RUN_ID,
                    "draft": "drafts/bound-draft.md",
                }
            )["structuredContent"]
            self.assertTrue(items["judgeable_ids"])

            with self.assertRaises(ProjectError):
                service.manuscript_bind(
                    {
                        "project_dir": "project",
                        "run_id": RUN_ID,
                        "draft": "drafts/bound-draft.md",
                        "output": "drafts/bound-2.md",
                    }
                )
            with self.assertRaises(ProjectError):
                service.manuscript_bind(
                    {
                        "project_dir": "project",
                        "run_id": RUN_ID,
                        "draft": "external-draft.md",
                        "output": "external-draft.md",
                    }
                )
            source.write_text("# 未映射\n\n[REF-99]。\n", encoding="utf-8")
            with self.assertRaises(ProjectError):
                service.manuscript_bind(
                    {
                        "project_dir": "project",
                        "run_id": RUN_ID,
                        "draft": "external-draft.md",
                        "output": "drafts/unresolved.md",
                    }
                )

    def test_mcp_support_panel_service_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            pack = build_writing_pack(project, RUN_ID)
            target = run_dir(project, RUN_ID)
            write_json_atomic(target / "writing-pack.json", pack)
            draft = project / "draft.md"
            draft.write_text(
                ensure_pack_marker(
                    "# 引言\n\n研究表明，该方法在湿热条件下保持稳定[REF-01]。",
                    pack,
                ),
                encoding="utf-8",
            )
            from research_agent.mcp_server import ResearchMCPService

            service = ResearchMCPService(root)
            with mock.patch.object(
                ResearchMCPService,
                "_gateway_support_judge",
                return_value=(_judge({}), ""),
            ):
                response = service.support_panel(
                    {
                        "project_dir": "project",
                        "run_id": RUN_ID,
                        "draft": "draft.md",
                        "judge_profiles": ["a", "b"],
                        "judge_providers": {"a": "openai", "b": "anthropic"},
                        "require_providers": True,
                        "strict_support": True,
                    }
                )
            self.assertFalse(response["isError"])
            payload = response["structuredContent"]
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["independence"], "distinct_providers")
            self.assertEqual(payload["provider_requirement"], "required")
            self.assertTrue((target / "support-panel.json").is_file())
            self.assertTrue((target / "support-adjudication-template.json").is_file())

    def test_panel_fails_closed_on_unbound_draft_and_invalid_adjudication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft = root / "draft.md"
            draft.write_text("# 引言\n\n研究表明，该方法在湿热条件下保持稳定[REF-01]。", encoding="utf-8")
            with self.assertRaises(SupportPanelError):
                audit_support_panel(
                    draft,
                    _pack(),
                    [("profile:a", _judge({}))],
                    cache_dir=root / "cache",
                )

            draft.write_text(DRAFT, encoding="utf-8")
            bad = root / "bad.json"
            bad.write_text(
                json.dumps(
                    {"decisions": [{"id": "SUP-02", "status": "partial", "human_reason": ""}]}
                ),
                encoding="utf-8",
            )
            with self.assertRaises(SupportPanelError):
                audit_support_panel(
                    draft,
                    _pack(),
                    [
                        ("profile:a", _judge({"SUP-02": "partial"})),
                        ("profile:b", _judge({"SUP-02": "supported"})),
                    ],
                    cache_dir=root / "cache",
                    adjudication_path=bad,
                )

            with self.assertRaises(SupportPanelError):
                audit_support_panel(
                    draft,
                    _pack(),
                    [("profile:a", _judge({}))],
                    strict=True,
                    cache_dir=root / "cache",
                )


if __name__ == "__main__":
    unittest.main()
