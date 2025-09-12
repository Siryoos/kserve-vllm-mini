# vLLM Feature Support Matrix

This document outlines which vLLM features are supported in kserve-vllm-mini benchmarking profiles and how they impact performance metrics.

## Core Features

| Feature | Status | Profiles | Performance Impact | Notes |
|---------|--------|----------|-------------------|-------|
| **Basic Inference** | ✅ Full | `standard`, `burst`, `sustained` | Baseline | Standard text generation |
| **Streaming** | ✅ Full | All profiles | Improved TTFT | Real-time token streaming |
| **Batching** | ✅ Full | All profiles | Higher throughput | Continuous batching enabled |
| **Prefix Caching** | ✅ Full | All profiles | Reduced latency for repeated prompts | Automatic in vLLM |

## Advanced Features

### Speculative Decoding
| Aspect | Support | Profile | Impact |
|--------|---------|---------|--------|
| **Draft Models** | ✅ Configurable | `speculative-decoding` | 20-40% TTFT reduction |
| **Multi-candidate** | ✅ Tunable | `speculative-decoding` | Higher accuracy vs speed tradeoff |
| **Auto Selection** | ⚠️ Limited | `speculative-decoding` | Requires compatible model pairs |

**Example Usage:**
```bash
./bench.sh --profile runners/profiles/speculative-decoding.yaml \
  --model s3://models/llama-3.1-8b/ --requests 200
```

### Structured Outputs
| Aspect | Support | Profile | Impact |
|--------|---------|---------|--------|
| **JSON Schema** | ✅ Full | `structured-output` | 10-30% latency increase |
| **Pydantic Models** | ✅ Full | `structured-output` | Type-safe generation |
| **Tool Calling** | ✅ Full | `tool-calling` | Function invocation support |

**Example Usage:**
```bash
./bench.sh --profile runners/profiles/structured-output.yaml \
  --model s3://models/mistral-7b-instruct/ --requests 150
```

### Quantization Methods

| Method | Status | Profile | Memory Reduction | Performance Impact | GPU Requirements |
|--------|--------|---------|------------------|-------------------|------------------|
| **AutoAWQ** | ✅ Full | `quantization/autoawq` | 75% | 10-20% faster | Any CUDA GPU |
| **GPTQ** | ✅ Full | `quantization/gptq` | 75% | Baseline | Any CUDA GPU |
| **FP8** | ✅ Full | `quantization/fp8` | 50% | 20-30% faster | H100/H800+ |
| **INT8** | ✅ Full | `quantization/int8` | 50% | 10-15% slower | Any CUDA GPU |
| **INT4** | ✅ Via AWQ/GPTQ | See above | 75% | Model-dependent | Any CUDA GPU |

**Quantization Comparison:**
```bash
# Compare all quantization methods
./scripts/compare_backends.py --model s3://models/llama-7b/ \
  --profile runners/profiles/quantization/autoawq.yaml
```

## Deployment Modes

### GPU Deployment
| Feature | Support | Requirements | Performance |
|---------|---------|-------------|-------------|
| **Single GPU** | ✅ Full | 1x GPU | Standard benchmarking |
| **Multi-GPU** | ✅ Full | 2+ GPUs | Higher throughput |
| **MIG Support** | ✅ Full | A100/H100 MIG | Resource sharing |

### CPU Deployment
| Feature | Support | Profile | Limitations |
|---------|---------|---------|-------------|
| **Basic Inference** | ⚠️ Limited | `cpu-smoke` | 10-50x slower |
| **Quantization** | ❌ None | N/A | GPU-only feature |
| **Speculative Decoding** | ❌ None | N/A | GPU-only feature |

**CPU Smoke Test:**
```bash
./bench.sh --profile runners/profiles/cpu-smoke.yaml \
  --model s3://models/small-model/ --requests 50
```

## Attention Mechanisms

| Method | Status | Use Case | Memory Impact |
|--------|--------|----------|---------------|
| **Flash Attention 2** | ✅ Auto | Long sequences | Lower memory |
| **Paged Attention** | ✅ Default | Variable lengths | Efficient KV cache |
| **Sliding Window** | ✅ Model-dependent | Ultra-long context | Constant memory |

