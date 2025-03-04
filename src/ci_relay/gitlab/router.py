import json

import aiohttp
from gidgetlab.routing import Router
from gidgetlab.sansio import Event
from sanic import Sanic
from sanic.log import logger
import gidgetlab.aiohttp
import asyncio

import ci_relay.github.utils as github
from ci_relay.gitlab import GitLab
from ci_relay.signature import Signature


async def on_job_hook(
    event: Event, gitlab_client: GitLab, app: Sanic, session: aiohttp.ClientSession
):
    if event.data["object_kind"] != "build":
        raise ValueError("Object is not a build")

    project_id = event.data["project_id"]
    pipeline_id = event.data["pipeline_id"]

    pipeline, variables, project, job = await asyncio.gather(
        gitlab_client.get_pipeline(project_id, pipeline_id),
        gitlab_client.get_pipeline_variables(project_id, pipeline_id),
        gitlab_client.get_project(project_id),
        gitlab_client.get_job(project_id, event.data["build_id"]),
    )

    bridge_payload = variables["BRIDGE_PAYLOAD"]
    signature = variables["TRIGGER_SIGNATURE"]

    if not Signature(app.config.TRIGGER_SECRET).verify(bridge_payload, signature):
        logger.error("Signatures do not match")
        return

    bridge_payload = json.loads(bridge_payload)

    print(bridge_payload)
    assert "installation_id" in bridge_payload
    installation_id = bridge_payload["installation_id"]

    logger.debug("Installation id: %s", installation_id)

    gh = await github.client_for_installation(app, installation_id, session)

    await github.handle_pipeline_status(
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
    gl: gidgetlab.aiohttp.GitLabAPI,
    app: Sanic,
):
    logger.debug("Received pipeline hook")


@router.register("Job Hook")
async def _on_job_hook(
    event: Event,
    session: aiohttp.ClientSession,
    gl: gidgetlab.aiohttp.GitLabAPI,
    app: Sanic,
):
    gitlab_client = GitLab(session=session, gl=gl, config=app.config)
    await on_job_hook(event, gitlab_client=gitlab_client, app=app, session=session)
