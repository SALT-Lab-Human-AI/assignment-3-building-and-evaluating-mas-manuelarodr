"""
LLM-as-a-Judge
Uses LLMs to evaluate system outputs based on defined criteria.

Example usage:
    # Initialize judge with config
    judge = LLMJudge(config)

    # Evaluate a response
    result = await judge.evaluate(
        query="What is the capital of France?",
        response="Paris is the capital of France.",
        sources=[],
        ground_truth="Paris"
    )

    print(f"Overall Score: {result['overall_score']}")
    print(f"Criterion Scores: {result['criterion_scores']}")
"""

from typing import Dict, Any, List, Optional
import logging
import json
import os
import re
from groq import Groq


class LLMJudge:
    """
    LLM-based judge for evaluating system responses.

    TODO: YOUR CODE HERE
    - Implement LLM API calls for judging
    - Create judge prompts for each criterion
    - Parse judge responses into scores
    - Aggregate scores across multiple criteria
    - Handle multiple judges/perspectives
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize LLM judge.

        Args:
            config: Configuration dictionary (from config.yaml)
        """
        self.config = config
        self.logger = logging.getLogger("evaluation.judge")

        # Load judge model configuration from config.yaml (models.judge)
        # This includes: provider, name, temperature, max_tokens
        self.model_config = config.get("models", {}).get("judge", {})

        # Load evaluation criteria from config.yaml (evaluation.criteria)
        # Each criterion has: name, weight, description
        self.criteria = config.get("evaluation", {}).get("criteria", [])

        # Initialize Groq client (similar to what we tried in Lab 5)
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            self.logger.warning("GROQ_API_KEY not found in environment")
        self.client = Groq(api_key=api_key) if api_key else None

        self.logger.info(f"LLMJudge initialized with {len(self.criteria)} criteria")

    async def evaluate(
        self,
        query: str,
        response: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        ground_truth: Optional[str] = None,
        judge_perspective: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a response using LLM-as-a-Judge.

        Args:
            query: The original query
            response: The system's response
            sources: Sources used in the response
            ground_truth: Optional ground truth/expected response
            judge_perspective: Optional judge perspective name (e.g., "comprehensive_rubric", "ethical_expert")

        Returns:
            Dictionary with scores for each criterion and overall score
        """
        self.logger.info(f"Evaluating response for query: {query[:50]}...")
        if judge_perspective:
            self.logger.info(f"Using judge perspective: {judge_perspective}")

        results = {
            "query": query,
            "judge_perspective": judge_perspective or "default",
            "overall_score": 0.0,
            "criterion_scores": {},
            "feedback": [],
        }

        total_weight = sum(c.get("weight", 1.0) for c in self.criteria)
        weighted_score = 0.0

        # Evaluate each criterion
        for criterion in self.criteria:
            criterion_name = criterion.get("name", "unknown")
            weight = criterion.get("weight", 1.0)

            self.logger.info(f"Evaluating criterion: {criterion_name}")

            score = await self._judge_criterion(
                criterion=criterion,
                query=query,
                response=response,
                sources=sources,
                ground_truth=ground_truth,
                judge_perspective=judge_perspective
            )

            results["criterion_scores"][criterion_name] = score
            weighted_score += score.get("score", 0.0) * weight

        # Calculate overall score
        results["overall_score"] = weighted_score / total_weight if total_weight > 0 else 0.0

        return results

    async def _judge_criterion(
        self,
        criterion: Dict[str, Any],
        query: str,
        response: str,
        sources: Optional[List[Dict[str, Any]]],
        ground_truth: Optional[str],
        judge_perspective: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Judge a single criterion.

        Args:
            criterion: Criterion configuration
            query: Original query
            response: System response
            sources: Sources used
            ground_truth: Optional ground truth
            judge_perspective: Optional judge perspective name

        Returns:
            Score and feedback for this criterion
        """
        criterion_name = criterion.get("name", "unknown")
        description = criterion.get("description", "")

        # Create judge prompt with perspective-specific instructions
        prompt = self._create_judge_prompt(
            criterion_name=criterion_name,
            description=description,
            query=query,
            response=response,
            sources=sources,
            ground_truth=ground_truth,
            judge_perspective=judge_perspective
        )

        # Call LLM API to get judgment
        try:
            judgment = await self._call_judge_llm(prompt, judge_perspective)
            score_value, reasoning = self._parse_judgment(judgment)

            score = {
                "score": score_value,  # 0-1 scale
                "reasoning": reasoning,
                "criterion": criterion_name
            }
        except Exception as e:
            self.logger.error(f"Error judging criterion {criterion_name}: {e}")
            score = {
                "score": 0.0,
                "reasoning": f"Error during evaluation: {str(e)}",
                "criterion": criterion_name
            }

        return score

    def _create_judge_prompt(
        self,
        criterion_name: str,
        description: str,
        query: str,
        response: str,
        sources: Optional[List[Dict[str, Any]]],
        ground_truth: Optional[str],
        judge_perspective: Optional[str] = None
    ) -> str:
        """
        Create a prompt for the judge LLM with perspective-specific instructions.

        Args:
            criterion_name: Name of the criterion
            description: Detailed description of the criterion
            query: Original query
            response: System response to evaluate
            sources: Sources used in the response
            ground_truth: Optional ground truth/expected response
            judge_perspective: Judge perspective ("comprehensive_rubric", "ethical_expert", or None for default)

        Returns:
            Formatted prompt string
        """
        # Get perspective-specific system instructions
        perspective_instructions = self._get_perspective_instructions(judge_perspective)

        prompt = f"""{perspective_instructions}

You are evaluating a research response about Ethical AI in Education. The response was generated by a multi-agent research system.

**EVALUATION CRITERION: {criterion_name.upper().replace('_', ' ')}**

**Criterion Description:**
{description}

**ORIGINAL QUERY:**
{query}

**SYSTEM RESPONSE TO EVALUATE:**
{self._truncate_response(response)}
"""

        # Add sources information if available
        if sources:
            sources_info = f"\n**SOURCES USED:** {len(sources)} sources"
            if len(sources) > 0:
                sources_info += "\nSource types: " + ", ".join(set(s.get("type", "unknown") for s in sources[:5]))
            prompt += sources_info

        # Add ground truth if available
        if ground_truth:
            prompt += f"""

**EXPECTED/GROUND TRUTH RESPONSE (for reference):**
{ground_truth}
"""

        # Add scoring rubric
        prompt += f"""

**SCORING RUBRIC:**
- 0.0-0.3: Poor - Major deficiencies, does not meet criterion
- 0.4-0.5: Below Average - Significant gaps or issues
- 0.6-0.7: Average - Meets basic requirements but has notable weaknesses
- 0.8-0.9: Good - Strong performance with minor areas for improvement
- 0.9-1.0: Excellent - Outstanding performance, exceeds expectations

**YOUR TASK:**
Evaluate the system response specifically on the criterion "{criterion_name}" for the query about Ethical AI in Education.

Consider:
1. How well does the response address this specific criterion?
2. Are there strengths or weaknesses specific to this criterion?
3. How does this relate to Ethical AI in Education contexts?

**REQUIRED OUTPUT FORMAT (JSON only):**
{{
    "score": <float between 0.0 and 1.0>,
    "reasoning": "<detailed explanation of your score, including specific examples from the response>"
}}

Provide your evaluation now:
"""

        return prompt

    def _truncate_response(self, response: str, max_length: int = 2000) -> str:
        """
        Truncate system response in prompt to leave room for judge's JSON output.

        Args:
            response: Full system response
            max_length: Maximum length to keep (default 2000 chars)

        Returns:
            Truncated response with indicator if truncated
        """
        if len(response) <= max_length:
            return response

        # Truncate but keep the beginning (most important content)
        truncated = response[:max_length]
        # Try to truncate at a sentence boundary if possible
        last_period = truncated.rfind('.')
        last_newline = truncated.rfind('\n')
        cutoff = max(last_period, last_newline)

        if cutoff > max_length * 0.8:  # Only use boundary if it's not too early
            truncated = truncated[:cutoff + 1]

        return truncated + f"\n\n[Response truncated for evaluation - original length: {len(response)} characters]"

    def _get_perspective_instructions(self, judge_perspective: Optional[str]) -> str:
        """
        Get perspective-specific instructions for the judge.

        Args:
            judge_perspective: Name of the judge perspective

        Returns:
            Instructions string for the judge
        """
        if judge_perspective == "comprehensive_rubric":
            return """You are an expert evaluator using a comprehensive rubric-based approach. You evaluate research responses systematically across multiple dimensions, providing detailed, structured assessments. Your evaluations are thorough, objective, and based on clear criteria. You consider all aspects of the response and provide balanced feedback."""

        elif judge_perspective == "ethical_expert":
            return """You are an expert in Ethical AI in Education with deep knowledge of:
- AI ethics principles and frameworks
- Educational technology ethics
- Student privacy and data protection (FERPA, COPPA)
- Algorithmic bias and fairness in educational contexts
- Transparency, accountability, and explainability in educational AI
- Pedagogical implications of AI systems

You evaluate responses from the perspective of someone who understands both the technical aspects of AI and the ethical considerations specific to educational settings. You pay special attention to:
- Practical applicability to educational contexts
- Consideration of multiple stakeholder perspectives (students, educators, parents, institutions)
- Alignment with established ethical frameworks
- Real-world implications and potential harms
- Balance between innovation and ethical safeguards

Your evaluations are informed by both theoretical understanding and practical experience with ethical AI in education."""

        else:
            # Default perspective
            return """You are an expert evaluator specializing in research quality assessment. You evaluate responses based on established academic and professional standards, considering relevance, evidence quality, accuracy, safety, and clarity."""

    async def _call_judge_llm(self, prompt: str, judge_perspective: Optional[str] = None) -> str:
        """
        Call LLM API to get judgment.
        Uses model configuration from config.yaml (models.judge section).
        """
        if not self.client:
            raise ValueError("Groq client not initialized. Check GROQ_API_KEY environment variable.")

        try:
            # Load model settings from config.yaml (models.judge)
            model_name = self.model_config.get("name", "llama-3.1-8b-instant")
            temperature = self.model_config.get("temperature", 0.3)
            max_tokens = self.model_config.get("max_tokens", 1024)

            self.logger.debug(f"Calling Groq API with model: {model_name} (perspective: {judge_perspective or 'default'})")

            # System message based on perspective
            system_message = "You are an expert evaluator. Provide your evaluations in valid JSON format only. Do not include any text outside the JSON object."

            # Call Groq API
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": system_message
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            response = chat_completion.choices[0].message.content
            self.logger.debug(f"Received response: {response[:100]}...")

            return response

        except Exception as e:
            self.logger.error(f"Error calling Groq API: {e}")
            raise

    def _parse_judgment(self, judgment: str) -> tuple:
        """
        Parse LLM judgment response.
        Handles truncated JSON by attempting to extract score from partial responses.
        """
        import re

        try:
            # Clean up the response - remove markdown code blocks if present
            judgment_clean = judgment.strip()
            if judgment_clean.startswith("```json"):
                judgment_clean = judgment_clean[7:]
            elif judgment_clean.startswith("```"):
                judgment_clean = judgment_clean[3:]
            if judgment_clean.endswith("```"):
                judgment_clean = judgment_clean[:-3]
            judgment_clean = judgment_clean.strip()

            # Try to parse JSON
            try:
                result = json.loads(judgment_clean)
                score = float(result.get("score", 0.0))
                reasoning = result.get("reasoning", "")
            except json.JSONDecodeError:
                # If JSON is invalid (likely truncated), try to extract score using regex
                self.logger.warning("JSON parse failed, attempting to extract score from truncated response")

                # Try to extract score using regex pattern: "score":0.95 or "score": 0.95
                score_match = re.search(r'"score"\s*:\s*([0-9.]+)', judgment_clean)
                if score_match:
                    score = float(score_match.group(1))
                    # Try to extract reasoning (may be truncated)
                    reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]*)', judgment_clean)
                    if reasoning_match:
                        reasoning = reasoning_match.group(1)
                        # If reasoning was truncated, indicate it
                        if not judgment_clean.rstrip().endswith('"') and not judgment_clean.rstrip().endswith('}'):
                            reasoning += " [truncated]"
                    else:
                        reasoning = "Reasoning not found in truncated response"
                else:
                    # If we can't extract score, return error
                    raise ValueError("Could not extract score from truncated JSON")

            # Validate score is in range [0, 1]
            score = max(0.0, min(1.0, score))

            return score, reasoning

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")
            self.logger.error(f"Raw judgment: {judgment[:200]}")
            # Try one more time with regex extraction
            try:
                score_match = re.search(r'"score"\s*:\s*([0-9.]+)', judgment)
                if score_match:
                    score = float(score_match.group(1))
                    score = max(0.0, min(1.0, score))
                    return score, "Score extracted from truncated JSON response"
            except:  # nosec B110 - Fallback error handling for JSON parsing
                pass
            return 0.0, f"Error parsing judgment: Invalid JSON"
        except Exception as e:
            self.logger.error(f"Error parsing judgment: {e}")
            return 0.0, f"Error parsing judgment: {str(e)}"



