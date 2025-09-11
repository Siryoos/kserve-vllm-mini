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
PROFILE=""

DRY_RUN=""
LIST_PROFILES=""

usage() {
  echo "Usage: $0 [--namespace NS] [--service NAME] [--url URL] [--requests N] [--concurrency N] [--model NAME] [--max-tokens N] [--pattern {steady,poisson,bursty,heavy}] [--profile PATH] [--prom-url URL] [--api-key KEY] [--run-dir DIR] [--insecure] [--cost-file PATH] [--bundle] [--loadtest-args '...'] [--dry-run] [--list-profiles]" >&2
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
    --profile)
      PROFILE="$2"
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
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --list-profiles)
      LIST_PROFILES=1
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

if [[ -n "$LIST_PROFILES" ]]; then
  echo "Available profiles (runners/profiles):"
  find runners/profiles -type f -name '*.yaml' | sed -e 's/^/  - /'
  echo ""
  echo "Other profiles:"
  echo "  - profiles/mig/*.yaml (MIG scheduling profiles)"
  echo "  - profiles/tensorrt-llm/*.yaml (TensorRT-LLM engine profiles)"
  exit 0
fi

# Load profile settings if provided
if [[ -n "$PROFILE" ]]; then
  if [[ ! -f "$PROFILE" ]]; then
    echo "ERROR: Profile file not found: $PROFILE" >&2
    exit 1
  fi
  echo "Loading profile: $PROFILE" >&2

  # Extract basic settings from YAML profile (simple parsing)
  if command -v python3 >/dev/null 2>&1; then
    eval "$(python3 -c "
import yaml, sys
try:
    with open('$PROFILE') as f:
        p = yaml.safe_load(f) or {}
    if 'requests' in p: print(f'REQUESTS={p[\"requests\"]}')
    if 'concurrency' in p: print(f'CONCURRENCY={p[\"concurrency\"]}')
    if 'max_tokens' in p: print(f'MAX_TOKENS={p[\"max_tokens\"]}')
    if 'pattern' in p: print(f'PATTERN={p[\"pattern\"]}')
    # Build vLLM args from profile
    vllm_args = []
    vf = p.get('vllm_features', {})
    for k, v in vf.items():
        if v is not None and v != '':
            if isinstance(v, bool):
                if v: vllm_args.append(f'--{k.replace(\"_\", \"-\")}')
            else:
                vllm_args.append(f'--{k.replace(\"_\", \"-\")} {v}')
    if vllm_args:
        args_str = ' '.join(vllm_args)
        print(f'PROFILE_VLLM_ARGS=\"{args_str}\"')
except Exception as e:
    print(f'echo \"Warning: Error parsing profile: {e}\"', file=sys.stderr)
" 2>/dev/null)" || echo "Warning: Could not parse profile with Python" >&2
  else
    echo "Warning: python3 not found, profile parsing limited" >&2
  fi

  # Append profile vLLM args to existing loadtest args
  if [[ -n "${PROFILE_VLLM_ARGS:-}" ]]; then
    LOADTEST_ARGS="$LOADTEST_ARGS $PROFILE_VLLM_ARGS"
  fi
fi

if [[ -z "$URL" ]] && [[ -z "$DRY_RUN" ]]; then
  echo "Discovering InferenceService URL for $SERVICE in $NAMESPACE ..." >&2
  URL=$(kubectl get inferenceservice "$SERVICE" -n "$NAMESPACE" -o jsonpath='{.status.url}' || true)
  if [[ -z "$URL" ]]; then
    echo "ERROR: Could not determine URL. Provide --url explicitly or ensure the InferenceService is READY." >&2
    exit 1
  fi
elif [[ -n "$DRY_RUN" ]] && [[ -z "$URL" ]]; then
  URL="http://placeholder-for-dry-run/"
fi

TS="$(date +%Y-%m-%d_%H-%M-%S)"
RUN_DIR="${RUN_DIR:-runs/$TS}"
mkdir -p "$RUN_DIR"

echo "=== 0/4 Configuration validation ==="
if [[ -f scripts/validate_config.py ]]; then
  VALIDATION_ARGS=(--max-tokens "$MAX_TOKENS" --concurrency "$CONCURRENCY" --requests "$REQUESTS")
  if [[ -n "$PROFILE" ]]; then
    VALIDATION_ARGS+=(--profile "$PROFILE")
  fi
  if [[ -n "$LOADTEST_ARGS" ]]; then
    VALIDATION_ARGS+=(--vllm-args "$LOADTEST_ARGS")
  fi
  python3 scripts/validate_config.py "${VALIDATION_ARGS[@]}" || {
    echo "FATAL: Configuration validation failed. Review errors above and fix configuration." >&2
    echo "For multi-step scheduling issues, ensure max_tokens is set when using advanced vLLM features." >&2
    exit 1
  }
else
  echo "Warning: scripts/validate_config.py not found, skipping validation" >&2
fi

echo "=== 1/4 Load test ==="
if [[ -n "$DRY_RUN" ]]; then
  echo "--dry-run enabled: validation only; skipping load test, analyze, and cost."
  exit 0
fi
EXTRA_ARGS=()
if [[ -n "$LOADTEST_ARGS" ]]; then
  # Split string into array on IFS boundaries safely
  # shellcheck disable=SC2206
  EXTRA_ARGS=($LOADTEST_ARGS)
fi
spinner() {
  local pid=$1
  local msg=$2
  local spin="|/-\\"
  local i=0
  echo -n "$msg "
  while kill -0 "$pid" 2>/dev/null; do
    i=$(((i + 1) % 4))
    printf "\r$msg %s" "${spin:$i:1}"
    sleep 0.2
  done
  echo -ne "\r$msg ✓\n"
}

set +x
(
  set -x
  ./load-test.sh --url "$URL" --model "$MODEL" --requests "$REQUESTS" --concurrency "$CONCURRENCY" --max-tokens "$MAX_TOKENS" --pattern "$PATTERN" --run-dir "$RUN_DIR" ${API_KEY:+--api-key "$API_KEY"} ${INSECURE:+--insecure} "${EXTRA_ARGS[@]}"
) &
lt_pid=$!
spinner $lt_pid "Running load test"
wait $lt_pid
set -x

printf "\n=== (optional) Network/Storage Probe ===\n"
if [[ -z "${DISABLE_IO_PROBE:-}" ]]; then
  if [[ -f tools/net_storage_probe.py ]]; then
    python3 tools/net_storage_probe.py --endpoint "$URL" --out "$RUN_DIR/io_probe.json" ${S3_OBJECT_URL:+--s3-object-url "$S3_OBJECT_URL"} || true
  fi
fi

printf "\n=== 2/4 Analyze ===\n"
(
  python3 analyze.py --run-dir "$RUN_DIR" --namespace "$NAMESPACE" --service "$SERVICE" ${PROM_URL:+--prom-url "$PROM_URL"}
) &
an_pid=$!
spinner $an_pid "Analyzing results"
wait $an_pid

printf "\n=== 3/4 Cost ===\n"
(
  python3 cost_estimator.py --run-dir "$RUN_DIR" --namespace "$NAMESPACE" --service "$SERVICE" --cost-file "$COST_FILE"
) &
ce_pid=$!
spinner $ce_pid "Estimating cost"
wait $ce_pid

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
