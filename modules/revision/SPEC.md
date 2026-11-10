---
id: revision
name: 已有手稿修订与投稿包
stage: S8–S12
version: 0.2.2
status: draft
owner: research-agent
inputs:
  - ManuscriptDraft
  - DataTable
  - MetricSpec
  - FigureSpec
  - VenueProfile
outputs:
  - RevisionPlan
  - RevisedManuscript
  - RevisionAudit
  - SentenceLedger
  - DataMetricReport
  - FigureManifest
  - ManuscriptExport
tools:
  - revision.ingest
  - revision.data_metrics
  - revision.figures
  - revision.rewrite
  - revision.audit
  - revision.export
gates: []
invariants:
  - 只修订已有手稿，不重新发明研究问题、实验或结论；原始叙事、实验条件、方法和限制必须保留
  - 没有模型 profile 时只做可审计的复制/数据更新，不伪装成模型改写
  - 模型改写必须逐段校验：引用 token 集合不变、数字集合不新增、图表编号不丢失、结果段数字不丢失；失败时保留原文并记录 blocker
- 改写只作用于当前段落，不接受整节/多段输出；Figure/Table 与 图/表 的中英互译视为同一引用
- 可选 rewrite goal 与 review comments 只作为改写指令，不得新增事实/数字/引用；模型返回双层 JSON 时必须解包
  - 数据指标只从用户提供的表格与 metric spec 重算；未知数字不得被当作已核验数字
  - 新图只从用户数据和 figure spec 生成；图 manifest 记录输入数据 SHA-256、spec SHA-256 和输出 SHA-256
  - 期刊模板是结构化排版 profile，不冒充官方模板；导出包必须标注模板版本与人工复核要求
  - submission_ready 始终为 false；最多输出 review_ready / format_ready；投稿、签核和最终录用仍是人工决定
  - 不创建或修改 Claim、EA、Protocol、Gate、Signature、Closure 或 export approval
---

# 已有手稿修订与投稿包（S8–S12）

## Purpose

让系统接收用户已经写好的论文、实验叙事、数据表和已有图表，在不重新发明研究内容的前提下做面向目标期刊的修订：重算可核验指标、生成数据图、逐段改写、做数字/引用/叙事一致性审计，并导出 Markdown、LaTeX、DOCX 和可用的 PDF 预览。

它不是“从 topic 重写一篇论文”，也不是同行评审或投稿决策系统。

## Contract

输入：

- `ManuscriptDraft`：`.md` / `.txt` / `.tex` / `.docx`；保留标题、章节、段落、表格、图占位、参考文献；
- `DataTable[]`：`.csv` / `.tsv` / `.json` / `.xlsx`，带表名；
- `MetricSpec`：JSON，声明 `table/column/op/where/digits/replace/section`；支持 `{{metric:name}}` 占位；
- `FigureSpec`：JSON，声明 `id/type(bar|line)/table/x/y/agg/title/caption/insert_after_heading`；
- `VenueProfile`：`zh_core_journal` / `software_journal` / `computer_journal`；只定义结构、字号、页边距和引用风格，不冒充官方模板；
- 可选 `model profile`：用于逐段改写；无 profile 时为 `copy_mode`。

输出（写入一个 revision 目录）：

- `revision-plan.json`：输入文件哈希、检测到的章节、将改写的段落、数据/图任务、模板；
- `revision-diff.json`：逐段原文/修订文、接受/拒绝状态、blockers 与 change summary；
- `revised-manuscript.md` / `.json`：保留原始叙事结构，写入改写后的段落、数据替换、图表块；
- `data-profile.json`：表格字段、类型、缺失值、数值摘要；
- `metric-results.json`：每个指标的计算值、样本数、过滤条件、格式化结果；
- `figure-manifest.json` + `figures/*.png|svg`：每个图的 data/spec/output SHA-256；
- `revision-audit.json`：引用/数字/图表/结果叙事/模板检查；blockers/warnings；
- `sentence-ledger.json`：逐句记录 citations、figure/table refs、numbers、matched data metrics 与 `numeric_unreferenced`；只是结构证据账本，不做语义蕴含判断；
- `export/manuscript.tex`、`export/manuscript.docx`、可选 `export/manuscript.pdf`、`export/manuscript.html`；
- `revision-summary.md`：给人看的一页变更与待确认清单。

改写规则：

