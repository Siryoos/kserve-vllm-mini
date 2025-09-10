#!/bin/bash

# Example usage of the A/B comparison harness
# This demonstrates how to compare vLLM vs TGI with streaming toggle

set -euo pipefail

echo "=== Backend A/B Harness Example ==="
echo ""

echo "🎯 Example 1: Basic vLLM vs TGI comparison"
echo "Command: ./ab-compare.sh --backends vllm,tgi --model demo-llm --profile standard"
echo ""

echo "🎯 Example 2: Streaming impact analysis"  
echo "Command: ./ab-compare.sh --backends vllm --model demo-llm --toggle-streaming --profile burst"
echo ""

echo "🎯 Example 3: High-throughput comparison"
echo "Command: ./ab-compare.sh --backends vllm,triton,tgi --model llama2-7b --profile sustained --requests 1000"
echo ""

echo "💡 Available backends:"
echo "  - vllm:   High-throughput batched inference (default)"
echo "  - tgi:    HuggingFace Text Generation Inference"
echo "  - triton: NVIDIA Triton TensorRT-LLM (requires pre-built engines)"
echo ""

echo "💡 Available profiles:"
echo "  - standard: Balanced load (200 req, 10 concurrency)"
echo "  - burst:    Bursty traffic (300 req, 25 concurrency)"  
echo "  - sustained: High throughput (500 req, 50 concurrency)"
echo ""

echo "📊 Output structure:"
echo "  runs/ab_compare_TIMESTAMP/"
echo "  ├── ab_comparison.csv          # Unified results across backends"
echo "  ├── comparison_report.json     # Detailed analysis and winners"
echo "  ├── vllm_streaming_false/      # Individual test results"
echo "  ├── vllm_streaming_true/"
echo "  ├── tgi_streaming_false/"
echo "  └── ..."
echo ""

echo "🏆 The harness automatically identifies:"
echo "  - Fastest TTFT backend"
echo "  - Highest throughput backend"
echo "  - Most cost-effective backend"
echo "  - Streaming vs non-streaming trade-offs"
echo ""

echo "To run a real test, execute one of the example commands above."
echo "Ensure your KServe cluster has sufficient GPU resources for multiple deployments."