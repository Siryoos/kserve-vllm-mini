# Troubleshooting Guide

Common issues and fixes when running kserve-vllm-mini benchmarks.

## Deployment
- InferenceService stuck NotReady
  - Check image pull, ServingRuntime name, and `kubectl describe isvc/<name>` events.
  - For Triton/TensorRT-LLM ensure model repo path is correct and engines exist.

- Pods crashloop with OOM
  - Reduce `max_tokens` and/or concurrency, enable INT4 quantization.
  - Increase memory limits or choose larger MIG slice.

## Benchmarking
- Load test fails with connection errors
  - Ensure `status.url` is reachable (network/DNS/mesh), and the service is Ready.
  - Add `--insecure` if using self-signed TLS in-cluster.

- TTFT unusually high
  - Enable streaming if supported, reduce initial prompt size, or enable context FMHA (TRT-LLM).

- Throughput much lower than expected
  - Increase concurrency, verify batching is enabled (vLLM), check GPU utilization.

## Quantization
- Model fails to load with AWQ/GPTQ
  - Use a pre-quantized model compatible with the chosen method.
  - See docs/models/OPTIMIZATIONS.md for guidance.

## MIG
- Scheduling fails on MIG nodes
  - Verify device plugin resources (e.g., `nvidia.com/mig-1g.5gb`).
  - Use the sample profiles in `profiles/mig/` to set correct resource keys.

## Cloud
- Storage access denied
  - Configure IRSA/Workload Identity/Managed Identity for S3/GCS/Azure Blob access.

Links:
- docs/FEATURES.md
- docs/models/OPTIMIZATIONS.md
- docs/MIG.md
- docs/cloud/aws.md, docs/cloud/gcp.md, docs/cloud/azure.md
