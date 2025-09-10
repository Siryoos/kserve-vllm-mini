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
            for k in ["start_ms", "ttfb_ms", "tllt_ms", "latency_ms", "status", "prompt_tokens", "completion_tokens", "total_tokens"]:
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


def compute_histograms(data: List[float], num_bins: int = 20) -> Dict[str, Any]:
    """Compute histogram data for timing analysis."""
    if not data:
        return {"bins": [], "counts": [], "bin_edges": []}
    
    data_clean = [x for x in data if not math.isnan(x)]
    if not data_clean:
        return {"bins": [], "counts": [], "bin_edges": []}
    
    min_val = min(data_clean)
    max_val = max(data_clean)
    
    if min_val == max_val:
        return {"bins": [min_val], "counts": [len(data_clean)], "bin_edges": [min_val, max_val]}
    
    # Create histogram bins
    bin_width = (max_val - min_val) / num_bins
    bin_edges = [min_val + i * bin_width for i in range(num_bins + 1)]
    bin_counts = [0] * num_bins
    
    for val in data_clean:
        # Find appropriate bin
        bin_idx = min(num_bins - 1, int((val - min_val) / bin_width))
        bin_counts[bin_idx] += 1
    
    bin_centers = [(bin_edges[i] + bin_edges[i + 1]) / 2 for i in range(num_bins)]
    
    return {
        "bins": bin_centers,
        "counts": bin_counts,
        "bin_edges": bin_edges,
        "min": min_val,
        "max": max_val,
        "total_samples": len(data_clean)
    }


def compute_token_timing_analysis(rows: List[dict]) -> Dict[str, Any]:
    """Analyze per-token timing patterns."""
    success_rows = [r for r in rows if str(int(r.get("status", 0))) == "200"]
    
    # Extract timing data
    ttfb_times = [r.get("ttfb_ms", float("nan")) for r in success_rows]
    tllt_times = [r.get("tllt_ms", float("nan")) for r in success_rows]
    total_times = [r.get("latency_ms", float("nan")) for r in success_rows]
    completion_tokens = [r.get("completion_tokens", 0) or 0 for r in success_rows]
    
    # Calculate per-token generation time (TLLT - TTFB)
    generation_times = []
    per_token_times = []
    
    for i, row in enumerate(success_rows):
        ttfb = ttfb_times[i]
        tllt = tllt_times[i] 
        tokens = completion_tokens[i]
        
        if not math.isnan(ttfb) and not math.isnan(tllt) and tokens > 0:
            gen_time = tllt - ttfb
            generation_times.append(gen_time)
            per_token_times.append(gen_time / tokens)  # ms per token
    
    # Compute histograms
    ttfb_hist = compute_histograms([x for x in ttfb_times if not math.isnan(x)])
    tllt_hist = compute_histograms([x for x in tllt_times if not math.isnan(x)])
    generation_hist = compute_histograms(generation_times)
    per_token_hist = compute_histograms(per_token_times)
    
    return {
        "ttfb_histogram": ttfb_hist,
        "tllt_histogram": tllt_hist,
        "generation_time_histogram": generation_hist,
        "per_token_time_histogram": per_token_hist,
        "ttfb_p50_ms": percentile(ttfb_times, 0.50) if ttfb_times else None,
        "ttfb_p95_ms": percentile(ttfb_times, 0.95) if ttfb_times else None,
        "ttfb_p99_ms": percentile(ttfb_times, 0.99) if ttfb_times else None,
        "tllt_p50_ms": percentile(tllt_times, 0.50) if tllt_times else None,
        "tllt_p95_ms": percentile(tllt_times, 0.95) if tllt_times else None,
        "tllt_p99_ms": percentile(tllt_times, 0.99) if tllt_times else None,
        "generation_p50_ms": percentile(generation_times, 0.50) if generation_times else None,
        "generation_p95_ms": percentile(generation_times, 0.95) if generation_times else None,
        "per_token_p50_ms": percentile(per_token_times, 0.50) if per_token_times else None,
        "per_token_p95_ms": percentile(per_token_times, 0.95) if per_token_times else None,
        "avg_tokens_per_response": stats.mean(completion_tokens) if completion_tokens else None,
    }


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

    # GPU power consumption (watts)
    gpu_power_queries = [
        f'avg_over_time(DCGM_FI_DEV_POWER_USAGE{{namespace="{namespace}",pod=~"{pod_re}"}}[{dur}])',
        f'avg_over_time(nvidia_dcgm_power_usage_watts{{namespace="{namespace}",pod=~"{pod_re}"}}[{dur}])',
        f'avg_over_time(nvidia_gpu_power_watts{{namespace="{namespace}",pod=~"{pod_re}"}}[{dur}])',
    ]
    gpu_power_watts = None
    for q in gpu_power_queries:
        gpu_power_watts = prom_vector_avg(prom_query(prom_url, q))
        if gpu_power_watts is not None:
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
        "gpu_power_watts_avg": gpu_power_watts,
        "cpu_util_avg": cpu_cores,  # cores
        "mem_used_avg": mem_bytes,   # bytes
    }


