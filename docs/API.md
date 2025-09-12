# API Documentation

This document provides comprehensive documentation for the kserve-vllm-mini toolkit APIs and command-line interfaces.

## Command Line Interface

### bench.sh - Main Benchmarking Tool

The primary entry point for running benchmarks against KServe vLLM deployments.

#### Basic Usage

```bash
./bench.sh [OPTIONS]
```

#### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--namespace` | Kubernetes namespace | `--namespace ml-prod` |
| `--service` | KServe InferenceService name | `--service demo-llm` |
| `--requests` | Number of requests to send | `--requests 500` |
| `--concurrency` | Concurrent connections | `--concurrency 20` |

#### Optional Parameters

| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `--model-uri` | Model S3 URI (for new deployments) | None | `--model-uri s3://models/llama-3.1-8b/` |
| `--profile` | Benchmark profile to use | `runners/profiles/standard.yaml` | `--profile runners/profiles/burst.yaml` |
| `--max-tokens` | Maximum tokens per response | 100 | `--max-tokens 256` |
| `--dry-run` | Validate config without running | false | `--dry-run` |
| `--output-dir` | Custom output directory | `runs/{timestamp}` | `--output-dir results/experiment1` |
| `--skip-deploy` | Use existing service | false | `--skip-deploy` |

#### Examples

```bash
# Basic benchmark
./bench.sh --namespace ml-prod --service demo-llm --requests 500 --concurrency 20

# Deploy new model and benchmark
./bench.sh --namespace ml-prod --service new-llm \
  --model-uri s3://models/llama-3.1-8b/ \
  --requests 200 --concurrency 10

# Burst testing with custom profile
./bench.sh --namespace ml-prod --service demo-llm \
  --profile runners/profiles/burst.yaml \
  --requests 1000 --concurrency 50

# Validate configuration without running
./bench.sh --dry-run --namespace ml-prod --service demo-llm \
  --requests 100 --concurrency 5
```

### analyze.py - Performance Analysis

Post-benchmark analysis and report generation.

#### Usage

```bash
python analyze.py [OPTIONS]
```

#### Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--run-dir` | Directory with benchmark results | `--run-dir runs/2025-09-12_14-30-15` |
| `--namespace` | Kubernetes namespace | `--namespace ml-prod` |
| `--service` | Service name for resource analysis | `--service demo-llm` |
| `--output` | Output file for results | `--output analysis.json` |

#### Examples

```bash
# Analyze latest run
python analyze.py --run-dir runs/$(ls -1t runs | head -1) \
  --namespace ml-prod --service demo-llm

# Example with current date
python analyze.py --run-dir runs/2025-09-12_14-30-15 \
  --namespace ml-prod --service demo-llm

# Generate custom analysis
python analyze.py --run-dir results/experiment1 \
  --output experiment1-analysis.json
```

### cost_estimator.py - Cost Analysis

Calculate deployment costs based on resource usage.

#### Usage

```bash
python cost_estimator.py [OPTIONS]
```

#### Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--namespace` | Kubernetes namespace | `--namespace ml-prod` |
| `--service` | Service name | `--service demo-llm` |
| `--duration` | Analysis duration in hours | `--duration 24` |
| `--cost-config` | Cost configuration file | `--cost-config cost.yaml` |

### report_generator.py - HTML Report Generation

Generate comprehensive HTML reports with charts and analysis.

#### Usage

```bash
python report_generator.py [OPTIONS]
```

#### Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--run-dir` | Input run directory | `--run-dir runs/2025-09-12_14-30-15` |
| `--output` | Output HTML file | `--output report.html` |
| `--template` | Report template | `--template templates/detailed.html` |

## Profile Configuration API

Profiles define benchmark behavior and vLLM configuration.

### Profile Structure

```yaml
# Basic profile structure
metadata:
  name: "standard"
  description: "Standard benchmarking profile"
  version: "1.0"

# Load testing configuration
load_test:
  pattern: "steady"          # steady, burst, ramp
  duration_seconds: 300
  warmup_requests: 50

# Request configuration
request:
  max_tokens: 100
  temperature: 0.8
  top_p: 0.9
  stream: true

# vLLM feature configuration
vllm_features:
  gpu_memory_utilization: 0.90
  quantization: null       # null, awq, gptq, fp8
  speculative_model: null  # draft model for speculative decoding
  guided_decoding_backend: "outlines"
  enable_auto_tool_choice: false

# Resource requirements
resources:
  requests:
    cpu: "2000m"
    memory: "8Gi"
    nvidia.com/gpu: 1
  limits:
    cpu: "4000m"
    memory: "16Gi"
    nvidia.com/gpu: 1

# Validation rules
validation:
  min_success_rate: 0.95
  max_error_rate: 0.05
  max_p95_latency_ms: 1000
```

### Available Profiles

| Profile | Path | Purpose |
|---------|------|---------|
| Standard | `runners/profiles/standard.yaml` | Baseline benchmarking |
| Burst | `runners/profiles/burst.yaml` | Autoscaling testing |
| Speculative | `runners/profiles/speculative-decoding.yaml` | Latency optimization |
| AutoAWQ | `runners/profiles/quantization/autoawq.yaml` | Memory optimization |
| Structured | `runners/profiles/structured-output.yaml` | JSON/tool calling |
| CPU Smoke | `runners/profiles/cpu-smoke.yaml` | Development testing |

## Output Formats

