import json
from typing import Any, Dict, List
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket client connections and broadcasts"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and store a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        self.active_connections.remove(websocket)

    async def broadcast(self, message_type: str, data: Dict[str, Any]):
        """Broadcast a message to all connected clients"""
        message = {"type": message_type, "data": data}
        message_json = json.dumps(message, default=str)

        # Send to all connected clients
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception:
                # Mark for removal if send fails
                disconnected.append(connection)

        # Remove disconnected clients
        for connection in disconnected:
            self.active_connections.remove(connection)


# Global connection manager instance
manager = ConnectionManager()
