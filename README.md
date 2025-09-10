# kserve-vllm-mini

Minimal, reproducible setup to deploy an LLM with **KServe + vLLM** on Kubernetes, run a small load test, and record:
- p50/p95 latency
- error rate
- approximate **cost per 1K tokens**

Includes a curl-based micro load test, Grafana screenshots, and a simple cost formula.

## Features
- KServe `InferenceService` for vLLM
- 200-request curl load test script
- Quick p50/p95 computation from raw timings
- Simple cost-per-1K-tokens estimator
- Works with Prometheus/Grafana for utilization screenshots

## Prerequisites
- Kubernetes ≥ 1.29 with at least 1 NVIDIA GPU node
- NVIDIA drivers + device plugin installed
- KServe installed (with vLLM runtime available)
- Access to an S3-compatible bucket for `storageUri` (e.g., MinIO)

## Deploy
```bash
kubectl create ns ml-prod
kubectl -n ml-prod apply -f isvc.yaml
# Wait until the InferenceService is READY, then get the URL:
kubectl -n ml-prod get inferenceservice demo-llm -o jsonpath='{.status.url}'
