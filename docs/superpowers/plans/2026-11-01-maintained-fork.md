# Maintained Fork Implementation Plan

> Execute inline with superpowers:executing-plans and a final independent review.

**Goal:** Publish the maintained Mealie MCP fork with Mealie 3.30 field preservation.
**Architecture:** Existing Python/FastMCP mixins, input models and tool wrappers; unchanged transport layering.
**Tech Stack:** Python 3.12, Pydantic 2, MCP 1.x, pytest and uv.
**Spec:** ../specs/2026-11-01-maintained-fork-design.md

## Global constraints
Preserve tool names, original MIT attribution and existing contribution branches. No production changes or private configuration. No new runtime dependency. Tests use synthetic data.

## Review focus
Duration clearing versus omission; bool/fraction coercion; end-of-month weeks; date-only edits of weekly entries; frozen package/install reproducibility.

## Task 1: Compatibility
- [ ] Add failing tool-boundary tests in tests/test_mealie_330.py for step seconds in create/patch, unrelated-edit preservation, zero/null clearing, invalid input and legacy omission.
- [ ] Add single/bulk weekly plan tests, invalid date ranges, retained end dates, explicit clearing and rejected invalid merged updates.
- [ ] Implement minimal model/mixin/tool changes in src/models/recipe.py, src/models/mealplan.py, src/mealie/mealplan.py, src/tools/recipe_tools.py, src/tools/mealplan_tools.py.
- [ ] Run focused tests and complete pytest suite; check and fix lint findings without changing behavior.

## Task 2: Publication
- [ ] Prepare README, changelog, version 0.2.0, package URLs, generic Docker instructions and attribution. Retain LICENSE.
- [ ] Validate locked dependencies, wheel and container; audit runtime dependencies; review whole change independently.
- [ ] Scan staged files and all publishable history; commit and push only the approved fork branch/main and release tag.
- [ ] Verify remote commit and release; document deployment status separately in the private operations repository.
