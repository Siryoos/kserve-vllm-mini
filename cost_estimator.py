#!/usr/bin/env python3
"""
Cost estimator for kserve-vllm-mini

Computes:
- cost_per_request
- cost_per_1k_tokens

Inputs:
- requests.csv from a run directory (created by loadtest)
- cost.yaml with unit pricing
- Kubernetes metadata (kubectl) to discover pods, resources, and GPU type

Usage:
  python cost_estimator.py \
    --run-dir runs/2025-01-01_12-00-00 \
    --namespace ml-prod \
    --service demo-llm \
    --cost-file cost.yaml

Outputs:
- Updates/creates results.json in run dir with cost fields
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:
    print("ERROR: Missing 'pyyaml'. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def run(cmd: List[str]) -> str:
    """Run a shell command and return stdout as text (raises on failure)."""
    return subprocess.check_output(cmd, text=True)


def parse_k8s_quantity(q: Optional[str]) -> float:
    """Convert Kubernetes resource quantity to float cores or bytes.
    - CPU: returns cores (e.g., '500m' -> 0.5, '2' -> 2.0)
    - Memory: returns bytes (e.g., '512Mi' -> 536870912)
    """
    if not q:
        return 0.0
    # CPU (m or plain)
    if q.endswith("m"):
        return float(q[:-1]) / 1000.0
    # Memory units
    suffixes = {
        "Ei": 2**60,
        "Pi": 2**50,
        "Ti": 2**40,
        "Gi": 2**30,
        "Mi": 2**20,
        "Ki": 2**10,
        "E": 10**18,
        "P": 10**15,
        "T": 10**12,
        "G": 10**9,
        "M": 10**6,
        "K": 10**3,
    }
    for suf, mult in suffixes.items():
        if q.endswith(suf):
            base = float(q[: -len(suf)])
            # If Gi/Mi/Ki -> bytes; otherwise assume decimal bytes
            return base * mult
    # No suffix: number -> CPU cores or bytes; assume cores if < 1000
    try:
        val = float(q)
        return val
    except Exception:
        return 0.0


def read_requests_csv(path: str) -> Tuple[List[dict], float, float, int, int]:
    """Read requests.csv and return (rows, start_ts, end_ts, success, total)."""
    rows: List[dict] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Convert numeric fields
            for k in [
                "start_ms",
                "ttfb_ms",
                "latency_ms",
                "status",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
            ]:
                if k in r and r[k] not in (None, "", "NaN"):
                    try:
                        r[k] = float(r[k])
                    except Exception:
                        pass
            # Handle cold start classification
            if "is_cold_start" in r:
                r["is_cold_start"] = r["is_cold_start"] in ("True", "true", "1", True)
            else:
                r["is_cold_start"] = False
            rows.append(r)

    if not rows:
        raise SystemExit("No rows in requests.csv")

    start = min(r.get("start_ms", 0.0) for r in rows) / 1000.0
    end = (
        max((r.get("start_ms", 0.0) + r.get("latency_ms", 0.0)) for r in rows) / 1000.0
    )
    start_ts = start
    end_ts = end
    success = sum(1 for r in rows if str(int(r.get("status", 0))) == "200")
    total = len(rows)
    return rows, start_ts, end_ts, success, total


@dataclass
class UnitPricing:
    """Unit prices and knobs used for cost calculation."""

    gpu_default: float
    gpu_map: Dict[str, float]
    cpu_per_core_hr: float
    mem_per_gib_hr: float
    overhead_fraction: float
    use_requests: bool
    include_sidecars: bool


def load_pricing(path: str) -> UnitPricing:
    """Load pricing YAML into a UnitPricing structure."""
    with open(path) as f:
        data = yaml.safe_load(f)
    gpu_map = data.get("gpu", {}) or {}
    return UnitPricing(
        gpu_default=float(gpu_map.get("default", 1.50)),
        gpu_map={k: float(v) for k, v in gpu_map.items() if k != "default"},
        cpu_per_core_hr=float(data.get("cpu", {}).get("hourly_per_core", 0.04)),
        mem_per_gib_hr=float(data.get("memory", {}).get("hourly_per_gib", 0.005)),
        overhead_fraction=float(data.get("overhead", {}).get("fraction", 0.10)),
        use_requests=bool(data.get("calculation", {}).get("use_requests", True)),
        include_sidecars=bool(
            data.get("calculation", {}).get("include_sidecars", False)
        ),
    )


def get_isvc_pods(namespace: str, service: str) -> dict:
    """Return JSON of pods belonging to the given InferenceService."""
    out = run(
        [
            "kubectl",
            "get",
            "pods",
            "-n",
            namespace,
            "-l",
            f"serving.kserve.io/inferenceservice={service}",
            "-o",
            "json",
        ]
    )
    return json.loads(out)


def node_gpu_label_of_pod(namespace: str, pod: str) -> Optional[str]:
    """Look up the node's GPU product label for the given pod, if any."""
    try:
        pod_json = json.loads(
            run(["kubectl", "get", "pod", pod, "-n", namespace, "-o", "json"])
        )
        node = pod_json["spec"].get("nodeName")
        if not node:
            return None
        node_json = json.loads(run(["kubectl", "get", "node", node, "-o", "json"]))
        labels = node_json.get("metadata", {}).get("labels", {})
        # Common GPU product labels
        for key in [
            "nvidia.com/gpu.product",
            "nvidia.com/gpu.product.name",
            "nvidia.com/gpu.family",
        ]:
            if key in labels:
                return labels[key]
    except Exception:
        return None
    return None


