from typing import Any, Dict
from pydantic import BaseModel


class HookEvent(BaseModel):
    """Event data received from Claude hooks"""
    session_id: str
    hook_event_name: str
    tool_name: str | None = None
    tool_input: Dict[str, Any] | None = None
    cwd: str | None = None


class AgentEvent(BaseModel):
    """Agent event data for WebSocket broadcast"""
    session_id: str
    event_type: str  # hook_event_name
    tool_name: str | None = None
    tool_input: Dict[str, Any] | None = None
    cwd: str | None = None


class EventResponse(BaseModel):
    """Response from events endpoint"""
    status: str = "ok"


class AgentSpawn(BaseModel):
    """Agent spawn event"""
    agent_id: str
    position: Dict[str, float]  # {"x": 0.0, "y": 0.0, "z": 0.0}
    agent_type: str = "default"


class AgentDespawn(BaseModel):
    """Agent despawn event"""
    agent_id: str
