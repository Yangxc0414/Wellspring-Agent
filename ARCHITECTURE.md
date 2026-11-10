# 可扩展科研智能体架构

> 状态基线：2026-10-30。当前 39 个 MCP 工具、762 tests（两个互补半程判定）。
> 本文是架构主文档；`45-`/`47-` 是专题与调研附录，`49-` 是差异化设计，`50-` 是宿主模型交接（Host-as-Model）设计记录，`51-` 是可执行面与搜索研究，`52-` 是独立评审，`53-` 是声明式因子空间，`54-` 是闭环对 Agent 的下一步可见性，`55-` 是跨数据集复现计数，`56-` 是 TTME 记忆反馈的可移植子集，`57-` 是设计合理性与工程性自查；当前事实以本文、`README.md`、`integrations/README.md` 为准。

## 1. 设计目标

这套系统的目标不是“再做一个固定流程的论文生成器”，而是：

> **一个证据可审计、能力可插拔、流程可组合、能被多种 Agent 框架调用的科研运行时。**

稳定的是证据与门禁；可变的是工具、流程、期刊策略、实验环境和接入方式。

### 差异化定位（与已有科研智能体对照）

已有工作主要在优化生成吞吐与端到端自动化：Co-Scientist 系做假设锦标赛，AI-Scientist/ScientistTwo 系做端到端论文，RSI 系做改进准入，Skill 生态做流程复用。本系统不与它们正面争生成能力，而是补一层**可移植的证据闭合与治理运行时**，把四个判定连成一条链：

1. **资格判定**：句子必须落到已持有 span 或人签实验证据；稿件与写作包内容寻址绑定，包漂移即阻断；
2. **完成判定**：canonical run 与 local experiment 各有 closure profile，都必须人签；MCP/HTTP 不提供 sign/approve/freeze/publish；
3. **失效判定**：spec/data/code/execution/evidence/claim/results table/figure 以 SHA-256 串联；`research_closure_status` 只读返回 presence/SHA-256 链（含 support panel fingerprint）与 `chain_fingerprint`，`research_lineage_status` 只读重算 lineage 节点并给出 fresh/stale，用于发现"文件还在但已不是原来那一份"；
4. **供给判定**：生成能力可以由宿主 Agent 供给（`kind="host_agent"`，无外部 key），但提交结果与网关模型受同一套门禁约束——可移植的是模型，不可移植的是证据资格。

评审独立性不靠“多问几次同一个模型”：`research_support_panel` 把多个 judge profile 的逐句 verdict 做分歧账本，分歧项进入 `pending_human`，strict 下未裁决即阻断；run 目录存在 `support-panel.json` 时，canonical、local experiment 与 search study 三套 closure 的 `support_panel_ready` 都要求 ready/not_applicable，未裁决分歧不能人签；local 还要求 panel 的 draft hash 与最终手稿一致。profile id 由调用方提供，不能证明 provider 真的不同，kappa 也不是 human gold。

差异是这四件事的**交集**，不是每一列的首创；当前仍缺独立人类 gold、跨提供商评审、真实本地实验执行与 HPO，详见 [`49-差异化设计-证据闭合运行时与现有科研智能体对照.md`](49-差异化设计-证据闭合运行时与现有科研智能体对照.md)。证据链只证明存在性与身份，不证明正确性、语义蕴含、同行评审或可投稿。

## 2. 四层架构

```text
Kernel（稳定）
  project / artifact ledger / evidence / claim / gates
  permissions / audit / hashes / human approval
        │
Capabilities（可插拔能力）
  retriever / parser / local experiment runner / writer
  figure renderer / citation verifier / journal template
        │
Skills（流程与策略）
  literature-review / manuscript-revision / paper-writing
  review-panel / local-experiment
        │
Adapters（接入方式）
  MCP stdio / HTTP JSON / Python SDK / CLI
```

### Kernel：必须固定

以下内容不允许 Skill、插件或外部 Agent 绕过：

