---
name: wellspring-research
description: 通过 Wellspring-Agent 的 MCP 工具执行受治理的科研流程（文献调研、创新评审、实验设计、证据闭合状态、投影与下一步）。当用户要求做文献综述、研究假设、实验设计、写证据包、查看 closure/lineage/RSI 状态，或询问某条结论能否被签署时使用。人工签核、协议冻结、发布与导出只在本地 CLI，不通过本 Skill 执行。
---

# Wellspring-Agent · WorkBuddy 接入

这个 Skill 只规定**如何调用**已经存在的 MCP 工具，不改变任何业务逻辑：不新增工具、不改门禁、不写 Claim/EA/Protocol/Signature。

## 前置条件

- MCP server `wellspring-agent` 已在 WorkBuddy 的自定义连接器中「信任」并启用。
- 服务端指向 `Wellspring-Agent/` 目录，使用 Python 3.8 解释器（依赖见 `requirements-runtime.txt`）。
- 接入自检：`python integrations/workbuddy/check.py`（只读，不启动服务、不写文件）。
- **首次调用前必须建项目**：发行目录里默认没有 `research-project/`，而 `research_literature_*`、`research_innovation_review`、`research_writing_pack` 等工具都要求项目目录已存在；直接调用会收到 `project directory does not exist`。先执行 `research_project_init`，或用 `research_bootstrap` 一次性初始化。
- **项目名要一路带下去（实测）**：`research_project_init` 用默认名 `research-project` 时，后续工具可省略 `project_dir`；若用了自定义名（如 `my-project`），**之后每一个项目级工具都必须显式传同一个 `project_dir`**，否则仍会去找默认目录并报同样的错。推荐直接用默认名。

## 调用纪律

1. 先建项目：`research_project_init`（推荐 `project_dir: "research-project"`）→ 记下项目名，之后每个项目级工具都带上它 → 再 `research_host_contract` 读回 blocked / next_commands，决定走工具面还是 handoff 面。
2. 只调用 `TOOL_NAMES` 里的工具；未知工具由 dispatch 直接拒收。
3. 所有项目产物写在用户工作区内的项目目录，不写到运行时代码目录。
4. `fixture` 输出只能用于流程验证，不得当作真实证据；摘要-only 来源只作线索，不生成 span。
5. 读 idea 产物时先看两处披露：S1 的 `evidence_breadth=`（证据规模是否达到综述级）与 idea 的 `source_mode=`（`fixture` 表示候选来自合成 S1 span，不是研究证据；`real` 仍需 Q0 / Claim Curator）。两者都不能替代人工门。
6. 遇到 `needs_human` / `needs_evidence` / `failed`，如实报告，不要说「已完成」。

## 文献调研与 idea：当前能做什么（实测）

MCP 工具面**没有**「输入问题直接返回 S1 spans/coverage」的工具，也**没有**「输入 spans 直接生成 idea」的工具。实测 `TOOL_NAMES` 里 literature 只有 `research_literature_fetch`（arXiv 下载，必须 `allow_network=true`）与 `research_literature_synthesis`（需要已有 `run_id`）；idea 侧只有 `research_innovation_review`（需要 `run_id` + 模型供给 + full-text spans）。

因此按顺序选择：

1. **完整 S1→S2**：`research_project_init` → `research_run`（`TaskAgent` 产出 `literature.json` / `idea.json` / `idea-review.json` 到 `<project>/runs/<RUN-ID>/`）→ `research_status` / `research_list_artifacts` 读回。默认 `flow_mode=review`，Q0 blocked 只写 warning 不会停；需要停在门禁前就用 `flow_mode=strict`。
2. **只要 S1 结果**：在用户本机用 CLI `python -m research_agent literature run --question "<问题>" --max-sources 4`，它离线跑 fixture、把 `fixture_mode` / `coverage.gaps` / `brief.saturation` 打到 stdout，**不落盘**。不要把这份输出当成真实文献。
3. **只要 idea**：`research_innovation_review` 需要模型供给；无 key 时用 `host-model` 交接（`research_model_turns` / `research_model_respond`），或直接用本机 CLI 的 `pipeline run` / `study from-idea`。

