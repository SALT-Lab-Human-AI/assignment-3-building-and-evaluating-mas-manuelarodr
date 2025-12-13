"""
AutoGen Agent Implementations

This module provides concrete AutoGen-based implementations of the research agents.
Each agent is implemented as an AutoGen AssistantAgent with specific tools and behaviors.

Based on the AutoGen literature review example:
https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/examples/literature-review.html
"""

import os
import logging
from typing import Dict, Any, List, Optional
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import ModelFamily
# Import our research tools
from src.tools.web_search import web_search
from src.tools.paper_search import paper_search
from src.tools.citation_tool import (
    format_citation,
    add_citation,
    get_citation_number,
    generate_bibliography,
    clear_citations,
    SourceModel,  # Pydantic model for better schema generation
)

# Set up logger for autogen agents
logger = logging.getLogger("agents.autogen")


def create_model_client(config: Dict[str, Any]) -> OpenAIChatCompletionClient:
    """
    Create model client for AutoGen agents.

    Args:
        config: Configuration dictionary from config.yaml

    Returns:
        OpenAIChatCompletionClient configured for the specified provider
    """
    model_config = config.get("models", {}).get("default", {})
    provider = model_config.get("provider", "groq")

    # Groq configuration (uses OpenAI-compatible API)
    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment")

        # Get max_tokens from config to limit response length
        max_tokens = model_config.get("max_tokens", 1500)

        return OpenAIChatCompletionClient(
            model=model_config.get("name", "openai/gpt-oss-20b"),
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            model_info={
                "json_output": True,
                "vision": False,
                "function_calling": True,
                "structured_output": True,
                "family": ModelFamily.GPT_4O,
                "max_tokens": max_tokens  # Limit response length
            }
        )

    # OpenAI configuration
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        # Get max_tokens from config to limit response length
        max_tokens = model_config.get("max_tokens", 1500)

        return OpenAIChatCompletionClient(
            model=model_config.get("name", "gpt-4o-mini"),
            api_key=api_key,
            base_url=base_url,
            model_info={
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "structured_output": True,
                "max_tokens": max_tokens  # Limit response length
            },
        )

    elif provider == "vllm":
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        # Get max_tokens from config to limit response length
        max_tokens = model_config.get("max_tokens", 1500)

        return OpenAIChatCompletionClient(
            model=model_config.get("name", "gpt-4o-mini"),
            api_key=api_key,
            base_url=base_url,
            model_info={
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": ModelFamily.GPT_4O,
                "structured_output": True,
                "max_tokens": max_tokens  # Limit response length
            },
        )

    else:
        raise ValueError(f"Unsupported provider: {provider}")


def create_planner_agent(config: Dict[str, Any], model_client: OpenAIChatCompletionClient) -> AssistantAgent:
    """
    Create a Planner Agent using AutoGen.

    The planner breaks down research queries into actionable steps.
    It doesn't use tools, but provides strategic direction.

    Args:
        config: Configuration dictionary
        model_client: Model client for the agent

    Returns:
        AutoGen AssistantAgent configured as a planner
    """
    agent_config = config.get("agents", {}).get("planner", {})

    # Use the shared model client - tools=[] will prevent tool calls
    # We keep function_calling enabled in model_info because AutoGen validates this,
    # but passing tools=[] ensures no tools are available to the Planner
    planner_model_client = model_client

    # Load system prompt from config or use default
    default_system_message = """Research planner. Break down queries into actionable steps (150-200 words max). You have NO tools - only create plans. Steps: 1) Analyze concepts, 2) Determine source types, 3) Suggest search queries, 4) Outline synthesis. Provide numbered steps. End with "PLAN COMPLETE"."""

    # Use custom prompt from config if available, otherwise use default
    custom_prompt = agent_config.get("system_prompt", "")
    if custom_prompt and custom_prompt != "You are a task planner. Break down research queries into actionable steps.":
        system_message = custom_prompt
        # Always add reminder about no tools if not already present
        if "do NOT have access to any tools" not in system_message and "CRITICAL: Do NOT attempt to use any tools" not in system_message:
            system_message += "\n\nCRITICAL: You do NOT have access to any tools, search functions, or browsing capabilities. You only create plans - the Researcher agent will handle all searching and information gathering."
    else:
        system_message = default_system_message

    # Debug: Log model_info to verify function_calling is set
    if hasattr(planner_model_client, 'model_info'):
        model_info = planner_model_client.model_info
        logger.debug(f"Planner model_info: function_calling={model_info.get('function_calling', 'NOT SET')}")
        logger.debug(f"Planner model_info keys: {list(model_info.keys()) if isinstance(model_info, dict) else 'N/A'}")

    try:
        planner = AssistantAgent(
            name="Planner",
            model_client=planner_model_client,
            tools=[],  # Explicitly no tools - Planner only creates plans
            description="Breaks down research queries into actionable steps",
            system_message=system_message,
        )
        logger.info("Planner agent created successfully")
    except ValueError as e:
        if "function calling" in str(e).lower():
            logger.error(f"Planner agent creation failed: {e}")
            logger.error("This may be due to AutoGen's function calling validation. Model info:")
            if hasattr(planner_model_client, 'model_info'):
                logger.error(f"  {planner_model_client.model_info}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating Planner agent: {e}")
        raise

    return planner


