# Developer Setup Guide

This guide will help you set up a complete development environment for kserve-vllm-mini, including code quality tools, testing, and contribution workflows.

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+), macOS (10.15+), or Windows (WSL2)
- **Python**: 3.11 or higher
- **Memory**: 8GB RAM minimum, 16GB recommended
- **Storage**: 20GB free space

### Required Software

#### 1. Git
```bash
# Ubuntu/Debian
sudo apt-get install git

# macOS (with Homebrew)
brew install git

# Verify installation
git --version
```

#### 2. Python 3.11+
```bash
# Ubuntu/Debian
sudo apt-get install python3.11 python3.11-venv python3.11-dev

# macOS (with Homebrew)
brew install python@3.11

# Verify installation
python3.11 --version
```

#### 3. Docker
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# macOS
brew install docker

# Verify installation
docker --version
```

#### 4. Helm
```bash
# Install Helm 3.12+
curl https://get.helm.sh/helm-v3.12.3-linux-amd64.tar.gz | tar xz
sudo mv linux-amd64/helm /usr/local/bin/

# Verify installation
helm version
```

#### 5. kubectl
```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# Verify installation
kubectl version --client
```

## Project Setup

### 1. Clone Repository
```bash
git clone https://github.com/siryoos/kserve-vllm-mini
cd kserve-vllm-mini
```

### 2. Python Environment Setup

#### Create Virtual Environment
```bash
# Create virtual environment
python3.11 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Verify Python version
python --version
```

#### Install Dependencies
```bash
# Install runtime dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Verify installation
pip list | grep -E "(ruff|black|pytest|pre-commit)"
```

### 3. Pre-commit Setup

Pre-commit hooks ensure code quality and consistency:

```bash
# Install pre-commit hooks
pre-commit install

# Run pre-commit on all files (first time)
pre-commit run --all-files

# Verify installation
pre-commit --version
```

**Pre-commit Hooks Configured:**
- **shellcheck**: Shell script linting
- **shfmt**: Shell script formatting
- **ruff**: Python linting and auto-fixing
- **black**: Python code formatting
- **yamllint**: YAML file linting
- **actionlint**: GitHub Actions workflow linting

### 4. Development Tools Installation

#### System Tools (Linux/Ubuntu)
```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y \
    shellcheck \
    shfmt \
    jq \
    curl \
    build-essential

# Install yq for YAML processing
sudo wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64
sudo chmod +x /usr/local/bin/yq
```

#### macOS Tools
```bash
# Install with Homebrew
brew install shellcheck shfmt jq yq
```

## Code Quality and Testing

### Linting and Formatting

#### Manual Execution
```bash
# Run all linters
make lint

# Format code automatically
make fmt

# Check formatting without changes
make fmt-check
```

#### Individual Tools
```bash
# Python linting
python -m ruff check .

# Python formatting
python -m black .

# Shell script linting
shellcheck $(find . -name "*.sh" -not -path "./.venv/*")

# Shell script formatting
shfmt -i 2 -bn -ci -w $(find . -name "*.sh" -not -path "./.venv/*")

# YAML linting
yamllint -c .yamllint.yaml .

# Helm chart linting
helm lint charts/kserve-vllm-mini
helm lint charts/kvmini
```

### Testing

#### Unit Tests
```bash
# Run all tests
make test

# Run specific test file
python -m pytest tests/test_analyze.py -v

# Run tests with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

#### Integration Tests
```bash
# Run integration tests (requires Kubernetes cluster)
./tests/integration_test.sh

# Run specific integration test
pytest tests/integration/ -k "test_benchmark_execution"
```

#### Helm Tests
```bash
# Test Helm charts
make helm-test

# Manual Helm testing
helm install test-release charts/kserve-vllm-mini --dry-run --debug
helm template test-release charts/kserve-vllm-mini > /tmp/rendered.yaml
```

## IDE Configuration

### Visual Studio Code

Create `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./.venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests/"],
    "files.associations": {
        "*.yaml": "yaml",
        "*.yml": "yaml"
    },
    "yaml.schemas": {
        "https://json.schemastore.org/github-workflow.json": ".github/workflows/*.yml"
    }
}
```

Create `.vscode/extensions.json`:
```json
{
    "recommendations": [
        "ms-python.python",
        "ms-python.black-formatter",
        "charliermarsh.ruff",
        "redhat.vscode-yaml",
        "ms-kubernetes-tools.vscode-kubernetes-tools",
        "ms-vscode.vscode-docker"
    ]
}
```

### PyCharm

1. **Interpreter Setup**:
   - File → Settings → Project → Python Interpreter
   - Add Local Interpreter → Existing environment
   - Select `.venv/bin/python`

2. **Code Quality Tools**:
   - File → Settings → Tools → External Tools
   - Add configurations for ruff, black, shellcheck

3. **Testing**:
   - File → Settings → Tools → Python Integrated Tools
   - Default test runner: pytest

## Development Workflow

### Branch Management

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Create bugfix branch
git checkout -b bugfix/issue-description

