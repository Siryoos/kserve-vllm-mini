---
sidebar_position: 1
---

# Introduction

Welcome to **kserve-vllm-mini** - the professional-grade KServe + vLLM benchmarking toolkit that produces objective metrics you can trust.

## What is kserve-vllm-mini?

kserve-vllm-mini is a comprehensive benchmarking suite designed to help you:

- 🎯 **Deploy and benchmark** KServe + vLLM deployments in one command
- 📊 **Measure performance** with p95 latency, TTFT, throughput, and cost analysis
- ⚡ **Test advanced features** like speculative decoding, quantization, and structured outputs
- 🔍 **Compare backends** (vLLM vs TGI vs TensorRT-LLM) with automated analysis
- 🛡️ **Prevent crashes** with configuration validation and guardrails

## Quick Start

Get started with a simple benchmark in under 5 minutes:

```bash
# Clone the repository
git clone https://github.com/yourusername/kserve-vllm-mini
cd kserve-vllm-mini

# Install dependencies
pip install -r requirements.txt

# Run your first benchmark
./bench.sh --model s3://models/llama-7b/ --requests 200
```

This will:
1. Deploy a vLLM service on KServe
2. Run 200 benchmark requests
3. Analyze performance and cost metrics
4. Generate a comprehensive report

## Key Features

### 🎯 One-Command Workflow
Deploy → Load Test → Analyze → Report in a single command with professional output.

### ⚡ Advanced vLLM Support
Ready-to-use profiles for:
- **Speculative Decoding**: 20-40% TTFT improvement
- **Quantization**: AWQ, GPTQ, FP8, INT8 with memory analysis
- **Structured Outputs**: JSON schema validation
- **Tool Calling**: Function invocation testing

### 🔍 Backend Comparison
Automated comparison between vLLM, TGI, and TensorRT-LLM with:
- Side-by-side performance metrics
- HTML reports with winner analysis
- CSV exports for further analysis

### 🛡️ Production Guardrails
- Configuration validation preventing KServe crashes
- Hardware compatibility checks (FP8 → H100 requirement)
- Resource allocation sanity checks

### 📊 Comprehensive Metrics
Every benchmark provides:
- **Latency**: p50, p95, p99, TTFT
- **Throughput**: RPS, tokens/sec
- **Resource Usage**: GPU utilization, memory consumption
- **Cost Analysis**: Per request and per 1K tokens
- **Energy**: Power consumption via DCGM integration

## Why Choose kserve-vllm-mini?

| Challenge | Our Solution |
|-----------|--------------|
| **"What's my real p95 under load?"** | Prometheus integration with cold/warm split analysis |
| **"How much does this cost per 1K tokens?"** | Resource-based cost estimation with detailed breakdowns |
| **"Which runtime is faster?"** | Automated A/B/C comparison with objective metrics |
| **"Does speculative decoding help my model?"** | Ready-to-run profiles measuring actual TTFT impact |
| **"Will this crash in production?"** | Validation guardrails preventing known KServe issues |

## Next Steps

Ready to dive deeper? Check out:

- [**Installation Guide**](getting-started/installation) - Complete setup instructions
- [**Quick Start**](getting-started/quickstart) - Your first benchmark in 5 minutes
- [**Feature Overview**](features/overview) - Detailed feature documentation
- [**Profile Gallery**](profiles/overview) - Browse available benchmark profiles

## Community

Join our growing community:

- 💬 [GitHub Discussions](https://github.com/yourusername/kserve-vllm-mini/discussions) - Q&A and community showcases
- 🐛 [Issues](https://github.com/yourusername/kserve-vllm-mini/issues) - Bug reports and feature requests
- 📈 [Public Roadmap](https://github.com/yourusername/kserve-vllm-mini/projects/1) - See what's coming next
- 🤝 [Contributing](contributing/overview) - Help make the project better

---

Ready to start benchmarking? Let's [get you set up](getting-started/installation)! 🚀
