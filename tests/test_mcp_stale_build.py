"""A stale MCP server must be identifiable from its own error, and a directory bundle must score
the same over MCP as over the library.

Both cases came from live testing through Qoder: the connector answered with an error message that
exists in no version of the code, and I filed two face defects against it before discovering that
the long-lived process was running an older import. The handler was already correct; what was
missing was any way for the host to see that from the error alone.
"""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.mcp_server import ResearchMCPService, tool_error
from research_agent.pack_audit import coverage_input
from research_agent.paths import build_fingerprint
from research_agent.skill_packs import coverage_report, scan_pack
from tests.test_skill_packs import _make_repo


class StaleBuildDisclosureTest(unittest.TestCase):
    def test_an_mcp_error_names_the_build_that_produced_it(self):
        result = tool_error("some handler refused the request")
        served = result["structuredContent"]["served_build"]
        self.assertEqual(served["fingerprint"], build_fingerprint())
        self.assertIn("handoff contract", served["check_command"])
        # the host reads the text, so the identity must be there too, not only in structuredContent
        self.assertIn(served["fingerprint"], result["content"][0]["text"])
        self.assertIn("stale code", result["content"][0]["text"])

    def test_a_rejected_request_raises_so_the_transport_wraps_it_with_the_build(self):
        from research_agent.mcp_server import ProjectError, dispatch_tool

        with tempfile.TemporaryDirectory() as tmp:
            service = ResearchMCPService(Path(tmp))
            with self.assertRaises(ProjectError):
                dispatch_tool(service, "research_skill_packs", {"action": "not-a-real-action"})
            # the transport turns that raise into this payload, which is what a host actually reads
            payload = tool_error("ProjectError: action must be scan, route or coverage")
        self.assertIn("action", payload["structuredContent"]["error"].lower())
        self.assertEqual(
            payload["structuredContent"]["served_build"]["fingerprint"], build_fingerprint()
        )


class DirectoryBundleParityTest(unittest.TestCase):
    """The face that scores a whole package directory must agree with the library exactly."""

    def _pack_and_package(self, root: Path):
        repo = _make_repo(root)
        package = root / "pkg"
        (package / "reader").mkdir(parents=True)
        (package / "reader" / "README.md").write_text(
            "report the compute budget and name the baseline", encoding="utf-8"
        )
        (package / "reader" / "outputs-per-seed.csv").write_text(
            "seed,score\n1,0.5\n2,0.6\n", encoding="utf-8"
        )
        return repo, package

    def test_mcp_and_library_report_the_same_bundle_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, package = self._pack_and_package(root)
            via_mcp = ResearchMCPService(root).skill_packs(
                {
                    "action": "coverage",
                    "pack_root": str(repo),
                    "venue": "Demo Journal",
                    "artifact": "pkg",
                }
            )["structuredContent"]
            pack = scan_pack(repo / "Demo-Skills", stages=via_mcp["stages"])
            text, bundle_fields = coverage_input(package)
            via_library = coverage_report(pack["checklist"], text, stages=via_mcp["stages"])
            via_library.update(bundle_fields)
        for field in ("covered", "items", "artifact_items", "artifact_covered", "items_scanned"):
            self.assertEqual(via_mcp[field], via_library[field], field)
        self.assertEqual(via_mcp["bundle"]["data_files"][0]["path"], "reader/outputs-per-seed.csv")
        self.assertEqual(via_mcp["bundle"]["skipped_unsupported_suffix"], 0)

    def test_the_directories_own_files_are_listed_not_assumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, _package = self._pack_and_package(root)
            payload = ResearchMCPService(root).skill_packs(
                {
                    "action": "coverage",
                    "pack_root": str(repo),
                    "venue": "Demo Journal",
                    "artifact": "pkg",
                }
            )["structuredContent"]
        paths = [row["path"] for row in payload["bundle"]["files"]]
        self.assertIn("reader/README.md", paths)
        self.assertNotIn("reader/outputs-per-seed.csv", json.dumps(paths))


if __name__ == "__main__":
    unittest.main()
