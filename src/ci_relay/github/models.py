from pydantic import BaseModel
from enum import StrEnum


class User(BaseModel):
    login: str
    id: int | None = None


class Repository(BaseModel):
    id: int
    url: str
    full_name: str
    clone_url: str
    user: User | None = None


class PullRequestHead(BaseModel):
    ref: str
    sha: str
    repo: Repository
    user: User


class PullRequestBase(BaseModel):
    ref: str
    sha: str
    repo: Repository


class PullRequest(BaseModel):
    user: User
    head: PullRequestHead
    base: PullRequestBase
    draft: bool
    number: int


class Organization(BaseModel):
    login: str


class Installation(BaseModel):
    id: int


class Sender(BaseModel):
    login: str


class Pusher(BaseModel):
    name: str


class CheckRun(BaseModel):
    external_id: str


class PushEvent(BaseModel):
    sender: Sender
    organization: Organization
    repository: Repository
    pusher: Pusher
    after: str
    ref: str
    installation: Installation


class CheckSuiteApp(BaseModel):
    id: int


class CheckSuite(BaseModel):
    id: int
    app: CheckSuiteApp
    head_sha: str
    check_runs_url: str


class CheckSuiteEvent(BaseModel):
    action: str
    sender: Sender
    organization: Organization
    repository: Repository
    check_suite: CheckSuite
    installation: Installation


class PullRequestEvent(BaseModel):
    pull_request: PullRequest
    organization: Organization
    installation: Installation
    sender: Sender
    action: str
    repository: Repository


class CheckRunEvent(BaseModel):
    action: str
    sender: Sender
    organization: Organization
    check_run: CheckRun
    repository: Repository
    installation: Installation


class Reactions(BaseModel):
    url: str


class Comment(BaseModel):
    id: int
    body: str
    user: User
    reactions: Reactions


class ReactionType(StrEnum):
    plus_one = "+1"
    minus_one = "-1"
    laugh = "laugh"
    confused = "confused"
    heart = "heart"
    hooray = "hooray"
    rocket = "rocket"
    eyes = "eyes"


class ReactionCreateRequest(BaseModel):
    content: ReactionType


class IssuePullRequest(BaseModel):
    url: str


class Issue(BaseModel):
    number: int
    pull_request: IssuePullRequest | None = None


class IssueCommentEvent(BaseModel):
    action: str
    comment: Comment
    issue: Issue
    organization: Organization
    installation: Installation
    sender: Sender
    repository: Repository


# New models for check run
class CheckRunOutput(BaseModel):
    title: str
    summary: str
    text: str | None = None


class CheckRunPayload(BaseModel):
    name: str
    status: str
    head_sha: str
    started_at: str | None = None
    completed_at: str | None = None
    conclusion: str | None = None
    details_url: str | None = None
    external_id: str | None = None
    output: CheckRunOutput
