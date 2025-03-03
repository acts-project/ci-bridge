from gidgethub.routing import Router
from sanic.log import logger
from sanic import Sanic
from gidgethub.abc import GitHubAPI
from gidgethub.sansio import Event
from gidgetlab.abc import GitLabAPI
import aiohttp

from ci_relay.github.utils import (
    handle_synchronize,
    handle_rerequest,
    handle_check_suite,
    handle_push,
)

router = Router()


@router.register("pull_request")
async def on_pr(
    event: Event,
    session: aiohttp.ClientSession,
    gh: GitHubAPI,
    app: Sanic,
    gl: GitLabAPI,
):
    pr = event.data["pull_request"]
    logger.debug("Received pull_request event on PR #%d", pr["number"])

    action = event.data["action"]
    logger.debug("Action: %s", action)

    repo_url = event.data["repository"]["url"]
    logger.debug("Repo url is %s", repo_url)

    if action not in ("synchronize", "opened", "reopened", "ready_for_review"):
        return

    return await handle_synchronize(gh, session, event.data, gl=gl)


@router.register("ping")
async def on_ping(event: Event, gh: GitHubAPI, app: Sanic, gl: GitLabAPI):
    logger.debug("Received ping event")


@router.register("check_run")
async def on_check_run(
    event: Event,
    session: aiohttp.ClientSession,
    gh: GitHubAPI,
    app: Sanic,
    gl: GitLabAPI,
):
    if event.data["action"] != "rerequested":
        return
    logger.debug("Received request for check rerun")
    await handle_rerequest(gh, session, event.data)


@router.register("check_suite")
async def on_check_suite(
    event: Event,
    session: aiohttp.ClientSession,
    gh: GitHubAPI,
    app: Sanic,
    gl: GitLabAPI,
):
    if event.data["action"] not in (
        #  "requested",
        "rerequested",
    ):
        return
    await handle_check_suite(gh, session, event.data, gl=gl)


@router.register("push")
async def on_push(
    event: Event,
    session: aiohttp.ClientSession,
    gh: GitHubAPI,
    app: Sanic,
    gl: GitLabAPI,
):
    logger.debug("Received push event")
    await handle_push(gh, session, event.data, gl=gl)
