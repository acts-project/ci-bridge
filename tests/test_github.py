import pytest
from unittest.mock import Mock, AsyncMock, create_autospec, MagicMock
from gidgethub import sansio
from contextlib import asynccontextmanager

from ci_relay.gitlab import GitLab
import ci_relay.github.router as github_router
from ci_relay.github.router import router
import ci_relay.github.utils as github
from ci_relay.github.models import (
    PullRequestEvent,
    CheckSuiteEvent,
    Sender,
    Organization,
    Repository,
    CheckSuite,
    CheckSuiteApp,
    Installation,
    PushEvent,
    Pusher,
    CheckRunEvent,
    CheckRun,
    User,
    PullRequestHead,
    PullRequestBase,
    PullRequest,
)
from ci_relay.signature import Signature
from tests.utils import AsyncIterator


@pytest.fixture
def session():
    return AsyncMock()


# Global test repository
test_repository = Repository(
    id=123,
    url="https://api.github.com/repos/test_org/test_repo",
    full_name="test_org/test_repo",
    clone_url="https://github.com/test_org/test_repo.git",
)


@pytest.mark.asyncio
async def test_handle_synchronize_draft_pr(session, monkeypatch, config):
    data = PullRequestEvent(
        pull_request=PullRequest(
            draft=True,
            user=User(login="author"),
            head=PullRequestHead(
                user=User(login="source"),
                ref="feature-branch",
                repo=test_repository,
                sha="abc123",
            ),
            base=PullRequestBase(
                ref="main",
                sha="abc123",
                repo=test_repository,
            ),
            number=123,
        ),
        organization=Organization(login="org"),
        installation=Installation(id=123),
        sender=Sender(login="sender"),
        action="synchronize",
        repository=test_repository,
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        get_author_in_team_mock.return_value = True

        m.setattr(github, "get_author_in_team", get_author_in_team_mock)
        m.setattr(
            gitlab_client,
            "cancel_pipelines_if_redundant",
            create_autospec(gitlab_client.cancel_pipelines_if_redundant),
        )
        trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
        m.setattr(
            gitlab_client,
            "trigger_pipeline",
            trigger_pipeline_mock,
        )

        await github.handle_synchronize(
            gidgethub_client, session, data, gidgetlab_client, config
        )

        # Verify no pipeline was triggered
        trigger_pipeline_mock.assert_not_called()


@pytest.mark.asyncio
async def test_handle_synchronize_author_not_in_team(session, monkeypatch, config):
    data = PullRequestEvent(
        pull_request=PullRequest(
            draft=False,
            user=User(login="author"),
            head=PullRequestHead(
                ref="feature-branch",
                repo=test_repository,
                sha="abc123",
                user=User(login="source"),
            ),
            base=PullRequestBase(
                repo=test_repository,
                ref="main",
                sha="abc123",
            ),
            number=123,
        ),
        organization=Organization(login="org"),
        installation=Installation(id=123),
        sender=Sender(login="sender"),
        action="synchronize",
        repository=test_repository,
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        get_author_in_team_mock.return_value = False
        m.setattr(github, "get_author_in_team", get_author_in_team_mock)

        add_rejection_status_mock = create_autospec(github.add_rejection_status)
        m.setattr(
            github,
            "add_rejection_status",
            add_rejection_status_mock,
        )
        cancel_pipelines_if_redundant_mock = create_autospec(
            gitlab_client.cancel_pipelines_if_redundant
        )
        m.setattr(
            gitlab_client,
            "cancel_pipelines_if_redundant",
            cancel_pipelines_if_redundant_mock,
        )
        trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
        m.setattr(
            gitlab_client,
            "trigger_pipeline",
            trigger_pipeline_mock,
        )

        await github.handle_synchronize(
            gidgethub_client, session, data, gidgetlab_client, config
        )

        # Verify rejection status was added and no pipeline was triggered
        add_rejection_status_mock.assert_called_once()
        trigger_pipeline_mock.assert_not_called()


@pytest.mark.asyncio
async def test_handle_synchronize_success(session, monkeypatch, config):
    data = PullRequestEvent(
        pull_request=PullRequest(
            draft=False,
            user=User(login="author"),
            head=PullRequestHead(
                ref="feature-branch",
                repo=test_repository,
                sha="abc123",
                user=User(login="source"),
            ),
            base=PullRequestBase(
                repo=test_repository,
                ref="main",
                sha="abc123",
            ),
            number=123,
        ),
        organization=Organization(login="org"),
        installation=Installation(id=123),
        sender=Sender(login="sender"),
        action="synchronize",
        repository=test_repository,
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        get_author_in_team_mock.return_value = True
        m.setattr(github, "get_author_in_team", get_author_in_team_mock)

        cancel_pipelines_if_redundant_mock = create_autospec(
            gitlab_client.cancel_pipelines_if_redundant
        )
        cancel_pipelines_if_redundant_mock.return_value = None
        m.setattr(
            gitlab_client,
            "cancel_pipelines_if_redundant",
            cancel_pipelines_if_redundant_mock,
        )

        trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
        m.setattr(gitlab_client, "trigger_pipeline", trigger_pipeline_mock)

        await github.handle_synchronize(
            gidgethub_client, session, data, gitlab_client, config
        )

        # Verify pipeline was triggered with correct parameters
        trigger_pipeline_mock.assert_called_once_with(
            gidgethub_client,
            head_sha="abc123",
            repo_url="https://api.github.com/repos/test_org/test_repo",
            repo_slug="test_org_test_repo",
            repo_name="test_org/test_repo",
            installation_id=123,
            clone_url="https://github.com/test_org/test_repo.git",
            clone_repo_slug="test_org_test_repo",
            clone_repo_name="test_org/test_repo",
            head_ref="feature-branch",
            config=config,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action", ["synchronize", "opened", "reopened", "ready_for_review"]
)
async def test_github_pr_webhook_allowed_actions(app, monkeypatch, action):
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
                    "repo": test_repository.model_dump(),
                    "sha": "abc123",
                },
                "base": {
                    "repo": test_repository.model_dump(),
                    "ref": "main",
                    "sha": "abc123",
                    "user": {"login": "source"},
                },
                "number": 123,
            },
            "repository": test_repository.model_dump(),
            "organization": {"login": "org"},
            "installation": {"id": 123},
            "sender": {"login": "sender"},
        },
        delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    with monkeypatch.context() as m:
        handle_sync_mocked = create_autospec(github_router.handle_synchronize)
        m.setattr(github_router, "handle_synchronize", handle_sync_mocked)

        await router.dispatch(
            event,
            app=app,
            gh=gidgethub_client,
            gl=gidgetlab_client,
            session=session,
        )
        handle_sync_mocked.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["closed", "merged", "reviewed", "labeled"])
