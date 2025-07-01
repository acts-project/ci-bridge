import re
from sanic.log import logger


def should_ignore_job(job_name: str, patterns: list[str]) -> bool:
    """
    Check if a job should be ignored based on regex patterns.

    Args:
        job_name: The name of the job to check
        patterns: List of regex patterns to match against

    Returns:
        True if the job should be ignored, False otherwise
    """
    if not patterns:
        return False

    for pattern in patterns:
        try:
            if re.match(pattern, job_name):
                logger.debug(f"Job '{job_name}' matches pattern '{pattern}', ignoring")
                return True
        except re.error as e:
            logger.error(f"Invalid regex pattern '{pattern}': {e}")
            continue

    return False
