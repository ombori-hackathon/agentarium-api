"""
Tests for agent state management and event processing.
"""

import os
import tempfile
import pytest
from app.services.agent import (
    AgentService,
    AgentState,
    generate_thought,
    extract_file_path,
    scan_filesystem
)
from app.schemas.filesystem import Position, FilesystemLayout, File, Folder
from app.schemas.events import HookEvent
from datetime import datetime


@pytest.fixture
def agent_service():
    """Create an agent service instance"""
    return AgentService()


@pytest.fixture
def sample_layout():
    """Sample filesystem layout for testing"""
    return FilesystemLayout(
        root="/test",
        folders=[
            Folder(
                path="/test/src",
                name="src",
                depth=1,
                file_count=2,
                position=Position(x=10.0, y=3.0, z=5.0),
                height=2.5
            )
        ],
        files=[
            File(
                path="/test/src/index.ts",
                name="index.ts",
                folder="/test/src",
                size=1024,
                position=Position(x=12.5, y=3.5, z=7.2)
            ),
            File(
                path="/test/src/app.ts",
                name="app.ts",
                folder="/test/src",
                size=2048,
                position=Position(x=8.3, y=3.5, z=4.1)
            )
        ],
        scanned_at=datetime.now()
    )


class TestAgentState:
    """Tests for AgentState class"""

    def test_agent_state_initialization(self):
        """Test AgentState is initialized with default values"""
        state = AgentState(agent_id="test-123")

        assert state.agent_id == "test-123"
        assert state.position == Position(x=0.0, y=0.0, z=0.0)
        assert state.current_action is None
        assert state.target_path is None
        assert state.thought is None

    def test_agent_state_update_position(self):
        """Test updating agent position"""
        state = AgentState(agent_id="test-123")
        new_pos = Position(x=10.0, y=5.0, z=15.0)

        state.position = new_pos

        assert state.position.x == 10.0
        assert state.position.y == 5.0
        assert state.position.z == 15.0


class TestThoughtGeneration:
    """Tests for thought text generation"""

    def test_read_tool_thought(self):
        """Test thought generation for Read tool"""
        thought = generate_thought("Read", {"file_path": "/src/index.ts"})
        assert thought == "Reading index.ts"

    def test_write_tool_thought(self):
        """Test thought generation for Write tool"""
        thought = generate_thought("Write", {"file_path": "/src/new.ts"})
        assert thought == "Writing new.ts"

    def test_edit_tool_thought(self):
        """Test thought generation for Edit tool"""
        thought = generate_thought("Edit", {"file_path": "/src/app.ts"})
        assert thought == "Editing app.ts"

    def test_bash_tool_thought(self):
        """Test thought generation for Bash tool"""
        thought = generate_thought("Bash", {"command": "npm test"})
        assert thought == "Running: npm test"

    def test_grep_tool_thought(self):
        """Test thought generation for Grep tool"""
        thought = generate_thought("Grep", {"pattern": "TODO"})
        assert thought == "Searching for: TODO"

    def test_glob_tool_thought(self):
        """Test thought generation for Glob tool"""
        thought = generate_thought("Glob", {"pattern": "**/*.ts"})
        assert thought == "Finding: **/*.ts"

    def test_unknown_tool_thought(self):
        """Test thought generation for unknown tool"""
        thought = generate_thought("UnknownTool", {})
        assert thought == "Using UnknownTool"

    def test_empty_input_thought(self):
        """Test thought generation with empty input"""
        thought = generate_thought("Read", {})
        assert thought == "Using Read"


