# AGENTS.md — 编码与模块规格规则

本文件约束后续在本仓库中新增/修改代码时的最小工作流。**模块规格 Markdown 是源，代码是规格的实现**；不是反过来。

## 1. 先读什么

在任何代码改动前，按顺序读：

1. 本文件（规则）；
2. 根目录 `ARCHITECTURE.md`（稳定内核/能力/Skill/适配器边界）与目标模块的 `modules/<module-id>/SPEC.md`；
3. 与改动相关的专题文档（通常是 `21-` §9、`22-` §4、`07-` §5）；
4. 目标模块的测试与相邻端口，确认不越过模块边界。

文档入口：`QUICKSTART.md`（10 分钟）、`ARCHITECTURE.md`（可扩展边界）、`integrations/README.md`（接入与人工门）、`modules/README.md`（模块与扩展清单）。

如果 `SPEC.md` 与代码不一致：**先判断是代码偏离还是规格过期**。不能直接“按代码改规格”掩盖偏离；也不能不更新规格就改行为。

## 2. 模块规格是唯一入口

每个子智能体模块必须有：

```text
modules/<module-id>/SPEC.md
```

`SPEC.md` 的 YAML frontmatter 至少包含：

```yaml
id: literature
name: 文献调研
stage: S1
version: 0.1.0
status: draft        # draft | pilot | active | deprecated | revoked
owner: research-agent
inputs: [...]
outputs: [...]
tools: [...]
gates: [...]
invariants: [...]
```

正文至少包含：`Purpose`、`Contract`、`Current Implementation`、`Boundaries`、`Minimal Change Workflow`、`Changelog`。

新增模块：复制 `modules/_template/SPEC.md`，改 `id/name/stage/outputs`，先在 `status: draft` 下实现，不得直接 `active`。

## 3. 最小修改规则

### 3.0 扩展优先原则

- 可以数据化的东西不要硬编码：期刊 profile、AstraDraw 模板、能力 schema 应优先注册表/JSON；当前仍是代码的部分必须在 SPEC 中标为“计划迁移”。
- 新工具不得复制 `mcp_server` 的业务逻辑；MCP/HTTP/Python 必须共用 `framework_api` 的 dispatch。
- 新 Skill 不得直接写 Claim/EA/gate/signature；只能调用白名单工具。
- 本地实验必须由用户环境执行，智能体不安装依赖、不假设自己的 Python 环境；执行前需要人工确认。
- **目标解释器是 Python 3.8**：不得使用 3.9+ 的 API 便利（`Path.write_text(newline=)`、`dict1 | dict2`、`str.removeprefix`、`zoneinfo`、`match` 语句等）。写文件用 `storage.write_json_atomic` 或 `open(..., newline=...)`。本轮同一坑踩了三次，因此它是规则而不是提醒。
- 未实现的能力只能写 roadmap，不能写成“已支持”。

- **一次只改一个模块**；除非任务明确要求跨模块，否则不改共享层、不改其他模块、不做顺手重构。
- 先写/改 `SPEC.md` 的契约或 changelog，再改代码；代码 diff 应能对应到规格中的一条改动。
- 只改内部实现、契约不变：`version` 升 patch（如 `0.1.0 → 0.1.1`），在 `## Changelog` 追加一条，`Contract` 不动。
- 契约变化（输入/输出/边界/门禁）：升 minor，更新 `Contract`，补测试；涉及 claim/EA/导出不变量时，必须停下来要求人工确认。
- 不重命名公开模块、类、CLI 命令；必须重命名时先在规格里写迁移说明并保留兼容入口。
- 不加“未来可能用到”的抽象；不为假想需求增加端口、配置或依赖。

## 4. 读取与修改规格的官方方式

优先用仓库自带 CLI，而不是手改 Markdown：

