import json
import os
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
)


def load_sample_data(filename):
    with open(os.path.join("tests/samples", filename)) as f:
        return json.load(f)


def test_check_suite_requested_model():
    data = load_sample_data("check_suite_requested.json")
    event = CheckSuiteEvent(**data)

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
    event = CheckSuiteEvent(**data)

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
    event = PushEvent(**data)

    assert event.ref == "refs/heads/main"
    assert event.after == "def456ghi789"
    assert isinstance(event.repository, Repository)
    assert event.repository.full_name == "test-org/test-repo"
    assert event.pusher.name == "test-user"
    assert isinstance(event.sender, Sender)
    assert event.sender.login == "test-user"


def test_pull_request_event_model():
    data = load_sample_data("pull_request_synchronize.json")
    event = PullRequestEvent(**data)

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
