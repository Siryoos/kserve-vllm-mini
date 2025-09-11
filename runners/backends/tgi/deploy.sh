#!/bin/bash

# Text Generation Inference (TGI) backend deployment adapter
# Usage: ./deploy.sh --model MODEL --namespace NS --streaming BOOL

set -euo pipefail

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

SERVICE_NAME="$MODEL-tgi"

echo "🚀 Deploying TGI backend: $SERVICE_NAME"

# Generate TGI InferenceService YAML
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
    containers:
    - name: kserve-container
      image: ghcr.io/huggingface/text-generation-inference:1.4.0
      resources:
        limits:
          nvidia.com/gpu: "1"
          memory: "16Gi"
        requests:
          nvidia.com/gpu: "1"
          memory: "8Gi"
      env:
        - name: MODEL_ID
          value: "microsoft/DialoGPT-medium"
        - name: NUM_SHARD
          value: "1"
        - name: MAX_CONCURRENT_REQUESTS
          value: "128"
        - name: MAX_BEST_OF
          value: "2"
        - name: MAX_STOP_SEQUENCES
          value: "4"
        - name: MAX_INPUT_LENGTH
          value: "2048"
        - name: MAX_TOTAL_TOKENS
          value: "2560"
        - name: WAITING_SERVED_RATIO
          value: "1.2"
        - name: MAX_BATCH_PREFILL_TOKENS
          value: "4096"
        - name: MAX_BATCH_TOTAL_TOKENS
          value: "131072"
        - name: TRUST_REMOTE_CODE
          value: "true"
        - name: DISABLE_CUSTOM_KERNELS
          value: "false"
      ports:
      - containerPort: 3000
        protocol: TCP
      command:
      - text-generation-launcher
      args:
      - --hostname
      - 0.0.0.0
      - --port
      - "3000"
      - --trust-remote-code
EOF

echo "✅ TGI deployment submitted"
echo "   Service: $SERVICE_NAME"
echo "   Namespace: $NAMESPACE"
echo "   Streaming: $STREAMING"
echo ""
echo "⚠️  Note: TGI may take longer to initialize than vLLM"
echo "   First request will be slower due to model loading"
