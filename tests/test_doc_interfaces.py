"""D6: a documented *.json path is an interface, and an unexplained one must be visible.

The failure this pins is measured, not imagined: 60-科研智能体设计缺陷与改正.md found 19 of
29 json paths in AGENTS.md missing from a clean checkout, so a command copied out of the
document failed at once. The guard enumerates every reference instead of sampling one number.
Every test here has a way to fail, including a renamed path injected into the real AGENTS.md
text (without touching the file on disk).
"""

import tempfile
import unittest
from pathlib import Path

from research_agent.doc_interfaces import (
    GENERATED_BY,
    KINDS,
    LIVING_DOC,
    SCHEMA_VERSION,
    UNEXPLAINED,
    audit_doc_interfaces,
    classify_references,
    doc_sources,
    find_json_references,
    interface_text,
)
from research_agent.paths import build_info
from research_agent.projections import CONTRACT_SLOTS, projection_inventory

REPO = Path(__file__).resolve().parents[1]


class ClassificationTest(unittest.TestCase):
    def test_an_unexplained_path_is_reported(self):
        rows = classify_references(
            "read docs/never-generated.json before running", REPO, reasons={},
            strict_basenames=True,
        )
        self.assertEqual([r["kind"] for r in rows], [UNEXPLAINED])
        self.assertEqual(rows[0]["path"], "docs/never-generated.json")
        self.assertEqual(rows[0]["reason"], "")

    def test_a_reason_naming_a_command_exempts_the_path(self):
        reasons = {
            "docs/never-generated.json": {
                "command": "python -m research_agent example --out docs/never-generated.json",
                "reason": "produced by example, absent from a clean checkout",
            }
        }
        rows = classify_references(
            "read docs/never-generated.json", REPO, reasons=reasons, strict_basenames=True
        )
        self.assertEqual(rows[0]["kind"], "generated")
        self.assertIn("python -m research_agent example", rows[0]["reason"])

    def test_a_reason_without_a_command_does_not_exempt_anything(self):
        reasons = {
            "docs/never-generated.json": {"command": "", "reason": "someone will make it later"}
        }
        rows = classify_references(
            "read docs/never-generated.json", REPO, reasons=reasons, strict_basenames=True
        )
        self.assertEqual(rows[0]["kind"], UNEXPLAINED)

    def test_templates_and_bare_names_are_counted_not_silently_dropped(self):
        text = (
            "outputs <run>/writing-pack.json, apps/web/public/*.json, "
            "EXP-.../closure-report.json and a bare idea.json"
        )
        refs = find_json_references(text)
        rows = classify_references(text, REPO)
        self.assertEqual(len(refs), len(rows))
        self.assertEqual(len(refs), 4)
        kinds = [row["kind"] for row in rows]
        self.assertEqual(kinds.count("template"), 3)
        self.assertEqual(kinds.count("artifact_name"), 1)
        for row in rows:
            self.assertTrue(row["reason"], "silence is not a reason: " + row["path"])

    def test_every_living_document_reference_is_classified(self):
        text = (REPO / LIVING_DOC).read_text(encoding="utf-8")
        rows = classify_references(text, REPO, strict_basenames=True)
        self.assertGreaterEqual(len(rows), 25)
        self.assertEqual(sorted(set(r["kind"] for r in rows))[0], "exists")
        for row in rows:
            self.assertIn(row["kind"], KINDS)
            self.assertTrue(row["reason"], row["path"])

    def test_run_relative_lineage_manifest_is_a_relative_artifact(self):
        rows = classify_references(
            "observe = 对每个含 `lineage/lineage.json` 的 run 重跑 verify", REPO
        )
        self.assertEqual([r["kind"] for r in rows], ["relative_artifact"])
        self.assertTrue(rows[0]["reason"])


class RealDocumentAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit_doc_interfaces()

    def test_no_unexplained_json_reference_survives_in_the_living_docs(self):
        self.assertEqual(
            self.report["unexplained"], [],
            "AGENTS.md / modules/*/SPEC.md name a path with no reason: %s"
            % ", ".join(self.report["unexplained"]),
        )

    def test_every_kind_conserves_the_enumerated_population(self):
        self.assertEqual(sum(self.report["counts"].values()), self.report["total_references"])
        self.assertEqual(len(self.report["rows"]), self.report["total_references"])
        self.assertEqual(set(self.report["counts"]), set(KINDS))

    def test_the_sources_are_the_living_doc_and_every_module_spec(self):
        sources = self.report["provenance"]["sources"]
        self.assertEqual(sources[0], LIVING_DOC)
        self.assertGreaterEqual(len(sources), 25)
        self.assertEqual(len(sources), len(doc_sources(REPO)))
        self.assertEqual(len(set(sources)), len(sources))

    def test_the_base_states_the_denominator(self):
        self.assertIn("distinct *.json references", self.report["base"])
        self.assertIn(str(self.report["total_references"]), self.report["base"])
        self.assertIn(LIVING_DOC, self.report["base"])

    def test_the_allowlist_is_neither_stale_nor_unreasoned(self):
        self.assertEqual(self.report["stale_allowlist"], [])
        self.assertEqual(self.report["reasonless_allowlist"], [])

    def test_every_reason_names_a_command_and_a_cause_not_a_placeholder(self):
        living = (REPO / LIVING_DOC).read_text(encoding="utf-8")
        referenced = set(find_json_references(living))
        for path, entry in GENERATED_BY.items():
            command = entry["command"]
            self.assertTrue(command, path)
            self.assertGreaterEqual(len(entry["reason"]), 20, path)
            self.assertTrue(
                command.startswith("python -m research_agent") or "human" in command,
                "a reason must name an executable command or an explicit human action: " + path,
            )
            # The path must really be a documented interface, not an entry invented to make the
            # audit green; and it must still be absent, otherwise its reason is stale.
            self.assertIn(path, referenced, path)
            self.assertFalse((REPO / path).is_file(), "reason is stale, file now exists: " + path)

    def test_the_audit_writes_nothing(self):
        before = sorted(p.as_posix() for p in REPO.glob("research_agent/*.py"))
        audit_doc_interfaces()
        after = sorted(p.as_posix() for p in REPO.glob("research_agent/*.py"))
        self.assertEqual(before, after)

    def test_skipped_history_is_counted_not_silently_dropped(self):
        self.assertGreater(self.report["skipped_sections"], 0)
        self.assertGreater(self.report["skipped_references"], 0)
        self.assertIn("excluded_as_history", self.report["provenance"])
        self.assertIn("dated history", self.report["boundary"])

    def test_a_renamed_path_in_the_real_document_would_turn_the_guard_red(self):
        original = (REPO / LIVING_DOC).read_text(encoding="utf-8")
        renamed = original.replace(
            "research_agent/web/data/rsi-compare-ledger.json", "docs/renamed-away.json", 1
        )
        self.assertNotEqual(renamed, original, "the fixture path must still be in AGENTS.md")
        rows = classify_references(renamed, REPO, strict_basenames=True)
        self.assertEqual(
            [r["path"] for r in rows if r["kind"] == UNEXPLAINED],
            ["docs/renamed-away.json"],
        )


class HistoryBoundaryTest(unittest.TestCase):
    def test_a_spec_changelog_is_history_not_a_copyable_interface(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            spec_dir = root / "modules" / "demo"
            spec_dir.mkdir(parents=True)
            (root / LIVING_DOC).write_text("reads answer.json\n", encoding="utf-8")
            (spec_dir / "SPEC.md").write_text(
                "## Contract\n\nreads inputs/thing.json\n\n"
                "## Changelog\n\n- regression example used docs/historical-only.json\n",
                encoding="utf-8",
            )
            report = audit_doc_interfaces(root)
            paths = set(row["path"] for row in report["rows"])
            self.assertIn("inputs/thing.json", paths)
            self.assertNotIn("docs/historical-only.json", paths)
            self.assertEqual(report["unexplained"], [])
            self.assertEqual(report["skipped_sections"], 1)
            self.assertGreaterEqual(report["skipped_references"], 1)

    def test_the_living_doc_has_no_excluded_tail(self):
        interface, history = interface_text(
            (REPO / LIVING_DOC).read_text(encoding="utf-8"), strict=True
        )
        self.assertIn("python -m research_agent", interface)
        self.assertEqual(history, "")


class StaleAllowlistTest(unittest.TestCase):
    def test_a_document_that_no_longer_names_a_path_exposes_the_stale_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / LIVING_DOC).write_text(
                "one documented output: answer.json\n", encoding="utf-8"
            )
            report = audit_doc_interfaces(root)
            self.assertEqual(report["unexplained"], [])
            self.assertIn(
                "research_agent/web/data/rsi-compare-ledger.json", report["stale_allowlist"]
            )


class ProjectionContractTest(unittest.TestCase):
    """The new guard is itself a projection: it must pass the guard that already exists."""

    def test_the_audit_carries_every_contract_slot_with_real_values(self):
        report = audit_doc_interfaces()
        for slot in CONTRACT_SLOTS:
            self.assertIn(slot, report, slot)
        self.assertEqual(report["schema_version"], SCHEMA_VERSION)
        self.assertEqual(report["source_fingerprint"], build_info()["fingerprint"])
        self.assertTrue(report["read_only"])
        self.assertTrue(report["generated_at"])
        self.assertIn("never writes to the", report["boundary"])

    def test_the_projection_inventory_reports_it_complete(self):
        inventory = projection_inventory()
        row = next(
            (r for r in inventory["rows"] if r["schema"] == SCHEMA_VERSION), None
        )
        self.assertIsNotNone(row, "the audit projection disappeared from the inventory")
        self.assertEqual(row["absent_slots"], [])
        self.assertTrue(row["complete"])


if __name__ == "__main__":
    unittest.main()
