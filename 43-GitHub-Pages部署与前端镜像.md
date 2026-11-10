# 43 · GitHub Pages 部署与前端镜像

> 日期：2026-10-25  
> 线上地址：**https://yangxc0414.github.io/research-agent/**  
> 工作台：**https://yangxc0414.github.io/research-agent/app/**  
> 创新演示：**https://yangxc0414.github.io/research-agent/innovation/**  
> GitHub 仓库：`Yangxc0414/research-agent`（前端镜像，不是主项目仓库）

## 0. 这次部署了什么

只部署**前端与部署材料**，不包含后端、`oss/` 快照、第三方仓库或本地数据。

`pages-repo/` 是独立的可发布镜像，约 3.9 MB / 145 个文件：

```text
pages-repo/
├── README.md                     # 前端镜像说明与边界
├── apps/web/                     # React/TS 工作台源码
├── site/                         # Pages 根：首页、/app/、demo、models、live、innovation、docs
├── demo/                         # build-site.mjs 会复制的旧版 demo
├── scripts/build-site.mjs
├── 16-/17-/18- 设计文档           # build-site.mjs 复制到 site/docs
└── .github/workflows/pages.yml   # 构建 + 上传 site/ + 部署 Pages
```

主项目中仍保留完整后端与设计文档；镜像仓库只负责展示，不作为源。

## 1. 静态模式

GitHub Pages 没有 Python runtime，因此 `build:site` 改为：

```json
"build:site": "vite build --mode static --outDir ../../site/app --emptyOutDir"
```

`vite.config.ts` 在 `mode === "static"` 时注入 `__STATIC_ONLY__ = true`。  
`runtimeApi.ts` 在静态模式下：

- `request()` 直接抛出 `runtime disabled in static build`，不发起 `/api` 请求；
- `liveThenSnapshot()` 捕获后读取 `public/*.json` 快照；
- 设置、技能、子智能体、证据沿袭等页面都走快照/本地状态；
- 不再产生 GitHub Pages 上的 `/api` 404/500 噪音。

这是本次部署最重要的修复：**静态构建不能依赖“请求失败后 fallback”**，否则控制台会一直出现红色错误。

## 2. 工作流审计与改进

初始工作流能跑通，但有四个实际缺口：

1. 没有 `pull_request` 构建校验，坏改动只能等合并到 `main` 才发现；
2. 没有 `timeout-minutes`，npm/构建卡住会长时间占用 runner；
3. 文档 `16–18` 会被 `build-site.mjs` 复制，但不在触发路径里，改文档不会重新部署；
4. 没有检查产物是否真的以静态模式构建，可能把带 `/api` 的 bundle 发上线。

本次改为：PR 只构建 + 校验，不部署；PR 与 main 使用独立 concurrency group，避免互相取消；构建/部署增加超时；触发路径补 `16–18` 与 `check-site.mjs`；新增 [scripts/check-site.mjs](../scripts/check-site.mjs) 校验 Pages 必需文件、app 资产引用和静态模式标记。

仍未做：Actions 固定到 commit SHA、job-level 最小权限、PR 预览部署、失败通知。这些是后续安全/运维项，不影响当前演示。

## 3. 部署流程

1. 在 `apps/web` 构建静态产物：
   ```bash
   npm ci
   npm run typecheck
   npm run build:site
   ```
2. 在仓库根目录组装站点：
   ```bash
   node scripts/build-site.mjs
   ```
3. 同步到 `pages-repo/`（当前是手动复制：`apps/web` 源码、`site/`、`demo/`、`scripts/`、`16–18` 文档、`.github/workflows/pages.yml`）。
4. 在 `pages-repo` 提交并推送 `main`。
5. GitHub Actions `Deploy site to GitHub Pages` 构建并部署；仓库 Settings → Pages → Source 必须是 **GitHub Actions**。

当前实际部署由 GitHub Git Data API 完成（本机 `github.com` 的 git 传输被网络重置）；这只是一次性的网络绕行，不改变仓库内容与构建方式。

## 4. 验证结果

线上：

- `https://yangxc0414.github.io/research-agent/` → HTTP 200；
- `https://yangxc0414.github.io/research-agent/app/` → HTTP 200；
- Playwright 1440/390：
  - 首页标题、侧栏、`Agent 工作台`入口正常；
  - `/app/` 欢迎页、任务、`/agents` 设置页正常；
  - 工作台 **0 个 `/api` 请求、0 个 4xx/5xx、无 console error**；
  - 390 无横向溢出；
- 截图：`116–121`（本地静态、线上首页、线上工作台、移动端）。

工作流运行：GitHub Actions `Deploy site to GitHub Pages` **completed success**。  
Pages API 返回 `html_url=https://yangxc0414.github.io/research-agent/`、`build_type=workflow`、`https_enforced=true`。

## 5. 这次部署暴露/确认的问题

1. **GitHub 仓库不能直接推整个项目**：主项目包含 1.7 GB `oss/`、222 MB `research_agent/`、18 MB 第三方 `claude-code-main/`，且后端数据不应公开；必须做前端镜像。
2. **静态站点不能请求 `/api`**：即使 UI 有 fallback，浏览器仍会记录 404/500；必须在构建时关闭 runtime。
3. **空仓库不能直接建 Git blob**：Git Data API 返回 `409 Git Repository is empty`；需要先用 Contents API 建首个 commit，再写完整树。
4. **本机 git 传输不可用**：`github.com:443` 连接重置，但 `api.github.com` 可用；因此采用 Git Data API 提交。后续更新仍建议恢复 git push 或使用 CI。
5. **前端镜像会漂移**：`pages-repo` 是快照，不是源；修改 `apps/web` 后必须重新构建、同步、提交，否则线上与源码不一致。

## 6. 边界与未完成

- 线上是 **SIM / STATIC**：没有真实 LLM、工具执行、claim 签名、runtime job；
- `/live/` 与 `/models/` 需要本地 Python runtime，Pages 上只能显示连接说明；
- `refresh-digest.yml` 尚未在镜像仓库启用，`site/data/digest.json` 仍是手工/CACHED 快照；
- 主项目仓库仍未推送；线上镜像与主项目不是同一个仓库；
- 没有自定义域名；Pages 使用 `github.io` 子路径；
- 还没有自动同步脚本；`pages-repo` 更新目前是手动步骤。

## 7. 后续建议

1. 将“构建 → 同步 pages-repo → 提交”做成脚本，避免镜像漂移；
2. 如果需要真实检索/模型，Pages 只做展示，runtime 放在本地或独立服务；
3. 给镜像仓库补一个 `Makefile`/`npm run pages` 入口；
4. 在主项目 README 中固定“在线 Demo / 主仓库未推送”的边界，避免把静态镜像误认为完整系统；
5. 如果 GitHub git 传输恢复，改为普通 push；否则继续用 API 提交并记录 commit SHA。

## 8. 一句话

> 线上部署的是一个**可公开演示的前端镜像**，不是完整科研运行时；它证明了工作台、命令/Skill、子智能体批量配置和证据界面可以被真实访问，但不证明后端执行、模型调用或 claim 签名已经上线。
