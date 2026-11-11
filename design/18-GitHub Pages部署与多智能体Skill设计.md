# GitHub Pages 部署与多智能体 Skill 设计：把科研智能体做成可公开访问的证据工作台

> 版本：v0.1 · 日期：2026-10-23 · 性质：部署设计 + 多智能体 skill 反思，不新增实验结果
> 上游依据：[16-科研Skill生态调研](16-科研Skill生态调研与动态流程编排.md)、[17-上层微服务架构](17-基于Skill契约的上层微服务架构.md)、[14-产品差异化](14-产品差异化与Demo反思-从证据链写作到证据运营工作台.md)、[09-系统架构](09-系统架构与流程编排设计.md)、[oss/README](oss/README.md)
> 证据纪律：GitHub Pages 能力边界按官方文档与实测 CORS 检查；外部多智能体研究只引公开摘要，不复用效果数字；站点中的数据必须标注 `SIM` / `CACHED` / `LIVE`，不得把模拟当实测。

---

## 0. 一页结论

**能上 GitHub Pages 的是“公开证据工作台”，不是“完整科研智能体运行时”。**

建议把系统拆成三个平面：

```text
┌────────────────────────────────────────────────────────────┐
│  A. 展示平面（GitHub Pages，静态）                          │
│     项目主页 · 真实公共检索 · 证据卡 · 案例回放 · 技能目录   │
│     模式：SIM（演示） / CACHED（预计算） / LIVE PUBLIC（公开 API）│
└──────────────────────────▲─────────────────────────────────┘
                           │ JSON / 静态资源
┌──────────────────────────┴─────────────────────────────────┐
│  B. 预计算平面（GitHub Actions，定时任务）                   │
│     OpenAlex / Crossref 检索 → 去重 → 排序 → 写 digest.json │
│     可选：LLM 摘要（用 Actions Secrets，不暴露到浏览器）     │
└──────────────────────────▲─────────────────────────────────┘
                           │ 可选
┌──────────────────────────┴─────────────────────────────────┐
│  C. 实时平面（本地 / 边缘服务，按需）                        │
│     FastAPI / Cloudflare Worker：LLM、沙箱、Docker、数据库   │
│     密钥只在服务端；Pages 通过健康检查连接，不内嵌 key        │
└────────────────────────────────────────────────────────────┘
```

多智能体部分，不建议“一个阶段一个 Agent”。建议 **1 个编排者 + 3–5 个职责角色 + 1 个人工签核者**：

- **Conductor**：编译任务、选技能、分配工作、记录状态；不写 claim。
- **Scout**：检索、筛选、抽 span、生成覆盖回执；只交 `SourceHit / Span / CoverageReceipt`。
- **Builder**：写协议、草稿、图表；只引用已有 claim，不创建 claim。
- **Executor / Judge**：执行与判定分离；只交 `RunCapsule / Verdict / EA`。
- **Auditor**：结构闭合与论证完整性审计；可阻断，不可改稿。
- **Human signer**：作者/PI；科学决策、实验安全、署名与最终责任。

核心不是“Agent 数量”，而是三件事：**类型化交接（typed handoff）、一对象一写者、证据门禁在 Agent 之外**。

---

## 1. GitHub Pages 能做什么，不能做什么

### 1.1 能力边界

| 能力 | GitHub Pages | GitHub Actions | 本地 / 边缘服务 |
| --- | --- | --- | --- |
| HTML / CSS / JS / SVG / WASM | 可以 | 构建 | 可以 |
| 静态 JSON / 预计算案例 | 可以 | 定时生成并提交 | 可以 |
| 浏览器直连公开 API（CORS） | 可以 | 可以 | 可以 |
| 服务端 API / 数据库 | **不可以** | 不作为常驻服务 | 可以 |
| 长时间任务（实验、沙箱、Docker） | **不可以** | 单次 job 有上限，不适合交互 | 可以 |
| 保护 API key | **不可以**（打包进浏览器即公开） | Secrets 可用 | 可以 |
| 私有稿件 / 未发表数据 | **不建议**（静态资源可被下载） | 私有仓库需谨慎 | 可以 |
| 用户登录 / 权限 | 仅静态或第三方 | 不提供运行时 | 可以 |
| SSE / WebSocket 实时推送 | 无服务端 | 不适合 | 可以 |

GitHub Pages 官方定位是静态站点托管；常见软限制包括约 1 GB 站点、约 100 GB/月流量、约 10 次构建/小时，具体以 [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) 为准。**它不是应用服务器。**

### 1.2 一个关键实测：公开学术 API 可以在浏览器直接调用

2026-10-23 实测：

- `https://api.openalex.org/works?...` 返回 `Access-Control-Allow-Origin: *`，可在静态页直接检索；
- `https://api.crossref.org/works?...` 返回 `access-control-allow-origin: *`，可用于 DOI 元数据；
- arXiv 的 export API 不保证 CORS，不能假定可直连；需要代理或预计算。

因此，**“真实检索 + 去重 + 覆盖回执 + 证据卡登记”可以完全在 GitHub Pages 上跑**，不需要服务器。它不能做的是：调用私有 LLM、跑实验、写全文、做语义判定。这些必须进入实时平面。

### 1.3 三种数据模式

