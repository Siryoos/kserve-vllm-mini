#!/bin/bash

# Triton TensorRT-LLM backend deployment adapter
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

SERVICE_NAME="$MODEL-triton"

echo "🚀 Deploying Triton TensorRT-LLM backend: $SERVICE_NAME"

# Generate Triton InferenceService YAML
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
        name: triton
      resources:
        limits:
          nvidia.com/gpu: "1"
          memory: "16Gi"
        requests:
          nvidia.com/gpu: "1"
          memory: "8Gi"
      runtime: kserve-tritonserver
      runtimeVersion: 23.10-trtllm-python-py3
      env:
        - name: MODEL_REPOSITORY
          value: "s3://models/triton/$MODEL"
        - name: TENSOR_PARALLEL_SIZE
          value: "1"
        - name: PIPELINE_PARALLEL_SIZE
          value: "1"
        - name: MAX_BATCH_SIZE
          value: "64"
        - name: MAX_INPUT_LEN
          value: "2048"
        - name: MAX_OUTPUT_LEN
          value: "512"
        - name: MAX_BEAM_WIDTH
          value: "1"
        - name: ENGINE_DIR
          value: "/opt/tritonserver/backends/tensorrtllm"
EOF

echo "✅ Triton TensorRT-LLM deployment submitted"
echo "   Service: $SERVICE_NAME"
echo "   Namespace: $NAMESPACE"
echo "   Streaming: $STREAMING"
echo ""
echo "⚠️  Note: Triton requires pre-built TensorRT engines"
echo "   Ensure model repository contains compiled engines for your GPU architecture"
