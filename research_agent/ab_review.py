"""Blind A/B rubric review of an original and a revised manuscript.

The reviewer model sees two anonymous versions of each section and scores
clarity, argument, evidence consistency and academic style. The A/B mapping is
revealed only after scoring. This is an independent-call evaluation, not peer
review or a substitute for human judgment.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .revision_io import read_draft
from .storage import write_json_atomic

AB_SCHEMA = "revision-ab-review-0.1"
DIMENSIONS = ("clarity", "argument", "evidence_consistency", "academic_style")


class ABReviewError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit else text


def _parse_json(raw: str) -> Any:
    value = str(raw or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    try:
        return json.loads(value)
    except ValueError:
        match = re.search(r"\{.*\}", value, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except ValueError:
                pass
    raise ABReviewError("reviewer did not return valid JSON")


def _section_pairs(original: Any, revised: Any, sections: Sequence[str]) -> List[Dict[str, Any]]:
    wanted = [item.strip().lower() for item in sections if str(item).strip()]
    revised_by_heading = {section.heading: section for section in revised.sections}
    pairs = []
    for section in original.sections:
        if not section.heading or section.heading not in revised_by_heading:
            continue
        if wanted and not any(item in section.heading.lower() for item in wanted):
            continue
        original_text = "\n\n".join(
            block.text for block in section.blocks if block.text
        ).strip()
        revised_text = "\n\n".join(
            block.text for block in revised_by_heading[section.heading].blocks if block.text
        ).strip()
        if len(original_text) < 40 or len(revised_text) < 40:
            continue
        pairs.append(
            {
                "heading": section.heading,
                "original": original_text[:6000],
                "revised": revised_text[:6000],
            }
        )
    return pairs


def _review_prompt(
    heading: str,
    first: str,
    second: str,
    round_index: int,
) -> List[Dict[str, str]]:
    system = (
        "You are an independent blind reviewer. You see two anonymous versions "
        "of the same manuscript section, labeled A and B. Do not assume which is "
        "the original or the revision. Score both, then choose a winner. Return JSON only."
    )
    user = """Section: %s
Round: %d

Version A:
%s

Version B:
%s

Score 1-10 on clarity, argument, evidence_consistency and academic_style.
Evidence_consistency means the text does not overstate what its citations/numbers can support.

