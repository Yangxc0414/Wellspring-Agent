"""Trace a draft's numbers back to on-disk artifacts.

A draft assembled from local study artifacts can quote values in two ways that verification has
to separate: full-precision decimals that must appear byte-identically in an artifact, and small
integer counts that appear everywhere by accident and can only be established by re-running the
command that produced them. String presence therefore *certifies decimals and refuses to certify
counts*, and it never calls an untraced number a mistake: it says the trace is missing.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# one token per number, sign and all decimals: splitting "-0.502872" into "-0.5028" was a real
# bug in the ad-hoc version of this check and it invented seventeen "unsourced" numbers
DECIMAL = re.compile(r"[-+]?\d+\.\d+")
INTEGER = re.compile(r"(?<![\d.])\d{1,6}(?![\d.])")

MAX_FILE_BYTES = 6_000_000
SKIP_DIRS = (".git", "__pycache__", "node_modules")


def _iter_corpus(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in (".json", ".csv", ".tsv", ".md", ".txt"):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def draft_numbers(text: str) -> Dict[str, List[str]]:
    """Split the draft's numbers into the two classes with different verification rules."""
    decimals = sorted(set(DECIMAL.findall(text or "")))
    counts = sorted({token for token in INTEGER.findall(text or "") if "." not in token})
    return {"decimals": decimals, "counts": counts}


