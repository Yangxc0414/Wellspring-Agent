"""Turn a search study into a claim draft the existing governance path can sign.

A finding that cannot be signed cannot be reported: ``writing_pack`` only admits result
numbers that appear as ``observed`` values on a human-approved claim's assertions. Without
this bridge, the study's numbers stay outside the evidence chain and the loop still ends at
"we ran something interesting" instead of "the paper may report this".

Two rules make the bridge safe rather than a shortcut:

1. only comparisons whose interval excludes zero become assertions, so an underpowered point
   estimate can never be signed into a paper;
2. the claim is written as a draft carrying the study/spec/evidence hashes; signing stays a
   separate human CLI act, exactly as with run and local-experiment claims.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .contracts import ClaimAssertion, ClaimRecord
from .search_lab import PROVENANCE_BOUNDARY, write_study_package
from .storage import now_iso, read_json, write_json_atomic

STUDY_CLAIM_SCHEMA = "study-claim-draft-0.2"
GUARD_AUDIT_SCHEMA = "guard-audit-0.1"

DECIDABLE = "interval excludes zero"
NOT_DECIDABLE = "interval covers zero: not signable"
OVERTURNED = (
    "a higher-power study of the same design on the same dataset does not decide this "
    "comparison, so it is not signable"
)


def run_and_stage_studies(
    output_root: Path,
    datasets: Optional[List[str]] = None,
    seeds: Optional[List[int]] = None,
    budget: int = 60,
    min_delta: float = 0.005,
) -> Dict[str, Any]:
    """Run the study for each dataset and keep the evidence envelopes together."""
    datasets = datasets or ["iris"]
    result = {}
    for dataset in datasets:
        result[dataset] = write_study_package(
            Path(output_root) / dataset,
            dataset=dataset,
            seeds=seeds,
            budget=budget,
            min_delta=min_delta,
        )
    return result


def comparison_verdicts(evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per comparison, stating whether its interval decides anything.

    This is the single place that turns an interval into a verdict, so the claim draft and any
    read-only inventory agree on which findings are undecidable rather than re-deriving it.
    """
    candidates: List[tuple] = list((evidence.get("comparison") or {}).items())
    # The interaction is usually the study's actual question, so it must be signable too.
    interaction = evidence.get("interaction_inference")
    interaction = interaction if isinstance(interaction, dict) else {}
    if interaction.get("available"):
        candidates.append(
            (
                str(interaction.get("name") or "memory_x_gate_interaction"),
                {
                    "mean_diff": interaction.get("mean_interaction"),
                    "ci95_low": interaction.get("ci95_low"),
                    "ci95_high": interaction.get("ci95_high"),
                    "comparator": "difference-of-differences",
                },
            )
        )
    conditional = evidence.get("conditional_interactions")
    conditional = conditional if isinstance(conditional, dict) else {}
    if conditional.get("available"):
        for level, item in sorted((conditional.get("slices") or {}).items()):
            item = item if isinstance(item, dict) else {}
            if item.get("available", item.get("mean_interaction") is not None):
                candidates.append(
                    (
                        str(item.get("name") or "conditional_interaction@%s" % level),
                        {
                            "mean_diff": item.get("mean_interaction"),
                            "ci95_low": item.get("ci95_low"),
                            "ci95_high": item.get("ci95_high"),
                            "comparator": "difference-of-differences",
                        },
                    )
                )
        three = conditional.get("three_way")
        three = three if isinstance(three, dict) else {}
        if three.get("available", three.get("mean_interaction") is not None):
            candidates.append(
                (
                    str(three.get("name") or "three_way_interaction"),
                    {
                        "mean_diff": three.get("mean_interaction"),
                        "ci95_low": three.get("ci95_low"),
                        "ci95_high": three.get("ci95_high"),
                        "comparator": "difference-of-differences",
                    },
                )
            )
    rows: List[Dict[str, Any]] = []
    for name, item in candidates:
        # On-disk evidence is caller data: a non-dict comparison must degrade to "unavailable",
        # not raise inside a read-only inventory.
        item = item if isinstance(item, dict) else {}
        observed = item.get("mean_diff")
        low = item.get("ci95_low")
        high = item.get("ci95_high")
        row = {
            "comparison": name,
            "comparator": item.get("comparator", "baseline"),
            "mean_diff": observed,
            "ci95": [low, high] if low is not None and high is not None else None,
        }
        if observed is None or low is None or high is None:
            row["state"] = "unavailable"
            row["reason"] = "interval unavailable"
        elif low > 0:
            row["state"] = "positive"
            row["reason"] = DECIDABLE
        elif high < 0:
            row["state"] = "negative"
            row["reason"] = DECIDABLE
        else:
            row["state"] = "undecidable"
            row["reason"] = NOT_DECIDABLE
        rows.append(row)
    return rows


def decidable_assertions(evidence: Dict[str, Any], dataset: str) -> Dict[str, Any]:
    """Split comparisons into signable and not-signable using the interval, not the estimate."""
    assertions: List[ClaimAssertion] = []
    rejected: List[Dict[str, Any]] = []
    for row in comparison_verdicts(evidence):
        name = row["comparison"]
        if row["state"] == "unavailable":
            rejected.append({"comparison": name, "reason": row["reason"]})
            continue
        if row["state"] == "undecidable":
            rejected.append(
                {
                    "comparison": name,
                    "mean_diff": row["mean_diff"],
                    "ci95": row["ci95"],
                    "reason": NOT_DECIDABLE,
                }
            )
            continue
        observed = float(row["mean_diff"])
        assertions.append(
            ClaimAssertion(
                claim_type="numerical",
                metric="%s.%s.%s" % (evidence.get("primary_metric", "metric"), dataset, name),
                comparator=">" if observed > 0 else "<",
                value=0.0,
                tolerance=0.0,
                observed=observed,
                status="verified",
                condition="%s vs %s (%s)" % (name, row["comparator"], DECIDABLE),
            )
        )
    return {"assertions": assertions, "rejected": rejected}


