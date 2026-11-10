"""Fetch recent top-conference papers that expose an arXiv PDF.

This is a bounded, opt-in acquisition adapter. It does not crawl publisher
sites, does not bypass paywalls, and does not claim that an arXiv comment is an
independent acceptance verification. Each PDF keeps its venue claim, comment,
arXiv URL, SHA-256 and license note; local parsing still decides what becomes
evidence.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .arxiv_fetcher import ArxivFetchError, ArxivFetcher

SUPPORTED_VENUES = {
    "NeurIPS": ("NeurIPS", "NIPS"),
    "ICLR": ("ICLR",),
    "ICML": ("ICML",),
    "ACL": ("ACL",),
    "EMNLP": ("EMNLP",),
    "AAAI": ("AAAI",),
    "CVPR": ("CVPR",),
    "KDD": ("KDD",),
}
ACCEPT_RE = re.compile(
    r"\b(accepted|published|to appear|camera[- ]ready|oral|spotlight|poster|conference paper|main conference)\b",
    re.I,
)
REJECT_RE = re.compile(
    r"\b(workshop|manuscript style|format|template|submitted|under review|preprint|"
    r"technical report|extended abstract|doctoral consortium|demo track|findings|"
    r"position paper track|srw|symposium)\b|@\s*(ICLR|ICML|NeurIPS|ACL|EMNLP|AAAI)\b",
    re.I,
)
TOPIC_TERMS = (
    "agent", "agentic", "language model", "llm", "scientific discovery",
    "research automation", "self-improv", "tool use", "multi-agent", "memory",
    "reasoning", "benchmark", "scientific", "automated research",
)
STRONG_TERMS = (
    "agent", "agentic", "self-improv", "scientific discovery",
    "research automation", "multi-agent", "tool use", "ai scientist",
)
TOPIC_QUERY = (
    '(abs:"agent" OR abs:"agentic" OR abs:"self-improvement" '
    'OR abs:"scientific discovery" OR abs:"research automation" '
    'OR abs:"multi-agent" OR abs:"tool use")'
)
TITLE_TERMS = (
    "agent", "agentic", "multi-agent", "self-improv", "scientific discovery",
    "research automation", "ai scientist", "tool-augmented", "tool use", "memory",
)


class ConferenceFetchError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _base_id(value: str) -> str:
    return re.sub(r"v[0-9]+$", "", str(value or "").strip())


def _venue_year_pattern(venue: str, year: int) -> re.Pattern:
    return re.compile(r"\b%s\s*[- ]?\s*%d\b" % (re.escape(venue), year), re.I)


def _topic_score(result: Dict[str, Any]) -> int:
    text = (str(result.get("title") or "") + " " + str(result.get("abstract") or "")).lower()
    return sum(1 for term in TOPIC_TERMS if term in text)


def _acceptance(comment: str, venue: str, year: int) -> Tuple[bool, str]:
    comment = str(comment or "").strip()
    if not comment:
        return False, "no arXiv comment"
    if not _venue_year_pattern(venue, year).search(comment):
        return False, "comment does not name %s %d" % (venue, year)
    if REJECT_RE.search(comment):
        return False, "not a main-track acceptance: " + comment[:160]
    if not ACCEPT_RE.search(comment):
        return False, "no acceptance marker: " + comment[:160]
    return True, ""


def _iter_venue_years(venues: Sequence[str], years: Sequence[int]) -> Iterable[Tuple[str, int]]:
    for venue in venues:
        for year in years:
            yield venue, year


def fetch_top_conference_corpus(
    target_dir: Path,
    *,
    venues: Sequence[str],
    years: Sequence[int],
    topic: str,
    max_papers: int = 24,
    max_per_venue: int = 4,
    max_candidates: int = 40,
    allow_network: bool = False,
    fetcher: Optional[ArxivFetcher] = None,
) -> Dict[str, Any]:
    if not allow_network:
        raise ConferenceFetchError(
            "network access is disabled; pass --allow-network / allow_network=true explicitly"
        )
    clean_venues = []
    for venue in venues:
        key = str(venue or "").strip()
        if key not in SUPPORTED_VENUES:
            raise ConferenceFetchError(
                "unsupported venue %s; choose from %s"
                % (key, ", ".join(sorted(SUPPORTED_VENUES)))
            )
        if key not in clean_venues:
            clean_venues.append(key)
    clean_years = []
    for year in years:
        try:
            value = int(year)
        except (TypeError, ValueError):
            raise ConferenceFetchError("invalid year: %s" % year)
        if value < 2018 or value > 2100:
            raise ConferenceFetchError("year out of range: %d" % value)
        if value not in clean_years:
            clean_years.append(value)
    if not clean_venues or not clean_years:
        raise ConferenceFetchError("at least one venue and one year are required")
    topic = str(topic or "").strip()
    if len(topic) < 2:
        raise ConferenceFetchError("topic is required")
    max_papers = max(1, min(int(max_papers), 80))
    max_per_venue = max(1, min(int(max_per_venue), 12))
    max_candidates = max(5, min(int(max_candidates), 50))
    client = fetcher or ArxivFetcher()
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    downloaded: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    seen_ids = set()
    per_venue: Dict[str, int] = {venue: 0 for venue in clean_venues}
    for venue, year in _iter_venue_years(clean_venues, clean_years):
        if len(downloaded) >= max_papers:
            break
        query = 'co:"%s %d" AND %s' % (venue, year, TOPIC_QUERY)
        try:
            results = client.search_query(query, max_results=max_candidates, sort_by="submittedDate")
        except ArxivFetchError as exc:
            skipped.append({"venue": venue, "year": str(year), "reason": str(exc)})
            continue
        candidates = []
        for result in results:
            base = _base_id(str(result.get("arxiv_id") or ""))
            if not base or base in seen_ids:
                continue
            ok, reason = _acceptance(str(result.get("comment") or ""), venue, year)
            if not ok:
                skipped.append(
                    {
                        "arxiv_id": result.get("arxiv_id", ""),
                        "venue": venue,
                        "year": str(year),
                        "reason": reason,
                    }
                )
                continue
            score = _topic_score(result)
            title_text = str(result.get("title") or "").lower()
            title_hit = any(term in title_text for term in TITLE_TERMS)
            llm_title_hit = any(
                term in title_text for term in ("llm", "language model", "language agent", "foundation model")
            )
            if not title_hit:
                skipped.append(
                    {
                        "arxiv_id": result.get("arxiv_id", ""),
                        "venue": venue,
                        "year": str(year),
                        "reason": "title has no agent/research term",
                    }
                )
                continue
            if "multi-agent" in title_text and not llm_title_hit:
                skipped.append(
                    {
                        "arxiv_id": result.get("arxiv_id", ""),
                        "venue": venue,
                        "year": str(year),
                        "reason": "multi-agent paper without language-model title signal",
                    }
                )
                continue
            if score < 3:
                skipped.append(
                    {
                        "arxiv_id": result.get("arxiv_id", ""),
                        "venue": venue,
                        "year": str(year),
                        "reason": "weak topic relevance (score=%d)" % score,
                    }
                )
                continue
            candidates.append((score, result))
        candidates.sort(
            key=lambda item: (item[0], str(item[1].get("published") or "")),
            reverse=True,
        )
        for score, result in candidates:
            if len(downloaded) >= max_papers or per_venue[venue] >= max_per_venue:
                break
            base = _base_id(str(result.get("arxiv_id") or ""))
            seen_ids.add(base)
            venue_dir = target / ("%s-%d" % (venue.lower(), year))
            try:
                saved = client.download(result, venue_dir)
            except ArxivFetchError as exc:
                skipped.append(
                    {
                        "arxiv_id": result.get("arxiv_id", ""),
                        "venue": venue,
                        "year": str(year),
                        "reason": str(exc),
                    }
                )
                continue
            meta_path = Path(str(saved["meta"]))
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            meta.update(
                {
                    "venue": "%s %d" % (venue, year),
                    "venue_claim": str(result.get("comment") or ""),
                    "venue_source": "arXiv comment; acceptance not independently verified",
                    "topic": topic,
                    "topic_score": score,
                    "corpus": "topconf",
                }
            )
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            downloaded.append(
                {
                    "arxiv_id": result.get("arxiv_id"),
                    "title": result.get("title"),
                    "authors": result.get("authors") or [],
                    "abstract": result.get("abstract"),
                    "year": result.get("year"),
                    "venue": "%s %d" % (venue, year),
                    "venue_claim": result.get("comment"),
                    "topic_score": score,
                    "url": result.get("url"),
                    "pdf_url": result.get("pdf_url"),
                    "license_note": result.get("license_note"),
                    "pdf": saved["pdf"],
                    "meta": saved["meta"],
                    "sha256": saved["sha256"],
                    "bytes": saved["bytes"],
                }
            )
            per_venue[venue] += 1
            if len(downloaded) >= max_papers or per_venue[venue] >= max_per_venue:
                break

    manifest = {
        "schema_version": "conference-corpus-0.1",
        "topic": topic,
        "venues": clean_venues,
        "years": clean_years,
        "max_papers": max_papers,
        "max_per_venue": max_per_venue,
        "downloaded_count": len(downloaded),
        "per_venue": per_venue,
        "downloaded": downloaded,
        "skipped": skipped[:200],
        "created_at": _now(),
        "boundary": (
            "Only arXiv-hosted PDFs with an arXiv comment naming an accepted venue/year are downloaded. "
            "Acceptance is not independently verified; no paywall bypass; PDFs are not evidence until "
            "local parsing produces spans. Not an exhaustive conference proceedings crawl."
        ),
    }
    (target / "conference-corpus.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Top-Conference Corpus",
        "",
        "- topic: %s" % topic,
        "- venues: %s" % ", ".join(clean_venues),
        "- years: %s" % ", ".join(str(year) for year in clean_years),
        "- downloaded: %d" % len(downloaded),
        "- boundary: arXiv versions with accepted-venue comments; acceptance not independently verified.",
        "",
    ]
    for item in downloaded:
        lines += [
            "## %s" % item.get("title"),
            "",
            "- venue claim: %s" % item.get("venue"),
            "- arXiv: %s" % item.get("url"),
            "- PDF: `%s`" % item.get("pdf"),
            "- SHA-256: `%s`" % item.get("sha256"),
            "- comment: %s" % str(item.get("venue_claim") or "")[:300],
            "",
        ]
    (target / "conference-corpus.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest
