# `research_agent/` — 可运行科研智能体底座

当前是一个**可运行的 test 模式纵切**，不是最终产品。test 模式默认离线、fixture 驱动、允许规则模板回退；**production 模式必须配置 API key、模型绑定，且所有必需模块完成模型接线，否则 runtime 直接拒绝运行**。模型网关仍是唯一的外部调用边界：

```text
S1 文献 → S2–S3 假设 → S4 实验设计 → S6 SVG 绘图 → S8–S12 论文契约
                                      └──────────→ 基金申报（可选）
```

核心不是“多接几个模型”，而是每个模块都有 Markdown SPEC、明确输入/输出、不可越过的证据边界，并由 CLI 以最小 diff 更新规格。

## 流程模式：review vs strict

- `review`（test 模式默认）：生成完整“待审包”，把 Q0/G1/G2 作为报告与证据包状态展示，适合 demo/回归。
- `strict`（production 强制）：Q0/G1/G2 是执行控制流；证据不足、未选 idea、未冻结协议时停在对应阶段，并留下可续跑产物。

```bash
# 1) S1/S2 产出 idea.json 后，人工选择并写 G1 decision
python -m research_agent flow g1 --idea-file <out>/idea.json \
  --idea-id IDEA-01 --human-reason "selected for protocol"

# 2) S4 产出 experiment.json 后，先冻结 design（不要求 RunCapsule）
python -m research_agent protocol freeze-design \
  --design <out>/experiment.json --limitation "single dataset" \
  --human-reason "checked design and stopping rule" --output-dir <out>/protocol

# 3) strict 续跑：带 G1 + frozen protocol 执行 S5
python -m research_agent pipeline run --topic "..." --flow-mode strict \
  --g1-decision <out>/g1-decision.json --protocol-file <out>/protocol/protocol-card.json \
  --run-dataset iris --run-seeds 3 --output-dir <out2>

# 4) 人签 claim 后，复用已有 run 续跑结果槽（不要重新跑出一个新 EA）
python -m research_agent pipeline run --topic "..." --flow-mode strict \
  --g1-decision <out>/g1-decision.json --protocol-file <out>/protocol/protocol-card.json \
  --run-dataset iris --run-dir <out2>/run --claim-file <signed-claim.json> --output-dir <out3>
```

runtime 的 `POST /api/runs` 也接受 `flow_mode`、`g1_decision_file`、`protocol_file`、`claim_file`；路径必须位于仓库或 runtime data 内。提供已签 `claim_file` 时，pipeline 写出 demo 后会自动运行 `closure check` 与 `lineage build/verify`，写 `postprocess.json`，但仍不签核、不提交。签署仍然只能在 CLI/人工流程完成。

项目级实验链只读接口：`GET /api/projects` 列出仓库内（含 `runtime_data/` 下一层）带 `project.json` 的项目及 experiment 数；`GET /api/project-experiments?project_dir=<relative>` 返回每个 `experiments/<EXP-ID>` 的真实 stages、next_action 与 evidence summary。路径必须保持在仓库内，不暴露绝对路径；接口不执行、不签核、不改证据。

## 结构

```text
research_agent/
  contracts.py        # 跨模块数据契约
  ports.py            # RetrieverPort / ParserPort
  specs.py            # SpecStore：解析、校验、原子更新、章节 patch
  flow.py             # review/strict 流程门禁、G1 decision、protocol hash 校验
  evidence_packages.py# S1–S13 证据包状态汇总（UI/任务报告共用）
  postprocess.py      # 已签 claim 后的 closure/lineage 后处理（不签核）
  pipeline.py         # fixture 纵切编排
  rsi.py              # 受治理的 RSI 控制面：ledger / policy / lease / archive / MetaTracker
  research_runner.py  # fixture 研究队列：pipeline → observations
  rsi_proposer.py     # FrozenModelProposer：ModelPort → 受治理候选
  rsi_fixture.py      # 本地 TF-RSI fixture 回路：public/hidden/near_ood/regression
  rsi_fixtures/       # 合成任务包（仅机制测试）
  modules/
    literature.py     # S1：检索 → span → coverage/gap
    idea.py           # S2–S3：span → 带否证条件的候选
    experiment.py     # S4：DesignCard / 预注册检查
    figure.py         # S6：scene → AstraDraw SVG + audit
    paper.py          # S8–S12：WritingProfile / sections / pending slots
    grant.py          # NSFC/NSSFC 骨架与合规清单
  adapters/
    fixture_retriever.py
    simple_parser.py
    astradraw_renderer.py
    svg_audit.py
  vendor/astradraw/   # 完整复制自本地 AstraDraw；上游无根许可证，不再分发
  runtime/            # 本地 FastAPI：真实 pipeline / SSE / 产物 / 只读 RSI / model gateway
  models/             # OpenAI / Anthropic / 兼容端点网关；密钥只进 env 或 runtime 内存
  project.py          # 研究项目目录：project.json / runs / inputs / 越界校验
  mcp_server.py       # stdio MCP：Qoder / Claude Code / Zcode 接入；无签核工具
  manuscript.py       # 中文投稿工作稿：编号引用 / GB/T 7714 风格 / 确定性审计
  design_audit.py     # S4 设计/统计完整性清单（不替代 G2）
  idea_review.py      # S2–S3 词法预审（grounding/falsifiability/testability）
  run_contract.py     # S5 run contract + artifact allowlist 核验
  obligations.py      # closure append-only obligations
  skill_lint.py       # 静态 Skill manifest/path/script 检查（不执行）
  external_skills.py  # 外部 Skill advisory + 显式 trusted script 调用
  skill_distill.py    # 外部 Skill → disabled 本地候选（provenance/license/hash）
  revision.py         # 已有手稿修订：模型改写/引用数字防篡改/审计
  revision_io.py      # MD/DOCX/TEX 解析，CSV/XLSX 数据，MD/TeX/DOCX/PDF 导出
  revision_figures.py # 数据表 → bar/line PNG/SVG
  revision_templates.py # 中文期刊工作模板 profile（非官方）
  figure_workflow.py  # AstraDraw scene/模板 → SVG/PNG + audit
  web/                # 静态 Module Workbench（无 API）
modules/<id>/SPEC.md  # 每个模块的唯一契约源
integrations/        # 平台接入说明与 MCP 配置示例
site/live/            # 前端 Live 页：连接本地 runtime，非 SIM
site/models/          # 模型接入页：Provider / Profile / 思考 / Probe / Binding
```

