#!/usr/bin/env python3
"""
Configuration validation script to prevent known KServe + vLLM issues.

This script checks for common misconfigurations that can cause crashes,
particularly the multi-step scheduling issue where max_tokens must be specified.
"""

import argparse
import sys
from typing import Any, Dict, List

import yaml


class ConfigValidator:
    """Validates benchmark configurations against known KServe+vLLM issues."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_multistep_scheduling(self, config: Dict[str, Any]) -> None:
        """
        Check for multi-step scheduling configuration issues.

        KServe's vLLM runtime crashes when:
        - Multi-step scheduling is enabled (num_scheduler_steps > 1)
        - max_tokens is not explicitly set

        Reference: https://github.com/kserve/kserve/issues/XXXX
        """
        vllm_features = config.get("vllm_features", {})
        max_tokens = config.get("max_tokens")

        # Check for multi-step scheduling flags
        multistep_indicators = [
            "num_scheduler_steps",
            "enable_chunked_prefill",
            "use_v2_block_manager",
        ]

        has_multistep = any(
            vllm_features.get(key, 1 if key == "num_scheduler_steps" else False)
            for key in multistep_indicators
        )

        if has_multistep and not max_tokens:
            self.errors.append(
                "Multi-step scheduling detected without max_tokens. "
                "This will cause KServe vLLM runtime to crash. "
                "Add 'max_tokens: <value>' to your profile or use --max-tokens flag."
            )

    def validate_quantization_compatibility(self, config: Dict[str, Any]) -> None:
        """Check for quantization method compatibility issues."""
        vllm_features = config.get("vllm_features", {})
        quantization = vllm_features.get("quantization")

        if quantization == "fp8":
            # FP8 requires modern GPU architectures
            self.warnings.append(
                "FP8 quantization requires H100, H800, or newer GPUs with FP8 tensor core support."
            )

        if quantization in ["awq", "gptq"]:
            # These require pre-quantized models
            self.warnings.append(
                f"{quantization.upper()} quantization requires pre-quantized weights. "
                "Suggestion: use a model repo with built-in AWQ/GPTQ weights or provide quantization_param_path. "
                "Docs: docs/models/OPTIMIZATIONS.md"
            )

        # Validate model format compatibility if declared by profile
        model_requirements = config.get("model_requirements", {})
        compatible = model_requirements.get("compatible_formats")
        if quantization and compatible and quantization not in compatible:
            self.errors.append(
                f"Quantization method '{quantization}' is not compatible with model formats {compatible}. "
                "Suggestion: choose one of the compatible formats or switch profile. "
                "Docs: docs/models/OPTIMIZATIONS.md"
            )

    def validate_cpu_deployment(self, config: Dict[str, Any]) -> None:
        """Check for CPU-only deployment issues."""
        vllm_features = config.get("vllm_features", {})

        # CPU deployment is limited in vLLM
        if vllm_features.get("device") == "cpu":
            self.warnings.append(
                "CPU-only deployment has limited vLLM support. "
                "Many features (quantization, speculative decoding) are GPU-only. "
                "See docs/CPU_LIMITATIONS.md for details."
            )

    def validate_resource_requirements(self, config: Dict[str, Any]) -> None:
        """Validate resource configuration makes sense."""
        requests = config.get("requests", 0)
        concurrency = config.get("concurrency", 1)
        max_tokens = config.get("max_tokens", 0)

        if requests > 0 and concurrency > requests:
            self.warnings.append(
                f"Concurrency ({concurrency}) > requests ({requests}). "
                "Some workers will be idle."
            )

        if max_tokens and max_tokens > 2048:
            self.warnings.append(
                f"Large max_tokens ({max_tokens}) may cause memory issues. "
                "Monitor GPU memory utilization during benchmarks."
            )

        # Heuristic GPU memory sufficiency check (optional hints)
        gpu_mem_gb = config.get("_gpu_memory_gb")
        hints = config.get("validation_hints", {})
        model_hint = (
            hints.get("model_size_hint") or config.get("model_size_hint") or ""
        ).lower()
        quant = config.get("vllm_features", {}).get("quantization")

        baseline_mem = None  # fp16 weights, GB
        if model_hint in {"7b", "13b", "34b", "70b"}:
            baseline_mem = {"7b": 14, "13b": 26, "34b": 65, "70b": 140}[model_hint]

        if gpu_mem_gb is not None and baseline_mem is not None:
            if quant in ["awq", "gptq", "int4"]:
                baseline_mem = max(4, baseline_mem // 4)
            est_required = int(baseline_mem * 1.2)  # +20% headroom for KV/activations
            if est_required > gpu_mem_gb:
                self.errors.append(
                    f"Estimated GPU memory insufficient: need ~{est_required} GiB, have {gpu_mem_gb} GiB. "
                    "Suggestion: enable INT4 (AWQ/GPTQ), reduce max_tokens/concurrency, or use a smaller model. "
                    "Docs: docs/models/OPTIMIZATIONS.md"
                )

        if concurrency <= 1:
            self.warnings.append(
                "Low concurrency (<=1) may underutilize GPU. Suggestion: try 4–16 for throughput baselines."
            )

    def validate_profile(self, config: Dict[str, Any]) -> bool:
        """
        Validate a complete profile configuration.

        Returns True if validation passed (no errors), False otherwise.
        """
        self.errors.clear()
        self.warnings.clear()

        self.validate_multistep_scheduling(config)
        self.validate_quantization_compatibility(config)
        self.validate_cpu_deployment(config)
        self.validate_resource_requirements(config)

        return len(self.errors) == 0


def main():
    parser = argparse.ArgumentParser(
        description="Validate benchmark configurations for known issues"
    )
    parser.add_argument("--profile", type=str, help="Profile YAML file to validate")
    parser.add_argument(
        "--max-tokens", type=int, help="Override max_tokens value for validation"
    )
    parser.add_argument(
        "--concurrency", type=int, help="Override concurrency value for validation"
    )
    parser.add_argument(
        "--requests", type=int, help="Override requests value for validation"
    )
    parser.add_argument(
        "--vllm-args", type=str, help="Additional vLLM arguments to validate"
    )
    parser.add_argument(
        "--gpu-memory-gb",
        type=int,
        help="Available GPU memory (GiB) for heuristic checks",
    )

    args = parser.parse_args()

    validator = ConfigValidator()
    config = {}

    # Load profile if specified
    if args.profile:
        try:
            with open(args.profile) as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading profile {args.profile}: {e}", file=sys.stderr)
            return 1

    # Apply command-line overrides
    if args.max_tokens:
        config["max_tokens"] = args.max_tokens
    if args.concurrency:
        config["concurrency"] = args.concurrency
    if args.requests:
        config["requests"] = args.requests

    # Parse vLLM args if provided
    if args.vllm_args:
        vllm_features = config.setdefault("vllm_features", {})
        # Simple parser for common flags
        if "--num-scheduler-steps" in args.vllm_args:
            vllm_features["num_scheduler_steps"] = 2  # Default assumption
        if "--enable-chunked-prefill" in args.vllm_args:
            vllm_features["enable_chunked_prefill"] = True

    # Attach GPU memory hint if provided
    if args.gpu_memory_gb:
        config["_gpu_memory_gb"] = args.gpu_memory_gb

    # Auto-detect GPU memory if not provided (best-effort)
    if "_gpu_memory_gb" not in config and not args.gpu_memory_gb:
        try:
            import subprocess

            res = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                # Use the smallest GPU memory among visible GPUs for conservative check
                mems = [
                    int(x.strip()) for x in res.stdout.strip().splitlines() if x.strip()
                ]
                if mems:
                    config["_gpu_memory_gb"] = min(mems) // 1024
        except Exception:
            pass

    # Validate configuration
    validator.validate_profile(config)

    # Report results (DX-friendly)
    if validator.warnings:
        print("WARNINGS (actionable suggestions):", file=sys.stderr)
        for warning in validator.warnings:
            print(f"  - {warning}", file=sys.stderr)
        print("", file=sys.stderr)

    if validator.errors:
        print("ERRORS:", file=sys.stderr)
        for error in validator.errors:
            print(f"  - {error}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Configuration validation FAILED. See suggestions above.", file=sys.stderr
        )
        print("Further reading:", file=sys.stderr)
        print("  - docs/FEATURES.md", file=sys.stderr)
        print("  - docs/models/OPTIMIZATIONS.md", file=sys.stderr)
        print("  - docs/MIG.md", file=sys.stderr)
        return 1

    print("Configuration validation PASSED.")
    if validator.warnings:
        print("Note: warnings were reported above.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
