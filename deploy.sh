#!/bin/bash

# kserve-vllm-mini Deployment Script
# Usage: ./deploy.sh [--namespace NS] [--service NAME] [--model-uri s3://...] [--runtime vllm]

set -euo pipefail

NAMESPACE="ml-prod"
SERVICE_NAME="demo-llm"
MODEL_URI=""
RUNTIME_NAME="vllm"

# Required binaries
command -v kubectl >/dev/null 2>&1 || {
  echo "kubectl not found" >&2
  exit 2
}

usage() {
  echo "Usage: $0 [--namespace NS] [--service NAME] [--model-uri s3://...] [--runtime NAME]" >&2
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
echo "Namespace: $NAMESPACE"
echo "Service name: $SERVICE_NAME"
echo "Runtime: $RUNTIME_NAME"
[[ -n "$MODEL_URI" ]] && echo "Model URI: $MODEL_URI"
echo ""

# Create namespace if it doesn't exist
echo "Creating namespace '$NAMESPACE'..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

TMP_YAML=$(mktemp)
cp isvc.yaml "$TMP_YAML"
# Patch namespace/service/runtime/model-uri if provided
sed -i -E "s/^(\s*)name:\s*.*/\1name: $SERVICE_NAME/" "$TMP_YAML"
sed -i -E "s/^(\s*)namespace:\s*.*/\1namespace: $NAMESPACE/" "$TMP_YAML"
sed -i -E "s/^(\s*)runtime:\s*.*/\1runtime: $RUNTIME_NAME/" "$TMP_YAML"
if [[ -n "$MODEL_URI" ]]; then
  sed -i -E "s#^(\s*)storageUri:\s*.*#\1storageUri: $MODEL_URI#" "$TMP_YAML"
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
