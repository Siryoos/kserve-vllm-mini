#!/usr/bin/env bash

set -euo pipefail

IMAGE=""
IMAGES_FILE=""
KEY="cosign.key"

usage() {
  echo "Usage: $0 [--image IMAGE | --images-file FILE] [--key cosign.key]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) IMAGE="$2"; shift 2;;
    --images-file) IMAGES_FILE="$2"; shift 2;;
    --key) KEY="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
  esac
done

if ! command -v cosign >/dev/null 2>&1; then
  echo "ERROR: 'cosign' not found. Install from https://github.com/sigstore/cosign" >&2
  exit 2
fi

IMAGES=()
if [[ -n "$IMAGE" ]]; then
  IMAGES+=("$IMAGE")
elif [[ -n "$IMAGES_FILE" ]]; then
  mapfile -t IMAGES < "$IMAGES_FILE"
else
  echo "ERROR: provide --image or --images-file" >&2
  usage; exit 1
fi

for img in "${IMAGES[@]}"; do
  echo "Signing $img with key $KEY"
  COSIGN_YES=1 cosign sign --key "$KEY" "$img" || echo "WARNING: sign failed for $img" >&2
done

echo "Done. Verify with: cosign verify --key $KEY.pub <image>"

