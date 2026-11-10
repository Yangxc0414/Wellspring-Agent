# 10 分钟 Quickstart

目标：让你先看到“真的能跑”，再决定接 Qoder、HTTP 还是 Python。

## 0. 前置

- Python 3.8+
- 从仓库根目录运行；不要求先安装成 pip package。
- 基础流程需要 `numpy / pandas / scikit-learn`（当前环境已用于 S5）。
- 文档/图表/HTTP 功能按需使用 `python-docx / openpyxl / matplotlib / Pillow`、`fastapi / uvicorn / pydantic`。
- 不联网；`test` 模式不需要 API key。真实模型改写/写作/创新评审要么配 provider key（Windows 下可放用户环境变量 `DEEPSEEK_API_KEY`，MCP 启动器会从 `HKCU\Environment` 回读，不写入项目文件），**要么绑定 keyless 的 `host_agent` profile 由当前 Agent 出模型**（见下文"零外部 API key"）。

先确认 CLI：

```bash
python -m research_agent --help
python -m research_agent spec list
```

## 1. 5 分钟：跑真实 MCP stdio 演示（不需要 key）

```bash
python scripts/research_mcp_demo.py \
  --project runtime_data/integrations/mcp-demo-project \
  --output runtime_data/integrations/mcp-demo
```

打开：

- `runtime_data/integrations/mcp-demo/summary.md`
- `runtime_data/integrations/mcp-demo/transcript.json`

你会看到：

- `research_project_init`
- `research_plan` / `research_run` 文献综述
- strict 假设任务停在 G1
- `research_skill_list` / distill
- `research_manuscript_revise`
- `research_figure_templates` / `research_figure_render`
- `research_literature_fetch`（必须 allow_network=true）
- `research_writing_pack` / `research_manuscript_audit`（fixture 来源会被正确阻断）

真实网络文献获取（显式 opt-in）：

```bash
python -m research_agent literature fetch   --query "self-improving agent large language model"   --target-dir research-project/inputs --max-results 4 --allow-network
```

下载只发生在 arXiv 公开 PDF；下载后必须用 `source=local` 解析成 span，摘要不算全文证据。

注意：演示使用 `fixture`，只验证流程，不是可引用证据。

更完整的 Qoder MCP 端到端测试（46 个工具、综述、G1、G1→S4 续跑、full_research→G2、AstraDraw、revision、closure/lineage status、multi-judge panel、model profile 发现、writing pack/audit、多源 synthesis/innovation 工具发现与路径越界）：

```bash
python scripts/qoder_e2e_test.py
```

结果在 `runtime_data/qoder-e2e/<timestamp>/summary.md`。

真实 arXiv 搜索 + 下载 + local 全文总结（需要网络）：

```bash
python scripts/qoder_live_literature_task.py
```

真实 arXiv 搜索 + ChemLab 复现实验（会下载 PDF、跑真实 ChemLab 数据、生成 RunCapsule/EA 和 claim draft；不签 Claim）：

```bash
python scripts/qoder_live_experiment_task.py
```

真实 CC-BY 任务（不是 fixture）：

```bash
python scripts/qoder_real_task.py
```

它会读取仓库冻结的 4 篇 CC-BY 全文，跑到 G1，写入一个测试 G1 decision，再续跑到 G2；产物包括 literature-ledger、idea-review、experiment、design-audit 和 stage-report。真实任务的 design-audit 会正确标出缺失的 baseline/metric/budget，而不是假装 ready。

## 2. 2 分钟：已有论文 + 数据 → 投稿工作包（copy mode，不需要 key）

```bash
python scripts/manuscript_revision_demo.py
```

产出：

- `runtime_data/revision-demo-output/revision-diff.json`
- `runtime_data/revision-demo-output/sentence-ledger.json`
- `runtime_data/revision-demo-output/revision-audit.json`
- `runtime_data/revision-demo-output/export/manuscript.{md,tex,docx,pdf}`

