# GitLab to GitHub Workflow Triggering

This feature allows the CI Bridge to trigger GitHub Actions workflows when GitLab CI jobs finish. When a GitLab job completes (success, failure, or other configured statuses), the system automatically checks the target repository for compatible workflows and triggers them on the main branch.

## Overview

The GitLab to GitHub triggering functionality extends the existing CI Bridge capabilities by:

1. **Monitoring GitLab job completions** - Listening for GitLab job hook events
2. **Filtering by job status** - Only triggering on configured job statuses (e.g., success, failed)
3. **Auto-detecting target repositories** - Uses the repository where GitLab status is posted
4. **Workflow detection** - Automatically checks if repository has compatible workflows
5. **Using repository dispatch** - Sending GitHub repository dispatch events to trigger workflows
6. **Running on main branch** - Always triggering workflows on the main branch as requested

## Configuration

Add the following environment variables to enable GitLab to GitHub triggering:

### Required Configuration

```bash
# Enable the feature
ENABLE_GITLAB_TO_GITHUB_TRIGGERING=true
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
GITLAB_TO_GITHUB_TRIGGER_ON_STATUS=["success"]
```

## How It Works

1. **GitLab job completes** - A GitLab CI job finishes with a configured status
2. **Repository identification** - The system uses the repository URL from the GitLab bridge payload
3. **Workflow detection** - Checks if the repository has workflows listening for `repository_dispatch` events with type `gitlab-job-finished`
4. **Conditional triggering** - Only triggers if compatible workflows are found
5. **Workflow execution** - GitHub workflow runs on the main branch with GitLab job data

## GitHub Actions Workflow

The system triggers GitHub workflows using the `repository_dispatch` event type `gitlab-job-finished`. You need to create a workflow in your target repository that listens for these events.

### Creating a Workflow

Create a file like `.github/workflows/gitlab-trigger.yml` in your target repository:

```yaml
name: GitLab Job Triggered Workflow

on:
  repository_dispatch:
    types: [gitlab-job-finished]

jobs:
  gitlab-triggered-job:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          ref: main  # Always use main branch
          
      - name: Display GitLab job information
        run: |
          echo "🚀 GitLab job has finished!"
          echo "📊 Job Status: ${{ github.event.client_payload.job_status }}"
          echo "🔧 Job Name: ${{ github.event.client_payload.job_name }}"
          echo "🆔 Job ID: ${{ github.event.client_payload.job_id }}"
          echo "🔗 Job URL: ${{ github.event.client_payload.job_url }}"
          echo "📁 Project: ${{ github.event.client_payload.project_name }}"
          echo "🌿 Branch: ${{ github.event.client_payload.ref }}"
          echo "📝 Commit SHA: ${{ github.event.client_payload.commit_sha }}"
          
      - name: Custom actions based on GitLab job status
        run: |
          JOB_STATUS="${{ github.event.client_payload.job_status }}"
          JOB_NAME="${{ github.event.client_payload.job_name }}"
          ALLOW_FAILURE="${{ github.event.client_payload.allow_failure }}"
          
          if [[ "$JOB_STATUS" == "success" ]]; then
            echo "✅ GitLab job succeeded - running success actions"
            # Add your success-specific commands here
          elif [[ "$JOB_STATUS" == "failed" ]]; then
            if [[ "$ALLOW_FAILURE" == "true" ]]; then
              echo "⚠️ GitLab job failed but failure is allowed"
            else
              echo "❌ GitLab job failed - running failure actions"
              # Add your failure-specific commands here
            fi
          fi
```

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
   - Ensure the target repository has a workflow listening for `repository_dispatch` events with type `gitlab-job-finished`
   - Verify GitHub App has access to the repository
   - Check CI Bridge logs for error messages

2. **"No GitLab workflow triggers found" message**
   - Verify your workflow file contains both `repository_dispatch` and `gitlab-job-finished` in the content
   - Ensure the workflow file is committed to the repository
   - Check the workflow file is in `.github/workflows/` directory

3. **Workflow receives no data**
   - Verify workflow listens for `repository_dispatch` with type `gitlab-job-finished`
   - Check that GitLab job completed with a configured trigger status
   - Ensure the repository is where GitLab CI status is being posted

### Debug Logging

Enable debug logging to troubleshoot issues:

```bash
OVERRIDE_LOGGING=DEBUG
```

Look for log messages like:
- `"GitLab to GitHub triggering is enabled, checking repository for workflows"`
- `"Checking repository owner/repo for GitLab workflow triggers"`
- `"Found GitLab workflow trigger in owner/repo: .github/workflows/example.yml"`
- `"Repository owner/repo has GitLab workflow triggers, proceeding"`
- `"Successfully triggered GitHub workflow (GitLab job: job-name, status: success)"`

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

## Limitations

- **Main branch only**: Workflows always run on the main branch regardless of GitLab branch
- **Repository dispatch limits**: GitHub has rate limits on repository dispatch events
- **GitHub App scope**: Only repositories with the GitHub App installed can be triggered
- **Workflow detection**: Uses simple text search for `repository_dispatch` and `gitlab-job-finished` in workflow files
- **Configuration updates**: Require CI Bridge restart to take effect