#!/bin/bash

# Systematic autoscaling parameter sweep for KServe InferenceServices
# Usage: ./autoscale-sweep.sh --namespace NS --service NAME --model-uri URI --base-requests N

set -euo pipefail

# Required binaries
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found" >&2; exit 2; }

NAMESPACE="ml-prod"
SERVICE="autoscale-sweep"
MODEL_URI=""
BASE_REQUESTS=200
PROM_URL=""
API_KEY=""
RUNTIME="vllm"
OUTPUT="autoscale_sweep_results.csv"
CLEANUP_BETWEEN_RUNS=true

# Autoscaling parameter space to explore
CONTAINER_CONCURRENCY_VALS=(1 4 8 16)
INITIAL_SCALE_VALS=(0 1 2)
SCALE_TO_ZERO_GRACE_PERIOD_VALS=(30s 60s 300s)
STABLE_WINDOW_VALS=(60s 120s)
PANIC_WINDOW_VALS=(6s 10s)

usage() {
  echo "Usage: $0 --namespace NS --model-uri URI [--service NAME] [--base-requests N] [--prom-url URL] [--runtime NAME] [--output CSV] [--no-cleanup]" >&2
  echo "" >&2
  echo "Systematically sweeps autoscaling parameters for KServe InferenceServices:" >&2
  echo "  - containerConcurrency: ${CONTAINER_CONCURRENCY_VALS[*]}" >&2
  echo "  - initialScale: ${INITIAL_SCALE_VALS[*]}" >&2
  echo "  - scaleToZeroGracePeriod: ${SCALE_TO_ZERO_GRACE_PERIOD_VALS[*]}" >&2
  echo "  - stableWindow: ${STABLE_WINDOW_VALS[*]}" >&2
  echo "  - panicWindow: ${PANIC_WINDOW_VALS[*]}" >&2
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
    --model-uri)
      MODEL_URI="$2"
      shift 2
      ;;
    --base-requests)
      BASE_REQUESTS="$2"
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
    --runtime)
      RUNTIME="$2"
      shift 2
      ;;
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    --no-cleanup)
      CLEANUP_BETWEEN_RUNS=false
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

if [[ -z "$MODEL_URI" ]]; then
  echo "ERROR: --model-uri is required" >&2
  usage
  exit 1
fi

echo "=== KServe Autoscaling Parameter Sweep ==="
echo "Namespace: $NAMESPACE"
echo "Service: $SERVICE"
echo "Model URI: $MODEL_URI"
echo "Runtime: $RUNTIME"
echo "Base requests per run: $BASE_REQUESTS"
echo "Output: $OUTPUT"
echo ""