## 运行

```bash
# 先规划任务，再执行最小必要阶段
python -m research_agent task plan \
  --goal "帮我做一轮钙钛矿界面钝化的文献综述" --type auto --source fixture
python -m research_agent task run \
  --goal "帮我做一轮钙钛矿界面钝化的文献综述" --type literature_review \
  --source fixture --output-dir runtime_data/tasks/literature

# 用户提供本地全文（PDF/TXT/MD，PDF 保留页码）
python -m research_agent pipeline run \
  --topic "passivation humidity stability" --language en --venue en_conference \
  --corpus-dir runtime_data/corpus --writer off \
  --output-dir research_agent/web/data/local-fulltext

# 生成 fixture 纵切 + SVG + Workbench 数据
python -m research_agent pipeline run \
  --topic "钙钛矿 界面 钝化 稳定性" \
  --venue zh_core_journal \
  --grant nsfc \
  --primary-metric "湿热稳定性" \
  --control "未钝化对照" \
  --output-dir research_agent/web/data

# 启动工作台
python -m research_agent web --port 8010
# http://127.0.0.1:8010/

# RSI 控制面：候选只写 pending；真实 trial 的 strict admission 需要四类 sealed 证据、哈希与 approver；撤销自动收回 capability claim
python -m research_agent rsi propose   --kind skill --target literature.query_planner   --patch "add review subquery" --rationale "thin coverage"   --predicted "one more full text" --dry-run-ref "DRY-001"
python -m research_agent rsi status
python -m research_agent rsi trace --ledger research_agent/web/data/rsi-chemlab-v2/ledger.json --scope S5/demo/chemlab --capsule research_agent/web/data/rsi-chemlab-v2/leased-run/run-capsule.json --confirmation research_agent/web/data/rsi-chemlab-v2/confirm/s5-confirmation.json

# runtime observation → advisory suggestion → human activate → 下一轮 job 消费（激活只走 CLI；MCP/runtime 只读）
python -m research_agent rsi observations show --limit 20
python -m research_agent rsi observations suggest --output research_agent/web/data/observation-proposal.json
python -m research_agent rsi active show
python -m research_agent rsi active activate --ledger research_agent/web/data/rsi-real-ledger.json --lease-scope S1/rsi-ccby-4-compare --reason "human approved bounded budget policy"
python -m research_agent rsi active deactivate --reason "restore incumbent"

# 研究队列 → observations
python -m research_agent research run   --tasks research_agent/rsi_fixtures/research_tasks.json   --output-dir research_agent/web/data/research-queue

# 研究 → observation → TF-RSI：默认 pending；--approve 后租约驱动 research-under-lease
python -m research_agent rsi research-cycle   --tasks research_agent/rsi_fixtures/research_tasks.json   --ledger research_agent/web/data/rsi-ledger.json   --output-dir research_agent/web/data/research-cycle

# 单独的 TF-RSI fixture 回路
python -m research_agent rsi fixture   --ledger research_agent/web/data/rsi-ledger.json   --output-dir research_agent/web/data/rsi-fixture --approve

# 租约后 sealed 复核：不回流选择/准入
python -m research_agent rsi confirm   --ledger research_agent/web/data/rsi-ledger.json   --output-dir research_agent/web/data/rsi-confirmation

# 4 篇 CC-BY 论文正文上的真实文本 probe；默认 pending
python -m research_agent rsi real-trial   --ledger research_agent/web/data/rsi-real-ledger.json   --output-dir research_agent/web/data/rsi-real

# 可选：本地 frozen MiniLM 做 abstract 级语义检索（人工指定的独立 probe）
python -m research_agent rsi real-trial   --ledger research_agent/web/data/rsi-mini-ledger.json   --output-dir research_agent/web/data/rsi-mini --retriever minilm

# 预注册候选集对比：bm25+budget2 vs minilm+budget3，由 gate 选择
python -m research_agent rsi real-trial   --ledger research_agent/web/data/rsi-compare-ledger.json   --output-dir research_agent/web/data/rsi-compare --retriever compare

# 人签后把 active harness lease 回灌真实 pipeline
python -m research_agent pipeline run   --topic "How do self-improving coding agents use archives?"   --language en --venue en_conference --use-lease   --ledger research_agent/web/data/rsi-compare-ledger.json   --output-dir research_agent/web/data/real-pipe-lease

# 本地 frozen proposer：Qwen2.5-0.5B-Instruct（Apache-2.0，权重不入库）
python -m research_agent rsi propose-model   --model-path ~/.cache/qwen-rsi/Qwen2.5-0.5B-Instruct   --observation "Public BM25 baseline recall=1.0, cost=21, gaps=0; paraphrase-heavy questions may lose coverage."   --out research_agent/web/data/model-proposal.json
python -m research_agent rsi real-trial   --candidate-file research_agent/web/data/model-proposal.json   --ledger research_agent/web/data/rsi-model-ledger.json   --output-dir research_agent/web/data/rsi-model

# 多 observation 的 prompt 稳定性审计（1/3 eligible，2/3 near-OOD 拒绝）
python -m research_agent rsi model-batch   --model-path ~/.cache/qwen-rsi/Qwen2.5-0.5B-Instruct   --observations research_agent/rsi_fixtures/model_observations.json   --output-dir research_agent/web/data/model-batch   --ledger-root research_agent/web/data/model-batch-ledgers

# 人签后用 4 个新问题做 sealed 保留检查
python -m research_agent rsi real-confirm   --ledger research_agent/web/data/rsi-compare-ledger.json   --lease-scope S1/rsi-ccby-4-compare   --output-dir research_agent/web/data/rsi-real-confirmation

# held-out 3 篇新论文 / 6 个新问题的迁移复核
python -m research_agent rsi real-confirm   --ledger research_agent/web/data/rsi-compare-ledger.json   --lease-scope S1/rsi-ccby-4-compare   --tasks research_agent/rsi_fixtures/transfer_tasks.json   --corpus modules/literature/fixtures/transfer_corpus.json   --output-dir research_agent/web/data/rsi-transfer-confirmation

# S5 本地协议验证：run → RunCapsule/EA → 人签 Claim
python -m research_agent run execute --seeds 3 --output-dir research_agent/web/data/run
python -m research_agent run claim --capsule research_agent/web/data/run/run-capsule.json --ea research_agent/web/data/run/ea.json --statement "..." --human-reason "..." --scope S5/demo/iris --output-dir research_agent/web/data/run-claim

# 把 supported claim 绑定到 paper result.primary（仅 bound_claim，不写数字）
python -m research_agent pipeline run --topic "Iris protocol validation" --language en --venue en_conference --claim-file research_agent/web/data/run-claim/claim.json --output-dir research_agent/web/data/paper-bound

# S5 seed-budget 改进：iris（breast_cancer 用 --dataset breast_cancer）
python -m research_agent rsi s5-trial   --ledger research_agent/web/data/rsi-s5-ledger.json   --output-dir research_agent/web/data/rsi-s5

# 人签后 run 实际消费 S5 seed lease
python -m research_agent run execute --use-lease --ledger research_agent/web/data/rsi-s5-ledger.json --lease-scope S5/demo/iris --output-dir research_agent/web/data/run-s5-lease

# 4 个新协议实例的 S5 sealed 复核
python -m research_agent rsi s5-confirm --ledger research_agent/web/data/rsi-s5-ledger.json --output-dir research_agent/web/data/rsi-s5-confirmation

# 用 S5 lease 跑 pipeline：真实 run + claim draft；人签 claim 后再 --claim-file 绑定
python -m research_agent pipeline run   --topic "Iris protocol validation"   --language en --venue en_conference   --use-s5-lease --s5-ledger research_agent/web/data/rsi-s5-ledger.json   --output-dir research_agent/web/data/pipeline-s5

# ChemLab 真实反应数据：Ridge/Morgan 指纹 → RunCapsule/EA → claim draft
python -m research_agent pipeline run   --topic "ChemLab reaction conversion baseline"   --language en --venue en_conference --run-dataset chemlab --run-seeds 3   --output-dir research_agent/web/data/pipeline-chemlab

# 核验 DataCite 元数据快照
python -m research_agent bibliography verify --source modules/literature/fixtures/bibliography.json --output-dir research_agent/web/data/bibliography

# 冻结 protocol（G2 人签）
python -m research_agent protocol freeze --design research_agent/web/data/pipeline-chemlab/experiment.json --capsule research_agent/web/data/pipeline-chemlab/run/run-capsule.json --limitation "single public dataset" --human-reason "checked design/capsule" --output-dir research_agent/web/data/protocol

# 闭合检查与签署
python -m research_agent closure check --demo research_agent/web/data/pipeline-chemlab-bound/demo.json --claim research_agent/web/data/run-claim/claim.json --output-dir research_agent/web/data/closure
python -m research_agent closure sign --report research_agent/web/data/closure/closure-report.json --demo research_agent/web/data/pipeline-chemlab-bound/demo.json --claim research_agent/web/data/run-claim/claim.json --human-reason "checked all slots" --output-dir research_agent/web/data/export
python -m research_agent closure check --demo research_agent/web/data/pipeline-chemlab/demo.json --claim research_agent/web/data/run-claim/claim.json --output-dir research_agent/web/data/closure

# 用已签 claim 和同一 run-dir 重新绑定（避免 EA 不匹配）
python -m research_agent pipeline run --topic "ChemLab reaction conversion baseline" --language en --venue en_conference --claim-file research_agent/web/data/run-claim/claim.json --run-dir research_agent/web/data/pipeline-chemlab/run --output-dir research_agent/web/data/pipeline-chemlab-bound

# 在冻结 CC-BY 正文上跑真实 S1→paper 纵切（无 API/run/EA/claims）
python -m research_agent pipeline run   --topic "How do self-improving coding agents use archives?"   --language en --venue en_conference --real-corpus   --output-dir research_agent/web/data/real-pipe

# 查看/最小更新模块规格
python -m research_agent spec list
python -m research_agent spec show figure
python -m research_agent spec update figure --version 0.1.1 --status pilot --changelog "..."
python -m research_agent spec patch figure --section "Current Implementation" --text "..."
```

