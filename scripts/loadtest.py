#!/usr/bin/env python3
import argparse
import asyncio
import csv
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class ReqResult:
    id: int
    scheduled_ms: float  # when request was supposed to start
    start_ms: float      # when request actually started
    ttfb_ms: Optional[float]  # time to first byte (first chunk received)
    tllt_ms: Optional[float]  # time to last token (final completion)  
    latency_ms: float
    status: int
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    error: Optional[str]
    is_cold_start: Optional[bool] = None  # determined later by analyzer


def now_ms() -> float:
    return time.time() * 1000.0


def generate_arrival_times(pattern: str, num_requests: int, duration_sec: float, rps: float) -> List[float]:
    """Generate request arrival times based on traffic pattern."""
    if pattern == "steady":
        # Even spacing
        interval = 1.0 / rps
        return [i * interval for i in range(num_requests)]
    
    elif pattern == "poisson":
        # Poisson arrival process with rate rps
        times = []
        t = 0.0
        for _ in range(num_requests):
            # Exponential inter-arrival times
            t += random.expovariate(rps)
            times.append(t)
        return times
    
    elif pattern == "bursty":
        # Burst of 80% requests in first 20% of time, rest spread out
        burst_fraction = 0.8
        burst_time_fraction = 0.2
        
        burst_count = int(num_requests * burst_fraction)
        normal_count = num_requests - burst_count
        
        times = []
        # Burst phase: cramped uniform distribution
        burst_duration = duration_sec * burst_time_fraction
        for i in range(burst_count):
            times.append(random.uniform(0, burst_duration))
        
        # Normal phase: remaining requests spread out
        normal_start = burst_duration
        normal_duration = duration_sec - burst_duration
        for i in range(normal_count):
            times.append(normal_start + random.uniform(0, normal_duration))
        
        times.sort()
        return times
    
    elif pattern == "heavy":
        # Heavy-tail: most requests early, long tail
        # Use Pareto distribution (power law)
        times = []
        for i in range(num_requests):
            # Pareto with shape parameter 1.2 (heavy tail)
            u = random.random()
            pareto_val = (1.0 / u) ** (1.0 / 1.2) - 1.0  # Pareto(1.2)
            # Scale to fit in duration
            t = (pareto_val / 10.0) * duration_sec  # rough scaling
            t = min(t, duration_sec * 0.95)  # cap outliers
            times.append(t)
        
        times.sort()
        return times
    
    else:
        raise ValueError(f"Unknown pattern: {pattern}")


def calculate_duration_and_rps(requests: int, concurrency: int, pattern: str) -> tuple[float, float]:
    """Calculate appropriate test duration and target RPS based on pattern."""
    if pattern == "steady":
        # Duration based on concurrency constraint
        target_rps = concurrency * 2.0  # assume ~500ms avg latency
        duration_sec = requests / target_rps
        return duration_sec, target_rps
    
    elif pattern in ["poisson", "bursty", "heavy"]:
        # For realistic patterns, use higher RPS but expect natural throttling
        target_rps = concurrency * 1.5  # slightly more aggressive
        duration_sec = (requests / target_rps) * 1.5  # give more time for bursts
        return duration_sec, target_rps
    
    else:
        return 60.0, requests / 60.0


async def do_openai_request(client: httpx.AsyncClient, url: str, api_key: Optional[str], model: str, prompt: str, max_tokens: int, stream: bool) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": stream,
    }
    if stream:
        # Stream chunks and assemble usage afterwards if available
        async with client.stream("POST", url, headers=headers, json=payload, timeout=60) as resp:
            status = resp.status_code
            ttfb_ms = None
            tllt_ms = None
            content = ""
            chunk_count = 0
            
            async for chunk in resp.aiter_text():
                current_time = now_ms()
                if ttfb_ms is None:
                    ttfb_ms = current_time  # First chunk
                tllt_ms = current_time  # Keep updating to capture last chunk time
                content += chunk
                chunk_count += 1
            
            return {
                "status": status, 
                "content": content, 
                "ttfb_mark_ms": ttfb_ms,
                "tllt_mark_ms": tllt_ms,
                "chunk_count": chunk_count
            }
    else:
        resp = await client.post(url, headers=headers, json=payload, timeout=60)
        return {"status": resp.status_code, "json": resp.json()}


