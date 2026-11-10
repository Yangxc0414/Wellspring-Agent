# Research Agent · 静态站点

> **定位（2026-11-11）：本仓库（research-agent）是早期 demo / 静态展示项目；智能体产品本体在 [Wellspring-Agent](https://github.com/Yangxc0414/Wellspring-Agent)（打开前端即工作台 + CLI + MCP），开发一律以产品仓库定位为准。**
>
> **2026-10-24 起，主工作台迁移为 `site/app/`**：源码在 `apps/web/`（Vite + React + TypeScript），
> 单页会话、RUN/EVIDENCE/EVOLUTION、模型/插件/指导、字体缩放、各模型 Token 用量、全屏设置与使用统计（热力图/趋势/模型用量）、证据沿袭（变更影响/stale propagation）与受治理全自动均在新应用内；`site/agent/`
> 是旧版单文件实现，仅保留历史链接。构建：`cd apps/web && npm run build:site`。
> 整套站点可用 `docker compose -f deploy/docker-compose.yml up --build` 部署（Nginx + `/api` 代理）。

这是项目的 GitHub Pages 站点，采用**单屏应用壳**：顶部状态栏 + 左侧工作区导航 + 右侧活动视图；工作台主入口是 **`site/app/`**（源码 `apps/web/`，静态三模式：调研/实验/全自动；全自动在 claim 人工门暂停；自进化候选/租约/回滚；不接 API），可从顶栏或侧栏“Agent 工作台”进入；旧版 `site/agent/` 仅保留历史链接。桌面端页面本身不滚动，首次加载先显示 boot，再按次序浮现 appbar、侧栏、标题与面板；默认打开“接入项目”。接入页包含 **REPORT PREVIEW** 空态、只读扫描三段式进度、readiness 计数环、结构统计、可复现缺口与可点击候选方向；支持本地文件夹（只读文件名/大小）、GitHub 公开元数据或示例仓库，再进入研究运行。顶部“演示模式”隐藏全部外壳、让运行台直接铺满，按 `Esc` 退出。工作区包括研究运行（对象流 + 指令流；子步骤推进，阶段卡可翻页/自动跟随）、证据工作台、自进化、功能地图、证据链、变更回放、多智能体、技能运行时、真实检索、部署与文档。Demo 由 `demo/index.html?embed=console|workbench|evolution` 提供，左侧工作区按钮控制 iframe 模式；演示页头部按模式显示 RUN CONSOLE / EVIDENCE WORKBENCH / SELF-EVOLUTION 与对应强调色，skill runtime 默认折叠。目标地址为 **https://yangxc0414.github.io/research-agent/**。

`site/qoder/` 是**接入矩阵**（不是 Qoder 专属页，路径沿用旧地址）：Qoder / Claude Code / Cursor / Cline / Codex CLI / Zed / Continue / 自建脚本共用同一份 `tools/list`；页面只给配置与边界，不发起真实连接。

`site/rsi/` 是**自进化接缝**（地址 **https://yangxc0414.github.io/research-agent/rsi/**）：递归改进的执行交给外部 Harness²，平台只保留数据基础、准入判据、台账与人签。页面读 `site/data/harness2.json`（由 `build-site.mjs` 从 `runtime_data/harness2/story.json` 同步），显示一次真实运行的预算恒等式（R=4k / P=3k）、c1..c8 组件面计数、去重后的采纳 diff、留出检查与 10 项 conformance 自检。没有产物时页面显式留空，不填默认数字；确定性夹具运行强制 `simulation=true`、`claim_eligible=false`。

同页的 **GENERATIONS** 区块做「对自进化本身做版本管理」：agent 轨记采纳树 SHA 与 episode，platform 轨记 `research_agent/**/*.py` 的指纹与提交，两条链由 `platform_fingerprint` 关联；数据读 `site/data/evolution.json`（由 `build-site.mjs` 从 `runtime_data/evolution/story.json` 同步）。平台变更后，旧 harness 世代会在这里被点名要求复验，但页面不提供任何回退/签核按钮。

新增 **创新点演示**：`site/innovation/`，地址 **https://yangxc0414.github.io/research-agent/innovation/**。它是纯静态、无 API 的七幕舞台：SPEC 契约 → span/coverage → AstraDraw SVG audit → 论文/基金 pending 槽 → 可宣称边界 → 度量有效性（64 种子预注册扩样）→ 判定消费（五类反馈对照，Q2）；数据来自 `research_agent/web/data` 的 fixture，构建时由 `build-site.mjs` 同步到 `site/innovation/data`。单屏舞台、自动播放/手动切幕、全屏演示模式（每幕 15 秒，共 105 秒）；读图约定与主页一致：实线 = 前向、虚线 = 反馈回指且改变下一步动作、红 = 人工门、青 = 自动门。不包含真实检索或实验结果。

版式参考 `yangxc0414.github.io/agent-memory-push` 的宋体大标题、等宽标签、淡蓝网格与细线排版；`assets/base.css` / `theme.css` 是参考页的公开样式底座，`assets/custom.css` 是 research-agent 自有组件与响应式覆盖。研究台使用双环 HUD、阶段轨完成勾/进度条、增量对象流与 PENDING 占位、指令分组筛选、卡组圆点/锁定页/方向翻页、逐阶段记忆计数与 +Δ；新增 **聚焦视图**（收起日志、一屏显示对象流/阶段卡/当前指令，站点演示模式自动开启）、**阶段封印**（P·gate·SEALED）、对象节点光环与当前指令同步脉冲，以及可展开 **STAGE CONTRACT**（S 段/门禁、服务/端口、artifact 链、硬不变量、失败路由、PF-P0–P8 过程协议、角色与 SIM 限制）。移动端阶段轨横向滚动并做边缘渐隐，翻页器保持单行。所有 `SIM` 标注保留；`prefers-reduced-motion` 与无 JS 场景均可用。

## 本地 Live Runtime

`site/live/` 是唯一会真实调用本地 Python 的页面：连接 `http://127.0.0.1:8787`，
提交真实 pipeline，接收 SSE 阶段/指令事件，预览 `demo.json`/`paper.json`/
`figure.svg` 等产物，并读取只读 RSI status/trace。启动：

```bash
python -m research_agent.runtime --port 8787
python -m http.server 8000 --directory site
# http://127.0.0.1:8000/live/
```

前端没有 approve/claim/sign 按钮；人工门禁仍在 CLI。GitHub Pages 不能运行
Python，且 HTTPS 页面调用本地 HTTP 会被 mixed content 拦截；Pages 上的 live
页只会在连接失败时显示启动说明。runtime 文档见
[`research_agent/runtime/README.md`](../research_agent/runtime/README.md)。

## 本地模型接入

`site/models/` 是模型网关页，必须配合本地 runtime 使用：

```bash
python -m research_agent.runtime --port 8787
python -m http.server 8000 --directory site
# http://127.0.0.1:8000/models/
```

支持 OpenAI / Anthropic / Azure OpenAI / OpenAI-compatible；密钥只从环境变量或
runtime session 内存读取，不写仓库、不回传浏览器。页面可配置 Provider、
ModelProfile（含 thinking/max_tokens/extra_body）、模块 Binding，并发一条真实
Probe 查看文本/usage/latency；调用日志不含 prompt/response/key。当前只有
`rsi` 是 WIRED，其他模块标 CONFIG ONLY；接入 API 不等于 pipeline 已使用模型。
设计与威胁模型见 [`29-多模型接入-OpenAI-Anthropic-API密钥与思考参数设计.md`](../29-多模型接入-OpenAI-Anthropic-API密钥与思考参数设计.md)。

## 本地预览

在仓库根目录：

```bash
cd apps/web && npm ci && npm run build:site && cd ../..
node scripts/build-site.mjs
npx serve site
# 或
python -m http.server 8000 --directory site
```

打开 `http://localhost:8000/`，工作台在 `http://localhost:8000/app/`。

## 部署到 GitHub Pages

1. 将仓库推送到 GitHub，仓库名设为 `research-agent`，默认分支为 `main`。
2. 仓库 Settings → Pages → Source 选择 **GitHub Actions**。
3. 推送 `site/`、`demo/` 或手动运行 **Deploy site to GitHub Pages** 工作流。
4. 站点地址为 **https://yangxc0414.github.io/research-agent/**。

`build-site.mjs` 会把 `demo/index.html` 复制到 `site/demo/index.html`，把 `research_agent/web/data` 同步到 `site/innovation/data`，并把关键设计文档复制到 `site/docs/`；不要直接编辑复制产物。`19–26` 中的内部调研/实现设计文档不随 Pages 发布，只在仓库内作为推进依据。

## 数据与模式

- `LIVE PUBLIC`：仅指 lab 页浏览器直连 OpenAlex 公共 API；只取公开元数据，不调用 LLM，不代表整套流水线在线。
- `CACHED`：`site/data/digest.json`，由 `refresh-digest.yml` 定时生成，或人工快照。当前线上文件是 2026-10-23 的手工快照，不是定时任务的实时产物；精确计数只反映 OpenAlex 当时的索引状态，不是本研究结论。
- `SIM`：研究运行、证据工作台、自进化与技能状态均为交互演示，不是实测结果；动效由阶段/对象/租约状态驱动，不做无含义装饰。
- `STATIC`（主入口 `/app/`）：`vite build --mode static` 产物，构建期注入 `__STATIC_ONLY__`，`runtimeApi.request()` 直接抛错，所有数据回退到随包分发的 `site/app/*.json` 快照。工作台顶部有可见的静态模式说明条。
- 人工门：G1 / G2 / claim / closure / export 只在本地 CLI；本站与工作台都没有 sign / approve / freeze / publish 入口。页面里的「已签署」文案来自打包快照，不是本站产生的签名。

`refresh-digest.yml` 默认每天 01:17 UTC 运行，读取 `site/data/queries.json`，写入 `site/data/digest.json` 并提交；但**前端镜像仓库尚未启用该工作流**（见 `43-GitHub-Pages部署与前端镜像.md:105`），线上仍是手工 CACHED 快照。

**镜像漂移提醒**：`site/app/` 是构建产物，不是源码。修改过 `apps/web/` 后必须重跑 `npm run build:site` 与 `node scripts/build-site.mjs`，否则 Pages 上仍是旧 bundle —— `43-…md:99` 已记录这个问题。部署前用 `node scripts/check-site.mjs` 确认静态模式与本地资源引用。

## 安全边界

- 不要把 API key、token、私有稿件写入本站或仓库。
- Pages 不能运行服务端代码、Docker、数据库或长任务；需要实时 LLM/沙箱时，启动本地或边缘运行时。
- 不抓取知网/万方/维普，不使用未授权全文。
- 所有 AI 生成内容都是草稿；科学决策、实验安全、署名与最终责任由作者/PI 保留。
