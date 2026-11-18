# 127-前端 demo 与 skill 框架的系统性反思和改进

日期：2026-11-18
范围：`apps/web/src`（前端工作台）+ 对照 `research_agent/runtime`（后端真实能力）

## 0. 这次反思的方法与结论先行

不是凭印象评审：对前端按钮→子页面逻辑、skill 加载机制做了两轮独立全量扫描（App.tsx / ContextPanel 8 tab / 6 条 seed 会话 / workspaceStore 全部 action / SkillsDrawer / 命令面板），逐条给文件+行号证据，再人工复核最严重的三条，避免误判。

**总判断**：
- 前端 demo 的"演示/真实"边界总体克制（大量 DEMO / fixture / 不代签标注），**没有数据损坏级致命问题**；
- 但存在两类真实缺陷：**交互逻辑断裂**（灰按钮无解释、tab 状态串台）和**能力表述失真**（skill"加载"其实没加载、前后端 skill 清单漂移）；
- 本轮改进遵循一条原则：**不为了"看起来能跑"而绕过门禁**。G2/G5 人工门、不写 claim/EA 是核心不变量，改进只发生在"反馈与表述"层，不动门禁语义。

## 1. 发现的问题清单（按严重度）

### 严重

**S1. skill 的"加载/调用"是纯 UI 幻觉**
- 证据：`workspaceStore.ts:651` 把 `route.mode` 映射成"按需加载/手动加载"文案，`:654` 插入"已加入本轮检查"消息；`instructions` 字段全仓只出现在表单与展示（`SkillsDrawer.tsx`、`catalog.ts`），**从未进入任何 prompt 或请求**。
- 后端其实有真实执行：`runtime/app.py:820` `POST /api/skills/{skill_id}/run`（只读、带版本与 usage）；前端 `runtimeApi.ts:869 runWorkspaceSkill` / `:805 toggleRuntimeSkill` 是**死代码，无人调用**。
- 风险：演示观众以为"加载了 skill = 模型执行了它的指令"，属于过度宣称。

**S2. 前后端 skill 清单漂移**
- 前端 10 个内置（`catalog.ts:89-188`）：literature-brief / hypothesis-triage / protocol-review / **evidence-audit** / paper-slots / rsi-preflight / research-scout / experiment-manager / exploration-check / eval-integrity。
- 后端可运行仅 4 个（`app.py:822`）：literature-brief / hypothesis-triage / protocol-review / **evidence-boundary**。
- 两个问题：6 个前端 skill 后端不存在；ID 冲突（`evidence-audit` vs `evidence-boundary`）。

**S3. 手动实验链路在 demo 会话里静默卡死**
- `freezeProtocol`（`workspaceStore.ts:1964`）故意不置 `protocolFrozen=true`（G2 是 CLI-only 人工门，这是**正确的合规设计**），而 `runExperiment`（`:2002`）要求 `protocolFrozen` 才运行；按钮 `disabled={!task.protocolFrozen}`（`ContextPanel.tsx:278`）。
- 后果：4 条未预置冻结的会话里"运行 3 seeds"是灰按钮，点了无反应、也没有解释——观众误以为是 bug 或"门禁太严"。

### 中等

**M1. tab 本地状态串台**：`ContextPanel.tsx:2483-2494` 的 `flow / projects / ese` 三个 tab 漏了 `key={task.id}`（其余 5 个都有），切任务后 `ProjectExperimentInventoryPanel` 的选中项、`EseRunsPanel` 的 `selectedId` 残留。

**M2. 多数 overlay 缺 focus trap / 焦点恢复**：只有 ClaimGateDialog、PermissionDialog 实现；CommandPalette / WorkspaceFilesDialog / ModelDialog / NewTaskDialog / PluginsDrawer / SkillsDrawer 都没有（`aria-modal="true"` 却可 Tab 到背景）。

**M3. 欢迎页推荐按钮名不副实**：`WelcomeHome.tsx:233` 点击只 `fillPrompt`（填入输入框），文案像"执行动作"，实则要用户再按发送。

