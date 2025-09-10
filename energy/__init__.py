"""Energy accounting utilities for kserve-vllm-mini.

This package provides:
- A power sampler that queries DCGM/Prometheus for GPU power (W) attached
  to a target KServe predictor pod.
- Alignment of sampled power to a run's active window (derived from requests.csv).
- Trapezoidal integration to compute Wh over the active window, optional idle tax,
  and normalized per-request and per-1k-tokens metrics.

See energy/collector.py and docs/ENERGY_METHOD.md for details.
"""

__all__ = [
    "__version__",
]

__version__ = "0.1.0"

