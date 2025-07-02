#!/bin/bash

# Test script for GitLab to GitHub webhook handler
# Usage: ./test-webhook.sh [webhook_url]

WEBHOOK_URL=${1:-"http://localhost:5000/webhook/gitlab"}

echo "Testing GitLab webhook handler at: $WEBHOOK_URL"

# Sample GitLab job completion payload
cat > payload.json << 'EOF'
{
  "object_kind": "build",
  "ref": "main",
  "tag": null,
  "before_sha": "2293ada6b400935a1378653304eaf6221e0fdb8f",
  "sha": "2293ada6b400935a1378653304eaf6221e0fdb8f",
  "build_id": 1977,
  "build_name": "test",
  "build_stage": "test",
  "build_status": "success",
  "build_started_at": "2016-01-11T10:13:28.000Z",
  "build_finished_at": "2016-01-11T10:15:28.000Z",
  "build_duration": 120,
  "build_allow_failure": false,
  "build_failure_reason": null,
  "pipeline_id": 2366,
  "project_id": 380,
  "project_name": "gitlab-test",
  "user": {
    "id": 1,
    "name": "Root",
    "username": "root",
    "state": "active",
    "avatar_url": "http://www.gravatar.com/avatar/avatar.png",
    "web_url": "http://localhost/root"
  },
  "commit": {
    "id": 2366,
    "sha": "2293ada6b400935a1378653304eaf6221e0fdb8f",
    "message": "Test commit",
    "author_name": "Test User",
    "author_email": "test@example.com",
    "status": "success",
    "duration": 120,
    "started_at": "2016-01-11T10:13:28.000Z",
    "finished_at": "2016-01-11T10:15:28.000Z"
  },
  "project": {
    "id": 380,
    "name": "gitlab-test",
    "description": "Test project",
    "web_url": "http://example.com/gitlab/gitlab-test",
    "avatar_url": null,
    "git_ssh_url": "git@example.com:gitlab/gitlab-test.git",
    "git_http_url": "http://example.com/gitlab/gitlab-test.git",
    "namespace": "gitlab",
    "visibility_level": 20,
    "path_with_namespace": "gitlab/gitlab-test",
    "default_branch": "main"
  }
}
EOF

echo "Sending test payload..."

# Send the webhook with optional secret token
if [ -n "$GITLAB_WEBHOOK_SECRET" ]; then
    echo "Using webhook secret for authentication"
    SIGNATURE=$(echo -n "$(cat payload.json)" | openssl dgst -sha256 -hmac "$GITLAB_WEBHOOK_SECRET" -binary | xxd -p)
    curl -X POST \
        -H "Content-Type: application/json" \
        -H "X-Gitlab-Token: $SIGNATURE" \
        -d @payload.json \
        "$WEBHOOK_URL"
else
    echo "No webhook secret provided - sending without authentication"
    curl -X POST \
        -H "Content-Type: application/json" \
        -d @payload.json \
        "$WEBHOOK_URL"
fi

echo -e "\n\nTest completed!"

# Cleanup
rm payload.json

echo "Check your GitHub Actions tab to see if the workflow was triggered."