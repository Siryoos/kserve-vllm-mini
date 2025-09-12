# TensorRT-LLM Engine Profiles

Profiles in this directory capture recommended build/runtime settings for common model families when targeting TensorRT-LLM via Triton/KServe.

## Files

- `llama-7b.yaml` – Llama 7B baseline (fp16)
- `mistral-7b.yaml` – Mistral 7B baseline (fp16, longer context)
- `codellama-7b.yaml` – CodeLlama 7B baseline
- `phi-2.7b.yaml` – Phi 2.7B baseline (higher batch)

## Usage

Use together with the build-vs-performance harness to compare tradeoffs:

```bash
python3 scripts/trtllm_build_vs_perf.py \
  --profile profiles/tensorrt-llm/llama-7b.yaml \
  --requests 200 --concurrency 10 --max-tokens 64 \
  --builder-cmd "trtllm-build --model /weights/{model_name} --dtype {dtype} {quantization_arg} \
      --use_gpt_attention_plugin={use_gpt_attention_plugin} --use_context_fmha={use_context_fmha} \
      --remove_input_padding={remove_input_padding} --tp_size {tensor_parallel_size} \
      --max_batch_size {max_batch_size} --max_input_len {max_input_len} --max_output_len {max_output_len} \
      --kv_cache_dtype {kv_cache_dtype}"
```

Adjust shapes and flags to match your hardware and workload. Rebuild engines whenever you change shapes or TP/PP sizes.
