# 科研 Skill 生态调研与动态流程编排：从固定流水线到能力图

> 版本：v0.2 · 日期：2026-10-23 · 性质：外部调研 + 架构反思 + demo 设计，不新增实验结果
> v0.2 增量：加入 `oss/` 三个**策展技能快照**（Scientific Agent Skills / Academic Research Skills / AI-Research-SKILLs），用实际 `SKILL.md` 核对“渐进加载、强制检查点、协议先冻结、六维 rigor review”等模式；快照只保留 README、LICENSE 与代表性技能说明，未下载完整脚本/参考，未运行。
> 上游依据：[01-组会纪要](01-组会纪要-核心判断与优先方向.md)、[02-需求书](02-需求书-科研自动化与写作平台.md)、[08-反思与差异化](08-反思与差异化工作方案.md)、[11-自进化循环](11-自进化循环设计-准入理由、跨循环继承、迁移与能力增益.md)、[13-创新点评审](13-创新点评审与主张收敛-需求对齐、开源对照与验证顺序.md)、[14-产品差异化](14-产品差异化与Demo反思-从证据链写作到证据运营工作台.md)、[15-调研补充](15-2026年9-10月调研补充与证据工作台实现.md)、[oss/README](oss/README.md)
> 证据纪律：star 数来自公开仓库页/二手报道的检索快照，只作“关注度”入口，不作质量或效果证据；外部效果数字未复现；本文中的流程、权限与指标均为 `[设计]`，demo 为 SIM

---

## 0. 一页结论

高 star 科研 skill 的共同点不是“提示词更长”，而是三件事：

1. **把程序性知识目录化**：每个技能是一个文件夹，`SKILL.md` 写用途、步骤、惯例、校验与版本；脚本与参考文档按需加载。
2. **渐进加载**：常驻上下文的只是短目录；完整指令、参考和脚本在选中技能后才读，避免上下文爆炸。
3. **可分发、可版本化**：技能可以装进 Claude Code、Codex、Cursor 等宿主，支持版本锁定与测试/安全扫描。

但它们大多停在 **“技能目录 + 固定 recipe”**：技能可以被选中、被串成一条预设流程，却很少回答：

- 跳过某个阶段后，哪类 claim / 导出权限必须被禁用？
- 一个技能产出的东西有没有 run/EA/span 支撑，能不能进入稿件？
- 技能升级、撤销或领域漂移后，依赖它的产物如何复核？
- 任务变化时，流程是重新编译，还是只能重跑同一条固定管线？

因此，我们的科研智能体不应再做一个“更大的技能目录”，而应把 **能力图、任务编译、技能运行时、证据权限、人工签核** 放在同一层：

> **技能决定“怎么做”，能力图决定“这次做哪些”，证据门禁决定“什么能留下”。**

---

## 1. 调研方法与口径

- 检索窗口：2026-08 至 2026-10-23；优先看科研 skill 仓库、公开 README、arXiv 摘要和二手榜单。
- 关注对象：技能数量、组织方式、加载方式、是否含脚本/测试/安全扫描、是否提供 workflow/编排、是否有人工检查点、是否接执行验证或证据链。
- **star 只作发现入口**：同一项目在不同报道中会出现 33k–53k 等不同快照；本文只记录范围与日期，不把 star 当质量、活跃度或效果证明。
- 外部系统的效果数字（K-Bench、任务通过率等）均为作者/项目口径，未复现，不进入本项目指标。

---

## 2. 代表项目与工作流

