"""Single source for default local state locations.

Defaults are absolute under the repository root so that running the CLI from a
different working directory cannot silently create a second policy/agent/memory
store. Explicit CLI/runtime paths still override these defaults.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DATA_ROOT = REPO_ROOT / "runtime_data"
WEB_DATA_ROOT = REPO_ROOT / "research_agent" / "web" / "data"

DEFAULT_JOBS_ROOT = RUNTIME_DATA_ROOT / "jobs"
DEFAULT_WAITPOINTS_ROOT = RUNTIME_DATA_ROOT / "waitpoints"
DEFAULT_WORKSPACE_MEMORY_PATH = RUNTIME_DATA_ROOT / "workspace_memory.json"
DEFAULT_WORKSPACE_ARCHIVE_ROOT = RUNTIME_DATA_ROOT / "workspace_archive"
DEFAULT_MODEL_STORE_PATH = RUNTIME_DATA_ROOT / "model_gateway.json"
DEFAULT_LITERATURE_MEMORY_PATH = RUNTIME_DATA_ROOT / "literature_memory.json"
DEFAULT_CUSTOM_AGENTS_PATH = RUNTIME_DATA_ROOT / "custom_agents.json"
DEFAULT_EVOLUTION_POLICY_PATH = RUNTIME_DATA_ROOT / "evolution_policy.json"
DEFAULT_EVOLUTION_OBSERVATIONS_PATH = RUNTIME_DATA_ROOT / "evolution_observations.json"
DEFAULT_EVOLUTION_ACTIVE_PATH = RUNTIME_DATA_ROOT / "evolution_active.json"
DEFAULT_SKILL_REGISTRY_PATH = RUNTIME_DATA_ROOT / "skills.json"
DEFAULT_SKILL_USAGE_PATH = RUNTIME_DATA_ROOT / "skill_usage.json"
DEFAULT_SKILL_EVAL_ROOT = RUNTIME_DATA_ROOT / "skill-evals"
DEFAULT_SKILL_VERSIONS_PATH = RUNTIME_DATA_ROOT / "skill_versions.json"
DEFAULT_SKILL_LIBRARY_ROOT = RUNTIME_DATA_ROOT / "skill-library"
DEFAULT_SIGNER_STORE_PATH = RUNTIME_DATA_ROOT / "signers.json"
DEFAULT_LOCAL_CORPUS_DIR = RUNTIME_DATA_ROOT / "corpus"
DEFAULT_HOST_MODEL_LEDGER_PATH = RUNTIME_DATA_ROOT / "host-model" / "turns.json"

DEFAULT_RSI_LEDGER_PATH = WEB_DATA_ROOT / "rsi-ledger.json"
DEFAULT_RSI_REAL_LEDGER_PATH = WEB_DATA_ROOT / "rsi-real-ledger.json"
DEFAULT_RSI_MINI_LEDGER_PATH = WEB_DATA_ROOT / "rsi-mini-ledger.json"
DEFAULT_RSI_COMPARE_LEDGER_PATH = WEB_DATA_ROOT / "rsi-compare-ledger.json"
DEFAULT_RSI_MODEL_LEDGER_PATH = WEB_DATA_ROOT / "rsi-model-ledger.json"
DEFAULT_RSI_S5_LEDGER_PATH = WEB_DATA_ROOT / "rsi-s5-ledger.json"
DEFAULT_RSI_S5BC_LEDGER_PATH = WEB_DATA_ROOT / "rsi-s5bc-ledger.json"
DEFAULT_RSI_CHEMLAB_LEDGER_PATH = WEB_DATA_ROOT / "rsi-chemlab-v2" / "ledger.json"
DEFAULT_REAL_CORPUS_PATH = REPO_ROOT / "modules" / "literature" / "fixtures" / "real_corpus.json"


_BUILD_INFO_CACHE = None


def _build_info() -> dict:
    """Hash of the package source **as this process loaded it**, computed once.

    Re-reading the files on every call made the value useless for its one job: a long-lived
    stdio server would report the bytes currently on disk while still executing the older
    modules it imported at startup, so the host saw a matching fingerprint and never reloaded.
    """
    global _BUILD_INFO_CACHE
    if _BUILD_INFO_CACHE is not None:
        return _BUILD_INFO_CACHE
    import hashlib
    import sys

    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and ".venv" not in path.parts
    )
    for path in files:
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    digest.update(("python=%d.%d" % sys.version_info[:2]).encode("utf-8"))
    _BUILD_INFO_CACHE = {
        "fingerprint": digest.hexdigest()[:16],
        "source_files": len(files),
    }
    return _BUILD_INFO_CACHE


def build_fingerprint() -> str:
    """Fingerprint of the code this process is running; fixed at import time."""
    return _build_info()["fingerprint"]


def build_info() -> dict:
    info = _build_info()
    return {
        "fingerprint": info["fingerprint"],
        "source_files": info["source_files"],
        "boundary": (
            "the fingerprint is fixed when this process imports the package; compare it against a "
            "fresh local process (`python -m research_agent handoff contract` prints the same "
            "value computed from the current checkout) - a difference means the long-lived server "
            "is running stale code and must be restarted, and a successful call is not evidence "
            "that the behaviour is current"
        ),
    }