- Span-only 证据；摘要不能当全文证据；
- Claim/EA/Protocol/Gate/Signature/Closure/Export 的写权限；
- human gates（Q0/G1/G2/S5b/G5）；
- artifact hash、run capsule、artifact allowlist；
- 项目目录与路径越界校验；
- 工具权限、网络/脚本策略；
- 本地实验的执行授权与审计。

Kernel 的目标是“不信任任何模型或外部 Skill”，这也是系统的差异化。

### Capabilities：可插拔能力

能力是**有输入输出 schema 的工具**，不是一段提示词。当前已实现：

- `literature`：fixture / real / OpenAlex / local PDF·TXT·MD；
- `run`：内置 S5 协议验证（iris / breast_cancer / ChemLab，仅 demo）；
- `revision`：已有手稿读取、指标重算、bar/line 图、逐段改写、审计、MD/TeX/DOCX/PDF；
- `writing_pack` / `writing_audit`：run → 真实来源卡/span/写作契约；中文稿 → 引用/结果数值/章节/占位符预审；
- `conference_fetcher`：venue/year → arXiv 公开 PDF + corpus manifest；过滤 workshop/symposium/preprint/非 agent 标题；
- `literature_synthesis`：多篇来源 → 主题×来源矩阵，每主题至少两篇，记录一致/张力/未使用来源；
- `loop_ledger`：S0–S16 阶段、门禁、迭代次数与下一步的只读投影；
- `innovation_review`：缺口 → 候选 → novelty/evidence/feasibility 三评审 → 修订 → 再评审；
- `manuscript_writer` / `manuscript_review`：写作包+创新评审 → 初稿 → 审计；rubric 评审 → 修订 → 再评审；
- `experiment_codegen`：S4 设计 + 项目内 CSV → 自包含实验包（spec/runner/requirements/README/manifest）；只生成，不执行；
- `experiment_figures`：verified evidence → mean/std 数据结果图 + 证据绑定 manifest（matplotlib，`kind=data_result_plot`，非示意图）；
- `figure_workflow`：AstraDraw scene/模板 → SVG/PNG/audit/manifest（方法/框架示意图，`schematic=true`，不作为实验结果）；
- `external_skills`：外部 Skill advisory，本地 trusted script 显式 opt-in；
- `skill_distill`：外部 Skill → disabled 本地候选。

能力扩展的正确方向是 `CapabilityManifest`：

```json
{
  "schema_version": "research-capability-0.1",
  "id": "citation.verify",
  "version": "0.1.0",
  "input_schema": "schemas/citation-verify.input.json",
  "output_schema": "schemas/citation-verify.output.json",
  "entry": "adapter:verify",
  "permissions": {"network": false, "write": false, "local_exec": false},
  "evidence_eligible": false
}
```

**当前状态**：工具表仍在 `mcp_server.py` 中静态注册；`CapabilityRegistry` 是下一阶段高优先级改造，不是已完成能力。手册不要把它写成已经有动态插件市场。

### 自动化科研主循环（当前落地）

```text
S0 任务路由
  → S1 多源检索：若干论文 → SourceHit / Span / CoverageReceipt
  → S1b 多篇综合：主题 × 来源矩阵（一致点 / 张力 / 未使用来源）
  → S2–S3 创新评审：缺口 → 候选 → 三评审 → 修订 → 再评审
      ├─ review/position 分支：写作包 → 初稿 → 手稿评审/修订 → 审计 → 导出
      └─ empirical 分支：S4 设计 → G2 → S5 本地实验 → S5b 人签 Claim
                         → S8–S12 写作/评审 → G5 闭包
```

多篇文献不是“读一篇然后引用多次”，而是四个硬约束：

1. S1 检索多个来源，并保留 coverage/facet/gap；
2. S1b 综合矩阵的每个主题至少覆盖 2 篇来源，未使用来源必须显式列出；
3. 每个创新缺口/方向至少引用 2 个 REF，且来自 2 篇不同论文；
4. 手稿正文至少覆盖 5 个不同 REF，单一来源引用占比不超过 60%。