| 项目 | 规模/关注度（公开快照） | 工作流特点 | 对我们的启示 | 停在哪 |
| --- | --- | --- | --- | --- |
| **Scientific Agent Skills**（K-Dense） | README 177 skills；2026-08–10 报道约 33k–53k stars；arXiv 2609.00065 | 每个技能是 `SKILL.md` + 脚本/参考/模板；目录约 1.4 万 token，完整指令与参考按需加载；测试与安全扫描 CI；多宿主安装、版本 pin | 采用“短 manifest + 懒加载全文”；技能要有测试、版本和宿主无关的接口 | 技能库/工具箱；不定义 claim 级证据契约，不处理变更后的维护与撤销传播 |
| **Academic Research Skills** | 约 42.1k stars（2026-08 快照） | 从深度研究、写作、评审到全流程编排；保留人工检查点，避免一次性生成整篇 | 流程要有检查点，不能把整篇论文丢给模型一次性完成 | 偏写作/评审；不接独立重跑、claim 槽位与导出硬门 |
| **Nature-skills** | 约 34.8k stars（2026-08 快照） | 检索、下载、引用管理、数据分析、绘图、实验日志、论文卡片；中文场景适配 | 中文科研用户需要“检索—引用—图表—写作”连续体验 | 工具集/写作工作流；不判断结果是否来自重跑，不做失效传播 |
| **AI-Research-SKILLs**（Orchestra） | 96 skills；约 11.6k–14.5k stars | 训练、评测、推理、模型架构等技能；`autoresearch` 双循环从文献到论文，按意图路由 | 技能应有“编排层”，但编排不能写死为一条流水线 | ML/AI 研究为主；固定双循环 recipe，缺少证据权限与人工签署 |
| **ARIS / Auto-claude-code-research-in-sleep** | 约 14.6k–15.6k stars | Markdown-only skills；plan / draft / 跨模型对抗审 / 迭代 / 持久化五步 loop；Zotero/Obsidian 集成 | 研究流程可以轻量、可读、可改；跨模型评审是检查点 | 偏事后/对抗评审；不跑独立复现，不把评审结论变成 claim 级硬门 |
| **AutoResearchClaw** | 约 14.5k stars；21 skills | 从想法到调研、方案、代码、实验、论文；阶段检查点、HITL、PRISMA 文献流程、领域流水线 | 阶段检查点与失败记录值得借鉴 | 固定阶段管线、领域特定；没有跨版本证据传播与可签署导出 |
| **PaperSpine** | 约 4.8k stars（2026-08 快照） | 先找研究动机与论证主线，再用证据蓝图和修改记录重建结构 | 与我们的“双轴审计”相邻：结构之外还要看论证 | 写作重构；不接执行证据与变更维护 |
| **Research-Paper-Writing-Skills** | 约 6.0k stars（2026-08 快照） | ML/CV/NLP 论文结构、动机、方法表述、实验组织 | 写作技能应明确“已有结果才可用”，不能补创新 | 只覆盖写作；不判断证据是否成立 |

> 读法：这些项目在“技能数量、加载效率、宿主兼容、写作体验”上很强；我们不应在数量上竞争。我们的差异应落在**技能与证据契约、流程与证据权限的联动**。

### 2.1 本地策展快照（2026-10-23）

为避免只读摘要，我从三个仓库各取了 README、LICENSE 与代表性 `SKILL.md`，放在 `oss/`，未下载完整脚本/参考，未运行：

| 目录 | 仓库 | commit | 许可证 | 源文件 | 体积 |
| --- | --- | --- | --- | ---: | ---: |
| `Scientific-Agent-Skills-curated/` | K-Dense-AI/scientific-agent-skills | `593377b` | MIT | 7 | 161.9 KB |
| `Academic-Research-Skills-curated/` | Imbad0202/academic-research-skills | `3224a27` | CC BY-NC 4.0 | 6 | 280.7 KB |
| `AI-Research-SKILLs-curated/` | Orchestra-Research/AI-Research-SKILLs | `773a529` | MIT | 6 | 136.8 KB |

共 **19 个源文件 / 579.4 KB**；每个目录另有 `CURATION.md` 与 `metadata.json`（含 commit、文件大小、许可证与省略说明）。`Academic-Research-Skills` 是 **CC BY-NC 4.0**，只能用于非商业阅读/对照，不能直接并入产品交付物。

实际读到的四个关键点：

