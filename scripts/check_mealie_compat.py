"""Destructive synthetic check, ONLY for an empty disposable Docker test instance.

Run inside the connector image on an internal network with a Mealie container
named mealie-compat-test. No caller-supplied URL or credentials are accepted.
The disposable instance and network must be removed after the check.
"""

import argparse
import asyncio
import json
import logging
import secrets

import httpx
from mcp.server.fastmcp.exceptions import ToolError

from server import ServerConfig, create_server

BASE = "http://mealie-compat-test:9000"
logging.disable(logging.CRITICAL)


def checked(response):
    response.raise_for_status()
    return response.json()


async def main(expected_version):
    with httpx.Client(base_url=BASE, timeout=30) as api:
        about = checked(api.get("/api/app/about"))
        assert (
            about["version"] == expected_version
        ), "Unexpected disposable Mealie version"
        modern = expected_version == "v3.30.0"
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
            instructions=[
                {"text": "Wait", **({"durationSeconds": 600} if modern else {})}
            ],
        )
        slug = recipe["slug"]
        assert recipe["orgURL"] == "Family notebook"
        await call("update_recipe", slug=slug, org_url="Cookbook, page 42")
        recipe = await call("get_recipe", slug=slug)
        assert recipe["orgURL"] == "Cookbook, page 42"
        if modern:
            assert recipe["recipeInstructions"][0]["durationSeconds"] == 600
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
        else:
            await call(
                "update_recipe",
                slug=slug,
                ingredients=[
                    {"quantity": 2, "note": "Synthetic", "originalText": "2 synthetic"}
                ],
            )
            recipe = await call("get_recipe", slug=slug)
            await call(
                "update_recipe",
                slug=slug,
                ingredients=recipe["recipeIngredient"],
                instructions=recipe["recipeInstructions"],
            )
            recipe = await call("get_recipe", slug=slug)
            assert recipe["recipeIngredient"][0]["originalText"] == "2 synthetic"
            day = await call(
                "create_mealplan", date="2099-11-29", title="Synthetic day"
            )
            await call("update_mealplan", entry_id=str(day["id"]), title="Renamed day")
            # The old API silently drops these fields; the connector must reject before writes.
            rejected = [
                (
                    "create_recipe",
                    {
                        "name": "Must not exist",
                        "instructions": [{"text": "Wait", "durationSeconds": 600}],
                    },
                ),
                (
                    "update_recipe",
                    {
                        "slug": slug,
                        "instructions": [{"text": "Wait", "durationSeconds": 600}],
                    },
                ),
                (
                    "create_mealplan_bulk",
                    {
                        "entries": [
                            {"date": "2099-12-01", "title": "Must not exist"},
                            {
                                "date": "2099-12-06",
                                "end_date": "2099-12-12",
                                "title": "Must not exist",
                            },
                        ]
                    },
                ),
                (
                    "update_mealplan",
                    {"entry_id": str(day["id"]), "clear_end_date": True},
                ),
            ]
            for name, args in rejected:
                try:
                    await call(name, **args)
                except ToolError as error:
                    assert "requires Mealie 3.30" in str(error)
                else:
                    raise AssertionError("Unsupported fields accepted on 3.29")
            recipes = await call("get_recipes", page=1, per_page=1)
            plans = await call("get_all_mealplans", page=1, per_page=1)
            assert recipes["total"] == 1 and plans["total"] == 1
            persisted = await call("get_recipe", slug=slug)
            assert persisted["recipeInstructions"] == recipe["recipeInstructions"]
    print(
        json.dumps(
            {
                "mealie": about["version"],
                "tools": len(tools),
                "non_admin": True,
                "source_metadata_create_update": "passed",
                **(
                    {
                        "step_duration_roundtrip": "passed",
                        "step_duration_clear": "passed",
                        "weekly_create_update_clear_bulk": "passed",
                    }
                    if modern
                    else {
                        "legacy_recipe_roundtrip": "passed",
                        "daily_plan_create_update": "passed",
                        "unsupported_fields_rejected_without_writes": "passed",
                    }
                ),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=("v3.29.0", "v3.30.0"), default="v3.30.0")
    asyncio.run(main(parser.parse_args().version))
