"""Frozen-model candidate proposer for the governed RSI loop.

The model is called through ModelPort and is never trained. Its only output is a
Candidate for skill/process/prompt/knowledge, validated by GovernancePolicy.
"""

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

from .ports import ModelPort
from .rsi import Candidate, GovernancePolicy, RSIPolicyError


class ProposerError(RuntimeError):
    pass


SYSTEM_PROMPT = """You output exactly one valid JSON object and nothing else.
Schema:
{"kind":"process","target":"literature.retrieval.budget","patch":"{\\"retriever\\":\\"minilm\\",\\"max_sources\\":3}","rationale":"...","predicted_effect":"...","parent_id":"","scope":"S1/model-proposal"}
Rules:
- target must be exactly literature.retrieval.budget.
- patch must be a JSON string with retriever in {bm25,minilm} and integer max_sources in {2,3,4}.
- scope must be S1/model-proposal.
- Never touch claim, evidence, gate, rubric, export, signature or authorship.
- No markdown fences, no prose, no extra keys."""


def _extract_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProposerError("model did not return valid JSON: %s" % exc)
    if not isinstance(value, dict):
        raise ProposerError("model output must be a JSON object")
    value.setdefault("kind", "process")
    required = ("kind", "target", "patch", "rationale", "predicted_effect")
    missing = [key for key in required if not str(value.get(key, "")).strip()]
    if missing:
        raise ProposerError("missing candidate fields: " + ", ".join(missing))
    return value


TARGET_ALIASES = {
    "budget": "literature.retrieval.budget",
    "retrieval.budget": "literature.retrieval.budget",
    "literature.retrieval.budget": "literature.retrieval.budget",
}


def _normalize_candidate(data: Dict[str, Any]) -> Dict[str, Any]:
    target = str(data.get("target", "")).strip()
    target = TARGET_ALIASES.get(target.lower(), target)
    patch = data.get("patch")
    if isinstance(patch, dict):
        patch = json.dumps(patch, ensure_ascii=False)
    patch = str(patch or "").strip()
    if target == "literature.retrieval.budget":
        try:
            parsed = json.loads(patch)
        except json.JSONDecodeError as exc:
            raise ProposerError("budget patch must be a JSON object string: %s" % exc)
        if not isinstance(parsed, dict):
            raise ProposerError("budget patch must be a JSON object")
        budget = parsed.get("max_sources")
        if not isinstance(budget, int) or isinstance(budget, bool) or not 1 <= budget <= 64:
            raise ProposerError("budget patch needs integer max_sources in 1..64")
        retriever = str(parsed.get("retriever", "bm25")).strip().lower()
        if retriever not in ("bm25", "minilm"):
            raise ProposerError("budget patch retriever must be bm25 or minilm")
        patch = json.dumps({"retriever": retriever, "max_sources": budget}, ensure_ascii=False)
    data["target"] = target
    data["patch"] = patch
    data["scope"] = str(data.get("scope", "")).strip() or (
        "S1/model-proposal" if target == "literature.retrieval.budget" else ""
    )
    return data


class FrozenModelProposer:
    def __init__(self, model: ModelPort):
        self.model = model

    def propose(self, observation: str, archive_summary: Optional[Dict[str, Any]] = None) -> Candidate:
        return self.propose_with_repair(
            observation, archive_summary, repair_attempts=0
        )["candidate"]

    def propose_with_repair(
        self,
        observation: str,
        archive_summary: Optional[Dict[str, Any]] = None,
        repair_attempts: int = 1,
    ) -> Dict[str, Any]:
        """Schema-repair loop for a frozen model; the model is never trained."""
        if not observation.strip():
            raise ProposerError("observation is required")
        if repair_attempts < 0:
            raise ProposerError("repair_attempts must be >= 0")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Observation:\n%s\n\nArchive summary:\n%s\n\n"
                    "Return one valid JSON object only; choose a cheaper harness "
                    "(bm25 or minilm, max_sources 2-4) without losing public coverage."
                    % (observation, json.dumps(archive_summary or {}, ensure_ascii=False))
                ),
            },
        ]
        errors: List[str] = []
        for attempt in range(repair_attempts + 1):
            raw = self.model.complete(messages, json_mode=True)
            try:
                candidate = self._candidate_from_raw(raw, messages[1]["content"])
            except ProposerError as exc:
                errors.append(str(exc))
                if attempt >= repair_attempts:
                    raise ProposerError(
                        "proposal failed after %d attempt(s): %s" % (attempt + 1, exc)
                    )
                messages = messages + [
                    {"role": "assistant", "content": raw[:2000]},
                    {
                        "role": "user",
                        "content": (
                            "Your previous output was rejected: %s\n"
                            "Return corrected JSON only; obey the schema exactly." % exc
                        ),
                    },
                ]
                continue
            return {
                "candidate": candidate,
                "attempts": attempt + 1,
                "errors": errors,
                "repaired": attempt > 0,
            }
        raise ProposerError("proposal loop ended unexpectedly")

    def _candidate_from_raw(self, raw: str, prompt_text: str = "") -> Candidate:
        data = _extract_json(raw)
        data = _normalize_candidate(data)
        predicted_metrics = data.get("predicted_metrics") or {}
        if not isinstance(predicted_metrics, dict):
            raise ProposerError("predicted_metrics must be an object")
        try:
            candidate = Candidate(
                kind=str(data["kind"]),
                target=str(data["target"]),
                patch=str(data["patch"]),
                rationale=str(data["rationale"]),
                predicted_effect=str(data["predicted_effect"]),
                parent_id=str(data.get("parent_id", "")),
                scope=str(data.get("scope", "")),
                predicted_metrics=predicted_metrics,
                proposer="model",
                proposer_model=str(getattr(self.model, "model_id", "unknown")),
                prompt_sha256=hashlib.sha256(
                    (SYSTEM_PROMPT + "\n" + (prompt_text or "")).encode("utf-8")
                ).hexdigest(),
            )
            GovernancePolicy.check(candidate)
        except RSIPolicyError as exc:
            raise ProposerError("candidate failed policy: %s" % exc)
        return candidate


class RuleBasedProposer:
    """Deterministic test proposer; not a model and not used for claims."""

    def propose(self, observation: str, archive_summary: Optional[Dict[str, Any]] = None) -> Candidate:
        text = observation.lower()
        if "retrieval cost" in text or "retrieval_cost" in text:
            return Candidate(
                kind="process",
                target="literature.retrieval.budget",
                patch=json.dumps({"max_sources": 2}, ensure_ascii=False),
                rationale="retrieval cost observation suggests a cheaper budget trial; recall/coverage gates must hold",
                predicted_effect="non-inferior recall and coverage with fewer sources",
                scope="S1/fixture",
                proposer="rule-based",
            )
        raise ProposerError("no rule matched observation")
