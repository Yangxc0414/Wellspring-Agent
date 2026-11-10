# 62 结构化反思与对照：前端七维审计 + Awesome-Journal-Skills 六维对照

> 状态：2026-11-05。性质：**只读事实审计 + 一轮已落地的前端修改**。
> 对比基准：`D:\Users\20691\Downloads\Research Skill调研\Awesome-Journal-Skills-main`（下称 AJS）。**该目录全程只读**：仅做枚举、读取与统计，未修改、移动、删除其中任何文件。
> 证据纪律：每个判断都带可核对的文件路径与行号或可复跑命令；没有量过的标「未核实」；AJS 的能力描述只写目录中确实存在的内容，不补写「应该有」的目录或文件。
> 自我纪律：沿用 `61-` 与 `ARCHITECTURE.md` §8 —— 未实现的能力写 roadmap，不写「已支持」；fixture 与模拟数字不当真实结果；负结果与失败判定保留。

---

## 0. 结论摘要

1. **前端**：信息架构与任务链路的映射是清楚的（6 个上下文 tab、16 个设置分节、9 阶段目录、门禁命令展示），但存在三类结构性不足：**无错误边界**、**静态/实时/演示三种数据来源的标签不统一**、**部分未加载状态用看似合理的数字兜底**。本轮修了前两类与第三类的一处代表，其余列入 §3.8。
2. **设定对照**：AJS 与本项目不是同类物。AJS 是 **300 个插件包 / 4166 份 Markdown 提示词 + 领域写作规范知识**的静态分发库；本项目是**带状态、门禁、哈希链与判定的证据治理运行时**。这个范畴差异决定了「优越性」只能在**运行时治理**维度成立，不能推广成「科研效果更好」。
3. **优越性（有边界）**：在「不变量能否被强制执行、系统能否发现自己错了、上游变更能否让下游结论失效」三件事上，本项目有**代码级、可复跑**的机制，AJS 对应位置要么只有文字要求，要么明确不测。这是可确认的机制优越性，§5 给出证据链。
4. **不占优（必须承认）**：领域覆盖广度、领域写作规范知识、安装即用性三项 AJS 明显更强；且本项目**已签确证 claim = 0、29 个 SPEC 中 active = 0、没有 external held-out eval**，因此没有任何依据宣称「产出质量更高」。
5. **本轮改动**：10 个源文件（新增 1 个组件、修改 9 处），另同步发布树；覆盖页面结构、状态反馈、交互一致性、结果呈现与文档一致性。两套前端构建、54 项 Python 护栏、发布树零漂移均通过。

---

## 1. 对比基准：AJS 的可确认事实

### 1.1 规模与定位

| 量 | 值 | 可核对来源 |
| --- | --- | --- |
| 一级目录 | 510 | `find -mindepth 1 -maxdepth 1 -type d` |
| 可安装 `-Skills` 包 | **300** | 包根下存在 `skills/` 与 `.claude-plugin`；两者集合完全相同 |
| `SKILL.md` | **4166** | `find -name SKILL.md`；全部位于 `*/skills/` 下 |
| 期刊/会议 venue | 744 | `README.md:4` 横幅；`catalog.json` 的 `venue_count` |
| 全库文件 | 11,153（7,011 `.md`、1,377 `.do`、675 `.svg`、602 `.json`、457 `.py`、406 `.png`） | 文件枚举 |
| 导航占位目录 | 201（每个只有 1 个 `README.md`） | `README.md:420` 自述「201 个轻量入口文件夹…只负责导航」 |

- 定位：`README.md:1-13`（Claude Code 插件索引，Stanford REAP × CoPaper.AI）；`.claude-plugin/marketplace.json:2-9` 的 `description` 明写「Add this marketplace once, then `/plugin install <pack-name>`」，`:10-16` 起 `plugins[]` 共 300 条。
- 安装无安装器：`README.md:1598-1636` 给出 `/plugin marketplace add … → /plugin install … → /reload-plugins` 与手动 `cp -R <pack>/skills/<prefix>-* ~/.claude/skills/` 两条路径。

### 1.2 单个 skill 的形状（实读样本）

`NeurIPS-Skills/skills/neurips-submission/SKILL.md:1-22` 的 frontmatter **只有 `name` 与 `description`**；正文是 `Use this skill → Core checks → NeurIPS-specific risks → Audit workflow → Output format`，要求 agent 按当年 CFP 做投稿前合规审查并输出结构化文本块。另抽读 `Econometrica-Skills/skills/ecta-writing-style/SKILL.md`、`Economic-Research-Journal-Skills/skills/er-style/SKILL.md`、`JAMA-Skills/skills/jama-study-design/SKILL.md`、`Advanced-Materials-Skills/skills/advmat-writing-style/SKILL.md`，形状一致：**触发条件 + 领域规范 + checklist + 反模式 + 输出模板**。

全库 4166 个 SKILL.md 的 frontmatter 键统计：`name` 4166、`description` 4166、**`allowed-tools` 0**。路由 skill 也只是文字表：`Econometrica-Skills/skills/ecta-workflow/SKILL.md:10-11` 明写「This is the router. It does not replace any specialized skill」。

### 1.3 质量保障：结构合规，且行为评测被刻意拆除

