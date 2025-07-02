import pytest
from unittest.mock import MagicMock, AsyncMock, create_autospec, patch
import json
import base64
from gidgetlab.sansio import Event

import ci_relay.gitlab.router as gitlab_router
import ci_relay.github.utils as github_utils
from ci_relay.gitlab import GitLab
from ci_relay.signature import Signature


class TestGitLabToGitHubTriggering:
    """Test suite for GitLab to GitHub workflow triggering functionality."""

    @pytest.mark.asyncio
    async def test_trigger_github_workflow_success(self, monkeypatch, config):
        """Test successful GitHub workflow triggering when repository has compatible workflows."""
        # Mock GitHub API client
        gh = AsyncMock()
        
        # Mock workflows list response
        workflows_response = {
            "workflows": [
                {"path": ".github/workflows/ci.yml"},
                {"path": ".github/workflows/gitlab-trigger.yml"},
            ]
        }
        gh.getitem.side_effect = [
            workflows_response,  # First call for workflows list
            {  # Second call for workflow content
                "content": base64.b64encode("""
name: GitLab Triggered
on:
  repository_dispatch:
    types: [gitlab-job-finished]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Triggered by GitLab"
                """.encode()).decode()
            }
        ]
        
        # Mock repository dispatch post
        gh.post = AsyncMock()
        
        # Test data
        repo_name = "myorg/myrepo"
        gitlab_job = {
            "id": 123,
            "name": "test-job",
            "status": "success",
            "web_url": "https://gitlab.com/project/-/jobs/123",
            "created_at": "2023-01-01T10:00:00Z",
            "started_at": "2023-01-01T10:01:00Z",
            "finished_at": "2023-01-01T10:05:00Z",
            "allow_failure": False,
        }
        gitlab_project = {
            "id": 456,
            "name": "myproject",
            "path_with_namespace": "myorg/myproject",
        }
        gitlab_pipeline = {
            "id": 789,
            "ref": "main",
            "sha": "abc123def456",
            "web_url": "https://gitlab.com/project/-/pipelines/789",
        }
        
        # Call the function
        result = await github_utils.trigger_github_workflow(
            gh=gh,
            repo_name=repo_name,
            gitlab_job=gitlab_job,
            gitlab_project=gitlab_project,
            gitlab_pipeline=gitlab_pipeline,
            config=config,
        )
        
        # Assertions
        assert result is True
        
        # Verify workflows were checked
        gh.getitem.assert_any_call("/repos/myorg/myrepo/actions/workflows")
        gh.getitem.assert_any_call("/repos/myorg/myrepo/contents/.github/workflows/ci.yml")
        
        # Verify repository dispatch was called
        gh.post.assert_called_once()
        call_args = gh.post.call_args
        assert call_args[0][0] == "/repos/myorg/myrepo/dispatches"
        
        # Verify payload structure
        payload = call_args[1]["data"]
        assert payload["event_type"] == "gitlab-job-finished"
        client_payload = payload["client_payload"]
        assert client_payload["job_status"] == "success"
        assert client_payload["job_name"] == "test-job"
        assert client_payload["job_id"] == 123
        assert client_payload["job_url"] == "https://gitlab.com/project/-/jobs/123"
        assert client_payload["project_name"] == "myproject"
        assert client_payload["project_path"] == "myorg/myproject"
        assert client_payload["ref"] == "main"
        assert client_payload["commit_sha"] == "abc123def456"
        assert client_payload["pipeline_id"] == 789
        assert client_payload["pipeline_url"] == "https://gitlab.com/project/-/pipelines/789"
        assert client_payload["allow_failure"] is False
        assert client_payload["gitlab_project_id"] == 456

    @pytest.mark.asyncio
    async def test_trigger_github_workflow_no_compatible_workflows(self, monkeypatch, config):
        """Test that no workflow is triggered when repository has no compatible workflows."""
        # Mock GitHub API client
        gh = AsyncMock()
        
        # Mock workflows list response with no compatible workflows
        workflows_response = {
            "workflows": [
                {"path": ".github/workflows/ci.yml"},
                {"path": ".github/workflows/deploy.yml"},
            ]
        }
        gh.getitem.side_effect = [
            workflows_response,  # First call for workflows list
            {  # CI workflow without repository_dispatch
                "content": base64.b64encode("""
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
                """.encode()).decode()
            },
            {  # Deploy workflow without gitlab-job-finished
                "content": base64.b64encode("""
name: Deploy
on:
  repository_dispatch:
    types: [deploy-requested]
jobs:
  deploy:
    runs-on: ubuntu-latest
                """.encode()).decode()
            }
        ]
        
        # Mock repository dispatch post (should not be called)
        gh.post = AsyncMock()
        
        # Test data
        repo_name = "myorg/myrepo"
        gitlab_job = {"id": 123, "name": "test-job", "status": "success"}
        gitlab_project = {"id": 456, "name": "myproject"}
        gitlab_pipeline = {"id": 789, "ref": "main", "sha": "abc123"}
        
        # Call the function
        result = await github_utils.trigger_github_workflow(
            gh=gh,
            repo_name=repo_name,
            gitlab_job=gitlab_job,
            gitlab_project=gitlab_project,
            gitlab_pipeline=gitlab_pipeline,
            config=config,
        )
        
        # Assertions
        assert result is False
        
        # Verify workflows were checked
        gh.getitem.assert_any_call("/repos/myorg/myrepo/actions/workflows")
        
        # Verify no repository dispatch was called
        gh.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_github_workflow_api_error(self, monkeypatch, config):
        """Test error handling when GitHub API calls fail."""
        # Mock GitHub API client
        gh = AsyncMock()

        # Mock API error
        gh.getitem.side_effect = Exception("GitHub API error")
        
        # Test data
        repo_name = "myorg/myrepo"
        gitlab_job = {"id": 123, "name": "test-job", "status": "success"}
        gitlab_project = {"id": 456, "name": "myproject"}
        gitlab_pipeline = {"id": 789, "ref": "main", "sha": "abc123"}
        
        # Call the function
        result = await github_utils.trigger_github_workflow(
            gh=gh,
            repo_name=repo_name,
            gitlab_job=gitlab_job,
            gitlab_project=gitlab_project,
            gitlab_pipeline=gitlab_pipeline,
            config=config,
        )
        
        # Assertions
        assert result is False

    @pytest.mark.asyncio
    async def test_trigger_github_workflow_sterile_mode(self, monkeypatch, config):
        """Test that workflow triggering respects STERILE mode."""
        # Enable sterile mode
        monkeypatch.setattr(config, "STERILE", True)
        
        # Mock GitHub API client
        gh = AsyncMock()
        
        # Mock workflows list response with compatible workflow
        workflows_response = {
            "workflows": [{"path": ".github/workflows/gitlab-trigger.yml"}]
        }
        gh.getitem.side_effect = [
            workflows_response,
            {
                "content": base64.b64encode("""
name: GitLab Triggered
on:
  repository_dispatch:
    types: [gitlab-job-finished]
                """.encode()).decode()
            }
        ]
        
        # Mock repository dispatch post (should not be called in sterile mode)
        gh.post = AsyncMock()
        
        # Test data
        repo_name = "myorg/myrepo"
        gitlab_job = {
            "id": 123,
            "name": "test-job",
            "status": "success",
            "web_url": "https://gitlab.com/project/-/jobs/123",
            "created_at": "2023-01-01T10:00:00Z",
            "started_at": "2023-01-01T10:01:00Z",
            "finished_at": "2023-01-01T10:05:00Z",
            "allow_failure": False,
        }
        gitlab_project = {
            "id": 456,
            "name": "myproject",
            "path_with_namespace": "myorg/myproject",
        }
        gitlab_pipeline = {
            "id": 789,
            "ref": "main",
            "sha": "abc123def456",
            "web_url": "https://gitlab.com/project/-/pipelines/789",
        }
        
        # Call the function
        result = await github_utils.trigger_github_workflow(
            gh=gh,
            repo_name=repo_name,
            gitlab_job=gitlab_job,
            gitlab_project=gitlab_project,
            gitlab_pipeline=gitlab_pipeline,
            config=config,
        )
        
        # Assertions
        assert result is True  # Function reports success even in sterile mode
        
        # Verify workflows were still checked
        gh.getitem.assert_any_call("/repos/myorg/myrepo/actions/workflows")
        
        # Verify no actual repository dispatch was called
        gh.post.assert_not_called()



    @pytest.mark.asyncio
    async def test_has_gitlab_workflow_detection(self, monkeypatch, config):
        """Test workflow detection logic for different workflow configurations."""
        # Mock GitHub API client
        gh = AsyncMock()
        
        # Test case 1: Workflow with repository_dispatch and gitlab-job-finished
        workflows_response = {
            "workflows": [{"path": ".github/workflows/gitlab.yml"}]
        }
        gh.getitem.side_effect = [
            workflows_response,
            {
                "content": base64.b64encode("""
name: GitLab Integration
on:
  repository_dispatch:
    types: [gitlab-job-finished, other-event]
jobs:
  test:
    runs-on: ubuntu-latest
                """.encode()).decode()
            }
        ]
        
        result = await github_utils.has_gitlab_workflow(gh, "myorg/myrepo")
        assert result is True
        
        # Test case 2: Workflow with repository_dispatch but no gitlab-job-finished
        gh.getitem.side_effect = [
            workflows_response,
            {
                "content": base64.b64encode("""
name: Other Integration
on:
  repository_dispatch:
    types: [deploy-requested]
jobs:
  deploy:
    runs-on: ubuntu-latest
                """.encode()).decode()
            }
        ]
        
        result = await github_utils.has_gitlab_workflow(gh, "myorg/myrepo")
        assert result is False
        
        # Test case 3: Workflow without repository_dispatch
        gh.getitem.side_effect = [
            workflows_response,
            {
                "content": base64.b64encode("""
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
                """.encode()).decode()
            }
        ]
        
        result = await github_utils.has_gitlab_workflow(gh, "myorg/myrepo")
        assert result is False

    @pytest.mark.asyncio
    async def test_on_job_hook_with_gitlab_to_github_triggering_enabled(self, app, monkeypatch, config):
        """Test the full job hook flow with GitLab to GitHub triggering enabled."""
        # Enable GitLab to GitHub triggering
        monkeypatch.setattr(app.config, "ENABLE_GITLAB_TO_GITHUB_TRIGGERING", True)
        monkeypatch.setattr(app.config, "GITLAB_TO_GITHUB_TRIGGER_ON_STATUS", ["success", "failed"])
        
        # Create test event
        event = Event(
            event="Job Hook",
            data={
                "object_kind": "build",
                "build_status": "success",
                "build_id": 123,
                "project_id": 456,
                "pipeline_id": 789,
            },
        )

        # Mock GitLab data
        mock_pipeline = {"id": 789, "project_id": 456, "ref": "main", "sha": "abc123"}
        mock_variables = {
            "BRIDGE_PAYLOAD": json.dumps({
                "installation_id": 12345,
                "repo_url": "https://api.github.com/repos/myorg/myrepo",
                "repo_slug": "myorg_myrepo",
                "repo_name": "myorg/myrepo",
                "head_sha": "abc123",
            }),
            "TRIGGER_SIGNATURE": "valid_signature",
        }
        mock_project = {"id": 456, "path_with_namespace": "myorg/myproject"}
        mock_job = {"id": 123, "name": "test_job", "status": "success"}

        # Create GitLab client
        session = AsyncMock()
        gidgetlab_client = AsyncMock()
        gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

        # Mock GitLab client methods
        get_pipeline_mock = create_autospec(gitlab_client.get_pipeline)
        get_pipeline_mock.return_value = mock_pipeline
        monkeypatch.setattr(gitlab_client, "get_pipeline", get_pipeline_mock)

        get_pipeline_variables_mock = create_autospec(gitlab_client.get_pipeline_variables)
        get_pipeline_variables_mock.return_value = mock_variables
        monkeypatch.setattr(gitlab_client, "get_pipeline_variables", get_pipeline_variables_mock)

        get_project_mock = create_autospec(gitlab_client.get_project)
        get_project_mock.return_value = mock_project
        monkeypatch.setattr(gitlab_client, "get_project", get_project_mock)

        get_job_mock = create_autospec(gitlab_client.get_job)
        get_job_mock.return_value = mock_job
        monkeypatch.setattr(gitlab_client, "get_job", get_job_mock)

        # Mock GitHub client and existing functionality
        mock_github_client = AsyncMock()
        get_client_for_installation_mock = create_autospec(github_utils.client_for_installation)
        get_client_for_installation_mock.return_value = mock_github_client
        monkeypatch.setattr(github_utils, "client_for_installation", get_client_for_installation_mock)

        handle_pipeline_status_mock = create_autospec(github_utils.handle_pipeline_status)
        monkeypatch.setattr(github_utils, "handle_pipeline_status", handle_pipeline_status_mock)

        # Mock GitLab to GitHub workflow triggering
        trigger_github_workflow_mock = create_autospec(github_utils.trigger_github_workflow)
        trigger_github_workflow_mock.return_value = True
        monkeypatch.setattr(github_utils, "trigger_github_workflow", trigger_github_workflow_mock)

        # Mock signature verification
        signature_verify_mock = create_autospec(Signature.verify)
        signature_verify_mock.return_value = True
        monkeypatch.setattr("ci_relay.signature.Signature.verify", signature_verify_mock)

        # Call the function
        await gitlab_router.on_job_hook(event, gitlab_client, app, session)

        # Verify existing functionality was called
        handle_pipeline_status_mock.assert_called_once()

        # Verify GitLab to GitHub workflow triggering was called
        trigger_github_workflow_mock.assert_called_once_with(
            gh=mock_github_client,
            repo_name="myorg/myrepo",
            gitlab_job=mock_job,
            gitlab_project=mock_project,
            gitlab_pipeline=mock_pipeline,
            config=app.config,
        )

    @pytest.mark.asyncio
    async def test_on_job_hook_with_triggering_disabled(self, app, monkeypatch, config):
        """Test that GitLab to GitHub triggering is skipped when disabled."""
        # Disable GitLab to GitHub triggering
        monkeypatch.setattr(app.config, "ENABLE_GITLAB_TO_GITHUB_TRIGGERING", False)
        
        # Create test event
        event = Event(
            event="Job Hook",
            data={
                "object_kind": "build",
                "build_status": "success",
                "build_id": 123,
                "project_id": 456,
                "pipeline_id": 789,
            },
        )

        # Mock basic setup (minimal for this test)
        mock_pipeline = {"id": 789}
        mock_variables = {
            "BRIDGE_PAYLOAD": json.dumps({
                "installation_id": 12345,
                "repo_url": "https://api.github.com/repos/myorg/myrepo",
                "repo_slug": "myorg_myrepo",
                "head_sha": "abc123",
            }),
            "TRIGGER_SIGNATURE": "valid_signature",
        }
        mock_project = {"id": 456}
        mock_job = {"id": 123, "name": "test_job", "status": "success"}

        session = AsyncMock()
        gidgetlab_client = AsyncMock()
        gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

        # Mock GitLab client methods
        monkeypatch.setattr(gitlab_client, "get_pipeline", AsyncMock(return_value=mock_pipeline))
        monkeypatch.setattr(gitlab_client, "get_pipeline_variables", AsyncMock(return_value=mock_variables))
        monkeypatch.setattr(gitlab_client, "get_project", AsyncMock(return_value=mock_project))
        monkeypatch.setattr(gitlab_client, "get_job", AsyncMock(return_value=mock_job))

        # Mock existing functionality
        mock_github_client = AsyncMock()
        monkeypatch.setattr(github_utils, "client_for_installation", AsyncMock(return_value=mock_github_client))
        monkeypatch.setattr(github_utils, "handle_pipeline_status", AsyncMock())

        # Mock GitLab to GitHub workflow triggering (should not be called)
        trigger_github_workflow_mock = create_autospec(github_utils.trigger_github_workflow)
        monkeypatch.setattr(github_utils, "trigger_github_workflow", trigger_github_workflow_mock)

        # Mock signature verification
        monkeypatch.setattr("ci_relay.signature.Signature.verify", lambda self, payload, signature: True)

        # Call the function
        await gitlab_router.on_job_hook(event, gitlab_client, app, session)

        # Verify GitLab to GitHub workflow triggering was NOT called
        trigger_github_workflow_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_job_hook_with_non_triggering_status(self, app, monkeypatch, config):
        """Test that GitLab to GitHub triggering is skipped for non-configured job statuses."""
        # Enable GitLab to GitHub triggering but only for "success" status
        monkeypatch.setattr(app.config, "ENABLE_GITLAB_TO_GITHUB_TRIGGERING", True)
        monkeypatch.setattr(app.config, "GITLAB_TO_GITHUB_TRIGGER_ON_STATUS", ["success"])
        
        # Create test event with "running" status (not in trigger list)
        event = Event(
            event="Job Hook",
            data={
                "object_kind": "build",
                "build_status": "running",
                "build_id": 123,
                "project_id": 456,
                "pipeline_id": 789,
            },
        )

        # Mock basic setup
        mock_pipeline = {"id": 789}
        mock_variables = {
            "BRIDGE_PAYLOAD": json.dumps({
                "installation_id": 12345,
                "repo_url": "https://api.github.com/repos/myorg/myrepo",
                "repo_slug": "myorg_myrepo",
                "head_sha": "abc123",
            }),
            "TRIGGER_SIGNATURE": "valid_signature",
        }
        mock_project = {"id": 456}
        mock_job = {"id": 123, "name": "test_job", "status": "running"}  # Non-triggering status

        session = AsyncMock()
        gidgetlab_client = AsyncMock()
        gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

        # Mock GitLab client methods
        monkeypatch.setattr(gitlab_client, "get_pipeline", AsyncMock(return_value=mock_pipeline))
        monkeypatch.setattr(gitlab_client, "get_pipeline_variables", AsyncMock(return_value=mock_variables))
        monkeypatch.setattr(gitlab_client, "get_project", AsyncMock(return_value=mock_project))
        monkeypatch.setattr(gitlab_client, "get_job", AsyncMock(return_value=mock_job))

        # Mock existing functionality
        mock_github_client = AsyncMock()
        monkeypatch.setattr(github_utils, "client_for_installation", AsyncMock(return_value=mock_github_client))
        monkeypatch.setattr(github_utils, "handle_pipeline_status", AsyncMock())

        # Mock GitLab to GitHub workflow triggering (should not be called)
        trigger_github_workflow_mock = create_autospec(github_utils.trigger_github_workflow)
        monkeypatch.setattr(github_utils, "trigger_github_workflow", trigger_github_workflow_mock)

        # Mock signature verification
        monkeypatch.setattr("ci_relay.signature.Signature.verify", lambda self, payload, signature: True)

        # Call the function
        await gitlab_router.on_job_hook(event, gitlab_client, app, session)

        # Verify GitLab to GitHub workflow triggering was NOT called due to status
        trigger_github_workflow_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_github_workflow_error_handling(self, app, monkeypatch, config):
        """Test error handling in GitLab to GitHub workflow triggering."""
        # Enable GitLab to GitHub triggering
        monkeypatch.setattr(app.config, "ENABLE_GITLAB_TO_GITHUB_TRIGGERING", True)
        monkeypatch.setattr(app.config, "GITLAB_TO_GITHUB_TRIGGER_ON_STATUS", ["success"])
        
        # Create test event
        event = Event(
            event="Job Hook",
            data={
                "object_kind": "build",
                "build_status": "success",
                "build_id": 123,
                "project_id": 456,
                "pipeline_id": 789,
            },
        )

        # Mock basic setup
        mock_pipeline = {"id": 789}
        mock_variables = {
            "BRIDGE_PAYLOAD": json.dumps({
                "installation_id": 12345,
                "repo_url": "https://api.github.com/repos/myorg/myrepo",
                "repo_slug": "myorg_myrepo",
                "repo_name": "myorg/myrepo",
                "head_sha": "abc123",
            }),
            "TRIGGER_SIGNATURE": "valid_signature",
        }
        mock_project = {"id": 456}
        mock_job = {"id": 123, "name": "test_job", "status": "success"}

        session = AsyncMock()
        gidgetlab_client = AsyncMock()
        gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

        # Mock GitLab client methods
        monkeypatch.setattr(gitlab_client, "get_pipeline", AsyncMock(return_value=mock_pipeline))
        monkeypatch.setattr(gitlab_client, "get_pipeline_variables", AsyncMock(return_value=mock_variables))
        monkeypatch.setattr(gitlab_client, "get_project", AsyncMock(return_value=mock_project))
        monkeypatch.setattr(gitlab_client, "get_job", AsyncMock(return_value=mock_job))

        # Mock existing functionality
        mock_github_client = AsyncMock()
        monkeypatch.setattr(github_utils, "client_for_installation", AsyncMock(return_value=mock_github_client))
        monkeypatch.setattr(github_utils, "handle_pipeline_status", AsyncMock())

        # Mock GitLab to GitHub workflow triggering to raise an exception
        trigger_github_workflow_mock = create_autospec(github_utils.trigger_github_workflow)
        trigger_github_workflow_mock.side_effect = Exception("API Error")
        monkeypatch.setattr(github_utils, "trigger_github_workflow", trigger_github_workflow_mock)

        # Mock signature verification
        monkeypatch.setattr("ci_relay.signature.Signature.verify", lambda self, payload, signature: True)

        # Call the function - should not raise exception despite error in triggering
        await gitlab_router.on_job_hook(event, gitlab_client, app, session)

        # Verify GitLab to GitHub workflow triggering was called despite the error
        trigger_github_workflow_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_job_hook_feature_disabled_comprehensive(self, app, monkeypatch, config):
        """Comprehensive test that GitLab to GitHub triggering is completely skipped when ENABLE_GITLAB_TO_GITHUB_TRIGGERING is False."""
        # Explicitly disable GitLab to GitHub triggering
        monkeypatch.setattr(app.config, "ENABLE_GITLAB_TO_GITHUB_TRIGGERING", False)
        
        # Create test event with success status (would normally trigger)
        event = Event(
            event="Job Hook",
            data={
                "object_kind": "build",
                "build_status": "success", 
                "build_id": 123,
                "project_id": 456,
                "pipeline_id": 789,
            },
        )

        # Mock GitLab data with proper bridge payload
        mock_pipeline = {"id": 789, "project_id": 456, "ref": "main", "sha": "abc123"}
        mock_variables = {
            "BRIDGE_PAYLOAD": json.dumps({
                "installation_id": 12345,
                "repo_url": "https://api.github.com/repos/myorg/myrepo",
                "repo_slug": "myorg_myrepo",
                "repo_name": "myorg/myrepo",
                "head_sha": "abc123",
            }),
            "TRIGGER_SIGNATURE": "valid_signature",
        }
        mock_project = {"id": 456, "path_with_namespace": "myorg/myproject"}
        mock_job = {"id": 123, "name": "test_job", "status": "success"}

        # Create GitLab client
        session = AsyncMock()
        gidgetlab_client = AsyncMock()
        gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

        # Mock GitLab client methods to return proper data
        monkeypatch.setattr(gitlab_client, "get_pipeline", AsyncMock(return_value=mock_pipeline))
        monkeypatch.setattr(gitlab_client, "get_pipeline_variables", AsyncMock(return_value=mock_variables))
        monkeypatch.setattr(gitlab_client, "get_project", AsyncMock(return_value=mock_project))
        monkeypatch.setattr(gitlab_client, "get_job", AsyncMock(return_value=mock_job))

        # Mock GitHub client and existing functionality
        mock_github_client = AsyncMock()
        monkeypatch.setattr(github_utils, "client_for_installation", AsyncMock(return_value=mock_github_client))
        
        # Mock existing pipeline status handling (should still be called)
        handle_pipeline_status_mock = AsyncMock()
        monkeypatch.setattr(github_utils, "handle_pipeline_status", handle_pipeline_status_mock)

        # Mock GitLab to GitHub workflow triggering (should NOT be called)
        trigger_github_workflow_mock = create_autospec(github_utils.trigger_github_workflow)
        monkeypatch.setattr(github_utils, "trigger_github_workflow", trigger_github_workflow_mock)

        # Mock signature verification
        monkeypatch.setattr("ci_relay.signature.Signature.verify", lambda self, payload, signature: True)

        # Call the on_job_hook function directly 
        await gitlab_router.on_job_hook(event, gitlab_client, app, session)

        # Verify existing functionality was still called (the main CI Bridge functionality should work)
        handle_pipeline_status_mock.assert_called_once()

        # Verify GitLab to GitHub workflow triggering was completely skipped
        trigger_github_workflow_mock.assert_not_called()
        
        # Verify the function never even tried to access the repo_name from bridge payload
        # (by ensuring no errors were raised due to the feature being disabled)