---
id: literature
name: 文献调研
stage: S1
version: 0.12.0
status: pilot
owner: research-agent
inputs:
  - question
  - max_sources
  - source_scope
  - coverage_plan
  - followup_plan
  - facet_subset
  - conference_venues
  - conference_years
outputs:
  - QueryPlan
  - SourceHit
  - Span
  - CoverageReceipt
  - LiteratureBrief
  - Gap
  - SourceManifest
  - DownloadedPDF
  - ConferenceCorpus
  - SynthesisMatrix
tools:
  - retriever.search
  - parser.spans
  - retriever.openalex
  - retriever.local_pdf
  - retriever.arxiv_fetch
  - retriever.arxiv_conference
  - literature.fetch
  - literature.conference_fetch
  - literature.synthesis
  - model.glm-5.3-flash
gates:
  - Q0
invariants:
  - 没有全文不得生成 Span
  - 不创建 Claim
  - fixture 必须显式标注
  - 摘要不能当全文证据
  - 真实语料必须 CC-BY 且带 provenance；harness-only 不写 capability claim
  - local PDF/TXT/MD 必须保留页码/文档锚点；空文本或扫描件不得伪装全文
  - 用户提供全文只作为本地证据，不自动升级为同行评审或 capability claim
  - OpenAlex 为只读公共 API：礼貌池 mailto、限流与重试；摘要只作 SourceHit 线索（full_text=false），OA 全文链接供人获取，不自动抓取
  - arXiv fetch 只在用户显式 opt-in 时联网；只下载 arXiv 公开 PDF，不绕过付费墙；记录 arXiv id/URL/SHA256/license-note；下载后仍走 local PDF 解析与 Q0
  - arXiv fetch 不把摘要当全文；下载失败/非 PDF/超限必须显式报错或记 skipped，不静默伪造来源
  - 顶会 fetch 只下载 arXiv 公开 PDF；venue 来自 arXiv comment，未独立核验；过滤 workshop/symposium/preprint/findings 与非 agent 标题；不是完整 proceedings 抓取
  - 综合矩阵每个主题至少覆盖 2 篇不同来源；未使用来源必须显式列出；不得把单篇结论写成领域共识
  - GLM-5.3-Flash 仅生成检索子查询：key 走环境变量，无 key/调用失败回退规则模板；输出只是查询串，不创建 Claim、不改证据边界
  - 覆盖不足必须显式进入 gap / brief.saturation；不能用摘要-only 或重复来源伪造“足够覆盖”
  - LiteratureBrief 只做结构化覆盖摘要与摘录，不新增 claim，不把 excerpt 当结论
---

# 文献调研子智能体（S1）

## Purpose

在 S1 阶段把研究问题变成可复核的检索与阅读证据：生成检索计划、来源候选、句级 span、覆盖回执与缺口。它只负责“找到并定位证据”，不负责提出假设、创建 Claim 或写论文。

## Contract

S1 输入 question → 输出 SourceHit/Span/CoverageReceipt/Gap/LiteratureBrief；fixtures 显式 fixture:true。S1b：synthesize_literature（模型驱动，需 DEEPSEEK_API_KEY 或注入 model port，产出 literature-synthesis-0.1）；synthesize_sources_deterministic（确定性词法共现，schema literature-synthesis-deterministic-0.1，每主题≥2 全文来源、span 级 evidence、stance 恒为 mixed、无全文 span 的来源进 excluded_sources 并 warning）。两者都只投影，不创建 Claim/EA/gate；主题不是语义综合，模型路径才是质量路径。

**候选论文发现（信息源层）**：`research_agent/adapters/paper_discovery.py` 汇聚三路信号 —— arXiv 关键词搜索（复用 `ArxivFetcher`）、Hugging Face Daily Papers、HF Trending（同一 `/api/daily_papers` 端点的 `sort=publishedAt` 与 `sort=trending`）。输出统一的候选清单，按归一化的 arXiv id 去重，并记录每路命中数与去重数。该层**只解决信息源**：每条候选恒标 `clue_only=true` / `span_eligible=false`，摘要与标题是线索不是证据，绝不生成 span、SourceHit、Claim/EA/gate，也不改变 Q0 判定。`allow_network` 默认 false，未授权时必须返回 `blocked` 而不是空清单或假装抓到；端点形态以 HF 官方文档为准，本环境未实测联网的部分必须如实标注。报告必须附「下载全文 → `literature run --source local --corpus-dir` 解析成 span」的可照抄后续链路，不得把「抓到多少篇」写成「证据够多少篇」。