1. **K-Dense `scientific-writing` 已经把“证据绑定”写成不可协商规则**：不编造引用/数字/方法/署名；每个事实/数字 claim 必须映射到已验证的证据 ID；人类 verifier 必须打开来源确认命题与 locator，并记录谁在何时验证；还单列了 “Verification scope”（声明本技能不验证什么）。这比“写作时引用一下”强得多，也说明**我们的 skill manifest 需要 `evidence_contract` 与 `verification_scope` 两个字段**，不能只写“会写作”。
2. **K-Dense `literature-review` 的 7 阶段是“可复现检索”而非“多搜几个库”**：记录 query/date、PRISMA records/reports/studies 分层、排除理由、两名评审的 eligibility、DOI 存在不等于 claim 支持。我们的 P1 工作台已有 query/span/冲突，但还缺少 “检索日期 + 覆盖回执 + 排除理由” 的完整 UI；这可以直接补进 Retrieval 视图。
3. **Academic Research Skills 是“固定 10 阶段 + 状态机 + 强制检查点”**：10 个 stage 有明确 deliverables，2.5/4.5 是 integrity 边界，review/re-review/re-revise 有回退，MANDATORY checkpoint 不能自动跳过；但它仍是一条固定 pipeline。**我们应借它的 checkpoint/state-machine 纪律，而不是照搬 10 阶段顺序**；能力图 + 模板投影才能让“换输出类型”不用重写流程。
4. **AI-Research-SKILLs 的 `autoresearch` 明确说“two-loop 是节奏，不是铁路”**：可以随时回到文献、改问题、pivot；实验前把 protocol commit 到 git，形成“计划先于结果”的时间证明；用 `research-state.yaml` 与 `findings.md` 记录状态/发现；按领域路由到具体 skill。rigor-reviewer 又给出六维评审：evidence relevance、falsifiability、scope calibration、argument coherence、exploration integrity、methodological rigor。**这正好支撑我们的双轴审计**：结构闭合是阻断轴，六维 rigor 是建议轴，不能合并成一个分数。

## 3. 五个可复用模式

1. **短目录 + 渐进披露**：技能目录只保留名称、触发条件、输入输出和少量示例；完整步骤/参考/脚本在选中后加载。demo 里对应“Skill manifest + 详情抽屉”。
2. **过程即文件夹**：`SKILL.md`、脚本、模板、测试、许可证放在同一目录；技能是可版本化的工程对象，不是一次性 prompt。
3. **workflow skill**：除了单点工具，还要有“把多个技能串起来”的编排技能；但编排应有输入、输出、失败去向和人工检查点。
4. **dry-run 与测试**：技能加载前先在样例上跑通；有测试/安全扫描/版本 pin，失败不得激活。
5. **宿主无关**：技能通过标准目录/安装器分发，不绑定单一模型或 IDE；我们的工作台也应能调用外部 skill，而不是把技能硬编码进 UI。

---

## 4. 它们没有解决的四个问题

### 4.1 目录 ≠ 组合

技能库回答“有哪些能力”，但不回答“这次任务需要哪些能力、按什么依赖顺序、哪些可以跳过”。一个 177 技能的目录仍然可能被一条固定 recipe 驱动。

### 4.2 跳过阶段 ≠ 知道失去什么权限

多数流程只把阶段当步骤；跳过“检索”后仍然可以写引用，跳过“复现”后仍然可以写结果段。我们需要 **evidence permissions**：阶段被跳过，对应的 claim/export 权限自动关闭，而不是靠人记得。

### 4.3 技能成功 ≠ 证据成立

技能可以“跑完并返回结果”，但结果可能没有独立重跑、没有 span、没有 EA。技能输出必须是**带 ID 的 artifact**，进入 claim/句/图前仍要过证据门禁。

### 4.4 技能升级/撤销 ≠ 依赖产物自动复核

技能是版本化对象；升级、撤销、领域漂移后，依赖它的产物必须进入复核。多数技能库只做安装/卸载，不做依赖闭包与失效传播。

---

## 5. 我们的设计：能力图 + 任务编译 + 技能运行时

### 5.1 三层分离

```text
能力层  Capability Graph：P0…P8 是能力节点，边表示依赖/回退，不是固定顺序
配方层  Workflow Template：完整论文 / 快速复现 / 综述 / 申请书 / 自定义
执行层  Run Instance：钉住 template@version，记录已完成节点、跳过原因、证据状态
技能层  Skill Runtime：技能 manifest、权限、dry-run、租约、产物 provenance
证据层  Evidence Permissions：跳过阶段 → 关闭对应 claim/export 权限
```

**关键**：模板只是能力图的一个投影；运行实例只认 `template@version`；技能只被能力节点调用，不能自己改流程。

### 5.2 任务编译

