# Technical Report: Multi-Agent Research System for Ethical AI in Education

## Abstract

This report presents the design, implementation, and evaluation of a multi-agent research system specialized in Ethical AI in Education. The system orchestrates four specialized agents (Planner, Researcher, Writer, and Critic) using AutoGen's RoundRobinGroupChat framework to collaboratively answer research queries. The Planner breaks down queries into actionable steps, the Researcher gathers evidence from academic papers and web sources using Semantic Scholar and Tavily APIs, the Writer synthesizes findings into coherent responses with proper citations, and the Critic evaluates quality and provides feedback. The system integrates safety guardrails using Guardrails AI to detect and handle unsafe inputs and outputs, with configurable response strategies including refusal, sanitization, and redirection. Evaluation was conducted using LLM-as-a-Judge methodology with two independent judge perspectives (comprehensive rubric and ethical expert) across five criteria: relevance and coverage, evidence use and citation quality, factual accuracy and consistency, safety compliance, and clarity and organization. The system achieved an overall average score of 0.588 across 8 test queries, with strong performance in safety compliance (0.951) but lower scores in factual accuracy (0.498). Key challenges included context length management, tool call validation, and ensuring citation quality. The system demonstrates the feasibility of multi-agent collaboration for domain-specific research while highlighting areas for improvement in source verification and response accuracy.

## System Design and Implementation

### 1.1 Agent Architecture

The system employs four specialized agents, each with distinct roles and capabilities:

**Planner Agent**: The Planner receives the initial query and breaks it down into actionable research steps. It has no tools and focuses solely on strategic planning. The Planner analyzes key concepts, determines appropriate source types (academic papers vs. web sources), suggests search queries and keywords, and outlines a synthesis approach.

**Researcher Agent**: The Researcher gathers evidence using two primary tools: `web_search()` (via Tavily API) and `paper_search()` (via Semantic Scholar API). The Researcher receives the plan, executes searches automatically based on natural language descriptions, and then selects the top 8 most relevant sources prioritizing by relevance scores (web) or citation count and recency (papers). It summarizes findings in 200-300 words, extracts key information, and notes citation details.

**Writer Agent**: The Writer synthesizes the Researcher's findings into a coherent response of 400-600 words. It structures the response with a brief introduction, logical sections, APA-style citations, and a references section. The Writer uses citation tools (`add_citation`, `format_citation`) to properly attribute sources. It paraphrases content rather than copying directly and ensures the response directly answers the query.

**Critic Agent**: The Critic evaluates the Writer's output for quality, accuracy, and completeness. It checks alignment with the original plan, verifies citations, identifies gaps or errors, and provides specific constructive feedback. The Critic assesses relevance to the query, source credibility, completeness, accuracy, clarity, synthesis quality, and appropriate length. It signals approval with "APPROVED - RESEARCH COMPLETE" or requests revision with "NEEDS REVISION".

### 1.2 Control Flow and Orchestration

The system uses AutoGen's `RoundRobinGroupChat` to orchestrate agent interactions. Agents communicate sequentially in a round-robin fashion: Planner → Researcher → Writer → Critic. The conversation terminates when the Critic outputs "APPROVED - RESEARCH COMPLETE" or when the maximum number of turns (8) is reached to prevent context length overflow. The orchestrator extracts the final response from the Writer's last message and includes full conversation history for debugging and UI display.

### 1.3 Tools and Integrations

**Web Search Tool**: Integrates with Tavily API to search the web for relevant articles, blog posts, and documentation. Results are filtered to the top 5 most relevant based on relevance scores, with snippets truncated to 100 characters to manage context length.

**Paper Search Tool**: Integrates with Semantic Scholar API to search academic papers. Results are sorted by citation count (descending) and year (descending), filtered to the top 8 most relevant papers, with abstracts truncated to 50 characters.

**Citation Tool**: Manages citations throughout the conversation using a module-level citation tracker. Provides functions to add citations, format them in APA style, get citation numbers, and generate a bibliography. Citations are automatically extracted from source metadata provided by search tools.

### 1.4 Model Configuration

