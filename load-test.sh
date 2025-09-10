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

usage() {
  echo "Usage: $0 --url <base_url> [--model <name>] [--requests N] [--concurrency N] [--max-tokens N] [--prompt STR] [--api-key KEY] [--run-dir DIR] [--insecure]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) URL="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    --requests) REQUESTS="$2"; shift 2;;
    --concurrency) CONCURRENCY="$2"; shift 2;;
    --max-tokens) MAX_TOKENS="$2"; shift 2;;
    --prompt) PROMPT="$2"; shift 2;;
    --api-key) API_KEY="$2"; shift 2;;
    --run-dir) RUN_DIR="$2"; shift 2;;
    --insecure) INSECURE=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
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
  --run-dir "$RUN_DIR" \
  ${API_KEY:+--api-key "$API_KEY"} \
  ${INSECURE:+--insecure}
set +x

echo ""
echo "Run complete. Data in: $RUN_DIR"
echo "- requests.csv: per-request metrics"
echo "- meta.json: run parameters"