`literature_synthesis.py` 产出 `synthesis-matrix.json`，写作包、创新评审和初稿共享同一矩阵；`loop_ledger.py` 把阶段完成/跳过、门禁、创新/手稿迭代次数和下一步投影为 `research-loop.json`。`pipeline.py` 是 S1→Idea→Design→Run→Paper 的经典纵切：S1b 已内建为确定性投影（`synthesize_sources_deterministic`：词法共现、每主题≥2 全文来源、span 级 evidence、非语义综合），`PaperAgent` 在相关工作章节消费该矩阵；模型驱动的主题矩阵仍走 `literature synthesize` / writing pack 路径，作为质量路径。`scripts/topconf_research_article.py` 是 review/position 分支的样例。

跨进程恢复：`pipeline run --resume-dir <dir>` 从既有 run 输出目录拾取 `g1-decision.json`、`protocol.json`/`protocol-card.json`、`claim/claim.json`、`run/`（RunCapsule+EA）四类产物自动续跑；显式给出的 `--g1-decision/--protocol-file/--claim-file/--run-dir` 优先。拾取只复用既有产物，不改变任何门禁语义；G1/G2/claim 的签核仍在 CLI/人工流程。

### 想法必须可执行：executable 注册表

自动化科研最常见的失效不是流程中断，而是**流程跑通却产不出结论**：想法阶段生成关于搜索的假设，
执行阶段只会做一次固定拟合，于是实验计划字段被填成口径混淆的内容，论文的实验节成为虚构。

`research_agent/executable.py` 把"本运行时能检验什么"提升为一等对象，每个档位必须同时声明
`supports` 与 `cannot_test`：

| profile | 能检验 | 明确不能检验 |
| --- | --- | --- |
| `protocol_run` | 固定协议的种子波动、两固定配置均值比较 | 搜索/档案/门控效应；智能体自我修改 |
| `local_tabular_experiment` | 用户 CSV 上的监督对比与配对差区间 | 生成式或智能体行为；长程搜索 |
| `search_factorial` | 记忆 × 门控主效应与交互、谱系深度、单位验证算力改进率 | 智能体源码自改；任何已发表系统复现 |

三处强制：

1. **生成侧**：提示词注入各档位与其 `cannot_test`，模型看不到"随手编一个大规模基准"的空间；
2. **校验侧**：`experiment_plan.profile` 成为必需字段，dataset/metric 必须属于该档位，
   不匹配直接拒绝该想法（不是 warning）；
3. **批评侧**：feasibility 审稿人读同一份注册表，并以代码层的 `executability_check` 为准；
   novelty/evidence 审稿人不被注入执行信息，避免角色串味。

配套的 `search-study` 模块（`research_agent/search_lab.py`）提供第一个真正可执行的搜索实验台：
被改进对象是流水线配置（结构类比，`analogue=true`），首要指标是单位验证算力的改进率，并按种子
配对给出 95% 区间。**区间跨零即报告为不可判定**，不得用点估计冒充结论；evidence 采用与本地实验包
相同的 `metrics_summary`/`comparison` 形状，因此人签 claim 之前这些数字进不了论文结果节。

设计本身是**声明式**的：`SEARCH_FACTORS`（`memory`/`gate`/`operators`/`min_delta`）与
`OPERATOR_SETS` 是注册表，`study search --factors factor=level[,level]` 按声明的笛卡尔积建格，
第一个声明的水平即参照格；未知因子/未知水平/格子数超过 `MAX_DESIGN_CELLS=12` 直接拒绝，
未变因子不进入格名（否则已签署断言引用的 `memory_*`/`gate_*` 键会漂移）。随机流按完整控制集
播种，因此改动搜索代码后旧结论由 `code.unchanged` 失效是设计而不是回归。

实测结论见 `51-…`（改码前记录：负交互三号 −0.288/−0.106/−0.078，"门控提升效率"仅 iris 可判定为
正、breast_cancer 点估计为负，即该一般性主张被自己的数据推翻）与 `53-声明式因子空间-让搜索研究能
检验别的假设.md`（新流 64 种子复现：负交互三号**同号且仍可判定**，−0.0932/−0.1031/−0.1276；
门控开启时只改旋钮的算子空间在两号数据集上都显著更差，只改特征位的算子空间在 iris 可判定为优
（+0.1117）而在 wine **不可判定**）。

### 复现是按设计分块的计数，不是第二个因子

