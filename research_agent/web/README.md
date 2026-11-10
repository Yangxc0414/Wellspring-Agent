# Module Workbench

静态工作台，读取 `data/tasks.json`（任务索引）、每个任务目录下的 `demo.json`/`specs.json`、全局 `models.json`（模型绑定）与 `rsi.json`（自进化台账快照）；无 API、无模型调用、无真实实验。

## 启动

```bash
# 1) 生成任务数据（可重复执行；每条命令产出一个任务目录）
python -m research_agent pipeline run \
  --topic "钙钛矿 界面 钝化 稳定性" \
  --venue zh_core_journal --grant nsfc \
  --primary-metric "湿热稳定性" --control "未钝化对照" \
  --run-dataset iris --run-seeds 3 \
  --output-dir research_agent/web/data            # 根任务（README 默认工作流）

python -m research_agent pipeline run \
  --topic "How do self-improving coding agents use archives?" \
  --language en --venue en_conference --real-corpus \
  --output-dir research_agent/web/data/tasks/agent-archives

python -m research_agent pipeline run \
  --topic "ChemLab reaction conversion baseline" \
  --language en --venue en_conference \
  --run-dataset chemlab --run-seeds 3 \
  --output-dir research_agent/web/data/tasks/chemlab-baseline

# 2) 构建任务索引 + 自进化视图快照（只读，不修改台账）
python scripts/build-task-index.py
python scripts/export-rsi-view.py \
  --ledger research_agent/web/data/rsi-chemlab-v2/ledger.json \
  --output research_agent/web/data/rsi.json

# 3) 启动
python -m research_agent web --port 8010
# http://127.0.0.1:8010/
```

## 结构：任务 → 流程

- 左栏分两级：**TASKS 任务列表**（多任务切换，标记 FIX/REAL、venue/语言、是否有 S5 run / 基金轨）与 **PIPELINE 当前任务流程**（S1 文献 → S2–S3 假设 → S4 设计 → S5 复现执行（可选）→ S6 绘图 → S8–S12 论文/基金）。
- 选中任务后：顶栏显示 `TASK n/N · run_id`，主标题为任务 topic，eyebrow 显示 venue/语言，徽章显示 status / FIXTURE|REAL-TEXT / gates；所选任务记忆在浏览器本地。
- `总览 / 证据 / 稿件·基金 / 运行记录 / 自进化` 五个视图。
- **指令行（底部 ❯ 小框）**：全局按 `/` 聚焦；支持 `↑↓` 历史、`Tab` 补全、`Esc` 退出。指令全部本地静态执行，不触发任何 API：
  - `/task <n|关键字>` 切换任务（如 `/task 2`、`/task chem`）；`/tasks` 列出任务；
  - `/module <名称>` 选中模块（如 `/module run`、`/module 文献`）；
  - `/view <名称|1-5>` 切换视图（`overview evidence paper trace evolution`，支持中文别名）；
  - `/replay` 回放运行；`/model` 查看模型绑定；`/theme` 切换主题；`/help` 帮助。
- `⌘K` 或 `Ctrl K` 打开命令面板（任务 + 模块 + 动作）；`j/k` 切换模块；`1–5` 切换视图；`r` 回放。
- **浅色/深色主题**：顶栏 🌙/☀️ 按钮或 `/theme` 切换；首次访问跟随系统，选择记忆在本地。
- 移动端：任务 chips 与阶段条横向滚动、模块图横向滚动、SVG 横向滚动、指令行 sticky 固定底部（图保持可读尺寸）。

## 数据文件

| 文件 | 作用 | 生成方式 |
| --- | --- | --- |
| `data/tasks.json` | 任务索引（topic/venue/来源/是否有 run） | `python scripts/build-task-index.py` |
| `data/demo.json` + `data/tasks/*/demo.json` | 每个任务的模块产物、gates、warnings | `pipeline run --output-dir …` |
| `data/models.json` | 静态模型绑定（调研智能体 → GLM-5.3-Flash，未接 API） | 手工维护（静态设计） |
| `data/rsi.json` | 自进化回路台账快照（ledger + report） | `python scripts/export-rsi-view.py --ledger …` |
| `data/specs.json`、`figure.svg`、`run/` | 各任务模块规格/示意图/S5 产物 | `pipeline run` 自动写出 |

## 模型网关（接入任意 OpenAI / Anthropic / 兼容 API）

