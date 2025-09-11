#!/bin/bash

# kserve-vllm-mini Cost Calculator
# Usage: ./cost-calculator.sh <load-test-results> <gpu-hourly-cost> [requests-per-1k-tokens]

set -e

RESULTS_FILE=${1:-"/tmp/load-test-results.txt"}
GPU_HOURLY_COST=${2:-"1.00"}      # Default $1/hour
REQUESTS_PER_1K_TOKENS=${3:-"10"} # Default 10 requests to produce 1K tokens

if [ ! -f "$RESULTS_FILE" ]; then
  echo "Error: Results file '$RESULTS_FILE' not found!"
  echo "Usage: $0 <load-test-results> <gpu-hourly-cost> [requests-per-1k-tokens]"
  exit 1
fi

echo "=== COST CALCULATION ==="
echo "GPU hourly cost: \$${GPU_HOURLY_COST}"
echo "Requests per 1K tokens: $REQUESTS_PER_1K_TOKENS"
echo "Results file: $RESULTS_FILE"
echo ""

# Calculate GPU cost per second
gpu_price_per_second=$(echo "scale=10; $GPU_HOURLY_COST / 3600" | bc -l)

# Calculate average latency for successful requests
avg_latency_ms=$(awk '$2 == "200" {sum+=$1; count++} END {if(count>0) print sum/count; else print 0}' "$RESULTS_FILE")
avg_latency_seconds=$(echo "scale=10; $avg_latency_ms / 1000" | bc -l)

# Count successful requests
success_count=$(awk '$2 == "200" {count++} END {print count+0}' "$RESULTS_FILE")

echo "=== METRICS ==="
echo "Successful requests: $success_count"
echo "Average latency: $(printf "%.2f" "$avg_latency_ms")ms ($(printf "%.4f" "$avg_latency_seconds")s)"
echo ""

if [ "$success_count" -eq 0 ]; then
  echo "No successful requests found. Cannot calculate cost."
  exit 1
fi

# Calculate cost per 1K tokens
cost_per_1k_tokens=$(echo "scale=6; $gpu_price_per_second * $avg_latency_seconds * $REQUESTS_PER_1K_TOKENS" | bc -l)

echo "=== COST ESTIMATION ==="
echo "GPU price per second: \$$(printf "%.6f" "$gpu_price_per_second")"
echo "Average latency (seconds): $(printf "%.4f" "$avg_latency_seconds")"
echo "Requests per 1K tokens: $REQUESTS_PER_1K_TOKENS"
echo ""
echo "Cost per 1K tokens: \$$(printf "%.6f" "$cost_per_1k_tokens")"

# Additional cost breakdowns
cost_per_1k_requests=$(echo "scale=6; $gpu_price_per_second * $avg_latency_seconds * 1000" | bc -l)
cost_per_hour=$(echo "scale=2; $gpu_price_per_second * 3600" | bc -l)

echo ""
echo "=== ADDITIONAL METRICS ==="
echo "Cost per 1K requests: \$$(printf "%.6f" "$cost_per_1k_requests")"
echo "GPU cost per hour: \$$(printf "%.2f" "$cost_per_hour")"

# Calculate throughput
if [ "$(echo "$avg_latency_seconds > 0" | bc -l)" -eq 1 ]; then
  requests_per_second=$(echo "scale=2; 1 / $avg_latency_seconds" | bc -l)
  requests_per_hour=$(echo "scale=0; $requests_per_second * 3600" | bc -l)
  echo "Theoretical throughput: $(printf "%.2f" "$requests_per_second") req/s ($requests_per_hour req/h)"
fi

echo ""
echo "=== NOTES ==="
echo "- This is a rough estimation based on GPU utilization time"
echo "- Actual costs may vary based on model size, batch processing, and infrastructure overhead"
echo "- Adjust 'requests_per_1k_tokens' based on your actual token generation patterns"
echo "- Consider additional costs: storage, networking, monitoring, etc."
