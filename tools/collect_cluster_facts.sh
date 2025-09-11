#!/bin/bash

# Collect cluster facts for run provenance
# Usage: ./collect_cluster_facts.sh --namespace NS --service NAME --output facts.json

set -euo pipefail

NAMESPACE=""
SERVICE=""
OUTPUT="cluster_facts.json"

# Required binaries
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "jq not found" >&2; exit 2; }

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
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

echo "Collecting cluster facts..." >&2

# Get Kubernetes version
K8S_VERSION=$(kubectl version --output=json 2>/dev/null | jq -r '.serverVersion.gitVersion' || echo "unknown")

# Get node information
NODES_JSON=$(kubectl get nodes -o json 2>/dev/null || echo '{"items":[]}')

# Get GPU information from nodes
GPU_INFO=$(echo "$NODES_JSON" | jq -r '.items[] | select(.status.capacity."nvidia.com/gpu"?) | {
  name: .metadata.name,
  gpu_count: .status.capacity."nvidia.com/gpu",
  gpu_product: .metadata.labels."nvidia.com/gpu.product" // "unknown",
  gpu_memory: .metadata.labels."nvidia.com/gpu.memory" // "unknown",
  mig_strategy: .metadata.labels."nvidia.com/mig.strategy" // "none",
  instance_type: .metadata.labels."beta.kubernetes.io/instance-type" // .metadata.labels."node.kubernetes.io/instance-type" // "unknown",
  zone: .metadata.labels."topology.kubernetes.io/zone" // "unknown"
}' 2>/dev/null | jq -s '.' || echo '[]')

# Get KServe/Knative versions if available
KSERVE_VERSION=$(kubectl get deployment -n knative-serving controller -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")
KNATIVE_VERSION=$(kubectl get deployment -n knative-serving activator -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")

# Get Istio version if available
ISTIO_VERSION=$(kubectl get deployment -n istio-system istiod -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")

# Get inference service details if specified
ISVC_INFO="{}"
if [[ -n "$NAMESPACE" && -n "$SERVICE" ]]; then
  ISVC_INFO=$(kubectl get inferenceservice "$SERVICE" -n "$NAMESPACE" -o json 2>/dev/null | jq '{
    name: .metadata.name,
    namespace: .metadata.namespace,
    created: .metadata.creationTimestamp,
    runtime: .spec.predictor.model.runtime // "unknown",
    storage_uri: .spec.predictor.model.storageUri // "unknown",
    resources: .spec.predictor.model.resources // {},
    annotations: .metadata.annotations // {},
    image: (.status.components.predictor.latestCreatedRevision | if . then "unknown" else "unknown" end),
    ready_replicas: .status.components.predictor.traffic[0].latestRevision // "unknown"
  }' || echo '{}')

  # Get actual pod images and digests
  POD_IMAGES=$(kubectl get pods -n "$NAMESPACE" -l "serving.kserve.io/inferenceservice=$SERVICE" -o json 2>/dev/null | jq -r '.items[].spec.containers[] | select(.name != "queue-proxy" and .name != "istio-proxy") | {
    name: .name,
    image: .image,
    digest: (.image | if contains("@sha256:") then (split("@")[1]) else "unknown" end)
  }' | jq -s '.' || echo '[]')
else
  POD_IMAGES="[]"
fi

# Get git information if in a git repo
GIT_INFO="{}"
if git rev-parse --git-dir >/dev/null 2>&1; then
  GIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
  GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  GIT_DIRTY=$(if git diff-index --quiet HEAD -- 2>/dev/null; then echo "false"; else echo "true"; fi)
  GIT_ORIGIN=$(git remote get-url origin 2>/dev/null || echo "unknown")

  GIT_INFO=$(jq -n --arg sha "$GIT_SHA" --arg branch "$GIT_BRANCH" --arg dirty "$GIT_DIRTY" --arg origin "$GIT_ORIGIN" '{
    sha: $sha,
    branch: $branch,
    dirty: ($dirty == "true"),
    origin: $origin
  }')
fi

# Get Helm releases if any
HELM_RELEASES="[]"
if command -v helm >/dev/null 2>&1; then
  HELM_RELEASES=$(helm list -A -o json 2>/dev/null | jq '[.[] | {
    name: .name,
    namespace: .namespace,
    chart: .chart,
    app_version: .app_version,
    status: .status,
    updated: .updated
  }]' 2>/dev/null || echo '[]')
fi

# Assemble final JSON
jq -n \
  --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg k8s_version "$K8S_VERSION" \
  --arg kserve_version "$KSERVE_VERSION" \
  --arg knative_version "$KNATIVE_VERSION" \
  --arg istio_version "$ISTIO_VERSION" \
  --argjson gpu_info "$GPU_INFO" \
  --argjson isvc_info "$ISVC_INFO" \
  --argjson pod_images "$POD_IMAGES" \
  --argjson git_info "$GIT_INFO" \
  --argjson helm_releases "$HELM_RELEASES" \
  '{
    timestamp: $timestamp,
    kubernetes_version: $k8s_version,
    kserve_version: $kserve_version,
    knative_version: $knative_version,
    istio_version: $istio_version,
    gpu_nodes: $gpu_info,
    inference_service: $isvc_info,
    pod_images: $pod_images,
    git: $git_info,
    helm_releases: $helm_releases,
    collection_method: "kserve-vllm-mini/collect_cluster_facts.sh"
  }' >"$OUTPUT"

echo "Cluster facts written to: $OUTPUT" >&2
