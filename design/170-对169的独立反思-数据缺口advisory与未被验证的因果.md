# 对 design/169 的独立反思：数据缺口、advisory 衰减，以及一句 UI 不该替人下的结论

**状态基线（2026-11-22）**：承接 design/169。本文**只修正判断与口径，不改代码、不改注册表、
不改执行器、不改门禁**。design/169 作为历史保留；其中三处事实错误在首段标注"已被本文取代"。
文中每条反驳都带文件与字段/行号证据，凡我没有实际跑通或核实的，明确写"待裁决"。

**为什么要有这一轮**：169 落地后我自己复述它的设计，越讲越顺——这本身就是危险信号。于是请了一个
没有参与实现的独立评审，只给代码路径、不问我的结论。它推翻了我的三条判断，其中两条是我写进
文档的"已验证事实"。把这次推翻过程写下来，比把 169 的成功面再讲一遍更有价值。

---

## 1. 最严重：我把"注册表的数据缺口"讲成了"方法学事实"

### 1.1 证据

| 事实 | 证据 |
|---|---|
| 组合接线**走了**写作槽位：`slot_map.写作 = ["S8-S12"]` | `registry.json` 两个 composition 的 slot_map |
| 但 `repository-mining.fit_stages = [S1,S4,S5,S5b]`，**不含 S8-S12** | `registry.json` 方法对象 |
| `controlled-experiment.fit_stages` **不含 S1**，而 `slot_map.证据` 含 S1 | `registry.json` 方法对象 |
| `stagePlanFor` 用 `fit.has(slot)` 过滤：组合走了但方法未 fit 的槽位被静默丢弃 | `methodModel.ts:390-397` |
| 被丢弃的槽位在会话里出现时，落到③轨并渲染为"本方法未声明" | `stagePlan.ts:220-226`、`MethodPlanFlow.tsx:269,275` |

更直接的自我反证：`repository-mining.reporting_sections` **已经声明了六个报告章节**
（抽样框与筛选、时间窗与切分、去重与标签、许可与伦理、抽取管线与快照、效度威胁）。
注册表自己就承认这个方法有写作产出，只是 `fit_stages` 没写上。所以面板上那句
「S8–S12 本方法未声明」的正确读法是「**这份注册表的 fit_stages 漏了**」，而不是
「仓库挖掘研究不写论文」。

### 1.2 错在哪里

`fit_stages` 的语义是"方法在哪些阶段有方法论约束"，它从来不是"这个方法允许存在的阶段全集"。
我把它当成后者来用，于是：

- 数据里没写 → 面板说"方法没声明" → 读者读成"方法不需要"；
- 而我在 169 §7 可证伪主张 1 里**已经写明了**"补上 S8-S12 面板就会多一个节点"——
  我知道那是数据缺口，却让 UI 用方法边界的语气说话。

这是把"我们还没建模"包装成"领域就是如此"，与项目一直警戒的"把未实现写成已支持"是同一类错误，
只不过这次发生在展示层。

### 1.3 修正方向（尚未执行）

1. **先裁决数据，再改文案**：`repository-mining` 补 `S8-S12` 及其 `stage_tasks`（内容可从它自己的
   `reporting_sections` 逐字推导，不需要发明）；`controlled-experiment` 是否应含 S1 需人判定——
   受控实验当然要做文献，但 S1 是否属于"该方法的方法论约束"是另一个问题。
2. **改测试期望**：`stagePlan.test.ts:90-93` 把 `mining.extras = [S2–S3,S6,S8–S12]` 固化为期望，
   数据补齐后这条会红——那是测试在保护 bug。必须先改测试再改数据，顺序反过来会让修数据看起来像回归。
3. **UI 增加区分**：把"注册表未声明（数据缺口）"与"方法学上不适用"分开措辞。在前者未修完之前，
   面板至少不能让读者误以为是后者。

---

## 2. 同样严重：UI 替人下了一个未被验证的因果结论

`MethodPlanFlow.tsx:200` 写着：

