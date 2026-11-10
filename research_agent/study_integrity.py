"""Chain integrity of a study package: can it still be verified, and what does it disclose?

The framework's coverage numbers (how many packages carry a provenance sidecar, a
pre-registration, a bound opponent, an environment block) were reported over one mixed
denominator. Early packages recorded a content hash that included wall-clock seconds, so no
re-derivation reproduces it: those packages are not weaker results, they are unverifiable ones,
and quoting a coverage figure that counts them beside verifiable packages overstates the
inventory. This module separates the two questions.

Read-only: it re-runs nothing, signs nothing, and moves no gate. Whether a study is closeable is
decided by ``study closure``, which still blocks on ``code.unchanged`` regardless of what is here.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .search_lab import code_fingerprint, evidence_sha256_of, spec_sha256_of, study_sha256_of
from .study_claims import BASELINE_FILENAME
from .storage import read_json

INTEGRITY_STATES = ("derivable", "non_derivable", "incomplete")

SIDECAR_ARTIFACTS = (
    ("origin", "study-origin.json"),
    ("preregistration", "study-preregistration.json"),
    ("baseline", BASELINE_FILENAME),
    ("claim", "claim.json"),
)

ARTIFACT_ORDER = ("origin", "preregistration", "baseline", "claim", "environment", "code_fingerprint")

INTEGRITY_BOUNDARY = (
    "Chain integrity asks whether the hashes recorded inside a package re-derive from the bytes "
    "on disk under the current hashing rule. It re-runs nothing, signs nothing and moves no gate: "
    "code.unchanged, power and the human signature are decided by `study closure`."
)


def _load(path: Path) -> Dict[str, Any]:
    try:
        value = read_json(path)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def package_integrity(study_dir: Path, current_fingerprint: Optional[str] = None) -> Dict[str, Any]:
    """Do this package's recorded hashes re-derive, and which disclosures does it carry?

    Three JSON reads and a few existence checks; nothing is executed. ``current_fingerprint`` lets
    a batch caller supply the code fingerprint once instead of re-reading the sources per package.
    """
    root = Path(study_dir)
    spec = _load(root / "study-spec.json")
    study = _load(root / "study.json")
    evidence = _load(root / "study-evidence.json")
    missing = [
        name
        for name, value in (
            ("study-spec.json", spec),
            ("study.json", study),
            ("study-evidence.json", evidence),
        )
        if not value
    ]
    failures: List[str] = []
    if not missing:
        if str(study.get("study_sha256") or "") != study_sha256_of(study):
            failures.append("study.self_hash")
        if str(spec.get("study_sha256") or "") != str(study.get("study_sha256") or ""):
            failures.append("spec.binds_study")
        if str(evidence.get("study_sha256") or "") != str(study.get("study_sha256") or ""):
            failures.append("evidence.binds_study")
        if str(evidence.get("study_spec_sha256") or "") != spec_sha256_of(spec):
            failures.append("evidence.binds_spec")
        if str(evidence.get("evidence_sha256") or "") != evidence_sha256_of(evidence):
            failures.append("evidence.self_hash")
    recorded = str(spec.get("code_fingerprint") or "")
    stamp = code_fingerprint() if current_fingerprint is None else current_fingerprint
    artifacts = {name: (root / filename).is_file() for name, filename in SIDECAR_ARTIFACTS}
    artifacts["environment"] = bool(spec.get("environment"))
    artifacts["code_fingerprint"] = bool(recorded)
    return {
        "state": "incomplete" if missing else ("derivable" if not failures else "non_derivable"),
        "missing": missing,
        "failures": failures,
        # A second axis on purpose: "the code that ran this is gone" and "this package cannot be
        # verified" are different reader problems, and until now one code.unchanged blocker mixed
        # them together so a metadata edit and a hashing-rule change looked identical.
        "code_fingerprint": "absent" if not recorded else ("match" if recorded == stamp else "stale"),
        "artifacts": artifacts,
        "boundary": INTEGRITY_BOUNDARY,
    }


def integrity_layers(packages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Coverage of each disclosure artifact, split by chain-integrity layer.

    ``packages`` are entries that carry the dict from ``package_integrity`` under the key
    ``integrity``; anything else is counted as ``unknown`` rather than silently dropped. Every
    artifact gets two denominators: all collected packages, and only the packages whose recorded
    hashes still re-derive. Quoting the first while meaning the second is what this prevents.
    """
    reporting = [item for item in packages if isinstance(item.get("integrity"), dict)]
    layers = {state: 0 for state in INTEGRITY_STATES}
    layers["unknown"] = len(packages) - len(reporting)
    for item in reporting:
        state = str(item["integrity"].get("state") or "unknown")
        layers[state] = layers.get(state, 0) + 1
    derivable = [i for i in reporting if i["integrity"].get("state") == "derivable"]
    artifacts: Dict[str, Dict[str, Any]] = {}
    for name in ARTIFACT_ORDER:
        present = sum(1 for i in reporting if (i["integrity"].get("artifacts") or {}).get(name))
        verified = sum(1 for i in derivable if (i["integrity"].get("artifacts") or {}).get(name))
        artifacts[name] = {
            "present": present,
            "denominator": len(reporting),
            "ratio": round(present / len(reporting), 4) if reporting else None,
            "derivable_present": verified,
            "derivable_denominator": len(derivable),
            "derivable_ratio": round(verified / len(derivable), 4) if derivable else None,
        }
    return {
        "packages": len(packages),
        "with_integrity_data": len(reporting),
        "layers": layers,
        "artifacts": artifacts,
        "rule": (
            "a package counts as citable evidence only when its state is derivable; ratio covers "
            "every collected package while derivable_ratio covers only verifiable ones, so any "
            "statement about how much of the inventory is citable must use derivable_ratio"
        ),
        "boundary": INTEGRITY_BOUNDARY,
    }
