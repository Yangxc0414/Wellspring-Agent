"""A tuned reference baseline for the search study: the comparison a reviewer asks for.

The study compares search policies against each other. That is not enough on its own: the
strong-baseline question ("did you beat a tuned model, or only a weak opponent?") stays open.
This module answers it locally, with no model API — it tunes classifier and hyperparameter by
stratified cross-validation on the same training split the search uses, then scores the tuned
configuration once on the same held-out split, so the numbers are directly comparable.

Limits that matter for interpretation:
- the baseline sees ALL features while the search may drop features, so this is a different,
  textbook-strong recipe and not "the same search with more budget";
- tuning consumes evaluations and the artifact reports how many, so any budget-matched claim
  can be made honestly;
- nothing here runs the archive/gate policies, and nothing here signs anything.
"""

from typing import Any, Dict, List, Optional, Tuple

# the grid mirrors what the knob mutation can reach (halve/double, clamped to [0.01, 32]);
# `tree` reads the knob as max_depth and `centroid` has no knob at all
CLASSIFIER_GRID: Dict[str, List[float]] = {
    "centroid": [1.0],
    "logistic": [0.01, 0.1, 1.0, 4.0, 8.0, 32.0],
    "ridge": [0.01, 0.1, 1.0, 4.0, 8.0, 32.0],
    "tree": [1.0, 2.0, 4.0, 8.0, 16.0, 32.0],
}
CV_FOLDS = 5
DATASETS = ("iris", "breast_cancer", "wine", "digits")

BOUNDARY = (
    "tuned cross-validation reference computed on the search's own split: the baseline uses every "
    "feature and a hand-specified grid, so it is a strong different recipe rather than the same "
    "search with more budget; the evaluations it spent are reported so budget-matched claims stay "
    "possible; this is not a claim, not evidence for one, and nothing here was signed"
)


TRIVIAL_BASELINE_NOTE = (
    "zero-fit trivial references computed on the same held-out split as the tuned reference: "
    "majority-class always predicts the most frequent training label, random-label draws from the "
    "training label frequencies with a fixed seed. They cost no evaluations, so they are not "
    "budget-matched comparisons; a single-feature reference is deliberately absent because choosing "
    "the feature would itself consume evaluations and blur the budget accounting"
)


def trivial_baselines(dataset: str, seeds: List[int], folds: int = CV_FOLDS) -> Dict[str, Any]:
    """The trivial rows an ACL-style design rubric asks for, on the study's own split.

    Only two of the four classic trivial baselines apply to tabular data with no text or retrieval
    (majority class, random label). They are reported separately from the tuned reference because
    they spend no evaluations, and a budget-matched claim must not quietly count them.
    """
    import numpy as np

    from .search_lab import _load_dataset

    if folds < 2:
        raise ValueError("cross-validation needs at least 2 folds")
    per_seed: Dict[str, List[float]] = {"majority_class": [], "random_label": []}
    for seed in seeds:
        x_train, x_valid, y_train, y_valid = _load_dataset(dataset, seed)
        counts: Dict[int, int] = {}
        for label in list(y_train):
            key = int(label)
            counts[key] = counts.get(key, 0) + 1
        majority = max(counts, key=lambda key: counts[key])
        per_seed["majority_class"].append(
            float(sum(1 for value in y_valid if int(value) == majority)) / float(len(list(y_valid)))
        )
        rng = np.random.RandomState(1000 + int(seed))
        pool: List[int] = []
        for label in sorted(counts):
            pool.extend([label] * counts[label])
        drawn = rng.choice(np.asarray(pool), size=int(len(list(y_valid))), replace=True)
        per_seed["random_label"].append(
            float(sum(1 for a, b in zip([int(v) for v in drawn], [int(v) for v in y_valid]) if a == b))
            / float(len(list(y_valid)))
        )

    out: Dict[str, Any] = {"note": TRIVIAL_BASELINE_NOTE, "seeds": len(list(seeds)), "values": {}}
    for name, values in per_seed.items():
        mean = sum(values) / float(len(values)) if values else None
        spread = (
            (sum((value - mean) ** 2 for value in values) / float(len(values) - 1)) ** 0.5
            if len(values) > 1 and mean is not None
            else None
        )
        out["values"][name] = {
            "mean": round(mean, 6) if mean is not None else None,
            "std": round(spread, 6) if spread is not None else None,
            "n": len(values),
        }
    return out


def _all_features(count: int) -> Tuple[bool, ...]:
    return tuple([True] * count)


