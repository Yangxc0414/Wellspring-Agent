"""S5 local execution: frozen protocol -> RunCapsule -> EA -> human-gated Claim."""

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..contracts import ClaimAssertion, ClaimRecord, EvidenceArtifact, RunCapsule, RunRequest
from ..specs import ModuleSpec


class RunError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _bound_protocol_sha(request: RunRequest, recipe_sha: str) -> str:
    supplied = (request.protocol_sha256 or "").strip().lower()
    if not supplied:
        return recipe_sha
    if len(supplied) != 64 or any(char not in "0123456789abcdef" for char in supplied):
        raise RunError("protocol_sha256 must be 64 lowercase hex characters")
    return supplied


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _metric_value(capsule: Dict[str, Any], metrics: List[Dict[str, Any]], metric: str) -> Optional[float]:
    requested = (metric or str(capsule.get("metric_name") or "")).strip()
    if not requested:
        return None
    if requested in ("mean", str(capsule.get("metric_name") or "")):
        if isinstance(capsule.get("mean"), (int, float)):
            return float(capsule["mean"])
    values = [
        float(item[requested]) for item in metrics
        if isinstance(item, dict) and isinstance(item.get(requested), (int, float))
    ]
    if values:
        return sum(values) / len(values)
    if isinstance(capsule.get("mean"), (int, float)):
        return float(capsule["mean"])
    return None


def _compare(observed: float, comparator: str, expected: float, tolerance: float) -> bool:
    delta = abs(observed - expected)
    if comparator == ">=":
        return observed >= expected - tolerance
    if comparator == "<=":
        return observed <= expected + tolerance
    if comparator == ">":
        return observed > expected + tolerance
    if comparator == "<":
        return observed < expected - tolerance
    if comparator == "==":
        return delta <= tolerance
    if comparator == "approx":
        return delta <= tolerance
    raise ValueError("unsupported comparator: " + comparator)


def verify_claim_assertions(
    capsule: Dict[str, Any],
    metrics: List[Dict[str, Any]],
    assertions: List[Any],
) -> List[Dict[str, Any]]:
    """Recompute structured numerical assertions from a completed capsule.

    This is intentionally deterministic and local: a claim cannot be supported
    by prose alone. The verifier is shared by `run claim` and `closure check`.
    """
    results: List[Dict[str, Any]] = []
    for raw in assertions:
        item = raw if isinstance(raw, dict) else asdict(raw)
        metric = str(item.get("metric") or "")
        observed = _metric_value(capsule, metrics, metric)
        expected_raw = item.get("value")
        expected = float(expected_raw) if isinstance(expected_raw, (int, float)) else None
        comparator = str(item.get("comparator") or ">=")
        tolerance = float(item.get("tolerance") or 0.0)
        passed = False
        if observed is not None and expected is not None:
            passed = _compare(observed, comparator, expected, tolerance)
        results.append({
            "claim_type": str(item.get("claim_type") or "numerical"),
            "metric": metric or str(capsule.get("metric_name") or ""),
            "comparator": comparator,
            "expected": expected,
            "observed": observed,
            "tolerance": tolerance,
            "condition": str(item.get("condition") or ""),
            "status": "pass" if passed else "fail",
        })
    return results


def _dataset_scope(capsule: Dict[str, Any]) -> str:
    dataset = str(capsule.get("dataset_id", ""))
    if dataset.startswith("chemlab:morgan:376train"):
        return "S5/confirm/chemlab_holdout"
    if dataset.startswith("chemlab:morgan:"):
        return "S5/demo/chemlab"
    if dataset.startswith("sklearn:breast_cancer:"):
        return "S5/demo/breast_cancer"
    if dataset.startswith("sklearn:iris:"):
        return "S5/demo/iris"
    raise RunError("cannot derive claim scope from dataset_id: " + dataset)


