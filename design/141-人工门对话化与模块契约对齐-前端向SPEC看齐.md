# 人工门对话化与模块契约对齐：前端向 SPEC 看齐

> 状态基线：2026-11-21。承接 136–138（演示诚实性）、139（谁有权说更好）、140（演示播放器）。
> 本文只改前端工作台（`apps/web`）；不新增后端能力、不改 seed 数字、不触碰 CLI/runtime 契约。

---

## 0. 一句话结论

对前端做了第二次"向对齐要设计"的审计，找到的最大不对齐点不在缺功能，而在**错误指向**：转录里所有人工门卡（G1/G2/S5b/G5）的主按钮都打开 claim 签署面板——一张 G1 卡让观看者去"签署 claim"，与后端"G1 收敛候选、S5b 才签 claim"的分工直接矛盾。本轮把每个门还给自己的对话框，并把模块契约（源自 SPEC）上屏。

## 1. 审计：前端 ↔ 后端模块对齐差距清单

| 后端模块/门 | 审计前的前端呈现 | 差距 | 本轮动作 |
|---|---|---|---|
| G1 候选收敛（flow g1） | 门卡主按钮 = "签署 claim"（错误指向）；无 G1 CLI 命令 | 门被冒名 | 新增 GateDialog(G1)：候选单选 + human_reason → 实时生成 `flow g1` 命令 + 决策 JSON |
| G2 协议冻结（protocol freeze） | 只有 `freezeProtocol` 追加一条消息 + 命令文本 | 有命令无对话 | GateDialog(G2)：协议摘要 + 冻结确认框 + 理由 → `protocol freeze` |
| S5b claim（run claim） | ClaimGateDialog 三路径完整 | 无 | 保持既有路由（Q0/S5b → claim 面板） |
| G5 闭合签署（closure sign） | 门卡同样错误指向 claim 面板 | 门被冒名 | GateDialog(G5)：claim/run/closure 就绪核对 + 确认 → `closure sign` |
| 九阶段 × 模块契约 | FlowDemo 有"命令/产物/义务"，但不说后端模块与硬性不变量 | 深度不足 | 每阶段新增"后端契约 · modules/xxx"块（源自 STAGE_MODULE_CONTRACTS） |
| BRIEF blockers | 只列原因，不可操作 | 看得见够不着 | 每行加动作按钮直达对应人工门对话框 / RUN 面板 |

方法论备注：这次审计的问题不是"前端没做"，而是**前端做了但指错对象**——它比缺一块面板更危险，因为它在演示时会把观看者的注意力引向错误的人工门。139 提出的"可核查"标准（DOM 实测而不是读代码）在这里再次起作用：读代码看不出这个错（`card.type === "gate"` 分支看起来很通用），点开每一张卡才看得出。

## 2. 设计：对话框收集决策，签名仍只发生在 CLI

`GateDialog` 沿用 ClaimGateDialog 立下的诚实模式，并把它推广为"对话"：

1. **门后契约块**：这个门在后端由什么保证（源自 `gateContracts.ts`，逐条注明出处模块；该文件是只读投影，禁止发明不变量）；
2. **人的决策块**：选择（G1 候选单选 / G2 冻结确认 / G5 就绪核对）+ human_reason 文本框（CLI 必填项，空理由会被 CLI 拒绝——对话框提前把这条规则翻译给用户）；
3. **实时命令块**：决策与理由实时填进 `flow g1` / `protocol freeze` / `closure sign` 命令（`gateCommands.ts` 逐字镜像 `research_agent/cli.py`）；
4. **决策记录 JSON**：勾选确认 + 非空理由后可复制（origin: browser-dialog，注明"真实生效必须执行 CLI 命令"）——它是对话的产物，不是签署的替代。

硬边界不变：对话框**不写** gates/evidence/claim，MCP/runtime 依旧没有 approve/claim/sign 端点（AGENTS.md §5/§7）；S5b 保持 ClaimGateDialog 的三路径（CLI / 导入已签产物 / 静态 DEMO 预览），本轮只修 G1/G2/G5 的指向与对话化。

## 3. 已实测

- `npm run typecheck` 通过；`test:unit` 32/32（新增 `tests/gateContracts.test.ts` 4 例：每个门 ≥3 条不变量且命令必带 `--human-reason`、命令镜像真实 CLI 入口、门卡路由映射（Q0→S5b、未知门→null）、契约表恰好覆盖九阶段无多余键）。
- 测试抓到两个真 bug 并已修：`claimSignCommand` 丢弃对话框理由（S5b lambda 未传 decision）；`gateIdForCard("S5b")` 因 `toUpperCase()` 产生 "S5B" 匹配失败。
- 浏览器实测（dev）：G1 卡→对话框→选 CAND-H1→理由→确认→命令实时含 `--idea-id CAND-H1` 与理由；G2 卡→协议五项摘要 + freeze 命令；BRIEF G5 行→"进入 G5 对话"→就绪核对（claim n/a / RUN-014 completed / closure 待人签）+ `closure sign` 命令；FlowDemo S1 展开→"后端契约 · modules/literature"三条不变量。
- `tsconfig.json` 开启 `allowImportingTsExtensions`（noEmit 前提已满足），使带运行时依赖的 domain 模块可被 node 单测直接导入——此前的单测只能覆盖叶子模块，是被测试覆盖面卡住的一小步。

## 4. 设计主张（可证伪）

1. 人工门的正确抽象是"每个门一个收集决策的对话框"，而不是"每个门一段说明文字"：决策（选择+理由）是人的输出，命令是它的编译结果——这与人签在 CLI 的边界兼容，且让"为什么要人"在 UI 上可见；
2. 门卡的路由必须由数据（`gateIdForCard`）驱动并被测试钉住，否则下一次新增门卡还会默认指向 claim 面板；
3. 模块契约上屏的可行性取决于"契约有唯一出处"：STAGE_MODULE_CONTRACTS 逐条可溯源到 AGENTS.md §5 与 SPEC，测试保证它恰好覆盖九阶段——多一条就是死数据，少一条就是假完整。

## 5. 边界与剩余差距（继承 139 §6 与 140 §5）

- 对话框产生的决策记录仍是草稿：G1 的 `--idea-file`/G2 的 `--design` 等路径占位符需人替换，本轮不做任务态→CLI 路径的自动推断（runtime 才知道真实 project 目录）；
- G1 决策记录与 `flow g1` 的 `--g1-decision` 文件格式尚未逐字段核对（现在是语义对齐，不是格式对齐）——列入下一步；
- EVIDENCE 面板尚未呈现 S1 文献台账（counts/metadata/六面向逐项核对），这是下一个最值得做的对齐增量；
- 非 S5b 的门暂无"导入已签产物"路径（G1 可导入 g1-decision.json、G2 可导入 protocol-card.json），需要先定只读校验规则再上 UI。

## 6. Changelog

- `apps/web`：新增 `domain/gateContracts.ts`（门契约 + 门卡路由 + 阶段×模块契约表）、`components/GateDialog.tsx`（G1/G2/G5 对话框）；`gateCommands.ts` 增 `g1DecisionCommand` 并让 G2/G5/S5b 命令接受对话框理由；`ArtifactCard` 门卡按 `gateIdForCard` 路由；`ContextPanel` BRIEF blockers 可操作；`FlowDemo` 阶段详情增后端契约块；store 增 `gateDialog` 状态与 open/close；App.tsx 挂载 + Escape；样式（components.css）；`tsconfig.json` 开启 `allowImportingTsExtensions`。
- 测试：`tests/gateContracts.test.ts`（4 例）并入 `test:unit`。
