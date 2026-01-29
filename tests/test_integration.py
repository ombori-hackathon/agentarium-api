"""
Integration tests for full event flow: hook → backend → websocket.

Tests the complete flow from receiving a hook event through the API
to broadcasting WebSocket messages to connected clients.
"""

import pytest
import json
from fastapi.testclient import TestClient

from app.main import app
from app.services.agent import agent_service
from app.schemas.filesystem import Position, FilesystemLayout, File, Folder
from datetime import datetime


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


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


@pytest.fixture(autouse=True)
def setup_agent_service(sample_layout):
    """Set up agent service with terrain layout before each test"""
    agent_service.set_terrain_layout(sample_layout)
    agent_service.agents.clear()  # Clear any existing agents
    yield
    agent_service.agents.clear()  # Clean up after test


class TestSessionLifecycle:
    """Tests for session lifecycle events"""

    def test_session_start_spawns_agent(self, client):
        """Test SessionStart event spawns agent at origin"""
        with client.websocket_connect("/ws") as websocket:
            # Post SessionStart event
            event_data = {
                "session_id": "test-session-123",
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            }

            response = client.post("/api/events", json=event_data)
            assert response.status_code == 200

            # Receive agent_spawn message
            data = websocket.receive_text()
            message = json.loads(data)

            assert message["type"] == "agent_spawn"
            assert message["data"]["agent_id"] == "test-session-123"
            assert message["data"]["position"]["x"] == 0.0
            assert message["data"]["position"]["y"] == 0.0
            assert message["data"]["position"]["z"] == 0.0
            assert message["data"]["color"] == "#e07850"

            # Verify agent was created in service
            assert "test-session-123" in agent_service.agents

    def test_session_end_despawns_agent(self, client):
        """Test SessionEnd event despawns agent"""
        with client.websocket_connect("/ws") as websocket:
            # First spawn the agent
            event_data = {
                "session_id": "test-session-456",
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            }
            client.post("/api/events", json=event_data)
            websocket.receive_text()  # Consume spawn message

            # Now end the session
            event_data = {
                "session_id": "test-session-456",
                "hook_event_name": "SessionEnd",
                "cwd": "/test"
            }

            response = client.post("/api/events", json=event_data)
            assert response.status_code == 200

            # Receive agent_despawn message
            data = websocket.receive_text()
            message = json.loads(data)

            assert message["type"] == "agent_despawn"
            assert message["data"]["agent_id"] == "test-session-456"

            # Verify agent was removed from service
            assert "test-session-456" not in agent_service.agents

    def test_stop_event_despawns_agent(self, client):
        """Test Stop event also despawns agent"""
        with client.websocket_connect("/ws") as websocket:
            # Spawn agent
            client.post("/api/events", json={
                "session_id": "test-session-789",
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            })
            websocket.receive_text()  # Consume spawn

            # Send Stop event
            response = client.post("/api/events", json={
                "session_id": "test-session-789",
                "hook_event_name": "Stop",
                "cwd": "/test"
            })

            assert response.status_code == 200

            # Should receive despawn
            data = websocket.receive_text()
            message = json.loads(data)
            assert message["type"] == "agent_despawn"
            assert "test-session-789" not in agent_service.agents


class TestToolUseEvents:
    """Tests for tool use events"""

    def test_pre_tool_use_with_known_file(self, client):
        """Test PreToolUse with known file moves agent"""
        with client.websocket_connect("/ws") as websocket:
            # Spawn agent first
            client.post("/api/events", json={
                "session_id": "test-abc",
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            })
            websocket.receive_text()  # Consume spawn

            # Send tool use event
            event_data = {
                "session_id": "test-abc",
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/test/src/index.ts"},
                "cwd": "/test"
            }

            response = client.post("/api/events", json=event_data)
            assert response.status_code == 200

            # Receive agent_event message
            data = websocket.receive_text()
            message = json.loads(data)

            assert message["type"] == "agent_event"
            assert message["data"]["agent_id"] == "test-abc"
            assert message["data"]["event_type"] == "move"
            assert message["data"]["tool_name"] == "Read"
            assert message["data"]["target_path"] == "/test/src/index.ts"
            assert message["data"]["target_position"]["x"] == 12.5
            assert message["data"]["target_position"]["y"] == 3.5
            assert message["data"]["target_position"]["z"] == 7.2
            assert message["data"]["thought"] == "Reading index.ts"

    def test_pre_tool_use_with_unknown_file(self, client):
        """Test PreToolUse with unknown file keeps agent in place"""
        with client.websocket_connect("/ws") as websocket:
            # Spawn agent
            client.post("/api/events", json={
                "session_id": "test-xyz",
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            })
            websocket.receive_text()

            # Send tool use with unknown file
            event_data = {
                "session_id": "test-xyz",
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/unknown/file.ts"},
                "cwd": "/test"
            }

            response = client.post("/api/events", json=event_data)
            assert response.status_code == 200

            # Receive agent_event
            data = websocket.receive_text()
            message = json.loads(data)

            # Agent should "think" instead of move
            assert message["data"]["event_type"] == "think"
            assert message["data"]["target_position"] is None
            assert message["data"]["thought"] == "Reading file.ts"

    def test_pre_tool_use_with_grep(self, client):
        """Test PreToolUse with Grep tool extracts path correctly"""
        with client.websocket_connect("/ws") as websocket:
            # Spawn agent
            client.post("/api/events", json={
                "session_id": "test-grep",
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            })
            websocket.receive_text()

            # Send Grep tool use with path parameter
            event_data = {
                "session_id": "test-grep",
                "hook_event_name": "PreToolUse",
                "tool_name": "Grep",
                "tool_input": {
                    "pattern": "TODO",
                    "path": "/test/src"
                },
                "cwd": "/test"
            }

            response = client.post("/api/events", json=event_data)
            assert response.status_code == 200

            # Receive agent_event
            data = websocket.receive_text()
            message = json.loads(data)

            # Grep should extract path from "path" field
            assert message["data"]["target_path"] == "/test/src"
            assert message["data"]["thought"] == "Searching for: TODO"

    def test_pre_tool_use_with_bash(self, client):
        """Test PreToolUse with Bash tool (no file path)"""
        with client.websocket_connect("/ws") as websocket:
            # Spawn agent
            client.post("/api/events", json={
                "session_id": "test-bash",
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            })
            websocket.receive_text()

            # Send Bash tool use
            event_data = {
                "session_id": "test-bash",
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "npm test"},
                "cwd": "/test"
            }

            response = client.post("/api/events", json=event_data)
            assert response.status_code == 200

            # Receive agent_event
            data = websocket.receive_text()
            message = json.loads(data)

            # Bash has no file, so agent should think
            assert message["data"]["event_type"] == "think"
            assert message["data"]["target_path"] is None
            assert message["data"]["thought"] == "Running: npm test"

    def test_post_tool_use(self, client):
        """Test PostToolUse marks tool as complete"""
        with client.websocket_connect("/ws") as websocket:
            # Spawn and start tool use
            client.post("/api/events", json={
                "session_id": "test-post",
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            })
            websocket.receive_text()

            client.post("/api/events", json={
                "session_id": "test-post",
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/test/src/app.ts"},
                "cwd": "/test"
            })
            websocket.receive_text()

            # Send PostToolUse
            event_data = {
                "session_id": "test-post",
                "hook_event_name": "PostToolUse",
                "tool_name": "Read",
                "cwd": "/test"
            }

            response = client.post("/api/events", json=event_data)
            assert response.status_code == 200

            # Receive completion event
            data = websocket.receive_text()
            message = json.loads(data)

            assert message["data"]["event_type"] == "idle"
            assert message["data"]["tool_name"] == "Read"