def pick_gpu_cost(pricing: UnitPricing, product_label: Optional[str]) -> float:
    """Choose hourly GPU price from map using best-effort label matching."""
    if not product_label:
        return pricing.gpu_default
    # Try exact match, then normalized token match
    if product_label in pricing.gpu_map:
        return pricing.gpu_map[product_label]
    tokens = re.split(r"[^A-Za-z0-9]+", product_label)
    key = "-".join(t for t in tokens if t)
    for k, v in pricing.gpu_map.items():
        if key.lower() in k.lower() or k.lower() in key.lower():
            return v
    return pricing.gpu_default


def container_resources(
    container: dict, use_requests: bool
) -> Tuple[float, float, float]:
    """Return (cpu_cores, mem_gib, gpus) for a container."""
    rs = container.get("resources", {})
    which = rs.get("requests" if use_requests else "limits", {}) or {}
    cpu_cores = parse_k8s_quantity(which.get("cpu"))
    mem_bytes = parse_k8s_quantity(which.get("memory"))
    mem_gib = mem_bytes / (2**30) if mem_bytes else 0.0
    # GPU often only in limits, fallback to limits if requests lacks it
    gpus = 0.0
    for scope in [which, rs.get("limits", {}) or {}]:
        val = scope.get("nvidia.com/gpu")
        if val:
            try:
                gpus = float(val)
                break
            except Exception:
                pass
    return cpu_cores, mem_gib, gpus


def collect_pod_resource_profiles(
    pods_json: dict, use_requests: bool, include_sidecars: bool
) -> List[dict]:
    """Summarize requested/limited resources per container across pods."""
    profiles: List[dict] = []
    items = pods_json.get("items", [])
    for p in items:
        pod = p["metadata"]["name"]
        ns = p["metadata"]["namespace"]
        product_label = node_gpu_label_of_pod(ns, pod)
        containers = p["spec"].get("containers", [])
        for c in containers:
            name = c.get("name")
            if not include_sidecars and name in ("queue-proxy", "istio-proxy"):
                continue
            cpu, mem_gib, gpus = container_resources(c, use_requests)
            profiles.append(
                {
                    "pod": pod,
                    "container": name,
                    "node_gpu_label": product_label,
                    "cpu": cpu,
                    "mem_gib": mem_gib,
                    "gpus": gpus,
                }
            )
    return profiles


def container_start_end(
    pod_status: dict,
) -> Tuple[Optional[dt.datetime], Optional[dt.datetime]]:
    """Infer earliest start and latest end timestamps from container statuses."""
    start: Optional[dt.datetime] = None
    end: Optional[dt.datetime] = None
    statuses = pod_status.get("containerStatuses", [])
    for s in statuses:
        st = s.get("state", {})
        running = st.get("running", {})
        terminated = st.get("terminated", {})
        if running.get("startedAt"):
            t = dt.datetime.fromisoformat(running["startedAt"].replace("Z", "+00:00"))
            start = min(start, t) if start else t
        if terminated.get("finishedAt"):
            t2 = dt.datetime.fromisoformat(
                terminated["finishedAt"].replace("Z", "+00:00")
            )
            end = max(end, t2) if end else t2
    return start, end


