"""Section-level rewrite planning for existing manuscripts.

The plan is generated before paragraph rewriting: for each selected section it
records the role, issues, paragraph actions and length target. The writer then
follows the plan while the deterministic citation/number guards still apply.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .revision_io import DraftDocument, read_draft
from .storage import write_json_atomic

PLAN_SCHEMA = "revision-plan-0.1"


class RevisionPlanError(ValueError):
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
    raise RevisionPlanError("model did not return valid JSON")


def _section_payload(section: Any) -> Dict[str, Any]:
    blocks = []
    for index, block in enumerate(section.blocks):
        if block.kind not in ("paragraph", "bullet") or len(block.text.strip()) < 40:
            continue
        blocks.append(
            {
                "block_index": index,
                "kind": block.kind,
                "text": block.text.strip()[:1400],
            }
        )
    return {"heading": section.heading, "blocks": blocks}


def _prompt(
    document: DraftDocument,
    sections: Sequence[Any],
    goal: str,
    review_comments: Sequence[str],
) -> List[Dict[str, str]]:
    system = (
        "You are planning a revision of an existing research manuscript. "
        "Do not invent facts, citations, numbers, experiments or results. "
        "Return only JSON."
    )
    payload = {
        "document_title": document.title,
        "language": document.language,
        "goal": goal or "improve clarity, logical flow and argument coherence",
        "review_comments": list(review_comments or [])[:12],
        "sections": [_section_payload(section) for section in sections],
        "requirements": [
            "For each section, state its role, concrete issues, and paragraph-level actions.",
            "Actions must preserve facts, citations, numbers and section order.",
            "Do not propose adding citations, results, experiments or data.",
            "Block indices must refer to the supplied blocks only.",
        ],
    }
    user = (
        "Create a section-level revision plan. Output JSON:\n"
        '{"sections":[{"heading":"","role":"","issues":[""],'
        '"paragraph_actions":[{"block_index":0,"action":"","preserve":[""]}],'
        '"target_length_ratio":"0.9-1.2"}]}\n\n'
        "Input:\n" + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_plan(plan: Dict[str, Any], document: DraftDocument) -> Dict[str, Any]:
    sections = plan.get("sections") if isinstance(plan, dict) else None
    if not isinstance(sections, list) or not sections:
        raise RevisionPlanError("plan must contain a non-empty sections array")
    by_heading = {section.heading: section for section in document.sections}
    validated = []
    for item in sections:
        if not isinstance(item, dict):
            continue
        heading = _clean(item.get("heading"), 200)
        section = by_heading.get(heading)
        if section is None:
            continue
        actions = []
        for action in item.get("paragraph_actions") or []:
            if not isinstance(action, dict):
                continue
            try:
                index = int(action.get("block_index"))
            except (TypeError, ValueError):
                continue
            if not 0 <= index < len(section.blocks):
                continue
            block = section.blocks[index]
            if block.kind not in ("paragraph", "bullet") or len(block.text.strip()) < 40:
                continue
            actions.append(
                {
                    "block_index": index,
                    "action": _clean(action.get("action"), 600),
                    "preserve": [_clean(value, 240) for value in action.get("preserve") or []][:8],
                }
            )
        if not actions:
            continue
        validated.append(
            {
                "heading": heading,
                "role": _clean(item.get("role"), 300),
                "issues": [_clean(value, 300) for value in item.get("issues") or []][:8],
                "paragraph_actions": actions,
                "target_length_ratio": _clean(item.get("target_length_ratio"), 30) or "0.8-1.3",
            }
        )
    if not validated:
        raise RevisionPlanError("plan has no valid section actions")
    return {
        "schema_version": PLAN_SCHEMA,
        "plan_id": "RPLAN-" + uuid.uuid4().hex[:10],
        "created_at": _now(),
        "sections": validated,
        "boundary": "Section-level revision plan only; facts/citations/numbers remain protected.",
    }


def build_revision_plan(
    draft_path: Path,
    model: Any,
    *,
    sections: Optional[Sequence[str]] = None,
    goal: str = "",
    review_comments: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    document = read_draft(Path(draft_path))
    wanted = [item.strip().lower() for item in (sections or []) if str(item).strip()]
    selected = []
    for section in document.sections:
        if not section.heading:
            continue
        if wanted and not any(item in section.heading.lower() for item in wanted):
            continue
        if any(len(block.text.strip()) >= 40 for block in section.blocks if block.kind in ("paragraph", "bullet")):
            selected.append(section)
    if not selected:
        raise RevisionPlanError("no selected sections with rewritable paragraphs")
    raw = model.complete(_prompt(document, selected, goal, review_comments or []), json_mode=True)
    plan = validate_plan(_parse_json(raw), document)
    plan["draft"] = str(Path(draft_path))
    plan["goal"] = _clean(goal, 1000)
    plan["review_comments"] = list(review_comments or [])[:20]
    return plan


def render_plan_markdown(plan: Dict[str, Any]) -> str:
    lines = [
        "# Revision Plan",
        "",
        "- plan: `%s`" % plan.get("plan_id"),
        "- draft: `%s`" % plan.get("draft", ""),
        "- goal: %s" % (plan.get("goal") or "-"),
        "",
    ]
    for section in plan.get("sections") or []:
        lines += [
            "## %s" % section.get("heading"),
            "",
            "- role: %s" % (section.get("role") or "-"),
            "- issues: %s" % ("; ".join(section.get("issues") or []) or "-"),
            "- target length ratio: %s" % section.get("target_length_ratio"),
            "",
        ]
        for action in section.get("paragraph_actions") or []:
            lines.append(
                "- block %s: %s%s"
                % (
                    action.get("block_index"),
                    action.get("action"),
                    (" | preserve: " + "; ".join(action["preserve"])) if action.get("preserve") else "",
                )
            )
        lines.append("")
    lines += [plan.get("boundary", ""), ""]
    return "\n".join(lines)


def write_revision_plan(plan: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "revision-plan.json"
    md_path = output / "revision-plan.md"
    write_json_atomic(json_path, plan)
    md_path.write_text(render_plan_markdown(plan), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
