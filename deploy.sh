#!/bin/bash

# kserve-vllm-mini Deployment Script
# Usage: ./deploy.sh [--namespace NS] [--service NAME] [--model-uri s3://...] [--runtime vllm]

set -euo pipefail

# Run preflight checks
if [ -f scripts/preflight-checks.sh ]; then
    ./scripts/preflight-checks.sh
fi

NAMESPACE="ml-prod"
SERVICE_NAME="demo-llm"
MODEL_URI=""
RUNTIME_NAME="vllm"
DRY_RUN=""

# Required binaries
command -v kubectl >/dev/null 2>&1 || {
  echo "kubectl not found" >&2
  exit 2
}

usage() {
  echo "Usage: $0 [options]"
  echo "
Options:"
  echo "  --namespace <NS>      Kubernetes namespace (default: ml-prod)"
  echo "  --service <NAME>      InferenceService name (default: demo-llm)"
  echo "  --model-uri <URI>     S3 URI for the model weights"
  echo "  --runtime <NAME>      KServe runtime name (default: vllm)"
  echo "  --dry-run             Print the generated Kubernetes manifest without applying it"
  echo "  -h, --help            Show this help message"
  echo "
Examples:"
  echo "  ./deploy.sh --service my-llama --model-uri s3://my-bucket/llama-7b/"
  echo "  ./deploy.sh --dry-run --service my-llama | kubectl apply -f -"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --service)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --model-uri)
      MODEL_URI="$2"
      shift 2
      ;;
    --runtime)
      RUNTIME_NAME="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 1
      ;;
  esac
done

echo "=== KServe vLLM Mini Deployment ==="
if [[ -n "$DRY_RUN" ]]; then
  echo "Mode: Dry Run"
fi
echo "Namespace: $NAMESPACE"
echo "Service name: $SERVICE_NAME"
echo "Runtime: $RUNTIME_NAME"
[[ -n "$MODEL_URI" ]] && echo "Model URI: $MODEL_URI"
echo ""

# Create namespace if it doesn't exist
if [[ -z "$DRY_RUN" ]]; then
  echo "Creating namespace '$NAMESPACE' בו..."
  kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
fi

TMP_YAML=$(mktemp)
cp isvc.yaml "$TMP_YAML"
# Patch namespace/service/runtime/model-uri if provided
sed -i -E "s/^(\s*)name:\s*.*/\1name: $SERVICE_NAME/" "$TMP_YAML"
sed -i -E "s/^(\s*)namespace:\s*.*/\1namespace: $NAMESPACE/" "$TMP_YAML"
sed -i -E "s/^(\s*)runtime:\s*.*/\1runtime: $RUNTIME_NAME/" "$TMP_YAML"
if [[ -n "$MODEL_URI" ]]; then
  sed -i -E "s#^(\s*)storageUri:\s*.*#\1storageUri: $MODEL_URI#" "$TMP_YAML"
fi

if [[ -n "$DRY_RUN" ]]; then
  echo "--- Generated InferenceService manifest ---"
  cat "$TMP_YAML"
  rm -f "$TMP_YAML"
  exit 0
fi

echo "Deploying InferenceService..."
kubectl -n "$NAMESPACE" apply -f "$TMP_YAML"
rm -f "$TMP_YAML"

echo ""
echo "Waiting for InferenceService to be READY..."
kubectl wait --for=condition=Ready --timeout=600s inferenceservice/"$SERVICE_NAME" -n "$NAMESPACE"

echo ""
echo "=== DEPLOYMENT STATUS ==="
kubectl get inferenceservice "$SERVICE_NAME" -n "$NAMESPACE" -o wide

echo ""
echo "=== SERVICE URL ==="
SERVICE_URL=$(kubectl get inferenceservice "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.status.url}')
if [ -n "$SERVICE_URL" ]; then
  echo "Model endpoint: $SERVICE_URL"
  echo ""
  echo "=== TESTING CONNECTION (OpenAI /v1/chat/completions) ==="
  kubectl run test-client --rm -i --restart=Never --image=curlimages/curl -- \
    curl -s -X POST -H 'Content-Type: application/json' \
    -d '{"model":"placeholder","messages":[{"role":"user","content":"ping"}],"max_tokens":4}' \
    "$SERVICE_URL/v1/chat/completions" || echo "Note: test may fail if model is still warming."
else
  echo "Service URL not available yet. Check the status above."
fi

echo ""
echo "=== NEXT STEPS ==="
echo "Run benchmark: ./bench.sh --namespace $NAMESPACE --service $SERVICE_NAME --requests 500 --concurrency 20 --model placeholder"
