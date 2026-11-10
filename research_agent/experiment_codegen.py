"""Generate a self-contained local experiment package from a run design.

This module never executes the generated code. It turns ``experiment.json``
plus a user-provided table schema into an auditable spec, a deterministic
runner, dependency notes and a README. The generated runner writes metrics,
predictions and a local receipt, but never creates EA/Claim/gate artifacts.
"""

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .data_audit import audit_tabular_data
from .project import run_dir
from .storage import read_json, write_json_atomic

CODEGEN_SCHEMA = "experiment-codegen-0.1"
SPEC_SCHEMA = "experiment-spec-0.1"
SUPPORTED_METHODS = ("dummy", "ridge", "logistic", "random_forest", "gradient_boosting")
SUPPORTED_METRICS = {
    "regression": ("r2", "mae", "rmse"),
    "classification": ("accuracy", "f1_macro"),
}


class ExperimentCodegenError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean(value: Any, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit else text


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-")
    return cleaned[:80] or "EXP-LOCAL"


def _read_csv_header(path: Path) -> List[str]:
    try:
        with open(str(path), "r", encoding="utf-8-sig", newline="") as handle:
            first = handle.readline().strip()
    except OSError as exc:
        raise ExperimentCodegenError("cannot read data table: %s" % exc)
    if not first:
        raise ExperimentCodegenError("data table is empty")
    return [item.strip() for item in first.split(",")]


def _runner_source() -> str:
    return r'''#!/usr/bin/env python3
"""Generated local experiment runner.

This runner writes metrics and a local receipt only. It does not create a
RunCapsule, EA, Claim, gate or signature. Run it only in the user's approved
local environment after G2/human review.
"""
import argparse
import hashlib
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, StratifiedKFold, train_test_split

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
SPEC = json.loads((HERE / "experiment-spec.json").read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_data(data_path, spec):
    target = spec["data"]["target"]
    features = list(spec["data"]["features"])
    if target in features:
        raise ValueError("target must not appear in features")
    frame = pd.read_csv(data_path)
    missing = [column for column in features + [target] if column not in frame.columns]
    if missing:
        raise ValueError("missing columns: " + ", ".join(missing))
    frame = frame[features + [target]].dropna().copy()
    if frame.empty:
        raise ValueError("no rows remain after dropping missing values")
    return frame


def build_model(name, task, seed, ridge_alpha=None):
    if name == "dummy":
        return DummyRegressor(strategy="mean") if task == "regression" else DummyClassifier(strategy="most_frequent")
    if name == "ridge":
        if task != "regression":
            raise ValueError("ridge is only supported for regression")
        return Ridge(alpha=float(ridge_alpha) if ridge_alpha else 1.0, random_state=seed)
    if name == "logistic":
        if task != "classification":
            raise ValueError("logistic is only supported for classification")
        return LogisticRegression(max_iter=2000, random_state=seed)
    if name == "random_forest":
        if task == "regression":
            return RandomForestRegressor(n_estimators=200, random_state=seed, n_jobs=-1)
        return RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=-1)
    if name == "gradient_boosting":
        if task == "regression":
            return GradientBoostingRegressor(n_estimators=150, random_state=seed)
        return GradientBoostingClassifier(n_estimators=150, random_state=seed)
    raise ValueError("unsupported method: " + name)


def metrics_for(task, y_true, y_pred):
    if task == "regression":
        return {
            "r2": float(r2_score(y_true, y_pred)),
            "mae": float(mean_absolute_error(y_true, y_pred)),
            "rmse": float(math.sqrt(mean_squared_error(y_true, y_pred))),
        }
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro")),
    }


def aggregate(rows, methods):
    output = {}
    for method in methods:
        values = [row["metrics"] for row in rows if row["method"] == method]
        output[method] = {}
        for key in values[0] if values else {}:
            sequence = [item[key] for item in values]
            mean = sum(sequence) / len(sequence)
            variance = sum((value - mean) ** 2 for value in sequence) / len(sequence)
            output[method][key] = {
                "mean": mean,
                "std": math.sqrt(variance),
                "by_seed": sequence,
            }
    return output


def paired_comparison(rows, methods, metric):
    if len(methods) < 2:
        return {}
    baseline, primary = methods[0], methods[-1]
    by_run = {}
    for row in rows:
        key = (row["seed"], row.get("fold", 0))
        by_run.setdefault(key, {})[row["method"]] = row["metrics"][metric]
    diffs = [
        item[primary] - item[baseline]
        for item in by_run.values()
        if baseline in item and primary in item
    ]
    if not diffs:
        return {}
    mean_diff = sum(diffs) / len(diffs)
    variance = sum((value - mean_diff) ** 2 for value in diffs) / len(diffs)
    std_diff = math.sqrt(variance)
    half = 1.96 * std_diff / math.sqrt(len(diffs))
    wins = sum(1 for value in diffs if value > 0)
    rng = random.Random(0)
    bootstrap = []
    for _ in range(1000):
        sample = [diffs[rng.randrange(len(diffs))] for _ in diffs]
        bootstrap.append(sum(sample) / len(sample))
    bootstrap.sort()
    low_index = max(0, int(0.025 * len(bootstrap)) - 1)
    high_index = min(len(bootstrap) - 1, int(0.975 * len(bootstrap)))
    tail = min(wins, len(diffs) - wins)
    sign_p = min(1.0, 2.0 * sum(math.comb(len(diffs), i) for i in range(tail + 1)) / (2 ** len(diffs)))
    return {
        primary + "_vs_" + baseline: {
            "metric": metric,
            "n": len(diffs),
            "mean_diff": mean_diff,
            "std_diff": std_diff,
            "ci95_low": mean_diff - half,
            "ci95_high": mean_diff + half,
            "bootstrap_ci95_low": bootstrap[low_index],
            "bootstrap_ci95_high": bootstrap[high_index],
            "wins": wins,
            "sign_test_p": sign_p,
            "higher_is_better": metric not in ("mae", "rmse"),
            "boundary": "paired seed differences; normal/bootstrap CI and sign test are exploratory, not adjusted for multiple comparisons",
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Generated local experiment runner")
    parser.add_argument("--data", default=SPEC["data"]["path"])
    parser.add_argument("--out", default=str(HERE / "outputs"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seeds", type=int, default=0)
    parser.add_argument("--ridge-alpha", type=float, default=0.0)
    args = parser.parse_args()
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = (PROJECT_ROOT / data_path).resolve()
    frame = load_data(data_path, SPEC)
    task = SPEC["design"]["task"]
    methods = list(SPEC["design"]["methods"])
    seeds = list(SPEC["design"]["seeds"]) if not args.seeds else list(range(args.seeds))
    ridge_alpha = float(args.ridge_alpha) if args.ridge_alpha and args.ridge_alpha > 0 else None
    if ridge_alpha is not None and "ridge" not in methods:
        raise ValueError("--ridge-alpha requires the ridge method")
    if args.dry_run:
        print(json.dumps({
            "status": "dry_run_ok",
            "rows": int(len(frame)),
            "features": SPEC["data"]["features"],
            "target": SPEC["data"]["target"],
            "task": task,
            "methods": methods,
            "seeds": seeds,
            "cv_folds": int(SPEC["design"].get("cv_folds") or 0),
            "ridge_alpha": ridge_alpha,
            "boundary": "dry run validates data/schema only; no model is trained",
        }, ensure_ascii=False, indent=2))
        return 0
    if len(seeds) < 3:
        print("warning: fewer than 3 seeds; variance will be weak", file=sys.stderr)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    prediction_rows = []
    cv_folds = int(SPEC["design"].get("cv_folds") or 0)
    for seed in seeds:
        folds = []
        if cv_folds >= 2:
            splitter = (
                StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)
                if task == "classification"
                else KFold(n_splits=cv_folds, shuffle=True, random_state=seed)
            )
            split_target = frame[SPEC["data"]["target"]] if task == "classification" else None
            folds = list(splitter.split(frame, split_target))
        else:
            train, test = train_test_split(
                frame, test_size=SPEC["design"]["test_size"], random_state=seed,
                shuffle=True,
            )
            folds = [(train.index, test.index)]
        for fold_index, (train_index, test_index) in enumerate(folds):
            train = frame.loc[train_index]
            test = frame.loc[test_index]
            for method in methods:
                model = build_model(method, task, seed, ridge_alpha)
                model.fit(train[SPEC["data"]["features"]], train[SPEC["data"]["target"]])
                predictions = model.predict(test[SPEC["data"]["features"]])
                rows.append({"seed": seed, "fold": fold_index, "method": method, "metrics": metrics_for(task, test[SPEC["data"]["target"]], predictions)})
                for index, value in zip(test.index, predictions):
                    prediction_rows.append({"row_index": int(index), "seed": seed, "fold": fold_index, "method": method, "prediction": value})
    metrics = aggregate(rows, methods)
    comparison = paired_comparison(rows, methods, SPEC["design"]["metric"])
    (out / "metrics.json").write_text(json.dumps({"by_seed": rows, "aggregate": metrics, "comparison": comparison}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metric_name = SPEC["design"]["metric"]
    table_rows = []
    for method, values in metrics.items():
        item = values.get(metric_name) or {}
        sequence = item.get("by_seed") or []
        mean = float(item.get("mean") or 0.0)
        std = float(item.get("std") or 0.0)
        half = 1.96 * std / math.sqrt(len(sequence)) if len(sequence) > 1 else 0.0
        table_rows.append({
            "method": method,
            "metric": metric_name,
            "mean": mean,
            "std": std,
            "ci95_low": mean - half,
            "ci95_high": mean + half,
            "n": len(sequence),
        })
    pd.DataFrame(table_rows).to_csv(out / "results-table.csv", index=False)
    table_lines = [
        "| method | metric | mean | std | 95% CI | n |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in table_rows:
        table_lines.append(
            "| %s | %s | %.4f | %.4f | [%.4f, %.4f] | %d |"
            % (row["method"], row["metric"], row["mean"], row["std"], row["ci95_low"], row["ci95_high"], row["n"])
        )
    (out / "results-table.md").write_text("\n".join(table_lines) + "\n", encoding="utf-8")
    pd.DataFrame(prediction_rows).to_csv(out / "predictions.csv", index=False)
    receipt = {
        "schema_version": "local-experiment-receipt-0.1",
        "experiment_id": SPEC["experiment_id"],
        "status": "completed_local",
        "created_at": now(),
        "data": str(data_path),
        "data_sha256": sha256_file(data_path),
        "spec_sha256": sha256_file(HERE / "experiment-spec.json"),
        "code_sha256": sha256_file(Path(__file__)),
        "seeds": seeds,
        "cv_folds": int(SPEC["design"].get("cv_folds") or 0),
        "methods": methods,
        "ridge_alpha": ridge_alpha,
        "metrics": metrics,
        "comparison": comparison,
        "results_table": "results-table.md",
        "boundary": "Local receipt only; not a RunCapsule, EA, Claim, gate or signature. Human review is required before any claim.",
    }
    (out / "run-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts = []
    for name in ("metrics.json", "predictions.csv", "results-table.csv", "results-table.md", "run-receipt.json"):
        path = out / name
        artifacts.append({"name": name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    (out / "artifact-manifest.json").write_text(json.dumps({"created_at": now(), "artifacts": artifacts}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed_local", "output_dir": str(out), "metrics": metrics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _sweep_source() -> str:
    return r"""#!/usr/bin/env python3
# Generated local parameter-sweep runner (planning profile).
# It explores the alpha grid recorded in experiment-spec.json and writes local
# sweep results only. It creates no RunCapsule, EA, Claim, gate or signature,
# and its results are not evidence until a separate sweep ingest profile exists.
import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, StratifiedKFold, train_test_split

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
SPEC = json.loads((HERE / "experiment-spec.json").read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_data(data_path, spec):
    target = spec["data"]["target"]
    features = list(spec["data"]["features"])
    if target in features:
        raise ValueError("target must not appear in features")
    frame = pd.read_csv(data_path)
    missing = [column for column in features + [target] if column not in frame.columns]
    if missing:
        raise ValueError("missing columns: " + ", ".join(missing))
    frame = frame[features + [target]].dropna().copy()
    if frame.empty:
        raise ValueError("no rows remain after dropping missing values")
    return frame


def metrics_for(task, y_true, y_pred):
    if task == "regression":
        return {
            "r2": float(r2_score(y_true, y_pred)),
            "mae": float(mean_absolute_error(y_true, y_pred)),
            "rmse": float(math.sqrt(mean_squared_error(y_true, y_pred))),
        }
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro")),
    }


def aggregate(rows, key, metric):
    grouped = {}
    for row in rows:
        grouped.setdefault(str(row[key]), []).append(row["metrics"][metric])
    output = {}
    for value, sequence in grouped.items():
        mean = sum(sequence) / len(sequence)
        variance = sum((item - mean) ** 2 for item in sequence) / len(sequence)
        output[value] = {"mean": mean, "std": math.sqrt(variance), "by_seed": sequence}
    return output


def main():
    parser = argparse.ArgumentParser(description="Generated local sweep runner (planning profile)")
    parser.add_argument("--data", default=SPEC["data"]["path"])
    parser.add_argument("--out", default=str(HERE / "outputs"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sweep = SPEC.get("sweep") or {}
    if not sweep:
        print("spec has no sweep plan; regenerate with an alpha grid", file=sys.stderr)
        return 2
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = (PROJECT_ROOT / data_path).resolve()
    frame = load_data(data_path, SPEC)
    task = SPEC["design"]["task"]
    metric = SPEC["design"]["metric"]
    seeds = list(SPEC["design"]["seeds"])
    values = list(sweep["values"])
    cv_folds = int(SPEC["design"].get("cv_folds") or 0)
    if args.dry_run:
        print(json.dumps({
            "status": "dry_run_ok",
            "rows": int(len(frame)),
            "parameter": sweep["parameter"],
            "values": values,
            "seeds": seeds,
            "cv_folds": cv_folds,
            "metric": metric,
            "budget": sweep.get("budget"),
            "boundary": "dry run validates data and the sweep plan only; no model is trained",
        }, ensure_ascii=False, indent=2))
        return 0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ridge_rows = []
    baseline_rows = []
    for seed in seeds:
        if cv_folds >= 2:
            splitter = (
                StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)
                if task == "classification"
                else KFold(n_splits=cv_folds, shuffle=True, random_state=seed)
            )
            split_target = frame[SPEC["data"]["target"]] if task == "classification" else None
            folds = list(splitter.split(frame, split_target))
        else:
            train, test = train_test_split(
                frame, test_size=SPEC["design"]["test_size"], random_state=seed, shuffle=True,
            )
            folds = [(train.index, test.index)]
        for fold_index, (train_index, test_index) in enumerate(folds):
            train = frame.loc[train_index]
            test = frame.loc[test_index]
            features = test[SPEC["data"]["features"]]
            truth = test[SPEC["data"]["target"]]
            dummy = DummyRegressor(strategy="mean") if task == "regression" else DummyClassifier(strategy="most_frequent")
            dummy.fit(train[SPEC["data"]["features"]], train[SPEC["data"]["target"]])
            baseline_rows.append({"seed": seed, "fold": fold_index, "metrics": metrics_for(task, truth, dummy.predict(features))})
            for alpha in values:
                if task != "regression":
                    raise ValueError("the sweep planning profile supports regression and ridge only")
                model = Ridge(alpha=float(alpha), random_state=seed)
                model.fit(train[SPEC["data"]["features"]], train[SPEC["data"]["target"]])
                ridge_rows.append({"alpha": alpha, "seed": seed, "fold": fold_index, "metrics": metrics_for(task, truth, model.predict(features))})
    alpha_summary = aggregate(ridge_rows, "alpha", metric)
    dummy_values = [item["metrics"][metric] for item in baseline_rows]
    dummy_mean = sum(dummy_values) / len(dummy_values)
    dummy_variance = sum((item - dummy_mean) ** 2 for item in dummy_values) / len(dummy_values)
    best_alpha = min(
        alpha_summary,
        key=lambda value: (-alpha_summary[value]["mean"], alpha_summary[value]["std"]),
    )
    result = {
        "schema_version": "experiment-sweep-results-0.1",
        "experiment_id": SPEC["experiment_id"],
        "parameter": sweep["parameter"],
        "values": values,
        "seeds": seeds,
        "cv_folds": cv_folds,
        "metric": metric,
        "rows": ridge_rows,
        "aggregate": alpha_summary,
        "baseline": {
            "method": "dummy",
            "mean": dummy_mean,
            "std": math.sqrt(dummy_variance),
            "by_seed": dummy_values,
        },
        "selection": {
            "best_alpha": float(best_alpha),
            "rule": sweep.get("selection"),
            "stopping_rule": sweep.get("stopping_rule"),
        },
        "created_at": now(),
        "boundary": "Local sweep results only; not an EA, Claim, gate or signature. Not evidence until a sweep ingest profile exists.",
    }
    results_path = out / "sweep-results.json"
    results_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": "local-sweep-receipt-0.1",
        "experiment_id": SPEC["experiment_id"],
        "status": "completed_local",
        "created_at": now(),
        "data": str(data_path),
        "data_sha256": sha256_file(data_path),
        "spec_sha256": sha256_file(HERE / "experiment-spec.json"),
        "code_sha256": sha256_file(Path(__file__)),
        "seeds": seeds,
        "cv_folds": cv_folds,
        "parameter": sweep["parameter"],
        "values": values,
        "selection": result["selection"],
        "boundary": "Local sweep receipt only; not a RunCapsule, EA, Claim, gate or signature. Human review is required.",
    }
    (out / "sweep-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts = []
    for name in ("sweep-results.json", "sweep-receipt.json"):
        path = out / name
        artifacts.append({"name": name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    (out / "sweep-artifact-manifest.json").write_text(json.dumps({"created_at": now(), "artifacts": artifacts}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed_local", "output_dir": str(out), "selection": result["selection"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _readme(spec: Dict[str, Any]) -> str:
    methods = ", ".join(spec["design"]["methods"])
    seeds = ", ".join(str(seed) for seed in spec["design"]["seeds"])
    return """# Generated experiment: %s

- experiment id: `%s`
- hypothesis: %s
- data: `%s`
- target: `%s`
- features: %s
- methods: %s
- seeds: %s
- cv folds: %s
- task: %s
- design status: `%s`
- boundary: **not a RunCapsule/EA/Claim**. The agent generated code only; it did not run the experiment.

## Local execution

Run this in your approved local environment after G2/human review:

```bash
python -m pip install -r requirements.txt
python run_experiment.py --dry-run
python run_experiment.py --data %s --out outputs
```

Paths in `--data` are resolved relative to the project root. Expected outputs: `metrics.json`, `predictions.csv`, `results-table.csv/.md`, `run-receipt.json`, `artifact-manifest.json`.

Do not treat the receipt as a signed Claim. A human must review the design, data, seeds and metrics before the claim process.
""" % (
        spec["title"],
        spec["experiment_id"],
        spec["hypothesis"],
        spec["data"]["path"],
        spec["data"]["target"],
        ", ".join(spec["data"]["features"]),
        methods,
        seeds,
        spec["design"].get("cv_folds", 0),
        spec["design"]["task"],
        spec["design"]["status"],
        spec["data"]["path"],
    ) + (
        "\n## Data audit\n\n- status: `%s`\n%s\n"
        % (
            (spec.get("data_audit") or {}).get("status", "missing"),
            "\n".join(
                "- " + warning
                for warning in (spec.get("data_audit") or {}).get("warnings") or []
            )
            or "- no warnings",
        )
    ) + (
        """

## Parameter sweep (planning profile)

- parameter: `ridge_alpha`; values: %s
- budget: %s; stopping rule: %s
- boundary: sweep execution is **not wired** to experiment approve/run/ingest in this version; `run_sweep.py` is local-only and its results cannot become evidence or a claim.

```bash
python run_sweep.py --dry-run
python run_sweep.py --data %s --out outputs
```
"""
        % (
            ", ".join(str(value) for value in spec["sweep"]["values"]),
            spec["sweep"].get("budget"),
            spec["sweep"].get("stopping_rule"),
            spec["data"]["path"],
        )
        if spec.get("sweep")
        else ""
    )


def generate_experiment_code(
    project: Path,
    run_id: str,
    *,
    data_path: str,
    target: str,
    features: List[str],
    task: str = "regression",
    methods: Optional[List[str]] = None,
    metric: str = "",
    experiment_id: str = "",
    test_size: float = 0.2,
    seeds: int = 3,
    cv_folds: int = 0,
    alpha_grid: Optional[List[float]] = None,
    output_root: Optional[Path] = None,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    target_run = run_dir(project, run_id)
    if not target_run.is_dir():
        raise ExperimentCodegenError("run does not exist: " + run_id)
    design = read_json(target_run / "experiment.json") if (target_run / "experiment.json").is_file() else {}
    if not isinstance(design, dict):
        raise ExperimentCodegenError("experiment.json is missing or invalid")
    if task not in SUPPORTED_METRICS:
        raise ExperimentCodegenError("unsupported task: " + task)
    features = [str(item).strip() for item in features if str(item).strip()]
    if not features:
        raise ExperimentCodegenError("at least one feature column is required")
    if target in features:
        raise ExperimentCodegenError("target must not appear in features")
    data_full = Path(data_path)
    if not data_full.is_absolute():
        data_full = (project / data_full).resolve()
    try:
        data_full.relative_to(project)
    except ValueError:
        raise ExperimentCodegenError("data path must stay inside the project")
    if not data_full.is_file():
        raise ExperimentCodegenError("data table does not exist: " + str(data_full))
    header = _read_csv_header(data_full)
    try:
        with open(str(data_full), "r", encoding="utf-8-sig") as handle:
            row_count = max(0, sum(1 for _ in handle) - 1)
    except OSError:
        row_count = 0
    missing = [column for column in features + [target] if column not in header]
    if missing:
        raise ExperimentCodegenError("data table is missing columns: " + ", ".join(missing))
    methods = [str(item).strip().lower() for item in (methods or ["dummy", "ridge"]) if str(item).strip()]
    if len(set(methods)) < 2:
        raise ExperimentCodegenError("at least two distinct methods are required (baseline + method)")
    for method in methods:
        if method not in SUPPORTED_METHODS:
            raise ExperimentCodegenError("unsupported method: " + method)
        if method == "ridge" and task != "regression":
            raise ExperimentCodegenError("ridge is only supported for regression")
        if method == "logistic" and task != "classification":
            raise ExperimentCodegenError("logistic is only supported for classification")
    allowed_metrics = SUPPORTED_METRICS[task]
    metric = metric or allowed_metrics[0]
    if metric not in allowed_metrics:
        raise ExperimentCodegenError("unsupported metric %s for %s" % (metric, task))
    seeds = max(1, min(int(seeds), 10))
    cv_folds = max(0, min(int(cv_folds or 0), 10))
    if cv_folds == 1:
        raise ExperimentCodegenError("cv_folds must be 0 or at least 2")
    sweep: Dict[str, Any] = {}
    if alpha_grid:
        if task != "regression" or "ridge" not in methods:
            raise ExperimentCodegenError(
                "alpha_grid requires a regression task with the ridge method"
            )
        values = []
        for item in alpha_grid:
            try:
                value = float(item)
            except (TypeError, ValueError):
                raise ExperimentCodegenError("alpha values must be numbers")
            if not math.isfinite(value) or value <= 0:
                raise ExperimentCodegenError("alpha values must be finite and positive")
            values.append(round(value, 6))
        values = sorted(set(values))
        if len(values) < 2:
            raise ExperimentCodegenError("alpha_grid needs at least two distinct values")
        if len(values) > 8:
            raise ExperimentCodegenError("alpha_grid supports at most eight values")
        sweep = {
            "parameter": "ridge_alpha",
            "values": values,
            "selection": "max mean %s across seeds; tie-break min std" % metric,
            "budget": "%d configs x %d seeds" % (len(values), seeds),
            "stopping_rule": "fixed grid over ridge alpha; no early stopping, no adaptive search",
            "status": "planned_local_only",
            "note": (
                "Sweep planning and code generation only. Execution is not wired to "
                "experiment approve/run/ingest in this version; run_sweep.py is local-only "
                "and its results cannot become evidence or a claim."
            ),
        }
    data_audit = audit_tabular_data(data_full, target, features, task)
    warnings = list(data_audit.get("warnings") or [])
    if seeds < 3:
        warnings.append("fewer than 3 seeds; variance/CI will be weak")
    if not 0.05 <= float(test_size) <= 0.5:
        raise ExperimentCodegenError("test_size must be in 0.05..0.5")
    experiment_id = _safe_id(experiment_id or "EXP-" + run_id)
    output_root = Path(output_root) if output_root else project / "experiments"
    output_dir = output_root / experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)
    seed_list = list(range(seeds))
    spec = {
        "schema_version": SPEC_SCHEMA,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "idea_id": str(design.get("idea_id") or ""),
        "title": _clean(design.get("hypothesis") or experiment_id, 200),
        "hypothesis": _clean(design.get("hypothesis") or "draft_hypothesis", 800),
        "data": {
            "path": str(data_full.relative_to(project)).replace("\\", "/"),
            "sha256": _sha256(data_full.read_bytes()),
            "target": target,
            "features": features,
            "rows": row_count,
        },
        "design": {
            "task": task,
            "status": "draft_needs_g2",
            "methods": methods,
            "metric": metric,
            "test_size": float(test_size),
            "seeds": seed_list,
            "cv_folds": cv_folds,
            "controls": design.get("controls") or [],
            "budget": design.get("budget") or "unspecified",
            "stopping_rule": design.get("stopping_rule") or "fixed seeds / fixed split; no post-hoc changes",
            "analysis_plan": "report mean/std by method across seeds; no significance or SOTA claim",
        },
        "data_audit": data_audit,
        "warnings": warnings,
        "boundary": (
            "Generated local experiment package. It is not a RunCapsule/EA/Claim/gate. "
            "Execution must be explicitly authorized by the user in their local environment."
        ),
    }
    if sweep:
        spec["sweep"] = sweep
    write_json_atomic(output_dir / "experiment-spec.json", spec)
    (output_dir / "run_experiment.py").write_text(_runner_source(), encoding="utf-8")
    if sweep:
        (output_dir / "run_sweep.py").write_text(_sweep_source(), encoding="utf-8")
    (output_dir / "requirements.txt").write_text("pandas\nscikit-learn\n", encoding="utf-8")
    (output_dir / "README.md").write_text(_readme(spec), encoding="utf-8")
    files = []
    generated_names = ["experiment-spec.json", "run_experiment.py"]
    if sweep:
        generated_names.append("run_sweep.py")
    generated_names += ["requirements.txt", "README.md"]
    for name in generated_names:
        path = output_dir / name
        files.append({"name": name, "sha256": _sha256(path.read_bytes()), "bytes": path.stat().st_size})
    manifest = {
        "schema_version": CODEGEN_SCHEMA,
        "experiment_id": experiment_id,
        "created_at": _now(),
        "run_id": run_id,
        "files": files,
        "execution": "not_run",
        "boundary": spec["boundary"],
    }
    write_json_atomic(output_dir / "code-manifest.json", manifest)
    return {
        "status": "generated",
        "experiment_id": experiment_id,
        "output_dir": str(output_dir),
        "files": {item["name"]: str(output_dir / item["name"]) for item in files},
        "execution": "not_run",
        "warnings": warnings,
        "data_audit": data_audit,
        "spec": spec,
        "sweep": sweep or None,
        "manifest": manifest,
        "next_action": (
            "Review the sweep plan, then run locally after G2/human approval: "
            "python run_sweep.py --dry-run (sweep results stay local-only in this version)"
            if sweep
            else "Review the spec and run locally after G2/human approval: python run_experiment.py --dry-run"
        ),
    }
