# Repository Guidance

## Project Structure

- This is a Python 3.12+ MCP server backed by the Mealie HTTP API.
- [`src/mealie/`](src/mealie/) contains API mixins and the shared HTTP client.
- [`src/tools/`](src/tools/) contains FastMCP-facing tool registrations.
- [`src/models/`](src/models/) contains Pydantic request and response models.
- [`src/server.py`](src/server.py) wires configuration, the client, prompts, and
  tools together.
- Use the SDK import `from mcp.server.fastmcp import FastMCP`; there is no
  standalone `fastmcp` dependency.

## Development Workflow

- Install all development dependencies with `uv sync --extra dev`.
- Before committing, run `uv run ruff check src tests` and `uv run pytest -q`.
- Keep [`uv.lock`](uv.lock) synchronized whenever
  [`pyproject.toml`](pyproject.toml) changes.
- Make focused commits. Do not stage generated files, local logs, `.env`,
  `.DS_Store`, or debug artifacts.
- The shared working tree may contain user changes. Inspect `git status` first
  and preserve unrelated work.
- Before pushing `main`, fetch the remote and inspect divergence. Rebase without
  overwriting newer remote functionality.

## Behavioral Constraints

- Never log API keys, request bodies, response bodies, recipe content, user data,
  or shopping-list content.
- Logging for stdio transport must go to stderr. Do not add an unconditional file
  logger or write protocol-adjacent output to stdout.
- Startup must fail on unsuccessful Mealie health checks; always call
  `raise_for_status()`.
- Close the HTTP client during shutdown.
- Keep MCP tool names and prompt references synchronized.
- Preserve Mealie field casing at the API boundary, such as `recipeId`,
  `entryType`, and `perPage`.

## Adding an API Capability

1. Add or extend the appropriate mixin in [`src/mealie/`](src/mealie/).
2. Ensure the mixin is inherited by `MealieFetcher` in
   [`src/mealie/__init__.py`](src/mealie/__init__.py).
3. Add the FastMCP wrapper in [`src/tools/`](src/tools/).
4. Register and export the wrapper through
   [`src/tools/__init__.py`](src/tools/__init__.py).
5. Add tests for request method, URL, parameters or payload, validation, success,
   and failure behavior.

See [source guidance](src/AGENTS.md) and [test guidance](tests/AGENTS.md) for
layer-specific conventions.

## Maintained fork publication

- Follow [CONTRIBUTING.md](CONTRIBUTING.md) as the required maintenance and release workflow. Keep source, documentation, tested compatibility and release evidence current together.

- Preserve the original MIT license and clear credit to Robert Diao's upstream project.
- Keep the top README compatibility version/date synchronized with docs/compatibility.md and actual evidence. Distinguish real application tests from mock/API-schema tests.
- Describe clients generically (ChatGPT, Claude, Codex and other MCP agents); do not imply untested client login flows passed.
- scripts/check_mealie_compat.py is an opt-in destructive check for an empty disposable Docker instance only, never a user's Mealie server. Unit tests remain offline.
- Publish no private infrastructure identifiers, credentials, deployment configuration or operational history.