def create_researcher_agent(config: Dict[str, Any], model_client: OpenAIChatCompletionClient) -> AssistantAgent:
    """
    Create a Researcher Agent using AutoGen.

    The researcher has access to web search and paper search tools.
    It gathers evidence based on the planner's guidance.

    Args:
        config: Configuration dictionary
        model_client: Model client for the agent

    Returns:
        AutoGen AssistantAgent configured as a researcher with tool access
    """
    agent_config = config.get("agents", {}).get("researcher", {})

    # Load system prompt from config or use default
    default_system_message = """Researcher. Gather credible info from papers and web (200-300 words max). Tools work automatically - describe needs in natural language. Select ONLY top 8 sources: prioritize by relevance score (web) or citations/recency (papers). Process: 1) Review plan, 2) State info needs, 3) Select 8 most relevant, 4) Extract findings, 5) Note citations. End with "RESEARCH COMPLETE"."""

    # Use custom prompt from config if available
    custom_prompt = agent_config.get("system_prompt", "")
    if custom_prompt and custom_prompt != "You are a researcher. Find and collect relevant information from various sources.":
        # Clean up custom prompt to remove function call syntax that might confuse the model
        system_message = custom_prompt.replace("web_search()", "web search").replace("paper_search()", "paper search")
        system_message = system_message.replace("<function", "").replace("</function>", "").replace("function=", "")
        # Always add strong clarification about not using function call syntax
        system_message += "\n\nCRITICAL: Never write function calls, XML tags like <function>, or any function syntax in your responses. The tools work automatically when you describe what you need. Just use natural language like 'I need to find articles about X' - the system handles the rest."
    else:
        system_message = default_system_message

    # Wrap tools in FunctionTool
    logger.info("Creating web_search_tool for Researcher agent")
    web_search_tool = FunctionTool(
        web_search,
        description="Web search for articles and information. Params: query (string), max_results (int, default=5)."
    )
    logger.debug(f"web_search_tool created: {web_search_tool}")

    logger.info("Creating paper_search_tool for Researcher agent")
    paper_search_tool = FunctionTool(
        paper_search,
        description="Search academic papers on Semantic Scholar. Params: query (string), max_results (int, default=10), year_from (int, optional). Returns papers with authors, abstracts, citations, URLs."
    )
    logger.debug(f"paper_search_tool created: {paper_search_tool}")

    # Create the researcher with tool access
    logger.info("Creating Researcher agent with tools")
    researcher = AssistantAgent(
        name="Researcher",
        model_client=model_client,
        tools=[web_search_tool, paper_search_tool],
        description="Gathers evidence from web and academic sources using search tools",
        system_message=system_message,
    )
    logger.info(f"Researcher agent created with {len([web_search_tool, paper_search_tool])} tools")

    return researcher


