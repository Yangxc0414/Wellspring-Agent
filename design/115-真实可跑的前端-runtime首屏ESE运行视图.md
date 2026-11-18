# 115-真实可跑的前端：runtime 首屏从占位符变成 ESE 运行视图

> 状态基线：2026-11-18。承接 112（前端反思：静态 demo 与真实运行之间缺数据管道）、114（图注接产物）。
> 用户要求：不要只改 demo，真实可跑的前端也要完善。本轮改的是 **本地 runtime 的前端**（python -m research_agent runtime serve 提供）。
> 边界：只读视图；不提供 approve/sign/export，不改变任何门禁。

---

## 1. 之前的问题

runtime 的 `/` 只有一个占位符：

```text
<h1>Research Agent Local Runtime</h1>
<p>Localhost-only. docs · health</p>
```

而本地 `runtime_data/` 里已经躺着真实的 ESE 研究目录（`result.json` + `run/run-capsule.json`）。真实可跑的前端反而看不到它们——静态 demo 与真实运行之间仍然缺管道。

---

## 2. 本轮改动

### 2.1 只读扫描器

新增 `research_agent/runtime/ese_runs.py`：

- `scan_ese_runs(root)`：扫描 `runtime_data/*/result.json`，提取 study_id、commits、pooled rate/CI、adjusted difference、capsule 状态与 sha256；按修改时间倒序；
- `summary(root)`：返回 `runtime-ese-runs-0.1`，带 boundary（只读、探索性、无 Claim/签名）；
- 任何缺失/损坏文件都跳过，不抛异常。

### 2.2 首屏与 API

- `GET /api/ese/runs`：JSON，字段同上；
- `GET /`：不再是占位符，而是本地 ESE 运行表（study / commits / rate / adjusted diff / capsule status / capsule 路径），附一行"Read-only: gates and Claim signing stay on the CLI"；
- 仍只监听 localhost，仍不提供任何写/签端点。

---

## 3. 真实数据

启动 `python -m research_agent runtime serve` 后，页面会列出本地 `runtime_data` 里的研究（例如 `ESE-MS-20261118-02/03`、`heldout` 等带 result.json 的目录），capsule 列显示 `completed` 与路径。

测试（`tests/test_runtime_ese_runs.py`，3 例）：

- 扫描器读取 study 字段与 64 位 capsule sha256；
- 缺失目录/空目录安全返回；
- TestClient 下 `/api/ese/runs` 返回 count=1，`/` 页面包含 study id 与 Read-only 声明。

---

## 4. 为什么先做服务端渲染页而不是 React 工作台

1. `apps/web` 是 45 tsx 的完整工作台，加一个视图要动 types/store/adapter/rebuild，成本高、回归面大；
2. runtime 首屏是真实用户最先打开的页面（localhost:8000），先把"真实数据可见"这一步做掉，收益最直接；
3. 服务端渲染页不引入新依赖、不改变静态 demo 的边界，安全面最小。

下一步再把同一份 `/api/ese/runs` 接进 `apps/web` 的 ContextPanel（新增 "ESE 运行" tab），并用 static fallback 让静态站点也能显示示例。

---

## 5. 验收

| 项 | 结果 |
| --- | --- |
| 扫描器 | result.json + capsule 字段齐全，capsule sha256 64 位 |
| API | `/api/ese/runs` schema=runtime-ese-runs-0.1，count 正确 |
| 页面 | 含 study id、表头与 Read-only 声明 |
| 测试 | tests.test_runtime_ese_runs 3 项 OK |
| 规格 | modules/integration/SPEC.md 升版并记录 |
