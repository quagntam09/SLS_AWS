#!/usr/bin/env bash
set -euo pipefail

# Fill these values before pasting into the AWS Console Launch Template user-data box.
STACK_NAME="NSGA2IS-SLS-dev"
GIT_REPO_URL="https://github.com/<owner>/<repo>.git"
AWS_REGION="ap-southeast-1"
SERVER_NAME="_"

# Optional overrides for the API service.
APP_ENV="production"
APP_CORS_ALLOW_ORIGINS="http://localhost:3000"

BOOTSTRAP_DIR="/opt/nsga2is-sls-bootstrap"
LOG_PREFIX='[launch-template-user-data]'

log() {
  printf '%s %s\n' "$LOG_PREFIX" "$*"
}

require_value() {
  local name="$1"
  local value="$2"

  if [[ -z "$value" || "$value" == *"<owner>"* || "$value" == *"<repo>"* ]]; then
    log "Missing or placeholder value for ${name}. Update the variables at the top of this user-data script."
    exit 1
  fi
}

log "Starting EC2 bootstrap for NSGA2IS-SLS API"

require_value "STACK_NAME" "$STACK_NAME"
require_value "GIT_REPO_URL" "$GIT_REPO_URL"
require_value "AWS_REGION" "$AWS_REGION"
require_value "SERVER_NAME" "$SERVER_NAME"

export DEBIAN_FRONTEND=noninteractive
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PAGER=""

log "Installing required packages"
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  git \
  nginx \
  python3.12 \
  python3.12-dev \
  python3.12-venv \
  python3-pip \
  unzip

log "Checking out repository to ${BOOTSTRAP_DIR}"
rm -rf "$BOOTSTRAP_DIR"
git clone "$GIT_REPO_URL" "$BOOTSTRAP_DIR"

cd "$BOOTSTRAP_DIR"

log "Running EC2 API setup script"
STACK_NAME="$STACK_NAME" \
GIT_REPO_URL="$GIT_REPO_URL" \
AWS_REGION="$AWS_REGION" \
SERVER_NAME="$SERVER_NAME" \
APP_ENV="$APP_ENV" \
APP_CORS_ALLOW_ORIGINS="$APP_CORS_ALLOW_ORIGINS" \
  bash ./ec2_api_setup.sh

log "Bootstrap completed"
