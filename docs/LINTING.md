# Code Quality and Linting Guide

This document covers the code quality tools, linting configuration, and pre-commit hooks used in the kserve-vllm-mini project.

## Overview

The project uses a comprehensive set of automated code quality tools to maintain consistency, catch bugs early, and ensure best practices. All tools run automatically via pre-commit hooks and CI/CD pipelines.

## Tools Stack

### Python Tools

| Tool | Purpose | Configuration File | Auto-Fix |
|------|---------|-------------------|----------|
| **ruff** | Fast Python linter and formatter | `pyproject.toml` | ✅ Yes |
| **black** | Code formatting | `pyproject.toml` | ✅ Yes |

### Shell Script Tools

| Tool | Purpose | Configuration | Auto-Fix |
|------|---------|---------------|----------|
| **shellcheck** | Shell script linting | Built-in rules | ❌ Manual |
| **shfmt** | Shell script formatting | CLI args: `-i 2 -bn -ci` | ✅ Yes |

### YAML/Configuration Tools

| Tool | Purpose | Configuration File | Auto-Fix |
|------|---------|-------------------|----------|
| **yamllint** | YAML linting | `.yamllint.yaml` | ❌ Manual |
| **actionlint** | GitHub Actions linting | Built-in rules | ❌ Manual |

### Generic Tools

| Tool | Purpose | Auto-Fix |
|------|---------|----------|
| **end-of-file-fixer** | Ensures files end with newline | ✅ Yes |
| **trailing-whitespace** | Removes trailing spaces | ✅ Yes |
| **mixed-line-ending** | Fixes line endings | ✅ Yes |

## Configuration Files

### `.pre-commit-config.yaml`

The main pre-commit configuration:

```yaml
exclude: '^(venv/|\\.venv/|env/|\\.env/|.*/site-packages/|.*/dist-info/|__pycache__/|.*\\.pyc$|docs/website/node_modules/)'

repos:
  # Shell script linting and formatting
  - repo: https://github.com/shellcheck-py/shellcheck-py
    rev: v0.11.0.1
    hooks:
      - id: shellcheck
        args: ["-x"]
        files: \\.(sh|bash)$

  - repo: https://github.com/scop/pre-commit-shfmt
    rev: v3.12.0-2
    hooks:
      - id: shfmt
        args: ["-i", "2", "-bn", "-ci"]

  # Generic file fixes
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: mixed-line-ending

  # Python linting and formatting
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.13.0
    hooks:
      - id: ruff
        args: ["--fix"]
      - id: ruff-format

  - repo: https://github.com/psf/black
    rev: 25.1.0
    hooks:
      - id: black

  # GitHub Actions workflow linting
  - repo: https://github.com/rhysd/actionlint
    rev: v1.6.27
    hooks:
      - id: actionlint
        files: ^\\.github/workflows/.*\\.ya?ml$

  # YAML linting
  - repo: https://github.com/adrienverge/yamllint
    rev: v1.35.1
    hooks:
      - id: yamllint
        args: ["-c", ".yamllint.yaml"]
```

### `pyproject.toml` (Python Configuration)

Python tool configuration:

```toml
[tool.ruff]
# Exclude directories
exclude = [
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    "docs/website/node_modules"
]

# Target Python 3.11+
target-version = "py311"

# Line length
line-length = 88

[tool.ruff.lint]
# Enable rule categories
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # Pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
    "N",   # pep8-naming
    "S",   # flake8-bandit (security)
    "T20", # flake8-print
    "SIM", # flake8-simplify
]

# Disable specific rules
ignore = [
    "S101",  # assert statements (common in tests)
    "T201",  # print statements (OK in CLI tools)
    "B008",  # function calls in argument defaults
]

[tool.ruff.lint.per-file-ignores]
# Test files can use assert and fixtures
"tests/**/*.py" = ["S101", "S603", "S607"]
# Scripts can use print statements
"scripts/**/*.py" = ["T201"]

[tool.black]
line-length = 88
target-version = ['py311']
exclude = '''
/(
    \\.venv
    | venv
    | __pycache__
    | build
    | dist
    | docs/website/node_modules
)/
'''
```

### `.yamllint.yaml` (YAML Configuration)

```yaml
extends: default

rules:
  # Allow longer lines for readability
  line-length:
    max: 120
    level: warning

  # Allow multiple spaces for alignment
  indentation:
    spaces: 2
    indent-sequences: true
    check-multi-line-strings: false

  # Relax comment requirements
  comments:
    min-spaces-from-content: 1

  # Allow empty values
  empty-values:
    forbid-in-block-mappings: false
    forbid-in-flow-mappings: false

ignore: |
  .venv/
  venv/
  __pycache__/
  build/
  dist/
  docs/website/node_modules/
  charts/*/templates/*.yaml  # Helm templates have Go templating
  .github/workflows/*.yml    # GitHub Actions have embedded scripts
```

