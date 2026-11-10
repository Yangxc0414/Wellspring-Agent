"""Candidate paper discovery from three public signals.

This module solves exactly one problem: *where* candidate papers come from.
It deliberately does not solve evidence. Every row is a clue, never a span.

    arXiv keyword search -> existing ``ArxivFetcher`` (reused, not reimplemented)
    HF Daily Papers      -> GET /api/daily_papers?sort=publishedAt
    HF Trending          -> GET /api/daily_papers?sort=trending

The two Hugging Face signals are the SAME documented endpoint with different
sort values (verified against the Hub API docs / ``list_daily_papers``).
Network is off by default; a blocked call returns ``status=blocked`` instead of
an empty list, because an empty discovery must never look like "nothing found".
Downstream, full texts still have to be downloaded and parsed by
``literature run --source local --corpus-dir`` before anything becomes a span.
"""

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .arxiv_fetcher import ArxivFetcher

DISCOVERY_SCHEMA = "paper-discovery-0.1"
HF_DAILY_URL = "https://huggingface.co/api/daily_papers"
DEFAULT_SOURCES = ("arxiv", "hf_daily", "hf_trending")
SORT_BY_SOURCE = {"hf_daily": "publishedAt", "hf_trending": "trending"}
ARXIV_NEW_ID = re.compile(r"^\d{4}\.\d{4,5}$")
ARXIV_OLD_ID = re.compile(r"^[a-z-]+(?:\.[A-Z]{2})?/\d{7}$", re.IGNORECASE)

Transport = Callable[[urllib.request.Request], bytes]


def _default_transport(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=request.timeout) as response:
        return response.read()


def canonical_arxiv_id(value: str) -> str:
    """Normalise 'arXiv:2311.12983v2' / URL forms to a stable comparison key."""
    text = str(value or "").strip().lower()
    text = text.split("?")[0].rstrip("/")
    for prefix in ("https://arxiv.org/abs/", "http://arxiv.org/abs/",
                   "https://arxiv.org/pdf/", "http://arxiv.org/pdf/",
                   "https://www.arxiv.org/abs/"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    if text.startswith("arxiv:"):
        text = text[6:]
    text = text.rstrip(".pdf")
    text = re.sub(r"v\d+$", "", text)
    return text


def _is_arxiv_id(value: str) -> bool:
    text = canonical_arxiv_id(value)
    return bool(ARXIV_NEW_ID.match(text) or ARXIV_OLD_ID.match(text))


def _hf_rows(payload: bytes) -> List[Dict[str, Any]]:
    """Parse the documented list response; tolerate shape changes explicitly."""
    try:
        data = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else str(payload))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("HF daily_papers is not JSON: %s" % exc)
    if not isinstance(data, list):
        raise ValueError("HF daily_papers is not a list")
    rows: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        paper = item.get("paper") if isinstance(item.get("paper"), dict) else {}
        paper_id = str(paper.get("id") or item.get("id") or "").strip()
        title = str(paper.get("title") or item.get("title") or "").strip()
        if not paper_id and not title:
            continue
        rows.append({
            "paper_id": canonical_arxiv_id(paper_id) if paper_id else "",
            "title": title,
            "published_at": str(
                item.get("publishedAt") or item.get("submittedOnDailyAt")
                or paper.get("publishedAt") or ""
            ),
            "upvotes": paper.get("upvotes", item.get("upvotes", 0)),
        })
    return rows


@dataclass
class DiscoveryReport:
    status: str = "blocked"
    query: str = ""
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    by_source: Dict[str, int] = field(default_factory=dict)
    duplicates_removed: int = 0
    network_used: bool = False
    errors: List[str] = field(default_factory=list)
    next_commands: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": DISCOVERY_SCHEMA,
            "status": self.status,
            "query": self.query,
            "candidates": [dict(row) for row in self.candidates],
            "by_source": dict(self.by_source),
            "duplicates_removed": self.duplicates_removed,
            "network_used": self.network_used,
            "errors": list(self.errors),
            "next_commands": list(self.next_commands),
            "boundary": (
                "clue-only: titles/abstracts/metadata are information sources, NOT "
                "evidence. No span, SourceHit, Claim/EA/gate/signature is produced. "
                "Full text must be downloaded and parsed with "
                "'literature run --source local --corpus-dir <dir>' before S1 can use it. "
                "No paywall bypass and no automatic full-text acquisition for HF rows."
            ),
        }


