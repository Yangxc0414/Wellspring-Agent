"""One implementation of "attach a journal skill pack rubric to a venue audit".

Both the CLI and the MCP tool call this, so the two surfaces cannot disagree about what a
pack contributed; when they were written separately, the host-facing tool silently lacked the
pack arguments the CLI had.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from .skill_packs import STAGE_PROFILES, coverage_report, find_venue, scan_pack

ADVISORY_BOUNDARY = (
    "advisory rubric extracted from a local skill pack; it is not a pass/fail check, "
    "not evidence, and not an official journal template"
)


def artifact_text(path: Any) -> str:
    """Flatten a rubric input (JSON artifact or Markdown/TeX/plain draft) into scored text.

    Both faces used to parse JSON only, which made the pack rubric unusable on the
    actual paper file — the one artifact a reviewer reads.
    """
    target = Path(path)
    raw = target.read_text(encoding="utf-8")
    if target.suffix.lower() != ".json":
        return raw
    import json

    texts = []

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif value is not None:
            texts.append(str(value))

    walk(json.loads(raw))
    return "\n".join(texts)


def manuscript_pack_text(data: Dict[str, Any], kind: str, sections: Optional[Dict[str, Any]] = None) -> str:
    """Flatten an audit input into the text the rubric is scored against."""
    if kind != "zh_journal":
        return "\n".join(str(value) for value in (sections or {}).values())
    parts = [
        str(data.get("abstract") or ""),
        " ".join(str(item) for item in data.get("keywords") or []),
    ]
    parts += [
        str(section.get("text") or "")
        for section in data.get("sections") or []
        if isinstance(section, dict)
    ]
    parts += [
        str(ref.get("title") or "")
        for ref in data.get("references") or []
        if isinstance(ref, dict)
    ]
    return "\n".join(parts)


# A reviewer reads a study package as a bundle, not as one file at a time. Measured on the real
# full-chain package: the pre-registration alone scores 0 of 6 design items while the same
# content as a bundle scores 2, and the README alone scores 1 of 23 submission items where the
# bundle scores 4. Scoring a single file therefore under-reports our own work, so a directory is
# accepted here — but the concatenation is reported (which files, how many bytes, whether a cap
# cut it) because an unlisted splice would just be a second, quieter denominator.
BUNDLE_SUFFIXES = (".md", ".json", ".txt", ".tex")
# Prose first, then JSON: sorted-by-path ordering let a single 709 KB pipeline state dump eat the
# whole character budget and push the manuscript and the report out of the bundle entirely.
BUNDLE_PROSE_SUFFIXES = (".md", ".tex", ".txt")
BUNDLE_MAX_FILES = 16
BUNDLE_MAX_CHARS = 200000
BUNDLE_MAX_FILE_CHARS = 40000
# The three numeric artifacts are the measurement, not prose about it: their per-cell floats and
# node lists would dominate a lexical score without saying anything a rubric asks about, and the
# same content is already projected into the README and the brief by this framework's own code.
# They are excluded by name, and the exclusion is printed rather than silent.
BUNDLE_NUMERIC_ARTIFACTS = ("study.json", "study-evidence.json", "closure-report.json")
# Released outputs are data, not prose: scoring them would let a lexical match against thousands of
# numbers credit any rubric item, so they stay out of the text. They must not be silently skipped
# either, because "model outputs released with the paper" is a requirement about their presence.
BUNDLE_DATA_SUFFIXES = (".csv", ".tsv", ".jsonl")


def artifact_base(target: Path) -> Dict[str, Any]:
    """The base a quoted coverage ratio needs: which build printed this artifact, and when.

    Measured need: the same study design scored 0/14 and 8/14 on the same rubric purely because
    one README was printed by an older generator and the other by the current one, and a third
    package scored 0/14 because its bundle mixed scripts. A coverage number without these slots
    is not comparable to another coverage number, so they travel with it. A package MANIFEST
    records both the fingerprint that printed it and the current one, which turns "is this
    artifact stale?" into a comparison instead of a guess. Slots that cannot be filled are left
    empty and rendered as ``unknown`` by the report rather than dropped.
    """
    import json

    base: Dict[str, Any] = {
        "path": str(target),
        "fingerprint": "",
        "fingerprint_now": "",
        "generated_at": "",
        "language": "",
        "foreign_script_fields": 0,
    }
    manifest = target / "MANIFEST.json" if target.is_dir() else None
    if manifest is not None and manifest.is_file():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        if isinstance(payload, dict):
            base["fingerprint"] = str(payload.get("code_fingerprint_recorded") or "")
            base["fingerprint_now"] = str(payload.get("code_fingerprint_now") or "")
            base["generated_at"] = str(payload.get("generated_at") or "")
            foreign = payload.get("foreign_script_fields")
            base["foreign_script_fields"] = len(foreign) if isinstance(foreign, list) else 0
            base["language"] = "mixed-script" if base["foreign_script_fields"] else "monolingual"
    return base


def coverage_input(path: Any):
    """(text, extra_fields) for a rubric input: one file, or a whole package directory.

    Both faces read through here, or CLI and MCP would answer the same request differently.
    """
    target = Path(path)
    if not target.is_dir():
        # a single file is not a bundle, so it carries no bundle metadata: the base it can offer is
        # its path, which every caller already reports as `input`
        return artifact_text(target), {}
    scored, numeric, skipped = [], [], 0
    data = []
    for item in target.rglob("*"):
        if not item.is_file():
            continue
        if item.name in BUNDLE_NUMERIC_ARTIFACTS:
            numeric.append(item.relative_to(target).as_posix())
        elif item.suffix.lower() in BUNDLE_DATA_SUFFIXES:
            with open(str(item), "rb") as stream:
                data.append(
                    {
                        "path": item.relative_to(target).as_posix(),
                        "bytes": item.stat().st_size,
                        "lines": sum(1 for _ in stream),
                    }
                )
        elif item.suffix.lower() in BUNDLE_SUFFIXES:
            scored.append(item)
        else:
            skipped += 1
    # prose artifacts are what a reviewer reads, so they claim the budget before any machine dump
    candidates = sorted(
        scored,
        key=lambda item: (
            0 if item.suffix.lower() in BUNDLE_PROSE_SUFFIXES else 1,
            item.relative_to(target).as_posix(),
        ),
    )
    parts = []
    files = []
    used = 0
    truncated = False
    for item in candidates:
        if len(parts) >= BUNDLE_MAX_FILES:
            truncated = True
            break
        room = BUNDLE_MAX_CHARS - used
        if room <= 0:
            truncated = True
            break
        raw = item.read_text(encoding="utf-8", errors="replace")
        if len(raw) > BUNDLE_MAX_FILE_CHARS:
            raw = raw[:BUNDLE_MAX_FILE_CHARS]
            truncated = True
        if len(raw) > room:
            raw = raw[:room]
            truncated = True
        used += len(raw)
        parts.append(raw)
        files.append({"path": item.relative_to(target).as_posix(), "chars": len(raw)})
    text = "\n".join(parts)
    return text, {
        "artifact_base": artifact_base(target),
        "bundle": {
            "unit": "directory",
            "files": files,
            "file_count": len(files),
            "considered": len(candidates),
            "excluded_numeric_artifacts": numeric,
            "data_files": data,
            "skipped_unsupported_suffix": skipped,
            "chars": len(text),
            "order": "prose artifacts first, then JSON, each group by path",
            "max_files": BUNDLE_MAX_FILES,
            "max_file_chars": BUNDLE_MAX_FILE_CHARS,
            "max_chars": BUNDLE_MAX_CHARS,
            "truncated": bool(truncated or len(files) < len(candidates)),
            "boundary": (
                "a bundle is scored as one text so that the unit of scoring matches the unit a "
                "reviewer reads; the file list and excluded_numeric_artifacts above are the whole "
                "input, data_files lists released tabular outputs by path, bytes and line count "
                "without scoring them (a lexical match against thousands of numbers would credit "
                "any rubric item), and a skipped_unsupported_suffix of zero means nothing in the "
                "package was dropped without being named; lexical coverage of a concatenation can "
                "still credit a term appearing in any one of its files, and a truncated bundle "
                "scores a partial rubric. Including an internal state dump scores the pipeline's "
                "own ledger rather than the paper, which is why prose is taken first and every "
                "file is capped"
            ),
        }
    }


def resolve_pack_dir(pack_dir: str, pack_root: str, venue: str) -> str:
    """A direct pack directory, or the one a venue name routes to."""
    if pack_dir:
        return pack_dir
    if not (pack_root and venue):
        return ""
    try:
        route = find_venue(Path(pack_root), venue)
    except ValueError as exc:
        # a wrong --pack-root is a routing failure, not a stack trace
        raise ValueError(
            "%s; pass pack_dir (CLI: --pack) with an explicit pack directory, or point pack_root "
            "(CLI: --pack-root) at the journal-skill root that contains "
            "shared-resources/journal-selection and give venue (CLI: --venue)" % exc
        )
    best = route.get("best") or {}
    if not best or not best.get("pack_exists"):
        raise ValueError("no local pack matched venue: " + venue)
    return str(best["pack_root"])


def route_for_venue(pack_root: str, venue: str) -> Dict[str, Any]:
    if not (pack_root and venue):
        return {}
    return find_venue(Path(pack_root), venue) or {}


def attach_pack_rubric(
    result: Dict[str, Any],
    pack_text: str,
    *,
    pack_dir: str = "",
    pack_root: str = "",
    venue: str = "",
    stage: str = "",
    profile: str = "",
    max_items: int = 40,
) -> bool:
    """Add ``skill_pack`` (checklist, coverage with its scored denominator, license, route)
    to an audit result. Returns False when no pack was asked for.
    """
    resolved = resolve_pack_dir(pack_dir, pack_root, venue)
    if not resolved:
        return False
    if stage and profile:
        raise ValueError("choose a stage or a profile, not both")
    if profile and profile not in STAGE_PROFILES:
        raise ValueError("unknown profile: " + profile)
    profile_stages = list(STAGE_PROFILES.get(profile, ()))
    pack = scan_pack(
        Path(resolved), stage=stage, max_items=max_items, stages=profile_stages
    )
    coverage = coverage_report(
        pack["checklist"], pack_text, stage=stage, stages=profile_stages
    )
    coverage["profile"] = profile
    # a ratio over a truncated rubric has to say so, or it reads as a full review
    coverage["pack_scope"] = {
        "pack": pack["pack"],
        "checklist_items": len(pack["checklist"]),
        "checklist_total": pack["checklist_total"],
        "max_items": max_items,
        "limit_applied": pack["limit_applied"],
        "truncated": pack["truncated"],
        "warnings": pack["warnings"],
    }
    if pack["truncated"]:
        coverage["boundary"] += (
            " this score uses only the first %d of %d pack items, so it is a partial rubric"
            % (len(pack["checklist"]), pack["checklist_total"])
        )
    result["skill_pack"] = {
        "pack": pack["pack"],
        "coverage": coverage,
        "license": pack["license"],
        "stage_counts": pack["stage_counts"],
        "actionable_counts": pack["actionable_counts"],
        "checklist": pack["checklist"],
        "checklist_total": pack["checklist_total"],
        "truncated": pack["truncated"],
        "warnings": pack["warnings"],
        "boundary": ADVISORY_BOUNDARY,
    }
    warnings = result.setdefault("warnings", [])
    route = route_for_venue(pack_root, venue)
    if route:
        result["skill_pack"]["route"] = route.get("best")
        result["skill_pack"]["route_confidence"] = route.get("confidence")
        if route.get("confidence") == "low":
            warnings.append(
                "skill_pack: low-confidence route to %s; verify the pack manually"
                % (route.get("best") or {}).get("pack_dir", "")
            )
    scope_like = int(coverage.get("scope_like") or 0)
    if scope_like:
        warnings.append(
            "skill_pack: %d scored item(s) look like scope or verified-fact statements rather "
            "than author requirements (scope_like=true); a human should dismiss them, the "
            "heuristic does not" % scope_like
        )
    warnings.extend(
        "skill_pack: " + item for item in (coverage.get("warnings") or [])
    )
    warnings.append(
        "skill_pack: advisory checklist from %s; target journal template wins" % pack["pack"]
    )
    return True
