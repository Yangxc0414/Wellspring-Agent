# 100-仓库归属反思与第二条 ESE 探索（benchmark-evaluation）

> 状态基线：2026-11-18。承接 99（ESE 研究模式落地）。
> 本文件回答两件事：① 代码到底应该改在哪个仓库；② 用现有流水线继续对 ESE 问题进行探索的第二条纵切。

---

## 1. 仓库归属：源仓库是 research-agent，Wellspring-Agent 是发布副本

本地事实（`git remote -v`）：

| 目录 | remote | 角色 |
| --- | --- | --- |
| 仓库根 `D:\Users\20691\Desktop\毕业设计` | `github.com/Yangxc0414/research-agent` | **源仓库**：`research_agent/`（后端/流水线）、`modules/`（SPEC）、`site/`（前端 demo）、`apps/web/`、`tests/`、`scripts/` |
| `Wellspring-Agent/` | `github.com/Yangxc0414/Wellspring-Agent` | **发布副本**：由 `scripts/build_release.py` 从根目录同步（SYNC_FILES/SYNC_DIRS；少量 RELEASE_OWNED 文件例外） |

因此：

- "项目代码在 Wellspring-Agent" 只对**发布产物**成立；Wellspring 里的代码是从根目录复制过去的，不是独立开发的源；
- "GitHub 上前端代码在 research-agent" 成立：前端 demo（`site/`、`apps/web`）属于源仓库，Pages 由 research-agent 仓库发布；
- **改代码要在根目录改**，再跑 `python scripts/build_release.py` 同步。直接改 Wellspring 的同步区会被下一次同步覆盖；
- 若希望反过来（Wellspring 为源、research-agent 只放前端），需要重写 `build_release.py` 的方向与 CI 漂移检查；这是流程决策，不是顺手改。

本轮所有实现（ESE 研究模式、方法检查、测试）都在根目录完成，并已/将同步到 Wellspring。

---

## 2. 第二条 ESE 探索：benchmark-evaluation

同一份真实语料（arXiv cs.SE 8 篇 flaky-test 论文，6198 span，`fixture_mode=false`），换一个 ESE 方法与研究问题：

```bash
python -m research_agent pipeline run \
  --topic "Do code-based flaky-test detectors generalize across datasets and ecosystems?" \
  --language en --venue en_conference \
  --corpus-dir runtime_data/se-corpus/pdfs --max-sources 8 \
  --idea-model deepseek-v41 --experiment-model deepseek-v41 --writer deepseek-v41 \
  --ese-method benchmark-evaluation \
  --output-dir runtime_data/ese-pipeline-bench-20261118
```

产物（真实）：

| 项 | 读数 |
| --- | --- |
| 方法 | `benchmark-evaluation`（S4 适用） |
| 候选 | 3 条，全部 grounded；主题：ecosystem-specific cues / label-reproduction heterogeneity / runtime-hybrid signals |
| 设计 | metric=generalization gap（balanced accuracy 从 within-source 到 cross-dataset 的下降）；baseline=within-dataset 同检测器 |
| 方法检查 | `advisory_missing`，缺 **6** 个协议字段：benchmark、benchmark_version、contamination_check、budget_matching、baselines、saturation_note |
| 语料 | 8 篇、6198 span、非 fixture |

与第一条（repository-mining）对照：

| 方法 | 缺失字段 |
| --- | --- |
| repository-mining | sampling_frame、project_selection、time_window、time_split、dedup_policy、label_source、license_check |
| benchmark-evaluation | benchmark、benchmark_version、contamination_check、budget_matching、baselines、saturation_note |

**这正是"用流水线探索 ESE"的样子**：同一个语料、同一套 S1–S4，换方法就换出一组不同的可预注册要求；缺口是具体可补的，而不是一句"设计不够好"。

---

## 3. 这条纵切证明了什么 / 没证明什么

**证明**：

1. 流水线可以在真实 SE 文献上跑 S1（6198 span）→ S2（3 条 grounded 候选）→ S4（方法相关设计）；
2. 方法注册表不是装饰：不同方法会产生可区分的协议缺口；
3. 语料可替换（`--corpus-dir`），不需要改代码就能换研究领域。

**没证明**：

1. 没有 S5 执行、没有 Claim/closure/人签——不能说"某个仓库信号能预测 flaky test"；
2. 语料是 arXiv preprint，不是同行评审全集；没有 venue 分层与发表偏倚控制；
3. 方法检查是 advisory，不是质量评分；字段补齐也不等于设计正确；
4. 没有人类评审参与，不能替代 G2。

---

## 4. 下一步（把探索变成可签署的 ESE 结论）

选一条成本最低、可本地执行的路线：

1. **repository-mining 最小闭环**：抽样框 = 本地两个有 git 历史的仓库（research-agent / Wellspring）；时间切分 = 按提交顺序前后半；去重 = 同一天批量导入提交合并；标签 = 测试文件是否与源码同提交变更；抽取脚本 = `scripts/msr_*.py`；产出区间与复现命令；
2. 把该设计写进 S4（补齐 sampling_frame/time_window/dedup/label_source），走 `experiment scaffold/run` 或独立执行，再由人签 Claim；
3. 第三条用 benchmark-evaluation：在同一 flaky-test 语料上做"跨数据集迁移"的二手数据 meta 分析（需要论文报告的数值表，成本更高）。

**边界**：在 S5 与人签之前，以上都只是设计探索，不是 ESE 结论。

---

## 5. 验收

| 项 | 结果 |
| --- | --- |
| 第二条 ESE 纵切 | 退出 0；`ese-method.json` 记录 benchmark-evaluation 的 6 个缺失字段 |
| 第一条 ESE 纵切（99） | 退出 0；repository-mining 7 个缺失字段 |
| 方法检查单测 | `tests.test_ese_pipeline` 4 项 OK |
| 仓库同步 | 根目录 → Wellspring（`build_release.py`） |