**Stage1 候选预筛与评分（低成本过滤层）**：`research_agent/prescreen.py` 位于信息源层与证据层之间，对 `paper_discovery` 的 clue-only 候选做确定性两阶段处理：Stage1 按结构完整性与「标题 + 可选摘要」的 query 词法命中做硬过滤，每条拒绝必须带可核对的 `reason`（`missing_title` / `no_query_term` / `excluded_term`）；Stage2 用可解释的多信号加权分**只做排序**，不改变 kept 集合。摘要是**过滤输入**：由调用方以独立 `abstracts` 映射传入，只在内存里参与词法匹配，预筛输出**不得回显摘要文本**、不得落盘、不得生成 span / SourceHit / Claim / EA / gate。分数恒标 `ranking_signal_only=true`，不得充当 novelty / 研究质量 / 门禁判据（`innovation_review` 的模型 1–10 自评分在 `single_author` 下不是独立证据，不能作为先例）。预筛不联网、不用模型、不改 Q0、不改 S1 默认行为；报告给出 before→after 压缩比与 `next_commands`（下载全文 → `--source local` 解析）。被预筛保留仍只是**更值得下载**，不是「已具备证据资格」。

S1 必须在 `LiteratureResult.warnings` 中输出一条结构化的证据广度回执 `evidence_breadth=...`，显式声明本次检索的证据规模：去重后的独立来源数、全文来源数、span 数、`coverage_score`、`saturation`，以及 `review_grade=yes|no`。判据：独立来源 ≥ `TARGET_SOURCES`(6) 且全文 ≥ `TARGET_FULL_TEXT`(3) 且 span ≥ `TARGET_SPANS`(12) 且 `saturation=saturated` 才为 `yes`；`review_grade=no` 时必须附带可照抄的扩大语料命令（`literature run --source local --corpus-dir <dir> --max-sources 12` 或 `pipeline run --corpus-dir <dir> --max-sources 12`）。该回执是**披露**，不改变 `status`、不改变 Q0 判定、不阻断 S2、不写 Claim/EA/gate；默认 fixture 语料只有 3 条（2 全文），因此默认运行必然 `review_grade=no`，其 S2 候选只是流程演练，不构成文献综述级证据基础。S2 消费者应据此判断 idea 候选是否建立在足够来源之上。


## Current Implementation

- `research_agent/literature_synthesis.py`：多篇来源 → 主题×来源矩阵；模型提议主题，确定性校验每主题 ≥2 篇、引用真实来源、附证据 span；未使用来源显式记录；CLI `literature synthesize`、MCP `research_literature_synthesis`；

- `research_agent/adapters/arxiv_fetcher.py`：arXiv Atom API 搜索 + PDF 下载；用户显式 `--allow-network`；记录 `inputs/arxiv-sources.json`、PDF SHA256、arXiv URL 与 license note；不绕过付费墙；下载后使用 local PDF 解析；
- CLI `literature fetch`；MCP `research_literature_fetch`；只负责获取来源，不生成 span/claim；
- `research_agent/adapters/conference_fetcher.py`：按 venue/year 查询 arXiv comment，过滤 workshop/symposium/preprint/findings/非 agent 标题后下载公开 PDF；写 `inputs/conference-corpus.json|md` 与逐文件 SHA-256；CLI `conference fetch`、MCP `research_conference_fetch`；下载后仍须 `source=local` 解析成 span；