## 在 Qoder / Claude Code / Zcode 中使用（MCP）

三端共用同一个 stdio MCP 服务，产物落在用户指定的项目文件夹：

```bash
# 创建项目目录（inputs/ runs/ protocols/ claims/ closure/ notes/）
python -m research_agent project init --dir research-project

# 真实 stdio 演示：初始化、文献综述、strict 假设任务（停在 G1）
python scripts/research_mcp_demo.py \
  --project runtime_data/integrations/mcp-demo-project \
  --output runtime_data/integrations/mcp-demo
```

- Qoder：项目级 `.mcp.json` + `.qoder/skills/research-workflow/SKILL.md`
- Claude Code：`.mcp.json` + `.claude/skills/research-workflow/SKILL.md`
- Zcode：设置 → MCP 服务器 → stdio；配置见 `integrations/mcp/zcode.mcp.json`
- 工具：`research_project_init` / `research_plan` / `research_run` / `research_status` / `research_list_artifacts` / `research_read_artifact` / `research_next_actions` / `research_skill_list` / `research_skill_invoke` / `research_skill_distill` / `research_manuscript_revise` / `research_figure_templates` / `research_figure_render` / `research_literature_fetch`；
- MCP **没有** sign/approve/freeze/publish 工具；G1/G2/S5b/G5 仍由人在 CLI 完成；
- MCP 进程只读自己的环境变量与 model store，不共享浏览器 runtime 的 session key；
- 详细说明见 [`integrations/README.md`](../integrations/README.md) 与根目录 `45-` 设计文档。
- 其他智能体框架：启动本地 runtime 后使用 `GET /api/research/capabilities`、`POST /api/research/tools/{tool_name}`，或使用 `research_agent.client.ResearchAgentClient` / `LocalResearchAgent`；MCP、HTTP、Python 共用同一套 35 个工具契约。非 loopback 访问必须设置 `RESEARCH_AGENT_API_TOKEN`。示例见 [`integrations/FRAMEWORKS.md`](../integrations/FRAMEWORKS.md)。真实 HTTP 桥接演示：`python scripts/framework_bridge_demo.py`，产物在 `runtime_data/integrations/framework-bridge-demo/`。

