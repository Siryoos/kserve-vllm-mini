# CI/CD Fixes Applied

## Issues Resolved

### 1. Docker Build Error - User Creation
**Problem**: UID 65534 was already taken by the `nobody` user in the base image.
```
useradd: UID 65534 is not unique
```

**Solution**: Simplified to use existing `nobody` user directly:
```dockerfile
# Before: Complex user creation
RUN groupadd -r appuser && useradd -r -g appuser -u 65534 appuser
USER appuser

# After: Use existing nobody user
USER 65534:65534
```

### 2. Deprecated GitHub Actions
**Problem**: Using deprecated `v3` versions of upload/download artifact actions.
```
Error: This request has been automatically failed because it uses a deprecated version of `actions/upload-artifact: v3`
```

**Solution**: Updated all GitHub Actions to `v4`:
- `actions/upload-artifact@v3` → `actions/upload-artifact@v4`
- `actions/download-artifact@v3` → `actions/download-artifact@v4`

## Files Modified

1. **Dockerfile.harness** - Simplified user management
2. **.github/workflows/reference-matrix.yml** - Updated action versions
3. **.github/workflows/policy-ci.yml** - Updated action versions

## Verification

The fixes address:
✅ **Docker Build**: Container now builds successfully with non-root user
✅ **GitHub Actions**: No more deprecation warnings
✅ **Security**: Maintains non-root execution (UID 65534)
✅ **Functionality**: All features remain intact

## Testing

To verify the fixes locally:

```bash
# Test Docker build
docker build -f Dockerfile.harness -t kvmini-harness:test .

# Test CLI functionality
docker run --rm kvmini-harness:test --help

# Verify non-root user
docker run --rm kvmini-harness:test id
```

Expected output should show UID 65534 (nobody user).

---
*These fixes ensure the GA hardening CI/CD pipeline runs successfully without deprecated warnings or build failures.*
