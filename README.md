# CI Bridge

This piece of software acts as a relay between GitHub and the GitLab CI service. It receives webhooks from GitHub repos that it is installed on, and triggers GitLab jobs based on job configuration that is stored in the GitHub repo. It then waits and listens for webhook events from GitLab when the triggered jobs have state transitions, and relays this information back to the GitHub side, also creating commit statuses that can be used in PR reviews, among other things.

## Features

### GitHub → GitLab Integration
- Triggers GitLab CI pipelines when GitHub events occur (push, PR, etc.)
- Creates GitHub check runs with GitLab job status and logs
- Supports team-based access control and job filtering

### GitLab → GitHub Integration  
- **NEW**: Triggers GitHub Actions workflows when GitLab jobs finish
- Configurable target repositories and job status filters
- Always runs workflows on the main branch
- Provides detailed GitLab job information to GitHub workflows

For detailed setup and configuration of the GitLab to GitHub triggering feature, see [docs/GITLAB_TO_GITHUB_TRIGGERING.md](docs/GITLAB_TO_GITHUB_TRIGGERING.md).
