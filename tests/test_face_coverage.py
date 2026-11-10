"""The face matrix must be verifiable, not plausible.

Written after measuring that name-matching pairs only 24 of 45 MCP tools and that a regex route scan
finds 52 of the 59 routes the app registers - enough to turn a rename into a reported absence.
"""

import unittest

from research_agent.face_coverage import (
    cli_command_paths,
    face_matrix,
    http_route_paths,
)
from research_agent.mcp_server import TOOL_NAMES


class FaceMatrixTest(unittest.TestCase):
    def test_every_capability_is_listed_exactly_once(self):
        matrix = face_matrix()
        names = [entry["capability"] for entry in matrix["entries"]]
        self.assertEqual(sorted(names), sorted(TOOL_NAMES))
        self.assertEqual(len(names), len(set(names)))

    def test_no_declared_target_is_invented(self):
        matrix = face_matrix()
        self.assertEqual(matrix["declaration_problems"], [])
        commands = set(cli_command_paths())
        routes = set(http_route_paths())
        for entry in matrix["entries"]:
            if entry["cli"]:
                self.assertIn(entry["cli"], commands, entry["capability"])
            if entry["http"] and routes:
                self.assertIn(entry["http"], routes, entry["capability"])

    def test_a_bogus_declaration_is_caught_rather_than_believed(self):
        from research_agent import face_coverage

        original = dict(face_coverage.DECLARATIONS)
        face_coverage.DECLARATIONS["research_status"] = {"cli": "study nonexistent-command-xyz"}
        try:
            matrix = face_matrix()
        finally:
            face_coverage.DECLARATIONS.clear()
            face_coverage.DECLARATIONS.update(original)
        self.assertTrue(
            any("does not exist" in p for p in matrix["declaration_problems"]),
            matrix["declaration_problems"],
        )

    def test_unaudited_entries_are_counted_instead_of_assumed(self):
        matrix = face_matrix()
        self.assertEqual(
            matrix["summary"]["declared"] + matrix["summary"]["unaudited"], len(TOOL_NAMES)
        )
        self.assertEqual(len(matrix["unaudited_capabilities"]), matrix["summary"]["unaudited"])

    def test_human_gates_are_not_served_by_the_mcp_face(self):
        for verb in ("approve", "sign", "freeze", "publish"):
            self.assertFalse(
                any(verb in str(name).lower() for name in TOOL_NAMES),
                "a gate verb reached the MCP face: " + verb,
            )


class ContractExposureTest(unittest.TestCase):
    """A host must be able to read the mapping from the negotiation it already performs."""

    def test_the_contract_publishes_the_matrix_and_says_what_it_did_not_check(self):
        from research_agent.host_contract import host_contract

        contract = host_contract(declared=["can_call_tools"])
        coverage = contract["face_coverage"]
        self.assertEqual(coverage["faces"]["mcp_tools"], len(TOOL_NAMES))
        self.assertEqual(
            coverage["declared"] + coverage["unaudited"], len(TOOL_NAMES)
        )
        # the contract does not import the runtime app, and must not pretend it verified HTTP
        self.assertFalse(coverage["http_targets_verified"])
        self.assertIn("not verified", coverage["boundary"])

    def test_the_build_boundary_names_the_command_to_compare_against(self):
        from research_agent.host_contract import host_contract

        boundary = host_contract()["build"]["boundary"]
        self.assertIn("python -m research_agent handoff contract", boundary)
        self.assertIn("stale", boundary)

    def test_full_verification_still_checks_every_http_declaration(self):
        matrix = face_matrix(include_http=True)
        self.assertTrue(matrix["faces"]["http_routes_enumerable"])
        self.assertEqual(matrix["declaration_problems"], [])
        self.assertTrue(matrix["faces"]["http_targets_verified"])


class BoundaryMatchesWhatWasEnumeratedTest(unittest.TestCase):
    """The verification sentence may only claim the enumeration that actually ran."""

    def test_an_unenumerated_http_column_is_called_unverified(self):
        matrix = face_matrix(include_http=False)
        self.assertFalse(matrix["faces"]["http_targets_verified"])
        self.assertIn("NOT verified", matrix["boundary"])
        self.assertNotIn("and the live FastAPI route list", matrix["boundary"])

    def test_an_enumerated_column_claims_both_trees(self):
        matrix = face_matrix(include_http=True)
        if not matrix["faces"]["http_targets_verified"]:
            self.skipTest("the runtime app could not be imported in this environment")
        self.assertIn("live FastAPI route list", matrix["boundary"])
        self.assertNotIn("NOT verified", matrix["boundary"])

    def test_research_run_is_declared_against_the_handler_not_the_matching_name(self):
        # CLI "research run" is the ResearchRunner batch; the MCP tool builds a TaskRequest, which is
        # CLI "task run". A name-paired declaration would have looked correct and been wrong.
        matrix = face_matrix(include_http=False)
        by_name = {entry["capability"]: entry for entry in matrix["entries"]}
        self.assertEqual(by_name["research_run"]["cli"], "task run")
        self.assertIn("research run", cli_command_paths())
        self.assertNotEqual(by_name["research_run"]["cli"], "research run")


