from sanic import Sanic, response
import aiohttp
from gidgethub.sansio import Event as GitHubEvent
from gidgetlab.sansio import Event as GitLabEvent
from gidgethub.apps import get_jwt
from gidgethub import aiohttp as gh_aiohttp
import gidgetlab.aiohttp
from sanic.log import logger
import cachetools
from aiolimiter import AsyncLimiter
import contextlib
import functools

from ci_relay import config
from ci_relay.github.router import router as github_router
from ci_relay.gitlab.router import router as gitlab_router
import ci_relay.github.utils as github_utils


def with_session(func):
    @functools.wraps(func)
    async def wrapper(
        *args, app: Sanic, session: aiohttp.ClientSession | None = None, **kwargs
    ):
        async with contextlib.AsyncExitStack() as stack:
            if session is None:
                session = await stack.enter_async_context(
                    aiohttp.ClientSession(loop=app.loop)
                )
            print("args", *args)
            print("kwargs", **kwargs)
            return await func(*args, app=app, session=session, **kwargs)

    return wrapper


@with_session
async def handle_gitlab_webhook(request, *, app: Sanic, session: aiohttp.ClientSession):
    event = GitLabEvent.from_http(
        request.headers, request.body, secret=config.GITLAB_WEBHOOK_SECRET
    )

    gl = gidgetlab.aiohttp.GitLabAPI(
        session,
        requester="acts",
        access_token=config.GITLAB_ACCESS_TOKEN,
        url=config.GITLAB_API_URL,
    )

    logger.debug("Dispatching event %s", event.event)
    await gitlab_router.dispatch(event, session=session, app=app, gl=gl)


@with_session
async def handle_github_webhook(request, *, app: Sanic, session: aiohttp.ClientSession):
    event = GitHubEvent.from_http(
        request.headers, request.body, secret=app.config.WEBHOOK_SECRET
    )

    assert "installation" in event.data
    installation_id = event.data["installation"]["id"]
    logger.debug("Installation id: %s", installation_id)

    gh = await github_utils.client_for_installation(
        app=app, installation_id=installation_id, session=session
    )

    gl = gidgetlab.aiohttp.GitLabAPI(
        session,
        requester="acts",
        access_token=config.GITLAB_ACCESS_TOKEN,
        url=config.GITLAB_API_URL,
    )

    logger.debug("Dispatching event %s", event.event)
    await github_router.dispatch(event, session=session, gh=gh, app=app, gl=gl)


def create_app():
    app = Sanic("ci-relay")
    app.update_config(config)
    logger.setLevel(config.OVERRIDE_LOGGING)

    app.ctx.cache = cachetools.LRUCache(maxsize=500)

    limiter = AsyncLimiter(10)

    @app.listener("before_server_start")
    async def init(app, loop):
        logger.debug("Creating aiohttp session")
        app.ctx.aiohttp_session = aiohttp.ClientSession(loop=loop)

        gh = gh_aiohttp.GitHubAPI(app.ctx.aiohttp_session, __name__)
        jwt = get_jwt(app_id=app.config.APP_ID, private_key=app.config.PRIVATE_KEY)
        app_info = await gh.getitem("/app", jwt=jwt)
        app.ctx.app_info = app_info

    @app.route("/")
    async def index(request):
        logger.debug("status check")
        return response.text("ok")

    @app.route("/health")
    async def health(request):
        if not limiter.has_capacity():
            return response.text("Rate limited", status=429)
        await limiter.acquire()

        gh = gh_aiohttp.GitHubAPI(app.ctx.aiohttp_session, __name__)

        github_ok = False
        gitlab_ok = False

        logger.info("Checking health")
        try:
            token = get_jwt(
                app_id=app.config.APP_ID, private_key=app.config.PRIVATE_KEY
            )
            app_info = await gh.getitem("/app", jwt=token)
            if app_info is None:
                github_ok = False
                logger.error("GitHub App info is None")
            logger.info("GitHub ok")
            github_ok = True
        except Exception as e:
            logger.error("GitHub App info failed: %s", e)
            logger.exception(e)
            github_ok = False

        try:
            gl = gidgetlab.aiohttp.GitLabAPI(
                app.ctx.aiohttp_session,
                requester="acts",
                access_token=config.GITLAB_ACCESS_TOKEN,
                url=config.GITLAB_API_URL,
            )
            projects = await gl.getitem(f"/projects/{config.GITLAB_PROJECT_ID}")
            if projects is None:
                gitlab_ok = False
                logger.error("GitLab project info is None")
            logger.info("GitLab ok")
            gitlab_ok = True
        except Exception as e:
            logger.error("GitLab project info failed: %s", e)
            logger.exception(e)
            gitlab_ok = False

        status = 200 if github_ok and gitlab_ok else 500
        github_str = "ok" if github_ok else "not ok"
        gitlab_str = "ok" if gitlab_ok else "not ok"
        text = f"GitHub: {github_str}, GitLab: {gitlab_str}"
        return response.text(text, status=status)

    @app.route("/webhook/github", methods=["POST"])
    async def github(request):
        logger.debug("Webhook received on github endpoint")

        app.add_task(handle_github_webhook(request, app))

        return response.empty(200)

    @app.route("/webhook/gitlab", methods=["POST"])
    async def gitlab(request):
        logger.debug("Webhook received on gitlab endpoint")

        app.add_task(handle_gitlab_webhook(request, app))

        return response.empty(200)

    @app.route("/webhook", methods=["POST"])
    async def webhook(request):
        logger.debug("Webhook received on compatibility endpoint")

        if "X-Gitlab-Event" in request.headers:
            app.add_task(handle_gitlab_webhook(request, app))
        elif "X-GitHub-Event" in request.headers:
            app.add_task(handle_github_webhook(request, app))

        return response.empty(200)

    return app
