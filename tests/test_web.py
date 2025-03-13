import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, create_autospec, ANY as MockANY
from gidgethub.sansio import Event as GitHubEvent
from gidgetlab.sansio import Event as GitLabEvent
from sanic import Sanic
import asyncio

import ci_relay.web as web
import ci_relay.github.router as github_router
import ci_relay.gitlab.router as gitlab_router


@pytest.mark.asyncio
async def test_handle_github_webhook(app, monkeypatch):
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
    client_for_installation_mock = create_autospec(
        web.github_utils.client_for_installation
    )
    client_for_installation_mock.return_value = mock_github_client
    monkeypatch.setattr(
        "ci_relay.github.utils.client_for_installation", client_for_installation_mock
    )

    # Mock GitLabAPI
    mock_gitlab_client = AsyncMock()
    monkeypatch.setattr(
        "gidgetlab.aiohttp.GitLabAPI",
        MagicMock(return_value=mock_gitlab_client),
    )

    # Mock router dispatch
    dispatch_mock = create_autospec(github_router.router.dispatch)
    monkeypatch.setattr("ci_relay.github.router.router.dispatch", dispatch_mock)

    # Call the handler
    await web.handle_github_webhook(request, app=app)

    # Verify client_for_installation was called with correct installation ID
    client_for_installation_mock.assert_called_once_with(
        app=app, installation_id=12345, session=MockANY
    )

    # Verify router dispatch was called with correct parameters
    call_args = dispatch_mock.call_args
    assert call_args[0][0] is event
    assert call_args[1]["gh"] == mock_github_client
    assert call_args[1]["app"] == app
    assert call_args[1]["gl"] == mock_gitlab_client


@pytest.mark.asyncio
async def test_handle_gitlab_webhook(app, monkeypatch):
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
    dispatch_mock = create_autospec(gitlab_router.router.dispatch)
    monkeypatch.setattr("ci_relay.gitlab.router.router.dispatch", dispatch_mock)

    # Call the handler
    await web.handle_gitlab_webhook(request, app=app)

    # Verify router dispatch was called with correct parameters
    call_args = dispatch_mock.call_args
    assert call_args[0][0] is event
    assert call_args[1]["app"] == app
    assert call_args[1]["gl"] == mock_gitlab_client


@pytest.mark.asyncio
async def test_webhook_endpoints(app: Sanic, monkeypatch):
    monkeypatch.setattr("ci_relay.web.get_jwt", Mock(return_value="test_token"))
    monkeypatch.setattr(app.config, "GITLAB_WEBHOOK_SECRET", "test_secret")
    monkeypatch.setattr("ci_relay.web.get_jwt", Mock(return_value="test_token"))

    mock_github_response = MagicMock()
    mock_github_response.getitem = AsyncMock(return_value={"id": 12345})
    monkeypatch.setattr(
        "gidgethub.aiohttp.GitHubAPI", MagicMock(return_value=mock_github_response)
    )

    tasks = []

    def add_task(app: Sanic, task):
        tasks.append(task)

    monkeypatch.setattr("ci_relay.web.add_task", add_task)

    payload = {"installation": {"id": 12345}}
    event = GitHubEvent(event="pull_request", data=payload, delivery_id="test")
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

    with monkeypatch.context() as m:
        dispatch_mock = create_autospec(github_router.router.dispatch)
        m.setattr(
            "ci_relay.github.router.router.dispatch",
            dispatch_mock,
        )
        # Test GitHub webhook endpoint
        _, response = await app.asgi_client.post(
            "/webhook/github",
            json=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                # "X-Hub-Signature-256": "sha256=test",
            },
        )
        assert response.status_code == 200
        await asyncio.gather(*tasks)

        dispatch_mock.assert_called_once()

    tasks = []

    with monkeypatch.context() as m:
        dispatch_mock = create_autospec(gitlab_router.router.dispatch)
        m.setattr("ci_relay.gitlab.router.router.dispatch", dispatch_mock)
        # Test GitLab webhook endpoint
        _, response = await app.asgi_client.post(
            "/webhook/gitlab",
            json={"object_kind": "build", "build_status": "success"},
            headers={"X-Gitlab-Event": "Job Hook", "X-Gitlab-Token": "test_secret"},
        )
        assert response.status_code == 200

        await asyncio.gather(*tasks)

        dispatch_mock.assert_called_once()

    tasks = []

    with monkeypatch.context() as m:
        handle_github_webhook_mock = create_autospec(web.handle_github_webhook)
        m.setattr("ci_relay.web.handle_github_webhook", handle_github_webhook_mock)
        handle_gitlab_webhook_mock = create_autospec(web.handle_gitlab_webhook)
        m.setattr(
            "ci_relay.web.handle_gitlab_webhook",
            handle_gitlab_webhook_mock,
        )

        # Test compatibility endpoint with GitLab event
        _, response = await app.asgi_client.post(
            "/webhook",
            json={"object_kind": "build", "build_status": "success"},
            headers={"X-Gitlab-Event": "Job Hook", "X-Gitlab-Token": "test_secret"},
        )
        assert response.status_code == 200

        await asyncio.gather(*tasks)

        handle_gitlab_webhook_mock.assert_called_once()

        tasks = []

        # Test compatibility endpoint with GitHub event
        _, response = await app.asgi_client.post(
            "/webhook",
            json={"installation": {"id": 12345}},
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=test",
            },
        )
        assert response.status_code == 200

        await asyncio.gather(*tasks)

        handle_github_webhook_mock.assert_called_once()


def test_health_check(app, monkeypatch):
    # Mock config
    monkeypatch.setattr("ci_relay.web.get_jwt", Mock(return_value="test_token"))

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
    _, response = app.test_client.get("/health")
    assert response.status_code == 200
    assert "GitHub: ok" in response.text
    assert "GitLab: ok" in response.text
