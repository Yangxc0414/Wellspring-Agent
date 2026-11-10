"""Read-only live retriever against the public OpenAlex API.

This is the first networked adapter in the repo and it is deliberately
narrow (registered in modules/literature/SPEC.md v0.2.0):

- only ``GET https://api.openalex.org/works`` (search + per-page + mailto);
- no API key required, but ``OPENALEX_API_KEY`` is supported: a free key
  avoids the shared per-IP daily quota and is sent as a Bearer header
  (never in the URL or output); ``mailto`` (env ``OPENALEX_EMAIL``) opts
  into the polite pool;
- client-side throttle (>= min_interval between requests), bounded retries
  with backoff on 429/5xx/network errors, explicit ``OpenAlexError`` when
  retries are exhausted -- a network failure is never silently swallowed;
- abstracts are rebuilt from ``abstract_inverted_index`` and stay
  ``SourceHit`` clues only: ``full_text`` is always False and
  ``full_text()`` always returns None. OA links are exposed on the hit for
  a human to fetch the full text; without it S1 records a
  ``full_text_unavailable`` gap and generates no span.

A ``transport`` callable (``urllib.request.Request -> bytes``) can be
injected for offline tests.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from ..contracts import SourceHit

BASE_URL = "https://api.openalex.org/works"


class OpenAlexError(RuntimeError):
    pass


def _default_transport(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=request.timeout) as response:
        return response.read()


def _rebuild_abstract(inverted: Optional[Dict[str, List[int]]], cap: int = 1600) -> str:
    if not inverted:
        return ""
    positions: List[tuple] = []
    for word, offsets in inverted.items():
        for offset in offsets or []:
            positions.append((int(offset), word))
    positions.sort()
    text = " ".join(word for _, word in positions)
    return text[:cap]


class OpenAlexRetriever:
    fixture_mode = False
    live_api = "openalex"

    def __init__(
        self,
        mailto: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 2,
        min_interval: float = 0.12,
        transport: Optional[Callable[[urllib.request.Request], bytes]] = None,
        api_key: Optional[str] = None,
    ):
        import os

        self.mailto = (mailto or os.environ.get("OPENALEX_EMAIL", "")).strip()
        self.api_key = (api_key or os.environ.get("OPENALEX_API_KEY", "")).strip()
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.min_interval = max(0.0, min_interval)
        self._transport = transport or _default_transport
        self._last_request = 0.0

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        wait = self._last_request + self.min_interval - now
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = dict(params)
        if self.mailto:
            query["mailto"] = self.mailto
        url = BASE_URL + "?" + urllib.parse.urlencode(query)
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            request = urllib.request.Request(
                url,
                method="GET",
                headers={
                    "User-Agent": "research-agent-workbench/0.1 (openalex adapter)"
                    + ("; mailto: " + self.mailto if self.mailto else ""),
                    "Accept": "application/json",
                },
            )
            if self.api_key:
                request.add_header("Authorization", "Bearer " + self.api_key)
            request.timeout = self.timeout
            try:
                payload = self._transport(request)
                return json.loads(payload.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 429 or exc.code >= 500:
                    if attempt < self.max_retries:
                        time.sleep(0.6 * (attempt + 1))
                        continue
                break
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                break
        detail = type(last_error).__name__
        if isinstance(last_error, urllib.error.HTTPError):
            detail = "HTTP %s" % last_error.code
            if last_error.code == 429:
                detail += (
                    "; shared free quota may be exhausted - set OPENALEX_API_KEY (free key) "
                    "and/or OPENALEX_EMAIL for the polite pool, or retry later"
                )
        raise OpenAlexError("openalex request failed after retries: %s" % detail)

    def search(self, query: str, limit: int) -> List[SourceHit]:
        text = (query or "").strip()
        if not text:
            return []
        data = self._get({"search": text, "per-page": str(max(1, min(int(limit), 50)))})
        hits: List[SourceHit] = []
        for work in data.get("results", []) or []:
            source_id = "OA:" + str(work.get("id", "")).rsplit("/", 1)[-1]
            if not source_id or source_id == "OA:":
                continue
            location = work.get("primary_location") or {}
            source = location.get("source") or {}
            open_access = work.get("open_access") or {}
            license_value = str(location.get("license") or open_access.get("oa_status") or "unknown")
            hits.append(SourceHit(
                source_id=source_id,
                title=str(work.get("display_name") or "(untitled)"),
                year=work.get("publication_year"),
                venue=str(source.get("display_name") or "unknown venue"),
                doi=work.get("doi"),
                abstract=_rebuild_abstract(work.get("abstract_inverted_index")),
                full_text=False,
                license=license_value,
                fixture=False,
                url=open_access.get("oa_url") or work.get("doi") or None,
            ))
        return hits

    def full_text(self, source_id: str) -> Optional[Dict[str, Any]]:
        # Abstracts are clues only; full texts are fetched by a human via the
        # OA link on the hit (S1 invariant: no full text, no span).
        return None