class TestFilePathExtraction:
    """Tests for file path extraction from tool input"""

    def test_extract_from_read(self):
        """Test extracting path from Read tool"""
        path = extract_file_path("Read", {"file_path": "/src/index.ts"})
        assert path == "/src/index.ts"

    def test_extract_from_write(self):
        """Test extracting path from Write tool"""
        path = extract_file_path("Write", {"file_path": "/src/new.ts"})
        assert path == "/src/new.ts"

    def test_extract_from_edit(self):
        """Test extracting path from Edit tool"""
        path = extract_file_path("Edit", {"file_path": "/src/app.ts"})
        assert path == "/src/app.ts"

    def test_no_file_path(self):
        """Test extraction when no file_path in input"""
        path = extract_file_path("Bash", {"command": "npm test"})
        assert path is None

    def test_empty_input(self):
        """Test extraction with empty input"""
        path = extract_file_path("Read", {})
        assert path is None

    def test_extract_from_grep(self):
        """Test extracting path from Grep tool"""
        path = extract_file_path("Grep", {"pattern": "TODO", "path": "/src"})
        assert path == "/src"

    def test_extract_from_glob(self):
        """Test extracting path from Glob tool"""
        path = extract_file_path("Glob", {"pattern": "*.ts", "path": "/src"})
        assert path == "/src"

    def test_bash_returns_none(self):
        """Test Bash tool returns None (no path extraction)"""
        path = extract_file_path("Bash", {"command": "cat file.txt"})
        assert path is None


