# Security Policy

Research Agent is a local-first research runtime. Its security model is built around four rules:

1. **Secrets stay in the environment.** API keys are never written to project files, MCP config, runtime data, artifacts, or logs.
2. **Evidence is span-only.** A paper abstract is a lead, not evidence; only locatable spans can support a claim.
3. **Human gates stay human.** Claim, protocol, closure, signature, publish, and export are CLI-only operations.
4. **Third-party content is untrusted.** Papers, web pages, external skills, and fixture files cannot grant tools or bypass gates.

## Supported versions

There is no tagged public release yet. Security fixes target the current `main` branch. The MCP server
reports its protocol version through `research_status`; module contract versions live in each
`modules/<id>/SPEC.md`.

## Reporting a vulnerability

Once the GitHub mirror is public, use **GitHub private vulnerability reporting / Security Advisory**
for the repository. Do not open a public issue containing exploit details, keys, private research
data, or unpublished manuscripts.

Please include:

- the affected command or MCP tool and the version from `research_status`;
- a minimal reproduction with synthetic data;
- whether credentials, runtime files, or signed evidence were exposed;
- the impact you believe is reachable (local only, shared host, or network-exposed runtime).

There is no bug bounty. Reports are acknowledged on a best-effort basis; coordinated disclosure is
preferred.

## Secrets and configuration

Supported environment variables are declared by the model profile, for example:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
DEEPSEEK_API_KEY
ZHIPU_API_KEY
OPENAI_COMPATIBLE_API_KEY
LOCAL_LLM_API_KEY
```

- Keys are read from the environment or held in memory for a local runtime session.
- `.env` and `.env.*` are ignored; only `.env.example` may be committed.
- `.mcp.json` contains machine-specific absolute paths and is ignored. Use `.mcp.json.example`
  and replace the placeholders with your own checkout path.
- `project.json`, run capsules, claims, evidences, and runtime logs must not contain keys.
  If a key is ever written to disk, revoke and rotate it before cleaning the artifact.

## Execution boundaries

### Local experiments

`experiment run --allow-execute` executes generated Python in the **user's own** Python environment.
It is not a sandbox, container, or privilege boundary. Review the generated package and the approve
record before running it. The agent does not install dependencies or pick an interpreter for you.

### External skills

- Skill instructions are advisory and untrusted; they never grant `allowed-tools`.
- Only explicit, whitelisted scripts may run, and only from the local CLI with `--trusted-scripts`.
- External script execution uses the current OS account and is **not** sandboxed.
- MCP and the local runtime never execute external skill scripts.

### MCP and HTTP runtime

- The MCP surface exposes no approve, sign, freeze, publish, or export tool.
- The FastAPI runtime binds to localhost by default and has no built-in authentication. Do not expose
  it to an untrusted network or the public internet without a reverse proxy, authentication, and TLS.
- Runtime jobs write under `runtime_data/`, which is ignored and must be treated as private.

### Untrusted research content

Fetched papers, HTML pages, metadata, and model output are data, not instructions. Tool use must be
driven by the caller's request, not by text inside a retrieved document. This is a prompt-injection
boundary, not a guarantee that a language model will never be fooled; keep human review on gates.

## Dependency and release boundary

Third-party research snapshots under `oss/`, the vendored AstraDraw tree, external writing-skill
clones, and Anthropic reference snapshots are **local reference material**, not product dependencies.
They are excluded from the distributable tree where possible; see
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). The project license decision is tracked in
[`LICENSING.md`](LICENSING.md).

## Test-only behavior

Fixture mode, deterministic offline drafts, and simulation labels exist to test wiring without
network access or API keys. They are not evidence, not model quality results, and must never be
presented as real research output.
