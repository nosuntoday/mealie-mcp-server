"""3.30-only fields must never silently succeed on older Mealie versions."""

import json
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from mealie import MealieFetcher
from server import ServerConfig, create_server


@contextmanager
def backend_for(version):
    requests = []

    def respond(request):
        if request.url.path == "/api/app/about":
            return httpx.Response(200, json={"version": version})
        if request.url.path == "/api/users/self":
            return httpx.Response(200, json={"admin": False})
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"slug": "test", "name": "Test"})
        if request.url.path == "/api/recipes" and request.method == "POST":
            return httpx.Response(200, json="test")
        return httpx.Response(200, json=json.loads(request.content))

    client = httpx.Client(
        base_url="http://mealie.invalid", transport=httpx.MockTransport(respond)
    )
    with patch("mealie.client.httpx.Client", return_value=client):
        backend = MealieFetcher("http://mealie.invalid", "synthetic")
    mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
    mcp.client_provider._client = backend
    try:
        yield mcp, requests
    finally:
        backend.close()


CASES = [
    (
        "create_recipe",
        {"name": "Test", "instructions": [{"text": "Wait", "durationSeconds": 600}]},
    ),
    (
        "update_recipe",
        {"slug": "test", "instructions": [{"text": "Wait", "durationSeconds": 0}]},
    ),
    (
        "create_mealplan",
        {"date": "2099-11-29", "end_date": "2099-12-05", "title": "Week"},
    ),
    (
        "create_mealplan_bulk",
        {
            "entries": [
                {"date": "2099-11-28", "title": "Day"},
                {"date": "2099-11-29", "end_date": "2099-12-05", "title": "Week"},
            ]
        },
    ),
    ("update_mealplan", {"entry_id": "1", "end_date": "2099-12-05"}),
    ("update_mealplan", {"entry_id": "1", "clear_end_date": True}),
]


@pytest.mark.parametrize("version", ["v3.29.0", None, "unknown"])
@pytest.mark.parametrize("tool,args", CASES)
async def test_330_fields_fail_before_any_write_on_old_or_unknown_backend(
    version, tool, args
):
    with backend_for(version) as (mcp, requests):
        with pytest.raises(ToolError, match="requires Mealie 3.30"):
            await mcp.call_tool(tool, args)
        assert not any(r.method in ("POST", "PUT", "PATCH", "DELETE") for r in requests)


@pytest.mark.parametrize("version", ["v3.30.0", "3.30.1"])
async def test_known_330_backend_accepts_step_durations(version):
    with backend_for(version) as (mcp, requests):
        await mcp.call_tool(*CASES[0])
        written = json.loads(next(r.content for r in requests if r.method == "PUT"))
        assert written["recipeInstructions"][0]["durationSeconds"] == 600


async def test_329_normal_recipes_and_daily_mealplans_still_work():
    with backend_for("v3.29.0") as (mcp, requests):
        await mcp.call_tool("create_recipe", {"name": "Test", "instructions": ["Mix"]})
        await mcp.call_tool("create_mealplan", {"date": "2099-11-29", "title": "Day"})
        written = [json.loads(r.content) for r in requests if r.method == "POST"]
        assert len(written) == 2
        assert "endDate" not in written[-1]


@pytest.mark.parametrize(
    "source",
    [
        "javascript:alert(1)",
        " \tJaVaScRiPt:alert(1)",
        "java\nscript:alert(1)",
        "data:text/plain,bad",
        "\x01vbscript:bad",
    ],
)
@pytest.mark.parametrize(
    "tool,args",
    [("create_recipe", {"name": "Test"}), ("update_recipe", {"slug": "test"})],
)
async def test_active_source_schemes_rejected_before_writes(source, tool, args):
    with backend_for("v3.29.0") as (mcp, requests):
        with pytest.raises(ToolError, match="source metadata"):
            await mcp.call_tool(tool, {**args, "org_url": source})
        assert requests == []
