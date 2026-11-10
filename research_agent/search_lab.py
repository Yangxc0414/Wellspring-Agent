"""Locally executable improvement-search study.

The idea stage keeps producing hypotheses about *search* (archives of prior solutions,
acceptance gates, compute-normalized improvement), while S5 could only fit a fixed model
once on a tabular dataset. That mismatch makes those hypotheses untestable in this system,
so their experiment plans are effectively fiction.

This module gives the runtime a real, deterministic search harness on public tabular data
where the two components the hypotheses talk about can be switched independently:

- ``archive``  whether the population of previously accepted configurations is retained and
  used to seed new proposals, or thrown away after every step (single-retained-best);
- ``gate``     whether a proposal must improve validation score over its parent by more than
  ``min_delta`` to be retained, or is retained unconditionally.

The measured object is what the hypotheses claim: improvements accumulated *per unit of
validation compute*, along the accepted lineage, plus the memory x gate interaction.

Honesty boundary: the entity being improved is a pipeline configuration, not agent source
code. This is a structural analogue of archive-based self-improvement search, not a
reproduction of any published system, and its numbers say nothing about those systems.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "search-study-0.1"

DATASETS = {
    "iris": {"target": "target", "classes": 3},
    "breast_cancer": {"target": "target", "classes": 2},
    "wine": {"target": "target", "classes": 3},
    # 64 features and 10 classes: a genuinely harder search landscape than the three two-/three-
    # class problems, which is what a replication count needs to mean anything.
    "digits": {"target": "target", "classes": 10},
}

CLASSIFIERS = ("logistic", "ridge", "tree", "centroid")

# Which edits the mutation step is allowed to apply. The canonical order matches the
# historical randrange(3) branch order, so the default set reproduces earlier numbers.
OPERATOR_SETS: Dict[str, Tuple[str, ...]] = {
    "all": ("flip_feature", "switch_classifier", "scale_knob"),
    "no_switch": ("flip_feature", "scale_knob"),
    "feature_only": ("flip_feature",),
    "classifier_only": ("switch_classifier",),
    "knob_only": ("scale_knob",),
}
DEFAULT_OPERATORS = OPERATOR_SETS["all"]
ALL_OPERATORS = ("flip_feature", "switch_classifier", "scale_knob")
MIN_MUTATION_OPERATORS = 1

# The design axes a caller may vary. Levels are declared here rather than coded into the
# runner so a user can test other search hypotheses than the memory x gate 2x2.
SEARCH_FACTORS: Dict[str, Dict[str, Any]] = {
    "memory": {
        "kind": "boolean",
        "levels": [False, True],
        "semantics": "accepted configurations are kept as future parents (on) or every "
        "child restarts from the root (off)",
    },
    "gate": {
        "kind": "boolean",
        "levels": [False, True],
        "semantics": "a child is accepted only when it beats its parent by min_delta (on) "
        "or is accepted unconditionally (off)",
    },
    "operators": {
        "kind": "operator_set",
        "levels": sorted(OPERATOR_SETS),
        "semantics": "which mutation operators the search may apply",
    },
    "min_delta": {
        "kind": "number",
        "levels": [0.005, 0.02, 0.05],
        "semantics": "the improvement the acceptance gate requires; only meaningful with gate=on",
    },
    # Which archived configuration the next child mutates from. `uniform` is the incumbent
    # behaviour, so declaring this factor at its first level must reproduce earlier numbers.
    # Selection deliberately draws no randomness in the other levels: two levels then share the
    # same mutation stream, which is what makes the difference attributable to the policy.
    "parent_selection": {
        "kind": "categorical",
        "levels": ["uniform", "best", "round_robin"],
        "semantics": "how the next parent is taken from the archive (uniform random, highest "
        "score, systematic sweep); inert when memory=off because no archive exists",
    },
    # A negative-example archive is not the accepted lineage: it stores rejected mutations and
    # skips a candidate that repeats one. `off` is the incumbent so the historical 2x2 and its
    # random stream are unchanged; declaring the factor at `negative` adds the archive arm.
    "archive": {
        "kind": "categorical",
        "levels": ["off", "negative"],
        "semantics": "rejected mutations are remembered as negative examples and resampled, "
        "so the search can avoid repeating them; inert when gate=off because nothing is rejected",
    },
    # Staleness is a design factor, not just a recorded statistic: `all` recalls every rejected
    # entry, `recent` recalls only entries younger than ARCHIVE_WINDOW evaluations. If the
    # archive's benefit comes from old failures, dropping them should weaken it.
    "archive_window": {
        "kind": "categorical",
        "levels": ["all", "recent"],
        "semantics": "which rejected entries the negative archive may recall (all ages or only "
        "entries younger than the window); inert when archive=off",
    },
    # `random_subset` is the incumbent, so declaring the factor at that level must reproduce
    # earlier numbers exactly. The policy is kept out of the random key: both arms draw the same
    # seed configuration and only the mask is overridden, so the difference is attributable to
    # the starting point rather than to a reshuffled stream.
    "root": {
        "kind": "categorical",
        "levels": ["random_subset", "all_features"],
        "semantics": "where the search starts: a random feature subset with the classifier and "
        "knob drawn at random (incumbent) or every feature present at the start",
    },
}

ARCHIVE_WINDOW = 10
MAX_DESIGN_CELLS = 12

# The level of each factor that means "behaviour as it was before this factor existed". Registry
# order is not decoration: `study_replication.comparable_design` drops single-level factors pinned
# here so that adding a factor does not retire every earlier package, and a test binds each
# incumbent to the runner's own default so the two cannot drift apart.
INCUMBENT_LEVEL = {name: spec["levels"][0] for name, spec in SEARCH_FACTORS.items()}

# Three seeds leave every interval covering zero; the study is cheap, so the default is
# higher and the runner still reports the interval rather than hiding it.
DEFAULT_SEEDS = 8
# Below this many seeds an interval is not interpreted at all: with two paired points the
# variance can be zero, which would collapse the interval onto the point estimate.
MIN_DECISION_SEEDS = 4

PROVENANCE_BOUNDARY = (
    "a deterministic search study on public tabular data: it measures an improvement-search "
    "control loop over pipeline configurations, not agent self-modification; results say "
    "nothing about any published self-improving agent and are not a reproduction"
)


@dataclass
class Configuration:
    """A candidate solution: classifier, feature subset and one knob value."""

    classifier: str
    feature_mask: Tuple[bool, ...]
    knob: float

    def key(self) -> str:
        return "%s|%s|%.4g" % (
            self.classifier,
            "".join("1" if flag else "0" for flag in self.feature_mask),
            self.knob,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classifier": self.classifier,
            "features": sum(1 for flag in self.feature_mask),
            "knob": self.knob,
            "signature": hashlib.sha256(self.key().encode("utf-8")).hexdigest()[:16],
        }


@dataclass
class EvaluatedNode:
    config: Configuration
    score: float
    parent_id: str
    node_id: str
    accepted_by_gate: bool
    evaluations: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "score": round(self.score, 6),
            "accepted_by_gate": self.accepted_by_gate,
            "evaluations": self.evaluations,
            "config": self.config.to_dict(),
        }


def _level_text(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def cell_id_of(controls: Dict[str, Any], order: List[str]) -> str:
    """A stable, readable name for one cell of the design."""
    return "_".join("%s_%s" % (factor, _level_text(controls[factor])) for factor in order)


def default_design() -> Dict[str, List[Any]]:
    """The historical memory x gate 2x2, expressed through the same declarative path."""
    return {"memory": [False, True], "gate": [False, True]}


def normalize_design(
    design: Optional[Dict[str, List[Any]]], min_delta: float
) -> Dict[str, List[Any]]:
    """Validate a caller design against the declared factor space.

    A design is data, but it still has to be checked: an unknown factor or level would
    otherwise silently produce a cell that the runner cannot interpret, and a wide product
    would turn a cheap study into an unbounded one. The first level of every factor is the
    reference cell, so the caller picks its baseline by declaration order, not by a hidden rule.
    """
    requested = dict(design or default_design())
    unknown = sorted(set(requested) - set(SEARCH_FACTORS))
    if unknown:
        raise ValueError(
            "unknown factor(s): %s; available: %s"
            % (", ".join(unknown), ", ".join(sorted(SEARCH_FACTORS)))
        )
    cleaned: Dict[str, List[Any]] = {}
    for factor in sorted(requested):
        spec = SEARCH_FACTORS[factor]
        levels = requested[factor]
        if isinstance(levels, (str, bytes)) or not levels:
            raise ValueError("factor %s needs a non-empty list of levels" % factor)
        values: List[Any] = []
        for level in levels:
            if spec["kind"] == "boolean":
                if isinstance(level, str):
                    level = level.strip().lower() in ("1", "true", "on", "yes")
                values.append(bool(level))
            elif spec["kind"] == "number":
                values.append(float(level))
            else:
                text = str(level).strip()
                if text not in spec["levels"]:
                    raise ValueError(
                        "unknown level '%s' for factor %s; available: %s"
                        % (text, factor, ", ".join(spec["levels"]))
                    )
                values.append(text)
        unique: List[Any] = []
        for value in values:
            if value not in unique:
                unique.append(value)
        if spec["kind"] == "operator_set":
            for value in unique:
                if len(OPERATOR_SETS[value]) < MIN_MUTATION_OPERATORS:
                    raise ValueError("operator set %s has no operators" % value)
        cleaned[factor] = unique
    for factor, spec in SEARCH_FACTORS.items():
        # Unstated factors stay in the design at their first level, so every cell describes a
        # complete control setting and the reference cell is well defined.
        cleaned.setdefault(factor, [spec["levels"][0]])
    if "min_delta" not in requested:
        cleaned["min_delta"] = [float(min_delta)]
    cells = 1
    for values in cleaned.values():
        cells *= len(values)
    if cells > MAX_DESIGN_CELLS:
        raise ValueError(
            "design would run %d cells; the limit is %d to keep a study reproducible in one "
            "sitting" % (cells, MAX_DESIGN_CELLS)
        )
    return cleaned


def reference_controls(design: Dict[str, List[Any]]) -> Dict[str, Any]:
    return {factor: values[0] for factor, values in sorted(design.items())}


def naming_order(design: Dict[str, List[Any]]) -> List[str]:
    """Only the factors that actually vary appear in a cell name.

    A single-level factor is part of the recorded design, not a condition label, so the classic
    2x2 keeps its ``memory_off_gate_on`` names even after new controls were added to the space.
    The memory-then-gate order is fixed because signed claims already cite those names.
    """
    priority = [factor for factor in ("memory", "gate") if factor in design]
    rest = sorted(
        factor
        for factor, values in design.items()
        if len(values) > 1 and factor not in priority
    )
    return priority + rest


def design_cells(design: Dict[str, List[Any]], order: List[str]) -> List[Dict[str, Any]]:
    """Cartesian product of the declared levels, in a deterministic order."""
    combos: List[Dict[str, Any]] = [{}]
    for factor in sorted(design):
        combos = [
            dict(combo, **{factor: level}) for combo in combos for level in design[factor]
        ]
    for combo in combos:
        combo["cell_id"] = cell_id_of(combo, order)
    return combos


def _load_dataset(name: str, seed: int) -> Tuple[Any, Any, Any, Any]:
    """Public tabular data split into a search split and a held-out validation split."""
    from sklearn.model_selection import train_test_split
    from sklearn.datasets import load_digits, load_iris, load_breast_cancer, load_wine

    loader = {
        "iris": load_iris,
        "breast_cancer": load_breast_cancer,
        "wine": load_wine,
        "digits": load_digits,
    }[name]
    bundle = loader()
    x_train, x_valid, y_train, y_valid = train_test_split(
        bundle.data,
        bundle.target,
        test_size=0.3,
        random_state=seed,
        stratify=bundle.target,
    )
    return x_train, x_valid, y_train, y_valid


def _score(
    config: Configuration, x_train, y_train, x_valid, y_valid
) -> float:
    """Validation score for one configuration; every branch is a single fit."""
    from sklearn.preprocessing import StandardScaler

    selected = [index for index, flag in enumerate(config.feature_mask) if flag]
    if not selected:
        return 0.0
    xt = x_train[:, selected]
    xv = x_valid[:, selected]
    scaler = StandardScaler().fit(xt)
    xt = scaler.transform(xt)
    xv = scaler.transform(xv)

    if config.classifier == "logistic":
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(C=config.knob, max_iter=500, random_state=0)
    elif config.classifier == "ridge":
        from sklearn.linear_model import RidgeClassifier

        model = RidgeClassifier(alpha=config.knob)
    elif config.classifier == "tree":
        from sklearn.tree import DecisionTreeClassifier

        # The knob is shared across classifier families; depth must stay >= 1.
        model = DecisionTreeClassifier(
            max_depth=max(1, int(round(config.knob))), random_state=0
        )
    else:
        from sklearn.neighbors import NearestCentroid

        model = NearestCentroid()
    model.fit(xt, y_train)
    return float(model.score(xv, y_valid))


def _mutations(
    config: Configuration,
    n_features: int,
    rng,
    operators: Tuple[str, ...] = DEFAULT_OPERATORS,
) -> Configuration:
    """Small, deterministic edits of one configuration (the 'self-modification' analogue).

    `operators` restricts which edits are allowed; the canonical order of the full set matches
    the historical ``randrange(3)`` branch order, so the default reproduces earlier studies.
    """
    import copy

    allowed = [name for name in ALL_OPERATORS if name in operators]
    if not allowed:
        raise ValueError("no mutation operators allowed")
    child = copy.deepcopy(config)
    action = allowed[rng.randrange(len(allowed))]
    if action == "flip_feature":
        index = rng.randrange(n_features)
        child.feature_mask = tuple(
            (not flag) if position == index else flag
            for position, flag in enumerate(child.feature_mask)
        )
        if sum(1 for flag in child.feature_mask) == 0:
            child.feature_mask = config.feature_mask
    elif action == "switch_classifier":
        child.classifier = rng.choice(CLASSIFIERS)
        if child.classifier == "centroid":
            child.knob = 1.0
    else:
        child.knob = float(getattr(child, "knob", 1.0) * rng.choice([0.5, 2.0]))
        child.knob = min(max(child.knob, 0.01), 32.0)
    return child


def _config_key(config: Configuration) -> Any:
    return (
        tuple(index for index, flag in enumerate(config.feature_mask) if flag),
        str(config.classifier),
        round(float(getattr(config, "knob", 1.0)), 6),
    )


def _seed_configuration(
    n_features: int, rng, root_policy: str = "random_subset"
) -> Configuration:
    if root_policy not in ("random_subset", "all_features"):
        raise ValueError("root policy must be random_subset or all_features")
    mask = tuple(
        bool(index == 0 or rng.random() < 0.6) for index in range(n_features)
    )
    if root_policy == "all_features":
        # the draws above still happen so both arms share one mutation stream
        mask = tuple([True] * n_features)
    return Configuration(
        classifier=rng.choice(CLASSIFIERS), feature_mask=mask, knob=rng.choice([0.1, 1.0, 4.0, 8])
    )


def run_condition(
    dataset: str,
    seed: int,
    budget: int,
    archive: bool,
    gate: bool,
    min_delta: float = 0.005,
    operators: Tuple[str, ...] = DEFAULT_OPERATORS,
    parent_selection: str = "uniform",
    archive_mode: str = "off",
    archive_window: str = "all",
    root_policy: str = "random_subset",
) -> Dict[str, Any]:
    """Run one cell of the design under a fixed evaluation budget.

    The RNG is keyed on the data-and-mutation controls, so cells that differ in those factors are
    different conditions. `parent_selection` is kept out of the key on purpose: two selection levels
    then share one mutation stream (common random numbers), so their difference is attributable to
    the selection policy rather than to a reshuffled random sequence.
    """
    import random

    archive_mode = str(archive_mode or "off")
    if archive_mode not in ("off", "negative"):
        raise ValueError("archive_mode must be off or negative")
    archive_window = str(archive_window or "all")
    if archive_window not in ("all", "recent"):
        raise ValueError("archive_window must be all or recent")
    root_policy = str(root_policy or "random_subset")
    if root_policy not in ("random_subset", "all_features"):
        raise ValueError("root_policy must be random_subset or all_features")
    controls = {
        "memory": bool(archive),
        "gate": bool(gate),
        "min_delta": float(min_delta),
        "operators": list(operators),
        "archive": archive_mode,
        "archive_window": archive_window,
        "root_policy": root_policy,
    }
    rng_controls = dict(controls)
    # Keep the historical random stream byte-for-byte stable: adding factors must not
    # reshuffle the existing 2x2. Only non-incumbent arms get a different key.
    if archive_mode == "off":
        rng_controls.pop("archive", None)
    if root_policy == "random_subset":
        # incumbent arm keeps the historical stream and the historical controls hash
        rng_controls.pop("root_policy", None)
    if archive_window == "all" or archive_mode == "off":
        # The window is inert without a negative archive, so off/all and off/recent must share
        # one stream; otherwise the negative control differs only because of a reshuffled RNG.
        rng_controls.pop("archive_window", None)
    x_train, x_valid, y_train, y_valid = _load_dataset(dataset, seed)
    n_features = int(x_train.shape[1])

    rng = random.Random(
        "%s|%d|%s" % (dataset, seed, json.dumps(rng_controls, sort_keys=True))
    )

    root = _seed_configuration(n_features, rng, root_policy)
    root_score = _score(root, x_train, y_train, x_valid, y_valid)
    evaluations = 1
    root_node = EvaluatedNode(root, root_score, "", "N000", True, evaluations)
    nodes: List[EvaluatedNode] = [root_node]
    # archive=True keeps every accepted configuration as a future starting point;
    # archive=False throws the population away and always restarts from the root.
    population: List[EvaluatedNode] = [root_node]

    improvements = 0
    gate_rejections = 0
    lineage_depth = 0
    rejected_at: Dict[Any, int] = {}
    archive_hits = 0
    archive_ages: List[int] = []

    while evaluations < budget:
        if not archive:
            parent = root_node
        elif parent_selection == "best":
            parent = max(population, key=lambda item: item.score)
        elif parent_selection == "round_robin":
            parent = population[evaluations % len(population)]
        else:
            parent = rng.choice(population)
        child = None
        for _attempt in range(8):
            candidate = _mutations(parent.config, n_features, rng, operators=operators)
            key = _config_key(candidate)
            recall = (
                key in rejected_at
                and (
                    archive_window == "all"
                    or evaluations - rejected_at[key] <= ARCHIVE_WINDOW
                )
            )
            if archive_mode == "negative" and recall:
                archive_hits += 1
                archive_ages.append(evaluations - rejected_at[key])
                continue
            child = candidate
            break
        if child is None:
            # Every resample repeated a rejected configuration; keep the budget fixed and accept
            # the duplicate rather than looping forever.
            child = candidate
        score = _score(child, x_train, y_train, x_valid, y_valid)
        evaluations += 1
        node_id = "N%03d" % len(nodes)
        accepted = (not gate) or (score > parent.score + min_delta)
        node = EvaluatedNode(child, score, parent.node_id, node_id, accepted, evaluations)
        nodes.append(node)
        if accepted:
            if archive:
                population.append(node)
            if score > parent.score + (min_delta if gate else 0.0):
                improvements += 1
        else:
            gate_rejections += 1
            if archive_mode == "negative":
                rejected_at[_config_key(child)] = evaluations

    best = max(nodes, key=lambda item: item.score)
    depth = 0
    cursor = best.node_id
    seen = set()
    by_id = {node.node_id: node for node in nodes}
    while cursor in by_id and cursor not in seen:
        seen.add(cursor)
        depth += 1
        cursor = by_id[cursor].parent_id

    condition = "memory=%s/gate=%s" % (archive, gate)
    if archive_mode != "off":
        condition += "/archive=%s" % archive_mode
    if archive_window != "all":
        condition += "/window=%s" % archive_window
    if root_policy != "random_subset":
        condition += "/root=%s" % root_policy
    return {
        "condition": condition,
        "memory": bool(archive),
        "gate": bool(gate),
        "archive": archive_mode,
        "archive_window": archive_window,
        "root_policy": root_policy,
        "archive_hits": archive_hits,
        "archive_age_mean": (
            round(sum(archive_ages) / float(len(archive_ages)), 3) if archive_ages else None
        ),
        "rejected_unique": len(rejected_at),
        "min_delta": min_delta,
        "operators": list(operators),
        "controls": controls,
        "seed": seed,
        "evaluations": evaluations,
        "accepted": sum(1 for node in nodes if node.accepted_by_gate),
        "gate_rejections": gate_rejections,
        "improvements": improvements,
        "improvement_per_evaluation": round(improvements / float(max(1, evaluations)), 6),
        "best_score": round(best.score, 6),
        "root_score": round(root_node.score, 6),
        "lineage_depth": depth,
        "nodes": [node.to_dict() for node in nodes],
    }


def _paired_diff_interval(
    left: List[float], right: List[float]
) -> Dict[str, Any]:
    """Paired mean difference with a t-based interval over seeds; exploratory only.

    A two-seed study can produce a degenerate interval: if both paired differences are equal
    the within-pair variance is zero, the interval collapses onto the point estimate and a
    fluke reads as "decidable". Below MIN_DECISION_SEEDS the interval is therefore withheld
    and the comparison is reported as underpowered instead.
    """
    n = len(left)
    if n != len(right) or n < 2:
        return {"mean_diff": None, "ci95_low": None, "ci95_high": None, "n": n, "underpowered": True}
    diffs = [float(a) - float(b) for a, b in zip(left, right)]
    mean = sum(diffs) / len(diffs)
    variance = sum((value - mean) ** 2 for value in diffs) / (len(diffs) - 1)
    if n < MIN_DECISION_SEEDS:
        return {
            "mean_diff": round(mean, 6),
            "ci95_low": None,
            "ci95_high": None,
            "n": n,
            "underpowered": True,
            "reason": "needs >= %d seeds before an interval is interpreted" % MIN_DECISION_SEEDS,
        }
    standard_error = variance ** 0.5 / (len(diffs) ** 0.5)
    try:
        from scipy.stats import t

        critical = float(t.ppf(0.975, len(diffs) - 1))
    except Exception:
        critical = 2.0
    width = 2.0 * critical * standard_error
    needed = seeds_for_80pct(diffs)
    # criterion: the bracket is narrower than the effect it brackets. A seed-count cliff
    # (n >= seeds_for_80pct) would flip a 0.3x-wide interval to "not informative" over one seed.
    informative = bool(mean) and width <= abs(mean)
    record: Dict[str, Any] = {
        "mean_diff": round(mean, 6),
        "ci95_low": round(mean - critical * standard_error, 6),
        "ci95_high": round(mean + critical * standard_error, 6),
        "ci_width": round(width, 6),
        "n": len(diffs),
        "underpowered": False,
        "seeds_for_80pct": needed,
        "informative": informative,
    }
    if not informative:
        # `underpowered=False` only says the seed count passed the floor; an interval several
        # times wider than the effect it brackets decides nothing about magnitude
        record["reading"] = (
            "the 95%% interval is %.1fx the point estimate, so the sign is decided but the "
            "magnitude is not; 80%% power at the observed effect would need %s seeds (this run: %d)"
            % (
                (width / abs(mean)) if mean else float("inf"),
                needed if needed else "more than this design reports",
                len(diffs),
            )
        )
    return record


def seeds_for_80pct(diffs: List[float]) -> Optional[int]:
    """Rough seeds needed to decide this paired difference at its own observed effect size.

    Planning arithmetic only (two-sided 80% power): it says how much more of the same experiment
    would give the interval a chance of excluding zero. It is not a promise about the effect and
    it is not used by any gate.
    """
    n = len(diffs)
    if n < 2:
        return None
    mean = sum(diffs) / n
    if abs(mean) < 1e-12:
        return None
    variance = sum((item - mean) ** 2 for item in diffs) / (n - 1)
    sd = variance ** 0.5
    if sd == 0:
        return n
    needed = math.ceil((2.8 * sd / abs(mean)) ** 2)
    return max(n + 1, min(needed, 4096))


def build_evidence_package(study: Dict[str, Any]) -> Dict[str, Any]:
    """Reshape the study into the evidence fields the writing pack already understands.

    ``metrics_summary`` and ``comparison`` use the same mean/std and mean_diff/ci95 keys as
    the local experiment package, so a human-signed claim over this study makes its numbers
    legitimately reportable without inventing a second evidence path.
    """
    cells = {str(cell["cell_id"]): cell for cell in study["cells"]}
    metrics_summary: Dict[str, Dict[str, Any]] = {}
    series: Dict[str, List[float]] = {}
    for name, cell in cells.items():
        runs = cell.get("runs") or []
        values = [float(run["improvement_per_evaluation"]) for run in runs]
        series[name] = values
        spread = (
            (sum((value - sum(values) / len(values)) ** 2 for value in values) / max(1, len(values) - 1)) ** 0.5
            if len(values) > 1 else 0.0
        )
        metrics_summary["improvement_per_evaluation." + name] = {
            "mean": cell["mean_improvement_per_evaluation"],
            "std": round(spread, 6),
            "n": len(values),
        }
        metrics_summary["best_score." + name] = {
            "mean": cell["mean_best_score"],
            "std": None,
            "n": len(values),
        }

    reference_id = str(study.get("reference_cell") or sorted(cells)[0])
    baseline = cells[reference_id]
    comparison = {}
    for name, cell in cells.items():
        if name == reference_id:
            continue
        cell_values = [float(run["improvement_per_evaluation"]) for run in cell.get("runs") or []]
        base_values = [float(run["improvement_per_evaluation"]) for run in baseline.get("runs") or []]
        interval = _paired_diff_interval(cell_values, base_values)
        diffs = [left - right for left, right in zip(cell_values, base_values)]
        comparison[name] = dict(
            interval,
            comparator=reference_id,
            seeds_for_80pct=seeds_for_80pct(diffs),
            power_note=(
                "planning estimate at the observed effect size: how many seeds the same design "
                "would need for a chance of deciding; not a promise and not used by any gate"
            ),
        )

    return {
        "schema_version": "search-study-evidence-0.1",
        "study_sha256": study.get("study_sha256", ""),
        "status": "verified",
        "dataset": study["dataset"],
        "seeds": study["seeds"],
        "budget": study["budget"],
        "min_delta": study["min_delta"],
        "primary_metric": "improvement_per_evaluation",
        "metrics_summary": metrics_summary,
        "comparison": comparison,
        "min_decision_seeds": MIN_DECISION_SEEDS,
        "underpowered": len(study.get("seeds") or []) < MIN_DECISION_SEEDS,
        "decomposition": study["decomposition"],
        "interaction_inference": interaction_contrast(study),
        "conditional_interactions": conditional_interactions(study),
        "analogue": True,
        "exploratory": True,
        "significance_claimed": False,
        "boundary": PROVENANCE_BOUNDARY,
    }


def run_full_study(
    dataset: str = "iris",
    seeds: Optional[List[int]] = None,
    budget: int = 60,
    min_delta: float = 0.005,
    design: Optional[Dict[str, List[Any]]] = None,
) -> Dict[str, Any]:
    """Run the study and emit the evidence envelope in one call."""
    study = run_study(
        dataset=dataset, seeds=seeds, budget=budget, min_delta=min_delta, design=design
    )
    return {"study": study, "evidence": build_evidence_package(study)}


def write_study_package(
    output_dir: Path,
    dataset: str = "iris",
    seeds: Optional[List[int]] = None,
    budget: int = 60,
    min_delta: float = 0.005,
    design: Optional[Dict[str, List[Any]]] = None,
) -> Dict[str, Any]:
    """Run the study and persist spec / study / evidence with cross-binding hashes.

    The evidence envelope deliberately matches the local experiment package, so a human
    signed claim over it feeds ``allowed_result_numbers`` through the existing path. The
    interval is reported: if it contains zero, the study cannot support a directional claim
    no matter how interesting the point estimate looks.
    """
    from .storage import write_json_atomic

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    study_started = time.perf_counter()
    result = run_full_study(
        dataset=dataset,
        seeds=seeds if seeds is not None else list(range(1, DEFAULT_SEEDS + 1)),
        budget=budget,
        min_delta=min_delta,
        design=design,
    )
    study, evidence = result["study"], result["evidence"]
    environment = _environment(time.perf_counter() - study_started)
    spec = {
        "schema_version": "search-study-spec-0.3",
        "dataset": study["dataset"],
        "seeds": study["seeds"],
        "budget": study["budget"],
        "min_delta": study["min_delta"],
        "design": study["design"],
        "factors": study["factors"],
        "reference_cell": study["reference_cell"],
        "code_fingerprint": code_fingerprint(),
        "algorithm_canary": algorithm_canary(),
        "study_sha256": study.get("study_sha256", ""),
        "profile": study_profile_summary(),
        "environment": environment,
    }
    spec_sha = spec_sha256_of(spec)
    study_sha = study.get("study_sha256", "")
    evidence = dict(
        evidence,
        study_spec_sha256=spec_sha,
        study_sha256=study_sha,
        created_at=_utc_now(),
    )
    evidence_sha = evidence_sha256_of(evidence)
    evidence = dict(evidence, evidence_sha256=evidence_sha)
    write_json_atomic(output / "study-spec.json", spec)
    write_json_atomic(output / "study.json", study)
    write_json_atomic(output / "study-evidence.json", evidence)
    directional = [
        name
        for name, item in evidence["comparison"].items()
        if item.get("mean_diff") is not None
        and item.get("ci95_low") is not None
        and item.get("ci95_high") is not None
        and (item["ci95_low"] > 0 or item["ci95_high"] < 0)
    ]
    return {
        "output_dir": str(output),
        "hashes": {"spec": spec_sha, "study": study_sha, "evidence": evidence_sha},
        "decomposition": evidence["decomposition"],
        "comparison": evidence["comparison"],
        "directional_supported": directional,
        "interval_covers_zero": [
            name
            for name, item in evidence["comparison"].items()
            if item.get("mean_diff") is not None
            and (
                item.get("ci95_low") is None
                or item.get("ci95_high") is None
                or item["ci95_low"] <= 0 <= item["ci95_high"]
            )
        ],
        "underpowered": bool(evidence.get("underpowered")),
        "boundary": evidence["boundary"],
    }


CANARY_CONTROLS = {
    "dataset": "iris",
    "seeds": [1, 2, 3, 4],
    "budget": 20,
    "design": {"memory": [False, True], "gate": [False, True]},
}


def algorithm_canary() -> str:
    """A fixed control set re-executed, so a code change can be judged by its numbers.

    ``code_fingerprint`` hashes whole files: a docstring edit or a new registry entry stops every
    study from closing even though no number can move. Guessing which edits are inert from source is
    fragile, so the narrower claim is checked the way research claims are checked — recompute the
    same controls and hash the outcome. Only a package whose stored canary matches today's canary
    may downgrade that blocker, and packages from before the canary keep the blocker unchanged.
    """
    study = run_study(
        dataset=CANARY_CONTROLS["dataset"],
        seeds=list(CANARY_CONTROLS["seeds"]),
        budget=int(CANARY_CONTROLS["budget"]),
        design={key: list(value) for key, value in CANARY_CONTROLS["design"].items()},
    )
    payload = {
        "cells": [
            {
                "cell_id": cell["cell_id"],
                "mean_improvement_per_evaluation": cell["mean_improvement_per_evaluation"],
                "mean_best_score": cell["mean_best_score"],
            }
            for cell in study["cells"]
        ],
        "study_sha256": study.get("study_sha256", ""),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


ENVIRONMENT_BOUNDARY = (
    "wall-clock is disclosed for reproducibility only: the registered compute metric stays "
    "evaluations, these seconds are not contention-corrected, and the same code measured "
    "1082.6s on a busy machine against 202.2s on an idle one, so cross-machine comparison of "
    "these numbers is meaningless and no judgement depends on them"
)


def _environment(total_seconds: float) -> Dict[str, Any]:
    """Which machine and which libraries produced this study: disclosed, never judged."""

    def _version(name: str) -> str:
        try:
            module = __import__(name)
        except Exception:
            return ""
        return str(getattr(module, "__version__", "") or "")

    return {
        "python": sys.version.split()[0],
        "platform": "%s %s" % (platform.system(), platform.release()),
        "machine": platform.machine(),
        "cpu_logical": int(os.cpu_count() or 0),
        "numpy": _version("numpy"),
        "sklearn": _version("sklearn"),
        "scipy": _version("scipy"),
        "study_wall_seconds": round(float(total_seconds), 3),
        "boundary": ENVIRONMENT_BOUNDARY,
    }


def code_fingerprint() -> str:
    """Hash of the code that produces a study, so editing it makes findings stale."""
    digest = hashlib.sha256()
    for name in ("search_lab.py", "executable.py", "study_claims.py"):
        path = Path(__file__).resolve().parent / name
        if path.is_file():
            digest.update(name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _interaction_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)


def archive_inert_warning(design: Dict[str, Any]) -> str:
    """A negative archive cannot reject anything when no gate-on level is declared."""
    archive_levels = [str(level).lower() for level in (design.get("archive") or [])]
    if not any(level not in ("off", "false", "0") for level in archive_levels):
        return ""
    gate_levels = [str(level).lower() for level in (design.get("gate") or [])]
    if any(level in ("on", "true", "1") for level in gate_levels):
        return ""
    return (
        "archive is inert without gate=on: nothing is rejected, so the design cannot test "
        "archive effects; declare --factors gate=on"
    )


def _paired_interaction_summary(contrasts: List[float], name: str) -> Dict[str, Any]:
    n = len(contrasts)
    mean = sum(contrasts) / n
    base = {
        "available": True,
        "name": name,
        "mean_interaction": round(mean, 6),
        "n": n,
    }
    if n < MIN_DECISION_SEEDS:
        base.update({
            "ci95_low": None,
            "ci95_high": None,
            "underpowered": True,
            "reason": "needs >= %d seeds before an interval is interpreted" % MIN_DECISION_SEEDS,
        })
        return base
    variance = sum((value - mean) ** 2 for value in contrasts) / (n - 1)
    standard_error = variance ** 0.5 / (n ** 0.5)
    try:
        from scipy.stats import t

        critical = float(t.ppf(0.975, n - 1))
    except Exception:
        critical = 2.0
    low = mean - critical * standard_error
    high = mean + critical * standard_error
    base.update({
        "ci95_low": round(low, 6),
        "ci95_high": round(high, 6),
        "underpowered": False,
        "decidable": low > 0 or high < 0,
    })
    return base


def _memory_archive_contrasts(cells_list: List[Dict[str, Any]]) -> Optional[List[float]]:
    by_cell: Dict[tuple, List[float]] = {}
    for cell in cells_list:
        key = (_interaction_value(cell.get("memory")), _interaction_value(cell.get("archive")))
        by_cell[key] = [float(run["improvement_per_evaluation"]) for run in cell.get("runs") or []]
    needed = [(False, "off"), (False, "negative"), (True, "off"), (True, "negative")]
    if any(key not in by_cell for key in needed):
        return None
    if len({len(by_cell[key]) for key in needed}) != 1:
        return None
    a, b, c, d = [by_cell[key] for key in needed]
    return [(d[i] - c[i]) - (b[i] - a[i]) for i in range(len(a))]


def conditional_interactions(study: Dict[str, Any]) -> Dict[str, Any]:
    """Memory x archive interaction within each archive-window level, plus the 3-way interval.

    A 2x2x2 design cannot be summarized by one interaction. This reports the two 2x2 slices
    (all / recent) and the paired high-minus-low 3-way contrast, so a window modulation can be
    signed or refused instead of left as a post-hoc spreadsheet.
    """
    cells_list = [cell for cell in study.get("cells") or [] if isinstance(cell, dict)]
    if not cells_list:
        return {"available": False, "reason": "study has no cells"}
    order = ("memory", "gate", "archive", "archive_window", "parent_selection", "operators", "min_delta")
    keys = [key for key in order if all(key in cell for cell in cells_list)]
    varied = [
        key for key in keys
        if len({_interaction_value(cell.get(key)) for cell in cells_list}) == 2
    ]
    if not {"memory", "archive", "archive_window"}.issubset(set(varied)):
        return {
            "available": False,
            "reason": "conditional interactions need memory x archive x archive_window",
        }
    design = study.get("design") if isinstance(study.get("design"), dict) else {}
    declared = design.get("archive_window")
    levels = (
        [_interaction_value(level) for level in declared]
        if isinstance(declared, list) and len(declared) == 2
        else sorted({_interaction_value(cell.get("archive_window")) for cell in cells_list}, key=str)
    )
    slices: Dict[str, Any] = {}
    raw: Dict[str, List[float]] = {}
    for level in levels:
        filtered = [
            cell for cell in cells_list
            if _interaction_value(cell.get("archive_window")) == level
        ]
        contrasts = _memory_archive_contrasts(filtered)
        if contrasts is None:
            return {"available": False, "reason": "a window slice is missing 2x2 cells"}
        summary = _paired_interaction_summary(
            contrasts, "memory_x_archive_interaction@archive_window=%s" % level
        )
        summary["condition"] = {"archive_window": level}
        slices[str(level)] = summary
        raw[str(level)] = contrasts
    high, low = raw[str(levels[1])], raw[str(levels[0])]
    three = _paired_interaction_summary(
        [high[index] - low[index] for index in range(len(high))],
        "memory_x_archive_x_archive_window_interaction",
    )
    three["levels"] = {"archive_window": [levels[0], levels[1]]}
    three["reading"] = (
        "high-minus-low: a positive decidable 3-way means the memory x archive interaction is "
        "less negative under archive_window=%s than under %s; it is a statement about this "
        "design and dataset, not about published self-improving agents"
        % (levels[1], levels[0])
    )
    return {
        "available": True,
        "condition_on": "archive_window",
        "levels": levels,
        "slices": slices,
        "three_way": three,
    }


def interaction_contrast(study: Dict[str, Any]) -> Dict[str, Any]:
    """A paired interval for the interaction of the two factors the design actually varies.

    Reporting only the interaction's point estimate is the same mistake this system exists to
    prevent: the strongest pattern in these studies is the interaction, and without its own
    interval it cannot be signed, defended or refuted. The contrast is computed per seed as
    (high,high - high,low) - (low,high - low,low), so seeds stay paired. The legacy
    memory x gate orientation is preserved; other 2x2 designs (e.g. memory x archive) use the
    declared level order.
    """
    cells_list = [cell for cell in study.get("cells") or [] if isinstance(cell, dict)]
    if not cells_list:
        return {"available": False, "reason": "study has no cells"}
    order = ("memory", "gate", "archive", "archive_window", "parent_selection", "operators", "min_delta")
    keys = [key for key in order if all(key in cell for cell in cells_list)]
    varied = []
    for key in keys:
        values = {_interaction_value(cell.get(key)) for cell in cells_list}
        if len(values) == 2:
            varied.append(key)
    if len(varied) != 2:
        return {
            "available": False,
            "reason": "design does not vary exactly two factors (found %d)" % len(varied),
        }
    a, b = ("memory", "gate") if set(varied) == {"memory", "gate"} else (varied[0], varied[1])
    design = study.get("design") if isinstance(study.get("design"), dict) else {}

    def ordered(name: str) -> list:
        declared = design.get(name)
        if isinstance(declared, list) and len(declared) == 2:
            return [_interaction_value(level) for level in declared]
        return sorted(
            {_interaction_value(cell.get(name)) for cell in cells_list}, key=lambda item: str(item)
        )

    levels_a, levels_b = ordered(a), ordered(b)
    cells: Dict[tuple, List[float]] = {}
    for cell in cells_list:
        key = (_interaction_value(cell.get(a)), _interaction_value(cell.get(b)))
        cells[key] = [float(run["improvement_per_evaluation"]) for run in cell.get("runs") or []]
    needed = [
        (levels_a[0], levels_b[0]),
        (levels_a[0], levels_b[1]),
        (levels_a[1], levels_b[0]),
        (levels_a[1], levels_b[1]),
    ]
    if any(key not in cells for key in needed):
        return {"available": False, "reason": "design does not contain all four 2x2 cells"}
    lengths = {len(cells[key]) for key in needed}
    if len(lengths) != 1:
        return {"available": False, "reason": "cells have unequal seed counts"}
    a_low_b_low, a_low_b_high, a_high_b_low, a_high_b_high = [cells[key] for key in needed]
    contrasts = [
        (a_high_b_high[index] - a_high_b_low[index])
        - (a_low_b_high[index] - a_low_b_low[index])
        for index in range(len(a_low_b_low))
    ]
    n = len(contrasts)
    mean = sum(contrasts) / n
    name = "%s_x_%s_interaction" % (a, b)
    if n < MIN_DECISION_SEEDS:
        return {
            "available": True,
            "name": name,
            "factors": [a, b],
            "levels": {a: levels_a, b: levels_b},
            "mean_interaction": round(mean, 6),
            "ci95_low": None,
            "ci95_high": None,
            "n": n,
            "underpowered": True,
            "reason": "needs >= %d seeds before an interval is interpreted" % MIN_DECISION_SEEDS,
        }
    variance = sum((value - mean) ** 2 for value in contrasts) / (n - 1)
    standard_error = variance ** 0.5 / (n ** 0.5)
    try:
        from scipy.stats import t

        critical = float(t.ppf(0.975, n - 1))
    except Exception:
        critical = 2.0
    low = mean - critical * standard_error
    high = mean + critical * standard_error
    if (a, b) == ("memory", "gate"):
        reading = (
            "a negative decidable interaction means the archive stops helping once the "
            "acceptance gate is on; it is a statement about this design and dataset, not "
            "about published self-improving agents"
        )
    else:
        reading = (
            "a decidable interaction means the effect of %s=%s vs %s changes when %s changes; "
            "it is a statement about this design and dataset, not about published "
            "self-improving agents" % (b, levels_b[1], levels_b[0], a)
        )
    return {
        "available": True,
        "name": name,
        "factors": [a, b],
        "levels": {a: levels_a, b: levels_b},
        "mean_interaction": round(mean, 6),
        "ci95_low": round(low, 6),
        "ci95_high": round(high, 6),
        "n": n,
        "underpowered": False,
        "decidable": low > 0 or high < 0,
        "reading": reading,
    }


def _json_sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# Wall-clock is disclosure, never content. A hash that covers seconds cannot be reproduced by
# re-running the same controls: two runs of the canary controls on this machine differed only in
# `elapsed_seconds` (0.098 against 0.094) and therefore produced two different `study_sha256`,
# which made `code.canary_stable` fail against a package written seconds earlier and would have
# failed any claim that the study hash can be recomputed. Every hashed view drops the fields
# below; the artifacts keep them for the reader, and no judgement depends on them.
TIMING_FIELDS = ("elapsed_seconds", "study_wall_seconds")


def _without_timing(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_timing(item)
            for key, item in value.items()
            if key not in TIMING_FIELDS
        }
    if isinstance(value, list):
        return [_without_timing(item) for item in value]
    return value


# The three hashes bind each other, so every producer and consumer must derive them with the
# same helper: a byte hash of a file and a canonical-JSON hash of its content are not equal,
# and mixing them once made a valid study look unverifiable.
def study_sha256_of(study: Dict[str, Any]) -> str:
    """The study payload without its own hash field, which is exactly what the writer hashed."""
    return _json_sha(
        _without_timing({key: value for key, value in study.items() if key != "study_sha256"})
    )


def spec_sha256_of(spec: Dict[str, Any]) -> str:
    return _json_sha(_without_timing(spec))


def study_sha256_of(study: Dict[str, Any]) -> str:
    """The study payload as the writer hashed it: its own hash field is not part of its content."""
    return _json_sha(
        _without_timing(
            {key: value for key, value in study.items() if key != "study_sha256"}
        )
    )


def evidence_sha256_of(evidence: Dict[str, Any]) -> str:
    return _json_sha(_without_timing(dict(evidence, evidence_sha256="")))


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def study_profile_summary() -> Dict[str, Any]:
    """What the runtime can actually execute, so idea-stage plans can be checked against it."""
    return {
        "id": "search_factorial",
        "kind": "improvement-search control study",
        "datasets": sorted(DATASETS),
        "factors": {
            factor: spec["levels"] for factor, spec in sorted(SEARCH_FACTORS.items())
        },
        "factor_semantics": {
            factor: spec["semantics"] for factor, spec in sorted(SEARCH_FACTORS.items())
        },
        "operator_sets": {
            name: list(ops) for name, ops in sorted(OPERATOR_SETS.items())
        },
        "max_cells": MAX_DESIGN_CELLS,
        "primary_metric": "improvement_per_evaluation",
        "supports": [
            "memory x gate main effects and interaction",
            "any declared factorial over the registered controls",
            "accepted-lineage depth",
            "improvement per unit validation compute",
        ],
        "does_not_support": [
            "agent source-code self-modification",
            "any published DGM/SICA/ACE/SIFT baseline reproduction",
            "language-model or benchmark-scale search",
        ],
        "boundary": PROVENANCE_BOUNDARY,
    }


def run_study(
    dataset: str = "iris",
    seeds: Optional[List[int]] = None,
    budget: int = 60,
    min_delta: float = 0.005,
    design: Optional[Dict[str, List[Any]]] = None,
) -> Dict[str, Any]:
    """Run a declared factorial design over the registered search controls.

    With no design this is the memory x gate 2x2. Declaring other factors (an operator set, a
    gate threshold) turns the same runner into a test of a different search hypothesis, which is
    what makes the study a method rather than one anecdote about one archive.
    """
    dataset = dataset if dataset in DATASETS else "iris"
    seeds = [int(seed) for seed in (seeds or [1, 2, 3])]
    plan = normalize_design(design, min_delta)
    order = naming_order(plan)
    cells: List[Dict[str, Any]] = []
    for combo in design_cells(plan, order):
        controls = {key: value for key, value in combo.items() if key != "cell_id"}
        cell_started = time.perf_counter()
        runs = [
            run_condition(
                dataset=dataset,
                seed=seed,
                budget=int(budget),
                archive=bool(controls["memory"]),
                gate=bool(controls["gate"]),
                min_delta=float(controls["min_delta"]),
                operators=OPERATOR_SETS[controls["operators"]],
                parent_selection=str(controls.get("parent_selection") or "uniform"),
                archive_mode=str(controls.get("archive") or "off"),
                archive_window=str(controls.get("archive_window") or "all"),
                root_policy=str(controls.get("root") or "random_subset"),
            )
            for seed in seeds
        ]
        cells.append(
            dict(
                controls,
                cell_id=combo["cell_id"],
                runs=runs,
                elapsed_seconds=round(time.perf_counter() - cell_started, 3),
                mean_best_score=round(
                    sum(run["best_score"] for run in runs) / len(runs), 6
                ),
                mean_improvements=round(
                    sum(run["improvements"] for run in runs) / len(runs), 4
                ),
                mean_improvement_per_evaluation=round(
                    sum(run["improvement_per_evaluation"] for run in runs) / len(runs), 6
                ),
                mean_lineage_depth=round(
                    sum(run["lineage_depth"] for run in runs) / len(runs), 4
                ),
            )
        )

    by_id = {cell["cell_id"]: cell for cell in cells}
    reference_id = cell_id_of(reference_controls(plan), order)

    def cell_at(**overrides: Any) -> Dict[str, Any]:
        controls = dict(reference_controls(plan))
        controls.update(overrides)
        return by_id[cell_id_of(controls, order)]

    factorial = len(plan.get("memory", [])) == 2 and len(plan.get("gate", [])) == 2
    varies_start = len(plan.get("root") or ()) > 1
    if factorial:
        gate_main = (
            cell_at(gate=True)["mean_improvement_per_evaluation"]
            - cell_at(gate=False)["mean_improvement_per_evaluation"]
        )
        memory_main = (
            cell_at(memory=True)["mean_improvement_per_evaluation"]
            - cell_at(memory=False)["mean_improvement_per_evaluation"]
        )
        interaction = (
            cell_at(memory=True, gate=True)["mean_improvement_per_evaluation"]
            - cell_at(memory=True, gate=False)["mean_improvement_per_evaluation"]
        ) - gate_main
        decomposition: Dict[str, Any] = {
            "memory_main_effect": round(memory_main, 6),
            "gate_main_effect": round(gate_main, 6),
            "memory_x_gate_interaction": round(interaction, 6),
            "metric_caveats": (
                [
                    "improvement_per_evaluation is not comparable across cells that start from a "
                    "different initial configuration: a better start leaves less room to improve, "
                    "so the rate can fall while the final score rises. Rank those cells by final "
                    "score and report the rate only within a fixed starting point."
                ]
                if varies_start
                else []
            ),
            "reading": (
                "improvements per validation evaluation; the interaction answers whether the "
                "archive still helps once the acceptance gate is held fixed"
            ),
        }
    else:
        baseline = by_id[reference_id]["mean_improvement_per_evaluation"]
        reference_cell = by_id[reference_id]

        def _paired(left: List[Dict[str, Any]], field: str) -> Dict[str, Any]:
            """Paired per-seed contrast; the reading below promises an interval, so emit one."""
            right_values = {int(run["seed"]): float(run[field]) for run in reference_cell["runs"]}
            left_values = {
                int(run["seed"]): float(run[field])
                for run in left.get("runs") or []
                if int(run["seed"]) in right_values
            }
            common = sorted(set(left_values) & set(right_values))
            if not common:
                return {"n": 0, "reading": "no seeds shared with the reference cell"}
            return _paired_diff_interval(
                [left_values[seed] for seed in common],
                [right_values[seed] for seed in common],
            )

        decomposition = {
            "memory_main_effect": None,
            "gate_main_effect": None,
            "memory_x_gate_interaction": None,
            "contrasts_vs_reference": [
                {
                    "cell_id": cell["cell_id"],
                    "difference": round(
                        cell["mean_improvement_per_evaluation"] - baseline, 6
                    ),
                    "paired_interval_improvement_per_evaluation": _paired(
                        cell, "improvement_per_evaluation"
                    ),
                    "paired_interval_best_score": _paired(cell, "best_score"),
                }
                for cell in cells
                if cell["cell_id"] != reference_id
            ],
            "reading": (
                "this design does not vary both memory and gate, so main effects and their "
                "interaction are undefined; only contrasts against the reference cell are "
                "reported, and a paired interval over seeds is what decides them"
            ),
            "metric_caveats": (
                ["improvement_per_evaluation is not comparable across cells that start from a "
                 "different initial configuration: a better start leaves less room to improve, "
                 "so the rate can fall while the final score rises. Rank those cells by final "
                 "score and report the rate only within a fixed starting point."]
                if varies_start
                else []
            ),
        }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "dataset": dataset,
        "seeds": seeds,
        "budget": int(budget),
        "min_delta": float(min_delta),
        "design": plan,
        "factors": order,
        "reference_cell": reference_id,
        "cells": cells,
        "decomposition": decomposition,
        "analogue": True,
        "not_a_reproduction_of": ["DGM", "SICA", "ACE", "SIFT"],
        "boundary": PROVENANCE_BOUNDARY,
    }
    payload["study_sha256"] = study_sha256_of(payload)
    return payload
