import re

import aiohttp
from gidgetlab.abc import GitLabAPI
from sanic.log import logger

from ci_relay import config

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


async def get_job(url: str, session: aiohttp.ClientSession):
    async with session.get(url, headers=_default_headers) as resp:
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