一个数据集上集训定不构成结论，而把 `dataset` 做成搜索因子是错的：比较永远对着参照格做，参照格
属于某个具体数据集，跨数据的"差值"同时混着回路差异与数据难度差异。`study_replication.py` 因此是
**只读的分块统计**：按 `{design, metric, budget, min_delta}` 哈希分组（种子数故意排除，改由
`warnings` 显式提示功效不等），判定复用 `comparison_verdicts` 而不重新推导，逐比较给出
`consistent / one_dataset_decided / undecided / conflict`，且 `generalizes` 仅当组内**每个**数据集
同向判定时为真；同数据集重复写归为 `unreplicated`（同数据是重跑不是复现）。它不重跑、不产 Claim、
不改 evidence 形状，所以已签署断言的引用键不受影响。实测（同一 2×2、16 种子 × iris/wine/breast_cancer）：
`memory_on_gate_on` 与交互项 `consistent(negative)`（各由两号数据集训定），`memory_on_gate_off`
仅 iris 判定故 `generalizes=false`，`memory_off_gate_on` 三处全跨零——"归档+贪婪门控一起用会伤害
搜索"是当前最可辩护的发现，而"只用归档就更好"被自己的数据判为不泛化。单数据集时 `next_actions`
追加 `study_replication`（含未试数据集与可原样执行的命令），出现第二个数据集后自行消失；
`closure profiles`/`/api/project-closures` schema 升 `closure-profiles-0.3` 带 `replication` 摘要。
见 `55-单数据集anecdote到跨数据集复现计数.md`。

### 评审独立性是可解除的状态，不是常量

Host-as-Model 下 novelty/evidence/feasibility 三个角色由同一宿主顺序回答，实测仅调阈值就能把结论
从 `needs_more_work` 翻成 `reviewed`。第一版修复只是**披露**（写死 `admission_eligible=false`），
但诚实的常量没有信息量：没有任何路径能让它变真。

现在 `research_agent/independence.py` 把角色回答者算成**供给指纹** `(provider_id, model_name)`，
并分两层判定：**配置层**要求三个角色落到互不相同的供给、且提案模型不兼任审稿（同 model 名的多个
profile 只算一个审稿人，所以"改配置"不能凭空造出审稿人）；**使用层**从宿主交接账本回读实际回答者
的 `host_label`，能否决配置层的结论。`innovation review --critic role=profile` 手工排席，
`--independent` 按 `critic_panel()`（`research_model_profiles` / `GET /api/host-model/panel`）
自动排席，供给不足时**直接失败并报告缺几个**，不静默退化成单作者评审；每条评审记录携带 `supply`，
分数事后可归因。实测：绑三个 model 互异的 host profile 后 `single_author_review` 被解除
（`distinct_supplies=3`），但账本显示三次批评都由同一宿主回答，`admission_eligible` 仍为 false。
详见 `52-独立评审-从披露到可解除.md`。

同理，写作契约的长度目标此前只写在提示词常量里，4740 字的稿子照样通过。现在 `LENGTH_TARGETS`
是 writer 与 audit 的同一来源，pack 记录 `length_target`，audit 输出 `han_character_count` 与
`length.chinese_characters`；可用 REF 少于 5 时多样性检查记为显式 `not_assessable` 而非静默跳过。



### Skills：流程与策略

Skill 负责“先做什么、后做什么、用什么检查”，而不是自己实现数字计算或门禁。

未来 Skill workflow 的结构：

```json
{
  "schema_version": "research-skill-0.1",
  "id": "manuscript-revision",
  "inputs": ["draft", "data", "metrics_spec", "figure_spec", "venue"],
  "steps": [
    {"tool": "revision.ingest"},
    {"tool": "revision.metrics"},
    {"tool": "revision.figures"},
    {"tool": "revision.rewrite", "optional": true},
    {"tool": "revision.audit"},
    {"tool": "revision.export"}
  ],
  "checks": ["citations_preserved", "no_new_numbers", "sentence_ledger"],
  "human_gates": []
}
```

