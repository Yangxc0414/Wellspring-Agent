# Research Agent Workspace (web)

静态优先、可部署的对话式科研工作台。生产入口在站点 `/app/`；三模式（调研 / 实验 / 全自动）、RUN / EVIDENCE / PROJECTS / EVOLUTION 上下文、claim 人工门、自进化候选与租约、运行中指导、模型设置、插件审批、页面字体缩放与各模型 token 用量均可用。左下角“设置与工具”打开全屏设置子页，内含使用统计（热力图 / 趋势 / 模型用量）与证据沿袭（变更影响 / stale propagation）。

TopBar 在静态构建下显示 `静态演示 · RUNTIME 已禁用`，并在顶栏下方给出模式说明；非静态构建才探测本地 `/api/health`，连上显示 `API · LOCAL`，否则显示 `演示数据 · 静态`。`API · LOCAL` 只代表 runtime 可达，不表示当前任务已执行；`/live <问题>` 或在 RUN 面板点“运行任务”才会提交真实本地 pipeline。页面不发起真实 MCP 连接，也不产生真实 claim。静态构建中 `/live` 会失败并提示需以非 static 模式重新构建，不会误报为“服务未启动”。

## 技术栈

- Vite 6 + React 19 + TypeScript（strict）
- Zustand（单一 store，actions 集中）
- 原生 CSS：tokens / base / layout / components / responsive 五层
- 无 UI 组件库、无图表库；图标为内联 SVG
- 按需加载：SettingsPage、弹窗与抽屉使用 `React.lazy`；vendor/主包拆分后约 287 KB main + 223 KB react-vendor

## 开发

```bash
npm ci
npm run dev        # http://127.0.0.1:5173
npm run typecheck
npm run test:unit  # node:test + type stripping；覆盖 runtimeLoop capsule 投影
npm run test:ui    # Playwright live smoke：启动 runtime+Vite，验证 loop/next actions/evolution/project experiments
npm run check      # typecheck + unit + build
npm run build      # dist/
npm run build:site # ../../site/app/（主站使用）
```

`vite.config.ts` 将 `/api` 代理到 `http://127.0.0.1:8787`，但当前 UI 不主动请求它。`VITE_SITE_BASE` 可覆盖子页面前缀（默认 `../`，适配 `/app/` 部署）。

## 目录

```text
src/
  adapters/     WorkspaceAdapter 契约 + localStorage 实现
  domain/       类型、种子数据、模式/阶段/模型/插件目录
  state/        Zustand store；自动运行、指导、审批、持久化
  components/   顶栏、侧栏、会话、上下文、浮层
    settings/   全屏设置页：常规 / 外观 / 模型 / 插件 / 自进化 / 使用统计 / 证据沿袭 / 数据 / 引导
  styles/       设计 tokens、工作台、设置页与响应式样式
```

数据流：`components → state/domain → adapters`。组件不直接访问 `localStorage`，domain 不引用 React。

## 关键边界

- `StaticWorkspaceAdapter` 是唯一的本地持久化入口，带版本/结构校验；刷新时把 auto runner 的 running/paused 归零。
- 自动运行由纯 reducer + `App.tsx` 外部 timer 驱动；到 S5b 的 claim 人工门必须暂停，签核后也必须由人点“继续”。
- 运行中普通输入进入 `Guidance` 队列，只在下一个阶段边界应用；不写 claim/EA/gate。
- 模型能力来自 `MODEL_PROFILES`：上下文/输出上限、思考档位（reasoning effort / thinking budget）均受模型声明约束；Anthropic budget 必须小于最大回复长度；密钥不进入浏览器。
- 字体缩放（90/100/110/120）通过 `--font-scale` 只调整文字，不改布局；设置持久化在 localStorage。设置页额外使用 `--settings-font-scale`（×1.15）。
- `usage` / `usageDays` 是按新增消息/卡片长度本地估算的各模型 token 用量与每日历史，不是真实 API usage；模型窗口、设置页与使用统计共同使用。
- “证据沿袭”页加载真实 closed-loop 快照 `public/lineage-demo.json`；模拟变更会把 dataset→run→claim→slots→closure→signature 传播为 stale，导出锁定。真实处置仍走 `python -m research_agent lineage impact` / closure CLI。
- MCP 工具结果必须逐次批准，且一律视为 `UNTRUSTED`；没有真实 transport。
- 导出是本地 JSON；重置会清空 localStorage 并恢复示例。

