# Backend A/B Testing Framework

This directory contains runtime adapters for fair backend comparisons.

## Overview

The A/B harness enables apples-to-apples comparisons between different LLM serving backends:
- **vLLM** (default): High-throughput batched inference
- **Triton TensorRT-LLM**: NVIDIA optimized runtime
- **TGI** (Text Generation Inference): HuggingFace runtime

## Usage

```bash
# Compare vLLM vs TGI with identical load profile
./ab-compare.sh --backends vllm,tgi --model llama2-7b --profile standard

# Test streaming vs non-streaming across backends
./ab-compare.sh --backends vllm,triton --toggle-streaming --requests 500
```

## Structure

```
runners/
├── README.md              # This file
├── ab-compare.sh          # Main comparison orchestrator
├── backends/
│   ├── vllm/
│   │   ├── deploy.sh      # Deploy vLLM InferenceService
│   │   └── invoke.sh      # Generate requests for vLLM
│   ├── triton/
│   │   ├── deploy.sh      # Deploy Triton TensorRT-LLM
│   │   └── invoke.sh      # Generate requests for Triton
│   └── tgi/
│       ├── deploy.sh      # Deploy TGI runtime
│       └── invoke.sh      # Generate requests for TGI
└── profiles/
    ├── standard.yaml      # Balanced load profile
    ├── burst.yaml         # Bursty traffic pattern
    └── sustained.yaml     # High sustained throughput
```

## Requirements

- Kubernetes cluster with GPU nodes
- KServe v0.12+ installed
- Sufficient GPU resources for multiple deployments
- Backend-specific model formats (see backend READMEs)

## Output

Each comparison produces:
- Unified CSV with backend, streaming mode, and latency metrics
- Side-by-side performance report (HTML)
- Resource utilization comparison
- Cost breakdown per backend
- Recommendation matrix
