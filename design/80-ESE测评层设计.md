# 80-ESE 测评层设计——把已有的实证严谨性收束为一等能力

> **方向修正（2026-11-16，用户决策）：本文原方案"新增 modules/evaluation + eval 命令组"作废。ESE 工作内容不进系统代码——留在研究层（协议人写、分析用独立脚本读系统产物、报告进论文）。系统定位为"被验证对象 + 产物供给者"，已有的预注册/区间门/underpowered 守卫按原样使用，不扩不删。唯一可选的能力级 glue 是 exec-port flashrsi 面注册（为了"能跑外部引擎"，不做也可直跑 CLI）。§4–§6 按此降级理解。**

> 状态基线：2026-11-16。方向确认：**前后端通用骨架不变，后续测评/验证统一按 ESE（empirical software engineering）方向做**。本文审计现有 ESE 资产、找出散落与缺口、设计收束层。承接 78（方法矩阵）、79（系统服务论文研究）。

## 1. 边界确认

- **通用层不动**：CLI/MCP/runtime/前端/门禁/dispatch 全部复用；评测不新增系统模块。
- **ESE 只管"测评与验证"**：机制正确性验证（测试）仍在，但研究级测评（效应、区间、效度）按 ESE 规范，**在研究层完成**（仓库外层脚本与文档），不写进 research_agent。
- **一条铁律**：**评估不产生判定。** 判定仍只出自 verdict-ledger 单点（75 §4.2）；ESE 分析只引用系统产出的 verdict/claim，不新增判定语义。

## 2. 现状审计：ESE 资产已经长在系统里

| ESE 要素 | 现有实现 | 成熟度 |
| --- | --- | --- |
| 机器绑定预注册 | `study_preregistration.py`：question/hypothesis/analysis/decision_rule 人写、`TODO(` 占位拒绝加载、study hash 漂移即拒、closure 拒收漂移 sidecar | **强**（study） |
| 受控实验设计 | study 因子×水平、seeds、budget、min_delta、`normalize_design` | **强**（study） |
| 区间估计 | `search_lab._paired_diff_interval`：配对均值差 + t 95% CI；n<MIN 截断为 underpowered；**信息性判据**（区间必须窄于效应）；seeds_for_80pct | **强**（study） |
| 判定门 | `study_claims`：**只有区间不含零的比较才能成为断言**（DECIDABLE/NOT_DECIDABLE 单点） | **强**（study） |
| 配对 A/B + 功效守卫 | `memory_ab`：per-idea delta、MIN_PAIRS=4、"below 4 paired ideas no direction is reported"、边界自述"cannot demonstrate" | **中**（无区间/效应量） |
| 实验断言 | `experiment_runner._parse_assertion`：点值 vs 目标 ±tolerance（`>=/<=/==`） | **弱**（点证据，非区间门） |
| 演示/实证分离 | fixture_mode、demo 标记、claim_eligible=false、host_label 自报未验证 | **强** |
| 复现包 | claim/EA/RunCapsule/closure/lineage + 复跑命令 + fact-baseline 台账 | **强** |
| 设计审计 | design_audit / ccfa_audit / study_integrity / study_replication / support_calibration | **中-强** |
| 效度威胁 | 散见 75 §4（内容寻址≠防篡改、dispatch≠门禁、多会话≠模型多样） | **弱**（散文，无结构字段） |

**结论：不需要重建统计引擎——需要的是"收束"：统一入口、补齐效度与报告、把弱口径拉齐。**

## 3. 缺口（按对论文测评的阻塞度）

1. **无统一测评入口**：study/memory-ab/experiment/外部引擎各自为战；论文第 6 章的"测评"没有一等命令面。
2. **效度威胁无结构**：construct/internal/external/conclusion 四类未入报告 schema（任务书要求"清晰说明优势与局限"，评审必看）。
3. **报告无 ESE 清单**：缺 Wohlin/Runeson 式报告结构（背景/RQ/设计/对象/变量/分析/结果/威胁/结论），论文章节不能从报告结构化派生。
4. **先验功效未暴露在协议期**：`seeds_for_80pct` 存在但只在分析后算；协议期就该给出"最小可检测效应/所需种子"。
5. **experiment claim 的点证据口径**：`±tolerance` 不是区间门；论文级实验须走区间口径或显式标注"点证据"。
6. **多比较/度量依赖无记账**：fact-baseline 已记录"效应量是度量依赖的"（AUC headroom 事件）与 M1 的 35% 未解释——多断言族的 multiplicity 与度量选择偏差需要结构字段。
7. **外部引擎未成为评估案例**：flashrsi 面未注册（exec faces=bridge/host_agent/inprocess），多引擎对照无法进同一协议。

