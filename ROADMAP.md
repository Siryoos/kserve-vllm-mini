# kserve-vllm-mini Public Roadmap

This roadmap outlines the planned development priorities for kserve-vllm-mini based on community feedback and KServe ecosystem needs.

## Current Status (v0.2.0)

### ✅ Completed Features
- **Core Benchmarking**: Deploy → Load Test → Analyze → Cost workflow
- **vLLM Advanced Features**: Speculative decoding, quantization (AWQ/GPTQ/FP8/INT8), structured outputs, tool calling
- **Backend Comparison**: Automated vLLM vs TGI vs TensorRT-LLM harness
- **Configuration Validation**: Guards against known KServe+vLLM crashes
- **Energy Monitoring**: DCGM integration for power consumption tracking
- **Professional Output**: JSON reports, HTML comparison dashboards, CSV exports
- **Enhanced CI/CD**: Automated linting, testing, and quality gates
- **Comprehensive Documentation**: Complete API reference, troubleshooting guides, and developer setup

### 🛠️ Recently Completed (v0.2.0)
- **Profile Integration**: ✅ Loading vLLM features from YAML profiles
- **Documentation Site**: ✅ Docusaurus deployment
- **CI/CD Pipeline**: ✅ Automated testing and profile validation
- **Enhanced Documentation**: ✅ Comprehensive API docs, troubleshooting, and developer guides

## Short Term (Q4 2025)

### 🎯 Priority 1: Profile System Enhancement
**Goal**: Make vLLM feature toggles seamless and discoverable

- [ ] **Profile Loader**: Parse `vllm_features` from YAML and inject into deployment
- [ ] **Profile Validation**: Extend `validate_config.py` to check feature compatibility
- [ ] **Profile Templates**: Generate profiles from CLI flags (`--enable-speculative`, `--quantization=awq`)
- [ ] **Profile Discovery**: `./list-profiles.sh` with descriptions and use cases

**Success Metrics**: Users can enable any vLLM feature with one YAML file

### 🎯 Priority 2: Deployment Integration
**Goal**: Support real-world KServe deployment scenarios

- [ ] **External Control Plane**: Allow benchmarking existing InferenceServices
- [ ] **Helm Charts**: Package deployment templates for various scenarios
- [ ] **ArgoCD Integration**: GitOps workflows for benchmark automation
- [ ] **Multi-Cluster**: Cross-cluster performance comparison

**Success Metrics**: Works with existing KServe installations without changes

### 🎯 Priority 3: Enhanced Validation
**Goal**: Prevent more classes of production issues

- [ ] **Resource Validation**: Check GPU memory requirements vs available capacity
- [ ] **Model Compatibility**: Validate quantization method matches model format
- [ ] **Runtime Feature Matrix**: Check feature support per KServe runtime version
- [ ] **Dependency Checks**: Verify DCGM, Prometheus, storage access

**Success Metrics**: 90% reduction in benchmark failures due to misconfiguration

## Medium Term (Q1-Q2 2026)

### 🚀 Advanced vLLM Features
**Goal**: Support cutting-edge vLLM capabilities

- [ ] **LoRA Adapters**: Benchmark adapter switching performance and memory impact
- [ ] **Multimodal Support**: Vision-language model benchmarking (LLaVA, CLIP)
- [ ] **Custom Attention**: Flash Attention variants, sliding window attention
- [ ] **Prefix Caching Advanced**: Benchmark cache hit rates and memory savings
- [ ] **Multi-LoRA**: Performance with multiple concurrent adapters

### 🔍 Analysis & Insights
**Goal**: Deeper performance understanding

- [ ] **Regression Detection**: Automated alerting when metrics degrade
- [ ] **Bottleneck Analysis**: Identify compute vs memory vs network limits
- [ ] **Scaling Laws**: Model size vs performance relationship analysis
- [ ] **Cost Optimization**: Recommend optimal instance types and quantization
- [ ] **SLO Monitoring**: Track SLA compliance over time

### 🌐 Ecosystem Integration
**Goal**: Integrate with broader MLOps toolchain

- [ ] **MLflow Integration**: Log metrics as MLflow experiments
- [ ] **Weights & Biases**: Experiment tracking and visualization
- [ ] **Kubernetes Events**: Rich event logging for debugging
- [ ] **OpenTelemetry**: Distributed tracing for request lifecycle
- [ ] **Slack/Teams Notifications**: Benchmark completion alerts

