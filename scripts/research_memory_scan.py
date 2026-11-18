"""Build a typed research-memory graph over a project's artifacts (read-only).

This is the memory instrument the design asks for: it ingests the artifacts a project
already produced (ideas, designs, claims, closures, audit findings), admits what may be
used for generation, marks what went stale, and emits a budgeted pack per stage.

It creates nothing on the gate path: no Claim / EA / Verdict / Signature, no writes to
project artifacts. Output goes to <project>/memory/ or --out.

Usage:
    python scripts/research_memory_scan.py --project runtime_data/e2e-closed-loop
    python scripts/research_memory_scan.py --project runtime_data/e2e-closed-loop --stage idea
    python scripts/research_memory_scan.py --project P --out D --budget 6000 --json
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from prototypes.ese.memory_graph import (  # noqa: E402
    MemoryGraph,
    build_pack,
    default_artifact_files,
    ingest_project,
    sha256_file,
)


def _write(path, payload):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _write_text(path, text):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="typed research memory scan (read-only)")
    parser.add_argument("--project", required=True, help="project directory containing runs/")
    parser.add_argument("--out", default="", help="output directory (default: <project>/memory)")
    parser.add_argument("--stage", action="append", default=[], choices=["idea", "experiment", "paper"])
    parser.add_argument("--budget", type=int, default=8000)
    parser.add_argument("--focus", default="", help="node id to prioritise in packs")
    parser.add_argument(
        "--failures",
        default="",
        help="durable failure atlas JSON (default: research_agent/failures/atlas.json when present)",
    )
    parser.add_argument("--json", action="store_true", help="print the graph summary as JSON")
    args = parser.parse_args(argv)

    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print("project not found: {0}".format(project))
        return 2

    files = default_artifact_files(project)
    if not files:
        print("no recognized artifacts under {0}/runs".format(project))
        return 2

    atlas_path = args.failures
    if not atlas_path:
        candidate = os.path.join(ROOT, "research_agent", "failures", "atlas.json")
        atlas_path = candidate if os.path.isfile(candidate) else ""
    graph = ingest_project(project, files, failure_atlas=atlas_path or None)
    out_dir = args.out or os.path.join(project, "memory")
    _write(os.path.join(out_dir, "memory-graph.json"), graph.to_dict())

    stages = args.stage or ["idea", "experiment", "paper"]
    packs = {}
    for stage in stages:
        pack = build_pack(graph, stage, budget=args.budget, focus=args.focus or None)
        _write(os.path.join(out_dir, "memory-pack-{0}.json".format(stage)), pack.to_dict())
        _write_text(os.path.join(out_dir, "memory-pack-{0}.md".format(stage)), pack.render())
        packs[stage] = {
            "chars": pack.total_chars,
            "stale": pack.stale_excluded,
            "pending": pack.pending_excluded,
            "sections": {s.name: len(s.lines) for s in pack.sections},
            "dropped": {s.name: s.dropped for s in pack.sections if s.dropped},
        }

    summary = {
        "project": project,
        "failure_atlas": atlas_path,
        "artifacts": len(files),
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "counts": graph.counts(),
        "packs": packs,
        "out": out_dir,
        "boundary": (
            "read-only projection over existing artifacts; the pack is generation context, "
            "not evidence; no gate reads it"
        ),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("project: {0}".format(project))
        print("artifacts: {0} | nodes: {1} | edges: {2}".format(len(files), len(graph.nodes), len(graph.edges)))
        print("failure atlas: {0}".format(atlas_path or "(none)"))
        for key in sorted(graph.counts()):
            print("  {0}: {1}".format(key, graph.counts()[key]))
        for stage in stages:
            info = packs[stage]
            print(
                "pack[{0}]: {1}/{2} chars | stale={3} pending={4} | sections={5}".format(
                    stage,
                    info["chars"],
                    args.budget,
                    info["stale"],
                    info["pending"],
                    ", ".join("{0}:{1}".format(k, v) for k, v in sorted(info["sections"].items()) if v),
                )
            )
        print("out: {0}".format(out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
