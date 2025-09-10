#!/bin/bash

# Grid sweep runner for parameter exploration
# Usage: ./grid-sweep.sh --namespace NS --service NAME [--url URL] [--output sweep.csv] [--prom-url URL]

set -euo pipefail

NAMESPACE="ml-prod"
SERVICE="demo-llm"
URL=""
OUTPUT="sweep_results.csv"
PROM_URL=""
BASE_REQUESTS=200
BASE_PATTERN="steady"
API_KEY=""
INSECURE=""

# Grid parameters (customize these)
CONCURRENCY_VALS=(5 10 20)
MAX_TOKENS_VALS=(32 64 128)
PATTERN_VALS=(steady poisson bursty)

usage() {
  echo "Usage: $0 [--namespace NS] [--service NAME] [--url URL] [--output CSV] [--requests N] [--prom-url URL] [--api-key KEY] [--insecure]" >&2
  echo "  Runs grid sweep over concurrency={5,10,20} × max-tokens={32,64,128} × pattern={steady,poisson,bursty}" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace) NAMESPACE="$2"; shift 2;;
    --service) SERVICE="$2"; shift 2;;
    --url) URL="$2"; shift 2;;
    --output) OUTPUT="$2"; shift 2;;
    --requests) BASE_REQUESTS="$2"; shift 2;;
    --prom-url) PROM_URL="$2"; shift 2;;
    --api-key) API_KEY="$2"; shift 2;;
    --insecure) INSECURE=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
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

echo "=== Grid Sweep Configuration ==="
echo "Service: $SERVICE (namespace: $NAMESPACE)"
echo "URL: $URL"
echo "Base requests per run: $BASE_REQUESTS"
echo "Concurrency values: ${CONCURRENCY_VALS[*]}"
echo "Max tokens values: ${MAX_TOKENS_VALS[*]}"
echo "Pattern values: ${PATTERN_VALS[*]}"
echo "Output: $OUTPUT"
echo ""

# Create CSV header
echo "concurrency,max_tokens,pattern,p50_ms,p95_ms,p99_ms,throughput_rps,tokens_per_sec,error_rate,ttft_p50_ms,ttft_p95_ms,cost_per_request,cost_per_1k_tokens,gpu_util_avg,run_dir" > "$OUTPUT"

