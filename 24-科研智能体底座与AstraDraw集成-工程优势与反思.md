# 24 · 科研智能体底座与 AstraDraw 集成：工程优势、反思与边界

> 日期：2026-10-23 · 性质：实现后的设计反思（不是效果报告）  
> 对应代码：[`research_agent/`](research_agent/) · 规格：[`modules/`](modules/) · 工作台：[`research_agent/web/`](research_agent/web/) · 规则：[`AGENTS.md`](AGENTS.md) · AstraDraw：[`research_agent/vendor/astradraw/`](research_agent/vendor/astradraw/)

## 1. 这次到底做了什么

把一个“静态 Demo + 设计文档”推进到**可运行、可测试、可最小演进的底座**：

```text
S1 文献 → S2–S3 假设 → S4 实验设计 → S6 SVG 绘图 → S8–S12 论文契约
                                      └──────────→ 基金申报（可选）
```

- 每个子智能体一份 `modules/<id>/SPEC.md`；代码读它，CLI 最小更新它；
- 产物是结构化 artifact（QueryPlan / Span / IdeaCard / DesignCard / FigureManifest / PaperContract / GrantPlan），不是聊天记录；
- 图表走 AstraDraw 的 scene→SVG；我们加 SVG 可访问性/安全/证据绑定审计；
- 论文与基金只产骨架和槽位，结果槽保持 `pending_evidence`；
- 工作台以“流水线 + 图 + 证据/稿件/运行记录”组织，不是长页宣传；
- 面向老师的静态创新演示页 `site/innovation/`：深色 hero + 五幕舞台，自动播放/手动切幕/全屏演示，数据来自同一 fixture，无 API。

## 2. 工程结构

```text
research_agent/
  specs.py            # SPEC 解析、校验、原子最小更新、章节 patch
  pipeline.py         # 模块编排（fixture，无 API）
  modules/            # 6 个子智能体，各自只依赖 contracts/ports
  adapters/           # fixture / parser / AstraDraw / SVG audit
  vendor/astradraw/   # 完整复制；上游无根许可证，本地只读
  web/                # 静态 Module Workbench（无 API）
modules/<id>/SPEC.md  # 唯一契约源
tests/                # 35 个契约/边界/CLI/SVG/RSI 测试
AGENTS.md             # 后续编码规则：先读/改 SPEC，最小 diff
```

**可验证的工程规则**：

- 没有全文，不生成 Span；摘要-only 永不成为证据；
- 候选必须带否证条件，不自动 G1；
- 设计只产草稿，不执行 run；
- SVG 无 script/foreignObject/外部 href，必须有 `role=img`、`title/desc`、唯一 ID、可解析 XML；
- Paper/Grant 不产生 claims、数字或科学观点；
- `spec update` 只改指定字段和 Changelog，正文不动；`spec patch` 只替换一个章节。

## 3. 与现有工作的差异（工程口径）

| 工作 | 强项 | 本研究刻意补的空位 |
| --- | --- | --- |
| DeepScientist | 本地工作区、逐轮 prompt、skills、UI | 把 skill/流程变更接到 SPEC + artifact/gate；避免“prompt 自动刷新无准入” |
| AI-Scientist-v3 | Docker/run 目录/rubric/单轮自验证 | 把 run 之后的证据、claim、稿件槽位连成可审计链 |
| AutoResearchClaw A-Evolve | 失败诊断→技能/prompt/knowledge 补丁 | 增加固定实例、public/hidden、租约与回滚（设计层） |
| ARIS | 多轮评审、citation/claim audit、meta-optimize/apply | 把独立审计放进统一模块契约与工作台；不让评审替代证据 |
| AstraDraw | 论文图→参考 prior→scene→SVG/PPTX | 不把绘图停在“好看”：加 SVG 审计、provenance、证据引用边界 |
| RSI-Anything | retained pair、incumbent、冻结评测 | 不自称 RSI；只做技能/过程的准入层（设计层） |
| 中文期刊/基金工具 | 格式、模板、语言 | 把语言/venue/基金路由成模块契约，不做“全能写作器” |

