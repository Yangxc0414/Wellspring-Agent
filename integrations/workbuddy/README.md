# WorkBuddy 即插即用接入（Wellspring-Agent）

这个目录只提供**接入面**：MCP 配置模板、Skill 说明和只读自检。它不修改 `research_agent/` 的任何业务逻辑，不新增工具、不改门禁、不写 Claim/EA/Protocol/Signature。

## 它做了什么

WorkBuddy 通过 stdio MCP 启动 `Wellspring-Agent/scripts/research_mcp_server.py`；启动器把工作目录与 `PYTHONPATH` 固定到 `Wellspring-Agent/`，因此导入的 `research_agent` 包、29 份 `modules/*/SPEC.md`、工具表全部来自发行目录本身。**Wellspring-Agent 即是唯一运行目录**，不需要仓库根目录参与。

## 三个占位符

`mcp.workbuddy.json` 里的占位符需要替换成实际值后合并进 `~/.workbuddy/mcp.json`：

| 占位符 | 含义 |
| --- | --- |
| `<WELLSPRING_AGENT_ROOT>` | `Wellspring-Agent/` 的绝对路径（Windows 用正斜杠） |
| `<PYTHON_38_EXECUTABLE>` | Python 3.8 解释器的绝对路径；必须已装 `requirements-runtime.txt` 的依赖 |

> 不要使用工作区默认的 Python 3.13：它缺少 numpy / sklearn / fastapi 等依赖，会让工具在运行时报 ImportError。

## 安装

1. 把模板中的两个占位符替换后，**合并**（不是覆盖）到 `~/.workbuddy/mcp.json` 的 `mcpServers` 对象。
2. 在 WorkBuddy 的自定义连接器入口点击「信任」启用 `wellspring-agent`。新 MCP 不会自动激活。
3. 把本目录的 `SKILL.md` 放到 `~/.workbuddy/skills/wellspring-research/SKILL.md`，让 WorkBuddy 自动发现调用纪律。
4. 运行只读自检：

```bash
python integrations/workbuddy/check.py
```

自检只读取文件与工具表：不启动服务、不写文件、不触发任何门禁。输出的 `project_dir_present` 为 `false` 是**正常状态** —— 发行目录不带运行数据，`first_call` 会提示下一步。

## 首次调用（实测过的阻塞点）

发行目录里没有 `research-project/`。实测直接调用 `research_literature_fetch` 或 `research_innovation_review` 都会返回：

```
ProjectError: project directory does not exist: <root>/research-project
```

因此 WorkBuddy 里的第一步必须是 `research_project_init`（推荐直接用默认名 `research-project`），或 `research_bootstrap` 一次性初始化。之后 `research_host_contract` → `research_run` 才会产出 `literature.json` / `idea.json`。`SKILL.md` 的「调用纪律」已把这一步列为第 1 条。

**实测补充**：若 init 用了自定义项目名（例如 `my-project`），后续每个项目级工具都必须显式传同一个 `project_dir`；否则工具仍去找默认目录 `research-project` 并报同样的错。两种用法都验证过：用默认名可省略参数，用自定义名则一路带参数。此后 `research_literature_fetch` 在 `allow_network=false` 时会被正确拒绝（守卫生效），不是故障。

另外，MCP 工具面没有「输入问题直接返回 S1 spans」的轻量工具，也没有「输入 spans 直接生成 idea」的工具；文献调研与 idea 要么走 `research_run` 全流程，要么用本机 CLI（详见 `SKILL.md` 的「文献调研与 idea：当前能做什么」）。这是接入面的能力缺口，不是配置错误。

## 文献规模：默认不是「搜很多篇」

实测（Python 3.8，本机 CLI）：默认 fixture 语料只有 3 条（2 全文 + 1 摘要），`--max-sources` 从 3 调到 50，来源数恒为 3、span 恒为 5、`coverage_score` 恒为 0.454、`saturation` 恒为 `partial`；Q0 恒为 `pass`。用发行目录内 7 篇 CC-BY 冻结正文构成本地语料、`--max-sources 12`，则得到 7 来源 / 56 span / 1.0 / `saturated`。两种情况 Q0 都放行，所以门禁输出不能用来判断 idea 是否有综述级证据基础。

S1 现在会在 `warnings` 输出 `evidence_breadth=...`（独立来源/全文/span/覆盖度/saturation/`review_grade=yes|no`）。`review_grade=no` 时附可照抄的扩语料命令：

```bash
python -m research_agent literature run --question "<问题>" --source local --corpus-dir <dir> --max-sources 12
python -m research_agent pipeline run --topic "<问题>" --corpus-dir <dir> --max-sources 12
```

第一行纯离线、无条件可跑。第二行实测在无模型 key 时会停在 `awaiting host model ... (module=idea purpose=S2 idea candidates)`、退出码 3、不产出 run 产物（宿主模型交接，不是故障）；需用 `research_model_turns` + `research_model_respond` 回答 turn 后重跑，或只跑第一行。

`--source openalex` 只给摘要、不产 span，Q0 会 blocked；下载类工具（`research_literature_fetch` / `research_conference_fetch`）拿到 PDF 后仍须走 `--source local` 解析。完整边界与判据见 `SKILL.md` 的「文献规模：先扩语料，再谈 idea」。这是披露，**没有**给 Q0 加最小来源数下限（门禁语义变化，未做）。

## WorkBuddy 内跑大规模语料（实测）

发行目录不带语料，但 `research_run` 的 `source="local"` 读 `<project>/inputs/` 下的 PDF/TXT/MD（`max_sources` 1–30，默认 6）。把真实全文放进该目录（可用 `research_literature_fetch` / `research_conference_fetch` 下载，或自行放入），再传 `source="local"` + `max_sources=30`：

- `task_type="literature_review"` **实测可离线 `completed`**，产出 `literature.json` / `q0.json`，`fixture_mode=false`；
- `task_type="hypothesis_design"` / `full_research` **实测停在 `awaiting_host_model`（S2 idea）**，需 `research_model_turns` → `research_model_respond` 回答后重跑；本轮未实测续跑。

规模基准（开发根 CLI，用项目内 30 篇真实 arXiv PDF，不联网）：30 独立来源 / 240 span / coverage 1.0 / `saturated` / `review_grade=yes`。`modules/idea/SPEC.md` 0.21.0 修复后，S2 规则路径的跨来源候选从 **0/3 → 3/3**，`idea_review` 全判 `multi_source`；新增 `candidate_breadth=` 回执显式声明「无 novelty 证明、无留出集与人工评分、G1 人签」。**这只让证据广度可判定，不构成创新点质量提升的宣称**（`ARCHITECTURE.md:400-415`）。详见 `SKILL.md` 的「大规模真实语料 → 跨来源创新点」。

## 边界（与运行时一致）

- 46 个 MCP 工具里没有 approve / sign / freeze / publish / export；人工门只留在 CLI。
- 人在终端执行 `research_status` 给出的签核命令，WorkBuddy 负责把命令原样呈现，不代为执行。
- `fixture` 与模拟数据只用于流程验证，不得写成研究结论。

## 与本仓库其它接入面的关系

`integrations/mcp/` 是 Qoder / Zcode / Codex 的模板，`plugin/` 是通用插件清单，`.mcp.json.example` 面向仓库根目录的开发模式。本目录是**面向发行目录**的 WorkBuddy 入口；四者共用同一个 `research_mcp_server.py` 与同一份工具表，没有第二套业务逻辑。
