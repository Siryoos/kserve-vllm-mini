#!/usr/bin/env python3
"""
Quantization & Decoding Sweeps Engine
Find the free performance wins by sweeping inference configurations
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QuantizationSweepRunner:
    """Systematic sweep of quantization and decoding parameters"""
    
    def __init__(self, config_path: str, output_dir: str):
        self.config = self._load_config(config_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results = []
        
    def _load_config(self, path: str) -> Dict[str, Any]:
        """Load sweep configuration"""
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    
    def _run_benchmark(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run benchmark with specific configuration"""
        
        # Generate unique run ID for this config
        config_hash = hash(json.dumps(config, sort_keys=True))
        run_id = f"quant_sweep_{abs(config_hash):x}_{datetime.now().strftime('%H%M%S')}"
        
        logger.info(f"Running sweep config: {config['name']}")
        
        # Prepare vLLM environment variables
        env = os.environ.copy()
        env.update({
            'VLLM_QUANTIZATION': config.get('quantization', 'none'),
            'VLLM_KV_CACHE_DTYPE': config.get('kv_cache_dtype', 'auto'),
            'VLLM_MAX_MODEL_LEN': str(config.get('max_model_len', 2048)),
            'VLLM_GPU_MEMORY_UTILIZATION': str(config.get('gpu_memory_utilization', 0.9)),
            'VLLM_ENFORCE_EAGER': 'true' if config.get('enforce_eager', False) else 'false',
        })
        
        # Add tensor parallel and pipeline parallel
        if config.get('tensor_parallel_size', 1) > 1:
            env['VLLM_TENSOR_PARALLEL_SIZE'] = str(config['tensor_parallel_size'])
        
        # Prepare benchmark command
        bench_cmd = [
            'kvmini', 'bench',
            '--namespace', self.config['benchmark']['namespace'],
            '--service', f"{self.config['benchmark']['service']}-{config['name']}",
            '--model', self.config['benchmark']['model'],
            '--requests', str(self.config['benchmark']['requests']),
            '--concurrency', str(self.config['benchmark']['concurrency']),
            '--max-tokens', str(config.get('max_tokens', 64)),
            '--run-id', run_id
        ]

        # Build decoding/loadtest args string for advanced sweeps
        lt_args: List[str] = []
        decoding = config.get('decoding', {})
        if decoding:
            if 'temperature' in decoding:
                lt_args.extend(['--temperature', str(decoding['temperature'])])
            if 'top_p' in decoding:
                lt_args.extend(['--top-p', str(decoding['top_p'])])
            if 'top_k' in decoding:
                lt_args.extend(['--top-k', str(decoding['top_k'])])
            if 'num_completions' in decoding:
                lt_args.extend(['--num-completions', str(decoding['num_completions'])])
            if decoding.get('json_mode'):
                lt_args.append('--json-mode')

            # Vendor-specific OpenAI fields (e.g., vLLM beam/speculative)
            extra_openai = decoding.get('extra_openai')
            if extra_openai:
                extra_file = self.output_dir / f"extra_openai_{config['name']}.json"
                with open(extra_file, 'w') as ef:
                    json.dump(extra_openai, ef)
                lt_args.extend(['--extra-openai-json', str(extra_file)])

        if lt_args:
            # Combine into quoted string for kvmini/bench.sh passthrough
            bench_cmd.extend(['--loadtest-args', ' '.join(lt_args)])
        
        try:
            # Deploy with specific config
            self._deploy_with_config(config, env)
            
            # Run benchmark
            result = subprocess.run(bench_cmd, capture_output=True, text=True, 
                                  env=env, timeout=600)
            
            if result.returncode == 0:
                # Load results
                results_file = Path("runs") / run_id / "results.json"
                if results_file.exists():
                    with open(results_file) as f:
                        benchmark_results = json.load(f)
                    
                    # Add configuration metadata
                    benchmark_results.update({
                        'config_name': config['name'],
                        'quantization': config.get('quantization', 'none'),
                        'kv_cache_dtype': config.get('kv_cache_dtype', 'auto'),
                        'max_model_len': config.get('max_model_len', 2048),
                        'gpu_memory_utilization': config.get('gpu_memory_utilization', 0.9),
                        'tensor_parallel_size': config.get('tensor_parallel_size', 1),
                        'run_id': run_id
                    })
                    
                    # Run quality evaluation if enabled
                    if self.config.get('quality_eval', {}).get('enabled', False):
                        benchmark_results = self._add_quality_eval(benchmark_results, config)
                    
                    return benchmark_results
                else:
                    logger.error(f"Results file not found: {results_file}")
                    return self._create_error_result(config, "results_not_found")
            else:
                logger.error(f"Benchmark failed: {result.stderr}")
                return self._create_error_result(config, "benchmark_failed")
                
        except subprocess.TimeoutExpired:
            logger.error(f"Benchmark timed out for config: {config['name']}")
            return self._create_error_result(config, "timeout")
        except Exception as e:
            logger.error(f"Benchmark error for config {config['name']}: {e}")
            return self._create_error_result(config, str(e))
        finally:
            # Cleanup deployment
            self._cleanup_deployment(config)
    
    def _deploy_with_config(self, config: Dict[str, Any], env: Dict[str, str]) -> None:
        """Deploy inference service with specific configuration"""
        
        service_name = f"{self.config['benchmark']['service']}-{config['name']}"
        
        # Create custom InferenceService YAML with vLLM config
        isvc_yaml = f"""
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: {service_name}
  namespace: {self.config['benchmark']['namespace']}
  annotations:
    serving.kserve.io/deploymentMode: Serverless
spec:
  predictor:
    containers:
    - name: kserve-container
      image: vllm/vllm-openai:latest
      env:
      - name: MODEL_NAME
        value: "{self.config['benchmark']['model']}"
      - name: VLLM_QUANTIZATION
        value: "{config.get('quantization', 'none')}"
      - name: VLLM_KV_CACHE_DTYPE
        value: "{config.get('kv_cache_dtype', 'auto')}"
      - name: VLLM_MAX_MODEL_LEN
        value: "{config.get('max_model_len', 2048)}"
      - name: VLLM_GPU_MEMORY_UTILIZATION
        value: "{config.get('gpu_memory_utilization', 0.9)}"
      - name: VLLM_TENSOR_PARALLEL_SIZE
        value: "{config.get('tensor_parallel_size', 1)}"
      resources:
        limits:
          cpu: "4"
          memory: "32Gi"
          nvidia.com/gpu: "{config.get('tensor_parallel_size', 1)}"
        requests:
          cpu: "2"
          memory: "16Gi"
          nvidia.com/gpu: "{config.get('tensor_parallel_size', 1)}"
"""
        
        # Apply the configuration
        yaml_file = f"/tmp/{service_name}.yaml"
        with open(yaml_file, 'w') as f:
            f.write(isvc_yaml)
        
        subprocess.run(['kubectl', 'apply', '-f', yaml_file], check=True)
        
        # Wait for service to be ready
        subprocess.run([
            'kubectl', 'wait', '--for=condition=ready',
            f'inferenceservice/{service_name}',
            f'--namespace={self.config["benchmark"]["namespace"]}',
            '--timeout=300s'
        ], check=True)
    
    def _cleanup_deployment(self, config: Dict[str, Any]) -> None:
        """Clean up deployment"""
        service_name = f"{self.config['benchmark']['service']}-{config['name']}"
        subprocess.run([
            'kubectl', 'delete', 'inferenceservice', service_name,
            f'--namespace={self.config["benchmark"]["namespace"]}',
            '--ignore-not-found'
        ])
    
    def _add_quality_eval(self, results: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Add quality evaluation to results"""
        try:
            # Get service endpoint
            service_name = f"{self.config['benchmark']['service']}-{config['name']}"
            endpoint_result = subprocess.run([
                'kubectl', 'get', 'inferenceservice', service_name,
                f'--namespace={self.config["benchmark"]["namespace"]}',
                '-o', 'jsonpath={.status.url}'
            ], capture_output=True, text=True)
            
            if endpoint_result.returncode == 0 and endpoint_result.stdout:
                endpoint = endpoint_result.stdout.strip()
                
                # Run quality evaluation
                quality_cmd = [
                    'python', 'quality/evaluator.py',
                    '--endpoint', endpoint,
                    '--model', self.config['benchmark']['model'],
                    '--tasks', 'hellaswag', 'boolq', 'math',
                    '--samples', '10'  # Small sample for speed
                ]
                
                quality_result = subprocess.run(quality_cmd, capture_output=True, text=True, timeout=300)
                if quality_result.returncode == 0:
                    # Quality results are written to file, load them
                    quality_file = "quality_results.json"
                    if Path(quality_file).exists():
                        with open(quality_file) as f:
                            quality_data = json.load(f)
                        results.update(quality_data)
                        Path(quality_file).unlink()  # Cleanup
        except Exception as e:
            logger.warning(f"Quality evaluation failed: {e}")
            results['quality_score'] = None
        
        return results
    
    def _create_error_result(self, config: Dict[str, Any], error: str) -> Dict[str, Any]:
        """Create error result placeholder"""
        return {
            'config_name': config['name'],
            'quantization': config.get('quantization', 'none'),
            'error': error,
            'p95_ms': float('inf'),
            'throughput_rps': 0,
            'cost_per_1k_tokens': float('inf'),
            'quality_score': 0,
        }
    
    def run_sweep(self) -> List[Dict[str, Any]]:
        """Run complete quantization and decoding sweep"""
        
        configurations = self.config['sweep_configurations']
        total_configs = len(configurations)
        
        logger.info(f"Running sweep with {total_configs} configurations")
        
        for i, config in enumerate(configurations, 1):
            logger.info(f"[{i}/{total_configs}] Testing: {config['name']}")
            
            result = self._run_benchmark(config)
            self.results.append(result)
            
            # Save intermediate results
            self._save_intermediate_results()
        
        # Generate final analysis
        self._generate_analysis()
        
        return self.results
    
    def _save_intermediate_results(self) -> None:
        """Save intermediate results to CSV"""
        if self.results:
            df = pd.DataFrame(self.results)
            csv_path = self.output_dir / "sweep_results.csv"
            df.to_csv(csv_path, index=False)
            logger.info(f"Intermediate results saved to {csv_path}")
    
    def _generate_analysis(self) -> None:
        """Generate comprehensive analysis with Pareto plots and heatmaps"""
        
        if not self.results:
            logger.error("No results to analyze")
            return
        
        df = pd.DataFrame(self.results)
        
        # Remove error results for analysis
        df_clean = df[df['error'].isna() | (df['error'] == '')]
        
        if df_clean.empty:
            logger.error("No successful results for analysis")
            return
        
        # Generate heatmaps
        self._generate_heatmaps(df_clean)
        
        # Generate Pareto analysis
        self._generate_pareto_analysis(df_clean)
        
        # Generate summary report
        self._generate_summary_report(df_clean)
        
        logger.info(f"Analysis complete. Results in {self.output_dir}")
    
    def _generate_heatmaps(self, df: pd.DataFrame) -> None:
        """Generate performance heatmaps"""
        
        # Prepare data for heatmaps
        metrics = ['p95_ms', 'throughput_rps', 'cost_per_1k_tokens']
        if 'quality_score' in df.columns:
            metrics.append('quality_score')
        
        # Create pivot tables for each metric
        for metric in metrics:
            if metric in df.columns:
                plt.figure(figsize=(12, 8))
                
                # Create pivot with quantization vs kv_cache_dtype
                pivot_data = df.pivot_table(
                    values=metric,
                    index='quantization',
                    columns='kv_cache_dtype',
                    aggfunc='mean',
                    fill_value=None
                )
                
                # Create heatmap
                sns.heatmap(
                    pivot_data,
                    annot=True,
                    fmt='.2f',
                    cmap='viridis' if metric in ['throughput_rps', 'quality_score'] else 'viridis_r',
                    cbar_kws={'label': metric}
                )
                
                plt.title(f'{metric.replace("_", " ").title()} by Configuration')
                plt.tight_layout()
                
                # Save heatmap
                heatmap_path = self.output_dir / f"heatmap_{metric}.png"
                plt.savefig(heatmap_path, dpi=300, bbox_inches='tight')
                plt.close()
                
                logger.info(f"Generated heatmap: {heatmap_path}")
    
    def _generate_pareto_analysis(self, df: pd.DataFrame) -> None:
        """Generate Pareto frontier analysis"""
        
        # Define objectives (lower is better for cost/latency, higher for quality/throughput)
        objectives = []
        if 'p95_ms' in df.columns:
            objectives.append(('p95_ms', 'minimize'))
        if 'cost_per_1k_tokens' in df.columns:
            objectives.append(('cost_per_1k_tokens', 'minimize'))
        if 'quality_score' in df.columns:
            objectives.append(('quality_score', 'maximize'))
        if 'throughput_rps' in df.columns:
            objectives.append(('throughput_rps', 'maximize'))
        
        # Calculate Pareto frontier
        pareto_mask = self._calculate_pareto_frontier(df, objectives)
        df['pareto_optimal'] = pareto_mask
        
        # Create Pareto plots
        if len(objectives) >= 2:
            fig, axes = plt.subplots(2, 2, figsize=(16, 12))
            axes = axes.ravel()
            
            plot_combinations = [
                ('cost_per_1k_tokens', 'p95_ms', 'Cost vs Latency'),
                ('cost_per_1k_tokens', 'quality_score', 'Cost vs Quality'),
                ('p95_ms', 'quality_score', 'Latency vs Quality'),
                ('throughput_rps', 'quality_score', 'Throughput vs Quality')
            ]
            
            for i, (x_metric, y_metric, title) in enumerate(plot_combinations):
                if i < 4 and x_metric in df.columns and y_metric in df.columns:
                    ax = axes[i]
                    
                    # Plot all points
                    scatter = ax.scatter(
                        df[x_metric], 
                        df[y_metric],
                        c=df['pareto_optimal'],
                        cmap='RdYlGn',
                        alpha=0.7,
                        s=100
                    )
                    
                    # Highlight Pareto optimal points
                    pareto_df = df[df['pareto_optimal']]
                    ax.scatter(
                        pareto_df[x_metric],
                        pareto_df[y_metric],
                        c='red',
                        marker='*',
                        s=200,
                        label='Pareto Optimal',
                        alpha=0.8
                    )
                    
                    # Annotate Pareto points
                    for _, row in pareto_df.iterrows():
                        ax.annotate(
                            row['config_name'],
                            (row[x_metric], row[y_metric]),
                            xytext=(5, 5),
                            textcoords='offset points',
                            fontsize=8,
                            alpha=0.8
                        )
                    
                    ax.set_xlabel(x_metric.replace('_', ' ').title())
                    ax.set_ylabel(y_metric.replace('_', ' ').title())
                    ax.set_title(title)
                    ax.grid(True, alpha=0.3)
                    ax.legend()
            
            plt.tight_layout()
            pareto_path = self.output_dir / "pareto_analysis.png"
            plt.savefig(pareto_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            logger.info(f"Generated Pareto analysis: {pareto_path}")
        
        # Save Pareto optimal configurations
        pareto_configs = df[df['pareto_optimal']].sort_values('cost_per_1k_tokens')
        pareto_path = self.output_dir / "pareto_optimal_configs.csv"
        pareto_configs.to_csv(pareto_path, index=False)
        
        logger.info(f"Top Pareto configs saved to: {pareto_path}")
    
    def _calculate_pareto_frontier(self, df: pd.DataFrame, objectives: List[Tuple[str, str]]) -> pd.Series:
        """Calculate Pareto frontier for multi-objective optimization"""
        
        n_points = len(df)
        pareto_mask = pd.Series([True] * n_points, index=df.index)
        
        for i in df.index:
            for j in df.index:
                if i != j:
                    dominates = True
                    strictly_better = False
                    
                    for metric, direction in objectives:
                        if metric in df.columns:
                            val_i = df.loc[i, metric]
                            val_j = df.loc[j, metric]
                            
                            if pd.isna(val_i) or pd.isna(val_j):
                                continue
                            
                            if direction == 'minimize':
                                if val_i > val_j:
                                    dominates = False
                                    break
                                elif val_i < val_j:
                                    strictly_better = True
                            else:  # maximize
                                if val_i < val_j:
                                    dominates = False
                                    break
                                elif val_i > val_j:
                                    strictly_better = True
                    
                    if dominates and strictly_better:
                        pareto_mask[i] = False
                        break
        
        return pareto_mask
    
    def _generate_summary_report(self, df: pd.DataFrame) -> None:
        """Generate summary HTML report"""
        
        # Get top 3 Pareto optimal configs
        pareto_df = df[df['pareto_optimal']].sort_values('cost_per_1k_tokens').head(3)
        
        html_report = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Quantization & Decoding Sweep Results</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .metric {{ display: inline-block; margin: 10px; padding: 10px; background: #f0f0f0; border-radius: 5px; }}
        .pareto {{ background: #e8f5e8; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .optimal {{ background-color: #e8f5e8; }}
    </style>
</head>
<body>
    <h1>Quantization & Decoding Sweep Results</h1>
    <p><strong>Generated:</strong> {datetime.now().isoformat()}</p>
    <p><strong>Total Configurations Tested:</strong> {len(df)}</p>
    <p><strong>Pareto Optimal Configurations:</strong> {len(pareto_df)}</p>
    
    <h2>Top 3 Pareto Optimal Configurations</h2>
    <table>
        <tr>
            <th>Config</th>
            <th>Quantization</th>
            <th>KV Cache</th>
            <th>P95 (ms)</th>
            <th>Throughput (RPS)</th>
            <th>Cost ($/1K tok)</th>
            <th>Quality Score</th>
        </tr>"""
        
        for _, row in pareto_df.iterrows():
            html_report += f"""
        <tr class="optimal">
            <td><strong>{row['config_name']}</strong></td>
            <td>{row.get('quantization', 'N/A')}</td>
            <td>{row.get('kv_cache_dtype', 'N/A')}</td>
            <td>{row.get('p95_ms', 'N/A'):.1f}</td>
            <td>{row.get('throughput_rps', 'N/A'):.1f}</td>
            <td>{row.get('cost_per_1k_tokens', 'N/A'):.4f}</td>
            <td>{row.get('quality_score', 'N/A')}</td>
        </tr>"""
        
        html_report += """
    </table>
    
    <h2>Performance Insights</h2>
    <ul>"""
        
        # Add insights based on data
        if 'quantization' in df.columns:
            quant_performance = df.groupby('quantization')['cost_per_1k_tokens'].mean().sort_values()
            best_quant = quant_performance.index[0] if len(quant_performance) > 0 else 'none'
            html_report += f"<li><strong>Best Quantization for Cost:</strong> {best_quant}</li>"
        
        if 'kv_cache_dtype' in df.columns:
            cache_performance = df.groupby('kv_cache_dtype')['throughput_rps'].mean().sort_values(ascending=False)
            best_cache = cache_performance.index[0] if len(cache_performance) > 0 else 'auto'
            html_report += f"<li><strong>Best KV Cache for Throughput:</strong> {best_cache}</li>"
        
        # Cost savings calculation
        if 'cost_per_1k_tokens' in df.columns:
            baseline_cost = df[df['quantization'] == 'none']['cost_per_1k_tokens'].mean()
            best_cost = df['cost_per_1k_tokens'].min()
            if not pd.isna(baseline_cost) and not pd.isna(best_cost) and baseline_cost > 0:
                savings_pct = ((baseline_cost - best_cost) / baseline_cost) * 100
                html_report += f"<li><strong>Maximum Cost Savings:</strong> {savings_pct:.1f}%</li>"
        
        html_report += """
    </ul>
    
    <h2>Heatmaps & Analysis</h2>
    <p>See generated heatmap files:</p>
    <ul>
        <li>heatmap_p95_ms.png - Latency performance</li>
        <li>heatmap_throughput_rps.png - Throughput performance</li>
        <li>heatmap_cost_per_1k_tokens.png - Cost efficiency</li>
        <li>pareto_analysis.png - Multi-objective optimization</li>
    </ul>
    
    <h2>Raw Data</h2>
    <p>Complete results available in: sweep_results.csv</p>
    <p>Pareto optimal configs: pareto_optimal_configs.csv</p>
    
</body>
</html>"""
        
        report_path = self.output_dir / "sweep_report.html"
        with open(report_path, 'w') as f:
            f.write(html_report)
        
        logger.info(f"Generated HTML report: {report_path}")


def create_default_config() -> Dict[str, Any]:
    """Create default sweep configuration"""
    return {
        'benchmark': {
            'namespace': 'benchmark',
            'service': 'llama2-7b-sweep',
            'model': 'llama2-7b',
            'requests': 100,
            'concurrency': 10,
        },
        'quality_eval': {
            'enabled': True,
        },
        'sweep_configurations': [
            {
                'name': 'baseline',
                'quantization': 'none',
                'kv_cache_dtype': 'auto',
                'max_model_len': 2048,
                'gpu_memory_utilization': 0.9,
                'max_tokens': 64,
                'decoding': { 'temperature': 0.0, 'top_p': 1.0 }
            },
            {
                'name': 'fp8-dynamic',
                'quantization': 'fp8',
                'kv_cache_dtype': 'fp8',
                'max_model_len': 2048,
                'gpu_memory_utilization': 0.9,
                'max_tokens': 64,
                'decoding': { 'temperature': 0.2, 'top_p': 0.9 }
            },
            {
                'name': 'int8-kv',
                'quantization': 'none',
                'kv_cache_dtype': 'int8',
                'max_model_len': 4096,  # Larger context with int8 KV
                'gpu_memory_utilization': 0.9,
                'max_tokens': 64,
                'decoding': { 'temperature': 0.0, 'top_p': 1.0 }
            },
            {
                'name': 'awq-optimized',
                'quantization': 'awq',
                'kv_cache_dtype': 'auto',
                'max_model_len': 2048,
                'gpu_memory_utilization': 0.95,
                'max_tokens': 64,
                'decoding': { 'temperature': 0.7, 'top_p': 0.9 }
            },
            {
                'name': 'fp8-aggressive',
                'quantization': 'fp8',
                'kv_cache_dtype': 'fp8',
                'max_model_len': 4096,
                'gpu_memory_utilization': 0.95,
                'max_tokens': 64,
                'decoding': { 'temperature': 0.0, 'top_p': 1.0, 'extra_openai': { 'use_beam_search': True, 'num_beams': 4 } }
            },
            {
                'name': 'gptq-balanced',
                'quantization': 'gptq',
                'kv_cache_dtype': 'auto',
                'max_model_len': 2048,
                'gpu_memory_utilization': 0.9,
                'max_tokens': 64,
                'decoding': { 'temperature': 0.3, 'top_p': 0.95 }
            }
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Quantization & Decoding Sweep Engine")
    parser.add_argument("--config", default="quantization_sweep.yaml",
                       help="Sweep configuration file")
    parser.add_argument("--output-dir", default="sweeps/quantization",
                       help="Output directory for results")
    parser.add_argument("--create-config", action="store_true",
                       help="Create default configuration file")
    
    args = parser.parse_args()
    
    if args.create_config:
        config = create_default_config()
        with open(args.config, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)
        print(f"✅ Created default config: {args.config}")
        return 0
    
    if not Path(args.config).exists():
        print(f"❌ Config file not found: {args.config}")
        print(f"Run with --create-config to generate default configuration")
        return 1
    
    # Run sweep
    runner = QuantizationSweepRunner(args.config, args.output_dir)
    results = runner.run_sweep()
    
    print(f"\n🎉 Quantization sweep completed!")
    print(f"📊 Results: {args.output_dir}/sweep_report.html")
    print(f"📈 Heatmaps: {args.output_dir}/heatmap_*.png") 
    print(f"🎯 Pareto configs: {args.output_dir}/pareto_optimal_configs.csv")
    
    # Show top recommendation
    if results:
        df = pd.DataFrame(results)
        df_clean = df[df['error'].isna() | (df['error'] == '')]
        if not df_clean.empty and 'cost_per_1k_tokens' in df_clean.columns:
            best_config = df_clean.loc[df_clean['cost_per_1k_tokens'].idxmin()]
            print(f"\n💡 **Top Recommendation**: {best_config['config_name']}")
            print(f"   💰 Cost: ${best_config.get('cost_per_1k_tokens', 0):.4f}/1K tokens")
            print(f"   ⚡ P95: {best_config.get('p95_ms', 0):.1f}ms")
            print(f"   🔧 Config: {best_config.get('quantization', 'none')} + {best_config.get('kv_cache_dtype', 'auto')} KV")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
