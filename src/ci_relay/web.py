import logging

from sanic import Sanic, response
import aiohttp
from gidgethub import sansio
from gidgethub.apps import get_installation_access_token, get_jwt
from gidgethub import aiohttp as gh_aiohttp
from sanic.log import logger
import cachetools

from ci_relay import config
from ci_relay.github import create_router


def create_app():

    app = Sanic("ci-relay")
    app.update_config(config)
    # app.logger = logging.getLogger(__name__)
    # if app.debug:
    # app.logger.setLevel(logging.DEBUG)

    app.ctx.cache = cachetools.LRUCache(maxsize=500)
    app.ctx.github_router = create_router()

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
        return response.text("hallo")

    @app.route("/webhook", methods=["POST"])
    async def github(request):
        logger.debug("Webhook received")
        event = sansio.Event.from_http(
            request.headers, request.body, secret=app.config.WEBHOOK_SECRET
        )

        if event.event == "ping":
            return response.empty(200)

        assert "installation" in event.data
        installation_id = event.data["installation"]["id"]
        logger.debug("Installation id: %s", installation_id)

        gh_pre = gh_aiohttp.GitHubAPI(app.ctx.aiohttp_session, __name__)
        access_token_response = await get_installation_access_token(
            gh_pre,
            installation_id=installation_id,
            app_id=app.config.APP_ID,
            private_key=app.config.PRIVATE_KEY,
        )

        token = access_token_response["token"]

        gh = gh_aiohttp.GitHubAPI(
            app.ctx.aiohttp_session, __name__, oauth_token=token, cache=app.ctx.cache
        )

        logger.debug("Dispatching event %s", event.event)
        await app.ctx.github_router.dispatch(event, gh, app=app)

        return response.empty(200)

    return app
