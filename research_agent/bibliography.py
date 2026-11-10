"""S13 bibliography metadata verification from a frozen DOI snapshot."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class BibliographyError(RuntimeError):
    pass


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


class BibliographyAgent:
    def verify(self, source_path: Path, output_dir: Path) -> Dict[str, Any]:
        data = json.loads(Path(source_path).read_text(encoding="utf-8"))
        if data.get("verification_source") != "datacite_api_snapshot":
            raise BibliographyError("only frozen datacite_api_snapshot metadata is accepted")
        entries: List[Dict[str, Any]] = list(data.get("entries") or [])
        if len(entries) < 2:
            raise BibliographyError("bibliography needs at least two entries")
        seen = set()
        for entry in entries:
            doi = str(entry.get("doi", "")).lower()
            if not doi.startswith("10.48550/") or doi in seen:
                raise BibliographyError("each entry needs a unique 10.48550 DOI")
            seen.add(doi)
            if not entry.get("title") or not entry.get("authors") or not entry.get("year"):
                raise BibliographyError("entry needs title/authors/year: " + doi)
            if not str(entry.get("url", "")).startswith("https://"):
                raise BibliographyError("entry needs an https URL: " + doi)
            if len(str(entry.get("response_sha256", ""))) != 64:
                raise BibliographyError("entry needs a 64-char response hash: " + doi)
        card = {
            "card_id": "BIB-" + uuid.uuid4().hex[:10],
            "status": "verified_datacite_snapshot",
            "verification_source": "datacite_api_snapshot",
            "verified_at": str(data.get("verified_at", "")),
            "entry_count": len(entries),
            "entries": entries,
            "card_sha256": hashlib.sha256(
                json.dumps(entries, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "warnings": [
                "metadata verification only; not peer review",
                "frozen DOI snapshot; no live re-query",
            ],
        }
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "bibliography-card.json"
        _write_json(path, card)
        return {"bibliography": card, "path": str(path)}
