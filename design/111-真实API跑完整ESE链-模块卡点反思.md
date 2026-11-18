# 111-用真实 API 跑完整 ESE 链：到哪一步、各模块设计哪里卡住

> 状态基线：2026-11-18。用户要求：接入 API，按 ESE 方向把"文献调研 → 假设生成 → 直到结束"完整跑一遍，并反思各模块设计。
> 本轮实际执行：pipeline S0–S16（真实 API）→ writing pack → innovation review → manuscript draft → writing audit。
> 结果：**核心链跑通，门按设计停住；innovation→manuscript 段暴露一个真实的模块耦合缺陷**。

---

## 1. 实际跑了什么（命令与产物）

```bash
# S0–S16，真实 SE 语料 + 真实模型（planner/idea/experiment/writer/judge）
python -m research_agent pipeline run \
  --topic "Do bug-fix commits in Python projects touch tests more often than feature commits, and does the difference survive project stratification?" \
  --language en --venue en_conference \
  --corpus-dir runtime_data/se-corpus/pdfs --max-sources 8 \
  --idea-model deepseek-v41 --experiment-model deepseek-v41 --writer deepseek-v41 \
  --ese-method repository-mining \
  --output-dir runtime_data/ese-fullrun-20261118

# 写作包 + 创新评审 + 中文初稿 + 评审 + 成稿审计（在 ESE run 上）
python -m research_agent writing pack --project runtime_data/ese-fullrun-project --run-id RUN-ESE-01
python -m research_agent innovation review --project ... --run-id RUN-ESE-01 --rounds 1
python -m research_agent manuscript draft --project ... --run-id RUN-ESE-01 --output .../drafts/review.md
python -m research_agent writing audit --project ... --run-id RUN-ESE-01 --draft .../paper.md
```

---

## 2. 各阶段真实状态

| 阶段 | 状态 | 关键读数 |
| --- | --- | --- |
| S1 文献 | ok | 8 篇全文、6198 span、coverage=saturated、Q0 pass |
| S1b 综合 | synthesized | 5 个主题；cross-source 候选 3 条 |
| S2–S3 假设 | candidates_need_human | 3 条候选（mechanism / boundary / measurement），各带 2–3 个证据 ref；12 条警告 |
| S4 设计 | needs_human | 模型给出 hypothesis/baseline/metric/controls；8 条警告，其中两条是真缺陷：metric 是句子、budget 不可测 |
| S6 图 | schematic_ready | 示意图，不绑结果 |
| S8 稿件 | needs_evidence | writer_mode=model，5 节模型写作，Results 保持 pending；6 条警告 |
| G1/G2 | needs_human | 设计需人签 |
| G3/G5 | blocked | 论文契约未定稿 / 无 EA/closure |
| 写作包 | ok（PACK=0） | 8 来源 + span 证据包 |
| 创新评审 | **失败** | "at least 3 valid ..."：候选的 experiment_plan 与 search-study 执行器不兼容 |
| 中文初稿 | **失败** | "innovation review is required before writing"（上游未产出） |
| 成稿审计 | blocked | article_type=review；draft 是英文 paper.md；citation_count=0、claim missing |

---

## 3. 模块设计反思（按真实卡点排序）

### 3.1 innovation ← idea: experiment_plan 只有一种 schema（真缺陷）

- 现象：3 条候选都带 experiment_plan，但 ESE 研究计划是 repository-mining/commit CSV；创新评审要求 plan 映射到 search-study 的因子/水平，未知因子直接判无效，最终不足 3 条有效候选。
- 设计问题：S2 的 plan schema 与 S5 的唯一执行器（search_factorial）绑死；ESE 方法没有自己的 plan 表示。
- 建议：plan 改为"方法 + 协议字段"的联合类型（method=search_factorial | repository-mining | ...），innovation 只检查 plan 是否和所选方法匹配，不强制 search-study 因子。

### 3.2 S4 design: 度量/预算形状仍不合格（老问题）

- metric="Difference in the proportion ..."、budget="No budget information ..."——与 86/104 的观察一致。
- 设计问题：形状检查只产 warning，模型不受约束；R1/R2 的修法没有进 pipeline 默认路径。
- 建议：S4 生成时把 method card 的 required fields 作为 payload 提示（已部分做到），并默认启用一次形状修复（R2），仍标 needs_human。

### 3.3 S8 paper writer: 可以写，但写作前门是 innovation（循环依赖）

- manuscript draft 要求 innovation review 产物；innovation 又被 idea plan schema 卡住。
- 设计问题：写作不开门是因为上游评审失败，而不是内容不足；对 ESE run 缺少"跳过 innovation、直接基于证据包写综述"的降级路径。
- 建议：manuscript draft 允许 --skip-innovation（产物标 review_mode=evidence_only，审计仍 blocked）。

### 3.4 writing audit: 英文 paper vs 中文评审模板

- audit 以 article_type=review 审计英文 paper.md，citation_count=0、han_character_count=0，直接 blocked。
- 设计问题：审计没有按语言/体裁选择规则；英文 venue 稿件与中文期刊稿件共用一套检查。
- 建议：audit 接受 --language/--venue，按 profile 选引用与结构规则；英文稿至少检查 [n] 引用与 span 绑定。

### 3.5 门与 ESE 执行器的断层

- ESE 结果已有 capsule/EA（107），但这次 pipeline 产出的是 paper/claim 路径，两者没有汇合：pipeline 不知道 ese_exec 已有一条可签结果。
- 建议：pipeline 增加 --ese-study-dir，把执行结果作为 S5 候选证据挂到 demo（不自动进 claim）。