## Long Term (Q3+ 2026)

### 🤖 Intelligence & Automation
**Goal**: Self-optimizing benchmarking

- [ ] **Auto-Tuning**: Automatically find optimal vLLM parameters for your model
- [ ] **Smart Scheduling**: Schedule benchmarks during low-cost periods
- [ ] **Anomaly Detection**: ML-based detection of performance regressions
- [ ] **Recommendation Engine**: Suggest profiles based on model characteristics
- [ ] **Predictive Scaling**: Model future resource needs based on trends

### 🏢 Enterprise Features
**Goal**: Support large-scale production deployments

- [ ] **Multi-Tenant**: Isolated benchmarking for different teams/models
- [ ] **RBAC Integration**: Kubernetes RBAC-aware access control
- [ ] **Audit Logging**: Compliance-friendly benchmark audit trails
- [ ] **Cost Allocation**: Per-team/model cost breakdown and chargeback
- [ ] **SLA Reporting**: Automated SLA compliance reports

### 🌍 Ecosystem Expansion
**Goal**: Support beyond KServe+vLLM

- [ ] **Ray Serve**: Benchmark Ray Serve deployments
- [x] **Triton**: NVIDIA Triton Inference Server support (TensorRT-LLM wired into comparator; tokens/sec accounted)
- [ ] **Azure ML**: Azure Machine Learning integration
- [ ] **AWS SageMaker**: SageMaker endpoint benchmarking
- [ ] **GCP Vertex AI**: Vertex AI model benchmarking

## Community Priorities

### 🟢 Good First Issues
Perfect for new contributors:

- [x] **Add quantization profile**: Create INT4 quantization profile
- [x] **Documentation**: Write tutorial for MIG deployment
- [x] **Profile validation**: Add checks for memory requirements
- [x] **CLI enhancement**: Add `--dry-run` flag to bench.sh
- [x] **Error handling**: Improve error messages in validation script

### 🟡 Help Wanted
Seeking community expertise:

- [ ] **TensorRT-LLM profiles**: Optimize TensorRT-LLM specific configurations
- [ ] **Model zoo**: Create profiles for popular model families
- [ ] **Cloud provider guides**: AWS/GCP/Azure specific deployment guides
- [ ] **Performance baselines**: Collect reference results for common hardware
- [ ] **Localization**: i18n support for error messages and docs

### 🔴 Major Contributions
High-impact features for experienced contributors:

- [ ] **GUI Dashboard**: Web interface for benchmark management
- [ ] **Database Integration**: Store historical results in PostgreSQL/ClickHouse
- [ ] **Advanced Analytics**: Statistical analysis of performance trends
- [ ] **Load Testing Suite**: More sophisticated traffic patterns
- [ ] **Security Scanning**: Automated vulnerability scanning for container images

## Feedback & Prioritization

We prioritize features based on:

1. **Community demand** (GitHub issues, discussions)
2. **KServe ecosystem gaps** (missing functionality)
3. **Production adoption blockers** (what prevents real usage?)
4. **Maintenance burden** (sustainable development)

### How to Influence the Roadmap

- 🗳️ **Vote on issues**: +1 issues you care about
- 💬 **Join discussions**: Share your use cases
- 📝 **Write RFCs**: Propose major features
- 🤝 **Contribute**: PRs move items up the priority list
- 📊 **Share results**: Public benchmark results help prioritize optimizations

### Success Metrics

We track roadmap success through:

- **GitHub Stars**: Community interest indicator
- **Issues/PRs**: Contribution velocity
- **Documentation traffic**: Feature discovery and adoption
- **Benchmark accuracy**: Comparison to production metrics
- **Time to insight**: Deploy → Results → Decision cycle time

## Getting Involved

- 📋 **Project Board**: https://github.com/users/siryoos/projects/1
- 💬 **GitHub Discussions**: https://github.com/siryoos/kserve-vllm-mini/discussions
- 🐛 **Issues**: https://github.com/siryoos/kserve-vllm-mini/issues
- 🐦 **X (Twitter)**: @myoosefiha

---

*This roadmap is a living document. Priorities may shift based on community needs and ecosystem changes.*

**Last Updated**: 2025-09-12
**Next Review**: 2025-10-01
