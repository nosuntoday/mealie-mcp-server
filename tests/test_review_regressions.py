"""Review boundaries tested through real tools and httpx URL construction."""

import asyncio
import json
import threading
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from mealie import MealieFetcher
from server import ServerConfig, create_server

ATTACKS = [
    ".",
    "..",
    "../users/self",
    "a/b",
    "a?x=y",
    "a#x",
    "%2F",
    "a\\b",
    "",
    " ",
    "ok\n",
]


async def test_migrated_recipe_times_survive_concise_read(invoke, fetcher):
    fetcher.recipe.update(
        totalTime=None,
        prepTime=None,
        performTime=None,
        totalTimeSeconds=2700,
        prepTimeSeconds=600,
        performTimeSeconds=2100,
    )
    result = await invoke("get_recipe", slug="test-recipe", concise=True)
    assert result["totalTimeSeconds"] == 2700
    assert result["prepTimeSeconds"] == 600
    assert result["performTimeSeconds"] == 2100


@pytest.mark.parametrize(
    "argument,field",
    [
        ("total_time", "totalTime"),
        ("prep_time", "prepTime"),
        ("perform_time", "performTime"),
    ],
)
async def test_time_text_replaces_old_structured_duration(
    invoke, fetcher, argument, field
):
    fetcher.recipe.update(
        totalTimeSeconds=1800, prepTimeSeconds=600, performTimeSeconds=1200
    )
    await invoke("update_recipe", slug="test-recipe", **{argument: "45 min"})
    body = fetcher.last("PATCH", "/api/recipes/")["json"]
    assert body[field] == "45 min"
    assert field + "Seconds" in body and body[field + "Seconds"] is None
    assert len(body) == 2


async def test_ingredient_put_retains_structured_durations(invoke, fetcher):
    fetcher.recipe.update(
        totalTimeSeconds=1800, prepTimeSeconds=600, performTimeSeconds=1200
    )
    await invoke("update_recipe", slug="test-recipe", ingredients=["synthetic"])
    body = fetcher.last("PUT", "/api/recipes/")["json"]
    assert body["totalTimeSeconds"] == 1800
    assert body["prepTimeSeconds"] == 600
    assert body["performTimeSeconds"] == 1200


@contextmanager
def real_backend(handler=None):
    """Keep all product layers; replace only the external HTTP transport."""
    requests = []

    def respond(request):
        if request.url.path == "/api/app/about":
            return httpx.Response(200, json={"version": "v3.28.0"})
        if request.url.path == "/api/users/self":
            return httpx.Response(200, json={"admin": False})
        requests.append(request)
        return handler(request) if handler else httpx.Response(200, json={})

    client = httpx.Client(
        base_url="http://mealie.invalid", transport=httpx.MockTransport(respond)
    )
    with patch("mealie.client.httpx.Client", return_value=client):
        backend = MealieFetcher("http://mealie.invalid", "synthetic-test-only")
    try:
        yield backend, requests
    finally:
        backend.close()


def sample(schema, root):
    if "$ref" in schema:
        return sample(root["$defs"][schema["$ref"].split("/")[-1]], root)
    if "anyOf" in schema:
        return sample(next(s for s in schema["anyOf"] if s.get("type") != "null"), root)
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "array":
        return [sample(schema["items"], root)]
    if kind == "object":
        return {
            k: sample(schema["properties"][k], root) for k in schema.get("required", [])
        }
    if kind in ("integer", "number"):
        return 1
    if kind == "boolean":
        return False
    return "valid-id"


