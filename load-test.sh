#!/bin/bash

# kserve-vllm-mini Load Test Wrapper
# Uses Python asyncio-based OpenAI-compatible load generator.
#
# Examples:
#   ./load-test.sh --url http://<host> --model <name> --requests 500 --concurrency 20

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR" && pwd)"

URL="${URL:-}"
MODEL="${MODEL:-placeholder}"
REQUESTS=200
CONCURRENCY=10
MAX_TOKENS=64
PROMPT=${PROMPT:-"Hello, world!"}
API_KEY=${API_KEY:-}
INSECURE=${INSECURE:-}
RUN_DIR=""
PATTERN="steady"
EXTRA_ARGS=()

usage() {
  echo "Usage: $0 --url <base_url> [options]"
  echo "
Options:"
  echo "  --url <URL>           (Required) The base URL of the OpenAI-compatible endpoint."
  echo "  --model <NAME>        The model name to include in the request payload (default: placeholder)."
  echo "  --requests <N>        Total number of requests to send (default: 200)."
  echo "  --concurrency <N>     Number of concurrent requests (default: 10)."
  echo "  --max-tokens <N>      Maximum number of tokens to generate (default: 64)."
  echo "  --prompt <STR>        The prompt to send in the request (default: 'Hello, world!')."
  echo "  --pattern <TYPE>      Traffic pattern: steady, poisson, bursty, heavy (default: steady)."
  echo "  --api-key <KEY>       API key for authenticated endpoints."
  echo "  --run-dir <DIR>       Directory to save run artifacts (default: runs/YYYY-MM-DD_HH-MM-SS)."
  echo "  --insecure            Allow insecure (non-HTTPS) connections."
  echo "  -h, --help            Show this help message."
  echo "
Examples:"
  echo "  # Basic load test"
  echo "  ./load-test.sh --url http://my-service.my-namespace.example.com --requests 1000 --concurrency 50"
  echo
  echo "  # Test with a different prompt and save to a custom directory"
  echo "  ./load-test.sh --url http://... --prompt \"What is the capital of France?\" --run-dir my-test-run"
  echo
  echo "  # Pass-through vLLM-specific arguments (e.g., for speculative decoding)"
  echo "  ./load-test.sh --url http://... -- --best-of 2 --use-beam-search"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      URL="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
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
    --max-tokens)
      MAX_TOKENS="$2"
      shift 2
      ;;
    --prompt)
      PROMPT="$2"
      shift 2
      ;;
    --pattern)
      PATTERN="$2"
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
    -h | --help)
      usage
      exit 0
      ;;
    *)
      # Collect unknown/extra args and forward to Python load generator
      if [[ "$1" == --* ]]; then
        EXTRA_ARGS+=("$1")
        # If next token exists and isn't another flag, treat as value
        if [[ $# -gt 1 && "$2" != --* ]]; then
          EXTRA_ARGS+=("$2")
          shift 2
          continue
        else
          shift
          continue
        fi
      else
        echo "Unknown arg: $1" >&2
        usage
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$URL" ]]; then
  echo "ERROR: --url is required (OpenAI-compatible endpoint base URL)" >&2
  exit 1
fi

TS="$(date +%Y-%m-%d_%H-%M-%S)"
RUN_DIR="${RUN_DIR:-runs/$TS}"
mkdir -p "$RUN_DIR"

echo "=== Load test ==="
echo "URL: $URL"
echo "Model: $MODEL"
echo "Requests: $REQUESTS"
echo "Concurrency: $CONCURRENCY"
echo "Max tokens: $MAX_TOKENS"
echo "Pattern: $PATTERN"
echo "Run dir: $RUN_DIR"

PY="$ROOT_DIR/scripts/loadtest.py"
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required" >&2
  exit 2
fi

set -x
python3 "$PY" \
  --url "$URL" \
  --model "$MODEL" \
  --prompt "$PROMPT" \
  --max-tokens "$MAX_TOKENS" \
  --requests "$REQUESTS" \
  --concurrency "$CONCURRENCY" \
  --pattern "$PATTERN" \
  --run-dir "$RUN_DIR" \
  ${API_KEY:+--api-key "$API_KEY"} \
  ${INSECURE:+--insecure} \
  "${EXTRA_ARGS[@]}"
set +x

echo ""
echo "Run complete. Data in: $RUN_DIR"
echo "- requests.csv: per-request metrics"
echo "- meta.json: run parameters"
