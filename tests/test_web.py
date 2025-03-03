import pytest
from unittest.mock import AsyncMock, MagicMock
from gidgethub.sansio import Event as GitHubEvent
from gidgetlab.sansio import Event as GitLabEvent

import ci_relay.web as web
import ci_relay.github.router as github_router
import ci_relay.gitlab.router as gitlab_router


@pytest.mark.asyncio
async def test_handle_github_webhook(app, monkeypatch):
    # Mock config
    monkeypatch.setattr("ci_relay.config.WEBHOOK_SECRET", "test_secret")
    monkeypatch.setattr("ci_relay.config.GITLAB_ACCESS_TOKEN", "test_token")
    monkeypatch.setattr("ci_relay.config.GITLAB_API_URL", "http://localhost")

    # Create test data
    payload = {
        "installation": {"id": 12345},
        "action": "opened",
        "pull_request": {
            "number": 123,
            "title": "Test PR",
        },
    }

    # Create mock request
    request = MagicMock()
    request.headers = {
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": "sha256=test",
    }
    request.body = str(payload).encode()

    # Create event object
    event = GitHubEvent(event="pull_request", data=payload, delivery_id="test")

    # Mock GitHub event creation
    monkeypatch.setattr(
        GitHubEvent,
        "from_http",
        MagicMock(return_value=event),
    )

    # Mock client_for_installation
    mock_github_client = AsyncMock()
    monkeypatch.setattr(
        "ci_relay.github.utils.client_for_installation",
        AsyncMock(return_value=mock_github_client),
    )

    # Mock GitLabAPI
    mock_gitlab_client = AsyncMock()
    monkeypatch.setattr(
        "gidgetlab.aiohttp.GitLabAPI",
        MagicMock(return_value=mock_gitlab_client),
    )

    # Mock router dispatch
    monkeypatch.setattr("ci_relay.github.router.router.dispatch", AsyncMock())

    session = AsyncMock()

    # Call the handler
    await web.handle_github_webhook(request, app, session)

    # Verify client_for_installation was called with correct installation ID
    web.github_utils.client_for_installation.assert_called_once_with(
        app, 12345, session=session
    )

    # Verify router dispatch was called with correct parameters
    call_args = github_router.router.dispatch.call_args
    assert call_args[0][0] is event
    assert call_args[1]["session"] == session
    assert call_args[1]["gh"] == mock_github_client
    assert call_args[1]["app"] == app
    assert call_args[1]["gl"] == mock_gitlab_client


@pytest.mark.asyncio
async def test_handle_gitlab_webhook(app, monkeypatch):
    # Mock config
    monkeypatch.setattr("ci_relay.config.GITLAB_WEBHOOK_SECRET", "test_secret")
    monkeypatch.setattr("ci_relay.config.GITLAB_ACCESS_TOKEN", "test_token")
    monkeypatch.setattr("ci_relay.config.GITLAB_API_URL", "http://localhost")

    # Create test data
    payload = {
        "object_kind": "build",
        "build_status": "success",
        "build_id": 123,
        "project_id": 456,
        "pipeline_id": 789,
    }

    # Create mock request
    request = MagicMock()
    request.headers = {
        "X-Gitlab-Event": "Job Hook",
        "X-Gitlab-Token": "test_secret",
    }
    request.body = str(payload).encode()

    # Create event object
    event = GitLabEvent(event="Job Hook", data=payload)

    # Mock GitLab event creation
    monkeypatch.setattr(
        GitLabEvent,
        "from_http",
        MagicMock(return_value=event),
    )

    # Mock GitLab client
    mock_gitlab_client = AsyncMock()
    monkeypatch.setattr(
        "gidgetlab.aiohttp.GitLabAPI",
        MagicMock(return_value=mock_gitlab_client),
    )

    # Mock router dispatch
    monkeypatch.setattr("ci_relay.gitlab.router.router.dispatch", AsyncMock())

    session = AsyncMock()

    # Call the handler
    await web.handle_gitlab_webhook(request, app, session)

    # Verify router dispatch was called with correct parameters
    call_args = gitlab_router.router.dispatch.call_args
    assert call_args[0][0] is event
    assert call_args[1]["session"] == session
    assert call_args[1]["app"] == app
    assert call_args[1]["gl"] == mock_gitlab_client


# @pytest.mark.asyncio
def test_webhook_endpoints(app, monkeypatch):
    # Mock config
    monkeypatch.setattr("ci_relay.config.WEBHOOK_SECRET", "test_secret")
    monkeypatch.setattr("ci_relay.config.GITLAB_WEBHOOK_SECRET", "test_secret")
    monkeypatch.setattr("ci_relay.config.GITLAB_ACCESS_TOKEN", "test_token")
    monkeypatch.setattr("ci_relay.config.GITLAB_API_URL", "http://localhost")

    # Mock handlers
    monkeypatch.setattr(web, "handle_github_webhook", AsyncMock())
    monkeypatch.setattr(web, "handle_gitlab_webhook", AsyncMock())

    # Test GitHub webhook endpoint
    request, response = app.test_client.post(
        "/webhook/github",
        json={"installation": {"id": 12345}},
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=test",
        },
    )
    assert response.status_code == 200
    web.handle_github_webhook.assert_called_once()

    # Test GitLab webhook endpoint
    request, response = app.test_client.post(
        "/webhook/gitlab",
        json={"object_kind": "build", "build_status": "success"},
        headers={"X-Gitlab-Event": "Job Hook", "X-Gitlab-Token": "test_secret"},
    )
    assert response.status_code == 200
    web.handle_gitlab_webhook.assert_called_once()

    # Test compatibility endpoint with GitLab event
    request, response = app.test_client.post(
        "/webhook",
        json={"object_kind": "build", "build_status": "success"},
        headers={"X-Gitlab-Event": "Job Hook", "X-Gitlab-Token": "test_secret"},
    )
    assert response.status_code == 200
    assert web.handle_gitlab_webhook.call_count == 2

    # Test compatibility endpoint with GitHub event
    request, response = app.test_client.post(
        "/webhook",
        json={"installation": {"id": 12345}},
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=test",
        },
    )
    assert response.status_code == 200
    assert web.handle_github_webhook.call_count == 2


def test_health_check(app, monkeypatch):
    # Mock config
    monkeypatch.setattr("ci_relay.config.APP_ID", 12345)
    monkeypatch.setattr("ci_relay.config.PRIVATE_KEY", "test_key")
    monkeypatch.setattr("ci_relay.config.GITLAB_ACCESS_TOKEN", "test_token")
    monkeypatch.setattr("ci_relay.config.GITLAB_API_URL", "http://localhost")
    monkeypatch.setattr("ci_relay.config.GITLAB_PROJECT_ID", "456")

    # Mock GitHub API response
    mock_github_response = MagicMock()
    mock_github_response.getitem = AsyncMock(return_value={"id": 12345})
    monkeypatch.setattr(
        "gidgethub.aiohttp.GitHubAPI", MagicMock(return_value=mock_github_response)
    )

    # Mock GitLab API response
    mock_gitlab_response = MagicMock()
    mock_gitlab_response.getitem = AsyncMock(return_value={"id": 456})
    monkeypatch.setattr(
        "gidgetlab.aiohttp.GitLabAPI", MagicMock(return_value=mock_gitlab_response)
    )

    # Test successful health check
    request, response = app.test_client.get("/health")
    assert response.status_code == 200
    assert "GitHub: ok" in response.text
    assert "GitLab: ok" in response.text

    # Test rate limiting
    for _ in range(2):  # Make two requests in quick succession
        request, response = app.test_client.get("/health")
    assert response.status_code == 429
