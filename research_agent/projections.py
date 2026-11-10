"""Projection contract: what every read-only projection must say about itself.

The system's main product is projections - stories, briefs, closure reports, READMEs, coverage
reports, face matrices, web snapshots. Each one decided for itself whether to carry a timestamp,
the fingerprint of the code that produced it, a fixture/simulation marker, or the base of its own
ratio. Measured with this scan: 171 schema ids are declared by 229 dict literals across 157
modules, and only 11 of those projections carry ``generated_at`` in the literal, 2 carry a
canonical ``source_fingerprint``, 3 carry ``read_only``. Every stale-reading defect this project has
hunted (#76 old build, the 0/14-versus-8/14 coverage readings, the undated web snapshot, the
MANIFEST with no timestamp, the story that dropped its simulation flags, 190 packages all stale) is
one instance of that absence.

So the slots are named once, and an inventory reports which projection fills which slot. The
inventory is deliberately a *report*, not a gate: 171 projections cannot be fixed in one step, and a
guard that fails on all of them would be turned off. What is enforced is the ratchet - the
projections on the signing and audit chain are asserted complete in
tests/test_projection_contract.py, and a new projection that omits a slot shows up with the slot
named ``absent`` instead of disappearing silently.

Four states, not two, because both a naive scan and a naive key check would lie:

``in_literal``      the dict that declares schema_version also declares the slot.
``aliased``         the same information is present under another key (``build`` for a fingerprint,
                    ``comparability`` for a base). An alias is a claim of equivalence that a human
                    has to confirm, which is exactly why it is not folded into ``in_literal``:
                    host-contract carries a build fingerprint and reporting it as "no fingerprint"
                    would have sent someone to duplicate the field.
``elsewhere``       the slot name occurs as a string in the module but not in this dict, so it may
                    be attached later or by a helper.
``absent``          the slot name occurs nowhere in the module.
"""

import ast
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import REPO_ROOT, build_info

SCHEMA_VERSION_SLOT = "schema_version"
# every schema id in this repo is name-<major>.<minor>; anything else is a dict that happens to use
# the same key. The first run of this scan counted its own SLOT_MEANING documentation table as a
# projection and reported it complete, so the shape filter is not decoration.
_SCHEMA_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*-[0-9]+\.[0-9]+$")

CONTRACT_SLOTS = (
    "schema_version",
    "generated_at",
    "source_fingerprint",
    "read_only",
    "base",
    "provenance",
    "boundary",
)
SLOT_MEANING = {
    "schema_version": "which shape this is, so a reader can tell a new field from a changed one",
    "generated_at": "when it was produced: a projection without a date reads as the current state",
    "source_fingerprint": "the code that produced it, so staleness is a comparison and not a guess",
    "read_only": "whether it can change anything; every projection here must say it cannot",
    "base": "the denominator or reference of any ratio it reports - a ratio without a base is not comparable",
    "provenance": "fixture / simulation / language flags: whether this describes a real run",
    "boundary": "what this artifact is not (not a claim, not a signature, not evidence)",
}
SLOT_ALIASES = {
    "schema_version": (),
    "generated_at": ("created_at",),
    "source_fingerprint": ("build", "served_build", "code_fingerprint_recorded", "code_fingerprint"),
    "read_only": ("advisory",),
    "base": ("comparability", "denominator", "pack_scope"),
    "provenance": ("fixture_mode", "simulation", "language", "license"),
    "boundary": (),
}