- CI 两个 workflow：`.github/workflows/plugin-scanner.yml:1-29`（第三方安全扫描，`min_score: 80`）、`.github/workflows/repo-audit.yml:1-74`（3 job）。
- `tools/run_checks.py:56-118` 硬检查 14 项：`py_compile`、`unittest discover -s tools/tests -t tools`（`:61`）、`audit_repo.py`、`quality_scorecard.py --min-score 40`、`clone_audit.py`、若干 `--check` 生成器、`git diff --check`。
- 测试范围：`tools/tests/` 13 个 `test_*.py`，**只测仓库维护工具**；`.maintenance/INDEX.md:19` 明写「no behavioural eval in CI」。
- `.maintenance/QUALITY-LANE-2026-09.md:15-23` 记载 owner 于 2026-06-29 刻意拆除 SkillOpt / monthly-uplift 行为评测装置（原因是它长成 7,400 行仪表盘 + 646KB worklog 的自引用循环并在干净检出上打破 CI），`:21` 「不得重建这类自动提交、自我度量、常驻 CI 的评测装置」，`:50` 「不把行为评测接入 run_checks」。
- `tools/quality_scorecard.py:9-16` 的 "This is pass/fail and it is the gate" 指的是**仓库内容结构 conformance**，不是 agent 运行时的门禁。

### 1.4 明确没有的东西（附检索方法）

以 4166 个 SKILL.md + 457 个 `.py` 为全集，用严格短语正则检索 `hash chain|sha-256|hashlib|approval gate|human sign|preregist|factorial design|code fingerprint|projection contract|state machine|schema contract` 并逐条复核命中上下文：

| 机制 | 结论 | 关键证据 |
| --- | --- | --- |
| 证据哈希链 | 未发现 | 全库 `hashlib` 仅 4 个文件 9 行，用途为 `tools/venue_lib.py:501` 的 venue 索引 digest、`tools/external_link_audit.py:311` 的报告指纹、`tools/build_eval_set.py:48` 与 `tools/fetch_venue_topics.py:225` 的缓存键/条目 ID；无一构成链 |
| 人签门禁 / agent 预注册 | 未发现 | `.py` 中 `approval` / `sign-off` / `state machine` 命中均为 0；SKILL.md 里的 `co-author sign-off`、`shepherd sign-off`、OSF / AEA RCT Registry 预注册都是**要求论文作者遵守的学科写作规范** |
| 投影契约 / 代码指纹绑定 / 因子设计引擎 | 未发现 | `projection contract` 全库 0 命中；`record a content hash` 等 2 处是文字建议；3 处 `factorial design` 是实验方法知识 |
| 后端服务 / 运行时状态持久化 | 未发现 | 全库 `package.json` / `requirements.txt` / `pyproject.toml` / `Dockerfile` / `server.py` / `app.py` / `main.py` 均 0；602 个 `.json` 全是静态清单（300 个 `plugin.json` + 300 个包内 `marketplace.json` + 根 `marketplace.json` + `catalog.json`） |
| skill 内可执行脚本 / 校验器 | 未发现 | `allowed-tools` 为 0；49 个 SKILL.md 提及 `.py` 文件名、84 处提及 python 命令，都是「建议复现包里准备什么文件」 |
| LaTeX / BibTeX 模板 | 不存在 | `.tex / .bib / .cls / .sty / .bst` 全为 0；格式规范以 Markdown 写在 SKILL.md 与 `resources/official-source-map.md` |

`shared-resources/empirical-methods/execution-with-mcp.md:1-9,31-55,148-159` 是唯一接近「执行层」的文件：要求 agent 调用**外部** StatsPAI / Stata MCP 服务并遵守 "Hard rules (the credibility contract)"（run don't claim / bibtex only / degrade honestly）。它是文字契约，仓库不内置该服务；`:25-27` 规定 MCP 未连接时回退代码骨架。`showcase/README.md:47` 自述 5 个案例的「复现契约是契约而非脚本」。

**一句话本质**：AJS 是静态的**领域知识 + 提示词技能库**，配一套纯 stdlib 的仓库维护脚本做结构合规；靠 agent 阅读后自觉遵守，仓库自身不提供运行时、状态、门禁或证据链。

---

## 2. 本系统侧：可确认事实（用于对照，含边界）

### 2.1 内核不变量与**可执行**守卫

- 文档定义：`ARCHITECTURE.md:48-56`（Kernel 固定 span-only、Claim/EA/Protocol/Gate/Signature/Closure/Export 写权限、Q0/G1/G2/S5b/G5 人工门、hash、allowlist、越界校验）；`AGENTS.md:251-255,283`。
- 代码强制（不是口号）：
  - `research_agent/mcp_server.py:53-101` 46 个工具白名单 + `:3652-3653`、`:3692-3693` 双层拒收；`framework_api.py:90-92` 对 HTTP/Python 面同一拒收；`mcp_server.py:102-105` `HUMAN_ONLY` 说明无签核工具。
  - `runtime/app.py:55-62` `WRITE_GUARD_BOUNDARY` + `:378-399` 中间件对 `POST/PUT/PATCH/DELETE` 默认拒绝；`tests/test_runtime_write_guard.py:131-154` 从**实时路由表**枚举 mutating 路由逐个断言 401。
  - `tests/test_dispatch_arg_hygiene.py:40-55` 用 Tripwire 遍历全部 46 工具，断言未知参数在 handler 之前被拒。
  - `flow.py:63-92` `q0_decision()` 无 span / 无全文 / coverage 不足即 blocked；`:95-136` G1 校验 `status`、`human_reason`、候选哈希；`:139-167` G2 校验 `human_reason`、`limitation`、`design_sha256`。
  - `adapters/fixture_retriever.py:16,23` 与 `contracts.py:130` 要求 fixture 显式标记。
