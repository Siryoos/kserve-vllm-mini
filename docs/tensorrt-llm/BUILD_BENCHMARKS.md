# Build-Time vs Inference Performance

This document explains how to measure TensorRT-LLM engine build time against inference performance to choose optimal flags for your workload.

## What to Compare

- KV cache precision: `fp16` vs `fp8` (H100+)
- Context FMHA: `use_context_fmha=true/false`
- Remove input padding: `true/false`
- Weight-only quantization: `none` vs `awq` vs `gptq`
- Max input length: tighter (e.g., 4k) vs larger (e.g., 32k)

Each dimension impacts build time, engine size, and runtime latency/throughput.

## Tooling

Use `scripts/trtllm_build_vs_perf.py` to automate build+benchmark runs:

```bash
# Baseline fp16 Llama 7B
python3 scripts/trtllm_build_vs_perf.py \
  --profile profiles/tensorrt-llm/llama-7b.yaml \
  --requests 200 --concurrency 10 --max-tokens 64 \
  --builder-cmd "trtllm-build --model /weights/{model_name} --dtype {dtype} {quantization_arg} \
      --use_gpt_attention_plugin={use_gpt_attention_plugin} --use_context_fmha={use_context_fmha} \
      --remove_input_padding={remove_input_padding} --tp_size {tensor_parallel_size} \
      --max_batch_size {max_batch_size} --max_input_len {max_input_len} --max_output_len {max_output_len} \
      --kv_cache_dtype {kv_cache_dtype}"

# Compare with fp8 KV cache (H100/H800)
sed -i 's/KV_CACHE_PRECISION: \"fp16\"/KV_CACHE_PRECISION: \"fp8\"/' profiles/tensorrt-llm/llama-7b.yaml
python3 scripts/trtllm_build_vs_perf.py --profile profiles/tensorrt-llm/llama-7b.yaml
```

The script outputs `trtllm_tradeoffs.csv` with columns:

- model_family, model_name, dtype, quantization, kv_cache_dtype
- max_batch_size, max_input_len, max_output_len, tp_size, pp_size
- build_time_s, p95_total_ms, throughput_req_per_sec, mean_ttfb_ms

## Reading Results

- If `build_time_s` increases substantially with minimal p95/throughput gains, prefer the faster-to-build configuration.
- Large `max_input_len` increases build time and engine size; only increase if your traffic requires it.
- On H100, `fp8` KV cache can reduce p95; validate accuracy for your tasks.
- Weight-only INT4 (AWQ/GPTQ) reduces memory and may improve throughput; check accuracy.

## Tips

- Build engines once per GPU arch and reuse across pods; never rebuild on each pod start.
- Separate build workers from serving nodes to avoid cold starts.
- Keep a small set of shape-specialized engines for your dominant traffic patterns.
