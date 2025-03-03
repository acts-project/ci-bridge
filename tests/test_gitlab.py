import pytest
from unittest.mock import MagicMock, AsyncMock, Mock
from gidgetlab import sansio
from sanic import Sanic

import ci_relay.gitlab.router as gitlab_router
from ci_relay.gitlab.router import router
import ci_relay.gitlab.utils as gitlab
import ci_relay.github.utils as github


@pytest.fixture
def app():
    app = Sanic("test")
    app.config.WEBHOOK_SECRET = "test_secret"
    return app


@pytest.fixture
def session():
    return AsyncMock()


@pytest.mark.asyncio
async def test_gitlab_job_hook(app, monkeypatch, aiohttp_session):
    event = sansio.Event(
        event="Job Hook",
        data={"object_kind": "build", "build_status": "success", "build_id": 123},
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    with monkeypatch.context() as m:
        on_job_mocked = AsyncMock()
        m.setattr(gitlab_router, "on_job_hook", on_job_mocked)

        await router.dispatch(
            event,
            gh=gidgethub_client,
            app=app,
            gl=gidgetlab_client,
            session=aiohttp_session,
        )
        on_job_mocked.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_pipeline_success(session, monkeypatch):
    # Mock config
    monkeypatch.setattr("ci_relay.config.STERILE", False)
    monkeypatch.setattr(
        "ci_relay.config.GITLAB_TRIGGER_URL", "http://localhost/trigger"
    )
    monkeypatch.setattr("ci_relay.config.GITLAB_PIPELINE_TRIGGER_TOKEN", "test_token")

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
    session.post = MagicMock()
    session.post.return_value = mock_response

    # Test parameters
    head_sha = "abc123"
    repo_url = "https://api.github.com/repos/test_org/test_repo"
    repo_slug = "test_org_test_repo"
    installation_id = 123
    clone_url = "https://github.com/test_org/test_repo.git"
    head_ref = "main"

    await gitlab.trigger_pipeline(
        gidgethub_client,
        session,
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
async def test_trigger_pipeline_failure(session, monkeypatch):
    # Mock config
    monkeypatch.setattr("ci_relay.config.STERILE", False)
    monkeypatch.setattr(
        "ci_relay.config.GITLAB_TRIGGER_URL", "http://localhost/trigger"
    )
    monkeypatch.setattr("ci_relay.config.GITLAB_PIPELINE_TRIGGER_TOKEN", "test_token")

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

    await gitlab.trigger_pipeline(
        gidgethub_client,
        session,
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
async def test_trigger_pipeline_sterile_mode(session, monkeypatch):
    # Mock config for sterile mode
    monkeypatch.setattr("ci_relay.config.STERILE", True)
    monkeypatch.setattr(
        "ci_relay.config.GITLAB_TRIGGER_URL", "http://localhost/trigger"
    )
    monkeypatch.setattr("ci_relay.config.GITLAB_PIPELINE_TRIGGER_TOKEN", "test_token")

    # Create mock response for GitLab trigger
    mock_response = MagicMock()
    mock_response.raise_for_status = Mock()
    mock_response.json = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None
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

    await gitlab.trigger_pipeline(
        gidgethub_client,
        session,
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
