#!/usr/bin/env bash
set -euo pipefail

TAG="${1:-latest}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
ECR_REPOSITORY="${ECR_REPOSITORY:-nsga2is-sls-worker}"
STACK_NAME="${STACK_NAME:-nsga2is-sls-worker-fargate}"
TEMPLATE_FILE="${TEMPLATE_FILE:-deploy/ecs-fargate/worker-fargate-stack.yaml}"
VPC_ID="${VPC_ID:-}"
SUBNET_IDS="${SUBNET_IDS:-}"
QUEUE_ARN="${QUEUE_ARN:-}"
TABLE_NAME="${TABLE_NAME:-}"
BUCKET_NAME="${BUCKET_NAME:-}"
CPU="${CPU:-2048}"
MEMORY="${MEMORY:-4096}"
ASSIGN_PUBLIC_IP="${ASSIGN_PUBLIC_IP:-DISABLED}"
IMAGE_LOCAL="${ECR_REPOSITORY}:${TAG}"
IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${TAG}"
DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-${SCRIPT_DIR:-.}/.deploy-worker.env}"

COLOR_RESET='\033[0m'
COLOR_BLUE='\033[1;34m'
COLOR_GREEN='\033[1;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[1;31m'

log_step() {
  printf '%b[STEP]%b %s\n' "${COLOR_BLUE}" "${COLOR_RESET}" "$1"
}

log_info() {
  printf '%b[INFO]%b %s\n' "${COLOR_YELLOW}" "${COLOR_RESET}" "$1"
}

log_success() {
  printf '%b[OK]%b %s\n' "${COLOR_GREEN}" "${COLOR_RESET}" "$1"
}

log_error() {
  printf '%b[ERROR]%b %s\n' "${COLOR_RED}" "${COLOR_RESET}" "$1" >&2
}

trap 'log_error "Deploy worker failed."' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ -f "${DEPLOY_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${DEPLOY_ENV_FILE}"
  set +a
  AWS_REGION="${AWS_REGION:-ap-southeast-1}"
  AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
  ECR_REPOSITORY="${ECR_REPOSITORY:-nsga2is-sls-worker}"
  STACK_NAME="${STACK_NAME:-nsga2is-sls-worker-fargate}"
  TEMPLATE_FILE="${TEMPLATE_FILE:-deploy/ecs-fargate/worker-fargate-stack.yaml}"
  VPC_ID="${VPC_ID:-}"
  SUBNET_IDS="${SUBNET_IDS:-}"
  QUEUE_ARN="${QUEUE_ARN:-}"
  TABLE_NAME="${TABLE_NAME:-}"
  BUCKET_NAME="${BUCKET_NAME:-}"
  CPU="${CPU:-2048}"
  MEMORY="${MEMORY:-4096}"
  ASSIGN_PUBLIC_IP="${ASSIGN_PUBLIC_IP:-DISABLED}"
  IMAGE_LOCAL="${ECR_REPOSITORY}:${TAG}"
  IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${TAG}"
fi

log_step "Starting worker deploy with tag: ${TAG}"
log_info "Repository root: ${SCRIPT_DIR}"
log_info "AWS Region: ${AWS_REGION}"
log_info "ECR Image URI: ${IMAGE_URI}"

if [[ -z "${AWS_ACCOUNT_ID}" || -z "${VPC_ID}" || -z "${SUBNET_IDS}" || -z "${QUEUE_ARN}" || -z "${TABLE_NAME}" || -z "${BUCKET_NAME}" ]]; then
  log_error "Missing required environment variables: AWS_ACCOUNT_ID, VPC_ID, SUBNET_IDS, QUEUE_ARN, TABLE_NAME, BUCKET_NAME"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  log_error "Docker CLI is not installed or not available in PATH."
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  log_error "AWS CLI is not installed or not available in PATH."
  exit 1
fi

log_step "Step 1/5: Building Docker image"
docker build -t "${IMAGE_LOCAL}" .
log_success "Built image ${IMAGE_LOCAL}"

log_step "Step 2/5: Logging in to AWS ECR"
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
log_success "Logged in to ECR"

log_step "Step 3/5: Tagging Docker image for ECR"
docker tag "${IMAGE_LOCAL}" "${IMAGE_URI}"
log_success "Tagged image as ${IMAGE_URI}"

log_step "Step 4/5: Pushing image to ECR"
docker push "${IMAGE_URI}"
log_success "Pushed image to ECR"

log_step "Step 5/5: Deploying CloudFormation stack"
aws cloudformation deploy \
  --stack-name "${STACK_NAME}" \
  --template-file "${TEMPLATE_FILE}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    VpcId="${VPC_ID}" \
    SubnetIds="${SUBNET_IDS}" \
    QueueArn="${QUEUE_ARN}" \
    ImageUri="${IMAGE_URI}" \
    TableName="${TABLE_NAME}" \
    BucketName="${BUCKET_NAME}" \
    Cpu="${CPU}" \
    Memory="${MEMORY}" \
    AssignPublicIp="${ASSIGN_PUBLIC_IP}"
log_success "CloudFormation stack updated successfully"

log_success "Worker deployment completed for tag ${TAG}"
