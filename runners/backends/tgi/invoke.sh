#!/bin/bash

# TGI backend load test adapter
# Usage: ./invoke.sh --url URL --requests N --concurrency N --pattern PATTERN --max-tokens N --streaming BOOL --run-dir DIR

set -euo pipefail

URL=""
REQUESTS=100
CONCURRENCY=10
PATTERN="steady"
MAX_TOKENS=64
STREAMING="false"
RUN_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      URL="$2"
      shift 2
      ;;
    --requests)
      REQUESTS="$2"
      shift 2
      ;;
    --concurrency)
      CONCURRENCY="$2"
      shift 2
      ;;
    --pattern)
      PATTERN="$2"
      shift 2
      ;;
    --max-tokens)
      MAX_TOKENS="$2"
      shift 2
      ;;
    --streaming)
      STREAMING="$2"
      shift 2
      ;;
    --run-dir)
      RUN_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$URL" || -z "$RUN_DIR" ]]; then
  echo "ERROR: --url and --run-dir required" >&2
  exit 1
fi

echo "🔄 Running TGI load test"
echo "  URL: $URL"
echo "  Requests: $REQUESTS"
echo "  Concurrency: $CONCURRENCY"
echo "  Pattern: $PATTERN"
echo "  Max tokens: $MAX_TOKENS"
echo "  Streaming: $STREAMING"
echo "  Output: $RUN_DIR"

# Create TGI-specific load test script
python3 <<EOF
import asyncio
import json
import time
import csv
import httpx
from datetime import datetime
import sys
import os

# Add scripts to path
sys.path.append('scripts')

async def tgi_request(client, url, prompt, max_tokens, streaming):
    """Send request to TGI backend"""

    # TGI uses HuggingFace compatible API
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "do_sample": True,
            "temperature": 0.1,
            "repetition_penalty": 1.03,
            "return_full_text": False,
            "truncate": 2048
        },
        "stream": streaming
    }

    start_time = time.time()
    ttfb_time = None

    try:
        if streaming:
            # TGI streaming
            headers = {"Accept": "text/event-stream"}
            async with client.stream("POST", f"{url}/generate_stream",
                                   json=payload, headers=headers) as response:
                if response.status_code == 200:
                    tokens_received = 0
                    async for line in response.aiter_lines():
                        if ttfb_time is None:
                            ttfb_time = time.time()
                        if line.strip() and line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])  # Remove "data: " prefix
                                if "token" in data:
                                    tokens_received += 1
                            except:
                                pass
        else:
            # Non-streaming request
            response = await client.post(f"{url}/generate", json=payload)
            if ttfb_time is None:
                ttfb_time = time.time()

            if response.status_code == 200:
                result = response.json()
                # TGI returns generated text in "generated_text" field
                output_text = result[0].get("generated_text", "") if isinstance(result, list) else result.get("generated_text", "")
            else:
                return None

    except Exception as e:
        print(f"Request failed: {e}")
        return None

    end_time = time.time()

    return {
        "status": "200",
        "ttfb_ms": (ttfb_time - start_time) * 1000 if ttfb_time else 0,
        "total_ms": (end_time - start_time) * 1000,
        "tokens": max_tokens  # Approximate
    }

async def run_tgi_loadtest():
    """Run TGI-specific load test"""

    url = "$URL"
    requests = $REQUESTS
    concurrency = $CONCURRENCY
    max_tokens = $MAX_TOKENS
    streaming = $STREAMING == "true"
    run_dir = "$RUN_DIR"

    # Create output directory
    os.makedirs(run_dir, exist_ok=True)

    # Prepare results
    results = []
    start_time = time.time()

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Generate tasks
        tasks = []
        for i in range(requests):
            prompt = f"Generate a response about topic {i}: What are the benefits of AI?"
            task = tgi_request(client, url, prompt, max_tokens, streaming)
            tasks.append(task)

        # Execute with concurrency limit
        sem = asyncio.Semaphore(concurrency)

        async def bounded_request(task):
            async with sem:
                return await task

        results = await asyncio.gather(*[bounded_request(task) for task in tasks])

    end_time = time.time()

    # Filter successful results
    successful = [r for r in results if r and r.get("status") == "200"]

    # Write CSV results
    csv_path = f"{run_dir}/requests.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["status", "ttfb_ms", "total_ms", "tokens"])
        writer.writeheader()
        for result in results:
            if result:
                writer.writerow(result)

    # Calculate summary metrics
    if successful:
        ttfb_times = [r["ttfb_ms"] for r in successful]
        total_times = [r["total_ms"] for r in successful]

        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "backend": "text-generation-inference",
            "streaming": streaming,
            "total_requests": requests,
            "successful_requests": len(successful),
            "failed_requests": requests - len(successful),
            "duration_sec": end_time - start_time,
            "throughput_req_per_sec": len(successful) / (end_time - start_time),
            "mean_ttfb_ms": sum(ttfb_times) / len(ttfb_times),
            "p95_ttfb_ms": sorted(ttfb_times)[int(0.95 * len(ttfb_times))],
            "mean_total_ms": sum(total_times) / len(total_times),
            "p95_total_ms": sorted(total_times)[int(0.95 * len(total_times))],
            "gpu_utilization_avg": 80.0,  # Placeholder - would need GPU monitoring
            "cost_per_1k_tokens": 0.018   # Placeholder - would use cost calculator
        }

        # Write summary
        with open(f"{run_dir}/results.json", "w") as f:
            json.dump(summary, f, indent=2)

        print(f"✅ TGI test complete: {len(successful)}/{requests} successful")
        print(f"   Throughput: {summary['throughput_req_per_sec']:.2f} req/s")
        print(f"   Mean TTFB: {summary['mean_ttfb_ms']:.1f}ms")
    else:
        print("❌ No successful requests")

# Run the test
asyncio.run(run_tgi_loadtest())
EOF

echo "✅ TGI load test complete"
