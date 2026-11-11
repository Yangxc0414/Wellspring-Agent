# 70 · Stage1 预筛的落位与边界

> 2026-11-08。参考设计：「先做标题与摘要级的 Stage1 预筛，压缩候选集合，再进行候选评分；
> 用低成本方式快速过滤掉大量不相关论文」。本文先给结合本项目的设计判断，再记实际落地。

## 1. 这个参考点接在哪一环

上一轮补完信息源层后，链路变成：

```
Stage0 候选发现 → [Stage1 预筛 + 排序] → 下载公开全文 → 本地解析 span → S1 覆盖判定 → S2 → G1 人签
   clue-only         本轮补这里              已有                已有            已有
```

`paper_discovery` 的三路汇聚会带回大量「只是热门/只是同领域边缘」的条目。若不预筛，
低成本环节省下的钱会在**下载与解析**上原样花回去。所以参考设计在咱们项目里是成立的，
而且位置很明确：**只能放在信息源层与证据层之间**，不能进 S1。

## 2. 五条设计判断

1. **预筛不进 S1，否则破坏 span-only**。S1 的输入必须是全文；摘要进 S1 会被误当可引用证据。
   本项目已有硬证据：`--source openalex` 只给摘要 → `full_text()` 恒 None → 0 span → Q0 blocked。
   因此 Stage1 是一个独立的候选闸门。
2. **摘要是「过滤输入」，不是「证据输出」**。上一轮 `paper_discovery` 故意不存摘要，与
   「标题+摘要级预筛」形成张力。解法不是把摘要塞回候选，而是让预筛接受**独立的
   `abstracts` 映射**，只在内存里做词法匹配；输出不回显摘要、不落盘、不产 span。
   「用摘要排除」与「用摘要支撑结论」是两件事，必须分开。
3. **评分只能是排序信号，不能变成判据**。项目里 `conference_fetcher._topic_score` 的
   词法命中、`fixture_retriever._score` / `local_document_retriever._score` 的检索排序都是
   确定性排序信号，可以沿用；但 `innovation_review.py:627` 的模型 1–10 自评分在
   `single_author` 下不是独立证据，是**反面教材**。所以 Stage2 分数恒标
   `ranking_signal_only=true`，只决定「先下载哪篇」，不决定新颖度、质量或门禁。
4. **拒绝必须带可核对理由**。本项目相对期刊 skills 库的优势是「不变量从文字纪律变成代码拒绝」；
   一个静默丢掉候选的黑箱过滤会破坏这一点。每条拒绝都写
   `missing_title` / `no_query_term` / `excluded_term` 与命中词表。
5. **压缩必须能真的减少下载量**。预筛报告附 `literature fetch` → `literature run --source local`
   的可照抄链路；它压缩的是「待下载集合」，不是展示用的列表。这与上一轮的
   `--adaptive-retrieval` 回路互补：预筛管**入口**，自适应回路管**S1 覆盖收敛**。

## 3. 与现有机制的对照

| 机制 | 做什么 | 为什么不能直接拿来当 Stage1 |
| --- | --- | --- |
| `conference_fetcher._topic_score` | 标题+摘要对硬编码 `TOPIC_TERMS` 计数 | 词表写死、只服务会议语料，不接受任意 query |
| `fixture/local_retriever._score` | 对**已解析全文**排序 | 作用在 S1 内部，输入是文档不是候选线索 |
| `idea_review` 词法预审 / `innovation_review` 1–10 分 | advisory / 模型自评 | advisory 不阻断，模型自评不是独立证据 |
| `literature synthesize` 主题矩阵 | 全文 span 的共现综合 | 需要 span，属于证据层之后 |

## 4. 本轮落地（规格先行，`literature` 0.11.0 → 0.12.0）

- `modules/literature/SPEC.md`：Contract 新增「Stage1 候选预筛与评分」条款 —— 落位、摘要边界、
  排序信号定位、拒绝理由、不改 Q0/S1。
- 新增 `research_agent/prescreen.py`（**纯函数，无 I/O、无网络、无模型**）：
  - `query_terms()` 中英文切词；`stage1_filter()` 结构 + 词法命中硬过滤，每条拒绝带 reason；
  - `rank_candidates()` 可解释加权（`title_hits×3 + abstract_hits + 多来源 + 有 PDF`），
    `rank_signals` 逐项可核，**绝不增删 kept**；
  - `PrescreenReport` 给 `input→kept` 压缩比、`by_reason`、`score_range`、
    `abstracts_used_in_memory_only`、边界声明与后续可照抄命令；
  - `_public_row()` 显式剔除 `abstract/summary/full_text/spans/text` 等证据类字段。
- CLI `literature prescreen`（`--input` / `--query` / `--abstracts` / `--min-hits` /
  `--exclude-terms` / `--output`）。
- `tests/test_prescreen.py` 13 例全离线；`runtime_data/probe-prescreen-20261108.py` 串起
  Stage0→Stage1→Stage2；`integrations/workbuddy/SKILL.md` 补一节。

## 5. 离线实测

```
Stage0 discovery : 5 unique candidates from {arxiv:2, hf_daily:3, hf_trending:2}
Stage1 prescreen : 5 -> 3 kept (compression 0.4)
  rejects        : {no_query_term: 1, excluded_term: 1}
  abstracts used : 1 (in memory only)  -> 救回 1 条标题不相关但摘要相关的候选
Stage2 ranking   : score_range [3, 8]，ranking_signal_only
  abstract echoed: False
```

CLI 端到端（临时 JSON）：`kept 1 / rejected 1 / compression 0.5 / abstract_echoed False`。

## 6. 边界（不粉饰）

- **不是语义筛选**：词法命中会漏掉同义改写、也会放进词面相关但实质无关的条目；它是低成本漏斗，
  不是相关性模型。真要语义判断需模型路径，那就不再是「低成本」。
- **分数不是质量**：`ranking_signal_only=true`，不得用于 novelty、研究质量评分或放行门禁。
- **通过预筛 ≠ 证据资格**：仍是 `clue_only=true / span_eligible=false`；必须下载全文并用
  `--source local` 解析成 span。
- 不联网、不用模型、不改 Q0/G1/G2/G3/G5、不改 S1 默认行为、不写 Claim/EA/gate/signature；
  MCP 工具表未新增对应工具（契约变化，未做）。
- 摘要由调用方提供；预筛**不会**自己去抓摘要，也不缓存。

## 7. 验证

新增 13 例 OK；护栏与全量判定由 `record_test_verdict.py` 重绑，结果见
`runtime_data/test-verdict.json`。判定指纹只覆盖 `research_agent/**/*.py`。
新增 CLI 子命令后必须同步 `workspace export`、`build_release.py --prune`
与 **`python -m research_agent plugin export`**（上一轮踩过的坑）。
