# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.2.1 — 2026-11-01

- Document the maintained fork's release policy: current-source checks, regression tests, independent review, accurate compatibility evidence and synchronized documentation.

- Complete the audit against our eight upstream PR heads (#35–#42). Version 0.2.0 was based on an earlier hardening snapshot and missed the final changes from #38 and #39.
- Preserve optional ingredient `isFood` and `disableAmount` flags when supplied, without inventing defaults when absent.
- Accept Mealie-native recipe import sources (`www.` addresses, share text containing an HTTP(S) URL, and long URLs). Preserve long HTTP(S) image URLs without truncation.
- Treat `org_url` as free-form source metadata, including cookbook references.
- Retain all seven added upstream regression suites. Explicitly adapt only the two fork policies: non-admin credentials and absence of server-local upload tools. See [PR parity audit](docs/pr-parity-2026-11-01.md).

## 0.2.0 — 2026-11-01 (maintained fork)

- Preserve Mealie 3.30 `durationSeconds` in recipe-step creation and replacement, with explicit zero/null clearing and validation.
- Support weekly meal plans through `end_date`, including bulk creation, merged update validation and explicit clearing.
- Carry forward tested roundtrip fixes, repeated array filters, credential/path validation, bounded workers, serialized short writes and uncertain-import reporting.
- Refresh the MCP 1.x runtime and certificate bundle. Local server-file upload tools are removed; text/URL import and public image URLs remain supported.
- Require a non-admin Mealie credential at startup; remote access still requires an authenticated proxy.
- Publish this independently maintained fork with original MIT attribution. See `docs/compatibility.md` for test evidence; no production migration is implied.

## Upstream history (through 86ebf37)

### Previously unreleased

### Changed

- **Breaking:** Consolidated `create_recipe_full` into `create_recipe` and removed
  the old tool name. Switch callers of `create_recipe_full` to `create_recipe`
  without changing their arguments. Only `name` is required; ingredients,
  instructions, metadata, nutrition, and display settings are optional. Existing
  `create_recipe` calls remain supported.
- **Breaking:** Consolidated detailed/concise recipe reads into `get_recipe`
  (`concise=True` for a summary), and `patch_recipe` into `update_recipe`.
  Recipe updates accept optional ingredients, instructions, and metadata in one
  call while preserving omitted fields.
- **Breaking:** Removed `set_recipe_categories` and `set_recipe_tags`; use
  `update_recipe_categories_and_tags` with either or both ID lists.
- **Breaking:** Removed `get_category_by_slug`, `get_tag_by_slug`, and
  `get_tool_by_slug`. Their corresponding `get_*` tools accept exactly one ID
  or slug argument.
- **Breaking:** Removed `parse_ingredient`; use `parse_ingredients` with a
  one-element list and read its first result. All lines are validated before
  sending the request. The MCP inventory is reduced from 70 to 61 tools.

### Added

- `create_recipe` and `update_recipe` accept a `nutrition` argument covering
  Mealie's full key set (calories, macros, cholesterol, sodium, sugars, and the
  fat breakdown). Numbers are converted to the strings Mealie stores. Mealie
  replaces the whole nutrition object on write, so when `nutrition` is supplied,
  `update_recipe` clears nutrition keys not included in that object.
- `parse_ingredients` wraps Mealie's server-side ingredient parser, resolving
  free text such as `"1/4 cup chopped onion"`
  against the instance's food and unit vocabulary in one request instead of
  searching `get_foods` and `get_units` per ingredient. Results are flattened to
  `{input, confidence, quantity, unit, food, note}` and can be passed straight
  to `create_recipe`; `verbose=True` returns Mealie's untouched response.
  It accepts Mealie's `nlp`, `brute`, and `openai` parser backends.
- `create_recipe` and `update_recipe` accept a `settings` argument for
  Mealie's per-recipe display toggles (`public`, `showNutrition`, `showAssets`,
  `landscapeView`, `disableComments`, `disableAmount`, `locked`). Any subset may
  be passed; the tools read the recipe's current settings and send the merged
  object, so toggles left out keep their value.

### Fixed

- Recipes now expose `showAssets` and `showNutrition` through their settings.
  Previously, uploaded assets and nutrition could be stored but hidden in the
  Mealie UI when household defaults disabled those cards.
