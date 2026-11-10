# 在 Qoder / Claude Code / Zcode 中使用科研工作流

三者都支持标准 MCP。本仓库把科研流水线封装成一个 **stdio MCP server**，平台侧只需要配置启动命令和技能说明，不需要为每个平台重写工具。

```text
Qoder / Claude Code / Zcode
          │  MCP (stdio, NDJSON or Content-Length)
          ▼
research_agent.mcp_server
          │
          ├─ research_project_init
          ├─ research_plan / research_run
          ├─ research_status / list / read
          ├─ research_skill_list / invoke / distill
          ├─ research_manuscript_revise
          ├─ research_writing_pack / research_manuscript_audit
          ├─ research_conference_fetch
          ├─ research_literature_synthesis
          ├─ research_innovation_review
          ├─ research_manuscript_draft / research_manuscript_review
          ├─ research_experiment_codegen
          ├─ research_literature_fetch
          ├─ research_figure_templates / render
          └─ research_next_actions
                    │
                    ▼
<project>/runs/<RUN-ID>/        →  task.json / task-report.md / writing-pack / 证据与失败产物
<project>/revisions/<REV-ID>/   →  revised manuscript / audit / DOCX / TeX / PDF
```

## 一键体验

```bash
python scripts/research_mcp_demo.py \
  --project runtime_data/integrations/mcp-demo-project \
  --output runtime_data/integrations/mcp-demo
```

演示会通过真实 stdio 握手调用工具，初始化项目、跑一轮文献综述、跑一次 strict 假设任务（停在 G1），并演示 skill list→distill→list，把调用记录与 stderr 写入 `runtime_data/integrations/mcp-demo/`。

外部 Skill 脚本调用与蒸馏（不依赖 API key）：

```bash
python scripts/external_skill_demo.py
```

产物在 `runtime_data/integrations/external-skill-demo/`：真实脚本 stdout/proof、invocation 回执、完整 candidate（SKILL.md/scripts/references/assets）与 summary；candidate 保持 disabled。

## 项目目录

```text
<project>/
  project.json
  inputs/          # source=local 时放 PDF / TXT / MD
  runs/
    RUN-.../
      run-context.json
      task-plan.json
      task.json
      task-report.md
      literature.json / idea.json / experiment.json / run/ / paper.md ...
      literature-ledger.json
      manuscript.md / manuscript-audit.json / argument-ledger.json / claim-registry.json
      failure.json / startup-error.json
  protocols/       # 人工冻结的 ProtocolCard
  claims/          # 人工签署的 ClaimRecord
  closure/         # closure / 签名 / bundle
  notes/
    skill-invocations/    # 外部 Skill advisory 回执
    skill-library/        # 蒸馏出的 disabled 本地候选
    skill-distillations/  # 蒸馏回执
  revisions/              # 已有手稿修订：diff/审计/图/导入包
  figures/                # AstraDraw 方法示意图：scene/svg/png/audit/manifest
```

`project_dir` 必须是 MCP server 的 `--root`（或 `RESEARCH_AGENT_MCP_ROOT`）之内；越界路径会被拒绝。

## Qoder

本仓库已包含：

- `.mcp.json.example`（项目级 MCP 模板；`.mcp.json` 是本机文件，含绝对路径，已忽略）
- `.qoder/skills/research-workflow/SKILL.md`（项目级技能）

在 Qoder 中打开本仓库后：

1. 运行 `python scripts/doctor.py` 检查 Python、MCP 启动器、Node、外部 Skill 与 key 是否存在（不会打印 key 值）。
2. 运行 `python scripts/setup_mcp.py` 生成本机 `.mcp.json`（已忽略）；也可复制 `.mcp.json.example` 并替换两处 `<ABSOLUTE_PATH_TO_REPO>`。
3. 确认 `python scripts/research_mcp_server.py --help` 可运行。
3. 在 MCP / 连接器设置中确认 `research-agent` 已加载；或手动添加 stdio 命令：
   `python <绝对根目录>/scripts/research_mcp_server.py --root <绝对根目录>`，并设置
   `PYTHONPATH`、`RESEARCH_AGENT_MCP_ROOT`、`PYTHONIOENCODING=utf-8`。
   启动器会固定 cwd 与 import path；直接 `-m research_agent.mcp_server` 也可用，但要求客户端 cwd/PYTHONPATH 正确。
