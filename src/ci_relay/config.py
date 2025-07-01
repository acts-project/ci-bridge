from typing import Literal

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    WEBHOOK_SECRET: str
    PRIVATE_KEY: str
    APP_ID: int

    ALLOW_TEAM: str

    GITLAB_ACCESS_TOKEN: str
    GITLAB_PIPELINE_TRIGGER_TOKEN: str
    GITLAB_TRIGGER_URL: str
    GITLAB_API_URL: str
    GITLAB_PROJECT_ID: int

    TRIGGER_SECRET: bytes

    GITLAB_WEBHOOK_SECRET: str

    OVERRIDE_LOGGING: Literal[
        "CRITICAL",
        "FATAL",
        "ERROR",
        "WARNING",
        "WARN",
        "INFO",
        "DEBUG",
        "NOTSET",
    ]

    EXTRA_USERS: list[str] = []

    STERILE: bool = False

    GITLAB_IGNORED_JOB_PATTERNS: list[str] = []
