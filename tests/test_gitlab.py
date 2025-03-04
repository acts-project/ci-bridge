import pytest
from unittest.mock import MagicMock, AsyncMock, Mock, create_autospec
from gidgetlab import sansio
import json
from sanic import Sanic
import asyncio
from gidgetlab.sansio import Event as GitLabEvent

import ci_relay.gitlab.router as gitlab_router
from ci_relay.gitlab.router import router
import ci_relay.github.utils as github
from ci_relay.gitlab import GitLab


@pytest.mark.asyncio
async def test_gitlab_job_hook(app, monkeypatch, config, session):
    event = sansio.Event(
        event="Job Hook",
        data={"object_kind": "build", "build_status": "success", "build_id": 123},
    )

    gidgetlab_client = AsyncMock()

    with monkeypatch.context() as m:
        on_job_mocked = create_autospec(gitlab_router.on_job_hook)
        m.setattr(gitlab_router, "on_job_hook", on_job_mocked)

        await router.dispatch(
            event,
            gl=gidgetlab_client,
            app=app,
            session=session,
        )
        on_job_mocked.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_pipeline_success(monkeypatch, config):
    gidgethub_client = AsyncMock()
    monkeypatch.setattr(config, "GITLAB_PIPELINE_TRIGGER_TOKEN", "test_token")

    gidgethub_client = AsyncMock()

    # Mock GitHub API response for CI config
    gidgethub_client.getitem = AsyncMock(
        return_value={
            "download_url": "https://raw.githubusercontent.com/test_org/test_repo/main/.gitlab-ci.yml"
        }
    )

    # Create mock response for GitLab trigger
    mock_response = MagicMock()
    mock_response.raise_for_status = Mock()
    mock_response.json = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None

    session = MagicMock()
    session.post = MagicMock()
    session.post.return_value = mock_response

    # Test parameters
    head_sha = "abc123"
    repo_url = "https://api.github.com/repos/test_org/test_repo"
    repo_slug = "test_org_test_repo"
    installation_id = 123
    clone_url = "https://github.com/test_org/test_repo.git"
    head_ref = "main"

    gidgetlab_client = AsyncMock()
    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    await gitlab_client.trigger_pipeline(
        gidgethub_client,
        head_sha=head_sha,
        repo_url=repo_url,
        repo_slug=repo_slug,
        installation_id=installation_id,
        clone_url=clone_url,
        head_ref=head_ref,
    )

    # Verify GitHub API was called to get CI config
    gidgethub_client.getitem.assert_called_once_with(
        f"{repo_url}/contents/.gitlab-ci.yml?ref={head_sha}"
    )

    # Verify GitLab trigger was called with correct parameters
    session.post.assert_called_once()
    call_args = session.post.call_args[1]
    assert call_args["data"]["token"] == "test_token"
    assert call_args["data"]["ref"] == "main"
    assert "variables[BRIDGE_PAYLOAD]" in call_args["data"]
    assert "variables[TRIGGER_SIGNATURE]" in call_args["data"]
    assert (
        call_args["data"]["variables[CONFIG_URL]"]
        == "https://raw.githubusercontent.com/test_org/test_repo/main/.gitlab-ci.yml"
    )
    assert call_args["data"]["variables[CLONE_URL]"] == clone_url
    assert call_args["data"]["variables[REPO_SLUG]"] == repo_slug
    assert call_args["data"]["variables[HEAD_SHA]"] == head_sha
    assert call_args["data"]["variables[HEAD_REF]"] == head_ref


@pytest.mark.asyncio
async def test_trigger_pipeline_failure(monkeypatch, config):
    gidgethub_client = AsyncMock()

    # Mock GitHub API response for CI config
    gidgethub_client.getitem = AsyncMock(
        return_value={
            "download_url": "https://raw.githubusercontent.com/test_org/test_repo/main/.gitlab-ci.yml"
        }
    )

    # Create mock response for GitLab trigger with 422 error
    mock_response = MagicMock()
    mock_response.status = 422
    mock_response.json = AsyncMock(
        return_value={"message": {"base": "Invalid configuration"}}
    )
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None

    session = MagicMock()
    session.post = MagicMock()
    session.post.return_value = mock_response

    # Mock add_failure_status
    monkeypatch.setattr(github, "add_failure_status", AsyncMock())

    # Test parameters
    head_sha = "abc123"
    repo_url = "https://api.github.com/repos/test_org/test_repo"
    repo_slug = "test_org_test_repo"
    installation_id = 123
    clone_url = "https://github.com/test_org/test_repo.git"
    head_ref = "main"

    gidgetlab_client = AsyncMock()
    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    await gitlab_client.trigger_pipeline(
        gidgethub_client,
        head_sha=head_sha,
        repo_url=repo_url,
        repo_slug=repo_slug,
        installation_id=installation_id,
        clone_url=clone_url,
        head_ref=head_ref,
    )

    # Verify failure status was added
    github.add_failure_status.assert_called_once_with(
        gidgethub_client,
        head_sha=head_sha,
        repo_url=repo_url,
        message="Invalid configuration",
    )