def origin_sha256_of(origin: Dict[str, Any]) -> str:
    """Canonical hash of a study-origin sidecar, so a claim can bind the idea it tests."""
    payload = {key: value for key, value in (origin or {}).items() if key != "origin_sha256"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def origin_state(directory: Path) -> Dict[str, Any]:
    """Whether the sidecar still describes the study sitting next to it."""
    from .search_lab import spec_sha256_of

    origin = read_json(Path(directory) / "study-origin.json")
    if not isinstance(origin, dict) or not origin:
        return {"state": "absent"}
    spec = read_json(Path(directory) / "study-spec.json") or {}
    bound = str(origin.get("study_spec_sha256") or "") == spec_sha256_of(spec)
    return {
        "state": "bound" if bound else "stale",
        "origin": origin,
        "origin_sha256": origin_sha256_of(origin),
        "idea_id": str(origin.get("idea_id") or ""),
        "falsification": str(origin.get("falsification") or ""),
    }


def replication_context(directory: Path) -> Dict[str, Any]:
    """What the project's other packages, run on the same design, say about this package.

    A claim is drafted from one package, but a reviewer reads the project. This pulls the
    read-only replication count into the claim's verification block and, critically, marks the
    comparisons a higher-power package on the same dataset failed to reproduce — those stop
    being signable.
    """
    # Imported lazily: study_replication consumes comparison_verdicts from this module.
    from .study_replication import build_replication_report, comparability_key, load_package

    current = load_package(directory)
    if not current:
        return {}
    studies = directory.parent
    if not studies.is_dir():
        return {}
    report = build_replication_report(
        studies, siblings=True, seed_scope=current.get("seed_set") or []
    )
    key = comparability_key(current)
    group = next((g for g in report["replicated"] if g["design_key"] == key), None)
    alone = next((u for u in report["unreplicated"] if u["design_key"] == key), None)
    own = str(current["dataset"])
    overturned = [
        item
        for item in report["overturned"]
        if item["design_key"] == key and item["decided_at"]["directory"] == current["directory"]
    ]
    return {
        "design_key": key,
        "dataset": own,
        # Whether a higher-power twin of this same design exists on this dataset at all: without it
        # a package cannot be power-audited, so its clean record is not evidence of safety.
        "power_ladder_present": any(
            str(ladder.get("dataset")) == own
            and ladder.get("design_key") == key
            and len(ladder.get("packages") or []) > 1
            for ladder in report.get("power_ladders") or []
        ),
        # Whoever is refused an assertion deserves to see how wide the evidence pool was that
        # refused it: the same project only, or sibling projects too.
        "siblings_included": bool(report.get("siblings_included")),
        "studies_scanned": report["packages"],
        "datasets_present": (group or alone or {}).get("datasets") or [own],
        "replication_packages": {
            str(name): str(package) for name, package in (group or {}).get("packages", {}).items()
        },
        "comparisons": {
            name: {
                "status": result["status"],
                "decided_in": result["decided_in"],
                "generalizes": result["generalizes"],
            }
            for name, result in (group or {}).get("comparisons", {}).items()
        },
        "overturned": [
            {
                "comparison": item["comparison"],
                "reason": item["reason"],
                "decided_at_seeds": item["decided_at"]["seeds"],
                "superseded_by": item["at_higher_power"]["directory"],
                "superseded_by_seeds": item["at_higher_power"]["seeds"],
                "shared_seeds": item.get("shared_seeds"),
                "arbiter_independent": item.get("arbiter_independent"),
                "overturn_kind": item.get("overturn_kind"),
                "claimed_effect": item.get("claimed_effect"),
                "arbiter_bound": item.get("arbiter_bound"),
            }
            for item in overturned
        ],
        "warnings": report["warnings"],
        "boundary": report["boundary"],
    }


def guard_audit(project: Path) -> Dict[str, Any]:
    """Counterfactual for evaluation: what would reach a human signature without the guard?

    This is deliberately a *guard-firing* measurement, not a claim that papers got better: it counts
    the assertions each package on disk would have offered, and how many of them the project's own
    higher-power or cross-environment evidence contradicts. It is the number an evaluation of the
    runtime needs before anyone argues about quality.
    """
    root = Path(project)
    studies = root / "studies"
    rows: List[Dict[str, Any]] = []
    offered = blocked = fully_blocked = stale_refusals = 0
    audited_packages = audited_offered = audited_blocked_packages = 0
    for directory in sorted(path for path in studies.iterdir() if path.is_dir()) if studies.is_dir() else []:
        evidence = read_json(directory / "study-evidence.json")
        if not isinstance(evidence, dict):
            continue
        decided = [
            str(row["comparison"])
            for row in comparison_verdicts(evidence)
            if row["state"] in ("positive", "negative")
        ]
        context = replication_context(directory)
        blocked_names = [
            str(item["comparison"])
            for item in context.get("overturned") or []
            if str(item["comparison"]) in decided
        ]
        provenance = origin_state(directory)
        audited = bool(context.get("power_ladder_present"))
        offered += len(decided)
        blocked += len(blocked_names)
        if audited:
            audited_packages += 1
            audited_offered += len(decided)
            if blocked_names:
                audited_blocked_packages += 1
        if decided and len(blocked_names) == len(decided):
            fully_blocked += 1
        if provenance["state"] == "stale":
            stale_refusals += 1
        rows.append(
            {
                "package": directory.name,
                "dataset": str(evidence.get("dataset") or ""),
                "seeds": len(evidence.get("seeds") or []),
                "offered": len(decided),
                "blocked": len(blocked_names),
                "blocked_comparisons": blocked_names,
                "power_ladder_present": audited,
                "origin": provenance["state"],
            }
        )
    return {
        "schema_version": GUARD_AUDIT_SCHEMA,
        "project_dir": str(root),
        "packages": len(rows),
        "offered_assertions": offered,
        "blocked_by_replication": blocked,
        "blocking_rate": round(blocked / float(offered), 4) if offered else None,
        "packages_fully_blocked": fully_blocked,
        "origin_stale_refusals": stale_refusals,
        "power_audited_packages": audited_packages,
        "offered_in_audited_packages": audited_offered,
        "audited_packages_with_block": audited_blocked_packages,
        "blocking_rate_where_auditable": (
            round(blocked / float(audited_offered), 4) if audited_offered else None
        ),
        "per_package": [row for row in rows if row["offered"] or row["origin"] == "stale"],
        "reading": (
            "%d of %d assertions this project could have offered a human would have been blocked by "
            "its own higher-power or cross-environment evidence" % (blocked, offered)
        ),
        "boundary": (
            "a guard-firing measurement on packages already on disk: it counts what the runtime "
            "refuses, and says nothing about whether accepted papers, reviewer scores or author "
            "time improved"
        ),
    }


BASELINE_FILENAME = "tuned-baseline.json"


def _bind_baseline(
    directory: Path, baseline_file: str, dataset: str, study_seeds: Any
) -> Dict[str, Any]:
    """Store a tuned-baseline report inside the package and report what was stored.

    Bytes are copied verbatim rather than re-serialised, so the hash the claim records is the
    hash of the file a reader can open, not of a re-rendered copy of it.
    """
    source = Path(baseline_file).expanduser()
    if not source.is_file():
        raise ValueError(
            "no tuned baseline to bind at %s: pass --baseline-file with the report written by "
            "`study baseline --output`, or omit the flag to leave the claim without an "
            "external reference" % source
        )
    raw = source.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise ValueError("tuned baseline is not readable JSON: %s (%s)" % (source, exc))
    if not isinstance(payload, dict):
        raise ValueError("tuned baseline must be a JSON object: " + str(source))
    baseline_dataset = str(payload.get("dataset") or "")
    if not baseline_dataset:
        # Two producers write this schema: the study-paired report carries one environment as
        # `dataset`, the grid-over-environments report carries them as `datasets`. A one-item
        # list is the same statement, and refusing it would make the CLI's own baseline command
        # produce a file that the claim command rejects for the wrong reason.
        listed = [str(item) for item in (payload.get("datasets") or []) if str(item).strip()]
        if len(set(listed)) == 1:
            baseline_dataset = listed[0]
    if not baseline_dataset:
        raise ValueError(
            "tuned baseline records no single dataset (it names neither `dataset` nor one-item "
            "`datasets`), so it cannot be checked against this study: " + str(source)
        )
    if baseline_dataset != dataset:
        raise ValueError(
            "tuned baseline was computed on %s but this study is on %s: binding it would attach "
            "the wrong opponent to these numbers" % (baseline_dataset, dataset)
        )
    baseline_seeds = [int(seed) for seed in (payload.get("seeds") or [])]
    allowed = [int(seed) for seed in (study_seeds or [])]
    if baseline_seeds and allowed and not set(baseline_seeds) & set(allowed):
        raise ValueError(
            "tuned baseline shares no seed with this study (baseline %s vs study %s): a paired "
            "comparison needs the same split" % (baseline_seeds[:4], allowed[:4])
        )
    target = directory / BASELINE_FILENAME
    target.write_bytes(raw)
    digest = {
        key: payload.get(key)
        for key in (
            "dataset",
            "folds",
            "grid_size",
            "baseline_fits_per_seed",
            "study_budget",
            "budget_matched",
            "seeds",
        )
        if payload.get(key) is not None
    }
    digest["cells"] = len(payload.get("cells") or [])
    return {
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "path": str(target),
        "digest": digest,
    }


BRIEF_LANGUAGES = ("zh", "en")

# The brief is a decision document, so its labels are part of its contract: a Chinese-labeled
# brief about an English submission is measured by the English rubric packs as mixed script and
# silently under-scored (#51). Every human-readable string is therefore pulled from one table.
BRIEF_LABELS = {
    "zh": {
        "title": "# 签核决策简报（由包内产物投影，非手写）",
        "package": "- 研究包：`%s`",
        "study_sha": "- study_sha256：`%s`",
        "shape": "- 数据集 / 种子数 / 预算：%s / %d 粒 / %s 次验证评估",
        "provenance": "- 想法溯源：%s",
        "compute": "- 算力口径：evaluations=%s 为唯一判定用度量；wall-clock 仅作披露：%s",
        "signable_heading": "## 可签署比较（区间不含 0 才是可签署内容）",
        "signable_none": "**无**：本包没有任何比较的区间不含 0，因此当前不存在可签署断言。",
        "refused_heading": "## 被判不可判定/拒绝的比较（必须随主张一起写进论文）",
        "refused_none": "无：本包所有比较都判定了方向。",
        "decomposition_heading": "## 分解读数（率指标，受起点与非可比性约束）",
        "reading": "- 读法：%s",
        "caveats_heading": "## 度量警告（原样转录，不改写）",
        "claim_warnings_heading": "## 主张警告（守卫写进记录的原话）",
        "ladder_heading": "## 功效阶梯与复现",
        "ladder_line": "- power_ladder：%s",
        "replication_heading": "## 复现护栏读数",
        "replication_line": "- replication：%s",
        "baseline_heading": "## 绑定的外部强基线",
        "baseline_bound": "- `%s` 已在包内，sha256=`%s`，读数：%s",
        "baseline_unbound": (
            "- 未绑定：本包的主张只与**研究内部的参照格**比较，没有预算对齐的外部强对手。"
            "（`study claim --baseline-file` 可把 `study baseline --output` 的报告绑进包）"
        ),
        "prereg_none": (
            "- 预注册未声明对手（`study-preregistration.json` 无 `baseline` 槽）：对手是在起草主张时"
            "定的而非跑之前定的，closure 记为 warning。"
        ),
        "prereg_declared": "- 预注册声明的对手：%s",
        "prereg_mismatch": (
            "- **不一致**：声明=%r 实绑=%r ⇒ closure 的 baseline.declared 判 blocker；"
            "要么绑声明过的那份，要么在签核前重新注册计划"
        ),
        "prereg_match": "- 一致：声明与实绑相同，事后没有换对手。",
        "path_heading": "## 复现路径（主张 → 命令 → 产物）",
        "rebuild_note": (
            "重建命令（由记录参数拼装；包内不存原始调用，所以这条命令本身是关于可重跑性的主张，"
            "要由 lineage verify 而不是本简报来支撑）："
        ),
        "artifacts": "产物：%s",
        "join": "、",
    },
    "en": {
        "title": "# Signing decision brief (projected from package artifacts, not hand-written)",
        "package": "- study package: `%s`",
        "study_sha": "- study_sha256: `%s`",
        "shape": "- dataset / seeds / budget: %s / %d seeds / %s validation evaluations",
        "provenance": "- idea provenance: %s",
        "compute": "- compute accounting: evaluations=%s is the only judged metric; wall-clock is disclosure only: %s",
        "signable_heading": "## Signable comparisons (an interval must exclude zero)",
        "signable_none": (
            "**None**: no comparison in this package has a 95% interval excluding zero, so nothing "
            "is signable today."
        ),
        "refused_heading": "## Undecidable or refused comparisons (report these with the claim)",
        "refused_none": "None: every comparison in this package decided a direction.",
        "decomposition_heading": "## Decomposition (rate metrics, bounded by start point and non-comparability)",
        "reading": "- reading: %s",
        "caveats_heading": "## Metric caveats (transcribed verbatim, not rewritten)",
        "claim_warnings_heading": "## Claim warnings (verbatim from the drafted record)",
        "ladder_heading": "## Power ladder and replication",
        "ladder_line": "- power_ladder: %s",
        "replication_heading": "## Replication guard readings",
        "replication_line": "- replication: %s",
        "baseline_heading": "## Bound external tuned baseline",
        "baseline_bound": "- `%s` is in the package, sha256=`%s`, readings: %s",
        "baseline_unbound": (
            "- Unbound: this package's claims face only the **in-study reference cell**, with no "
            "budget-matched external opponent (`study claim --baseline-file` binds a report from "
            "`study baseline --output` into the package)."
        ),
        "prereg_none": (
            "- The pre-registration declares no opponent (`study-preregistration.json` has no "
            "`baseline` slot): the opponent was chosen while drafting the claim instead of before "
            "the run, and closure records a warning."
        ),
        "prereg_declared": "- Opponent declared in the pre-registration: %s",
        "prereg_mismatch": (
            "- **Mismatch**: declared=%r bound=%r => closure's baseline.declared is a blocker; "
            "bind the declared file or re-register the plan before signing"
        ),
        "prereg_match": "- Consistent: the declared and bound opponent are the same file; nobody was switched after the results.",
        "path_heading": "## Reproduction path (claim -> command -> artifacts)",
        "rebuild_note": (
            "Rebuilt command (assembled from recorded parameters; the package stores no original "
            "invocation, so this line is itself a claim about re-runnability that lineage verify, "
            "not this brief, has to support):"
        ),
        "artifacts": "Artifacts: %s",
        "join": ", ",
    },
}


def _non_primary_decidable(evidence: Dict[str, Any]) -> list:
    """Metrics the package decided that the primary-metric signability path never looks at.

    Signable/refused are derived from ``evidence["comparison"]``, which carries only the primary
    metric, so a package whose registered analysis names a second metric used to print "nothing in
    this package can be signed" while a decidable interval for that metric sat in the same file
    (measured on memory_tradeoff_iris: best_score +0.02951 CI[+0.01685,+0.04218] was decidable and
    invisible to the brief).
    """
    primary = str(evidence.get("primary_metric") or "")
    rows = []
    contrasts = (evidence.get("decomposition") or {}).get("contrasts_vs_reference") or []
    for cell in contrasts:
        for key, value in cell.items():
            if not str(key).startswith("paired_interval_") or not isinstance(value, dict):
                continue
            metric = str(key).replace("paired_interval_", "")
            if metric == primary:
                continue
            low, high = value.get("ci95_low"), value.get("ci95_high")
            if low is None or high is None:
                continue
            if low > 0 or high < 0:
                rows.append(
                    {
                        "metric": metric,
                        "cell": cell.get("cell_id"),
                        "mean_diff": value.get("mean_diff"),
                        "ci95": [low, high],
                    }
                )
    return rows


def _comparison_reading(row: Dict[str, Any], reference_cell: str) -> str:
    """Say what a sign actually means, because "positive" alone was read as "hypothesis supported".

    Only a cell-vs-reference comparison can beat or lose to the reference; an interaction contrast
    is a difference-of-differences, so calling its sign a win or a loss against a cell is false.
    """
    state = row.get("state")
    comparator = str(row.get("comparator") or "")
    if comparator and reference_cell and comparator == reference_cell:
        if state == "positive":
            return "beats the declared reference cell"
        if state == "negative":
            return "loses to the declared reference cell"
        return "undecidable against the declared reference cell"
    if state in ("positive", "negative"):
        return "%s contrast, %s zero (not a cell-vs-reference comparison)" % (
            comparator or "interaction", "above" if state == "positive" else "below",
        )
    return "undecidable"


def build_study_brief(
    study_dir: Path,
    output: Optional[Path] = None,
    language: str = "zh",
) -> Dict[str, Any]:
    """Render the human decision brief for a study package, from package artifacts only.

    The signing brief used to be hand-written markdown, which is how a decision document drifts
    from the numbers it is supposed to be reading: every value here is projected from
    study-evidence.json / study-spec.json / tuned-baseline.json, and the reproduction command is
    rebuilt from recorded parameters and labelled as a rebuild.

    ``language`` picks the label set only; it never changes a number, a verdict or a hash, so the
    zh and en briefs of one package are two renderings of the same evidence.
    """
    lang = str(language or "zh").strip().lower()
    if lang not in BRIEF_LANGUAGES:
        raise ValueError("unknown brief language %r; expected one of %s" % (language, "/".join(BRIEF_LANGUAGES)))
    directory = Path(study_dir)
    evidence = read_json(directory / "study-evidence.json")
    if not isinstance(evidence, dict):
        raise ValueError("study-evidence.json is missing or unreadable: " + str(directory))
    spec = read_json(directory / "study-spec.json") or {}
    dataset = str(evidence.get("dataset") or "")
    seeds = [int(seed) for seed in (evidence.get("seeds") or [])]
    verdicts = comparison_verdicts(evidence)
    signable = [row for row in verdicts if row["state"] in ("positive", "negative")]
    refused = [row for row in verdicts if row["state"] not in ("positive", "negative")]
    provenance = origin_state(directory)
    replication = replication_context(directory)
    decomposition = evidence.get("decomposition") or {}

    baseline_path = directory / BASELINE_FILENAME
    baseline_sha = ""
    baseline_digest: Dict[str, Any] = {}
    if baseline_path.is_file():
        raw = baseline_path.read_bytes()
        baseline_sha = hashlib.sha256(raw).hexdigest()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError:
            payload = {}
        if isinstance(payload, dict):
            baseline_digest = {
                key: payload.get(key)
                for key in (
                    "dataset",
                    "folds",
                    "grid_size",
                    "baseline_fits_per_seed",
                    "study_budget",
                    "budget_matched",
                )
                if payload.get(key) is not None
            }

    command_parts = ["python -m research_agent study search", "--dataset %s" % (dataset or "<dataset>")]
    if seeds:
        command_parts.append("--seeds %s" % ",".join(str(seed) for seed in seeds))
    if evidence.get("budget"):
        command_parts.append("--budget %s" % evidence.get("budget"))
    design = spec.get("design") or {}
    for factor in sorted(design):
        levels = design.get(factor) or []
        if len(levels) > 1:
            command_parts.append("--factors %s=%s" % (factor, ",".join(str(item) for item in levels)))
    if baseline_sha:
        command_parts.append("(bind the tuned reference with: study claim --baseline-file %s)" % BASELINE_FILENAME)
    claim_command = " ".join(command_parts)

    L = BRIEF_LABELS[lang]
    lines = [
        L["title"],
        "",
        L["package"] % directory.name,
        L["study_sha"] % str(evidence.get("study_sha256") or "")[:16],
        L["shape"] % (dataset or "?", len(seeds), evidence.get("budget")),
        L["provenance"] % provenance["state"],
        L["compute"]
        % (
            evidence.get("budget"),
            json.dumps(
                {
                    key: (spec.get("environment") or {}).get(key)
                    for key in ("python", "sklearn", "numpy", "cpu_logical", "study_wall_seconds")
                },
                ensure_ascii=False,
            ),
        ),
        "",
        L["signable_heading"],
        "",
    ]
    if signable:
        lines.append("| comparison | comparator | mean_diff | 95% CI | state |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in signable:
            ci = row.get("ci95") or [None, None]
            lines.append(
                "| %s | %s | %s | [%s, %s] | %s |"
                % (row["comparison"], row["comparator"], row["mean_diff"], ci[0], ci[1], row["state"])
            )
    else:
        lines.append(L["signable_none"])
    lines += ["", L["refused_heading"], ""]
    if refused:
        lines.append("| comparison | mean_diff | 95% CI | reason |")
        lines.append("| --- | --- | --- | --- |")
        for row in refused:
            ci = row.get("ci95") or [None, None]
            lines.append(
                "| %s | %s | [%s, %s] | %s |"
                % (row["comparison"], row["mean_diff"], ci[0], ci[1], row.get("reason") or "")
            )
    else:
        lines.append(L["refused_none"])
    if decomposition:
        lines += ["", L["decomposition_heading"], ""]
        for key in sorted(decomposition):
            if key == "reading":
                continue
            lines.append("- %s = %s" % (key, decomposition.get(key)))
        if decomposition.get("reading"):
            lines.append(L["reading"] % decomposition["reading"])
    if (evidence.get("metric_caveats") or []):
        lines += ["", L["caveats_heading"], ""]
        for caveat in evidence.get("metric_caveats") or []:
            lines.append("- %s" % caveat)
    # The guard writes its judgement into the drafted record, and a warning nobody reads at the
    # moment of signing is not a warning: quote the record's own warnings into the brief.
    drafted = read_json(directory / "claim.json") or read_json(directory / "claim-draft.json") or {}
    claim_warnings = [str(item) for item in (drafted.get("warnings") or []) if str(item).strip()]
    if claim_warnings:
        lines += ["", L["claim_warnings_heading"], ""]
        for note in claim_warnings:
            lines.append("- %s" % note)
    ladder = evidence.get("power_ladder") or {}
    if ladder:
        lines += ["", L["ladder_heading"], ""]
        lines.append(L["ladder_line"] % json.dumps(ladder, ensure_ascii=False)[:600])
    lines += [
        "",
        L["replication_heading"],
        "",
        L["replication_line"] % json.dumps(
            {key: value for key, value in (replication or {}).items() if key != "packages"},
            ensure_ascii=False,
        )[:700],
        "",
        L["baseline_heading"],
        "",
    ]
    if baseline_sha:
        lines.append(
            L["baseline_bound"]
            % (BASELINE_FILENAME, baseline_sha[:16], json.dumps(baseline_digest, ensure_ascii=False))
        )
    else:
        lines.append(L["baseline_unbound"])
    # who the opponent was declared to be, next to who it actually is: the ordering is the point
    prereg = read_json(directory / "study-preregistration.json") or {}
    declared = prereg.get("baseline") if isinstance(prereg.get("baseline"), dict) else None
    if declared is None:
        lines.append(L["prereg_none"])
    else:
        declared_file = (
            "" if str(declared.get("kind") or "") == "none" else str(declared.get("file") or "")
        )
        bound_file = BASELINE_FILENAME if baseline_sha else ""
        lines.append(L["prereg_declared"] % json.dumps(declared, ensure_ascii=False))
        if declared_file != bound_file:
            lines.append(L["prereg_mismatch"] % (declared_file, bound_file))
        else:
            lines.append(L["prereg_match"])
    artifacts = L["join"].join(["`study.json`", "`study-evidence.json`", "`study-spec.json`"])
    if baseline_sha:
        artifacts += L["join"] + "`%s`" % BASELINE_FILENAME
    lines += [
        "",
        L["path_heading"],
        "",
        L["rebuild_note"],
        "",
        "```",
        claim_command,
        "```",
        "",
        L["artifacts"] % artifacts,
    ]
    # An English label set does not make the artifact English: the plan and the caveats are quoted
    # verbatim (#44), and they were authored in whatever language the human who wrote them used.
    # So the brief discloses which of its own fields carry another script instead of pretending
    # the rendering is monolingual — measured: one Chinese `baseline.why` line put the English
    # brief at 22.8% CJK tokens, which the English rubric packs read as mixed script.
    foreign: list = []
    if lang == "en":
        declared_baseline = prereg.get("baseline") if isinstance(prereg.get("baseline"), dict) else {}
        for field_name, value in (
            ("preregistration.question", prereg.get("question")),
            ("preregistration.hypothesis", prereg.get("hypothesis")),
            ("preregistration.analysis", prereg.get("analysis")),
            ("preregistration.decision_rule", prereg.get("decision_rule")),
            ("preregistration.baseline.why", (declared_baseline or {}).get("why")),
            ("metric_caveats", " ".join(evidence.get("metric_caveats") or [])),
            ("decomposition.reading", (decomposition or {}).get("reading")),
        ):
            if isinstance(value, str) and any("\u4e00" <= char <= "\u9fff" for char in value):
                foreign.append(field_name)
        if foreign:
            lines += [
                "",
                "## Script disclosure",
                "",
                "- labels are English, but %d recorded field(s) were authored in another script and "
                "are quoted verbatim: %s. Rewriting them here would make the decision document "
                "disagree with the evidence it reports, so the mixture is disclosed, not hidden."
                % (len(foreign), ", ".join(foreign)),
            ]
    markdown = "\n".join(lines) + "\n"
    if output:
        handle = Path(output)
        with open(str(handle), "w", encoding="utf-8", newline="\n") as stream:
            stream.write(markdown)
    # The markdown table prints each row's state, but a host reading structuredContent saw only
    # names: "4 signable, 0 refused" read as good news on a package that contradicted its own
    # hypothesis. `state` is relative to the DECLARED reference cell (design order picks it), so
    # "positive" means "this cell beat the reference" - it is never a statement that the registered
    # hypothesis held. Measured: this package's reference cell was the treated arm, so three
    # "positive" rows actually said the reference lost by 0.098-0.115.
    reference_cell = str(spec.get("reference_cell") or "")
    signable_states = {row["comparison"]: row.get("state") for row in signable}
    state_counts = {
        "positive": sum(1 for row in signable if row.get("state") == "positive"),
        "negative": sum(1 for row in signable if row.get("state") == "negative"),
    }
    relative_to_reference = [
        {
            "comparison": row["comparison"],
            "comparator": row.get("comparator"),
            "mean_diff": row.get("mean_diff"),
            "state": row.get("state"),
            "reading": _comparison_reading(row, reference_cell),
        }
        for row in signable
    ]
    if not signable:
        direction_reading = "no decidable comparison; nothing in this package can be signed"
        if _non_primary_decidable(evidence):
            direction_reading = (
                "nothing is signable on the primary metric %s, but %d interval(s) on another metric "
                "in this same package exclude zero; signability is derived from the primary metric "
                "only, so this is a scope limit of the brief, not a finding of no effect"
                % (evidence.get("primary_metric"), len(_non_primary_decidable(evidence)))
            )
    else:
        direction_reading = (
            "%d decidable comparison(s) relative to reference cell %s: %d beat it, %d lost to it. "
            "This is not a verdict about the registered hypothesis, which is recorded as prose; a "
            "human has to read the hypothesis against these signs before signing anything"
            % (len(signable), reference_cell or "?", state_counts["positive"], state_counts["negative"])
        )
    from datetime import datetime, timezone

    from .paths import build_info

    return {
        "schema_version": "study-brief-0.4",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_fingerprint": str(build_info().get("fingerprint") or ""),
        "read_only": True,
        "base": "%d signable comparison(s) of %d recorded, over %d paired seed(s), one dataset (%s)"
        % (len(signable), len(signable) + len(refused), len(seeds), dataset or "?"),
        "provenance": {
            "language": lang,
            "foreign_script_fields": list(foreign),
            "origin_state": provenance["state"],
            "baseline_bound": bool(baseline_sha),
        },
        "language": lang,
        "foreign_script_fields": foreign,
        "study_dir": str(directory),
        "dataset": dataset,
        "seeds": len(seeds),
        "budget": evidence.get("budget"),
        "reference_cell": reference_cell,
        "signable_comparisons": [row["comparison"] for row in signable],
        "signable_states": signable_states,
        "state_counts": state_counts,
        "comparisons_relative_to_reference": relative_to_reference,
        "direction_reading": direction_reading,
        "decidable_outside_primary_metric": _non_primary_decidable(evidence),
        "refused_comparisons": [row["comparison"] for row in refused],
        "baseline_bound": bool(baseline_sha),
        "baseline_sha256": baseline_sha,
        "origin_state": provenance["state"],
        "reproduction_command": claim_command,
        "markdown": markdown,
        "output": str(Path(output)) if output else "",
        "boundary": (
            "a read-only projection of the package: it is not a claim, not a signature and not "
            "evidence; the reproduction command is rebuilt from recorded parameters, so it is a "
            "claim about re-runnability that lineage verify, not this brief, has to support; "
            "signable/refused are computed from the primary metric only, so an empty signable list "
            "does not mean no effect was detected - read "
            "decidable_outside_primary_metric before concluding"
        ),
    }


# Direction words are only read to catch a sentence that contradicts its own assertions, never to
# rewrite one. Both scripts are listed because the corpus and the claims are bilingual (#50/#63).
_UP_WORDS = (
    "提升", "提高", "增加", "改善", "更好", "变好",
    "improve", "increas", "raise", "higher", "gain", "better",
)
_DOWN_WORDS = (
    "降低", "减少", "下降", "变差", "更差", "代价", "牺牲",
    "hurt", "reduc", "decreas", "lower", "worse", "cost", "sacrific",
)

FACTOR_KEYWORDS = {
    "operators": ("算子", "operator"),
    "gate": ("门控", "gate"),
    "memory": ("记忆", "memory"),
    "archive_window": ("档案窗口", "archive_window"),
    "archive": ("档案", "archive"),
    "parent_selection": ("父代", "parent"),
    "min_delta": ("最小改进", "min_delta"),
    "root": ("起点", "root"),
}


def _named_factors(statement: str) -> set:
    text = str(statement or "").lower()
    named = set()
    for factor, keywords in FACTOR_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text:
                named.add(factor)
                break
    if "archive_window" in named:
        named.discard("archive")
    return named


def statement_subject_check(
    statement: str, design: Dict[str, Any], assertions: List[Any], profile_factors: Optional[Dict[str, Any]] = None
):
    """Refuse a claim about a factor this package never varied, and warn when it names none.

    Measured on a real draft: a statement written as 收窄变异算子空间降低了单位验证算力的改进率
    carried assertions about memory and gate, because the design held ``operators`` at one level
    and assertion selection only asked whether an interval excluded zero. Signing that sentence
    would bind a human to a claim the package can neither support nor refute.

    Levels come from the declared design first and fall back to the profile's factor list, so a
    default run (whose declared design is empty because nothing was overridden) is still read as
    varying the controls the profile offers.
    """
    merged = dict(profile_factors or {})
    merged.update(design or {})
    levels = {str(key): value for key, value in merged.items() if isinstance(value, list)}
    varied = {key for key, value in levels.items() if len(value) > 1}
    fixed = {key for key, value in levels.items() if len(value) == 1}
    named = _named_factors(statement)
    if not named:
        if not varied:
            return "", ""
        return "", (
            "the statement names none of the factors this design varies (%s); read it as a "
            "mechanism sentence, not as what these assertions test" % ", ".join(sorted(varied))
        )
    dead = sorted(named & fixed)
    if dead:
        return (
            "the statement is about %s, but this design holds %s at a single level: the package "
            "contains no comparison over it, so these numbers can neither support nor refute it. "
            "Vary it in the design (--factors) and re-run, or rewrite the statement about the "
            "factors actually varied (%s)."
            % (", ".join(dead), ", ".join(dead), ", ".join(sorted(varied)) or "none")
        ), ""
    covered = set()
    for assertion in assertions:
        tail = str(getattr(assertion, "metric", "") or "").rsplit(".", 1)[-1]
        for factor in named:
            if factor in tail:
                covered.add(factor)
    missing = sorted(named - covered)
    if missing:
        return (
            "the statement is about %s, but no decidable comparison in this package covers it; "
            "the assertions here decide %s. Narrow the statement to what was decided, or raise "
            "seeds/budget until it is."
            % (
                ", ".join(missing),
                ", ".join(sorted({str(getattr(a, "metric", "") or "").rsplit(".", 1)[-1] for a in assertions})),
            )
        ), ""
    return "", ""


def statement_arm_disclosure(statement: str, verdicts: List[Dict[str, Any]]) -> str:
    """Name the arms over each quoted factor that this package leaves undecided.

    Factor coverage is not arm coverage. A sentence about memory alone passes a guard that only
    asks whether some memory comparison excludes zero, and on three of four environments the
    memory-alone arm is undecided while memory-plus-gate is decided negative: the same words then
    travel across packages whose evidence says different things. The machine still does not
    rewrite the human's sentence, it just refuses to let the gap stay invisible.
    """
    named = _named_factors(statement)
    if not named or not verdicts:
        return ""
    lines: List[str] = []
    for factor in sorted(named):
        arms = [
            (str(row.get("comparison") or ""), str(row.get("state") or ""))
            for row in verdicts
            if factor in str(row.get("comparison") or "")
        ]
        if not arms:
            continue
        decided = sorted(name for name, state in arms if state in ("positive", "negative"))
        open_arms = sorted(name for name, state in arms if state not in ("positive", "negative"))
        if decided and open_arms:
            lines.append(
                "%s: decided in %s but still undecided in %s" % (factor, ", ".join(decided), ", ".join(open_arms))
            )
    if not lines:
        return ""
    return (
        "the statement names a factor, not an arm: %s. A sentence about one arm of a factor is "
        "not covered by a decision about another arm, so read the assertion list against this "
        "line before signing." % "; ".join(lines)
    )


def statement_direction_note(statement: str, assertions: List[Any]) -> str:
    """Warn when the sentence points one way and the derived assertions point the other.

    Comparators come from the measured interval, so they cannot misstate direction; the prose can.
    The #65 guard asked only which factors a statement names, so "memory improves efficiency" could
    be signed next to an assertion reading `memory_on_gate_off < 0`. Advisory only: rewriting a
    human's claim sentence is not this tool's call, and blocking on word lists would refuse
    legitimate mechanism prose.
    """
    text = str(statement or "").lower()
    up = any(word in text for word in _UP_WORDS)
    down = any(word in text for word in _DOWN_WORDS)
    if up == down or not assertions:
        return ""
    comparators = {str(getattr(item, "comparator", "") or "") for item in assertions}
    conditions = "; ".join(
        str(getattr(item, "condition", "") or getattr(item, "metric", "")) for item in assertions
    )
    if up and comparators <= {"<"}:
        return (
            "the statement reads as an improvement, but every derived assertion compares less than "
            "zero (%s): re-word the sentence to what was decided, or raise seeds/budget; this tool "
            "will not rewrite a human's claim" % conditions
        )
    if down and comparators <= {">"}:
        return (
            "the statement reads as a cost or decrease, but every derived assertion compares "
            "greater than zero (%s): re-word the sentence to what was decided; this tool will not "
            "rewrite a human's claim" % conditions
        )
    return ""


def build_study_claim(
    study_dir: Path,
    statement: str,
    human_reason: str,
    scope: str,
    sign: bool = False,
    use_replication_guard: bool = True,
    baseline_file: str = "",
) -> Dict[str, Any]:
    """Draft a study claim, and with ``sign`` record the human acceptance of it.

    Drafting is inert. Signing is the human act itself — it only happens because a person
    ran the command with a reason, mirroring ``run claim`` / ``experiment claim``. Once
    signed, ``writing_pack`` admits the assertion values as reportable result numbers.
    """
    directory = Path(study_dir)
    evidence = read_json(directory / "study-evidence.json")
    if not isinstance(evidence, dict):
        raise ValueError("study-evidence.json is missing or unreadable: " + str(directory))
    provenance = origin_state(directory)
    if provenance["state"] == "stale":
        raise ValueError(
            "study-origin.json no longer describes this study: the package was re-run or edited "
            "after the idea was executed. Re-run `study from-idea` (or restore the design the "
            "idea declared) before drafting a claim; these numbers must not be attached to an "
            "idea they no longer test."
        )
    dataset = str(evidence.get("dataset") or "")
    split = decidable_assertions(evidence, dataset)
    assertions: List[ClaimAssertion] = split["assertions"]
    replication = replication_context(directory)
    replication["guard_enabled"] = bool(use_replication_guard)
    if sign and not use_replication_guard:
        raise ValueError(
            "the counterfactual arm exists to measure what the guard prevents; it cannot produce a "
            "signed claim. Re-run with the guard on to sign."
        )
    overturned = (
        {str(item["comparison"]) for item in replication.get("overturned") or []}
        if use_replication_guard
        else set()
    )
    if overturned:
        kept: List[ClaimAssertion] = []
        for assertion in assertions:
            name = next(
                (
                    item
                    for item in overturned
                    if str(assertion.metric).endswith("." + item)
                ),
                None,
            )
            if name is None:
                kept.append(assertion)
                continue
            detail = next(
                item for item in replication["overturned"] if item["comparison"] == name
            )
            split["rejected"].append(
                {
                    "comparison": name,
                    "reason": OVERTURNED,
                    "detail": detail,
                }
            )
        assertions = kept
        if not assertions:
            raise ValueError(
                "every comparison this package decided was not reproduced by a higher-power "
                "study on the same dataset (%s); nothing here is signable. Cite the higher-power "
                "package instead, or re-run this one at that power."
                % ", ".join(sorted(overturned))
            )
    if not assertions:
        raise ValueError(
            "no comparison in this study has an interval excluding zero; nothing is "
            "signable. Increase seeds/budget or narrow the claim to a mechanism check."
        )
    study_spec = read_json(directory / "study-spec.json") or {}
    subject_refusal, subject_warning = statement_subject_check(
        statement,
        study_spec.get("design") or {},
        assertions,
        profile_factors=(study_spec.get("profile") or {}).get("factors") or {},
    )
    if subject_refusal:
        raise ValueError(subject_refusal)
    arm_note = statement_arm_disclosure(statement, comparison_verdicts(evidence))
    direction_note = statement_direction_note(statement, assertions)
    baseline = _bind_baseline(directory, baseline_file, dataset, evidence.get("seeds")) if (
        baseline_file or ""
    ) else {}
    baseline_sha = str(baseline.get("sha256") or "")
    claim = ClaimRecord(
        claim_id="CLM-STUDY-"
        + hashlib.sha256((statement + dataset + str(evidence.get("study_sha256", "")) + baseline_sha).encode("utf-8")).hexdigest()[:10],
        statement=statement,
        evidence_refs=[
            "study.json#%s" % str(evidence.get("study_sha256", ""))[:12],
            "study-evidence.json#%s" % str(evidence.get("evidence_sha256", ""))[:12],
            "study-spec.json#%s" % str(evidence.get("study_spec_sha256", ""))[:12],
        ]
        + (
            ["study-origin.json#%s" % provenance["origin_sha256"][:12]]
            if provenance["state"] == "bound"
            else []
        )
        + (
            ["%s#%s" % (BASELINE_FILENAME, baseline_sha[:12])]
            if baseline_sha
            else []
        ),
        scope=scope,
        status="draft",
        human_reason=human_reason,
        created_at=now_iso(),
        warnings=[
            "study evidence is an analogue over pipeline configurations: " + PROVENANCE_BOUNDARY,
            "intervals are exploratory: no significance claim, no multiple-comparison correction",
        ]
        + [note for note in (subject_warning, arm_note, direction_note) if note]
        + (
            []
            if provenance["state"] == "bound"
            else [
                "no study-origin.json is bound to this package: the claim states numbers without "
                "naming the idea they were produced to test"
            ]
        )
        + (
            [
                "bound external reference: %s folds on %s used %s fits per seed against a study "
                "budget of %s (budget_matched=%s), so the comparison is with a tuned opponent "
                "that spent a stated amount of compute"
                % (
                    baseline["digest"].get("folds"),
                    baseline["digest"].get("dataset"),
                    baseline["digest"].get("baseline_fits_per_seed"),
                    baseline["digest"].get("study_budget"),
                    baseline["digest"].get("budget_matched"),
                )
            ]
            if baseline
            else [
                "no tuned baseline is bound: these numbers are compared only with the reference "
                "cell inside this study, not with a strong external opponent"
            ]
        ),
        claim_type="numerical",
        assertions=assertions,
        verification={
            "schema_version": STUDY_CLAIM_SCHEMA,
            "dataset": dataset,
            "seeds": evidence.get("seeds"),
            "budget": evidence.get("budget"),
            "study_sha256": evidence.get("study_sha256", ""),
            "study_spec_sha256": evidence.get("study_spec_sha256", ""),
            "baseline_sha256": baseline_sha,
            "baseline_digest": dict(baseline.get("digest") or {}),
            "decomposition": evidence.get("decomposition", {}),
            "not_signable": split["rejected"],
            "replication": replication,
            "idea_provenance": {
                "state": provenance["state"],
                "idea_id": provenance.get("idea_id", ""),
                "origin_sha256": provenance.get("origin_sha256", ""),
                "falsification": provenance.get("falsification", ""),
            },
            "signing_rule": "only comparisons whose 95% interval excludes zero became assertions",
        },
    )
    payload = asdict(claim)
    if sign:
        payload["status"] = "supported"
        payload["signed_by"] = "human-cli"
    output = directory / (
        "claim.json"
        if sign
        else ("claim-draft.json" if use_replication_guard else "claim-draft-unguarded.json")
    )
    write_json_atomic(output, payload)
    return {
        "claim_file": str(output),
        "claim_id": claim.claim_id,
        "status": payload["status"],
        "warnings": list(claim.warnings),
        "signed": bool(sign),
        "signable_assertions": len(assertions),
        "rejected_comparisons": split["rejected"],
        "idea_provenance": {
            "state": provenance["state"],
            "idea_id": provenance.get("idea_id", ""),
        },
        "tuned_baseline": {
            "bound": bool(baseline_sha),
            "path": str(baseline.get("path") or ""),
            "sha256": baseline_sha,
        },
        "next": (
            "writing pack now admits these numbers as allowed_result_numbers; run "
            "study closure to check the chain"
            if sign
            else "sign with `study claim --sign` (a human act) or run study closure to see "
                 "the chain blocked at claim.signed"
        ),
        "boundary": (
            "the draft is not a signature; signing records a human acceptance of this "
            "statement and nothing else, and closure/export remain separate steps"
        ),
    }
