"""
Evaluation Report Generator
Generates comprehensive evaluation reports for inclusion in technical write-ups.
"""

import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


class EvaluationReportGenerator:
    """
    Generates formatted evaluation reports from evaluation results.
    """

    def __init__(self, report_data: Dict[str, Any]):
        """
        Initialize report generator.

        Args:
            report_data: Evaluation report data from SystemEvaluator
        """
        self.report_data = report_data

    def generate_markdown_report(self) -> str:
        """
        Generate a markdown-formatted evaluation report.

        Returns:
            Markdown string with comprehensive evaluation report
        """
        lines = []

        # Header
        lines.append("# Multi-Agent System Evaluation Report")
        lines.append("")
        lines.append(f"**Evaluation Date:** {self.report_data.get('timestamp', 'N/A')}")
        lines.append("")

        # Summary
        summary = self.report_data.get("summary", {})
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(f"- **Total Queries Evaluated:** {summary.get('total_queries', 0)}")
        lines.append(f"- **Successful Evaluations:** {summary.get('successful', 0)}")
        lines.append(f"- **Failed Evaluations:** {summary.get('failed', 0)}")
        lines.append(f"- **Success Rate:** {summary.get('success_rate', 0.0):.1%}")
        lines.append(f"- **Number of Judge Perspectives:** {summary.get('num_judges', 0)}")
        lines.append("")

        # Judge Perspectives
        if summary.get('judge_perspectives'):
            lines.append("### Judge Perspectives")
            lines.append("")
            for judge_name in summary['judge_perspectives']:
                lines.append(f"- **{judge_name}**: Independent evaluation rubric")
            lines.append("")

        # Overall Scores
        scores = self.report_data.get("scores", {})
        lines.append("## Overall Performance")
        lines.append("")
        lines.append(f"**Aggregated Overall Score:** {scores.get('overall_average', 0.0):.3f} / 1.000")
        lines.append("")

        # Scores by Judge
        if scores.get("by_judge"):
            lines.append("### Scores by Judge Perspective")
            lines.append("")
            lines.append("| Judge Perspective | Average Score |")
            lines.append("|-------------------|---------------|")
            for judge_name, score in scores["by_judge"].items():
                lines.append(f"| {judge_name.replace('_', ' ').title()} | {score:.3f} |")
            lines.append("")

        # Scores by Criterion
        if scores.get("by_criterion"):
            lines.append("### Scores by Evaluation Criterion")
            lines.append("")
            lines.append("| Criterion | Average Score |")
            lines.append("|-----------|---------------|")
            for criterion, score in scores["by_criterion"].items():
                criterion_name = criterion.replace("_", " ").title()
                lines.append(f"| {criterion_name} | {score:.3f} |")
            lines.append("")

        # Best and Worst Results
        if self.report_data.get("best_result"):
            best = self.report_data["best_result"]
            lines.append("## Best Performing Query")
            lines.append("")
            lines.append(f"**Query:** {best.get('query', '')}")
            lines.append(f"**Score:** {best.get('score', 0.0):.3f}")
            lines.append("")
            lines.append("*Note: See detailed results section below for the full system response.*")
            lines.append("")

        if self.report_data.get("worst_result"):
            worst = self.report_data["worst_result"]
            lines.append("## Worst Performing Query")
            lines.append("")
            lines.append(f"**Query:** {worst.get('query', '')}")
            lines.append(f"**Score:** {worst.get('score', 0.0):.3f}")
            lines.append("")
            lines.append("*Note: See detailed results section below for the full system response.*")
            lines.append("")

        # Detailed Results Summary
        lines.append("## Detailed Results by Query")
        lines.append("")

        detailed_results = self.report_data.get("detailed_results", [])
        for i, result in enumerate(detailed_results, 1):
            if "error" in result:
                lines.append(f"### Query {i}: ERROR")
                lines.append(f"**Error:** {result.get('error', 'Unknown error')}")
                lines.append("")
                continue

            query = result.get("query", "")
            evaluation = result.get("evaluation", {})
            overall_score = evaluation.get("overall_score", 0.0)

            lines.append(f"### Query {i}")
            lines.append("")
            lines.append(f"**Query:** {query}")
            lines.append("")

            # Include the system response
            response = result.get("response", "")
            if response:
                lines.append("**System Response:**")
                lines.append("")
                # Truncate very long responses for readability, but show full response
                if len(response) > 2000:
                    lines.append("```")
                    lines.append(response[:2000])
                    lines.append("...")
                    lines.append(f"[Response truncated. Full length: {len(response)} characters]")
                    lines.append("```")
                else:
                    lines.append("```")
                    lines.append(response)
                    lines.append("```")
                lines.append("")

            lines.append(f"**Overall Score:** {overall_score:.3f}")
            lines.append("")

            # Criterion scores
            criterion_scores = evaluation.get("criterion_scores", {})
            if criterion_scores:
                lines.append("**Criterion Scores:**")
                lines.append("")
                for criterion, score_data in criterion_scores.items():
                    score = score_data.get("score", 0.0) if isinstance(score_data, dict) else score_data
                    criterion_name = criterion.replace("_", " ").title()
                    lines.append(f"- {criterion_name}: {score:.3f}")
                lines.append("")

            # Judge-specific scores
            evaluations_by_judge = result.get("evaluations_by_judge", {})
            if evaluations_by_judge:
                lines.append("**Scores by Judge:**")
                lines.append("")
                for judge_name, judge_eval in evaluations_by_judge.items():
                    judge_score = judge_eval.get("overall_score", 0.0)
                    lines.append(f"- {judge_name.replace('_', ' ').title()}: {judge_score:.3f}")
                lines.append("")

        # Evaluation Methodology
        lines.append("## Evaluation Methodology")
        lines.append("")
        lines.append("### Task Prompts and Ground Truth Criteria")
        lines.append("")
        lines.append("The evaluation uses test queries specifically designed for Ethical AI in Education, each with:")
        lines.append("- **Ground truth/expected response**: Comprehensive answer covering key aspects")
        lines.append("- **Expected topics**: List of topics that should be addressed")
        lines.append("- **Expected sources**: Types of sources that should be consulted")
        lines.append("- **Evaluation notes**: Specific guidance for evaluators")
        lines.append("")

        lines.append("### Evaluation Criteria")
        lines.append("")
        lines.append("1. **Relevance & Coverage**: Does the response comprehensively address the query?")
        lines.append("2. **Evidence Use & Citation Quality**: Are sources credible, relevant, and properly cited?")
        lines.append("3. **Factual Accuracy & Consistency**: Is information correct and internally consistent?")
        lines.append("4. **Safety Compliance**: Does the response avoid unsafe or inappropriate content?")
        lines.append("5. **Clarity & Organization**: Is the response well-structured and easy to understand?")
        lines.append("")

        lines.append("### Judge Perspectives")
        lines.append("")
        lines.append("**Comprehensive Rubric Judge**: Evaluates responses using a detailed rubric-based approach,")
        lines.append("providing systematic, objective assessments across all dimensions.")
        lines.append("")
        lines.append("**Ethical Expert Judge**: Evaluates from the perspective of an expert in Ethical AI in Education,")
        lines.append("with deep knowledge of AI ethics principles, educational technology ethics, student privacy,")
        lines.append("algorithmic bias, and pedagogical implications. Focuses on practical applicability and")
        lines.append("alignment with established ethical frameworks.")
        lines.append("")

        lines.append("### Scoring")
        lines.append("")
        lines.append("Each criterion is scored on a 0.0-1.0 scale:")
        lines.append("- 0.0-0.3: Poor")
        lines.append("- 0.4-0.5: Below Average")
        lines.append("- 0.6-0.7: Average")
        lines.append("- 0.8-0.9: Good")
        lines.append("- 0.9-1.0: Excellent")
        lines.append("")
        lines.append("Scores from multiple judge perspectives are aggregated using weighted averaging.")
        lines.append("")

        return "\n".join(lines)

    def generate_latex_report(self) -> str:
        """
        Generate a LaTeX-formatted evaluation report.

        Returns:
            LaTeX string with evaluation report
        """
        lines = []

        lines.append("\\section{Evaluation Results}")
        lines.append("")

        summary = self.report_data.get("summary", {})
        scores = self.report_data.get("scores", {})

        lines.append("\\subsection{Executive Summary}")
        lines.append("")
        lines.append(f"Total queries evaluated: {summary.get('total_queries', 0)}. ")
        lines.append(f"Success rate: {summary.get('success_rate', 0.0):.1\\%}. ")
        lines.append(f"Overall average score: {scores.get('overall_average', 0.0):.3f}.")
        lines.append("")

        lines.append("\\subsection{Scores by Criterion}")
        lines.append("")
        lines.append("\\begin{table}[h]")
        lines.append("\\centering")
        lines.append("\\begin{tabular}{|l|c|}")
        lines.append("\\hline")
        lines.append("\\textbf{Criterion} & \\textbf{Score} \\\\")
        lines.append("\\hline")

        for criterion, score in scores.get("by_criterion", {}).items():
            criterion_name = criterion.replace("_", " ").title()
            lines.append(f"{criterion_name} & {score:.3f} \\\\")

        lines.append("\\hline")
        lines.append("\\end{tabular}")
        lines.append("\\caption{Average scores by evaluation criterion}")
        lines.append("\\end{table}")
        lines.append("")

        return "\n".join(lines)

    def save_report(self, output_path: str, format: str = "markdown"):
        """
        Save evaluation report to file.

        Args:
            output_path: Path to save the report
            format: Report format ("markdown" or "latex")
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if format == "markdown":
            content = self.generate_markdown_report()
            output_file = output_file.with_suffix(".md")
        elif format == "latex":
            content = self.generate_latex_report()
            output_file = output_file.with_suffix(".tex")
        else:
            raise ValueError(f"Unsupported format: {format}")

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"Report saved to {output_file}")


def load_and_generate_report(results_path: str, output_path: str, format: str = "markdown"):
    """
    Load evaluation results and generate a report.

    Args:
        results_path: Path to evaluation results JSON file
        output_path: Path to save the generated report
        format: Report format ("markdown" or "latex")
    """
    with open(results_path, 'r') as f:
        report_data = json.load(f)

    generator = EvaluationReportGenerator(report_data)
    generator.save_report(output_path, format)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python report_generator.py <results_json_path> <output_path> [format]")
        print("Format: markdown (default) or latex")
        sys.exit(1)

    results_path = sys.argv[1]
    output_path = sys.argv[2]
    format = sys.argv[3] if len(sys.argv) > 3 else "markdown"

    load_and_generate_report(results_path, output_path, format)
