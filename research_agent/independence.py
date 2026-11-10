"""Critic-supply fingerprints: turning "single author review" into a liftable state.

Disclosure alone was honest but useless: the panel reported that one model answered every critic
role, and nothing in the runtime could change that. Here each role can be bound to a distinct model
supply, so the same field becomes a condition the caller can actually satisfy.

A supply is the (provider, model) pair that answers a role. Distinctness is a property of the
declared gateway configuration, not of the outputs: two model ids can share a training corpus, and
one model answering three prompts is not three reviewers. Two host profiles naming the same model
are one supply in two config rows, so the model name is compared rather than the profile id, and
host turns are additionally attributed from the ledger instead of trusted from the binding.
"""

from typing import Any, Dict, List, Optional

PANEL_SCHEMA = "critic-supply-panel-0.1"
PANEL_BOUNDARY = (
    "supply fingerprints are caller-declared gateway configuration plus ledger host labels where a "
    "host agent answered: distinct provider and model ids make a panel structurally independent but "
    "do not prove independent outputs, disagreeing error modes or a different training corpus, and "
    "an admission-eligible panel still validates nothing about novelty, correctness or G1/G2."
)

KIND_PROVIDER_AND_MODEL = "provider_and_model"
KIND_PROVIDER_ONLY = "provider_only"
KIND_MODEL_ONLY = "model_only"
KIND_SINGLE_AUTHOR = "single_author"
KIND_UNVERIFIABLE = "unverifiable"


def supply_of(model: Any) -> Dict[str, str]:
    """Fingerprint the supply behind a ModelPort; unknown fields stay empty and are never guessed."""
    if model is None:
        return {"profile_id": "", "provider_id": "", "kind": "", "model": "", "model_id": "none"}
    model_id = str(getattr(model, "model_id", "") or type(model).__name__).strip()
    return {
        "profile_id": str(getattr(model, "profile_id", "") or ""),
        "provider_id": str(getattr(model, "provider_id", "") or "").strip(),
        "kind": str(getattr(model, "provider_kind", "") or "").strip(),
        "model": str(getattr(model, "model_name", "") or "").strip() or model_id,
        "model_id": model_id,
    }


def supply_key(supply: Dict[str, str]) -> str:
    return "%s::%s" % (
        (supply.get("provider_id") or "").lower(),
        (supply.get("model") or "").lower(),
    )


def _identifiable(supply: Dict[str, str]) -> bool:
    return bool(supply.get("provider_id")) and bool(supply.get("model"))


def evaluate_panel(
    roles: List[str],
    models_by_role: Dict[str, Any],
    proposer: Any = None,
    *,
    rounds: int = 1,
    answered_by: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Judge how independent the critic bench is, role by role."""
    supplies = {role: supply_of(models_by_role.get(role)) for role in roles}
    identifiable = [role for role in roles if _identifiable(supplies[role])]
    keys = [supply_key(supplies[role]) for role in identifiable]
    distinct = sorted(set(keys))
    providers = sorted({supplies[role]["provider_id"].lower() for role in identifiable})
    models = sorted({supplies[role]["model"].lower() for role in identifiable})

    labels = {
        role: sorted(
            {
                str(item).strip()
                for item in (answered_by or {}).get(role) or []
                if str(item).strip()
            }
        )
        for role in roles
    }
    observed = sorted({label for role in identifiable for label in labels[role]})
    attributed = [role for role in identifiable if labels[role]]
    # Every role attributed to a host agent by the ledger, and all of them name the same agent:
    # the configs differ but there is one reviewer, so declared identity is contradicted by use.
    one_host_answered_all = len(attributed) == len(identifiable) and len(observed) == 1

    proposer_supply = supply_of(proposer) if proposer is not None else {}
    proposer_is_critic = bool(
        proposer_supply
        and _identifiable(proposer_supply)
        and supply_key(proposer_supply) in keys
    )

    reasons: List[str] = []
    if len(identifiable) < len(roles):
        reasons.append(
            "%d critic role(s) have no resolvable provider+model fingerprint (%s): identity is "
            "unverifiable, so it cannot count as independent"
            % (
                len(roles) - len(identifiable),
                ", ".join(role for role in roles if role not in identifiable),
            )
        )
    if len(distinct) < len(roles):
        reasons.append(
            "%d critic role(s) share a supply with another role: %d supply answer(s) for %d role(s)"
            % (len(roles) - len(distinct), len(distinct), len(roles))
        )
    if proposer_is_critic:
        reasons.append(
            "the model that proposed these ideas also scored them, so author bias is uncontrolled"
        )
    if one_host_answered_all:
        reasons.append(
            "the ledger attributes every critic turn to one host agent (%s), so distinct profile "
            "configs did not produce distinct reviewers" % ", ".join(observed)
        )

    provider_spread = len(providers) >= len(roles)
    model_spread = len(models) >= len(roles)
    if reasons:
        eligible = False
        kind = (
            KIND_UNVERIFIABLE
            if not identifiable
            else (KIND_SINGLE_AUTHOR if len(distinct) <= 1 else KIND_MODEL_ONLY)
        )
    elif provider_spread and model_spread:
        eligible, kind = True, KIND_PROVIDER_AND_MODEL
    elif provider_spread:
        eligible, kind = True, KIND_PROVIDER_ONLY
    elif model_spread:
        eligible, kind = True, KIND_MODEL_ONLY
    else:
        eligible, kind = False, KIND_SINGLE_AUTHOR

    return {
        "schema_version": PANEL_SCHEMA,
        "roles": list(roles),
        "critic_calls": int(rounds) * int(len(roles)),
        "supplies": {
            role: dict(supplies[role], supply_key=supply_key(supplies[role])) for role in roles
        },
        "proposer": dict(proposer_supply, supply_key=supply_key(proposer_supply))
        if proposer_supply
        else {},
        "proposer_is_critic": proposer_is_critic,
        "distinct_supplies": len(distinct),
        "distinct_model_ids": models,
        "distinct_providers": providers,
        "host_labels": observed,
        "answered_by": labels,
        "one_host_answered_all": one_host_answered_all,
        "single_author_review": len(distinct) <= 1,
        "kind": kind,
        "reasons": reasons,
        "admission_eligible": eligible,
        "requires_distinct_supplies": len(roles),
        "boundary": PANEL_BOUNDARY,
        "reading": _reading(kind, eligible, reasons, observed),
    }


def _reading(kind: str, eligible: bool, reasons: List[str], observed: List[str]) -> str:
    if not eligible:
        return "; ".join(reasons) or (
            "critic supplies are not distinguishable, so these scores are a process signal and "
            "must not be cited as independent review evidence"
        )
    if len(observed) > 1:
        return (
            "critic roles are bound to distinct supplies and the ledger attributes their turns to "
            "%d named host agent(s) (%s); independence is observed at agent level, which still "
            "says nothing about output independence" % (len(observed), ", ".join(observed))
        )
    if kind == KIND_MODEL_ONLY:
        return (
            "each critic role is answered by a different model, but the declared provider is "
            "shared, so disagreement may reflect one vendor's training distribution rather than "
            "independent review"
        )
    if kind == KIND_PROVIDER_ONLY:
        return (
            "each critic role is answered through a different provider, but the model name is the "
            "same, so disagreement may come from serving configuration rather than different models"
        )
    return (
        "every critic role is answered by a distinct provider+model supply that did not propose "
        "these ideas; the panel is structurally independent, which is a supply claim, not proof "
        "of independent outputs"
    )
