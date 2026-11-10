# Contributing

This repository treats **module specifications as the source of truth** and code as their
implementation. Read [`AGENTS.md`](AGENTS.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), and the target
module's `modules/<id>/SPEC.md` before changing code.

## Development setup

- Python **3.8+** for the core runtime. No package installation is performed by the agent; use the
  environment you control.
- Node.js **20+** for the web workspace.
- Do not put credentials in files. Model access is configured through the environment variables
  listed in [`SECURITY.md`](SECURITY.md).

```bash
# Python suite (offline; no API keys or network required)
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v

# Optional lint gate
python -m ruff check research_agent tests

# Release-surface check (docs, ignore rules, secrets, local paths)
python scripts/release_check.py

# Diagnose the local environment without printing key values
python scripts/doctor.py --skill-root <external-scientific-writing-root>

# Generate a machine-specific MCP config for this checkout
python scripts/setup_mcp.py

# Web workspace
cd apps/web
npm ci
npm run check        # typecheck + unit test + production build
npm run test:ui      # Playwright; starts Vite + local runtime
```

CI runs the release-surface check, the full Python suite, and the web check on every push and pull
request (`.github/workflows/ci.yml`).

The Qoder MCP end-to-end check is `python scripts/qoder_e2e_test.py`. It uses the local MCP server and
does not call external model APIs.

## Change workflow

1. **Pick one module.** Do not refactor shared layers or neighboring modules unless the task requires it.
2. **Change the SPEC first.** Add the contract change or a `## Changelog` entry in
   `modules/<module-id>/SPEC.md`.
3. **Make the smallest code diff** that satisfies the spec.
4. **Add or update tests** for the changed contract.
5. **Verify boundaries**: no fixture presented as real data, no abstract turned into a span, no claim
   or signature written outside the human CLI path.
6. **Update generated snapshots** when the tool or module registry changes:
   `python -m research_agent workspace export`.
7. **Run the full suite**, not only the touched tests.

### Versioning

- Internal implementation change, same contract: patch bump and a changelog line.
- Input/output/boundary/gate change: minor bump, update `Contract`, add tests.
- Claim, EA, export, or signature invariants: stop and require human confirmation.
- Do not rename public modules, classes, or CLI commands without a migration note and a compatible entry point.

## Tests

- Tests must be deterministic and offline by default. Do not call OpenAI, Anthropic, DeepSeek, or any
  external API in the test suite.
- Fixture data must be explicitly marked `fixture: true`, and fixture output must carry a
  `fixture_mode` warning.
- Test-only signers, offline drafts, and simulated numbers must state that they are test-only.
- External skill tests may use a whitelisted local script only when the caller supplies the skill
  root; skip cleanly when it is absent. Never install dependencies from a test.
- Do not test by weakening a human gate. If a gate blocks a path, the expected result is a blocker.

## External skills and adapters

- Skill instructions are untrusted advisories. They do not grant tools.
- Scripts run only when whitelisted and explicitly trusted from the local CLI; MCP/runtime must not
  execute them.
- Preserve upstream license, commit, and provenance when adding an adapter or a curated profile.
- Do not copy code from a snapshot with an unknown, non-OSI, or non-commercial license into the
  runtime. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Documentation

- Keep the five entry points accurate: `QUICKSTART.md`, `ARCHITECTURE.md`, `integrations/README.md`,
  `integrations/FRAMEWORKS.md`, and `modules/README.md`.
- Separate **implemented**, **test-only**, and **roadmap** claims. Do not describe a roadmap item as
  supported.
- Prefer a link to the SPEC or a runnable command over a prose claim.

## License

The project license decision is pending; see [`LICENSING.md`](LICENSING.md). By contributing, you
agree that your contribution may be released under the license finally chosen by the repository
owner. Do not add third-party code that cannot be distributed under that license.