def _candidate(paper_id: str, title: str, source: str, url: str,
               pdf_url: str, published_at: str) -> Dict[str, Any]:
    return {
        "paper_id": paper_id,
        "title": title,
        "sources": [source],
        "url": url,
        "pdf_url": pdf_url,
        "published_at": published_at,
        "clue_only": True,
        "span_eligible": False,
    }


def _merge(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    duplicates = 0
    for row in candidates:
        key = canonical_arxiv_id(row.get("paper_id") or "") or (
            "title:" + str(row.get("title") or "").strip().lower()
        )
        if key in merged:
            duplicates += 1
            existing = merged[key]
            for source in row.get("sources") or []:
                if source not in existing["sources"]:
                    existing["sources"].append(source)
            if not existing.get("pdf_url") and row.get("pdf_url"):
                existing["pdf_url"] = row["pdf_url"]
            if not existing.get("published_at") and row.get("published_at"):
                existing["published_at"] = row["published_at"]
            continue
        merged[key] = dict(row)
        order.append(key)
    return [merged[key] for key in order], duplicates


def discover_papers(
    query: str = "",
    *,
    sources: Sequence[str] = DEFAULT_SOURCES,
    limit_per_source: int = 10,
    allow_network: bool = False,
    timeout: int = 6,
    transport: Optional[Transport] = None,
    arxiv_client: Optional[Any] = None,
) -> DiscoveryReport:
    """Collect and de-duplicate candidate papers. Pure w.r.t. the repository.

    ``transport`` / ``arxiv_client`` are injectable so tests never touch the
    network. Without ``allow_network=True`` no request is made at all.
    """
    selected = [str(source) for source in (sources or DEFAULT_SOURCES)]
    report = DiscoveryReport(query=str(query or "").strip())
    report.by_source = {source: 0 for source in selected}
    if not allow_network:
        report.status = "blocked"
        report.errors.append(
            "network disabled: pass allow_network=True (or --allow-network) to fetch candidates"
        )
        return report

    use_transport = transport or _default_transport
    raw: List[Dict[str, Any]] = []
    for source in selected:
        try:
            if source == "arxiv":
                if not report.query:
                    report.errors.append("arxiv source skipped: --query is required")
                    continue
                client = arxiv_client or ArxivFetcher(
                    timeout=timeout, transport=use_transport
                )
                for hit in client.search(report.query, max_results=limit_per_source):
                    paper_id = canonical_arxiv_id(str(hit.get("arxiv_id") or ""))
                    raw.append(_candidate(
                        paper_id, str(hit.get("title") or ""), "arxiv",
                        str(hit.get("url") or ""), str(hit.get("pdf_url") or ""),
                        str(hit.get("published") or ""),
                    ))
                    report.by_source[source] += 1
                continue
            sort_value = SORT_BY_SOURCE.get(source)
            if not sort_value:
                report.errors.append("unknown source: %s" % source)
                continue
            params = urllib.parse.urlencode({
                "p": 0,
                "limit": max(1, min(int(limit_per_source), 100)),
                "sort": sort_value,
            })
            request = urllib.request.Request(HF_DAILY_URL + "?" + params, method="GET")
            request.timeout = timeout
            for row in _hf_rows(use_transport(request)):
                paper_id = row["paper_id"]
                arxiv_like = _is_arxiv_id(paper_id)
                raw.append(_candidate(
                    paper_id or ("hf:" + row["title"][:40]),
                    row["title"], source,
                    ("https://huggingface.co/papers/" + paper_id) if paper_id else "",
                    ("https://arxiv.org/pdf/" + paper_id) if arxiv_like else "",
                    row["published_at"],
                ))
                report.by_source[source] += 1
        except Exception as exc:  # one source failing must not erase the others
            report.errors.append("%s: %s: %s" % (source, type(exc).__name__, str(exc)[:140]))

    report.candidates, report.duplicates_removed = _merge(raw)
    report.network_used = True
    report.status = "ok" if report.candidates else "empty"
    if report.query:
        report.next_commands.append(
            'python -m research_agent literature fetch --query "%s" '
            '--target-dir <corpus-dir> --max-results 10 --allow-network' % report.query
        )
    report.next_commands.append(
        'python -m research_agent literature run --question "<问题>" '
        '--source local --corpus-dir <corpus-dir> --max-sources 12'
    )
    return report


__all__ = [
    "DISCOVERY_SCHEMA", "HF_DAILY_URL", "DEFAULT_SOURCES", "SORT_BY_SOURCE",
    "DiscoveryReport", "canonical_arxiv_id", "discover_papers",
]
