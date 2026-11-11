"""Command line entry point for specs, the fixture pipeline, and the workbench."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
import os
import re
import subprocess
import sys
from dataclasses import asdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional

from .adapters import FixtureRetriever, LocalDocumentRetriever, LocalHFModel, MiniLMRetriever, RealCorpusRetriever, SimpleParser
from .actions import ActionError, automation_plan, run_skill
from .adapters.glm_model import GLMModel, glm_query_planner
from .adapters.openalex_retriever import OpenAlexRetriever
from .flow import sha256_json
from .models import GatewayModelPort, GatewayStore, ModelGateway, ModelTurnPending, SessionKeyStore
from .models.store import default_store_path
from .literature_memory import LiteratureMemoryError, LiteratureMemoryStore
from .custom_agents import CustomAgentError, CustomAgentStore
from .evolution_policy import EvolutionPolicyError, EvolutionPolicyStore
from .skill_registry import SkillError, SkillRegistryStore
from .waitpoints import WaitpointError, WaitpointStore
from .maintenance import MaintenanceAgent
from .paths import (
    DEFAULT_CUSTOM_AGENTS_PATH,
    DEFAULT_EVOLUTION_ACTIVE_PATH,
    DEFAULT_EVOLUTION_OBSERVATIONS_PATH,
    DEFAULT_EVOLUTION_POLICY_PATH,
    DEFAULT_LITERATURE_MEMORY_PATH,
    DEFAULT_MODEL_STORE_PATH,
    DEFAULT_RSI_LEDGER_PATH,
    DEFAULT_RSI_REAL_LEDGER_PATH,
    DEFAULT_RSI_S5_LEDGER_PATH,
    DEFAULT_SIGNER_STORE_PATH,
    DEFAULT_SKILL_LIBRARY_ROOT,
    DEFAULT_SKILL_REGISTRY_PATH,
    DEFAULT_SKILL_USAGE_PATH,
    DEFAULT_WORKSPACE_ARCHIVE_ROOT,
    DEFAULT_WORKSPACE_MEMORY_PATH,
)
from .orchestrator import (
    OrchestrationError,
    collaboration_plan,
    public_snapshot,
    run_orchestration,
    write_orchestration_artifacts,
)
from .rsi_proposer import FrozenModelProposer
from .modules.literature import LiteratureAgent, LiteratureRequest
from .modules.run import RunAgent
from .contracts import RunRequest
from .closure import ClosureAgent, audit_pipeline_bundle
from .signers import SignerError, SignerStore
from .task_agent import TaskAgent, TaskRequest
from .skill_lab import SkillLab, SkillLabError
from .lineage import LineageAgent, write_impact, write_manifest
from .bibliography import BibliographyAgent
from .modules.experiment import ExperimentDesignAgent
from .pipeline import PipelineRequest, PipelineRunner, write_pipeline_artifacts
from .rsi import Candidate, EvalEvidence, RSIController, RSIPolicyError, StepLedger, ledger_story, trace_research
from .rsi_fixture import run_confirmation_trial, run_fixture_trial
from .model_batch import load_observations, run_model_batch
from .real_eval import resolve_active_harness, run_real_confirmation, run_real_trial
from .s5_eval import resolve_s5_seed_policy, run_s5_confirmation, run_s5_trial
from .research_runner import ResearchRunner, load_research_tasks, run_research_cycle
from .cli_autopilot import add_autopilot_parsers
from .cli_design import add_design_parsers
from .cli_host import add_host_parsers, print_json as _print_json
from .specs import SpecError, SpecStore
from .workspace import (
    AgentRegistry,
    ArchiveStore,
    CommandRegistry,
    MemoryStore,
    WorkspaceStoreError,
    export_workspace_snapshots,
)


def _cmd_spec_list(store: SpecStore, args: argparse.Namespace) -> int:
    specs = store.list_specs()
    if getattr(args, "json", False):
        _print_json([spec.to_dict() for spec in specs])
        return 0
    for spec in specs:
        print("%-20s %-8s %-8s %s" % (spec.id, spec.stage, spec.version, spec.name))
    return 0


def _cmd_spec_show(store: SpecStore, args: argparse.Namespace) -> int:
    spec = store.load(args.module_id)
    if getattr(args, "body", False):
        print(spec.body)
        return 0
    _print_json(spec.to_dict())
    return 0


def _cmd_spec_update(store: SpecStore, args: argparse.Namespace) -> int:
    spec = store.update(
        args.module_id,
        version=args.version,
        status=args.status,
        name=args.name,
        stage=args.stage,
        inputs=args.inputs,
        outputs=args.outputs,
        tools=args.tools,
        gates=args.gates,
        invariants=args.invariants,
        changelog=args.changelog,
        replace_lists=bool(getattr(args, "replace_lists", False)),
    )
    _print_json(spec.to_dict())
    return 0


def _cmd_spec_patch(store: SpecStore, args: argparse.Namespace) -> int:
    text = args.text
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    if not text:
        raise SpecError("spec patch requires --text or --file")
    spec = store.patch_section(args.module_id, args.section, text)
    _print_json(spec.to_dict())
    return 0


def _models_required() -> bool:
    return (os.environ.get("RESEARCH_AGENT_MODE") or "test").strip().lower() == "production"


def _resolve_planner(spec: str):
    """Return (planner, note). Never raises unless production requires models."""
    from .adapters.glm_model import ModelConfigError, gateway_query_planner

    strict = _models_required()
    if not spec or spec == "rules":
        if strict and spec != "rules":
            from .models import ModelRequiredError

            raise ModelRequiredError("production requires a model-backed query planner")
        return None, ""
    if spec == "glm":
        try:
            return glm_query_planner(GLMModel.from_env(), strict=strict), "query planner: GLM-5.3-Flash (ZHIPU_API_KEY)"
        except ModelConfigError as error:
            if strict:
                from .models import ModelRequiredError

                raise ModelRequiredError(str(error))
            return None, "%s; using rule-based queries" % error
    if spec == "gateway":
        return gateway_query_planner(store_path=default_store_path(), strict=strict)
    if spec.startswith("profile:"):
        return gateway_query_planner(
            profile_id=spec.split(":", 1)[1],
            store_path=default_store_path(),
            strict=strict,
        )
    return None, "unknown planner '%s'; using rule-based queries" % spec


def _resolve_paper_writer(spec: str):
    """Return (section_writer, note). Never raises: missing keys fall back."""
    from .adapters.paper_writer import gateway_paper_writer

    strict = _models_required()
    if not spec or spec == "off":
        if strict and spec != "off":
            from .models import ModelRequiredError

            raise ModelRequiredError("production requires a model-backed paper writer")
        return None, ""
    if spec == "auto":
        return gateway_paper_writer(store_path=default_store_path(), strict=strict)
    if spec.startswith("profile:"):
        return gateway_paper_writer(
            profile_id=spec.split(":", 1)[1],
            store_path=default_store_path(),
            strict=strict,
        )
    return None, "unknown writer '%s'; using deterministic draft" % spec


def _resolve_idea_proposer(spec: str):
    """Return (proposer, note). Never raises: missing keys fall back to rules."""
    from .adapters.research_models import gateway_idea_proposer

    strict = _models_required()
    if not spec or spec == "off":
        if strict and spec != "off":
            from .models import ModelRequiredError

            raise ModelRequiredError("production requires a model-backed idea proposer")
        return None, ""
    if spec == "auto":
        return gateway_idea_proposer(store_path=default_store_path(), strict=strict)
    if spec.startswith("profile:"):
        return gateway_idea_proposer(
            profile_id=spec.split(":", 1)[1],
            store_path=default_store_path(),
            strict=strict,
        )
    return None, "unknown idea model '%s'; using rule-based candidates" % spec


def _resolve_experiment_designer(spec: str):
    """Return (designer, note). Never raises: missing keys fall back to rules."""
    from .adapters.research_models import gateway_experiment_designer

    strict = _models_required()
    if not spec or spec == "off":
        if strict and spec != "off":
            from .models import ModelRequiredError

            raise ModelRequiredError("production requires a model-backed experiment designer")
        return None, ""
    if spec == "auto":
        return gateway_experiment_designer(store_path=default_store_path(), strict=strict)
    if spec.startswith("profile:"):
        return gateway_experiment_designer(
            profile_id=spec.split(":", 1)[1],
            store_path=default_store_path(),
            strict=strict,
        )
    return None, "unknown experiment model '%s'; using deterministic design" % spec


def _resolve_support_judge(spec: str):
    """Return (support_judge, note). Production requires the judge model."""
    from .adapters.support_judge import gateway_support_judge

    strict = _models_required()
    if not spec or spec == "off":
        if strict and spec != "off":
            from .models import ModelRequiredError

            raise ModelRequiredError("production requires a support judge")
        return None, ""
    if spec == "auto":
        return gateway_support_judge(store_path=default_store_path(), strict=strict)
    if spec.startswith("profile:"):
        return gateway_support_judge(
            profile_id=spec.split(":", 1)[1],
            store_path=default_store_path(),
            strict=strict,
        )
    return None, "unknown support judge '%s'; using lexical audit" % spec


def _cmd_literature_run(args: argparse.Namespace) -> int:
    store = SpecStore()
    spec = store.load("literature")
    if args.source == "openalex":
        retriever = OpenAlexRetriever(mailto=args.mailto or None)
        source_scope = ["openalex"]
    elif args.source == "local":
        if not args.corpus_dir:
            raise RuntimeError("--source local requires --corpus-dir")
        retriever = LocalDocumentRetriever(Path(args.corpus_dir))
        source_scope = ["local"]
    else:
        corpus = Path(args.fixture) if args.fixture else None
        retriever = FixtureRetriever(corpus)
        source_scope = ["fixture"]
    planner, planner_note = _resolve_planner(args.planner)
    if planner_note:
        print(planner_note, file=sys.stderr)
    agent = LiteratureAgent(spec, retriever, SimpleParser(), query_planner=planner)
    result = agent.run(
        LiteratureRequest(
            question=args.question,
            max_sources=args.max_sources,
            source_scope=source_scope,
            run_id=args.run_id,
            coverage_plan=True,
        )
    )
    _print_json(result.to_dict())
    return 0


def _cmd_literature_fetch(args: argparse.Namespace) -> int:
    from .adapters.arxiv_fetcher import ArxivFetchError, ArxivFetcher

    try:
        result = ArxivFetcher(timeout=args.timeout).fetch(
            query=args.query,
            target_dir=Path(args.target_dir),
            max_results=args.max_results,
            allow_network=args.allow_network,
        )
    except (ArxivFetchError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_literature_discover(args: argparse.Namespace) -> int:
    from .adapters.paper_discovery import discover_papers

    sources = [
        item.strip() for item in str(args.sources or "").split(",") if item.strip()
    ]
    report = discover_papers(
        args.query or "",
        sources=sources or None,
        limit_per_source=args.limit_per_source,
        allow_network=args.allow_network,
        timeout=args.timeout,
    )
    payload = report.to_dict()
    if args.output:
        _write_json(Path(args.output), payload)
    _print_json(payload)
    return 0


def _cmd_literature_prescreen(args: argparse.Namespace) -> int:
    import json

    from .prescreen import prescreen

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    candidates = payload if isinstance(payload, list) else list(payload.get("candidates") or [])
    abstracts = {}
    if args.abstracts:
        loaded = json.loads(Path(args.abstracts).read_text(encoding="utf-8"))
        abstracts = {
            str(key): str(value) for key, value in loaded.items()
        } if isinstance(loaded, dict) else {}
    exclude = [
        item.strip() for item in str(args.exclude_terms or "").split(",") if item.strip()
    ]
    report = prescreen(
        candidates, query=args.query, abstracts=abstracts,
        min_hits=args.min_hits, exclude_terms=exclude,
    )
    result = report.to_dict()
    if args.output:
        _write_json(Path(args.output), result)
    _print_json(result)
    return 0


def _cmd_literature_memory(args: argparse.Namespace) -> int:
    store = LiteratureMemoryStore(Path(args.memory_path))
    if args.memory_command == "show":
        payload = store.snapshot(limit=args.limit)
        if args.output:
            _write_json(Path(args.output), payload)
            _print_json({"output": args.output, "topics": payload["count"]})
        else:
            _print_json(payload)
        return 0
    advice = store.advise(args.question, args.max_sources, args.source)
    if args.output:
        _write_json(Path(args.output), advice)
        _print_json({"output": args.output, "observed_runs": advice["observed_runs"]})
    else:
        _print_json(advice)
    return 0


def _cmd_orchestrate_plan(args: argparse.Namespace) -> int:
    store = LiteratureMemoryStore(Path(args.memory_path))
    custom_store = CustomAgentStore(Path(args.custom_agents_path))
    policy_store = EvolutionPolicyStore(Path(args.policy_path))
    try:
        policy = policy_store.snapshot()
        advice = (
            store.advise(args.topic, args.max_sources, args.source)
            if policy_store.allows_memory_order()
            else None
        )
        plan = collaboration_plan(
            args.topic,
            args.max_sources,
            args.source,
            advice,
            custom_agents=custom_store.list(enabled_only=True),
            evolution_policy=policy,
        )
    except (LiteratureMemoryError, CustomAgentError, EvolutionPolicyError, OrchestrationError) as exc:
        raise SystemExit(str(exc))
    _print_json(plan)
    return 0


def _cmd_orchestrate_run(args: argparse.Namespace) -> int:
    try:
        result = run_orchestration(
            topic=args.topic,
            max_sources=args.max_sources,
            source=args.source,
            corpus_path=Path(args.corpus) if args.corpus else None,
            memory_path=Path(args.memory_path),
            max_workers=args.max_workers,
            custom_agents_path=Path(args.custom_agents_path),
            policy_path=Path(args.policy_path),
        )
    except (LiteratureMemoryError, CustomAgentError, EvolutionPolicyError, OrchestrationError) as exc:
        raise SystemExit(str(exc))
    payload = result.to_dict()
    if args.output_dir:
        path = write_orchestration_artifacts(result, Path(args.output_dir))
        payload["artifacts"] = str(path)
    if args.summary_out:
        _write_json(Path(args.summary_out), public_snapshot(result))
        payload["summary"] = args.summary_out
    _print_json(payload)
    return 0


def _cmd_agent(args: argparse.Namespace) -> int:
    store = CustomAgentStore(Path(args.custom_agents_path))
    try:
        if args.agent_command == "list":
            _print_json(store.snapshot())
            return 0
        if args.agent_command == "add":
            agent = store.add(
                name=args.name,
                role=args.role,
                purpose=args.purpose,
                checks=args.check,
                enabled=not args.disabled,
            )
            _print_json(agent)
            return 0
        if args.agent_command == "toggle":
            if args.enabled == args.disabled:
                raise CustomAgentError("provide exactly one of --enabled or --disabled")
            _print_json(store.update(args.id, enabled=bool(args.enabled)))
            return 0
        if args.agent_command == "delete":
            _print_json({"deleted": store.delete(args.id), "id": args.id})
            return 0
        _print_json(store.export(Path(args.output)))
        return 0
    except CustomAgentError as exc:
        raise SystemExit(str(exc))


def _skill_lab(args: argparse.Namespace) -> SkillLab:
    return SkillLab(
        registry_path=Path(args.registry_path) if getattr(args, "registry_path", "") else None,
        usage_path=Path(args.usage_path) if getattr(args, "usage_path", "") else None,
        eval_root=Path(args.eval_root) if getattr(args, "eval_root", "") else None,
        ledger_path=Path(args.ledger) if getattr(args, "ledger", "") else None,
        policy_path=Path(args.policy_path) if getattr(args, "policy_path", "") else None,
        versions_path=Path(args.versions_path) if getattr(args, "versions_path", "") else None,
    )


def _cmd_skill_usage(args: argparse.Namespace) -> int:
    lab = _skill_lab(args)
    try:
        if args.usage_command == "record":
            checks = []
            for raw in args.check or []:
                if "=" not in raw:
                    raise SkillLabError("check must be name=status: " + raw)
                key, value = raw.split("=", 1)
                checks.append({"id": key.strip(), "status": value.strip()})
            _print_json(lab.record_usage(
                skill_id=args.skill_id,
                status=args.status,
                task_id=args.task_id,
                checks=checks,
                artifact_ref=args.artifact_ref,
                note=args.note,
            ))
            return 0
        if args.usage_command == "summary":
            _print_json(lab.usage.summary())
            return 0
        _print_json({"entries": lab.usage.list(skill_id=args.skill_id, limit=args.limit)})
        return 0
    except SkillLabError as exc:
        raise SystemExit(str(exc))


def _cmd_skill_eval(args: argparse.Namespace) -> int:
    lab = _skill_lab(args)
    try:
        report = lab.evaluate(
            args.skill_id, args.split, version=args.version or None
        )
        _print_json(report.to_dict())
        return 0 if report.status in ("pass", "not_executable") else 1
    except SkillLabError as exc:
        raise SystemExit(str(exc))


def _cmd_skill_version(args: argparse.Namespace) -> int:
    lab = _skill_lab(args)
    try:
        if args.version_command == "list":
            _print_json(lab.versions.snapshot())
            return 0
        if args.version_command == "activate":
            _print_json(lab.activate(
                args.skill_id,
                args.version,
                Path(args.eval_report),
                args.human_reason,
            ))
            return 0
        if args.version_command == "rollback":
            _print_json(lab.rollback(args.skill_id, args.human_reason))
            return 0
        raise SkillLabError("unknown version command")
    except SkillLabError as exc:
        raise SystemExit(str(exc))


def _cmd_skill_propose(args: argparse.Namespace) -> int:
    lab = _skill_lab(args)
    try:
        _print_json(lab.propose(
            skill_id=args.skill_id,
            patch=args.patch,
            rationale=args.rationale,
            predicted_effect=args.predicted,
            dry_run_ref=args.dry_run_ref,
            observation=args.observation,
        ))
        return 0
    except SkillLabError as exc:
        raise SystemExit(str(exc))


def _cmd_skill_lint(args: argparse.Namespace) -> int:
    from .skill_lint import lint_skill_directory

    try:
        result = lint_skill_directory(Path(args.path))
    except ValueError as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0 if result["status"] != "invalid" else 1


def _cmd_skill_route(args: argparse.Namespace) -> int:
    from .skill_packs import find_venue, scan_pack

    try:
        route = find_venue(Path(args.root), args.venue)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    best = route.get("best") or {}
    if args.with_checklist and best.get("pack_exists"):
        try:
            route["scan"] = scan_pack(
                Path(best["pack_root"]), stage=args.stage, max_items=args.max_items
            )
        except (OSError, ValueError) as exc:
            raise SystemExit(str(exc))
    _print_json(route)
    return 0 if best else 1


def _cmd_skill_coverage(args: argparse.Namespace) -> int:
    from .skill_packs import STAGE_PROFILES, coverage_report, scan_pack

    profile = getattr(args, "profile", "") or ""
    if profile and args.stage:
        raise SystemExit("choose --stage or --profile, not both")
    stages = list(STAGE_PROFILES.get(profile, ()))
    from .pack_audit import resolve_pack_dir, route_for_venue

    try:
        resolved = resolve_pack_dir(args.pack, args.pack_root or "", args.venue or "")
    except ValueError as exc:
        raise SystemExit(str(exc))
    if not resolved:
        raise SystemExit("pass --pack, or --pack-root with --venue to route to one")
    try:
        pack = scan_pack(
            Path(resolved),
            stage=args.stage,
            max_items=args.max_items,
            stages=stages,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    route = route_for_venue(args.pack_root or "", args.venue or "")
    try:
        from .pack_audit import coverage_input

        source_text, bundle_fields = coverage_input(Path(args.file).expanduser())
    except (OSError, ValueError) as exc:
        raise SystemExit("coverage input is not readable: %s" % exc)
    result = coverage_report(
        pack["checklist"], source_text, stage=args.stage, stages=stages,
        artifact=bundle_fields.get("artifact_base"),
    )
    result.update(bundle_fields)
    result["profile"] = profile
    result["pack"] = pack["pack"]
    result["input"] = str(Path(args.file).expanduser().resolve())
    result["license"] = pack["license"]
    result["route"] = (route or {}).get("best") or {}
    result["route_confidence"] = (route or {}).get("confidence") or ""
    if route and route.get("confidence") == "low":
        result["warnings"] = (result.get("warnings") or []) + [
            "low-confidence route to %s; verify the pack directory by hand before trusting "
            "these counts" % (route.get("best") or {}).get("pack_dir", "")
        ]
    result["pack_scope"] = {
        "pack": pack["pack"],
        "checklist_items": len(pack["checklist"]),
        "checklist_total": pack["checklist_total"],
        "max_items": args.max_items,
        "limit_applied": pack["limit_applied"],
        "truncated": pack["truncated"],
        "warnings": pack["warnings"],
    }
    if pack["truncated"]:
        result["boundary"] += (
            " this score uses only the first %d of %d pack items, so it is a partial "
            "rubric: narrow it with --stage or --profile rather than reading the misses "
            "as the whole requirement set"
            % (len(pack["checklist"]), pack["checklist_total"])
        )
    if args.output:
        from .storage import write_json_atomic

        path = Path(args.output)
        write_json_atomic(path, result)
        result["output"] = str(path.resolve())
    _print_json(result)
    return 0


def _cmd_mandate_status(args: argparse.Namespace) -> int:
    from .mandate import build_mandate_status
    from .storage import write_json_atomic

    try:
        result = build_mandate_status(Path(args.project), max_runs=args.max_runs)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    if args.output:
        path = Path(args.output)
        write_json_atomic(path, result)
        result["output"] = str(path.resolve())
    _print_json(result)
    return 0 if result["status"] != "stopped" else 1


def _cmd_skill_pack(args: argparse.Namespace) -> int:
    from .skill_packs import SCHEMA, STAGES, scan_pack
    from .storage import write_json_atomic

    try:
        result = scan_pack(Path(args.path), stage=args.stage, max_items=args.max_items)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    if args.output:
        path = Path(args.output)
        write_json_atomic(path, result)
        result["output"] = str(path.resolve())
    _print_json(result)
    return 0


def _cmd_skill_journal_verify(args: argparse.Namespace) -> int:
    from .journal_skill_audit import verify_journal_profiles

    try:
        result = verify_journal_profiles(
            Path(args.pack_root),
            Path(args.profiles) if args.profiles else None,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0 if result["status"] == "verified" else 1


def _cmd_skill_invoke(args: argparse.Namespace) -> int:
    from .external_skills import ExternalSkillError, invoke_external_skill

    if bool(args.input) == bool(args.input_file):
        raise SystemExit("provide exactly one of --input or --input-file")
    if args.input_file:
        input_text = Path(args.input_file).read_text(encoding="utf-8")
    else:
        input_text = args.input
    context = ""
    if args.context_file:
        context = Path(args.context_file).read_text(encoding="utf-8")
    try:
        result = invoke_external_skill(
            skill_id=args.skill_id,
            input_text=input_text,
            profile_id=args.profile,
            context=context,
            registry_path=args.registry_path,
            usage_path=args.usage_path,
            store_path=args.store,
            output_path=args.output or None,
            trusted_scripts=args.trusted_scripts,
            workdir=args.workdir or None,
            timeout=args.timeout,
            script_args=args.script_arg,
            distill_on_success=args.distill_on_success,
            distill_license=args.distill_license,
            distill_reason=args.distill_reason,
            distill_source_url=args.distill_source_url,
            library_dir=args.library_dir,
        )
    except (ExternalSkillError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    if result.get("distillation", {}).get("status") == "error":
        raise SystemExit(2)
    return 0


def _cmd_skill_distill(args: argparse.Namespace) -> int:
    from .skill_distill import SkillDistillError, distill_skill

    try:
        result = distill_skill(
            skill_id=args.skill_id,
            library_dir=Path(args.library_dir),
            registry_path=Path(args.registry_path),
            license=args.license,
            human_reason=args.human_reason,
            source_url=args.source_url,
        )
    except (SkillDistillError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_revision_ab(args: argparse.Namespace) -> int:
    from .ab_review import ABReviewError, render_ab_markdown, run_ab_review
    from .revision import _gateway_model
    from .storage import write_json_atomic

    try:
        model = _gateway_model(args.profile, args.store or None)
        result = run_ab_review(
            Path(args.original),
            Path(args.revised),
            model,
            sections=list(args.section or []),
            rounds=args.rounds,
        )
    except (ABReviewError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output / "ab-review.json", result)
    (output / "ab-review.md").write_text(render_ab_markdown(result), encoding="utf-8")
    _print_json(result)
    return 0


def _cmd_revision(args: argparse.Namespace) -> int:
    from .revision import RevisionError, _gateway_model, inspect_revision, load_review_comments, run_revision
    from .revision_plan import RevisionPlanError, build_revision_plan, write_revision_plan

    data_paths = [Path(item) for item in (args.data or [])]
    metrics_path = Path(args.metrics) if args.metrics else None
    figures_path = Path(args.figures) if args.figures else None
    try:
        if args.revision_command == "plan":
            model = _gateway_model(args.profile, args.store or None)
            plan = build_revision_plan(
                Path(args.draft),
                model,
                sections=list(args.section or []),
                goal=args.goal,
                review_comments=(
                    load_review_comments(Path(args.review_file)) if args.review_file else None
                ),
            )
            files = write_revision_plan(plan, Path(args.output_dir))
            result = {**plan, "files": files}
        elif args.revision_command == "inspect":
            result = inspect_revision(
                draft_path=Path(args.draft),
                output_dir=Path(args.output_dir),
                data_paths=data_paths,
                metrics_path=metrics_path,
                figures_path=figures_path,
                venue=args.venue,
            )
        else:
            formats = list(args.format or [])
            if not formats:
                formats = ["md", "tex", "docx", "pdf"]
            result = run_revision(
                draft_path=Path(args.draft),
                output_dir=Path(args.output_dir),
                data_paths=data_paths,
                metrics_path=metrics_path,
                figures_path=figures_path,
                venue=args.venue,
                profile_id=args.profile,
                store_path=args.store or None,
                sections=list(args.section or []),
                formats=formats,
                goal=args.goal,
                review_comments=load_review_comments(Path(args.review_file)) if args.review_file else None,
                plan=json.loads(Path(args.plan_file).read_text(encoding="utf-8")) if args.plan_file else None,
                auto_plan=getattr(args, "auto_plan", False),
            )
    except (RevisionError, RevisionPlanError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    if args.revision_command == "run" and result.get("status") == "blocked":
        return 1
    return 0


def _cmd_literature_synthesize(args: argparse.Namespace) -> int:
    from .literature_synthesis import SynthesisError, synthesize_literature

    try:
        result = synthesize_literature(
            Path(args.project),
            args.run_id,
            max_themes=args.max_themes,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except (SynthesisError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_conference_fetch(args: argparse.Namespace) -> int:
    from .adapters.conference_fetcher import ConferenceFetchError, fetch_top_conference_corpus

    venues = [item.strip() for item in str(args.venues or "").split(",") if item.strip()]
    years = []
    for item in str(args.years or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            years.append(int(item))
        except ValueError:
            raise SystemExit("invalid year: " + item)
    try:
        result = fetch_top_conference_corpus(
            target_dir=Path(args.target_dir),
            venues=venues,
            years=years,
            topic=args.topic,
            max_papers=args.max_papers,
            max_per_venue=args.max_per_venue,
            allow_network=args.allow_network,
        )
    except (ConferenceFetchError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_loop_status(args: argparse.Namespace) -> int:
    from .loop_ledger import build_loop_ledger

    try:
        result = build_loop_ledger(
            Path(args.project),
            args.run_id,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_verdicts_collect(args: argparse.Namespace) -> int:
    from .verdict_ledger import collect, write_ledger

    try:
        ledger = collect(Path(args.project), limit=args.limit)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    if args.output:
        _print_json(write_ledger(Path(args.output), ledger))
        return 0
    _print_json(ledger)
    return 0


def _cmd_verdicts_show(args: argparse.Namespace) -> int:
    from .storage import read_json

    try:
        _print_json(read_json(args.ledger))
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    return 0


def _cmd_feedback_run(args: argparse.Namespace) -> int:
    from .feedback import registered_loops, run_feedback

    loops = [item.strip() for item in (args.loops or "").split(",") if item.strip()]
    try:
        result = run_feedback(Path(args.project), loops=loops or None, limit=args.limit)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_feedback_list(args: argparse.Namespace) -> int:
    from .feedback import _LOOPS

    _print_json({"loops": [{"id": loop_id, "propose": "observe->propose->gate->apply->record"} for loop_id in sorted(_LOOPS)]})
    return 0


def _cmd_experiment_closure(args: argparse.Namespace) -> int:
    from .experiment_closure import (
        ExperimentClosureError,
        build_experiment_lineage,
        check_experiment_closure,
        sign_experiment_closure,
        verify_experiment_lineage,
    )
    from .signers import SignerError, SignerStore

    try:
        if args.experiment_command == "closure":
            result = check_experiment_closure(
                Path(args.project),
                args.experiment_id,
                manuscript=Path(args.manuscript) if args.manuscript else None,
                output_dir=Path(args.output_dir) if args.output_dir else None,
            )
            blocked = result.get("status") != "ready_for_human_signature"
        elif args.experiment_command == "sign":
            store = None
            if args.signer_id:
                store = SignerStore(Path(args.signer_store) if args.signer_store else None)
            result = sign_experiment_closure(
                Path(args.project),
                args.experiment_id,
                Path(args.report),
                args.human_reason,
                signer_store=store,
                signer_id=args.signer_id,
                output_dir=Path(args.output_dir) if args.output_dir else None,
            )
            blocked = False
        else:
            if args.verify:
                result = verify_experiment_lineage(
                    Path(args.project),
                    args.experiment_id,
                    lineage_path=Path(args.lineage) if args.lineage else None,
                )
                blocked = result.get("status") != "fresh"
            else:
                result = build_experiment_lineage(
                    Path(args.project),
                    args.experiment_id,
                    output_dir=Path(args.output_dir) if args.output_dir else None,
                )
                blocked = False
    except (ExperimentClosureError, SignerError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 1 if blocked else 0


def _cmd_experiment_local(args: argparse.Namespace) -> int:
    from .local_exec import (
        approve_local_experiment,
        init_local_experiment,
        ingest_local_experiment,
        run_local_experiment,
    )
    project = Path(args.project)
    if args.experiment_command == "local-init":
        result = init_local_experiment(
            project, args.experiment_id, args.command,
            cwd=args.cwd, env_prefix=args.env_prefix,
            expected_outputs=args.expect, timeout_sec=args.timeout,
        )
    elif args.experiment_command == "local-approve":
        result = approve_local_experiment(project, args.experiment_id, args.human_reason)
    elif args.experiment_command == "local-run":
        result = run_local_experiment(
            project, args.experiment_id,
            allow_execute=bool(args.allow_execute), timeout_sec=args.timeout,
        )
    else:
        result = ingest_local_experiment(project, args.experiment_id)
    _print_json(result)
    if args.experiment_command == "local-run" and result.get("status") != "completed":
        return 1
    if args.experiment_command == "local-ingest" and result.get("status") != "verified":
        return 1
    return 0


def _cmd_experiment_lifecycle(args: argparse.Namespace) -> int:
    from .experiment_runner import (
        ExperimentExecutionError,
        approve_experiment,
        execute_experiment,
        ingest_experiment,
        sign_experiment_claim,
    )

    try:
        if args.experiment_command == "approve":
            result = approve_experiment(
                Path(args.project), args.experiment_id, args.human_reason,
                timeout_sec=args.timeout, ridge_alpha=args.ridge_alpha,
            )
        elif args.experiment_command == "run":
            result = execute_experiment(
                Path(args.project), args.experiment_id,
                allow_execute=args.allow_execute, python=args.python,
                timeout_sec=args.timeout, dry_run=args.dry_run,
                ridge_alpha=args.ridge_alpha,
            )
        elif args.experiment_command == "ingest":
            result = ingest_experiment(Path(args.project), args.experiment_id)
        else:
            result = sign_experiment_claim(
                Path(args.project), args.experiment_id,
                args.statement, args.human_reason, list(args.assertion or []),
            )
    except (ExperimentExecutionError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    if args.experiment_command == "run" and result.get("status") != "completed":
        return 1
    if args.experiment_command == "ingest" and result.get("status") != "verified":
        return 1
    return 0


def _cmd_experiment_figure(args: argparse.Namespace) -> int:
    from .experiment_figures import (
        ExperimentFigureError,
        build_result_figure,
        result_figure_manifest_path,
        verify_result_figure,
    )

    project = Path(args.project).expanduser()
    try:
        if args.verify:
            manifest = (
                Path(args.manifest)
                if args.manifest
                else result_figure_manifest_path(project, args.experiment_id)
            )
            result = verify_result_figure(manifest, project=project)
        else:
            result = build_result_figure(
                project,
                args.experiment_id,
                output_dir=Path(args.output_dir) if args.output_dir else None,
            )
    except (ExperimentFigureError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0 if result.get("status") != "stale" else 1


def _cmd_experiment_status(args: argparse.Namespace) -> int:
    from .experiment_runner import ExperimentExecutionError, experiment_status

    try:
        result = experiment_status(Path(args.project), args.experiment_id)
    except (ExperimentExecutionError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_experiment_consistency(args: argparse.Namespace) -> int:
    from .experiment_consistency import (
        ExperimentConsistencyError,
        build_consistency_registry,
    )
    from .project import ProjectError, project_output_path
    from .storage import write_json_atomic

    try:
        result = build_consistency_registry(Path(args.project), args.experiment_id)
        output = project_output_path(Path(args.project), args.output, "output")
        write_json_atomic(output, result["registry"])
    except (ExperimentConsistencyError, ProjectError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    result["output"] = str(output)
    _print_json(result)
    return 0


def _cmd_experiment_preflight(args: argparse.Namespace) -> int:
    from .experiment_runner import ExperimentExecutionError, preflight_experiment

    try:
        result = preflight_experiment(
            Path(args.project),
            args.experiment_id,
            python=args.python,
            timeout_sec=args.timeout,
        )
    except (ExperimentExecutionError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0 if result.get("status") == "passed" else 1


def _cmd_experiment_sweep(args: argparse.Namespace) -> int:
    from .experiment_runner import (
        ExperimentExecutionError,
        approve_sweep,
        execute_sweep,
        ingest_sweep,
        sweep_status,
    )

    project = Path(args.project).expanduser()
    try:
        if args.experiment_command == "sweep-approve":
            result = approve_sweep(
                project, args.experiment_id, args.human_reason, timeout_sec=args.timeout
            )
        elif args.experiment_command == "sweep-run":
            result = execute_sweep(
                project,
                args.experiment_id,
                allow_execute=args.allow_execute,
                python=args.python,
                timeout_sec=args.timeout,
                dry_run=args.dry_run,
            )
        elif args.experiment_command == "sweep-ingest":
            result = ingest_sweep(project, args.experiment_id)
        else:
            result = sweep_status(project, args.experiment_id)
    except (ExperimentExecutionError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    if result.get("status") in ("blocked", "failed", "timeout"):
        return 1
    return 0


def _cmd_experiment_scaffold(args: argparse.Namespace) -> int:
    from .experiment_codegen import ExperimentCodegenError, generate_experiment_code

    try:
        result = generate_experiment_code(
            Path(args.project),
            args.run_id,
            data_path=args.data,
            target=args.target,
            features=[item.strip() for item in args.features.split(",") if item.strip()],
            task=args.task,
            methods=[item.strip() for item in args.methods.split(",") if item.strip()],
            metric=args.metric,
            experiment_id=args.experiment_id,
            test_size=args.test_size,
            seeds=args.seeds,
            cv_folds=args.cv_folds,
            alpha_grid=[
                float(item.strip())
                for item in str(args.alpha_grid or "").split(",")
                if item.strip()
            ],
            output_root=Path(args.output_root) if args.output_root else None,
        )
    except (ExperimentCodegenError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _critic_models(args: argparse.Namespace) -> Dict[str, object]:
    """Staff the critic bench: --critic role=profile wins, else --independent takes the panel."""
    from .adapters.research_models import model_for_profile
    from .innovation_review import REVIEW_ROLES
    from .model_catalog import critic_panel

    assigned: Dict[str, str] = {}
    for item in args.critic or []:
        role, _, profile = str(item).partition("=")
        role, profile = role.strip(), profile.strip()
        if role not in REVIEW_ROLES or not profile:
            raise SystemExit(
                "--critic expects role=profile_id with role in %s" % ", ".join(REVIEW_ROLES)
            )
        if role in assigned:
            raise SystemExit("--critic %s given twice" % role)
        assigned[role] = profile
    if args.independent and not assigned:
        panel = critic_panel()
        if not panel["panel_possible"]:
            raise SystemExit(
                "no independent bench is available: %d distinct provider+model supply for %d "
                "critic roles (missing %d). Configure another provider or bind a host profile "
                "that names a different model.\npanel: %s"
                % (
                    panel["distinct_supplies"],
                    len(REVIEW_ROLES),
                    panel["missing_supplies"],
                    json.dumps(panel["supplies"], ensure_ascii=False),
                )
            )
        assigned = dict(panel["suggested"])
    models = {}
    for role, profile in assigned.items():
        port, _note = model_for_profile(
            profile, module="idea", purpose="innovation critic: %s" % role, strict=True
        )
        models[role] = port
    if assigned and len(models) < len(REVIEW_ROLES):
        unbound = sorted(set(REVIEW_ROLES) - set(models))
        print(
            "warning: critic role(s) %s fall back to the proposer supply, so the panel stays "
            "partly single-author" % ", ".join(unbound),
            file=sys.stderr,
        )
    return models


def _cmd_innovation_review(args: argparse.Namespace) -> int:
    from .innovation_review import InnovationReviewError, run_innovation_review

    try:
        result = run_innovation_review(
            Path(args.project),
            args.run_id,
            topic=args.topic,
            direction=args.direction,
            rounds=args.rounds,
            max_ideas=args.max_ideas,
            threshold=args.threshold,
            critic_models=_critic_models(args),
            output_dir=Path(args.output_dir) if args.output_dir else None,
            use_guidance=not bool(getattr(args, "no_guidance", False)),
            propose_only=bool(getattr(args, "propose_only", False)),
            language=str(getattr(args, "language", "zh") or "zh"),
            prior_art_corpus=(
                Path(args.prior_art_corpus) if getattr(args, "prior_art_corpus", "") else None
            ),
            prior_art_limit=int(getattr(args, "prior_art_limit", 6) or 6),
        )
    except (InnovationReviewError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    independence = result.get("independence") or {}
    if not independence.get("admission_eligible"):
        print(
            "note: this review is not an independent panel (%s); scores are a process signal"
            % independence.get("kind"),
            file=sys.stderr,
        )
    _print_json(result)
    return 0


def _cmd_manuscript_draft(args: argparse.Namespace) -> int:
    from .manuscript_writer import ManuscriptWriterError, generate_manuscript

    try:
        result = generate_manuscript(
            Path(args.project), args.run_id, Path(args.output)
        )
    except (ManuscriptWriterError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    result.pop("pack", None)
    result.pop("innovation", None)
    _print_json(result)
    return 0 if result.get("status") == "generated" else 1


def _cmd_empirical(args: argparse.Namespace) -> int:
    from .empirical_loop import EmpiricalLoopError, check_empirical_loop, run_empirical_paper
    from .manuscript_review import default_review_model
    from .manuscript_writer import default_writer_model
    from .project import project_output_path

    project = Path(args.project).expanduser()
    empirical_support_judge = None
    empirical_judge_id = ""
    if getattr(args, "judge_profile", ""):
        empirical_support_judge, _note = _resolve_support_judge(
            "profile:" + str(args.judge_profile)
        )
        empirical_judge_id = "profile:" + str(args.judge_profile)
    try:
        if args.empirical_command == "check":
            result = check_empirical_loop(project, args.run_id, args.experiment_id)
        else:
            if args.offline_draft and args.review_rounds > 0:
                raise SystemExit("--offline-draft requires --review-rounds 0")
            output = project_output_path(project.resolve(), args.output, "draft")
            result = run_empirical_paper(
                project,
                args.run_id,
                args.experiment_id,
                output,
                model=default_writer_model(),
                review_model=(
                    default_review_model()
                    if args.review_rounds > 0 or args.semantic_support
                    else None
                ),
                review_rounds=args.review_rounds,
                threshold=args.threshold,
                language=args.language,
                venue=args.venue,
                max_sources=args.max_sources,
                max_spans_per_source=args.max_spans_per_source,
                repair_attempts=args.repair_attempts,
                method_scene=args.method_scene,
                method_template=args.method_template,
                semantic_support=args.semantic_support,
                strict_support=args.strict_support,
                support_votes=args.support_votes,
                support_judge=empirical_support_judge,
                judge_model_id=empirical_judge_id,
                ab_check=args.ab_check,
                ab_sections=list(args.ab_sections or []),
                offline_draft=bool(args.offline_draft),
                external_lint=bool(args.external_lint),
                external_skill_root=str(args.external_skill_root or ""),
                external_consistency=bool(args.external_consistency),
                external_consistency_registry=str(
                    args.external_consistency_registry or ""
                ),
                external_consistency_auto=bool(args.external_consistency_auto),
            )
    except (EmpiricalLoopError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0 if result.get("status") in ("ready_for_writing", "ready_for_human_review") else 1


def _cmd_workspace_preflight(args: argparse.Namespace) -> int:
    from .preflight import build_preflight

    report = build_preflight()
    if args.output:
        from .storage import write_json_atomic

        write_json_atomic(Path(args.output), report)
    _print_json(report)
    return 0 if report["status"] == "fresh" else 3


def _cmd_study_baseline(args: argparse.Namespace) -> int:
    from .baseline_lab import compare_with_study, run_baseline, to_markdown

    seeds = [int(item) for item in str(args.seeds).split(",") if item.strip()]
    folds = args.folds if args.folds > 0 else None
    markdown = ""
    try:
        if args.table_from:
            paths = [item for item in str(args.table_from).split(",") if item.strip()]
            reports = [
                json.loads(Path(item).expanduser().read_text(encoding="utf-8")) for item in paths
            ]
            result = to_markdown(reports, title=args.title)
            markdown = result["markdown"]
        elif args.study:
            study = json.loads(Path(args.study).expanduser().read_text(encoding="utf-8"))
            result = compare_with_study(study, seeds=seeds or None, folds=folds)
            if args.markdown:
                markdown = to_markdown([result], title=args.title)["markdown"]
        else:
            datasets = [item for item in str(args.dataset).split(",") if item.strip()]
            result = run_baseline(datasets, seeds or [1, 2, 3], folds=folds or 5)
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(str(exc))
    if args.output:
        from .storage import write_json_atomic

        write_json_atomic(Path(args.output).expanduser(), result)
    if args.markdown:
        handle = Path(args.markdown).expanduser()
        with open(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(markdown)
        print("tuned baseline table: %s" % handle.resolve())
    _print_json(result)
    return 0


def _cmd_manuscript_provenance(args: argparse.Namespace) -> int:
    from .number_provenance import provenance_for_draft

    try:
        result = provenance_for_draft(
            Path(args.draft), Path(args.corpus), max_files=args.max_files
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    if args.output:
        from .storage import write_json_atomic

        write_json_atomic(Path(args.output), result)
    _print_json(result)
    return 0


def _cmd_manuscript_review(args: argparse.Namespace) -> int:
    from .adapters.support_judge import support_judge_from_model
    from .manuscript_review import ManuscriptReviewError, review_model as resolve_review_model, run_manuscript_review
    from .models.types import ModelTurnPending

    try:
        review_model = resolve_review_model()
        semantic = bool(
            getattr(args, "semantic_support", False)
            or getattr(args, "strict_support", False)
            or getattr(args, "judge_profile", "")
        )
        judge_profile = str(getattr(args, "judge_profile", "") or "").strip()
        if semantic and judge_profile:
            support_judge, _note = _resolve_support_judge("profile:" + judge_profile)
            judge_model_id = "profile:" + judge_profile
        else:
            support_judge = (
                support_judge_from_model(
                    review_model, strict=bool(getattr(args, "strict_support", False))
                )
                if semantic
                else None
            )
            judge_model_id = getattr(
                review_model, "model_id", type(review_model).__name__
            )
        result = run_manuscript_review(
            Path(args.project),
            args.run_id,
            Path(args.draft),
            rounds=args.rounds,
            threshold=args.threshold,
            model=review_model,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            support_judge=support_judge,
            strict_support=bool(getattr(args, "strict_support", False)),
            judge_model_id=judge_model_id,
            support_votes=int(getattr(args, "support_votes", 1) or 1),
            revision_mode=getattr(args, "revision_mode", "full"),
            ab_reviewer=review_model if getattr(args, "ab_check", False) else None,
            ab_sections=list(getattr(args, "ab_sections", []) or []),
        )
    except ModelTurnPending as exc:
        raise SystemExit(str(exc))
    except (ManuscriptReviewError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_writing(args: argparse.Namespace) -> int:
    from .project import run_dir
    from .storage import read_json, write_json_atomic
    from .writing_audit import WritingAuditError, write_audit
    from .writing_pack import build_writing_pack, render_writing_pack

    project = Path(args.project).expanduser()
    try:
        if args.writing_command == "pack":
            pack = build_writing_pack(
                project,
                args.run_id,
                language=args.language,
                venue=args.venue,
                max_sources=args.max_sources,
                max_spans_per_source=args.max_spans_per_source,
                experiment_id=args.experiment_id,
            )
            target = run_dir(project.resolve(), args.run_id)
            write_json_atomic(target / "writing-pack.json", pack)
            with open(str(target / "writing-pack.md"), "w", encoding="utf-8", newline="\n") as handle:
                handle.write(render_writing_pack(pack))
            result = {**pack, "files": {"json": str(target / "writing-pack.json"), "markdown": str(target / "writing-pack.md")}}
        elif args.writing_command == "support-gold-template":
            from .project import project_file
            from .support_gold import (
                SupportGoldError,
                build_gold_templates,
                panel_from_ledger,
                render_gold_template_instructions,
            )

            ledger_value = str(getattr(args, "ledger", "") or "").strip()
            panel_value = str(getattr(args, "panel", "") or "").strip()
            if ledger_value:
                panel_path = project_file(project, ledger_value, "ledger")
                try:
                    ledger = json.loads(panel_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise SystemExit("ledger is unreadable: " + str(exc))
                try:
                    panel = panel_from_ledger(ledger, source=str(panel_path))
                except SupportGoldError as exc:
                    raise SystemExit(str(exc))
            else:
                panel_path = project_file(
                    project,
                    panel_value or "runs/%s/support-panel.json" % args.run_id,
                    "panel",
                )
                try:
                    panel = json.loads(panel_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise SystemExit("panel is unreadable: " + str(exc))
            annotators = list(getattr(args, "annotators", None) or []) or ["A", "B"]
            try:
                result = build_gold_templates(
                    panel, annotators, source=str(panel_path)
                )
            except SupportGoldError as exc:
                raise SystemExit(str(exc))
            output = (
                Path(args.output_dir)
                if getattr(args, "output_dir", "")
                else run_dir(project.resolve(), args.run_id)
            )
            output.mkdir(parents=True, exist_ok=True)
            files = {}
            for template in result["templates"]:
                safe = re.sub(r"[^A-Za-z0-9_-]+", "_", template["annotator"]) or "annotator"
                path = output / ("support-gold-annotations-%s.json" % safe)
                write_json_atomic(path, template)
                files[template["annotator"]] = str(path)
            write_json_atomic(output / "support-gold-template.json", result)
            with open(
                str(output / "support-gold-template.md"),
                "w",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                handle.write(render_gold_template_instructions(result))
            result["files"] = files
            _print_json(result)
            return 0
        elif args.writing_command == "support-gold":
            from .project import project_file
            from .revision_io import sha256_file
            from .support_gold import (
                SupportGoldError,
                evaluate_support_gold,
                load_annotations,
                panel_from_ledger,
                render_support_gold,
            )

            files = list(getattr(args, "annotator_files", None) or [])
            if len(files) < 2:
                raise SystemExit("support-gold requires at least two --annotator-file")
            draft_path = None
            draft_sha = ""
            if getattr(args, "draft", ""):
                draft_path = project_file(project, args.draft, "draft")
                draft_sha = sha256_file(draft_path)
            panel = None
            ledger_value = str(getattr(args, "ledger", "") or "").strip()
            if ledger_value:
                ledger_path = project_file(project, ledger_value, "ledger")
                try:
                    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise SystemExit("ledger is unreadable: " + str(exc))
                try:
                    panel = panel_from_ledger(ledger, source=str(ledger_path))
                except SupportGoldError as exc:
                    raise SystemExit(str(exc))
            elif getattr(args, "panel", ""):
                panel_path = project_file(project, args.panel, "panel")
                try:
                    panel = json.loads(panel_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise SystemExit("panel is unreadable: " + str(exc))
                if not isinstance(panel, dict):
                    raise SystemExit("panel must be a JSON object")
            try:
                annotations = [
                    load_annotations(project_file(project, value, "annotation"))
                    for value in files
                ]
                result = evaluate_support_gold(
                    annotations, panel=panel, draft_sha256=draft_sha
                )
            except SupportGoldError as exc:
                raise SystemExit(str(exc))
            if draft_path is not None:
                result["draft"] = str(draft_path)
            output = (
                Path(args.output_dir)
                if getattr(args, "output_dir", "")
                else run_dir(project.resolve(), args.run_id)
            )
            output.mkdir(parents=True, exist_ok=True)
            write_json_atomic(output / "support-gold.json", result)
            with open(
                str(output / "support-gold.md"), "w", encoding="utf-8", newline="\n"
            ) as handle:
                handle.write(render_support_gold(result))
            result["files"] = {
                "json": str(output / "support-gold.json"),
                "markdown": str(output / "support-gold.md"),
            }
            _print_json(result)
            return 0 if result.get("status") == "complete" else 1
        elif args.writing_command == "bind":
            from .project import project_file, project_output_path
            from .writing_pack import bind_text_to_pack, load_writing_pack

            draft_path = project_file(project, args.draft, "draft")
            output_path = project_output_path(project, args.output, "output")
            if output_path.resolve() == draft_path.resolve():
                raise SystemExit("output must be a new draft, not the source draft")
            pack = load_writing_pack(project.resolve(), args.run_id)
            if pack is None:
                raise SystemExit("writing pack missing; run writing pack first")
            try:
                result = bind_text_to_pack(
                    draft_path.read_text(encoding="utf-8"), pack
                )
            except (OSError, ValueError) as exc:
                raise SystemExit(str(exc))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(
                str(output_path), "w", encoding="utf-8", newline="\n"
            ) as handle:
                handle.write(result["text"])
            _print_json(
                {
                    "pack_id": str(pack.get("pack_id") or ""),
                    "pack_sha256": str(pack.get("pack_sha256") or ""),
                    "marker": result["marker"],
                    "source_draft": str(draft_path),
                    "new_draft": str(output_path),
                    "refs": result["refs"],
                    "resolved_refs": result["resolved_refs"],
                    "unresolved_refs": result["unresolved_refs"],
                    "boundary": (
                        "Binding only attaches the writing-pack marker and preserves "
                        "the body; no evidence or signature."
                    ),
                }
            )
            return 0
        elif args.writing_command == "external-claim-audit":
            from .external_claim_audit import run_claim_audit
            from .external_writing_gate import ExternalWritingGateError
            from .project import run_dir

            target = run_dir(project.resolve(), args.run_id)
            registry = read_json(target / "claim-registry.json")
            literature = read_json(target / "literature.json")
            if not isinstance(registry, dict) or not registry.get("entries"):
                raise SystemExit("claim-registry.json is missing or has no entries")
            if not isinstance(literature, dict) or not literature.get("spans"):
                raise SystemExit("literature.json with spans is required")
            try:
                result = run_claim_audit(
                    registry,
                    literature,
                    Path(args.skill_root) if args.skill_root else None,
                )
            except ExternalWritingGateError as exc:
                raise SystemExit(str(exc))
            if args.output:
                output = project_output_path(project, args.output, "output")
                write_json_atomic(output, result)
                result["output"] = str(output)
            _print_json(result)
            return 0 if result.get("status") in ("ready", "attention") else 1
        elif args.writing_command == "external-lint":
            from .external_writing_gate import (
                ExternalWritingGateError,
                run_writing_lint,
            )
            from .project import project_file

            draft = project_file(project, args.draft, "draft")
            try:
                result = run_writing_lint(
                    draft,
                    Path(args.skill_root) if args.skill_root else None,
                )
            except ExternalWritingGateError as exc:
                raise SystemExit(str(exc))
            if args.output:
                output = project_output_path(project, args.output, "output")
                write_json_atomic(output, result)
                result["output"] = str(output)
            _print_json(result)
            return 0 if result.get("status") in ("ready", "attention") else 1
        elif args.writing_command == "external-consistency":
            from .external_consistency_gate import (
                ExternalConsistencyGateError,
                run_consistency_check,
            )
            from .project import project_file

            registry = project_file(project, args.registry, "consistency registry")
            try:
                result = run_consistency_check(
                    registry,
                    Path(args.skill_root) if args.skill_root else None,
                )
            except ExternalConsistencyGateError as exc:
                raise SystemExit(str(exc))
            if args.output:
                output = project_output_path(project, args.output, "output")
                write_json_atomic(output, result)
                result["output"] = str(output)
            _print_json(result)
            return 0 if result.get("status") in ("ready", "attention") else 1
        elif args.writing_command == "support-panel":
            from .support_panel import SupportPanelError, audit_support_panel
            from .writing_pack import load_writing_pack

            pack = load_writing_pack(project, args.run_id)
            if pack is None:
                raise SystemExit("writing pack missing; run writing pack first")
            profiles = list(
                dict.fromkeys(
                    str(value).strip()
                    for value in (getattr(args, "judge_profiles", None) or [])
                    if str(value).strip()
                )
            )
            if not profiles:
                raise SystemExit("support-panel requires at least one --judge-profile")
            if len(profiles) < 2:
                print(
                    "warning: a single judge is not an independent panel",
                    file=sys.stderr,
                )
            families = {}
            for value in getattr(args, "judge_families", None) or []:
                if "=" not in str(value):
                    raise SystemExit("--judge-family must be profile_id=family")
                family_id, family = str(value).split("=", 1)
                family_id = family_id.strip()
                family = family.strip().lower()
                if not family_id or not family:
                    raise SystemExit("--judge-family must be profile_id=family")
                families[family_id] = family
            providers = {}
            models = {}
            try:
                profile_store = GatewayStore(default_store_path())
                for profile in profiles:
                    try:
                        profile_obj = profile_store.profile(profile)
                    except Exception:
                        continue
                    provider_id = str(getattr(profile_obj, "provider_id", "") or "").strip().lower()
                    if provider_id:
                        providers[profile] = provider_id
                        if profile not in families:
                            families[profile] = provider_id
                    model_id = str(getattr(profile_obj, "model", "") or "").strip()
                    if model_id:
                        models[profile] = model_id
            except Exception:
                pass
            require_families = bool(getattr(args, "require_families", False))
            if require_families and any(profile not in families for profile in profiles):
                raise SystemExit(
                    "--require-families needs a family for every judge profile; "
                    "set --judge-family or configure the profile provider"
                )
            require_providers = bool(getattr(args, "require_providers", False))
            if require_providers and any(profile not in providers for profile in profiles):
                raise SystemExit(
                    "--require-providers needs a configured provider for every judge profile"
                )
            judges = []
            for profile_id in profiles:
                judge, note = _resolve_support_judge("profile:" + profile_id)
                if judge is None:
                    raise SystemExit(note or "judge profile not configured: " + profile_id)
                judges.append((profile_id, judge))
            target = run_dir(project.resolve(), args.run_id)
            try:
                result = audit_support_panel(
                    Path(args.draft),
                    pack,
                    judges,
                    strict=bool(getattr(args, "strict_support", False)),
                    max_items=int(getattr(args, "max_items", 80) or 80),
                    judge_votes=int(getattr(args, "support_votes", 1) or 1),
                    cache_dir=target / "support-cache",
                    refresh=bool(getattr(args, "refresh_support", False)),
                    adjudication_path=(
                        Path(args.adjudication)
                        if getattr(args, "adjudication", "")
                        else None
                    ),
                    judge_families=families,
                    require_families=require_families,
                    judge_providers=providers,
                    judge_models=models,
                    require_providers=require_providers,
                )
            except SupportPanelError as exc:
                raise SystemExit(str(exc))
            write_json_atomic(target / "support-panel.json", result)
            template_path = target / "support-adjudication-template.json"
            write_json_atomic(template_path, result["adjudication_template"])
            result["files"] = {
                "panel": str(target / "support-panel.json"),
                "adjudication_template": str(template_path),
            }
            _print_json(result)
            return 1 if result.get("status") in ("blocked", "needs_human") else 0
        else:
            target = run_dir(project.resolve(), args.run_id)
            support_judge = None
            judge_model_id = ""
            semantic = bool(
                getattr(args, "semantic", False) or getattr(args, "strict_support", False)
            )
            if semantic and not (target / "support-ledger.json").is_file():
                judge_profile = str(getattr(args, "judge_profile", "") or "").strip()
                if judge_profile:
                    support_judge, _note = _resolve_support_judge(
                        "profile:" + judge_profile
                    )
                    judge_model_id = "profile:" + judge_profile
                else:
                    from .adapters.support_judge import support_judge_from_model
                    from .manuscript_review import default_review_model

                    judge_model = default_review_model()
                    support_judge = support_judge_from_model(
                        judge_model, strict=bool(getattr(args, "strict_support", False))
                    )
                    judge_model_id = getattr(
                        judge_model, "model_id", type(judge_model).__name__
                    )
            result = write_audit(
                draft_path=Path(args.draft),
                output_dir=target,
                project=project,
                run_id=args.run_id,
                language=args.language,
                venue=args.venue,
                experiment_id=args.experiment_id,
                support_judge=support_judge,
                strict_support=bool(getattr(args, "strict_support", False)),
                judge_model_id=judge_model_id,
                strict_pack_binding=bool(getattr(args, "strict_pack_binding", False)),
                support_votes=int(getattr(args, "support_votes", 1) or 1),
                support_max_items=int(getattr(args, "support_max_items", 80) or 80),
                refresh_support=bool(getattr(args, "refresh_support", False)),
            )
    except (WritingAuditError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 1 if args.writing_command == "audit" and result.get("status") == "blocked" else 0


def _cmd_support_eval(args: argparse.Namespace) -> int:
    from .adapters.support_judge import support_judge_from_model
    from .manuscript_review import default_review_model
    from .storage import write_json_atomic
    from .support_calibration import (
        SupportCalibrationError,
        evaluate_support_cases,
        load_cases,
        render_support_calibration,
    )

    try:
        cases = load_cases(Path(args.cases) if args.cases else None)
        model = default_review_model()
        judge = support_judge_from_model(model, strict=False)
        report = evaluate_support_cases(
            cases,
            judge,
            votes=args.votes,
            model_id=getattr(model, "model_id", type(model).__name__),
        )
    except (SupportCalibrationError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    if args.output_dir:
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        write_json_atomic(output / "support-calibration.json", report)
        (output / "support-calibration.md").write_text(
            render_support_calibration(report), encoding="utf-8"
        )
    _print_json(report)
    return 0


def _cmd_figure_table(args: argparse.Namespace) -> int:
    """Render figures straight from a data table plus a spec.

    ``revision_figures.generate_figures`` could always do this, but it was only reachable
    through ``revision run``, which needs a manuscript; a measured result with nothing to
    point at stayed out of the article.  Read-only over the data, writes only into
    --output-dir, and it creates no evidence, claim or gate.
    """
    from .revision_figures import generate_figures, load_figure_specs
    from .revision_io import RevisionIOError, load_data_tables

    try:
        tables = load_data_tables([Path(item) for item in args.data])
        specs = load_figure_specs(Path(args.spec))
        if not specs:
            raise RevisionIOError("figure spec contains no figures: " + str(args.spec))
        result = generate_figures(specs, tables, Path(args.output_dir))
    except (RevisionIOError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    payload = dict(result) if isinstance(result, dict) else {"figures": result}
    # A series drawn on a varying number of seeds hides a selection effect: normalisation
    # drops exactly the runs that start at the ceiling, which are the cases the metric
    # argument is about.  The chart cannot show that, so the command has to say it.
    coverage: list = []
    for table in tables:
        if "seeds" not in table.columns:
            continue
        for spec in specs:
            series_col = str(spec.get("series") or "")
            if not series_col or series_col not in table.columns:
                continue
            groups: dict = {}
            for row in table.rows:
                name = str(row.get(series_col) or "").strip()
                raw = str(row.get("seeds") or "").strip()
                if name and raw.isdigit():
                    groups.setdefault(name, []).append(int(raw))
            for name, values in sorted(groups.items()):
                if min(values) < max(values):
                    coverage.append({
                        "table": table.name,
                        "figure_id": spec.get("id"),
                        "series": name,
                        "min_seeds": min(values),
                        "max_seeds": max(values),
                    })
    payload["seed_coverage"] = coverage
    if coverage:
        payload["warnings"] = list(payload.get("warnings") or []) + [
            "%d series are drawn on a varying seed count; every caption using them must "
            "state N of M seeds, because normalisation drops runs that start at the ceiling"
            % len(coverage)
        ]
    # A disclosure that only lives in one stdout reading is not a disclosure: whoever takes
    # the PNG never sees it. Ship the caption next to the image it describes.
    sidecars: list = []
    for entry in payload.get("figures") or []:
        figure_id = str(entry.get("figure_id") or "").strip()
        if not figure_id or not entry.get("svg"):
            continue
        related = [item for item in coverage if item.get("figure_id") == figure_id]
        lines = [
            "# %s" % figure_id,
            "",
            str(entry.get("caption") or "(no caption in spec)"),
            "",
            "- title: %s" % (entry.get("title") or ""),
            "- x=%s  y=%s  series=%s  type=%s  agg=%s" % (
                entry.get("x"), entry.get("y"), entry.get("series"),
                entry.get("type"), entry.get("agg")),
            "- where: %s" % json.dumps(entry.get("where") or {}, sort_keys=True),
            "- table: %s" % entry.get("table"),
            "- data_sha256: %s" % entry.get("data_sha256"),
            "- spec_sha256: %s" % entry.get("spec_sha256"),
            "- output_sha256: %s" % entry.get("output_sha256"),
            "- schematic: %s" % entry.get("schematic"),
            "- images: %s | %s" % (entry.get("png"), entry.get("svg")),
        ]
        if related:
            lines.append("- seed coverage (each series averages a varying number of seeds:")
            for item in related:
                lines.append("  - %s: %d of %d" % (
                    item.get("series"), item.get("min_seeds"), item.get("max_seeds")))
            lines.append("  runs that already start at the ceiling are excluded, and those")
            lines.append("  are the ceiling-censoring cases the metric argument is about)")
        lines.append("")
        lines.append("This caption is a deterministic projection of verified evidence; it is")
        lines.append("not a claim, not a gate, and signing stays in the CLI.")
        sidecar = Path(entry["svg"]).parent / ("%s.caption.md" % figure_id)
        with open(sidecar, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
        sidecars.append(str(sidecar))
    payload["caption_sidecars"] = sidecars
    payload["boundary"] = (
        "deterministic rendering of the supplied data table; the figure is not evidence, "
        "not a claim and not a gate, and it does not recompute any metric"
    )
    _print_json(payload)
    return 0


def _cmd_figure(args: argparse.Namespace) -> int:
    from .figure_workflow import FigureWorkflowError, list_templates, render_scene, render_template

    try:
        if args.figure_command == "templates":
            _print_json(list_templates())
            return 0
        formats = list(args.format or [])
        if not formats:
            formats = ["svg", "png"]
        if args.template:
            result = render_template(
                template_id=args.template,
                output_dir=Path(args.output_dir),
                title=args.title,
                description=args.description,
                output_name=args.name,
                formats=formats,
            )
        else:
            result = render_scene(
                scene_path=Path(args.scene),
                output_dir=Path(args.output_dir),
                title=args.title,
                description=args.description,
                output_name=args.name,
                formats=formats,
            )
    except (FigureWorkflowError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_skill(args: argparse.Namespace) -> int:
    store = SkillRegistryStore(Path(args.registry_path))
    try:
        if args.skill_command == "list":
            _print_json(store.snapshot())
            return 0
        if args.skill_command == "scan":
            _print_json(store.import_directory(Path(args.path)))
            return 0
        if args.skill_command in ("enable", "disable"):
            _print_json(store.set_enabled(args.id, args.skill_command == "enable"))
            return 0
        if args.skill_command == "delete":
            _print_json({"deleted": store.delete(args.id), "id": args.id})
            return 0
        _print_json(store.export(Path(args.output)))
        return 0
    except SkillError as exc:
        raise SystemExit(str(exc))


def _parse_scope_values(values: List[str]) -> dict:
    scopes = {}
    for item in values or []:
        if "=" not in item:
            raise EvolutionPolicyError("scope must be id=on|off: " + item)
        key, raw = item.split("=", 1)
        key = key.strip()
        value = raw.strip().lower()
        if value not in ("on", "off", "true", "false", "1", "0"):
            raise EvolutionPolicyError("scope value must be on/off: " + item)
        scopes[key] = value in ("on", "true", "1")
    return scopes


def _cmd_rsi_policy(args: argparse.Namespace) -> int:
    store = EvolutionPolicyStore(Path(args.policy_path))
    try:
        if args.policy_command == "show":
            payload = store.snapshot()
            if args.output:
                _write_json(Path(args.output), payload)
                _print_json({"output": args.output, "enabled": payload["enabled"]})
            else:
                _print_json(payload)
            return 0
        scopes = _parse_scope_values(args.scope)
        enabled = None
        if args.enabled:
            enabled = True
        elif args.disabled:
            enabled = False
        _print_json(store.update(enabled=enabled, scopes=scopes or None))
        return 0
    except EvolutionPolicyError as exc:
        raise SystemExit(str(exc))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _cmd_run_execute(args: argparse.Namespace) -> int:
    seeds = args.seeds
    lease = None
    if args.use_lease:
        if not args.ledger:
            raise RuntimeError("--use-lease requires --ledger")
        lease = resolve_s5_seed_policy(Path(args.ledger), args.lease_scope)
        if lease is None:
            raise RuntimeError("no active S5 seed lease for scope: " + args.lease_scope)
        seeds = lease["seeds"]
    dataset = args.dataset
    if lease and args.lease_scope.startswith("S5/demo/"):
        dataset = args.lease_scope.split("S5/demo/", 1)[1] or dataset
    result = RunAgent(SpecStore().load("run")).execute(
        RunRequest(
            protocol_id=args.protocol_id,
            dataset=dataset,
            seeds=seeds,
            test_size=args.test_size,
            run_id=args.run_id or "",
        ),
        Path(args.output_dir),
    )
    if lease:
        result["active_harness"] = lease
    _print_json(result)
    return 0


def _parse_claim_assertions(values):
    assertions = []
    for raw in values or []:
        item = {}
        for part in str(raw).split(","):
            if "=" not in part:
                raise RuntimeError("assertion must be key=value: %s" % raw)
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in ("value", "tolerance"):
                try:
                    item[key] = float(value)
                except ValueError:
                    raise RuntimeError("assertion %s must be numeric" % key)
            elif key in ("metric", "comparator", "condition", "claim_type"):
                item[key] = value
            else:
                raise RuntimeError("unknown assertion field: %s" % key)
        if "value" not in item:
            raise RuntimeError("assertion requires value: %s" % raw)
        assertions.append(item)
    return assertions


def _cmd_run_claim(args: argparse.Namespace) -> int:
    result = RunAgent(SpecStore().load("run")).claim(
        Path(args.capsule),
        Path(args.ea),
        args.statement,
        args.human_reason,
        args.scope,
        Path(args.output_dir),
        assertions=_parse_claim_assertions(getattr(args, "assertion", None)),
    )
    _print_json(result)
    return 0


def _cmd_bibliography_verify(args: argparse.Namespace) -> int:
    result = BibliographyAgent().verify(Path(args.source), Path(args.output_dir))
    _print_json(result)
    return 0


def _cmd_protocol_freeze(args: argparse.Namespace) -> int:
    design = json.loads(Path(args.design).read_text(encoding="utf-8"))
    result = ExperimentDesignAgent(SpecStore().load("experiment")).freeze(
        design, Path(args.capsule), args.limitation, args.human_reason, Path(args.output_dir)
    )
    _print_json(result)
    return 0


def _cmd_flow_g1(args: argparse.Namespace) -> int:
    idea = json.loads(Path(args.idea_file).read_text(encoding="utf-8"))
    candidates = idea.get("candidates") or []
    selected = next(
        (item for item in candidates if str(item.get("idea_id") or "") == args.idea_id),
        None,
    )
    if selected is None:
        raise RuntimeError("idea id not found in idea file: " + args.idea_id)
    payload = {
        "status": "approved",
        "selected_idea_id": args.idea_id,
        "selected_idea_sha256": sha256_json({
            "idea_id": str(selected.get("idea_id") or ""),
            "title": str(selected.get("title") or ""),
            "hypothesis": str(selected.get("hypothesis") or ""),
            "falsification": str(selected.get("falsification") or ""),
            "evidence_refs": list(selected.get("evidence_refs") or []),
        }),
        "human_reason": args.human_reason,
        "decision_id": args.decision_id or "G1-" + args.idea_id,
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "g1-decision.json"
    _write_json(path, payload)
    _print_json({"path": str(path), "decision": payload})
    return 0


def _cmd_protocol_freeze_design(args: argparse.Namespace) -> int:
    design = json.loads(Path(args.design).read_text(encoding="utf-8"))
    result = ExperimentDesignAgent(SpecStore().load("experiment")).freeze_design(
        design, args.limitation, args.human_reason, Path(args.output_dir)
    )
    _print_json(result)
    return 0


def _cmd_closure_check(args: argparse.Namespace) -> int:
    result = ClosureAgent().check(
        Path(args.demo), Path(args.claim), Path(args.output_dir)
    )
    _print_json(result)
    return 0


def _cmd_closure_profiles(args: argparse.Namespace) -> int:
    from .closure_profiles import describe_profiles, detect_project_profiles

    result = describe_profiles()
    if args.project:
        result["project"] = detect_project_profiles(Path(args.project))
    _print_json(result)
    return 0


def _cmd_closure_sign(args: argparse.Namespace) -> int:
    signer_store = None
    signer_id = ""
    if args.signer:
        signer_store = SignerStore(Path(args.signers_path))
        signer_id = args.signer
    try:
        result = ClosureAgent().sign(
            Path(args.report), Path(args.demo), Path(args.claim),
            args.human_reason, Path(args.output_dir),
            signer_store=signer_store,
            signer_id=signer_id,
        )
    except SignerError as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_closure_publish(args: argparse.Namespace) -> int:
    signature = Path(args.signature) if args.signature else None
    try:
        result = ClosureAgent().publish(
            Path(args.manifest), Path(args.output_dir), signature, args.bundle_name,
            signer_store=SignerStore(Path(args.signers_path)),
        )
    except SignerError as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_signer(args: argparse.Namespace) -> int:
    try:
        store = SignerStore(Path(args.signers_path))
        if args.signer_command == "create":
            _print_json({"signer": store.create(args.name), "boundary": store.boundary})
            return 0
        if args.signer_command == "list":
            _print_json(store.snapshot())
            return 0
        raise SignerError("unknown signer command")
    except SignerError as exc:
        raise SystemExit(str(exc))


def _cmd_closure_obligations(args: argparse.Namespace) -> int:
    from .obligations import ObligationLedger

    ledger = ObligationLedger(Path(args.ledger))
    try:
        if args.obligations_command == "list":
            result = ledger.snapshot()
        elif args.obligations_command == "resolve":
            result = ledger.resolve(
                args.id,
                args.reason,
                Path(args.evidence) if args.evidence else None,
            )
        else:
            result = ledger.waive(args.id, args.reason)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_closure_verify_bundle(args: argparse.Namespace) -> int:
    try:
        result = ClosureAgent().verify_bundle(
            Path(args.bundle), signer_store=SignerStore(Path(args.signers_path))
        )
    except SignerError as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0 if result.get("status") == "clean" else 1


def _cmd_closure_audit(args: argparse.Namespace) -> int:
    result = audit_pipeline_bundle(Path(args.bundle), Path(args.output_dir) if args.output_dir else None)
    _print_json(result)
    return 0 if result.get("status") != "structural_failure" else 1


def _cmd_lineage_build(args: argparse.Namespace) -> int:
    manifest = LineageAgent().build(
        Path(args.bundle),
        signer_store=SignerStore(Path(args.signers_path)),
    )
    path = write_manifest(manifest, Path(args.output_dir))
    _print_json({**manifest, "path": str(path)})
    return 0


def _cmd_lineage_verify(args: argparse.Namespace) -> int:
    result = LineageAgent().verify(Path(args.manifest), Path(args.bundle))
    path = write_impact(result, Path(args.output_dir))
    _print_json({**result, "path": str(path)})
    return 0 if result.get("status") == "clean" else 1


def _cmd_lineage_impact(args: argparse.Namespace) -> int:
    result = LineageAgent().impact(Path(args.baseline), Path(args.bundle))
    path = write_impact(result, Path(args.output_dir))
    _print_json({**result, "path": str(path)})
    if args.fail_on_stale and result.get("status") != "clean":
        return 2
    return 0


def _flow_mode(args: argparse.Namespace) -> str:
    if _models_required():
        return "strict"
    value = str(getattr(args, "flow_mode", "") or "").strip().lower()
    return value if value in ("review", "strict") else "review"


def _task_request(args: argparse.Namespace) -> TaskRequest:
    return TaskRequest(
        goal=args.goal,
        task_type=args.type,
        deliverable=args.deliverable or "",
        language=args.language,
        venue_type=args.venue,
        source=args.source,
        max_sources=args.max_sources,
        run_dataset=args.run_dataset or "",
        run_dir=args.run_dir or "",
        run_seeds=args.run_seeds,
        corpus_dir=args.corpus_dir or "",
        constraints=list(args.constraint or []),
        success_criteria=list(args.criterion or []),
        flow_mode=_flow_mode(args),
        g1_decision_file=args.g1_decision or "",
        protocol_file=getattr(args, "protocol_file", "") or "",
        claim_file=getattr(args, "claim_file", "") or "",
        bibliography_file=getattr(args, "bibliography_file", "") or "",
    )


def _task_agent(args: argparse.Namespace) -> TaskAgent:
    planner, planner_note = _resolve_planner(getattr(args, "planner", "gateway"))
    writer, writer_note = _resolve_paper_writer(getattr(args, "writer", "auto"))
    idea, idea_note = _resolve_idea_proposer(getattr(args, "idea_model", "auto"))
    experiment, experiment_note = _resolve_experiment_designer(
        getattr(args, "experiment_model", "auto")
    )
    support_judge, support_note = _resolve_support_judge(
        getattr(args, "support_judge", "auto")
    )
    for note in (planner_note, writer_note, idea_note, experiment_note, support_note):
        if note:
            print(note, file=sys.stderr)
    return TaskAgent(
        query_planner=planner,
        section_writer=writer,
        idea_proposer=idea,
        experiment_designer=experiment,
        support_judge=support_judge,
        strict_models=_models_required(),
        strict_routing=_models_required(),
    )


def _cmd_benchmark(args: argparse.Namespace) -> int:
    from .benchmark import run_internal_benchmark

    report = run_internal_benchmark(
        Path(args.output_dir) if args.output_dir else None,
        include_closure=not args.no_closure,
    )
    _print_json(report)
    return 0 if report["summary"]["failed"] == 0 else 1


def _cmd_task_plan(args: argparse.Namespace) -> int:
    plan = TaskAgent().plan(_task_request(args))
    _print_json(plan.to_dict())
    return 0


def _cmd_task_run(args: argparse.Namespace) -> int:
    agent = _task_agent(args)
    execution = agent.run(_task_request(args), Path(args.output_dir))
    _print_json({
        "task_id": execution.task_id,
        "status": execution.status,
        "route": execution.plan.route,
        "output_dir": str(Path(args.output_dir)),
        "artifacts": execution.artifacts,
        "checks": execution.checks,
        "warnings": execution.warnings,
    })
    return 0 if execution.status != "failed" else 1


def _cmd_project_init(args: argparse.Namespace) -> int:
    from .project import init_project

    result = init_project(Path(args.dir), args.name)
    _print_json(result)
    return 0


def _cmd_project_status(args: argparse.Namespace) -> int:
    from .project import project_status

    _print_json(project_status(Path(args.dir), limit=args.limit))
    return 0


def _resume_pipeline_inputs(resume_dir: Path) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for rel in ("g1-decision.json", "flow/g1-decision.json"):
        candidate = resume_dir / rel
        if candidate.is_file():
            found["g1_decision"] = str(candidate)
            break
    for rel in ("idea.json", "flow/idea.json"):
        candidate = resume_dir / rel
        if candidate.is_file():
            found["idea_file"] = str(candidate)
            break
    for rel in ("experiment.json", "design.json"):
        candidate = resume_dir / rel
        if candidate.is_file():
            found["design_file"] = str(candidate)
            break
    for rel in ("study-design.json", "design/study-design.json"):
        candidate = resume_dir / rel
        if candidate.is_file():
            found["study_design_file"] = str(candidate)
            break
    for rel in ("protocol.json", "protocol/protocol-card.json"):
        candidate = resume_dir / rel
        if candidate.is_file():
            found["protocol_file"] = str(candidate)
            break
    # A verified bibliography card is an input like any other: without it a resumed run silently
    # loses the reference verification and reports a worse audit than the run it continues.
    for rel in ("bibliography.json", "inputs/bibliography.json"):
        candidate = resume_dir / rel
        if candidate.is_file():
            found["bibliography_file"] = str(candidate)
            break
    for rel in ("claim/claim.json", "run-claim/claim.json", "claim.json"):
        candidate = resume_dir / rel
        if candidate.is_file():
            found["claim_file"] = str(candidate)
            break
    run_capsule = resume_dir / "run" / "run-capsule.json"
    run_ea = resume_dir / "run" / "ea.json"
    if run_capsule.is_file() and run_ea.is_file():
        found["run_dir"] = str(resume_dir / "run")
    return found


def _cmd_pipeline_run(args: argparse.Namespace) -> int:
    language = args.language
    if not language:
        language = "en" if args.venue.startswith("en_") else "zh"
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    resume_sources: Dict[str, str] = {}
    if getattr(args, "resume_dir", ""):
        resume_dir = Path(args.resume_dir)
        if not resume_dir.is_dir():
            raise RuntimeError("--resume-dir not found: " + str(resume_dir))
        for key, path in _resume_pipeline_inputs(resume_dir).items():
            current = getattr(args, key, "")
            if not current:
                setattr(args, key, path)
                resume_sources[key] = path
    planner, planner_note = _resolve_planner(args.planner)
    if planner_note:
        print(planner_note, file=sys.stderr)
    writer, writer_note = _resolve_paper_writer(getattr(args, "writer", "auto"))
    idea_proposer, idea_note = _resolve_idea_proposer(getattr(args, "idea_model", "auto"))
    experiment_designer, experiment_note = _resolve_experiment_designer(
        getattr(args, "experiment_model", "auto")
    )
    support_judge, support_note = _resolve_support_judge(
        getattr(args, "support_judge", "auto")
    )
    for note in (writer_note, idea_note, experiment_note, support_note):
        if note:
            print(note, file=sys.stderr)
    runner = PipelineRunner(
        run_output_dir=out / "run",
        query_planner=planner,
        section_writer=writer,
        idea_proposer=idea_proposer,
        experiment_designer=experiment_designer,
        strict_models=_models_required(),
    )
    lease = None
    retriever_kind = ""
    if args.use_lease:
        if not args.ledger:
            raise RuntimeError("--use-lease requires --ledger")
        lease = resolve_active_harness(Path(args.ledger), args.lease_scope)
        if lease is None:
            raise RuntimeError("no active harness lease for scope: " + args.lease_scope)
        retriever_kind = lease["retriever"]
    elif args.real_corpus or args.corpus:
        retriever_kind = "bm25"
    if args.corpus_dir:
        runner = PipelineRunner(
            retriever=LocalDocumentRetriever(Path(args.corpus_dir)),
            parser=SimpleParser(max_spans_per_source=4000),
            source_scope=["local"],
            run_output_dir=out / "run",
            query_planner=planner,
            section_writer=writer,
            idea_proposer=idea_proposer,
            experiment_designer=experiment_designer,
            strict_models=_models_required(),
        )
    elif args.openalex:
        runner = PipelineRunner(
            retriever=OpenAlexRetriever(mailto=args.mailto or None),
            parser=SimpleParser(),
            source_scope=["openalex"],
            run_output_dir=out / "run",
            query_planner=planner,
            section_writer=writer,
            idea_proposer=idea_proposer,
            experiment_designer=experiment_designer,
            strict_models=_models_required(),
        )
    elif retriever_kind:
        corpus = Path(args.corpus) if args.corpus else (
            Path(__file__).resolve().parents[1] / "modules" / "literature" / "fixtures" / "real_corpus.json"
        )
        retriever = MiniLMRetriever(corpus) if retriever_kind == "minilm" else RealCorpusRetriever(corpus)
        runner = PipelineRunner(
            retriever=retriever,
            parser=SimpleParser(max_spans_per_source=2000),
            source_scope=["real"],
            run_output_dir=out / "run",
            query_planner=planner,
            section_writer=writer,
            idea_proposer=idea_proposer,
            experiment_designer=experiment_designer,
            strict_models=_models_required(),
        )
    max_sources = lease["max_sources"] if lease else args.max_sources
    run_dataset = args.run_dataset
    run_seeds = args.run_seeds
    run_harness = {}
    if args.use_s5_lease:
        if not args.s5_ledger:
            raise RuntimeError("--use-s5-lease requires --s5-ledger")
        s5 = resolve_s5_seed_policy(Path(args.s5_ledger), args.s5_scope)
        if s5 is None:
            raise RuntimeError("no active S5 seed lease for scope: " + args.s5_scope)
        run_dataset = run_dataset or args.s5_scope.split("S5/demo/", 1)[-1]
        run_seeds = s5["seeds"]
        run_harness = s5
    claim_refs = []
    claim_statements = []
    claim_assertions = []
    if args.claim_file:
        claim = json.loads(Path(args.claim_file).read_text(encoding="utf-8"))
        if claim.get("status") != "supported" or not claim.get("evidence_refs"):
            raise RuntimeError("claim file must be supported and reference at least one EA")
        claim_refs = [str(claim["claim_id"])]
        if str(claim.get("statement") or "").strip():
            claim_statements = [str(claim["statement"]).strip()]
        claim_assertions = list(claim.get("assertions") or [])
    result = runner.run(
        PipelineRequest(
            topic=args.topic,
            language=language,
            venue_type=args.venue,
            grant_scheme=args.grant or "",
            figure_style=args.style,
            max_sources=max_sources,
            primary_metric=args.primary_metric or "",
            controls=list(args.control or []),
            budget=args.budget or "",
            claim_refs=claim_refs,
            claim_statements=claim_statements,
            claim_assertions=claim_assertions,
            run_dataset=run_dataset,
            run_dir=args.run_dir or "",
            protocol_file=args.protocol_file or "",
            bibliography_file=args.bibliography_file or "",
            run_seeds=run_seeds,
            run_harness=run_harness,
            run_id=args.run_id or "",
            flow_mode=_flow_mode(args),
            g1_decision_file=args.g1_decision or "",
            idea_file=args.idea_file or "",
            design_file=args.design_file or "",
            study_design_file=getattr(args, "study_design_file", "") or "",
            study_dataset=getattr(args, "study_dataset", "") or "",
            study_seeds=int(getattr(args, "study_seeds", 0) or 0),
            study_budget=int(getattr(args, "study_budget", 60) or 60),
            study_root=(
                str(Path(getattr(args, "study_project", "") or "").expanduser())
                if getattr(args, "study_project", "")
                else ""
            ),
            claim_file=args.claim_file or "",
            adaptive_retrieval=bool(getattr(args, "adaptive_retrieval", False)),
        )
    )
    extra = {}
    if lease:
        extra["active_harness"] = lease
    if run_harness:
        extra["run_harness"] = run_harness
    write_pipeline_artifacts(
        result,
        out,
        extra=extra,
        claim_file=args.claim_file or "",
        support_judge=support_judge,
        strict_support=_models_required(),
    )
    _print_json({
        "status": result.status,
        "run_id": result.run_id,
        "fixture_mode": result.fixture_mode,
        "active_harness": lease,
        "run_harness": run_harness,
        "resume_sources": resume_sources,
        "output_dir": str(out),
        "figure": "data/figure.svg",
        "modules": {key: (value.get("status") if isinstance(value, dict) else None) for key, value in result.modules.items()},
    })
    return 0


def _parse_metrics(values):
    metrics = {}
    for item in values or []:
        if "=" not in item:
            raise RSIPolicyError("metric must be key=value: " + item)
        key, raw = item.split("=", 1)
        metrics[key.strip()] = float(raw)
    return metrics


def _artifact_sha(ref: str) -> str:
    path = Path(ref)
    if not ref or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rsi_ledger(args: argparse.Namespace) -> StepLedger:
    return StepLedger.load(Path(args.ledger))


def _require_evolution_enabled(args: argparse.Namespace) -> EvolutionPolicyStore:
    store = EvolutionPolicyStore(
        Path(getattr(args, "policy_path", str(DEFAULT_EVOLUTION_POLICY_PATH)))
    )
    try:
        store.require_enabled()
    except EvolutionPolicyError as exc:
        raise SystemExit(str(exc))
    return store


def _predicted_metrics(pairs) -> Dict[str, float]:
    """Parse repeatable ``KEY=VALUE`` numeric predictions for ``rsi propose``.

    Without a numeric prediction the loop can record outcomes but can never be calibrated against
    them: tracking reports "actuals recorded without numeric predictions" and the story says
    calibration unavailable, however many trials run. The field existed and was validated, but no
    documented command could fill it, so every human-proposed episode was uncalibratable.
    """
    metrics: Dict[str, float] = {}
    for pair in pairs or ():
        text = str(pair)
        key, sep, value = text.partition("=")
        key = key.strip()
        if not sep or not key:
            raise SystemExit("--predicted-metric needs KEY=VALUE, got: %s" % text)
        try:
            number = float(value.strip())
        except ValueError:
            raise SystemExit("--predicted-metric value must be numeric, got: %s" % text)
        if number != number or number in (float("inf"), float("-inf")):
            raise SystemExit("--predicted-metric value must be finite, got: %s" % text)
        metrics[key] = number
    return metrics


def _cmd_rsi_propose(args: argparse.Namespace) -> int:
    policy_store = _require_evolution_enabled(args)
    try:
        policy_store.require_candidate(args.kind, args.target)
    except EvolutionPolicyError as exc:
        raise SystemExit(str(exc))
    ledger = _rsi_ledger(args)
    controller = RSIController(ledger)
    candidate = Candidate(
        kind=args.kind,
        target=args.target,
        patch=args.patch,
        rationale=args.rationale,
        predicted_effect=args.predicted,
        predicted_metrics=_predicted_metrics(args.predicted_metric),
        parent_id=args.parent or "",
        scope=args.scope or "",
    )
    record = controller.propose(candidate, observation=args.observation or "", dry_run_ref=args.dry_run_ref or "")
    _print_json(asdict(record))
    return 0


def _cmd_rsi_actuals(args: argparse.Namespace) -> int:
    # Closes the calibration loop for a human proposal: `rsi propose --predicted-metric` records a
    # prediction, and this records the measured outcome for the same episode. Without it, actuals
    # were only writable inside fixture/s5, so a human-proposed candidate could never be calibrated.
    ledger = _rsi_ledger(args)
    controller = RSIController(ledger)
    actuals = _predicted_metrics(args.metric)
    if not actuals:
        raise SystemExit("rsi actuals needs at least one --metric KEY=VALUE")
    record = controller.record_actuals(args.episode, actuals, note=args.note or "")
    _print_json(asdict(record))
    return 0


def _cmd_rsi_fixture(args: argparse.Namespace) -> int:
    result = run_fixture_trial(
        ledger_path=Path(args.ledger),
        output_dir=Path(args.output_dir),
        tasks_path=Path(args.tasks) if args.tasks else None,
        human_approve=bool(args.approve),
    )
    _print_json(result)
    return 0


def _cmd_rsi_confirm(args: argparse.Namespace) -> int:
    result = run_confirmation_trial(
        Path(args.ledger),
        Path(args.output_dir),
        Path(args.tasks) if args.tasks else None,
    )
    _print_json(result)
    return 0


def _cmd_rsi_real_trial(args: argparse.Namespace) -> int:
    result = run_real_trial(
        Path(args.ledger),
        Path(args.output_dir),
        Path(args.tasks) if args.tasks else None,
        Path(args.corpus) if args.corpus else None,
        human_approve=bool(args.approve),
        retriever_kind=args.retriever,
        candidate_path=Path(args.candidate_file) if args.candidate_file else None,
    )
    _print_json(result)
    return 0


def _cmd_rsi_real_confirm(args: argparse.Namespace) -> int:
    result = run_real_confirmation(
        Path(args.ledger),
        Path(args.output_dir),
        args.lease_scope,
        Path(args.tasks) if args.tasks else None,
        Path(args.corpus) if args.corpus else None,
    )
    _print_json(result)
    return 0


def _cmd_rsi_propose_model(args: argparse.Namespace) -> int:
    _require_evolution_enabled(args)
    if bool(args.profile) == bool(args.model_path):
        raise RuntimeError("provide exactly one of --profile or --model-path")
    if args.profile:
        store = GatewayStore(Path(args.store))
        model = GatewayModelPort(
            ModelGateway(store, SessionKeyStore()),
            args.profile,
        )
    else:
        model = LocalHFModel(Path(args.model_path))
    candidate = FrozenModelProposer(model).propose(args.observation)
    out = Path(args.out)
    _write_json(out, asdict(candidate))
    _print_json({
        "candidate": asdict(candidate),
        "model": model.model_id,
        "out": str(out),
        "note": "proposal only; evaluate with rsi real-trial --candidate-file",
    })
    return 0


def _cmd_rsi_model_batch(args: argparse.Namespace) -> int:
    report = run_model_batch(
        Path(args.model_path),
        load_observations(Path(args.observations)),
        Path(args.output_dir),
        Path(args.ledger_root),
        human_approve=bool(args.approve),
        repair_attempts=int(args.repair_attempts),
    )
    _print_json(report)
    return 0


def _cmd_rsi_s5_trial(args: argparse.Namespace) -> int:
    result = run_s5_trial(
        Path(args.ledger), Path(args.output_dir),
        human_approve=bool(args.approve), dataset=args.dataset,
    )
    _print_json(result)
    return 0


def _cmd_rsi_s5_confirm(args: argparse.Namespace) -> int:
    result = run_s5_confirmation(
        Path(args.ledger), Path(args.output_dir),
        dataset=args.dataset, scope=args.lease_scope or None,
    )
    _print_json(result)
    return 0


def _cmd_rsi_story(args: argparse.Namespace) -> int:
    story = ledger_story(StepLedger.load(Path(args.ledger)))
    story["ledger_path"] = args.ledger
    if args.output:
        _write_json(Path(args.output), story)
        _print_json({"output": args.output, "headline": story["summary"]["headline"]})
    else:
        _print_json(story)
    return 0


def _cmd_rsi_observations(args: argparse.Namespace) -> int:
    from .evolution_observations import EvolutionObservationStore, ObservationError

    store = EvolutionObservationStore(Path(args.observations_path))
    try:
        if args.observations_command == "show":
            result = {
                "summary": store.summary(),
                "observations": store.list(limit=args.limit),
                "boundary": store.boundary,
            }
        else:
            result = store.suggest_budget()
            if args.output and result.get("status") == "suggested":
                candidate = result["candidate"]
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                _write_json(output, candidate)
                result = dict(result, output=str(output), candidate_file=str(output))
    except ObservationError as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_rsi_active(args: argparse.Namespace) -> int:
    from .evolution_active import ActivePolicyError, ActivePolicyStore

    store = ActivePolicyStore(Path(args.active_path))
    try:
        if args.active_command == "show":
            result = store.snapshot()
        elif args.active_command == "activate":
            result = store.activate(
                Path(args.ledger),
                args.lease_scope,
                args.reason,
                allow_simulation=bool(args.allow_simulation),
            )
        else:
            result = store.deactivate(args.reason)
    except ActivePolicyError as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_rsi_status(args: argparse.Namespace) -> int:
    ledger = _rsi_ledger(args)
    _print_json(RSIController(ledger).report())
    return 0


def _cmd_rsi_gen(args: argparse.Namespace) -> int:
    """Two-track version management for evolution itself: agent harness and platform code."""
    from . import evolution_generations as gens

    command = args.gen_command
    path = args.path or ""
    store = gens.GenerationStore.load(path)

    if command == "list":
        items = [item.to_dict() for item in store.list(args.kind or "")]
        _print_json({"generations": items, "count": len(items)})
        return 0
    if command == "verify":
        report = store.verify()
        _print_json(report)
        return 0 if report["ok"] else 1
    if command == "snapshot":
        generation = gens.platform_snapshot(
            store,
            label=args.label,
            commit=args.commit or "",
            note=args.note or "",
            fingerprint=args.fingerprint or "",
        )
        _print_json(generation.to_dict())
        return 0
    if command == "propose":
        applies = None
        try:
            check = subprocess.run(
                ["git", "apply", "--check", str(Path(args.patch).resolve())],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                timeout=60,
            )
            applies = check.returncode == 0
        except (OSError, subprocess.SubprocessError):
            applies = None
        generation = gens.propose_platform_patch(
            store, label=args.label, patch_path=args.patch, note=args.note or "", applies=applies
        )
        _print_json({"generation": generation.to_dict(), "applies_cleanly": applies})
        return 0 if applies is not False else 1
    if command == "close":
        generation = store.close(
            args.id, args.status, note=args.note or "", commit=args.commit or ""
        )
        _print_json(generation.to_dict())
        return 0
    if command == "agent":
        from . import rsi_harness2 as seam

        payload = seam.load_artifact(args.artifact or "")
        episodes = [item for item in (args.episodes or "").split(",") if item.strip()]
        generation = gens.agent_generation_from_run(
            store,
            payload,
            label=args.label,
            artifact_path=args.artifact or "",
            episode_ids=[item.strip() for item in episodes],
            status=args.status,
            note=args.note or "",
        )
        _print_json(generation.to_dict())
        return 0
    if command == "compare":
        _print_json(store.compare(args.left, args.right))
        return 0
    if command == "export":
        target = Path(args.out)
        from .storage import write_json_atomic

        write_json_atomic(target, gens.summarize_lineage(store))
        _print_json({"out": str(target), "generations": len(store.generations)})
        return 0
    raise SystemExit("unknown gen command")


def _cmd_rsi_harness2(args: argparse.Namespace) -> int:
    """Probe, run, read or record Harness²; never admit and never sign."""
    from . import rsi_harness2

    command = args.harness2_command
    if command == "probe":
        _print_json(rsi_harness2.probe(root=args.root or "", interpreter=args.python or ""))
        return 0
    if command == "run":
        payload = rsi_harness2.run_bridge(
            interpreter=args.python or "",
            root=args.root or "",
            output=args.output or "",
            k=args.k,
            mode=args.mode,
            adapter=args.adapter,
            timeout=args.timeout,
        )
        path = rsi_harness2.write_artifact(payload, args.artifact or "")
        story = rsi_harness2.public_story(payload)
        story["artifact_name"] = path.name
        story_path = path.parent / "story.json"
        from .storage import write_json_atomic

        write_json_atomic(story_path, story)
        _print_json(
            {
                "artifact": str(path),
                "adapter": story["run"]["adapter"],
                "k": story["run"]["k"],
                "modes": story["run"]["modes"],
                "budget": story["budget"],
                "tasks": story["tasks"],
                "adopted": len(story["adopted"]),
                "checklist_ok": story["checklist_ok"],
                "failed": [item["id"] for item in story["checklist"] if not item["ok"]],
            }
        )
        return 0 if story["checklist_ok"] else 1
    if command == "status":
        payload = rsi_harness2.load_artifact(args.artifact or "")
        _print_json(rsi_harness2.summarize(payload))
        return 0
    if command == "record":
        payload = rsi_harness2.load_artifact(args.artifact or "")
        result = rsi_harness2.record_episode(
            payload,
            args.ledger,
            artifact_path=args.artifact or "",
            scope=args.scope,
            policy_path=getattr(args, "policy_path", ""),
        )
        result["story"] = ledger_story(_rsi_ledger(args))["summary"]
        if getattr(args, "generation", ""):
            from . import evolution_generations as generations

            store = generations.GenerationStore.load(getattr(args, "gen_path", "") or "")
            generation = generations.agent_generation_from_run(
                store,
                payload,
                label=args.generation,
                artifact_path=args.artifact or "",
                episode_ids=[item["episode_id"] for item in result["episodes"]],
                note="recorded from rsi harness2 record",
            )
            result["generation"] = generation.to_dict()
        _print_json(result)
        return 0
    raise SystemExit("unknown harness2 command")


def _cmd_rsi_trace(args: argparse.Namespace) -> int:
    result = trace_research(
        Path(args.ledger), args.scope, Path(args.capsule),
        Path(args.confirmation) if args.confirmation else None,
    )
    _print_json(result)
    return 0 if result["ok"] else 1


def _cmd_rsi_admit(args: argparse.Namespace) -> int:
    ledger = _rsi_ledger(args)
    controller = RSIController(ledger)
    task_pack_sha = _artifact_sha(args.task_pack) if args.task_pack else ""
    evaluated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    evaluator = args.evaluator
    public = EvalEvidence(
        "public", "passed", args.public_ref, _parse_metrics(args.public_metric), n=args.n,
        evaluator=evaluator, artifact_sha256=_artifact_sha(args.public_ref),
        task_pack_sha256=task_pack_sha, evaluated_at=evaluated_at,
    )
    hidden = EvalEvidence(
        "hidden", "passed", args.hidden_ref, _parse_metrics(args.hidden_metric), n=args.n,
        evaluator=evaluator, artifact_sha256=_artifact_sha(args.hidden_ref),
        task_pack_sha256=task_pack_sha, evaluated_at=evaluated_at,
    )
    near_ood = EvalEvidence(
        "near_ood", "passed", args.near_ood_ref, _parse_metrics(args.near_ood_metric), n=args.n,
        evaluator=evaluator, artifact_sha256=_artifact_sha(args.near_ood_ref),
        task_pack_sha256=task_pack_sha, evaluated_at=evaluated_at,
    ) if args.near_ood_ref else None
    regression = EvalEvidence(
        "regression", "passed", args.regression_ref, _parse_metrics(args.regression_metric), n=args.n,
        evaluator=evaluator, artifact_sha256=_artifact_sha(args.regression_ref),
        task_pack_sha256=task_pack_sha, evaluated_at=evaluated_at,
    ) if args.regression_ref else None
    record = controller.admit(
        args.episode, public, hidden, args.reason, args.scope, args.ttl_days,
        near_ood_eval=near_ood, regression_eval=regression,
        strict=args.strict, approved_by=args.approved_by,
    )
    _print_json(asdict(record))
    return 0


def _cmd_rsi_reject(args: argparse.Namespace) -> int:
    ledger = _rsi_ledger(args)
    record = RSIController(ledger).reject(args.episode, args.reason)
    _print_json(asdict(record))
    return 0


def _cmd_rsi_revoke(args: argparse.Namespace) -> int:
    ledger = _rsi_ledger(args)
    lease = RSIController(ledger).revoke(args.lease, args.reason)
    _print_json(lease.__dict__)
    return 0


def _cmd_rsi_research_cycle(args: argparse.Namespace) -> int:
    _require_evolution_enabled(args)
    tasks = load_research_tasks(Path(args.tasks))
    result = run_research_cycle(
        tasks, Path(args.ledger), Path(args.output_dir), human_approve=bool(args.approve)
    )
    _print_json({
        "research": result["research"],
        "observation_kinds": result["observation_kinds"],
        "proposal": result.get("proposal"),
        "rsi": result["rsi"],
        "output": str(Path(args.output_dir) / "research-cycle.json"),
    })
    return 0


def _cmd_research_run(args: argparse.Namespace) -> int:
    tasks = load_research_tasks(Path(args.tasks))
    result = ResearchRunner(Path(args.output_dir)).run(tasks)
    _print_json({
        "batch_id": result["batch_id"],
        "tasks": result["summary"]["tasks"],
        "runs": result["summary"]["runs"],
        "observations": result["summary"]["observations"],
        "errors": result["summary"]["errors"],
        "output": str(Path(args.output_dir) / "research-batch.json"),
    })
    return 0


def _cmd_web(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parent / "web"
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError("workbench not found: " + str(index))
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print("Research Agent Workbench: http://127.0.0.1:%d/" % args.port)
    print("Serving", root)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _cmd_action_plan(args: argparse.Namespace) -> int:
    _print_json(
        automation_plan(
            topic=args.topic,
            max_sources=args.max_sources,
            run_dataset=args.run_dataset,
            run_seeds=args.run_seeds,
        )
    )
    return 0


def _cmd_action_skill(args: argparse.Namespace) -> int:
    payload = {}
    if args.payload:
        payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    if args.question:
        payload["question"] = args.question
    if args.max_sources is not None:
        payload["max_sources"] = args.max_sources
    if args.source:
        payload["source"] = args.source
    _print_json(run_skill(args.id, payload))
    return 0


def _cmd_workspace_agents(args: argparse.Namespace) -> int:
    snapshot = AgentRegistry().snapshot()
    if args.output:
        _write_json(Path(args.output), snapshot)
        _print_json({"output": args.output, "count": snapshot["count"]})
    else:
        _print_json(snapshot)
    return 0


def _cmd_workspace_commands(args: argparse.Namespace) -> int:
    snapshot = CommandRegistry().snapshot()
    if args.output:
        _write_json(Path(args.output), snapshot)
        _print_json({"output": args.output, "count": snapshot["count"]})
    else:
        _print_json(snapshot)
    return 0


def _waitpoint_store(args: argparse.Namespace) -> WaitpointStore:
    return WaitpointStore(Path(args.root) if args.root else None)


def _cmd_maintenance_plan(args: argparse.Namespace) -> int:
    result = MaintenanceAgent().plan(
        Path(args.baseline), Path(args.bundle), args.actor, args.reason, Path(args.output_dir),
    )
    _print_json(result)
    return 0


def _cmd_maintenance_reclose(args: argparse.Namespace) -> int:
    result = MaintenanceAgent().reclose(
        Path(args.plan), Path(args.bundle), Path(args.demo), Path(args.claim), Path(args.output_dir),
    )
    _print_json(result)
    status = (result.get("report") or {}).get("status") or result.get("status")
    return 0 if status in ("clean", "ready_for_resign") else 1


def _cmd_waitpoint_create(args: argparse.Namespace) -> int:
    seconds = int(args.ttl_hours) * 3600
    result = _waitpoint_store(args).create(
        label=args.label,
        intent=args.intent,
        owner=args.owner,
        ttl_seconds=seconds,
        max_signals=args.max_signals,
        members=args.member,
        quorum=args.quorum,
        fail_fast=args.fail_fast,
    )
    _print_json(result)
    return 0


def _cmd_waitpoint_signal(args: argparse.Namespace) -> int:
    secret = args.secret or os.environ.get("RESEARCH_AGENT_WAITPOINT_SECRET", "")
    if not secret:
        raise WaitpointError("secret is required (or set RESEARCH_AGENT_WAITPOINT_SECRET)")
    data = None
    if args.data_file:
        data = Path(args.data_file).read_text(encoding="utf-8")
    result = _waitpoint_store(args).signal(
        args.id,
        secret,
        status=args.status,
        message=args.message or "",
        data=data,
        member=args.member,
        dedupe_key=args.dedupe_key,
        source=args.source,
    )
    _print_json(result)
    return 0


def _cmd_waitpoint_status(args: argparse.Namespace) -> int:
    _print_json(_waitpoint_store(args).status(args.id))
    return 0


def _cmd_waitpoint_list(args: argparse.Namespace) -> int:
    _print_json({"waitpoints": _waitpoint_store(args).list(args.owner)})
    return 0


def _cmd_waitpoint_inbox(args: argparse.Namespace) -> int:
    _print_json({"owner": args.owner, "wakes": _waitpoint_store(args).inbox(args.owner)})
    return 0


def _cmd_waitpoint_consume(args: argparse.Namespace) -> int:
    _print_json({"owner": args.owner, "wakes": _waitpoint_store(args).consume(args.owner)})
    return 0


def _cmd_waitpoint_expire(args: argparse.Namespace) -> int:
    _print_json({"expired": _waitpoint_store(args).expire()})
    return 0


def _cmd_waitpoint_triage(args: argparse.Namespace) -> int:
    from .waitpoints import record_delegation_events

    store = _waitpoint_store(args)
    notices = store.inbox(args.owner)
    result = record_delegation_events(Path(args.project), notices, args.scope)
    store.consume(args.owner)
    _print_json(result)
    return 0


def _cmd_exec_faces(args: argparse.Namespace) -> int:
    from .execport.exec_port import describe

    _print_json(describe())
    return 0


def _cmd_workspace_export(args: argparse.Namespace) -> int:
    _print_json(export_workspace_snapshots(Path(args.output_dir)))
    return 0


def _cmd_workspace_memory(args: argparse.Namespace) -> int:
    store = MemoryStore(Path(args.store))
    if args.memory_command == "list":
        _print_json(store.snapshot())
        return 0
    if args.memory_command == "add":
        _print_json(store.add(args.text, kind=args.kind, scope=args.scope, source=args.source))
        return 0
    _print_json({"deleted": store.delete(args.id), "id": args.id})
    return 0


def _cmd_workspace_archive(args: argparse.Namespace) -> int:
    store = ArchiveStore(Path(args.root))
    if args.archive_command == "list":
        _print_json(store.snapshot())
        return 0
    if args.archive_command == "add":
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        _print_json(store.add(args.title, args.task_id, payload, note=args.note or ""))
        return 0
    if args.archive_command == "get":
        _print_json(store.get(args.id))
        return 0
    _print_json({"deleted": store.delete(args.id), "id": args.id})
    return 0


def _host_store_path(args: argparse.Namespace):
    from pathlib import Path

    from .models import GatewayStore, ModelGateway
    from .models.store import SessionKeyStore, default_store_path

    raw = str(getattr(args, "store", "") or "").strip()
    store = GatewayStore(Path(raw).expanduser() if raw else default_store_path())
    return ModelGateway(store, SessionKeyStore())


def _cmd_host_model_bind(args: argparse.Namespace) -> int:
    from .models import ModelConfigError, ModelProfile, ProviderConfig

    gateway = _host_store_path(args)
    profile_id = str(args.profile).strip()
    modules = [item.strip() for item in str(args.modules).split(",") if item.strip()]
    if "host-agent" not in gateway.store.providers:
        gateway.store.upsert_provider(
            ProviderConfig(
                provider_id="host-agent",
                kind="host_agent",
                label="宿主 Agent（Qoder / Claude Code / Codex / Zcode）",
                models=["host-agent"],
            )
        )
    gateway.store.upsert_profile(
        ModelProfile(
            profile_id=profile_id,
            provider_id="host-agent",
            model=str(args.model).strip() or "host-agent",
            label="宿主 Agent 模型",
            json_mode=True,
        )
    )
    bound = {}
    for module in modules:
        try:
            gateway.store.set_binding(module, profile_id)
            bound[module] = profile_id
        except ModelConfigError as exc:
            bound[module] = "rejected: %s" % exc
    _print_json(
        {
            "profile_id": profile_id,
            "provider_kind": "host_agent",
            "bindings": bound,
            "next": (
                "run the usual command; each model step now writes a pending turn. "
                "Answer it with 'python -m research_agent host-model turns --prompt' then "
                "'host-model respond --turn-id MT-... --file answer.json', and re-run the step."
            ),
            "boundary": (
                "the host agent supplies the model; nothing here signs, approves, freezes, "
                "claims, publishes or exports, and every downstream audit still runs"
            ),
        }
    )
    return 0


def _cmd_host_model_turns(args: argparse.Namespace) -> int:
    from .host_model import ModelTurnLedger, host_turn_requests

    ledger = ModelTurnLedger()
    _print_json(
        host_turn_requests(
            ledger,
            status=str(args.status or "") or None,
            module=str(args.module or "") or None,
            limit=int(args.limit),
            include_request=bool(args.prompt),
        )
    )
    return 0


def _cmd_host_model_respond(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .host_model import ModelTurnLedger

    if args.file:
        text = Path(args.file).expanduser().read_text(encoding="utf-8")
    else:
        text = str(args.text or "")
    if not text.strip():
        print("error: --text or --file with content is required", file=sys.stderr)
        return 2
    project_root = Path(args.project).expanduser().resolve() if args.project else None
    outcome = ModelTurnLedger().respond(
        str(args.turn_id).strip(),
        text,
        host_label=str(args.host_label or ""),
        project_root=project_root,
    )
    _print_json(
        {
            "accepted": outcome.get("accepted"),
            "errors": outcome.get("errors", []),
            "receipt": (outcome.get("receipt") or {}),
            "next": (
                "re-run the deferred step: it replays this answer instead of asking again"
                if outcome.get("accepted")
                else "the turn is still pending; fix the output and respond again"
            ),
        }
    )
    return 0 if outcome.get("accepted") else 1


def _cmd_host_model_void(args: argparse.Namespace) -> int:
    from .host_model import ModelTurnLedger

    turn = ModelTurnLedger().void(str(args.turn_id).strip(), str(args.reason).strip())
    _print_json(
        {
            "voided": True,
            "turn_id": turn.get("turn_id"),
            "status": turn.get("status"),
            "previous_text_sha256": (turn.get("voided") or {}).get("previous_text_sha256", ""),
            "next": "re-run the stage: it raises a fresh turn for the same request",
        }
    )
    return 0


def _cmd_host_model_status(args: argparse.Namespace) -> int:
    from .host_model import ModelTurnLedger, host_model_summary

    _print_json(host_model_summary(ModelTurnLedger(), limit=int(args.limit)))
    return 0


def _study_design(items: List[str]) -> Optional[Dict[str, List[str]]]:
    """Parse repeatable ``--factors memory=off,on`` into a design; first level is the reference."""
    if not items:
        return None
    design: Dict[str, List[str]] = {}
    for item in items:
        factor, _, levels = str(item).partition("=")
        factor = factor.strip()
        parts = [part.strip() for part in levels.split(",") if part.strip()]
        if not factor or not parts:
            raise SystemExit(
                "--factors expects factor=level[,level...], e.g. --factors operators=all,feature_only"
            )
        if factor in design:
            raise SystemExit("--factors %s given twice" % factor)
        design[factor] = parts
    return design


def _cmd_study_prereg_init(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .study_from_idea import DEFAULT_MIN_DELTA
    from .study_preregistration import scaffold, unfilled_fields

    seeds = [int(item) for item in str(args.seeds).split(",") if item.strip()]
    design = _study_design(args.factors)
    plan = scaffold(
        design,
        seeds,
        int(args.budget),
        args.dataset,
        min_delta=args.min_delta if args.min_delta is not None else DEFAULT_MIN_DELTA,
    )
    text = json.dumps(plan, ensure_ascii=False, indent=2) + chr(10)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(str(target), "w", encoding="utf-8", newline=chr(10)) as handle:
            handle.write(text)
    _print_json(
        {
            "schema_version": "study-preregistration-scaffold-0.1",
            "written": str(args.output or ""),
            "dataset": plan["dataset"],
            "seeds": len(plan["seeds"]),
            "budget": plan["budget"],
            "resolved_design": plan["design"],
            "unfilled": unfilled_fields(plan),
            "next": "fill the listed fields in prose, then pass the file to study search "
                    "--preregistration or study from-idea --preregistration",
            "boundary": plan["boundary"],
        }
    )
    return 0


def _cmd_study_search(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .search_lab import archive_inert_warning, write_study_package

    output = Path(args.output_dir) if args.output_dir else (
        Path(args.project) / "studies" / args.dataset
    )
    warnings: List[str] = []
    if args.output_dir and "studies" not in output.parts:
        warnings.append(
            "study dir is not under <project>/studies/, so `closure profiles --project` and "
            "research_status will not inventory this package; move it or drop --output-dir"
        )
    seeds = [int(item) for item in str(args.seeds).split(",") if item.strip()]
    design = _study_design(args.factors)
    prereg = None
    if args.preregistration:
        from .study_preregistration import (
            assert_matches_run,
            load_preregistration,
        )

        prereg = load_preregistration(Path(args.preregistration))
        assert_matches_run(
            prereg,
            design=design or {},
            seeds=seeds,
            budget=int(args.budget),
            dataset=args.dataset,
        )
    inert = archive_inert_warning(design or {})
    if inert:
        warnings.append(inert)
    try:
        result = write_study_package(
            output,
            dataset=args.dataset,
            seeds=seeds,
            budget=int(args.budget),
            min_delta=float(args.min_delta),
            design=design,
        )
    except ValueError as exc:
        raise SystemExit(str(exc))
    if prereg is not None:
        from .storage import read_json
        from .study_preregistration import bind_sidecar

        study = read_json(output / "study.json")
        bind_sidecar(output, prereg, study)
    if warnings:
        result["warnings"] = warnings
    _print_json(result)
    return 0


def _cmd_study_from_idea(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .study_from_idea import StudyFromIdeaError, run_study_from_idea

    seeds = [int(item) for item in str(args.seeds).split(",") if item.strip()]
    try:
        result = run_study_from_idea(
            Path(args.project),
            args.run_id,
            args.idea_id,
            seeds=seeds,
            budget=int(args.budget),
            output_root=Path(args.output_root) if args.output_root else None,
            force=bool(args.force),
            datasets=(getattr(args, "datasets", "") or None),
            preregistration=(getattr(args, "preregistration", "") or None),
        )
    except (StudyFromIdeaError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_memory_ab(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .memory_ab import MEMORY_AB_BOUNDARY, analysis, path_for, record

    project = Path(args.project).expanduser().resolve()
    command = getattr(args, "ab_command", "")
    if command == "plan":
        _print_json(
            {
                "status": "planned",
                "arms": [
                    "python -m research_agent innovation review --project %s --run-id %s --rounds 1 --max-ideas 5"
                    % (project, args.run_id),
                    "python -m research_agent innovation review --project %s --run-id %s --rounds 1 "
                    "--max-ideas 5 --no-guidance --output-dir %s"
                    % (project, args.run_id, project / "memory" / "arm-without"),
                ],
                "then": [
                    "python -m research_agent memory ab record --project %s --run-id %s --arm with "
                    "--ideas-file <arm ideas> --literature-file <run literature>" % (project, args.run_id),
                    "python -m research_agent memory ab record --project %s --run-id %s --arm without "
                    "--ideas-file <arm ideas> --literature-file <run literature>" % (project, args.run_id),
                    "python -m research_agent memory ab compare --project %s" % project,
                ],
                "note": (
                    "the two arms must differ only by the guideline block; anything else (model, "
                    "rounds, topic) turns the comparison into an unattributable mix"
                ),
                "boundary": MEMORY_AB_BOUNDARY,
            }
        )
        return 0
    if command == "record":
        ideas = json.loads(
            Path(args.ideas_file).expanduser().read_text(encoding="utf-8")
        )
        literature = json.loads(
            Path(args.literature_file).expanduser().read_text(encoding="utf-8")
        )
        if isinstance(ideas, dict):
            ideas = ideas.get("selected_ideas") or ideas.get("final_ideas") or ideas.get("ideas") or []
        scored = record(
            project,
            run_id=args.run_id,
            arm=args.arm,
            ideas=ideas,
            literature=literature,
            session={
                "session_id": getattr(args, "session_id", "") or "",
                "host_label": getattr(args, "session_host_label", "") or "",
            },
        )
        _print_json({"status": "recorded", "arm": args.arm, "store": str(path_for(project)), **scored})
        return 0
    result = analysis(project, session_mode=getattr(args, "sessions", "") or "single")
    if result.get("status") == "compared" and args.output_dir:
        from .storage import write_json_atomic

        target = Path(args.output_dir).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        write_json_atomic(target / "memory-ab.json", result)
        result["report_file"] = str(target / "memory-ab.json")
    _print_json(result)
    return 0


def _cmd_memory_guidelines(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .guideline_memory import block_for, load, merge, save

    project = Path(args.project).expanduser().resolve()
    step = int(args.step or 0)
    if args.propose_file:
        payload = json.loads(
            Path(args.propose_file).expanduser().read_text(encoding="utf-8")
        )
        proposed = payload.get("proposals") if isinstance(payload, dict) else payload
        if not isinstance(proposed, list):
            raise SystemExit("propose file must be a JSON list of {text, sources} objects")
        from .memory_port import admit

        admission_strategy = getattr(args, "admission", "") or "store_all"
        try:
            admission = admit(proposed, strategy=admission_strategy, project=project)
        except ValueError as exc:
            raise SystemExit(str(exc))
        result = merge(load(project), admission["admitted"], step=step, project=project)
        path = save(project, result["entries"], step)
        _print_json(
            {
                "status": "merged",
                "store": str(path),
                "kept": len(result["entries"]),
                "accepted": result["accepted"],
                "rejected": result["rejected"],
                "expired": result["expired"],
                "admission": {
                    "strategy": admission["strategy"],
                    "proposed": admission["counts"]["proposed"],
                    "admitted": admission["counts"]["admitted"],
                    "rejected_by_strategy": admission["counts"]["rejected"],
                    "rows": admission["rows"],
                },
                "next": (
                    "these lines are appended to the idea-generation prompt on the next review; "
                    "they are advice, not evidence, and cannot reach a claim or a gate"
                ),
            }
        )
        return 0
    entries = load(project)
    _print_json(
        {
            "status": "ok",
            "entries": entries,
            "block": block_for(project),
            "boundary": (
                "guidelines are prompt-side advice with named artifacts; they never create or "
                "change a Claim, assertion, gate decision or exported number"
            ),
        }
    )
    return 0


def _cmd_study_profiles(args: argparse.Namespace) -> int:
    from .search_lab import study_profile_summary

    _print_json(
        {
            "executable_profiles": [study_profile_summary()],
            "note": (
                "idea-stage experiment plans must be checkable against these profiles; "
                "a plan whose object is not in supports() cannot be validated locally"
            ),
        }
    )
    return 0


def _cmd_closure_guard_audit(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .study_claims import guard_audit

    _print_json(guard_audit(Path(args.project).expanduser()))
    return 0


def _cmd_study_replicate(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .study_replication import build_replication_report, write_replication_report

    project = Path(args.project).expanduser() if args.project else None
    studies = (
        Path(args.studies_dir).expanduser()
        if args.studies_dir
        else (project / "studies" if project else None)
    )
    if studies is None:
        raise SystemExit("study replicate needs --project or --studies-dir")
    report = build_replication_report(studies, siblings=not bool(getattr(args, "project_only", False)))
    if args.output_dir:
        report["report_file"] = str(
            write_replication_report(report, Path(args.output_dir).expanduser())
        )
    _print_json(report)
    return 0


def _cmd_study_claim(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .study_claims import build_study_claim

    _print_json(
        build_study_claim(
            Path(args.study_dir),
            statement=args.statement,
            human_reason=args.human_reason,
            scope=args.scope,
            sign=bool(args.sign),
            use_replication_guard=not bool(getattr(args, "no_guard", False)),
            baseline_file=str(getattr(args, "baseline_file", "") or ""),
        )
    )
    return 0


def _cmd_study_brief(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .study_claims import build_study_brief

    try:
        result = build_study_brief(
            Path(args.study_dir),
            output=Path(args.output) if args.output else None,
            language=args.language,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    print(result["markdown"])
    _print_json({key: value for key, value in result.items() if key != "markdown"})
    return 0


def _cmd_study_package(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .study_package import build_study_package

    try:
        result = build_study_package(
            Path(args.study_dir),
            output=Path(args.output) if args.output else None,
            language=args.language,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def _cmd_study_closure(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .study_closure import (
        build_study_lineage,
        check_study_closure,
        sign_study_closure,
        verify_study_lineage,
    )

    study_dir = Path(args.study_dir)
    if args.verify:
        _print_json(verify_study_lineage(study_dir))
        return 0
    if args.build_lineage:
        _print_json(build_study_lineage(study_dir))
        return 0
    if args.sign:
        _print_json(
            sign_study_closure(
                study_dir, human_reason=args.human_reason or "", signer=args.signer or ""
            )
        )
        return 0
    _print_json(check_study_closure(study_dir, verify_repro=bool(args.verify_repro)))
    return 0


def _cmd_study_saturation(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .metric_saturation import interaction_sensitivity, saturation_report

    study_dir = Path(args.study_dir)
    study = json.loads((study_dir / "study.json").read_text(encoding="utf-8"))
    _print_json(
        {
            "schema_version": "study-saturation-0.1",
            "study_dir": str(study_dir.resolve()),
            "saturation": saturation_report(study),
            "sensitivity": interaction_sensitivity(study),
            "boundary": (
                "post-hoc metric-validity disclosure; not a claim, not pre-registered evidence, "
                "and it never signs or replaces the registered metric"
            ),
        }
    )
    return 0


def _cmd_grant_template(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .modules.grant import grant_template
    from .storage import write_json_atomic

    try:
        data = grant_template(args.scheme)
    except ValueError as exc:
        raise SystemExit(str(exc))
    path = Path(args.output)
    write_json_atomic(path, data)
    _print_json({"path": str(path.resolve()), "scheme": args.scheme, "sections": list(data["sections"])})
    return 0


def _cmd_venue_audit(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .venue_audit import audit_chinese_journal, audit_grant

    path = Path(args.file)
    if not path.is_file():
        raise SystemExit("venue audit input does not exist: " + str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    if args.kind == "zh_journal":
        result = audit_chinese_journal(data, profile_name=args.profile)
    else:
        sections = data.get("sections") if isinstance(data, dict) else None
        if not isinstance(sections, dict):
            raise SystemExit("grant input needs a JSON object with a sections field")
        evidence = data.get("evidence_refs") if isinstance(data, dict) else None
        result = audit_grant(
            sections,
            scheme=args.scheme,
            evidence_refs=[str(item) for item in evidence or []],
            anonymous=bool(args.anonymous),
            identity_removed=bool(args.identity_removed),
            ai_statement=bool(args.ai_statement),
        )
    from .pack_audit import attach_pack_rubric, manuscript_pack_text

    sections_field = data.get("sections") if isinstance(data.get("sections"), dict) else None
    pack_text = manuscript_pack_text(data, args.kind, sections_field)
    try:
        attach_pack_rubric(
            result,
            pack_text,
            pack_dir=args.skill_pack,
            pack_root=args.skill_pack_root,
            venue=args.venue,
            stage=args.skill_stage,
            profile=getattr(args, "skill_profile", "") or "",
            max_items=args.skill_max_items,
        )
    except ValueError as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research_agent", description="Research Agent module specs and subagents")
    sub = parser.add_subparsers(dest="command", required=True)

    spec = sub.add_parser("spec", help="read or minimally update module specs")
    spec_sub = spec.add_subparsers(dest="spec_command", required=True)

    list_parser = spec_sub.add_parser("list", help="list modules")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=_cmd_spec_list)

    show_parser = spec_sub.add_parser("show", help="show one module spec")
    show_parser.add_argument("module_id")
    show_parser.add_argument("--body", action="store_true")
    show_parser.set_defaults(func=_cmd_spec_show)

    update_parser = spec_sub.add_parser("update", help="minimally update frontmatter + changelog")
    update_parser.add_argument("module_id")
    update_parser.add_argument("--version")
    update_parser.add_argument("--status", choices=["draft", "pilot", "active", "deprecated", "revoked"])
    update_parser.add_argument("--name")
    update_parser.add_argument("--stage")
    update_parser.add_argument("--input", dest="inputs", action="append")
    update_parser.add_argument("--output", dest="outputs", action="append")
    update_parser.add_argument("--tool", dest="tools", action="append")
    update_parser.add_argument("--gate", dest="gates", action="append")
    update_parser.add_argument("--invariant", dest="invariants", action="append")
    update_parser.add_argument("--changelog", required=True)
    update_parser.add_argument(
        "--replace-lists",
        action="store_true",
        help="replace input/output/tool/gate/invariant lists instead of appending to them",
    )
    update_parser.set_defaults(func=_cmd_spec_update)

    patch_parser = spec_sub.add_parser("patch", help="replace one '## section' body")
    patch_parser.add_argument("module_id")
    patch_parser.add_argument("--section", required=True)
    patch_parser.add_argument("--text")
    patch_parser.add_argument("--file")
    patch_parser.set_defaults(func=_cmd_spec_patch)

    add_host_parsers(sub)
    add_autopilot_parsers(sub)
    add_design_parsers(sub)

    venue_parser = sub.add_parser(
        "venue", help="Chinese-journal and NSFC/NSSFC submission checks (advisory, never signs)"
    )
    venue_sub = venue_parser.add_subparsers(dest="venue_command", required=True)
    venue_audit = venue_sub.add_parser("audit", help="audit a manuscript or grant JSON")
    venue_audit.add_argument("--file", required=True)
    venue_audit.add_argument("--kind", choices=["zh_journal", "grant"], default="zh_journal")
    venue_audit.add_argument(
        "--profile",
        choices=["zh_core_journal", "software_journal", "computer_journal"],
        default="zh_core_journal",
    )
    venue_audit.add_argument("--scheme", choices=["nsfc", "nssfc", "generic"], default="nsfc")
    venue_audit.add_argument("--anonymous", action="store_true")
    venue_audit.add_argument("--identity-removed", action="store_true")
    venue_audit.add_argument("--ai-statement", action="store_true")
    venue_audit.add_argument(
        "--skill-pack",
        default="",
        help="optional local SKILL pack directory; adds an advisory rubric block",
    )
    venue_audit.add_argument("--skill-max-items", type=int, default=40)
    venue_audit.add_argument(
        "--skill-pack-root",
        default="",
        help="Awesome-Journal-Skills root; route --venue to a pack automatically",
    )
    venue_audit.add_argument("--venue", default="", help="venue name/id for --skill-pack-root")
    venue_audit.add_argument(
        "--skill-stage",
        choices=["", "idea", "design", "writing", "submission", "review", "reproducibility", "general"],
        default="",
        help="optional stage filter for the pack coverage report",
    )
    venue_audit.add_argument(
        "--skill-profile",
        choices=["", "design", "draft", "submission", "revision"],
        default="",
        help="optional stage profile (draft/submission/revision) instead of a single stage",
    )
    venue_audit.set_defaults(func=_cmd_venue_audit)

    grant_parser = sub.add_parser("grant", help="NSFC/NSSFC grant scaffold (never writes science)")
    grant_sub = grant_parser.add_subparsers(dest="grant_command", required=True)
    grant_template_parser = grant_sub.add_parser("template", help="write a blank section skeleton")
    grant_template_parser.add_argument("--scheme", choices=["nsfc", "nssfc", "generic"], default="nsfc")
    grant_template_parser.add_argument("--output", required=True)
    grant_template_parser.set_defaults(func=_cmd_grant_template)

    host_model = sub.add_parser(
        "host-model",
        help="hand generation steps to the calling agent instead of an external API key",
    )
    host_sub = host_model.add_subparsers(dest="host_model_command", required=True)

    bind_parser = host_sub.add_parser(
        "bind", help="register the keyless host-agent profile and bind modules to it"
    )
    bind_parser.add_argument(
        "--modules",
        default="idea,experiment,paper,judge,rsi",
        help="comma-separated module ids to bind (idea, experiment, paper, judge, rsi)",
    )
    bind_parser.add_argument("--profile", default="host-agent")
    bind_parser.add_argument("--model", default="host-agent")
    bind_parser.add_argument("--store", default="", help="gateway store path")
    bind_parser.set_defaults(func=_cmd_host_model_bind)

    turns_parser = host_sub.add_parser("turns", help="list host model turns")
    turns_parser.add_argument("--status", default="pending")
    turns_parser.add_argument("--module", default="")
    turns_parser.add_argument("--limit", type=int, default=10)
    turns_parser.add_argument(
        "--prompt", action="store_true", help="include the full request text to answer"
    )
    turns_parser.set_defaults(func=_cmd_host_model_turns)

    respond_parser = host_sub.add_parser("respond", help="submit one host answer")
    respond_parser.add_argument("--turn-id", required=True)
    respond_parser.add_argument("--text", default="")
    respond_parser.add_argument("--file", default="", help="read the answer from a file")
    respond_parser.add_argument("--host-label", default="")
    respond_parser.add_argument("--project", default="", help="project root for a file sink")
    respond_parser.set_defaults(func=_cmd_host_model_respond)

    void_parser = host_sub.add_parser(
        "void", help="invalidate an answered turn so the stage asks again"
    )
    void_parser.add_argument("--turn-id", required=True)
    void_parser.add_argument("--reason", required=True, help="why the answer cannot be used")
    void_parser.set_defaults(func=_cmd_host_model_void)

    status_parser = host_sub.add_parser("status", help="read-only handoff summary")
    status_parser.add_argument("--limit", type=int, default=20)
    status_parser.set_defaults(func=_cmd_host_model_status)

    study = sub.add_parser(
        "study",
        help="locally executable improvement-search studies (memory x gate factorial)",
    )
    study_sub = study.add_subparsers(dest="study_command", required=True)

    profiles_parser = study_sub.add_parser("profiles", help="what the runtime can execute")
    profiles_parser.set_defaults(func=_cmd_study_profiles)

    search_parser = study_sub.add_parser(
        "search", help="run a declared factorial over the registered search controls"
    )
    search_parser.add_argument("--project", default="research-project")
    search_parser.add_argument("--output-dir", default="")
    search_parser.add_argument("--dataset", default="iris", choices=["iris", "breast_cancer", "wine", "digits"])
    search_parser.add_argument("--seeds", default="", help="comma-separated seeds; empty uses default")
    search_parser.add_argument("--budget", type=int, default=60)
    search_parser.add_argument("--min-delta", type=float, default=0.005)
    search_parser.add_argument(
        "--factors",
        action="append",
        default=[],
        metavar="FACTOR=LEVEL[,LEVEL...]",
        help="declare the design (memory, gate, operators, min_delta, archive, archive_window, parent_selection); first level is the "
        "reference cell; archive=negative needs gate=on; omit for the memory x gate 2x2",
    )
    search_parser.add_argument(
        "--preregistration",
        default="",
        help="JSON plan (question/hypothesis/analysis/decision_rule/design/seeds/budget/dataset) "
        "declared before the run; bound to the study by hash",
    )
    search_parser.set_defaults(func=_cmd_study_search)

    prereg_sub = study_sub.add_parser("prereg", help="pre-registration tooling")
    prereg_actions = prereg_sub.add_subparsers(dest="study_prereg_action")
    prereg_init = prereg_actions.add_parser(
        "init",
        help="scaffold a pre-registration: facts filled, research promises left as explicit placeholders",
    )
    prereg_init.add_argument("--dataset", required=True)
    prereg_init.add_argument("--seeds", required=True, help="comma-separated seeds")
    prereg_init.add_argument("--budget", type=int, required=True)
    prereg_init.add_argument(
        "--factors",
        action="append",
        default=[],
        help="declared factor levels, factor=a,b; the first level is the reference cell",
    )
    prereg_init.add_argument("--min-delta", type=float, default=None)
    prereg_init.add_argument("--output", default="", help="write the JSON here (default: stdout only)")
    prereg_init.set_defaults(func=_cmd_study_prereg_init)

    from_idea_parser = study_sub.add_parser(
        "from-idea",
        help="execute the declared design an idea's experiment_plan asked for",
    )
    from_idea_parser.add_argument("--project", required=True)
    from_idea_parser.add_argument("--run-id", required=True)
    from_idea_parser.add_argument("--idea-id", required=True)
    from_idea_parser.add_argument("--seeds", default="", help="comma-separated seeds; empty uses 1..8")
    from_idea_parser.add_argument("--budget", type=int, default=60)
    from_idea_parser.add_argument("--output-root", default="", help="defaults to <project>/studies")
    from_idea_parser.add_argument(
        "--datasets",
        default="",
        help="execute the same declared design on several environments (comma list or 'all'); "
        "each package keeps the idea's provenance so a generalising result stays traceable",
    )
    from_idea_parser.add_argument(
        "--preregistration",
        default="",
        help=(
            "JSON plan declared before the run, validated against the idea's resolved design "
            "before anything is computed; the same file `study search --preregistration` takes. "
            "Without it an idea-attributed study could never carry a pre-registration."
        ),
    )
    from_idea_parser.add_argument("--force", action="store_true")
    from_idea_parser.set_defaults(func=_cmd_study_from_idea)

    claim_parser = study_sub.add_parser(
        "claim",
        help="draft a signable claim from a study; only interval-decidable comparisons qualify",
    )
    claim_parser.add_argument("--study-dir", required=True)
    claim_parser.add_argument("--statement", required=True)
    claim_parser.add_argument("--scope", required=True)
    claim_parser.add_argument("--human-reason", required=True)
    claim_parser.add_argument(
        "--baseline-file",
        default="",
        help=(
            "optional tuned-baseline report from `study baseline --output`: copied into the "
            "package byte-for-byte as tuned-baseline.json and hash-bound to this claim"
        ),
    )
    claim_parser.add_argument(
        "--sign",
        action="store_true",
        help="record this human act as an accepted claim, not only a draft",
    )
    claim_parser.add_argument(
        "--no-guard",
        action="store_true",
        help=(
            "counterfactual arm for the guard experiment: keep overturned comparisons in the draft. "
            "Writes claim-draft-unguarded.json and can never sign."
        ),
    )
    claim_parser.set_defaults(func=_cmd_study_claim)

    brief_parser = study_sub.add_parser(
        "brief",
        help="render the human signing brief for a study package from its artifacts (read-only)",
    )
    brief_parser.add_argument("--study-dir", required=True)
    brief_parser.add_argument("--output", default="", help="write the markdown brief to this path")
    brief_parser.add_argument(
        "--language",
        choices=["zh", "en"],
        default="zh",
        help=(
            "label language of the brief; it changes no number, verdict or hash. English venues "
            "need this because a Chinese-labelled brief is scored as mixed script by the English "
            "rubric packs (see study brief #51)."
        ),
    )
    brief_parser.set_defaults(func=_cmd_study_brief)

    package_parser = study_sub.add_parser(
        "package",
        help="project one study package into a reader-facing README.md + MANIFEST.json (read-only over artifacts)",
    )
    package_parser.add_argument("--study-dir", required=True)
    package_parser.add_argument("--output", default="", help="where to write README.md/MANIFEST.json")
    package_parser.add_argument("--language", choices=["zh", "en"], default="zh")
    package_parser.set_defaults(func=_cmd_study_package)

    closure_parser = study_sub.add_parser(
        "closure",
        help="check, sign or lineage-verify a study package (human signature stays local)",
    )
    closure_parser.add_argument("--study-dir", required=True)
    closure_parser.add_argument("--sign", action="store_true")
    closure_parser.add_argument("--human-reason", default="")
    closure_parser.add_argument("--signer", default="")
    closure_parser.add_argument("--build-lineage", action="store_true")
    closure_parser.add_argument("--verify", action="store_true")
    closure_parser.add_argument(
        "--verify-repro",
        action="store_true",
        help="re-run this package's own controls and compare the study hash (slow, opt-in)",
    )
    closure_parser.set_defaults(func=_cmd_study_closure)

    saturation_parser = study_sub.add_parser(
        "saturation",
        help=(
            "post-hoc ceiling sensitivity for a recorded 2x2 study: ceiling share plus "
            "headroom-normalized anytime interactions (never signs)"
        ),
    )
    saturation_parser.add_argument("--study-dir", required=True)
    saturation_parser.set_defaults(func=_cmd_study_saturation)

    replicate_parser = study_sub.add_parser(
        "replicate",
        help=(
            "read-only: group executed studies by design and count how many datasets decide each "
            "comparison (re-runs the search on another dataset with `study search`)"
        ),
    )
    replicate_parser.add_argument("--project", default="", help="research project root")
    replicate_parser.add_argument("--studies-dir", default="", help="override <project>/studies")
    replicate_parser.add_argument("--output-dir", default="")
    replicate_parser.add_argument(
        "--project-only",
        action="store_true",
        help="ignore sibling projects' studies; by default they are included, because a verdict "
        "overturned by a higher-power study next door is still overturned",
    )
    replicate_parser.set_defaults(func=_cmd_study_replicate)

    baseline_parser = study_sub.add_parser(
        "baseline",
        help="tune a strong cross-validation reference and pair it with a study artifact",
    )
    baseline_parser.add_argument("--study", default="", help="study.json to compare against")
    baseline_parser.add_argument("--dataset", default="iris,breast_cancer,wine,digits")
    baseline_parser.add_argument("--seeds", default="", help="comma-separated seeds")
    baseline_parser.add_argument(
        "--folds", type=int, default=0, help="0 = use the largest fold count the budget affords"
    )
    baseline_parser.add_argument("--output", default="")
    baseline_parser.add_argument(
        "--markdown",
        default="",
        help="also write the table rendered from these artifacts, header and rows from one column spec",
    )
    baseline_parser.add_argument(
        "--title",
        default="",
        help="heading for the markdown table; kept here so the table is never hand-edited",
    )
    baseline_parser.add_argument(
        "--table-from",
        default="",
        help=(
            "comma-separated tuned-baseline report JSONs to render as one table without computing "
            "anything; read-only projection, it does not re-run the grid"
        ),
    )
    baseline_parser.set_defaults(func=_cmd_study_baseline)

    memory = sub.add_parser(
        "memory",
        help="run-wide guideline memory (deterministic bookkeeping; never touches claims or gates)",
    )
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    guidelines_parser = memory_sub.add_parser(
        "guidelines",
        help="merge or show the confirmed lessons that get appended to idea generation",
    )
    guidelines_parser.add_argument("--project", required=True)
    guidelines_parser.add_argument(
        "--propose-file",
        default="",
        help="JSON list of {text: 'trigger -> mechanism -> action', sources: [artifact paths]}",
    )
    guidelines_parser.add_argument("--step", default="0")
    guidelines_parser.add_argument(
        "--admission",
        default="store_all",
        help="memory admission strategy: store_all (default) | store_none | replay_then_store | independent_verify_then_store",
    )
    guidelines_parser.set_defaults(func=_cmd_memory_guidelines)

    ab_parser = memory_sub.add_parser(
        "ab",
        help=(
            "paired A/B of the guideline block: same request with and without it, scored by the "
            "runtime's own deterministic checks"
        ),
    )
    ab_sub = ab_parser.add_subparsers(dest="ab_command", required=True)
    ab_record = ab_sub.add_parser("record", help="score and store one arm's ideas")
    ab_record.add_argument("--project", required=True)
    ab_record.add_argument("--run-id", required=True)
    ab_record.add_argument("--arm", required=True, choices=["with", "without"])
    ab_record.add_argument("--ideas-file", required=True)
    ab_record.add_argument("--literature-file", required=True)
    ab_record.add_argument("--session-host-label", default="", help="host session label answering this arm (required for multi-session compare)")
    ab_record.add_argument("--session-id", default="")
    ab_record.set_defaults(func=_cmd_memory_ab)
    ab_compare = ab_sub.add_parser("compare", help="paired read-out of the two recorded arms")
    ab_compare.add_argument("--project", required=True)
    ab_compare.add_argument("--output-dir", default="")
    ab_compare.add_argument(
        "--sessions",
        default="single",
        choices=["single", "multi"],
        help="single: same host session answered both arms (traditional, cannot rule out same-source bias); multi: distinct host sessions per arm (enforced)",
    )
    ab_compare.set_defaults(func=_cmd_memory_ab)
    ab_plan = ab_sub.add_parser("plan", help="print the two commands that make the arms")
    ab_plan.add_argument("--project", required=True)
    ab_plan.add_argument("--run-id", required=True)
    ab_plan.set_defaults(func=_cmd_memory_ab)

    literature = sub.add_parser("literature", help="run the S1 literature subagent")
    literature_sub = literature.add_subparsers(dest="literature_command", required=True)
    run_parser = literature_sub.add_parser("run", help="run S1 retrieval (fixture or OpenAlex)")
    run_parser.add_argument("--question", required=True)
    run_parser.add_argument("--max-sources", type=int, default=12)
    run_parser.add_argument("--source", choices=["fixture", "local", "openalex"], default="fixture")
    run_parser.add_argument("--corpus-dir", default="", help="local PDF/TXT/MD corpus directory")
    run_parser.add_argument("--mailto", default="", help="OpenAlex polite-pool email (or OPENALEX_EMAIL)")
    run_parser.add_argument("--planner", default="gateway", help="rule | glm | gateway | profile:<id>；无 key 自动回退规则模板")
    run_parser.add_argument("--fixture")
    run_parser.add_argument("--run-id")
    run_parser.set_defaults(func=_cmd_literature_run)

    fetch_parser = literature_sub.add_parser(
        "fetch", help="search arXiv and download explicit open PDFs into a corpus"
    )
    fetch_parser.add_argument("--query", required=True)
    fetch_parser.add_argument("--target-dir", required=True, help="usually <project>/inputs")
    fetch_parser.add_argument("--max-results", type=int, default=4, choices=range(1, 11))
    fetch_parser.add_argument("--timeout", type=int, default=30)
    fetch_parser.add_argument(
        "--allow-network",
        action="store_true",
        help="explicitly allow arxiv.org network search/download",
    )
    fetch_parser.set_defaults(func=_cmd_literature_fetch)

    discover_parser = literature_sub.add_parser(
        "discover",
        help="collect clue-only candidate papers from arXiv + HF Daily/Trending",
    )
    discover_parser.add_argument("--query", default="", help="arXiv keyword query")
    discover_parser.add_argument(
        "--sources", default="arxiv,hf_daily,hf_trending",
        help="comma-separated: arxiv, hf_daily, hf_trending",
    )
    discover_parser.add_argument("--limit-per-source", type=int, default=10)
    discover_parser.add_argument("--timeout", type=int, default=6)
    discover_parser.add_argument("--output", default="", help="optional JSON output path")
    discover_parser.add_argument(
        "--allow-network", action="store_true",
        help="explicitly allow public API calls (off by default)",
    )
    discover_parser.set_defaults(func=_cmd_literature_discover)

    prescreen_parser = literature_sub.add_parser(
        "prescreen",
        help="deterministic Stage1 filter + explainable ranking of clue-only candidates",
    )
    prescreen_parser.add_argument("--input", required=True, help="candidates JSON (list or DiscoveryReport)")
    prescreen_parser.add_argument("--query", required=True)
    prescreen_parser.add_argument("--abstracts", default="", help="optional id->abstract JSON map")
    prescreen_parser.add_argument("--min-hits", type=int, default=1)
    prescreen_parser.add_argument("--exclude-terms", default="", help="comma-separated")
    prescreen_parser.add_argument("--output", default="", help="optional JSON output path")
    prescreen_parser.set_defaults(func=_cmd_literature_prescreen)

    synth_parser = literature_sub.add_parser(
        "synthesize", help="build a theme-by-source synthesis matrix from a run"
    )
    synth_parser.add_argument("--project", required=True)
    synth_parser.add_argument("--run-id", required=True)
    synth_parser.add_argument("--max-themes", type=int, default=7)
    synth_parser.add_argument("--output-dir", default="")
    synth_parser.set_defaults(func=_cmd_literature_synthesize)

    conference = sub.add_parser("conference", help="fetch recent top-conference arXiv PDFs")
    conference_sub = conference.add_subparsers(dest="conference_command", required=True)
    conference_fetch = conference_sub.add_parser(
        "fetch", help="bounded venue/year arXiv corpus with provenance"
    )
    conference_fetch.add_argument("--target-dir", required=True, help="usually <project>/inputs")
    conference_fetch.add_argument("--topic", default="LLM agents scientific discovery self-improvement")
    conference_fetch.add_argument(
        "--venues", default="NeurIPS,ICLR,ICML,ACL",
        help="comma-separated: NeurIPS,ICLR,ICML,ACL,EMNLP,AAAI,CVPR,KDD",
    )
    conference_fetch.add_argument("--years", default="2024,2025,2026", help="comma-separated years")
    conference_fetch.add_argument("--max-papers", type=int, default=24)
    conference_fetch.add_argument("--max-per-venue", type=int, default=4)
    conference_fetch.add_argument("--allow-network", action="store_true")
    conference_fetch.set_defaults(func=_cmd_conference_fetch)

    memory_parser = literature_sub.add_parser("memory", help="inspect process-level literature memory")
    memory_sub = memory_parser.add_subparsers(dest="memory_command", required=True)
    memory_show = memory_sub.add_parser("show", help="show facet coverage/yield memory")
    memory_show.add_argument("--memory-path", default=str(DEFAULT_LITERATURE_MEMORY_PATH))
    memory_show.add_argument("--limit", type=int, default=20)
    memory_show.add_argument("--output")
    memory_show.set_defaults(func=_cmd_literature_memory)
    memory_advise = memory_sub.add_parser("advise", help="suggest next facet order and budget")
    memory_advise.add_argument("--question", required=True)
    memory_advise.add_argument("--max-sources", type=int, default=12)
    memory_advise.add_argument("--source", choices=["fixture", "real", "openalex"], default="fixture")
    memory_advise.add_argument("--memory-path", default=str(DEFAULT_LITERATURE_MEMORY_PATH))
    memory_advise.add_argument("--output")
    memory_advise.set_defaults(func=_cmd_literature_memory)

    orchestrate = sub.add_parser("orchestrate", help="typed multi-agent S1 fan-out and S2/S3 fan-in")
    orchestrate_sub = orchestrate.add_subparsers(dest="orchestrate_command", required=True)
    orchestrate_plan = orchestrate_sub.add_parser("plan", help="show roles, handoffs, gates and facet budgets")
    orchestrate_plan.add_argument("--topic", required=True)
    orchestrate_plan.add_argument("--max-sources", type=int, default=12)
    orchestrate_plan.add_argument("--source", choices=["fixture", "real"], default="fixture")
    orchestrate_plan.add_argument("--memory-path", default=str(DEFAULT_LITERATURE_MEMORY_PATH))
    orchestrate_plan.add_argument("--custom-agents-path", default=str(DEFAULT_CUSTOM_AGENTS_PATH))
    orchestrate_plan.add_argument("--policy-path", default=str(DEFAULT_EVOLUTION_POLICY_PATH))
    orchestrate_plan.set_defaults(func=_cmd_orchestrate_plan)
    orchestrate_run = orchestrate_sub.add_parser("run", help="run scout fan-out, coverage merge and idea fan-in")
    orchestrate_run.add_argument("--topic", required=True)
    orchestrate_run.add_argument("--max-sources", type=int, default=12)
    orchestrate_run.add_argument("--source", choices=["fixture", "real"], default="fixture")
    orchestrate_run.add_argument("--corpus")
    orchestrate_run.add_argument("--memory-path", default=str(DEFAULT_LITERATURE_MEMORY_PATH))
    orchestrate_run.add_argument("--custom-agents-path", default=str(DEFAULT_CUSTOM_AGENTS_PATH))
    orchestrate_run.add_argument("--policy-path", default=str(DEFAULT_EVOLUTION_POLICY_PATH))
    orchestrate_run.add_argument("--max-workers", type=int)
    orchestrate_run.add_argument("--output-dir")
    orchestrate_run.add_argument("--summary-out")
    orchestrate_run.set_defaults(func=_cmd_orchestrate_run)

    agent_parser = sub.add_parser("agent", help="manage user-registered advisory subagents")
    agent_sub = agent_parser.add_subparsers(dest="agent_command", required=True)
    agent_list = agent_sub.add_parser("list")
    agent_list.add_argument("--custom-agents-path", default=str(DEFAULT_CUSTOM_AGENTS_PATH))
    agent_list.set_defaults(func=_cmd_agent)
    agent_add = agent_sub.add_parser("add")
    agent_add.add_argument("--name", required=True)
    agent_add.add_argument("--role", required=True, choices=["reviewer", "auditor", "scout", "methodologist", "writer-assistant"])
    agent_add.add_argument("--purpose", required=True)
    agent_add.add_argument("--check", action="append", required=True, choices=["coverage", "citation", "hypothesis", "protocol", "evidence", "figure", "closure"])
    agent_add.add_argument("--disabled", action="store_true")
    agent_add.add_argument("--custom-agents-path", default=str(DEFAULT_CUSTOM_AGENTS_PATH))
    agent_add.set_defaults(func=_cmd_agent)
    agent_toggle = agent_sub.add_parser("toggle")
    agent_toggle.add_argument("id")
    agent_toggle.add_argument("--enabled", action="store_true")
    agent_toggle.add_argument("--disabled", action="store_true")
    agent_toggle.add_argument("--custom-agents-path", default=str(DEFAULT_CUSTOM_AGENTS_PATH))
    agent_toggle.set_defaults(func=_cmd_agent)
    agent_delete = agent_sub.add_parser("delete")
    agent_delete.add_argument("id")
    agent_delete.add_argument("--custom-agents-path", default=str(DEFAULT_CUSTOM_AGENTS_PATH))
    agent_delete.set_defaults(func=_cmd_agent)
    agent_export = agent_sub.add_parser("export")
    agent_export.add_argument("--custom-agents-path", default=str(DEFAULT_CUSTOM_AGENTS_PATH))
    agent_export.add_argument("--output", default="apps/web/public/custom-agents.json")
    agent_export.set_defaults(func=_cmd_agent)

    skill_parser = sub.add_parser("skill", help="scan and inspect local Agent Skills (SKILL.md)")
    skill_sub = skill_parser.add_subparsers(dest="skill_command", required=True)
    skill_list = skill_sub.add_parser("list")
    skill_list.add_argument("--registry-path", default=str(DEFAULT_SKILL_REGISTRY_PATH))
    skill_list.set_defaults(func=_cmd_skill)
    skill_scan = skill_sub.add_parser("scan")
    skill_scan.add_argument("--path", required=True)
    skill_scan.add_argument("--registry-path", default=str(DEFAULT_SKILL_REGISTRY_PATH))
    skill_scan.set_defaults(func=_cmd_skill)
    skill_enable = skill_sub.add_parser("enable")
    skill_enable.add_argument("id")
    skill_enable.add_argument("--registry-path", default=str(DEFAULT_SKILL_REGISTRY_PATH))
    skill_enable.set_defaults(func=_cmd_skill)
    skill_disable = skill_sub.add_parser("disable")
    skill_disable.add_argument("id")
    skill_disable.add_argument("--registry-path", default=str(DEFAULT_SKILL_REGISTRY_PATH))
    skill_disable.set_defaults(func=_cmd_skill)
    skill_delete = skill_sub.add_parser("delete")
    skill_delete.add_argument("id")
    skill_delete.add_argument("--registry-path", default=str(DEFAULT_SKILL_REGISTRY_PATH))
    skill_delete.set_defaults(func=_cmd_skill)
    skill_export = skill_sub.add_parser("export")
    skill_export.add_argument("--registry-path", default=str(DEFAULT_SKILL_REGISTRY_PATH))
    skill_export.add_argument("--output", default="apps/web/public/skills.json")
    skill_export.set_defaults(func=_cmd_skill)
    skill_lint = skill_sub.add_parser("lint", help="static manifest/path lint for skill packages")
    skill_lint.add_argument("--path", default=".qoder/skills")
    skill_lint.set_defaults(func=_cmd_skill_lint)
    skill_journal_verify = skill_sub.add_parser(
        "journal-verify",
        help="verify external journal SKILL.md/license bytes against the local skill profile",
    )
    skill_journal_verify.add_argument("--pack-root", required=True, help="Awesome-Journal-Skills root")
    skill_journal_verify.add_argument("--profiles", default="", help="optional profiles JSON")
    skill_journal_verify.set_defaults(func=_cmd_skill_journal_verify)
    from .skill_packs import DEFAULT_MAX_ITEMS  # one rubric-window default for every face

    skill_pack = skill_sub.add_parser(
        "pack",
        help="extract auditable rubric data (license/provenance/checklists) from a local SKILL pack",
    )
    skill_pack.add_argument("--path", required=True)
    skill_pack.add_argument("--stage", choices=["", "idea", "design", "writing", "submission", "review", "reproducibility", "general"], default="")
    skill_pack.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    skill_pack.add_argument("--output", default="")
    skill_pack.set_defaults(func=_cmd_skill_pack)
    skill_route = skill_sub.add_parser(
        "route",
        help="route a venue to a local SKILL pack via shared-resources/journal-selection/venue-index.tsv",
    )
    skill_route.add_argument("--root", required=True, help="Awesome-Journal-Skills root")
    skill_route.add_argument("--venue", required=True, help="venue display name or id")
    skill_route.add_argument("--with-checklist", action="store_true")
    skill_route.add_argument("--stage", choices=["", "idea", "design", "writing", "submission", "review", "reproducibility", "general"], default="")
    skill_route.add_argument("--max-items", type=int, default=40)
    skill_route.set_defaults(func=_cmd_skill_route)

    skill_coverage = skill_sub.add_parser(
        "coverage",
        help=(
            "score an artifact, a draft, or a whole package directory against a local SKILL "
            "pack's actionable rubric (advisory)"
        ),
    )
    skill_coverage.add_argument(
        "--pack", help="local SKILL pack directory; or route with --pack-root plus --venue"
    )
    skill_coverage.add_argument("--pack-root", help="root of available packs, used with --venue")
    skill_coverage.add_argument("--venue", help="venue name or id to route to a pack")
    skill_coverage.add_argument(
        "--file",
        required=True,
        help=(
            "artifact to check: JSON design/plan or md/tex/txt draft, or a whole package directory "
            "scored as one bundle (the file list and excluded numeric artifacts are reported)"
        ),
    )
    skill_coverage.add_argument(
        "--stage",
        choices=["", "idea", "design", "writing", "submission", "review", "reproducibility", "general"],
        default="",
    )
    skill_coverage.add_argument(
        "--profile",
        choices=["", "design", "draft", "submission", "revision"],
        default="",
        help="stage profile instead of a single stage",
    )
    skill_coverage.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    skill_coverage.add_argument("--output", default="")
    skill_coverage.set_defaults(func=_cmd_skill_coverage)

    mandate = sub.add_parser(
        "mandate",
        help="read-only projection of a human-authored research mandate over existing runs",
    )
    mandate_sub = mandate.add_subparsers(dest="mandate_command", required=True)
    mandate_status = mandate_sub.add_parser(
        "status",
        help="aggregate run-capsule blockers/next-actions and autopilot policy into a mandate view",
    )
    mandate_status.add_argument("--project", required=True)
    mandate_status.add_argument("--max-runs", type=int, default=20)
    mandate_status.add_argument("--output", default="")
    mandate_status.set_defaults(func=_cmd_mandate_status)
    skill_invoke = skill_sub.add_parser(
        "invoke", help="invoke an enabled instruction-only external skill as advisory"
    )
    skill_invoke.add_argument("--skill-id", required=True)
    skill_invoke.add_argument("--profile", default="", help="runtime model profile id (instruction-only)")
    skill_invoke.add_argument(
        "--trusted-scripts",
        action="store_true",
        help="run a script-bearing skill locally with the user's OS permissions (not sandboxed)",
    )
    skill_invoke.add_argument("--workdir", default="", help="working directory for trusted script execution")
    skill_invoke.add_argument(
        "--script-arg",
        action="append",
        default=[],
        help="argument passed directly to a trusted script (no shell; repeatable)",
    )
    skill_invoke.add_argument("--timeout", type=int, default=60)
    skill_invoke.add_argument("--input", default="")
    skill_invoke.add_argument("--input-file", default="")
    skill_invoke.add_argument("--context-file", default="")
    skill_invoke.add_argument("--output", default="")
    skill_invoke.add_argument("--registry-path", default=str(DEFAULT_SKILL_REGISTRY_PATH))
    skill_invoke.add_argument("--usage-path", default=str(DEFAULT_SKILL_USAGE_PATH))
    skill_invoke.add_argument("--store", default="")
    skill_invoke.add_argument(
        "--distill-on-success",
        action="store_true",
        help="after a successful invocation, register a disabled local candidate",
    )
    skill_invoke.add_argument("--distill-license", default="")
    skill_invoke.add_argument("--distill-reason", default="")
    skill_invoke.add_argument("--distill-source-url", default="")
    skill_invoke.add_argument(
        "--library-dir",
        default=str(DEFAULT_SKILL_LIBRARY_ROOT),
        help="local distillation library (default: runtime_data/skill-library)",
    )
    skill_invoke.set_defaults(func=_cmd_skill_invoke)

    skill_distill = skill_sub.add_parser(
        "distill", help="copy an enabled external skill into a disabled local candidate"
    )
    skill_distill.add_argument("--skill-id", required=True)
    skill_distill.add_argument("--license", default="")
    skill_distill.add_argument("--source-url", default="")
    skill_distill.add_argument("--human-reason", required=True)
    skill_distill.add_argument("--library-dir", default=str(DEFAULT_SKILL_LIBRARY_ROOT))
    skill_distill.add_argument("--registry-path", default=str(DEFAULT_SKILL_REGISTRY_PATH))
    skill_distill.set_defaults(func=_cmd_skill_distill)

    skill_lab_common = argparse.ArgumentParser(add_help=False)
    skill_lab_common.add_argument("--registry-path", default="")
    skill_lab_common.add_argument("--usage-path", default="")
    skill_lab_common.add_argument("--eval-root", default="")
    skill_lab_common.add_argument("--ledger", default="")
    skill_lab_common.add_argument("--policy-path", default="")
    skill_lab_common.add_argument("--versions-path", default="")

    skill_usage = skill_sub.add_parser("usage", help="record and inspect skill usage evidence")
    skill_usage_sub = skill_usage.add_subparsers(dest="usage_command", required=True)
    skill_usage_record = skill_usage_sub.add_parser("record", parents=[skill_lab_common])
    skill_usage_record.add_argument("--skill-id", required=True)
    skill_usage_record.add_argument("--status", required=True, choices=["pass", "warn", "fail", "blocked", "needs_input"])
    skill_usage_record.add_argument("--task-id", default="")
    skill_usage_record.add_argument("--check", action="append")
    skill_usage_record.add_argument("--artifact-ref", default="")
    skill_usage_record.add_argument("--note", default="")
    skill_usage_record.set_defaults(func=_cmd_skill_usage)
    skill_usage_list = skill_usage_sub.add_parser("list", parents=[skill_lab_common])
    skill_usage_list.add_argument("--skill-id", default="")
    skill_usage_list.add_argument("--limit", type=int, default=50)
    skill_usage_list.set_defaults(func=_cmd_skill_usage)
    skill_usage_summary = skill_usage_sub.add_parser("summary", parents=[skill_lab_common])
    skill_usage_summary.set_defaults(func=_cmd_skill_usage)

    skill_eval = skill_sub.add_parser("eval", parents=[skill_lab_common], help="run deterministic built-in skill regression cases")
    skill_eval.add_argument("--skill-id", required=True)
    skill_eval.add_argument("--split", choices=["public", "hidden", "all"], default="all")
    skill_eval.add_argument("--version", default="", help="evaluate a specific built-in version")
    skill_eval.set_defaults(func=_cmd_skill_eval)

    skill_version = skill_sub.add_parser("version", help="inspect, activate or roll back built-in skill versions")
    skill_version_sub = skill_version.add_subparsers(dest="version_command", required=True)
    skill_version_list = skill_version_sub.add_parser("list", parents=[skill_lab_common])
    skill_version_list.set_defaults(func=_cmd_skill_version)
    skill_version_activate = skill_version_sub.add_parser("activate", parents=[skill_lab_common])
    skill_version_activate.add_argument("--skill-id", required=True)
    skill_version_activate.add_argument("--version", required=True)
    skill_version_activate.add_argument("--eval-report", required=True)
    skill_version_activate.add_argument("--human-reason", required=True)
    skill_version_activate.set_defaults(func=_cmd_skill_version)
    skill_version_rollback = skill_version_sub.add_parser("rollback", parents=[skill_lab_common])
    skill_version_rollback.add_argument("--skill-id", required=True)
    skill_version_rollback.add_argument("--human-reason", required=True)
    skill_version_rollback.set_defaults(func=_cmd_skill_version)

    skill_propose = skill_sub.add_parser("propose", parents=[skill_lab_common], help="create a pending RSI skill candidate")
    skill_propose.add_argument("--skill-id", required=True)
    skill_propose.add_argument("--patch", required=True)
    skill_propose.add_argument("--rationale", required=True)
    skill_propose.add_argument("--predicted", required=True)
    skill_propose.add_argument("--dry-run-ref", default="")
    skill_propose.add_argument("--observation", default="")
    skill_propose.set_defaults(func=_cmd_skill_propose)

    experiment_parser = sub.add_parser("experiment", help="experiment design and local code package")
    experiment_sub = experiment_parser.add_subparsers(dest="experiment_command", required=True)
    experiment_closure = experiment_sub.add_parser("closure", help="check experiment closure and artifact hashes")
    experiment_closure.add_argument("--project", required=True)
    experiment_closure.add_argument("--experiment-id", required=True)
    experiment_closure.add_argument("--manuscript", default="")
    experiment_closure.add_argument("--output-dir", default="")
    experiment_closure.set_defaults(func=_cmd_experiment_closure)
    experiment_sign = experiment_sub.add_parser("sign", help="human-signed experiment closure (CLI only)")
    experiment_sign.add_argument("--project", required=True)
    experiment_sign.add_argument("--experiment-id", required=True)
    experiment_sign.add_argument("--report", required=True)
    experiment_sign.add_argument("--human-reason", required=True)
    experiment_sign.add_argument("--manuscript", default="")
    experiment_sign.add_argument("--signer-id", default="")
    experiment_sign.add_argument("--signer-store", default="")
    experiment_sign.add_argument("--output-dir", default="")
    experiment_sign.set_defaults(func=_cmd_experiment_closure)
    experiment_lineage = experiment_sub.add_parser("lineage", help="build or verify experiment lineage")
    experiment_lineage.add_argument("--project", required=True)
    experiment_lineage.add_argument("--experiment-id", required=True)
    experiment_lineage.add_argument("--verify", action="store_true")
    experiment_lineage.add_argument("--lineage", default="")
    experiment_lineage.add_argument("--output-dir", default="")
    experiment_lineage.set_defaults(func=_cmd_experiment_closure)

    experiment_figure = experiment_sub.add_parser(
        "figure", help="generate or verify a data-backed result figure from verified evidence"
    )
    experiment_figure.add_argument("--project", required=True)
    experiment_figure.add_argument("--experiment-id", required=True)
    experiment_figure.add_argument("--output-dir", default="")
    experiment_figure.add_argument("--verify", action="store_true")
    experiment_figure.add_argument("--manifest", default="")
    experiment_figure.set_defaults(func=_cmd_experiment_figure)
    experiment_status = experiment_sub.add_parser("status", help="read-only lifecycle status for one experiment")
    experiment_status.add_argument("--project", required=True)
    experiment_status.add_argument("--experiment-id", required=True)
    experiment_status.set_defaults(func=_cmd_experiment_status)
    experiment_consistency = experiment_sub.add_parser(
        "consistency-registry",
        help="derive a read-only external consistency registry from verified evidence",
    )
    experiment_consistency.add_argument("--project", required=True)
    experiment_consistency.add_argument("--experiment-id", required=True)
    experiment_consistency.add_argument(
        "--output", required=True, help="project-relative registry JSON output path"
    )
    experiment_consistency.set_defaults(func=_cmd_experiment_consistency)
    experiment_preflight = experiment_sub.add_parser(
        "preflight", help="dry-run schema/import validation without training or approval"
    )
    experiment_preflight.add_argument("--project", required=True)
    experiment_preflight.add_argument("--experiment-id", required=True)
    experiment_preflight.add_argument("--python", default="")
    experiment_preflight.add_argument("--timeout", type=int, default=60)
    experiment_preflight.set_defaults(func=_cmd_experiment_preflight)

    experiment_approve = experiment_sub.add_parser("approve", help="human approval for local execution")
    experiment_approve.add_argument("--project", required=True)
    experiment_approve.add_argument("--experiment-id", required=True)
    experiment_approve.add_argument("--human-reason", required=True)
    experiment_approve.add_argument("--timeout", type=int, default=7200)
    experiment_approve.add_argument(
        "--ridge-alpha", type=float, default=None, help="confirmatory ridge alpha from a sweep"
    )
    experiment_approve.set_defaults(func=_cmd_experiment_lifecycle)
    experiment_run = experiment_sub.add_parser("run", help="explicit local execution of a generated package")
    experiment_run.add_argument("--project", required=True)
    experiment_run.add_argument("--experiment-id", required=True)
    experiment_run.add_argument("--allow-execute", action="store_true")
    experiment_run.add_argument("--python", default="")
    experiment_run.add_argument("--timeout", type=int, default=0)
    experiment_run.add_argument("--dry-run", action="store_true")
    experiment_run.add_argument(
        "--ridge-alpha", type=float, default=None, help="must match the approved ridge alpha"
    )
    experiment_run.set_defaults(func=_cmd_experiment_lifecycle)
    experiment_ingest = experiment_sub.add_parser("ingest", help="verify execution hashes and metrics into evidence")
    experiment_ingest.add_argument("--project", required=True)
    experiment_ingest.add_argument("--experiment-id", required=True)
    experiment_ingest.set_defaults(func=_cmd_experiment_lifecycle)
    experiment_claim = experiment_sub.add_parser("claim", help="human-signed local experiment claim (CLI only)")
    experiment_claim.add_argument("--project", required=True)
    experiment_claim.add_argument("--experiment-id", required=True)
    experiment_claim.add_argument("--statement", required=True)
    experiment_claim.add_argument("--human-reason", required=True)
    experiment_claim.add_argument("--assertion", action="append", default=[])
    experiment_claim.set_defaults(func=_cmd_experiment_lifecycle)

    local_init = experiment_sub.add_parser(
        "local-init", help="register a human-specified local command experiment (Codex-like, CLI only)"
    )
    local_init.add_argument("--project", required=True)
    local_init.add_argument("--experiment-id", required=True)
    local_init.add_argument("--command", required=True, help="command parsed to argv (no shell)")
    local_init.add_argument("--cwd", default="")
    local_init.add_argument("--env-prefix", default="", help="argv prefix e.g. 'conda run -n myenv' (no shell)")
    local_init.add_argument("--expect", action="append", default=[], help="expected output file (repeatable)")
    local_init.add_argument("--timeout", type=int, default=3600)
    local_init.set_defaults(func=_cmd_experiment_local)
    local_approve = experiment_sub.add_parser("local-approve", help="human approval for a local command experiment")
    local_approve.add_argument("--project", required=True)
    local_approve.add_argument("--experiment-id", required=True)
    local_approve.add_argument("--human-reason", required=True)
    local_approve.set_defaults(func=_cmd_experiment_local)
    local_run = experiment_sub.add_parser(
        "local-run", help="explicit local execution of the registered command (requires approve + --allow-execute)"
    )
    local_run.add_argument("--project", required=True)
    local_run.add_argument("--experiment-id", required=True)
    local_run.add_argument("--allow-execute", action="store_true")
    local_run.add_argument("--timeout", type=int, default=0)
    local_run.set_defaults(func=_cmd_experiment_local)
    local_ingest = experiment_sub.add_parser("local-ingest", help="verify local execution hashes into evidence")
    local_ingest.add_argument("--project", required=True)
    local_ingest.add_argument("--experiment-id", required=True)
    local_ingest.set_defaults(func=_cmd_experiment_local)

    sweep_approve = experiment_sub.add_parser(
        "sweep-approve", help="human approval for the generated local sweep script"
    )
    sweep_approve.add_argument("--project", required=True)
    sweep_approve.add_argument("--experiment-id", required=True)
    sweep_approve.add_argument("--human-reason", required=True)
    sweep_approve.add_argument("--timeout", type=int, default=7200)
    sweep_approve.set_defaults(func=_cmd_experiment_sweep)
    sweep_run = experiment_sub.add_parser(
        "sweep-run", help="explicit local execution of run_sweep.py"
    )
    sweep_run.add_argument("--project", required=True)
    sweep_run.add_argument("--experiment-id", required=True)
    sweep_run.add_argument("--allow-execute", action="store_true")
    sweep_run.add_argument("--python", default="")
    sweep_run.add_argument("--timeout", type=int, default=0)
    sweep_run.add_argument("--dry-run", action="store_true")
    sweep_run.set_defaults(func=_cmd_experiment_sweep)
    sweep_ingest = experiment_sub.add_parser(
        "sweep-ingest", help="verify sweep hashes into exploratory evidence"
    )
    sweep_ingest.add_argument("--project", required=True)
    sweep_ingest.add_argument("--experiment-id", required=True)
    sweep_ingest.set_defaults(func=_cmd_experiment_sweep)
    sweep_status = experiment_sub.add_parser(
        "sweep-status", help="read-only sweep lifecycle status"
    )
    sweep_status.add_argument("--project", required=True)
    sweep_status.add_argument("--experiment-id", required=True)
    sweep_status.set_defaults(func=_cmd_experiment_sweep)

    experiment_scaffold = experiment_sub.add_parser(
        "scaffold", help="generate a self-contained local experiment package (does not execute it)"
    )
    experiment_scaffold.add_argument("--project", required=True)
    experiment_scaffold.add_argument("--run-id", required=True)
    experiment_scaffold.add_argument("--data", required=True, help="project-relative CSV")
    experiment_scaffold.add_argument("--target", required=True)
    experiment_scaffold.add_argument("--features", required=True, help="comma-separated feature columns")
    experiment_scaffold.add_argument("--task", choices=["regression", "classification"], default="regression")
    experiment_scaffold.add_argument("--methods", default="dummy,ridge", help="comma-separated methods")
    experiment_scaffold.add_argument("--metric", default="")
    experiment_scaffold.add_argument("--experiment-id", default="")
    experiment_scaffold.add_argument("--test-size", type=float, default=0.2)
    experiment_scaffold.add_argument("--seeds", type=int, default=3)
    experiment_scaffold.add_argument(
        "--cv-folds", type=int, default=0, help="k-fold CV (0 = holdout split)"
    )
    experiment_scaffold.add_argument(
        "--alpha-grid",
        default="",
        help="optional comma-separated ridge alpha values for a sweep plan (planning profile only)",
    )
    experiment_scaffold.add_argument("--output-root", default="")
    experiment_scaffold.set_defaults(func=_cmd_experiment_scaffold)

    loop_parser = sub.add_parser("loop", help="stage ledger for the automated research loop")
    loop_sub = loop_parser.add_subparsers(dest="loop_command", required=True)
    loop_status = loop_sub.add_parser("status", help="inspect stages, gates and iterations of one run")
    loop_status.add_argument("--project", required=True)
    loop_status.add_argument("--run-id", required=True)
    loop_status.add_argument("--output-dir", default="")
    loop_status.set_defaults(func=_cmd_loop_status)

    verdicts_parser = sub.add_parser(
        "verdicts", help="deterministic read-only ledger of the decisions a project's artifacts contain"
    )
    verdicts_sub = verdicts_parser.add_subparsers(dest="verdicts_command", required=True)
    verdicts_collect = verdicts_sub.add_parser(
        "collect", help="re-derive every verdict from its single-point producer and compare snapshots"
    )
    verdicts_collect.add_argument("--project", required=True)
    verdicts_collect.add_argument("--output", default="", help="write the ledger JSON here; default stdout")
    verdicts_collect.add_argument("--limit", type=int, default=50)
    verdicts_collect.set_defaults(func=_cmd_verdicts_collect)
    verdicts_show = verdicts_sub.add_parser("show", help="print a previously collected ledger")
    verdicts_show.add_argument("--ledger", required=True)
    verdicts_show.set_defaults(func=_cmd_verdicts_show)

    feedback_parser = sub.add_parser(
        "feedback", help="pluggable feedback loops: observe -> propose -> gate (default reject) -> apply -> record"
    )
    feedback_sub = feedback_parser.add_subparsers(dest="feedback_command", required=True)
    feedback_list = feedback_sub.add_parser("list", help="list registered feedback loops")
    feedback_list.set_defaults(func=_cmd_feedback_list)
    feedback_run = feedback_sub.add_parser(
        "run", help="run the explicitly enabled loops; with none enabled nothing is written"
    )
    feedback_run.add_argument("--project", required=True)
    feedback_run.add_argument(
        "--loops",
        default="",
        help="comma-separated loop ids to enable (default: none — disabled, writes nothing)",
    )
    feedback_run.add_argument("--limit", type=int, default=50)
    feedback_run.set_defaults(func=_cmd_feedback_run)

    innovation_parser = sub.add_parser("innovation", help="multi-role innovation review over a run")
    innovation_sub = innovation_parser.add_subparsers(dest="innovation_command", required=True)
    innovation_review = innovation_sub.add_parser(
        "review", help="propose, review, revise and re-review innovation ideas"
    )
    innovation_review.add_argument("--project", required=True)
    innovation_review.add_argument("--run-id", required=True)
    innovation_review.add_argument("--topic", default="")
    innovation_review.add_argument("--direction", default="", help="research direction seed")
    innovation_review.add_argument("--rounds", type=int, default=2)
    innovation_review.add_argument("--max-ideas", type=int, default=5)
    innovation_review.add_argument(
        "--no-guidance",
        action="store_true",
        help="control arm: generate without the guideline-memory block (memory ab --arm without)",
    )
    innovation_review.add_argument(
        "--propose-only",
        action="store_true",
        help="stop after generation (no critic panel) — what the memory A/B needs to compare ideas",
    )
    innovation_review.add_argument("--threshold", type=float, default=8.0)
    innovation_review.add_argument(
        "--prior-art-corpus",
        default="",
        help=(
            "real CC-BY corpus the novelty critic searches on its own, after generation, for prior "
            "art that refutes each idea's delta; omitting it means novelty is judged only against "
            "the generator's own evidence set, and the output says so"
        ),
    )
    innovation_review.add_argument(
        "--prior-art-limit", type=int, default=6, help="hits per idea in reviewer-side retrieval"
    )
    innovation_review.add_argument(
        "--critic",
        action="append",
        default=[],
        metavar="ROLE=PROFILE_ID",
        help="answer one critic role with a specific model profile (novelty|evidence|feasibility)",
    )
    innovation_review.add_argument(
        "--independent",
        action="store_true",
        help="staff all critic roles from distinct provider+model supplies; fails when the "
        "gateway cannot offer them",
    )
    innovation_review.add_argument(
        "--language",
        choices=["zh", "en"],
        default="zh",
        help=(
            "language of the returned idea fields (title/problem/mechanism/falsification/"
            "experiment_plan). The prompt stays Chinese; only the artifact language follows this. "
            "Rule 8 used to be hard-coded to Chinese, so English-venue runs still produced "
            "artifacts that English rubric packs score as foreign script."
        ),
    )
    innovation_review.add_argument("--output-dir", default="")
    innovation_review.set_defaults(func=_cmd_innovation_review)

    manuscript_parser = sub.add_parser("manuscript", help="review and revise a manuscript iteratively")
    manuscript_sub = manuscript_parser.add_subparsers(dest="manuscript_command", required=True)
    manuscript_draft = manuscript_sub.add_parser(
        "draft", help="generate an evidence-grounded first draft and audit it"
    )
    manuscript_draft.add_argument("--project", required=True)
    manuscript_draft.add_argument("--run-id", required=True)
    manuscript_draft.add_argument("--output", required=True, help="output .md path")
    manuscript_draft.set_defaults(func=_cmd_manuscript_draft)
    manuscript_provenance = manuscript_sub.add_parser(
        "provenance", help="trace a draft's numbers back to artifacts on disk"
    )
    manuscript_provenance.add_argument("--draft", required=True)
    manuscript_provenance.add_argument("--corpus", required=True)
    manuscript_provenance.add_argument("--max-files", type=int, default=20000)
    manuscript_provenance.add_argument("--output", default="")
    manuscript_provenance.set_defaults(func=_cmd_manuscript_provenance)
    manuscript_review = manuscript_sub.add_parser(
        "review", help="rubric review, revision, re-review, and deterministic audit"
    )
    manuscript_review.add_argument("--project", required=True)
    manuscript_review.add_argument("--run-id", required=True)
    manuscript_review.add_argument("--draft", required=True)
    manuscript_review.add_argument("--rounds", type=int, default=3)
    manuscript_review.add_argument("--threshold", type=float, default=8.0)
    manuscript_review.add_argument("--output-dir", default="")
    manuscript_review.add_argument(
        "--semantic-support",
        action="store_true",
        help="feed sentence-level support failures into review/revision (model key required)",
    )
    manuscript_review.add_argument(
        "--strict-support",
        action="store_true",
        help="reject revisions that leave contradicted/unresolved/insufficient citations",
    )
    manuscript_review.add_argument(
        "--support-votes",
        type=int,
        default=1,
        help="semantic judge votes per item (majority; 1-5)",
    )
    manuscript_review.add_argument(
        "--judge-profile",
        default="",
        help="model profile id for an independent support judge",
    )
    manuscript_review.add_argument(
        "--revision-mode",
        choices=["full", "section", "support", "auto"],
        default="full",
        help="full-document rewrite, targeted section rewrite, or auto fallback",
    )
    manuscript_review.add_argument(
        "--ab-check",
        action="store_true",
        help="accept a revision only if blind A/B review does not prefer the original",
    )
    manuscript_review.add_argument(
        "--ab-section",
        action="append",
        default=[],
        help="section heading substring for A/B review (repeatable; default all)",
    )
    manuscript_review.set_defaults(func=_cmd_manuscript_review)

    empirical_parser = sub.add_parser(
        "empirical", help="same-run literature + local experiment evidence paper loop"
    )
    empirical_sub = empirical_parser.add_subparsers(dest="empirical_command", required=True)
    empirical_common = argparse.ArgumentParser(add_help=False)
    empirical_common.add_argument("--project", required=True)
    empirical_common.add_argument("--run-id", required=True)
    empirical_common.add_argument("--experiment-id", required=True)
    empirical_check = empirical_sub.add_parser("check", parents=[empirical_common])
    empirical_check.set_defaults(func=_cmd_empirical)
    empirical_paper = empirical_sub.add_parser("paper", parents=[empirical_common])
    empirical_paper.add_argument("--output", required=True, help="draft .md path inside the project")
    empirical_paper.add_argument("--language", choices=["zh", "en"], default="zh")
    empirical_paper.add_argument(
        "--venue",
        choices=["zh_core_journal", "software_journal", "computer_journal", "en_conference"],
        default="zh_core_journal",
    )
    empirical_paper.add_argument("--max-sources", type=int, default=16)
    empirical_paper.add_argument("--max-spans-per-source", type=int, default=3)
    empirical_paper.add_argument("--review-rounds", type=int, default=2)
    empirical_paper.add_argument("--repair-attempts", type=int, default=2)
    method_group = empirical_paper.add_mutually_exclusive_group()
    method_group.add_argument(
        "--method-scene", default="", help="project-relative AstraDraw scene for the method schematic"
    )
    method_group.add_argument(
        "--method-template", default="", help="vendored AstraDraw template id for the method schematic"
    )
    empirical_paper.add_argument(
        "--semantic-support",
        action="store_true",
        help="run a reference-aware semantic support ledger over the final draft (model key required)",
    )
    empirical_paper.add_argument(
        "--strict-support",
        action="store_true",
        help="require all cited sentences to be supported (implies semantic support)",
    )
    empirical_paper.add_argument(
        "--support-votes",
        type=int,
        default=1,
        help="semantic judge votes per item (majority; 1-5)",
    )
    empirical_paper.add_argument(
        "--judge-profile",
        default="",
        help="model profile id for an independent support judge",
    )
    empirical_paper.add_argument(
        "--ab-check",
        action="store_true",
        help="accept a revision only if blind A/B review does not prefer the original",
    )
    empirical_paper.add_argument(
        "--ab-section",
        action="append",
        default=[],
        help="section heading substring for A/B review (repeatable)",
    )
    empirical_paper.add_argument(
        "--offline-draft",
        action="store_true",
        help="deterministic test-only draft from pack refs/allowed numbers; not model quality",
    )
    empirical_paper.add_argument(
        "--external-lint",
        action="store_true",
        help="run whitelisted external scientific-writing lint after audit; errors block loop",
    )
    empirical_paper.add_argument(
        "--external-skill-root",
        default="",
        help="external skill root; or set RESEARCH_AGENT_EXTERNAL_SKILLS",
    )
    empirical_paper.add_argument(
        "--external-consistency",
        action="store_true",
        help="run whitelisted external consistency check after audit; errors block loop",
    )
    empirical_paper.add_argument(
        "--external-consistency-registry",
        default="",
        help="project-relative JSON registry for --external-consistency",
    )
    empirical_paper.add_argument(
        "--external-consistency-auto",
        action="store_true",
        help="derive the consistency registry from verified experiment evidence",
    )
    empirical_paper.add_argument("--threshold", type=float, default=8.0)
    empirical_paper.set_defaults(func=_cmd_empirical)

    writing_parser = sub.add_parser("writing", help="build a writing pack or audit a draft")
    writing_sub = writing_parser.add_subparsers(dest="writing_command", required=True)
    writing_common = argparse.ArgumentParser(add_help=False)
    writing_common.add_argument("--project", required=True, help="research project directory")
    writing_common.add_argument("--run-id", required=True)
    writing_common.add_argument("--language", choices=["zh", "en"], default="zh")
    writing_common.add_argument("--experiment-id", default="", help="use verified local experiment evidence")
    writing_common.add_argument(
        "--venue",
        choices=["zh_core_journal", "software_journal", "computer_journal", "en_conference"],
        default="zh_core_journal",
    )
    external_common = argparse.ArgumentParser(add_help=False)
    external_common.add_argument("--project", required=True, help="research project directory")
    writing_pack_parser = writing_sub.add_parser(
        "pack", parents=[writing_common], help="project one run into writing-pack.json/.md"
    )
    writing_pack_parser.add_argument("--max-sources", type=int, default=8)
    writing_pack_parser.add_argument("--max-spans-per-source", type=int, default=3)
    writing_pack_parser.set_defaults(func=_cmd_writing)
    writing_audit_parser = writing_sub.add_parser(
        "audit", parents=[writing_common], help="audit a draft against a writing pack"
    )
    writing_audit_parser.add_argument("--draft", required=True, help=".md/.txt/.tex/.docx draft")
    writing_audit_parser.add_argument(
        "--semantic",
        action="store_true",
        help="run the reference-aware semantic support ledger (model key required)",
    )
    writing_audit_parser.add_argument(
        "--strict-support",
        action="store_true",
        help="block non-ready semantic support verdicts (implies --semantic)",
    )
    writing_audit_parser.add_argument(
        "--strict-pack-binding",
        action="store_true",
        help="block drafts without a matching writing-pack marker",
    )
    writing_audit_parser.add_argument(
        "--support-votes",
        type=int,
        default=1,
        help="semantic judge votes per item (majority; 1-5)",
    )
    writing_audit_parser.add_argument(
        "--support-max-items",
        type=int,
        default=80,
        help="maximum cited sentences to judge; strict support blocks if truncated",
    )
    writing_audit_parser.add_argument(
        "--refresh-support",
        action="store_true",
        help="ignore the cached support ledger and re-run the judge",
    )
    writing_audit_parser.add_argument(
        "--judge-profile",
        default="",
        help="model profile id for an independent support judge (recommended different provider)",
    )
    writing_audit_parser.set_defaults(func=_cmd_writing)

    support_gold_template_parser = writing_sub.add_parser(
        "support-gold-template",
        parents=[writing_common],
        help="blank human-gold annotation templates from a support panel",
    )
    support_gold_template_parser.add_argument(
        "--panel",
        default="",
        help="project-relative support-panel.json; defaults to runs/<RUN>/support-panel.json",
    )
    support_gold_template_parser.add_argument(
        "--annotator",
        dest="annotators",
        action="append",
        default=[],
        help="annotator id (repeat; default A and B)",
    )
    support_gold_template_parser.add_argument(
        "--ledger",
        default="",
        help="project-relative support-ledger.json; takes precedence over --panel",
    )
    support_gold_template_parser.add_argument("--output-dir", default="")
    support_gold_template_parser.set_defaults(func=_cmd_writing)

    writing_bind_parser = writing_sub.add_parser(
        "bind",
        parents=[writing_common],
        help="attach the current writing pack marker to an existing draft",
    )
    writing_bind_parser.add_argument(
        "--draft", required=True, help="project-relative existing draft"
    )
    writing_bind_parser.add_argument(
        "--output", required=True, help="project-relative new draft path"
    )
    writing_bind_parser.set_defaults(func=_cmd_writing)
    support_gold_parser = writing_sub.add_parser(
        "support-gold",
        parents=[writing_common],
        help="double-annotated human gold with kappa and panel comparison",
    )
    support_gold_parser.add_argument(
        "--annotator-file",
        dest="annotator_files",
        action="append",
        default=[],
        help="annotation JSON from one annotator (repeat for at least two annotators)",
    )
    support_gold_parser.add_argument(
        "--draft", default="", help="optional project-relative draft to hash"
    )
    support_gold_parser.add_argument(
        "--panel", default="", help="optional project-relative support-panel.json"
    )
    support_gold_parser.add_argument(
        "--ledger",
        default="",
        help="optional project-relative support-ledger.json; takes precedence over --panel",
    )
    support_gold_parser.add_argument("--output-dir", default="")
    support_gold_parser.set_defaults(func=_cmd_writing)

    external_claim = writing_sub.add_parser(
        "external-claim-audit",
        parents=[writing_common],
        help="run a whitelisted external claim/evidence audit (read-only)",
    )
    external_claim.add_argument(
        "--skill-root",
        default="",
        help="external skill root; or set RESEARCH_AGENT_EXTERNAL_SKILLS",
    )
    external_claim.add_argument("--output", default="", help="optional project-relative JSON report")
    external_claim.set_defaults(func=_cmd_writing)

    external_lint = writing_sub.add_parser(
        "external-lint",
        parents=[external_common],
        help="run a whitelisted external scientific-writing lint (read-only)",
    )
    external_lint.add_argument("--draft", required=True, help="project-relative Markdown draft")
    external_lint.add_argument(
        "--skill-root",
        default="",
        help="external skill root; or set RESEARCH_AGENT_EXTERNAL_SKILLS",
    )
    external_lint.add_argument("--output", default="", help="optional project-relative JSON report")
    external_lint.set_defaults(func=_cmd_writing)

    external_consistency = writing_sub.add_parser(
        "external-consistency",
        parents=[external_common],
        help="run a whitelisted external numeric/methods consistency check (read-only)",
    )
    external_consistency.add_argument(
        "--registry", required=True, help="project-relative consistency registry JSON"
    )
    external_consistency.add_argument(
        "--skill-root",
        default="",
        help="external skill root; or set RESEARCH_AGENT_EXTERNAL_SKILLS",
    )
    external_consistency.add_argument(
        "--output", default="", help="optional project-relative JSON report"
    )
    external_consistency.set_defaults(func=_cmd_writing)

    support_panel_parser = writing_sub.add_parser(
        "support-panel",
        parents=[writing_common],
        help="multi-judge support panel with disagreement ledger and human adjudication",
    )
    support_panel_parser.add_argument("--draft", required=True, help=".md/.txt/.tex draft")
    support_panel_parser.add_argument(
        "--judge-profile",
        dest="judge_profiles",
        action="append",
        default=[],
        help="independent judge profile id (repeat for a panel; different providers recommended)",
    )
    support_panel_parser.add_argument(
        "--judge-family",
        dest="judge_families",
        action="append",
        default=[],
        help="optional profile_id=family declaration, repeat for a panel",
    )
    support_panel_parser.add_argument(
        "--require-families",
        action="store_true",
        help="require at least two distinct declared model families (strict independence)",
    )
    support_panel_parser.add_argument(
        "--require-providers",
        action="store_true",
        help="require at least two distinct configured provider ids for the panel",
    )
    support_panel_parser.add_argument(
        "--support-votes", type=int, default=1, help="votes per judge per item (1-5)"
    )
    support_panel_parser.add_argument("--max-items", type=int, default=80)
    support_panel_parser.add_argument(
        "--strict-support",
        action="store_true",
        help="block unresolved judge disagreement (requires at least two judges)",
    )
    support_panel_parser.add_argument(
        "--refresh-support", action="store_true", help="ignore cached per-judge ledgers"
    )
    support_panel_parser.add_argument(
        "--adjudication",
        default="",
        help="JSON file with human decisions for disagreed items",
    )
    support_panel_parser.set_defaults(func=_cmd_writing)

    support_eval_parser = writing_sub.add_parser(
        "support-eval", help="evaluate the support judge against the curated calibration set"
    )
    support_eval_parser.add_argument("--cases", default="")
    support_eval_parser.add_argument("--votes", type=int, default=1)
    support_eval_parser.add_argument("--output-dir", default="")
    support_eval_parser.set_defaults(func=_cmd_support_eval)

    revision_parser = sub.add_parser(
        "revision", help="revise an existing manuscript with data-backed figures and journal export"
    )
    revision_sub = revision_parser.add_subparsers(dest="revision_command", required=True)
    revision_common = argparse.ArgumentParser(add_help=False)
    revision_common.add_argument("--draft", required=True, help="existing .md/.txt/.docx/.tex manuscript")
    revision_common.add_argument("--output-dir", required=True)
    revision_common.add_argument("--data", action="append", default=[], help="CSV/TSV/JSON/XLSX table (repeatable)")
    revision_common.add_argument("--metrics", default="", help="metric spec JSON")
    revision_common.add_argument("--figures", default="", help="figure spec JSON")
    revision_common.add_argument(
        "--venue",
        choices=["zh_core_journal", "software_journal", "computer_journal"],
        default="zh_core_journal",
    )
    revision_inspect = revision_sub.add_parser(
        "inspect", parents=[revision_common], help="parse sections, data and figures without rewriting"
    )
    revision_inspect.set_defaults(func=_cmd_revision)
    revision_plan = revision_sub.add_parser(
        "plan", parents=[revision_common], help="generate a section-level rewrite plan"
    )
    revision_plan.add_argument("--profile", required=True, help="model gateway profile")
    revision_plan.add_argument("--store", default="", help="model gateway store path")
    revision_plan.add_argument("--section", action="append", default=[], help="plan only matching section headings")
    revision_plan.add_argument("--goal", default="", help="rewrite goal")
    revision_plan.add_argument("--review-file", default="", help="JSON with must_fix")
    revision_plan.set_defaults(func=_cmd_revision)
    revision_ab = revision_sub.add_parser(
        "ab-review", help="blind A/B rubric review of original vs revised"
    )
    revision_ab.add_argument("--original", required=True)
    revision_ab.add_argument("--revised", required=True)
    revision_ab.add_argument("--output-dir", required=True)
    revision_ab.add_argument("--profile", required=True)
    revision_ab.add_argument("--store", default="")
    revision_ab.add_argument("--section", action="append", default=[])
    revision_ab.add_argument("--rounds", type=int, default=1)
    revision_ab.set_defaults(func=_cmd_revision_ab)
    revision_run = revision_sub.add_parser(
        "run", parents=[revision_common], help="rewrite and export a submission working package"
    )
    revision_run.add_argument("--profile", default="", help="model gateway profile; empty keeps copy mode")
    revision_run.add_argument("--store", default="", help="model gateway store path")
    revision_run.add_argument("--section", action="append", default=[], help="rewrite only matching section headings")
    revision_run.add_argument("--goal", default="", help="rewrite goal, e.g. improve logical flow and clarity")
    revision_run.add_argument("--review-file", default="", help="JSON with must_fix or manuscript-review iterations")
    revision_run.add_argument("--plan-file", default="", help="revision-plan.json generated by `revision plan`")
    revision_run.add_argument("--auto-plan", action="store_true", help="generate and apply a section-level plan before rewriting")
    revision_run.add_argument(
        "--format",
        action="append",
        choices=["md", "tex", "docx", "pdf", "html"],
        default=[],
        help="export format (repeatable; default md/tex/docx/pdf)",
    )
    revision_run.set_defaults(func=_cmd_revision)

    figure_parser = sub.add_parser("figure", help="render AstraDraw scenes or bundled templates")
    figure_sub = figure_parser.add_subparsers(dest="figure_command", required=True)
    figure_templates = figure_sub.add_parser("templates", help="list bundled AstraDraw scene templates")
    figure_templates.set_defaults(func=_cmd_figure)
    figure_render = figure_sub.add_parser("render", help="render a project scene or vendored template")
    figure_source = figure_render.add_mutually_exclusive_group(required=True)
    figure_source.add_argument("--scene", default="", help="AstraDraw .scene.json file")
    figure_source.add_argument("--template", default="", help="bundled template id")
    figure_render.add_argument("--output-dir", required=True)
    figure_render.add_argument("--title", default="")
    figure_render.add_argument("--description", default="")
    figure_render.add_argument("--name", default="")
    figure_render.add_argument("--format", action="append", choices=["svg", "png"], default=[])
    figure_render.set_defaults(func=_cmd_figure)
    figure_table = figure_sub.add_parser(
        "table", help="render a chart from a CSV/XLSX data table plus a figure spec"
    )
    figure_table.add_argument("--data", action="append", required=True)
    figure_table.add_argument("--spec", required=True, help="figure spec JSON")
    figure_table.add_argument("--output-dir", required=True)
    figure_table.set_defaults(func=_cmd_figure_table)

    benchmark_parser = sub.add_parser("benchmark", help="internal deterministic regression benchmark")
    benchmark_sub = benchmark_parser.add_subparsers(dest="benchmark_command", required=True)
    benchmark_run = benchmark_sub.add_parser("run", help="run strict-flow and support-audit oracle/nop cases")
    benchmark_run.add_argument("--output-dir", default="")
    benchmark_run.add_argument("--no-closure", action="store_true", help="skip the slower full closure case")
    benchmark_run.set_defaults(func=_cmd_benchmark)

    project_parser = sub.add_parser("project", help="bounded research project folders")
    project_sub = project_parser.add_subparsers(dest="project_command", required=True)
    project_init = project_sub.add_parser("init", help="create project.json and the fixed folder layout")
    project_init.add_argument("--dir", required=True)
    project_init.add_argument("--name", default="")
    project_init.set_defaults(func=_cmd_project_init)
    project_status = project_sub.add_parser("status", help="show recent runs and their gates")
    project_status.add_argument("--dir", required=True)
    project_status.add_argument("--limit", type=int, default=20)
    project_status.set_defaults(func=_cmd_project_status)

    task_parser = sub.add_parser("task", help="plan or execute a bounded research task")
    task_sub = task_parser.add_subparsers(dest="task_command", required=True)
    task_common = argparse.ArgumentParser(add_help=False)
    task_common.add_argument("--goal", required=True, help="task goal, 2-500 characters")
    task_common.add_argument("--type", default="auto", choices=["auto", "literature_review", "hypothesis_design", "experiment_validation", "full_research"])
    task_common.add_argument("--deliverable", default="")
    task_common.add_argument("--language", default="zh", choices=["zh", "en"])
    task_common.add_argument("--venue", default="zh_core_journal", choices=["zh_core_journal", "en_conference", "en_journal", "zh_thesis"])
    task_common.add_argument("--source", default="fixture", choices=["fixture", "real", "openalex", "local"])
    task_common.add_argument("--corpus-dir", default="", help="local PDF/TXT/MD corpus directory")
    task_common.add_argument("--max-sources", type=int, default=6)
    task_common.add_argument("--run-dataset", choices=["", "iris", "breast_cancer", "chemlab"], default="")
    task_common.add_argument("--run-dir", default="", help="reuse an existing RunCapsule/EA directory instead of running S5")
    task_common.add_argument("--run-seeds", type=int, default=3)
    task_common.add_argument("--flow-mode", choices=["review", "strict"], default="")
    task_common.add_argument("--g1-decision", default="", help="approved G1 decision JSON")
    task_common.add_argument(
        "--idea-file",
        default="",
        help="reuse an approved idea set (idea.json) so a G1 decision still binds",
    )
    task_common.add_argument(
        "--design-file",
        default="",
        help="reuse a frozen design (experiment.json) so a G2 protocol still binds",
    )
    task_common.add_argument("--protocol-file", default="", help="frozen ProtocolCard JSON")
    task_common.add_argument("--claim-file", default="", help="signed supported ClaimRecord JSON")
    task_common.add_argument("--bibliography-file", default="", help="verified bibliography card JSON")
    task_common.add_argument("--constraint", action="append")
    task_common.add_argument("--criterion", action="append")
    task_common.add_argument("--planner", default="gateway")
    task_common.add_argument(
        "--writer", default="auto",
        help="论文非结果章节写作：auto | off | profile:<id>；无 key 自动回退确定性草稿",
    )
    task_common.add_argument(
        "--idea-model", default="auto",
        help="S2–S3 候选生成：auto | off | profile:<id>；按设置中的 idea 绑定",
    )
    task_common.add_argument(
        "--experiment-model", default="auto",
        help="S4 设计草稿：auto | off | profile:<id>；按设置中的 experiment 绑定",
    )
    task_common.add_argument(
        "--support-judge", default="auto",
        help="claim/引用支持审稿：auto | off | profile:<id>；按设置中的 judge 绑定",
    )
    task_plan = task_sub.add_parser("plan", parents=[task_common], help="show route, steps, gates and checks")
    task_plan.set_defaults(func=_cmd_task_plan)
    task_run = task_sub.add_parser("run", parents=[task_common], help="execute the bounded task route")
    task_run.add_argument("--output-dir", default="runtime_data/tasks")
    task_run.set_defaults(func=_cmd_task_run)

    pipeline = sub.add_parser("pipeline", help="run the fixture vertical slice")
    pipeline_sub = pipeline.add_subparsers(dest="pipeline_command", required=True)
    pipeline_run = pipeline_sub.add_parser("run", help="literature → idea → design → figure → paper (+grant)")
    pipeline_run.add_argument("--topic", required=True)
    pipeline_run.add_argument("--language", choices=["zh", "en"])
    pipeline_run.add_argument(
        "--venue", default="zh_core_journal",
        choices=["zh_core_journal", "en_conference", "en_journal", "zh_thesis"],
    )
    pipeline_run.add_argument("--grant", choices=["", "nsfc", "nssfc", "generic"], default="")
    pipeline_run.add_argument("--style", choices=["comic", "roman", "modern"], default="modern")
    pipeline_run.add_argument("--max-sources", type=int, default=6)
    pipeline_run.add_argument(
        "--adaptive-retrieval",
        action="store_true",
        help="let the S1 coverage verdict widen the next retrieval budget (bounded, no human gate crossed)",
    )
    pipeline_run.add_argument("--primary-metric")
    pipeline_run.add_argument("--control", action="append")
    pipeline_run.add_argument("--budget")
    pipeline_run.add_argument("--claim-file")
    pipeline_run.add_argument("--run-dataset", choices=["", "iris", "breast_cancer", "chemlab"], default="")
    pipeline_run.add_argument("--run-seeds", type=int, default=3)
    pipeline_run.add_argument(
        "--study-dataset",
        choices=["", "iris", "breast_cancer", "wine", "digits"],
        default="",
        help="额外执行搜索研究臂（memory x gate 因子设计）；设计不属于该档位时直接失败",
    )
    pipeline_run.add_argument("--study-seeds", type=int, default=0, help="研究臂配对种子数（>=4）")
    pipeline_run.add_argument("--study-budget", type=int, default=60, help="研究臂验证评估预算")
    pipeline_run.add_argument(
        "--study-project",
        default="",
        help="研究包落到的 <project>/studies 目录，便于闭包盘点与 research_status 看见",
    )
    pipeline_run.add_argument("--run-dir")
    pipeline_run.add_argument(
        "--resume-dir", default="",
        help="从既有 run 输出目录拾取 G1 决策/冻结协议/人签 claim/已完成 run 产物续跑；显式给出的 --g1-decision/--protocol-file/--claim-file/--run-dir 优先",
    )
    pipeline_run.add_argument("--protocol-file")
    pipeline_run.add_argument("--g1-decision", default="", help="approved G1 decision JSON")
    pipeline_run.add_argument(
        "--idea-file",
        default="",
        help="reuse an approved idea set (idea.json) so a G1 decision still binds",
    )
    pipeline_run.add_argument(
        "--study-design-file",
        default="",
        help="pre-registered study design (study-design.json) rendered as the paper's setup; the local run stays protocol validation",
    )
    pipeline_run.add_argument(
        "--design-file",
        default="",
        help="reuse a frozen design (experiment.json) so a G2 protocol still binds",
    )
    pipeline_run.add_argument("--flow-mode", choices=["review", "strict"], default="")
    pipeline_run.add_argument("--bibliography-file")
    pipeline_run.add_argument("--use-s5-lease", action="store_true")
    pipeline_run.add_argument("--s5-ledger")
    pipeline_run.add_argument("--s5-scope", default="S5/demo/iris")
    pipeline_run.add_argument("--run-id")
    pipeline_run.add_argument("--real-corpus", action="store_true")
    pipeline_run.add_argument("--corpus-dir", default="", help="local PDF/TXT/MD corpus directory")
    pipeline_run.add_argument("--openalex", action="store_true", help="S1 使用 OpenAlex 实时检索（无需 key）")
    pipeline_run.add_argument("--mailto", default="", help="OpenAlex polite-pool email（或 OPENALEX_EMAIL）")
    pipeline_run.add_argument("--planner", default="gateway", help="S1 检索规划器：rule | glm | gateway | profile:<id>；无 key 自动回退")
    pipeline_run.add_argument("--writer", default="auto", help="论文非结果章节写作：auto | off | profile:<id>；无 key 自动回退确定性草稿")
    pipeline_run.add_argument("--idea-model", default="auto", help="S2–S3 候选生成：auto | off | profile:<id>；按设置中的 idea 绑定")
    pipeline_run.add_argument("--experiment-model", default="auto", help="S4 设计草稿：auto | off | profile:<id>；按设置中的 experiment 绑定")
    pipeline_run.add_argument("--support-judge", default="auto", help="claim/引用支持审稿：auto | off | profile:<id>；按设置中的 judge 绑定")
    pipeline_run.add_argument("--corpus")
    pipeline_run.add_argument("--ledger")
    pipeline_run.add_argument("--lease-scope", default="S1/rsi-ccby-4-compare")
    pipeline_run.add_argument("--use-lease", action="store_true")
    pipeline_run.add_argument("--output-dir", default="research_agent/web/data")
    pipeline_run.set_defaults(func=_cmd_pipeline_run)

    bib_parser = sub.add_parser("bibliography", help="S13 bibliography metadata verification")
    bib_sub = bib_parser.add_subparsers(dest="bibliography_command", required=True)
    bib_verify = bib_sub.add_parser("verify")
    bib_verify.add_argument("--source", default="modules/literature/fixtures/bibliography.json")
    bib_verify.add_argument("--output-dir", default="research_agent/web/data/bibliography")
    bib_verify.set_defaults(func=_cmd_bibliography_verify)

    flow_parser = sub.add_parser("flow", help="explicit G1/G2 control artifacts")
    flow_sub = flow_parser.add_subparsers(dest="flow_command", required=True)
    flow_g1 = flow_sub.add_parser("g1", help="write an approved G1 decision from idea.json")
    flow_g1.add_argument("--idea-file", required=True)
    flow_g1.add_argument("--idea-id", required=True)
    flow_g1.add_argument("--human-reason", required=True)
    flow_g1.add_argument("--decision-id", default="")
    flow_g1.add_argument("--output-dir", default="research_agent/web/data/flow")
    flow_g1.set_defaults(func=_cmd_flow_g1)

    protocol_parser = sub.add_parser("protocol", help="S4 protocol freeze / G2")
    protocol_sub = protocol_parser.add_subparsers(dest="protocol_command", required=True)
    protocol_freeze = protocol_sub.add_parser("freeze", help="legacy: freeze after a completed run")
    protocol_freeze.add_argument("--design", required=True)
    protocol_freeze.add_argument("--capsule", required=True)
    protocol_freeze.add_argument("--limitation", required=True)
    protocol_freeze.add_argument("--human-reason", required=True)
    protocol_freeze.add_argument("--output-dir", default="research_agent/web/data/protocol")
    protocol_freeze.set_defaults(func=_cmd_protocol_freeze)
    protocol_freeze_design = protocol_sub.add_parser(
        "freeze-design", help="pre-register: freeze design before S5"
    )
    protocol_freeze_design.add_argument("--design", required=True)
    protocol_freeze_design.add_argument("--limitation", required=True)
    protocol_freeze_design.add_argument("--human-reason", required=True)
    protocol_freeze_design.add_argument("--output-dir", default="research_agent/web/data/protocol")
    protocol_freeze_design.set_defaults(func=_cmd_protocol_freeze_design)

    closure_parser = sub.add_parser("closure", help="S13-S16 closure and export gate")
    closure_sub = closure_parser.add_subparsers(dest="closure_command", required=True)
    closure_profiles = closure_sub.add_parser(
        "profiles", help="read-only registry of canonical-run vs local-experiment closure"
    )
    closure_profiles.add_argument("--project", default="", help="also inventory project closure artifacts")
    closure_profiles.set_defaults(func=_cmd_closure_profiles)
    closure_check = closure_sub.add_parser("check")
    closure_check.add_argument("--demo", required=True)
    closure_check.add_argument("--claim", required=True)
    closure_check.add_argument("--output-dir", default="research_agent/web/data/closure")
    closure_check.set_defaults(func=_cmd_closure_check)
    closure_sign = closure_sub.add_parser("sign")
    closure_sign.add_argument("--report", required=True)
    closure_sign.add_argument("--demo", required=True)
    closure_sign.add_argument("--claim", required=True)
    closure_sign.add_argument("--human-reason", required=True)
    closure_sign.add_argument("--signer", default="", help="local signer id; otherwise legacy unsigned record")
    closure_sign.add_argument("--signers-path", default=str(DEFAULT_SIGNER_STORE_PATH))
    closure_sign.add_argument("--output-dir", default="research_agent/web/data/closure-signature")
    closure_sign.set_defaults(func=_cmd_closure_sign)
    closure_publish = closure_sub.add_parser("publish", help="seal signed evidence into an immutable bundle")
    closure_publish.add_argument("--manifest", required=True)
    closure_publish.add_argument("--signature", default=None)
    closure_publish.add_argument("--signers-path", default=str(DEFAULT_SIGNER_STORE_PATH))
    closure_publish.add_argument("--bundle-name", default="evidence-bundle")
    closure_publish.add_argument("--output-dir", default="research_agent/web/data/closure-bundle")
    closure_publish.set_defaults(func=_cmd_closure_publish)

    signer_parser = sub.add_parser("signer", help="local HMAC signer identities")
    signer_sub = signer_parser.add_subparsers(dest="signer_command", required=True)
    signer_create = signer_sub.add_parser("create")
    signer_create.add_argument("--name", required=True)
    signer_create.add_argument("--signers-path", default=str(DEFAULT_SIGNER_STORE_PATH))
    signer_create.set_defaults(func=_cmd_signer)
    signer_list = signer_sub.add_parser("list")
    signer_list.add_argument("--signers-path", default=str(DEFAULT_SIGNER_STORE_PATH))
    signer_list.set_defaults(func=_cmd_signer)
    closure_verify_bundle = closure_sub.add_parser("verify-bundle", help="re-hash a sealed evidence bundle")
    closure_verify_bundle.add_argument("--bundle", required=True)
    closure_verify_bundle.add_argument("--signers-path", default=str(DEFAULT_SIGNER_STORE_PATH))
    closure_verify_bundle.set_defaults(func=_cmd_closure_verify_bundle)
    closure_audit = closure_sub.add_parser(
        "audit", help="static S1→S5→paper artifact consistency audit"
    )
    closure_audit.add_argument("--bundle", required=True)
    closure_audit.add_argument("--output-dir", default="")
    closure_audit.set_defaults(func=_cmd_closure_audit)
    closure_guard_audit = closure_sub.add_parser(
        "guard-audit",
        help=(
            "counterfactual: how many assertions this project would have offered a human, and how "
            "many its own higher-power or cross-environment evidence blocks"
        ),
    )
    closure_guard_audit.add_argument("--project", required=True)
    closure_guard_audit.set_defaults(func=_cmd_closure_guard_audit)

    closure_obligations = closure_sub.add_parser(
        "obligations", help="append-only closure obligation ledger (CLI only)"
    )
    obligations_sub = closure_obligations.add_subparsers(
        dest="obligations_command", required=True
    )
    obligations_list = obligations_sub.add_parser("list", help="read the ledger")
    obligations_list.add_argument("--ledger", required=True)
    obligations_list.set_defaults(func=_cmd_closure_obligations)
    obligations_resolve = obligations_sub.add_parser(
        "resolve", help="close an obligation with a human reason and evidence hash"
    )
    obligations_resolve.add_argument("--ledger", required=True)
    obligations_resolve.add_argument("--id", required=True)
    obligations_resolve.add_argument("--reason", required=True)
    obligations_resolve.add_argument("--evidence", required=True)
    obligations_resolve.set_defaults(func=_cmd_closure_obligations)
    obligations_waive = obligations_sub.add_parser(
        "waive", help="explicitly waive an obligation with a human reason"
    )
    obligations_waive.add_argument("--ledger", required=True)
    obligations_waive.add_argument("--id", required=True)
    obligations_waive.add_argument("--reason", required=True)
    obligations_waive.set_defaults(func=_cmd_closure_obligations)

    lineage_parser = sub.add_parser("lineage", help="content-addressed evidence lineage and change impact")
    lineage_sub = lineage_parser.add_subparsers(dest="lineage_command", required=True)
    lineage_build = lineage_sub.add_parser("build")
    lineage_build.add_argument("--bundle", required=True)
    lineage_build.add_argument("--signers-path", default=str(DEFAULT_SIGNER_STORE_PATH))
    lineage_build.add_argument("--output-dir", default="research_agent/web/data/lineage")
    lineage_build.set_defaults(func=_cmd_lineage_build)
    lineage_verify = lineage_sub.add_parser("verify")
    lineage_verify.add_argument("--manifest", required=True)
    lineage_verify.add_argument("--bundle", required=True)
    lineage_verify.add_argument("--output-dir", default="research_agent/web/data/lineage-verify")
    lineage_verify.set_defaults(func=_cmd_lineage_verify)
    lineage_impact = lineage_sub.add_parser("impact")
    lineage_impact.add_argument("--baseline", required=True)
    lineage_impact.add_argument("--bundle", required=True)
    lineage_impact.add_argument("--output-dir", default="research_agent/web/data/lineage-impact")
    lineage_impact.add_argument("--fail-on-stale", action="store_true")
    lineage_impact.set_defaults(func=_cmd_lineage_impact)

    run_parser = sub.add_parser("run", help="S5 local execution and evidence")
    run_sub = run_parser.add_subparsers(dest="run_command", required=True)
    run_execute = run_sub.add_parser("execute")
    run_execute.add_argument("--protocol-id", default="P-iris-logreg-v1")
    run_execute.add_argument("--dataset", choices=["iris", "breast_cancer", "chemlab"], default="iris")
    run_execute.add_argument("--seeds", type=int, default=3)
    run_execute.add_argument("--test-size", type=float, default=0.3)
    run_execute.add_argument("--run-id")
    run_execute.add_argument("--use-lease", action="store_true")
    run_execute.add_argument("--ledger")
    run_execute.add_argument("--lease-scope", default="S5/demo/iris")
    run_execute.add_argument("--output-dir", default="research_agent/web/data/run")
    run_execute.set_defaults(func=_cmd_run_execute)
    run_claim = run_sub.add_parser("claim")
    run_claim.add_argument("--capsule", required=True)
    run_claim.add_argument("--ea", required=True)
    run_claim.add_argument("--statement", required=True)
    run_claim.add_argument("--human-reason", required=True)
    run_claim.add_argument("--scope", default="S5/demo/iris")
    run_claim.add_argument(
        "--assertion",
        action="append",
        help="structured numeric assertion, e.g. metric=accuracy,value=0.95,comparator=>=,tolerance=0.01",
    )
    run_claim.add_argument("--output-dir", default="research_agent/web/data/run-claim")
    run_claim.set_defaults(func=_cmd_run_claim)

    rsi = sub.add_parser("rsi", help="governed RSI control plane")
    rsi_sub = rsi.add_subparsers(dest="rsi_command", required=True)
    rsi_propose = rsi_sub.add_parser("propose")
    rsi_propose.add_argument("--ledger", default=str(DEFAULT_RSI_LEDGER_PATH))
    rsi_propose.add_argument("--kind", choices=["skill", "process", "prompt", "knowledge"], required=True)
    rsi_propose.add_argument("--target", required=True)
    rsi_propose.add_argument("--patch", required=True)
    rsi_propose.add_argument("--rationale", required=True)
    rsi_propose.add_argument("--predicted", required=True)
    rsi_propose.add_argument(
        "--predicted-metric", action="append", default=[], metavar="KEY=VALUE",
        help="numeric prediction this proposal can later be calibrated against, e.g. "
             "recall=0.85 or cost=-0.02; repeatable. Prose alone leaves the loop unable to "
             "learn whether its own predictions were any good",
    )
    rsi_propose.add_argument("--parent")
    rsi_propose.add_argument("--scope")
    rsi_propose.add_argument("--observation")
    rsi_propose.add_argument("--dry-run-ref")
    rsi_propose.add_argument("--policy-path", default=str(DEFAULT_EVOLUTION_POLICY_PATH))
    rsi_propose.set_defaults(func=_cmd_rsi_propose)

    rsi_actuals = rsi_sub.add_parser(
        "actuals", help="record measured outcomes for an episode so its predictions can be calibrated"
    )
    rsi_actuals.add_argument("--ledger", default=str(DEFAULT_RSI_LEDGER_PATH))
    rsi_actuals.add_argument("--episode", required=True)
    rsi_actuals.add_argument("--metric", action="append", default=[], metavar="KEY=VALUE",
                             help="measured numeric outcome, e.g. recall=0.7; repeatable")
    rsi_actuals.add_argument("--note", default="")
    rsi_actuals.set_defaults(func=_cmd_rsi_actuals)

    rsi_policy = rsi_sub.add_parser("policy")
    rsi_policy_sub = rsi_policy.add_subparsers(dest="policy_command", required=True)
    rsi_policy_show = rsi_policy_sub.add_parser("show")
    rsi_policy_show.add_argument("--policy-path", default=str(DEFAULT_EVOLUTION_POLICY_PATH))
    rsi_policy_show.add_argument("--output")
    rsi_policy_show.set_defaults(func=_cmd_rsi_policy)
    rsi_policy_set = rsi_policy_sub.add_parser("set")
    rsi_policy_set.add_argument("--policy-path", default=str(DEFAULT_EVOLUTION_POLICY_PATH))
    policy_switch = rsi_policy_set.add_mutually_exclusive_group()
    policy_switch.add_argument("--enabled", action="store_true")
    policy_switch.add_argument("--disabled", action="store_true")
    rsi_policy_set.add_argument("--scope", action="append", default=[], help="scope=on|off, e.g. literature.query_planner=off")
    rsi_policy_set.set_defaults(func=_cmd_rsi_policy)

    rsi_observations = rsi_sub.add_parser(
        "observations", help="read-only runtime observations and budget suggestions"
    )
    rsi_observations_sub = rsi_observations.add_subparsers(
        dest="observations_command", required=True
    )
    rsi_obs_show = rsi_observations_sub.add_parser("show")
    rsi_obs_show.add_argument("--observations-path", default=str(DEFAULT_EVOLUTION_OBSERVATIONS_PATH))
    rsi_obs_show.add_argument("--limit", type=int, default=20)
    rsi_obs_show.set_defaults(func=_cmd_rsi_observations)
    rsi_obs_suggest = rsi_observations_sub.add_parser("suggest")
    rsi_obs_suggest.add_argument("--observations-path", default=str(DEFAULT_EVOLUTION_OBSERVATIONS_PATH))
    rsi_obs_suggest.add_argument("--output", default="research_agent/web/data/observation-proposal.json")
    rsi_obs_suggest.set_defaults(func=_cmd_rsi_observations)

    rsi_active = rsi_sub.add_parser(
        "active", help="inspect or human-activate a bounded runtime policy"
    )
    rsi_active_sub = rsi_active.add_subparsers(dest="active_command", required=True)
    rsi_active_show = rsi_active_sub.add_parser("show")
    rsi_active_show.add_argument("--active-path", default=str(DEFAULT_EVOLUTION_ACTIVE_PATH))
    rsi_active_show.set_defaults(func=_cmd_rsi_active)
    rsi_active_activate = rsi_active_sub.add_parser("activate")
    rsi_active_activate.add_argument("--active-path", default=str(DEFAULT_EVOLUTION_ACTIVE_PATH))
    rsi_active_activate.add_argument("--ledger", required=True)
    rsi_active_activate.add_argument("--lease-scope", required=True)
    rsi_active_activate.add_argument("--reason", required=True)
    rsi_active_activate.add_argument("--allow-simulation", action="store_true")
    rsi_active_activate.set_defaults(func=_cmd_rsi_active)
    rsi_active_deactivate = rsi_active_sub.add_parser("deactivate")
    rsi_active_deactivate.add_argument("--active-path", default=str(DEFAULT_EVOLUTION_ACTIVE_PATH))
    rsi_active_deactivate.add_argument("--reason", required=True)
    rsi_active_deactivate.set_defaults(func=_cmd_rsi_active)

    rsi_fixture = rsi_sub.add_parser("fixture")
    rsi_fixture.add_argument("--ledger", default=str(DEFAULT_RSI_LEDGER_PATH))
    rsi_fixture.add_argument("--output-dir", default="research_agent/web/data/rsi-fixture")
    rsi_fixture.add_argument("--tasks")
    rsi_fixture.add_argument("--approve", action="store_true")
    rsi_fixture.set_defaults(func=_cmd_rsi_fixture)

    rsi_confirm = rsi_sub.add_parser("confirm")
    rsi_confirm.add_argument("--ledger", default=str(DEFAULT_RSI_LEDGER_PATH))
    rsi_confirm.add_argument("--output-dir", default="research_agent/web/data/rsi-confirmation")
    rsi_confirm.add_argument("--tasks")
    rsi_confirm.set_defaults(func=_cmd_rsi_confirm)

    rsi_real = rsi_sub.add_parser("real-trial")
    rsi_real.add_argument("--ledger", default=str(DEFAULT_RSI_REAL_LEDGER_PATH))
    rsi_real.add_argument("--output-dir", default="research_agent/web/data/rsi-real")
    rsi_real.add_argument("--tasks")
    rsi_real.add_argument("--corpus")
    rsi_real.add_argument("--retriever", choices=["bm25", "minilm", "compare"], default="bm25")
    rsi_real.add_argument("--candidate-file")
    rsi_real.add_argument("--approve", action="store_true")
    rsi_real.set_defaults(func=_cmd_rsi_real_trial)

    rsi_confirm_real = rsi_sub.add_parser("real-confirm")
    rsi_confirm_real.add_argument("--ledger", required=True)
    rsi_confirm_real.add_argument("--output-dir", default="research_agent/web/data/rsi-real-confirmation")
    rsi_confirm_real.add_argument("--lease-scope", default="S1/rsi-ccby-4-compare")
    rsi_confirm_real.add_argument("--tasks")
    rsi_confirm_real.add_argument("--corpus")
    rsi_confirm_real.set_defaults(func=_cmd_rsi_real_confirm)

    rsi_model = rsi_sub.add_parser("propose-model")
    rsi_model.add_argument("--model-path")
    rsi_model.add_argument("--profile")
    rsi_model.add_argument("--store", default=str(DEFAULT_MODEL_STORE_PATH))
    rsi_model.add_argument("--observation", required=True)
    rsi_model.add_argument("--out", default="research_agent/web/data/model-proposal.json")
    rsi_model.add_argument("--policy-path", default=str(DEFAULT_EVOLUTION_POLICY_PATH))
    rsi_model.set_defaults(func=_cmd_rsi_propose_model)

    rsi_batch = rsi_sub.add_parser("model-batch")
    rsi_batch.add_argument("--model-path", required=True)
    rsi_batch.add_argument("--observations", required=True)
    rsi_batch.add_argument("--output-dir", default="research_agent/web/data/model-batch")
    rsi_batch.add_argument("--ledger-root", default="research_agent/web/data/model-batch-ledgers")
    rsi_batch.add_argument("--approve", action="store_true")
    rsi_batch.add_argument("--repair-attempts", type=int, default=0)
    rsi_batch.set_defaults(func=_cmd_rsi_model_batch)

    rsi_s5 = rsi_sub.add_parser("s5-trial")
    rsi_s5.add_argument("--ledger", default=str(DEFAULT_RSI_S5_LEDGER_PATH))
    rsi_s5.add_argument("--output-dir", default="research_agent/web/data/rsi-s5")
    rsi_s5.add_argument("--dataset", choices=["iris", "breast_cancer", "chemlab"], default="iris")
    rsi_s5.add_argument("--approve", action="store_true")
    rsi_s5.set_defaults(func=_cmd_rsi_s5_trial)

    rsi_s5_confirm = rsi_sub.add_parser("s5-confirm")
    rsi_s5_confirm.add_argument("--ledger", required=True)
    rsi_s5_confirm.add_argument("--output-dir", default="research_agent/web/data/rsi-s5-confirmation")
    rsi_s5_confirm.add_argument("--dataset", choices=["iris", "breast_cancer", "chemlab"], default="iris")
    rsi_s5_confirm.add_argument("--lease-scope", default="")
    rsi_s5_confirm.set_defaults(func=_cmd_rsi_s5_confirm)

    rsi_cycle = rsi_sub.add_parser("research-cycle")
    rsi_cycle.add_argument("--tasks", required=True)
    rsi_cycle.add_argument("--ledger", default=str(DEFAULT_RSI_LEDGER_PATH))
    rsi_cycle.add_argument("--output-dir", default="research_agent/web/data/research-cycle")
    rsi_cycle.add_argument("--approve", action="store_true")
    rsi_cycle.add_argument("--policy-path", default=str(DEFAULT_EVOLUTION_POLICY_PATH))
    rsi_cycle.set_defaults(func=_cmd_rsi_research_cycle)

    rsi_story = rsi_sub.add_parser("story")
    rsi_story.add_argument("--ledger", required=True)
    rsi_story.add_argument("--output")
    rsi_story.set_defaults(func=_cmd_rsi_story)

    rsi_status = rsi_sub.add_parser("status")
    rsi_status.add_argument("--ledger", default=str(DEFAULT_RSI_LEDGER_PATH))
    rsi_status.set_defaults(func=_cmd_rsi_status)

    rsi_trace = rsi_sub.add_parser("trace")
    rsi_trace.add_argument("--ledger", required=True)
    rsi_trace.add_argument("--scope", required=True)
    rsi_trace.add_argument("--capsule", required=True)
    rsi_trace.add_argument("--confirmation", default="")
    rsi_trace.set_defaults(func=_cmd_rsi_trace)

    rsi_admit = rsi_sub.add_parser("admit")
    rsi_admit.add_argument("--ledger", default=str(DEFAULT_RSI_LEDGER_PATH))
    rsi_admit.add_argument("--episode", required=True)
    rsi_admit.add_argument("--public-ref", required=True)
    rsi_admit.add_argument("--hidden-ref", required=True)
    rsi_admit.add_argument("--public-metric", action="append")
    rsi_admit.add_argument("--hidden-metric", action="append")
    rsi_admit.add_argument("--near-ood-ref")
    rsi_admit.add_argument("--near-ood-metric", action="append")
    rsi_admit.add_argument("--regression-ref")
    rsi_admit.add_argument("--regression-metric", action="append")
    rsi_admit.add_argument("--n", type=int, default=0)
    rsi_admit.add_argument("--reason", required=True)
    rsi_admit.add_argument("--scope", required=True)
    rsi_admit.add_argument("--ttl-days", type=int, default=90)
    rsi_admit.add_argument("--strict", action="store_true", help="require all four sealed evidence splits with hashes")
    rsi_admit.add_argument("--approved-by", default="human-cli")
    rsi_admit.add_argument("--evaluator", default="manual-cli")
    rsi_admit.add_argument("--task-pack", default="", help="task pack file used for the evaluation")
    rsi_admit.set_defaults(func=_cmd_rsi_admit)

    rsi_reject = rsi_sub.add_parser("reject")
    rsi_reject.add_argument("--ledger", default=str(DEFAULT_RSI_LEDGER_PATH))
    rsi_reject.add_argument("--episode", required=True)
    rsi_reject.add_argument("--reason", required=True)
    rsi_reject.set_defaults(func=_cmd_rsi_reject)

    rsi_revoke = rsi_sub.add_parser("revoke")
    rsi_revoke.add_argument("--ledger", default=str(DEFAULT_RSI_LEDGER_PATH))
    rsi_revoke.add_argument("--lease", required=True)
    rsi_revoke.add_argument("--reason", required=True)
    rsi_revoke.set_defaults(func=_cmd_rsi_revoke)

    # Harness² is an external recursion engine. These commands run it, check its artifact
    # against a frozen contract, and record pending episodes; admission stays with
    # `rsi admit`, which needs a named human and every evidence split.
    rsi_harness2 = rsi_sub.add_parser(
        "harness2", help="run the Harness² recursion engine and ingest its artifact"
    )
    rsi_harness2_sub = rsi_harness2.add_subparsers(dest="harness2_command", required=True)
    h2_probe = rsi_harness2_sub.add_parser("probe", help="read-only seam status")
    h2_probe.add_argument("--root", default="", help="Harness² checkout; defaults to a sibling folder")
    h2_probe.add_argument("--python", default="", help="3.12/3.13 interpreter; auto-detected otherwise")
    h2_probe.set_defaults(func=_cmd_rsi_harness2)

    h2_run = rsi_harness2_sub.add_parser("run", help="run one recursion and write the artifact")
    h2_run.add_argument("--root", default="")
    h2_run.add_argument("--python", default="")
    h2_run.add_argument("--output", default="", help="work directory for the run")
    h2_run.add_argument("--artifact", default="", help="artifact path; defaults to runtime_data/harness2/latest.json")
    h2_run.add_argument("--k", type=int, default=2, help="task-level recursion budget")
    h2_run.add_argument("--mode", choices=["parallel", "sequential", "both"], default="both")
    h2_run.add_argument("--adapter", choices=["demo", "science"], default="science")
    h2_run.add_argument("--timeout", type=int, default=1800)
    h2_run.set_defaults(func=_cmd_rsi_harness2)

    h2_status = rsi_harness2_sub.add_parser("status", help="read the latest artifact and its checklist")
    h2_status.add_argument("--artifact", default="")
    h2_status.set_defaults(func=_cmd_rsi_harness2)

    h2_record = rsi_harness2_sub.add_parser(
        "record", help="write pending episodes for the adopted edits; never admits"
    )
    h2_record.add_argument("--artifact", default="")
    h2_record.add_argument("--ledger", default=str(DEFAULT_RSI_LEDGER_PATH))
    h2_record.add_argument("--scope", default="harness2.harness")
    h2_record.add_argument("--policy-path", default=str(DEFAULT_EVOLUTION_POLICY_PATH))
    h2_record.add_argument(
        "--generation", default="", help="also record this run as an agent generation with this label"
    )
    h2_record.add_argument("--gen-path", default="", help="generation ledger path")
    h2_record.set_defaults(func=_cmd_rsi_harness2)

    # Version the evolution itself on two tracks: the adopted agent harness and this
    # repository's own code. Neither track applies changes or signs; it only records what
    # ran on which code, so a later change can name what needs re-validation.
    rsi_gen = rsi_sub.add_parser(
        "gen", help="two-track version management for evolution (agent harness + platform code)"
    )
    gen_sub = rsi_gen.add_subparsers(dest="gen_command", required=True)
    gen_list = gen_sub.add_parser("list")
    gen_list.add_argument("--kind", choices=["agent", "platform"], default="")
    gen_list.add_argument("--path", default="")
    gen_list.set_defaults(func=_cmd_rsi_gen)

    gen_verify = gen_sub.add_parser("verify", help="check chain, parent links and platform coupling")
    gen_verify.add_argument("--path", default="")
    gen_verify.set_defaults(func=_cmd_rsi_gen)

    gen_snapshot = gen_sub.add_parser("snapshot", help="record the current platform code state")
    gen_snapshot.add_argument("--label", required=True)
    gen_snapshot.add_argument("--commit", default="")
    gen_snapshot.add_argument("--note", default="")
    gen_snapshot.add_argument(
        "--fingerprint", default="", help="record a known earlier state instead of the current one"
    )
    gen_snapshot.add_argument("--path", default="")
    gen_snapshot.set_defaults(func=_cmd_rsi_gen)

    gen_propose = gen_sub.add_parser("propose", help="record a platform patch proposal")
    gen_propose.add_argument("--label", required=True)
    gen_propose.add_argument("--patch", required=True)
    gen_propose.add_argument("--note", default="")
    gen_propose.add_argument("--path", default="")
    gen_propose.set_defaults(func=_cmd_rsi_gen)

    gen_close = gen_sub.add_parser("close", help="mark a generation adopted, reverted or superseded")
    gen_close.add_argument("--id", required=True)
    gen_close.add_argument("--status", choices=["adopted", "reverted", "superseded"], required=True)
    gen_close.add_argument("--commit", default="")
    gen_close.add_argument("--note", default="")
    gen_close.add_argument("--path", default="")
    gen_close.set_defaults(func=_cmd_rsi_gen)

    gen_agent = gen_sub.add_parser("agent", help="record a Harness² run as an agent generation")
    gen_agent.add_argument("--label", required=True)
    gen_agent.add_argument("--artifact", default="")
    gen_agent.add_argument("--episodes", default="", help="comma-separated episode ids")
    gen_agent.add_argument("--status", choices=["proposed", "adopted"], default="adopted")
    gen_agent.add_argument("--note", default="")
    gen_agent.add_argument("--path", default="")
    gen_agent.set_defaults(func=_cmd_rsi_gen)

    gen_compare = gen_sub.add_parser("compare")
    gen_compare.add_argument("--left", required=True)
    gen_compare.add_argument("--right", required=True)
    gen_compare.add_argument("--path", default="")
    gen_compare.set_defaults(func=_cmd_rsi_gen)

    gen_export = gen_sub.add_parser("export", help="write the page projection")
    gen_export.add_argument("--out", default="runtime_data/evolution/story.json")
    gen_export.add_argument("--path", default="")
    gen_export.set_defaults(func=_cmd_rsi_gen)

    action = sub.add_parser("action", help="backend actions behind workspace buttons")
    action_sub = action.add_subparsers(dest="action_command", required=True)
    action_plan = action_sub.add_parser("automation-plan", help="generate a governed auto plan")
    action_plan.add_argument("--topic", required=True)
    action_plan.add_argument("--max-sources", type=int, default=6)
    action_plan.add_argument("--run-dataset", choices=["", "iris", "breast_cancer", "chemlab"], default="")
    action_plan.add_argument("--run-seeds", type=int, default=3)
    action_plan.set_defaults(func=_cmd_action_plan)
    action_skill = action_sub.add_parser("skill", help="run a read-only backend skill")
    action_skill.add_argument("--id", required=True, choices=["literature-brief", "hypothesis-triage", "protocol-review", "evidence-boundary"])
    action_skill.add_argument("--payload", help="JSON file with skill payload")
    action_skill.add_argument("--question")
    action_skill.add_argument("--max-sources", type=int)
    action_skill.add_argument("--source", choices=["fixture", "real"])
    action_skill.set_defaults(func=_cmd_action_skill)

    workspace = sub.add_parser("workspace", help="local workspace registry, memory and archive")
    workspace_sub = workspace.add_subparsers(dest="workspace_command", required=True)

    workspace_agents = workspace_sub.add_parser("agents", help="export the read-only module registry")
    workspace_agents.add_argument("--output")
    workspace_agents.set_defaults(func=_cmd_workspace_agents)

    workspace_commands = workspace_sub.add_parser("commands", help="export the descriptive command catalog")
    workspace_commands.add_argument("--output")
    workspace_commands.set_defaults(func=_cmd_workspace_commands)

    workspace_export = workspace_sub.add_parser("export", help="write frontend settings snapshots")
    workspace_export.add_argument("--output-dir", default="apps/web/public")
    workspace_export.set_defaults(func=_cmd_workspace_export)

    workspace_preflight = workspace_sub.add_parser(
        "preflight", help="report which link of the spec/export/tool chain is stale"
    )
    workspace_preflight.add_argument("--output", default="")
    workspace_preflight.set_defaults(func=_cmd_workspace_preflight)

    workspace_memory = workspace_sub.add_parser("memory", help="manage workspace memory")
    memory_sub = workspace_memory.add_subparsers(dest="memory_command", required=True)
    memory_list = memory_sub.add_parser("list")
    memory_list.add_argument("--store", default=str(DEFAULT_WORKSPACE_MEMORY_PATH))
    memory_list.set_defaults(func=_cmd_workspace_memory)
    memory_add = memory_sub.add_parser("add")
    memory_add.add_argument("--text", required=True)
    memory_add.add_argument("--kind", choices=["decision", "preference", "constraint", "note"], default="note")
    memory_add.add_argument("--scope", default="workspace")
    memory_add.add_argument("--source", default="cli")
    memory_add.add_argument("--store", default=str(DEFAULT_WORKSPACE_MEMORY_PATH))
    memory_add.set_defaults(func=_cmd_workspace_memory)
    memory_delete = memory_sub.add_parser("delete")
    memory_delete.add_argument("--id", required=True)
    memory_delete.add_argument("--store", default=str(DEFAULT_WORKSPACE_MEMORY_PATH))
    memory_delete.set_defaults(func=_cmd_workspace_memory)

    workspace_archive = workspace_sub.add_parser("archive", help="manage local task snapshots")
    archive_sub = workspace_archive.add_subparsers(dest="archive_command", required=True)
    archive_list = archive_sub.add_parser("list")
    archive_list.add_argument("--root", default=str(DEFAULT_WORKSPACE_ARCHIVE_ROOT))
    archive_list.set_defaults(func=_cmd_workspace_archive)
    archive_add = archive_sub.add_parser("add")
    archive_add.add_argument("--file", required=True)
    archive_add.add_argument("--title", required=True)
    archive_add.add_argument("--task-id", required=True)
    archive_add.add_argument("--note", default="")
    archive_add.add_argument("--root", default=str(DEFAULT_WORKSPACE_ARCHIVE_ROOT))
    archive_add.set_defaults(func=_cmd_workspace_archive)
    archive_get = archive_sub.add_parser("get")
    archive_get.add_argument("--id", required=True)
    archive_get.add_argument("--root", default=str(DEFAULT_WORKSPACE_ARCHIVE_ROOT))
    archive_get.set_defaults(func=_cmd_workspace_archive)
    archive_delete = archive_sub.add_parser("delete")
    archive_delete.add_argument("--id", required=True)
    archive_delete.add_argument("--root", default=str(DEFAULT_WORKSPACE_ARCHIVE_ROOT))
    archive_delete.set_defaults(func=_cmd_workspace_archive)

    maintenance = sub.add_parser("maintenance", help="plan and reclose evidence changes")
    maintenance_sub = maintenance.add_subparsers(dest="maintenance_command", required=True)
    maintenance_plan = maintenance_sub.add_parser("plan", help="create a maintenance plan from a lineage baseline")
    maintenance_plan.add_argument("--baseline", required=True)
    maintenance_plan.add_argument("--bundle", required=True)
    maintenance_plan.add_argument("--actor", required=True)
    maintenance_plan.add_argument("--reason", required=True)
    maintenance_plan.add_argument("--output-dir", default="runtime_data/maintenance")
    maintenance_plan.set_defaults(func=_cmd_maintenance_plan)
    maintenance_reclose = maintenance_sub.add_parser("reclose", help="re-run closure only when the plan is recheck-only")
    maintenance_reclose.add_argument("--plan", required=True)
    maintenance_reclose.add_argument("--bundle", required=True)
    maintenance_reclose.add_argument("--demo", required=True)
    maintenance_reclose.add_argument("--claim", required=True)
    maintenance_reclose.add_argument("--output-dir", default="runtime_data/maintenance/reclose")
    maintenance_reclose.set_defaults(func=_cmd_maintenance_reclose)

    waitpoint = sub.add_parser("waitpoint", help="local durable waitpoints for external jobs")
    waitpoint_sub = waitpoint.add_subparsers(dest="waitpoint_command", required=True)
    waitpoint_create = waitpoint_sub.add_parser("create", help="create a waitpoint and print its one-time secret")
    waitpoint_create.add_argument("--label", required=True)
    waitpoint_create.add_argument("--intent", required=True)
    waitpoint_create.add_argument("--owner", required=True)
    waitpoint_create.add_argument("--ttl-hours", type=int, default=168)
    waitpoint_create.add_argument("--max-signals", type=int, default=1)
    waitpoint_create.add_argument("--member", action="append", default=None)
    waitpoint_create.add_argument("--quorum", default="all")
    waitpoint_create.add_argument("--no-fail-fast", dest="fail_fast", action="store_false", default=True)
    waitpoint_create.add_argument("--root", default=None)
    waitpoint_create.set_defaults(func=_cmd_waitpoint_create)
    waitpoint_signal = waitpoint_sub.add_parser("signal", help="record an external job signal")
    waitpoint_signal.add_argument("--id", required=True)
    waitpoint_signal.add_argument("--secret", default=None)
    waitpoint_signal.add_argument("--status", choices=["ok", "fail", "progress"], default="ok")
    waitpoint_signal.add_argument("--message", default="")
    waitpoint_signal.add_argument("--data-file", default=None)
    waitpoint_signal.add_argument("--member", default=None)
    waitpoint_signal.add_argument("--dedupe-key", default=None)
    waitpoint_signal.add_argument("--source", default="cli")
    waitpoint_signal.add_argument("--root", default=None)
    waitpoint_signal.set_defaults(func=_cmd_waitpoint_signal)
    waitpoint_status = waitpoint_sub.add_parser("status", help="show one waitpoint")
    waitpoint_status.add_argument("--id", required=True)
    waitpoint_status.add_argument("--root", default=None)
    waitpoint_status.set_defaults(func=_cmd_waitpoint_status)
    waitpoint_list = waitpoint_sub.add_parser("list", help="list waitpoints")
    waitpoint_list.add_argument("--owner", default=None)
    waitpoint_list.add_argument("--root", default=None)
    waitpoint_list.set_defaults(func=_cmd_waitpoint_list)
    waitpoint_inbox = waitpoint_sub.add_parser("inbox", help="show undelivered wakes for an owner")
    waitpoint_inbox.add_argument("--owner", required=True)
    waitpoint_inbox.add_argument("--root", default=None)
    waitpoint_inbox.set_defaults(func=_cmd_waitpoint_inbox)
    waitpoint_consume = waitpoint_sub.add_parser("consume", help="mark wakes delivered for an owner")
    waitpoint_consume.add_argument("--owner", required=True)
    waitpoint_consume.add_argument("--root", default=None)
    waitpoint_consume.set_defaults(func=_cmd_waitpoint_consume)
    waitpoint_expire = waitpoint_sub.add_parser("expire", help="expire due waitpoints and create expired wakes")
    waitpoint_expire.add_argument("--root", default=None)
    waitpoint_expire.set_defaults(func=_cmd_waitpoint_expire)
    waitpoint_triage = waitpoint_sub.add_parser(
        "triage",
        help="relevance-check undelivered wakes against a declared scope; record delegation events (default reject)",
    )
    waitpoint_triage.add_argument("--project", required=True)
    waitpoint_triage.add_argument("--owner", required=True)
    waitpoint_triage.add_argument("--scope", action="append", default=None)
    waitpoint_triage.add_argument("--root", default=None)
    waitpoint_triage.set_defaults(func=_cmd_waitpoint_triage)

    execp = sub.add_parser("exec", help="read-only execution-face pool (ExecPort)")
    exec_sub = execp.add_subparsers(dest="exec_command", required=True)
    exec_faces = exec_sub.add_parser("faces", help="describe the registered execution faces")
    exec_faces.set_defaults(func=_cmd_exec_faces)

    research = sub.add_parser("research", help="run the fixture research queue")
    research_sub = research.add_subparsers(dest="research_command", required=True)
    research_run = research_sub.add_parser("run")
    research_run.add_argument("--tasks", required=True)
    research_run.add_argument("--output-dir", default="research_agent/web/data/research-queue")
    research_run.set_defaults(func=_cmd_research_run)

    web = sub.add_parser("web", help="serve the static workbench")
    web.add_argument("--port", type=int, default=8010)
    web.set_defaults(func=_cmd_web)

    return parser


def _ensure_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, ValueError):
                pass


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "spec":
            store = SpecStore()
            return args.func(store, args)
        return args.func(args)
    except ModelTurnPending as exc:
        # A host-agent profile deferred the turn: this is a handoff, not a crash. Exit 3 tells a
        # driving agent to answer the turn and re-run the same command.
        print(
            "awaiting host model: %s\n"
            "answer it with `python -m research_agent host-model turns`, then "
            "`host-model respond --turn-id ... --file answer.json`, and re-run this command "
            "(replay reuses turns that are already answered)." % exc,
            file=sys.stderr,
        )
        return 3
    except (SpecError, RSIPolicyError, WorkspaceStoreError, ActionError, RuntimeError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