# Calculate total combinations
TOTAL_COMBINATIONS=$((${#CONTAINER_CONCURRENCY_VALS[@]} * ${#INITIAL_SCALE_VALS[@]} * ${#SCALE_TO_ZERO_GRACE_PERIOD_VALS[@]} * ${#STABLE_WINDOW_VALS[@]} * ${#PANIC_WINDOW_VALS[@]}))
echo "Total parameter combinations: $TOTAL_COMBINATIONS"
echo ""

# Create CSV header
cat >"$OUTPUT" <<'EOF'
container_concurrency,initial_scale,scale_to_zero_grace_period,stable_window,panic_window,p50_ms,p95_ms,p99_ms,p50_warm_ms,p95_warm_ms,p50_cold_ms,p95_cold_ms,cold_start_count,cold_multiplier,throughput_rps,tokens_per_sec,error_rate,cost_per_request,cost_per_1k_tokens,cold_cost_per_request,warm_cost_per_request,cold_cost_per_1k_tokens,warm_cost_per_1k_tokens,energy_wh_per_1k_tokens,gpu_util_avg,run_dir,deploy_time_sec,notes
EOF

RUN_COUNT=0

# Helper function to deploy InferenceService with specific autoscaling config
deploy_with_config() {
  local container_concurrency="$1"
  local initial_scale="$2"
  local scale_grace="$3"
  local stable_window="$4"
  local panic_window="$5"
  local service_name="$6"

  local deploy_start
  deploy_start=$(date +%s)

  cat >/tmp/autoscale_isvc.yaml <<EOF
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: $service_name
  namespace: $NAMESPACE
  annotations:
    # Knative autoscaling annotations
    autoscaling.knative.dev/target: "$container_concurrency"
    autoscaling.knative.dev/initialScale: "$initial_scale"
    autoscaling.knative.dev/scaleToZeroGracePeriod: "$scale_grace"
    autoscaling.knative.dev/stableWindow: "$stable_window"
    autoscaling.knative.dev/panicWindow: "$panic_window"
    autoscaling.knative.dev/metric: "concurrency"
    autoscaling.knative.dev/minScale: "0"
    autoscaling.knative.dev/maxScale: "5"
    serving.kserve.io/enable-metrics: "true"
spec:
  predictor:
    model:
      runtime: $RUNTIME
      storageUri: $MODEL_URI
      env:
        - name: VLLM_ARGS
          value: "--max-model-len 4096 --gpu-memory-utilization 0.90 --disable-log-requests"
      resources:
        limits:
          nvidia.com/gpu: "1"
          memory: "12Gi"
        requests:
          cpu: "2"
          memory: "12Gi"
EOF

  echo "  Deploying with config: concurrency=$container_concurrency, initialScale=$initial_scale, gracePeriod=$scale_grace..."
  kubectl apply -f /tmp/autoscale_isvc.yaml

  # Wait for readiness with timeout
  if kubectl wait --for=condition=Ready --timeout=300s inferenceservice/"$service_name" -n "$NAMESPACE"; then
    local deploy_end
    deploy_end=$(date +%s)
    local deploy_time=$((deploy_end - deploy_start))
    echo "  ✅ Deployed in ${deploy_time}s"
    echo $deploy_time
  else
    echo "  ❌ Deploy timeout"
    echo "TIMEOUT"
  fi
}

# Helper function to cleanup InferenceService
cleanup_service() {
  local service_name="$1"

  echo "  🧹 Cleaning up $service_name..."
  kubectl delete inferenceservice "$service_name" -n "$NAMESPACE" --ignore-not-found=true

  # Wait for pods to terminate
  sleep 30

  # Force cleanup any stuck pods
  kubectl delete pods -n "$NAMESPACE" -l serving.kserve.io/inferenceservice="${service_name}" --ignore-not-found=true
}

# Main sweep loop
for container_concurrency in "${CONTAINER_CONCURRENCY_VALS[@]}"; do
  for initial_scale in "${INITIAL_SCALE_VALS[@]}"; do
    for scale_grace in "${SCALE_TO_ZERO_GRACE_PERIOD_VALS[@]}"; do
      for stable_window in "${STABLE_WINDOW_VALS[@]}"; do
        for panic_window in "${PANIC_WINDOW_VALS[@]}"; do
          RUN_COUNT=$((RUN_COUNT + 1))

          echo ""
          echo "=== Run $RUN_COUNT/$TOTAL_COMBINATIONS ==="
          echo "Config: concurrency=$container_concurrency, initialScale=$initial_scale, gracePeriod=$scale_grace, stableWindow=$stable_window, panicWindow=$panic_window"

          # Generate unique service name for this run
          TS="$(date +%Y%m%d_%H%M%S)"
          RUN_SERVICE="${SERVICE}-${RUN_COUNT}-${TS}"
          RUN_DIR="runs/autoscale_${RUN_COUNT}_${TS}"

          # Deploy with specific configuration
          DEPLOY_TIME=$(deploy_with_config "$container_concurrency" "$initial_scale" "$scale_grace" "$stable_window" "$panic_window" "$RUN_SERVICE")

          if [[ "$DEPLOY_TIME" == "TIMEOUT" ]]; then
            echo "  ❌ Deployment failed, recording failure..."
            echo "$container_concurrency,$initial_scale,$scale_grace,$stable_window,$panic_window,DEPLOY_TIMEOUT,DEPLOY_TIMEOUT,DEPLOY_TIMEOUT,,,,,,,,,,,,,,,,$RUN_DIR,$DEPLOY_TIME,deployment_timeout" >>"$OUTPUT"

            # Cleanup and continue
            if [[ "$CLEANUP_BETWEEN_RUNS" == "true" ]]; then
              cleanup_service "$RUN_SERVICE"
            fi
            continue
          fi

          # Wait for cold start to complete and service to be fully ready
          sleep 45

          # Run benchmark
          echo "  📊 Running benchmark..."
          if ./bench.sh \
            --namespace "$NAMESPACE" \
            --service "$RUN_SERVICE" \
            --requests "$BASE_REQUESTS" \
            --concurrency 10 \
            --max-tokens 64 \
            --pattern poisson \
            --run-dir "$RUN_DIR" \
            --model "autoscale-test" \
            ${PROM_URL:+--prom-url "$PROM_URL"} \
            ${API_KEY:+--api-key "$API_KEY"} 2>&1; then

            echo "  ✅ Benchmark completed"

            # Extract metrics from results
            if [[ -f "$RUN_DIR/results.json" ]]; then
              # Parse results using jq/python
              python3 <<EOF
import json
import csv
import sys

try:
    with open("$RUN_DIR/results.json") as f:
        results = json.load(f)

    # Extract key metrics
    p50 = results.get("p50_ms", "")
    p95 = results.get("p95_ms", "")
    p99 = results.get("p99_ms", "")
    p50_warm = results.get("warm_p50_ms", "")
    p95_warm = results.get("warm_p95_ms", "")
    p50_cold = results.get("cold_p50_ms", "")
    p95_cold = results.get("cold_p95_ms", "")
    cold_starts = results.get("cold_start_count", "")
    throughput = results.get("throughput_rps", "")
    tokens_sec = results.get("tokens_per_sec", "")
    error_rate = results.get("error_rate", "")
    cost_req = results.get("cost_per_request", "")
    cost_1k = results.get("cost_per_1k_tokens", "")
    cold_cost_req = results.get("cold_cost_per_request", "")
    warm_cost_req = results.get("warm_cost_per_request", "")
    cold_cost_1k = results.get("cold_cost_per_1k_tokens", "")
    warm_cost_1k = results.get("warm_cost_per_1k_tokens", "")
    energy_1k = results.get("energy_wh_per_1k_tokens", "")
    gpu_util = results.get("gpu_util_avg", "")

    # Calculate cold start multiplier
    cold_multiplier = ""
    if p95_cold and p95_warm and p95_warm > 0:
        cold_multiplier = p95_cold / p95_warm

    # Write CSV row
    with open("$OUTPUT", "a") as f:
        writer = csv.writer(f)
        writer.writerow([
            "$container_concurrency", "$initial_scale", "$scale_grace",
            "$stable_window", "$panic_window",
            p50, p95, p99, p50_warm, p95_warm, p50_cold, p95_cold,
            cold_starts, cold_multiplier, throughput, tokens_sec, error_rate,
            cost_req, cost_1k, cold_cost_req, warm_cost_req, cold_cost_1k, warm_cost_1k,
            energy_1k, gpu_util, "$RUN_DIR", "$DEPLOY_TIME", "success"
        ])

    print("  ✅ Metrics extracted")

except Exception as e:
    print(f"  ❌ Failed to extract metrics: {e}")
    # Write failure row
    with open("$OUTPUT", "a") as f:
        writer = csv.writer(f)
        writer.writerow([
            "$container_concurrency", "$initial_scale", "$scale_grace",
            "$stable_window", "$panic_window",
            "PARSE_ERROR", "PARSE_ERROR", "PARSE_ERROR", "", "", "", "",
            "", "", "", "", "", "", "", "", "", "", "",
            "", "", "$RUN_DIR", "$DEPLOY_TIME", "parse_error"
        ])
EOF
            else
              echo "  ❌ No results.json found"
              # Record missing results
              echo "$container_concurrency,$initial_scale,$scale_grace,$stable_window,$panic_window,NO_RESULTS,NO_RESULTS,NO_RESULTS,,,,,,,,,,,,,,,,$RUN_DIR,$DEPLOY_TIME,no_results" >>"$OUTPUT"
            fi

          else
            echo "  ❌ Benchmark failed"
            echo "$container_concurrency,$initial_scale,$scale_grace,$stable_window,$panic_window,BENCHMARK_FAIL,BENCHMARK_FAIL,BENCHMARK_FAIL,,,,,,,,,,,,,,,,$RUN_DIR,$DEPLOY_TIME,benchmark_failed" >>"$OUTPUT"
          fi

          # Cleanup service for next run
          if [[ "$CLEANUP_BETWEEN_RUNS" == "true" ]]; then
            cleanup_service "$RUN_SERVICE"
          fi

          # Brief pause between runs
          sleep 10

        done
      done
    done
  done
done

echo ""
echo "=== Autoscaling Sweep Complete ==="
echo "Results written to: $OUTPUT"
echo "Total runs: $RUN_COUNT"

# Generate summary analysis
echo ""
echo "=== Top Configurations ==="

# Find best configurations by different criteria
OUTPUT_CSV="$OUTPUT" python3 <<'EOF'
import pandas as pd
import sys
import os

try:
    df = pd.read_csv(os.environ.get("OUTPUT_CSV", "autoscale_sweep_results.csv"))
    # Filter out failed runs
    df_success = df[df['notes'] == 'success'].copy()

    if len(df_success) == 0:
        print("❌ No successful runs found")
        sys.exit(0)

    print(f"📊 Analyzing {len(df_success)} successful configurations out of {len(df)} total")
    print("")

    # Convert string columns to numeric where possible
    numeric_cols = ['p50_ms', 'p95_ms', 'p99_ms', 'cold_multiplier', 'throughput_rps', 'cost_per_1k_tokens']
    for col in numeric_cols:
        if col in df_success.columns:
            df_success[col] = pd.to_numeric(df_success[col], errors='coerce')

    # Best P95 latency
    if not df_success['p95_ms'].isna().all():
        best_p95 = df_success.loc[df_success['p95_ms'].idxmin()]
        print("🏆 BEST P95 LATENCY:")
        print(f"  Config: concurrency={best_p95['container_concurrency']}, initialScale={best_p95['initial_scale']}, gracePeriod={best_p95['scale_to_zero_grace_period']}")
        print(f"  P95: {best_p95['p95_ms']:.1f}ms, Cold starts: {best_p95['cold_start_count']}")
        print("")

    # Lowest cold start penalty
    if not df_success['cold_multiplier'].isna().all():
        best_cold = df_success.loc[df_success['cold_multiplier'].idxmin()]
        print("❄️  LOWEST COLD START PENALTY:")
        print(f"  Config: concurrency={best_cold['container_concurrency']}, initialScale={best_cold['initial_scale']}, gracePeriod={best_cold['scale_to_zero_grace_period']}")
        print(f"  Cold multiplier: {best_cold['cold_multiplier']:.2f}x, P95: {best_cold['p95_ms']:.1f}ms")
        print("")

    # Best cost efficiency
    if not df_success['cost_per_1k_tokens'].isna().all():
        best_cost = df_success.loc[df_success['cost_per_1k_tokens'].idxmin()]
        print("💰 BEST COST EFFICIENCY:")
        print(f"  Config: concurrency={best_cost['container_concurrency']}, initialScale={best_cost['initial_scale']}, gracePeriod={best_cost['scale_to_zero_grace_period']}")
        print(f"  Cost: ${best_cost['cost_per_1k_tokens']:.4f}/1K tokens, P95: {best_cost['p95_ms']:.1f}ms")
        print("")

    # Scale-to-zero analysis
    scale_to_zero = df_success[df_success['initial_scale'] == 0]
    pre_warmed = df_success[df_success['initial_scale'] > 0]

    if len(scale_to_zero) > 0 and len(pre_warmed) > 0:
        stz_avg_p95 = scale_to_zero['p95_ms'].mean()
        pw_avg_p95 = pre_warmed['p95_ms'].mean()
        stz_avg_cost = scale_to_zero['cost_per_1k_tokens'].mean()
        pw_avg_cost = pre_warmed['cost_per_1k_tokens'].mean()

        print("🔄 SCALE-TO-ZERO vs PRE-WARMED ANALYSIS:")
        print(f"  Scale-to-zero (initialScale=0): P95={stz_avg_p95:.1f}ms, Cost=${stz_avg_cost:.4f}/1K tokens")
        print(f"  Pre-warmed (initialScale>0): P95={pw_avg_p95:.1f}ms, Cost=${pw_avg_cost:.4f}/1K tokens")

        if stz_avg_cost > 0 and pw_avg_cost > 0:
            cost_savings = (pw_avg_cost - stz_avg_cost) / pw_avg_cost * 100
            latency_penalty = (stz_avg_p95 - pw_avg_p95) / pw_avg_p95 * 100
            print(f"  Trade-off: {cost_savings:.1f}% cost savings for {latency_penalty:.1f}% higher P95")
        print("")

except Exception as e:
    print(f"❌ Analysis failed: {e}")

EOF

echo ""
echo "💡 **Recommendations**:"
echo "1. Review configurations with lowest cold start multiplier for latency-sensitive workloads"
echo "2. Consider pre-warming (initialScale>0) if cost impact is acceptable"
echo "3. Tune containerConcurrency based on your model's optimal batch size"
echo "4. Use longer scaleToZeroGracePeriod for bursty traffic patterns"
echo ""
echo "📂 Individual run data available in runs/autoscale_* directories"