def tune_one_dataset(dataset: str, seed: int, folds: int = CV_FOLDS) -> Dict[str, Any]:
    """Grid-tune by stratified CV on the training split; return the held-out score too."""
    from sklearn.model_selection import StratifiedKFold

    from .search_lab import Configuration, _load_dataset, _score

    if dataset not in DATASETS:
        raise ValueError("unsupported dataset: %s (choose %s)" % (dataset, ", ".join(DATASETS)))
    if folds < 2:
        raise ValueError("cross-validation needs at least 2 folds")

    x_train, x_valid, y_train, y_valid = _load_dataset(dataset, seed)
    mask = _all_features(int(x_train.shape[1]))
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)

    rows: List[Dict[str, Any]] = []
    spent = 0
    for classifier in sorted(CLASSIFIER_GRID):
        for knob in CLASSIFIER_GRID[classifier]:
            config = Configuration(classifier=classifier, feature_mask=mask, knob=knob)
            scores: List[float] = []
            for train_index, valid_index in splitter.split(x_train, y_train):
                scores.append(
                    _score(
                        config,
                        x_train[train_index],
                        y_train[train_index],
                        x_train[valid_index],
                        y_train[valid_index],
                    )
                )
                spent += 1
            rows.append(
                {
                    "classifier": classifier,
                    "knob": knob,
                    "cv_mean": round(sum(scores) / float(len(scores)), 6),
                    "cv_min": round(min(scores), 6),
                    "cv_max": round(max(scores), 6),
                }
            )
    # deterministic winner: best CV mean, then the smallest knob, then the family name
    rows.sort(key=lambda row: (-row["cv_mean"], row["knob"], row["classifier"]))
    best = rows[0]
    held_out = _score(
        Configuration(classifier=best["classifier"], feature_mask=mask, knob=best["knob"]),
        x_train,
        y_train,
        x_valid,
        y_valid,
    )
    return {
        "dataset": dataset,
        "seed": seed,
        "n_features": int(x_train.shape[1]),
        "train_rows": int(x_train.shape[0]),
        "valid_rows": int(x_valid.shape[0]),
        "folds": folds,
        "evaluations_spent": spent,
        "grid_size": len(rows),
        "best": dict(best),
        "held_out_score": round(float(held_out), 6),
        "runner_up": dict(rows[1]) if len(rows) > 1 else None,
    }


def run_baseline(
    datasets: Optional[List[str]] = None,
    seeds: Optional[List[int]] = None,
    folds: int = CV_FOLDS,
) -> Dict[str, Any]:
    """Tune every requested (dataset, seed) pair and aggregate the held-out scores."""
    wanted = list(datasets or list(DATASETS))
    used_seeds = list(seeds or [1, 2, 3])
    for name in wanted:
        if name not in DATASETS:
            raise ValueError("unsupported dataset: %s (choose %s)" % (name, ", ".join(DATASETS)))
    rows: List[Dict[str, Any]] = []
    for name in wanted:
        for seed in used_seeds:
            rows.append(tune_one_dataset(name, seed, folds=folds))
    per_dataset: Dict[str, Dict[str, Any]] = {}
    for name in wanted:
        subset = [row for row in rows if row["dataset"] == name]
        scores = [float(row["held_out_score"]) for row in subset]
        mean = sum(scores) / float(len(scores)) if scores else 0.0
        spread = (
            (sum((value - mean) ** 2 for value in scores) / float(len(scores))) ** 0.5
            if scores
            else 0.0
        )
        families: Dict[str, int] = {}
        for row in subset:
            families[row["best"]["classifier"]] = families.get(row["best"]["classifier"], 0) + 1
        per_dataset[name] = {
            "seeds": len(subset),
            "held_out_mean": round(mean, 6),
            "held_out_std": round(spread, 6),
            "held_out_min": round(min(scores), 6) if scores else None,
            "held_out_max": round(max(scores), 6) if scores else None,
            "evaluations_spent": int(sum(row["evaluations_spent"] for row in subset)),
            "winning_families": families,
        }
    return {
        "schema_version": "tuned-baseline-0.1",
        "datasets": wanted,
        "seeds": used_seeds,
        "folds": folds,
        "rows": rows,
        "per_dataset": per_dataset,
        "trivial_baselines": dict(
            (name, trivial_baselines(name, used_seeds, folds=folds)) for name in wanted
        ),
        "boundary": BOUNDARY,
    }


