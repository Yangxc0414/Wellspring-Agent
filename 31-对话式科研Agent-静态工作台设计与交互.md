---
title: 对话式科研 Agent：静态工作台设计与交互
date: 2026-10-24
status: design + static implementation
scope: site/agent + static state machine; no API
related: [14, 21, 27, 28, 29, 30, 32, 33, 34]
---

# 对话式科研 Agent：静态工作台设计与交互

> 目标：把平台从“可看的演示”推进到“可用的工作台”。用户可以新建项目、用对话推进调研、设计实验、启动受治理的全自动、处理人工门、审批/回滚自进化候选，并查看证据链与运行上下文。
> 本轮**不接 API**：所有模型/实验/claim 都是静态状态，页面明确标 `SIM · STATIC`；先把交互、对象、状态与失败路径设计对，再替换 adapter。

---

## 0. 结论

1. **对话是控制面，不是全部。** 科研 agent 不能只有聊天：每条回复旁边要有可检查的 artifact（来源、span、协议、RunCapsule、EA、claim、closure）与状态（pending/blocked/signed）。`site/agent/` 采用“项目侧栏 + 会话 + 运行/证据/自进化上下文”的三栏结构。
2. **三种模式足够，不要做成功能菜单。** `调研 / 实验 / 全自动` 分别对应 S1–S3、S4–S5、S1–META；证据与自进化是上下文，不是第四、第五种流程。
3. **全自动必须停在人工门。** 自动执行 S1→S5→S6→S8→S13，在 claim 处暂停；“模拟签核”是显式的 SIM 动作。没有自动 claim、没有自动导出、没有跳过 gate。
4. **自进化要出现在工作流里，不是单独的仪表盘。** 运行结束后在会话里出现候选卡：target/patch/rationale/predicted/EV1–EV4/lease；右侧显示 harness 版本、租约、lineage、回滚；下一轮显示加载新 harness。
5. **静态层也要“可操作”。** 新建项目、发消息、跑检索、设计/冻结/运行实验、启动/暂停/单步全自动、签人工门、批准/拒绝/回滚候选、导出状态、重置——全部有真实状态变化，不是自动播放动画。
6. **所有数字都标 SIM。** 页面没有真实 API、没有真实实验、没有密码学签名；`claim` 只用于演示人工门，不是科学结论。
7. **未来接 runtime 的接口应是 adapter，不是重写 UI。** 静态版有 `StaticWorkspaceAdapter`；未来替换为 `RuntimeWorkspaceAdapter`，UI 只消费 `Project / Message / Card / Evidence / Evolution` 对象。

---

## 1. 产品定义

### 1.1 一句话

> **Research Agent 是一个对话式科研工作台：对话负责推进，artifact 负责留下证据，gate 负责让人保留最终判断。**

不是“通用聊天机器人”，也不是“论文一键生成器”。它要回答：

- 我现在在研究什么？目标是什么？
- 系统刚才做了什么？产出了什么对象？
- 哪些结论有证据，哪些只是候选？
- 为什么被 gate 挡住？下一步该做什么？
- 上次的改进是否真的加载了？如何撤销？

### 1.2 用户旅程

```text
新建项目 / 选择示例
  → 对话描述目标
  → 系统给检索计划
  → 来源 + span + gap
  → gap 变成候选假设（G1 人工）
  → 实验协议（G2 人工冻结）
  → run → RunCapsule/EA（claim 人工）
  → 结果图 / 写作槽（pending）
  → closure（blocked/reason）
  → 全自动模式：同一链路自动推进，但在 claim 处停下
  → 自进化候选：EV1–EV4 + lease → 下一轮加载 / 拒绝 / 回滚
```

### 1.3 非目标

- 不做通用聊天助手；不回答与项目无关的闲聊。
- 不做“模型自己改 claim/gate”；候选只能改 skill/process/prompt/knowledge。
- 不把聊天记录当共享状态；对象/artifact 才是状态。
- 不接 API、不训练、不执行真实实验、不生成真实 claim（本轮）。
- 不把 SIM 数字写成结果。

---

## 2. 信息架构

### 2.1 桌面三栏

```text
┌ appbar: brand / project switch / 调研·实验·全自动 / SIM / new / palette / export ┐
├──────────────┬──────────────────────────────────────────────┬──────────────────┤
│ PROJECTS     │ THREAD                                       │ CONTEXT          │
│ 项目列表      │ 目标 / 状态 chips                            │ RUN              │
│ QUICK START  │ 用户/Agent 消息                              │ EVIDENCE         │
│ RUN CONTEXT  │ 计划/来源/gap/假设/协议/run/ gate/候选卡       │ EVOLUTION        │
│ 版本/边界     │ composer + suggestions                       │ 下一步            │
└──────────────┴──────────────────────────────────────────────┴──────────────────┘
```