**M4. 静态会话的"运行真实 pipeline"错觉**：`runResearch/runExperiment/startAuto` 的按钮文案（"扩展检索/运行 3 seeds/启动全自动"）配合自动 tick 会真实逐条推进阶段，seed 又预置 RUN-014/EA-7c41 数字——观众容易当成真实执行。

**M5. `filesOpen` 未纳入 Esc / closeOverlays**：`App.tsx:93-117` 与 `workspaceStore.ts:1440` 的关闭链都漏了 filesOpen，关文件弹窗时会连带收起侧栏/上下文。

### 轻微

- `/live` 入口在静态构建不可达却仍出现在 help 文案（`workspaceStore.ts:1792`）。
- 术语堆砌无释义：ExecPort / verdict-ledger / CAPSULE / EA 等（`ContextPanel.tsx:548-632`）。
- "测试连接（静态）"仅弹 toast（`PluginsDrawer.tsx:217`）。

## 2. 本轮已落地的改进

只做"反馈与表述"层、零门禁语义变更的低风险项：

| 问题 | 改动 | 文件 |
|---|---|---|
| S3 灰按钮无解释 | 按钮加 `title` 说明 G2 是人工门；`runExperiment` 在静态构建的提示改为明确指路（用全自动推进 / 切到完整闭环会话） | `ContextPanel.tsx`、`workspaceStore.ts` |
| M1 tab 串台 | `flow / projects / ese` 三处补 `key={task.id}` | `ContextPanel.tsx` |
| S1 skill 加载幻觉 | SkillsDrawer 顶部新增诚实说明：点击"调用"=插入检查卡，**不会把 instructions 喂给模型**；真实执行走 CLI 或 `/api/skills/{id}/run` | `SkillsDrawer.tsx`、`components.css` |
| M3 欢迎按钮 | title 明确"点击填入输入框，再按发送（不会自动执行）" | `WelcomeHome.tsx` |

验证：`npm run typecheck` 通过；`test_claim_preview_demo` 等相关测试与完整 CI hard gate 全过（详见提交记录）。

## 3. 建议但本轮不改的项（附理由）

- **接通 `/api/skills/{id}/run`（S1/S2 的根治）**：需要把静态 demo 与真实 runtime 两套体验分开设计，属于产品化工作量，不是 bug 修复。且静态 Pages 构建本就没有后端，接通后仍要在产品工作台生效——留作独立任务。
- **统一前后端 skill 清单（S2）**：涉及改 ID（`evidence-audit` → `evidence-boundary`）与 10→4 的能力收敛，会影响现有演示脚本与文档，需人工确认后单独做。
- **overlay focus trap（M2）**：体验重要但无演示阻断；建议抽公共 `useModalFocus` hook 一次性修，避免逐个改造成新风险。
- **静态会话按钮加 DEMO 角标（M4）**：卡片的免责声明已存在，按钮层再加角标收益边际；且要改 5+ 个按钮，留待统一设计。

## 4. 反思：为什么这些问题会积累

1. **"静态 demo"与"产品工作台"共用一套组件**：许多表述要在两种模式下都成立，导致文案模糊（skill"加载"、pipeline"运行"）。根因不是代码，是**两种模式的语义边界没有在数据层显式区分**，只靠 `__STATIC_ONLY__` 在个别分支打补丁。
2. **门禁正确 ≠ 体验正确**：G2/G5 不绕过是对的，但"静默 disabled + 干巴巴 notify"把正确门禁表达成了疑似 bug。门禁的严格应该配同等清晰的引导。
3. **前后端清单靠人肉同步**：前端内置 skill 与 runtime 可运行 skill 是两个独立常量，没有一致性测试。这正是项目一直强调的"规格是源、代码是实现"的反面案例——应给 skill 清单加一条 parity 测试。

## 5. 下一步优先级

1. 给 skill 清单加前后端 parity 测试，防止继续漂移（最高价值、成本最低的根治起点）。
2. 抽 `useModalFocus` 统一修 overlay 可访问性。
3. 独立设计"静态 demo vs 产品工作台"的 skill 体验分层，再决定是否接通 run 端点。
