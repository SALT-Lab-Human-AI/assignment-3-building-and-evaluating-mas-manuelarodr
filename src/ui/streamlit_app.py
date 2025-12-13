"""
Streamlit Web Interface
Web UI for the multi-agent research system.

Run with: streamlit run src/ui/streamlit_app.py
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import asyncio
import yaml
import logging
import os
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv
from io import StringIO

from src.autogen_orchestrator import AutoGenOrchestrator
from src.guardrails import SafetyManager
from src.ui.agent_status_display import display_agent_status, update_agent_status, clear_agent_status

# Load environment variables
load_dotenv()


def load_config():
    """Load configuration file."""
    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}


# Setup logging for Streamlit
def setup_logging():
    """Configure logging for Streamlit app."""
    os.makedirs("logs", exist_ok=True)

    # Get log level from config
    config = load_config()
    log_config = config.get("logging", {})
    log_level = log_config.get("level", "DEBUG")  # Default to DEBUG for detailed logs

    # Create a string buffer to capture logs for UI display
    log_capture = StringIO()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))

    # Clear existing handlers
    root_logger.handlers = []

    # File handler
    file_handler = logging.FileHandler("logs/streamlit.log")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Stream handler for console (terminal where Streamlit runs)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Reduce noise from some libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return log_capture

# Initialize logging
setup_logging()
logger = logging.getLogger("streamlit_app")


def initialize_session_state():
    """Initialize Streamlit session state."""
    if 'history' not in st.session_state:
        st.session_state.history = []

    # Agent status tracking for real-time display
    if 'agent_status' not in st.session_state:
        st.session_state.agent_status = {
            'current_agent': None,
            'agent_outputs': {},
            'workflow_stage': 'idle',
            'progress': 0.0
        }

    if 'orchestrator' not in st.session_state:
        config = load_config()
        # Initialize AutoGen orchestrator with status callback
        try:
            logger.info("Initializing AutoGen orchestrator...")
            # Create status callback that updates session state
            def status_callback(status_dict):
                """Callback to update agent status in session state."""
                if 'agent_status' not in st.session_state:
                    st.session_state.agent_status = {
                        'current_agent': None,
                        'agent_outputs': {},
                        'workflow_stage': 'idle',
                        'progress': 0.0
                    }

                # Update status
                st.session_state.agent_status['current_agent'] = status_dict.get('current_agent')
                st.session_state.agent_status['workflow_stage'] = status_dict.get('workflow_stage', 'processing')
                st.session_state.agent_status['progress'] = status_dict.get('progress', 0.0)

                # Add output if provided
                agent = status_dict.get('current_agent')
                output = status_dict.get('output')
                if output and agent:
                    if 'agent_outputs' not in st.session_state.agent_status:
                        st.session_state.agent_status['agent_outputs'] = {}
                    if agent not in st.session_state.agent_status['agent_outputs']:
                        st.session_state.agent_status['agent_outputs'][agent] = []
                    # Only add if different from last output (avoid duplicates)
                    if not st.session_state.agent_status['agent_outputs'][agent] or \
                       st.session_state.agent_status['agent_outputs'][agent][-1] != output:
                        st.session_state.agent_status['agent_outputs'][agent].append(output)

            st.session_state.orchestrator = AutoGenOrchestrator(config, status_callback=status_callback)
            logger.info("AutoGen orchestrator initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize orchestrator: {e}", exc_info=True)
            st.error(f"Failed to initialize orchestrator: {e}")
            st.session_state.orchestrator = None

    if 'show_traces' not in st.session_state:
        st.session_state.show_traces = False

    if 'show_safety_log' not in st.session_state:
        st.session_state.show_safety_log = False

    if 'show_logs' not in st.session_state:
        st.session_state.show_logs = False

    if 'safety_manager' not in st.session_state:
        config = load_config()
        safety_config = config.get("safety", {})
        if safety_config:
            try:
                # SafetyManager needs both safety config and system config (for topic)
                safety_config_with_system = {
                    **safety_config,
                    "system": config.get("system", {})
                }
                st.session_state.safety_manager = SafetyManager(safety_config_with_system)
            except Exception as e:
                st.warning(f"Failed to initialize safety manager: {e}")
                st.session_state.safety_manager = None
        else:
            st.session_state.safety_manager = None


def process_query_sync(query: str, status_callback=None) -> Dict[str, Any]:
    """
    Synchronous wrapper for processing queries (avoids event loop issues in Streamlit).

    Args:
        query: Research query to process

    Returns:
        Result dictionary with response, citations, and metadata
    """
    logger.info(f"Processing query: {query[:100]}...")
    orchestrator = st.session_state.orchestrator
    safety_manager = st.session_state.get("safety_manager")

    if orchestrator is None:
        logger.error("Orchestrator not initialized")
        return {
            "query": query,
            "error": "Orchestrator not initialized",
            "response": "Error: System not properly initialized. Please check your configuration.",
            "citations": [],
            "metadata": {}
        }

    # Check input safety
    input_safety_events = []
    if safety_manager:
        logger.debug("Checking input safety...")
        input_safety_result = safety_manager.check_input_safety(query)

        if not input_safety_result.get("safe", True):
            violations = input_safety_result.get("violations", [])
            message = input_safety_result.get("message", "Input blocked by safety policies.")

            input_safety_events.append({
                "type": "input",
                "safe": False,
                "violations": violations,
                "message": message,
                "action": "refused" if "refuse" in message.lower() else "sanitized"
            })

            # If refused (not safe and no sanitized query), return early
            if not input_safety_result.get("sanitized_query"):
                # Use the message from safety result, or default message
                refusal_message = input_safety_result.get("message", "I cannot process this request due to safety policies.")
                return {
                    "query": query,
                    "response": refusal_message,
                    "citations": [],
                    "metadata": {
                        "safety_events": input_safety_events,
                        "input_blocked": True,
                        "violations": violations
                    }
                }

            # If sanitized, use sanitized query
            if input_safety_result.get("sanitized_query"):
                query = input_safety_result.get("sanitized_query")

    try:
        # Process query through AutoGen orchestrator (sync method handles async internally)
        logger.info(f"Processing query: {query[:100]}...")
        result = orchestrator.process_query(query)
        logger.info("Query processing completed")

        # Check for errors
        if "error" in result:
            return result

        # Check output safety
        output_safety_events = []
        response = result.get("response", "")
        # Ensure response is a string (handle list case)
        if isinstance(response, list):
            response = "\n".join(str(item) for item in response) if response else ""
        elif not isinstance(response, str):
            response = str(response) if response else ""

        # ALWAYS update result["response"] with the converted string
        result["response"] = response

        if safety_manager and response:
            output_safety_result = safety_manager.check_output_safety(response)

            if not output_safety_result.get("safe", True):
                violations = output_safety_result.get("violations", [])
                sanitized_response = output_safety_result.get("response", response)

                output_safety_events.append({
                    "type": "output",
                    "safe": False,
                    "violations": violations,
                    "action": "sanitized" if sanitized_response != response else "refused",
                    "original_length": len(response),
                    "sanitized_length": len(sanitized_response)
                })

                # Update response with sanitized version
                result["response"] = sanitized_response

        # Extract citations from conversation history
        citations = extract_citations(result)

        # Extract agent traces for display
        agent_traces = extract_agent_traces(result)

        # Format metadata
        metadata = result.get("metadata", {})
        metadata["agent_traces"] = agent_traces
        metadata["citations"] = citations
        metadata["critique_score"] = calculate_quality_score(result)
        metadata["safety_events"] = input_safety_events + output_safety_events

        return {
            "query": query,
            "response": result.get("response", ""),
            "citations": citations,
            "metadata": metadata
        }

    except Exception as e:
        return {
            "query": query,
            "error": str(e),
            "response": f"An error occurred: {str(e)}",
            "citations": [],
            "metadata": {"error": True}
        }


async def process_query(query: str) -> Dict[str, Any]:
    """
    Process a query through the orchestrator with safety checks.

    Args:
        query: Research query to process

    Returns:
        Result dictionary with response, citations, and metadata
    """
    orchestrator = st.session_state.orchestrator
    safety_manager = st.session_state.get("safety_manager")

    if orchestrator is None:
        return {
            "query": query,
            "error": "Orchestrator not initialized",
            "response": "Error: System not properly initialized. Please check your configuration.",
            "citations": [],
            "metadata": {}
        }

    # Check input safety
    input_safety_events = []
    if safety_manager:
            input_safety_result = safety_manager.check_input_safety(query)

            if not input_safety_result.get("safe", True):
                violations = input_safety_result.get("violations", [])
                message = input_safety_result.get("message", "Input blocked by safety policies.")

                input_safety_events.append({
                    "type": "input",
                    "safe": False,
                    "violations": violations,
                    "message": message,
                    "action": "refused" if "refuse" in message.lower() else "sanitized"
                })

                # If refused (not safe and no sanitized query), return early
                if not input_safety_result.get("sanitized_query"):
                    # Use the message from safety result, or default message
                    refusal_message = input_safety_result.get("message", "I cannot process this request due to safety policies.")
                    return {
                        "query": query,
                        "response": refusal_message,
                        "citations": [],
                        "metadata": {
                            "safety_events": input_safety_events,
                            "input_blocked": True,
                            "violations": violations
                        }
                    }

                # If sanitized, use sanitized query
                if input_safety_result.get("sanitized_query"):
                    query = input_safety_result.get("sanitized_query")

    try:
        # Process query through AutoGen orchestrator
        result = orchestrator.process_query(query)

        # Check for errors
        if "error" in result:
            return result

        # Check output safety
        output_safety_events = []
        response = result.get("response", "")
        # Ensure response is a string (handle list case)
        if isinstance(response, list):
            response = "\n".join(str(item) for item in response) if response else ""
        elif not isinstance(response, str):
            response = str(response) if response else ""

        # ALWAYS update result["response"] with the converted string
        result["response"] = response

        if safety_manager and response:
            output_safety_result = safety_manager.check_output_safety(response)

            if not output_safety_result.get("safe", True):
                violations = output_safety_result.get("violations", [])
                sanitized_response = output_safety_result.get("response", response)

                output_safety_events.append({
                    "type": "output",
                    "safe": False,
                    "violations": violations,
                    "action": "sanitized" if sanitized_response != response else "refused",
                    "original_length": len(response),
                    "sanitized_length": len(sanitized_response)
                })

                # Update response with sanitized version
                result["response"] = sanitized_response

        # Extract citations from conversation history
        citations = extract_citations(result)

        # Extract agent traces for display
        agent_traces = extract_agent_traces(result)

        # Format metadata
        metadata = result.get("metadata", {})
        metadata["agent_traces"] = agent_traces
        metadata["citations"] = citations
        metadata["critique_score"] = calculate_quality_score(result)
        metadata["safety_events"] = input_safety_events + output_safety_events

        return {
            "query": query,
            "response": result.get("response", ""),
            "citations": citations,
            "metadata": metadata
        }

    except Exception as e:
        return {
            "query": query,
            "error": str(e),
            "response": f"An error occurred: {str(e)}",
            "citations": [],
            "metadata": {"error": True}
        }


def extract_citations(result: Dict[str, Any]) -> list:
    """Extract citations from research result."""
    citations = []
    import re

    # First, check the full response for citations (most important)
    response = result.get("response", "")

    # Ensure response is a string before using regex (defensive check)
    if isinstance(response, list):
        response = "\n".join(str(item) for item in response) if response else ""
    elif not isinstance(response, str):
        response = str(response) if response else ""

    if response:
        # Find URLs in response
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', response)
        for url in urls:
            if url not in citations:
                citations.append(url)

        # Find citation patterns like [Source: Title] or References section
        citation_patterns = re.findall(r'\[Source: ([^\]]+)\]', response)
        for citation in citation_patterns:
            if citation not in citations:
                citations.append(citation)

    # Also look through conversation history for citations
    for msg in result.get("conversation_history", []):
        content = msg.get("content", "")

        # Ensure content is a string before using regex (handle list case)
        if isinstance(content, list):
            content = "\n".join(str(item) for item in content) if content else ""
        elif not isinstance(content, str):
            content = str(content) if content else ""

        # Find URLs in content
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', content)

        # Find citation patterns like [Source: Title]
        citation_patterns = re.findall(r'\[Source: ([^\]]+)\]', content)

        for url in urls:
            if url not in citations:
                citations.append(url)

        for citation in citation_patterns:
            if citation not in citations:
                citations.append(citation)

    return citations[:10]  # Limit to top 10


def extract_agent_traces(result: Dict[str, Any]) -> Dict[str, list]:
    """Extract agent execution traces from conversation history."""
    traces = {}
    logger = logging.getLogger("streamlit_app")

    conversation_history = result.get("conversation_history", [])

    # Log how many messages we received
    logger.debug(f"Extracting agent traces from {len(conversation_history)} messages")

    if not conversation_history:
        # If no conversation history, try to extract from metadata
        metadata = result.get("metadata", {})
        logger.warning("No conversation_history found, falling back to metadata")
        if metadata.get("plan"):
            traces["Planner"] = [{"action_type": "plan", "details": metadata.get("plan", "")}]
        if metadata.get("research_findings"):
            traces["Researcher"] = [{"action_type": "research", "details": "\n".join(metadata.get("research_findings", []))}]
        if metadata.get("critique"):
            traces["Critic"] = [{"action_type": "critique", "details": metadata.get("critique", "")}]
        return traces

    # Group messages by agent to show complete conversation flow
    message_counts = {}  # Track counts per agent for debugging
    for msg in conversation_history:
        agent = msg.get("source", "Unknown")
        content = msg.get("content", "")

        # Ensure content is a string (handle list case)
        if isinstance(content, list):
            content = "\n".join(str(item) for item in content) if content else ""
        elif not isinstance(content, str):
            content = str(content) if content else ""

        # Track message counts
        message_counts[agent] = message_counts.get(agent, 0) + 1

        if agent not in traces:
            traces[agent] = []

        # Store full content (no truncation) for better visibility
        traces[agent].append({
            "action_type": "message",
            "details": content,  # Full content, not truncated (always a string)
            "timestamp": msg.get("timestamp", "")
        })

    # Log message counts per agent for debugging
    logger.info(f"Agent trace extraction complete. Messages per agent: {message_counts}")
    logger.debug(f"Total traces created: {sum(len(msgs) for msgs in traces.values())}")

    return traces


def calculate_quality_score(result: Dict[str, Any]) -> float:
    """Calculate a quality score based on various factors."""
    score = 5.0  # Base score

    metadata = result.get("metadata", {})

    # Add points for sources
    num_sources = metadata.get("num_sources", 0)
    score += min(num_sources * 0.5, 2.0)

    # Add points for critique
    if metadata.get("critique"):
        score += 1.0

    # Add points for conversation length (indicates thorough discussion)
    num_messages = metadata.get("num_messages", 0)
    score += min(num_messages * 0.1, 2.0)

    return min(score, 10.0)  # Cap at 10


def display_response(result: Dict[str, Any]):
    """
    Display query response.

    TODO: YOUR CODE HERE
    - Format response nicely
    - Show citations with links
    - Display sources
    - Show safety events if any
    """
    # Check for errors
    if "error" in result:
        st.error(f"Error: {result['error']}")
        return

    # Display response
    st.markdown("### Response")
    response = result.get("response", "")
    st.markdown(response)

    # Display citations
    citations = result.get("citations", [])
    if citations:
        with st.expander("📚 Citations", expanded=False):
            for i, citation in enumerate(citations, 1):
                st.markdown(f"**[{i}]** {citation}")

    # Display metadata
    metadata = result.get("metadata", {})

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Sources Used", metadata.get("num_sources", 0))
    with col2:
        score = metadata.get("critique_score", 0)
        st.metric("Quality Score", f"{score:.2f}")

    # Safety events - show prominently if input was blocked
    safety_events = metadata.get("safety_events", [])
    input_blocked = metadata.get("input_blocked", False)

    if safety_events:
        # If input was blocked, show safety events more prominently
        if input_blocked:
            st.markdown("### ⚠️ Safety Policy Violations")
            st.error("**Your query was refused due to the following safety violations:**")
        else:
            st.markdown("### ⚠️ Safety Events")

        with st.expander("View Safety Details", expanded=input_blocked):  # Auto-expand if input blocked
            for event in safety_events:
                event_type = event.get("type", "unknown")
                action = event.get("action", "unknown")
                violations = event.get("violations", [])

                # Display action taken
                if action == "refused":
                    st.error(f"🚫 **{event_type.upper()} REFUSED**")
                    st.caption(f"{len(violations)} violation(s) detected")
                    if event.get("message"):
                        st.info(f"**Reason:** {event.get('message')}")
                elif action == "sanitized":
                    st.warning(f"🧹 **{event_type.upper()} SANITIZED**")
                    st.caption(f"{len(violations)} violation(s) detected")
                    if event.get("original_length") and event.get("sanitized_length"):
                        reduction = event.get("original_length") - event.get("sanitized_length")
                        if reduction > 0:
                            st.caption(f"Content reduced by {reduction} characters")

                # Display violations
                if violations:
                    for violation in violations:
                        severity = violation.get("severity", "unknown")
                        reason = violation.get("reason", "Unknown violation")
                        validator = violation.get("validator", "unknown")

                        severity_color = {
                            "high": "🔴",
                            "medium": "🟡",
                            "low": "🟢"
                        }.get(severity, "⚪")

                        st.text(f"  {severity_color} [{validator}] {reason}")

    # Agent traces - only show if checkbox is enabled
    if st.session_state.get("show_traces", False):
        agent_traces = metadata.get("agent_traces", {})
        if agent_traces:
            display_agent_traces(agent_traces)
        else:
            st.info("ℹ️ No agent traces available. Agent traces are extracted from the conversation history after processing completes.")


def display_agent_traces(traces: Dict[str, Any]):
    """
    Display agent execution traces with workflow visualization.
    """
    with st.expander("🔍 Agent Execution Traces", expanded=True):
        # Show workflow order
        agent_order = ["Planner", "Researcher", "Writer", "Critic"]

        # Create tabs for each agent
        tabs = st.tabs([agent for agent in agent_order if agent in traces])

        for idx, agent_name in enumerate(agent_order):
            if agent_name in traces:
                with tabs[agent_order.index(agent_name)]:
                    actions = traces[agent_name]
                    num_messages = len(actions)

                    st.markdown(f"### 🤖 {agent_name}")
                    st.caption(f"**{num_messages} message(s)** from this agent")

                    for i, action in enumerate(actions, 1):
                        action_type = action.get("action_type", "unknown")
                        details = action.get("details", "")
                        timestamp = action.get("timestamp", "")

                        with st.container():
                            step_label = f"**Step {i}:** {action_type}"
                            if timestamp:
                                step_label += f" ({timestamp})"
                            st.markdown(step_label)

                            if details:
                                # Show full content in a scrollable text area
                                # Adjust height based on content length (min 100, max 400)
                                content_height = min(max(100, len(details) // 10), 400)
                                st.text_area(
                                    f"Message {i}",
                                    value=details,
                                    height=content_height,
                                    disabled=True,
                                    key=f"{agent_name}_step_{i}"
                                )
                            st.divider()

        # Show agents involved
        agents_involved = list(traces.keys())
        st.caption(f"**Agents involved:** {', '.join(agents_involved)}")


def display_sidebar():
    """Display sidebar with settings and statistics."""
    with st.sidebar:
        st.title("⚙️ Settings")

        # Show traces toggle
        st.session_state.show_traces = st.checkbox(
            "Show Agent Traces",
            value=st.session_state.show_traces
        )

        # Show safety log toggle
        st.session_state.show_safety_log = st.checkbox(
            "Show Safety Log",
            value=st.session_state.show_safety_log
        )

        # Show logs toggle
        st.session_state.show_logs = st.checkbox(
            "Show Debug Logs",
            value=st.session_state.show_logs
        )

        st.divider()

        st.title("📊 Statistics")

        # Get actual statistics
        st.metric("Total Queries", len(st.session_state.history))

        # Get safety statistics
        safety_manager = st.session_state.get("safety_manager")
        if safety_manager:
            safety_stats = safety_manager.get_safety_stats()
            st.metric("Safety Events", safety_stats.get("total_events", 0))
            st.metric("Violations", safety_stats.get("violations", 0))
        else:
            st.metric("Safety Events", 0)

        st.divider()

        # Clear history button
        if st.button("Clear History"):
            st.session_state.history = []
            st.rerun()

        # About section
        st.divider()
        st.markdown("### About")
        config = load_config()
        system_name = config.get("system", {}).get("name", "Research Assistant")
        topic = config.get("system", {}).get("topic", "General")
        st.markdown(f"**System:** {system_name}")
        st.markdown(f"**Topic:** {topic}")


def display_history():
    """Display query history."""
    if not st.session_state.history:
        return

    with st.expander("📜 Query History", expanded=False):
        for i, item in enumerate(reversed(st.session_state.history), 1):
            timestamp = item.get("timestamp", "")
            query = item.get("query", "")
            st.markdown(f"**{i}.** [{timestamp}] {query}")


def main():
    """Main Streamlit app."""
    st.set_page_config(
        page_title="Multi-Agent Research Assistant",
        page_icon="🤖",
        layout="wide"
    )

    initialize_session_state()

    # Header
    st.title("🤖 Multi-Agent Research Assistant")
    st.markdown("Ask me anything about Ethical AI in Education!")

    # Sidebar
    display_sidebar()

    # Main area
    col1, col2 = st.columns([2, 1])

    with col1:
        # Initialize query in session state if not present
        if 'query_text' not in st.session_state:
            st.session_state.query_text = ""

        # Query input - don't use key so we can control the value directly
        query = st.text_area(
            "Enter your research query:",
            value=st.session_state.query_text,
            height=100,
            placeholder="e.g., What are the latest developments in Ethical AI in Education?"
        )

        # Update session state when user types
        if query != st.session_state.query_text:
            st.session_state.query_text = query

        # Submit button
        if st.button("🔍 Search", type="primary", use_container_width=True):
            if query.strip():
                # Clear previous agent status
                clear_agent_status()

                # Create status display area
                status_placeholder = st.empty()
                agent_outputs_placeholder = st.empty()
                progress_placeholder = st.empty()

                try:
                    # Initial status
                    with status_placeholder.container():
                        st.info("🔍 Checking input safety...")

                    # Process query - use orchestrator's sync method which handles async internally
                    # This avoids event loop conflicts with Streamlit
                    logger.info(f"Starting query processing: {query[:50]}...")

                    # Display agent activity in real-time
                    with status_placeholder.container():
                        st.info("🤖 Processing query through multi-agent system...")

                    # Process query (status updates happen via callback)
                    result = process_query_sync(query)
                    logger.info("Query processing completed")

                    # Display results and agent activity
                    if result and 'metadata' in result:
                        metadata = result.get('metadata', {})
                        agent_traces = metadata.get('agent_traces', {})

                        # Show completion status
                        with status_placeholder.container():
                            st.success("✅ Processing complete!")

                        # Display agent outputs from conversation history
                        if agent_traces:
                            with agent_outputs_placeholder.container():
                                st.markdown("### 🤖 Agent Activity")

                                # Agent order and info
                                agent_info = {
                                    'Planner': {'icon': '📋', 'color': 'blue'},
                                    'Researcher': {'icon': '🔍', 'color': 'green'},
                                    'Writer': {'icon': '✍️', 'color': 'purple'},
                                    'Critic': {'icon': '🔎', 'color': 'orange'}
                                }

                                # Display outputs in workflow order
                                for agent_name in ['Planner', 'Researcher', 'Writer', 'Critic']:
                                    if agent_name in agent_traces:
                                        traces = agent_traces[agent_name]
                                        info = agent_info.get(agent_name, {'icon': '🤖', 'color': 'gray'})

                                        # Show all outputs from this agent
                                        for i, trace in enumerate(traces):
                                            # Get output and ensure it's a string
                                            if isinstance(trace, dict):
                                                output = trace.get('details', '')
                                            else:
                                                output = str(trace)

                                            # Convert to string if it's a list or other type
                                            if isinstance(output, list):
                                                output = "\n".join(str(item) for item in output) if output else ""
                                            elif not isinstance(output, str):
                                                output = str(output) if output else ""

                                            if output and output.strip():
                                                # Truncate for initial display
                                                preview = output[:300] + "..." if len(output) > 300 else output
                                                is_last = (i == len(traces) - 1)

                                                with st.expander(
                                                    f"{info['icon']} **{agent_name}** - Output {i+1}" + (" (Latest)" if is_last else ""),
                                                    expanded=is_last
                                                ):
                                                    st.markdown(output)
                                                    if len(output) > 300:
                                                        st.caption(f"*Full output: {len(output)} characters*")

                    # Show progress completion
                    with progress_placeholder.container():
                        st.progress(1.0)
                        st.caption("✅ All agents completed")

                except Exception as e:
                    # Clear status
                    status_placeholder.empty()
                    agent_outputs_placeholder.empty()
                    progress_placeholder.empty()

                    # Check for context length error and provide helpful message
                    error_str = str(e)
                    if "context_length_exceeded" in error_str or "Please reduce the length" in error_str or "context limit" in error_str.lower():
                        st.error("❌ **Context Length Exceeded**")
                        st.warning(
                            "The conversation history has become too long for the model to process. "
                            "This can happen when agents exchange many messages or when research findings are very detailed."
                        )
                        st.info(
                            "**Suggestions:**\n"
                            "- Try a simpler or more focused query\n"
                            "- The system will automatically reduce max_turns in future queries\n"
                            "- Consider breaking complex queries into smaller parts"
                        )
                    else:
                        # Show generic error
                        st.error(f"❌ Error processing query: {str(e)}")
                        st.exception(e)

                    # Return early to prevent further processing
                    return

                # Check for errors first
                if "error" in result:
                    st.error(f"❌ Error: {result.get('error', 'Unknown error')}")
                    if result.get("response"):
                        st.info(result.get("response"))
                    return

                # Check if input was blocked by safety policies
                metadata = result.get("metadata", {})
                if metadata.get("input_blocked"):
                    st.error("🚫 **Input Blocked by Safety Policies**")
                    st.info("Your query was refused due to safety policy violations. See details below.")
                    # display_response will show the detailed safety events
                    st.divider()
                    display_response(result)
                    return

                # Check if we got a valid result
                response = result.get("response", "")
                if not response or not response.strip():
                    st.warning("⚠️ No response received. The query may have timed out or the agents may not have generated a response.")
                    # Still show what we got for debugging
                    if result:
                        with st.expander("Debug: Raw Result", expanded=False):
                            st.json(result)
                    return

                # Add to history
                st.session_state.history.append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "query": query,
                    "response": response,
                    "citations": result.get("citations", []),
                    "metadata": result.get("metadata", {})
                })

                # Display result
                st.divider()
                display_response(result)
            else:
                st.warning("Please enter a query.")

        # History
        display_history()

    with col2:
        st.markdown("### 💡 Example Queries")
        examples = [
            "What are ethical considerations in AI for education?",
            "How can bias in AI educational systems be mitigated?",
            "What are the privacy concerns with AI in educational settings?",
            "How does AI impact teacher and student autonomy in education?",
        ]

        for example in examples:
            if st.button(example, use_container_width=True, key=f"example_{hash(example)}"):
                # Directly set the query text and trigger rerun
                st.session_state.query_text = example
                st.rerun()

        st.divider()

        st.markdown("### ℹ️ How It Works")
        st.markdown("""
        1. **Planner** breaks down your query
        2. **Researcher** gathers evidence
        3. **Writer** synthesizes findings
        4. **Critic** verifies quality
        5. **Safety** checks ensure appropriate content
        """)

    # Debug logs (if enabled)
    if st.session_state.show_logs:
        st.divider()
        st.markdown("### 📋 Debug Logs")

        log_file = Path("logs/streamlit.log")
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_lines = f.readlines()

                # Show last 100 lines
                recent_logs = log_lines[-100:] if len(log_lines) > 100 else log_lines

                # Create a text area with the logs
                log_content = ''.join(recent_logs)
                st.text_area(
                    "Recent Logs (last 100 lines)",
                    value=log_content,
                    height=400,
                    key="debug_logs_display"
                )

                # Download button
                st.download_button(
                    label="📥 Download Full Log",
                    data=''.join(log_lines),
                    file_name=f"streamlit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                    mime="text/plain"
                )
            except Exception as e:
                st.error(f"Error reading log file: {e}")
        else:
            st.info("No log file found. Logs will appear here once the system starts logging.")

    # Safety log (if enabled)
    if st.session_state.show_safety_log:
        st.divider()
        st.markdown("### 🛡️ Safety Event Log")

        safety_manager = st.session_state.get("safety_manager")
        if safety_manager:
            safety_events = safety_manager.get_safety_events()

            if safety_events:
                # Display events in reverse chronological order
                for event in reversed(safety_events[-20:]):  # Show last 20 events
                    with st.container():
                        timestamp = event.get("timestamp", "Unknown time")
                        event_type = event.get("type", "unknown")
                        is_safe = event.get("safe", True)
                        violations = event.get("violations", [])

                        # Color code by safety status
                        if is_safe:
                            st.success(f"✅ [{timestamp}] {event_type.upper()} - Safe")
                        else:
                            st.error(f"❌ [{timestamp}] {event_type.upper()} - {len(violations)} violation(s)")

                            # Show violations
                            for violation in violations:
                                st.text(f"  • {violation.get('reason', 'Unknown')}")

                        st.divider()
            else:
                st.info("No safety events recorded yet.")
        else:
            st.warning("Safety manager not initialized.")


if __name__ == "__main__":
    main()
