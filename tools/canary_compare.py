#!/usr/bin/env python3
"""
Canary comparator between a baseline and candidate run.

Accepts either run directories or bundle tarballs (from tools/bundle_run.sh).
Produces JSON and a small HTML diff view, and flags regressions over thresholds.

Usage:
  ./tools/canary_compare.py --baseline artifacts/<tag>.tar.gz --candidate artifacts/<new>.tar.gz --out runs/<id>/canary.html
"""

import argparse
import io
import json
import os
import tarfile
from typing import Any, Dict, Tuple


KEYS = [
    ("p95_ms", "lower_better", 0.10),
    ("throughput_rps", "higher_better", 0.10),
    ("error_rate", "lower_better", 0.01),
    ("cost_per_1k_tokens", "lower_better", 0.10),
    ("energy_wh_per_1k_tokens", "lower_better", 0.10),
]


def load_results_from_path(path: str) -> Dict[str, Any]:
    if os.path.isdir(path):
        p = os.path.join(path, "results.json")
        with open(p) as f:
            return json.load(f)
    elif path.endswith(".tar.gz") and os.path.exists(path):
        with tarfile.open(path, "r:gz") as tar:
            # find results.json inside bundle
            member = next((m for m in tar.getmembers() if m.name.endswith("/results.json")), None)
            if not member:
                raise FileNotFoundError("results.json not found in bundle")
            f = tar.extractfile(member)
            if not f:
                raise FileNotFoundError("unable to read results.json from bundle")
            return json.load(io.TextIOWrapper(f))
    else:
        raise FileNotFoundError(path)


def compare(b: Dict[str, Any], c: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    deltas: Dict[str, Any] = {}
    regression = False
    for k, direction, thr in KEYS:
        bv = b.get(k)
        cv = c.get(k)
        if bv is None or cv is None:
            deltas[k] = {"baseline": bv, "candidate": cv, "delta": None, "regression": False}
            continue
        if bv == 0:
            # Avoid division by zero; treat as no regression unless candidate is non-zero and direction lower_better
            rel = float('inf') if direction == "lower_better" and cv > 0 else 0
        else:
            rel = (cv - bv) / bv
        is_regress = False
        if direction == "lower_better":
            is_regress = rel > thr
        else:
            # higher_better
            is_regress = rel < -thr
        deltas[k] = {"baseline": bv, "candidate": cv, "delta": rel, "regression": is_regress}
        regression = regression or is_regress
    return deltas, regression


def write_reports(deltas: Dict[str, Any], out_html: str, out_json: str) -> None:
    os.makedirs(os.path.dirname(out_html), exist_ok=True)
    with open(out_json, "w") as f:
        json.dump(deltas, f, indent=2)
    rows = []
    for k, v in deltas.items():
        baseline = v.get("baseline")
        cand = v.get("candidate")
        delta = v.get("delta")
        reg = v.get("regression")
        delta_str = f"{delta:.3f}" if isinstance(delta, (int, float)) else "NA"
        rows.append(f"<tr><td>{k}</td><td>{baseline}</td><td>{cand}</td><td>{delta_str}</td><td>{'REGRESS' if reg else 'OK'}</td></tr>")
    html = f"""
<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>Canary Compare</title>
<style>table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:6px 10px}}</style>
</head><body>
<h2>Canary Comparison</h2>
<table>
<tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Δ rel</th><th>Status</th></tr>
{''.join(rows)}
</table>
</body></html>
"""
    with open(out_html, "w") as f:
        f.write(html)


def main() -> int:
    ap = argparse.ArgumentParser(description="Canary comparator")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--out", required=True, help="Output HTML path for delta view")
    ap.add_argument("--json", default=None, help="Output JSON path (default: alongside HTML)")
    args = ap.parse_args()

    b = load_results_from_path(args.baseline)
    c = load_results_from_path(args.candidate)
    deltas, regression = compare(b, c)
    out_json = args.json or os.path.splitext(args.out)[0] + ".json"
    write_reports(deltas, args.out, out_json)
    print(f"Wrote {args.out} and {out_json}")
    return 2 if regression else 0


if __name__ == "__main__":
    raise SystemExit(main())
