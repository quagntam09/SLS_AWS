#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="${STACK_NAME:-NSGA2IS-SLS-dev}"
GIT_REPO_URL="${GIT_REPO_URL:-https://github.com/quagntam09/SLS_AWS.git}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"

APP_NAME="nsga2is-sls"
APP_DIR="/opt/${APP_NAME}"
REPO_DIR="${APP_DIR}/NSGA2IS-SLS"
SERVICE_NAME="${APP_NAME}-worker"
SERVICE_USER="ubuntu"
ENV_FILE="/etc/${APP_NAME}-worker.env"
SYSTEMD_UNIT="/etc/systemd/system/${SERVICE_NAME}.service"

export AWS_DEFAULT_REGION="${AWS_REGION}"
export AWS_PAGER=""

log() {
  printf '[ec2-worker-setup] %s\n' "$*"
}

require_non_placeholder() {
  local var_name="$1"
  local var_value="$2"

  if [[ -z "${var_value}" || "${var_value}" == "<REPLACE_ME>" || "${var_value}" == "REPLACE_ME" || "${var_value}" == \<*\> ]]; then
    log "Biến ${var_name} chưa được cấu hình. Hãy điền giá trị thật vào đầu file ec2_worker_setup.sh."
    exit 1
  fi
}

detect_os() {
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    printf '%s' "${ID:-unknown}"
  else
    printf 'unknown'
  fi
}

install_packages_ubuntu() {
  export DEBIAN_FRONTEND=noninteractive
  log "Cập nhật package index"
  apt-get update
  log "Cài gói hệ thống cần thiết cho Ubuntu 24.04"
  apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    python3-pip \
    unzip
}

install_prerequisites() {
  local os_id
  os_id="$(detect_os)"

  case "${os_id}" in
    ubuntu)
      install_packages_ubuntu
      ;;
    *)
      log "Hệ điều hành không được hỗ trợ: ${os_id}. Script này được thiết kế cho Ubuntu 24.04 LTS."
      exit 1
      ;;
  esac
}

install_aws_cli_v2() {
  local tmp_dir
  tmp_dir="$(mktemp -d)"

  log "Tải AWS CLI v2 từ awscli.amazonaws.com"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "${tmp_dir}/awscliv2.zip"
  unzip -q "${tmp_dir}/awscliv2.zip" -d "${tmp_dir}"
  "${tmp_dir}/aws/install" --update
  rm -rf "${tmp_dir}"
}

require_stack_output() {
  local output_key="$1"
  local value

  if ! value="$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --no-cli-pager \
    --query "Stacks[0].Outputs[?OutputKey=='${output_key}'].OutputValue | [0]" \
    --output text 2>&1)"; then
    if [[ "${value}" == *ValidationError* ]]; then
      log "Không tìm thấy CloudFormation stack '${STACK_NAME}' ở region '${AWS_REGION}'. Kiểm tra lại STACK_NAME và AWS_REGION rồi thử lại."
      exit 1
    fi

    log "Không thể đọc output '${output_key}' từ CloudFormation: ${value}"
    exit 1
  fi

  if [[ -z "${value}" || "${value}" == "None" ]]; then
    log "Stack '${STACK_NAME}' không có output '${output_key}'."
    exit 1
  fi

  printf '%s' "${value}"
}

prepare_source() {
  log "Chuẩn bị source code tại ${APP_DIR}"
  rm -rf "${APP_DIR}"
  git clone "${GIT_REPO_URL}" "${APP_DIR}"
  chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"
}

create_virtualenv() {
  log "Tạo virtualenv Python 3.12"
  python3.12 -m venv "${REPO_DIR}/.venv"
  "${REPO_DIR}/.venv/bin/pip" install --upgrade pip
  log "Cài dependencies từ ${REPO_DIR}/requirements.txt"
  "${REPO_DIR}/.venv/bin/pip" install -r "${REPO_DIR}/requirements.txt"
}

write_env_file() {
  local queue_url="$1"
  local table_name="$2"
  local bucket_name="$3"

  log "Ghi file environment ${ENV_FILE}"
  cat >"${ENV_FILE}" <<EOF
AWS_REGION=${AWS_REGION}
APP_ENV=production
QUEUE_URL=${queue_url}
TABLE_NAME=${table_name}
BUCKET_NAME=${bucket_name}
EOF
  chown "${SERVICE_USER}:${SERVICE_USER}" "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
}

write_systemd_unit() {
  log "Tạo systemd service ${SERVICE_NAME}"
  cat >"${SYSTEMD_UNIT}" <<EOF
[Unit]
Description=NSGA2IS-SLS background worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
Environment=PYTHONPATH=${APP_DIR}/NSGA2IS-SLS
ExecStart=${REPO_DIR}/.venv/bin/python -m server.app.worker
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
}

main() {
  require_non_placeholder "STACK_NAME" "${STACK_NAME}"
  require_non_placeholder "GIT_REPO_URL" "${GIT_REPO_URL}"
  require_non_placeholder "AWS_REGION" "${AWS_REGION}"

  log "Bắt đầu khởi tạo worker EC2"
  install_prerequisites

  if command -v aws >/dev/null 2>&1; then
    log "AWS CLI đã có sẵn trên máy"
  else
    log "Cài AWS CLI v2 theo cách tương thích với Ubuntu 24.04"
    install_aws_cli_v2
  fi

  log "Lấy outputs từ CloudFormation stack ${STACK_NAME}"
  local queue_url
  local table_name
  local bucket_name

  queue_url="$(require_stack_output "ScheduleJobsQueueUrl")"
  table_name="$(require_stack_output "ScheduleRequestsTableName")"
  bucket_name="$(require_stack_output "ScheduleResultsBucketName")"

  prepare_source
  create_virtualenv
  write_env_file "${queue_url}" "${table_name}" "${bucket_name}"
  write_systemd_unit

  log "Reload systemd và khởi động service"
  systemctl daemon-reload
  systemctl enable --now "${SERVICE_NAME}"

  log "Hoàn tất. Service đang chạy: ${SERVICE_NAME}"
}

main "$@"