```bash
# 读取
python -m research_agent spec list
python -m research_agent spec show literature

# 最小更新（版本/状态/说明；正文与未涉及字段保持不动）
python -m research_agent spec update literature \
  --version 0.1.1 --status pilot \
  --changelog "最小改进：增加摘要-only 来源的覆盖缺口提示"

# 定点替换某一节（例如 Current Implementation）
python -m research_agent spec patch literature \
  --section "Current Implementation" \
  --text "FixtureRetriever + SimpleParser；不联网、不创建 Claim。"

# 无外部 API key：把生成步骤交给当前 Agent（Qoder/Claude Code/Codex/Zcode）
python -m research_agent host-model bind --modules idea,experiment,paper
python -m research_agent host-model turns --prompt          # 读回运行要什么
python -m research_agent host-model respond --turn-id MT-... --file answer.json
python -m research_agent host-model status                  # 只读交接概览

# S5 本地协议验证：run → RunCapsule/EA → 人签 Claim
python -m research_agent run execute --seeds 3 --output-dir research_agent/web/data/run
python -m research_agent run claim --capsule research_agent/web/data/run/run-capsule.json --ea research_agent/web/data/run/ea.json --statement "..." --human-reason "..." --scope S5/demo/iris --output-dir research_agent/web/data/run-claim

# 运行模块
python -m research_agent literature run \
  --question "钙钛矿 界面 钝化 稳定性" --max-sources 4

# 写作包与预审：run 的只读投影 → Qoder 写稿 → 结构与数值边界审计
python -m research_agent writing pack --project research-project --run-id RUN-... --max-sources 8
python -m research_agent writing audit --project research-project --run-id RUN-... \
  --draft research-project/drafts/review.md

# 顶会语料 → 创新点评审 → 中文初稿 → 多轮评审
python -m research_agent conference fetch --target-dir research-project/inputs \
  --topic "LLM agents scientific discovery" --venues NeurIPS,ICLR,ICML,ACL --years 2024,2025,2026 \
  --max-papers 24 --allow-network
python -m research_agent literature synthesize --project research-project --run-id RUN-... --max-themes 7
python -m research_agent innovation review --project research-project --run-id RUN-... --rounds 3
python -m research_agent manuscript draft --project research-project --run-id RUN-... \
  --output research-project/drafts/review.md
python -m research_agent manuscript review --project research-project --run-id RUN-... \
  --draft research-project/drafts/review.md --rounds 3
python -m research_agent loop status --project research-project --run-id RUN-...

# S4 设计 + CSV → 本地实验包 → 显式执行 → evidence → 人签 Claim → closure/lineage
python -m research_agent experiment scaffold --project research-project --run-id RUN-... \
  --data inputs/data.csv --target y --features x1,x2 --task regression --methods dummy,ridge
python -m research_agent experiment approve --project research-project --experiment-id EXP-... \
  --human-reason "checked design/data/split"
python -m research_agent experiment run --project research-project --experiment-id EXP-... --allow-execute
python -m research_agent experiment ingest --project research-project --experiment-id EXP-...
python -m research_agent experiment claim --project research-project --experiment-id EXP-... \
  --statement "..." --human-reason "..." --assertion "metric=r2,value=0.8,comparator=>=,tolerance=0.01"
python -m research_agent experiment closure --project research-project --experiment-id EXP-...
python -m research_agent experiment sign --project research-project --experiment-id EXP-... \
  --report research-project/experiments/EXP-.../experiment-closure/closure-report.json --human-reason "..."
python -m research_agent experiment lineage --project research-project --experiment-id EXP-...
python -m research_agent experiment lineage --project research-project --experiment-id EXP-... --verify

# 多智能体编排：S1 scout fan-out → fan-in → S2/S3 候选帧（停在 G1 前）
python -m research_agent orchestrate plan --topic "..." --max-sources 12 --source fixture
python -m research_agent orchestrate run --topic "..." --max-sources 12 --source real \
  --memory-path research_agent/web/data/orchestration/memory.json \
  --output-dir research_agent/web/data/orchestration/run-2
python -m research_agent literature memory show --memory-path research_agent/web/data/orchestration/memory.json
python -m research_agent literature memory advise --question "..." --max-sources 12 --source real
python -m research_agent agent add --name "覆盖与引用审稿人" --role reviewer \
  --purpose "检查全文覆盖与引用对齐" --check coverage --check citation
python -m research_agent agent export --output apps/web/public/custom-agents.json
python -m research_agent rsi policy show
python -m research_agent rsi policy set --scope literature.memory_order=off
python -m research_agent skill scan --path ~/.claude/skills
python -m research_agent skill list

# 声明式搜索研究：设计是数据，第一个水平是参照格；未知因子/水平或格子数 >12 直接拒绝
python -m research_agent study profiles
python -m research_agent study search --dataset iris --seeds 1,2,3,4,5,6,7,8 --budget 60
python -m research_agent study search --dataset iris --seeds 1,2,3,4 --budget 40 \
  --factors gate=on --factors operators=all,feature_only,knob_only
python -m research_agent study claim --study-dir <project>/studies/<dir> --statement "..." --human-reason "..." --scope S5/...
python -m research_agent study closure --study-dir <project>/studies/<dir>
# 一条命令带上研究臂：调研→想法→设计→真实执行的研究→写作（度量口径固定为搜索效率）
python -m research_agent pipeline run --topic "..." --language en --venue en_conference \
  --output-dir runtime_data/pipeline-study --study-dataset iris --study-seeds 8 --study-budget 60
# idea → 实验：把该 idea 的 experiment_plan 声明的设计真的执行成研究（profile 必须 search_factorial）
python -m research_agent study from-idea --project <项目> --run-id RUN-... --idea-id IDEA-01 \
  --seeds 1,2,3,4,5,6,7,8 --budget 60

# 在冻结 CC-BY 正文上跑真实 S1→paper 纵切
python -m research_agent pipeline run --topic "How do self-improving coding agents use archives?" --language en --venue en_conference --real-corpus --output-dir research_agent/web/data/real-pipe

# RSI 控制面：默认只能 pending；缺 dry-run/public/hidden/人签不能 active
python -m research_agent rsi propose --kind skill --target literature.query_planner --patch "add review subquery" --rationale "thin coverage" --predicted "one more full text" --dry-run-ref "DRY-001"
python -m research_agent rsi status
python -m research_agent rsi fixture --ledger research_agent/web/data/rsi-ledger.json --output-dir research_agent/web/data/rsi-fixture
python -m research_agent rsi research-cycle --tasks research_agent/rsi_fixtures/research_tasks.json --ledger research_agent/web/data/rsi-ledger.json --output-dir research_agent/web/data/research-cycle
python -m research_agent rsi confirm --ledger research_agent/web/data/rsi-ledger.json --output-dir research_agent/web/data/rsi-confirmation
python -m research_agent rsi real-trial --ledger research_agent/web/data/rsi-real-ledger.json --output-dir research_agent/web/data/rsi-real
python -m research_agent rsi real-trial --retriever minilm --ledger research_agent/web/data/rsi-mini-ledger.json --output-dir research_agent/web/data/rsi-mini
python -m research_agent rsi real-trial --retriever compare --ledger research_agent/web/data/rsi-compare-ledger.json --output-dir research_agent/web/data/rsi-compare
python -m research_agent rsi propose-model --model-path ~/.cache/qwen-rsi/Qwen2.5-0.5B-Instruct --observation "Public BM25 baseline recall=1.0, cost=21, gaps=0." --out research_agent/web/data/model-proposal.json
python -m research_agent rsi real-trial --candidate-file research_agent/web/data/model-proposal.json --ledger research_agent/web/data/rsi-model-ledger.json --output-dir research_agent/web/data/rsi-model
python -m research_agent rsi model-batch --model-path ~/.cache/qwen-rsi/Qwen2.5-0.5B-Instruct --observations research_agent/rsi_fixtures/model_observations.json --output-dir research_agent/web/data/model-batch --ledger-root research_agent/web/data/model-batch-ledgers
python -m research_agent rsi real-confirm --ledger research_agent/web/data/rsi-compare-ledger.json --lease-scope S1/rsi-ccby-4-compare --output-dir research_agent/web/data/rsi-real-confirmation
python -m research_agent rsi real-confirm --ledger research_agent/web/data/rsi-compare-ledger.json --lease-scope S1/rsi-ccby-4-compare --tasks research_agent/rsi_fixtures/transfer_tasks.json --corpus modules/literature/fixtures/transfer_corpus.json --output-dir research_agent/web/data/rsi-transfer-confirmation
python -m research_agent rsi s5-trial --ledger research_agent/web/data/rsi-s5-ledger.json --output-dir research_agent/web/data/rsi-s5
python -m research_agent rsi s5-trial --dataset breast_cancer --ledger research_agent/web/data/rsi-s5bc-ledger.json --output-dir research_agent/web/data/rsi-s5bc
python -m research_agent run execute --use-lease --ledger research_agent/web/data/rsi-s5-ledger.json --lease-scope S5/demo/iris --output-dir research_agent/web/data/run-s5-lease
python -m research_agent rsi s5-confirm --ledger research_agent/web/data/rsi-s5-ledger.json --output-dir research_agent/web/data/rsi-s5-confirmation
python -m research_agent pipeline run --use-s5-lease --s5-ledger research_agent/web/data/rsi-s5-ledger.json --topic "Iris protocol validation" --language en --venue en_conference --output-dir research_agent/web/data/pipeline-s5
python -m research_agent pipeline run --run-dataset chemlab --run-seeds 3 --topic "ChemLab reaction conversion baseline" --language en --venue en_conference --output-dir research_agent/web/data/pipeline-chemlab
python -m research_agent bibliography verify --source modules/literature/fixtures/bibliography.json --output-dir research_agent/web/data/bibliography
python -m research_agent flow g1 --idea-file research_agent/web/data/flow/idea.json --idea-id IDEA-01 --human-reason "selected for protocol" --output-dir research_agent/web/data/flow
python -m research_agent protocol freeze-design --design research_agent/web/data/pipeline-chemlab/experiment.json --limitation "single public dataset" --human-reason "checked design/stopping rule" --output-dir research_agent/web/data/protocol
python -m research_agent pipeline run --topic "Iris protocol validation" --language en --venue en_conference --flow-mode strict --g1-decision research_agent/web/data/flow/g1-decision.json --protocol-file research_agent/web/data/protocol/protocol-card.json --run-dataset iris --run-seeds 3 --output-dir research_agent/web/data/strict-pipe
python -m research_agent pipeline run --topic "..." --language en --venue en_conference --flow-mode strict --claim-file research_agent/web/data/run-claim/claim.json --output-dir research_agent/web/data/resume-claim
python -m research_agent protocol freeze --design research_agent/web/data/pipeline-chemlab/experiment.json --capsule research_agent/web/data/pipeline-chemlab/run/run-capsule.json --limitation "single public dataset" --human-reason "checked design/capsule" --output-dir research_agent/web/data/protocol
python -m research_agent study replicate --project research-project   # 只读：按设计分组，只数判定的数据集
python -m research_agent closure check --demo research_agent/web/data/pipeline-chemlab/demo.json --claim research_agent/web/data/run-claim/claim.json --output-dir research_agent/web/data/closure
python -m research_agent lineage build --bundle research_agent/web/data/closed-loop --output-dir research_agent/web/data/closed-loop/lineage
python -m research_agent lineage verify --manifest research_agent/web/data/closed-loop/lineage/lineage.json --bundle research_agent/web/data/closed-loop --output-dir research_agent/web/data/closed-loop/impact-clean
python -m research_agent lineage impact --baseline research_agent/web/data/closed-loop/lineage/lineage.json --bundle research_agent/web/data/closed-loop-changed --output-dir research_agent/web/data/closed-loop-changed-impact --fail-on-stale
```

