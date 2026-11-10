# 生产就绪度评估（2026-11-10）

> 本文是对“Wellspring-Agent 是否是可完整运行的生产级实现”的实测回答，不是宣传页。
> 每条结论都标注了验证方式；没有实测的地方明确写“未实测”。

## 1. 结论

**三端都能真实运行，但“生产级”要按它的真实定位读：单用户、本地优先、以证据治理为核心的科研运行时——不是多租户 SaaS。**

| 层 | 可运行 | 证据 | 定位 |
| --- | --- | --- | --- |
| CLI | ✅ | 41 组 / 205 条命令；`python -m research_agent.cli --help` 全部列出；本轮实跑 `rsi harness2 run`（R=48/48、P=36/36）、`rsi gen snapshot/verify`、`plugin export` | 主入口；四道人签门（G1/G2/S5b/G5）只在这里 |
| 后端 | ✅ | `python -m research_agent.runtime` 起 FastAPI，`/api/health`、`/api/rsi/generations`、`/api/research/capabilities` 实测 200 | 本地 localhost（默认拒绝远程绑定），60+ 只读/作业端点 + SSE |
| MCP | ✅ | stdio 冒烟：`initialize` → serverInfo 0.48.0，`tools/list` = 46，**签名类工具 = 0** | 供 Qoder / Codex / Zcode / WorkBuddy 等接入 |
| 前端 | ✅（混合） | `site/app` Vite/React/TS 构建产物可用；核心工作区走本地状态（SIM），治理/RSI/用量面板连本地 runtime | 展示 + 只读治理面板；不是完整的前端后端闭环 |

运行时 `/api/health` 自报 `"production_ready": false, "research_mode": "test"`——这个字段是诚实的：它指“模式为 test/本地”，不指“代码不能跑”。

## 2. 接口衔接与数据流（实测一致）

- **单一 dispatch**：MCP、HTTP JSON、Python SDK 共用 `framework_api.dispatch` 与 `mcp_tools.TOOLS`（46 条）；工具表是数据不是分支，MCP 侧无业务逻辑副本。
- **签名边界成立**：46 个工具名里 grep `sign|approve|freeze|publish|export` = 0；`venue_audit` 对空模板返回 blocked。
- **版本指纹贯穿**：`paths.build_fingerprint()` 出现在 `handoff contract`、capabilities、RSI episode（`platform_fingerprint`）、Harness² 产物与世代台账——宿主“读到的服务是不是当前代码”一次比较可判定。
- **两个台账同构**：RSI `StepLedger` 与世代 `GenerationStore` 都是 append-only + SHA-256 哈希链事件，`verify_events()` 可检测篡改。
- **模块 SPEC → 代码**：`python -m research_agent workspace export` 把 26 个模块的版本/状态导出成注册表，前端与站点读同一份，不会各说各话。

## 3. 前端评估

**合理的部分**：Vite/React/TS 分层（`state/`、`adapters/`、`components/`）；workspace 快照走 `staticAdapter`（localStorage 持久化）；`runtimeApi` 面板（Artifact / Context / Governance / RSI / UsageStats / Settings）与本地 runtime 对接；构建产物可直接部署到 Pages，无后端也能演示；移动端与对比度做过实测修复。

**缺口**：
1. **适配器切换是构建期**（`import.meta.env.VITE_RUNTIME_URL`）：同一份构建产物无法在“演示模式 / 连本机 runtime”之间切换，要连后端必须重新 build。
2. **两套数据模型并存**：workspace 主流程（RUN/EVIDENCE/EVOLUTION 的对象流）是前端状态机，runtime 的 `/api/runs` 是另一条真实执行链；两者没有打通成“前端发起 → 后端执行 → 前端展示同一条 run”。
3. Pages 上实时面板必然 `ERR_CONNECTION_REFUSED`（无后端），UI 已 catch 并显示 OFFLINE——诚实，但首次使用者会困惑。

## 4. 后端评估

**合理的部分**：FastAPI 应用 1090 行、60+ 端点；JobManager 落盘 + SSE 事件流；RSI 只读面（story/trace/generations）与 CLI 语义一致；`--allow-remote` 默认拒绝、token 可选；自报 `production_ready` 不装样子。

**缺口**：
1. 存储 = JSON 文件 + append-only 日志：可审计、可 diff，但无并发/事务/多项目隔离；单用户是前提，不是缺陷陈述。
2. 作业在进程内执行：runtime 重启丢队列（jobs 目录可恢复已落盘状态，但进行中的任务会中断）。
3. 无鉴权默认关闭（localhost 假设正确，但 `--allow-remote` + 无 token 的组合只靠文档约束）。
4. 模型密钥只进内存/环境变量（好），但网关调用无配额/熔断。

## 5. 可运行性缺口与风险（分级）

**P0（发布阻断）**
- 根 `LICENSE` 未选定：`release_check.py --for-public-release` 会直接阻断；Harness²（Apache-2.0）已 vendored，本仓库自己的许可证必须先定。
- `research_agent/vendor/astradraw` 本地 200MB、上游无 LICENSE：发布树已排除（DENY），但意味着“换一台机器渲染方法示意图”不可复现，需在文档中持续声明。

**P1（功能完整度）**
- 双解释器：平台 3.8 / Harness² 3.12–3.13。桥已隔离进程并显式声明 Windows 补丁，但部署文档必须写清两个 Python 的要求。
- MCP 只有 stdio 主路径；远程 host（浏览器插件、云端 agent）需要 Streamable HTTP 传输，目前未实现。
- `site/app` 实时面板在 Pages 上离线：需要“同域部署 runtime + 反代”的部署形态（`deploy/docker-compose.yml` 存在但未实测）。

**P2（打磨）**
- 前端 i18n / 无障碍深审 / `prefers-reduced-motion` 全覆盖复核。
- CLI 输出机器可读性不统一（部分表格式、部分 JSON）。
- 测试 1377 例全绿，但 E2E（前端点击 → 后端 run → 前端读回）缺一条。

## 6. 改进建议（按优先级）

1. **前端运行时开关**：`Settings` 增加 “Runtime URL” 输入（存 localStorage），`runtimeApi` 优先读它、`VITE_RUNTIME_URL` 作默认——一次构建同时服务演示与本地真跑。
2. **打通一条真实纵切**：工作台“新建任务”在检测到本机 runtime 时改调 `POST /api/runs`，复用现有 SSE 面板；这是从 demo 到产品的最短一跳。
3. **MCP Streamable HTTP**：在 `runtime/app.py` 挂 `/mcp` 端点复用 `ResearchMCPService`，让浏览器/云端 host 无需本地 Python。
4. **CI 部署 runtime**：docker compose 实测一轮（含 `--allow-remote` + token），把“能跑”变成“可部署”。
5. **LICENSE 决策**：先定本仓库许可证，再谈公开发布；`release_check --for-public-release` 已把规则写好。
6. **数据层**：把 `StepLedger`/`GenerationStore` 的 JSON 换成 SQLite（保留哈希链导出），解决并发与断电一致性；审计格式不变。

## 7. 可以对外说的 / 不能说的

**可以**：三端可运行且接口单一；46 工具零签名入口；证据/治理/版本管理有哈希链与指纹；确定性夹具下的自进化接缝与双轨世代台账真实跑通。
**不能**：多用户/公网服务；“越跑越强”的能力声明（夹具是 `simulation=true`）；与 RSI 基础设施已完成对接（执行在 Harness²，外部 RSI 服务是 roadmap）。
