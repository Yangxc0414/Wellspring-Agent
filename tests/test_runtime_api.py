import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from research_agent.runtime.app import create_app
from research_agent.runtime.jobs import default_settings
from research_agent.experiment_codegen import generate_experiment_code
from research_agent.project import init_project
from research_agent.storage import write_json_atomic


class RuntimeApiTest(unittest.TestCase):
    def test_research_api_capabilities_and_tool_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = default_settings()
            settings.jobs_root = root / "jobs"
            settings.workspace_memory_path = root / "workspace_memory.json"
            settings.workspace_archive_root = root / "archive"
            settings.literature_memory_path = root / "literature_memory.json"
            settings.custom_agents_path = root / "custom_agents.json"
            settings.evolution_policy_path = root / "evolution_policy.json"
            settings.skill_registry_path = root / "skills.json"
            settings.model_store_path = root / "model_gateway.json"
            settings.research_api_root = root / "research-root"
            settings.research_api_root.mkdir()
            settings.research_api_token = "test-secret"
            app = create_app(settings)
            with TestClient(app) as client:
                denied = client.get("/api/research/capabilities")
                self.assertEqual(denied.status_code, 401)
                headers = {"Authorization": "Bearer test-secret"}
                caps = client.get("/api/research/capabilities", headers=headers)
                self.assertEqual(caps.status_code, 200)
                from research_agent.mcp_server import TOOL_NAMES

                payload = caps.json()
                # the HTTP surface must expose exactly the dispatch layer's tools; a copied
                # count here would only remind the author to edit the test
                self.assertEqual(len(payload["tools"]), len(TOOL_NAMES))
                self.assertEqual({tool["name"] for tool in payload["tools"]}, set(TOOL_NAMES))
                created = client.post(
                    "/api/research/tools/research_project_init",
                    headers=headers,
                    json={"project_dir": "demo", "name": "HTTP bridge"},
                )
                self.assertEqual(created.status_code, 200)
                self.assertTrue(created.json()["result"]["created"])
                self.assertTrue((settings.research_api_root / "demo" / "project.json").is_file())
                missing = client.post(
                    "/api/research/tools/made_up", headers=headers, json={}
                )
                self.assertEqual(missing.status_code, 400)

    def test_project_experiment_inventory_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = default_settings()
            settings.repo_root = root
            settings.jobs_root = root / "jobs"
            settings.workspace_memory_path = root / "workspace_memory.json"
            settings.workspace_archive_root = root / "archive"
            settings.literature_memory_path = root / "literature_memory.json"
            settings.custom_agents_path = root / "custom_agents.json"
            settings.evolution_policy_path = root / "evolution_policy.json"
            settings.skill_registry_path = root / "skills.json"
            settings.model_store_path = root / "model_gateway.json"
            project = root / "paper"
            init_project(project, "Paper")
            rows = ["x1,x2,y"] + [
                "%d,%d,%d" % (index, index % 5, index * 2 + (index % 4))
                for index in range(48)
            ]
            (project / "data.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
            run = project / "runs" / "RUN-INVENTORY"
            run.mkdir()
            write_json_atomic(run / "experiment.json", {"run_id": "RUN-INVENTORY"})
            generate_experiment_code(
                project,
                "RUN-INVENTORY",
                data_path="data.csv",
                target="y",
                features=["x1", "x2"],
                task="regression",
                methods=["dummy", "ridge"],
                seeds=2,
                experiment_id="EXP-INVENTORY",
            )
            app = create_app(settings)
            with TestClient(app) as client:
                projects = client.get("/api/projects")
                self.assertEqual(projects.status_code, 200)
                body = projects.json()
                self.assertEqual(body["count"], 1)
                self.assertEqual(body["projects"][0]["project_dir"], "paper")
                self.assertEqual(body["projects"][0]["experiment_count"], 1)
                self.assertNotIn("root", body)
                inventory = client.get(
                    "/api/project-experiments", params={"project_dir": "paper"}
                )
                self.assertEqual(inventory.status_code, 200)
                payload = inventory.json()
                self.assertEqual(payload["count"], 1)
                experiment = payload["experiments"][0]
                self.assertEqual(experiment["experiment_id"], "EXP-INVENTORY")
                self.assertEqual(experiment["stages"]["spec"], "ready")
                self.assertEqual(experiment["next_action"], "experiment approve")
                self.assertNotIn(str(root), str(payload))
                closures = client.get("/api/project-closures", params={"project_dir": "paper"})
                self.assertEqual(closures.status_code, 200)
                closure_body = closures.json()
                self.assertEqual(closure_body["schema_version"], "closure-profiles-0.7")
                self.assertEqual(
                    [item["experiment_id"] for item in closure_body["local_experiment"]],
                    ["EXP-INVENTORY"],
                )
                self.assertEqual(closure_body["search_study"], [])
                self.assertNotIn(str(root), str(closure_body))
                outside_closures = client.get(
                    "/api/project-closures", params={"project_dir": "../outside"}
                )
                self.assertEqual(outside_closures.status_code, 400)
                outside = client.get(
                    "/api/project-experiments", params={"project_dir": "../outside"}
                )
                self.assertEqual(outside.status_code, 400)
                missing = client.get(
                    "/api/project-experiments", params={"project_dir": "missing"}
                )
                self.assertEqual(missing.status_code, 404)

    def test_autopilot_status_is_read_only_and_path_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = default_settings()
            settings.repo_root = root
            settings.jobs_root = root / "jobs"
            settings.workspace_memory_path = root / "workspace_memory.json"
            settings.workspace_archive_root = root / "archive"
            settings.literature_memory_path = root / "literature_memory.json"
            settings.custom_agents_path = root / "custom_agents.json"
            settings.evolution_policy_path = root / "evolution_policy.json"
            settings.skill_registry_path = root / "skills.json"
            settings.model_store_path = root / "model_gateway.json"
            project = root / "paper"
            init_project(project, "Paper")
            write_json_atomic(project / "autopilot" / "ledger.json", {
                "schema_version": "autopilot-ledger-0.1",
                "runs": [{
                    "policy_id": "AUTO-1",
                    "run_id": "RUN-1",
                    "status": "completed",
                    "claim_id": "CLM-1",
                    "signature_id": "SIG-1",
                    "bundle": str(project / "bundles" / "RUN-1"),
                }],
            })
            write_json_atomic(project / "autopilot" / "RUN-1" / "autopilot-report.json", {
                "run_id": "RUN-1",
                "status": "completed",
                "policy": {"policy_id": "AUTO-1", "authorized_by": "owner"},
                "steps": [{"step": "G5-sign", "status": "delegated", "detail": "x"}],
                "artifacts": {
                    "claim": {"claim_id": "CLM-1", "path": str(project / "claim.json")},
                    "bundle": {"path": str(project / "bundles" / "RUN-1"), "verified": True},
                },
            })
            app = create_app(settings)
            with TestClient(app) as client:
                response = client.get("/api/autopilot-status", params={"project_dir": "paper"})
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["schema_version"], "autopilot-snapshot-0.1")
                self.assertEqual(body["claim"]["claim_id"], "CLM-1")
                self.assertEqual(body["bundle"]["path"], "bundles/RUN-1")
                self.assertTrue(body["bundle"]["verified"])
                self.assertNotIn(str(root), str(body))
                outside = client.get("/api/autopilot-status", params={"project_dir": "../outside"})
                self.assertEqual(outside.status_code, 400)

    def test_health_and_pipeline_job_run_through_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = default_settings()
            settings.jobs_root = root / "jobs"
            settings.workspace_memory_path = root / "workspace_memory.json"
            settings.workspace_archive_root = root / "archive"
            settings.literature_memory_path = root / "literature_memory.json"
            settings.custom_agents_path = root / "custom_agents.json"
            settings.evolution_policy_path = root / "evolution_policy.json"
            settings.skill_registry_path = root / "skills.json"
            settings.model_store_path = root / "model_gateway.json"
            app = create_app(settings)
            with TestClient(app) as client:
                health = client.get("/api/health")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json()["human_sign"], False)
                self.assertTrue(health.json()["rsi_read_only"])
                created = client.post("/api/runs", json={
                    "topic": "API integration smoke test",
                    "language": "en",
                    "venue_type": "en_conference",
                    "max_sources": 2,
                })
                self.assertEqual(created.status_code, 202)
                job_id = created.json()["job_id"]
                final = None
                for _ in range(80):
                    response = client.get("/api/runs/" + job_id)
                    self.assertEqual(response.status_code, 200)
                    final = response.json()
                    if final["status"] in ("completed", "failed"):
                        break
                    time.sleep(0.2)
                self.assertIsNotNone(final)
                self.assertEqual(final["status"], "completed")
                self.assertIn("result", final)
                artifacts = client.get("/api/runs/" + job_id + "/artifacts")
                self.assertEqual(artifacts.status_code, 200)
                self.assertGreaterEqual(len(artifacts.json()["artifacts"]), 1)

    def test_exec_stats_is_read_only_telemetry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = default_settings()
            settings.jobs_root = root / "jobs"
            settings.workspace_memory_path = root / "workspace_memory.json"
            settings.workspace_archive_root = root / "archive"
            settings.literature_memory_path = root / "literature_memory.json"
            settings.custom_agents_path = root / "custom_agents.json"
            settings.evolution_policy_path = root / "evolution_policy.json"
            settings.skill_registry_path = root / "skills.json"
            settings.model_store_path = root / "model_gateway.json"
            app = create_app(settings)
            with TestClient(app) as client:
                body = client.get("/api/exec/stats")
                self.assertEqual(body.status_code, 200)
                payload = body.json()
                self.assertEqual(payload["schema_version"], "exec-port-0.2")
                kinds = {face["kind"] for face in payload["faces"]}
                self.assertEqual(
                    kinds, {"bridge", "host_agent", "inprocess"},
                    "three execution faces must be registered for the seam",
                )
                self.assertIn("counts", payload["dispatch_stats"])
                self.assertIn("recent", payload["dispatch_stats"])
                # 只读边界：不启动/不杀死/不调度进程，不产生门禁语义
                self.assertIn("never", payload["boundary"].lower())
                self.assertIn("no claim/ea/gate/signature", payload["boundary"].lower())
                # POST 必须被拒绝——遥测端点不允许写路径
                self.assertEqual(client.post("/api/exec/stats").status_code, 405)


if __name__ == "__main__":
    unittest.main()