class TestFullEventFlow:
    """Test complete end-to-end flows"""

    def test_full_session_flow(self, client):
        """Test complete session: start → tool use → end"""
        with client.websocket_connect("/ws") as websocket:
            session_id = "test-full-flow"

            # 1. Session starts
            client.post("/api/events", json={
                "session_id": session_id,
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            })

            msg = json.loads(websocket.receive_text())
            assert msg["type"] == "agent_spawn"
            assert msg["data"]["agent_id"] == session_id

            # 2. Agent reads a file
            client.post("/api/events", json={
                "session_id": session_id,
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/test/src/index.ts"},
                "cwd": "/test"
            })

            msg = json.loads(websocket.receive_text())
            assert msg["type"] == "agent_event"
            assert msg["data"]["event_type"] == "move"

            # 3. Tool completes
            client.post("/api/events", json={
                "session_id": session_id,
                "hook_event_name": "PostToolUse",
                "tool_name": "Read",
                "cwd": "/test"
            })

            msg = json.loads(websocket.receive_text())
            assert msg["type"] == "agent_event"
            assert msg["data"]["event_type"] == "idle"

            # 4. Agent writes a different file
            client.post("/api/events", json={
                "session_id": session_id,
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "/test/src/app.ts"},
                "cwd": "/test"
            })

            msg = json.loads(websocket.receive_text())
            assert msg["type"] == "agent_event"
            assert msg["data"]["event_type"] == "move"
            assert msg["data"]["thought"] == "Writing app.ts"

            # 5. Session ends
            client.post("/api/events", json={
                "session_id": session_id,
                "hook_event_name": "SessionEnd",
                "cwd": "/test"
            })

            msg = json.loads(websocket.receive_text())
            assert msg["type"] == "agent_despawn"

            # Verify cleanup
            assert session_id not in agent_service.agents

    def test_multiple_agents(self, client):
        """Test multiple concurrent agents"""
        with client.websocket_connect("/ws") as websocket:
            # Start two sessions
            client.post("/api/events", json={
                "session_id": "agent-1",
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            })
            msg1 = json.loads(websocket.receive_text())
            assert msg1["data"]["agent_id"] == "agent-1"

            client.post("/api/events", json={
                "session_id": "agent-2",
                "hook_event_name": "SessionStart",
                "cwd": "/test"
            })
            msg2 = json.loads(websocket.receive_text())
            assert msg2["data"]["agent_id"] == "agent-2"

            # Both agents should exist
            assert len(agent_service.agents) == 2
            assert "agent-1" in agent_service.agents
            assert "agent-2" in agent_service.agents

            # End first session
            client.post("/api/events", json={
                "session_id": "agent-1",
                "hook_event_name": "SessionEnd",
                "cwd": "/test"
            })
            websocket.receive_text()

            # Only agent-2 should remain
            assert len(agent_service.agents) == 1
            assert "agent-2" in agent_service.agents


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_despawn_nonexistent_agent(self, client):
        """Test despawning an agent that doesn't exist"""
        response = client.post("/api/events", json={
            "session_id": "nonexistent",
            "hook_event_name": "SessionEnd",
            "cwd": "/test"
        })

        # Should not crash, just return ok
        assert response.status_code == 200

    def test_post_tool_use_without_pre(self, client):
        """Test PostToolUse without PreToolUse"""
        response = client.post("/api/events", json={
            "session_id": "test-orphan",
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "cwd": "/test"
        })

        # Should not crash
        assert response.status_code == 200

    def test_unknown_event_ignored(self, client):
        """Test unknown hook event names are ignored"""
        response = client.post("/api/events", json={
            "session_id": "test-unknown",
            "hook_event_name": "UnknownEvent",
            "cwd": "/test"
        })

        # Should return ok but not crash
        assert response.status_code == 200
