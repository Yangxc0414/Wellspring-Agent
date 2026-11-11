"""Harness² seam: run the upstream recursion, ingest it under governance.

This module does not re-implement recursive harness improvement. It locates the
Harness² checkout, runs its ``run_domain`` through a Python 3.12 bridge process,
validates the emitted artifact against a frozen contract, and maps the result
onto this project's ``Candidate`` / ``EvalEvidence`` types.

Two boundaries stay fixed:

* the platform owns admission, the ledger and the data foundation;
* Harness² owns propose-probe-compose and the c1..c8 component tree.

A run recorded here is ``simulation`` when its executor is deterministic. It is
never ``claim_eligible``: a harness change measured on a deterministic task pack
is interface evidence, not a research result.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import RUNTIME_DATA_ROOT, REPO_ROOT
from .storage import read_json, write_json_atomic

SEAM_SCHEMA = "harness2-seam-0.1"
ARTIFACT_SCHEMA = "harness2-run-0.1"
DEFAULT_ARTIFACT_PATH = RUNTIME_DATA_ROOT / "harness2" / "latest.json"
DEFAULT_SCOPE = "harness2.harness"
BRIDGE_RELATIVE = Path("scripts") / "harness2_run.py"

SUPPORTED_PYTHON = ((3, 12), (3, 13))

#: The adapter surface a science task pack must supply. Kept here as data so a
#: future adapter can be checked without importing the 3.12-only package.
REQUIRED_ADAPTER_METHODS = (
    "tasks",
    "domain_of",
    "task_prompt",
    "task_files",
    "execute",
    "delivered",
    "trajectory",
    "deliverable_text",
    "base_harness",
    "validate_tree",
    "score",
)

COMPONENT_LABELS = {
    "systemprompt.md": "c1 system prompt",
    "guardrails.md": "c2 guardrails",
    "LongTermMEMORY.md": "c3 memory",
    "tool_descriptions/tool_guidance.md": "c4 tool guidance",
    "sub_agents": "c5 subagents",
    "skills": "c6 skills",
    "scripts": "c7 scripts",
    "plugin": "c8 plugins",
}

IMMUTABLE_TOKENS = (
    "claim",
    "evidence",
    "gate",
    "rubric",
    "export",
    "signature",
    "authorship",
    "closure",
    "heldout",
)


class Harness2Error(ValueError):
    """The seam cannot run or its output breaks the frozen contract."""


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def resolve_root(explicit: str = "") -> Path:
    """Locate the Harness² checkout: explicit, env, sibling, then parent sibling.

    An explicit path is authoritative: if it is wrong, the probe must say so instead of
    silently using a different checkout the caller did not name.
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    candidates: List[Path] = []
    env_root = os.environ.get("HARNESS2_ROOT", "").strip()
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(REPO_ROOT / "harness2-main")
    candidates.append(REPO_ROOT.parent / "harness2-main")
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if (resolved / "harness2" / "core" / "spec.py").is_file():
            return resolved
    return candidates[0].expanduser()


def _package_meta(root: Path) -> Dict[str, Any]:
    text = _read_text(root / "pyproject.toml")
    version = ""
    requires = ""
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if match:
        version = match.group(1)
    match = re.search(r'^requires-python\s*=\s*"([^"]+)"', text, re.M)
    if match:
        requires = match.group(1)
    return {"version": version, "requires_python": requires}


