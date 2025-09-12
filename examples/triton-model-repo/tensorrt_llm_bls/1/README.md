# tensorrt_llm_bls model (placeholder)

- Copy your TensorRT-LLM engine files into this directory.
- Update `config.pbtxt` to match your TRT-LLM version and inputs/outputs.
- Ensure the ensemble maps `text_input`, `max_tokens`, `bad_words`, `stop_words` and exposes `text_output` and `output_lengths`.

This layout matches the harness payloads in:
- `runners/backends/triton/invoke.sh`
