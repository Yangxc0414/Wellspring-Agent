"""Documented JSON paths are an interface; an unexplained one is a broken handoff.

60-科研智能体设计缺陷与改正.md D6 measured it: AGENTS.md names ~29 ``*.json`` paths and
19 of them do not exist in a clean checkout. Copying
``rsi real-trial --ledger research_agent/web/data/rsi-compare-ledger.json`` fails immediately.
The documents are how one agent hands a command to the next, so a path that exists only in
prose is a handoff that cannot be executed. A regex-based "freshness" check cannot catch this:
it looks for one number, not for every path the document asks a reader to use.

So this module enumerates instead of sampling. Every ``*.json`` reference in AGENTS.md and
modules/*/SPEC.md is classified as one of: exists / generated (with the command that produces
it) / template (contains a placeholder) / relative_artifact (a run- or project-relative product
name declared by a SPEC) / not_a_path (an extension list or a joined pair of names) /
unexplained. Silence is not a reason: absence of an explanation is itself a reported row, and
tests/test_doc_interfaces.py asserts the unexplained set is empty. A path renamed in a living
document without updating GENERATED_BY therefore turns the suite red.

This is deliberately a report plus a ratchet, not a gate that creates files: adding a new
documented output must come with the command that produces it, and nothing here writes to the
repository, changes a judgement, or touches a gate.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import REPO_ROOT, build_info

SCHEMA_VERSION = "doc-interface-audit-0.1"

# A reference may start with a placeholder, a bare filename, or a repo-relative path. The
# lookbehind keeps a long path from being reported as its own tail.
_JSON_REF = re.compile(r"(?<![A-Za-z0-9_./-])([A-Za-z0-9_.<>/*-]*\.json)(?![A-Za-z0-9_])")

LIVING_DOC = "AGENTS.md"
SPEC_GLOB = "modules/*/SPEC.md"

# First path segment of a product name that a SPEC declares relative to a run/project directory.
# These are not files in the checkout and must never be "fixed" by creating them at the root.
RELATIVE_PREFIXES = (
    "autopilot", "claim", "closure", "closure-signature", "closed-loop", "fixtures",
    "flow", "inbox", "inputs", "outbox", "pipeline-chemlab", "run",
)

EXISTS = "exists"
GENERATED = "generated"
TEMPLATE = "template"
RELATIVE_ARTIFACT = "relative_artifact"
NOT_A_PATH = "not_a_path"
ARTIFACT_NAME = "artifact_name"
UNEXPLAINED = "unexplained"
KINDS = (
    EXISTS, GENERATED, TEMPLATE, RELATIVE_ARTIFACT, ARTIFACT_NAME, NOT_A_PATH, UNEXPLAINED,
)

# A SPEC Changelog is a dated historical record, not a copyable interface. test_docs_freshness.py
# already excludes dated logs for the same reason. Skipping is counted, never silent: the audit
# reports how many sections were skipped and how many references they contained.
_CHANGELOG_HEADING = re.compile(r"^## Changelog\s*$", re.MULTILINE)

TEMPLATE_REASON = "contains a placeholder (< > * ...); replace it before copying the command"
RELATIVE_REASON = (
    "a run/project-relative product name declared by a SPEC, created by that module's command "
    "inside the run directory; it is not a file in the checkout"
)
BASENAME_REASON = (
    "a bare product name in a SPEC (not a path); its producing command is declared in that "
    "module's Contract/Current Implementation"
)
NOT_A_PATH_REASON = "an extension list, a joined pair of names, or a shell fragment, not a path"

# Every entry must name BOTH the command and why the file is absent from a clean checkout.
# A reason without a command is the "silence is not a reason" failure D6 warns about.
GENERATED_BY = {
    "answer.json": {
        "command": "python -m research_agent host-model respond --turn-id MT-... --file answer.json",
        "reason": "written by the human/host outside the repo; it is an input to respond, not an output",
    },
    "autopilot-policy.json": {
        "command": "human-authored autopilot policy (python -m research_agent autopilot policy init)",
        "reason": "AGENTS.md §7 forbids an agent from creating or relaxing this policy; it starts absent",
    },
    "project.json": {
        "command": "python -m research_agent project init --project <dir>",
        "reason": "created inside a project directory, never at the repository root",
    },
    "research_agent/web/data/rsi-compare-ledger.json": {
        "command": "python -m research_agent rsi propose --ledger research_agent/web/data/rsi-compare-ledger.json ...",
        "reason": "first propose writes the ledger; real-trial/real-confirm in AGENTS.md §4 then consume it",
    },
    "research_agent/web/data/rsi-mini-ledger.json": {
        "command": "python -m research_agent rsi propose --ledger research_agent/web/data/rsi-mini-ledger.json ...",
        "reason": "ledger for the minilm retriever trial in AGENTS.md §4; absent until that trial is run",
    },
    "research_agent/web/data/rsi-model-ledger.json": {
        "command": "python -m research_agent rsi propose --ledger research_agent/web/data/rsi-model-ledger.json ...",
        "reason": "ledger for the model-candidate trial in AGENTS.md §4; absent until that trial is run",
    },
    "research_agent/web/data/rsi-s5-ledger.json": {
        "command": "python -m research_agent rsi propose --ledger research_agent/web/data/rsi-s5-ledger.json ...",
        "reason": "ledger for the S5 trial (rsi s5-trial / run execute --use-lease) in AGENTS.md §4",
    },
    "research_agent/web/data/rsi-s5bc-ledger.json": {
        "command": "python -m research_agent rsi propose --ledger research_agent/web/data/rsi-s5bc-ledger.json ...",
        "reason": "ledger for the breast_cancer S5 trial in AGENTS.md §4; absent until that trial is run",
    },
    "research_agent/web/data/model-proposal.json": {
        "command": "python -m research_agent rsi propose-model --out research_agent/web/data/model-proposal.json ...",
        "reason": "an output of propose-model; real-trial --candidate-file then reads it",
    },
    "research_agent/web/data/flow/g1-decision.json": {
        "command": "python -m research_agent flow g1 --output-dir research_agent/web/data/flow ...",
        "reason": "the G1 human decision produced by flow g1; strict pipeline mode refuses to run without it",
    },
    "research_agent/web/data/flow/idea.json": {
        "command": "python -m research_agent pipeline run --output-dir <dir> ... (idea stage)",
        "reason": "input to flow g1 (--idea-file); produced by an earlier pipeline run, not checked in",
    },
    "research_agent/web/data/pipeline-chemlab/demo.json": {
        "command": "python -m research_agent pipeline run --run-dataset chemlab --output-dir research_agent/web/data/pipeline-chemlab ...",
        "reason": "pipeline demo artifact from the ChemLab run in AGENTS.md §4; not a committed fixture",
    },
    "research_agent/web/data/pipeline-chemlab/experiment.json": {
        "command": "python -m research_agent pipeline run --run-dataset chemlab --output-dir research_agent/web/data/pipeline-chemlab ...",
        "reason": "S4 design artifact consumed by protocol freeze-design; produced by the same pipeline run",
    },
    "research_agent/web/data/pipeline-chemlab/run/run-capsule.json": {
        "command": "python -m research_agent pipeline run --run-dataset chemlab --output-dir research_agent/web/data/pipeline-chemlab ...",
        "reason": "S5 RunCapsule produced by the same pipeline run; protocol freeze reads it as --capsule",
    },
    "research_agent/web/data/protocol/protocol-card.json": {
        "command": "python -m research_agent protocol freeze-design|freeze --output-dir research_agent/web/data/protocol ...",
        "reason": "frozen protocol produced by the CLI human-gate step; strict mode consumes it at G2",
    },
    "research_agent/web/data/run-claim/claim.json": {
        "command": "python -m research_agent run claim --output-dir research_agent/web/data/run-claim ...",
        "reason": "human-signed Claim; AGENTS.md §5 forbids creating it from MCP/HTTP, so it starts absent",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def doc_sources(root: Path) -> List[Tuple[str, Path]]:
    """(label, path) for the living doc and every module SPEC, in stable order."""
    sources = [(LIVING_DOC, root / LIVING_DOC)]
    sources.extend(
        (path.relative_to(root).as_posix(), path) for path in sorted(root.glob(SPEC_GLOB))
    )
    return [(label, path) for label, path in sources if path.is_file()]


def find_json_references(text: str) -> List[str]:
    """Distinct ``*.json`` references in document order (sorted for a stable report)."""
    return sorted(set(_JSON_REF.findall(text)))


def classify_reference(
    ref: str, root: Path, reasons: Dict[str, Dict[str, str]], strict_basenames: bool
) -> Dict[str, str]:
    basename = ref.rsplit("/", 1)[-1]
    if basename.startswith(".") or ".json/" in ref:
        kind, reason = NOT_A_PATH, NOT_A_PATH_REASON
    elif any(ch in ref for ch in "<>*") or "..." in ref:
        kind, reason = TEMPLATE, TEMPLATE_REASON
    elif (root / ref).is_file():
        kind, reason = EXISTS, "present in this checkout"
    elif ref in reasons and reasons[ref].get("command") and reasons[ref].get("reason"):
        kind = GENERATED
        reason = "%s — %s" % (reasons[ref]["command"], reasons[ref]["reason"])
    elif "/" not in ref and not strict_basenames:
        kind, reason = ARTIFACT_NAME, BASENAME_REASON
    elif "/" in ref and ref.split("/", 1)[0] in RELATIVE_PREFIXES:
        kind, reason = RELATIVE_ARTIFACT, RELATIVE_REASON
    else:
        kind, reason = UNEXPLAINED, ""
    return {"path": ref, "kind": kind, "reason": reason}


def interface_text(text: str, strict: bool) -> Tuple[str, str]:
    """Split a document into its copyable interface and its dated historical tail.

    ``strict`` is used for AGENTS.md, which has no Changelog and whose every reference is a
    command a reader may copy. SPEC changelogs quote paths from past runs and from regression
    examples; treating those as live interface entries produced a false unexplained row the first
    time this audit ran. The skipped tail is returned so the audit can count it instead of
    dropping it.
    """
    normalized = text.replace("\r\n", "\n")
    if strict:
        return normalized, ""
    match = _CHANGELOG_HEADING.search(normalized)
    if not match:
        return normalized, ""
    return normalized[:match.start()], normalized[match.start():]


def classify_references(
    text: str, root: Path, reasons: Optional[Dict[str, Dict[str, str]]] = None,
    strict_basenames: bool = False,
) -> List[Dict[str, str]]:
    """Classify every reference in one document. Pure: never reads or writes repository state."""
    active = GENERATED_BY if reasons is None else reasons
    return [
        classify_reference(ref, root, active, strict_basenames)
        for ref in find_json_references(text)
    ]


def audit_doc_interfaces(root: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only enumeration of documented JSON paths and their explanations.

    The returned object is itself a projection and therefore fills every slot of the
    projection contract in research_agent/projections.py.
    """
    base = Path(root or REPO_ROOT)
    rows: List[Dict[str, str]] = []
    sources: List[str] = []
    skipped_sections = 0
    skipped_references = 0
    for label, path in doc_sources(base):
        sources.append(label)
        strict = label == LIVING_DOC
        interface, history = interface_text(path.read_text(encoding="utf-8"), strict)
        if history:
            skipped_sections += 1
            skipped_references += len(find_json_references(history))
        for row in classify_references(interface, base, strict_basenames=strict):
            rows.append(dict(row, source=label))
    counts = {kind: 0 for kind in KINDS}
    for row in rows:
        counts[row["kind"]] += 1
    unexplained = sorted(set(row["path"] for row in rows if row["kind"] == UNEXPLAINED))
    referenced = set(row["path"] for row in rows)
    stale_allowlist = sorted(set(GENERATED_BY) - referenced)
    # A reason that does not name a command is not a reason at all.
    reasonless = sorted(
        name for name, entry in GENERATED_BY.items()
        if not entry.get("command") or not entry.get("reason")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "source_fingerprint": str(build_info().get("fingerprint") or ""),
        "read_only": True,
        "base": (
            "%d distinct *.json references enumerated across %d documents (%s + modules/*/SPEC.md); "
            "%d are unexplained. Denominator is references, not lines or files; a bare product "
            "name and a repo-relative path are counted separately so neither is silently dropped"
            % (len(rows), len(sources), LIVING_DOC, len(unexplained))
        ),
        "provenance": {
            "scan": "read-only regex enumeration of Markdown; no command is executed",
            "sources": sources,
            "strict_basenames_in": [LIVING_DOC],
            "fixture_mode": False,
            "simulation": False,
            "language": "en",
            "classification": list(KINDS),
            "relative_prefixes": sorted(set(RELATIVE_PREFIXES)),
            "excluded_as_history": "modules/*/SPEC.md sections from '## Changelog' onward",
        },
        "counts": counts,
        "skipped_sections": skipped_sections,
        "skipped_references": skipped_references,
        "total_references": len(rows),
        "unexplained": unexplained,
        "stale_allowlist": stale_allowlist,
        "reasonless_allowlist": reasonless,
        "generated_paths": sorted(GENERATED_BY),
        "rows": rows,
        "boundary": (
            "a report and a test ratchet, not a gate that creates files: it never writes to the "
            "repository, never changes a judgement/gate/signature, and does not prove that a "
            "command named in GENERATED_BY actually succeeds. A template or a relative product "
            "name has an explicit class-level reason, never silence. SPEC Changelog sections are "
            "dated history, not a copyable interface (the same exclusion test_docs_freshness.py "
            "uses); the number of skipped sections and the references inside them are counted in "
            "this report rather than silently dropped. The shortest copyable command chain from "
            "60-D6 is still a separate deliverable and must not be claimed as implemented by "
            "this audit."
        ),
    }


__all__ = [
    "GENERATED_BY",
    "KINDS",
    "LIVING_DOC",
    "SCHEMA_VERSION",
    "UNEXPLAINED",
    "audit_doc_interfaces",
    "classify_reference",
    "classify_references",
    "doc_sources",
    "find_json_references",
    "interface_text",
]
