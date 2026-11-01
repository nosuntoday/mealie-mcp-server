# Compatibility evidence

**Latest tested Mealie: 3.30.0. Test date: 2026-11-01. Connector: 0.2.1.**

## What was tested

- 817 offline tests passed (including 34 Mealie 3.30 cases), exercising registered MCP tools, validation, request serialization and existing regressions.
- A real, empty Mealie 3.30.0 Docker instance with SQLite and synthetic data: authenticated non-admin MCP startup; 59 standard tools; free-form source metadata creation/update; recipe creation with a step duration; unrelated ingredient editing and full step replacement preserving that duration; zero clearing; weekly plan creation, title editing, moving both dates, clearing the end date and bulk creation.
- The connector used its actual FastMCP tool dispatch and real Mealie HTTP API. The Mealie server image was linux/arm64; the connector image was linux/amd64 under local emulation.
- A separate linux/amd64 container smoke check passed: non-root, read-only filesystem, initialize/session cleanup, annotations, 60 tools with optional AI import enabled, removed file-upload tools, host/origin rejection and separation of incoming authorization from the Mealie credential. Its backend was synthetic.
- Frozen Python package installation and wheel/source-distribution builds passed. Runtime dependency audit reported no known vulnerabilities on this date. Ruff correctness/import checks passed. The inherited production call to `datetime.utcnow()` still emits a deprecation warning (reported by two tests).
- A real, empty Mealie 3.29.0 instance additionally passed non-admin startup, free-form source create/update, ingredient/step roundtrip, daily meal-plan create/update and rejection of 3.30-only fields without new recipes/plans or changed steps. Offline tests also cover unknown versions and mixed daily/weekly batches; they are rejected before the first write. Mealie 3.28 remains covered by offline regressions only.

The eight upstream PRs and the intentional fork differences are documented in the [parity audit](pr-parity-2026-11-01.md).

## Limits

This verifies a fresh synthetic installation, not migration of an existing database, backup restoration, browser UI, AI-provider behavior or a new OAuth login in each AI client. It is not a statement that every Mealie endpoint or client/version is covered. Production updates need their own backup and migration checks. No production server was changed as part of this release.

ChatGPT, Claude, Codex and other MCP-capable agents can be configured according to their supported transports. This release's compatibility claim is about the MCP/API behavior above, not a blanket certification of those clients or authentication providers.

## Reproducing the real application check

Use disposable containers only. The helper intentionally accepts no target URL or credentials and only contacts the Docker hostname `mealie-compat-test`. It requires an empty Mealie 3.29.0 or 3.30.0 instance with its default setup, provisions a synthetic non-admin account, and creates synthetic recipes/plans. It does not clean up those records individually: remove the entire disposable container after inspection.

1. Build this release with BuildKit: `docker buildx build --platform linux/amd64 --load -t mealie-mcp-test:0.2.1 .`.
2. Create a new internal Docker network and an empty Mealie 3.30.0 container on it with alias `mealie-compat-test`, `DB_ENGINE=sqlite`, `ALLOW_SIGNUP=true`, and `/app/data` in a disposable tmpfs. Publish no ports and attach no real data volume. Wait for `/api/app/about` to be ready.
3. Run the helper from this checkout (replace `TEST_NETWORK` with the new network's name):

   ```sh
   docker run --rm -i --platform linux/amd64 --network TEST_NETWORK \
     --read-only --cap-drop ALL --security-opt no-new-privileges \
     --tmpfs /tmp:rw,size=64m -e PYTHONPATH=/app/src \
     --entrypoint python mealie-mcp-test:0.2.1 - < scripts/check_mealie_compat.py
   ```

4. Repeat on a fresh Mealie 3.29.0 container using the same network alias and add `--version v3.29.0` after the Python `-` argument. Never run both Mealie containers with that alias on the same network. The helper verifies rejection of unsupported fields and unchanged object counts.
5. Require the JSON report with all checks `passed` and exit code zero. Remove only your disposable test containers and network.

For each future compatibility release, repeat the checks, record actual results here and update the prominent README version/date together. Do not advance the badge merely because model tests pass or upstream released a new version.
