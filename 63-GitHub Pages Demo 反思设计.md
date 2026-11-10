# 63 GitHub Pages Demo 反思设计

> 状态：2026-11-05。性质：**只读事实审计 + 一轮已落地的 demo 修改与重建**。
> 对象：`https://yangxc0414.github.io/research-agent/` —— 由 `.github/workflows/pages.yml` 部署 `site/` 的静态前端镜像。
> 证据纪律：每个判断带可核对的文件与行号；未核实的标「未核实」；不把静态快照、SIM 数字或旧文档措辞写成已上线能力。
> 与 `62-` 的关系：`62-` 对照的是期刊 skills 基准，本文对照的是**自己的公开演示**；两篇共用同一条底线 —— 不把机制存在写成结论已产出。

---

## 0. 结论摘要

1. **线上 demo 是静态前端镜像，不是科研运行时**。作者自己在 `43-GitHub-Pages部署与前端镜像.md:103,118-120` 与 `README.md:392-400` 已明确这一点；但界面上仍有几处会让访问者高估「真实可用程度」。
2. **本轮最硬的工程问题不是设计，而是镜像漂移**：`site/app/` 是旧一次 `build:site` 的产物（`agent-registry.json` public 71,039 B / site/app 66,794 B，`command-catalog.json` 91,219 / 84,519），也就是说上一轮所有前端改进**根本没进 Pages 包**。`43-…md:99` 早已记录这个风险。本轮重建后 9 个 JSON 逐字节一致。
3. **反思的核心判断**：公开演示的价值是「把机制讲清楚」，不是「把系统演得像已上线」。因此设计目标是**让边界比能力更显眼**：顶栏口径、快照来源、人工门位置、本地 runtime 依赖都必须在首屏可见。
4. **本轮修改**：4 个源文件（`site/index.html`、`site/assets/app.js`、`site/README.md`、`pages.yml`）+ 重新生成的 `site/app/`、`site/demo/`、`site/docs/`、`site/innovation/data/`、`site/data/build.json` + 发布树同步。验证：站点静态校验通过、前端 `npm run check` 通过、43 项 Python 护栏 OK、发布树零漂移。
5. **与底层闭环的呼应**：`58-:6248,6294` 记录「已签确证 claim = 0」，本轮实测 192 份 `closure-report.json` 中 174 blocked、**0 份带 `human_reason`**，`pipeline.py:1081` 的 G5 仍是硬编码字符串。既然主仓库的闭环都没走完，公开 demo 更不应该呈现「已上线运行」的观感。

---

## 1. demo 到底是什么（可确认事实）

### 1.1 部署链

| 环节 | 事实 | 来源 |
| --- | --- | --- |
| 触发 | `push` / `pull_request`（`main`）+ `workflow_dispatch`，带 `paths` 白名单 | `.github/workflows/pages.yml:3-28` |
| 构建工作台 | `working-directory: apps/web` → `npm ci` → `npm run typecheck` → `npm run build:site` | `pages.yml:55-59` |
| 静态注入 | `vite build --mode static --outDir ../../site/app --emptyOutDir`，`vite.config.ts:12` 把 `__STATIC_ONLY__` 编译为 `true` | `apps/web/package.json:11`、`vite.config.ts:10-13` |
| 组装站点 | `node scripts/build-site.mjs` → 复制 `demo/index.html`、4 份文档、innovation 数据，写 `site/data/build.json` | `pages.yml:61-62`、`scripts/build-site.mjs:16-24,26-45,47-72,88-100` |
| 校验 | `node scripts/check-site.mjs`：必需文件、`./assets/` 引用存在、至少 1 个 JS、bundle 含 `"runtime disabled in static build"`、`./app/` 链接、`favicon` | `pages.yml:64-65`、`scripts/check-site.mjs:15-49` |
| 部署 | `actions/upload-pages-artifact@v3` `path: site` → `deploy-pages@v4`；PR 只 build/check 不部署 | `pages.yml:68-88` |
| 域名 | 无 CNAME，用 `github.io` 子路径 | `43-…md:107`；`find site -iname CNAME` 为空 |

### 1.2 站点构成

