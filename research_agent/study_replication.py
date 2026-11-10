"""Cross-dataset replication over already-executed study packages (read-only).

A study package decides something on one dataset. Reviewers do not accept that as a general
finding, and neither does this module: it aligns packages that share a *design* and reports how
many datasets actually decide the comparison, using only the intervals already on disk. It never
re-runs anything, never invents a statistic, and never lets agreement upgrade a comparison that
was undecidable on its own.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .storage import read_json, write_json_atomic
from .study_claims import comparison_verdicts

REPLICATION_SCHEMA = "study-replication-0.5"
REPLICATION_BOUNDARY = (
    "agreement across datasets is a count, not a test: it cannot create a finding, cannot turn an "
    "undecidable comparison into a result, and says nothing about datasets that are not listed here; "
    "it is also per-metric - `comparisons` covers the primary metric and `secondary_metrics` each "
    "other measured quantity, and one deciding while the other is undecided is two separate "
    "replications, never one verdict"
)

DECIDED = ("positive", "negative")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    """A package that cannot be read is not evidence.

    Sibling scanning walks directories that other processes may be creating or deleting (tests use
    temporary roots), so an unreadable or vanished package must be skipped, not crash the scan.
    """
    try:
        loaded = read_json(path)
    except OSError:
        return None
    return loaded if isinstance(loaded, dict) else None


def design_labels(design: Dict[str, Any]) -> Dict[str, List[str]]:
    """A design as text levels, so a spec on disk and a package in memory can be compared."""
    return {
        str(factor): [str(level) for level in (levels or [])]
        for factor, levels in design.items()
    }


def comparable_design(design: Dict[str, Any]) -> Dict[str, List[str]]:
    """The part of a design that separates one experiment from another.

    A single-level factor pinned at its incumbent level is dropped: when `parent_selection`
    entered the registry, packages written before it existed never declare it, while new ones
    declare it at `uniform` — the same experiment. Keeping it in the key would start a new evidence
    epoch every time a factor is added, so older packages would stop replicating newer ones and the
    replication guard would go blind across the boundary (measured: a held-out iris package landed
    in `unreplicated` next to five iris packages of the same effective design).

    A fixed factor that has *left* its incumbent level is a different experiment and stays in the
    key (`operators=feature_only` must not merge with `operators=all`).
    """
    from .search_lab import INCUMBENT_LEVEL

    labels = design_labels(design)
    kept: Dict[str, List[str]] = {}
    for factor, levels in labels.items():
        incumbent = INCUMBENT_LEVEL.get(factor)
        if incumbent is not None:
            incumbent = str(incumbent)
        if len(levels) == 1 and incumbent is not None and levels[0] == incumbent:
            continue
        kept[factor] = levels
    return dict(sorted(kept.items()))


def _secondary_verdicts(evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Intervals this package decided on a metric other than the primary one.

    ``comparison_verdicts`` reads ``evidence["comparison"]``, which carries only the primary metric,
    so a design registered on two metrics got replicated as "0 datasets decided" on the side that
    actually decided (measured on the four memory_tradeoff packages: best_score intervals excluded
    zero in 4/4 environments while the group reported status=undecided). The sign keeps the same
    base as the primary rows: the cell minus the reference cell it was compared against.
    """
    primary = str(evidence.get("primary_metric") or "")
    rows: List[Dict[str, Any]] = []
    for cell in (evidence.get("decomposition") or {}).get("contrasts_vs_reference") or []:
        for key, value in cell.items():
            if not str(key).startswith("paired_interval_") or not isinstance(value, dict):
                continue
            metric = str(key).replace("paired_interval_", "")
            if metric == primary:
                continue
            low, high = value.get("ci95_low"), value.get("ci95_high")
            if low is None or high is None:
                state = "undecidable"
            elif low > 0:
                state = "positive"
            elif high < 0:
                state = "negative"
            else:
                state = "undecidable"
            rows.append(
                {
                    "metric": metric,
                    "comparison": cell.get("cell_id"),
                    "state": state,
                    "mean_diff": value.get("mean_diff"),
                    "ci95": [low, high],
                }
            )
    return rows


