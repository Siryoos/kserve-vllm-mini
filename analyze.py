#!/usr/bin/env python3
"""
Analyze a run directory produced by loadtest to compute latency, throughput,
error rate, tokens/sec, cold starts, and utilization metrics (optional via Prometheus),
and emit a results.json file for reporting and comparisons.

Usage:
  python analyze.py \
    --run-dir runs/2025-01-01_12-00-00 \
    --namespace ml-prod \
    --service demo-llm \
    [--prom-url http://prometheus.kube-system:9090]
"""

import argparse
import csv
import datetime as dt
import json
import math
import os
import statistics as stats
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

import urllib.parse
import urllib.request


def run(cmd: List[str]) -> str:
    return subprocess.check_output(cmd, text=True)


def read_requests_csv(path: str) -> List[dict]:
    rows: List[dict] = []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            for k in ["start_ms", "ttfb_ms", "latency_ms", "status", "prompt_tokens", "completion_tokens", "total_tokens"]:
                if k in row and row[k] not in (None, "", "NaN"):
                    try:
                        row[k] = float(row[k])
                    except Exception:
                        pass
            rows.append(row)
    return rows


def percentile(arr: List[float], p: float) -> float:
    if not arr:
        return float("nan")
    arr_sorted = sorted(arr)
    k = max(0, min(len(arr_sorted) - 1, int(math.floor(p * len(arr_sorted)))))
    return arr_sorted[k]


def window_bounds(rows: List[dict]) -> Tuple[float, float]:
    start = min(r.get("start_ms", 0.0) for r in rows) / 1000.0
    end = max((r.get("start_ms", 0.0) + r.get("latency_ms", 0.0)) for r in rows) / 1000.0
    return start, end


def prom_query(prom_url: str, query: str, start: Optional[float] = None, end: Optional[float] = None, step: Optional[int] = None) -> Dict[str, Any]:
    if start is not None and end is not None and step is not None:
        endpoint = "/api/v1/query_range"
        params = {"query": query, "start": str(start), "end": str(end), "step": str(step)}
    else:
        endpoint = "/api/v1/query"
        params = {"query": query}
    url = urllib.parse.urljoin(prom_url, endpoint) + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read())
        return data


def prom_vector_avg(result: Dict[str, Any]) -> Optional[float]:
    try:
        res = result["data"]["result"]
        if not res:
            return None
        vals = [float(s["value"][1]) for s in res]
        if not vals:
            return None
        return sum(vals) / len(vals)
    except Exception:
        return None


def prom_matrix_timeavg(result: Dict[str, Any]) -> Optional[float]:
    try:
        res = result["data"]["result"]
        if not res:
            return None
        pts: List[float] = []
        for series in res:
            for t, v in series.get("values", []):
                pts.append(float(v))
        if not pts:
            return None
        return sum(pts) / len(pts)
    except Exception:
        return None


def utilization_from_prom(prom_url: str, namespace: str, isvc: str, start: float, end: float) -> Dict[str, Optional[float]]:
    # Window
    step = max(5, int((end - start) / 60))  # ~60pts
    window = int(end - start)
    dur = f"{window}s"
    # Pod name prefix used by KServe/Knative for predictor pods
    pod_re = f"{isvc}-predictor-.*"

    # GPU util (DCGM) attempts
    gpu_queries = [
        f'avg_over_time(DCGM_FI_DEV_GPU_UTIL{{namespace="{namespace}",pod=~"{pod_re}"}}[{dur}])',
        f'avg_over_time(nvidia_dcgm_gpu_utilization{{namespace="{namespace}",pod=~"{pod_re}"}}[{dur}])',
        f'avg_over_time(nvidia_gpu_utilization{{namespace="{namespace}",pod=~"{pod_re}"}}[{dur}])',
    ]
    gpu_util = None
    for q in gpu_queries:
        gpu_util = prom_vector_avg(prom_query(prom_url, q))
        if gpu_util is not None:
            break

    # GPU memory used (bytes)
    gpu_mem_queries = [
        f'avg_over_time(DCGM_FI_DEV_FB_USED{{namespace="{namespace}",pod=~"{pod_re}"}}[{dur}])',
        f'avg_over_time(nvidia_dcgm_fb_used_bytes{{namespace="{namespace}",pod=~"{pod_re}"}}[{dur}])',
    ]
    gpu_mem = None
    for q in gpu_mem_queries:
        gpu_mem = prom_vector_avg(prom_query(prom_url, q))
        if gpu_mem is not None:
            break

    # CPU utilization (cores)
    cpu_q = (
        f'avg(rate(container_cpu_usage_seconds_total{{namespace="{namespace}",pod=~"{pod_re}",container!="",container!="POD"}}[2m]))'
    )
    cpu_cores = prom_vector_avg(prom_query(prom_url, cpu_q, start, end, step))

    # Memory working set (bytes)
    mem_q = (
        f'avg(container_memory_working_set_bytes{{namespace="{namespace}",pod=~"{pod_re}",container!="",container!="POD"}})'
    )
    mem_bytes = prom_vector_avg(prom_query(prom_url, mem_q, start, end, step))

    return {
        "gpu_util_avg": gpu_util,
        "gpu_mem_used_avg": gpu_mem,
        "cpu_util_avg": cpu_cores,  # cores
        "mem_used_avg": mem_bytes,   # bytes
    }


def cold_start_count(namespace: str, isvc: str, start: float, end: float) -> int:
    try:
        out = run([
            "kubectl", "get", "pods", "-n", namespace,
            "-l", f"serving.kserve.io/inferenceservice={isvc}",
            "-o", "json",
        ])
        podlist = json.loads(out)
    except Exception:
        return 0
    t0 = dt.datetime.fromtimestamp(start, tz=dt.timezone.utc)
    t1 = dt.datetime.fromtimestamp(end, tz=dt.timezone.utc)
    cold = 0
    for p in podlist.get("items", []):
        status = p.get("status", {})
        # If any container started during window, treat as cold-start event
        for cs in status.get("containerStatuses", []):
            st = cs.get("state", {}).get("running", {})
            if st.get("startedAt"):
                ts = dt.datetime.fromisoformat(st["startedAt"].replace("Z", "+00:00"))
                if t0 <= ts <= t1:
                    cold += 1
                    break
    return cold


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--service", required=True)
    ap.add_argument("--prom-url", default=None)
    args = ap.parse_args()

    req_csv = os.path.join(args.run_dir, "requests.csv")
    rows = read_requests_csv(req_csv)
    if not rows:
        print("No request rows found", file=sys.stderr)
        sys.exit(1)

    lats = [r.get("latency_ms", float("nan")) for r in rows if str(int(r.get("status", 0))) == "200"]
    ttfs = [r.get("ttfb_ms", float("nan")) for r in rows if str(int(r.get("status", 0))) == "200" and not math.isnan(r.get("ttfb_ms", float("nan")))]
    start, end = window_bounds(rows)

    success = sum(1 for r in rows if str(int(r.get("status", 0))) == "200")
    total = len(rows)
    error_rate = (total - success) / total if total else None
    duration = end - start if end > start else None
    throughput = (success / duration) if duration and duration > 0 else None

    completion_tokens = [r.get("completion_tokens", 0.0) or 0.0 for r in rows if str(int(r.get("status", 0))) == "200"]
    total_tokens = sum((r.get("total_tokens", 0.0) or 0.0) for r in rows if str(int(r.get("status", 0))) == "200")
    tokens_per_sec = (sum(completion_tokens) / duration) if duration and duration > 0 else None

    util = {"gpu_util_avg": None, "gpu_mem_used_avg": None, "cpu_util_avg": None, "mem_used_avg": None}
    if args.prom_url:
        try:
            util = utilization_from_prom(args.prom_url, args.namespace, args.service, start, end)
        except Exception as e:
            print(f"Prometheus query failed: {e}", file=sys.stderr)

    cold_starts = cold_start_count(args.namespace, args.service, start, end)

    results = {
        "p50_ms": percentile(lats, 0.50),
        "p95_ms": percentile(lats, 0.95),
        "throughput_rps": throughput,
        "tokens_per_sec": tokens_per_sec,
        "error_rate": error_rate,
        "cold_start_count": cold_starts,
        "time_to_first_token_ms": stats.mean(ttfs) if ttfs else None,
        **util,
        "window": {"start": start, "end": end, "seconds": duration},
        "requests": {"total": total, "success": success},
    }

    out_path = os.path.join(args.run_dir, "results.json")
    # Merge if exists
    if os.path.exists(out_path):
        try:
            with open(out_path) as f:
                prev = json.load(f)
            prev.update(results)
            results = prev
        except Exception:
            pass
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