`spec update` 只改 frontmatter 中给出的字段和 Changelog；`spec patch` 只替换指定 `##` 节，其他节原样保留。写入是原子的；校验失败不落盘。

**传中文/markdown 正文时的硬要求**：`--changelog` / `--text` 走 shell 参数，双引号里的反引号会被当成命令替换执行，
结果是**静默删字**（本仓库踩过：0.23.0 的 changelog 少了 `study replicate` 与一段设计名，只在回读 SPEC 时才发现）。
因此：正文含反引号时改用 `spec patch --section Changelog --file <utf8 文件>` 或单引号包裹，并在写入后回读该条确认字数。

## 5. 代码边界

```text
research_agent/
  contracts.py       # 模块间数据契约（dataclass）
  ports.py           # RetrieverPort / ParserPort
  paths.py           # repo-root 默认状态路径（CLI/runtime 共用）
  storage.py         # 原子 JSON 读写（本地 store 共用）
  specs.py           # SpecStore：读/校验/最小更新
  project.py         # 研究项目目录（project.json / runs / 越界校验）
  autopilot.py       # 人写一次策略 → G1/G2/S5b/G5/publish/lineage 的委托执行（CLI only）
  cli_autopilot.py   # autopilot policy init|run|status（cli.py 单向 import）
  mcp_server.py      # stdio MCP：Qoder/Claude Code/Zcode 接入；无签核工具
  framework_api.py   # 框架无关能力清单与工具 dispatch（MCP/HTTP/Python 共用）
  client.py          # HTTP ResearchAgentClient / 本地 LocalResearchAgent
  manuscript.py      # 中文投稿工作稿：编号引用/GB/T 7714 草稿/确定性审计
  literature_synthesis.py # 多篇来源 → 主题×来源矩阵（一致/张力/未使用）
  loop_ledger.py     # S0–S16 阶段/门禁/迭代/下一步的只读投影
  writing_pack.py    # 单 run 写作包：真实来源卡、span、写作契约（不签核）
  writing_audit.py   # 成稿预审：引用键/结果数值/章节/占位符/fixture
  manuscript_writer.py # 证据包+创新评审 → 中文综述/立场初稿（模型；不伪造实验）
  innovation_review.py # 缺口→创新点→三评审→修订→再评审
  independence.py      # 批评角色供给指纹与独立面板校验（配置层+账本层，不证明输出独立）
  manuscript_review.py # rubric 评审→修订→再评审；审计不变差才接受
  design_audit.py    # S4 设计/统计完整性清单（不替代 G2）
  experiment_codegen.py # S4 设计+CSV → 自包含实验包（只生成）
  experiment_runner.py  # 实验包 approve→本地执行→ingest→人签 Claim（CLI-only 执行/签核）
  idea_review.py     # S2–S3 词法预审（grounding/falsifiability/testability）
  run_contract.py    # S5 run contract + artifact allowlist 核验
  obligations.py     # closure append-only obligations
  skill_lint.py      # 静态 Skill manifest/path/script 检查（不执行）
  external_skills.py # 外部 Skill advisory + 显式 trusted script 调用
  skill_distill.py   # 外部 Skill → disabled 本地候选（license/provenance/hash）
  revision.py        # 已有手稿修订：模型改写、引用/数字防篡改、审计
  revision_io.py     # MD/DOCX/TEX 解析，CSV/XLSX 数据，MD/TeX/DOCX/PDF 导出
  revision_figures.py# 数据表 → bar/line PNG/SVG 图
  revision_templates.py # 中文期刊结构/版面 profile（非官方模板）
  figure_workflow.py  # AstraDraw scene/模板 → SVG/PNG/audit/manifest
  modules/           # 子智能体实现
  orchestration/     # 编排 plan / advisory / merge（orchestrator.py 是 facade）
  adapters/          # 外部适配器（fixture、未来 OpenAlex/DeepSeek）
  models/            # OpenAI/Anthropic/兼容端点网关；密钥只进 env 或 runtime 内存
  runtime/           # 本地 FastAPI：pipeline job / SSE / artifacts / 只读 RSI / model gateway
  cli.py             # 唯一命令行入口
modules/
  <id>/SPEC.md       # 规格（唯一源）
  <id>/fixtures/     # 只用于离线测试的 fixture
integrations/        # 平台接入说明与 MCP 配置示例
tests/               # 规格与模块契约测试
```

