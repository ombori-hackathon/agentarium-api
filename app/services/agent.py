"""
Agent state management service for Agentarium.

This service tracks agent state, processes hook events, and generates agent events
for WebSocket broadcast to clients.
"""

import time
from typing import Dict, Optional
from pathlib import Path

from app.schemas.events import HookEvent, AgentEvent
from app.schemas.filesystem import Position, FilesystemLayout


class AgentState:
    """
    Represents the state of a single agent in the system.

    Agents are identified by session_id and track their current position,
    action, and context in the 3D scene.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.position = Position(x=0.0, y=0.0, z=0.0)
        self.current_action: Optional[str] = None
        self.target_path: Optional[str] = None
        self.thought: Optional[str] = None


def extract_file_path(tool_name: str, tool_input: Dict) -> Optional[str]:
    """
    Extract file path from tool input if present.

    Args:
        tool_name: Name of the tool being used
        tool_input: Tool input parameters

    Returns:
        File path if found, None otherwise
    """
    if not tool_input:
        return None

    return tool_input.get("file_path")


def generate_thought(tool_name: str, tool_input: Dict) -> str:
    """
    Generate thought text from tool name and input.

    Args:
        tool_name: Name of the tool being used
        tool_input: Tool input parameters

    Returns:
        Human-readable thought text
    """
    if not tool_input:
        return f"Using {tool_name}"

    # Extract relevant parameters based on tool type
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if file_path:
            file_name = Path(file_path).name
            return f"Reading {file_name}"

    elif tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        if file_path:
            file_name = Path(file_path).name
            return f"Writing {file_name}"

    elif tool_name == "Edit":
        file_path = tool_input.get("file_path", "")
        if file_path:
            file_name = Path(file_path).name
            return f"Editing {file_name}"

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if command:
            return f"Running: {command}"

    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        if pattern:
            return f"Searching for: {pattern}"

    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        if pattern:
            return f"Finding: {pattern}"

    # Default fallback
    return f"Using {tool_name}"


class AgentService:
    """
    Service for managing agent state and processing hook events.

    This service:
    - Tracks active agents by session_id
    - Maintains terrain layout for position lookups
    - Processes hook events and generates agent events
    - Maps file paths to 3D coordinates
    """

    def __init__(self):
        self.agents: Dict[str, AgentState] = {}
        self.terrain_layout: Optional[FilesystemLayout] = None

    def set_terrain_layout(self, layout: FilesystemLayout):
        """
        Set the terrain layout for file position lookups.

        Args:
            layout: Filesystem layout with positioned files and folders
        """
        self.terrain_layout = layout

    def get_file_position(self, file_path: str) -> Optional[Position]:
        """
        Look up 3D position for a file path.

        Args:
            file_path: Absolute path to the file

        Returns:
            Position if file is found in terrain, None otherwise
        """
        if not self.terrain_layout:
            return None

        # Search for file in terrain layout
        for file in self.terrain_layout.files:
            if file.path == file_path:
                return file.position

        return None

    def get_or_create_agent(self, session_id: str) -> AgentState:
        """
        Get existing agent state or create new one.

        Args:
            session_id: Unique session identifier

        Returns:
            AgentState for this session
        """
        if session_id not in self.agents:
            self.agents[session_id] = AgentState(agent_id=session_id)

        return self.agents[session_id]

    def process_hook_event(self, event: HookEvent) -> Optional[AgentEvent]:
        """
        Process a hook event and generate an agent event.

        This method:
        1. Gets or creates agent state for the session
        2. Extracts file path from tool input (if present)
        3. Looks up 3D coordinates for the file
        4. Generates thought text
        5. Updates agent state
        6. Creates and returns AgentEvent for broadcast

        Args:
            event: Hook event from Claude

        Returns:
            AgentEvent for WebSocket broadcast, or None if event should be ignored
        """
        # Get or create agent state
        agent = self.get_or_create_agent(event.session_id)

        # Extract file path if present
        file_path = None
        if event.tool_input:
            file_path = extract_file_path(event.tool_name or "", event.tool_input)

        # Look up position for file path
        target_position = None
        if file_path:
            target_position = self.get_file_position(file_path)

        # Generate thought text
        thought = None
        if event.tool_name and event.tool_input:
            thought = generate_thought(event.tool_name, event.tool_input)

        # Determine event type
        if target_position:
            event_type = "move"
            # Update agent position to target
            agent.position = target_position
        else:
            # No movement - just thinking
            event_type = "think"

        # Update agent state
        agent.current_action = event_type
        agent.target_path = file_path
        agent.thought = thought

        # Create agent event
        agent_event = AgentEvent(
            agent_id=event.session_id,
            event_type=event_type,
            target_path=file_path,
            target_position=target_position,
            thought=thought,
            tool_name=event.tool_name,
            timestamp=int(time.time() * 1000)  # milliseconds
        )

        return agent_event


# Global agent service instance
agent_service = AgentService()
