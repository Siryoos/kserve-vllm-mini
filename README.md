# kserve-vllm-mini

<p align="center">
  <img src="https://i.imgur.com/sOU2X2a.png" alt="kserve-vllm-mini logo" width="200"/>
</p>

<p align="center">
  <strong>Professional-grade KServe + vLLM benchmarking toolkit</strong>
</p>

<p align="center">
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0">
  </a>
  <a href="https://kserve.github.io/website/">
    <img src="https://img.shields.io/badge/KServe-Compatible-green.svg" alt="KServe Compatible">
  </a>
  <a href="https://github.com/vllm-project/vllm">
    <img src="https://img.shields.io/badge/vLLM-Integrated-orange.svg" alt="vLLM Integration">
  </a>
  <a href="docs/ENERGY_METHOD.md">
    <img src="https://img.shields.io/badge/DCGM-Energy%20Tracking-purple.svg" alt="DCGM Energy">
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

# Results in runs/2024-09-11_14-30-15/results.json:
{
  "p95_latency_ms": 342.1,
  "avg_ttft_ms": 23.4,
  "throughput_rps": 47.2,
  "cost_per_1k_tokens": "$0.0023",
  "energy_per_1k_tokens_wh": 15.7
}
```

## vLLM Feature Matrix

| Feature                  | Status | Profile                     | Performance Impact        | Notes                           |
| ------------------------ | :----: | --------------------------- | ------------------------- | ------------------------------- |
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

## Available Profiles

| Profile                       | Use Case              | Expected Impact           |
| ----------------------------- | --------------------- | ------------------------- |
| `standard.yaml`               | Baseline comparison   | Balanced metrics          |
| `burst.yaml`                  | Autoscaling behavior  | Cold start analysis       |
| `speculative_decoding.yaml`   | Latency optimization  | 30% TTFT improvement      |
| `quantization/autoawq.yaml`   | Memory optimization   | 60% cost reduction        |
| `structured_output.yaml`      | API integration       | 100% format compliance    |
| `tool-calling.yaml`           | Agent applications    | Function invocation       |
| `cpu-smoke.yaml`              | Development testing   | Compatibility check       |

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
4.  Create a new branch for your changes.
5.  Make your changes and commit them to your branch.
6.  Push your changes to your fork on GitHub.
7.  Open a pull request to the main repository.

### Code of Conduct

We are committed to providing a friendly, safe and welcoming environment for all, regardless of gender, sexual orientation, disability, ethnicity, or religion. Please read our [Code of Conduct](CODE_OF_CONDUCT.md) to learn more.

## Community & Support

- 📚 [Documentation](docs/)
- 💬 [Discussions](https://github.com/siryoos/kserve-vllm-mini/discussions)
- 🐛 [Issues](https://github.com/siryoos/kserve-vllm-mini/issues)
- 📈 [Public Roadmap](ROADMAP.md)

## License

This project is licensed under the Apache-2.0 License. See the [LICENSE](LICENSE) file for details.