## 已有论文修订与投稿包

`revision` 不是从 topic 重新生成论文，而是读入已有手稿和实验数据，保留原有实验叙事与引用，做数据指标重算、数据图重画、逐段改写和投稿工作包导出：

```bash
# 只检查解析/数据/图表，不改写
python -m research_agent revision inspect \
  --draft manuscript/01-投稿版-数字引用.md --output-dir runtime_data/revision-inspect

# 有 profile 才调用模型改写；否则 copy mode
python -m research_agent revision run \
  --draft runtime_data/revision-demo-input/paper.md \
  --data runtime_data/revision-demo-input/results.csv \
  --metrics runtime_data/revision-demo-input/metrics.json \
  --figures runtime_data/revision-demo-input/figures.json \
  --venue software_journal --profile <runtime-profile-id> \
  --output-dir runtime_data/revision-demo-output
```

输出包括 `revision-plan.json`、`revision-diff.json`、`revision-audit.json`、`sentence-ledger.json`、`metric-results.json`、`figure-manifest.json`、`revised-manuscript.md`，以及 `export/manuscript.{md,tex,docx,pdf}`。模型改写会拒绝新增数字、丢失引用、删除实验数字/图表编号的段落；被拒绝的段落回退原文并进入 blockers。`sentence-ledger.json` 逐句记录引用、图表引用、数字和匹配的数据指标；它标出缺口，但不做语义蕴含证明。`submission_ready` 始终为 false；`software_journal`/`computer_journal` 是工作模板，不是官方模板，投稿前仍需替换官方模板并人工复核。

无 key 演示：`python scripts/manuscript_revision_demo.py`，产物在 `runtime_data/revision-demo-output/`。

## AstraDraw 方法示意图

仓库已 vendored AstraDraw，原 `AstraDraw-main` 不需要修改。CLI：

```bash
python -m research_agent figure templates
python -m research_agent figure render   --template framework-example   --output-dir runtime_data/figure-demo   --title "Example Framework"   --description "AstraDraw scene rendered by the research agent"
```

输出 `scene/svg/png/audit/manifest`；MCP 对应 `research_figure_templates` / `research_figure_render`。模板只是视觉/版式先验，输出标 `schematic=true`，不是数据图、不是证据、不是发表许可；可编辑 PPTX 仍需本地 AstraDraw Node/presentations 环境。

## 中文投稿工作稿与审计

`pipeline` 在 `paper.md` 之外额外生成：

