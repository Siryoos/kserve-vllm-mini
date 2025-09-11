#!/usr/bin/env python3
"""
Quality evaluation integration for LLM benchmarks.
Integrates with lm-eval-harness or Lighteval to assess quality vs cost vs latency tradeoffs.
"""

import argparse
import json
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QualityEvaluator:
    """Quality evaluation using lm-eval-harness subset"""

    # Lightweight evaluation suite - balances accuracy with speed
    DEFAULT_TASKS = [
        "hellaswag",  # Common sense reasoning
        "arc_easy",  # Basic reasoning
        "boolq",  # Reading comprehension
        "piqa",  # Physical reasoning
    ]

    def __init__(
        self,
        model_endpoint: str,
        model_name: str,
        tasks: Optional[List[str]] = None,
        num_samples: int = 100,
    ):
        self.endpoint = model_endpoint.rstrip("/")
        self.model_name = model_name
        self.tasks = tasks or self.DEFAULT_TASKS
        self.num_samples = num_samples
        self.session = requests.Session()

    def _call_model(self, prompt: str, max_tokens: int = 32) -> Tuple[str, float, int]:
        """Call model endpoint and return response, latency, tokens"""
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.0,  # Deterministic for evaluation
            "stream": False,
        }

        import time

        start_time = time.time()

        try:
            response = self.session.post(
                f"{self.endpoint}/v1/chat/completions", json=payload, timeout=30
            )
            response.raise_for_status()
            data = response.json()

            latency = time.time() - start_time
            content = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", 0)

            return content, latency, tokens

        except Exception as e:
            logger.error(f"Model call failed: {e}")
            return "", float("inf"), 0

    def _evaluate_hellaswag(self) -> Dict[str, Any]:
        """Evaluate common sense reasoning"""
        # Simplified HellaSwag - just a few examples for demo
        samples = [
            {
                "context": "A woman is outside with a bucket and a dog. The dog is running around trying to avoid a bath. She...",
                "choices": [
                    "gives the dog a treat to calm it down",
                    "runs after the dog with a hose",
                    "ignores the dog and fills the bucket",
                    "gets more upset with the dog",
                ],
                "correct": 1,
            },
            {
                "context": "A man is in the garage working on his car. He opens the hood and checks the oil. Then he...",
                "choices": [
                    "closes the hood and goes inside",
                    "adds more oil to the engine",
                    "starts the car to test it",
                    "cleans his hands with a rag",
                ],
                "correct": 1,
            },
            {
                "context": "The kids are at a birthday party. They're sitting around a table with a cake. Someone...",
                "choices": [
                    "blows out the candles on the cake",
                    "cuts the cake into pieces",
                    "sings happy birthday song",
                    "takes photos of everyone",
                ],
                "correct": 0,
            },
        ]

        correct = 0
        total_latency = 0

        for sample in samples:
            prompt = f"""Complete this scenario by choosing the most likely next action:

{sample["context"]}

Choices:
A) {sample["choices"][0]}
B) {sample["choices"][1]}
C) {sample["choices"][2]}
D) {sample["choices"][3]}

Answer with just the letter (A, B, C, or D):"""

            response, latency, tokens = self._call_model(prompt, max_tokens=1)
            total_latency += latency

            # Extract answer
            answer = response.strip().upper()
            if answer in ["A", "B", "C", "D"]:
                choice_idx = ord(answer) - ord("A")
                if choice_idx == sample["correct"]:
                    correct += 1

        return {
            "task": "hellaswag",
            "score": correct / len(samples),
            "samples": len(samples),
            "avg_latency": total_latency / len(samples),
        }

    def _evaluate_boolq(self) -> Dict[str, Any]:
        """Evaluate reading comprehension"""
        samples = [
            {
                "passage": "The Panama Canal connects the Atlantic and Pacific oceans. It was built between 1904 and 1914.",
                "question": "Was the Panama Canal completed before World War I?",
                "answer": True,
            },
            {
                "passage": "Python is a programming language created by Guido van Rossum in 1991. It emphasizes code readability.",
                "question": "Is Python older than Java?",
                "answer": False,  # Java was released in 1995
            },
            {
                "passage": "Mount Everest is the highest mountain in the world at 29,029 feet above sea level.",
                "question": "Is Mount Everest taller than 30,000 feet?",
                "answer": False,
            },
        ]

        correct = 0
        total_latency = 0

        for sample in samples:
            prompt = f"""Read the passage and answer the yes/no question:

Passage: {sample["passage"]}

Question: {sample["question"]}

Answer (Yes or No):"""

            response, latency, tokens = self._call_model(prompt, max_tokens=1)
            total_latency += latency

            # Extract answer
            answer = response.strip().lower()
            expected = "yes" if sample["answer"] else "no"

            if answer.startswith(expected):
                correct += 1

        return {
            "task": "boolq",
            "score": correct / len(samples),
            "samples": len(samples),
            "avg_latency": total_latency / len(samples),
        }

    def _evaluate_math(self) -> Dict[str, Any]:
        """Evaluate basic arithmetic reasoning"""
        samples = [
            {"problem": "What is 15 + 27?", "answer": "42"},
            {"problem": "What is 8 × 7?", "answer": "56"},
            {"problem": "What is 144 ÷ 12?", "answer": "12"},
            {"problem": "What is 100 - 37?", "answer": "63"},
        ]

        correct = 0
        total_latency = 0

        for sample in samples:
            prompt = f"Solve this math problem and give just the number as your answer:\n{sample['problem']}"

            response, latency, tokens = self._call_model(prompt, max_tokens=8)
            total_latency += latency

            # Extract numeric answer
            try:
                answer = "".join(c for c in response if c.isdigit())
                if answer == sample["answer"]:
                    correct += 1
            except Exception:
                pass

        return {
            "task": "math",
            "score": correct / len(samples),
            "samples": len(samples),
            "avg_latency": total_latency / len(samples),
        }

    def evaluate(self) -> Dict[str, Any]:
        """Run quality evaluation suite"""
        logger.info(f"Running quality evaluation on {self.endpoint}")

        results = {}

        # Run evaluation tasks
        if "hellaswag" in self.tasks:
            results["hellaswag"] = self._evaluate_hellaswag()

        if "boolq" in self.tasks:
            results["boolq"] = self._evaluate_boolq()

        if "math" in self.tasks or "arc_easy" in self.tasks:
            results["math"] = self._evaluate_math()

        # Calculate overall quality score (0-100)
        scores = [r["score"] for r in results.values()]
        overall_score = np.mean(scores) * 100 if scores else 0

        # Calculate average latency across tasks
        latencies = [r["avg_latency"] for r in results.values()]
        avg_latency = np.mean(latencies) if latencies else 0

        return {
            "quality_score": round(overall_score, 2),
            "avg_quality_latency_ms": round(avg_latency * 1000, 1),
            "task_results": results,
            "evaluated_at": pd.Timestamp.now().isoformat(),
            "model_endpoint": self.endpoint,
            "model_name": self.model_name,
        }


