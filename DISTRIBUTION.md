# DISTRIBUTION · Wellspring-Agent 发行说明

本目录是 **Wellspring-Agent** 的发行副本——"证据闭合的科研智能体运行时"的开源打包。根目录 `README.md` 是完整项目文档；本文件只回答三件事：这是什么、怎么再生成、排除了什么。

## 1. 名称与代码的关系

Wellspring-Agent 是发行名；Python 包名保持 `research_agent`、CLI 保持 `python -m research_agent`（遵循"不重命名公开模块/CLI 命令"的工程约束，见 AGENTS.md §3）。

核心主张浓缩为四个判定（详见 ARCHITECTURE.md 与根 README 的"当前事实基线"）：

- **资格判定**：这句话有资格写吗——span-only 证据
- **完成判定**：这次运行能签吗——RunCapsule → EA → Closure 11 项 → 作者签署
- **失效判定**：输入变了谁失效——lineage stale 传播、导出锁死
- **供给判定**：模型草稿能信到哪——生成可移植，证据资格不可移植

## 2. 再生成（同步上游代码）

```bash
python scripts/build_release.py            # 从仓库根同步本发行目录
python scripts/build_release.py --check    # 只报告 drift，不写盘（CI 守卫）
```

工程性质：

- **构建产物，不是第二份源**：本目录由仓库根脚本化生成；手改本目录就是 invisible drift，应改根目录再重跑脚本（旧脚本 `package_wellspring.py` 已废弃，其清单格式与现行不兼容）；
- **清单可核验**：`MANIFEST.txt` 记录每个文件的 relpath/sha256/bytes，`tests/test_release_integrity.py` 逐文件比对哈希，并断言"目录里每个文件都被清单解释"；
- **凭据与本地路径门禁**：`scripts/release_check.py` 扫描凭据模式与本机绝对路径，命中即 blocker；
- **确定性**：同一仓库状态 → 同一 MANIFEST，可审计、可重放。

## 3. 包含与排除（provenance）

**包含**：代码（research_agent/modules/tests/scripts）、前端（apps/web、site）、接入（integrations）、核心文档，以及**作者自有设计档案**——00–70 号设计文档、组会汇报.md、trees/papers/single-loop 笔记、deploy/plugin 配置。以上均为文本源，随仓库公开（作者已确认；文档许可待定，见 LICENSING.md）。

| 排除 | 原因 |
| --- | --- |
| `figures/`（根目录旧综述图）、`docs/`（审计截图）、PDF/DOCX/PPTX 二进制 | 媒体不是源；integrity 测试限定 bundle < 40 MB（source-sized）。例外：README 引用的四张策略图 PNG（`figures/01–04`）为 release-owned 媒体，直接入库并进 MANIFEST 计账 |
| `research_agent/vendor/astradraw/` 大部分 | 第三方本地拷贝，无再分发授权；只保留 renderer/components/references/examples 与目录广告所需的 scene（THIRD_PARTY_NOTICES.md） |
| `research_agent/web/data/`、`runtime_data/` | 运行产物与研究数据（私有） |
| `manuscript/`（未发表投稿）、第三方参考仓库、`.mcp.json`/`.env` | 未发表/无授权/含本机路径与密钥 |
| `node_modules / dist / test-results` | 构建产物不入库（含历史 dist 的陈旧 bundle 问题） |

## 4. 发布前置（LICENSING.md 决策记录）

1. ✅ 根目录 `LICENSE` 已选定 **Apache-2.0** 并入库（2026-11-11，随 `LICENSE` + `NOTICE` 分发）；文档若单独发布仍待 CC BY 4.0 决策；
2. ✅ `pyproject.toml` 与 `apps/web/package.json` 已带 `license` 字段；
3. `THIRD_PARTY_NOTICES.md` 是第三方归属的权威记录（`NOTICE` 指向它）；`research_agent/vendor/astradraw/` 仍按裁剪规则 excluded from redistribution。

## 5. 最小自检

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests      # 全量离线套件（数量以实际输出为准）
python -m research_agent --help           # 顶级命令以 --help 为准
python -m research_agent rsi status       # 应输出 "no capability claim is allowed" 警告
```

## 6. WorkBuddy 即插即用

本目录可作为**独立运行目录**直接接入 WorkBuddy，不需要仓库根目录参与。接入面在
`integrations/workbuddy/`：

- `mcp.workbuddy.json`：配置模板。把 `<WELLSPRING_AGENT_ROOT>` 与 `<PYTHON_38_EXECUTABLE>`
  替换后**合并**（不是覆盖）进 `~/.workbuddy/mcp.json` 的 `mcpServers`；
- `SKILL.md`：调用纪律（46 个工具、人工门只在 CLI、fixture 不得当证据）；
- `check.py`：只读自检，不启动服务、不写文件、不改门禁。

启用步骤：在 WorkBuddy 的自定义连接器入口对新 server 点「信任」。新 MCP 不会自动激活。
自检：`python integrations/workbuddy/check.py`。

功能逻辑与仓库根完全一致：同一个 `scripts/research_mcp_server.py`、同一份 46 工具的
`TOOL_NAMES`、同一套门禁；接入层不新增工具、不改判定、不写 Claim/EA/Protocol/Signature。
解释器必须是已安装 `requirements-runtime.txt` 依赖的 Python 3.8，否则工具会在运行时
报 ImportError。
