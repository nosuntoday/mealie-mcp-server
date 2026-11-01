"""Regressionen; in den gepinnten Upstream unter tests/ kopieren."""

import builtins
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from server import ServerConfig, create_server
from tools import register_all_tools


async def test_file_uploads_are_neither_discoverable_nor_callable(fetcher, tmp_path):
    mcp = FastMCP("file-boundary")
    register_all_tools(mcp, fetcher)
    sentinel = tmp_path / "private-file"
    sentinel.write_text("synthetic private bytes")
    names = {t.name for t in await mcp.list_tools()}
    for name, field in (
        ("upload_recipe_image_file", "image_path"),
        ("upload_recipe_asset_file", "asset_path"),
    ):
        assert name not in names
        with pytest.raises(ToolError, match="Unknown tool"):
            await mcp.call_tool(name, {"slug": "test-recipe", field: str(sentinel)})
    assert fetcher.requests == []


async def test_ai_import_does_not_read_server_files(fetcher, tmp_path, monkeypatch):
    mcp = FastMCP("ai-file-boundary")
    register_all_tools(mcp, fetcher, enable_ai_import=True)
    sentinel = tmp_path / "private-file"
    sentinel.write_text("synthetic private bytes")
    reads = []
    original = builtins.open

    def watch(file, *args, **kwargs):
        if str(file) == str(sentinel):
            reads.append(str(file))
        return original(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watch)
    original_read = Path.read_bytes

    def watch_bytes(path):
        if path == sentinel:
            reads.append(str(path))
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", watch_bytes)
    fetcher.responses["GET", "/api/groups/self"] = {"aiProviderSettings": {
        "aiEnabled": True, "imageProviderEnabled": True, "audioProviderEnabled": False,
    }}
    # The SDK may ignore unknown arguments; neither ignoring nor rejection may read.
    try:
        await mcp.call_tool("import_recipe_with_ai", {
            "content": "synthetic recipe", "image_paths": [str(sentinel)],
        })
    except ToolError:
        pass
    assert reads == []
    for request in fetcher.requests:
        assert not request.get("files")


async def test_ai_import_schema_has_no_server_paths(fetcher):
    mcp = FastMCP("ai-schema-boundary")
    register_all_tools(mcp, fetcher, enable_ai_import=True)
    tool = next(t for t in await mcp.list_tools() if t.name == "import_recipe_with_ai")
    assert "image_paths" not in tool.inputSchema["properties"]


async def test_kitchen_tools_have_honest_annotations(fetcher):
    mcp = FastMCP("annotations")
    register_all_tools(mcp, fetcher, enable_ai_import=True)
    tools = {t.name: t for t in await mcp.list_tools()}
    assert all(t.annotations is not None for t in tools.values())
    assert tools["get_recipes"].annotations.readOnlyHint is True
    assert tools["create_recipe"].annotations.readOnlyHint is False
    assert tools["update_recipe"].annotations.destructiveHint is True
    assert tools["delete_recipe"].annotations.destructiveHint is True
    assert tools["import_recipe_with_ai"].annotations.openWorldHint is True
    assert tools["import_recipe_from_url"].annotations.idempotentHint is False


@pytest.mark.parametrize(("name", "hint"), [
    ("create_recipe", "openWorldHint"),
    ("set_recipe_image_from_url", "destructiveHint"),
])
async def test_image_operations_annotations(fetcher, name, hint):
    mcp = FastMCP("image-annotations")
    register_all_tools(mcp, fetcher)
    tools = {t.name: t for t in await mcp.list_tools()}
    assert getattr(tools[name].annotations, hint) is True


@pytest.mark.parametrize(("host", "origin", "expected"), [
    ("mcp.example.invalid", None, 200),
    ("mcp.example.invalid", "https://claude.ai", 200),
    ("mcp.example.invalid", "https://chatgpt.com", 200),
    ("127.0.0.1:8765", None, 200),
    ("evil.example", None, 421),
    ("mcp.example.invalid.evil.example", None, 421),
    ("mcp.example.invalid", "https://evil.example", 403),
])
async def test_http_host_origin_and_bearer_boundary(host, origin, expected):
    outgoing = []

    def respond(request):
        assert request.headers["authorization"] == "Bearer synthetic-backend-token"
        outgoing.append(request.url.path)
        if request.url.path == "/api/users/self":
            return httpx.Response(200, json={"admin": False})
        assert request.url.path in ("/api/app/about", "/api/recipes")
        return httpx.Response(200, json={"items": [], "total": 0})

    api = httpx.Client(base_url="http://mealie.invalid",
                       headers={"Authorization": "Bearer synthetic-backend-token"},
                       transport=httpx.MockTransport(respond))
    mcp = create_server(ServerConfig("http://mealie.invalid", "synthetic-backend-token",
        allowed_hosts=("127.0.0.1:*", "localhost:*", "mcp.example.invalid", "mcp.example.invalid:443"),
        allowed_origins=("https://mcp.example.invalid", "https://claude.ai", "https://chatgpt.com")))
    app = mcp.streamable_http_app()
    with patch("mealie.client.httpx.Client", return_value=api):
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app),
                                         base_url="http://127.0.0.1:8765") as client:
                headers = {"Host": host, "Accept": "application/json, text/event-stream",
                           "Authorization": "Bearer synthetic-cloudflare-token"}
                if origin:
                    headers["Origin"] = origin
                r = await client.post("/mcp", headers=headers, json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "boundary-test", "version": "1"},
                    },
                })
                assert r.status_code == expected
                if expected != 200:
                    assert outgoing == ["/api/app/about", "/api/users/self"]
                    return
                headers["Mcp-Session-Id"] = r.headers["mcp-session-id"]
                r = await client.post("/mcp", headers=headers, json={
                    "jsonrpc": "2.0", "method": "notifications/initialized",
                })
                assert r.status_code == 202
                r = await client.post("/mcp", headers=headers, json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "get_recipes", "arguments": {}},
                })
                assert r.status_code == 200
                assert outgoing == ["/api/app/about", "/api/users/self", "/api/recipes"]