4. 运行 `/skills reload` 或重启会话，确认 `research-workflow` 技能可见。
5. 直接说：“用 research-workflow 在这个项目的 inputs/ 上做一轮文献综述，输出到 research-project。”

本机已通过 Qoder MCP 管理注册 user-scope `research-agent`（status=ready，工具数当时为 38，73/73 E2E）。

> 上句是**当时的核验记录**。工具面随版本增长，当前数量以 `tools/list` 为准；Qoder 里那个长驻连接器可能仍在跑旧模块缓存——重载前它看不到新工具，用 `python scripts/mcp_build_probe.py` 对构建指纹即可判定（本仓库已实测到这种陈旧：连接器指纹与磁盘不一致）。
若当前会话的工具列表尚未刷新，重启会话或执行 `/mcp reload`；注册项的用户级 root 固定为本仓库，如不需要可在 Qoder MCP 设置中禁用。
若客户端支持 MCP prompts，`start-research` 是一键入口；否则直接说“启动科研智能体”，由 `research-workflow` 技能触发同一流程。

CLI 也可用 `qodercli mcp list` 查看连接状态；修改配置后用 `/mcp reload`。

真实文献获取与实验演示：

```bash
python scripts/qoder_live_literature_task.py   # arXiv 搜索 → 下载 PDF → local S1
python scripts/qoder_live_experiment_task.py   # arXiv + ChemLab 复现 → RunCapsule/EA + claim draft
```

本仓库的 Qoder MCP 端到端测试：

```bash
python scripts/qoder_e2e_test.py
```

覆盖全部工具发现（数量以 `tools/list` 为准）、start-research/review-draft prompt、文献综述、strict G1 停止、G1 CLI 续跑、full_research G2 停止、AstraDraw、手稿修订、closure/lineage status、multi-judge panel、写作包/预审、manuscript bind、support items/verdicts/reuse/archive、human-gold 模板/比较、本地实验包生成（不执行、等待人工 approve）和路径越界拒绝；结果在 `runtime_data/qoder-e2e/<timestamp>/summary.md`。

### 不需要外部 API key：宿主 Agent 就是模型

绑一个 keyless `host_agent` profile 之后，本系统不再向任何 provider 发请求；生成步骤变成一次
可审计的**交接**，由正在使用它的 Agent 用自己的模型完成。对 Qoder / Claude Code / Codex / Zcode
都一样的三步：

```text
1. 宿主 Agent 调 research_bootstrap / research_run（或 writing pack、innovation review）
2. 返回 status=awaiting_host_model + turn_id → 用 research_model_turns 读回提示词原文与期望形状
3. 用自己的模型作答 → research_model_respond 提交 → 重跑第 1 步的命令
```

第 3 步之后不需要任何额外状态：答案按**请求哈希**而不是 turn id 复用，重跑即续跑。提交会被
校验（形状、请求绑定、一次性消费、TTL），校验不过就保持 pending，不会写半成品。

```bash
python -m research_agent host-model bind --modules idea,experiment,paper
python scripts/host_model_loop_test.py --workdir runtime_data/host-model-loop   # 真实 stdio MCP
```

已实测：S1 检索 → S2 假设（宿主作答）→ S4 设计（宿主作答）→ `completed`，6 项检查全过，
G1 仍停在人工门；`research_innovation_review` 同样以 `awaiting_host_model` 结构化返回。
宿主答案与网关答案受同一套门禁：span-only、引用白名单、结果数值上限、章节/占位符/fixture 审计、
支持面板与闭包都照旧执行；`research_model_respond` 不是签核通道，不能 approve/claim/freeze/publish。
`host_label` 由宿主自报，只用于溯源，不能用来主张模型独立性。

### Qoder 聊天框能跑到哪一步

