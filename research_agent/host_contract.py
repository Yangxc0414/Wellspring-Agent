"""Host capability contract: what a connecting agent can do here, and what will stop it.

The runtime used to assume the host spoke MCP and could serve a model. Both assumptions broke in
practice — a long-lived MCP process caches stale modules, and some hosts can only exchange files.
This module turns "what does this host need to know" into one read-only answer that every transport
can serve, so a plugin degrades by declared capability instead of failing unexpectedly.

It negotiates nothing about gates: the human-only operations are reported as unavailable to *every*
transport, and this function never performs them.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import build_info

# Stages that ask a model for generated content. Everything else is deterministic or read-only.
MODEL_STAGES = {
    "S2 ideas": "idea",
    "S3 review": "idea",
    "S4 experiment design": "experiment",
    "S8 draft prose": "paper",
    "S2-S3 innovation review": "idea",
    "S13 support judge": "judge",
}
CAPABILITIES = ("can_call_tools", "can_write_files", "can_serve_model", "long_sessions")
GATE_VERBS = (
    "claim signature",
    "gate decision (G1/G2/S5b/G3/G5)",
    "protocol freeze",
    "closure signature",
    "bundle publish",
    "export approval",
)
BOUNDARY = (
    "read-only negotiation: it reports what would happen, runs no stage, and cannot sign, approve, "
    "freeze, close, publish or export anything through any transport"
)


def _transports(outbox: Optional[Path]) -> Dict[str, Any]:
    from .storage import write_json_atomic  # noqa: F401  (import proves the writer is available)

    mcp_importable = True
    try:
        import importlib

        importlib.import_module("research_agent.mcp_server")
    except Exception:  # pragma: no cover - an install without the package
        mcp_importable = False
    writable = None
    if outbox is not None:
        try:
            Path(outbox).mkdir(parents=True, exist_ok=True)
            probe = Path(outbox) / ".probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            writable = True
        except OSError:
            writable = False
    return {
        "in_process_api": True,
        "http_runtime": True,
        "mcp_stdio": mcp_importable,
        "file_drop": None if outbox is None else bool(writable),
        "file_drop_probe_dir": str(outbox) if outbox else None,
    }


def _model_supply() -> Dict[str, Any]:
    from .models import GatewayStore
    from .models.store import default_store_path

    store = GatewayStore(default_store_path())
    keyless = {
        profile_id
        for profile_id, profile in store.profiles.items()
        if store.provider(profile.provider_id).kind in ("host_agent",)
    }
    bound = dict(sorted(store.bindings.items()))
    suspended = sorted(
        stage for stage, module in MODEL_STAGES.items() if bound.get(module) in keyless
    )
    unbound = sorted(
        module for module in set(MODEL_STAGES.values()) if not bound.get(module)
    )
    return {
        "store_path": str(default_store_path()),
        "bindings": bound,
        "keyless_host_profiles": sorted(keyless),
        "stages_suspended_for_host_answer": suspended,
        "modules_without_binding": unbound,
        "external_key_configured": bool(
            [
                profile_id
                for profile_id, profile in store.profiles.items()
                if store.provider(profile.provider_id).kind not in ("host_agent",)
            ]
        ),
    }


def host_contract(
    declared: Optional[List[str]] = None, outbox: Optional[Path] = None
) -> Dict[str, Any]:
    """Describe the contract for one host, given what it says it can do."""
    claims = [str(item).strip() for item in (declared or []) if str(item).strip()]
    unknown = sorted(set(claims) - set(CAPABILITIES))
    transports = _transports(outbox)
    supply = _model_supply()
    try:
        from .face_coverage import face_matrix

        matrix = face_matrix(include_http=False)
        coverage: Dict[str, Any] = {
            "faces": matrix["faces"],
            "declared": matrix["summary"]["declared"],
            "unaudited": matrix["summary"]["unaudited"],
            "unaudited_capabilities": matrix["unaudited_capabilities"],
            "declaration_problems": matrix["declaration_problems"],
            "entries": matrix["entries"],
            "reverse": matrix["reverse"],
            "http_targets_verified": False,
            "boundary": (
                matrix["boundary"]
                + "; HTTP targets are not verified in this response because the runtime app is not "
                "imported here, so the CLI face and the guarded matrix in face_coverage are the "
                "checked sources"
            ),
        }
    except Exception as exc:
        coverage = {
            "error": "%s: %s" % (type(exc).__name__, exc),
            "boundary": "the face matrix could not be built, which is reported rather than omitted",
        }

    blocked: List[str] = []
    next_commands: List[str] = []
    if "can_serve_model" not in claims and supply["stages_suspended_for_host_answer"]:
        blocked.append("model_stages_suspend_without_a_host_model")
        next_commands.append(
            "python -m research_agent host-model bind --modules idea,experiment,paper "
            "(keep the host as the model) or bind a profile with an external key"
        )
    # Only a host with no tool path depends on files; a tool-capable host is blocked by the
    # missing directory it never uses.
    if (
        "can_call_tools" not in claims
        and "can_write_files" not in claims
        and transports["file_drop"] is not True
    ):
        blocked.append("no_writable_handoff_directory")
        next_commands.append(
            "python -m research_agent handoff export --outbox <dir> (a writable directory is the "
            "only thing a file-only host needs)"
        )
    if "can_call_tools" not in claims and not supply["external_key_configured"]:
        blocked.append("no_tools_and_no_external_model")
        next_commands.append(
            "either let the host call tools over MCP/file-drop, or bind an external model profile"
        )

    return {
        "schema_version": "host-contract-0.3",
        "build": build_info(),
        "face_coverage": coverage,
        "declared_capabilities": sorted(set(claims)),
        "unknown_capabilities": unknown,
        "known_capabilities": list(CAPABILITIES),
        "transports": transports,
        "model_supply": supply,
        "human_only_for_every_transport": list(GATE_VERBS),
        "blocked": blocked,
        "next_commands": next_commands,
        "boundary": BOUNDARY,
    }
