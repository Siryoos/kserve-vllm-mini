#!/bin/bash

# Bundle complete run artifacts for audit and reproduction
# Usage: ./bundle_run.sh --run-dir runs/2025-01-01_12-00-00 --namespace NS --service NAME [--output bundle.tar.gz]

set -euo pipefail

RUN_DIR=""
NAMESPACE=""
SERVICE=""
OUTPUT=""
INCLUDE_GRAFANA_PNGS=true
INCLUDE_TRACES=true
INCLUDE_SBOM=true
INCLUDE_SIGNATURES=true

usage() {
  echo "Usage: $0 --run-dir DIR --namespace NS --service NAME [--output FILE] [--no-grafana] [--no-traces] [--no-sbom] [--no-signatures]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir) RUN_DIR="$2"; shift 2;;
    --namespace) NAMESPACE="$2"; shift 2;;
    --service) SERVICE="$2"; shift 2;;
    --output) OUTPUT="$2"; shift 2;;
    --no-grafana) INCLUDE_GRAFANA_PNGS=false; shift;;
    --no-traces) INCLUDE_TRACES=false; shift;;
    --no-sbom) INCLUDE_SBOM=false; shift;;
    --no-signatures) INCLUDE_SIGNATURES=false; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
  esac
done

if [[ -z "$RUN_DIR" || -z "$NAMESPACE" || -z "$SERVICE" ]]; then
  echo "ERROR: --run-dir, --namespace, and --service are required" >&2
  usage
  exit 1
fi

if [[ ! -d "$RUN_DIR" ]]; then
  echo "ERROR: Run directory $RUN_DIR does not exist" >&2
  exit 1
fi

# Determine output file
if [[ -z "$OUTPUT" ]]; then
  RUN_ID=$(basename "$RUN_DIR")
  OUTPUT="artifacts/${RUN_ID}.tar.gz"
fi

echo "=== Bundling Run Artifacts ==="
echo "Run directory: $RUN_DIR"
echo "Service: $SERVICE (namespace: $NAMESPACE)"
echo "Output: $OUTPUT"
echo ""

# Create temporary bundle directory
BUNDLE_DIR=$(mktemp -d)
BUNDLE_NAME=$(basename "$OUTPUT" .tar.gz)
BUNDLE_PATH="$BUNDLE_DIR/$BUNDLE_NAME"
mkdir -p "$BUNDLE_PATH"

cleanup() {
  rm -rf "$BUNDLE_DIR"
}
trap cleanup EXIT

# 1. Copy core run artifacts
echo "📁 Copying run artifacts..."
if [[ -f "$RUN_DIR/results.json" ]]; then
  cp "$RUN_DIR/results.json" "$BUNDLE_PATH/"
else
  echo "WARNING: No results.json found in $RUN_DIR" >&2
fi

if [[ -f "$RUN_DIR/requests.csv" ]]; then
  cp "$RUN_DIR/requests.csv" "$BUNDLE_PATH/"
fi

if [[ -f "$RUN_DIR/requests_classified.csv" ]]; then
  cp "$RUN_DIR/requests_classified.csv" "$BUNDLE_PATH/"
fi

if [[ -f "$RUN_DIR/meta.json" ]]; then
  cp "$RUN_DIR/meta.json" "$BUNDLE_PATH/"
fi

# Fairness artifacts (if present)
if [[ -f "$RUN_DIR/fairness_summary.json" ]]; then
  echo "🟰 Including fairness artifacts"
  cp "$RUN_DIR/fairness_summary.json" "$BUNDLE_PATH/"
  if [[ -f "$RUN_DIR/fairness_report.html" ]]; then
    cp "$RUN_DIR/fairness_report.html" "$BUNDLE_PATH/"
  fi
fi

# 2. Generate provenance information
echo "🔍 Collecting provenance..."
PROVENANCE_FILE="$BUNDLE_PATH/provenance.json"

# Get run metadata from meta.json if available
RUN_META="{}"
if [[ -f "$RUN_DIR/meta.json" ]]; then
  RUN_META=$(cat "$RUN_DIR/meta.json")
fi

# Get cluster facts
CLUSTER_FACTS_FILE="$BUNDLE_PATH/cluster_facts.json"
./tools/collect_cluster_facts.sh --namespace "$NAMESPACE" --service "$SERVICE" --output "$CLUSTER_FACTS_FILE"