> 组合接线决定的是这条方法应走的顺序；当前执行器仍按固定阶段跑，所以这条会话没有按计划剪裁。

前半句可证（`pipeline.py` 只在未覆盖阶段发 `stage_skip` 后继续执行）。**后半句是把两个不同现象
强行归因为一个原因**：

- `stage_skip` 不改顺序，它解释的是③轨为什么有 extras；
- ESE 会话的 S1 在 S4 之前、S2–S3 在 S4 之前，顺序来自种子消息的人工叙事（`seed.ts` 的 stage 标签），
  与执行器是否跳过阶段无关。

而 169 §1.1 明明已经把矛盾列为**两种待人类裁决的读法**：

- 读法 A：挖掘研究是先有断言再预注册分析 → 方法绑定该改；
- 读法 B：绑定正确，是叙事按执行器固定链写的 → 属于执行层待改。

文档说"判定权在人"，UI 却直接给了 B 作为因果。这是会在组会/答辩上被追问且**无法辩护**的一句话——
因为拿不出证据证明这条会话的顺序是执行器造成的。

**修正方向**：警示框只陈述差异（计划 X / 会话 Y / 首处分歧位置），不陈述原因；把 A/B 两种读法作为
"待裁决"并列展示，或至少不在 UI 里选边。这条不需要改任何数据或后端，纯文案修正，优先级最高。

---

## 3. advisory 在展示层被升格为"既定事实"

### 3.1 证据链

- `pipeline.py:293-309`：`--method auto` 产出 `method_selection`，含三态 `status`、`candidates`、
  `needs_human: True`、`boundary: "advisory selection; no gate reads it"`。
- `pipeline.py:301`：即便 `status=ok`，也只是把 `proposed` 设为 `resolved_method_id`，仍是人确认前的建议。
- `pipeline.py:322` / `method_registry.py:330`：`composition_plan.method` 写的就是这个值。
- `runtimeSnapshot.ts:202-207` 的 `runtimeMethodId` **只读 method，丢弃 status 与 needs_human**。
- `FlowDemo.tsx:213` 的 banner 于是写「由**这条任务声明的研究方法**决定」——自动推荐被说成声明。

### 3.2 一个反讽的失败模式

`status=insufficient/ambiguous` → `proposed=None` → `resolved_method_id=""`（`pipeline.py:301`）
→ 无 `composition_plan` → 前端读不到 method → 面板退回无方法的 SESSION PATH。
**推荐越不确定，方法信息反而越彻底地消失**。168 辛苦做的"三态拒答"，在 RESEARCH FLOW 上
变成了"什么都不显示"，既没有"信号不足"的提示，也没有"待确认"的标记。

### 3.3 还有一条不可达的回退

`runtimeSnapshot.ts:205-206` 读 `method_selection.proposed` 作为回退，但要走到它，需要
"有 proposed 却没有 composition_plan"的产物；当前 pipeline 在 proposed 非空时必定写 composition_plan，
proposed 为空时两者都没有。所以这条分支在当前实现下不可达。169 §4.1 说"两处都读，谁也不猜"，
代码层面是广告。

### 3.4 修正方向

- `MethodFlow` 携带 `selectionStatus` 与 `needsHuman`（从 `method_selection` 读，不丢字段）。
- 面板把「任务声明的方法」与「自动推荐 · 待人确认」分开措辞；后者必须显示三态和 needs_human。
- 三态为 insufficient/ambiguous 时，不退回"无方法"的沉默，而是显示"推荐未采纳：信号不足/有并列"。
- 删掉不可达的 proposed 回退分支，或写测试证明它在某种真实产物下可达。

**原则**：advisory 必须在每一层保持 advisory 口径。CLI 里诚实、UI 里变成决定，等于没有 advisory。

---

## 4. 中等问题：治理固定是前端重新分类，且未来会双轨重复

- `stagePlan.ts:33` 硬编码 `GOVERNANCE_STAGES = {"S13-S16","META"}`。
- 但注册表**已经**把 S13-S16 声明为组合中"闭包"元素的槽位（`slot_map.闭包 = ["S13-S16"]`）。
  它不是注册表外的新概念，是前端又做了一次语义分类。