- 子智能体不得直接写 Claim/EA/Verdict；S1 只产出 `SourceHit / Span / CoverageReceipt / Gap`。
- 没有全文的摘要只能作为 `SourceHit` 线索，不能生成 `Span`，更不能当证据。
- fixture 数据必须显式标 `fixture: true`；输出必须带 `fixture_mode` 警告，不得把 fixture 当真实检索结果。
- 不联网、不调用外部 API 是默认；接入 OpenAlex/DeepSeek/知网等必须新增 adapter，并在规格中写权限、错误与限流。
- `runtime/` 只暴露本地 pipeline 执行、SSE、产物与只读 RSI；不得提供 approve/claim/sign 端点，不得把人工门禁搬进浏览器。
- external Skill 的 instruction-only advisory 不得授予 allowed-tools；script 只在本地 CLI 显式 `--trusted-scripts` 下以用户 OS 权限执行，**不是 sandbox**，MCP/runtime 不执行脚本。
- 蒸馏只产出 disabled `local-*` 候选，必须有 license 与 human_reason，复制完整 scripts/references/assets（排除隐藏/缓存）；不得自动启用、不得把候选当能力增益或证据。
- revision 只修订已有手稿：无模型 profile 时为 copy mode；模型改写必须保留引用集合、不得新增数字、保护实验/结果数字；数据指标只从用户表格和 spec 重算；submission_ready 始终 false。

