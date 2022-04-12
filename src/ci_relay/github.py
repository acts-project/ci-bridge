import asyncio
import hmac
import io
from tracemalloc import start
from typing import Any, List, Mapping
import json
import gidgethub
import dateutil.parser
from pprint import pprint
import textwrap

from gidgethub.routing import Router
from sanic.log import logger
from sanic import Sanic
from gidgethub.abc import GitHubAPI
from gidgethub.sansio import Event
from gidgethub import BadRequest
import aiohttp

from ci_relay import config, gitlab


def create_router():
    router = Router()

    @router.register("pull_request")
    async def on_pr(event: Event, gh: GitHubAPI, app: Sanic):

        pr = event.data["pull_request"]
        logger.debug("Received pull_request event on PR #%d", pr["number"])

        action = event.data["action"]
        logger.debug("Action: %s", action)

        repo_url = event.data["repository"]["url"]
        logger.debug("Repo url is %s", repo_url)

        if action not in ("synchronize", "opened", "reopened"):
            return

        return await handle_synchronize(gh, app.ctx.aiohttp_session, event.data)

    @router.register("check_run")
    async def on_check_run(event: Event, gh: GitHubAPI, app: Sanic):
        if event.data["action"] != "rerequested":
            return
        logger.debug("Received request for check rerun")
        await handle_rerequest(gh, app.ctx.aiohttp_session, event.data)

    @router.register("check_suite")
    async def on_check_suite(event: Event, gh: GitHubAPI, app: Sanic):
        if event.data["action"] not in (
            #  "requested",
            "rerequested",
        ):
            return
        await handle_check_suite(gh, app.ctx.aiohttp_session, event.data)

    @router.register("push")
    async def on_push(event: Event, gh: GitHubAPI, app: Sanic):
        logger.debug("Received push event")
        await handle_push(gh, app.ctx.aiohttp_session, event.data)

    return router


async def get_installed_repos(gh: GitHubAPI) -> List[str]:
    return await gh.getitem("/installation/repositories")


async def is_in_installed_repos(gh: GitHubAPI, repo_id: int) -> bool:
    repos = await get_installed_repos(gh)

    for repo in repos["repositories"]:
        if repo["id"] == repo_id:
            return True

    return False


async def add_rejection_status(gh: GitHubAPI, head_sha, repo_url):
    payload = {
        "name": "CI Bridge",
        "status": "completed",
        "conclusion": "neutral",
        "head_branch": "",
        "head_sha": head_sha,
        "output": {
            "title": f"Pipeline refused",
            "summary": "No pipeline was triggered for this user",
        },
    }

    logger.debug(
        "Posting check run status for sha %s to GitHub: %s",
        head_sha,
        f"{repo_url}/check-runs",
    )
    await gh.post(f"{repo_url}/check-runs", data=payload)


async def add_failure_status(gh: GitHubAPI, head_sha, repo_url):
    payload = {
        "name": "CI Bridge",
        "status": "completed",
        "conclusion": "failure",
        "head_branch": "",
        "head_sha": head_sha,
        "output": {
            "title": f"Pipeline could not be created",
            "summary": "This is likely a YAML error.",
        },
    }

    logger.debug(
        "Posting check run status for sha %s to GitHub: %s",
        head_sha,
        f"{repo_url}/check-runs",
    )
    await gh.post(f"{repo_url}/check-runs", data=payload)


async def handle_check_suite(
    gh: GitHubAPI, session: aiohttp.ClientSession, data: Mapping[str, Any]
):
    sender = data["sender"]["login"]
    org = data["organization"]["login"]
    repo_url = data["repository"]["url"]
    head_sha = data["check_suite"]["head_sha"]
    head_branch = data["check_suite"]["head_branch"]

    if data["check_suite"]["app"]["id"] != config.APP_ID:
        logger.debug("Ignoring rerequest for check suite from other app")
        return

    author_in_team = await get_author_in_team(gh, sender, org)
    logger.debug(
        "Is sender %s in team %s: %s", sender, config.ALLOW_TEAM, author_in_team
    )
    if not author_in_team:
        logger.debug("Sender is not in team, stop processing")
        await add_rejection_status(gh, head_sha=head_sha, repo_url=repo_url)
        return

    if not await is_in_installed_repos(gh, data["repository"]["id"]):
        logger.debug(
            "Repository %s is not among installed repositories",
            data["repository"]["full_name"],
        )
    else:
        logger.debug(
            "Repository %s is among installed repositories",
            data["repository"]["full_name"],
        )

    await trigger_pipeline(
        gh,
        repo_url=repo_url,
        head_sha=head_sha,
        session=session,
        clone_url=data["repository"]["clone_url"],
        installation_id=data["installation"]["id"],
    )

