import re

import aiohttp

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