def grid_size() -> int:
    """Number of (classifier, knob) configurations the reference tunes over."""
    return sum(len(values) for values in CLASSIFIER_GRID.values())


def fits_within_budget(budget: int) -> int:
    """Largest fold count whose cross-validation fits stay inside the search's budget.

    The comparison is only honest at equal budget: a tuned reference that spent 95 fits against
    a search allowed 60 evaluations is not a baseline, it is a different game.
    """
    size = grid_size()
    if size <= 0 or budget < size:
        return 0
    return int(budget // size)


TABLE_COLUMNS = (
    ("dataset", "dataset"),
    ("seeds", "seeds"),
    ("cell", "cell"),
    ("study_mean_best", "study_mean_best"),
    ("baseline_mean_held_out", "baseline_mean_held_out"),
    ("mean_delta", "mean_delta"),
    ("ci95_low", "ci95_low"),
    ("ci95_high", "ci95_high"),
    ("interval_informative", "informative"),
    ("wins", "W"),
    ("losses", "L"),
    ("ties", "T"),
    ("folds", "folds"),
    ("fits_per_seed", "fits/seed"),
    ("study_budget", "budget"),
    ("budget_matched", "matched"),
)


def _require(container: Dict[str, Any], key: str, where: str) -> Any:
    """A table column that silently renders as blank is how a mislabeled number ships."""
    if not isinstance(container, dict) or key not in container:
        raise KeyError(
            "tuned baseline table: %s carries no %r; regenerate it with `study baseline --output` "
            "instead of transcribing or hand-editing the markdown" % (where, key)
        )
    return container[key]


def _table_row(report: Dict[str, Any], cell: Dict[str, Any]) -> Dict[str, Any]:
    where = "cell %s of the %s report" % (cell.get("cell_id"), report.get("dataset"))
    top = "the %s report" % report.get("dataset")
    interval = cell.get("paired_interval")
    if isinstance(interval, dict) and interval.get("ci95_low") is not None:
        low: Any = _require(interval, "ci95_low", where + " interval")
        high: Any = _require(interval, "ci95_high", where + " interval")
    elif isinstance(interval, dict) and interval.get("underpowered"):
        # the honest marker: the interval was computed and then withheld for lack of power
        low = high = "withheld(low power)"
    else:
        # the artifact carries no interval at all, which must not read as "withheld for power"
        low = high = "not computed"
    # informative arrived with the interval-width rule, so a report written before it legitimately
    # carries no such field; saying so is honest, blanking it out or inventing it is not
    informative = (
        interval.get("informative") if isinstance(interval, dict) else None
    )
    informative = {True: "yes", False: "no"}.get(informative, "unrecorded")
    return {
        "dataset": _require(report, "dataset", top),
        "seeds": _require(cell, "seeds_compared", where),
        "cell": _require(cell, "cell_id", where),
        "study_mean_best": _require(cell, "study_mean_best", where),
        "baseline_mean_held_out": _require(cell, "baseline_mean_held_out", where),
        "mean_delta": _require(cell, "mean_delta", where),
        "ci95_low": low,
        "ci95_high": high,
        "interval_informative": informative,
        "wins": _require(cell, "seeds_where_study_wins", where),
        "losses": _require(cell, "seeds_where_baseline_wins", where),
        "ties": _require(cell, "seeds_tied", where),
        "folds": _require(report, "folds", top),
        "fits_per_seed": _require(report, "baseline_fits_per_seed", top),
        "study_budget": _require(report, "study_budget", top),
        "budget_matched": _require(report, "budget_matched", top),
    }


def to_markdown(reports: List[Dict[str, Any]], title: str = "") -> Dict[str, Any]:
    """Render tuned-baseline reports straight from their artifacts, header and rows together.

    A hand-written table is how a column ends up labelled one thing and filled with another, so
    both come from TABLE_COLUMNS and every cell value is read by its real key name.
    """
    header = [label for _, label in TABLE_COLUMNS]
    lines = [title or "# Tuned baseline comparison", ""]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join([" --- "] * len(header)) + "|")
    rows = []
    for report in reports:
        for cell in report.get("cells") or []:
            row = _table_row(report, cell)
            rows.append(row)
            lines.append("| " + " | ".join(str(row[key]) for key, _ in TABLE_COLUMNS) + " |")
    if not rows:
        raise ValueError(
            "tuned baseline table: no cell rows to render; pass the report written by "
            "`study baseline --output`, whose cells carry the paired per-seed comparison"
        )
    lines.extend(
        [
            "",
            "标记由代码判定，不手写：`not computed` = 该产物由尚未计算配对区间的版本写出，"
            "**不等于**功效不足；`withheld(low power)` = 区间已算出但种子低于判定下界被扣住；"
            "`unrecorded` = 该产物写成时还没有区间宽度判定字段。",
        ]
    )
    return {
        "schema_version": "tuned-baseline-table-0.1",
        "markdown": "\n".join(lines) + "\n",
        "columns": header,
        "rows": rows,
        "row_count": len(rows),
        "boundary": (
            "a projection of tuned-baseline reports: every value is read by its artifact key, a "
            "withheld interval is printed as withheld rather than blank, and nothing here creates "
            "evidence, signs a claim or changes a status"
        ),
    }


