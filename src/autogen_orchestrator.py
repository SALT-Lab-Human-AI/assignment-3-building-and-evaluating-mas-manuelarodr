"""
AutoGen-Based Orchestrator

This orchestrator uses AutoGen's RoundRobinGroupChat to coordinate multiple agents
in a research workflow.

Workflow:
1. Planner: Breaks down the query into research steps
2. Researcher: Gathers evidence using web and paper search tools
3. Writer: Synthesizes findings into a coherent response
4. Critic: Evaluates quality and provides feedback
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.messages import TextMessage

from src.agents.autogen_agents import create_research_team


class AutoGenOrchestrator:
    """
    Orchestrates multi-agent research using AutoGen's RoundRobinGroupChat.

    This orchestrator manages a team of specialized agents that work together
    to answer research queries. It uses AutoGen's built-in conversation
    management and tool execution capabilities.
    """

    def __init__(self, config: Dict[str, Any], status_callback=None):
        """
        Initialize the AutoGen orchestrator.

        Args:
            config: Configuration dictionary from config.yaml
            status_callback: Optional callback function(status_dict) for status updates
        """
        self.config = config
        self.logger = logging.getLogger("autogen_orchestrator")
        self.status_callback = status_callback

        # Get max_turns from config with sensible default
        self.max_turns = config.get("system", {}).get("max_turns", 8)

        # Don't create team here - create it fresh for each query to avoid event loop binding issues
        # The team object has internal queues that get bound to event loops
        self.logger.info("Orchestrator initialized (team will be created per query)")

        # Workflow trace for debugging and UI display
        self.workflow_trace: List[Dict[str, Any]] = []

    def _update_status(self, agent: Optional[str] = None, stage: str = "processing", progress: float = 0.0, output: Optional[str] = None):
        """
        Update status and call callback if available.

        Args:
            agent: Current agent name
            stage: Workflow stage
            progress: Progress (0.0 to 1.0)
            output: Agent output
        """
        status = {
            'current_agent': agent,
            'workflow_stage': stage,
            'progress': progress,
            'output': output
        }
        if self.status_callback:
            try:
                self.status_callback(status)
            except Exception as e:
                self.logger.warning(f"Status callback error: {e}")

    async def process_query_async(self, query: str, max_turns: int = None) -> Dict[str, Any]:
        """
        Async version of process_query for use in async contexts (e.g., evaluation).

        Args:
            query: The research question to answer
            max_turns: Maximum number of conversation turns

        Returns:
            Dictionary containing:
            - query: Original query
            - response: Final synthesized response
            - conversation_history: Full conversation between agents
            - metadata: Additional information about the process
        """
        self.logger.info(f"Processing query (async): {query}")

        try:
            # Use max_turns from config if not provided
            if max_turns is None:
                max_turns = self.max_turns

            # Directly call the async implementation
            result = await self._process_query_async(query, max_turns)
            self.logger.info("Query processing complete (async)")
            return result

        except Exception as e:
            self.logger.error(f"Error processing query (async): {e}", exc_info=True)
            return {
                "query": query,
                "error": str(e),
                "response": f"An error occurred while processing your query: {str(e)}",
                "conversation_history": [],
                "metadata": {"error": True}
            }

    def process_query(self, query: str, max_turns: int = None) -> Dict[str, Any]:
        """
        Process a research query through the multi-agent system (synchronous version).

        This method is kept for backward compatibility with sync contexts (e.g., Streamlit).
        For async contexts (e.g., evaluation), use process_query_async() instead.

        Args:
            query: The research question to answer
            max_turns: Maximum number of conversation turns

        Returns:
            Dictionary containing:
            - query: Original query
            - response: Final synthesized response
            - conversation_history: Full conversation between agents
            - metadata: Additional information about the process
        """
        self.logger.info(f"Processing query (sync): {query}")

        try:
            # Use max_turns from config if not provided
            if max_turns is None:
                max_turns = self.max_turns

            # For Streamlit and other environments where event loops can conflict,
            # always use a fresh event loop in a new thread to avoid queue binding issues
            import concurrent.futures
            import threading

            def run_in_new_loop():
                """Run the async function in a completely new event loop."""
                # Create a new event loop for this thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(self._process_query_async(query, max_turns))
                finally:
                    new_loop.close()

            # Run in a separate thread with a fresh event loop
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_in_new_loop)
                result = future.result(timeout=300)  # 5 minute timeout

            self.logger.info("Query processing complete (sync)")
            return result

        except Exception as e:
            self.logger.error(f"Error processing query (sync): {e}", exc_info=True)
            return {
                "query": query,
                "error": str(e),
                "response": f"An error occurred while processing your query: {str(e)}",
                "conversation_history": [],
                "metadata": {"error": True}
            }

    async def _process_query_async(self, query: str, max_turns: int = 8) -> Dict[str, Any]:
        """
        Async implementation of query processing.

        Args:
            query: The research question to answer
            max_turns: Maximum number of conversation turns

        Returns:
            Dictionary containing results
        """
        # Create a fresh team for each query to avoid event loop binding issues
        # AutoGen's RoundRobinGroupChat has internal queues that get bound to event loops
        # Creating a new team ensures clean state for each query
        self.logger.info("Creating fresh research team for this query...")

        # Clear citation tool state to ensure clean start for each query
        from src.tools.citation_tool import clear_citations
        try:
            clear_citations()
            self.logger.debug("Citation tool cleared for new query")
        except Exception as e:
            self.logger.warning(f"Could not clear citations: {e}")

        try:
            # Pass max_turns to create_research_team so it can set max_turns on RoundRobinGroupChat
            team = create_research_team(self.config, max_turns=max_turns)
            self.logger.info(f"Research team created successfully (max_turns={max_turns})")
        except Exception as e:
            self.logger.error(f"Error creating research team: {e}", exc_info=True)
            # Return structured error instead of raising to allow evaluation to continue
            error_msg = str(e)
            if "function calling" in error_msg.lower():
                self.logger.error("Planner agent creation failed - model function calling validation issue")
                return {
                    "query": query,
                    "error": "Agent creation failed: " + error_msg,
                    "response": f"An error occurred while initializing the research team: {error_msg}. This may be due to a model configuration issue.",
                    "conversation_history": [],
                    "metadata": {
                        "error": True,
                        "error_type": "agent_creation_failed",
                        "error_message": error_msg
                    }
                }
            # For other errors, still raise to maintain existing behavior
            raise

        # Create task message
        task_message = f"""Research Query: {query}

