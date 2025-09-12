# kserve-vllm-mini

<p align="center">
  <img src="https://i.imgur.com/sOU2X2a.png" alt="kserve-vllm-mini logo" width="200"/>
</p>

<p align="center">
  <strong>Professional-grade KServe + vLLM benchmarking toolkit</strong>
</p>

<p align="center">
  <a href="https://github.com/Siryoos/kserve-vllm-mini/actions/workflows/lint-test.yml">
    <img src="https://github.com/Siryoos/kserve-vllm-mini/actions/workflows/lint-test.yml/badge.svg" alt="CI">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-Apache--2.0-blue.svg" alt="License: Apache-2.0">
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python">
  </a>
  <a href=".pre-commit-config.yaml">
    <img src="https://img.shields.io/badge/pre--commit-enabled-brightgreen" alt="pre-commit">
  </a>
</p>

**kserve-vllm-mini** is a powerful and easy-to-use toolkit for benchmarking KServe and vLLM deployments. It provides objective metrics like p95 latency, cost per 1K tokens, and energy consumption, with a detailed analysis of cold and warm start performance.

## Key Features

- 🎯 **One-Command Benchmarking:** Deploy, benchmark, and generate reports with a single command.
- 📊 **Comprehensive Metrics:** Track TTFT, p95 latency, RPS, tokens/sec, GPU utilization, and cost estimation.
- ⚡ **Advanced vLLM Features:** Support for speculative decoding, quantization, structured outputs, and tool calling.
- 🔍 **Backend Comparison:** A/B test vLLM against other backends like TGI and TensorRT-LLM.
- 🛡️ **Production-Ready:** Includes security policies, MIG support, and validation guardrails.

## Getting Started

### Prerequisites

- Kubernetes ≥ 1.29 with NVIDIA GPU nodes
- KServe installed with vLLM runtime
- DCGM for energy monitoring (optional)
- S3-compatible storage (MinIO, AWS S3)

### Installation

```bash
git clone https://github.com/siryoos/kserve-vllm-mini
cd kserve-vllm-mini

# Install Python dependencies
pip install -r requirements.txt

# Install development dependencies (optional)
pip install -r requirements-dev.txt

# Install pre-commit hooks (recommended for development)
pre-commit install
```

### Quick Demo

```bash
# Deploy and benchmark in one command
./bench.sh --namespace ml-prod --service demo-llm \
  --model-uri s3://models/llama-3.1-8b/ --requests 500 --concurrency 20

# Results in runs/2025-09-12_14-30-15/results.json:
{
  "p95_latency_ms": 342.1,
  "avg_ttft_ms": 23.4,
  "throughput_rps": 47.2,
  "cost_per_1k_tokens": "$0.0023",
  "energy_per_1k_tokens_wh": 15.7
}
```

### First run in kind/minikube

For a quick local demo without affecting a shared cluster:

```bash
# 1. Create a local cluster
kind create cluster --name kvmini

# 2. Create a namespace
kubectl create ns ml-prod

# 3. Deploy a sample model
#    (replace with your model URI)
./deploy.sh --namespace ml-prod --service demo-llm --model-uri s3://<your-bucket-name>/<your-model-path>/

# 4. Run a quick load test
./load-test.sh --namespace ml-prod --service demo-llm --requests 100 --concurrency 10

# 5. Generate a report
python report_generator.py runs/latest/results.json
```

## Known Good Stack

This stack is tested and known to be compatible. See the full [Bill of Materials](docs/BOM.md) for details.

| Component     | Version   | Notes                               |
|---------------|-----------|-------------------------------------|
| Kubernetes    | `1.29+`   |                                     |
| KServe        | `v0.14.0` | vLLM is bundled in the runtime.     |
| vLLM          | `0.4.0`   | Via KServe runtime `v0.14.0`        |
| GPU SKU       | A100, L4  | MIG supported on A100.              |
| Helm          | `3.12+`   |                                     |

## vLLM Feature Matrix

| Feature                  | Status | Profile                     | Performance Impact        | Notes                           |
|------------------------ | :----: | --------------------------- | ------------------------- | ------------------------------- |
| **Speculative Decoding** |   ✅   | `speculative-decoding`      | 20-40% TTFT improvement   | Draft model acceleration        |
| **AutoAWQ Quantization** |   ✅   | `quantization/autoawq`      | 75% memory reduction      | 4-bit weights, faster inference |
| **GPTQ Quantization**    |   ✅   | `quantization/gptq`         | 75% memory reduction      | 4-bit weights, broad compatibility |
| **FP8 Quantization**     |   ✅   | `quantization/fp8`          | 50% memory reduction      | H100/H800 optimized             |
| **Structured Outputs**   |   ✅   | `structured-output`         | 100% format compliance    | JSON schema validation          |
| **Tool Calling**         |   ✅   | `tool-calling`              | Function invocation       | OpenAI-compatible APIs          |
| **CPU Deployment**       |   ⚠️   | `cpu-smoke`                 | Limited functionality     | Development/testing only        |