class TestAgentService:
    """Tests for AgentService"""

    def test_initialization(self, agent_service):
        """Test service initializes with empty state"""
        assert len(agent_service.agents) == 0
        assert agent_service.terrain_layout is None

    def test_set_terrain_layout(self, agent_service, sample_layout):
        """Test setting terrain layout"""
        agent_service.set_terrain_layout(sample_layout)

        assert agent_service.terrain_layout is not None
        assert len(agent_service.terrain_layout.files) == 2

    def test_get_file_position_known_file(self, agent_service, sample_layout):
        """Test getting position for known file"""
        agent_service.set_terrain_layout(sample_layout)

        position = agent_service.get_file_position("/test/src/index.ts")

        assert position is not None
        assert position.x == 12.5
        assert position.y == 3.5
        assert position.z == 7.2

    def test_get_file_position_unknown_file(self, agent_service, sample_layout):
        """Test getting position for unknown file returns None"""
        agent_service.set_terrain_layout(sample_layout)

        position = agent_service.get_file_position("/unknown/file.ts")

        assert position is None

    def test_get_file_position_no_layout(self, agent_service):
        """Test getting position when no layout set returns None"""
        position = agent_service.get_file_position("/src/index.ts")
        assert position is None

    def test_get_or_create_agent_new(self, agent_service):
        """Test creating new agent state"""
        state = agent_service.get_or_create_agent("session-123")

        assert state.agent_id == "session-123"
        assert "session-123" in agent_service.agents
        assert agent_service.agents["session-123"] == state

    def test_get_or_create_agent_existing(self, agent_service):
        """Test getting existing agent state"""
        # Create first time
        state1 = agent_service.get_or_create_agent("session-123")
        state1.thought = "Test thought"

        # Get again
        state2 = agent_service.get_or_create_agent("session-123")

        assert state1 is state2
        assert state2.thought == "Test thought"

    def test_remove_agent(self, agent_service):
        """Test removing agent state"""
        # Create agent
        agent_service.get_or_create_agent("session-123")
        assert "session-123" in agent_service.agents

        # Remove it
        result = agent_service.remove_agent("session-123")
        assert result is True
        assert "session-123" not in agent_service.agents

    def test_remove_nonexistent_agent(self, agent_service):
        """Test removing non-existent agent returns False"""
        result = agent_service.remove_agent("nonexistent")
        assert result is False

    def test_process_hook_event_with_file_tool(self, agent_service, sample_layout):
        """Test processing hook event with file operation"""
        agent_service.set_terrain_layout(sample_layout)

        event = HookEvent(
            session_id="session-123",
            hook_event_name="PreToolUse",
            tool_name="Read",
            tool_input={"file_path": "/test/src/index.ts"},
            cwd="/test"
        )

        messages = agent_service.process_hook_event(event)

        assert len(messages) == 1
        message_type, message_data = messages[0]
        assert message_type == "agent_event"
        assert message_data is not None
        assert message_data["agent_id"] == "session-123"
        assert message_data["event_type"] == "move"
        assert message_data["target_path"] == "/test/src/index.ts"
        assert message_data["target_position"] is not None
        assert message_data["target_position"]["x"] == 12.5
        assert message_data["thought"] == "Reading index.ts"
        assert message_data["tool_name"] == "Read"

    def test_process_hook_event_with_bash_tool(self, agent_service):
        """Test processing hook event with Bash tool (no file)"""
        event = HookEvent(
            session_id="session-456",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={"command": "npm test"},
            cwd="/test"
        )

        messages = agent_service.process_hook_event(event)

        assert len(messages) == 1
        message_type, message_data = messages[0]
        assert message_type == "agent_event"
        assert message_data is not None
        assert message_data["agent_id"] == "session-456"
        assert message_data["event_type"] == "think"
        assert message_data["target_path"] is None
        assert message_data["target_position"] is None
        assert message_data["thought"] == "Running: npm test"
        assert message_data["tool_name"] == "Bash"

    def test_process_hook_event_unknown_file(self, agent_service, sample_layout):
        """Test processing event with unknown file path"""
        agent_service.set_terrain_layout(sample_layout)

        event = HookEvent(
            session_id="session-789",
            hook_event_name="PreToolUse",
            tool_name="Read",
            tool_input={"file_path": "/unknown/file.ts"},
            cwd="/test"
        )

        messages = agent_service.process_hook_event(event)

        assert len(messages) == 1
        message_type, message_data = messages[0]
        # Agent should stay in place for unknown files
        assert message_type == "agent_event"
        assert message_data is not None
        assert message_data["event_type"] == "think"
        assert message_data["target_position"] is None
        assert message_data["thought"] == "Reading file.ts"

    def test_process_hook_event_updates_agent_state(self, agent_service, sample_layout):
        """Test that processing event updates agent state"""
        agent_service.set_terrain_layout(sample_layout)

        event = HookEvent(
            session_id="session-abc",
            hook_event_name="PreToolUse",
            tool_name="Write",
            tool_input={"file_path": "/test/src/app.ts"},
            cwd="/test"
        )

        agent_service.process_hook_event(event)

        # Check agent state was updated
        state = agent_service.agents["session-abc"]
        assert state.target_path == "/test/src/app.ts"
        assert state.thought == "Writing app.ts"
        assert state.current_action == "move"
        assert state.position.x == 8.3  # Updated to target position

    def test_multiple_agents(self, agent_service):
        """Test managing multiple agents"""
        event1 = HookEvent(
            session_id="session-1",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={"command": "test1"},
            cwd="/test"
        )

        event2 = HookEvent(
            session_id="session-2",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={"command": "test2"},
            cwd="/test"
        )

        agent_service.process_hook_event(event1)
        agent_service.process_hook_event(event2)

        assert len(agent_service.agents) == 2
        assert "session-1" in agent_service.agents
        assert "session-2" in agent_service.agents
        assert agent_service.agents["session-1"].thought == "Running: test1"
        assert agent_service.agents["session-2"].thought == "Running: test2"

    def test_session_start_event_without_cwd(self, agent_service):
        """Test SessionStart event without cwd just spawns agent"""
        event = HookEvent(
            session_id="session-start",
            hook_event_name="SessionStart"
        )

        messages = agent_service.process_hook_event(event)

        # Should only have agent_spawn
        assert len(messages) == 1
        message_type, message_data = messages[0]
        assert message_type == "agent_spawn"
        assert message_data["agent_id"] == "session-start"
        assert message_data["position"]["x"] == 0.0
        assert message_data["position"]["y"] == 0.0
        assert message_data["position"]["z"] == 0.0
        assert "session-start" in agent_service.agents

    def test_session_end_event(self, agent_service):
        """Test SessionEnd event removes agent"""
        # Create agent first
        agent_service.get_or_create_agent("session-end")

        event = HookEvent(
            session_id="session-end",
            hook_event_name="SessionEnd",
            cwd="/test"
        )

        messages = agent_service.process_hook_event(event)

        assert len(messages) == 1
        message_type, message_data = messages[0]
        assert message_type == "agent_despawn"
        assert message_data["agent_id"] == "session-end"
        assert "session-end" not in agent_service.agents

    def test_stop_event(self, agent_service):
        """Test Stop event also removes agent"""
        agent_service.get_or_create_agent("session-stop")

        event = HookEvent(
            session_id="session-stop",
            hook_event_name="Stop",
            cwd="/test"
        )

        messages = agent_service.process_hook_event(event)

        assert len(messages) == 1
        message_type, _ = messages[0]
        assert message_type == "agent_despawn"
        assert "session-stop" not in agent_service.agents

    def test_post_tool_use_event(self, agent_service):
        """Test PostToolUse event marks tool complete"""
        # Create agent and do pre-tool use first
        event_pre = HookEvent(
            session_id="session-post",
            hook_event_name="PreToolUse",
            tool_name="Read",
            tool_input={"file_path": "/test/file.ts"},
            cwd="/test"
        )
        agent_service.process_hook_event(event_pre)

        # Now send PostToolUse
        event_post = HookEvent(
            session_id="session-post",
            hook_event_name="PostToolUse",
            tool_name="Read",
            cwd="/test"
        )

        messages = agent_service.process_hook_event(event_post)

        assert len(messages) == 1
        message_type, message_data = messages[0]
        assert message_type == "agent_event"
        assert message_data["event_type"] == "idle"
        assert message_data["tool_name"] == "Read"

    def test_unknown_event_ignored(self, agent_service):
        """Test unknown event types are ignored"""
        event = HookEvent(
            session_id="session-unknown",
            hook_event_name="UnknownEvent",
            cwd="/test"
        )

        messages = agent_service.process_hook_event(event)

        assert len(messages) == 0


