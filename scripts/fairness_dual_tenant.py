#!/usr/bin/env python3
"""
Dual-tenant fairness and backpressure harness.

Runs two concurrent traffic streams (tenants A and B) against an
OpenAI-compatible endpoint. Enforces a simple backpressure guard that
throttles tenant B when rolling P95 approaches/exceeds a target SLO.

Outputs:
  - requests.csv (per-request with tenant + guard_action)
  - fairness_summary.json (per-tenant latency/throughput, guard stats)
  - fairness_report.html (latency and throughput share charts)
"""

import argparse
import asyncio
import csv
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
import numpy as np


def now_ms() -> float:
    return time.time() * 1000.0


@dataclass
class Req:
    id: int
    tenant: str
    start_ms: float
    latency_ms: Optional[float] = None
    status: Optional[int] = None
    error: Optional[str] = None
    guard_action: Optional[str] = None


class RollingP95:
    def __init__(self, window: int = 50):
        self.window = window
        self.samples: List[float] = []

    def add(self, val: float):
        self.samples.append(val)
        if len(self.samples) > self.window:
            self.samples.pop(0)

    def p95(self) -> Optional[float]:
        if not self.samples:
            return None
        arr = sorted(self.samples)
        k = int(0.95 * (len(arr) - 1))
        return arr[k]


async def do_request(client: httpx.AsyncClient, url: str, api_key: Optional[str], model: str, prompt: str, max_tokens: int) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    resp = await client.post(url.rstrip("/") + "/v1/chat/completions", headers=headers, json=payload)
    return {"status": resp.status_code, "json": (await resp.aread()) if hasattr(resp, 'aread') else resp.text}


async def run_tenant(name: str, nreq: int, concurrency: int, args, 
                     results: List[Req], sem: asyncio.Semaphore, guard) -> None:
    async with httpx.AsyncClient(verify=not args.insecure, timeout=60) as client:
        async def task_fn(i: int):
            nonlocal client
            # Backpressure: if guard active, drop/slow tenant B only
            if name == 'B' and guard.should_throttle_b():
                r = Req(id=i, tenant=name, start_ms=now_ms(), status=429, error='throttled', guard_action='throttled')
                results.append(r)
                await asyncio.sleep(0.01)
                return

            async with sem:
                r = Req(id=i, tenant=name, start_ms=now_ms())
                try:
                    t0 = now_ms()
                    _ = await do_request(client, args.url, args.api_key, args.model, args.prompt, args.max_tokens)
                    r.latency_ms = now_ms() - t0
                    r.status = 200
                    guard.observe(r.latency_ms)
                except Exception as e:
                    r.status = 0
                    r.error = str(e)
                results.append(r)

        tasks = [asyncio.create_task(task_fn(i + 1)) for i in range(nreq)]
        await asyncio.gather(*tasks)


class Guard:
    def __init__(self, p95_budget_ms: Optional[float], window: int = 50, cooldown_sec: float = 2.0):
        self.p95_budget_ms = p95_budget_ms
        self.rolling = RollingP95(window)
        self.cooldown_sec = cooldown_sec
        self._throttle_until: float = 0.0
        self.trigger_count = 0

    def observe(self, latency_ms: float):
        self.rolling.add(latency_ms)
        if self.p95_budget_ms:
            p = self.rolling.p95()
            if p and p > self.p95_budget_ms:
                self.trigger_count += 1
                self._throttle_until = time.time() + self.cooldown_sec

    def should_throttle_b(self) -> bool:
        return time.time() < self._throttle_until


def summarize(results: List[Req]) -> Dict[str, Any]:
    def per_tenant(name: str) -> Dict[str, Any]:
        rs = [r for r in results if r.tenant == name]
        succ = [r for r in rs if r.status == 200 and r.latency_ms is not None]
        lats = [r.latency_ms for r in succ]
        p95 = float(np.percentile(lats, 95)) if lats else None
        p50 = float(np.percentile(lats, 50)) if lats else None
        return {
            "requests": len(rs),
            "success": len(succ),
            "p50_ms": p50,
            "p95_ms": p95,
        }
    A = per_tenant('A')
    B = per_tenant('B')
    total_succ = (A.get('success') or 0) + (B.get('success') or 0)
    share_A = (A.get('success') or 0) / total_succ if total_succ else None
    share_B = (B.get('success') or 0) / total_succ if total_succ else None
    return {"A": A, "B": B, "throughput_share": {"A": share_A, "B": share_B}}


