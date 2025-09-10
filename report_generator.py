#!/usr/bin/env python3
"""
HTML Report Generator for kserve-vllm-mini

Creates executive-friendly HTML reports from benchmark results.json files.
Includes embedded charts, key metrics, and actionable recommendations.

Usage:
  python report_generator.py --input runs/2025-01-01_12-00-00/results.json --output report.html [--cost-file cost.yaml]
  python report_generator.py --grid-sweep sweep_results.csv --output grid_report.html
  python report_generator.py --mig-matrix runs/<id>/mig_matrix.csv --output mig_report.html
"""

import argparse
import base64
import json
import math
import os
import sys
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
except ImportError:
    print("ERROR: Missing 'matplotlib'. Install with: pip install matplotlib", file=sys.stderr)
    sys.exit(2)

try:
    import pandas as pd
except ImportError:
    print("ERROR: Missing 'pandas'. Install with: pip install pandas", file=sys.stderr)
    sys.exit(2)


def load_results(path: str) -> Dict[str, Any]:
    """Load results.json file."""
    with open(path) as f:
        return json.load(f)


def format_number(val: Any, unit: str = "", precision: int = 2) -> str:
    """Format numbers for display."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "N/A"
    if isinstance(val, (int, float)):
        if unit == "ms" and val < 1:
            return f"{val*1000:.1f}μs"
        elif unit == "tokens/sec" and val > 1000:
            return f"{val/1000:.1f}K {unit}"
        elif unit.startswith("$") and val < 0.01:
            return f"${val*1000:.2f}m"
        else:
            return f"{val:.{precision}f}{unit}"
    return str(val)


def create_latency_chart(results: Dict[str, Any]) -> str:
    """Create latency distribution chart and return base64 encoded image."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Latency metrics
    metrics = ['p50_ms', 'p95_ms', 'p99_ms']
    values = [results.get(m) for m in metrics]
    labels = ['P50', 'P95', 'P99']
    
    # Cold/warm breakdown if available
    cold_values = [results.get(f'cold_{m}') for m in metrics]
    warm_values = [results.get(f'warm_{m}') for m in metrics]
    
    x_pos = range(len(labels))
    
    if any(cold_values) and any(warm_values):
        # Show cold vs warm
        width = 0.35
        ax.bar([x - width/2 for x in x_pos], warm_values, width, label='Warm Path', color='green', alpha=0.7)
        ax.bar([x + width/2 for x in x_pos], cold_values, width, label='Cold Path', color='red', alpha=0.7)
        ax.bar(x_pos, values, width/4, label='Overall', color='blue', alpha=0.9)
    else:
        # Just overall
        ax.bar(x_pos, values, color='steelblue', alpha=0.8)
    
    ax.set_xlabel('Percentile')
    ax.set_ylabel('Latency (ms)')
    ax.set_title('Request Latency Distribution')
    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels)
    
    if any(cold_values) and any(warm_values):
        ax.legend()
    
    # Add value labels on bars
    for i, v in enumerate(values):
        if v is not None:
            ax.text(i, v + max(values) * 0.01, f'{v:.1f}ms', ha='center', va='bottom')
    
    plt.tight_layout()
    
    # Save to base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100)
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    plt.close()
    
    return image_base64


