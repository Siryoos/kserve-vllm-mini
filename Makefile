# KServe vLLM Mini - Production Makefile
.PHONY: help build test airgap clean install-deps lint typecheck fmt fmt-check

PYTHON ?= python3
PIP ?= pip3

REGISTRY ?= kvmini
TAG ?= latest
AIRGAP_DIR ?= airgap-bundle
ARCH ?= amd64

help: ## Show this help message
	@echo "KServe vLLM Mini - Available targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build the benchmark harness container
	docker build -f Dockerfile.harness -t $(REGISTRY)/kvmini-harness:$(TAG) .

test: ## Run all tests
	$(PYTHON) -m pytest tests/ -v
	./tests/integration_test.sh

lint: ## Run linting (Python + Shell)
	@echo "Ruff (Python)"
	$(PYTHON) -m ruff check .
	@echo "Black (Python)"
	$(PYTHON) -m black --check .
	@echo "ShellCheck (Shell)"
	# Include tracked and untracked shell scripts, but prune virtualenvs and VCS dirs
	files=$$(find . \
	  -path './.git' -prune -o \
	  -path './.venv' -prune -o \
	  -path './venv' -prune -o \
	  -path './env' -prune -o \
	  -name '*.sh' -type f -print | sort -u); \
	if [ -n "$$files" ]; then shellcheck $$files; fi
	@echo "shfmt (Shell)"
	shfmt -i 2 -bn -ci -d $$(git ls-files '*.sh' | grep -v -E '^(.venv|venv|env)/' || true)

fmt: ## Auto-format code (Python + Shell)
	@echo "shfmt (write)"
	files=$$(git ls-files '*.sh' | grep -v -E '^(.venv|venv|env)/' || true); if [ -n "$$files" ]; then shfmt -i 2 -bn -ci -w $$files; fi
	@echo "ruff format"
	$(PYTHON) -m ruff format .
	@echo "black (write)"
	$(PYTHON) -m black .

fmt-check: ## Check formatting only (no write)
	@echo "shfmt (diff)"
	files=$$(git ls-files '*.sh' | grep -v -E '^(.venv|venv|env)/' || true); if [ -n "$$files" ]; then shfmt -i 2 -bn -ci -d $$files; fi
	@echo "ruff format --check"
	$(PYTHON) -m ruff format --check .
	@echo "black --check"
	$(PYTHON) -m black --check .

typecheck: ## Run type checking
	$(PYTHON) -m mypy scripts/ tools/ || true

install-deps: ## Install Python dependencies
	$(PIP) install -r requirements.txt
	@if [ -f requirements-dev.txt ]; then $(PIP) install -r requirements-dev.txt; else echo "(no requirements-dev.txt)"; fi

install-tools: ## Install local developer tools (ruff, black, shellcheck, shfmt)
	@echo "Installing Python tools (ruff, black)"
	$(PIP) install ruff black || true
	@echo "Installing shell tools (shellcheck, shfmt)"
	@if command -v apt-get >/dev/null 2>&1; then \
		sudo apt-get update && sudo apt-get install -y shellcheck shfmt; \
	elif command -v brew >/dev/null 2>&1; then \
		brew install shellcheck shfmt || true; \
	else \
		echo "Please install shellcheck and shfmt via your package manager"; \
	fi

# Air-gapped bundle creation
airgap: airgap-images airgap-artifacts airgap-docs airgap-examples ## Create complete air-gapped bundle

airgap-clean: ## Clean airgap directory
	rm -rf $(AIRGAP_DIR)
	mkdir -p $(AIRGAP_DIR)/{images,charts,docs,examples,wheels,dashboards}

airgap-images: airgap-clean ## Bundle container images
	@echo "📦 Bundling container images for air-gapped deployment..."

	# Pull and save core images
	docker pull registry.k8s.io/kserve/kserve-controller:latest
	docker save -o $(AIRGAP_DIR)/images/kserve-controller.tar registry.k8s.io/kserve/kserve-controller:latest

	docker pull kserve/lgb-server:latest
	docker save -o $(AIRGAP_DIR)/images/lgb-server.tar kserve/lgb-server:latest

	docker pull vllm/vllm-openai:latest
	docker save -o $(AIRGAP_DIR)/images/vllm-openai.tar vllm/vllm-openai:latest

	# Build and save benchmark harness
	$(MAKE) build
	docker save -o $(AIRGAP_DIR)/images/kvmini-harness.tar $(REGISTRY)/kvmini-harness:$(TAG)

	# Monitoring stack
	docker pull prom/prometheus:latest
	docker save -o $(AIRGAP_DIR)/images/prometheus.tar prom/prometheus:latest

	docker pull grafana/grafana:latest
	docker save -o $(AIRGAP_DIR)/images/grafana.tar grafana/grafana:latest

	docker pull nvidia/dcgm-exporter:latest
	docker save -o $(AIRGAP_DIR)/images/dcgm-exporter.tar nvidia/dcgm-exporter:latest

	# Compress all images
	cd $(AIRGAP_DIR)/images && gzip *.tar

	@echo "✅ Container images bundled"

