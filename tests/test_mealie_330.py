"""Mealie 3.30 API compatibility, exercised at registered MCP boundaries."""

from copy import deepcopy

import pytest
from mcp.server.fastmcp.exceptions import ToolError

PLANS = "/api/households/mealplans"


@pytest.mark.parametrize(
    "tool,args",
    [("create_recipe", {"name": "Timed"}), ("update_recipe", {"slug": "test-recipe"})],
)
@pytest.mark.parametrize("seconds", [1, 600, 600.0, 2147483647])
async def test_step_duration_reaches_mealie(invoke, fetcher, tool, args, seconds):
    await invoke(
        tool, **args, instructions=[{"text": "Wait", "durationSeconds": seconds}]
    )
    step = fetcher.last("PUT", "/api/recipes/")["json"]["recipeInstructions"][0]
    assert step["durationSeconds"] == int(seconds)
    assert type(step["durationSeconds"]) is int


@pytest.mark.parametrize("seconds", [True, False, -1, 1.5, "600", 2147483648])
async def test_invalid_step_duration_never_writes(invoke, fetcher, seconds):
    with pytest.raises(ToolError):
        await invoke(
            "create_recipe",
            name="Invalid",
            instructions=[{"text": "Wait", "durationSeconds": seconds}],
        )
    assert fetcher.requests == []


@pytest.mark.parametrize("seconds", [0, None])
async def test_explicit_duration_clear_reaches_mealie(invoke, fetcher, seconds):
    await invoke(
        "update_recipe",
        slug="test-recipe",
        instructions=[{"text": "Wait", "durationSeconds": seconds}],
    )
    step = fetcher.last("PUT", "/api/recipes/")["json"]["recipeInstructions"][0]
    assert "durationSeconds" in step and step["durationSeconds"] is None


async def test_legacy_step_omits_duration(invoke, fetcher):
    await invoke("create_recipe", name="Legacy", instructions=[{"text": "Wait"}])
    step = fetcher.last("PUT", "/api/recipes/")["json"]["recipeInstructions"][0]
    assert "durationSeconds" not in step


async def test_unrelated_recipe_edit_preserves_step_duration_and_links(invoke, fetcher):
    steps = [
        {
            "text": "Wait",
            "durationSeconds": 600,
            "id": "step-1",
            "noteReferences": [{"referenceId": "note-1"}],
        }
    ]
    fetcher.recipe["recipeInstructions"] = deepcopy(steps)
    read = await invoke("get_recipe", slug="test-recipe")
    assert read["recipeInstructions"] == steps
    await invoke(
        "update_recipe", slug="test-recipe", ingredients=["Synthetic ingredient"]
    )
    assert fetcher.last("PUT", "/api/recipes/")["json"]["recipeInstructions"] == steps


@pytest.mark.parametrize("bulk", [False, True])
async def test_create_weekly_plan_across_month_boundary(invoke, fetcher, bulk):
    entry = {"date": "2026-11-29", "end_date": "2026-12-05", "title": "Weekly meal"}
    if bulk:
        await invoke("create_mealplan_bulk", entries=[entry])
    else:
        await invoke("create_mealplan", **entry)
    payload = fetcher.last("POST", PLANS)["json"]
    assert payload == {
        "date": "2026-11-29",
        "endDate": "2026-12-05",
        "title": "Weekly meal",
        "entryType": "breakfast",
    }


@pytest.mark.parametrize("end", ["2026-11-29", "2026-12-04", "2026-12-06", "bad"])
@pytest.mark.parametrize("bulk", [False, True])
async def test_invalid_week_never_writes(invoke, fetcher, end, bulk):
    entry = {"date": "2026-11-29", "end_date": end, "title": "Weekly meal"}
    with pytest.raises(ToolError):
        if bulk:
            await invoke(
                "create_mealplan_bulk",
                entries=[{"date": "2026-11-01", "title": "Valid"}, entry],
            )
        else:
            await invoke("create_mealplan", **entry)
    assert fetcher.requests == []


@pytest.fixture
def weekly(fetcher):
    entry = {
        "id": "meal-1",
        "date": "2026-11-29",
        "endDate": "2026-12-05",
        "entryType": "dinner",
        "title": "Weekly",
        "recipeId": None,
        "text": "Keep",
    }
    fetcher.responses[("GET", PLANS + "/meal-1")] = entry
    return entry


async def test_weekly_update_preserves_omitted_end_date(invoke, fetcher, weekly):
    await invoke("update_mealplan", entry_id="meal-1", title="New")
    assert fetcher.last("PUT", PLANS)["json"] == {**weekly, "title": "New"}


async def test_weekly_update_can_move_both_dates(invoke, fetcher, weekly):
    await invoke(
        "update_mealplan", entry_id="meal-1", date="2026-12-06", end_date="2026-12-12"
    )
    payload = fetcher.last("PUT", PLANS)["json"]
    assert payload["date"] == "2026-12-06" and payload["endDate"] == "2026-12-12"


async def test_weekly_update_can_clear_end_date(invoke, fetcher, weekly):
    await invoke("update_mealplan", entry_id="meal-1", clear_end_date=True)
    assert fetcher.last("PUT", PLANS)["json"]["endDate"] is None


async def test_weekly_date_only_change_rejects_invalid_merged_range(
    invoke, fetcher, weekly
):
    with pytest.raises(ToolError):
        await invoke("update_mealplan", entry_id="meal-1", date="2026-12-06")
    assert not any(r["method"] == "PUT" for r in fetcher.requests)


async def test_cannot_clear_and_replace_week_end(invoke, fetcher, weekly):
    with pytest.raises(ToolError):
        await invoke(
            "update_mealplan",
            entry_id="meal-1",
            end_date="2026-12-05",
            clear_end_date=True,
        )
    assert fetcher.requests == []


async def test_duration_tool_schema_allows_documented_zero_clear(server):
    mcp, _ = server
    tool = next(t for t in await mcp.list_tools() if t.name == "update_recipe")
    duration = tool.inputSchema["$defs"]["RecipeInstructionInput"]["properties"][
        "durationSeconds"
    ]
    integer = next(t for t in duration["anyOf"] if t.get("type") == "integer")
    assert integer["minimum"] == 0
