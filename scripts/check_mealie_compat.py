"""Destructive synthetic check, ONLY for an empty disposable Docker test instance.

Run inside the connector image on an internal network with a Mealie container
named mealie-compat-test. No caller-supplied URL or credentials are accepted.
The disposable instance and network must be removed after the check.
"""

import asyncio
import json
import logging
import secrets

import httpx

from server import ServerConfig, create_server

BASE = "http://mealie-compat-test:9000"
logging.disable(logging.CRITICAL)


def checked(response):
    response.raise_for_status()
    return response.json()


async def main():
    with httpx.Client(base_url=BASE, timeout=30) as api:
        about = checked(api.get("/api/app/about"))
        assert about["version"] == "v3.30.0", "This check targets Mealie 3.30.0"
        admin = checked(
            api.post(
                "/api/auth/token",
                data={"username": "changeme@example.com", "password": "MyPassword"},
            )
        )
        api.headers["Authorization"] = "Bearer " + admin["access_token"]
        identity = checked(api.get("/api/users/self"))
        assert identity["admin"] is True and identity["email"] == "changeme@example.com"
        assert checked(api.get("/api/recipes", params={"perPage": 1}))["total"] == 0
        password = secrets.token_urlsafe(24)
        checked(
            api.post(
                "/api/admin/users",
                json={
                    "username": "compat-check",
                    "fullName": "Synthetic compatibility check",
                    "email": "compat@example.invalid",
                    "password": password,
                    "group": identity["group"],
                    "household": identity["household"],
                    "admin": False,
                    "canOrganize": True,
                },
            )
        )
        login = checked(
            api.post(
                "/api/auth/token",
                data={"username": "compat@example.invalid", "password": password},
            )
        )
        api.headers["Authorization"] = "Bearer " + login["access_token"]
        token = checked(
            api.post(
                "/api/users/api-tokens", json={"name": "Synthetic compatibility test"}
            )
        )["token"]

    mcp = create_server(ServerConfig(base_url=BASE, api_key=token))

    async def call(tool_name, **args):
        result = await mcp.call_tool(tool_name, args)
        # FastMCP returns content plus structured data for structured tool outputs.
        if isinstance(result, tuple):
            content, structured = result
            if isinstance(structured, dict) and set(structured) == {"result"}:
                return structured["result"]
            if structured is not None:
                return structured
        else:
            content = result
        return json.loads(content[0].text)

    async with mcp.client_provider.lifespan():
        tools = await mcp.list_tools()
        assert len(tools) == 59
        recipe = await call(
            "create_recipe",
            name="Synthetic duration test",
            org_url="Family notebook",
            instructions=[{"text": "Wait", "durationSeconds": 600}],
        )
        slug = recipe["slug"]
        assert recipe["orgURL"] == "Family notebook"
        await call("update_recipe", slug=slug, org_url="Cookbook, page 42")
        recipe = await call("get_recipe", slug=slug)
        assert recipe["recipeInstructions"][0]["durationSeconds"] == 600
        assert recipe["orgURL"] == "Cookbook, page 42"
        # Replacing another collection must not lose the existing step timer.
        await call("update_recipe", slug=slug, ingredients=["Synthetic ingredient"])
        recipe = await call("get_recipe", slug=slug)
        assert recipe["recipeInstructions"][0]["durationSeconds"] == 600
        # A complete step roundtrip preserves the timer as well.
        await call(
            "update_recipe", slug=slug, instructions=recipe["recipeInstructions"]
        )
        recipe = await call("get_recipe", slug=slug)
        assert recipe["recipeInstructions"][0]["durationSeconds"] == 600
        recipe["recipeInstructions"][0]["durationSeconds"] = 0
        await call(
            "update_recipe", slug=slug, instructions=recipe["recipeInstructions"]
        )
        recipe = await call("get_recipe", slug=slug)
        assert recipe["recipeInstructions"][0]["durationSeconds"] is None
        meal = await call(
            "create_mealplan",
            date="2099-11-29",
            end_date="2099-12-05",
            title="Synthetic week",
        )
        entry_id = str(meal["id"])
        await call("update_mealplan", entry_id=entry_id, title="Renamed week")
        await call(
            "update_mealplan",
            entry_id=entry_id,
            date="2099-12-06",
            end_date="2099-12-12",
        )
        with httpx.Client(
            base_url=BASE, headers={"Authorization": "Bearer " + token}
        ) as api:
            persisted = checked(api.get("/api/households/mealplans/" + entry_id))
            assert persisted["endDate"] == "2099-12-12"
        await call("update_mealplan", entry_id=entry_id, clear_end_date=True)
        with httpx.Client(
            base_url=BASE, headers={"Authorization": "Bearer " + token}
        ) as api:
            persisted = checked(api.get("/api/households/mealplans/" + entry_id))
            assert persisted["endDate"] is None
        await call(
            "create_mealplan_bulk",
            entries=[
                {
                    "date": "2099-12-13",
                    "end_date": "2099-12-19",
                    "title": "Synthetic bulk week",
                }
            ],
        )
    print(
        json.dumps(
            {
                "mealie": about["version"],
                "tools": len(tools),
                "non_admin": True,
                "source_metadata_create_update": "passed",
                "step_duration_roundtrip": "passed",
                "step_duration_clear": "passed",
                "weekly_create_update_clear_bulk": "passed",
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