- `60-科研智能体设计缺陷与改正.md:200-202` 是逐条核验结论：46 个 MCP 工具无签核类，HTTP 路由中带 gate 词的只有两个只读 GET。

### 2.2 能力面数字（以代码为准）

| 量 | 值 | 来源 |
| --- | --- | --- |
| MCP 工具 | **46** | `mcp_server.py:53-101`；`tests/test_mcp.py:222` 断言 |
| CLI 命令目录 | **194**（143 条 argparse 叶子 + 51 条人工条目） | `apps/web/public/command-catalog.json`；`workspace.py:558-630,795-823`。注意该文件自述 "descriptive catalog only; the UI does not execute shell commands" |
| 模块 SPEC | **29**（15 draft / 14 pilot / **0 active**） | `modules/*/SPEC.md` frontmatter 全量枚举 |
| 可执行档位 | 3（`protocol_run` / `local_tabular_experiment` / `search_factorial`），每个同时声明 `supports` 与 `cannot_test` | `executable.py:36-44,58-66,91-97,104-142` |
| 声明式搜索因子 | 8，格子数 >12 直接拒绝，区间跨零即不可判定 | `search_lab.py:66-143,215-272,595-646,821-847` |
| 测试与判定 | 150 个 `test_*.py`；最近 `Ran 1239 tests / OK`，`--show` = `current`（指纹 `032562c461289b05`） | `tests/`、`runtime_data/test-verdict.json` |
| 交付一致性 | MANIFEST 每行 `relpath \t sha256 \t bytes`，`content_drift / missing_in_release` 必须为 0 | `build_release.py:219-242`、`tests/test_release_integrity.py:30-38,77-90,117-124` |

### 2.3 判定与失效机制（对照时可复跑）

- `projections.py:47-55,145-265`：7 槽投影契约 + AST 枚举，四态 `in_literal / aliased / elsewhere / absent`；注释记录的扫描基线为 171 个 schema id（**不是硬编码常量**，函数返回动态 `len(schemas)`）。`:14-18` 明确「a report, not a gate」，合规性只在 `tests/test_projection_contract.py:35-42` 的 6 个 ADOPTED 投影上强制（棘轮）。
- `doc_interfaces.py`（D6）：枚举 AGENTS.md + SPEC 的 `*.json` 引用，16 条 `GENERATED_BY` 必须同时给命令与理由；`tests/test_doc_interfaces.py` 断言未解释集合为空。
- `verdicts.py` + `scripts/record_test_verdict.py`（D9）：判定由运行器自己解析 `Ran N tests / OK` 写入，带 `source_fingerprint`、`truncated`、五态 `verdict_status()`；退出码来自解析结果而非 shell 链。
- `closure_profiles.py:16-31`：三套 profile，`SUBMISSION_READY = False`；boundary 明写「链只报存在性与 SHA-256 身份，不证明正确性、语义蕴含、同行评审或可投稿」。
- `lineage.py:171-541`：SHA-256 哈希化节点与依赖边，`verify()/impact()` 重算后 BFS 传播 `stale_ids`，推导 `stale_claims / requires_resign / export_allowed`；返回状态是 `clean / stale`。
- `study_closure.py:125-135,224-245`：`code.unchanged` 指纹不匹配为 blocker，功效不足 / 区间跨零即不可判定。
- `runtime/jobs.py:232,266-270,855-869`：单 worker 线程池、`job.json` 原子落盘、事件序号；`runtime/app.py:947-986` SSE 流式推送。
- `rsi.py:457-563,694-720` + `evolution_active.py:94-152`：只有 `regressed` 触发自动 revoke，升级需 `human_reason`；`SAFE_SCOPES` 5 个注册项，`claim.statement / evidence.artifact / gate.decision` 被 `LOCKED_SCOPES` 锁死。

### 2.4 诚实边界（对照时不可越过）

- `ARCHITECTURE.md:400-415` §8「不能宣称」逐条：不是全自动科研系统、不支持任意本地实验环境、不是期刊官方模板、不是同行评审、没有动态插件市场、没有多租户鉴权、Host-as-Model 不担保质量/独立性、自进化只在两个过程参数闭合且「降级自动、升级人签」、不是断点恢复框架、`search_factorial` 是结构类比、多角色评审不是多审稿人、区间跨零即不可判定。
- 仍是 roadmap：`CapabilityRegistry`（`:389,94`）、`SkillRuntime`（`:390,220`）、VenueProfile / 模板 JSON registry（`:391`）、任意实验环境 `LocalExperimentRunner`（`:392,403`）、external held-out / human blind eval（`:394`，「没有这一步，不能声称论文质量提升」）。
- `README.md:117,389-401`：所有「可做性/风险」评估均基于文献未做实验；前端工作台 demo 数据全是 SIM；没有真实导入、后端运行、真实导出或密码学签名。
- **最尖锐的事实**：`58-交付验收清单.md:6248,6294`「已签确证 claim = 0」；`60-科研智能体设计缺陷与改正.md:98` 同；`59-自改进度量设计.md:4`「431 个比较里 0 条已签确证结论」。即证据链机制齐备，但闭环从未被人工签核消费完。
- 跨进程状态是 `job.json` 文件快照级持久化；`jobs.py:246-250` 把重启时仍 `queued/running` 的任务直接判 `failed`，`ARCHITECTURE.md:410` 自认「不是断点恢复框架」。