- `literature-ledger.json`：S1 来源卡与筛选账本（全文/摘要-only/重复/元数据缺口、DOI 与近五年覆盖、peer-review 状态 unknown）；
- `manuscript.md`：标题、结构化摘要、关键词、章节、GB/T 7714 风格参考文献；
- `manuscript.json`：编号引用映射、关键词、引用清单；
- `manuscript-audit.json`：章节/摘要/关键词/引用/数字/claim/fixture 的确定性审计，含 `submission_ready`；
- `argument-ledger.json`：逐句的 section / refs / numbers / supported / needs_evidence；
- `claim-registry.json`：claim×ref×anchor evidence rows、quote/SHA-256、词法候选覆盖率（semantic completeness=unknown）。

```bash
python -m research_agent pipeline run \
  --topic "钙钛矿界面钝化 湿热稳定性" --venue zh_core_journal \
  --bibliography-file <verified-bibliography.json> --claim-file <signed-claim.json> \
  --output-dir runtime_data/manuscript-run
```

边界：这是“投稿工作稿 + 结构性审计”，不是期刊模板，也不是同行评审。缺全文、缺已签 claim、引用未核验或存在待补占位时，`submission_ready` 必须为 false；它只说明稿件是否满足我们定义的可提交条件，不保证期刊录用。

## 确定性质检

- `route_decision`：TaskPlan 记录路由信号/置信度；`RESEARCH_AGENT_STRICT_ROUTING=1` 时模糊任务要求指定 task_type；
- `idea-review.json`：S2–S3 词法预审（证据 grounding、来源多样性、否证条件、可测指标、lens、是否复述证据），输出 advance/revise/reject，不替代 G1；
- `design-audit.json`：S4 必需字段、seeds/controls 与统计计划（effect size / power / randomization / 多重比较 / CI / 缺失数据 / 敏感性）清单；`incomplete` 阻断的是清单，不是自动 G2；
- `run-contract.json` / `run-contract-check.json`：绑定 protocol/dataset/seeds/metric 与 artifact allowlist，核验 capsule/EA/evidence hash 与必需产物；有 paired baseline 时计算 `min_delta` 并与预注册阈值比较，无 baseline 标 `not_verifiable`；
- `obligations.json`：closure 未通过项进入 append-only obligations；报告消失只标 `unverified_disappearance`，不会自动 resolved；必须 `closure obligations resolve --evidence` 或 `waive --reason` 显式关闭；
- `loop-capsule.json`：只读闭环投影（S1→S2–S3→S4→S5→S6→S8–S12→S13→META），列出节点状态、blockers、bounded next_actions 和 artifact_refs；同 run 的 `experiments/<id>` 会把 evidence/claim/closure/signature 阶段投射到 S5/S13；MCP `research_status` / `research_next_actions` 直接返回 capsule；缺失不是通过，不创建证据/claim/gate/signature/closure；
- `python -m research_agent skill lint --path .qoder/skills`：静态检查 frontmatter、名称/描述、正文行数、重复名称、越界链接与 scripts 中的 eval/exec/os.system/subprocess 等危险调用；不执行脚本。

外部 Skill：advisory、脚本全权限与本地沉淀：

```bash
# 1) 无脚本 Skill：只发指令+输入给模型，输出 advisory
python -m research_agent skill invoke \
  --skill-id <enabled-skill-id> --profile <runtime-profile-id> \
  --input-file runtime_data/task.md --output runtime_data/skill-advice.json

# 2) 带脚本 Skill：只有显式 opt-in 才在本地执行；不是 sandbox
python -m research_agent skill invoke \
  --skill-id <enabled-skill-id> --trusted-scripts --workdir <dir> \
  --script-arg --check --script-arg evidence \
  --input-file runtime_data/task.md

# 3) 成功调用后沉淀为 disabled 本地候选（也可单独 distill）
python -m research_agent skill invoke \
  --skill-id <enabled-skill-id> --profile <runtime-profile-id> \
  --input-file runtime_data/task.md \
  --distill-on-success --distill-reason "reuse for claim review"
python -m research_agent skill distill \
  --skill-id <enabled-skill-id> --human-reason "reuse for claim review" \
  --library-dir runtime_data/skill-library

# 4) 人审候选后再启用（候选生成时始终 disabled）
python -m research_agent skill enable <local-candidate-id>
```

- instruction-only 只允许 enabled 且无 scripts 的 Skill；不授予 allowed-tools、不联网、不写 Claim/EA/gate，输出为不可信 advisory，写 `SkillUsageRecord`；
- trusted script 继承当前环境与 OS 权限，可访问文件/网络，超时与输出有上限；结果仍不是证据；
- 蒸馏要求 enabled + license + human_reason，复制 `SKILL.md` 与完整 `scripts/references/assets`（排除隐藏文件/缓存）及逐文件 SHA-256，注册 disabled `local-*` 候选；不自动启用、不证明质量；同一 source hash 幂等；
- MCP 只暴露 instruction-only advisory、列表与蒸馏，不执行外部脚本、不自动启用候选；脚本全权限只在本地 CLI；
- 无 API key 也能跑通脚本调用与蒸馏：`python scripts/external_skill_demo.py`，产物在 `runtime_data/integrations/external-skill-demo/`（调用回执、脚本 proof、完整 candidate、summary）。

## 本地 Runtime 与前端 Live

静态 Pages 只做展示；真实执行需要本地 runtime（默认 `127.0.0.1:8787`）：

```bash
pip install -r requirements-runtime.txt
python -m research_agent.runtime --port 8787
python -m http.server 8000 --directory site
# 打开 http://127.0.0.1:8000/live/
```

