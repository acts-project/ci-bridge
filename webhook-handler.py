#!/usr/bin/env python3
"""
GitLab to GitHub Webhook Handler

This script receives GitLab webhooks when jobs finish and triggers GitHub workflows
via the repository_dispatch API.
"""

import os
import json
import hmac
import hashlib
import requests
from flask import Flask, request, jsonify
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - set these environment variables
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO')  # format: owner/repo
GITLAB_WEBHOOK_SECRET = os.environ.get('GITLAB_WEBHOOK_SECRET')

def verify_gitlab_webhook(payload, signature, secret):
    """Verify GitLab webhook signature"""
    if not signature or not secret:
        return False
    
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)

def trigger_github_workflow(payload_data):
    """Trigger GitHub workflow via repository dispatch"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.error("GitHub token or repo not configured")
        return False
    
    # Prepare payload for GitHub
    github_payload = {
        "event_type": "gitlab-job-finished",
        "client_payload": {
            "job_status": payload_data.get("build_status"),
            "job_name": payload_data.get("build_name"),
            "project_name": payload_data.get("project", {}).get("name"),
            "ref": payload_data.get("ref"),
            "commit_sha": payload_data.get("sha"),
            "pipeline_url": payload_data.get("project", {}).get("web_url"),
            "gitlab_payload": payload_data  # Include full GitLab payload for advanced use
        }
    }
    
    # GitHub API endpoint
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=github_payload, headers=headers)
        response.raise_for_status()
        logger.info(f"Successfully triggered GitHub workflow for job: {payload_data.get('build_name')}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to trigger GitHub workflow: {e}")
        return False

@app.route('/webhook/gitlab', methods=['POST'])
def gitlab_webhook():
    """Handle GitLab webhook"""
    try:
        # Get the payload
        payload = request.get_data()
        
        # Verify webhook signature if secret is configured
        if GITLAB_WEBHOOK_SECRET:
            signature = request.headers.get('X-Gitlab-Token')
            if not verify_gitlab_webhook(payload, signature, GITLAB_WEBHOOK_SECRET):
                logger.warning("Invalid GitLab webhook signature")
                return jsonify({"error": "Invalid signature"}), 401
        
        # Parse JSON payload
        data = json.loads(payload)
        
        # Check if this is a job event
        if data.get('object_kind') != 'build':
            logger.info(f"Ignoring non-build event: {data.get('object_kind')}")
            return jsonify({"message": "Event ignored"}), 200
        
        # Check if job is finished
        build_status = data.get('build_status')
        if build_status not in ['success', 'failed', 'canceled']:
            logger.info(f"Job not finished yet, status: {build_status}")
            return jsonify({"message": "Job not finished"}), 200
        
        logger.info(f"GitLab job finished: {data.get('build_name')} - {build_status}")
        
        # Trigger GitHub workflow
        success = trigger_github_workflow(data)
        
        if success:
            return jsonify({"message": "GitHub workflow triggered successfully"}), 200
        else:
            return jsonify({"error": "Failed to trigger GitHub workflow"}), 500
            
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload")
        return jsonify({"error": "Invalid JSON"}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "gitlab-github-bridge"}), 200

if __name__ == '__main__':
    # Validate required environment variables
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN environment variable is required")
        exit(1)
    
    if not GITHUB_REPO:
        logger.error("GITHUB_REPO environment variable is required")
        exit(1)
    
    logger.info(f"Starting webhook handler for GitHub repo: {GITHUB_REPO}")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))