async def test_every_discoverable_path_argument_rejects_before_transport():
    # These IDs are request-body references, not API path segments.
    body_only = {
        ("create_food", "label_id"),
        ("update_food", "label_id"),
        ("create_shopping_list_item", "shopping_list_id"),
        ("create_shopping_list_item", "unit_id"),
        ("create_shopping_list_item", "food_id"),
        ("create_shopping_list_item", "label_id"),
        ("create_mealplan", "recipe_id"),
        ("update_mealplan", "recipe_id"),
    }
    with real_backend() as (backend, requests):
        mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
        mcp.client_provider._client = backend
        extras = {
            "update_recipe": {"name": "control"},
            "update_recipe_categories_and_tags": {"tag_ids": []},
            "set_recipe_image_from_url": {"image_url": "https://example.org/image.jpg"},
            "update_category": {"name": "control"},
            "update_tag": {"name": "control"},
            "update_food": {"name": "control"},
            "update_unit": {"name": "control"},
            "update_tool": {"name": "control"},
            "update_shopping_list_item": {"note": "control"},
            "update_mealplan": {"title": "control"},
        }
        checked = set()
        for tool in await mcp.list_tools():
            schema = tool.inputSchema
            for key in schema["properties"]:
                if not (key == "slug" or key.endswith(("_id", "_slug", "_ids"))):
                    continue
                if (tool.name, key) in body_only:
                    continue
                checked.add((tool.name, key))
                base = dict(sample(schema, schema), **extras.get(tool.name, {}))
                many = key.endswith("_ids")
                requests.clear()
                try:
                    await mcp.call_tool(
                        tool.name,
                        dict(base, **{key: ["control-id"] if many else "control-id"}),
                    )
                except ToolError:
                    pass  # Only later fake response validation may fail.
                assert any("control-id" in str(r.url) for r in requests), (
                    tool.name,
                    key,
                )
                for attack in ATTACKS:
                    args = dict(base)
                    args[key] = ["control-id", attack] if many else attack
                    requests.clear()
                    with pytest.raises(ToolError):
                        await mcp.call_tool(tool.name, args)
                    assert requests == [], (tool.name, key, attack)
        assert (
            len(checked) >= 30
        )  # Catalogue shrinkage must not silently remove coverage.


async def test_bulk_update_validates_all_ids_before_fetching_first():
    with real_backend() as (backend, requests):
        mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
        mcp.client_provider._client = backend
        for attack in ATTACKS:
            requests.clear()
            with pytest.raises(ToolError):
                await mcp.call_tool(
                    "update_shopping_list_items_bulk",
                    {
                        "items": [
                            {"id": "valid-id", "note": "first"},
                            {"id": attack, "note": "second"},
                        ]
                    },
                )
            assert requests == []


@pytest.mark.parametrize(
    "url",
    [
        "/api/recipes/../users/self",
        "/api/recipes/a?x",
        "/api/recipes/a#x",
        "/api/recipes/%2f",
    ],
)
def test_central_guard_rejects_invalid_complete_paths(url):
    with real_backend() as (backend, requests):
        with pytest.raises(ValueError):
            backend._handle_request("GET", url)
        assert requests == []


def test_unicode_uuid_and_integer_segments_remain_usable():
    with real_backend() as (backend, requests):
        backend.get_recipe("käse-überbacken")
        backend.get_food("8d8dbe47-811e-4f27-9ed3-cfa87b6962ba")
        backend.delete_mealplan(123)
        assert [r.url.path for r in requests] == [
            "/api/recipes/käse-überbacken",
            "/api/foods/8d8dbe47-811e-4f27-9ed3-cfa87b6962ba",
            "/api/households/mealplans/123",
        ]


@pytest.mark.parametrize("tags", [["quick", "vegan"], []])
def test_filter_arrays_use_repeated_query_parameters(tags):
    with real_backend() as (backend, requests):
        backend.get_recipes(tags=tags)
        assert requests[-1].url.params.get_list("tags") == tags


