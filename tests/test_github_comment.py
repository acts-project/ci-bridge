import pytest
from unittest.mock import AsyncMock, create_autospec

from ci_relay.github.models import (
    IssueCommentEvent,
    Comment,
    User,
    Issue,
    IssuePullRequest,
    Organization,
    Installation,
    Sender,
    Repository,
    PullRequest,
    PullRequestHead,
    PullRequestBase,
    Reactions,
    ReactionCreateRequest,
    ReactionType,
)

from ci_relay.gitlab import GitLab
import ci_relay.github.utils as github


# Global test repository
test_repository = Repository(
    id=123,
    url="https://api.github.com/repos/test_org/test_repo",
    full_name="test_org/test_repo",
    clone_url="https://github.com/test_org/test_repo.git",
)


@pytest.mark.asyncio
async def test_handle_comment_success(session, monkeypatch, config):
    # Create test data using the model
    event = IssueCommentEvent(
        action="created",
        comment=Comment(
            id=123,
            body="/rerun",
            user=User(login="test_user"),
            reactions=Reactions(
                url="https://api.github.com/repos/test_org/test_repo/issues/comments/123456/reactions",
            ),
        ),
        issue=Issue(
            number=123,
            pull_request=IssuePullRequest(
                url="https://github.com/test_org/test_repo/pull/123",
            ),
        ),
        organization=Organization(login="test_org"),
        installation=Installation(id=123),
        sender=Sender(login="test_user"),
        repository=test_repository,
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    # https://api.github.com/repos/acts-project/acts/pulls/3975
    sample_pr = PullRequest(
        number=123,
        user=User(login="test_user"),
        draft=False,
        head=PullRequestHead(
            ref="test-branch",
            sha="abc123",
            repo=test_repository,
            user=User(login="test_user"),
        ),
        base=PullRequestBase(
            ref="main",
            sha="abc123",
            repo=test_repository,
            user=User(login="test_user"),
        ),
    )
    gidgethub_client.getitem.return_value = sample_pr.model_dump()

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
        cancel_pipelines_if_redundant_mock.return_value = None
        m.setattr(
            gitlab_client,
            "cancel_pipelines_if_redundant",
            cancel_pipelines_if_redundant_mock,
        )

        trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
        trigger_pipeline_mock.return_value = None
        m.setattr(gitlab_client, "trigger_pipeline", trigger_pipeline_mock)

        await github.handle_comment(
            gidgethub_client, session, event, gitlab_client, config
        )

        # Verify pipeline was triggered with correct parameters
        trigger_pipeline_mock.assert_called_once_with(
            gidgethub_client,
            head_sha="abc123",
            repo_url="https://api.github.com/repos/test_org/test_repo",
            repo_slug="test_org_test_repo",
            clone_url="https://github.com/test_org/test_repo.git",
            installation_id=123,
            head_ref="test-branch",
            config=config,
        )

        # Verify reaction was created
        gidgethub_client.post.assert_called_once_with(
            event.comment.reactions.url,
            data=ReactionCreateRequest(content=ReactionType.rocket).model_dump(),
        )


@pytest.mark.asyncio
async def test_handle_comment_wrong_action(session, monkeypatch, config):
    # Test that we ignore non-created comment actions
    event = IssueCommentEvent(
        action="edited",  # Should be ignored
        comment=Comment(
            id=123,
            body="/rerun",
            user=User(login="test_user"),
            reactions=Reactions(
                url="https://api.github.com/repos/test_org/test_repo/issues/comments/123456/reactions",
            ),
        ),
        issue=Issue(
            number=123,
            pull_request=IssuePullRequest(
                url="https://github.com/test_org/test_repo/pull/123",
            ),
        ),
        organization=Organization(login="test_org"),
        installation=Installation(id=123),
        sender=Sender(login="test_user"),
        repository=test_repository,
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        m.setattr(
            github,
            "get_author_in_team",
            get_author_in_team_mock,
        )
        is_in_installed_repos_mock = create_autospec(github.is_in_installed_repos)
        m.setattr(github, "is_in_installed_repos", is_in_installed_repos_mock)
        trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
        m.setattr(gitlab_client, "trigger_pipeline", trigger_pipeline_mock)

        await github.handle_comment(
            gidgethub_client, session, event, gitlab_client, config
        )

        # Verify no team check or pipeline trigger was attempted
        get_author_in_team_mock.assert_not_called()
        trigger_pipeline_mock.assert_not_called()
        # Verify no reaction was created
        gidgethub_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_handle_comment_user_not_in_team(session, monkeypatch, config):
    event = IssueCommentEvent(
        action="created",
        comment=Comment(
            id=123,
            body="/rerun",
            user=User(login="test_user"),
            reactions=Reactions(
                url="https://api.github.com/repos/test_org/test_repo/issues/comments/123456/reactions",
            ),
        ),
        issue=Issue(
            number=123,
            pull_request=IssuePullRequest(
                url="https://github.com/test_org/test_repo/pull/123",
            ),
        ),
        organization=Organization(login="test_org"),
        installation=Installation(id=123),
        sender=Sender(login="test_user"),
        repository=test_repository,
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        get_author_in_team_mock.return_value = False
        m.setattr(github, "get_author_in_team", get_author_in_team_mock)

        is_in_installed_repos_mock = create_autospec(github.is_in_installed_repos)
        is_in_installed_repos_mock.return_value = True
        m.setattr(github, "is_in_installed_repos", is_in_installed_repos_mock)

        trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
        m.setattr(
            gitlab_client,
            "trigger_pipeline",
            trigger_pipeline_mock,
        )

        await github.handle_comment(
            gidgethub_client, session, event, gitlab_client, config
        )

        # Verify no pipeline was triggered
        trigger_pipeline_mock.assert_not_called()
        # Verify no reaction was created
        gidgethub_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_handle_comment_not_pr(session, monkeypatch, config):
    # Test that we ignore comments on regular issues
    event = IssueCommentEvent(
        action="created",
        comment=Comment(
            id=123,
            body="/rerun",
            user=User(login="test_user"),
            reactions=Reactions(
                url="https://api.github.com/repos/test_org/test_repo/issues/comments/123456/reactions",
            ),
        ),
        issue=Issue(number=123),  # Regular issue, not a PR
        organization=Organization(login="test_org"),
        installation=Installation(id=123),
        sender=Sender(login="test_user"),
        repository=test_repository,
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        m.setattr(github, "get_author_in_team", get_author_in_team_mock)
        is_in_installed_repos_mock = create_autospec(github.is_in_installed_repos)
        m.setattr(
            github,
            "is_in_installed_repos",
            is_in_installed_repos_mock,
        )
        trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
        m.setattr(
            gitlab_client,
            "trigger_pipeline",
            trigger_pipeline_mock,
        )

        await github.handle_comment(
            gidgethub_client, session, event, gitlab_client, config
        )

        # Verify no team check or pipeline trigger was attempted
        get_author_in_team_mock.assert_not_called()
        trigger_pipeline_mock.assert_not_called()
        # Verify no reaction was created
        gidgethub_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_handle_comment_wrong_command(session, monkeypatch, config):
    event = IssueCommentEvent(
        action="created",
        comment=Comment(
            id=123,
            body="/invalid-command",  # Invalid command
            user=User(login="test_user"),
            reactions=Reactions(
                url="https://api.github.com/repos/test_org/test_repo/issues/comments/123456/reactions",
            ),
        ),
        issue=Issue(
            number=123,
            pull_request=IssuePullRequest(
                url="https://github.com/test_org/test_repo/pull/123",
            ),
        ),
        organization=Organization(login="test_org"),
        installation=Installation(id=123),
        sender=Sender(login="test_user"),
        repository=test_repository,
    )

    gidgethub_client = AsyncMock()
    gidgetlab_client = AsyncMock()

    gitlab_client = GitLab(session=session, gl=gidgetlab_client, config=config)

    with monkeypatch.context() as m:
        get_author_in_team_mock = create_autospec(github.get_author_in_team)
        m.setattr(github, "get_author_in_team", get_author_in_team_mock)
        is_in_installed_repos_mock = create_autospec(github.is_in_installed_repos)
        m.setattr(github, "is_in_installed_repos", is_in_installed_repos_mock)
        trigger_pipeline_mock = create_autospec(gitlab_client.trigger_pipeline)
        m.setattr(gitlab_client, "trigger_pipeline", trigger_pipeline_mock)

        await github.handle_comment(
            gidgethub_client, session, event, gitlab_client, config
        )

        # Verify no pipeline was triggered for invalid command
        trigger_pipeline_mock.assert_not_called()
        # Verify no reaction was created
        gidgethub_client.post.assert_not_called()