默认 `writer_mode=copy`：只更新数据指标、生成图、审计和导出，不假装改写了正文。

零外部 API key 的真实模型流程（宿主 Agent 出模型）：

```bash
# 1) 把生成步骤交给"正在调用本系统的 Agent"（Qoder / Claude Code / Codex / Zcode）
python -m research_agent host-model bind --modules idea,experiment,paper

# 2) 正常跑任务；遇到生成步骤会停下并报一个交接号
python -m research_agent task run --goal "自改进智能体的评估门控" --source real

# 3) 读回运行时想要什么（提示词原文 + 期望形状），让宿主作答后提交
python -m research_agent host-model turns --prompt
python -m research_agent host-model respond --turn-id MT-... --file answer.json

# 4) 重跑第 2 步同一条命令：答案按请求哈希复用，流程继续往下一格走
python -m research_agent host-model status
```

也可以只读队列并驱动整条链路：`python scripts/host_model_loop_test.py --workdir runtime_data/host-model-loop`
（真实 stdio MCP；无答案时把运行时的提示词写到 `pending-request.json`，你作答后重跑同一条命令）。
提交内容只是**能力输出**：span-only、引用白名单、结果数值上限与章节/fixture 审计照旧，
G1/G2/S5b/G5 仍只在 CLI 由人签署。

真实模型改写：

```bash
python -m research_agent revision run \
  --draft runtime_data/revision-demo-input/paper.md \
  --data runtime_data/revision-demo-input/results.csv \
  --metrics runtime_data/revision-demo-input/metrics.json \
  --figures runtime_data/revision-demo-input/figures.json \
  --venue software_journal --profile <runtime-profile-id> \
  --goal "提升论证连贯性，合并冗余表达，不新增事实" \
  --review-file runtime_data/revision-review.json \
  --output-dir runtime_data/revision-model-output

# 改写质量报告：接受率、引用/数字保持、长度比
python scripts/revision_quality_report.py \
  --audit runtime_data/revision-model-output/revision-audit.json \
  --output runtime_data/revision-model-output/quality-summary.md
```

真实测试（7.5 万字中文综述的引言）：`accepted=7/8`、`unchanged=1`、`rejected=0`、引用/数字 8/8 保持、平均长度比 1.05、`review_ready`。报告在 `runtime_data/revision-real-intro-eval3/quality-summary.md`；修复前的整节输出/双层 JSON 版本只有 6.7% 接受。

## 2b. 2 分钟：写作包 + 中文稿预审（MCP/CLI）

写作包把一次 run 压成 Qoder 可直接使用的证据包；它不会替人签 Claim，也不会把未签核的结果写成发现。

```bash
python -m research_agent writing pack \
  --project research-project --run-id <RUN-ID> \
  --max-sources 8 --max-spans-per-source 3

python -m research_agent writing audit \
  --project research-project --run-id <RUN-ID> \
  --draft research-project/drafts/review.md

# 需要模型 key 时：句级支持账本 + 严格门
python -m research_agent writing audit \
  --project research-project --run-id <RUN-ID> \
  --draft research-project/drafts/review.md \
  --semantic --strict-support --strict-pack-binding --support-votes 3 --judge-profile <profile-id>
```

支持 judge 校准（项目自建回归集，不是独立人工金标准）：

```bash
python -m research_agent writing support-eval --votes 3 --output-dir runtime_data/support-calibration
```

`--semantic` 会把每个 `[REF-xx]` 句绑定到选中 span 并给出支持/部分支持/相反/证据不足；strict 下证据不足、相反或稿-包 marker 不一致会阻断。

产物：

- `<run>/writing-pack.json` / `.md`：来源卡（REF-01…）、选中 span、idea/design/run/claim 状态、写作契约、warnings；
- `<run>/writing-audit.json`：`ready_for_human_review` 或 `blocked`，`submission_ready` 始终 false。