def calculate_cold_warm_costs(
    rows: List[dict], total_cost: float, success: int, total_tokens: float
) -> Dict[str, Optional[float]]:
    """Calculate separate cost metrics for cold and warm requests."""
    cold_rows = [
        r
        for r in rows
        if r.get("is_cold_start", False) and str(int(r.get("status", 0))) == "200"
    ]
    warm_rows = [
        r
        for r in rows
        if not r.get("is_cold_start", False) and str(int(r.get("status", 0))) == "200"
    ]

    cold_count = len(cold_rows)
    warm_count = len(warm_rows)

    cold_tokens = sum(float(r.get("total_tokens", 0.0) or 0.0) for r in cold_rows)
    warm_tokens = sum(float(r.get("total_tokens", 0.0) or 0.0) for r in warm_rows)

    # Simple cost allocation based on request count (could be improved with time-based allocation)
    if success > 0:
        cold_cost_fraction = cold_count / success
        warm_cost_fraction = warm_count / success
    else:
        cold_cost_fraction = 0
        warm_cost_fraction = 0

    cold_total_cost = total_cost * cold_cost_fraction
    warm_total_cost = total_cost * warm_cost_fraction

    return {
        "cold_cost_per_request": (
            (cold_total_cost / cold_count) if cold_count > 0 else None
        ),
        "warm_cost_per_request": (
            (warm_total_cost / warm_count) if warm_count > 0 else None
        ),
        "cold_cost_per_1k_tokens": (
            (cold_total_cost / cold_tokens * 1000.0) if cold_tokens > 0 else None
        ),
        "warm_cost_per_1k_tokens": (
            (warm_total_cost / warm_tokens * 1000.0) if warm_tokens > 0 else None
        ),
        "cold_total_cost": cold_total_cost,
        "warm_total_cost": warm_total_cost,
        "cold_requests": cold_count,
        "warm_requests": warm_count,
        "cold_tokens": cold_tokens,
        "warm_tokens": warm_tokens,
    }


def sum_resource_seconds(
    pods_json: dict, window_start: float, window_end: float
) -> Dict[str, float]:
    """Return approximate total resource-seconds across pods in window.
    Keys: cpu_core_seconds, mem_gib_seconds, gpu_seconds
    """
    w0 = dt.datetime.fromtimestamp(window_start, tz=dt.timezone.utc)
    w1 = dt.datetime.fromtimestamp(window_end, tz=dt.timezone.utc)

    cpu_core_seconds = 0.0
    mem_gib_seconds = 0.2
    gpu_seconds = 0.0

    for p in pods_json.get("items", []):
        spec = p.get("spec", {})
        status = p.get("status", {})
        containers = spec.get("containers", [])
        cstats = status.get("containerStatuses", [])
        # Build name->resources map
        res_map = {c.get("name"): c for c in containers}

        # Pod active interval
        pst, pend = container_start_end(status)
        # If no container info, use pod startTime
        if not pst and status.get("startTime"):
            pst = dt.datetime.fromisoformat(status["startTime"].replace("Z", "+00:00"))
        # If pod still running, set end to window end
        if not pend:
            pend = w1

        if not pst or not pend:
            continue
        # Overlap with window
        start = max(pst, w0)
        end = min(pend, w1)
        if end <= start:
            continue
        seconds = (end - start).total_seconds()

        for s in cstats:
            name = s.get("name")
            cdef = res_map.get(name, {})
            cpu, mem_gib, gpus = container_resources(cdef, use_requests=True)
            # Count inference container more prominently if named
            # Otherwise sum all containers (sidecars included)
            cpu_core_seconds += cpu * seconds
            mem_gib_seconds += mem_gib * seconds
            gpu_seconds += gpus * seconds

    return {
        "cpu_core_seconds": cpu_core_seconds,
        "mem_gib_seconds": mem_gib_seconds,
        "gpu_seconds": gpu_seconds,
    }


