# Licensing Status and Decision Record

## Current status

**There is no root `LICENSE` file yet.** Original code and documentation in this repository are
therefore **not yet granted under an open-source license**; absent a license, default copyright
applies. Do not describe a public copy as "open source" until the owner selects and adds a license.

This file is a decision record and a release checklist, not legal advice.

## Decisions the owner must make

| Decision | Options | Consequence |
| --- | --- | --- |
| Code license | **Apache-2.0 (recommended)** | Explicit patent grant, trademark clause, and commercial-friendly terms; widely accepted by agent/tooling ecosystems. |
| | MIT | Shortest permissive license; no explicit patent grant. |
| | AGPL-3.0 | Copyleft for network use; conflicts with the stated goal of plug-and-play commercial adoption. |
| Documentation license | CC BY 4.0 or CC BY-SA 4.0 | Separate from code; the research/design documents are currently thesis material. |
| Brand and name | Reserved marks | A license to code does not grant rights to the project name or logo. |

**Recommendation:** Apache-2.0 for the runtime, specs, and frontend; CC BY 4.0 for documentation that
the owner wants to publish. Keep the thesis drafts, private research data, and third-party snapshots
out of the public repository.

## Release checklist

Before publishing the first public tag:

- [ ] Add the chosen `LICENSE` text at the repository root.
- [ ] Add `license` to `pyproject.toml` and `apps/web/package.json`.
- [ ] Update the README badge/statement from "pending" to the chosen license.
- [ ] Confirm every contributor has agreed to the chosen license (or the contribution is owned by
      the repository owner).
- [ ] Exclude or clarify all local-only trees listed in `THIRD_PARTY_NOTICES.md`:
      `oss/`, `research_agent/vendor/astradraw/`, `research/anthropic/`, `claude-code-main/`,
      `cortex-agent/`, `template_refs/`, `oss/writing-skills/`, `oss/full/`,
      `agent-reliability-survey/`, `manuscript/`, `research/frontier/`.
- [ ] Resolve the optional **PyMuPDF (AGPL-3.0/commercial)** path for the intended distribution model.
- [ ] Confirm that no external skill with a non-commercial or unknown license has been copied into
      runtime code, fixtures, or generated profiles.
- [ ] Add a `NOTICE` file if Apache-2.0 is chosen and any bundled material requires attribution.
- [ ] Confirm that no API keys, private paths, signed claims, or unpublished manuscripts are present
      in the public tree.
- [ ] Publish a source archive only after the checks above; a GitHub source ZIP includes everything
      tracked, not just the runtime directory.

## What cannot be relicensed

- Third-party research snapshots and clones: see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
- AstraDraw: no root upstream license; excluded from distribution.
- External skills: the caller supplies them; this repository does not redistribute them.
- Journal sample PDFs/DOCX and conference HTML captures: publisher copyright; local reference only.

## Until the decision is made

- The repository may be used locally for research and evaluation.
- Do not redistribute it as a whole, and do not describe it as licensed open source.
- The security and evidence-governance rules still apply to all local use.