- **appbar**：对话切换、模式、模型入口、全局动作。移动端隐藏对话下拉，保留模式与 CTX 抽屉。
- **侧栏**：从上到下是 `新的任务`、`搜索`、`工作区`（材料实验室 / Agent 研究 / 毕业设计；文件夹树，任务嵌套在各自工作区下、可展开）、`最近任务`（跨工作区，组头可折叠）、底部 `站点 / 自动化 / 扩展 / 更多` 与“设置与工具”。Quick Start 与 Run Context 已移出侧栏，运行上下文留在右侧。
- **会话**：用户消息靠右，Agent 消息靠左；Agent 文本 + artifact 卡；系统事件用细线小字。底部 composer 常驻。
- **单页边界**：新建任务、模型设置、工具/个性化、暂停/单步/签核都在同一页的弹窗、抽屉或面板里完成；`site/models/`、`site/live/` 只作为高级配置/运行子页面，从设置面板进入并标明“SUBPAGE”，不进入日常路径。移动端侧栏收起为 `TASKS` 抽屉，仍用同一套工作区/最近任务切换会话。
- **上下文**：三个 tab：
  - `RUN`：当前阶段、9 步、对象链、gates、预算；
  - `EVIDENCE`：gap/候选/EA/claim/closure；
  - `EVOLUTION`：harness、process feedback、候选、lease、lineage。
- **下一步**：上下文底部固定显示“下一步”提示，避免用户不知道点哪里。

### 2.2 为什么不是“长页”

长页适合解释设计，不适合持续工作。工作台必须：

- 项目/模式/会话/上下文在一屏内；
- 只有会话与上下文内部滚动；
- 移动端退化为正常滚动 + 抽屉，不嵌套滚动；
- 关键动作始终在可视区（composer、gate 按钮、候选按钮）。

---

## 3. 三种模式与状态机

### 3.1 调研模式（RESEARCH / S1–S3）

- 输入：研究问题、项目目标。
- Agent 动作：query plan → sources/spans → gap → candidate hypotheses。
- 人工门：G1；系统只产候选，不自动选短名单。
- 输出：`QueryPlan / SourceHit / Span / CoverageReceipt / Gap / IdeaCard`。
- 证据边界：摘要-only 不生成 span；没有全文不能当证据；不产 claim。

### 3.2 实验模式（EXPERIMENT / S4–S5）

- 协议卡：hypothesis / baseline / metric / seeds / controls / status。
- 人工门：G2 冻结；S5 claim 人签。
- 运行卡：RUN id / dataset / seeds / metric / baseline / EA / claim 状态。
- 证据边界：没有冻结协议不能运行；没有 EA 不能 claim；没有 claim 不能填结果槽。

### 3.3 全自动模式（GOVERNED AUTO / S1–META）

自动推进 9 个阶段：

| # | 阶段 | 命令 | 输出 |
|---:|---|---|---|
| 1 | S1 文献检索 | `retrieval.query` | 3 sources / 12 spans / gap |
| 2 | S2–S3 假设 | `idea.frame` | 2 candidates / G1 (SIM) |
| 3 | S4 设计 | `design.freeze` | protocol frozen / G2 |
| 4 | S5a 运行 | `run.work` | RUN-014 / 3 seeds |
| 5 | S5b 判定 | `judge.verify` | EA sealed / claim unsigned |
| 6 | S6 图 | `figure.render` | SVG + manifest bound EA |
| 7 | S8–S12 写作 | `paper.bind` | result.primary pending |
| 8 | S13–S16 闭包 | `closure.check` | 9/11 · citation pending |
| 9 | META 自进化 | `rsi.propose` | candidate budget 6→3 |

**关键**：第 5 步是人工门，自动模式会暂停。用户必须显式点击“模拟签核”（SIM）才继续；真实系统中这里应走 CLI/人工签署，不会由浏览器自动完成。

### 3.4 控制动作

- `启动全自动`：从当前项目开始一轮；若已有 pending 候选，先审批，不叠加。
- `暂停` / `继续` / `单步` / `停止`：所有状态可见；停止不会清除已产生对象。
- `保持 pending`：gate 保持 blocked，导出不打开。
- `批准候选`：发放 lease，harness 版本 +1；下一轮加载新版本。
- `拒绝`：保留负结果，不重试无新证据的提案。
- `撤销租约`：回滚 harness；依赖产物需要复核，不假装“回滚 = 修复”。

