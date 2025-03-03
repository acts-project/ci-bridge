import json

import aiohttp
from gidgetlab.routing import Router
from gidgetlab.abc import GitLabAPI
from gidgethub.abc import GitHubAPI
from gidgetlab.sansio import Event
from sanic import Sanic
from sanic.log import logger
import asyncio

import ci_relay.gitlab.utils as utils
from ci_relay.signature import Signature


async def on_job_hook(event: Event, gl: GitLabAPI, gh: GitHubAPI, app: Sanic):
    if event.data["object_kind"] != "build":
        raise ValueError("Object is not a build")

    project_id = event.data["project_id"]
    pipeline_id = event.data["pipeline_id"]

    pipeline, variables, project, job = await asyncio.gather(
        utils.get_pipeline(project_id, pipeline_id, session=app.ctx.aiohttp_session),
        utils.get_pipeline_variables(
            project_id, pipeline_id, session=app.ctx.aiohttp_session
        ),
        utils.get_project(project_id, session=app.ctx.aiohttp_session),
        utils.get_job(
            project_id, event.data["build_id"], session=app.ctx.aiohttp_session
        ),
    )

    #  logger.debug("%s", pipeline)
    #  logger.debug("%s", variables)

    bridge_payload = variables["BRIDGE_PAYLOAD"]
    signature = variables["TRIGGER_SIGNATURE"]

    if not Signature().verify(bridge_payload, signature):
        logger.error("Signatures do not match")
        return

    bridge_payload = json.loads(bridge_payload)

    installation_id = bridge_payload["installation_id"]
    logger.debug("Installation id: %s", installation_id)

    await utils.handle_pipeline_status(
        pipeline=pipeline,
        job=job,
        project=project,
        repo_url=bridge_payload["repo_url"],
        head_sha=bridge_payload["head_sha"],
        gh=gh,
        app=app,
    )


router = Router()


@router.register("Pipeline Hook")
async def _on_pipeline_hook(
    event: Event,
    session: aiohttp.ClientSession,
    gl: GitLabAPI,
    gh: GitHubAPI,
    app: Sanic,
):
    logger.debug("Received pipeline hook")


@router.register("Job Hook")
async def _on_job_hook(
    event: Event,
    session: aiohttp.ClientSession,
    gl: GitLabAPI,
    gh: GitHubAPI,
    app: Sanic,
):
    await on_job_hook(event, gl, gh, app)
