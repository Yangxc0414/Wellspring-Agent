"""Read-only retriever for a frozen real-text corpus.

Only corpora explicitly marked ``corpus_kind: real`` are accepted. Every paper
must carry a CC-BY license and a provenance URL; the retriever never writes
claims and never fetches the network.
"""

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..contracts import SourceHit

K1 = 1.5
B = 0.75


def _tokens(text: str) -> List[str]:
    lowered = text.lower().replace("–", " ").replace("—", " ").replace("-", " ")
    return re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", lowered)


class RealCorpusError(ValueError):
    pass


class RealCorpusRetriever:
    fixture_mode = False

    def __init__(self, corpus_path: Path):
        self.corpus_path = Path(corpus_path)
        data = json.loads(self.corpus_path.read_text(encoding="utf-8"))
        if data.get("corpus_kind") != "real" or data.get("fixture") is not False:
            raise RealCorpusError("real corpus must be marked corpus_kind=real and fixture=false")
        self._docs: Dict[str, Dict[str, Any]] = {}
        for paper in data.get("papers", []):
            source_id = str(paper.get("source_id", ""))
            if not source_id:
                raise RealCorpusError("real corpus paper is missing source_id")
            if paper.get("fixture") is not False or not paper.get("full_text"):
                raise RealCorpusError("real corpus paper must be fixture=false and full_text=true: " + source_id)
            if not str(paper.get("license", "")).upper().startswith("CC-BY"):
                raise RealCorpusError("real corpus paper must be CC-BY licensed: " + source_id)
            if not str(paper.get("url", "")).startswith("https://"):
                raise RealCorpusError("real corpus paper needs an https provenance URL: " + source_id)
            if not paper.get("sections"):
                raise RealCorpusError("real corpus paper has no readable sections: " + source_id)
            self._docs[source_id] = paper
        if not self._docs:
            raise RealCorpusError("real corpus is empty")
        self._stats = self._index()
        self._avg_len = sum(stat["dl"] for stat in self._stats.values()) / len(self._stats)

    def _index(self) -> Dict[str, Dict[str, Any]]:
        stats: Dict[str, Dict[str, Any]] = {}
        for source_id, paper in self._docs.items():
            text = " ".join([
                str(paper.get("title", "")),
                str(paper.get("abstract", "")),
                " ".join(str(section.get("text", "")) for section in paper.get("sections", [])),
            ])
            tokens = _tokens(text)
            frequencies: Dict[str, int] = {}
            for token in tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
            stats[source_id] = {"tf": frequencies, "dl": len(tokens)}
        return stats

    def _idf(self, term: str) -> float:
        total = len(self._stats)
        df = sum(1 for stat in self._stats.values() if term in stat["tf"])
        return math.log((total - df + 0.5) / (df + 0.5) + 1)

    def _score(self, source_id: str, query: str) -> float:
        stat = self._stats[source_id]
        score = 0.0
        for term in set(_tokens(query)):
            tf = stat["tf"].get(term, 0)
            if not tf:
                continue
            score += self._idf(term) * tf * (K1 + 1) / (
                tf + K1 * (1 - B + B * stat["dl"] / self._avg_len)
            )
        return score

    def _hit(self, paper: Dict[str, Any]) -> SourceHit:
        return SourceHit(
            source_id=str(paper["source_id"]),
            title=str(paper.get("title", "")),
            year=paper.get("year"),
            venue=str(paper.get("venue", "")),
            doi=paper.get("doi"),
            abstract=str(paper.get("abstract", "")),
            full_text=bool(paper.get("full_text")),
            license=str(paper.get("license", "")),
            fixture=False,
        )

    def search(self, query: str, limit: int) -> List[SourceHit]:
        ranked = []
        for source_id, paper in self._docs.items():
            score = self._score(source_id, query)
            if score > 0:
                ranked.append((score, paper))
        ranked.sort(key=lambda item: (-item[0], str(item[1]["source_id"])))
        hits: List[SourceHit] = []
        for _, paper in ranked[: max(0, limit)]:
            hits.append(self._hit(paper))
        return hits

    def full_text(self, source_id: str) -> Optional[Dict[str, Any]]:
        paper = self._docs.get(source_id)
        if not paper or not paper.get("full_text"):
            return None
        return paper
