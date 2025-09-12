"""
CLI interface for KServe vLLM Mini toolkit.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


def run_script(script_name, args):
    """Run a Python script from the project root."""
    project_root = get_project_root()
    script_path = project_root / script_name

    if not script_path.exists():
        print(f"Error: Script {script_name} not found at {script_path}")
        return 1

    # Execute the script with the provided arguments
    cmd = [sys.executable, str(script_path)] + args
    return subprocess.run(cmd).returncode


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="KServe vLLM Mini - Production-ready LLM inference benchmarking toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Available commands"
    )

    # --- Plan Command ---
    plan_parser = subparsers.add_parser(
        "plan", help="Capacity & budget planning for KServe vLLM deployments"
    )
    plan_parser.set_defaults(script="planner.py")

    # --- Analyze Command ---
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze benchmark run results"
    )
    analyze_parser.set_defaults(script="analyze.py")

    # --- Report Command ---
    report_parser = subparsers.add_parser(
        "report", help="Generate comprehensive reports"
    )
    report_parser.set_defaults(script="report_generator.py")

    # --- Calculate Command ---
    calculate_parser = subparsers.add_parser(
        "calculate", help="Cost calculation utilities"
    )
    calculate_parser.set_defaults(script="cost_calculator.py")

    # --- Deploy Command ---
    deploy_parser = subparsers.add_parser(
        "deploy", help="Deploy configurations (uses deploy.sh)"
    )
    deploy_parser.set_defaults(script="deploy.sh")

    # --- Bench Command ---
    bench_parser = subparsers.add_parser("bench", help="Run benchmarks (uses bench.sh)")
    bench_parser.add_argument(
        "--namespace", default="ml-prod", help="Kubernetes namespace"
    )
    bench_parser.add_argument(
        "--service", default="demo-llm", help="InferenceService name"
    )
    bench_parser.add_argument(
        "--url", help="InferenceService URL (if not discoverable)"
    )
    bench_parser.add_argument("--requests", type=int, help="Total number of requests")
    bench_parser.add_argument(
        "--concurrency", type=int, help="Number of concurrent requests"
    )
    bench_parser.add_argument("--model", help="Model name for the run")
    bench_parser.add_argument(
        "--max-tokens", type=int, help="Maximum number of tokens to generate"
    )
    bench_parser.add_argument(
        "--pattern",
        choices=["steady", "poisson", "bursty", "heavy"],
        help="Load test traffic pattern",
    )
    bench_parser.add_argument("--profile", help="Path to a benchmark profile YAML file")
    bench_parser.add_argument("--prom-url", help="Prometheus URL for metrics")
    bench_parser.add_argument("--api-key", help="API key for authentication")
    bench_parser.add_argument("--run-dir", help="Directory to save run artifacts")
    bench_parser.add_argument(
        "--insecure", action="store_true", help="Allow insecure connections"
    )
    bench_parser.add_argument("--cost-file", help="Path to the cost configuration file")
    bench_parser.add_argument(
        "--bundle", action="store_true", help="Bundle artifacts after the run"
    )
    bench_parser.add_argument(
        "--loadtest-args", help="Additional arguments for the load test script"
    )
    bench_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without running the benchmark",
    )
    bench_parser.add_argument(
        "--list-profiles", action="store_true", help="List available benchmark profiles"
    )
    bench_parser.set_defaults(script="bench.sh")

    # Parse known args to get the command, then pass the rest to the script
    args, remaining = parser.parse_known_args()

    script = args.script

    # Reconstruct the arguments for the script
    script_args = []
    arg_dict = vars(args)
    for key, value in arg_dict.items():
        if key in ["command", "script"]:
            continue
        if value is not None:
            # For store_true actions, only add the flag if True
            if isinstance(value, bool) and value:
                script_args.append(f"--{key.replace('_', '-')}")
            elif not isinstance(value, bool):
                script_args.extend([f"--{key.replace('_', '-')}", str(value)])

    # For shell scripts, use bash
    if script.endswith(".sh"):
        project_root = get_project_root()
        script_path = project_root / script

        if not script_path.exists():
            print(f"Error: Script {script} not found at {script_path}")
            return 1

        cmd = ["bash", str(script_path)] + script_args + remaining
        return subprocess.run(cmd).returncode
    else:
        # For Python scripts
        return run_script(script, script_args + remaining)


if __name__ == "__main__":
    sys.exit(main())
