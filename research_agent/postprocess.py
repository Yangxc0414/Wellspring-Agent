"""Post-claim closure and lineage artifacts.

This runs only after a signed claim is supplied. It never signs, admits, or
changes a Claim; it materializes the structural closure/lineage views so the
main pipeline does not stop at an unconnected claim.
"""

import json
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .closure import ClosureAgent, ClosureError
from .lineage import LineageAgent, LineageError, write_impact, write_manifest
from .storage import write_json_atomic
from .support_audit import SupportAuditError, audit_support


def run_claim_postprocess(
    demo_path: Path,
    claim_file: Path,
    output_dir: Path,
    support_judge: Optional[Callable[[Dict[str, Any]], Optional[list]]] = None,
    strict_support: bool = False,
) -> Dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    demo_path = Path(demo_path)
    claim_source = Path(claim_file)
    claim_target = out / "claim" / "claim.json"
    claim_target.parent.mkdir(parents=True, exist_ok=True)
    if claim_source.resolve() != claim_target.resolve():
        shutil.copyfile(str(claim_source), str(claim_target))

    result: Dict[str, Any] = {
        "schema_version": "claim-postprocess-0.1",
        "demo": str(demo_path),
        "claim": str(claim_target),
        "closure": None,
        "lineage": None,
        "verify": None,
        "support_audit": None,
        "warnings": [],
        "boundary": "closure is structural only; lineage is an audit view; neither signs or submits",
    }
    try:
        closure = ClosureAgent().check(demo_path, claim_target, out / "closure")
        report = closure.get("report") or {}
        result["closure"] = {
            "status": report.get("status", ""),
            "path": closure.get("path", ""),
            "unresolved": list(report.get("unresolved") or []),
            "obligations": closure.get("obligations", ""),
            "obligation_summary": dict(closure.get("obligation_summary") or {}),
        }
    except (ClosureError, OSError, ValueError) as exc:
        result["warnings"].append("closure check failed: %s" % exc)

    try:
        manifest = LineageAgent().build(out)
        manifest_path = write_manifest(manifest, out / "lineage")
        result["lineage"] = {
            "status": manifest.get("status", ""),
            "path": str(manifest_path),
        }
        try:
            impact = LineageAgent().verify(manifest_path, out)
            impact_path = write_impact(impact, out / "lineage")
            result["verify"] = {
                "status": impact.get("status", ""),
                "path": str(impact_path),
            }
        except (LineageError, OSError, ValueError) as exc:
            result["warnings"].append("lineage verify failed: %s" % exc)
    except (LineageError, OSError, ValueError) as exc:
        result["warnings"].append("lineage build failed: %s" % exc)

    try:
        demo = json.loads(demo_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_target.read_text(encoding="utf-8"))
        modules = demo.get("modules") or {}
        paper = modules.get("paper") or {}
        spans = (modules.get("literature") or {}).get("spans") or []
        audit = audit_support(
            paper,
            spans,
            claim,
            judge=support_judge,
            strict=strict_support,
        )
        audit_path = out / "support-audit.json"
        write_json_atomic(audit_path, audit)
        result["support_audit"] = {
            "status": audit.get("status", ""),
            "method": audit.get("method", ""),
            "counts": dict(audit.get("counts") or {}),
            "citation_modes": dict(audit.get("citation_modes") or {}),
            "path": str(audit_path),
            "advisory_only": True,
            "production_block_on": ["contradicted"],
        }
        result["warnings"].extend(list(audit.get("warnings") or []))
        if strict_support and int((audit.get("counts") or {}).get("contradicted", 0)) > 0:
            raise SupportAuditError(
                "support judge found contradicted citations; production blocks "
                "this claim until a human resolves them"
            )
    except SupportAuditError:
        raise
    except Exception as exc:
        from .models import ModelRequiredError

        if isinstance(exc, ModelRequiredError):
            raise
        result["warnings"].append("support audit failed: %s" % type(exc).__name__)

    path = out / "postprocess.json"
    write_json_atomic(path, result)
    result["path"] = str(path)
    return result