---

## 4. 自进化如何“被看见”

### 4.1 四个可见位置

1. **会话里的候选卡**：运行结束出现 `CAND-S1-01`；包含 target/patch/rationale/predicted/EV1–EV4/lease；动作“批准/拒绝”。
2. **右侧 EVOLUTION**：harness 版本、scope、TTL、process feedback、candidate、lineage；动作“批准/撤销”。
3. **顶栏/侧栏**：`v1 → v2 · budget 6→3`、`auto paused / human gate`，让当前加载的 harness 一眼可见。
4. **下一轮会话**：启动下一轮时显示 `v2 · budget 3`，让“上次改进被加载”成为可观察事实。

### 4.2 候选对象

```text
Candidate
  id, kind (process/prompt/skill/knowledge),
  target, patch, rationale, predicted,
  ev[4] (reason / retain/scope / transfer / gain),
  lease (scope + TTL), status (pending/active/rejected/revoked)
```

静态版候选示例：

- `CAND-S1-01`：`literature.retrieval.budget`，`budget 6 → 3`，预测 `cost −40%; recall non-inferior`；EV1 reason、EV2 scope、EV3 near-OOD、EV4 cost。
- 第二轮：`process.literature.read_order`，`broad-first → deep-read top-2 → broad`；预测 span +2 / cost +1；EV3 transfer 仍标 pending（不假装通过）。

### 4.3 不能写成什么

- 不能写“系统已经会自进化”：静态版是**受治理的候选演示**，没有真实评测、没有真实租约执行。
- 不能写“候选一定提升能力”：预测与 EV 只是展示；真实系统要 held-out、sealed evaluator、两次以上完整循环。
- 不能写“回滚 = 修复”：回滚只恢复 harness；依赖产物仍要重新复核。

---

## 5. 静态层与未来 API 的边界

### 5.1 当前实现

- `site/agent/index.html` + `agent.css` + `agent.js`；
- 状态存在 `localStorage`（`researchAgent.workspace.v1`）；
- 没有 `fetch`、没有模型调用、没有后端；
- 所有指标、来源、claim、租约均为示例数据；
- 顶栏/输入区持续显示 `SIM · STATIC`。

### 5.2 未来 adapter 映射

| UI 动作 | 当前静态实现 | 未来 runtime |
|---|---|---|
| 发送消息 | 本地 deterministic reply | `POST /api/sessions/{id}/messages` + SSE |
| 开始检索 | 本地 source card | `POST /api/runs`（S1） |
| 冻结协议 | 本地状态变更 | `POST /api/designs/{id}/freeze`（人签） |
| 运行实验 | 本地 run card | `POST /api/runs`（S5）+ SSE |
| 签 claim | 本地 SIM | CLI/人工签署；runtime **不得**提供 sign 端点 |
| 全自动 | `setInterval` 状态机 | runtime job + SSE 事件；人工门暂停 |
| 批准候选 | 本地 lease | `rsi admit` CLI/人签；runtime 只读 |
| 撤销 | 本地回滚 | `rsi revoke` + stale 传播 |
| 导出 | 下载 JSON | closure/export gate + manifest |

**原则**：UI 只消费 view model；不要把浏览器变成审批/签名入口。签核仍在 CLI/人工流程。

---

## 6. 交互与视觉细节