**我们想主张的不是“效果更好”**，而是三个可验证的工程差异：

1. **Spec-driven module**：每个模块的输入/输出/不变量可读、可改、可测试；修改一个模块不必理解全部代码。  
2. **Artifact/gate 中介**：模块只交换 artifact，不共享聊天上下文；claim/结果槽有硬边界。  
3. **Figure provenance**：scene、SVG、manifest、audit 一体；示意图不会被误绑成结果图。

> 这些是**设计贡献/工程贡献**；是否提升研究质量，仍需固定实例实验，当前没有效果数字。

## 4. 可验证的优势假设（待实验，不是结论）

| 假设 | 检验方式 | 当前证据 |
| --- | --- | --- |
| H1：SPEC 驱动的最小修改降低跨模块回归 | 给 6 个模块各做一次小改动，比较“有无 SPEC/测试”下的回归与返工 | 47 个测试通过；尚无对照实验 |
| H2：SVG 审计能拦截不安全/不可追溯图 | 注入 script/外链/空文本/重复 ID，检查 audit 是否拒绝 | 单测覆盖；已实现 |
| H3：结果槽机制阻止无证据数字进入稿件 | 结构化检查 PaperContract：claims=0、result slots=pending | 单测 + pipeline 输出 |
| H4：工作台降低任务发现成本 | 5–8 人可用性测试：找模块/看证据/看门禁的时间与错误率 | 尚未做用户研究 |

## 5. 反思：现在还不够好的地方

1. **fixture 不是科研**：文献是合成数据；没有真实 OpenAlex/中文库；不能据此谈检索效果。
2. **没有真实 run/EA**：实验设计只到 G2 草稿；论文结果槽没有 EA，导出必然阻断。
3. **写作/基金只是契约骨架**：没有正文生成、引用库、Word/LaTeX 导出；不是 ghostwriting。
4. **AstraDraw 上游无根许可证**：当前只本地使用；若公开部署，必须先解决授权/替换素材。
5. **工作台没有用户研究**：目前只做 1440/1024/390/320 的渲染、溢出、交互路径检查；不是可用性结论。
6. **平板端 inspector 被隐藏**：1024 布局不再拥挤，但模块规格详情需要下一轮做抽屉/弹层。
7. **SVG 视觉质量仍依赖 AstraDraw**：我们改进的是安全/可访问性/证据边界，不是审美判断；最终图需要人看。

## 6. 下一轮优先级

1. **真实检索 adapter**：OpenAlex 先做只读、无 key、限流；中文库只做授权 API，不抓取。
2. **EA/Run 账本**：把 experiment 模块从“设计草稿”推进到可接 `RunCapsule → EA → Claim` 的最小链路。
3. **论文/基金的真实模板**：中文期刊 GB/T 7714、学校 Word 模板；基金只做结构与合规，不生成科学观点。
4. **AstraDraw 适配层**：增加 figure spec 与真实论文图的 evidence_refs 绑定；保留上游原始脚本不动。
5. **可用性测试**：5–8 人完成任务（找模块、读证据、看阻断原因），再决定 inspector 抽屉/命令面板优先级。
6. **固定实例评测**：只在有真实 run/EA 后，做 H1–H4 的对照；没有数据不写“更好”。

## 7. 本地验证

```bash
python -m unittest discover -s tests -v   # 47 tests
python -m research_agent pipeline run \
  --topic "钙钛矿 界面 钝化 稳定性" \
  --venue zh_core_journal --grant nsfc \
  --primary-metric "湿热稳定性" --control "未钝化对照" \
  --output-dir research_agent/web/data
python -m research_agent web --port 8010
```

静态回归记录在 [`18-` §5.9](18-GitHub%20Pages部署与多智能体Skill设计.md)；工作台在 1440/1024/390/320 均无横向页面溢出，控制台无错误；图表 SVG 通过审计。
