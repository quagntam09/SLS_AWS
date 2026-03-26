#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="${STACK_NAME:-<REPLACE_ME>}"
GIT_REPO_URL="${GIT_REPO_URL:-<REPLACE_ME>}"
AWS_REGION="${AWS_REGION:-<REPLACE_ME>}"
SERVER_NAME="${SERVER_NAME:-<REPLACE_ME_OR_USE_>}"
APP_ENV="${APP_ENV:-production}"
APP_CORS_ALLOW_ORIGINS="${APP_CORS_ALLOW_ORIGINS:-http://localhost:3000}"

APP_NAME="nsga2is-sls"
APP_DIR="/opt/${APP_NAME}"
REPO_DIR="${APP_DIR}/NSGA2IS-SLS"
SERVICE_NAME="${APP_NAME}-api"
SERVICE_USER="ubuntu"
ENV_FILE="/etc/${APP_NAME}-api.env"
SYSTEMD_UNIT="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_SITE_AVAILABLE="/etc/nginx/sites-available/${SERVICE_NAME}"
NGINX_SITE_ENABLED="/etc/nginx/sites-enabled/${SERVICE_NAME}"

export AWS_DEFAULT_REGION="${AWS_REGION}"
export AWS_PAGER=""

log() {
  printf '[ec2-api-setup] %s\n' "$*"
}

require_non_placeholder() {
  local var_name="$1"
  local var_value="$2"

  if [[ -z "${var_value}" || "${var_value}" == "<REPLACE_ME>" || "${var_value}" == "<REPLACE_ME_OR_USE_>" ]]; then
    log "Biến ${var_name} chưa được cấu hình. Hãy điền giá trị thật vào đầu file ec2_api_setup.sh."
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
  log "Cài gói hệ thống cần thiết cho Ubuntu"
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
}

install_prerequisites() {
  local os_id
  os_id="$(detect_os)"

  case "${os_id}" in
    ubuntu)
      install_packages_ubuntu
      ;;
    *)
      log "Hệ điều hành không được hỗ trợ: ${os_id}. Script này được thiết kế cho Ubuntu."
      exit 1
      ;;
  esac
}

install_aws_cli_v2() {
  local tmp_dir
  tmp_dir="$(mktemp -d)"

  log "Tải AWS CLI v2"
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
  log "Ghi file environment ${ENV_FILE}"
  cat >"${ENV_FILE}" <<EOF
AWS_REGION=${AWS_REGION}
APP_ENV=${APP_ENV}
APP_CORS_ALLOW_ORIGINS=${APP_CORS_ALLOW_ORIGINS}
QUEUE_URL=${QUEUE_URL}
TABLE_NAME=${TABLE_NAME}
BUCKET_NAME=${BUCKET_NAME}
SCHEDULE_QUEUE_URL=${QUEUE_URL}
SCHEDULE_TABLE_NAME=${TABLE_NAME}
SCHEDULE_RESULTS_BUCKET=${BUCKET_NAME}
EOF
  chmod 600 "${ENV_FILE}"
}

write_systemd_unit() {
  log "Tạo systemd service ${SERVICE_NAME}"
  cat >"${SYSTEMD_UNIT}" <<EOF
[Unit]
Description=NSGA2IS-SLS FastAPI API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
Environment=PYTHONPATH=${REPO_DIR}
ExecStart=${REPO_DIR}/.venv/bin/uvicorn server.app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
}

write_nginx_config() {
  log "Tạo nginx reverse proxy"
  cat >"${NGINX_SITE_AVAILABLE}" <<EOF
server {
    listen 80;
    server_name ${SERVER_NAME};

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
    }
}
EOF

  ln -sf "${NGINX_SITE_AVAILABLE}" "${NGINX_SITE_ENABLED}"
  rm -f /etc/nginx/sites-enabled/default
}

main() {
  require_non_placeholder "STACK_NAME" "${STACK_NAME}"
  require_non_placeholder "GIT_REPO_URL" "${GIT_REPO_URL}"
  require_non_placeholder "AWS_REGION" "${AWS_REGION}"
  require_non_placeholder "SERVER_NAME" "${SERVER_NAME}"

  log "Bắt đầu khởi tạo EC2 API"
  install_prerequisites

  if command -v aws >/dev/null 2>&1; then
    log "AWS CLI đã có sẵn trên máy"
  else
    log "Cài AWS CLI v2"
    install_aws_cli_v2
  fi

  log "Lấy outputs từ CloudFormation stack ${STACK_NAME}"
  QUEUE_URL="$(require_stack_output "ScheduleJobsQueueUrl")"
  TABLE_NAME="$(require_stack_output "ScheduleRequestsTableName")"
  BUCKET_NAME="$(require_stack_output "ScheduleResultsBucketName")"

  prepare_source
  create_virtualenv
  write_env_file
  write_systemd_unit
  write_nginx_config

  log "Reload systemd và khởi động API"
  systemctl daemon-reload
  systemctl enable --now "${SERVICE_NAME}"
  nginx -t
  systemctl restart nginx

  log "Hoàn tất. API đang chạy qua systemd service ${SERVICE_NAME}"
}

main "$@"