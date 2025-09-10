# kserve-vllm-mini

Minimal, reproducible setup to deploy an LLM with **KServe + vLLM** on Kubernetes, run a small load test, and record:
- p50/p95 latency
- error rate
- approximate **cost per 1K tokens**

Includes a curl-based micro load test, Grafana screenshots, and a simple cost formula.

## Features
- KServe `InferenceService` for vLLM
- Automated deployment script (`deploy.sh`)
- Comprehensive load testing script (`load-test.sh`)
- Cost calculation tool (`cost-calculator.sh`)
- Quick p50/p95 computation from raw timings
- Simple cost-per-1K-tokens estimator
- Works with Prometheus/Grafana for utilization screenshots

## Prerequisites
- Kubernetes ≥ 1.29 with at least 1 NVIDIA GPU node
- NVIDIA drivers + device plugin installed
- KServe installed (with vLLM runtime available)
- Access to an S3-compatible bucket for `storageUri` (e.g., MinIO)

## Quick Start

### Option 1: Automated Deployment
```bash
# Deploy everything with one command
./deploy.sh

# Run load test
./load-test.sh

# Calculate costs
./cost-calculator.sh /tmp/load-test-results.txt 1.00
```

### Option 2: Manual Deployment
```bash
kubectl create ns ml-prod
kubectl -n ml-prod apply -f isvc.yaml
# Wait until the InferenceService is READY, then get the URL:
kubectl -n ml-prod get inferenceservice demo-llm -o jsonpath='{.status.url}'
```

## Load Testing

### Automated Load Test
```bash
# Run comprehensive load test with statistics
./load-test.sh <model-endpoint> [num-requests]

# Example:
./load-test.sh http://demo-llm.ml-prod.svc.cluster.local 200
```

### Manual Load Test
```bash
# Launch a temporary curl pod:
kubectl -n ml-prod run curler --rm -it --image=curlimages/curl --restart=Never -- sh

# Inside the pod, run 200 requests and capture per-request latency in ms:
for i in $(seq 1 200); do
  t=$(date +%s%3N)
  curl -s -X POST -H 'Content-Type: application/json' \
    -d '{"text":"hello"}' http://<model-endpoint> >/dev/null
  echo $(( $(date +%s%3N) - t ))
done | tee /tmp/times.txt
```

Compute p50/p95 locally:

```bash
sort -n /tmp/times.txt | awk 'BEGIN{n=0}{a[n++]=$1}END{print "p50:",a[int(n*0.50)],"ms\np95:",a[int(n*0.95)],"ms"}'
```

## Cost Estimation

### Automated Cost Calculation
```bash
# Calculate costs from load test results
./cost-calculator.sh <load-test-results> <gpu-hourly-cost> [requests-per-1k-tokens]

# Example:
./cost-calculator.sh /tmp/load-test-results.txt 1.00 10
```

### Manual Cost Calculation

Let:

* `gpu_price_per_second` = (your hourly GPU cost) / 3600
* `avg_latency_seconds`  = average per-request latency in seconds
* `requests_per_1k_tokens` = approx. requests to produce 1000 tokens (adjust to your prompt/decoding)

Formula:

```
cost_per_1k_tokens ≈ gpu_price_per_second * avg_latency_seconds * requests_per_1k_tokens
```

Record p50/p95, error rate, utilization screenshots, and the cost estimate in this README.

## Files Overview

- `isvc.yaml` - Basic KServe InferenceService configuration
- `example-config.yaml` - Extended configuration with additional options
- `deploy.sh` - Automated deployment script
- `load-test.sh` - Comprehensive load testing script
- `cost-calculator.sh` - Cost calculation tool
- `README.md` - This documentation
- `LICENSE` - Apache 2.0 license
- `NOTICE` - Copyright notice
- `THIRD_PARTY_NOTICES.md` - Third-party license information

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