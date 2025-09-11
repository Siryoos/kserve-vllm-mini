# Security & Supply Chain

This project ships a minimal policy pack and supply chain tooling to improve runtime security and artifact provenance. Policies are conservative by default and start in audit mode.

## Policies

Kyverno (audit):
- Require non-root: `policies/kyverno/nonroot.yaml`
- Require read-only rootfs: `policies/kyverno/readonlyfs.yaml`
- Require explicit GPU requests/limits: `policies/kyverno/gpu-requests.yaml`
- Forbid hostPath volumes: `policies/kyverno/no-hostpath.yaml`

Gatekeeper (audit):
- Templates: `policies/gatekeeper/constrainttemplates.yaml`
- Constraints: `policies/gatekeeper/constraints.yaml`

Apply in audit mode, validate against your manifests, then enable enforce mode per namespace.

## SBOM & Signing

Tools in `tools/`:
- `sbom.sh` — generate SBOMs (SPDX-JSON) for deployed container images via `syft`
- `sign.sh` — sign container images via `cosign`

SBOMs and signatures are included in the artifact bundle produced by `tools/bundle_run.sh` when available.

### SBOM Example

```
./tools/sbom.sh --namespace ml-prod --service demo-llm --out-dir sboms/
```

### Signing Example

```
./tools/sign.sh --image myrepo/vllm-runtime@sha256:... --key cosign.key
```

See also: `policies/README.md` for application and enforcement notes.