def load_package(directory: Path) -> Optional[Dict[str, Any]]:
    """One executed study, shaped for alignment. Returns None when the directory is not a study."""
    spec = _read_json(directory / "study-spec.json")
    evidence = _read_json(directory / "study-evidence.json")
    if not spec or not evidence:
        return None
    design = spec.get("design") if isinstance(spec.get("design"), dict) else {}
    return {
        "directory": directory.name,
        "dataset": str(evidence.get("dataset") or spec.get("dataset") or ""),
        "design": design_labels(design),
        "metric": str(evidence.get("primary_metric") or ""),
        "budget": evidence.get("budget"),
        "min_delta": evidence.get("min_delta"),
        "seeds": len(evidence.get("seeds") or []),
        # The seeds themselves, not just their count: an arbiter that re-runs the offered sample
        # with more data is correlated evidence, and a reader is entitled to know that.
        "seed_set": sorted(int(item) for item in (evidence.get("seeds") or [])),
        "underpowered": bool(evidence.get("underpowered")),
        "study_spec_sha256": str(evidence.get("study_spec_sha256") or spec.get("study_sha256") or ""),
        "comparisons": comparison_verdicts(evidence),
        "secondary": _secondary_verdicts(evidence),
    }


def comparability_key(package: Dict[str, Any]) -> str:
    """What has to match before two packages may be called replications of one another.

    Seed count is deliberately excluded: power may differ per dataset and that is reported, not
    hidden. Budget, min_delta, metric and the design itself are not excluded — a different search
    budget is a different experiment, not a replication of it.
    """
    payload = {
        "design": comparable_design(package["design"]),
        "metric": package["metric"],
        "budget": package["budget"],
        "min_delta": package["min_delta"],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


def _agree(rows: List[Dict[str, Any]], datasets: int) -> Dict[str, Any]:
    decided = [row for row in rows if row["state"] in DECIDED]
    signs = {row["state"] for row in decided}
    if datasets < 2:
        status = "single_dataset"
    elif not decided:
        status = "undecided"
    elif len(signs) > 1:
        status = "conflict"
    elif len(decided) == 1:
        status = "one_dataset_decided"
    else:
        status = "consistent"
    return {
        "status": status,
        "datasets": datasets,
        "decided_in": sorted(row["dataset"] for row in decided),
        "direction": sorted(signs)[0] if len(signs) == 1 else "",
        # Generalising is only allowed when every dataset in the group decides the same way; a
        # single decidable dataset among three is still an anecdote.
        "generalizes": status == "consistent" and len(decided) == datasets,
        "rows": rows,
    }


def _power_ladder(key: str, members: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Keep the strongest package per dataset, and record the rest as a power ladder.

    The same design on the same dataset at two seed counts is not two independent datasets, so it
    must not inflate an agreement count. But that pair is exactly the anecdote-versus-power test,
    so it is reported instead of being thrown away: the higher-power package supersedes the lower
    one for counting, and the pair is what ``overturned`` is derived from.
    """
    by_dataset: Dict[str, List[Dict[str, Any]]] = {}
    for member in members:
        by_dataset.setdefault(str(member["dataset"]), []).append(member)
    representatives: List[Dict[str, Any]] = []
    ladders: List[Dict[str, Any]] = []
    for dataset, runs in sorted(by_dataset.items()):
        runs = sorted(runs, key=lambda item: (int(item["seeds"]), str(item["directory"])))
        representatives.append(runs[-1])
        if len(runs) > 1:
            ladders.append(
                {
                    "design_key": key,
                    "dataset": dataset,
                    "packages": [
                        {
                            "directory": item["directory"],
                            "seeds": item["seeds"],
                            "seed_set": item.get("seed_set"),
                            "states": {
                                row["comparison"]: {
                                    "state": row["state"],
                                    "mean_diff": row.get("mean_diff"),
                                    "ci95": row.get("ci95"),
                                }
                                for row in item["comparisons"]
                            },
                        }
                        for item in runs
                    ],
                }
            )
    return representatives, ladders


def overturn_kind(
    offer_state: str, offered: Any, arbiter_state: str, arbiter_ci: Any
) -> Optional[str]:
    """What the arbiter actually says about the claimed size, not just that it failed to decide.

    "Undecided at higher power" hides a distinction that matters for what a claim may still say:
    an interval that still contains the claimed effect only failed to measure it, while one that
    excludes it is positive evidence that the low-power claim overstates.
    """
    if offer_state not in DECIDED:
        return None
    if arbiter_state in DECIDED:
        return "sign_reversal"
    if arbiter_state != "undecidable":
        return None
    try:
        claimed = float(offered)
        low, high = float(arbiter_ci[0]), float(arbiter_ci[1])
    except (TypeError, ValueError, IndexError):
        return None
    return "arbiter_uninformative" if low <= claimed <= high else "effect_bounded"


def _overturned(ladder: Dict[str, Any], warnings: List[str]) -> List[Dict[str, Any]]:
    """Comparisons a lower-power package decided and the strongest package on that dataset does not.

    This is the machine-detectable form of "we over-claimed on a small sample": the assertion was
    signable at 16 seeds and is undecidable, or of the opposite sign, at 64.
    """
    runs = ladder["packages"]
    strongest = runs[-1]
    if int(runs[0]["seeds"]) == int(strongest["seeds"]):
        warnings.append(
            "design %s dataset %s: %d packages at the same %s seeds — identical controls reproduce "
            "identical numbers, so this pair tests nothing about power"
            % (ladder["design_key"], ladder["dataset"], len(runs), runs[0]["seeds"])
        )
        return []
    found: List[Dict[str, Any]] = []
    # Every weaker run is measured against the strongest one, not just the weakest: a verdict that
    # only survives at mid power is exactly the kind of claim a signing recommendation must not rest
    # on, and comparing endpoints alone let it through.
    for weaker in runs[:-1]:
        for name, low in (weaker["states"] or {}).items():
            high = (strongest["states"] or {}).get(name)
            if not high or low["state"] not in DECIDED:
                continue
            if high["state"] == "undecidable":
                reason = "the interval crosses zero again at higher power: the low-power verdict does not hold"
            elif high["state"] != low["state"]:
                reason = "the sign reverses at higher power"
            else:
                continue
            low_seeds = weaker.get("seed_set")
            high_seeds = strongest.get("seed_set")
            shared = (
                len(set(low_seeds) & set(high_seeds))
                if low_seeds is not None and high_seeds is not None
                else None
            )
            kind = overturn_kind(
                low["state"], low.get("mean_diff"), high["state"], high.get("ci95")
            )
            arbiter_ci = high.get("ci95") or [None, None]
            claimed = low.get("mean_diff")
            bound = None
            if kind == "effect_bounded":
                bound = arbiter_ci[1] if claimed > arbiter_ci[1] else arbiter_ci[0]
            found.append(
                {
                    "design_key": ladder["design_key"],
                    "dataset": ladder["dataset"],
                    "comparison": name,
                    "reason": reason,
                    # How much of the offered sample the arbiter merely re-used: an overturn from a
                    # disjoint seed range is independent evidence, one from a superset is a
                    # re-sampling of the same runs, and the reader cannot tell those apart from a
                    # seed count alone.
                    "shared_seeds": shared,
                    "arbiter_independent": None if shared is None else shared == 0,
                    # What the arbiter says about the size that was claimed, so a blocked assertion
                    # can be re-scoped instead of merely denied.
                    "overturn_kind": kind,
                    "claimed_effect": claimed,
                    "arbiter_bound": bound,
                    "decided_at": {"directory": weaker["directory"], "seeds": weaker["seeds"], "state": low["state"], "mean_diff": low["mean_diff"], "ci95": low["ci95"]},
                    "at_higher_power": {"directory": strongest["directory"], "seeds": strongest["seeds"], "state": high["state"], "mean_diff": high["mean_diff"], "ci95": high["ci95"]},
                }
            )
    return found


def sibling_studies_dirs(studies_dir: Path) -> List[Path]:
    """Every ``<parent>/*/studies`` next to this project, plus this one.

    A verdict overturned by a higher-power study in a sibling project is still overturned: reading
    only the current ``studies/`` let the runtime recommend signing exactly such a verdict. Siblings
    are deterministic (same parent), read-only, and need no new configuration.
    """
    studies_dir = Path(studies_dir)
    found = [studies_dir] if studies_dir.is_dir() else []
    # <project>/studies -> scan <parent-of-project>; anything else -> scan the containing directory.
    parent = studies_dir.parent.parent if studies_dir.name == "studies" else studies_dir.parent
    if parent.is_dir():
        try:
            candidates = sorted(parent.iterdir())
        except OSError:
            candidates = []
        for candidate in candidates:
            candidate_studies = candidate / "studies"
            try:
                if candidate_studies.is_dir() and candidate_studies != studies_dir:
                    found.append(candidate_studies)
            except OSError:
                # A locked, unrelated directory beside the project is not a
                # sibling study. Skipping it keeps this read-only verdict scan
                # deterministic instead of aborting every caller that needs it.
                continue
    return found


def collect_packages(directories: List[Path]) -> List[Dict[str, Any]]:
    """Load every study package under the given roots, dropping byte-identical duplicates.

    The same package is often copied between projects (that is how a ladder gets built by hand); two
    copies of one `study_sha256` are one piece of evidence and must not count twice.
    """
    from .search_lab import code_fingerprint
    from .study_integrity import package_integrity

    packages: List[Dict[str, Any]] = []
    seen: set = set()
    stamp = code_fingerprint()
    for directory in directories:
        if not directory.is_dir():
            continue
        for child in sorted(p for p in directory.iterdir() if p.is_dir()):
            package = load_package(child)
            if not package:
                continue
            marker = package["study_spec_sha256"] or package["directory"]
            if marker in seen:
                continue
            seen.add(marker)
            package["studies_root"] = str(directory.parent.name)
            # Integrity is attached here because this is the only place that still knows the
            # package path; the report itself is deliberately path-free.
            package["integrity"] = package_integrity(child, current_fingerprint=stamp)
            packages.append(package)
    return packages


def _ladder_audit(ladder: Dict[str, Any], overturned: List[Dict[str, Any]]) -> Dict[str, Any]:
    """How many lower-power verdicts a ladder put on the table, and how many did not survive.

    The ratio is the quantity a reader actually wants: of the comparisons this project was able to
    call "decided" at low power, what share stopped being decided (or flipped) once the same design
    was re-run at higher power on the same dataset.
    """
    runs = ladder["packages"]
    strongest = runs[-1]
    decided = 0
    for weaker in runs[:-1]:
        for name, low in (weaker["states"] or {}).items():
            if low["state"] in DECIDED:
                decided += 1
    types: Dict[str, int] = {}
    by_power: Dict[str, int] = {}
    for item in overturned:
        kind = "sign_flip" if "reverses" in item["reason"] else "interval_returns_to_zero"
        types[kind] = types.get(kind, 0) + 1
        key = "%s->%s seeds" % (item["decided_at"]["seeds"], item["at_higher_power"]["seeds"])
        by_power[key] = by_power.get(key, 0) + 1
    return {
        "decided_at_lower_power": decided,
        "overturned": len(overturned),
        "by_type": types,
        "by_power_step": by_power,
        "datasets": {str(ladder["dataset"]): {"decided": decided, "overturned": len(overturned)}},
    }


def _count_by_root(roots: List[str]) -> Dict[str, int]:
    """How many packages each scanned root holds, counted on disk before de-duplication.

    A package records only its directory name, so attributing the de-duplicated list back to a
    root would be guesswork; counting the directories themselves is exact, and the difference
    against the reported total is precisely the copies the de-duplication folded together.
    """
    counts: Dict[str, int] = {}
    for root in [str(item) for item in roots]:
        handle = Path(root)
        counts[root] = len(list(handle.glob("*/study.json"))) if handle.is_dir() else 0
    return counts


def build_replication_report(
    studies_dir: Path,
    *,
    packages: Optional[List[Dict[str, Any]]] = None,
    siblings: bool = False,
    seed_scope: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Group executed studies by design and count how many datasets decide each comparison.

    ``seed_scope`` keeps only packages whose seed set covers the claim's seeds. Without it two
    same-design, same-dataset runs on disjoint seed ranges are silently treated as one evidence
    pool, so a claim for seeds 33-64 could inherit the undecided row of seeds 1-32.
    """
    from .study_integrity import integrity_layers

    studies_dir = Path(studies_dir)
    roots: List[Path] = [studies_dir]
    if packages is None:
        roots = sibling_studies_dirs(studies_dir) if siblings else [studies_dir]
        packages = collect_packages(roots)
    scanned_roots = [str(item) for item in roots]
    loaded = [pkg for pkg in packages if pkg]
    seed_excluded: List[Dict[str, Any]] = []
    if seed_scope:
        scope = {int(item) for item in seed_scope}
        kept = []
        for package in loaded:
            seeds = {int(item) for item in package.get("seed_set") or []}
            if scope <= seeds:
                kept.append(package)
            else:
                seed_excluded.append(
                    {"dataset": package.get("dataset"), "seeds": sorted(seeds)}
                )
        loaded = kept

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for package in loaded:
        groups.setdefault(comparability_key(package), []).append(package)

    replicated: List[Dict[str, Any]] = []
    unreplicated: List[Dict[str, Any]] = []
    ladders: List[Dict[str, Any]] = []
    overturned: List[Dict[str, Any]] = []
    audits: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if seed_excluded:
        warnings.append(
            "seed-scope excluded %d package(s) on disjoint seeds: %s"
            % (
                len(seed_excluded),
                ", ".join(
                    "%s=%s" % (item["dataset"], item["seeds"]) for item in seed_excluded[:6]
                ),
            )
        )
    for key, members in groups.items():
        members, group_ladders = _power_ladder(key, members)
        ladders.extend(group_ladders)
        for ladder in group_ladders:
            ladder_overturned = _overturned(ladder, warnings)
            overturned.extend(ladder_overturned)
            audits.append(_ladder_audit(ladder, ladder_overturned))
        datasets = sorted({str(m["dataset"]) for m in members})
        if len(datasets) < 2:
            unreplicated.append(
                {
                    "design_key": key,
                    "design": members[0]["design"],
                    "datasets": datasets,
                    "packages": [m["directory"] for m in members],
                    "reason": (
                        "only one dataset was executed for this design; replication needs the same "
                        "design on a second dataset"
                        if not group_ladders
                        else "this design exists on one dataset only, but at several seed counts: "
                        "the ladder below compares the powers, it is not a replication"
                    ),
                }
            )
            continue
        by_comparison: Dict[str, List[Dict[str, Any]]] = {}
        for member in members:
            for row in member["comparisons"]:
                by_comparison.setdefault(row["comparison"], []).append(
                    {
                        "dataset": member["dataset"],
                        "package": member["directory"],
                        "state": row["state"],
                        "mean_diff": row.get("mean_diff"),
                        "ci95": row.get("ci95"),
                        "seeds": member["seeds"],
                    }
                )
        secondary_rows: Dict[Any, List[Dict[str, Any]]] = {}
        for member in members:
            for row in member.get("secondary") or []:
                secondary_rows.setdefault((row["metric"], row["comparison"]), []).append(
                    {
                        "dataset": member["dataset"],
                        "package": member["directory"],
                        "state": row["state"],
                        "mean_diff": row.get("mean_diff"),
                        "ci95": row.get("ci95"),
                        "seeds": member["seeds"],
                    }
                )
        secondary: Dict[str, Dict[str, Any]] = {}
        for (metric, name), rows in sorted(secondary_rows.items()):
            secondary.setdefault(metric, {})[str(name)] = _agree(rows, len(datasets))
        seed_counts = sorted({m["seeds"] for m in members})
        if len(seed_counts) > 1:
            warnings.append(
                "design %s: datasets were run with different seed counts (%s); a comparison that "
                "decides on only one of them may reflect that power gap rather than a difference "
                "between the datasets" % (key, ", ".join(str(c) for c in seed_counts))
            )
        primary_results = {
            name: _agree(rows, len(datasets))
            for name, rows in sorted(by_comparison.items())
        }
        primary_all_undecided = bool(primary_results) and all(
            result["status"] == "undecided" for result in primary_results.values()
        )
        if primary_all_undecided:
            for metric in sorted(secondary):
                for name, result in sorted(secondary[metric].items()):
                    if result["decided_in"]:
                        warnings.append(
                            "design %s: the primary metric left every comparison undecided, yet %s "
                            "decided %s in %d of %d dataset(s); read the two metrics as two separate "
                            "replications, not as one verdict"
                            % (key, metric, name, len(result["decided_in"]), len(datasets))
                        )
        replicated.append(
            {
                "design_key": key,
                "design": members[0]["design"],
                "datasets": datasets,
                "packages": {m["dataset"]: m["directory"] for m in members},
                "seed_counts": {m["dataset"]: m["seeds"] for m in members},
                "comparisons": primary_results,
                "secondary_metrics": secondary,
            }
        )

    counts: Dict[str, int] = {}
    for group in replicated:
        for result in group["comparisons"].values():
            counts[result["status"]] = counts.get(result["status"], 0) + 1
    decided_low = sum(int(item["decided_at_lower_power"]) for item in audits)
    by_type: Dict[str, int] = {}
    by_step: Dict[str, int] = {}
    per_dataset: Dict[str, Dict[str, int]] = {}
    for item in audits:
        for key_type, value in item["by_type"].items():
            by_type[key_type] = by_type.get(key_type, 0) + value
        for step, value in item["by_power_step"].items():
            by_step[step] = by_step.get(step, 0) + value
        for dataset, values in item["datasets"].items():
            slot = per_dataset.setdefault(dataset, {"decided": 0, "overturned": 0})
            slot["decided"] += values["decided"]
            slot["overturned"] += values["overturned"]
    return {
        "schema_version": REPLICATION_SCHEMA,
        "studies_dir": str(studies_dir),
        "siblings_included": bool(siblings),
        "scope": {
            "roots": scanned_roots,
            "root_count": len(scanned_roots),
            "packages": len(loaded),
            "packages_on_disk": sum(_count_by_root(scanned_roots).values()),
            "packages_by_root": _count_by_root(scanned_roots),
        },
        "packages": len(loaded),
        "chain_layers": integrity_layers(loaded),
        "replicated": replicated,
        "unreplicated": unreplicated,
        "power_ladders": ladders,
        "overturned": overturned,
        "power_audit": {
            "ladders": len(audits),
            "decided_at_lower_power": decided_low,
            "overturned": len(overturned),
            "reversal_rate": round(len(overturned) / float(decided_low), 4) if decided_low else None,
            "by_type": by_type,
            "by_power_step": by_step,
            "per_dataset": per_dataset,
            "reading": (
                "of %d verdicts this project could call at lower power, %d stopped being decisive or "
                "flipped at higher power; this is the cost of deciding early, measured on the "
                "packages actually on disk" % (decided_low, len(overturned))
            )
            if decided_low
            else "no lower-power verdicts to audit yet",
        },
        "status_counts": counts,
        "warnings": warnings,
        "boundary": REPLICATION_BOUNDARY,
    }


def write_replication_report(report: Dict[str, Any], output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "replication-report.json"
    write_json_atomic(target, report)
    return target
