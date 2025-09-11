#!/bin/bash

# Chaos & Resilience Harness
# Injects controlled faults and records MTTR, p95 under fault, and SLO gate outcomes.
#
# Faults:
#  - device_plugin_restart
#  - pod_preemption
#  - pod_oom_kill (simulated by SIGKILL)
#  - netem_packet_loss (on predictor pod)
#  - node_drain
#
# Usage:
#  tools/chaos_harness.sh --namespace benchmark --service llama2-7b --model llama2-7b \
#     --slo slo.json --prom-url http://prom:9090 --requests 200 --concurrency 10

set -euo pipefail

NS="benchmark"
SVC="demo-llm"
MODEL="placeholder"
PROM_URL=""
REQUESTS=200
CONCURRENCY=10
MAX_TOKENS=64
SLO_FILE="slo.json"
RUNS_DIR="runs"

usage() {
  echo "Usage: $0 --namespace NS --service SVC --model NAME [--requests N] [--concurrency N] [--max-tokens N] [--prom-url URL] [--slo PATH]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NS="$2"
      shift 2
      ;;
    --service)
      SVC="$2"
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
    --prom-url)
      PROM_URL="$2"
      shift 2
      ;;
    --slo)
      SLO_FILE="$2"
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

timestamp() { date -u +%s; }

get_predictor_pod() {
  kubectl -n "$NS" get pod -l "serving.kserve.io/inferenceservice=$SVC" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true
}

get_pod_node() {
  kubectl -n "$NS" get pod "$1" -o jsonpath='{.spec.nodeName}' 2>/dev/null || true
}

wait_isvc_ready() {
  local start_ts
  start_ts=$(timestamp)
  if kubectl -n "$NS" wait --for=condition=ready "inferenceservice/$SVC" --timeout=600s >/dev/null 2>&1; then
    local end_ts
    end_ts=$(timestamp)
    echo $((end_ts - start_ts))
  else
    echo 600
  fi
}

run_bench() {
  local tag="$1"
  local run_id
  run_id="chaos_${SVC}_${tag}_$(date +%Y%m%d_%H%M%S)"
  kvmini bench --namespace "$NS" --service "$SVC" --model "$MODEL" \
    --requests "$REQUESTS" --concurrency "$CONCURRENCY" --max-tokens "$MAX_TOKENS" \
    ${PROM_URL:+--prom-url "$PROM_URL"} --run-id "$run_id"
  echo "$RUNS_DIR/$run_id"
}

record_result() {
  local fault="$1"
  shift
  local mttr_s="$1"
  shift
  local run_dir="$1"
  shift
  local results_json="$run_dir/results.json"
  local gate_status="unknown"
  if [[ -f "$results_json" && -f "$SLO_FILE" ]]; then
    if python3 tools/gate.py --results "$results_json" --slo "$SLO_FILE" >/dev/null 2>&1; then
      gate_status="pass"
    else
      gate_status="fail"
    fi
  fi
  local p95
  p95=$(jq -r '.p95_ms // 0' "$results_json" 2>/dev/null || echo 0)
  echo "{\"fault\":\"$fault\",\"mttr_s\":$mttr_s,\"p95_ms\":$p95,\"slo_gate\":\"$gate_status\",\"run_dir\":\"$run_dir\"}"
}

RESULTS=()

echo "=== Baseline ==="
BASE_RUN_DIR=$(run_bench baseline)
echo "Baseline run directory: $BASE_RUN_DIR"

echo "=== 1) device_plugin_restart ==="
{
  set +e
  # Attempt rollout restart of NVIDIA device plugin
  NS_DP=$(kubectl get ns -o name | grep -Eo 'nvidia.*device.*|gpu-operator' | head -n1 | sed 's#namespace/##')
  MTTR=0
  if [[ -n "$NS_DP" ]]; then
    kubectl -n "$NS_DP" rollout restart daemonset | true
    MTTR=$(wait_isvc_ready)
  fi
  RUN_DIR=$(run_bench device_plugin_restart)
  RESULTS+=("$(record_result device_plugin_restart "$MTTR" "$RUN_DIR")")
  set -e
}

echo "=== 2) pod_preemption ==="
{
  set +e
  POD=$(get_predictor_pod)
  MTTR=0
  if [[ -n "$POD" ]]; then
    kubectl -n "$NS" delete pod "$POD" --grace-period=0 --force | true
    MTTR=$(wait_isvc_ready)
  fi
  RUN_DIR=$(run_bench pod_preemption)
  RESULTS+=("$(record_result pod_preemption "$MTTR" "$RUN_DIR")")
  set -e
}

echo "=== 3) pod_oom_kill (simulated) ==="
{
  set +e
  POD=$(get_predictor_pod)
  MTTR=0
  if [[ -n "$POD" ]]; then
    # Simulate abrupt container death
    kubectl -n "$NS" exec "$POD" -- /bin/sh -c 'kill -9 1' | true
    MTTR=$(wait_isvc_ready)
  fi
  RUN_DIR=$(run_bench pod_oom_kill)
  RESULTS+=("$(record_result pod_oom_kill "$MTTR" "$RUN_DIR")")
  set -e
}

echo "=== 4) netem_packet_loss ==="
{
  set +e
  POD=$(get_predictor_pod)
  MTTR=0
  if [[ -n "$POD" ]]; then
    kubectl -n "$NS" exec "$POD" -- bash -lc 'which tc && sudo tc qdisc add dev eth0 root netem loss 10% delay 50ms 10ms' 2>/dev/null || true
    RUN_DIR=$(run_bench netem_loss)
    kubectl -n "$NS" exec "$POD" -- bash -lc 'sudo tc qdisc del dev eth0 root' 2>/dev/null || true
  else
    RUN_DIR=$(run_bench netem_loss)
  fi
  RESULTS+=("$(record_result netem_packet_loss "$MTTR" "$RUN_DIR")")
  set -e
}

echo "=== 5) node_drain ==="
{
  set +e
  POD=$(get_predictor_pod)
  NODE=""
  MTTR=0
  if [[ -n "$POD" ]]; then
    NODE=$(get_pod_node "$POD")
    if [[ -n "$NODE" ]]; then
      kubectl drain "$NODE" --ignore-daemonsets --delete-emptydir-data --force --timeout=5m | true
      MTTR=$(wait_isvc_ready)
      kubectl uncordon "$NODE" | true
    fi
  fi
  RUN_DIR=$(run_bench node_drain)
  RESULTS+=("$(record_result node_drain "$MTTR" "$RUN_DIR")")
  set -e
}

# Write resilience table
OUT_DIR="$RUNS_DIR/chaos_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"
(
  echo "["
  for i in "${!RESULTS[@]}"; do
    echo "  ${RESULTS[$i]}"
    if [[ $i -lt $((${#RESULTS[@]} - 1)) ]]; then echo ","; fi
  done
  echo "]"
) >"$OUT_DIR/resilience_table.json"

printf "\n✅ Resilience table: %s\n" "$OUT_DIR/resilience_table.json"
sed -e 's/^/  /' "$OUT_DIR/resilience_table.json"
