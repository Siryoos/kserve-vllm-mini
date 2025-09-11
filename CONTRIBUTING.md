# Contributing to kserve-vllm-mini

Welcome! We're excited to have you contribute to making KServe + vLLM benchmarking better for everyone.

## Quick Start for Contributors

```bash
# Fork the repo and clone your fork
git clone https://github.com/YOURUSERNAME/kserve-vllm-mini.git
cd kserve-vllm-mini

# Set up development environment
pip install -r requirements-dev.txt
pre-commit install

# Run tests to verify setup
python -m pytest tests/
./scripts/validate_config.py --profile runners/profiles/standard.yaml
```

## How to Contribute

### 🟢 Good First Issues

Perfect entry points for new contributors:

1. **Add new quantization profile** [`good-first-issue` `profiles`]
   - Create `runners/profiles/quantization/int4.yaml`
   - Test with a small model and document memory reduction
   - Add validation checks for INT4 compatibility

2. **Improve error messages** [`good-first-issue` `dx`]
   - Enhance `scripts/validate_config.py` error messages
   - Add suggestions for common fixes
   - Include links to relevant documentation

3. **Add profile validation** [`good-first-issue` `validation`]
   - Check if GPU memory is sufficient for model + batch size
   - Validate model format matches quantization method
   - Add warnings for suboptimal configurations

4. **Documentation improvements** [`good-first-issue` `docs`]
   - Write tutorial for MIG deployments using `profiles/mig/`
   - Create troubleshooting guide for common benchmark failures
   - Add examples for different cloud providers

5. **CLI enhancements** [`good-first-issue` `cli`]
   - Add `--dry-run` flag to `bench.sh` for config validation
   - Implement `--list-profiles` to show available profiles
   - Add progress bars for long-running benchmarks

### 🟡 Help Wanted

Seeking community expertise:

6. **TensorRT-LLM optimization** [`help-wanted` `tensorrt`]
   - Create TensorRT-LLM specific profiles with optimal flags
   - Benchmark engine build time vs inference performance tradeoffs
   - Document TensorRT-LLM specific deployment patterns

7. **Model zoo expansion** [`help-wanted` `models`]
   - Create tested profiles for Llama, Mistral, CodeLlama, Phi families
   - Document model-specific optimization recommendations
   - Validate quantization compatibility across model types

8. **Cloud provider guides** [`help-wanted` `cloud`]
   - AWS EKS + KServe deployment guide with IAM roles
   - GCP GKE + KServe with Workload Identity setup
   - Azure AKS + KServe integration patterns

9. **Performance baselines** [`help-wanted` `benchmarks`]
   - Collect reference results for A100, H100, L40S, V100
   - Document performance scaling across instance types
   - Create hardware recommendation matrices

### 🔴 Major Contributions

High-impact features for experienced contributors:

10. **Profile system integration** [`major` `core`]
    - Load `vllm_features` from YAML profiles into deployments
    - Implement profile inheritance and overrides
    - Add profile validation pipeline

11. **Advanced analytics** [`major` `analytics`]
    - Statistical analysis of performance trends over time
    - Regression detection and alerting
    - Cost optimization recommendations

12. **GUI dashboard** [`major` `frontend`]
    - Web interface for benchmark management and visualization
    - Historical results comparison
    - Real-time monitoring during benchmark runs

## Types of Contributions

### 🏗️ Code Contributions

**Benchmark Profiles** (`runners/profiles/`)
- Create YAML profiles for new vLLM features
- Test profiles with multiple models and document results
- Add validation rules to prevent common misconfigurations

**Scripts & Tools** (`scripts/`)
- Extend `validate_config.py` with new checks
- Improve `compare_backends.py` with additional metrics
- Add new analysis tools for specific use cases

**Core Benchmarking** (`*.py`, `*.sh`)
- Enhance load testing patterns and traffic models
- Improve cost estimation accuracy
- Add support for new KServe runtimes

### 📝 Documentation Contributions

**Tutorials** (`docs/`)
- Step-by-step guides for specific deployment scenarios
- Cloud provider specific instructions
- Troubleshooting guides for common issues

**Profile Documentation**
- Document expected performance impacts for each profile
- Add usage examples and recommended models
- Create comparison matrices between profiles

**API Documentation**
- Document configuration options and validation rules
- Add examples for programmatic usage
- Improve error message documentation

### 🧪 Testing Contributions

**Test Coverage**
- Unit tests for validation logic
- Integration tests for benchmark workflows
- Profile validation tests

**CI/CD Improvements**
- GitHub Actions workflow improvements
- Pre-commit hook enhancements
- Automated profile testing

## Development Guidelines

### Code Standards

**Python Code**
```python
# Use type hints
def validate_profile(config: Dict[str, Any]) -> ValidationResult:
    pass

# Follow black formatting (automatic via pre-commit)
# Use descriptive variable names
# Add docstrings for public functions
```

