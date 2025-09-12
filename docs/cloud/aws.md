# AWS (EKS) Deployment Guide for TensorRT-LLM

This guide outlines a pragmatic setup for running Triton TensorRT-LLM with KServe on EKS.

## Prerequisites

- EKS cluster with GPU nodes (e.g., p4d/p4de A100, p5 H100, g5 A10G, g6/g6e L4)
- IAM roles for service accounts (IRSA) to access your model repository (S3)
- Node Feature Discovery and NVIDIA device plugin installed
- KServe v0.14+ and a Triton ServingRuntime available

## Steps

1) Create GPU nodegroup

```bash
eksctl create cluster --name trtllm --region us-west-2 \
  --nodegroup-name gpu --nodes 2 --nodes-min 1 --nodes-max 5 \
  --node-type p4d.24xlarge --version 1.29
```

2) Install NFD and NVIDIA device plugin

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/node-feature-discovery/master/deployment/overlays/default/nfd-master.yaml
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/stable/nvidia-device-plugin.yml
```

3) Install KServe and Triton runtime

Follow KServe installation for your cluster, then ensure a Triton ServingRuntime (e.g., `kserve-tritonserver`) is present.

4) Prepare model repository in S3

```
s3://models/triton/<model>/
├── ensemble/1/config.pbtxt
├── tokenizer/1/...
└── tensorrt_llm_bls/1/model.plan + config.pbtxt
```

5) Deploy InferenceService

```bash
runners/backends/triton/deploy.sh --model llama-7b --namespace ml-prod --streaming false
```

6) Benchmark

```bash
URL=$(kubectl get isvc llama-7b-triton -n ml-prod -o jsonpath='{.status.url}')
runners/backends/triton/invoke.sh --url "$URL" --requests 200 --concurrency 10 --max-tokens 64 --run-dir runs/aws-test
```

## Tips

- Prefer p5 (H100) for FP8 KV cache experiments
- Use IRSA and fine-grained S3 policies for model repo access
- Consider EFA-enabled instance types for high TP sizes across nodes