---

## 3. 前端七维反思（基于当前最新代码）

### 3.1 页面结构

**现状**：`App.tsx:172-215` 单壳 + `welcomeOpen` 二元视图（`:190`）+ 8 个 `React.lazy` 浮层（`:15-38,204-211`）；设置页 5 组 16 分节（`SettingsPage.tsx:29-74,86-121`）；`ContextPanel` 6 tab（`ContextPanel.tsx:19-26,2398-2407`）。
**判断**：导航分层与「一个任务 / 一个上下文 / 一个设置中心」的划分是合理的；但 `workspaceStore.ts`（3102 行）、`ContextPanel.tsx`（2423 行）、`components.css`（5865 行）承担过多职责，且 16 个分节组件静态 import 进同一个 lazy chunk。
**不足**：`App.tsx:203` 原为 `Suspense fallback={null}`，全库 `ErrorBoundary` 零匹配 —— 任一 lazy chunk 失败即白屏，用户无法判断本地状态是否被动过。
**本轮处理**：新增 `AppErrorBoundary.tsx` 并在 `main.tsx:6-11` 包住 `<App />`；`App.tsx` 给 Suspense 一个可见的 `overlay-loading`；`disclosures.css` 补恢复面板与加载提示样式。错误面板明确写「本地状态未被改动，没有触发任何门禁或签核」。

### 3.2 信息架构

**现状**：`liveThenSnapshot` 返回 `source: "runtime" | "snapshot"`（`runtimeApi.ts:638-641,676-682`），`SourcePill.tsx` 已在 3 个设置组件复用；`runtimeBacked`（`ContextPanel.tsx:485,2360`）切换 RUN 两套视图。
**判断**：「证据在哪」最短 2 层可达（命令面板 → EVIDENCE tab），但术语与来源标签仍有歧义。
**不足**：
- `Q0` 在 `ContextPanel.tsx:32` 是覆盖门禁，`:859` 又被写成 claim 门；`S5b`（`catalog.ts:42`）与 `GATE_NAMES` 的 `S5`（`ContextPanel.tsx:32`）不统一。
- `LineagePage.tsx:88` 直接 fetch `lineage-demo.json`，不带来源徽章，却显示文件里写死的 `"closed-loop CheMLab (real local artifacts)"`。
- `SettingsSections.tsx:738` 原硬编码 `Runtime: not connected`、`:744` 写「不调用 LLM / MCP transport」，在**非静态构建且 runtime 已连接**时与 `/live` 真实 pipeline 矛盾。
- `apps/web/README.md:5` 仍写 `SIM · STATIC`，`:79` 写 `LOCAL DEMO CANDIDATE · SIM`，与实际 `TopBar.tsx:110-114` 和 `ContextPanel.tsx:2096-2097` 不符。
**本轮处理**：`AboutSettingsPage` 改为 `probeRuntime()` 探测（`__STATIC_ONLY__` 下显示 `disabled in static build`），「不可宣称」列表改写为**与连接状态无关**的架构不变量；Guide 页文案区分演示引导与真实 `/live`；README 两处文案同步。未改项（术语表、LineagePage 来源徽章）列入 §3.8。

### 3.3 交互流程

**现状**：Composer 建议（`Composer.tsx:27-54`）、斜杠命令（`commandCatalog.ts:27-224`）、自动推进 timer（`App.tsx:52-65`）、`/live` 的 SSE + poll（`workspaceStore.ts:2400-2649`）、strict 续跑表单（`ContextPanel.tsx:796-856`）、人工门 CLI 命令展示（`gateCommands.ts`）。
**判断**：真实 pipeline 与演示 reducer 两条链并存，已有缓解（`runtimeBacked` 隐藏演示按钮、`startLiveRun` 拒绝并发、`RUNTIME WORKSPACE` 消息替换），但初始状态二者并列在 `run-controls` 同一行，且用相同阶段号标注。
**不足**：`SLASH_COMMANDS` 没有 `live`，而 `workspaceStore.ts:1666-1673` 支持 `/live`、`/help`（`:1731`）也列出它 —— 命令目录与执行器不同步，补全里搜不到。
**本轮处理**：`commandCatalog.ts` 补 `id: "live"` 条目（`Composer.tsx:107` 会生成 `/live`），`available` 与只读/运行态约束一致；`claim` 原已是 `sign` 的 alias（`:123`），无需重复。

### 3.4 状态反馈

