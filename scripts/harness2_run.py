"""Run Harness² and emit one contract-checked artifact. Requires Python 3.12+.

This bridge is the only process that imports Harness². The platform side
(`research_agent.rsi_harness2`) never imports it, because the platform runs on
Python 3.8 while Harness² requires >=3.12,<3.14.

Two portability shims are installed *in this process only* and recorded in the
artifact, so nobody mistakes a shimmed run for upstream POSIX behaviour:

* ``fcntl.flock`` -> ``msvcrt.locking`` (the run summary lock);
* ``tree.read_tree`` -> the same function with POSIX relative paths, because
  upstream compares ``str(Path.relative_to(...))`` against slash-separated
  surface patterns, which never matches on Windows.

Nothing else is patched: recursion, budget, selection, prompts and the editable
surface all come from the checkout unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SHIMS = []


def install_fcntl_shim() -> None:
    if os.name != "nt":
        return
    import msvcrt
    import types

    module = types.ModuleType("fcntl")
    module.LOCK_SH = 1
    module.LOCK_EX = 2
    module.LOCK_NB = 4
    module.LOCK_UN = 8

    def flock(handle, operation):
        fd = handle.fileno()
        handle.seek(0)
        if operation & module.LOCK_UN:
            try:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            return
        deadline = time.time() + 30.0
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if operation & module.LOCK_NB or time.time() > deadline:
                    raise
                time.sleep(0.05)

    module.flock = flock
    sys.modules["fcntl"] = module
    SHIMS.append(
        {
            "name": "fcntl.flock",
            "detail": "mapped to msvcrt.locking over one byte of the summary lock file",
        }
    )


def install_tree_path_shim() -> None:
    if os.name != "nt":
        return
    from harness2.core import tree as harness_tree

    original = harness_tree.read_tree

    def read_tree(surface, directory, *, rejected=None):
        directory = Path(directory)
        out = {}
        if not directory.is_dir():
            return out
        stubs = {rel for rel, _ in surface.stubs}
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(directory).as_posix()
            if rel in stubs:
                continue
            if not harness_tree.is_allowed(surface, rel):
                if rejected is not None:
                    rejected.append(rel)
                continue
            out[rel] = path.read_text(encoding="utf-8", errors="replace")
        return out

    harness_tree.read_tree = read_tree
    SHIMS.append(
        {
            "name": "tree.read_tree",
            "detail": "same surface filter, but relative paths are POSIX on every platform; "
            "upstream %s kept" % original.__name__,
        }
    )


# --------------------------------------------------------------------------- #
# Science fixture task pack: claim -> span binding coverage.
# The base harness over-reports coverage because it matches span ids globally
# instead of joining on (claim_id, span_id). That is the defect the recursion
# has to find from probe contrasts alone.
# --------------------------------------------------------------------------- #

BASE_COVERAGE = '''import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
claims = json.loads((root / "claims.json").read_text(encoding="utf-8"))
spans = json.loads((root / "spans.json").read_text(encoding="utf-8"))

known = {span["span_id"] for span in spans}
supported = 0
for claim in claims:
    if any(span_id in known for span_id in claim.get("span_ids", [])):
        supported += 1

answer = {
    "supported": supported,
    "total": len(claims),
    "coverage": round(supported / len(claims), 4),
    "orphan_spans": len(spans) - supported,
}
print(json.dumps(answer, sort_keys=True))
'''

FIXED_COVERAGE = '''import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
claims = json.loads((root / "claims.json").read_text(encoding="utf-8"))
spans = json.loads((root / "spans.json").read_text(encoding="utf-8"))

index = {(span["claim_id"], span["span_id"]): span for span in spans}
supported = 0
used = set()
for claim in claims:
    for span_id in claim.get("span_ids", []):
        span = index.get((claim["claim_id"], span_id))
        if span is None:
            continue
        if 0 <= span["start"] < span["end"] <= len(span["quote"]):
            supported += 1
            used.add((claim["claim_id"], span_id))
            break

answer = {
    "supported": supported,
    "total": len(claims),
    "coverage": round(supported / len(claims), 4),
    "orphan_spans": len(index) - len(used),
}
print(json.dumps(answer, sort_keys=True))
'''


def _claims(rows):
    return [{"claim_id": cid, "text": text, "span_ids": list(sids)} for cid, text, sids in rows]


def _spans(rows):
    return [
        {
            "span_id": sid,
            "claim_id": cid,
            "source_id": src,
            "quote": quote,
            "start": start,
            "end": end,
        }
        for sid, cid, src, quote, start, end in rows
    ]


QUOTE_A = "The retrieval budget bounds how many sources one pass may read."
QUOTE_B = "Coverage is the share of claims whose span resolves inside its own source."
QUOTE_C = "A claim without a resolvable span stays pending and cannot enter the manuscript."
QUOTE_D = "Preregistration freezes the metric before any run starts."

SCIENCE_TASKS = {
    "claims-1": {
        "domain": "claim-audit",
        "prompt": "Join claims.json and spans.json, then write answer.json.",
        "claims": _claims(
            [
                ("c1", "retrieval budget is bounded", ["s1"]),
                ("c2", "coverage counts resolvable spans", ["s2"]),
                ("c3", "pending claims cannot enter the manuscript", ["s1"]),
                ("c4", "preregistration freezes the metric", ["s4"]),
            ]
        ),
        "spans": _spans(
            [
                ("s1", "c1", "p1", QUOTE_A, 4, 31),
                ("s2", "c2", "p1", QUOTE_B, 0, 44),
                ("s4", "c4", "p2", QUOTE_D, 0, 38),
            ]
        ),
    },
    "claims-2": {
        "domain": "claim-audit",
        "prompt": "Join claims.json and spans.json, then write answer.json.",
        "claims": _claims(
            [
                ("c1", "budget bounds one pass", ["s1"]),
                ("c2", "coverage needs a resolvable span", ["s2"]),
                ("c3", "preregistration freezes the metric", ["s3"]),
            ]
        ),
        "spans": _spans(
            [
                ("s1", "c1", "p1", QUOTE_A, 4, 31),
                ("s2", "c2", "p1", QUOTE_B, 0, 70),
                ("s3", "c3", "p2", QUOTE_D, 0, 38),
            ]
        ),
    },
    "claims-3": {
        "domain": "claim-audit",
        "prompt": "Join claims.json and spans.json, then write answer.json.",
        "claims": _claims(
            [
                ("c1", "coverage counts resolvable spans", ["s1"]),
                ("c2", "pending claims stay pending", ["s2"]),
                ("c3", "preregistration freezes the metric", ["s3"]),
            ]
        ),
        "spans": _spans(
            [
                ("s1", "c1", "p1", QUOTE_B, 0, 44),
                ("s2", "c2", "p1", QUOTE_C, 0, 52),
                ("s3", "c3", "p2", QUOTE_D, 0, 38),
            ]
        ),
    },
}

HOLDOUT_TASK = {
    "domain": "claim-audit",
    "prompt": "Join claims.json and spans.json, then write answer.json.",
    "claims": _claims(
        [
            ("c1", "budget bounds one pass", ["s1"]),
            ("c2", "coverage needs a resolvable span", ["s2"]),
            ("c3", "preregistration freezes the metric", ["s3"]),
            ("c4", "pending claims cannot enter the manuscript", ["s4"]),
        ]
    ),
    "spans": _spans(
        [
            ("s1", "c1", "p1", QUOTE_A, 4, 20),
            ("s2", "c2", "p1", QUOTE_B, 0, 44),
            ("s3", "c3", "p2", QUOTE_D, 0, 10),
            ("s4", "c1", "p3", QUOTE_C, 0, 52),
        ]
    ),
}


def expected_answer(task) -> dict:
    """Reference implementation: join on (claim_id, span_id), validate offsets."""
    index = {(span["claim_id"], span["span_id"]): span for span in task["spans"]}
    supported = 0
    used = set()
    for claim in task["claims"]:
        for span_id in claim.get("span_ids", []):
            span = index.get((claim["claim_id"], span_id))
            if span is None:
                continue
            if 0 <= span["start"] < span["end"] <= len(span["quote"]):
                supported += 1
                used.add((claim["claim_id"], span_id))
                break
    return {
        "supported": supported,
        "total": len(task["claims"]),
        "coverage": round(supported / len(task["claims"]), 4),
        "orphan_spans": len(index) - len(used),
    }


def build_science_adapter(root: Path):
    from harness2 import config
    from harness2.core import tree
    from harness2.core.spec import BenchPrompts, BenchSpec, ChannelSpec
    from harness2.substrate.opencode import OpencodeSubstrate

    class ScienceAdapter:
        def __init__(self, root: Path):
            self.root = root
            self.substrate = OpencodeSubstrate()
            channel = ChannelSpec("opencode", "local/deterministic")
            self.spec = BenchSpec(
                name="claims",
                runs_root=root / "runs",
                install_mode="workspace_config",
                prompts=BenchPrompts(
                    work="audit the claim-to-span binding of a frozen literature snapshot"
                ),
                channels={"proposer": channel, "selector": channel},
                leak_globs=("expected.json",),
            )
            self.execution_count = 0
            base = {name: "" for name in self.substrate.surface().always_on}
            base["systemprompt.md"] = (
                "Audit claim-to-span binding. Run python scripts/coverage.py <task-dir>.\n"
            )
            base["scripts/coverage.py"] = BASE_COVERAGE
            tree.write_tree(self.substrate.surface(), base, self.base_harness(), stubs=False)
            for task_id, task in list(SCIENCE_TASKS.items()) + [(HOLDOUT, TASK_HOLDOUT)]:
                folder = self.task_files(task_id)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "claims.json").write_text(
                    json.dumps(task["claims"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                (folder / "spans.json").write_text(
                    json.dumps(task["spans"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )

        def tasks(self, split: str = "all") -> list[str]:
            return list(SCIENCE_TASKS)

        def domain_of(self, task_id: str) -> str:
            return "claim-audit"

        def task_prompt(self, task_id: str) -> str:
            return (
                "Read claims.json and spans.json in the task folder, then write answer.json with "
                "supported, total, coverage (four decimals) and orphan_spans."
            )

        def task_files(self, task_id: str) -> Path:
            return self.root / "sources" / task_id

        def base_harness(self) -> Path:
            return self.root / "base"

        def validate_tree(self, harness: dict) -> None:
            if "scripts/coverage.py" not in harness:
                raise ValueError("The audit executor requires scripts/coverage.py")

        def execute(self, task_id, harness_dir, run_id, *, timeout=None) -> Path:
            self.execution_count += 1
            run_dir = self.root / "executions" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            script = (harness_dir or self.base_harness()) / "scripts" / "coverage.py"
            result = subprocess.run(
                [sys.executable, str(script), str(self.task_files(task_id))],
                capture_output=True,
                text=True,
                timeout=timeout or 30,
                env=config.scrub_env(),
            )
            (run_dir / "answer.json").write_text(result.stdout, encoding="utf-8")
            (run_dir / "trajectory.md").write_text(
                "[ACTION] Run scripts/coverage.py on claims.json + spans.json\n[OBSERVATION]\n"
                + (result.stdout or result.stderr),
                encoding="utf-8",
            )
            if result.returncode != 0:
                raise RuntimeError("coverage.py failed: " + (result.stderr or "")[-400:])
            return run_dir

        def delivered(self, run_dir: Path) -> bool:
            return (run_dir / "answer.json").is_file()

        def trajectory(self, run_dir: Path, *, obs_trunc: int) -> str:
            return (run_dir / "trajectory.md").read_text(encoding="utf-8")

        def deliverable_text(self, run_dir: Path) -> str:
            return (run_dir / "answer.json").read_text(encoding="utf-8")

        def deliverable_files(self, run_dir: Path) -> dict:
            return {"answer.json": self.deliverable_text(run_dir)}

        def score(self, run_dir: Path, task_id: str) -> dict | None:
            task = SCIENCE_TASKS.get(task_id) or HOLDOUT_TASK
            try:
                produced = json.loads(self.deliverable_text(run_dir))
            except ValueError:
                return None
            return {"match": produced == expected_answer(task), "answer": produced}

    return ScienceAdapter(root)


HOLDOUT = "claims-holdout"
TASK_HOLDOUT = HOLDOUT_TASK


def build_demo_adapter(root: Path):
    from harness2.demo import DemoAdapter

    return DemoAdapter(root)


class ScienceProposer:
    """Scripted editor and selector: the fixture counterpart of DemoProposer."""

    def __init__(self, spec):
        self.spec = spec
        self._calls = []

    def call(self, mission, context_dir, label, **kwargs):
        from harness2.core.proposer import Reply

        context = Path(context_dir)
        workspace = None
        if label.startswith("select."):
            expected = self._expected_from_source(context / "source")
            candidates = sorted((context / "candidates").glob("*.md"))
            chosen = None
            for path in candidates:
                body = path.read_text(encoding="utf-8")
                try:
                    payload = json.loads(body.split("-->", 1)[-1].strip())
                except ValueError:
                    continue
                if payload == expected:
                    chosen = path.stem
                    break
            if chosen is None:
                raise RuntimeError("no candidate answer matched the reference join")
            text = (
                "<why>The claim-to-span join resolves inside each claim's own source.</why>\n"
                "```choice\n%s\n```" % chosen
            )
        elif label.startswith("experience."):
            harness = context / "harness" / "scripts" / "coverage.py"
            base = context / "base_harness" / "scripts" / "coverage.py"
            changed = harness.read_text(encoding="utf-8") != base.read_text(encoding="utf-8")
            text = (
                "<edits>\ncomponent: scripts/coverage.py\ncandidates: inv1, dom1\n"
                "change: joined span ids on (claim_id, span_id) and validated the offsets\n"
                "observed: probes that only matched span ids globally counted a foreign span as "
                "support\nverdict: %s\n</edits>\n\n" % ("helped" if changed else "no observed effect")
            ) + (
                "<experience>\ncue: When a claim cites a span that belongs to another claim\n"
                "lesson: Join claim and span on the pair, never on the span id alone; then require "
                "0 <= start < end <= len(quote).\n"
                "evidence: The scripts/coverage.py row -- removing the global membership test "
                "lowered the reported coverage from 1.0 to the reference value on claims-1.\n"
                "confidence: high for this observed join contrast\n</experience>"
                if changed
                else "NO_ENTRY"
            )
        else:
            workspace = context / "harness"
            script = workspace / "scripts" / "coverage.py"
            script.write_text(FIXED_COVERAGE, encoding="utf-8")
            text = (
                "<notes>The base script matched span ids in a global set, so a claim inherited "
                "another claim's span. Join on (claim_id, span_id) and check the offsets.</notes>"
            )
        reply = Reply(label=label, text=text, ok=True, attempts=1, workspace=workspace)
        self._calls.append(reply)
        return reply

    @staticmethod
    def _expected_from_source(source: Path):
        task = {
            "claims": json.loads((source / "claims.json").read_text(encoding="utf-8")),
            "spans": json.loads((source / "spans.json").read_text(encoding="utf-8")),
        }
        return expected_answer(task)


def _tree_hash(tree: dict) -> str:
    payload = json.dumps(tree, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _unified_diff(base: dict, adopted: dict, limit: int = 6000) -> str:
    import difflib

    chunks = []
    for path in sorted(set(base) | set(adopted)):
        before = base.get(path, "")
        after = adopted.get(path, "")
        if before == after:
            continue
        diff = difflib.unified_diff(
            before.splitlines(True),
            after.splitlines(True),
            fromfile="a/" + path,
            tofile="b/" + path,
            n=2,
        )
        chunks.append("".join(diff))
    return ("\n".join(chunks))[:limit]


def _component_map(root: Path, surface) -> dict:
    from harness2.core import tree as harness_tree

    tree = harness_tree.read_tree(surface, root)
    counts = {
        "systemprompt.md": 0,
        "guardrails.md": 0,
        "LongTermMEMORY.md": 0,
        "tool_descriptions/tool_guidance.md": 0,
        "sub_agents": 0,
        "skills": 0,
        "scripts": 0,
        "plugin": 0,
    }
    for rel in tree:
        if rel in counts:
            counts[rel] += 1
        elif rel.startswith("sub_agents/"):
            counts["sub_agents"] += 1
        elif rel.startswith("skills/"):
            counts["skills"] += 1
        elif rel.startswith("scripts/"):
            counts["scripts"] += 1
        elif rel.startswith("plugin/"):
            counts["plugin"] += 1
    labels = {
        "systemprompt.md": "c1 system prompt",
        "guardrails.md": "c2 guardrails",
        "LongTermMEMORY.md": "c3 memory",
        "tool_descriptions/tool_guidance.md": "c4 tool guidance",
        "sub_agents": "c5 subagents",
        "skills": "c6 skills",
        "scripts": "c7 scripts",
        "plugin": "c8 plugins",
    }
    return {labels[key]: count for key, count in counts.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness2-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--mode", choices=("parallel", "sequential", "both"), default="both")
    parser.add_argument("--adapter", choices=("demo", "science"), default="science")
    args = parser.parse_args(argv)

    root = Path(args.harness2_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root))

    install_fcntl_shim()
    install_tree_path_shim()

    from harness2 import config
    from harness2.core import schedule
    from harness2.core import tree as harness_tree

    started = time.time()
    work = output / args.adapter
    if args.adapter == "demo":
        adapter = build_demo_adapter(work)
        from harness2.demo import DemoProposer

        proposer = DemoProposer(adapter.spec.channels["proposer"])
        executor = "deterministic-demo"
    else:
        adapter = build_science_adapter(work)
        proposer = ScienceProposer(adapter.spec.channels["proposer"])
        executor = "deterministic-science-fixture"

    modes = ("agg", "seq") if args.mode == "both" else (schedule.mode_token(args.mode),)
    task_ids = adapter.tasks()
    domain = adapter.domain_of(task_ids[0])
    result = schedule.run_domain(
        domain,
        task_ids,
        args.k,
        adapter=adapter,
        prop=proposer,
        runs_root=adapter.spec.runs_root,
        library_root=work / "library" / ("k%d" % args.k),
        modes=modes,
    )

    surface = adapter.substrate.surface()
    base_tree = harness_tree.read_tree(surface, adapter.base_harness())
    namespace_by_mode = {
        mode: "%s-oc-%s%d" % (adapter.spec.name, mode, args.k) for mode in modes
    }

    tasks_out = []
    adopted = []
    budget = {"R": 0, "expected_R": 0, "P": 0, "expected_P": 0, "usd": 0.0}
    fallbacks = []
    selections = {}
    notes_by_label = {}
    # Harness² always writes one task summary under the base (agg) namespace, with every
    # requested mode recorded inside `modes`; the per-mode namespaces only hold work dirs.
    summary_ns = "%s-oc-agg%d" % (adapter.spec.name, args.k)

    for task_id in task_ids:
        entry = {
            "task_id": task_id,
            "domain": adapter.domain_of(task_id),
            "status": "ok",
            "modes": {},
        }
        for mode in modes:
            summary_path = adapter.spec.runs_root / summary_ns / task_id / "summary.json"
            if not summary_path.is_file():
                entry["status"] = "failed"
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            record = (summary.get("modes") or {}).get(mode) or {}
            entry["modes"][mode] = {
                "ok": bool(record.get("ok")),
                "finals": record.get("finals") or [],
                "fell_back": record.get("fell_back") or [],
            }
            if not record.get("ok"):
                entry["status"] = "partial"
            for label in record.get("fell_back") or []:
                fallbacks.append("%s/%s/%s" % (task_id, mode, label))
            ledger = record.get("ledger") or {}
            for key in ("R", "expected_R", "P", "expected_P"):
                budget[key] += int(ledger.get(key, 0) or 0)
            budget["usd"] = round(budget["usd"] + float(ledger.get("usd", 0) or 0), 6)

            selection = (summary.get("selections") or {}).get(mode) or {}
            if selection:
                selections["%s/%s" % (task_id, mode)] = {
                    "chosen_label": selection.get("chosen_label", ""),
                    "chosen_is_base": bool(selection.get("chosen_is_base")),
                    "why": str(selection.get("why", ""))[:400],
                    "n_candidates": selection.get("n_candidates", 0),
                    "fallback": bool(selection.get("fallback")),
                }
            for stage in record.get("stages") or []:
                label = stage.get("label", "")
                if stage.get("notes"):
                    notes_by_label[label] = str(stage["notes"])[:600]

            adopted_label = selection.get("chosen_label") or ""
            if not adopted_label or selection.get("chosen_is_base"):
                continue
            harness_dir = (
                adapter.spec.runs_root
                / namespace_by_mode[mode]
                / task_id
                / "harnesses"
                / adopted_label
            )
            adopted_tree = harness_tree.read_tree(surface, harness_dir)
            if not adopted_tree:
                continue
            changes = []
            for path in sorted(set(base_tree) | set(adopted_tree)):
                if base_tree.get(path) == adopted_tree.get(path):
                    continue
                diff = _unified_diff({path: base_tree.get(path, "")}, {path: adopted_tree.get(path, "")})
                changes.append({"path": path, "diff": diff})
            lesson = ""
            experience = selection.get("experience") or {}
            if isinstance(experience, dict):
                lesson = str(experience.get("lesson", ""))
            adopted.append(
                {
                    "task_id": task_id,
                    "mode": mode,
                    "label": adopted_label,
                    "base_sha256": _tree_hash(base_tree),
                    "adopted_sha256": _tree_hash(adopted_tree),
                    "notes": notes_by_label.get(adopted_label, ""),
                    "lesson": lesson,
                    "changes": changes,
                }
            )
        tasks_out.append(entry)

    # Held-out check: a task the proposer never saw, executed with the adopted harness.
    held_out = {"n": 0, "passed": 0, "base_passed": 0, "delta": 0}
    holdout_task = HOLDOUT if args.adapter == "science" else None
    if holdout_task and adopted:
        first = adopted[0]
        harness_dir = (
            adapter.spec.runs_root
            / namespace_by_mode[first["mode"]]
            / first["task_id"]
            / "harnesses"
            / first["label"]
        )
        expected = expected_answer(TASK_HOLDOUT)
        try:
            base_run = adapter.execute(holdout_task, adapter.base_harness(), "holdout-base")
            base_ok = json.loads(adapter.deliverable_text(base_run)) == expected
        except Exception:
            base_ok = False
        try:
            adopted_run = adapter.execute(holdout_task, harness_dir, "holdout-adopted")
            adopted_ok = json.loads(adapter.deliverable_text(adopted_run)) == expected
        except Exception:
            adopted_ok = False
        held_out = {
            "n": 1,
            "passed": 1 if adopted_ok else 0,
            "base_passed": 1 if base_ok else 0,
            "delta": (1 if adopted_ok else 0) - (1 if base_ok else 0),
            "artifact_ref": str(work / "executions" / "holdout-adopted"),
        }

    pack = {
        "adapter": args.adapter,
        "tasks": {
            key: {
                "domain": value["domain"],
                "claims": value["claims"],
                "spans": value["spans"],
            }
            for key, value in SCIENCE_TASKS.items()
        },
        "holdout": HOLDOUT_TASK,
        "reference": "join on (claim_id, span_id); require 0 <= start < end <= len(quote)",
    }
    pack_bytes = json.dumps(pack, sort_keys=True, ensure_ascii=False).encode("utf-8")
    (output / "task-pack.json").write_bytes(pack_bytes)

    lessons = []
    for item in adopted:
        if not item.get("lesson"):
            continue
        lessons.append(
            {
                "task_id": item["task_id"],
                "mode": item["mode"],
                "lesson": item["lesson"],
                "evidence": "scripts/coverage.py contrast on %s" % item["task_id"],
                "confidence": "high for the observed join contrast",
            }
        )

    finished = time.time()
    artifact = {
        "schema": "harness2-run-0.1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "harness2": {
            "root": str(root),
            "method_version": int(getattr(config, "METHOD_VERSION", 0)),
            "package_version": "0.1.0",
            "python": "%d.%d.%d" % sys.version_info[:3],
        },
        "run": {
            "adapter": args.adapter,
            "executor": executor,
            "platform": os.name,
            "k": args.k,
            "modes": list(modes),
            "exit_code": 0 if result.get("failed", 0) == 0 else 1,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
            "wall_s": round(finished - started, 3),
            "executions": int(getattr(adapter, "execution_count", 0)),
            "editor_calls": len(getattr(proposer, "_calls", [])),
        },
        "tasks": tasks_out,
        "budget": budget,
        "fallbacks": fallbacks,
        "selections": selections,
        "adopted": adopted,
        "held_out": held_out,
        "lessons": lessons,
        "surface": {"components": _component_map(adapter.base_harness(), surface)},
        "shims": SHIMS,
        "classification": {
            "simulation": True,
            "claim_eligible": False,
            "why": "deterministic executor and scripted proposer: this measures the seam, "
            "not a scientific capability gain",
        },
        "task_pack_sha256": hashlib.sha256(pack_bytes).hexdigest(),
    }

    target = output / "harness2-run.json"
    target.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "harness2 bridge: adapter=%s k=%d modes=%s tasks=%d/%d R=%d P=%d adopted=%d -> %s"
        % (
            args.adapter,
            args.k,
            ",".join(modes),
            result.get("done", 0),
            result.get("n_tasks", 0),
            budget["R"],
            budget["P"],
            len(adopted),
            target,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