不要向用户宣称「已通过 MCP 完成一次文献调研」——除非确实跑过 `research_run` 并从产物里读回了 spans。`fixture_mode=true` 的结果必须原样标注为演练。

## 信息源：候选论文发现（0.11.0，clue-only）

`literature discover` 汇聚三路公开信号，解决「候选论文从哪来」：

```
python -m research_agent literature discover --query "<关键词>" --allow-network
```

- `arxiv`：复用已有的 `ArxivFetcher` 关键词搜索；`hf_daily` 与 `hf_trending` 是**同一个** HF 端点 `GET /api/daily_papers` 的 `sort=publishedAt` / `sort=trending` 两种取值（依据 Hub API 文档）。按归一化的 arXiv id 去重，并记录每路命中数与去重数。
- **默认不联网**：不加 `--allow-network` 返回 `status=blocked` 和明确错误，不会返回空清单冒充「没找到」。可用 `--sources hf_daily,hf_trending` 只取 HF 两路。
- **这一层只解决信息源**：每条候选恒为 `clue_only=true` / `span_eligible=false`，标题与元数据是线索**不是证据**；不产 span / SourceHit / Claim / EA / gate，不改 Q0。报告 `next_commands` 给出可照抄的后续链路：`literature fetch --allow-network` 下载公开 PDF → `literature run --source local --corpus-dir <dir> --max-sources 12` 解析成 span。抓到多少篇 ≠ 证据够多少篇。
- HF 候选**不自动下载全文**（需确认许可并自行取得）；无付费墙绕过。MCP `research_run` / 工具表暂无对应的候选发现工具，属接入面缺口。
- **诚实边界**：本环境对 `huggingface.co/api/daily_papers` 的一次轻量探测 6 秒超时，端点形态按官方文档实现，测试与探针全部离线注入 `transport`，**未实测联网抓取**。离线探针 `runtime_data/probe-paper-discovery-20261107.py` 可复跑。

## Stage1 预筛与排序（0.12.0，低成本过滤）

`literature prescreen` 对候选清单做确定性两阶段处理，位于**信息源层与证据层之间**：

```
python -m research_agent literature prescreen --input <candidates.json> --query "<问题>" \
  --abstracts <id-to-abstract.json> --exclude-terms "<排除词>" --output <report.json>
```

- **Stage1 硬过滤**：结构完整性 + 标题/摘要的 query 词法命中（`--min-hits` 可设阈值），每条拒绝带可核对 reason（`missing_title` / `no_query_term` / `excluded_term`）。中英文 query 都可切词。
- **Stage2 只排序**：可解释加权分（`title_hits×3 + abstract_hits + 多来源 + 有 PDF`），`rank_signals` 逐项可核；**不改变 kept 集合**，恒标 `ranking_signal_only=true`。
- **摘要是过滤输入，不是证据**：由 `--abstracts` 单独提供，只在内存里参与匹配，输出**不回显摘要文本**、不落盘、不生成 span / SourceHit / Claim / EA / gate。`passing Stage1 = 更值得下载 ≠ 具备证据资格`。
- 报告给 `input_count → kept_count` 压缩比、`by_reason`、`score_range` 与后续可照抄链路（`literature fetch --allow-network` → `literature run --source local --corpus-dir`）。不联网、不用模型、不改 Q0、不改 S1 默认行为。
- **不要**把 Stage2 分数当 novelty / 研究质量 / 门禁：`innovation_review` 的模型 1–10 自评分在 `single_author` 下不是独立证据，不是可援引的先例。
- 离线探针 `runtime_data/probe-prescreen-20261108.py` 串起「信息源 → 预筛 → 排序」：5 条候选 → 3 条（压缩 0.4），摘要救回 1 条标题不相关的候选，摘要文本不出现在报告里。

