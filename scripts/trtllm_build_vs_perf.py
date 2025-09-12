#!/usr/bin/env python3
"""
TensorRT-LLM build-time vs inference-performance tradeoff benchmarking.

This script consumes a TensorRT-LLM engine profile YAML (profiles/tensorrt-llm/*)
and optionally an engine builder command template, then:

1) Builds the TensorRT-LLM engine and times the build
2) Deploys a Triton TensorRT-LLM InferenceService (via runners/backends/triton/deploy.sh)
3) Executes a load test against KServe v2 endpoints (via runners/backends/triton/invoke.sh)
4) Emits a CSV with build time and performance metrics to compare tradeoffs

Notes:
- This script only orchestrates commands; it assumes you have the necessary
  tools installed and access to a Kubernetes cluster with KServe and Triton.
- The builder command is passed via --builder-cmd. If omitted, the build step
  is skipped and the script will only deploy + benchmark.
"""

import argparse
import csv
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import yaml


def redact_cmd(cmd) -> str:
    s = cmd if isinstance(cmd, str) else " ".join(cmd)
    s = re.sub(
        r"(--?(?:api[-_]?key|token|password|pass|secret)\s+)(\S+)",
        r"\1****",
        s,
        flags=re.I,
    )
    s = re.sub(r"(Authorization:\s*Bearer\s+)\S+", r"\1****", s, flags=re.I)
    return s


