import pytest
from unittest.mock import MagicMock, Mock, AsyncMock
from gidgethub import sansio
from sanic import Sanic

import ci_relay.github.router as github_router
from ci_relay.github.router import router
import ci_relay.github.utils as github
import ci_relay.gitlab.utils as gitlab
from ci_relay.github.models import PullRequestEvent


@pytest.fixture
def gidgethub_client():
    mock = MagicMock()
    return mock


@pytest.fixture
def gidgetlab_client():
    mock = MagicMock()
    return mock


@pytest.fixture
def session():
    return AsyncMock()


@pytest.mark.asyncio
async def test_handle_synchronize_draft_pr(
    gidgethub_client, gidgetlab_client, session, monkeypatch
):
    data = PullRequestEvent(
        pull_request={
            "draft": True,
            "user": {"login": "author"},
            "head": {
                "user": {"login": "source"},
                "ref": "feature-branch",
                "repo": {
                    "url": "https://api.github.com/repos/org/repo",
                    "full_name": "org/repo",
                    "clone_url": "https://github.com/org/repo.git",
                },
                "sha": "abc123",
            },
            "base": {
                "repo": {
                    "url": "https://api.github.com/repos/org/repo",
                    "full_name": "org/repo",
                    "clone_url": "https://github.com/org/repo.git",
                }
            },
            "number": 123,
        },
        organization={"login": "org"},
        installation={"id": 123},
        sender={"login": "sender"},
        action="synchronize",
        repository={
            "url": "https://api.github.com/repos/org/repo",
            "full_name": "org/repo",
            "clone_url": "https://github.com/org/repo.git",
        },
    )

    with monkeypatch.context() as m:
        m.setattr(github, "get_author_in_team", AsyncMock(return_value=True))
        m.setattr(gitlab, "cancel_pipelines_if_redundant", AsyncMock())
        m.setattr(github, "trigger_pipeline", AsyncMock())

        await github.handle_synchronize(
            gidgethub_client, session, data, gidgetlab_client
        )

        # Verify no pipeline was triggered
        github.trigger_pipeline.assert_not_called()


@pytest.mark.asyncio
async def test_handle_synchronize_author_not_in_team(
    gidgethub_client, gidgetlab_client, session, monkeypatch
):
    data = PullRequestEvent(
        pull_request={
            "draft": False,
            "user": {"login": "author"},
            "head": {
                "user": {"login": "source"},
                "ref": "feature-branch",
                "repo": {
                    "url": "https://api.github.com/repos/org/repo",
                    "full_name": "org/repo",
                    "clone_url": "https://github.com/org/repo.git",
                },
                "sha": "abc123",
            },
            "base": {
                "repo": {
                    "url": "https://api.github.com/repos/org/repo",
                    "full_name": "org/repo",
                    "clone_url": "https://github.com/org/repo.git",
                }
            },
            "number": 123,
        },
        organization={"login": "org"},
        installation={"id": 123},
        sender={"login": "sender"},
        action="synchronize",
        repository={
            "url": "https://api.github.com/repos/org/repo",
            "full_name": "org/repo",
            "clone_url": "https://github.com/org/repo.git",
        },
    )

    with monkeypatch.context() as m:
        m.setattr(github, "get_author_in_team", AsyncMock(return_value=False))
        m.setattr(github, "add_rejection_status", AsyncMock())
        m.setattr(gitlab, "cancel_pipelines_if_redundant", AsyncMock())
        m.setattr(github, "trigger_pipeline", AsyncMock())

        await github.handle_synchronize(
            gidgethub_client, session, data, gidgetlab_client
        )

        # Verify rejection status was added and no pipeline was triggered
        github.add_rejection_status.assert_called_once()
        github.trigger_pipeline.assert_not_called()


