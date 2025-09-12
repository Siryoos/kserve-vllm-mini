#!/usr/bin/env python3
"""
Backend comparison harness for KServe inference runtimes.

Compares vLLM, TGI (Text Generation Inference), and TensorRT-LLM performance
across standardized benchmarks to answer the open KServe request for
comprehensive inference runtime comparisons.
"""

import argparse
import asyncio
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class BackendResult:
    """Results from benchmarking a single backend."""

    backend: str
    runtime: str
    model: str
    profile: str
    success: bool
    error: Optional[str] = None

    # Performance metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    avg_ttft_ms: float = 0.0
    throughput_rps: float = 0.0
    tokens_per_sec: float = 0.0

    # Cost and efficiency
    cost_per_1k_tokens: float = 0.0
    cost_per_request: float = 0.0
    energy_per_1k_tokens_wh: float = 0.0

    # Resource utilization
    avg_gpu_util_pct: float = 0.0
    avg_gpu_memory_util_pct: float = 0.0
    peak_memory_gb: float = 0.0

    # Deployment characteristics
    deployment_time_s: float = 0.0
    cold_start_count: int = 0


@dataclass
class ComparisonSummary:
    """Summary comparison across all backends."""

    model: str
    profile: str
    timestamp: str
    results: List[BackendResult]

    def get_winner(self, metric: str) -> Optional[str]:
        """Get the backend with the best value for a given metric."""
        valid_results = [r for r in self.results if r.success]
        if not valid_results:
            return None

        if metric in [
            "avg_latency_ms",
            "p95_latency_ms",
            "avg_ttft_ms",
            "cost_per_1k_tokens",
            "deployment_time_s",
        ]:
            # Lower is better
            best = min(valid_results, key=lambda r: getattr(r, metric, float("inf")))
        elif metric in ["throughput_rps", "tokens_per_sec", "avg_gpu_util_pct"]:
            # Higher is better
            best = max(valid_results, key=lambda r: getattr(r, metric, 0))
        else:
            return None

        return best.backend