airgap-charts: ## Bundle Helm charts
	@echo "📦 Bundling Helm charts..."

	# Package kvmini chart
	helm package charts/kvmini -d $(AIRGAP_DIR)/charts/

	# Download external charts
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
	helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
	helm repo update

	helm pull prometheus-community/kube-prometheus-stack -d $(AIRGAP_DIR)/charts/
	helm pull grafana/grafana -d $(AIRGAP_DIR)/charts/

	@echo "✅ Helm charts bundled"

airgap-wheels: ## Bundle Python wheels
	@echo "📦 Bundling Python wheels..."

	pip download -r requirements.txt --platform linux_$(ARCH) --only-binary=:all: -d $(AIRGAP_DIR)/wheels/
	pip wheel . --wheel-dir $(AIRGAP_DIR)/wheels/ --no-deps

	@echo "✅ Python wheels bundled"

airgap-artifacts: airgap-charts airgap-wheels ## Bundle software artifacts
	@echo "📦 Bundling artifacts and configuration..."

	# Copy all scripts and tools
	cp -r scripts/ $(AIRGAP_DIR)/
	cp -r tools/ $(AIRGAP_DIR)/
	cp -r policies/ $(AIRGAP_DIR)/
	cp -r profiles/ $(AIRGAP_DIR)/
	cp kvmini $(AIRGAP_DIR)/

	# Copy configuration files
	cp *.yaml $(AIRGAP_DIR)/
	cp cost.yaml $(AIRGAP_DIR)/ 2>/dev/null || echo "cost.yaml not found, skipping"
	cp slo.json $(AIRGAP_DIR)/ 2>/dev/null || echo "slo.json not found, skipping"

	@echo "✅ Artifacts bundled"

airgap-docs: ## Bundle documentation
	@echo "📦 Bundling documentation..."

	cp -r docs/ $(AIRGAP_DIR)/docs/ 2>/dev/null || mkdir -p $(AIRGAP_DIR)/docs
	cp README.md $(AIRGAP_DIR)/
	cp LICENSE $(AIRGAP_DIR)/
	cp NOTICE $(AIRGAP_DIR)/

	# Create air-gap specific installation guide
	cat > $(AIRGAP_DIR)/AIRGAP_INSTALL.md <<- 'EOF'
	# Air-Gapped Installation Guide

	This bundle contains everything needed to run KServe vLLM Mini in an air-gapped environment.

	## Prerequisites
	- Kubernetes cluster ≥1.29 with NVIDIA GPU nodes
	- Helm 3.x
	- Docker or containerd runtime

	## Installation Steps

	### 1. Load Container Images
	```bash
	# Load all container images
	for img in images/*.tar.gz; do
	  gunzip -c "$$img" | docker load
	done

	# If using containerd/nerdctl:
	# for img in images/*.tar.gz; do
	#   gunzip -c "$$img" | nerdctl load
	# done
	```

	### 2. Install Helm Charts
	```bash
	# Install kvmini benchmark harness
	helm install kvmini charts/kvmini-*.tgz \
	  --namespace kvmini-system --create-namespace \
	  --set image.repository=kvmini/kvmini-harness \
	  --set image.tag=latest

	# Optional: Install monitoring stack
	helm install monitoring charts/kube-prometheus-stack-*.tgz \
	  --namespace monitoring --create-namespace
	```

	### 3. Install Python Dependencies (if needed)
	```bash
	pip install --no-index --find-links wheels/ kvmini
	```

	### 4. Verify Installation
	```bash
	kubectl get pods -n kvmini-system
	kvmini --help
	```

	### 5. Run Your First Benchmark
	```bash
	kvmini deploy --namespace demo --service my-llm --model-uri s3://models/llama2-7b/
	kvmini bench --namespace demo --service my-llm --model llama2-7b
	```

	## Bundle Contents
	- `images/` - Container images (compressed)
	- `charts/` - Helm charts
	- `wheels/` - Python packages
	- `scripts/` - Benchmark scripts
	- `tools/` - Utility tools
	- `policies/` - Security policies
	- `docs/` - Documentation
	- `kvmini` - Unified CLI

	## Support
	For issues, see README.md or visit: https://github.com/kserve/kserve-vllm-mini
	EOF

	@echo "✅ Documentation bundled"

