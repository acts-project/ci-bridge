from typing import Literal

from pydantic_settings import BaseSettings
from sanic.log import logger


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

    def print_config(self):
        """Print configuration values with sensitive attributes masked"""
        sensitive_attrs = {
            "WEBHOOK_SECRET",
            "PRIVATE_KEY",
            "GITLAB_ACCESS_TOKEN",
            "GITLAB_PIPELINE_TRIGGER_TOKEN",
            "TRIGGER_SECRET",
            "GITLAB_WEBHOOK_SECRET",
        }

        logger.info("=== CI Bridge Configuration ===")
        for field_name, field_value in self.model_dump().items():
            if field_name in sensitive_attrs:
                if isinstance(field_value, bytes):
                    logger.info(f"{field_name}: *** (bytes)")
                else:
                    logger.info(f"{field_name}: ***")
            else:
                logger.info(f"{field_name}: {field_value}")
        logger.info("================================")
