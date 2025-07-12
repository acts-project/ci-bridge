import pytest
import aiohttp
from sanic import Sanic
import pytest_asyncio
from sanic_testing import TestManager
from sanic.log import logger

from ci_relay.config import Config


@pytest.fixture
def config():
    config = Config(
        WEBHOOK_SECRET="abc",
        PRIVATE_KEY="abc",
        APP_ID=123,
        ALLOW_TEAM="test_team",
        GITLAB_ACCESS_TOKEN="abc",
        GITLAB_PIPELINE_TRIGGER_TOKEN="abc",
        GITLAB_TRIGGER_URL="abc",
        GITLAB_API_URL="abc",
        GITLAB_PROJECT_ID=123,
        TRIGGER_SECRET=b"abc",
        GITLAB_WEBHOOK_SECRET="abc",
        OVERRIDE_LOGGING="DEBUG",
        EXTRA_USERS=["test_user"],
        STERILE=False,
        GITLAB_IGNORED_JOB_PATTERNS=[],
        ENABLE_GITLAB_TO_GITHUB_TRIGGERING=False,
        GITLAB_TO_GITHUB_TRIGGER_ON_STATUS=["success", "failed"],
    )

    logger.setLevel(config.OVERRIDE_LOGGING)

    return config


@pytest.fixture(scope="function")
def app(monkeypatch, config) -> Sanic:
    """Create a Sanic app for testing."""
    from ci_relay.web import create_app

    app = create_app(config=config)
    TestManager(app)
    return app


@pytest_asyncio.fixture
async def session():
    async with aiohttp.ClientSession() as session:
        yield session
