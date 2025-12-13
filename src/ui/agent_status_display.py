"""
Agent Status Display Component
Displays real-time agent activity and outputs in Streamlit.
"""
import streamlit as st
from typing import Dict, Any, Optional
from datetime import datetime


def display_agent_status(status: Dict[str, Any], agent_outputs_container):
    """
    Display current agent status and outputs.

    Args:
        status: Status dictionary with current_agent, workflow_stage, progress
        agent_outputs_container: Streamlit container for agent outputs
    """
    current_agent = status.get('current_agent')
    workflow_stage = status.get('workflow_stage', 'idle')
    progress = status.get('progress', 0.0)
    agent_outputs = status.get('agent_outputs', {})

    # Agent icons and colors
    agent_info = {
        'Planner': {'icon': '📋', 'color': 'blue', 'description': 'Creating research plan'},
        'Researcher': {'icon': '🔍', 'color': 'green', 'description': 'Gathering evidence'},
        'Writer': {'icon': '✍️', 'color': 'purple', 'description': 'Synthesizing response'},
        'Critic': {'icon': '🔎', 'color': 'orange', 'description': 'Evaluating quality'}
    }

    # Display current agent status
    if current_agent and current_agent in agent_info:
        info = agent_info[current_agent]
        with st.status(f"{info['icon']} **{current_agent}** - {info['description']}", state="running"):
            st.write(f"**Stage:** {workflow_stage}")
            if progress > 0:
                st.progress(progress)

    # Display agent outputs
    with agent_outputs_container:
        if agent_outputs:
            st.markdown("### 🤖 Agent Activity")

            # Display outputs in workflow order
            agent_order = ['Planner', 'Researcher', 'Writer', 'Critic']
            for agent in agent_order:
                if agent in agent_outputs:
                    output_data = agent_outputs[agent]
                    if isinstance(output_data, list):
                        outputs = output_data
                    else:
                        outputs = [output_data]

                    for i, output in enumerate(outputs):
                        if output and output.strip():
                            with st.expander(f"{agent_info.get(agent, {}).get('icon', '🤖')} {agent} Output {i+1}", expanded=(i == len(outputs)-1)):
                                # Truncate very long outputs for display
                                display_output = output[:2000] + "..." if len(output) > 2000 else output
                                st.markdown(display_output)
                                if len(output) > 2000:
                                    st.caption(f"*Output truncated. Full length: {len(output)} characters*")


def update_agent_status(agent: Optional[str], stage: str, progress: float = 0.0, output: Optional[str] = None):
    """
    Update agent status in session state.

    Args:
        agent: Name of current agent (None if idle)
        stage: Current workflow stage
        progress: Progress value (0.0 to 1.0)
        output: Agent output to add
    """
    if 'agent_status' not in st.session_state:
        st.session_state.agent_status = {
            'current_agent': None,
            'agent_outputs': {},
            'workflow_stage': 'idle',
            'progress': 0.0
        }

    st.session_state.agent_status['current_agent'] = agent
    st.session_state.agent_status['workflow_stage'] = stage
    st.session_state.agent_status['progress'] = progress

    if output and agent:
        if agent not in st.session_state.agent_status['agent_outputs']:
            st.session_state.agent_status['agent_outputs'][agent] = []
        st.session_state.agent_status['agent_outputs'][agent].append(output)


def clear_agent_status():
    """Clear agent status from session state."""
    if 'agent_status' in st.session_state:
        st.session_state.agent_status = {
            'current_agent': None,
            'agent_outputs': {},
            'workflow_stage': 'idle',
            'progress': 0.0
        }
