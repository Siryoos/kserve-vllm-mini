#!/usr/bin/env python3
"""
Capacity & Budget Planner for KServe vLLM deployments.
Answers: "How many GPUs for N RPS at SLO and how much per month?"
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class CapacityPlanner:
    """Capacity planning based on measured performance data"""

    def __init__(self, cost_config_path: str = "cost.yaml"):
        self.cost_config = self._load_cost_config(cost_config_path)
        self.calibrated_baseline = None

    def _load_cost_config(self, path: str) -> Dict[str, Any]:
        """Load cost configuration"""
        if Path(path).exists():
            with open(path, "r") as f:
                return yaml.safe_load(f)
        return {
            "gpus": {
                "nvidia-tesla-a100-80gb": 3.06,
                "nvidia-tesla-l40s": 1.28,
                "nvidia-geforce-rtx-4090": 0.83,
            },
            "cpu_per_hour": 0.04761,
            "memory_per_gb_hour": 0.00638,
            "storage_per_gb_hour": 0.000137,
            "regions": {
                "us-central1": {"multiplier": 1.0},
                "us-east1": {"multiplier": 0.95},
                "europe-west1": {"multiplier": 1.1},
            },
        }

    def _load_run_history(self, run_dirs: List[str]) -> List[Dict[str, Any]]:
        """Load historical run data for planning"""
        runs = []
        for run_dir in run_dirs:
            results_file = Path(run_dir) / "results.json"
            if results_file.exists():
                with open(results_file) as f:
                    run_data = json.load(f)
                    runs.append(run_data)
        return runs

    def _calculate_base_capacity(
        self, target_rps: float, p95_budget_ms: float, mix_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate base capacity requirements from measured data"""

        # Default performance baselines (would be learned from run history)
        gpu_baselines = {
            "nvidia-tesla-a100-80gb": {"rps_per_gpu": 15.0, "p95_ms": 1200},
            "nvidia-tesla-l40s": {"rps_per_gpu": 12.0, "p95_ms": 1400},
            "nvidia-geforce-rtx-4090": {"rps_per_gpu": 10.0, "p95_ms": 1600},
        }
        # Override with calibrated baseline if available
        if self.calibrated_baseline:
            for k in gpu_baselines.keys():
                gpu_baselines[k].update(self.calibrated_baseline)

        capacity_options = []

        for gpu_type, baseline in gpu_baselines.items():
            # Account for latency headroom
            latency_factor = min(p95_budget_ms / baseline["p95_ms"], 2.0)
            effective_rps = baseline["rps_per_gpu"] * latency_factor

            # Calculate GPU count needed
            base_gpus = math.ceil(target_rps / effective_rps)

            # Add headroom for cold starts and bursts
            cold_headroom = mix_profile.get("cold_start_multiplier", 1.2)
            burst_headroom = mix_profile.get("burst_multiplier", 1.5)
            total_headroom = cold_headroom * burst_headroom

            recommended_gpus = math.ceil(base_gpus * total_headroom)

            # Calculate supporting resources
            cpu_cores = recommended_gpus * mix_profile.get("cpu_per_gpu", 4)
            memory_gb = recommended_gpus * mix_profile.get("memory_gb_per_gpu", 32)

            capacity_options.append(
                {
                    "gpu_type": gpu_type,
                    "gpu_count": recommended_gpus,
                    "cpu_cores": cpu_cores,
                    "memory_gb": memory_gb,
                    "effective_rps": effective_rps,
                    "headroom_factor": total_headroom,
                }
            )

        return {"options": capacity_options}

    def _calculate_costs(
        self, capacity: Dict[str, Any], region: str = "us-central1"
    ) -> Dict[str, Any]:
        """Calculate monthly costs for capacity options"""

        region_multiplier = (
            self.cost_config.get("regions", {}).get(region, {}).get("multiplier", 1.0)
        )
        hours_per_month = 24 * 30  # 720 hours

        cost_breakdown = []

        for option in capacity["options"]:
            gpu_type = option["gpu_type"]
            gpu_count = option["gpu_count"]
            cpu_cores = option["cpu_cores"]
            memory_gb = option["memory_gb"]

            # GPU costs
            gpu_hourly = self.cost_config["gpus"].get(gpu_type, 3.0)
            gpu_monthly = gpu_hourly * gpu_count * hours_per_month * region_multiplier

            # CPU costs
            cpu_monthly = (
                self.cost_config["cpu_per_hour"]
                * cpu_cores
                * hours_per_month
                * region_multiplier
            )

            # Memory costs
            memory_monthly = (
                self.cost_config["memory_per_gb_hour"]
                * memory_gb
                * hours_per_month
                * region_multiplier
            )

            # Storage costs (assume 100GB persistent disk per GPU)
            storage_gb = gpu_count * 100
            storage_monthly = (
                self.cost_config["storage_per_gb_hour"]
                * storage_gb
                * hours_per_month
                * region_multiplier
            )

            total_monthly = gpu_monthly + cpu_monthly + memory_monthly + storage_monthly

            cost_breakdown.append(
                {
                    "gpu_type": gpu_type,
                    "gpu_count": gpu_count,
                    "costs": {
                        "gpu_monthly": round(gpu_monthly, 2),
                        "cpu_monthly": round(cpu_monthly, 2),
                        "memory_monthly": round(memory_monthly, 2),
                        "storage_monthly": round(storage_monthly, 2),
                        "total_monthly": round(total_monthly, 2),
                    },
                    "region": region,
                    "region_multiplier": region_multiplier,
                }
            )

        return {"cost_breakdown": cost_breakdown}

    def _calculate_warm_pool_sizing(
        self, target_rps: float, mix_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate cold-start warm pool requirements"""

        # Cold start characteristics
        cold_start_time_s = mix_profile.get("cold_start_time_s", 45)
        cold_start_frequency = mix_profile.get(
            "cold_start_frequency", 0.1
        )  # 10% of requests
        target_cold_time_s = mix_profile.get(
            "target_cold_time_s", 10
        )  # Target cold time

        # Calculate warm pool size to minimize cold starts
        expected_cold_requests_per_min = target_rps * 60 * cold_start_frequency
        warm_pool_size = math.ceil(
            expected_cold_requests_per_min * (cold_start_time_s / 60)
        )

        # Minimum pool size (always keep some warm)
        min_pool_size = max(1, math.ceil(target_rps * 0.1))  # 10% of target RPS
        final_pool_size = max(warm_pool_size, min_pool_size)

        return {
            "warm_pool_size": final_pool_size,
            "cold_start_time_s": cold_start_time_s,
            "target_cold_time_s": target_cold_time_s,
            "expected_cold_requests_per_min": round(expected_cold_requests_per_min, 1),
        }

    def plan_capacity(
        self,
        target_rps: float,
        p95_budget_ms: float,
        mix_profile: Dict[str, Any],
        region: str = "us-central1",
        run_history: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate complete capacity and budget plan"""

        # Load historical data if provided
        if run_history:
            self._load_run_history(run_history)

        # Calculate base capacity requirements
        capacity = self._calculate_base_capacity(target_rps, p95_budget_ms, mix_profile)

        # Calculate costs
        costs = self._calculate_costs(capacity, region)

        # Calculate warm pool sizing
        warm_pool = self._calculate_warm_pool_sizing(target_rps, mix_profile)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            capacity, costs, warm_pool, target_rps, p95_budget_ms
        )

        return {
            "planning_inputs": {
                "target_rps": target_rps,
                "p95_budget_ms": p95_budget_ms,
                "region": region,
                "mix_profile": mix_profile,
            },
            "capacity_requirements": capacity,
            "cost_analysis": costs,
            "warm_pool_sizing": warm_pool,
            "recommendations": recommendations,
            "generated_at": self._get_timestamp(),
        }

    def calibrate_from_sweep_csv(self, csv_path: str) -> None:
        """Calibrate baseline rps_per_gpu and p95 from sweep CSV.

        Expects columns: throughput_rps, p95_ms, tensor_parallel_size
        """
        try:
            import pandas as pd

            df = pd.read_csv(csv_path)
            if not {"throughput_rps", "p95_ms", "tensor_parallel_size"} <= set(
                df.columns
            ):
                return
            df = df[df["tensor_parallel_size"] > 0]
            if df.empty:
                return
            # Compute per-GPU RPS
            df["rps_per_gpu"] = df["throughput_rps"] / df["tensor_parallel_size"]
            rps_pg = df["rps_per_gpu"].median()
            p95 = df["p95_ms"].median()
            self.calibrated_baseline = {
                "rps_per_gpu": float(rps_pg),
                "p95_ms": float(p95),
            }
        except Exception:
            pass

    def _generate_recommendations(
        self,
        capacity: Dict[str, Any],
        costs: Dict[str, Any],
        warm_pool: Dict[str, Any],
        target_rps: float,
        p95_budget_ms: float,
    ) -> List[Dict[str, Any]]:
        """Generate ranked recommendations"""

        recommendations = []

        # Combine capacity and cost data
        for i, option in enumerate(capacity["options"]):
            cost_data = costs["cost_breakdown"][i]

            # Calculate efficiency metrics
            cost_per_rps = cost_data["costs"]["total_monthly"] / target_rps
            gpu_utilization = target_rps / (
                option["gpu_count"] * option["effective_rps"]
            )

            # Score recommendation (lower is better)
            cost_score = (
                cost_data["costs"]["total_monthly"] / 1000
            )  # Normalize to ~1-10 range
            efficiency_score = 1 / max(gpu_utilization, 0.1)  # Penalize low utilization
            total_score = cost_score + efficiency_score

            recommendations.append(
                {
                    "rank": i + 1,  # Will be re-ranked
                    "gpu_type": option["gpu_type"],
                    "gpu_count": option["gpu_count"],
                    "monthly_cost": cost_data["costs"]["total_monthly"],
                    "cost_per_rps": round(cost_per_rps, 2),
                    "gpu_utilization": round(gpu_utilization * 100, 1),
                    "warm_pool_size": warm_pool["warm_pool_size"],
                    "score": round(total_score, 2),
                    "rationale": self._get_rationale(
                        option, cost_data, gpu_utilization
                    ),
                }
            )

        # Sort by score (lower is better)
        recommendations.sort(key=lambda x: x["score"])

        # Update ranks
        for i, rec in enumerate(recommendations):
            rec["rank"] = i + 1

        return recommendations

    def _get_rationale(
        self, option: Dict[str, Any], cost_data: Dict[str, Any], utilization: float
    ) -> str:
        """Generate human-readable rationale for recommendation"""

        gpu_type = option["gpu_type"].replace("nvidia-", "").replace("-", " ").title()
        monthly_cost = cost_data["costs"]["total_monthly"]

        if utilization > 0.8:
            efficiency = "High efficiency"
        elif utilization > 0.6:
            efficiency = "Good efficiency"
        elif utilization > 0.4:
            efficiency = "Moderate efficiency"
        else:
            efficiency = "Low efficiency"

        if monthly_cost < 1000:
            cost_tier = "Budget-friendly"
        elif monthly_cost < 5000:
            cost_tier = "Mid-range cost"
        else:
            cost_tier = "Premium option"

        return f"{cost_tier} with {gpu_type} GPUs. {efficiency} ({utilization * 100:.0f}% utilization)."

    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        try:
            from datetime import datetime

            return datetime.now().isoformat()
        except Exception:
            return "unknown"

    def generate_report(
        self, plan: Dict[str, Any], output_file: Optional[str] = None
    ) -> str:
        """Generate human-readable planning report"""

        inputs = plan["planning_inputs"]
        recommendations = plan["recommendations"]

        report = f"""# Capacity & Budget Planning Report

## Requirements
- **Target RPS**: {inputs["target_rps"]}
- **P95 Latency Budget**: {inputs["p95_budget_ms"]}ms
- **Region**: {inputs["region"]}

## Recommendations (Ranked by Cost-Efficiency)

"""

        for rec in recommendations:
            report += f"""### #{rec["rank"]}: {rec["gpu_type"].replace("-", " ").title()}
- **GPUs**: {rec["gpu_count"]} units
- **Monthly Cost**: ${rec["monthly_cost"]:,}
- **Cost per RPS**: ${rec["cost_per_rps"]}/RPS/month
- **GPU Utilization**: {rec["gpu_utilization"]}%
- **Warm Pool Size**: {rec["warm_pool_size"]} replicas
- **Rationale**: {rec["rationale"]}

"""

        # Add warm pool analysis
        warm_pool = plan["warm_pool_sizing"]
        report += f"""## Cold Start Mitigation
- **Recommended Warm Pool**: {warm_pool["warm_pool_size"]} replicas
- **Cold Start Time**: {warm_pool["cold_start_time_s"]}s
- **Expected Cold Requests**: {warm_pool["expected_cold_requests_per_min"]}/min

## Next Steps
1. **Validate assumptions** by running benchmarks with your actual workload
2. **Start with the #1 recommendation** and monitor performance
3. **Adjust warm pool size** based on observed cold start patterns
4. **Consider autoscaling** between min=warm_pool_size and max=gpu_count

*Generated at: {plan.get("generated_at", "unknown")}*
"""

        if output_file:
            with open(output_file, "w") as f:
                f.write(report)
            print(f"📄 Planning report saved to {output_file}")

        return report


