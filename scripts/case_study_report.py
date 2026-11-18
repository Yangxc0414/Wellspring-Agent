"""Case-study report over the durable failure atlas (read-only).

The atlas records what failed; this report adds the coding a case study needs: how each
defect was detected, what the repair looked like, and whether a regression test guards it.
Codings are human-authored data (research_agent/eval/case_study_codings.json); the script
only validates and aggregates them, so the numbers are reproducible but not self-graded.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ATLAS = ROOT / "research_agent" / "failures" / "atlas.json"
CODINGS = ROOT / "research_agent" / "eval" / "case_study_codings.json"
DETECTION = ("real_model_run", "heldout_rubric", "browser_check", "contract_test")
FIX_TYPES = ("code", "code_and_test", "config", "docs")
REGRESSION = ("yes", "no")


class CaseStudyError(ValueError):
    pass


def load_codings(atlas_path=ATLAS, codings_path=CODINGS):
    atlas = json.loads(Path(atlas_path).read_text(encoding="utf-8"))
    codings = json.loads(Path(codings_path).read_text(encoding="utf-8"))
    if str(codings.get("schema") or "") != "case-study-codings-0.1":
        raise CaseStudyError("codings schema must be case-study-codings-0.1")
    protocol = codings.get("protocol") or {}
    for field in ("research_questions", "case_selection", "data_sources", "ethics"):
        if not protocol.get(field):
            raise CaseStudyError("protocol needs " + field)
    atlas_ids = [str(entry["failure_id"]) for entry in atlas.get("entries") or []]
    cases = codings.get("cases") or []
    coded_ids = [str(case.get("failure_id") or "") for case in cases]
    missing = [item for item in atlas_ids if item not in coded_ids]
    if missing:
        raise CaseStudyError("uncoded failures: " + ", ".join(missing))
    unknown = [item for item in coded_ids if item not in atlas_ids]
    if unknown:
        raise CaseStudyError("codings for unknown failures: " + ", ".join(unknown))
    duplicated = [item for item in set(coded_ids) if coded_ids.count(item) > 1]
    if duplicated:
        raise CaseStudyError("duplicate codings: " + ", ".join(duplicated))
    for case in cases:
        if case.get("detection_mechanism") not in DETECTION:
            raise CaseStudyError("bad detection_mechanism: " + str(case.get("failure_id")))
        if case.get("fix_type") not in FIX_TYPES:
            raise CaseStudyError("bad fix_type: " + str(case.get("failure_id")))
        if case.get("regression_test") not in REGRESSION:
            raise CaseStudyError("bad regression_test: " + str(case.get("failure_id")))
    return atlas, codings


def _counts(values):
    out = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def summarise(atlas, codings):
    cases = codings["cases"]
    total = len(cases)
    return {
        "schema": "case-study-report-0.1",
        "study_id": codings.get("study_id"),
        "title": codings.get("title"),
        "n": total,
        "detection": _counts([case["detection_mechanism"] for case in cases]),
        "fix_type": _counts([case["fix_type"] for case in cases]),
        "regression_test": _counts([case["regression_test"] for case in cases]),
        "stage": _counts([str(case.get("stage")) for case in cases]),
        "regression_rate": round(
            sum(1 for case in cases if case["regression_test"] == "yes") / float(total), 3
        ),
        "cases": [
            {
                "failure_id": case["failure_id"],
                "stage": case.get("stage"),
                "detection_mechanism": case["detection_mechanism"],
                "fix_type": case["fix_type"],
                "regression_test": case["regression_test"],
                "repair": case.get("repair"),
            }
            for case in cases
        ],
        "boundary": (
            "single-project, single-author case study with six purposively sampled durable "
            "failures; counts are descriptive, not population estimates"
        ),
    }


def render_markdown(report):
    lines = [
        "# Case study: " + str(report.get("title")),
        "",
        "- study: " + str(report.get("study_id")),
        "- cases: " + str(report["n"]),
        "",
        "## RQ1 classes (defect kinds)",
        "",
        "- all six are design_flaw (the atlas only records durable failures)",
        "",
        "## RQ2 detection mechanism",
        "",
    ]
    for key, value in report["detection"].items():
        lines.append("- {0}: {1}".format(key, value))
    lines.extend(["", "## RQ3 repair", ""])
    for key, value in report["fix_type"].items():
        lines.append("- fix_type {0}: {1}".format(key, value))
    lines.append("- regression test added: {0}/{1} ({2})".format(
        report["regression_test"].get("yes", 0), report["n"], report["regression_rate"]))
    lines.extend(["", "## Cases", "", "| id | stage | detected by | fix | test |", "| --- | --- | --- | --- | --- |"])
    for case in report["cases"]:
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            case["failure_id"], case["stage"], case["detection_mechanism"],
            case["fix_type"], case["regression_test"]))
    lines.extend(["", "> " + report["boundary"]])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="case-study report over durable failures")
    parser.add_argument("--atlas", default=str(ATLAS))
    parser.add_argument("--codings", default=str(CODINGS))
    parser.add_argument("--out", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        atlas, codings = load_codings(args.atlas, args.codings)
    except CaseStudyError as exc:
        print(str(exc))
        return 2
    report = summarise(atlas, codings)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix.lower() == ".json":
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
        else:
            out.write_text(render_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
