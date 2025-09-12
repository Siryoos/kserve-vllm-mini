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
        epilog="""
Available commands:
  plan      - Capacity & budget planning for KServe vLLM deployments
  analyze   - Analyze benchmark run results
  report    - Generate comprehensive reports
  calculate - Cost calculation utilities
  bench     - Run benchmarks (uses bench.sh)
  deploy    - Deploy configurations (uses deploy.sh)

Examples:
  kvmini plan --help
  kvmini analyze --run-dir runs/2025-01-01_12-00-00 --namespace ml-prod --service demo-llm
  kvmini report --input results.json --format html
        """,
    )

    parser.add_argument(
        "command",
        choices=["plan", "analyze", "report", "calculate", "bench", "deploy"],
        help="Command to execute",
    )

    # Parse known args to get the command, then pass the rest to the script
    args, remaining = parser.parse_known_args()

    # Map commands to scripts
    script_map = {
        "plan": "planner.py",
        "analyze": "analyze.py",
        "report": "report_generator.py",
        "calculate": "cost_calculator.py",
        "bench": "bench.sh",
        "deploy": "deploy.sh",
    }

    script = script_map.get(args.command)
    if not script:
        print(f"Unknown command: {args.command}")
        return 1

    # For shell scripts, use bash
    if script.endswith(".sh"):
        project_root = get_project_root()
        script_path = project_root / script

        if not script_path.exists():
            print(f"Error: Script {script} not found at {script_path}")
            return 1

        cmd = ["bash", str(script_path)] + remaining
        return subprocess.run(cmd).returncode
    else:
        # For Python scripts
        return run_script(script, remaining)


if __name__ == "__main__":
    sys.exit(main())
