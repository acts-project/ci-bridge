import hmac

from sanic import Sanic, SanicException, response
import aiohttp
from gidgethub import sansio
from gidgethub.apps import get_installation_access_token, get_jwt
from gidgethub import aiohttp as gh_aiohttp
import gidgetlab.aiohttp
from sanic.log import logger
import cachetools
import json
import asyncio

from ci_relay import config, gitlab
from ci_relay.github import create_router, get_installed_repos, handle_pipeline_status


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
        logger.debug("status check")
        return response.text("ok")

    @app.route("/health")
    async def health(request):
        gh = gh_aiohttp.GitHubAPI(app.ctx.aiohttp_session, __name__)

        github_ok = False
        gitlab_ok = False

        # access_token_url = f"/app/installations/{installation_id}/access_tokens"

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
        text = f"GitHub: {"ok" if github_ok else "not ok"}, GitLab: {"ok" if gitlab_ok else "not ok"}"
        return response.text(text, status=status)

    async def handle_webhook(request):
        if request.headers.get("X-Gitlab-Event") == "Pipeline Hook":
            logger.debug("Received pipeline report")
        elif request.headers.get("X-Gitlab-Event") == "Job Hook":
            # this is a ping back!
            logger.debug("Received job report")
            if request.headers["X-Gitlab-Token"] != config.GITLAB_WEBHOOK_SECRET:
                raise ValueError("Webhook has invalid token")

            payload = request.json

            if payload["object_kind"] != "build":
                raise ValueError("Object is not a build")

            project_id = payload["project_id"]
            pipeline_id = payload["pipeline_id"]

            pipeline, variables, project, job = await asyncio.gather(
                gitlab.get_pipeline(
                    project_id, pipeline_id, session=app.ctx.aiohttp_session
                ),
                gitlab.get_pipeline_variables(
                    project_id, pipeline_id, session=app.ctx.aiohttp_session
                ),
                gitlab.get_project(project_id, session=app.ctx.aiohttp_session),
                gitlab.get_job(
                    project_id, payload["build_id"], session=app.ctx.aiohttp_session
                ),
            )

            #  logger.debug("%s", pipeline)
            #  logger.debug("%s", variables)

            bridge_payload = variables["BRIDGE_PAYLOAD"]
            signature = variables["TRIGGER_SIGNATURE"]

            expected_signature = hmac.new(
                config.TRIGGER_SECRET,
                bridge_payload.encode(),
                digestmod="sha512",
            ).hexdigest()
            if not hmac.compare_digest(expected_signature, signature):
                logger.error("Signatures do not match")
                return response.empty(400)

            bridge_payload = json.loads(bridge_payload)

            installation_id = bridge_payload["installation_id"]
            logger.debug("Installation id: %s", installation_id)

            gh = await client_for_installation(app, installation_id)

            await handle_pipeline_status(
                pipeline=pipeline,
                job=job,
                project=project,
                repo_url=bridge_payload["repo_url"],
                head_sha=bridge_payload["head_sha"],
                gh=gh,
                app=app,
            )

        else:
            event = sansio.Event.from_http(
                request.headers, request.body, secret=app.config.WEBHOOK_SECRET
            )

            if event.event == "ping":
                return response.empty(200)

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
            await app.ctx.github_router.dispatch(event, gh, app=app, gl=gl)

    @app.route("/webhook", methods=["POST"])
    async def github(request):
        logger.debug("Webhook received")

        app.add_task(handle_webhook(request))

        return response.empty(200)

    return app
