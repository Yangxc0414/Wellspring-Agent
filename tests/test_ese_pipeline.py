"""ESE pipeline mode: advisory method check over the S4 design (no gate)."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent import cli  # noqa: E402
from research_agent.method_registry import get_method  # noqa: E402


def _payload_satisfying(method_id):
    payload = {}
    for rule in get_method(method_id)["checks"]:
        for field in rule["requires"]:
            node = payload
            parts = field.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = "x"
    return payload


class EsePipelineMethodTest(unittest.TestCase):
    def test_empty_design_reports_missing_protocol_fields(self):
        report = cli._ese_method_report("repository-mining", {})
        self.assertEqual(report["method"], "repository-mining")
        self.assertEqual(report["stage"], "S4")
        self.assertTrue(report["missing"])
        self.assertIn("advisory", report["boundary"])

    def test_satisfied_design_has_no_missing_fields(self):
        payload = _payload_satisfying("repository-mining")
        report = cli._ese_method_report("repository-mining", payload)
        self.assertEqual(report["missing"], [])

    def test_unknown_method_is_a_clear_error(self):
        with self.assertRaises(SystemExit) as context:
            cli._ese_method_report("not-a-method", {})
        self.assertIn("unknown method", str(context.exception))

    def test_report_is_serialisable(self):
        import json

        report = cli._ese_method_report("case-study", {"hypothesis": "h"})
        text = json.dumps(report, ensure_ascii=False)
        self.assertIn("case-study", text)


if __name__ == "__main__":
    unittest.main()