| 模式 | 含义 | 能否声称“真实” | 典型内容 |
| --- | --- | --- | --- |
| `SIM` | 手工构造的交互演示 | 不能 | 三幕工作台、变更传播、签署 |
| `CACHED` | Actions 或人工预计算，带时间戳与来源 | 可以说“某时检索的快照” | 每日 arXiv/OpenAlex 摘要、案例回放 |
| `LIVE PUBLIC` | 浏览器实时调用公开 API | 可以说“刚刚检索到” | OpenAlex 检索、Crossref DOI 查询 |
| `LIVE API` | 连接本地/边缘运行时 | 需附运行日志与版本 | LLM 草稿、沙箱执行、真实导出 |

**规则：页面上每个数字旁边必须有模式徽章；`SIM` 不得伪装成 `LIVE`。**

---

## 2. 三平面部署架构

### 2.1 展示平面：GitHub Pages

静态站点只做四件事：

1. **解释**：这个系统解决什么问题、与现有工作差在哪；
2. **演示**：真实公共检索、证据卡、门禁、案例回放；
3. **证明**：展示真实的接口契约、技能 manifest、运行日志格式；
4. **引流**：进入完整工作台（SIM）或本地运行时（LIVE API）。

站点不承担：用户数据、私有稿件、密钥、长任务、真实同行评审。

### 2.2 预计算平面：GitHub Actions

Actions 是最容易被低估的一层。它可以把“科研智能体”的一小段流水线变成**每天自动运行、结果可追溯**的静态数据：

```text
schedule / workflow_dispatch
  → 读取 queries.json
  → OpenAlex / Crossref 检索
  → 去重、年份/类型过滤、排序
  → 生成 digest.json（query、时间、计数、来源、许可）
  → 校验 schema
  → commit 回仓库（仅数据目录）
  → 触发 Pages 重新构建
```

这条链路是真实的“检索型 Agent”：有输入、有工具、有输出、有日志、有版本；只是没有 LLM 推理。它适合做：

- 每日/每周领域新论文摘要；
- 会议 deadline 前的增量监测；
- 公开证据卡的更新；
- 静态站点的“最近更新”内容。

限制：Actions 不是常驻服务，不能跑交互式会话；job 有时限；私有数据不应提交到公开仓库；LLM key 只能放 Secrets，且输出要检查是否含敏感信息。

### 2.3 实时平面：本地或边缘服务

真正需要 LLM、沙箱、Docker、数据库时，启动一个轻量运行时：

```text
runtime/
  app.py            FastAPI /health /retrieve /draft /run /export
  adapters/         OpenAlex、Crossref、LLM、Docker
  contracts/        Artifact / RunCapsule / Claim / ExportManifest
  .env              密钥（不入库）
```

Pages 通过设置面板连接：

```text
https://<user>.github.io/<repo>/?api=http://localhost:8787
```

连接前必须：

- `GET /health` 返回版本、能力、时间；
- CORS 只允许 Pages 域名与 localhost；
- 需要 `X-API-Token`（存浏览器 sessionStorage，不写死在代码里）；
- 页面明确显示 `LIVE API · <version> · <time>`；
- 断线后降级到 `CACHED`，不假装还在实时运行。

### 2.4 为什么不让 Pages 直接调 LLM

- 任何写进 JS 的 key 都等于公开；混淆只能增加一点成本，不是安全边界；
- 浏览器直连模型会暴露 prompt、项目数据与调用模式；
- 无法做速率限制、成本控制、内容审计与密钥轮换；
- 无法保证模型版本与评测口径一致。

因此：**展示平面可以公开，推理平面必须有服务端边界。**

---

## 3. 前端信息架构：让人 30 秒看懂，3 分钟能操作

### 3.1 页面结构

MVP 采用**一个单屏应用壳**：顶部状态栏 + 左侧工作区导航 + 右侧活动视图。桌面端页面本身不滚动，每个视图内部滚动；默认打开“接入项目”，扫描/读取项目后再进入“研究运行”，不再用长页叙事。

| 视图 | 回答的问题 | 数据来源 | 模式 |
| --- | --- | --- | --- |
| **接入项目** | 已有仓库/文件夹怎么体检、生成研究计划 | 本地文件名 / GitHub 公开元数据 | `LOCAL` / `SIM` |
| **研究运行** | 整体 pipeline 怎么跑、每步对象/指令是什么 | `/demo/?embed=console` | `SIM` |
| **证据工作台** | 检索、复现、句子绑定、变更、签署怎么操作 | `/demo/?embed=workbench` | `SIM` |
| **自进化** | 四问、租约、候选、过程反馈怎么进入下一轮 | `/demo/?embed=evolution` | `SIM` |
| 功能地图 | 13 个功能各自的输入/产物/状态 | 静态数据 | 设计/SIM |
| 证据链 | 六个对象的所有权与依赖 | 静态图示 | 设计 |
| 变更回放 | 一个结果失效后如何传播 | 预计算 JSON | `CACHED` / `SIM` |
| 多智能体 | 谁做什么、不能做什么 | 角色契约 | 设计 |
| 技能运行时 | 技能如何加载、运行、撤销 | manifest | `SIM` |
| 真实检索 | 能不能现在就跑一次 | OpenAlex 实时 | `LIVE PUBLIC` |
| 部署 | 为什么这样部署、怎么部署 | 架构图 | 设计 |
| 文档 | 还有哪些没做 | 文档链接 | — |

桌面端用 `100dvh` 固定壳：`appbar` + `app-layout(sidebar + app-main)`；活动视图 `overflow-y:auto`。默认接入项目：本地文件夹只读扫描文件名/大小，GitHub URL 只读公开元数据；不克隆、不上传、不执行。顶部“演示模式”隐藏 appbar/侧栏、切换为深色舞台并放大运行台，`Esc` 退出；移动端退化为顶部横向标签 + 正常页面滚动，隐藏演示按钮。完整 demo 仍保留在 `/demo/`，由构建脚本从 `demo/index.html` 复制，避免两份代码漂移。

