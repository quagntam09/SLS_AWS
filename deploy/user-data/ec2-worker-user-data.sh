#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="${STACK_NAME:-<REPLACE_ME>}"
GIT_REPO_URL="${GIT_REPO_URL:-<REPLACE_ME>}"
AWS_REGION="${AWS_REGION:-<REPLACE_ME>}"

BOOTSTRAP_DIR="/opt/nsga2is-sls-bootstrap"

log() {
  printf '[ec2-worker-user-data] %s\n' "$*"
}

require_non_placeholder() {
  local var_name="$1"
  local var_value="$2"

  if [[ -z "${var_value}" || "${var_value}" == "<REPLACE_ME>" ]]; then
    log "Thiếu biến ${var_name}. Hãy truyền qua user-data hoặc Launch Template."
    exit 1
  fi
}

main() {
  require_non_placeholder "STACK_NAME" "${STACK_NAME}"
  require_non_placeholder "GIT_REPO_URL" "${GIT_REPO_URL}"
  require_non_placeholder "AWS_REGION" "${AWS_REGION}"

  log "Cài git để clone source"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends git

  log "Clone repo bootstrap vào ${BOOTSTRAP_DIR}"
  rm -rf "${BOOTSTRAP_DIR}"
  git clone "${GIT_REPO_URL}" "${BOOTSTRAP_DIR}"

  log "Chạy ec2_worker_setup.sh từ repo đã clone"
  cd "${BOOTSTRAP_DIR}"
  STACK_NAME="${STACK_NAME}" \
  GIT_REPO_URL="${GIT_REPO_URL}" \
  AWS_REGION="${AWS_REGION}" \
    bash ./ec2_worker_setup.sh
}

main "$@"