Please work together to answer this query comprehensively:
1. Planner: Create a research plan
2. Researcher: Gather evidence from web and academic sources using the search tools
3. Writer: Review the Researcher's findings from the conversation and synthesize them into a well-cited response. Use ALL the sources and information the Researcher has gathered.
4. Critic: Evaluate the quality and provide feedback"""

        # Run the team
        self.logger.info(f"Starting team execution (max_turns: {max_turns})")
        self.logger.debug(f"Task message: {task_message[:200]}...")

        # Update status: Starting
        self._update_status(agent=None, stage="initializing", progress=0.1)

        try:
            # RoundRobinGroupChat has max_turns set in team creation
            # The termination condition and max_turns are handled by the team configuration
            self._update_status(agent=None, stage="running_agents", progress=0.2)
            result = await team.run(task=task_message)
            self.logger.info("Team execution completed")
            self._update_status(agent=None, stage="extracting_results", progress=0.9)
        except Exception as e:
            self.logger.error(f"Error during team execution: {e}", exc_info=True)
            self._update_status(agent=None, stage="error", progress=0.0)

            # Check if it's a context length error
            error_str = str(e)
            if "context_length_exceeded" in error_str or "Please reduce the length" in error_str:
                self.logger.warning("Context length exceeded - conversation history too long")
                raise ValueError(
                    "The conversation history has exceeded the model's context limit. "
                    "This usually happens when agents exchange too many messages. "
                    "Try reducing max_turns in config.yaml or simplifying your query."
                ) from e

            raise

        # Extract conversation history
        messages = []
        full_message_contents = {}  # Store full content for final response extraction and agent traces
        message_counts = {}  # Track message counts per agent for debugging

        # Log total messages from AutoGen
        total_messages = len(result.messages) if hasattr(result, 'messages') else 0
        self.logger.info(f"Extracting {total_messages} messages from AutoGen result")

        # result.messages is a list, not an async iterator
        total_msgs = len(result.messages)
        for idx, message in enumerate(result.messages):
            msg_source = getattr(message, 'source', 'Unknown')

            # Handle FunctionCall and other non-string content types
            if hasattr(message, 'content'):
                msg_content = message.content
                # Convert FunctionCall, lists, and other objects to string
                if isinstance(msg_content, list):
                    # Join list items into a string
                    msg_content = "\n".join(str(item) for item in msg_content) if msg_content else ""
                elif not isinstance(msg_content, str):
                    # Check if it's a FunctionCall or similar object
                    content_type = str(type(msg_content))
                    if 'FunctionCall' in content_type or hasattr(msg_content, 'name'):
                        # Format FunctionCall as readable string
                        tool_name = getattr(msg_content, 'name', 'unknown_tool')
                        args = getattr(msg_content, 'arguments', {})
                        if isinstance(args, dict):
                            args_str = ', '.join(f"{k}={v}" for k, v in args.items())
                        else:
                            args_str = str(args)
                        msg_content = f"[Tool Call: {tool_name}({args_str})]"
                    else:
                        msg_content = str(msg_content)
            else:
                msg_content = str(message)

            # Update status for UI display
            progress = (idx + 1) / total_msgs if total_msgs > 0 else 0.0
            self._update_status(
                agent=msg_source,
                stage="processing",
                progress=min(progress * 0.8, 0.8),  # Reserve 20% for final processing
                output=msg_content[:500] if len(msg_content) > 500 else msg_content  # Preview
            )

            # Track message counts per agent
            message_counts[msg_source] = message_counts.get(msg_source, 0) + 1

            # Store full content for all agents (needed for agent traces and final response)
            if msg_source not in full_message_contents:
                full_message_contents[msg_source] = []
            full_message_contents[msg_source].append(msg_content)

            # Log tool calls if present
            if hasattr(message, 'tool_calls') and message.tool_calls:
                self.logger.info(f"Tool call detected from {msg_source}: {len(message.tool_calls)} tool(s)")
                for tool_call in message.tool_calls:
                    self.logger.debug(f"  Tool: {getattr(tool_call, 'name', 'Unknown')}, "
                                    f"Args: {getattr(tool_call, 'arguments', {})}")

            # Store full content in messages (not truncated) for agent traces
            msg_dict = {
                "source": msg_source,
                "content": msg_content,  # Store full content, not truncated
            }
            messages.append(msg_dict)
            self.logger.debug(f"Message from {msg_source}: {len(msg_content)} chars")

        # Log message counts per agent
        self.logger.info(f"Messages extracted per agent: {message_counts}")
        self.logger.info(f"Total messages in conversation_history: {len(messages)}")

        # Extract final response - use full content, not truncated
        # The Writer produces the final output; the Critic only reviews it
        final_response = ""
        writer_response = ""
        critic_feedback = ""

        # Get Writer's last response (this is the actual output)
        if "Writer" in full_message_contents and full_message_contents["Writer"]:
            writer_response = full_message_contents["Writer"][-1]
            final_response = writer_response

        # Get Critic's feedback (for metadata, not as the main response)
        if "Critic" in full_message_contents and full_message_contents["Critic"]:
            critic_feedback = full_message_contents["Critic"][-1]
            # Only use Critic's response as fallback if Writer hasn't produced anything
            if not final_response:
                final_response = critic_feedback

        # Final fallback: get from last message
        if not final_response and messages:
            final_response = messages[-1].get("content", "")

        return self._extract_results(query, messages, final_response, critic_feedback)

    def _extract_results(self, query: str, messages: List[Dict[str, Any]], final_response: str = "", critic_feedback: str = "") -> Dict[str, Any]:
        """
        Extract structured results from the conversation history.

        Args:
            query: Original query
            messages: List of conversation messages
            final_response: Final response from the team (Writer's output)
            critic_feedback: Critic's evaluation/feedback

        Returns:
            Structured result dictionary
        """
        # Extract components from conversation
        research_findings = []
        plan = ""
        critique = critic_feedback  # Use the passed critic_feedback

        for msg in messages:
            source = msg.get("source", "")
            content = msg.get("content", "")

            if source == "Planner" and not plan:
                plan = content

            elif source == "Researcher":
                research_findings.append(content)

            elif source == "Critic" and not critique:
                # Only use this if critic_feedback wasn't passed
                critique = content

        # Count sources mentioned in research
        num_sources = 0
        for finding in research_findings:
            # Rough count of sources based on numbered results
            num_sources += finding.count("\n1.") + finding.count("\n2.") + finding.count("\n3.")

        # Clean up final response
        if final_response:
            final_response = final_response.replace("TERMINATE", "").strip()

        return {
            "query": query,
            "response": final_response,
            "conversation_history": messages,
            "metadata": {
                "num_messages": len(messages),
                "num_sources": max(num_sources, 1),  # At least 1
                "plan": plan,
                "research_findings": research_findings,
                "critique": critique,
                "agents_involved": list(set([msg.get("source", "") for msg in messages])),
            }
        }

    def get_agent_descriptions(self) -> Dict[str, str]:
        """
        Get descriptions of all agents.

        Returns:
            Dictionary mapping agent names to their descriptions
        """
        return {
            "Planner": "Breaks down research queries into actionable steps",
            "Researcher": "Gathers evidence from web and academic sources",
            "Writer": "Synthesizes findings into coherent responses",
            "Critic": "Evaluates quality and provides feedback",
        }

    def visualize_workflow(self) -> str:
        """
        Generate a text visualization of the workflow.

        Returns:
            String representation of the workflow
        """
        workflow = """
AutoGen Research Workflow:

1. User Query
   ↓
2. Planner
   - Analyzes query
   - Creates research plan
   - Identifies key topics
   ↓
3. Researcher (with tools)
   - Uses web_search() tool
   - Uses paper_search() tool
   - Gathers evidence
   - Collects citations
   ↓
4. Writer
   - Synthesizes findings
   - Creates structured response
   - Adds citations
   ↓
5. Critic
   - Evaluates quality
   - Checks completeness
   - Provides feedback
   ↓
6. Decision Point
   - If APPROVED → Final Response
   - If NEEDS REVISION → Back to Writer
        """
        return workflow


def demonstrate_usage():
    """
    Demonstrate how to use the AutoGen orchestrator.

    This function shows a simple example of using the orchestrator.
    """
    import yaml
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    # Load configuration
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    # Create orchestrator
    orchestrator = AutoGenOrchestrator(config)

    # Print workflow visualization
    print(orchestrator.visualize_workflow())

    # Example query
    query = "What are the latest trends in human-computer interaction research?"

    print(f"\nProcessing query: {query}\n")
    print("=" * 70)

    # Process query
    result = orchestrator.process_query(query)

    # Display results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"\nQuery: {result['query']}")
    print(f"\nResponse:\n{result['response']}")
    print(f"\nMetadata:")
    print(f"  - Messages exchanged: {result['metadata']['num_messages']}")
    print(f"  - Sources gathered: {result['metadata']['num_sources']}")
    print(f"  - Agents involved: {', '.join(result['metadata']['agents_involved'])}")


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    demonstrate_usage()
