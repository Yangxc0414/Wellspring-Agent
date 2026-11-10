"""Declarative MCP tool table: names, descriptions and argument schemas.

This is data, not logic. `mcp_server` validates arguments against these entries and dispatches
to `framework_api`, so describing a tool does not add branching to the server, and the human-gate
boundary stays auditable in one place: no signing, approval, freeze or export entry exists here.
"""

from typing import Any, Dict, List

RUN_PROPERTIES: Dict[str, Any] = {
    "project_dir": {
        "type": "string",
        "description": "Project folder, relative to the server root or absolute inside it.",
    },
    "goal": {
        "type": "string",
        "minLength": 2,
        "maxLength": 500,
        "description": "Research goal or question.",
    },
    "task_type": {
        "type": "string",
        "enum": [
            "auto",
            "literature_review",
            "hypothesis_design",
            "experiment_validation",
            "full_research",
        ],
        "default": "auto",
    },
    "source": {
        "type": "string",
        "enum": ["fixture", "real", "openalex", "local"],
        "description": (
            "fixture is workflow-only and uncitable; real is the frozen CC-BY corpus; "
            "openalex returns abstract clues only; local reads PDF/TXT/MD from inputs/."
        ),
    },
    "max_sources": {"type": "integer", "minimum": 1, "maximum": 30, "default": 6},
    "language": {"type": "string", "enum": ["zh", "en"], "default": "zh"},
    "venue_type": {
        "type": "string",
        "enum": [
            "zh_core_journal",
            "software_journal",
            "computer_journal",
            "en_conference",
            "en_journal",
            "zh_thesis",
        ],
        "default": "zh_core_journal",
    },
    "flow_mode": {"type": "string", "enum": ["review", "strict"], "default": "review"},
    "deliverable": {"type": "string", "maxLength": 120, "default": ""},
    "run_dataset": {
        "type": "string",
        "enum": ["", "iris", "breast_cancer", "chemlab"],
        "default": "",
    },
    "run_seeds": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
    "g1_decision_file": {
        "type": "string",
        "description": "Human-approved G1 decision JSON, relative to the project.",
    },
    "protocol_file": {
        "type": "string",
        "description": "Human-frozen ProtocolCard JSON, relative to the project.",
    },
    "claim_file": {
        "type": "string",
        "description": "Human-signed ClaimRecord JSON, relative to the project.",
    },
    "bibliography_file": {
        "type": "string",
        "description": "Verified bibliography card JSON, relative to the project.",
    },
    "run_dir": {
        "type": "string",
        "description": "Existing RunCapsule/EA directory, relative to the project.",
    },
}

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "research_project_init",
        "description": (
            "Create a research project folder with project.json and inputs/, runs/, "
            "protocols/, claims/, closure/, notes/. Use before running tasks. "
            "All outputs stay inside this folder."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "name": {"type": "string", "maxLength": 120},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_bootstrap",
        "description": (
            "One-call start for a research project: initialize the project, build a task plan, "
            "list enabled external Skills plus journal Skill profiles, and optionally run the "
            "bounded local TaskAgent pipeline via run_now. It never executes Skill scripts, "
            "signs or approves."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "name": {"type": "string", "maxLength": 120},
                "goal": {"type": "string", "maxLength": 2000},
                "source": {"type": "string", "enum": ["fixture", "real", "openalex", "local"], "default": "local"},
                "task_type": {
                    "type": "string",
                    "enum": ["auto", "literature_review", "hypothesis_design", "experiment_validation", "full_research"],
                    "default": "auto",
                },
                "max_sources": {"type": "integer", "minimum": 1, "maximum": 30, "default": 6},
                "language": {"type": "string", "enum": ["zh", "en"], "default": "zh"},
                "venue_type": {
                    "type": "string",
                    "enum": [
                        "zh_core_journal",
                        "software_journal",
                        "computer_journal",
                        "en_conference",
                        "en_journal",
                        "zh_thesis",
                    ],
                    "default": "zh_core_journal",
                },
                "flow_mode": {"type": "string", "enum": ["review", "strict"], "default": "review"},
                "run_now": {
                    "type": "boolean",
                    "default": False,
                    "description": "Run the bounded research-agent pipeline after bootstrap; no signing or approval.",
                },
                "run_dataset": {
                    "type": "string",
                    "enum": ["", "iris", "breast_cancer", "chemlab"],
                    "default": "",
                },
                "run_seeds": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
                "skill_ids": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 120},
                    "maxItems": 8,
                },
            },
            "required": ["goal"],
            "additionalProperties": False,
        },
    },
    {
        "name": "research_plan",
        "description": (
            "Plan a bounded research task without executing it. Returns the route, "
            "steps, human gates, warnings and success criteria. No model call and no output."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "goal": RUN_PROPERTIES["goal"],
                "task_type": RUN_PROPERTIES["task_type"],
                "source": RUN_PROPERTIES["source"],
                "max_sources": RUN_PROPERTIES["max_sources"],
                "language": RUN_PROPERTIES["language"],
                "venue_type": RUN_PROPERTIES["venue_type"],
                "flow_mode": RUN_PROPERTIES["flow_mode"],
                "run_dataset": RUN_PROPERTIES["run_dataset"],
            },
            "required": ["goal", "source"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_run",
        "description": (
            "Execute a bounded research task under <project>/runs/<RUN-ID>/. Stops at "
            "Q0/G1/G2/S5b/G5 as needed. It never signs a claim, freezes a protocol, "
            "signs closure or approves export. Use research_next_actions afterwards."
        ),
        "inputSchema": {
            "type": "object",
            "properties": dict(RUN_PROPERTIES),
            "required": ["goal", "source"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_status",
        "description": (
            "List recent runs in a research project with status, route, gates, failure, "
            "an optional governance summary (support panel/gold/writing audit), and a "
            "read-only project experiment_inventory (stages/next_action/evidence summary)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_model_profiles",
        "description": (
            "Read-only catalog of model gateway profiles for judge selection: profile id, "
            "label, provider, model and has_key. It returns no API keys, masked keys, base "
            "URLs or local paths and makes no network call. Use diverse_judge_pairs for a "
            "multi-judge panel when available."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_model_turns",
        "description": (
            "Read the host-agent model queue: generation steps the runtime deferred because "
            "a bound profile is keyless (provider kind host_agent). Returns the exact prompt, "
            "declared output shape and expiry for each turn so the calling agent can answer "
            "with its own model. No network call; an answer is capability output, not evidence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "responded", "expired", "cancelled"],
                    "description": "Filter by turn status; omit to return all.",
                },
                "module": {
                    "type": "string",
                    "maxLength": 40,
                    "description": "Filter by consuming module, for example idea or paper.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Most recent turns to return.",
                },
                "include_request": {
                    "type": "boolean",
                    "description": "Include the full prompt. Defaults to true.",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_model_respond",
        "description": (
            "Submit the host agent's answer for a pending model turn. The answer is bound to "
            "the request hash, validated against the turn's declared shape, consumed once and "
            "never half-written; a rejected answer leaves the turn pending. This returns a "
            "capability output, not a signature: it cannot approve, claim, freeze, publish or "
            "export, and downstream audits still run."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "turn_id": {
                    "type": "string",
                    "maxLength": 60,
                    "description": "Turn id from research_model_turns.",
                },
                "text": {
                    "type": "string",
                    "maxLength": 200000,
                    "description": "The raw model output, usually a JSON object.",
                },
                "host_label": {
                    "type": "string",
                    "maxLength": 80,
                    "description": "Self-reported host, for example Qoder. Unverified.",
                },
                "project_dir": {
                    "type": "string",
                    "maxLength": 300,
                    "description": "Project root when the turn declares a file sink.",
                },
            },
            "required": ["turn_id", "text"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "idempotentHint": False},
    },
    {
        "name": "research_model_void",
        "description": (
            "Invalidate an already-answered host model turn so the stage asks again. Needed "
            "when an answer is valid JSON but wrong for the module's deeper contract: answers "
            "are replayed by request hash and would otherwise stick forever. Requires a "
            "reason; the previous answer hash is kept for audit. Reopens a request only; it "
            "never admits a capability or signs anything."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "turn_id": {"type": "string", "maxLength": 60},
                "reason": {
                    "type": "string",
                    "maxLength": 400,
                    "description": "Why the previous answer cannot be used.",
                },
            },
            "required": ["turn_id", "reason"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "idempotentHint": True},
    },
    {
        "name": "research_list_artifacts",
        "description": "List artifacts for one run, including task.json, report, evidence and failure.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string"},
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_read_artifact",
        "description": (
            "Read a text artifact from one run (bounded, project-only). Use this to read "
            "task.json, task-report.md, support-audit.json or failure.json before summarizing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string"},
                "path": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 1000, "maximum": 400000, "default": 120000},
            },
            "required": ["run_id", "path"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_next_actions",
        "description": (
            "Read one run and return the next human actions and exact CLI commands. "
            "Never execute a human-gate command for the user."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string"},
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_skill_list",
        "description": (
            "List imported external skills with id, name, enabled state, license, "
            "has_scripts and risk flags. Instructions and local paths are not returned. "
            "Use this before invoke or distill."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_skill_instructions",
        "description": (
            "Read-only instructions of one enabled external Skill for Qoder itself to follow. "
            "It never calls a model, never executes scripts, and returns no local paths; "
            "instructions remain untrusted advisory and create no claims/evidence/gates."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "maxLength": 120},
                "max_chars": {
                    "type": "integer",
                    "minimum": 500,
                    "maximum": 8000,
                    "default": 8000,
                },
            },
            "required": ["skill_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_skill_invoke",
        "description": (
            "Invoke an enabled instruction-only external SKILL.md as advisory. "
            "Scripts, tools, network and files are never executed; output is not evidence "
            "and cannot create claims, gates or signatures. Optionally distill the skill "
            "into a disabled local candidate after a successful call."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "input": {"type": "string", "minLength": 1, "maxLength": 12000},
                "profile_id": {
                    "type": "string",
                    "description": "Runtime model profile id; may come from RESEARCH_AGENT_SKILL_PROFILE.",
                },
                "context": {"type": "string", "maxLength": 12000},
                "project_dir": RUN_PROPERTIES["project_dir"],
                "distill_on_success": {"type": "boolean", "default": False},
                "license": {"type": "string", "maxLength": 200},
                "human_reason": {"type": "string", "maxLength": 1000},
                "source_url": {"type": "string", "maxLength": 500},
            },
            "required": ["skill_id", "input"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_skill_distill",
        "description": (
            "Copy an enabled external skill into a disabled local candidate under "
            "<project>/notes/skill-library/. Requires license and human_reason. It never "
            "executes or enables the candidate; a human must review and enable it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "project_dir": RUN_PROPERTIES["project_dir"],
                "human_reason": {"type": "string", "minLength": 1, "maxLength": 1000},
                "license": {"type": "string", "maxLength": 200},
                "source_url": {"type": "string", "maxLength": 500},
            },
            "required": ["skill_id", "human_reason"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_manuscript_revise",
        "description": (
            "Revise an existing manuscript inside a research project without inventing new "
            "research. Reads .md/.txt/.docx/.tex, optionally recomputes metrics from CSV/JSON/XLSX, "
            "generates data-backed figures, rewrites sections with a model profile, audits numbers/"
            "citations/figures, and exports Markdown/LaTeX/DOCX/PDF under <project>/revisions/. "
            "It never signs, approves or claims submission readiness."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "draft": {
                    "type": "string",
                    "description": "Manuscript path relative to the project (md/txt/docx/tex).",
                },
                "data": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 10,
                    "description": "CSV/TSV/JSON/XLSX data files relative to the project.",
                },
                "metrics_file": {
                    "type": "string",
                    "description": "Metric spec JSON relative to the project.",
                },
                "figures_file": {
                    "type": "string",
                    "description": "Figure spec JSON relative to the project.",
                },
                "venue": {
                    "type": "string",
                    "enum": ["zh_core_journal", "software_journal", "computer_journal"],
                    "default": "zh_core_journal",
                },
                "profile_id": {
                    "type": "string",
                    "description": "Model profile for rewriting; may come from RESEARCH_AGENT_REVISION_PROFILE.",
                },
                "sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 30,
                    "description": "Only rewrite sections whose headings contain one of these strings.",
                },
                "formats": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["md", "tex", "docx", "pdf", "html"]},
                    "default": ["md", "tex", "docx", "pdf"],
                },
            },
            "required": ["draft"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_figure_templates",
        "description": (
            "List bundled AstraDraw scene templates with id, scene_id, component, style, "
            "size and object count. Templates are visual/layout priors only, not scientific "
            "claims or evidence."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_figure_render",
        "description": (
            "Render a project .scene.json or a bundled AstraDraw template into "
            "<project>/figures/<name>/ as SVG/PNG with an audit and manifest. The result "
            "is a schematic, not a data plot, not evidence and not a publication approval."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "scene": {
                    "type": "string",
                    "description": "Project-relative AstraDraw .scene.json.",
                },
                "template_id": {
                    "type": "string",
                    "description": "Bundled template id from research_figure_templates.",
                },
                "title": {"type": "string", "maxLength": 200},
                "description": {"type": "string", "maxLength": 1000},
                "name": {"type": "string", "maxLength": 60},
                "formats": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["svg", "png"]},
                    "default": ["svg", "png"],
                },
            },
            "oneOf": [{"required": ["scene"]}, {"required": ["template_id"]}],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_literature_fetch",
        "description": (
            "Explicitly search arxiv.org and download open arXiv PDFs into "
            "<project>/inputs/ with provenance and SHA-256. Network is disabled by default; "
            "set allow_network=true. Downloads are not evidence until local PDF parsing "
            "produces spans; no paywall bypass."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "query": {"type": "string", "minLength": 2, "maxLength": 300},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 4},
                "allow_network": {"type": "boolean", "default": False},
                "timeout": {"type": "integer", "minimum": 5, "maximum": 120, "default": 30},
            },
            "required": ["query", "allow_network"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_literature_synthesis",
        "description": (
            "Build a theme-by-source synthesis matrix from one completed run. Every theme must "
            "cover at least two distinct papers; unused papers are reported. It is not a claim "
            "and does not replace the literature ledger."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string"},
                "max_themes": {"type": "integer", "minimum": 3, "maximum": 10, "default": 7},
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_conference_fetch",
        "description": (
            "Explicitly fetch recent top-conference papers that expose an open arXiv PDF. "
            "Filters venue/year acceptance comments, records provenance/SHA-256 and a bounded "
            "corpus manifest under <project>/inputs/. Not an exhaustive proceedings crawl; "
            "downloads are not evidence until local parsing produces spans."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "topic": {"type": "string", "minLength": 2, "maxLength": 300},
                "venues": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["NeurIPS", "ICLR", "ICML", "ACL", "EMNLP", "AAAI", "CVPR", "KDD"],
                    },
                    "minItems": 1,
                    "maxItems": 8,
                    "default": ["NeurIPS", "ICLR", "ICML", "ACL"],
                },
                "years": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 2018, "maximum": 2100},
                    "minItems": 1,
                    "maxItems": 5,
                    "default": [2024, 2025, 2026],
                },
                "max_papers": {"type": "integer", "minimum": 1, "maximum": 80, "default": 24},
                "max_per_venue": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
                "allow_network": {"type": "boolean", "default": False},
            },
            "required": ["topic", "allow_network"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_writing_pack",
        "description": (
            "Build a compact, read-only writing pack for one run: real references, selected "
            "evidence spans, ideas, design, capsule/EA, signed-claim status, allowed result "
            "numbers, a reproduction map (claim -> rebuilt re-run command -> named artifacts) "
            "and a writing contract. Use this before Qoder writes a Chinese manuscript; "
            "it never invents claims or result numbers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string"},
                "language": {"type": "string", "enum": ["zh", "en"], "default": "zh"},
                "venue": {
                    "type": "string",
                    "enum": ["zh_core_journal", "software_journal", "computer_journal", "en_conference"],
                    "default": "zh_core_journal",
                },
                "max_sources": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
                "max_spans_per_source": {"type": "integer", "minimum": 1, "maximum": 8, "default": 3},
                "experiment_id": {"type": "string", "maxLength": 80, "description": "Use verified local experiment evidence."},
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_manuscript_audit",
        "description": (
            "Audit a Qoder-authored manuscript against one run's writing pack. Checks "
            "citation keys, result-number policy, claim status, required sections and "
            "placeholders. If the run has a support panel, its pending/stale status also "
            "blocks the audit; a human-gold artifact is reported as a reference summary, "
            "not a gate. It does not sign claims or declare submission-ready."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string"},
                "draft": {"type": "string", "description": "Project-relative .md/.txt/.docx/.tex draft."},
                "language": {"type": "string", "enum": ["zh", "en"], "default": "zh"},
                "venue": {
                    "type": "string",
                    "enum": ["zh_core_journal", "software_journal", "computer_journal", "en_conference"],
                    "default": "zh_core_journal",
                },
                "experiment_id": {"type": "string", "maxLength": 80},
                "semantic": {
                    "type": "boolean",
                    "default": False,
                    "description": "Run the reference-aware semantic support ledger (requires a model key).",
                },
                "judge_profile": {
                    "type": "string",
                    "description": "Optional model profile id for an independent support judge.",
                },
                "strict_support": {
                    "type": "boolean",
                    "default": False,
                    "description": "Block if any cited sentence is unsupported, partial, contradicted or unresolved.",
                },
                "strict_pack_binding": {
                    "type": "boolean",
                    "default": False,
                    "description": "Block drafts without a matching writing-pack marker.",
                },
                "support_votes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 1,
                    "description": "Semantic judge votes per item; majority reduces single-call noise.",
                },
                "support_max_items": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 80,
                    "description": "Maximum cited sentences to judge; strict support blocks if truncated.",
                },
                "refresh_support": {
                    "type": "boolean",
                    "default": False,
                    "description": "Ignore the cached support ledger and re-run the judge.",
                },
                "revision_mode": {
                    "type": "string",
                    "enum": ["full", "section", "support", "auto"],
                    "default": "full",
                    "description": "Targeted section revision avoids truncating long manuscripts.",
                },
                "ab_check": {
                    "type": "boolean",
                    "default": False,
                    "description": "Reject a revision if blind A/B review prefers the original.",
                },
                "ab_sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 12,
                    "default": [],
                    "description": "Section heading substrings for A/B review; empty means all.",
                },
            },
            "required": ["run_id", "draft"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_innovation_review",
        "description": (
            "Run an evidence-grounded innovation review over one completed run: propose ideas, "
            "critique them from novelty/evidence/feasibility roles, revise and re-review. "
            "Needs a model supply for the generation steps (a gateway profile, an env key, or a "
            "keyless host_agent profile answered by this agent) plus full-text spans. "
            "Pass critic_profiles or independent=true to staff the three critic roles on distinct "
            "supplies; otherwise the result discloses itself as single-author and its scores are a "
            "process signal. It does not run experiments or create claims."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string"},
                "topic": {"type": "string", "maxLength": 300},
                "direction": {"type": "string", "maxLength": 1200},
                "rounds": {"type": "integer", "minimum": 1, "maximum": 5, "default": 2},
                "max_ideas": {"type": "integer", "minimum": 3, "maximum": 8, "default": 5},
                "threshold": {"type": "number", "minimum": 0, "maximum": 10, "default": 8.0},
                "prior_art_corpus": {
                    "type": "string",
                    "maxLength": 300,
                    "description": (
                        "Path to a real CC-BY corpus (corpus_kind=real, fixture=false) that the "
                        "novelty critic searches on its own, after generation, to look for prior "
                        "art refuting each idea. Without it the review reports prior_art.available"
                        "=false: novelty was judged only against the generator's own evidence set."
                    ),
                },
                "prior_art_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 6,
                    "description": "Reviewer-side hits retrieved per idea.",
                },
                "language": {
                    "type": "string",
                    "enum": ["zh", "en"],
                    "default": "zh",
                    "description": (
                        "Language of the returned idea fields (title, problem, mechanism, "
                        "falsification, experiment_plan strings). The prompt itself stays Chinese; "
                        "only the artifact language follows this. An English-venue run needs en, "
                        "otherwise English rubric packs read the artifact as foreign script and "
                        "score it 0."
                    ),
                },
                "critic_profiles": {
                    "type": "object",
                    "additionalProperties": {"type": "string", "maxLength": 120},
                    "description": (
                        "novelty|evidence|feasibility -> model profile id. Unbound roles fall back "
                        "to the proposer supply and stay disclosed as single-author."
                    ),
                },
                "independent": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Staff all three roles from distinct provider+model supplies (proposer "
                        "excluded); fails with the missing-supply count instead of silently "
                        "reviewing alone."
                    ),
                },
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_manuscript_draft",
        "description": (
            "Generate a first Chinese review/position manuscript from a run's writing pack and "
            "innovation review, then run the deterministic manuscript audit. Needs a model supply "
            "(gateway profile, env key, or a keyless host_agent profile answered by this agent). "
            "It does not fabricate experiments, sign claims or declare submission readiness."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string"},
                "output": {
                    "type": "string",
                    "description": "Project-relative .md output path, e.g. drafts/review.md.",
                },
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["run_id", "output"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_manuscript_review",
        "description": (
            "Review a project-local draft with a strict rubric, revise it, and re-review for "
            "multiple rounds. Candidate revisions are rejected if deterministic citation/number "
            "audit gets worse. It never signs claims or claims submission readiness."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string"},
                "draft": {"type": "string", "description": "Project-relative .md draft."},
                "rounds": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
                "threshold": {"type": "number", "minimum": 0, "maximum": 10, "default": 8.0},
                "semantic_support": {
                    "type": "boolean",
                    "default": False,
                    "description": "Feed sentence-level support failures into review/revision.",
                },
                "judge_profile": {
                    "type": "string",
                    "description": "Optional model profile id for an independent support judge.",
                },
                "strict_support": {
                    "type": "boolean",
                    "default": False,
                    "description": "Reject revisions that leave contradicted/unresolved/insufficient citations.",
                },
                "support_votes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 1,
                    "description": "Semantic judge votes per item; majority reduces single-call noise.",
                },
            },
            "required": ["run_id", "draft"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_experiment_codegen",
        "description": (
            "Generate a self-contained local experiment package from one run and a CSV table: "
            "a validated experiment spec, deterministic runner, requirements and README. It does "
            "NOT execute the experiment, install dependencies, create EA/Claim or approve G2."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string"},
                "data": {"type": "string", "description": "Project-relative CSV path."},
                "target": {"type": "string"},
                "features": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 100},
                "task": {"type": "string", "enum": ["regression", "classification"], "default": "regression"},
                "methods": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["dummy", "ridge", "logistic", "random_forest", "gradient_boosting"]},
                    "minItems": 2,
                    "maxItems": 5,
                    "default": ["dummy", "ridge"],
                },
                "metric": {"type": "string", "maxLength": 40},
                "experiment_id": {"type": "string", "maxLength": 80},
                "test_size": {"type": "number", "minimum": 0.05, "maximum": 0.5, "default": 0.2},
                "seeds": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
                "cv_folds": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 0,
                    "description": "k-fold cross-validation (0 = holdout split; 1 is invalid).",
                },
                "alpha_grid": {
                    "type": "array",
                    "items": {"type": "number", "exclusiveMinimum": 0},
                    "minItems": 2,
                    "maxItems": 8,
                    "description": (
                        "Optional ridge alpha grid for a sweep plan. Planning profile only: "
                        "run_sweep.py is generated but not executed by MCP/CLI lifecycle tools."
                    ),
                },
            },
            "required": ["run_id", "data", "target", "features"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_experiment_status",
        "description": (
            "Read-only lifecycle status for a generated experiment: spec/data/code/approval/"
            "execution/evidence/claim/closure/signature/lineage freshness and the next action. "
            "It never executes, signs or changes evidence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "experiment_id": {"type": "string", "minLength": 1, "maxLength": 80},
            },
            "required": ["experiment_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_empirical_status",
        "description": (
            "Read-only same-run empirical preflight: checks literature/synthesis/innovation, "
            "experiment run/idea linkage, verified evidence and human-signed claim. It returns "
            "blockers and next actions; it never executes, signs or edits."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "experiment_id": {"type": "string", "minLength": 1, "maxLength": 80},
            },
            "required": ["run_id", "experiment_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_closure_status",
        "description": (
            "Read-only closure status for the canonical RunCapsule/EA profile or the "
            "local experiment profile. It returns status, checks, blockers, the next "
            "human action and a presence/SHA-256 chain of custody (not a correctness "
            "proof); it never signs, publishes or edits artifacts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string", "maxLength": 120},
                "experiment_id": {"type": "string", "maxLength": 80},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_evolution_status",
        "description": (
            "Read-only view of the self-improvement loop for one RSI ledger: how many episodes "
            "exist, how many a human ever decided, the rejection rate, which gates never fired "
            "(gate_stops) and the gate verdict. A round that rejected nothing is reported as "
            "gate_uninformative, never as success. It cannot propose, admit, reject, revoke or "
            "activate anything: those stay CLI operations with a human reason."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ledger": {
                    "type": "string",
                    "maxLength": 300,
                    "description": "path to an RSI step ledger json",
                },
            },
            "required": ["ledger"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_lineage_status",
        "description": (
            "Read-only re-hash verification of a local experiment lineage manifest. "
            "It returns fresh/stale nodes, stale reasons and the next CLI action; "
            "it never rebuilds, edits, signs or executes. Fresh means bytes match the "
            "recorded hashes, not that the experiment or closure is valid."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "experiment_id": {"type": "string", "maxLength": 80},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_support_panel",
        "description": (
            "Run a multi-judge sentence-level support panel over a draft bound to the "
            "current writing pack. It records per-judge verdicts, disagreements, pairwise "
            "kappa and pending human adjudication, then writes support-panel.json and an "
            "adjudication template. It never signs, edits the draft or authorizes submission."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string", "maxLength": 120},
                "draft": {
                    "type": "string",
                    "description": "Project-relative .md/.txt/.tex draft bound to the pack.",
                },
                "judge_profiles": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 120},
                    "minItems": 1,
                    "maxItems": 4,
                    "description": "Independent model profile ids; different providers recommended.",
                },
                "judge_families": {
                    "type": "object",
                    "additionalProperties": {"type": "string", "maxLength": 80},
                    "description": "Optional profile_id -> model family declaration; caller-supplied, not proof.",
                },
                "require_families": {
                    "type": "boolean",
                    "default": False,
                    "description": "Require at least two distinct declared model families.",
                },
                "judge_providers": {
                    "type": "object",
                    "additionalProperties": {"type": "string", "maxLength": 80},
                    "description": "Optional profile_id -> provider id; caller-supplied, not proof.",
                },
                "require_providers": {
                    "type": "boolean",
                    "default": False,
                    "description": "Require at least two distinct declared provider ids.",
                },
                "strict_support": {
                    "type": "boolean",
                    "default": False,
                    "description": "Block unresolved judge disagreement; requires at least two judges.",
                },
                "support_votes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 1,
                },
                "max_items": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 80,
                },
                "refresh_support": {"type": "boolean", "default": False},
                "adjudication_file": {
                    "type": "string",
                    "description": "Optional project-relative human adjudication JSON.",
                },
            },
            "required": ["run_id", "draft", "judge_profiles"],
            "additionalProperties": False,
        },
    },
    {
        "name": "research_support_items",
        "description": (
            "Read-only sentence-level support items for an external judge such as Qoder. "
            "It reads a draft bound to the current writing pack and returns item ids, "
            "sentences, refs and evidence spans without calling a model or assigning verdicts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string", "maxLength": 120},
                "draft": {"type": "string", "description": "Project-relative .md/.txt/.tex draft."},
                "max_items": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 80,
                },
            },
            "required": ["run_id", "draft"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_support_verdicts",
        "description": (
            "Record Qoder-authored sentence support verdicts for a draft bound to the "
            "current writing pack, without calling an external model. It validates ids, "
            "statuses and evidence refs, writes support-ledger.json, and never signs. "
            "reuse=true keeps prior verdicts for unchanged sentence+evidence pairs from "
            "the same judge id and only requires verdicts for changed items."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string", "maxLength": 120},
                "draft": {"type": "string"},
                "judge_id": {"type": "string", "maxLength": 120},
                "strict": {
                    "type": "boolean",
                    "default": True,
                    "description": "Require a verdict for every judgeable item.",
                },
                "reuse": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Reuse prior verdicts for unchanged sentence+evidence pairs from "
                        "support-ledger.json when the judge id matches."
                    ),
                },
                "verdicts": {
                    "type": "array",
                    "minItems": 0,
                    "maxItems": 200,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": [
                                    "supported",
                                    "partial",
                                    "contradicted",
                                    "insufficient",
                                    "not_required",
                                ],
                            },
                            "rationale": {"type": "string", "maxLength": 600},
                            "evidence_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 8,
                            },
                        },
                        "required": ["id", "status", "rationale"],
                        "additionalProperties": False,
                    },
                },
                "max_items": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 80,
                },
            },
            "required": ["run_id", "draft", "judge_id", "verdicts"],
            "additionalProperties": False,
        },
    },
    {
        "name": "research_manuscript_section_edit",
        "description": (
            "Apply a Qoder-authored replacement body to exactly one section of a draft "
            "bound to the current writing pack. It preserves all other sections and the "
            "pack marker, rejects new REFs or numeric tokens, and never calls a model or signs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string", "maxLength": 120},
                "draft": {"type": "string", "description": "Project-relative source draft."},
                "section": {"type": "string", "description": "Heading substring; must match one section."},
                "replacement": {"type": "string", "description": "Replacement section body."},
                "output": {"type": "string", "description": "Project-relative new draft path."},
                "expected_section_sha256": {
                    "type": "string",
                    "maxLength": 64,
                    "description": "Optional stale-read guard from a previous items/edit result.",
                },
            },
            "required": ["run_id", "draft", "section", "replacement", "output"],
            "additionalProperties": False,
        },
    },
    {
        "name": "research_manuscript_bind",
        "description": (
            "Attach the current writing pack marker to an existing project draft without "
            "changing its body. It rejects already-bound or differently-bound drafts, requires "
            "at least one [REF-xx] that exists in the pack, returns resolved/unresolved refs, "
            "and never calls a model or signs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "run_id": {"type": "string", "maxLength": 120},
                "draft": {"type": "string", "description": "Project-relative unbound draft."},
                "output": {"type": "string", "description": "Project-relative new draft path."},
            },
            "required": ["run_id", "draft", "output"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_manuscript_ab_review",
        "description": (
            "Blind A/B rubric review of an original and a revised manuscript inside a project. "
            "The reviewer sees anonymous A/B sections, scores clarity/argument/evidence/style, "
            "then the mapping is revealed. It does not rewrite or sign."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "original": {"type": "string", "description": "Project-relative original draft."},
                "revised": {"type": "string", "description": "Project-relative revised draft."},
                "sections": {"type": "array", "items": {"type": "string"}, "maxItems": 20, "default": []},
                "rounds": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
                "profile_id": {"type": "string", "description": "Reviewer model profile; different from writer is recommended."},
            },
            "required": ["original", "revised", "profile_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "research_host_contract",
        "description": (
            "Read-only host negotiation, before any run: returns the live build fingerprint, which "
            "transports actually work (in-process, HTTP, MCP stdio, file-drop with a real write "
            "probe), which model stages are bound to a keyless host profile and will therefore "
            "suspend waiting for your answer, and what stays human-only for every transport. "
            "Declare what the host can do with capabilities: can_call_tools, can_write_files, "
            "can_serve_model, long_sessions. Unknown claims are reported, never silently accepted. "
            "Runs no stage and cannot sign, approve, freeze, close, publish or export."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Host-declared abilities: can_call_tools, can_write_files, "
                        "can_serve_model, long_sessions"
                    ),
                },
                "outbox_dir": {
                    "type": "string",
                    "description": "Optional handoff directory to probe for writability.",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_venue_audit",
        "description": (
            "Read-only structural audit for a Chinese-journal manuscript or an NSFC/NSSFC grant "
            "draft. Chinese journals: abstract/keywords/sections/references/funding/innovation/"
            "data availability. Grants: required modules, innovation, evidence, NSSFC anonymity "
            "and AI declaration. Optionally attach a local skill-pack rubric (skill_pack or "
            "venue, with skill_stage/skill_profile/skill_max_items) as an advisory punch list. "
            "It never writes text, signs, approves or submits."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "file": {
                    "type": "string",
                    "description": "Project-relative JSON: manuscript for zh_journal, {sections:...} for grant.",
                },
                "kind": {
                    "type": "string",
                    "enum": ["zh_journal", "grant"],
                    "default": "zh_journal",
                },
                "profile": {
                    "type": "string",
                    "enum": ["zh_core_journal", "software_journal", "computer_journal"],
                    "default": "zh_core_journal",
                },
                "scheme": {
                    "type": "string",
                    "enum": ["nsfc", "nssfc", "generic"],
                    "default": "nsfc",
                },
                "anonymous": {"type": "boolean", "default": False},
                "identity_removed": {"type": "boolean", "default": False},
                "ai_statement": {"type": "boolean", "default": False},
                "skill_pack": {
                    "type": "string",
                    "maxLength": 300,
                    "description": "Local skill pack directory to attach as an advisory rubric.",
                },
                "skill_pack_root": {
                    "type": "string",
                    "maxLength": 300,
                    "description": "Root of available packs; used with venue to route.",
                },
                "venue": {"type": "string", "maxLength": 160},
                "skill_stage": {
                    "type": "string",
                    "enum": [
                        "", "idea", "design", "writing", "submission",
                        "review", "reproducibility", "general",
                    ],
                    "default": "",
                },
                "skill_profile": {
                    "type": "string",
                    "enum": ["", "design", "draft", "submission", "revision"],
                    "default": "",
                },
                "skill_max_items": {"type": "integer", "minimum": 1, "maximum": 300, "default": 40},
            },
            "required": ["project_dir", "file", "kind"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_grant_template",
        "description": (
            "Write a blank NSFC/NSSFC/generic grant section skeleton into the project. "
            "The applicant fills the sections; the tool never writes scientific ideas, budget "
            "numbers or text, signs, approves or submits. Audit it with research_venue_audit."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "scheme": {
                    "type": "string",
                    "enum": ["nsfc", "nssfc", "generic"],
                    "default": "nsfc",
                },
                "output": {
                    "type": "string",
                    "default": "grant-template.json",
                    "description": "Project-relative JSON path.",
                },
            },
            "required": ["project_dir"],
        },
        "annotations": {"destructiveHint": False},
    },
    {
        "name": "research_skill_packs",
        "description": (
            "Read-only audit of a local journal/reviewer skill pack: scan extracts the "
            "checklist with license/provenance/hashes, route maps a venue name to a pack "
            "directory, and coverage scores a JSON artifact (design, plan or draft) "
            "against the pack's actionable rubric and always reports the scored window "
            "(checklist_total / limit_applied / truncated). It never executes pack scripts, "
            "never uses the network, and its output is advisory: it is not evidence, not a "
            "gate and not a compliance verdict."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["scan", "route", "coverage"]},
                "pack_dir": {
                    "type": "string",
                    "maxLength": 300,
                    "description": (
                        "Pack directory for scan and coverage. Optional when pack_root plus "
                        "venue are given: the venue name is routed to its pack, exactly as on "
                        "the command line."
                    ),
                },
                "pack_root": {
                    "type": "string",
                    "maxLength": 300,
                    "description": (
                        "Journal-skill root containing shared-resources/journal-selection; with "
                        "venue it selects the pack for route, scan and coverage alike."
                    ),
                },
                "venue": {
                    "type": "string",
                    "maxLength": 160,
                    "description": "Venue name routed to a local pack (e.g. NeurIPS).",
                },
                "artifact": {
                    "type": "string",
                    "maxLength": 300,
                    "description": (
                        "Project-relative or absolute JSON artifact (design, plan, audit), a "
                        "Markdown/TeX/plain-text draft, or a whole package directory: a "
                        "directory is scored as one bundle and reports which files it spliced."
                    ),
                },
                "stage": {
                    "type": "string",
                    "enum": [
                        "", "idea", "design", "writing", "submission",
                        "review", "reproducibility", "general",
                    ],
                    "default": "",
                },
                "profile": {
                    "type": "string",
                    "enum": ["", "design", "draft", "submission", "revision"],
                    "default": "",
                },
                "max_items": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 300,
                    "default": 200,
                    "description": (
                        "Rubric items scored at most; the default is the same on every face, "
                        "and pack_scope always reports the denominator."
                    ),
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_mandate_status",
        "description": (
            "Read-only projection of continuous delegation for a run: what the human "
            "authorised, which stage each delegation is at (trigger/context/plan/approval/"
            "verification/obligations), the acceptance unit, and the exact CLI actions a "
            "human must take. It reports partial views honestly (MANDATE_SCOPE_TRUNCATED) "
            "instead of reporting a healthy state it did not inspect, and it grants nothing: "
            "no signing, approving, freezing, publishing or exporting."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": RUN_PROPERTIES["project_dir"],
                "max_runs": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            },
            "required": ["project_dir"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_number_provenance",
        "description": (
            "Read-only trace of a draft's numbers back to artifacts on disk: every decimal must "
            "appear byte-identically in the corpus (the draft file itself is excluded), values "
            "found only under the draft's own folder are reported separately, and integer counts "
            "are never certified by string presence because small integers match by accident and "
            "require re-running the recorded command. A missing trace is reported as missing, not "
            "as a fabrication. It signs, approves, freezes, publishes or edits nothing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "draft": {
                    "type": "string",
                    "maxLength": 300,
                    "description": "Draft to score: project-relative or absolute json/md/tex/txt.",
                },
                "corpus": {
                    "type": "string",
                    "maxLength": 300,
                    "description": "Directory of artifacts searched for the values.",
                },
                "max_files": {"type": "integer", "minimum": 1, "maximum": 60000, "default": 20000},
            },
            "required": ["draft", "corpus"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "research_study_baseline",
        "description": (
            "Read-only strong-baseline comparison: tune classifier and hyperparameter by "
            "stratified cross-validation on the same split and scorer the search uses, then pair "
            "the held-out score with a study artifact seed by seed. The fold count is capped by the "
            "study budget and the call fails when the budget cannot afford two folds, so the "
            "reference never gets more evaluations than the search had. It reports deltas as paired "
            "differences, not causal claims, and it signs nothing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "study": {
                    "type": "string",
                    "maxLength": 300,
                    "description": "study.json to compare against, project-relative or absolute.",
                },
                "seeds": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": 100000},
                    "maxItems": 256,
                    "description": "Subset of the study seeds; omit to use all of them.",
                },
                "folds": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 0,
                    "description": "0 means the largest fold count the study budget affords.",
                },
            },
            "required": ["study"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
]