## 文献规模：先扩语料，再谈 idea（实测）

**默认运行里没有「搜很多篇」这回事**：默认 fixture 语料只有 3 条（2 全文 + 1 摘要），`--max-sources` 从 3 调到 50，来源数恒为 3、span 恒为 5、`coverage_score` 恒为 0.454、`saturation` 恒为 `partial`。Q0 对这 3 篇演练语料和 7 篇全文语料都返回 `pass`，理由也只报全文数/span 数，因此**不能用 Q0 判断 idea 的证据基础**。

S1 现在在 `warnings` 输出 `evidence_breadth=...`：独立来源数、全文数、span 数、`coverage_score`、`saturation`、`review_grade=yes|no`。判据是 ≥6 独立来源 / ≥3 全文 / ≥12 span 且 `saturated`。`review_grade=no` 表示 S2 候选只是流程演练，不是文献综述级结论，并附可照抄的扩语料命令。这是**披露**，不阻断 S2、不改 Q0。

要真的基于多篇形成 idea，按以下顺序（命令在本机 CLI 执行，用 Python 3.8）：

1. 把已取得的 PDF / TXT / MD 全文放进一个目录（可选同名 `.meta.json` 提供 title/year/venue/license）。本地检索器按文件哈希作 source_id、按页/句切 span，不联网、不 OCR、不把空文本当全文。
2. `python -m research_agent literature run --question "<问题>" --source local --corpus-dir <dir> --max-sources 12`（纯离线，无条件可跑）
   完整链路：`python -m research_agent pipeline run --topic "<问题>" --corpus-dir <dir> --max-sources 12`。**实测前提**：无模型 key / 无 host model 供给时这条命令**不会跑完** —— S2 停在 `awaiting host model ... (module=idea purpose=S2 idea candidates)`，退出码 3、不产出 run 产物（宿主模型交接机制，不是故障）。要么 `research_host_contract` → `research_model_turns` 查看 → `research_model_respond --turn-id ... --file answer.json` 回答后重跑同一命令（replay 复用已答 turn），要么只用第 2 条取 S1 结果。
3. 读 `evidence_breadth`：`review_grade=yes` 才说明证据广度达到 S1 自带判据；再读 idea 产物的 `source_mode=` 确认来源不是 fixture。

实测基准：把发行目录内 7 篇 CC-BY 冻结正文导出成本地 txt，`--max-sources 12` → **7 来源 / 56 span / coverage 1.0 / saturated / review_grade=yes / fixture_mode=false**；同一语料 `--max-sources 3` → 3 来源 / 24 span / 0.675 / partial。

**边界**：`--source openalex` 只返回摘要元数据、`full_text()` 恒为 None，S1 会记 `full_text_unavailable` gap、0 span、Q0 blocked，**不能当证据来源**；`research_literature_fetch` / `research_conference_fetch` 只下载 PDF，下载后仍须 `--source local --corpus-dir` 解析成 span。给 Q0 加「最小来源数」下限属于门禁语义变化，本轮未做。

### 自动扩检索（0.48.0，仅本机 CLI）

不想手工调 `--max-sources` 时，可让 S1 覆盖判定自己决定下一轮预算：

```
python -m research_agent pipeline run --topic "<问题>" --corpus-dir <dir> --max-sources 3 --adaptive-retrieval
```

- 纯函数 `decide_next_cycle`：`partial` / `insufficient` → 下一轮预算翻倍（上限 30）；`saturated` 立即停；轮数或预算耗尽标 `exhausted` 并写明「需人补语料」，**不假装收敛**。
- 每轮观测与决策写进 `events.ndjson`（`cycle_observed` / `cycle_expanded` / `cycle_converged` 或 `cycle_exhausted`），产物带 `adaptive_cycle` 投影与一行 `adaptive_cycle=` 回执。
- 实测（7 篇 CC-BY 全文）：**3 来源 / 24 span / 0.675 / partial → 6 来源 / 48 span / 1.0 / saturated**，2 轮收敛；idea 候选引用的独立来源 3 → 5。
- **边界**：只改检索预算；不跨人工门、不写 Claim/EA/gate/signature、不置真 `submission_ready`、不编造语料；默认关闭，既有 run 行为逐字不变。**MCP `research_run` 目前没有这个开关**（接入面能力缺口，属契约变化，未做）。这是证据广度的结构性改进，不等于创新点质量更好。