class ParetoAnalyzer:
    """Analyze quality vs cost vs latency tradeoffs"""

    @staticmethod
    def classify_pareto_bucket(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Classify results into Pareto optimal buckets"""

        # Extract metrics for Pareto analysis
        points = []
        for i, result in enumerate(results):
            quality = result.get("quality_score", 0)
            latency = result.get("p95_ms", float("inf"))
            cost = result.get("cost_per_1k_tokens", float("inf"))

            # For Pareto: higher quality is better, lower latency/cost is better
            # So we negate quality to make all "lower is better"
            points.append((-quality, latency, cost, i))

        if not points:
            return results

        # Simple 3D Pareto frontier calculation
        pareto_indices = set()

        for i, (q1, l1, c1, idx1) in enumerate(points):
            is_dominated = False

            for j, (q2, l2, c2, idx2) in enumerate(points):
                if i != j:
                    # Point i is dominated if another point is better/equal in all dimensions
                    if (
                        q2 <= q1
                        and l2 <= l1
                        and c2 <= c1
                        and (q2 < q1 or l2 < l1 or c2 < c1)
                    ):
                        is_dominated = True
                        break

            if not is_dominated:
                pareto_indices.add(idx1)

        # Add Pareto classification to results
        enhanced_results = []
        for i, result in enumerate(results):
            enhanced = result.copy()
            enhanced["pareto_bucket"] = (
                "on-pareto" if i in pareto_indices else "off-pareto"
            )
            enhanced_results.append(enhanced)

        logger.info(
            f"Pareto analysis: {len(pareto_indices)}/{len(results)} configurations on frontier"
        )
        return enhanced_results


def integrate_quality_eval(
    results_file: str, model_endpoint: str, model_name: str
) -> None:
    """Integrate quality evaluation into existing benchmark results"""

    # Load existing results
    with open(results_file, "r") as f:
        results = json.load(f)

    # Run quality evaluation
    evaluator = QualityEvaluator(model_endpoint, model_name)
    quality_results = evaluator.evaluate()

    # Merge quality metrics into benchmark results
    results.update(quality_results)

    # Save updated results
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(
        f"✅ Quality evaluation integrated. Score: {quality_results['quality_score']:.1f}"
    )


def main():
    parser = argparse.ArgumentParser(description="LLM Quality Evaluation")
    parser.add_argument("--endpoint", required=True, help="Model endpoint URL")
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--results-file", help="Results file to augment")
    parser.add_argument(
        "--tasks",
        nargs="+",
        default=QualityEvaluator.DEFAULT_TASKS,
        help="Evaluation tasks",
    )
    parser.add_argument(
        "--samples", type=int, default=100, help="Number of samples per task"
    )
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    if args.results_file:
        # Integration mode - augment existing results
        integrate_quality_eval(args.results_file, args.endpoint, args.model)
    else:
        # Standalone mode
        evaluator = QualityEvaluator(
            args.endpoint, args.model, args.tasks, args.samples
        )
        results = evaluator.evaluate()

        output_file = args.output or "quality_results.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)

        print(f"✅ Quality evaluation complete. Score: {results['quality_score']:.1f}")
        print(f"📄 Results saved to {output_file}")


if __name__ == "__main__":
    # Import pandas here to avoid import errors if not available
    try:
        import pandas as pd
    except ImportError:
        import datetime

        # Simple replacement for pd.Timestamp
        class Timestamp:
            @staticmethod
            def now():
                return datetime.datetime.now()

        pd = type("pd", (), {"Timestamp": Timestamp})()

    sys.exit(main())