async def handle_push(
    gh: GitHubAPI, session: aiohttp.ClientSession, data: Mapping[str, Any]
):
    sender = data["sender"]["login"]
    org = data["organization"]["login"]
    repo_url = data["repository"]["url"]
    if repo_url.startswith("https://github.com/"):
        repo_url = f"https://api.github.com/repos/{data['repository']['full_name']}"
    head_sha = data["after"]

    for user in sender, data["pusher"]["name"]:
        user_in_team = await get_author_in_team(gh, user, org)
        logger.debug("Is user %s in team %s: %s", user, config.ALLOW_TEAM, user_in_team)
        if not user_in_team:
            logger.debug("User is not in team, stop processing")
            await add_rejection_status(gh, head_sha=head_sha, repo_url=repo_url)
            return

    if not await is_in_installed_repos(gh, data["repository"]["id"]):
        logger.debug(
            "Repository %s is not among installed repositories",
            data["repository"]["full_name"],
        )
    else:
        logger.debug(
            "Repository %s is among installed repositories",
            data["repository"]["full_name"],
        )

    await trigger_pipeline(
        gh,
        repo_url=repo_url,
        head_sha=head_sha,
        session=session,
        clone_url=data["repository"]["clone_url"],
        installation_id=data["installation"]["id"],
    )

    payload = {
        "name": "CI Bridge",
        "status": "queued",
        "head_branch": "",
        "head_sha": head_sha,
        "output": {
            "title": f"Queued on GitLab CI",
            "summary": "",
        },
    }

    logger.debug(
        "Posting check run status for sha %s to GitHub: %s",
        head_sha,
        f"{repo_url}/check-runs",
    )

    res = await gh.post(f"{repo_url}/check-runs", data=payload)


async def handle_rerequest(
    gh: GitHubAPI, session: aiohttp.ClientSession, data: Mapping[str, Any]
):
    pipeline_url = data["check_run"]["external_id"]
    if not pipeline_url.startswith(config.GITLAB_API_URL):
        raise ValueError("Incompatible external id / pipeline url")
    logger.debug("Pipeline in question is %s", pipeline_url)

    sender = data["sender"]["login"]
    org = data["organization"]["login"]

    author_in_team = await get_author_in_team(gh, sender, org)

    logger.debug(
        "Is sender %s in team %s: %s", sender, config.ALLOW_TEAM, author_in_team
    )

    if not author_in_team:
        logger.debug("Sender is not in team, stop processing")
        return

    if not await is_in_installed_repos(gh, data["repository"]["id"]):
        logger.debug(
            "Repository %s is not among installed repositories",
            data["repository"]["full_name"],
        )
    else:
        logger.debug(
            "Repository %s is among installed repositories",
            data["repository"]["full_name"],
        )

    async with session.post(
        f"{job_url}/retry",
        headers={"private-token": config.GITLAB_ACCESS_TOKEN},
    ) as resp:
        resp.raise_for_status()
        logger.debug("Job retry has been posted")


async def get_author_in_team(gh: GitHubAPI, author: str, org: str) -> bool:

    allow_org, allow_team = config.ALLOW_TEAM.split("/", 1)

    if allow_org != org:
        raise ValueError(f"Allow team {config.ALLOW_TEAM} not in org {org}")

    try:
        membership = await gh.getitem(
            f"/orgs/{org}/teams/{allow_team}/memberships/{author}"
        )
        return True
    except gidgethub.BadRequest as e:
        if e.status_code != 404:
            raise e

    return False


async def handle_synchronize(
    gh: GitHubAPI, session: aiohttp.ClientSession, data: Mapping[str, Any]
):
    pr = data["pull_request"]
    author = pr["user"]["login"]
    source_repo_login = pr["head"]["user"]["login"]
    logger.debug("PR author is %s, source repo user is %s", author, source_repo_login)
    org = data["organization"]["login"]
    logger.debug("Org is %s", org)
    logger.debug("Allow team is: %s", config.ALLOW_TEAM)

    repo_url = pr["base"]["repo"]["url"]
    head_sha = pr["head"]["sha"]

    for login, label in [(author, "author"), (source_repo_login, "source repo login")]:
        login_in_team = await get_author_in_team(gh, login, org)

        logger.debug(
            "Is %s %s in team %s: %s", label, login, config.ALLOW_TEAM, login_in_team
        )

        if not login_in_team:
            logger.debug("%s is not in team, stop processing", label)
            await add_rejection_status(gh, head_sha=head_sha, repo_url=repo_url)
            return

        logger.debug("%s is in team", label)

    await trigger_pipeline(
        gh,
        session,
        head_sha=head_sha,
        repo_url=repo_url,
        clone_url=pr["head"]["repo"]["clone_url"],
        installation_id=data["installation"]["id"],
    )


