"""Deterministic S1 source cards and screening ledger.

This is an audit view over LiteratureResult: it records source metadata,
full-text status, duplicates, recency and screening counts. It does not create
spans, claims or evidence, and metadata completeness is not claim support.
"""

import hashlib
import json
import re
from datetime import date
from typing import Any, Dict, List, Optional

SOURCE_LEDGER_SCHEMA = "literature-ledger-0.1"
BOUNDARY = (
    "source screening and metadata audit only; peer-review status is unknown; "
    "metadata presence is not claim support"
)


def _sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _norm_doi(value: Any) -> str:
    text = str(value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def _source_type(hit: Dict[str, Any]) -> str:
    doi = _norm_doi(hit.get("doi"))
    venue = _clean(hit.get("venue")).lower()
    title = _clean(hit.get("title")).lower()
    if "arxiv" in doi or "arxiv" in venue or "preprint" in venue or "arxiv" in title:
        return "preprint"
    if venue:
        return "venue_indexed"
    return "unknown"


def _metadata_complete(hit: Dict[str, Any]) -> bool:
    return bool(
        _clean(hit.get("title"))
        and hit.get("year")
        and _clean(hit.get("venue"))
        and (_norm_doi(hit.get("doi")) or _clean(hit.get("url")))
    )


def build_source_ledger(
    literature: Dict[str, Any],
    question: str,
    source_scope: Optional[List[str]] = None,
    current_year: Optional[int] = None,
) -> Dict[str, Any]:
    current = int(current_year or date.today().year)
    hits = [item for item in (literature.get("hits") or []) if isinstance(item, dict)]
    spans = [item for item in (literature.get("spans") or []) if isinstance(item, dict)]
    span_by_source: Dict[str, List[str]] = {}
    for span in spans:
        source_id = str(span.get("source_id") or "")
        span_id = str(span.get("span_id") or "")
        if source_id and span_id:
            span_by_source.setdefault(source_id, []).append(span_id)
    seen: Dict[str, str] = {}
    cards: List[Dict[str, Any]] = []
    counts = {
        "found": len(hits),
        "included_full_text": 0,
        "abstract_only": 0,
        "duplicates": 0,
        "metadata_incomplete": 0,
        "with_locatable_span": 0,
        "preprints": 0,
    }
    warnings: List[str] = []
    for hit in hits:
        source_id = str(hit.get("source_id") or "")
        title = _clean(hit.get("title"))
        doi = _norm_doi(hit.get("doi"))
        dedupe_key = doi or re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title.lower())
        duplicate_of = seen.get(dedupe_key, "") if dedupe_key else ""
        if dedupe_key and not duplicate_of:
            seen[dedupe_key] = source_id
        full_text = bool(hit.get("full_text"))
        span_ids = span_by_source.get(source_id, [])
        metadata_ok = _metadata_complete(hit)
        source_type = _source_type(hit)
        if duplicate_of:
            counts["duplicates"] += 1
            screening = "duplicate"
        elif not metadata_ok:
            counts["metadata_incomplete"] += 1
            if full_text and span_ids:
                counts["included_full_text"] += 1
                screening = "included_full_text_metadata_incomplete"
            elif full_text:
                screening = "full_text_no_span_metadata_incomplete"
                warnings.append(
                    "%s: full text exists but no locatable span was parsed" % source_id
                )
            else:
                counts["abstract_only"] += 1
                screening = "abstract_only_metadata_incomplete"
        elif full_text and span_ids:
            counts["included_full_text"] += 1
            screening = "included_full_text"
        elif full_text:
            screening = "full_text_no_span"
            warnings.append("%s: full text exists but no locatable span was parsed" % source_id)
        else:
            counts["abstract_only"] += 1
            screening = "abstract_only"
        if span_ids:
            counts["with_locatable_span"] += 1
        if source_type == "preprint":
            counts["preprints"] += 1
        year = hit.get("year")
        age = (current - int(year)) if isinstance(year, int) else None
        cards.append(
            {
                "source_id": source_id,
                "title": title,
                "year": year,
                "venue": _clean(hit.get("venue")),
                "doi": str(hit.get("doi") or ""),
                "url": str(hit.get("url") or ""),
                "license": _clean(hit.get("license")),
                "full_text": full_text,
                "fixture": bool(hit.get("fixture", False)),
                "source_type": source_type,
                "peer_reviewed": "unknown",
                "metadata_complete": metadata_ok,
                "metadata_sha256": _sha256(
                    {
                        "title": title,
                        "year": year,
                        "venue": _clean(hit.get("venue")),
                        "doi": _norm_doi(hit.get("doi")),
                        "url": str(hit.get("url") or ""),
                        "full_text": full_text,
                    }
                ),
                "duplicate_of": duplicate_of,
                "screening": screening,
                "span_count": len(span_ids),
                "span_ids": span_ids[:20],
                "age_years": age,
                "recent_5y": age is not None and age <= 5,
            }
        )
    doi_count = sum(1 for card in cards if card["doi"])
    recent = sum(1 for card in cards if card["recent_5y"])
    years = [int(card["year"]) for card in cards if isinstance(card.get("year"), int)]
    coverage = literature.get("coverage") or {}
    brief = literature.get("brief") or {}
    gaps = list(coverage.get("gaps") or [])
    if not cards:
        warnings.append("no source hit was returned")
    if counts["included_full_text"] == 0:
        warnings.append("no full-text source with a locatable span; evidence gates cannot pass")
    if counts["abstract_only"]:
        warnings.append(
            "%d abstract-only source(s) remain clues, not evidence" % counts["abstract_only"]
        )
    if counts["duplicates"]:
        warnings.append("%d duplicate source record(s) detected" % counts["duplicates"])
    if counts["metadata_incomplete"]:
        warnings.append(
            "%d source(s) have incomplete metadata for a GB/T 7714 reference"
            % counts["metadata_incomplete"]
        )
    if cards and doi_count == 0:
        warnings.append("no source has a DOI; reference verification is limited")
    if cards and recent == 0:
        warnings.append("no source is from the last five years")
    status = (
        "ready"
        if counts["included_full_text"] > 0 and counts["with_locatable_span"] > 0
        else "insufficient"
    )
    return {
        "schema_version": SOURCE_LEDGER_SCHEMA,
        "run_id": str(literature.get("run_id") or ""),
        "question": _clean(question),
        "source_scope": list(source_scope or []),
        "fixture_mode": bool(literature.get("fixture_mode", False)),
        "status": status,
        "counts": counts,
        "metadata": {
            "doi_coverage": round(doi_count / len(cards), 3) if cards else 0.0,
            "year_range": [min(years), max(years)] if years else [],
            "recent_5y": recent,
            "current_year": current,
        },
        "source_types": {
            "preprint": counts["preprints"],
            "venue_indexed": sum(1 for card in cards if card["source_type"] == "venue_indexed"),
            "unknown": sum(1 for card in cards if card["source_type"] == "unknown"),
        },
        "peer_reviewed": {
            "verified": 0,
            "unknown": len(cards),
            "note": "venue indexing does not prove peer review",
        },
        "coverage": {
            "score": coverage.get("score"),
            "saturation": brief.get("saturation", ""),
            "gaps": gaps,
            "facets": brief.get("facets") or [],
        },
        "screening_flow": {
            "found": counts["found"],
            "duplicates_removed": counts["duplicates"],
            "full_text_included": counts["included_full_text"],
            "abstract_only_not_evidence": counts["abstract_only"],
            "metadata_incomplete": counts["metadata_incomplete"],
            "full_text_no_span": sum(
                1 for card in cards
                if card["screening"] in (
                    "full_text_no_span", "full_text_no_span_metadata_incomplete",
                )
            ),
        },
        "sources": cards,
        "warnings": warnings,
        "boundary": BOUNDARY,
    }