主页通过三个 embed 模式嵌入完整 Demo：`console` 显示 9 阶段研究运行、**LIVE EXECUTION 对象流**（输入 → 操作 → 产物/失败分支）与 **COMMAND TRACE 指令流**（逐条命令、产物、退出状态）；进入视口后自动播放一次，可暂停/单步/重置；`workbench` 只显示证据工作台本体，外部 7 个按钮控制内部 tab；`evolution` 显示四问、租约、候选账本与过程反馈。三者共用同源 iframe。

### 3.2 真实检索实验室的交互

这是主页面的核心，不是装饰：

1. 输入研究主题（默认“钙钛矿太阳能电池稳定性”）；
2. 选择年份与返回条数；
3. 点击“运行检索”；
4. 浏览器请求 OpenAlex `title_and_abstract.search`；
5. 显示真实论文标题、年份、期刊、作者、DOI、被引数、开放获取状态；
6. 去重（DOI / OpenAlex ID）；
7. 生成覆盖回执：query、检索时间、来源、records、unique、included、excluded、过滤条件；
8. 勾选 1–3 篇，登记为“候选证据”；
9. 显示摘要片段与 `unverified` 状态；
10. 用户手写 claim，绑定候选证据；
11. 导出检查：缺摘要核对、缺全文 locator、claim 未确认 → `blocked`；
12. 人工点击“我已核对摘要”后，状态变为 `review_required`，仍不释放导出。

这个流程展示的是**证据纪律**，不是“AI 一键写论文”。页面必须写明：

> 本页只做公共元数据检索、去重、覆盖回执与证据登记；不调用 LLM、不生成研究结论、不做全文核验、不抓取知网/万方/维普。

### 3.3 视觉与交互约束

站点版式参考 `https://yangxc0414.github.io/agent-memory-push/`：宋体大标题、等宽小标签、淡蓝网格背景、细线/直角排版、右侧状态面板与编号列表。只借用排版语法，不复制其业务内容；research-agent 自己的功能地图、真实检索、Agent 拓扑与技能目录使用同一套语法。

- 白底、淡蓝/靛青线条，少量青绿表示通过、琥珀表示待办、玫红表示阻断；
- 证据链上的点沿线流动，表示“对象在传递”，不是“AI 在思考”；
- 每个状态都有文字标签，不能只靠颜色；
- **动效必须由状态变化驱动**：运行台只动“阶段推进 / 子步骤推进 / 失败回退 / 证据权限关闭 / 技能租约”，并同时呈现对象流与指令流；首次加载采用“空白 boot → appbar/侧栏/面板逐个出现”；研究运行首次启动采用控制台 boot → 顶部控制/阶段轨/主画布/记忆/日志依次入场；无 JS 时直接显示内容，`prefers-reduced-motion` 跳过启动动效；阶段卡入场、标题 flash、失败节点呼吸、进度线流光、圆形阶段 HUD、对象流粒子、指令逐字揭示都必须对应状态，不做装饰性随机运动；阶段内容采用单页画册，`‹ 1/N ›` 与方向键翻页，自动运行跟随子步骤翻页，手动翻页后暂停跟随；每个阶段按子步骤逐步展开对象节点、阶段卡、命令与日志，未到达的内容保持淡出，不能一次性铺满；工作台只动“对象选择 / 槽位绑定 / 债务变化”，自进化只动“候选 → EV1–EV4 → 租约 → 下一轮”；不做无数据含义的漂浮粒子；
- **三种镜头共用一个对象模型**：研究运行看时间线，证据工作台看结构，自进化看跨轮继承；切换镜头不改变证据事实；
- **动画可暂停、可单步、可重置**：研究运行台进入视口自动播放一次 SIM 流程，但用户随时可以暂停、单步或重置；
- `prefers-reduced-motion` 时关闭自动播放与流动动画，保留静态状态；
- 360 / 768 / 1024 / 1440 宽度无页面级横向溢出；
- iframe 采用 eager 加载并在加载后锁定高度，避免锚点跳转后的布局抖动；工作台内部按需滚动。

---

## 4. 对现有“多智能体 Skill”的反思

### 4.1 我们实际读到的模式

| 系统 | 多智能体/技能做法 | 强在哪 | 停在哪 |
| --- | --- | --- | --- |
| **Academic Research Skills** | 5 个流水线 Agent、12 个论文 Agent、43 Agent 分级表；阶段边界、状态跟踪、2.5/4.5 完整性门、claim 审计 | 角色契约、检查点、独立完整性检查、可恢复状态 | 固定 10 阶段；Agent 数量与流程 bureaucracy 容易压过任务；没有独立重跑/EA；没有 claim 级变更传播 |
| **AI-Research-SKILLs** | `autoresearch` 双循环；按领域路由 skill；protocol 先 commit；`research-state.yaml` / `findings.md`；六维 rigor reviewer | 非线性的研究节奏、计划先于结果、领域技能可插拔 | 仍是固定 recipe；LLM 路由缺少证据权限；ML/AI 场景为主；没有技能租约与撤销传播 |
| **Scientific Agent Skills** | 177 个技能；`SKILL.md` + scripts/references；渐进加载；测试与安全扫描 | 技能打包、版本化、宿主无关、按需加载 | 技能库不是编排器；不定义 claim/EA/导出契约；不处理技能撤销后的依赖复核 |
| **ARIS / AutoResearchClaw** | 多模型对抗评审、HITL、PRISMA、阶段检查点 | 对抗审查与人工检查点 | 评审多在事后；评审结论不等于可执行证据；固定阶段管线 |
| **通用多 Agent 框架**（LangGraph / CrewAI / AutoGen / ADK 等） | 图/角色/消息编排 | 状态机、并行、工具调用、可观测性 | 不内置科研证据语义；容易把“能对话”当成“能验证” |

