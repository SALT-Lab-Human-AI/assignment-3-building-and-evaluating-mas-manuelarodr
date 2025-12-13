"""
Example: Using AutoGen for Multi-Agent Research

This script demonstrates how to use the AutoGen-based multi-agent research system.

Usage:
    python example_autogen.py
"""

import os
import yaml
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from src.autogen_orchestrator import AutoGenOrchestrator


def setup_logging():
    """Configure logging for the application."""
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    logging.basicConfig(
        level=logging.DEBUG,  # Changed to DEBUG for detailed tool call logging
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/example.log")
        ]
    )

    # Set specific loggers to appropriate levels
    logging.getLogger("autogen").setLevel(logging.INFO)  # Reduce AutoGen internal noise
    logging.getLogger("httpx").setLevel(logging.WARNING)  # Reduce HTTP noise


def load_config():
    """Load configuration from config.yaml."""
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def print_separator(title: str = ""):
    """Print a visual separator."""
    if title:
        print(f"\n{'=' * 70}")
        print(f"{title:^70}")
        print(f"{'=' * 70}\n")
    else:
        print(f"{'=' * 70}\n")


def save_conversation_output(result: dict, query: str, output_dir: str = "outputs"):
    """
    Save the full conversation output to both text and JSON files.

    Args:
        result: The result dictionary from orchestrator.process_query()
        query: The original query
        output_dir: Directory to save the output files
    """
    # Create outputs directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Generate timestamp for filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamp_readable = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Save as JSON
    json_filename = f"conversation_{timestamp}.json"
    json_filepath = os.path.join(output_dir, json_filename)

    # Prepare JSON data - convert conversation history to serializable format
    def make_serializable(obj, max_string_length=50000):
        """Recursively convert objects to JSON-serializable format."""
        if isinstance(obj, dict):
            return {k: make_serializable(v, max_string_length) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serializable(item, max_string_length) for item in obj]
        elif isinstance(obj, str):
            # Truncate very long strings to prevent JSON serialization issues
            if len(obj) > max_string_length:
                return obj[:max_string_length] + f"\n... [truncated, original length: {len(obj)} characters]"
            return obj
        elif isinstance(obj, (int, float, bool, type(None))):
            return obj
        else:
            # Convert non-serializable objects to string representation
            return str(obj)

    # Convert all data to serializable format, including metadata
    conversation_history = result.get("conversation_history", [])
    metadata = result.get("metadata", {})

    # Make everything serializable
    serializable_history = make_serializable(conversation_history)
    serializable_metadata = make_serializable(metadata)
    serializable_response = make_serializable(result.get("response", ""))

    json_data = {
        "timestamp": timestamp_readable,
        "query": query,
        "metadata": serializable_metadata,
        "response": serializable_response,
        "error": result.get("error"),
        "conversation_history": serializable_history
    }

    # Write JSON file with error handling
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        # If serialization fails, try with more aggressive conversion
        print(f"Warning: JSON serialization issue: {e}")
        print("Attempting fallback serialization...")

        # Fallback: convert everything to strings if needed
        def force_serialize(obj):
            if isinstance(obj, dict):
                return {str(k): force_serialize(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [force_serialize(item) for item in obj]
            elif isinstance(obj, (str, int, float, bool, type(None))):
                return obj
            else:
                return str(obj)

        json_data_fallback = force_serialize(json_data)
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(json_data_fallback, f, indent=2, ensure_ascii=False)

    # Save as text
    txt_filename = f"conversation_{timestamp}.txt"
    txt_filepath = os.path.join(output_dir, txt_filename)

    # Format the output
    output_lines = []
    output_lines.append("=" * 80)
    output_lines.append("CONVERSATION OUTPUT")
    output_lines.append("=" * 80)
    output_lines.append(f"Timestamp: {timestamp_readable}")
    output_lines.append(f"Query: {query}")
    output_lines.append("")

    # Add metadata
    if "metadata" in result:
        output_lines.append("METADATA")
        output_lines.append("-" * 80)
        metadata = result["metadata"]
        output_lines.append(f"Messages exchanged: {metadata.get('num_messages', 'N/A')}")
        output_lines.append(f"Sources gathered: {metadata.get('num_sources', 'N/A')}")
        output_lines.append(f"Agents involved: {', '.join(metadata.get('agents_involved', []))}")
        output_lines.append("")

    # Add final response
    output_lines.append("FINAL RESPONSE")
    output_lines.append("-" * 80)
    if "error" in result:
        output_lines.append(f"ERROR: {result['error']}")
    else:
        output_lines.append(result.get('response', 'No response generated'))
    output_lines.append("")

    # Note: Full conversation history is available in the JSON file
    # We only include query, response, and metadata in the text/markdown file

    # Write text file
    with open(txt_filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    print(f"\n✓ Full conversation saved to:")
    print(f"  - Text: {txt_filepath}")
    print(f"  - JSON: {json_filepath}")
    return txt_filepath, json_filepath


def run_single_query():
    """
    Example 1: Run a single research query.

    This is the simplest way to use the system.
    """
    print_separator("Example 1: Single Research Query")

    # Load environment and config
    load_dotenv()
    config = load_config()

    # Create orchestrator
    orchestrator = AutoGenOrchestrator(config)

    # Define your research query
    query = "What is the latest research on ethical AI in education?"

    print(f"Query: {query}\n")
    print("Processing... (this may take 1-2 minutes)\n")

    # Process the query (using max_turns from config, or override with parameter)
    result = orchestrator.process_query(query, max_turns=None)  # None uses config value

    # Display results
    if "error" in result:
        print(f"Error: {result['error']}")
        # Still save the error output
        save_conversation_output(result, query)
        return

    print_separator("Final Response")
    print(result['response'])

    print_separator("Metadata")
    print(f"Messages exchanged: {result['metadata']['num_messages']}")
    print(f"Sources gathered: {result['metadata']['num_sources']}")
    print(f"Agents involved: {', '.join(result['metadata']['agents_involved'])}")

    # Save full conversation output
    save_conversation_output(result, query)


def run_multiple_queries():
    """
    Example 2: Process multiple queries in sequence.

    Shows how to reuse the orchestrator for multiple queries.
    """
    print_separator("Example 2: Multiple Research Queries")

    load_dotenv()
    config = load_config()

    # Create orchestrator once
    orchestrator = AutoGenOrchestrator(config)

    # List of queries to process
    queries = [
        "What level of transparency is required for an AI-driven feedback/grading system to be considered ethical and fair to students?",
        "What are the ethical considerations for using AI in education?",
        "What are key factors to keep in mind when designing AI-driven personalized learning systems?",
    ]

    results = []

    for i, query in enumerate(queries, 1):
        print(f"\n[Query {i}/{len(queries)}] {query}")
        print("-" * 70)

        result = orchestrator.process_query(query, max_turns=None)  # Uses config value (8)
        results.append(result)

        # Print brief summary
        if "error" not in result:
            response_preview = result['response'][:200] + "..."
            print(f"Response preview: {response_preview}\n")

    print_separator("Summary")
    print(f"Processed {len(queries)} queries successfully")

    return results


def inspect_conversation():
    """
    Example 3: Inspect the conversation history.

    Shows how to access and examine the agent-to-agent conversation.
    """
    print_separator("Example 3: Inspecting Conversation History")

    load_dotenv()
    config = load_config()

    orchestrator = AutoGenOrchestrator(config)

    query = "What is the difference between usability and user experience?"

    print(f"Query: {query}\n")
    result = orchestrator.process_query(query, max_turns=None)  # Uses config value

    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print_separator("Conversation Flow")

    # Display each message in the conversation
    for i, msg in enumerate(result['conversation_history'], 1):
        agent = msg.get('source', msg.get('name', 'Unknown'))
        content = msg.get('content', '')

        # Truncate long messages for readability
        if len(content) > 300:
            content = content[:300] + "...[truncated]"

        print(f"[{i}] {agent}:")
        print(f"    {content}\n")


def view_workflow():
    """
    Example 4: Visualize the workflow.

    Shows the structure of the multi-agent system.
    """
    print_separator("Example 4: Workflow Visualization")

    load_dotenv()
    config = load_config()

    orchestrator = AutoGenOrchestrator(config)

    # Print workflow diagram
    print(orchestrator.visualize_workflow())

    # Print agent descriptions
    print_separator("Agent Descriptions")
    for agent_name, description in orchestrator.get_agent_descriptions().items():
        print(f"• {agent_name}: {description}")


def check_setup():
    """
    Check if the system is properly configured.

    Verifies API keys and dependencies.
    """
    print_separator("Setup Check")

    load_dotenv()

    checks = {
        "Environment file (.env)": os.path.exists(".env"),
        "Config file (config.yaml)": os.path.exists("config.yaml"),
        "Logs directory": os.path.exists("logs"),
        "GROQ_API_KEY": bool(os.getenv("GROQ_API_KEY")),
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "TAVILY_API_KEY": bool(os.getenv("TAVILY_API_KEY")),
    }

    print("Configuration Status:\n")

    all_good = True
    for check, status in checks.items():
        status_str = "✓ OK" if status else "✗ MISSING"
        print(f"  {check:.<40} {status_str}")

        if not status and "API_KEY" in check:
            all_good = False

    print("\nRequired API Keys:")
    print("  - At least one LLM key (GROQ_API_KEY or OPENAI_API_KEY)")
    print("  - At least one search key (TAVILY_API_KEY recommended)")

    if not checks["GROQ_API_KEY"] and not checks["OPENAI_API_KEY"]:
        print("\n⚠ Warning: No LLM API key found. Please add one to .env")

    if not checks["TAVILY_API_KEY"]:
        print("\n⚠ Warning: No search API key found. Research capabilities will be limited.")

    print()


def main():
    """
    Main function - run all examples or choose one.
    """
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    setup_logging()

    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║           AutoGen Multi-Agent Research System Examples               ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
    """)

    # First, check setup
    check_setup()

    # Menu
    print("\nChoose an example to run:\n")
    print("  1. Single research query (simple)")
    print("  2. Multiple queries in sequence")
    print("  3. Inspect conversation history")
    print("  4. View workflow diagram")
    print("  5. Check setup")
    print("  0. Exit\n")

    try:
        choice = input("Enter your choice (0-5): ").strip()

        if choice == "1":
            run_single_query()
        elif choice == "2":
            run_multiple_queries()
        elif choice == "3":
            inspect_conversation()
        elif choice == "4":
            view_workflow()
        elif choice == "5":
            check_setup()
        elif choice == "0":
            print("Goodbye!")
        else:
            print("Invalid choice. Please run again and select 0-5.")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Goodbye!")
    except Exception as e:
        print(f"\nError: {e}")
        logging.exception("Error in main")


if __name__ == "__main__":
    main()
