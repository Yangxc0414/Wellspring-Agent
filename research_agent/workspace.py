"""Local workspace settings surfaces: agents, commands, memory, archive.

These are support records, not evidence. Nothing in this module creates or
mutates SourceHit / Span / Claim / EA / Closure / Signature, and memory or
archive entries never enter an evidence chain.
"""

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .specs import SpecStore
from .storage import JsonStoreError, now_iso, read_json, write_json_atomic

WORKSPACE_SCHEMA = "workspace-0.1"
MEMORY_KINDS = ("decision", "preference", "constraint", "note")
MEMORY_MAX_ENTRIES = 500
MEMORY_MAX_TEXT = 2000
MEMORY_MAX_SCOPE = 120
MEMORY_MAX_SOURCE = 120
ARCHIVE_MAX_BYTES = 2 * 1024 * 1024
ARCHIVE_ID_RE = re.compile(r"^ARC-[A-Za-z0-9-]+$")
MEMORY_ID_RE = re.compile(r"^MEM-[A-Za-z0-9-]+$")
SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
}
STAGE_ORDER = (
    "S1",
    "S2–S3",
    "S4",
    "S5",
    "S6",
    "S8–S12",
    "S8–S12（基金轨）",
    "S13",
    "S13–S16",
    "META",
)


class WorkspaceStoreError(ValueError):
    pass


def _now() -> str:
    return now_iso()


def _new_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "%s-%s-%s" % (prefix, stamp, uuid.uuid4().hex[:6])


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    write_json_atomic(path, payload)


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        payload = read_json(path)
    except JsonStoreError as exc:
        raise WorkspaceStoreError(str(exc))
    if payload is None:
        return default
    if not isinstance(payload, dict):
        raise WorkspaceStoreError("workspace store must be a JSON object")
    return payload


def _clip(value: Any, limit: int, field: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise WorkspaceStoreError("%s must not be empty" % field)
    if len(text) > limit:
        raise WorkspaceStoreError("%s is longer than %d characters" % (field, limit))
    return text


def _relative(path: Optional[Path], root: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except (ValueError, TypeError):
        return Path(path).as_posix()


INFRASTRUCTURE_MODULES = {"waitpoints", "maintenance"}


class AgentRegistry:
    """Read-only projection of modules/*/SPEC.md for the settings UI."""

    def __init__(self, store: Optional[SpecStore] = None):
        self.store = store or SpecStore()

    def snapshot(self) -> Dict[str, Any]:
        specs = self.store.list_specs()
        specs.sort(key=lambda spec: (STAGE_ORDER.index(spec.stage) if spec.stage in STAGE_ORDER else 99, spec.id))
        repo_root = Path(__file__).resolve().parents[1]
        agents = []
        for spec in specs:
            if spec.id in INFRASTRUCTURE_MODULES:
                continue
            agents.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "stage": spec.stage,
                    "version": spec.version,
                    "status": spec.status,
                    "owner": spec.owner,
                    "outputs": list(spec.outputs),
                    "tools": list(spec.tools),
                    "gates": list(spec.gates),
                    "invariants": list(spec.invariants),
                    "spec": _relative(spec.path, repo_root),
                }
            )
        return {
            "schema_version": WORKSPACE_SCHEMA,
            "source": "modules/*/SPEC.md",
            "generated_at": _now(),
            "count": len(agents),
            "agents": agents,
            "boundary": "read-only spec projection; it does not execute agents or change their status",
        }


