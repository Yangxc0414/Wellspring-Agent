"""Grant scaffold: a blank applicant workflow, then a deterministic audit."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.cli import main
from research_agent.modules.grant import SCHEMES, GrantError, grant_template


class GrantTemplateTest(unittest.TestCase):
    def test_nsfc_template_contains_the_required_modules_and_is_blank(self):
        data = grant_template("nsfc")
        self.assertEqual(data["scheme"], "nsfc")
        self.assertEqual(list(data["sections"]), SCHEMES["nsfc"]["modules"])
        self.assertTrue(all(value == "" for value in data["sections"].values()))
        self.assertFalse(data["ai_statement"])

    def test_nssfc_template_starts_anonymous(self):
        data = grant_template("nssfc")
        self.assertTrue(data["anonymous"])
        self.assertTrue(data["identity_removed"])

    def test_unknown_scheme_is_refused(self):
        with self.assertRaises(GrantError):
            grant_template("unknown")

    def test_cli_template_then_venue_audit_blocks_the_blank_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "grant.json"
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["grant", "template", "--scheme", "nsfc", "--output", str(path)])
            self.assertEqual(code, 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(list(data["sections"]), SCHEMES["nsfc"]["modules"])

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([
                    "venue", "audit", "--kind", "grant", "--scheme", "nsfc", "--file", str(path)
                ])
            self.assertEqual(code, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["submission_ready"])
            self.assertTrue(any(item.startswith("module.") for item in result["blockers"]))


if __name__ == "__main__":
    unittest.main()