def compute_prewarm_breakeven(results: Dict[str, Any], cost_file: Optional[str] = None) -> Dict[str, Any]:
    """Estimate RPS threshold where prewarm cost equals cold penalty using a simple model.

    Model assumptions:
    - Cold penalty per cold request ≈ (cold_p95 - warm_p95) seconds of latency impact.
    - Cold frequency per second ≈ cold_start_count / window_seconds.
    - Prewarm cost per hour derived from cost.yaml (gpu.default) if available; else unknown.
    - Convert penalty to an 'equivalent cost' using cost_per_request as a proxy.
    """
    cold = results.get('cold_start_count', 0) or 0
    window_s = results.get('window', {}).get('seconds') or (results.get('window', {}).get('end', 0) - results.get('window', {}).get('start', 0))
    warm_p95 = results.get('warm_p95_ms') or 0
    cold_p95 = results.get('cold_p95_ms') or 0
    cost_per_req = results.get('cost_per_request')

    penalty_s = max(0.0, (cold_p95 - warm_p95) / 1000.0) if (cold_p95 and warm_p95) else None
    cold_rate_s = (cold / window_s) if window_s and cold is not None else None

    gpu_hourly = None
    if cost_file:
        try:
            import yaml
            with open(cost_file) as f:
                c = yaml.safe_load(f) or {}
            gpu_hourly = float(c.get('gpu', {}).get('default', 0.0))
        except Exception:
            gpu_hourly = None

    breakeven_rps = None
    notes = []
    if penalty_s and cold_rate_s and cost_per_req and gpu_hourly:
        # cost of cold per second ≈ cold_rate_s * cost_per_req (proxy)
        cost_cold_per_s = cold_rate_s * cost_per_req
        # prewarm cost per second per replica
        cost_prewarm_per_s = gpu_hourly / 3600.0
        if cost_cold_per_s > 0:
            # If higher request rate reduces cold_rate_s (autoscaling), assume proportional to 1/RPS (toy model)
            # breakeven when cost_prewarm_per_s == cost_cold_per_s * (base_rps / rps)
            base_rps = results.get('throughput_rps') or 1.0
            breakeven_rps = (cost_cold_per_s * base_rps) / cost_prewarm_per_s
            notes.append('Cold rate assumed inversely proportional to RPS (toy model).')
    else:
        if gpu_hourly is None:
            notes.append('GPU hourly cost unavailable; provide --cost-file for prewarm estimate.')
        if penalty_s is None:
            notes.append('Insufficient cold/warm P95 data for penalty estimate.')
        if cost_per_req is None:
            notes.append('cost_per_request not present; run cost_estimator.py.')

    return {
        'penalty_seconds': penalty_s,
        'cold_rate_per_s': cold_rate_s,
        'gpu_hourly_cost': gpu_hourly,
        'breakeven_rps_estimate': breakeven_rps,
        'notes': notes,
    }


def classify_headroom(results: Dict[str, Any]) -> Dict[str, Any]:
    """Classify bottleneck headroom with simple heuristics from available metrics."""
    gpu_util = results.get('gpu_util_avg') or 0
    error_rate = results.get('error_rate') or 0
    p95 = results.get('p95_ms') or 0
    warm_p95 = results.get('warm_p95_ms') or 0
    cold_starts = results.get('cold_start_count') or 0

    if gpu_util >= 80:
        cls = 'Compute-bound'
        hint = 'GPU utilization high; consider batching/tuning or more GPUs.'
    elif error_rate > 0.05 or (cold_starts > 0 and (p95 > 2 * (warm_p95 or 1))):
        cls = 'Scheduler-bound'
        hint = 'Cold starts or queuing likely; consider prewarm or autoscaling tweaks.'
    else:
        cls = 'I/O-bound'
        hint = 'Low GPU util with high latency; check CPU/IO or network.'

    return {'classification': cls, 'hint': hint, 'gpu_util_avg': gpu_util, 'error_rate': error_rate}


