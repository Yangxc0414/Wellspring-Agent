# Codex 接入 Research Agent

Codex 通过 stdio MCP 接入本仓库，不需要改动 server 代码。

1. 把 `integrations/mcp/codex.config.toml.example` 复制到 Codex 配置（通常是 `~/.codex/config.toml`）。
2. 将 `<ABSOLUTE_ROOT>` 替换为本仓库绝对路径；不要把 API key 写进配置。
3. 重启 Codex 会话，确认能发现 `research-agent` server 的工具（以 `tools/list` 为准，当前 41 个）。
4. 首次使用：`research_project_init` → `research_plan` → `research_run`；
   `research_status` / `research_next_actions` 会返回 `loop-capsule.json` 摘要。
5. 人工门（G1/G2/claim/closure/export/sign）仍在 CLI；Codex 没有 sign/approve/freeze 工具。

验证传输层（与客户端无关）：

```bash
python scripts/mcp_transport_smoke.py --root "<ABSOLUTE_ROOT>"
```

它只做 initialize + tools/list，不发模型 Key、不执行科研任务。完整 Qoder E2E 使用
`python scripts/qoder_e2e_test.py`，Codex/Claude Code/Zcode 共用同一 stdio server。
