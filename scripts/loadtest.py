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
    """Per-request outcome captured by the load generator."""

    id: int
    scheduled_ms: float  # when request was supposed to start
    start_ms: float  # when request actually started
    ttfb_ms: Optional[float]  # time to first byte (first chunk received)
    tllt_ms: Optional[float]  # time to last token (final completion)
    latency_ms: float
    status: int
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    error: Optional[str]
    is_cold_start: Optional[bool] = None  # determined later by analyzer
    trace_id: Optional[str] = None  # OpenTelemetry trace ID


@dataclass
class TraceSpan:
    """Lightweight trace span for request lifecycle analysis."""

    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: float  # milliseconds
    end_time: Optional[float] = None
    status: str = "ok"  # ok, error, timeout
    attributes: Optional[Dict[str, Any]] = None


def now_ms() -> float:
    """Current time in milliseconds (float)."""
    return time.time() * 1000.0


def generate_trace_id() -> str:
    """Generate OpenTelemetry-compatible trace ID (32 hex chars)."""
    return f"{random.randint(0, 2**128 - 1):032x}"


def generate_span_id() -> str:
    """Generate OpenTelemetry-compatible span ID (16 hex chars)."""
    return f"{random.randint(0, 2**64 - 1):016x}"


def create_traceparent_header(trace_id: str, span_id: str) -> str:
    """Create W3C traceparent header for distributed tracing."""
    # Format: version-traceid-spanid-flags
    return f"00-{trace_id}-{span_id}-01"


