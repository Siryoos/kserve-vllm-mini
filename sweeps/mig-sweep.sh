#!/usr/bin/env bash

# MIG sweep across profiles to build a comparison matrix.
#
# Usage:
#   ./sweeps/mig-sweep.sh \
#     --profiles a100-1g.5gb,a100-2g.10gb,full \
#     --profile-file runners/profiles/standard.yaml \
#     --namespace ml-prod --service demo-llm \
#     [--prom-url http://prometheus.kube-system:9090]
#
set -euo pipefail

PROFILES="a100-1g.5gb,a100-2g.10gb,full"
PROFILE_FILE="runners/profiles/standard.yaml"
NAMESPACE="ml-prod"
SERVICE="demo-llm"
PROM_URL=""
OUT_DIR="runs/mig-$(date +%Y-%m-%d_%H-%M-%S)"

usage() {
  echo "Usage: $0 [--profiles list] [--profile-file path] [--namespace NS] [--service NAME] [--prom-url URL] [--out-dir DIR]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profiles) PROFILES="$2"; shift 2;;
    --profile-file) PROFILE_FILE="$2"; shift 2;;
    --namespace) NAMESPACE="$2"; shift 2;;
    --service) SERVICE="$2"; shift 2;;
    --prom-url) PROM_URL="$2"; shift 2;;
    --out-dir) OUT_DIR="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
  esac
done

mkdir -p "$OUT_DIR"
CSV="$OUT_DIR/mig_matrix.csv"
echo "profile,p50_ms,p95_ms,throughput_rps,Wh_per_1k_tokens,cost_per_1k_tokens,error_rate" > "$CSV"

# Read basic load settings from PROFILE_FILE (YAML with keys: requests, concurrency, max_tokens, pattern)
yaml_get() {
  local key=$1
  local file=$2
  python3 - "$key" "$file" << 'PY'
import sys, yaml
key, path = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = yaml.safe_load(f)
print(data.get(key, ""))
PY
}

REQS=$(yaml_get requests "$PROFILE_FILE" || echo 200)
CONC=$(yaml_get concurrency "$PROFILE_FILE" || echo 10)
TOKS=$(yaml_get max_tokens "$PROFILE_FILE" || echo 64)
PATTERN=$(yaml_get pattern "$PROFILE_FILE" || echo steady)

apply_profile() {
  local name=$1
  local tmp=$(mktemp)
  cp isvc.yaml "$tmp"
  # Patch namespace/service from deploy.sh path to keep consistency
  sed -i -E "s/^(\s*)name:\s*.*/\1name: $SERVICE/" "$tmp"
  sed -i -E "s/^(\s*)namespace:\s*.*/\1namespace: $NAMESPACE/" "$tmp"

  case "$name" in
    full)
      # Ensure full GPU
      sed -i "/nvidia.com\/gpu:/!b;n;" "$tmp" 2>/dev/null || true
      # Remove any MIG resource keys if present and set full GPU=1
      # Replace resources.limits block for GPU
      python3 - "$tmp" << 'PY'
import sys, yaml
p = sys.argv[1]
with open(p) as f:
    doc = yaml.safe_load(f)
limits = doc['spec']['predictor']['model']['resources'].setdefault('limits', {})
limits.pop('nvidia.com/mig-1g.5gb', None)
limits.pop('nvidia.com/mig-2g.10gb', None)
limits['nvidia.com/gpu'] = '1'
# Remove nodeSelector MIG constraints if present
doc['spec']['predictor'].setdefault('nodeSelector', {})
ns = doc['spec']['predictor']['nodeSelector']
ns.pop('nvidia.com/mig.capable', None)
with open(p, 'w') as f:
    yaml.safe_dump(doc, f, sort_keys=False)
PY
      ;;
    a100-1g.5gb)
      python3 - "$tmp" << 'PY'
import sys, yaml
from copy import deepcopy
path = sys.argv[1]
with open(path) as f:
    doc = yaml.safe_load(f)
res = doc['spec']['predictor']['model'].setdefault('resources', {})
limits = res.setdefault('limits', {})
limits.pop('nvidia.com/gpu', None)
limits['nvidia.com/mig-1g.5gb'] = '1'
doc['spec']['predictor'].setdefault('nodeSelector', {})['nvidia.com/mig.capable'] = 'true'
with open(path, 'w') as f:
    yaml.safe_dump(doc, f, sort_keys=False)
PY
      ;;
    a100-2g.10gb)
      python3 - "$tmp" << 'PY'
import sys, yaml
path = sys.argv[1]
with open(path) as f:
    doc = yaml.safe_load(f)
res = doc['spec']['predictor']['model'].setdefault('resources', {})
limits = res.setdefault('limits', {})
limits.pop('nvidia.com/gpu', None)
limits['nvidia.com/mig-2g.10gb'] = '1'
doc['spec']['predictor'].setdefault('nodeSelector', {})['nvidia.com/mig.capable'] = 'true'
with open(path, 'w') as f:
    yaml.safe_dump(doc, f, sort_keys=False)
PY
      ;;
    *) echo "Unknown profile: $name" >&2; return 1;;
  esac

  kubectl -n "$NAMESPACE" apply -f "$tmp" >/dev/null
  rm -f "$tmp"
}

for prof in ${PROFILES//,/ }; do
  echo "=== MIG profile: $prof ==="
  apply_profile "$prof"
  echo "Waiting for $SERVICE to be READY..."
  kubectl wait --for=condition=Ready --timeout=600s inferenceservice/$SERVICE -n $NAMESPACE

  RUN_ID="${OUT_DIR}/${prof}-$(date +%H%M%S)"
  mkdir -p "$RUN_ID"

  ./bench.sh --namespace "$NAMESPACE" --service "$SERVICE" \
    --requests "$REQS" --concurrency "$CONC" --model placeholder \
    --pattern "$PATTERN" ${PROM_URL:+--prom-url "$PROM_URL"} --run-dir "$RUN_ID" >/dev/null

  python3 - "$RUN_ID" "$CSV" "$prof" << 'PY'
import json, sys
from pathlib import Path
run_dir, csv_path, prof = sys.argv[1:4]
res = json.load(open(Path(run_dir) / 'results.json'))
def get(k, d=None):
    return res.get(k, d)
p50 = get('p50_ms')
p95 = get('p95_ms')
rps = get('throughput_rps')
wh1k = get('energy_wh_per_1k_tokens')
cost1k = get('cost_per_1k_tokens')
err = get('error_rate')
with open(csv_path, 'a') as f:
    f.write(f"{prof},{p50},{p95},{rps},{wh1k},{cost1k},{err}\n")
PY
done

echo "\nMatrix written: $CSV"

