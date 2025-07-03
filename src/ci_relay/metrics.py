import time
from typing import Dict, Any
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    REGISTRY
)
from sanic.log import logger


class Metrics:
    """Prometheus metrics for CI Relay application"""
    
    def __init__(self):
        # Webhook metrics
        self.webhook_requests_total = Counter(
            'ci_relay_webhook_requests_total',
            'Total number of webhook requests received',
            ['source', 'event_type', 'status']
        )
        
        self.webhook_processing_duration = Histogram(
            'ci_relay_webhook_processing_duration_seconds',
            'Time spent processing webhooks',
            ['source', 'event_type'],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float('inf')]
        )
        
        # Job trigger metrics
        self.jobs_triggered_total = Counter(
            'ci_relay_jobs_triggered_total',
            'Total number of jobs triggered',
            ['source', 'target', 'trigger_reason']
        )
        
        self.github_workflows_triggered_total = Counter(
            'ci_relay_github_workflows_triggered_total',
            'Total number of GitHub workflows triggered from GitLab',
            ['repo_name', 'gitlab_job_status', 'success']
        )
        
        self.gitlab_pipelines_triggered_total = Counter(
            'ci_relay_gitlab_pipelines_triggered_total',
            'Total number of GitLab pipelines triggered from GitHub',
            ['repo_name', 'github_event_type', 'success']
        )
        
        # Error metrics
        self.errors_total = Counter(
            'ci_relay_errors_total',
            'Total number of errors',
            ['component', 'error_type', 'severity']
        )
        
        self.webhook_errors_total = Counter(
            'ci_relay_webhook_errors_total',
            'Total number of webhook processing errors',
            ['source', 'event_type', 'error_type']
        )
        
        self.api_errors_total = Counter(
            'ci_relay_api_errors_total',
            'Total number of API call errors',
            ['service', 'endpoint', 'status_code']
        )
        
        # GitHub integration metrics
        self.github_check_runs_created_total = Counter(
            'ci_relay_github_check_runs_created_total',
            'Total number of GitHub check runs created',
            ['repo_name', 'status']
        )
        
        self.github_commit_statuses_created_total = Counter(
            'ci_relay_github_commit_statuses_created_total',
            'Total number of GitHub commit statuses created',
            ['repo_name', 'state']
        )
        
        # GitLab integration metrics
        self.gitlab_job_status_updates_total = Counter(
            'ci_relay_gitlab_job_status_updates_total',
            'Total number of GitLab job status updates processed',
            ['project_name', 'job_status', 'processed']
        )
        
        # Health and performance metrics
        self.health_check_status = Gauge(
            'ci_relay_health_check_status',
            'Health check status (1=healthy, 0=unhealthy)',
            ['service']
        )
        
        self.active_webhooks = Gauge(
            'ci_relay_active_webhooks',
            'Number of webhooks currently being processed'
        )
        
        self.retry_attempts_total = Counter(
            'ci_relay_retry_attempts_total',
            'Total number of retry attempts',
            ['operation', 'final_result']
        )
        
        # Application info
        self.app_info = Info(
            'ci_relay_app_info',
            'Application information'
        )
    
    def record_webhook_received(self, source: str, event_type: str, status: str = "received"):
        """Record that a webhook was received"""
        self.webhook_requests_total.labels(
            source=source,
            event_type=event_type,
            status=status
        ).inc()
        logger.debug(f"Recorded webhook: {source}/{event_type} - {status}")
    
    def record_webhook_processing_time(self, source: str, event_type: str, duration: float):
        """Record webhook processing duration"""
        self.webhook_processing_duration.labels(
            source=source,
            event_type=event_type
        ).observe(duration)
    
    def record_job_triggered(self, source: str, target: str, trigger_reason: str):
        """Record that a job was triggered"""
        self.jobs_triggered_total.labels(
            source=source,
            target=target,
            trigger_reason=trigger_reason
        ).inc()
        logger.debug(f"Recorded job trigger: {source} -> {target} ({trigger_reason})")
    
    def record_github_workflow_triggered(self, repo_name: str, gitlab_job_status: str, success: bool):
        """Record GitHub workflow triggered from GitLab"""
        self.github_workflows_triggered_total.labels(
            repo_name=repo_name,
            gitlab_job_status=gitlab_job_status,
            success=str(success).lower()
        ).inc()
    
    def record_gitlab_pipeline_triggered(self, repo_name: str, github_event_type: str, success: bool):
        """Record GitLab pipeline triggered from GitHub"""
        self.gitlab_pipelines_triggered_total.labels(
            repo_name=repo_name,
            github_event_type=github_event_type,
            success=str(success).lower()
        ).inc()
    
    def record_error(self, component: str, error_type: str, severity: str = "error"):
        """Record a general error"""
        self.errors_total.labels(
            component=component,
            error_type=error_type,
            severity=severity
        ).inc()
        logger.debug(f"Recorded error: {component}/{error_type} - {severity}")
    
    def record_webhook_error(self, source: str, event_type: str, error_type: str):
        """Record a webhook processing error"""
        self.webhook_errors_total.labels(
            source=source,
            event_type=event_type,
            error_type=error_type
        ).inc()
    
    def record_api_error(self, service: str, endpoint: str, status_code: int):
        """Record an API call error"""
        self.api_errors_total.labels(
            service=service,
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()
    
    def record_github_check_run_created(self, repo_name: str, status: str):
        """Record GitHub check run creation"""
        self.github_check_runs_created_total.labels(
            repo_name=repo_name,
            status=status
        ).inc()
    
    def record_github_commit_status_created(self, repo_name: str, state: str):
        """Record GitHub commit status creation"""
        self.github_commit_statuses_created_total.labels(
            repo_name=repo_name,
            state=state
        ).inc()
    
    def record_gitlab_job_status_update(self, project_name: str, job_status: str, processed: bool):
        """Record GitLab job status update processing"""
        self.gitlab_job_status_updates_total.labels(
            project_name=project_name,
            job_status=job_status,
            processed=str(processed).lower()
        ).inc()
    
    def set_health_status(self, service: str, healthy: bool):
        """Set health check status"""
        self.health_check_status.labels(service=service).set(1 if healthy else 0)
    
    def inc_active_webhooks(self):
        """Increment active webhook counter"""
        self.active_webhooks.inc()
    
    def dec_active_webhooks(self):
        """Decrement active webhook counter"""
        self.active_webhooks.dec()
    
    def record_retry_attempt(self, operation: str, final_result: str):
        """Record a retry attempt"""
        self.retry_attempts_total.labels(
            operation=operation,
            final_result=final_result
        ).inc()
    
    def set_app_info(self, info: Dict[str, Any]):
        """Set application information"""
        self.app_info.info(info)


# Global metrics instance
metrics = Metrics()


def get_metrics_content():
    """Get Prometheus metrics in text format"""
    return generate_latest(REGISTRY)


def get_metrics_content_type():
    """Get Prometheus metrics content type"""
    return CONTENT_TYPE_LATEST


class MetricsContext:
    """Context manager for tracking webhook processing time and active count"""
    
    def __init__(self, source: str, event_type: str):
        self.source = source
        self.event_type = event_type
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        metrics.inc_active_webhooks()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.time() - self.start_time
            metrics.record_webhook_processing_time(self.source, self.event_type, duration)
        metrics.dec_active_webhooks()
        
        if exc_type is not None:
            # Record error if exception occurred
            error_type = exc_type.__name__ if exc_type else "unknown"
            metrics.record_webhook_error(self.source, self.event_type, error_type)