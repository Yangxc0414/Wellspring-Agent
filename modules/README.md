# `modules/` — 子智能体模块规格

每个子智能体一个目录，目录内 `SPEC.md` 是**唯一契约源**。代码读取它，CLI 最小更新它；后续改进模块时先改规格。

> 完整模块清单、代码路径与当前阶段见 [`AGENTS.md`](../AGENTS.md) §8；架构分层与可扩展点见 [`ARCHITECTURE.md`](../ARCHITECTURE.md)。

## 目录

```text
modules/
  _template/SPEC.md      # 新模块模板
  task-agent/SPEC.md     # S0–S12 任务路由与执行
  literature/SPEC.md     # S1 文献调研
  idea/SPEC.md           # S2–S3 假设收敛
  experiment/SPEC.md     # S4 实验设计
  figure/SPEC.md         # S6 SVG 绘图
  paper/SPEC.md          # S8–S12 论文契约
  manuscript/SPEC.md     # 中文投稿工作稿与审计
  writing/SPEC.md        # S8–S12 写作包与手稿预审
  revision/SPEC.md       # 已有手稿修订、数据图与投稿包
  grant/SPEC.md          # NSFC/NSSFC 基金轨
  venue-audit/SPEC.md    # 中文期刊稿件与基金申请结构/合规检查
  rsi/SPEC.md            # 受治理的 RSI 控制面（META）
  search-study/SPEC.md   # S5 可执行改进搜索研究（记忆 × 接受门控）
  host-model/SPEC.md     # 宿主模型交接（META）：无外部 key 的生成能力供给
  autopilot/SPEC.md      # 策略自动驾驶（META）：人授权一次，G1/G2/S5b/G5 在边界内代跑
  mandate/SPEC.md        # 持续委托投影（META）：只读聚合 blockers/next_actions/policy，不新增权限
  verdict-ledger/SPEC.md # 判定总线（S5–S16）：确定性只读投影已存在的判定，快照漂移 fail-visible
  feedback/SPEC.md       # 反馈端口（S5–S16）：observe→propose→gate(默认拒绝)→apply→record，默认全关
  memory-port/SPEC.md    # 记忆写入端口（META）：四准入策略对象，默认 store_all=现状逐字节一致
  ccfa-audit/SPEC.md     # S4 CCF-A 实验设计披露审计（拆分研究设计与本地 run 设计）
  literature/fixtures/   # 仅离线测试用的 fixture 语料
```

## 新增模块

1. 复制 `modules/_template/SPEC.md` 到 `modules/<id>/SPEC.md`；
2. 改 `id` / `name` / `stage` / `inputs` / `outputs` / `gates` / `invariants`；
3. `status: draft`，先实现 contract 与测试，不直接 `active`；
4. 在 `research_agent/modules/` 实现子智能体，只依赖端口，不直接联网；
5. 在 `tests/` 增加模块契约测试；
6. 用 `python -m research_agent spec list` 确认注册表读得到。

## 扩展点与当前状态

| 扩展点 | 当前状态 | 正确方式 |
| --- | --- | --- |
| idea/experiment 模块替换 | 已实现 | `module_overrides` / `module_factories` |
| MCP/HTTP/Python 工具 | 静态注册 | 先改 `mcp_server.py` + `framework_api` + schema/tests；`CapabilityRegistry` roadmap |
| AstraDraw 模板 | 代码映射 | 当前改 `figure_workflow.TEMPLATES`；计划 JSON registry |
| 期刊 profile | 代码 profile | 当前改 `revision_templates.py`；计划 JSON registry |
| 外部 Skill | advisory + distill | `skill scan/enable/invoke`；脚本本地 trusted opt-in |
| 顶会语料获取 | 已实现（有界） | `conference fetch`；venue 来自 arXiv comment，不是完整 proceedings |
| 多篇综合矩阵 | 已实现（模型辅助） | `literature synthesize`；每主题 ≥2 篇，未使用来源显式记录 |
| 研究主循环 ledger | 已实现（只读） | `loop status`；阶段/门禁/迭代/下一步，不替代 orchestrator |
| 创新/手稿评审 | 已实现（模型辅助） | `innovation review` / `manuscript review`；评分是 advisory，不替代 G1/同行评审 |
| 声明式 Skill workflow | 未实现 | `SkillRuntime` roadmap |
| 任意本地实验环境 | 未实现 | `LocalExperimentRunner` roadmap |

新增工具时必须同步：工具 schema、`TOOL_NAMES`/`TOOLS`、dispatch、capabilities、MCP/HTTP/Python 测试、三端 SKILL 与集成文档。不要把 roadmap 写成已实现。

## 可插拔扩展点

PipelineRunner 现在支持不改主流程替换模块：

```python
runner = PipelineRunner(
    module_overrides={"idea": MyIdeaAgent(spec)},
)
# 或者用工厂：
runner = PipelineRunner(
    module_factories={"idea": lambda spec: MyIdeaAgent(spec)},
)
```

TaskAgent 也接受同一份 `module_overrides`，因此自定义 idea/experiment 实现可同时用于直接任务路由和完整 pipeline。

约束不变：

- 被替换对象必须保持 `module_id`、`run(request) -> result`（S5 为 `execute(request, output_dir)`）以及对应契约字段；
- 替换实现仍然不能创建 Claim/EA、不能绕过人工门；
- 新模块仍必须先有 `SPEC.md`，再实现和测试；
- 替换模块的输出仍要能被 `write_pipeline_artifacts` 和 runtime/closure 消费。

## 最小改模块

```bash
python -m research_agent spec show literature
python -m research_agent spec update literature --version 0.1.1 --status pilot --changelog "..."
python -m research_agent spec patch literature --section "Current Implementation" --text "..."
```

## 新增能力检查表

- 新模块：`SPEC.md`（draft）→ 契约测试 → 实现 → 全量测试；
- 新工具：JSON Schema → 权限/边界 → `mcp_server`/`framework_api` → MCP/HTTP/Python smoke test；
- 新期刊/模板：优先数据文件；若仍是代码，必须加版本、样例和边界；
- 新实验环境：不能把依赖装进智能体；定义 `EnvironmentSpec` + 本地 runner + 人工执行确认；
- 新 Skill：先定义输入/输出/检查/人工门，再决定它只是 advisory 还是可执行 workflow。

规则详见根目录 `AGENTS.md`。
