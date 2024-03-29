import os
import dotenv
import logging

dotenv.load_dotenv()

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
APP_ID = int(os.environ.get("APP_ID"))

ALLOW_TEAM = os.environ["ALLOW_TEAM"]

GITLAB_ACCESS_TOKEN = os.environ["GITLAB_ACCESS_TOKEN"]
GITLAB_PIPELINE_TRIGGER_TOKEN = os.environ["GITLAB_PIPELINE_TRIGGER_TOKEN"]
GITLAB_TRIGGER_URL = os.environ["GITLAB_TRIGGER_URL"]
GITLAB_API_URL = os.environ["GITLAB_API_URL"]
GITLAB_PROJECT_ID = int(os.environ["GITLAB_PROJECT_ID"])

TRIGGER_SECRET = os.environ["TRIGGER_SECRET"].encode()

GITLAB_WEBHOOK_SECRET = os.environ["GITLAB_WEBHOOK_SECRET"]

OVERRIDE_LOGGING = logging.getLevelName(os.environ.get("OVERRIDE_LOGGING", "WARNING"))

EXTRA_USERS = os.environ.get("EXTRA_USERS", "").split(",")


STERILE = os.environ.get("STERILE") == "true"