输入：研究问题、输出类型（论文/复现报告/综述/申请书）、预算、体裁、已有材料。
输出：最小能力子图 + 每个节点的 gate/产物/人工检查点 + 允许的 claim/export 类型。

例如：

- 完整论文：P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8；
- 快速复现：P0 → P1? → P3 → P4 → P5 → P7；跳过 P2/P6，禁用 manuscript_claim；
- 综述核验：P0 → P1 → P2′ → P6 → P7；跳过 P3/P4/P5，禁用 result_claim；
- 国自然申请书：P0 → P1 → P2′ → P3′ → P6 → P7；跳过 P4/P5；
- 自定义：逐节点开关，硬门 P0/P3/P5 不可跳过，P7 可跳过但禁用导出。

### 5.3 动态重规划

- P4 失败 → 回到 P3 修订协议；不是“再跑一次”；
- P7 阻断 → 回到 P6 重写/降级；不是“改导出格式”；
- 新证据/ChangeSet → 进入 RWMT 影响闭包，重新计算受影响 claim/句/图；
- 技能撤销 → 依赖产物进入复核，必要时回退到上一个闭合版本。

### 5.4 技能运行时

- 加载：manifest/签名/权限/dry-run → `pilot`；
- 运行：只生成 artifact；不得创建 claim；
- 准入：通过样例与适用域判定后，才可 `active`；
- 撤销：租约失效，依赖产物进入复核；
- 过程协议：按阶段 type 绑定，不按数组下标；模板重排不破坏协议。

### 5.5 从本地快照得到的五个补丁

1. **Manifest 补字段**：除了版本/权限/证据契约/dry-run，还要有 `allowed-tools`、`compatibility`、`verification_scope`（本技能不验证什么）、`license`、`last_reviewed`。我们当前 demo 的 skill 卡已展示前四类，但还缺后两类；应在详情抽屉补齐。
2. **渐进披露补全文**：技能卡只放短摘要；点击“查看 SKILL.md”再懒加载完整步骤/参考。当前 demo 只有摘要，没有全文入口，容易把“卡片”误当“技能”。
3. **强制检查点独立于模板**：无论选完整论文、快速复现还是自定义，P0 立项、P3 协议冻结、P5 判定、最终签署都不能被模板裁掉；模板只能裁“可选能力”，不能裁“责任门”。当前 flow 视图已把 P0 设为硬门，但 P3/P5 仍需在“需要 result_claim”时强制保留，并在运行日志里记录。
4. **运行前冻结协议**：借 autoresearch 的“先 commit protocol，再跑实验”，技能运行前要写入 protocol hash、输入快照与预测；RunCapsule 记录“计划先于结果”。当前 demo 有 RunCapsule，但技能运行还没有 protocol freeze 字段。
5. **六维 rigor 作为建议轴**：rigor-reviewer 的 evidence relevance / falsifiability / scope calibration / argument coherence / exploration integrity / methodological rigor 可以成为我们的“论证完整性”建议轴，但**不能替代结构闭合的阻断轴**；两者分开报告，避免用一个总分掩盖失败维度。

另外，K-Dense 的检索工作流提醒我们：P1 应当记录 **query、日期、覆盖回执、排除理由、records/reports/studies 三层计数**；当前 demo 的检索漏斗有计数和来源卡，但还没有“检索日期 + 覆盖回执 + 排除理由”的完整展示，这是下一轮最该补的真实细节。

---

## 6. demo 改动

### 6.1 新增“流程”视图

- 五个配方按钮：完整论文 / 快速复现 / 综述核验 / 国自然申请书 / 自定义；
- 能力节点条：P0…P8，显示 required/optional/skipped、gate、技能槽；
- 回退边：P4 失败 → P3；P7 阻断 → P6；ChangeSet → 影响闭包；
- 证据权限条：literature_claim / result_claim / manuscript_claim / export / memory，随跳过阶段自动关闭；
- “自定义”：点击可选节点切换跳过；P0/P3/P5 为硬门，不允许跳过。

### 6.2 新增“技能”视图