**现状**：`sim-badge`、`Toast`（`Toast.tsx:5-24`）、`RunIndicator`（`Conversation.tsx:149-171`）、`gate-hint`、失败卡与 `RuntimePreflight`。
**不足**：
- `workspaceStore.ts:2637-2640` 原 `onerror` 只 `close()` 并置 null，**没有告知用户实时通道已断开**，虽然 900ms 轮询仍保数据。
- 上一轮修的静态构建失败提示仍有残留：`:2661` 原写「请用本地 runtime（npm run dev）运行 /live」，但静态产物里 `npm run dev` 不能让该页面生效，等于再次把构建期限制归因于用户。
- `gateApproved` 全库 16 处写入全是 `false`，claim 门到达后 `resumeAuto/stepAuto/timer` 都被拦住，是**前端不可解锁的死锁**；原 `gate-hint` 只说「会被门禁拒绝」，没给出路。
- `Toast` 成功/失败同图标，无 tone 区分。
**本轮处理**：SSE 断连加一条明确的降级提示；静态失败 toast 改为「当前是静态演示构建…需以非 static 模式重新构建前端」；`gate-hint` 补充「签核只能在本地 CLI 完成，前端不会代为签署或解锁；签核后请重新载入状态或以 /live 续跑」。**未改状态语义**：`gateApproved` 仍是只读的人工门投影，不擅自新增「导入签名回执」这类会改变门禁逻辑的功能。

### 3.5 结果呈现

**现状**：`ArtifactCard.tsx` 13 种卡片、`stage-kv-grid` 5 组 KV、EVIDENCE/CLOSURE PROFILES/Lineage 页；`UsageStats.tsx:280,528` 已明确区分本地估算与真实 `/api/models/calls` 用量。
**不足**：fixture 数值缺统一 SIM 标记（`catalog.ts:41` 的 `R² 0.164`、`workspaceStore.ts:743-758` 的 `mean 412 / baseline 286 / sha256:7c41e2`）；`OrchestrationOverview.tsx:197-200` 在 `plan` 未加载时用 `|| 3` / `?? 8` / `?? 4` **编造看似合理的数字**；`workspaceStore.ts:758` 的 `sha256:7c41e2` 不是有效指纹。
**本轮处理**：`OrchestrationOverview` 改为 `plan ? 实际值 : "—"`，`autoEvolve` 未加载时显示 `AUTO-EVOLVE UNKNOWN`（不再默认 ON）；上一轮已给 `ContextPanel` 的 run KV 加 `demo-disclaimer`。未改项（统一 `SIM` 徽章、KV 附来源/分母/指纹、伪哈希）列入 §3.8。

### 3.6 异常与空状态

**现状**：7 种空态类名，`disclosures.css:36-48` 已统一颜色与行高；各页有自己的失败文案；资源缺失统一回落静态快照。
**不足**：无 App 级错误边界（已在 §3.1 修）；`.settings-empty` 在 `settings.css:577` 与 `:1969` 重复定义；两处 runtime 启动命令写法不一致（`ContextPanel.tsx:427` 的 `python -m research_agent.runtime` vs `GovernancePanel.tsx:48` 的 `python -m research_agent runtime serve`）；`liveThenSnapshot` 的 `catch {}` 吞掉 401 / 超时 / 静态禁用 / 后端未启动，调用方无法区分。
**本轮处理**：补错误边界与可见 fallback。其余列入 §3.8 —— 这些需要跨多个组件统一改造，不适合与本次「不新增无关功能」的定向修改混在一起。

### 3.7 与科研任务链路的衔接

**现状**：前端 9 阶段目录（`catalog.ts:37-47`，无 S0/S7，多阶段合并）；门禁 `Q0/G1/G2/S5/G5`；完成后按后缀加载 7 类 loop 产物（`workspaceStore.ts:2510-2525`）；`ArtifactCard.tsx:587-627` 把 `S5 needs_human` / `G5 blocked` / `G5 needs_human` 映射成 CLI 命令。人工签核、协议冻结、发布全部只读展示 —— **这与后端 `AGENTS.md:283` 的人工门边界是一致的，是正确的**。
**断链（事实）**：① 签核后无 closure 入口，演示链路 G5 永远 blocked；② `gateApproved` 死锁（§3.4）；③ EVIDENCE 页 `refs` 是字符串数组，不能跳到 span 原文；④ `S5/S5b/Q0` 命名不对齐；⑤ `LineagePage` 的 export 状态来自预置快照，与当前 job 无联动。
**本轮处理**：只修「死锁不可理解」这一条（gate-hint 文案）。其余属于需要新增状态/入口的功能变更，按「不新增无关功能」与「人工门不搬进浏览器」的约束**不擅自改**，写入 §3.8 作为待决项。

### 3.8 本轮未修项（明确列出，不藏在结论里）

| 项 | 原因 |
| --- | --- |
| 统一 `SIM` 徽章并覆盖所有 fixture 数值 | 需跨 5+ 组件与 domain 层，属独立改造 |
| 每个 KV 数字附来源 / 分母 / 指纹前 8 位 | 需要后端产物字段配合，不能凭空生成 |
| 术语表统一 `Q0 / S5 / S5b` | 涉及 `catalog.ts`、`ContextPanel`、`gateCommands` 三处语义，需人工确认口径 |
| `LineagePage` 接入 `SourcePill`、与当前 job 联动 | 该页当前读静态 `lineage-demo.json`，联动需新数据通道 |
| `liveThenSnapshot` 返回失败原因并区分 401/超时/静态 | 返回类型变更需逐调用点核对 |
| SSE 指数退避重连 | 与 `finally { stream.close() }` 的生命周期耦合，需单独设计 |
| `refs` 可点跳转 span 正文 | 需后端 span 索引接口 |
| 拆分 `workspaceStore.ts` / `ContextPanel.tsx` / 大 CSS | 大重构，应单独立项 |
| 合并 `.settings-empty` 重复定义、统一 Toast tone、统一 CLI 启动命令文案 | 样式/文案收尾，低风险但需整批核对 |

