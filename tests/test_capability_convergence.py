"""Pins for the capability-convergence refactor (design/128 §6, step 1-2).

Two structural claims:
  1. Build-time capability is decided in exactly one module; adapters must not
     re-test the build flag (that omission is how /api/models kept fetching).
  2. Every settings section states what it can really do, so a viewer does not
     have to read the whole page to find out.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
CAPS = (WEB / "domain" / "capabilities.ts").read_text(encoding="utf-8")
SETTINGS = (WEB / "components" / "settings" / "SettingsPage.tsx").read_text(encoding="utf-8")
CSS = (WEB / "styles" / "settings.css").read_text(encoding="utf-8")


def read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


ADAPTERS = ["adapters/runtimeApi.ts", "adapters/modelRuntime.ts", "adapters/hostModelApi.ts"]


class CapabilityConvergenceTest(unittest.TestCase):
    def test_single_source_of_truth_exists(self):
        self.assertIn("export const runtimeAvailable = !__STATIC_ONLY__", CAPS)
        self.assertIn("export function requireRuntime(", CAPS)
        self.assertIn("export type CapabilityLevel", CAPS)
        # the build flag is read here and nowhere else in the adapter layer;
        # count code lines only (the doc comment explains the flag by name)
        code = [
            line for line in CAPS.splitlines()
            if "__STATIC_ONLY__" in line and not line.strip().startswith("*")
        ]
        self.assertEqual(len(code), 1, f"capabilities.ts should read the flag once, got {code}")

    def test_no_adapter_tests_the_build_flag_directly(self):
        for rel in ADAPTERS:
            text = read(rel)
            self.assertNotIn("__STATIC_ONLY__", text, f"{rel} must consult capabilities.ts")
            self.assertIn("requireRuntime", text, f"{rel} must guard with requireRuntime")

    def test_every_request_helper_guards_before_fetch(self):
        # each requireRuntime call must precede the fetch in the same function
        for rel in ADAPTERS:
            text = read(rel)
            for match in re.finditer(r"requireRuntime\([^)]*\)", text):
                tail = text[match.end():]
                fence = tail.find("fetch(")
                next_fn = tail.find("function ")
                if fence != -1:
                    self.assertTrue(
                        next_fn == -1 or fence < next_fn,
                        f"{rel}: requireRuntime not inside the same function as fetch",
                    )

    def test_every_section_declares_a_capability(self):
        sections = [
            "general", "appearance", "shortcuts", "commands", "model", "memory",
            "agents", "plugins", "evolution", "runtime", "usage", "lineage",
            "archive", "data", "guide", "about",
        ]
        for section in sections:
            self.assertIn(f"{section}: ", SETTINGS, f"{section} has no capability entry")

    def test_runtime_level_collapses_when_runtime_ships(self):
        self.assertIn('declared === "runtime" && runtimeAvailable ? "real" : declared', SETTINGS)

    def test_capability_badge_is_rendered_with_style(self):
        self.assertIn("settings-cap is-${capability}", SETTINGS)
        self.assertIn("CAPABILITY_META[capability].hint", SETTINGS)
        for level in ("real", "demo", "cli", "runtime"):
            self.assertIn(f".settings-cap.is-{level}", CSS)


if __name__ == "__main__":
    unittest.main()
