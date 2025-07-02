# GitLab to GitHub Workflow Triggering

This feature allows the CI Bridge to trigger GitHub Actions workflows when GitLab CI jobs finish. When a GitLab job completes (success, failure, or other configured statuses), the system can automatically trigger GitHub workflows on the main branch of specified target repositories.

## Overview

The GitLab to GitHub triggering functionality extends the existing CI Bridge capabilities by:

1. **Monitoring GitLab job completions** - Listening for GitLab job hook events
2. **Filtering by job status** - Only triggering on configured job statuses (e.g., success, failed)
3. **Targeting specific repositories** - Triggering workflows only in configured GitHub repositories
4. **Using repository dispatch** - Sending GitHub repository dispatch events to trigger workflows
5. **Running on main branch** - Always triggering workflows on the main branch as requested

## Configuration

Add the following environment variables to enable and configure GitLab to GitHub triggering:

### Required Configuration

```bash
# Enable the feature
ENABLE_GITLAB_TO_GITHUB_TRIGGERING=true

# Target repositories (comma-separated list of "owner/repo" strings)
GITLAB_TO_GITHUB_TARGET_REPOS=["myorg/frontend-repo", "myorg/docs-repo"]
```

### Optional Configuration

```bash
# Job statuses that trigger workflows (default: ["success", "failed"])
GITLAB_TO_GITHUB_TRIGGER_ON_STATUS=["success", "failed", "canceled"]
```

### Example Configuration

```bash
# .env file or environment variables
ENABLE_GITLAB_TO_GITHUB_TRIGGERING=true
GITLAB_TO_GITHUB_TARGET_REPOS=["myorg/website", "myorg/documentation"]
GITLAB_TO_GITHUB_TRIGGER_ON_STATUS=["success"]
```

## GitHub Actions Workflow

The system triggers GitHub workflows using the `repository_dispatch` event type `gitlab-job-finished`. A sample workflow is provided in `.github/workflows/gitlab-trigger.yml`.

### Workflow Event Structure

The triggered workflow receives detailed information about the GitLab job:

```yaml
name: GitLab Job Triggered Workflow

on:
  repository_dispatch:
    types: [gitlab-job-finished]

jobs:
  my-job:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          ref: main  # Always uses main branch
          
      - name: Access GitLab job data
        run: |
          echo "Job Status: ${{ github.event.client_payload.job_status }}"
          echo "Job Name: ${{ github.event.client_payload.job_name }}"
          echo "Project: ${{ github.event.client_payload.project_name }}"
          echo "Commit SHA: ${{ github.event.client_payload.commit_sha }}"
          # ... and more fields
```

### Available Data Fields

The `client_payload` contains the following GitLab job information:

| Field | Description | Example |
|-------|-------------|---------|
| `job_status` | Current job status | `"success"`, `"failed"`, `"canceled"` |
| `job_name` | Name of the GitLab job | `"test"`, `"build"`, `"deploy"` |
| `job_id` | GitLab job ID | `12345` |
| `job_url` | Link to GitLab job | `"https://gitlab.com/project/-/jobs/12345"` |
| `project_name` | GitLab project name | `"my-awesome-project"` |
| `project_path` | Full project path | `"myorg/my-awesome-project"` |
| `ref` | Git reference (branch/tag) | `"main"`, `"feature/new-feature"` |
| `commit_sha` | Git commit SHA | `"abc123def456..."` |
| `pipeline_id` | GitLab pipeline ID | `67890` |
| `pipeline_url` | Link to GitLab pipeline | `"https://gitlab.com/project/-/pipelines/67890"` |
| `created_at` | Job creation timestamp | `"2023-01-01T12:00:00Z"` |
| `started_at` | Job start timestamp | `"2023-01-01T12:01:00Z"` |
| `finished_at` | Job completion timestamp | `"2023-01-01T12:05:00Z"` |
| `allow_failure` | Whether job failure is allowed | `true`, `false` |
| `gitlab_project_id` | GitLab project ID | `42` |