@pytest.mark.asyncio
async def test_handle_synchronize_success(
    gidgethub_client, gidgetlab_client, session, monkeypatch
):
    data = PullRequestEvent(
        pull_request={
            "draft": False,
            "user": {"login": "author"},
            "head": {
                "user": {"login": "source"},
                "ref": "feature-branch",
                "repo": {
                    "url": "https://api.github.com/repos/org/repo",
                    "full_name": "org/repo",
                    "clone_url": "https://github.com/org/repo.git",
                },
                "sha": "abc123",
            },
            "base": {
                "repo": {
                    "url": "https://api.github.com/repos/org/repo",
                    "full_name": "org/repo",
                    "clone_url": "https://github.com/org/repo.git",
                }
            },
            "number": 123,
        },
        organization={"login": "org"},
        installation={"id": 123},
        sender={"login": "sender"},
        action="synchronize",
        repository={
            "url": "https://api.github.com/repos/org/repo",
            "full_name": "org/repo",
            "clone_url": "https://github.com/org/repo.git",
        },
    )

    with monkeypatch.context() as m:
        m.setattr(github, "get_author_in_team", AsyncMock(return_value=True))
        m.setattr(gitlab, "cancel_pipelines_if_redundant", AsyncMock())
        m.setattr(github, "trigger_pipeline", AsyncMock())

        await github.handle_synchronize(
            gidgethub_client, session, data, gidgetlab_client
        )

        # Verify pipeline was triggered with correct parameters
        github.trigger_pipeline.assert_called_once_with(
            gidgethub_client,
            session,
            head_sha="abc123",
            repo_url="https://api.github.com/repos/org/repo",
            repo_slug="org_repo",
            installation_id=123,
            clone_url="https://github.com/org/repo.git",
            head_ref="feature-branch",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action", ["synchronize", "opened", "reopened", "ready_for_review"]
)
async def test_github_pr_webhook_allowed_actions(
    gidgethub_client, gidgetlab_client, app, monkeypatch, action, aiohttp_session
):
    event = sansio.Event(
        event="pull_request",
        data={
            "action": action,
            "pull_request": {
                "draft": False,
                "user": {"login": "author"},
                "head": {
                    "user": {"login": "source"},
                    "ref": "feature-branch",
                    "repo": {
                        "url": "https://api.github.com/repos/org/repo",
                        "full_name": "org/repo",
                        "clone_url": "https://github.com/org/repo.git",
                    },
                    "sha": "abc123",
                },
                "base": {
                    "repo": {
                        "url": "https://api.github.com/repos/org/repo",
                        "full_name": "org/repo",
                        "clone_url": "https://github.com/org/repo.git",
                    }
                },
                "number": 123,
            },
            "repository": {
                "url": "https://api.github.com/repos/org/repo",
                "full_name": "org/repo",
                "clone_url": "https://github.com/org/repo.git",
            },
            "organization": {"login": "org"},
            "installation": {"id": 123},
            "sender": {"login": "sender"},
        },
        delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
    )

    with monkeypatch.context() as m:
        handle_sync_mocked = AsyncMock()
        m.setattr(github_router, "handle_synchronize", handle_sync_mocked)

        await router.dispatch(
            event,
            session=aiohttp_session,
            app=app,
            gh=gidgethub_client,
            gl=gidgetlab_client,
        )
        handle_sync_mocked.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["closed", "merged", "reviewed", "labeled"])
async def test_github_pr_webhook_ignored_actions(
    gidgethub_client, gidgetlab_client, app, monkeypatch, action, aiohttp_session
):
    event = sansio.Event(
        event="pull_request",
        data={
            "action": action,
            "pull_request": {
                "draft": False,
                "user": {"login": "author"},
                "head": {
                    "user": {"login": "source"},
                    "ref": "feature-branch",
                    "repo": {
                        "url": "https://api.github.com/repos/org/repo",
                        "full_name": "org/repo",
                        "clone_url": "https://github.com/org/repo.git",
                    },
                    "sha": "abc123",
                },
                "base": {
                    "repo": {
                        "url": "https://api.github.com/repos/org/repo",
                        "full_name": "org/repo",
                        "clone_url": "https://github.com/org/repo.git",
                    }
                },
                "number": 123,
            },
            "repository": {
                "url": "https://api.github.com/repos/org/repo",
                "full_name": "org/repo",
                "clone_url": "https://github.com/org/repo.git",
            },
            "organization": {"login": "org"},
            "installation": {"id": 123},
            "sender": {"login": "sender"},
        },
        delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
    )

    with monkeypatch.context() as m:
        handle_sync_mocked = AsyncMock()
        m.setattr(github_router, "handle_synchronize", handle_sync_mocked)

        await router.dispatch(
            event,
            session=aiohttp_session,
            app=app,
            gh=gidgethub_client,
            gl=gidgetlab_client,
        )
        handle_sync_mocked.assert_not_called()