- `research_agent/modules/literature.py`：`LiteratureAgent`（可选 `query_planner`：给定 question 返回子查询列表，模型失败回退规则模板）；可选 `followup_plan` 在剩余预算内做一次 gap 驱动补检索并写 QueryPlan.followup_*；
- `research_agent/modules/literature.py`：`LiteratureAgent`（可选 `query_planner`：给定 question 返回子查询列表，模型失败回退规则模板）；
- `research_agent/models/`（本地模型网关）：provider = OpenAI / Anthropic / Azure OpenAI / OpenAI 兼容（含智谱 GLM）；`ModelProfile` 支持思考模式 off/effort/budget、上下文与输出上限、json_mode、extra_body 白名单；密钥只进环境变量或 runtime 内存，落盘自动扫描拒绝 secret 字段，错误自动脱敏；默认画像 `glm-flash`（zhipu/glm-5.3-flash）并绑定 literature 模块；
- `research_agent/adapters/glm_model.py`：`glm_query_planner()`（对任意 ModelPort：GLMModel 或 `GatewayModelPort`，即任何网关 provider）+ `gateway_query_planner()`（按模块绑定解析，缺 key/缺 profile 返回说明并回退规则，不抛错）；
- `research_agent/adapters/openalex_retriever.py`：`OpenAlexRetriever`，只读公共 OpenAlex API 实时检索（无 key）；礼貌池 mailto、限流 ≥0.12s、429/5xx 退避重试、30s 超时、重试耗尽抛 `OpenAlexError`；摘要由 `abstract_inverted_index` 重建；`full_text()` 恒为 None（不自动抓全文），SourceHit 附 OA 链接；`fixture_mode=false`；
- `research_agent/adapters/fixture_retriever.py` / `real_corpus_retriever.py` / `minilm_retriever.py`：本地 fixture / 冻结 CC-BY 正文 BM25 / 本地 frozen embedding；
- `research_agent/adapters/local_document_retriever.py`：用户本地 PDF/TXT/MD 全文，PDF 按页提取并保留 `page`；可选 `.meta.json` 提供 title/year/venue/license；空文本不伪装全文；不 OCR、不联网；
- `research_agent/adapters/simple_parser.py`：PDF/文本换行归一（合并硬换行、修复连字符断词、跨空行小写续行）后按中英文句末标点切句，避免把版面行当成证据；同一小节内合并缩写、十进制小数和标签造成的伪断句；生成 span 时保留页码与偏移；
- CLI：`literature run --source openalex --planner gateway|glm|rule|profile:<id>`、`literature run --source local --corpus-dir <dir>`、`pipeline run --openalex` / `--corpus-dir <dir>`；无 key 时 planner 自动回退规则并在 stderr 说明；
- fixture 输出标 `fixture_mode=true`；真实语料/OpenAlex 输出 `fixture_mode=false`；
- 不创建 claim_drafts，不写 Claim/EA；spec version 从本文件 frontmatter 读取，并写入运行结果。


## Boundaries

- 摘要只能作为 `SourceHit` 线索，不能生成 `Span`；
- 默认不联网、不调用模型；OpenAlex/GLM 只在显式参数或 adapter 下启用，并在本文件登记权限/限流/错误；
- 真实语料只用于 harness/检索评估，不能直接作为论文 Claim 证据；需要经过 Q0/Claim Curator；
- 不创建 Claim、不写 manuscript、不做题目推荐；
- fixture 不是真实文献，不能引用为论文证据；
- S1 的输出要经过 Q0/Claim Curator 才能进入后续阶段。


## Minimal Change Workflow

1. 先改本文件 `Contract` 或 `Current Implementation`；
2. 升 `version`，在 `## Changelog` 追加说明；
3. 最小化改 `LiteratureAgent`/adapter，不碰其他模块；
4. 加/改 `tests/test_literature.py` 与 `tests/test_specs.py`；
5. 跑 `python -m unittest discover -s tests -v`。

## Changelog

