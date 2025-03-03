import re
import json

import aiohttp
from gidgetlab.abc import GitLabAPI
from gidgethub.abc import GitHubAPI
from sanic.log import logger

from ci_relay import config
from ci_relay.gitlab.models import PipelineTriggerData
from ci_relay.signature import Signature

_default_headers = {"Private-Token": config.GITLAB_ACCESS_TOKEN}

ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/ ]*[@-~])")


def get_pipeline_url(project_id: int, pipeline_id: int) -> str:
    return f"{config.GITLAB_API_URL}/projects/{project_id}/pipelines/{pipeline_id}"


async def get_pipeline(
    project_id: int, pipeline_id: int, session: aiohttp.ClientSession
):
    full_pipeline_url = get_pipeline_url(project_id, pipeline_id)

    async with session.get(full_pipeline_url, headers=_default_headers) as resp:
        resp.raise_for_status()
        return await resp.json()


def get_job_url(project_id: int, job_id: int):
    return f"{config.GITLAB_API_URL}/projects/{project_id}/jobs/{job_id}"


async def get_job(project_id: int, job_id: int, session: aiohttp.ClientSession):
    async with session.get(
        get_job_url(project_id, job_id), headers=_default_headers
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


async def get_job_log(project_id: int, job_id: int, session: aiohttp.ClientSession):
    async with session.get(
        get_job_url(project_id, job_id) + "/trace", headers=_default_headers
    ) as resp:
        resp.raise_for_status()
        text = await resp.text()

    return ansi_escape.sub("", text)


async def get_pipeline_variables(
    project_id: int, pipeline_id: int, session: aiohttp.ClientSession
):
    full_pipeline_url = f"{config.GITLAB_API_URL}/projects/{project_id}/pipelines/{pipeline_id}/variables"

    async with session.get(full_pipeline_url, headers=_default_headers) as resp:
        resp.raise_for_status()
        data = await resp.json()

    output = {}
    for item in data:
        output[item["key"]] = item["value"]

    return output


async def get_project(project_id: int, session: aiohttp.ClientSession):
    full_pipeline_url = f"{config.GITLAB_API_URL}/projects/{project_id}"

    async with session.get(full_pipeline_url, headers=_default_headers) as resp:
        resp.raise_for_status()
        return await resp.json()


async def cancel_pipelines_if_redundant(gl: GitLabAPI, head_ref: str, clone_url: str):
    logger.debug("Checking for redundant pipelines")
    for scope in ["running", "pending"]:
        async for pipeline in gl.getiter(
            f"/projects/{config.GITLAB_PROJECT_ID}/pipelines", {"scope": scope}
        ):
            variables = {}
            for item in await gl.getitem(
                f"/projects/{config.GITLAB_PROJECT_ID}/pipelines/{pipeline['id']}/variables"
            ):
                variables[item["key"]] = item["value"]

            if (
                variables["HEAD_REF"] == head_ref
                and variables["CLONE_URL"] == clone_url
            ):
                logger.debug(
                    "Cancel pipeline %d for %s on %s",
                    pipeline["id"],
                    head_ref,
                    clone_url,
                )
                if not config.STERILE:
                    await gl.post(
                        f"/projects/{config.GITLAB_PROJECT_ID}/pipelines/{pipeline['id']}/cancel",
                        data=None,
                    )


async def trigger_pipeline(
    gh: GitHubAPI,
    session: aiohttp.ClientSession,
    head_sha: str,
    repo_url: str,
    repo_slug: str,
    installation_id: int,
    clone_url: str,
    head_ref: str,
):
    if config.STERILE:
        logger.debug("Sterile mode: skipping pipeline trigger")
        return

    logger.debug(
        "Getting url for CI config from %s",
        f"{repo_url}/contents/.gitlab-ci.yml?ref={head_sha}",
    )

    ci_config_file = await gh.getitem(
        f"{repo_url}/contents/.gitlab-ci.yml?ref={head_sha}"
    )

    data = PipelineTriggerData(
        installation_id=installation_id,
        repo_url=repo_url,
        repo_slug=repo_slug,
        head_sha=head_sha,
        config_url=ci_config_file["download_url"],
        clone_url=clone_url,
        head_ref=head_ref,
    )
    payload = json.dumps(data.model_dump())

    signature = Signature().create(payload)

    logger.debug("Triggering pipeline on gitlab")
    async with session.post(
        config.GITLAB_TRIGGER_URL,
        data={
            "token": config.GITLAB_PIPELINE_TRIGGER_TOKEN,
            "ref": "main",
            "variables[BRIDGE_PAYLOAD]": payload,
            "variables[TRIGGER_SIGNATURE]": signature,
            "variables[CONFIG_URL]": data.config_url,
            "variables[CLONE_URL]": clone_url,
            "variables[REPO_SLUG]": repo_slug,
            "variables[HEAD_SHA]": head_sha,
            "variables[HEAD_REF]": head_ref,
        },
    ) as resp:
        if resp.status == 422:
            info = await resp.json()
            message = "Unknown error"
            try:
                message = info["message"]["base"]
            except KeyError:
                pass
            logger.debug("Pipeline was not created: %s", message)
            from ci_relay.github.utils import add_failure_status

            await add_failure_status(
                gh, head_sha=head_sha, repo_url=repo_url, message=message
            )
        else:
            resp.raise_for_status()
            logger.debug("Triggered pipeline on gitlab")