规则：

- 草稿只能引用 pack 中的 `[REF-xx]`；不能编造标题、作者、DOI；
- Claim 未签核时，结果段不得出现数值；已签核时只能使用 `allowed_result_numbers`；
- fixture 来源、未知引用、缺章节、`TODO/待补` 会阻断；
- 这是结构审计，不做语义蕴含判断，也不替代同行评审。

真实示例：4 篇 arXiv 全文 → 4,351 个句级 span → 写作包（4 个来源卡，约 6.1k tokens）→ 中文综述稿 → 审计 `ready_for_human_review`（review 类型，claim missing）→ revision 导出 DOCX/PDF。产物在 `runtime_data/qoder-live-literature/20261026T110020Z/`；DOCX/PDF 是中文期刊工作排版，不是官方模板。

## 2c. 30–60 分钟：顶会语料 → 创新点 → 文章 → 多轮评审（需要 DeepSeek key）

```bash
# 1) 初始化项目并抓取近 2–3 年顶会 arXiv 公开版本（显式联网）
python -m research_agent project init --dir research-project --name "TopConf"
python -m research_agent conference fetch \
  --target-dir research-project/inputs \
  --topic "LLM agents scientific discovery self-improvement" \
  --venues NeurIPS,ICLR,ICML,ACL,EMNLP,AAAI --years 2024,2025,2026 \
  --max-papers 24 --max-per-venue 4 --allow-network
```

在 Qoder 中调用 `research_run({project_dir:"research-project", goal:"...", task_type:"literature_review", source:"local", max_sources:24, flow_mode:"review"})` 得到 `RUN-ID`，然后：

```bash
# 2) 写作包 + 创新评审 + 初稿 + 手稿评审
python -m research_agent writing pack --project research-project --run-id RUN-... --max-sources 16
python -m research_agent literature synthesize --project research-project --run-id RUN-... --max-themes 7
python -m research_agent innovation review --project research-project --run-id RUN-... --rounds 2
# 一条命令带上研究臂：把设计映射成 search_factorial 计划并真的执行（--study-project 让它可被盘点）
python -m research_agent pipeline run --topic "..." --language en --venue en_conference \
  --output-dir runtime_data/pipeline-study --study-dataset iris --study-seeds 8 --study-budget 60 \
  --study-project runtime_data/from-idea-check/studies
# 想让三个审稿角色真的落在不同模型供给上（供给不足会直接失败并说明缺几个）：
python -m research_agent innovation review --project research-project --run-id RUN-... --independent
python -m research_agent innovation review --project research-project --run-id RUN-... \
  --critic novelty=host_crit_a --critic evidence=host_crit_b --critic feasibility=host_crit_c
python -m research_agent manuscript draft --project research-project --run-id RUN-... \
  --output research-project/drafts/review.md
python -m research_agent manuscript review --project research-project --run-id RUN-... \
  --draft research-project/drafts/review.md --rounds 2 --threshold 7.0

# 可选：把句级支持失败喂进评审/修订，并拒绝让支持变差的修订
python -m research_agent manuscript review --project research-project --run-id RUN-... \
  --draft research-project/drafts/review.md --rounds 2 --threshold 7.0 \
  --semantic-support --strict-support --revision-mode section --ab-check --ab-section 讨论

# 只修支持账本标出的 partial/insufficient 句（find/rewrite JSON patch）
python -m research_agent manuscript review --project research-project --run-id RUN-... \
  --draft research-project/drafts/review.md --rounds 2 --threshold 7.0 \
  --semantic-support --strict-support --revision-mode support --ab-check
```

本机真实产物（22 篇检索、22 篇全文、16 篇写作包、16 篇 → 6 个跨来源主题、三个创新方向、59 处引用/16 个正文来源、0 结果数值、DOCX/PDF）：