Live 页会真实提交 pipeline、接收 SSE 阶段/指令事件、列出并预览产物，并读取
RSI 的只读 status/trace。它**没有** approve/claim/sign 端点；人工签署仍在
CLI/人工流程。Runtime 单 worker 串行执行；每个 job 的状态、事件与结果摘要写入
`runtime_data/jobs/<job_id>/job.json`，产物写入同目录；重启后会恢复已完成任务，
旧的 `queued/running` 任务标为 interrupted。任务执行异常时除 `task-error.txt` 外还会写
`failure.json`（`task-failure-0.1`：error_type/retryable/suggested_action），runtime 与前端卡片会直接展示可重试性与修复建议；该记录只用于诊断，不自动重试。详见
[`runtime/README.md`](runtime/README.md)。

Pages 是 HTTPS，不能直接调用本地 HTTP runtime（mixed content）；请本地打开
Live 页，或把 runtime 放在 HTTPS 反代后。健康检查、请求校验、产物路径阻断、
RSI 根目录限制都有测试覆盖。

## 模型网关（OpenAI / Anthropic / 兼容端点）

```bash
# 1) 启动 runtime 与站点（同一台机器）
python -m research_agent.runtime --port 8787
python -m http.server 8000 --directory site
# 打开 http://127.0.0.1:8000/models/

# 2) 密钥二选一：
#    - 环境变量（推荐，runtime 进程读取）
#      export OPENAI_API_KEY=...        # 或 ANTHROPIC_API_KEY
#    - 模型页粘贴 session key（只存 runtime 内存，重启失效）

# 3) 用 profile 跑 RSI proposer（CLI 进程只读环境变量 key）
python -m research_agent rsi propose-model \
  --profile rsi-proposer \
  --store runtime_data/model_gateway.json \
  --observation "Public BM25 baseline recall=1.0, cost=21, gaps=0." \
  --out research_agent/web/data/model-proposal.json
```

- 供应商：`openai` / `anthropic` / `azure_openai` / `openai_compatible`（Ollama、vLLM、DeepSeek、OpenRouter 等）。
- 思考参数：OpenAI 用 `reasoning_effort` + `max_completion_tokens`；Anthropic 用 `thinking.budget_tokens`（`max_tokens > budget`）；兼容端点用 `extra_body` 显式声明。
- 配置分三层：Provider → ModelProfile → Module Binding；`GET /api/models` 只返回 key 状态与 masked key，不返回明文。
- 在 **Settings → 模型设置 → 模块模型绑定** 为 `literature` / `idea` / `experiment` / `paper` / `judge` 选择 profile 并保存；留空表示使用确定性规则/模板。runtime job 与设置页共用同一个 `GatewayStore` 和 `SessionKeyStore`，页面粘贴的 session key 会被任务使用（仅 runtime 内存，重启失效）。绑定页可直接为已注册 profile 的 provider 写入/清除 session key（`POST/DELETE /api/models/providers/{provider_id}/key`），不会覆盖 base_url、模型列表等 provider 配置。
- `judge` 与 `literature` / `idea` / `experiment` / `paper` 共用同一 profile 时，readiness 会在 `warnings[]` 中提示“同一基座模型，独立性受限”；这是警告，不阻断生产模式。
- `rsi`、`literature`（仅检索子查询）、`idea`（仅候选，引用必须解析到输入 span）、`experiment`（只补缺失设计字段，模型补全后仍 `needs_human`）、`paper`（仅非结果章节，引用/数字校验后收）与 `judge`（句子级支持审稿，advisory）均已 WIRED；
- `RESEARCH_AGENT_MODE=test`（默认）允许缺 key 回退；`RESEARCH_AGENT_MODE=production` 要求 `literature / idea / experiment / paper / judge` 全部 wired + bound + key，缺一项 `/api/runs` 返回 503；已就绪后若模型调用或输出解析失败，job 直接失败，不会静默退回规则模板；
- 证据门禁、claim/EA/closure 与数值重算始终是确定性代码，API key 只增强智能层，不赦免证据边界。
- 模型页的 Probe、绑定后的 runtime pipeline 模型调用都会真实产生 API 费用；调用日志只保留 provider/model/thinking/usage/latency/request id，不含 prompt/response/key，并进入 `/api/models/calls` 与 UsageStats。
- 设计、威胁模型与失败模式见根目录 [`29-多模型接入-OpenAI-Anthropic-API密钥与思考参数设计.md`](../29-多模型接入-OpenAI-Anthropic-API密钥与思考参数设计.md)。

## Skill 版本治理

```bash
# 1) 先评测目标 built-in 版本；报告必须同时包含 public + hidden 且全部通过
python -m research_agent skill eval --skill-id protocol-review --version 1.0.0 \
  --eval-root runtime_data/skill-evals
# 2) 人工激活；只允许预注册 built-in handler，不重写代码
python -m research_agent skill version activate --skill-id protocol-review \
  --version 1.0.0 --eval-report runtime_data/skill-evals/protocol-review-1.0.0-all-<id>.json \
  --human-reason "validated old behavior"
# 3) 回滚到上一版本
python -m research_agent skill version rollback --skill-id protocol-review \
  --human-reason "restore current behavior"
# 只读查看
python -m research_agent skill version list
```

runtime 只暴露 `GET /api/skills/versions`；`POST /api/skills/{id}/run` 使用 active version，激活/回滚仍只能在 CLI。