async def trigger_pipeline(
    gh, session, head_sha: str, repo_url: str, installation_id: int, clone_url: str
):
    logger.debug(
        "Getting url for CI config from %s",
        f"{repo_url}/contents/.gitlab-ci.yml?ref={head_sha}",
    )

    ci_config_file = await gh.getitem(
        f"{repo_url}/contents/.gitlab-ci.yml?ref={head_sha}"
    )

    data = {
        "installation_id": installation_id,
        "repo_url": repo_url,
        "head_sha": head_sha,
        "config_url": ci_config_file["download_url"],
    }
    payload = json.dumps(data)

    signature = hmac.new(
        config.TRIGGER_SECRET, payload.encode(), digestmod="sha512"
    ).hexdigest()

    async with session.post(
        config.GITLAB_TRIGGER_URL,
        data={
            "token": config.GITLAB_PIPELINE_TRIGGER_TOKEN,
            "ref": "main",
            "variables[BRIDGE_PAYLOAD]": payload,
            "variables[TRIGGER_SIGNATURE]": signature,
            "variables[CONFIG_URL]": data["config_url"],
            "variables[CLONE_URL]": clone_url,
            "variables[HEAD_SHA]": head_sha,
        },
    ) as resp:
        # data = await resp.json()
        if resp.status == 422:
            logger.debug("Pipeline was not created: likely yaml error")
            await add_failure_status(gh, head_sha=head_sha, repo_url=repo_url)
        else:
            resp.raise_for_status()
            logger.debug("Triggered pipeline on gitlab")


async def handle_pipeline_status(
    pipeline, job, repo_url: str, head_sha: str, project, gh: GitHubAPI, app
):
    status = job["status"]

    logger.debug("Job %d is reported as '%s'", pipeline["id"], status)


    status_map = {
        "created",
        "waiting_for_resource",
        "preparing",
        "pending",
        "running",
        "success",
        "failed",
        "canceled",
        "skipped",
        "manual",
        "scheduled",
    }

    if status in (
        "created",
        "waiting_for_resource",
        "preparing",
        "pending",
        "manual",
        "scheduled",
    ):
        check_status = "queued"
    elif status in ("running",):
        check_status = "in_progress"
    elif status in ("success", "failed", "canceled", "skipped"):
        check_status = "completed"
    else:
        raise ValueError(f"Unknown status {status}")

    logger.debug("Status: %s => %s", status, check_status)

    if status == "success":
        conclusion = "success"
    elif status == "failed":
        conclusion = "failure"
    elif status == "canceled":
        conclusion = "cancelled"
    else:
        conclusion = "neutral"

    logger.debug("Status to conclusion: %s => %s", status, conclusion)

    started_at = job["started_at"]
    completed_at = job["finished_at"]

    log = await gitlab.get_job_log(
        project["id"], job["id"], session=app.ctx.aiohttp_session
    )

    github_limit = 65535 - 200  # tolerance
    logger.debug("Log length: %d (max %d)", len(log), github_limit)

    lines = log.split("\n")

    if len(log) > github_limit:
        selected_lines = []
        size = 0
        rlines = list(reversed(lines))
        for line in rlines:
            if size + len(line) >= github_limit:
                break

            selected_lines.append(line)
            #  logger.debug("%d => %d", size, size + len(line))
            size += len(line) + 1  # +1 for newline

        log = f"Showing last {len(selected_lines)} out of {len(lines)} total lines\n\n"
        lines = list(reversed(selected_lines))
    else:
        log = ""

    raw_lines = lines
    lines = []
    for line in raw_lines:
        if len(line) > 150:
            lines.append(textwrap.fill(line, width=150))
        else:
            lines.append(line)

    log += "\n".join(lines)
    logger.debug("Log is: %d characters", len(log))

    payload = {
        "name": f"CI Bridge / {job['name']}",
        "status": check_status,
        #  "head_branch": "",
        "head_sha": head_sha,
        "output": {
            "title": f"GitLab CI: {status.upper()}",
            "summary": (
                "This check triggered job "
                f"[{project['path_with_namespace']}/{job['id']}]({job['web_url']})\n"
                "in pipeline "
                f"[{project['path_with_namespace']}/{pipeline['iid']}]({pipeline['web_url']})\n"
                f"Status: {status.upper()}\n"
                f"Created at: {job['created_at']}\n"
                f"Started at: {started_at}\n"
                f"Finished at: {completed_at}\n"
            ),
        },
        "details_url": job["web_url"],
        "external_id": gitlab.get_job_url(project["id"], job["id"]),
    }

    if status == "failed" and pipeline["yaml_errors"] is not None:
        payload["output"]["summary"] += f"\n\nError in YAML:\n{pipeline['yaml_errors']}"

    if started_at is not None:
        payload["started_at"] = started_at
    if completed_at is not None and check_status == "completed":
        payload["completed_at"] = completed_at
        payload["conclusion"] = conclusion

        payload["output"]["text"] = f"```\n{log}\n```"

    # repo_url = trigger["head"]["repo"]["url"]
    # repo_url = trigger["base"]["repo"]["url"]

    logger.debug(
        "Posting check run status for sha %s to GitHub: %s",
        head_sha,
        f"{repo_url}/check-runs",
    )

    await gh.post(f"{repo_url}/check-runs", data=payload)
