#!/bin/bash

# Prompt cache hit ratio analysis for vLLM KServe services
# Usage: ./cache-probe.sh --namespace NS --service NAME --base-requests N

set -euo pipefail

# Required binaries
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found" >&2; exit 2; }

NAMESPACE="ml-prod"
SERVICE="demo-llm"
BASE_REQUESTS=100
PROM_URL=""
API_KEY=""
RUN_DIR=""
CACHE_ANALYSIS_OUTPUT="cache_analysis.json"

usage() {
  echo "Usage: $0 --namespace NS --service NAME [--base-requests N] [--prom-url URL] [--api-key KEY] [--run-dir DIR]" >&2
  echo "" >&2
  echo "Analyzes prompt cache hit ratio using deterministic probe sets:" >&2
  echo "  - repeat-80: 80% repeated prompts (high cache hit expected)" >&2
  echo "  - unique-100: 100% unique prompts (low cache hit expected)" >&2
  echo "  - Infers hit ratio from TTFT differences (heuristic when server metrics unavailable)" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --service)
      SERVICE="$2"
      shift 2
      ;;
    --base-requests)
      BASE_REQUESTS="$2"
      shift 2
      ;;
    --prom-url)
      PROM_URL="$2"
      shift 2
      ;;
    --api-key)
      API_KEY="$2"
      shift 2
      ;;
    --run-dir)
      RUN_DIR="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 1
      ;;
  esac
done

echo "=== Prompt Cache Analysis ==="
echo "Service: $SERVICE (namespace: $NAMESPACE)"
echo "Prom URL: ${PROM_URL:-none}"
echo "Base requests per probe: $BASE_REQUESTS"
echo ""

