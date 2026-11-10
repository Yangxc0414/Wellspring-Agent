"""The distributable folder must be a build product, not a hand-maintained twin.

A copied folder silently diverges, and divergence is exactly the defect class this project
hunts: what a surface claims stops matching what the code does.  So the release folder is
verified, not trusted.
"""

import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "Wellspring-Agent"


def _load_builder():
    path = ROOT / "scripts" / "build_release.py"
    spec = importlib.util.spec_from_file_location("build_release", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseIntegrityTest(unittest.TestCase):
    def setUp(self):
        if not RELEASE.is_dir():
            self.skipTest("release folder not built; run python scripts/build_release.py")

    def test_manifest_describes_the_files_that_exist(self):
        lines = (RELEASE / "MANIFEST.txt").read_text(encoding="utf-8").splitlines()
        rows = [l.split("\t") for l in lines if l and not l.startswith("#")]
        self.assertGreater(len(rows), 100, "the manifest must cover the shipped tree")
        for rel, digest, size in rows:
            path = RELEASE / rel
            self.assertTrue(path.is_file(), "manifest lists a missing file: " + rel)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, rel)
            self.assertEqual(path.stat().st_size, int(size), rel)

    def test_release_carries_the_vendored_renderer_and_no_build_debris(self):
        self.assertTrue(
            (RELEASE / "research_agent/vendor/astradraw/scripts/build_components.py").is_file(),
            "without the vendored renderer the schematic path silently degrades",
        )
        self.assertTrue((RELEASE / "apps/web/public/agent-registry.json").is_file())
        for debris in (
            "apps/web/dist",
            "apps/web/node_modules",
            "research_agent/__pycache__",
            "research_agent/web/data",
            "research_agent/vendor/astradraw/.local",
            "research_agent/vendor/astradraw/docs",
        ):
            self.assertFalse((RELEASE / debris).exists(), "must not ship: " + debris)
        # the vendored output folder is allowed only for the scene files the catalog names:
        # its png/pptx demos are the third party's own state, not our source
        output = RELEASE / "research_agent/vendor/astradraw/output"
        if output.is_dir():
            stray = [p.as_posix() for p in output.rglob("*") if p.is_file() and p.suffix != ".json"]
            self.assertEqual(stray, [], "only .scene.json may ship from the vendored output")
        size = sum(f.stat().st_size for f in RELEASE.rglob("*") if f.is_file())
        self.assertLess(size, 40 * 1024 * 1024, "the release grew past a source-sized bundle")

    def test_the_bundle_passes_the_release_scan_as_its_own_root(self):
        # the root scan skips the nested product; the product itself must still be clean
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "release_check", ROOT / "scripts" / "release_check.py"
        )
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        report = checker.check_release(RELEASE)
        blockers = [item for item in report["blockers"] if item.get("kind") != "license"]
        self.assertEqual(blockers, [], report["blockers"])

    def test_every_file_in_the_bundle_is_explained(self):
        # an untracked file is either forgotten state or an unnoticed edit; both belong to a
        # build product as little as a stale bundle does
        lines = (RELEASE / "MANIFEST.txt").read_text(encoding="utf-8").splitlines()
        tracked = {l.split("\t")[0] for l in lines if l and not l.startswith("#")}
        here = RELEASE.resolve()
        on_disk = {
            p.relative_to(here).as_posix() for p in RELEASE.rglob("*") if p.is_file()
        }
        # the release folder is itself a git repository; its object store is version-control
        # internals, not bundle content, and would otherwise read as unexplained
        on_disk = {rel for rel in on_disk if not rel.startswith(".git/")}
        on_disk.discard("MANIFEST.txt")
        unexplained = sorted(on_disk - tracked)
        self.assertEqual(unexplained, [], "untracked files inside the release bundle")
        report = _load_builder().build(True)
        self.assertEqual(report["release_owned_missing"], [], "release-facing docs must exist")

    def test_the_bundle_can_render_every_template_it_advertises(self):
        # the release used to advertise seven figure templates while shipping the scenes for
        # three, because the vendored-folder trim removed the rest
        import os
        import subprocess
        import sys

        # running the CLI inside the bundle otherwise writes __pycache__ there, and the
        # sibling debris assertion then fails for a reason the test itself caused
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

        def ids(cwd):
            out = subprocess.run(
                [sys.executable, "-m", "research_agent", "figure", "templates"],
                capture_output=True, text=True, cwd=str(cwd), encoding="utf-8", env=env,
            ).stdout
            import json as _json

            payload = _json.loads(out)
            return sorted(t["id"] for t in payload.get("templates") or [])

        shipped = ids(RELEASE)
        self.assertEqual(shipped, ids(ROOT), "the bundle lost figure templates the root has")
        self.assertGreater(len(shipped), 0)

    def test_release_is_identical_to_the_repository_root(self):
        report = _load_builder().build(True)
        self.assertEqual(
            [report["missing_in_release"], report["content_drift"]],
            [0, 0],
            "Wellspring-Agent has drifted from the repository root; run scripts/build_release.py: %s"
            % (report["examples_missing"] + report["examples_drift"]),
        )


if __name__ == "__main__":
    unittest.main()