All agents use the `openai/gpt-oss-20b` model via Groq API with a temperature of 0.7 for creative planning and synthesis. The model is configured with `max_tokens: 1500` to limit response length and prevent context overflow. Function calling is enabled for agents that use tools (Researcher, Writer), while the Planner explicitly has `tools=[]` to prevent tool calls. The system uses AutoGen's `OpenAIChatCompletionClient` with proper `ModelInfo` configuration including `family: GPT_4O` and `structured_output: True`.

## Safety Design

### 2.1 Safety Policies

The system implements comprehensive safety guardrails using the Guardrails AI framework. Prohibited categories include: harmful content, personal attacks, misinformation, and off-topic queries. The system is specialized for "Ethical AI in Education" and rejects queries outside this domain.

**Input Guardrails** check for: (1) Toxic language using Guardrails AI's `ToxicLanguage` validator, (2) Personally Identifiable Information (PII) using `DetectPII` validator, (3) Prompt injection using `DetectPromptInjection` validator and fallback regex patterns covering 20+ common injection techniques, and (4) Off-topic queries using a relevance check that flags queries with fewer than 3 words or those not related to Ethical AI in Education.

**Output Guardrails** check for: (1) Toxic language in generated responses, (2) PII that may have been included in responses, (3) Bias using `BiasCheck` validator, and (4) Factual consistency. Responses longer than 1500 characters are truncated before validation to avoid embedding model token limits, but the original full response is used for sanitization.

### 2.2 Response Strategies

The system implements configurable response strategies per violation type:

**Refuse**: For high-severity violations (toxic language, prompt injection), the system refuses the request and returns a user-friendly error message explaining why the request cannot be processed.

**Sanitize**: For PII and bias violations, the system sanitizes the content by redacting sensitive information (marked as "[REDACTED]") or adjusting biased language, then proceeds with the sanitized version.

**Redirect**: For off-topic queries, the system redirects users back to the specialized topic with a message explaining the system's focus area.

All safety events are logged to both system logs and a dedicated safety events log file, and violations are prominently displayed in the UI with detailed explanations.

## Evaluation Setup and Results

### 3.1 Dataset and Test Queries

Evaluation was conducted on 8 test queries from `data/test_queries.json`, each covering different aspects of Ethical AI in Education: ethical principles, bias detection, privacy concerns, student autonomy, automated grading, transparency, surveillance, and accountability frameworks. Each query includes expected topics, ground truth responses, expected source types, and evaluation notes.

### 3.2 Judge Prompts and Perspectives

Two independent judge perspectives were used to evaluate system outputs:

**Comprehensive Rubric Judge**: Uses a detailed rubric-based approach, providing systematic, objective assessments across all dimensions. This judge evaluates responses methodically using clear criteria.

**Ethical Expert Judge**: Evaluates from the perspective of an expert in Ethical AI in Education with deep knowledge of AI ethics principles, educational technology ethics, student privacy (FERPA, COPPA), algorithmic bias, transparency, accountability, and pedagogical implications. This judge focuses on practical applicability, stakeholder perspectives, alignment with ethical frameworks, and real-world implications.

Both judges score each criterion on a 0.0-1.0 scale: 0.0-0.3 (Poor), 0.4-0.5 (Below Average), 0.6-0.7 (Average), 0.8-0.9 (Good), 0.9-1.0 (Excellent). Scores are aggregated using weighted averaging (equal weights of 0.5 per judge).

### 3.3 Evaluation Criteria and Metrics

Five criteria were evaluated with the following weights:

1. **Relevance and Coverage** (25%): Does the response directly and comprehensively address the query? Includes addressing key aspects, covering relevant principles/frameworks, connecting to educational contexts, addressing stakeholder perspectives, and including practical implications.

2. **Evidence Use and Citation Quality** (25%): Are sources credible, relevant, and properly cited? Includes use of peer-reviewed sources, policy documents, proper APA formatting, integration of evidence, source diversity, and recency.

