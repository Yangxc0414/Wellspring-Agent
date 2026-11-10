"""Offline fixture retriever.

This adapter exists so the S1 module can be tested without network, keys, or
real papers. Fixture data is synthetic and must never be cited as evidence.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..contracts import SourceHit


class FixtureRetriever:
    fixture_mode = True

    def __init__(self, corpus_path: Optional[Path] = None):
        root = Path(__file__).resolve().parents[2]
        self.corpus_path = Path(corpus_path) if corpus_path else root / "modules" / "literature" / "fixtures" / "corpus.json"
        data = json.loads(self.corpus_path.read_text(encoding="utf-8"))
        if data.get("fixture") is not True:
            raise ValueError("fixture corpus must be explicitly marked fixture: true")
        self._docs: Dict[str, Dict[str, Any]] = {}
        for paper in data.get("papers", []):
            self._docs[str(paper["source_id"])] = paper

    def _score(self, paper: Dict[str, Any], query: str) -> int:
        q = query.lower()
        score = 0
        for keyword in paper.get("keywords", []):
            if str(keyword).lower() in q:
                score += 3
        haystack = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
        for term in re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", q):
            if term and term in haystack:
                score += 1
        return score

    def search(self, query: str, limit: int) -> List[SourceHit]:
        ranked = []
        for paper in self._docs.values():
            score = self._score(paper, query)
            if score > 0:
                ranked.append((score, paper))
        ranked.sort(key=lambda item: (-item[0], str(item[1]["source_id"])))
        hits: List[SourceHit] = []
        for _, paper in ranked[: max(0, limit)]:
            hits.append(
                SourceHit(
                    source_id=str(paper["source_id"]),
                    title=str(paper.get("title", "")),
                    year=paper.get("year"),
                    venue=str(paper.get("venue", "")),
                    doi=paper.get("doi"),
                    abstract=str(paper.get("abstract", "")),
                    full_text=bool(paper.get("full_text")),
                    license=str(paper.get("license", "fixture-only")),
                    fixture=True,
                )
            )
        return hits

    def full_text(self, source_id: str) -> Optional[Dict[str, Any]]:
        paper = self._docs.get(source_id)
        if not paper or not paper.get("full_text"):
            return None
        return paper