class TestSessionStartWithTerrain:
    """Tests for SessionStart with auto-terrain loading"""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some folders and files
            src_dir = os.path.join(tmpdir, "src")
            os.makedirs(src_dir)

            # Create some files
            with open(os.path.join(tmpdir, "README.md"), "w") as f:
                f.write("# Test Project")

            with open(os.path.join(src_dir, "index.ts"), "w") as f:
                f.write("console.log('hello');")

            with open(os.path.join(src_dir, "app.ts"), "w") as f:
                f.write("export default {};")

            yield tmpdir

    def test_session_start_with_cwd_loads_terrain(self, temp_project):
        """Test SessionStart with cwd triggers terrain loading"""
        agent_service = AgentService()

        event = HookEvent(
            session_id="session-terrain",
            hook_event_name="SessionStart",
            cwd=temp_project
        )

        messages = agent_service.process_hook_event(event)

        # Should have: terrain_loading, filesystem, terrain_complete, agent_spawn
        assert len(messages) == 4

        # Check message types in order
        assert messages[0][0] == "terrain_loading"
        assert messages[0][1]["cwd"] == temp_project
        assert messages[0][1]["message"] == "Creating world..."

        assert messages[1][0] == "filesystem"
        assert messages[1][1]["root"] == temp_project

        assert messages[2][0] == "terrain_complete"
        assert messages[2][1]["folder_count"] == 1  # src folder
        assert messages[2][1]["file_count"] == 3  # README.md, index.ts, app.ts

        assert messages[3][0] == "agent_spawn"
        assert messages[3][1]["agent_id"] == "session-terrain"

    def test_session_start_sets_current_cwd(self, temp_project):
        """Test SessionStart updates current_cwd"""
        agent_service = AgentService()

        event = HookEvent(
            session_id="session-cwd",
            hook_event_name="SessionStart",
            cwd=temp_project
        )

        agent_service.process_hook_event(event)

        assert agent_service.current_cwd == temp_project
        assert agent_service.terrain_layout is not None

    def test_session_start_same_cwd_no_reload(self, temp_project):
        """Test SessionStart with same cwd doesn't reload terrain"""
        agent_service = AgentService()

        # First session
        event1 = HookEvent(
            session_id="session-1",
            hook_event_name="SessionStart",
            cwd=temp_project
        )
        messages1 = agent_service.process_hook_event(event1)
        assert len(messages1) == 4  # Full terrain loading

        # Second session with same cwd
        event2 = HookEvent(
            session_id="session-2",
            hook_event_name="SessionStart",
            cwd=temp_project
        )
        messages2 = agent_service.process_hook_event(event2)

        # Should only have agent_spawn (no terrain reload)
        assert len(messages2) == 1
        assert messages2[0][0] == "agent_spawn"

    def test_session_start_different_cwd_reloads_terrain(self, temp_project):
        """Test SessionStart with different cwd reloads terrain"""
        agent_service = AgentService()

        # First session
        event1 = HookEvent(
            session_id="session-1",
            hook_event_name="SessionStart",
            cwd=temp_project
        )
        agent_service.process_hook_event(event1)

        # Create another temp directory
        with tempfile.TemporaryDirectory() as tmpdir2:
            os.makedirs(os.path.join(tmpdir2, "lib"))

            event2 = HookEvent(
                session_id="session-2",
                hook_event_name="SessionStart",
                cwd=tmpdir2
            )
            messages2 = agent_service.process_hook_event(event2)

            # Should have full terrain loading for new cwd
            assert len(messages2) == 4
            assert messages2[0][0] == "terrain_loading"
            assert messages2[1][0] == "filesystem"
            assert agent_service.current_cwd == tmpdir2

    def test_session_start_invalid_cwd_still_spawns_agent(self, agent_service):
        """Test SessionStart with invalid cwd still spawns agent"""
        event = HookEvent(
            session_id="session-invalid",
            hook_event_name="SessionStart",
            cwd="/nonexistent/path/that/does/not/exist"
        )

        messages = agent_service.process_hook_event(event)

        # Should have terrain_loading (which starts) then agent_spawn
        # filesystem scanning fails but agent still spawns
        assert any(msg[0] == "agent_spawn" for msg in messages)
        assert "session-invalid" in agent_service.agents