## 部署

仓库根目录的 `deploy/` 提供整套站点镜像：

```bash
docker compose -f deploy/docker-compose.yml up --build
# http://127.0.0.1:8080/app/
```

Nginx 把 `/api/` 代理到 `API_UPSTREAM`（默认 `host.docker.internal:8787`），并关闭 proxy buffering 以支持 SSE。GitHub Pages 的 `.github/workflows/pages.yml` 会先构建本应用，再发布 `site/`。

## 实时运行与数据面

- 欢迎页输入 `/live <研究问题>` 会创建干净标题的会话并提交本地 runtime；也可在会话 RUN 面板选择任务类型/来源/流程后点“运行任务”。
- runtime 事件通过 `/api/runs/{id}/events/stream`（SSE）实时进入会话卡片和 RUN 面板，轮询作为兜底；一次被中断的产物请求不会把已完成的运行改判为失败。
- runtime 任务的 RUN 面板显示真实 `job / route / flow / events`、runtime 返回的 gates 和事件 trace；不再用静态 9 阶段、`Q0 PASS` 或 `WAIT G1` 代替真实状态。9 阶段只作为完整研究目录，标出的完成数来自实际 `step_end/stage_end` 事件。
- 完成后从 `literature.json` 回填 span/gap 覆盖，并加载 `idea.json / experiment.json / paper.json / figure.manifest.json / claim-registry.json / loop-capsule.json`，在 EVIDENCE 页显示真实 RESEARCH LOOP（S1→META）与 blockers / next actions；缺失节点不显示为通过。
- EVIDENCE 与独立 PROJECTS 页签均只读展示项目实验链：通过 `/api/projects` 与 `/api/project-experiments` 列出项目内多个 `experiments/<EXP-ID>`，显示 evidence/claim/closure/signature 的真实阶段和 next_action；执行与签核仍只在 CLI/人工流程，不在浏览器发生。
- EVIDENCE 页显示 G1 SHORTLIST：rank/evidence/source/prior-art scope/novelty status/testability/kill criteria/cross-source contrast；只作 advisory，selection 固定为 `human_g1`，不自动收敛。
- EVIDENCE 页的 META 行显示本 job 实际消费的 active policy 与 S5 lease（policy_id / lease_id / seeds）；观测不是证据，activation 仍只走 CLI 人审。
- EVOLUTION 页在存在 sealed confirmation 时显示 `CONFIRMATION / DELTA`（mean_score/cost 等配对变化），并明确它只是审计记录，不是能力结论或自动准入。
- 写作槽位会显示 `external_lint`/`external_consistency` 的状态与 issue 数；两者只是外部只读检查，不是本仓库证据、Claim 或签名。
- `idea.json` 的 `prior_art_scope`、`contrast_refs`、`shortlist` 会显示在编排总览与证据链 note；它们不是 novelty 证明。
- EVOLUTION 页读取真实 `/api/evolution/observations` 与 `/api/evolution/active`，显示 observation、active policy 与 CLI 人工闭环命令；下方 `LOCAL DEMO CANDIDATE`（标注「演示数据」）与真实账本分开。

## 已知限制

- Composer 的模型选择仍是本地 `MODEL_PROFILES`（例如 GPT-5），不随 `/api/models` 自动切换；真实模块绑定与 key 在“设置 → 模型设置”。runtime 任务的顶部 chip 显示实际 `route`，不再冒充模型选择。
- 未接真实 MCP transport；Web 用本地 HTTP runtime，Qoder 走 MCP，两者不是同一个客户端。
- RUN 面板的严格流程续跑输入仍是文件路径；人工门不会搬进浏览器。
- 旧 `site/agent/` 是 legacy 单文件版本，已不再从主站入口链接。
- 仅为单浏览器本地状态；没有多用户、鉴权或并发写入协调。
- 详细架构与验证记录见 [`35-前端工程化架构-可部署的对话式科研工作台.md`](../../35-前端工程化架构-可部署的对话式科研工作台.md)；逐页截图与交互逻辑审计见 [`37-前端全量体验审计-截图与交互逻辑.md`](../../37-前端全量体验审计-截图与交互逻辑.md)。
