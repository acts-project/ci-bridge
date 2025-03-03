from pydantic import BaseModel


class User(BaseModel):
    login: str


class Repository(BaseModel):
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


class PullRequestEvent(BaseModel):
    sender: User
    organization: Organization
    pull_request: PullRequest
    installation: Installation
    action: str
    repository: Repository


class CheckRun(BaseModel):
    external_id: str
    number: int


class CheckSuite(BaseModel):
    head_sha: str
    app: dict
    check_runs_url: str


class CheckRunEvent(BaseModel):
    action: str
    check_run: CheckRun
    repository: Repository
    installation: Installation


class CheckSuiteEvent(BaseModel):
    action: str
    check_suite: CheckSuite
    repository: Repository
    installation: Installation
    sender: User
    organization: Organization


class PushEvent(BaseModel):
    sender: User
    organization: Organization
    repository: Repository
    installation: Installation
    after: str
    ref: str
    pusher: User