# Generate comprehensive provenance
jq -n \
  --arg run_id "$(basename "$RUN_DIR")" \
  --arg bundle_timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg tool_version "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')" \
  --argjson run_meta "$RUN_META" \
  --argjson cluster_facts "$(cat "$CLUSTER_FACTS_FILE")" \
  '{
    bundle: {
      run_id: $run_id,
      created: $bundle_timestamp,
      tool_version: $tool_version,
      schema_version: "1.0"
    },
    run: $run_meta,
    cluster: $cluster_facts,
    reproducibility: {
      instructions: "Use pinned digests from cluster_facts.json pod_images and identical Kubernetes/KServe versions",
      verification: "Compare results.json metrics against baseline with ±10% tolerance"
    }
  }' > "$PROVENANCE_FILE"

# 3. Collect YAMLs and configs
echo "📄 Collecting configuration files..."
CONFIG_DIR="$BUNDLE_PATH/configs"
mkdir -p "$CONFIG_DIR"

# Copy key config files from repo root
for file in isvc.yaml cost.yaml example-config.yaml; do
  if [[ -f "$file" ]]; then
    cp "$file" "$CONFIG_DIR/"
  fi
done

# Get current InferenceService YAML
if kubectl get inferenceservice "$SERVICE" -n "$NAMESPACE" >/dev/null 2>&1; then
  kubectl get inferenceservice "$SERVICE" -n "$NAMESPACE" -o yaml > "$CONFIG_DIR/deployed_isvc.yaml"
fi

# Get pod specs with resolved images
if kubectl get pods -n "$NAMESPACE" -l "serving.kserve.io/inferenceservice=$SERVICE" >/dev/null 2>&1; then
  kubectl get pods -n "$NAMESPACE" -l "serving.kserve.io/inferenceservice=$SERVICE" -o yaml > "$CONFIG_DIR/actual_pods.yaml"
fi

