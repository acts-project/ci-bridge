"""
Prometheus metrics for the CI relay application.

This module defines all the metrics that are collected throughout the application
to monitor webhook reception, job triggering, error rates, and GitHub workflow triggering.
"""

from prometheus_client import Counter, Histogram, Gauge, Info
import time


# Webhook reception metrics
webhooks_received_total = Counter(
    'ci_relay_webhooks_received_total',
    'Total number of webhooks received',
    ['source', 'event_type']  # source = github|gitlab, event_type = push|pull_request|job_hook|etc
)

webhook_processing_duration_seconds = Histogram(
    'ci_relay_webhook_processing_duration_seconds',
    'Time spent processing webhooks',
    ['source', 'event_type']
)

webhook_processing_errors_total = Counter(
    'ci_relay_webhook_processing_errors_total',
    'Total number of webhook processing errors',
    ['source', 'event_type', 'error_type']
)

# GitLab job triggering metrics
gitlab_jobs_triggered_total = Counter(
    'ci_relay_gitlab_jobs_triggered_total',
    'Total number of GitLab pipelines/jobs triggered',
    ['repo_name', 'trigger_source']  # trigger_source = pull_request|push|comment|rerun
)

gitlab_job_trigger_errors_total = Counter(
    'ci_relay_gitlab_job_trigger_errors_total',
    'Total number of GitLab job trigger errors',
    ['repo_name', 'error_type']
)

gitlab_job_trigger_duration_seconds = Histogram(
    'ci_relay_gitlab_job_trigger_duration_seconds',
    'Time spent triggering GitLab jobs',
    ['repo_name']
)

# GitHub workflow triggering metrics (workloads triggered back to GitHub)
github_workflows_triggered_total = Counter(
    'ci_relay_github_workflows_triggered_total',
    'Total number of GitHub workflows triggered',
    ['repo_name', 'job_status']  # job_status = success|failed|canceled|etc
)

github_workflow_trigger_errors_total = Counter(
    'ci_relay_github_workflow_trigger_errors_total',
    'Total number of GitHub workflow trigger errors',
    ['repo_name', 'error_type']
)

github_workflow_trigger_duration_seconds = Histogram(
    'ci_relay_github_workflow_trigger_duration_seconds',
    'Time spent triggering GitHub workflows',
    ['repo_name']
)

# GitHub status update metrics
github_status_updates_total = Counter(
    'ci_relay_github_status_updates_total',
    'Total number of GitHub status updates posted',
    ['repo_name', 'status', 'conclusion']  # status = in_progress|completed, conclusion = success|failure|neutral|cancelled
)

github_status_update_errors_total = Counter(
    'ci_relay_github_status_update_errors_total',
    'Total number of GitHub status update errors',
    ['repo_name', 'error_type']
)

# GitLab API interaction metrics
gitlab_api_calls_total = Counter(
    'ci_relay_gitlab_api_calls_total',
    'Total number of GitLab API calls',
    ['endpoint', 'method', 'status_code']
)

gitlab_api_call_duration_seconds = Histogram(
    'ci_relay_gitlab_api_call_duration_seconds',
    'Duration of GitLab API calls',
    ['endpoint', 'method']
)

# GitHub API interaction metrics
github_api_calls_total = Counter(
    'ci_relay_github_api_calls_total',
    'Total number of GitHub API calls',
    ['endpoint', 'method', 'status_code']
)

github_api_call_duration_seconds = Histogram(
    'ci_relay_github_api_call_duration_seconds',
    'Duration of GitHub API calls',
    ['endpoint', 'method']
)

# Application-level metrics
app_errors_total = Counter(
    'ci_relay_app_errors_total',
    'Total number of application errors',
    ['error_type', 'component']  # component = github_router|gitlab_router|web|etc
)

active_installations = Gauge(
    'ci_relay_active_installations',
    'Number of active GitHub app installations'
)

# Health check metrics
health_check_status = Gauge(
    'ci_relay_health_check_status',
    'Health check status (1 = healthy, 0 = unhealthy)',
    ['service']  # service = github|gitlab|overall
)

health_check_duration_seconds = Histogram(
    'ci_relay_health_check_duration_seconds',
    'Duration of health checks',
    ['service']
)

# Application info
app_info = Info(
    'ci_relay_app',
    'CI Relay application information'
)


class MetricsContext:
    """Context manager for timing operations and handling errors with metrics."""
    
    def __init__(self, histogram, error_counter, labels=None, error_labels=None):
        self.histogram = histogram
        self.error_counter = error_counter
        self.labels = labels or []
        self.error_labels = error_labels or []
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.time() - self.start_time
            self.histogram.labels(*self.labels).observe(duration)
        
        if exc_type is not None:
            error_type = exc_type.__name__
            self.error_counter.labels(*self.error_labels, error_type).inc()
        
        return False  # Don't suppress exceptions


def track_webhook_processing(source: str, event_type: str):
    """Context manager for tracking webhook processing metrics."""
    return MetricsContext(
        webhook_processing_duration_seconds.labels(source, event_type),
        webhook_processing_errors_total,
        labels=[source, event_type],
        error_labels=[source, event_type]
    )


def track_gitlab_job_trigger(repo_name: str):
    """Context manager for tracking GitLab job trigger metrics."""
    return MetricsContext(
        gitlab_job_trigger_duration_seconds.labels(repo_name),
        gitlab_job_trigger_errors_total,
        labels=[repo_name],
        error_labels=[repo_name]
    )


def track_github_workflow_trigger(repo_name: str):
    """Context manager for tracking GitHub workflow trigger metrics."""
    return MetricsContext(
        github_workflow_trigger_duration_seconds.labels(repo_name),
        github_workflow_trigger_errors_total,
        labels=[repo_name],
        error_labels=[repo_name]
    )


def track_gitlab_api_call(endpoint: str, method: str):
    """Context manager for tracking GitLab API call metrics."""
    return MetricsContext(
        gitlab_api_call_duration_seconds.labels(endpoint, method),
        Counter('dummy_gitlab_api_errors', 'dummy'),  # We'll handle status codes separately
        labels=[endpoint, method],
        error_labels=[]
    )


def track_github_api_call(endpoint: str, method: str):
    """Context manager for tracking GitHub API call metrics."""
    return MetricsContext(
        github_api_call_duration_seconds.labels(endpoint, method),
        Counter('dummy_github_api_errors', 'dummy'),  # We'll handle status codes separately
        labels=[endpoint, method],
        error_labels=[]
    )