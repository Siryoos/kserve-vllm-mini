# Energy Accounting Method

This document describes how kserve-vllm-mini computes energy for a benchmark run in defensible, reproducible terms.

## Scope

- Target: GPU power for the exact predictor pod(s) that serve requests.
- Source: DCGM exporter metrics via Prometheus (preferred). Queries fall back across common label names.
- Output: `energy.json` with Wh over the active run window, optional idle tax, and normalized metrics.

## Sampling

- The collector queries Prometheus at a fixed interval (default 1s):
  - Primary: `sum(DCGM_FI_DEV_POWER_USAGE{namespace="$NS",pod=~"$ISVC-predictor-.*"})`
  - Fallbacks: `nvidia_dcgm_power_usage_watts`, `nvidia_gpu_power_watts`
- If multiple GPU/MIG instances are in-use and expose pod labels, results are summed across instances.
- Timestamps are captured from the collector’s clock in seconds since epoch.

## Alignment to Active Window

- The active window is derived from `requests.csv` as:  
  `t0 = min(start_ms)/1000`, `t1 = max(start_ms + latency_ms)/1000`.
- By default, only samples within `[t0, t1]` are integrated. This excludes warm-up and cool-down.
- `--include-warmup` integrates the full sample span instead.

## Integration (Trapezoidal)

Energy in watt-hours is computed by trapezoidal integration over the aligned series:

```
Wh_active = Σ_i ((P[i] + P[i+1]) / 2) * (Δt_i_hours)
```

Samples with missing values are ignored. At least two valid samples inside the window are required to produce non-zero energy.

### Idle Tax (optional)

Two optional modes (off by default):

- `series`: Integrate energy outside `[t0, t1]` over the sample span and report as `Wh_idle_tax`.
- `baseline`: Estimate baseline power `P_idle` as the median of outside-window samples, multiply by outside duration (approx. average step × count).

## Normalization

From `requests.csv`, successful requests and total tokens are summed. The following are emitted:

- `Wh_per_request_active = Wh_active / success_count`
- `Wh_per_1k_tokens_active = (Wh_active / total_tokens) * 1000`

If tokens are missing, the per-1k-tokens value is `null`.

## Outputs

- `power.json`: raw samples `{samples: [{ts_s, watts}, ...], interval_s}`
- `energy.json`: `{Wh_active, Wh_idle_tax, Wh_per_request_active, Wh_per_1k_tokens_active, window, samples}`
- Optionally merges fields into `results.json` as:  
  `energy_wh_active`, `energy_wh_idle_tax`, `energy_wh_per_request`, `energy_wh_per_1k_tokens`.

## Validation & Expectations

- Two identical runs should produce `Wh/1K tokens` within ±10% p95 variance, assuming similar traffic and GPU clocks.
- If throughput doubles while p95 latency remains similar, `Wh/1K tokens` should decrease or remain flat.
- When sampling or DCGM is unavailable, energy fields are set to `null` and a warning is emitted.

## Caveats

- Accurate per-pod attribution requires DCGM metrics labeled with `pod` (or equivalent). Some deployments label at node/GPU only; in such cases, consider isolating the workload on the node during measurement.
- MIG labeling varies across device plugin versions; ensure the exporter includes MIG instance labels and pod attribution for multi-slice deployments.
- Sampling intervals shorter than 1s may yield diminishing returns; 1–2s is usually sufficient.