## Backend Comparison Support

The comparison harness supports benchmarking across multiple KServe runtimes:

| Runtime | Status | Profiles | Notes |
|---------|--------|----------|-------|
| **vLLM** | ✅ Full | All | Primary runtime |
| **TGI** | ✅ Full | Standard profiles | Hugging Face runtime |
| **TensorRT-LLM** | ✅ Full | Standard profiles | NVIDIA optimized |

**Run Comparison:**
```bash
./scripts/compare_backends.py --model s3://models/llama-7b/ \
  --backends vllm tgi tensorrt --profile runners/profiles/standard.yaml
```

See also:
- TensorRT-LLM deployment patterns: tensorrt-llm/DEPLOYMENT.md
- Build vs performance tradeoffs: tensorrt-llm/BUILD_BENCHMARKS.md
- Model-specific recommendations: models/OPTIMIZATIONS.md

## Feature Toggles in Profiles

### Profile Structure
```yaml
# Example profile with vLLM features
vllm_features:
  speculative_model: "facebook/opt-125m"
  quantization: "awq"
  guided_decoding_backend: "outlines"
  enable_auto_tool_choice: true
  gpu_memory_utilization: 0.90
```

### Common Combinations
- **High Throughput**: No quantization, batching optimized
- **Memory Constrained**: AWQ/GPTQ quantization
- **Low Latency**: Speculative decoding + FP8 (H100)
- **Structured**: Tool calling + guided decoding
- **Development**: CPU smoke test

## Performance Impact Summary

| Feature Category | TTFT Impact | Throughput Impact | Memory Impact | Cost Impact |
|------------------|-------------|-------------------|---------------|-------------|
| **Quantization** | Neutral | +10-30% | -50-75% | -40-60% |
| **Speculative Decoding** | -20-40% | Neutral | +10-20% | -15-25% |
| **Structured Output** | +10-30% | -5-15% | Neutral | +5-20% |
| **Tool Calling** | +15-25% | -10-20% | Neutral | +10-25% |

## Validation and Guardrails

The configuration validator (`scripts/validate_config.py`) checks for:

- ✅ Multi-step scheduling + max_tokens requirement
- ✅ Quantization method compatibility
- ✅ GPU architecture requirements (FP8)
- ✅ Resource allocation sanity checks

**Validation Example:**
```bash
./scripts/validate_config.py --profile runners/profiles/speculative-decoding.yaml
./bench.sh --dry-run --namespace ml-prod --service demo-llm --requests 200 --concurrency 10 --max-tokens 64
./bench.sh --list-profiles
```

## Recommended Profiles by Use Case

| Use Case | Recommended Profile | Expected Results |
|----------|-------------------|------------------|
| **Production Baseline** | `standard.yaml` | Balanced performance metrics |
| **Cost Optimization** | `quantization/autoawq.yaml` | 60% cost reduction |
| **Latency Critical** | `speculative-decoding.yaml` | 30% TTFT improvement |
| **API Integration** | `structured-output.yaml` | 100% format compliance |
| **Resource Planning** | `burst.yaml` | Autoscaling behavior |
| **Backend Selection** | Compare all via `compare_backends.py` | Objective runtime comparison |

## Future Roadmap

Features planned for future releases:

- 🔄 LoRA adapter benchmarking
- 🔄 Multimodal input support
- 🔄 Custom attention mechanisms
- 🔄 Advanced prompt caching strategies
- 🔄 Cross-cloud deployment profiles

## Troubleshooting

Common issues and solutions:

| Issue | Cause | Solution |
|-------|-------|----------|
| Crashes with multi-step | Missing max_tokens | Use validation, add max_tokens |
| FP8 not available | Wrong GPU architecture | Use H100/H800 or switch to AWQ |
| CPU deployment slow | Expected behavior | Use GPU profiles for realistic testing |
| Quantization fails | Model not pre-quantized | Use compatible quantized model |

For detailed troubleshooting, see individual profile documentation.
