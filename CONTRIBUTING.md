# Maintenance and release policy

This public fork is maintained at [nosuntoday/mealie-mcp-server](https://github.com/nosuntoday/mealie-mcp-server). “Upstream” means the original [rldiao/mealie-mcp-server](https://github.com/rldiao/mealie-mcp-server); the fork is the source for its own releases. Preserve upstream attribution and the original MIT license.

## Before changing behavior

- Fetch the fork remote, inspect the working tree and divergence, and preserve unrelated work.
- Check relevant changes in the original project, current Mealie release notes/API and the MCP SDK. Record which versions and commits informed the change; an old patch or a green test run alone does not establish current compatibility.
- Reproduce a bug with a regression test. Compare complete PR head changes when incorporating contributions, including their tests and later amendments. Document deliberate differences.

## Before publishing a release

- Run the full offline suite and Ruff using the locked environment (`uv sync --locked --extra dev`, `uv run pytest -q`, `uv run ruff check src tests scripts`). Do not publish with unexplained failures.
- Build the wheel, source distribution and Docker image from the exact reviewed, tagged commit in a clean build context. Verify packaged source/metadata against that commit, record checksums, and upload only these freshly built artifacts. Audit locked runtime dependencies for known vulnerabilities and resolve or explicitly document relevant findings before release. Check staged files and the history to be published for secrets and private data.
- For compatibility-affecting changes, test the built connector against a disposable real instance of the claimed Mealie version, using synthetic data. Record the actual scope; mock tests are not proof of a real application or AI-client login flow.
- Obtain an independent review of behavior changes and address substantive findings before publication. Record the review outcome and remaining limitations.
- Update code, tool descriptions, usage examples and changelog together. Update the README's prominent last-tested Mealie version/date and `docs/compatibility.md` only from actual evidence. Link exact source/PR commits where relevant.
- Publish a versioned release from the reviewed commit, verify its tag and release assets, and verify the remote branch after pushing. Never silently replace an existing release tag to hide a defect: document the defect and publish a correction.

## Ongoing care

At each update/release review, recheck Mealie, the original project and runtime dependencies. Keep known issues, incompatibilities and test limits visible rather than claiming that a version is universally error-free or continuously verified. Reported defects receive a reproducible test and a documented correction. Avoid adding automatic installation or changing a production instance as part of source maintenance; deployments require their own approval and migration checks.

The current compatibility record is [docs/compatibility.md](docs/compatibility.md). The initial contribution audit is [docs/pr-parity-2026-11-01.md](docs/pr-parity-2026-11-01.md).