## Use Cases

### 1. Documentation Updates
Trigger documentation builds when GitLab tests pass:

```yaml
- name: Update documentation
  if: github.event.client_payload.job_status == 'success'
  run: |
    # Build and deploy documentation
    npm run build:docs
    npm run deploy:docs
```

### 2. Deployment Workflows
Deploy applications when GitLab builds succeed:

```yaml
- name: Deploy to production
  if: |
    github.event.client_payload.job_status == 'success' &&
    github.event.client_payload.job_name == 'build-production' &&
    github.event.client_payload.ref == 'main'
  run: |
    # Deploy to production environment
    ./deploy.sh production
```

### 3. Notifications and Alerts
Send notifications based on GitLab job results:

```yaml
- name: Send Slack notification
  if: github.event.client_payload.job_status == 'failed'
  uses: 8398a7/action-slack@v3
  with:
    status: failure
    text: |
      GitLab job failed: ${{ github.event.client_payload.job_name }}
      Project: ${{ github.event.client_payload.project_name }}
      Job URL: ${{ github.event.client_payload.job_url }}
```

### 4. Cross-Repository Coordination
Trigger related workflows in multiple repositories:

```yaml
- name: Trigger dependent repository builds
  if: |
    github.event.client_payload.job_status == 'success' &&
    github.event.client_payload.job_name == 'integration-tests'
  run: |
    # Trigger builds in dependent repositories
    gh workflow run deploy.yml --repo myorg/frontend
    gh workflow run update.yml --repo myorg/mobile-app
```

## Security Considerations

1. **GitHub App Permissions**: The CI Bridge GitHub App must have access to target repositories
2. **Repository Access**: Target repositories must have the GitHub App installed
3. **Workflow Permissions**: Ensure triggered workflows have appropriate permissions
4. **Sensitive Data**: Avoid passing sensitive GitLab data to GitHub workflows

## Troubleshooting

### Common Issues

1. **Workflows not triggering**
   - Check that `ENABLE_GITLAB_TO_GITHUB_TRIGGERING=true`
   - Verify target repositories are correctly configured
   - Ensure GitHub App has access to target repositories
   - Check CI Bridge logs for error messages

2. **Repository not found errors**
   - Verify repository names are in "owner/repo" format
   - Ensure GitHub App is installed on target repositories
   - Check that the repository exists and is accessible

3. **Workflow receives no data**
   - Verify workflow listens for `repository_dispatch` with type `gitlab-job-finished`
   - Check that GitLab job completed with a configured trigger status

### Debug Logging

Enable debug logging to troubleshoot issues:

```bash
OVERRIDE_LOGGING=DEBUG
```

Look for log messages like:
- `"GitLab to GitHub triggering is enabled, checking target repos"`
- `"Triggering GitHub workflow for target repo: owner/repo"`
- `"Successfully triggered GitHub workflow for owner/repo"`

### Testing

You can manually test the workflow triggering using the GitHub API:

```bash
curl -X POST \
  -H "Authorization: token YOUR_GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/OWNER/REPO/dispatches \
  -d '{
    "event_type": "gitlab-job-finished",
    "client_payload": {
      "job_status": "success",
      "job_name": "test-job",
      "project_name": "test-project",
      "ref": "main",
      "commit_sha": "abc123",
      "pipeline_url": "https://gitlab.com/project/pipeline"
    }
  }'
```

## Migration from Standalone Setup

If you previously used a standalone webhook handler, migrate by:

1. Removing the standalone webhook handler deployment
2. Updating GitLab webhooks to point to the CI Bridge endpoints
3. Adding the new configuration variables to the CI Bridge
4. Testing the integration with existing workflows

## Limitations

- **Main branch only**: Workflows always run on the main branch regardless of GitLab branch
- **Repository dispatch limits**: GitHub has rate limits on repository dispatch events
- **GitHub App scope**: Only repositories with the GitHub App installed can be triggered
- **Configuration updates**: Require CI Bridge restart to take effect