## 大规模真实语料 → 跨来源创新点（实测）

**WorkBuddy 侧的可照抄路径**：发行目录不带语料（0 个 PDF），但 `research_run` 的 `source="local"` 会读 `<project>/inputs/` 下的 PDF/TXT/MD（`mcp_server.py:746, 2960-2975`），`max_sources` 范围 1–30、默认 6。

1. 把真实全文放进 `<project>/inputs/`：可用 `research_literature_fetch`（需 `allow_network=true`，`max_results` ≤10）或 `research_conference_fetch`（`max_papers` ≤80）下载，或由用户自行放入 PDF/TXT/MD。
2. `research_run` 传 `goal` + `source="local"` + `max_sources=30`。**实测**：`task_type="literature_review"` 可离线 `completed`，产出 `literature.json` / `q0.json` / `literature-ledger.json`，`fixture_mode=false`。
3. **S2 的诚实边界**：`task_type="hypothesis_design"` 与 `full_research` 实测都停在 `awaiting_host_model ... (module=idea purpose=S2 idea candidates)`，需 `research_model_turns` → `research_model_respond` 回答后重跑；本轮未实测完整续跑。本机 CLI 的规则路径（无模型时的候选生成路径）可直接产出候选。

**实测规模基准**（开发根 CLI / Python API，用项目内 30 篇真实 arXiv PDF，无需联网）：

```bash
python -m research_agent literature run --question "<问题>" --source local --corpus-dir agent-reliability-survey/inputs --max-sources 30
python runtime_data/probe-breadth-20261106.py
```

S1 得 **30 独立来源 / 240 span / coverage 1.0 / saturated / `review_grade=yes` / `fixture_mode=false` / Q0 `pass`**。改前 S2 的 3 个候选各自 4 条证据全来自同一篇论文、跨来源候选 **0**（`max_candidates=8` 仍是 0）；`modules/idea/SPEC.md` 0.21.0 把系统已挑出的异源 `contrast_refs` 计入 `evidence_refs`（簇内 3 + 对照 1，≤4）并让 `source_count` 按实际来源统计后，变为 **3/3 跨来源候选**、`IdeaBrief.multi_source_candidates=3`、`idea_review` 全判 `multi_source`、`no_multi_source_candidate` gap 消失。注意：本轮修的是**离线规则路径**；WorkBuddy 的 S2 走模型 proposer，未改其候选生成。

**0.22.0 起「综合」可追溯**：`pipeline` 把 S1 的 `coverage.gaps` / `brief.gaps` / `facets` 与 S1b 跨来源主题矩阵组成 `gap_pack` 传给 S2。候选现在带 `gap_ref`（仅当 `evidence_refs` 命中主题 `stances[].evidence` 时绑定 `theme:<id>`，否则 `unbound` / `none`）与 `relation_type`（`single_source` / `contrast` / `theme_co_occurrence` / `unclassified`）。离线 S1b 的 `tension` / `agreement` 恒空，因此**不会**谎报 tension/agreement；`synthesis_breadth=` 回执与 `no_scientific_gap_in_s1` gap 会如实说明「S1 只有检索回执与词法共现主题，没有科学缺口」。实测 30 篇语料下 3/3 候选真绑定到跨来源主题。这只让综合可追溯，**不是语义综合，也不是质量提升**。