- **密度**：桌面单屏，侧栏 230px、上下文 338px；正文 11–12px，mono 标签 7–9px；避免大卡片堆叠。整体为淡蓝底、白卡片、细蓝线；任务页使用紧凑头（工作区/任务/目标/摘要），不再用大标题占据左上角。
- **状态色**：蓝=可操作/当前；青=通过/已验证；红=人工门/失败；黄=待处理。颜色始终配文字，不只靠颜色。
- **模型设置**：顶部 model chip 打开 440px 浮动小窗（不是大页面）；模型/上下文/回复/思考/压缩在一屏内，细节折叠；滑块只选模型已声明档位，完整 Provider/Profile 配置走“高级配置”链接，细节见 `32-`。
- **折叠层级**：侧栏“最近任务”组头、RUN 阶段列表都是 `details`；组头/阶段左侧有小三角，当前阶段默认展开（可在个性化中关闭“自动展开运行中”）。
- **左下角工具**：设置与工具面板显示软件版本、个性化（自动展开、自动滚动、减少动效）、模型设置、导出、高级 Provider/Profile、重置；版本同时显示在面板与侧栏底部。
- **新建对话**：侧栏 `＋` 或顶栏 `＋` 打开对话对话框；对话即项目，切换对话不离开页面。
- **运行中指导**：自动运行中输入自然语言会进入 GUIDANCE 队列，在下一阶段应用；暂停/继续/单步/签核是显式命令；指导不改 claim/EA/gate，细节见 `33-`。
- **插件 / MCP**：composer 的 `PLUGINS` chip 打开插件面板；GitHub MCP 预设、按对话启用、工具调用逐次审批、`UNTRUSTED` 结果；本轮静态登记，细节见 `34-`。
- **消息层级**：Agent 文字先给结论，再给 artifact 卡；卡片标题是 mono 标签，正文是短句；行动按钮不超过 3 个。
- **阶段状态**：显式 `done / current / skipped / pending`；新建实验项目不会假装 S1/S2 已跑过，直接标 `skipped`，G1 仍需人工。
- **历史卡片跟随当前状态**：候选批准后，旧候选卡不再保留“批准/拒绝”按钮，改为“撤销租约”；claim 签署后，run/gate 卡显示 signed，而不是可重复点击的旧动作。
- **可检查性**：每张卡都有 artifact 类型与状态；claim 卡显示 scope/refs；run 卡显示 EA；候选卡显示 EV/lease。
- **不假精确**：静态数字不写 6 位小数；写 `412h vs 286h`、`cost −40%`，并标 SIM。
- **空态**：无项目、无候选、无证据、无会话时有明确下一步，不是空白。
- **键盘**：`⌘/Ctrl K` 命令面板；`/` 聚焦输入；`Enter` 发送、`Shift+Enter` 换行；`Esc` 关闭面板/抽屉。
- **移动端**：≤960 侧栏收为 `TASKS` 会话抽屉（工作区树 + 最近任务），`CTX` 打开右侧上下文抽屉；≤650 压缩模式与按钮；composer 常驻；无页面级横向溢出。
- **动效**：消息入场 0.22s；自动阶段用进度线；`prefers-reduced-motion` 关闭。
- **错误/失败**：停止自动不会清除对象；gate 保持 pending；回滚保留 negative result；页面不假装成功。

---

## 7. 设计依据（与本仓库既有工作的关系）

- `14-` 的证据运营工作台：三幕“体检→变更→签署”；本页把“会话”作为新的入口层，但保留证据对象与人工门。
- `21-` 的可落地系统：S0–S16、SSE、审批、Skill/Lease；本页是它的静态交互原型，不替代 runtime。
- `27-` 的创新逻辑对账：主贡献仍是 RWJT/证据闭合与测量；本页不把“对话 UI”写成新创新。
- `28-` 的全量反思：UI 必须显示臂/scope/claim 状态；本页的上下文面板与 SIM 标识延续这一点。
- `29-` 的模型接入：模型选择/思考参数只做配置与探测；本页不调用 API。
- `30-` 的百篇调研：RSEA 的 held-out keep-better、RRSI 的编辑预算、Self-Authored Verification 的 sealed audit、SkillJack 的技能供应链风险，决定了本页把“候选/租约/回滚”放在显眼位置，并避免“自动签核”。

---

## 8. 验收清单

- [x] 新建项目（研究/实验/全自动）并保留在 localStorage；
- [x] 对话发送，按模式产生 deterministic 回复；
- [x] 调研：计划 → 来源/span → gap → 假设；
- [x] 实验：协议 → 冻结 G2 → run → EA → claim 人工门；
- [x] 全自动：9 阶段推进，claim 人工门暂停；
- [x] 候选：EV1–EV4、lease、批准/拒绝/撤销；
- [x] 上下文三 tab：RUN/EVIDENCE/EVOLUTION；
- [x] 1440/1280/1024/768/390 无页面级横向溢出；
- [x] 移动端 `TASKS` 会话抽屉 + `CTX` 上下文抽屉；
- [x] 侧栏“新的任务 / 搜索 / 工作区 / 最近任务” + 最近任务折叠；RUN 阶段可展开；
- [x] 左下角设置与工具：版本、个性化、模型设置、导出/重置；
- [x] 新建对话、模型设置、工具面板都不离开当前页面；
- [x] 无 API 调用、无 console error；
- [ ] 真实模型、真实 run、真实签核（下一阶段，不在本轮）；
- [ ] 5–8 人可用性测试（未做）。

---

## 9. 代码入口

- 页面：`site/agent/index.html`
- 样式：`site/agent/agent.css`
- 状态机/交互：`site/agent/agent.js`
- 入口：主站侧栏/顶栏 “Agent 工作台”，或直接 `/agent/`
- 说明：`site/agent/README.md`

*本轮不接 API；所有状态为 SIM。真实系统仍以 runtime/CLI 的人工门与证据链为准。*