class RunAgent:
    module_id = "run"

    def __init__(self, spec: ModuleSpec):
        if spec.id != self.module_id:
            raise RunError("spec id must be 'run', got '%s'" % spec.id)
        self.spec = spec

    def execute(self, request: RunRequest, output_dir: Path) -> Dict[str, Any]:
        if self.spec.status in ("revoked", "deprecated"):
            raise RunError("module spec status is %s; refusing to run" % self.spec.status)
        # ExecPort 路由分派（71-§5 步 5 收口）：inprocess 面的 S5 协议执行经端口
        # 门禁 + 溯源。端口只记录 provenance，不改变执行语义。
        try:
            from ..execport.exec_port import begin_dispatch, end_dispatch

            _exec_ticket = begin_dispatch("inprocess", subject="%s/%s" % (request.dataset, request.model))
        except Exception:
            _exec_ticket = None
            end_dispatch = None
        try:
            return self._execute_dispatched(request, output_dir, _exec_ticket, end_dispatch)
        except Exception:
            if _exec_ticket:
                end_dispatch(_exec_ticket, "failed")
            raise

    def _execute_dispatched(self, request: RunRequest, output_dir: Path, _exec_ticket, end_dispatch) -> Dict[str, Any]:
        if self.spec.status in ("revoked", "deprecated"):
            raise RunError("module spec status is %s; refusing to run" % self.spec.status)
        if request.dataset not in ("iris", "breast_cancer", "chemlab"):
            raise RunError("only local iris/breast_cancer/chemlab protocol-validation datasets are supported")
        if request.split != "demo" and request.dataset != "chemlab":
            raise RunError("split is only supported for chemlab")
        if request.seeds < 1 or request.seeds > 10:
            raise RunError("seeds must be in 1..10")
        if not 0.1 <= request.test_size <= 0.5:
            raise RunError("test_size must be in 0.1..0.5")
        if request.dataset == "chemlab":
            if request.model not in ("ridge", "logistic_regression"):
                raise RunError("chemlab supports ridge")
            if request.metric not in ("r2", "accuracy"):
                raise RunError("chemlab supports r2")
            return self._execute_chemlab(request, Path(output_dir), _exec_ticket, end_dispatch)
        if request.model != "logistic_regression":
            raise RunError("only logistic_regression is supported")
        if request.metric != "accuracy":
            raise RunError("only accuracy is supported")

        import numpy as np
        import sklearn
        from sklearn.datasets import load_breast_cancer, load_iris
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        data = load_iris() if request.dataset == "iris" else load_breast_cancer()
        dataset_id = "sklearn:iris:150x4" if request.dataset == "iris" else "sklearn:breast_cancer:569x30"
        dataset_bytes = (
            np.asarray(data.data, dtype=np.float64).tobytes()
            + np.asarray(data.target, dtype=np.int64).tobytes()
            + "|".join(str(name) for name in data.feature_names).encode("utf-8")
        )
        dataset_sha = _sha256_bytes(dataset_bytes)
        code_sha = _sha256_file(Path(__file__))
        protocol_payload = json.dumps({
            "dataset": request.dataset,
            "model": request.model,
            "seeds": request.seeds,
            "test_size": request.test_size,
            "metric": request.metric,
        }, sort_keys=True).encode("utf-8")
        protocol_sha = _bound_protocol_sha(request, _sha256_bytes(protocol_payload))
        run_id = request.run_id or "RUN-%s-%s" % (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), uuid.uuid4().hex[:6]
        )

        metrics: List[Dict[str, Any]] = []
        for offset in range(request.seeds):
            seed = 17 + offset
            x_train, x_test, y_train, y_test = train_test_split(
                data.data, data.target, test_size=request.test_size,
                random_state=seed, stratify=data.target,
            )
            model = make_pipeline(
                StandardScaler(),
                LogisticRegression(max_iter=500, random_state=seed),
            )
            model.fit(x_train, y_train)
            score = float(model.score(x_test, y_test))
            metrics.append({"seed": seed, "accuracy": score})

        values = [item["accuracy"] for item in metrics]
        mean = float(np.mean(values))
        std = float(np.std(values))
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = output_dir / "metrics.json"
        _write_json(metrics_path, metrics)
        capsule_path = output_dir / "run-capsule.json"
        capsule = RunCapsule(
            run_id=run_id,
            protocol_id=request.protocol_id,
            protocol_sha256=protocol_sha,
            dataset_id=dataset_id,
            dataset_sha256=dataset_sha,
            code_sha256=code_sha,
            model=request.model,
            seeds=[item["seed"] for item in metrics],
            test_size=request.test_size,
            metric_name=request.metric,
            metrics_by_seed=metrics,
            mean=mean,
            std=std,
            environment={
                "python": "%d.%d.%d" % __import__("sys").version_info[:3],
                "sklearn": sklearn.__version__,
                "numpy": np.__version__,
            },
            status="completed",
            artifacts={"metrics": str(metrics_path), "capsule": str(capsule_path)},
            created_at=_now(),
            warnings=[
                "%s is a protocol-validation dataset; not thesis scientific evidence" % request.dataset,
                "single dataset/model; no generalization or SOTA claim",
            ],
        )
        _write_json(capsule_path, asdict(capsule))
        ea = EvidenceArtifact(
            artifact_id="EA-" + _sha256_bytes((run_id + _sha256_file(metrics_path)).encode("utf-8"))[:12],
            kind="metric",
            run_id=run_id,
            path=str(metrics_path),
            sha256=_sha256_file(metrics_path),
            source="run",
            captured_at=_now(),
            immutable=True,
            scope=_dataset_scope(asdict(capsule)),
        )
        ea_path = output_dir / "ea.json"
        _write_json(ea_path, asdict(ea))
        if _exec_ticket and end_dispatch:
            end_dispatch(_exec_ticket, "completed")
        return {"capsule": asdict(capsule), "evidence": asdict(ea), "paths": {
            "capsule": str(capsule_path), "metrics": str(metrics_path), "ea": str(ea_path),
        }}


    def _execute_chemlab(self, request: RunRequest, output_dir: Path, _exec_ticket=None, end_dispatch=None) -> Dict[str, Any]:
        import numpy as np
        import pandas as pd
        import sklearn
        from sklearn.dummy import DummyRegressor
        from sklearn.linear_model import Ridge
        from sklearn.metrics import mean_absolute_error, r2_score

        fixture = Path(__file__).resolve().parents[2] / "modules" / "run" / "fixtures" / "chemlab"
        if request.split not in ("demo", "holdout"):
            raise RunError("chemlab split must be demo or holdout")
        train_path = fixture / ("%s_train_Morgan_fingerprints.csv" % request.split)
        test_path = fixture / ("%s_test_Morgan_fingerprints.csv" % request.split)
        train = pd.read_csv(train_path)
        test = pd.read_csv(test_path)

        def bits(series):
            # parse CSV independently of pandas/numpy version: trailing \r from a CRLF
            # file must never leak into a fingerprint, and ragged widths must fail with
            # a named row instead of an opaque numpy stack error
            encoded = [str(value).strip().encode("ascii") for value in series]
            widths = {}
            for index, item in enumerate(encoded):
                widths.setdefault(len(item), index)
            if len(widths) > 1:
                raise RunError(
                    "chemlab fingerprint widths differ: %s (first offending row %d)"
                    % (sorted(widths), min(index for _, index in sorted(widths.items())))
                )
            return np.stack([np.frombuffer(value, dtype=np.uint8) for value in encoded]).astype(np.float32) - 48.0

        x_train = np.concatenate([bits(train["B_Fingerprint"]), bits(train["C_Fingerprint"])], axis=1)
        x_test = np.concatenate([bits(test["B_Fingerprint"]), bits(test["C_Fingerprint"])], axis=1)
        y_train = train.iloc[:, 3].to_numpy(dtype=np.float64)
        y_test = test.iloc[:, 3].to_numpy(dtype=np.float64)

        dataset_sha = _sha256_bytes(
            train_path.read_bytes() + test_path.read_bytes()
            + "|".join(train.columns).encode("utf-8")
        )
        code_sha = _sha256_file(Path(__file__))
        validation_fraction = min(max(float(request.test_size), 0.05), 0.6)
        fit_fraction = 1.0 - validation_fraction
        protocol_sha = _bound_protocol_sha(request, _sha256_bytes(json.dumps({
            "dataset": "chemlab", "model": "ridge", "seeds": request.seeds,
            "split": request.split, "fit_fraction": round(fit_fraction, 6), "metric": "r2",
        }, sort_keys=True).encode("utf-8")))
        run_id = request.run_id or "RUN-%s-%s" % (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), uuid.uuid4().hex[:6]
        )
        metrics = []
        for offset in range(request.seeds):
            seed = 17 + offset
            rng = np.random.default_rng(seed)
            # test_size is the internal validation fraction here; ignoring it made
            # every S5 task reuse the same 80% fit subset and turned the gate vacuous.
            size = max(2, int(len(x_train) * fit_fraction))
            indices = rng.choice(len(x_train), size=size, replace=False)
            model = Ridge(alpha=1.0)
            model.fit(x_train[indices], y_train[indices])
            prediction = model.predict(x_test)
            baseline = DummyRegressor(strategy="mean")
            baseline.fit(x_train[indices], y_train[indices])
            baseline_prediction = baseline.predict(x_test)
            r2 = float(r2_score(y_test, prediction))
            baseline_r2 = float(r2_score(y_test, baseline_prediction))
            metrics.append({
                "seed": seed,
                "r2": r2,
                "baseline_r2": baseline_r2,
                "delta_r2": r2 - baseline_r2,
                "mae": float(mean_absolute_error(y_test, prediction)),
                "baseline_mae": float(mean_absolute_error(y_test, baseline_prediction)),
                "n_fit": int(size),
            })
        values = [item["r2"] for item in metrics]
        mean = float(np.mean(values))
        std = float(np.std(values))
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = output_dir / "metrics.json"
        _write_json(metrics_path, metrics)
        capsule_path = output_dir / "run-capsule.json"
        capsule = RunCapsule(
            run_id=run_id,
            protocol_id=request.protocol_id,
            protocol_sha256=protocol_sha,
            dataset_id=(
                "chemlab:morgan:418train+22test" if request.split == "demo"
                else "chemlab:morgan:376train+42holdout"
            ),
            dataset_sha256=dataset_sha,
            code_sha256=code_sha,
            model="ridge",
            seeds=[item["seed"] for item in metrics],
            test_size=request.test_size,
            metric_name="r2",
            metrics_by_seed=metrics,
            mean=mean,
            std=std,
            environment={
                "python": "%d.%d.%d" % __import__("sys").version_info[:3],
                "sklearn": sklearn.__version__,
                "numpy": np.__version__,
                "pandas": pd.__version__,
            },
            status="completed",
            artifacts={"metrics": str(metrics_path), "capsule": str(capsule_path)},
            created_at=_now(),
            warnings=[
                "ChemLab reaction-conversion data is real but only used for protocol validation",
                "controlled comparison: Ridge vs mean baseline on Morgan fingerprints; baseline protocol only, not a novel scientific result",
                "split=%s; holdout reactions were never used as test data during admission" % request.split,
            ],
        )
        _write_json(capsule_path, asdict(capsule))
        ea = EvidenceArtifact(
            artifact_id="EA-" + _sha256_bytes((run_id + _sha256_file(metrics_path)).encode("utf-8"))[:12],
            kind="metric",
            run_id=run_id,
            path=str(metrics_path),
            sha256=_sha256_file(metrics_path),
            source="run",
            captured_at=_now(),
            immutable=True,
            scope=_dataset_scope(asdict(capsule)),
        )
        ea_path = output_dir / "ea.json"
        _write_json(ea_path, asdict(ea))
        if _exec_ticket and end_dispatch:
            end_dispatch(_exec_ticket, "completed")
        return {"capsule": asdict(capsule), "evidence": asdict(ea), "paths": {
            "capsule": str(capsule_path), "metrics": str(metrics_path), "ea": str(ea_path),
        }}

    def claim(
        self,
        capsule_path: Path,
        ea_path: Path,
        statement: str,
        human_reason: str,
        scope: str,
        output_dir: Path,
        assertions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if not statement.strip():
            raise RunError("claim statement is required")
        if not human_reason.strip():
            raise RunError("human_reason is required; claims are never auto-created")
        if not scope.strip():
            raise RunError("claim scope is required")
        capsule = json.loads(Path(capsule_path).read_text(encoding="utf-8"))
        evidence = json.loads(Path(ea_path).read_text(encoding="utf-8"))
        if capsule.get("status") != "completed":
            raise RunError("only a completed run can support a claim")
        if evidence.get("run_id") != capsule.get("run_id"):
            raise RunError("EA run_id does not match capsule")
        if not evidence.get("immutable") or evidence.get("source") != "run":
            raise RunError("EA must be immutable and run-sourced")
        metrics_path = Path(evidence.get("path", ""))
        if not metrics_path.is_file() or _sha256_file(metrics_path) != evidence.get("sha256"):
            raise RunError("EA sha256 does not match the metrics artifact")
        expected_scope = str(evidence.get("scope", ""))
        if scope.strip() != expected_scope:
            raise RunError(
                "claim scope %r does not match EA scope %r" % (scope.strip(), expected_scope)
            )
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        if not isinstance(metrics, list):
            raise RunError("metrics artifact must be a JSON list")
        assertion_inputs = list(assertions or [])
        verified = verify_claim_assertions(capsule, metrics, assertion_inputs)
        failures = [item for item in verified if item["status"] != "pass"]
        if failures:
            raise RunError(
                "claim assertion failed: "
                + "; ".join(
                    "%s expected %s %s but observed %s"
                    % (
                        item.get("metric") or "metric",
                        item.get("comparator"),
                        item.get("expected"),
                        item.get("observed"),
                    )
                    for item in failures
                )
            )
        claim_type = "numerical" if verified else "conclusion"
        warnings = [
            "claim scope %s covers one protocol-validation run" % expected_scope,
            "not a thesis result and not a peer-reviewed finding",
        ]
        if not verified:
            warnings.append(
                "legacy claim has no structured assertions; numeric support was not re-verified"
            )
        else:
            warnings.append(
                "%d numerical assertion(s) recomputed from metrics artifact" % len(verified)
            )
        claim = ClaimRecord(
            claim_id="CLM-" + uuid.uuid4().hex[:10],
            statement=statement.strip(),
            evidence_refs=[str(evidence.get("artifact_id"))],
            scope=scope.strip(),
            status="supported",
            human_reason=human_reason.strip(),
            created_at=_now(),
            warnings=warnings,
            claim_type=claim_type,
            assertions=[
                ClaimAssertion(
                    claim_type=item["claim_type"],
                    metric=item["metric"],
                    comparator=item["comparator"],
                    value=item["expected"],
                    tolerance=item["tolerance"],
                    observed=item["observed"],
                    status=item["status"],
                    condition=item["condition"],
                )
                for item in verified
            ],
            verification={
                "source": str(metrics_path),
                "checked": len(verified),
                "passed": len(verified) - len(failures),
                "failed": len(failures),
                "run_id": capsule.get("run_id"),
                "ea_id": evidence.get("artifact_id"),
            },
        )
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "claim.json"
        _write_json(path, asdict(claim))
        return {"claim": asdict(claim), "path": str(path)}
