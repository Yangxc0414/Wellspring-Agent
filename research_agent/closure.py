"""S13–S16 closure and export gate: no Claim/EA, no export."""

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .contracts import ClosureCheck, ClosureReport, SignatureRecord
from .signers import SIGNATURE_SCHEME, SignerStore
from .storage import atomic_replace
from .modules.run import verify_claim_assertions


class ClosureError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


BUNDLE_SCHEMA = "closure-evidence-bundle/1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BUNDLE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.match(value))


def _safe_artifact_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(str(name)).name).strip("._")
    return (cleaned or fallback)[:80]


def _write_bytes_durable(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(str(path), flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise ClosureError("short write while sealing evidence bundle")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_json_durable(path: Path, value: Any) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _write_bytes_durable(path, data)


def _fsync_dir(path: Path) -> None:
    # Windows cannot open a directory as an fd; NTFS rename is still atomic.
    if os.name == "nt":
        return
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _confined_path(root: Path, relative: str) -> Path:
    candidate = Path(str(relative))
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise ClosureError("bundle path escapes its root: %s" % relative)
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise ClosureError("bundle path escapes its root: %s" % relative)
    return resolved


class ClosureAgent:
    def check(self, demo_path: Path, claim_path: Path, output_dir: Path) -> Dict[str, Any]:
        demo = json.loads(Path(demo_path).read_text(encoding="utf-8"))
        claim = json.loads(Path(claim_path).read_text(encoding="utf-8"))
        modules = demo.get("modules") or {}
        paper = modules.get("paper") or {}
        run = modules.get("run") or {}
        evidence = run.get("evidence") or {}
        capsule = run.get("capsule") or {}
        protocol = modules.get("protocol") or {}
        bibliography = modules.get("bibliography") or {}
        figure = run.get("result_figure") or {}
        figure_manifest = figure.get("manifest") or {}
        checks: List[ClosureCheck] = []
        capsule_path = Path((run.get("paths") or {}).get("capsule", ""))
        capsule_artifact: Optional[Dict[str, Any]] = None
        capsule_error = ""
        if not capsule_path.is_file():
            capsule_error = "capsule file missing: %s" % capsule_path
        else:
            try:
                value = json.loads(capsule_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    capsule_artifact = value
                else:
                    capsule_error = "capsule file is not an object"
            except (OSError, ValueError) as exc:
                capsule_error = "cannot read capsule: %s" % exc

        roots: List[Path] = []
        for base in (Path(demo_path).parent, Path(demo_path).parent.parent, Path(claim_path).parent):
            if base.is_dir() and base not in roots:
                roots.append(base)

        def find_artifact(relative_paths: List[str]) -> Optional[Path]:
            for base in roots:
                for relative in relative_paths:
                    candidate = base / relative
                    if candidate.is_file():
                        return candidate.resolve()
            return None

        protocol_path = find_artifact([
            "protocol/protocol-card.json", "bound/protocol.json", "protocol.json",
        ]) if protocol else None
        bibliography_path = find_artifact([
            "bibliography/bibliography-card.json", "bound/bibliography.json", "bibliography.json",
        ]) if bibliography else None
        support_panel_path = find_artifact(["support-panel.json"])
        figure_manifest_path: Optional[Path] = None
        figure_svg_path: Optional[Path] = None
        if figure:
            declared_manifest = str((figure.get("paths") or {}).get("manifest") or "")
            if declared_manifest and Path(declared_manifest).is_file():
                figure_manifest_path = Path(declared_manifest)
            else:
                figure_manifest_path = find_artifact([
                    "run/run/result-figure.manifest.json",
                    "run/result-figure.manifest.json",
                    "result-figure.manifest.json",
                ])
            declared_svg = str((figure.get("paths") or {}).get("svg") or "")
            if declared_svg and Path(declared_svg).is_file():
                figure_svg_path = Path(declared_svg)
            else:
                figure_svg_path = find_artifact([
                    "run/run/result-figure.svg", "run/result-figure.svg", "result-figure.svg",
                ])

        def add(name: str, ok: bool, detail: str) -> None:
            checks.append(ClosureCheck(name, "pass" if ok else "fail", detail))

        add("claim_supported", claim.get("status") == "supported", "claim status=%s" % claim.get("status"))
        if support_panel_path is not None:
            try:
                support_panel = json.loads(support_panel_path.read_text(encoding="utf-8"))
                panel_status = str(support_panel.get("status") or "missing")
                pending_human = support_panel.get("pending_human") or []
                add(
                    "support_panel_ready",
                    panel_status in ("ready", "not_applicable"),
                    "status=%s pending_human=%d" % (panel_status, len(pending_human)),
                )
            except (OSError, ValueError) as exc:
                add("support_panel_ready", False, "unreadable: %s" % exc)
        refs = claim.get("evidence_refs") or []
        add("claim_has_ea", bool(refs), "evidence_refs=%s" % refs)
        add(
            "ea_id_matches",
            bool(refs) and evidence.get("artifact_id") in refs,
            "EA=%s refs=%s" % (evidence.get("artifact_id"), refs),
        )
        ea_path = Path(evidence.get("path", ""))
        ea_ok = ea_path.is_file() and _sha256_file(ea_path) == evidence.get("sha256")
        add("ea_hash", ea_ok, "path=%s" % ea_path)
        add(
            "run_capsule_artifact",
            capsule_artifact is not None,
            capsule_error or "path=%s" % capsule_path,
        )
        actual_capsule = capsule_artifact if capsule_artifact is not None else capsule
        add(
            "run_completed",
            actual_capsule.get("status") == "completed",
            "status=%s" % actual_capsule.get("status"),
        )
        claim_assertions = claim.get("assertions") or []
        if claim_assertions:
            try:
                metrics = json.loads(ea_path.read_text(encoding="utf-8"))
                if not isinstance(metrics, list):
                    raise ValueError("metrics must be a list")
                assertion_results = verify_claim_assertions(
                    actual_capsule, metrics, claim_assertions
                )
                assertion_failures = [
                    item for item in assertion_results if item.get("status") != "pass"
                ]
                add(
                    "claim_assertions",
                    not assertion_failures,
                    "%d checked, %d failed"
                    % (len(assertion_results), len(assertion_failures)),
                )
            except (OSError, ValueError) as exc:
                add("claim_assertions", False, "cannot re-verify assertions: %s" % exc)
        else:
            add(
                "claim_assertions",
                True,
                "legacy claim has no structured assertions; numeric support not re-verified",
            )
        slots = paper.get("slots") or []
        primary = next((slot for slot in slots if slot.get("slot_id") == "result.primary"), None)
        add(
            "result_primary_bound",
            bool(primary) and primary.get("status") == "bound_claim",
            "result.primary=%s" % (primary.get("status") if primary else "missing"),
        )
        add(
            "claim_listed_in_paper",
            str(claim.get("claim_id")) in [str(item) for item in (paper.get("claims") or [])],
            "paper claims=%s" % (paper.get("claims") or []),
        )

        bibliography_entries = bibliography.get("entries") or []
        bibliography_card_hash = _sha256_bytes(
            json.dumps(bibliography_entries, sort_keys=True, ensure_ascii=False).encode("utf-8")
        )
        bibliography_ok = (
            bibliography.get("status") == "verified_datacite_snapshot"
            and bibliography.get("verification_source") == "datacite_api_snapshot"
            and int(bibliography.get("entry_count", 0)) >= 2
            and bibliography_card_hash == bibliography.get("card_sha256")
        )
        add("bibliography_verified", bibliography_ok, "card=%s" % bibliography.get("card_id"))
        if bibliography:
            bibliography_file_ok = False
            bibliography_file_detail = "path=%s" % bibliography_path
            if bibliography_path:
                try:
                    bibliography_file = json.loads(bibliography_path.read_text(encoding="utf-8"))
                    bibliography_file_ok = (
                        bibliography_file.get("card_id") == bibliography.get("card_id")
                        and bibliography_file.get("status") == bibliography.get("status")
                        and bibliography_file.get("card_sha256") == bibliography.get("card_sha256")
                        and int(bibliography_file.get("entry_count", 0)) == int(bibliography.get("entry_count", 0))
                    )
                except (OSError, ValueError) as exc:
                    bibliography_file_detail += " (%s)" % exc
            add("bibliography_artifact", bibliography_file_ok, bibliography_file_detail)

        binding = modules.get("protocol_binding") or {}
        capsule_sha = _sha256_file(capsule_path) if capsule_path.is_file() else ""
        binding_ok = bool(
            binding
            and binding.get("capsule_sha256") == capsule_sha
            and binding.get("protocol_id") == protocol.get("protocol_id")
            and binding.get("design_sha256") == protocol.get("design_sha256")
        )
        protocol_ok = (
            protocol.get("status") == "frozen"
            and bool(protocol.get("human_reason"))
            and bool(protocol.get("limitation"))
            and bool(capsule_sha)
            and (
                protocol.get("capsule_sha256") == capsule_sha
                or binding_ok
            )
        )
        add("protocol_frozen", protocol_ok, "protocol=%s" % protocol.get("protocol_id"))
        if protocol:
            protocol_file_ok = False
            protocol_file_detail = "path=%s" % protocol_path
            if protocol_path:
                try:
                    protocol_file = json.loads(protocol_path.read_text(encoding="utf-8"))
                    protocol_file_ok = (
                        protocol_file.get("protocol_id") == protocol.get("protocol_id")
                        and protocol_file.get("status") == protocol.get("status")
                        and protocol_file.get("capsule_sha256") == protocol.get("capsule_sha256")
                        and protocol_file.get("human_reason") == protocol.get("human_reason")
                    )
                except (OSError, ValueError) as exc:
                    protocol_file_detail += " (%s)" % exc
            add("protocol_artifact", protocol_file_ok, protocol_file_detail)

        figure_ok = (
            figure_manifest.get("schematic") is False
            and figure_svg_path is not None
            and figure_svg_path.is_file()
            and _sha256_file(figure_svg_path) == figure_manifest.get("svg_sha256")
            and evidence.get("artifact_id") in (figure_manifest.get("evidence_refs") or [])
        )
        add("result_figure_provenance", figure_ok, "figure=%s" % figure_manifest.get("figure_id"))
        if figure:
            figure_manifest_ok = False
            figure_manifest_detail = "path=%s" % figure_manifest_path
            if figure_manifest_path:
                try:
                    figure_manifest_file = json.loads(figure_manifest_path.read_text(encoding="utf-8"))
                    figure_manifest_ok = figure_manifest_file == figure_manifest
                except (OSError, ValueError) as exc:
                    figure_manifest_detail += " (%s)" % exc
            add("figure_manifest_artifact", figure_manifest_ok, figure_manifest_detail)

        unresolved = [
            str(slot.get("slot_id")) for slot in slots
            if slot.get("status") == "pending_evidence"
        ]
        add("all_slots_bound", not unresolved, "unresolved=%s" % unresolved)
        artifact_refs: List[str] = []
        for candidate in [
            Path(demo_path), Path(claim_path), ea_path, capsule_path,
            protocol_path, bibliography_path, support_panel_path,
            figure_manifest_path, figure_svg_path,
        ]:
            if candidate is not None and candidate.is_file() and str(candidate) not in artifact_refs:
                artifact_refs.append(str(candidate))
        passed = all(check.status == "pass" for check in checks)
        report = ClosureReport(
            report_id="CLR-" + uuid.uuid4().hex[:10],
            status="ready" if passed and not unresolved else "blocked",
            checks=checks,
            unresolved=unresolved,
            artifact_refs=artifact_refs,
            created_at=_now(),
            warnings=[
                "closure is structural only; not peer review",
                "all resolvable companion artifacts are hashed into the export; missing companion files block closure",
                "no automatic submission; human sign required",
            ],
            closure_profile="canonical_run",
        )
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "closure-report.json"
        _write_json(path, asdict(report))
        from .obligations import ObligationLedger

        obligations = ObligationLedger(output_dir / "obligations.json").reconcile(
            asdict(report)
        )
        return {
            "report": asdict(report),
            "path": str(path),
            "obligations": obligations["path"],
            "obligation_summary": obligations["summary"],
        }

    def sign(
        self,
        report_path: Path,
        demo_path: Path,
        claim_path: Path,
        human_reason: str,
        output_dir: Path,
        signer_store: Optional[SignerStore] = None,
        signer_id: str = "",
    ) -> Dict[str, Any]:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        if report.get("status") != "ready":
            raise ClosureError("closure report is not ready; export is blocked")
        if not human_reason.strip():
            raise ClosureError("human_reason is required for export")
        # Recompute from the current inputs instead of trusting a stale report.
        with tempfile.TemporaryDirectory(prefix="ra-closure-sign-") as temp_dir:
            fresh = self.check(Path(demo_path), Path(claim_path), Path(temp_dir))
        fresh_report = fresh.get("report") or {}
        if fresh_report.get("status") != "ready":
            raise ClosureError("closure is no longer ready for the current inputs")
        if report.get("checks") != fresh_report.get("checks"):
            raise ClosureError("submitted report checks do not match current inputs; re-run closure check")
        artifact_paths: List[str] = []
        for value in [demo_path, claim_path, report_path, *fresh_report.get("artifact_refs", [])]:
            path = Path(str(value)).resolve()
            if path.is_file() and str(path) not in artifact_paths:
                artifact_paths.append(str(path))
        try:
            files = {path: _sha256_file(Path(path)) for path in artifact_paths}
        except OSError as exc:
            raise ClosureError("cannot hash a closure input: %s" % exc)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = output_dir / "export-manifest.json"
        _write_json(manifest, {
            "report_id": report.get("report_id"),
            "revalidated_report_id": fresh_report.get("report_id"),
            "closure_checks_sha256": hashlib.sha256(
                json.dumps(fresh_report.get("checks"), ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "files": files,
            "submission": False,
            "note": "signed draft manifest; closure was re-run immediately before signing; no auto-submission",
            "revalidated_at": _now(),
        })
        if bool(signer_store) != bool((signer_id or "").strip()):
            raise ClosureError("signer_store and signer_id must be provided together")
        signed_payload = {
            "schema_version": "closure-signature-0.2",
            "report_id": str(report.get("report_id")),
            "export_manifest_sha256": _sha256_file(manifest),
            "human_reason": human_reason.strip(),
            "submission": False,
        }
        signature_fields: Dict[str, Any] = {}
        if signer_store is not None:
            signature_fields = signer_store.sign(signer_id, signed_payload)
        signature = SignatureRecord(
            signature_id="SIG-" + uuid.uuid4().hex[:10],
            report_id=str(report.get("report_id")),
            human_reason=human_reason.strip(),
            created_at=_now(),
            artifact_refs=[str(demo_path), str(claim_path), str(report_path)],
            export_manifest=str(manifest),
            submission=False,
            **signature_fields,
        )
        path = output_dir / "signature.json"
        _write_json(path, asdict(signature))
        return {
            "signature": asdict(signature),
            "path": str(path),
            "manifest": str(manifest),
            "signed_payload": signed_payload,
            "scheme": signature.signature_scheme,
        }

    def publish(
        self,
        export_manifest_path: Path,
        output_dir: Path,
        signature_path: Optional[Path] = None,
        bundle_name: str = "evidence-bundle",
        signer_store: Optional[SignerStore] = None,
    ) -> Dict[str, Any]:
        """Copy a signed export manifest and its evidence into a sealed directory.

        The manifest is the authority for *which bytes* were signed. The bundle is a
        byte-verified copy, not a new claim: it never overwrites an existing directory and
        never accepts a manifest with submission=true.
        """
        manifest_path = Path(export_manifest_path)
        if not manifest_path.is_file():
            raise ClosureError("export manifest not found: %s" % manifest_path)
        export = self._read_json_object(manifest_path, "export manifest")
        if export.get("submission") is not False:
            raise ClosureError("only submission=false export manifests can be sealed")
        if not str(export.get("report_id") or "").strip():
            raise ClosureError("export manifest has no report_id")
        if not _is_sha256(export.get("closure_checks_sha256")):
            raise ClosureError("export manifest has no closure checks digest")
        files = export.get("files")
        if not isinstance(files, dict) or not files:
            raise ClosureError("export manifest has no evidence files")
        if not _BUNDLE_NAME_RE.match(bundle_name):
            raise ClosureError("invalid bundle name: %s" % bundle_name)

        if signature_path is None:
            candidate = manifest_path.with_name("signature.json")
            selected_signature = candidate if candidate.is_file() else None
        else:
            selected_signature = Path(signature_path)
            if not selected_signature.is_file():
                raise ClosureError("signature not found: %s" % selected_signature)
        signature_payload: Optional[Dict[str, Any]] = None
        if selected_signature is not None:
            signature_payload = self._read_json_object(selected_signature, "signature")
            if str(signature_payload.get("report_id")) != str(export.get("report_id")):
                raise ClosureError("signature report_id does not match export manifest")
            if signature_payload.get("submission") is not False:
                raise ClosureError("signature must declare submission=false")
            scheme = str(signature_payload.get("signature_scheme") or "legacy-unsigned")
            if scheme == SIGNATURE_SCHEME:
                if signer_store is None:
                    raise ClosureError("HMAC signature requires --signers-path to verify")
                signed_payload = {
                    "schema_version": "closure-signature-0.2",
                    "report_id": str(export.get("report_id")),
                    "export_manifest_sha256": _sha256_file(manifest_path),
                    "human_reason": str(signature_payload.get("human_reason") or ""),
                    "submission": False,
                }
                if not signer_store.verify(
                    str(signature_payload.get("signer_id") or ""),
                    str(signature_payload.get("signer_key_id") or ""),
                    signed_payload,
                    str(signature_payload.get("signature_hmac") or ""),
                ):
                    raise ClosureError("signature HMAC verification failed")
            elif scheme != "legacy-unsigned":
                raise ClosureError("unsupported signature scheme: " + scheme)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        final = output_dir / bundle_name
        if final.exists():
            raise ClosureError("evidence bundle already exists: %s" % final)
        staging = output_dir / (".%s.staging-%s" % (bundle_name, uuid.uuid4().hex[:10]))
        staging.mkdir()
        file_entries: List[Dict[str, Any]] = []
        try:
            for index, (source_text, expected) in enumerate(
                sorted(files.items(), key=lambda item: str(item[0])), 1
            ):
                if not _is_sha256(expected):
                    raise ClosureError("invalid evidence digest for %s" % source_text)
                source = Path(str(source_text))
                if not source.is_absolute():
                    candidates = [
                        (manifest_path.parent / source).resolve(),
                        (Path.cwd() / source).resolve(),
                    ]
                    source = next((item for item in candidates if item.is_file()), candidates[0])
                else:
                    source = source.resolve()
                if not source.is_file():
                    raise ClosureError("evidence file not found: %s" % source)
                raw = source.read_bytes()
                actual = _sha256_bytes(raw)
                if actual != expected:
                    raise ClosureError("evidence changed since signature: %s" % source)
                relative = "artifacts/%02d-%s" % (
                    index, _safe_artifact_name(source.name, "artifact")
                )
                _write_bytes_durable(staging / relative, raw)
                file_entries.append({
                    "role": "artifact",
                    "source_path": str(source),
                    "bundle_path": relative,
                    "sha256": actual,
                    "bytes": len(raw),
                })

            manifest_raw = manifest_path.read_bytes()
            manifest_digest = _sha256_bytes(manifest_raw)
            export_relative = "manifest/export-manifest.json"
            _write_bytes_durable(staging / export_relative, manifest_raw)
            file_entries.append({
                "role": "export-manifest",
                "source_path": str(manifest_path.resolve()),
                "bundle_path": export_relative,
                "sha256": manifest_digest,
                "bytes": len(manifest_raw),
            })

            if selected_signature is not None and signature_payload is not None:
                signature_raw = selected_signature.read_bytes()
                signature_relative = "signature/signature.json"
                _write_bytes_durable(staging / signature_relative, signature_raw)
                file_entries.append({
                    "role": "signature",
                    "source_path": str(selected_signature.resolve()),
                    "bundle_path": signature_relative,
                    "sha256": _sha256_bytes(signature_raw),
                    "bytes": len(signature_raw),
                })

            artifact_count = sum(1 for entry in file_entries if entry["role"] == "artifact")
            bundle_manifest = {
                "schema_version": BUNDLE_SCHEMA,
                "bundle_id": "BND-" + uuid.uuid4().hex[:12],
                "created_at": _now(),
                "status": "sealed",
                "source_export_manifest": {
                    "source_path": str(manifest_path.resolve()),
                    "bundle_path": export_relative,
                    "sha256": manifest_digest,
                },
                "export": {
                    "report_id": export.get("report_id"),
                    "revalidated_report_id": export.get("revalidated_report_id"),
                    "closure_checks_sha256": export.get("closure_checks_sha256"),
                    "revalidated_at": export.get("revalidated_at"),
                    "submission": False,
                },
                "signature": {
                    "present": selected_signature is not None,
                    "signature_id": (signature_payload or {}).get("signature_id"),
                },
                "artifact_count": artifact_count,
                "files": file_entries,
                "note": "self-contained byte-verified copy; anchor manifest_sha256 externally",
            }
            _write_json_durable(staging / "bundle-manifest.json", bundle_manifest)

            staged = self._verify_bundle(staging, signer_store=signer_store)
            if staged["status"] != "clean":
                raise ClosureError("staged evidence bundle failed verification: %s" % "; ".join(staged["errors"]))
            _fsync_dir(staging)
            if final.exists():
                raise ClosureError("evidence bundle already exists: %s" % final)
            try:
                atomic_replace(staging, final)
            except OSError as exc:
                raise ClosureError("cannot publish evidence bundle atomically: %s" % exc)
            _fsync_dir(output_dir)
            manifest_out = final / "bundle-manifest.json"
            return {
                "status": "sealed",
                "bundle": str(final),
                "manifest": str(manifest_out),
                "manifest_sha256": _sha256_file(manifest_out),
                "artifact_count": artifact_count,
                "file_count": len(file_entries),
                "signed": selected_signature is not None,
            }
        except Exception:
            if staging.exists():
                shutil.rmtree(str(staging), ignore_errors=True)
            raise

    def verify_bundle(
        self, bundle: Path, signer_store: Optional[SignerStore] = None
    ) -> Dict[str, Any]:
        return self._verify_bundle(Path(bundle), signer_store=signer_store)

    def _verify_bundle(
        self, bundle: Path, signer_store: Optional[SignerStore] = None
    ) -> Dict[str, Any]:
        root = Path(bundle)
        manifest_path = root / "bundle-manifest.json"
        result: Dict[str, Any] = {
            "status": "stale",
            "bundle": str(root.resolve()),
            "manifest": str(manifest_path.resolve()),
            "manifest_sha256": "",
            "artifact_count": 0,
            "signed": False,
            "signature_verified": False,
            "checks": [],
            "warnings": [],
            "errors": [],
        }
        if not root.is_dir() or not manifest_path.is_file():
            result["errors"].append("bundle-manifest.json is missing")
            return result
        result["manifest_sha256"] = _sha256_file(manifest_path)
        try:
            manifest = self._read_json_object(manifest_path, "bundle manifest")
        except ClosureError as exc:
            result["errors"].append(str(exc))
            return result
        if manifest.get("schema_version") != BUNDLE_SCHEMA:
            result["errors"].append("unsupported bundle schema")
        if manifest.get("status") != "sealed":
            result["errors"].append("bundle is not sealed")
        entries = manifest.get("files")
        if not isinstance(entries, list) or not entries:
            result["errors"].append("bundle has no files")
            return result
        allowed_roles = {"artifact", "export-manifest", "signature"}
        artifact_count = 0
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                result["errors"].append("file entry %d is not an object" % index)
                continue
            role = entry.get("role")
            if role not in allowed_roles:
                result["errors"].append("file entry %d has an invalid role" % index)
                continue
            if role == "artifact":
                artifact_count += 1
            if role == "signature":
                result["signed"] = True
            expected = entry.get("sha256")
            expected_bytes = entry.get("bytes")
            try:
                target = _confined_path(root, str(entry.get("bundle_path", "")))
            except ClosureError as exc:
                result["errors"].append(str(exc))
                continue
            check = {
                "role": role,
                "bundle_path": entry.get("bundle_path"),
                "sha256": expected,
                "bytes": expected_bytes,
                "status": "stale",
            }
            if not target.is_file():
                result["errors"].append("missing file: %s" % entry.get("bundle_path"))
                result["checks"].append(check)
                continue
            raw = target.read_bytes()
            actual = _sha256_bytes(raw)
            check["observed_sha256"] = actual
            check["observed_bytes"] = len(raw)
            if actual != expected:
                result["errors"].append("digest mismatch: %s" % entry.get("bundle_path"))
            elif not isinstance(expected_bytes, int) or len(raw) != expected_bytes:
                result["errors"].append("size mismatch: %s" % entry.get("bundle_path"))
            else:
                check["status"] = "clean"
            result["checks"].append(check)
        if manifest.get("artifact_count") != artifact_count:
            result["errors"].append("artifact_count does not match the sealed file list")
        export_entries = [
            entry for entry in entries
            if isinstance(entry, dict) and entry.get("role") == "export-manifest"
        ]
        if not export_entries:
            result["errors"].append("bundle has no sealed export manifest")
        source_export = manifest.get("source_export_manifest")
        if isinstance(source_export, dict):
            if not export_entries or export_entries[0].get("sha256") != source_export.get("sha256"):
                result["errors"].append("sealed export manifest does not match source digest")
        else:
            result["errors"].append("bundle has no source_export_manifest record")
        sealed_export = manifest.get("export")
        if not isinstance(sealed_export, dict) or sealed_export.get("submission") is not False:
            result["errors"].append("bundle export is not marked submission=false")
        if export_entries:
            try:
                export_path = _confined_path(root, str(export_entries[0].get("bundle_path", "")))
                export_payload = self._read_json_object(export_path, "sealed export manifest")
                if isinstance(sealed_export, dict):
                    for key in ("report_id", "closure_checks_sha256", "submission"):
                        if export_payload.get(key) != sealed_export.get(key):
                            result["errors"].append(
                                "sealed export manifest disagrees with bundle record: %s" % key
                            )
            except ClosureError as exc:
                result["errors"].append(str(exc))
        signature_meta = manifest.get("signature")
        signature_entries = [
            entry for entry in entries
            if isinstance(entry, dict) and entry.get("role") == "signature"
        ]
        if isinstance(signature_meta, dict) and signature_meta.get("present") is True and not signature_entries:
            result["errors"].append("bundle says a signature is present but none is sealed")
        if signature_entries:
            try:
                signature_path = _confined_path(root, str(signature_entries[0].get("bundle_path", "")))
                signature_payload = self._read_json_object(signature_path, "sealed signature")
                expected_report = (sealed_export or {}).get("report_id")
                if signature_payload.get("report_id") != expected_report:
                    result["errors"].append("sealed signature report_id does not match export")
                if signature_payload.get("submission") is not False:
                    result["errors"].append("sealed signature is not submission=false")
                scheme = str(signature_payload.get("signature_scheme") or "legacy-unsigned")
                if scheme == SIGNATURE_SCHEME:
                    if signer_store is None:
                        result["errors"].append("HMAC signature requires a signer store for verification")
                    else:
                        signed_payload = {
                            "schema_version": "closure-signature-0.2",
                            "report_id": str(expected_report),
                            "export_manifest_sha256": str(export_entries[0].get("sha256")),
                            "human_reason": str(signature_payload.get("human_reason") or ""),
                            "submission": False,
                        }
                        if signer_store.verify(
                            str(signature_payload.get("signer_id") or ""),
                            str(signature_payload.get("signer_key_id") or ""),
                            signed_payload,
                            str(signature_payload.get("signature_hmac") or ""),
                        ):
                            result["signature_verified"] = True
                        else:
                            result["errors"].append("sealed signature HMAC verification failed")
                elif scheme != "legacy-unsigned":
                    result["errors"].append("unsupported sealed signature scheme: " + scheme)
                else:
                    result["warnings"].append("legacy-unsigned signature; no HMAC identity proof")
            except ClosureError as exc:
                result["errors"].append(str(exc))
        result["artifact_count"] = artifact_count
        result["status"] = "clean" if not result["errors"] else "stale"
        return result

    @staticmethod
    def _read_json_object(path: Path, label: str) -> Dict[str, Any]:
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ClosureError("cannot read %s %s: %s" % (label, path, exc))
        if not isinstance(value, dict):
            raise ClosureError("%s must contain a JSON object: %s" % (label, path))
        return value


def audit_pipeline_bundle(
    bundle_dir: Path,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Static audit of a pipeline artifact directory.

    This is deliberately a *structural* audit: it checks that the artifacts
    claim only what their upstream objects support. It never turns a missing
    human gate into a pass. A structurally consistent bundle can still be
    ``blocked`` because no claim/closure exists.
    """
    root = Path(bundle_dir)
    checks: List[Dict[str, str]] = []

    def add(check_id: str, status: str, detail: str) -> None:
        checks.append({"id": check_id, "status": status, "detail": detail})

    required = (
        "demo.json",
        "paper.json",
        "paper.md",
        "report.md",
        "experiment.json",
        "figure.svg",
    )
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        add("artifacts_present", "fail", "missing: " + ", ".join(missing))
        report = _audit_report(root, checks, output_dir)
        return report
    add("artifacts_present", "pass", "core artifacts are present")

    try:
        demo = json.loads((root / "demo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        add("demo_readable", "fail", "cannot read demo.json: %s" % exc)
        return _audit_report(root, checks, output_dir)
    add("demo_readable", "pass", "demo.json parsed")
    modules = demo.get("modules") or {}
    literature = modules.get("literature") or {}
    idea = modules.get("idea") or {}
    design = modules.get("experiment") or {}
    paper = modules.get("paper") or {}
    run = modules.get("run") or {}
    figure = modules.get("figure") or {}
    protocol = modules.get("protocol") or {}
    hits = literature.get("hits") or []
    spans = literature.get("spans") or []
    hit_map = {str(hit.get("source_id")): hit for hit in hits if isinstance(hit, dict)}
    span_ids = {str(span.get("span_id")) for span in spans if isinstance(span, dict)}

    bad_spans = []
    for span in spans:
        source_id = str(span.get("source_id"))
        if source_id not in hit_map:
            bad_spans.append("%s:source-not-in-hits" % span.get("span_id"))
        elif not span.get("text") or not isinstance(span.get("start"), int) or not isinstance(span.get("end"), int):
            bad_spans.append("%s:no-locator" % span.get("span_id"))
        elif bool(hit_map[source_id].get("full_text")) is not True:
            bad_spans.append("%s:abstract-only" % span.get("span_id"))
    if bad_spans:
        add("s1_span_source_link", "fail", "; ".join(bad_spans[:6]))
    else:
        add("s1_span_source_link", "pass", "%d spans resolve to full-text hits" % len(spans))

    fixture_hits = any(bool(hit.get("fixture")) for hit in hits)
    if demo.get("fixture_mode") and not fixture_hits:
        add("s1_fixture_label", "warn", "fixture_mode=true but no fixture hit")
    elif not demo.get("fixture_mode") and fixture_hits:
        add("s1_fixture_label", "fail", "fixture hit presented as non-fixture evidence")
    else:
        add("s1_fixture_label", "pass", "fixture flag is consistent")

    candidate_refs = []
    for candidate in idea.get("candidates") or []:
        if not candidate.get("falsification"):
            candidate_refs.append("%s:no-falsification" % candidate.get("idea_id"))
        for ref in candidate.get("evidence_refs") or []:
            if str(ref) not in span_ids:
                candidate_refs.append("%s:unknown-ref-%s" % (candidate.get("idea_id"), ref))
    if candidate_refs:
        add("s2_candidate_grounding", "fail", "; ".join(candidate_refs[:6]))
    else:
        add("s2_candidate_grounding", "pass", "candidates have falsification and existing span refs")

    design_bad = [
        str(ref) for ref in (design.get("evidence_refs") or [])
        if str(ref) not in span_ids
    ]
    if design_bad:
        add("s4_design_grounding", "fail", "unknown evidence refs: " + ", ".join(design_bad[:6]))
    else:
        add("s4_design_grounding", "pass", "design references existing spans")

    gates = {str(gate.get("gate")): str(gate.get("status")) for gate in demo.get("gates") or []}
    if gates.get("G2") in ("pass", "ready"):
        if protocol.get("status") != "frozen":
            add("g2_requires_protocol", "fail", "G2 is ready/pass without a frozen ProtocolCard")
        else:
            add("g2_requires_protocol", "pass", "G2 has a frozen ProtocolCard")
    else:
        add("g2_requires_protocol", "pass", "G2 is not claimed as passed")

    capsule = run.get("capsule") or {}
    evidence = run.get("evidence") or {}
    if capsule and evidence:
        if str(capsule.get("run_id")) != str(evidence.get("run_id")):
            add("s5_ea_run_binding", "fail", "capsule.run_id != EA.run_id")
        else:
            add("s5_ea_run_binding", "pass", "capsule and EA share run_id")
    else:
        add("s5_ea_run_binding", "warn", "no run capsule/EA in this bundle")

    draft = run.get("claim_draft_record") or {}
    if draft:
        refs = [str(item) for item in draft.get("evidence_refs") or []]
        ea_id = str(evidence.get("artifact_id") or "")
        if draft.get("status") != "draft_needs_human":
            add("s5_claim_draft_state", "fail", "claim draft is not marked draft_needs_human")
        elif ea_id and ea_id not in refs:
            add("s5_claim_draft_state", "fail", "claim draft does not reference its EA")
        else:
            add("s5_claim_draft_state", "pass", "claim draft is unsigned and EA-bound")
    else:
        add("s5_claim_draft_state", "warn", "no claim draft in this bundle")

    claims = paper.get("claims") or []
    primary = next((slot for slot in paper.get("slots") or [] if slot.get("slot_id") == "result.primary"), {})
    if claims and primary.get("status") != "bound_claim":
        add("paper_claim_binding", "fail", "paper has claims but result.primary is not bound_claim")
    elif not claims and primary.get("status") == "bound_claim":
        add("paper_claim_binding", "fail", "result.primary is bound_claim without paper.claims")
    else:
        add("paper_claim_binding", "pass", "paper claim binding is consistent")

    manifest = figure.get("manifest") or {}
    result_figure = run.get("result_figure") or {}
    result_manifest = result_figure.get("manifest") or {}
    figure_slot = next(
        (slot for slot in paper.get("slots") or [] if slot.get("slot_id") == "result.figure"),
        {},
    )
    if figure_slot.get("status") == "bound_figure":
        if result_manifest.get("schematic") is not True and result_manifest.get("figure_id"):
            add("s6_schematic_not_result", "pass", "result.figure is backed by a data figure manifest")
        else:
            add("s6_schematic_not_result", "fail", "result.figure is bound without a data-backed result manifest")
    elif manifest.get("schematic") is True:
        add("s6_schematic_not_result", "pass", "schematic figure is not bound as result.figure")
    else:
        add("s6_schematic_not_result", "pass", "no schematic/result figure binding conflict")

    if not paper.get("draft"):
        add("paper_readable_draft", "warn", "paper has no draft sections")
    else:
        add("paper_readable_draft", "pass", "%d draft sections" % len(paper.get("draft")))

    if gates.get("G5") in ("pass", "ready"):
        add("g5_requires_closure", "fail", "G5 is ready/pass but this bundle has no closure report")
    else:
        add("g5_requires_closure", "pass", "G5 is not claimed as passed")

    return _audit_report(root, checks, output_dir)


def _audit_report(
    root: Path,
    checks: List[Dict[str, str]],
    output_dir: Optional[Path],
) -> Dict[str, Any]:
    failures = [item for item in checks if item["status"] == "fail"]
    warnings = [item for item in checks if item["status"] == "warn"]
    if failures:
        status = "structural_failure"
    else:
        status = "structurally_consistent_but_not_closed"
    report = {
        "schema_version": "pipeline-static-audit/1",
        "bundle": str(root),
        "status": status,
        "summary": {
            "checks": len(checks),
            "pass": len([item for item in checks if item["status"] == "pass"]),
            "warn": len(warnings),
            "fail": len(failures),
        },
        "checks": checks,
        "boundary": (
            "Static audit only: it verifies artifact-to-artifact support and "
            "does not re-run experiments, verify citation content, or sign claims."
        ),
    }
    if output_dir is not None:
        path = Path(output_dir) / "audit-report.json"
        _write_json(path, report)
        report["path"] = str(path)
    return report
