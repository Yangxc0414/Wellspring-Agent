# Third-Party Notices

This repository distinguishes three layers:

1. **Runtime code and specifications** authored for this project.
2. **Declared dependencies** installed by the user, not vendored here.
3. **Local reference material** used for research comparison. It is not a product dependency and
   must not be redistributed.

The project's own license is not yet chosen; see [`LICENSING.md`](LICENSING.md). Nothing in this file
grants a license to third-party material.

## 1. Vendored code

### AstraDraw

- Local path: `research_agent/vendor/astradraw/`
- Source: a local copy of `AstraDraw-main` supplied by the project owner.
- License status: **no root LICENSE file upstream**. The tree is therefore **not redistributable**
  and is excluded by `.gitignore` (`research_agent/vendor/astradraw/`, with only
  `research_agent/vendor/README.md` tracked).
- Use: the local adapter `research_agent/adapters/astradraw_renderer.py` calls its scene renderer to
  produce method/framework schematics. Upstream scripts are not modified.
- Asset risk: examples and brand/font assets may carry their own restrictions. See
  `astradraw/examples/*/SOURCES.md` and `astradraw/docs/media/brand/fonts/`. Generated SVGs that
  embed such assets inherit those restrictions.
- Release rule: do not include this directory, its assets, or generated outputs that embed
  restricted assets in a public or commercial distribution until the upstream rights are clarified.

## 2. Optional runtime dependencies

These are installed by the user and are not vendored. Consult the installed package metadata for the
binding license text.

| Dependency | Typical license | Use |
| --- | --- | --- |
| NumPy | BSD-3-Clause | experiment numerics |
| pandas | BSD-3-Clause | tabular data |
| scikit-learn | BSD-3-Clause | local experiment baselines |
| matplotlib | Matplotlib License (BSD-compatible) | result figures |
| FastAPI | MIT | local HTTP runtime |
| Uvicorn | BSD-3-Clause | local HTTP runtime |
| Pydantic | MIT | runtime schemas |
| python-docx | MIT | DOCX read/write (when installed) |
| openpyxl | MIT | XLSX input (when installed) |
| **PyMuPDF** | **AGPL-3.0 or commercial** | optional PDF full-text ingestion |

**PyMuPDF is the main copyleft risk.** It is imported lazily in
`research_agent/adapters/local_document_retriever.py`. If you distribute a proprietary or
AGPL-incompatible build, either comply with the AGPL, obtain a commercial license from Artifex, or
remove the optional PDF path. TXT/MD ingestion works without it.

## 3. Frontend dependencies

Declared in `apps/web/package.json`; installed from npm, not vendored in this repository.

| Package | License |
| --- | --- |
| React, React DOM | MIT |
| Zustand | MIT |
| Vite | MIT |
| `@vitejs/plugin-react` | MIT |
| TypeScript | Apache-2.0 |
| Playwright | Apache-2.0 |
| `@types/react`, `@types/react-dom` | MIT |

## 4. External skills invoked, not vendored

### `scientific-writing` (qinyan academic skills)

- License: MIT, per the upstream repository metadata recorded in `oss/writing-skills/CLONES.md`.
- Local status: **not vendored**. The caller supplies a skill root; the repository only invokes
  three whitelisted, read-only scripts:
  - `skills/scientific-writing/scripts/lint_manuscript.py`
  - `skills/scientific-writing/scripts/audit_claims.py`
  - `skills/scientific-writing/scripts/check_consistency.py`
- Boundary: execution uses the current interpreter, does not install dependencies, does not modify
  the draft or registry, and does not create evidence, claims, closures, or signatures.

### Awesome-Journal-Skills (JOS/CJC profiles)

- License: MIT.
- Local status: only a data projection is retained in
  `research_agent/fixtures/journal_skill_profiles.json` with `derived_from` provenance.
- Boundary: the external skill is not executed; the profiles are writing guidance and audit checks,
  not official journal templates.

### External skill survey directory

`D:\Users\20691\Downloads\Research Skill调研` (outside this repository) was used for comparison. It
is not a dependency and is not included in any release artifact. Individual repositories there have
their own licenses; several are **CC BY-NC 4.0** or unstated and must not be merged into a commercial
distribution.

## 5. Local research snapshots (not distributed)

The following trees are reference material. They are excluded by `.gitignore` and must be removed
from any release archive. Their licenses do **not** flow to this project, and their presence locally
does not imply endorsement or reuse.

| Path | Contents | License notes |
| --- | --- | --- |
| `oss/*-main/`, `oss/*-master/` | full/partial third-party research repositories | mixed: MIT, Apache-2.0, NOASSERTION, and a research-only CycleResearcher License |
| `oss/full/` | complete git clones / work-tree archives | mixed; one repository uses a **non-OSI research-only** license; do not redistribute |
| `oss/writing-skills/` | complete clones of writing-skill repositories | includes **CC BY-NC 4.0**; non-commercial, do not ship |
| `oss/*-curated/` | curated README/LICENSE/SKILL.md excerpts | MIT and **CC BY-NC 4.0**; reference only |
| `research/anthropic/` | Anthropic article HTML and code snapshots | article copyright Anthropic; code under Apache-2.0, MIT, or source-available terms; local only |
| `claude-code-main/` | Claude Code snapshot | see that directory's `LICENSE.md`; local only |
| `cortex-agent/` | external Cortex snapshot used for audit | local only; do not redistribute |
| `template_refs/` | journal sample PDFs/DOCX and conference HTML captures | publisher copyright; local reference only |
| `agent-reliability-survey/` | local research project with downloaded arXiv PDFs and notes | paper copyright; local only |
| `research/frontier/` | local frontier survey inputs and downloaded PDFs | paper copyright; local only |
| `manuscript/` | unpublished drafts, review notes, and journal-layout previews | author/publisher rights; local only |

`oss/README.md` and `oss/metadata.json` record commits and licenses for the research snapshots. They
are provenance records, not a redistribution license.

## 6. Generated artifacts

- Figures and manuscripts generated by this project may embed third-party fonts, templates, or
  datasets supplied by the user or by an external skill. The operator is responsible for checking
  those rights before publication or commercial use.
- Fixture data and deterministic test drafts are synthetic/test-only and carry no third-party rights
  beyond the repository itself.

## 7. Reporting an attribution problem

If you believe material in this repository is misattributed or should not be distributed, open a
private security/legal notice through the repository's private reporting channel described in
[`SECURITY.md`](SECURITY.md). Do not include confidential third-party material in a public issue.
