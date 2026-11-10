"""The runtime's write guard: default-deny, one rule, and a proof it covers every route.

The defect these tests pin down was structural, not a typo: the credential check was applied by
hand inside 4 of 59 route handlers, so the writes that mattered most (model API keys, model
bindings, host-model answers) were reachable unauthenticated whenever the runtime was bound
off-loopback with --allow-remote. A per-route guard cannot be trusted to scale, so the rule now
lives in one pure function plus a middleware, and one test below enumerates the live route table
to prove nothing is exempt.
"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from research_agent.runtime.app import (
    MUTATING_METHODS,
    credential_problem,
    create_app,
    remote_bind_problem,
)
from research_agent.runtime.jobs import default_settings


def _settings(root: Path, token: str = ""):
    settings = default_settings()
    settings.repo_root = root
    settings.jobs_root = root / "jobs"
    settings.workspace_memory_path = root / "workspace_memory.json"
    settings.workspace_archive_root = root / "archive"
    settings.literature_memory_path = root / "memory.json"
    settings.custom_agents_path = root / "custom_agents.json"
    settings.evolution_policy_path = root / "evolution_policy.json"
    settings.skill_registry_path = root / "skills.json"
    settings.model_store_path = root / "model_gateway.json"
    settings.host_model_ledger_path = root / "host-model" / "turns.json"
    settings.research_api_root = root / "research-root"
    settings.research_api_root.mkdir(parents=True, exist_ok=True)
    settings.research_api_token = token
    return settings


class CredentialRuleTest(unittest.TestCase):
    """One rule, tested without a socket: the middleware and the route guard share it."""

    def test_no_token_means_loopback_only(self):
        self.assertIsNone(credential_problem("127.0.0.1", "", ""))
        self.assertIsNone(credential_problem("testclient", "", ""))
        status, detail = credential_problem("192.168.1.5", "", "")
        self.assertEqual(status, 403)
        self.assertIn("loopback-only", detail)

    def test_a_token_must_match_exactly(self):
        self.assertEqual(credential_problem("127.0.0.1", "secret", "")[0], 401)
        self.assertEqual(credential_problem("127.0.0.1", "secret", "Bearer wrong")[0], 401)
        self.assertEqual(credential_problem("127.0.0.1", "secret", "secret")[0], 401)
        self.assertIsNone(credential_problem("127.0.0.1", "secret", "Bearer secret"))

    def test_a_token_set_but_padded_still_matches(self):
        self.assertIsNone(credential_problem("10.0.0.9", "  secret  ", "Bearer secret"))

    def test_a_missing_client_host_is_not_loopback(self):
        self.assertEqual(credential_problem("", "", "")[0], 403)


class RemoteBindRuleTest(unittest.TestCase):
    """--allow-remote is only safe together with a token; the refusal says why."""

    def test_loopback_needs_neither_flag_nor_token(self):
        self.assertEqual(remote_bind_problem("127.0.0.1", False, ""), "")

    def test_non_loopback_without_the_flag_is_refused(self):
        self.assertIn("--allow-remote", remote_bind_problem("0.0.0.0", False, ""))

    def test_non_loopback_with_the_flag_but_no_token_is_refused(self):
        reason = remote_bind_problem("0.0.0.0", True, "")
        self.assertIn("RESEARCH_AGENT_API_TOKEN", reason)
        self.assertIn("model keys", reason)

    def test_non_loopback_with_flag_and_token_is_allowed(self):
        self.assertEqual(remote_bind_problem("0.0.0.0", True, "secret"), "")


class WriteGuardHttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_stay_open_while_writes_need_the_token(self):
        app = create_app(_settings(self.root, token="test-secret"))
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/health").status_code, 200)
            self.assertEqual(client.get("/api/research/capabilities").status_code, 401)

            refused = client.post("/api/models/providers/p1/key", json={"api_key": "k"})
            self.assertEqual(refused.status_code, 401)
            body = refused.json()
            self.assertEqual(body["route"], "/api/models/providers/p1/key")
            self.assertEqual(body["method"], "POST")
            self.assertIn("mutating", body["boundary"])

            admitted = client.post(
                "/api/models/providers/p1/key",
                headers={"Authorization": "Bearer test-secret"},
                json={"api_key": "k"},
            )
            self.assertNotEqual(admitted.status_code, 401)

    def test_a_previously_unguarded_write_is_now_guarded(self):
        # This is the regression that the hand-applied guard let through: answering a host-model
        # turn is how a suspended stage gets its text, and it used to need no credential.
        app = create_app(_settings(self.root, token="test-secret"))
        with TestClient(app) as client:
            for path, payload in (
                ("/api/host-model/respond", {"turn_id": "MT-x", "text": "t"}),
                ("/api/host-model/void", {"turn_id": "MT-x"}),
                ("/api/models/bindings", {"module": "idea", "profile_id": "p1"}),
            ):
                self.assertEqual(client.post(path, json=payload).status_code, 401, path)

    def test_loopback_writes_still_work_without_a_token(self):
        app = create_app(_settings(self.root))
        with TestClient(app) as client:
            response = client.post("/api/host-model/void", json={"turn_id": "MT-missing"})
            self.assertNotIn(response.status_code, (401, 403))

    def test_every_mutating_route_is_covered_by_the_middleware(self):
        """Enumerate the live route table: no mutating route may be exempt.

        A middleware is only default-deny if this holds for routes added later too, so the test
        derives its list from the app instead of naming routes the author remembered.
        """
        app = create_app(_settings(self.root, token="test-secret"))
        checked = 0
        with TestClient(app) as client:
            for route in app.routes:
                methods = set(getattr(route, "methods", None) or ())
                path = getattr(route, "path", "")
                for method in sorted(methods.intersection(MUTATING_METHODS)):
                    concrete = "".join(
                        "/x" if part.startswith("{") else "/" + part
                        for part in path.strip("/").split("/")
                    ) or "/"
                    response = client.request(method, concrete, json={})
                    self.assertEqual(
                        response.status_code, 401,
                        "%s %s was not guarded by the write middleware" % (method, path),
                    )
                    checked += 1
        self.assertGreater(checked, 10, "the route table shrank; the enumeration is not testing anything")


if __name__ == "__main__":
    unittest.main()
