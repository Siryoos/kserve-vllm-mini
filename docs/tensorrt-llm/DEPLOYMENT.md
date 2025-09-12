# TensorRT-LLM Deployment Patterns (KServe + Triton)

This guide documents practical patterns for deploying TensorRT-LLM with KServe using the Triton backend, including engine management and performance tips.

## Overview

- Build TensorRT-LLM engines offline for your exact GPU arch (SM) and shapes
- Store engines in a model repository (S3/GS/Azure Blob) in Triton layout
- Point a KServe InferenceService at the repo using the Triton runtime
- Scale replicas/pods; reuse the same engines across pods to avoid rebuilds

## Model Repository Layout (example)

```
models/
├── tensorrt_llm_bls/
│   └── 1/
│       ├── model.plan                # TensorRT engines (per submodule)
│       └── config.pbtxt
├── tokenizer/
│   └── 1/
│       ├── tokenizer.json
│       └── config.pbtxt
└── ensemble/
    └── 1/
        └── config.pbtxt              # Wires tokenizer + engines
```

Place this under an object store path, e.g. `s3://models/triton/llama-7b/`.

### Quick skeleton (copy/paste)

```
models/
  tensorrt_llm_bls/
    1/
      model.plan           # your TRT engine (or subgraphs if split)
      config.pbtxt
  tokenizer/
    1/
      tokenizer.json
      config.pbtxt
  ensemble/
    1/
      config.pbtxt         # routes inputs -> tokenizer -> TRT LLM -> output
```

Minimal `ensemble/config.pbtxt` example:

```
name: "ensemble"
platform: "ensemble"
max_batch_size: 64
input [
  { name: "text_input" data_type: TYPE_BYTES dims: [1] }
]
output [
  { name: "text_output" data_type: TYPE_BYTES dims: [1] }
]
ensemble_scheduling {
  step [
    { model_name: "tensorrt_llm_bls" input_map { key: "text_input" value: "text_input" } output_map { key: "text_output" value: "text_output" } }
  ]
}
```

See a working skeleton under `examples/triton-model-repo/` which aligns with the harness request/response schema used by `runners/backends/triton/invoke.sh` (including `max_tokens` and `output_lengths`).

## KServe InferenceService (Triton)

Use the provided adapter to deploy a Triton-based service:

```bash
# Deploy with pre-built engines
runners/backends/triton/deploy.sh \
  --model llama-7b \
  --namespace ml-prod \
  --streaming false
```

The script sets sensible env defaults:
- `MODEL_REPOSITORY`: `s3://models/triton/<model>`
- `TENSOR_PARALLEL_SIZE`, `PIPELINE_PARALLEL_SIZE`
- `MAX_BATCH_SIZE`, `MAX_INPUT_LEN`, `MAX_OUTPUT_LEN`, `MAX_BEAM_WIDTH`

Adjust these in your profile and rebuild engines if shapes change.

## Patterns

- Single GPU, low latency
  - `tp=1, pp=1`, `max_batch_size ≤ 32`, long-IO disabled
  - Prefer `dtype=bf16` (H100) or `fp16` (A100/A10/L4)

- Multi-GPU throughput (TP)
  - `tp=2/4`, one pod per node recommended to minimize NCCL hops
  - Ensure engines are built with matching `tp_size`

- MIG
  - Build engines for the MIG slice’s memory budget
  - Use `profiles/mig/*` for KServe resource shapes

- Engine shape strategy
  - Keep `max_input_len` tight to your real traffic; large max lengths increase build time and engine size
  - Use `beam_width=1` unless doing beam search

- KV cache precision
  - `fp8` KV cache can reduce latency on H100/H800 (set `KV_CACHE_PRECISION=fp8`)
  - Validate accuracy for your workloads

## Build and Benchmark Tradeoffs

Use the included script to measure engine build time vs inference performance:

```bash
python3 scripts/trtllm_build_vs_perf.py \
  --profile profiles/tensorrt-llm/llama-7b.yaml \
  --builder-cmd "trtllm-build --model /weights/{model_name} \
      --dtype {dtype} {quantization_arg} \
      --use_gpt_attention_plugin={use_gpt_attention_plugin} \
      --use_context_fmha={use_context_fmha} \
      --remove_input_padding={remove_input_padding} \
      --max_batch_size {max_batch_size} --max_input_len {max_input_len} \
      --max_output_len {max_output_len} --max_beam_width {max_beam_width} \
      --tp_size {tensor_parallel_size} --kv_cache_dtype {kv_cache_dtype}"
```

The script will deploy a Triton service and run a load test using `runners/backends/triton/invoke.sh`, then emit a CSV row with build time vs p95/throughput.

## Troubleshooting

- Engines rebuild on pod start
  - Ensure the model repo contains compiled engines for your GPU arch and shapes
  - Verify Triton has access to the repo and correct permissions

- Latency spikes after changing shapes
  - Rebuild engines when `max_input_len`/`max_output_len`/`batch_size` changes

- NCCL errors with TP
  - Align TP size between build and runtime, verify network and NCCL settings

- Accuracy regressions
  - Re-test with `KV_CACHE_PRECISION=fp16` and without quantization

## References

- TensorRT-LLM docs and builder flags vary by version; prefer your installed version’s documentation when in doubt.