### Benchmark Results (JSON)

```json
{
  "metadata": {
    "timestamp": "2025-09-12T14:30:15Z",
    "namespace": "ml-prod",
    "service": "demo-llm",
    "profile": "standard",
    "total_requests": 500,
    "concurrent_users": 20
  },
  "performance": {
    "p50_latency_ms": 123.4,
    "p95_latency_ms": 342.1,
    "p99_latency_ms": 456.7,
    "avg_ttft_ms": 23.4,
    "throughput_rps": 47.2,
    "success_rate": 0.998,
    "error_rate": 0.002
  },
  "cost": {
    "cost_per_1k_tokens": "$0.0023",
    "hourly_cost": "$2.45",
    "breakdown": {
      "gpu": "$1.80",
      "cpu": "$0.45",
      "memory": "$0.20"
    }
  },
  "energy": {
    "energy_per_1k_tokens_wh": 15.7,
    "total_energy_wh": 1234.5
  },
  "resources": {
    "avg_gpu_utilization": 0.87,
    "avg_memory_usage_gb": 12.3,
    "avg_cpu_usage": 2.1
  }
}
```

### Analysis Output (JSON)

```json
{
  "summary": {
    "total_requests": 500,
    "successful_requests": 499,
    "failed_requests": 1,
    "success_rate": 0.998
  },
  "latency": {
    "percentiles": {
      "p50": 123.4,
      "p90": 234.5,
      "p95": 342.1,
      "p99": 456.7
    },
    "histogram": {
      "bins": [0, 100, 200, 300, 400, 500],
      "counts": [45, 123, 234, 89, 8, 0]
    }
  },
  "throughput": {
    "requests_per_second": 47.2,
    "tokens_per_second": 1234.5
  },
  "errors": [
    {
      "timestamp": "2025-09-12T14:45:23Z",
      "error": "timeout",
      "details": "Request timed out after 30s"
    }
  ]
}
```

## Environment Variables

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `KUBECONFIG` | Kubernetes config file | `~/.kube/config` |
| `KVMINI_NAMESPACE` | Default namespace | `default` |
| `KVMINI_OUTPUT_DIR` | Default output directory | `runs` |
| `KVMINI_COST_CONFIG` | Cost configuration file | `cost.yaml` |

### AWS/S3 Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `AWS_ACCESS_KEY_ID` | AWS access key | Yes (for S3) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | Yes (for S3) |
| `AWS_DEFAULT_REGION` | AWS region | Yes (for S3) |
| `S3_ENDPOINT_URL` | Custom S3 endpoint | No |

### Debug/Logging

| Variable | Description | Values |
|----------|-------------|--------|
| `LOG_LEVEL` | Logging verbosity | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `KVMINI_DEBUG` | Enable debug mode | `true`, `false` |

## Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| 1 | General error | Check logs for details |
| 2 | Configuration error | Validate profile/config |
| 3 | Network/connection error | Check Kubernetes connectivity |
| 4 | Resource error | Check resource availability |
| 5 | Validation error | Fix validation failures |

## Integration APIs

### Kubernetes Resources

The toolkit creates and manages these Kubernetes resources:

#### InferenceService (KServe)

```yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: demo-llm
  namespace: ml-prod
spec:
  predictor:
    model:
      modelFormat:
        name: vllm
      storageUri: s3://models/llama-3.1-8b/
      resources:
        requests:
          cpu: 2000m
          memory: 8Gi
          nvidia.com/gpu: 1
        limits:
          cpu: 4000m
          memory: 16Gi
          nvidia.com/gpu: 1
      env:
        - name: GPU_MEMORY_UTILIZATION
          value: "0.90"
```

#### ConfigMap (vLLM Configuration)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: demo-llm-config
  namespace: ml-prod
data:
  model_config.json: |
    {
      "gpu_memory_utilization": 0.90,
      "quantization": null,
      "max_model_len": 4096
    }
```

### Prometheus Metrics

Available metrics for monitoring:

| Metric | Type | Description |
|--------|------|-------------|
| `kvmini_request_duration_seconds` | Histogram | Request latency distribution |
| `kvmini_requests_total` | Counter | Total requests sent |
| `kvmini_errors_total` | Counter | Total errors encountered |
| `kvmini_gpu_utilization` | Gauge | GPU utilization percentage |
| `kvmini_memory_usage_bytes` | Gauge | Memory usage in bytes |

### HTTP Endpoints

When running as a service, these endpoints are available:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |
| `/api/v1/benchmark` | POST | Start benchmark |
| `/api/v1/status` | GET | Benchmark status |
| `/api/v1/results/{run_id}` | GET | Get results |

## Troubleshooting

### Common Issues

1. **"Service not ready"**
   - Wait for InferenceService to be ready
   - Check `kubectl get isvc -n <namespace>`

2. **"Permission denied"**
   - Verify RBAC permissions
   - Check ServiceAccount configuration

3. **"Out of memory"**
   - Reduce `gpu_memory_utilization`
   - Increase resource limits

4. **"Connection timeout"**
   - Check network connectivity
   - Verify service endpoints

### Debug Commands

```bash
# Check service status
kubectl get isvc -n ml-prod

# View service logs
kubectl logs -n ml-prod -l app=demo-llm

# Check resource usage
kubectl top pods -n ml-prod

# Validate configuration
./scripts/validate_config.py --profile runners/profiles/standard.yaml
```