---

## 4. 六维对照表

> 「判断」列只做**机制层面**的对照；凡涉及效果、质量、覆盖广度的地方直接标注谁更强，不做价值平衡。

| 维度 | AJS（可确认） | 本系统（可确认） | 客观判断 | 依据 |
| --- | --- | --- | --- | --- |
| **功能覆盖** | 300 包 / 4166 skills / 744 venues；11 学科板块；`resources/` 3540 文件（1757 md、1360 `.do`、408 `.py`）、`assets/` 1091、`templates/` 198 | 46 个 MCP 工具 / 194 条 CLI 目录 / 29 个 SPEC / 3 个可执行档位 / 3 个中文期刊 profile（`revision_templates.py`） | **AJS 在领域覆盖与写作规范知识上压倒性更强**；本系统覆盖的是「流程与治理」而非「期刊知识」 | `README.md:4,44-58`、`marketplace.json`；`mcp_server.py:53-101`、`executable.py:96-97`、`ARCHITECTURE.md:279` |
| **科研流程适配** | skill 按投稿环节切成「选题 / 方法 / 文风 / 图表 / 复现 / camera-ready」等 checklist，靠 router skill 文字路由；无跨 skill 状态 | S0–S16 阶段目录、Q0/G1/G2/S5b/G5 门禁、strict 模式停在 `needs_g1/needs_g2`、三套 closure profile、RunCapsule→EA→Claim→Closure 对象链 | **适配方式不同**：AJS 适配「投稿环节的知识需求」，本系统适配「证据资格与流程阶段」；后者有可执行状态，前者没有 | `ecta-workflow/SKILL.md:10-11,42-71`；`flow.py:95-167`、`closure_profiles.py:33-67`、`pipeline.py:467-516` |
| **任务闭环** | 无运行时、无状态持久化、无跨 skill 状态机；`showcase/` 5 个案例是已提交的文字运行记录 | `job.json` 原子落盘 + SSE + 三套 closure + lineage stale 传播 + `code.unchanged` 让旧结论失效 + RSI 只降级自动/升级人签 | **本系统更强，但有限**：机制闭环齐备；`jobs.py:246-250` 在途任务重启判 failed，`ARCHITECTURE.md:410` 自认不是断点恢复框架；且**已签确证 claim = 0**，闭环最后一公里未被人工消费 | `showcase/README.md:47`；`jobs.py:232-270`、`lineage.py:445-506`、`study_closure.py:125-135`、`58-:6248,6294` |
| **用户体验** | `/plugin install <pack>` 即可用，无环境要求；纯文本交互 | React 工作台（6 tab / 16 分节 / 命令面板 / SSE 实时反馈 / 错误边界），但需 Python 3.8 + runtime + 静态构建会禁用能力；人工门要切到 CLI | **AJS 上手成本更低**；本系统在「状态可见性、异常恢复、数据来源披露」上更强，代价是部署与认知成本 | `README.md:1598-1636`；`App.tsx`、`main.tsx`、`StaticModeNotice.tsx`、`ARCHITECTURE.md:400-415` |
| **可扩展性** | 300 个包由 `marketplace.json` 聚合，新增 venue 是复制包 + 结构审计；`tools/audit_repo.py` 防漂移 | 模块 SPEC 为唯一源、`spec update/patch` CLI、executable 注册表、8 因子声明式设计、MCP/HTTP/Python 共用 dispatch；但 `CapabilityRegistry` / `SkillRuntime` 仍是 roadmap | **各有侧重**：AJS 在「加一个期刊」上极便宜；本系统在「加一种可检验的研究能力」上有注册表与契约，但动态插件市场未实现 | `marketplace.json:10-16`、`tools/audit_repo.py`；`AGENTS.md:60-62`、`executable.py:96-142`、`ARCHITECTURE.md:94,389-390` |
| **差异化价值** | 规模化、可检索的领域写作规范知识库（这是很实在的价值） | 证据治理运行时：span-only、人工门不可绕过、hash 链失效传播、投影契约、判定绑指纹、拒绝/负结果保留 | **互补而非替代**：AJS 卖「知道怎么写」，本系统卖「凭什么这么写、什么时候必须停」 | 见 §1.4 与 §2.1–2.3 |

---

## 5. 优越性论证（有明确边界）

### 5.1 先限定范畴

两者不是同一层产品：AJS 是**静态知识分发**，本系统是**运行时治理**。因此「优越性」这一命题只在二者都试图回答的问题上成立 —— 即「**agent 产出的东西，凭什么可以被信任、被复核、被判定失效**」。在「领域知识覆盖」问题上，AJS 更强，§4 已如实列出。

### 5.2 三条可确认的优越性