# Generate deterministic prompt sets
generate_prompt_sets() {
  local base_requests="$1"
  local output_dir="$2"

  mkdir -p "$output_dir"

  # Create repeat-80 set (20% unique, 80% repeated)
  python3 <<EOF
import json
import random

# Set deterministic seed for reproducibility
random.seed(42)

base_requests = $base_requests

# Generate base prompts (20% of total)
unique_count = max(1, base_requests // 5)  # 20%
base_prompts = []

for i in range(unique_count):
    # Create diverse but deterministic prompts
    prompt_types = [
        f"What are the main features of Python version 3.{i % 12}?",
        f"Explain the concept of {['recursion', 'inheritance', 'polymorphism', 'encapsulation'][i % 4]} in programming.",
        f"Write a brief summary of the year {2020 + (i % 5)}.",
        f"List {3 + (i % 7)} benefits of using cloud computing.",
        f"Describe the process of {['photosynthesis', 'mitosis', 'meiosis', 'evolution'][i % 4]}.",
    ]
    base_prompts.append(prompt_types[i % len(prompt_types)])

# Create repeat-80 set by repeating prompts
repeat_80_prompts = []
for i in range(base_requests):
    # 80% chance of using existing prompt, 20% chance of unique
    if i < unique_count:
        repeat_80_prompts.append(base_prompts[i])
    else:
        # Pick random existing prompt
        repeat_80_prompts.append(random.choice(base_prompts))

# Shuffle to make timing realistic
random.shuffle(repeat_80_prompts)

with open("$output_dir/repeat_80_prompts.json", "w") as f:
    json.dump(repeat_80_prompts, f, indent=2)

print(f"Generated repeat-80 set: {unique_count} unique prompts repeated across {len(repeat_80_prompts)} requests")

# Create unique-100 set (100% unique prompts)
unique_100_prompts = []
for i in range(base_requests):
    unique_100_prompts.append(f"Generate a unique response about topic #{i:04d}: What is the significance of the number {1000 + i} in mathematics and science?")

with open("$output_dir/unique_100_prompts.json", "w") as f:
    json.dump(unique_100_prompts, f, indent=2)

print(f"Generated unique-100 set: {len(unique_100_prompts)} unique prompts")
EOF
}

# Set up run directories
TS="$(date +%Y-%m-%d_%H-%M-%S)"
CACHE_RUN_DIR="${RUN_DIR:-runs/cache_analysis_$TS}"
mkdir -p "$CACHE_RUN_DIR"

echo "🎯 Generating deterministic prompt sets..."
generate_prompt_sets "$BASE_REQUESTS" "$CACHE_RUN_DIR"

# Get service URL
URL=$(kubectl get inferenceservice "$SERVICE" -n "$NAMESPACE" -o jsonpath='{.status.url}' || true)
if [[ -z "$URL" ]]; then
  echo "ERROR: Could not determine InferenceService URL. Ensure $SERVICE is READY in namespace $NAMESPACE." >&2
  exit 1
fi

echo "🔄 Running cache analysis experiments..."

# Function to run a single cache experiment
run_cache_experiment() {
  local prompt_file="$1"
  local experiment_name="$2"
  local run_dir="$3"

  echo "  Running $experiment_name experiment..."

  # Create custom loadtest script that reads prompts from file
  python3 <<EOF
import asyncio
import json
import sys
sys.path.append('scripts')

from scripts.loadtest import main_async
import argparse

# Load prompts from file
with open("$prompt_file") as f:
    prompts = json.load(f)

# Create args object
class Args:
    def __init__(self):
        self.url = "$URL"
        self.model = "cache-test"
        self.max_tokens = 64
        self.requests = len(prompts)
        self.concurrency = 10
        self.pattern = "steady"
        self.run_dir = "$run_dir"
        self.api_key = "${API_KEY:-}"
        self.insecure = False

async def run_with_prompts():
    args = Args()

    # Monkey patch to use custom prompts
    import scripts.loadtest as loadtest_module
    original_worker = loadtest_module.worker

    async def custom_worker(task_id, scheduled_time, args, results, sem, test_start_time):
        # Override prompt with the one from our list
        original_prompt = args.prompt
        args.prompt = prompts[(task_id - 1) % len(prompts)]
        await original_worker(task_id, scheduled_time, args, results, sem, test_start_time)
        args.prompt = original_prompt  # restore

    loadtest_module.worker = custom_worker

    # Run the test
    await loadtest_module.main_async(args)

# Run the experiment
asyncio.run(run_with_prompts())
EOF
}

# Run repeat-80 experiment
REPEAT_80_DIR="$CACHE_RUN_DIR/repeat_80"
mkdir -p "$REPEAT_80_DIR"
run_cache_experiment "$CACHE_RUN_DIR/repeat_80_prompts.json" "repeat-80" "$REPEAT_80_DIR"

# Run unique-100 experiment
UNIQUE_100_DIR="$CACHE_RUN_DIR/unique_100"
mkdir -p "$UNIQUE_100_DIR"
run_cache_experiment "$CACHE_RUN_DIR/unique_100_prompts.json" "unique-100" "$UNIQUE_100_DIR"

# Wait between experiments for cache to potentially reset
sleep 30

echo "📊 Analyzing cache hit ratio..."

# Analyze results and compute inferred hit ratio
python3 <<EOF
import json
import csv
import statistics
import math

def load_experiment_results(run_dir):
    """Load experiment results and compute TTFT statistics."""
    csv_path = f"{run_dir}/requests.csv"
    ttft_times = []

    try:
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['status'] == '200' and row['ttfb_ms']:
                    ttft_times.append(float(row['ttfb_ms']))

        if not ttft_times:
            return None

        return {
            'count': len(ttft_times),
            'mean_ttft': statistics.mean(ttft_times),
            'median_ttft': statistics.median(ttft_times),
            'p95_ttft': sorted(ttft_times)[int(0.95 * len(ttft_times))],
            'std_ttft': statistics.stdev(ttft_times) if len(ttft_times) > 1 else 0
        }
    except Exception as e:
        print(f"Error loading {run_dir}: {e}")
        return None

# Load both experiments
repeat_80_stats = load_experiment_results("$REPEAT_80_DIR")
unique_100_stats = load_experiment_results("$UNIQUE_100_DIR")

if not repeat_80_stats or not unique_100_stats:
    print("ERROR: Could not load experiment results")
    exit(1)

# Calculate inferred cache hit ratio using TTFT differences
# Theory: Cache hits should have faster TTFT due to skipped prompt processing
repeat_mean_ttft = repeat_80_stats['mean_ttft']
unique_mean_ttft = unique_100_stats['mean_ttft']

if unique_mean_ttft > 0:
    # Inferred hit ratio based on TTFT improvement
    ttft_improvement = max(0, (unique_mean_ttft - repeat_mean_ttft) / unique_mean_ttft)
    # Scale by expected cache hit rate (80% for repeat-80 set)
    inferred_hit_ratio = min(1.0, ttft_improvement / 0.8)  # Normalize by theoretical max
else:
    inferred_hit_ratio = 0.0

# Statistical significance test (simple t-test approximation)
pooled_std = math.sqrt(
    (repeat_80_stats['std_ttft']**2 + unique_100_stats['std_ttft']**2) / 2
)
t_statistic = abs(repeat_mean_ttft - unique_mean_ttft) / (
    pooled_std * math.sqrt(2 / min(repeat_80_stats['count'], unique_100_stats['count']))
) if pooled_std > 0 else 0

# Generate analysis report
analysis = {
    "cache_analysis": {
        "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "service": "$SERVICE",
        "namespace": "$NAMESPACE",
        "method": "ttft_heuristic",
        "experiments": {
            "repeat_80": {
                "description": "80% repeated prompts (high cache hit expected)",
                "prompts_file": "$CACHE_RUN_DIR/repeat_80_prompts.json",
                "results_dir": "$REPEAT_80_DIR",
                **repeat_80_stats
            },
            "unique_100": {
                "description": "100% unique prompts (low cache hit expected)",
                "prompts_file": "$CACHE_RUN_DIR/unique_100_prompts.json",
                "results_dir": "$UNIQUE_100_DIR",
                **unique_100_stats
            }
        },
        "analysis": {
            "inferred_hit_ratio": inferred_hit_ratio,
            "ttft_improvement_pct": (unique_mean_ttft - repeat_mean_ttft) / unique_mean_ttft * 100 if unique_mean_ttft > 0 else 0,
            "statistical_significance": "significant" if t_statistic > 2.0 else "not_significant",
            "t_statistic": t_statistic,
            "interpretation": {
                "cache_effectiveness": "high" if inferred_hit_ratio > 0.6 else "moderate" if inferred_hit_ratio > 0.3 else "low",
                "ttft_benefit_ms": unique_mean_ttft - repeat_mean_ttft,
                "confidence": "medium" if t_statistic > 1.5 else "low"
            }
        },
        "caveats": [
            "Hit ratio is inferred from TTFT differences, not direct server metrics",
            "Assumes cache hits primarily affect prompt processing time",
            "Results may vary with model size, hardware, and vLLM configuration",
            "Small sample sizes may reduce statistical confidence"
        ]
    }
}

# Save analysis
with open("$CACHE_RUN_DIR/$CACHE_ANALYSIS_OUTPUT", "w") as f:
    json.dump(analysis, f, indent=2)

# Print summary
print(f"\\n=== Cache Analysis Results ===")
print(f"Service: $SERVICE")
print(f"")
print(f"📈 TTFT Comparison:")
print(f"  Repeat-80 (cached):  {repeat_mean_ttft:.1f}ms avg (n={repeat_80_stats['count']})")
print(f"  Unique-100 (uncached): {unique_mean_ttft:.1f}ms avg (n={unique_100_stats['count']})")
print(f"")
print(f"🎯 Inferred Cache Performance:")
print(f"  Hit Ratio: {inferred_hit_ratio:.1%}")
print(f"  TTFT Improvement: {((unique_mean_ttft - repeat_mean_ttft) / unique_mean_ttft * 100) if unique_mean_ttft > 0 else 0:.1f}%")
print(f"  Cache Effectiveness: {analysis['cache_analysis']['analysis']['interpretation']['cache_effectiveness']}")
print(f"  Statistical Confidence: {analysis['cache_analysis']['analysis']['interpretation']['confidence']}")
print(f"")

if inferred_hit_ratio > 0.5:
    print("✅ Cache appears to be working effectively")
    print("💡 Consider increasing cache size or TTL for better hit rates")
elif inferred_hit_ratio > 0.2:
    print("⚠️  Moderate cache effectiveness detected")
    print("💡 Check vLLM cache configuration and prompt patterns")
else:
    print("❌ Low or no cache effectiveness detected")
    print("💡 Verify vLLM prompt caching is enabled and configured")
    print("💡 Check if prompts are sufficiently similar for caching")

print(f"")
print(f"📄 Detailed analysis: $CACHE_RUN_DIR/$CACHE_ANALYSIS_OUTPUT")
print(f"📂 Raw experiment data: $REPEAT_80_DIR, $UNIQUE_100_DIR")
EOF

echo ""
echo "=== Cache Analysis Complete ==="
echo "Results available in: $CACHE_RUN_DIR"
