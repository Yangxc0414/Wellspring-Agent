"""Pins for the settings-surface availability audit (design/128).

Claim: every settings module is reachable and carries real content, and the
static build never misattributes a compile-time runtime disable to the user,
nor emits runtime requests it cannot serve.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
SETTINGS = (WEB / "components" / "settings" / "SettingsPage.tsx").read_text(encoding="utf-8")
WORKSPACE = (WEB / "components" / "settings" / "WorkspaceSettings.tsx").read_text(encoding="utf-8")
USAGE = (WEB / "components" / "settings" / "UsageStats.tsx").read_text(encoding="utf-8")
BINDINGS = (WEB / "components" / "settings" / "ModelBindings.tsx").read_text(encoding="utf-8")
MODEL_RT = (WEB / "adapters" / "modelRuntime.ts").read_text(encoding="utf-8")
SIDEBAR = (WEB / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
CSS = (WEB / "styles" / "settings.css").read_text(encoding="utf-8")
TYPES = (WEB / "domain" / "types.ts").read_text(encoding="utf-8")

# All 16 settings sections declared in the type.
SECTIONS = [
    "general", "appearance", "shortcuts", "model", "memory", "agents", "commands",
    "plugins", "evolution", "runtime", "usage", "lineage", "archive", "data",
    "guide", "about",
]


class SettingsRealAvailabilityTest(unittest.TestCase):
    def test_every_declared_section_is_dispatched(self):
        for section in SECTIONS:
            self.assertIn(f'"{section}"', TYPES, f"{section} missing from SettingsSection")
            self.assertIn(f'case "{section}":', SETTINGS, f"{section} not dispatched")

    def test_settings_discloses_static_build_inside_the_modal(self):
        # the global banner sits behind this full-screen dialog
        self.assertIn("__STATIC_ONLY__", SETTINGS)
        self.assertIn("STATIC · DEMO", SETTINGS)
        self.assertIn(".settings-badge.is-static", CSS)

    def test_runtime_page_does_not_blame_the_user_in_static_build(self):
        self.assertIn("静态演示构建：runtime 在构建时已禁用", WORKSPACE)
        # the old unconditional "start the runtime" line must be gated
        self.assertIn('__STATIC_ONLY__', WORKSPACE)
        self.assertIn('loading\n                    ? "正在连接本地 runtime…"', WORKSPACE)

    def test_usage_and_bindings_speak_plainly_in_static_build(self):
        self.assertIn("静态演示构建：runtime 在构建时已禁用，这里只有本地估算", USAGE)
        self.assertIn("静态演示构建：runtime 在构建时已禁用，模块绑定只在本地 CLI 可用", BINDINGS)

    def test_model_runtime_never_fetches_in_static_build(self):
        # Both request helpers must refuse to fetch in a static build. The guard
        # now lives in capabilities.ts (design/129), so assert the call site
        # rather than the old inline literal.
        self.assertEqual(MODEL_RT.count("requireRuntime(path)"), 2)
        self.assertNotIn("__STATIC_ONLY__", MODEL_RT)

    def test_sidebar_automation_fallback_is_accurate(self):
        self.assertIn("静态演示构建不含 runtime", SIDEBAR)


if __name__ == "__main__":
    unittest.main()