def compare_with_study(
    study: Dict[str, Any],
    seeds: Optional[List[int]] = None,
    folds: Optional[int] = None,
) -> Dict[str, Any]:
    """Pair the tuned reference with a study artifact on the same dataset and seeds."""
    dataset = str(study.get("dataset") or "")
    budget = int(study.get("budget") or 0)
    allowed = [int(seed) for seed in (study.get("seeds") or [])]
    chosen = [int(seed) for seed in (seeds or allowed)]
    chosen = [seed for seed in chosen if not allowed or seed in allowed]
    if not chosen:
        raise ValueError("no seeds in common with the study")
    used_folds = folds or fits_within_budget(budget)
    if used_folds < 2:
        raise ValueError(
            "the study budget (%d) cannot afford even 2 cross-validation folds over a "
            "%d-configuration grid; no budget-matched baseline exists at this budget"
            % (budget, grid_size())
        )
    report = run_baseline([dataset], chosen, folds=used_folds)
    rows = {int(row["seed"]): row for row in report["rows"]}
    cells = []
    for cell in study.get("cells") or []:
        per_seed = []
        for run in cell.get("runs") or []:
            seed = int(run.get("seed") or -1)
            if seed in rows:
                best = float(run.get("best_score") or 0.0)
                per_seed.append(
                    {
                        "seed": seed,
                        "study_best_score": round(best, 6),
                        "baseline_held_out": rows[seed]["held_out_score"],
                        "delta": round(best - rows[seed]["held_out_score"], 6),
                    }
                )
        if not per_seed:
            continue
        deltas = [item["delta"] for item in per_seed]
        mean_delta = sum(deltas) / float(len(deltas))
        from .search_lab import MIN_DECISION_SEEDS, _paired_diff_interval

        interval = _paired_diff_interval(
            [float(item["study_best_score"]) for item in per_seed],
            [float(item["baseline_held_out"]) for item in per_seed],
        )
        cells.append(
            {
                "cell_id": cell.get("cell_id"),
                "seeds_compared": len(per_seed),
                "study_mean_best": round(
                    sum(item["study_best_score"] for item in per_seed) / float(len(per_seed)), 6
                ),
                "baseline_mean_held_out": round(
                    sum(item["baseline_held_out"] for item in per_seed) / float(len(per_seed)), 6
                ),
                "mean_delta": round(mean_delta, 6),
                "paired_interval": interval,
                "decidable": len(per_seed) >= MIN_DECISION_SEEDS,
                "seeds_where_study_wins": sum(1 for value in deltas if value > 0),
                "seeds_where_baseline_wins": sum(1 for value in deltas if value < 0),
                "seeds_tied": sum(1 for value in deltas if value == 0),
                "per_seed": per_seed,
            }
        )
    spent = int(report["rows"][0]["evaluations_spent"])
    return {
        "schema_version": "tuned-baseline-comparison-0.1",
        "dataset": dataset,
        "study_budget": budget,
        "folds": used_folds,
        "grid_size": grid_size(),
        "baseline_fits_per_seed": spent,
        "budget_matched": spent <= budget,
        "seeds": chosen,
        "trivial_baselines": (report.get("trivial_baselines") or {}).get(dataset) or {},
        "cells": cells,
        "boundary": (
            BOUNDARY
            + "; the paired interval is withheld below MIN_DECISION_SEEDS, so a small positive "
            "mean_delta on few seeds is not a decision; "
            + "; the study's best_score and this baseline's held_out_score are both validation "
            "accuracy on the same split function, so the delta is a paired difference, not a "
            "causal claim, and a budget-matched comparison needs baseline_fits_per_seed <= "
            "study_budget"
        ),
    }
