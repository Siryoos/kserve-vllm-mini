# Troubleshooting Guide

This comprehensive guide covers common issues, error messages, and solutions when working with kserve-vllm-mini.

## Quick Diagnosis Commands

```bash
# Check overall system health
kubectl get isvc,pods,svc -n ml-prod
kubectl get nodes -o wide

# Check specific service
kubectl describe isvc/demo-llm -n ml-prod
kubectl logs -f deployment/demo-llm-predictor-default -n ml-prod

# Check benchmarking tools
./bench.sh --dry-run --namespace ml-prod --service demo-llm --requests 10
pre-commit run --all-files
```

## Installation and Setup Issues

### 1. Python Environment Problems

#### Issue: `ModuleNotFoundError` or import errors
```bash
Error: No module named 'httpx'
```

**Solution:**
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Verify installation
python -c "import httpx, yaml, matplotlib; print('Dependencies OK')"
```

#### Issue: Python version incompatibility
```bash
Error: This package requires Python >=3.11
```

**Solution:**
```bash
# Check Python version
python --version

# Install Python 3.11+
# Ubuntu/Debian
sudo apt-get install python3.11 python3.11-venv

# Recreate virtual environment
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Pre-commit Hook Issues

#### Issue: Pre-commit hooks failing
```bash
error: hook declined to install
```

**Solution:**
```bash
# Update pre-commit
pip install --upgrade pre-commit

# Clean and reinstall hooks
pre-commit clean
pre-commit install

# Run to test
pre-commit run --all-files
```

#### Issue: Shellcheck not found
```bash
[INFO] Installing environment for shellcheck-py.
[ERROR] Could not find shellcheck
```

**Solution:**
```bash
# Ubuntu/Debian
sudo apt-get install shellcheck

# macOS
brew install shellcheck

# Manual installation
curl -L https://github.com/koalaman/shellcheck/releases/download/stable/shellcheck-stable.linux.x86_64.tar.xz | tar xJ
sudo mv shellcheck-stable/shellcheck /usr/local/bin/
```

### 3. Docker and Container Issues

#### Issue: Docker permission denied
```bash
permission denied while trying to connect to the Docker daemon
```

**Solution:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Logout and login again, or:
newgrp docker

# Test docker access
docker version
```

## Kubernetes and KServe Issues

### 1. InferenceService Deployment Problems

#### Issue: InferenceService stuck in `NotReady` state
```bash
kubectl get isvc -n ml-prod
NAME       URL   READY   PREV   LATEST   PREVROLLEDOUTREVISION   LATESTREADYREVISION   AGE
demo-llm         False                                                                  5m
```

**Diagnosis:**
```bash
# Check detailed status
kubectl describe isvc/demo-llm -n ml-prod

# Check predictor pods
kubectl get pods -n ml-prod -l serving.kserve.io/inferenceservice=demo-llm

# Check events
kubectl get events -n ml-prod --sort-by='.lastTimestamp'
```

**Common Causes and Solutions:**

1. **Image pull failures:**
   ```bash
   # Check image pull secrets
   kubectl describe pod <pod-name> -n ml-prod | grep -A 5 Events

   # Add image pull secret if needed
   kubectl create secret docker-registry regcred \
     --docker-server=ghcr.io \
     --docker-username=$GITHUB_USERNAME \
     --docker-password=$GITHUB_TOKEN \
     -n ml-prod
   ```

2. **Insufficient resources:**
   ```bash
   # Check node capacity
   kubectl describe nodes | grep -A 5 "Allocated resources"

   # Reduce resource requests
   # Edit your profile or use smaller resource requests
   ```

3. **Missing ServingRuntime:**
   ```bash
   # Check available runtimes
   kubectl get servingruntime -A

   # Install vLLM runtime
   helm install vllm charts/kserve-vllm-mini \
     --set servingRuntime.enabled=true \
     -n ml-prod
   ```

### 2. Pod Crashes and OOM Issues

#### Issue: Pods crashing with Out of Memory (OOM)
```bash
kubectl logs deployment/demo-llm-predictor-default -n ml-prod
OOMKilled
```

**Solutions:**
1. **Increase memory limits:**
   ```yaml
   # In your profile
   resources:
     limits:
       memory: "32Gi"  # Increase from default
   ```

2. **Enable quantization:**
   ```bash
   # Use quantized profile
   ./bench.sh --profile runners/profiles/quantization/autoawq.yaml
   ```

3. **Reduce GPU memory utilization:**
   ```yaml
   vllm_features:
     gpu_memory_utilization: 0.8  # Reduce from 0.9
   ```

#### Issue: GPU not available
```bash
RuntimeError: No GPU available
```

**Solutions:**
```bash
# Check GPU nodes
kubectl get nodes -l accelerator

