# 断言指向清晰化：每条 claim 都带"主张什么 + 在什么范围内成立"

> 状态基线：2026-11-21。承接 141（人工门对话化）、144（显示细节）、145（人的表述上屏）、146（网页内签署）。
> 本文只改前端显示（`apps/web`）；claim 内容逐字来自会话证据行，不新增任何断言。

---

## 0. 一句话结论

"CLAIM" 在前端出现在至少五处（KPI、证据链节点、门卡、REGISTRY、签署对话框），但多数只给状态词（none / 待签 / signed）而不给**主张内容与适用范围**——观看者无法回答"这条 claim 到底是对什么的 claim"。本轮在两块高频面板补齐：BRIEF 新增 **CLAIMS · 断言** 段，证据链「断言」节点下直接显示**主张全文 + 范围**。至此每条 claim 在出现的地方都能自答："在 click/requests/httpx 合并样本上…（范围：三仓库便利样本 · 启发式标签 · 不可外推）"。

## 1. 差距与补齐映射

| 出现处 | 补齐前 | 补齐后 |
|---|---|---|
| BRIEF KPI | `none CLAIM`——无任何主张信息 | KPI 保持，其下新增 **CLAIMS · 断言** 段：每条 claim 的 id + 状态徽章（待人工签署/委托签/DEMO）+ 主张全文 + `范围：scope` + `依据：RUN/EA` + 签署来源说明 |
| EVIDENCE 证据链「断言」节点 | 只有 NOT CREATED / 待签 状态词 | 节点正下方新增主张卡：`断言 {id} · {badge}` + 全文 + 范围 |
| EVIDENCE REGISTRY | 已有全文 + scope + refs（先前实现） | 不动 |
| 门卡 / 签署对话框 | 144/141 已带 reason 与 claim 文案 | 不动 |

空态同样说明"claim 是什么"：无 claim 的会话显示"claim = 一句可检验的话 + 数值断言 + 它成立的范围（scope）；位置在证据链「断言」段"。

## 2. 设计主张（可证伪）

1. claim 的最小完整呈现是三元组：**主张句 + scope + 依据（RUN/EA）**——只显示状态词的 claim 展示等于没展示，因为观看者无法判断"这句断言在我的演示里指什么"；
2. 状态徽章永远携带来源限定词（待人工签署 / 委托签 · 非人签 / DEMO），主张句永远携带 scope——两者合起来才能防止" Iris 0.956"被听成科学结论。

## 3. 已实测

- `npm run typecheck` 通过；`test:unit` 41/41；`build` + `build:site` + `build-site.mjs` 通过。
- 静态构建实测：ESE 会话 BRIEF 显示 "CLM-ESE-01 · 待人工签署"+ 主张全文 + "范围：三仓库便利样本 · 启发式标签 · 不可外推" + "依据：RUN-…/EA-65d32e114229"；证据链下方主张卡同文；教学会话空态文案说明 claim 定义。
- `docs_audit` / `repo_hygiene` / 发行副本 `--prune` 同步 + 完整性测试通过。

## 4. Changelog

- `apps/web`：`ContextPanel.tsx` BRIEF 增 CLAIMS · 断言 段、EVIDENCE 链下增主张卡；`components.css` 增 chain-claim / brief-claim 样式。