**当前状态**：已有 built-in 只读 Skill、外部 Skill advisory、Skill usage/eval/version；但还没有通用 `SkillRuntime`。revision/figure 的编排仍在 Python 中。Skill Runtime 是下一阶段改造。

写作工作流是“Skill 编排 + 确定性能力”的当前样例：`research-workflow/SKILL.md` 规定 pack → draft → audit 的顺序与禁令，Python 只负责生成真实来源卡、span、数值策略与阻断。Qoder 可以自由写 prose，但不能绕过引用白名单、`allowed_result_numbers`、fixture 检查或章节检查。流程可改在 Markdown/Skill，证据与数字边界不能被提示词改写。

写作包现在有 `pack_id`/`pack_sha256`，生成稿带 pack marker；审计优先加载持久化 pack，marker 不匹配即阻断，避免“用 A pack 写、用 B pack 审”的漂移。`writing audit --semantic` 进一步把每个 `[REF-xx]` 句解析到 selected spans，输出 supported/partial/contradicted/insufficient 的句级支持账本；strict 下 contradicted/unresolved/insufficient 阻断，partial 保留为 warning。它是模型辅助判断，不是语义蕴含证明，也不是同行评审。

同一个 run 的实证文章走 `empirical` 闭环：`empirical check` 先验证 literature/synthesis/innovation 与本地实验属于同一 run，且 evidence=verified、claim 已人签；`empirical paper` 才生成写作包（`experiment_id`）、初稿、可选多轮评审，并把手稿审计重新绑到 experiment closure。它在人工审阅与签名前停止，不执行实验、不签 claim、不签 closure、不投稿。跨 run 或未签 claim 的实验证据不能被拼进同一篇文章。

### Adapters：接入方式

已实现且共用同一 MCP 工具契约（数量随版本增长，**当前 41**，以 `tools/list` 为准）：

- MCP stdio：Qoder / Claude Code / Zcode / Codex；
- HTTP JSON：`/api/research/capabilities`、`/api/research/tools/{tool}`；
- Python SDK：`ResearchAgentClient` / `LocalResearchAgent`；
- CLI：本地人工门与调试。

适配器不得复制业务逻辑。`framework_api.py` 是唯一 dispatch 层。

### 生成能力从哪来：Host-as-Model

证据与门禁必须固定，但**模型接入不该固定**。过去所有生成步骤都要一个外部 provider key；
这把"谁生成了这段文字"推到系统之外，也让接入任何 Agent 框架前先要配一遍密钥。

本系统把生成能力反转：绑到 `kind="host_agent"` 的 profile 时，运行时**不发网络请求**，
而是产出一份可审计的**交接物** `ModelTurn`，交给当前调用本系统的宿主 Agent（Qoder /
Claude Code / Codex / Zcode）用它自己的模型完成。

```text
模块需要一次生成
  → HostModelPort（仍是同一个 ModelPort 接缝）
  → 落一条 pending ModelTurn：请求原文 + messages_sha256 + 期望形状 + TTL
  → 抛 ModelTurnPending（显式挂起，禁止静默降级成模板）
  → 宿主用 research_model_turns 读回提示词，用自己的模型作答
  → research_model_respond 提交：按请求哈希绑定、形状校验、一次性消费
  → 重跑同一步：find_by_hash 命中已答 turn，直接重放答案
```

这条路径带来三件此前没有的事：

1. **零外部 key 的完整闭环**。`python -m research_agent host-model bind` 之后，S1→S2→S4
   的生成步骤全部经宿主作答；实测两个阶段交接、作答、重放并推进到 `completed`，
   G1 仍是人工门（`scripts/host_model_loop_test.py`，6 项检查全过）。
2. **挂起即续跑**。答案按**请求哈希**而不是 turn id 复用，所以任何中途停下的流程
   都能靠重跑同一条命令继续，不需要 checkpoint 机制。
3. **宿主被视为不可信能力**。提交的内容只是能力输出：span-only、引用白名单、
   `allowed_result_numbers`、章节与 fixture 审计、支持面板、闭包校验一律照旧；
   `research_model_respond` 不是人工门，不能 approve/claim/sign/freeze/publish。

