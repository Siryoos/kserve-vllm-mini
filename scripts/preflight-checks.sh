#!/bin/bash

# Preflight checks for kserve-vllm-mini

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_passed() {
  echo -e "${GREEN}✓${NC} $1"
}

check_failed() {
  echo -e "${RED}✗${NC} $1" >&2
  exit 1
}

check_warn() {
  echo -e "${YELLOW}⚠${NC} $1"
}

# 1. Check for kubectl
command -v kubectl >/dev/null 2>&1 || check_failed "kubectl is not installed or not in your PATH."
check_passed "kubectl is installed."

# 2. Check kubectl context
CONTEXT=$(kubectl config current-context)
check_passed "Using kubectl context: $CONTEXT"

# 3. Check for KServe CRDs
if ! kubectl get crd inferenceservices.serving.kserve.io >/dev/null 2>&1; then
  check_failed "KServe CRDs are not installed in the cluster."
fi
check_passed "KServe CRDs are present."

# 4. Check for GPU nodes
if ! kubectl get nodes --selector=nvidia.com/gpu.present=true | grep -q 'Ready'; then
  check_warn "No GPU nodes found in the cluster. This may not be an error if you are deploying to CPU."
else
  check_passed "GPU nodes are available in the cluster."
fi

# 5. Check for S3 credentials
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -z "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    check_warn "AWS S3 credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) are not set. Assuming IAM role."
else
    check_passed "AWS S3 credentials are set."
fi

echo -e "${GREEN}Preflight checks complete.${NC}"
