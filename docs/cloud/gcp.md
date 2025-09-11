# GCP (GKE) Deployment Guide for TensorRT-LLM

Run Triton TensorRT-LLM with KServe on GKE with NVIDIA GPUs.

## Prerequisites

- GKE Autopilot or Standard with GPU nodes (A100/H100/L4)
- GCS bucket for model repository and appropriate workload identity bindings
- NVIDIA drivers and device plugin via GKE add-ons or DaemonSets

## Steps

1) Create cluster with GPU node pool

```bash
gcloud container clusters create trtllm --zone us-central1-c --num-nodes 1 --machine-type a2-highgpu-1g
```

2) Install KServe and Triton ServingRuntime

Follow KServe docs. Ensure a Triton runtime (e.g., `kserve-tritonserver`) exists.

3) Prepare model repo in GCS

```
gs://<bucket>/models/triton/<model>/
└── [ensemble, tokenizer, tensorrt_llm_bls]
```

4) Deploy InferenceService

```bash
runners/backends/triton/deploy.sh --model llama-7b --namespace ml-prod --streaming false
```

5) Benchmark

```bash
URL=$(kubectl get isvc llama-7b-triton -n ml-prod -o jsonpath='{.status.url}')
runners/backends/triton/invoke.sh --url "$URL" --requests 200 --concurrency 10 --max-tokens 64 --run-dir runs/gcp-test
```

## Tips

- L4 nodes are cost‑efficient for smaller models; A100/H100 for large models and FP8 KV cache
- Use Workload Identity for GCS access; avoid node-scoped credentials
