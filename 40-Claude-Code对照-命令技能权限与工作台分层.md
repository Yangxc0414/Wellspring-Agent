# 40 · Claude Code 对照：命令、技能、子智能体与权限分层

> 对照对象：本地 `claude-code-main/`（Claude Code 官方仓库快照，含 `plugins/`、`examples/`、`mods/`、`.claude/commands/`；不是可执行源码）。
> 审计日期：2026-10-25。方法：读其命令/Agent/Skill/Hook 的 frontmatter 与示例，抽取设计模式，再回看 `apps/web` 与 `research_agent` 的真实能力。
> 原则：只借鉴结构与交互模式，不复制其代码；不把 Claude Code 的 coding-agent 能力直接等同为科研 Agent 的能力。

## 0. 结论

Claude Code 最值得借鉴的不是“终端界面”，而是**把不同层拆开**：

- **Command**：用户显式触发的动作/宏，带 `description`、`argument-hint`、`allowed-tools`、`model`；
- **Skill**：过程性知识，靠 `name + description` 渐进披露，正文只在触发时加载；
- **Agent**：有独立工具/模型/角色的子智能体，通过 Task/mention 调用；
- **Hook**：在生命周期事件上执行策略，不属于提示词；
- **Plugin**：把 commands/agents/skills/hooks/MCP 打包分发；
- **Permission**：会话级模式 + 每工具规则 + sandbox，人工门与工具审批分离。

我们的工作台此前把 Command、Skill、Action 混在同一个 `/` 菜单里，并且权限模式只覆盖了部分动作。本轮已修掉两类真问题：**命令/Skill 分层**与**只读模式越权**。但仍有明确边界：没有真实模型工具循环、没有 Hooks、没有真实 MCP transport、没有文件 diff/checkpoint、没有可恢复会话。

## 1. Claude Code 的结构证据

| 层 | 参考位置 | 关键设计 |
| --- | --- | --- |
| Commands | `.claude/commands/*.md`、`plugins/*/commands/*.md` | frontmatter 的 `description` / `argument-hint` / `allowed-tools` / `model`；用户触发，内容是指令而非说明 |
| Skills | `plugins/*/skills/*/SKILL.md` | `name` + `description` 决定触发；正文 imperative；references/examples/scripts 渐进披露 |
| Agents | `plugins/*/agents/*.md` | `name` / `description` / `tools` / `model` / `color`；独立上下文与工具集 |
| Hooks | `plugins/hookify/hooks/*`、`examples/hooks/*` | `PreToolUse` / `PostToolUse` / `Stop` 等事件；策略与提示词分离 |
| Plugins | `.claude-plugin/marketplace.json`、`plugins/README.md` | plugin manifest 统一 commands/agents/skills/hooks/MCP |
| Permissions | `examples/settings/settings-strict.json` | `permissions.ask/deny`、managed rules、sandbox 网络白名单 |
| Diff/Checkpoint | `mods/diff/README.md` | 编辑后自动开 diff、session start 基线、checkpoint、可切换比较基准 |
| Frontend design | `plugins/frontend-design/skills/frontend-design/SKILL.md` | 反模板化、先定 token/布局、克制动效、文案即界面、移动端与 reduced-motion |

这些是**设计证据**，不是效果证据；本地快照没有真实运行 Claude Code 的模型/工具链。

## 2. 我们当前的分层与真实状态

| 层 | 我们的实现 | 状态 | 差距 |
| --- | --- | --- | --- |
| Command | `domain/commandCatalog.ts` + Composer `/` 菜单 | 前端 WIRED | 仍是本地动作；未接 runtime 命令目录 |
| Skill | `domain/skillRouting.ts` + `activation` 三态 | 前端 WIRED；后端目录 only | 没有真实模型自主选择；没有 references/scripts |
| Agent | `custom_agents.py` + 设置页 `AgentManagement` | PARTIAL | 模板组批量创建已 WIRED；仍不能在会话里 `@agent` 调用 |
| Hook | 无 | ABSENT | 没有 tool lifecycle / stop hook |
| Plugin/MCP | 前端登记 + 模拟审批 | SIM | 没有 plugin manifest、stdio/HTTP transport、真实工具 |
| Permission | read-only / ask / full | PARTIAL | 只读本轮已覆盖 8 类动作；ask/full 仍无逐工具规则 |
| File | 只读浏览器 + 预览 | PARTIAL | 无编辑、diff、checkpoint、undo、全文搜索 |
| Session | localStorage 快照 | PARTIAL | 无 resume/clear/checkpoint 语义；多标签无协调 |