| 场景 | 聊天框内 | 说明 |
| --- | --- | --- |
| 文献综述 / 评审包 | 可以完整跑完 | `research_project_init` → `research_plan` → `research_run(flow_mode=review)` → 读 `task-report.md` / ledgers |
| 严格全流程 | 跑到人工门为止 | `Q0/G1/G2/S5b/G5` 返回 `needs_human`；Qoder 只能展示 CLI 命令，不能替人签核 |
| 门后继续 | 可以，但需要人先做 CLI | 人生成 `g1-decision.json` / `protocol-card.json` / `claim.json` 后，聊天里用 `research_run` 带对应文件续跑 |
| Claim / Closure / Export | 不可以 | 这是设计边界，不是遗漏；MCP 没有 sign/approve/freeze/publish 工具 |
| 外部 Skill | 可以发现/调用/蒸馏 | 只做 instruction-only advisory；脚本必须本地 CLI 显式 `--trusted-scripts` |
| 已有论文修订 | 可以，需把稿件/数据放进项目 | `research_manuscript_revise` 产出修订稿、审计和 DOCX/TeX/PDF；没有 model profile 时为 copy mode |
| 真实模型质量 | 需要 API key / production | 无 key 的 `test` 模式只验证流程，不能当作真实科研效果 |
| 改过 `research_agent/` 之后 | **先比指纹再读结果** | 连接器是长驻 stdio 进程，模块缓存停在启动那一刻；未重载时聊天里读到的是旧行为 |

**每次声称"已在 Qoder 里验证过"之前**，先跑一次本地探针并把两个指纹对上：
```bash
python scripts/mcp_build_probe.py --project runtime_data/power-ladder
# 再看宿主侧 research_status 的 build.fingerprint
```

`build` 字段缺失或两个值不同 ⇒ 服务是旧的，重载 `research-agent` 连接器后重测；
本仓库不重启宿主进程，也不代为修改连接器配置（那是用户环境里的动作）。
探针比对的是同一条 `python scripts/research_mcp_server.py --root <仓库>` 命令在新进程里的答复，
因此差异只可能来自进程内的模块缓存，而不是磁盘代码版本。

推荐对话：

```text
用户：用 research-workflow 在 research-project 里对 inputs/ 做一轮文献综述，review 模式。
Qoder：research_project_init → research_plan → research_run → 读取产物 → 报告 status/证据/缺口。
```

```text
用户：做 full_research，strict，目标输出中文核刊工作稿。
Qoder：research_run → 返回 G1 needs_human 和 CLI 命令 → 停止。
用户：我在本机执行了 flow g1，文件是 runs/<RUN>/g1-decision.json，继续。
Qoder：research_run(g1_decision_file=...) → 继续到 G2/S5b；每一步都只展示人工命令。
```

### 可直接复制的 5 个调用

**1. 文献综述（review，聊天内可完成）**

```text
用 research-workflow 在 research-project 里对 inputs/ 做一轮文献综述，review 模式。
先 research_project_init，再 research_plan，再 research_run；
最后读 task-report.md 和 literature-ledger.json，告诉我覆盖缺口。
```

**2. 严格全流程（停在人工门）**

```text
做 full_research，strict，目标中文核刊工作稿。
每一步到 G1/G2/S5b/G5 就停下来，调用 research_next_actions 给我 CLI 命令；
不要替我签 claim 或冻结 protocol。
```

**3. 已有论文 + 数据修订**

```text
用 research_manuscript_revise 修订 notes/paper.docx。
数据在 notes/results.csv，指标在 notes/metrics.json，图在 notes/figures.json；
venue=software_journal，profile_id=<profile>。
先返回 blocker 和 writer_mode，不要声称 submission_ready=true。
```

**4. AstraDraw 方法图**

```text
先 research_figure_templates，选 survey-framework；
再 research_figure_render，输出到当前项目的 figures/，
标题用 <标题>，报告 SVG audit 和 manifest 路径。
```

**5. 外部 Skill**

```text
先 research_skill_list，只选 enabled 且无 scripts 的 Skill；
用 research_skill_invoke 做 advisory，不要把它当证据；
如果结果值得保留，再用 research_skill_distill 生成 disabled 候选。
```

> 如果 Qoder 只给了文字建议而没有调用工具，补一句：“请实际调用 `research_*` MCP 工具，不要只说明步骤。”

