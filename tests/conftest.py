import pytest
import aiohttp
from sanic import Sanic
import pytest_asyncio
from sanic_testing import TestManager


@pytest.fixture(scope="function")
def app(monkeypatch) -> Sanic:
    """Create a Sanic app for testing."""
    monkeypatch.setenv("APP_ID", "123")
    from ci_relay.web import create_app

    app = create_app()
    TestManager(app)
    yield app
    app.stop()


@pytest_asyncio.fixture
async def aiohttp_session() -> aiohttp.ClientSession:
    """Create a aiohttp ClientSession for testing."""
    async with aiohttp.ClientSession() as session:
        yield session