def load_mix_profile(profile_path: Optional[str]) -> Dict[str, Any]:
    """Load traffic mix profile"""
    if profile_path and Path(profile_path).exists():
        with open(profile_path) as f:
            return yaml.safe_load(f)

    # Default profile
    return {
        "cold_start_multiplier": 1.2,  # 20% headroom for cold starts
        "burst_multiplier": 1.5,  # 50% headroom for traffic bursts
        "cpu_per_gpu": 4,  # CPU cores per GPU
        "memory_gb_per_gpu": 32,  # Memory GB per GPU
        "cold_start_time_s": 45,  # Time for cold start
        "cold_start_frequency": 0.1,  # Fraction of requests that hit cold
        "target_cold_time_s": 10,  # Target cold start time
    }


def main():
    parser = argparse.ArgumentParser(description="Capacity & Budget Planner")
    parser.add_argument(
        "--target-rps", type=float, required=True, help="Target requests per second"
    )
    parser.add_argument(
        "--p95-budget",
        type=float,
        required=True,
        help="P95 latency budget in milliseconds",
    )
    parser.add_argument(
        "--mix", default="profile.yaml", help="Traffic mix profile YAML"
    )
    parser.add_argument(
        "--region", default="us-central1", help="Cloud region for pricing"
    )
    parser.add_argument(
        "--cost-file", default="cost.yaml", help="Cost configuration file"
    )
    parser.add_argument(
        "--runs", nargs="+", help="Historical run directories for calibration"
    )
    parser.add_argument("--output", help="Output markdown report file")
    parser.add_argument(
        "--calibrate-csv", help="Sweep CSV to calibrate baselines (throughput/p95)"
    )
    parser.add_argument("--json", help="Output JSON plan file")

    args = parser.parse_args()

    # Load configuration
    mix_profile = load_mix_profile(args.mix)

    # Create planner and generate plan
    planner = CapacityPlanner(args.cost_file)
    if args.calibrate_csv:
        planner.calibrate_from_sweep_csv(args.calibrate_csv)
    plan = planner.plan_capacity(
        target_rps=args.target_rps,
        p95_budget_ms=args.p95_budget,
        mix_profile=mix_profile,
        region=args.region,
        run_history=args.runs,
    )

    # Output JSON plan
    json_file = args.json or "capacity_plan.json"
    with open(json_file, "w") as f:
        json.dump(plan, f, indent=2)

    print(f"✅ Capacity plan generated: {json_file}")

    # Generate and display report
    report_file = args.output or "capacity_report.md"
    planner.generate_report(plan, report_file)

    # Print summary
    rec = plan["recommendations"][0]  # Best recommendation
    print(f"\n🎯 **Top Recommendation**: {rec['gpu_count']}x {rec['gpu_type']}")
    print(f"💰 **Monthly Cost**: ${rec['monthly_cost']:,}")
    print(f"📊 **Efficiency**: {rec['gpu_utilization']}% GPU utilization")
    print(f"⚡ **Cost per RPS**: ${rec['cost_per_rps']}/RPS/month")


if __name__ == "__main__":
    sys.exit(main())