# Check GPU resources
kubectl describe node <gpu-node> | grep -A 5 "nvidia.com/gpu"

# Verify device plugin
kubectl get daemonset -n kube-system | grep nvidia

# For MIG, check specific resources
kubectl describe node <node> | grep nvidia.com/mig
```

### 3. Network and Connectivity Issues

#### Issue: Connection timeouts during benchmarking
```bash
Connection error: HTTPSConnectionPool(host='demo-llm-ml-prod.example.com', port=443)
```

**Diagnosis:**
```bash
# Check service endpoints
kubectl get endpoints -n ml-prod

# Test internal connectivity
kubectl run debug --image=curlimages/curl -it --rm -- sh
# Inside debug pod:
curl -v http://demo-llm.ml-prod.svc.cluster.local/v1/models
```

**Solutions:**
1. **DNS resolution:**
   ```bash
   # Check CoreDNS
   kubectl get pods -n kube-system -l k8s-app=kube-dns

   # Test DNS from debug pod
   nslookup demo-llm.ml-prod.svc.cluster.local
   ```

2. **Service mesh issues:**
   ```bash
   # If using Istio, check sidecars
   kubectl get pods -n ml-prod -o jsonpath='{.items[*].spec.containers[*].name}'

   # Add sidecar annotation if needed
   kubectl annotate pod <pod> sidecar.istio.io/inject="false"
   ```

## Benchmarking Issues

### 1. Load Test Failures

#### Issue: All requests failing with 4xx/5xx errors
```bash
Error rate: 100%
Status codes: {500: 100}
```

**Diagnosis:**
```bash
# Check service readiness
kubectl get isvc/demo-llm -n ml-prod -o yaml | grep -A 10 status

# Check logs for errors
kubectl logs deployment/demo-llm-predictor-default -n ml-prod --tail=100

# Test single request
curl -X POST http://demo-llm.ml-prod.svc.cluster.local/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "model", "prompt": "Hello", "max_tokens": 10}'
```

**Solutions:**
1. **Model loading issues:**
   ```bash
   # Check if model loaded successfully
   kubectl logs deployment/demo-llm-predictor-default -n ml-prod | grep -i "loaded\|error\|exception"

   # Verify model path
   curl http://demo-llm.ml-prod.svc.cluster.local/v1/models
   ```

2. **Authentication issues:**
   ```bash
   # Check if auth is required
   curl -I http://demo-llm.ml-prod.svc.cluster.local/v1/models

   # Add auth if needed (modify bench.sh)
   ```

#### Issue: Very high latency (TTFT > 10s)
```bash
Average TTFT: 15000ms
```

**Solutions:**
1. **Enable speculative decoding:**
   ```bash
   ./bench.sh --profile runners/profiles/speculative-decoding.yaml
   ```

2. **Optimize batch size:**
   ```yaml
   # In profile
   vllm_features:
     max_num_seqs: 128  # Increase batch size
   ```

3. **Use streaming:**
   ```yaml
   request:
     stream: true
   ```

### 2. Resource Analysis Issues

#### Issue: Cost estimation failing
```bash
Error: Unable to fetch resource metrics
```

**Solutions:**
```bash
# Check metrics server
kubectl get pods -n kube-system -l k8s-app=metrics-server

