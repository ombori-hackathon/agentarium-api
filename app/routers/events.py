from fastapi import APIRouter

from app.schemas.events import HookEvent, EventResponse, AgentEvent
from app.websocket import manager

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("", response_model=EventResponse)
async def receive_event(event: HookEvent):
    """
    Receive hook events from Claude and broadcast to WebSocket clients
    """
    # Convert hook event to agent event for broadcast
    agent_event = AgentEvent(
        session_id=event.session_id,
        event_type=event.hook_event_name,
        tool_name=event.tool_name,
        tool_input=event.tool_input,
        cwd=event.cwd
    )

    # Broadcast to all connected WebSocket clients
    await manager.broadcast("agent_event", agent_event.model_dump())

    return EventResponse(status="ok")
