import unittest

from research_agent.design_audit import audit_design


def complete_design():
    return {
        "hypothesis": "钝化层延长湿热稳定性",
        "baseline": "未钝化对照，随机划分为训练/验证/测试",
        "primary_metric": "T80",
        "controls": ["未钝化", "单分子钝化"],
        "seeds": 3,
        "budget": "3 seeds x 5 folds; power=0.8; effect size=0.2; 95% CI",
        "stopping_rule": "预设停止；多重比较用 FDR 校正；缺失数据按预设排除；敏感性分析",
    }


class DesignAuditTest(unittest.TestCase):
    def test_complete_design_is_ready_for_human_g2(self):
        report = audit_design(complete_design())
        self.assertEqual(report["status"], "ready_for_g2")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["warnings"], [])

    def test_missing_required_fields_are_incomplete(self):
        report = audit_design(
            {
                "hypothesis": "",
                "baseline": "",
                "primary_metric": "",
                "controls": [],
                "seeds": 1,
                "budget": "",
                "stopping_rule": "",
            }
        )
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(report["blockers"])
        joined = " ".join(report["blockers"])
        self.assertIn("design.required", joined)
        self.assertIn("design.controls", joined)
        self.assertIn("design.seeds", joined)

    def test_missing_statistical_elements_are_attention(self):
        report = audit_design(
            {
                "hypothesis": "h",
                "baseline": "control",
                "primary_metric": "accuracy",
                "controls": ["control"],
                "seeds": 3,
                "budget": "three repeated runs",
                "stopping_rule": "stop after the fixed budget",
            }
        )
        self.assertEqual(report["status"], "attention")
        self.assertFalse(report["blockers"])
        self.assertTrue(any("design.statistics" in item for item in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
