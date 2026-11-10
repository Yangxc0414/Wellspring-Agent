import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "verify_innovation_claims", ROOT / "scripts/verify-innovation-claims.py"
)
verify = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verify)


class InnovationClaimsTest(unittest.TestCase):
    def test_every_innovation_claim_binds_a_repository_check(self):
        data = json.loads(verify.SOURCE.read_text(encoding="utf-8"))
        self.assertTrue(data.get("pillars"))
        for pillar in data["pillars"]:
            checks = pillar.get("checks") or []
            self.assertTrue(checks, "pillar has no repository checks: " + pillar["id"])
            for check in checks:
                self.assertTrue(
                    verify.run_check(check),
                    "%s / %s no longer resolves: %s"
                    % (pillar["id"], check.get("label"), check.get("path")),
                )


if __name__ == "__main__":
    unittest.main()
