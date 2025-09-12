# Triton Model Repository (Sample Skeleton)

This is a minimal example layout for deploying a TensorRT-LLM model with Triton via KServe.

Copy this directory to your object store (e.g., `s3://models/triton/llama-7b/`) and replace placeholders.

Structure:
- `ensemble/1/config.pbtxt`: Routes inputs to the TensorRT-LLM backend
- `tensorrt_llm_bls/1/config.pbtxt`: Backend configuration for the LLM
- `tensorrt_llm_bls/1/README.md`: Instructions for adding your engine(s)

Note: This is an illustrative skeleton. Adjust shapes, names, and flags to your model.
