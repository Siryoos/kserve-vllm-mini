#!/bin/bash

# vLLM backend load test adapter
# Usage: ./invoke.sh --url URL --requests N --concurrency N --pattern PATTERN --max-tokens N --streaming BOOL --run-dir DIR

set -euo pipefail

URL=""
REQUESTS=100
CONCURRENCY=10
PATTERN="steady"
MAX_TOKENS=64
STREAMING="false"
RUN_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
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
    --pattern)
      PATTERN="$2"
      shift 2
      ;;
    --max-tokens)
      MAX_TOKENS="$2"
      shift 2
      ;;
    --streaming)
      STREAMING="$2"
      shift 2
      ;;
    --run-dir)
      RUN_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$URL" || -z "$RUN_DIR" ]]; then
  echo "ERROR: --url and --run-dir required" >&2
  exit 1
fi

echo "🔄 Running vLLM load test"
echo "  URL: $URL"
echo "  Requests: $REQUESTS"
echo "  Concurrency: $CONCURRENCY"
echo "  Pattern: $PATTERN"
echo "  Max tokens: $MAX_TOKENS"
echo "  Streaming: $STREAMING"
echo "  Output: $RUN_DIR"

# Determine streaming flag for loadtest.py
STREAM_FLAG=""
if [[ "$STREAMING" == "true" ]]; then
  STREAM_FLAG="--stream"
fi

# Run the standard load test
python3 scripts/loadtest.py \
  --url "$URL" \
  --model "vllm-backend" \
  --requests "$REQUESTS" \
  --concurrency "$CONCURRENCY" \
  --max-tokens "$MAX_TOKENS" \
  --pattern "$PATTERN" \
  --run-dir "$RUN_DIR" \
  $STREAM_FLAG

echo "✅ vLLM load test complete"