## 6. 测试与完成定义

每次代码改动至少跑：

```bash
python -m unittest discover -s tests -v
```

完成必须同时满足：

- [ ] `SPEC.md` 的 version/changelog 已更新；
- [ ] 改过 `modules/*/SPEC.md` 或 CLI 命令面后，跑过 `python -m research_agent workspace export`：`tests/test_workspace.py` 拿已提交的 `apps/web/public/*.json` 与实时 registry 比对，规格升版而忘记重导出会让全量套件在最后一步红掉；
- [ ] 新增/删除 CLI 命令后，还必须跑 `python -m research_agent plugin export`：`plugin/manifest.json` 的命令计数与工具面是派生物，`tests/test_plugin_bundle.py` 会逐文件比对——两次踩坑（verdicts 命令组）证明这一步不会有人提醒；
- [ ] 目标模块测试通过，未破坏其他模块；
- [ ] 输出仍遵守 `fixture_mode` / `span-only` / no-claim 边界；
- [ ] 没有新增未使用依赖；
- [ ] 改动文件清单与规格 changelog 能对上。

## 7. 不要做

- 不要为了“看起来完整”一次性重写多个模块；
- 不要让 LLM 生成的内容绕过 Spec/Contract/测试；
- 不要把 fixture、模拟分数、外部 README 效果数字写成真实结果；
- 不要在未更新规格的情况下改 CLI/输入输出；
- 不要在 MCP/插件层暴露 approve、sign、freeze、publish 或 export 工具；人工门只能留在 CLI/人工流程；
- 唯一例外是**人预先授权的 autopilot**：人写 `autopilot-policy.json`（scope/数据集/最低种子/有效期/次数），agent 才能在 CLI 上代跑 G1/G2/S5b/G5；每一步 reason 必须带 `[delegated:autopilot]` 与策略 SHA-256，缺失或越界即停，且不得由 agent 创建或放宽策略；
- 不要修改 `00-` 到 `23-` 的设计文档来“适配”代码；代码应服从模块规格，设计变更另行提出。

