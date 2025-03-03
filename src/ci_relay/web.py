from sanic import Sanic, response
import aiohttp
from gidgethub.sansio import Event as GitHubEvent
from gidgetlab.sansio import Event as GitLabEvent
from gidgethub.apps import get_installation_access_token, get_jwt
from gidgethub import aiohttp as gh_aiohttp
import gidgetlab.aiohttp
from sanic.log import logger
import cachetools
from aiolimiter import AsyncLimiter

from ci_relay import config
from ci_relay.github.router import router as github_router
from ci_relay.gitlab.router import router as gitlab_router


async def client_for_installation(app, installation_id):
    gh_pre = gh_aiohttp.GitHubAPI(app.ctx.aiohttp_session, __name__)
    access_token_response = await get_installation_access_token(
        gh_pre,
        installation_id=installation_id,
        app_id=app.config.APP_ID,
        private_key=app.config.PRIVATE_KEY,
    )

    token = access_token_response["token"]

    return gh_aiohttp.GitHubAPI(
        app.ctx.aiohttp_session,
        __name__,
        oauth_token=token,
        cache=app.ctx.cache,
    )


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

    async def handle_gitlab_webhook(request):
        if request.headers.get("X-Gitlab-Event") == "Pipeline Hook":
            logger.debug("Received pipeline report")
        elif request.headers.get("X-Gitlab-Event") == "Job Hook":
            # # this is a ping back!
            # logger.debug("Received job report")
            # if request.headers["X-Gitlab-Token"] != config.GITLAB_WEBHOOK_SECRET:
            #     raise ValueError("Webhook has invalid token")

            event = GitLabEvent.from_http(
                request.headers, request.body, secret=config.GITLAB_WEBHOOK_SECRET
            )

            assert "installation" in event.data
            installation_id = event.data["installation"]["id"]
            logger.debug("Installation id: %s", installation_id)
            gh = await client_for_installation(app, installation_id)

            gl = gidgetlab.aiohttp.GitLabAPI(
                app.ctx.aiohttp_session,
                requester="acts",
                access_token=config.GITLAB_ACCESS_TOKEN,
                url=config.GITLAB_API_URL,
            )

            logger.debug("Dispatching event %s", event.event)
            await gitlab_router.dispatch(
                event, session=app.ctx.aiohttp_session, gh=gh, app=app, gl=gl
            )

    async def handle_github_webhook(request):
        event = GitHubEvent.from_http(
            request.headers, request.body, secret=app.config.WEBHOOK_SECRET
        )

        assert "installation" in event.data
        installation_id = event.data["installation"]["id"]
        logger.debug("Installation id: %s", installation_id)

        gh = await client_for_installation(app, installation_id)

        gl = gidgetlab.aiohttp.GitLabAPI(
            app.ctx.aiohttp_session,
            requester="acts",
            access_token=config.GITLAB_ACCESS_TOKEN,
            url=config.GITLAB_API_URL,
        )

        logger.debug("Dispatching event %s", event.event)
        await github_router.dispatch(
            event, session=app.ctx.aiohttp_session, gh=gh, app=app, gl=gl
        )

    @app.route("/webhook/github", methods=["POST"])
    async def github(request):
        logger.debug("Webhook received")

        app.add_task(handle_github_webhook(request))

        return response.empty(200)

    @app.route("/webhook/gitlab", methods=["POST"])
    async def gitlab(request):
        logger.debug("Webhook received")

        app.add_task(handle_gitlab_webhook(request))

        return response.empty(200)

    return app