# Create documentation branch
git checkout -b docs/update-api-docs
```

### Making Changes

1. **Code Changes**:
   ```bash
   # Make your changes
   vim your_file.py

   # Run pre-commit to check quality
   pre-commit run --files your_file.py

   # Run tests
   python -m pytest tests/ -v
   ```

2. **Documentation Changes**:
   ```bash
   # Update documentation
   vim docs/API.md

   # Check YAML/Markdown formatting
   yamllint docs/
   ```

3. **Configuration Changes**:
   ```bash
   # Update Helm charts
   vim charts/kserve-vllm-mini/values.yaml

   # Validate charts
   make helm-lint
   ```

### Pre-commit Validation

Before committing, ensure all checks pass:
```bash
# Run all pre-commit hooks
pre-commit run --all-files

# If issues found, fix them and retry
pre-commit run --all-files
```

### Commit Guidelines

Follow conventional commit format:
```bash
# Feature commits
git commit -m "feat: add speculative decoding profile"

# Bug fixes
git commit -m "fix: resolve memory leak in analyzer"

# Documentation
git commit -m "docs: update API documentation"

# Configuration
git commit -m "config: update Helm chart values"

# Tests
git commit -m "test: add unit tests for cost estimator"
```

## Testing Your Changes

### Local Testing

1. **Unit Tests**:
   ```bash
   # Test your changes
   python -m pytest tests/test_your_module.py -v

   # Test with coverage
   python -m pytest tests/ --cov=your_module
   ```

2. **Integration Testing**:
   ```bash
   # If you have a Kubernetes cluster
   ./tests/integration_test.sh

   # Test Helm charts
   helm install test charts/kserve-vllm-mini --dry-run
   ```

3. **Manual Testing**:
   ```bash
   # Test CLI tools
   python analyze.py --help
   python cost_estimator.py --help

   # Test scripts
   ./scripts/fix-shellcheck.sh --dry-run
   ```

### CI/CD Testing

Push your branch to trigger CI:
```bash
git push -u origin feature/your-feature-name
```

Monitor the GitHub Actions workflows:
- **Lint and Test**: Code quality and unit tests
- **Helm Tests**: Chart validation and testing
- **Integration Tests**: Full system testing

## Debugging

### Common Issues

1. **Import Errors**:
   ```bash
   # Ensure virtual environment is activated
   source .venv/bin/activate

   # Reinstall dependencies
   pip install -r requirements-dev.txt
   ```

2. **Pre-commit Failures**:
   ```bash
   # Update pre-commit hooks
   pre-commit autoupdate

   # Run individual hook
   pre-commit run shellcheck --all-files
   ```

3. **Test Failures**:
   ```bash
   # Run with verbose output
   python -m pytest tests/ -v -s

   # Run specific failing test
   python -m pytest tests/test_module.py::test_function -v
   ```

### Debugging Tools

1. **Python Debugging**:
   ```python
   # Add breakpoints
   import pdb; pdb.set_trace()

   # Or use ipdb for enhanced debugging
   import ipdb; ipdb.set_trace()
   ```

2. **Shell Script Debugging**:
   ```bash
   # Enable debug mode
   bash -x your_script.sh

   # Add debug output
   set -x  # Enable debug mode
   set +x  # Disable debug mode
   ```

3. **Kubernetes Debugging**:
   ```bash
   # Check resource status
   kubectl get pods -n ml-prod
   kubectl describe pod pod-name -n ml-prod

   # View logs
   kubectl logs -f pod-name -n ml-prod
   ```

## Contributing Guidelines

### Before Submitting PR

1. **Code Quality**:
   ```bash
   # All linters pass
   make lint

   # All tests pass
   make test

   # Pre-commit hooks pass
   pre-commit run --all-files
   ```

2. **Documentation**:
   - Update relevant documentation
   - Add docstrings to new functions
   - Update API documentation if needed

3. **Tests**:
   - Add unit tests for new functionality
   - Update integration tests if needed
   - Ensure test coverage remains high

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Tests added/updated for new functionality
- [ ] Documentation updated
- [ ] Pre-commit hooks pass
- [ ] CI/CD pipeline passes
- [ ] Changes are backward compatible
- [ ] Breaking changes are documented

## Environment Variables

Set these for development:

```bash
# Export in your shell profile (.bashrc, .zshrc)
export KVMINI_DEV_MODE=true
export KVMINI_LOG_LEVEL=DEBUG
export KVMINI_OUTPUT_DIR=./dev-results

# Kubernetes development
export KUBECONFIG=$HOME/.kube/config

# AWS/S3 for testing (if needed)
export AWS_PROFILE=development
export AWS_DEFAULT_REGION=us-west-2
```

## Additional Resources

- [Contributing Guidelines](../CONTRIBUTING.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)
- [API Documentation](API.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)
- [Feature Matrix](FEATURES.md)

## Getting Help

- 💬 [GitHub Discussions](https://github.com/siryoos/kserve-vllm-mini/discussions)
- 🐛 [Issue Tracker](https://github.com/siryoos/kserve-vllm-mini/issues)
- 📚 [Documentation](../README.md)

## Next Steps

Once your development environment is set up:

1. Pick an issue from the [issue tracker](https://github.com/siryoos/kserve-vllm-mini/issues)
2. Create a feature branch
3. Make your changes following this guide
4. Submit a pull request

Happy coding! 🚀
