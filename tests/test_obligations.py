import tempfile
import unittest
from pathlib import Path

from research_agent.obligations import ObligationLedger


def report(report_id, blocked=True):
    checks = [
        {"name": "all_slots_bound", "status": "fail" if blocked else "pass", "detail": "unresolved=['limitation']" if blocked else "unresolved=[]"},
        {"name": "claim_supported", "status": "pass", "detail": "ok"},
    ]
    return {
        "report_id": report_id,
        "status": "blocked" if blocked else "ready",
        "checks": checks,
        "unresolved": ["limitation"] if blocked else [],
    }


class ObligationLedgerTest(unittest.TestCase):
    def test_missing_from_report_is_not_auto_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "obligations.json"
            ledger = ObligationLedger(path)
            first = ledger.reconcile(report("CLR-1"))
            self.assertEqual(first["summary"]["open"], 2)
            second = ledger.reconcile(report("CLR-2", blocked=False))
            self.assertEqual(second["summary"]["open"], 0)
            self.assertEqual(second["summary"]["unverified_disappearance"], 2)
            self.assertEqual(second["summary"]["resolved"], 0)
            self.assertEqual(second["summary"]["status"], "blocked")
            for item in second["obligations"]:
                self.assertEqual(item["status"], "unverified_disappearance")
                self.assertNotIn("resolution_evidence_sha256", item)

    def test_explicit_resolve_requires_reason_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "obligations.json"
            ledger = ObligationLedger(path)
            first = ledger.reconcile(report("CLR-1"))
            obligation_id = first["obligations"][0]["obligation_id"]
            with self.assertRaises(ValueError):
                ledger.resolve(obligation_id, "short", None)
            evidence = Path(tmp) / "fix.json"
            evidence.write_text('{"fixed": true}', encoding="utf-8")
            resolved = ledger.resolve(obligation_id, "restored limitation slot", evidence)
            self.assertEqual(resolved["obligation"]["status"], "resolved")
            self.assertEqual(resolved["obligation"]["resolution_kind"], "resolve")
            self.assertEqual(len(resolved["obligation"]["resolution_evidence_sha256"]), 64)
            self.assertEqual(resolved["summary"]["resolved"], 1)
            self.assertEqual(resolved["summary"]["status"], "blocked")

            second_id = first["obligations"][1]["obligation_id"]
            waived = ledger.waive(second_id, "limitation accepted for internal draft")
            self.assertEqual(waived["obligation"]["status"], "waived")
            self.assertEqual(waived["summary"]["waived"], 1)
            self.assertEqual(waived["summary"]["status"], "clear")

    def test_resolve_rejects_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "obligations.json"
            ledger = ObligationLedger(path)
            first = ledger.reconcile(report("CLR-1"))
            obligation_id = first["obligations"][0]["obligation_id"]
            with self.assertRaises(ValueError):
                ledger.resolve(obligation_id, "fixed the report path", None)

    def test_reappearance_reopens_and_history_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "obligations.json"
            evidence = Path(tmp) / "fix.txt"
            evidence.write_text("fixed", encoding="utf-8")
            ledger = ObligationLedger(path)
            first = ledger.reconcile(report("CLR-A", blocked=True))
            for item in first["obligations"]:
                ledger.resolve(
                    item["obligation_id"],
                    "explicitly fixed with evidence",
                    evidence,
                )
            reopened = ObligationLedger(path).reconcile(report("CLR-B", blocked=True))
            self.assertEqual(reopened["summary"]["reopened"], 2)
            self.assertEqual(reopened["summary"]["resolved"], 0)
            self.assertEqual(reopened["summary"]["status"], "blocked")
            self.assertEqual(len(reopened["obligations"]), 2)
            for item in reopened["obligations"]:
                self.assertEqual(item["status"], "reopened")
                self.assertGreaterEqual(len(item["history"]), 2)

    def test_ledger_never_deletes_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "obligations.json"
            evidence = Path(tmp) / "fix.txt"
            evidence.write_text("fixed", encoding="utf-8")
            ledger = ObligationLedger(path)
            first = ledger.reconcile(report("CLR-1"))
            for item in first["obligations"]:
                ledger.waive(item["obligation_id"], "accepted by the author")
            final = ObligationLedger(path).reconcile(report("CLR-2", blocked=False))
            self.assertEqual(len(final["obligations"]), 2)
            self.assertEqual(final["summary"]["unverified_disappearance"], 0)
            self.assertEqual(final["summary"]["waived"], 2)
            self.assertEqual(final["summary"]["status"], "clear")


if __name__ == "__main__":
    unittest.main()
