# Bill of Materials (BOM)

This document tracks component versions, image digests, and dependency pinning for reproducible benchmarks.

## Version: 1.0.0
**Last Updated**: 2025-01-10
**Git SHA**: `$(git rev-parse HEAD 2>/dev/null || echo 'unknown')`

---

## 🚀 Core Components

### KServe Runtime
- **Version**: `v0.12.1` (as of 2025-01-10)
- **Image**: `kserve/vllmserver:v0.12.1` (pin to digest in production)
- **API Version**: `serving.kserve.io/v1beta1`
- **Notes**: Using vLLM runtime for LLM inference

### Knative Serving
- **Version**: `v1.12.x`
- **Components**:
  - Controller: `gcr.io/knative-releases/knative.dev/serving/cmd/controller@sha256:...`
  - Activator: `gcr.io/knative-releases/knative.dev/serving/cmd/activator@sha256:...`
- **Notes**: Required for autoscaling and traffic management

### Istio Service Mesh
- **Version**: `1.20.x`
- **Components**:
  - Pilot: `docker.io/istio/pilot:1.20.1@sha256:...`
  - Proxy: `docker.io/istio/proxyv2:1.20.1@sha256:...`
- **Notes**: Provides ingress and metrics collection

---

## 🐳 Container Images

### Load Test Generator
- **Base**: `python:3.11-slim@sha256:...` (pin in production)
- **Dependencies**: httpx, asyncio (see requirements.txt)

### Analysis Tools
- **Base**: `python:3.11-slim@sha256:...`
- **Dependencies**: pandas, matplotlib, pyyaml (see requirements.txt)

---

## 📊 Dashboard Versions

### KServe/Knative Golden Signals
- **File**: `dashboards/knative-kserve-golden.json`
- **UID**: `kserve-golden-001`
- **Version**: 1.0
- **Grafana**: Compatible with v9.x, v10.x

### Cold Start Impact Analysis
- **File**: `dashboards/cold-start-impact.json`
- **UID**: `cold-start-001`
- **Version**: 1.0
- **Grafana**: Compatible with v9.x, v10.x

### Utilization & Latency
- **File**: `dashboards/kserve-llm-utilization.json`
- **UID**: Auto-generated (varies)
- **Version**: 1.0
- **Grafana**: Compatible with v9.x, v10.x

---

## 🔧 System Dependencies

### Required Binaries
- **kubectl**: `v1.29+` (client version)
- **jq**: `1.6+` (JSON processing)
- **yq**: `4.x` (YAML processing)
- **helm**: `3.x` (optional, for Helm deployments)

### Python Dependencies
```txt
httpx>=0.25.0
pandas>=2.0.0
matplotlib>=3.7.0
PyYAML>=6.0
```

### Optional Dependencies
```txt
pytest>=7.0.0         # For testing
cosign>=2.0.0         # For image signing
syft>=0.90.0          # For SBOM generation
```

---

## 🏗️ Infrastructure Requirements

### Kubernetes Cluster
- **Version**: `1.29+`
- **GPU Support**: NVIDIA Device Plugin required
- **Node Requirements**:
  - GPU nodes: NVIDIA drivers + CUDA runtime
  - CPU nodes: 4+ cores recommended for load generation

### Monitoring Stack
- **Prometheus**: `v2.45+` with DCGM exporter
- **Grafana**: `v9.5+` or `v10.x`
- **DCGM Exporter**: `3.1.8+` for GPU metrics

### Storage
- **S3 Compatible**: MinIO or cloud object storage
- **Volume**: 100GB+ recommended for model weights

---

## 🔄 Change Log

### v1.0.0 (2025-01-10)
- **Added**: Traffic pattern support (Poisson, bursty, heavy-tail)
- **Added**: Cold vs warm cost accounting
- **Added**: DCGM power consumption tracking
- **Added**: Artifact bundling with provenance
- **Added**: Grid sweep automation
- **Added**: HTML report generation
- **Updated**: Dashboard UIDs for consistency
- **Breaking**: CSV format includes `scheduled_ms`, `tllt_ms` fields

---

## 🚨 Breaking Changes

### From v0.x to v1.0
1. **CSV Format**: Added new columns (`scheduled_ms`, `tllt_ms`, `is_cold_start`)
2. **Cost Schema**: New cold/warm cost fields in `results.json`
3. **Dashboard UIDs**: All dashboards assigned stable UIDs
4. **Bundle Format**: New artifact bundling with provenance tracking

---

## 🔒 Security Notes

### Image Pinning Strategy
- **Production**: Always use `@sha256:...` digests
- **Development**: Pin to semantic versions (`:v1.2.3`)
- **Never**: Use `:latest` or untagged images

### Secret Management
- **API Keys**: Use Kubernetes secrets, never hardcode
- **Certificates**: External cert management (cert-manager)
- **Service Mesh**: mTLS enabled by default

---

## ✅ Validation

### Reproducibility Criteria
- **P95 Variance**: ≤ ±10% across identical runs
- **Cost Calculation**: Deterministic to 6 decimal places
- **Bundle Integrity**: SHA256 checksums match
- **Dashboard Import**: No UID conflicts

### Compatibility Matrix
| Component     | v1.29 K8s | v1.30 K8s | v1.31 K8s |
|---------------|-----------|-----------|-----------|
| KServe v0.12  | ✅        | ✅        | ✅        |
| Knative v1.12 | ✅        | ✅        | ⚠️        |
| Istio v1.20   | ✅        | ✅        | ✅        |

**Legend**: ✅ Tested | ⚠️ Should work | ❌ Incompatible

---

## 📞 Support

**Maintainer**: kserve-vllm-mini team
**Issues**: GitHub Issues
**Dependencies**: Automated Dependabot updates enabled
**Security**: Private security advisories for CVEs