async def worker(task_id: int, scheduled_time: float, args, results: List[ReqResult], sem: asyncio.Semaphore, test_start_time: float):
    url = args.url.rstrip("/") + "/v1/chat/completions"
    
    # Wait until scheduled time
    current_time = time.time() - test_start_time
    if scheduled_time > current_time:
        await asyncio.sleep(scheduled_time - current_time)
    
    async with sem:
        start = now_ms()
        ttfb_mark = None
        tllt_mark = None
        status = 0
        usage = None
        err = None
        try:
            async with httpx.AsyncClient(http2=False, verify=not args.insecure) as client:
                res = await do_openai_request(
                    client,
                    url=url,
                    api_key=args.api_key,
                    model=args.model,
                    prompt=args.prompt,
                    max_tokens=args.max_tokens,
                    stream=True,
                )
                status = int(res.get("status", 0))
                if res.get("ttfb_mark_ms"):
                    ttfb_mark = float(res["ttfb_mark_ms"]) - start
                if res.get("tllt_mark_ms"):
                    tllt_mark = float(res["tllt_mark_ms"]) - start
                # Try to parse final usage from concatenated chunks
                text = res.get("content") or ""
                # Extract last JSON object after "data: [DONE]" cases
                # Look for '"usage":{' pattern and parse minimal JSON braces
                try:
                    if "\n{\"id\"" in text:
                        last_json = text.strip().split("\n")[-1]
                        if last_json and last_json.startswith("{"):
                            js = json.loads(last_json)
                            usage = js.get("usage")
                    elif '"usage":' in text:
                        # naive fallback: attempt to find a JSON block
                        pass
                except Exception:
                    pass
        except Exception as e:
            err = str(e)
        end = now_ms()
        latency = end - start

        pr = None
        cr = None
        tr = None
        if isinstance(usage, dict):
            pr = usage.get("prompt_tokens")
            cr = usage.get("completion_tokens")
            tr = usage.get("total_tokens")

        scheduled_ms = test_start_time * 1000.0 + scheduled_time * 1000.0
        results.append(ReqResult(
            id=task_id,
            scheduled_ms=scheduled_ms,
            start_ms=start,
            ttfb_ms=ttfb_mark,
            tllt_ms=tllt_mark,
            latency_ms=latency,
            status=status,
            prompt_tokens=pr,
            completion_tokens=cr,
            total_tokens=tr,
            error=err,
        ))


async def main_async(args):
    results: List[ReqResult] = []
    sem = asyncio.Semaphore(args.concurrency)
    
    # Generate arrival schedule based on pattern
    duration, target_rps = calculate_duration_and_rps(args.requests, args.concurrency, args.pattern)
    arrival_times = generate_arrival_times(args.pattern, args.requests, duration, target_rps)
    
    print(f"Generated {args.pattern} pattern: {args.requests} requests over {duration:.1f}s (target {target_rps:.1f} RPS)")
    
    test_start_time = time.time()
    tasks = [
        worker(i + 1, arrival_times[i], args, results, sem, test_start_time)
        for i in range(args.requests)
    ]
    
    # Launch all tasks concurrently; they'll self-schedule based on arrival times
    await asyncio.gather(*[asyncio.create_task(t) for t in tasks])

    # Persist
    os.makedirs(args.run_dir, exist_ok=True)
    csv_path = os.path.join(args.run_dir, "requests.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "scheduled_ms", "start_ms", "ttfb_ms", "tllt_ms", "latency_ms", "status", "prompt_tokens", "completion_tokens", "total_tokens", "error"])
        for r in results:
            w.writerow([
                r.id,
                f"{r.scheduled_ms:.3f}",
                f"{r.start_ms:.3f}",
                f"{r.ttfb_ms:.3f}" if r.ttfb_ms is not None else "",
                f"{r.tllt_ms:.3f}" if r.tllt_ms is not None else "",
                f"{r.latency_ms:.3f}",
                r.status,
                r.prompt_tokens if r.prompt_tokens is not None else "",
                r.completion_tokens if r.completion_tokens is not None else "",
                r.total_tokens if r.total_tokens is not None else "",
                r.error or "",
            ])

    meta = {
        "url": args.url,
        "model": args.model,
        "prompt": args.prompt,
        "max_tokens": args.max_tokens,
        "concurrency": args.concurrency,
        "requests": args.requests,
        "pattern": args.pattern,
        "duration_sec": duration,
        "target_rps": target_rps,
        "test_start_time": test_start_time,
    }
    with open(os.path.join(args.run_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="Base URL of endpoint (OpenAI-compatible), e.g., http://<host>")
    ap.add_argument("--model", default="placeholder", help="Model name passed to API")
    ap.add_argument("--prompt", default="Hello, world!", help="Prompt to send")
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--pattern", choices=["steady", "poisson", "bursty", "heavy"], default="steady",
                    help="Traffic pattern: steady (even spacing), poisson (exponential arrivals), bursty (80%% in first 20%% of time), heavy (power-law tail)")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--insecure", action="store_true", help="Disable TLS verification")
    args = ap.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("Aborted")
        sys.exit(130)


if __name__ == "__main__":
    main()

