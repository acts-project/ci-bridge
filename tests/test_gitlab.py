import pytest
from unittest.mock import MagicMock, AsyncMock, Mock, create_autospec, ANY as MockANY
from gidgetlab import sansio
import json
from sanic import Sanic
import asyncio
from gidgetlab.sansio import Event as GitLabEvent

import ci_relay.gitlab.router as gitlab_router
from ci_relay.gitlab.router import router
import ci_relay.github.utils as github
from ci_relay.gitlab import GitLab
from ci_relay.signature import Signature
from ci_relay.gitlab.models import PipelineTriggerData


@pytest.mark.asyncio
async def test_gitlab_job_hook(app, monkeypatch, session):
    event = sansio.Event(
        event="Job Hook",
        data={"object_kind": "build", "build_status": "success", "build_id": 123},
    )

    gidgetlab_client = AsyncMock()

    with monkeypatch.context() as m:
        on_job_mocked = create_autospec(gitlab_router.on_job_hook)
        m.setattr(gitlab_router, "on_job_hook", on_job_mocked)

        await router.dispatch(
            event,
            gl=gidgetlab_client,
            app=app,
            session=session,
        )
        on_job_mocked.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_pipeline_success(monkeypatch, config):
    gidgethub_client = AsyncMock()
    monkeypatch.setattr(config, "GITLAB_PIPELINE_TRIGGER_TOKEN", "test_token")

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

    session = MagicMock()
    session.post = MagicMock()
    session.post.return_value = mock_response

    # Test parameters
    head_sha = "abc123"
    repo_url = "https://api.github.com/repos/test_org/test_repo"
    repo_slug = "test_org_test_repo"
    installation_id = 123
    clone_url = "https://github.com/test_org/test_repo_fork.git"
    clone_repo_slug = "test_org_test_repo_fork"
    head_ref = "main"

    gidgetlab_client = AsyncMock()
    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    await gitlab_client.trigger_pipeline(
        gidgethub_client,
        head_sha=head_sha,
        repo_url=repo_url,
        repo_slug=repo_slug,
        repo_name="test_org/test_repo",
        installation_id=installation_id,
        clone_url=clone_url,
        clone_repo_slug=clone_repo_slug,
        clone_repo_name="test_org/test_repo_fork",
        head_ref=head_ref,
        config=config,
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
    payload = call_args["data"]["variables[BRIDGE_PAYLOAD]"]
    # Check this is valid JSON
    PipelineTriggerData.model_validate(json.loads(payload))
    assert "variables[TRIGGER_SIGNATURE]" in call_args["data"]
    assert (
        call_args["data"]["variables[CONFIG_URL]"]
        == "https://raw.githubusercontent.com/test_org/test_repo/main/.gitlab-ci.yml"
    )
    assert call_args["data"]["variables[CLONE_URL]"] == clone_url
    assert call_args["data"]["variables[CLONE_REPO_SLUG]"] == clone_repo_slug
    assert call_args["data"]["variables[REPO_SLUG]"] == repo_slug
    assert call_args["data"]["variables[HEAD_SHA]"] == head_sha
    assert call_args["data"]["variables[HEAD_REF]"] == head_ref


@pytest.mark.asyncio
async def test_trigger_pipeline_failure(monkeypatch, config):
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

    session = MagicMock()
    session.post = MagicMock()
    session.post.return_value = mock_response

    # Mock add_failure_status
    add_failure_status_mock = create_autospec(github.add_failure_status)
    monkeypatch.setattr(
        github,
        "add_failure_status",
        add_failure_status_mock,
    )

    # Test parameters
    head_sha = "abc123"
    repo_url = "https://api.github.com/repos/test_org/test_repo"
    repo_slug = "test_org_test_repo"
    installation_id = 123
    clone_url = "https://github.com/test_org/test_repo_fork.git"
    clone_repo_slug = "test_org_test_repo_fork"
    head_ref = "main"

    gidgetlab_client = AsyncMock()
    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    await gitlab_client.trigger_pipeline(
        gidgethub_client,
        head_sha=head_sha,
        repo_url=repo_url,
        repo_slug=repo_slug,
        repo_name="test_org/test_repo",
        installation_id=installation_id,
        clone_url=clone_url,
        clone_repo_slug=clone_repo_slug,
        clone_repo_name="test_org/test_repo_fork",
        head_ref=head_ref,
        config=config,
    )

    # Verify failure status was added
    add_failure_status_mock.assert_called_once_with(
        gidgethub_client,
        head_sha=head_sha,
        repo_url=repo_url,
        message="Invalid configuration",
        config=config,
    )


@pytest.mark.asyncio
async def test_trigger_pipeline_sterile_mode(monkeypatch, config):
    monkeypatch.setattr(config, "GITLAB_PIPELINE_TRIGGER_TOKEN", "test_token")
    monkeypatch.setattr(config, "STERILE", True)

    # Create mock response for GitLab trigger
    mock_response = MagicMock()
    mock_response.raise_for_status = Mock()
    mock_response.json = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None

    session = MagicMock()
    session.post = AsyncMock()
    session.post.return_value = mock_response

    # Test parameters
    head_sha = "abc123"
    repo_url = "https://api.github.com/repos/test_org/test_repo"
    repo_slug = "test_org_test_repo"
    installation_id = 123
    clone_url = "https://github.com/test_org/test_repo_fork.git"
    clone_repo_slug = "test_org_test_repo_fork"
    head_ref = "main"

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    await gitlab_client.trigger_pipeline(
        gidgethub_client,
        head_sha=head_sha,
        repo_url=repo_url,
        repo_slug=repo_slug,
        repo_name="test_org/test_repo",
        installation_id=installation_id,
        clone_url=clone_url,
        clone_repo_slug=clone_repo_slug,
        clone_repo_name="test_org/test_repo_fork",
        head_ref=head_ref,
        config=config,
    )

    # Verify no API calls were made in sterile mode
    gidgethub_client.getitem.assert_not_called()
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_gitlab_webhook_success(app, monkeypatch):
    # Create test data
    payload = {}

    # Create mock clients
    gidgethub_client = AsyncMock()

    # Mock the client_for_installation function
    monkeypatch.setattr(
        "ci_relay.github.utils.client_for_installation",
        AsyncMock(return_value=gidgethub_client),
    )

    # monkeypatch.setattr()

    tasks = []

    def add_task(app: Sanic, task):
        tasks.append(task)

    monkeypatch.setattr("ci_relay.web.add_task", add_task)

    event = GitLabEvent(event="Job Hook", data=payload)

    monkeypatch.setattr(
        GitLabEvent,
        "from_http",
        MagicMock(return_value=event),
    )

    # Mock on_job_hook
    with monkeypatch.context() as m:
        on_job_mocked = create_autospec(gitlab_router.on_job_hook)
        m.setattr(gitlab_router, "on_job_hook", on_job_mocked)
        m.setattr("ci_relay.web.get_jwt", AsyncMock(return_value="test_token"))

        gh = AsyncMock()
        m.setattr("gidgethub.aiohttp.GitHubAPI", Mock(return_value=gh))

        gh.getitem = AsyncMock()

        # Create test request
        headers = {
            "X-Gitlab-Token": "test_secret",
            "X-Gitlab-Event": "Job Hook",
        }

        # Call the webhook endpoint using test client
        await app.asgi_client.post(
            "/webhook/gitlab",
            json=payload,
            headers=headers,
        )

        await asyncio.gather(*tasks)

        on_job_mocked.assert_called_once()


@pytest.mark.asyncio
async def test_on_job_hook(app, monkeypatch, config):
    # Create test event
    event = sansio.Event(
        event="Job Hook",
        data={
            "object_kind": "build",
            "build_status": "success",
            "build_id": 123,
            "project_id": 456,
            "pipeline_id": 789,
        },
    )

    # Mock utility functions
    mock_pipeline = {"id": 789, "project_id": 456}
    mock_variables = {
        "BRIDGE_PAYLOAD": json.dumps(
            {
                "installation_id": 12345,
                "repo_url": "https://api.github.com/repos/test/org",
                "head_sha": "abc123",
            }
        ),
        "TRIGGER_SIGNATURE": "valid_signature",
    }
    mock_project = {"id": 456, "path_with_namespace": "test/org"}
    mock_job = {"id": 123, "name": "test_job"}

    gidgetlab_client = AsyncMock()
    session = AsyncMock()
    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    # Mock the gather results
    get_pipeline_mock = create_autospec(gitlab_client.get_pipeline)
    get_pipeline_mock.return_value = mock_pipeline
    monkeypatch.setattr(
        gitlab_client,
        "get_pipeline",
        get_pipeline_mock,
    )

    get_pipeline_variables_mock = create_autospec(gitlab_client.get_pipeline_variables)
    get_pipeline_variables_mock.return_value = mock_variables
    monkeypatch.setattr(
        gitlab_client,
        "get_pipeline_variables",
        get_pipeline_variables_mock,
    )

    get_project_mock = create_autospec(gitlab_client.get_project)
    get_project_mock.return_value = mock_project
    monkeypatch.setattr(
        gitlab_client,
        "get_project",
        get_project_mock,
    )

    get_job_mock = create_autospec(gitlab_client.get_job)
    get_job_mock.return_value = mock_job
    monkeypatch.setattr(
        gitlab_client,
        "get_job",
        get_job_mock,
    )

    # Mock handle_pipeline_status
    handle_pipeline_status_mock = create_autospec(github.handle_pipeline_status)
    monkeypatch.setattr(
        github,
        "handle_pipeline_status",
        handle_pipeline_status_mock,
    )

    # Mock client_for_installation
    mock_github_client = AsyncMock()
    get_client_for_installation_mock = create_autospec(github.client_for_installation)
    get_client_for_installation_mock.return_value = mock_github_client
    monkeypatch.setattr(
        github,
        "client_for_installation",
        get_client_for_installation_mock,
    )

    # Mock Signature verification
    signature_verify_mock = create_autospec(Signature.verify)
    signature_verify_mock.return_value = True
    monkeypatch.setattr(
        "ci_relay.signature.Signature.verify",
        signature_verify_mock,
    )

    session = AsyncMock()

    # Call the function
    await gitlab_router.on_job_hook(event, gitlab_client, app, session)

    # Verify client_for_installation was called with correct installation ID
    get_client_for_installation_mock.assert_called_once_with(app, 12345, session)

    # Verify handle_pipeline_status was called with correct parameters
    handle_pipeline_status_mock.assert_called_once_with(
        pipeline=mock_pipeline,
        job=mock_job,
        project=mock_project,
        repo_url="https://api.github.com/repos/test/org",
        head_sha="abc123",
        gh=mock_github_client,
        gitlab_client=gitlab_client,
        config=MockANY,
    )


@pytest.mark.asyncio
async def test_on_job_hook_ignores_filtered_jobs(app, monkeypatch, config):
    """Test that jobs matching ignore patterns are filtered out"""
    # Set up ignore patterns
    monkeypatch.setattr(
        app.config, "GITLAB_IGNORED_JOB_PATTERNS", ["test-.*", ".*-debug"]
    )

    # Create test event
    event = sansio.Event(
        event="Job Hook",
        data={
            "object_kind": "build",
            "build_status": "success",
            "build_id": 123,
            "project_id": 456,
            "pipeline_id": 789,
        },
    )

    # Mock utility functions
    mock_pipeline = {"id": 789, "project_id": 456}
    mock_variables = {
        "BRIDGE_PAYLOAD": json.dumps(
            {
                "installation_id": 12345,
                "repo_url": "https://api.github.com/repos/test/org",
                "head_sha": "abc123",
            }
        ),
        "TRIGGER_SIGNATURE": "valid_signature",
    }
    mock_project = {"id": 456, "path_with_namespace": "test/org"}
    # This job name should match the ignore pattern
    mock_job = {"id": 123, "name": "test-unit"}

    gidgetlab_client = AsyncMock()
    session = AsyncMock()
    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    # Mock the gather results
    get_pipeline_mock = create_autospec(gitlab_client.get_pipeline)
    get_pipeline_mock.return_value = mock_pipeline
    monkeypatch.setattr(
        gitlab_client,
        "get_pipeline",
        get_pipeline_mock,
    )

    get_pipeline_variables_mock = create_autospec(gitlab_client.get_pipeline_variables)
    get_pipeline_variables_mock.return_value = mock_variables
    monkeypatch.setattr(
        gitlab_client,
        "get_pipeline_variables",
        get_pipeline_variables_mock,
    )

    get_project_mock = create_autospec(gitlab_client.get_project)
    get_project_mock.return_value = mock_project
    monkeypatch.setattr(
        gitlab_client,
        "get_project",
        get_project_mock,
    )

    get_job_mock = create_autospec(gitlab_client.get_job)
    get_job_mock.return_value = mock_job
    monkeypatch.setattr(
        gitlab_client,
        "get_job",
        get_job_mock,
    )

    # Mock handle_pipeline_status - this should NOT be called for ignored jobs
    handle_pipeline_status_mock = create_autospec(github.handle_pipeline_status)
    monkeypatch.setattr(
        github,
        "handle_pipeline_status",
        handle_pipeline_status_mock,
    )

    # Mock client_for_installation - this should NOT be called for ignored jobs
    mock_github_client = AsyncMock()
    get_client_for_installation_mock = create_autospec(github.client_for_installation)
    get_client_for_installation_mock.return_value = mock_github_client
    monkeypatch.setattr(
        github,
        "client_for_installation",
        get_client_for_installation_mock,
    )

    # Mock Signature verification
    signature_verify_mock = create_autospec(Signature.verify)
    signature_verify_mock.return_value = True
    monkeypatch.setattr(
        "ci_relay.signature.Signature.verify",
        signature_verify_mock,
    )

    session = AsyncMock()

    # Call the function
    await gitlab_router.on_job_hook(event, gitlab_client, app, session)

    # Verify that the job was fetched (to get the name for filtering)
    get_job_mock.assert_called_once()

    # Verify that handle_pipeline_status was NOT called (job was ignored)
    handle_pipeline_status_mock.assert_not_called()

    # Verify that client_for_installation was NOT called (job was ignored)
    get_client_for_installation_mock.assert_not_called()


@pytest.mark.asyncio
async def test_on_job_hook_processes_non_filtered_jobs(app, monkeypatch, config):
    """Test that jobs not matching ignore patterns are processed normally"""
    # Set up ignore patterns
    monkeypatch.setattr(config, "GITLAB_IGNORED_JOB_PATTERNS", ["test-.*", ".*-debug"])

    # Create test event
    event = sansio.Event(
        event="Job Hook",
        data={
            "object_kind": "build",
            "build_status": "success",
            "build_id": 123,
            "project_id": 456,
            "pipeline_id": 789,
        },
    )

    # Mock utility functions
    mock_pipeline = {"id": 789, "project_id": 456}
    mock_variables = {
        "BRIDGE_PAYLOAD": json.dumps(
            {
                "installation_id": 12345,
                "repo_url": "https://api.github.com/repos/test/org",
                "head_sha": "abc123",
            }
        ),
        "TRIGGER_SIGNATURE": "valid_signature",
    }
    mock_project = {"id": 456, "path_with_namespace": "test/org"}
    # This job name should NOT match the ignore pattern
    mock_job = {"id": 123, "name": "build-production"}

    gidgetlab_client = AsyncMock()
    session = AsyncMock()
    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    # Mock the gather results
    get_pipeline_mock = create_autospec(gitlab_client.get_pipeline)
    get_pipeline_mock.return_value = mock_pipeline
    monkeypatch.setattr(
        gitlab_client,
        "get_pipeline",
        get_pipeline_mock,
    )

    get_pipeline_variables_mock = create_autospec(gitlab_client.get_pipeline_variables)
    get_pipeline_variables_mock.return_value = mock_variables
    monkeypatch.setattr(
        gitlab_client,
        "get_pipeline_variables",
        get_pipeline_variables_mock,
    )

    get_project_mock = create_autospec(gitlab_client.get_project)
    get_project_mock.return_value = mock_project
    monkeypatch.setattr(
        gitlab_client,
        "get_project",
        get_project_mock,
    )

    get_job_mock = create_autospec(gitlab_client.get_job)
    get_job_mock.return_value = mock_job
    monkeypatch.setattr(
        gitlab_client,
        "get_job",
        get_job_mock,
    )

    # Mock handle_pipeline_status - this SHOULD be called for non-ignored jobs
    handle_pipeline_status_mock = create_autospec(github.handle_pipeline_status)
    monkeypatch.setattr(
        github,
        "handle_pipeline_status",
        handle_pipeline_status_mock,
    )

    # Mock client_for_installation - this SHOULD be called for non-ignored jobs
    mock_github_client = AsyncMock()
    get_client_for_installation_mock = create_autospec(github.client_for_installation)
    get_client_for_installation_mock.return_value = mock_github_client
    monkeypatch.setattr(
        github,
        "client_for_installation",
        get_client_for_installation_mock,
    )

    # Mock Signature verification
    signature_verify_mock = create_autospec(Signature.verify)
    signature_verify_mock.return_value = True
    monkeypatch.setattr(
        "ci_relay.signature.Signature.verify",
        signature_verify_mock,
    )

    session = AsyncMock()

    # Call the function
    await gitlab_router.on_job_hook(event, gitlab_client, app, session)

    # Verify that the job was fetched
    get_job_mock.assert_called_once()

    # Verify that client_for_installation was called with correct installation ID
    get_client_for_installation_mock.assert_called_once_with(app, 12345, session)

    # Verify that handle_pipeline_status was called with correct parameters
    handle_pipeline_status_mock.assert_called_once_with(
        pipeline=mock_pipeline,
        job=mock_job,
        project=mock_project,
        repo_url="https://api.github.com/repos/test/org",
        head_sha="abc123",
        gh=mock_github_client,
        gitlab_client=gitlab_client,
        config=MockANY,
    )
