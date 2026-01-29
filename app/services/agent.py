"""
Agent state management service for Agentarium.

This service tracks agent state, processes hook events, and generates agent events
for WebSocket broadcast to clients.
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from app.schemas.events import (
    HookEvent, AgentEvent, AgentSpawn, AgentDespawn,
    TerrainLoading, TerrainComplete
)
from app.schemas.filesystem import Position, FilesystemLayout, Folder, File
from app.services.terrain import calculate_positions_for_layout

logger = logging.getLogger(__name__)

# Directories to exclude from filesystem scanning for performance
EXCLUDED_DIRS = {
    # Package managers
    'node_modules', '.pnpm', 'bower_components', 'vendor', 'packages',
    # Version control
    '.git', '.svn', '.hg',
    # Build outputs
    'dist', 'build', 'out', 'target', '.next', '.nuxt', '.output',
    # Caches
    '.cache', '__pycache__', '.pytest_cache', '.mypy_cache', '.tox',
    # Virtual environments
    '.venv', 'venv', 'env', '.env',
    # IDE/Editor
    '.idea', '.vscode',
    # Logs/temp
    'logs', 'tmp', 'temp', '.tmp',
    # Coverage/reports
    'coverage', '.nyc_output', 'htmlcov',
}

MAX_DEPTH = 5


def scan_filesystem(path: str) -> FilesystemLayout:
    """
    Scan a directory and return its structure with positions.

    Args:
        path: Root path to scan

    Returns:
        FilesystemLayout with positions calculated
    """
    root_path = Path(path)

    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"Invalid directory: {path}")

    folders: List[Folder] = []
    files: List[File] = []
    root_depth = len(root_path.parts)

    for dirpath, dirnames, filenames in os.walk(root_path):
        current_path = Path(dirpath)
        current_depth = len(current_path.parts) - root_depth

        # Filter excluded directories
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]

        if current_depth >= MAX_DEPTH:
            dirnames.clear()

        if current_path != root_path:
            file_count = len(filenames)
            folders.append(Folder(
                path=str(current_path),
                name=current_path.name,
                depth=current_depth,
                file_count=file_count
            ))

        for filename in filenames:
            file_path = current_path / filename
            try:
                file_size = file_path.stat().st_size
                files.append(File(
                    path=str(file_path),
                    name=filename,
                    folder=str(current_path),
                    size=file_size
                ))
            except (OSError, PermissionError):
                continue

    layout = FilesystemLayout(
        root=str(root_path),
        folders=folders,
        files=files,
        scanned_at=datetime.now(timezone.utc)
    )

    return calculate_positions_for_layout(layout)


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
    - Auto-loads terrain on SessionStart based on cwd
    """

    def __init__(self):
        self.agents: Dict[str, AgentState] = {}
        self.terrain_layout: Optional[FilesystemLayout] = None
        self.current_cwd: Optional[str] = None

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

    def process_hook_event(self, event: HookEvent) -> List[Tuple[str, Optional[dict]]]:
        """
        Process a hook event and generate WebSocket messages.

        This method handles the full session lifecycle:
        - SessionStart: scan filesystem, broadcast terrain_loading, filesystem, terrain_complete, agent_spawn
        - PreToolUse: move agent to file location
        - PostToolUse: mark tool complete
        - SessionEnd/Stop: despawn agent

        Args:
            event: Hook event from Claude

        Returns:
            List of (message_type, message_data) tuples for WebSocket broadcast.
            Returns empty list if event should be ignored.
        """
        start_time = time.time()
        logger.info(f"Event received: {event.session_id} - {event.hook_event_name} at {start_time}")

        # Handle session lifecycle events
        if event.hook_event_name == "SessionStart":
            return self._handle_session_start(event, start_time)
        elif event.hook_event_name in ("SessionEnd", "Stop"):
            result = self._handle_session_end(event, start_time)
            return [result] if result[0] else []
        elif event.hook_event_name == "PreToolUse":
            result = self._handle_pre_tool_use(event, start_time)
            return [result] if result[0] else []
        elif event.hook_event_name == "PostToolUse":
            result = self._handle_post_tool_use(event, start_time)
            return [result] if result[0] else []
        else:
            logger.debug(f"Ignoring event: {event.hook_event_name}")
            return []

    def _handle_session_start(self, event: HookEvent, start_time: float) -> List[Tuple[str, dict]]:
        """
        Handle SessionStart event - auto-load terrain and spawn agent.

        This method:
        1. Broadcasts terrain_loading event
        2. Scans filesystem at cwd (if provided and different from current)
        3. Broadcasts filesystem layout
        4. Broadcasts terrain_complete event
        5. Spawns agent at origin

        Args:
            event: Hook event
            start_time: Timestamp when event was received

        Returns:
            List of (message_type, message_data) tuples
        """
        messages: List[Tuple[str, dict]] = []
        cwd = event.cwd

        # Auto-load terrain if cwd is provided
        if cwd and cwd != self.current_cwd:
            logger.info(f"SessionStart with new cwd: {cwd}")

            # 1. Broadcast terrain_loading
            loading_event = TerrainLoading(
                session_id=event.session_id,
                cwd=cwd,
                message="Creating world..."
            )
            messages.append(("terrain_loading", loading_event.model_dump()))

            # 2. Scan filesystem and broadcast layout
            try:
                layout = scan_filesystem(cwd)
                self.set_terrain_layout(layout)
                self.current_cwd = cwd

                # Broadcast filesystem layout
                messages.append(("filesystem", layout.model_dump()))

                # 3. Broadcast terrain_complete
                complete_event = TerrainComplete(
                    session_id=event.session_id,
                    folder_count=len(layout.folders),
                    file_count=len(layout.files)
                )
                messages.append(("terrain_complete", complete_event.model_dump()))

                logger.info(f"Terrain loaded: {len(layout.folders)} folders, {len(layout.files)} files")

            except Exception as e:
                logger.error(f"Failed to scan filesystem at {cwd}: {e}")
                # Still spawn agent even if terrain loading fails

        # Create new agent at origin
        agent = self.get_or_create_agent(event.session_id)
        agent.position = Position(x=0.0, y=0.0, z=0.0)

        spawn_event = AgentSpawn(
            agent_id=event.session_id,
            position=agent.position,
            color="#e07850"
        )
        messages.append(("agent_spawn", spawn_event.model_dump()))

        process_time = (time.time() - start_time) * 1000  # ms
        logger.info(f"SessionStart processed in {process_time:.2f}ms for {event.session_id}")

        return messages

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
