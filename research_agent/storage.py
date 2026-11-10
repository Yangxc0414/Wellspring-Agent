"""Small shared primitives for local JSON stores.

The stores in this repository are intentionally local and file-based. This
module keeps the one piece that must not be reimplemented four times: atomic
replacement of a JSON file. It is not a database and does not provide
cross-process transactions.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class JsonStoreError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Optional[Any]:
    """Return None when the file does not exist; raise on invalid JSON/IO."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        with open(str(path), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise JsonStoreError("cannot read %s: %s" % (path, exc))


def atomic_replace(tmp: Path, path: Path, attempts: int = 10) -> None:
    """Replace with short retries for Windows sharing violations."""
    last_error: Optional[OSError] = None
    for attempt in range(max(1, attempts)):
        try:
            os.replace(str(tmp), str(path))
            return
        except PermissionError as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(0.02 * (attempt + 1))
    if last_error is not None:
        raise last_error


def write_json_atomic(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(str(tmp), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    atomic_replace(tmp, path)
