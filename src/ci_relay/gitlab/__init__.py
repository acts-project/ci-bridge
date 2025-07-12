import re
import json
import aiohttp
from gidgetlab.abc import GitLabAPI
from gidgethub.abc import GitHubAPI
from sanic.log import logger

from ci_relay.config import Config
from ci_relay.gitlab.models import PipelineTriggerData
from ci_relay.signature import Signature


class GitLab:
    def __init__(self, session: aiohttp.ClientSession, gl: GitLabAPI, config: Config):
        self.session = session
        self.gl = gl
        self._headers = {"Private-Token": config.GITLAB_ACCESS_TOKEN}
        self._ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/ ]*[@-~])")
        self.config = config

    def get_pipeline_url(self, project_id: int, pipeline_id: int) -> str:
        return f"{self.config.GITLAB_API_URL}/projects/{project_id}/pipelines/{pipeline_id}"

    def get_job_url(self, project_id: int, job_id: int) -> str:
        return f"{self.config.GITLAB_API_URL}/projects/{project_id}/jobs/{job_id}"

    async def get_pipeline(self, project_id: int, pipeline_id: int):
        full_pipeline_url = self.get_pipeline_url(project_id, pipeline_id)
        async with self.session.get(full_pipeline_url, headers=self._headers) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_job(self, project_id: int, job_id: int):
        async with self.session.get(
            self.get_job_url(project_id, job_id), headers=self._headers
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_job_log(self, project_id: int, job_id: int) -> str:
        async with self.session.get(
            self.get_job_url(project_id, job_id) + "/trace", headers=self._headers
        ) as resp:
            resp.raise_for_status()
            text = await resp.text()
        return self._ansi_escape.sub("", text)

    async def get_pipeline_variables(self, project_id: int, pipeline_id: int):
        full_pipeline_url = f"{self.config.GITLAB_API_URL}/projects/{project_id}/pipelines/{pipeline_id}/variables"
        async with self.session.get(full_pipeline_url, headers=self._headers) as resp:
            resp.raise_for_status()
            data = await resp.json()

        output = {}
        for item in data:
            output[item["key"]] = item["value"]
        return output

    async def get_project(self, project_id: int):
        full_pipeline_url = f"{self.config.GITLAB_API_URL}/projects/{project_id}"
        async with self.session.get(full_pipeline_url, headers=self._headers) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def cancel_pipelines_if_redundant(self, head_ref: str, clone_url: str):
        logger.debug("Checking for redundant pipelines")
        for scope in ["running", "pending"]:
            async for pipeline in self.gl.getiter(
                f"/projects/{self.config.GITLAB_PROJECT_ID}/pipelines", {"scope": scope}
            ):
                variables = {}
                for item in await self.gl.getitem(
                    f"/projects/{self.config.GITLAB_PROJECT_ID}/pipelines/{pipeline['id']}/variables"
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
                    if not self.config.STERILE:
                        await self.gl.post(
                            f"/projects/{self.config.GITLAB_PROJECT_ID}/pipelines/{pipeline['id']}/cancel",
                            data=None,
                        )

    async def trigger_pipeline(
        self,
        gh: GitHubAPI,
        head_sha: str,
        repo_url: str,
        repo_slug: str,
        repo_name: str,
        installation_id: int,
        clone_url: str,
        clone_repo_slug: str,
        clone_repo_name: str,
        head_ref: str,
        config: Config,
    ):
        if self.config.STERILE:
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
            repo_name=repo_name,
            head_sha=head_sha,
            config_url=ci_config_file["download_url"],
            clone_url=clone_url,
            clone_repo_slug=clone_repo_slug,
            clone_repo_name=clone_repo_name,
            head_ref=head_ref,
        )
        payload = json.dumps(data.model_dump())

        signature = Signature(self.config.TRIGGER_SECRET).create(payload)

        logger.debug("Triggering pipeline on gitlab")
        print(self.session)
        async with self.session.post(
            self.config.GITLAB_TRIGGER_URL,
            data={
                "token": self.config.GITLAB_PIPELINE_TRIGGER_TOKEN,
                "ref": "main",
                "variables[BRIDGE_PAYLOAD]": payload,
                "variables[TRIGGER_SIGNATURE]": signature,
                "variables[CONFIG_URL]": data.config_url,
                "variables[CLONE_URL]": clone_url,
                "variables[REPO_SLUG]": repo_slug,
                "variables[CLONE_REPO_SLUG]": clone_repo_slug,
                "variables[REPO_NAME]": repo_name,
                "variables[CLONE_REPO_NAME]": clone_repo_name,
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
                    gh,
                    head_sha=head_sha,
                    repo_url=repo_url,
                    message=message,
                    config=config,
                )
            else:
                resp.raise_for_status()
                logger.debug("Triggered pipeline on gitlab")
