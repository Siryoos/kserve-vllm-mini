#!/bin/bash

# Backend A/B comparison harness for fair runtime benchmarking
# Usage: ./ab-compare.sh --backends vllm,tgi --model MODEL --profile PROFILE

set -euo pipefail

# Required binaries
command -v kubectl >/dev/null 2>&1 || {
  echo "kubectl not found" >&2
  exit 2
}

BACKENDS="vllm"
MODEL="demo-llm"
PROFILE="standard"
NAMESPACE="ml-prod"
TOGGLE_STREAMING=false
REQUESTS=100
CONCURRENCY=10
RUN_DIR=""
CLEANUP=true
WAIT_BETWEEN=60

usage() {
  echo "Usage: $0 --backends LIST --model NAME [options]" >&2
  echo "" >&2
  echo "Backend A/B testing for fair runtime comparisons:" >&2
  echo "  --backends LIST      Comma-separated backends (vllm,tgi,triton)" >&2
  echo "  --model NAME         Model to deploy across backends" >&2
  echo "  --profile PROFILE    Load profile (standard,burst,sustained)" >&2
  echo "  --namespace NS       Kubernetes namespace (default: ml-prod)" >&2
  echo "  --toggle-streaming   Test both streaming and non-streaming" >&2
  echo "  --requests N         Requests per test (default: 100)" >&2
  echo "  --concurrency N      Concurrent requests (default: 10)" >&2
  echo "  --run-dir DIR        Output directory" >&2
  echo "  --no-cleanup         Keep deployments after testing" >&2
  echo "  --wait-between N     Seconds between tests (default: 60)" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backends)
      BACKENDS="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --toggle-streaming)
      TOGGLE_STREAMING=true
      shift
      ;;
    --requests)
      REQUESTS="$2"
      shift 2
      ;;
    --concurrency)
      CONCURRENCY="$2"
      shift 2
      ;;
    --run-dir)
      RUN_DIR="$2"
      shift 2
      ;;
    --no-cleanup)
      CLEANUP=false
      shift
      ;;
    --wait-between)
      WAIT_BETWEEN="$2"
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

echo "=== Backend A/B Comparison ==="
echo "Backends: $BACKENDS"
echo "Model: $MODEL"
echo "Profile: $PROFILE"
echo "Toggle streaming: $TOGGLE_STREAMING"
echo ""

# Set up run directory
TS="$(date +%Y-%m-%d_%H-%M-%S)"
AB_RUN_DIR="${RUN_DIR:-runs/ab_compare_$TS}"
mkdir -p "$AB_RUN_DIR"

# Parse backends
IFS=',' read -ra BACKEND_LIST <<<"$BACKENDS"

# Load profile configuration
PROFILE_FILE="runners/profiles/${PROFILE}.yaml"
if [[ ! -f "$PROFILE_FILE" ]]; then
  echo "ERROR: Profile file not found: $PROFILE_FILE" >&2
  exit 1
fi

echo "📋 Loading profile: $PROFILE_FILE"
cat "$PROFILE_FILE"
echo ""

# Extract profile parameters
PATTERN=$(yq eval '.pattern' "$PROFILE_FILE")
MAX_TOKENS=$(yq eval '.max_tokens' "$PROFILE_FILE")
PROFILE_REQUESTS=$(yq eval '.requests' "$PROFILE_FILE")
PROFILE_CONCURRENCY=$(yq eval '.concurrency' "$PROFILE_FILE")

# Override with command line if specified
FINAL_REQUESTS=${REQUESTS:-$PROFILE_REQUESTS}
FINAL_CONCURRENCY=${CONCURRENCY:-$PROFILE_CONCURRENCY}

echo "🎯 Test Parameters:"
echo "  Pattern: $PATTERN"
echo "  Requests: $FINAL_REQUESTS"
echo "  Concurrency: $FINAL_CONCURRENCY"
echo "  Max tokens: $MAX_TOKENS"
echo ""

# Initialize results tracking
RESULTS_CSV="$AB_RUN_DIR/ab_comparison.csv"
echo "backend,streaming,requests,concurrency,mean_ttft_ms,p95_ttft_ms,mean_tpot_ms,p95_tpot_ms,throughput_req_s,gpu_util_avg,cost_per_1k_tokens" >"$RESULTS_CSV"