def cache_hit_ratio(prom_url: Optional[str], namespace: str, isvc: str, start: float, end: float) -> Optional[float]:
    """Try to derive cache hit ratio from server metrics or logs."""
    # Try Prometheus metrics under several likely names
    if prom_url:
        dur = f"{int(end - start)}s"
        pod_re = f"{isvc}-predictor-.*"
        queries = [
            # ratio = hits / (hits+misses)
            f"sum(rate(vllm_prompt_cache_hits_total{{namespace=\"{namespace}\",pod=~\"{pod_re}\"}}[{dur}])) / sum(rate(vllm_prompt_cache_requests_total{{namespace=\"{namespace}\",pod=~\"{pod_re}\"}}[{dur}]))",
            f"sum(rate(vllm_cache_hits_total{{namespace=\"{namespace}\",pod=~\"{pod_re}\"}}[{dur}])) / (sum(rate(vllm_cache_hits_total{{namespace=\"{namespace}\",pod=~\"{pod_re}\"}}[{dur}])) + sum(rate(vllm_cache_misses_total{{namespace=\"{namespace}\",pod=~\"{pod_re}\"}}[{dur}])))",
        ]
        for q in queries:
            try:
                r = prom_query(prom_url, q)
                v = prom_vector_avg(r)
                if v is not None and v >= 0 and v <= 1:
                    return v
            except Exception:
                pass

    # Fallback: scan logs for cache hit/miss tokens
    try:
        out = run([
            "bash", "-lc",
            f"kubectl -n {namespace} logs -l serving.kserve.io/inferenceservice={isvc} --tail=200 | grep -i 'cache' || true"
        ])
        hits = 0
        misses = 0
        for line in out.splitlines():
            l = line.lower()
            if 'cache hit' in l: hits += 1
            if 'cache miss' in l: misses += 1
        if hits + misses > 0:
            return hits / (hits + misses)
    except Exception:
        pass
    return None


def get_cold_start_times(namespace: str, isvc: str, start: float, end: float) -> List[float]:
    """Get the times when pods started during the test window (cold starts)."""
    try:
        out = run([
            "kubectl", "get", "pods", "-n", namespace,
            "-l", f"serving.kserve.io/inferenceservice={isvc}",
            "-o", "json",
        ])
        podlist = json.loads(out)
    except Exception:
        return []
    
    t0 = dt.datetime.fromtimestamp(start, tz=dt.timezone.utc)
    t1 = dt.datetime.fromtimestamp(end, tz=dt.timezone.utc)
    cold_times = []
    
    for p in podlist.get("items", []):
        status = p.get("status", {})
        # If any container started during window, record the time
        for cs in status.get("containerStatuses", []):
            st = cs.get("state", {}).get("running", {})
            if st.get("startedAt"):
                ts = dt.datetime.fromisoformat(st["startedAt"].replace("Z", "+00:00"))
                if t0 <= ts <= t1:
                    cold_times.append(ts.timestamp())
                    break  # Only count one cold start per pod
    
    return sorted(cold_times)


def cold_start_count(namespace: str, isvc: str, start: float, end: float) -> int:
    return len(get_cold_start_times(namespace, isvc, start, end))


def classify_requests_cold_warm(rows: List[dict], cold_start_times: List[float], cold_window_sec: float = 30.0) -> List[dict]:
    """
    Classify requests as cold or warm based on proximity to cold start events.
    Requests within cold_window_sec after a cold start are marked as cold.
    """
    for row in rows:
        row['is_cold_start'] = False
        request_time = row.get('start_ms', 0) / 1000.0
        
        # Check if request falls within cold window of any cold start
        for cold_time in cold_start_times:
            if cold_time <= request_time <= cold_time + cold_window_sec:
                row['is_cold_start'] = True
                break
    
    return rows


def compute_cold_warm_metrics(rows: List[dict]) -> Dict[str, Any]:
    """Compute separate metrics for cold and warm requests."""
    cold_rows = [r for r in rows if r.get('is_cold_start', False)]
    warm_rows = [r for r in rows if not r.get('is_cold_start', False)]
    
    def metrics_for_subset(subset: List[dict], prefix: str) -> Dict[str, Any]:
        if not subset:
            return {f"{prefix}_count": 0, f"{prefix}_p50_ms": None, f"{prefix}_p95_ms": None, f"{prefix}_p99_ms": None}
        
        success_subset = [r for r in subset if str(int(r.get("status", 0))) == "200"]
        lats = [r.get("latency_ms", float("nan")) for r in success_subset]
        ttfs = [r.get("ttfb_ms", float("nan")) for r in success_subset if not math.isnan(r.get("ttfb_ms", float("nan")))]
        
        return {
            f"{prefix}_count": len(subset),
            f"{prefix}_success_count": len(success_subset),
            f"{prefix}_p50_ms": percentile(lats, 0.50) if lats else None,
            f"{prefix}_p95_ms": percentile(lats, 0.95) if lats else None,
            f"{prefix}_p99_ms": percentile(lats, 0.99) if lats else None,
            f"{prefix}_ttft_p50_ms": percentile(ttfs, 0.50) if ttfs else None,
            f"{prefix}_ttft_p95_ms": percentile(ttfs, 0.95) if ttfs else None,
            f"{prefix}_error_rate": (len(subset) - len(success_subset)) / len(subset) if subset else 0,
        }
    
    cold_metrics = metrics_for_subset(cold_rows, "cold")
    warm_metrics = metrics_for_subset(warm_rows, "warm")
    
    return {**cold_metrics, **warm_metrics}


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

    start, end = window_bounds(rows)
    
    # Get cold start times and classify requests
    cold_start_times = get_cold_start_times(args.namespace, args.service, start, end)
    rows = classify_requests_cold_warm(rows, cold_start_times)
    
    # Compute overall metrics
    lats = [r.get("latency_ms", float("nan")) for r in rows if str(int(r.get("status", 0))) == "200"]
    ttfs = [r.get("ttfb_ms", float("nan")) for r in rows if str(int(r.get("status", 0))) == "200" and not math.isnan(r.get("ttfb_ms", float("nan")))]

    success = sum(1 for r in rows if str(int(r.get("status", 0))) == "200")
    total = len(rows)
    error_rate = (total - success) / total if total else None
    duration = end - start if end > start else None
    throughput = (success / duration) if duration and duration > 0 else None

    completion_tokens = [r.get("completion_tokens", 0.0) or 0.0 for r in rows if str(int(r.get("status", 0))) == "200"]
    total_tokens = sum((r.get("total_tokens", 0.0) or 0.0) for r in rows if str(int(r.get("status", 0))) == "200")
    tokens_per_sec = (sum(completion_tokens) / duration) if duration and duration > 0 else None

    # Compute cold/warm breakdown
    cold_warm_metrics = compute_cold_warm_metrics(rows)
    
    # Compute token timing analysis with histograms
    token_timing_metrics = compute_token_timing_analysis(rows)

    util = {"gpu_util_avg": None, "gpu_mem_used_avg": None, "gpu_power_watts_avg": None, "cpu_util_avg": None, "mem_used_avg": None}
    if args.prom_url:
        try:
            util = utilization_from_prom(args.prom_url, args.namespace, args.service, start, end)
        except Exception as e:
            print(f"Prometheus query failed: {e}", file=sys.stderr)

    cold_starts = len(cold_start_times)

    # Calculate energy metrics
    energy_metrics = {}
    if util.get("gpu_power_watts_avg") and duration:
        # Energy consumed in watt-hours
        energy_wh = util["gpu_power_watts_avg"] * (duration / 3600.0)
        energy_metrics.update({
            "energy_wh": energy_wh,
            "energy_wh_per_request": (energy_wh / success) if success > 0 else None,
            "energy_wh_per_1k_tokens": (energy_wh / total_tokens * 1000.0) if total_tokens > 0 else None,
        })

    # Incorporate network/storage probe if available
    io_probe_path = os.path.join(args.run_dir, "io_probe.json")
    io_probe = {}
    if os.path.exists(io_probe_path):
        try:
            with open(io_probe_path) as f:
                io_probe = json.load(f)
        except Exception:
            io_probe = {}

    # Cache hit ratio if available
    chr_val = None
    try:
        chr_val = cache_hit_ratio(args.prom_url, args.namespace, args.service, start, end)
    except Exception:
        chr_val = None

    results = {
        "p50_ms": percentile(lats, 0.50),
        "p95_ms": percentile(lats, 0.95),
        "p99_ms": percentile(lats, 0.99),
        "throughput_rps": throughput,
        "tokens_per_sec": tokens_per_sec,
        "error_rate": error_rate,
        "cold_start_count": cold_starts,
        "time_to_first_token_ms": stats.mean(ttfs) if ttfs else None,
        "ttft_p50_ms": percentile(ttfs, 0.50) if ttfs else None,
        "ttft_p95_ms": percentile(ttfs, 0.95) if ttfs else None,
        **util,
        **energy_metrics,
        **cold_warm_metrics,
        **token_timing_metrics,
        "window": {"start": start, "end": end, "seconds": duration},
        "requests": {"total": total, "success": success},
        # Optional I/O probe
        "network_rtt_p50_ms": (io_probe.get("rtt", {}) or {}).get("p50_ms"),
        "network_rtt_p95_ms": (io_probe.get("rtt", {}) or {}).get("p95_ms"),
        "s3_avg_MBps": (io_probe.get("s3", {}) or {}).get("avg_MBps"),
        "cache_hit_ratio": chr_val,
    }

    # Update the requests CSV with cold/warm classification
    req_csv_updated = os.path.join(args.run_dir, "requests_classified.csv")
    with open(req_csv_updated, "w", newline="") as f:
        if rows:
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

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