## 3. 本轮修掉的真问题

### 3.1 Command 与 Skill 混在一个菜单

**问题**：`/` 菜单只列 Skill；`/start`、`/run`、`/sign` 等命令只能靠记忆输入。用户无法区分“我要执行一个动作”和“我要加载一段过程知识”。

**修复**：

- 新增 `apps/web/src/domain/commandCatalog.ts`：25 个命令按 `RUN / WORK / VIEW / TOOLS` 分组，带 `description`、`hint` 与任务状态 `available` 判断；
- Composer 的 `/` 菜单先显示命令组，再显示 `SKILLS`；命令直接执行，Skill 插入 `/<skill-id> ` 以便补充检查重点；
- 新增 `/freeze`、`/eval`、`/new`、`/lineage`、`/export`、`/agents`、`/files`、`/memory`；命令按任务状态过滤，只显示当前可执行项；`/settings` 改为打开通用设置而不是默认“用量”；
- 菜单字体从 6–8px 提升到 8–9.2px，并限制最大高度；1440/390 无横向溢出。

### 3.2 只读模式可以设计/冻结/签署/提交评估

**问题**：只读模式的描述是“查看与检索”，但 `designExperiment`、`freezeProtocol`、`signClaim`、`submitEvaluation` 没有走 `denyReadOnly`；只读会话仍能改变协议、签 claim、消耗 held-out。

**修复**：四个动作都加只读门；只读现在阻断：

- 设计实验、冻结协议；
- 运行实验、启动/单步全自动；
- 签署 claim、提交 held-out 评估；
- 批准工具、批准自进化候选。

ask/full 仍不能绕过 claim/EA/closure/signature 的人工门；这只是前端策略层，真实 runtime 仍需服务端复核。

### 3.3 权限文案与真实行为不一致

AccessPicker 的提示从“人工门不受此设置影响”改为“人工门不受此设置影响；只读模式仍会阻止设计、冻结与签署”，与代码一致。

### 3.4 子智能体：从单条表单到模板组

**问题**：旧表单一次只能配置一个角色，且一个角色可以勾很多 checks；真实审稿更像“组队”，用户要反复填表，容易把多个职责塞进一个 agent。

**设计**：把“新建”拆成两层——模板组（组队意图）→ 待创建清单（可改名/移除）→ 批量创建。模板只展开为白名单 checks 组合，不引入任意 prompt 或工具；每个角色仍然保持单一职责/单一阶段为主。

- 模板：标准审稿组（覆盖+引用、假设、协议，3 个）、证据审计组（证据、闭包，2 个）、图表 provenance 组（1 个）、全流程审稿组（5 个）；
- 待创建清单支持改名、单条移除、整组移除；重名自动加序号，手改重名会在创建前拦截；
- 批量创建 runtime 在线时逐个调用 `/api/agents/custom`，部分失败保留失败项并显示原因；离线时写本地草稿并标 `LOCAL DRAFT`；
- 上限 30 个；仍只接收白名单 checks，`advisory_only=true`、`writes=[]`，创建不等于执行；
- 已创建角色支持编辑名称/用途/checks（角色固定），runtime 在线走 PATCH，离线改本地草稿；这样不用“删了重来”。

实现：`apps/web/src/domain/agentTemplates.ts`、`AgentManagement.tsx`；截图 `113–115`。

## 4. 仍然存在的问题（不应宣称“没有问题”）

