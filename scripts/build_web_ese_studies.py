"""Build the workbench's ESE study detail JSON from runtime_data.

Same source as demo/ese-ms-03: result.json plus the five on-disk chain
artifacts. The workbench shows it inline; the demo page shows the long form.
Neither page may claim a step that is not on disk.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import build_ese_study_page as page  # noqa: E402

SCHEMA = "runtime-ese-studies-0.1"
BOUNDARY = (
    "read-only local projection of ESE studies; chain state reflects files on disk; "
    "no Claim/EA/signature is created or changed here"
)


def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _public_repo(repo):
    return {
        key: repo.get(key)
        for key in ("repo", "head", "commits", "test_cochange", "rate", "ci")
    }


def _public_stratum(item):
    return {
        "factor": item.get("factor"),
        "value": item.get("value"),
        "bug": item.get("bug") or {},
        "other": item.get("other") or {},
        "difference": item.get("difference"),
        "degenerate": bool(item.get("degenerate")),
    }


def build(scan_root):
    base = Path(scan_root)
    studies = []
    if not base.is_dir():
        return {"schema": SCHEMA, "count": 0, "studies": [], "boundary": BOUNDARY}

    for directory in sorted(base.iterdir()):
        if not directory.is_dir():
            continue
        result_path = directory / "result.json"
        if not result_path.is_file():
            continue
        result = _read(result_path)
        if result is None:
            continue
        steps, state, _badge = page.chain_state(directory, result)
        studies.append({
            "study_id": str(result.get("study_id") or directory.name),
            "directory": directory.name,
            "method": str(result.get("method") or ""),
            "questions": [str(item) for item in (result.get("research_questions") or [])],
            "protocol_sha256": str(result.get("protocol_sha256") or ""),
            "repos": [_public_repo(item) for item in (result.get("repos") or [])],
            "pooled": result.get("pooled") or {},
            "strata": [
                _public_stratum(item)
                for item in ((result.get("stratified") or {}).get("strata") or [])
            ],
            "time_split": result.get("time_split") or {},
            "boundary": str(result.get("boundary") or ""),
            "chain": steps,
            "state": state,
        })

    # Studies with real repository-mining detail come first; the M1/M2 feedback
    # studies have no result.json repos and would otherwise open as an empty panel.
    studies.sort(
        key=lambda item: (len(item.get("repos") or []) > 0, item.get("study_id") or ""),
        reverse=True,
    )
    return {
        "schema": SCHEMA,
        "count": len(studies),
        "studies": studies,
        "boundary": BOUNDARY,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="build apps/web/public/ese-studies.json")
    parser.add_argument("--scan-root", default="runtime_data")
    parser.add_argument("--out", default="apps/web/public/ese-studies.json")
    args = parser.parse_args(argv)

    payload = build(args.scan_root)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("ese studies: {0} study(ies) -> {1}".format(payload["count"], out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
