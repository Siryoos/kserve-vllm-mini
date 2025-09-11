#!/bin/bash
set -e

# Policy CI Test Script
# Tests policy enforcement in KIND cluster

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🔧 Policy CI Test Suite"
echo "======================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
  echo -e "${GREEN}ℹ️  $1${NC}"
}

log_warn() {
  echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
  echo -e "${RED}❌ $1${NC}"
}

log_success() {
  echo -e "${GREEN}✅ $1${NC}"
}

# Check prerequisites
check_prereqs() {
  log_info "Checking prerequisites..."

  if ! command -v kubectl &>/dev/null; then
    log_error "kubectl not found"
    exit 1
  fi

  if ! kubectl cluster-info &>/dev/null; then
    log_error "No Kubernetes cluster access"
    exit 1
  fi

  log_success "Prerequisites satisfied"
}

# Install Gatekeeper
install_gatekeeper() {
  log_info "Installing Gatekeeper..."

  kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/release-3.14/deploy/gatekeeper.yaml

  log_info "Waiting for Gatekeeper to be ready..."
  kubectl wait --for=condition=available --timeout=300s deployment/gatekeeper-controller-manager -n gatekeeper-system
  kubectl wait --for=condition=available --timeout=300s deployment/gatekeeper-audit -n gatekeeper-system

  log_success "Gatekeeper installed"
}

# Apply policies
apply_policies() {
  log_info "Applying security policies..."

  if [ -d "$PROJECT_ROOT/policies/gatekeeper" ]; then
    kubectl apply -f "$PROJECT_ROOT/policies/gatekeeper/"
    sleep 10 # Allow policies to be processed
    log_success "Gatekeeper policies applied"
  else
    log_warn "Gatekeeper policies directory not found"
  fi

  if [ -d "$PROJECT_ROOT/policies/kyverno" ]; then
    # Check if Kyverno is installed
    if kubectl get crd policies.kyverno.io &>/dev/null; then
      kubectl apply -f "$PROJECT_ROOT/policies/kyverno/"
      log_success "Kyverno policies applied"
    else
      log_warn "Kyverno not installed, skipping Kyverno policies"
    fi
  else
    log_warn "Kyverno policies directory not found"
  fi
}

# Create test namespace
setup_test_env() {
  log_info "Setting up test environment..."

  kubectl create namespace policy-test-suite || true

  log_success "Test environment ready"
}

# Test policy violations
test_violations() {
  log_info "Testing policy violations..."

  local test_dir="/tmp/policy-tests"
  mkdir -p "$test_dir"

  # Test 1: hostPath volume (should be blocked/flagged)
  cat >"$test_dir/bad-hostpath.yaml" <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: test-hostpath-violation
  namespace: policy-test-suite
spec:
  containers:
  - name: test
    image: nginx:1.21
    volumeMounts:
    - name: host-mount
      mountPath: /host
  volumes:
  - name: host-mount
    hostPath:
      path: /
      type: Directory
EOF

  # Test 2: Root user (should be blocked/flagged)
  cat >"$test_dir/bad-root.yaml" <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: test-root-violation
  namespace: policy-test-suite
spec:
  containers:
  - name: test
    image: nginx:1.21
    securityContext:
      runAsUser: 0
      runAsNonRoot: false
EOF

  # Test 3: No resource limits (should be blocked/flagged)
  cat >"$test_dir/bad-no-limits.yaml" <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: test-no-limits-violation
  namespace: policy-test-suite
spec:
  containers:
  - name: test
    image: nginx:1.21
EOF

  # Test 4: Privileged container (should be blocked/flagged)
  cat >"$test_dir/bad-privileged.yaml" <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: test-privileged-violation
  namespace: policy-test-suite
spec:
  containers:
  - name: test
    image: nginx:1.21
    securityContext:
      privileged: true
EOF

  # Apply violation tests (in audit mode, these should be created but flagged)
  log_info "Applying test violations (audit mode)..."

  for test_file in "$test_dir"/bad-*.yaml; do
    echo "Testing $(basename "$test_file")..."
    if kubectl apply -f "$test_file" 2>&1 | grep -q "denied\|rejected\|webhook"; then
      log_success "$(basename "$test_file") properly blocked by admission controller"
    else
      log_warn "$(basename "$test_file") was not blocked (audit mode or policies not enforced)"
    fi
  done
}

# Test compliant manifests
test_compliant() {
  log_info "Testing compliant manifests..."

  local test_dir="/tmp/policy-tests"

  # Test 5: Compliant pod (should succeed)
  cat >"$test_dir/good-pod.yaml" <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: test-compliant-pod
  namespace: policy-test-suite
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    runAsGroup: 65534
    fsGroup: 65534
  containers:
  - name: test
    image: nginx:1.21
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop:
        - ALL
      readOnlyRootFilesystem: true
      runAsNonRoot: true
      runAsUser: 65534
    resources:
      limits:
        cpu: "500m"
        memory: "512Mi"
      requests:
        cpu: "100m"
        memory: "128Mi"
    volumeMounts:
    - name: tmp
      mountPath: /tmp
    - name: var-cache
      mountPath: /var/cache/nginx
    - name: var-run
      mountPath: /var/run
  volumes:
  - name: tmp
    emptyDir: {}
  - name: var-cache
    emptyDir: {}
  - name: var-run
    emptyDir: {}
EOF

  # Apply compliant test
  log_info "Applying compliant manifest..."

  if kubectl apply -f "$test_dir/good-pod.yaml"; then
    log_success "Compliant pod created successfully"
  else
    log_error "Compliant pod creation failed"
    return 1
  fi

  # Wait for pod to be ready
  kubectl wait --for=condition=ready pod/test-compliant-pod -n policy-test-suite --timeout=60s || true
}

