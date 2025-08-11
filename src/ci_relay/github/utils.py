from typing import Any
import json
import textwrap

from gidgethub.abc import GitHubAPI
from gidgethub import aiohttp as gh_aiohttp
import gidgethub
import aiohttp
from gidgethub.apps import get_installation_access_token
from sanic.log import logger

from ci_relay.gitlab import GitLab
from ci_relay.exceptions import (
    SignatureMismatchError,
    TeamOrgMismatchError,
    IncompatibleJobUrlError,
)
from ci_relay.github.models import (
    PullRequestEvent,
    CheckSuiteEvent,
    PushEvent,
    IssueCommentEvent,
    PullRequest,
    ReactionCreateRequest,
    ReactionType,
    CheckRunEvent,
    CheckRunPayload,
    CheckRunOutput,
)
from ci_relay.signature import Signature
from ci_relay import utils
from ci_relay.config import Config


async def get_installed_repos(gh: GitHubAPI) -> dict[str, Any]:
    return await gh.getitem("/installation/repositories")


async def is_in_installed_repos(gh: GitHubAPI, repo_id: int) -> bool:
    repos = await get_installed_repos(gh)

    for repo in repos["repositories"]:
        if repo["id"] == repo_id:
            return True

    return False


async def add_rejection_status(gh: GitHubAPI, head_sha, repo_url, config: Config):
    payload = {
        "name": "CI Bridge",
        "status": "completed",
        "conclusion": "neutral",
        "head_branch": "",
        "head_sha": head_sha,
        "output": {
            "title": "Pipeline refused",
            "summary": "No pipeline was triggered for this user",
        },
    }

    logger.debug(
        "Posting check run status for sha %s to GitHub: %s",
        head_sha,
        f"{repo_url}/check-runs",
    )
    if not config.STERILE:
        await gh.post(f"{repo_url}/check-runs", data=payload)


async def add_failure_status(
    gh: GitHubAPI, head_sha, repo_url, message, config: Config
):
    payload = {
        "name": "CI Bridge",
        "status": "completed",
        "conclusion": "failure",
        "head_branch": "",
        "head_sha": head_sha,
        "output": {
            "title": "Pipeline could not be created",
            "summary": message,
        },
    }

    logger.debug(
        "Posting check run status for sha %s to GitHub: %s",
        head_sha,
        f"{repo_url}/check-runs",
    )
    if not config.STERILE:
        await gh.post(f"{repo_url}/check-runs", data=payload)


def make_repo_slug(full_name: str) -> str:
    return full_name.replace("/", "_")


async def handle_check_suite(
    gh: GitHubAPI,
    session: aiohttp.ClientSession,
    event: CheckSuiteEvent,
    gitlab_client: GitLab,
    config: Config,
):
    logger.debug("Handling check suite")
    sender = event.sender.login
    org = event.organization.login
    repo_url = event.repository.url
    repo_slug = make_repo_slug(event.repository.full_name)
    head_sha = event.check_suite.head_sha

    if event.check_suite.app.id != config.APP_ID:
        logger.debug("Ignoring rerequest for check suite from other app")
        return

    author_in_team = await get_author_in_team(gh, sender, org, config)
    logger.debug(
        "Is sender %s in team %s: %s", sender, config.ALLOW_TEAM, author_in_team
    )
    if not author_in_team:
        logger.debug("Sender is not in team, stop processing")
        await add_rejection_status(
            gh, head_sha=head_sha, repo_url=repo_url, config=config
        )
        return

    if not await is_in_installed_repos(gh, event.repository.id):
        logger.debug(
            "Repository %s is not among installed repositories",
            event.repository.full_name,
        )
    else:
        logger.debug(
            "Repository %s is among installed repositories",
            event.repository.full_name,
        )

    check_runs_resp = await gh.getitem(event.check_suite.check_runs_url)
    check_runs = check_runs_resp["check_runs"]
    if len(check_runs) == 0:
        logger.debug(
            "Tried to rerequest check suite without jobs, cannot determine original check suite parameters"
        )
        return

    logger.debug("Have %d check runs for suite", len(check_runs))

    job_url = check_runs[0]["external_id"]
    if job_url == "":
        logger.debug("Job does not have external url attached, can't retry")
        return

    logger.debug("Query job url %s", job_url)

    job_data = await get_gitlab_job(session, job_url, config)

    pipeline_id = job_data["pipeline"]["id"]
    project_id = job_data["pipeline"]["project_id"]

    pipeline_vars = await gitlab_client.get_pipeline_variables(project_id, pipeline_id)

    bridge_payload = pipeline_vars["BRIDGE_PAYLOAD"]
    signature = pipeline_vars["TRIGGER_SIGNATURE"]

    if not Signature(config.TRIGGER_SECRET).verify(bridge_payload, signature):
        logger.error("Signatures do not match for pipeline behind check suite")
        raise SignatureMismatchError("Signature mismatch")

    bridge_payload = json.loads(bridge_payload)

    clone_url = bridge_payload["clone_url"]
    head_sha = bridge_payload["head_sha"]
    head_ref = bridge_payload.get(
        "head_ref", ""
    )  # defaulted in case payloads without base_ref are still in flight
    clone_repo_slug = bridge_payload.get(
        "clone_repo_slug", ""
    )  # defaulted in case payloads without clone_repo_slug are still in flight
    clone_repo_name = bridge_payload.get(
        "clone_repo_name", ""
    )  # defaulted in case payloads without clone_repo_name are still in flight
    logger.debug("Clone url of previous job was: %s", clone_url)
    logger.debug("Head sha previous job was: %s", head_sha)

    await gitlab_client.cancel_pipelines_if_redundant(
        head_ref=head_ref, clone_url=clone_url
    )

    await gitlab_client.trigger_pipeline(
        gh,
        repo_url=repo_url,
        repo_slug=repo_slug,
        repo_name=event.repository.full_name,
        head_sha=head_sha,
        clone_url=clone_url,
        clone_repo_slug=clone_repo_slug,
        clone_repo_name=clone_repo_name,
        installation_id=event.installation.id,
        head_ref=head_ref,
        config=config,
    )


