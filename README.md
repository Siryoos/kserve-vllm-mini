# kserve-vllm-mini

Minimal, boringly reliable tool to deploy an LLM with **KServe + vLLM**, run a repeatable micro-benchmark, and produce objective numbers:

- p50/p95 latency, throughput (RPS), tokens/sec
- error rate, cold-start count, time-to-first-token (TTFT)
- GPU/CPU/memory utilization (via Prometheus/DCGM)
- estimated cost per 1K tokens and per request

Outputs a single timestamped `results.json` per run, plus ready-to-import Grafana dashboards.

## Features
- Minimal `InferenceService` for vLLM with GPU and autoscaling annotations
- One-command deploy (`deploy.sh`) and benchmark (`bench.sh`)
- Async OpenAI-compatible load generator: `load-test.sh` → `scripts/loadtest.py`
- Analyzer (`analyze.py`) to compute latencies, TTFT, RPS, tokens/sec, error rate, cold starts, and utilization (Prometheus)
- Cost model (`cost_estimator.py`) driven by editable `cost.yaml` (GPU/CPU/Mem/unit pricing)
- Grafana dashboards for per-namespace/pod GPU/CPU/Mem and Istio p50/p95
- Portable and air-gapped-friendly (S3/MinIO storageUri, no hard cloud deps)

## Prerequisites
- Kubernetes ≥ 1.29 with at least 1 NVIDIA GPU node
- NVIDIA drivers + device plugin installed
- KServe installed (with vLLM runtime available)
- Access to an S3-compatible bucket for `storageUri` (e.g., MinIO)

## Quick Start

1) Deploy the service (runtime `vllm` must exist in your cluster):
```bash
./deploy.sh --namespace ml-prod --service demo-llm \
  --model-uri s3://models/llm-demo/ --runtime vllm
```

2) Run the benchmark end-to-end (200–1,000 requests):
```bash
./bench.sh --namespace ml-prod --service demo-llm \
  --requests 500 --concurrency 20 --model placeholder \
  --prom-url http://prometheus.kube-system.svc.cluster.local:9090
```

This creates `runs/<timestamp>/` containing:
- `requests.csv` — per-request: start_ms, ttfb_ms, latency_ms, status, tokens
- `meta.json` — run parameters
- `results.json` — consolidated metrics and cost estimates

## Load Testing (details)

OpenAI-compatible endpoint required. If your KServe vLLM runtime exposes `/v1/chat/completions`, you can call the loader directly:

```bash
./load-test.sh --url "$(kubectl -n ml-prod get isvc demo-llm -o jsonpath='{.status.url}')" \
  --model placeholder --requests 500 --concurrency 20 --max-tokens 64
```

The loader measures per-request latency and time-to-first-token (TTFT) via streaming, and attempts to parse `usage` to record token counts (if provided by your runtime).

## Cost Estimation

Edit `cost.yaml` to reflect your unit pricing (GPU SKUs, CPU/mem hourly). The estimator uses actual pods and their resource requests/limits to compute resource-seconds during the run window, then allocates cost across requests/tokens:

```bash
python3 cost_estimator.py --run-dir runs/<timestamp> \
  --namespace ml-prod --service demo-llm --cost-file cost.yaml
```

It updates `results.json` with `cost_per_request` and `cost_per_1k_tokens`, plus a breakdown.

## Files Overview

- `isvc.yaml` — Minimal KServe InferenceService (GPU, autoscaling hints)
- `deploy.sh` — One-command deployment and readiness check
- `bench.sh` — One-command benchmark: load → analyze → cost → results.json
- `load-test.sh` / `scripts/loadtest.py` — Async OpenAI-compatible load generator
- `analyze.py` — p50/p95, RPS, TTFT, tokens/sec, error rate, cold starts, utilization
- `cost.yaml` — Unit pricing (GPU/CPU/mem)
- `cost_estimator.py` — Cost per request and per 1K tokens
- `dashboards/` — Grafana JSON: utilization and latency panels
- `README.md`, `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`

## Cleanup

```bash
kubectl -n ml-prod delete -f isvc.yaml
kubectl delete ns ml-prod
```

## License

* Code: Apache-2.0 (see `LICENSE`)
* Docs/screenshots: CC BY 4.0
* Sample data/snippets: CC0-1.0

See `NOTICE` and `THIRD_PARTY_NOTICES.md` for third-party attributions.
