# Azure (AKS) Deployment Guide for TensorRT-LLM

Deploy Triton TensorRT-LLM with KServe on AKS using NVIDIA GPU nodes.

## Prerequisites

- AKS cluster with GPU VM SKUs (e.g., Standard_ND96asr_v4 A100, ND_H100_v5 H100, NCasT4_v3 T4)
- Azure Blob Storage container for the Triton model repository
- Azure AD Workload Identity for secure access

## Steps

1) Create AKS + GPU node pool

```bash
az aks create --name trtllm --resource-group rg-trtllm --node-count 1 \
  --node-vm-size Standard_ND40rs_v2 --kubernetes-version 1.29
```

2) Install NFD, NVIDIA device plugin, and KServe

Follow official docs; ensure a Triton ServingRuntime exists in the cluster.

3) Prepare model repo in Azure Blob

```
https://<storage-account>.blob.core.windows.net/<container>/models/triton/<model>/
└── [ensemble, tokenizer, tensorrt_llm_bls]
```

4) Deploy InferenceService

```bash
runners/backends/triton/deploy.sh --model llama-7b --namespace ml-prod --streaming false
```

5) Benchmark

```bash
URL=$(kubectl get isvc llama-7b-triton -n ml-prod -o jsonpath='{.status.url}')
runners/backends/triton/invoke.sh --url "$URL" --requests 200 --concurrency 10 --max-tokens 64 --run-dir runs/azure-test
```

## Tips

- ND H100 v5 is recommended for FP8 KV cache trials
- Use ephemeral OS disks and premium SSDs for fast local caching if needed
