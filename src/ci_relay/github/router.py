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
from ci_relay.github.models import (
    PullRequestEvent,
    CheckRunEvent,
    CheckSuiteEvent,
    PushEvent,
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
    data = PullRequestEvent(**event.data)
    logger.debug("Received pull_request event on PR #%d", data.pull_request.number)

    logger.debug("Action: %s", data.action)

    logger.debug("Repo url is %s", data.repository.url)

    if data.action not in ("synchronize", "opened", "reopened", "ready_for_review"):
        return

    return await handle_synchronize(gh, session, data, gl=gl, config=app.config)


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
    data = CheckRunEvent(**event.data)
    if data.action != "rerequested":
        return
    logger.debug("Received request for check rerun")
    await handle_rerequest(gh, session, data, config=app.config)


@router.register("check_suite")
async def on_check_suite(
    event: Event,
    session: aiohttp.ClientSession,
    gh: GitHubAPI,
    app: Sanic,
    gl: GitLabAPI,
):
    data = CheckSuiteEvent(**event.data)
    if data.action not in ("rerequested",):
        return
    await handle_check_suite(gh, session, data, gl=gl, config=app.config)


@router.register("push")
async def on_push(
    event: Event,
    session: aiohttp.ClientSession,
    gh: GitHubAPI,
    app: Sanic,
    gl: GitLabAPI,
):
    logger.debug("Received push event")
    data = PushEvent(**event.data)
    await handle_push(gh, session, data, gl=gl, config=app.config)
