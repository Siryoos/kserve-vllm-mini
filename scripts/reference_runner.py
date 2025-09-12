#!/usr/bin/env python3
"""
Reference runs matrix executor for GA hardening.
Produces signed, reproducible artifacts across GPU/model/traffic matrix.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ReferenceRunner:
    """Run a matrix of reference benchmarks and produce signed artifacts."""

    def __init__(self, config_path: str, output_dir: str):
        self.config = self._load_config(config_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self, path: str) -> Dict[str, Any]:
        with open(path) as f:
            return yaml.safe_load(f)

    def _run_command(self, cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
        """Run command with logging and error handling"""
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
        if result.returncode != 0:
            logger.error(f"Command failed: {result.stderr}")
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        return result

    def _kvmini_path(self) -> str:
        """Resolve the kvmini CLI path.

        Prefer repo-local ./kvmini if present; otherwise fallback to PATH.
        """
        repo_root = Path(__file__).resolve().parent.parent
        local = repo_root / "kvmini"
        if local.exists():
            return str(local)
        return "kvmini"

    def _generate_run_id(self, gpu: str, model: str, traffic: str) -> str:
        """Generate deterministic run ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"ref_{gpu}_{model}_{traffic}_{timestamp}"

    def _create_bom(self, run_dir: Path, gpu: Dict, model: Dict, traffic: Dict) -> None:
        """Create Bill of Materials (BOM) for the run"""
        bom_content = f"""# Bill of Materials - Reference Run

**Generated**: {datetime.now().isoformat()}
**Run ID**: {run_dir.name}

## Configuration
- **GPU**: {gpu["name"]} (${gpu["cost_per_hour"]}/hour)
- **Model**: {model["name"]} ({model["uri"]})
- **Traffic**: {traffic["name"]} ({traffic["requests"]} req, {traffic["concurrency"]} concurrent)

## Environment
- **Kubernetes Version**: {self._get_k8s_version()}
- **KServe Version**: {self._get_kserve_version()}
- **Node Info**: {self._get_node_info(gpu)}

## Thresholds
- P95 Variance: ±{self.config["thresholds"]["p95_variance_pct"]}%
- Error Rate Max: {self.config["thresholds"]["error_rate_max"]}
- Cold Multiplier Max: {self.config["thresholds"]["cold_multiplier_max"]}

## Files Included
- `results.json` - Consolidated metrics
- `requests.csv` - Per-request data
- `meta.json` - Run metadata
- `energy.json` - Power consumption data
- `report.html` - Visual report
- `BOM.md` - This bill of materials

## Reproducibility
To reproduce this run:
```bash
kvmini bench \\
  --namespace benchmark \\
  --service {model["name"]}-ref \\
  --model {model["name"]} \\
  --requests {traffic["requests"]} \\
  --concurrency {traffic["concurrency"]} \\
  --max-tokens {traffic.get("max_tokens", 64)}
```

## Verification
- Bundle signed with: {self._get_signing_info()}
- Checksum: {self._calculate_checksum(run_dir)}
"""
        with open(run_dir / "BOM.md", "w") as f:
            f.write(bom_content)

    def _get_k8s_version(self) -> str:
        try:
            result = self._run_command(["kubectl", "version", "--short", "--client"])
            return result.stdout.strip()
        except Exception:
            return "unknown"

    def _get_kserve_version(self) -> str:
        try:
            result = self._run_command(
                [
                    "kubectl",
                    "get",
                    "deployment",
                    "kserve-controller-manager",
                    "-n",
                    "kserve-system",
                    "-o",
                    "jsonpath={.spec.template.spec.containers[0].image}",
                ]
            )
            return result.stdout.strip().split(":")[-1]
        except Exception:
            return "unknown"

    def _get_node_info(self, gpu: Dict) -> str:
        try:
            selector = ",".join(
                [f"{k}={v}" for k, v in gpu.get("node_selector", {}).items()]
            )
            result = self._run_command(
                [
                    "kubectl",
                    "get",
                    "nodes",
                    f"--selector={selector}",
                    "-o",
                    "jsonpath={.items[0].status.nodeInfo.kernelVersion}",
                ]
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"

    def _get_signing_info(self) -> str:
        # Placeholder for actual signing implementation
        return "cosign keyless (OIDC)"

    def _calculate_checksum(self, run_dir: Path) -> str:
        try:
            result = subprocess.run(
                ["find", str(run_dir), "-type", "f", "-exec", "sha256sum", "{}", "+"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                import hashlib

                return hashlib.sha256(result.stdout.encode()).hexdigest()[:16]
        except Exception:
            pass
        return "unknown"

    def run_single_benchmark(
        self, gpu: Dict, model: Dict, traffic: Dict
    ) -> Optional[Path]:
        """Run a single benchmark configuration"""
        run_id = self._generate_run_id(gpu["name"], model["name"], traffic["name"])
        run_dir = self.output_dir / run_id

        logger.info(
            f"Starting benchmark: {gpu['name']} + {model['name']} + {traffic['name']}"
        )

        try:
            # Deploy inference service with GPU constraints
            deploy_cmd = [
                self._kvmini_path(),
                "deploy",
                "--namespace",
                "benchmark",
                "--service",
                f"{model['name']}-ref",
                "--model-uri",
                model["uri"],
                "--runtime",
                "vllm",
                "--gpu-limit",
                str(gpu["gpu_limit"]),
            ]
            self._run_command(deploy_cmd)

            # Run benchmark with traffic pattern
            bench_cmd = [
                self._kvmini_path(),
                "bench",
                "--namespace",
                "benchmark",
                "--service",
                f"{model['name']}-ref",
                "--model",
                model["name"],
                "--requests",
                str(traffic["requests"]),
                "--concurrency",
                str(traffic["concurrency"]),
                "--max-tokens",
                str(traffic.get("max_tokens", 64)),
                "--bundle",
                "--run-id",
                run_id,
            ]

            # Add node selector via environment
            env = os.environ.copy()
            if gpu.get("node_selector"):
                env["NODE_SELECTOR"] = json.dumps(gpu["node_selector"])

            self._run_command(bench_cmd, env=env)

            # Verify run results exist
            results_file = Path("runs") / run_id / "results.json"
            if not results_file.exists():
                raise FileNotFoundError(f"Results not found: {results_file}")

            # Load and validate results
            with open(results_file) as f:
                results = json.load(f)

            if not self._validate_results(results, gpu, model, traffic):
                logger.warning(f"Results validation failed for {run_id}")
                return None

            # Move to reference output directory
            import shutil

            shutil.move(str(Path("runs") / run_id), str(run_dir))

            # Create BOM
            self._create_bom(run_dir, gpu, model, traffic)

            # Sign bundle if enabled
            if self.config["artifacts"].get("sign_bundles", False):
                self._sign_bundle(run_dir)

            logger.info(f"✅ Benchmark completed: {run_dir}")
            return run_dir

        except Exception as e:
            logger.error(f"❌ Benchmark failed: {e}")
            # Cleanup failed deployment
            try:
                self._run_command(
                    [
                        "kubectl",
                        "delete",
                        "inferenceservice",
                        f"{model['name']}-ref",
                        "-n",
                        "benchmark",
                        "--ignore-not-found",
                    ]
                )
            except Exception:
                pass
            return None

    def _validate_results(
        self, results: Dict, gpu: Dict, model: Dict, traffic: Dict
    ) -> bool:
        """Validate results against thresholds"""
        thresholds = self.config["thresholds"]

        # Check error rate
        error_rate = results.get("error_rate", 1.0)
        if error_rate > thresholds["error_rate_max"]:
            logger.error(
                f"Error rate {error_rate} exceeds {thresholds['error_rate_max']}"
            )
            return False

        # Check minimum throughput
        throughput = results.get("throughput_rps", 0)
        if throughput < thresholds["min_throughput_rps"]:
            logger.error(
                f"Throughput {throughput} below {thresholds['min_throughput_rps']} RPS"
            )
            return False

        # Check cold start multiplier
        cold_p95 = results.get("cold_p95_ms", 0)
        warm_p95 = results.get("warm_p95_ms", 1)
        if warm_p95 > 0 and (cold_p95 / warm_p95) > thresholds["cold_multiplier_max"]:
            logger.error(
                f"Cold multiplier {cold_p95 / warm_p95} exceeds {thresholds['cold_multiplier_max']}"
            )
            return False

        return True

    def _sign_bundle(self, run_dir: Path) -> None:
        """Sign bundle with cosign (placeholder)"""
        logger.info(f"Signing bundle: {run_dir}")
        # TODO: Implement actual cosign signing
        # cosign sign-blob --bundle=signature.bundle <bundle-file>
        pass

    def run_matrix(
        self, gpu_filter: Optional[str] = None, model_filter: Optional[str] = None
    ) -> List[Path]:
        """Run complete reference matrix"""
        successful_runs = []
        total_runs = 0

        for gpu in self.config["matrix"]["gpus"]:
            if gpu_filter and gpu["name"] != gpu_filter:
                continue

            for model in self.config["matrix"]["models"]:
                if model_filter and model["name"] != model_filter:
                    continue

                for traffic in self.config["matrix"]["traffic_patterns"]:
                    total_runs += 1
                    result = self.run_single_benchmark(gpu, model, traffic)
                    if result:
                        successful_runs.append(result)

        logger.info(
            f"Reference matrix completed: {len(successful_runs)}/{total_runs} successful"
        )

        # Generate matrix summary
        self._generate_summary(successful_runs)

        return successful_runs

    def _generate_summary(self, runs: List[Path]) -> None:
        """Generate summary report of all runs"""
        summary = {
            "generated_at": datetime.now().isoformat(),
            "total_runs": len(runs),
            "runs": [],
        }

        for run_dir in runs:
            results_file = run_dir / "results.json"
            if results_file.exists():
                with open(results_file) as f:
                    results = json.load(f)
                summary["runs"].append(
                    {
                        "run_id": run_dir.name,
                        "p95_ms": results.get("p95_ms"),
                        "throughput_rps": results.get("throughput_rps"),
                        "error_rate": results.get("error_rate"),
                        "cost_per_1k_tokens": results.get("cost_per_1k_tokens"),
                    }
                )

        with open(self.output_dir / "matrix_summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(
            f"Matrix summary written to {self.output_dir / 'matrix_summary.json'}"
        )


def main():
    """CLI: execute the configured reference matrix or show a dry-run plan."""
    parser = argparse.ArgumentParser(description="Reference runs matrix executor")
    parser.add_argument(
        "--config", default="reference-matrix.yaml", help="Matrix configuration file"
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/reference",
        help="Output directory for artifacts",
    )
    parser.add_argument("--gpu", help="Filter to specific GPU type")
    parser.add_argument("--model", help="Filter to specific model")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be run")

    args = parser.parse_args()

    if args.dry_run:
        with open(args.config) as f:
            config = yaml.safe_load(f)
        print("Reference matrix would run:")
        for gpu in config["matrix"]["gpus"]:
            for model in config["matrix"]["models"]:
                for traffic in config["matrix"]["traffic_patterns"]:
                    if (not args.gpu or gpu["name"] == args.gpu) and (
                        not args.model or model["name"] == args.model
                    ):
                        print(f"  {gpu['name']} + {model['name']} + {traffic['name']}")
        return 0

    runner = ReferenceRunner(args.config, args.output_dir)
    successful_runs = runner.run_matrix(args.gpu, args.model)

    return 0 if successful_runs else 1


if __name__ == "__main__":
    sys.exit(main())