`site/` 约 63 个文件，混着**三类东西**：
- **主入口**：`site/app/`（Vite 生成的 React SPA，`site/app/index.html:13-16` 引用 hash 化 assets + 9 个 JSON）。
- **手写静态页**：`site/index.html`（56 KB 落地页，13 项功能地图、lab 实时检索、案例回放、拓扑、部署三平面）、`site/innovation/`、`site/live/`、`site/models/`、`site/qoder/`、旧版单页 `site/demo/index.html`（491 KB）、LEGACY `site/agent/`。
- **数据/文档副本**：`site/data/{build,digest,queries}.json`、`site/docs/`（4 份 Markdown 原文副本，`README.md:400` 明确「未做站内渲染」）、`.nojekyll`、`404.html`、`manifest.webmanifest`。

### 1.3 静态构建下的数据来源（关键）

- `runtimeApi.ts:644` `request()` 首行 `if (__STATIC_ONLY__) throw new Error("runtime disabled in static build")`，**不发 fetch**；`hostModelApi.ts:62` 同款。
- `liveThenSnapshot()`（`:676-682`）恒回退到 `snapshot(file)`，即 Vite 从 `apps/web/public/` 拷进 `site/app/` 的 9 个 JSON。走此路径的只有 7 处（`loadAgents / loadCommands / loadOrchestrationTopology / loadLiteratureMemory / loadCustomAgents / loadEvolutionPolicy / fetchRsiStory`），`loadOrchestrationRun` 直接读快照。
- **其余大量函数**（`probeRuntime`、`createRun`、`loadRuns`、`loadProjects`、`loadModelCalls`、`loadRunEvents`、`createRuntimeMemory` 等，`:684-1103`）**直接调 `request()` 没有回退**，静态模式下抛错。`43-…md:41` 的「设置、技能、子智能体、证据沿袭等页面都走快照/本地状态」是概括描述，代码层并不完全成立。
- 9 个 JSON 的 `source` 口径不统一：`orchestration-topology.json:6` 标 `fixture`，`orchestration-run.json:5-6` 标 `real` + `fixture_mode:false`，`lineage-demo.json:2` 标 `closed-loop CheMLab (real local artifacts)`；但它们都是**构建期打包的本地快照**，线上没有任何 runtime 重新生成。
- lab 页确实直连 OpenAlex（`site/assets/app.js:367-371`），而 digest 面板读的是 `site/data/digest.json`（`:758`）—— 后者是 `generated_at 2026-10-23` / `mode CACHED` 的手工快照（`:2,4`），`43-…md:105` 与 `README.md:400` 都说明 `refresh-digest.yml` 在镜像仓库尚未启用。

---

## 2. 设计判断：公开演示应守的三条边界

1. **边界比能力更显眼**。访问者第一屏就该知道「这是静态原型、runtime 已禁用、人工门在 CLI」，而不是从 README 里找。原 demo 把免责写在 `43-…md:103` 与 `site/README.md:79-84`，主入口 `/app/` 只有不可见的 meta description。
2. **数字必须带来源与时效**。CACHED 快照的 `total_hits: 17141`、`cited_by: 3074` 是真实公开元数据，但既非本项目产出也非实时；与 `source: "real"`、`「已人工签署」` 文案并置时，容易被读成「系统已验证的结论」。
3. **失败要能被解释**。`/live/`、`/models/` 在 Pages 上必然连不上（`site/README.md:26-28`、`43-…md:104`），若入口只写 `LIVE / 真实 pipeline`，用户会把设计边界当成故障。

---

## 3. 六维反思（现状 → 判断 → 本轮处理）

### 3.1 定位与叙事