def write_csv(results: List[Req], path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(["id", "tenant", "start_ms", "latency_ms", "status", "error", "guard_action"])
        for r in results:
            w.writerow([r.id, r.tenant, f"{r.start_ms:.3f}", f"{r.latency_ms:.3f}" if r.latency_ms else "", r.status or "", r.error or "", r.guard_action or ""])


def write_report(summary: Dict[str, Any], guard_triggers: int, output_path: str):
    try:
        import matplotlib.pyplot as plt
        import base64
        from io import BytesIO
    except Exception:
        # Fallback JSON-only
        with open(output_path.replace('.html', '.json'), 'w') as f:
            json.dump({"summary": summary, "guard_triggers": guard_triggers}, f, indent=2)
        return

    # Bar chart: per-tenant p95
    p95 = [summary['A'].get('p95_ms') or 0, summary['B'].get('p95_ms') or 0]
    shares = [summary['throughput_share'].get('A') or 0, summary['throughput_share'].get('B') or 0]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10,5))
    ax1.bar(['Tenant A', 'Tenant B'], p95, color=['steelblue','orange'])
    ax1.set_title('P95 Latency per Tenant (ms)')
    ax2.bar(['Tenant A', 'Tenant B'], shares, color=['seagreen','salmon'])
    ax2.set_ylim(0,1)
    ax2.set_title('Throughput Share')
    buffer = BytesIO(); plt.tight_layout(); plt.savefig(buffer, format='png', dpi=100); buffer.seek(0)
    img = base64.b64encode(buffer.getvalue()).decode(); plt.close()

    html = f"""
<!DOCTYPE html><html><head><meta charset='utf-8'><title>Fairness Report</title></head>
<body>
<h1>Multi-tenant Fairness & Backpressure</h1>
<p><b>Guard triggers:</b> {guard_triggers}</p>
<img src="data:image/png;base64,{img}" alt="Fairness Charts"/>
</body></html>
"""
    with open(output_path, 'w') as f:
        f.write(html)


async def main_async(args):
    run_dir = args.run_dir
    os.makedirs(run_dir, exist_ok=True)
    sem = asyncio.Semaphore(args.tenant_a_concurrency + args.tenant_b_concurrency)
    results: List[Req] = []
    guard = Guard(p95_budget_ms=args.p95_budget_ms, window=args.guard_window, cooldown_sec=args.guard_cooldown)

    await asyncio.gather(
        run_tenant('A', args.tenant_a_requests, args.tenant_a_concurrency, args, results, sem, guard),
        run_tenant('B', args.tenant_b_requests, args.tenant_b_concurrency, args, results, sem, guard),
    )

    # Persist artifacts
    write_csv(results, os.path.join(run_dir, 'requests.csv'))
    summary = summarize(results)
    with open(os.path.join(run_dir, 'fairness_summary.json'), 'w') as f:
        json.dump({"summary": summary, "guard_triggers": guard.trigger_count}, f, indent=2)
    write_report(summary, guard.trigger_count, os.path.join(run_dir, 'fairness_report.html'))


def main():
    ap = argparse.ArgumentParser(description='Dual-tenant fairness + backpressure harness')
    ap.add_argument('--url', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--prompt', default='Respond briefly to: Hello')
    ap.add_argument('--max-tokens', type=int, default=32)
    ap.add_argument('--tenant-a-requests', type=int, default=200)
    ap.add_argument('--tenant-b-requests', type=int, default=200)
    ap.add_argument('--tenant-a-concurrency', type=int, default=10)
    ap.add_argument('--tenant-b-concurrency', type=int, default=10)
    ap.add_argument('--p95-budget-ms', type=float, default=None)
    ap.add_argument('--guard-window', type=int, default=50)
    ap.add_argument('--guard-cooldown', type=float, default=2.0)
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--api-key', default=None)
    ap.add_argument('--insecure', action='store_true')
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == '__main__':
    main()