## 8. 当前模块

| 模块 | 阶段 | 代码 | 规格 |
| --- | --- | --- | --- |
| task-agent | S0–S12 | `research_agent/task_agent.py` | `modules/task-agent/SPEC.md` |
| literature | S1 | `research_agent/modules/literature.py` + `literature_synthesis.py` + `adapters/conference_fetcher.py` | `modules/literature/SPEC.md` |
| orchestrator | S1–S3 | `research_agent/orchestrator.py` + `research_agent/orchestration/` + `literature_memory.py` + `custom_agents.py` + `evolution_policy.py` | `modules/orchestrator/SPEC.md` |
| idea | S2–S3 | `research_agent/modules/idea.py` | `modules/idea/SPEC.md` |
| experiment | S4–S16（本地 profile） | `research_agent/modules/experiment.py` + `experiment_codegen.py` + `experiment_runner.py` + `experiment_closure.py` | `modules/experiment/SPEC.md` + `modules/run/SPEC.md` |
| run | S5 | `research_agent/modules/run.py` | `modules/run/SPEC.md` |
| search-study | S5 | `research_agent/search_lab.py` + `research_agent/executable.py` + `research_agent/study_claims.py` + `research_agent/study_closure.py` + `research_agent/study_from_idea.py` + `research_agent/study_replication.py` | `modules/search-study/SPEC.md` |
| guideline-memory | META | `research_agent/guideline_memory.py` | `modules/guideline-memory/SPEC.md` |
| waitpoints | S5–META | `research_agent/waitpoints.py` | `modules/waitpoints/SPEC.md` |
| figure | S6 | `research_agent/modules/figure.py` + `figure_workflow.py` | `modules/figure/SPEC.md` |
| paper | S8–S12 | `research_agent/modules/paper.py` | `modules/paper/SPEC.md` |
| manuscript | S8–S12 | `research_agent/manuscript.py` | `modules/manuscript/SPEC.md` |
| writing | S8–S12 | `research_agent/writing_pack.py` + `writing_audit.py` + `manuscript_writer.py` + `manuscript_review.py` | `modules/writing/SPEC.md` |
| innovation | S2–S3 | `research_agent/innovation_review.py` + `research_agent/independence.py` + `research_agent/adapters/conference_fetcher.py` | `modules/idea/SPEC.md` |
| revision | S8–S12 | `research_agent/revision.py` + `revision_io.py` + `revision_figures.py` | `modules/revision/SPEC.md` |
| grant | S8–S12（基金轨） | `research_agent/modules/grant.py` | `modules/grant/SPEC.md` |
| bibliography | S13 | `research_agent/bibliography.py` | `modules/bibliography/SPEC.md` |
| closure | S13–S16 | `research_agent/closure.py` | `modules/closure/SPEC.md` |
| judge | S5b–S13 | `research_agent/support_audit.py` + `research_agent/adapters/support_judge.py` | `modules/judge/SPEC.md` |
| maintenance | S13–S16 | `research_agent/maintenance.py` | `modules/maintenance/SPEC.md` |
| lineage | S13–S16 | `research_agent/lineage.py` | `modules/lineage/SPEC.md` |
| skills | META | `research_agent/skill_registry.py` + `external_skills.py` + `skill_distill.py` | `modules/skills/SPEC.md` |
| integration | META | `research_agent/project.py` + `mcp_server.py` + `framework_api.py` + `client.py` | `modules/integration/SPEC.md` |
| host-model | META | `research_agent/host_model.py` + `research_agent/models/gateway.py`（`host_agent` kind） | `modules/host-model/SPEC.md` |
| rsi | META | `research_agent/rsi.py` | `modules/rsi/SPEC.md` |
| autopilot | S2–S16（委托门） | `research_agent/autopilot.py` + `cli_autopilot.py` | `modules/autopilot/SPEC.md` |
| mandate | META（只读委托投影） | `research_agent/mandate.py` | `modules/mandate/SPEC.md` |
| verdict-ledger | S5–S16（判定总线） | `research_agent/verdict_ledger.py` | `modules/verdict-ledger/SPEC.md` |
| feedback | S5–S16（反馈端口） | `research_agent/feedback.py` | `modules/feedback/SPEC.md` |
| ccfa-audit | S4 | `research_agent/ccfa_audit.py` + `cli_design.py` | `modules/ccfa-audit/SPEC.md` |

每个模块的测试在 `tests/`；完整纵切见 `research_agent/pipeline.py`。`research_agent/vendor/astradraw/` 是从本地完整复制的第三方绘图工作流，**不要改上游脚本**；需要适配时只改 `research_agent/adapters/astradraw_renderer.py` 与 `svg_audit.py`。

下一步若要改进某模块（例如给文献模块加真实 OpenAlex/中文库 adapter，或给 figure 加更多 scene 语义），先改对应 `SPEC.md` 的 `Contract` 或 `Current Implementation`，再以最小 diff 改代码和测试。