## 4. 设计：ESE 测评层的五段结构

```
① Protocol（协议期）
   eval-protocol 扩展 study-preregistration：
   + design_type（controlled|factorial|quasi|case|benchmark）
   + 先验：最小可检测效应 / 所需种子（复用 seeds_for_80pct）
   + validity.expected（四类威胁的预判与缓解）
   + claim_family（本次实验属于论文哪一族断言，供多重性记账）
        │ hash 绑定（已有机制）
② Execution（执行期）
   复用现有面：study search / memory ab / experiment run / exec-port（flashrsi 面待注册）
   不改执行器；run 产物记录 protocol_sha256
        │
③ Analysis（分析期）
   复用 _paired_diff_interval；统一输出块：
   {n, mean_diff, ci95_low/high, underpowered, informative, seeds_for_80pct}
   memory-ab 补同口径区间；experiment 点证据显式标注 evidence_kind=point
        │
④ Verdict（判定期，不动）
   仍由 verdict-ledger 单点；评估层只引用 verdict_id
        │
⑤ Report（报告期，新增最小件）
   eval-report-0.1：ESE 清单八段 + validity.observed + reproduction（claim/capsule/lineage 指针 + 复跑命令）
   前端沿用通用渲染（结构化 JSON）
```

**系统影响：零新模块。** ESE 三件套放在仓库外层 `thesis-eval/`（不进 research_agent、不进发布同步）：

```
thesis-eval/
  protocols/   PROTO-*.md      # 人写：RQ/假设/设计/分析计划/决策规则/效度预判
  analysis/    analyze_*.py    # 独立脚本：只读系统产物 → 区间/效应量 → eval 读数
  reports/     EVAL-*.md       # ESE 八段报告 + 实测效度 + 复跑命令
```

- 分析脚本**只读**系统产物（study/memory-ab/experiment 输出、claim/EA/capsule），不写回、不签核、不产生判定。
- 唯一可选的能力级 glue：exec-port 注册 flashrsi 面（为了"能跑外部引擎"；不注册亦可直跑 CLI）。
- 系统侧代码改动：无（如做可选 glue，按 SPEC-first 最小 diff + 测试）。

## 5. 落地顺序（与 78/79 的进度对齐）

1. **试点 = 79 第一条 loop（memory ab → signed claim）**：产出入 `thesis-eval/` 外层分析——`analyze_memory_ab.py` 只读 memory-ab 产物，计算配对区间/效应量（口径参照 study 的 `_paired_diff_interval`，但脚本独立）→ EVAL 报告 → 第 6 章直接派生。试点会暴露 memory-ab 区间缺口——在**外层脚本**补齐，不改系统。
2. **泛化 study**：study 已有最严口径与区间输出，报告直接引用其产物，**零代码改动**。
3. **（可选）flashrsi 面注册**：多引擎对照（76）进同一协议，Phase 3 的 localqa 难题池实验用它；不注册则直跑 CLI + 外层分析。
4. **论文第 6/7 章**：表格从 EVAL 报告字段与 fact-baseline 直出。

## 6. 验收与风险

**验收**：EVAL 报告按 ESE 清单完整（背景/RQ/设计/对象/变量/分析/结果/效度/复跑）；分析脚本可在干净环境重跑系统产物得到相同读数；1487 测试保持绿（系统零改动；若做可选 glue 则另加测试）；fact-baseline 登记试点读数。

**风险与边界**：
- 小样本区间在小 n 下退化——已有 underpowered 截断与信息性判据，评估层**不得**提供"凑显著"工具（不做 p-hacking 助手）。
- multiplicity：按 claim_family 记账与提示，**不自动改判**（判定仍单点+人签）。
- 度量依赖（fact-baseline 的 headroom 教训）：eval-report 必填"度量选择理由与替代度量"字段。
- 自反案例的效度威胁（研究者=开发者）：validity.observed 必须显式列出，第二签核者缓解。

## 7. 结论

ESE 不是要在系统外再搭一套评测台，也不是要写进系统：**把已经长在 study/memory-ab/claims 里的实证严谨性当作被验证对象，用外层协议卡+分析脚本+ESE 报告去验证它**。通用前后端不动，判定仍单点，系统零改动。下一步从 `thesis-eval/` 的第一张协议卡 + memory-ab 外层分析脚本开始。