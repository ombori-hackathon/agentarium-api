from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel

from app.schemas.filesystem import Position


class HookEvent(BaseModel):
    """Event data received from Claude hooks"""
    session_id: str
    hook_event_name: str
    tool_name: str | None = None
    tool_input: Dict[str, Any] | None = None
    cwd: str | None = None


class AgentEvent(BaseModel):
    """Agent event data for WebSocket broadcast"""
    type: Literal["agent_event"] = "agent_event"
    agent_id: str
    event_type: Literal["move", "read", "write", "think", "idle"]
    target_path: Optional[str] = None
    target_position: Optional[Position] = None
    thought: Optional[str] = None
    tool_name: Optional[str] = None
    timestamp: int


class EventResponse(BaseModel):
    """Response from events endpoint"""
    status: str = "ok"


class AgentSpawn(BaseModel):
    """Agent spawn event"""
    type: Literal["agent_spawn"] = "agent_spawn"
    agent_id: str
    position: Position
    color: str = "#e07850"


class AgentDespawn(BaseModel):
    """Agent despawn event"""
    type: Literal["agent_despawn"] = "agent_despawn"
    agent_id: str