**不能宣称“Qoder 聊天框一键自动跑完全部 S0–S16 并签核”**：系统明确把 claim/closure/export 留给人工。聊天框能做的是编排、执行、读产物和给出下一步；完整闭环是“聊天 + 人工 CLI”的协作闭环。

## 插件包（生成物，别手改）

`plugin/` 由 `python -m research_agent plugin export` 从活注册表派生：`manifest.json`、
`mcp.qoder.json`、`mcp.zcode.json`、`mcp.codex.toml`（Codex 用 TOML 的 `[mcp_servers.*]`）、
`SKILL.md`、`README.md`。根路径默认是占位符 `<RESEARCH_AGENT_ROOT>`，落地到某台机器时用
`plugin export --root <绝对路径>`。

装完之后**第一件事**是协商，不是跑任务：

```bash
python -m research_agent handoff contract --capabilities can_call_tools,can_write_files
```

它只读返回：当前构建指纹、四种传输的实测可用性（含 handoff 目录写探针）、模型绑定与哪些阶段会挂起、
按宿主声明算出的 `blocked` 与下一步命令，以及对任何传输都不可用的六项人工门。
不能调用工具的宿主改走文件通道：`handoff export` → 宿主写 `outbox/MT-*.answer.json` →
`handoff import` → 重跑被挂起的步骤（按哈希重放）。

改动运行时后先验证说明书没过期：

```bash
python -m research_agent plugin verify   # 不一致时退出码非 0
```

## Claude Code

本仓库已包含：

- `.mcp.json.example`（复制为 `.mcp.json` 并替换绝对路径；本机 `.mcp.json` 已被忽略）
- `.claude/skills/research-workflow/SKILL.md`

在仓库根目录启动 Claude Code，首次会提示信任项目级 MCP server。确认后可以直接要求执行科研任务。若没有自动发现技能，检查 `.claude/skills/` 路径并重启会话。

## Codex

Codex 通过 stdio MCP 接入：

1. 参考 `integrations/mcp/codex.config.toml.example`，复制到 Codex 的 MCP 配置；
2. 把 `<ABSOLUTE_ROOT>` 替换为本仓库绝对路径；
3. 重启 Codex 会话，确认发现 `research-agent` 的工具（以 `tools/list` 为准，当前 41 个）；
4. 人工门仍在 CLI，没有 sign/approve/freeze/export 工具。

客户端无关传输冒烟：`python scripts/mcp_transport_smoke.py --root <root>`。它只做 initialize + tools/list，不发模型 Key、不执行科研任务。

## Zcode

Zcode 在 **设置 → MCP 服务器 → 新建** 中选择 `stdio`：

- 名称：`research-agent`
- 命令：`python`
- 参数：`<绝对根目录>/scripts/research_mcp_server.py --root <绝对根目录>`
- 环境变量：
  - `PYTHONPATH=<绝对根目录>`
  - `RESEARCH_AGENT_MCP_ROOT=<绝对根目录>`
  - `PYTHONIOENCODING=utf-8`

也可参考 `integrations/mcp/zcode.mcp.json`。技能副本位于 `.zcode/skills/research-workflow/SKILL.md`；不同 Zcode 版本对技能目录的支持可能不同，MCP 工具本身不依赖技能目录。

注意：Zcode/Qoder 启动子进程时不一定继承你 shell 里的全部环境变量。模型 key 只放**用户/系统环境变量**；Windows 下 `scripts/research_mcp_server.py` 会从 `HKCU\Environment` 回读 key 名并注入子进程，不把 key 写入项目文件、MCP 配置或聊天。修改后重连 MCP；不要把 key 写进项目文件或聊天。

## 已有论文修订与投稿包

MCP 工具：`research_manuscript_revise`

