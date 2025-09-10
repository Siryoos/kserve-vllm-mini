#!/usr/bin/env python3
"""
SLO Gate: validates a benchmark run against budgets in slo.json.

Usage:
  ./tools/gate.py --results runs/<id>/results.json --energy runs/<id>/energy.json --slo slo.json

Exits non-zero on any budget violation and prints a summary table.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional


def load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description="SLO Gate")
    ap.add_argument("--results", required=True)
    ap.add_argument("--energy", default=None)
    ap.add_argument("--slo", required=True)
    args = ap.parse_args()

    slo = load_json(args.slo)
    res = load_json(args.results)
    eng = load_json(args.energy)

    failures = []
    summary = []

    # p95 latency
    p95_budget = slo.get("p95_ms")
    p95_val = res.get("p95_ms")
    if p95_budget is not None and p95_val is not None:
        ok = p95_val <= p95_budget
        summary.append(("p95_ms", p95_val, p95_budget, ok))
        if not ok:
            failures.append("p95_ms")

    # error rate
    err_budget = slo.get("error_rate")
    err_val = res.get("error_rate")
    if err_budget is not None and err_val is not None:
        ok = err_val <= err_budget
        summary.append(("error_rate", err_val, err_budget, ok))
        if not ok:
            failures.append("error_rate")

    # cost per 1k tokens
    cost_budget = slo.get("$per_1k_tokens")
    cost_val = res.get("cost_per_1k_tokens")
    if cost_budget is not None and cost_val is not None:
        ok = cost_val <= cost_budget
        summary.append(("$per_1k_tokens", cost_val, cost_budget, ok))
        if not ok:
            failures.append("$per_1k_tokens")

    # cold multiplier
    cold_mult_budget = slo.get("cold_multiplier_max")
    cold_p95 = res.get("cold_p95_ms")
    warm_p95 = res.get("warm_p95_ms")
    if cold_mult_budget is not None and cold_p95 and warm_p95 and warm_p95 > 0:
        mult = cold_p95 / warm_p95
        ok = mult <= cold_mult_budget
        summary.append(("cold_multiplier", mult, cold_mult_budget, ok))
        if not ok:
            failures.append("cold_multiplier")

    # energy per 1k tokens
    energy_budget = slo.get("Wh_per_1k_tokens_max")
    energy_val = None
    if eng.get("Wh_per_1k_tokens_active") is not None:
        energy_val = eng.get("Wh_per_1k_tokens_active")
    elif res.get("energy_wh_per_1k_tokens") is not None:
        energy_val = res.get("energy_wh_per_1k_tokens")
    if energy_budget is not None and energy_val is not None:
        ok = energy_val <= energy_budget
        summary.append(("Wh_per_1k_tokens", energy_val, energy_budget, ok))
        if not ok:
            failures.append("Wh_per_1k_tokens")

    # Print summary
    print("SLO Gate Summary:\n")
    print(f"{'Metric':25} {'Actual':>12} {'Budget':>12}  Result")
    print("-" * 60)
    for name, actual, budget, ok in summary:
        print(f"{name:25} {actual:12.4f} {budget:12.4f}  {'PASS' if ok else 'FAIL'}")

    if failures:
        print(f"\nFAIL: {len(failures)} budget violation(s): {', '.join(failures)}", file=sys.stderr)
        return 3
    print("\nPASS: All budgets met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

