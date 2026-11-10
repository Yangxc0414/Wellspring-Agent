---
id: figure
name: 科研绘图
stage: S6
version: 0.4.1
status: pilot
owner: research-agent
inputs:
  - title
  - description
  - nodes
  - edges
  - evidence_refs
  - SceneFile
outputs:
  - FigureScene
  - SVG
  - FigureManifest
  - FigurePreview
  - RenderAudit
tools:
  - astradraw.render
  - astradraw.render_scene
  - astradraw.templates
  - svg.audit
gates:
  - G3
invariants:
  - 示意图与数据图分开；数据图必须绑 RunCapsule/EA
  - SVG 不引外部资源/脚本
  - 必须记录 scene/svg/hash
  - 模板只提供布局/风格先验，不携带其科学结论；标题、说明和 provenance 必须声明 schematic=true
  - 只渲染本地 vendored AstraDraw scene；不执行上游新增脚本、不联网、不修改 vendor
  - AstraDraw 只产方法/框架示意图（`schematic=true`），不产实验数据结果图；数据结果图走 experiment_figures 的 verified-evidence 管线
---

# 科研绘图子智能体（S6）

## Purpose

把模块/机制关系画成确定性的、可编辑 SVG。以 AstraDraw 的 scene→SVG 为渲染底座；本模块只负责把我们的 FigureRequest 变成 scene、做可访问性与安全审计、写 provenance。

## Contract

- 输入：标题、说明、节点（id/label/kind/level/evidence_refs）、边；
- 输出：`FigureScene`（AstraDraw schema v1）、`SVG`、`FigureManifest`（scene/svg SHA-256、evidence_refs、schematic=true、audit）；
- SVG 必须通过：XML 可解析、root svg、width/height/viewBox、唯一 ID、非空文本、无 script/foreignObject、无外部 href、role=img、title/desc；
- 失败则拒绝输出，不用“生成了一张图”掩盖校验失败。
- `figure table --data <csv/xlsx> --spec <figures JSON> --output-dir <dir>`：数据表直出图。
  输入是使用者提供的数据表与 `{"figures": [...]}` 规格（`x`/`y`/`series`/`agg`/`where`），
  输出每张图的 PNG+SVG 路径与 `data_sha256`/`spec_sha256`/`output_sha256`、`schematic=false`
  与边界文案。它是**已给数据的确定性渲染**：不重算指标、不产生证据/Claim/门禁，
  规格里没有图时直接失败退出，不用“跑了一条命令”掩盖空规格。

## Current Implementation

- `research_agent/modules/figure.py`；
- `research_agent/adapters/astradraw_renderer.py` 加载 `vendor/astradraw/scripts/build_components.py` 的 `render_svg`，不改上游；
- `research_agent/adapters/svg_audit.py` 做静态审计；
- 版面：按 `level` 分层、同层纵向排列，边从节点右中到左中；
- `build_result_figure`：从 RunCapsule 的逐 seed 指标生成 method vs baseline 数据柱状图；manifest 记录 `schematic=false`、运行/数据集/指标、SVG 与数据哈希、EA refs；使用同一 SVG 审计；
- 示意图与数据结果图分开：本模块的 `build_result_figure` 只绑定 RunCapsule/EA；revision 模块从用户表格生成的数据图由其 metric/figure manifest 绑定，二者不得互相冒充；
- `research_agent/figure_workflow.py`：列出 vendored scene 模板；加载项目内 `.scene.json` 或模板，调用同一 renderer + audit，写 SVG/PNG/audit/manifest；
- CLI `figure templates|render`；MCP `research_figure_templates|research_figure_render`；
- 模板：`calm-method`、`calm-survey`、`survey-framework`、`tracerl-method`、`role-guided-search`、`self-forcing`、`framework-example`；它们只作版式/风格参考。


## Boundaries

- 不支持任意插图/照片/外部素材；不嵌入外部图片；
- 本轮支持场景渲染为 SVG/PNG；可编辑 PPTX 导出仍依赖上游 Node/presentations 环境，不在 MCP 中承诺；
- vendored 模板只作本地视觉参考，不能把示例中的机制或数字当成本文结论；
- 不把示意图当实验图；
- 不自动判断审美；风格选择与最终视觉由人确认；
- 上游 AstraDraw 无根许可证，本地使用、不再分发。

## Minimal Change Workflow