**0.23.0 起候选结构自查**：同一 run 内对照证据不复用（实测 30 篇语料下不同对照来源 1→3），representative 优先取有句末标点的实质句而非论文题名 / 作者行；`warnings` 新增 `idea_structure=` 回执，报出不同对照来源数、唯一否证条件数 / 候选数、`needs_metric` 数，并明确「模板帧不含变量、预期方向或预注册指标，不是研究假设」。**读 idea 时要把这条回执当作「尚未成形」的信号**：当前离线规则路径产出的是可追溯的候选框架，不是可直接拿去做实验的科学假设。S1 的 span 里仍有约 56% 疑似题名 / 作者 / 地名等噪音（`literature` 模块未过滤），引用前需人工核对。

**0.24.0 起 idea 能承载可证伪预测**：`IdeaCard` 新增 `prediction`（十槽位：`variable/direction/condition/profile/dataset/metric/controls/seeds/stopping_rule/criterion`）、`prediction_status`（`testable` / `cannot_test` / `not_testable_here`）与 `open_slots`。判定是纯函数，以 `executable.py` 的 `validate_plan` 为唯一权威，**不用词法猜研究对象**。规则路径绝不编造变量，一律 `not_testable_here` + 列出全部 10 个 `open_slots`；模型 proposer 给出的结构化槽位现在原样保留（此前 10/10 供给 → 0/10 保留），填齐且在册才 `testable`，档位外或槽位不全为 `cannot_test`。`idea_structure=` 回执报 `prediction_status` 分布。**默认离线语料（agent reliability / LLM-judge）不在任何可执行档位**，默认仍是 `not_testable_here` —— 这是正确结果不是故障；要得到 `testable` 需档位内研究问题 + 模型或人给出预测。G1 是否拒收 `not_testable_here` 尚未实现（门禁变化，需人裁）。

**回答 host-model turn 时（0.24.1）**：`IDEA_SYSTEM` 现在允许在候选里给**嵌套 `prediction` 对象**，字段为上述十槽位，且只在研究对象确属已注册档位时才填；不确定或不在册就**省略** `prediction`，不要编造 `profile/dataset/metric`。`research_model_respond` 的 `expects` 只要求 JSON、不拒绝额外字段，十槽位能穿过交接面到 `IdeaCard`。填齐且在册 → `testable`；档位外或槽位不全 → `cannot_test`；不给 → `not_testable_here`。默认离线语料仍不在册，所以「宿主不给预测」是常见且正确的结果。

**「足够好」不能宣称**：`novelty_status` 恒 `unverified`，`IdeaResult` 无质量指标，`idea_review` 只是 advisory 词法预审，`innovation_review` 的 1–10 分是模型自评；仓库**没有独立留出集与人工评分**（`ARCHITECTURE.md:400-415`、`58-交付验收清单.md:123-124`）。本轮只让「候选建立在几篇独立文献上」变得**可判定**，新增的 `candidate_breadth=` 回执也显式写明「no novelty proof / G1 stays a human signature」。不要把跨来源候选数说成创新点质量。

## 绝对不做

- 不签 claim、不冻结 ProtocolCard、不签 closure、不发布 bundle、不批准 gate。
- 不通过 MCP/runtime 调用 approve、sign、freeze、publish、export 类动作。
- 不把模型输出当作人签结论；不在参数里传 API key（密钥只来自环境变量）。
- 遇到人工门时：把 `research_status` → `closure_profiles` 给出的 CLI 命令原样交给用户，由人在终端执行。

## 能力面速查

- 调研/来源：`research_literature_fetch`、`research_literature_synthesis`、`research_conference_fetch`
- 想法与评审：`research_innovation_review`、`research_manuscript_review`、`research_support_panel`
- 写作与审计：`research_writing_pack`、`research_manuscript_audit`、`research_manuscript_draft`
- 状态与证据：`research_status`、`research_closure_status`、`research_lineage_status`、`research_evolution_status`
- 宿主模型交接：`research_model_turns`、`research_model_respond`（不是人工门）

工具总数以服务端 `tools/list` 为准，不要在 Skill 里写死数量。