async def test_sync_tools_overlap_without_blocking_loop_and_limit_workers():
    # A blocking implementation cannot start two workers or run the ticker.
    import anyio

    from server import _MealieServer

    mcp = _MealieServer(None)
    release = threading.Event()
    four_started = threading.Event()
    lock = threading.Lock()
    active = peak = 0

    @mcp.tool()
    def slow(value: int) -> int:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 4:
                four_started.set()
        assert release.wait(3)
        with lock:
            active -= 1
        return value

    progress = []

    async def ticker():
        await anyio.sleep(0.02)
        progress.append(not release.is_set())

    # Timer bounds failure even if the event loop is blocked by the broken code.
    timer = threading.Timer(0.4, release.set)
    timer.start()
    try:
        await asyncio.gather(
            *(mcp.call_tool("slow", {"value": n}) for n in range(6)), ticker()
        )
    finally:
        release.set()
        timer.join()
    assert peak == 4
    assert four_started.is_set()
    assert progress == [True]


async def test_wrapper_preserves_tool_catalogue_and_returns_original_function(fetcher):
    from mcp.server.fastmcp import FastMCP

    from server import _MealieServer
    from tools import register_all_tools

    plain, wrapped = FastMCP("plain"), _MealieServer(None)
    for mcp in (plain, wrapped):
        register_all_tools(mcp, fetcher, enable_ai_import=True)
    assert [t.model_dump_json() for t in await plain.list_tools()] == [
        t.model_dump_json() for t in await wrapped.list_tools()
    ]

    def original(value: int) -> int:
        return value

    assert wrapped.tool()(original) is original


async def test_cancelled_scope_waits_for_worker_before_client_close():
    import anyio

    from server import _MealieServer

    mcp = _MealieServer(None)
    entered, release = threading.Event(), threading.Event()
    events = []

    @mcp.tool()
    def slow() -> str:
        entered.set()
        assert release.wait(3)
        events.append("worker-finished")
        return "done"

    async def caller():
        await mcp.call_tool("slow", {})

    timer = threading.Timer(0.3, release.set)
    timer.start()
    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(caller)
            with anyio.fail_after(2):
                while not entered.is_set():
                    await anyio.sleep(0.01)
            tg.cancel_scope.cancel()
        events.append("client-close-safe")
    finally:
        release.set()
        timer.join()
    assert events == ["worker-finished", "client-close-safe"]


async def test_full_mealie_328_ingredient_and_step_roundtrip():
    ingredient = {
        "quantity": 2,
        "unit": {"name": "gram", "id": "8d8dbe47-811e-4f27-9ed3-cfa87b6962ba"},
        "food": {"name": "rice", "id": "b54bd00d-68af-4d6b-8fcf-0cb24220df6f"},
        "referencedRecipe": {
            "id": "526fd567-ecdc-47c7-95de-c4f41ab18806",
            "slug": "linked",
        },
        "note": "synthetic",
        "display": "old rendered text",
        "title": "section",
        "originalText": "2 g rice",
        "substitutions": [
            {"substituteFoodId": None, "note": "water", "substituteFood": None}
        ],
        "referenceId": "428a7081-f8cd-4406-a6c6-9317ba661aa9",
    }
    step = {
        "id": "53c99c94-00d2-4014-9e47-f4ee8bf84174",
        "title": "section",
        "summary": "heading",
        "text": "mix",
        "ingredientReferences": [{"referenceId": ingredient["referenceId"]}],
        "noteReferences": [{"referenceId": "cc1d58da-2620-4d01-8384-f28bb931d4fb"}],
    }
    current = {
        "slug": "roundtrip",
        "name": "test",
        "recipeIngredient": [ingredient],
        "recipeInstructions": [step],
    }

    def respond(request):
        return httpx.Response(
            200,
            json=json.loads(request.content) if request.method == "PUT" else current,
        )

    with real_backend(respond) as (backend, requests):
        mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
        mcp.client_provider._client = backend
        fetched = backend.get_recipe("roundtrip")
        await mcp.call_tool(
            "update_recipe",
            {
                "slug": "roundtrip",
                "ingredients": fetched["recipeIngredient"],
                "instructions": fetched["recipeInstructions"],
            },
        )
        payload = json.loads(requests[-1].content)
        expected = {k: v for k, v in ingredient.items() if k != "display"}
        assert payload["recipeIngredient"] == [expected]
        assert payload["recipeInstructions"] == [step]


