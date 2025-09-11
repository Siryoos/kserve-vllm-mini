#!/usr/bin/env python3
"""
Network & storage profiling probe.
Measures endpoint RTT and optional S3/MinIO object fetch throughput.
Writes results to a JSON file for ingestion into analysis/report.
"""

import argparse
import json
import time
from typing import Any, Dict

import httpx


def measure_http_rtt(
    url: str, attempts: int = 5, timeout: float = 5.0
) -> Dict[str, Any]:
    timings = []
    with httpx.Client(timeout=timeout) as client:
        for _ in range(attempts):
            t0 = time.time()
            try:
                resp = client.get(url)
                resp.raise_for_status()
                dt = (time.time() - t0) * 1000
                timings.append(dt)
            except Exception:
                timings.append(None)
    vals = [t for t in timings if t is not None]
    return {
        "attempts": attempts,
        "success": len(vals),
        "p50_ms": sorted(vals)[len(vals) // 2] if vals else None,
        "p95_ms": sorted(vals)[int(0.95 * len(vals))] if vals else None,
        "avg_ms": sum(vals) / len(vals) if vals else None,
    }


def measure_object_fetch(
    url: str, attempts: int = 3, timeout: float = 30.0
) -> Dict[str, Any]:
    throughputs = []
    sizes = []
    with httpx.Client(timeout=timeout) as client:
        for _ in range(attempts):
            t0 = time.time()
            try:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.content
                dt = time.time() - t0
                sz = len(data)
                sizes.append(sz)
                if dt > 0:
                    throughputs.append(sz / dt)  # bytes/sec
            except Exception:
                pass
    tp_mb_s = [x / (1024 * 1024) for x in throughputs]
    return {
        "attempts": attempts,
        "success": len(tp_mb_s),
        "avg_MBps": sum(tp_mb_s) / len(tp_mb_s) if tp_mb_s else None,
        "min_MBps": min(tp_mb_s) if tp_mb_s else None,
        "max_MBps": max(tp_mb_s) if tp_mb_s else None,
        "avg_size_bytes": sum(sizes) / len(sizes) if sizes else None,
    }


def main():
    ap = argparse.ArgumentParser(description="Network & storage profiling probe")
    ap.add_argument(
        "--endpoint", required=True, help="Service base URL (e.g., http://host)"
    )
    ap.add_argument("--s3-object-url", help="Optional S3/MinIO object URL to test")
    ap.add_argument(
        "--out", required=True, help="Output JSON path (e.g., runs/<id>/io_probe.json)"
    )
    args = ap.parse_args()

    # Measure endpoint RTT via a cheap GET (models list or root)
    rtt_path_candidates = ["/v1/models", "/health", "/"]
    rtt = None
    for p in rtt_path_candidates:
        try:
            rtt = measure_http_rtt(args.endpoint.rstrip("/") + p)
            if rtt and rtt.get("success"):
                break
        except Exception:
            continue

    s3 = None
    if args.s3_object_url:
        try:
            s3 = measure_object_fetch(args.s3_object_url)
        except Exception:
            s3 = {"error": "fetch_failed"}

    out = {
        "endpoint": args.endpoint,
        "rtt": rtt,
        "s3": s3,
        "generated_at": time.time(),
    }
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
