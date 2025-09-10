#!/bin/bash

# kserve-vllm-mini Load Test Script
# Usage: ./load-test.sh <model-endpoint> [num-requests]

set -e

MODEL_ENDPOINT=${1:-"http://demo-llm.ml-prod.svc.cluster.local"}
NUM_REQUESTS=${2:-200}
OUTPUT_FILE="/tmp/load-test-results.txt"

echo "Starting load test..."
echo "Model endpoint: $MODEL_ENDPOINT"
echo "Number of requests: $NUM_REQUESTS"
echo "Results will be saved to: $OUTPUT_FILE"
echo ""

# Clear previous results
> "$OUTPUT_FILE"

# Run load test
for i in $(seq 1 $NUM_REQUESTS); do
  echo -n "Request $i/$NUM_REQUESTS... "
  
  # Measure request time in milliseconds
  start_time=$(date +%s%3N)
  
  # Make the request
  response=$(curl -s -w "%{http_code}" -X POST \
    -H 'Content-Type: application/json' \
    -d '{"text":"hello"}' \
    "$MODEL_ENDPOINT" 2>/dev/null)
  
  end_time=$(date +%s%3N)
  duration=$((end_time - start_time))
  
  # Extract HTTP status code (last 3 characters)
  http_code="${response: -3}"
  
  # Record result
  echo "$duration $http_code" >> "$OUTPUT_FILE"
  
  if [ "$http_code" = "200" ]; then
    echo "OK (${duration}ms)"
  else
    echo "ERROR (${duration}ms, HTTP $http_code)"
  fi
done

echo ""
echo "Load test completed!"
echo ""

# Calculate statistics
echo "=== RESULTS ==="
echo "Total requests: $NUM_REQUESTS"

# Count successful requests
success_count=$(awk '$2 == "200" {count++} END {print count+0}' "$OUTPUT_FILE")
error_count=$((NUM_REQUESTS - success_count))
error_rate=$(echo "scale=2; $error_count * 100 / $NUM_REQUESTS" | bc -l)

echo "Successful requests: $success_count"
echo "Failed requests: $error_count"
echo "Error rate: ${error_rate}%"

# Calculate latency statistics (only for successful requests)
if [ $success_count -gt 0 ]; then
  echo ""
  echo "=== LATENCY STATISTICS (ms) ==="
  
  # Extract latencies for successful requests
  awk '$2 == "200" {print $1}' "$OUTPUT_FILE" | sort -n > /tmp/successful_latencies.txt
  
  # Calculate percentiles
  p50=$(awk 'BEGIN{n=0}{a[n++]=$1}END{print a[int(n*0.50)]}' /tmp/successful_latencies.txt)
  p95=$(awk 'BEGIN{n=0}{a[n++]=$1}END{print a[int(n*0.95)]}' /tmp/successful_latencies.txt)
  p99=$(awk 'BEGIN{n=0}{a[n++]=$1}END{print a[int(n*0.99)]}' /tmp/successful_latencies.txt)
  
  # Calculate average
  avg=$(awk '{sum+=$1; count++} END {print sum/count}' /tmp/successful_latencies.txt)
  
  echo "Average: $(printf "%.2f" $avg)ms"
  echo "P50: ${p50}ms"
  echo "P95: ${p95}ms"
  echo "P99: ${p99}ms"
  
  # Calculate min/max
  min=$(head -1 /tmp/successful_latencies.txt)
  max=$(tail -1 /tmp/successful_latencies.txt)
  echo "Min: ${min}ms"
  echo "Max: ${max}ms"
  
  # Clean up temp file
  rm -f /tmp/successful_latencies.txt
fi

echo ""
echo "Raw results saved to: $OUTPUT_FILE"
echo "Format: <latency_ms> <http_status_code>"
