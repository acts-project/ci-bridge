import os
import dotenv

dotenv.load_dotenv()

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
APP_ID = int(os.environ.get("APP_ID"))

ALLOW_TEAM = os.environ["ALLOW_TEAM"]

GITLAB_ACCESS_TOKEN = os.environ["GITLAB_ACCESS_TOKEN"]
GITLAB_PIPELINE_TRIGGER_TOKEN = os.environ["GITLAB_PIPELINE_TRIGGER_TOKEN"]
GITLAB_TRIGGER_URL = os.environ["GITLAB_TRIGGER_URL"]
GITLAB_API_URL = os.environ["GITLAB_API_URL"]

TRIGGER_SECRET = os.environ["TRIGGER_SECRET"].encode()

GITLAB_WEBHOOK_SECRET = os.environ["GITLAB_WEBHOOK_SECRET"]