async def handle_push(
    gh: GitHubAPI,
    event: PushEvent,
    gitlab_client: GitLab,
    config: Config,
):
    sender = event.sender.login
    org = event.organization.login
    repo_url = event.repository.url
    repo_slug = make_repo_slug(event.repository.full_name)
    if repo_url.startswith("https://github.com/"):
        repo_url = f"https://api.github.com/repos/{event.repository.full_name}"
    head_sha = event.after

    for user in sender, event.pusher.name:
        user_in_team = await get_author_in_team(gh, user, org, config=config)
        logger.debug("Is user %s in team %s: %s", user, config.ALLOW_TEAM, user_in_team)
        if not user_in_team:
            logger.debug("User is not in team, stop processing")
            await add_rejection_status(
                gh, head_sha=head_sha, repo_url=repo_url, config=config
            )
            return

    if not await is_in_installed_repos(gh, event.repository.id):
        logger.debug(
            "Repository %s is not among installed repositories",
            event.repository.full_name,
        )
    else:
        logger.debug(
            "Repository %s is among installed repositories",
            event.repository.full_name,
        )

    head_ref = event.ref.split("/")[-1]

    await gitlab_client.cancel_pipelines_if_redundant(
        head_ref=head_ref, clone_url=event.repository.clone_url
    )

    await gitlab_client.trigger_pipeline(
        gh,
        repo_url=repo_url,
        repo_slug=repo_slug,
        repo_name=event.repository.full_name,
        head_sha=head_sha,
        clone_url=event.repository.clone_url,
        clone_repo_slug=repo_slug,
        clone_repo_name=event.repository.full_name,
        installation_id=event.installation.id,
        head_ref=head_ref,
        config=config,
    )