---

## 4. 本轮证明了什么 / 没证明什么

**证明**：真实 API 下 S0–S16 能跑；S1/S1b/S2/S4/S6/S8 都有真实产物；门按设计停住；writing pack 可用；写作链路在 innovation 处断掉，原因可定位到 plan schema。

**没证明**：没有完整"到结束"的稿件（innovation 失败、无 claim）；没有 surface 的 ESE 结论；英文写作审计未通过。

---

## 5. 下一步（按优先级）

1. **plan schema 联合类型**（修 innovation 卡点，解锁 manuscript draft）；
2. **audit 按语言/venue 选规则**（英文稿可审计）；
3. **pipeline --ese-study-dir**（把已执行 ESE 结果接进 run）；
4. 之后才是 B/C 卡 k≥6 与配方对照。

---

## 6. 补记：同日修复 innovation 卡点后重跑

1. **修复**：创新评审的实验计划校验改为按 profile 分流——只有 `search_factorial` 用 search_lab 因子词汇校验；`protocol_run` / `local_tabular_experiment` 的设计变量（项目、提交大小等）不再被误判为不可执行，标 `executable.deferred_design`。idea SPEC 升 0.27.0。
2. **重跑 innovation review（真实 API）→ 成功**：模型给出 4 个创新点的三评审与修订，分数集中在 7–8；must_fix 是"CSV 必须含 commit_message/file_type/change_size/test_dir_flag 等列，否则词汇-only 不可执行"。
3. **第二个卡点**：`innovation review --output-dir X` 把产物写到 X，而 `manuscript draft` 固定读 `runs/<id>/innovation-review.json`。运行者必须手动拷回 run 目录——这是**输出路径契约不一致**，不是模型问题。已在本轮手动复制并重跑初稿。
4. **建议**：innovation review 默认同时写 `runs/<id>/innovation-review.json`（或 manuscript draft 接受 `--innovation` 路径），并把这条写进 idea SPEC 的 Contract。

## 7. 最终结果：链路真的走通了（真实 API）

| 阶段 | 产物 | 真实读数 |
| --- | --- | --- |
| S1 文献 | literature.json | 8 篇全文、6198 span、coverage=saturated、Q0 pass |
| S1b 综合 | synthesis-matrix.json | 5 个主题、3 条跨来源候选 |
| S2–S3 假设 | idea.json | 3 条候选（mechanism/boundary/measurement） |
| S4 设计 | experiment.json | needs_human；metric/budget 仍不合格（已记录） |
| S6 图 | figure.svg | schematic_ready，不绑结果 |
| S8 稿件 | paper.md | writer_mode=model，Results pending |
| 写作包 | writing-pack.json | 8 来源 + span 证据包 |
| 创新评审 | innovation-review.json | **成功**：4 个创新点 × 三评审 + 修订，分数 7–8；must_fix 指向 CSV schema |
| 中文初稿 | drafts/review.md | 36 KB；**9401 汉字、73 条引用、8 个来源、0 条无引用事实句、13 条多引用句** |
| 手稿评审 | manuscript-review | rounds=1，candidate **accepted=true**，progress=true |
| 成稿审计 | manuscript-audit | **status=ready_for_human_review**；submission_ready=false、claim missing |

**门与签名**：G1/G2 仍 needs_human、G3/G5 blocked；没有 Claim/EA/签名——这是设计边界，不是失败。

这一轮同时暴露并修掉两个真实卡点：

1. **创新评审的实验计划校验绑死 search_lab 因子**（已修：按 profile 分流，idea SPEC 0.27.0）；
2. **innovation review 的 --output-dir 与 manuscript draft 的读取路径不一致**（本轮手动复制产物绕过；建议 CLI 默认双写或 draft 接受 --innovation 路径）。

**结论**：在真实 API 下，ESE 方向的"文献调研 → 假设 → 设计 → 图 → 稿件 → 创新评审 → 中文初稿 → 评审 → 审计"已经完整跑通；剩余未完成的是人签门与 claim/EA/closure，不是流水线能力。

## 8. 同日收尾：路径契约修复 + 下游状态上板

1. **路径修复（已落代码）**：创新评审现在双写 `runs/<id>/innovation-review.json` 与 `--output-dir`，`_review_destinations` 负责去重；manuscript draft 不再需要手动拷贝。idea SPEC 升 0.27.1，新增 3 个目的地测试。
2. **下游状态上 demo 面板**：`build_ese_run_panel.py` 增加 `--project-run-dir/--review-dir`，读取 manuscript-review 与 final-audit，面板新增两行：
   - manuscript-review: needs_more_work · rounds=1 · accepted=True
   - final-audit: ready_for_human_review · citations=73 · han=9401 · submission_ready=False
3. 面板现在覆盖"文献→…→审计"的整条链，仍是生成式（不手写状态）。

## 9. 验证：从零重跑，路径修复真的生效

步骤（全部真实 API）：

1. 把 run 目录里的 `innovation-review.json` 移走（模拟"没有手工拷贝"的初始状态）；
2. 重跑 `innovation review --project ... --run-id RUN-ESE-01 --rounds 1 --output-dir .../innovation`；
3. 检查：run 目录自动出现 `innovation-review.json` → **WRITE_THROUGH=OK**；
4. 直接跑 `manuscript draft --output drafts/review2.md` → **DRAFT=0（成功）**，未做任何手工复制。

结论：上一轮记录的输出路径契约缺陷已修复并被真实重建验证；manuscript 读取与 innovation 写入现在一致。
