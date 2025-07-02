# GitLab to GitHub Job Trigger Bridge

This system allows GitLab CI jobs to trigger GitHub Actions workflows when they finish. All configuration lives in the GitHub repository as requested.

## Overview

The system consists of:
1. **GitHub Actions Workflow** (`.github/workflows/gitlab-trigger.yml`) - Triggered when GitLab jobs finish
2. **Webhook Handler Service** (`webhook-handler.py`) - Receives GitLab webhooks and triggers GitHub workflows
3. **GitLab Webhook Configuration** - Sends job completion events to the webhook handler

## Setup Instructions

### 1. GitHub Configuration

#### Create GitHub Personal Access Token
1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate a new token with the following permissions:
   - `repo` (Full control of private repositories)
   - `workflow` (Update GitHub Action workflows)
3. Save the token securely - you'll need it for the webhook handler

#### GitHub Actions Workflow
The workflow is already configured in `.github/workflows/gitlab-trigger.yml`. It:
- Listens for `repository_dispatch` events with type `gitlab-job-finished`
- Always checks out the `main` branch as requested
- Receives GitLab job information via the event payload
- Runs tests and custom actions based on job status

### 2. Webhook Handler Service Deployment

The webhook handler (`webhook-handler.py`) needs to be deployed to a publicly accessible server.

#### Environment Variables
Set these environment variables where you deploy the service:

```bash
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPO=your-username/your-repo-name  # e.g., "octocat/Hello-World"
GITLAB_WEBHOOK_SECRET=your_webhook_secret  # Optional but recommended
PORT=5000  # Optional, defaults to 5000
```

#### Deployment Options

##### Option A: Deploy to Heroku
1. Create a new Heroku app
2. Set the environment variables in Heroku config vars
3. Deploy this repository to Heroku
4. The service will be available at `https://your-app.herokuapp.com`

##### Option B: Deploy to your own server
1. Install dependencies: `pip install flask requests`
2. Set environment variables
3. Run: `python webhook-handler.py`
4. Make sure the service is accessible from the internet

##### Option C: Use the existing Docker setup
1. Build the Docker image: `docker build -t gitlab-github-bridge .`
2. Run with environment variables:
   ```bash
   docker run -p 5000:5000 \
     -e GITHUB_TOKEN=your_token \
     -e GITHUB_REPO=owner/repo \
     -e GITLAB_WEBHOOK_SECRET=your_secret \
     gitlab-github-bridge
   ```

### 3. GitLab Configuration

#### Configure GitLab Webhook
1. Go to your GitLab project → Settings → Webhooks
2. Add a new webhook with:
   - **URL**: `https://your-webhook-handler-domain.com/webhook/gitlab`
   - **Secret Token**: Same as `GITLAB_WEBHOOK_SECRET` (optional but recommended)
   - **Trigger Events**: Check "Job events"
   - **Enable SSL verification**: ✓ (recommended)

#### Update GitLab CI Configuration
Your existing `.gitlab-ci.yml` works as-is. The webhook will trigger for any job completion.

If you want to trigger GitHub workflows only for specific jobs, you can add conditions in the webhook handler or modify the GitLab CI configuration.

## Testing the Setup

### 1. Test the Webhook Handler
```bash
# Health check
curl https://your-webhook-handler-domain.com/health

# Should return: {"status": "healthy", "service": "gitlab-github-bridge"}
```

### 2. Test GitLab Integration
1. Push a commit to your GitLab repository
2. Wait for the GitLab CI job to complete
3. Check GitHub Actions tab - you should see the "GitLab Triggered Workflow" running

### 3. Manual Testing
You can manually trigger the GitHub workflow using the GitHub API:

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

## Customization

### Modify GitHub Actions Workflow
Edit `.github/workflows/gitlab-trigger.yml` to customize what happens when GitLab jobs finish:
- Add deployment steps
- Run different tests
- Send notifications
- Update documentation

### Filter GitLab Events
Modify the webhook handler (`webhook-handler.py`) to:
- Only trigger on specific job names
- Filter by branch names
- Add custom logic based on GitLab payload

### Security Considerations
1. **Use webhook secrets** to verify GitLab requests
2. **Limit GitHub token permissions** to only what's needed
3. **Use HTTPS** for all webhook communications
4. **Monitor webhook handler logs** for suspicious activity

## Troubleshooting

### Common Issues

1. **GitHub workflow not triggering**
   - Check webhook handler logs
   - Verify GitHub token permissions
   - Ensure repository dispatch event type matches workflow configuration

2. **Webhook handler not receiving requests**
   - Verify GitLab webhook URL is accessible
   - Check GitLab webhook delivery logs
   - Ensure webhook handler is running and accessible

3. **Authentication errors**
   - Verify GitHub token is valid and has correct permissions
   - Check that GITHUB_REPO format is correct (owner/repo)

### Debug Mode
Set environment variable `FLASK_ENV=development` for detailed error messages.

### Logs
Check webhook handler logs for detailed information about received requests and GitHub API calls.

## Architecture

```
GitLab CI Job Completes
        ↓
   Webhook Sent
        ↓
  Webhook Handler
        ↓
   GitHub API Call
        ↓
 GitHub Actions Workflow Triggered
        ↓
   Actions Run on Main Branch
```

This setup ensures that GitHub workflows are triggered reliably when GitLab jobs finish, with all configuration living in the GitHub repository as requested.