边界：`host_label` 是宿主自报且未验证，不能据此主张模型独立性或质量；多轮评审阶段会排队
多个 turn，需要批量作答；账本缺失或不可读时消费端 fail-closed。

## 3. 当前可扩展点

| 扩展点 | 当前状态 | 增加方式 | 是否改内核 |
| --- | --- | --- | --- |
| 替换 idea/experiment 模块 | 已实现 | `module_overrides` / `module_factories` | 否 |
| 新增 MCP/HTTP/Python 工具 | 工具表静态 | 改 `mcp_server.py` + `framework_api` + tests | 是（待 CapabilityRegistry） |
| 新增 AstraDraw 模板 | 代码映射 | 改 `figure_workflow.TEMPLATES` | 是（计划改 JSON registry） |
| 新增期刊模板 | 代码 profile | 改 `revision_templates.py` | 是（计划改 JSON registry） |
| 外部 Skill advisory | 已实现 | `skill scan/enable/invoke` | 否 |
| 外部 Skill 蒸馏 | 已实现 | `skill distill` / `--distill-on-success` | 否 |
| 声明式 Skill workflow | 未实现 | `SkillRuntime` roadmap | 待实现 |
| 实验代码生成 | 已实现（只生成） | `experiment scaffold`；自动执行/探索仍 roadmap | 否 |
| 任意本地实验环境 | 未实现 | `LocalExperimentRunner` roadmap | 待实现 |
| 新技术来源 | 代码 adapter | 新增 `RetrieverPort` 实现 | 是 |
| 换掉生成模型供给方 | 已实现 | 绑定 profile：外部 provider key **或** keyless `host_agent`（宿主 Agent 出模型） | 否 |
| 新增可执行实验类型 | 已实现（注册表驱动） | 扩 `executable.py` 的 profile 并同时声明 `supports`/`cannot_test`；想法校验与 feasibility 审稿人自动跟随 | 否 |
| 自进化参数被运行时消费 | 已实现（单目标） | `rsi propose→admit→lease→active`，每次消费复查租约；regressed 确认自动撤销 | 是（目标仍只有两个已注册 scope） |
| 递归改进的执行引擎 | 已接通 Harness²（确定性夹具） | `rsi harness2 run` → `harness2-run-0.1` → 候选；换引擎只改桥，不改判据 | 否 |
| 自进化本身的版本管理 | 已实现（双轨台账） | `rsi gen` 的 snapshot / agent / verify；agent 记树 SHA，platform 记代码指纹；跨轨靠 `platform_fingerprint` 关联 | 否 |

这张表是“可用性”的核心：**不要把 roadmap 写成已经支持。**

## 4. 本地实验的目标契约

当前 S5 只是内置协议验证。真实实验应通过独立 runner，在用户本地环境中执行：

```json
{
  "experiment_id": "EXP-001",
  "environment": {
    "kind": "conda",
    "name": "my-research",
    "command_prefix": ["conda", "run", "-n", "my-research"]
  },
  "command": ["python", "train.py", "--config", "configs/main.yaml"],
  "cwd": "experiments/exp-001",
  "timeout_sec": 7200,
  "expected_outputs": ["metrics.json", "figures/"],
  "seeds": [1, 2, 3],
  "human_reason": "approved protocol"
}
```

目标行为：

- 智能体不安装依赖，不假设自己的 Python 环境；
- 使用用户指定的 conda/uv/docker/命令前缀；
- 执行前需要人工 G2/执行确认；
- 记录命令、环境指纹、git commit、stdout/stderr、artifact SHA-256；
- 论文结果只能来自该 runner 的实际产物或人签 claim；
- 本地执行默认只走 CLI；MCP/HTTP 不暴露任意命令执行。

**当前状态：生成实验包 + CLI approve/run/ingest/claim 已实现；自动启动与多配置探索尚未实现。**

```bash
python -m research_agent experiment approve --project <project> --experiment-id <EXP-ID> --human-reason "approved protocol"
python -m research_agent experiment run --project <project> --experiment-id <EXP-ID> --allow-execute --timeout 7200
python -m research_agent experiment ingest --project <project> --experiment-id <EXP-ID>
python -m research_agent experiment claim --project <project> --experiment-id <EXP-ID> \
  --statement "..." --human-reason "..." --assertion "metric=accuracy,value=0.85,comparator=>=,tolerance=0.01"
```

