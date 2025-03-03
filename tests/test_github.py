import pytest
from unittest.mock import MagicMock, Mock, AsyncMock

from gidgethub import sansio

import ci_relay.github.router as github_router
from ci_relay.github.router import router


@pytest.fixture
def gidgethub_client():
    mock = MagicMock()
    return mock


@pytest.fixture
def gidgetlab_client():
    mock = MagicMock()
    return mock


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
            "pull_request": {"number": 123},
            "repository": {"url": "https://github.com/owner/repo"},
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
            "pull_request": {"number": 123},
            "repository": {"url": "https://github.com/owner/repo"},
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