- 输入：项目内的 `.md/.txt/.docx/.tex` 原稿；可选 CSV/TSV/JSON/XLSX 数据表、`metrics.json`、`figures.json`；
- 输出：`<project>/revisions/<REV-ID>/` 下的修订稿、diff、逐句引用/数字账本、指标结果、数据图、审计、Markdown/LaTeX/DOCX/PDF；
- 有 `profile_id` 时逐段改写；没有时为 `copy_mode`，只做数据替换/图表/审计，不会把复制说成改写；
- 模型改写会拒绝新增数字、丢失引用、丢失图表编号、删除实验数字的段落，并回退原文；
- 模板是 `software_journal` / `computer_journal` / `zh_core_journal` 工作 profile，**不是官方模板**；`submission_ready=false`。

```bash
python -m research_agent revision inspect \
  --draft manuscript/01-投稿版-数字引用.md --output-dir runtime_data/revision-inspect
python -m research_agent revision run \
  --draft runtime_data/revision-demo-input/paper.md \
  --data runtime_data/revision-demo-input/results.csv \
  --metrics runtime_data/revision-demo-input/metrics.json \
  --figures runtime_data/revision-demo-input/figures.json \
  --venue software_journal --profile <runtime-profile-id> \
  --output-dir runtime_data/revision-demo-output
```

无 key 的端到端演示：

```bash
python scripts/manuscript_revision_demo.py
```

它会在 `runtime_data/revision-demo-output/` 生成真实 DOCX/TeX/PDF、数据图、diff 和审计；默认 copy mode，传入 `--profile` 才会调用模型改写。

## 写作包与中文稿预审

MCP：`research_writing_pack` / `research_manuscript_audit`；CLI：

```bash
python -m research_agent writing pack --project research-project --run-id <RUN-ID>
python -m research_agent writing audit --project research-project --run-id <RUN-ID> \
  --draft research-project/drafts/review.md
```

- 写作包只投影已有 run：真实来源卡（REF-01…）、选中 span、来源简报、idea/design/run/claim 状态与写作契约；不创建 Claim/EA/gate；
- 草稿只能引用 pack 中的 `[REF-xx]`；未签核 Claim 不发布结果数值，已签核时只允许 `allowed_result_numbers`；
- 审计检查引用键、结果数值、章节、占位符与 fixture；`submission_ready` 始终 false，最多 `ready_for_human_review`；
- 审计不做语义蕴含判断，也不替代同行评审；正式导出仍走 revision/人工流程。

## 顶会语料、创新评审与手稿评审

MCP：`research_conference_fetch` / `research_innovation_review` / `research_manuscript_draft` / `research_manuscript_review`。

- `research_conference_fetch`：按 venue/year 下载 arXiv 公开 PDF；只保留 arXiv comment 明确写主会接收、标题含 agent/研究自动化信号的论文；过滤 workshop/symposium/preprint/findings；不是完整 proceedings 抓取，venue 未独立核验。
- `research_literature_synthesis`：多篇来源 → 主题×来源矩阵；每个主题至少 2 篇，未使用来源显式记录；写作包/创新评审共享该矩阵。
- `research_innovation_review`：从 S1 全文 run 生成 3–6 个缺口与候选想法，跑 novelty/evidence/feasibility 三评审、修订、再评审；引用必须解析到写作包 REF；不运行实验、不创建 Claim。
- `research_manuscript_draft`：写作包+创新评审 → 中文综述/立场初稿 → 确定性审计；不伪造实验/数字。
- `research_manuscript_review`：5 维 rubric 评审 → 修订 → 再评审；候选修订必须通过引用/数值/章节审计且 blockers 不变差；`submission_ready=false`。

本机真实运行（2026-10-26）：22 篇 2024–2026 顶会 arXiv 语料、22 篇全文、16 篇写作包；16 篇 → 6 个跨来源主题、0 篇未使用；6 个缺口、3 个创新方向；中文立场综述 59 处引用、16 个正文来源、0 结果数值、审计 `ready_for_human_review`，导出 DOCX/PDF；模型评审 6.0→6.2（未达 7.0 内部阈值，仍为研究议程）。产物与边界见 `runtime_data/topconf-research-2026/run-summary.md`。

## 实验代码包（只生成，不执行）

MCP：`research_experiment_codegen`；CLI：`experiment scaffold`。

