import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "apps" / "web" / "src" / "domain" / "seed.ts"
STORE = ROOT / "apps" / "web" / "src" / "state" / "workspaceStore.ts"


class SeedEseReplayTest(unittest.TestCase):
    def test_task_is_seeded_with_real_numbers(self):
        text = SEED.read_text(encoding="utf-8")
        self.assertIn('id: "ese-ms-20261118-03"', text)
        self.assertIn("ESE：缺陷修复更常触碰测试？", text)
        self.assertIn('workspaceId: "thesis"', text)
        self.assertIn('status: "blocked"', text)
        self.assertIn("0.3749", text)
        self.assertIn("-0.0067", text)

    def test_replay_never_claims_a_signature(self):
        text = SEED.read_text(encoding="utf-8")
        self.assertIn("claim / closure / signature 仍未人签", text)
        self.assertIn("Claim · 待人工", text)
        self.assertIn("Signature · 待人工", text)

    def test_persisted_workspace_gets_the_replay_once(self):
        text = STORE.read_text(encoding="utf-8")
        self.assertIn("ESE_REPLAY_TASK_ID", text)
        self.assertIn("ensureSeedEseTask", text)
        self.assertIn("archivedTaskIds", text)


if __name__ == "__main__":
    unittest.main()