1. 先改本文件 Contract 或 Current Implementation；
2. 升 version + Changelog；
3. 改 `FigureAgent` / SVG audit / renderer adapter；
4. 加/改 `tests/test_figure.py`；
5. 不修改 vendor 上游脚本；如需改，新增 adapter 层。

## Changelog

- 2026-11-01 · v0.4.1 · status=pilot · 示意图渲染器缺失时降级而不是失败：vendored AstraDraw 是可选第三方依赖，此前 research_agent/vendor 缺失会让 adapters/astradraw_renderer.py 抛 FileNotFoundError，一路炸穿 modules/figure.py → pipeline.py → runtime/jobs.py，使整条 S5/S6 job 失败——一个 advisory 产物拥有了否决主链的权力。现在 figure 在无渲染器时仍产出 scene 与 manifest，svg 为空、audit.errors=astradraw_renderer_missing、manifest.renderer_available=false，pipeline 的状态改为 scene_only 并追加 warning（不再谎称 SVG ready）。tests.test_pipeline 新增一项钉住该降级路径。
- 2026-11-01 · v0.4.0 · status=pilot · figure table 现在为每张图在图片同目录写 <figure_id>.caption.md 边车：caption 正文、title/x/y/series/type/agg/where/table、data/spec/output 三个 SHA-256、schematic、图片路径，以及该图被 seed_coverage 命中的每条 series 的 “N of M” 种子数。动机是 §102 的核实——披露此前只存在于一次 stdout：5 张图的 caption（205–237 字符）既不画进 SVG/PNG，也没有任何边车文件，拿走 PNG 的人看不到“本曲线基于 28–31/32 个种子，排除的是起点已达上限的 run”。只在 figure table 这条 CLI 路径加边车，不动 generate_figures，因此 revision run 的输出集合与既有测试不变。契约新增一条输出文件，升 minor。
- 2026-11-01 · v0.3.1 · status=pilot · figure table 现在自带 seed_coverage 与对应 warning：数据表里有 seeds 列且同一 series 的种子数不一致时，逐条列出 table/figure_id/series/min_seeds/max_seeds 并提示“图注必须写明 N of M 个种子”。动机来自 §99：把响应曲线扩到四个独立环境后发现 16 条 series 里 7 条只有 28–31 个种子，因为归一化会排除起点已达上限的 run——被排除的正是天花板截断本身，而图上看不到这件事。advisory 输出字段，判定与门禁不变，升 patch。
- 2026-11-01 · v0.3.0 · status=pilot · 新增 figure table --data --spec --output-dir：数据表直出 PNG/SVG。动机是能力一直在内部函数里却没有入口——revision_figures.generate_figures() 此前只被 revision.py 的 revision run 调用（需要先有一份稿件），所以“有测量结果但画不出图”挂了好几轮，§96/§97 的响应曲线正是被它卡住。输出带 data/spec/output 三个 SHA-256、schematic=false 与边界文案；空规格直接失败，不静默产出零张图。契约新增一条 CLI 与输出形状，升 minor。
- 2026-10-27 · v0.2.2 · status=pilot · empirical loop 可显式传 `--method-template`/`--method-scene` 渲染方法示意图（图 2，schematic=true，AstraDraw）；只作为机制说明，不进结果节/证据。
- 2026-10-27 · v0.2.1 · status=pilot · 明确 AstraDraw 只产方法/框架示意图，不产实验数据结果图；manifest 增加 `renderer=astradraw`/`data_result_plot=false` 标记。
- 2026-10-26 · v0.2.0 · status=pilot · 接入 AstraDraw 场景/模板渲染：CLI `figure templates|render`、MCP `research_figure_templates|research_figure_render`；输出 SVG/PNG/audit/manifest；模板仅作视觉先验，schematic=true，不改 vendor。
- 2026-10-24 · v0.1.2 · status=pilot · 修正 invariant：允许数据结果图，但必须绑定 RunCapsule/EA 且 schematic=false
- 2026-10-24 · v0.1.1 · status=pilot · 最小改进：增加 build_result_figure，从 RunCapsule 逐 seed 指标生成数据图（method vs baseline），写 manifest 与 SVG 审计；示意图与数据图分开
- 2026-10-23 · v0.1.0 · 初始 module graph → AstraDraw scene → SVG；接入可访问性/安全审计。
