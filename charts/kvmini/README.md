# kvmini Helm Chart

The kvmini chart provides a benchmark harness for KServe vLLM deployments. It can be used standalone or as a subchart in the main `kserve-vllm-mini` chart.

## Overview

This chart deploys:
- **Deployment**: Benchmark harness pod with tools and scripts
- **ServiceAccount**: With RBAC permissions for Kubernetes API access
- **ConfigMap**: Benchmark configuration and scripts
- **PersistentVolumeClaim**: Storage for benchmark results and artifacts
- **Service**: Internal service for metrics and monitoring

## Features

- 🏃 **Benchmark Execution**: Run performance tests against KServe services
- 📊 **Results Storage**: Persistent storage for benchmark data and reports
- 🔧 **Configurable**: Customizable benchmark parameters and profiles
- 📈 **Monitoring**: Metrics collection and Prometheus integration
- 🛡️ **RBAC**: Proper permissions for Kubernetes resource access

## Installation

### Standalone Installation

```bash
# Basic installation
helm install kvmini-harness charts/kvmini \
  --namespace benchmark --create-namespace

# Custom configuration
helm install kvmini-harness charts/kvmini \
  --namespace benchmark --create-namespace \
  --set persistence.size=50Gi \
  --set image.tag=latest \
  --set resources.requests.cpu=2000m
```

### As Subchart

When used as a subchart in `kserve-vllm-mini`:

```bash
helm install vllm charts/kserve-vllm-mini \
  --set kvmini.enabled=true \
  --set kvmini.persistence.size=20Gi \
  --namespace ml-prod
```

## Configuration

### Core Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `enabled` | Enable the kvmini subchart | `false` |
| `nameOverride` | Override chart name | `""` |
| `fullnameOverride` | Override full name | `""` |

### Image Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.repository` | Container image repository | `kvmini/kvmini-harness` |
| `image.tag` | Container image tag | `"latest"` |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `imagePullSecrets` | Image pull secrets | `[]` |

### Resources

| Parameter | Description | Default |
|-----------|-------------|---------|
| `resources.requests.cpu` | CPU request | `1000m` |
| `resources.requests.memory` | Memory request | `2Gi` |
| `resources.limits.cpu` | CPU limit | `2000m` |
| `resources.limits.memory` | Memory limit | `4Gi` |

### Persistence

| Parameter | Description | Default |
|-----------|-------------|---------|
| `persistence.enabled` | Enable persistent storage | `true` |
| `persistence.size` | Storage size | `10Gi` |
| `persistence.storageClass` | Storage class | `""` |
| `persistence.accessMode` | Access mode | `ReadWriteOnce` |

### Service Account

| Parameter | Description | Default |
|-----------|-------------|---------|
| `serviceAccount.create` | Create service account | `true` |
| `serviceAccount.name` | Service account name | `""` |
| `serviceAccount.annotations` | Service account annotations | `{}` |

### RBAC

| Parameter | Description | Default |
|-----------|-------------|---------|
| `rbac.create` | Create RBAC resources | `true` |
| `rbac.rules` | Additional RBAC rules | `[]` |

### Service

| Parameter | Description | Default |
|-----------|-------------|---------|
| `service.type` | Service type | `ClusterIP` |
| `service.port` | Service port | `8080` |
| `service.annotations` | Service annotations | `{}` |

### Benchmark Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `benchmark.defaultProfile` | Default benchmark profile | `standard` |
| `benchmark.outputDir` | Results output directory | `/data/results` |
| `benchmark.timeout` | Benchmark timeout | `3600s` |
| `benchmark.retries` | Number of retries | `3` |

### Global Configuration (when used as subchart)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.isvc.name` | Target InferenceService name | `""` |
| `global.isvc.namespace` | Target InferenceService namespace | `""` |
| `global.model.storageUri` | Model storage URI | `""` |

## Usage Examples

### Basic Benchmark Execution

```bash
# Get pod name
HARNESS_POD=$(kubectl get pods -n benchmark -l app.kubernetes.io/name=kvmini -o jsonpath='{.items[0].metadata.name}')

# Run benchmark
kubectl exec -n benchmark $HARNESS_POD -- \
  ./bench.sh --namespace ml-prod --service demo-llm \
  --requests 100 --concurrency 10

# View results
kubectl exec -n benchmark $HARNESS_POD -- \
  ls -la /data/results/
```

### Custom Profile

```bash
# Upload custom profile
kubectl create configmap custom-profile \
  --from-file=custom.yaml=my-profile.yaml \
  -n benchmark

# Mount and use custom profile
helm upgrade kvmini-harness charts/kvmini \
  --set extraVolumes[0].name=custom-profile \
  --set extraVolumes[0].configMap.name=custom-profile \
  --set extraVolumeMounts[0].name=custom-profile \
  --set extraVolumeMounts[0].mountPath=/profiles/custom
```