def create_cost_chart(results: Dict[str, Any]) -> str:
    """Create cost breakdown chart."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))
    
    # Cost per request
    cost_per_req = results.get('cost_per_request')
    cold_cost_per_req = results.get('cold_cost_per_request')
    warm_cost_per_req = results.get('warm_cost_per_request')
    
    if cold_cost_per_req and warm_cost_per_req:
        ax1.bar(['Warm', 'Cold', 'Overall'], 
                [warm_cost_per_req, cold_cost_per_req, cost_per_req],
                color=['green', 'red', 'blue'], alpha=0.7)
        ax1.set_ylabel('Cost per Request ($)')
        ax1.set_title('Cost per Request')
        
        # Add value labels
        for i, v in enumerate([warm_cost_per_req, cold_cost_per_req, cost_per_req]):
            if v:
                ax1.text(i, v + max([warm_cost_per_req, cold_cost_per_req, cost_per_req]) * 0.01, 
                        f'${v:.4f}', ha='center', va='bottom')
    
    # Cost per 1K tokens
    cost_per_1k = results.get('cost_per_1k_tokens')
    cold_cost_per_1k = results.get('cold_cost_per_1k_tokens')
    warm_cost_per_1k = results.get('warm_cost_per_1k_tokens')
    
    if cold_cost_per_1k and warm_cost_per_1k:
        ax2.bar(['Warm', 'Cold', 'Overall'],
                [warm_cost_per_1k, cold_cost_per_1k, cost_per_1k],
                color=['green', 'red', 'blue'], alpha=0.7)
        ax2.set_ylabel('Cost per 1K Tokens ($)')
        ax2.set_title('Cost per 1K Tokens')
        
        for i, v in enumerate([warm_cost_per_1k, cold_cost_per_1k, cost_per_1k]):
            if v:
                ax2.text(i, v + max([warm_cost_per_1k, cold_cost_per_1k, cost_per_1k]) * 0.01,
                        f'${v:.4f}', ha='center', va='bottom')
    
    plt.tight_layout()
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100)
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    plt.close()
    
    return image_base64


def generate_recommendations(results: Dict[str, Any]) -> List[str]:
    """Generate actionable recommendations based on results."""
    recs = []
    
    p95 = results.get('p95_ms', 0)
    error_rate = results.get('error_rate', 0)
    gpu_util = results.get('gpu_util_avg', 0)
    cold_starts = results.get('cold_start_count', 0)
    cold_p95 = results.get('cold_p95_ms')
    warm_p95 = results.get('warm_p95_ms')
    
    # Latency recommendations
    if p95 and p95 > 2000:
        recs.append("🔴 **P95 latency is high (>2s)**. Consider increasing concurrency target or checking for resource bottlenecks.")
    elif p95 and p95 < 500:
        recs.append("✅ **Excellent P95 latency** (<500ms). Current configuration is performing well.")
    
    # Error rate recommendations  
    if error_rate and error_rate > 0.05:
        recs.append("🔴 **High error rate** (>5%). Investigate timeout settings, resource limits, or model loading issues.")
    elif error_rate and error_rate < 0.01:
        recs.append("✅ **Low error rate** (<1%). System reliability is good.")
    
    # GPU utilization recommendations
    if gpu_util is not None:
        if gpu_util < 50:
            recs.append("💡 **GPU underutilized** (<50%). Consider reducing GPU allocation or increasing batch size/concurrency.")
        elif gpu_util > 90:
            recs.append("⚠️ **GPU highly utilized** (>90%). May need additional GPU capacity for traffic spikes.")
        else:
            recs.append("✅ **Good GPU utilization** (50-90%). Well balanced configuration.")
    
    # Cold start recommendations
    if cold_starts > 0 and cold_p95 and warm_p95:
        multiplier = cold_p95 / warm_p95 if warm_p95 > 0 else None
        if multiplier and multiplier > 3:
            recs.append(f"🔴 **Cold starts are expensive** ({multiplier:.1f}x slower). Consider pre-warming pools or reducing scale-to-zero grace period.")
        elif multiplier and multiplier > 1.5:
            recs.append(f"⚠️ **Moderate cold start penalty** ({multiplier:.1f}x slower). Monitor if traffic patterns justify scale-to-zero.")
        
    # Cost recommendations
    cost_per_1k = results.get('cost_per_1k_tokens')
    if cost_per_1k:
        if cost_per_1k > 0.1:
            recs.append(f"💰 **High cost per 1K tokens** (${cost_per_1k:.4f}). Consider optimizing GPU utilization or model quantization.")
        elif cost_per_1k < 0.01:
            recs.append(f"✅ **Efficient cost per 1K tokens** (${cost_per_1k:.4f}). Good cost optimization.")
    
    # Energy efficiency
    energy_per_1k = results.get('energy_wh_per_1k_tokens')
    if energy_per_1k:
        if energy_per_1k > 50:
            recs.append(f"⚡ **High energy consumption** ({energy_per_1k:.1f}Wh/1K tokens). Consider power optimization settings.")
        elif energy_per_1k < 10:
            recs.append(f"✅ **Efficient energy usage** ({energy_per_1k:.1f}Wh/1K tokens). Good power efficiency.")
    
    return recs


def generate_single_run_html(results: Dict[str, Any], output_path: str, cost_file: Optional[str] = None) -> None:
    """Generate HTML report for a single benchmark run."""
    
    # Create charts
    latency_chart = create_latency_chart(results)
    cost_chart = create_cost_chart(results)
    recommendations = generate_recommendations(results)
    prewarm = compute_prewarm_breakeven(results, cost_file)
    headroom = classify_headroom(results)
    
    # Get key metrics
    key_metrics = {
        'P95 Latency': format_number(results.get('p95_ms'), 'ms'),
        'Throughput': format_number(results.get('throughput_rps'), 'RPS'),
        'Tokens/sec': format_number(results.get('tokens_per_sec'), 'tokens/sec'),
        'Error Rate': format_number(results.get('error_rate', 0) * 100, '%'),
        'Cost/Request': format_number(results.get('cost_per_request'), '$'),
        'Cost/1K Tokens': format_number(results.get('cost_per_1k_tokens'), '$'),
        'GPU Utilization': format_number(results.get('gpu_util_avg'), '%'),
        'Cold Starts': results.get('cold_start_count', 0),
    }
    
    # Generate HTML
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>KServe vLLM Benchmark Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .header {{ border-bottom: 3px solid #2196F3; padding-bottom: 20px; margin-bottom: 30px; }}
        .header h1 {{ color: #1976D2; margin: 0; font-size: 2.5em; }}
        .header .subtitle {{ color: #666; font-size: 1.1em; margin-top: 5px; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 30px 0; }}
        .metric-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; }}
        .metric-card .value {{ font-size: 2em; font-weight: bold; margin-bottom: 5px; }}
        .metric-card .label {{ font-size: 0.9em; opacity: 0.9; }}
        .chart-container {{ margin: 30px 0; text-align: center; }}
        .chart-container img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 8px; }}
        .recommendations {{ background: #f8f9fa; padding: 25px; border-radius: 8px; margin: 30px 0; }}
        .recommendations h2 {{ color: #495057; margin-top: 0; }}
        .recommendations ul {{ list-style: none; padding: 0; }}
        .recommendations li {{ margin: 10px 0; padding: 10px; background: white; border-radius: 5px; border-left: 4px solid #28a745; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; color: #666; font-size: 0.9em; text-align: center; }}
        .cold-warm {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
        .cold-warm .cold {{ border-left: 4px solid #dc3545; }}
        .cold-warm .warm {{ border-left: 4px solid #28a745; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 LLM Benchmark Report</h1>
            <div class="subtitle">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | KServe + vLLM Performance Analysis</div>
        </div>
        
        <div class="metrics-grid">
            {chr(10).join(f'<div class="metric-card"><div class="value">{value}</div><div class="label">{label}</div></div>' 
                         for label, value in key_metrics.items())}
        </div>
        
        <div class="chart-container">
            <h2>📊 Latency Distribution</h2>
            <img src="data:image/png;base64,{latency_chart}" alt="Latency Chart">
        </div>
        
        <div class="chart-container">
            <h2>💰 Cost Analysis</h2>
            <img src="data:image/png;base64,{cost_chart}" alt="Cost Chart">
        </div>
        
        <div class="recommendations">
            <h2>🎯 Recommendations</h2>
            <ul>
                {chr(10).join(f'<li>{rec}</li>' for rec in recommendations)}
            </ul>
        </div>

        <div class="recommendations">
            <h2>🔥 Prewarm Break-even</h2>
            <ul>
                <li>Penalty seconds (cold-warm P95): {prewarm.get('penalty_seconds')}</li>
                <li>Cold rate (1/s): {prewarm.get('cold_rate_per_s')}</li>
                <li>GPU hourly cost: {prewarm.get('gpu_hourly_cost')}</li>
                <li>Breakeven RPS (est.): {prewarm.get('breakeven_rps_estimate')}</li>
                {chr(10).join(f'<li><em>Note:</em> {n}</li>' for n in prewarm.get('notes', []))}
            </ul>
        </div>

        <div class="recommendations">
            <h2>📈 Headroom</h2>
            <ul>
                <li>Classification: <strong>{headroom.get('classification')}</strong></li>
                <li>Hint: {headroom.get('hint')}</li>
                <li>GPU Utilization: {headroom.get('gpu_util_avg')}</li>
                <li>Error Rate: {headroom.get('error_rate')}</li>
            </ul>
        </div>
        
        <div class="footer">
            🤖 Generated with <a href="https://claude.ai/code" target="_blank">Claude Code</a> | 
            Report powered by kserve-vllm-mini benchmark suite
        </div>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w') as f:
        f.write(html_content)


def generate_grid_sweep_html(csv_path: str, output_path: str) -> None:
    """Generate HTML report for grid sweep results."""
    
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"ERROR: Failed to read CSV: {e}", file=sys.stderr)
        return
    
    # Create comparison charts
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
    
    # P95 latency heatmap
    pivot_p95 = df.pivot_table(values='p95_ms', index='concurrency', columns='max_tokens', aggfunc='mean')
    im1 = ax1.imshow(pivot_p95.values, cmap='RdYlGn_r', aspect='auto')
    ax1.set_title('P95 Latency (ms)')
    ax1.set_xlabel('Max Tokens')
    ax1.set_ylabel('Concurrency')
    ax1.set_xticks(range(len(pivot_p95.columns)))
    ax1.set_xticklabels(pivot_p95.columns)
    ax1.set_yticks(range(len(pivot_p95.index)))
    ax1.set_yticklabels(pivot_p95.index)
    
    # Add text annotations
    for i in range(len(pivot_p95.index)):
        for j in range(len(pivot_p95.columns)):
            val = pivot_p95.values[i, j]
            if not pd.isna(val):
                ax1.text(j, i, f'{val:.0f}', ha='center', va='center', 
                        color='white' if val > pivot_p95.values.max() * 0.7 else 'black')
    
    # Throughput heatmap  
    pivot_rps = df.pivot_table(values='throughput_rps', index='concurrency', columns='max_tokens', aggfunc='mean')
    im2 = ax2.imshow(pivot_rps.values, cmap='RdYlGn', aspect='auto')
    ax2.set_title('Throughput (RPS)')
    ax2.set_xlabel('Max Tokens')
    ax2.set_ylabel('Concurrency')
    ax2.set_xticks(range(len(pivot_rps.columns)))
    ax2.set_xticklabels(pivot_rps.columns)
    ax2.set_yticks(range(len(pivot_rps.index)))
    ax2.set_yticklabels(pivot_rps.index)
    
    # Cost per 1K tokens heatmap
    pivot_cost = df.pivot_table(values='cost_per_1k_tokens', index='concurrency', columns='max_tokens', aggfunc='mean')
    im3 = ax3.imshow(pivot_cost.values, cmap='RdYlGn_r', aspect='auto')
    ax3.set_title('Cost per 1K Tokens ($)')
    ax3.set_xlabel('Max Tokens')
    ax3.set_ylabel('Concurrency')
    ax3.set_xticks(range(len(pivot_cost.columns)))
    ax3.set_xticklabels(pivot_cost.columns)
    ax3.set_yticks(range(len(pivot_cost.index)))
    ax3.set_yticklabels(pivot_cost.index)
    
    # Pattern comparison
    if 'pattern' in df.columns:
        pattern_p95 = df.groupby('pattern')['p95_ms'].mean()
        ax4.bar(pattern_p95.index, pattern_p95.values, color=['blue', 'orange', 'green', 'red'])
        ax4.set_title('P95 Latency by Traffic Pattern')
        ax4.set_ylabel('P95 Latency (ms)')
        ax4.tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100)
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    plt.close()
    
    # Find best configurations
    best_p95 = df.loc[df['p95_ms'].idxmin()] if 'p95_ms' in df.columns else None
    best_rps = df.loc[df['throughput_rps'].idxmax()] if 'throughput_rps' in df.columns else None
    best_cost = df.loc[df['cost_per_1k_tokens'].idxmin()] if 'cost_per_1k_tokens' in df.columns else None
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Grid Sweep Analysis Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .header {{ border-bottom: 3px solid #2196F3; padding-bottom: 20px; margin-bottom: 30px; }}
        .header h1 {{ color: #1976D2; margin: 0; font-size: 2.5em; }}
        .winners {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 30px 0; }}
        .winner-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; }}
        .winner-card h3 {{ margin: 0 0 15px 0; font-size: 1.2em; }}
        .winner-card .config {{ font-family: monospace; background: rgba(255,255,255,0.1); padding: 10px; border-radius: 4px; margin: 5px 0; }}
        .chart-container {{ margin: 30px 0; text-align: center; }}
        .chart-container img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 8px; }}
        .summary-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .summary-table th, .summary-table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        .summary-table th {{ background-color: #f8f9fa; font-weight: 600; }}
        .summary-table tr:hover {{ background-color: #f5f5f5; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔬 Grid Sweep Analysis</h1>
            <div class="subtitle">Comprehensive parameter optimization results | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
        
        <div class="winners">
            <div class="winner-card">
                <h3>🏆 Best Latency (P95)</h3>
                <div class="config">Concurrency: {best_p95['concurrency'] if best_p95 is not None else 'N/A'}</div>
                <div class="config">Max Tokens: {best_p95['max_tokens'] if best_p95 is not None else 'N/A'}</div>
                <div class="config">Pattern: {best_p95['pattern'] if best_p95 is not None and 'pattern' in best_p95 else 'N/A'}</div>
                <div class="config"><strong>P95: {best_p95['p95_ms']:.1f}ms</strong></div>
            </div>
            
            <div class="winner-card">
                <h3>🚀 Best Throughput</h3>
                <div class="config">Concurrency: {best_rps['concurrency'] if best_rps is not None else 'N/A'}</div>
                <div class="config">Max Tokens: {best_rps['max_tokens'] if best_rps is not None else 'N/A'}</div>
                <div class="config">Pattern: {best_rps['pattern'] if best_rps is not None and 'pattern' in best_rps else 'N/A'}</div>
                <div class="config"><strong>RPS: {best_rps['throughput_rps']:.1f}</strong></div>
            </div>
            
            <div class="winner-card">
                <h3>💰 Best Cost Efficiency</h3>
                <div class="config">Concurrency: {best_cost['concurrency'] if best_cost is not None else 'N/A'}</div>
                <div class="config">Max Tokens: {best_cost['max_tokens'] if best_cost is not None else 'N/A'}</div>
                <div class="config">Pattern: {best_cost['pattern'] if best_cost is not None and 'pattern' in best_cost else 'N/A'}</div>
                <div class="config"><strong>Cost: ${best_cost['cost_per_1k_tokens']:.4f}/1K tokens</strong></div>
            </div>
        </div>
        
        <div class="chart-container">
            <h2>📊 Parameter Space Analysis</h2>
            <img src="data:image/png;base64,{image_base64}" alt="Grid Sweep Results">
        </div>
        
        <div class="footer">
            🤖 Generated with <a href="https://claude.ai/code" target="_blank">Claude Code</a> | 
            Grid sweep powered by kserve-vllm-mini
        </div>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w') as f:
        f.write(html_content)


def generate_mig_matrix_html(csv_path: str, output_path: str) -> None:
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"ERROR: Failed to read CSV: {e}", file=sys.stderr)
        return
    
    # Simple bar charts for P95 and Cost/Energy
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    if 'p95_ms' in df.columns:
        ax1.bar(df['profile'], df['p95_ms'], color='steelblue')
        ax1.set_title('P95 by Profile')
        ax1.set_ylabel('ms')
        ax1.set_xticklabels(df['profile'], rotation=30, ha='right')
    if 'cost_per_1k_tokens' in df.columns:
        ax2.bar(df['profile'], df['cost_per_1k_tokens'], color='seagreen', label='Cost/1K tokens')
        if 'Wh_per_1k_tokens' in df.columns:
            ax2.plot(df['profile'], df['Wh_per_1k_tokens'], 'o-r', label='Wh/1K tokens')
        ax2.legend()
        ax2.set_title('Cost/Energy by Profile')
        ax2.set_xticklabels(df['profile'], rotation=30, ha='right')
    plt.tight_layout()
    buffer = BytesIO(); plt.savefig(buffer, format='png', dpi=100); buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode(); plt.close()

    rows_html = ''.join(
        f"<tr><td>{r['profile']}</td><td>{r.get('p50_ms','')}</td><td>{r.get('p95_ms','')}</td><td>{r.get('throughput_rps','')}</td><td>{r.get('Wh_per_1k_tokens','')}</td><td>{r.get('cost_per_1k_tokens','')}</td><td>{r.get('error_rate','')}</td></tr>"
        for _, r in df.iterrows()
    )

    html = f"""