**A. 不变量从「文字纪律」升级为「代码拒绝」。**
AJS 里「证据链」「签核」「预注册」是 SKILL.md 的输出模板字段与 checklist 条目：4166 个 frontmatter 只有 `name/description`、`allowed-tools = 0`，`.py` 中 `approval / sign-off / state machine` 命中为 0，`hashlib` 全库仅 4 文件 9 行且只用于 digest/缓存键。它的 `execution-with-mcp.md:148-159` 自称 "credibility contract"，但明确是要求 agent 自觉遵守的文字。
本系统对应位置是：46 工具白名单在 dispatch 入口拒收（`mcp_server.py:3652-3653`）、HTTP mutating 路由默认拒绝并由测试枚举全部路由（`runtime/app.py:378-399`、`test_runtime_write_guard.py:131-154`）、G1 校验 `human_reason` 与候选哈希（`flow.py:95-136`）、G2 校验 `design_sha256`（`:139-167`）、Q0 无 span 即 blocked（`:63-92`）、fixture 未标记即抛错（`fixture_retriever.py:16,23`）。
→ **推论**：对「agent 会不会绕过规则」这个问题，AJS 的答案是「请它不要」，本系统的答案是「它做不到，且测试守着这一点」。这是可复跑的差异，不是措辞差异。

**B. 从「刻意不测」到「可证伪的判定与失效传播」。**
AJS 的 CI 只做仓库结构合规（`run_checks.py:56-118`），且 `.maintenance/QUALITY-LANE-2026-09.md:15-23,50` 明确拆除并禁止重建行为评测装置；`.maintenance/INDEX.md:19` 写「no behavioural eval in CI」。
本系统把「系统怎么知道自己错了」做成一级对象：1239 项带 `source_fingerprint` 的判定（`verdicts.py` + `record_test_verdict.py`，`--show` 报 `current`）、投影契约 7 槽的 AST 枚举与棘轮（`projections.py`、`test_projection_contract.py`）、D6 文档路径守卫（`doc_interfaces.py`）、SUCCESS/FAILED 判定由运行器自己解析而非 shell 退出码、失败判定留档、负结果与不可判定区间原样保留（`search_lab.py:821-847`、59- 的自我更正链）。
→ **推论**：AJS 把「不自我度量」作为治理决策（有它的道理，避免自引用循环），本系统则选择「让度量本身带指纹与分母、且不许把失败写成绿灯」。在「外部审稿人能否复核这套系统有没有自欺」这个问题上，后者提供了机器可读的抓手。

**C. 从「无状态」到「上游一改，下游结论自动失效」。**
AJS 无后端、无状态持久化、无跨 skill 状态机，602 个 JSON 全是静态清单。本系统有 `job.json` 原子落盘 + SSE、`lineage.py` 的 SHA-256 节点与 BFS stale 传播（推导 `stale_claims / requires_resign / export_allowed`）、`study_closure.py:125-135` 的 `code.unchanged` 指纹不匹配即 blocker、三套 closure profile 都 `submission_ready=false`、`rsi.py:457-563` 只有 regressed 自动撤销且升级必须人签、`LOCKED_SCOPES` 锁死 claim/evidence/gate。
→ **推论**：对「三个月前那个结论，在代码/数据/协议改过之后还能引用吗」这个问题，AJS 没有可执行的答案；本系统给出可复跑的 `lineage verify` 与 `closure` 判定。这正是「证据运营」相对「写作辅助」的结构性优势。

### 5.3 优越性依据链（证据 → 推论 → 边界）

| 主张 | 直接证据 | 推论 | 不可越过的边界 |
| --- | --- | --- | --- |
| 门禁不可被 agent 绕过 | `mcp_server.py:53-101,3652-3653`；`runtime/app.py:378-399`；`test_runtime_write_guard.py:131-154`；AJS `.py` 中 `approval` 0 命中 | 治理从自律变为他律 | 只覆盖本系统暴露的 46 工具与 64 条路由；不等于「科学结论正确」 |
| 系统能发现并保留自己的失败 | `verdicts.py:32-138`；`projections.py:14-18`；`test-verdict.json`（1239/OK，另有失败判定留档）；AJS `QUALITY-LANE-2026-09.md:21,50` | 判定可复核、可过期 | 判定只覆盖 `research_agent/**/*.py` 指纹（`61-` §4.3 C4），不含前端/SPEC/脚本 |
| 上游变更让下游失效 | `lineage.py:445-506`；`study_closure.py:125-135`；`closure_profiles.py:19-31` | 证据链有失效语义 | 链只证明存在性与身份，不证明正确性/语义蕴含/可投稿；重启后在途任务不恢复 |
| 不自夸 | `ARCHITECTURE.md:400-415`；`58-:6248,6294` 已签 claim = 0；`README.md:389-401` | 对外口径可审计 | 这正是「优越性」不能推广到产出质量的理由 |

### 5.4 结论（明确回答用户的问题）

**在「科研智能体的治理与可审计性」这一范畴内，本系统相对 AJS 具有可确认、可复跑的优越性**：它把 AJS 只能写成 checklist 的证据资格、人工门、失效判定与拒绝纪律，变成了有白名单、有哈希、有测试、有指纹判定的运行时机制；并且它把「不能宣称什么」写进架构层而不是藏在 README 角落。其代价是复杂度、部署成本与 `0 active` 模块的成熟度。

