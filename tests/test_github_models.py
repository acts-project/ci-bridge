import json
import os

import pytest

from ci_relay.github.models import (
    CheckSuiteEvent,
    CheckSuite,
    CheckSuiteApp,
    Repository,
    Organization,
    Sender,
    Installation,
    PushEvent,
    PullRequestEvent,
    IssueCommentEvent,
    PullRequest,
    PullRequestHead,
    PullRequestBase,
    User,
    ReactionCreateRequest,
    ReactionType,
)


def load_sample_data(filename):
    with open(os.path.join("tests/samples", filename)) as f:
        return json.load(f)


def test_check_suite_requested_model():
    data = load_sample_data("check_suite_requested.json")
    event = CheckSuiteEvent(**data)  # type: ignore

    assert event.action == "requested"
    assert isinstance(event.check_suite, CheckSuite)
    assert event.check_suite.id == 123456
    assert isinstance(event.check_suite.app, CheckSuiteApp)
    assert event.check_suite.app.id == 12345
    assert isinstance(event.repository, Repository)
    assert isinstance(event.organization, Organization)
    assert event.organization.login == "org"
    assert isinstance(event.sender, Sender)
    assert event.sender.login == "test-bot"
    assert isinstance(event.installation, Installation)
    assert event.installation.id == 12345


def test_check_suite_rerequested_model():
    data = load_sample_data("check_suite_rerequested.json")
    event = CheckSuiteEvent(**data)  # type: ignore

    assert event.action == "rerequested"
    assert isinstance(event.check_suite, CheckSuite)
    assert event.check_suite.id == 123456
    assert event.check_suite.head_sha == "abc123def456"
    assert isinstance(event.check_suite.app, CheckSuiteApp)
    assert event.check_suite.app.id == 12345
    assert isinstance(event.repository, Repository)
    assert isinstance(event.organization, Organization)
    assert event.organization.login == "org"
    assert isinstance(event.sender, Sender)
    assert event.sender.login == "test-bot"
    assert isinstance(event.installation, Installation)
    assert event.installation.id == 12345


def test_push_event_model():
    data = load_sample_data("push.json")
    event = PushEvent(**data)  # type: ignore

    assert event.ref == "refs/heads/main"
    assert event.after == "def456ghi789"
    assert isinstance(event.repository, Repository)
    assert event.repository.full_name == "test-org/test-repo"
    assert event.pusher.name == "test-user"
    assert isinstance(event.sender, Sender)
    assert event.sender.login == "test-user"


def test_pull_request_event_model():
    data = load_sample_data("pull_request_synchronize.json")
    event = PullRequestEvent(**data)  # type: ignore

    assert event.action == "synchronize"
    assert event.pull_request.number == 123
    assert not event.pull_request.draft
    assert event.pull_request.user.login == "test-user"
    assert event.pull_request.head.ref == "test-branch"
    assert event.pull_request.head.sha == "def456ghi789"
    assert event.repository.full_name == "test-org/test-repo"
    assert event.organization.login == "test-org"
    assert event.sender.login == "test-user"
    assert event.installation.id == 12345


def test_issue_comment_event_model():
    data = load_sample_data("issue_comment_created_issue.json")
    event = IssueCommentEvent(**data)  # type: ignore

    assert event.action == "created"
    assert event.comment.body == "test comment"
    assert event.comment.user.login == "test_user"
    assert (
        event.comment.reactions.url
        == "https://api.github.com/repos/test_org/test_repo/issues/comments/123456/reactions"
    )
    assert event.issue.number == 123
    assert event.issue.pull_request is None
    assert event.repository.full_name == "test_org/test_repo"
    assert event.organization.login == "test_org"
    assert event.sender.login == "test_user"
    assert event.installation.id == 12345


def test_issue_comment_event_model_pr():
    data = load_sample_data("issue_comment_created_pr.json")
    event = IssueCommentEvent(**data)  # type: ignore

    assert event.action == "created"
    assert event.comment.body == "/rerun"
    assert event.comment.user.login == "test_user"
    assert (
        event.comment.reactions.url
        == "https://api.github.com/repos/test_org/test_repo/issues/comments/123456/reactions"
    )
    assert event.issue.number == 123
    assert event.issue.pull_request is not None
    assert (
        event.issue.pull_request.url
        == "https://api.github.com/repos/test_org/test_repo/pulls/123"
    )


def test_pr_api_response_model():
    data = load_sample_data("pr_api_response.json")
    pr = PullRequest(**data)  # type: ignore

    print(pr)
    assert pr.number == 123
    assert pr.user == User(
        login="test_user",
        id=12345,
    )
    assert pr.draft is False
    assert pr.head == PullRequestHead(
        ref="test-branch",
        sha="abc123",
        repo=Repository(
            id=123456,
            full_name="test_user/test_repo",
            url="https://api.github.com/repos/test_user/test_repo",
            clone_url="https://github.com/test_user/test_repo.git",
        ),
        user=User(
            login="test_user",
            id=12345,
        ),
    )
    assert pr.base == PullRequestBase(
        ref="main",
        sha="abc123",
        repo=Repository(
            id=123456,
            full_name="test_org/test_repo",
            url="https://api.github.com/repos/test_org/test_repo",
            clone_url="https://github.com/test_org/test_repo.git",
        ),
    )


@pytest.mark.parametrize("reaction_type", ReactionType)
def test_reaction_create_request_model(reaction_type):
    reaction = ReactionCreateRequest(content=reaction_type)
    json = reaction.model_dump_json()

    assert json == f'{{"content":"{reaction_type}"}}'
