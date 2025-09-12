# vLLM Model Repository Example

This document provides an example of how to structure a model in an S3 bucket for use with the vLLM KServe runtime.

## Recommended Example Model

For a quick start, we recommend using a small, open-source model like `TinyLlama/TinyLlama-1.1B-Chat-v1.0`.

- **Model:** TinyLlama/TinyLlama-1.1B-Chat-v1.0
- **Hugging Face:** [https://huggingface.co/TinyLlama/TinyLlama-1.1B-Chat-v1.0](https://huggingface.co/TinyLlama/TinyLlama-1.1B-Chat-v1.0)

## S3 Bucket Structure

vLLM requires the model files to be in a directory in your S3 bucket. The structure is simpler than Triton's. You can use the Hugging Face CLI or the `huggingface_hub` library to download the model files and then upload them to your S3 bucket.

Example structure for TinyLlama in a bucket named `my-models`:

```
s3://my-models/tiny-llama/
├── config.json
├── generation_config.json
├── model.safetensors
├── special_tokens_map.json
├── tokenizer.json
├── tokenizer.model
└── tokenizer_config.json
```

## Usage

Once the model is in your S3 bucket, you can deploy it using the `deploy.sh` script or the `kvmini deploy` CLI command. The `model-uri` should point to the directory containing the model files.

Example:

```bash
./deploy.sh --namespace ml-prod --service tinyllama-demo --model-uri s3://my-models/tiny-llama/
```
