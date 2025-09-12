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
    """Read JSON from `path` if it exists; otherwise return empty dict."""
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def main() -> int:
    """Validate results against SLO budgets and print a pass/fail summary."""
    ap = argparse.ArgumentParser(description="SLO Gate")
    ap.add_argument("--results", default=None)
    ap.add_argument("--energy", default=None)
    ap.add_argument("--slo", required=True)
    ap.add_argument(
        "--fairness",
        default=None,
        help="Path to fairness_summary.json for multi-tenant gate",
    )
    args = ap.parse_args()

    slo = load_json(args.slo)
    res = load_json(args.results) if args.results else {}
    eng = load_json(args.energy)

    failures = []
    summary = []

    # p95 latency (single-tenant/overall)
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

    # Fairness gate (optional)
    if args.fairness:
        fair = load_json(args.fairness)
        fair_slo = slo.get("fairness", {})
        tp95 = fair_slo.get("tenant_p95_ms_max")
        share_diff_max = fair_slo.get("throughput_share_diff_max")
        triggers_max = fair_slo.get("guard_triggers_max")
        # Extract fairness metrics
        A = (fair.get("summary") or {}).get("A") or {}
        B = (fair.get("summary") or {}).get("B") or {}
        shares = (fair.get("summary") or {}).get("throughput_share") or {}
        trig = fair.get("guard_triggers")
        if tp95 is not None:
            a_ok = (A.get("p95_ms") or float("inf")) <= tp95
            b_ok = (B.get("p95_ms") or float("inf")) <= tp95
            summary.append(("fairness_tenantA_p95_ms", A.get("p95_ms"), tp95, a_ok))
            summary.append(("fairness_tenantB_p95_ms", B.get("p95_ms"), tp95, b_ok))
            if not a_ok:
                failures.append("fairness_tenantA_p95_ms")
            if not b_ok:
                failures.append("fairness_tenantB_p95_ms")
        if share_diff_max is not None and shares:
            diff = abs((shares.get("A") or 0) - (shares.get("B") or 0))
            ok = diff <= share_diff_max
            summary.append(("fairness_share_diff", diff, share_diff_max, ok))
            if not ok:
                failures.append("fairness_share_diff")
        if triggers_max is not None and trig is not None:
            ok = trig <= triggers_max
            summary.append(("fairness_guard_triggers", trig, triggers_max, ok))
            if not ok:
                failures.append("fairness_guard_triggers")

    # Print summary
    print("SLO Gate Summary:\n")
    if summary:
        print(f"{'Metric':25} {'Actual':>12} {'Budget':>12}  Result")
        print("-" * 60)
        for name, actual, budget, ok in summary:
            try:
                a = float(actual)
            except Exception:
                a = 0.0 if actual is None else actual
            try:
                b = float(budget)
            except Exception:
                b = 0.0 if budget is None else budget
            print(f"{name:25} {a:12.4f} {b:12.4f}  {'PASS' if ok else 'FAIL'}")

    if failures:
        print(
            f"\nFAIL: {len(failures)} budget violation(s): {', '.join(failures)}",
            file=sys.stderr,
        )
        return 3
    print("\nPASS: All budgets met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
