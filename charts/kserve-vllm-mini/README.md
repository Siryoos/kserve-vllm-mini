# kserve-vllm-mini Helm Chart

This chart deploys a KServe InferenceService for vLLM and optionally wires in the existing `charts/kvmini` benchmark harness as a subchart. It can also create a vLLM ServingRuntime for clusters that don’t already have one.

## Features
- KServe `InferenceService` (v1beta1)
- Optional `ServingRuntime` (v1alpha1) for vLLM
- Optional S3 credential Secret injection for model `storageUri`
- Optional benchmark harness via `kvmini` subchart (PVC + RBAC managed by subchart)

## Installation
```bash
# Minimal install (InferenceService only)
helm upgrade --install vllm charts/kserve-vllm-mini --dependency-update \
  -f charts/kserve-vllm-mini/examples/values-minimal.yaml \
  --namespace ml-prod --create-namespace \
  --wait
```

Makefile shortcuts (namespace defaults to ml-prod, override with NS=<your-ns>):
```bash
make helm-install-minimal
make helm-install-with-kvmini
make helm-install-runtime
make helm-install-s3
make helm-test            # runs the chart's Helm tests
```

Enable the benchmark harness (kvmini subchart):
```bash
helm upgrade --install vllm charts/kserve-vllm-mini --dependency-update \
  -f charts/kserve-vllm-mini/examples/values-with-kvmini.yaml \
  --namespace ml-prod --create-namespace \
  --wait
```

Optionally, create S3 credentials Secret for the InferenceService:
```bash
helm upgrade --install vllm charts/kserve-vllm-mini --dependency-update \
  -f charts/kserve-vllm-mini/examples/values-s3.yaml \
  --namespace ml-prod --create-namespace \
  --wait
```

If your cluster does not already have the vLLM `ServingRuntime`, enable it:
```bash
helm upgrade --install vllm charts/kserve-vllm-mini --dependency-update \
  -f charts/kserve-vllm-mini/examples/values-runtime.yaml \
  --namespace ml-prod --create-namespace \
  --wait
```

## Values
See `values.yaml` and `values.schema.json` for the full list of configurable options.

Key sections:
- `inferenceService.*`: Configure name, annotations, `predictor.runtime`, `predictor.storageUri`, `predictor.resources`, and optional S3 Secret.
- `servingRuntime.*`: Enable if needed and set the vLLM runtime container image and basic resources.
- `kvmini.*`: Parent values to enable and override settings in the `kvmini` subchart (e.g., image, resources, persistence).
- `global.*`: Auto-wire kvmini to your InferenceService without repeating flags:
  - `global.isvc.name`, `global.isvc.namespace` mapped to your service
  - `global.model.storageUri` mapped to your model path
  - kvmini defaults to these for `--namespace`, `--service`, and `--model` in NOTES and injects env vars.

## Notes
- This chart does not manage Knative/KServe installation; ensure these are present in the cluster.
- The default `ServingRuntime` is disabled to avoid clobbering cluster-managed runtimes.
- GPU scheduling requires NVIDIA device plugin and appropriate node labeling.
- Subchart `kvmini` can be toggled with `kvmini.enabled` and customized via `kvmini.*` values.
- Example values under `charts/kserve-vllm-mini/examples/` cover common setups.
- Helm tests: a smoke test Pod will curl the predictor service at `/v1/models` and report readiness.

## Uninstall
```bash
helm uninstall vllm -n ml-prod
```
