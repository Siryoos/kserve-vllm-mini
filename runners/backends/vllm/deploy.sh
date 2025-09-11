#!/bin/bash

# vLLM backend deployment adapter
# Usage: ./deploy.sh --model MODEL --namespace NS --streaming BOOL

set -euo pipefail

# Required binaries
command -v kubectl >/dev/null 2>&1 || {
  echo "kubectl not found" >&2
  exit 2
}

MODEL=""
NAMESPACE="ml-prod"
STREAMING="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      MODEL="$2"
      shift 2
      ;;
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --streaming)
      STREAMING="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$MODEL" ]]; then
  echo "ERROR: --model required" >&2
  exit 1
fi

SERVICE_NAME="$MODEL-vllm"

echo "🚀 Deploying vLLM backend: $SERVICE_NAME"

# Generate vLLM InferenceService YAML
cat <<EOF | kubectl apply -f -
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: $SERVICE_NAME
  namespace: $NAMESPACE
  annotations:
    serving.kserve.io/deploymentMode: Serverless
    autoscaling.knative.dev/class: kpa.autoscaling.knative.dev
    autoscaling.knative.dev/metric: concurrency
    autoscaling.knative.dev/target: "10"
    autoscaling.knative.dev/scaleToZeroGracePeriod: "30s"
spec:
  predictor:
    model:
      modelFormat:
        name: vllm
      resources:
        limits:
          nvidia.com/gpu: "1"
          memory: "16Gi"
        requests:
          nvidia.com/gpu: "1"
          memory: "8Gi"
      runtime: kserve-vllmserver
      runtimeVersion: v0.12.1
      env:
        - name: MODEL_NAME
          value: "microsoft/DialoGPT-medium"
        - name: TENSOR_PARALLEL_SIZE
          value: "1"
        - name: GPU_MEMORY_UTILIZATION
          value: "0.9"
        - name: MAX_MODEL_LEN
          value: "2048"
        - name: ENABLE_PREFIX_CACHING
          value: "true"
        - name: DISABLE_LOG_STATS
          value: "false"
        - name: DISABLE_LOG_REQUESTS
          value: "false"
        - name: MAX_LOG_LEN
          value: "2048"
EOF

echo "✅ vLLM deployment submitted"
echo "   Service: $SERVICE_NAME"
echo "   Namespace: $NAMESPACE"
echo "   Streaming: $STREAMING"