**现状**：`site/index.html:63` 顶栏 `<i class="dot dot-live"></i>LIVE PUBLIC`、`:70` `LIVE RUN · SIM`、`:112` `LIVE PUBLIC 公开检索`、`:127` 功能行 `LIVE PUBLIC` badge；同时 `:113` 有 `SIM / 未运行`、多个 `SIM` badge。**两套口径并存**，且最显眼的顶栏用了「LIVE」。
**判断**：`LIVE PUBLIC` 在设计里只指「浏览器直连 OpenAlex 公共元数据」，把这个局部事实放在全局顶栏，会让首屏读者推断「整套流水线在线」。而 `43-…md:103` 明确线上没有真实 LLM、工具执行、claim 签名、runtime job。
**本轮处理**：顶栏改为 `PUBLIC · STATIC` 并加 `title` 说明；演示模式水印 `LIVE RUN · SIM` → `STATIC DEMO · SIM`；新增首屏可见的 `site-mode-banner`，一句话讲清四件事（静态镜像 / runtime 禁用 / 数值来自 CACHED 或 SIM / 人工门只在 CLI），并解释 `LIVE PUBLIC` 的确切含义。lab 区 `:421`「浏览器会直接请求 OpenAlex」经核实为真（`app.js:367`），**保留不改**。

### 3.2 页面结构与信息架构

**现状**：三套工作台并存 —— `site/app/`（React SPA，主入口）、`site/agent/`（LEGACY 单文件工作台，`site/README.md:4-5`）、`site/demo/`（491 KB 旧单页，首页 `:65` 仍有「全屏打开」链接指向它）；另有 `innovation/ live/ models/ qoder/` 五个独立静态页；`site/docs/` 是未渲染的 Markdown 原文。
**判断**：入口重复、代际混杂，访问者难以判断「哪个是当前工作台」。这属于**历史累积**，不是本轮能一次性收敛的（会涉及删除/重定向多个页面）。
**本轮处理**：不删页面（避免破坏引用），但在 `site/README.md` 明确 `STATIC` 主入口是 `/app/` 并写明镜像漂移与重建命令；把 `/live/`、`/models/` 两个入口的标签从 `LIVE` / 「Provider / Profile」改为 `LOCAL` / 「需本地 runtime · Pages 上不可用」，让「点进去会失败」在点击前就可见。
**未改项（建议）**：后续把 `site/agent/` 与 `site/demo/` 收敛为 `/app/` 的归档链接，给 `site/docs/` 做站内渲染或换成外链；这需要单独一轮，不是「修文案」能解决的。

### 3.3 数据来源披露

**现状**：digest 面板（`app.js:765-778`）展示 `generated_at / queries / works / source` 与每条 `total_hits / returned`，但**不展示 `mode: CACHED`**；`:780` 的空态文案写「启用 refresh-digest.yml 后，这里会出现带时间戳的公开检索结果」，而文件本身已带时间戳，容易读成实时产物。首页 `:476` badge 是 `CACHED / LIVE`，把两种模式混在一个标签里。
**判断**：精确计数 + 时间戳 + 无 `CACHED` 标记 = 最容易被误读为「本项目实时检索成果」的组合。
**本轮处理**：`app.js:775` 的 meta 增加 `mode: <digest.mode>`，并在结果前插入一条明确说明「随站点打包的公开元数据快照，不是实时检索，也不是本研究产出的结论；精确计数只反映 OpenAlex 当时的索引状态」；首页 badge `CACHED / LIVE` → `CACHED SNAPSHOT`；`site/README.md` 补上「线上 digest 是 2026-10-23 手工快照、镜像仓库未启用定时刷新」。

### 3.4 交互可信度与人工门

**现状**：人工门声明只出现在深层页 —— `site/qoder/index.html:210`、`site/live/index.html:214`、`site/README.md:26`，以及代码里的 `gateCommands.ts:4-6,11`；首页/工作台主界面没有直白说明。工作台快照里还有 `ArtifactCard.tsx:222`「已人工签署（证据来自 CLI）」这类文案。
**判断**：`43-…md:103` 说线上没有 claim 签名，但界面里出现「已签署」字样而**无就近声明**，是语义冲突。
**本轮处理**：新增的 `site-mode-banner` 把「G1 / G2 / claim / closure / export 只在本地 CLI」放到首屏；`site/README.md` 增补「页面里的『已签署』文案来自打包快照，不是本站产生的签名」。
**未改项**：`apps/web/public/*.json` 里 `source: "real"` 与 `fixture_mode: false` 的口径属于**后端导出快照的字段语义**，改它会触碰导出不变量，按 `AGENTS.md:60` 需人工确认，本轮不动，只在报告中登记。

