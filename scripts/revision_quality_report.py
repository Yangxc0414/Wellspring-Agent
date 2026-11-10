"""Summarize revision quality from an existing revision-audit.json."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.revision import extract_citations, protected_numbers
from research_agent.storage import write_json_atomic


def summarize(audit_path: Path) -> dict:
    audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    rewrite = audit.get("rewrite") or {}
    records = list(rewrite.get("records") or [])
    counts = {"accepted": 0, "unchanged": 0, "rejected": 0}
    accepted = []
    citation_ok = 0
    number_ok = 0
    ratios = []
    for item in records:
        status = str(item.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
        original = str(item.get("original_text") or "")
        revised = str(item.get("revised_text") or "")
        citations_same = set(extract_citations(original)) == set(extract_citations(revised))
        numbers_same = set(protected_numbers(original)) == set(protected_numbers(revised))
        ratio = round(len(revised) / max(1, len(original)), 3)
        ratios.append(ratio)
        if citations_same:
            citation_ok += 1
        if numbers_same:
            number_ok += 1
        if status == "accepted":
            accepted.append(
                {
                    "section": item.get("section"),
                    "block_index": item.get("block_index"),
                    "length_ratio": ratio,
                    "citations_preserved": citations_same,
                    "numbers_preserved": numbers_same,
                    "change_summary": item.get("change_summary") or [],
                }
            )
    return {
        "schema_version": "revision-quality-0.1",
        "audit": str(audit_path),
        "status": audit.get("status"),
        "writer_mode": audit.get("writer_mode"),
        "submission_ready": audit.get("submission_ready"),
        "records": len(records),
        "counts": counts,
        "accepted_rate": round(counts.get("accepted", 0) / max(1, len(records)), 3),
        "citation_preserved_records": citation_ok,
        "number_preserved_records": number_ok,
        "average_length_ratio": round(sum(ratios) / max(1, len(ratios)), 3),
        "accepted_changes": accepted,
        "blockers": audit.get("blockers") or [],
        "warnings": (audit.get("warnings") or [])[:40],
        "boundary": (
            "Deterministic revision-quality summary: citation/number preservation and accepted-block "
            "counts. It is not a semantic or peer-review judgment."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = summarize(Path(args.audit))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output.with_suffix(".json"), result)
    lines = [
        "# Revision Quality",
        "",
        "- audit: `%s`" % result["audit"],
        "- status: `%s`; writer_mode: `%s`; submission_ready: %s"
        % (result["status"], result["writer_mode"], result["submission_ready"]),
        "- records: %d; accepted=%d, unchanged=%d, rejected=%d"
        % (
            result["records"],
            result["counts"].get("accepted", 0),
            result["counts"].get("unchanged", 0),
            result["counts"].get("rejected", 0),
        ),
        "- accepted rate: %.1f%%" % (result["accepted_rate"] * 100),
        "- citation preserved records: %d / %d" % (result["citation_preserved_records"], result["records"]),
        "- number preserved records: %d / %d" % (result["number_preserved_records"], result["records"]),
        "- average length ratio: %.2f" % result["average_length_ratio"],
        "",
        "## Accepted changes",
        "",
    ]
    for item in result["accepted_changes"]:
        lines.append(
            "- `%s` block %s (ratio %.2f): %s"
            % (item["section"], item["block_index"], item["length_ratio"], "; ".join(item["change_summary"]))
        )
    lines += ["", "## Blockers", ""]
    for item in result["blockers"]:
        lines.append("- " + item)
    lines += ["", result["boundary"], ""]
    output.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": result["status"], "summary": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
