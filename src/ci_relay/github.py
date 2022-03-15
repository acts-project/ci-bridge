import asyncio
from typing import Any, Mapping
import gidgethub

from gidgethub.routing import Router
from sanic.log import logger
from sanic import Sanic
from gidgethub.abc import GitHubAPI
from gidgethub.sansio import Event
from gidgethub import BadRequest
import aiohttp

from ci_relay import config


def create_router():
    router = Router()

    @router.register("pull_request")
    async def on_pr(event: Event, gh: GitHubAPI, app: Sanic):

        pr = event.data["pull_request"]
        logger.debug("Received pull_request event on PR #%d", pr["number"])

        action = event.data["action"]
        logger.debug("Action: %s", action)

        repo_url = event.data["repository"]["url"]
        logger.debug("Repo url is %s", repo_url)

        if action not in ("synchronize", "opened"):
            return

        return await handle_synchronize(gh, event.data)

    return router


async def handle_synchronize(gh: GitHubAPI, data: Mapping[str, Any]):
    pr = data["pull_request"]
    author = pr["user"]["login"]
    logger.debug("PR author is %s", author)
    org = data["organization"]["login"]
    logger.debug("Org is %s", org)
    logger.info("Allow team is: %s", config.ALLOW_TEAM)

    allow_org, allow_team = config.ALLOW_TEAM.split("/", 1)

    if allow_org != org:
        raise ValueError(f"Allow team {config.ALLOW_TEAM} not in org {org}")

    author_in_team = False
    try:
        membership = await gh.getitem(
            f"/orgs/{org}/teams/{allow_team}/memberships/{author}"
        )
        author_in_team = True
    except gidgethub.BadRequest as e:
        if e.status_code != 404:
            raise e

    logger.debug(
        "Is author %s in team %s: %s", author, config.ALLOW_TEAM, author_in_team
    )

    if not author_in_team:
        logger.debug("Author is not in team, stop processing")
        return

    logger.debug("Author is in team, triggering pipeline")
