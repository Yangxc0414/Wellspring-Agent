"""S4 experiment design: produce a pre-registration-shaped design card."""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..contracts import seed_count, ExperimentDesign, ProtocolCard
from ..flow import design_sha256
from ..models import ModelRequiredError
from ..specs import ModuleSpec


class ExperimentError(RuntimeError):
    pass


@dataclass
class ExperimentRequest:
    question: str
    hypothesis: str = ""
    baseline: str = ""
    primary_metric: str = ""
    controls: List[str] = field(default_factory=list)
    seeds: int = 3
    budget: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    evidence: List[Dict[str, str]] = field(default_factory=list)
    language: str = "zh"
    idea_id: str = ""
    run_id: str = ""


ExperimentDesigner = Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]


class ExperimentDesignAgent:
    module_id = "experiment"

    def __init__(
        self,
        spec: ModuleSpec,
        designer: Optional[ExperimentDesigner] = None,
        strict_model: bool = False,
    ):
        if spec.id != self.module_id:
            raise ExperimentError("spec id must be 'experiment'")
        self.spec = spec
        self.designer = designer
        self.strict_model = strict_model

    def _run_id(self, provided: str) -> str:
        if provided:
            return provided
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return "DESIGN-%s-%s" % (stamp, uuid.uuid4().hex[:6])

    @staticmethod
    def _is_missing(value: Any) -> bool:
        text = str(value or "").strip()
        return not text or text in ("待人工补全", "待补全", "TODO", "TBD")

    def _designer_payload(self, request: ExperimentRequest, current: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "question": request.question,
            "language": request.language,
            "current": current,
            "evidence": [
                {
                    "ref": item.get("ref", ""),
                    "section": item.get("section", ""),
                    "text": str(item.get("text", ""))[:500],
                }
                for item in request.evidence[:12]
            ],
        }

    def _apply_model_draft(
        self, draft: Dict[str, Any], current: Dict[str, Any]
    ) -> Dict[str, Any]:
        accepted: Dict[str, Any] = {}
        for key in ("hypothesis", "baseline", "primary_metric", "budget"):
            if not self._is_missing(current.get(key)):
                continue
            value = str(draft.get(key) or "").strip()
            if 3 <= len(value) <= 600:
                accepted[key] = value
        if not current.get("controls"):
            raw_controls = draft.get("controls")
            if isinstance(raw_controls, list):
                controls = [
                    str(item).strip()[:200]
                    for item in raw_controls
                    if str(item).strip()
                ][:5]
                if controls:
                    accepted["controls"] = controls
        return accepted

    def run(self, request: ExperimentRequest) -> ExperimentDesign:
        if self.spec.status in ("revoked", "deprecated"):
            raise ExperimentError("module spec status is %s; refusing to run" % self.spec.status)
        if request.language not in ("zh", "en"):
            raise ExperimentError("language must be zh or en")
        warnings = [
            "design draft only; G2 must be signed by a human",
            "no run, no metric, no Claim is produced by this module",
        ]
        hypothesis = request.hypothesis
        baseline = request.baseline
        primary_metric = request.primary_metric
        budget = request.budget
        controls = list(request.controls)
        model_fields: List[str] = []

        current = {
            "hypothesis": hypothesis,
            "baseline": baseline,
            "primary_metric": primary_metric,
            "controls": controls,
            "budget": budget,
        }
        missing_before = [
            key for key, value in current.items()
            if self._is_missing(value) and key != "controls"
        ]
        if not controls:
            missing_before.append("controls")
        if self.strict_model and self.designer is None and missing_before:
            raise ModelRequiredError("strict experiment mode requires a model designer")
        if self.designer is not None and missing_before and not request.evidence:
            # Span-only invariant: an ungrounded design request would only invite invention.
            warnings.append(
                "experiment designer skipped: no span-level evidence to ground a model design"
            )
        if self.designer is not None and missing_before and request.evidence:
            try:
                draft = self.designer(self._designer_payload(request, current))
            except Exception as exc:
                if isinstance(exc, ModelRequiredError):
                    raise
                if self.strict_model:
                    raise ModelRequiredError(
                        "experiment designer failed: %s" % type(exc).__name__
                    )
                draft = None
                warnings.append("experiment designer failed: %s" % type(exc).__name__)
            if isinstance(draft, dict):
                accepted = self._apply_model_draft(draft, current)
                model_fields = sorted(accepted)
                hypothesis = accepted.get("hypothesis", hypothesis)
                baseline = accepted.get("baseline", baseline)
                primary_metric = accepted.get("primary_metric", primary_metric)
                budget = accepted.get("budget", budget)
                controls = list(accepted.get("controls", controls))
                if model_fields:
                    warnings.append(
                        "model-drafted fields require human confirmation: "
                        + ", ".join(model_fields)
                    )
                elif self.strict_model:
                    raise ModelRequiredError(
                        "experiment designer returned no usable fields"
                    )
            else:
                if self.strict_model:
                    raise ModelRequiredError("experiment designer returned no usable draft")
                warnings.append("experiment designer returned no usable draft")

        required = {
            "hypothesis": hypothesis,
            "baseline": baseline,
            "primary_metric": primary_metric,
            "budget": budget,
        }
        missing = [key for key, value in required.items() if self._is_missing(value)]
        if missing:
            warnings.append("missing pre-registration fields: " + ", ".join(missing))
        if not controls:
            warnings.append("no negative/positive control supplied")
        if self.strict_model and (missing or not controls):
            raise ModelRequiredError(
                "experiment designer did not produce a complete pre-registration draft"
            )
        seeds = max(1, int(request.seeds))
        if seeds < 3:
            warnings.append("fewer than 3 seeds; variance/CI will be weak")
        stopping_rule = "预注册后由人冻结；主指标、样本量、停止条件不得事后修改"
        status = "ready_for_g2" if not missing and controls and not model_fields else "needs_human"
        if model_fields:
            warnings.append(
                "model-drafted design stays needs_human until a human confirms it; no automatic G2"
            )
        if self.spec.status != "active":
            warnings.append("spec status=%s; development-only" % self.spec.status)
        return ExperimentDesign(
            design_id=self._run_id(request.run_id),
            question=request.question,
            hypothesis=hypothesis or "待人工补全",
            baseline=baseline or "待人工补全",
            primary_metric=primary_metric or "待人工补全",
            controls=controls,
            seeds=seeds,
            budget=budget or "待人工补全",
            stopping_rule=stopping_rule,
            evidence_refs=list(request.evidence_refs),
            status=status,
            warnings=warnings,
            idea_id=request.idea_id,
        )

    def freeze_design(
        self,
        design: Dict[str, Any],
        limitation: str,
        human_reason: str,
        output_dir: Path,
    ) -> Dict[str, Any]:
        """Freeze the design before S5; does not require a RunCapsule."""
        if design.get("status") != "ready_for_g2":
            raise ExperimentError("design must be ready_for_g2 before freezing")
        if not limitation.strip() or not human_reason.strip():
            raise ExperimentError("limitation and human_reason are required for G2")
        design_hash = design_sha256(design)
        card = ProtocolCard(
            protocol_id="PROT-" + uuid.uuid4().hex[:10],
            design_sha256=design_hash,
            capsule_sha256="",
            hypothesis=str(design.get("hypothesis", "")),
            baseline=str(design.get("baseline", "")),
            primary_metric=str(design.get("primary_metric", "")),
            controls=list(design.get("controls", [])),
            seeds=seed_count(design.get("seeds", 0)),
            limitation=limitation.strip(),
            human_reason=human_reason.strip(),
            status="frozen",
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "protocol-card.json"
        with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(asdict(card), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return {"protocol": asdict(card), "path": str(path), "design_sha256": design_hash}

    def freeze(
        self,
        design: Dict[str, Any],
        capsule_path: Path,
        limitation: str,
        human_reason: str,
        output_dir: Path,
    ) -> Dict[str, Any]:
        if design.get("status") != "ready_for_g2":
            raise ExperimentError("design must be ready_for_g2 before freezing")
        if not limitation.strip() or not human_reason.strip():
            raise ExperimentError("limitation and human_reason are required for G2")
        capsule_path = Path(capsule_path)
        if not capsule_path.is_file():
            raise ExperimentError("run capsule not found: " + str(capsule_path))
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
        if capsule.get("status") != "completed":
            raise ExperimentError("run capsule must be completed before G2")
        design_sha = design_sha256(design)
        capsule_sha = hashlib.sha256(capsule_path.read_bytes()).hexdigest()
        card = ProtocolCard(
            protocol_id="PROT-" + uuid.uuid4().hex[:10],
            design_sha256=design_sha,
            capsule_sha256=capsule_sha,
            hypothesis=str(design.get("hypothesis", "")),
            baseline=str(design.get("baseline", "")),
            primary_metric=str(design.get("primary_metric", "")),
            controls=list(design.get("controls", [])),
            seeds=seed_count(design.get("seeds", 0)),
            limitation=limitation.strip(),
            human_reason=human_reason.strip(),
            status="frozen",
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "protocol-card.json"
        with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(asdict(card), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return {"protocol": asdict(card), "path": str(path)}

