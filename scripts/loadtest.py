#!/usr/bin/env python3
import argparse
import asyncio
import csv
import json
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
    start_ms: float
    ttfb_ms: Optional[float]
    latency_ms: float
    status: int
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    error: Optional[str]


def now_ms() -> float:
    return time.time() * 1000.0


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
            content = ""
            async for chunk in resp.aiter_text():
                if ttfb_ms is None:
                    ttfb_ms = now_ms()
                content += chunk
            return {"status": status, "content": content, "ttfb_mark_ms": ttfb_ms}
    else:
        resp = await client.post(url, headers=headers, json=payload, timeout=60)
        return {"status": resp.status_code, "json": resp.json()}


async def worker(task_id: int, args, results: List[ReqResult], sem: asyncio.Semaphore):
    url = args.url.rstrip("/") + "/v1/chat/completions"
    async with sem:
        start = now_ms()
        ttfb_mark = None
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

        results.append(ReqResult(
            id=task_id,
            start_ms=start,
            ttfb_ms=ttfb_mark,
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
    tasks = [worker(i + 1, args, results, sem) for i in range(args.requests)]
    # Stagger a little to avoid bursty SYN
    batch = []
    for i, t in enumerate(tasks):
        batch.append(asyncio.create_task(t))
        if (i + 1) % args.concurrency == 0:
            await asyncio.gather(*batch)
            batch = []
        else:
            await asyncio.sleep(0.001)
    if batch:
        await asyncio.gather(*batch)

    # Persist
    os.makedirs(args.run_dir, exist_ok=True)
    csv_path = os.path.join(args.run_dir, "requests.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "start_ms", "ttfb_ms", "latency_ms", "status", "prompt_tokens", "completion_tokens", "total_tokens", "error"])
        for r in results:
            w.writerow([
                r.id,
                f"{r.start_ms:.3}",
                f"{r.ttfb_ms:.3}" if r.ttfb_ms is not None else "",
                f"{r.latency_ms:.3}",
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