## 内部确定性 benchmark

```bash
python -m research_agent benchmark run --output-dir runtime_data/benchmark
# 快速只跑 support judge oracle/nop
python -m research_agent benchmark run --output-dir runtime_data/benchmark --no-closure
```

覆盖：strict 在 G1/G2 前停止、协议绑定、复用 RunCapsule/EA、closure ready + sign；support judge 的 oracle / nop / heuristic 对照。它不是外部能力 benchmark，也不是人工评测，不能当作科学效果证明；真实效果仍需 held-out 任务、独立 Judge 与人工盲评。

## 严格预注册流程（推荐用于真实研究）

`--flow-mode strict` 把 Q0/G1/G2 当执行门：未选 idea、未冻结协议时不会执行 S5。`review` 只用于待审包/演示。

```bash
# 1) S1→S2/S3，停在 G1
python -m research_agent pipeline run --topic "研究问题" --language zh \
  --venue zh_core_journal --flow-mode strict --output-dir runtime_data/jobs/strict-1
# 2) 人工选择候选，生成 G1 决策
python -m research_agent flow g1 --idea-file runtime_data/jobs/strict-1/idea.json \
  --idea-id IDEA-01 --human-reason "选择该候选的理由" \
  --output-dir runtime_data/jobs/strict-1
# 3) 带 G1 决策进入 S4，停在 G2
python -m research_agent pipeline run --topic "研究问题" --language zh \
  --venue zh_core_journal --flow-mode strict \
  --g1-decision runtime_data/jobs/strict-1/g1-decision.json \
  --output-dir runtime_data/jobs/strict-2
# 4) 人工预注册：只冻结 design，不需要 capsule
python -m research_agent protocol freeze-design \
  --design runtime_data/jobs/strict-2/experiment.json \
  --limitation "适用边界" --human-reason "已核对 baseline/指标/seeds" \
  --output-dir runtime_data/jobs/strict-2/protocol
# 5) 带 frozen protocol 执行 S5，生成 RunCapsule/EA 与未签 claim draft
python -m research_agent pipeline run --topic "研究问题" --language zh \
  --venue zh_core_journal --flow-mode strict \
  --g1-decision runtime_data/jobs/strict-1/g1-decision.json \
  --protocol-file runtime_data/jobs/strict-2/protocol/protocol-card.json \
  --run-dataset iris --run-seeds 3 --output-dir runtime_data/jobs/strict-3
# 6) 人签 claim 后复用原 run（不要重跑 S5），可附已验证 bibliography
python -m research_agent run claim \
  --capsule runtime_data/jobs/strict-3/run/run-capsule.json \
  --ea runtime_data/jobs/strict-3/run/ea.json \
  --statement "<claim-draft 中的 statement>" --human-reason "已核对 EA" \
  --scope S5/demo/iris --output-dir runtime_data/jobs/strict-3/claim
python -m research_agent pipeline run --topic "研究问题" --language zh \
  --venue zh_core_journal --flow-mode strict \
  --g1-decision runtime_data/jobs/strict-1/g1-decision.json \
  --protocol-file runtime_data/jobs/strict-2/protocol/protocol-card.json \
  --claim-file runtime_data/jobs/strict-3/claim/claim.json \
  --run-dir runtime_data/jobs/strict-3/run \
  --bibliography-file research_agent/web/data/bibliography/bibliography-card.json \
  --output-dir runtime_data/jobs/strict-4
# 7) Closure ready 后，人工签核导出（推荐先用本地 signer 建立身份）
python -m research_agent signer create --name "PI"
python -m research_agent closure sign \
  --report runtime_data/jobs/strict-4/closure/closure-report.json \
  --demo runtime_data/jobs/strict-4/demo.json \
  --claim runtime_data/jobs/strict-4/claim/claim.json \
  --human-reason "已复核 closure 与导出清单" \
  --signer <SIGNER-ID> \
  --output-dir runtime_data/jobs/strict-4/closure-signature
# publish 会重算 HMAC 与全部文件字节；签名无效时拒绝封装
python -m research_agent closure publish \
  --manifest runtime_data/jobs/strict-4/closure-signature/export-manifest.json \
  --signature runtime_data/jobs/strict-4/closure-signature/signature.json \
  --output-dir runtime_data/jobs/strict-4/publish
# 独立复核 bundle：文件哈希 + sealed signature HMAC
python -m research_agent closure verify-bundle \
  --bundle runtime_data/jobs/strict-4/publish/evidence-bundle
```

本地 signer 是 HMAC possession proof，不是 PKI 或法律签名；不提供密钥就不生成 HMAC，signature 会明确标记为 `legacy-unsigned`。

runtime UI 的 RUN 面板提供同样的严格流程入口：可填 G1/Protocol/Claim/Bibliography/Run 目录后继续；浏览器不代签。

## 证据边界

