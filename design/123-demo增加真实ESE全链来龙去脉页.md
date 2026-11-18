# 123-demo 增加「真实 ESE 全链来龙去脉」页

> 状态基线：2026-11-18。触发：用户要求 demo 上能体现"真实 ESE 全链运行"的具体来龙去脉，而不是只有一句结果。
> 本轮交付：`demo/run/index.html`（生成式），逐阶段展示输入、动作、产物、门禁与断点。

---

## 1. 之前缺什么

- 首页有"最近一次真实运行"面板：只有阶段状态与门禁；
- `/demo/` 回放页：输入 → 输出摘要，但没有"每一步的产物从哪来、喂给谁"；
- 读者无法回答："这条 37.5% 的结论/这份稿件到底经过了哪些文件与命令？"

## 2. 新页面：来龙去脉（demo/run/）

由 `scripts/build_ese_chain_page.py` 读取一次真实运行生成（20 KB），包含：

1. **一图链路**：问题 → QueryPlan → 检索/全文 → span+coverage → S1b 综合 → 候选 → 设计+方法缺口 → 图 → 稿件 → 写作包 → 创新评审 → 初稿 → 评审 → 审计 → 门禁；
2. **阶段表**：每阶段 输入 / 动作 / 输出产物 / 状态（warning 数）；
3. **输入与覆盖**：coverage 读数、Q0、来源标题清单；
4. **综合与候选**：主题、3 条候选的 hypothesis/falsification/lens/refs；
5. **S4 设计与方法缺口**：字段摘要 + repository-mining 缺失字段（advisory）；
6. **图与稿件**：figure manifest 摘要、writer_mode、sections、模型草稿摘录；
7. **创新评审**：状态、轮次、gaps、最终候选；
8. **初稿、评审与审计**：评审 scores/accepted/revisions、审计 citations/汉字/claim_status/submission_ready；
9. **产物清单**：12 个关键文件的路径、大小、sha256 前 12 位（本机指纹）；
10. **门禁与边界**：G1/G2/G3/G5 仍人签；无 Claim/EA/签名；模型评审≠同行评审；本机产物不入发布包。

页面带 `data-dl-page="demo"`、`data-demo-chain="<run id>"`，沿用共享 legibility；回放页与首页卡片已链到该页。

## 3. 构建与校验

- `build-site.mjs` 递归复制 `demo/` 树 → `site/demo/run/index.html`；
- `check-site` 把该页加入 legibility 清单：**10 demo pages legible**；
- `tests/test_demo_page.py` 新增 2 项：页面含阶段名/来龙去脉/REAL RUN 与源副本一致；回放页链到 `run/`。

## 4. 边界与仍未做

1. 页面里的路径/哈希来自**本机 runtime_data**，不随发布包分发；读者看到的是"这次运行在本机的指纹"，不是可下载产物；
2. 阶段表中的命令/动作是归纳描述，不是从日志逐条抽取（日志中有更细的调用）；
3. frontier 版本（24 篇/6 候选）还没有对应的"来龙去脉"页，目前只链到回放摘要；可复用同一脚本生成第二页。

---

## 5. 验收

| 项 | 结果 |
| --- | --- |
| 生成 | `python scripts/build_ese_chain_page.py` → 20 KB 页面 |
| 站点 | check-site ok（10 demo pages legible） |
| 测试 | tests.test_demo_page 7 项 OK（新增 2 项） |
| 链接 | 首页卡片 + 回放页均链到 `demo/run/` |
| 发布 | release 同步见提交；CI 由远端验证 |