async def test_github_pr_webhook_ignored_actions(app, monkeypatch, action):
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
                    "repo": test_repository.model_dump(),
                    "sha": "abc123",
                },
                "base": {
                    "repo": test_repository.model_dump(),
                    "ref": "main",
                    "sha": "abc123",
                    "user": {"login": "source"},
                },
                "number": 123,
            },
            "repository": test_repository.model_dump(),
            "organization": {"login": "org"},
            "installation": {"id": 123},
            "sender": {"login": "sender"},
        },
        delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    with monkeypatch.context() as m:
        handle_sync_mocked = create_autospec(github_router.handle_synchronize)
        m.setattr(github_router, "handle_synchronize", handle_sync_mocked)

        await router.dispatch(
            event,
            app=app,
            gh=gidgethub_client,
            gl=gidgetlab_client,
            session=session,
        )
        handle_sync_mocked.assert_not_called()


@pytest.mark.asyncio
async def test_github_pr_webhook_check_run_rerequested(app, monkeypatch):
    event = sansio.Event(
        event="check_run",
        data={
            "action": "rerequested",
            "check_run": {"external_id": "123"},
            "repository": test_repository.model_dump(),
            "organization": {"login": "org"},
            "installation": {"id": 123},
            "sender": {"login": "sender"},
        },
        delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    with monkeypatch.context() as m:
        handle_rerequest_mocked = create_autospec(github_router.handle_rerequest)
        m.setattr(github_router, "handle_rerequest", handle_rerequest_mocked)

        await router.dispatch(
            event, app=app, gh=gidgethub_client, gl=gidgetlab_client, session=session
        )

        handle_rerequest_mocked.assert_called_once()


@pytest.mark.asyncio
async def test_github_pr_webhook_check_run_other_action(app, monkeypatch):
    event = sansio.Event(
        event="check_run",
        data={
            "action": "other",
            "check_run": {"external_id": "123"},
            "repository": test_repository.model_dump(),
            "organization": {"login": "org"},
            "installation": {"id": 123},
            "sender": {"login": "sender"},
        },
        delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    with monkeypatch.context() as m:
        handle_rerequest_mocked = create_autospec(github_router.handle_rerequest)
        m.setattr(github_router, "handle_rerequest", handle_rerequest_mocked)

        await router.dispatch(
            event, app=app, gh=gidgethub_client, gl=gidgetlab_client, session=session
        )

        handle_rerequest_mocked.assert_not_called()


@pytest.mark.asyncio
async def test_github_on_push_success(app, monkeypatch):
    event = sansio.Event(
        event="push",
        data={
            "sender": {"login": "sender"},
            "organization": {"login": "org"},
            "repository": test_repository.model_dump(),
            "pusher": {"name": "pusher"},
            "after": "abc123",
            "ref": "refs/heads/main",
            "installation": {"id": 123},
        },
        delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    with monkeypatch.context() as m:
        handle_push_mocked = create_autospec(github_router.handle_push)
        m.setattr(github_router, "handle_push", handle_push_mocked)

        await router.dispatch(
            event, app=app, gh=gidgethub_client, gl=gidgetlab_client, session=session
        )

        handle_push_mocked.assert_called_once()


@pytest.mark.asyncio
async def test_add_rejection_status(config):
    head_sha = "abc123"
    repo_url = "https://api.github.com/repos/org/repo"

    gidgethub_client = AsyncMock()
    gidgethub_client.post = AsyncMock()

    await github.add_rejection_status(gidgethub_client, head_sha, repo_url, config)

    # Verify the post was called with correct parameters
    gidgethub_client.post.assert_called_once_with(
        f"{repo_url}/check-runs",
        data={
            "name": "CI Bridge",
            "status": "completed",
            "conclusion": "neutral",
            "head_branch": "",
            "head_sha": head_sha,
            "output": {
                "title": "Pipeline refused",
                "summary": "No pipeline was triggered for this user",
            },
        },
    )


@pytest.mark.asyncio
async def test_add_failure_status(config):
    head_sha = "abc123"
    repo_url = "https://api.github.com/repos/org/repo"
    message = "Pipeline creation failed"

    gidgethub_client = AsyncMock()
    gidgethub_client.post = AsyncMock()

    await github.add_failure_status(
        gidgethub_client, head_sha, repo_url, message, config
    )

    # Verify the post was called with correct parameters
    gidgethub_client.post.assert_called_once_with(
        f"{repo_url}/check-runs",
        data={
            "name": "CI Bridge",
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "",
            "head_sha": head_sha,
            "output": {
                "title": "Pipeline could not be created",
                "summary": message,
            },
        },
    )


@pytest.mark.asyncio
async def test_handle_check_suite_success(session, monkeypatch, config):
    # Create test data using the model
    event = CheckSuiteEvent(
        action="completed",
        sender=Sender(login="test_user"),
        organization=Organization(login="test_org"),
        repository=test_repository,
        check_suite=CheckSuite(
            id=123456,
            app=CheckSuiteApp(id=config.APP_ID),  # matching APP ID
            head_sha="abc123",
            check_runs_url="https://api.github.com/repos/test_org/test_repo/check-runs",
        ),
        installation=Installation(id=123),
    )

    # Mock responses
    check_runs_response = {
        "check_runs": [{"external_id": "/api/v4/projects/456/jobs/789"}]
    }

    job_response = {"pipeline": {"id": 101, "project_id": 456}}

    # Create a real signature for the test payload
    bridge_payload = '{"clone_url": "https://github.com/test_org/test_repo.git", "head_sha": "abc123", "head_ref": "main"}'
    signature = Signature(config.TRIGGER_SECRET).create(bridge_payload)

    pipeline_vars = {
        "BRIDGE_PAYLOAD": bridge_payload,
        "TRIGGER_SIGNATURE": signature,
    }

    # Create a mock GitHub client
    gidgethub_client = AsyncMock()
    gidgethub_client.getitem = AsyncMock(
        side_effect=[
            check_runs_response,  # For check_runs_url
            {
                "download_url": "https://raw.githubusercontent.com/test_org/test_repo/main/.gitlab-ci.yml"
            },  # For CI config
        ]
    )

    # Create a mock GitLab client with async iteration support
    gidgetlab_client = AsyncMock()
    gidgetlab_client.getiter = MagicMock(return_value=AsyncIterator([]))

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    # Mock other functions
    get_author_in_team_mock = create_autospec(github.get_author_in_team)
    get_author_in_team_mock.return_value = True
    monkeypatch.setattr(github, "get_author_in_team", get_author_in_team_mock)

    is_in_installed_repos_mock = create_autospec(github.is_in_installed_repos)
    is_in_installed_repos_mock.return_value = True
    monkeypatch.setattr(github, "is_in_installed_repos", is_in_installed_repos_mock)

    trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
    monkeypatch.setattr(gitlab_client, "trigger_pipeline", trigger_pipeline_mock)

    get_gitlab_job_mock = create_autospec(github.get_gitlab_job)
    get_gitlab_job_mock.return_value = job_response
    monkeypatch.setattr(github, "get_gitlab_job", get_gitlab_job_mock)

    get_pipeline_variables_mock = create_autospec(gitlab_client.get_pipeline_variables)
    get_pipeline_variables_mock.return_value = pipeline_vars
    monkeypatch.setattr(
        gitlab_client, "get_pipeline_variables", get_pipeline_variables_mock
    )

    await github.handle_check_suite(
        gidgethub_client, session, event, gitlab_client, config
    )

    # Verify the pipeline was triggered
    trigger_pipeline_mock.assert_called_once()
    call_args = trigger_pipeline_mock.call_args[1]
    assert call_args["head_sha"] == "abc123"
    assert call_args["repo_url"] == "https://api.github.com/repos/test_org/test_repo"
    assert call_args["repo_slug"] == "test_org_test_repo"
    assert call_args["installation_id"] == 123
    assert call_args["clone_url"] == "https://github.com/test_org/test_repo.git"
    assert call_args["head_ref"] == "main"


@pytest.mark.asyncio
async def test_handle_push_success(session, monkeypatch, config):
    # Create test data using the model
    event = PushEvent(
        sender=Sender(login="test_user"),
        organization=Organization(login="test_org"),
        repository=test_repository,
        pusher=Pusher(name="test_user"),
        after="abc123",
        ref="refs/heads/main",
        installation=Installation(id=123),
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        get_author_in_team_mock.return_value = True
        m.setattr(github, "get_author_in_team", get_author_in_team_mock)
        is_in_installed_repos_mock = create_autospec(github.is_in_installed_repos)
        is_in_installed_repos_mock.return_value = True
        m.setattr(github, "is_in_installed_repos", is_in_installed_repos_mock)
        cancel_pipelines_if_redundant_mock = create_autospec(
            gitlab_client.cancel_pipelines_if_redundant
        )
        m.setattr(
            gitlab_client,
            "cancel_pipelines_if_redundant",
            cancel_pipelines_if_redundant_mock,
        )
        trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
        m.setattr(gitlab_client, "trigger_pipeline", trigger_pipeline_mock)

        await github.handle_push(gidgethub_client, event, gitlab_client, config)

        # Verify pipeline was triggered with correct parameters
        trigger_pipeline_mock.assert_called_once_with(
            gidgethub_client,
            repo_url="https://api.github.com/repos/test_org/test_repo",
            repo_slug="test_org_test_repo",
            repo_name="test_org/test_repo",
            head_sha="abc123",
            clone_url="https://github.com/test_org/test_repo.git",
            clone_repo_slug="test_org_test_repo",
            clone_repo_name="test_org/test_repo",
            installation_id=123,
            head_ref="main",
            config=config,
        )


@pytest.mark.asyncio
async def test_handle_push_user_not_in_team(session, monkeypatch, config):
    event = PushEvent(
        sender=Sender(login="test_user"),
        organization=Organization(login="test_org"),
        repository=test_repository,
        pusher=Pusher(name="test_user"),
        after="abc123",
        ref="refs/heads/main",
        installation=Installation(id=123),
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()
    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        get_author_in_team_mock.return_value = False
        m.setattr(github, "get_author_in_team", get_author_in_team_mock)
        add_rejection_status_mock = create_autospec(github.add_rejection_status)
        m.setattr(github, "add_rejection_status", add_rejection_status_mock)
        cancel_pipelines_if_redundant_mock = create_autospec(
            gitlab_client.cancel_pipelines_if_redundant
        )
        m.setattr(
            gitlab_client,
            "cancel_pipelines_if_redundant",
            cancel_pipelines_if_redundant_mock,
        )
        trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
        m.setattr(gitlab_client, "trigger_pipeline", trigger_pipeline_mock)

        await github.handle_push(gidgethub_client, event, gitlab_client, config)

        # Verify rejection status was added and no pipeline was triggered
        add_rejection_status_mock.assert_called_once()
        trigger_pipeline_mock.assert_not_called()


@pytest.mark.asyncio
async def test_handle_rerequest_success(session, monkeypatch, config):
    # Mock GitLab config
    monkeypatch.setattr(config, "GITLAB_ACCESS_TOKEN", "test_token")

    # Create test data using the model
    event = CheckRunEvent(
        action="rerequested",
        sender=Sender(login="test_user"),
        organization=Organization(login="test_org"),
        repository=test_repository,
        check_run=CheckRun(external_id="http://localhost/api/v4/projects/456/jobs/789"),
        installation=Installation(id=123),
    )

    # Create a mock response for the post call
    mock_response = AsyncMock()
    mock_response.raise_for_status = Mock()

    # Create a mock context manager for the post call
    @asynccontextmanager
    async def mock_context():
        yield mock_response

    mock_post = Mock()
    mock_post.return_value = mock_context()

    gidgethub_client = AsyncMock()

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        get_author_in_team_mock.return_value = True
        m.setattr(github, "get_author_in_team", get_author_in_team_mock)

        is_in_installed_repos_mock = create_autospec(github.is_in_installed_repos)
        is_in_installed_repos_mock.return_value = True
        m.setattr(github, "is_in_installed_repos", is_in_installed_repos_mock)

        get_gitlab_job_mock = create_autospec(github.get_gitlab_job)
        get_gitlab_job_mock.return_value = {"id": 789}
        m.setattr(github, "get_gitlab_job", get_gitlab_job_mock)
        m.setattr(session, "post", mock_post)

        await github.handle_rerequest(gidgethub_client, session, event, config)

        # Verify job retry was posted
        mock_post.assert_called_once_with(
            "http://localhost/api/v4/projects/456/jobs/789/retry",
            headers={"private-token": "test_token"},
        )


@pytest.mark.asyncio
async def test_handle_rerequest_user_not_in_team(session, monkeypatch, config):
    # Mock GitLab config
    monkeypatch.setattr(config, "GITLAB_ACCESS_TOKEN", "test_token")

    # Create test data using the model
    event = CheckRunEvent(
        action="rerequested",
        sender=Sender(login="test_user"),
        organization=Organization(login="test_org"),
        repository=test_repository,
        check_run=CheckRun(external_id="http://localhost/api/v4/projects/456/jobs/789"),
        installation=Installation(id=123),
    )

    gidgethub_client = AsyncMock()

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        get_author_in_team_mock.return_value = False
        m.setattr(github, "get_author_in_team", get_author_in_team_mock)

        is_in_installed_repos_mock = create_autospec(github.is_in_installed_repos)
        is_in_installed_repos_mock.return_value = True
        m.setattr(github, "is_in_installed_repos", is_in_installed_repos_mock)

        get_gitlab_job_mock = create_autospec(github.get_gitlab_job)
        get_gitlab_job_mock.return_value = {"id": 789}
        m.setattr(github, "get_gitlab_job", get_gitlab_job_mock)
        m.setattr(session, "post", AsyncMock())

        await github.handle_rerequest(gidgethub_client, session, event, config)

        # Verify no job retry was posted
        session.post.assert_not_called()


@pytest.mark.asyncio
async def test_handle_rerequest_incompatible_url(session, monkeypatch, config):
    # Create test data using the model
    event = CheckRunEvent(
        action="rerequested",
        sender=Sender(login="test_user"),
        organization=Organization(login="test_org"),
        repository=test_repository,
        check_run=CheckRun(external_id="https://incompatible-url.com/jobs/789"),
        installation=Installation(id=123),
    )

    gidgethub_client = AsyncMock()

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        get_author_in_team_mock.return_value = True
        m.setattr(github, "get_author_in_team", get_author_in_team_mock)

        is_in_installed_repos_mock = create_autospec(github.is_in_installed_repos)
        is_in_installed_repos_mock.return_value = True
        m.setattr(github, "is_in_installed_repos", is_in_installed_repos_mock)

        m.setattr(
            github,
            "get_gitlab_job",
            AsyncMock(side_effect=ValueError("Incompatible external id / job url")),
        )
        m.setattr(session, "post", AsyncMock())

        with pytest.raises(ValueError, match="Incompatible external id / job url"):
            await github.handle_rerequest(gidgethub_client, session, event, config)

        # Verify no job retry was posted
        session.post.assert_not_called()


@pytest.mark.asyncio
async def test_github_on_check_suite_success(app, monkeypatch):
    event = sansio.Event(
        event="check_suite",
        data={
            "action": "rerequested",
            "sender": {"login": "sender"},
            "organization": {"login": "org"},
            "repository": test_repository.model_dump(),
            "check_suite": {
                "id": 123,
                "app": {"id": 12345},
                "head_sha": "abc123",
                "check_runs_url": "https://api.github.com/repos/test_org/test_repo/check-suites/123/check-runs",
            },
            "installation": {"id": 123},
        },
        delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    with monkeypatch.context() as m:
        handle_check_suite_mocked = create_autospec(github_router.handle_check_suite)
        m.setattr(github_router, "handle_check_suite", handle_check_suite_mocked)

        await router.dispatch(
            event, app=app, gh=gidgethub_client, gl=gidgetlab_client, session=session
        )

        handle_check_suite_mocked.assert_called_once()


@pytest.mark.asyncio
async def test_github_on_check_suite_other_action(app, monkeypatch):
    event = sansio.Event(
        event="check_suite",
        data={
            "action": "completed",  # Different action
            "sender": {"login": "sender"},
            "organization": {"login": "org"},
            "repository": test_repository.model_dump(),
            "check_suite": {
                "id": 123,
                "app": {"id": 12345},
                "head_sha": "abc123",
                "check_runs_url": "https://api.github.com/repos/test_org/test_repo/check-suites/123/check-runs",
            },
            "installation": {"id": 123},
        },
        delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    with monkeypatch.context() as m:
        handle_check_suite_mocked = create_autospec(github_router.handle_check_suite)
        m.setattr(github_router, "handle_check_suite", handle_check_suite_mocked)

        await router.dispatch(
            event, app=app, gh=gidgethub_client, gl=gidgetlab_client, session=session
        )

        handle_check_suite_mocked.assert_not_called()