- 2026-11-08 · v0.12.0 · status=pilot · Stage1 低成本候选预筛与可解释排序（信息源层与证据层之间）：用户参考「标题与摘要级 Stage1 预筛压缩候选集合，再做候选评分」后复核，现有 conference_fetcher._topic_score 已有标题+摘要词法命中的先例、fixture/local retriever 有检索排序，但没有独立 Stage1 层；上一轮 paper_discovery 故意不存摘要（摘要不能当证据），因此预筛必须用「摘要只作内存过滤输入、输出不回显不落盘」的方式接。新增 research_agent/prescreen.py 纯函数：Stage1 结构完整性 + query 词法命中硬过滤，每条拒绝带可核对 reason；Stage2 可解释多信号加权分只做排序、不改变 kept 集合；报告给压缩比、score_range 与后续下载→--source local 链路。CLI literature prescreen。边界：不联网、不用模型、不改 Q0、不改 S1 默认行为、不生成 span/SourceHit/Claim/EA/gate；分数恒标 ranking_signal_only，不得充当 novelty 或质量判据（innovation_review 的模型 1-10 自评分不是独立证据）。通过预筛只表示更值得下载，不代表具备证据资格。新增 tests/test_prescreen.py 全离线用例。
- 2026-11-07 · v0.11.0 · status=pilot · 信息源层：多源候选论文发现（clue-only，不产 span）。用户参考「arXiv 关键词 + HF Daily Papers + Trending 抓取候选论文」后复核：现有已有 ArxivFetcher 关键词搜索与 literature fetch 下载、conference_fetcher 按 venue/year 抓 arXiv、OpenAlex 只给摘要；缺的是三路汇聚成统一候选清单并按 arXiv id 去重，且全库无 HF 相关代码。核实 HF 端点事实：Daily Papers 与 Trending 是同一 GET /api/daily_papers 的 sort=publishedAt / sort=trending 两种取值（官方文档），另有 /api/papers/{id} 取结构化元数据；本环境 curl 该端点 6 秒超时，故按文档实现、测试全部离线注入 transport，如实标注未实测联网。新增 adapters/paper_discovery.py 与 CLI literature discover；候选恒标 clue_only=true / span_eligible=false，allow_network 默认 false 且未授权返回 blocked 而非空清单；报告附可照抄的下载与 --source local 解析链路。边界：不生成 span/SourceHit/Claim/EA/gate、不改 Q0、不改 S1 默认行为；「抓到多少篇」不等于「证据够多少篇」。新增 tests/test_paper_discovery.py 全离线用例。
- 2026-11-06 · v0.10.0 · status=pilot · 证据广度回执（只改披露，不动门禁）：实测默认 fixture 把 max_sources 从 3 调到 50，来源数恒为 3、span 恒为 5、coverage_score 恒为 0.454、saturation 恒为 partial、Q0 恒为 pass；而用本地 7 篇 CC-BY 正文语料配 max_sources=12 可得 7 来源 / 56 span / 1.0 / saturated，Q0 仍是同一个 pass 理由。也就是说 Q0 的输出无法区分 3 篇演练语料与综述级语料，且两层 SPEC 都未规定最小来源数。Contract 新增 evidence_breadth 条款：S1 必须显式声明独立来源/全文/span/覆盖度/saturation/review_grade，未达综述级时附可照抄的扩语料命令。不改 status、不改 q0_decision、不阻断 S2、不写 Claim/EA/gate；Q0 加来源数下限属门禁语义变化，仍需人工确认，本轮未做。新增 tests/test_literature.py 三条用例钉住 3 篇判 no、7 篇判 yes、以及回执不改变 Q0 状态。
- 2026-10-28 · v0.9.0 · status=pilot · 新增确定性跨来源综合构建器 synthesize_sources_deterministic（词法共现、每主题≥2 全文来源、span 级 evidence、摘要-only 来源显式排除）；schema literature-synthesis-deterministic-0.1；供 pipeline 内建 S1b 使用，模型驱动综合仍走 writing pack 路径
- 2026-10-28 · v0.8.0 · status=pilot · 新增可选 `followup_plan`：首轮后按未覆盖面向生成变体查询，在剩余 max_sources 预算内补检索（最多 2 个新来源），去重并记录 followup_queries/sources/spans/budget；TaskAgent/pipeline 开启，证据边界不变。
- 2026-10-27 · v0.7.0 · status=pilot · 新增多篇文献综合矩阵：主题×来源、stance、一致点/张力/置信度、未使用来源；每主题至少两篇来源；写作包/创新评审/初稿共享该矩阵；不创建 Claim。
- 2026-10-26 · v0.6.0 · status=pilot · 新增顶会开放语料获取：按 venue/year 查询 arXiv comment，过滤 workshop/symposium/preprint/findings/非 agent 标题，下载 arXiv 公开 PDF 并写 corpus manifest/SHA；venue 来自 comment，未独立核验；不是完整 proceedings 抓取；下载不是证据。
- 2026-10-26 · v0.5.1 · status=pilot · 改进 PDF/文本句级解析：合并硬换行与跨空行续行、修复连字符断词、合并缩写/小数/标签造成的伪断句；span 仍保留页码与偏移，证据边界不变。
- 2026-10-26 · v0.5.0 · status=pilot · 新增 arXiv 文献获取：显式 `--allow-network` 搜索并下载 arXiv 公开 PDF 到项目 inputs，记录 provenance/SHA/license-note；下载后仍走 local PDF 解析与 Q0；不绕过付费墙、不把摘要当全文；CLI `literature fetch`、MCP `research_literature_fetch`。
- 2026-10-26 · v0.4.1 · status=pilot · 新增 derived `literature-ledger.json`：来源卡、全文/摘要/重复/元数据缺口筛选计数、DOI/年份覆盖、近五年分布与 source-level warnings；不改变 SourceHit/Span 契约。
- 2026-10-25 · v0.4.0 · status=pilot · 契约扩展：新增 local 来源（用户提供 PDF/TXT/MD，LocalDocumentRetriever）、PDF 页码锚点（Span.page）与本地 provenance；不 OCR、不联网，空文本不伪装全文。
- 2026-10-24 · v0.3.1 · status=pilot · 最小契约扩展：新增 `facet_subset`，允许编排器把六个检索面向切给并行 scout；严格拒绝未知/空面向与未开启 `coverage_plan` 的调用；query planner 只扩展 scout 已获授权的 `core`，不会把被排除的面向重新带回。检索与证据边界不变。
- 2026-10-24 · v0.3.0 · status=pilot · 覆盖规划升级：按 core/survey/method/evaluation/limitation/recent 六面向分配检索预算，新增 LiteratureBrief（facet 覆盖、source_briefs、section digest、coverage_score、saturation、gap）；预算耗尽/领域覆盖不足会显式记 coverage_cap_reached / thin_domain_coverage，不伪造来源；检索改为面向轮转，避免前序面向吃满 cap；恢复可选 query planner 接线，`literature run` 显式支持 `--source openalex` 与 `--planner glm`；OpenAlex 可选免费 `OPENALEX_API_KEY`（Bearer，不进 URL）并给出 429 配额提示；新规划由 `coverage_plan` 显式开启（pipeline/CLI），旧调用默认沿用既有的三子查询路径，保证 RSI 基线可复现。
- 2026-10-24 · v0.2.0 · status=pilot · 契约升级：接入真实检索与调研模型——新增 OpenAlex 只读检索 adapter（无 key、mailto 礼貌池、限流重试）与 GLM-5.3-Flash 检索规划器（OpenAI 兼容、环境变量 key、失败回退规则）；S1 证据边界不变（span-only、不创建 Claim）
- 2026-10-24 · v0.1.6 · status=pilot · 最小改进：静态登记调研智能体模型绑定 GLM-5.3-Flash（未接入 API；接入前须新增 adapter 并在本文件登记权限/限流/错误）；当前实现仍为本地 BM25/MiniLM，行为不变
- 2026-10-24 · v0.1.5 · status=pilot · 最小改进：增加 3 篇 held-out CC-BY transfer corpus（Agent Laboratory / The AI Scientist / SEAL）与 6 个新问题，仅用于 sealed 复核，不参与设计/准入
- 2026-10-24 · v0.1.4 · status=pilot · 最小改进：增加可选 MiniLM 冻结 embedding 检索（abstract 级，本地缓存、不训练）；BM25 仍为默认，MiniLM 作为独立 probe，不静默替换评分
- 2026-10-24 · v0.1.3 · status=pilot · 最小改进：RealCorpusRetriever 改为正文 BM25（k1=1.5,b=0.75），移除手调 keyword 权重；真实 probe 的 budget2/3 在 near-OOD 被拒，负结果保留
- 2026-10-24 · v0.1.2 · status=pilot · 最小改进：增加 RealCorpusRetriever 与冻结 CC-BY 论文正文语料，支持 fixture 之外的只读真实文本检索；仍为 span-only
- 2026-10-23 · v0.1.1 · status=pilot · 最小实现：FixtureRetriever + SimpleParser 已通过 10 个测试；仍为 S1 span-only，不创建 Claim。
- 2026-10-23 · v0.1.0 · 初始 fixture 版：QueryPlan → SourceHit → Span → CoverageReceipt；只做 S1，不创建 Claim。