class TraceCollector:
    """Lightweight trace collector for request lifecycle analysis."""

    def __init__(self):
        self.spans: List[TraceSpan] = []

    def start_span(
        self,
        trace_id: str,
        operation_name: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> TraceSpan:
        """Start a new trace span."""
        span = TraceSpan(
            trace_id=trace_id,
            span_id=generate_span_id(),
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            start_time=now_ms(),
            attributes=attributes or {},
        )
        self.spans.append(span)
        return span

    def finish_span(
        self,
        span: TraceSpan,
        status: str = "ok",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Finish a trace span."""
        span.end_time = now_ms()
        span.status = status
        if attributes:
            span.attributes = {**(span.attributes or {}), **attributes}

    def export_traces(self, output_file: str) -> None:
        """Export traces to JSON file in OpenTelemetry format."""
        trace_data = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": "kserve-vllm-loadtest"},
                            },
                            {
                                "key": "service.version",
                                "value": {"stringValue": "1.0.0"},
                            },
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "kserve-vllm-mini", "version": "1.0.0"},
                            "spans": [],
                        }
                    ],
                }
            ]
        }

        # Convert spans to OpenTelemetry format
        for span in self.spans:
            otlp_span = {
                "traceId": span.trace_id,
                "spanId": span.span_id,
                "name": span.operation_name,
                "startTimeUnixNano": int(
                    span.start_time * 1_000_000
                ),  # convert ms to nanoseconds
                "endTimeUnixNano": int((span.end_time or span.start_time) * 1_000_000),
                "attributes": [],
                "status": {
                    "code": 1 if span.status == "ok" else 2
                },  # STATUS_CODE_OK = 1, STATUS_CODE_ERROR = 2
            }

            if span.parent_span_id:
                otlp_span["parentSpanId"] = span.parent_span_id

            # Add attributes
            if span.attributes:
                for key, value in span.attributes.items():
                    attr = {"key": key}
                    if isinstance(value, str):
                        attr["value"] = {"stringValue": value}
                    elif isinstance(value, (int, float)):
                        attr["value"] = {"doubleValue": float(value)}
                    elif isinstance(value, bool):
                        attr["value"] = {"boolValue": value}
                    else:
                        attr["value"] = {"stringValue": str(value)}
                    otlp_span["attributes"].append(attr)

            trace_data["resourceSpans"][0]["scopeSpans"][0]["spans"].append(otlp_span)

        # Write to file
        with open(output_file, "w") as f:
            json.dump(trace_data, f, indent=2)


# Global trace collector
trace_collector = TraceCollector()


def generate_arrival_times(
    pattern: str, num_requests: int, duration_sec: float, rps: float
) -> List[float]:
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
        for _i in range(burst_count):
            times.append(random.uniform(0, burst_duration))

        # Normal phase: remaining requests spread out
        normal_start = burst_duration
        normal_duration = duration_sec - burst_duration
        for _i in range(normal_count):
            times.append(normal_start + random.uniform(0, normal_duration))

        times.sort()
        return times

    elif pattern == "heavy":
        # Heavy-tail: most requests early, long tail
        # Use Pareto distribution (power law)
        times = []
        for _i in range(num_requests):
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


def calculate_duration_and_rps(
    requests: int, concurrency: int, pattern: str
) -> tuple[float, float]:
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


async def do_openai_request(
    client: httpx.AsyncClient,
    url: str,
    api_key: Optional[str],
    model: str,
    prompt: str,
    max_tokens: int,
    stream: bool,
    trace_id: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    n: Optional[int] = None,
    presence_penalty: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    json_mode: bool = False,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Send a single OpenAI chat.completions request.

    Supports optional streaming; when streaming, returns ttfb/tllt markers
    measured on the client and concatenated chunk text.
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Add distributed tracing header if trace_id provided
    request_span_id = generate_span_id()
    if trace_id:
        headers["traceparent"] = create_traceparent_header(trace_id, request_span_id)

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0 if temperature is None else temperature,
        "stream": stream,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if top_k is not None:
        payload["top_k"] = top_k
    if n is not None and n > 1:
        payload["n"] = n
    if presence_penalty is not None:
        payload["presence_penalty"] = presence_penalty
    if frequency_penalty is not None:
        payload["frequency_penalty"] = frequency_penalty
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if extra_payload:
        # Merge vendor-specific fields (e.g., vLLM: use_beam_search, num_beams, speculative decoding)
        payload.update(extra_payload)
    if stream:
        # Stream chunks and assemble usage afterwards if available
        async with client.stream(
            "POST", url, headers=headers, json=payload, timeout=60
        ) as resp:
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
                "chunk_count": chunk_count,
            }
    else:
        resp = await client.post(url, headers=headers, json=payload, timeout=60)
        return {"status": resp.status_code, "json": resp.json()}


async def worker(
    task_id: int,
    scheduled_time: float,
    args,
    results: List[ReqResult],
    sem: asyncio.Semaphore,
    test_start_time: float,
):
    """Cooperative task that schedules and issues one request and records result."""
    url = args.url.rstrip("/") + "/v1/chat/completions"

    # Generate trace ID for this request
    trace_id = generate_trace_id()

    # Start root span for the entire request
    root_span = trace_collector.start_span(
        trace_id=trace_id,
        operation_name="client.request",
        attributes={
            "request.id": task_id,
            "http.url": url,
            "http.method": "POST",
            "llm.model": args.model,
            "llm.max_tokens": args.max_tokens,
        },
    )

    # Wait until scheduled time
    wait_span = trace_collector.start_span(
        trace_id=trace_id,
        operation_name="client.wait_scheduled",
        parent_span_id=root_span.span_id,
    )

    current_time = time.time() - test_start_time
    if scheduled_time > current_time:
        await asyncio.sleep(scheduled_time - current_time)

    trace_collector.finish_span(
        wait_span,
        attributes={
            "wait_time_ms": (time.time() - test_start_time - scheduled_time) * 1000
        },
    )

    async with sem:
        start = now_ms()
        ttfb_mark = None
        tllt_mark = None
        status = 0
        usage = None
        err = None

        # Start HTTP request span
        http_span = trace_collector.start_span(
            trace_id=trace_id,
            operation_name="http.request",
            parent_span_id=root_span.span_id,
            attributes={"http.url": url},
        )

        try:
            async with httpx.AsyncClient(
                http2=False, verify=not args.insecure
            ) as client:
                # Build extra payload if provided via args
                extra_payload = None
                if args.extra_openai_json:
                    try:
                        import json as _json

                        with open(args.extra_openai_json) as _f:
                            extra_payload = _json.load(_f)
                    except Exception:
                        extra_payload = None

                res = await do_openai_request(
                    client,
                    url=url,
                    api_key=args.api_key,
                    model=args.model,
                    prompt=args.prompt,
                    max_tokens=args.max_tokens,
                    stream=args.stream,
                    trace_id=trace_id,
                    temperature=args.temperature,
                    top_p=args.top_p,
                    top_k=args.top_k,
                    n=args.num_completions,
                    presence_penalty=args.presence_penalty,
                    frequency_penalty=args.frequency_penalty,
                    json_mode=args.json_mode,
                    extra_payload=extra_payload,
                )
                status = int(res.get("status", 0))

                # Create spans for timing milestones
                if res.get("ttfb_mark_ms"):
                    ttfb_mark = float(res["ttfb_mark_ms"]) - start
                    ttft_span = trace_collector.start_span(
                        trace_id=trace_id,
                        operation_name="server.ttft",
                        parent_span_id=http_span.span_id,
                        attributes={"ttft_ms": ttfb_mark},
                    )
                    ttft_span.end_time = res["ttfb_mark_ms"]
                    trace_collector.finish_span(ttft_span)

                if res.get("tllt_mark_ms"):
                    tllt_mark = float(res["tllt_mark_ms"]) - start
                    tllt_span = trace_collector.start_span(
                        trace_id=trace_id,
                        operation_name="server.tllt",
                        parent_span_id=http_span.span_id,
                        attributes={"tllt_ms": tllt_mark},
                    )
                    tllt_span.end_time = res["tllt_mark_ms"]
                    trace_collector.finish_span(tllt_span)

                # Try to parse final usage from concatenated chunks
                text = res.get("content") or ""
                # Extract last JSON object after "data: [DONE]" cases
                # Look for '"usage":{' pattern and parse minimal JSON braces
                try:
                    if '\n{"id"' in text:
                        last_json = text.strip().split("\n")[-1]
                        if last_json and last_json.startswith("{"):
                            js = json.loads(last_json)
                            usage = js.get("usage")
                    elif '"usage":' in text:
                        # naive fallback: attempt to find a JSON block
                        pass
                except Exception:
                    pass

                trace_collector.finish_span(
                    http_span,
                    "ok",
                    {
                        "http.status_code": status,
                        "response.chunk_count": res.get("chunk_count", 0),
                    },
                )

        except Exception as e:
            err = str(e)
            trace_collector.finish_span(http_span, "error", {"error.message": str(e)})

        end = now_ms()
        latency = end - start

        pr = None
        cr = None
        tr = None
        if isinstance(usage, dict):
            pr = usage.get("prompt_tokens")
            cr = usage.get("completion_tokens")
            tr = usage.get("total_tokens")

        # Finish root span
        trace_collector.finish_span(
            root_span,
            "error" if err else "ok",
            {
                "http.status_code": status,
                "request.latency_ms": latency,
                "llm.prompt_tokens": pr or 0,
                "llm.completion_tokens": cr or 0,
                "llm.total_tokens": tr or 0,
            },
        )

        scheduled_ms = test_start_time * 1000.0 + scheduled_time * 1000.0
        results.append(
            ReqResult(
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
                trace_id=trace_id,
            )
        )


async def main_async(args):
    """Drive the async load test, persist OTLP traces and requests.csv."""
    results: List[ReqResult] = []
    sem = asyncio.Semaphore(args.concurrency)

    # Generate arrival schedule based on pattern
    duration, target_rps = calculate_duration_and_rps(
        args.requests, args.concurrency, args.pattern
    )
    arrival_times = generate_arrival_times(
        args.pattern, args.requests, duration, target_rps
    )

    print(
        f"Generated {args.pattern} pattern: {args.requests} requests over {duration:.1f}s (target {target_rps:.1f} RPS)"
    )

    test_start_time = time.time()
    tasks = [
        worker(i + 1, arrival_times[i], args, results, sem, test_start_time)
        for i in range(args.requests)
    ]

    # Launch all tasks concurrently; they'll self-schedule based on arrival times
    await asyncio.gather(*[asyncio.create_task(t) for t in tasks])

    # Persist results
    os.makedirs(args.run_dir, exist_ok=True)

    # Export traces to OTLP JSON format
    traces_dir = os.path.join(args.run_dir, "traces")
    os.makedirs(traces_dir, exist_ok=True)
    trace_file = os.path.join(traces_dir, "traces.json")
    trace_collector.export_traces(trace_file)
    print(f"Exported {len(trace_collector.spans)} trace spans to {trace_file}")

    # Export requests CSV with trace IDs
    csv_path = os.path.join(args.run_dir, "requests.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "id",
                "scheduled_ms",
                "start_ms",
                "ttfb_ms",
                "tllt_ms",
                "latency_ms",
                "status",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "error",
                "trace_id",
            ]
        )
        for r in results:
            w.writerow(
                [
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
                    r.trace_id or "",
                ]
            )

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
    """CLI entrypoint for the OpenAI-compatible load tester."""
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--url",
        required=True,
        help="Base URL of endpoint (OpenAI-compatible), e.g., http://<host>",
    )
    ap.add_argument("--model", default="placeholder", help="Model name passed to API")
    ap.add_argument("--prompt", default="Hello, world!", help="Prompt to send")
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument(
        "--pattern",
        choices=["steady", "poisson", "bursty", "heavy"],
        default="steady",
        help="Traffic pattern: steady (even spacing), poisson (exponential arrivals), bursty (80%% in first 20%% of time), heavy (power-law tail)",
    )
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--insecure", action="store_true", help="Disable TLS verification")
    ap.add_argument(
        "--stream", action="store_true", help="Enable streaming responses (SSE)"
    )
    # Decoding parameters
    ap.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature (default: 0)",
    )
    ap.add_argument("--top-p", type=float, default=None, help="Nucleus sampling top-p")
    ap.add_argument(
        "--top-k", type=int, default=None, help="Top-k sampling (if supported)"
    )
    ap.add_argument(
        "--num-completions",
        type=int,
        default=None,
        help="Number of parallel completions (n)",
    )
    ap.add_argument("--presence-penalty", type=float, default=None)
    ap.add_argument("--frequency-penalty", type=float, default=None)
    ap.add_argument(
        "--json-mode", action="store_true", help="Set response_format to json_object"
    )
    ap.add_argument(
        "--extra-openai-json",
        default=None,
        help="Path to JSON file with extra OpenAI payload fields",
    )
    args = ap.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("Aborted")
        sys.exit(130)


if __name__ == "__main__":
    main()