3. **Factual Accuracy and Consistency** (20%): Is information correct and internally consistent? Includes accurate representation of principles/frameworks, correct references to regulations, consistency in terminology, no contradictions, and proper understanding of technical concepts.

4. **Safety Compliance** (15%): Does the response avoid unsafe content? Includes no harmful/discriminatory content, no misinformation, appropriate handling of sensitive topics, balanced perspectives, and compliance with standards.

5. **Clarity and Organization** (15%): Is the response well-structured and easy to understand? Includes clear introduction, logical organization, smooth transitions, appropriate formatting, accessible language, appropriate length (400-600 words), and effective use of examples.

### 3.4 Evaluation Results

The system achieved an overall average score of **0.588** across all 8 queries. Performance by criterion:

- **Safety Compliance**: 0.951 (Excellent) - The system consistently produced safe, appropriate content.
- **Clarity and Organization**: 0.568 (Average) - Responses were generally well-structured but could be improved.
- **Relevance and Coverage**: 0.530 (Average) - Responses addressed queries but sometimes missed key aspects.
- **Evidence Use and Citation Quality**: 0.513 (Average) - Citations were present but quality varied.
- **Factual Accuracy and Consistency**: 0.498 (Below Average) - Significant room for improvement in accuracy.

### 3.5 Error Analysis

Key issues identified during evaluation:

1. **Tool Call Validation Errors**: Some queries failed due to malformed tool calls, particularly with citation tools. The Writer agent sometimes attempted to call tools with incorrect syntax, resulting in `BadRequestError: tool call validation failed`.

2. **Context Length Exceeded**: Despite implementing `max_turns: 8` and message buffer limits, some queries still exceeded context length, particularly when search results were extensive. The system now filters search results more aggressively (top 5 web, top 8 papers) and truncates content.

3. **Citation Quality Issues**: Judges noted that some citations appeared to be fabricated or unverifiable. The system relies on source metadata from search APIs, which may not always be accurate. Additionally, citation formatting sometimes lacked complete information.

4. **Factual Accuracy Concerns**: The lowest scoring criterion was factual accuracy (0.498). Judges found that while responses covered relevant topics, specific claims and citations were not always verifiable or accurate. This suggests the need for better source verification and fact-checking mechanisms.

## Discussion and Limitations

The development and evaluation of this multi-agent system revealed several important insights about building collaborative AI research assistants. The round-robin workflow proved effective at breaking down complex research tasks into manageable components, with each agent's specialization contributing unique value to the overall process. The iterative critique mechanism, where the Critic provides feedback to the Writer, demonstrates how multi-agent collaboration can improve response quality through structured refinement. The safety guardrails implemented using Guardrails AI successfully detected and handled unsafe inputs and outputs throughout the evaluation, with configurable response strategies providing flexibility to handle different types of violations appropriately. However, context management emerged as one of the most challenging aspects, requiring aggressive filtering of search results and strict message buffer limits to balance information completeness with token constraints. Tool integration with AutoGen required careful attention to schema design and error handling, highlighting the importance of defensive programming and graceful error recovery in production systems.

Despite these achievements, several key limitations persist that constrain the system's effectiveness. Context length constraints remain a fundamental challenge, with complex queries potentially exceeding token limits and resulting in incomplete or truncated responses. The revision mechanism is limited to a single cycle between Critic and Writer, which may be insufficient for queries requiring multiple iterations. The system's dependence on external APIs introduces reliability concerns, with no fallback mechanisms or caching strategies to mitigate failures. Additionally, the LLM-as-a-Judge evaluation methodology has inherent limitations, including potential judge biases and inconsistent evaluations. The system also lacks learning or memory capabilities, processing each query independently without leveraging previous interactions. Future work should focus on enhanced source verification mechanisms, including fact-checking against trusted knowledge bases and integration with citation databases for accurate metadata validation. The revision mechanism could support multiple iteration cycles with revision history tracking, while context management could be improved through summarization of earlier turns and dynamic token budgeting. Domain-specific fine-tuning on Ethical AI in Education literature would improve domain expertise, and robustness enhancements including retry logic for API failures and caching strategies would improve production reliability.