- 四个技能：检索式生成、统计结果复现、中文核刊结果段、图表一致性检查；
- 每个技能显示 manifest、权限、证据契约、dry-run、artifact；
- manifest 还展示 `allowed-tools`、`compatibility`、`verification_scope`、`license`、`last-reviewed`，对应本地快照中真实 SKILL.md 的字段；
- 加载为 `pilot`，运行后 `active`，撤销后依赖产物进入复核；
- 技能只生成 artifact，不创建 claim；不能绕过导出硬门。

### 6.3 验收

- 切换配方，rail、流程节点与证据权限同步变化；
- 点击可选节点可切换跳过；硬门点击时明确拒绝；
- 加载/运行/撤销技能，状态与事件日志同步；
- 360–1440px 无页面级横向溢出；
- 所有数字、状态与传播标注 SIM。

---

## 7. 与现有工作的差异

不是“技能数量更多”，也不是“又一个 autoresearch recipe”。我们的差异是：

- **能力图而不是固定流水线**：阶段是能力节点，模板是投影，运行钉版本；
- **证据权限与流程联动**：跳过阶段自动关闭对应 claim/export，不靠人记；
- **技能运行时与准入**：manifest、dry-run、租约、撤销传播，而不是“装上就用”；
- **变更后的维护与签署**：技能输出进入 claim/句/图，仍要重新闭合、作者/PI 签署；
- **中文学术长文**是验证场景，不是能力边界。

在本轮调研范围内，把“技能加载 + 能力图编排 + 证据权限 + 变更维护 + 签署导出”接成同一条可操作链的原型仍较少见；这不是单点首创，而是交集与一体化。

---

## 8. 不可宣称

- 不写“首个科研 skill 平台 / 首个动态流程系统 / 唯一”；
- 不把 star 数当质量或效果证据；
- 不把外部项目的任务通过率、K-Bench 数字当我们的结果；
- 不说“技能加载 = 能力可靠”；技能仍需 dry-run、适用域判定、撤销传播；
- 不说“动态流程 = 自动科研”；流程可调不等于证据成立；
- demo 全部为 SIM，C1–C4、E7/E8 未运行。

---

## 9. 下一步

1. 在 demo 中实现“流程”视图与“技能”视图（本次同步）；
2. 选一个真实任务，做一次“技能加载 → 产物 → claim → 导出”的纵切；
3. 对 10 个变更场景比较配方切换/技能撤销后的复核闭包；
4. 把“技能失败/技能撤销”纳入负结果与审计记录。

---

## 附录：来源

> 服务化落地：本文的能力图/技能运行时如何映射为 BFF、Workflow、Evidence、Execution、Skills、Impact、Closure、Audit 等服务，见 [17-基于 Skill 契约的上层微服务架构](17-基于Skill契约的上层微服务架构.md)；本文不定义部署形态。
> 公开部署与多智能体分工：本文的能力图/技能运行时如何落到 GitHub Pages、Actions 与本地运行时，以及 1+4+人 的角色契约与 typed handoff，见 [18-GitHub Pages 部署与多智能体 Skill 设计](18-GitHub Pages部署与多智能体Skill设计.md)；该文不改变本文的技能权限设计。

- K-Dense Scientific Agent Skills：https://github.com/K-Dense-AI/scientific-agent-skills ；arXiv 2609.00065
- Academic Research Skills：https://github.com/Imbad0202/academic-research-skills
- AI-Research-SKILLs：https://github.com/Orchestra-Research/AI-Research-SKILLs
- ARIS：https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep
- AutoResearchClaw：https://github.com/aiming-lab/AutoResearchClaw
- PaperSpine / Research-Paper-Writing-Skills / Nature-skills：公开仓库与 2026-08 科研 Skill 榜单（二手报道；star 为快照）
- 榜单口径：https://m.toutiao.com/article/7673257316845748742/ （2026-08-12 快照，二手报道）
- 本地策展快照：[Scientific-Agent-Skills-curated](oss/Scientific-Agent-Skills-curated/CURATION.md)（MIT，`593377b`）、[Academic-Research-Skills-curated](oss/Academic-Research-Skills-curated/CURATION.md)（CC BY-NC 4.0，`3224a27`）、[AI-Research-SKILLs-curated](oss/AI-Research-SKILLs-curated/CURATION.md)（MIT，`773a529`）；各目录的 `metadata.json` 记录文件大小与省略范围。
