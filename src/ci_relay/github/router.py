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
    handle_comment,
)
from ci_relay.github.models import (
    PullRequestEvent,
    CheckRunEvent,
    CheckSuiteEvent,
    PushEvent,
    IssueCommentEvent,
)
from ci_relay.gitlab import GitLab

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

    gitlab_client = GitLab(session=session, gl=gl, config=app.config)

    return await handle_synchronize(
        gh, session, data, gitlab_client=gitlab_client, config=app.config
    )


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
    gitlab_client = GitLab(session=session, gl=gl, config=app.config)
    await handle_check_suite(
        gh, session, data, gitlab_client=gitlab_client, config=app.config
    )


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
    gitlab_client = GitLab(session=session, gl=gl, config=app.config)
    await handle_push(gh, data, gitlab_client=gitlab_client, config=app.config)


@router.register("issue_comment")
async def on_comment(
    event: Event,
    session: aiohttp.ClientSession,
    gh: GitHubAPI,
    app: Sanic,
    gl: GitLabAPI,
):
    data = IssueCommentEvent(**event.data)
    logger.debug("Received issue_comment event")
    logger.debug("Action: %s", data.action)

    gitlab_client = GitLab(session=session, gl=gl, config=app.config)
    await handle_comment(
        gh, session, data, gitlab_client=gitlab_client, config=app.config
    )
