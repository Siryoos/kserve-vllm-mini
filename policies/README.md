# Policy Pack

This directory contains optional cluster policy packs for runtime hardening and guardrails.

## Kyverno

Apply in audit mode by default:

```
kubectl apply -f policies/kyverno/
```

Policies:
- `nonroot.yaml` — require `runAsNonRoot: true`
- `readonlyfs.yaml` — require `readOnlyRootFilesystem: true`
- `gpu-requests.yaml` — deny pods using GPU without explicit `requests/limits`
- `no-hostpath.yaml` — forbid `hostPath` volumes

Switch to enforce mode per namespace by labeling, if you use Kyverno namespaced policies, or by changing `validationFailureAction: Enforce` and optionally scoping via `match.namespaces`.

## Gatekeeper

ConstraintTemplates and Constraints are provided as equivalents:

```
kubectl apply -f policies/gatekeeper/constrainttemplates.yaml
kubectl apply -f policies/gatekeeper/constraints.yaml
```

Start in audit-only (default). Move to enforce mode by adding `enforcementAction: deny` in constraints once validated.

