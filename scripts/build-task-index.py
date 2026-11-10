"""Build the workbench task index (data/tasks.json) from pipeline outputs.

Scans research_agent/web/data/demo.json (root run, kept for the README
workflow) plus every research_agent/web/data/tasks/<id>/demo.json produced by
`pipeline run`, and writes a static index the workbench uses for task
switching. Read-only with respect to the pipeline outputs.

Usage:
    python scripts/build-task-index.py
"""

import json
import re
from pathlib import Path

WEB_DATA = Path(__file__).resolve().parents[1] / "research_agent" / "web" / "data"
RUN_STAMP = re.compile(r"PIPE-(\d{8}T\d{6}Z)-")


def describe(demo: dict, dir_rel: str) -> dict:
    paper = demo.get("modules", {}).get("paper") or {}
    profile = paper.get("profile") or {}
    gates = demo.get("gates") or []
    return {
        "id": ("current" if dir_rel == "data" else dir_rel.rstrip("/").rsplit("/", 1)[-1]),
        "dir": dir_rel,
        "topic": demo.get("topic", ""),
        "run_id": demo.get("run_id", ""),
        "status": demo.get("status", ""),
        "fixture_mode": bool(demo.get("fixture_mode", True)),
        "source": demo.get("source", ""),
        "venue": profile.get("venue_type", ""),
        "language": profile.get("language", ""),
        "has_run": bool(demo.get("modules", {}).get("run")),
        "has_grant": bool(demo.get("modules", {}).get("grant")),
        "gates_total": len(gates),
        "gates_attention": sum(
            1 for gate in gates if gate.get("status") in ("blocked", "needs_human")
        ),
        "spec_versions": demo.get("spec_versions", {}),
        "created_at": (
            RUN_STAMP.search(demo.get("run_id", "")).group(1)
            if RUN_STAMP.search(demo.get("run_id", "")) else ""
        ),
    }


def main() -> int:
    tasks = []
    root_demo = WEB_DATA / "demo.json"
    if root_demo.is_file():
        tasks.append(describe(json.loads(root_demo.read_text(encoding="utf-8")), "data"))
    for task_dir in sorted((WEB_DATA / "tasks").glob("*/")):
        demo_path = task_dir / "demo.json"
        if not demo_path.is_file():
            continue
        tasks.append(describe(
            json.loads(demo_path.read_text(encoding="utf-8")),
            "data/tasks/" + task_dir.name,
        ))
    # Runtime jobs (submitted from the workbench "运行" flow) become tasks too:
    # their artifact set is snapshotted into data/tasks/<JOB-id>/ so the static
    # workbench can serve it, closing the loop run → job → task in the rail.
    jobs_root = WEB_DATA.parents[2] / "runtime_data" / "jobs"
    if jobs_root.is_dir():
        import shutil

        for job_dir in sorted(jobs_root.glob("JOB-*")):
            demo_path = job_dir / "demo.json"
            if not demo_path.is_file():
                continue
            snapshot_dir = WEB_DATA / "tasks" / job_dir.name
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            for artifact in ("demo.json", "specs.json", "figure.svg", "figure.manifest.json", "experiment.json", "paper.json", "grant.json"):
                source = job_dir / artifact
                if source.is_file():
                    shutil.copyfile(source, snapshot_dir / artifact)
            run_dir = job_dir / "run"
            if run_dir.is_dir():
                snapshot_run = snapshot_dir / "run"
                snapshot_run.mkdir(exist_ok=True)
                for artifact in run_dir.iterdir():
                    if artifact.is_file():
                        shutil.copyfile(artifact, snapshot_run / artifact.name)
            tasks.append(describe(
                json.loads((snapshot_dir / "demo.json").read_text(encoding="utf-8")),
                "data/tasks/" + job_dir.name,
            ))
    tasks.sort(key=lambda task: task["created_at"], reverse=True)
    index = {
        "schema_version": "tasks-0.1",
        "static": True,
        "note": "任务索引由 scripts/build-task-index.py 从 pipeline 产物生成；浏览器只读。",
        "tasks": tasks,
    }
    out = WEB_DATA / "tasks.json"
    with open(str(out), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("wrote %s (%d tasks)" % (out, len(tasks)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