### 3.5 资源加载与镜像漂移（本轮最实质的修复）

**现状（重建前）**：`site/app/` 是旧构建产物：`agent-registry.json` public 71,039 B vs site/app 66,794 B、`command-catalog.json` 91,219 vs 84,519；`site/app/index.html` 引用的仍是上一代 hash 化 assets。也就是说 `62-` 报告与本轮之前新增的 `AppErrorBoundary`、`StaticModeNotice`、`SourcePill`、`disclosures.css`、`/live` 命令、兜底数字修正**全部没有进 Pages 包**。
**判断**：这是工程链条问题，不是设计问题 —— `build:site` 只在 CI 里跑，本地改完前端若不手动重跑，主仓库的 `site/app/` 会长期滞后。`pages.yml` 的 `paths` 白名单还漏了 `README.md`（`build-site.mjs:29` 会复制它）、`scripts/refresh-digest.mjs`、`.github/workflows/refresh-digest.yml`，改这些不会触发重新部署。
**本轮处理**：
- 重跑 `npm run build:site` → `node scripts/build-site.mjs` → `node scripts/check-site.mjs`；
- 哈希核对 `apps/web/public/*.json` 与 `site/app/*.json`：**9 个全部一致，漂移归零**；
- bundle 中确认同时含 `"runtime disabled in static build"` 与「静态演示模式」字样；
- `pages.yml` 的 push / PR `paths` 各补 3 项（`README.md`、`scripts/refresh-digest.mjs`、`.github/workflows/refresh-digest.yml`）。

### 3.6 与真实 runtime 的边界（呼应「闭环是否跑通」）

**现状**：静态构建在编译期禁用 runtime；`/live/`、`/models/` 页需要本地 Python，HTTPS 页面调本地 HTTP 还会被 mixed content 拦截（`site/README.md:26-28`）。
**更深一层的事实**（本轮实测）：主仓库里 221 个 claim-like 文件中 42 个 `status: supported`，但 `human_reason` 全是 `[delegated:autopilot] …` 或 `benchmark reviewed EA`，且 statement 都是同一句 iris fixture（`mean accuracy 0.956 over seeds [17,18,19]`）；192 份 `closure-report.json` 中 174 `blocked`、17 `ready`、1 `ready_for_human_signature`，**0 份带 `human_reason`**；`pipeline.py:1081` 的 G5 仍是硬编码 `"no EA/Closure; export is closed"`；`jobs.py:116,843` 默认 test 模式 + `FixtureRetriever()`。
**判断**：主仓库的**机制层**跑通了（1239 项测试 OK、46 工具、CLI/MCP/SSE、发布树、WorkBuddy 接入），但**闭环层**没通：closure sign 从未发生、确证 claim = 0、导出恒锁定。在这个前提下，公开 demo 若呈现「LIVE / 已签署 / 精确计数」，不仅是界面误导，还会与仓库自身的诚实口径（`ARCHITECTURE.md:400-415`）冲突。本轮的口径收敛正是为了消除这个冲突。
**本轮处理**：不改后端逻辑（闭环是设计决定与人工签核问题，不是前端能修的），只把 demo 的叙事拉回与事实一致。

---

## 4. 本轮修改清单

| 文件 | 改动 | 维度 |
| --- | --- | --- |
| `site/index.html` | 新增 `site-mode-banner` 样式与首屏说明条；顶栏 `LIVE PUBLIC` → `PUBLIC · STATIC`（带 title）；演示水印 → `STATIC DEMO · SIM`；`/live/` 与 `/models/` 入口标注「需本地 runtime」；`CACHED / LIVE` → `CACHED SNAPSHOT` | 定位叙事 / 信息架构 / 交互可信度 |
| `site/assets/app.js` | digest 面板 meta 增加 `mode`，并在结果前加「构建期快照、非实时、非本研究结论」说明 | 数据来源披露 |
| `site/README.md` | 补 `STATIC` 主入口定义、人工门边界、digest 手工快照事实、镜像漂移提醒与重建命令 | 信息架构 / 可维护性 |
| `.github/workflows/pages.yml` | push / PR 的 `paths` 各补 `README.md`、`scripts/refresh-digest.mjs`、`.github/workflows/refresh-digest.yml` | CI 触发完整性 |
| `site/app/**` | 由 `npm run build:site` 重新生成（11 个 JS chunk + CSS + 9 个 JSON），把上一轮前端改进与可见的 `StaticModeNotice` 带进 Pages 包 | 镜像漂移 |
| `site/demo/index.html`、`site/docs/*`、`site/innovation/data/*`、`site/data/build.json` | 由 `scripts/build-site.mjs` 重新组装 | 交付一致性 |
| `Wellspring-Agent/**` | 由 `build_release.py --prune` 同步（`site/`、`.github/` 均在 `SYNC_DIRS`） | 发布树一致性 |

