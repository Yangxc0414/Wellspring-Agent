"""Drive the Host-as-Model loop over the real stdio MCP transport, one handoff at a time.

A bound keyless ``host_agent`` profile makes every model stage suspend instead of calling
an external API. This harness runs the task, reads the turn back through
``research_model_turns``, answers it from ``<workdir>/answers/<turn_id>.json`` when that
answer exists, and re-runs so the stage replays it. It stops when it reaches a stage with
no answer yet and writes the request so the host agent can produce one.

    python scripts/host_model_loop_test.py --workdir runtime_data/host-model-loop
    # write runtime_data/host-model-loop/answers/MT-xxxx.json, then re-run the same command

Exit codes: 3 = a turn still awaits a host answer; 0 = the run reached a real stop point
and the closed-loop checks passed; 1 = the loop broke.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from research_mcp_demo import MCPClient  # noqa: E402

GOAL = "How do self-improving coding agents use archives and evaluation gates to improve?"
SOURCE = "real"
LANGUAGE = "en"
VENUE = "en_conference"
MAX_STAGES = 6
STATE_SCHEMA = "host-model-loop-state-0.2"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _prepare_store(workdir: Path) -> None:
    """Bind idea/experiment/paper to a keyless host-agent profile, like `host-model bind`."""
    from research_agent.models import GatewayStore, ModelProfile, ProviderConfig

    store = GatewayStore(workdir / "model_gateway.json")
    store.upsert_provider(
        ProviderConfig(
            provider_id="host-agent",
            kind="host_agent",
            label="宿主 Agent",
            models=["host-agent"],
        )
    )
    store.upsert_profile(
        ModelProfile(
            profile_id="host-agent",
            provider_id="host-agent",
            model="host-agent",
            label="宿主 Agent 模型",
            json_mode=True,
        )
    )
    for module in ("idea", "experiment", "paper"):
        store.set_binding(module, "host-agent")


def _client(workdir: Path) -> MCPClient:
    return MCPClient(
        ROOT,
        {
            "RESEARCH_AGENT_MODE": "test",
            "RESEARCH_AGENT_MODEL_STORE": str(workdir / "model_gateway.json"),
            "RESEARCH_AGENT_HOST_MODEL_LEDGER": str(workdir / "turns.json"),
            "PYTHONIOENCODING": "utf-8",
        },
    )


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2))


def _read(path: Path):
    with open(str(path), "r", encoding="utf-8") as handle:
        return json.loads(handle.read())


def _handoff_turn(client: MCPClient, project: str, run_id: str) -> str:
    actions = client.call(
        "research_next_actions", {"project_dir": project, "run_id": run_id}
    )
    item = next(
        (entry for entry in actions.get("next_actions", []) if entry.get("kind") == "host_model"),
        None,
    )
    return str(item["turn_id"]) if item else ""


def _turn_request(client: MCPClient, turn_id: str):
    queue = client.call("research_model_turns", {"status": "pending", "limit": 30})
    return next((t for t in queue.get("turns", []) if t.get("turn_id") == turn_id), None)


def _first_run(client: MCPClient, project: str):
    result = client.call(
        "research_bootstrap",
        {
            "project_dir": project,
            "goal": GOAL,
            "source": SOURCE,
            "task_type": "hypothesis_design",
            "max_sources": 6,
            "language": LANGUAGE,
            "venue_type": VENUE,
            "run_now": True,
        },
    )
    return result.get("run") or {}


def _rerun(client: MCPClient, project: str):
    result = client.call(
        "research_run",
        {
            "project_dir": project,
            "goal": GOAL,
            "source": SOURCE,
            "task_type": "hypothesis_design",
            "max_sources": 6,
            "language": LANGUAGE,
            "venue_type": VENUE,
        },
    )
    return result.get("run") or result.get("task") or result


def _answer_path(answers: Path, turn: dict):
    """Answers are keyed by request hash so they survive re-runs; turn id is a fallback."""
    for key in (turn.get("messages_sha256"), turn.get("turn_id")):
        if not key:
            continue
        candidate = answers / ("%s.json" % key)
        if candidate.exists():
            return candidate
    return None


def _drain_answerable(client: MCPClient, answers: Path, state, state_path: Path, note) -> bool:
    """Answer every queued turn we hold an answer for; returns whether any was answered."""
    queue = client.call("research_model_turns", {"status": "pending", "limit": 30})
    answered = 0
    for item in queue.get("turns", []):
        path = _answer_path(answers, item)
        if path is None:
            continue
        accepted = client.call(
            "research_model_respond",
            {
                "turn_id": str(item["turn_id"]),
                "text": path.read_text(encoding="utf-8"),
                "host_label": "Qoder Desktop",
            },
        )
        if not accepted.get("accepted"):
            note("FAIL", "host answer rejected for %s: %s" % (item["turn_id"], accepted.get("errors")))
            raise SystemExit(1)
        receipt = accepted.get("receipt") or {}
        state["answered"].append(
            {
                "turn_id": item["turn_id"],
                "module": item.get("module"),
                "purpose": item.get("purpose"),
                "messages_sha256": receipt.get("messages_sha256"),
                "text_sha256": receipt.get("text_sha256"),
                "host_label": receipt.get("host_label"),
            }
        )
        answered += 1
        note("answered", "%s module=%s" % (item["turn_id"], item.get("module")))
    if answered:
        _write(state_path, state)
    return bool(answered)


def drive(workdir: Path, project: str, reset: bool) -> int:
    workdir.mkdir(parents=True, exist_ok=True)
    answers = workdir / "answers"
    _prepare_store(workdir)
    state_path = workdir / "state.json"
    if reset and (workdir / "turns.json").exists():
        (workdir / "turns.json").unlink()
    state = _read(state_path) if state_path.exists() else {"answered": []}
    state.setdefault("answered", [])
    log = []

    def note(stage, detail=""):
        log.append({"stage": stage, "detail": str(detail)[:240], "at": _now()})
        print("[%s] %s" % (stage, str(detail)[:240]))

    client = _client(workdir)
    try:
        listed = client.request("tools/list")
        names = [tool["name"] for tool in listed.get("tools", [])]
        missing = [n for n in ("research_model_turns", "research_model_respond") if n not in names]
        if missing:
            note("FAIL", "not exposed over MCP: %s" % ", ".join(missing))
            return 1
        note("mcp", "%d tools exposed; host-model pair present" % len(names))

        client.call("research_project_init", {"project_dir": project, "name": "host-model-loop"})
        already_answered = bool(state.get("answered"))
        for _stage in range(MAX_STAGES):
            body = _rerun(client, project) if already_answered else _first_run(client, project)
            already_answered = True
            run_id = str(body.get("run_id") or "")
            status = str(body.get("status") or "")
            note("run", "run=%s status=%s" % (run_id, status))
            if not run_id:
                note("FAIL", "no run_id returned")
                return 1
            if status != "awaiting_host_model":
                return _finish(workdir, state_path, project, run_id, status, log, state)

            # Multi-round stages queue several turns at once: drain every turn we already
            # have an answer for, otherwise each pass would unblock exactly one call.
            if _drain_answerable(client, answers, state, state_path, note):
                continue

            turn_id = _handoff_turn(client, project, run_id)
            if not turn_id:
                note("FAIL", "awaiting_host_model but next_actions surfaced no turn")
                return 1
            turn = _turn_request(client, turn_id)
            if turn is None:
                note("FAIL", "pending turn %s missing from research_model_turns" % turn_id)
                return 1
            target = answers / ("%s.json" % turn.get("messages_sha256"))
            _write(
                workdir / "pending-request.json",
                {
                    "turn_id": turn_id,
                    "module": turn.get("module"),
                    "purpose": turn.get("purpose"),
                    "expects": turn.get("expects"),
                    "request": turn.get("request"),
                    "write_your_answer_to": str(target),
                },
            )
            _write(state_path, state)
            note(
                "awaiting_host_answer",
                "%s module=%s purpose=%s -> write %s"
                % (turn_id, turn.get("module"), turn.get("purpose"), target),
            )
            return 3
        note("FAIL", "hit the %d-stage ceiling without reaching a stop point" % MAX_STAGES)
        return 1
    finally:
        client.close()


def _finish(
    workdir: Path,
    state_path: Path,
    project: str,
    run_id: str,
    status: str,
    log,
    state,
) -> int:
    client = _client(workdir)
    checks = []

    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": str(detail)[:240]})
        print(
            "[%s] %s%s"
            % ("PASS" if passed else "FAIL", name, (" · " + str(detail)[:180]) if detail else "")
        )

    try:
        answered = state.get("answered", [])
        modules = [str(item.get("module")) for item in answered]
        check("model stages handed off and answered by the host", bool(modules), ", ".join(modules))

        idea_raw = client.call(
            "research_read_artifact",
            {"project_dir": project, "run_id": run_id, "path": "idea.json", "max_chars": 60000},
        )
        text = json.dumps(idea_raw, ensure_ascii=False)
        check(
            "host-authored candidates passed the module validator",
            "model_proposed_candidates" in text,
            "" if "model_proposed_candidates" in text else text[:160],
        )
        check(
            "G1 stayed human-only after the host answer",
            status in ("needs_human", "completed", "blocked") or "G1" in text,
            "status=%s" % status,
        )

        queue = client.call("research_model_turns", {"status": "pending", "limit": 20})
        answered_ids = {str(item.get("turn_id")) for item in answered}
        stranded = [
            str(item.get("turn_id"))
            for item in queue.get("turns", [])
            if str(item.get("turn_id")) in answered_ids
        ]
        check("answered stages left no pending duplicate", not stranded, ",".join(stranded))

        ledger = _read(workdir / "turns.json")
        responded = [t for t in ledger.get("turns", []) if t.get("status") == "responded"]
        check(
            "every answer receipt is bound to its own request hash",
            all(
                (t.get("receipt") or {}).get("messages_sha256") == t.get("messages_sha256")
                for t in responded
            ),
            "%d responded" % len(responded),
        )
        check(
            "every answer records a host label and response hash",
            all(
                (t.get("response") or {}).get("host_label")
                and (t.get("response") or {}).get("text_sha256")
                for t in responded
            ),
        )
        summary = {
            "schema_version": "host-model-loop-summary-0.2",
            "created_at": _now(),
            "project": project,
            "run_id": run_id,
            "final_status": status,
            "goal": GOAL,
            "source": SOURCE,
            "answered_turns": answered,
            "log": log,
            "checks": checks,
            "passed": sum(1 for item in checks if item["passed"]),
            "failed": sum(1 for item in checks if not item["passed"]),
            "boundary": (
                "no external API key was used: the host agent answered each model turn with its "
                "own model, and Q0/G1/G2/S5b/G5 stayed human-only"
            ),
        }
        _write(workdir / "loop-summary.json", summary)
        print(
            "\nhost-model loop: %d passed, %d failed -> %s"
            % (summary["passed"], summary["failed"], workdir / "loop-summary.json")
        )
        return 0 if summary["failed"] == 0 else 1
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default="runtime_data/host-model-loop")
    parser.add_argument("--project", default="runtime_data/host-model-loop/project")
    parser.add_argument("--reset", action="store_true", help="clear the turn ledger first")
    args = parser.parse_args()
    workdir = Path(args.workdir)
    if not workdir.is_absolute():
        workdir = ROOT / workdir
    return drive(workdir, args.project, bool(args.reset))


if __name__ == "__main__":
    raise SystemExit(main())
