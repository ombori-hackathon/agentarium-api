"""
Agent state management service for Agentarium.

This service tracks agent state, processes hook events, and generates agent events
for WebSocket broadcast to clients.
"""

import time
import logging
from typing import Dict, Optional, Tuple
from pathlib import Path

from app.schemas.events import HookEvent, AgentEvent, AgentSpawn, AgentDespawn
from app.schemas.filesystem import Position, FilesystemLayout

logger = logging.getLogger(__name__)


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

    # Read, Write, Edit tools use file_path
    if tool_name in ("Read", "Write", "Edit"):
        return tool_input.get("file_path")

    # Grep and Glob tools use path
    if tool_name in ("Grep", "Glob"):
        return tool_input.get("path")

    # Bash tool - best effort parsing (skip for MVP)
    # We could parse commands like "cat file.txt" but this is complex
    # For now, return None and agent will stay in place

    return None


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

    def remove_agent(self, session_id: str) -> bool:
        """
        Remove agent state for a session.

        Args:
            session_id: Session to remove

        Returns:
            True if agent was removed, False if not found
        """
        if session_id in self.agents:
            del self.agents[session_id]
            return True
        return False

    def process_hook_event(self, event: HookEvent) -> Tuple[str, Optional[dict]]:
        """
        Process a hook event and generate WebSocket message.

        This method handles the full session lifecycle:
        - SessionStart: spawn agent at origin
        - PreToolUse: move agent to file location
        - PostToolUse: mark tool complete
        - SessionEnd/Stop: despawn agent

        Args:
            event: Hook event from Claude

        Returns:
            Tuple of (message_type, message_data) for WebSocket broadcast.
            Returns (None, None) if event should be ignored.
        """
        start_time = time.time()
        logger.info(f"Event received: {event.session_id} - {event.hook_event_name} at {start_time}")

        # Handle session lifecycle events
        if event.hook_event_name == "SessionStart":
            return self._handle_session_start(event, start_time)
        elif event.hook_event_name in ("SessionEnd", "Stop"):
            return self._handle_session_end(event, start_time)
        elif event.hook_event_name == "PreToolUse":
            return self._handle_pre_tool_use(event, start_time)
        elif event.hook_event_name == "PostToolUse":
            return self._handle_post_tool_use(event, start_time)
        else:
            logger.debug(f"Ignoring event: {event.hook_event_name}")
            return None, None

    def _handle_session_start(self, event: HookEvent, start_time: float) -> Tuple[str, dict]:
        """
        Handle SessionStart event - spawn agent at origin.

        Args:
            event: Hook event
            start_time: Timestamp when event was received

        Returns:
            Tuple of (message_type, message_data)
        """
        # Create new agent at origin
        agent = self.get_or_create_agent(event.session_id)
        agent.position = Position(x=0.0, y=0.0, z=0.0)

        spawn_event = AgentSpawn(
            agent_id=event.session_id,
            position=agent.position,
            color="#e07850"
        )

        process_time = (time.time() - start_time) * 1000  # ms
        logger.info(f"SessionStart processed in {process_time:.2f}ms for {event.session_id}")

        return "agent_spawn", spawn_event.model_dump()

    def _handle_session_end(self, event: HookEvent, start_time: float) -> Tuple[str, dict]:
        """
        Handle SessionEnd/Stop event - despawn agent.

        Args:
            event: Hook event
            start_time: Timestamp when event was received

        Returns:
            Tuple of (message_type, message_data)
        """
        # Remove agent state
        removed = self.remove_agent(event.session_id)

        if not removed:
            logger.warning(f"Attempted to remove non-existent agent: {event.session_id}")

        despawn_event = AgentDespawn(
            agent_id=event.session_id
        )

        process_time = (time.time() - start_time) * 1000  # ms
        logger.info(f"SessionEnd processed in {process_time:.2f}ms for {event.session_id}")

        return "agent_despawn", despawn_event.model_dump()

    def _handle_pre_tool_use(self, event: HookEvent, start_time: float) -> Tuple[str, Optional[dict]]:
        """
        Handle PreToolUse event - move agent to file location.

        Args:
            event: Hook event
            start_time: Timestamp when event was received

        Returns:
            Tuple of (message_type, message_data)
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
            if target_position:
                logger.debug(f"Found position for {file_path}: {target_position}")
            else:
                logger.debug(f"Unknown file path: {file_path} (agent stays in place)")

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
            # No movement - just thinking (unknown file or non-file tool)
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

        process_time = (time.time() - start_time) * 1000  # ms
        logger.info(f"PreToolUse processed in {process_time:.2f}ms for {event.session_id}")

        return "agent_event", agent_event.model_dump()

    def _handle_post_tool_use(self, event: HookEvent, start_time: float) -> Tuple[str, Optional[dict]]:
        """
        Handle PostToolUse event - mark tool complete.

        Args:
            event: Hook event
            start_time: Timestamp when event was received

        Returns:
            Tuple of (message_type, message_data)
        """
        # Get agent state
        if event.session_id not in self.agents:
            logger.warning(f"PostToolUse for unknown session: {event.session_id}")
            return None, None

        agent = self.agents[event.session_id]

        # Create completion event
        agent_event = AgentEvent(
            agent_id=event.session_id,
            event_type="idle",
            target_path=agent.target_path,
            target_position=None,
            thought=None,
            tool_name=event.tool_name,
            timestamp=int(time.time() * 1000)
        )

        process_time = (time.time() - start_time) * 1000  # ms
        logger.info(f"PostToolUse processed in {process_time:.2f}ms for {event.session_id}")

        return "agent_event", agent_event.model_dump()


# Global agent service instance
agent_service = AgentService()