**未改**：`demo/index.html` 源单页（491 KB 历史快照，仅被复制）、`site/agent/`（LEGACY）、`apps/web/public/*.json` 的 `source` 字段（涉及导出语义，需人工确认）、任何 `research_agent/**/*.py`、门禁与判定语义。

---

## 5. 验证结果

| 检查 | 结果 |
| --- | --- |
| `npm run build:site` | ✓ built（11 个 JS chunk + CSS） |
| `node scripts/build-site.mjs` | `site build ok`，demo sha256 `0658f279c87bc5da`，docs/data/innovation 清单齐全 |
| `node scripts/check-site.mjs` | `site check ok: 4 app assets, 11 JS bundle(s), static mode confirmed` |
| 镜像漂移 | `apps/web/public` 9 个 JSON 与 `site/app` 逐字节一致，`mismatches []` |
| 静态产物内容 | bundle 同时含 `"runtime disabled in static build"` 与「静态演示模式」 |
| `npm run check`（apps/web） | typecheck + 7 单测 + build 全通过 |
| `scripts/build_release.py --prune` / `--check` | 同步 12 处漂移、补齐 10 个文件、剪除 10 个旧 assets；`content_drift: 0 / missing_in_release: 0` |
| `scripts/release_check.py` | `release surface: ok (0 blockers, 4 warnings)` |
| Python 护栏 | 43 项 OK |
| 判定 | `record_test_verdict.py --show` = `current | tests 1239`（本轮未改 `research_agent/*.py`） |

---

## 6. 仍存在的问题 / 不可宣称

- **三套工作台并存**（`/app/`、`/agent/` LEGACY、`/demo/` 旧单页）未收敛；`site/docs/` 仍是未渲染的 Markdown 原文。
- `apps/web/public/orchestration-run.json:5-6` 的 `source: "real"` / `fixture_mode: false` 与静态打包事实冲突，但属导出字段语义，需人工确认后改。
- `refresh-digest.yml` 在前端镜像仓库仍未启用，线上 digest 依旧是 2026-10-23 手工快照；本轮只改了它的披露方式，没有让它变实时。
- `pages.yml` 的 `paths` 仍未覆盖 `43-…md`、编号反思文档等；这些不影响部署内容，只影响触发。
- **本文不宣称 demo 已上线新版本**：本轮修改的是主仓库 `site/`，是否推送到 `Yangxc0414/research-agent` 前端镜像仓库、以及 Actions 是否成功部署，本轮**未核实、未执行**（无网络推送动作）。
- 与主仓库一致：**已签确证 claim = 0**、29 个 SPEC 全 draft/pilot、无 external held-out eval；demo 的所有 SIM / CACHED 数字不是研究结论。

---

## 7. 复跑方式

```bash
# 重建 Pages 产物（顺序不可换）
cd apps/web && npm run build:site
cd ../.. && node scripts/build-site.mjs && node scripts/check-site.mjs

# 校验镜像一致性
python -c "import hashlib; from pathlib import Path; p=Path('apps/web/public'); a=Path('site/app'); print([f.name for f in p.glob('*.json') if not (a/f.name).is_file() or hashlib.sha256(f.read_bytes()).digest()!=hashlib.sha256((a/f.name).read_bytes()).digest()])"

# 交付一致性（Python 3.8）
python scripts/build_release.py --prune && python scripts/build_release.py --check
python scripts/release_check.py
python -m unittest tests.test_release_integrity tests.test_workspace tests.test_integration_files -q
```
