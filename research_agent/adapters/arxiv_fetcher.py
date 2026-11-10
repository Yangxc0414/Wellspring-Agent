"""Explicit opt-in arXiv search and open-PDF download.

This adapter never bypasses a paywall. It searches the public arXiv Atom API,
downloads only PDF links exposed by arXiv, records provenance/hashes, and then
hands the files to the existing local PDF parser for span extraction.
"""

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from xml.etree import ElementTree

API_URL = "https://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
MAX_PDF_BYTES = 30 * 1024 * 1024
DEFAULT_MIN_INTERVAL = 1.0


class ArxivFetchError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _default_transport(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=request.timeout) as response:
        return response.read()


def _entry_id(value: str) -> str:
    match = re.search(r"abs/([^/]+)$", str(value or ""))
    return match.group(1) if match else ""


def _pdf_link(entry: ElementTree.Element) -> str:
    for link in entry.findall("atom:link", NS):
        if str(link.get("title") or "").lower() == "pdf":
            href = str(link.get("href") or "").strip()
            if href.startswith("http://"):
                href = "https://" + href[len("http://"):]
            if href.startswith("https://arxiv.org/pdf/"):
                return href
    arxiv_id = _entry_id(entry.findtext("atom:id", default="", namespaces=NS))
    return "https://arxiv.org/pdf/" + arxiv_id if arxiv_id else ""


