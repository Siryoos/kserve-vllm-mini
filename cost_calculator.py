#!/usr/bin/env python3

"""
This script calculates the cost of running a model on a GPU based on the load test results.
"""

import argparse
import sys


def main():
    """Main function."""

    parser = argparse.ArgumentParser(
        description="Calculate the cost of running a model on a GPU."
    )
    parser.add_argument(
        "results_file",
        type=str,
        help="Path to the load test results file.",
    )
    parser.add_argument(
        "gpu_hourly_cost",
        type=float,
        help="GPU hourly cost in USD.",
    )
    parser.add_argument(
        "--requests-per-1k-tokens",
        type=int,
        default=10,
        help="Number of requests to produce 1K tokens.",
    )
    args = parser.parse_args()

    try:
        with open(args.results_file) as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Results file '{args.results_file}' not found!", file=sys.stderr)
        sys.exit(1)

    successful_requests = [line for line in lines if line.split()[1] == "200"]

    if not successful_requests:
        print("No successful requests found. Cannot calculate cost.")
        sys.exit(1)

    avg_latency_ms = sum(float(line.split()[0]) for line in successful_requests) / len(
        successful_requests
    )
    avg_latency_seconds = avg_latency_ms / 1000

    gpu_price_per_second = args.gpu_hourly_cost / 3600

    cost_per_1k_tokens = (
        gpu_price_per_second * avg_latency_seconds * args.requests_per_1k_tokens
    )

    print("=== COST CALCULATION ===")
    print(f"GPU hourly cost: ${args.gpu_hourly_cost:.2f}")
    print(f"Requests per 1K tokens: {args.requests_per_1k_tokens}")
    print(f"Results file: {args.results_file}")
    print()

    print("=== METRICS ===")
    print(f"Successful requests: {len(successful_requests)}")
    print(f"Average latency: {avg_latency_ms:.2f}ms ({avg_latency_seconds:.4f}s)")
    print()

    print("=== COST ESTIMATION ===")
    print(f"GPU price per second: ${gpu_price_per_second:.6f}")
    print(f"Average latency (seconds): {avg_latency_seconds:.4f}")
    print(f"Requests per 1K tokens: {args.requests_per_1k_tokens}")
    print()
    print(f"Cost per 1K tokens: ${cost_per_1k_tokens:.6f}")


if __name__ == "__main__":
    main()