### Monitoring Integration

```bash
# Enable service monitor for Prometheus
helm upgrade kvmini-harness charts/kvmini \
  --set monitoring.enabled=true \
  --set monitoring.serviceMonitor.enabled=true
```

## Environment Variables

The harness pod includes these environment variables:

| Variable | Description | Source |
|----------|-------------|--------|
| `KVMINI_NAMESPACE` | Target namespace | `global.isvc.namespace` |
| `KVMINI_SERVICE` | Target service | `global.isvc.name` |
| `KVMINI_MODEL_URI` | Model URI | `global.model.storageUri` |
| `KVMINI_OUTPUT_DIR` | Output directory | `benchmark.outputDir` |
| `KUBECONFIG` | Kubernetes config | `/var/run/secrets/kubernetes.io/serviceaccount` |

## RBAC Permissions

The service account has these permissions:

```yaml
# Core resources for benchmark execution
- apiGroups: [""]
  resources: ["pods", "services", "configmaps"]
  verbs: ["get", "list", "watch"]

# KServe resources
- apiGroups: ["serving.kserve.io"]
  resources: ["inferenceservices"]
  verbs: ["get", "list", "watch"]

# Metrics and monitoring
- apiGroups: ["metrics.k8s.io"]
  resources: ["pods", "nodes"]
  verbs: ["get", "list"]

# Custom resources (optional)
- apiGroups: ["custom.metrics.k8s.io"]
  resources: ["*"]
  verbs: ["get", "list"]
```

## Persistent Volume Structure

```
/data/
├── results/           # Benchmark results
│   ├── 2025-09-12_14-30-15/
│   ├── 2025-09-12_15-45-22/
│   └── latest -> 2025-09-12_15-45-22/
├── profiles/          # Custom profiles
│   ├── custom.yaml
│   └── experimental.yaml
├── scripts/           # Custom scripts
└── logs/              # Application logs
```

## Troubleshooting

### Common Issues

1. **Permission Denied**
   ```bash
   # Check RBAC
   kubectl auth can-i get pods --as=system:serviceaccount:benchmark:kvmini-harness

   # Fix RBAC
   helm upgrade kvmini-harness charts/kvmini --set rbac.create=true
   ```

2. **Storage Issues**
   ```bash
   # Check PVC status
   kubectl get pvc -n benchmark

   # Check available storage classes
   kubectl get storageclass

   # Use specific storage class
   helm upgrade kvmini-harness charts/kvmini --set persistence.storageClass=fast-ssd
   ```

3. **Network Connectivity**
   ```bash
   # Test service connectivity
   kubectl exec -n benchmark $HARNESS_POD -- \
     curl -s http://demo-llm.ml-prod.svc.cluster.local/v1/models

   # Check DNS resolution
   kubectl exec -n benchmark $HARNESS_POD -- \
     nslookup demo-llm.ml-prod.svc.cluster.local
   ```

### Debug Commands

```bash
# View harness logs
kubectl logs -n benchmark -l app.kubernetes.io/name=kvmini -f

# Execute shell in harness
kubectl exec -n benchmark $HARNESS_POD -it -- /bin/bash

# Check resource usage
kubectl top pod -n benchmark $HARNESS_POD

# Describe pod for events
kubectl describe pod -n benchmark $HARNESS_POD
```

### Performance Tuning

```bash
# Increase resources for large benchmarks
helm upgrade kvmini-harness charts/kvmini \
  --set resources.requests.cpu=2000m \
  --set resources.requests.memory=4Gi \
  --set resources.limits.cpu=4000m \
  --set resources.limits.memory=8Gi

# Use faster storage
helm upgrade kvmini-harness charts/kvmini \
  --set persistence.storageClass=fast-ssd \
  --set persistence.size=100Gi

# Enable resource monitoring
helm upgrade kvmini-harness charts/kvmini \
  --set monitoring.enabled=true \
  --set monitoring.resources.enabled=true
```

## Integration

### With CI/CD

```yaml
# GitHub Actions example
- name: Run Benchmark
  run: |
    helm install kvmini-test charts/kvmini \
      --namespace benchmark --create-namespace \
      --wait

    HARNESS_POD=$(kubectl get pods -n benchmark -o jsonpath='{.items[0].metadata.name}')
    kubectl exec -n benchmark $HARNESS_POD -- \
      ./bench.sh --namespace ml-prod --service ${{ github.sha }} \
      --requests 200 --concurrency 20
```

### With Prometheus

```yaml
# values.yaml
monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 30s
    scrapeTimeout: 10s
```

### With Grafana

Import the provided dashboard from `dashboards/kvmini-harness.json`.

## Uninstall

```bash
# Standalone
helm uninstall kvmini-harness -n benchmark

# As subchart
helm upgrade vllm charts/kserve-vllm-mini --set kvmini.enabled=false
```