@pytest.mark.asyncio
async def test_trigger_pipeline_sterile_mode(monkeypatch, config):
    monkeypatch.setattr(config, "GITLAB_PIPELINE_TRIGGER_TOKEN", "test_token")
    monkeypatch.setattr(config, "STERILE", True)

    # Create mock response for GitLab trigger
    mock_response = MagicMock()
    mock_response.raise_for_status = Mock()
    mock_response.json = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None

    session = MagicMock()
    session.post = AsyncMock()
    session.post.return_value = mock_response

    # Test parameters
    head_sha = "abc123"
    repo_url = "https://api.github.com/repos/test_org/test_repo"
    repo_slug = "test_org_test_repo"
    installation_id = 123
    clone_url = "https://github.com/test_org/test_repo.git"
    head_ref = "main"

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    await gitlab_client.trigger_pipeline(
        gidgethub_client,
        head_sha=head_sha,
        repo_url=repo_url,
        repo_slug=repo_slug,
        installation_id=installation_id,
        clone_url=clone_url,
        head_ref=head_ref,
    )

    # Verify no API calls were made in sterile mode
    gidgethub_client.getitem.assert_not_called()
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_gitlab_webhook_success(app, monkeypatch):
    # Create test data
    payload = {
        # "object_kind": "build",
        # "build_status": "success",
        # "build_id": 123,
        # "project_id": 456,
        # "pipeline_id": 789,
    }

    # Create mock clients
    gidgethub_client = AsyncMock()

    # Mock the client_for_installation function
    monkeypatch.setattr(
        "ci_relay.github.utils.client_for_installation",
        AsyncMock(return_value=gidgethub_client),
    )

    tasks = []

    def add_task(app: Sanic, task):
        tasks.append(task)

    monkeypatch.setattr("ci_relay.web.add_task", add_task)

    event = GitLabEvent(event="Job Hook", data=payload)

    monkeypatch.setattr(
        GitLabEvent,
        "from_http",
        MagicMock(return_value=event),
    )

    # Mock on_job_hook
    with monkeypatch.context() as m:
        on_job_mocked = create_autospec(gitlab_router.on_job_hook)
        m.setattr(gitlab_router, "on_job_hook", on_job_mocked)
        m.setattr("ci_relay.web.get_jwt", AsyncMock(return_value="test_token"))

        gh = AsyncMock()
        m.setattr("gidgethub.aiohttp.GitHubAPI", Mock(return_value=gh))

        gh.getitem = AsyncMock()

        # Create test request
        headers = {
            "X-Gitlab-Token": "test_secret",
            "X-Gitlab-Event": "Job Hook",
        }

        # Call the webhook endpoint using test client
        await app.asgi_client.post(
            "/webhook/gitlab",
            json=payload,
            headers=headers,
        )

        await asyncio.gather(*tasks)

        on_job_mocked.assert_called_once()


@pytest.mark.asyncio
async def test_on_job_hook(app, monkeypatch, config):
    # Create test event
    event = sansio.Event(
        event="Job Hook",
        data={
            "object_kind": "build",
            "build_status": "success",
            "build_id": 123,
            "project_id": 456,
            "pipeline_id": 789,
        },
    )

    # Mock utility functions
    mock_pipeline = {"id": 789, "project_id": 456}
    mock_variables = {
        "BRIDGE_PAYLOAD": json.dumps(
            {
                "installation_id": 12345,
                "repo_url": "https://api.github.com/repos/test/org",
                "head_sha": "abc123",
            }
        ),
        "TRIGGER_SIGNATURE": "valid_signature",
    }
    mock_project = {"id": 456, "path_with_namespace": "test/org"}
    mock_job = {"id": 123, "name": "test_job"}

    gidgetlab_client = AsyncMock()
    session = AsyncMock()
    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    # Mock the gather results
    monkeypatch.setattr(
        gitlab_client,
        "get_pipeline",
        AsyncMock(return_value=mock_pipeline),
    )
    monkeypatch.setattr(
        gitlab_client,
        "get_pipeline_variables",
        AsyncMock(return_value=mock_variables),
    )
    monkeypatch.setattr(
        gitlab_client,
        "get_project",
        AsyncMock(return_value=mock_project),
    )
    monkeypatch.setattr(
        gitlab_client,
        "get_job",
        AsyncMock(return_value=mock_job),
    )

    # Mock handle_pipeline_status
    monkeypatch.setattr(
        github,
        "handle_pipeline_status",
        AsyncMock(),
    )

    # Mock client_for_installation
    mock_github_client = AsyncMock()
    monkeypatch.setattr(
        github,
        "client_for_installation",
        AsyncMock(return_value=mock_github_client),
    )

    # Mock Signature verification
    monkeypatch.setattr(
        "ci_relay.signature.Signature.verify",
        Mock(return_value=True),
    )

    session = AsyncMock()

    # Call the function
    await gitlab_router.on_job_hook(event, gitlab_client, app, session)

    # Verify client_for_installation was called with correct installation ID
    github.client_for_installation.assert_called_once_with(app, 12345, session)

    # Verify handle_pipeline_status was called with correct parameters
    github.handle_pipeline_status.assert_called_once_with(
        pipeline=mock_pipeline,
        job=mock_job,
        project=mock_project,
        repo_url="https://api.github.com/repos/test/org",
        head_sha="abc123",
        gh=mock_github_client,
        app=app,
    )