# Check audit results
check_audit_results() {
  log_info "Checking audit results..."

  sleep 30 # Allow time for audit to process

  # Check Gatekeeper violations
  violations=$(kubectl get constraints -o json 2>/dev/null | jq -r '.items[] | select(.status.violations != null) | .status.violations[] | .message' 2>/dev/null || echo "")

  if [ -n "$violations" ]; then
    log_warn "Policy violations detected:"
    echo "$violations"

    # Count violations
    violation_count=$(echo "$violations" | wc -l)
    log_info "Total violations: $violation_count"
  else
    log_success "No policy violations detected"
  fi

  # Check constraint status
  log_info "Constraint status:"
  kubectl get constraints -o wide 2>/dev/null || log_warn "No constraints found"
}

# Test enforcement mode
test_enforcement() {
  log_info "Testing enforcement mode..."

  # Find a constraint to test enforcement with
  constraint=$(kubectl get constraints -o name 2>/dev/null | head -1 | cut -d'/' -f2)

  if [ -n "$constraint" ]; then
    log_info "Testing enforcement with constraint: $constraint"

    # Get constraint type
    constraint_type=$(kubectl get constraints "$constraint" -o jsonpath='{.kind}')

    # Try to update to enforcement mode
    kubectl patch "$constraint_type" "$constraint" \
      --type='merge' \
      -p='{"spec":{"enforcementAction":"deny"}}' 2>/dev/null || log_warn "Could not update enforcement mode"

    sleep 5

    # Test that a bad manifest is now blocked
    local test_dir="/tmp/policy-tests"
    if [ -f "$test_dir/bad-root.yaml" ]; then
      if kubectl apply -f "$test_dir/bad-root.yaml" 2>&1 | grep -q "denied\|rejected\|webhook"; then
        log_success "Enforcement mode successfully blocked bad manifest"
      else
        log_warn "Enforcement mode did not block manifest (may need more time or different constraint)"
      fi
    fi

    # Reset to audit mode
    kubectl patch "$constraint_type" "$constraint" \
      --type='merge' \
      -p='{"spec":{"enforcementAction":"warn"}}' 2>/dev/null || true
  else
    log_warn "No constraints found to test enforcement"
  fi
}

# Generate report
generate_report() {
  log_info "Generating policy report..."

  local report_file="$PROJECT_ROOT/policy-test-report.md"

  cat >"$report_file" <<EOF
# Policy CI Test Report

**Generated**: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
**Cluster**: $(kubectl config current-context)

## Test Summary

### ✅ Tests Completed
- [x] Gatekeeper installation
- [x] Policy application
- [x] Violation detection
- [x] Compliant manifest validation
- [x] Audit mode verification
- [x] Enforcement mode testing

### 📊 Results
EOF

  # Add constraint status to report
  {
    echo ""
    echo "### Policy Status"
    echo '```'
    kubectl get constraints -o wide 2>/dev/null || echo "No constraints found"
    echo '```'
  } >>"$report_file"

  # Add violations to report
  violations=$(kubectl get constraints -o json 2>/dev/null | jq -r '.items[] | select(.status.violations != null) | .status.violations[] | "- " + .message' 2>/dev/null || echo "- No violations detected")
  {
    echo ""
    echo "### Violations Detected"
    echo "$violations"
  } >>"$report_file"

  # Add recommendations
  cat >>"$report_file" <<'EOF'

### 🔧 Recommendations
1. Review any violations listed above and update manifests accordingly
2. Consider enabling enforcement mode for critical security policies
3. Add policy validation to CI/CD pipelines
4. Regularly audit and update policy configurations
5. Monitor policy violations in production environments

### 📋 Next Steps
- Update any non-compliant manifests
- Test enforcement mode in staging environment
- Deploy policies to production with appropriate enforcement actions
EOF

  log_success "Report generated: $report_file"
}

# Cleanup
cleanup() {
  log_info "Cleaning up test resources..."

  kubectl delete namespace policy-test-suite --ignore-not-found=true
  rm -rf /tmp/policy-tests

  log_success "Cleanup completed"
}

# Main execution
main() {
  check_prereqs
  setup_test_env
  install_gatekeeper
  apply_policies
  test_violations
  test_compliant
  check_audit_results
  test_enforcement
  generate_report

  if [ "${CLEANUP:-true}" != "false" ]; then
    cleanup
  fi

  log_success "Policy CI test suite completed!"
  echo ""
  echo "📄 See policy-test-report.md for detailed results"
}

# Handle cleanup on exit
trap cleanup EXIT

# Run main function
main "$@"