[**Full Feature Documentation →**](docs/FEATURES.md)

## Why Choose This Over Raw vLLM?

| Challenge                                   | kserve-vllm-mini Solution                               |
| ------------------------------------------- | ------------------------------------------------------- |
| **"What's my real p95 under load?"**        | Prometheus integration with cold/warm split analysis    |
| **"How much does this cost per 1K tokens?"** | Resource-based cost estimation with GPU/CPU/memory breakdown |
| **"Which runtime is faster: vLLM vs TGI?"** | Automated A/B/C comparison harness with HTML reports    |
| **"Does speculative decoding help my model?"**| Ready-to-run profiles measuring TTFT impact             |
| **"Will this crash in production?"**        | Validation guardrails preventing known KServe+vLLM issues |

## Profiles at a Glance

The following performance and cost profiles are available. They can be used with the `planner.py` and `deploy.sh` scripts via the `--profile <name>` flag.

| Profile                                                     | Description                                  |
|-----------------------------------------------------------|--------------------------------------------|
| [`mig/a100-1g.5gb`](profiles/mig/a100-1g.5gb.yaml)           | NVIDIA A100 1g.5gb MIG profile.              |
| [`mig/a100-2g.10gb`](profiles/mig/a100-2g.10gb.yaml)          | NVIDIA A100 2g.10gb MIG profile.             |
| [`tensorrt-llm/codellama-7b`](profiles/tensorrt-llm/codellama-7b.yaml) | CodeLlama-7B with TensorRT-LLM.    |
| [`tensorrt-llm/llama-7b`](profiles/tensorrt-llm/llama-7b.yaml)         | Llama-7B with TensorRT-LLM.        |
| [`tensorrt-llm/mistral-7b`](profiles/tensorrt-llm/mistral-7b.yaml)     | Mistral-7B with TensorRT-LLM.      |
| [`tensorrt-llm/phi-2.7b`](profiles/tensorrt-llm/phi-2.7b.yaml)         | Phi-2.7B with TensorRT-LLM.        |

## Development Setup

### Prerequisites for Development

- Python 3.11+
- Docker (for container builds)
- Helm 3.12+ (for chart development)
- kubectl (for Kubernetes interaction)
- pre-commit (for code quality)

### Code Quality Tools

This project uses automated code quality tools:

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Set up pre-commit hooks
pre-commit install

# Manual code quality checks
make lint          # Run all linters
make helm-lint     # Lint Helm charts
make test          # Run tests

# Run pre-commit on all files
pre-commit run --all-files
```

**Supported Linters:**
- **Python**: ruff (linting + formatting), black (formatting)
- **Shell Scripts**: shellcheck (linting), shfmt (formatting)
- **YAML**: yamllint, actionlint (GitHub Actions)
- **Helm Charts**: helm lint

### Build Commands

```bash
# Build container
make build

# Create air-gapped bundle
make airgap

# Package Helm charts
make helm-package
```

## Contributing

We welcome contributions from the community! Whether you're a seasoned developer or just getting started, there are many ways to help us improve kserve-vllm-mini.

### Why Contribute?

-   **Make an impact:** Your contributions will help other users make better decisions about their LLM deployments.
-   **Gain experience:** You'll get to work with cutting-edge technologies like Kubernetes, KServe, and vLLM.
-   **Join a community:** You'll be part of a friendly and supportive community of developers.

### How to Contribute

-   **Report bugs:** If you find a bug, please open an issue on GitHub.
-   **Suggest features:** If you have an idea for a new feature, please open an issue to discuss it.
-   **Write code:** If you're a developer, you can help us by writing code to fix bugs or add new features.
-   **Improve documentation:** If you're a good writer, you can help us improve our documentation.
-   **Spread the word:** If you like kserve-vllm-mini, please share it with your friends and colleagues.

### Getting Started

1.  Fork the repository on GitHub.
2.  Clone your fork to your local machine.
3.  Install the development dependencies: `pip install -r requirements-dev.txt`
4.  **Set up the pre-commit hooks:** This is crucial for ensuring your contributions pass the linter checks.
    ```bash
    pre-commit install
    ```
5.  Create a new branch for your changes.
6.  Make your changes and commit them to your branch. The hooks will run automatically.
7.  Push your changes to your fork on GitHub.
8.  Open a pull request to the main repository.

### Code of Conduct

We are committed to providing a friendly, safe and welcoming environment for all, regardless of gender, sexual orientation, disability, ethnicity, or religion. Please read our [Code of Conduct](CODE_OF_CONDUCT.md) to learn more.

## Community & Support

- 📚 [Documentation](docs/)
- 💬 [Discussions](https://github.com/siryoos/kserve-vllm-mini/discussions)
- 🐛 [Issues](https://github.com/siryoos/kserve-vllm-mini/issues)
- 📈 [Public Roadmap](ROADMAP.md)

## License

This project is licensed under the Apache-2.0 License. See the [LICENSE](LICENSE) file for details.