def create_writer_agent(config: Dict[str, Any], model_client: OpenAIChatCompletionClient) -> AssistantAgent:
    """
    Create a Writer Agent using AutoGen.

    The writer synthesizes research findings into coherent responses with proper citations.

    Args:
        config: Configuration dictionary
        model_client: Model client for the agent

    Returns:
        AutoGen AssistantAgent configured as a writer
    """
    agent_config = config.get("agents", {}).get("writer", {})

    # Load system prompt from config or use default
    default_system_message = """Writer for Ethical AI in Education. Synthesize Researcher's findings (400-600 words max). Structure: Brief intro → logical sections → APA citations → References. Paraphrase, don't copy. Citation tools work automatically - reference sources naturally. If Critic says "NEEDS REVISION", address feedback. If "APPROVED - RESEARCH COMPLETE", done."""

    # Use custom prompt from config if available
    custom_prompt = agent_config.get("system_prompt", "")
    if custom_prompt and custom_prompt != "You are a writer. Synthesize research findings into a coherent report.":
        # Clean up custom prompt to remove function call syntax
        system_message = custom_prompt.replace("add_citation()", "add citation").replace("generate_bibliography()", "generate bibliography")
        system_message = system_message.replace("<function", "").replace("</function>", "").replace("function=", "")
        # Always add strong clarification about not using function call syntax
        if "CRITICAL" not in system_message and "Never write function" not in system_message:
            system_message += "\n\nCRITICAL: Never write function calls, XML tags like <function>, or any function syntax. The citation tools work automatically - just use natural language."
    else:
        system_message = default_system_message

    # Wrap citation tools in FunctionTool
    logger.info("Creating citation tools for Writer agent")

    format_citation_tool = FunctionTool(
        format_citation,
        description="Format source as APA citation. Param 'source': dict with type, authors (list of {'name': str}), year, title (required); venue, url, doi, site_name (optional)."
    )
    logger.debug("format_citation_tool created")

    add_citation_tool = FunctionTool(
        add_citation,
        name="add_citation",
        description="Add source to citations. Param 'source': type ('paper'|'article'|'webpage'|'book'), authors ([{'name': str}]), year (int), title (str) - required; url, venue, doi, site_name (optional). Returns citation number."
    )
    logger.debug("add_citation_tool created")

    get_citation_number_tool = FunctionTool(
        get_citation_number,
        description="Get citation number for existing source. Param 'source': dict with 'title' (required) and optional fields. Returns citation number or 'not found'."
    )
    logger.debug("get_citation_number_tool created")

    generate_bibliography_tool = FunctionTool(
        generate_bibliography,
        description="Generate APA bibliography from all added citations. Returns numbered list sorted alphabetically. Use for References section."
    )
    logger.debug("generate_bibliography_tool created")

    clear_citations_tool = FunctionTool(
        clear_citations,
        description="Clear all citations. Use to reset for new task."
    )
    logger.debug("clear_citations_tool created")

    logger.info(f"Created {5} citation tools for Writer agent")

    # Create the writer with citation tool access
    writer_tools = [
        format_citation_tool,
        add_citation_tool,
        get_citation_number_tool,
        generate_bibliography_tool,
        clear_citations_tool,
    ]
    logger.info(f"Creating Writer agent with {len(writer_tools)} citation tools")
    writer = AssistantAgent(
        name="Writer",
        model_client=model_client,
        tools=writer_tools,
        description="Synthesizes research findings into coherent, well-cited responses",
        system_message=system_message,
    )
    logger.info("Writer agent created successfully")

    return writer


def create_critic_agent(config: Dict[str, Any], model_client: OpenAIChatCompletionClient) -> AssistantAgent:
    """
    Create a Critic Agent using AutoGen.

    The critic evaluates the quality of the research and writing,
    providing feedback for improvement.

    Args:
        config: Configuration dictionary
        model_client: Model client for the agent

    Returns:
        AutoGen AssistantAgent configured as a critic
    """
    agent_config = config.get("agents", {}).get("critic", {})

    # Load system prompt from config or use default
    default_system_message = """Peer reviewer. Evaluate for relevance, credible/well-cited sources, completeness, accuracy, clarity, synthesis, appropriate length (400-600 words). Provide specific constructive feedback. End with "APPROVED - RESEARCH COMPLETE" (if quality) OR "NEEDS REVISION" (if issues)."""

    # Use custom prompt from config if available
    custom_prompt = agent_config.get("system_prompt", "")
    if custom_prompt and custom_prompt != "You are a critic. Evaluate the quality and accuracy of research findings.":
        system_message = custom_prompt
    else:
        system_message = default_system_message

    critic = AssistantAgent(
        name="Critic",
        model_client=model_client,
        description="Evaluates research quality and provides feedback",
        system_message=system_message,
    )

    return critic


def create_research_team(config: Dict[str, Any], max_turns: int = None) -> RoundRobinGroupChat:
    """
    Create the research team as a RoundRobinGroupChat.

    Args:
        config: Configuration dictionary
        max_turns: Maximum number of turns (if None, uses max_turns from config)

    Returns:
        RoundRobinGroupChat with all agents configured
    """
    # Create model client (shared by all agents)
    model_client = create_model_client(config)

    # Create all agents
    planner = create_planner_agent(config, model_client)
    researcher = create_researcher_agent(config, model_client)
    writer = create_writer_agent(config, model_client)
    critic = create_critic_agent(config, model_client)

    # Create termination condition
    termination = TextMentionTermination("APPROVED - RESEARCH COMPLETE")

    # Get max_turns from parameter or config
    if max_turns is None:
        max_turns = config.get("system", {}).get("max_turns", 8)

    # Create team with round-robin ordering and max_turns limit
    team = RoundRobinGroupChat(
        participants=[planner, researcher, writer, critic],
        termination_condition=termination,
        max_turns=max_turns,  # Enforce turn limit to prevent context length errors
    )

    return team
