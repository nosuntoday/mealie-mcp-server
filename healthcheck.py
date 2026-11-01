"""MCP initialize + Session-Ende; keine Mealie-Schreibaktion."""

import http.client
import json


def check() -> None:
    connection = http.client.HTTPConnection("127.0.0.1", 8765, timeout=5)
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    try:
        connection.request("POST", "/mcp", json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "healthcheck", "version": "1"},
            },
        }), headers)
        response = connection.getresponse()
        body = response.read().decode()
        if response.status != 200:
            raise RuntimeError("MCP initialize failed")
        payload = body if response.getheader("Content-Type", "").startswith("application/json") else next(
            line[5:].strip() for line in body.splitlines() if line.startswith("data:")
        )
        result = json.loads(payload)
        if "result" not in result or result.get("id") != 1:
            raise RuntimeError("Invalid initialize response")
        headers["Mcp-Session-Id"] = response.getheader("Mcp-Session-Id")
        headers["MCP-Protocol-Version"] = "2025-03-26"
        connection.request("DELETE", "/mcp", headers=headers)
        response = connection.getresponse()
        response.read()
        if response.status != 200:
            raise RuntimeError("MCP session cleanup failed")
    finally:
        connection.close()


if __name__ == "__main__":
    check()
