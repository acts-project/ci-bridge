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
from ci_relay.gitlab.utils import should_ignore_job
from ci_relay.signature import Signature
from ci_relay.exceptions import (
    InvalidBuildError,
    SignatureMismatchError,
    MissingInstallationIdError,
)


async def on_job_hook(
    event: Event, gitlab_client: GitLab, app: Sanic, session: aiohttp.ClientSession
):
    logger.debug("On job hook")
    if event.data["object_kind"] != "build":
        raise InvalidBuildError(f"Object is not a build: {event.data['object_kind']}")

    project_id = event.data["project_id"]
    pipeline_id = event.data["pipeline_id"]

    pipeline, variables, project, job = await asyncio.gather(
        gitlab_client.get_pipeline(project_id, pipeline_id),
        gitlab_client.get_pipeline_variables(project_id, pipeline_id),
        gitlab_client.get_project(project_id),
        gitlab_client.get_job(project_id, event.data["build_id"]),
    )

    # Check if job should be ignored based on patterns
    logger.debug(
        "Checking if job should be ignored %s (patterns: %s)",
        job["name"],
        app.config.GITLAB_IGNORED_JOB_PATTERNS,
    )
    if should_ignore_job(job["name"], app.config.GITLAB_IGNORED_JOB_PATTERNS):
        logger.info(f"Ignoring job '{job['name']}' based on configured patterns")
        return

    bridge_payload = variables["BRIDGE_PAYLOAD"]
    signature = variables["TRIGGER_SIGNATURE"]

    if not Signature(app.config.TRIGGER_SECRET).verify(bridge_payload, signature):
        logger.error("Signatures do not match")
        raise SignatureMismatchError("Signature mismatch")

    bridge_payload = json.loads(bridge_payload)

    logger.debug("Bridge payload: %s", bridge_payload)
    if "installation_id" not in bridge_payload:
        raise MissingInstallationIdError("installation_id missing from bridge payload")

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
        gitlab_client=gitlab_client,
        config=app.config,
    )

    # Check if GitLab to GitHub workflow triggering is enabled
    if (app.config.ENABLE_GITLAB_TO_GITHUB_TRIGGERING and 
        job["status"] in app.config.GITLAB_TO_GITHUB_TRIGGER_ON_STATUS):
        
        logger.debug("GitLab to GitHub triggering is enabled, checking repository for workflows")
        
        # Trigger GitHub workflow in the repository where the status is being posted
        try:
            success = await github.trigger_github_workflow(
                gh=gh,
                repo_slug=bridge_payload["repo_slug"],
                gitlab_job=job,
                gitlab_project=project,
                gitlab_pipeline=pipeline,
                config=app.config,
            )
            if success:
                logger.info(
                    "Successfully triggered GitHub workflow (GitLab job: %s, status: %s)",
                    job["name"], job["status"]
                )
            else:
                logger.debug(
                    "No GitHub workflow triggered (GitLab job: %s, status: %s)",
                    job["name"], job["status"]
                )
        except Exception as e:
            logger.error(
                "Error triggering GitHub workflow: %s",
                e, exc_info=e
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