> 公开 skill 目录（检索快照，未下载运行）里还有两类容易混淆的“多智能体 skill”：一类是 `crewai-multi-agent` 这种**教宿主如何搭建角色协作系统**的框架型 skill；另一类是 `orchestrate` / `dispatching-parallel-agents` 这种**直接做任务分解、并行分派与审批门**的编排型 skill。前者是“教方法”，后者是“做调度”。我们的 Skills 运行时接近后者，但把权限、证据契约与撤销传播写进 manifest，而不是只写角色提示词。

### 4.2 外部研究给出的三条冷水

1. **MAST（arXiv:2503.13657，NeurIPS 2025）** 基于 150 条标注轨迹归纳出 14 种失败模式，归为系统设计、Agent 间失配、任务验证三大类。结论不是“模型不够强”，而是很多失败来自**任务划分、交接与验证缺失**。[来源](https://arxiv.org/abs/2503.13657)
2. **Anthropic 多智能体研究系统**的经验：编排者 + 子 Agent 适合**广度优先**的并行检索，但 token 成本约为单 Agent 的 15 倍；强顺序依赖的任务不适合拆多 Agent。[来源](https://www.anthropic.com/engineering/multi-agent-research-system)
3. **Agent Skills 的渐进披露**解决的是上下文卫生，不是智能本身；技能目录应保留短索引、按需加载全文与脚本。是否为多级路由，应按任务规模实测，不能假定越深越好。[来源](https://claude.com/blog/skills)

由此得到四条设计约束：

- 多 Agent 只用于**可并行、低耦合、需要独立视角**的环节：检索、阅读、图表、独立复核；
- 协议、执行、claim、写作、导出是**强顺序**的，不能被拆成自由对话；
- 交接必须是**类型化 artifact**，不是把上一轮聊天记录粘贴给下一个 Agent；
- 验证必须独立于生成，且不能只靠 LLM-as-judge。

### 4.3 我们的拓扑：1 + 4 + 人

这里的“4”指 Scout、Builder、Executor+Judge、Auditor 四类职责；Executor 与 Judge 必须是两个隔离角色，不能合并成一个“执行并自评”的 Agent。

```text
                    ┌──────────────┐
                    │  Conductor   │  编译任务 / 选技能 / 记状态
                    └──┬───┬───┬───┘
          ┌────────────┘   │   └────────────┐
          ▼                ▼                ▼
    ┌──────────┐     ┌──────────┐     ┌──────────┐
    │  Scout   │     │ Builder  │     │ Executor │
    │ 检索/阅读 │     │ 设计/写作 │     │ Work     │
    └────┬─────┘     └────┬─────┘     └────┬─────┘
         │                │                │
         │                │          ┌─────▼─────┐
         │                │          │  Judge    │ 独立判定
         │                │          └─────┬─────┘
         └────────┬───────┴────────────────┘
                  ▼
           ┌──────────────┐       ┌──────────────┐
           │   Evidence   │◄──────│   Auditor    │ 只读/可阻断
           │ claim/EA/债务 │       └──────────────┘
           └──────┬───────┘
                  ▼
           ┌──────────────┐
           │ Human signer │ 作者/PI
           └──────────────┘
```

#### 角色契约

| 角色 | 输入 | 输出 | 绝对不能做 |
| --- | --- | --- | --- |
| **Conductor** | 任务 brief、能力图、预算 | `WorkflowRun`、任务分派、状态事件 | 不写 claim、不改稿件、不代替 Judge |
| **Scout** | `QuerySpec`、来源权限 | `SourceHit[]`、`Span[]`、`CoverageReceipt` | 不把摘要当全文证据、不写 claim |
| **Builder** | 已确认 claim、槽位、体裁模板 | `Protocol`、`Draft`、`Figure` | 不新增事实、不创建 claim、不绕过槽位 |
| **Executor** | 冻结的 `TaskSpec`、环境 | `RunCapsule`、`Artifact`、成本 | 不改判据、不读 Judge 的隐藏答案 |
| **Judge** | `RunCapsule`、rubric | `Verdict`、`EA` | 不被 Work 修改、不跳干净重跑 |
| **Auditor** | 全链路 artifact | 审计报告、阻断/放行建议 | 不改稿、不生成 claim、不代替人工签署 |
| **Human signer** | 闭包报告、未解决项 | 签署/拒绝、责任记录 | 不把责任转交给模型 |

#### 交班信封（typed handoff）

```json
{
  "handoff_id": "H-20261023-0007",
  "run_id": "RUN-0311",
  "from_role": "scout",
  "to_role": "conductor",
  "skill": "SK-01@1.1",
  "intent": "retrieve_and_screen",
  "inputs": ["Q-0042"],
  "outputs": ["ART-SPAN-118", "ART-COV-014"],
  "evidence_status": "unverified",
  "budget": { "tokens": 12000, "usd": 0.08, "wall_min": 6 },
  "stop_condition": "included >= 8 or sources_exhausted",
  "trace_id": "TR-9f2c..."
}
```

规则：

1. **只传引用，不传长文**：下游读 artifact store，不读上一轮的完整对话；
2. **每个交接有停止条件与预算**：没有停止条件的 Agent 会无限循环；
3. **一对象一写者**：Scout 不能写 claim，Builder 不能写 EA，Auditor 不能改稿；
4. **证据状态显式**：`unverified` 不能因为“下游需要”就变成 `confirmed`；
5. **并行有上限**：Scout 最多 3–5 个并发；强顺序阶段禁止并行；
6. **审计独立**：Auditor 用不同提示/模型/上下文，只看 artifact 与 rubric，不看生成过程的自辩。

### 4.4 什么时候才增加一个 Agent

只有满足以下之一才拆：

- 任务可并行且彼此低耦合（如多源检索、多图独立生成）；
- 单上下文放不下（需要上下文隔离）；
- 需要独立视角（Judge/Auditor 不能与生成共享同一上下文）；
- 有可测量的瓶颈（延迟、错误率、人工干预次数）。

否则，用一个函数、一个服务或一个 skill 就够了。**“多智能体”不是成熟度标志。**

### 4.5 Skill 在多智能体中的位置

Skill 是**程序性知识包**，不是 Agent：

```text
Skill = SKILL.md（何时用/步骤/边界/校验）
      + manifest（权限/证据契约/适用域/测试/许可证）
      + scripts/references（按需加载）
```

- 同一个 Skill 可以被 Scout、Builder 或多个 Agent 使用；
- Skill 的权限按调用角色收窄，不按“技能自己”放大；
- Skill 只产出 artifact，不直接写 claim / manuscript / closure；
- Skill 升级、撤销、领域漂移时，依赖它的 artifact 进入复核；
- 技能目录保持扁平，完整 `SKILL.md` 与脚本按需加载；不要为了“分层”增加路由层。

这与 [16-](16-科研Skill生态调研与动态流程编排.md) 的“能力图 + 任务编译 + 技能运行时 + 证据权限”一致；[17-](17-基于Skill契约的上层微服务架构.md) 则给出了 `SkillRuntimePort` 与服务边界。

---

## 5. GitHub Pages 站点实现

### 5.1 目录

```text
site/
  index.html              主页 + 真实检索实验室
  assets/style.css
  assets/app.js
  data/queries.json       预计算检索式
  data/digest.json        Actions 预计算输出（可选）
  demo/index.html         构建时从 demo/ 复制
  404.html
.github/workflows/
  pages.yml               构建并部署 site/
  refresh-digest.yml      定时检索并提交 digest（可选）
scripts/
  build-site.mjs          复制 demo、校验 JSON
  refresh-digest.mjs      OpenAlex → digest.json
```

### 5.2 构建与部署

`build-site.mjs` 只做三件事：复制 `demo/index.html`、校验 `site/data/*.json`、打印部署提示。不做打包、不引入框架。

`pages.yml` 使用官方 Actions：

```yaml
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
```

步骤：`checkout → setup-node → build-site → configure-pages → upload-pages-artifact → deploy-pages`。

### 5.3 路径与缓存

- 站点资源全部用相对路径（`./assets/...`），兼容 `https://<user>.github.io/<repo>/`；
- 不使用 history 路由；如必须，使用 hash 路由并配 `404.html`；
- Pages 不能自定义长缓存头，静态资源用内容 hash 或查询参数破缓存；
- 不把 `node_modules`、`oss/`、`papers/` 上传到 Pages；站点只包含 `site/` 与复制后的 demo。

### 5.4 安全

- 仓库内不出现任何 API key、token、私有稿件；
- Actions Secrets 只用于预计算；日志中不打印 key；
- 公开站点只展示公开元数据与人工批准的案例；
- 不抓取知网/万方/维普；不绕过付费墙；不使用未授权全文；
- 页面明确标注 AI 使用与责任边界；导出仍是草稿，不是自动投稿。

### 5.5 本次已实现的静态原型

仓库内已加入：

- `site/index.html`：**单屏应用壳**（顶部状态栏 + 左侧工作区 + 右侧活动视图），默认打开接入项目；包含接入项目（本地文件夹 / GitHub 元数据 / 示例）、研究运行（对象流 + COMMAND TRACE + 仓库场景）、证据工作台、自进化、13 项功能地图、证据链、变更回放、Agent 拓扑、技能运行时、真实检索、部署与文档；
- `site/assets/app.js`：OpenAlex 实时检索、去重、覆盖回执、证据登记、门禁检查、Agent/技能交互；
- `site/demo/index.html`：构建时从 `demo/index.html` 复制，保持单一源；
- `scripts/build-site.mjs`：复制 demo、复制文档、校验 JSON；
- `.github/workflows/pages.yml`：GitHub Pages 构建与部署；
- `.github/workflows/refresh-digest.yml` + `scripts/refresh-digest.mjs`：定时公开检索并提交 `digest.json`；
- `site/data/digest.json`：2026-10-23 手工从 OpenAlex 取回的快照，页面标为 `CACHED`，不是 Actions 运行结果。

**目标地址**：`https://yangxc0414.github.io/research-agent/`。仓库尚未初始化/推送到 GitHub，因此该地址尚未上线；站点的 `LIVE PUBLIC` 检索已在本机浏览器验证，`SIM` 案例与技能状态仍是演示。前端使用 `assets/base.css` + `assets/theme.css`（参考页公开样式底座）与 `assets/custom.css`（research-agent 自有组件）；如果要完全去除参考页样式，只需替换这两层并保留 custom。

### 5.6 v0.3 前端细化：从“能演示”到“可逐眼检查”

第三十六轮把界面与动效从整块淡入改成状态驱动的细粒度反馈，原则仍是**不装饰、只解释状态**：

| 层面 | 细化 |
| --- | --- |
| 页面壳 | view 有 20px 安全边距；面板 14px 圆角；appbar 下方载入扫线；appbar 标题与 studio 标题切换时短入场；iframe 切换有 `mounting research context` 遮罩，避免白闪 |
| 接入页 | 空态直接展示报告结构；只读扫描分“读目录 / 枚举复现信号 / 生成候选方向”三步；分数环从 0 计数；缺口按优先级、候选按可点击按钮排布；目标有 160 字计数；≤1180px 改为单列并把来源表单单列居中，避免窄报告 |
| 演示头 | 固定大标题改为模式化紧凑头：RUN CONSOLE / EVIDENCE WORKBENCH / SELF-EVOLUTION，分别用蓝/青/紫强调色；只保留事实条、状态行与一条折叠的 skill runtime |
| 研究台 | 双环 HUD（阶段 + 子步骤）、STAGE 眉标、head 底部子步骤进度线；阶段轨完成勾与 active 进度条；对象流只追加新增节点，旧节点不重建，新增连线生长，未展开部分用 PENDING 占位；卡组 dots 显示已展开/锁定，自动跟随可切“手动”，翻页有方向；指令流按阶段分组、token 着色、当前/全部筛选、当前行扫光；侧栏卡按阶段聚焦，记忆计数 +Δ，复现状态 flash，日志只让新行入场 |
| 启动 | 页面 boot 约 1.05s；控制台 boot 缩短，先让模块入场，再延迟约 1s 起跑，避免遮罩把 P0 前几步吃掉；无 JS / reduced-motion 直接显示内容 |
| 演示模式 | 隐藏 studio 头、工具条、skill、frame bar 与页脚，让运行台从 12px 起铺满；`Esc` 退出按钮移到底部，不遮运行控制 |

验证：Playwright 覆盖 360/390/768/900/980/1024/1200/1440/1920，文件夹与 GitHub URL 接入、阶段跳转/翻页/跟随/筛选、无 JS、reduced-motion 与演示模式；无页面级横向溢出或控制台错误。所有新增数字与状态仍为 `SIM`。

### 5.7 v0.3.1 STAGE CONTRACT：把 demo 落回仓库契约

上一版 demo 已经能讲“9 阶段”，但阶段与 `09-` 的 S0–S16、`17-` 的服务/端口、`11-` 的过程协议之间还是靠观众自己联想。第三十七轮新增可展开的 **STAGE CONTRACT** 条，把每个 P 阶段映射到真实契约，并明确区分“设计契约”和“本轮 SIM 运行”。

| P | 服务 / 端口 | S 段 / 门禁 | artifact 链（节选） | 硬不变量 / 角色 |
| --- | --- | --- | --- | --- |
| P0 | Workflow · Orchestrator | S0/S4 · G2′ | TaskSpec · RunInstance · Checkpoint | INV-3 · Planner |
| P1 | Knowledge · RetrieverPort | S1 · Q0 | QuerySpec · SourceHit · Span · CoverageReceipt | INV-1 · Librarian/Reader |
| P2 | Workflow · hypothesis.generate | S2/S3 · G1 | HypothesisCard · ConflictEdge · GapCard | RULE · Ideator/Critic |
| P3 | Workflow / Execution · protocol.freeze | S4 · G2/G2′ | Protocol · TaskSpec · RunPlan | INV-3 · Architect |
| P4 | Execution · JudgePort | S5e/S5c · X0–X7 | RunCapsule · Verdict · EA · FailureRecord | JUDGE · Work/Judge |
| P5 | Evidence · claim.create | S5c/S9 · verdict + EA | Verdict · EA · result_claim · EvidenceLink | INV-1 · Curator/Judge |
| P6 | Manuscript · WriterPort | S6–S10 · G3/Q1 | Manuscript · Sentence · Slot · Figure | INV-1 · Writer/Figure |
| P7 | Closure / Export · ExporterPort | S12–S16 · Q1/G4/G5 | ClosureReport · Signature · ExportManifest | INV-2 · Verifier/Export |
| P8 | Skills / Evidence / Audit | 跨轮 · EV1–EV4 → M1 | EvolutionCandidate · AdmissionRecord · InheritanceLease | INV-4 · Curator/Human |

条内同时显示：

- **FAILURE ROUTE**：例如 P7 的 `G5 失败 → 阻止导出`，P4 的 `verifier_error → FailureRecord`；
- **PROCESS PROTOCOL / SIM**：`PF-P0@v1` 六字段、`PF-P4@v1` 失败→修订→重跑、`PF-P5@v1` 拒绝移动门槛（rejected）、`PF-P8@v1` 一次成功不晋升（pilot）；
- **LIMIT**：P4 没有真实沙箱/镜像/seed，P5 没有真实 Judge/实验数据，P7 没有真实签名/模板/导出包，P8 没有跨轮真实对照；
- **REFS**：`09 §5.3/§5.12`、`17 §2/§4.2`、`11 §9.1`。

**一个必须保持的边界声明**：P0–P8 是 S0–S16 的**叙事压缩**，rail 上的 X0/G1/G2/… 是演示标签；条内给出真实 S 段与门禁，二者不一一对应。这个声明直接显示在条内备注里，避免把 demo 的 9 阶段误读成实现架构。指令流分组头也加上服务名（`Evidence · 3/3 · C3`），让“命令属于哪个 bounded context”可见。

### 5.8 v0.3.2 一屏聚焦与因果动效

上一版在 1440×900 下控制台约 960–1000px，指令流仍在首屏之外；这一版按“减法”处理：

- **聚焦视图**：控制台新增“聚焦”按钮；站点“演示模式”通过 `postMessage` 自动开启。聚焦时收起运行日志、压缩阶段卡/指令区、关闭展开的契约正文；对象流、阶段卡、当前指令、反馈与右侧证据状态落在一屏内。可切回“全览”，日志用 `max-height/opacity` 过渡，演示模式下 iframe 高度同步缓动。
- **阶段封印**：阶段推进时，在 STAGE 眉标旁短暂显示上一阶段的 `P·gate·SEALED`（如 `P1 · G1 · SEALED`），与阶段轨勾选、HUD 外环推进形成同一因果序列；完成后不常驻。
- **对象/指令同步**：新增对象节点出现一次性光环，当前指令行出现同步脉冲（同一 680ms 缓动），让“指令被发出 → 对象生成”可被看见；失败节点仍保留呼吸/失败路径。
- **噪音收敛**：移除对象流背景扫光；保留阶段入场、卡组方向翻页、HUD 子环、记忆 +Δ 等有状态的动效。命令/对象/契约字号整体上调。
- 聚焦在 ≤1100px 时隐藏右侧证据栏，避免它落到指令流下方破坏一屏；>1100px 保留三栏。

验证：1440×900 演示模式下命令面板与反馈条均在首屏内（iframe 坐标系命令底部约 830px、反馈底部约 883px）；≤1100px 聚焦时隐藏右侧证据栏。聚焦/全览切换、`Esc` 退出、阶段封印、移动端聚焦和 360–1920 无横向溢出均通过，控制台无错误。

### 5.9 v0.3.3 可用性与细粒度交互审计（2026-10-23）

这一轮不再加“展示模块”，而是按真实使用路径做可用性回归：**打开 → 进入研究台 → 选择场景 → 运行/暂停/单步 → 看阶段 → 聚焦 → 移动端回看**。用 Edge headless + Playwright 在 1440/1024/768/390/320 五个宽度量测 `scrollWidth`、控制台错误、导航/工具栏/阶段导航是否可见。

**发现的问题（改前）**：

1. 1024px 时 8 个导航项被挤成两行，中文标签竖排；Brand 副标题也换行。
2. 1024px 控制台工具栏换行后靠左，与场景选择脱节，主按钮在视觉上被“悬空”。
3. ≤900px 阶段轨变成横向滚动条，但标签被裁、没有明确的上一阶段/下一阶段入口；768px 只能看到前 4 个阶段。
4. 390px 场景选择仍是 3 列，第 4 个“仓库”掉到第二行，形成孤行。
5. 一轮约 23 秒，演示/复盘时缺少速度控制；只能等或频繁单步。
6. 键盘只能 Tab 到按钮；没有运行/暂停/单步/速度的快捷键，也没有可见提示。
7. favicon 缺失导致控制台一条 404；焦点样式不统一。
8. 站点壳层移动端侧栏可横向滚动，但边缘被硬裁，缺少“还能滑”的视觉提示。

**这一版的处理**：

- **响应式导航**：≤1180px 隐藏二级导航，只保留 Brand + 主 CTA；`.nav-cta` 始终右对齐；Brand 副标题 `nowrap`。1024px 不再出现中文竖排。
- **控制台工具栏**：`.console-actions` 增加 `margin-left:auto; justify-content:flex-end`；换行后仍与右边缘对齐，主按钮不再悬空。
- **运行速度**：新增 `1× / 2× / 4×` 速度按钮（`S` 循环），只改变动画调度间隔，不改变任何阶段/门禁/证据状态；刷新后回到 1×，避免误以为运行结果变了。
- **键盘操作**：`Space` 运行/暂停、`N` 单步、`R` 重置、`F` 聚焦、`S` 速度；按钮加 `aria-keyshortcuts` 与 title；输入框/按钮聚焦时不拦截按键。运行副标题直接显示快捷键提示。
- **移动端阶段导航**：≤900px 隐藏横向阶段轨，改成“上一阶段 / 当前阶段名 / 下一阶段”的 stagebar；`aria-live` 播报当前阶段；首尾按钮自动禁用。这样 768/390/320 都不再依赖被裁剪的横向滚动。
- **移动端场景选择**：≤640px 改为 4 列等宽，四个场景在同一行；不再出现第 4 项孤行。
- **细节修复**：内联 SVG favicon 消除 404；统一 `:focus-visible` 外 outline；站点壳层侧栏增加右侧渐隐 + `scroll-snap`，明确“横向还有内容”。
- **不改的东西**：所有运行数据仍是 SIM；不新增“已完成/已生效”状态；不把速度按钮做成“加速真实实验”。

**验证结果**：

| 宽度 | 横向溢出 | 控制台错误 | 布局结果 |
| --- | --- | --- | --- |
| 1440 | 0 | 0 | 完整导航；三栏控制台 |
| 1024 | 0 | 0 | 二级导航隐藏；CTA 右对齐；工具栏右对齐 |
| 768 | 0 | 0 | stagebar 可见；阶段轨隐藏；场景一行 |
| 390 | 0 | 0 | 4 列场景；stagebar；工具栏两行 |
| 320 | 0 | 0 | 无溢出；stagebar 可用；焦点 outline 可见 |

- 1× 约 4.5s 仍在 P1；4× 约 4.2s 已到 P4 附近，说明速度控制只影响节奏，不跳阶段。
- 聚焦模式在 1024 仍 0 溢出，标签从“聚焦”切为“全览”；`prefers-reduced-motion` 下无动画报错。
- 站点壳层 390 无横向溢出；侧栏渐隐可见。

**还没做 / 下一轮**：

- 快捷键的可视化帮助面板（当前只有 title + 副标题提示）；首次使用 onboarding。
- 屏幕阅读器的完整朗读顺序与 `aria-describedby`；真实键盘用户测试。
- 把 `WritingProfile`（中文期刊/英文会议/学位论文/基金）做进研究台，而不是只留在设计文档。
- 把多智能体并行泳道、证据 `pending_evidence → bound → stale` 做成可切换视图；当前只展示阶段/对象/指令。
- 真机性能与低端移动端滚动测试；目前只验证了无溢出与交互路径。

> 边界：以上是 SIM Demo 的可用性改进，不是产品效果验证；没有真实运行、没有用户研究样本、没有可宣称的效率提升数字。

---

## 6. 实施顺序

### W1：静态主页 + 真实检索

- 主页、证据链示意、真实 OpenAlex 检索、证据卡、门禁；
- 复制现有工作台到 `/demo/`；
- 360–1440 宽度检查，无横向溢出；
- 所有数据带 `LIVE PUBLIC` / `SIM` 徽章。

### W2：Actions 预计算

- `refresh-digest.yml` 每日检索一个公开主题；
- 生成 `digest.json`，带 query、时间、计数、来源、许可；
- 主页显示“最近一次自动检索”，并链接到原始记录；
- 失败时保留上次成功版本，不覆盖为空白。

### W3：本地实时运行时

- `runtime/` FastAPI：`/health`、`/retrieve`、`/draft`、`/run`、`/export`；
- Pages 设置面板连接本地 API；
- 密钥只放 `.env`；CORS 白名单；
- 真实 LLM 草稿必须绑定 claim/span；没有证据的句子标 `unsupported`。

### W4：真实任务纵切

- 选一个真实小任务：检索 10 篇 → 人工确认 3 条 claim → 生成 1 段草稿 → 导出检查；
- 保存完整 trace，作为 `CACHED` 案例发布；
- 记录人工干预、失败与回退；
- 不宣称“自动写完一篇论文”。

### 验收标准

- 访客 30 秒内能说出“这是证据运营，不是聊天写作”；
- 真实检索返回可核对的标题/DOI/年份，覆盖回执可展开；
- 证据卡明确显示 `unverified`，导出默认 `blocked`；
- 技能卡显示 manifest、权限、证据契约、撤销影响；
- 部署说明能让另一个人从零跑起 Pages；
- 所有数字有来源与模式，没有把 SIM 写成实测。

---

## 7. 不可宣称

- 不写“GitHub Pages 上运行完整科研智能体”；它只运行静态 UI 与公开 API 检索；
- 不写“多智能体一定优于单 Agent”；外部研究反而提示强顺序任务会退化；
- 不写“Agent 数量 = 能力”；角色多不等于证据强；
- 不写“真实检索 = 真实结论”；检索只证明来源存在，不证明 claim 成立；
- 不写“摘要核对 = 全文核验”；页面必须区分；
- 不写“自动导出 = 自动投稿”；导出仍是草稿，需作者/PI 签署；
- 不把外部系统的效果数字当本项目结果；不把 star 数当质量证据。

---

## 8. 来源

| 来源 | 用途 | 证据等级 |
| --- | --- | --- |
| [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) | 静态托管能力与限制 | 官方文档 |
| [OpenAlex API](https://docs.openalex.org/) | 公开文献元数据；实测 CORS `*` | 官方文档 + 2026-10-23 实测 |
| [Crossref REST API](https://api.crossref.org/) | DOI 元数据；实测 CORS `*` | 官方 API + 实测 |
| [Why Do Multi-Agent LLM Systems Fail? (arXiv:2503.13657)](https://arxiv.org/abs/2503.13657) | MAST 14 种失败模式/3 类 | 论文摘要 |
| [Anthropic: multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) | 编排者-工作者、广度优先、约 15× token | 工程博客 |
| [Claude Agent Skills](https://claude.com/blog/skills) | 技能目录与渐进披露 | 官方博客 |
| [Agent Memory 推送](https://yangxc0414.github.io/agent-memory-push/) | 前端版式参考：宋体标题、等宽标签、淡蓝网格、状态面板 | 公开页面 + 本地 CSS 解读 |
| [16-科研Skill生态调研](16-科研Skill生态调研与动态流程编排.md) | 本地快照与机制对照 | 本项目调研 |
| [17-上层微服务架构](17-基于Skill契约的上层微服务架构.md) | 服务边界、端口、硬不变量 | 本项目设计 |
| `oss/Academic-Research-Skills-curated/` | 5/12/43 Agent、检查点、完整性门 | commit `3224a27`，CC BY-NC 4.0，仅对照 |
| `oss/AI-Research-SKILLs-curated/` | 双循环、protocol freeze、六维 rigor | commit `773a529`，MIT |
| `oss/Scientific-Agent-Skills-curated/` | 177 技能、渐进加载、测试 | commit `593377b`，MIT |

> 外部效果数字未复现；star 数只作关注度；本地快照只读，不运行。