TOTAL_RUNS=$((${#CONCURRENCY_VALS[@]} * ${#MAX_TOKENS_VALS[@]} * ${#PATTERN_VALS[@]}))
RUN_COUNT=0

for concurrency in "${CONCURRENCY_VALS[@]}"; do
  for max_tokens in "${MAX_TOKENS_VALS[@]}"; do
    for pattern in "${PATTERN_VALS[@]}"; do
      RUN_COUNT=$((RUN_COUNT + 1))
      echo "=== Run $RUN_COUNT/$TOTAL_RUNS: concurrency=$concurrency, max_tokens=$max_tokens, pattern=$pattern ==="
      
      # Create timestamped run directory
      TS="$(date +%Y-%m-%d_%H-%M-%S)_c${concurrency}_t${max_tokens}_${pattern}"
      RUN_DIR="runs/grid_$TS"
      
      # Run benchmark with these parameters
      ./bench.sh \
        --namespace "$NAMESPACE" \
        --service "$SERVICE" \
        --url "$URL" \
        --requests "$BASE_REQUESTS" \
        --concurrency "$concurrency" \
        --max-tokens "$max_tokens" \
        --pattern "$pattern" \
        --run-dir "$RUN_DIR" \
        --model "grid-sweep" \
        ${PROM_URL:+--prom-url "$PROM_URL"} \
        ${API_KEY:+--api-key "$API_KEY"} \
        ${INSECURE:+--insecure} || {
          echo "WARNING: Run failed for concurrency=$concurrency, max_tokens=$max_tokens, pattern=$pattern" >&2
          echo "$concurrency,$max_tokens,$pattern,ERROR,ERROR,ERROR,ERROR,ERROR,ERROR,ERROR,ERROR,ERROR,ERROR,ERROR,$RUN_DIR" >> "$OUTPUT"
          continue
        }
      
      # Extract key metrics from results.json
      RESULTS_FILE="$RUN_DIR/results.json"
      if [[ -f "$RESULTS_FILE" ]]; then
        # Use jq if available, otherwise python
        if command -v jq >/dev/null 2>&1; then
          P50=$(jq -r '.p50_ms // "N/A"' "$RESULTS_FILE")
          P95=$(jq -r '.p95_ms // "N/A"' "$RESULTS_FILE")
          P99=$(jq -r '.p99_ms // "N/A"' "$RESULTS_FILE")
          THROUGHPUT=$(jq -r '.throughput_rps // "N/A"' "$RESULTS_FILE")
          TOKENS_SEC=$(jq -r '.tokens_per_sec // "N/A"' "$RESULTS_FILE")
          ERROR_RATE=$(jq -r '.error_rate // "N/A"' "$RESULTS_FILE")
          TTFT_P50=$(jq -r '.ttft_p50_ms // "N/A"' "$RESULTS_FILE")
          TTFT_P95=$(jq -r '.ttft_p95_ms // "N/A"' "$RESULTS_FILE")
          COST_REQ=$(jq -r '.cost_per_request // "N/A"' "$RESULTS_FILE")
          COST_1K=$(jq -r '.cost_per_1k_tokens // "N/A"' "$RESULTS_FILE")
          GPU_UTIL=$(jq -r '.gpu_util_avg // "N/A"' "$RESULTS_FILE")
        else
          # Fallback to python
          P50=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('p50_ms', 'N/A'))" 2>/dev/null || echo "N/A")
          P95=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('p95_ms', 'N/A'))" 2>/dev/null || echo "N/A")
          P99=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('p99_ms', 'N/A'))" 2>/dev/null || echo "N/A")
          THROUGHPUT=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('throughput_rps', 'N/A'))" 2>/dev/null || echo "N/A")
          TOKENS_SEC=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('tokens_per_sec', 'N/A'))" 2>/dev/null || echo "N/A")
          ERROR_RATE=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('error_rate', 'N/A'))" 2>/dev/null || echo "N/A")
          TTFT_P50=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('ttft_p50_ms', 'N/A'))" 2>/dev/null || echo "N/A")
          TTFT_P95=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('ttft_p95_ms', 'N/A'))" 2>/dev/null || echo "N/A")
          COST_REQ=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('cost_per_request', 'N/A'))" 2>/dev/null || echo "N/A")
          COST_1K=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('cost_per_1k_tokens', 'N/A'))" 2>/dev/null || echo "N/A")
          GPU_UTIL=$(python3 -c "import json,sys; d=json.load(open('$RESULTS_FILE')); print(d.get('gpu_util_avg', 'N/A'))" 2>/dev/null || echo "N/A")
        fi
        
        # Append to CSV
        echo "$concurrency,$max_tokens,$pattern,$P50,$P95,$P99,$THROUGHPUT,$TOKENS_SEC,$ERROR_RATE,$TTFT_P50,$TTFT_P95,$COST_REQ,$COST_1K,$GPU_UTIL,$RUN_DIR" >> "$OUTPUT"
      else
        echo "WARNING: No results.json found in $RUN_DIR" >&2
        echo "$concurrency,$max_tokens,$pattern,NO_RESULTS,NO_RESULTS,NO_RESULTS,NO_RESULTS,NO_RESULTS,NO_RESULTS,NO_RESULTS,NO_RESULTS,NO_RESULTS,NO_RESULTS,NO_RESULTS,$RUN_DIR" >> "$OUTPUT"
      fi
      
      # Brief pause between runs
      sleep 2
    done
  done
done

echo ""
echo "=== Grid Sweep Complete ==="
echo "Results written to: $OUTPUT"
echo "Total runs: $TOTAL_RUNS"

# Show summary
echo ""
echo "=== Top Performers (by p95 latency) ==="
if command -v sort >/dev/null 2>&1; then
  (head -1 "$OUTPUT"; tail -n +2 "$OUTPUT" | grep -v "ERROR\|NO_RESULTS" | sort -t, -k5 -n | head -5) | column -t -s,
fi

echo ""
echo "=== Top Performers (by throughput) ==="
if command -v sort >/dev/null 2>&1; then
  (head -1 "$OUTPUT"; tail -n +2 "$OUTPUT" | grep -v "ERROR\|NO_RESULTS" | sort -t, -k7 -nr | head -5) | column -t -s,
fi