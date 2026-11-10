"""Content-addressed evidence lineage and change-impact propagation.

The lineage is intentionally conservative: it records the artifacts that a
research run actually produced plus the dependency edges implied by their
fields. A change to any upstream artifact marks every downstream claim, slot,
figure, closure and signature stale. It is not a semantic proof of the claim.
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .signers import SIGNATURE_SCHEME, SignerStore


class LineageError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(text.encode("utf-8"))


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LineageError("cannot read JSON artifact %s: %s" % (path, exc))
    if not isinstance(value, dict):
        raise LineageError("artifact must contain a JSON object: %s" % path)
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


@dataclass
class LineageNode:
    node_id: str
    kind: str
    label: str
    sha256: str
    dependencies: List[str] = field(default_factory=list)
    path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LineageManifest:
    manifest_id: str
    created_at: str
    bundle_root: str
    status: str
    nodes: List[LineageNode]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChangeImpact:
    status: str
    changed: List[Dict[str, Any]]
    stale: List[Dict[str, Any]]
    stale_claims: List[str]
    stale_slots: List[str]
    stale_figures: List[str]
    requires_reclosure: bool
    requires_resign: bool
    export_allowed: bool
    created_at: str
    baseline_manifest: str
    bundle_root: str
    dispositions: List[Dict[str, str]] = field(default_factory=list)
    action_counts: Dict[str, int] = field(default_factory=dict)
    next_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LineageAgent:
    """Build, verify and compare a local evidence lineage bundle."""

    def _resolve(self, root: Path) -> Dict[str, Optional[Path]]:
        candidates: Dict[str, List[str]] = {
            "demo": ["bound/demo.json", "demo.json", "run/demo.json"],
            "claim": ["claim/claim.json", "claim.json"],
            "protocol": ["protocol/protocol-card.json", "bound/protocol.json", "protocol.json"],
            "bibliography": [
                "bibliography/bibliography-card.json",
                "bound/bibliography.json",
                "bibliography.json",
            ],
            "paper": ["bound/paper.json", "paper.json", "run/paper.json"],
            "capsule": [
                "run/run/run-capsule.json",
                "run/run-capsule.json",
                "run-capsule.json",
            ],
            "ea": ["run/run/ea.json", "run/ea.json", "ea.json"],
            "figure_manifest": [
                "run/run/result-figure.manifest.json",
                "run/result-figure.manifest.json",
                "result-figure.manifest.json",
            ],
            "figure_svg": [
                "run/run/result-figure.svg",
                "run/result-figure.svg",
                "result-figure.svg",
            ],
            "closure": ["closure/closure-report.json", "closure-report.json"],
            "signature": ["signature/signature.json", "signature.json"],
            "export_manifest": ["signature/export-manifest.json", "export-manifest.json"],
            "metrics": ["run/run/metrics.json", "run/metrics.json", "metrics.json"],
        }
        found: Dict[str, Optional[Path]] = {}
        for role, options in candidates.items():
            found[role] = next((root / option for option in options if (root / option).is_file()), None)
        return found

    def _file_node(
        self,
        node_id: str,
        kind: str,
        label: str,
        path: Path,
        root: Path,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LineageNode:
        return LineageNode(
            node_id=node_id,
            kind=kind,
            label=label,
            sha256=_sha256_file(path),
            dependencies=list(dependencies or []),
            path=_relative(path, root),
            metadata=metadata or {},
        )

    def build(
        self, bundle: Path, signer_store: Optional[SignerStore] = None
    ) -> Dict[str, Any]:
        root = Path(bundle)
        if not root.is_dir():
            raise LineageError("bundle directory not found: %s" % root)
        paths = self._resolve(root)
        nodes: List[LineageNode] = []
        warnings: List[str] = []

        capsule_path = paths["capsule"]
        if not capsule_path:
            raise LineageError("bundle has no run-capsule.json")
        capsule = _read_json(capsule_path)
        run_id = str(capsule.get("run_id") or "unknown-run")
        dataset_sha = str(capsule.get("dataset_sha256") or "").strip()
        code_sha = str(capsule.get("code_sha256") or "").strip()
        dataset_id = "dataset:%s" % (dataset_sha[:12] or "unknown")
        code_id = "code:%s" % (code_sha[:12] or "unknown")
        if dataset_sha:
            nodes.append(LineageNode(
                node_id=dataset_id,
                kind="dataset",
                label=str(capsule.get("dataset_id") or dataset_id),
                sha256=dataset_sha,
                metadata={"source": "capsule.dataset_sha256"},
            ))
        if code_sha:
            nodes.append(LineageNode(
                node_id=code_id,
                kind="code",
                label="run code",
                sha256=code_sha,
                metadata={"source": "capsule.code_sha256"},
            ))
        run_deps = [node.node_id for node in nodes if node.kind in ("dataset", "code")]
        run_id_node = "run:%s" % run_id
        nodes.append(self._file_node(
            run_id_node, "run", run_id, capsule_path, root, run_deps,
            {"status": capsule.get("status"), "seeds": capsule.get("seeds", [])},
        ))

        ea_path = paths["ea"]
        ea: Dict[str, Any] = {}
        claim_id = ""
        if ea_path:
            ea = _read_json(ea_path)
            ea_node_id = "ea:%s" % (ea.get("artifact_id") or "unknown")
            nodes.append(self._file_node(
                ea_node_id, "evidence", str(ea.get("artifact_id") or "EA"), ea_path, root,
                [run_id_node], {"scope": ea.get("scope"), "kind": ea.get("kind")},
            ))
        else:
            ea_node_id = ""
            warnings.append("bundle has no ea.json; claim provenance is incomplete")

        protocol_node_id = ""
        if paths["protocol"]:
            protocol = _read_json(paths["protocol"])
            protocol_node_id = "protocol:%s" % (protocol.get("protocol_id") or "unknown")
            nodes.append(self._file_node(
                protocol_node_id, "protocol", str(protocol.get("protocol_id") or "protocol"),
                paths["protocol"], root, [run_id_node],
                {"status": protocol.get("status"), "capsule_sha256": protocol.get("capsule_sha256")},
            ))

        bibliography_node_id = ""
        if paths["bibliography"]:
            bibliography = _read_json(paths["bibliography"])
            bibliography_node_id = "bibliography:%s" % (bibliography.get("card_id") or "unknown")
            nodes.append(self._file_node(
                bibliography_node_id, "bibliography", str(bibliography.get("card_id") or "bibliography"),
                paths["bibliography"], root, [],
                {"status": bibliography.get("status"), "entry_count": bibliography.get("entry_count")},
            ))

        claim_node_id = ""
        claim_path = paths["claim"]
        if claim_path:
            claim = _read_json(claim_path)
            claim_id = str(claim.get("claim_id") or "")
            claim_node_id = "claim:%s" % (claim_id or "unknown")
            claim_deps = [ea_node_id] if ea_node_id else []
            nodes.append(self._file_node(
                claim_node_id, "claim", claim_id or "claim", claim_path, root, claim_deps,
                {"status": claim.get("status"), "scope": claim.get("scope"), "statement": claim.get("statement")},
            ))
        else:
            warnings.append("bundle has no supported claim.json; lineage ends before the claim")

        figure_node_id = ""
        if paths["figure_manifest"]:
            manifest = _read_json(paths["figure_manifest"])
            figure_id = str(manifest.get("figure_id") or "figure")
            figure_node_id = "figure:%s" % figure_id
            figure_hash_parts = [paths["figure_manifest"].read_bytes()]
            if paths["figure_svg"]:
                figure_hash_parts.append(paths["figure_svg"].read_bytes())
            figure_sha = _sha256_bytes(b"".join(figure_hash_parts))
            nodes.append(LineageNode(
                node_id=figure_node_id,
                kind="figure",
                label=figure_id,
                sha256=figure_sha,
                dependencies=[dep for dep in (ea_node_id, run_id_node) if dep],
                path=_relative(paths["figure_manifest"], root),
                metadata={
                    "svg_sha256": manifest.get("svg_sha256"),
                    "data_sha256": manifest.get("data_sha256"),
                    "schematic": manifest.get("schematic"),
                },
            ))

        slot_node_ids: List[str] = []
        paper_path = paths["paper"]
        if paper_path:
            paper = _read_json(paper_path)
            for slot in paper.get("slots") or []:
                slot_id = str(slot.get("slot_id") or "slot")
                status = str(slot.get("status") or "")
                deps: List[str] = []
                if status == "bound_claim":
                    deps = [claim_node_id] if claim_node_id else []
                elif status == "bound_figure":
                    deps = [figure_node_id] if figure_node_id else []
                elif status == "bound_protocol":
                    deps = [protocol_node_id] if protocol_node_id else []
                elif status == "bound_bibliography":
                    deps = [bibliography_node_id] if bibliography_node_id else []
                elif status == "bound_scope":
                    deps = [dep for dep in (claim_node_id, protocol_node_id) if dep]
                slot_node = "slot:%s" % slot_id
                slot_node_ids.append(slot_node)
                nodes.append(LineageNode(
                    node_id=slot_node,
                    kind="paper_slot",
                    label=slot_id,
                    sha256=_sha256_json(slot),
                    dependencies=deps,
                    path=_relative(paper_path, root),
                    metadata={"status": status, "section": slot.get("section")},
                ))
        else:
            warnings.append("bundle has no paper.json; paper slots are absent")

        paper_node_id = ""
        if paper_path:
            paper = _read_json(paper_path)
            paper_node_id = "paper:manuscript"
            paper_deps = [
                dep for dep in (
                    claim_node_id,
                    figure_node_id,
                    protocol_node_id,
                    bibliography_node_id,
                    *slot_node_ids,
                ) if dep
            ]
            nodes.append(self._file_node(
                paper_node_id, "paper", str(paper.get("title") or "paper manuscript"),
                paper_path, root, paper_deps,
                {"status": paper.get("status"), "claims": paper.get("claims") or []},
            ))

        closure_node_id = ""
        closure_path = paths["closure"]
        if closure_path:
            closure = _read_json(closure_path)
            closure_node_id = "closure:%s" % (closure.get("report_id") or "unknown")
            closure_deps = [
                dep for dep in (
                    claim_node_id,
                    ea_node_id,
                    run_id_node,
                    figure_node_id,
                    protocol_node_id,
                    bibliography_node_id,
                    paper_node_id,
                    *slot_node_ids,
                ) if dep
            ]
            nodes.append(self._file_node(
                closure_node_id, "closure", str(closure.get("report_id") or "closure"),
                closure_path, root, closure_deps,
                {"status": closure.get("status"), "checks": len(closure.get("checks") or [])},
            ))
        else:
            warnings.append("bundle has no closure-report.json; export is not closed")

        signature_node_id = ""
        signature_path = paths["signature"]
        if signature_path:
            signature = _read_json(signature_path)
            signature_node_id = "signature:%s" % (signature.get("signature_id") or "unknown")
            scheme = str(signature.get("signature_scheme") or "legacy-unsigned")
            metadata = {
                "submission": signature.get("submission", False),
                "scheme": scheme,
                "signer_id": signature.get("signer_id", ""),
                "signer_key_id": signature.get("signer_key_id", ""),
            }
            if scheme == SIGNATURE_SCHEME:
                export_manifest_path = paths.get("export_manifest")
                if signer_store is None:
                    metadata["signature_verified"] = False
                    warnings.append("signature is HMAC-signed; provide a signer store to verify")
                elif not export_manifest_path:
                    metadata["signature_verified"] = False
                    warnings.append("signature HMAC cannot be verified without export manifest")
                else:
                    signed_payload = {
                        "schema_version": "closure-signature-0.2",
                        "report_id": str(signature.get("report_id") or ""),
                        "export_manifest_sha256": _sha256_file(export_manifest_path),
                        "human_reason": str(signature.get("human_reason") or ""),
                        "submission": False,
                    }
                    verified = signer_store.verify(
                        str(signature.get("signer_id") or ""),
                        str(signature.get("signer_key_id") or ""),
                        signed_payload,
                        str(signature.get("signature_hmac") or ""),
                    )
                    metadata["signature_verified"] = verified
                    if not verified:
                        warnings.append("signature HMAC verification failed")
            elif scheme == "legacy-unsigned":
                metadata["signature_verified"] = False
                warnings.append("legacy-unsigned signature; no HMAC identity proof")
            else:
                metadata["signature_verified"] = False
                warnings.append("unsupported signature scheme: " + scheme)
            nodes.append(self._file_node(
                signature_node_id, "signature", str(signature.get("signature_id") or "signature"),
                signature_path, root, [closure_node_id] if closure_node_id else [],
                metadata,
            ))
        else:
            warnings.append("bundle has no signature.json; draft is not signed")

        export_manifest_path = paths["export_manifest"]
        if export_manifest_path:
            nodes.append(self._file_node(
                "export:manifest", "export_manifest", "export manifest", export_manifest_path, root,
                [signature_node_id] if signature_node_id else [],
                {},
            ))

        if paths["metrics"]:
            warnings.append("metric file is represented by the EA hash; it is not a separate downstream node")
        if not claim_id:
            warnings.append("no claim id found; closure may be incomplete")

        status = "complete" if closure_node_id and signature_node_id else "partial"
        manifest = LineageManifest(
            manifest_id="LIN-" + uuid.uuid4().hex[:10],
            created_at=_now(),
            bundle_root=str(root.resolve()),
            status=status,
            nodes=nodes,
            warnings=warnings,
        )
        return manifest.to_dict()

    def verify(self, manifest_path: Path, bundle: Path) -> Dict[str, Any]:
        baseline = _read_json(Path(manifest_path))
        current = self.build(Path(bundle))
        impact = self._compare(baseline, current, str(Path(manifest_path).resolve()), str(Path(bundle).resolve()))
        impact["verified_at"] = _now()
        return impact

    def impact(self, baseline_path: Path, bundle: Path) -> Dict[str, Any]:
        return self.verify(baseline_path, bundle)

    def _compare(
        self,
        baseline: Dict[str, Any],
        current: Dict[str, Any],
        baseline_path: str,
        bundle_root: str,
    ) -> Dict[str, Any]:
        base_nodes = {str(node.get("node_id")): node for node in baseline.get("nodes") or []}
        curr_nodes = {str(node.get("node_id")): node for node in current.get("nodes") or []}
        all_ids = set(base_nodes) | set(curr_nodes)
        changed_ids: Set[str] = set()
        changed: List[Dict[str, Any]] = []
        for node_id in sorted(all_ids):
            before = base_nodes.get(node_id)
            after = curr_nodes.get(node_id)
            before_hash = before.get("sha256") if before else None
            after_hash = after.get("sha256") if after else None
            if before_hash != after_hash:
                changed_ids.add(node_id)
                changed.append({
                    "node_id": node_id,
                    "kind": (after or before or {}).get("kind"),
                    "label": (after or before or {}).get("label"),
                    "before": before_hash,
                    "after": after_hash,
                    "change": "missing" if after is None else "new" if before is None else "hash_changed",
                })

        reverse: Dict[str, Set[str]] = {}
        for node_id, node in list(base_nodes.items()) + list(curr_nodes.items()):
            for dep in node.get("dependencies") or []:
                reverse.setdefault(dep, set()).add(node_id)
        stale_ids: Set[str] = set(changed_ids)
        queue = list(changed_ids)
        while queue:
            node_id = queue.pop(0)
            for dependent in reverse.get(node_id, set()):
                if dependent not in stale_ids:
                    stale_ids.add(dependent)
                    queue.append(dependent)

        stale: List[Dict[str, Any]] = []
        for node_id in sorted(stale_ids):
            node = curr_nodes.get(node_id) or base_nodes.get(node_id) or {}
            reasons = sorted(
                dep for dep in (node.get("dependencies") or []) if dep in stale_ids
            )
            stale.append({
                "node_id": node_id,
                "kind": node.get("kind"),
                "label": node.get("label"),
                "reason": "changed" if node_id in changed_ids else "upstream:%s" % ",".join(reasons),
            })

        stale_claims = [item["node_id"] for item in stale if item.get("kind") == "claim"]
        stale_slots = [item["node_id"] for item in stale if item.get("kind") == "paper_slot"]
        stale_figures = [item["node_id"] for item in stale if item.get("kind") == "figure"]
        requires_resign = any(item.get("kind") == "signature" for item in stale)
        requires_reclosure = any(item.get("kind") == "closure" for item in stale) or requires_resign
        export_allowed = not requires_resign and any(
            node.get("kind") == "signature" for node in curr_nodes.values()
        )
        dispositions: List[Dict[str, str]] = []
        action_counts: Dict[str, int] = {}
        for item in stale:
            kind = str(item.get("kind") or "unknown")
            if kind in ("run", "evidence"):
                action = "rerun"
                detail = "rerun S5 with the changed dataset/code and emit a new capsule/EA"
            elif kind in ("figure", "paper_slot", "paper"):
                action = "rewrite"
                detail = "regenerate or rebind this figure / manuscript slot to the new evidence"
            else:
                action = "recheck"
                detail = "recheck this artifact; closure and signature must be refreshed after reruns"
            action_counts[action] = action_counts.get(action, 0) + 1
            dispositions.append({
                "node_id": str(item.get("node_id")),
                "kind": kind,
                "label": str(item.get("label") or ""),
                "action": action,
                "detail": detail,
            })
        next_steps: List[str] = []
        if stale:
            if action_counts.get("rerun"):
                next_steps.append("rerun S5 with the changed dataset/code; write a new capsule and EA")
            if action_counts.get("recheck"):
                next_steps.append("recheck claim/protocol/bibliography; rerun closure after the new run")
            if action_counts.get("rewrite"):
                next_steps.append("regenerate/rebind the affected figure and paper slots")
            next_steps.append("rerun closure checks and confirm all stale nodes are cleared")
            if requires_resign:
                next_steps.append("request a fresh human signature; the old signature is stale")
            if not export_allowed:
                next_steps.append("keep export blocked until reclosure and re-signing complete")
        status = "stale" if stale else "clean"
        return ChangeImpact(
            status=status,
            changed=changed,
            stale=stale,
            stale_claims=stale_claims,
            stale_slots=stale_slots,
            stale_figures=stale_figures,
            requires_reclosure=requires_reclosure,
            requires_resign=requires_resign,
            export_allowed=export_allowed,
            created_at=_now(),
            baseline_manifest=baseline_path,
            bundle_root=bundle_root,
            dispositions=dispositions,
            action_counts=action_counts,
            next_steps=next_steps,
        ).to_dict()


def write_manifest(manifest: Dict[str, Any], output_dir: Path) -> Path:
    path = Path(output_dir) / "lineage.json"
    _write_json(path, manifest)
    return path


def write_impact(impact: Dict[str, Any], output_dir: Path) -> Path:
    path = Path(output_dir) / "change-impact.json"
    _write_json(path, impact)
    return path