def build_provenance(
    text: str,
    corpus_root: Path,
    max_files: int = 20000,
    exclude_paths: Optional[List[Path]] = None,
    draft_dir: str = "",
) -> Dict[str, Any]:
    corpus = Path(corpus_root)
    if not corpus.is_dir():
        raise ValueError("corpus root is not a directory: " + str(corpus_root))
    # the draft's own copy is not evidence for the draft: a value that only appears next to the
    # draft is reported separately instead of being counted as traced
    excluded = {str(Path(p).resolve()) for p in (exclude_paths or [])}
    classes = draft_numbers(text)
    sources: Dict[str, List[str]] = {}
    stored_values: Dict[str, float] = {}
    excluded_sources: Dict[str, str] = {}
    scanned = 0
    over_budget = 0
    unreadable = 0
    for path in _iter_corpus(corpus):
        if scanned >= max_files:
            over_budget += 1
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            unreadable += 1
            continue
        scanned += 1
        resolved = str(path.resolve())
        for token in DECIMAL.findall(body):
            key = token.lstrip("+")
            if resolved in excluded:
                if key not in excluded_sources:
                    excluded_sources[key] = resolved
                continue
            hits = sources.setdefault(key, [])
            if resolved not in hits:
                hits.append(resolved)
            if key not in stored_values:
                try:
                    stored_values[key] = float(key)
                except ValueError:
                    pass
    traced = [t for t in classes["decimals"] if sources.get(t.lstrip("+"))]
    untraced = [t for t in classes["decimals"] if not sources.get(t.lstrip("+"))]
    # second tier: the draft renders a different number of digits than the artifact stored.
    # the value agrees within the draft's last digit, so it is a source with a rendering
    # difference, not a byte-identical trace and not a missing trace either
    warnings: List[str] = []
    rounded = []
    only_draft = [
        t
        for t in classes["decimals"]
        if draft_dir
        and sources.get(t.lstrip("+"))
        and all(h.startswith(draft_dir) for h in sources[t.lstrip("+")])
    ]
    needs_check = untraced + [t for t in only_draft if t not in untraced]
    for token in needs_check:
        key = token.lstrip("+")
        try:
            value = float(key)
        except ValueError:
            continue
        places = len(key.split(".")[1])
        tolerance = 0.5 * 10 ** -places
        for stored, stored_value in stored_values.items():
            if abs(stored_value - value) >= tolerance:
                continue
            # a rounded match must come from outside the draft's own folder, otherwise the
            # draft would be citing its own copies again
            outside = [
                h for h in (sources.get(stored) or [])
                if not (draft_dir and h.startswith(draft_dir))
            ]
            if outside:
                rounded.append(
                    {
                        "draft_value": token,
                        "stored_value": stored,
                        "source": outside[0],
                        "draft_places": places,
                        "stored_places": len(stored.split(".")[1]),
                        "over_precision": places > len(stored.split(".")[1]),
                        "note": "the literal differs: the draft renders %d decimals, "
                        "the artifact stores %d" % (places, len(stored.split(".")[1])),
                    }
                )
                break
    rounded_values = {row["draft_value"] for row in rounded}
    untraced = [t for t in untraced if t not in rounded_values]
    over = [row for row in rounded if row["over_precision"]]
    if over:
        warnings.append(
            "%d value(s) are rendered with MORE decimals than the artifact stores, so the paper "
            "implies precision the evidence does not carry: %s"
            % (len(over), ", ".join(row["draft_value"] for row in over))
        )
    if rounded:
        warnings.append(
            "%d decimal(s) match an artifact only after rounding; the literal differs, so the "
            "paper's rendering precision must be checked by a human against the stored value"
            % len(rounded)
        )
    only_draft = [
        t
        for t in classes["decimals"]
        if draft_dir
        and sources.get(t.lstrip("+"))
        and all(h.startswith(draft_dir) for h in sources[t.lstrip("+")])
    ]
    if not draft_dir:
        warnings.append(
            "no draft directory was excluded, so a value can be traced back to the draft's own "
            "copies; call provenance_for_draft on a draft file to get a non-circular verdict"
        )
    if scanned == 0:
        warnings.append("no artifact file was scanned: the verdict describes nothing")
    if unreadable:
        warnings.append("%d file(s) could not be read" % unreadable)
    if over_budget:
        warnings.append(
            "%d file(s) were not read because --max-files=%d was reached: a value is reported "
            "untraceable only within the scanned budget" % (over_budget, max_files)
        )
    if untraced:
        warnings.append(
            "%d decimal value(s) have no byte-identical source in the corpus; this reports a "
            "missing trace, not a fabricated number" % len(untraced)
        )
    if only_draft:
        warnings.append(
            "%d decimal value(s) were found only under the draft's own directory, so their only "
            "\"source\" is the draft itself: %s" % (len(only_draft), ", ".join(only_draft[:8]))
        )
    return {
        "schema_version": "number-provenance-0.1",
        "corpus_root": str(corpus.resolve()),
        "files_scanned": scanned,
        "files_over_budget": over_budget,
        "files_unreadable": unreadable,
        "decimals_total": len(classes["decimals"]),
        "decimals_traced": len(traced),
        "decimals_untraced": untraced,
        "decimals_rounded_match": rounded,
        "decimals_over_precision": [row["draft_value"] for row in over],
        "decimals_only_in_draft_folder": only_draft,
        "counts_total": len(classes["counts"]),
        "counts_certified": 0,
        "boundary": (
            "decimals are traced by byte-identical presence in an artifact, which shows where a "
            "value was read from but not that the reading was correct; integer counts are never "
            "certified by presence because small integers match by accident, so counts require "
            "re-running the recorded command; a missing trace is reported as missing and is not "
            "called a fabrication"
        ),
        "warnings": warnings,
        "examples": [
            {"value": token, "source": (sources.get(token.lstrip("+")) or [""])[0]}
            for token in traced[:5]
        ],
    }


def provenance_for_draft(
    draft_path: Path, corpus_root: Path, max_files: int = 20000
) -> Dict[str, Any]:
    """Score a Markdown/JSON/TeX/plain draft; JSON drafts are flattened to their text values."""
    from .pack_audit import artifact_text

    path = Path(draft_path)
    if not path.is_file():
        raise ValueError("draft does not exist: " + str(draft_path))
    return build_provenance(
        artifact_text(path),
        corpus_root,
        max_files=max_files,
        exclude_paths=[path],
        draft_dir=str(path.resolve().parent) + os.sep,
    )