class TestScanFilesystem:
    """Tests for filesystem scanning function"""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = os.path.join(tmpdir, "src")
            os.makedirs(src_dir)

            with open(os.path.join(tmpdir, "README.md"), "w") as f:
                f.write("# Test")

            with open(os.path.join(src_dir, "index.ts"), "w") as f:
                f.write("test")

            yield tmpdir

    def test_scan_filesystem_returns_layout(self, temp_project):
        """Test scan_filesystem returns proper layout"""
        layout = scan_filesystem(temp_project)

        assert layout.root == temp_project
        assert len(layout.folders) == 1  # src
        assert len(layout.files) == 2  # README.md, index.ts

    def test_scan_filesystem_calculates_positions(self, temp_project):
        """Test scan_filesystem calculates positions"""
        layout = scan_filesystem(temp_project)

        # Check that positions are calculated
        for folder in layout.folders:
            assert folder.position is not None
            assert folder.height is not None

        for file in layout.files:
            assert file.position is not None

    def test_scan_filesystem_excludes_node_modules(self):
        """Test scan_filesystem excludes node_modules"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create node_modules directory
            node_modules = os.path.join(tmpdir, "node_modules")
            os.makedirs(node_modules)
            with open(os.path.join(node_modules, "package.json"), "w") as f:
                f.write("{}")

            # Create src directory
            src_dir = os.path.join(tmpdir, "src")
            os.makedirs(src_dir)

            layout = scan_filesystem(tmpdir)

            # Should not include node_modules
            folder_names = [f.name for f in layout.folders]
            assert "node_modules" not in folder_names
            assert "src" in folder_names

    def test_scan_filesystem_invalid_path_raises(self):
        """Test scan_filesystem raises for invalid path"""
        with pytest.raises(ValueError):
            scan_filesystem("/nonexistent/path")
