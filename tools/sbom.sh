#!/usr/bin/env bash

set -euo pipefail

NAMESPACE=""
SERVICE=""
OUT_DIR="sboms"

usage() {
  echo "Usage: $0 --namespace NS --service NAME [--out-dir DIR]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace) NAMESPACE="$2"; shift 2;;
    --service) SERVICE="$2"; shift 2;;
    --out-dir) OUT_DIR="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
  esac
done

if [[ -z "$NAMESPACE" || -z "$SERVICE" ]]; then
  usage; exit 1
fi

if ! command -v syft >/dev/null 2>&1; then
  echo "ERROR: 'syft' not found. Install from https://github.com/anchore/syft" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"

echo "Discovering images for $SERVICE in $NAMESPACE..."
POD_JSON=$(kubectl get pods -n "$NAMESPACE" -l "serving.kserve.io/inferenceservice=$SERVICE" -o json)
IMAGES=$(echo "$POD_JSON" | python3 - << 'PY'
import sys, json
data = json.load(sys.stdin)
imgs = set()
for item in data.get('items', []):
    for c in item.get('spec', {}).get('containers', []):
        if 'image' in c:
            imgs.add(c['image'])
print('\n'.join(imgs))
PY
)

if [[ -z "$IMAGES" ]]; then
  echo "No images found." >&2
  exit 1
fi

for img in $IMAGES; do
  SAFE=$(echo "$img" | sed 's/[^a-zA-Z0-9_.-]/_/g')
  OUT="$OUT_DIR/sbom-${SAFE}.spdx.json"
  echo "Generating SBOM for $img -> $OUT"
  syft packages "$img" -o spdx-json > "$OUT" || echo "WARNING: syft failed for $img" >&2
done

echo "SBOMs written to $OUT_DIR"

