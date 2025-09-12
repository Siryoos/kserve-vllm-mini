#!/usr/bin/env python3
"""
Energy Collector & Integrator

Collects GPU power (W) for the specific KServe predictor pod via Prometheus/DCGM,
and integrates power over the active benchmark window (from requests.csv) to
compute energy (Wh). Produces power samples (JSON) and energy.json, and can
optionally merge energy fields into results.json.

Usage:
  # 1) Sample power (DCGM via Prometheus) for N seconds
  python energy/collector.py collect \
    --namespace ml-prod --service demo-llm \
    --prom-url http://prometheus.kube-system.svc.cluster.local:9090 \
    --interval 1 --duration 120 --out runs/<id>/power.json

  # 2) Integrate Wh aligned to active benchmark window
  python energy/collector.py integrate \
    --run-dir runs/<id> \
    [--include-warmup] [--idle-tax baseline|series] \
    [--merge-results]

Notes:
 - If Prometheus/DCGM labels do not include pod references for your setup,
   you may need to adjust queries (see PROM_QUERIES below).
 - For MIG, the DCGM exporter typically exposes per-instance labels; we sum
   per-pod power series returned by the query.
"""

import argparse
import csv
import json
import os
import signal
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# Prometheus query candidates for DCGM power metrics.
# Order matters; the first that returns data is used.
PROM_QUERIES = [
    'sum(DCGM_FI_DEV_POWER_USAGE{namespace="{ns}",pod=~"{pod_re}"})',
    'sum(nvidia_dcgm_power_usage_watts{namespace="{ns}",pod=~"{pod_re}"})',
    'sum(nvidia_gpu_power_watts{namespace="{ns}",pod=~"{pod_re}"})',
]


def now_s() -> float:
    """Current UNIX timestamp in seconds (float)."""
    return time.time()


def http_get_json(url: str, timeout: int = 10) -> Dict[str, Any]:
    """HTTP GET and JSON-decode the response body."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def prom_instant_query(prom_url: str, query: str) -> Optional[float]:
    """Execute an instant vector query and return average value (if any)."""
    url = (
        urllib.parse.urljoin(prom_url, "/api/v1/query")
        + "?"
        + urllib.parse.urlencode({"query": query})
    )
    try:
        data = http_get_json(url)
        result = data.get("data", {}).get("result", [])
        if not result:
            return None
        # Sum should yield one vector sample; handle multiple just in case
        vals = []
        for series in result:
            v = series.get("value", [None, None])[1]
            if v is not None:
                try:
                    vals.append(float(v))
                except Exception:
                    pass
        if not vals:
            return None
        return sum(vals) / len(vals)
    except Exception:
        return None


def get_predictor_pod_regex(service_name: str) -> str:
    """Regex for KServe predictor pods (e.g., <isvc>-predictor-.*)."""
    return f"{service_name}-predictor-.*"


def read_requests_csv(req_csv: str) -> List[dict]:
    """Read requests.csv and coerce numeric fields, returning row dicts."""
    rows: List[dict] = []
    with open(req_csv, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                row["start_ms"] = float(row.get("start_ms", 0) or 0)
                row["latency_ms"] = float(row.get("latency_ms", 0) or 0)
                # tokens optional
                for tk in ("total_tokens", "completion_tokens"):
                    if tk in row and row[tk] not in (None, "", "NaN"):
                        row[tk] = float(row[tk])
            except Exception:
                pass
            rows.append(row)
    return rows


def run_window_bounds(rows: List[dict]) -> Tuple[float, float]:
    """Start and end (seconds) from per-request start_ms+latency_ms fields."""
    if not rows:
        return (0.0, 0.0)
    start = min(r.get("start_ms", 0.0) for r in rows) / 1000.0
    end = (
        max((r.get("start_ms", 0.0) + r.get("latency_ms", 0.0)) for r in rows) / 1000.0
    )
    return start, end


@dataclass
class PowerSample:
    """One power sample at timestamp `ts` with value `watts` (or None)."""

    ts: float
    watts: Optional[float]


def trapezoidal_wh(samples: List[PowerSample], t0: float, t1: float) -> float:
    """Integrate power (W) over [t0, t1] using trapezoidal rule to get Wh."""
    if not samples or t1 <= t0:
        return 0.0
    # Clip to [t0, t1] and drop None
    ss = [s for s in samples if s.watts is not None and t0 <= s.ts <= t1]
    if len(ss) < 2:
        return 0.0
    ss.sort(key=lambda s: s.ts)
    wh = 0.0
    for i in range(len(ss) - 1):
        p0 = ss[i].watts or 0.0
        p1 = ss[i + 1].watts or 0.0
        dt_h = (ss[i + 1].ts - ss[i].ts) / 3600.0
        if dt_h > 0:
            wh += ((p0 + p1) / 2.0) * dt_h
    return wh


def load_power_samples(path: str) -> List[PowerSample]:
    """Load power samples JSON produced by `collect` mode."""
    with open(path) as f:
        data = json.load(f)
    samples: List[PowerSample] = []
    if isinstance(data, list):
        for item in data:
            samples.append(
                PowerSample(
                    ts=float(item.get("ts_s", item.get("ts", 0))),
                    watts=(
                        float(item["watts"]) if item.get("watts") is not None else None
                    ),
                )
            )
    elif isinstance(data, dict) and "samples" in data:
        for item in data["samples"]:
            samples.append(
                PowerSample(
                    ts=float(item.get("ts_s", item.get("ts", 0))),
                    watts=(
                        float(item["watts"]) if item.get("watts") is not None else None
                    ),
                )
            )
    return samples


def write_json(path: str, obj: Dict[str, Any]) -> None:
    """Write a JSON file with pretty indentation."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def merge_results(run_dir: str, fields: Dict[str, Any]) -> None:
    """Merge given fields into run_dir/results.json (create if missing)."""
    results_path = os.path.join(run_dir, "results.json")
    if os.path.exists(results_path):
        try:
            with open(results_path) as f:
                prev = json.load(f)
        except Exception:
            prev = {}
    else:
        prev = {}
    prev.update(fields)
    with open(results_path, "w") as f:
        json.dump(prev, f, indent=2)