顶栏 🧠「模型」按钮、命令面板或指令行 `/model` 打开模型网关面板：

- **Providers**：OpenAI / Anthropic / 智谱 GLM / 本地 OpenAI 兼容端点（Azure 亦可配置）；每卡显示 key 状态（只显示 env 变量名与掩码，前端永远看不到 key 值）、base_url、模型菜单；
- **模块绑定**：默认 `literature → glm-flash（zhipu/glm-5.3-flash）`；思考模式 off/effort/budget 三种语义按 provider 翻译（OpenAI reasoning_effort、Anthropic thinking.budget_tokens、兼容端点 extra_body 透传）；
- **Live 探测**：面板可连本地 runtime（`python -m research_agent.runtime --port 8787`，默认 CORS 已放行 8010/8017），点击「探测实时状态」即从 `GET /api/models` 拉实时配置；未连接时展示 `data/gateway.json` 离线快照（`python scripts/export-gateway-snapshot.py` 生成）；
- **密钥边界**：key 只进环境变量（如 `ZHIPU_API_KEY`/`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`）或 runtime 内存 session key；配置落盘自动扫描并拒绝 secret 字段；错误信息自动脱敏。

设置任意一个 key 后，无需改代码：

```bash
export ZHIPU_API_KEY=...            # 或 OPENAI_API_KEY / ANTHROPIC_API_KEY
python -m research_agent pipeline run --topic "..." --openalex --run-dataset iris   --output-dir research_agent/web/data/tasks/live-demo   # S1 真检索 + GLM 子查询规划 + 本地 run
python scripts/build-task-index.py   # 任务进入左栏（REAL 标记）
```

无 key 时同一命令自动回退规则模板（stderr 说明），流程照常可跑。

## 自进化视图（RSI）

`自进化` 视图把治理回路可视化：观察 → 提案+dry-run → public 预筛 → hidden/near-OOD/regression → 人签准入 → Lease(scope+TTL) → 研究运行消费 → sealed 复核 → 归档/负结果。数据来自本地 RSI 控制面台账（`rsi status`），静态导出；浏览器只读，不提供 approve/claim/sign。

- 当前快照：S5 ChemLab seed-budget 台账（3 episodes：1 人签准入 + 2 拒绝保留，1 active lease，1 sealed 复核 confirmed，capability_claims=0）。
- `capability_claims=0` 是设计行为：harness-only / `claim_eligible=false` 的证据不生成能力主张。
- 调研智能体（S1）模型绑定 GLM-5.3-Flash 为**静态登记**（`modules/literature/SPEC.md` v0.1.6）；未接入 API，当前实现仍为本地 BM25/MiniLM。

### 2026-10-24 证据臂与 scope 改造

- 总览新增 **EVIDENCE ARMS**：S1 / S5 / S8 三臂分别显示模式、数值与 claim 状态；当 S1 是 fixture、S5 是真实本地 run 时，顶栏与面板标 **MIXED ARMS**，并明确“两臂不可合并读成一个结果”。
- 自进化视图新增 **LEDGER / SCOPE / THIS TASK / MATCH** 条：当前任务与台账 scope 不一致时，用红色 banner 标记“跨任务台账”，避免把 ChemLab 的 episode 读成当前任务结果。
- `claim_eligible`、`capability_claims`、claim 状态、paper claims 数、lease effective status 均从数据计算，不再硬编码。
- 移动端臂卡单列；1440/390 浏览器实测无 console error、无页面级横向溢出。

## 设计取舍

- 单屏应用壳：顶部任务上下文、左栏任务+流程、中心 canvas、右侧 inspector；
- 信息优先：任务 → 模块图 → 关键数字 → 模型绑定 → SVG → 证据/稿件/运行记录/自进化；
- 颜色只编码状态/模块类型，不做装饰性渐变；
- 图表由 AstraDraw scene→SVG，前端只展示，不重新绘制；
- inspector 在 ≤1180px 隐藏，避免把画布挤到不可读；后续可改为抽屉。

## 边界

- `data/*` 是 fixture / 静态快照；不是论文证据；
- `figure.svg` 是示意图，不是结果图；结果图只随 S5 run 生成并绑定 EA；
- 结果槽在没有人签 claim / ProtocolCard / DataCite 书目时保持 `pending_evidence`；全部槽位 bound 且 closure ready 才允许签署导出；
- 浏览器端没有 approve/claim/sign；人工门禁只能通过 CLI 完成。