Return JSON:
{"scores":{"A":{"clarity":1,"argument":1,"evidence_consistency":1,"academic_style":1},"B":{"clarity":1,"argument":1,"evidence_consistency":1,"academic_style":1}},"winner":"A|B|tie","reason":"","issues":{"A":[""],"B":[""]}}
""" % (heading, round_index, first[:5000], second[:5000])
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _normalise(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ABReviewError("review must be an object")
    raw_scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
    scores = {}
    for label in ("A", "B"):
        raw = raw_scores.get(label) if isinstance(raw_scores.get(label), dict) else {}
        scores[label] = {}
        for dimension in DIMENSIONS:
            try:
                value = float(raw.get(dimension))
            except (TypeError, ValueError):
                value = 1.0
            scores[label][dimension] = max(1.0, min(10.0, value))
    winner = _clean(payload.get("winner"), 10).lower()
    if winner not in ("a", "b", "tie"):
        winner = "tie"
    return {
        "scores": scores,
        "winner": winner.upper() if winner != "tie" else "tie",
        "reason": _clean(payload.get("reason"), 1000),
        "issues": {
            label: [_clean(item, 300) for item in (payload.get("issues") or {}).get(label, [])][:8]
            if isinstance(payload.get("issues"), dict) else []
            for label in ("A", "B")
        },
    }


def run_ab_review(
    original_path: Path,
    revised_path: Path,
    model: Any,
    *,
    sections: Optional[Sequence[str]] = None,
    rounds: int = 1,
) -> Dict[str, Any]:
    original = read_draft(Path(original_path))
    revised = read_draft(Path(revised_path))
    pairs = _section_pairs(original, revised, sections or [])
    if not pairs:
        raise ABReviewError("no matching sections with enough text for A/B review")
    rounds = max(1, min(int(rounds), 3))
    results = []
    original_total = {key: [] for key in DIMENSIONS}
    revised_total = {key: [] for key in DIMENSIONS}
    wins = {"original": 0, "revised": 0, "tie": 0}
    for pair in pairs:
        for round_index in range(1, rounds + 1):
            digest = hashlib.sha256(
                (pair["heading"] + ":" + str(round_index)).encode("utf-8")
            ).digest()
            swap = digest[0] % 2 == 1
            first = pair["revised"] if swap else pair["original"]
            second = pair["original"] if swap else pair["revised"]
            raw = model.complete(_review_prompt(pair["heading"], first, second, round_index), json_mode=True)
            review = _normalise(_parse_json(raw))
            first_role = "revised" if swap else "original"
            second_role = "original" if swap else "revised"
            mapping = {"A": first_role, "B": second_role}
            by_role = {
                mapping[label]: review["scores"][label] for label in ("A", "B")
            }
            for dimension in DIMENSIONS:
                original_total[dimension].append(by_role["original"][dimension])
                revised_total[dimension].append(by_role["revised"][dimension])
            if review["winner"] == "tie":
                wins["tie"] += 1
            else:
                wins[mapping[review["winner"]]] += 1
            results.append(
                {
                    "heading": pair["heading"],
                    "round": round_index,
                    "mapping": mapping,
                    "winner": mapping.get(review["winner"], "tie"),
                    "review": review,
                }
            )

    def mean(values: List[float]) -> float:
        return round(sum(values) / max(1, len(values)), 3)

    original_scores = {key: mean(values) for key, values in original_total.items()}
    revised_scores = {key: mean(values) for key, values in revised_total.items()}
    original_overall = mean(list(original_scores.values()))
    revised_overall = mean(list(revised_scores.values()))
    if revised_overall > original_overall:
        overall_winner = "revised"
    elif original_overall > revised_overall:
        overall_winner = "original"
    else:
        overall_winner = "tie"
    result = {
        "schema_version": AB_SCHEMA,
        "created_at": _now(),
        "original": str(Path(original_path)),
        "revised": str(Path(revised_path)),
        "model": getattr(model, "model_id", type(model).__name__),
        "sections": [pair["heading"] for pair in pairs],
        "rounds": rounds,
        "original_scores": original_scores,
        "revised_scores": revised_scores,
        "original_overall": original_overall,
        "revised_overall": revised_overall,
        "overall_winner": overall_winner,
        "wins": wins,
        "results": results,
        "boundary": (
            "Blind model A/B review with anonymous labels; independent call, not peer review. "
            "The reviewer model/provider is recorded; same-provider review is not a substitute for "
            "human or multi-family evaluation."
        ),
    }
    return result


def render_ab_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Blind A/B Review",
        "",
        "- original: `%s`" % result.get("original"),
        "- revised: `%s`" % result.get("revised"),
        "- reviewer: `%s`" % result.get("model"),
        "- overall: **%s** (original %.2f vs revised %.2f)"
        % (result.get("overall_winner"), result.get("original_overall", 0), result.get("revised_overall", 0)),
        "- wins: original=%s revised=%s tie=%s"
        % (
            result.get("wins", {}).get("original", 0),
            result.get("wins", {}).get("revised", 0),
            result.get("wins", {}).get("tie", 0),
        ),
        "",
        "## Dimensions",
        "",
        "| dimension | original | revised | delta |",
        "| --- | --- | --- | --- |",
    ]
    for dimension in DIMENSIONS:
        original = result.get("original_scores", {}).get(dimension, 0)
        revised = result.get("revised_scores", {}).get(dimension, 0)
        lines.append("| %s | %.2f | %.2f | %+.2f |" % (dimension, original, revised, revised - original))
    lines += ["", "## Section results", ""]
    for item in result.get("results") or []:
        lines.append(
            "- %s round %d: winner=%s; %s"
            % (item["heading"], item["round"], item["winner"], item["review"].get("reason", ""))
        )
    lines += ["", result.get("boundary", ""), ""]
    return "\n".join(lines)