def collect_power(args: argparse.Namespace) -> int:
    """Collect DCGM power via Prometheus at interval for duration, write JSON."""
    prom_url = args.prom_url
    if not prom_url:
        print("ERROR: --prom-url is required for collect", file=sys.stderr)
        return 2

    pod_re = get_predictor_pod_regex(args.service)
    queries = [q.format(ns=args.namespace, pod_re=pod_re) for q in PROM_QUERIES]

    samples: List[PowerSample] = []
    stop = False

    def _sigint(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _sigint)

    start_ts = now_s()
    duration = float(args.duration) if args.duration else 0.0
    interval = max(0.5, float(args.interval or 1.0))

    while True:
        ts = now_s()
        watts: Optional[float] = None
        for q in queries:
            watts = prom_instant_query(prom_url, q)
            if watts is not None:
                break
        samples.append(PowerSample(ts=ts, watts=watts))
        if args.verbose:
            print(json.dumps({"ts_s": ts, "watts": watts}))
        # Exit conditions
        if stop:
            break
        if duration and (ts - start_ts) >= duration:
            break
        # sleep until next interval
        time.sleep(interval)

    # Persist
    out = args.out
    if not out:
        print("ERROR: --out required to write power samples", file=sys.stderr)
        return 2
    write_json(out, {"samples": [s.__dict__ for s in samples], "interval_s": interval})
    print(f"Wrote power samples: {out} ({len(samples)} points)")
    return 0