IN_LITERAL = "in_literal"
ALIASED = "aliased"
ELSEWHERE = "elsewhere_in_file"
ABSENT = "absent"
_RANK = {IN_LITERAL: 3, ALIASED: 2, ELSEWHERE: 1, ABSENT: 0}
INVENTORY_SCHEMA = "projection-inventory-0.1"
# third-party drawing workflow copied verbatim into the repo: never scanned, never edited
EXCLUDED_PARTS = ("vendor", "__pycache__", "web")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _module_strings(tree: ast.AST) -> set:
    return {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _module_constants(tree: ast.AST) -> Dict[str, str]:
    """Module-level ``NAME = "literal"`` assignments, so an indirect schema id can still be read."""
    constants: Dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        text = node.value.value if isinstance(node.value, ast.Constant) else None
        if not isinstance(text, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = text
    return constants


def _literal_schema_ids(tree: ast.AST, constants: Dict[str, str]) -> List[Dict[str, Any]]:
    """Every dict literal that declares a schema id, with the keys it declares beside it."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = set()
        schema = None
        for key, value in zip(node.keys, node.values):
            name = key.value if isinstance(key, ast.Constant) else None
            if not isinstance(name, str):
                continue
            keys.add(name)
            if name != SCHEMA_VERSION_SLOT:
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                schema = value.value
            elif isinstance(value, ast.Name):
                schema = constants.get(value.id)
        if schema and _SCHEMA_ID.match(schema):
            found.append({"schema": schema, "keys": keys, "line": node.lineno})
    return found


def _slot_state(slot: str, keys: set, module_strings: set) -> str:
    if slot in keys:
        return IN_LITERAL
    if any(alias in keys for alias in SLOT_ALIASES[slot]):
        return ALIASED
    if slot in module_strings:
        return ELSEWHERE
    return ABSENT


def projection_inventory(root: Optional[Path] = None) -> Dict[str, Any]:
    """Report which projection fills which contract slot. Read-only; changes nothing."""
    base = Path(root or REPO_ROOT)
    package = base / "research_agent"
    occurrences: List[Dict[str, Any]] = []
    dynamic = 0
    scanned = 0
    for path in sorted(package.rglob("*.py")):
        if set(path.parts) & set(EXCLUDED_PARTS):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        scanned += 1
        strings = _module_strings(tree)
        constants = _module_constants(tree)
        for item in _literal_schema_ids(tree, constants):
            slots = {slot: _slot_state(slot, item["keys"], strings) for slot in CONTRACT_SLOTS}
            occurrences.append(
                {
                    "schema": item["schema"],
                    "module": path.relative_to(base).as_posix(),
                    "line": item["line"],
                    "slots": slots,
                    "absent_slots": sorted(s for s, state in slots.items() if state == ABSENT),
                }
            )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                name = key.value if isinstance(key, ast.Constant) else None
                if name == SCHEMA_VERSION_SLOT and not isinstance(value, ast.Constant):
                    dynamic += 1

    rollup: Dict[str, Dict[str, Any]] = {}
    for row in occurrences:
        entry = rollup.setdefault(
            row["schema"],
            {
                "schema": row["schema"],
                "modules": [],
                # every slot starts absent. The first version of this rollup only upgraded slots it
                # had already seen, so a slot no occurrence declared was dropped from the row and
                # absent_slots read empty - a report that flatters is worse than no report.
                "slots": {slot: ABSENT for slot in CONTRACT_SLOTS},
            },
        )
        if row["module"] not in entry["modules"]:
            entry["modules"].append(row["module"])
        for slot, state in row["slots"].items():
            if _RANK[state] > _RANK[entry["slots"][slot]]:
                entry["slots"][slot] = state
    for entry in rollup.values():
        entry["absent_slots"] = sorted(
            slot for slot, state in entry["slots"].items() if state == ABSENT
        )
        entry["aliased_slots"] = sorted(
            "%s (as %s)" % (slot, ", ".join(SLOT_ALIASES[slot]))
            for slot, state in entry["slots"].items() if state == ALIASED
        )
        entry["complete"] = all(
            entry["slots"][slot] == IN_LITERAL for slot in CONTRACT_SLOTS
        )
        entry["satisfied"] = not entry["absent_slots"]

    slot_coverage = {}
    for slot in CONTRACT_SLOTS:
        states = [entry["slots"][slot] for entry in rollup.values()]
        slot_coverage[slot] = {
            "meaning": SLOT_MEANING[slot],
            "aliases": list(SLOT_ALIASES[slot]),
            IN_LITERAL: states.count(IN_LITERAL),
            ALIASED: states.count(ALIASED),
            ELSEWHERE: states.count(ELSEWHERE),
            ABSENT: states.count(ABSENT),
        }
    schemas = sorted(rollup)
    complete = sorted(name for name in schemas if rollup[name]["complete"])
    satisfied = sorted(name for name in schemas if rollup[name]["satisfied"])
    return {
        "schema_version": INVENTORY_SCHEMA,
        "generated_at": _now(),
        "source_fingerprint": str(build_info().get("fingerprint") or ""),
        "read_only": True,
        "base": "%d modules scanned; %d schema ids resolved from %d dict literals; %d further "
        "literals declare schema_version through something this scan cannot resolve (a call or a "
        "formatted string) and are counted as dynamic rather than silently dropped. The "
        "denominator is dict literals, not every schema-id string in the repo: a grep over string "
        "literals finds a slightly different set because its pattern differs"
        % (scanned, len(schemas), len(occurrences), dynamic),
        "provenance": {
            "scan": "static AST over research_agent/**/*.py, excluding %s"
            % ", ".join(EXCLUDED_PARTS),
            "slot_states": [IN_LITERAL, ALIASED, ELSEWHERE, ABSENT],
            "dynamic_schema_versions": dynamic,
        },
        "contract": {"slots": list(CONTRACT_SLOTS), "slot_meaning": dict(SLOT_MEANING),
                     "slot_aliases": {k: list(v) for k, v in SLOT_ALIASES.items()}},
        "modules_scanned": scanned,
        "schemas": len(schemas),
        "occurrences": len(occurrences),
        "dynamic_schema_versions": dynamic,
        "slot_coverage": slot_coverage,
        "complete": complete,
        "complete_count": len(complete),
        "satisfied": satisfied,
        "satisfied_count": len(satisfied),
        "rows": [rollup[name] for name in schemas],
        "occurrence_rows": occurrences,
        "boundary": (
            "a report, not a gate: it says which projection fills which slot and changes nothing. "
            "aliased means the information is present under another key and that equivalence is a "
            "human claim, not a verified one, so it is never folded into in_literal; elsewhere means "
            "a static scan cannot tell; a schema id built at runtime is counted as dynamic and "
            "cannot be classified at all. Compliance is enforced only where it is asserted - the "
            "signing and audit chain projections named in tests/test_projection_contract.py - so the "
            "ratchet tightens without failing on 171 projections at once"
        ),
    }


def contract_slots() -> Dict[str, Any]:
    """The contract itself, for callers that must state it (doctor, preflight, docs)."""
    return {
        "schema_version": "projection-contract-0.1",
        "generated_at": _now(),
        "source_fingerprint": str(build_info().get("fingerprint") or ""),
        "read_only": True,
        "base": "%d slots" % len(CONTRACT_SLOTS),
        "provenance": {"slots": list(CONTRACT_SLOTS)},
        "slots": list(CONTRACT_SLOTS),
        "slot_meaning": dict(SLOT_MEANING),
        "slot_aliases": {key: list(value) for key, value in SLOT_ALIASES.items()},
        "boundary": (
            "the slots a read-only projection should carry about itself; adopting them is a "
            "disclosure change and must never alter a judgement, a gate or a number"
        ),
    }


__all__ = [
    "ABSENT",
    "ALIASED",
    "CONTRACT_SLOTS",
    "ELSEWHERE",
    "IN_LITERAL",
    "INVENTORY_SCHEMA",
    "SLOT_ALIASES",
    "contract_slots",
    "projection_inventory",
]