**Shell Scripts**
```bash
#!/bin/bash
set -euo pipefail  # Always include error handling

# Use descriptive variable names
PROFILE_PATH="$1"
VALIDATION_RESULT=""

# Quote variables to handle spaces
if [[ -f "$PROFILE_PATH" ]]; then
    echo "Validating profile: $PROFILE_PATH"
fi
```

**YAML Profiles**
```yaml
# Use consistent structure
pattern: "steady"
requests: 200
concurrency: 10
max_tokens: 64

description: "Brief description of profile purpose"
use_cases:
  - "Primary use case"
  - "Secondary use case"

# Document expected impacts
characteristics:
  traffic_shape: "Steady arrival rate"
  expected_benefits: "Specific performance improvements"
```

### Testing Requirements

**Before submitting a PR:**

1. **Run validation checks**
```bash
# Code formatting and linting
pre-commit run --all-files

# Configuration validation tests
python -m pytest tests/test_validation.py

# Profile validation
./scripts/validate_config.py --profile your-new-profile.yaml
```

2. **Test with real deployment** (if possible)
```bash
# Test new profiles end-to-end
./bench.sh --profile your-new-profile.yaml --requests 50
```

3. **Update documentation**
- Add profile to feature matrix in README.md
- Update docs/FEATURES.md with new capabilities
- Include usage examples

### Submission Process

1. **Create feature branch**
```bash
git checkout -b feature/add-int4-quantization-profile
```

2. **Make atomic commits**
```bash
git commit -m "Add INT4 quantization profile with validation checks"
git commit -m "Update documentation for INT4 profile usage"
```

3. **Test thoroughly**
- Run all validation checks
- Test with multiple configurations if possible
- Verify documentation builds correctly

4. **Create pull request**
- Use descriptive title: `Add INT4 quantization profile with validation`
- Fill out PR template completely
- Link to relevant issues
- Request review from maintainers

## Issue Templates

### 🐛 Bug Report
```markdown
**Profile/Command**: Which profile or command triggered the issue?
**Expected vs Actual**: What should have happened vs what happened?
**Environment**: KServe version, vLLM version, GPU type
**Logs**: Relevant error messages or log snippets
**Reproduction**: Minimal steps to reproduce the issue
```

### ✨ Feature Request
```markdown
**Problem**: What problem does this solve?
**Proposed Solution**: How should this work?
**Alternatives**: Other approaches considered?
**Additional Context**: Use cases, examples, related issues
```

### 📋 Profile Request
```markdown
**vLLM Feature**: Which vLLM feature should be benchmarked?
**Use Case**: What problem would this profile solve?
**Configuration**: Suggested vLLM arguments or settings
**Expected Impact**: Performance characteristics you expect
```

## Release Process

We follow semantic versioning (MAJOR.MINOR.PATCH):

- **PATCH** (0.1.1): Bug fixes, documentation updates, profile additions
- **MINOR** (0.2.0): New features, profile system changes, API additions
- **MAJOR** (1.0.0): Breaking changes, major architectural shifts

**Release criteria:**
- All CI checks pass
- Documentation is updated
- CHANGELOG.md includes all changes
- At least one maintainer approval

## Community Guidelines

### Code of Conduct

We follow the [Contributor Covenant](https://www.contributor-covenant.org/):
- Be respectful and inclusive
- Welcome newcomers and help them succeed
- Give constructive feedback
- Focus on what's best for the community

### Communication Channels

- **GitHub Issues**: Bug reports, feature requests, questions
- **GitHub Discussions**: General questions, showcase, ideas
- **Discord**: Real-time chat, community support
- **Mailing List**: Announcements, major decisions

### Recognition

Contributors are recognized through:
- 🏆 **Contributor profiles** in README.md
- 🎖️ **Special recognition** for major contributions
- 📊 **Annual contributor report** highlighting impact
- 🎁 **Swag and conference discounts** for regular contributors

## Getting Help

### Stuck on something?

1. **Check existing issues** for similar problems or questions
2. **Join Discord** for real-time help from the community
3. **Open a discussion** for general questions or brainstorming
4. **Create an issue** for specific bugs or feature requests

### Maintainer Response Times

We aim to respond within:
- 🟢 **Good first issues**: 24-48 hours
- 🟡 **Standard issues**: 3-5 business days
- 🔴 **Complex issues**: 1-2 weeks
- 🚨 **Security issues**: 24 hours

### Office Hours

Maintainers hold weekly office hours:
- **When**: Wednesdays 2-3 PM UTC
- **Where**: Discord voice channel
- **Topics**: Questions, code reviews, roadmap discussions

---

Thank you for contributing to kserve-vllm-mini! Every contribution, no matter how small, helps make KServe + vLLM benchmarking better for everyone. 🚀