def integrate_energy(args: argparse.Namespace) -> int:
    """Integrate Wh over benchmark window (or full span) and emit energy.json."""
    run_dir = args.run_dir
    req_csv = os.path.join(run_dir, "requests.csv")
    power_path = args.power or os.path.join(run_dir, "power.json")
    energy_out = os.path.join(run_dir, "energy.json")

    if not os.path.exists(req_csv):
        print(f"ERROR: requests.csv not found at {req_csv}", file=sys.stderr)
        return 2
    if not os.path.exists(power_path):
        print(
            f"WARNING: power.json not found at {power_path}; energy fields will be null",
            file=sys.stderr,
        )
        energy = {
            "Wh_active": None,
            "Wh_idle_tax": None,
            "Wh_per_1k_tokens_active": None,
            "Wh_per_request_active": None,
            "warnings": ["Missing power samples"],
        }
        write_json(energy_out, energy)
        if args.merge_results:
            merge_results(
                run_dir,
                {
                    "energy_wh_active": None,
                    "energy_wh_idle_tax": None,
                    "energy_wh_per_1k_tokens": None,
                    "energy_wh_per_request": None,
                },
            )
        return 0

    rows = read_requests_csv(req_csv)
    t0, t1 = run_window_bounds(rows)
    if args.include_warmup:
        # Integrate over full sample span instead
        pass
    samples = load_power_samples(power_path)

    # Determine integration window
    if args.include_warmup:
        if samples:
            t0 = min(s.ts for s in samples)
            t1 = max(s.ts for s in samples)
    if t1 <= t0:
        print("ERROR: Invalid integration window", file=sys.stderr)
        return 2

    wh_active = trapezoidal_wh(samples, t0, t1)

    # Idle tax options
    wh_idle_tax: Optional[float] = None
    idle_mode = args.idle_tax
    if idle_mode == "series":
        # Energy outside the active window
        if samples:
            smin = min(s.ts for s in samples)
            smax = max(s.ts for s in samples)
            if smin < t0:
                wh_before = trapezoidal_wh(samples, smin, min(t0, smax))
            else:
                wh_before = 0.0
            if smax > t1:
                wh_after = trapezoidal_wh(samples, max(smin, t1), smax)
            else:
                wh_after = 0.0
            wh_idle_tax = wh_before + wh_after
    elif idle_mode == "baseline":
        # Use median power outside active window as baseline P_idle
        outside_vals: List[float] = []
        for s in samples:
            if s.watts is None:
                continue
            if s.ts < t0 or s.ts > t1:
                outside_vals.append(s.watts)
        if outside_vals:
            p_idle = sorted(outside_vals)[len(outside_vals) // 2]
            idle_dur_h = 0.0
            # idle time = sum outside durations approximated by sample spacing
            # Use average sample step
            if len(samples) > 1:
                steps = [
                    samples[i + 1].ts - samples[i].ts for i in range(len(samples) - 1)
                ]
                avg_step = sum(steps) / len(steps)
            else:
                avg_step = t1 - t0
            # Count samples outside window and multiply by avg step
            n_out = len([s for s in samples if (s.ts < t0 or s.ts > t1)])
            idle_dur_h = (n_out * avg_step) / 3600.0
            wh_idle_tax = p_idle * idle_dur_h

    # Totals for normalization
    success = sum(1 for r in rows if str(int(r.get("status", 0))) == "200")
    total_tokens = sum(
        (r.get("total_tokens", 0.0) or 0.0)
        for r in rows
        if str(int(r.get("status", 0))) == "200"
    )

    energy = {
        "Wh_active": wh_active,
        "Wh_idle_tax": wh_idle_tax,
        "Wh_per_1k_tokens_active": (
            ((wh_active / total_tokens) * 1000.0) if total_tokens > 0 else None
        ),
        "Wh_per_request_active": (wh_active / success) if success > 0 else None,
        "window": {"start": t0, "end": t1},
        "samples": os.path.basename(power_path),
    }
    write_json(energy_out, energy)
    print(json.dumps(energy, indent=2))

    if args.merge_results:
        merge_results(
            run_dir,
            {
                "energy_wh_active": energy["Wh_active"],
                "energy_wh_idle_tax": energy["Wh_idle_tax"],
                "energy_wh_per_1k_tokens": energy["Wh_per_1k_tokens_active"],
                "energy_wh_per_request": energy["Wh_per_request_active"],
            },
        )
        print(f"Merged energy fields into {os.path.join(run_dir, 'results.json')}")
    return 0


def main() -> int:
    """CLI for collecting power samples and integrating energy usage."""
    ap = argparse.ArgumentParser(description="Energy collector and integrator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_collect = sub.add_parser(
        "collect", help="Collect DCGM power samples via Prometheus"
    )
    ap_collect.add_argument("--namespace", required=True)
    ap_collect.add_argument("--service", required=True)
    ap_collect.add_argument("--prom-url", required=True)
    ap_collect.add_argument(
        "--interval", type=float, default=1.0, help="Sampling interval seconds"
    )
    ap_collect.add_argument(
        "--duration", type=float, default=0.0, help="Duration seconds (0=until Ctrl-C)"
    )
    ap_collect.add_argument(
        "--out", required=True, help="Output path for power samples JSON"
    )
    ap_collect.add_argument("--verbose", action="store_true")

    ap_integrate = sub.add_parser(
        "integrate", help="Integrate Wh aligned to benchmark window"
    )
    ap_integrate.add_argument(
        "--run-dir", required=True, help="Run directory containing requests.csv"
    )
    ap_integrate.add_argument(
        "--power", help="Path to power samples JSON (default: run-dir/power.json)"
    )
    ap_integrate.add_argument(
        "--include-warmup",
        action="store_true",
        help="Integrate across full sample span",
    )
    ap_integrate.add_argument(
        "--idle-tax", choices=["baseline", "series"], default=None
    )
    ap_integrate.add_argument(
        "--merge-results",
        action="store_true",
        help="Merge energy fields into results.json",
    )

    args = ap.parse_args()

    if args.cmd == "collect":
        return collect_power(args)
    elif args.cmd == "integrate":
        return integrate_energy(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
