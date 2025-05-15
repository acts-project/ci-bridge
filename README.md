# CI Bridge

This piece of software acts as a relay between GitHub and the GitLab CI service. It receives webhooks from GitHub repos that it is installed on, and triggers GitLab jobs based on job configuration that is stored in the GitHub repo. It then waits and listens for webhook events from GitLab when the triggered jobs have state transitions, and relays this information back to the GitHub side, also creating commit statuses that can be used in PR reviews, among other things.V
