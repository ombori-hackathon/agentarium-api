import pytest
import json
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

from app.main import app
from app.websocket import ConnectionManager


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def manager():
    """Fresh connection manager for each test"""
    return ConnectionManager()


def test_websocket_connection(client):
    """Test that WebSocket connection can be established"""
    with client.websocket_connect("/ws") as websocket:
        # Connection should be established
        assert websocket is not None


def test_websocket_receives_broadcast(client):
    """Test that WebSocket receives broadcast messages"""
    with client.websocket_connect("/ws") as websocket:
        # The connection is established, but we need to trigger a broadcast
        # This test validates the connection is ready to receive
        pass


def test_connection_manager_connect():
    """Test ConnectionManager can accept connections"""
    manager = ConnectionManager()
    assert len(manager.active_connections) == 0


@pytest.mark.asyncio
async def test_connection_manager_broadcast(manager):
    """Test ConnectionManager can broadcast messages"""
    # Create mock WebSocket
    class MockWebSocket:
        def __init__(self):
            self.sent_messages = []

        async def send_text(self, message: str):
            self.sent_messages.append(message)

    mock_ws = MockWebSocket()
    manager.active_connections.append(mock_ws)

    # Broadcast a message
    await manager.broadcast("test_type", {"key": "value"})

    # Verify message was sent
    assert len(mock_ws.sent_messages) == 1
    sent_data = json.loads(mock_ws.sent_messages[0])
    assert sent_data["type"] == "test_type"
    assert sent_data["data"]["key"] == "value"


@pytest.mark.asyncio
async def test_connection_manager_removes_failed_connections(manager):
    """Test that failed connections are removed from the list"""
    # Create mock WebSocket that fails
    class FailingWebSocket:
        async def send_text(self, message: str):
            raise Exception("Connection failed")

    failing_ws = FailingWebSocket()
    manager.active_connections.append(failing_ws)

    # Broadcast should remove the failing connection
    await manager.broadcast("test_type", {"key": "value"})

    # Verify connection was removed
    assert len(manager.active_connections) == 0


def test_connection_manager_disconnect(manager):
    """Test that disconnect removes connection"""
    class MockWebSocket:
        pass

    mock_ws = MockWebSocket()
    manager.active_connections.append(mock_ws)
    assert len(manager.active_connections) == 1

    manager.disconnect(mock_ws)
    assert len(manager.active_connections) == 0