- 只允许本地 CLI；MCP/HTTP 不暴露执行或签核；
- run 前必须有 approve 记录并显式 `--allow-execute`；环境使用白名单变量，不自动装依赖；
- execution.json 记录命令、环境、stdout/stderr、artifact SHA；ingest 校验哈希后写 experiment-evidence.json；
- evidence 不是 RunCapsule/EA/Claim；claim 只能由 CLI 人签，并绑定 evidence hash；
- `experiment closure/lineage` 是独立的本地实验 profile：校验 data/spec/code/approval/execution/metrics/evidence/claim，人工签名后才可验 lineage；它不是 RunCapsule/EA-based closure；
- 自动探索（多组配置/HPO）需要额外的预算、停止规则和 artifact allowlist，仍未实现。

### Closure 的三套 profile：统一语义，不混用产物

| profile | 适用对象 | 命令 | ready 状态 | 人工门 |
| --- | --- | --- | --- | --- |
| `canonical_run` | S5 pipeline 的 RunCapsule + EA + 人签 Claim | `closure check/sign/publish` | `ready` | `closure sign` |
| `local_experiment` | `experiments/<EXP-ID>` 生成包 + 本地执行证据 + 人签 experiment Claim | `experiment closure/sign` | `ready_for_human_signature` | `experiment sign` |
| `search_study` | `studies/<dataset>` 搜索研究包 + 人签 study Claim | `study closure/sign/lineage` | `ready_for_human_signature` | `study sign` |

三套 profile 共用 `closure_profiles.py` 的词汇与边界：都只做结构化闭合、都必须人工签署、都 `submission_ready=false`、都不替代同行评审；一套 profile 的报告不能冒充另一套。`closure profiles` 只读查看注册表；`closure profiles --project <dir>` 或 `research_status` 的 `closure_profiles` 盘点项目里已存在的产物，只给下一步建议，不重跑、不签核。选择规则只有一条：按证据产物类型选 profile，不能把本地实验 evidence 升级成 EA，不能把 RunCapsule 降级成本地实验，也不能把搜索研究伪装成前两者。

`search_study` 额外把两件事纳入闭合条件：**功效**（`power.sufficient`、`has_decidable_comparison`：区间全部跨零的研究不能被关闭成"结论"）与**代码不变性**（`code.unchanged`：`study-spec.json` 记录搜索代码指纹，改动 `search_lab.py`/`executable.py`/`study_claims.py` 之后旧结论不能再被引用）。`study lineage --verify` 会在 spec 被改写（例如换种子或改预算）时把对应节点标为 stale，签名动作在报告不再 ready 时直接拒绝。

### 自进化的返回边：升级人签，降级自动

```text
observe → propose（必须命中已注册 scope）→ dry-run + public/hidden/near-ood/regression
        → 人签 admit → lease → activate（人签理由）
        → 运行时消费：每次 resolve 都重读源租约
        → 后置确认 regressed ⇒ 自动 revoke ⇒ 下一次消费即回到 incumbent
```

三条硬规则：

- **可被消费的目标必须先在 `SAFE_SCOPES` 注册**，`activate` 会调用准入 scope 门；未注册或被关掉的命名空间不能因为"有租约"就进入运行时；
- **撤销立即生效**：`ActivePolicyStore` 在每次 `resolve/snapshot` 重读源租约，账本缺失或不可读时 fail-closed，不再等到 TTL；
- **只有降级可以自动**。`record_confirmation` 遇 `regressed` 自动撤销对应 active 租约；通过确认不产生任何升级作用，确认本身永远不是准入输入。

`rsi revoke` 之后 UI/HTTP 只读视图会显示 `auto_deactivated` 与 `lease_state`，激活记录中的账本路径不对客户端暴露。

## 5. Skill 与扩展的安全规则