**但这个优越性不是「更好的科研助手」**：AJS 在 744 个 venue 的领域规范知识、Stata/Python 计量骨架、官方源映射与安装即用性上明显更强；本系统没有 external held-out eval、没有真实导入/导出/签名、已签确证 claim = 0、29 个 SPEC 全为 draft/pilot。任何「论文质量更高 / 科研效果更好 / 已能自动做研究」的表述都**没有证据支持，本文不予论证**。二者更准确的关系是**互补**：AJS 回答「这个领域该怎么写」，本系统回答「凭什么可以这么写、什么时候必须停下来等人」。

---

## 6. 本轮实际修改（代码与文档）

| 文件 | 改动 | 对应维度 |
| --- | --- | --- |
| `apps/web/src/components/AppErrorBoundary.tsx` | 新增：class 错误边界，渲染恢复面板，明确「本地状态未改动、未触发门禁」 | 页面结构 / 异常与空状态 |
| `apps/web/src/main.tsx` | 在 `StrictMode` 内包住 `<App />` | 页面结构 |
| `apps/web/src/App.tsx` | `Suspense fallback={null}` → 可见「正在载入面板…」 | 页面结构 / 状态反馈 |
| `apps/web/src/styles/disclosures.css` | 新增 `.app-error-boundary`、`.overlay-loading` 样式 | 样式一致性 |
| `apps/web/src/state/workspaceStore.ts` | SSE `onerror` 增加降级为轮询的明确提示；静态构建失败 toast 不再误导为「启动 npm run dev」 | 状态反馈 |
| `apps/web/src/components/ContextPanel.tsx` | `gate-hint` 补充人工门出路（CLI 签核 / 重新载入 / `/live` 续跑） | 状态反馈 / 任务链路衔接 |
| `apps/web/src/domain/commandCatalog.ts` | 补 `id: "live"` 斜杠命令，使目录与 `sendMessage` 执行器一致 | 交互流程 |
| `apps/web/src/components/settings/OrchestrationOverview.tsx` | 未加载时不再用 3/8/4 兜底，改显示 `—` 与 `AUTO-EVOLVE UNKNOWN` | 结果呈现 |
| `apps/web/src/components/settings/SettingsSections.tsx` | About 页 `probeRuntime()` 动态显示 Runtime 状态；「不可宣称」改为与连接状态无关的架构边界；Guide 文案区分演示与 `/live` | 信息架构 |
| `apps/web/README.md` | 同步 TopBar 徽章文案与 `LOCAL DEMO CANDIDATE` 文案 | 文档一致性 |
| `Wellspring-Agent/**`（发布树） | 由 `build_release.py --prune` 同步以上文件并重建 MANIFEST | 交付一致性 |

**未改动**：任何 `research_agent/**/*.py`、`modules/*/SPEC.md`、CLI 命令面、门禁与判定语义；AJS 基准目录；`gateApproved` 状态语义；人工门位置。

---

## 7. 验证结果

- 前端 `npm run check`：**typecheck + 7 项单测 + `vite build` 全通过**（105 个 module 转换成功，11 个 JS chunk + 1 个 CSS 产物）。
- 静态构建 `vite build --mode static`：**通过**；产物中可检出「工作台渲染失败」与「静态演示模式」文案，9 个 `public/*.json` 资源齐全，页面引用与资源加载正常。
- 后端：`release_check.py` **0 blockers**；`build_release.py --check` 报 `content_drift: 0 / missing_in_release: 0`；54 项护栏测试 **OK**。
- 判定：`record_test_verdict.py --show` = `current | tests 1239 | current 032562c461289b05`（本轮未改 `research_agent/*.py`，故指纹未变；未重跑 35 分钟全量，理由充分且如实声明）。

---

## 8. 不可宣称

- 本文的「优越性」仅限 §5.1 限定的运行时治理范畴，**不是**科研效果、论文质量、领域覆盖或产品成熟度的优越性。
- AJS 的「没有某机制」是**基于本次检索的结论**（检索方法见 §1.4），不是对其上游仓库、StatsPAI 服务或作者意图的断言；其「刻意不建行为评测」是明确记录的设计决策，本文不评价其优劣，只对照差异。
- 本系统 29 个 SPEC 全为 draft/pilot、`active = 0`；`CapabilityRegistry` / `SkillRuntime` / 任意实验环境 / external held-out eval 仍是 roadmap。
- **已签确证 claim = 0**（`58-:6248,6294`），fixture 与 SIM 数字不是研究证据；前端的 1239/OK 判定只覆盖 `research_agent/**/*.py`。
- §3.8 的未修项仍然存在，本文未把它们写成已解决。

---

## 9. 复跑方式

```bash
# 前端（两套构建）
cd apps/web && npm run check
cd apps/web && npx vite build --mode static --outDir ../../runtime_data/static-build-check2 --emptyOutDir

# 后端护栏与交付一致性（用 Python 3.8）
python scripts/release_check.py
python scripts/build_release.py --check
python -m unittest tests.test_release_integrity tests.test_workspace tests.test_integration_files tests.test_docs_freshness tests.test_doc_interfaces tests.test_projection_contract -q
python scripts/record_test_verdict.py --show

# 基准目录数字核对（只读）
python -c "import json,glob; b=r'D:/Users/20691/Downloads/Research Skill调研/Awesome-Journal-Skills-main'; print(len(json.load(open(b+'/.claude-plugin/marketplace.json',encoding='utf-8'))['plugins']), len(glob.glob(b+'/**/SKILL.md',recursive=True)))"
```