- 输入：run 的 `experiment.json` + 项目内 CSV + target/features/task/methods/seeds；
- 输出：`<project>/experiments/<EXP-ID>/` 的 spec、确定性 runner、requirements、README、code manifest；
- runner 会写 metrics/predictions/run-receipt/artifact-manifest；receipt **不是** RunCapsule/EA/Claim；
- 不安装依赖、不在 MCP 执行、不联网、不通过 G2；用户在本机显式运行；自动启动/探索仍是 roadmap。
- 本地 CLI 生命周期：`experiment approve → run --allow-execute → ingest → claim`；run 记录环境/命令/stdout/stderr/artifact SHA；ingest 写 `experiment-evidence.json`；claim 是 CLI 人签并绑定 evidence hash。
- breast cancer demo 已跑通：dummy accuracy 0.6082，logistic 0.8918±0.0149，evidence verified，Claim 未签；产物在 `runtime_data/experiment-codegen-demo/`。

## 真实 arXiv 文献获取

MCP：`research_literature_fetch`；CLI：

```bash
python -m research_agent literature fetch   --query "self-improving agent large language model"   --target-dir research-project/inputs --max-results 4 --allow-network
```

只下载 arXiv 公开 PDF，网络默认关闭，必须显式 `allow_network=true`；下载后仍用 `source=local` 解析成 span。下载不是证据，摘要也不是全文。

## AstraDraw 方法示意图

AstraDraw 作为 vendored 工作流随仓库保存，原 `AstraDraw-main` 文件夹不需要修改。MCP 提供：

- `research_figure_templates`：列出 7 个内置 scene 模板（`calm-method` / `calm-survey` / `survey-framework` / `tracerl-method` / `role-guided-search` / `self-forcing` / `framework-example`）；
- `research_figure_render`：渲染项目内 `.scene.json` 或内置模板，写入 `<project>/figures/<name>/` 的 SVG/PNG/audit/manifest。

```bash
python -m research_agent figure templates
python -m research_agent figure render   --template framework-example   --output-dir runtime_data/figure-demo   --title "Example Framework"
```

边界：

- 模板只是版式/视觉先验，不能携带模板原有的科学结论；
- 输出 `schematic=true`，不是数据图、不是证据、不是发表许可；
- 不修改 upstream vendor；可编辑 PPTX 仍需要本地 AstraDraw 的 Node/presentations 环境，MCP 不执行。
- 图的形式：SVG + PNG + audit + manifest；Qoder 可直接调用；
- 渲染出的 `<name>.scene.json` 是项目内副本；修改文字/几何后再以 `scene=` 重新渲染即可迭代，不必改 vendored 或原 AstraDraw 文件。

## 外部 Skill 调用与沉淀

MCP 提供三个工具：

- `research_skill_list`：返回 enabled/license/has_scripts/risk_flags 等目录投影，不返回 instructions 或本地路径；
- `research_skill_invoke`：只对 enabled 且无 scripts 的 SKILL.md 做 instruction-only advisory；需要 runtime model profile；返回 advisory/assumptions/limitations/suggested_checks，并记录 usage；可选写 `<project>/notes/skill-invocations/`；
- `research_skill_distill`：把 enabled Skill 复制为 `<project>/notes/skill-library/` 下的 **disabled** `local-*` 候选，要求 license 与 human_reason，复制完整 `scripts/references/assets` 与顶层资源并记录 provenance/逐文件 SHA-256；不执行、不自动启用、不进入 Claim/EA/gate；
- `research_skill_invoke` 的 `distill_on_success` 只在调用成功后才蒸馏，适合“先用，再沉淀”。

MCP 不执行外部 scripts，也不自动启用候选。需要脚本全权限时，由人在本地 CLI 显式开启：

```bash
python -m research_agent skill list
python -m research_agent skill invoke \
  --skill-id <enabled-skill-id> --trusted-scripts --workdir <dir> \
  --script-arg <script-argument> \
  --input-file task.md --output skill-result.json
python -m research_agent skill distill \
  --skill-id <enabled-skill-id> --human-reason "<why>" \
  --library-dir <project>/notes/skill-library
```

`--trusted-scripts` 以当前用户的 OS 权限运行脚本，继承环境变量，**不是 sandbox**；只在确认技能与脚本可信后使用。蒸馏候选仍需人在 CLI 中 review 后启用。