class ReverseRegistryTest(unittest.TestCase):
    """An absence is only excused when a reason is written down; silence must count as unexplained."""

    def setUp(self):
        self.matrix = face_matrix(include_http=True)
        self.reverse = self.matrix["reverse"]

    def test_every_surface_is_classified_exactly_once(self):
        self.assertEqual(
            self.reverse["surfaces"], sum(self.reverse["summary"].values())
        )
        self.assertTrue(self.reverse["surfaces"] > self.matrix["faces"]["cli_commands"])

    def test_a_gate_command_is_classified_as_design_not_as_an_unexplained_hole(self):
        # checked on a controlled surface list because the real one keeps only a capped sample: with
        # ~200 unexplained rows, absence from the sample would prove nothing.
        from research_agent.face_coverage import reverse_coverage

        reverse = reverse_coverage(
            entries=[],
            commands=["run claim", "experiment approve", "study brief", "zzz invented probe"],
            routes=["/api/zzz"],
            http_scanned=True,
        )
        self.assertEqual(reverse["surfaces"], 5)
        self.assertEqual(reverse["summary"]["human_gate_by_design"], 2)
        self.assertEqual(reverse["summary"]["reasoned"], 1)
        self.assertEqual(reverse["summary"]["unexplained"], 2)

    def test_a_reached_surface_never_appears_in_the_hole_list(self):
        # the bug this guards: classifying every surface instead of only unreached ones counted the
        # 8 declared HTTP routes as holes, so the hole count disagreed with the forward matrix
        from research_agent.face_coverage import reverse_coverage

        reverse = reverse_coverage(
            entries=[{"cli": "study brief", "http": "/api/zzz"}],
            commands=["study brief", "zzz unreached"],
            routes=["/api/zzz"],
            http_scanned=True,
        )
        self.assertEqual(reverse["surfaces"], 1)
        self.assertEqual(reverse["summary"]["unexplained"], 1)

    def test_preflight_is_named_as_a_known_mcp_gap_rather_than_left_unexplained(self):
        # measured: /api/research/preflight exists and no MCP tool points at it. Recording the reason
        # is what keeps it visible; dropping it into the unexplained bucket would bury it in 200 rows.
        from research_agent.face_coverage import REVERSE_REASONS

        self.assertIn("cli:experiment preflight", REVERSE_REASONS)
        self.assertIn("cli:study brief", REVERSE_REASONS)

    def test_truncation_is_reported_and_not_hidden(self):
        self.assertTrue(self.reverse["truncated"])
        self.assertEqual(
            self.reverse["unlisted"],
            self.reverse["summary"]["unexplained"] - len(self.reverse["unexplained_examples"]),
        )

    def test_family_counts_cover_every_unexplained_row(self):
        # the capped examples are an alphabetical prefix, so the only trustworthy distribution is the
        # one computed over all rows; it must add up or it is another capped sample in disguise
        reverse = self.reverse
        self.assertEqual(
            reverse["unexplained_families_scanned"], reverse["summary"]["unexplained"]
        )
        self.assertTrue(reverse["unexplained_families"])
        self.assertIn("alphabetical prefix", reverse["examples_order"])

    def test_group_namespaces_are_not_counted_as_surfaces(self):
        # "empirical" and "skill" are parents, not commands: counting them inflated the hole list
        paths = cli_command_paths()
        for group in ("skill", "empirical", "study", "task", "closure"):
            self.assertNotIn(group, paths)
        self.assertTrue(len(paths) < 241)

    def test_an_unscanned_http_column_says_it_was_not_scanned(self):
        reverse = face_matrix(include_http=False)["reverse"]
        self.assertFalse(reverse["http_scanned"])
        self.assertIn("not because nothing is missing", reverse["boundary"])


if __name__ == "__main__":
    unittest.main()