def _python_version(path: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            [str(path), "-c", "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip()


def _is_supported(version: str) -> bool:
    parts = version.split(".")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return False
    return (int(parts[0]), int(parts[1])) in SUPPORTED_PYTHON


def find_interpreter(explicit: str = "") -> Dict[str, Any]:
    """Find a 3.12/3.13 interpreter; never assume the caller's own Python qualifies."""
    attempted: List[str] = []

    def consider(path_text: str, source: str) -> Optional[Dict[str, Any]]:
        if not path_text:
            return None
        path = Path(path_text)
        if not path.is_file():
            attempted.append("%s (%s): not a file" % (path_text, source))
            return None
        version = _python_version(path)
        if not version:
            attempted.append("%s (%s): did not run" % (path_text, source))
            return None
        if not _is_supported(version):
            attempted.append("%s (%s): %s unsupported" % (path_text, source, version))
            return None
        return {"path": str(path), "version": version, "source": source}

    for env_name in ("RESEARCH_AGENT_PY312", "HARNESS2_PYTHON"):
        found = consider(os.environ.get(env_name, "").strip(), "env:" + env_name)
        if found:
            return dict(found, attempted=attempted)

    if explicit:
        found = consider(explicit, "explicit")
        if found:
            return dict(found, attempted=attempted)

    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            for tag in ("-3.12", "-3.13"):
                try:
                    probe = subprocess.run(
                        [launcher, tag, "-c", "import sys;print(sys.executable)"],
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                except (OSError, subprocess.SubprocessError):
                    continue
                if probe.returncode == 0:
                    found = consider((probe.stdout or "").strip(), "py " + tag)
                    if found:
                        return dict(found, attempted=attempted)

    for name in ("python3.12", "python3.13", "python"):
        found = consider(shutil.which(name) or "", "PATH:" + name)
        if found:
            return dict(found, attempted=attempted)

    if os.name == "nt":
        guesses = []
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            for folder in ("Python312", "Python313"):
                guesses.append(Path(local) / "Programs" / "Python" / folder / "python.exe")
                guesses.append(Path(local) / folder / "python.exe")
        for drive in ("C:/", "D:/"):
            for folder in ("Python312", "Python313"):
                guesses.append(Path(drive) / folder / "python.exe")
        for candidate in guesses:
            found = consider(str(candidate), "guess")
            if found:
                return dict(found, attempted=attempted)

    return {"path": "", "version": "", "source": "", "attempted": attempted}


def bridge_path() -> Path:
    return REPO_ROOT / BRIDGE_RELATIVE


def probe(root: str = "", interpreter: str = "") -> Dict[str, Any]:
    """Read-only status of the seam. Never raises: an unavailable seam is a state."""
    resolved = resolve_root(root)
    meta = _package_meta(resolved)
    spec_path = resolved / "harness2" / "core" / "spec.py"
    python = find_interpreter(interpreter)
    bridge = bridge_path()
    payload = {
        "schema": SEAM_SCHEMA,
        "checked_at": _now(),
        "available": False,
        "reason": "",
        "root": str(resolved),
        "root_found": spec_path.is_file(),
        "root_source": "explicit" if root else ("env" if os.environ.get("HARNESS2_ROOT") else "sibling"),
        "package": meta,
        "interpreter": python,
        "bridge": {"path": str(bridge), "exists": bridge.is_file()},
        "adapters": ["demo", "science"],
        "platform_python": "%d.%d.%d" % sys.version_info[:3],
        "shims": [
            {
                "name": "fcntl.flock",
                "why": "Harness² uses advisory file locks; Windows has no fcntl.",
                "when": "os.name == 'nt'",
            },
            {
                "name": "tree.read_tree",
                "why": "Upstream assumes POSIX path separators when matching the editable surface.",
                "when": "os.name == 'nt'",
            },
        ],
        "governance": {
            "scope": DEFAULT_SCOPE,
            "admission": "public + hidden + dry-run + human; harness2 never signs",
            "classification": "simulation unless a model-backed executor is declared",
        },
    }
    problems = []
    if not spec_path.is_file():
        problems.append("Harness² checkout not found at %s" % resolved)
    if not bridge.is_file():
        problems.append("bridge script missing: %s" % bridge)
    if not python.get("path"):
        problems.append(
            "no Python 3.12/3.13 interpreter found (Harness² requires >=3.12,<3.14); "
            "set RESEARCH_AGENT_PY312"
        )
    if problems:
        payload["reason"] = "; ".join(problems)
        return payload
    payload["available"] = True
    payload["reason"] = "ready"
    return payload


def run_bridge(
    interpreter: str = "",
    root: str = "",
    output: str = "",
    k: int = 2,
    mode: str = "both",
    adapter: str = "demo",
    timeout: int = 1800,
) -> Dict[str, Any]:
    """Run Harness² through the bridge and return the parsed artifact."""
    status = probe(root=root, interpreter=interpreter)
    if not status["available"]:
        raise Harness2Error(status["reason"])
    if k < 1:
        raise Harness2Error("k must be >= 1")
    if mode not in ("parallel", "sequential", "both"):
        raise Harness2Error("mode must be parallel, sequential or both")
    if adapter not in status["adapters"]:
        raise Harness2Error("unknown adapter: %s" % adapter)

    output_dir = Path(output).expanduser().resolve() if output else (
        RUNTIME_DATA_ROOT / "harness2" / ("run-%d" % int(time.time()))
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / "harness2-run.json"
    command = [
        status["interpreter"]["path"],
        str(bridge_path()),
        "--harness2-root",
        status["root"],
        "--output",
        str(output_dir),
        "--k",
        str(int(k)),
        "--mode",
        mode,
        "--adapter",
        adapter,
    ]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    started = time.time()
    # ExecPort 路由分派（71-§5 步 5 收口）：bridge 面的分派经端口门禁 + 溯源。
    # 端口只记录 provenance，不启动/调度进程；未注册面会在此拒绝执行。
    try:
        from .execport.exec_port import begin_dispatch, end_dispatch

        ticket = begin_dispatch("bridge", subject=str(output_dir.name))
    except Exception:
        ticket = None
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        if ticket:
            end_dispatch(ticket, "failed_timeout")
        raise Harness2Error("Harness² bridge timed out after %ss" % timeout)
    except OSError as exc:
        if ticket:
            end_dispatch(ticket, "failed_start")
        raise Harness2Error("cannot start the bridge: %s" % exc)

    if not artifact_path.is_file():
        raise Harness2Error(
            "bridge produced no artifact (exit %s): %s"
            % (completed.returncode, (completed.stderr or completed.stdout or "")[-600:])
        )
    payload = load_artifact(artifact_path)
    payload["bridge"] = {
        "command": command,
        "exit_code": completed.returncode,
        "wall_s": round(time.time() - started, 3),
        "stdout_tail": (completed.stdout or "")[-1200:],
        "stderr_tail": (completed.stderr or "")[-1200:],
    }
    # Which platform produced this artifact. Without it, a harness generation cannot be
    # tied to the code it was measured on, and a later platform change cannot name the
    # generations that now need re-validation.
    from .paths import build_fingerprint

    payload["platform_fingerprint"] = build_fingerprint()
    if ticket:
        end_dispatch(ticket, "completed")
        payload["exec_face"] = {"kind": "bridge", "status": "completed"}
    write_json_atomic(artifact_path, payload)
    return payload


def load_artifact(path: Any = "") -> Dict[str, Any]:
    target = Path(path) if path else DEFAULT_ARTIFACT_PATH
    data = read_json(target)
    if not isinstance(data, dict):
        raise Harness2Error("no Harness² artifact at %s" % target)
    return data


def validate_artifact(payload: Any) -> List[str]:
    """Contract check. Returns human-readable problems; [] means the shape holds."""
    problems: List[str] = []
    if not isinstance(payload, dict):
        return ["artifact must be an object"]
    if payload.get("schema") != ARTIFACT_SCHEMA:
        problems.append("schema must be %s" % ARTIFACT_SCHEMA)

    harness2 = payload.get("harness2") or {}
    if not isinstance(harness2, dict) or not harness2.get("root"):
        problems.append("harness2.root is required")
    if not isinstance(harness2.get("method_version"), int):
        problems.append("harness2.method_version must be an integer")

    run = payload.get("run") or {}
    for key, kind in (("adapter", str), ("k", int), ("modes", list), ("exit_code", int)):
        value = run.get(key)
        if not isinstance(value, kind) or isinstance(value, bool):
            problems.append("run.%s must be %s" % (key, kind.__name__))
    if not run.get("adapter"):
        problems.append("run.adapter must not be empty")

    budget = payload.get("budget") or {}
    for key in ("R", "expected_R", "P", "expected_P"):
        value = budget.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            problems.append("budget.%s must be an integer" % key)

    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        problems.append("tasks must be a non-empty list")
    else:
        for index, task in enumerate(tasks):
            if not isinstance(task, dict) or not task.get("task_id"):
                problems.append("tasks[%d].task_id is required" % index)
                continue
            if task.get("status") not in ("ok", "partial", "failed"):
                problems.append("tasks[%d].status is invalid" % index)

    surface = payload.get("surface") or {}
    components = surface.get("components") if isinstance(surface, dict) else None
    if not isinstance(components, dict) or len(components) < 6:
        problems.append("surface.components must describe at least 6 editable components")

    if not isinstance(payload.get("adopted"), list):
        problems.append("adopted must be a list")

    classification = payload.get("classification") or {}
    if not isinstance(classification.get("simulation"), bool):
        problems.append("classification.simulation must be a boolean")
    if not isinstance(classification.get("claim_eligible"), bool):
        problems.append("classification.claim_eligible must be a boolean")
    if classification.get("claim_eligible"):
        problems.append(
            "classification.claim_eligible must stay false: a deterministic harness run is "
            "interface evidence, not a research result"
        )

    pack_hash = payload.get("task_pack_sha256") or ""
    if len(pack_hash) != 64 or any(ch not in "0123456789abcdef" for ch in pack_hash.lower()):
        problems.append("task_pack_sha256 must be a 64-character sha256")

    return problems


def conformance(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn the contract and the budget identity into a page-ready checklist."""
    problems = validate_artifact(payload)
    run = payload.get("run") or {}
    budget = payload.get("budget") or {}
    tasks = payload.get("tasks") or []
    adopted = payload.get("adopted") or []
    lessons = payload.get("lessons") or []
    classification = payload.get("classification") or {}

    def item(check_id: str, label: str, ok: bool, detail: str) -> Dict[str, Any]:
        return {"id": check_id, "label": label, "ok": bool(ok), "detail": detail}

    failed_tasks = [t.get("task_id") for t in tasks if t.get("status") != "ok"]
    fallbacks = payload.get("fallbacks") or []
    identity_ok = (
        isinstance(budget.get("R"), int)
        and isinstance(budget.get("P"), int)
        and budget.get("R") == budget.get("expected_R")
        and budget.get("P") == budget.get("expected_P")
    )
    lessons_with_evidence = [
        lesson
        for lesson in lessons
        if isinstance(lesson, dict) and str(lesson.get("evidence", "")).strip()
    ]
    checklist = [
        item("contract", "产物符合 harness2-run-0.1 契约", not problems, "; ".join(problems[:3]) or "shape ok"),
        item(
            "budget",
            "预算恒等式 R=4k、P=3k 成立",
            identity_ok,
            "R=%s/%s · P=%s/%s" % (budget.get("R"), budget.get("expected_R"), budget.get("P"), budget.get("expected_P")),
        ),
        item("exit", "桥进程正常退出", run.get("exit_code") == 0, "exit=%s" % run.get("exit_code")),
        item("tasks", "全部任务完成", not failed_tasks, ", ".join(failed_tasks) or "%d/%d ok" % (len(tasks), len(tasks))),
        item("fallback", "没有阶段回退到旧 harness", not fallbacks, ", ".join(fallbacks) or "no fallback"),
        item("adopted", "至少有一个被采纳的组件改动", bool(adopted), "%d adopted" % len(adopted)),
        item(
            "lessons",
            "经验条目都带观测证据",
            bool(lessons) and len(lessons_with_evidence) == len(lessons),
            "%d/%d with evidence" % (len(lessons_with_evidence), len(lessons)),
        ),
        item(
            "classification",
            "确定性执行被标为 simulation，且不可申领能力",
            classification.get("simulation") is True and classification.get("claim_eligible") is False,
            "simulation=%s · claim_eligible=%s" % (classification.get("simulation"), classification.get("claim_eligible")),
        ),
        item(
            "shims",
            "便携性补丁已显式声明",
            bool(payload.get("shims")) or run.get("platform") not in ("nt", "win32", "windows"),
            ", ".join(item.get("name", "") for item in payload.get("shims") or [])
            or "none needed on %s" % (run.get("platform") or "posix"),
        ),
        item(
            "human_gate",
            "产物不含任何签名/准入动作",
            not payload.get("admission"),
            "admission stays in the platform CLI",
        ),
    ]
    return checklist


def _kind_for_path(path: str) -> str:
    if path.startswith("skills/"):
        return "skill"
    if path in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md") or path.startswith(
        "tool_descriptions/"
    ):
        return "prompt"
    return "process"


def to_candidates(payload: Dict[str, Any], scope: str = DEFAULT_SCOPE) -> Tuple[List[Any], List[Dict[str, str]]]:
    """Map adopted harness edits onto governed candidates. Returns (candidates, blocked).

    The same component is often adopted on several tasks and modes. One candidate per
    distinct (path, diff) keeps the ledger readable; the observations it was seen on are
    listed in the rationale, not turned into duplicate episodes.
    """
    from .rsi import Candidate

    grouped: Dict[str, Dict[str, Any]] = {}
    blocked: List[Dict[str, str]] = []
    for entry in payload.get("adopted") or []:
        if not isinstance(entry, dict):
            continue
        task_id = str(entry.get("task_id", "")).strip() or "task"
        mode = str(entry.get("mode", "")).strip() or "mode"
        for change in entry.get("changes") or []:
            path = str(change.get("path", "")).strip()
            diff = str(change.get("diff", "")).strip()
            if not path or not diff:
                continue
            # The immutable-surface guard applies to the component path, not to task ids:
            # a task named "claims-1" is data, not a claim surface.
            lowered = path.lower()
            hit = next((token for token in IMMUTABLE_TOKENS if token in lowered), "")
            if hit:
                entry_block = {
                    "target": "%s/" % scope + path,
                    "reason": "component path names an immutable surface (%s); a harness "
                    "component cannot be admitted through this scope" % hit,
                }
                if entry_block not in blocked:
                    blocked.append(entry_block)
                continue
            key = path + "::" + _sha256_bytes(diff.encode("utf-8"))
            slot = grouped.setdefault(
                key,
                {
                    "path": path,
                    "diff": diff,
                    "seen_on": [],
                    "notes": "",
                    "lesson": "",
                },
            )
            slot["seen_on"].append("%s/%s" % (task_id, mode))
            if entry.get("notes") and not slot["notes"]:
                slot["notes"] = str(entry["notes"]).strip()
            if entry.get("lesson") and not slot["lesson"]:
                slot["lesson"] = str(entry["lesson"]).strip()

    held = payload.get("held_out") or {}
    held_note = ""
    if held.get("n"):
        held_note = "held-out %s/%s (base %s/%s)" % (
            held.get("passed", 0),
            held.get("n", 0),
            held.get("base_passed", 0),
            held.get("n", 0),
        )

    candidates: List[Any] = []
    for slot in grouped.values():
        path = str(slot["path"])
        seen = sorted(set(slot["seen_on"]))
        rationale = (
            "Harness² adopted this component on %d improvement runs (%s). %s"
            % (len(seen), ", ".join(seen[:6]), slot["notes"] or slot["lesson"] or "")
        ).strip()
        candidates.append(
            Candidate(
                kind=_kind_for_path(path),
                target="%s/" % scope + path,
                patch=str(slot["diff"])[:12000],
                rationale=rationale[:2000],
                predicted_effect=held_note or "no measured gain claimed; deterministic task pack",
                scope=scope,
                proposer="harness2",
                proposer_model=str((payload.get("run") or {}).get("executor", "")),
                version=str((payload.get("harness2") or {}).get("method_version", "")),
            )
        )
    return candidates, blocked


def _metrics(payload: Dict[str, Any]) -> Dict[str, float]:
    budget = payload.get("budget") or {}
    tasks = payload.get("tasks") or []
    adopted = payload.get("adopted") or []
    held = payload.get("held_out") or {}
    return {
        "tasks_ok": float(sum(1 for t in tasks if t.get("status") == "ok")),
        "tasks_total": float(len(tasks)),
        "adopted_components": float(len(adopted)),
        "budget_identity": 1.0
        if budget.get("R") == budget.get("expected_R") and budget.get("P") == budget.get("expected_P")
        else 0.0,
        "held_out_passed": float(held.get("passed", 0) or 0),
        "held_out_n": float(held.get("n", 0) or 0),
    }


def to_evidence(
    payload: Dict[str, Any], artifact_path: Any = "", task_pack_sha256: str = ""
) -> Tuple[Any, Optional[Any]]:
    """Build (public, hidden) evidence from a run. Hidden is absent without a held-out split."""
    from .rsi import EvalEvidence

    problems = validate_artifact(payload)
    tasks = payload.get("tasks") or []
    failed = [t.get("task_id") for t in tasks if t.get("status") != "ok"]
    artifact = Path(artifact_path) if artifact_path else DEFAULT_ARTIFACT_PATH
    digest = ""
    if artifact.is_file():
        digest = _sha256_bytes(artifact.read_bytes())
    metrics = _metrics(payload)
    public = EvalEvidence(
        split="public",
        status="failed" if (problems or failed) else "passed",
        artifact_ref=str(artifact),
        metrics=metrics,
        n=len(tasks),
        note="Harness² improvement split; deterministic executor, interface evidence only",
        simulation=True,
        claim_eligible=False,
        evaluator="harness2-bridge/%s" % str((payload.get("run") or {}).get("adapter", "")),
        artifact_sha256=digest,
        task_pack_sha256=task_pack_sha256 or str(payload.get("task_pack_sha256", "")),
        evaluated_at=_now(),
    )
    held = payload.get("held_out") or {}
    hidden = None
    if held.get("n"):
        hidden = EvalEvidence(
            split="hidden",
            status="passed" if held.get("passed") and not held.get("regressed") else "failed",
            artifact_ref=str(held.get("artifact_ref") or artifact),
            metrics={
                "held_out_passed": float(held.get("passed", 0)),
                "held_out_n": float(held.get("n", 0)),
                "held_out_delta": float(held.get("delta", 0)),
            },
            n=int(held.get("n", 0)),
            note="held-out task never shown to the proposer; deterministic executor",
            simulation=True,
            claim_eligible=False,
            evaluator="harness2-bridge/held-out",
            artifact_sha256=digest,
            task_pack_sha256=task_pack_sha256 or str(payload.get("task_pack_sha256", "")),
            evaluated_at=_now(),
        )
    return public, hidden


def summarize(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Page-ready projection: no new facts, only the artifact rearranged."""
    problems = validate_artifact(payload)
    checklist = conformance(payload)
    budget = payload.get("budget") or {}
    run = payload.get("run") or {}
    held = payload.get("held_out") or {}
    return {
        "schema": "harness2-story-0.1",
        "generated_at": payload.get("generated_at", ""),
        "available": not problems,
        "problems": problems,
        "platform_fingerprint": payload.get("platform_fingerprint", ""),
        "run": {
            "adapter": run.get("adapter", ""),
            "executor": run.get("executor", ""),
            "platform": run.get("platform", ""),
            "k": run.get("k", 0),
            "modes": run.get("modes", []),
            "wall_s": run.get("wall_s", 0),
            "started_at": run.get("started_at", ""),
            "finished_at": run.get("finished_at", ""),
        },
        "budget": {
            "R": budget.get("R", 0),
            "expected_R": budget.get("expected_R", 0),
            "P": budget.get("P", 0),
            "expected_P": budget.get("expected_P", 0),
            "usd": budget.get("usd", 0),
        },
        "tasks": [
            {"task_id": t.get("task_id", ""), "domain": t.get("domain", ""), "status": t.get("status", "")}
            for t in payload.get("tasks") or []
        ],
        "surface": payload.get("surface") or {},
        "adopted": payload.get("adopted") or [],
        "lessons": payload.get("lessons") or [],
        "held_out": held,
        "classification": payload.get("classification") or {},
        "checklist": checklist,
        "checklist_ok": all(entry["ok"] for entry in checklist),
    }


def _public_probe(status: Dict[str, Any]) -> Dict[str, Any]:
    """The probe fields a published page may show: no absolute local paths."""
    interpreter = status.get("interpreter") or {}
    bridge = status.get("bridge") or {}
    root = str(status.get("root") or "")
    return {
        "available": bool(status.get("available")),
        "reason": status.get("reason", ""),
        "root_name": Path(root).name if root else "",
        "package": status.get("package") or {},
        "interpreter_version": interpreter.get("version", ""),
        "interpreter_source": interpreter.get("source", ""),
        "bridge_name": Path(str(bridge.get("path") or "")).name if bridge.get("path") else "",
        "bridge_exists": bool(bridge.get("exists")),
        "adapters": status.get("adapters") or [],
        "platform_python": status.get("platform_python", ""),
        "shims": status.get("shims") or [],
    }


def public_story(payload: Dict[str, Any], status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Story safe to publish: the same facts, minus machine-specific paths."""
    story = summarize(payload)
    story["probe"] = _public_probe(status if status is not None else probe())
    held = dict(story.get("held_out") or {})
    held.pop("artifact_ref", None)
    story["held_out"] = held
    return story


def write_artifact(payload: Dict[str, Any], path: Any = "") -> Path:
    target = Path(path) if path else DEFAULT_ARTIFACT_PATH
    write_json_atomic(target, payload)
    return target


def record_episode(
    payload: Dict[str, Any],
    ledger_path: Any,
    artifact_path: Any = "",
    scope: str = DEFAULT_SCOPE,
    policy_path: Any = "",
    simulation: bool = True,
) -> Dict[str, Any]:
    """Write pending episodes for adopted edits. Never admits, never signs."""
    from .evolution_policy import DEFAULT_EVOLUTION_POLICY_PATH, EvolutionPolicyStore
    from .rsi import RSIController, StepLedger

    policy = EvolutionPolicyStore(
        Path(policy_path) if policy_path else DEFAULT_EVOLUTION_POLICY_PATH
    )
    policy.require_enabled()
    failed = [item["id"] for item in conformance(payload) if not item["ok"]]
    if failed:
        raise Harness2Error(
            "refusing to record: conformance failed (%s); a partial run is not an episode"
            % ", ".join(failed)
        )
    candidates, blocked = to_candidates(payload, scope=scope)
    # Check every candidate before writing one: a policy denial halfway through would leave
    # a partial batch in the ledger, and a partial batch looks like a complete round.
    for candidate in candidates:
        policy.require_candidate(candidate.kind, candidate.target)
    public, hidden = to_evidence(payload, artifact_path=artifact_path)
    ledger = StepLedger.load(Path(ledger_path))
    controller = RSIController(ledger)
    episodes: List[Dict[str, Any]] = []
    for candidate in candidates:
        record = controller.propose(
            candidate,
            observation="Harness² run %s k=%s" % (payload.get("run", {}).get("adapter"), payload.get("run", {}).get("k")),
            dry_run_ref=str(payload.get("run", {}).get("dry_run_ref", "")),
            simulation=simulation,
        )
        controller.evaluate(record.episode_id, public_eval=public, hidden_eval=hidden)
        episodes.append(
            {
                "episode_id": record.episode_id,
                "candidate_id": candidate.candidate_id,
                "target": candidate.target,
                "patch_chars": len(candidate.patch),
                "hidden_present": hidden is not None,
            }
        )
    return {
        "ledger": str(ledger_path),
        "episodes": episodes,
        "blocked": blocked,
        "public_status": public.status,
        "hidden_present": hidden is not None,
        "simulation": simulation,
        "note": "pending_human: admission needs dry-run, public, hidden and a named human",
    }