## 其他智能体框架：即插即用

除了 MCP，本仓库还提供框架无关的 HTTP JSON 与 Python SDK：

```bash
python -m research_agent.runtime --port 8787
# 远程访问时设置 RESEARCH_AGENT_API_TOKEN
```

- `GET /api/research/capabilities`：全部工具的 JSON Schema 与 OpenAI function schema（数量以 `tools/list` 为准，当前 41）；
- `POST /api/research/tools/{tool_name}`：统一调用入口；
- `GET /api/projects` / `GET /api/project-experiments?project_dir=...`：只读项目级实验链，返回真实 stages/next_action/evidence summary；执行与签核仍走 CLI/人工；
- `research_agent.client.ResearchAgentClient`：LangGraph / CrewAI / AutoGen / 自研 Python 进程；
- `research_agent.client.LocalResearchAgent`：进程内嵌；
- MCP / HTTP / Python 共用同一套工具契约，没有第二个业务实现。

完整接入示例见 [`FRAMEWORKS.md`](FRAMEWORKS.md)。默认只允许 loopback；远程必须 token、TLS/反代和额外鉴权。无论哪种框架，都没有 sign/approve/freeze/publish 工具。

真实桥接演示：

```bash
python scripts/framework_bridge_demo.py
```

它会启动一个隔离 runtime，用 `ResearchAgentClient` 完成 capabilities → project_init → plan → run → status → read，产物在 `runtime_data/integrations/framework-bridge-demo/`。

## 闭环胶囊与自进化交接

每次 pipeline/task job 会在 run 目录写入 `loop-capsule.json`，外部 Agent 不需要解析散落的 idea/experiment/paper JSON：

- `nodes`：S1→S2–S3→S4→S5→S6→S8–S12→S13→META 的真实状态（done/partial/needs_human/missing/blocked）；
- `blockers`：如 `G1_IDEA_SELECTION_REQUIRED`、`G2_PROTOCOL_FREEZE_REQUIRED`、`S5_NOT_RUN`、`CLAIM_UNSIGNED`、`FIXTURE_ONLY`；
- `next_actions`：带 `owner/gate/command` 的 bounded CLI 下一步；
- `artifact_refs`：当前 run 内可定位的证据文件；
- `boundary`：只读投影，不创建证据/claim/gate/signature/closure。

通过 `research_list_artifacts` / `research_read_artifact`、HTTP artifacts 或直接读文件即可接入。自进化交接只走 CLI：

```bash
python -m research_agent rsi observations show
python -m research_agent rsi observations suggest --output runtime_data/observation-proposal.json
python -m research_agent rsi active show
python -m research_agent rsi active activate --ledger <ledger.json> --lease-scope <scope> --reason "..."
```

MCP/runtime 只读 observation 与 active；没有 activate/sign/approve 工具。

## 人工门边界

MCP 只做“计划、执行、读取、给出下一步”，**没有**以下工具：

- `flow g1`（G1 选择）
- `protocol freeze-design`（G2 冻结）
- `run claim`（Claim 人签）
- `closure sign` / `publish`（导出签核与发布）
- 任何 gate approve / sign 端点

运行返回 `needs_human` 时，MCP 会给出对应 CLI 命令；由人执行并将产物放回项目后，再用 `research_run` 的
`g1_decision_file` / `protocol_file` / `claim_file` 续跑。

## 来源与密钥

- `fixture`：只用于流程验证，不可引用。
- `openalex`：只返回摘要线索，不生成 span，不产生 claim。
- `local`：读取 `<project>/inputs/` 的 PDF/TXT/MD，只有全文才能形成 span。
- `real`：仓库内冻结 CC-BY 语料。

MCP 进程读取自己的环境变量：`RESEARCH_AGENT_MODE`、`RESEARCH_AGENT_MODEL_STORE`、模型 provider key。浏览器 runtime 里粘贴的 session key 不会传给 MCP 进程。

## 维护

三个平台的 SKILL.md 保持同一份内容；修改 `.qoder` 版本后运行：

```bash
python scripts/sync_integration_skills.py
python -m unittest tests.test_integration_files -v
```