def dns1123_label(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if len(s) > 63:
        s = s[:63].rstrip("-")
    if not s or not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", s):
        s = f"trtllm-{int(time.time())}"
    return s


def run(cmd, timeout=None, cwd=None, env=None, check=True):
    """Run a command (list or string), returning (proc, duration_seconds).

    Prints a redacted command, captures output, and optionally raises on non‑zero rc.
    """
    print(f"$ {redact_cmd(cmd)}")
    start = time.time()
    proc = subprocess.run(
        cmd if isinstance(cmd, list) else shlex.split(cmd),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    duration = time.time() - start
    if check and proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed ({proc.returncode}): {cmd}")
    return proc, duration


def wait_for_isvc_ready(namespace: str, service: str, timeout_s: int = 600):
    """Block until the specified InferenceService reports Ready or times out."""
    cmd = [
        "kubectl",
        "wait",
        "--for=condition=Ready",
        f"--timeout={timeout_s}s",
        f"inferenceservice/{service}",
        "-n",
        namespace,
    ]
    run(cmd, timeout=timeout_s + 30)


def get_isvc_url(namespace: str, service: str) -> str:
    """Return the external URL for a KServe InferenceService (may be empty)."""
    cmd = [
        "kubectl",
        "get",
        "inferenceservice",
        service,
        "-n",
        namespace,
        "-o",
        "jsonpath={.status.url}",
    ]
    proc, _ = run(cmd, check=False)
    url = proc.stdout.strip()
    if not url:
        cmd = [
            "kubectl",
            "get",
            "inferenceservice",
            service,
            "-n",
            namespace,
            "-o",
            "jsonpath={.status.components.predictor.url}",
        ]
        proc, _ = run(cmd, check=False)
        url = proc.stdout.strip()
    return url


def build_engine_if_configured(profile: dict, builder_cmd_tmpl: str | None):
    """Optionally run a builder command (templated by `profile`) and time it."""
    if not builder_cmd_tmpl:
        print("No --builder-cmd provided; skipping engine build step.")
        return {"build_time_s": 0.0}

    # Prepare substitutions
    subs = {**profile}
    subs.update(profile.get("builder_flags", {}))

    # Helper: include quantization flag only if set
    quant = profile.get("quantization", "none")
    subs["quantization_arg"] = (
        "" if quant in (None, "", "none") else f"--quantization {quant}"
    )

    # Fill template safely
    try:
        builder_cmd = builder_cmd_tmpl.format(**subs)
    except KeyError as e:
        raise KeyError(
            f"Missing placeholder {e!s} in --builder-cmd template; available keys: {sorted(subs.keys())}"
        ) from e
    print(f"Builder command: {redact_cmd(builder_cmd)}")

    # Time the build
    env = None
    if isinstance(profile.get("runtime_env"), dict):
        env = {**os.environ, **{k: str(v) for k, v in profile["runtime_env"].items()}}
    _, build_time = run(builder_cmd, timeout=None, env=env)
    return {"build_time_s": round(build_time, 2)}


def deploy_triton_service(
    model: str, namespace: str, streaming: bool
) -> tuple[str, str]:
    """Deploy a Triton TRT-LLM service and return (service_name, url)."""
    svc_name = dns1123_label(f"{model}-trtllm-{int(time.time())}")
    cmd = [
        "runners/backends/triton/deploy.sh",
        "--model",
        svc_name,
        "--namespace",
        namespace,
        "--streaming",
        "true" if streaming else "false",
    ]
    run(cmd, timeout=900)
    wait_for_isvc_ready(namespace, svc_name, 900)
    url = get_isvc_url(namespace, svc_name)
    if not url:
        raise RuntimeError("Failed to get InferenceService URL")
    return svc_name, url


def run_triton_benchmark(
    url: str,
    requests: int,
    concurrency: int,
    max_tokens: int,
    streaming: bool,
    run_dir: Path,
):
    """Invoke Triton benchmark adapter and load results.json from run_dir."""
    run_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "runners/backends/triton/invoke.sh",
        "--url",
        url,
        "--requests",
        str(requests),
        "--concurrency",
        str(concurrency),
        "--pattern",
        "steady",
        "--max-tokens",
        str(max_tokens),
        "--streaming",
        "true" if streaming else "false",
        "--run-dir",
        str(run_dir),
    ]
    run(cmd, timeout=1800)
    results_file = run_dir / "results.json"
    if results_file.exists():
        with open(results_file) as f:
            return json.load(f)
    print(f"Warning: {results_file} not found; using empty metrics.", file=sys.stderr)
    return {}


def main():
    """CLI: build (optional), deploy TRT‑LLM via Triton, benchmark, write CSV."""
    ap = argparse.ArgumentParser(description="TRT-LLM build vs perf tradeoff bench")
    ap.add_argument("--profile", required=True, help="profiles/tensorrt-llm/*.yaml")
    ap.add_argument("--namespace", default="ml-prod")
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--streaming", action="store_true")
    ap.add_argument(
        "--builder-cmd",
        default=None,
        help="Builder command template with {placeholders} from profile",
    )
    ap.add_argument("--output", default="trtllm_tradeoffs.csv", help="CSV output path")
    args = ap.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.exists():
        raise SystemExit(f"Profile not found: {profile_path}")

    with open(profile_path) as f:
        profile = yaml.safe_load(f)

    # 1) Build engine (optional)
    build_info = build_engine_if_configured(profile, args.builder_cmd)

    # 2) Deploy Triton -> 3) Benchmark -> Cleanup
    service = None
    bench = {}
    try:
        service, url = deploy_triton_service(
            profile.get("model_name", "trtllm-model"), args.namespace, args.streaming
        )

        # 3) Benchmark
        run_dir = Path("runs") / f"trtllm-{int(time.time())}"
        bench = run_triton_benchmark(
            url,
            args.requests,
            args.concurrency,
            args.max_tokens,
            args.streaming,
            run_dir,
        )
    finally:
        # 4) Cleanup service (best-effort)
        if service:
            try:
                run(
                    [
                        "kubectl",
                        "delete",
                        "inferenceservice",
                        service,
                        "-n",
                        args.namespace,
                    ],
                    check=False,
                )
            except Exception:
                pass

    # 5) Write CSV
    row = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "model_family": profile.get("model_family"),
        "model_name": profile.get("model_name"),
        "dtype": profile.get("dtype"),
        "quantization": profile.get("quantization"),
        "kv_cache_dtype": profile.get("kv_cache_dtype"),
        "max_batch_size": profile.get("max_batch_size"),
        "max_input_len": profile.get("max_input_len"),
        "max_output_len": profile.get("max_output_len"),
        "tp_size": profile.get("tensor_parallel_size"),
        "pp_size": profile.get("pipeline_parallel_size"),
        "build_time_s": build_info.get("build_time_s", 0.0),
        "p95_total_ms": bench.get("p95_total_ms", 0.0),
        "throughput_req_per_sec": bench.get("throughput_req_per_sec", 0.0),
        "mean_ttfb_ms": bench.get("mean_ttfb_ms", 0.0),
    }

    out_path = Path(args.output)
    write_header = not out_path.exists()
    with open(out_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            w.writeheader()
        w.writerow(row)

    print("\n=== Tradeoff Result ===")
    for k, v in row.items():
        print(f"{k}: {v}")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
