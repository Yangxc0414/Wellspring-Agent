"""Local full-text corpus: user-provided PDF / TXT / Markdown with page anchors.

This adapter is deliberately local and opt-in. It extracts text per PDF page,
keeps a stable file hash as the source id, and never pretends that an empty or
scanned PDF is full text. No OCR, no network, no URL fetching.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..contracts import SourceHit

SUPPORTED_SUFFIXES = (".pdf", ".txt", ".md", ".markdown")
GENERATED_SIDECAR_FILES = {
    "arxiv-sources.md",
    "arxiv-sources.json",
    "conference-corpus.md",
    "conference-corpus.json",
    "source-manifest.md",
    "source-manifest.json",
}
TOKEN_RE = re.compile(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")


class LocalDocumentError(RuntimeError):
    pass


def _tokens(text: str) -> List[str]:
    return TOKEN_RE.findall((text or "").lower())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_pdf(path: Path) -> tuple:
    try:
        import fitz  # PyMuPDF

        document = fitz.open(str(path))
        pages = [page.get_text("text") for page in document]
        metadata = document.metadata or {}
        document.close()
        return pages, metadata
    except Exception:
        pass
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as document:
            pages = [(page.extract_text() or "") for page in document.pages]
        return pages, {}
    except Exception:
        pass
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "") for page in reader.pages]
        metadata = dict(reader.metadata or {})
        return pages, metadata
    except Exception as exc:
        raise LocalDocumentError("cannot extract PDF text from %s: %s" % (path, exc))


def _read_text(path: Path) -> tuple:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="gb18030", errors="replace")
    return [text], {}


def _metadata(path: Path) -> Dict[str, Any]:
    for candidate in (path.with_name(path.name + ".meta.json"), path.with_suffix(".meta.json")):
        if candidate.is_file():
            try:
                value = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    return value
            except (OSError, ValueError):
                pass
    return {}


class LocalDocumentRetriever:
    fixture_mode = False

    def __init__(self, root: Path, recursive: bool = True):
        self.root = Path(root)
        if not self.root.is_dir():
            raise LocalDocumentError("local corpus directory not found: " + str(self.root))
        pattern = "**/*" if recursive else "*"
        self._docs: Dict[str, Dict[str, Any]] = {}
        for path in sorted(self.root.glob(pattern)):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if path.name.startswith(".") or path.name.lower() in GENERATED_SIDECAR_FILES:
                continue
            try:
                if path.suffix.lower() == ".pdf":
                    pages, pdf_meta = _read_pdf(path)
                else:
                    pages, pdf_meta = _read_text(path)
                meta = {**pdf_meta, **_metadata(path)}
                digest = _sha256(path)
                source_id = "LOCAL-" + digest[:10]
                clean_pages = [str(page).strip() for page in pages]
                readable = any(clean_pages)
                sections = [
                    {"name": "Page %d" % index, "page": index, "text": text}
                    for index, text in enumerate(clean_pages, start=1)
                    if text
                ]
                title = str(meta.get("title") or meta.get("Title") or path.stem)
                year = meta.get("year")
                try:
                    year = int(year) if year is not None else None
                except (TypeError, ValueError):
                    year = None
                self._docs[source_id] = {
                    "source_id": source_id,
                    "title": title,
                    "year": year,
                    "venue": str(meta.get("venue") or "local corpus"),
                    "doi": meta.get("doi"),
                    "abstract": clean_pages[0][:500] if clean_pages else "",
                    "full_text": readable,
                    "license": str(meta.get("license") or "user-provided"),
                    "fixture": False,
                    "url": str(path),
                    "source_sha256": digest,
                    "sections": sections,
                    "path": str(path),
                }
            except LocalDocumentError:
                continue
        if not self._docs:
            raise LocalDocumentError(
                "no readable .pdf/.txt/.md files found in: " + str(self.root)
            )

    def _score(self, document: Dict[str, Any], query: str) -> float:
        terms = _tokens(query)
        if not terms:
            return 0.0
        title = str(document.get("title") or "").lower()
        body = " ".join(str(section.get("text") or "") for section in document.get("sections") or []).lower()
        score = 0.0
        for term in terms:
            if term in title:
                score += 4.0
            count = body.count(term)
            if count:
                score += 1.0 + min(count, 8) * 0.15
        return score

    def search(self, query: str, limit: int) -> List[SourceHit]:
        ranked = []
        for document in self._docs.values():
            score = self._score(document, query)
            if score > 0:
                ranked.append((score, document))
        ranked.sort(key=lambda item: (-item[0], str(item[1]["source_id"])))
        hits: List[SourceHit] = []
        for _, document in ranked[: max(0, int(limit))]:
            hits.append(
                SourceHit(
                    source_id=document["source_id"],
                    title=document["title"],
                    year=document["year"],
                    venue=document["venue"],
                    doi=document["doi"],
                    abstract=document["abstract"],
                    full_text=document["full_text"],
                    license=document["license"],
                    fixture=False,
                    url=document["url"],
                )
            )
        return hits

    def full_text(self, source_id: str) -> Optional[Dict[str, Any]]:
        document = self._docs.get(source_id)
        if not document or not document.get("full_text"):
            return None
        return document

    def snapshot(self) -> Dict[str, Any]:
        return {
            "root": str(self.root),
            "count": len(self._docs),
            "documents": [
                {
                    "source_id": item["source_id"],
                    "title": item["title"],
                    "pages": len(item["sections"]),
                    "full_text": item["full_text"],
                    "license": item["license"],
                    "source_sha256": item["source_sha256"],
                }
                for item in self._docs.values()
            ],
            "boundary": "user-provided local text; no OCR, no network; page anchors are PDF page numbers",
        }
