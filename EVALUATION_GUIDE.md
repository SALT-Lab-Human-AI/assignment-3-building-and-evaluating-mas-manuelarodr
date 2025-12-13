# Evaluation Guide: LLM-as-a-Judge for Ethical AI in Education

This guide explains how to run and interpret the evaluation of the multi-agent research system.

## Overview

The evaluation system uses **LLM-as-a-Judge** methodology with **multiple independent judge perspectives** to evaluate system outputs on queries about Ethical AI in Education.

## Evaluation Components

### 1. Test Queries with Ground Truth

Test queries are defined in `data/test_queries.json`. Each query includes:
- **Query**: The research question
- **Category**: Topic category (e.g., "ethical_principles", "bias_detection")
- **Expected Topics**: List of topics that should be addressed
- **Ground Truth**: Comprehensive expected response covering key aspects
- **Expected Sources**: Types of sources that should be consulted
- **Evaluation Notes**: Specific guidance for evaluators

### 2. Evaluation Criteria

Five comprehensive criteria are used to evaluate responses:

1. **Relevance & Coverage** (weight: 0.25)
   - Does the response directly and comprehensively address the query?
   - Are all key aspects of the ethical question addressed?
   - Are stakeholder perspectives considered?

2. **Evidence Use & Citation Quality** (weight: 0.25)
   - Are sources credible, relevant, and properly cited?
   - Use of peer-reviewed academic sources
   - Proper APA-style citation formatting
   - Diversity and recency of sources

3. **Factual Accuracy & Consistency** (weight: 0.20)
   - Is the information correct and internally consistent?
   - Accurate representation of ethical principles and frameworks
   - Correct references to regulations and policies
   - No contradictory statements

4. **Safety Compliance** (weight: 0.15)
   - Does the response avoid unsafe or inappropriate content?
   - No harmful, discriminatory, or biased content
   - Appropriate handling of sensitive topics
   - Balanced perspectives

5. **Clarity & Organization** (weight: 0.15)
   - Is the response well-structured and easy to understand?
   - Clear introduction and logical organization
   - Appropriate use of formatting
   - Concise yet comprehensive (500-800 words)

### 3. Multiple Judge Perspectives

The system uses **at least 2 independent judge perspectives**:

#### Comprehensive Rubric Judge
- Evaluates using a detailed rubric-based approach
- Provides systematic, objective assessments
- Considers all dimensions of quality

#### Ethical Expert Judge
- Evaluates from the perspective of an expert in Ethical AI in Education
- Deep knowledge of:
  - AI ethics principles and frameworks
  - Educational technology ethics
  - Student privacy and data protection (FERPA, COPPA)
  - Algorithmic bias and fairness
  - Transparency, accountability, and explainability
  - Pedagogical implications
- Focuses on practical applicability and alignment with ethical frameworks

### 4. Scoring System

Each criterion is scored on a **0.0-1.0 scale**:
- **0.0-0.3**: Poor - Major deficiencies
- **0.4-0.5**: Below Average - Significant gaps
- **0.6-0.7**: Average - Meets basic requirements
- **0.8-0.9**: Good - Strong performance
- **0.9-1.0**: Excellent - Outstanding performance

Scores from multiple judge perspectives are aggregated using weighted averaging.

## Running the Evaluation

### Prerequisites

1. Set up environment variables:
   ```bash
   export GROQ_API_KEY=your_api_key_here
   ```

2. Ensure the system is configured:
   - `config.yaml` has `evaluation.enabled: true`
   - Test queries are in `data/test_queries.json`

### Running Evaluation

```bash
python main.py --mode evaluate
```

Or directly:
```python
import asyncio
import yaml
from dotenv import load_dotenv
from src.autogen_orchestrator import AutoGenOrchestrator
from src.evaluation.evaluator import SystemEvaluator

load_dotenv()

with open("config.yaml", 'r') as f:
    config = yaml.safe_load(f)

orchestrator = AutoGenOrchestrator(config)
evaluator = SystemEvaluator(config, orchestrator=orchestrator)

report = await evaluator.evaluate_system("data/test_queries.json")
```

### Output Files

The evaluation generates several output files in `outputs/`:

1. **`evaluation_YYYYMMDD_HHMMSS.json`**: Complete evaluation results in JSON format
2. **`evaluation_summary_YYYYMMDD_HHMMSS.txt`**: Text summary of results
3. **`evaluation_report_YYYYMMDD_HHMMSS.md`**: Markdown report for inclusion in write-up

## Interpreting Results

### Overall Scores

- **Overall Average Score**: Weighted average across all criteria and queries
- **Scores by Judge**: Average scores from each judge perspective
- **Scores by Criterion**: Average scores for each evaluation criterion

### Detailed Results

Each query includes:
- Overall score (aggregated from multiple judges)
- Individual criterion scores
- Scores from each judge perspective
- Detailed reasoning from judges

### Best and Worst Results

The report identifies:
- **Best Result**: Query with highest overall score
- **Worst Result**: Query with lowest overall score

These can help identify:
- What types of queries the system handles well
- Areas where the system needs improvement

## Using Results in Write-Up

The evaluation report includes:

1. **Executive Summary**: High-level statistics
2. **Overall Performance**: Aggregated scores
3. **Scores by Criterion**: Performance breakdown
4. **Scores by Judge**: Comparison of judge perspectives
5. **Detailed Results**: Query-by-query analysis
6. **Evaluation Methodology**: Description of evaluation approach

You can use the generated markdown report (`evaluation_report_*.md`) as a starting point for your technical write-up.

## Customization

### Adding New Test Queries

Edit `data/test_queries.json` to add queries with:
- Query text
- Category
- Expected topics
- Ground truth
- Expected sources
- Evaluation notes

### Modifying Evaluation Criteria

Edit `config.yaml` under `evaluation.criteria` to:
- Add new criteria
- Modify weights
- Update descriptions

### Adding Judge Perspectives

Edit `config.yaml` under `evaluation.judges` to add new judge perspectives with:
- Name
- Description
- Weight

Then implement the perspective instructions in `src/evaluation/judge.py` in the `_get_perspective_instructions` method.

## Troubleshooting

### Evaluation Fails

- Check that `GROQ_API_KEY` is set
- Verify test queries file exists and is valid JSON
- Check that orchestrator is working correctly

### Low Scores

- Review detailed reasoning from judges
- Check if queries match system capabilities
- Verify ground truth expectations are reasonable
- Consider adjusting criteria weights

### Inconsistent Judge Scores

- This is expected - different perspectives may emphasize different aspects
- Review individual judge reasoning to understand differences
- Consider if judge perspectives need adjustment

## Example Evaluation Output

```
EVALUATION RESULTS
======================================================================

Total Queries: 8
Successful: 8
Failed: 0
Success Rate: 100.00%
Number of Judges: 2

Overall Average Score: 0.782

Average Scores by Judge Perspective:
  comprehensive_rubric: 0.775
  ethical_expert: 0.789

Average Scores by Criterion:
  relevance_and_coverage: 0.810
  evidence_use_and_citation_quality: 0.765
  factual_accuracy_and_consistency: 0.790
  safety_compliance: 0.850
  clarity_and_organization: 0.695
```

This shows the system performs well overall (0.782), with strong safety compliance and relevance, but could improve in clarity and organization.
