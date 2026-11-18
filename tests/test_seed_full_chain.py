import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "apps" / "web" / "src" / "domain" / "seed.ts"
STORE = ROOT / "apps" / "web" / "src" / "state" / "workspaceStore.ts"


class SeedFullChainReplayTest(unittest.TestCase):
    def test_full_chain_task_is_seeded_and_default(self):
        text = SEED.read_text(encoding="utf-8")
        self.assertIn('id: "full-chain-demo"', text)
        self.assertIn("完整闭环：从检索到自改进", text)
        self.assertIn('selectedTaskId: "full-chain-demo"', text)
        self.assertIn("seedFullChainDemo(),", text)

    def test_full_chain_covers_every_stage(self):
        text = SEED.read_text(encoding="utf-8")
        # the demo must walk S1 survey -> G1 -> G2 -> S5 -> S5b -> writing -> G5 -> META
        for marker in (
            "S1 检索完成",
            "S2–S3：从 gap 到候选假设",
            "G1 已收敛",
            "S4：设计冻结（预注册）",
            "G2 已冻结",
            "S5a 执行完成",
            "S5b：证据判定",
            "S8–S12 写作槽位",
            "结论待人签",
            "META 自改进提案",
        ):
            self.assertIn(marker, text)

    def test_full_chain_never_fakes_a_signature(self):
        text = SEED.read_text(encoding="utf-8")
        self.assertIn("不产生真实签名", text)
        self.assertIn("断言 · 待人工", text)
        self.assertIn("签名只能在本地 CLI 产生，网页不代签", text)
        self.assertIn('gate: "G5"', text)
        self.assertIn('status: "blocked"', text)

    def test_full_chain_states_the_governance_boundaries(self):
        text = SEED.read_text(encoding="utf-8")
        self.assertIn("不训练模型权重", text)
        self.assertIn("单题参数不上长为通用默认", text)
        self.assertIn("新版本不追认旧结果", text)

    def test_persisted_workspace_gets_full_chain_once(self):
        text = STORE.read_text(encoding="utf-8")
        self.assertIn("FULL_CHAIN_TASK_ID", text)
        self.assertIn("ensureSeedFullChainDemo", text)
        self.assertIn("archivedTaskIds", text)


if __name__ == "__main__":
    unittest.main()
