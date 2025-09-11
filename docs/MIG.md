# MIG How-To

This guide shows how to run kserve-vllm-mini against different MIG profiles and generate a comparison matrix.

## Requirements

- NVIDIA device plugin with MIG support
- Nodes configured for MIG and exposing `nvidia.com/mig-*` resources
- DCGM exporter (optional, for power metrics)

## Profiles

Sample profiles are provided in `profiles/mig/` and `runners/profiles/mig/`.

- `a100-1g.5gb` — requests `nvidia.com/mig-1g.5gb: 1`
- `a100-2g.10gb` — requests `nvidia.com/mig-2g.10gb: 1`
- `full` — requests `nvidia.com/gpu: 1`

Node selectors assume `nvidia.com/mig.capable=true`. Adjust for your cluster labels if different.

## Sweep

Run a sweep comparing profiles (uses `isvc.yaml` as base and patches resources per profile):

```
./sweeps/mig-sweep.sh --profiles a100-1g.5gb,a100-2g.10gb,full \
  --profile-file runners/profiles/standard.yaml \
  --namespace ml-prod --service demo-llm \
  --prom-url http://prometheus.kube-system.svc.cluster.local:9090
```

Outputs `runs/mig-<ts>/mig_matrix.csv` with columns:

```
profile,p50,p95,throughput_rps,Wh_per_1k_tokens,$/1K tokens,error_rate
```

Generate an HTML report:

```
python report_generator.py --mig-matrix runs/mig-<ts>/mig_matrix.csv --output runs/mig-<ts>/mig_report.html
```

## Notes

- MIG label and resource keys vary. Confirm your device plugin exposes `nvidia.com/mig-*` resources and adjust profiles accordingly.
- DCGM pod attribution for MIG may require recent DCGM exporter with Kubernetes labels.