class BackendComparator:
    """Manages backend comparison benchmarks."""

    def __init__(self, namespace: str = "ml-prod", cost_file: str = "cost.yaml"):
        self.namespace = namespace
        self.cost_file = cost_file
        self.backends = {
            "vllm": "vllm",
            "tgi": "huggingface-text-generation-inference",
            "tensorrt": "tensorrt-llm",
        }

    async def run_single_backend(
        self,
        backend: str,
        runtime: str,
        model: str,
        profile_path: str,
        service_name: str,
    ) -> BackendResult:
        """Run benchmark against a single backend."""

        result = BackendResult(
            backend=backend,
            runtime=runtime,
            model=model,
            profile=Path(profile_path).stem,
        )

        print(f"Benchmarking {backend} with profile {result.profile}...")

        try:
            deploy_start = time.time()

            # Load profile for benchmark parameters early
            with open(profile_path) as f:
                profile = yaml.safe_load(f)

            if backend == "tensorrt":
                # Use Triton TensorRT-LLM deploy/invoke adapters
                # Deploy
                deploy_cmd = [
                    "runners/backends/triton/deploy.sh",
                    "--model",
                    service_name,
                    "--namespace",
                    self.namespace,
                    "--streaming",
                    "false",
                    "--model-repo",
                    model,
                ]
                deploy_result = subprocess.run(
                    deploy_cmd, capture_output=True, text=True, timeout=900
                )
                if deploy_result.returncode != 0:
                    result.error = f"Deployment failed: {deploy_result.stderr}"
                    return result

                # Wait for readiness
                wait_cmd = [
                    "kubectl",
                    "wait",
                    "--for=condition=Ready",
                    "--timeout=900s",
                    f"inferenceservice/{service_name}",
                    "-n",
                    self.namespace,
                ]
                wait = subprocess.run(
                    wait_cmd, capture_output=True, text=True, timeout=930
                )
                if wait.returncode != 0:
                    result.error = f"Service not ready: {wait.stderr}"
                    return result

                result.deployment_time_s = time.time() - deploy_start

                # Discover URL
                url_cmd = [
                    "kubectl",
                    "get",
                    "inferenceservice",
                    service_name,
                    "-n",
                    self.namespace,
                    "-o",
                    "jsonpath={.status.url}",
                ]
                url_res = subprocess.run(
                    url_cmd, capture_output=True, text=True, timeout=60
                )
                service_url = url_res.stdout.strip()
                if not service_url:
                    result.error = "Failed to discover service URL"
                    return result

                # Run Triton-specific load test
                run_dir = Path("runs") / f"{service_name}"
                run_dir.mkdir(parents=True, exist_ok=True)
                bench_cmd = [
                    "runners/backends/triton/invoke.sh",
                    "--url",
                    service_url,
                    "--requests",
                    str(profile.get("requests", 200)),
                    "--concurrency",
                    str(profile.get("concurrency", 10)),
                    "--pattern",
                    profile.get("pattern", "steady"),
                    "--max-tokens",
                    str(profile.get("max_tokens", 64)),
                    "--streaming",
                    "false",
                    "--run-dir",
                    str(run_dir),
                ]
                bench_result = subprocess.run(
                    bench_cmd, capture_output=True, text=True, timeout=1800
                )
                if bench_result.returncode != 0:
                    result.error = f"Benchmark failed: {bench_result.stderr}"
                    return result

                # Parse Triton results
                results_file = run_dir / "results.json"
                if not results_file.exists():
                    result.error = "Results file not found"
                    return result

                with open(results_file) as f:
                    bench_data = json.load(f)

                result.total_requests = bench_data.get("total_requests", 0)
                result.successful_requests = bench_data.get("successful_requests", 0)
                result.failed_requests = bench_data.get("failed_requests", 0)
                # Triton adapter uses total_ms metrics
                result.p95_latency_ms = bench_data.get(
                    "p95_total_ms", bench_data.get("p95_latency_ms", 0)
                )
                result.avg_ttft_ms = bench_data.get(
                    "mean_ttfb_ms", bench_data.get("avg_ttft_ms", 0)
                )
                result.throughput_rps = bench_data.get(
                    "throughput_req_per_sec", bench_data.get("throughput_rps", 0)
                )
                result.tokens_per_sec = bench_data.get("tokens_per_sec", 0.0)
                result.cost_per_1k_tokens = bench_data.get("cost_per_1k_tokens", 0)
                result.avg_gpu_util_pct = bench_data.get("gpu_utilization_avg", 0)
                result.success = True

            else:
                # Generic deploy via deploy.sh
                deploy_cmd = [
                    "./deploy.sh",
                    "--namespace",
                    self.namespace,
                    "--service",
                    service_name,
                    "--runtime",
                    runtime,
                    "--model-uri",
                    model,
                ]

                deploy_result = subprocess.run(
                    deploy_cmd, capture_output=True, text=True, timeout=600
                )

                if deploy_result.returncode != 0:
                    result.error = f"Deployment failed: {deploy_result.stderr}"
                    return result

                result.deployment_time_s = time.time() - deploy_start

                # Run standard benchmark via bench.sh (OpenAI-compatible)
                bench_cmd = [
                    "./bench.sh",
                    "--namespace",
                    self.namespace,
                    "--service",
                    service_name,
                    "--requests",
                    str(profile.get("requests", 200)),
                    "--concurrency",
                    str(profile.get("concurrency", 10)),
                    "--max-tokens",
                    str(profile.get("max_tokens", 64)),
                    "--pattern",
                    profile.get("pattern", "steady"),
                    "--model",
                    model,
                    "--cost-file",
                    self.cost_file,
                ]

                bench_result = subprocess.run(
                    bench_cmd,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )

                if bench_result.returncode != 0:
                    result.error = f"Benchmark failed: {bench_result.stderr}"
                    return result

                # Parse results from the most recent run
                runs_dir = Path("runs")
                if runs_dir.exists():
                    latest_run = max(
                        runs_dir.iterdir(), key=lambda p: p.stat().st_mtime
                    )
                    results_file = latest_run / "results.json"

                    if results_file.exists():
                        with open(results_file) as f:
                            bench_data = json.load(f)

                        # Extract metrics
                        result.total_requests = bench_data.get("total_requests", 0)
                        result.successful_requests = bench_data.get(
                            "successful_requests", 0
                        )
                        result.failed_requests = bench_data.get("failed_requests", 0)
                        result.avg_latency_ms = bench_data.get("avg_latency_ms", 0)
                        result.p50_latency_ms = bench_data.get("p50_latency_ms", 0)
                        result.p95_latency_ms = bench_data.get("p95_latency_ms", 0)
                        result.p99_latency_ms = bench_data.get("p99_latency_ms", 0)
                        result.avg_ttft_ms = bench_data.get("avg_ttft_ms", 0)
                        result.throughput_rps = bench_data.get("throughput_rps", 0)
                        result.tokens_per_sec = bench_data.get("tokens_per_sec", 0)
                        result.cost_per_1k_tokens = bench_data.get(
                            "cost_per_1k_tokens", 0
                        )
                        result.cost_per_request = bench_data.get("cost_per_request", 0)
                        result.energy_per_1k_tokens_wh = bench_data.get(
                            "energy_per_1k_tokens_wh", 0
                        )
                        result.avg_gpu_util_pct = bench_data.get(
                            "avg_gpu_utilization_pct", 0
                        )
                        result.avg_gpu_memory_util_pct = bench_data.get(
                            "avg_gpu_memory_utilization_pct", 0
                        )
                        result.peak_memory_gb = bench_data.get("peak_memory_gb", 0)
                        result.cold_start_count = bench_data.get("cold_start_count", 0)

                        result.success = True
                    else:
                        result.error = "Results file not found"
                else:
                    result.error = "No benchmark runs found"

        except subprocess.TimeoutExpired:
            result.error = "Benchmark timed out"
        except Exception as e:
            result.error = f"Unexpected error: {str(e)}"
        finally:
            # Cleanup: delete the service
            try:
                subprocess.run(
                    [
                        "kubectl",
                        "delete",
                        "inferenceservice",
                        service_name,
                        "-n",
                        self.namespace,
                    ],
                    capture_output=True,
                )
            except Exception:
                pass  # Best effort cleanup

        return result

    def generate_comparison_report(
        self, summary: ComparisonSummary, output_dir: Path
    ) -> None:
        """Generate HTML and JSON comparison reports."""

        # JSON report
        json_file = output_dir / "backend_comparison.json"
        with open(json_file, "w") as f:
            json.dump(asdict(summary), f, indent=2)

        # HTML report
        html_content = self._generate_html_report(summary)
        html_file = output_dir / "backend_comparison.html"
        with open(html_file, "w") as f:
            f.write(html_content)

        # CSV for data analysis
        csv_file = output_dir / "backend_comparison.csv"
        self._generate_csv_report(summary, csv_file)

        print("Reports generated:")
        print(f"  JSON: {json_file}")
        print(f"  HTML: {html_file}")
        print(f"  CSV: {csv_file}")

    def _generate_html_report(self, summary: ComparisonSummary) -> str:
        """Generate an HTML comparison report."""
        successful_results = [r for r in summary.results if r.success]

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Backend Comparison: {summary.model} - {summary.profile}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        .winner {{ background-color: #e8f5e8; font-weight: bold; }}
        .failed {{ background-color: #ffe8e8; }}
        .metric-section {{ margin: 30px 0; }}
    </style>
</head>
<body>
    <h1>KServe Backend Comparison</h1>
    <p><strong>Model:</strong> {summary.model}</p>
    <p><strong>Profile:</strong> {summary.profile}</p>
    <p><strong>Timestamp:</strong> {summary.timestamp}</p>

    <div class="metric-section">
        <h2>Performance Summary</h2>
        <table>
            <tr>
                <th>Backend</th>
                <th>Status</th>
                <th>P95 Latency (ms)</th>
                <th>TTFT (ms)</th>
                <th>Throughput (RPS)</th>
                <th>Tokens/sec</th>
                <th>Cost per 1K tokens</th>
                <th>Deployment time (s)</th>
            </tr>
"""

        for result in summary.results:
            if result.success:
                row_class = ""
                status = "✅ Success"
            else:
                row_class = "failed"
                status = f"❌ {result.error or 'Failed'}"

            html += f"""
            <tr class="{row_class}">
                <td>{result.backend}</td>
                <td>{status}</td>
                <td>{result.p95_latency_ms:.1f}</td>
                <td>{result.avg_ttft_ms:.1f}</td>
                <td>{result.throughput_rps:.1f}</td>
                <td>{result.tokens_per_sec:.1f}</td>
                <td>${result.cost_per_1k_tokens:.4f}</td>
                <td>{result.deployment_time_s:.1f}</td>
            </tr>
"""

        html += """
        </table>
    </div>

    <div class="metric-section">
        <h2>Winners by Metric</h2>
        <table>
            <tr><th>Metric</th><th>Winner</th></tr>
"""

        metrics = [
            ("p95_latency_ms", "Lowest P95 Latency"),
            ("avg_ttft_ms", "Fastest Time to First Token"),
            ("throughput_rps", "Highest Throughput"),
            ("tokens_per_sec", "Highest Token Rate"),
            ("cost_per_1k_tokens", "Lowest Cost per 1K Tokens"),
            ("deployment_time_s", "Fastest Deployment"),
        ]

        for metric, label in metrics:
            winner = summary.get_winner(metric)
            html += f"<tr><td>{label}</td><td>{winner or 'N/A'}</td></tr>"

        html += """
        </table>
    </div>

    <div class="metric-section">
        <h2>Resource Utilization</h2>
        <table>
            <tr>
                <th>Backend</th>
                <th>Avg GPU Util (%)</th>
                <th>Avg GPU Memory Util (%)</th>
                <th>Peak Memory (GB)</th>
                <th>Cold Starts</th>
            </tr>
"""

        for result in successful_results:
            html += f"""
            <tr>
                <td>{result.backend}</td>
                <td>{result.avg_gpu_util_pct:.1f}%</td>
                <td>{result.avg_gpu_memory_util_pct:.1f}%</td>
                <td>{result.peak_memory_gb:.1f}</td>
                <td>{result.cold_start_count}</td>
            </tr>
"""

        html += """
        </table>
    </div>

    <footer>
        <p><em>Generated by kserve-vllm-mini backend comparison harness</em></p>
    </footer>
</body>
</html>
"""
        return html

    def _generate_csv_report(self, summary: ComparisonSummary, csv_file: Path) -> None:
        """Generate CSV report for data analysis."""
        import csv

        with open(csv_file, "w", newline="") as f:
            if not summary.results:
                return

            writer = csv.DictWriter(f, fieldnames=asdict(summary.results[0]).keys())
            writer.writeheader()

            for result in summary.results:
                writer.writerow(asdict(result))


async def main():
    parser = argparse.ArgumentParser(
        description="Compare KServe inference runtime backends"
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model URI to benchmark across backends",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="runners/profiles/standard.yaml",
        help="Benchmark profile to use",
    )
    parser.add_argument(
        "--backends",
        type=str,
        nargs="+",
        default=["vllm", "tgi"],
        choices=["vllm", "tgi", "tensorrt"],
        help="Backends to compare",
    )
    parser.add_argument(
        "--namespace", type=str, default="ml-prod", help="Kubernetes namespace"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="backend-comparison",
        help="Output directory for reports",
    )
    parser.add_argument(
        "--cost-file", type=str, default="cost.yaml", help="Cost configuration file"
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    comparator = BackendComparator(args.namespace, args.cost_file)
    results = []

    print(f"Starting backend comparison for model: {args.model}")
    print(f"Profile: {args.profile}")
    print(f"Backends: {args.backends}")

    for backend in args.backends:
        if backend not in comparator.backends:
            print(f"Warning: Unknown backend {backend}, skipping")
            continue

        runtime = comparator.backends[backend]
        service_name = f"compare-{backend}-{int(time.time())}"

        result = await comparator.run_single_backend(
            backend, runtime, args.model, args.profile, service_name
        )

        results.append(result)

        if result.success:
            print(
                f"✅ {backend}: P95={result.p95_latency_ms:.1f}ms, "
                f"RPS={result.throughput_rps:.1f}, Cost=${result.cost_per_1k_tokens:.4f}/1K"
            )
        else:
            print(f"❌ {backend}: {result.error}")

    # Generate comparison summary
    summary = ComparisonSummary(
        model=args.model,
        profile=Path(args.profile).stem,
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        results=results,
    )

    # Generate reports
    comparator.generate_comparison_report(summary, output_dir)

    print(f"\nBackend comparison complete. Results saved to {output_dir}/")

    # Print summary to console
    successful = [r for r in results if r.success]
    if successful:
        print(f"\nSuccessful benchmarks: {len(successful)}/{len(results)}")

        best_latency = min(successful, key=lambda r: r.p95_latency_ms)
        best_throughput = max(successful, key=lambda r: r.throughput_rps)
        best_cost = min(successful, key=lambda r: r.cost_per_1k_tokens)

        print(
            f"Best P95 latency: {best_latency.backend} ({best_latency.p95_latency_ms:.1f}ms)"
        )
        print(
            f"Best throughput: {best_throughput.backend} ({best_throughput.throughput_rps:.1f} RPS)"
        )
        print(
            f"Best cost efficiency: {best_cost.backend} (${best_cost.cost_per_1k_tokens:.4f}/1K tokens)"
        )


if __name__ == "__main__":
    asyncio.run(main())
