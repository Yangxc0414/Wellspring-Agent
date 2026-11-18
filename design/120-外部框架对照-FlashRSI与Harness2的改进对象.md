# 120-外部框架对照：FlashRSI、Harness² 与我们系统各自的"改进对象"

> 状态基线：2026-11-18。老师布置了 FlashRSI 跑通与 Harness² 了解；本轮借这次对照，回答一个设计问题：**我们和这些 RSI 框架到底在优化什么，哪些能借、哪些不能借**。
> 边界：这是定位与设计反思，不是 benchmark 结果；FlashRSI 的真实 evolution 仍卡在 Docker（见 docs/组会准备）。

---

## 1. 三个系统，三种"改进对象"

| 维度 | FlashRSI | Harness² | 我们（Wellspring-Agent / research-agent） |
| --- | --- | --- | --- |
| 一句话 | 多算法/多 harness/多 benchmark 的统一 RSI 实验台 | 固定权重下的递归 agent harnessing 框架 | 证据闭合、可人签、面向 ESE 研究执行的科研智能体运行时 |
| 改进对象 | harness（prompts/tools/memory/skills/orchestration） | harness（两级：task-level + harnessing-level） | 研究过程的证据与判定；harness/流程作为受治理候选 |
| 优化信号 | benchmark 分数（held-out/test） | 行为对比（Propose–Probe–Compose），不依赖 ground truth | 证据闭合 + 人签 claim + held-out 研究任务符合性 |
| 是否训练权重 | 否 | 否 | 否 |
| 产物 | snapshots / trajectories / result.json / end-summary | 改进后的 harness + improvement harness + 轨迹 | run-capsule / EA / claim / closure / lineage |
| 治理 | 实验台本身不做人签 | 框架不负责人签 | 四人工门（G1/G2/S5b/G5）+ 判定总线；签名只在 CLI |
| 规模 | 13 算法 / 31 benchmark / 7 harness | 3 benchmark（JobBench/LAB/WorkBuddy），OpenCode/Codex executor | 33+ 模块；ESE 全链真实跑通（8→24 篇、3→6 候选） |

一句话：**FlashRSI 优化"模型外执行系统"并用分数证明；Harness² 优化"harness 的递归改进机制"；我们优化"研究结论的可信与可签署"**。三者可以叠加，但不是同一件事。

---

## 2. 能借的三点

1. **Snapshot 血缘与轨迹记录**：FlashRSI 每次 run 保存候选资源、轨迹、最终 Snapshot。我们的 RSI 控制面有候选/租约/世代/回滚，但"每次候选改动的资源 diff + 执行轨迹"还不够细；可以按它的 snapshots/trajectories 结构补齐。
2. **OOD / near-domain 评估分层**：FlashRSI 的 benchmark 矩阵强调 source / near-domain / far-OOD。我们的 held-out rubric 目前只有"冻结任务卡"，缺"同域/近域/远域"分层；design/83 的 M3 可以照这个切。
3. **一键实验接口**：FlashRSI 用 CLI + YAML 把"算法×benchmark×harness"变成一次 run。我们的 pipeline 已经是一键，但没有 benchmark 化的"同一任务多配方对照"接口；R1/R2 的对照还是手工跑。

---

## 3. 不能借的三点（也是我们的差异化）

1. **不能把 benchmark 分数当唯一信号**：我们的对象是研究 claim；分数高不等于证据闭合。demo 上也必须继续写"机制 ≠ 效果"。
2. **不能把人签门交出去**：FlashRSI/Harness² 都不负责人签；我们的 G1/G2/S5b/G5 是设计核心，不能为了自动化率而移除。
3. **不能把"研究任务"简化成"任务分数"**：ESE 研究有方法合规、协议冻结、复现与适用域；这些不在 RSI benchmark 的评分维度里。

---

## 4. 对 demo 与论文表述的含义

- demo 里不应出现"我们的 RSI 比 FlashRSI/Harness² 更强"这类话——没有对照实验，也没有同一 benchmark；
- 可以写的是："我们用同一套 RSI 框架做对照实验台；我们的贡献在证据治理与科研任务执行"；
- 论文的 related work 应把三者并列：FlashRSI（实验台）、Harness²（递归 harnessing）、我们（证据闭链 + 人签 + ESE 执行），避免"又一个 RSI"的定位。

---

## 5. 组会后的联合实验提案（待老师确认）

1. 先用 FlashRSI 的最小 run 跑通（Docker 就绪后）；
2. 把"科研任务执行"作为 harness 层（prompts/流程/工具配置），用我们已有的 held-out research rubric 做评分信号；
3. 对照：base harness vs 经 FlashRSI 演化的 harness；指标用 rubric 通过数 + claim 证据闭合率，而不是 benchmark 分数；
4. 报告时明确：n 小、探索性、人签仍是最终门。

---

## 6. 本轮落盘

- 新增本对照文档（design/120）；
- 组会准备稿：docs/组会准备-FlashRSI跑通与Harness2理解.md（含跑通路线、Harness² 三层理解、15–20 分钟汇报结构）；
- 未改代码；未改变任何门禁。