- 具体冲突：若将来某方法把 S13-S16 写进 `fit_stages`（`method_registry.py:283-287` 的校验允许），
  `stagePlanFor` 会把它放进①轨；而 `buildMethodFlow` 的 governance 分支在 `plannedSlots` 检查**之前**
  就 continue，于是同一阶段会**同时出现在①轨和②轨**。
- `stagePlan.ts:212` 还给 META 行硬写 `element: "经验"`，而"经验"并不在任何 slot_map 里——
  面板写出了一个注册表不存在的元素名。

**修正方向（二选一）**：把治理槽位作为显式字段写进注册表（L3 语义数据化，前端只读），
或把②轨改名为"本次会话的治理事实"并加去重，不再声称它是方法模型的分类。

---

## 5. 中等问题：uncovered 死代码，以及 design/169 里两处站不住的"可证伪主张"

### 5.1 uncovered

`method_registry.py:283-287` 要求每个 `fit_stage` 都在组合的 `slot_map` 里；当前两个 composition 的
slot_map 键全部接在 wiring 里。所以 `stagePlanFor` 的 `uncovered` 在当前数据下**永远为空**。
169 称它是"诚实的扩展缝"——严格说它只是"当前数据不可达的缝"：`validate` 并没有检查
`slot_map` 的键是否都在 `wiring` 里，将来新增一个映射却漏接 wiring 时它才会出现。

保留它没有问题，但"当前十个方法都没有这种槽位（有单测断言）"被写成扩展能力，措辞过头。

### 5.2 可证伪主张 3 是假的

169 §7 写：

> 若某方法的 `stage_tasks` 缺一个槽位，注册表 fail-closed 校验会先红（`stage_tasks` 必须覆盖 fit_stages）。

实际 `method_registry.py:157-159` 只做**单向**检查：`stage_tasks` 的键必须在 `fit_stages` 内。
删掉某方法的 `stage_tasks.S4`，validate 照常通过，`stagePlanFor` 产出空 task，
只有 `apps/web/tests/stagePlan.test.ts:63-65` 会红。**保护来自前端单测，不是注册表 fail-closed。**
把未验证的防线写成已验证，是这轮最不该出现在"可证伪主张"章节里的错误。

已在 design/169 首段标注该条被本文取代。

---

## 6. 中等问题：测试跟随代码，把缺陷固化为期望

- 新增 9 个 `stagePlan.test.ts` 全部断言投影结构（精确 slot 数组、extras、governance、分歧下标），
  **没有一个验证方法学正确性**（验证式是否真的避免 HARKing、fit_stages 是否完整、advisory 是否保留）。
- `:90-93` 把数据缺口写进期望，修数据反而红——测试在保护 bug。
- 上一轮我顺手改的 3 个 HEAD 红断言里，两条要分开看：
  - ESE 标签那条**是收紧**：新断言同时检查 `short: "闭环·待签"`，而侧栏渲染的正是 `short`
    （`Sidebar.tsx:140-142`），约束比原来更贴实际。
  - `contextTab` 那条**确实降约束**：新断言把整个表达式折叠后硬编码，注释仍称"行为未变"，
    但钉住的是"任何带 stage 标签的任务强制进入 flow"，与原注释"explicit tab choice must survive"
    冲突。把意图改成当前字符串，等于放弃对原意图的检验。169 §7 说"前两条是漂移、保留原意"，
    这一条说得不准。

**原则**：测试应该钉住意图。代码与意图不符时，要么改代码，要么**显式声明意图已变更**；
默默改断言是最容易的一种自欺。

---

## 7. 低优先级：方法差异没有并置，组会汇报靠记忆拼接

