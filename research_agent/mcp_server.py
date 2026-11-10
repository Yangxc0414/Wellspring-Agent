"""Universal stdio MCP server for the local research workflow.

The server exposes bounded research tools to Qoder, Claude Code, Zcode and any
other MCP client. It never exposes claim signing, protocol freeze, closure sign,
bundle publish or gate approval: those stay in the human CLI.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .project import (
    PROJECT_BOUNDARY,
    PROJECT_DIRS,
    ProjectError,
    init_project,
    list_artifacts,
    new_run_dir,
    open_project,
    project_file,
    project_output_path,
    project_status,
    read_artifact,
    resolve_project,
    resolve_root,
    run_dir,
    update_run_index,
)
from .paths import DEFAULT_MODEL_STORE_PATH, build_info
from .storage import write_json_atomic

SERVER_NAME = "research-agent"


def _integration_spec_version() -> str:
    try:
        from .specs import SpecStore

        return str(SpecStore().load("integration").version)
    except Exception:
        return "0.15.71"


SERVER_VERSION = _integration_spec_version()
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
TOOL_NAMES = (
    "research_project_init",
    "research_bootstrap",
    "research_plan",
    "research_run",
    "research_status",
    "research_model_profiles",
    "research_model_turns",
    "research_model_respond",
    "research_model_void",
    "research_list_artifacts",
    "research_read_artifact",
    "research_next_actions",
    "research_skill_list",
    "research_skill_instructions",
    "research_skill_invoke",
    "research_skill_distill",
    "research_manuscript_revise",
    "research_figure_templates",
    "research_figure_render",
    "research_literature_fetch",
    "research_literature_synthesis",
    "research_conference_fetch",
    "research_writing_pack",
    "research_manuscript_audit",
    "research_innovation_review",
    "research_manuscript_draft",
    "research_manuscript_review",
    "research_experiment_codegen",
    "research_experiment_status",
    "research_empirical_status",
    "research_closure_status",
    "research_evolution_status",
    "research_lineage_status",
    "research_support_panel",
    "research_support_items",
    "research_support_verdicts",
    "research_manuscript_section_edit",
    "research_manuscript_bind",
    "research_manuscript_ab_review",
    "research_host_contract",
    "research_venue_audit",
    "research_grant_template",
    "research_skill_packs",
    "research_mandate_status",
    "research_number_provenance",
    "research_study_baseline",

)
HUMAN_ONLY = (
    "G1 decision, G2 protocol freeze, claim signature, closure signature, "
    "bundle publish and export approval are human-only; this server has no tool for them"
)
START_RESEARCH_PROMPT = "start-research"
REVIEW_DRAFT_PROMPT = "review-draft"
REVIEW_IDEA_PROMPT = "review-idea"
PROMPTS = [
    {
        "name": START_RESEARCH_PROMPT,
        "title": "启动科研智能体",
        "description": (
            "Initialize a project and run the local research-agent pipeline through "
            "research_bootstrap(run_now=true), then continue the evidence/support loop. "
            "Human gates stay in the CLI."
        ),
        "arguments": [
            {
                "name": "project_dir",
                "description": "Project folder, relative to the server root or absolute inside it.",
                "required": True,
            },
            {
                "name": "goal",
                "description": "Research goal or question.",
                "required": True,
            },
            {
                "name": "source",
                "description": "local|real|openalex|fixture (default local).",
                "required": False,
            },
            {
                "name": "venue_type",
                "description": (
                    "zh_core_journal|software_journal|computer_journal|"
                    "en_conference|en_journal|zh_thesis."
                ),
                "required": False,
            },
            {
                "name": "language",
                "description": "zh|en (default zh).",
                "required": False,
            },
        ],
    },
    {
        "name": REVIEW_DRAFT_PROMPT,
        "title": "审阅并改写已有草稿",
        "description": (
            "Bind an existing project draft to its writing pack, run the Qoder-native "
            "support review, rewrite weak sections with reuse=true, and stop at human gold."
        ),
        "arguments": [
            {
                "name": "project_dir",
                "description": "Project folder, relative to the server root or absolute inside it.",
                "required": True,
            },
            {
                "name": "run_id",
                "description": "Run whose writing pack should back the draft.",
                "required": True,
            },
            {
                "name": "draft",
                "description": "Project-relative existing draft; unbound drafts are bound to a new output.",
                "required": True,
            },
            {
                "name": "judge_id",
                "description": "Stable Qoder judge id across review rounds (default qoder-review).",
                "required": False,
            },
            {
                "name": "output",
                "description": "Project-relative bound draft path (default drafts/<stem>-bound.md).",
                "required": False,
            },
        ],
    },
    {
        "name": REVIEW_IDEA_PROMPT,
        "title": "审阅 idea 列表并准备 G1",
        "description": (
            "Read a run's idea candidates and shortlist, present an advisory comparison, "
            "and stop before human G1. It never writes a G1 decision or signs."
        ),
        "arguments": [
            {
                "name": "project_dir",
                "description": "Project folder, relative to the server root or absolute inside it.",
                "required": True,
            },
            {
                "name": "run_id",
                "description": "Run whose idea.json should be reviewed.",
                "required": True,
            },
        ],
    },
]


from .mcp_tools import RUN_PROPERTIES, TOOLS


def _text(value: str) -> Dict[str, Any]:
    return {"type": "text", "text": value}


def tool_ok(data: Dict[str, Any], summary: Optional[str] = None) -> Dict[str, Any]:
    text = summary or json.dumps(data, ensure_ascii=False, indent=2)
    return {"content": [_text(text)], "structuredContent": data, "isError": False}


def tool_error(message: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from .paths import build_info

    # A long-lived stdio server executes the code it imported at startup, so an unexpected error
    # may be a bug in the build rather than in the checkout the host just edited. The error names
    # the build that produced it, or the host files a code defect against code that is not running.
    served = build_info()
    served["check_command"] = (
        "python -m research_agent handoff contract  # compare build.fingerprint with this value"
    )
    payload = {"error": str(message), "boundary": HUMAN_ONLY, "served_build": served}
    if extra:
        payload.update(extra)
    # a host reads the text, not structuredContent, so the identity has to travel in the message
    return {
        "content": [
            _text(
                "Error: %s [served build %s; if that differs from `python -m research_agent "
                "handoff contract` the server is running stale code and must be reloaded]"
                % (str(message), served["fingerprint"])
            )
        ],
        "structuredContent": payload,
        "isError": True,
    }


def _string(
    args: Dict[str, Any],
    name: str,
    default: str = "",
    required: bool = False,
    maximum: int = 500,
) -> str:
    value = args.get(name, default)
    if value is None:
        value = default
    if not isinstance(value, str):
        raise ProjectError("%s must be a string" % name)
    value = value.strip()
    if required and not value:
        raise ProjectError("%s is required" % name)
    if len(value) > maximum:
        raise ProjectError("%s is too long (max %d)" % (name, maximum))
    return value


def _integer(
    args: Dict[str, Any], name: str, default: int, minimum: int, maximum: int
) -> int:
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProjectError("%s must be an integer" % name)
    if value < minimum or value > maximum:
        raise ProjectError("%s must be between %d and %d" % (name, minimum, maximum))
    return value


def _boolean(args: Dict[str, Any], name: str, default: bool = False) -> bool:
    value = args.get(name, default)
    if not isinstance(value, bool):
        raise ProjectError("%s must be a boolean" % name)
    return value


def _choice(args: Dict[str, Any], name: str, values: Tuple[str, ...], default: str) -> str:
    value = _string(args, name, default, maximum=40)
    if value not in values:
        raise ProjectError("%s must be one of: %s" % (name, ", ".join(values)))
    return value


def _reject_unknown(args: Dict[str, Any], allowed: Tuple[str, ...]) -> None:
    unknown = sorted(set(args) - set(allowed))
    if unknown:
        raise ProjectError("unknown arguments: %s" % ", ".join(unknown))


def _host_model_ledger_path() -> Path:
    """Single default location for host-agent turns, overridable like the model store."""
    from .host_model import resolve_ledger_path

    return resolve_ledger_path()


def _host_model_handoff(exc: Any) -> Dict[str, Any]:
    """A deferred generation turn is a handoff, so return instructions rather than an error."""
    return tool_ok(
        {
            "schema_version": "awaiting-host-model-0.1",
            "status": "awaiting_host_model",
            "turn_id": getattr(exc, "turn_id", ""),
            "messages_sha256": getattr(exc, "messages_sha256", ""),
            "read_tool": "research_model_turns",
            "respond_tool": "research_model_respond",
            "resume": (
                "answer this turn with your own model, call research_model_respond, then "
                "re-run the same tool: the request hash replays your answer instead of asking again"
            ),
            "detail": str(exc),
            "boundary": (
                "no external API key is required and no gate moved: the answer is capability "
                "output that still passes manuscript audit, citation whitelists and "
                "result-number limits"
            ),
        }
    )


def _start_research_prompt(arguments: Dict[str, Any]) -> str:
    _reject_unknown(
        arguments,
        ("project_dir", "goal", "source", "venue_type", "language"),
    )
    project = _string(arguments, "project_dir", "research-project", maximum=300)
    goal = _string(arguments, "goal", required=True, maximum=2000)
    source = _choice(arguments, "source", ("local", "real", "openalex", "fixture"), "local")
    venue = _choice(
        arguments,
        "venue_type",
        (
            "zh_core_journal",
            "software_journal",
            "computer_journal",
            "en_conference",
            "en_journal",
            "zh_thesis",
        ),
        "zh_core_journal",
    )
    language = _choice(arguments, "language", ("zh", "en"), "zh")

    def quoted(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    return (
        "请使用本项目的科研智能体完成一次可审计的科研启动，不要在 Qoder 侧另起一套流程。\n\n"
        "1. 调用 research_bootstrap({project_dir: %s, goal: %s, source: %s, "
        "venue_type: %s, language: %s, run_now: true})；它会初始化项目、生成计划，"
        "并执行本地 TaskAgent pipeline。\n"
        "2. 读取 run/artifacts；若没有 API key，明确说明这是无 key 测试，"
        "不得声称已生成真实结果。\n"
        "3. 若使用 local 来源，先把 PDF/TXT/MD 放入 inputs/；不要伪造来源或全文。\n"
        "4. 需要写作时，调用 research_writing_pack → research_manuscript_draft；"
        "每句最多一个 REF，每个 claim 绑定一个 span。\n"
        "5. 句级支持评审：research_support_items → research_support_verdicts；"
        "修订后用 reuse=true，只重判变更句；然后 research_manuscript_audit。\n"
        "6. 若 route 为 hypothesis_design：调用 research_next_actions 读取 G1 的 "
        "idea/idea_ids，使用 review-idea 展示候选、prior-art、contrast 与短名单；"
        "G1 必须由人运行 flow g1，不得代选。\n"
        "7. claim/EA/protocol/closure/signature 只能由人类在 CLI 完成；"
        "不要通过 MCP 签署、批准、冻结或发布。\n"
        "8. Qoder verdict 是自评审，不是独立评审或 human gold；"
        "外部 Skill 只按 research_skill_instructions 的文本执行，不执行脚本。\n"
    ) % (
        quoted(project),
        quoted(goal),
        quoted(source),
        quoted(venue),
        quoted(language),
    )


def _review_draft_prompt(arguments: Dict[str, Any]) -> str:
    _reject_unknown(
        arguments,
        ("project_dir", "run_id", "draft", "judge_id", "output"),
    )
    project = _string(arguments, "project_dir", "research-project", maximum=300)
    run_id = _string(arguments, "run_id", required=True, maximum=120)
    draft = _string(arguments, "draft", required=True, maximum=500)
    judge_id = _string(arguments, "judge_id", "qoder-review", maximum=120)
    stem = Path(draft).stem or "draft"
    output = _string(
        arguments,
        "output",
        "drafts/%s-bound.md" % stem,
        maximum=500,
    )

    def quoted(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    return (
        "请用本项目的科研智能体审阅并改写一个已有草稿，不要另起一套流程。\n\n"
        "1. 确认该 run 已有 writing pack；若没有，先调用 "
        "research_writing_pack({project_dir: %s, run_id: %s})。\n"
        "2. 若草稿还没有 pack marker，调用 "
        "research_manuscript_bind({project_dir: %s, run_id: %s, draft: %s, "
        "output: %s})；检查 resolved_refs/unresolved_refs，未解析引用不是证据，"
        "必须先修正或删除。\n"
        "3. 对绑定稿调用 research_support_items({project_dir: %s, run_id: %s, "
        "draft: %s}) 获取句级项；逐条审阅后调用 research_support_verdicts"
        "({project_dir: %s, run_id: %s, draft: %s, judge_id: %s, verdicts})。\n"
        "4. 只对 weak_sections 使用 research_manuscript_section_edit；每句最多一个 "
        "REF，不新增 REF/数字；改写后复用同一 judge_id 并传 reuse=true，只重判变更句，"
        "再调用 research_manuscript_audit。\n"
        "5. 重复直到 weak_sections 为空或无法进一步改进；调用 research_next_actions。\n"
        "6. ledger ready 后，生成空白 human gold 模板并停下；Qoder 不得代填 gold。\n"
        "7. 边界：不通过 MCP 签署/批准/冻结/发布；Qoder verdicts 是自评审，"
        "不是 human gold；外部 Skill 只读文本、不执行脚本。\n"
    ) % (
        quoted(project),
        quoted(run_id),
        quoted(project),
        quoted(run_id),
        quoted(draft),
        quoted(output),
        quoted(project),
        quoted(run_id),
        quoted(output),
        quoted(project),
        quoted(run_id),
        quoted(output),
        quoted(judge_id),
    )


def _review_idea_prompt(arguments: Dict[str, Any]) -> str:
    _reject_unknown(arguments, ("project_dir", "run_id"))
    project = _string(arguments, "project_dir", "research-project", maximum=300)
    run_id = _string(arguments, "run_id", required=True, maximum=120)

    def quoted(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    return (
        "请用本项目的科研智能体审阅一个已生成的 idea 列表，但不要替人做 G1。\n\n"
        "1. 调用 research_status({project_dir: %s, run_id: %s})；读取 run 的 `idea` 字段；"
        "若缺失，再调用 research_next_actions。\n"
        "2. 逐个候选展示：idea_id、标题、prior_art_scope（live_search/live_abstract/"
        "s1_corpus/none）、has_contrast、evidence_count/source_count、"
        "novelty_status=unverified、kill_criteria。\n"
        "3. 对每个候选说明 prior_art_delta：相对哪条 prior work 有何变化，"
        "以及什么结果会否证它；不要声称 novelty 已证明。\n"
        "4. 给出 advisory 对比：证据强度、跨来源、prior-art 风险、可测性、成本；"
        "不得给单一推荐或自动选短名单。\n"
        "5. 由人选择 idea_id，并在 CLI 运行 flow g1；不要通过 MCP 写 g1-decision 或签名。\n"
        "6. 边界：idea 只是候选帧；G1 必须人工；Qoder verdict 不是 human gold。\n"
    ) % (
        quoted(project),
        quoted(run_id),
    )


def _support_reuse_key(item: Dict[str, Any]) -> str:
    evidence = [
        [
            str(entry.get("ref_id") or ""),
            str(entry.get("ref") or ""),
            str(entry.get("text") or ""),
        ]
        for entry in item.get("evidence") or []
    ]
    payload = {
        "sentence": str(item.get("sentence") or ""),
        "mode": str(item.get("mode") or ""),
        "citation_mode": str(item.get("citation_mode") or ""),
        "evidence": evidence,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


class ResearchMCPService:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.client_info: Dict[str, Any] = {}
        # Pin the fingerprint to the modules this process imported. If it were computed per
        # request it would follow the files on disk and hide a stale long-lived server.
        build_info()

    def _project_path(self, project_dir: str) -> Path:
        return resolve_project(self.root, project_dir)

    def _open_project(self, project_dir: str) -> Path:
        project = self._project_path(project_dir)
        opened = open_project(project)
        return Path(opened["path"])

    def init(self, args: Dict[str, Any]) -> Dict[str, Any]:
        _reject_unknown(args, ("project_dir", "name"))
        project = self._project_path(_string(args, "project_dir", "research-project"))
        result = init_project(project, _string(args, "name", "", maximum=120))
        return tool_ok(
            {
                **result,
                "folders": list(PROJECT_DIRS),
                "next_step": "Add full texts to inputs/ if using source=local, then call research_plan or research_run.",
                "boundary": PROJECT_BOUNDARY,
            },
            summary=(
                "%s research project at %s\nfolders: %s\nnext: %s"
                % (
                    "created" if result["created"] else "reused",
                    result["path"],
                    ", ".join(PROJECT_DIRS),
                    "add full texts to inputs/ if source=local; then research_plan/research_run",
                )
            ),
        )

    def bootstrap(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .journal_skill_audit import load_profiles
        from .skill_registry import SkillRegistryStore

        _reject_unknown(
            args,
            (
                "project_dir",
                "name",
                "goal",
                "source",
                "task_type",
                "max_sources",
                "language",
                "venue_type",
                "flow_mode",
                "run_now",
                "run_dataset",
                "run_seeds",
                "skill_ids",
            ),
        )
        project = self._project_path(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        created = init_project(project, _string(args, "name", "", maximum=120))
        plan_args = {
            "project_dir": _string(args, "project_dir", "research-project", maximum=300),
            "goal": _string(args, "goal", required=True, maximum=2000),
            "source": _choice(args, "source", ("fixture", "real", "openalex", "local"), "local"),
            "task_type": _choice(
                args,
                "task_type",
                ("auto", "literature_review", "hypothesis_design", "experiment_validation", "full_research"),
                "auto",
            ),
            "max_sources": _integer(args, "max_sources", 6, 1, 30),
            "language": _choice(args, "language", ("zh", "en"), "zh"),
            "venue_type": _choice(
                args, "venue_type", (
                    "zh_core_journal",
                    "software_journal",
                    "computer_journal",
                    "en_conference",
                    "en_journal",
                    "zh_thesis",
                ), "zh_core_journal"
            ),
            "flow_mode": _choice(args, "flow_mode", ("review", "strict"), "review"),
        }
        planned = self.plan(plan_args)["structuredContent"]["plan"]
        store = SkillRegistryStore(Path(self._skill_registry_path()))
        enabled_skills = [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "license": item.get("license"),
                "has_scripts": bool(item.get("has_scripts")),
            }
            for item in store.list(enabled_only=True)
        ]
        requested = [str(value).strip() for value in (args.get("skill_ids") or []) if str(value).strip()]
        if requested:
            available = {str(item.get("id")) for item in enabled_skills}
            unknown = [value for value in requested if value not in available]
            if unknown:
                raise ProjectError("unknown or disabled skill: " + ", ".join(unknown))
        profiles = load_profiles().get("profiles") or {}
        journal_profiles = [
            {
                "venue_id": venue,
                "label": profile.get("label"),
                "sources": len(profile.get("sources") or []),
            }
            for venue, profile in profiles.items()
        ]
        next_steps = [
            "Add PDF/TXT/MD to inputs/ if using source=local.",
            "Call research_run with the same project/goal/source to execute the plan.",
            "Call research_skill_instructions({skill_id}) for any enabled Skill you want to follow yourself.",
        ]
        run_result = None
        if bool(args.get("run_now")):
            run_args = {
                **plan_args,
                "run_dataset": _choice(
                    args, "run_dataset", ("", "iris", "breast_cancer", "chemlab"), ""
                ),
                "run_seeds": _integer(args, "run_seeds", 3, 1, 10),
            }
            run_result = self.run(run_args)["structuredContent"]
            next_steps = [
                "Read the run result via research_status / research_list_artifacts.",
                "Call research_skill_instructions({skill_id}) for any enabled Skill you want to follow yourself.",
            ]
        return tool_ok(
            {
                "schema_version": "research-bootstrap-0.2",
                "project": created,
                "plan": planned,
                "available_skills": enabled_skills,
                "requested_skills": requested,
                "journal_profiles": journal_profiles,
                "run": run_result,
                "next_steps": next_steps,
                "boundary": (
                    "Bootstrap + optional bounded research_run through the local TaskAgent; "
                    "no external skill scripts, no claim/EA/gate/signature, and no approval."
                ),
            }
        )

    def plan(self, args: Dict[str, Any]) -> Dict[str, Any]:
        _reject_unknown(
            args,
            (
                "project_dir",
                "goal",
                "task_type",
                "source",
                "max_sources",
                "language",
                "venue_type",
                "flow_mode",
                "run_dataset",
            ),
        )
        from .task_agent import TaskAgent, TaskRequest

        goal = _string(args, "goal", required=True)
        source = _choice(args, "source", ("fixture", "real", "openalex", "local"), "")
        task_type = _choice(
            args,
            "task_type",
            (
                "auto",
                "literature_review",
                "hypothesis_design",
                "experiment_validation",
                "full_research",
            ),
            "auto",
        )
        flow_mode = _choice(args, "flow_mode", ("review", "strict"), "review")
        project = self._project_path(_string(args, "project_dir", "research-project"))
        request = TaskRequest(
            goal=goal,
            task_type=task_type,
            source=source,
            max_sources=_integer(args, "max_sources", 6, 1, 30),
            language=_choice(args, "language", ("zh", "en"), "zh"),
            venue_type=_choice(
                args,
                "venue_type",
                (
                    "zh_core_journal",
                    "software_journal",
                    "computer_journal",
                    "en_conference",
                    "en_journal",
                    "zh_thesis",
                ),
                "zh_core_journal",
            ),
            flow_mode=flow_mode,
            run_dataset=_choice(
                args, "run_dataset", ("", "iris", "breast_cancer", "chemlab"), ""
            ),
            corpus_dir=str(project / "inputs") if source == "local" else "",
        )
        plan = TaskAgent().plan(request)
        return tool_ok(
            {
                "project_dir": str(project),
                "project_initialized": (project / "project.json").is_file(),
                "plan": plan.to_dict(),
                "boundary": HUMAN_ONLY,
            }
        )

    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        _reject_unknown(args, tuple(RUN_PROPERTIES))
        from .task_agent import TaskRequest

        goal = _string(args, "goal", required=True)
        source = _choice(args, "source", ("fixture", "real", "openalex", "local"), "")
        task_type = _choice(
            args,
            "task_type",
            (
                "auto",
                "literature_review",
                "hypothesis_design",
                "experiment_validation",
                "full_research",
            ),
            "auto",
        )
        language = _choice(args, "language", ("zh", "en"), "zh")
        venue_type = _choice(
            args,
            "venue_type",
            (
                    "zh_core_journal",
                    "software_journal",
                    "computer_journal",
                    "en_conference",
                    "en_journal",
                    "zh_thesis",
                ),
            "zh_core_journal",
        )
        flow_mode = _choice(args, "flow_mode", ("review", "strict"), "review")
        run_dataset = _choice(
            args, "run_dataset", ("", "iris", "breast_cancer", "chemlab"), ""
        )
        project = self._open_project(_string(args, "project_dir", "research-project"))

        strict = _models_required()
        if strict and flow_mode == "review":
            flow_mode = "strict"

        corpus_dir = ""
        if source == "local":
            corpus_dir = str(project / "inputs")
            _require_local_inputs(Path(corpus_dir))

        g1_decision_file = _optional_project_file(
            project, args.get("g1_decision_file"), "g1_decision_file"
        )
        protocol_file = _optional_project_file(project, args.get("protocol_file"), "protocol_file")
        claim_file = _optional_project_file(project, args.get("claim_file"), "claim_file")
        bibliography_file = _optional_project_file(
            project, args.get("bibliography_file"), "bibliography_file"
        )
        run_dir_value = ""
        if _string(args, "run_dir", "", maximum=300):
            run_dir_value = str(project_file(project, _string(args, "run_dir"), "run_dir"))

        request = TaskRequest(
            goal=goal,
            task_type=task_type,
            deliverable=_string(args, "deliverable", "", maximum=120),
            language=language,
            venue_type=venue_type,
            source=source,
            max_sources=_integer(args, "max_sources", 6, 1, 30),
            corpus_dir=corpus_dir,
            run_dataset=run_dataset,
            run_dir=run_dir_value,
            run_seeds=_integer(args, "run_seeds", 3, 1, 10),
            flow_mode=flow_mode,
            g1_decision_file=g1_decision_file,
            protocol_file=protocol_file,
            claim_file=claim_file,
            bibliography_file=bibliography_file,
        )

        run_path = new_run_dir(project)
        run_id = run_path.name
        context = {
            "schema_version": "research-run-context-0.1",
            "run_id": run_id,
            "project_id": (open_project(project)["project"] or {}).get("project_id", ""),
            "created_at": _now(),
            "tool": "research_run",
            "client": dict(self.client_info),
            "request": {
                "goal": goal,
                "task_type": task_type,
                "source": source,
                "max_sources": request.max_sources,
                "language": language,
                "venue_type": venue_type,
                "flow_mode": flow_mode,
                "run_dataset": run_dataset,
                "run_seeds": request.run_seeds,
                "has_g1_decision": bool(g1_decision_file),
                "has_protocol": bool(protocol_file),
                "has_claim": bool(claim_file),
                "has_bibliography": bool(bibliography_file),
                "reuse_run_dir": run_dir_value,
            },
            "boundary": PROJECT_BOUNDARY,
        }
        write_json_atomic(run_path / "run-context.json", context)

        try:
            agent, model_notes = _build_task_agent()
            execution = agent.run(request, run_path)
        except Exception as exc:
            failure = {
                "schema_version": "research-run-startup-error-0.1",
                "run_id": run_id,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "boundary": HUMAN_ONLY,
            }
            write_json_atomic(run_path / "startup-error.json", failure)
            update_run_index(
                project,
                {
                    "run_id": run_id,
                    "status": "failed",
                    "route": "",
                    "stopped_at": "",
                    "goal": goal,
                    "created_at": _now(),
                    "failure": failure,
                },
            )
            raise

        warnings = list(execution.warnings) + list(model_notes)
        summary = {
            "schema_version": "research-run-result-0.1",
            "run_id": run_id,
            "project_dir": str(project),
            "run_dir": str(run_path),
            "task_id": execution.task_id,
            "status": execution.status,
            "route": execution.plan.route,
            "flow_mode": execution.plan.flow_mode,
            "stopped_at": execution.stopped_at,
            "fixture_mode": source == "fixture",
            "gates": list(execution.gates),
            "checks": list(execution.checks),
            "warnings": warnings,
            "failure": dict(execution.failure),
            "artifacts": sorted(execution.artifacts),
            "evidence_packages": _package_counts(execution.evidence_packages),
            "next_actions": _next_actions(project, run_id),
            "boundary": HUMAN_ONLY,
        }
        update_run_index(
            project,
            {
                "run_id": run_id,
                "status": execution.status,
                "route": execution.plan.route,
                "stopped_at": execution.stopped_at,
                "goal": goal,
                "created_at": _now(),
                "failure": dict(execution.failure),
            },
        )
        return tool_ok(
            summary,
            summary=(
                "run %s: %s | route=%s | stopped_at=%s\nrun_dir: %s\nartifacts: %s\nnext: %s"
                % (
                    run_id,
                    execution.status,
                    execution.plan.route,
                    execution.stopped_at or "-",
                    run_path,
                    ", ".join(summary["artifacts"]) or "-",
                    "; ".join(item["message"] for item in summary["next_actions"][:2]) or "read task-report.md",
                )
            ),
        )

    def _skill_registry_path(self) -> str:
        from .paths import DEFAULT_SKILL_REGISTRY_PATH

        return os.environ.get("RESEARCH_AGENT_SKILL_REGISTRY") or str(
            DEFAULT_SKILL_REGISTRY_PATH
        )

    def _skill_usage_path(self) -> str:
        from .paths import DEFAULT_SKILL_USAGE_PATH

        return os.environ.get("RESEARCH_AGENT_SKILL_USAGE") or str(
            DEFAULT_SKILL_USAGE_PATH
        )

    def host_contract(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read-only host negotiation: what this host can do and what will stop it.

        A plugin host needs this before it starts a run, otherwise it discovers the hard way that
        five stages suspend waiting for a model it cannot serve.
        """
        from .host_contract import host_contract as build_contract

        declared = args.get("capabilities") or []
        if isinstance(declared, str):
            declared = [item.strip() for item in declared.split(",") if item.strip()]
        outbox = str(args.get("outbox_dir") or "").strip()
        report = build_contract(
            declared=[str(item) for item in declared],
            outbox=Path(outbox) if outbox else None,
        )
        reachable = sum(
            1
            for key in ("in_process_api", "http_runtime", "mcp_stdio", "file_drop")
            if report["transports"].get(key) is True
        )
        return tool_ok(
            report,
            "%d transport(s) reachable, %d stage(s) suspend for the host model, %d blocker(s)"
            % (
                reachable,
                len(report["model_supply"]["stages_suspended_for_host_answer"]),
                len(report["blocked"]),
            ),
        )

    def skill_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .skill_registry import SkillRegistryStore

        _reject_unknown(args, ())
        snapshot = SkillRegistryStore(Path(self._skill_registry_path())).snapshot()
        skills = [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "description": str(item.get("description") or "")[:300],
                "version": item.get("version"),
                "license": item.get("license"),
                "source": item.get("source"),
                "enabled": bool(item.get("enabled")),
                "has_scripts": bool(item.get("has_scripts")),
                "risk_flags": list(item.get("risk_flags") or []),
            }
            for item in snapshot.get("skills") or []
            if isinstance(item, dict)
        ]
        return tool_ok(
            {
                "schema_version": snapshot.get("schema_version"),
                "count": len(skills),
                "skills": skills,
                "boundary": (
                    "catalog projection only; instructions and local paths are withheld; "
                    "scripts are not executed through MCP"
                ),
            }
        )

    def skill_instructions(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .skill_registry import SkillRegistryStore

        _reject_unknown(args, ("skill_id", "max_chars"))
        skill_id = _string(args, "skill_id", required=True, maximum=120)
        max_chars = _integer(args, "max_chars", 8000, 500, 8000)
        store = SkillRegistryStore(Path(self._skill_registry_path()))
        skill = next(
            (
                item
                for item in store.list(enabled_only=True)
                if skill_id in (str(item.get("id")), str(item.get("name")))
            ),
            None,
        )
        if skill is None:
            raise ProjectError("enabled skill not found: " + skill_id)
        instructions = str(skill.get("instructions") or "")
        return tool_ok(
            {
                "schema_version": "skill-instructions-0.1",
                "skill_id": skill.get("id"),
                "name": skill.get("name"),
                "description": str(skill.get("description") or "")[:1024],
                "version": skill.get("version"),
                "license": skill.get("license"),
                "content_hash": skill.get("content_hash"),
                "has_scripts": bool(skill.get("has_scripts")),
                "risk_flags": list(skill.get("risk_flags") or []),
                "instructions": instructions[:max_chars],
                "truncated": len(instructions) > max_chars,
                "boundary": (
                    "Untrusted external instructions for Qoder itself; no model call, "
                    "no script execution, no claims/evidence/gates, no local paths."
                ),
            }
        )

    def skill_invoke(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .external_skills import invoke_external_skill

        _reject_unknown(
            args,
            (
                "skill_id",
                "input",
                "profile_id",
                "context",
                "project_dir",
                "distill_on_success",
                "license",
                "human_reason",
                "source_url",
            ),
        )
        skill_id = _string(args, "skill_id", required=True, maximum=120)
        text = _string(args, "input", required=True, maximum=12000)
        profile_id = _string(args, "profile_id", "", maximum=120)
        profile_id = profile_id or os.environ.get("RESEARCH_AGENT_SKILL_PROFILE", "").strip()
        if not profile_id:
            raise ProjectError(
                "profile_id is required (or set RESEARCH_AGENT_SKILL_PROFILE) for external skill invocation"
            )
        context = _string(args, "context", "", maximum=12000)
        distill_on_success = _boolean(args, "distill_on_success", False)
        human_reason = _string(args, "human_reason", "", maximum=1000)
        if distill_on_success and not human_reason:
            raise ProjectError("human_reason is required when distill_on_success is true")
        output_path = None
        library_dir = None
        project_value = _string(args, "project_dir", "", maximum=300)
        if distill_on_success and not project_value:
            raise ProjectError("project_dir is required when distill_on_success is true")
        if project_value:
            project = self._open_project(project_value)
            notes = project / "notes" / "skill-invocations"
            notes.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9._-]+", "-", skill_id)[:60] or "skill"
            output_path = str(notes / ("%s-%s.json" % (_now().replace(":", ""), safe)))
            if distill_on_success:
                library_dir = str(project / "notes" / "skill-library")
        result = invoke_external_skill(
            skill_id=skill_id,
            input_text=text,
            profile_id=profile_id,
            context=context,
            registry_path=self._skill_registry_path(),
            usage_path=self._skill_usage_path(),
            store_path=os.environ.get("RESEARCH_AGENT_MODEL_STORE") or None,
            output_path=output_path,
            distill_on_success=distill_on_success,
            distill_license=_string(args, "license", "", maximum=200),
            distill_reason=human_reason,
            distill_source_url=_string(args, "source_url", "", maximum=500),
            library_dir=library_dir,
        )
        return tool_ok(result)

    def skill_distill(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .skill_distill import distill_skill

        _reject_unknown(
            args, ("skill_id", "project_dir", "human_reason", "license", "source_url")
        )
        skill_id = _string(args, "skill_id", required=True, maximum=120)
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        human_reason = _string(args, "human_reason", required=True, maximum=1000)
        result = distill_skill(
            skill_id=skill_id,
            library_dir=project / "notes" / "skill-library",
            registry_path=Path(self._skill_registry_path()),
            license=_string(args, "license", "", maximum=200),
            human_reason=human_reason,
            source_url=_string(args, "source_url", "", maximum=500),
        )
        receipts = project / "notes" / "skill-distillations"
        receipts.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", skill_id)[:60] or "skill"
        write_json_atomic(
            receipts / ("%s-%s.json" % (_now().replace(":", ""), safe)),
            result,
        )
        return tool_ok(result)

    def manuscript_revise(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .revision import load_review_comments, run_revision

        _reject_unknown(
            args,
            (
                "project_dir",
                "draft",
                "data",
                "metrics_file",
                "figures_file",
                "venue",
                "profile_id",
                "sections",
                "formats",
                "goal",
                "review_file",
                "plan_file",
                "auto_plan",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        draft = project_file(
            project, _string(args, "draft", required=True, maximum=500), "draft"
        )
        raw_data = args.get("data") or []
        if not isinstance(raw_data, list):
            raise ProjectError("data must be an array of project-relative paths")
        if len(raw_data) > 10:
            raise ProjectError("at most 10 data files are supported")
        data_paths = []
        for index, value in enumerate(raw_data):
            if not isinstance(value, str) or not value.strip():
                raise ProjectError("data[%d] must be a non-empty string" % index)
            data_paths.append(project_file(project, value, "data[%d]" % index))
        metrics_file = _optional_project_file(
            project, args.get("metrics_file"), "metrics_file"
        )
        figures_file = _optional_project_file(
            project, args.get("figures_file"), "figures_file"
        )
        venue = _choice(
            args,
            "venue",
            ("zh_core_journal", "software_journal", "computer_journal"),
            "zh_core_journal",
        )
        raw_sections = args.get("sections") or []
        if not isinstance(raw_sections, list):
            raise ProjectError("sections must be an array of strings")
        sections = [str(item).strip() for item in raw_sections if str(item).strip()][:30]
        raw_formats = args.get("formats") or ["md", "tex", "docx", "pdf"]
        if not isinstance(raw_formats, list) or not raw_formats:
            raise ProjectError("formats must be a non-empty array")
        allowed_formats = ("md", "tex", "docx", "pdf", "html")
        formats = []
        for item in raw_formats:
            value = str(item).strip().lower()
            if value not in allowed_formats:
                raise ProjectError("unsupported format: " + value)
            if value not in formats:
                formats.append(value)
        profile_id = _string(args, "profile_id", "", maximum=120)
        profile_id = profile_id or os.environ.get(
            "RESEARCH_AGENT_REVISION_PROFILE", ""
        ).strip()
        revision_id = "REV-%s-%s" % (
            _now().replace(":", "").replace("-", "").replace("+", ""),
            uuid.uuid4().hex[:6],
        )
        output_dir = project / "revisions" / revision_id
        result = run_revision(
            draft_path=draft,
            output_dir=output_dir,
            data_paths=data_paths,
            metrics_path=Path(metrics_file) if metrics_file else None,
            figures_path=Path(figures_file) if figures_file else None,
            venue=venue,
            profile_id=profile_id,
            store_path=os.environ.get("RESEARCH_AGENT_MODEL_STORE") or None,
            sections=sections,
            formats=formats,
            goal=_string(args, "goal", "", maximum=1000),
            plan=(
                json.loads(project_file(project, _string(args, "plan_file", "", maximum=500), "plan_file").read_text(encoding="utf-8"))
                if _string(args, "plan_file", "", maximum=500) else None
            ),
            auto_plan=_boolean(args, "auto_plan", False),
            review_comments=(
                load_review_comments(
                    project_file(project, _string(args, "review_file", "", maximum=500), "review_file")
                )
                if _string(args, "review_file", "", maximum=500) else None
            ),
        )
        audit = result.get("audit") or {}
        summary = {
            "schema_version": result.get("schema_version"),
            "revision_id": revision_id,
            "output_dir": result.get("output_dir"),
            "draft": result.get("draft"),
            "status": result.get("status"),
            "writer_mode": result.get("writer_mode"),
            "venue": result.get("venue"),
            "review_ready": audit.get("review_ready"),
            "format_ready": audit.get("format_ready"),
            "submission_ready": False,
            "blockers": list(audit.get("blockers") or [])[:20],
            "warnings": list(audit.get("warnings") or [])[:20],
            "changed_blocks": (audit.get("rewrite") or {}).get("changed_blocks", 0),
            "metrics": audit.get("metrics") or [],
            "sentence_ledger_summary": audit.get("sentence_ledger_summary") or {},
            "figures": [
                {
                    "figure_id": item.get("figure_id"),
                    "png": item.get("png"),
                    "output_sha256": item.get("output_sha256"),
                }
                for item in (audit.get("figures") or [])
            ],
            "files": result.get("files") or {},
            "boundary": result.get("boundary"),
        }
        write_json_atomic(output_dir / "mcp-revision-summary.json", summary)
        return tool_ok(summary)

    def figure_templates(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .figure_workflow import list_templates

        _reject_unknown(args, ())
        return tool_ok(list_templates())

    def figure_render(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .figure_workflow import FigureWorkflowError, render_scene, template_path

        _reject_unknown(
            args, ("project_dir", "scene", "template_id", "title", "description", "name", "formats")
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        scene_value = _string(args, "scene", "", maximum=500)
        template_id = _string(args, "template_id", "", maximum=80)
        if bool(scene_value) == bool(template_id):
            raise ProjectError("provide exactly one of scene or template_id")
        if scene_value:
            scene_path = project_file(project, scene_value, "scene")
            fallback_name = Path(scene_value).stem
        else:
            try:
                scene_path = template_path(template_id)
            except FigureWorkflowError as exc:
                raise ProjectError(str(exc))
            fallback_name = template_id
        raw_formats = args.get("formats") or ["svg", "png"]
        if not isinstance(raw_formats, list):
            raise ProjectError("formats must be an array")
        formats = []
        for item in raw_formats:
            value = str(item).lower().strip()
            if value not in ("svg", "png"):
                raise ProjectError("unsupported figure format: " + value)
            if value not in formats:
                formats.append(value)
        name = _string(args, "name", fallback_name, maximum=60)
        safe = re.sub(r"[^A-Za-z0-9._\-]+", "-", name)[:60] or "figure"
        output_dir = project / "figures" / safe
        result = render_scene(
            scene_path=scene_path,
            output_dir=output_dir,
            title=_string(args, "title", "", maximum=200),
            description=_string(args, "description", "", maximum=1000),
            output_name=safe,
            formats=formats,
            template_id=template_id,
        )
        return tool_ok(result)

    def literature_fetch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .adapters.arxiv_fetcher import ArxivFetchError, ArxivFetcher

        _reject_unknown(
            args, ("project_dir", "query", "max_results", "allow_network", "timeout")
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        query = _string(args, "query", required=True, maximum=300)
        allow_network = _boolean(args, "allow_network", False)
        if not allow_network:
            raise ProjectError("network access is disabled; set allow_network=true explicitly")
        target = project / "inputs"
        target.mkdir(parents=True, exist_ok=True)
        try:
            result = ArxivFetcher(
                timeout=_integer(args, "timeout", 30, 5, 120)
            ).fetch(
                query=query,
                target_dir=target,
                max_results=_integer(args, "max_results", 4, 1, 10),
                allow_network=True,
            )
        except ArxivFetchError as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def literature_synthesis(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .literature_synthesis import SynthesisError, synthesize_literature

        _reject_unknown(args, ("project_dir", "run_id", "max_themes"))
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        try:
            result = synthesize_literature(
                project,
                _string(args, "run_id", required=True, maximum=120),
                max_themes=_integer(args, "max_themes", 7, 3, 10),
            )
        except (SynthesisError, OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def conference_fetch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .adapters.conference_fetcher import ConferenceFetchError, fetch_top_conference_corpus

        _reject_unknown(
            args,
            (
                "project_dir",
                "topic",
                "venues",
                "years",
                "max_papers",
                "max_per_venue",
                "allow_network",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        topic = _string(args, "topic", required=True, maximum=300)
        allow_network = _boolean(args, "allow_network", False)
        if not allow_network:
            raise ProjectError("network access is disabled; set allow_network=true explicitly")
        raw_venues = args.get("venues") or ["NeurIPS", "ICLR", "ICML", "ACL"]
        if not isinstance(raw_venues, list):
            raise ProjectError("venues must be an array")
        venues = [str(item).strip() for item in raw_venues if str(item).strip()]
        raw_years = args.get("years") or [2024, 2025, 2026]
        if not isinstance(raw_years, list):
            raise ProjectError("years must be an array")
        years = []
        for item in raw_years:
            if isinstance(item, bool) or not isinstance(item, int):
                raise ProjectError("years must contain integers")
            years.append(item)
        target = project / "inputs"
        target.mkdir(parents=True, exist_ok=True)
        try:
            result = fetch_top_conference_corpus(
                target_dir=target,
                venues=venues,
                years=years,
                topic=topic,
                max_papers=_integer(args, "max_papers", 24, 1, 80),
                max_per_venue=_integer(args, "max_per_venue", 4, 1, 12),
                allow_network=True,
            )
        except ConferenceFetchError as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def writing_pack(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .writing_pack import build_writing_pack, render_writing_pack

        _reject_unknown(
            args,
            (
                "project_dir",
                "run_id",
                "language",
                "venue",
                "max_sources",
                "max_spans_per_source",
                "experiment_id",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        run_id = _string(args, "run_id", required=True, maximum=120)
        language = _choice(args, "language", ("zh", "en"), "zh")
        venue = _choice(
            args,
            "venue",
            ("zh_core_journal", "software_journal", "computer_journal", "en_conference"),
            "zh_core_journal",
        )
        target = run_dir(project, run_id)
        if not target.is_dir():
            raise ProjectError("run does not exist: " + run_id)
        pack = build_writing_pack(
            project,
            run_id,
            language=language,
            venue=venue,
            max_sources=_integer(args, "max_sources", 8, 1, 20),
            max_spans_per_source=_integer(args, "max_spans_per_source", 3, 1, 8),
            experiment_id=_string(args, "experiment_id", "", maximum=80),
        )
        write_json_atomic(target / "writing-pack.json", pack)
        pack_md = target / "writing-pack.md"
        with open(str(pack_md), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_writing_pack(pack))
        result = {**pack, "files": {"json": str(target / "writing-pack.json"), "markdown": str(pack_md)}}
        return tool_ok(result)

    def grant_template(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .modules.grant import grant_template

        _reject_unknown(args, ("project_dir", "scheme", "output"))
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        scheme = _choice(args, "scheme", ("nsfc", "nssfc", "generic"), "nsfc")
        output = _string(args, "output", "grant-template.json", maximum=300)
        path = project_output_path(project, output, "grant template")
        data = grant_template(scheme)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, data)
        relative = str(path.resolve().relative_to(project.resolve()))
        return tool_ok(
            {
                "path": relative,
                "scheme": scheme,
                "sections": list(data["sections"]),
                "next": "fill sections and call research_venue_audit with kind=grant",
                "boundary": (
                    "blank scaffold only; the applicant supplies science and budget; "
                    "nothing is signed, approved or submitted"
                ),
            },
            summary="grant template at %s (%s)" % (relative, scheme),
        )

    def venue_audit(self, args: Dict[str, Any]) -> Dict[str, Any]:
        import json as _json

        from .venue_audit import audit_chinese_journal, audit_grant

        _reject_unknown(
            args,
            (
                "project_dir",
                "file",
                "kind",
                "profile",
                "scheme",
                "anonymous",
                "identity_removed",
                "ai_statement",
                "skill_pack",
                "skill_pack_root",
                "venue",
                "skill_stage",
                "skill_profile",
                "skill_max_items",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        try:
            path = project_file(
                project, _string(args, "file", required=True, maximum=500), "venue audit input"
            )
        except ValueError as exc:
            raise ProjectError(str(exc))
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProjectError("venue audit input is not readable JSON: %s" % exc)
        kind = _choice(args, "kind", ("zh_journal", "grant"), "zh_journal")
        try:
            if kind == "zh_journal":
                result = audit_chinese_journal(
                    data,
                    profile_name=_string(
                        args, "profile", "zh_core_journal", maximum=80
                    ),
                )
            else:
                sections = data.get("sections") if isinstance(data, dict) else None
                if not isinstance(sections, dict):
                    raise ProjectError("grant input needs a sections object")
                evidence = data.get("evidence_refs") if isinstance(data, dict) else None
                result = audit_grant(
                    sections,
                    scheme=_choice(args, "scheme", ("nsfc", "nssfc", "generic"), "nsfc"),
                    evidence_refs=[str(item) for item in evidence or []],
                    anonymous=bool(args.get("anonymous")),
                    identity_removed=bool(args.get("identity_removed")),
                    ai_statement=bool(args.get("ai_statement")),
                )
        except ValueError as exc:
            raise ProjectError(str(exc))
        from .pack_audit import attach_pack_rubric, manuscript_pack_text

        def local(raw: str) -> str:
            if not raw:
                return ""
            candidate = Path(raw).expanduser()
            return str(candidate if candidate.is_absolute() else (self.root / candidate))

        try:
            attach_pack_rubric(
                result,
                manuscript_pack_text(data, kind),
                pack_dir=local(_string(args, "skill_pack", "", maximum=300)),
                pack_root=local(_string(args, "skill_pack_root", "", maximum=300)),
                venue=_string(args, "venue", "", maximum=160),
                stage=_string(args, "skill_stage", "", maximum=30),
                profile=_string(args, "skill_profile", "", maximum=30),
                max_items=_integer(args, "skill_max_items", 40, 1, 300),
            )
        except ValueError as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def manuscript_audit(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .writing_audit import write_audit

        _reject_unknown(
            args,
            (
                "project_dir",
                "run_id",
                "draft",
                "language",
                "venue",
                "experiment_id",
                "semantic",
                "strict_support",
                "strict_pack_binding",
                "support_votes",
                "support_max_items",
                "refresh_support",
                "judge_profile",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        run_id = _string(args, "run_id", required=True, maximum=120)
        draft = project_file(
            project, _string(args, "draft", required=True, maximum=500), "draft"
        )
        target = run_dir(project, run_id)
        if not target.is_dir():
            raise ProjectError("run does not exist: " + run_id)
        language = _choice(args, "language", ("zh", "en"), "zh")
        venue = _choice(
            args,
            "venue",
            ("zh_core_journal", "software_journal", "computer_journal", "en_conference"),
            "zh_core_journal",
        )
        support_judge = None
        judge_model_id = ""
        strict_support = bool(args.get("strict_support"))
        judge_profile = str(args.get("judge_profile") or "").strip()
        if bool(args.get("semantic")) or strict_support or judge_profile:
            if judge_profile:
                support_judge, _note = self._gateway_support_judge(
                    judge_profile, strict=strict_support
                )
                judge_model_id = "profile:" + judge_profile
            else:
                from .adapters.support_judge import support_judge_from_model
                from .manuscript_review import default_review_model

                judge_model = default_review_model()
                support_judge = support_judge_from_model(
                    judge_model, strict=strict_support
                )
                judge_model_id = getattr(
                    judge_model, "model_id", type(judge_model).__name__
                )
        audit = write_audit(
            draft_path=draft,
            output_dir=target,
            project=project,
            run_id=run_id,
            language=language,
            venue=venue,
            experiment_id=_string(args, "experiment_id", "", maximum=80),
            support_judge=support_judge,
            strict_support=strict_support,
            judge_model_id=judge_model_id,
            strict_pack_binding=bool(args.get("strict_pack_binding")),
            support_votes=_integer(args, "support_votes", 1, 1, 5),
            support_max_items=_integer(args, "support_max_items", 80, 1, 200),
            refresh_support=bool(args.get("refresh_support")),
        )
        return tool_ok(audit)

    def _gateway_critic_model(self, profile_id: str, purpose: str):
        """Resolve one critic role onto an explicitly named supply, not the module binding."""
        from .adapters.research_models import model_for_profile
        from .models import GatewayStore, ModelGateway, ModelRequiredError

        store_path = Path(
            os.environ.get("RESEARCH_AGENT_MODEL_STORE")
            or str(DEFAULT_MODEL_STORE_PATH)
        )
        gateway = ModelGateway(GatewayStore(store_path))
        try:
            port, note = model_for_profile(
                profile_id,
                module="idea",
                purpose=purpose,
                store_path=store_path,
                gateway=gateway,
                strict=True,
            )
        except ModelRequiredError as exc:
            raise ProjectError(str(exc))
        if port is None:
            raise ProjectError(note or "critic profile is not configured: " + profile_id)
        return port

    def _critic_models(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .innovation_review import REVIEW_ROLES
        from .model_catalog import critic_panel

        assigned = args.get("critic_profiles")
        if assigned is None:
            assigned = {}
        if not isinstance(assigned, dict):
            raise ProjectError("critic_profiles must be an object of role -> profile id")
        unknown = sorted(set(assigned) - set(REVIEW_ROLES))
        if unknown:
            raise ProjectError(
                "unknown critic role(s): %s; expected %s"
                % (", ".join(unknown), ", ".join(REVIEW_ROLES))
            )
        if args.get("independent") and not assigned:
            panel = critic_panel(
                Path(
                    os.environ.get("RESEARCH_AGENT_MODEL_STORE")
                    or str(DEFAULT_MODEL_STORE_PATH)
                )
            )
            if not panel["panel_possible"]:
                raise ProjectError(
                    "no independent bench is available: %d distinct provider+model supply for %d "
                    "critic roles, missing %d; configure another provider or bind a host profile "
                    "naming a different model"
                    % (
                        panel["distinct_supplies"],
                        len(REVIEW_ROLES),
                        panel["missing_supplies"],
                    )
                )
            assigned = dict(panel["suggested"])
        models = {}
        for role, profile_id in assigned.items():
            profile_id = str(profile_id or "").strip()
            if not profile_id:
                raise ProjectError("critic_profiles.%s must be a profile id" % role)
            models[role] = self._gateway_critic_model(
                profile_id, "innovation critic: %s" % role
            )
        return models

    def innovation_review(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .innovation_review import InnovationReviewError, run_innovation_review
        from .models import ModelTurnPending

        _reject_unknown(
            args,
            (
                "project_dir",
                "run_id",
                "topic",
                "direction",
                "rounds",
                "max_ideas",
                "threshold",
                "critic_profiles",
                "independent",
                "prior_art_corpus",
                "prior_art_limit",
                "language",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        corpus_arg = _string(args, "prior_art_corpus", "", maximum=300)
        corpus_path = None
        if corpus_arg:
            candidate = Path(corpus_arg)
            corpus_path = candidate if candidate.is_absolute() else (project / candidate)
        try:
            result = run_innovation_review(
                project,
                _string(args, "run_id", required=True, maximum=120),
                topic=_string(args, "topic", "", maximum=300),
                direction=_string(args, "direction", "", maximum=1200),
                rounds=_integer(args, "rounds", 2, 1, 5),
                max_ideas=_integer(args, "max_ideas", 5, 3, 8),
                threshold=float(args.get("threshold", 8.0)),
                critic_models=self._critic_models(args),
                prior_art_corpus=corpus_path,
                prior_art_limit=_integer(args, "prior_art_limit", 6, 1, 20),
                language=_string(args, "language", "zh", maximum=8),
            )
        except ModelTurnPending as exc:
            return _host_model_handoff(exc)
        except (InnovationReviewError, OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def manuscript_draft(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .manuscript_writer import ManuscriptWriterError, generate_manuscript
        from .models import ModelTurnPending

        _reject_unknown(args, ("project_dir", "run_id", "output", "overwrite"))
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        run_id = _string(args, "run_id", required=True, maximum=120)
        output = project_output_path(
            project, _string(args, "output", required=True, maximum=500), "output"
        )
        if output.exists() and not _boolean(args, "overwrite", False):
            raise ProjectError("output already exists; pass overwrite=true to replace: " + str(output))
        try:
            result = generate_manuscript(project, run_id, output)
        except ModelTurnPending as exc:
            return _host_model_handoff(exc)
        except (ManuscriptWriterError, OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        result.pop("pack", None)
        result.pop("innovation", None)
        result["files"] = {"draft": str(output)}
        return tool_ok(result)

    def experiment_codegen(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .experiment_codegen import ExperimentCodegenError, generate_experiment_code

        _reject_unknown(
            args,
            (
                "project_dir",
                "run_id",
                "data",
                "target",
                "features",
                "task",
                "methods",
                "metric",
                "experiment_id",
                "test_size",
                "seeds",
                "cv_folds",
                "alpha_grid",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        raw_features = args.get("features")
        if not isinstance(raw_features, list) or not raw_features:
            raise ProjectError("features must be a non-empty array")
        raw_methods = args.get("methods") or ["dummy", "ridge"]
        if not isinstance(raw_methods, list):
            raise ProjectError("methods must be an array")
        raw_alpha = args.get("alpha_grid")
        if raw_alpha is not None and not isinstance(raw_alpha, list):
            raise ProjectError("alpha_grid must be an array")
        try:
            result = generate_experiment_code(
                project,
                _string(args, "run_id", required=True, maximum=120),
                data_path=_string(args, "data", required=True, maximum=500),
                target=_string(args, "target", required=True, maximum=200),
                features=[str(item) for item in raw_features],
                task=_choice(args, "task", ("regression", "classification"), "regression"),
                methods=[str(item) for item in raw_methods],
                metric=_string(args, "metric", "", maximum=40),
                experiment_id=_string(args, "experiment_id", "", maximum=80),
                test_size=float(args.get("test_size", 0.2)),
                seeds=_integer(args, "seeds", 3, 1, 10),
                cv_folds=_integer(args, "cv_folds", 0, 0, 10),
                alpha_grid=(
                    [float(item) for item in raw_alpha] if raw_alpha else None
                ),
            )
        except (ExperimentCodegenError, OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def experiment_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .experiment_runner import ExperimentExecutionError, experiment_status

        _reject_unknown(args, ("project_dir", "experiment_id"))
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        try:
            result = experiment_status(
                project, _string(args, "experiment_id", required=True, maximum=80)
            )
        except (ExperimentExecutionError, OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def _gateway_support_judge(self, profile_id: str, *, strict: bool = False):
        from .adapters.support_judge import gateway_support_judge
        from .models import GatewayStore, ModelGateway

        store_path = Path(
            os.environ.get("RESEARCH_AGENT_MODEL_STORE")
            or str(DEFAULT_MODEL_STORE_PATH)
        )
        gateway = ModelGateway(GatewayStore(store_path))
        judge, note = gateway_support_judge(
            profile_id=profile_id, gateway=gateway, strict=strict
        )
        if judge is None:
            raise ProjectError(note or "judge profile is not configured: " + profile_id)
        return judge, note

    def empirical_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .empirical_loop import EmpiricalLoopError, check_empirical_loop

        _reject_unknown(args, ("project_dir", "run_id", "experiment_id"))
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        try:
            result = check_empirical_loop(
                project,
                _string(args, "run_id", required=True, maximum=120),
                _string(args, "experiment_id", required=True, maximum=80),
            )
        except (EmpiricalLoopError, OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def study_baseline(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Pair a budget-matched tuned reference with a study artifact; read-only."""
        from .baseline_lab import compare_with_study

        _reject_unknown(args, ("study", "seeds", "folds"))

        def local(raw: str) -> Path:
            candidate = Path(raw).expanduser()
            return candidate if candidate.is_absolute() else (self.root / candidate)

        path = local(_string(args, "study", required=True, maximum=300))
        seeds = args.get("seeds")
        chosen = [int(item) for item in seeds] if isinstance(seeds, list) else None
        try:
            study = json.loads(path.read_text(encoding="utf-8"))
            result = compare_with_study(study, seeds=chosen, folds=_integer(args, "folds", 0, 0, 10) or None)
        except (OSError, ValueError, KeyError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def number_provenance(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Trace a draft's numbers back to artifacts on disk; read-only, grants nothing."""
        from .number_provenance import provenance_for_draft

        _reject_unknown(args, ("draft", "corpus", "max_files"))

        def local(raw: str) -> Path:
            candidate = Path(raw).expanduser()
            return candidate if candidate.is_absolute() else (self.root / candidate)

        try:
            result = provenance_for_draft(
                local(_string(args, "draft", required=True, maximum=300)),
                local(_string(args, "corpus", required=True, maximum=300)),
                max_files=_integer(args, "max_files", 20000, 1, 60000),
            )
        except (OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def skill_packs(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Advisory read-only access to local skill packs: scan, venue route, rubric coverage."""
        from .skill_packs import DEFAULT_MAX_ITEMS, STAGE_PROFILES, coverage_report, find_venue, scan_pack

        _reject_unknown(
            args,
            ("action", "pack_dir", "pack_root", "venue", "artifact", "stage", "profile", "max_items"),
        )
        action = _string(args, "action", required=True, maximum=20)
        if action not in ("scan", "route", "coverage"):
            raise ProjectError("action must be scan, route or coverage")
        stage = _string(args, "stage", "", maximum=30)
        profile = _string(args, "profile", "", maximum=30)
        if stage and profile:
            raise ProjectError("choose stage or profile, not both")
        if profile and profile not in STAGE_PROFILES:
            raise ProjectError("unknown profile: " + profile)
        max_items = _integer(args, "max_items", DEFAULT_MAX_ITEMS, 1, 300)
        stages = list(STAGE_PROFILES.get(profile, ()))

        def local(raw: str) -> Path:
            candidate = Path(raw).expanduser()
            return candidate if candidate.is_absolute() else (self.root / candidate)

        pack_dir = _string(args, "pack_dir", "", maximum=300)
        pack_root = _string(args, "pack_root", "", maximum=300)
        venue = _string(args, "venue", "", maximum=160)
        try:
            if action == "route":
                result = find_venue(
                    local(_string(args, "pack_root", required=True, maximum=300)),
                    _string(args, "venue", required=True, maximum=160),
                )
                return tool_ok(result)
            from .pack_audit import resolve_pack_dir, route_for_venue

            # the same routing the CLI offers: pack_root plus venue resolves a pack for scan and
            # coverage too, or the two faces answer the same request differently
            resolved = resolve_pack_dir(pack_dir, pack_root, venue)
            if not resolved:
                raise ValueError(
                    "pass pack_dir, or pack_root together with venue, to pick a skill pack"
                )
            pack = scan_pack(
                local(resolved),
                stage=stage,
                max_items=max_items,
                stages=stages,
            )
            if action == "scan":
                return tool_ok(pack)
            artifact = local(_string(args, "artifact", required=True, maximum=300))
            from .pack_audit import coverage_input

            source_text, bundle_fields = coverage_input(artifact)
            coverage = coverage_report(
                pack["checklist"], source_text, stage=stage, stages=stages,
                artifact=bundle_fields.get("artifact_base"),
            )
            coverage.update(bundle_fields)
            coverage["pack"] = pack["pack"]
            coverage["license"] = pack["license"]
            coverage["profile"] = profile
            route = route_for_venue(pack_root, venue)
            coverage["route"] = (route or {}).get("best") or {}
            coverage["route_confidence"] = (route or {}).get("confidence") or ""
            if (route or {}).get("confidence") == "low":
                coverage["warnings"] = (coverage.get("warnings") or []) + [
                    "low-confidence route to %s; verify the pack directory by hand before trusting "
                    "these counts" % (route.get("best") or {}).get("pack_dir", "")
                ]
            # the scored denominator travels with the score, or the number is misleading
            coverage["pack_scope"] = {
                "pack": pack["pack"],
                "checklist_items": len(pack["checklist"]),
                "checklist_total": pack["checklist_total"],
                "max_items": max_items,
                "limit_applied": pack["limit_applied"],
                "truncated": pack["truncated"],
                "warnings": pack["warnings"],
            }
            if pack["truncated"]:
                coverage["boundary"] = coverage.get("boundary", "") + (
                    " this score uses only the first %d of %d pack items, so it is a partial "
                    "rubric" % (len(pack["checklist"]), pack["checklist_total"])
                )
            return tool_ok(coverage)
        except (OSError, ValueError) as exc:
            raise ProjectError(str(exc))

    def mandate_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .mandate import build_mandate_status

        _reject_unknown(args, ("project_dir", "max_runs"))
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        max_runs = _integer(args, "max_runs", 20, 1, 200)
        try:
            # the delegation view is project-level: it aggregates the run capsules, so there
            # is no run_id to pass and inventing one would silently narrow the window
            result = build_mandate_status(project, max_runs=max_runs)
        except (OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def closure_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .closure_profiles import closure_status

        _reject_unknown(args, ("project_dir", "run_id", "experiment_id"))
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        run_id = _string(args, "run_id", "", maximum=120)
        experiment_id = _string(args, "experiment_id", "", maximum=80)
        if run_id and experiment_id:
            raise ProjectError("provide run_id or experiment_id, not both")
        try:
            result = closure_status(
                project, run_id=run_id, experiment_id=experiment_id
            )
        except (OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def evolution_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .rsi import StepLedger, ledger_story

        _reject_unknown(args, ("ledger",))
        raw = _string(args, "ledger", "", maximum=300)
        if not raw:
            raise ProjectError(
                "ledger is required: point at an RSI step ledger, or make one with "
                "`python -m research_agent rsi propose ...`"
            )
        path = Path(raw).expanduser()
        if not path.is_file():
            raise ProjectError("no RSI ledger at %s" % path)
        try:
            story = ledger_story(StepLedger.load(path))
        except (OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        summary = dict(story.get("summary") or {})
        return tool_ok({
            "schema_version": "mcp-evolution-status-0.2",
            "ledger": str(path),
            # The reading has to arrive with the same provenance the CLI face gives it. Measured on
            # a real local BM25 trial: the CLI story carried generated_at, source_fingerprint, base,
            # read_only, provenance and summary.simulation_episodes, while this tool carried none of
            # them - so a host inside Qoder could not tell a simulated ledger from a real one, nor
            # which build produced the numbers. Provenance that survives one face and is dropped by
            # another is not provenance.
            "story_schema_version": story.get("schema_version"),
            "generated_at": story.get("generated_at"),
            "source_fingerprint": story.get("source_fingerprint"),
            "read_only": story.get("read_only"),
            "base": story.get("base"),
            "provenance": dict(story.get("provenance") or {}),
            "simulation_episodes": summary.get("simulation_episodes"),
            "warnings": list(story.get("warnings") or []),
            "headline": summary.get("headline"),
            "gate_verdict": summary.get("gate_verdict"),
            "episodes": summary.get("episodes"),
            "decided": summary.get("decided"),
            "approved": summary.get("approved"),
            "rejected": summary.get("rejected"),
            "rejection_rate": summary.get("rejection_rate"),
            "confirmed": summary.get("confirmed"),
            "regressed": summary.get("regressed"),
            "capability_claims": summary.get("capability_claims"),
            "gate_stops": summary.get("gate_stops"),
            "timeline": list(story.get("timeline") or []),
            "boundary": (
                "read-only projection of one ledger: gate_verdict and rejection_rate are readings of "
                "the gate and the task set, not of proposal quality, and gate_uninformative means "
                "nothing was rejected in this round; this tool cannot propose, admit, reject, revoke "
                "or activate anything - those stay CLI operations that require a human reason"
            ),
        })

    def lineage_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .closure_profiles import lineage_status

        _reject_unknown(args, ("project_dir", "experiment_id"))
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        try:
            result = lineage_status(
                project,
                experiment_id=_string(args, "experiment_id", required=True, maximum=80),
            )
        except (OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def support_panel(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .support_panel import SupportPanelError, audit_support_panel
        from .writing_pack import load_writing_pack

        _reject_unknown(
            args,
            (
                "project_dir",
                "run_id",
                "draft",
                "judge_profiles",
                "judge_families",
                "require_families",
                "judge_providers",
                "require_providers",
                "strict_support",
                "support_votes",
                "max_items",
                "refresh_support",
                "adjudication_file",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        run_id = _string(args, "run_id", required=True, maximum=120)
        draft = project_file(
            project, _string(args, "draft", required=True, maximum=500), "draft"
        )
        target = run_dir(project, run_id)
        if not target.is_dir():
            raise ProjectError("run does not exist: " + run_id)
        pack = load_writing_pack(project, run_id)
        if pack is None:
            raise ProjectError("writing pack missing; call research_writing_pack first")
        raw_profiles = args.get("judge_profiles")
        if not isinstance(raw_profiles, list) or not raw_profiles:
            raise ProjectError("judge_profiles must be a non-empty array")
        if not all(isinstance(value, str) and value.strip() for value in raw_profiles):
            raise ProjectError("judge_profiles must be unique non-empty strings")
        profiles = list(dict.fromkeys(value.strip() for value in raw_profiles))
        if len(profiles) != len(raw_profiles):
            raise ProjectError("judge_profiles must be unique non-empty strings")
        if len(profiles) > 4:
            raise ProjectError("at most 4 judge profiles are supported")
        raw_families = args.get("judge_families") or {}
        if not isinstance(raw_families, dict):
            raise ProjectError("judge_families must be an object of profile_id -> family")
        families = {
            str(key).strip(): str(value).strip().lower()
            for key, value in raw_families.items()
            if str(key).strip() and str(value).strip()
        }
        require_families = bool(args.get("require_families"))
        if require_families and any(profile not in families for profile in profiles):
            raise ProjectError("require_families needs a family for every judge profile")
        raw_providers = args.get("judge_providers") or {}
        if not isinstance(raw_providers, dict):
            raise ProjectError("judge_providers must be an object of profile_id -> provider")
        providers = {
            str(key).strip(): str(value).strip().lower()
            for key, value in raw_providers.items()
            if str(key).strip() and str(value).strip()
        }
        require_providers = bool(args.get("require_providers"))
        if require_providers and any(profile not in providers for profile in profiles):
            raise ProjectError("require_providers needs a provider for every judge profile")
        strict_support = bool(args.get("strict_support"))
        if strict_support and len(profiles) < 2:
            raise ProjectError("strict panel requires at least two judge profiles")
        judges = []
        for profile_id in profiles:
            judge, _note = self._gateway_support_judge(
                profile_id, strict=strict_support
            )
            judges.append((profile_id, judge))
        adjudication = None
        if str(args.get("adjudication_file") or "").strip():
            adjudication = project_file(
                project, str(args["adjudication_file"]).strip(), "adjudication"
            )
        try:
            result = audit_support_panel(
                draft,
                pack,
                judges,
                strict=strict_support,
                max_items=max(1, min(int(args.get("max_items") or 80), 200)),
                judge_votes=int(args.get("support_votes") or 1),
                cache_dir=target / "support-cache",
                refresh=bool(args.get("refresh_support")),
                adjudication_path=adjudication,
                judge_families=families,
                require_families=require_families,
                judge_providers=providers,
                require_providers=require_providers,
            )
        except (SupportPanelError, OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        from .storage import write_json_atomic

        panel_path = target / "support-panel.json"
        template_path = target / "support-adjudication-template.json"
        write_json_atomic(panel_path, result)
        write_json_atomic(template_path, result["adjudication_template"])
        return tool_ok(
            {
                **result,
                "files": {
                    "panel": str(panel_path),
                    "adjudication_template": str(template_path),
                },
            }
        )

    def _bound_writing_pack(self, project: Path, run_id: str, draft: Path) -> Dict[str, Any]:
        from .revision_io import read_draft
        from .writing_pack import PACK_MARKER_RE, load_writing_pack

        pack = load_writing_pack(project, run_id)
        if pack is None:
            raise ProjectError("writing pack missing; call research_writing_pack first")
        document = read_draft(draft)
        text = "\n".join(
            block.text
            for section in document.sections
            for block in section.blocks
            if block.text
        )
        marker = PACK_MARKER_RE.search(text)
        if (
            not marker
            or marker.group(1) != str(pack.get("pack_id") or "")
            or marker.group(2) != str(pack.get("pack_sha256") or "")
        ):
            raise ProjectError(
                "draft is not bound to the current writing pack; rebuild it from this pack"
            )
        return pack

    def support_items(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .support_audit import audit_pack_support

        _reject_unknown(args, ("project_dir", "run_id", "draft", "max_items"))
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        run_id = _string(args, "run_id", required=True, maximum=120)
        draft = project_file(
            project, _string(args, "draft", required=True, maximum=500), "draft"
        )
        pack = self._bound_writing_pack(project, run_id, draft)
        report = audit_pack_support(
            draft,
            pack,
            collect_only=True,
            max_items=_integer(args, "max_items", 80, 1, 200),
        )
        judgeable = [
            item["id"]
            for item in report.get("items") or []
            if item.get("evidence") and item.get("mode") != "proposal"
        ]
        return tool_ok(
            {
                "schema_version": "support-items-0.1",
                "draft": str(draft),
                "draft_sha256": report.get("draft_sha256"),
                "pack_id": pack.get("pack_id"),
                "pack_sha256": pack.get("pack_sha256"),
                "items": report.get("items") or [],
                "judgeable_ids": judgeable,
                "item_limit": report.get("item_limit"),
                "total_cited_sentences": report.get("total_cited_sentences"),
                "skipped_short_cited": report.get("skipped_short_cited", 0),
                "truncated": bool(report.get("truncated")),
                "boundary": (
                    "Read-only support items for an external judge; no model call and no verdicts. "
                    "Use one REF/span per sentence; a verdict is not a Claim or peer review."
                ),
            }
        )

    def support_verdicts(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .support_audit import STATUSES, audit_pack_support

        _reject_unknown(
            args,
            (
                "project_dir",
                "run_id",
                "draft",
                "judge_id",
                "strict",
                "verdicts",
                "max_items",
                "reuse",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        run_id = _string(args, "run_id", required=True, maximum=120)
        draft = project_file(
            project, _string(args, "draft", required=True, maximum=500), "draft"
        )
        judge_id = _string(args, "judge_id", required=True, maximum=120)
        reuse = bool(args.get("reuse", False))
        raw_verdicts = args.get("verdicts")
        if not isinstance(raw_verdicts, list) or (not raw_verdicts and not reuse):
            raise ProjectError("verdicts must be a non-empty array unless reuse=true")
        pack = self._bound_writing_pack(project, run_id, draft)
        max_items = _integer(args, "max_items", 80, 1, 200)
        collected = audit_pack_support(
            draft, pack, collect_only=True, max_items=max_items
        )
        by_item = {str(item.get("id") or ""): item for item in collected.get("items") or []}
        judgeable = {
            item_id
            for item_id, item in by_item.items()
            if item.get("evidence") and item.get("mode") != "proposal"
        }
        cleaned: Dict[str, Dict[str, Any]] = {}
        for value in raw_verdicts:
            if not isinstance(value, dict):
                raise ProjectError("each verdict must be an object")
            item_id = str(value.get("id") or "").strip()
            status = str(value.get("status") or "").strip().lower()
            rationale = str(value.get("rationale") or "").strip()
            item = by_item.get(item_id)
            if item is None:
                raise ProjectError("unknown support item: " + item_id)
            if status not in STATUSES:
                raise ProjectError("invalid verdict status for %s: %s" % (item_id, status))
            if not rationale:
                raise ProjectError("verdict needs a rationale: " + item_id)
            allowed_refs = {
                str(entry.get("ref"))
                for entry in item.get("evidence") or []
                if entry.get("ref")
            }
            evidence_refs = value.get("evidence_refs") or []
            if not isinstance(evidence_refs, list) or any(
                str(ref) not in allowed_refs for ref in evidence_refs
            ):
                raise ProjectError("verdict evidence_refs must come from item evidence: " + item_id)
            if item_id in cleaned:
                raise ProjectError("duplicate verdict: " + item_id)
            cleaned[item_id] = {
                "id": item_id,
                "status": status,
                "rationale": rationale[:600],
                "evidence_refs": [str(ref) for ref in evidence_refs],
            }
        target = run_dir(project, run_id)
        reused: Dict[str, Dict[str, Any]] = {}
        reuse_source: Optional[str] = None
        if reuse:
            ledger_path = target / "support-ledger.json"
            if ledger_path.is_file():
                try:
                    prior = json.loads(ledger_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    prior = {}
                if prior.get("judge_model") == "qoder:" + judge_id:
                    previous = {
                        _support_reuse_key(entry): entry
                        for entry in prior.get("items") or []
                        if entry.get("status") in STATUSES
                    }
                    for item_id in sorted(judgeable - set(cleaned)):
                        item = by_item[item_id]
                        prior_item = previous.get(_support_reuse_key(item))
                        if not prior_item:
                            continue
                        allowed_refs = {
                            str(value.get("ref"))
                            for value in item.get("evidence") or []
                            if value.get("ref")
                        }
                        reused[item_id] = {
                            "id": item_id,
                            "status": str(prior_item.get("status")),
                            "rationale": str(
                                prior_item.get("rationale") or "reused previous verdict"
                            ),
                            "evidence_refs": [
                                str(ref)
                                for ref in prior_item.get("evidence_refs") or []
                                if str(ref) in allowed_refs
                            ],
                        }
                    if reused:
                        reuse_source = "support-ledger.json"

        combined = dict(reused)
        combined.update(cleaned)
        missing = sorted(judgeable - set(combined))
        if bool(args.get("strict", True)) and missing:
            raise ProjectError(
                "missing verdicts for judgeable items: " + ", ".join(missing[:20])
            )

        def judge(payload: Dict[str, Any]):
            return [
                combined[item["id"]]
                for item in payload.get("items") or []
                if item.get("id") in combined
            ]

        report = audit_pack_support(
            draft,
            pack,
            judge=judge,
            strict=False,
            judge_model_id="qoder:" + judge_id,
            max_items=max_items,
        )
        report["method"] = "qoder_agent_judge"
        report["verdict_source"] = "qoder"
        report["judge_model"] = "qoder:" + judge_id
        report["provided_count"] = len(cleaned)
        report["reused_count"] = len(reused)
        report["reuse_source"] = reuse_source
        reused_ids = set(reused)
        for entry in report.get("items") or []:
            if entry.get("id") in reused_ids:
                entry["reused"] = True
        target.mkdir(parents=True, exist_ok=True)
        archived_ledger = ""
        ledger_path = target / "support-ledger.json"
        if ledger_path.is_file():
            try:
                previous_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                previous_ledger = {}
            previous_sha = str(previous_ledger.get("draft_sha256") or "")
            current_sha = str(report.get("draft_sha256") or "")
            if previous_sha and previous_sha != current_sha:
                history = target / "support-ledger-history"
                history.mkdir(parents=True, exist_ok=True)
                archive = history / ("support-ledger-%s.json" % previous_sha[:16])
                write_json_atomic(archive, previous_ledger)
                archived_ledger = archive.relative_to(target).as_posix()
                report["archived_ledger"] = archived_ledger
        write_json_atomic(ledger_path, report)
        return tool_ok(
            {
                "schema_version": "support-ledger-0.1",
                "draft": str(draft),
                "draft_sha256": report.get("draft_sha256"),
                "judge_model": report.get("judge_model"),
                "status": report.get("status"),
                "counts": report.get("counts"),
                "provided_count": report.get("provided_count"),
                "reused_count": report.get("reused_count"),
                "reuse_source": report.get("reuse_source"),
                "archived_ledger": archived_ledger,
                "unresolved_refs": report.get("unresolved_refs"),
                "items": report.get("items"),
                "section_summary": report.get("section_summary"),
                "boundary": (
                    "Qoder-authored support verdicts recorded from the current pack; "
                    "unchanged sentence+evidence pairs may reuse a prior verdict from the "
                    "same judge id. A prior ledger for a different draft hash is archived "
                    "under support-ledger-history/ before overwrite. Not an external "
                    "validation, not a Claim or peer review, no signature."
                ),
            }
        )

    def manuscript_section_edit(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .manuscript_edit import ManuscriptEditError, replace_section

        _reject_unknown(
            args,
            (
                "project_dir",
                "run_id",
                "draft",
                "section",
                "replacement",
                "output",
                "expected_section_sha256",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        run_id = _string(args, "run_id", required=True, maximum=120)
        draft = project_file(
            project, _string(args, "draft", required=True, maximum=500), "draft"
        )
        output = project_output_path(
            project, _string(args, "output", required=True, maximum=500), "output"
        )
        if output.resolve() == draft.resolve():
            raise ProjectError("output must be a new draft, not the source draft")
        self._bound_writing_pack(project, run_id, draft)
        try:
            result = replace_section(
                draft.read_text(encoding="utf-8"),
                _string(args, "section", required=True, maximum=200),
                _string(args, "replacement", required=True, maximum=20000),
                expected_section_sha256=_string(
                    args, "expected_section_sha256", "", maximum=64
                ),
            )
        except (ManuscriptEditError, OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(str(output), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(result["text"])
        return tool_ok(
            {
                **result,
                "source_draft": str(draft),
                "new_draft": str(output),
            }
        )

    def manuscript_bind(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .writing_pack import bind_text_to_pack, load_writing_pack

        _reject_unknown(args, ("project_dir", "run_id", "draft", "output"))
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        run_id = _string(args, "run_id", required=True, maximum=120)
        draft = project_file(
            project, _string(args, "draft", required=True, maximum=500), "draft"
        )
        output = project_output_path(
            project, _string(args, "output", required=True, maximum=500), "output"
        )
        if output.resolve() == draft.resolve():
            raise ProjectError("output must be a new draft, not the source draft")
        pack = load_writing_pack(project, run_id)
        if not pack:
            raise ProjectError("writing pack missing; run research_writing_pack first")
        try:
            result = bind_text_to_pack(draft.read_text(encoding="utf-8"), pack)
        except (OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(str(output), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(result["text"])
        return tool_ok(
            {
                "pack_id": str(pack.get("pack_id") or ""),
                "pack_sha256": str(pack.get("pack_sha256") or ""),
                "marker": result["marker"],
                "source_draft": str(draft),
                "new_draft": str(output),
                "refs": result["refs"],
                "resolved_refs": result["resolved_refs"],
                "unresolved_refs": result["unresolved_refs"],
                "boundary": (
                    "Binding only attaches the writing-pack marker and preserves the body. "
                    "It creates no evidence and no signature; unresolved refs will fail "
                    "the support audit."
                ),
            }
        )

    def manuscript_ab_review(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .ab_review import ABReviewError, render_ab_markdown, run_ab_review
        from .revision import _gateway_model

        _reject_unknown(
            args, ("project_dir", "original", "revised", "sections", "rounds", "profile_id")
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        original = project_file(
            project, _string(args, "original", required=True, maximum=500), "original"
        )
        revised = project_file(
            project, _string(args, "revised", required=True, maximum=500), "revised"
        )
        profile_id = _string(args, "profile_id", required=True, maximum=80)
        raw_sections = args.get("sections") or []
        if not isinstance(raw_sections, list):
            raise ProjectError("sections must be an array")
        try:
            model = _gateway_model(
                profile_id, os.environ.get("RESEARCH_AGENT_MODEL_STORE") or None
            )
            result = run_ab_review(
                original,
                revised,
                model,
                sections=[str(item) for item in raw_sections],
                rounds=_integer(args, "rounds", 1, 1, 3),
            )
        except (ABReviewError, OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        output = project / "revisions" / ("AB-" + uuid.uuid4().hex[:8])
        output.mkdir(parents=True, exist_ok=True)
        write_json_atomic(output / "ab-review.json", result)
        (output / "ab-review.md").write_text(render_ab_markdown(result), encoding="utf-8")
        result["files"] = {
            "json": str(output / "ab-review.json"),
            "markdown": str(output / "ab-review.md"),
        }
        return tool_ok(result)

    def manuscript_review(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .manuscript_review import (
            ManuscriptReviewError,
            default_review_model,
            run_manuscript_review,
        )

        _reject_unknown(
            args,
            (
                "project_dir",
                "run_id",
                "draft",
                "rounds",
                "threshold",
                "semantic_support",
                "strict_support",
                "support_votes",
                "revision_mode",
                "ab_check",
                "ab_sections",
                "judge_profile",
            ),
        )
        project = self._open_project(
            _string(args, "project_dir", "research-project", maximum=300)
        )
        run_id = _string(args, "run_id", required=True, maximum=120)
        target = run_dir(project, run_id)
        if not target.is_dir():
            raise ProjectError("run does not exist: " + run_id)
        draft = project_file(
            project, _string(args, "draft", required=True, maximum=500), "draft"
        )
        try:
            review_model = default_review_model()
            strict_support = bool(args.get("strict_support"))
            support_judge = None
            judge_profile = str(args.get("judge_profile") or "").strip()
            if bool(args.get("semantic_support")) or strict_support or judge_profile:
                if judge_profile:
                    support_judge, _note = self._gateway_support_judge(
                        judge_profile, strict=strict_support
                    )
                else:
                    from .adapters.support_judge import support_judge_from_model

                    support_judge = support_judge_from_model(
                        review_model, strict=strict_support
                    )
            result = run_manuscript_review(
                project,
                run_id,
                draft,
                rounds=_integer(args, "rounds", 3, 1, 5),
                threshold=float(args.get("threshold", 8.0)),
                model=review_model,
                support_judge=support_judge,
                strict_support=strict_support,
                judge_model_id=(
                    "profile:" + judge_profile
                    if judge_profile
                    else getattr(
                        review_model, "model_id", type(review_model).__name__
                    )
                ),
                support_votes=_integer(args, "support_votes", 1, 1, 5),
                revision_mode=_choice(
                    args, "revision_mode", ("full", "section", "support", "auto"), "full"
                ),
                ab_reviewer=review_model if bool(args.get("ab_check")) else None,
                ab_sections=[
                    str(item) for item in (args.get("ab_sections") or [])
                ],
            )
        except (ManuscriptReviewError, OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        _reject_unknown(args, ("project_dir", "limit"))
        project = self._open_project(_string(args, "project_dir", "research-project"))
        limit = _integer(args, "limit", 20, 1, 100)
        result = project_status(project, limit=limit)
        runs = result.get("runs") or []
        seen = {str(row.get("run_id") or "") for row in runs}
        if len(runs) < limit:
            for path in sorted((project / "runs").glob("RUN-*"), reverse=True):
                if len(runs) >= limit:
                    break
                if not path.is_dir() or path.name in seen:
                    continue
                task = _read_json(path / "task.json")
                task = task if isinstance(task, dict) else {}
                runs.append(
                    {
                        "run_id": path.name,
                        "status": task.get("status", "unknown"),
                        "route": (task.get("plan") or {}).get("route", ""),
                        "stopped_at": task.get("stopped_at", ""),
                        "failure": task.get("failure", {}),
                        "goal": "",
                        "created_at": "",
                        "path": str(path),
                    }
                )
                seen.add(path.name)
        result["runs"] = runs

        def display(value: str) -> str:
            if not value:
                return ""
            path = Path(value)
            return _relative(project, path) if path.is_absolute() else value

        for row in result.get("runs") or []:
            target = Path(str(row.get("path") or ""))
            if not target.is_dir():
                continue
            ledger = _read_json(target / "support-ledger.json")
            audit = _read_json(target / "writing-audit.json")
            gold = _read_json(target / "support-gold.json")
            template = _read_json(target / "support-gold-template.json")
            ledger_status = (
                str(ledger.get("status") or "") if isinstance(ledger, dict) else ""
            )
            audit_status = (
                str(audit.get("status") or "") if isinstance(audit, dict) else ""
            )
            if isinstance(ledger, dict):
                summary = (
                    ledger.get("section_summary")
                    if isinstance(ledger.get("section_summary"), dict)
                    else {}
                )
                row["support"] = {
                    "status": ledger_status,
                    "counts": ledger.get("counts"),
                    "judge_model": str(ledger.get("judge_model") or ""),
                    "draft": display(str(ledger.get("draft") or "")),
                    "weak_sections": [
                        entry
                        for entry in summary.get("weak_sections") or []
                        if isinstance(entry, dict)
                    ][:5],
                }
            if isinstance(audit, dict):
                row["manuscript"] = {
                    "status": audit_status,
                    "submission_ready": bool(audit.get("submission_ready")),
                    "draft": display(str(audit.get("draft") or "")),
                }
            loop_capsule = _loop_capsule_summary(target)
            if loop_capsule:
                row["loop_capsule"] = loop_capsule
            if isinstance(gold, dict) or isinstance(template, dict):
                row["support_gold"] = {
                    "evaluated": isinstance(gold, dict),
                    "templates": isinstance(template, dict),
                    "draft_sha256": str(
                        (gold if isinstance(gold, dict) else template or {}).get(
                            "draft_sha256"
                        )
                        or ""
                    )[:16],
                }
            experiment_rows = _experiment_rows(project, str(row.get("run_id") or ""))
            if experiment_rows:
                row["experiments"] = experiment_rows
            idea_summary = _idea_summary(_read_json(target / "idea.json"))
            if idea_summary:
                row["idea"] = idea_summary
            if not (target / "task.json").is_file() and (
                ledger_status or audit_status
            ):
                row["qoder_native"] = True
                row["status"] = "manuscript:" + (
                    ledger_status or audit_status or "unknown"
                )
        try:
            from .project import list_project_experiments

            result["experiment_inventory"] = list_project_experiments(
                project, limit=limit
            )
        except (OSError, ValueError) as exc:
            result["experiment_inventory"] = {
                "count": 0,
                "experiments": [],
                "error": type(exc).__name__,
            }
        return tool_ok(result)

    def model_profiles(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .model_catalog import profile_catalog

        _reject_unknown(args, ())
        store_path = Path(
            os.environ.get("RESEARCH_AGENT_MODEL_STORE") or str(DEFAULT_MODEL_STORE_PATH)
        )
        try:
            result = profile_catalog(store_path)
        except (OSError, ValueError) as exc:
            raise ProjectError(str(exc))
        return tool_ok(result)

    def model_turns(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .host_model import ModelTurnLedger, host_turn_requests

        _reject_unknown(
            args, ("status", "module", "limit", "include_request")
        )
        ledger = ModelTurnLedger(_host_model_ledger_path())
        limit = int(args.get("limit") or 10)
        include_request = bool(args.get("include_request", True))
        return tool_ok(
            host_turn_requests(
                ledger,
                status=str(args.get("status") or "") or None,
                module=str(args.get("module") or "") or None,
                limit=limit,
                include_request=include_request,
            )
        )

    def model_respond(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .host_model import ModelTurnLedger

        _reject_unknown(args, ("turn_id", "text", "host_label", "project_dir"))
        ledger = ModelTurnLedger(_host_model_ledger_path())
        turn_id = _string(args, "turn_id", required=True, maximum=60)
        text = str(args.get("text") or "")
        if len(text) > 200_000:
            raise ProjectError("text exceeds 200000 chars")
        project_root = None
        if args.get("project_dir"):
            project_root = self._open_project(_string(args, "project_dir"))
        try:
            outcome = ledger.respond(
                turn_id,
                text,
                host_label=str(args.get("host_label") or ""),
                project_root=project_root,
            )
        except ValueError as exc:
            raise ProjectError(str(exc))
        if not outcome.get("accepted"):
            return tool_ok(
                {
                    "accepted": False,
                    "turn_id": turn_id,
                    "errors": outcome.get("errors", []),
                    "note": "the turn stays pending; correct the output and respond again",
                }
            )
        return tool_ok({"accepted": True, "receipt": outcome.get("receipt", {})})

    def model_void(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from .host_model import ModelTurnLedger

        _reject_unknown(args, ("turn_id", "reason"))
        ledger = ModelTurnLedger(_host_model_ledger_path())
        turn_id = _string(args, "turn_id", required=True, maximum=60)
        reason = _string(args, "reason", required=True, maximum=400)
        try:
            turn = ledger.void(turn_id, reason)
        except ValueError as exc:
            raise ProjectError(str(exc))
        return tool_ok(
            {
                "voided": True,
                "turn_id": turn_id,
                "status": turn.get("status"),
                "previous_text_sha256": (turn.get("voided") or {}).get("previous_text_sha256", ""),
                "note": (
                    "the stage will raise a fresh turn next time it asks the same thing; "
                    "voiding only reopens the request, it never admits a capability"
                ),
            }
        )

    def artifacts(self, args: Dict[str, Any]) -> Dict[str, Any]:
        _reject_unknown(args, ("project_dir", "run_id"))
        project = self._open_project(_string(args, "project_dir", "research-project"))
        return tool_ok(list_artifacts(project, _string(args, "run_id", required=True, maximum=120)))

    def read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        _reject_unknown(args, ("project_dir", "run_id", "path", "max_chars"))
        project = self._open_project(_string(args, "project_dir", "research-project"))
        return tool_ok(
            read_artifact(
                project,
                _string(args, "run_id", required=True, maximum=120),
                _string(args, "path", required=True, maximum=500),
                _integer(args, "max_chars", 120_000, 1_000, 400_000),
            )
        )

    def next_actions(self, args: Dict[str, Any]) -> Dict[str, Any]:
        _reject_unknown(args, ("project_dir", "run_id"))
        project = self._open_project(_string(args, "project_dir", "research-project"))
        run_id = _string(args, "run_id", required=True, maximum=120)
        return tool_ok(
            {
                "run_id": run_id,
                "next_actions": _next_actions(project, run_id),
                "loop_capsule": _loop_capsule_summary(run_dir(project, run_id)),
                "boundary": HUMAN_ONLY,
            }
        )


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _models_required() -> bool:
    return (os.environ.get("RESEARCH_AGENT_MODE") or "test").strip().lower() == "production"


def _build_task_agent():
    from .adapters.glm_model import gateway_query_planner
    from .adapters.paper_writer import gateway_paper_writer
    from .adapters.research_models import (
        gateway_experiment_designer,
        gateway_idea_proposer,
    )
    from .adapters.support_judge import gateway_support_judge
    from .models import GatewayStore, ModelGateway
    from .task_agent import TaskAgent

    strict = _models_required()
    store_path = Path(
        os.environ.get("RESEARCH_AGENT_MODEL_STORE") or str(DEFAULT_MODEL_STORE_PATH)
    )
    gateway = ModelGateway(GatewayStore(store_path))
    planner, planner_note = gateway_query_planner(gateway=gateway, strict=strict)
    writer, writer_note = gateway_paper_writer(gateway=gateway, strict=strict)
    idea, idea_note = gateway_idea_proposer(gateway=gateway, strict=strict)
    experiment, experiment_note = gateway_experiment_designer(gateway=gateway, strict=strict)
    judge, judge_note = gateway_support_judge(gateway=gateway, strict=strict)
    notes = [
        note
        for note in (
            planner_note,
            writer_note,
            idea_note,
            experiment_note,
            judge_note,
        )
        if note
    ]
    agent = TaskAgent(
        query_planner=planner,
        section_writer=writer,
        idea_proposer=idea,
        experiment_designer=experiment,
        support_judge=judge,
        strict_models=strict,
        strict_routing=strict,
    )
    return agent, notes


def _optional_project_file(project: Path, value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return str(project_file(project, text, label))


def _require_local_inputs(corpus_dir: Path) -> None:
    from .adapters.local_document_retriever import SUPPORTED_SUFFIXES

    if not corpus_dir.is_dir():
        raise ProjectError("local source requires a corpus directory: %s" % corpus_dir)
    files = [
        path
        for path in corpus_dir.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
        and not path.name.startswith(".")
    ]
    if not files:
        raise ProjectError(
            "source=local requires at least one PDF/TXT/MD under %s" % corpus_dir
        )


def _package_counts(packages: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in packages:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _support_ledger_action(
    project: Path, target: Path, ledger: Any
) -> Optional[Dict[str, Any]]:
    if not isinstance(ledger, dict):
        return None
    ledger_status = str(ledger.get("status") or "")
    summary = (
        ledger.get("section_summary")
        if isinstance(ledger.get("section_summary"), dict)
        else {}
    )
    weak_sections = [
        entry for entry in summary.get("weak_sections") or [] if isinstance(entry, dict)
    ]
    if not (ledger_status in ("partial", "blocked", "needs_human") or weak_sections):
        return None
    counts = ledger.get("counts") if isinstance(ledger.get("counts"), dict) else {}
    draft = str(ledger.get("draft") or "")
    return {
        "kind": "support_review",
        "message": (
            "Support ledger is %s (supported=%s, partial=%s, insufficient=%s); "
            "rewrite the weakest sections first, then call "
            "research_support_verdicts with reuse=true for unchanged "
            "sentence+evidence pairs and re-run research_manuscript_audit. "
            "Qoder verdicts are self-review, not human gold."
        )
        % (
            ledger_status or "unknown",
            counts.get("supported", 0),
            counts.get("partial", 0),
            counts.get("insufficient", 0),
        ),
        "draft": _relative(project, Path(draft)) if draft else "",
        "weak_sections": weak_sections[:10],
        "next_tools": [
            "research_support_items",
            "research_support_verdicts",
            "research_manuscript_audit",
        ],
    }


def _human_gold_action(
    project: Path, target: Path, ledger: Any, run_id: str
) -> Optional[Dict[str, Any]]:
    if not isinstance(ledger, dict) or str(ledger.get("status") or "") != "ready":
        return None
    draft_sha = str(ledger.get("draft_sha256") or "")
    if not draft_sha:
        return None
    gold = _read_json(target / "support-gold.json")
    if isinstance(gold, dict) and str(gold.get("draft_sha256") or "") == draft_sha:
        panel = gold.get("panel") if isinstance(gold.get("panel"), dict) else {}
        return {
            "kind": "human_gold_ready",
            "message": (
                "Human gold is present; review panel/gold disagreements and proceed "
                "to human review. It is a reference label, not peer review or a signature."
            ),
            "artifact": "support-gold.json",
            "accuracy": panel.get("accuracy"),
            "disagreements": panel.get("disagreements") or [],
        }
    template = _read_json(target / "support-gold-template.json")
    template_ready = (
        isinstance(template, dict)
        and str(template.get("draft_sha256") or "") == draft_sha
    )
    base = "runs/%s" % run_id
    if template_ready:
        message = (
            "Support ledger is ready; blank human-gold templates exist. Two independent "
            "annotators must fill their own A/B files, then run support-gold with --ledger. "
            "Qoder must not fill gold or treat its verdicts as human gold."
        )
        cli = (
            'python -m research_agent writing support-gold --project "%s" --run-id "%s" '
            '--annotator-file "%s/support-gold-annotations-A.json" '
            '--annotator-file "%s/support-gold-annotations-B.json" '
            '--ledger "%s/support-ledger.json"'
            % (project, run_id, base, base, base)
        )
        artifact = "support-gold-template.json"
    else:
        message = (
            "Support ledger is ready; human gold is missing. Generate blank A/B templates "
            "and have two independent annotators fill them; Qoder must not fill gold or "
            "treat its verdicts as human gold."
        )
        cli = (
            'python -m research_agent writing support-gold-template --project "%s" '
            '--run-id "%s" --ledger "%s/support-ledger.json"'
            % (project, run_id, base)
        )
        artifact = "support-ledger.json"
    return {
        "kind": "human_gold",
        "message": message,
        "cli": cli,
        "artifact": artifact,
    }


def _idea_summary(idea: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(idea, dict):
        return None
    candidates = [
        {
            "idea_id": card.get("idea_id"),
            "title": str(card.get("title") or "")[:160],
            "prior_art_scope": card.get("prior_art_scope"),
            "novelty_status": card.get("novelty_status"),
            "evidence_count": card.get("evidence_count"),
            "source_count": card.get("source_count"),
            "has_kill_criteria": bool(card.get("kill_criteria")),
            "has_contrast": bool(card.get("contrast_refs")),
        }
        for card in (idea.get("candidates") or [])[:5]
        if isinstance(card, dict)
    ]
    shortlist = (
        idea.get("shortlist") if isinstance(idea.get("shortlist"), dict) else {}
    )
    return {
        "run_id": idea.get("run_id"),
        "status": idea.get("status"),
        "candidate_count": len(idea.get("candidates") or []),
        "candidates": candidates,
        "shortlist_selection": shortlist.get("selection"),
        "shortlist_ranked": [
            {
                "rank": item.get("rank"),
                "idea_id": item.get("idea_id"),
                "prior_art_scope": item.get("prior_art_scope"),
                "has_contrast": item.get("has_contrast"),
            }
            for item in (shortlist.get("ranked") or [])[:3]
            if isinstance(item, dict)
        ],
        "boundary": shortlist.get("boundary")
        or "candidate frames only; human G1",
    }


def _experiment_rows(project: Path, run_id: str) -> List[Dict[str, Any]]:
    experiments = project / "experiments"
    if not experiments.is_dir():
        return []
    from .experiment_runner import experiment_status

    rows: List[Dict[str, Any]] = []
    for package in sorted(experiments.glob("EXP-*"), reverse=True):
        spec_path = package / "experiment-spec.json"
        if not spec_path.is_file():
            spec_path = package / "spec.json"
        if not spec_path.is_file():
            continue
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(spec, dict) or str(spec.get("run_id") or "") != run_id:
            continue
        try:
            status = experiment_status(project, package.name)
        except Exception:
            continue
        rows.append(
            {
                "experiment_id": package.name,
                "package": str(package),
                "stages": (
                    status.get("stages")
                    if isinstance(status.get("stages"), dict)
                    else {}
                ),
                "next_action": str(status.get("next_action") or ""),
            }
        )
    return rows


def _experiment_approval_action(
    project: Path, run_id: str
) -> Optional[Dict[str, Any]]:
    for row in _experiment_rows(project, run_id):
        stages = row.get("stages") or {}
        if stages.get("approval") != "missing":
            continue
        return {
            "kind": "experiment_approval",
            "message": (
                "Experiment package is generated and waiting for human approval; "
                "MCP does not approve or execute."
            ),
            "experiment_id": row["experiment_id"],
            "package": row["package"],
            "cli": (
                'python -m research_agent experiment approve --project "%s" '
                '--experiment-id "%s" --human-reason "<reason>"'
                % (project, row["experiment_id"])
            ),
            "next_tools": ["research_experiment_status"],
        }
    return None


def _loop_capsule_summary(target: Path) -> Dict[str, Any]:
    capsule = _read_json(target / "loop-capsule.json")
    if not isinstance(capsule, dict):
        return {}
    # The capsule is a run-time snapshot: a delegated signature can land after it was
    # written, so the snapshot may still say CLOSURE_UNSIGNED over an already-signed
    # closure.  Re-derive that one verdict from the single-point producer (verdict
    # ledger) and override the stale blocker — a host following blockers must never
    # be pointed at re-signing a signed closure.
    override = None
    blockers = [str(item) for item in (capsule.get("blockers") or [])]
    actions = [item for item in (capsule.get("next_actions") or []) if isinstance(item, dict)]
    if "CLOSURE_UNSIGNED" in blockers:
        try:
            from .loop_capsule import project_root_for_run
            from .verdict_ledger import collect

            project_root = project_root_for_run(target)
            ledger = collect(project_root, limit=50) if project_root is not None else None
        except (OSError, ValueError):
            ledger = None
        row = next(
            (
                item
                for item in (ledger or {}).get("rows") or []
                if item.get("kind") == "closure" and item.get("subject") == "runs/" + target.name
            ),
            None,
        )
        if row and row.get("status") == "signed":
            override = {
                "snapshot": "CLOSURE_UNSIGNED",
                "recomputed": "signed",
                "source": "verdict-ledger",
                "source_path": row.get("source_path") or "",
                "source_sha256": row.get("source_sha256") or "",
            }
            blockers = [item for item in blockers if item != "CLOSURE_UNSIGNED"]
            actions = [
                item
                for item in actions
                if "closure sign" not in str(item.get("command") or "")
            ]
    nodes = [
        item for item in (capsule.get("nodes") or [])
        if isinstance(item, dict)
    ]
    return {
        "path": "loop-capsule.json",
        "run_id": str(capsule.get("run_id") or ""),
        "status": "blocked" if blockers else "ready_for_human_review",
        "nodes": {
            str(item.get("id")): str(item.get("status") or "")
            for item in nodes
        },
        "blockers": blockers,
        "verdict_override": override,
        "next_actions": actions[:8],
        "boundary": str(capsule.get("boundary") or ""),
    }


def _next_actions(project: Path, run_id: str) -> List[Dict[str, Any]]:
    target = run_dir(project, run_id)
    task = _read_task(target)
    ledger = _read_json(target / "support-ledger.json")
    support_action = _support_ledger_action(project, target, ledger)
    gold_action = _human_gold_action(project, target, ledger, run_id)
    experiment_action = _experiment_approval_action(project, run_id)
    from .loop_ledger import pending_study_actions

    # An idea bound to an executable search profile is the next concrete step, and the server
    # points at the CLI rather than running experiments itself. Task-less (Qoder-native) runs get
    # it too: there is no task record, but the reviewed ideas are still on disk.
    study_actions = pending_study_actions(
        project, run_id, _read_json(target / "innovation-review.json") or {}
    )
    if not task:
        actions = [
            action
            for action in (support_action, gold_action, experiment_action)
            if action
        ]
        if actions or study_actions:
            return actions + study_actions
        # A task-less run can still carry a capsule: pointing the human at the directory
        # would be weaker advice than the artifacts already support.
        capsule_actions = [
            action
            for action in (_loop_capsule_summary(target) or {}).get("next_actions") or []
            if isinstance(action, dict) and action.get("command")
        ]
        if capsule_actions:
            return capsule_actions
        return [
            {
                "kind": "inspect",
                "message": "task.json is missing; read startup-error.json or the run directory.",
                "run_dir": str(target),
            }
        ]
    status = str(task.get("status", ""))
    stopped_at = str(task.get("stopped_at", ""))
    artifacts = sorted(task.get("artifacts", {}).keys()) if isinstance(task.get("artifacts"), dict) else []
    actions: List[Dict[str, Any]] = []
    if status == "failed":
        failure = task.get("failure") or {}
        actions.append(
            {
                "kind": "failure",
                "message": str(failure.get("suggested_action") or "Read failure.json and fix the reported input."),
                "retryable": bool(failure.get("retryable")),
                "artifact": "failure.json" if "failure.json" in artifacts else "",
            }
        )
        return actions
    handoff = _read_json(target / "awaiting-host-model.json")
    if isinstance(handoff, dict) and handoff.get("turn_id"):
        actions.append(
            {
                "kind": "host_model",
                "message": str(
                    handoff.get("resume")
                    or "answer the pending host model turn, then re-run this task"
                ),
                "turn_id": str(handoff.get("turn_id")),
                "tool": "research_model_respond",
                "read_tool": "research_model_turns",
                "artifact": "awaiting-host-model.json",
            }
        )
        return actions
    if stopped_at == "Q0":
        actions.append(
            {
                "kind": "evidence",
                "message": "Q0 blocked: add full-text PDF/TXT/MD to inputs/ and rerun with source=local; abstract-only sources cannot create spans.",
            }
        )
        return actions
    panel = _read_json(target / "support-panel.json")
    if isinstance(panel, dict) and str(panel.get("status") or "") in (
        "blocked",
        "needs_human",
    ):
        profiles = [
            str(item.get("id") or "profile")
            for item in (panel.get("judges") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ][:4]
        profile_args = " ".join(
            '--judge-profile "%s"' % profile for profile in profiles
        )
        strict_args = " --strict-support" if len(profiles) >= 2 else ""
        draft = str(panel.get("draft") or "")
        template = target / "support-adjudication-template.json"
        cli = ""
        if draft and profiles:
            cli = (
                'python -m research_agent writing support-panel --project "%s" '
                '--run-id "%s" --draft "%s" %s%s --adjudication "%s"'
                % (project, run_id, draft, profile_args, strict_args, template)
            )
        actions.insert(
            0,
            {
                "kind": "human_adjudication",
                "message": (
                    "Support panel has unresolved disagreements; fill status and "
                    "human_reason in the adjudication template, then rerun the panel. "
                    "Closure and the writing audit remain blocked."
                ),
                "cli": cli,
                "artifact": "support-adjudication-template.json",
            },
        )
    if support_action:
        actions.append(support_action)
    if gold_action:
        actions.append(gold_action)
    if experiment_action:
        actions.append(experiment_action)
    actions.extend(study_actions)
    if stopped_at == "G1":
        idea = target / "idea.json"
        action = {
            "kind": "human_gate",
            "gate": "G1",
            "message": "Select one candidate and write a human-approved G1 decision, then resume with g1_decision_file.",
            "cli": (
                'python -m research_agent flow g1 --idea-file "%s" --idea-id <IDEA-ID> '
                '--human-reason "<reason>" --output-dir "%s"' % (idea, target)
            ),
            "resume": {
                "g1_decision_file": _relative(
                    project, target / "g1-decision.json"
                )
            },
        }
        idea_summary = _idea_summary(_read_json(idea))
        if idea_summary:
            action["idea"] = idea_summary
            action["idea_ids"] = [
                item.get("idea_id")
                for item in idea_summary.get("candidates") or []
                if item.get("idea_id")
            ]
        actions.append(action)
    if stopped_at == "G2":
        design = target / "experiment.json"
        actions.append(
            {
                "kind": "human_gate",
                "gate": "G2",
                "message": "Check baseline/metric/seeds and freeze the ProtocolCard before S5; this server cannot freeze it.",
                "cli": (
                    'python -m research_agent protocol freeze-design --design "%s" '
                    '--limitation "<scope>" --human-reason "<reason>" --output-dir "%s"'
                    % (design, target / "protocol")
                ),
                "resume": {
                    "protocol_file": _relative(
                        project, target / "protocol" / "protocol-card.json"
                    )
                },
            }
        )
    gates = task.get("gates") or []
    gate_map = {
        str(item.get("gate")): item for item in gates if isinstance(item, dict)
    }
    if status == "needs_human" and "S5" in gate_map and "claim/claim.json" not in artifacts:
        dataset = "iris"
        run_context = _read_json(target / "run-context.json")
        request = run_context.get("request") if isinstance(run_context.get("request"), dict) else {}
        dataset = str(request.get("run_dataset") or dataset)
        actions.append(
            {
                "kind": "human_gate",
                "gate": "S5b",
                "message": "Inspect RunCapsule/EA and sign the claim in the CLI; then resume with claim_file.",
                "cli": (
                    'python -m research_agent run claim --capsule "%s" --ea "%s" '
                    '--statement "<claim statement>" --human-reason "<reason>" '
                    '--scope S5/demo/%s --output-dir "%s"'
                    % (
                        target / "run" / "run-capsule.json",
                        target / "run" / "ea.json",
                        dataset,
                        target / "claim",
                    )
                ),
                "resume": {"claim_file": _relative(project, target / "claim" / "claim.json")},
            }
        )
    closure_report = target / "closure" / "closure-report.json"
    if closure_report.is_file() and "closure-signature/signature.json" not in artifacts:
        actions.append(
            {
                "kind": "human_gate",
                "gate": "G5",
                "message": "Closure is ready; sign the export in the CLI. Add --signer <id> when using a local HMAC signer. This server cannot sign.",
                "cli": (
                    'python -m research_agent closure sign --report "%s" --demo "%s" '
                    '--claim "%s" --human-reason "<reason>" --output-dir "%s"'
                    % (
                        closure_report,
                        target / "demo.json",
                        target / "claim" / "claim.json",
                        target / "closure-signature",
                    )
                ),
            }
        )
    if not actions:
        if status in ("completed", "needs_human"):
            actions.append(
                {
                    "kind": "read",
                    "message": "Read task-report.md and task.json, then verify the evidence boundary before using any conclusion.",
                    "artifacts": ["task-report.md", "task.json"],
                }
            )
        else:
            actions.append(
                {
                    "kind": "inspect",
                    "message": "Inspect task-report.md and task.json for the current blocker.",
                }
            )
    if (target / "literature-ledger.json").is_file() and (target / "writing-pack.json").is_file():
        actions.append(
            {
                "kind": "audit",
                "message": "A writing pack exists. After writing a project-local draft, call research_manuscript_audit before treating it as ready for human review.",
                "tool": "research_manuscript_audit",
                "run_id": target.name,
            }
        )
    elif status == "completed" and (target / "literature-ledger.json").is_file():
        actions.append(
            {
                "kind": "write",
                "message": "Build a compact writing pack for Qoder, then write a project-local draft with only the pack's REF ids.",
                "tool": "research_writing_pack",
                "run_id": target.name,
            }
        )
    return actions


def _read_task(target: Path) -> Dict[str, Any]:
    payload = _read_json(target / "task.json")
    return payload if isinstance(payload, dict) else {}


def _read_json(path: Path) -> Any:
    from .storage import read_json

    try:
        return read_json(path)
    except Exception:
        return None


def _relative(base: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


class _MethodNotFound(Exception):
    pass


class Transport:
    """Newline-delimited JSON (MCP stdio) or LSP Content-Length framing."""

    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.mode: Optional[str] = None
        self._pending_header: Optional[bytes] = None

    def read(self) -> Optional[Dict[str, Any]]:
        if self.mode is None:
            line = self._readline()
            while line is not None and not line.strip():
                line = self._readline()
            if line is None:
                return None
            if line.lstrip().startswith(b"{"):
                self.mode = "ndjson"
                return self._loads(line)
            if line.lower().startswith(b"content-length:"):
                self.mode = "lsp"
                self._pending_header = line
                return self._read_lsp()
            self.mode = "ndjson"
            return self._loads(line)
        if self.mode == "lsp":
            return self._read_lsp()
        line = self._readline()
        while line is not None and not line.strip():
            line = self._readline()
        return None if line is None else self._loads(line)

    def _readline(self) -> Optional[bytes]:
        line = self.reader.readline()
        if not line:
            return None
        return line

    def _read_lsp(self) -> Optional[Dict[str, Any]]:
        headers = []
        if self._pending_header is not None:
            headers.append(self._pending_header)
            self._pending_header = None
        while True:
            line = self._readline()
            if line is None:
                return None
            if not line.strip():
                break
            headers.append(line)
        length = 0
        for line in headers:
            text = line.decode("ascii", errors="replace").strip()
            if text.lower().startswith("content-length:"):
                try:
                    length = int(text.split(":", 1)[1].strip())
                except ValueError:
                    length = 0
        if length <= 0:
            return None
        body = self.reader.read(length)
        if not body:
            return None
        return self._loads(body)

    def _loads(self, payload: bytes) -> Optional[Dict[str, Any]]:
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def write(self, message: Dict[str, Any]) -> None:
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if self.mode == "lsp":
            header = ("Content-Length: %d\r\n\r\n" % len(payload)).encode("ascii")
            self.writer.write(header + payload)
        else:
            self.writer.write(payload + b"\n")
        try:
            self.writer.flush()
        except Exception:
            pass


class MCPServer:
    def __init__(self, service: ResearchMCPService, transport: Transport):
        self.service = service
        self.transport = transport
        self.initialized = False

    def serve(self) -> None:
        while True:
            message = self.transport.read()
            if message is None:
                return
            response = self.handle(message)
            if response is not None:
                self.transport.write(response)

    def handle(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = message.get("method")
        request_id = message.get("id")
        if method is None:
            return None
        if request_id is None:
            return self._notification(str(method), message.get("params") or {})
        try:
            result = self._dispatch(str(method), message.get("params") or {})
        except _MethodNotFound:
            return _rpc_error(request_id, -32601, "method not found: %s" % method)
        except ProjectError as exc:
            return _rpc_error(request_id, -32602, str(exc))
        except Exception as exc:  # protocol must survive one bad tool call
            _log("internal error: %s\n%s" % (exc, traceback.format_exc()))
            return _rpc_error(request_id, -32603, "internal error: %s" % type(exc).__name__)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _notification(self, method: str, params: Dict[str, Any]) -> None:
        if method == "notifications/initialized":
            self.initialized = True
        return None

    def _dispatch(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == "initialize":
            requested = params.get("protocolVersion")
            version = requested if isinstance(requested, str) and requested else DEFAULT_PROTOCOL_VERSION
            client = params.get("clientInfo")
            if isinstance(client, dict):
                self.service.client_info = {
                    "name": str(client.get("name", ""))[:120],
                    "version": str(client.get("version", ""))[:80],
                }
            return {
                "protocolVersion": version,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Bounded research workflow. Call research_project_init first, then "
                    "research_plan/research_run. All outputs stay under <project>/runs/. "
                    "Use research_manuscript_revise to revise an existing paper with project data. "
                    "If the client supports MCP prompts, start-research is the one-click entry; "
                    "it still runs the local TaskAgent through research_bootstrap. "
                    "Human gates G1/G2/S5b/G5 are CLI-only; never sign or approve through MCP."
                ),
            }
        if method == "ping":
            return {}
        if method == "logging/setLevel":
            return {}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str) or name not in TOOL_NAMES:
                raise ProjectError("unknown tool: %s" % name)
            if not isinstance(arguments, dict):
                raise ProjectError("tool arguments must be an object")
            return self._call_tool(name, arguments)
        if method == "resources/list":
            return {"resources": []}
        if method == "prompts/list":
            return {"prompts": PROMPTS}
        if method == "prompts/get":
            name = params.get("name")
            prompt = next(
                (item for item in PROMPTS if item.get("name") == name), None
            )
            if prompt is None:
                raise ProjectError("unknown prompt: %s" % name)
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise ProjectError("prompt arguments must be an object")
            if name == START_RESEARCH_PROMPT:
                text = _start_research_prompt(arguments)
            elif name == REVIEW_IDEA_PROMPT:
                text = _review_idea_prompt(arguments)
            else:
                text = _review_draft_prompt(arguments)
            return {
                "description": prompt["description"],
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": text},
                    }
                ],
            }
        if method in ("shutdown", "exit"):
            return {}
        raise _MethodNotFound(method)

    def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if name not in TOOL_NAMES:
                return tool_error("unknown tool: %s" % name)
            return dispatch_tool(self.service, name, arguments)
        except Exception as exc:
            _log("tool %s failed: %s\n%s" % (name, exc, traceback.format_exc()))
            return tool_error(
                "%s: %s" % (type(exc).__name__, exc),
                {"tool": name},
            )


TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    str(tool.get("name")): (tool.get("inputSchema") or {}) for tool in TOOLS
}


def unknown_argument_problem(name: str, arguments: Any) -> str:
    """Return a refusal reason when arguments carry keys the tool's own schema does not declare.

    The MCP face already rejects these because every tool schema sets additionalProperties=false,
    but the HTTP face and any in-process caller reach dispatch_tool directly, so a handler that
    forgot its own _reject_unknown ignored them silently. Measured: research_host_contract had no
    guard, and a caller sending {"declared": [...]} instead of {"capabilities": [...]} got a 200
    with a contract computed from no declared capabilities at all - a different answer, no error.
    One rule here covers every face and every future tool; the per-handler calls stay as belt and
    braces. Tools whose schema does not constrain additional properties are exempt and must be
    named with a reason in tests/test_dispatch_arg_hygiene.py, so silence is never the default.
    """
    if not isinstance(arguments, dict):
        return ""
    schema = TOOL_SCHEMAS.get(str(name)) or {}
    if schema.get("additionalProperties") is not False:
        return ""
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return ""
    extra = sorted(str(key) for key in arguments if str(key) not in properties)
    if not extra:
        return ""
    return "unknown argument(s) for %s: %s; this tool declares %s" % (
        name,
        ", ".join(extra),
        ", ".join(sorted(str(key) for key in properties)) or "no arguments",
    )


def dispatch_tool(
    service: ResearchMCPService, name: str, arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch one tool call, enforcing the declared argument schema on every face."""
    problem = unknown_argument_problem(name, arguments)
    if problem:
        return tool_error(problem)
    if name == "research_project_init":
        return service.init(arguments)
    if name == "research_bootstrap":
        return service.bootstrap(arguments)
    if name == "research_plan":
        return service.plan(arguments)
    if name == "research_run":
        return service.run(arguments)
    if name == "research_status":
        result = service.status(arguments)
        payload = result.get("structuredContent") if isinstance(result, dict) else None
        if isinstance(payload, dict):
            # A host talking to a long-lived stdio server cannot otherwise tell "feature missing"
            # from "server loaded old code"; this makes it one comparison instead of a guess.
            payload["build"] = build_info()
        return result
    if name == "research_model_profiles":
        return service.model_profiles(arguments)
    if name == "research_model_turns":
        return service.model_turns(arguments)
    if name == "research_model_respond":
        return service.model_respond(arguments)
    if name == "research_model_void":
        return service.model_void(arguments)
    if name == "research_list_artifacts":
        return service.artifacts(arguments)
    if name == "research_read_artifact":
        return service.read(arguments)
    if name == "research_next_actions":
        return service.next_actions(arguments)
    if name == "research_host_contract":
        return service.host_contract(arguments)
    if name == "research_skill_list":
        return service.skill_list(arguments)
    if name == "research_skill_instructions":
        return service.skill_instructions(arguments)
    if name == "research_skill_invoke":
        return service.skill_invoke(arguments)
    if name == "research_skill_distill":
        return service.skill_distill(arguments)
    if name == "research_manuscript_revise":
        return service.manuscript_revise(arguments)
    if name == "research_figure_templates":
        return service.figure_templates(arguments)
    if name == "research_figure_render":
        return service.figure_render(arguments)
    if name == "research_literature_fetch":
        return service.literature_fetch(arguments)
    if name == "research_literature_synthesis":
        return service.literature_synthesis(arguments)
    if name == "research_conference_fetch":
        return service.conference_fetch(arguments)
    if name == "research_writing_pack":
        return service.writing_pack(arguments)
    if name == "research_manuscript_audit":
        return service.manuscript_audit(arguments)
    if name == "research_venue_audit":
        return service.venue_audit(arguments)
    if name == "research_grant_template":
        return service.grant_template(arguments)
    if name == "research_innovation_review":
        return service.innovation_review(arguments)
    if name == "research_manuscript_draft":
        return service.manuscript_draft(arguments)
    if name == "research_manuscript_review":
        return service.manuscript_review(arguments)
    if name == "research_manuscript_ab_review":
        return service.manuscript_ab_review(arguments)
    if name == "research_experiment_codegen":
        return service.experiment_codegen(arguments)
    if name == "research_experiment_status":
        return service.experiment_status(arguments)
    if name == "research_empirical_status":
        return service.empirical_status(arguments)
    if name == "research_skill_packs":
        return service.skill_packs(arguments)
    if name == "research_mandate_status":
        return service.mandate_status(arguments)
    if name == "research_number_provenance":
        return service.number_provenance(arguments)
    if name == "research_study_baseline":
        return service.study_baseline(arguments)
    if name == "research_evolution_status":
        return service.evolution_status(arguments)
    if name == "research_closure_status":
        return service.closure_status(arguments)
    if name == "research_lineage_status":
        return service.lineage_status(arguments)
    if name == "research_support_panel":
        return service.support_panel(arguments)
    if name == "research_support_items":
        return service.support_items(arguments)
    if name == "research_support_verdicts":
        return service.support_verdicts(arguments)
    if name == "research_manuscript_section_edit":
        return service.manuscript_section_edit(arguments)
    if name == "research_manuscript_bind":
        return service.manuscript_bind(arguments)
    return tool_error("unknown tool: %s" % name)


def _rpc_error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _log(message: str) -> None:
    try:
        print("[research-agent-mcp] " + message, file=sys.stderr, flush=True)
    except Exception:
        pass


def _raw_stdio(stdout) -> Any:
    """Redirect ordinary stdout prints to stderr; protocol keeps a raw handle."""
    try:
        protocol_out = os.fdopen(os.dup(stdout.fileno()), "wb", buffering=0)
    except Exception:
        return stdout.buffer
    try:
        os.dup2(sys.stderr.fileno(), stdout.fileno())
    except Exception:
        pass
    return protocol_out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Research-agent MCP stdio server")
    parser.add_argument(
        "--root",
        default=None,
        help="allowed project root (default: RESEARCH_AGENT_MCP_ROOT or cwd)",
    )
    args = parser.parse_args(argv)
    try:
        root = resolve_root(args.root)
    except ProjectError as exc:
        _log(str(exc))
        return 2
    protocol_out = _raw_stdio(sys.stdout)
    service = ResearchMCPService(root)
    transport = Transport(sys.stdin.buffer, protocol_out)
    _log("serving root=%s" % root)
    try:
        MCPServer(service, transport).serve()
    except KeyboardInterrupt:
        pass
    except Exception:
        _log("fatal: %s" % traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