- 文献：没有全文不生成 span；摘要不是证据；不创建 Claim。
- 假设：候选必须带否证条件，不自动通过 G1。
- 实验：只产设计草稿，不执行 run、不产生结果。
- 绘图：SVG 只作示意图；不走实验结果图；无外部脚本/链接。
- 论文：结果槽 `pending_evidence`；`schematic figure` 不能当结果图；claims 为空。
- 基金：不生成科学观点/预算数字，不自动提交；官方模板优先。
- RSI：fixture 证据 `simulation: true`，真实语料证据 `claim_eligible: false`，两者都保持 `capability_claims` 为空；hidden 只读 public 排序后的 finalist；active lease 才进入研究 runner；租约后的 sealed confirm 只做复核。
- 真实语料：`modules/literature/fixtures/real_corpus.json` 仅含 4 篇 CC-BY 4.0 论文正文（references 省略），逐篇记录 license/URL/SHA256；只用于 S1 harness 评估，不直接进入论文证据。
- S5：`run execute` 支持 iris/breast_cancer/ChemLab 协议验证并产出 RunCapsule/EA；`run claim` 必须有人签理由；`pipeline --run-dir` 复用同一 run 后，`result.primary=bound_claim`、`result.figure=bound_figure`；closure 在 claim + ProtocolCard + 数据图 + DataCite 元数据后可 11/11 ready；人签生成 export manifest（submission=false）。注意：该签署链是历史运行，当前工作区未保留 `signature.json`/`export-manifest.json`，引用前必须用 `closure check/sign` 重新生成并复验。
- S5 RSI 第二基准（ChemLab）：`test_size` 作为内部验证比例，不同 split 使用不同训练子集；seeds2 通过 public/hidden/near-OOD/regression，hidden cost 10→4、mean R² −0.0095、min +0.0402，人签 lease 后 `run execute --use-lease` 实际以 2 seeds 运行；租约后 `s5-confirm` 在由训练池确定性派生、与 22 化合物测试集不重叠的 **42 条 held-out 反应**上复核通过（mean R² +0.00566、min +0.00966、cost 20→8、failed 0），`used_for_admission=false`；复核结果以 audit-only 记录写入 `StepLedger.confirmations`，`rsi status` 显示 confirmed 且 `capability_claims=[]`；写入校验 status/passed/scope/delta，`rsi trace` 同时核对文件与账本 artifact hash。

所有输出带 `fixture_mode` / `SIM` 语义；默认没有任何外部 API 调用。只有显式模型绑定后的 runtime pipeline、模型页 Probe 或 `rsi propose-model --profile` 会联网，且仍需 provider key；模型输出不会绕过 claim/EA/gate。

## 测试

```bash
python -m unittest discover -s tests -v
```

532 个测试覆盖规格最小更新、文献 span 边界、本地 PDF/TXT/MD 全文与页码锚点、候选/设计/写作/基金契约、模块替换 seam（module_overrides / module_factories）、SVG 审计、纵切编排、任务路由与 RouteDecision、任务报告、证据包状态汇总（S1–S13 的 ready/partial/needs_human/missing/blocked）、strict/review 门禁控制流（Q0/G1/G2 停止、G1 decision、freeze-before-run、protocol hash binding）、Skill 使用记录/确定性评测/RSI pending 提案/Skill manifest linter/external advisory 与 trusted script 边界/Skill 蒸馏（license/provenance/hash/disabled candidate）/已有手稿修订（MD/DOCX/TEX 读取、数据指标、bar/line 图、引用数字防篡改、MD/TeX/DOCX/PDF 导出）/框架无关 capabilities、HTTP 工具桥与 Python client、AstraDraw scene/template 渲染（SVG/PNG/audit/manifest）、production/test 模式与模型 readiness 门禁、CLI 产出、可读 `paper.md` / `report.md` 与模型写作拒收边界、S1 来源账本（全文/摘要/重复/元数据/时效筛选）、S2–S3 idea review、S4 设计/统计审计、S5 run contract/allowlist、中文投稿工作稿审计（编号引用、GB/T 7714 风格、claim×ref×anchor 覆盖率、结果数字/claim/fixture/占位符阻断）、closure append-only obligations、结构化 claim 数值重算、静态闭环审计、前后端功能接线（runtime routes / API adapters / model calls / runs history / skills catalog / no signing endpoint）、真实 CC-BY 文本纵切、S5 run/EA/人签 claim、ChemLab R² 与 split 独立性、runtime 的健康检查/请求校验/真实执行/事件/产物路径阻断/RSI 只读、项目级实验链只读清单、经验证据派生 consistency registry、创新账本逐条代码绑定、active budget policy 与 S5 seed lease 实际消费、环境 doctor（不打印 key 值）、job 跨重启恢复与产物重读、模型网关（OpenAI/Anthropic 请求翻译、thinking budget、密钥脱敏与不落盘、URL 策略、runtime binding）、通用 MCP 集成（NDJSON 与 Content-Length 双帧、工具白名单、skill list/distill 项目边界、项目路径穿越拒绝、production 缺 key fail-closed、无 sign/approve 工具），以及 RSI 控制面（strict admission 四类 sealed 证据/evaluator/artifact/task-pack hash/approver、证据不可替换、撤销/过期自动收回 capability claim、policy 默认拒绝、append-only 哈希链事件日志，以及 lease→capsule→confirmation 的 `rsi trace` 链接校验、hidden 不泄漏给未入选 finalist、过期/冲突 lease fail-closed、租约能驱动下一批 research、sealed confirm 不回流准入、CC-BY probe 人签后仍不写 capability claim、重复 trial 不新增 episode、撤销保留记录、数值预测按 MAE/bias/direction/coverage 校准且自由文本预测显式标为不可校准）。MiniLM 真实模型路径需本地缓存，设置 `RUN_MINILM_TEST=1` 才会执行该用例。

规则见根目录 [`AGENTS.md`](../AGENTS.md)。