- `runtime_data/topconf-research-2026/run-summary.md`
- `runtime_data/topconf-research-2026/revisions/REV-20261026T1601140000-f589ae/export/manuscript.docx`
- `runtime_data/topconf-research-2026/revisions/REV-20261026T1601140000-f589ae/export/manuscript.pdf`

边界：venue 来自 arXiv comment，未独立核验；这是立场综述/研究议程，不是已验证实验论文；模型评审 6.0→6.2，未达 7.0 阈值；不创建 Claim/EA/gate，`submission_ready=false`。

## 2d. 2 分钟：把创新评审选出的想法真的跑成实验

上面那步产出的 `experiment_plan` 不再是只给写作提示词看的文字：`study from-idea` 会校验它绑定的
档位，把它声明的设计真的执行成一份研究，并记下"这些数字是为了检验哪个假设"。

```bash
python -m research_agent study profiles          # 可执行档位 + 因子空间 + 算子集合
python -m research_agent study from-idea \
  --project runtime_data/topconf-research-2026 --run-id RUN-... --idea-id IDEA-01 \
  --seeds 1,2,3,4,5,6,7,8 --budget 60
python -m research_agent study claim --study-dir <project>/studies/STUDY-IDEA-01 \
  --statement "..." --human-reason "..." --scope RUN-.../IDEA-01
python -m research_agent study closure --study-dir <project>/studies/STUDY-IDEA-01
```

一个数据集上集训定的区间，只说明这一个数据集。"换个数据还成立吗"因此不是哲学问题，而是把同一
设计写到第二个数据集、然后读一条命令：

```bash
python -m research_agent study search --project <project> --dataset breast_cancer \
  --seeds 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16 --budget 60 \
  --factors memory=False,True --factors gate=False,True
python -m research_agent study replicate --project <project>
```

本机实测（同一 memory×gate 2×2、16 种子、iris/wine/breast_cancer 三份研究包）：
`memory_on_gate_on` 与 `memory_x_gate_interaction` 为 **consistent(negative)**，分别由 2 个数据集
判定；`memory_on_gate_off` 只在 iris 判定（positive），故 `generalizes=false`；
`memory_off_gate_on` 三处全部跨零 = `undecided`。翻译成人话：**"归档 + 贪婪门控一起用会让搜索变差"
是目前最站得住的结论，"只用归档就更好"明确不泛化**。复现只数判定的数据集，不数试过的数据集。

也可以直接换一个假设来问（第一个水平是参照格；未知因子/水平或格子数 >12 会被拒绝）：

```bash
python -m research_agent study search --dataset wine --seeds 1,2,3,4,5,6,7,8 --budget 60 \
  --factors gate=on --factors operators=all,feature_only,knob_only
```

边界：只有 `profile=search_factorial` 的计划能这样执行（其余档位走 `run execute` / `experiment run`）；
种子 <4、目标目录已有研究（除非 `--force`）都在写文件之前拒绝；区间跨零时结果是**非结果**，
`study closure` 会停在 `claim.signed` 这个人签门上，`submission_ready` 始终 false。

### 持续委托只读视图（META）

```bash
python -m research_agent mandate status --project research-project
```

它只读聚合 `runs/*/loop-capsule.json` 的 blockers/next_actions 与可选 autopilot policy，
输出 trigger/context/plan/approval/verification/obligations；policy 过期 → `status=stopped`
且退出码 1。不签名、不批准、不执行，缺失 artifact 不是 pass。

## 2e. 2 分钟：S4 设计 + CSV → 代码 → 本地执行 → 证据 → 人签 Claim