async def example_basic_evaluation():
    """
    Example 1: Basic evaluation with LLMJudge

    Usage:
        import asyncio
        from src.evaluation.judge import example_basic_evaluation
        asyncio.run(example_basic_evaluation())
    """
    import yaml
    from dotenv import load_dotenv

    load_dotenv()

    # Load config
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)

    # Initialize judge
    judge = LLMJudge(config)

    # Test case (similar to Lab 5)
    print("=" * 70)
    print("EXAMPLE 1: Basic Evaluation")
    print("=" * 70)

    query = "What is the capital of France?"
    response = "Paris is the capital of France. It is known for the Eiffel Tower."
    ground_truth = "Paris"

    print(f"\nQuery: {query}")
    print(f"Response: {response}")
    print(f"Ground Truth: {ground_truth}\n")

    # Evaluate
    result = await judge.evaluate(
        query=query,
        response=response,
        sources=[],
        ground_truth=ground_truth
    )

    print(f"Overall Score: {result['overall_score']:.3f}\n")
    print("Criterion Scores:")
    for criterion, score_data in result['criterion_scores'].items():
        print(f"  {criterion}: {score_data['score']:.3f}")
        print(f"    Reasoning: {score_data['reasoning'][:100]}...")
        print()


async def example_compare_responses():
    """
    Example 2: Compare multiple responses

    Usage:
        import asyncio
        from src.evaluation.judge import example_compare_responses
        asyncio.run(example_compare_responses())
    """
    import yaml
    from dotenv import load_dotenv

    load_dotenv()

    # Load config
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)

    # Initialize judge
    judge = LLMJudge(config)

    print("=" * 70)
    print("EXAMPLE 2: Compare Multiple Responses")
    print("=" * 70)

    query = "What causes climate change?"
    ground_truth = "Climate change is primarily caused by increased greenhouse gas emissions from human activities, including burning fossil fuels, deforestation, and industrial processes."

    responses = [
        "Climate change is primarily caused by greenhouse gas emissions from human activities.",
        "The weather changes because of natural cycles and the sun's activity.",
        "Climate change is a complex phenomenon involving multiple factors including CO2 emissions, deforestation, and industrial processes."
    ]

    print(f"\nQuery: {query}\n")
    print(f"Ground Truth: {ground_truth}\n")

    results = []
    for i, response in enumerate(responses, 1):
        print(f"\n{'='*70}")
        print(f"Response {i}:")
        print(f"{response}")
        print(f"{'='*70}")

        result = await judge.evaluate(
            query=query,
            response=response,
            sources=[],
            ground_truth=ground_truth
        )

        results.append(result)

        print(f"\nOverall Score: {result['overall_score']:.3f}")
        print("\nCriterion Scores:")
        for criterion, score_data in result['criterion_scores'].items():
            print(f"  {criterion}: {score_data['score']:.3f}")
        print()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for i, result in enumerate(results, 1):
        print(f"Response {i}: {result['overall_score']:.3f}")

    best_idx = max(range(len(results)), key=lambda i: results[i]['overall_score'])
    print(f"\nBest Response: Response {best_idx + 1}")


# For direct execution
if __name__ == "__main__":
    import asyncio

    print("Running LLMJudge Examples\n")

    # Run example 1
    asyncio.run(example_basic_evaluation())

    print("\n\n")

    # Run example 2
    asyncio.run(example_compare_responses())
