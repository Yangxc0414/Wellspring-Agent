"""Read-only model profile catalog for agent hosts.

Exposes profile ids, labels, provider ids, model names and key availability only.
It never returns API keys, masked keys, base URLs or local paths, and it makes no
network call.
"""

from typing import Any, Dict, List, Optional, Sequence

from .models import GatewayStore, ModelGateway
from .models.types import KEYLESS_PROVIDER_KINDS

CATALOG_SCHEMA = "model-profile-catalog-0.1"
CATALOG_BOUNDARY = (
    "Profile ids and model names only; no keys, masked keys, base URLs or local paths. "
    "has_key means a key is present in the process environment or session store, not that "
    "the model is reachable, independent or high quality."
)

PANEL_SCHEMA = "critic-panel-0.1"
PANEL_BOUNDARY = (
    "A suggested bench is a supply assignment, not a review: distinct provider+model configs make "
    "structural independence possible but do not prove independent outputs, and an eligible panel "
    "still grants no novelty verdict and passes no gate."
)
CRITIC_ROLES = ("novelty", "evidence", "feasibility")


def profile_catalog(store_path=None) -> Dict[str, Any]:
    try:
        if store_path is None:
            from .models.store import default_store_path

            # A pathless GatewayStore is intentionally ephemeral: reading the built-in defaults
            # here would ignore RESEARCH_AGENT_MODEL_STORE and show a config the CLI is not using.
            store_path = default_store_path()
        gateway = ModelGateway(GatewayStore(store_path))
    except Exception as exc:
        raise ValueError("model gateway config is unreadable: %s" % type(exc).__name__)
    profiles: List[Dict[str, Any]] = []
    for profile_id in sorted(gateway.store.profiles):
        profile = gateway.store.profiles[profile_id]
        provider = gateway.store.provider(profile.provider_id)
        status = gateway.keys.status(provider)
        keyless = provider.kind in KEYLESS_PROVIDER_KINDS
        profiles.append(
            {
                "profile_id": profile.profile_id,
                "label": profile.label,
                "provider_id": provider.provider_id,
                "provider_label": provider.label,
                "kind": provider.kind,
                "model": profile.model,
                "has_key": bool(status.get("configured")),
                "keyless": keyless,
                "supply": "host_agent" if keyless else "provider",
                "json_mode": bool(profile.json_mode),
            }
        )
    # A keyless host-agent profile cannot demonstrate a different provider: two of them are
    # the same host model answering twice, so they never count as a diverse judge pair.
    available = [item for item in profiles if item["has_key"] and not item["keyless"]]
    host_supply = [item for item in profiles if item["keyless"]]
    pairs: List[List[str]] = []
    for left_index in range(len(available)):
        for right_index in range(left_index + 1, len(available)):
            left = available[left_index]
            right = available[right_index]
            if left["provider_id"] == right["provider_id"]:
                continue
            pairs.append([left["profile_id"], right["profile_id"]])
            if len(pairs) >= 6:
                break
        if len(pairs) >= 6:
            break
    bindings = {
        module: profile_id
        for module, profile_id in sorted(gateway.store.bindings.items())
        if profile_id in gateway.store.profiles
    }
    host_modules = sorted(
        module
        for module, profile_id in bindings.items()
        if gateway.store.provider(gateway.store.profiles[profile_id].provider_id).kind
        in KEYLESS_PROVIDER_KINDS
    )
    catalog = {
        "schema_version": CATALOG_SCHEMA,
        "profiles": profiles,
        "available_profiles": len(available),
        "diverse_judge_pairs": pairs,
        "host_agent_profiles": [item["profile_id"] for item in host_supply],
        "host_agent_bound_modules": host_modules,
        "bindings": bindings,
        "config_warning": bool(gateway.store.warning),
        "note": (
            "Use diverse_judge_pairs for a multi-judge panel and critic_panel to staff an "
            "independent critic bench; if both are empty, configure a key for at least two "
            "providers. A suggestion is availability, not proof of independence. keyless "
            "profiles are host-agent supply: they need no API key but never count as an "
            "independent provider."
        ),
        "boundary": CATALOG_BOUNDARY,
    }
    catalog["critic_panel"] = _panel_from(catalog, CRITIC_ROLES)
    return catalog


def _panel_from(catalog: Dict[str, Any], roles: Sequence[str]) -> Dict[str, Any]:
    usable = [item for item in catalog["profiles"] if item["has_key"]]
    proposer_profile = str((catalog.get("bindings") or {}).get("idea") or "")
    proposer_key = ""
    for item in usable:
        if item["profile_id"] == proposer_profile:
            proposer_key = "%s::%s" % (item["provider_id"].lower(), item["model"].lower())

    by_supply: Dict[str, Dict[str, Any]] = {}
    for item in usable:
        key = "%s::%s" % (item["provider_id"].lower(), item["model"].lower())
        by_supply.setdefault(key, item)
    # Prefer a supply the proposer is not using, so the bench can be staffed off the same row.
    ordered = sorted(
        by_supply.items(),
        key=lambda entry: (entry[0] == proposer_key, entry[0]),
    )
    chosen: List[Dict[str, Any]] = []
    chosen_keys: List[str] = []
    for key, item in ordered:
        if key == proposer_key and len(by_supply) > 1:
            continue
        chosen.append(item)
        chosen_keys.append(key)
        if len(chosen) >= len(roles):
            break

    suggested = {}
    for index, role in enumerate(roles):
        if index < len(chosen):
            suggested[role] = chosen[index]["profile_id"]
    complete = len(chosen) >= len(roles)
    missing = max(0, len(roles) - len(chosen))
    return {
        "schema_version": PANEL_SCHEMA,
        "roles": list(roles),
        "distinct_supplies": len(by_supply),
        "usable_profiles": [item["profile_id"] for item in usable],
        "supplies": [
            {
                "supply_key": key,
                "profile_id": item["profile_id"],
                "provider_id": item["provider_id"],
                "model": item["model"],
                "kind": item["kind"],
                "keyless": item["keyless"],
            }
            for key, item in ordered
        ],
        "proposer_profile": proposer_profile,
        "proposer_excluded": bool(proposer_key) and proposer_key not in chosen_keys,
        "panel_possible": complete,
        "suggested": suggested,
        "missing_supplies": missing,
        "note": (
            "run `innovation review --independent` to staff the bench from this panel, or "
            "`--critic role=profile_id` to choose it yourself; with %d distinct supply the panel "
            "stays single_author and its scores remain a process signal"
            % len(by_supply)
        ),
        "boundary": PANEL_BOUNDARY,
    }


def critic_panel(store_path=None, roles: Sequence[str] = CRITIC_ROLES) -> Dict[str, Any]:
    """Which profiles could staff an independent critic bench, and what is still missing.

    Two profiles pointing at the same provider+model are one supply: the config rows differ but the
    answering model does not, so counting profiles would let a user manufacture a bench of one. The
    proposer is kept off the bench, because a model scoring its own ideas leaves author bias
    uncontrolled — that is what the measured single-author finding actually showed.
    """
    return _panel_from(profile_catalog(store_path), roles)
