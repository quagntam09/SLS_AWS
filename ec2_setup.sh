#!/usr/bin/env bash
set -euo pipefail

# --- KHAI BÁO CẤU HÌNH BẮT BUỘC ---
export STACK_NAME="NSGA2IS-SLS-dev" # Đổi nếu stack Serverless của bạn dùng tên khác
export GIT_REPO_URL="https://github.com/quagntam09/SLS_AWS.git" # Repo nguồn của dự án hiện tại
export AWS_REGION="ap-southeast-1"
# ----------------------------------

APP_NAME="nsga2is-sls"
APP_DIR="/opt/${APP_NAME}"
SERVICE_NAME="${APP_NAME}-worker"
SERVICE_USER="ec2-user"
GIT_BRANCH="${GIT_BRANCH:-main}"
SCHEDULE_QUEUE_URL="${SCHEDULE_QUEUE_URL:-}"
SCHEDULE_TABLE_NAME="${SCHEDULE_TABLE_NAME:-}"
SCHEDULE_RESULTS_BUCKET="${SCHEDULE_RESULTS_BUCKET:-}"

log() {
  echo "[ec2-setup] $*"
}

detect_os() {
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    echo "${ID:-unknown}"
  else
    echo "unknown"
  fi
}

install_packages_ubuntu() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y software-properties-common git curl ca-certificates jq unzip
  add-apt-repository -y ppa:deadsnakes/ppa
  apt-get update
  apt-get install -y python3.12 python3.12-venv python3.12-dev python3-pip
}

install_packages_amazon_linux() {
  dnf install -y git curl jq awscli python3.12 python3.12-pip python3.12-devel
}

install_prerequisites() {
  local os_id
  os_id="$(detect_os)"

  case "${os_id}" in
    ubuntu)
      install_packages_ubuntu
      SERVICE_USER="ubuntu"
      ;;
    amzn|amazon)
      install_packages_amazon_linux
      SERVICE_USER="ec2-user"
      ;;
    *)
      log "Unsupported OS: ${os_id}"
      exit 1
      ;;
  esac
}

fetch_stack_outputs() {
  if [[ -n "${STACK_NAME}" ]] && command -v aws >/dev/null 2>&1; then
    if [[ -z "${SCHEDULE_QUEUE_URL}" ]]; then
      SCHEDULE_QUEUE_URL="$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --region "${AWS_REGION}" \
        --query "Stacks[0].Outputs[?OutputKey=='ScheduleJobsQueueUrl'].OutputValue | [0]" \
        --output text)"
    fi
    if [[ -z "${SCHEDULE_TABLE_NAME}" ]]; then
      SCHEDULE_TABLE_NAME="$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --region "${AWS_REGION}" \
        --query "Stacks[0].Outputs[?OutputKey=='ScheduleRequestsTableName'].OutputValue | [0]" \
        --output text)"
    fi
    if [[ -z "${SCHEDULE_RESULTS_BUCKET}" ]]; then
      SCHEDULE_RESULTS_BUCKET="$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --region "${AWS_REGION}" \
        --query "Stacks[0].Outputs[?OutputKey=='ScheduleResultsBucketName'].OutputValue | [0]" \
        --output text)"
    fi
  fi
}

prepare_source() {
  mkdir -p /opt
  if [[ -f "${APP_DIR}/requirements.txt" && -d "${APP_DIR}/server" ]]; then
    log "Repository already present at ${APP_DIR}"
    return
  fi

  if [[ -z "${GIT_REPO_URL}" ]]; then
    log "Set GIT_REPO_URL to clone the source code, or pre-copy the repo to ${APP_DIR}."
    exit 1
  fi

  rm -rf "${APP_DIR}"
  git clone --branch "${GIT_BRANCH}" --single-branch "${GIT_REPO_URL}" "${APP_DIR}"
}

create_virtualenv() {
  python3.12 -m venv "${APP_DIR}/.venv"
  "${APP_DIR}/.venv/bin/pip" install --upgrade pip
  "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
}

install_aws_cli_v2() {
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "${tmp_dir}/awscliv2.zip"
  unzip -q "${tmp_dir}/awscliv2.zip" -d "${tmp_dir}"
  "${tmp_dir}/aws/install" --update
  rm -rf "${tmp_dir}"
}

write_env_file() {
  cat >/etc/${APP_NAME}.env <<EOF
AWS_REGION=${AWS_REGION}
APP_ENV=production
PYTHONPATH=${APP_DIR}/server
SCHEDULE_QUEUE_URL=${SCHEDULE_QUEUE_URL}
SCHEDULE_TABLE_NAME=${SCHEDULE_TABLE_NAME}
SCHEDULE_RESULTS_BUCKET=${SCHEDULE_RESULTS_BUCKET}
EOF
  chmod 600 /etc/${APP_NAME}.env
}

write_service_file() {
  cat >/etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=NSGA2IS-SLS SQS worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=/etc/${APP_NAME}.env
ExecStart=${APP_DIR}/.venv/bin/python -m app.worker
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF
}

main() {
  log "Installing prerequisites"
  install_prerequisites

  if command -v aws >/dev/null 2>&1; then
    log "AWS CLI already present"
  else
    log "Installing AWS CLI v2"
    install_aws_cli_v2
  fi

  log "Fetching stack outputs if available"
  fetch_stack_outputs

  if [[ -z "${SCHEDULE_QUEUE_URL}" || -z "${SCHEDULE_TABLE_NAME}" || -z "${SCHEDULE_RESULTS_BUCKET}" ]]; then
    log "Missing required runtime settings. Provide SCHEDULE_QUEUE_URL, SCHEDULE_TABLE_NAME, and SCHEDULE_RESULTS_BUCKET or set STACK_NAME."
    exit 1
  fi

  log "Preparing source code"
  prepare_source

  log "Creating virtual environment and installing Python dependencies"
  create_virtualenv

  log "Writing environment file"
  write_env_file

  log "Installing systemd service"
  write_service_file
  systemctl daemon-reload
  systemctl enable --now "${SERVICE_NAME}"

  log "Worker service started: ${SERVICE_NAME}"
}

main "$@"