async def test_partial_progress_keeps_sanitized_error_cause():
    def respond(request):
        if request.method == "POST":
            return httpx.Response(200, json="created")
        return httpx.Response(422, json={"detail": "SENSITIVE synthetic-backend-body"})

    with real_backend(respond) as (backend, requests):
        mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
        mcp.client_provider._client = backend
        with pytest.raises(ToolError) as error:
            await mcp.call_tool("create_recipe", {"name": "synthetic"})
        message = str(error.value)
        assert "HTTP 422" in message
        assert "created_slug" in message
        assert "SENSITIVE" not in message


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
async def test_url_import_timeout_is_unknown_outcome_and_never_retried(failure):
    def respond(request):
        raise failure("SENSITIVE URL and private backend context", request=request)

    with real_backend(respond) as (backend, requests):
        mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
        mcp.client_provider._client = backend
        with pytest.raises(ToolError) as error:
            await mcp.call_tool(
                "import_recipe_from_url", {"url": "https://example.org/recipe"}
            )
        assert "unknown" in str(error.value).lower()
        assert "SENSITIVE" not in str(error.value)
        assert len(requests) == 1
        assert requests[0].extensions["timeout"]["read"] == 300


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("import_recipe_from_url", {"url": "file:///etc/passwd"}),
        (
            "set_recipe_image_from_url",
            {"slug": "valid", "image_url": "ftp://example.org/image"},
        ),
        ("create_recipe", {"name": "valid", "image_url": "file:///etc/passwd"}),
        ("create_recipe", {"name": "valid", "org_url": "javascript:alert(1)"}),
        ("update_recipe", {"slug": "valid", "org_url": "data:text/plain,bad"}),
    ],
)
async def test_non_http_urls_rejected_before_any_request(tool, args):
    with real_backend() as (backend, requests):
        mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
        mcp.client_provider._client = backend
        with pytest.raises(ToolError):
            await mcp.call_tool(tool, args)
        assert requests == []


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (401, {"detail": "private"}),
        (403, {}),
        (200, {"admin": True}),
        (200, {}),
        (200, {"admin": "false"}),
        (200, []),
    ],
)
def test_startup_rejects_invalid_admin_or_malformed_identity(status, payload):
    client = httpx.Client(
        base_url="http://mealie.invalid",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                status if r.url.path == "/api/users/self" else 200,
                json=payload
                if r.url.path == "/api/users/self"
                else {"version": "v3.28.0"},
            )
        ),
    )
    with patch("mealie.client.httpx.Client", return_value=client):
        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            MealieFetcher("http://mealie.invalid", "synthetic")
    assert client.is_closed


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MCP_ALLOWED_HOSTS", "*"),
        ("MCP_ALLOWED_HOSTS", " , "),
        ("MCP_ALLOWED_HOSTS", "*.example.org"),
        ("MCP_ALLOWED_ORIGINS", "*"),
        ("MCP_ALLOWED_ORIGINS", "https://*"),
    ],
)
def test_transport_allowlists_reject_empty_or_wildcard(monkeypatch, name, value):
    monkeypatch.setenv("MEALIE_BASE_URL", "http://mealie.invalid")
    monkeypatch.setenv("MEALIE_API_KEY", "synthetic")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        ServerConfig.from_environment()


def test_transport_allowlists_replace_defaults_and_trim(monkeypatch):
    monkeypatch.setenv("MEALIE_BASE_URL", "http://mealie.invalid")
    monkeypatch.setenv("MEALIE_API_KEY", "synthetic")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "127.0.0.1:*, example.org ")
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://example.org ")
    server = create_server(ServerConfig.from_environment())
    assert server.settings.transport_security.allowed_hosts == [
        "127.0.0.1:*",
        "example.org",
    ]
    assert server.settings.transport_security.allowed_origins == ["https://example.org"]