```bash
# 1) 生成代码包（不执行）
python -m research_agent experiment scaffold \
  --project runtime_data/experiment-codegen-demo --run-id RUN-EXP-DEMO-001 \
  --data inputs/breast_cancer.csv --target target \
  --features mean_radius,mean_texture,mean_perimeter,mean_area,mean_smoothness,mean_compactness,mean_concavity,mean_concave_points,mean_symmetry,mean_fractal_dimension \
  --task classification --methods dummy,logistic --metric accuracy --seeds 3 \
  --experiment-id EXP-BREAST-CANCER
# 可选更强表格基线：--methods dummy,random_forest,gradient_boosting
# 可选 k-fold CV：--cv-folds 5（0 = holdout split）
# codegen 会先审计数据：缺失/重复/常量列/ID-like/类别不平衡/可疑目标相关

# 可选：ridge alpha 固定网格 + 本地 sweep 生命周期
# sweep-approve 人签 → sweep-run --allow-execute → sweep-ingest；
# sweep 使用与确认实验相同的 cv_folds；sweep evidence 是 verified_exploratory，不是 EA/Claim
python -m research_agent experiment scaffold --project <project> --run-id <RUN-ID> \
  --data inputs/data.csv --target y --features x1,x2 --task regression \
  --methods dummy,ridge --metric r2 --alpha-grid 0.1,1,10 --experiment-id EXP-SWEEP
python -m research_agent experiment sweep-approve --project <project> --experiment-id EXP-SWEEP --human-reason "checked sweep plan/budget"
python -m research_agent experiment sweep-run --project <project> --experiment-id EXP-SWEEP --allow-execute --timeout 600
python -m research_agent experiment sweep-ingest --project <project> --experiment-id EXP-SWEEP
python -m research_agent experiment sweep-status --project <project> --experiment-id EXP-SWEEP
# 4) 用 sweep 选出的 alpha 做确认实验（仍走完整 approve/run/ingest/claim）
python -m research_agent experiment approve --project <project> --experiment-id EXP-SWEEP --ridge-alpha 0.1 --human-reason "confirm selected alpha"
python -m research_agent experiment run --project <project> --experiment-id EXP-SWEEP --ridge-alpha 0.1 --allow-execute --timeout 600
python -m research_agent experiment ingest --project <project> --experiment-id EXP-SWEEP

# 1b) preflight：只做 --dry-run schema/依赖校验，不训练、不生成 evidence
python -m research_agent experiment preflight --project <project> --experiment-id EXP-...

# 2) 人工审批 + 显式本地执行（不会自动启动）
python -m research_agent experiment approve --project runtime_data/experiment-codegen-demo \
  --experiment-id EXP-BREAST-CANCER --human-reason "checked design/data/split"
python -m research_agent experiment run --project runtime_data/experiment-codegen-demo \
  --experiment-id EXP-BREAST-CANCER --allow-execute --timeout 600

# 3) 校验 execution/receipt/metrics/artifact 哈希，生成 experiment-evidence.json
python -m research_agent experiment ingest --project runtime_data/experiment-codegen-demo \
  --experiment-id EXP-BREAST-CANCER

# 4) 人工检查指标后签本地 Claim（CLI-only；不签就不会放行结果数值）
python -m research_agent experiment claim --project runtime_data/experiment-codegen-demo \
  --experiment-id EXP-BREAST-CANCER \
  --statement "Logistic regression outperforms the dummy baseline on held-out accuracy in this local protocol." \
  --human-reason "checked design, seeds, metrics and artifact hashes" \
  --assertion "metric=accuracy,value=0.85,comparator=>=,tolerance=0.01"
```

人签后做实验专用 closure/lineage（不是 RunCapsule/EA closure）：

```bash
python -m research_agent experiment closure --project runtime_data/experiment-codegen-demo --experiment-id EXP-BREAST-CANCER
python -m research_agent experiment sign --project runtime_data/experiment-codegen-demo --experiment-id EXP-BREAST-CANCER --report runtime_data/experiment-codegen-demo/experiments/EXP-BREAST-CANCER/experiment-closure/closure-report.json --human-reason "final local closure check"
python -m research_agent experiment lineage --project runtime_data/experiment-codegen-demo --experiment-id EXP-BREAST-CANCER
python -m research_agent experiment lineage --project runtime_data/experiment-codegen-demo --experiment-id EXP-BREAST-CANCER --verify
```

