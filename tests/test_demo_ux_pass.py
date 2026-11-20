"""Pins for the demo UX pass: empty/error states, duplicate info, misleading labels.

Rules this guards:
  * an empty surface must say what is missing and what to do next, not render a
    bare line of unstyled text;
  * a class used as an empty state must actually have a rule (`.context-note`
    had none for a dozen call sites);
  * a build-time disable must never leak as a raw English technical error
    spliced into Chinese UI;
  * a button must not promise something this build cannot do.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
PANEL = (WEB / "components" / "ContextPanel.tsx").read_text(encoding="utf-8")
EMPTY = (WEB / "components" / "EmptyState.tsx").read_text(encoding="utf-8")
CAPS = (WEB / "domain" / "capabilities.ts").read_text(encoding="utf-8")
COMPOSER = (WEB / "components" / "Composer.tsx").read_text(encoding="utf-8")
CSS = (WEB / "styles" / "components.css").read_text(encoding="utf-8")
WS = (WEB / "components" / "settings" / "WorkspaceSettings.tsx").read_text(encoding="utf-8")
BIND = (WEB / "components" / "settings" / "ModelBindings.tsx").read_text(encoding="utf-8")


class DemoUxPassTest(unittest.TestCase):
    def test_empty_state_component_reuses_the_existing_styled_card(self):
        # reuse .context-empty-card instead of inventing a second empty style
        self.assertIn("context-empty-card empty-state", EMPTY)
        self.assertIn("empty-state-title", EMPTY)
        self.assertIn("tone?: \"block\" | \"note\"", EMPTY)

    def test_context_note_actually_has_a_rule(self):
        # the class had no CSS at all before this pass
        self.assertIn(".context-note {", CSS)
        self.assertIn("border: 1px dashed var(--line);", CSS)

    def test_projects_empty_and_error_states_are_explained(self):
        self.assertIn("静态构建不含项目实验链", PANEL)
        self.assertIn("还没有登记项目实验链", PANEL)
        # no bare english technical error spliced after a colon
        self.assertNotIn("项目实验链不可用：{error}", PANEL)

    def test_raw_runtime_errors_are_translated(self):
        self.assertIn("export function describeRuntimeError(", CAPS)
        self.assertIn("静态演示构建：runtime 在构建时已禁用", CAPS)
        # all four call sites go through it
        for text in (PANEL, WS, BIND):
            self.assertNotIn("读取失败：{error}", text)
        self.assertIn("describeRuntimeError(error", PANEL)
        self.assertIn("describeRuntimeError(error)", WS)
        self.assertIn("describeRuntimeError(error)", BIND)

    def test_evidence_gates_do_not_repeat_the_run_list(self):
        # only non-passing gates are listed here, with a pointer to RUN
        self.assertIn('task.gates.filter((gate) => gate.status !== "pass")', PANEL)
        self.assertIn("在 RUN 面板查看全部", PANEL)

    def test_question_heading_replaced_with_a_statement(self):
        self.assertNotIn("这五段是什么意思？什么时候需要人签？", PANEL)
        self.assertIn("六段的含义与人工签署时点", PANEL)

    def test_pipeline_button_does_not_promise_a_missing_runtime(self):
        self.assertIn('__STATIC_ONLY__ ? "推演一次 pipeline（演示）"', COMPOSER)
        # and in a static build it must run something that works
        self.assertIn("if (__STATIC_ONLY__) actions.startAuto();", COMPOSER)

    def test_host_model_panel_does_not_splice_raw_runtime_errors(self):
        # EVOLUTION tab 的 HOST MODEL 面板：静态构建下不渲染原始英文错误行，
        # runtime 下经 describeRuntimeError 翻译（131 轮补的漏网点）。
        host = (WEB / "components" / "HostModelPanel.tsx").read_text(encoding="utf-8")
        self.assertNotIn('<p className="host-error">{error}</p>', host)
        self.assertIn("describeRuntimeError(error", host)
        self.assertIn("runtimeAvailable ? (", host)

    def test_guidance_and_packages_use_the_unified_empty_state(self):
        self.assertIn('title="还没有插入指导"', PANEL)
        self.assertIn('title="还没有证据包"', PANEL)


if __name__ == "__main__":
    unittest.main()