COMMANDS: List[Dict[str, Any]] = [
    {
        "id": "study.baseline",
        "group": "研究与对照",
        "label": "调优强基线与研究配对比较（只读）",
        "syntax": "python -m research_agent study baseline --study <study.json> [--seeds 1,2] [--folds 0]",
        "description": "在搜索使用的同一划分上做交叉验证调众，"
        "再逐种子与研究成绩配对；折数受研究预算约束，"
        "预算不够两折时直接拒绝。不执行策略、不签核。",
        "safety": "read_only",
    },
    {
        "id": "manuscript.provenance",
        "group": "写作与审稿",
        "label": "数字溯源（只读）",
        "syntax": "python -m research_agent manuscript provenance --draft <稿> --corpus <产物根>",
        "description": "逐个小数判定来源：字节相同命中 / 舍入命中 / 正文位数超过证据；"
        "整数计数不用字符串命中认证，必须重跑。不签核、不改文件。",
        "safety": "read_only",
    },
    {
        "id": "workspace.preflight",
        "group": "仓库自审",
        "label": "治理链是否过期（只读）",
        "syntax": "python -m research_agent workspace preflight",
        "description": "秒级报告 SPEC 版本与 Changelog、导出注册表与 SPEC 投影、"
        "MCP 三个工具面是否一致；只查记账，不查行为，不修复、不执行。",
        "safety": "read_only",
    },
    {
        "id": "task.plan",
        "group": "核心流水线",
        "label": "规划一个科研任务",
        "syntax": "python -m research_agent task plan --goal \"...\" --type auto",
        "description": "按任务类型选择最小必要阶段；只读，不执行检索或运行。",
        "safety": "read_only",
    },
    {
        "id": "task.run",
        "group": "核心流水线",
        "label": "执行一个科研任务",
        "syntax": "python -m research_agent task run --goal \"...\" --type auto --output-dir runtime_data/tasks",
        "description": "执行文献综述/假设设计/实验验证/完整研究路由；人工门与 claim 边界不变。",
        "safety": "local_write",
    },
    {
        "id": "pipeline.run",
        "group": "核心流水线",
        "label": "运行 S1→S12 纵切",
        "syntax": "python -m research_agent pipeline run --topic \"...\" --language zh --venue zh_core_journal",
        "description": "离线 fixture 纵切；不会自动创建 claim。",
        "safety": "local_write",
    },
    {
        "id": "flow.g1",
        "group": "核心流水线",
        "label": "写入 G1 选择决定",
        "syntax": "python -m research_agent flow g1 --idea-file <idea.json> --idea-id IDEA-01 --human-reason \"...\"",
        "description": "把人工选中的候选写成 G1 decision；strict 流程进入 S4 的前置条件。",
        "safety": "human_gate",
    },
    {
        "id": "protocol.freeze_design",
        "group": "核心流水线",
        "label": "预注册冻结设计",
        "syntax": "python -m research_agent protocol freeze-design --design <experiment.json> --limitation \"...\" --human-reason \"...\"",
        "description": "在 S5 之前冻结 design；不要求 RunCapsule，strict 流程据此校验 protocol hash。",
        "safety": "human_gate",
    },
    {
        "id": "literature.run",
        "group": "文献调研",
        "label": "运行 S1 检索与覆盖审计",
        "syntax": "python -m research_agent literature run --question \"...\" [--source openalex --planner glm]",
        "description": "默认 fixture；OpenAlex/GLM 需要显式开启，摘要-only 不生成 span。",
        "safety": "network_opt_in",
    },
    {
        "id": "literature.memory",
        "group": "文献调研",
        "label": "查看文献覆盖记忆",
        "syntax": "python -m research_agent literature memory show|advise",
        "description": "只记录面向覆盖/产出与缺口，不保存摘要或 span 文本，不进入证据链。",
        "safety": "read_only",
    },
    {
        "id": "orchestrate.plan",
        "group": "多智能体编排",
        "label": "生成协作计划",
        "syntax": "python -m research_agent orchestrate plan --topic \"...\" --source fixture",
        "description": "只读：角色、并行 scout、typed handoff 与人工门；不执行检索。",
        "safety": "read_only",
    },
    {
        "id": "orchestrate.run",
        "group": "多智能体编排",
        "label": "运行 S1 scout fan-out + S2 fan-in",
        "syntax": "python -m research_agent orchestrate run --topic \"...\" --source fixture",
        "description": "本地写入 scouting/idea 产物；停在 G1 前，不创建 Claim 或准入技能。",
        "safety": "local_write",
    },
    {
        "id": "agent.manage",
        "group": "多智能体编排",
        "label": "注册自定义 advisory 子智能体",
        "syntax": "python -m research_agent agent add --name \"...\" --role reviewer --purpose \"...\" --check coverage",
        "description": "只允许白名单确定性 checks；输出 advisory note，不写 Claim/EA、不通过门禁。",
        "safety": "local_write",
    },
    {
        "id": "skill.scan",
        "group": "科研技能",
        "label": "扫描本地 SKILL.md",
        "syntax": "python -m research_agent skill scan --path ~/.claude/skills",
        "description": "解析 name/description/allowed-tools，标记 untrusted/scripts；只登记目录，不执行 scripts。",
        "safety": "local_write",
    },
    {
        "id": "skill.list",
        "group": "科研技能",
        "label": "查看技能目录与风险标记",
        "syntax": "python -m research_agent skill list",
        "description": "只读注册表；execution=not_available，不把 allowed-tools 当成权限。",
        "safety": "read_only",
    },
    {
        "id": "revision.run",
        "group": "科研技能",
        "label": "修订已有论文并导出投稿工作包",
        "syntax": "python -m research_agent revision run --draft <paper.md|docx|tex> --data <table.csv> --metrics <metrics.json> --figures <figures.json> --venue software_journal --profile <profile> --output-dir runtime_data/revision",
        "description": "保留原实验叙事与引用，重算指标、生成数据图、逐段改写并导出 MD/TeX/DOCX/PDF；无 profile 为 copy mode，不替代投稿决定。",
        "safety": "local_write",
    },
    {
        "id": "writing.pack",
        "group": "科研技能",
        "label": "把一次 run 压成写作包",
        "syntax": "python -m research_agent writing pack --project <project> --run-id <RUN-ID> --max-sources 8",
        "description": "只读投影 run 的来源卡、span、设计、run/claim 状态与写作契约；不签核、不编造引用或数字。",
        "safety": "local_write",
    },
    {
        "id": "writing.audit",
        "group": "科研技能",
        "label": "预审 Qoder 写好的中文手稿",
        "syntax": "python -m research_agent writing audit --project <project> --run-id <RUN-ID> --draft <draft.md>",
        "description": "检查引用键、结果数值、章节、占位符与 fixture；submission_ready 始终 false，不替代同行评审。",
        "safety": "local_write",
    },
    {
        "id": "conference.fetch",
        "group": "科研技能",
        "label": "抓取近 2–3 年顶会 arXiv 公开论文",
        "syntax": "python -m research_agent conference fetch --target-dir <project>/inputs --venues NeurIPS,ICLR,ICML,ACL --years 2024,2025,2026 --allow-network",
        "description": "按 venue/year 下载 arXiv 公开 PDF；过滤 workshop/symposium/preprint/非 agent 标题；venue 来自 comment，未独立核验。",
        "safety": "network_opt_in",
    },
    {
        "id": "literature.synthesize",
        "group": "科研技能",
        "label": "生成多篇文献综合矩阵",
        "syntax": "python -m research_agent literature synthesize --project <project> --run-id <RUN-ID> --max-themes 7",
        "description": "多篇来源 → 主题×来源矩阵；每主题至少 2 篇，记录一致点、张力和未使用来源；不创建 Claim。",
        "safety": "local_write",
    },
    {
        "id": "loop.status",
        "group": "科研技能",
        "label": "查看自动化科研主循环状态",
        "syntax": "python -m research_agent loop status --project <project> --run-id <RUN-ID>",
        "description": "S0–S16 阶段、Q0/G1/G2/S5b/G5 门禁、创新/手稿迭代次数与下一步的只读投影。",
        "safety": "read_only",
    },
    {
        "id": "experiment.approve",
        "group": "科研技能",
        "label": "人工批准本地实验执行",
        "syntax": 'python -m research_agent experiment approve --project <project> --experiment-id <EXP-ID> --human-reason "<why>"',
        "description": "记录 data/spec/code 哈希与人工理由；不是 Claim，不自动执行。",
        "safety": "human_gate",
    },
    {
        "id": "experiment.run",
        "group": "科研技能",
        "label": "显式本地执行实验代码包",
        "syntax": "python -m research_agent experiment run --project <project> --experiment-id <EXP-ID> --allow-execute",
        "description": "只在本地 CLI；校验 approval 后运行生成的 runner，记录环境/命令/stdout/stderr/artifact SHA；不是 EA/Claim。",
        "safety": "local_write",
    },
    {
        "id": "experiment.ingest",
        "group": "科研技能",
        "label": "校验实验执行并生成 evidence",
        "syntax": "python -m research_agent experiment ingest --project <project> --experiment-id <EXP-ID>",
        "description": "校验 execution/receipt/metrics/artifact 哈希，写 experiment-evidence.json；不是 EA/Claim。",
        "safety": "local_write",
    },
    {
        "id": "experiment.claim",
        "group": "科研技能",
        "label": "人签本地实验 Claim",
        "syntax": 'python -m research_agent experiment claim --project <project> --experiment-id <EXP-ID> --statement "..." --human-reason "..." --assertion "metric=accuracy,value=0.85,comparator=>=,tolerance=0.01"',
        "description": "只能由人执行；要求 verified evidence，绑定 evidence hash；不是 MCP 工具。",
        "safety": "human_gate",
    },
    {
        "id": "experiment.closure",
        "group": "科研技能",
        "label": "检查本地实验 closure",
        "syntax": "python -m research_agent experiment closure --project <project> --experiment-id <EXP-ID> [--manuscript <draft.md>]",
        "description": "校验 data/spec/code/approval/execution/metrics/evidence/claim 与哈希；不是 EA closure，不通过即阻断。",
        "safety": "local_write",
    },
    {
        "id": "experiment.sign",
        "group": "科研技能",
        "label": "人签本地实验 closure",
        "syntax": "python -m research_agent experiment sign --project <project> --experiment-id <EXP-ID> --report <closure-report.json> --human-reason \"<why>\"",
        "description": "只能由人执行；要求 closure ready；导出 manifest 标记 submission=false；不是 MCP 工具。",
        "safety": "human_gate",
    },
    {
        "id": "experiment.lineage",
        "group": "科研技能",
        "label": "构建或验证实验 lineage",
        "syntax": "python -m research_agent experiment lineage --project <project> --experiment-id <EXP-ID> [--verify]",
        "description": "spec/data/code/approval/execution/metrics/evidence/claim/closure 的哈希 DAG；verify 检测 stale。",
        "safety": "local_write",
    },
    {
        "id": "experiment.scaffold",
        "group": "科研技能",
        "label": "生成可审阅的本地实验代码包",
        "syntax": "python -m research_agent experiment scaffold --project <project> --run-id <RUN-ID> --data inputs/data.csv --target y --features x1,x2",
        "description": "S4 设计 + 项目内 CSV → spec/runner/requirements/README/manifest；只生成代码，不执行、不装依赖、不创建 EA/Claim。",
        "safety": "local_write",
    },
    {
        "id": "innovation.review",
        "group": "科研技能",
        "label": "创新点三评审与修订循环",
        "syntax": "python -m research_agent innovation review --project <project> --run-id <RUN-ID> --rounds 2",
        "description": "缺口→候选→novelty/evidence/feasibility 评审→修订→再评审；评分只是 advisory，不通过 G1、不写 Claim。",
        "safety": "local_write",
    },
    {
        "id": "manuscript.draft",
        "group": "科研技能",
        "label": "从证据包生成中文初稿",
        "syntax": "python -m research_agent manuscript draft --project <project> --run-id <RUN-ID> --output <project>/drafts/review.md",
        "description": "写作包+创新评审→中文综述/立场初稿→确定性审计；不伪造实验/数字；需要真实模型 key。",
        "safety": "local_write",
    },
    {
        "id": "manuscript.review",
        "group": "科研技能",
        "label": "手稿 rubric 评审与修订循环",
        "syntax": "python -m research_agent manuscript review --project <project> --run-id <RUN-ID> --draft <project>/drafts/review.md --rounds 2",
        "description": "评审→修订→再评审；候选修订必须通过引用/数值/章节审计且 blockers 不变差；submission_ready=false。",
        "safety": "local_write",
    },
    {
        "id": "figure.render",
        "group": "科研技能",
        "label": "渲染 AstraDraw 方法示意图",
        "syntax": "python -m research_agent figure render --template framework-example --output-dir runtime_data/figure-demo --title \"...\"",
        "description": "从项目 scene 或 vendored AstraDraw 模板生成 SVG/PNG/audit/manifest；模板仅视觉先验，schematic=true。",
        "safety": "local_write",
    },
    {
        "id": "rsi.policy",
        "group": "受治理 RSI",
        "label": "查看/切换自进化策略",
        "syntax": "python -m research_agent rsi policy show|set [--enabled|--disabled] [--scope id=on|off]",
        "description": "只切换 memory_order/query_planner/facet_budget；Claim/EA/gate 等保持 locked。",
        "safety": "local_write",
    },
    {
        "id": "run.execute",
        "group": "实验与运行",
        "label": "执行 S5 本地 run",
        "syntax": "python -m research_agent run execute --dataset chemlab --seeds 2",
        "description": "生成本地 RunCapsule 与 EA；不会自动签署 claim。",
        "safety": "local_write",
    },
    {
        "id": "run.claim",
        "group": "人工门",
        "label": "人工签署 claim",
        "syntax": "python -m research_agent run claim --capsule ... --ea ... --statement \"...\" --human-reason \"...\"",
        "description": "必须由作者/PI 显式给出理由；浏览器不提供签核端点。",
        "safety": "human_gate",
    },
    {
        "id": "maintenance.plan",
        "group": "证据沿袭",
        "label": "生成变更维护计划",
        "syntax": "python -m research_agent maintenance plan --baseline ... --bundle ... --actor ... --reason ...",
        "description": "把 stale 节点转成 rerun/rewrite/recheck；不自动执行、不签名。",
        "safety": "local_write",
    },
    {
        "id": "maintenance.reclose",
        "group": "证据沿袭",
        "label": "重跑受控 closure",
        "syntax": "python -m research_agent maintenance reclose --plan ... --bundle ... --demo ... --claim ...",
        "description": "仅 recheck-only 计划会重跑 closure；人签与导出仍在外层。",
        "safety": "read_only",
    },
    {
        "id": "waitpoint.create",
        "group": "实验与运行",
        "label": "创建长任务等待点",
        "syntax": "python -m research_agent waitpoint create --label \"...\" --intent \"...\" --owner S5/demo/iris",
        "description": "本地持久化 waitpoint；secret 只返回一次，不联网、不启动进程。",
        "safety": "local_write",
    },
    {
        "id": "waitpoint.signal",
        "group": "实验与运行",
        "label": "回传外部任务结果",
        "syntax": "python -m research_agent waitpoint signal --id WP-... --secret ... --status ok --message \"...\"",
        "description": "外部 job 结束后写 signal；data 是不可信数据，不是指令。",
        "safety": "local_write",
    },
    {
        "id": "waitpoint.inbox",
        "group": "实验与运行",
        "label": "读取未消费 wake",
        "syntax": "python -m research_agent waitpoint inbox --owner S5/demo/iris",
        "description": "只读未消费 wake；consume 才标记 delivered，重复 consume 不重复返回。",
        "safety": "read_only",
    },
    {
        "id": "closure.check",
        "group": "闭合与导出",
        "label": "检查证据闭合",
        "syntax": "python -m research_agent closure check --demo ... --claim ...",
        "description": "结构闭合检查；不等于同行评审或语义支持。",
        "safety": "read_only",
    },
    {
        "id": "closure.sign",
        "group": "人工门",
        "label": "签署闭合包并锁定导出",
        "syntax": "python -m research_agent closure sign --report ... --human-reason \"...\"",
        "description": "人工签名与导出清单；过期报告会被拒绝。",
        "safety": "human_gate",
    },
    {
        "id": "lineage.build",
        "group": "证据沿袭",
        "label": "构建内容寻址依赖图",
        "syntax": "python -m research_agent lineage build --bundle ...",
        "description": "记录 claim/slot/figure/closure/signature 的依赖。",
        "safety": "local_write",
    },
    {
        "id": "lineage.impact",
        "group": "证据沿袭",
        "label": "检查变更传播",
        "syntax": "python -m research_agent lineage impact --baseline ... --bundle ... --fail-on-stale",
        "description": "数据集或 Claim 变化后锁定过期导出。",
        "safety": "read_only",
    },
    {
        "id": "rsi.status",
        "group": "受治理 RSI",
        "label": "查看 RSI 账本与租约",
        "syntax": "python -m research_agent rsi status",
        "description": "只读；准入与撤销仍在人工流程。",
        "safety": "read_only",
    },
    {
        "id": "rsi.trace",
        "group": "受治理 RSI",
        "label": "校验 lease→run→confirmation",
        "syntax": "python -m research_agent rsi trace --ledger ... --capsule ...",
        "description": "只读审计，不回流准入。",
        "safety": "read_only",
    },
    {
        "id": "workspace.agents",
        "group": "工作区",
        "label": "导出模块注册表",
        "syntax": "python -m research_agent workspace export --output-dir apps/web/public",
        "description": "生成设置页使用的 SPEC 快照与命令目录。",
        "safety": "local_write",
    },
    {
        "id": "workspace.memory",
        "group": "工作区",
        "label": "管理本地记忆",
        "syntax": "python -m research_agent workspace memory list|add|delete",
        "description": "用户自管的工作记忆，不是证据、不进 Claim。",
        "safety": "local_write",
    },
    {
        "id": "workspace.archive",
        "group": "工作区",
        "label": "管理本地归档",
        "syntax": "python -m research_agent workspace archive list|add|delete",
        "description": "保存任务 JSON 快照；不改变证据状态。",
        "safety": "local_write",
    },
    {
        "id": "spec.show",
        "group": "规格",
        "label": "查看模块规格",
        "syntax": "python -m research_agent spec show literature",
        "description": "读取 SPEC 契约；规格是代码的源。",
        "safety": "read_only",
    },
]