# Install metrics server if missing
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Verify metrics available
kubectl top nodes
kubectl top pods -n ml-prod
```

#### Issue: GPU utilization showing 0%
```bash
Average GPU utilization: 0%
```

**Solutions:**
```bash
# Check DCGM exporter
kubectl get pods -n kube-system -l app=dcgm-exporter

# Install DCGM if missing
helm repo add gpu-helm-charts https://nvidia.github.io/gpu-monitoring-tools/helm-charts
helm install dcgm-exporter gpu-helm-charts/dcgm-exporter -n kube-system

# Check GPU metrics manually
nvidia-smi
```

## Model and Runtime Issues

### 1. vLLM Specific Issues

#### Issue: vLLM engine failed to start
```bash
ValueError: Model <model-name> is not supported by vLLM
```

**Solutions:**
1. **Check model compatibility:**
   ```bash
   # See vLLM supported models
   python -c "from vllm import LLM; print(LLM.get_model_config('<model-path>'))"
   ```

2. **Use compatible model format:**
   ```bash
   # Convert model if needed
   python -m transformers.convert_checkpoint_to_hf \
     --checkpoint_path <original> \
     --output_dir <converted>
   ```

#### Issue: Quantization not working
```bash
RuntimeError: AWQ quantization is not available
```

**Solutions:**
```bash
# Check GPU compatibility
nvidia-smi | grep "Compute capability"

# Use pre-quantized model
# Download AWQ model from HuggingFace
# Update storageUri to point to quantized model
```

### 2. Storage and Model Loading

#### Issue: S3 access denied
```bash
Error: Access denied when downloading model
```

**Solutions:**
```bash
# Check AWS credentials
aws sts get-caller-identity

# Create service account with IRSA
kubectl create serviceaccount s3-access -n ml-prod
kubectl annotate serviceaccount s3-access -n ml-prod \
  eks.amazonaws.com/role-arn=arn:aws:iam::ACCOUNT:role/S3AccessRole

# Update InferenceService to use service account
```

#### Issue: Model files corrupt or incomplete
```bash
Error: Unable to load tokenizer
```

**Solutions:**
```bash
# Verify model files
aws s3 ls s3://your-bucket/model-path/ --recursive

# Re-download model
aws s3 sync s3://your-bucket/model-path/ ./local-model/

# Check file integrity
python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('./local-model')"
```

## Development and Debugging Issues

### 1. Code Quality Issues

#### Issue: Pre-commit hooks blocking commits
```bash
shellcheck...............................................Failed
- hook id: shellcheck
- exit code: 1
```

**Solutions:**
```bash
# Fix shellcheck issues automatically
./scripts/fix-shellcheck.sh

# Run specific hook to see errors
pre-commit run shellcheck --all-files

# Fix manually or skip (not recommended)
git commit --no-verify -m "emergency fix"
```

#### Issue: Import errors in Python modules
```bash
ModuleNotFoundError: No module named 'local_module'
```

**Solutions:**
```bash
# Add project root to Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Or install in development mode
pip install -e .
```

### 2. Testing Issues

#### Issue: Integration tests failing
```bash
Error: kubectl not found
```

**Solutions:**
```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# Set up kubeconfig
export KUBECONFIG=$HOME/.kube/config

# Test connection
kubectl cluster-info
```

#### Issue: Unit tests failing
```bash
ImportError: No module named 'pytest'
```

**Solutions:**
```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run tests with verbose output
python -m pytest tests/ -v -s