## Installation and Setup

### Install Pre-commit

```bash
# Install pre-commit tool
pip install pre-commit

# Install the hooks
pre-commit install

# Install commit-msg hook (optional)
pre-commit install --hook-type commit-msg
```

### Install System Tools

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y shellcheck shfmt jq yq
```

#### macOS
```bash
brew install shellcheck shfmt jq yq
```

#### Manual Installation (shfmt)
```bash
# Download and install shfmt
curl -L https://github.com/mvdan/sh/releases/download/v3.7.0/shfmt_v3.7.0_linux_amd64 -o shfmt
chmod +x shfmt
sudo mv shfmt /usr/local/bin/
```

## Usage

### Automatic (Pre-commit Hooks)

Hooks run automatically on `git commit`:

```bash
# Make changes
vim your_file.py

# Stage changes
git add your_file.py

# Commit triggers pre-commit hooks
git commit -m "feat: add new feature"
```

If hooks fail, they'll prevent the commit and show what needs fixing.

### Manual Execution

#### Run All Hooks
```bash
# Run on all files
pre-commit run --all-files

# Run on staged files only
pre-commit run

# Run specific hook
pre-commit run shellcheck --all-files
pre-commit run black --all-files
```

#### Individual Tools

**Python:**
```bash
# Ruff linting (with auto-fix)
python -m ruff check . --fix

# Ruff formatting
python -m ruff format .

# Black formatting
python -m black .

# Check formatting without changes
python -m black --check .
```

**Shell Scripts:**
```bash
# ShellCheck linting
shellcheck $(find . -name "*.sh" -not -path "./.venv/*")

# shfmt formatting
shfmt -i 2 -bn -ci -w $(find . -name "*.sh" -not -path "./.venv/*")

# Check formatting without changes
shfmt -i 2 -bn -ci -d $(find . -name "*.sh" -not -path "./.venv/*")
```

**YAML:**
```bash
# Yamllint
yamllint -c .yamllint.yaml .

# Actionlint for GitHub Actions
actionlint
```

### Makefile Shortcuts

```bash
# Run all linters
make lint

# Format code
make fmt

# Check formatting without changes
make fmt-check

# Lint Helm charts
make helm-lint
```

## Rule Configuration

### Python Rules (Ruff)

Key rule categories enabled:

- **E/W**: pycodestyle errors and warnings
- **F**: Pyflakes (undefined variables, imports)
- **I**: import sorting
- **B**: bugbear (common bugs)
- **C4**: comprehensions (list/dict optimization)
- **UP**: pyupgrade (modern Python syntax)
- **N**: PEP 8 naming conventions
- **S**: bandit security rules
- **T20**: print statement detection
- **SIM**: code simplification

### Shell Rules (ShellCheck)

Common rules enforced:

- **SC2086**: Unquoted variables (double quote to prevent globbing)
- **SC2034**: Unused variables
- **SC2164**: Use `cd ... || exit` for error handling
- **SC2155**: Declare and assign separately
- **SC2181**: Check exit code directly with `if cmd`

### YAML Rules (yamllint)

Key rules:

- **line-length**: Maximum 120 characters
- **indentation**: 2 spaces, consistent
- **trailing-spaces**: Not allowed
- **empty-lines**: Controlled empty line usage
- **comments**: Proper comment formatting

## Auto-fixing

### Tools with Auto-fix Capability

| Tool | What it fixes | Command |
|------|---------------|---------|
| **ruff** | Import sorting, code style, some bugs | `ruff check --fix` |
| **ruff format** | Code formatting | `ruff format` |
| **black** | Code formatting | `black .` |
| **shfmt** | Shell script formatting | `shfmt -w` |
| **end-of-file-fixer** | Missing final newlines | Automatic |
| **trailing-whitespace** | Trailing spaces | Automatic |

### Manual Fix Required

| Tool | Issues requiring manual fix |
|------|----------------------------|
| **shellcheck** | Logic errors, unsafe practices, undefined variables |
| **yamllint** | YAML syntax errors, structural issues |
| **actionlint** | GitHub Actions workflow errors |

## CI/CD Integration

### GitHub Actions

The project includes comprehensive CI/CD linting:

```yaml
# .github/workflows/lint-test.yml
jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install tools
        run: |
          sudo apt-get install -y shellcheck
          pip install pre-commit
      - name: Run pre-commit
        run: pre-commit run --all-files --show-diff-on-failure
