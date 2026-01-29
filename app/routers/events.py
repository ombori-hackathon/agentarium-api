from fastapi import APIRouter

from app.schemas.events import HookEvent, EventResponse
from app.services.agent import agent_service
from app.websocket import manager

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("", response_model=EventResponse)
async def receive_event(event: HookEvent):
    """
    Receive hook events from Claude and broadcast to WebSocket clients
    """
    # Process hook event through agent service
    agent_event = agent_service.process_hook_event(event)

    # Broadcast agent event to all connected WebSocket clients
    if agent_event:
        await manager.broadcast("agent_event", agent_event.model_dump())

    return EventResponse(status="ok")