class ArxivFetcher:
    live_api = "arxiv"
    fixture_mode = False

    def __init__(
        self,
        timeout: int = 30,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        transport: Optional[Callable[[urllib.request.Request], bytes]] = None,
        user_agent: str = "research-agent-workbench/0.1 (arxiv adapter)",
    ):
        self.timeout = max(5, min(int(timeout), 120))
        self.min_interval = max(0.0, min(float(min_interval), 10.0))
        self._transport = transport or _default_transport
        self.user_agent = user_agent
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = self._last_request + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _get(self, request: urllib.request.Request) -> bytes:
        request.add_header("User-Agent", self.user_agent)
        request.timeout = self.timeout
        last_error: Optional[Exception] = None
        for attempt in range(3):
            self._throttle()
            try:
                return self._transport(request)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                break
        raise ArxivFetchError("arXiv request failed: %s" % last_error)

    def search(self, query: str, max_results: int = 4) -> List[Dict[str, Any]]:
        query = _clean(query)
        if not query:
            raise ArxivFetchError("query is required")
        if len(query) > 300:
            raise ArxivFetchError("query is too long")
        return self.search_query("all:" + query, max_results=max_results, sort_by="relevance")

    def search_query(
        self,
        search_query: str,
        max_results: int = 4,
        sort_by: str = "submittedDate",
    ) -> List[Dict[str, Any]]:
        query = _clean(search_query)
        if not query:
            raise ArxivFetchError("search_query is required")
        if len(query) > 600:
            raise ArxivFetchError("search_query is too long")
        count = max(1, min(int(max_results), 50))
        params = urllib.parse.urlencode(
            {
                "search_query": query,
                "start": 0,
                "max_results": count,
                "sortBy": sort_by,
                "sortOrder": "descending",
            }
        )
        request = urllib.request.Request(API_URL + "?" + params, method="GET")
        try:
            payload = self._get(request)
        except ArxivFetchError:
            raise
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise ArxivFetchError("arXiv returned invalid Atom XML: %s" % exc)
        results: List[Dict[str, Any]] = []
        for entry in root.findall("atom:entry", NS):
            arxiv_id = _entry_id(entry.findtext("atom:id", default="", namespaces=NS))
            if not arxiv_id:
                continue
            published = _clean(entry.findtext("atom:published", default="", namespaces=NS))
            authors = [
                _clean(author.findtext("atom:name", default="", namespaces=NS))
                for author in entry.findall("atom:author", NS)
            ]
            results.append(
                {
                    "arxiv_id": arxiv_id,
                    "title": _clean(entry.findtext("atom:title", default="", namespaces=NS)),
                    "abstract": _clean(entry.findtext("atom:summary", default="", namespaces=NS)),
                    "authors": [name for name in authors if name],
                    "published": published,
                    "year": int(published[:4]) if published[:4].isdigit() else None,
                    "doi": _clean(entry.findtext("arxiv:doi", default="", namespaces=NS)) or None,
                    "comment": _clean(
                        entry.findtext("arxiv:comment", default="", namespaces=NS)
                    ),
                    "url": "https://arxiv.org/abs/" + arxiv_id,
                    "pdf_url": _pdf_link(entry),
                    "license_note": "arXiv PDF; verify the article license before redistribution",
                }
            )
        return results

    def download(self, result: Dict[str, Any], target_dir: Path) -> Dict[str, Any]:
        pdf_url = str(result.get("pdf_url") or "")
        arxiv_id = str(result.get("arxiv_id") or "unknown")
        if not pdf_url:
            raise ArxivFetchError("arXiv entry has no PDF link: " + arxiv_id)
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", arxiv_id)[:80] or "paper"
        pdf_path = target / ("arxiv-%s.pdf" % safe_id)
        if pdf_path.is_file():
            data = pdf_path.read_bytes()
            if not data.startswith(b"%PDF"):
                raise ArxivFetchError("existing file is not a PDF: " + arxiv_id)
        else:
            request = urllib.request.Request(pdf_url, method="GET")
            data = self._get(request)
            if len(data) > MAX_PDF_BYTES:
                raise ArxivFetchError("PDF exceeds %d bytes: %s" % (MAX_PDF_BYTES, arxiv_id))
            if not data.startswith(b"%PDF"):
                raise ArxivFetchError("downloaded content is not a PDF: " + arxiv_id)
            tmp = pdf_path.with_suffix(".pdf.tmp")
            tmp.write_bytes(data)
            tmp.replace(pdf_path)
        digest = _sha256(data)
        meta = {
            "title": result.get("title"),
            "authors": result.get("authors") or [],
            "year": result.get("year"),
            "venue": "arXiv",
            "doi": result.get("doi"),
            "url": result.get("url"),
            "pdf_url": pdf_url,
            "arxiv_id": arxiv_id,
            "license": result.get("license_note"),
            "source_sha256": digest,
            "retrieved_at": _now(),
        }
        meta_path = pdf_path.with_suffix(".meta.json")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"pdf": str(pdf_path), "meta": str(meta_path), "sha256": digest, "bytes": len(data)}

    def fetch(
        self,
        query: str,
        target_dir: Path,
        max_results: int = 4,
        allow_network: bool = False,
    ) -> Dict[str, Any]:
        if not allow_network:
            raise ArxivFetchError(
                "network access is disabled; pass --allow-network / allow_network=true explicitly"
            )
        results = self.search(query, max_results=max_results)
        downloaded: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []
        for result in results:
            try:
                saved = self.download(result, target_dir)
                downloaded.append({**result, **saved})
            except ArxivFetchError as exc:
                skipped.append({"arxiv_id": str(result.get("arxiv_id")), "reason": str(exc)})
        manifest = {
            "schema_version": "arxiv-source-manifest-0.1",
            "query": _clean(query),
            "requested": max_results,
            "found": len(results),
            "downloaded": downloaded,
            "skipped": skipped,
            "created_at": _now(),
            "boundary": (
                "open arXiv PDFs only; no paywall bypass; verify article license before redistribution; "
                "download is not evidence until local PDF parsing makes spans"
            ),
        }
        target = Path(target_dir)
        (target / "arxiv-sources.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        lines = ["# arXiv Search Results", "", "- Query: `%s`" % _clean(query), ""]
        for item in downloaded:
            lines += [
                "## %s" % item.get("title"),
                "",
                "- arXiv: https://arxiv.org/abs/%s" % item.get("arxiv_id"),
                "- PDF: `%s`" % item.get("pdf"),
                "- SHA-256: `%s`" % item.get("sha256"),
                "- Authors: %s" % ", ".join(item.get("authors") or []),
                "- Year: %s" % (item.get("year") or "unknown"),
                "",
                "### Abstract",
                "",
                str(item.get("abstract") or "")[:1600],
                "",
            ]
        for item in skipped:
            lines += ["- Skipped `%s`: %s" % (item.get("arxiv_id"), item.get("reason")), ""]
        (target / "arxiv-sources.md").write_text("\n".join(lines), encoding="utf-8")
        return manifest