169 §8 已把"同一转录在两种方法下并排"列为中优先级下一步，说明我当时看到了。但 169 §3 又写
"两条会话放在一起演示，方法差异和实现差距同时可见"——实际并不存在并置视图，
`MethodPlanFlow` 一次只渲染一个 flow，切换靠侧栏手动完成。①轨的方法差异被分散在不同会话的
时间轴上，观众要在脑子里拼。这是已知但延后的展示缺口，不是盲点，但文案不该提前宣称效果。

---

## 8. 认知模式：这轮真正值得沉淀的东西

1. **数据现状 ≠ 领域真相**。`fit_stages` 从"方法约束适用的阶段"被我悄悄用成"方法允许存在的阶段全集"。
   凡是面板出现"未声明"，先问是"领域不需要"还是"我们没写"。
2. **advisory 会沿层衰减**。管道里 `needs_human=true`，到 UI 就剩一个方法名。
   每一层都要显式携带口径字段，否则越往上越像决定。
3. **存在约束 ≠ 唯一原因**。执行器确实全阶段执行，但不能用它解释所有顺序差异。
   两个现象同时为真，不代表一个导致另一个。
4. **测试钉结构不钉语义，就会把 bug 期望化**。当"修数据导致测试红"时，先怀疑测试。
5. **历史文档不能当现状声明**。"可证伪主张"必须真的去证伪；没验证就写"fail-closed 会先红"，
   比不写更糟，因为它会让后来者停止检查。

这五条比三轨道的 UI 结构更可迁移——下次设计任何"把数据投影成界面"的功能，都应该先过一遍。

---

## 9. 最小修正清单（尚未执行）

| 优先级 | 动作 | 前置条件 |
|---|---|---|
| 1 | 删掉 UI 里"执行器固定链导致顺序差异"的因果结论，改为只陈述差异 + A/B 待裁决 | 无，纯文案 |
| 2 | `MethodFlow` 携带 `selectionStatus` / `needsHuman`，面板区分"声明"与"自动推荐·待确认"；三态不足时显示拒答而不是沉默 | 无，前端增量 |
| 3 | 数据裁决：`repository-mining` 补 S8-S12；`controlled-experiment` 是否补 S1 由人定 | 需改注册表数据 + SPEC Changelog + 同步导出 |
| 4 | 先改 `stagePlan.test.ts` 的 extras 期望，再改数据；补一条"fit 必须有 stage_task"的注册表 fail-closed 校验（若确认需要） | 依赖 3 |
| 5 | 治理槽位显式数据化，或②轨去重并改名为"会话治理事实" | 设计选择 |
| 6 | 删掉 `runtimeSnapshot.ts:205-206` 不可达分支；修正 169 §7 可证伪主张 3 的措辞（本文已取代） | 无 |

**本文不改代码**。第 3 项是数据/契约变化，按 AGENTS.md 需先改 `modules/method-registry/SPEC.md`
并要人工确认；第 1、2 项可以随时落地。等用户确认裁决方向后再进入下一轮实现。

---

## 10. 验证方式

本文的证据来自逐条读取下列文件，未做新的实现或测试：

- `research_agent/method_registry.py:157-159`（stage_tasks 单向校验）、`:283-287`（fit 必须在 slot_map）
- `research_agent/pipeline.py:293-309`（method_selection 三态 + needs_human）、`:301`、`:322`
- `modules/method-registry/registry.json`（两组合 slot_map、十方法 fit_stages、repository-mining.reporting_sections）
- `apps/web/src/domain/methodModel.ts:390-397`（fit 过滤）
- `apps/web/src/domain/stagePlan.ts:33,96,204,212,220-226`（治理硬编码、uncovered、governance 分支）
- `apps/web/src/domain/runtimeSnapshot.ts:202-207`（丢状态 + 不可达回退）
- `apps/web/src/components/MethodPlanFlow.tsx:200,269,275`（因果文案、计划外标签）
- `apps/web/src/components/FlowDemo.tsx:213`（"任务声明的方法"措辞）
- `apps/web/tests/stagePlan.test.ts:63-65,90-93`（测试固化结构）
- 独立评审（只读、未参与实现）的逐条反驳与行号证据