async def test_http_initialize_progresses_while_sync_tool_is_waiting():
    import anyio

    entered, release = threading.Event(), threading.Event()

    def respond(request):
        if request.url.path == "/api/app/about":
            return httpx.Response(200, json={"version": "v3.28.0"})
        if request.url.path == "/api/users/self":
            return httpx.Response(200, json={"admin": False})
        entered.set()
        assert release.wait(3)
        return httpx.Response(200, json={"items": [], "total": 0})

    api = httpx.Client(
        base_url="http://mealie.invalid", transport=httpx.MockTransport(respond)
    )
    mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
    app = mcp.streamable_http_app()
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }
    headers = {"Accept": "application/json, text/event-stream"}
    timer = threading.Timer(0.8, release.set)
    timer.start()
    try:
        with patch("mealie.client.httpx.Client", return_value=api):
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    base_url="http://127.0.0.1:8765", transport=httpx.ASGITransport(app)
                ) as http:
                    first = await http.post("/mcp", json=body, headers=headers)
                    session = dict(
                        headers, **{"Mcp-Session-Id": first.headers["Mcp-Session-Id"]}
                    )
                    await http.post(
                        "/mcp",
                        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                        headers=session,
                    )
                    call = asyncio.create_task(
                        http.post(
                            "/mcp",
                            json={
                                "jsonrpc": "2.0",
                                "id": 2,
                                "method": "tools/call",
                                "params": {"name": "get_recipes", "arguments": {}},
                            },
                            headers=session,
                        )
                    )
                    try:
                        with anyio.fail_after(2):
                            while not entered.is_set():
                                await anyio.sleep(0.01)
                        assert not release.is_set()
                        health = await http.post("/mcp", json=body, headers=headers)
                        assert health.status_code == 200
                        assert not release.is_set()
                        await http.delete(
                            "/mcp",
                            headers=dict(
                                headers,
                                **{"Mcp-Session-Id": health.headers["Mcp-Session-Id"]},
                            ),
                        )
                    finally:
                        release.set()
                        assert (await call).status_code == 200
                    await http.delete("/mcp", headers=session)
        assert api.is_closed
    finally:
        release.set()
        timer.join()


async def test_parallel_recipe_writes_preserve_both_successful_changes():
    from copy import deepcopy

    state = {
        "slug": "r",
        "name": "r",
        "recipeServings": 2,
        "recipeIngredient": [],
        "recipeInstructions": [],
        "settings": {},
    }
    patched = threading.Event()

    def respond(request):
        if request.method == "GET":
            snapshot = deepcopy(state)
            patched.wait(0.2)  # Force the old implementation to read stale state.
            return httpx.Response(200, json=snapshot)
        body = json.loads(request.content)
        if request.method == "PATCH":
            state.update(body)
            patched.set()
        else:
            state.clear()
            state.update(body)
        return httpx.Response(200, json=state)

    with real_backend(respond) as (backend, requests):
        mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
        mcp.client_provider._client = backend
        await asyncio.gather(
            mcp.call_tool(
                "update_recipe", {"slug": "r", "ingredients": ["synthetic rice"]}
            ),
            mcp.call_tool("update_recipe", {"slug": "r", "servings": 4}),
        )
        assert state["recipeServings"] == 4
        assert state["recipeIngredient"][0]["note"] == "synthetic rice"


async def test_reads_progress_while_short_write_holds_its_lock():
    import anyio

    entered, release = threading.Event(), threading.Event()

    def respond(request):
        if request.url.path.endswith("/writing") and request.method == "GET":
            entered.set()
            assert release.wait(3)
        return httpx.Response(200, json={"name": "synthetic", "slug": "writing"})

    with real_backend(respond) as (backend, requests):
        mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
        mcp.client_provider._client = backend
        timer = threading.Timer(0.8, release.set)
        timer.start()
        try:
            write = asyncio.create_task(
                mcp.call_tool(
                    "update_recipe", {"slug": "writing", "ingredients": ["synthetic"]}
                )
            )
            with anyio.fail_after(2):
                while not entered.is_set():
                    await anyio.sleep(0.01)
            await mcp.call_tool("get_recipe", {"slug": "reading"})
            assert not release.is_set()
            release.set()
            await write
        finally:
            release.set()
            timer.join()