def cli_command_surface() -> List[Dict[str, Any]]:
    """Every command path the CLI actually accepts, derived from the parser itself.

    The curated ``COMMANDS`` list is hand-written documentation and drifts silently: measured today,
    twelve whole groups (`study`, `memory`, `handoff`, `host-model`, `benchmark`, ...) were invisible
    to a host reading the exported catalog while the workspace snapshot test stayed green. Deriving
    the surface means a command becomes discoverable the moment it is wired, and the curated entries
    keep their richer human-written descriptions.
    """
    import argparse as _argparse

    from .cli import build_parser

    rows: List[Dict[str, Any]] = []

    def walk(parser: Any, prefix: str) -> None:
        actions = [
            action
            for action in parser._actions
            if isinstance(action, _argparse._SubParsersAction)
        ]
        for action in actions:
            for name, sub in sorted(action.choices.items()):
                ident = "%s.%s" % (prefix, name) if prefix else name
                has_children = any(
                    isinstance(other, _argparse._SubParsersAction) for other in sub._actions
                )
                if has_children:
                    walk(sub, ident)
                    continue
                usage = sub.format_usage().strip()
                rows.append(
                    {
                        "id": ident,
                        "group": ident.split(".")[0],
                        "label": name.replace("-", " "),
                        "syntax": "python -m research_agent %s" % ident.replace(".", " ", 1),
                        "description": sub.description.strip() if sub.description else usage,
                        "safety": "catalog_only",
                        "curated": False,
                    }
                )

    walk(build_parser(), "")
    return rows