async def get_gitlab_job(
    session: aiohttp.ClientSession, job_url: str, config: Config
) -> dict[str, Any]:
    if not job_url.startswith(config.GITLAB_API_URL):
        raise IncompatibleJobUrlError(f"Incompatible external id / job url: {job_url}")
    logger.debug("Pipeline in question is %s", job_url)

    async with session.get(
        job_url,
        headers={"private-token": config.GITLAB_ACCESS_TOKEN},
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


async def handle_rerequest(
    gh: GitHubAPI, session: aiohttp.ClientSession, event: CheckRunEvent, config: Config
):
    job_url = event.check_run.external_id
    # This will raise an error if the job url is not valid
    await get_gitlab_job(session, job_url, config)

    sender = event.sender.login
    org = event.organization.login

    author_in_team = await get_author_in_team(gh, sender, org, config=config)

    logger.debug(
        "Is sender %s in team %s: %s", sender, config.ALLOW_TEAM, author_in_team
    )

    if not author_in_team:
        logger.debug("Sender is not in team, stop processing")
        return

    if not await is_in_installed_repos(gh, event.repository.id):
        logger.debug(
            "Repository %s is not among installed repositories",
            event.repository.full_name,
        )
    else:
        logger.debug(
            "Repository %s is among installed repositories",
            event.repository.full_name,
        )

    if not config.STERILE:
        async with session.post(
            f"{job_url}/retry",
            headers={"private-token": config.GITLAB_ACCESS_TOKEN},
        ) as resp:
            resp.raise_for_status()
            logger.debug("Job retry has been posted")


async def get_author_in_team(
    gh: GitHubAPI, author: str, org: str, config: Config
) -> bool:
    allow_org, allow_team = config.ALLOW_TEAM.split("/", 1)

    if allow_org != org:
        raise TeamOrgMismatchError(f"Allow team {config.ALLOW_TEAM} not in org {org}")

    if author == org:
        logger.debug("Author IS the org, continue")
        return True

    try:
        await gh.getitem(f"/orgs/{org}/teams/{allow_team}/memberships/{author}")
        return True
    except gidgethub.BadRequest as e:
        if e.status_code != 404:
            raise e

    if author in config.EXTRA_USERS:
        return True

    return False


async def handle_synchronize(
    gh: GitHubAPI,
    session: aiohttp.ClientSession,
    event: PullRequestEvent,
    gitlab_client: GitLab,
    config: Config,
):
    pr = event.pull_request

    if pr.draft:
        logger.debug("PR is draft, stop processing")
        return

    author = pr.user.login
    source_repo_login = pr.head.user.login
    logger.debug("PR author is %s, source repo user is %s", author, source_repo_login)
    org = event.organization.login
    logger.debug("Org is %s", org)
    logger.debug("Allow team is: %s", config.ALLOW_TEAM)

    repo_url = pr.base.repo.url
    repo_slug = make_repo_slug(pr.base.repo.full_name)
    head_sha = pr.head.sha

    for login, label in [(author, "author"), (source_repo_login, "source repo login")]:
        login_in_team = await get_author_in_team(gh, login, org, config)

        logger.debug(
            "Is %s %s in team %s: %s", label, login, config.ALLOW_TEAM, login_in_team
        )

        if not login_in_team:
            logger.debug("%s is not in team, stop processing", label)
            await add_rejection_status(
                gh, head_sha=head_sha, repo_url=repo_url, config=config
            )
            return

        logger.debug("%s is in team", label)

    await gitlab_client.cancel_pipelines_if_redundant(
        head_ref=pr.head.ref, clone_url=pr.head.repo.clone_url
    )

    await gitlab_client.trigger_pipeline(
        gh,
        head_sha=head_sha,
        repo_url=repo_url,
        repo_slug=repo_slug,
        repo_name=pr.base.repo.full_name,
        clone_url=pr.head.repo.clone_url,
        clone_repo_slug=make_repo_slug(pr.head.repo.full_name),
        clone_repo_name=pr.head.repo.full_name,
        installation_id=event.installation.id,
        head_ref=pr.head.ref,
        config=config,
    )


async def client_for_installation(app, installation_id, session: aiohttp.ClientSession):
    gh_pre = gh_aiohttp.GitHubAPI(session, __name__)
    access_token_response = await get_installation_access_token(
        gh_pre,
        installation_id=installation_id,
        app_id=app.config.APP_ID,
        private_key=app.config.PRIVATE_KEY,
    )

    token = access_token_response["token"]

    return gh_aiohttp.GitHubAPI(
        session,
        __name__,
        oauth_token=token,
        cache=app.ctx.cache,
    )


async def handle_pipeline_status(
    pipeline,
    job,
    repo_url: str,
    head_sha: str,
    project,
    gh: GitHubAPI,
    gitlab_client: GitLab,
    config: Config,
):
    status = job["status"]

    logger.debug("Job %d is reported as '%s'", pipeline["id"], status)

    check_status = utils.gitlab_to_github_status(status)

    logger.debug("Status: %s => %s", status, check_status)

    if status == "success":
        conclusion = "success"
    elif status == "failed":
        if job["allow_failure"]:
            conclusion = "neutral"
        else:
            conclusion = "failure"
    elif status == "canceled":
        conclusion = "cancelled"
    else:
        conclusion = "neutral"

    logger.debug(
        "Status to conclusion: %s => %s (allow_failure: %s)",
        status,
        conclusion,
        job["allow_failure"],
    )

    started_at = job["started_at"]
    completed_at = job["finished_at"]

    log = await gitlab_client.get_job_log(project["id"], job["id"])

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

    title = f"GitLab CI: {status.upper()}"
    if status == "failed" and job["allow_failure"]:
        title += " [allowed failure]"

    summary = (
        "This check triggered job "
        f"[{project['path_with_namespace']}/{job['id']}]({job['web_url']})\n"
        "in pipeline "
        f"[{project['path_with_namespace']}/{pipeline['iid']}]({pipeline['web_url']})\n"
        f"Status: {status.upper()}\n"
        f"Created at: {job['created_at']}\n"
        f"Started at: {started_at}\n"
        f"Finished at: {completed_at}\n"
    )

    if status == "failed" and pipeline["yaml_errors"] is not None:
        summary += f"\n\nError in YAML:\n{pipeline['yaml_errors']}"

    output = CheckRunOutput(
        title=title,
        summary=summary,
        text=(
            f"```\n{log}\n```"
            if completed_at is not None and check_status == "completed"
            else None
        ),
    )

    payload = CheckRunPayload(
        name=f"CI Bridge / {job['name']}",
        status=check_status,
        head_sha=head_sha,
        started_at=started_at,
        completed_at=(
            completed_at
            if completed_at is not None and check_status == "completed"
            else None
        ),
        conclusion=(
            conclusion
            if completed_at is not None and check_status == "completed"
            else None
        ),
        details_url=job["web_url"],
        external_id=gitlab_client.get_job_url(project["id"], job["id"]),
        output=output,
    )

    logger.debug(
        "Posting check run status for sha %s to GitHub: %s",
        head_sha,
        f"{repo_url}/check-runs",
    )

    if not config.STERILE:
        await gh.post(
            f"{repo_url}/check-runs", data=payload.model_dump(exclude_none=True)
        )


async def handle_comment(
    gh: GitHubAPI,
    session: aiohttp.ClientSession,
    event: IssueCommentEvent,
    gitlab_client: GitLab,
    config: Config,
):
    """Handle pull request comment events"""
    logger.debug("Handling comment event")
    if event.action != "created":
        logger.debug("Ignoring comment action: %s", event.action)
        return

    # Check if comment is on a PR (GitHub sends PR comments as issue_comment events)
    if event.issue.pull_request is None:
        logger.debug("Comment is not on a PR, ignoring")
        return

    # Check if commenter is in allowed team
    commenter = event.comment.user.login
    org = event.organization.login
    commenter_in_team = await get_author_in_team(gh, commenter, org, config)

    logger.debug(
        "Is commenter %s in team %s: %s",
        commenter,
        config.ALLOW_TEAM,
        commenter_in_team,
    )

    if not commenter_in_team:
        logger.debug("Commenter is not in team, stop processing")
        return

    # Check if repository is installed
    if not await is_in_installed_repos(gh, event.repository.id):
        logger.debug(
            "Repository %s is not among installed repositories",
            event.repository.full_name,
        )
        return

    # Parse comment for commands
    comment_body = event.comment.body.strip().lower()
    if comment_body in ("/rerun", "/retry"):
        logger.debug("Comment is a rerun command, handling")
        await handle_rerun_comment(gh, event, gitlab_client, config)


async def handle_rerun_comment(
    gh: GitHubAPI, event: IssueCommentEvent, gitlab_client: GitLab, config: Config
):
    # Get pull-request details from GitHub
    if event.issue.pull_request is None:
        # Should be filtered before
        logger.debug("Comment is not on a PR, ignoring")
        return
    pr_resp = await gh.getitem(event.issue.pull_request.url)
    pr = PullRequest.model_validate(pr_resp)
    logger.debug("PR is: %s", pr.number)

    # Trigger pipeline rerun
    await gitlab_client.cancel_pipelines_if_redundant(
        head_ref=pr.head.ref,
        clone_url=pr.head.repo.clone_url,
    )

    await gitlab_client.trigger_pipeline(
        gh,
        head_sha=pr.head.sha,
        repo_url=event.repository.url,
        repo_slug=make_repo_slug(event.repository.full_name),
        repo_name=event.repository.full_name,
        clone_url=pr.head.repo.clone_url,
        clone_repo_slug=make_repo_slug(pr.head.repo.full_name),
        clone_repo_name=pr.head.repo.full_name,
        installation_id=event.installation.id,
        head_ref=pr.head.ref,
        config=config,
    )

    # create a reaction to the comment
    await gh.post(
        event.comment.reactions.url,
        data=ReactionCreateRequest(content=ReactionType.rocket).model_dump(),
    )


async def has_gitlab_workflow(gh: GitHubAPI, repo: str) -> bool:
    """
    Check if a repository has a workflow that listens for gitlab-job-finished repository_dispatch events.

    Args:
        gh: Authenticated GitHub API client
        repo: Repository name in "owner/repo" format

    Returns:
        True if repository has a compatible workflow, False otherwise
    """
    try:
        # Get all workflows in the repository
        workflows_resp = await gh.getitem(f"/repos/{repo}/actions/workflows")
        workflows = workflows_resp.get("workflows", [])

        logger.debug("Found %d workflows in repository %s", len(workflows), repo)

        # Check each workflow file for repository_dispatch trigger with gitlab-job-finished type
        for workflow in workflows:
            try:
                # Get workflow content
                workflow_resp = await gh.getitem(
                    f"/repos/{repo}/contents/{workflow['path']}"
                )

                # Decode base64 content
                import base64

                content = base64.b64decode(workflow_resp["content"]).decode("utf-8")

                # Simple check for repository_dispatch and gitlab-job-finished
                # This is a basic text search, could be improved with YAML parsing
                if (
                    "repository_dispatch" in content
                    and "gitlab-job-finished" in content
                ):
                    logger.debug(
                        "Found GitLab workflow trigger in %s: %s",
                        repo,
                        workflow["path"],
                    )
                    return True

            except gidgethub.BadRequest as e:
                if e.status_code == 404:
                    logger.debug(
                        "Workflow %s not found in %s (404)",
                        workflow["path"],
                        repo,
                        exc_info=True,
                    )
                else:
                    logger.debug(
                        "Error checking workflow %s in %s: %s",
                        workflow["path"],
                        repo,
                        e,
                    )
                continue
            except Exception as e:
                logger.debug(
                    "Error checking workflow %s in %s: %s",
                    workflow["path"],
                    repo,
                    e,
                    exc_info=True,
                )
                continue

        logger.debug("No GitLab workflow triggers found in repository %s", repo)
        return False

    except Exception as e:
        logger.debug("Error checking workflows in repository %s: %s", repo, e)
        return False


async def trigger_github_workflow(
    gh: GitHubAPI,
    repo_name: str,
    gitlab_job: dict[str, Any],
    gitlab_project: dict[str, Any],
    gitlab_pipeline: dict[str, Any],
    config: Config,
):
    """
    Trigger a GitHub workflow via repository dispatch event if the repository has a compatible workflow.

    Args:
        gh: Authenticated GitHub API client (from existing installation)
        repo_name: Repository name from bridge payload in "owner/repo" format
        gitlab_job: GitLab job data
        gitlab_project: GitLab project data
        gitlab_pipeline: GitLab pipeline data
        config: Application configuration
    """
    logger.debug("Checking repository %s for GitLab workflow triggers", repo_name)

    # Check if repository has a workflow that listens for gitlab-job-finished events
    if not await has_gitlab_workflow(gh, repo_name):
        logger.debug(
            "Repository %s does not have GitLab workflow triggers, skipping", repo_name
        )
        return False

    logger.debug("Repository %s has GitLab workflow triggers, proceeding", repo_name)

    # Prepare payload for GitHub repository dispatch
    dispatch_payload = {
        "event_type": "gitlab-job-finished",
        "client_payload": {
            "job_status": gitlab_job["status"],
            "job_name": gitlab_job["name"],
            "job_id": gitlab_job["id"],
            "job_url": gitlab_job["web_url"],
            "project_name": gitlab_project["name"],
            "project_path": gitlab_project["path_with_namespace"],
            "ref": gitlab_pipeline["ref"],
            "commit_sha": gitlab_pipeline["sha"],
            "pipeline_id": gitlab_pipeline["id"],
            "pipeline_url": gitlab_pipeline["web_url"],
            "created_at": gitlab_job["created_at"],
            "started_at": gitlab_job["started_at"],
            "finished_at": gitlab_job["finished_at"],
            "allow_failure": gitlab_job["allow_failure"],
            "gitlab_project_id": gitlab_project["id"],
        },
    }

    # Send repository dispatch event
    try:
        if not config.STERILE:
            await gh.post(f"/repos/{repo_name}/dispatches", data=dispatch_payload)
            logger.info(
                "Successfully triggered GitHub workflow for repo %s (job: %s, status: %s)",
                repo_name,
                gitlab_job["name"],
                gitlab_job["status"],
            )
        else:
            logger.info(
                "STERILE mode: Would trigger GitHub workflow for repo %s (job: %s, status: %s)",
                repo_name,
                gitlab_job["name"],
                gitlab_job["status"],
            )
        return True

    except Exception as e:
        logger.error("Failed to trigger GitHub workflow for repo %s: %s", repo_name, e)
        return False
