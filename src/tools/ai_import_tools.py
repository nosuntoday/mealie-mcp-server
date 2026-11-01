from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mealie import MealieFetcher
from tools.errors import tool_error_boundary
from tools.recipe_tools import _created_recipe_stage


def register_ai_import_tools(mcp: FastMCP, mealie: MealieFetcher) -> None:
    """Register the explicitly enabled AI recipe importer."""

    @mcp.tool(annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ))
    def import_recipe_with_ai(
        content: str = "",
        url: str | None = None,
        translate_language: str | None = None,
        create_new_organizers: bool = False,
    ) -> dict[str, Any]:
        """Create one recipe from text, HTML/JSON, or web links using AI.
        Supports combined sources and translation.

        Prefer import_recipe_from_url for ordinary webpages, create_recipe for
        structured recipes.

        Provide content or a URL. Server file paths are not supported.

        Saves immediately and returns the recipe for review. AI charges may apply.
        """
        with tool_error_boundary("Error importing recipe with AI"):
            # A plain str annotation prevents FastMCP from pre-parsing recipe JSON.
            slug = mealie.import_recipe_with_ai(
                content=content or None, url=url,
                translate_language=translate_language,
                create_new_organizers=create_new_organizers,
            )
            with _created_recipe_stage(slug, "fetch"):
                return mealie.get_recipe(slug)
