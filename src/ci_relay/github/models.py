from pydantic import BaseModel


class User(BaseModel):
    login: str


class Repository(BaseModel):
    id: int
    url: str
    full_name: str
    clone_url: str


class PullRequestHead(BaseModel):
    ref: str
    sha: str
    repo: Repository
    user: User


class PullRequestBase(BaseModel):
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


class RerequestEvent(BaseModel):
    sender: Sender
    organization: Organization
    repository: Repository
    check_run: CheckRun
    installation: Installation


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
    check_run: CheckRun
    repository: Repository
    installation: Installation