airgap-examples: ## Bundle example runs
	@echo "📦 Bundling example runs..."

	mkdir -p $(AIRGAP_DIR)/examples

	# Create example configurations
	cat > $(AIRGAP_DIR)/examples/simple-benchmark.yaml <<- 'EOF'
	apiVersion: v1
	kind: ConfigMap
	metadata:
	  name: benchmark-config
	  namespace: demo
	data:
	  cost.yaml: |
	    gpus:
	      nvidia-tesla-a100-80gb: 3.06
	    cpu_per_hour: 0.04761
	    memory_per_gb_hour: 0.00638
	  slo.json: |
	    {
	      "p95_ms": 2000,
	      "error_rate": 0.01,
	      "$per_1k_tokens": 0.10
	    }
	EOF

	cat > $(AIRGAP_DIR)/examples/run-benchmark.sh <<- 'EOF'
	#!/bin/bash
	set -e

	echo "🚀 Running air-gapped benchmark example"

	# Deploy a simple model
	kvmini deploy \
	  --namespace demo \
	  --service llama2-7b-demo \
	  --model-uri s3://models/llama2-7b/ \
	  --runtime vllm

	# Run benchmark
	kvmini bench \
	  --namespace demo \
	  --service llama2-7b-demo \
	  --model llama2-7b \
	  --requests 100 \
	  --concurrency 10

	echo "✅ Benchmark complete! Check runs/ directory for results."
	EOF
	chmod +x $(AIRGAP_DIR)/examples/run-benchmark.sh

	@echo "✅ Examples bundled"

airgap-dashboards: ## Bundle Grafana dashboards
	@echo "📦 Bundling Grafana dashboards..."

	cp -r dashboards/ $(AIRGAP_DIR)/dashboards/ 2>/dev/null || mkdir -p $(AIRGAP_DIR)/dashboards

	@echo "✅ Dashboards bundled"

airgap-finalize: ## Finalize air-gapped bundle
	@echo "📦 Finalizing air-gapped bundle..."

	# Create manifest of all included files
	find $(AIRGAP_DIR) -type f -exec sha256sum {} \; > $(AIRGAP_DIR)/MANIFEST.sha256

	# Create version info
	cat > $(AIRGAP_DIR)/VERSION <<- EOF
	Bundle Created: $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
	Bundle Version: $(TAG)
	Architecture: $(ARCH)
	Git Commit: $(shell git rev-parse HEAD 2>/dev/null || echo "unknown")
	Generator: make airgap
	EOF

	# Create tarball
	tar -czf kvmini-airgap-$(TAG)-$(ARCH).tar.gz -C . $(AIRGAP_DIR)

	@echo "🎉 Air-gapped bundle created: kvmini-airgap-$(TAG)-$(ARCH).tar.gz"
	@echo "   Bundle size: $(shell du -h kvmini-airgap-$(TAG)-$(ARCH).tar.gz | cut -f1)"
	@echo "   Extract with: tar -xzf kvmini-airgap-$(TAG)-$(ARCH).tar.gz"

# Development targets
dev-setup: install-deps ## Set up development environment
	pip install -e .
	pre-commit install

clean: ## Clean build artifacts
	rm -rf $(AIRGAP_DIR)
	rm -f kvmini-airgap-*.tar.gz
	docker rmi $(REGISTRY)/kvmini-harness:$(TAG) 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete

# Add missing dependency files for complete build
requirements-dev.txt:
	@echo "# Development dependencies" > requirements-dev.txt
	@echo "pytest==7.4.3" >> requirements-dev.txt
	@echo "black==23.11.0" >> requirements-dev.txt
	@echo "ruff==0.1.6" >> requirements-dev.txt
	@echo "mypy==1.7.1" >> requirements-dev.txt
	@echo "pre-commit==3.6.0" >> requirements-dev.txt
validate-configs: ## Validate YAML/JSON configs locally
	@echo "Validating YAML syntax (excluding Helm templates)..."
	@set -e; \
	for file in $$(find . \( -name '*.yaml' -o -name '*.yml' \) -not -path './charts/*/templates/*' -type f | sort); do \
	  echo "  $$file"; \
	  python3 -c "import sys,yaml; p=sys.argv[1]; list(yaml.safe_load_all(open(p,'rb'))); print('    ✓ OK')" "$$file" \
	    || { echo "YAML invalid: $$file" >&2; exit 1; }; \
	done
	@echo "Validating dashboard JSON..."
	@set -e; \
	find dashboards -name '*.json' -type f 2>/dev/null | while read -r f; do \
	  echo "  $$f"; \
	  python3 -m json.tool "$$f" > /dev/null; \
	  echo "    ✓ OK"; \
	done || true
	@echo "All validations complete."