async def test_concise_recipe_preserves_readable_ingredient_display():
    def respond(request):
        return httpx.Response(
            200,
            json={
                "userId": "synthetic-user",
                "householdId": "synthetic-household",
                "groupId": "synthetic-group",
                "name": "synthetic",
                "slug": "r",
                "recipeIngredient": [{"quantity": 200, "display": "200 g rice"}],
            },
        )

    with real_backend(respond) as (backend, requests):
        mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic"))
        mcp.client_provider._client = backend
        result = await mcp.call_tool("get_recipe", {"slug": "r", "concise": True})
        assert "200 g rice" in str(result)


@pytest.mark.parametrize("tool", ["import_recipe_from_url", "import_recipe_with_ai"])
@pytest.mark.parametrize("status", [502, 503, 504])
async def test_import_proxy_failure_has_unknown_outcome(tool, status):
    def respond(request):
        if request.url.path == "/api/groups/self":
            return httpx.Response(
                200,
                json={
                    "aiProviderSettings": {
                        "aiEnabled": True,
                        "imageProviderEnabled": False,
                        "audioProviderEnabled": False,
                    }
                },
            )
        return httpx.Response(status, text="SENSITIVE synthetic proxy body")

    with real_backend(respond) as (backend, requests):
        mcp = create_server(
            ServerConfig("http://mealie.invalid", "synthetic", enable_ai_import=True)
        )
        mcp.client_provider._client = backend
        args = (
            {"url": "https://example.org/recipe"}
            if tool.endswith("url")
            else {"content": "synthetic text recipe"}
        )
        with pytest.raises(ToolError) as error:
            await mcp.call_tool(tool, args)
        assert "unknown" in str(error.value).lower()
        assert "SENSITIVE" not in str(error.value)
        assert sum(r.method == "POST" for r in requests) == 1


async def test_legacy_text_times_remain_visible(invoke, fetcher):
    fetcher.recipe.update(totalTime="30 min", prepTime="10 min", performTime="20 min")
    result = await invoke("get_recipe", slug="test-recipe", concise=True)
    assert result["totalTime"] == "30 min"
    assert "totalTimeSeconds" not in result
    assert "prepTimeSeconds" not in result
    assert "performTimeSeconds" not in result


async def test_time_text_and_ingredients_clear_only_selected_duration(invoke, fetcher):
    fetcher.recipe.update(totalTimeSeconds=1800, prepTimeSeconds=600)
    await invoke(
        "update_recipe",
        slug="test-recipe",
        total_time="45 min",
        ingredients=["synthetic"],
    )
    body = fetcher.last("PUT", "/api/recipes/")["json"]
    assert body["totalTime"] == "45 min"
    assert body["totalTimeSeconds"] is None
    assert body["prepTimeSeconds"] == 600


async def test_empty_time_text_clears_structured_duration(invoke, fetcher):
    fetcher.recipe.update(totalTimeSeconds=1800)
    await invoke("update_recipe", slug="test-recipe", total_time="")
    body = fetcher.last("PATCH", "/api/recipes/")["json"]
    assert body == {"totalTime": "", "totalTimeSeconds": None}


async def test_create_recipe_accepts_time_text(invoke, fetcher):
    await invoke("create_recipe", name="Synthetic time", total_time="45 min")
    body = fetcher.last("PUT", "/api/recipes/")["json"]
    assert body["totalTime"] == "45 min"
    assert body["totalTimeSeconds"] is None