class CommandRegistry:
    """Descriptive catalog of wired CLI commands. It never executes them."""

    def snapshot(self) -> Dict[str, Any]:
        curated = [dict(item, curated=True) for item in COMMANDS]
        documented = {str(item["id"]).replace(".", "_") for item in COMMANDS}
        documented |= {str(item["id"]) for item in COMMANDS}
        derived = [
            item for item in cli_command_surface()
            if item["id"] not in documented
            and item["id"].replace("_", ".") not in documented
        ]
        commands = curated + sorted(derived, key=lambda item: item["id"])
        return {
            "schema_version": WORKSPACE_SCHEMA,
            "generated_at": _now(),
            "count": len(commands),
            "curated": len(curated),
            "derived": len(derived),
            "commands": commands,
            "boundary": (
                "descriptive catalog only; the UI does not execute shell commands; entries marked "
                "safety=catalog_only are derived from the parser and have not been classified by a "
                "human, so they carry no safety promise"
            ),
        }


@dataclass
class MemoryEntry:
    id: str
    text: str
    kind: str
    scope: str
    source: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "kind": self.kind,
            "scope": self.scope,
            "source": self.source,
            "created_at": self.created_at,
        }


class MemoryStore:
    """User-curated workspace memory, explicitly outside the evidence chain."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> List[Dict[str, Any]]:
        payload = _read_json(self.path, {"schema_version": WORKSPACE_SCHEMA, "entries": []})
        entries = payload.get("entries", [])
        if not isinstance(entries, list):
            raise WorkspaceStoreError("memory entries must be a list")
        return [entry for entry in entries if isinstance(entry, dict)]

    def _save(self, entries: List[Dict[str, Any]]) -> None:
        _atomic_write_json(
            self.path,
            {"schema_version": WORKSPACE_SCHEMA, "updated_at": _now(), "entries": entries},
        )

    def snapshot(self) -> Dict[str, Any]:
        entries = self._load()
        return {
            "schema_version": WORKSPACE_SCHEMA,
            "count": len(entries),
            "entries": entries,
            "boundary": "workspace memory is user-curated and is not evidence; it never enters Claim/EA/gate/export",
        }

    def add(self, text: str, kind: str = "note", scope: str = "workspace", source: str = "user") -> Dict[str, Any]:
        if kind not in MEMORY_KINDS:
            raise WorkspaceStoreError("memory kind must be one of: " + ", ".join(MEMORY_KINDS))
        entry = MemoryEntry(
            id=_new_id("MEM"),
            text=_clip(text, MEMORY_MAX_TEXT, "memory text"),
            kind=kind,
            scope=_clip(scope, MEMORY_MAX_SCOPE, "memory scope"),
            source=_clip(source, MEMORY_MAX_SOURCE, "memory source"),
            created_at=_now(),
        ).to_dict()
        entries = self._load()
        if len(entries) >= MEMORY_MAX_ENTRIES:
            raise WorkspaceStoreError("memory store is full (%d entries)" % MEMORY_MAX_ENTRIES)
        entries.insert(0, entry)
        self._save(entries)
        return entry

    def delete(self, entry_id: str) -> bool:
        if not MEMORY_ID_RE.match(entry_id or ""):
            return False
        entries = self._load()
        remaining = [entry for entry in entries if entry.get("id") != entry_id]
        if len(remaining) == len(entries):
            return False
        self._save(remaining)
        return True


class ArchiveStore:
    """Local task snapshots. Archive metadata is not evidence and never signs."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, archive_id: str) -> Path:
        if not ARCHIVE_ID_RE.match(archive_id or ""):
            raise WorkspaceStoreError("invalid archive id")
        return self.root / (archive_id + ".json")

    @staticmethod
    def _reject_secret_keys(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in SECRET_KEYS:
                    raise WorkspaceStoreError("archive payload must not contain secret field: %s" % key)
                ArchiveStore._reject_secret_keys(item)
        elif isinstance(value, list):
            for item in value:
                ArchiveStore._reject_secret_keys(item)

    def add(self, title: str, task_id: str, payload: Dict[str, Any], note: str = "") -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise WorkspaceStoreError("archive payload must be a JSON object")
        self._reject_secret_keys(payload)
        archive_id = _new_id("ARC")
        meta = {
            "id": archive_id,
            "title": _clip(title, 200, "archive title"),
            "task_id": _clip(task_id, 120, "archive task_id"),
            "note": " ".join(str(note or "").split())[:500],
            "created_at": _now(),
        }
        body = {"schema_version": WORKSPACE_SCHEMA, "meta": meta, "payload": payload}
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if len(encoded) > ARCHIVE_MAX_BYTES:
            raise WorkspaceStoreError("archive payload is larger than %d bytes" % ARCHIVE_MAX_BYTES)
        _atomic_write_json(self._path(archive_id), body)
        meta["bytes"] = len(encoded)
        return meta

    def list(self) -> List[Dict[str, Any]]:
        if not self.root.is_dir():
            return []
        items: List[Dict[str, Any]] = []
        for path in sorted(self.root.glob("ARC-*.json")):
            try:
                payload = _read_json(path, {})
            except WorkspaceStoreError:
                continue
            meta = payload.get("meta")
            if isinstance(meta, dict) and meta.get("id") == path.stem:
                meta = dict(meta)
                meta["bytes"] = path.stat().st_size
                items.append(meta)
        items.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return items

    def get(self, archive_id: str) -> Dict[str, Any]:
        path = self._path(archive_id)
        if not path.is_file():
            raise WorkspaceStoreError("archive not found: " + archive_id)
        payload = _read_json(path, {})
        if not isinstance(payload.get("payload"), dict):
            raise WorkspaceStoreError("archive payload is malformed: " + archive_id)
        return payload

    def delete(self, archive_id: str) -> bool:
        path = self._path(archive_id)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def snapshot(self) -> Dict[str, Any]:
        items = self.list()
        return {
            "schema_version": WORKSPACE_SCHEMA,
            "count": len(items),
            "items": items,
            "boundary": "task snapshots only; archive does not create, sign or invalidate claims",
        }


def export_workspace_snapshots(
    output_dir: Path,
    store: Optional[SpecStore] = None,
    custom_agents_path: Optional[Path] = None,
    policy_path: Optional[Path] = None,
) -> Dict[str, Any]:
    from .custom_agents import CustomAgentStore
    from .evolution_policy import EvolutionPolicyStore
    from .orchestrator import topology_snapshot
    from .paths import DEFAULT_CUSTOM_AGENTS_PATH, DEFAULT_EVOLUTION_POLICY_PATH

    output = Path(output_dir)
    agents = AgentRegistry(store).snapshot()
    commands = CommandRegistry().snapshot()
    custom_store = CustomAgentStore(
        Path(custom_agents_path) if custom_agents_path else DEFAULT_CUSTOM_AGENTS_PATH
    )
    policy_store = EvolutionPolicyStore(
        Path(policy_path) if policy_path else DEFAULT_EVOLUTION_POLICY_PATH
    )
    custom_snapshot = custom_store.snapshot()
    policy_snapshot = policy_store.snapshot()
    topology = topology_snapshot(custom_store.list(enabled_only=True), policy_snapshot)
    _atomic_write_json(output / "agent-registry.json", agents)
    _atomic_write_json(output / "command-catalog.json", commands)
    _atomic_write_json(output / "orchestration-topology.json", topology)
    _atomic_write_json(output / "custom-agents.json", custom_snapshot)
    _atomic_write_json(output / "evolution-policy.json", policy_snapshot)
    return {
        "output_dir": str(output),
        "agents": agents["count"],
        "commands": commands["count"],
        "custom_agents": custom_snapshot["count"],
        "policy_enabled": policy_snapshot["enabled"],
        "files": [
            "agent-registry.json",
            "command-catalog.json",
            "orchestration-topology.json",
            "custom-agents.json",
            "evolution-policy.json",
        ],
    }
