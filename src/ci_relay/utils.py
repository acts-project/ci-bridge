def gitlab_to_github_status(gitlab_status: str) -> str:
    if gitlab_status in (
        "created",
        "waiting_for_resource",
        "preparing",
        "pending",
        "manual",
        "scheduled",
    ):
        check_status = "queued"
    elif gitlab_status in ("running",):
        check_status = "in_progress"
    elif gitlab_status in ("success", "failed", "canceled", "skipped"):
        check_status = "completed"
    else:
        raise ValueError(f"Unknown status {gitlab_status}")
    return check_status