同一个 run 的实证文章闭环（要求 literature/synthesis/innovation 与实验同 run，且 claim 已人签；未满足时 `check` 直接列出 blocker）：

```bash
python -m research_agent empirical check --project <project> --run-id <RUN-ID> --experiment-id <EXP-ID>
python -m research_agent empirical paper --project <project> --run-id <RUN-ID> --experiment-id <EXP-ID> \
  --output <project>/drafts/empirical.md --review-rounds 2 \
  --method-template calm-method   # 可选：AstraDraw 方法示意图，标 schematic=true，不是结果图
```

`empirical paper` 生成写作包/初稿/多轮评审，并把最终稿审计绑到 experiment closure；`--method-template` 或 `--method-scene` 可额外渲染一张 AstraDraw 方法示意图（图 2，`schematic=true`），审计禁止把它放进结果节。不执行实验、不签 Claim/closure、不投稿，状态最多 `ready_for_human_review`。

数据结果图（只从 verified evidence 生成；需要本机已有 matplotlib，缺库时跳过而不是安装依赖）：

```bash
python -m research_agent experiment figure --project <project> --experiment-id <EXP-ID>
python -m research_agent experiment figure --project <project> --experiment-id <EXP-ID> --verify
```

图落在 `<run>/figures/empirical-result/`，manifest 绑定 spec/execution/evidence/claim 哈希并标 `schematic=false`、`kind=data_result_plot`、`renderer=matplotlib`、`astradraw=false`；它不是 AstraDraw 方法示意图。实证稿必须引用图 1，否则审计阻断。方法/框架示意图仍走 `figure render`（AstraDraw，`schematic=true`）。

生成 runner 的 `metrics.json`/receipt 还包含 primary vs baseline 的 paired `mean_diff`、normal-approx 95% CI 与 `wins`；它不是显著性检验。`outputs/results-table.md` 是可直接进论文的结果表（表 1）。

本机 demo 结果：dummy accuracy 0.6082，logistic 0.8918 ± 0.0149（3 seeds）；`experiment-evidence.json` 已 verified，**Claim 尚未签核**，因此 closure 当前按预期 blocked。边界：不自动装依赖、不自动探索、不创建 EA/Claim；MCP 不执行训练或签核。详见 `runtime_data/experiment-codegen-demo/summary.md`。

自动启动/多配置探索仍未实现；执行必须在用户环境、显式 opt-in 和 G2 之后。

## 3. 1 分钟：AstraDraw 方法示意图

```bash
python -m research_agent figure templates
python -m research_agent figure render \
  --template framework-example \
  --output-dir runtime_data/figure-demo \
  --title "Example Framework"
```

产出：

- `runtime_data/figure-demo/framework-example.svg`
- `runtime_data/figure-demo/framework-example.png`
- `runtime_data/figure-demo/framework-example.audit.json`
- `runtime_data/figure-demo/framework-example.manifest.json`

模板是视觉先验，`schematic=true`；数据图请用 revision 的指标图。

## 4. 2 分钟：非 MCP 框架 HTTP 桥

```bash
python scripts/framework_bridge_demo.py
```

它会自动启动一个隔离 runtime，并用 `ResearchAgentClient` 完成：

```text
capabilities → project → plan → run → status → read
```

结果在 `runtime_data/integrations/framework-bridge-demo/summary.md`。

手动启动：

```bash
python -m research_agent.runtime --port 8787
```

前端开发服务器默认把 `/api` 代理到 `127.0.0.1:8787`。runtime 换端口或换机器时，只在
**启动 vite 的 shell** 里设置代理目标，不要用 `VITE_RUNTIME_URL`——那个变量客户端也会读，
会让浏览器直接跨域打绝对地址，面板会退化成 “UNAVAILABLE”：