1. **没有真实模型对话/工具循环**：Composer 仍是静态模板；`/research` 等命令不调用模型，也不产生真实 span。
2. **Skill 不是模型自主调用**：当前是确定性 keyword/action 路由，最多 1 个；真正接 runtime 后应由模型调用受控 `load_skill`，服务端校验白名单。
3. **Agent 不能在会话中调用**：自定义 advisory agent 只在设置页可见，未实现 `@agent` mention 或 Task 调用。
4. **Hooks 缺失**：没有 `PreToolUse/PostToolUse/Stop`，也没有“工具调用前后”的策略注入。
5. **Plugin/MCP 是登记与模拟审批**：没有真实 transport、OAuth、工具 schema 或结果 untrusted 标记。
6. **文件只读**：没有编辑、diff、checkpoint、undo；Claude Code 的 diff pane 不能直接照搬，但“变更前后对照”对科研稿件/实验配置同样有用。
7. **权限粒度仍粗**：只有会话级三模式；没有 per-tool allow/deny/ask 规则，也没有 sandbox 网络白名单。
8. **会话不可恢复**：localStorage 整包快照，没有 Claude Code 的 `/resume`、`/clear`、checkpoint 语义。
9. **静态模式 API 噪音**：runtime 离线时打开设置/文件可能产生 500 控制台记录，UI 会回退快照；这是已知 fallback，不是业务失败。
10. **卡片仍然偏大**：Skill 检查卡在消息里占空间；Claude Code 用单行 tool call + 可展开输出。科研工作台需要展示检查项，但下一步应做“摘要 + 展开”，而不是继续加卡片。

## 5. 哪些不该照搬

- **终端特有的 keybinding/diff pane**：我们的主界面是对话式工作台，不是 TUI；可以借“变更前后对照”的信息结构，不必复刻终端布局。
- **完整 plugin marketplace**：毕设阶段不需要插件市场；先把 skill/agent 的契约做真。
- **Hooks 全家桶**：没有真实工具执行前，hooks 只是空转；等 runtime 工具体系稳定后再做。
- **自动改文件/执行 shell**：科研 Agent 首先需要的是 PDF/span/claim 的可追溯，而不是 coding-agent 的写文件能力。
- **多智能体越多越好**：Claude Code 的 multi-agent 也有 token/协调成本；我们的 fan-out 应只在 S1 检索等可并行环节使用。

## 6. 对科研工作台的优先级

**P0（先做真）**

1. 真实模型对话 + 受控工具循环：模型只能提议 `SourceHit / Span / ClaimDraft`，不能直接写 Claim/EA/gate。
2. PDF/Zotero 导入 + 页码/字符 span + 原文高亮；没有这个，span-only 只是小语料演示。
3. claim → EA → closure → export 的签名/事实源修复（见 `39-` 的 P0）。
4. 文件变更/版本对照：先做“实验配置/稿件槽位的 diff”，不急着做代码编辑器。

**P1（再做顺）**

5. 在会话中调用自定义 advisory agent（`@agent` 或“请子智能体检查”），返回只读 advisory note。
6. Skill 的 references/examples 渐进披露；导入技能只做 manual。
7. 真实 runtime 命令目录：让 `/` 菜单的命令来自 `CommandRegistry`，而不是前端硬编码。
8. 会话 checkpoint/resume：至少保存“阶段边界”的快照，而不是整包 localStorage。

**不做**

- 插件市场、完整 hooks、coding-agent shell、自动改文件；
- 为了“像 Claude Code”而增加更多全局开关/面板；
- 把前端静态控制面写成已接 runtime。

## 7. 验证

- `npm run typecheck`：通过；
- `npm run build:site` / `npm run build`：通过（约 602 kB JS / 207 kB CSS，gzip ≈182/31 kB）；
- Playwright 1440/390：
  - `/` 菜单显示 `RUN / WORK / VIEW / TOOLS / SKILLS`；
  - `/help` 直接执行并返回命令列表；
  - `/` 菜单按状态筛选：空任务只显示 start/research/evidence/eval/skills/files；检索后出现 experiment；设计后出现 freeze；冻结后出现 run；
  - 只读模式 `/experiment`、`/sign` 被阻断，菜单只剩 VIEW/TOOLS/SKILLS；
  - `/freeze` 可执行并冻结协议；`/agents` 打开设置子智能体页，`/files` 打开只读文件浏览器；
  - 子智能体：标准审稿组 + 证据审计组 → 5 个待创建 → 改名 → 创建 → 列表从 2 个变为 7 个；390 模板单列无溢出；
  - 无页面横向溢出；runtime 离线时设置/文件页有预期 500 fallback，不影响 UI。
- 新截图：`111-slash-commands-1440.png`、`112-slash-commands-mobile-390.png`。

## 8. 一句话

> Claude Code 给我们的不是“终端外观”，而是**分层与契约**：命令是用户动作，Skill 是按需知识，Agent 是独立角色，Hook 是生命周期策略，Permission 是执行边界。把这些层拆对，比继续加面板更重要。