def main() -> None:
    """CLI: compute cost metrics for a run and merge into results.json."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--service", required=True)
    ap.add_argument("--cost-file", default="cost.yaml")
    args = ap.parse_args()

    run_dir = args.run_dir
    # Try classified CSV first (from analyzer), then fall back to original
    req_csv = os.path.join(run_dir, "requests_classified.csv")
    if not os.path.exists(req_csv):
        req_csv = os.path.join(run_dir, "requests.csv")
    if not os.path.exists(req_csv):
        print(f"ERROR: {req_csv} not found", file=sys.stderr)
        sys.exit(1)

    rows, start_ts, end_ts, success, total = read_requests_csv(req_csv)
    total_tokens = sum(
        float(r.get("total_tokens", 0.0) or 0.0)
        for r in rows
        if str(int(r.get("status", 0))) == "200"
    )

    pricing = load_pricing(args.cost_file)

    pods_json = get_isvc_pods(args.namespace, args.service)
    # Resource-seconds across all pods over window
    rsecs = sum_resource_seconds(pods_json, start_ts, end_ts)

    # Determine GPU product from any pod
    product_label = None
    items = pods_json.get("items", [])
    if items:
        p0 = items[0]["metadata"]["name"]
        product_label = node_gpu_label_of_pod(args.namespace, p0)

    gpu_hr = pick_gpu_cost(pricing, product_label)
    cpu_hr = pricing.cpu_per_core_hr
    mem_hr = pricing.mem_per_gib_hr

    total_cost = (
        (rsecs["gpu_seconds"] * (gpu_hr / 3600.0))
        + (rsecs["cpu_core_seconds"] * (cpu_hr / 3600.0))
        + (rsecs["mem_gib_seconds"] * (mem_hr / 3600.0))
    )
    total_cost *= 1.0 + pricing.overhead_fraction

    cost_per_request = (total_cost / success) if success > 0 else None
    cost_per_1k_tokens = (
        (total_cost / total_tokens * 1000.0) if total_tokens > 0 else None
    )

    # Calculate cold/warm cost breakdown
    cold_warm_costs = calculate_cold_warm_costs(rows, total_cost, success, total_tokens)

    # Update results.json
    results_path = os.path.join(run_dir, "results.json")
    results = {}
    if os.path.exists(results_path):
        with open(results_path) as f:
            try:
                results = json.load(f)
            except Exception:
                results = {}
    results.update(
        {
            "cost_per_request": cost_per_request,
            "cost_per_1k_tokens": cost_per_1k_tokens,
            **cold_warm_costs,
            "cost_breakdown": {
                "total_cost": total_cost,
                "gpu_seconds": rsecs["gpu_seconds"],
                "cpu_core_seconds": rsecs["cpu_core_seconds"],
                "mem_gib_seconds": rsecs["mem_gib_seconds"],
                "gpu_hourly": gpu_hr,
                "cpu_hourly_per_core": cpu_hr,
                "mem_hourly_per_gib": mem_hr,
                "overhead_fraction": pricing.overhead_fraction,
                "gpu_product_label": product_label,
            },
        }
    )
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    output_summary = {
        "cost_per_request": cost_per_request,
        "cost_per_1k_tokens": cost_per_1k_tokens,
        "cold_cost_per_request": cold_warm_costs.get("cold_cost_per_request"),
        "warm_cost_per_request": cold_warm_costs.get("warm_cost_per_request"),
        "cold_cost_per_1k_tokens": cold_warm_costs.get("cold_cost_per_1k_tokens"),
        "warm_cost_per_1k_tokens": cold_warm_costs.get("warm_cost_per_1k_tokens"),
        "cold_vs_warm_multiplier": (
            cold_warm_costs.get("cold_cost_per_request")
            / cold_warm_costs.get("warm_cost_per_request")
            if cold_warm_costs.get("cold_cost_per_request")
            and cold_warm_costs.get("warm_cost_per_request")
            else None
        ),
    }
    print(json.dumps(output_summary, indent=2))


if __name__ == "__main__":
    main()
