# `research_agent/vendor/` — 第三方工作流

## AstraDraw

- 来源：`D:\Users\20691\Desktop\AstraDraw-main`（用户提供的本地工作流）
- 复制时间：2026-10-23
- 复制方式：**完整目录原样复制**（含 `SKILL.md`、`scripts/`、`references/`、`examples/`、`output/`、`tests/` 与 `.local/`）
- 本地路径：`research_agent/vendor/astradraw/`
- 上游仓库未提供根 `LICENSE`；仅作本地研究/生成使用，**不再分发**。上游素材/字体的使用限制见 `astradraw/examples/*/SOURCES.md`、`astradraw/docs/media/brand/fonts/` 及各示例说明。

### 我们改哪里

- 不改 `astradraw/scripts/build_components.py` 等上游脚本；
- 在 `research_agent/adapters/astradraw_renderer.py` 调用其 `render_svg(scene)`；
- 在 `research_agent/adapters/svg_audit.py` 增加 SVG 可访问性、无外链、无脚本、文本/ID/尺寸检查；
- 在 `research_agent/modules/figure.py` 生成 AstraDraw schema-v1 的 scene，并写 provenance/manifest。

这样既保留上游可追溯性，又让绘图进入我们的 `Spec → Agent → Artifact → Audit` 链路。