<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>MIG Matrix</title>
<style>table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:6px 10px}}</style>
</head><body>
<h2>MIG Profile Comparison</h2>
<img src="data:image/png;base64,{image_base64}" alt="MIG charts"/>
<table>
<tr><th>Profile</th><th>P50</th><th>P95</th><th>RPS</th><th>Wh/1K</th><th>$ / 1K</th><th>Error</th></tr>
{rows_html}
</table>
</body></html>
"""
    with open(output_path, 'w') as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(description='Generate HTML reports from benchmark results')
    parser.add_argument('--input', help='Path to results.json file from a single run')
    parser.add_argument('--grid-sweep', help='Path to CSV file from grid sweep')
    parser.add_argument('--mig-matrix', help='Path to CSV file from MIG sweep')
    parser.add_argument('--cost-file', help='Path to cost.yaml for prewarm estimate')
    parser.add_argument('--output', required=True, help='Output HTML file path')
    
    args = parser.parse_args()
    
    if sum(bool(x) for x in [args.input, args.grid_sweep, args.mig_matrix]) != 1:
        print("ERROR: Provide exactly one of --input, --grid-sweep, or --mig-matrix", file=sys.stderr)
        sys.exit(1)
    
    try:
        if args.input:
            results = load_results(args.input)
            generate_single_run_html(results, args.output, args.cost_file)
            print(f"Generated single-run report: {args.output}")
        elif args.grid_sweep:
            generate_grid_sweep_html(args.grid_sweep, args.output)
            print(f"Generated grid-sweep report: {args.output}")
        else:
            generate_mig_matrix_html(args.mig_matrix, args.output)
            print(f"Generated MIG matrix report: {args.output}")
    
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