# Run specific test
python -m pytest tests/test_analyze.py::test_percentile -v
```

## Performance Optimization

### 1. Slow Benchmarking

#### Issue: Benchmarks taking too long
```bash
Benchmark running for 30+ minutes
```

**Solutions:**
1. **Reduce test parameters:**
   ```bash
   # Use smaller test
   ./bench.sh --requests 50 --concurrency 5
   ```

2. **Use faster profile:**
   ```bash
   # Use CPU smoke test for dev
   ./bench.sh --profile runners/profiles/cpu-smoke.yaml
   ```

3. **Enable parallel processing:**
   ```bash
   # Increase concurrency
   ./bench.sh --concurrency 20
   ```

### 2. Resource Constraints

#### Issue: Node resources exhausted
```bash
Warning  FailedScheduling  2m    default-scheduler  0/3 nodes are available: insufficient nvidia.com/gpu
```

**Solutions:**
```bash
# Check available resources
kubectl describe nodes | grep -A 5 "Allocated resources"

# Use resource-efficient profiles
./bench.sh --profile runners/profiles/quantization/autoawq.yaml

# Scale down other workloads
kubectl scale deployment <other-deployment> --replicas=0 -n <namespace>
```

## Error Reference

### Common Exit Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 1 | General error | Check logs for specific error message |
| 2 | Configuration error | Validate profile and parameters |
| 3 | Network/connection error | Check connectivity and DNS |
| 4 | Resource error | Check available resources |
| 5 | Validation error | Fix validation failures |
| 126 | Permission denied | Check file permissions and RBAC |
| 127 | Command not found | Install missing dependencies |

### HTTP Status Codes

| Code | Meaning | Common Cause |
|------|---------|--------------|
| 400 | Bad Request | Invalid JSON or parameters |
| 401 | Unauthorized | Missing authentication |
| 403 | Forbidden | RBAC or permission issues |
| 404 | Not Found | Service not ready or wrong URL |
| 500 | Internal Server Error | Model loading or runtime error |
| 503 | Service Unavailable | Service not ready or overloaded |
| 504 | Gateway Timeout | Request timeout or slow model |

## Getting Help

### Diagnostic Information to Collect

When asking for help, include:

```bash
# System information
kubectl version
docker version
python --version

# Cluster state
kubectl get nodes -o wide
kubectl get isvc,pods,svc -n ml-prod
kubectl describe isvc/<your-service> -n ml-prod

# Recent logs
kubectl logs deployment/<your-deployment> -n ml-prod --tail=50

# Pre-commit status
pre-commit run --all-files

# Resource usage
kubectl top nodes
kubectl top pods -n ml-prod
```

### Support Channels

- 🐛 [GitHub Issues](https://github.com/siryoos/kserve-vllm-mini/issues) - Bug reports and feature requests
- 💬 [GitHub Discussions](https://github.com/siryoos/kserve-vllm-mini/discussions) - General questions and help
- 📚 [Documentation](../README.md) - Complete project documentation

### Creating Good Bug Reports

Include:
1. **Environment details** (OS, Python version, Kubernetes version)
2. **Steps to reproduce** (exact commands run)
3. **Expected vs actual behavior**
4. **Full error messages and logs**
5. **Configuration files** (sanitized)
6. **Screenshots** (if applicable)

## Advanced Debugging

### Debug Mode

```bash
# Enable debug mode
export KVMINI_DEBUG=true
export LOG_LEVEL=DEBUG

# Run with debug output
./bench.sh --namespace ml-prod --service demo-llm --requests 10 2>&1 | tee debug.log
```

### Remote Debugging

```bash
# Access running pod
kubectl exec -it deployment/demo-llm-predictor-default -n ml-prod -- /bin/bash

# Run debug commands inside pod
ps aux
netstat -tlnp
cat /proc/meminfo
nvidia-smi
```

### Performance Profiling

```bash
# Profile Python code
python -m cProfile -o profile.stats analyze.py --run-dir results/

# Analyze profile
python -c "import pstats; p=pstats.Stats('profile.stats'); p.sort_stats('cumtime').print_stats(20)"

# Memory profiling
pip install memory-profiler
python -m memory_profiler analyze.py --run-dir results/
```

This troubleshooting guide should help you resolve most common issues. For complex problems, don't hesitate to create a GitHub issue with detailed information.