1. Skill 不能直接写 Claim/EA/gate/signature/export；
2. 外部 Skill 默认只读 advisory；脚本只在本地 CLI 显式 `--trusted-scripts`；
3. 扩展只能调用白名单工具；权限由 runtime 决定，不由 Skill 声明自行授予；
4. 高权限扩展必须有版本、license、输入/输出 schema 和负例评测；
5. 扩展候选默认 disabled，必须人工启用；
6. 任何“自动研究/自动投稿”都不得绕过人工门。

## 6. 可用性路径

| 目标 | 入口 |
| --- | --- |
| 5 分钟验证接入 | [`QUICKSTART.md`](QUICKSTART.md) |
| Qoder / Claude / Zcode | [`integrations/README.md`](integrations/README.md) |
| HTTP / LangGraph / CrewAI / AutoGen | [`integrations/FRAMEWORKS.md`](integrations/FRAMEWORKS.md) |
| 模块契约与新增模块 | [`modules/README.md`](modules/README.md) |
| 当前状态与组会 | [`组会汇报-科研智能体进展与下一步.md`](组会汇报-科研智能体进展与下一步.md) |

## 7. Roadmap

1. `CapabilityRegistry`：声明式工具注册，MCP/HTTP/Python 自动发现，移除静态 `TOOLS` 复制。
2. `SkillRuntime`：声明式 workflow + check，把 revision 编排从 Python 移到 Skill。
3. `VenueProfile` / AstraDraw template JSON registry：新增期刊/模板不改 Python。
4. `LocalExperimentRunner`：表格数据 profile 已落地（codegen/approve/run/ingest/claim/closure/lineage，均由用户在本机执行与人签）；下一阶段是任意实验环境 adapter 与一次真实 study 闭环。
5. `ReviewPack`：句级支持账本、多票、A/B 与多 judge 分歧/裁决面板已落地；下一步用真实跨提供商 profile 跑面板并公开分歧，仍只是投稿前评审。
6. 外部 held-out / human blind eval：没有这一步，不能声称论文质量提升。
7. Canonical lineage 校验：local experiment 已有只读 fresh/stale；下一步把同一校验扩展到 canonical run 与图 manifest。
8. Host-as-Model 下一步：批量作答（一次提交多个 turn）、turn 级配额与过期治理、把 sink 写入接到写作包绑定的草稿上；以及把 judge/support panel 也接到宿主供给，用于无 key 的多评审分歧账本。
9. 搜索研究接入闭包：✅ 已完成——`study claim` 只接受区间排除零的比较，`search_study` 作为第三套 closure profile 串起 spec→study→evidence→claim→report→signature 哈希链，闭合条件含功效与搜索代码不变性，`study closure --verify` 报告 fresh/stale。下一步是把同一 lineage 校验扩到多数据集研究之间的对比，以及 `search_factorial` 因子空间的声明式扩展。
10. 可执行面注册表成为 S5 的能力目录：让 `run`/`experiment` 的可用档位从注册表读取，而不是各自维护一份数据集清单。

## 8. 不能宣称

- 当前不是”任意领域全自动科研系统”；
- 当前不支持任意本地实验环境；
- 当前不是期刊官方模板；
- 当前不是同行评审；
- 当前没有动态插件市场；
- 当前没有多租户/公网 SaaS 鉴权；
- Host-as-Model 不证明宿主真的用了它自报的模型：`host_label` 自报且未验证，答案的质量与独立性都不能由交接机制担保；
- 自进化目前只在两个已注册的过程参数上闭合（检索预算、S5 种子），且都是**降级自动、升级人签**；不得表述为”系统已能自我提升能力”；
- 宿主作答让流程”能重跑续上”，但这不是断点恢复框架：状态在 turn 账本里，不在进程里；
- `search_factorial` 改进的是**流水线配置**而非智能体代码：它是结构类比，其结论不能迁移到 DGM/SICA/ACE/SIFT，也不能被写成对这些系统的复现或反驳；
- 多角色评审在同一模型供给下是**多提示词**而非多审稿人：`single_author_review=true` 的分数不是独立证据，更不是准入依据；
- 区间跨零即”不可判定”：不得用点估计、也不得靠调低阈值把不可判定说成成立。

这些限制写在架构层，而不是藏在 README 角落。
