"""The projection contract: gaps must be listable, and the audit chain must actually fill them.

Two failure modes are pinned here, both of which the first implementation of the inventory had:

* A rollup that only upgrades slots it has already seen drops the slots nobody declared, so
  `absent_slots` reads empty and an incomplete projection looks compliant. Conservation is asserted
  per slot (the four states must sum to the schema count) and a known-incomplete projection is
  required to list its gaps.
* A scan that treats any dict with a `schema_version` key as a projection counted this module's own
  documentation table as one, and reported it complete. Schema ids must match the repo's shape.

Compliance is a ratchet, not a blanket gate: only the signing/audit-chain projections are asserted
complete, because failing on all 171 at once would just get the test deleted.
"""

import re
import tempfile
import unittest
from pathlib import Path

from research_agent.paths import build_info
from research_agent.projections import (
    ABSENT,
    ALIASED,
    CONTRACT_SLOTS,
    ELSEWHERE,
    IN_LITERAL,
    contract_slots,
    projection_inventory,
)
from research_agent.rsi import Candidate, RSIController, StepLedger, ledger_story
from research_agent.skill_packs import coverage_report

SHAPE = re.compile(r"^[a-z0-9][a-z0-9._-]*-[0-9]+\.[0-9]+$")
ADOPTED = (
    "rsi-story-0.4",
    "skill-pack-coverage-0.4",
    "study-brief-0.4",
    "study-package-manifest-0.3",
    "projection-inventory-0.1",
    "projection-contract-0.1",
)


class InventoryShapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = projection_inventory()

    def test_it_enumerates_the_population_instead_of_naming_it(self):
        self.assertGreater(self.report["schemas"], 100)
        self.assertGreater(self.report["modules_scanned"], 100)
        self.assertGreaterEqual(self.report["occurrences"], self.report["schemas"])

    def test_every_schema_id_has_the_repo_shape(self):
        for name in self.report["complete"] + [row["schema"] for row in self.report["rows"]]:
            self.assertTrue(SHAPE.match(name), "not a schema id: %r" % name)
        # the regression: this module's SLOT_MEANING table was once read as a projection
        self.assertNotIn("which shape this is", " ".join(row["schema"] for row in self.report["rows"]))

    def test_slot_states_are_one_of_the_four_declared_values(self):
        allowed = {IN_LITERAL, ALIASED, ELSEWHERE, ABSENT}
        for row in self.report["rows"]:
            for slot in CONTRACT_SLOTS:
                self.assertIn(row["slots"][slot], allowed)

    def test_the_four_states_conserve_the_population_for_every_slot(self):
        for slot, counts in self.report["slot_coverage"].items():
            total = counts[IN_LITERAL] + counts[ALIASED] + counts[ELSEWHERE] + counts[ABSENT]
            self.assertEqual(total, self.report["schemas"], slot)

    def test_a_known_incomplete_projection_lists_its_gaps(self):
        rows = {row["schema"]: row for row in self.report["rows"]}
        signature = rows.get("closure-signature-0.2")
        self.assertIsNotNone(signature, "the signing projection left the inventory")
        self.assertIn("generated_at", signature["absent_slots"])
        self.assertFalse(signature["complete"])

    def test_the_inventory_itself_satisfies_the_contract(self):
        for slot in CONTRACT_SLOTS:
            self.assertIn(slot, self.report)
        self.assertTrue(self.report["read_only"])
        self.assertEqual(self.report["source_fingerprint"], build_info()["fingerprint"])
        self.assertIn("dict literals", self.report["base"])


class AdoptionRatchetTest(unittest.TestCase):
    """The audit/signing chain is asserted complete; everything else is reported, not failed."""

    def test_the_adopted_projections_are_complete_in_the_static_scan(self):
        report = projection_inventory()
        missing = [name for name in ADOPTED if name not in report["complete"]]
        self.assertEqual(missing, [], "these projections stopped filling a contract slot")

    def test_the_contract_states_its_own_slots(self):
        contract = contract_slots()
        self.assertEqual(contract["slots"], list(CONTRACT_SLOTS))
        for slot in CONTRACT_SLOTS:
            self.assertIn(slot, contract["slot_meaning"])


class RuntimeSlotTest(unittest.TestCase):
    """Static compliance is not enough: the returned object must carry real values."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "rsi-ledger.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_story_carries_a_fingerprint_a_base_and_provenance(self):
        controller = RSIController(StepLedger(self.path))
        controller.propose(
            Candidate(
                kind="skill", target="literature.query_planner", patch="p", rationale="r",
                predicted_effect="e", predicted_metrics={"recall": 0.8}, parent_id="incumbent",
                scope="S1/zh",
            ),
            dry_run_ref="DRY-001",
        )
        story = ledger_story(StepLedger.load(self.path))
        self.assertEqual(story["schema_version"], "rsi-story-0.4")
        self.assertEqual(story["source_fingerprint"], build_info()["fingerprint"])
        self.assertTrue(story["read_only"])
        self.assertIn("1 episode", story["base"])
        self.assertEqual(story["provenance"]["simulation_episodes"], 0)
        self.assertTrue(story["generated_at"])

    def test_the_coverage_report_carries_the_same_slots(self):
        report = coverage_report(
            [{"text": "Report uncertainty and variance", "stage": "design", "actionable": True,
              "source": "s", "heading": "h"}],
            "we report uncertainty and variance",
            stage="design",
        )
        self.assertEqual(report["schema_version"], "skill-pack-coverage-0.4")
        self.assertEqual(report["source_fingerprint"], build_info()["fingerprint"])
        self.assertTrue(report["read_only"])
        self.assertIn("scored items", report["base"])
        self.assertIn("artifact_language", report["provenance"])
        self.assertTrue(report["generated_at"])

    def test_the_slots_are_disclosure_only_and_move_no_number(self):
        items = [{"text": "Report uncertainty and variance", "stage": "design",
                  "actionable": True, "source": "s", "heading": "h"}]
        text = "we report uncertainty and variance"
        report = coverage_report(items, text, stage="design")
        self.assertEqual(report["covered"], 1)
        self.assertEqual(report["items"], 1)
        self.assertEqual(report["rows"][0]["matched_demands"], report["rows"][0]["demands"])


if __name__ == "__main__":
    unittest.main()
