# Agent Workspace（LEGACY · 静态预览）

> 这个目录是旧版单文件工作台（`index.html + agent.js + agent.css`）。主入口已迁移到
> **`site/app/`**（源码 `apps/web/`，Vite + React + TypeScript）。这里仅保留给旧链接与
> 历史对照，页面已加 canonical 指向 `../app/` 与 `noindex`。

新版入口：

```bash
cd apps/web
npm ci
npm run dev        # 开发
npm run build:site # 输出 site/app
```

或直接启动整套站点：

```bash
python -m http.server 8000 --directory site
# http://127.0.0.1:8000/app/
```

## 保留的功能（旧版）

- 三模式：调研 / 实验 / 受治理全自动（claim 人工门暂停）
- 工作区/最近任务、会话切换、新建任务、命令面板
- 模型设置小窗、上下文压缩、思考强度
- 运行中指导、插件/MCP 静态审批、自进化候选/租约/回滚
- 全部为 SIM，仅 localStorage；不调用 API、不产生真实 claim

## 迁移后去哪

- 新工作台源码：[`apps/web/`](../../apps/web/README.md)
- 构建与部署：[`35-前端工程化架构-可部署的对话式科研工作台.md`](../../35-前端工程化架构-可部署的对话式科研工作台.md)
- 旧版设计与验收：[`31-对话式科研Agent-静态工作台设计与交互.md`](../../31-对话式科研Agent-静态工作台设计与交互.md)

真实 runtime 的 live 控制台仍是 `site/live/`，模型接入高级页仍是 `site/models/`；工作台中的
“运行控制台 / Provider Profile”链接会以子页面打开。