```bash
RUNTIME_PROXY_URL=http://127.0.0.1:9000 npm --prefix apps/web run dev
```

远程访问必须设置：

```bash
RESEARCH_AGENT_API_TOKEN=<random-token> \
  python -m research_agent.runtime --host 0.0.0.0 --allow-remote --port 8787
```

## 5. 接入 Qoder

1. 生成项目级 MCP 配置（写入 `.mcp.json`，该文件含本机绝对路径，已被忽略）：
   `python scripts/setup_mcp.py`
2. 打开本仓库；
3. `/skills reload`，或重启会话；
4. `/mcp reload`，确认 `research-agent` 出现 46 个工具；
5. 直接说：

> 用 research-workflow 在 research-project 里对 inputs/ 做一轮文献综述，review 模式。

严格任务会停在 G1/G2/S5b/G5；Qoder 只能显示 CLI 命令，不能替你签核。

如果 Qoder 只给建议而没有实际调用工具，补一句：

```text
请实际调用 research_* MCP 工具，不要只说明步骤。
```

Qoder 当前会话的工具目录是启动时加载的；`mcp_list` 仍为空时不要怀疑服务端，先 `/mcp reload` 或重启。

## 6. 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| Qoder 看不到 `research_*` | 会话工具目录未刷新 | `/mcp reload` 或重启 |
| HTTP 401/403 | 缺 token / 非 loopback | 设置 `RESEARCH_AGENT_API_TOKEN` |
| production 503 | 模型未 wired/bound | 绑定 profile：provider 需要 key，`host_agent` 不需要；或先用 test |
| 文档说“完成”但 `stopped_at=G1` | 人工门 | 查看 `research_next_actions`，人执行 CLI |
| 图没有任务里的内容 | 模板只是视觉先验 | 编辑输出 `.scene.json` 后重新 `figure render --scene` |
| fixture 结果被当论文证据 | 来源是 fixture | 看 `fixture_mode`，换 local/真实全文 |

## 7. 下一步读什么

- 架构与扩展点：[`ARCHITECTURE.md`](ARCHITECTURE.md)
- 模块契约：[`modules/README.md`](modules/README.md)
- Qoder / Claude / Zcode：[`integrations/README.md`](integrations/README.md)
- HTTP / LangGraph / CrewAI / AutoGen：[`integrations/FRAMEWORKS.md`](integrations/FRAMEWORKS.md)
- 当前状态与路线：[`组会汇报-科研智能体进展与下一步.md`](组会汇报-科研智能体进展与下一步.md)

## 边界

- 当前实验只内置 iris / breast_cancer / ChemLab 协议验证；任意本地实验 runner 仍在 roadmap。
- 当前 revision 的期刊模板是工作 profile，不是官方模板。
- 当前没有 sign/approve/freeze/publish MCP 工具。
- `submission_ready` 不是自动投稿许可。

## 发行包（Wellspring-Agent）怎么生成

发行目录是构建产物，不要手改，也不要再手工拷贝：

1. 同步并剪掉构建不会产出的文件：`python scripts/build_release.py --prune`
2. 只看漂移不写盘：`python scripts/build_release.py --check`
3. 校验一致性：`python -m unittest tests.test_release_integrity`

`--prune` 只删构建器判定不该存在的文件（包内运行数据 `research_agent/web/data`、
第三方工具的 `.local`/`output`/`docs`、`__pycache__`、以点开头的文件），
仓库根本身的数据一律不动。MANIFEST.txt 是这份构建的输出清单，逐条带 SHA-256 与字节数。

接入 Qoder / Claude Code / Zcode / Codex 的 MCP 配置模板放在 `integrations/mcp/`，
用 `python scripts/setup_mcp.py` 生成指向你本机仓库根的 `.mcp.json`（已存在时需要 `--force`）。
配置由你自己保存；工具面里没有签核、批准、冻结、闭包签署、发布或导出端点，这些永远在 CLI/人这一侧。
