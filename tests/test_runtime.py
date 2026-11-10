import json
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from research_agent.evolution_active import ActivePolicyStore
from research_agent.models import ModelRequiredError
from research_agent.rsi import (
    Candidate,
    EvalEvidence,
    RSIController,
    StepLedger,
)
from research_agent.runtime.app import create_app
from research_agent.runtime.jobs import RuntimeSettings


def _eval(split):
    return EvalEvidence(
        split=split,
        status="passed",
        artifact_ref="artifact-%s.json" % split,
        metrics={"coverage": 0.9},
        n=10,
        simulation=False,
        claim_eligible=True,
        evaluator="test-evaluator",
        artifact_sha256="a" * 64,
        task_pack_sha256="b" * 64,
    )


def _activate_budget(root: Path) -> Path:
    ledger_path = root / "rsi-active.json"
    controller = RSIController(StepLedger(ledger_path))
    record = controller.propose(
        Candidate(
            kind="process",
            target="literature.retrieval.budget",
            patch=json.dumps({"retriever": "bm25", "max_sources": 3}),
            rationale="healthy coverage at lower budget",
            predicted_effect="same coverage with fewer sources",
            scope="S1/test",
            proposer="test",
        ),
        dry_run_ref="DRY-ACTIVE",
    )
    controller.admit(
        record.episode_id,
        _eval("public"),
        _eval("hidden"),
        "approved after review",
        "S1/test",
        30,
        near_ood_eval=_eval("near_ood"),
        regression_eval=_eval("regression"),
    )
    active_path = root / "evolution_active.json"
    ActivePolicyStore(active_path).activate(
        ledger_path, "S1/test", "human approved bounded budget policy"
    )
    return active_path


class RuntimeAPITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = Path(__file__).resolve().parents[1]
        self.rsi_root = self.root / "rsi"
        self.rsi_root.mkdir()
        settings = RuntimeSettings(
            repo_root=self.repo,
            jobs_root=self.root / "jobs",
            allowed_rsi_roots=[self.rsi_root],
            default_rsi_ledger=None,
            real_corpus_path=self.repo / "modules" / "literature" / "fixtures" / "real_corpus.json",
            model_store_path=self.root / "model_gateway.json",
            workspace_memory_path=self.root / "workspace_memory.json",
            workspace_archive_root=self.root / "workspace_archive",
            literature_memory_path=self.root / "literature_memory.json",
            custom_agents_path=self.root / "custom_agents.json",
            evolution_policy_path=self.root / "evolution_policy.json",
            evolution_observations_path=self.root / "evolution_observations.json",
            evolution_active_path=self.root / "evolution_active.json",
            skill_registry_path=self.root / "skills.json",
            max_pending=2,
        )
        self.settings = settings
        self.app = create_app(settings)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def _wait(self, job_id, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            response = self.client.get("/api/runs/" + job_id)
            self.assertEqual(response.status_code, 200)
            job = response.json()
            if job["status"] in ("completed", "failed"):
                return job
            time.sleep(0.1)
        self.fail("job did not finish: " + job_id)

    def test_governance_preflight_reports_the_three_faces(self):
        from research_agent.mcp_server import TOOL_NAMES

        response = self.client.get("/api/research/preflight")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["schema_version"], "preflight-0.1")
        self.assertEqual(body["faces"]["mcp_tools"], len(TOOL_NAMES))
        self.assertEqual(
            body["faces"]["http_tools"],
            body["faces"]["mcp_tools"],
            "the HTTP surface must expose the same tools as MCP",
        )
        self.assertGreaterEqual(body["faces"]["cli_commands"], body["faces"]["mcp_tools"])
        self.assertIn("bookkeeping only", body["boundary"])
        self.assertIn("cannot run any command", body["boundary"])

    def test_health_validation_and_fixture_run(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertFalse(health.json()["human_sign"])

        invalid = self.client.post("/api/runs", json={"topic": "x"})
        self.assertEqual(invalid.status_code, 422)
        invalid_seeds = self.client.post(
            "/api/runs", json={"topic": "valid topic", "run_seeds": 0}
        )
        self.assertEqual(invalid_seeds.status_code, 422)

        created = self.client.post(
            "/api/runs", json={"topic": "fixture runtime test", "max_sources": 2}
        )
        self.assertEqual(created.status_code, 202)
        job_id = created.json()["job_id"]
        job = self._wait(job_id)
        self.assertEqual(job["status"], "completed")
        self.assertTrue(job["result"]["fixture_mode"])
        self.assertIn("paper", job["result"]["modules"])

        events = self.client.get("/api/runs/%s/events" % job_id).json()
        types = [(item["type"], item.get("stage")) for item in events["events"]]
        self.assertTrue(events["terminal"])
        self.assertIn(("stage_start", "literature"), types)
        self.assertIn(("run_complete", None), types)

        artifacts = self.client.get("/api/runs/%s/artifacts" % job_id).json()["artifacts"]
        paths = {item["path"] for item in artifacts}
        self.assertIn("demo.json", paths)
        self.assertIn("paper.json", paths)
        self.assertIn("figure.svg", paths)
        demo = self.client.get("/api/runs/%s/artifacts/demo.json" % job_id)
        self.assertEqual(demo.status_code, 200)
        payload = demo.json()
        self.assertEqual(payload["runtime"]["job_id"], job_id)
        self.assertIn("fixture", payload["source"])

        traversal = self.client.get(
            "/api/runs/%s/artifacts/..%%2F..%%2Fsecret.json" % job_id
        )
        self.assertIn(traversal.status_code, (400, 404))

        artifact = self.client.get("/api/runs/%s/artifacts/literature.json" % job["job_id"])
        self.assertEqual(artifact.status_code, 200)

        self.assertTrue(job["result"].get("observation_id"))
        observations = self.client.get("/api/evolution/observations").json()
        self.assertEqual(observations["summary"]["count"], 1)
        self.assertTrue(observations["boundary"].startswith("runtime observations only"))

    def test_runtime_applies_active_budget_policy(self):
        active_path = _activate_budget(self.root)
        self.settings.evolution_active_path = active_path
        app = create_app(self.settings)
        with TestClient(app) as client:
            created = client.post(
                "/api/runs",
                json={"topic": "active budget policy test", "max_sources": 8},
            )
            self.assertEqual(created.status_code, 202)
            job = None
            for _ in range(80):
                response = client.get("/api/runs/" + created.json()["job_id"])
                self.assertEqual(response.status_code, 200)
                job = response.json()
                if job["status"] in ("completed", "failed"):
                    break
                time.sleep(0.1)
            self.assertIsNotNone(job)
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["result"]["max_sources"], 3)
            self.assertEqual(
                job["result"]["active_policy"]["patch"]["max_sources"], 3
            )
            events = client.get("/api/runs/%s/events" % job["job_id"]).json()["events"]
            self.assertTrue(
                any(
                    "active evolution policy" in item["message"]
                    for item in events
                )
            )

    def test_runtime_applies_active_s5_seed_lease(self):
        from research_agent.s5_eval import run_s5_trial

        ledger = self.root / "s5-lease-ledger.json"
        run_s5_trial(
            ledger,
            self.root / "s5-lease-trial",
            human_approve=True,
            dataset="iris",
        )
        original = self.settings.default_rsi_ledger
        self.settings.default_rsi_ledger = ledger
        try:
            app = create_app(self.settings)
            with TestClient(app) as client:
                created = client.post(
                    "/api/runs",
                    json={
                        "topic": "active S5 seed lease test",
                        "run_dataset": "iris",
                        "run_seeds": 5,
                    },
                )
                self.assertEqual(created.status_code, 202)
                job = None
                for _ in range(80):
                    response = client.get("/api/runs/" + created.json()["job_id"])
                    self.assertEqual(response.status_code, 200)
                    job = response.json()
                    if job["status"] in ("completed", "failed"):
                        break
                    time.sleep(0.1)
                self.assertIsNotNone(job)
                self.assertEqual(job["status"], "completed")
                self.assertEqual(job["result"]["requested_run_seeds"], 5)
                self.assertEqual(job["result"]["run_seeds"], 3)
                self.assertEqual(job["result"]["active_s5_lease"]["seeds"], 3)
                events = client.get(
                    "/api/runs/%s/events" % job["job_id"]
                ).json()["events"]
                self.assertTrue(
                    any("active S5 seed lease" in item["message"] for item in events)
                )
        finally:
            self.settings.default_rsi_ledger = original

    def test_production_mode_fails_closed_without_model_readiness(self):
        settings = self.settings
        settings.research_mode = "production"
        app = create_app(settings)
        with TestClient(app) as client:
            health = client.get("/api/health").json()
            self.assertEqual(health["research_mode"], "production")
            self.assertFalse(health["production_ready"])
            response = client.post("/api/runs", json={"topic": "production gate test"})
            self.assertEqual(response.status_code, 503)
            detail = response.json()["detail"]
            self.assertIn("readiness", detail)
            self.assertTrue(any("no model profile binding" in item for item in detail["readiness"]["blocking"]))

    def test_production_model_tools_fail_closed_without_binding(self):
        self.settings.research_mode = "production"
        with self.assertRaises(ModelRequiredError):
            self.app.state.manager._model_tools()

    def test_runtime_strict_flow_stops_at_g1(self):
        created = self.client.post(
            "/api/runs",
            json={"topic": "strict runtime gate test", "max_sources": 2, "flow_mode": "strict"},
        )
        self.assertEqual(created.status_code, 202)
        job = self._wait(created.json()["job_id"])
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"]["status"], "needs_g1")
        self.assertEqual(job["result"]["flow_mode"], "strict")
        self.assertEqual(job["result"]["stopped_at"], "G1")
        self.assertIn("JOB-", job["result"]["job_dir"])
        self.assertIn(job["job_id"], job["result"]["job_dir"])
        packages = {item["id"]: item for item in job["result"]["evidence_packages"]}
        self.assertEqual(packages["literature"]["status"], "partial")
        self.assertEqual(packages["design"]["status"], "missing")
        artifacts = self.client.get(
            "/api/runs/%s/artifacts" % job["job_id"]
        ).json()["artifacts"]
        paths = {item["path"] for item in artifacts}
        self.assertIn("idea.json", paths)
        self.assertIn("q0.json", paths)
        self.assertNotIn("paper.md", paths)

    def test_runtime_rejects_unsafe_resume_paths(self):
        created = self.client.post(
            "/api/runs",
            json={
                "topic": "unsafe resume path",
                "protocol_file": "C:/Windows/win.ini",
            },
        )
        self.assertEqual(created.status_code, 202)
        job = self._wait(created.json()["job_id"])
        self.assertEqual(job["status"], "failed")
        self.assertIn("inside the repository", job["error"])

    def test_completed_job_survives_runtime_restart(self):
        created = self.client.post(
            "/api/runs", json={"topic": "persistent runtime job", "max_sources": 2}
        )
        self.assertEqual(created.status_code, 202)
        job_id = created.json()["job_id"]
        first = self._wait(job_id)
        self.assertEqual(first["status"], "completed")

        second_app = create_app(self.settings)
        with TestClient(second_app) as second:
            listed = second.get("/api/runs")
            self.assertEqual(listed.status_code, 200)
            self.assertIn(job_id, {item["job_id"] for item in listed.json()["jobs"]})
            recovered = second.get("/api/runs/" + job_id)
            self.assertEqual(recovered.status_code, 200)
            self.assertEqual(recovered.json()["status"], "completed")
            self.assertEqual(recovered.json()["result"]["run_id"], first["result"]["run_id"])
            events = second.get("/api/runs/%s/events" % job_id)
            self.assertTrue(events.json()["terminal"])
            self.assertTrue(events.json()["events"])
            artifacts = second.get("/api/runs/%s/artifacts" % job_id).json()["artifacts"]
            paths = {item["path"] for item in artifacts}
            self.assertIn("report.md", paths)
            self.assertIn("paper.md", paths)
            self.assertNotIn("job.json", paths)
            demo = second.get("/api/runs/%s/artifacts/demo.json" % job_id)
            self.assertEqual(demo.status_code, 200)

    def test_artifact_listing_survives_an_entry_that_vanishes(self):
        # a job directory is live: cleanup or a scanner can remove an entry between
        # is_file() and stat(), and that must not turn a listing into a 500
        from types import SimpleNamespace
        from unittest import mock

        from research_agent.runtime.jobs import JobManager

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "report.md").write_text("# ok\n", encoding="utf-8")
            (root / "raced.json").write_text("{}", encoding="utf-8")
            real_stat = Path.stat
            seen = {"count": 0}

            def flaky_stat(self, *args, **kwargs):
                if self.name == "raced.json":
                    seen["count"] += 1
                    if seen["count"] > 1:
                        # first stat (from is_file) succeeds, the second (the size read)
                        # hits the file already gone: the listing must degrade, not 500
                        import errno

                        raise FileNotFoundError(errno.ENOENT, "gone", str(self))
                return real_stat(self, *args, **kwargs)

            job = SimpleNamespace(job_id="JOB-RACE", output_dir=root)
            with mock.patch.object(Path, "stat", flaky_stat):
                items = JobManager.artifacts(None, job)
            self.assertEqual([item["path"] for item in items], ["report.md"])
            self.assertEqual(items[0]["size"], 6)

    def test_runtime_can_execute_task_agent_route(self):
        created = self.client.post(
            "/api/runs",
            json={
                "topic": "钙钛矿界面钝化 文献综述",
                "task_type": "literature_review",
                "max_sources": 2,
            },
        )
        self.assertEqual(created.status_code, 202)
        job = self._wait(created.json()["job_id"])
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"]["route"], "literature_review")
        self.assertEqual(job["result"]["status"], "completed")
        self.assertIn("task-report.md", job["result"]["artifacts"])
        self.assertIn("literature.json", job["result"]["artifacts"])
        artifacts = self.client.get(
            "/api/runs/%s/artifacts" % job["job_id"]
        ).json()["artifacts"]
        paths = {item["path"] for item in artifacts}
        self.assertIn("task-report.md", paths)
        self.assertNotIn("paper.md", paths)

    def test_runtime_can_execute_s5_and_expose_run_artifacts(self):
        created = self.client.post(
            "/api/runs",
            json={
                "topic": "ChemLab runtime integration",
                "language": "en",
                "venue_type": "en_conference",
                "run_dataset": "chemlab",
                "run_seeds": 1,
                "max_sources": 2,
            },
        )
        self.assertEqual(created.status_code, 202)
        job = self._wait(created.json()["job_id"], timeout=60)
        self.assertEqual(job["status"], "completed")
        self.assertIn("run", job["result"]["modules"])
        artifacts = self.client.get(
            "/api/runs/%s/artifacts" % job["job_id"]
        ).json()["artifacts"]
        paths = {item["path"] for item in artifacts}
        self.assertIn("run/run-capsule.json", paths)
        self.assertIn("run/ea.json", paths)

    def test_workspace_registry_memory_and_archive(self):
        agents = self.client.get("/api/workspace/agents")
        self.assertEqual(agents.status_code, 200)
        payload = agents.json()
        self.assertGreaterEqual(payload["count"], 11)
        self.assertIn("literature", {item["id"] for item in payload["agents"]})

        commands = self.client.get("/api/workspace/commands")
        self.assertEqual(commands.status_code, 200)
        self.assertIn(
            "human_gate",
            {item["safety"] for item in commands.json()["commands"]},
        )

        created = self.client.post(
            "/api/workspace/memory",
            json={"text": "pairwise control required", "kind": "constraint", "scope": "S1/perovskite"},
        )
        self.assertEqual(created.status_code, 200)
        entry_id = created.json()["id"]
        listed = self.client.get("/api/workspace/memory").json()
        self.assertEqual(listed["count"], 1)
        self.assertIn("not evidence", listed["boundary"])
        self.assertEqual(self.client.delete("/api/workspace/memory/" + entry_id).status_code, 200)
        self.assertEqual(self.client.delete("/api/workspace/memory/" + entry_id).status_code, 404)

        archive = self.client.post(
            "/api/workspace/archive",
            json={
                "title": "perovskite snapshot",
                "task_id": "perovskite",
                "note": "runtime test",
                "payload": {"task_id": "perovskite", "messages": []},
            },
        )
        self.assertEqual(archive.status_code, 200)
        archive_id = archive.json()["id"]
        self.assertEqual(self.client.get("/api/workspace/archive").json()["count"], 1)
        self.assertEqual(self.client.get("/api/workspace/archive/" + archive_id).status_code, 200)
        self.assertEqual(self.client.delete("/api/workspace/archive/" + archive_id).status_code, 200)
        self.assertEqual(self.client.get("/api/workspace/archive/" + archive_id).status_code, 404)

        secret = self.client.post(
            "/api/workspace/archive",
            json={
                "title": "bad",
                "task_id": "bad",
                "payload": {"api_key": "must-not-persist"},
            },
        )
        self.assertEqual(secret.status_code, 400)
        traversal = self.client.get("/api/workspace/archive/..%2F..%2Fsecret")
        self.assertIn(traversal.status_code, (400, 404))

    def test_workspace_backend_actions(self):
        plan = self.client.post(
            "/api/workspace/actions/automation-plan",
            json={"topic": "perovskite passivation", "max_sources": 8, "run_dataset": "chemlab", "run_seeds": 2},
        )
        self.assertEqual(plan.status_code, 200)
        body = plan.json()
        self.assertTrue(body["fingerprint"].startswith("sha256:"))
        self.assertEqual(body["stop_at"], "S5b")
        self.assertTrue(any(gate["id"] == "G1" for gate in body["human_gates"]))
        self.assertTrue(body["adaptive_literature"]["coverage_plan"])

        literature = self.client.post(
            "/api/workspace/actions/skill",
            json={"skill_id": "literature-brief", "payload": {"question": "perovskite stability", "max_sources": 4}},
        )
        self.assertEqual(literature.status_code, 200)
        self.assertEqual(literature.json()["skill_id"], "literature-brief")
        self.assertIn("brief", literature.json())

        idea = self.client.post(
            "/api/workspace/actions/skill",
            json={
                "skill_id": "hypothesis-triage",
                "payload": {
                    "topic": "stability",
                    "spans": [
                        {"span_id": "S1", "source_id": "A", "section": "Results", "text": "Passivation improves T80 under damp heat."},
                        {"span_id": "S2", "source_id": "A", "section": "Results", "text": "Passivation needs repeated T80 measurement."}
                    ]
                }
            },
        )
        self.assertEqual(idea.status_code, 200)
        self.assertEqual(idea.json()["status"], "candidates_need_human")

        boundary = self.client.post(
            "/api/workspace/actions/skill",
            json={"skill_id": "evidence-boundary", "payload": {"evidence": [{"kind": "claim", "status": "unsigned", "refs": []}]}},
        )
        self.assertEqual(boundary.status_code, 200)
        self.assertEqual(boundary.json()["status"], "blocked")
        self.assertEqual(boundary.json()["counts"]["claims_without_refs"], 1)

        unknown = self.client.post(
            "/api/workspace/actions/skill",
            json={"skill_id": "not-a-skill", "payload": {}},
        )
        self.assertEqual(unknown.status_code, 422)

    def test_orchestrator_and_literature_memory_are_read_only(self):
        topology = self.client.get("/api/orchestrator/topology")
        self.assertEqual(topology.status_code, 200)
        self.assertTrue(topology.json()["template"])
        self.assertEqual(topology.json()["lanes"]["parallel"]["max_workers"], 3)

        plan = self.client.get(
            "/api/orchestrator/plan",
            params={"topic": "perovskite stability", "max_sources": 12, "source": "fixture"},
        )
        self.assertEqual(plan.status_code, 200)
        body = plan.json()
        self.assertEqual(body["blocked_at"], "G1")
        self.assertEqual(sum(group["sources"] for group in body["budget"]["groups"]), 12)
        self.assertIn("SkillCandidate", {item["contract"] for item in body["handoffs"]})

        memory = self.client.get("/api/literature/memory")
        self.assertEqual(memory.status_code, 200)
        self.assertEqual(memory.json()["count"], 0)
        self.assertIn("process memory only", memory.json()["boundary"])

        invalid = self.client.get(
            "/api/orchestrator/plan",
            params={"topic": "perovskite stability", "source": "openalex"},
        )
        self.assertEqual(invalid.status_code, 422)

    def test_skill_usage_is_read_only_evidence(self):
        response = self.client.get("/api/skills/usage")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("entries", payload)
        self.assertIn("capability claim", payload["boundary"])
        versions = self.client.get("/api/skills/versions")
        self.assertEqual(versions.status_code, 200)
        self.assertEqual(versions.json()["active"]["protocol-review"], "1.1.0")

        run = self.client.post(
            "/api/skills/protocol-review/run",
            json={
                "task_id": "TASK-SKILL",
                "payload": {
                    "protocol": {
                        "hypothesis": "h",
                        "baseline": "b",
                        "metric": "m",
                        "seeds": 3,
                        "controls": ["negative"],
                    }
                },
            },
        )
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["result"]["status"], "pass")
        self.assertEqual(run.json()["result"]["skill_version"], "1.1.0")
        self.assertEqual(run.json()["active_version"], "1.1.0")
        self.assertEqual(run.json()["usage"]["skill_id"], "protocol-review")
        self.assertEqual(run.json()["usage"]["version"], "1.1.0")
        self.assertEqual(self.client.get("/api/skills/usage").json()["count"], 1)

        imported = self.client.post(
            "/api/skills/some-imported-skill/run",
            json={"payload": {}},
        )
        self.assertEqual(imported.status_code, 404)

    def test_skill_registry_endpoints_are_catalog_only(self):
        empty = self.client.get("/api/skills")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["count"], 0)
        imported = self.client.post(
            "/api/skills/import",
            json={
                "skills": [
                    {
                        "name": "citation-check",
                        "description": "Check refs",
                        "instructions": "Read refs and check spans.",
                        "tools": ["evidence.inspect", "Bash(git:*)"],
                        "source": "imported",
                    },
                    {
                        "name": "chat-review",
                        "description": "Chat-created review",
                        "instructions": "Review the task.",
                        "tools": ["session.inspect"],
                        "source": "custom",
                        "enabled": True,
                    },
                ]
            },
        )
        self.assertEqual(imported.status_code, 200)
        body = imported.json()
        self.assertEqual(body["accepted"], 2)
        self.assertEqual(body["snapshot"]["count"], 2)
        first = next(item for item in body["snapshot"]["skills"] if item["name"] == "citation-check")
        self.assertTrue(first["untrusted"])
        self.assertEqual(first["execution"], "not_available")
        self.assertIn("shell_capable", first["risk_flags"])

        duplicate = self.client.post(
            "/api/skills/import",
            json={"skills": [{"name": "citation-check", "description": "Check refs", "instructions": "Same."}]},
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json()["accepted"], 0)
        self.assertEqual(len(duplicate.json()["rejected"]), 1)

        toggled = self.client.patch("/api/skills/" + first["id"], json={"enabled": True})
        self.assertEqual(toggled.status_code, 200)
        self.assertTrue(toggled.json()["enabled"])
        self.assertEqual(toggled.json()["execution"], "not_available")

        deleted = self.client.delete("/api/skills/" + first["id"])
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/skills").json()["count"], 1)

        invalid = self.client.post(
            "/api/skills/import",
            json={"skills": [{"name": "bad", "description": "", "instructions": "x"}]},
        )
        self.assertEqual(invalid.status_code, 422)

    def test_custom_agents_and_evolution_policy_are_local_advisory_controls(self):
        created = self.client.post(
            "/api/agents/custom",
            json={
                "name": "覆盖与引用审稿人",
                "role": "reviewer",
                "purpose": "检查全文覆盖与候选引用",
                "checks": ["coverage", "citation"],
                "enabled": True,
            },
        )
        self.assertEqual(created.status_code, 200)
        agent = created.json()
        self.assertTrue(agent["id"].startswith("CAG-"))
        self.assertEqual(agent["stages"], ["S1"])
        self.assertEqual(agent["writes"], [])

        listed = self.client.get("/api/agents/custom")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)

        toggled = self.client.patch(
            "/api/agents/custom/" + agent["id"], json={"enabled": False}
        )
        self.assertEqual(toggled.status_code, 200)
        self.assertFalse(toggled.json()["enabled"])

        plan = self.client.get(
            "/api/orchestrator/plan",
            params={"topic": "perovskite stability", "max_sources": 12, "source": "fixture"},
        )
        self.assertEqual(plan.status_code, 200)
        self.assertIn("evolution_policy", plan.json())
        self.assertNotIn("custom_advisory", plan.json()["lanes"])

        policy = self.client.get("/api/evolution/policy")
        self.assertEqual(policy.status_code, 200)
        self.assertTrue(policy.json()["enabled"])
        self.assertIn("claim.statement", {item["id"] for item in policy.json()["locked"]})

        updated = self.client.post(
            "/api/evolution/policy",
            json={"enabled": False, "scopes": {"literature.memory_order": False}},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()["enabled"])
        self.assertFalse(updated.json()["scopes"][0]["effective"])

        immutable = self.client.post(
            "/api/evolution/policy", json={"scopes": {"claim.statement": True}}
        )
        self.assertEqual(immutable.status_code, 400)

        deleted = self.client.delete("/api/agents/custom/" + agent["id"])
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/agents/custom").json()["count"], 0)

    def test_real_corpus_run_uses_frozen_text(self):
        created = self.client.post(
            "/api/runs",
            json={
                "topic": "self-improving coding agents",
                "real_corpus": True,
                "max_sources": 2,
                "language": "en",
                "venue_type": "en_conference",
            },
        )
        self.assertEqual(created.status_code, 202)
        job = self._wait(created.json()["job_id"])
        self.assertEqual(job["status"], "completed")
        self.assertFalse(job["result"]["fixture_mode"])
        self.assertTrue(any("real-text" in item for item in job["result"]["warnings"]))

    def test_model_registry_is_secret_safe_and_bindings_are_visible(self):
        initial = self.client.get("/api/models")
        self.assertEqual(initial.status_code, 200)
        body = initial.json()
        self.assertFalse(body["security"]["keys_persisted"])
        self.assertIn("openai", {item["provider_id"] for item in body["providers"]})

        key = "sk-runtime-test-secret-987654"
        created = self.client.post("/api/models/providers", json={
            "provider_id": "runtime-test",
            "kind": "openai_compatible",
            "label": "Runtime test",
            "base_url": "http://127.0.0.1:9/v1",
            "api_key_env": "RUNTIME_TEST_KEY",
            "allow_private_network": True,
            "models": ["model-a"],
            "api_key": key,
        })
        self.assertEqual(created.status_code, 200)
        self.assertNotIn(key, created.text)
        provider = next(item for item in created.json()["providers"] if item["provider_id"] == "runtime-test")
        self.assertTrue(provider["configured"])
        self.assertEqual(provider["key_source"], "session")
        self.assertNotEqual(provider["masked_key"], key)

        profile = self.client.post("/api/models/profiles", json={
            "profile_id": "runtime-test-main",
            "provider_id": "runtime-test",
            "model": "model-a",
            "thinking": {"mode": "off"},
            "max_tokens": 2048,
        })
        self.assertEqual(profile.status_code, 200)
        self.assertNotIn(key, profile.text)

        bound = self.client.post("/api/models/bindings", json={
            "module": "rsi", "profile_id": "runtime-test-main",
        })
        self.assertEqual(bound.status_code, 200)
        self.assertEqual(bound.json()["bindings"]["rsi"], "runtime-test-main")
        self.assertTrue(bound.json()["wired"]["rsi"]["wired"])

        cleared = self.client.delete("/api/models/providers/runtime-test/key")
        self.assertEqual(cleared.status_code, 200)
        self.assertNotIn(key, cleared.text)
        provider = next(item for item in cleared.json()["providers"] if item["provider_id"] == "runtime-test")
        self.assertFalse(provider["configured"])

        no_key_probe = self.client.post("/api/models/probe", json={
            "profile_id": "runtime-test-main", "prompt": "hello",
        })
        self.assertEqual(no_key_probe.status_code, 400)
        self.assertNotIn(key, no_key_probe.text)

    def test_runtime_provider_key_can_be_set_without_overwriting_config(self):
        created = self.client.post("/api/models/providers", json={
            "provider_id": "key-only-test",
            "kind": "openai_compatible",
            "label": "Key only",
            "base_url": "http://127.0.0.1:9/v1",
            "api_key_env": "KEY_ONLY_TEST",
            "allow_private_network": True,
            "models": ["model-a"],
        })
        self.assertEqual(created.status_code, 200)
        provider = next(item for item in created.json()["providers"] if item["provider_id"] == "key-only-test")
        self.assertFalse(provider["configured"])

        key = "sk-key-only-secret-456789"
        saved = self.client.post(
            "/api/models/providers/key-only-test/key",
            json={"api_key": key},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertNotIn(key, saved.text)
        provider = next(item for item in saved.json()["providers"] if item["provider_id"] == "key-only-test")
        self.assertTrue(provider["configured"])
        self.assertEqual(provider["key_source"], "session")
        self.assertEqual(provider["base_url"], "http://127.0.0.1:9/v1")
        self.assertEqual(provider["models"], ["model-a"])

        missing = self.client.post(
            "/api/models/providers/not-registered/key",
            json={"api_key": key},
        )
        self.assertEqual(missing.status_code, 404)
        self.assertNotIn(key, missing.text)

        cleared = self.client.delete("/api/models/providers/key-only-test/key")
        self.assertEqual(cleared.status_code, 200)
        provider = next(item for item in cleared.json()["providers"] if item["provider_id"] == "key-only-test")
        self.assertFalse(provider["configured"])

    def test_runtime_bindings_and_session_keys_are_shared_with_jobs(self):
        key = "sk-runtime-shared-secret-123456"
        created = self.client.post("/api/models/providers", json={
            "provider_id": "shared-test",
            "kind": "openai_compatible",
            "label": "Shared test",
            "base_url": "http://127.0.0.1:9/v1",
            "api_key_env": "SHARED_TEST_KEY",
            "allow_private_network": True,
            "models": ["model-a"],
            "api_key": key,
        })
        self.assertEqual(created.status_code, 200)
        profile = self.client.post("/api/models/profiles", json={
            "profile_id": "shared-main",
            "provider_id": "shared-test",
            "model": "model-a",
            "thinking": {"mode": "off"},
            "max_tokens": 2048,
        })
        self.assertEqual(profile.status_code, 200)

        for module in ("literature", "idea", "experiment", "paper", "judge"):
            bound = self.client.post(
                "/api/models/bindings",
                json={"module": module, "profile_id": "shared-main"},
            )
            self.assertEqual(bound.status_code, 200)
        snapshot = self.client.get("/api/models").json()
        self.assertTrue(snapshot["readiness"]["production_ready"])
        self.assertTrue(all(
            snapshot["readiness"]["modules"][module]["key_configured"]
            for module in ("literature", "idea", "experiment", "paper", "judge")
        ))
        self.assertTrue(any(
            "judge shares profile" in item
            for item in snapshot["readiness"]["warnings"]
        ))

        service = self.app.state.model_service
        manager = self.app.state.manager
        self.assertIs(manager.model_gateway, service.gateway)
        provider = service.store.provider("shared-test")
        resolved, source = manager.model_gateway.keys.resolve(provider)
        self.assertEqual(resolved, key)
        self.assertEqual(source, "session")
        tools, _notes = manager._model_tools()
        self.assertIsNotNone(tools["idea"])
        self.assertIsNotNone(tools["experiment"])
        self.assertIsNotNone(tools["judge"])
        self.assertIsNotNone(tools["planner"])
        self.assertIsNotNone(tools["writer"])

    def test_signer_snapshot_is_read_only_and_masked(self):
        initial = self.client.get("/api/signers")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["count"], 0)
        signer = self.app.state.signers.create("PI")
        listed = self.client.get("/api/signers")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)
        self.assertEqual(listed.json()["signers"][0]["signer_id"], signer["signer_id"])
        self.assertNotIn("secret_hex", listed.text)
        self.assertEqual(self.client.post("/api/signers", json={}).status_code, 405)

    def test_model_provider_rejects_cleartext_public_url(self):
        response = self.client.post("/api/models/providers", json={
            "provider_id": "bad",
            "kind": "openai_compatible",
            "base_url": "http://example.com/v1",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("cleartext", response.json()["detail"])

    def test_rsi_status_is_read_only_and_path_limited(self):
        ledger_path = self.rsi_root / "ledger.json"
        ledger = StepLedger(ledger_path)
        controller = RSIController(ledger)
        controller.propose(
            Candidate(
                kind="process",
                target="literature.retrieval.budget",
                patch='{"retriever": "minilm", "max_sources": 3}',
                rationale="runtime read test",
                predicted_effect="lower cost",
                scope="S1/runtime-test",
            ),
            dry_run_ref="DRY-RUNTIME",
        )
        status = self.client.get("/api/rsi/status", params={"ledger": str(ledger_path)})
        self.assertEqual(status.status_code, 200)
        body = status.json()
        self.assertTrue(body["read_only"])
        self.assertEqual(body["episodes"], 1)
        self.assertEqual(body["capability_claims"], [])

        story = self.client.get("/api/rsi/story", params={"ledger": str(ledger_path)})
        self.assertEqual(story.status_code, 200)
        self.assertTrue(story.json()["read_only"])
        self.assertIn("timeline", story.json())
        self.assertGreaterEqual(len(story.json()["episodes"]), 1)

        listed = self.client.get("/api/rsi/ledgers")
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(any(item["path"].endswith("ledger.json") for item in listed.json()["ledgers"]))

        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        blocked = self.client.get("/api/rsi/status", params={"ledger": str(outside)})
        self.assertEqual(blocked.status_code, 403)


if __name__ == "__main__":
    unittest.main()
