import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
COMP = (WEB / "components" / "FlowDemo.tsx").read_text(encoding="utf-8")
PANEL = (WEB / "components" / "ContextPanel.tsx").read_text(encoding="utf-8")
TYPES = (WEB / "domain" / "types.ts").read_text(encoding="utf-8")
STORE = (WEB / "state" / "workspaceStore.ts").read_text(encoding="utf-8")


class FlowDemoTest(unittest.TestCase):
    def test_registered_as_default_tab(self):
        self.assertIn('"ese" | "flow"', TYPES)
        self.assertIn('{ id: "flow", label: "演示流程" }', PANEL)
        self.assertIn('tab === "flow" && <FlowDemo key={task.id} />', PANEL)
        self.assertIn('contextTab: "flow"', STORE)

    def test_demo_never_writes_or_fakes_a_signature(self):
        # the whole demo is local React state; it must never touch disk
        self.assertIn("useState", COMP)
        self.assertIn("no signature.json is produced", COMP)
        self.assertIn("刷新页面即回到待签", COMP)
        self.assertIn("不会生成真实", COMP)
        self.assertIn("页面不代签", COMP)

    def test_sign_gate_requires_reaching_evidence_stage(self):
        self.assertIn("const SIGN_STEP = 5", COMP)
        self.assertIn("if (step < SIGN_STEP || signed) return", COMP)
        self.assertIn("disabled={step < SIGN_STEP || signed}", COMP)

    def test_all_nine_stages_are_present(self):
        for stage in (
            "文献检索",
            "假设收敛",
            "设计冻结",
            "复现执行",
            "证据判定",
            "结果图",
            "写作槽位",
            "闭包检查",
            "自改进提案",
        ):
            self.assertIn(stage, COMP)

    def test_pending_and_signed_states_both_exist(self):
        self.assertIn("待签 · 第 ${step}/${STAGES.length} 步", COMP)
        self.assertIn("已签 · DEMO", COMP)
        self.assertIn("4/5 · 断言待人工", COMP)
        self.assertIn("5/5 · DEMO SIGNED", COMP)

    def test_signed_state_lights_chain_and_slots(self):
        self.assertIn("effectiveStep = signed ? 8 : step", COMP)
        self.assertIn("const lit = effectiveStep >= node.need", COMP)
        self.assertIn("signed && slot.need <= 8", COMP)


if __name__ == "__main__":
    unittest.main()
