"""FlashRSI localqa launcher: native-execution local QA, registered at runtime.

Upstream FlashRSI routes every built-in QA benchmark through Docker
(integrations/supplied_context.py raises without a docker CLI). This machine
has no Docker daemon. Following the upstream extension guide (README.md
"How do I add a new benchmark?"), this launcher registers ``localqa``:
the same quickstart.jsonl rows, the same SearchQA prompt rendering and the
same text_em_f1 grading, but ``Task.env=None`` so MiniAgent executes natively
in-process. No upstream file is modified; registration lives only in this
process. A run produced this way is a local-extension experiment, NOT an
upstream SearchQA result, and its scores are not leaderboard-comparable.

Run with the FlashRSI venv interpreter, cwd = FlashRSI checkout root:

    .venv/Scripts/python.exe ../scripts/flashrsi_localqa_run.py run \
        --config ../runtime_data/flashrsi-localqa/quickstart.local.yaml --check-only
"""

from dataclasses import replace
from types import MappingProxyType

import flashrsi.runner as runner
from flashrsi.benchmarks.searchqa import SearchQA
from flashrsi.cli import main


class LocalQA(SearchQA):
    name = "localqa"
    description = (
        "Local extension: SearchQA quickstart rows with native (container-free) execution."
    )
    metadata = MappingProxyType(
        {
            "source": "local:FlashRSI-main/examples/data/quickstart.jsonl",
            "revision": "FlashRSI-main local archive (downloaded 2026-11-13)",
            "execution": "native: Task.env=None; upstream searchqa requires Docker supplied_context",
            "extension": "runtime registration by scripts/flashrsi_localqa_run.py; not an upstream benchmark",
        }
    )

    @staticmethod
    def _task_from_row(row, source_split):
        return replace(SearchQA._task_from_row(row, source_split), env=None)


runner._BENCHMARKS["localqa"] = LocalQA


if __name__ == "__main__":
    raise SystemExit(main())