# 4. Collect Grafana dashboard exports (if requested)
if [[ "$INCLUDE_GRAFANA_PNGS" == "true" ]]; then
  echo "📊 Looking for Grafana artifacts..."
  GRAFANA_DIR="$BUNDLE_PATH/grafana"
  mkdir -p "$GRAFANA_DIR"
  
  # Copy dashboard JSON definitions
  if [[ -d "dashboards" ]]; then
    cp dashboards/*.json "$GRAFANA_DIR/" 2>/dev/null || echo "No dashboard JSONs found"
  fi
  
  # Note: Actual PNG exports would require Grafana API integration
  # For now, include instructions
  cat > "$GRAFANA_DIR/README.md" << EOF
# Grafana Export Instructions

To capture dashboard screenshots for this run:

1. Import dashboards from the JSON files in this directory
2. Set time range to: $(cat "$RUN_DIR/results.json" | jq -r '.window.start') - $(cat "$RUN_DIR/results.json" | jq -r '.window.end')
3. Export panels as PNG
4. Add PNGs to this directory for complete audit trail

Dashboard files included:
$(ls *.json 2>/dev/null | sed 's/^/- /' || echo "- None found")
EOF
fi

# 5. Collect traces (if available and requested)
if [[ "$INCLUDE_TRACES" == "true" ]]; then
  echo "🔍 Looking for trace artifacts..."
  TRACES_DIR="$BUNDLE_PATH/traces"
  mkdir -p "$TRACES_DIR"
  
  if [[ -d "$RUN_DIR/traces" ]]; then
    cp -r "$RUN_DIR/traces"/* "$TRACES_DIR/" 2>/dev/null || echo "No traces found in run directory"
  fi
  
  # Create placeholder for future OTLP integration
  cat > "$TRACES_DIR/README.md" << EOF
# OpenTelemetry Traces

This directory contains distributed traces for request lifecycle analysis.

Current status: Placeholder for future OTLP integration
Run ID: $(basename "$RUN_DIR")
Service: $SERVICE
Namespace: $NAMESPACE

Trace collection will include:
- client.request spans with full latency breakdown
- server.ttft timing
- server.stream chunk processing  
- server.tllt completion timing
EOF
fi

# 6. Generate run summary
echo "📋 Generating run summary..."
SUMMARY_FILE="$BUNDLE_PATH/SUMMARY.md"

cat > "$SUMMARY_FILE" << EOF
# Run Summary

**Run ID**: $(basename "$RUN_DIR")  
**Service**: $SERVICE  
**Namespace**: $NAMESPACE  
**Bundled**: $(date -u +%Y-%m-%d\ %H:%M:%S\ UTC)

## Key Results

$(if [[ -f "$RUN_DIR/results.json" ]]; then
  cat "$RUN_DIR/results.json" | jq -r '
    "**P95 Latency**: " + (.p95_ms // "N/A" | tostring) + "ms",
    "**Throughput**: " + (.throughput_rps // "N/A" | tostring) + " RPS", 
    "**Error Rate**: " + ((.error_rate // 0) * 100 | tostring) + "%",
    "**Cost/1K Tokens**: $" + (.cost_per_1k_tokens // "N/A" | tostring),
    "**Cold Starts**: " + (.cold_start_count // "N/A" | tostring),
    "**Energy**: " + (.energy_wh_per_1k_tokens // "N/A" | tostring) + " Wh/1K tokens"
  '
else
  echo "Results not available"
fi)

## Contents

- \`provenance.json\` - Complete reproducibility metadata
- \`cluster_facts.json\` - Kubernetes cluster state and versions
- \`results.json\` - Benchmark results and metrics
- \`requests.csv\` - Per-request timing data
- \`configs/\` - YAML files and resolved configurations  
- \`grafana/\` - Dashboard definitions and export instructions
- \`traces/\` - OpenTelemetry traces (future)
$(if [[ -f "$RUN_DIR/fairness_summary.json" ]]; then echo "- \`fairness_summary.json\` and \`fairness_report.html\` - Multi-tenant fairness results"; fi)

## Reproduction

1. Use identical Kubernetes/KServe versions from \`cluster_facts.json\`
2. Deploy with pinned image digests from \`configs/deployed_isvc.yaml\`  
3. Run same benchmark parameters from \`meta.json\`
4. Expect ±10% variance in P95 latency metrics

Generated by kserve-vllm-mini v$(git rev-parse HEAD 2>/dev/null || echo 'unknown')
EOF

# 7. Supply chain: SBOMs and signatures (optional)
SUPPLY_DIR="$BUNDLE_PATH/supply-chain"
mkdir -p "$SUPPLY_DIR"

if [[ "$INCLUDE_SBOM" == "true" && -x "tools/sbom.sh" ]]; then
  echo "🧾 Generating SBOMs..."
  ./tools/sbom.sh --namespace "$NAMESPACE" --service "$SERVICE" --out-dir "$SUPPLY_DIR/sboms" || echo "WARNING: SBOM generation failed" >&2
fi

if [[ "$INCLUDE_SIGNATURES" == "true" ]]; then
  # Record images for later signing/verification
  echo "🔐 Recording image list..."
  kubectl get pods -n "$NAMESPACE" -l "serving.kserve.io/inferenceservice=$SERVICE" -o json \
    | jq -r '.items[].spec.containers[].image' | sort -u > "$SUPPLY_DIR/images.txt" || true
  cat > "$SUPPLY_DIR/README.md" << EOF
# Supply Chain Artifacts

This directory contains SBOMs and image lists for signing/verification.

Commands:
- Generate SBOMs: ../../tools/sbom.sh --namespace $NAMESPACE --service $SERVICE --out-dir sboms/
- Sign images:    ../../tools/sign.sh --images-file images.txt --key cosign.key
- Verify:         cosign verify --key cosign.pub <image>
EOF
fi

# 8. Create the final bundle
echo "📦 Creating bundle archive..."
mkdir -p "$(dirname "$OUTPUT")"

# Create tar.gz with consistent timestamps for reproducibility
tar -czf "$OUTPUT" -C "$BUNDLE_DIR" --sort=name --mtime='2024-01-01 00:00:00' "$BUNDLE_NAME"

echo ""
echo "✅ Bundle created: $OUTPUT"
echo "📊 Size: $(du -h "$OUTPUT" | cut -f1)"
echo ""
echo "Contents:"
tar -tzf "$OUTPUT" | head -20
if [[ $(tar -tzf "$OUTPUT" | wc -l) -gt 20 ]]; then
  echo "... and $(($(tar -tzf "$OUTPUT" | wc -l) - 20)) more files"
fi
echo ""
echo "🔍 Verify bundle: tar -tzf $OUTPUT"
echo "📂 Extract: tar -xzf $OUTPUT"