- 只改写允许的 section；默认跳过参考文献、致谢、表格、图题、代码块；
- 参考 section 保留原始标题与段落顺序；
- 模型返回只接受 `{"text": "...", "change_summary": [...]}`；不接受新引用、新数字、新图表编号；
- 模型原样返回时标为 `unchanged`，不计入改写成功；
- 引用 token 集合必须与原文一致（允许顺序变化，不允许新增/丢失）；
- 数字 token 集合不得新增；结果/实验段落的数字不得丢失；允许通过 `metric replace` 显式替换；
- 改写长度控制在原文 50%–180%；
- 任一校验失败：该段回退原文，写入 blocker；不中断整篇；
- `copy_mode` 明确标记 `writer_mode=copy`，不把原文复制冒充改写。

## Current Implementation

- `research_agent/revision.py`：编排、逐段模型改写、引用/数字/图表引用防篡改、blocker 回退、sentence-ledger、revision-diff/audit/summary；支持 `--goal` 与 `--review-file`（must_fix / manuscript-review iterations）；只接受当前段落范围；
- `research_agent/revision_io.py`：MD/TXT/DOCX/TeX 解析（DOCX 表格与内嵌图片提取），CSV/TSV/JSON/XLSX 读取，Markdown/LaTeX/DOCX/PDF 导出；
- `research_agent/revision_figures.py`：从数据表生成 bar/line PNG/SVG，记录 data/spec/output SHA-256；
- `research_agent/revision_templates.py`：`zh_core_journal`、`software_journal`（18.4×26 cm、正文 9 pt、参考 7.5 pt 的近似样例）、`computer_journal` 工作 profile；
- CLI `revision inspect|run`；MCP `research_manuscript_revise`（项目内 draft/data → `<project>/revisions/<REV-ID>/`）；
- 模板是工作排版，不是官方模板；PDF 导出依赖本机 LibreOffice，缺失时保留 DOCX 并记录 warning；
- 不联网；模型调用只走现有 model gateway；不执行用户脚本；无模型 profile 时 writer_mode=copy，数据替换/图表/审计仍执行。

已知边界：本轮不做 PDF/扫描件 OCR（PDF 输入未列入本期）；不做语义蕴含证明；不做目标期刊官方模板替换；DOCX 复杂分栏/浮动对象为尽力保留。

## Boundaries

- 不能从零验证实验是否真实；只能重算用户提供的数据并保留其原始方法和限制；
- 不能证明引用语义支持；只保证引用 token 不丢失、不新增，数字可追溯到数据指标或原文；真正的语义支持仍由现有 bibliography/support audit/人工审稿负责；
- 不能替代目标期刊官方模板；`.docx`/`.tex` 是工作排版；
- 不能替代同行评审或编辑决定；
- 不处理扫描 PDF 的 OCR；PDF 输入仅支持已有可提取文本的后续扩展，本轮先支持 MD/TXT/TEX/DOCX；
- 不自动填入作者、单位、基金、伦理声明等真实信息；
- 不自动提交投稿系统。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 `version` + Changelog；
3. 先实现 ingest + data metrics + audit，再实现模型改写与 export；
4. 补 `tests/test_revision.py`，覆盖数字/引用防篡改、DOCX 解析、图表、导出；
5. 跑全量测试并导出工作区快照。

## Changelog

- 2026-11-01 · v0.2.2 · status=draft · load_figure_specs 现在拒绝未知字段并点名 figure_id、字段名与可用字段集合：此前不认识的键被静默丢弃，`"kind": "line"` 会落到 type 的默认值 bar，于是"响应曲线"画成柱状图而没有任何信号（§98 实测发生）。允许键集合按渲染器实际读取的字段列举（id/type/table/x/y/series/agg/where/title/caption/xlabel/ylabel/insert_after_heading/dpi）。tests.test_figure_table_cli 新增一项钉住该报错。判定与门禁不变，升 patch。
- 2026-10-27 · v0.2.0 · status=draft · 改写质量修复：解包模型双层 JSON、剥离重复标题、Figure/Table 与 图/表 引用归一、拒绝整节输出；新增 `--goal`/`--review-file` 把 must_fix 送入逐段改写；真实 7.5 万字综述引言测试 accepted 7/8、引用/数字 8/8、review_ready。
- 2026-10-26 · v0.1.0 · status=draft · 初始设计：已有手稿 + 数据表 → 修订、重算指标、重画图、审计、Markdown/LaTeX/DOCX/PDF 导出；不重新发明研究内容，不替代同行评审。
