from pydantic import BaseModel


class PipelineTriggerData(BaseModel):
    installation_id: int
    repo_url: str
    repo_slug: str
    head_sha: str
    config_url: str
    clone_url: str
    clone_repo_slug: str
    head_ref: str
