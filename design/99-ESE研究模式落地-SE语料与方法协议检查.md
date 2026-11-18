# 99-ESE 研究模式落地：SE 语料 + 方法协议检查的第一条纵切

> 状态基线：2026-11-18。承接 97（定位）与 98（案例研究）。
> 本轮把"流水线针对 ESE 方向"从口号变成可执行模式：S1 接真实 cs.SE 语料，S4 按选定 ESE 方法检查协议完整性，并跑通一条真实纵切。
> 边界：只到 S4（设计草稿），没有 S5 执行/Claim/人签；方法检查是 advisory，不是门禁。

---

## 1. 新增的两个入口

### 1.1 SE 语料：`scripts/fetch_se_corpus.py`

- 查询 arXiv `cat:cs.SE` + 主题词（默认 flaky test），按提交时间取最近论文；
- 下载 PDF 到 `runtime_data/se-corpus/pdfs/`（gitignored），manifest 记录 arXiv id / 年份 / comment / SHA-256 / **license 提示**；
- 不把 PDF 或全文提交进仓库（arXiv 许可各异），管线通过 `--corpus-dir` 本地解析；摘要仍不能当证据。

### 1.2 ESE 方法检查：`pipeline run --ese-method <id>`

- 复用 `modules/method-registry` 的 9 个 ESE 方法与任务卡；
- S4 设计完成后，按所选方法检查 `protocol_fields`（如 repository-mining 的 sampling_frame / time_window / dedup_policy / label_source）；
- 写出 `ese-method.json` 到 run 目录，并在 `demo.json` 的 `extra.ese_method` 记录；
- **advisory**：缺失字段只报告，不改设计状态、不替代 G2、不进 Claim。

命令：

```bash
python scripts/fetch_se_corpus.py --topic "flaky test" --max-papers 8
python -m research_agent pipeline run \
  --topic "Which repository signals predict flaky test occurrence in continuous integration?" \
  --language en --venue en_conference \
  --corpus-dir runtime_data/se-corpus/pdfs --max-sources 8 \
  --idea-model deepseek-v41 --experiment-model deepseek-v41 --writer deepseek-v41 \
  --ese-method repository-mining \
  --output-dir runtime_data/ese-pipeline-20261118
```

---

## 2. 第一条 ESE 纵切的真实产物

| 项 | 读数 |
| --- | --- |
| 语料 | arXiv cs.SE 8 篇 flaky-test 论文（Shaker/Python、Swift 词汇、CPS 混合模型、Delta Debugging、预测性测试优化、代码检测极限、可复现数据集、NeuroFlake） |
| 解析 | 6198 个 span，`fixture_mode=false`（真实全文） |
| S2 候选 | 3 条，全部 grounded（每条 4 个 evidence_ref，可解析到同 run span） |
| 候选主题 | ① CI rerun vs 静态仓库信号 ② ecosystem-conditioned 信号 ③ reproducibility-filtered 标签改变结论 |
| S4 设计 | hypothesis/baseline/AUC/controls(3)/seeds(3)/budget 均在；方法检查报 **7 个协议字段缺失** |
| `ese-method.json` | `method=repository-mining`、`status=advisory_missing`、缺失 sampling_frame/project_selection/time_window/time_split/dedup_policy/label_source/license_check |

方法检查的读法：这不是失败，而是**设计还没达到 repository-mining 的可预注册水平**——缺抽样框、时间切分、去重与标签来源。对 ESE 研究来说，这些字段比"有没有 AUC"更关键。

---

## 3. 设计层为什么这样接

- **方法是一等输入**：同一个研究问题在不同 ESE 方法下要求的协议完全不同；把方法作为 pipeline 参数，才能让 S4 的产出对准方法规范。
- **检查只读**：方法检查不能改变设计字段或门禁（与 85 号的"advisory only"边界一致），但它会留下证据——人能在 G2 前看到缺什么。
- **语料可替换**：`--corpus-dir` 是通用入口，SE 语料只是其中一种；未来可接本地 PDF 库、会议 corpus、机构库。
- **不伪造 SE 结论**：S4 只是设计；没有 S5 执行与 Claim，就不能说"某个仓库信号能预测 flaky test"。

---

## 4. 验收

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 语料抓取 | `scripts/fetch_se_corpus.py` | 8 PDF + manifest，退出 0 |
| ESE 纵切 | `pipeline run … --corpus-dir … --ese-method repository-mining` | 退出 0；`fixture_mode=false`；3 候选、6198 span |
| 方法检查 | 读 `ese-method.json` | advisory_missing，列出 7 个缺失字段 |
| 单元测试 | `python -m unittest tests.test_ese_pipeline` | 4 项 OK |
| 规格 | `spec update experiment --version 0.10.0` | S4 可附带 ESE 方法检查（advisory）已入 changelog |

---

## 5. 未完成与下一步

| 缺口 | 说明 | 下一步 |
| --- | --- | --- |
| 只有 S1–S4 | 没有 S5 执行、Claim、closure | 选一个可本地执行的设计（如仓库挖掘脚本）走 S5 |
| 方法字段缺失 | 设计没写 sampling_frame/time_split/dedup/label_source | 让 S4 把方法任务卡作为输入（下一轮：字段级提示 + 检查回环） |
| 语料是 preprint | arXiv cs.SE 非同行评审全集 | 允许会议 corpus/本地 PDF 库；记录 venue 与 license |
| 语料许可 | 只本地使用，不提交 | 保留 manifest 的 license_note；不把 PDF 进 git |

**一句话**：从这一轮起，"拿一个 ESE 研究问题 + SE 语料 + ESE 方法"可以真的跑进流水线，并产出一份能被方法规范检查的设计与缺口清单；距离"可签署的 ESE 结论"还差 S5 执行与人签。
