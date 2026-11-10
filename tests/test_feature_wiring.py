import re
import tempfile
import unittest
from pathlib import Path

from research_agent.runtime.app import create_app
from research_agent.runtime.jobs import RuntimeSettings


class FeatureWiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[1]
        cls.web = cls.repo / "apps" / "web" / "src"

    def _settings(self, root: Path) -> RuntimeSettings:
        return RuntimeSettings(
            repo_root=self.repo,
            jobs_root=root / "jobs",
            allowed_rsi_roots=[],
            model_store_path=root / "models.json",
            workspace_memory_path=root / "memory.json",
            workspace_archive_root=root / "archive",
            literature_memory_path=root / "literature-memory.json",
            custom_agents_path=root / "agents.json",
            evolution_policy_path=root / "policy.json",
            skill_registry_path=root / "skills.json",
        )

    def test_runtime_exposes_run_model_and_workspace_routes_without_signing(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(self._settings(Path(tmp)))
            paths = {route.path for route in app.routes}
        required = {
            "/api/health",
            "/api/runs",
            "/api/runs/{job_id}",
            "/api/runs/{job_id}/events",
            "/api/runs/{job_id}/artifacts",
            "/api/models",
            "/api/models/calls",
            "/api/skills",
            "/api/workspace/memory",
            "/api/workspace/archive",
            "/api/orchestrator/plan",
            "/api/rsi/story",
        }
        self.assertTrue(required <= paths, "missing routes: %s" % sorted(required - paths))
        forbidden = {
            path for path in paths
            if path.endswith(("/approve", "/claim", "/sign"))
        }
        self.assertEqual(forbidden, set(), "runtime must not expose human signing")

    def test_frontend_api_surface_matches_runtime_contract(self):
        source = (self.web / "adapters" / "runtimeApi.ts").read_text(encoding="utf-8")
        exports = set(re.findall(r"export async function (\w+)", source))
        required = {
            "probeRuntime",
            "loadRuns",
            "createRun",
            "getRun",
            "loadRunEvents",
            "loadRunArtifacts",
            "loadRunArtifactJson",
            "loadModelCalls",
            "loadRuntimeSkills",
            "loadRuntimeMemory",
            "loadRuntimeArchive",
            "loadCustomAgents",
        }
        self.assertTrue(required <= exports, "missing API bridges: %s" % sorted(required - exports))
        for endpoint in (
            "/api/runs",
            "/api/models/calls",
            "/api/skills",
            "/api/workspace/memory",
            "/api/workspace/archive",
            "/api/agents/custom",
        ):
            self.assertIn(endpoint, source)
        self.assertNotRegex(source, r"fetch\([^\n]*/api/(approve|claim|sign)")

    def test_key_features_are_connected_to_their_actual_source(self):
        usage = (self.web / "components" / "settings" / "UsageStats.tsx").read_text(encoding="utf-8")
        runtime = (self.web / "components" / "settings" / "WorkspaceSettings.tsx").read_text(encoding="utf-8")
        skills = (self.web / "components" / "SkillsDrawer.tsx").read_text(encoding="utf-8")
        store = (self.web / "state" / "workspaceStore.ts").read_text(encoding="utf-8")
        snapshot = (self.web / "domain" / "runtimeSnapshot.ts").read_text(encoding="utf-8")

        self.assertIn("loadModelCalls", usage)
        self.assertIn("loadRuns", runtime)
        self.assertIn("loadRuntimeSkills", skills)
        self.assertIn("loadSkillUsage", skills)
        self.assertIn("loadRunEvents", store)
        self.assertIn("applyRuntimeSnapshot", store)
        self.assertIn("startLiveRun", store)
        self.assertIn("gates", snapshot)
        self.assertIn("claim", snapshot)
        self.assertIn("coverage", snapshot)

    def test_pipeline_feature_chain_is_statically_present(self):
        pipeline = (self.repo / "research_agent" / "pipeline.py").read_text(encoding="utf-8")
        paper = (self.repo / "research_agent" / "modules" / "paper.py").read_text(encoding="utf-8")
        run = (self.repo / "research_agent" / "modules" / "run.py").read_text(encoding="utf-8")
        closure = (self.repo / "research_agent" / "closure.py").read_text(encoding="utf-8")

        self.assertIn('"paper.md"', pipeline)
        self.assertIn('"report.md"', pipeline)
        self.assertIn("section_writer=self.section_writer", pipeline)
        self.assertIn("claim_assertions", pipeline)
        self.assertIn("claim_assertions", paper)
        self.assertIn("verify_claim_assertions", run)
        self.assertIn("claim_assertions", closure)
        self.assertIn("run_capsule_artifact", closure)

        app_source = (self.repo / "research_agent" / "runtime" / "app.py").read_text(encoding="utf-8")
        jobs_source = (self.repo / "research_agent" / "runtime" / "jobs.py").read_text(encoding="utf-8")
        task_agent = (self.repo / "research_agent" / "task_agent.py").read_text(encoding="utf-8")
        context = (self.web / "components" / "ContextPanel.tsx").read_text(encoding="utf-8")
        self.assertIn("task_type", app_source)
        self.assertIn("TaskAgent", jobs_source)
        self.assertIn("class TaskRouter", task_agent)
        self.assertIn("runtimeTaskType", context)
        self.assertIn("actions.startLiveRun(", context)
        self.assertIn("runtimeFlowMode", context)
        self.assertIn("runDataset", context)
        self.assertIn("g1DecisionFile", context)
        self.assertIn("bibliographyFile", context)
        self.assertIn("runDir", context)
        self.assertIn("本地全文", context)
        local = (self.repo / "research_agent" / "adapters" / "local_document_retriever.py").read_text(encoding="utf-8")
        self.assertIn("class LocalDocumentRetriever", local)
        self.assertIn("page", local)
        self.assertIn("local_corpus", app_source)
        skill_lab = (self.repo / "research_agent" / "skill_lab.py").read_text(encoding="utf-8")
        self.assertIn("class SkillUsageStore", skill_lab)
        self.assertIn("class SkillLab", skill_lab)
        self.assertIn("/api/skills/usage", app_source)
        self.assertIn("SkillUsageStore", app_source)

    def test_no_component_bypasses_runtime_api_adapter(self):
        offenders = []
        for path in self.web.rglob("*"):
            if path.suffix not in (".ts", ".tsx"):
                continue
            if path.name in ("runtimeApi.ts", "modelRuntime.ts"):
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"fetch\([^\n]*['\"]/?api/", text):
                offenders.append(str(path.relative_to(self.repo)))
        self.assertEqual(offenders, [], "direct /api fetch outside adapters: %s" % offenders)


if __name__ == "__main__":
    unittest.main()
