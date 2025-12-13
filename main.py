"""
Main Entry Point
Can be used to run the system or evaluation.

Usage:
  python main.py --mode cli           # Run CLI interface
  python main.py --mode web           # Run web interface
  python main.py --mode evaluate      # Run evaluation
"""

import argparse
import asyncio
import sys
from pathlib import Path


def run_cli():
    """Run CLI interface."""
    from src.ui.cli import main as cli_main
    cli_main()


def run_web():
    """Run web interface."""
    import subprocess  # nosec B404 - Safe utility script, no user input
    print("Starting Streamlit web interface...")
    subprocess.run(["streamlit", "run", "src/ui/streamlit_app.py"])  # nosec B603, B607 - Safe CLI utility


async def run_evaluation():
    """Run system evaluation using LLM-as-a-Judge."""
    import yaml
    from dotenv import load_dotenv
    from src.autogen_orchestrator import AutoGenOrchestrator
    from src.evaluation.evaluator import SystemEvaluator

    # Load environment variables
    load_dotenv()

    # Load config
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)

    # Check if evaluation is enabled
    eval_config = config.get("evaluation", {})
    if not eval_config.get("enabled", False):
        print("Evaluation is disabled in config.yaml. Set evaluation.enabled: true to run evaluation.")
        return

    # Initialize AutoGen orchestrator
    print("Initializing AutoGen orchestrator...")
    orchestrator = AutoGenOrchestrator(config)

    # Initialize SystemEvaluator
    print("Initializing SystemEvaluator...")
    evaluator = SystemEvaluator(config, orchestrator=orchestrator)

    # Get test queries path
    test_queries_path = eval_config.get("test_queries_path", "data/test_queries.json")

    print("\n" + "=" * 70)
    print("RUNNING SYSTEM EVALUATION")
    print("=" * 70)
    print(f"\nTest queries: {test_queries_path}")
    print(f"Judge perspectives: {len(evaluator.judge_perspectives)}")
    for judge in evaluator.judge_perspectives:
        print(f"  - {judge.get('name')}: {judge.get('description', 'No description')}")
    print(f"Evaluation criteria: {len(evaluator.judge.criteria)}")
    for criterion in evaluator.judge.criteria:
        print(f"  - {criterion.get('name')} (weight: {criterion.get('weight', 0)})")
    print("\nStarting evaluation...\n")

    # Run evaluation
    report = await evaluator.evaluate_system(test_queries_path)

    # Display results
    print("\n" + "=" * 70)
    print("EVALUATION RESULTS")
    print("=" * 70)

    summary = report.get("summary", {})
    print(f"\nTotal Queries: {summary.get('total_queries', 0)}")
    print(f"Successful: {summary.get('successful', 0)}")
    print(f"Failed: {summary.get('failed', 0)}")
    print(f"Success Rate: {summary.get('success_rate', 0.0):.2%}")
    print(f"Number of Judges: {summary.get('num_judges', 0)}")

    scores = report.get("scores", {})
    print(f"\nOverall Average Score: {scores.get('overall_average', 0.0):.3f}")

    print("\nAverage Scores by Judge Perspective:")
    for judge_name, score in scores.get("by_judge", {}).items():
        print(f"  {judge_name}: {score:.3f}")

    print("\nAverage Scores by Criterion:")
    for criterion, score in scores.get("by_criterion", {}).items():
        print(f"  {criterion}: {score:.3f}")

    # Show best and worst results
    if report.get("best_result"):
        best = report["best_result"]
        print(f"\nBest Result:")
        print(f"  Query: {best.get('query', '')[:80]}...")
        print(f"  Score: {best.get('score', 0.0):.3f}")

    if report.get("worst_result"):
        worst = report["worst_result"]
        print(f"\nWorst Result:")
        print(f"  Query: {worst.get('query', '')[:80]}...")
        print(f"  Score: {worst.get('score', 0.0):.3f}")

    print("\n" + "=" * 70)
    print("Detailed results saved to outputs/")
    print("=" * 70)


def run_autogen():
    """Run AutoGen example."""
    import subprocess  # nosec B404 - Safe utility script, no user input
    print("Running AutoGen example...")
    subprocess.run([sys.executable, "example_autogen.py"])  # nosec B603 - Safe CLI utility


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Research Assistant"
    )
    parser.add_argument(
        "--mode",
        choices=["cli", "web", "evaluate", "autogen"],
        default="autogen",
        help="Mode to run: cli, web, evaluate, or autogen (default)"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file"
    )

    args = parser.parse_args()

    if args.mode == "cli":
        run_cli()
    elif args.mode == "web":
        run_web()
    elif args.mode == "evaluate":
        asyncio.run(run_evaluation())
    elif args.mode == "autogen":
        run_autogen()


if __name__ == "__main__":
    main()
