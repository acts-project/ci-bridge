import pytest
import aiohttp
from sanic import Sanic
from ci_relay.web import create_app
import pytest_asyncio
from sanic_testing import TestManager


@pytest.fixture(scope="session")
def app() -> Sanic:
    """Create a Sanic app for testing."""
    app = create_app()
    TestManager(app)
    return app


@pytest_asyncio.fixture
async def aiohttp_session() -> aiohttp.ClientSession:
    """Create a aiohttp ClientSession for testing."""
    async with aiohttp.ClientSession() as session:
        yield session