# Function to run single backend test
run_backend_test() {
  local backend="$1"
  local streaming="$2"
  local test_dir="$3"

  echo "🚀 Testing $backend (streaming: $streaming)"

  # Deploy backend
  if [[ -f "runners/backends/$backend/deploy.sh" ]]; then
    echo "  Deploying $backend..."
    bash "runners/backends/$backend/deploy.sh" \
      --model "$MODEL" \
      --namespace "$NAMESPACE" \
      --streaming "$streaming"
  else
    echo "ERROR: Deploy script not found: runners/backends/$backend/deploy.sh" >&2
    return 1
  fi

  # Wait for deployment to be ready
  echo "  Waiting for deployment..."
  kubectl wait --for=condition=Ready inferenceservice "$MODEL-$backend" -n "$NAMESPACE" --timeout=300s

  # Get service URL
  URL=$(kubectl get inferenceservice "$MODEL-$backend" -n "$NAMESPACE" -o jsonpath='{.status.url}')
  if [[ -z "$URL" ]]; then
    echo "ERROR: Could not get URL for $MODEL-$backend" >&2
    return 1
  fi

  echo "  Service URL: $URL"

  # Run load test using backend-specific invoke script
  if [[ -f "runners/backends/$backend/invoke.sh" ]]; then
    echo "  Running load test..."
    bash "runners/backends/$backend/invoke.sh" \
      --url "$URL" \
      --requests "$FINAL_REQUESTS" \
      --concurrency "$FINAL_CONCURRENCY" \
      --pattern "$PATTERN" \
      --max-tokens "$MAX_TOKENS" \
      --streaming "$streaming" \
      --run-dir "$test_dir"
  else
    echo "ERROR: Invoke script not found: runners/backends/$backend/invoke.sh" >&2
    return 1
  fi

  # Extract metrics from results
  if [[ -f "$test_dir/requests.csv" ]]; then
    echo "  Analyzing results..."
    python3 <<EOF
import csv
import statistics
import subprocess
import json

# Load test results
ttft_times = []
tpot_times = []
with open("$test_dir/requests.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['status'] == '200':
            if row.get('ttfb_ms'):
                ttft_times.append(float(row['ttfb_ms']))
            if row.get('tpot_ms'):
                tpot_times.append(float(row['tpot_ms']))

# Calculate metrics
mean_ttft = statistics.mean(ttft_times) if ttft_times else 0
p95_ttft = sorted(ttft_times)[int(0.95 * len(ttft_times))] if ttft_times else 0
mean_tpot = statistics.mean(tpot_times) if tpot_times else 0
p95_tpot = sorted(tpot_times)[int(0.95 * len(tpot_times))] if tpot_times else 0

# Load summary for throughput
with open("$test_dir/results.json") as f:
    summary = json.load(f)

throughput = summary.get('throughput_req_per_sec', 0)
gpu_util = summary.get('gpu_utilization_avg', 0)
cost_per_1k = summary.get('cost_per_1k_tokens', 0)

# Write to comparison CSV
with open("$RESULTS_CSV", "a") as f:
    f.write(f"$backend,$streaming,$FINAL_REQUESTS,$FINAL_CONCURRENCY,{mean_ttft:.1f},{p95_ttft:.1f},{mean_tpot:.1f},{p95_tpot:.1f},{throughput:.2f},{gpu_util:.1f},{cost_per_1k:.4f}\n")
EOF
  else
    echo "WARNING: No results CSV found for $backend test" >&2
  fi

  echo "  ✅ $backend test complete"
}

# Function to cleanup deployment
cleanup_backend() {
  local backend="$1"

  if [[ "$CLEANUP" == "true" ]]; then
    echo "🧹 Cleaning up $backend deployment..."
    kubectl delete inferenceservice "$MODEL-$backend" -n "$NAMESPACE" --ignore-not-found=true

    # Wait for cleanup
    sleep 10
  fi
}

# Run tests for each backend
for backend in "${BACKEND_LIST[@]}"; do
  echo ""
  echo "=== Testing Backend: $backend ==="

  if [[ "$TOGGLE_STREAMING" == "true" ]]; then
    # Test both streaming and non-streaming
    for streaming in "true" "false"; do
      test_dir="$AB_RUN_DIR/${backend}_streaming_${streaming}"
      mkdir -p "$test_dir"

      run_backend_test "$backend" "$streaming" "$test_dir"

      # Wait between streaming modes
      if [[ "$streaming" == "true" ]]; then
        echo "  Waiting ${WAIT_BETWEEN}s before non-streaming test..."
        sleep "$WAIT_BETWEEN"
      fi
    done
  else
    # Test only non-streaming
    test_dir="$AB_RUN_DIR/${backend}_streaming_false"
    mkdir -p "$test_dir"

    run_backend_test "$backend" "false" "$test_dir"
  fi

  cleanup_backend "$backend"

  # Wait between backends
  if [[ "$backend" != "${BACKEND_LIST[-1]}" ]]; then
    echo "  Waiting ${WAIT_BETWEEN}s before next backend..."
    sleep "$WAIT_BETWEEN"
  fi
done

echo ""
echo "📊 Generating comparison report..."

# Generate comparison analysis
python3 <<EOF
import csv
import json
from datetime import datetime

# Load comparison results
results = []
with open("$RESULTS_CSV") as f:
    reader = csv.DictReader(f)
    for row in reader:
        results.append(row)

if not results:
    print("No results to analyze")
    exit(1)

# Find best performing backend for each metric
best_ttft = min(results, key=lambda x: float(x['mean_ttft_ms']))
best_throughput = max(results, key=lambda x: float(x['throughput_req_s']))
best_cost = min(results, key=lambda x: float(x['cost_per_1k_tokens']))

# Generate comparison report
report = {
    "comparison_metadata": {
        "timestamp": datetime.utcnow().isoformat(),
        "profile": "$PROFILE",
        "model": "$MODEL",
        "requests": $FINAL_REQUESTS,
        "concurrency": $FINAL_CONCURRENCY,
        "streaming_tested": $TOGGLE_STREAMING
    },
    "results": results,
    "winners": {
        "fastest_ttft": {
            "backend": best_ttft['backend'],
            "streaming": best_ttft['streaming'],
            "value_ms": float(best_ttft['mean_ttft_ms'])
        },
        "highest_throughput": {
            "backend": best_throughput['backend'],
            "streaming": best_throughput['streaming'],
            "value_req_s": float(best_throughput['throughput_req_s'])
        },
        "lowest_cost": {
            "backend": best_cost['backend'],
            "streaming": best_cost['streaming'],
            "value_per_1k": float(best_cost['cost_per_1k_tokens'])
        }
    }
}

# Save detailed report
with open("$AB_RUN_DIR/comparison_report.json", "w") as f:
    json.dump(report, f, indent=2)

# Print summary
print("\n=== A/B Comparison Results ===")
print(f"Profile: $PROFILE")
print(f"Model: $MODEL")
print("")

print("🏆 Performance Winners:")
print(f"  Fastest TTFT: {best_ttft['backend']} (streaming: {best_ttft['streaming']}) - {best_ttft['mean_ttft_ms']}ms")
print(f"  Highest Throughput: {best_throughput['backend']} (streaming: {best_throughput['streaming']}) - {best_throughput['throughput_req_s']} req/s")
print(f"  Lowest Cost: {best_cost['backend']} (streaming: {best_cost['streaming']}) - \${best_cost['cost_per_1k_tokens']} per 1K tokens")
print("")

print("📋 All Results:")
for result in results:
    streaming_label = "streaming" if result['streaming'] == 'true' else "non-streaming"
    print(f"  {result['backend']} ({streaming_label}):")
    print(f"    TTFT: {result['mean_ttft_ms']}ms (p95: {result['p95_ttft_ms']}ms)")
    print(f"    Throughput: {result['throughput_req_s']} req/s")
    print(f"    Cost: \${result['cost_per_1k_tokens']} per 1K tokens")
    print("")

if $TOGGLE_STREAMING:
    print("💡 Streaming vs Non-streaming Analysis:")

    # Group by backend
    backends = {}
    for result in results:
        backend = result['backend']
        if backend not in backends:
            backends[backend] = {}
        backends[backend][result['streaming']] = result

    for backend, modes in backends.items():
        if 'true' in modes and 'false' in modes:
            streaming = modes['true']
            non_streaming = modes['false']

            ttft_diff = float(non_streaming['mean_ttft_ms']) - float(streaming['mean_ttft_ms'])
            throughput_diff = float(streaming['throughput_req_s']) - float(non_streaming['throughput_req_s'])

            print(f"  {backend}:")
            print(f"    TTFT impact: {ttft_diff:+.1f}ms (streaming advantage)")
            print(f"    Throughput impact: {throughput_diff:+.2f} req/s (streaming advantage)")
            print("")

print("📄 Detailed results:")
print(f"  Comparison CSV: $RESULTS_CSV")
print(f"  Full report: $AB_RUN_DIR/comparison_report.json")
print(f"  Individual test results: $AB_RUN_DIR/*/")
EOF

echo ""
echo "=== A/B Comparison Complete ==="
echo "Results directory: $AB_RUN_DIR"
