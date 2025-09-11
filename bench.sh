#!/bin/bash

# Orchestrated benchmark run: deploy (if needed) -> load test -> analyze -> cost
#
# Examples:
#   ./bench.sh --namespace ml-prod --service demo-llm --requests 500 --concurrency 20 \
#     --model my-llm --prom-url http://prometheus.kube-system:9090

set -euo pipefail

command -v kubectl >/dev/null 2>&1 || {
  echo "kubectl not found" >&2
  exit 2
}

NAMESPACE="ml-prod"
SERVICE="demo-llm"
URL=""
PROM_URL=""
REQUESTS=200
CONCURRENCY=10
MODEL="placeholder"
MAX_TOKENS=64
API_KEY=""
INSECURE=""
RUN_DIR=""
COST_FILE="cost.yaml"
PATTERN="steady"
LOADTEST_ARGS=""
BUNDLE_ARTIFACTS=""

usage() {
  echo "Usage: $0 [--namespace NS] [--service NAME] [--url URL] [--requests N] [--concurrency N] [--model NAME] [--max-tokens N] [--pattern {steady,poisson,bursty,heavy}] [--prom-url URL] [--api-key KEY] [--run-dir DIR] [--insecure] [--cost-file PATH] [--bundle] [--loadtest-args '...']" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --service)
      SERVICE="$2"
      shift 2
      ;;
    --url)
      URL="$2"
      shift 2
      ;;
    --requests)
      REQUESTS="$2"
      shift 2
      ;;
    --concurrency)
      CONCURRENCY="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --max-tokens)
      MAX_TOKENS="$2"
      shift 2
      ;;
    --pattern)
      PATTERN="$2"
      shift 2
      ;;
    --prom-url)
      PROM_URL="$2"
      shift 2
      ;;
    --api-key)
      API_KEY="$2"
      shift 2
      ;;
    --run-dir)
      RUN_DIR="$2"
      shift 2
      ;;
    --insecure)
      INSECURE=1
      shift
      ;;
    --cost-file)
      COST_FILE="$2"
      shift 2
      ;;
    --bundle)
      BUNDLE_ARTIFACTS=1
      shift
      ;;
    --loadtest-args)
      LOADTEST_ARGS="$2"
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

if [[ -z "$URL" ]]; then
  echo "Discovering InferenceService URL for $SERVICE in $NAMESPACE ..." >&2
  URL=$(kubectl get inferenceservice "$SERVICE" -n "$NAMESPACE" -o jsonpath='{.status.url}' || true)
  if [[ -z "$URL" ]]; then
    echo "ERROR: Could not determine URL. Provide --url explicitly or ensure the InferenceService is READY." >&2
    exit 1
  fi
fi

TS="$(date +%Y-%m-%d_%H-%M-%S)"
RUN_DIR="${RUN_DIR:-runs/$TS}"
mkdir -p "$RUN_DIR"

echo "=== 1/3 Load test ==="
EXTRA_ARGS=()
if [[ -n "$LOADTEST_ARGS" ]]; then
  # Split string into array on IFS boundaries safely
  # shellcheck disable=SC2206
  EXTRA_ARGS=($LOADTEST_ARGS)
fi
./load-test.sh --url "$URL" --model "$MODEL" --requests "$REQUESTS" --concurrency "$CONCURRENCY" --max-tokens "$MAX_TOKENS" --pattern "$PATTERN" --run-dir "$RUN_DIR" ${API_KEY:+--api-key "$API_KEY"} ${INSECURE:+--insecure} "${EXTRA_ARGS[@]}"

printf "\n=== (optional) Network/Storage Probe ===\n"
if [[ -z "${DISABLE_IO_PROBE:-}" ]]; then
  if [[ -f tools/net_storage_probe.py ]]; then
    python3 tools/net_storage_probe.py --endpoint "$URL" --out "$RUN_DIR/io_probe.json" ${S3_OBJECT_URL:+--s3-object-url "$S3_OBJECT_URL"} || true
  fi
fi

printf "\n=== 2/3 Analyze ===\n"
python3 analyze.py --run-dir "$RUN_DIR" --namespace "$NAMESPACE" --service "$SERVICE" ${PROM_URL:+--prom-url "$PROM_URL"}

printf "\n=== 3/3 Cost ===\n"
python3 cost_estimator.py --run-dir "$RUN_DIR" --namespace "$NAMESPACE" --service "$SERVICE" --cost-file "$COST_FILE"

printf "\n=== DONE ===\n"
echo "Results: $RUN_DIR/results.json"
sed -e 's/^/  /' "$RUN_DIR/results.json"

if [[ -n "$BUNDLE_ARTIFACTS" ]]; then
  echo ""
  echo "=== 4/4 Bundle Artifacts ==="
  if [[ -f "tools/bundle_run.sh" ]]; then
    ./tools/bundle_run.sh --run-dir "$RUN_DIR" --namespace "$NAMESPACE" --service "$SERVICE"
  else
    echo "WARNING: tools/bundle_run.sh not found, skipping bundling" >&2
  fi
fi