```

### Status Badges

Add to your PRs to show linting status:

- ✅ All linters pass
- ❌ Linting failures need fixing
- ⚠️ Warnings present but not blocking

## Troubleshooting

### Common Issues

1. **Pre-commit hooks fail to install:**
   ```bash
   # Update pre-commit
   pre-commit autoupdate

   # Clear cache and reinstall
   pre-commit clean
   pre-commit install
   ```

2. **Shellcheck not found:**
   ```bash
   # Install shellcheck
   sudo apt-get install shellcheck
   # or
   brew install shellcheck
   ```

3. **Python import sorting conflicts:**
   ```bash
   # Ruff handles import sorting, disable isort if present
   # Remove isort from pre-commit config
   ```

4. **YAML validation errors:**
   ```bash
   # Check YAML syntax
   python -c "import yaml; yaml.safe_load(open('file.yml'))"

   # Use yq for validation
   yq eval . file.yml
   ```

### Skipping Hooks

For emergency commits (not recommended):

```bash
# Skip all hooks
git commit --no-verify -m "emergency fix"

# Skip specific hook
SKIP=shellcheck git commit -m "skip shellcheck only"
```

### Updating Hooks

```bash
# Update to latest versions
pre-commit autoupdate

# Update specific repo
pre-commit autoupdate --repo https://github.com/astral-sh/ruff-pre-commit
```

## Custom Rules

### Adding New Rules

1. **Python (ruff):**
   ```toml
   # pyproject.toml
   [tool.ruff.lint]
   select = ["E", "W", "F", "NEW_RULE_CATEGORY"]
   ```

2. **Shell (shellcheck):**
   ```bash
   # Enable additional checks
   # shellcheck enable=require-variable-braces
   ```

3. **YAML (yamllint):**
   ```yaml
   # .yamllint.yaml
   rules:
     new-rule:
       level: error
   ```

### Project-specific Ignores

```python
# Ignore specific rule for this file
# ruff: noqa: E501

# Ignore rule for specific line
long_line = "this is too long"  # noqa: E501
```

```bash
# Disable shellcheck for script
# shellcheck disable=SC2086
```

## Best Practices

### Development Workflow

1. **Before committing:**
   ```bash
   # Run linters manually
   make lint

   # Fix auto-fixable issues
   make fmt

   # Commit (triggers hooks)
   git commit -m "your message"
   ```

2. **IDE Integration:**
   - Configure your IDE to run linters on save
   - Enable format-on-save for supported tools
   - Set up real-time error highlighting

3. **Code Reviews:**
   - All linting issues must be resolved before merge
   - Use `# noqa` comments sparingly and with justification
   - Document any disabled rules in PR description

### Writing Lint-friendly Code

**Python:**
```python
# Good: Clear, formatted code
def calculate_cost(
    requests: int,
    duration: float,
    cpu_cores: float,
) -> float:
    """Calculate deployment cost."""
    hourly_rate = get_hourly_rate()
    return requests * duration * cpu_cores * hourly_rate

# Avoid: Dense, unformatted code
def calculate_cost(requests,duration,cpu_cores): return requests*duration*cpu_cores*get_hourly_rate()
```

**Shell:**
```bash
# Good: Quoted variables, error handling
files=$(find . -name "*.sh")
if [[ -n "$files" ]]; then
    shellcheck "$files"
fi

# Avoid: Unquoted variables, no error handling
files=$(find . -name *.sh)
shellcheck $files
```

## Integration with Development Tools

### IDE Setup

**VS Code:**
```json
{
    "python.linting.ruffEnabled": true,
    "python.formatting.provider": "black",
    "shellcheck.enable": true,
    "yaml.validate": true
}
```

**PyCharm:**
- Install Ruff plugin
- Configure Black as external tool
- Enable YAML schema validation

### Git Hooks

Beyond pre-commit, you can add other hooks:

```bash
# .git/hooks/pre-push
#!/bin/bash
# Run full test suite before push
make test
```

## Performance

### Hook Performance

| Hook | Typical Runtime | Performance Tips |
|------|----------------|------------------|
| ruff | <1s | Very fast, runs on changed files only |
| black | <2s | Fast, incremental processing |
| shellcheck | <5s | Moderate, scales with number of shell files |
| yamllint | <3s | Fast, scales with YAML files |

### Optimization Tips

1. **File filtering:**
   ```yaml
   # Only run on relevant files
   - id: ruff
     files: \\.py$
   ```

2. **Parallel execution:**
   ```bash
   # Pre-commit runs hooks in parallel automatically
   pre-commit run --all-files
   ```

3. **Incremental runs:**
   ```bash
   # Only run on changed files
   pre-commit run
   ```

This comprehensive linting setup ensures consistent code quality across the project while providing fast feedback to developers.
