"""Deterministic section replacement for Qoder-authored revisions.

Qoder writes the replacement body; this module preserves the rest of the draft,
requires no new REF or numeric token, and does not call a model.
"""

import hashlib
import re
from typing import Any, Dict

from .manuscript_review import (
    _join_markdown_sections,
    _normalised_numbers,
    _section_matches,
)


class ManuscriptEditError(ValueError):
    pass


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _split_editable_sections(text: str):
    parts = re.split(r"(?m)(?=^#{2,3}\s+)", text or "")
    preamble = parts[0] if parts and not re.match(r"^#{2,3}\s+", parts[0].lstrip()) else ""
    sections = []
    for part in parts[1:]:
        lines = part.splitlines()
        if not lines:
            continue
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip("\n")
        sections.append(
            {
                "heading": heading,
                "title": re.sub(r"^#{2,3}\s*", "", heading).strip(),
                "body": body,
            }
        )
    return preamble, sections


def replace_section(
    text: str,
    section: str,
    replacement: str,
    *,
    expected_section_sha256: str = "",
) -> Dict[str, Any]:
    preamble, sections = _split_editable_sections(text)
    matches = [
        index
        for index, item in enumerate(sections)
        if _section_matches(section, item.get("title") or "")
    ]
    if len(matches) != 1:
        raise ManuscriptEditError(
            "section must match exactly one heading; matched %d" % len(matches)
        )
    index = matches[0]
    target = sections[index]
    old_body = str(target.get("body") or "")
    old_sha = hashlib.sha256(old_body.encode("utf-8")).hexdigest()
    if expected_section_sha256 and expected_section_sha256 != old_sha:
        raise ManuscriptEditError("section changed since it was read; re-read before editing")
    body = str(replacement or "").strip("\n")
    if not body.strip():
        raise ManuscriptEditError("replacement body is empty")
    if body.lstrip().startswith("##"):
        raise ManuscriptEditError("replacement must be a section body, not a heading")
    old_refs = set(re.findall(r"\[(REF-[0-9]{2,})\]", old_body))
    new_refs = set(re.findall(r"\[(REF-[0-9]{2,})\]", body))
    if not new_refs.issubset(old_refs):
        raise ManuscriptEditError(
            "replacement adds citations: " + ", ".join(sorted(new_refs - old_refs))
        )
    old_numbers = _normalised_numbers(old_body)
    new_numbers = _normalised_numbers(body)
    added_numbers = [
        value
        for value in new_numbers
        if not any(abs(value - old) <= 1e-9 for old in old_numbers)
    ]
    if added_numbers:
        raise ManuscriptEditError(
            "replacement adds numeric tokens: " + ", ".join(str(value) for value in added_numbers)
        )
    target["body"] = body
    new_text = _join_markdown_sections(preamble, sections)
    return {
        "schema_version": "manuscript-section-edit-0.1",
        "section": target.get("title"),
        "text": new_text,
        "old_section_sha256": old_sha,
        "new_section_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "removed_refs": sorted(old_refs - new_refs),
        "removed_numbers": sorted(
            {value for value in old_numbers if value not in new_numbers}
        ),
        "removed_chars": max(0, len(old_body) - len(body)),
        "boundary": (
            "Deterministic section replacement only: no model call, no new REF/number, "
            "no Claim/EA/gate/signature; run support review and audit on the new draft."
        ),
    }
