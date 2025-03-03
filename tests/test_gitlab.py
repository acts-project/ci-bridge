import pytest
from unittest.mock import MagicMock, Mock, AsyncMock
from gidgetlab import sansio
from sanic import Sanic

import ci_relay.gitlab.router as gitlab_router
from ci_relay.gitlab.router import router


@pytest.fixture
def gidgethub_client():
    mock = MagicMock()
    return mock


@pytest.fixture
def gidgetlab_client():
    mock = MagicMock()
    return mock


@pytest.fixture
def app():
    app = Sanic("test")
    app.config.WEBHOOK_SECRET = "test_secret"
    return app


@pytest.mark.asyncio
async def test_gitlab_job_hook(
    gidgethub_client, gidgetlab_client, app, monkeypatch, aiohttp_session
):
    event = sansio.Event(
        event="Job Hook",
        data={"object_kind": "build", "build_status": "success", "build_id": 123},
    )

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
